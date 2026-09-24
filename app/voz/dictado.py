"""
Dictado por voz global (push-to-talk).
Manten apretada F9, hablas, la soltas -> transcribe en la 4070 (Whisper local)
y PEGA el texto donde tengas el cursor (VS Code, Claude Code, WhatsApp Web, etc.).

Beeps:  agudo = empezo a grabar | medio = proceso | grave = no se entendio nada.

Correr:  python dictado.py   (o via el panel / acceso del escritorio)
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)   # Avast rompe el SSL de Python

import json
import time
import threading
import winsound
from pathlib import Path

from app.nucleo import core                              # setea SSL + DLLs de CUDA
from faster_whisper import WhisperModel
import numpy as np
import sounddevice as sd
import keyboard
import pyperclip

from app.rutas import CONFIG_DICTADO

CFG_FILE = CONFIG_DICTADO


def _device():
    """Lee el microfono elegido del config; devuelve el indice o None (=predeterminado)."""
    try:
        nombre = json.loads(CFG_FILE.read_text(encoding="utf-8")).get("microfono")
    except Exception:
        nombre = None
    if not nombre:
        return None
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["name"] == nombre:
                return i
    except Exception:
        pass
    return None   # si no lo encuentra, usa el predeterminado

TECLA = "f9"
SR = 16000            # 16 kHz mono, lo ideal para Whisper
MIN_SEG = 0.3         # ignora toques mas cortos que esto
SONIDO = False        # True = beeps de aviso ; False = silencioso


def _beep(freq, dur):
    if SONIDO:
        try:
            winsound.Beep(freq, dur)
        except Exception:
            pass

# --- Modelo rapido (turbo). Si no esta, cae a 'small' que ya esta descargado ---
try:
    model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16",
                         download_root=core.DIR_MODELOS, local_files_only=True)
    print("Modelo: large-v3-turbo", flush=True)
except Exception:
    model = WhisperModel("small", device="cuda", compute_type="float16",
                         download_root=core.DIR_MODELOS, local_files_only=True)
    print("Modelo: small (turbo no disponible)", flush=True)

_grabando = False
_buf = []


def _audio_cb(indata, frames, t, status):
    if _grabando:
        _buf.append(indata.copy())


_dev = _device()
_stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=_audio_cb, device=_dev)
_stream.start()
_nombre_mic = sd.query_devices(_dev)["name"] if _dev is not None else "predeterminado de Windows"
print(f"Microfono: {_nombre_mic}", flush=True)


_mods = set()   # modificadores apretados (shift/ctrl/alt), rastreados del flujo


def _procesar(frames):
    if not frames:
        return
    audio = np.concatenate(frames, axis=0).flatten().astype("float32")
    if len(audio) < SR * MIN_SEG:
        return
    try:
        segs, _ = model.transcribe(audio, language="es", vad_filter=True)
        texto = " ".join(s.text.strip() for s in segs).strip()
    except Exception as ex:
        print("error transcribiendo:", ex, flush=True)
        _beep(300, 200)
        return
    if not texto:
        _beep(300, 160)
        return
    _pegar(texto)
    print("dictado:", texto, flush=True)


def _pegar(texto):
    """Pega el texto en la app activa via portapapeles (respeta acentos/enies)."""
    try:
        previo = pyperclip.paste()
    except Exception:
        previo = ""
    pyperclip.copy(texto)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.25)
    try:
        pyperclip.copy(previo)   # restaura lo que tenias en el portapapeles
    except Exception:
        pass


def _on_key(ev):
    global _grabando, _buf
    n = (ev.name or "").lower()
    if any(m in n for m in ("shift", "ctrl", "alt")):
        if ev.event_type == "down":
            _mods.add(n)
        else:
            _mods.discard(n)
        return
    if n == TECLA:
        if ev.event_type == "down":
            if not _mods and not _grabando:      # F9 SIN modificadores = dictado
                _buf = []
                _grabando = True
                _beep(880, 90)
        elif ev.event_type == "up":
            if _grabando:
                _grabando = False
                _beep(560, 90)
                frames = list(_buf)
                threading.Thread(target=_procesar, args=(frames,), daemon=True).start()


keyboard.hook(_on_key)
print(f"Dictado por voz ACTIVO. Manten {TECLA.upper()} (sin modificadores) para hablar.", flush=True)
keyboard.wait()   # mantener el proceso vivo
