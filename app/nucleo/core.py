"""
Nucleo compartido: setup de entorno, transcripcion y extraccion de audio/frames.
Lo usan transcribir.py (CLI), el bot de Telegram y el conector de WhatsApp.
"""

import os
import sys
import json
import subprocess
import threading
from pathlib import Path

# Avast setea SSLKEYLOGFILE a un proxy propio y rompe el SSL de Python -> lo ignoramos
os.environ.pop("SSLKEYLOGFILE", None)

# --- SSL: usar el almacen de certificados de Windows (antivirus/proxy) ---
import truststore
truststore.inject_into_ssl()

# --- DLLs de CUDA (cuBLAS + cuDNN) para que Whisper use la GPU ---
_nv = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
for _sub in ("cublas", "cudnn", "cuda_nvrtc"):
    _p = os.path.join(_nv, _sub, "bin")
    if os.path.isdir(_p):
        os.add_dll_directory(_p)

from faster_whisper import WhisperModel

from app import rutas

# ============================ CONFIG ============================
MODELO         = "large-v3"
DEVICE         = "cuda"
COMPUTE_TYPE   = "float16"
IDIOMA         = "es"
DIR_MODELOS    = str(rutas.DIR_MODELOS)
DIR_RESULTADOS = str(rutas.RESULTADOS)

FRAME_CADA_SEG = 4
MAX_FRAMES     = 12

EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp"}
EXT_AUDIO = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".flac", ".oga"}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif"}
# ===============================================================

_MODEL = None  # se carga una sola vez y se reutiliza
# Una sola GPU, un solo modelo cargado: dos hilos llamando a model.transcribe()
# al mismo tiempo (ej. varios audios de WhatsApp llegando juntos) se pisan y
# ninguno termina nunca -- se vio en vivo el 2026-08-11 con 11 audios en cola,
# 0 % de avance en 48 s con la GPU al 100 %. Este lock los pone en fila: de a
# uno, sin pelearse por la placa. El cuello de botella es la GPU, no el código.
_LOCK_TRANSCRIBIR = threading.Lock()
# Mismo problema, momento distinto: arranque en frio + varios audios juntos =
# el "if _MODEL is None" no es atomico y cada hilo carga SU PROPIA copia del
# modelo (~2 GB c/u) antes de que la primera termine de asignarse. Se vio en
# vivo el mismo dia: 3 pedidos juntos justo despues de un reinicio, 3 cargas
# superpuestas. Un solo lock cubre carga Y transcripcion: cargar es unico y
# rapido, no vale la pena un lock aparte.
_LOCK_MODELO = threading.Lock()


def log(msg):
    print(msg, flush=True)


def cargar_modelo():
    """Carga el modelo Whisper una sola vez (singleton)."""
    global _MODEL
    with _LOCK_MODELO:
        if _MODEL is None:
            log(f"Cargando modelo {MODELO} en {DEVICE}...")
            _MODEL = WhisperModel(MODELO, device=DEVICE, compute_type=COMPUTE_TYPE,
                                  download_root=DIR_MODELOS, local_files_only=True)
            log("Modelo listo.")
        return _MODEL


# ⚠ Que ffmpeg y ffprobe no abran una consola en Windows: esto corre adentro del bot
# de Telegram y del webhook de WhatsApp, que el panel lanza SIN consola, asi que sin
# la marca cada audio que entra le hacia parpadear una ventana negra en la pantalla
# (2026-09-06). `entrantes.py` ya la tenia; el nucleo habia quedado afuera.
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, text=True, creationflags=SIN_VENTANA)
    if r.returncode != 0:
        log(f"  ffmpeg error: {r.stderr.strip()}")
        return False
    return True


def _duracion_seg(ruta):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)],
        capture_output=True, text=True, creationflags=SIN_VENTANA)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _extraer_audio(video, destino_wav):
    log("  Extrayendo audio del video...")
    return _ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(destino_wav)])


def _extraer_frames(video, carpeta_frames):
    carpeta_frames.mkdir(parents=True, exist_ok=True)
    dur = _duracion_seg(video)
    fps = 1.0 / FRAME_CADA_SEG
    if dur > 0 and dur * fps > MAX_FRAMES:
        fps = MAX_FRAMES / dur
    log(f"  Extrayendo frames (~1 cada {1/fps:.1f}s)...")
    patron = str(carpeta_frames / "frame_%03d.jpg")
    ok = _ffmpeg(["-i", str(video), "-vf", f"fps={fps:.4f}", "-q:v", "3", patron])
    frames = sorted(str(p) for p in carpeta_frames.glob("frame_*.jpg")) if ok else []
    log(f"  {len(frames)} frames extraidos.")
    return frames


def _avisar_progreso(progreso, pct, paso):
    """Cuenta el avance sin dejar que una pantalla pueda frenar Whisper."""
    if not progreso:
        return
    try:
        progreso(max(0, min(100, int(pct))), str(paso or ""))
    except Exception:
        pass


def procesar_archivo(entrada, progreso=None):
    """
    Procesa un audio o video: extrae (si video) + transcribe.
    Devuelve (datos:dict, carpeta_salida:Path). Guarda transcripcion.txt y datos.json.
    """
    entrada = Path(entrada)
    if not entrada.exists():
        raise FileNotFoundError(entrada)

    ext = entrada.suffix.lower()
    es_video = ext in EXT_VIDEO

    nombre = entrada.stem
    out = Path(DIR_RESULTADOS) / nombre
    out.mkdir(parents=True, exist_ok=True)
    log(f"\n=== Procesando: {entrada.name} ({'video' if es_video else 'audio'}) ===")

    _avisar_progreso(progreso, 2, "Preparando el archivo…")
    frames = []
    frames_tiempos = []
    if es_video:
        audio_path = out / "audio.wav"
        _avisar_progreso(progreso, 6, "Extrayendo el audio del video…")
        if not _extraer_audio(entrada, audio_path):
            raise RuntimeError("No se pudo extraer el audio del video")
        _avisar_progreso(progreso, 14, "Buscando momentos del video…")
        frames = _extraer_frames(entrada, out / "frames")
        dur_video = _duracion_seg(entrada)
        paso_frames = (dur_video / len(frames)) if dur_video > 0 and frames else FRAME_CADA_SEG
        frames_tiempos = [round(min(dur_video, i * paso_frames), 2)
                          for i in range(len(frames))]
    else:
        audio_path = entrada

    duracion_audio = max(1.0, _duracion_seg(audio_path))
    _avisar_progreso(progreso, 24, "Cargando el modelo de voz…")
    model = cargar_modelo()
    if _LOCK_TRANSCRIBIR.locked():
        log("  Esperando su turno (ya hay otra transcripcion en la GPU)...")
        _avisar_progreso(progreso, 28, "Esperando su turno en la placa…")
    with _LOCK_TRANSCRIBIR:
        log("  Transcribiendo en la 4070...")
        _avisar_progreso(progreso, 30, "Separando las frases…")
        segments, info = model.transcribe(str(audio_path), language=IDIOMA, vad_filter=True)
        segs = []
        for s in segments:
            segs.append({"inicio": round(s.start, 2), "fin": round(s.end, 2), "texto": s.text.strip()})
            _avisar_progreso(progreso, 30 + 66 * min(1.0, s.end / duracion_audio),
                              "Separando las frases…")
    texto_plano = " ".join(s["texto"] for s in segs).strip()

    txt = out / "transcripcion.txt"
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"Archivo: {entrada.name}\n")
        f.write(f"Idioma: {info.language} (prob {info.language_probability:.2f})\n")
        f.write("=" * 50 + "\n\n")
        f.write(texto_plano + "\n\n--- Con marcas de tiempo ---\n")
        for s in segs:
            f.write(f"[{s['inicio']:.1f}s -> {s['fin']:.1f}s] {s['texto']}\n")

    datos = {
        "archivo": entrada.name,
        "tipo": "video" if es_video else "audio",
        "idioma": info.language,
        "transcripcion": texto_plano,
        "segmentos": segs,
        "frames": frames,
        # Cada imagen lleva su lugar aproximado en el video. Gemini recibe esta marca
        # justo antes del fotograma y puede narrar lo que va pasando en orden.
        "frames_tiempos": frames_tiempos,
        "analisis_ia": None,
    }
    with open(out / "datos.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    _avisar_progreso(progreso, 100, "Fragmentos listos")
    log(f"  Transcripcion lista ({len(segs)} segmentos).")
    return datos, out
