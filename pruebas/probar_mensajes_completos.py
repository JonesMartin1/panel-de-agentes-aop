"""Que la pantalla reciba las respuestas ENTERAS, y que si corta algo lo diga.

Historia: el 2026-08-24 Martin trajo una captura de una sesion que "no mandaba las
respuestas completas". No era la sesion: era el panel. `_filas_de` y
`_codex_mensajes` recortaban cada mensaje a 4.000 letras y no avisaban nada, asi que
un informe de 7.512 letras se cortaba en "1. Preguntarle a Eve (bloqueante" y parecia
que la sesion habia dejado de escribir sola. El tope no ahorraba nada medible (el hilo
mas pesado del disco pasaba de 78 KB a 79 KB sacandolo), asi que subio a 40.000 y
sobre todo dejo de ser mudo.

Aca no se habla con ninguna sesion: se arman archivos de mentira.

    python -m pruebas.probar_mensajes_completos
"""
import json
import sys
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm

ok = fallo = 0


def probar(que, condicion):
    global ok, fallo
    if condicion:
        ok += 1
        print("  ok   ", que)
    else:
        fallo += 1
        print("  FALLA", que)


# --- 1: el caso real de la captura ------------------------------------------------
# El informe que se corto medía 7.512 letras. Ese es el largo que tiene que pasar
# entero: si alguien vuelve a bajar el tope por debajo, esta prueba lo caza.
informe = "El aumento del 28/08. " * 358          # ~7.500 letras, como el de Martin
probar("un informe del largo del que se corto pasa entero",
       sm._recortar(informe) == informe and len(informe) > 7000)

probar("el mensaje mas largo que existe hoy en el disco entra sin cortarse",
       sm._recortar("x" * 16_518) == "x" * 16_518)


# --- 2: cuando SI corta, avisa ----------------------------------------------------
bestia = "y" * (sm.TOPE_MENSAJE + 5_000)
salida = sm._recortar(bestia)
probar("un mensaje patologico se corta igual (la reja sigue puesta)",
       len(salida) < len(bestia))
probar("y al cortarlo lo DICE, no se lo come callado",
       "cortado acá" in salida and "5.000 letras" in salida)
probar("lo que se ve arranca igual que el original",
       salida.startswith("y" * 100))


# --- 3: de punta a punta, leyendo un .jsonl como lo lee el panel ------------------
# Es el camino que fallaba de verdad: no alcanza con que `_recortar` este bien, tiene
# que estar ENCHUFADO en el lector del hilo.
with tempfile.TemporaryDirectory() as tmp:
    jsonl = Path(tmp) / "sesion.jsonl"
    largo = "Respuesta larga de verdad. " * 400          # ~10.800 letras
    with open(jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {
            "role": "user", "content": "contame todo"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": largo}]}}) + "\n")
    sm._HILOS.clear()
    filas = sm._filas_de(jsonl)
    dichas = [f for f in filas if f["de"] == "claude"]
    probar("el lector del hilo devolvio la respuesta", len(dichas) == 1)
    # `.strip()`: el lector le saca los espacios de los bordes, y esta bien que lo haga.
    # Lo que se mide aca es que no falte NADA del medio.
    probar("y la devolvio ENTERA, que era el bug",
           dichas and dichas[0]["texto"] == largo.strip())

    # Lo mismo del lado de Martin: sus mensajes largos tampoco se recortan.
    tuyas = [f for f in filas if f["de"] == "vos"]
    probar("el mensaje de Martin tambien viaja entero",
           tuyas and tuyas[0]["texto"] == "contame todo")


print(f"\n{ok} bien, {fallo} mal")
sys.exit(1 if fallo else 0)
