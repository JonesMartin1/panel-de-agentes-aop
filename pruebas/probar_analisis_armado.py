"""El análisis pedido para un armado debe volver al abrir la misma fila."""

import tempfile
from pathlib import Path

from app.nucleo import entrantes


def ok(condicion, texto):
    print(("  OK   " if condicion else "  FALLA ") + texto)
    return condicion


def main():
    fallas = []
    original = entrantes.ESTUDIO_ANALISIS_ARMADOS
    pistas = [{"archivo": "reunion.ogg", "ini": 3.0, "fin": 40.0}]
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            entrantes.ESTUDIO_ANALISIS_ARMADOS = Path(carpeta) / "analisis.json"
            clave = entrantes.guardar_analisis_armado(pistas, "ventas", "Resumen guardado", "Texto dicho")
            if not ok(bool(clave), "el análisis del armado se guarda"):
                fallas.append("guardar")

            item = entrantes.analisis_armado(pistas, "ventas")
            if not ok(item and item["texto"] == "Resumen guardado" and item["dicho"] == "Texto dicho",
                      "la misma fila y el mismo análisis recuperan el resultado"):
                fallas.append("recuperar")

            otro = entrantes.analisis_armado([{**pistas[0], "fin": 41.0}], "ventas")
            if not ok(otro is None, "un recorte distinto no muestra un análisis viejo"):
                fallas.append("recorte")

            perfil_distinto = entrantes.analisis_armado(pistas, "reuniones")
            if not ok(perfil_distinto is None, "cada tipo de análisis conserva el suyo"):
                fallas.append("perfil")
    finally:
        entrantes.ESTUDIO_ANALISIS_ARMADOS = original

    html = Path("app/estaticos/estudio.html").read_text(encoding="utf-8")
    if not ok("cargarAnalisisGuardado" in html and "/estudio/analizar/guardado" in html,
              "la pantalla vuelve a pedir el análisis guardado al abrir la fila"):
        fallas.append("pantalla")
    if not ok("guardado" in html and "#perfil').onchange" in html,
              "cambiar el tipo de análisis recupera su resultado correspondiente"):
        fallas.append("selector")

    if fallas:
        raise SystemExit("Fallaron: " + ", ".join(fallas))
    print("\nAnálisis del armado: todo bien.")


if __name__ == "__main__":
    main()
