"""La terminal del panel (`app/voz/terminales.py`), sin abrir el panel y sin gastar tokens.

    D:/IA/envs/wpp/python.exe -m pruebas.probar_terminal
    D:/IA/envs/wpp/python.exe -m pruebas.probar_terminal --mutar

Lo que cuida, en orden de lo que más duele si se rompe:
  1. LOS TRES CANDADOS. Una terminal alcanzable por la red es una puerta a la máquina, y un
     navegador no protege a un WebSocket como protege a los demás pedidos: si la ruta no
     mira de qué página viene, cualquier sitio abierto en Chrome podría tipear en la compu
     de Martín. Se prueba el nombre (`Host`), la página (`Origin`) y la llave, en las rutas
     comunes Y en el WebSocket, que es el que importa.
  2. Que la terminal sea de verdad: un PowerShell en la carpeta pedida, que contesta, que
     se entera del tamaño, y que NO abre ninguna ventana (regla del proyecto).
  3. Que un F5 no pierda lo que había: lo último queda guardado y se manda al reconectar.
  4. El tope, el cierre, y que lo que se cerró solo no ocupe lugar.

Arma un servidor chico con las mismas rutas (no importa `panel.py`). Con `--mutar` rompe
cada candado a propósito y exige que algún chequeo lo cace.
"""
import ctypes
import importlib
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import psutil
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

VERDES, ROJOS = [], []
PROPIO = "http://127.0.0.1:8750"          # como llega un pedido de la página del panel
AJENO = "http://sitio-cualquiera.example"


def ok(bien, nombre, detalle=""):
    (VERDES if bien else ROJOS).append(nombre)
    print(("  ok    " if bien else "  FALLA ") + nombre + (f"  ({detalle})" if detalle and not bien else ""))


def consolas_a_la_vista():
    """Las ventanas de consola VISIBLES ahora mismo (la clásica y la Terminal de Windows)."""
    vistas, u32 = set(), ctypes.windll.user32
    tipo = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cada(h, _):
        if u32.IsWindowVisible(h):
            clase = ctypes.create_unicode_buffer(80)
            u32.GetClassNameW(h, clase, 80)
            if clase.value in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"):
                vistas.add(h)
        return True
    u32.EnumWindows(tipo(cada), 0)
    return vistas


class Escucha:
    """Un WebSocket de la prueba, con un hilo que va juntando lo que llega: `receive_text`
    a secas se queda esperando para siempre si la terminal no contesta."""

    def __init__(self, cliente, ident, llave, origen=PROPIO):
        cabeceras = {"origin": origen} if origen else {}
        # ⚠ Con la dirección ENTERA: el cliente de pruebas, si no, se presenta como
        # "testserver" y el candado del nombre lo frena (que es lo que tiene que hacer).
        self._cm = cliente.websocket_connect(
            PROPIO.replace("http", "ws") + f"/terminal/ws?id={ident}&llave={llave}", headers=cabeceras)
        self.ws = self._cm.__enter__()
        self.todo, self.cerrado, self.cuadros = "", False, []
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        try:
            while True:
                dato = self.ws.receive_text()
                self.cuadros.append(dato)
                self.todo += dato
        except Exception:
            self.cerrado = True

    def tipear(self, texto):
        self.ws.send_json({"t": "i", "d": texto})

    def medir(self, filas, cols):
        self.ws.send_json({"t": "m", "f": filas, "c": cols})

    def esperar(self, texto, segundos=30):
        fin = time.time() + segundos
        while time.time() < fin:
            if texto in self.todo:
                return True
            time.sleep(0.1)
        return False

    def soltar(self):
        try:
            self._cm.__exit__(None, None, None)
        except Exception:
            pass


def entra_al_ws(cliente, ident, llave, origen):
    """¿El WebSocket lo deja pasar? (True = aceptado)"""
    try:
        e = Escucha(cliente, ident, llave, origen)
        e.soltar()
        return True
    except WebSocketDisconnect:
        return False
    except Exception:
        return False


def correr_todo(mod):
    carpeta = Path(tempfile.mkdtemp(prefix="probar_terminal_"))
    mod.LOGS = carpeta                         # que no escriba en el registro de verdad
    app = FastAPI()
    app.include_router(mod.crear_router())
    cliente = TestClient(app, base_url=PROPIO)
    try:
        # --- 1. Los candados, en las rutas comunes ---------------------------------------
        print("=== Los candados ===")
        r = cliente.get("/terminal/llave")
        llave = r.json().get("llave", "") if r.status_code == 200 else ""
        ok(r.status_code == 200 and len(llave) > 20, "la página del panel recibe la llave")
        ok(cliente.get("/terminal/llave", headers={"origin": PROPIO}).status_code == 200,
           "también si dice que viene de la propia página")
        ok(cliente.get("/terminal/llave", headers={"origin": AJENO}).status_code == 403,
           "otra página NO recibe la llave")
        ok(cliente.get("/terminal/llave", headers={"host": "sitio-cualquiera.example:8750"}).status_code == 403,
           "un nombre de afuera que apunta a esta máquina NO recibe la llave")
        ok(cliente.get("/terminal/llave", headers={"host": "127.0.0.1.sitio-cualquiera.example"}).status_code == 403,
           "ni uno que EMPIEZA como una dirección de esta máquina")
        ok(cliente.get("/terminal/llave", headers={"host": "mi-compu.tail1234.ts.net",
                                                    "origin": "https://mi-compu.tail1234.ts.net"}).status_code == 200,
           "por Tailscale (su nombre .ts.net) sí")
        ok(cliente.get("/terminal/lista").status_code == 403, "sin llave no se puede ni listar")
        ok(cliente.post("/terminal/abrir", json={"cwd": str(carpeta)}).status_code == 403,
           "sin llave no se puede abrir una terminal")
        ok(cliente.post("/terminal/abrir", json={"cwd": str(carpeta)},
                        headers={"x-terminal-llave": "inventada"}).status_code == 403,
           "con una llave inventada tampoco")
        con = {"x-terminal-llave": llave}
        ok(cliente.get("/terminal/lista", headers=con).status_code == 200, "con la llave, sí")
        ok(cliente.post("/terminal/abrir", json={"cwd": str(carpeta)},
                        headers=dict(con, origin=AJENO)).status_code == 403,
           "con la llave pero desde otra página, no")

        # --- 1 bis. El primer mensaje es SIEMPRE el repaso, aunque esté vacío -------------
        # La página dibuja el primer mensaje sin contestar las preguntas que trae adentro
        # (son viejas). Si el servidor se lo salteara cuando no hay nada guardado, la página
        # tomaría por "repaso" la primera salida de verdad y dejaría sin contestar al
        # PowerShell que está arrancando. Se prueba con una terminal de mentira, para que
        # no dependa de cuánto tarda una de verdad en escribir.
        class DeMentira:
            id, cwd, viva, creada = "mentira", str(carpeta), True, 0

            def escuchar(self, bucle):
                self.bucle, self.cola = bucle, __import__("asyncio").Queue()
                return "", self.cola

            def dejar(self, bucle, cola): pass
            def escribir(self, texto): pass
            def medir(self, filas, cols): pass
            def cerrar(self): self.viva = False
            def ficha(self): return {"id": self.id, "cwd": self.cwd, "viva": True, "creada": 0}
        falsa = DeMentira()
        mod._TERMINALES[falsa.id] = falsa
        em = Escucha(cliente, falsa.id, llave)
        time.sleep(0.4)
        falsa.bucle.call_soon_threadsafe(falsa.cola.put_nowait, "salida-de-verdad")
        fin = time.time() + 5
        while time.time() < fin and len(em.cuadros) < 2:
            time.sleep(0.05)
        ok(em.cuadros[:2] == ["", "salida-de-verdad"],
           "⭐ el primer mensaje es el repaso aunque esté vacío, y la salida de verdad va después",
           em.cuadros[:3])
        em.soltar()
        mod._TERMINALES.pop(falsa.id, None)

        if not mod.disponible():
            ok(False, "pywinpty está instalado en el entorno (sin él no hay terminal que probar)")
            return

        # --- 2. Una terminal de verdad --------------------------------------------------
        print("=== La terminal ===")
        antes = consolas_a_la_vista()
        r = cliente.post("/terminal/abrir", json={"cwd": str(carpeta), "filas": 24, "cols": 100},
                         headers=con).json()
        ident = r.get("id", "")
        ok(r.get("ok") and ident and Path(r.get("cwd", "")) == carpeta, "abre una terminal en la carpeta pedida", r)
        ok(any(t["id"] == ident for t in cliente.get("/terminal/lista", headers=con).json()["terminales"]),
           "y figura en la lista")

        # ⭐⭐ El WebSocket: el candado que importa.
        ok(not entra_al_ws(cliente, ident, "", PROPIO), "el WebSocket SIN llave no entra")
        ok(not entra_al_ws(cliente, ident, "inventada", PROPIO), "con una llave inventada tampoco")
        ok(not entra_al_ws(cliente, ident, llave, AJENO),
           "⭐ con la llave pero desde OTRA página no entra (lo que el navegador no frena solo)")
        ok(not entra_al_ws(cliente, "no-existe", llave, PROPIO), "a una terminal que no existe no entra")

        e = Escucha(cliente, ident, llave)
        # El comando ARMA la marca: así aparece solo en la respuesta, no en lo tipeado.
        e.tipear('echo ("ho"+"la-"+(100+23))\r')
        ok(e.esperar("hola-123"), "⭐ es un PowerShell de verdad: tipeás un comando y contesta", e.todo[-300:])
        e.tipear("(Get-Location).Path\r")
        ok(e.esperar(carpeta.name), "está parado en la carpeta pedida", e.todo[-300:])
        e.medir(30, 123)
        time.sleep(0.4)
        e.tipear('echo ("ancho="+[Console]::WindowWidth)\r')
        ok(e.esperar("ancho=123"), "se entera del tamaño de la pieza", e.todo[-300:])
        ok(consolas_a_la_vista() <= antes, "⭐ no abrió NINGUNA ventana de consola",
           f"nuevas: {len(consolas_a_la_vista() - antes)}")
        e.soltar()

        # --- 3. Un F5 no pierde lo que había -------------------------------------------
        print("=== La memoria ===")
        e2 = Escucha(cliente, ident, llave)
        ok(e2.esperar("hola-123", 6) and e2.esperar("ancho=123", 3),
           "⭐ al reconectar llega lo que ya se había escrito", e2.todo[-200:])
        e2.tipear('echo ("sigue-"+(7*6))\r')
        ok(e2.esperar("sigue-42"), "y sigue andando la misma terminal")
        sin_origen = entra_al_ws(cliente, ident, llave, "")
        ok(sin_origen, "un programa que no es un navegador entra con la llave (no manda de qué página viene)")

        # --- 4. Cerrar, el tope, y lo que se cierra solo ---------------------------------
        print("=== El cierre y el tope ===")
        t = mod.de(ident)
        pid = getattr(t._proc, "pid", 0)
        ok(cliente.post("/terminal/cerrar", json={"id": ident}, headers=con).json().get("ok"),
           "se puede cerrar")
        fin = time.time() + 8
        while time.time() < fin and (not e2.cerrado or (pid and psutil.pid_exists(pid))):
            time.sleep(0.2)
        ok(e2.cerrado, "la página que la miraba se entera de que se cerró")
        ok(not (pid and psutil.pid_exists(pid)), "y su PowerShell no queda corriendo", f"pid {pid}")
        e2.soltar()
        ok(not any(x["id"] == ident for x in cliente.get("/terminal/lista", headers=con).json()["terminales"]),
           "ya no figura en la lista")

        tope = mod.MAX_TERMINALES
        mod.MAX_TERMINALES = 2
        try:
            a = cliente.post("/terminal/abrir", json={"cwd": str(carpeta)}, headers=con).json()
            b = cliente.post("/terminal/abrir", json={"cwd": str(carpeta)}, headers=con).json()
            c = cliente.post("/terminal/abrir", json={"cwd": str(carpeta)}, headers=con).json()
            ok(a.get("ok") and b.get("ok") and not c.get("ok") and "cerr" in c.get("error", ""),
               "con el tope alcanzado no abre otra y dice por qué", c)
            # Una que se cierra sola (un `exit`) deja su lugar.
            es = Escucha(cliente, a["id"], llave)
            es.tipear("exit\r")
            fin = time.time() + 15
            while time.time() < fin and mod.de(a["id"]).viva:
                time.sleep(0.2)
            ok(not mod.de(a["id"]).viva, "con `exit` la terminal se da por cerrada sola")
            es.soltar()
            d = cliente.post("/terminal/abrir", json={"cwd": str(carpeta)}, headers=con).json()
            ok(d.get("ok"), "y la que se cerró sola deja su lugar a una nueva", d)
        finally:
            mod.MAX_TERMINALES = tope
        cuenta = (carpeta / "correr.log").read_text(encoding="utf-8") if (carpeta / "correr.log").exists() else ""
        ok("abierta en" in cuenta, "cada terminal abierta queda anotada en el registro")

        # --- 5. Segunda vuelta: el programa, las marcas de cada comando y el Ctrl+K ----------
        print("=== Programas, marcas y Ctrl+K ===")
        mod.cerrar_todas()
        llave_r = cliente.get("/terminal/llave").json()
        ids = [x["id"] for x in llave_r.get("shells", [])]
        ok("pwsh" in ids and "cmd" in ids, "la llave trae la lista de programas que se pueden abrir", ids)
        r = cliente.post("/terminal/abrir", json={"cwd": str(carpeta), "shell": "cmd"}, headers=con).json()
        ok(r.get("ok") and r.get("shell") == "cmd", "⭐ se puede abrir una con CMD", r)
        e = Escucha(cliente, r["id"], llave)
        e.tipear("echo %COMSPEC%\r")
        ok(e.esperar("cmd.exe"), "y es CMD de verdad", e.todo[-200:])
        e.soltar()
        r = cliente.post("/terminal/abrir", json={"cwd": str(carpeta), "shell": "notepad & calc"},
                         headers=con).json()
        ok(r.get("ok") and r.get("shell") == "pwsh",
           "⭐ un programa que no está en la lista NO se corre: abre PowerShell", r)
        e = Escucha(cliente, r["id"], llave)
        ok(e.esperar("\x1b]633;B\x07", 30), "⭐ PowerShell avisa dónde empieza lo que tipeás (marca B)")
        e.tipear("cmd /c exit 3\r")
        ok(e.esperar("\x1b]633;D;3\x07"), "⭐ y cuando un comando falla avisa con su código (marca D;3)",
           repr(e.todo[-160:]))
        e.tipear('echo ("o"+"k")\r')
        ok(e.esperar("\x1b]633;D;0\x07"), "y cuando anda, con 0")
        e.soltar()

        # El Ctrl+K: se reemplaza la consulta a Claude por una de mentira (gratis, al toque).
        pedidos = []
        mod.sugerir = lambda pedido, shell, cwd, pantalla: (pedidos.append((pedido, shell, cwd)) or ("dir /s", ""))
        ok(cliente.post("/terminal/sugerir", json={"pedido": "x"}).status_code == 403,
           "⭐ el Ctrl+K sin llave no entra (gasta plata: también va con candado)")
        ok(cliente.post("/terminal/sugerir", json={"pedido": "x"},
                        headers=dict(con, origin=AJENO)).status_code == 403, "ni desde otra página")
        r = cliente.post("/terminal/sugerir", json={"pedido": "listar todo", "shell": "cmd", "cwd": "C:/x"},
                         headers=con).json()
        ok(r.get("comando") == "dir /s" and pedidos and pedidos[-1] == ("listar todo", "cmd", "C:/x"),
           "con la llave devuelve el comando, y le pasa el pedido, el programa y la carpeta", r)
        ok("Ctrl+K" in (carpeta / "correr.log").read_text(encoding="utf-8"),
           "lo pedido queda anotado en el registro")
    finally:
        mod.cerrar_todas()
        time.sleep(0.6)
        shutil.rmtree(carpeta, ignore_errors=True)


# Cada una rompe UNA cosa. Si con eso roto todo sigue verde, ese chequeo era un adorno.
MUTACIONES = {
    "no mira con qué nombre llegaron (Host)":
        ("    if not _anfitrion_propio(anfitrion, anfitriones_extra):", "    if False:"),
    "no mira de qué página viene (Origin)":
        ("    if origen and origen not in origenes_extra:", "    if False:"),
    "no pide la llave":
        ("    if pide_llave and not (llave and", "    if False and not (llave and"),
    "el WebSocket no pasa por la puerta":
        ('        motivo = _puerta(ws.headers, ws.query_params.get("llave", ""),\n'
         "                         origenes_extra, anfitriones_extra)", '        motivo = ""'),
    "no guarda lo último que se escribió":
        ("                self._memoria.append(dato)", "                pass"),
    "se saltea el repaso cuando no hay nada guardado":
        ("            await ws.send_text(previo)",
         "            if previo:\n                await ws.send_text(previo)"),
    "abre cualquier programa que mande la página":
        ('        t = Terminal(carpeta, _medida(filas, 4, 300, 24), _medida(cols, 20, 500, 100),\n'
         '                     shell if shell in SHELLS else "pwsh")',
         '        SHELLS.setdefault(shell, {"nombre": shell, "exe": "cmd", "ps": False})\n'
         '        t = Terminal(carpeta, _medida(filas, 4, 300, 24), _medida(cols, 20, 500, 100), shell)'),
    "PowerShell sin las marcas de cada comando":
        ('        linea += ["-NoLogo", "-NoExit", "-EncodedCommand", cod]', '        linea += ["-NoLogo"]'),
    "el Ctrl+K sin candado":
        ('    async def terminal_sugerir(request: Request):\n'
         '        """El Ctrl+K: lo que querés hacer, en tus palabras → el comando, para ESCRIBIRLO."""\n'
         '        motivo = puerta(request)',
         '    async def terminal_sugerir(request: Request):\n'
         '        motivo = ""'),
    "no hay tope de terminales":
        ("        if len(_TERMINALES) >= MAX_TERMINALES:", "        if False:"),
}


def mutar():
    original = importlib.import_module("app.voz.terminales")
    fuente = Path(original.__file__).read_text(encoding="utf-8")
    caidas = 0
    for nombre, (viejo, nuevo) in MUTACIONES.items():
        if fuente.count(viejo) != 1:
            print(f"  FALLA la mutación '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        mod = types.ModuleType("terminales_mutado")
        mod.__file__ = original.__file__
        exec(compile(fuente.replace(viejo, nuevo), original.__file__, "exec"), vars(mod))
        antes, verdes = len(ROJOS), len(VERDES)
        salida = sys.stdout
        sys.stdout = open("nul", "w", encoding="utf-8")
        try:
            correr_todo(mod)
        except Exception:
            ROJOS.append("excepción")
        finally:
            sys.stdout.close()
            sys.stdout = salida
        cayo = len(ROJOS) > antes
        del ROJOS[antes:]
        del VERDES[verdes:]
        caidas += cayo
        print(("  ok    " if cayo else "  FALLA ") + "mutación cazada: " + nombre)
        if not cayo:
            ROJOS.append("mutación no cazada: " + nombre)
    return caidas


def main():
    correr_todo(importlib.import_module("app.voz.terminales"))
    if "--mutar" in sys.argv and not ROJOS:
        print("\n=== Las mutaciones: cada candado tiene que poder fallar ===")
        n = mutar()
        print(f"\n{n} de {len(MUTACIONES)} mutaciones cazadas")
    print(f"\n{len(VERDES)} bien, {len(ROJOS)} mal")
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
