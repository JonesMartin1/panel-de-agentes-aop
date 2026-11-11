"""Subproyectos adentro de una carpeta (2026-11-10).

Pedido de Martin: en una carpeta donde conviven varios trabajos, poder ponerle a cada
charla una etiqueta (su subproyecto) y ver la bandeja agrupada por esa etiqueta, igual
en la compu y en el celular. Es SOLO una forma de ordenar la vista: no cambia la carpeta
de la charla, ni su memoria, ni nada de Claude.

Esta prueba no abre ningun navegador ni toca nada vivo: importa `panel.py`, apunta el
archivo de subproyectos a un temporal y le reemplaza el listado de charlas por uno de
mentira. Al final comprueba que el `subproyectos_sesiones.json` de verdad quedo igual.
El agrupado de las dos pantallas se prueba sacando la funcion de cada HTML y corriendola
con node.

    python -m pruebas.probar_subproyectos
    python -m pruebas.probar_subproyectos --mutar   # rompe cada regla y exige que se note
"""

import asyncio
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import panel                                              # noqa: E402
from app.voz import sesiones_movil                        # noqa: E402

BIEN, MAL = [], []


def probar(nombre, cond, detalle=""):
    (BIEN if cond else MAL).append(nombre)
    print(("  ok  " if cond else "  MAL ") + nombre + (f"   [{detalle}]" if detalle and not cond else ""))


class Pedido:
    """Lo minimo que el endpoint usa de un Request: `await request.json()`."""

    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


# Dos carpetas de mentira: una que va a tener subproyectos y otra que nunca.
FALSO = [
    {"proyecto": "CarpetaMezclada", "cwd": "D:/falso/mezclada",
     "sesiones": [{"id": "sid-a", "nombre": "Charla A", "ts": 3},
                  {"id": "sid-b", "nombre": "Charla B", "ts": 2},
                  {"id": "sid-c", "nombre": "Charla C", "ts": 1}]},
    {"proyecto": "CarpetaLisa", "cwd": "D:/falso/lisa",
     "sesiones": [{"id": "sid-x", "nombre": "Charla X", "ts": 5},
                  {"id": "sid-y", "nombre": "Charla Y", "ts": 4}]},
]


def asignar(sid, sub):
    return asyncio.run(panel.movil_subproyecto(Pedido({"sid": sid, "subproyecto": sub})))


def listado():
    panel._SESIONES_ULTIMA["datos"] = None
    return {p["proyecto"]: p for p in panel.movil_sesiones()["proyectos"]}


def correr_js(fuente, nombre_func, filas):
    """Saca `function <nombre>(...){...}` del HTML y la corre con node sobre `filas`."""
    m = re.search(r"function " + nombre_func + r"\(filas\)\{.*?\n\}", fuente, re.S)
    if not m:
        return "NO ESTA"
    prog = m.group(0) + "\nconsole.log(JSON.stringify(" + nombre_func + "(" + json.dumps(filas) + ")));"
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(r.stdout) if r.returncode == 0 else "FALLO: " + r.stderr[:200]


def corrida(mutacion=None):
    BIEN.clear(); MAL.clear()
    real = panel.SUBPROYECTOS_SESIONES
    real_antes = real.read_bytes() if real.exists() else None

    tmp = Path(tempfile.mkdtemp(prefix="subproy_"))
    original = {"sid-de-otra-carpeta": "Algo que ya estaba"}
    texto_original = json.dumps(original, ensure_ascii=False, indent=1)
    archivo = tmp / "subproyectos_sesiones.json"
    archivo.write_text(texto_original, encoding="utf-8")

    viejos = (panel.SUBPROYECTOS_SESIONES, sesiones_movil.listar, panel._sesion_de_laura,
              panel._subproyectos)
    panel.SUBPROYECTOS_SESIONES = archivo
    sesiones_movil.listar = lambda: copy.deepcopy(FALSO)
    panel._sesion_de_laura = lambda: None
    if mutacion == "no-lee-lo-guardado":
        panel._subproyectos = lambda: {}
    try:
        print("\n--- Sin ningun subproyecto, la lista es la de siempre ---")
        antes = listado()
        probar("ninguna charla trae el campo `sub`",
               not any("sub" in s for p in antes.values() for s in p["sesiones"]))

        print("\n--- Asignar ---")
        r = asignar("sid-a", "  Descalzo  ")
        probar("el servidor contesta ok", r.get("ok") is True, str(r))
        asignar("sid-b", "Migración")
        d = listado()
        sub = {s["id"]: s.get("sub") for s in d["CarpetaMezclada"]["sesiones"]}
        probar("la charla A queda en Descalzo (sin espacios de sobra)", sub["sid-a"] == "Descalzo", str(sub))
        probar("la charla B queda en Migración", sub["sid-b"] == "Migración", str(sub))
        probar("la charla C sigue sin subproyecto", sub["sid-c"] is None, str(sub))

        print("\n--- Cambiar ---")
        asignar("sid-b", "Descalzo")
        d = listado()
        sub = {s["id"]: s.get("sub") for s in d["CarpetaMezclada"]["sesiones"]}
        probar("la charla B pasa a Descalzo", sub["sid-b"] == "Descalzo", str(sub))
        probar("el grupo Migración, sin charlas, ya no existe en el archivo",
               "Migración" not in archivo.read_text(encoding="utf-8"))

        print("\n--- ⭐ Es solo la vista: la carpeta de cada charla no se toca ---")
        probar("la carpeta sigue con su nombre real y su ruta",
               d["CarpetaMezclada"]["cwd"] == "D:/falso/mezclada")
        probar("las tres charlas siguen en su carpeta",
               [s["id"] for s in d["CarpetaMezclada"]["sesiones"]] == ["sid-a", "sid-b", "sid-c"])

        print("\n--- ⭐ Una carpeta donde nadie usa subproyectos queda IGUAL ---")
        probar("CarpetaLisa devuelve exactamente lo mismo que al principio",
               d["CarpetaLisa"] == antes["CarpetaLisa"])

        print("\n--- Sacar ---")
        asignar("sid-a", "")
        asignar("sid-b", "   ")
        d = listado()
        probar("sacadas las dos, nadie trae `sub`",
               not any("sub" in s for s in d["CarpetaMezclada"]["sesiones"]))
        probar("y la carpeta quedo como al principio",
               d["CarpetaMezclada"] == antes["CarpetaMezclada"])

        print("\n--- Basura: lo que entra se limpia ---")
        r = asignar("", "Algo")
        probar("sin sesion no guarda nada", r.get("ok") is False)
        r = asignar("nueva-123", "Algo")
        probar("una charla que todavia no existe no se etiqueta", r.get("ok") is False)
        r = asignar("sid-c", 'Un "nombre" ' + "x" * 80)
        probar("las comillas se van (viaja en atributos del HTML)", '"' not in r["subproyecto"])
        probar("se recorta a 40 letras", len(r["subproyecto"]) == 40, str(len(r["subproyecto"])))
        asignar("sid-c", "")

        print("\n--- ⭐ El archivo de datos queda como estaba ---")
        probar("el temporal volvio a su contenido original",
               json.loads(archivo.read_text(encoding="utf-8")) == original,
               archivo.read_text(encoding="utf-8"))
    finally:
        (panel.SUBPROYECTOS_SESIONES, sesiones_movil.listar, panel._sesion_de_laura,
         panel._subproyectos) = viejos
        panel._SESIONES_ULTIMA["datos"] = None
    real_despues = real.read_bytes() if real.exists() else None
    probar("el subproyectos_sesiones.json de verdad no se toco", real_antes == real_despues)

    print("\n--- Las dos pantallas agrupan igual ---")
    compu = (RAIZ / "app" / "estaticos" / "sesiones.html").read_text(encoding="utf-8")
    celu = panel.MOVIL_HTML
    if mutacion == "celu-agrupa-siempre":
        celu = celu.replace("if (!filas.some(s => s.sub)) return null;", "")
    planas = [{"id": "1"}, {"id": "2"}]
    mezcladas = [{"id": "1", "sub": "B"}, {"id": "2"}, {"id": "3", "sub": "A"}, {"id": "4", "sub": "B"}]
    for nombre, fuente, func in (("compu", compu, "agruparSub"), ("celu", celu, "agruparSubMovil")):
        probar(f"{nombre}: sin subproyectos no agrupa (lista de siempre)",
               correr_js(fuente, func, planas) is None)
        g = correr_js(fuente, func, mezcladas)
        orden = [(x["sub"], [f["id"] for f in x["filas"]]) for x in g] if isinstance(g, list) else g
        probar(f"{nombre}: nombrados en orden de aparicion y 'sin subproyecto' al final",
               orden == [["B", ["1", "4"]], ["A", ["3"]], ["", ["2"]]] or
               orden == [("B", ["1", "4"]), ("A", ["3"]), ("", ["2"])], str(orden))
    probar("compu: la bandeja usa la lista plana cuando no hay grupos",
           "const html = !grupos ? filas.map(filaCorreo).join('')" in compu)
    probar("celu: la bandeja usa la lista plana cuando no hay grupos",
           "const filas = !grupos ? lista.map(filaCorreo).join('')" in celu)
    probar("compu: el repintado no pisa una charla abierta",
           "function repintarBandeja(){ if (!activa && !verArchivo)" in compu)

    print(f"\n{len(BIEN)} bien, {len(MAL)} mal")
    for m in MAL:
        print("   MAL:", m)
    return not MAL


def main():
    if "--mutar" not in sys.argv:
        return 0 if corrida() else 1
    ok = corrida()
    cazadas = True
    for mut in ("no-lee-lo-guardado", "celu-agrupa-siempre"):
        print(f"\n===== mutacion: {mut} (tiene que FALLAR) =====")
        if corrida(mut):
            print(f"!!! la mutacion {mut} paso: el chequeo es un adorno")
            cazadas = False
        else:
            print(f"--> cazada: {mut}")
    print("\nRESULTADO:", "ok" if ok and cazadas else "MAL")
    return 0 if ok and cazadas else 1


if __name__ == "__main__":
    sys.exit(main())
