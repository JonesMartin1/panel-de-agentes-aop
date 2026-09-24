"""Lee las lineas 'tiempos:' de logs/voz.log y dice donde se va la latencia.

Uso, desde la raiz del proyecto:
    python -m pruebas.analizar_tiempos
    python -m pruebas.analizar_tiempos 50      (solo las ultimas 50 muestras)

Las lineas las escribe _medir() en app/voz/voz.py. Si no aparece ninguna,
todavia no usaste la voz desde que se instrumento.
"""

import re
import sys
from statistics import median

from app.rutas import LOGS

LINEA = re.compile(r"^tiempos:\s+(\w+)=([\d.]+)s(.*)$")
EXTRA = re.compile(r"(\w+)=([\d.]+)")


def leer(limite=None):
    """Devuelve {etapa: [(segundos, {extras})]} desde el log."""
    datos = {}
    try:
        lineas = (LOGS / "voz.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        print(f"no encuentro {LOGS / 'voz.log'}")
        return datos
    for ln in lineas:
        m = LINEA.match(ln.strip())
        if not m:
            continue
        etapa, seg, resto = m.group(1), float(m.group(2)), m.group(3)
        extras = {k: float(v) for k, v in EXTRA.findall(resto)}
        datos.setdefault(etapa, []).append((seg, extras))
    if limite:
        datos = {k: v[-limite:] for k, v in datos.items()}
    return datos


def main():
    limite = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    datos = leer(limite)
    if not datos:
        print("Todavia no hay mediciones. Usa la voz un rato y volve a correr esto.")
        return

    print(f"{'etapa':<20} {'n':>3} {'min':>7} {'mediana':>8} {'max':>7}   observaciones")
    print("-" * 86)
    for etapa in ("transcribir", "tts_primera_palabra", "tts_total", "respuesta_total"):
        muestras = datos.get(etapa)
        if not muestras:
            continue
        segs = [s for s, _ in muestras]
        obs = ""
        # Factor de tiempo real: cuantos segundos de audio procesa por segundo.
        # >1 es mas rapido que tiempo real, <1 es mas lento.
        audios = [e["audio"] for _, e in muestras if "audio" in e]
        if audios and etapa == "transcribir":
            ftr = sum(audios) / sum(segs)
            obs = f"{ftr:.1f}x tiempo real (mas alto = mejor)"
            colas = [e["cola"] for _, e in muestras if "cola" in e]
            if colas and max(colas) > 0.05:
                obs += f" | ESPERA por el lock: max {max(colas):.2f}s"
        elif etapa == "tts_primera_palabra":
            obs = "lo que de verdad se siente: silencio antes de la 1a palabra"
        elif etapa == "tts_total":
            letras = [e["letras"] for _, e in muestras if "letras" in e]
            if letras:
                obs = f"{sum(segs) / sum(letras) * 1000:.0f} ms por letra"
        print(f"{etapa:<20} {len(segs):>3} {min(segs):>6.2f}s {median(segs):>7.2f}s "
              f"{max(segs):>6.2f}s   {obs}")

    # Con la sintesis por trozos, lo que importa es que el silencio inicial NO crezca
    # con el largo de la respuesta. Si crece, la rampa de trozos esta mal calibrada.
    primeras = datos.get("tts_primera_palabra") or []
    conletras = [(e["letras"], s, e.get("total", 0)) for s, e in primeras if "letras" in e]
    if conletras:
        print()
        print("Silencio hasta la primera palabra, segun el largo TOTAL de la respuesta:")
        for letras, seg, total in sorted(conletras, key=lambda x: x[2])[-8:]:
            print(f"   respuesta de {int(total):>4} letras -> habla a los {seg:.2f}s"
                  f"   (1er trozo: {int(letras)} letras)")
        print()
        print("   Tiene que quedar PLANO: si el silencio crece con el largo de la")
        print("   respuesta, revisar TTS_CRECIMIENTO y TTS_TROZO_1 en app/voz/voz.py.")
    else:
        print()
        print("Falta una respuesta de Laura para ver el silencio inicial con la sintesis")
        print("por trozos. Preguntale algo que conteste largo.")


if __name__ == "__main__":
    main()
