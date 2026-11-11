"""¿Quien abre esa terminal? Mira la pantalla y anota cada ventana de consola que aparece.

Nace del 2026-11-10, pedido de Martin: *"se me abre una terminal y yo no se que es lo que
hace... me da miedo y puede que haya algo malicioso"*. Leer el codigo dice quien PODRIA
abrir una ventana; esto dice quien la ABRIO, con nombre, linea de comando y de quien es hijo.

    D:/IA/envs/wpp/python.exe -m pruebas.ver_terminales              # mira 5 minutos
    D:/IA/envs/wpp/python.exe -m pruebas.ver_terminales --segundos 900

No toca nada: no cierra ventanas ni mata procesos, solo mira. No gasta tokens.

Como sabe que una terminal se VIO, y no solo que existio:
  - enumera las ventanas de arriba de todo que estan VISIBLES y son de consola: la clasica
    (`ConsoleWindowClass`) y la de la Terminal de Windows (`CASCADIA_HOSTING_WINDOW_CLASS`);
  - y mira si nacio un `OpenConsole.exe`, que es lo que Windows lanza cuando le pasa una
    consola nueva a la Terminal — o sea, cuando la ventana se dibuja.
⚠ Un `conhost.exe` nuevo NO alcanza como señal: tambien nace uno por cada proceso lanzado
SIN ventana (`CREATE_NO_WINDOW`), que es lo que hacen bien las sesiones del panel. Por eso
los `conhost` no se cuentan: contarlos daria decenas de falsas alarmas por minuto.
⚠ Un proceso que vive menos que una vuelta del bucle (unos 40 ms) se escapa de la lista de
"quien nacio", pero su ventana igual queda anotada con el titulo, que suele ser el programa.
"""
import ctypes
import sys
import time
from ctypes import wintypes

import psutil

CLASES = {"ConsoleWindowClass": "consola clasica",
          "CASCADIA_HOSTING_WINDOW_CLASS": "Terminal de Windows"}
# Programas que, lanzados sin esconder, traen una ventana de consola.
DE_CONSOLA = {"cmd.exe", "powershell.exe", "pwsh.exe", "python.exe", "node.exe", "bash.exe",
              "ssh.exe", "scp.exe", "git.exe", "curl.exe", "docker.exe", "wsl.exe",
              "ffmpeg.exe", "ffprobe.exe", "tailscale.exe", "taskkill.exe", "timeout.exe"}

# Los que dibujan o sostienen la consola: nacen CON la terminal, no la causan.
ANFITRIONES = {"conhost.exe", "openconsole.exe", "windowsterminal.exe"}

_u32 = ctypes.windll.user32
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def ventanas_de_consola():
    """{hwnd: (clase, titulo, pid)} de las ventanas de consola que se VEN ahora."""
    halladas = {}

    def cada(hwnd, _):
        if not _u32.IsWindowVisible(hwnd):
            return True
        clase = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(hwnd, clase, 128)
        if clase.value in CLASES:
            titulo = ctypes.create_unicode_buffer(300)
            _u32.GetWindowTextW(hwnd, titulo, 300)
            pid = wintypes.DWORD()
            _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            halladas[hwnd] = (clase.value, titulo.value, pid.value)
        return True

    _u32.EnumWindows(_EnumProc(cada), 0)
    return halladas


def ficha(pid):
    """Lo que se pueda saber de ese proceso: nombre, linea de comando y sus padres."""
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            nombre = p.name()
            try:
                linea = " ".join(p.cmdline())
            except (psutil.Error, OSError):
                linea = ""
            cadena, actual = [], p
            for _ in range(6):
                try:
                    actual = actual.parent()
                except psutil.Error:
                    break
                if actual is None:
                    break
                try:
                    extra = " ".join(actual.cmdline())[:90]
                except (psutil.Error, OSError):
                    extra = ""
                cadena.append(f"{actual.name()}[{actual.pid}] {extra}".strip())
        return {"pid": pid, "nombre": nombre, "linea": linea[:260], "padres": cadena}
    except (psutil.Error, OSError):
        return {"pid": pid, "nombre": "(ya habia terminado)", "linea": "", "padres": []}


def hora(t):
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 10)}"


def main():
    # ⚠ La salida va a un archivo o a una consola en cp1252, y ahi un titulo de ventana
    # con un emoji tumba el `print` — y con el la corrida entera, justo cuando aparecio
    # la terminal que se queria ver (paso la primera vez que se uso). Lo raro se reemplaza.
    for canal in (sys.stdout, sys.stderr):
        try:
            canal.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    segundos = 300
    if "--segundos" in sys.argv:
        segundos = int(sys.argv[sys.argv.index("--segundos") + 1])
    yo = psutil.Process().pid
    conocidos = set(psutil.pids())
    vistas = dict(ventanas_de_consola())
    abiertas = {h: time.time() for h in vistas}
    nacidos = []                         # (cuando, ficha) de los ultimos procesos
    eventos = 0
    print(f"Mirando {segundos} s. Terminales visibles al empezar: {len(vistas)}", flush=True)
    for clase, titulo, pid in vistas.values():
        print(f"   ya estaba: {CLASES[clase]} «{titulo}»", flush=True)
    fin = time.time() + segundos
    pendientes = []                      # terminales vistas a las que les falta el "despues"
    while time.time() < fin:
        ahora = time.time()
        actuales = set(psutil.pids())
        for pid in actuales - conocidos:
            if pid != yo:
                nacidos.append((ahora, ficha(pid)))
        conocidos = actuales
        nacidos = [(t, f) for t, f in nacidos if ahora - t < 20]

        ahora_v = ventanas_de_consola()
        for h, (clase, titulo, pid) in ahora_v.items():
            if h not in vistas:
                abiertas[h] = ahora
                pendientes.append((ahora, f"{CLASES[clase]} «{titulo}»"))
        for h in list(abiertas):
            if h not in ahora_v:
                clase, titulo, _ = vistas.get(h, ("", "", 0))
                print(f"{hora(ahora)}  se cerro «{titulo}» "
                      f"(estuvo {ahora - abiertas.pop(h):.1f} s en pantalla)", flush=True)
        vistas = {**vistas, **ahora_v}
        # Una consola que se dibuja adentro de una Terminal YA abierta no trae ventana
        # nueva: se la reconoce por el `OpenConsole.exe` que nace.
        for t, f in nacidos:
            if f["nombre"].lower() == "openconsole.exe" and not f.get("contado"):
                f["contado"] = True
                if not any(abs(t - tp) < 1.5 for tp, _ in pendientes):
                    pendientes.append((t, "una pestaña nueva en la Terminal de Windows"))

        # Se informa medio segundo despues, para alcanzar a ver a los que nacieron junto.
        for tp, que in [p for p in pendientes if ahora - p[0] > 0.6]:
            pendientes.remove((tp, que))
            eventos += 1
            print(f"\n{hora(tp)}  >>> APARECIO UNA TERMINAL: {que}", flush=True)
            # ⚠ Se listan TODOS los que nacieron pegados a la terminal, no solo los de
            # nombre conocido: la primera version filtraba por una lista de programas
            # "de consola" y el culpable de verdad no estaba en la lista. Van ordenados
            # por cercania, y los que nacen DESPUES casi nunca son: son la consecuencia.
            cerca = sorted(((t - tp, f) for t, f in nacidos
                            if -2.5 < t - tp < 0.6 and f["nombre"].lower() not in ANFITRIONES),
                           key=lambda x: abs(x[0]))[:6]
            if not cerca:
                print("   no alcance a ver que programa la trajo (vivio muy poco)", flush=True)
            for dt, f in cerca:
                marca = "*" if f["nombre"].lower() in DE_CONSOLA else " "
                print(f"  {marca}{dt:+.2f} s  {f['nombre']}[{f['pid']}]  {f['linea']}", flush=True)
                for i, papa in enumerate(f["padres"][:3]):
                    print("         " + "   " * i + "└ hijo de " + papa, flush=True)
        time.sleep(0.04)
    print(f"\nListo: {eventos} terminal(es) visibles en {segundos} s.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
