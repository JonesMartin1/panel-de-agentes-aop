"""Prueba del pegado de audios del Estudio: ffmpeg de verdad, archivos de verdad.

No necesita el panel prendido ni un navegador: importa `panel` (que al importarse no
levanta ningun hilo) y llama a `_unir_audios` directo. Los audios de prueba se generan
con ffmpeg, asi que no depende de ningun archivo que tenga que existir en el disco.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_unir_audios

Lo que se verifica:
  1. Un audio que entra queda guardado con su ficha (canal, quien, que dice).
  2. La lista los devuelve del mas nuevo al mas viejo.
  3. Pegar tres audios da un mp3 que dura lo que tiene que durar, con los recortes
     de cada uno y el silencio del medio contados.
  4. El recorte NO toca el archivo original (se puede volver a pegar distinto).
  5. Un archivo que no existe da error claro en vez de un mp3 a medias.
  6. Borrar saca el audio y su ficha.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import panel                                    # noqa: E402  (no levanta hilos al importar)
from app.nucleo import entrantes                # noqa: E402
from app.rutas import ESTUDIO, ESTUDIO_ENTRANTES  # noqa: E402
from app.rutas import ESTUDIO_PROYECTOS as PROYECTOS  # noqa: E402

CREATE_NO_WINDOW = 0x08000000
FALLAS = []


def chequear(que, ok, detalle=""):
    print(("  OK   " if ok else "  FALLA ") + que + (" -> " + detalle if detalle else ""))
    if not ok:
        FALLAS.append(que)


def tono(destino, seg, hz):
    """Un pitido de `seg` segundos, para tener audio real sin depender de archivos."""
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=%d:duration=%s" % (hz, seg),
                    str(destino)], check=True, creationflags=CREATE_NO_WINDOW)


def main():
    tmp = Path(__file__).with_name("_tmp_estudio")
    tmp.mkdir(exist_ok=True)
    creados = []
    try:
        print("\n1. guardar tres audios entrantes")
        for i, (segs, hz, origen, de, texto) in enumerate([
                (3.0, 440, "whatsapp", "5493794000000", "hola, te mando el primero"),
                (1.0, 660, "telegram", "Martin Jones", "este es el del medio"),
                (2.0, 880, "disco", "grabacion", "y este es el ultimo")]):
            f = tmp / ("prueba_%d.wav" % i)
            tono(f, segs, hz)
            # Solo el primero lleva la transcripcion con marcas de tiempo, para probar
            # tambien el caso de un audio viejo que no la tiene.
            # ⚠ La ULTIMA frase termina en 4,2 s a proposito, en un audio que dura 3: asi
            # es como las manda Whisper a veces (cierra el bloque con lo que estimo, no
            # con lo que dura el archivo) y hay que devolverla recortada.
            frases = [{"inicio": 0.0, "fin": 1.5, "texto": "hola, te mando el primero"},
                      {"inicio": 1.5, "fin": 4.2, "texto": "este es el segundo pedazo"}] if i == 0 else None
            nombre = entrantes.guardar(f, origen=origen, de=de, texto=texto, segmentos=frases)
            creados.append(nombre)
            chequear("se guardo el audio %d" % (i + 1), bool(nombre), nombre)

        fichas = {a["archivo"]: a for a in entrantes.listar()}
        primero = fichas.get(creados[0], {})
        chequear("la ficha guarda el canal", primero.get("origen") == "whatsapp",
                 str(primero.get("origen")))
        chequear("la ficha guarda quien lo mando", primero.get("de") == "5493794000000")
        chequear("la ficha guarda lo que dice",
                 "primero" in (primero.get("texto") or ""), primero.get("texto", ""))
        chequear("la ficha mide la duracion", abs((primero.get("dur") or 0) - 3.0) < 0.1,
                 str(primero.get("dur")))
        chequear("la lista dice cuantas frases tiene", primero.get("segs") == 2,
                 str(primero.get("segs")))
        chequear("pero NO manda los segmentos en la lista (son ~200 por audio)",
                 "segmentos" not in primero)
        segs = entrantes.segmentos_de(creados[0])
        chequear("los segmentos se piden de a uno y vienen con sus tiempos",
                 len(segs) == 2 and segs[1]["inicio"] == 1.5 and "segundo" in segs[1]["texto"],
                 str(segs[:1]))
        chequear("un audio que no existe devuelve lista vacia, no revienta",
                 entrantes.segmentos_de("no_existe.ogg") == [])
        # ⭐ Si una frase termina despues del final del audio, en la pantalla queda tachada
        # y el boton "+ poner" no la puede poner: el recorte no se estira mas alla del
        # final. Por eso el servidor no la manda asi (2026-08-18).
        chequear("una frase que se pasa del final vuelve recortada",
                 segs[-1]["fin"] <= (primero.get("dur") or 0) + 0.01, str(segs[-1]["fin"]))
        chequear("y no se pierde ninguna frase al recortar (las posiciones se guardan)",
                 len(segs) == 2, str(len(segs)))

        print("\n2. pegar los tres, con recortes y silencio")
        # 1,5 s (del primero, recortado) + 0,4 + 1,0 (entero) + 0,4 + 0,5 (recortado) = 3,8
        pistas = [{"archivo": creados[0], "ini": 0.5, "fin": 2.0},
                  {"archivo": creados[1], "ini": 0, "fin": 0},
                  {"archivo": creados[2], "ini": 0, "fin": 0.5}]
        salida = ESTUDIO / "_prueba_unido.mp3"
        ok, err = panel._unir_audios(pistas, 0.4, salida)
        chequear("ffmpeg unio sin error", ok, err)
        dur = entrantes.duracion(salida)
        chequear("el resultado dura lo esperado (3,8 s)", abs(dur - 3.8) < 0.2, "%.2f s" % dur)

        print("\n3. los originales quedan intactos")
        chequear("el original sigue durando 3 s",
                 abs(entrantes.duracion(ESTUDIO_ENTRANTES / creados[0]) - 3.0) < 0.1)
        salida2 = ESTUDIO / "_prueba_unido2.mp3"
        ok2, _ = panel._unir_audios([{"archivo": creados[0], "ini": 0, "fin": 1.0}], 0, salida2)
        chequear("se puede volver a pegar con otro recorte", ok2)
        chequear("y da la duracion nueva", abs(entrantes.duracion(salida2) - 1.0) < 0.2,
                 "%.2f s" % entrantes.duracion(salida2))

        print("\n4. un audio que no existe")
        ok3, err3 = panel._unir_audios([{"archivo": "no_existe.ogg"}], 0,
                                       ESTUDIO / "_prueba_nada.mp3")
        chequear("avisa que falta el archivo", (not ok3) and "falta" in err3, err3)
        ok4, _ = panel._unir_audios([{"archivo": "../../.env"}], 0, ESTUDIO / "_prueba_nada.mp3")
        chequear("no deja salir de la carpeta", not ok4)

        print("\n3b. sacar un pedazo del MEDIO de un audio (dos tramos del mismo archivo)")
        # Es lo que manda la pantalla cuando sacás una frase: el mismo archivo dos veces,
        # con el agujero en el medio. 3 s con 1 s sacado = 2 s.
        salida3 = ESTUDIO / "_prueba_agujero.mp3"
        ok5, err5 = panel._unir_audios([{"archivo": creados[0], "ini": 0, "fin": 1.0},
                                        {"archivo": creados[0], "ini": 2.0, "fin": 3.0}],
                                       0, salida3)
        chequear("une dos tramos del mismo archivo", ok5, err5)
        chequear("y el resultado dura sin el pedazo sacado",
                 abs(entrantes.duracion(salida3) - 2.0) < 0.2,
                 "%.2f s" % entrantes.duracion(salida3))

        print("\n4b. las bandejas (proyectos)")
        # ⚠ Esto pisa el archivo de bandejas de VERDAD, asi que se guarda tal cual estaba
        # y se restaura en el finally. Y no se compara la lista completa: `proyectos()`
        # suma las bandejas de los audios reales que Martin tenga, asi que exigir una
        # lista exacta hacia fallar la prueba en cuanto el creara una bandeja (paso).
        crudo_antes = PROYECTOS.read_text(encoding="utf-8") if PROYECTOS.exists() else None
        entrantes.guardar_proyectos(["Tienda", "Curso", "  ", "tienda"])
        lista = entrantes.proyectos()
        chequear("crea bandejas, sin vacias ni repetidas",
                 lista[:2] == ["Tienda", "Curso"], str(lista))
        chequear("mueve un audio a una bandeja", entrantes.mover(creados[0], "Tienda"))
        fichas2 = {a["archivo"]: a for a in entrantes.listar()}
        chequear("y la lista lo dice", fichas2[creados[0]].get("proyecto") == "Tienda",
                 str(fichas2[creados[0]].get("proyecto")))
        chequear("los demas quedan sin clasificar",
                 fichas2[creados[2]].get("proyecto") == "")
        chequear("mover no pierde el resto de la ficha",
                 fichas2[creados[0]].get("segs") == 2 and fichas2[creados[0]].get("dur") > 0,
                 str(fichas2[creados[0]].get("segs")))
        chequear("y no se pierden los segmentos", len(entrantes.segmentos_de(creados[0])) == 2)
        # Si se borra la bandeja pero quedan audios adentro, el nombre sigue apareciendo:
        # si no, esos audios se volverian invisibles.
        entrantes.guardar_proyectos(["Curso"])
        chequear("una bandeja borrada con audios adentro no desaparece",
                 "Tienda" in entrantes.proyectos(), str(entrantes.proyectos()))
        chequear("sacar el audio de la bandeja la hace desaparecer",
                 entrantes.mover(creados[0], "") and "Tienda" not in entrantes.proyectos(),
                 str(entrantes.proyectos()))
        if crudo_antes is not None:                  # se deja EXACTAMENTE como estaba
            PROYECTOS.write_text(crudo_antes, encoding="utf-8")
        elif PROYECTOS.exists():
            PROYECTOS.unlink()

        print("\n5. mandar al celular: los frenos (no manda nada de verdad)")
        # Se le saca la config al vuelo: los dos tienen que cortar ANTES de tocar la red.
        # Probar el envio real mandaria un audio al telefono de Martin sin que lo pida.
        orig = panel._env
        panel._env = lambda *claves: ["" for _ in claves]
        try:
            ok5, err5 = panel._mandar_telegram(salida, "prueba")
            chequear("sin token de Telegram avisa y no manda",
                     (not ok5) and "TELEGRAM" in err5, err5)
            ok6, err6 = panel._mandar_whatsapp(salida)
            chequear("sin config de WhatsApp avisa y no manda",
                     (not ok6) and "EVOLUTION" in err6, err6)
        finally:
            panel._env = orig

        print("\n6. borrar")
        chequear("borra el audio", entrantes.borrar(creados[1]))
        chequear("y tambien su ficha",
                 not (ESTUDIO_ENTRANTES / creados[1]).with_suffix(".json").exists())
        chequear("ya no aparece en la lista",
                 creados[1] not in [a["archivo"] for a in entrantes.listar()])
    finally:
        for n in creados:
            if n:
                entrantes.borrar(n)
        for f in ESTUDIO.glob("_prueba_*"):
            f.unlink(missing_ok=True)
        for f in tmp.glob("*"):
            f.unlink(missing_ok=True)
        tmp.rmdir()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d: %s" % (len(FALLAS), FALLAS)))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
