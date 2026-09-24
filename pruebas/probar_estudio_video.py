"""Prueba real del Estudio de video: guardar, recortar y pegar con ffmpeg."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import panel  # noqa: E402
from app.nucleo import analizar_gemini, entrantes  # noqa: E402
from app.rutas import ESTUDIO, ESTUDIO_ENTRANTES  # noqa: E402

CREATE_NO_WINDOW = 0x08000000
FALLAS = []


def chequear(que, ok, detalle=""):
    print(("  OK   " if ok else "  FALLA ") + que + (" -> " + detalle if detalle else ""))
    if not ok:
        FALLAS.append(que)


def video(destino, segundos, color, hz):
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=%s:s=360x640:d=%s:r=30" % (color, segundos),
        "-f", "lavfi", "-i", "sine=frequency=%s:duration=%s" % (hz, segundos),
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(destino)], check=True, creationflags=CREATE_NO_WINDOW)


def main():
    tmp = Path(__file__).with_name("_tmp_estudio_video")
    tmp.mkdir(exist_ok=True)
    guardados, salidas = [], []
    try:
        for i, (segundos, color, hz) in enumerate(((2.0, "blue", 440), (1.5, "red", 660))):
            original = tmp / ("video_%d.mp4" % i)
            video(original, segundos, color, hz)
            nombre = entrantes.guardar(
                original, origen="telegram", de="Martin Jones", texto="video %d" % i,
                segmentos=[{"inicio": 0, "fin": segundos, "texto": "video %d" % i}])
            guardados.append(nombre)
            chequear("guarda el video %d" % (i + 1), bool(nombre), nombre)

        fichas = {a["archivo"]: a for a in entrantes.listar()}
        chequear("la ficha lo distingue de un audio",
                 fichas[guardados[0]].get("tipo") == "video",
                 str(fichas[guardados[0]].get("tipo")))
        chequear("conserva la transcripcion con tiempos",
                 len(entrantes.segmentos_de(guardados[0])) == 1)
        # Un archivo viejo sin tiempos se completa en su misma ficha: no se duplica ni
        # se toca el video original.
        ficha = (ESTUDIO_ENTRANTES / guardados[0]).with_suffix(".json")
        d = json.loads(ficha.read_text(encoding="utf-8"))
        d["segmentos"] = []
        ficha.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tamano_antes = (ESTUDIO_ENTRANTES / guardados[0]).stat().st_size
        chequear("retranscribe una ficha vieja",
                 entrantes.poner_transcripcion(guardados[0], "texto recuperado", [
                     {"inicio": 0.2, "fin": 1.1, "texto": "texto recuperado"}]))
        chequear("la retranscripcion genera fragmentos editables",
                 entrantes.segmentos_de(guardados[0])[0]["texto"] == "texto recuperado")
        chequear("no toca ni duplica el video original",
                 (ESTUDIO_ENTRANTES / guardados[0]).stat().st_size == tamano_antes)
        visual = analizar_gemini.formato_legible({
            "transcripcion_visual": [
                {"segundo": 0, "descripcion": "aparece una caja"},
                {"segundo": 65, "descripcion": "Martín la abre"},
            ]})
        chequear("la interpretación visual queda ordenada por minuto",
                 "0:00 aparece una caja" in visual and "1:05 Martín la abre" in visual,
                 visual.replace("\n", " | "))
        mini_ok, mini_err = panel._miniaturas_video(ESTUDIO_ENTRANTES / guardados[0], tmp / "tira.jpg")
        chequear("la tira de miniaturas se genera desde el video", mini_ok, mini_err)
        chequear("y deja una imagen para navegar el video", (tmp / "tira.jpg").is_file(),
                 str((tmp / "tira.jpg").stat().st_size if (tmp / "tira.jpg").exists() else 0))
        entrantes.poner_analisis(guardados[0], {
            "transcripcion_visual": [{"segundo": 0.4, "descripcion": "aparece la caja"}]})
        analisis_api = panel.estudio_analisis(guardados[0])
        chequear("el análisis expone sus momentos para navegar",
                 analisis_api.get("visual") == [{"segundo": 0.4, "descripcion": "aparece la caja"}],
                 str(analisis_api.get("visual")))

        destino = ESTUDIO / "_prueba_video_unido.mp4"
        salidas.append(destino)
        ok, err = panel._unir_videos([
            {"archivo": guardados[0], "ini": 0.5, "fin": 1.5},
            {"archivo": guardados[1], "ini": 0, "fin": 1.0},
        ], destino)
        chequear("recorta y pega los videos", ok, err)
        chequear("el resultado dura dos segundos",
                 abs(entrantes.duracion(destino) - 2.0) < 0.2,
                 str(entrantes.duracion(destino)))
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(destino)],
            capture_output=True, text=True, check=True, creationflags=CREATE_NO_WINDOW)
        stream = json.loads(probe.stdout)["streams"][0]
        chequear("normaliza el resultado para que los clips sean compatibles",
                 (stream.get("width"), stream.get("height")) == (1280, 720), str(stream))

        audio = tmp / "solo_audio.wav"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "sine=duration=1", str(audio)],
                       check=True, creationflags=CREATE_NO_WINDOW)
        audio_guardado = entrantes.guardar(audio)
        guardados.append(audio_guardado)
        ok, err = panel._unir_videos([
            {"archivo": guardados[0]}, {"archivo": audio_guardado}],
            ESTUDIO / "_prueba_video_mezclado.mp4")
        chequear("no mezcla audio suelto dentro de un video", not ok and "todas" in err, err)
    finally:
        for nombre in guardados:
            if nombre:
                entrantes.borrar(nombre)
        for salida in salidas + [ESTUDIO / "_prueba_video_mezclado.mp4"]:
            salida.unlink(missing_ok=True)
        for f in tmp.glob("*"):
            f.unlink(missing_ok=True)
        tmp.rmdir()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d" % len(FALLAS)))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
