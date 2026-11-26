"""La pieza VISTA de la columna derecha: los PDF y las fotos de la charla (2026-11-16).

Pedido de Martin: "me gustaria poder ver pdfs o fotos aca, porque yo trabajo mucho con eso:
si una sesion me crea un PDF o me muestra una imagen, me gustaria poder verlo aca".

De donde salen: de la CHARLA misma (su `.jsonl`), no de mirar carpetas. Se juntan las rutas a
un PDF o a una imagen que aparecen en:
  · lo que la sesion ESCRIBIO (Write/Edit/NotebookEdit) -> "creó"
  · lo que la sesion ABRIO (Read: es como Claude "mira" una foto o un PDF) -> "abrió"
  · lo que vos le mandaste (tus mensajes, incluidas las fotos del celular) -> "tuya"
  · lo que la sesion nombro en su texto o en un comando -> "nombró"
Y solo las que existen en el disco.

⚠ Lo que DEVUELVE una herramienta (la salida de un Glob, un `ls`, un `git status`) no se mira:
trae cientos de rutas que nadie pidio ver, y la pieza se llenaria de capturas de pruebas.
⚠ Tampoco los avisos que el sistema le inyecta a la charla (`<system-reminder>`) ni el
resumen de una charla compactada: son rutas viejas o ajenas.

⭐⭐ Los candados, porque esto SIRVE ARCHIVOS DEL DISCO a una pagina:
  1. Solo se sirve un archivo que ESA charla nombro, y se pide por su codigo (`id`), nunca por
     la ruta: no hay forma de pedir "C:\\cualquier\\cosa.pdf".
  2. Solo PDF e imagenes (`EXT`). Un SVG puede traer codigo adentro: se sirve con
     `Content-Security-Policy: sandbox` para que, abierto aparte, no corra nada.
  3. La misma puerta que la terminal (`terminales._puerta`, sin llave): el nombre con el que
     llego el pedido tiene que ser de esta maquina y, si trae `Origin`, el del propio panel.
     Y ademas el navegador tiene que decir que el pedido viene del mismo sitio
     (`Sec-Fetch-Site`), asi otra pagina no puede ni siquiera embeberlo.
Nunca ejecuta nada.

⭐ ELIMINAR (2026-11-16, pedido de Martin: "¿y si quisiera eliminarlos?"; eligio las dos cosas):
  · "Quitar de la lista": el archivo queda en el disco y solo deja de verse en ESA charla
    (`VISTA_QUITADOS`). Se deshace con "devolver".
  · "Mandar a la papelera": lo saca del disco pero a la PAPELERA DE WINDOWS, de donde se
    recupera. Nunca un borrado definitivo: en un disco sin papelera (de red, un pendrive) se
    niega en vez de borrar para siempre (`_disco_con_papelera`). La pagina pide un segundo toque.
  Los dos van por codigo, solo sobre lo que esa charla nombro, y con la misma puerta.
Se prueba con `python -m pruebas.probar_vista --mutar`.
"""

import hashlib
import json
import os
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app.rutas import CLAUDE_PROYECTOS, ESTATICOS, VISTA_QUITADOS
from app.voz.seguir import carpeta_de
from app.voz.terminales import _puerta

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
EXT = EXT_IMAGEN | {".pdf"}
MAX_POR_CHARLA = 300          # una charla larguisima no puede mandar una lista infinita
MAX_TEXTO = 200_000           # un texto mas largo que esto es un volcado, no una charla

_EXTS = r"(?:pdf|png|jpe?g|gif|webp|bmp|svg)"
# Ruta completa de Windows (con \ o con /). Puede tener espacios; el `*?` corta en la PRIMERA
# extension que aparece, asi "D:\a.png y D:\b.pdf" da dos y no una larga.
ABSOLUTA = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]:[\\/][^\"<>|*?\r\n\t`'\[\]()]*?\." + _EXTS +
                      r")(?![A-Za-z0-9])", re.I)
# Ruta relativa a la carpeta de la charla ("docs/informe.pdf"). Sin espacios: con espacios
# agarraria media frase.
RELATIVA = re.compile(r"(?<![A-Za-z0-9_:\\/.\-])((?:[\w.\-]+[\\/])*[\w.\-]+\." + _EXTS +
                      r")(?![A-Za-z0-9])", re.I)
AVISO_SISTEMA = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
SID_OK = re.compile(r"[A-Za-z0-9_-]{1,80}")

# De mas fuerte a mas debil: si la misma ruta aparece de dos formas, queda la mas fuerte.
FUERZA = {"creó": 4, "abrió": 3, "tuya": 2, "nombró": 1}
ESCRIBEN = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

_CACHE = {}                   # ruta del .jsonl -> {"pos", "items"}
_CANDADO = threading.Lock()


def id_de(ruta):
    """El codigo de un archivo: lo que viaja en el pedido en vez de la ruta."""
    return hashlib.sha1(os.path.normcase(str(ruta)).encode("utf-8")).hexdigest()[:14]


def charla_de(cwd, sid):
    """El `.jsonl` de la charla, o None. Primero donde deberia estar; si no, se busca por id
    (una charla que se movio de carpeta sigue teniendo el mismo id)."""
    if not SID_OK.fullmatch(sid or ""):
        return None
    if cwd:
        f = carpeta_de(cwd) / (sid + ".jsonl")
        if f.is_file():
            return f
    for f in CLAUDE_PROYECTOS.glob("*/" + sid + ".jsonl"):
        return f
    return None


def _rutas_en(texto, cwd, relativas=True):
    """Las rutas a un PDF o imagen que nombra un texto, ya resueltas (existan o no)."""
    if not texto or len(texto) > MAX_TEXTO:
        return []
    salida = []
    for m in ABSOLUTA.finditer(texto):
        salida.append(Path(m.group(1)))
    if relativas and cwd:
        base = Path(cwd)
        for m in RELATIVA.finditer(texto):
            t = m.group(1)
            if re.match(r"[A-Za-z]:", t):
                continue
            salida.append(base / t)
    return salida


def _de_un_renglon(d, cwd):
    """[(ruta, como)] de un renglon ya leido del `.jsonl`."""
    tipo = d.get("type")
    if tipo not in ("user", "assistant") or d.get("isCompactSummary") or d.get("isMeta"):
        return []
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        c = [{"type": "text", "text": c}]
    if not isinstance(c, list):
        return []
    salida = []
    for it in c:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t == "text":
            texto = AVISO_SISTEMA.sub(" ", it.get("text") or "")
            como = "tuya" if tipo == "user" else "nombró"
            salida += [(r, como) for r in _rutas_en(texto, cwd)]
        elif t == "tool_use" and tipo == "assistant":
            nombre, ent = it.get("name") or "", it.get("input") or {}
            if not isinstance(ent, dict):
                continue
            fp = ent.get("file_path") or ent.get("notebook_path") or ""
            if isinstance(fp, str) and fp and Path(fp).suffix.lower() in EXT:
                como = "creó" if nombre in ESCRIBEN else "abrió" if nombre == "Read" else "nombró"
                salida.append((Path(fp) if Path(fp).is_absolute() else Path(cwd or ".") / fp, como))
            cmd = ent.get("command")
            if isinstance(cmd, str):
                salida += [(r, "nombró") for r in _rutas_en(cmd, cwd)]
        # tool_result: a proposito no (ver arriba).
    return salida


def _leer_nuevo(archivo, cwd):
    """Lee SOLO lo que se agrego al `.jsonl` desde la ultima vez. Una charla de 100 MB se lee
    entera una sola vez; despues, cada pedido cuesta lo que escribio desde el anterior."""
    clave = str(archivo)
    try:
        tam = archivo.stat().st_size
    except OSError:
        return {}
    est = _CACHE.get(clave)
    if not est or tam < est["pos"]:
        est = {"pos": 0, "items": {}}
        if len(_CACHE) > 60:
            _CACHE.clear()
        _CACHE[clave] = est
    if tam == est["pos"]:
        return est["items"]
    with open(archivo, "rb") as h:
        h.seek(est["pos"])
        bloque = h.read(tam - est["pos"])
    fin = bloque.rfind(b"\n")
    if fin < 0:
        return est["items"]           # un renglon a medio escribir: se lee la proxima vez
    est["pos"] += fin + 1
    items = est["items"]
    for crudo in bloque[:fin].split(b"\n"):
        # Atajo barato: un renglon sin ninguna de las extensiones no puede aportar nada.
        bajo = crudo.lower()
        if not any(e.encode() in bajo for e in (".pdf", ".png", ".jp", ".gif", ".webp", ".bmp", ".svg")):
            continue
        try:
            d = json.loads(crudo)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        cuando = d.get("timestamp") or ""
        for ruta, como in _de_un_renglon(d, cwd):
            if ruta.suffix.lower() not in EXT:
                continue
            k = os.path.normcase(os.path.normpath(str(ruta)))
            viejo = items.pop(k, None)        # pop + volver a poner = queda como el mas nuevo
            if viejo and FUERZA[viejo["como"]] > FUERZA[como]:
                como = viejo["como"]
            items[k] = {"ruta": os.path.normpath(str(ruta)), "como": como, "cuando": cuando}
    while len(items) > MAX_POR_CHARLA:
        items.pop(next(iter(items)))
    return items


def _quitados():
    try:
        d = json.loads(Path(VISTA_QUITADOS).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_quitados(d):
    VISTA_QUITADOS.parent.mkdir(parents=True, exist_ok=True)
    tmp = VISTA_QUITADOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, VISTA_QUITADOS)       # de un saque: un corte a mitad no deja el archivo roto


def lista(cwd, sid, con_quitados=False):
    """Los archivos de la charla que existen y no quitaste, del mas reciente al mas viejo."""
    todos = _todos(cwd, sid)
    if con_quitados:
        return todos
    fuera = set(_quitados().get(sid, []))
    return [a for a in todos if a["id"] not in fuera]


def _todos(cwd, sid):
    archivo = charla_de(cwd, sid)
    if not archivo:
        return []
    with _CANDADO:
        items = list(_leer_nuevo(archivo, cwd).values())
    salida = []
    for it in reversed(items):
        p = Path(it["ruta"])
        try:
            if not p.is_file():
                continue
            st = p.stat()
        except OSError:
            continue
        salida.append({"id": id_de(p), "nombre": p.name, "ruta": str(p),
                       "tipo": "pdf" if p.suffix.lower() == ".pdf" else "imagen",
                       "como": it["como"], "cuando": it["cuando"],
                       "bytes": st.st_size, "ts": st.st_mtime})
    return salida


def buscar(cwd, sid, ident):
    """La ruta de un archivo DE ESTA CHARLA por su codigo, o None. Es el candado 1."""
    for it in _todos(cwd, sid):
        if it["id"] == ident:
            return Path(it["ruta"])
    return None


def quitar(cwd, sid, ident):
    """Lo saca de la Vista de esta charla. El archivo no se toca."""
    if not buscar(cwd, sid, ident):
        return {"ok": False, "error": "Ese archivo no es de esta charla."}
    with _CANDADO:
        d = _quitados()
        fuera = d.setdefault(sid, [])
        if ident not in fuera:
            fuera.append(ident)
            del fuera[:-500]                 # una charla no puede crecer esto sin fin
            _guardar_quitados(d)
    return {"ok": True}


def devolver(sid, ident):
    """Deshace "quitar"."""
    with _CANDADO:
        d = _quitados()
        fuera = d.get(sid, [])
        if ident not in fuera:
            return {"ok": True}
        fuera.remove(ident)
        if not fuera:
            d.pop(sid, None)
        _guardar_quitados(d)
    return {"ok": True}


def _disco_con_papelera(ruta):
    """Solo los discos FIJOS de la compu tienen papelera. En uno de red o un pendrive, Windows
    "manda a la papelera" borrando para siempre: ahi se niega."""
    import ctypes
    raiz = os.path.splitdrive(str(ruta))[0]
    if not raiz or raiz.startswith("\\\\"):
        return False
    return ctypes.windll.kernel32.GetDriveTypeW(raiz + "\\") == 3      # DRIVE_FIXED


def _a_la_papelera(ruta):
    """Lo manda a la Papelera de Windows, sin preguntar nada en pantalla (la pagina ya pregunto).
    `SHFileOperationW` con FOF_ALLOWUNDO es lo que usa el Explorador al apretar Supr."""
    import ctypes
    from ctypes import wintypes

    class OP(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", ctypes.c_void_p), ("pTo", ctypes.c_void_p),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_void_p)]

    desde = ctypes.create_unicode_buffer(str(ruta) + "\0")       # termina con DOS ceros
    # FO_DELETE = 3 · ALLOWUNDO 0x40 · NOCONFIRMATION 0x10 · SILENT 0x4 · NOERRORUI 0x400
    op = OP(None, 3, ctypes.addressof(desde), None, 0x40 | 0x10 | 0x4 | 0x400, False, None, None)
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r or op.fAnyOperationsAborted:
        raise OSError(f"código {r}")


def a_la_papelera(cwd, sid, ident, _mandar=None, _hay_papelera=None):
    """Manda a la papelera un archivo DE ESTA CHARLA. Los `_` son para las pruebas."""
    _mandar = _mandar or _a_la_papelera
    _hay_papelera = _hay_papelera or _disco_con_papelera
    ruta = buscar(cwd, sid, ident)
    if not ruta or ruta.suffix.lower() not in EXT:
        return {"ok": False, "error": "Ese archivo no es de esta charla."}
    if not _hay_papelera(ruta):
        return {"ok": False, "error": "Ese disco no tiene papelera: no lo borro para siempre. "
                                      "Si de verdad querés, borralo a mano."}
    try:
        _mandar(ruta)
    except OSError as err:
        return {"ok": False, "error": f"Windows no lo pudo mandar a la papelera ({str(err)[:60]})."}
    if ruta.exists():
        return {"ok": False, "error": "Windows dijo que sí, pero el archivo sigue ahí."}
    return {"ok": True}


# --- Las rutas -------------------------------------------------------------------------------

# Un SVG abierto aparte es una pagina: con esto no puede correr nada adentro.
CAB_SVG = {"Content-Security-Policy": "sandbox"}


def _de_otro_sitio(cab):
    """Candado 3, segunda mitad: si el navegador dice de donde viene el pedido (`Sec-Fetch-Site`),
    tiene que ser de aca mismo. Sin esto, otra pagina podria embeber `<img src=…/vista/crudo>`:
    un `<img>` no manda `Origin`, asi que la puerta de la terminal sola no lo ve."""
    sitio = cab.get("sec-fetch-site", "")
    return "el pedido viene de otra pagina" if sitio and sitio not in ("same-origin", "none") else ""


def crear_router(origenes_extra=(), anfitriones_extra=()):
    """Las rutas. Los `extra` son para las pruebas, que lo sirven desde un servidor aparte."""
    r = APIRouter()

    def puerta(pedido):
        motivo = _puerta(pedido.headers, "", origenes_extra, anfitriones_extra, pide_llave=False)
        return motivo or _de_otro_sitio(pedido.headers)

    def no(motivo, cod=403):
        return JSONResponse({"ok": False, "error": motivo}, status_code=cod)

    @r.get("/vista/lista")
    def vista_lista(request: Request, cwd: str = "", sid: str = ""):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        if not SID_OK.fullmatch(sid or ""):
            return JSONResponse({"ok": True, "archivos": [], "sin_charla": True},
                                headers={"Cache-Control": "no-store"})
        return JSONResponse({"ok": True, "archivos": lista(cwd, sid)},
                            headers={"Cache-Control": "no-store"})

    @r.get("/vista/crudo")
    def vista_crudo(request: Request, cwd: str = "", sid: str = "", id: str = ""):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        ruta = buscar(cwd, sid, id)
        if not ruta or ruta.suffix.lower() not in EXT:
            return no("ese archivo no es de esta charla", 404)
        cab = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if ruta.suffix.lower() == ".svg":
            cab.update(CAB_SVG)
        # Sin `filename`: asi va "inline" y el navegador lo MUESTRA (un PDF en su visor) en vez
        # de bajarlo.
        return FileResponse(ruta, headers=cab)

    async def cuerpo(pedido):
        try:
            d = await pedido.json()
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}

    def charla(d):
        sid = str(d.get("sid", ""))
        return str(d.get("cwd", "")), sid if SID_OK.fullmatch(sid) else "", str(d.get("id", ""))

    @r.post("/vista/quitar")
    async def vista_quitar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        cwd, sid, ident = charla(await cuerpo(request))
        return quitar(cwd, sid, ident) if sid else {"ok": False, "error": "Sin charla."}

    @r.post("/vista/devolver")
    async def vista_devolver(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        _, sid, ident = charla(await cuerpo(request))
        return devolver(sid, ident) if sid else {"ok": False, "error": "Sin charla."}

    @r.post("/vista/papelera")
    async def vista_papelera(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        cwd, sid, ident = charla(await cuerpo(request))
        return a_la_papelera(cwd, sid, ident) if sid else {"ok": False, "error": "Sin charla."}

    @r.get("/estaticos/vista.js")
    def estatico_vista():
        return FileResponse(ESTATICOS / "vista.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-store"})

    return r


router = crear_router()
