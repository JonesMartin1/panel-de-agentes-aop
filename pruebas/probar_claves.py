"""Prueba del 🔑 "Pegar una clave" (`app/voz/claves.py`), sin tocar las claves reales.

    python -m pruebas.probar_claves            # los chequeos
    python -m pruebas.probar_claves --mutar    # rompe cada candado y exige que se note

Lo que importa cuidar:
  · que la clave NUNCA vuelva en una respuesta (ni al guardar ni al listar);
  · que el nombre no pueda escaparse de la carpeta (`../`, rutas absolutas);
  · que no se pise una clave sin confirmarlo;
  · que otra pagina no pueda usar las rutas (la puerta de la terminal).
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import rutas
from app.voz import claves

OK, MAL = [], []
SECRETO = "Sup3r-S3creta!#"


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {detalle}")


def correr():
    OK.clear(); MAL.clear()
    tmp = Path(tempfile.mkdtemp(prefix="claves_"))
    carpeta = tmp / "claves"
    rutas.CLAVES = carpeta

    # --- nombres
    chequeo("nombre con espacios y tildes", claves.limpiar_nombre("Panel Admin (Ana) ñandú")
            == "panel-admin-ana-nandu", claves.limpiar_nombre("Panel Admin (Ana) ñandú"))
    for malo in ("../../etc/passwd", "..\\..\\Windows\\x", "C:\\Users\\x", "/abs/x"):
        n = claves.limpiar_nombre(malo)
        chequeo(f"no se escapa: {malo}", n and "/" not in n and "\\" not in n
                and ":" not in n and not n.startswith("."), n)
    chequeo("nombre vacío", claves.limpiar_nombre("  ..  ") == "")

    # --- guardar
    r = claves.guardar("Panel admin", SECRETO + "\r\n")
    chequeo("guarda", r.get("ok") and r.get("nombre") == "panel-admin", r)
    chequeo("la respuesta no trae la clave", SECRETO not in str(r), r)
    f = carpeta / "panel-admin"
    chequeo("queda en su archivo, sin el salto del final",
            f.exists() and f.read_text(encoding="utf-8") == SECRETO)
    chequeo("ruta mostrable", r.get("ruta") == "~/.claude/claves/panel-admin", r)
    r = claves.guardar("../../afuera", "x")
    chequeo("un ../ cae adentro de la carpeta", r.get("ok") and (carpeta / r["nombre"]).exists()
            and not (tmp / "afuera").exists(), r)

    # --- no pisar sin querer
    r = claves.guardar("panel admin", "otra")
    chequeo("ya existe: no pisa", not r.get("ok") and r.get("existe")
            and f.read_text(encoding="utf-8") == SECRETO, r)
    r = claves.guardar("panel admin", "otra", reemplazar=True)
    chequeo("con reemplazar: pisa", r.get("ok") and f.read_text(encoding="utf-8") == "otra", r)
    chequeo("sin clave se rechaza", not claves.guardar("x", "   ").get("ok"))
    chequeo("sin nombre se rechaza", not claves.guardar("", "x").get("ok"))
    chequeo("no quedan temporales", not list(carpeta.glob("*.tmp-guardando")))

    # --- por HTTP, con la puerta
    app = FastAPI(); app.include_router(claves.crear_router())
    c = TestClient(app, base_url="http://127.0.0.1:8750")
    r = c.post("/claves/guardar", json={"nombre": "por http", "valor": SECRETO})
    chequeo("guardar por HTTP", r.status_code == 200 and r.json().get("ok"), r.text)
    chequeo("la respuesta HTTP no trae la clave", SECRETO not in r.text, r.text)
    r = c.get("/claves")
    chequeo("lista solo nombres", r.status_code == 200 and "por-http" in r.json().get("nombres", [])
            and SECRETO not in r.text and "otra" not in r.text, r.text)
    r = c.post("/claves/guardar", json={"nombre": "mala", "valor": "x"},
               headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede guardar", r.status_code == 403 and not (carpeta / "mala").exists(),
            r.status_code)
    r = c.get("/claves", headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede listar", r.status_code == 403, r.status_code)
    r = c.post("/claves/guardar", json={"nombre": "host", "valor": "x"}, headers={"host": "atacante.com"})
    chequeo("un nombre que no es de esta máquina no pasa", r.status_code == 403, r.status_code)
    chequeo("con Origin del panel: pasa", c.post("/claves/guardar", json={"nombre": "orig", "valor": "x"},
            headers={"origin": "http://127.0.0.1:8750"}).json().get("ok"))
    chequeo("sirve claves.js", c.get("/estaticos/claves.js").status_code == 200)
    return not MAL


def mutaciones():
    """Rompe cada candado y exige que la prueba se ponga roja."""
    orig_guardar = claves.guardar
    casos = {
        "sin puerta": lambda: setattr(claves, "_puerta", lambda *a, **k: ""),
        "devuelve la clave": lambda: setattr(claves, "guardar",
                                             lambda n, v, rr=False: {**orig_guardar(n, v, rr), "valor": v}),
        "nombre sin limpiar": lambda: setattr(claves, "limpiar_nombre", lambda n: str(n).strip()),
        "pisa sin preguntar": lambda: setattr(claves, "guardar",
                                              lambda n, v, rr=False: orig_guardar(n, v, True)),
    }
    cazadas = 0
    for nombre, romper in casos.items():
        guardado = {k: getattr(claves, k) for k in ("_puerta", "guardar", "limpiar_nombre")}
        romper()
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                paso = correr()
            except Exception:
                paso = False
        for k, v in guardado.items():
            setattr(claves, k, v)
        print(f"  mutación «{nombre}»: {'CAZADA' if not paso else 'NO SE NOTÓ ✗'}")
        cazadas += not paso
    return cazadas == len(casos)


if __name__ == "__main__":
    real = rutas.CLAVES
    try:
        bien = correr()
        print(f"claves: {len(OK)} bien, {len(MAL)} mal")
        if "--mutar" in sys.argv:
            bien = mutaciones() and bien
    finally:
        rutas.CLAVES = real
    sys.exit(0 if bien else 1)
