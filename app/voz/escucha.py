"""
Wake words con Porcupine (Picovoice): manos libres, sin apretar tecla.

  "Laura"      -> modo CLAUDE     (cerebro grande, solo lectura)
  "Venus"      -> modo ASISTENTE  (comandos locales, navegador, pantalla)

Corre en CPU, offline, y NO transcribe nada: solo busca el patron sonoro.
Se alimenta del MISMO microfono que ya abre voz.py (no abre un segundo stream).

Si faltan la clave o los archivos .ppn, queda DESACTIVADO y todo lo demas sigue
funcionando igual (las teclas F9 / Shift+F9 / Ctrl+F9 no dependen de esto).

Necesita en D:\\IA\\modelos\\porcupine:
  - porcupine_params_es.pv        (modelo de espaniol)
  - *laura*.ppn                   (wake word "Laura",      Windows, es)
  - *venus*.ppn                   (wake word "Venus",      Windows, es)
y PICOVOICE_ACCESS_KEY en el .env
"""

import os
import glob
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from app.rutas import ENV, DIR_PORCUPINE

load_dotenv(ENV)

CARPETA = str(DIR_PORCUPINE)
PARAMS_ES = os.path.join(CARPETA, "porcupine_params_es.pv")
SENSIBILIDAD = 0.6            # 0-1: mas alto = detecta mas facil pero mas falsos positivos

_pp = None                    # instancia de Porcupine
_modo_por_indice = {}         # indice del keyword -> modo que dispara
_resto = np.empty(0, dtype=np.int16)   # audio sobrante entre bloques
_activo = False


def _buscar_ppn(*claves):
    """Busca un .ppn cuyo nombre contenga alguna clave (los nombres de Picovoice son largos)."""
    for f in glob.glob(os.path.join(CARPETA, "*.ppn")):
        n = os.path.basename(f).lower().replace("-", " ").replace("_", " ")
        if any(k in n for k in claves):
            return f
    return None


def iniciar():
    """Prepara Porcupine. Devuelve True si quedo escuchando; False si falta algo."""
    global _pp, _modo_por_indice, _activo
    if _activo:
        return True
    clave = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip()
    if not clave:
        print("wake word: falta PICOVOICE_ACCESS_KEY en .env (desactivado)", flush=True)
        return False
    if not os.path.exists(PARAMS_ES):
        print(f"wake word: falta el modelo de espaniol {PARAMS_ES} (desactivado)", flush=True)
        return False

    rutas, modos = [], []
    for claves, modo in ((("laura",), "claude"), (("venus",), "asistente")):
        f = _buscar_ppn(*claves)
        if f:
            rutas.append(f)
            modos.append(modo)
            print(f"wake word: {os.path.basename(f)} -> {modo}", flush=True)
        else:
            print(f"wake word: no encontre el .ppn de {claves[0]} en {CARPETA}", flush=True)
    if not rutas:
        return False

    try:
        import pvporcupine
        _pp = pvporcupine.create(access_key=clave, keyword_paths=rutas,
                                 model_path=PARAMS_ES,
                                 sensitivities=[SENSIBILIDAD] * len(rutas))
    except Exception as e:
        print("wake word: no pude iniciar Porcupine:", e, flush=True)
        return False

    _modo_por_indice = {i: m for i, m in enumerate(modos)}
    _activo = True
    print(f"wake word ACTIVO ({len(rutas)} palabras, {_pp.sample_rate} Hz)", flush=True)
    return True


def procesar(bloque_float32):
    """Alimenta el detector con audio del microfono (float32 mono 16k).
    Devuelve el modo ('claude' / 'asistente') si se dijo la palabra, o None."""
    global _resto
    if not _activo or _pp is None:
        return None
    try:
        pcm = np.clip(np.asarray(bloque_float32, dtype=np.float32).flatten(), -1.0, 1.0)
        pcm = (pcm * 32767).astype(np.int16)
        buf = np.concatenate((_resto, pcm)) if _resto.size else pcm
        n = _pp.frame_length
        detectado = None
        i = 0
        while i + n <= buf.size:
            idx = _pp.process(buf[i:i + n])
            if idx >= 0:
                detectado = _modo_por_indice.get(idx)
            i += n
        _resto = buf[i:].copy()
        return detectado
    except Exception as e:
        print("wake word: error procesando:", e, flush=True)
        return None


def frecuencia():
    return _pp.sample_rate if _pp else 16000


def cerrar():
    global _pp, _activo
    if _pp is not None:
        try:
            _pp.delete()
        except Exception:
            pass
    _pp, _activo = None, False
