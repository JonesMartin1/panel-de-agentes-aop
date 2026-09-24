"""Chequeos puros del estado de avance del Estudio, sin cargar Whisper ni tocar videos."""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import panel  # noqa: E402


def main():
    from app.nucleo import core

    nombre = "_prueba_progreso_video.mp4"
    panel._ESTUDIO_PROGRESOS.pop(nombre, None)
    assert panel._estudio_progreso_empezar(nombre) is True
    assert panel._estudio_progreso_empezar(nombre) is False, "una recarga no duplica Whisper"
    panel._estudio_progreso_poner(nombre, 61, "Separando las frases…", en_curso=True)
    estado = panel._estudio_progreso(nombre)
    assert estado["pct"] == 61 and estado["en_curso"] is True
    assert estado["paso"] == "Separando las frases…"
    panel._estudio_progreso_poner(nombre, 100, "Listo para editar", en_curso=False)
    assert panel._estudio_progreso(nombre)["en_curso"] is False
    panel._ESTUDIO_PROGRESOS.pop(nombre, None)

    # El recorrido del Estudio no termina al transcribir: Gemini tiene que mirar el
    # video y el análisis se guarda antes de habilitarlo para editar.
    import asyncio
    from app.nucleo import analizar_gemini, entrantes
    ruta_original = panel._estudio_ruta
    procesar_original = core.procesar_archivo
    analizar_original = analizar_gemini.analizar
    guardar_texto_original = entrantes.poner_transcripcion
    guardar_analisis_original = entrantes.poner_analisis
    llamadas = []
    try:
        panel._estudio_ruta = lambda _nombre: Path("video_prueba.mp4")
        def procesar_falso(_ruta, progreso=None):
            progreso(100, "Fragmentos listos")
            return ({"transcripcion": "hola", "segmentos": [{"inicio": 0, "fin": 1, "texto": "hola"}],
                     "frames": [], "frames_tiempos": []}, Path("resultados/prueba"))
        core.procesar_archivo = procesar_falso
        entrantes.poner_transcripcion = lambda *args: llamadas.append("texto") or True
        analizar_gemini.analizar = lambda datos: llamadas.append("analisis") or {"resumen": "ok"}
        entrantes.poner_analisis = lambda *args: llamadas.append("guardar_analisis") or True
        respuesta = asyncio.run(panel.estudio_transcribir(nombre))
        assert respuesta["ok"] is True and respuesta["tiene_analisis"] is True
        assert llamadas == ["texto", "analisis", "guardar_analisis"]
        assert panel._estudio_progreso(nombre)["paso"] == "Texto y análisis listos para editar"
    finally:
        panel._estudio_ruta = ruta_original
        core.procesar_archivo = procesar_original
        analizar_gemini.analizar = analizar_original
        entrantes.poner_transcripcion = guardar_texto_original
        entrantes.poner_analisis = guardar_analisis_original
        panel._ESTUDIO_PROGRESOS.pop(nombre, None)

    # El callback es opcional: los tres caminos existentes de transcripción conservan
    # su llamada de un solo argumento.
    assert "progreso" in inspect.signature(core.procesar_archivo).parameters
    print("OK: progreso del Estudio")


if __name__ == "__main__":
    main()
