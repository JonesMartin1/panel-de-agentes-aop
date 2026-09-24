"""El paquete para una sesión conserva cortes, tiempos, análisis y rutas locales."""

import tempfile
from pathlib import Path

import panel
from app.nucleo import entrantes


FALLAS = []


def chequear(texto, condicion, detalle=""):
    print(("  OK   " if condicion else "  FALLA ") + texto +
          ((" -> " + detalle) if detalle else ""))
    if not condicion:
        FALLAS.append(texto)


def main():
    originales = {
        "estudio": panel.ESTUDIO,
        "ruta": panel._estudio_ruta,
        "unir": panel._unir_videos,
        "miniaturas": panel._miniaturas_video,
        "duracion": entrantes.duracion,
        "segmentos": entrantes.segmentos_de,
        "analisis": entrantes.analisis_de,
        "armado": entrantes.analisis_armado,
    }
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            original = base / "original.mp4"
            original.write_bytes(b"video de prueba")
            panel.ESTUDIO = base / "salidas"
            panel._estudio_ruta = lambda nombre: original if nombre == "original.mp4" else None
            entrantes.duracion = lambda ruta: 40.0
            entrantes.segmentos_de = lambda nombre: [
                {"inicio": 10, "fin": 12, "texto": "primera frase"},
                {"inicio": 30, "fin": 32, "texto": "segunda frase"},
            ]
            entrantes.analisis_de = lambda nombre: {
                "resumen": "Resumen automático del original",
                "transcripcion_visual": [
                    {"segundo": 11, "descripcion": "se abre una puerta"},
                    {"segundo": 31, "descripcion": "aparece la calle"},
                ],
            }
            entrantes.analisis_armado = lambda pistas, perfil: {
                "texto": "Análisis específico de los cortes"
            }

            def unir(pistas, destino):
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(b"armado")
                return True, ""

            def miniaturas(ruta, destino, cantidad=8):
                destino.write_bytes(b"mosaico")
                return True, ""

            panel._unir_videos = unir
            panel._miniaturas_video = miniaturas
            paquete = panel._preparar_paquete_estudio([
                {"archivo": "original.mp4", "ini": 10, "fin": 15},
                {"archivo": "original.mp4", "ini": 30, "fin": 35},
            ], proyecto="Campaña", perfil="generico")

            chequear("prepara el paquete", paquete.get("ok"), str(paquete))
            chequear("deja el video armado", Path(paquete.get("ruta_medio", "")).is_file())
            chequear("deja un mosaico visual", Path(paquete.get("ruta_mosaico", "")).is_file())
            ficha = Path(paquete.get("ruta_contexto", ""))
            chequear("deja una ficha legible", ficha.is_file())
            texto = ficha.read_text(encoding="utf-8") if ficha.is_file() else ""
            chequear("recalcula la primera frase sobre el armado",
                     "[00:00–00:02] primera frase" in texto)
            chequear("recalcula la segunda frase después del primer corte",
                     "[00:05–00:07] segunda frase" in texto)
            chequear("recalcula también la lectura visual",
                     "[00:01] se abre una puerta" in texto and
                     "[00:06] aparece la calle" in texto)
            chequear("incluye el análisis específico ya guardado",
                     "Análisis específico de los cortes" in texto)
            chequear("conserva el origen exacto para poder verificarlo",
                     str(original.resolve()) in texto)
    finally:
        panel.ESTUDIO = originales["estudio"]
        panel._estudio_ruta = originales["ruta"]
        panel._unir_videos = originales["unir"]
        panel._miniaturas_video = originales["miniaturas"]
        entrantes.duracion = originales["duracion"]
        entrantes.segmentos_de = originales["segmentos"]
        entrantes.analisis_de = originales["analisis"]
        entrantes.analisis_armado = originales["armado"]

    html = Path("app/estaticos/estudio.html").read_text(encoding="utf-8")
    chequear("la pantalla ofrece el envío a Sesiones",
             "Pasar a una sesión" in html and "/movil/sesiones" in html)
    chequear("usa el envío común sin tocar la conversación por otro camino",
             "fetch('/movil/mandar'" in html and "segundo_plano" in html)
    chequear("no manda antes de que el paquete esté listo",
             html.index("/estudio/preparar-sesion") < html.index("fetch('/movil/mandar'"))

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d" % len(FALLAS)))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
