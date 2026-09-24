"""Prueba de app/nucleo/gasto.py: el medidor del gasto de tokens de Claude Code.

No toca la carpeta real de transcripciones: arma una de mentira con archivos como
los que escribe Claude Code y verifica que el gasto se cuente bien — sin contar
dos veces el mismo `usage` repetido, de forma incremental, y dejando afuera lo
que no es de hoy. Se corre con: python -m pruebas.probar_gasto
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.nucleo import gasto

OK = MAL = 0


def chequear(nombre, cond):
    global OK, MAL
    print(("  ok   " if cond else "  MAL  ") + nombre)
    if cond:
        OK += 1
    else:
        MAL += 1


def linea(mid, entrada, cuando=None, salida=5):
    ts = (cuando or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {
        "id": mid, "usage": {"input_tokens": entrada, "output_tokens": salida,
                             "cache_creation_input_tokens": 0,
                             "cache_read_input_tokens": 0}}}) + "\n"


def limpiar():
    """Que cada chequeo arranque de cero: sin memoria de archivos ni cache de 30 s."""
    gasto._archivos.clear()
    gasto._CACHE["ts"] = 0.0
    gasto._CACHE["r"] = None


def fresco():
    gasto._CACHE["ts"] = 0.0
    return gasto.resumen()


with tempfile.TemporaryDirectory() as tmp:
    gasto.CARPETA = Path(tmp)
    carpeta = Path(tmp) / "D--IA-proyecto-uno"
    carpeta.mkdir()
    f = carpeta / "abcd1234-5678-90ab-cdef-000000000001.jsonl"

    # --- la suma basica, y que el usage repetido cuente UNA vez -------------------
    f.write_text(linea("msg_a", 1000) + linea("msg_a", 1000) + linea("msg_a", 1000)
                 + linea("msg_b", 2000), encoding="utf-8")
    limpiar()
    r = fresco()
    chequear("suma lo de hoy sin contar el usage repetido (3010)", r["hoy"] == 3010)
    chequear("cuenta 2 llamadas, no 4 lineas", r["llamadas"] == 2)
    chequear("la ultima hora tambien lo tiene", r["ultima_hora"] == 3010)
    chequear("la sesion sale con proyecto y principio del id",
             r["sesiones"] and r["sesiones"][0]["nombre"] == "IA-proyecto-uno · abcd1234")

    # --- lo viejo del mismo archivo: cuenta en el dia de AYER, no en hoy ----------
    ayer = datetime.now(timezone.utc) - timedelta(days=1)
    hace3h = datetime.now(timezone.utc) - timedelta(hours=3)
    with open(f, "a", encoding="utf-8") as h:
        h.write(linea("msg_c", 500, cuando=ayer))
        h.write(linea("msg_d", 700, cuando=hace3h))
    r = fresco()
    chequear("lo de ayer no entra en hoy; lo de hace 3 h si", r["hoy"] == 3715)
    chequear("pero hace 3 h ya no es 'ultima hora'", r["ultima_hora"] == 3010)

    # --- incremental: lo nuevo se suma, lo leido no se relee ----------------------
    pos_antes = gasto._archivos[str(f)]["pos"]
    with open(f, "a", encoding="utf-8") as h:
        h.write(linea("msg_e", 4000))
    r = fresco()
    chequear("lo agregado despues se suma (7720)", r["hoy"] == 7720)
    chequear("y solo se leyo lo nuevo del archivo",
             gasto._archivos[str(f)]["pos"] > pos_antes)

    # --- una linea a medio escribir espera al proximo repaso ----------------------
    with open(f, "a", encoding="utf-8") as h:
        h.write(linea("msg_f", 9000).rstrip("\n"))      # sin salto: quedo a medias
    r = fresco()
    chequear("la linea cortada no se cuenta todavia", r["hoy"] == 7720)
    with open(f, "a", encoding="utf-8") as h:
        h.write("\n")
    r = fresco()
    chequear("completada la linea, se cuenta (16725)", r["hoy"] == 16725)

    # --- un archivo que no se escribio hoy ni se abre -----------------------------
    g = carpeta / "abcd1234-5678-90ab-cdef-000000000002.jsonl"
    g.write_text(linea("msg_z", 123456), encoding="utf-8")
    viejo = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(g, (viejo, viejo))
    r = fresco()
    chequear("un archivo de anteayer se saltea entero", r["hoy"] == 16725)

    # --- los numeros dichos como una persona --------------------------------------
    chequear("lindo: 1.640M", gasto.lindo(1_640_000_000) == "1.640M")
    chequear("lindo: 67M", gasto.lindo(67_000_000) == "67M")
    chequear("lindo: 6,5M", gasto.lindo(6_500_000) == "6,5M")
    chequear("lindo: 850k", gasto.lindo(850_000) == "850k")

print(f"\n{OK} ok, {MAL} mal")
sys.exit(1 if MAL else 0)
