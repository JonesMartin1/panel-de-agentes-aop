"""Pegar una CONTRASEÑA desde el panel sin que pase por la charla (2026-11-26).

Pedido de Martin: "me parece importante que pueda pegar las contraseñas aca en el panel".
Hasta hoy, para darle una clave a una sesion habia que escribirla en el chat, y eso la deja:
  · en la transcripcion de la charla, que se guarda diez años (`cleanupPeriodDays`);
  · en lo que viaja al modelo en cada turno.

El 🔑 de la caja de escribir (lo dibuja `app/estaticos/claves.js`, el mismo en la compu y en
el celular) manda la clave ACA, que la escribe en un archivo propio dentro de
`~/.claude/claves/`, y a la caja de escribir vuelve solo el NOMBRE y la ruta. La sesion la
lee del archivo cuando la necesita.

⭐ Reglas:
  · El valor no vuelve NUNCA en una respuesta, ni se imprime, ni se lista. `/claves` da
    solo los nombres.
  · Las rutas pasan por la misma puerta que la terminal (`terminales._puerta`, sin llave):
    otra pagina abierta en el Chrome de Martin no puede mandarle claves al panel.
  · El nombre se reduce a letras, numeros, `-`, `_` y `.`: nunca puede escaparse de la
    carpeta ni pisar un archivo ajeno.
  · Pisar una clave que ya existe pide confirmarlo (`reemplazar`).
Se prueba con `python -m pruebas.probar_claves --mutar`.
"""

import os
import re
import threading
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app import rutas
from app.voz.terminales import _puerta

MAX_NOMBRE = 60
MAX_VALOR = 8000

_CANDADO = threading.Lock()


def _carpeta():
    # Se lee de `rutas` en cada uso para que las pruebas puedan apuntarla a otro lado.
    return rutas.CLAVES


def limpiar_nombre(nombre):
    """'Panel Admin (Ana)' -> 'panel-admin-ana'. Vacio si no queda nada usable."""
    t = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9._-]+", "-", t.lower()).strip("-._")
    t = re.sub(r"-{2,}", "-", t)[:MAX_NOMBRE].strip("-._")
    return t


def ruta_mostrable(nombre):
    return f"~/.claude/claves/{nombre}"


def nombres():
    try:
        return sorted(p.name for p in _carpeta().iterdir() if p.is_file())
    except OSError:
        return []


def guardar(nombre, valor, reemplazar=False):
    n = limpiar_nombre(nombre)
    if not n:
        return {"ok": False, "error": "Ponele un nombre (letras o números)."}
    v = str(valor if valor is not None else "").strip("\r\n")
    if not v.strip():
        return {"ok": False, "error": "Falta la clave."}
    if len(v) > MAX_VALOR:
        return {"ok": False, "error": "Es demasiado larga para ser una clave."}
    carpeta = _carpeta()
    destino = carpeta / n
    with _CANDADO:
        if destino.exists() and not reemplazar:
            return {"ok": False, "existe": True, "nombre": n,
                    "error": f"Ya hay una clave «{n}». Tocá Reemplazar para pisarla."}
        carpeta.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(n + ".tmp-guardando")
        tmp.write_text(v, encoding="utf-8", newline="")
        os.replace(tmp, destino)          # de un saque: nunca queda media clave
    return {"ok": True, "nombre": n, "ruta": ruta_mostrable(n)}


# --- Las rutas -------------------------------------------------------------------------------

def crear_router(origenes_extra=(), anfitriones_extra=()):
    """Las rutas. Los `extra` son para las pruebas, que lo sirven desde un servidor aparte."""
    r = APIRouter()

    def puerta(pedido):
        return _puerta(pedido.headers, "", origenes_extra, anfitriones_extra, pide_llave=False)

    def no(motivo):
        return JSONResponse({"ok": False, "error": motivo}, status_code=403)

    @r.get("/estaticos/claves.js")
    def claves_js():
        # El 🔑 de la caja de escribir: lo cargan `/sesiones` y el celular.
        return FileResponse(rutas.ESTATICOS / "claves.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-store"})

    @r.get("/claves")
    def claves_lista(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        return JSONResponse({"ok": True, "nombres": nombres()},
                            headers={"Cache-Control": "no-store"})

    @r.post("/claves/guardar")
    async def claves_guardar(request: Request):
        motivo = puerta(request)
        if motivo:
            return no(motivo)
        try:
            d = await request.json()
        except ValueError:
            d = {}
        if not isinstance(d, dict):
            d = {}
        res = guardar(str(d.get("nombre", "")), d.get("valor"), bool(d.get("reemplazar")))
        return JSONResponse(res, headers={"Cache-Control": "no-store"})

    return r


router = crear_router()
