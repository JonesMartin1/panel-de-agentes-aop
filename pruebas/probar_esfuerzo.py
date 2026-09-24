"""El esfuerzo con que piensa cada sesión (`--effort` del CLI), sin tocar Claude.

Pedido de Martín (2026-08-18), la perilla hermana de la del modelo: bajo contesta
rápido y barato, máximo piensa largo. Acá se prueba la parte que se puede probar sin
gastar un turno de verdad: que se guarde, que se lea, que un nivel inventado no entre,
que la sesión que nace de compactar lo herede, y sobre todo que el flag salga en la
línea de comando SOLO cuando se eligió algo — vacío es "el de fábrica del CLI".

Correr con:  python -m pruebas.probar_esfuerzo   (no necesita el panel prendido)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    from app.voz import sesiones_movil as sm

    # El archivo de ajustes se desvía a uno de mentira: esta prueba NO puede tocar
    # lo que Martín tenga elegido de verdad.
    tmp = Path(tempfile.mkdtemp()) / "ajustes.json"
    sm.AJUSTES_SESIONES = tmp

    # --- Guardar y leer -------------------------------------------------------
    revisar("sin elegir nada, es el de fábrica (vacío)", sm.esfuerzo_de("ses-1"), "")
    revisar("guardar 'high' devuelve 'high'", sm.poner_esfuerzo("ses-1", "high"), "high")
    revisar("y se lee de vuelta", sm.esfuerzo_de("ses-1"), "high")
    revisar("otra sesión sigue en el de fábrica", sm.esfuerzo_de("ses-2"), "")

    # --- Lo que no existe no entra -------------------------------------------
    revisar("un nivel inventado cae al de fábrica",
            sm.poner_esfuerzo("ses-1", "altísimo"), "")
    revisar("y queda guardado el de fábrica", sm.esfuerzo_de("ses-1"), "")

    # --- Los cinco niveles del CLI, más el vacío ------------------------------
    revisar("los niveles son los del CLI", list(sm.ESFUERZOS),
            ["", "low", "medium", "high", "xhigh", "max"])
    for nivel in ("low", "medium", "high", "xhigh", "max"):
        revisar(f"guarda '{nivel}'", sm.poner_esfuerzo("ses-3", nivel), nivel)

    # --- El modelo y el esfuerzo conviven en el mismo archivo -----------------
    sm.poner_modelo("ses-4", "sonnet")
    sm.poner_esfuerzo("ses-4", "max")
    revisar("el modelo no se pisa con el esfuerzo", sm.modelo_de("ses-4"), "sonnet")
    revisar("ni el esfuerzo con el modelo", sm.esfuerzo_de("ses-4"), "max")
    guardado = json.loads(tmp.read_text(encoding="utf-8"))
    revisar("los dos viven bajo la misma sesión", guardado["ses-4"],
            {"modelo": "sonnet", "esfuerzo": "max"})

    # --- Compactar hereda las dos perillas ------------------------------------
    sm._heredar_modelo("ses-4", "ses-4-nueva")
    revisar("la sesión compactada hereda el modelo", sm.modelo_de("ses-4-nueva"), "sonnet")
    revisar("y también el esfuerzo", sm.esfuerzo_de("ses-4-nueva"), "max")

    # --- ⭐ El flag en la línea de comando -------------------------------------
    # Lo que de verdad importa: sin elegir nada NO puede aparecer --effort (eso le
    # cambiaría el comportamiento a todas las sesiones sin que nadie lo pidiera).
    lineas = []
    sm.poner_esfuerzo("ses-5", "low")

    class ProcesoFalso:
        def __init__(self, cmd, **kw):
            lineas.append(cmd)
            raise RuntimeError("hasta acá llega la prueba: no arrancamos Claude")

    original = sm.subprocess.Popen
    sm.subprocess.Popen = ProcesoFalso
    try:
        for sid in ("ses-5", "ses-2"):
            try:
                sm.mandar(str(Path.cwd()), sid, "hola")
            except Exception:
                pass
    finally:
        sm.subprocess.Popen = original

    con, sin = (lineas + [[], []])[:2]
    revisar("con esfuerzo elegido, el flag va en la línea",
            ["--effort", "low"] == con[con.index("--effort"):con.index("--effort") + 2]
            if "--effort" in con else False, True)
    revisar("sin elegir nada, el flag NO aparece", "--effort" in sin, False)

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print(f"todo bien ({len(fallas) or 0} fallas)")


if __name__ == "__main__":
    main()
