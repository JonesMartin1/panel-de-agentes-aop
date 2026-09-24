"""
Asistente de voz local. Manten Ctrl+F9, das una orden, la soltas ->
Whisper la transcribe -> ejecuta la accion -> te contesta por voz (Piper, es-AR).

F9 solo = dictado (otro script). Ctrl+F9 = asistente (este).
Comandos en acciones.py (extensible).
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)

import json
import time
import wave
import tempfile
import threading
import winsound
from pathlib import Path

from app.nucleo import core
from faster_whisper import WhisperModel
import numpy as np
import sounddevice as sd
import keyboard
from piper import PiperVoice

from app.voz import acciones
from app.voz import cerebro

from app.rutas import CONFIG_DICTADO, VOZ_PIPER

VOZ = str(VOZ_PIPER)
SR = 16000
MIN_SEG = 0.3
CFG_FILE = CONFIG_DICTADO   # comparte el mic con el dictado


def _device():
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
    return None


model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16",
                     download_root=core.DIR_MODELOS, local_files_only=True)
voz = PiperVoice.load(VOZ)
_WAV = str(Path(tempfile.gettempdir()) / "asistente_tts.wav")
_lock = threading.Lock()


def hablar(texto):
    if not texto:
        return
    with _lock:
        try:
            with wave.open(_WAV, "wb") as wf:
                voz.synthesize_wav(texto, wf)
            winsound.PlaySound(_WAV, winsound.SND_FILENAME)
        except Exception as e:
            print("error TTS:", e, flush=True)


_grabando = False
_buf = []


def _cb(indata, frames, t, status):
    if _grabando:
        _buf.append(indata.copy())


_dev = _device()
_stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=_cb, device=_dev)
_stream.start()


_shift = False   # estado de la tecla Shift, rastreado del flujo de eventos


def _procesar(frames):
    if not frames:
        return
    audio = np.concatenate(frames, axis=0).flatten().astype("float32")
    if len(audio) < SR * MIN_SEG:
        return
    try:
        segs, _ = model.transcribe(audio, language="es", vad_filter=True)
        texto = " ".join(s.text.strip() for s in segs).strip()
    except Exception as e:
        print("error transcribiendo:", e, flush=True)
        return
    if not texto:
        return
    print("comando:", texto, flush=True)
    resp, ok = acciones.ejecutar(texto)
    if not ok:
        resp = cerebro.responder(texto) or "No te entendi, podes repetir?"
    print("respuesta:", resp, flush=True)
    hablar(resp)


def _on_key(ev):
    global _shift, _grabando, _buf
    n = (ev.name or "").lower()
    if "shift" in n:
        _shift = (ev.event_type == "down")
        return
    if n == "f9":
        if ev.event_type == "down":
            if _shift and not _grabando:
                _buf = []
                _grabando = True
        elif ev.event_type == "up":
            if _grabando:
                _grabando = False
                frames = list(_buf)
                threading.Thread(target=_procesar, args=(frames,), daemon=True).start()


keyboard.hook(_on_key)
print("Asistente de voz ACTIVO. Manten Shift+F9 para hablar.", flush=True)
keyboard.wait()
