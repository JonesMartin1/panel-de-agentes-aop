"""Prueba del escritorio remoto (`app/voz/escritorio.py`) SIN tocar ningun RustDesk.

    python -m pruebas.probar_escritorio            # los chequeos
    python -m pruebas.probar_escritorio --mutar    # rompe cada cuidado y exige que se note

Levanta una PUERTA DE MENTIRA (un servidor chico que habla el mismo protocolo que la de
RustDesk) y le cambia al modulo todo lo que toca la maquina: los procesos, el lanzador, la
configuracion y la clave van a una carpeta temporal. Lo que importa cuidar:
  · que ninguna ruta deje pasar sin la puerta y la llave de la terminal;
  · que prender NO cierre el RustDesk de siempre sin permiso, y que apagar lo devuelva;
  · que la puerta no pueda quedar prendida para siempre (el vigia);
  · que una pagina solo pueda mandar clics, teclas y texto acotados;
  · que ni la clave de la puerta ni la contraseña de un equipo salgan en una respuesta.
"""
import base64
import io
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.voz import escritorio, terminales

OK, MAL = [], []


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {str(detalle)[:300]}")


# --- La puerta de mentira --------------------------------------------------------------------

class PuertaFalsa:
    """Habla MCP como la puerta de RustDesk. Anota todo lo que le piden."""

    def __init__(self, clave):
        self.clave = clave
        self.llamadas = []            # (herramienta, argumentos)
        self.sesiones = {}            # sid -> dict
        self.protocolo = set()        # sesiones del protocolo que conoce
        self.claves_vistas = []
        self.color = (30, 90, 160)
        self.srv = None

    def png(self):
        b = io.BytesIO()
        Image.new("RGB", (800, 600), self.color).save(b, "PNG")
        return base64.b64encode(b.getvalue()).decode()

    def herramienta(self, nombre, a):
        self.llamadas.append((nombre, dict(a)))
        texto = lambda t, mal=False: {"content": [{"type": "text", "text": t}], "isError": mal}
        if nombre == "list_peers":
            return texto(json.dumps({"peers": [
                {"id": "111222333", "alias": "Fox", "hostname": "datos", "username": "SERVER", "online": True},
                {"id": "444555666", "alias": "", "hostname": "ventas1", "username": "SILVA", "online": False}]}))
        if nombre == "list_sessions":
            return texto(json.dumps({"sessions": list(self.sesiones.values())}))
        if nombre == "connect":
            sid = "ses-" + a["peer_id"]
            self.sesiones[sid] = {"peer_id": a["peer_id"], "session_id": sid, "mode": "human",
                                  "ready": False, "state": "needs_password",
                                  "next_step": "Call authenticate."}
            return texto(json.dumps(self.sesiones[sid]))
        s = self.sesiones.get(a.get("session_id"))
        if not s:
            return texto("Unknown session_id: " + str(a.get("session_id")), True)
        if nombre == "authenticate":
            self.claves_vistas.append(a["password"])
            if a["password"] != "buena":
                s["state"] = "wrong_password"
                return texto("The password " + a["password"] + " was rejected.", True)
            s.update(state="ready", ready=True, displays=[{"index": 0, "x": 0, "y": 0, "width": 800, "height": 600}])
            return texto("ok")
        if nombre == "get_session":
            return texto(json.dumps(s))
        if nombre == "request_control":
            s["mode"] = "agent"
            return texto("Granted. The connection is now under agent control.")
        if nombre == "release_control":
            s["mode"] = "human"
            return texto("Released.")
        if nombre == "screenshot":
            return {"content": [{"type": "image", "data": self.png(), "mimeType": "image/png"},
                                {"type": "text", "text": "Display 0: 800x600 px."}]}
        if nombre in ("mouse", "scroll", "press_key", "type_text", "paste_text", "disconnect"):
            if s["mode"] != "agent":
                return texto("This session is under human control, so the agent may only read it. "
                             "Call request_control and wait for the user to approve first.", True)
            if nombre == "disconnect":
                self.sesiones.pop(a["session_id"], None)
            return texto("ok")
        return texto("Unknown tool", True)

    # ⚠⚠ Esta puerta NO contesta por la red: el montaje le cambia al modulo su `_post` por
    # `post`, de aca abajo. En esta maquina algo se mete en los pedidos locales que llevan la
    # marca del protocolo (la cabecera `Mcp-Session-Id`, o una direccion que termina en `/mcp`)
    # y a un servidor de prueba le deja la respuesta VACIA. Medido pedido por pedido: el
    # `initialize` llega bien y los que ya llevan la marca, no. Con la puerta real de RustDesk
    # no pasa. Lo unico que si escucha en la red es el puerto, para `puerta_abierta`.
    def post(self, cuerpo, espera=0):
        import urllib.error
        e = escritorio
        if e.CLAVE.read_text().strip() != self.clave:
            raise urllib.error.HTTPError("falsa", 401, "sin clave", {}, None)
        if self.srv is None:
            raise e.PuertaCerrada("apagada")
        if cuerpo.get("method") == "initialize":
            self.n_proto = getattr(self, "n_proto", 0) + 1
            nuevo = "proto-%d" % self.n_proto
            self.protocolo.add(nuevo)
            e.PUERTA._sid = nuevo
            return {"jsonrpc": "2.0", "id": cuerpo["id"], "result": {"serverInfo": {}}}
        if e.PUERTA._sid not in self.protocolo:
            raise urllib.error.HTTPError("falsa", 404, "sesion desconocida", {}, None)
        if "id" not in cuerpo:
            return None
        res = self.herramienta(cuerpo["params"]["name"], cuerpo["params"].get("arguments") or {})
        return json.loads(json.dumps({"jsonrpc": "2.0", "id": cuerpo["id"], "result": res}))

    def arrancar(self, puerto=0):
        import socket
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", puerto))
        self.srv.listen(64)
        return self.srv.getsockname()[1]

    def parar(self):
        if self.srv:
            self.srv.close(); self.srv = None


class Proc:
    def __init__(self, que):
        self.que, self.vivo = que, True


# --- El montaje: nada de lo real --------------------------------------------------------------

class Montaje:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="escritorio_"))
        self.clave = "clave-de-prueba-0123456789"
        (self.tmp / "respaldo").mkdir()
        (self.tmp / "respaldo" / "mcp_token.txt").write_text(self.clave)
        (self.tmp / "prueba.exe").write_bytes(b"MZ")
        (self.tmp / "oficial.exe").write_bytes(b"MZ")
        (self.tmp / "local.toml").write_text("remote_id = ''\n\n[options]\ninput-source = 'x'\n\n[ui_flutter]\nwm = 'y'\n")
        self.falsa = PuertaFalsa(self.clave)
        self.prueba, self.oficiales, self.lanzados, self.matados = [], [], [], []
        e = escritorio
        self.guardado = {k: getattr(e, k) for k in (
            "PUERTO", "RUTA", "CLAVE", "CONFIG", "EXE_PRUEBA", "EXE_OFICIAL", "_procesos", "_matar",
            "_lanzar", "ESPERA_ARRANQUE", "QUIETUD_SEG", "TOPE_SEG", "BOTONES", "MODIFICADORES",
            "arrancar", "apagar")}
        self.guardado_puerta = terminales._puerta
        self.puerto_libre = self._libre()
        e.PUERTO = self.puerto_libre
        e.PUERTA._post = self.falsa.post
        e.CLAVE = self.tmp / "respaldo" / "mcp_token.txt"
        e.CONFIG = self.tmp / "local.toml"
        e.EXE_PRUEBA = self.tmp / "prueba.exe"
        e.EXE_OFICIAL = self.tmp / "oficial.exe"
        e.ESPERA_ARRANQUE = 5
        e._procesos = lambda: ([p for p in self.prueba if p.vivo], [p for p in self.oficiales if p.vivo])
        e._matar = self._matar
        e._lanzar = self._lanzar
        e.PUERTA._sid = None
        e._ESTADO.update(nuestra=False, ultimo=0.0)
        e._EQUIPOS.update(hora=0.0, lista=[])

    @staticmethod
    def _libre():
        import socket
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

    def _matar(self, procesos):
        for p in procesos:
            p.vivo = False
            self.matados.append(p.que)
            if p.que == "prueba":
                self.falsa.parar()

    def _lanzar(self, exe):
        self.lanzados.append(Path(exe).name)
        if Path(exe).name == "prueba.exe":
            self.prueba.append(Proc("prueba"))
            self.falsa.arrancar(self.puerto_libre)
        else:
            self.oficiales.append(Proc("oficial"))

    def desarmar(self):
        self.falsa.parar()
        escritorio.PUERTA.__dict__.pop("_post", None)
        for k, v in self.guardado.items():
            setattr(escritorio, k, v)
        terminales._puerta = self.guardado_puerta


def correr(romper=None):
    OK.clear(); MAL.clear()
    m = Montaje()
    if romper:
        romper(m)
    try:
        _chequeos(m)
    except Exception as x:            # un chequeo que explota es un chequeo que fallo
        chequeo("la prueba corre hasta el final", False, repr(x))
    finally:
        m.desarmar()
    return not MAL


def _chequeos(m):
    e, f = escritorio, m.falsa
    config = lambda: (m.tmp / "local.toml").read_text(encoding="utf-8")

    # --- apagada
    est = e.estado()
    chequeo("apagada: instalado sí, puerta no", est["instalado"] and not est["puerta"] and est["sesiones"] == [], est)

    # --- prender: nunca cierra el RustDesk de siempre sin permiso
    m.oficiales.append(Proc("oficial"))
    chequeo("apagada avisa que el de siempre está abierto", e.estado()["oficial_abierto"])
    r = e.arrancar(False)
    chequeo("sin permiso NO cierra el RustDesk de siempre",
            not r["ok"] and r.get("oficial_abierto") and not m.matados and not m.lanzados, (r, m.matados, m.lanzados))
    chequeo("y no toca la configuración", "mcp" not in config(), config())
    r = e.arrancar(True)
    chequeo("con permiso lo cierra y prende", r["ok"] and r.get("cerro_oficial") and m.matados == ["oficial"]
            and m.lanzados == ["prueba.exe"], (r, m.matados, m.lanzados))
    c = config()
    chequeo("deja la puerta, su clave y la aprobación automática en [options]",
            "allow-mcp-server = 'Y'" in c and f"mcp-server-token = '{m.clave}'" in c
            and "allow-mcp-auto-approve = 'Y'" in c
            and c.index("[options]") < c.index("allow-mcp-server") < c.index("[ui_flutter]"), c)
    chequeo("sin perder lo que ya había", "input-source = 'x'" in c and "wm = 'y'" in c and "remote_id" in c, c)
    chequeo("prender dos veces no relanza", e.arrancar(False).get("ya") and m.lanzados == ["prueba.exe"])

    # --- el cliente de la puerta
    est = e.estado()
    chequeo("prendida y sin conexiones", est["puerta"] and est["sesiones"] == [], est)
    eq = e.equipos()["equipos"]
    chequeo("equipos: alias o nombre, y si está en línea",
            [(x["nombre"], x["en_linea"]) for x in eq] == [("Fox", True), ("ventas1", False)], eq)
    f.protocolo.clear()                       # la puerta "se reinició": olvida nuestra sesión
    chequeo("si la puerta olvida la sesión del protocolo, se rearma sola", e.equipos()["ok"] is True
            or e.estado()["puerta"])

    # --- conectar y contraseña
    chequeo("un ID que no es número se rechaza sin llamar",
            not e.conectar("abc")["ok"] and not any(n == "connect" for n, _ in f.llamadas))
    r = e.conectar("111 222 333")
    sid = r.get("sid")
    chequeo("conectar pide contraseña", r["ok"] and r["estado"] == "needs_password" and sid, r)
    est = e.estado()
    chequeo("la conexión figura con el nombre del equipo",
            est["sesiones"] and est["sesiones"][0]["equipo"] == "Fox" and not est["sesiones"][0]["listo"], est)
    r = e.dar_clave(sid, "secreto-malo")
    chequeo("contraseña mala: avisa SIN repetirla", not r["ok"] and "secreto-malo" not in json.dumps(r), r)
    r = e.dar_clave(sid, "buena")
    chequeo("contraseña buena: lista", r["ok"] and r["estado"] == "ready", r)
    en_disco = "".join(p.read_text(errors="replace") for p in m.tmp.rglob("*") if p.is_file())
    chequeo("ninguna contraseña quedó escrita en el disco", "secreto-malo" not in en_disco and "buena" not in en_disco)

    # --- la foto
    datos, tipo, marca = e.foto(sid)
    chequeo("foto: un PNG con su marca", datos[:4] == b"\x89PNG" and tipo == "image/png" and len(marca) == 20)
    chequeo("misma pantalla, misma marca", e.foto(sid)[2] == marca)
    f.color = (200, 40, 40)
    chequeo("pantalla distinta, marca distinta", e.foto(sid)[2] != marca)
    datos, tipo, _ = e.foto(sid, jpg=True)
    chequeo("para el celular va en JPEG", datos[:2] == b"\xff\xd8" and tipo == "image/jpeg")

    # --- las acciones: solo lo acotado
    f.llamadas.clear()
    r = e.accion({"sid": sid, "tipo": "mouse", "accion": "click", "x": 400, "y": 300, "mods": ["shift", "inventado"]})
    chequeo("tocar con la ventana al mando: pide el control solo y repite",
            r == {"ok": True, "tomo_control": True}
            and [n for n, _ in f.llamadas] == ["mouse", "request_control", "mouse"], (r, f.llamadas))
    chequeo("el clic llega con sus coordenadas y solo los modificadores válidos",
            f.llamadas[-1][1] == {"session_id": sid, "action": "click", "x": 400, "y": 300, "modifiers": ["shift"]},
            f.llamadas[-1])
    f.llamadas.clear()
    e.accion({"sid": sid, "tipo": "mouse", "accion": "drag", "x": 10, "y": 20, "a_x": 300, "a_y": 400})
    chequeo("arrastrar manda desde y hasta", f.llamadas[-1] == ("mouse", {"session_id": sid, "action": "drag",
            "x": 10, "y": 20, "to_x": 300, "to_y": 400}), f.llamadas[-1])
    e.accion({"sid": sid, "tipo": "rueda", "x": 5, "y": 5, "direccion": "down", "cantidad": 999})
    chequeo("la rueda se acota a 50", f.llamadas[-1][1]["amount"] == 50 and f.llamadas[-1][0] == "scroll", f.llamadas[-1])
    e.accion({"sid": sid, "tipo": "tecla", "tecla": "Enter", "mods": ["ctrl"]})
    chequeo("tecla con modificador", f.llamadas[-1] == ("press_key", {"session_id": sid, "key": "Enter",
            "modifiers": ["ctrl"]}), f.llamadas[-1])
    e.accion({"sid": sid, "tipo": "texto", "texto": "hola"})
    chequeo("texto", f.llamadas[-1] == ("type_text", {"session_id": sid, "text": "hola"}), f.llamadas[-1])
    antes = len(f.llamadas)
    malas = [{"sid": sid, "tipo": "mouse", "accion": "formatear", "x": 1, "y": 1},
             {"sid": sid, "tipo": "shell", "texto": "del /s"},
             {"sid": sid, "tipo": "mouse", "accion": "click"},
             {"sid": sid, "tipo": "rueda", "x": 1, "y": 1, "direccion": "adentro"},
             {"sid": sid, "tipo": "texto", "texto": "x" * 5000},
             {"sid": "", "tipo": "texto", "texto": "x"}, "no soy un dict"]
    chequeo("lo que no es un clic, una tecla o un texto acotado se rechaza SIN llegar a RustDesk",
            all(not e.accion(a)["ok"] for a in malas) and len(f.llamadas) == antes, f.llamadas[antes:])
    chequeo("la coordenada negativa se lleva a cero",
            e._armar({"sid": sid, "tipo": "mouse", "accion": "click", "x": -50, "y": 7})[1]["x"] == 0)

    # --- control y desconectar
    chequeo("soltar el control", e.control(sid, False)["ok"] and f.sesiones[sid]["mode"] == "human")
    chequeo("desconectar pide el control si hace falta y cierra", e.desconectar(sid)["ok"] and sid not in f.sesiones)

    # --- las rutas: la puerta y la llave
    enrutador = e.crear_router()
    app = FastAPI(); app.include_router(enrutador)
    c = TestClient(app, base_url="http://127.0.0.1:8750")
    ll = {"x-terminal-llave": terminales.LLAVE}
    # Las rutas se sacan del enrutador mismo, no de una lista a mano: una ruta nueva que se
    # olvide de la puerta tiene que caer aca sola.
    rutas = sorted({(next(iter(r.methods - {"HEAD"})), r.path) for r in enrutador.routes
                    if getattr(r, "path", "").startswith("/escritorio/")})
    chequeo("hay rutas que cuidar (por lo menos diez)", len(rutas) >= 10, rutas)
    pedir = lambda met, ruta, **k: (c.get(ruta, **k) if met == "GET" else c.post(ruta, json={}, **k))
    sin_llave = [(met, ruta) for met, ruta in rutas if ruta != "/escritorio/llave"
                 and pedir(met, ruta).status_code != 403]
    chequeo("sin llave no entra ninguna ruta", not sin_llave, sin_llave)
    de_afuera = [(met, ruta) for met, ruta in rutas
                 if pedir(met, ruta, headers={**ll, "origin": "https://pagina-mala.com"}).status_code != 403]
    chequeo("con llave pero desde OTRA página, tampoco", not de_afuera, de_afuera)
    otro_nombre = [(met, ruta) for met, ruta in rutas
                   if pedir(met, ruta, headers={**ll, "host": "atacante.com"}).status_code != 403]
    chequeo("con un nombre que no es de esta máquina, tampoco", not otro_nombre, otro_nombre)
    r = c.get("/escritorio/llave")
    chequeo("la página del panel recibe la llave", r.status_code == 200 and r.json()["llave"] == terminales.LLAVE)
    chequeo("con la llave, el estado contesta", c.get("/escritorio/estado", headers=ll).json().get("puerta") is True)
    respuestas = [c.get("/escritorio/estado", headers=ll).text, c.get("/escritorio/equipos", headers=ll).text,
                  c.get("/escritorio/llave").text, c.get("/escritorio").text,
                  c.post("/escritorio/conectar", json={"id": "444555666"}, headers=ll).text]
    chequeo("la clave de la puerta de RustDesk no sale en ninguna respuesta",
            all(m.clave not in t for t in respuestas))
    sid2 = "ses-444555666"
    r = c.post("/escritorio/clave", json={"sid": sid2, "clave": "otra-mala"}, headers=ll)
    chequeo("por HTTP la contraseña tampoco vuelve", r.status_code == 200 and "otra-mala" not in r.text, r.text)
    c.post("/escritorio/clave", json={"sid": sid2, "clave": "buena"}, headers=ll)
    r = c.get("/escritorio/foto", params={"sid": sid2}, headers=ll)
    chequeo("la foto llega con su marca", r.status_code == 200 and r.content[:4] == b"\x89PNG" and r.headers.get("etag"))
    r2 = c.get("/escritorio/foto", params={"sid": sid2}, headers={**ll, "if-none-match": r.headers["etag"]})
    chequeo("si la pantalla no cambió, no se vuelve a mandar (304)", r2.status_code == 304, r2.status_code)
    r = c.post("/escritorio/accion", json={"sid": sid2, "tipo": "tecla", "tecla": "Meta"}, headers=ll)
    chequeo("una tecla por HTTP llega a RustDesk", r.json().get("ok") and f.llamadas[-1][0] == "press_key", r.text)
    chequeo("la foto de una conexión que no existe avisa (409)",
            c.get("/escritorio/foto", params={"sid": "nada"}, headers=ll).status_code == 409)

    # --- el vigía: no puede quedar prendida para siempre
    ahora = time.time()
    e._ESTADO.update(nuestra=True, ultimo=ahora)
    chequeo("recién usada: el vigía no hace nada", e._vigia_paso(ahora + 60) == "" and m.prueba[-1].vivo)
    chequeo("quieta pero con una conexión abierta: la deja", e._vigia_paso(ahora + e.QUIETUD_SEG + 5) == ""
            and m.prueba[-1].vivo)
    chequeo("con conexión, pasado el tope: la apaga igual",
            e._vigia_paso(ahora + e.TOPE_SEG + 5) == "tope" and not m.prueba[-1].vivo)
    c2 = config()
    chequeo("apagar saca la aprobación automática y deja lo demás",
            "allow-mcp-auto-approve" not in c2 and "input-source = 'x'" in c2, c2)
    chequeo("y vuelve a abrir el RustDesk de siempre", m.lanzados[-1] == "oficial.exe" and not e._ESTADO["nuestra"])
    chequeo("apagada, el estado lo dice y no explota", e.estado()["puerta"] is False)
    chequeo("una acción con la puerta apagada avisa, no explota",
            e._con_puerta(e.accion, {"sid": "x", "tipo": "texto", "texto": "a"}).get("cerrada") is True)
    # sin conexiones: se apaga a los QUIETUD_SEG
    for p in m.oficiales:
        p.vivo = False
    e.arrancar(False)
    e._ESTADO.update(nuestra=True, ultimo=ahora)
    f.sesiones.clear()
    chequeo("sin conexiones y quieta: la apaga", e._vigia_paso(ahora + e.QUIETUD_SEG + 5) == "quieta"
            and not m.prueba[-1].vivo)
    # una que no prendió el panel no se toca
    for p in m.oficiales:
        p.vivo = False
    e.arrancar(False)
    e._ESTADO.update(nuestra=False, ultimo=0)
    chequeo("una puerta que no prendió el panel no la apaga", e._vigia_paso(ahora + 10 * e.TOPE_SEG) == ""
            and m.prueba[-1].vivo)


def mutaciones():
    class Todo:
        def __contains__(self, x):
            return True

    def sin_puerta(m):
        terminales._puerta = lambda *a, **k: ""

    def vigia_dormido(m):
        escritorio.QUIETUD_SEG = escritorio.TOPE_SEG = 10 ** 9

    def cierra_sin_permiso(m):
        real = escritorio.arrancar
        escritorio.arrancar = lambda cerrar_oficial=False: real(True)

    def acciones_sin_acotar(m):
        escritorio.BOTONES = Todo()

    def repite_la_clave(m):
        real = m.falsa.herramienta
        # nada que romper en la puerta: se rompe el tapado del modulo
        escritorio_dar = escritorio.dar_clave
        def dar(sid, clave):
            r = escritorio.PUERTA.llamar("authenticate", {"session_id": sid, "password": clave})
            return {"ok": r["ok"], "error": r["texto"]} if not r["ok"] else escritorio_dar(sid, clave)
        m.guardado["dar_clave"] = escritorio_dar
        escritorio.dar_clave = dar

    casos = {"sin la puerta de la terminal": sin_puerta, "vigía que nunca apaga": vigia_dormido,
             "cierra el RustDesk de siempre sin permiso": cierra_sin_permiso,
             "acepta cualquier acción de mouse": acciones_sin_acotar,
             "devuelve la contraseña en el error": repite_la_clave}
    import contextlib
    cazadas = 0
    for nombre, romper in casos.items():
        with contextlib.redirect_stdout(io.StringIO()):
            paso = correr(romper)
        print(f"  mutación «{nombre}»: {'CAZADA' if not paso else 'NO SE NOTÓ ✗'}")
        cazadas += not paso
    return cazadas == len(casos)


if __name__ == "__main__":
    bien = correr()
    print(f"escritorio: {len(OK)} bien, {len(MAL)} mal")
    if "--mutar" in sys.argv:
        bien = mutaciones() and bien
    sys.exit(0 if bien else 1)
