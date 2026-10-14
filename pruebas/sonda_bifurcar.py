"""Sonda contra el CLI de VERDAD: ¿como se bifurca una charla con `--fork-session`?

⚠ GASTA TOKENS (poco: modelo chico, dos turnos cortos). Se corre a mano.

Lo que tiene que pasar para que el boton "bifurcar" del panel sirva:
  1. la copia RECUERDA lo anterior (sigue la charla, no empieza de cero);
  2. la copia tiene un id NUEVO;
  3. la original queda INTACTA (mismo archivo, mismas lineas).

Corre en una carpeta temporal y se limpia sola.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_bifurcar
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.voz import seguir  # noqa: E402
from app.voz import sesiones_movil as sm  # noqa: E402

CARPETA = Path(tempfile.mkdtemp(prefix="sonda_fork_"))


def turno(texto, extra):
    cmd = [sm._claude_bin(), "-p", "--input-format", "stream-json", "--output-format",
           "stream-json", "--verbose", "--model", "haiku", *extra]
    p = subprocess.run(cmd, cwd=str(CARPETA), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180,
                       input=json.dumps({"type": "user", "message": {"role": "user",
                                         "content": [{"type": "text", "text": texto}]}}) + "\n",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for linea in p.stdout.splitlines():
        if linea.startswith("{") and json.loads(linea).get("type") == "result":
            d = json.loads(linea)
            return d.get("session_id"), (d.get("result") or "").strip()
    return None, p.stderr[:200]


def main():
    try:
        a, r1 = turno("Recordá el número 4217. Contestá solamente: ok.", [])
        orig = seguir.carpeta_de(CARPETA) / f"{a}.jsonl"
        antes = orig.read_text(encoding="utf-8").count("\n")
        b, r2 = turno("¿Qué número te pedí que recordaras? Contestá solo el número.",
                      ["--resume", a, "--fork-session"])
        despues = orig.read_text(encoding="utf-8").count("\n")
        copia = seguir.carpeta_de(CARPETA) / f"{b}.jsonl"
        filas = [f["de"] + ": " + f["texto"][:50] for f in sm._filas_de(copia)] if b else []
        print("original:", a, "->", r1)
        print("copia:   ", b, "->", r2)
        print("hilo de la copia:", filas)
        print()
        print("1) recuerda lo anterior:", "SI" if "4217" in r2 else "NO")
        print("2) id nuevo:", "SI" if b and b != a else "NO")
        print("3) original intacta:", "SI" if antes == despues else f"NO ({antes} -> {despues})")
        print("4) el hilo de la copia trae lo anterior:", "SI" if any("4217" in f for f in filas) else "NO")
    finally:
        shutil.rmtree(seguir.carpeta_de(CARPETA), ignore_errors=True)
        shutil.rmtree(CARPETA, ignore_errors=True)


if __name__ == "__main__":
    main()
