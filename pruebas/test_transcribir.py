import os
import sys
import truststore
truststore.inject_into_ssl()

# DLLs de CUDA
base = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
for sub in ("cublas", "cudnn", "cuda_nvrtc"):
    p = os.path.join(base, sub, "bin")
    if os.path.isdir(p):
        os.add_dll_directory(p)

from faster_whisper import WhisperModel

from app.rutas import DIR_MODELOS

MODELOS = str(DIR_MODELOS)
# El audio se pasa como argumento: python -m pruebas.test_transcribir "mi_audio.m4a".
# No viene ninguno con el proyecto a proposito: un audio de prueba real tiene voces reales.
if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
    sys.exit('Uso: python -m pruebas.test_transcribir "ruta\\a\\un_audio.m4a"')
AUDIO = sys.argv[1]

# Uso 'small' para una prueba rapida con calidad decente en espaniol
print(">>> Cargando modelo 'small' en la GPU...")
model = WhisperModel("small", device="cuda", compute_type="float16", download_root=MODELOS)

print(">>> Transcribiendo en la 4070...\n")
segments, info = model.transcribe(AUDIO, language="es")
print(f"Idioma detectado: {info.language} (prob {info.language_probability:.2f})\n")
print("TRANSCRIPCION:")
for seg in segments:
    print(f"  [{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text.strip()}")
