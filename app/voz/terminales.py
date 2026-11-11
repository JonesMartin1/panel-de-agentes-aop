"""Terminales de verdad adentro del panel (2026-11-10).

Martin: *"hay cosas de Claude Code que podriamos agregar a este panel, como la terminal o
el navegador dentro del mismo panel"*. De la entrevista de ese dia salio que la quiere
COMPLETA (se tipea, con colores, programas que preguntan, cosas que quedan corriendo), no
una caja de comandos. Esto es el lado del servidor; la pagina es `estaticos/terminal.js`.

Como esta armado:
  · cada terminal es un PowerShell colgado de una pseudo-consola de Windows (`pywinpty`):
    el programa cree que tiene una terminal de verdad, pero NO hay ninguna ventana — la
    regla "nada del panel deja una terminal a la vista" se cumple sola;
  · un hilo lee lo que escribe y lo reparte a las paginas que la miran; lo ultimo queda
    guardado (`MEMORIA`) para que un F5, o cambiar de pestaña, no pierda lo que habia;
  · la pagina habla por un WebSocket: teclas para un lado, salida para el otro.

⭐ Todo viaja en un `APIRouter` y `panel.py` solo lo enchufa (`app.include_router`): son
dos renglones alla, que es lo que se puede pedir en un archivo que tocan varias sesiones.

⚠⚠ SEGURIDAD — lo que NO se toca sin entenderlo. Un navegador protege a un pedido comun
de que lo haga otra pagina (no le deja leer la respuesta, y a un POST con JSON ni lo deja
salir). **A un WebSocket no lo protege nada**: cualquier sitio abierto en el Chrome de
Martin podria conectarse a `ws://127.0.0.1:8750/terminal/ws` y tipear en su maquina. Por
eso son TRES candados y hacen falta los tres (`_puerta`):
  1. el nombre con el que llegaron (`Host`) tiene que ser de esta maquina o de su Tailscale:
     sin eso, un dominio de afuera que se haga pasar por 127.0.0.1 entra como "el mismo sitio";
  2. si el pedido dice de que pagina viene (`Origin`), tiene que ser la del panel;
  3. la llave (`LLAVE`): nace con el proceso, se pide por `GET /terminal/llave` y otra
     pagina no la puede leer.
No agrega un poder nuevo —desde el panel ya se le habla a una sesion que corre comandos—,
pero una terminal sin estos candados seria el camino mas corto para cualquiera.

Limites que Martin conoce y acepto: lo que corra aca **se corta cuando el panel se
reinicia** (las terminales viven adentro de su proceso).
"""
import asyncio
import atexit
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from app.rutas import ESTATICOS, LOGS, RAIZ

MAX_TERMINALES = 8          # abiertas a la vez; cada una es un PowerShell con su memoria
MEMORIA = 300_000           # letras de salida que se guardan por terminal
LLAVE = secrets.token_urlsafe(32)
TERCEROS = ESTATICOS / "terceros"

_TERMINALES = {}
_CANDADO = threading.Lock()


def disponible():
    """¿Esta instalada la pieza que da la pseudo-consola? Sin ella la pagina avisa en vez
    de romperse (el modulo se importa igual: el panel no puede dejar de arrancar por esto)."""
    try:
        import winpty  # noqa: F401
        return True
    except Exception:
        return False


# ⭐ La INTEGRACION (2026-11-10, segunda vuelta): unas marcas invisibles que el PowerShell
# escribe en cada renglon de entrada, las mismas que usan VS Code y Cursor (`ESC ] 633`):
#   A = empieza el renglon de entrada · B = empieza lo que tipeas · D;<codigo> = el comando
#   anterior termino, con ese codigo de salida (0 = bien).
# Con eso la pagina sabe donde empieza y termina cada comando y si fallo: pinta un puntito
# verde o rojo al costado, deja saltar de comando en comando, y ofrece "arreglalo con la
# sesion" cuando uno falla. No cambia nada de lo que se ve: las marcas no se dibujan.
# ⚠ Se envuelve el `prompt` que ya hubiera (el de conda, el de oh-my-posh…), no se lo pisa.
# ⚠ `$?` se lee PRIMERO: cualquier cosa que corra antes en el prompt lo pisa.
_INTEGRACION_PS = r"""
$global:__panelPromptViejo = $function:prompt
function global:prompt {
  $ok = $?; $c = if ($ok) { 0 } elseif ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
  $e = [char]27; $b = [char]7
  $txt = if ($global:__panelPromptViejo) { & $global:__panelPromptViejo } else { "PS $($PWD.Path)> " }
  "$e]633;D;$c$b$e]633;A$b" + $txt + "$e]633;B$b"
}
"""

# Los programas que se pueden abrir. Solo estos: lo que venga de la pagina es una CLAVE de
# esta lista, nunca una linea de comando.
SHELLS = {
    "pwsh": {"nombre": "PowerShell 7", "exe": "pwsh", "ps": True},
    "powershell": {"nombre": "Windows PowerShell", "exe": "powershell", "ps": True},
    "cmd": {"nombre": "Símbolo del sistema", "exe": "cmd", "ps": False},
    "bash": {"nombre": "Git Bash", "exe": r"C:\Program Files\Git\bin\bash.exe", "ps": False,
             "args": ["--login", "-i"]},
}


def _exe(clave):
    s = SHELLS.get(clave) or {}
    exe = s.get("exe", "")
    if not exe:
        return ""
    if Path(exe).is_absolute():
        return exe if Path(exe).exists() else ""
    return shutil.which(exe) or ""


def shells_disponibles():
    return [{"id": k, "nombre": v["nombre"]} for k, v in SHELLS.items() if _exe(k)]


def _shell(clave="pwsh"):
    """La linea de comando del programa pedido. PowerShell 7 si no se pide nada (pega bien
    varios renglones y habla UTF-8); si no esta, el de Windows."""
    if not _exe(clave):
        clave = "pwsh" if _exe("pwsh") else "powershell"
    s = SHELLS[clave]
    linea = [_exe(clave) or s["exe"]]
    if s["ps"]:
        # La integracion viaja como `-EncodedCommand` (base64 de UTF-16LE): asi no hay nada
        # que escapar, igual que en `/correr`. `-NoExit` deja la terminal abierta despues.
        cod = base64.b64encode(_INTEGRACION_PS.encode("utf-16-le")).decode("ascii")
        linea += ["-NoLogo", "-NoExit", "-EncodedCommand", cod]
    linea += s.get("args", [])
    return linea, clave


def _anotar(texto):
    """Al mismo registro que el boton de correr de siempre, para poder mirar que se ejecuto."""
    try:
        with open(LOGS / "correr.log", "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")
    except Exception:
        pass                                  # el registro no puede voltear una terminal


def _medida(n, piso, techo, fabrica):
    try:
        return max(piso, min(techo, int(n)))
    except (TypeError, ValueError):
        return fabrica


class Terminal:
    def __init__(self, cwd, filas, cols, shell="pwsh"):
        from winpty import PtyProcess
        self.id = secrets.token_hex(6)
        self.cwd = cwd
        self.creada = time.time()
        self.viva = True
        self._memoria = deque()
        self._largo = 0
        self._oyentes = set()                 # (bucle, cola) de cada pagina que la mira
        self._candado = threading.Lock()
        linea, self.shell = _shell(shell)
        self._proc = PtyProcess.spawn(linea, cwd=cwd, dimensions=(filas, cols),
                                      env=dict(os.environ))
        threading.Thread(target=self._leer, daemon=True, name=f"terminal-{self.id}").start()

    def _repartir(self, dato):
        with self._candado:
            if dato:
                self._memoria.append(dato)
                self._largo += len(dato)
                while self._largo > MEMORIA and len(self._memoria) > 1:
                    self._largo -= len(self._memoria.popleft())
            oyentes = list(self._oyentes)
        for bucle, cola in oyentes:
            try:
                bucle.call_soon_threadsafe(cola.put_nowait, dato)
            except RuntimeError:              # esa pagina ya se fue y su bucle cerro
                pass

    def _leer(self):
        while True:
            try:
                dato = self._proc.read(4096)
            except Exception:                 # EOFError al cerrarse, o la consola murio
                break
            if dato:
                self._repartir(dato)
            elif not self._proc.isalive():
                break
        self.viva = False
        self._repartir(None)                  # None = se termino: la pagina lo dice

    def escuchar(self, bucle):
        """Lo que habia hasta ahora y una cola con lo que venga. ⚠ Las dos cosas bajo el
        mismo candado: si no, un renglon que sale justo en el medio se pierde o va dos veces."""
        cola = asyncio.Queue()
        with self._candado:
            previo = "".join(self._memoria)
            self._oyentes.add((bucle, cola))
        return previo, cola

    def dejar(self, bucle, cola):
        with self._candado:
            self._oyentes.discard((bucle, cola))

    def escribir(self, texto):
        if self.viva and texto:
            try:
                self._proc.write(texto)
            except Exception:
                pass

    def medir(self, filas, cols):
        if self.viva:
            try:
                self._proc.setwinsize(_medida(filas, 4, 300, 24), _medida(cols, 20, 500, 80))
            except Exception:
                pass

    def cerrar(self):
        self.viva = False
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass

    def ficha(self):
        return {"id": self.id, "cwd": self.cwd, "viva": self.viva, "creada": self.creada,
                "shell": self.shell, "nombre_shell": SHELLS[self.shell]["nombre"]}


def abrir(cwd, filas=24, cols=100, shell="pwsh"):
    """Abre una terminal en esa carpeta (si no existe, en la raiz, igual que `/correr`)."""
    try:
        carpeta = cwd if cwd and Path(cwd).is_dir() else str(RAIZ)
    except OSError:
        carpeta = str(RAIZ)
    with _CANDADO:
        for k in [k for k, t in _TERMINALES.items() if not t.viva]:
            del _TERMINALES[k]                # las que se cerraron solas (un `exit`) no cuentan
        if len(_TERMINALES) >= MAX_TERMINALES:
            return None, f"ya hay {MAX_TERMINALES} terminales abiertas: cerra alguna"
        t = Terminal(carpeta, _medida(filas, 4, 300, 24), _medida(cols, 20, 500, 100),
                     shell if shell in SHELLS else "pwsh")
        _TERMINALES[t.id] = t
    _anotar(f"terminal {t.id} ({t.shell}) abierta en {carpeta}")
    return t, ""


def lista():
    with _CANDADO:
        return [t.ficha() for t in _TERMINALES.values()]


def de(ident):
    with _CANDADO:
        return _TERMINALES.get(ident)


def cerrar(ident):
    with _CANDADO:
        t = _TERMINALES.pop(ident, None)
    if t:
        t.cerrar()
    return bool(t)


def cerrar_todas():
    with _CANDADO:
        todas = list(_TERMINALES.values())
        _TERMINALES.clear()
    for t in todas:
        t.cerrar()


atexit.register(cerrar_todas)     # el panel se va: no quedan PowerShell huerfanos


# --- El Ctrl+K de Cursor: describís lo que querés y te escribe el comando ------------------
# ⭐ Una consulta CORTA a Claude: Haiku, sin herramientas, sin conectores, sin la
# configuracion ni el CLAUDE.md de ningun proyecto, y sin guardar la charla. Medido el
# 2026-11-10: ~8 s (casi todo es arrancar el programa) y 0,0002 dolares por pedido.
# ⚠ Devuelve un TEXTO. La pagina lo ESCRIBE en el renglon y no lo ejecuta: el Enter es de
# Martin, igual que con el ▶ de los bloques de codigo.
_SISTEMA_SUGERIR = ("Sos un generador de comandos de terminal para Windows. Te dicen que "
                    "programa de terminal se usa, en que carpeta, que se ve en pantalla y que "
                    "quiere hacer la persona. Devolve SOLO el comando, en UNA linea (si hacen "
                    "falta varios pasos, encadenalos con el separador de ese programa), sin "
                    "explicacion, sin comillas de codigo y sin el prompt. Si el pedido no se "
                    "puede hacer con un comando, devolve una linea que empiece con # y diga "
                    "por que, en castellano rioplatense.")


def sugerir(pedido, shell="pwsh", cwd="", pantalla=""):
    """(comando, error). Corre en un hilo: el programa tarda unos segundos en arrancar."""
    pedido = (pedido or "").strip()[:1500]
    if not pedido:
        return "", "no hay pedido"
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude:
        return "", "no encuentro el programa de Claude"
    nombre = (SHELLS.get(shell) or SHELLS["pwsh"])["nombre"]
    entrada = (f"Programa de terminal: {nombre}\nCarpeta: {cwd}\n"
               f"Lo que se ve en la terminal (lo ultimo):\n{(pantalla or '')[-3000:]}\n\n"
               f"Lo que quiere hacer: {pedido}")
    # ⚠ Una carpeta vacia: si corriera en la del proyecto leeria su CLAUDE.md y su memoria,
    # que son miles de letras que no hacen falta para escribir un comando.
    with tempfile.TemporaryDirectory(prefix="terminal_sugerir_") as vacia:
        try:
            r = subprocess.run(
                [claude, "-p", "--model", "haiku", "--tools", "", "--no-session-persistence",
                 "--strict-mcp-config", "--setting-sources", "", "--output-format", "json",
                 "--system-prompt", _SISTEMA_SUGERIR],
                input=entrada, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=90, cwd=vacia,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return "", "Claude tardó demasiado en contestar"
        except Exception as e:
            return "", f"no pude preguntarle a Claude: {e}"
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        return "", "Claude contestó algo que no entiendo"
    if d.get("is_error"):
        return "", str(d.get("result") or "Claude no pudo contestar")[:300]
    texto = str(d.get("result") or "").strip().strip("`").strip()
    if texto.lower().startswith(("powershell\n", "bash\n", "cmd\n", "ps\n")):
        texto = texto.split("\n", 1)[1].strip()
    # Un renglon: si contesto varios, se queda con el primero que no sea un comentario vacio.
    renglones = [x.rstrip() for x in texto.splitlines() if x.strip()]
    return (renglones[0] if renglones else ""), ("" if renglones else "Claude no devolvió ningún comando")


# --- Los tres candados ----------------------------------------------------------------------

def _nombre(anfitrion):
    """El nombre de un `Host` u `Origin`, sin el puerto y en minuscula (`[::1]:8750` incluido)."""
    a = (anfitrion or "").strip().lower()
    if a.startswith("["):
        return a.split("]", 1)[0] + "]"
    return a.rsplit(":", 1)[0] if ":" in a else a


def _anfitrion_propio(anfitrion, extra=()):
    """¿Ese nombre es de esta maquina? `localhost`, sus direcciones, su nombre y su Tailscale."""
    n = _nombre(anfitrion)
    return bool(n) and (n in ("localhost", "127.0.0.1", "[::1]") or n.endswith(".ts.net")
                        or n == socket.gethostname().lower() or n in extra)


def _puerta(cabeceras, llave, origenes_extra=(), anfitriones_extra=(), pide_llave=True):
    """¿Pasa este pedido? Devuelve "" si pasa, o el motivo por el que no.

    Los tres candados del encabezado, en una sola funcion para que no haya una ruta que se
    olvide de alguno. `Origin` puede faltar (un pedido comun del mismo sitio no lo manda, y
    un programa que no es un navegador tampoco): ahi deciden el nombre y la llave.
    """
    anfitrion = cabeceras.get("host", "")
    if not _anfitrion_propio(anfitrion, anfitriones_extra):
        return "ese nombre no es de esta maquina"
    origen = cabeceras.get("origin", "")
    if origen and origen not in origenes_extra:
        if urlsplit(origen).netloc.lower() != anfitrion.strip().lower():
            return "el pedido viene de otra pagina"
    if pide_llave and not (llave and secrets.compare_digest(str(llave), LLAVE)):
        return "falta la llave"
    return ""


# --- Las rutas -------------------------------------------------------------------------------

def crear_router(origenes_extra=(), anfitriones_extra=()):
    """Las rutas de la terminal. Los `extra` son para las pruebas, que la sirven desde un
    servidor chico aparte: el panel lo crea sin nada (`router`, al final)."""
    r = APIRouter()

    def puerta(pedido, pide_llave=True):
        return _puerta(pedido.headers, pedido.headers.get("x-terminal-llave", ""),
                       origenes_extra, anfitriones_extra, pide_llave)

    def no(motivo):
        return JSONResponse({"ok": False, "error": motivo}, status_code=403)

    @r.get("/terminal/llave")
    def terminal_llave(request: Request):
        """La llave, para la pagina del panel. Otra pagina no puede leer esta respuesta (el
        navegador no se la entrega), y si lo intenta de frente el `Origin` la delata."""
        motivo = puerta(request, pide_llave=False)
        if motivo:
            return no(motivo)
        return JSONResponse({"ok": True, "llave": LLAVE, "disponible": disponible(),
                             "tope": MAX_TERMINALES, "shells": shells_disponibles(),
                             "sugerir": True}, headers={"Cache-Control": "no-store"})

    @r.get("/terminal/lista")
    def terminal_lista(request: Request):
        motivo = puerta(request)
        return no(motivo) if motivo else {"ok": True, "terminales": lista()}

    @r.post("/terminal/abrir")
    async def terminal_abrir(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        if not disponible():
            return {"ok": False, "error": "falta instalar pywinpty en el entorno del panel"}
        d = await request.json()
        try:
            t, error = abrir((d.get("cwd") or "").strip(), d.get("filas"), d.get("cols"),
                             str(d.get("shell") or "pwsh"))
        except Exception as e:
            return {"ok": False, "error": f"no pude abrirla: {e}"}
        return {"ok": True, **t.ficha()} if t else {"ok": False, "error": error}

    @r.post("/terminal/cerrar")
    async def terminal_cerrar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await request.json()
        return {"ok": cerrar(str(d.get("id") or ""))}

    @r.post("/terminal/sugerir")
    async def terminal_sugerir(request: Request):
        """El Ctrl+K: lo que querés hacer, en tus palabras → el comando, para ESCRIBIRLO."""
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await request.json()
        comando, error = await asyncio.to_thread(
            sugerir, str(d.get("pedido") or ""), str(d.get("shell") or "pwsh"),
            str(d.get("cwd") or ""), str(d.get("pantalla") or ""))
        _anotar(f"Ctrl+K en {str(d.get('cwd') or '')}: {str(d.get('pedido') or '')[:300]}"
                f" -> {comando or error}")
        return {"ok": bool(comando), "comando": comando, "error": error}

    @r.post("/terminal/anotar")
    async def terminal_anotar(request: Request):
        """Lo que la pagina pega desde el ▶ de un bloque de codigo queda escrito, igual que
        quedaba con el boton de correr de antes. Lo tipeado a mano no se anota."""
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await request.json()
        _anotar(f"pegado en la terminal {str(d.get('id') or '')[:20]} ({d.get('cwd') or ''})\n"
                + str(d.get("cmd") or "")[:8000])
        return {"ok": True}

    @r.websocket("/terminal/ws")
    async def terminal_ws(ws: WebSocket):
        motivo = _puerta(ws.headers, ws.query_params.get("llave", ""),
                         origenes_extra, anfitriones_extra)
        t = None if motivo else de(ws.query_params.get("id", ""))
        if motivo or not t:
            await ws.close(code=4403 if motivo else 4404)     # antes de aceptar: ni entra
            return
        await ws.accept()
        bucle = asyncio.get_running_loop()
        previo, cola = t.escuchar(bucle)

        async def salida():
            # ⚠ SIEMPRE se manda primero lo que ya habia, aunque este vacio: la pagina trata
            # al PRIMER mensaje como "repaso" y lo dibuja SIN contestar las preguntas que
            # trae adentro. Lo guardado incluye preguntas que el PowerShell le hizo a la
            # terminal en su momento (donde esta el cursor, que terminal sos); si la pagina
            # las contestara de nuevo, esas respuestas viejas le caerian al PowerShell como
            # si alguien las hubiera tipeado, y ensucian el renglon (medido: despues de
            # volver a una terminal, el Enter corria basura en vez del comando pegado).
            await ws.send_text(previo)
            while True:
                dato = await cola.get()
                # Lo que haya llegado junto se manda junto: un `dir` grande son cientos de
                # pedacitos y mandarlos de a uno traba la pagina.
                partes = [dato]
                while not cola.empty():
                    partes.append(cola.get_nowait())
                texto = "".join(p for p in partes if p)
                if texto:
                    await ws.send_text(texto)
                if None in partes:
                    await ws.close(code=4000)                 # la terminal se cerro
                    return

        tarea = asyncio.create_task(salida())
        try:
            while True:
                m = json.loads(await ws.receive_text())
                if m.get("t") == "i":
                    t.escribir(str(m.get("d") or ""))
                elif m.get("t") == "m":
                    t.medir(m.get("f"), m.get("c"))
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            tarea.cancel()
            t.dejar(bucle, cola)

    def archivo(nombre, tipo, sin_cache=False):
        return FileResponse(nombre, media_type=tipo, headers={
            "Cache-Control": "no-store" if sin_cache else "public, max-age=86400"})

    @r.get("/estaticos/terminal.js")
    def estatico_terminal():
        return archivo(ESTATICOS / "terminal.js", "application/javascript", sin_cache=True)

    @r.get("/estaticos/terceros/xterm.js")
    def estatico_xterm():
        return archivo(TERCEROS / "xterm.js", "application/javascript")

    @r.get("/estaticos/terceros/xterm-addon-fit.js")
    def estatico_xterm_ajuste():
        return archivo(TERCEROS / "xterm-addon-fit.js", "application/javascript")

    @r.get("/estaticos/terceros/xterm.css")
    def estatico_xterm_hoja():
        return archivo(TERCEROS / "xterm.css", "text/css")

    @r.get("/estaticos/terceros/xterm-addon-search.js")
    def estatico_xterm_buscar():
        return archivo(TERCEROS / "xterm-addon-search.js", "application/javascript")

    @r.get("/estaticos/terceros/xterm-addon-web-links.js")
    def estatico_xterm_enlaces():
        return archivo(TERCEROS / "xterm-addon-web-links.js", "application/javascript")

    return r


router = crear_router()
