"""Sonda: ¿se puede FILMAR la ventana de un Chrome sin tocar cómo arranca? (2026-11-10)

Martín quiere ver adentro del panel, en vivo, el Chrome que maneja una sesión. Ese Chrome es
un perfil interno de su Chrome personal: no se le puede abrir un puerto de control (Chrome
lo ignora sobre su carpeta de datos de fábrica, y además abriría los perfiles de las dos
agencias de un saque). Lo que queda es copiar los píxeles de la VENTANA, que Windows permite
aunque esté tapada (`PrintWindow` con contenido completo). Antes de construir nada sobre eso
hay que medirlo, porque hay una trampa conocida: Chrome deja de DIBUJAR una ventana que
considera tapada, y ahí la copia saldría bien… congelada en el último cuadro.

Lo que mide, sobre un Chrome DE PRUEBA con carpeta de datos temporal (nunca el de Martín):
  1. a la vista: la copia trae la página (no un rectángulo negro) y CAMBIA cuando la página
     cambia;
  2. tapada por otra ventana: lo mismo;
  3. fuera de la pantalla: lo mismo (es el caso de "que no me tape la pantalla");
  4. minimizada: se espera que NO ande, para saber qué decirle al que la minimice;
  5. cuánto tarda cada cuadro (copiar + achicar + comprimir) y cuánto procesador gasta;
  6. si se la puede traer al frente por programa;
  7. si las ventanas de Chrome llevan una marca que distinga un perfil de otro (el
     identificador de la barra de tareas): de las ventanas que ya haya abiertas se lee SOLO
     esa marca, nunca el título ni el contenido.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_ventana_chrome
    D:/IA/envs/wpp/python.exe -m pruebas.sonda_ventana_chrome --sin-ocultamiento

⚠ Abre una ventana de Chrome de verdad durante unos 40 segundos y la mueve: es una sonda,
se corre a mano. No toca el panel, ni el Chrome de nadie, ni ningún archivo del proyecto.

⭐⭐ LO QUE DIO (2026-11-10, Chrome 157, Windows 11) — de acá sale el diseño de la pieza:
  · A la vista: la copia trae la página y va cambiando.
  · ⚠⚠ TAPADA DEL TODO por una ventana normal, o FUERA de la pantalla: la copia SALE pero
    CONGELADA. Chrome deja de dibujar una ventana que nadie puede ver (lo decide mirando las
    ventanas comunes de arriba; una auxiliar no le cuenta, y por eso la primera versión de
    esta sonda creyó que "tapada" andaba).
  · ⭐ CASI afuera —2 px adentro del borde y siempre encima—: sigue viva. Ese es el modo
    "guardada" de la pieza: una rayita en el borde en vez de una ventana.
  · Con `--sin-ocultamiento` anda TODO, hasta fuera de pantalla. En el Chrome de verdad eso
    sería la política `NativeWindowOcclusionEnabled`, que toca todos sus perfiles y lo marca
    como "administrado": no se pone sin que Martín lo pida.
  · Minimizada: no trae la página.
  · ~40 ms por cuadro (copiar una ventana de 1750x1260, achicar a 900 y comprimir): unos 25
    por segundo como máximo, ~27 ms de procesador cada uno.
  · Traerla: subirla en el orden de ventanas anda sin pedir foco; `SetForegroundWindow` a
    secas se niega (Windows no deja robar el foco desde un programa de fondo) y con el toque
    de la tecla Alt antes, anda.
  · La marca de barra de tareas distingue el perfil: `Chrome.<carpeta de datos>.<perfil>`
    (con espacios vueltos `_`), y `Chrome` a secas para el perfil de fábrica.
  · ⚠ Una ventana abierta por un programa de fondo puede nacer detrás de las demás y tardar
    unos segundos en dibujar su primera página: el caso 1 puede dar mal por eso solo.
"""
import ctypes
import io
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil
import win32con
import win32gui
import win32ui
from PIL import Image

user32 = ctypes.windll.user32
try:                                    # que las medidas de ventana y de copia coincidan
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

CHROME = next((c for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
               if Path(c).exists()), "")
MARCA = "SONDA-VENTANA-" + str(int(time.time()))
# Tres colores bien distintos, uno cada 400 ms: con mirar el color del medio se sabe si la
# copia es de AHORA o es un cuadro viejo.
COLORES = [(200, 40, 40), (40, 160, 60), (40, 70, 200)]
PAGINA = """<!doctype html><html><head><meta charset="utf-8"><title>%s</title>
<style>html,body{margin:0;height:100%%}body{display:grid;place-items:center;
font:700 120px system-ui;color:#fff}</style></head><body><div id="n">0</div><script>
const c = %s; let i = 0;
setInterval(() => { i++; document.body.style.background = 'rgb(' + c[i %% 3].join(',') + ')';
  document.getElementById('n').textContent = i; }, 400);
document.body.style.background = 'rgb(' + c[0].join(',') + ')';
</script></body></html>""" % (MARCA, [list(c) for c in COLORES])
resultados = []


def anotar(nombre, bien, detalle=""):
    print(("ok   " if bien else "MAL  ") + nombre + (": " + str(detalle) if detalle != "" else ""))
    resultados.append((nombre, bool(bien)))


def ventanas_chrome():
    """Todas las ventanas de arriba de todo que son de Chrome y están a la vista."""
    lista = []

    def cada(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "Chrome_WidgetWin_1":
            lista.append(h)
        return True
    win32gui.EnumWindows(cada, None)
    return lista


def buscar(titulo, espera=25):
    fin = time.time() + espera
    while time.time() < fin:
        for h in ventanas_chrome():
            if win32gui.GetWindowText(h).startswith(titulo):
                return h
        time.sleep(0.3)
    return 0


def copiar(h):
    """Los píxeles de la ventana, esté donde esté. Devuelve (anduvo, imagen)."""
    izq, arr, der, aba = win32gui.GetWindowRect(h)
    w, alto = der - izq, aba - arr
    if w <= 0 or alto <= 0:
        return False, None
    dc = win32gui.GetWindowDC(h)
    mfc = win32ui.CreateDCFromHandle(dc)
    mem = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, alto)
    mem.SelectObject(bmp)
    try:
        ok = user32.PrintWindow(h, mem.GetSafeHdc(), 2)       # 2 = contenido completo
        im = Image.frombuffer("RGB", (w, alto), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mem.DeleteDC()
        mfc.DeleteDC()
        win32gui.ReleaseDC(h, dc)
    return bool(ok), im


def color_del_medio(im):
    """Cuál de los tres colores tiene el centro de la página (-1 = ninguno: negra, vieja…)."""
    w, alto = im.size
    r, g, b = im.crop((w // 4, alto // 2, w // 4 + 40, alto // 2 + 40)).resize((1, 1)).getpixel((0, 0))
    for i, (cr, cg, cb) in enumerate(COLORES):
        if abs(r - cr) + abs(g - cg) + abs(b - cb) < 90:
            return i
    return -1


def mirar(h, veces=6):
    """Copia varias veces seguidas: ¿la copia sale?, ¿trae la página?, ¿va CAMBIANDO?"""
    vistos = []
    for _ in range(veces):
        ok, im = copiar(h)
        vistos.append(color_del_medio(im) if ok and im else -2)
        time.sleep(0.45)
    return {"sale": all(v != -2 for v in vistos), "pagina": all(v >= 0 for v in vistos),
            "cambia": len({v for v in vistos if v >= 0}) >= 2, "vistos": vistos}


def marca_de(h):
    """El identificador de barra de tareas de la ventana (lo que Windows usa para agruparlas)."""
    try:
        from win32com.propsys import propsys, pscon
        return str(propsys.SHGetPropertyStoreForWindow(h).GetValue(pscon.PKEY_AppUserModel_ID).GetValue() or "")
    except Exception as e:
        return "(no se pudo leer: " + type(e).__name__ + ")"


def main():
    if not CHROME:
        print("No encuentro chrome.exe")
        return 2
    carpeta = Path(tempfile.mkdtemp(prefix="sonda_ventana_"))
    pagina = carpeta / "pagina.html"
    pagina.write_text(PAGINA, encoding="utf-8")
    datos = carpeta / "datos"
    # Las marcas de las ventanas que YA estaban (solo la marca, ni título ni contenido).
    antes = [marca_de(h) for h in ventanas_chrome()]
    print("ventanas de Chrome ya abiertas:", len(antes), "· marcas distintas:", sorted(set(antes)))
    # `--sin-ocultamiento`: el mismo Chrome con su ahorro de "ventana tapada = no dibujo"
    # apagado. Es para saber si apagárselo (por política, en el Chrome de verdad) arreglaría
    # los casos que fallan. Sin la opción se mide a Chrome tal como viene.
    extra = ["--disable-features=CalculateNativeWinOcclusion",
             "--disable-backgrounding-occluded-windows"] if "--sin-ocultamiento" in sys.argv else []
    print("Chrome", "CON el ahorro apagado" if extra else "tal como viene")
    proc = subprocess.Popen([CHROME, f"--user-data-dir={datos}", "--no-first-run",
                             "--no-default-browser-check", "--disable-sync", "--new-window",
                             "--window-size=1000,720", "--window-position=140,120", *extra,
                             pagina.as_uri()])
    tapa = 0
    try:
        h = buscar(MARCA)
        anotar("la ventana de prueba aparece y se la reconoce por su título", h != 0)
        if not h:
            return 1
        # ⚠ Una ventana abierta por un programa de fondo puede nacer DETRÁS de las demás, y
        # Chrome no dibuja la página de una ventana tapada del todo: la segunda corrida de
        # esta sonda dio gris hasta "a la vista" por eso. Se la sube a mano antes de medir.
        sinfoco = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 0, 0, 0, 0, sinfoco)
        win32gui.SetWindowPos(h, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, sinfoco)
        time.sleep(2.5)
        print("marca de la ventana de prueba:", marca_de(h))
        izq, arr, der, aba = win32gui.GetWindowRect(h)
        w, alto = der - izq, aba - arr

        # 1. A la vista.
        m = mirar(h)
        anotar("1. a la vista: la copia trae la página y va cambiando",
               m["sale"] and m["pagina"] and m["cambia"], m["vistos"])

        # 2. Tapada entera por otra ventana, siempre encima.
        tapa = win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW, "STATIC",
                                       "tapa de la sonda", win32con.WS_POPUP | win32con.WS_VISIBLE,
                                       izq - 10, arr - 10, w + 20, alto + 20, 0, 0, 0, None)
        win32gui.UpdateWindow(tapa)
        time.sleep(2.5)                  # el rato que Chrome tarda en darse por tapado
        m = mirar(h)
        anotar("2. tapada por otra ventana: la copia trae la página", m["sale"] and m["pagina"], m["vistos"])
        anotar("2b. …y sigue CAMBIANDO (Chrome no la congeló)", m["cambia"], m["vistos"])
        win32gui.DestroyWindow(tapa)
        tapa = 0
        time.sleep(0.8)

        # 2c. Lo mismo con una ventana NORMAL (la primera era una auxiliar, y Chrome decide si
        # está tapado mirando las ventanas comunes de arriba: puede que esa no le contara).
        # Es el caso real: su Chrome detrás de la ventana del panel, maximizada.
        tapa = win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST, "STATIC", "tapa normal de la sonda",
                                       win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE,
                                       izq - 40, arr - 60, w + 80, alto + 120, 0, 0, 0, None)
        win32gui.UpdateWindow(tapa)
        time.sleep(7)                    # bastante más que lo que tarda en darse por tapado
        m = mirar(h)
        anotar("2c. tapada por una ventana NORMAL, 7 s después: trae la página",
               m["sale"] and m["pagina"], m["vistos"])
        anotar("2d. …y sigue CAMBIANDO", m["cambia"], m["vistos"])
        win32gui.DestroyWindow(tapa)
        tapa = 0
        time.sleep(0.8)

        # 3. Fuera de la pantalla: más allá del borde izquierdo de todos los monitores.
        x0 = user32.GetSystemMetrics(76)             # SM_XVIRTUALSCREEN
        win32gui.SetWindowPos(h, 0, x0 - w - 400, arr, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        time.sleep(2.5)
        donde = win32gui.GetWindowRect(h)
        m = mirar(h)
        anotar("3. fuera de la pantalla: Windows la deja quedarse ahí", donde[2] <= x0, donde)
        anotar("3b. …la copia trae la página", m["sale"] and m["pagina"], m["vistos"])
        anotar("3c. …y sigue CAMBIANDO", m["cambia"], m["vistos"])

        # 3d. CASI afuera: dos píxeles adentro del borde izquierdo y siempre encima. Si lo que
        # congela a Chrome es no estar en ningún monitor, con dos píxeles a la vista debería
        # seguir dibujando — y dos píxeles en el borde no le tapan la pantalla a nadie.
        win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, x0 - w + 2, arr, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        time.sleep(4)
        m = mirar(h)
        anotar("3d. casi afuera (2 px adentro, siempre encima): trae la página",
               m["sale"] and m["pagina"], m["vistos"])
        anotar("3e. …y sigue CAMBIANDO", m["cambia"], m["vistos"])
        win32gui.SetWindowPos(h, win32con.HWND_NOTOPMOST, x0 - w - 400, arr, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

        # 5. Cuánto cuesta cada cuadro (se mide acá, fuera de pantalla, que es el caso real).
        yo = psutil.Process()
        cpu0, t0, pesos = yo.cpu_times(), time.perf_counter(), []
        for _ in range(30):
            ok, im = copiar(h)
            chico = im.resize((900, int(900 * im.size[1] / im.size[0])), Image.BILINEAR)
            salida = io.BytesIO()
            chico.save(salida, "JPEG", quality=70)
            pesos.append(len(salida.getvalue()))
        dt = time.perf_counter() - t0
        cpu1 = yo.cpu_times()
        gasto = (cpu1.user + cpu1.system) - (cpu0.user + cpu0.system)
        print(f"5. cuadro de {im.size[0]}x{im.size[1]} achicado a 900 de ancho: "
              f"{1000 * dt / 30:.0f} ms cada uno ({30 / dt:.0f} por segundo como máximo), "
              f"{sum(pesos) // 30 // 1024} kB, {1000 * gasto / 30:.0f} ms de procesador por cuadro")
        anotar("5. alcanza para 5 cuadros por segundo con margen", dt / 30 < 0.1, f"{1000 * dt / 30:.0f} ms")

        # 6. Traerla de vuelta y al frente.
        win32gui.SetWindowPos(h, 0, izq, arr, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        time.sleep(0.5)
        try:
            win32gui.SetForegroundWindow(h)
        except Exception as e:
            print("   SetForegroundWindow se negó:", e)
        time.sleep(0.6)
        vuelta = win32gui.GetWindowRect(h)
        anotar("6. vuelve a su lugar", vuelta[:2] == (izq, arr), vuelta)
        anotar("6b. …y queda al frente por programa", win32gui.GetForegroundWindow() == h)
        # 6c. Windows no deja que un programa de fondo le robe el foco a otro. Dos caminos
        # conocidos: subirla en el orden de las ventanas sin pedir el foco (alcanza para
        # VERLA arriba), y el toque de la tecla Alt que destraba el pedido de foco.
        otra = win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST, "STATIC", "otra de la sonda",
                                       win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE,
                                       izq + 60, arr + 60, 500, 300, 0, 0, 0, None)
        win32gui.SetWindowPos(otra, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        time.sleep(0.4)
        sinfoco = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 0, 0, 0, 0, sinfoco)
        win32gui.SetWindowPos(h, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, sinfoco)
        time.sleep(0.4)
        # ¿Quedó por encima de la otra? Se pregunta qué ventana hay en un punto que comparten.
        arriba = win32gui.GetAncestor(win32gui.WindowFromPoint((izq + 200, arr + 200)), 2)
        anotar("6c. subirla en el orden de ventanas, sin pedir foco: queda arriba de las demás",
               arriba == h, hex(arriba))
        user32.keybd_event(0x12, 0, 0, 0)            # Alt abajo
        user32.keybd_event(0x12, 0, 2, 0)            # Alt arriba
        try:
            win32gui.SetForegroundWindow(h)
        except Exception as e:
            print("   con el toque de Alt también se negó:", e)
        time.sleep(0.5)
        anotar("6d. con el toque de la tecla Alt: queda con el foco", win32gui.GetForegroundWindow() == h)
        win32gui.DestroyWindow(otra)

        # 4. Minimizada (al final: es la que se espera que falle).
        win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
        time.sleep(1.5)
        m = mirar(h, veces=3)
        print("4. minimizada:", "la copia sale" if m["sale"] else "la copia NO sale",
              "· trae la página" if m["pagina"] else "· NO trae la página", m["vistos"])
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
    finally:
        if tapa:
            try:
                win32gui.DestroyWindow(tapa)
            except Exception:
                pass
        # Se cierra SOLO el Chrome de la sonda: el que tiene esta carpeta temporal en su línea.
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                if (p.info["name"] or "").lower() == "chrome.exe" and \
                        any(str(datos) in a for a in (p.info["cmdline"] or [])):
                    p.kill()
            except (psutil.Error, OSError):
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        time.sleep(1)
        shutil.rmtree(carpeta, ignore_errors=True)
    mal = [n for n, b in resultados if not b]
    print("\n" + ("TODO BIEN" if not mal else "FALLARON " + str(len(mal)) + ": " + ", ".join(mal)))
    return 1 if mal else 0


if __name__ == "__main__":
    sys.exit(main())
