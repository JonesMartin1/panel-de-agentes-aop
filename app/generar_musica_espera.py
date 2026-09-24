"""
Genera musica_espera.wav en la misma carpeta.
Correr una sola vez: python generar_musica_espera.py
"""
import numpy as np
import wave
from pathlib import Path

SR = 22050
VOL = 0.28

def nota(freq, dur):
    n = int(SR * dur)
    t = np.linspace(0, dur, n, False)
    s = (np.sin(2 * np.pi * freq * t)
       + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
       + 0.12 * np.sin(2 * np.pi * freq * 3 * t))
    s /= np.max(np.abs(s))
    s *= VOL
    fade = int(SR * 0.018)
    s[:fade] *= np.linspace(0, 1, fade)
    s[-fade:] *= np.linspace(1, 0, fade)
    return s

# Melodia pentatonica ascendente/descendente - estilo musica de ascensor
MELODIA = [
    (523.25, 0.4),   # C5
    (587.33, 0.4),   # D5
    (659.25, 0.4),   # E5
    (783.99, 0.4),   # G5
    (880.00, 0.6),   # A5 - pico
    (783.99, 0.4),   # G5
    (659.25, 0.4),   # E5
    (523.25, 0.8),   # C5 - pausa larga
    (659.25, 0.4),   # E5
    (783.99, 0.4),   # G5
    (880.00, 0.4),   # A5
    (783.99, 0.4),   # G5
    (523.25, 1.0),   # C5 - cierre
]

silencio = np.zeros(int(SR * 0.2))
audio = np.concatenate([nota(f, d) for f, d in MELODIA] + [silencio])
audio_int16 = (audio * 32767).astype(np.int16)

from app.rutas import MUSICA_ESPERA

destino = MUSICA_ESPERA
with wave.open(str(destino), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(audio_int16.tobytes())

print(f"Generado: {destino}  ({len(audio)/SR:.1f}s)")
