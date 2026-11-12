"""Los ENLACES Y ARCHIVOS importantes de cada carpeta (2026-11-11).

Pedido de Martin, mirando la columna derecha de una charla: "me gustaria que aca pudiera poner
links y archivos importantes". Es una lista por carpeta (la del proyecto de la charla), que se
ve igual en la compu y en el celular porque la dibuja `entorno.js`, la pieza que comparten.

  · Un ENLACE (http/https) se abre en una pestaña nueva: eso lo hace la pagina sola.
  · Un ARCHIVO o una CARPETA se abre EN LA COMPU, con el programa que Windows tenga para ese
    tipo (`os.startfile`), aunque el toque venga del celular.
  · No se copia nada: se guarda la ruta. Si el archivo se mueve o se borra, la fila lo avisa.

⭐⭐ Abrir un archivo desde una pagina web es delicado, por dos motivos, y los dos estan
cubiertos aca:
  1. Otra pagina abierta en el Chrome de Martin podria intentar mandarle pedidos al panel.
     Todas las rutas pasan por la misma puerta que la terminal (`terminales._puerta`, sin
     llave): el nombre con el que llegaron tiene que ser de esta maquina y, si traen `Origin`,
     tiene que ser el del propio panel.
  2. "Abrir" un `.exe`, un `.bat` o un acceso directo es EJECUTARLO. Esos nunca se abren:
     se muestran marcados en el Explorador (`TIPOS_QUE_EJECUTAN`). Y solo se abre algo que ya
     esta en la lista, por su id: la ruta nunca viaja en el pedido de abrir.
Se prueba con `python -m pruebas.probar_fijados --mutar`.
"""

import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rutas import FIJADOS
from app.voz.terminales import _puerta

MAX_POR_CARPETA = 60
MAX_NOMBRE = 80

# Lo que Windows EJECUTA en vez de mostrar. Abrirlos desde una pagina seria correr un programa.
TIPOS_QUE_EJECUTAN = {
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
    ".wsh", ".msi", ".msp", ".msc", ".scr", ".hta", ".lnk", ".pif", ".cpl", ".reg", ".jar",
    ".py", ".pyw", ".url", ".appref-ms", ".application", ".gadget", ".inf", ".sys", ".dll",
    ".scf", ".ws", ".sct", ".chm", ".appx", ".msix", ".diagcab", ".settingcontent-ms",
}

_CANDADO = threading.Lock()


def _clave(cwd):
    """La carpeta como llave del archivo: misma carpeta escrita distinto = misma lista."""
    c = (cwd or "").strip().strip('"')
    return os.path.normcase(os.path.normpath(c)) if c else ""


def _llave(cwd, sid="", ambito="proyecto"):
    """Dónde vive la lista: la del PROYECTO (la carpeta) o la de UNA SESIÓN (2026-11-11, pedido
    de Martin: "un apartado para proyecto y otro para sesiones"). Las de sesión van con el
    prefijo `sesion:`, que ninguna ruta de Windows puede tener. Sin sid valido no hay lista
    de sesion (una charla que todavia no arranco no tiene identidad donde guardarse)."""
    if ambito == "sesion":
        s = (sid or "").strip()
        return "sesion:" + s if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", s) else ""
    return _clave(cwd)


def _leer():
    try:
        datos = json.loads(Path(FIJADOS).read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar(datos):
    FIJADOS.parent.mkdir(parents=True, exist_ok=True)
    tmp = FIJADOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FIJADOS)          # de un saque: un corte a mitad no deja el archivo roto


def _nombre_de_enlace(url):
    p = urlsplit(url)
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    tramo = next((t for t in p.path.split("/") if t), "")
    return (host + ("/" + tramo if tramo else ""))[:MAX_NOMBRE]


def interpretar(texto, cwd=""):
    """Lo que pegó Martin -> (tipo, destino, nombre) o (None, motivo).

    Acepta una direccion web, o una ruta de archivo/carpeta: absoluta, o relativa a la
    carpeta del proyecto. "Copiar como ruta" de Windows la trae entre comillas: se sacan.
    """
    t = (texto or "").strip().strip('"').strip("'").strip()
    if not t:
        return None, "Pegá un enlace o la ruta de un archivo."
    if "\n" in t or len(t) > 2000:
        return None, "Eso no parece un enlace ni una ruta."
    bajo = t.lower()
    if bajo.startswith(("http://", "https://")):
        if not urlsplit(t).netloc:
            return None, "Ese enlace está incompleto."
        return ("enlace", t, _nombre_de_enlace(t)), ""
    if bajo.startswith("www."):
        t = "https://" + t
        return ("enlace", t, _nombre_de_enlace(t)), ""
    if "://" in t or bajo.startswith(("javascript:", "data:", "file:", "mailto:")):
        return None, "Solo enlaces que empiecen con http:// o https://."
    ruta = Path(os.path.expandvars(os.path.expanduser(t)))
    if not ruta.is_absolute():
        if not cwd:
            return None, "Esa ruta no está completa."
        ruta = Path(cwd) / ruta
    try:
        ruta = ruta.resolve()
    except OSError:
        return None, "No entiendo esa ruta."
    if not ruta.exists():
        return None, "No encuentro ese archivo o carpeta."
    tipo = "carpeta" if ruta.is_dir() else "archivo"
    return (tipo, str(ruta), (ruta.name or str(ruta))[:MAX_NOMBRE]), ""


def lista(cwd, sid="", ambito="proyecto"):
    llave = _llave(cwd, sid, ambito)
    filas = _leer().get(llave, []) if llave else []
    salida = []
    for f in filas:
        f = dict(f)
        if f.get("tipo") in ("archivo", "carpeta"):
            f["existe"] = Path(f.get("destino", "")).exists()
        salida.append(f)
    return salida


def agregar(cwd, texto, nombre="", sid="", ambito="proyecto"):
    llave = _llave(cwd, sid, ambito)
    if not llave:
        return {"ok": False, "error": "Esta charla todavía no arrancó: guardalo en el proyecto."
                if ambito == "sesion" else "No sé de qué carpeta es."}
    r, motivo = interpretar(texto, cwd)
    if not r:
        return {"ok": False, "error": motivo}
    tipo, destino, auto = r
    nombre = (nombre or "").strip()[:MAX_NOMBRE] or auto
    with _CANDADO:
        datos = _leer()
        filas = datos.setdefault(llave, [])
        igual = next((f for f in filas
                      if (f.get("destino") == destino if tipo == "enlace"
                          else _clave(f.get("destino")) == _clave(destino))), None)
        if igual:
            return {"ok": True, "repetido": True, "item": igual}
        if len(filas) >= MAX_POR_CARPETA:
            return {"ok": False, "error": f"Ya hay {MAX_POR_CARPETA}: sacá alguno primero."}
        item = {"id": uuid.uuid4().hex[:10], "tipo": tipo, "destino": destino,
                "nombre": nombre, "ts": int(time.time())}
        filas.append(item)
        _guardar(datos)
    return {"ok": True, "item": item}


def quitar(cwd, ident, sid="", ambito="proyecto"):
    llave = _llave(cwd, sid, ambito)
    with _CANDADO:
        datos = _leer()
        filas = datos.get(llave, []) if llave else []
        quedan = [f for f in filas if f.get("id") != ident]
        if len(quedan) == len(filas):
            return {"ok": False, "error": "Ese ya no estaba."}
        if quedan:
            datos[llave] = quedan
        else:
            datos.pop(llave, None)
        _guardar(datos)
    return {"ok": True}


def _mostrar_en_explorador(ruta):
    subprocess.Popen(["explorer", "/select,", str(ruta)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def abrir(cwd, ident, sid="", ambito="proyecto", _abrir=None, _mostrar=None):
    """Abre en la compu un archivo o carpeta DE LA LISTA (por su id, nunca por ruta).

    Lo que Windows ejecutaria (`TIPOS_QUE_EJECUTAN`) no se abre: se muestra marcado en el
    Explorador. Los `_abrir`/`_mostrar` son para las pruebas, que no pueden abrir ventanas.
    """
    _abrir = _abrir or os.startfile
    _mostrar = _mostrar or _mostrar_en_explorador
    llave = _llave(cwd, sid, ambito)
    f = next((x for x in (_leer().get(llave, []) if llave else []) if x.get("id") == ident), None)
    if not f:
        return {"ok": False, "error": "Ese ya no está en la lista."}
    if f.get("tipo") not in ("archivo", "carpeta"):
        return {"ok": False, "error": "Los enlaces los abre la página."}
    ruta = Path(f.get("destino", ""))
    if not ruta.exists():
        return {"ok": False, "error": "Ese archivo ya no está ahí: se movió o se borró."}
    try:
        if ruta.is_file() and ruta.suffix.lower() in TIPOS_QUE_EJECUTAN:
            _mostrar(ruta)
            return {"ok": True, "como": "mostrado",
                    "aviso": "Es un programa: te lo marqué en el Explorador en vez de correrlo."}
        _abrir(str(ruta))
    except OSError as err:
        return {"ok": False, "error": f"Windows no lo pudo abrir: {str(err)[:80]}"}
    return {"ok": True, "como": "abierto"}


# --- Las rutas -------------------------------------------------------------------------------

def crear_router(origenes_extra=(), anfitriones_extra=()):
    """Las rutas. Los `extra` son para las pruebas, que lo sirven desde un servidor aparte."""
    r = APIRouter()

    def puerta(pedido):
        return _puerta(pedido.headers, "", origenes_extra, anfitriones_extra, pide_llave=False)

    def no(motivo):
        return JSONResponse({"ok": False, "error": motivo}, status_code=403)

    async def cuerpo(pedido):
        try:
            d = await pedido.json()
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}

    def donde(d):
        """cwd, sid y ambito de un pedido, como textos (`ambito` solo puede ser uno de dos)."""
        amb = "sesion" if str(d.get("ambito", "")) == "sesion" else "proyecto"
        return str(d.get("cwd", "")), str(d.get("sid", "")), amb

    @r.get("/fijados")
    def fijados_lista(request: Request, cwd: str = "", sid: str = ""):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        # `sesion` es null cuando la charla no tiene id: la pagina entonces no muestra ese apartado.
        ses = lista(cwd, sid, "sesion") if _llave(cwd, sid, "sesion") else None
        return JSONResponse({"ok": True, "proyecto": lista(cwd), "sesion": ses},
                            headers={"Cache-Control": "no-store"})

    @r.post("/fijados/agregar")
    async def fijados_agregar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        cwd, sid, amb = donde(d)
        return agregar(cwd, str(d.get("texto", "")), str(d.get("nombre", "")), sid, amb)

    @r.post("/fijados/quitar")
    async def fijados_quitar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        cwd, sid, amb = donde(d)
        return quitar(cwd, str(d.get("id", "")), sid, amb)

    @r.post("/fijados/abrir")
    async def fijados_abrir(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        d = await cuerpo(request)
        cwd, sid, amb = donde(d)
        return abrir(cwd, str(d.get("id", "")), sid, amb)

    return r


router = crear_router()
