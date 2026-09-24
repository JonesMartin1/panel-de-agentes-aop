import os
import sys

# --- Usar el almacen de certificados de Windows (evita el error SSL del antivirus/proxy) ---
import truststore
truststore.inject_into_ssl()

# --- Ayudar a Windows a encontrar las DLLs de CUDA (cuBLAS + cuDNN) del entorno ---
base = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
dll_dirs = []
if os.path.isdir(base):
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        p = os.path.join(base, sub, "bin")
        if os.path.isdir(p):
            os.add_dll_directory(p)
            dll_dirs.append(p)
print("DLL dirs agregados:")
for d in dll_dirs:
    print("  ", d)

from faster_whisper import WhisperModel

MODELOS = r"D:\IA\modelos"

print("\n>>> Intentando cargar el modelo 'tiny' en la GPU (CUDA)...")
try:
    model = WhisperModel("tiny", device="cuda", compute_type="float16", download_root=MODELOS)
    print("OK: el modelo cargo en la GPU (CUDA + float16). La 4070 esta lista.")
    ok = True
except Exception as e:
    print("FALLO en GPU:", repr(e))
    print("\n>>> Probando en CPU como control...")
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=MODELOS)
    print("OK en CPU (pero la GPU no se uso).")
    ok = False

print("\nRESULTADO:", "GPU FUNCIONA" if ok else "GPU NO - reviso las DLLs")
