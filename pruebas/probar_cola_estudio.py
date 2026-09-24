"""Chequeos de la cola compartida entre la página y los procesos de mensajería."""

import json
import tempfile
from pathlib import Path

from app.nucleo import entrantes


def ok(condicion, texto):
    print(("  OK   " if condicion else "  FALLA ") + texto)
    return condicion


def main():
    fallas = []
    original = entrantes.ESTUDIO_COLA
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            entrantes.ESTUDIO_COLA = Path(carpeta)
            ident = entrantes.cola_abrir("reunion.mp4", origen="whatsapp", de="Martín")
            item = entrantes.cola_listar()[0]
            if not ok(item["tipo"] == "video" and item["origen"] == "whatsapp",
                      "la llegada por WhatsApp entra a la cola como video"):
                fallas.append("llegada WhatsApp")

            entrantes.cola_actualizar(ident, pct=47, paso="Separando las frases…",
                                      archivo="2026-08-24_prueba.mp4")
            item = entrantes.cola_de_archivo("2026-08-24_prueba.mp4")
            if not ok(item and item["pct"] == 47 and item["paso"] == "Separando las frases…",
                      "la cola conserva el avance y enlaza el archivo del Estudio"):
                fallas.append("avance")

            entrantes.cola_terminar(ident, archivo="2026-08-24_prueba.mp4")
            item = entrantes.cola_listar()[0]
            if not ok(item["estado"] == "listo" and item["pct"] == 100,
                      "un trabajo terminado queda visible como confirmación"):
                fallas.append("final")
    finally:
        entrantes.ESTUDIO_COLA = original

    html = Path("app/estaticos/estudio.html").read_text(encoding="utf-8")
    if not ok('id="colaViva"' in html and "setInterval(cargarCola, 2000)" in html,
              "la pantalla tiene una cola visible que se actualiza en vivo"):
        fallas.append("pantalla")
    inicio_cola = html.index("function pintarCola()")
    fin_cola = html.index("async function cargarCola()", inicio_cola)
    if not ok("caja.style.display = 'block'" in html[inicio_cola:fin_cola],
              "cuando llega un trabajo la cola deja de estar oculta"):
        fallas.append("cola visible")
    if not ok("/estudio/cola" in html and "colaLocal" in html,
              "la subida desde la página aparece antes de que termine de llegar"):
        fallas.append("subida página")

    if fallas:
        raise SystemExit("Fallaron: " + ", ".join(fallas))
    print("\nCola del Estudio: todo bien.")


if __name__ == "__main__":
    main()
