"""Un audio nuevo sólo entra al Estudio cuando ya trae el análisis de Gemini."""

import json
import tempfile
from pathlib import Path

from app.nucleo import entrantes, procesar


def ok(condicion, texto):
    print(("  OK   " if condicion else "  FALLA ") + texto)
    return condicion


def main():
    fallas = []
    original_entrantes = entrantes.ESTUDIO_ENTRANTES
    original_cola = entrantes.ESTUDIO_COLA
    original_procesar = procesar.core.procesar_archivo
    original_analizar = procesar.analizar_gemini.analizar
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            entrada = raiz / "nota.ogg"
            entrada.write_bytes(b"audio de prueba")
            entrantes.ESTUDIO_ENTRANTES = raiz / "entrantes"
            entrantes.ESTUDIO_COLA = raiz / "cola"

            def falso_procesar(_ruta, progreso=None):
                if progreso:
                    progreso(50, "Transcribiendo…")
                return ({"transcripcion": "Hola, esta es una prueba.",
                         "segmentos": [{"inicio": 0, "fin": 2,
                                         "texto": "Hola, esta es una prueba."}]}, "")

            procesar.core.procesar_archivo = falso_procesar
            procesar.analizar_gemini.analizar = lambda _datos, perfil=None: {
                "resumen": "Gemini ya lo analizó."}
            procesar.procesar_a_texto(entrada, origen="disco", de="nota.ogg")

            fichas = list(entrantes.ESTUDIO_ENTRANTES.glob("*.json"))
            ficha = json.loads(fichas[0].read_text(encoding="utf-8")) if fichas else {}
            if not ok(len(fichas) == 1 and ficha.get("analisis", {}).get("resumen") ==
                      "Gemini ya lo analizó.",
                      "la copia nueva se guarda junto con el análisis de Gemini"):
                fallas.append("ficha completa")

            fila = entrantes.listar()
            if not ok(len(fila) == 1 and fila[0].get("tiene_analisis"),
                      "la bandeja recibe el audio como material listo"):
                fallas.append("bandeja lista")

            cola = entrantes.cola_listar()
            if not ok(cola and cola[0].get("estado") == "listo" and cola[0].get("pct") == 100,
                      "la cola termina sólo después de guardar texto y análisis"):
                fallas.append("cola")
    finally:
        entrantes.ESTUDIO_ENTRANTES = original_entrantes
        entrantes.ESTUDIO_COLA = original_cola
        procesar.core.procesar_archivo = original_procesar
        procesar.analizar_gemini.analizar = original_analizar

    panel = Path("panel.py").read_text(encoding="utf-8")
    webhook = Path("app/ingesta/webhook_wasender.py").read_text(encoding="utf-8")
    if not ok("threading.Thread(target=_estudio_procesar_subida" in panel and
              "procesar.procesar_a_texto(ruta, origen=\"disco\"" in panel,
              "la subida web usa el recorrido completo en segundo plano"):
        fallas.append("subida web")
    if not ok("analisis = analizar_gemini.analizar(datos)" in webhook and
              "segmentos=datos.get(\"segmentos\"), analisis=analisis" in webhook,
              "un audio mandado a Laura por WhatsApp también se guarda con Gemini"):
        fallas.append("WhatsApp Martín")

    if fallas:
        raise SystemExit("Fallaron: " + ", ".join(fallas))
    print("\nEntradas con Gemini: todo bien.")


if __name__ == "__main__":
    main()
