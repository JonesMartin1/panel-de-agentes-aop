"""El ESCRITORIO REMOTO adentro del panel (2026-11-12).

Pedido de Martin, despues de ver a una sesion manejar un server por RustDesk: "¿no podemos
embeber RustDesk en el panel?". Es la pieza "Escritorio" de la columna derecha de /sesiones
(y la pagina suelta `/escritorio`, para el celular): muestra la pantalla de la otra compu y
deja manejarla con clics y teclado. La misma conexion la usa el agente de una sesion (skill
`rustdesk-agente`), asi que Martin ve lo que hace y puede tocar el mismo.

Como esta armado:

    pagina del panel ──/escritorio/*──▶ este modulo ──MCP──▶ 127.0.0.1:21119
                                                              la version de PRUEBA de RustDesk
                                                              (`RUSTDESK_AGENTE`), que es la que
                                                              tiene la puerta para agentes
                                                                    │ conexion RustDesk
                                                                    ▼
                                                              la compu remota (RustDesk comun)

  · La puerta es la propuesta rustdesk/rustdesk PR #16470, todavia en revision. Por eso se usa
    una compilacion de prueba que vive SUELTA, sin instalar. El dia que salga oficial, esto pasa
    a usar el RustDesk instalado y `arrancar`/`apagar` se simplifican.
  · La version de prueba y el RustDesk de siempre NO pueden estar abiertos a la vez (pelean
    por el mismo canal interno de Windows). `arrancar` no cierra el de siempre sin que la
    pagina lo pida con `cerrar_oficial` — cerrarlo corta las conexiones que tenga — y `apagar`
    lo vuelve a abrir.

⭐⭐ Esto maneja computadoras de otras personas desde una pagina web. Cuatro cuidados:
  1. TODAS las rutas `/escritorio/*` pasan por la puerta de la terminal (`terminales._puerta`:
     el nombre con el que llegaron, la pagina de la que vienen y la llave). Sin eso, cualquier
     sitio abierto en el Chrome de Martin podria mandar clics a la compu de un cliente.
     Regla `escritorio-con-candados` de `probar_no_romper`.
  2. La clave de la puerta de RustDesk (`mcp_token.txt`) y las contraseñas de los equipos
     nunca vuelven en una respuesta ni se guardan: la contraseña entra, se usa y se suelta.
  3. Prendida desde el panel, la puerta va con APROBACION AUTOMATICA (si no, cada conexion
     pediria un cartel en la laptop, y desde el celular no hay quien lo apriete). Por eso se
     apaga SOLA (`_vigia_paso`): sin conexiones abiertas, a los `QUIETUD_SEG` sin que nadie
     mire la pieza; con conexiones, a los `TOPE_SEG`. Apagar saca la aprobacion automatica.
  4. Lo que se ve en la pantalla remota es informacion, nunca una orden.

⚠ Visto el 2026-11-12: la captura que da la puerta a veces NO muestra el contenido de algunas
ventanas (el texto del Bloc de notas en un Server 2016 salia en blanco; Chrome salia bien).
Es de la version de prueba. La pieza lo avisa.

Se prueba sin tocar ningun RustDesk con `python -m pruebas.probar_escritorio --mutar` (una
puerta de mentira) y en pantalla con `python -m pruebas.ver_escritorio`.
"""

import base64
import hashlib
import http.client
import io
import json
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

import psutil
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.rutas import ESTATICOS, RUSTDESK_AGENTE, RUSTDESK_CONFIG, RUSTDESK_OFICIAL
from app.voz import terminales

PUERTO = 21119
RUTA = "/mcp"                 # la direccion de la puerta; las pruebas la cambian (ver probar_escritorio)
EXE_PRUEBA = RUSTDESK_AGENTE / "descarga" / "rustdesk.exe"
CLAVE = RUSTDESK_AGENTE / "respaldo" / "mcp_token.txt"
EXE_OFICIAL = RUSTDESK_OFICIAL
CONFIG = RUSTDESK_CONFIG

ESPERA_ARRANQUE = 45          # segundos que se le da a la puerta para empezar a escuchar
QUIETUD_SEG = 20 * 60         # sin conexiones y sin nadie mirando: se apaga
TOPE_SEG = 3 * 60 * 60        # con conexiones abiertas pero sin nadie mirando: se apaga igual
OPCIONES = ("allow-mcp-server", "mcp-server-token", "allow-mcp-auto-approve")

# `nuestra`: la prendio el panel (o la adopto al arrancar) y por eso el vigia la puede apagar.
# `ultimo`: la ultima vez que la pagina pidio algo.
_ESTADO = {"nuestra": False, "ultimo": 0.0}
_CANDADO = threading.Lock()          # arrancar y apagar, de a uno
_EQUIPOS = {"hora": 0.0, "lista": []}


class PuertaCerrada(Exception):
    """La version de prueba no esta abierta (o todavia no escucha)."""


# --- Hablarle a la puerta de RustDesk (MCP por HTTP) -----------------------------------------

class _Puerta:
    """Un cliente MCP chico. Guarda la sesion del protocolo y la rearma si la puerta la olvido."""

    def __init__(self):
        self._sid = None
        self._abriendo = threading.Lock()
        self._n = 0

    def _post(self, cuerpo, espera):
        try:
            clave = CLAVE.read_text(encoding="ascii").strip()
        except OSError:
            raise PuertaCerrada("no hay clave de la puerta")
        cab = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "Authorization": "Bearer " + clave}
        if self._sid:
            cab["Mcp-Session-Id"] = self._sid
        pedido = urllib.request.Request(f"http://127.0.0.1:{PUERTO}{RUTA}",
                                        data=json.dumps(cuerpo).encode(), headers=cab, method="POST")
        try:
            with urllib.request.urlopen(pedido, timeout=espera) as r:
                if r.headers.get("Mcp-Session-Id"):
                    self._sid = r.headers["Mcp-Session-Id"]
                try:
                    texto = r.read().decode("utf-8", "replace")
                except http.client.IncompleteRead as e:   # el 202 de un aviso llega vacio y cortado
                    texto = e.partial.decode("utf-8", "replace")
                tipo = r.headers.get("Content-Type") or ""
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as e:
            raise PuertaCerrada(str(e))
        if not texto.strip():
            return None
        if "text/event-stream" in tipo:
            datos = [l[5:].strip() for l in texto.splitlines() if l.startswith("data:")]
            return json.loads(datos[-1]) if datos else None
        return json.loads(texto)

    def _abrir(self):
        self._sid = None
        r = self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "panel", "version": "1"}}}, 15)
        if not r or "error" in r:
            raise PuertaCerrada("la puerta no quiso iniciar")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, 15)

    def llamar(self, herramienta, args=None, espera=60):
        """Llama una herramienta. Devuelve {ok, texto, datos, imagen}: `datos` es el texto leido
        como JSON cuando lo es, e `imagen` los bytes de la captura si vino una."""
        for intento in (0, 1):
            with self._abriendo:
                if not self._sid:
                    self._abrir()
                self._n += 1
                n = self._n
            try:
                r = self._post({"jsonrpc": "2.0", "id": n, "method": "tools/call",
                                "params": {"name": herramienta, "arguments": args or {}}}, espera)
                break
            except urllib.error.HTTPError as e:
                # La puerta se reinicio y no conoce nuestra sesion del protocolo: se rearma una vez.
                if intento == 0 and e.code in (400, 401, 404):
                    self._sid = None
                    continue
                raise PuertaCerrada(f"la puerta contesto {e.code}")
        if not r:
            return {"ok": False, "texto": "la puerta no contesto nada", "datos": None, "imagen": None}
        if "error" in r:
            return {"ok": False, "texto": str((r["error"] or {}).get("message") or r["error"])[:400],
                    "datos": None, "imagen": None}
        res = r.get("result") or {}
        textos, imagen = [], None
        for parte in res.get("content") or []:
            if parte.get("type") == "text":
                textos.append(parte.get("text") or "")
            elif parte.get("type") == "image" and parte.get("data"):
                imagen = base64.b64decode(parte["data"])
        texto = "\n".join(textos)
        datos = res.get("structuredContent")
        if datos is None:
            try:
                datos = json.loads(textos[0]) if textos else None
            except ValueError:
                datos = None
        return {"ok": not res.get("isError"), "texto": texto[:2000], "datos": datos, "imagen": imagen}


PUERTA = _Puerta()


# --- Los procesos y la configuracion (lo unico que toca la maquina) --------------------------

def puerta_abierta():
    """¿Hay algo escuchando en el puerto de la puerta? Un intento corto, solo en esta maquina."""
    try:
        with socket.create_connection(("127.0.0.1", PUERTO), timeout=0.4):
            return True
    except OSError:
        return False


def _procesos():
    """(los de la version de prueba, los del RustDesk de siempre). Uno sin ruta legible (de otro
    usuario, o elevado) se cuenta como el de siempre: ante la duda no se lo trata como nuestro."""
    prueba, oficiales = [], []
    carpeta = str(RUSTDESK_AGENTE).lower()
    for p in psutil.process_iter(["name", "exe"]):
        try:
            if (p.info.get("name") or "").lower() != "rustdesk.exe":
                continue
            ruta = (p.info.get("exe") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        (prueba if ruta.startswith(carpeta) else oficiales).append(p)
    return prueba, oficiales


def _matar(procesos):
    for p in procesos:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(procesos, timeout=5)


def _lanzar(exe):
    """Abre un RustDesk. Es un programa de ventana: la marca solo evita una consola de mas."""
    subprocess.Popen([str(exe)], cwd=str(exe.parent), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _escribir_opciones(prender, auto):
    """Deja en la configuracion local de RustDesk las opciones de la puerta.

    `prender` False no saca la puerta ni su clave (el RustDesk de siempre no las entiende y las
    ignora): solo saca la aprobacion automatica, que es lo unico que no puede quedar olvidado.
    """
    try:
        lineas = CONFIG.read_text(encoding="utf-8").splitlines()
    except OSError:
        lineas = []
    fuera = OPCIONES if prender else ("allow-mcp-auto-approve",)
    lineas = [l for l in lineas if l.split("=")[0].strip() not in fuera]
    if prender:
        if "[options]" not in lineas:
            lineas.append("[options]")
        i = lineas.index("[options]")
        nuevas = ["allow-mcp-server = 'Y'", f"mcp-server-token = '{_clave()}'"]
        if auto:
            nuevas.append("allow-mcp-auto-approve = 'Y'")
        lineas[i + 1:i + 1] = nuevas
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_bytes(("\n".join(lineas) + "\n").encode("utf-8"))


def _clave():
    """La clave de la puerta. Se crea una sola vez; no sale nunca de este modulo."""
    try:
        c = CLAVE.read_text(encoding="ascii").strip()
        if len(c) >= 20:
            return c
    except OSError:
        pass
    c = secrets.token_urlsafe(24).replace("-", "").replace("_", "")
    CLAVE.parent.mkdir(parents=True, exist_ok=True)
    CLAVE.write_text(c, encoding="ascii")
    return c


def _auto_puesta():
    try:
        return any(l.split("=")[0].strip() == "allow-mcp-auto-approve" and "'Y'" in l
                   for l in CONFIG.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


# --- Prender y apagar ------------------------------------------------------------------------

def arrancar(cerrar_oficial=False):
    """Abre la version de prueba con su puerta. No cierra el RustDesk de siempre sin permiso."""
    with _CANDADO:
        if not EXE_PRUEBA.exists():
            return {"ok": False, "error": "Falta la versión de prueba de RustDesk en esta máquina."}
        prueba, oficiales = _procesos()
        if puerta_abierta() and prueba and _auto_puesta():
            _ESTADO.update(nuestra=True, ultimo=time.time())
            return {"ok": True, "ya": True}
        if oficiales and not cerrar_oficial:
            return {"ok": False, "oficial_abierto": True,
                    "error": "Tu RustDesk de siempre está abierto: hay que cerrarlo para prender esto."}
        _matar(oficiales + prueba)      # la de prueba tambien: las opciones se leen al arrancar
        _escribir_opciones(True, True)
        _lanzar(EXE_PRUEBA)
        limite = time.time() + ESPERA_ARRANQUE
        while time.time() < limite and not puerta_abierta():
            time.sleep(0.5)
        if not puerta_abierta():
            _escribir_opciones(False, False)
            return {"ok": False, "error": "La versión de prueba no arrancó. Puede que el antivirus "
                                          "la esté frenando: mirá su registro."}
        PUERTA._sid = None
        _ESTADO.update(nuestra=True, ultimo=time.time())
        return {"ok": True, "cerro_oficial": bool(oficiales)}


def apagar(reabrir=True):
    """Cierra la version de prueba, saca la aprobacion automatica y reabre el RustDesk de siempre."""
    with _CANDADO:
        prueba, oficiales = _procesos()
        _matar(prueba)
        _escribir_opciones(False, False)
        PUERTA._sid = None
        _ESTADO.update(nuestra=False)
        reabierto = False
        if reabrir and not oficiales and EXE_OFICIAL.exists():
            _lanzar(EXE_OFICIAL)
            reabierto = True
        return {"ok": True, "reabierto": reabierto}


def _vigia_paso(ahora=None):
    """Una vuelta del vigia: ¿hay que apagarla sola? Devuelve el motivo, o "" si no hizo nada.

    Con aprobacion automatica, una puerta olvidada deja entrar a cualquier sesion sin preguntar:
    por eso no puede quedar prendida para siempre.
    """
    ahora = ahora or time.time()
    if not _ESTADO["nuestra"]:
        return ""
    if not puerta_abierta():
        _ESTADO["nuestra"] = False
        return ""
    quieta = ahora - _ESTADO["ultimo"]
    if quieta < QUIETUD_SEG:
        return ""
    if quieta < TOPE_SEG:
        try:
            if (PUERTA.llamar("list_sessions", espera=10)["datos"] or {}).get("sessions"):
                return ""             # hay una conexion abierta: alguien (o un agente) la usa
        except PuertaCerrada:
            return ""
    apagar()
    motivo = "tope" if quieta >= TOPE_SEG else "quieta"
    print(f"escritorio: la puerta de RustDesk se apago sola ({motivo}, {int(quieta / 60)} min sin mirar)",
          flush=True)
    return motivo


def encender_vigia():
    """Lo llama el panel al enchufar el modulo. Adopta una puerta que quedo prendida de antes
    (el panel se reinicia seguido y la version de prueba sobrevive) y arranca el vigia."""
    if puerta_abierta() and _auto_puesta() and _procesos()[0]:
        _ESTADO.update(nuestra=True, ultimo=time.time())

    def bucle():
        while True:
            time.sleep(60)
            try:
                _vigia_paso()
            except Exception as e:        # el vigia no puede morirse por un error suelto
                print("escritorio: vigia:", e, flush=True)

    threading.Thread(target=bucle, name="vigia-escritorio", daemon=True).start()


# --- Lo que muestra y hace la pieza ----------------------------------------------------------

def _equipos():
    """Los equipos recientes de RustDesk, para elegir a cual entrar. Se recuerdan un minuto."""
    if time.time() - _EQUIPOS["hora"] > 60:
        r = PUERTA.llamar("list_peers", espera=15)
        _EQUIPOS.update(hora=time.time(), lista=(r["datos"] or {}).get("peers") or [])
    return _EQUIPOS["lista"]


def _nombre_de(peer_id):
    for e in _EQUIPOS["lista"]:
        if str(e.get("id")) == str(peer_id):
            return e.get("alias") or e.get("hostname") or str(peer_id)
    return str(peer_id)


def estado():
    """Todo lo que la pieza necesita para dibujarse, en un pedido."""
    instalado = EXE_PRUEBA.exists()
    abierta = instalado and puerta_abierta()
    base = {"ok": True, "instalado": instalado, "puerta": abierta, "sesiones": [],
            "oficial_abierto": False}
    if not abierta:
        base["oficial_abierto"] = bool(_procesos()[1]) if instalado else False
        return base
    _ESTADO["ultimo"] = time.time()
    try:
        ses = (PUERTA.llamar("list_sessions", espera=15)["datos"] or {}).get("sessions") or []
        if ses and not _EQUIPOS["lista"]:
            _equipos()
    except PuertaCerrada:
        return {**base, "puerta": False}
    for s in ses:
        base["sesiones"].append({
            "sid": s.get("session_id"), "equipo": _nombre_de(s.get("peer_id")),
            "modo": s.get("mode"), "estado": s.get("state"), "listo": bool(s.get("ready")),
            "paso": s.get("next_step") or "", "pantallas": s.get("displays") or []})
    return base


def equipos():
    return {"ok": True, "equipos": [
        {"id": str(e.get("id")), "nombre": e.get("alias") or e.get("hostname") or str(e.get("id")),
         "usuario": e.get("username") or "", "en_linea": bool(e.get("online"))} for e in _equipos()]}


def _criollo(texto):
    """Lo que dice la puerta (en ingles, y para un agente) -> lo que le sirve leer a Martin."""
    t = (texto or "").lower()
    if "unknown session_id" in t:
        return "Esa conexión ya no existe."
    if "human control" in t or "request_control" in t:
        return "Ahora la maneja la ventana de RustDesk de la laptop."
    if "rejected" in t or "wrong password" in t:
        return "Esa contraseña no es."
    if "denied" in t or "declined" in t:
        return "No lo aprobaron en la laptop."
    if "timed out" in t or "timeout" in t:
        return "El equipo no contestó a tiempo."
    if "offline" in t:
        return "Ese equipo está apagado o sin conexión."
    return (texto or "").strip()[:300] or "No se pudo."


def _resumen(r):
    """Lo que vuelve a la pagina de una llamada: si anduvo y, si no, por que. Nunca la imagen."""
    if r["ok"]:
        d = r["datos"] if isinstance(r["datos"], dict) else {}
        return {"ok": True, "sid": d.get("session_id"), "estado": d.get("state"), "modo": d.get("mode")}
    return {"ok": False, "error": _criollo(r["texto"])}


def conectar(peer_id):
    peer_id = "".join(ch for ch in str(peer_id) if ch.isdigit())
    if not 6 <= len(peer_id) <= 12:
        return {"ok": False, "error": "Ese ID no parece de RustDesk (son números)."}
    return _resumen(PUERTA.llamar("connect", {"peer_id": peer_id}, espera=90))


def dar_clave(sid, clave):
    """Le pasa a RustDesk la contraseña del equipo. Se usa y se suelta: no se guarda ni se anota."""
    if not clave:
        return {"ok": False, "error": "Falta la contraseña."}
    r = PUERTA.llamar("authenticate", {"session_id": sid, "password": clave}, espera=60)
    if not r["ok"]:
        # La puerta a veces repite la contraseña en su mensaje: se tapa antes de traducirlo.
        dicho = _criollo(r["texto"].replace(clave, "•••"))
        mala = dicho == "Esa contraseña no es."
        return {"ok": False, "mala": mala, "error": "" if mala else dicho}
    return _resumen(PUERTA.llamar("get_session", {"session_id": sid, "wait_ms": 15000}, espera=40))


def control(sid, tomar):
    return _resumen(PUERTA.llamar("request_control" if tomar else "release_control",
                                  {"session_id": sid}, espera=90))


def desconectar(sid):
    r = PUERTA.llamar("disconnect", {"session_id": sid}, espera=30)
    if not r["ok"] and _sin_control(r):
        PUERTA.llamar("request_control", {"session_id": sid}, espera=30)
        r = PUERTA.llamar("disconnect", {"session_id": sid}, espera=30)
    return _resumen(r)


def foto(sid, jpg=False):
    """La pantalla remota: (bytes, tipo, marca). `marca` identifica el contenido, para que la
    pagina no vuelva a bajar una imagen igual a la que ya tiene."""
    _ESTADO["ultimo"] = time.time()
    r = PUERTA.llamar("screenshot", {"session_id": sid}, espera=30)
    if not r["ok"] or not r["imagen"]:
        return None, r["texto"][:300] or "sin imagen", ""
    datos = r["imagen"]
    marca = hashlib.sha1(datos).hexdigest()[:20]
    if jpg:
        try:
            from PIL import Image
            salida = io.BytesIO()
            Image.open(io.BytesIO(datos)).convert("RGB").save(salida, "JPEG", quality=72)
            return salida.getvalue(), "image/jpeg", marca
        except Exception:
            pass                      # si no se pudo achicar, va el PNG tal cual
    return datos, "image/png", marca


BOTONES = {"click", "double_click", "right_click", "middle_click", "move", "drag"}
MODIFICADORES = {"ctrl", "shift", "alt", "command"}
DIRECCIONES = {"up", "down", "left", "right"}


def _sin_control(r):
    t = (r.get("texto") or "").lower()
    return "request_control" in t or "human control" in t or "agent control" in t


def _armar(a):
    """Un pedido de la pagina -> (herramienta, argumentos) de la puerta, o (None, motivo).

    Aca se decide que puede mandar una pagina: solo estas cinco cosas, con sus valores acotados.
    """
    tipo = a.get("tipo")
    sid = str(a.get("sid") or "")
    if not sid:
        return None, "Falta la conexión."
    mods = [m for m in (a.get("mods") or []) if m in MODIFICADORES]
    base = {"session_id": sid}

    def punto(cx, cy):
        return max(0, min(20000, int(a[cx]))), max(0, min(20000, int(a[cy])))

    try:
        if tipo == "mouse":
            if a.get("accion") not in BOTONES:
                return None, "Ese clic no existe."
            x, y = punto("x", "y")
            args = {**base, "action": a["accion"], "x": x, "y": y}
            if a["accion"] == "drag":
                args["to_x"], args["to_y"] = punto("a_x", "a_y")
            if mods:
                args["modifiers"] = mods
            return "mouse", args
        if tipo == "rueda":
            if a.get("direccion") not in DIRECCIONES:
                return None, "Esa dirección no existe."
            x, y = punto("x", "y")
            return "scroll", {**base, "x": x, "y": y, "direction": a["direccion"],
                              "amount": max(1, min(50, int(a.get("cantidad") or 3)))}
        if tipo == "tecla":
            tecla = str(a.get("tecla") or "")
            if not tecla or len(tecla) > 20:
                return None, "Falta la tecla."
            args = {**base, "key": tecla}
            if mods:
                args["modifiers"] = mods
            return "press_key", args
        if tipo in ("texto", "pegar"):
            texto = str(a.get("texto") or "")
            if not texto or len(texto) > 4000:
                return None, "Falta el texto (o es demasiado largo)."
            return ("type_text" if tipo == "texto" else "paste_text"), {**base, "text": texto}
    except (KeyError, TypeError, ValueError):
        return None, "A ese pedido le falta un dato."
    return None, "No sé hacer eso."


def accion(a):
    """Un clic, una tecla o un texto en la compu remota. Si el control lo tenia la ventana de
    RustDesk, lo pide solo y repite una vez: tocar la imagen ES pedir el control."""
    herramienta, args = _armar(a if isinstance(a, dict) else {})
    if not herramienta:
        return {"ok": False, "error": args}
    _ESTADO["ultimo"] = time.time()
    r = PUERTA.llamar(herramienta, args, espera=45)
    tomo = False
    if not r["ok"] and _sin_control(r):
        pedido = PUERTA.llamar("request_control", {"session_id": args["session_id"]}, espera=90)
        if not pedido["ok"]:
            return {"ok": False, "error": "No me dieron el control. " + _criollo(pedido["texto"])}
        tomo = True
        r = PUERTA.llamar(herramienta, args, espera=45)
    return {"ok": True, "tomo_control": tomo} if r["ok"] else {"ok": False, "error": _criollo(r["texto"])}


# --- Las rutas -------------------------------------------------------------------------------

PAGINA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Escritorio remoto</title>
<style>html,body{margin:0;height:100%;background:#0f1420;color:#e6e9ef;
font-family:'Segoe UI',system-ui,sans-serif}#caja{height:100%;box-sizing:border-box;padding:10px}</style>
</head><body><div id="caja"></div><script src="/estaticos/escritorio.js"></script>
<script>Escritorio.iniciar({suelta: true}); Escritorio.mostrar(document.getElementById('caja'));</script>
</body></html>"""


def crear_router(origenes_extra=(), anfitriones_extra=()):
    """Las rutas. Los `extra` son para las pruebas, que lo sirven desde un servidor aparte."""
    r = APIRouter()

    def puerta(pedido, pide_llave=True):
        return terminales._puerta(pedido.headers, pedido.headers.get("x-terminal-llave", ""),
                                  origenes_extra, anfitriones_extra, pide_llave)

    def no(motivo):
        return JSONResponse({"ok": False, "error": motivo}, status_code=403)

    def cerrada(e):
        return {"ok": False, "cerrada": True, "error": "RustDesk con agente no está prendido."}

    async def cuerpo(pedido):
        try:
            d = await pedido.json()
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}

    @r.get("/escritorio/llave")
    def escritorio_llave(request: Request):
        """La llave (la misma de la terminal), para la pagina del panel. Otra pagina no puede
        leer esta respuesta, y si lo intenta de frente el `Origin` la delata."""
        motivo = puerta(request, pide_llave=False)
        if motivo:
            return no(motivo)
        return JSONResponse({"ok": True, "llave": terminales.LLAVE},
                            headers={"Cache-Control": "no-store"})

    @r.get("/escritorio/estado")
    def escritorio_estado(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        return JSONResponse(estado(), headers={"Cache-Control": "no-store"})

    @r.post("/escritorio/arrancar")
    async def escritorio_arrancar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(arrancar, bool(d.get("cerrar_oficial")))

    @r.post("/escritorio/apagar")
    async def escritorio_apagar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        return await _aparte(apagar)

    @r.get("/escritorio/equipos")
    def escritorio_equipos(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        try:
            return equipos()
        except PuertaCerrada as e:
            return cerrada(e)

    @r.post("/escritorio/conectar")
    async def escritorio_conectar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(_con_puerta, conectar, d.get("id"))

    @r.post("/escritorio/clave")
    async def escritorio_clave(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(_con_puerta, dar_clave, str(d.get("sid") or ""), str(d.get("clave") or ""))

    @r.post("/escritorio/control")
    async def escritorio_control(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(_con_puerta, control, str(d.get("sid") or ""), bool(d.get("tomar")))

    @r.post("/escritorio/desconectar")
    async def escritorio_desconectar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(_con_puerta, desconectar, str(d.get("sid") or ""))

    @r.post("/escritorio/accion")
    async def escritorio_accion(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        return await _aparte(_con_puerta, accion, d)

    @r.get("/escritorio/foto")
    def escritorio_foto(request: Request, sid: str = "", jpg: int = 0):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        try:
            datos, tipo, marca = foto(sid, bool(jpg))
        except PuertaCerrada as e:
            return JSONResponse(cerrada(e), status_code=503)
        if datos is None:
            return JSONResponse({"ok": False, "error": tipo}, status_code=409)
        if request.headers.get("if-none-match", "").strip('"') == marca:
            return Response(status_code=304)
        return Response(datos, media_type=tipo,
                        headers={"ETag": f'"{marca}"', "Cache-Control": "no-store"})

    @r.get("/estaticos/escritorio.js")
    def estatico_escritorio():
        return FileResponse(ESTATICOS / "escritorio.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-store"})

    @r.get("/escritorio")
    def escritorio_pagina():
        """La pieza sola, a pantalla completa: para el celular. Es una pagina sin datos: todo
        lo que muestra lo pide despues, por las rutas de arriba y con la llave."""
        return Response(PAGINA, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})

    return r


def _con_puerta(funcion, *args):
    try:
        return funcion(*args)
    except PuertaCerrada:
        return {"ok": False, "cerrada": True, "error": "RustDesk con agente no está prendido."}


async def _aparte(funcion, *args):
    """Lo que puede tardar (prender la puerta, esperar una contraseña) va en otro hilo: el
    panel atiende a todas las sesiones por el mismo lado y no puede quedarse esperando."""
    import asyncio
    return await asyncio.get_running_loop().run_in_executor(None, funcion, *args)


router = crear_router()
