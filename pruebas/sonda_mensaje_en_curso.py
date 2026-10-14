"""Sonda contra el CLI de VERDAD: ¿se le puede escribir a una sesion MIENTRAS trabaja?

⚠ GASTA TOKENS (poco: modelo chico). Se corre a mano, no en cada commit.

En Claude Code nativo, lo que escribis mientras trabaja queda en fila y lo lee en la
proxima pausa: sirve para corregirlo sobre la marcha. El panel bloquea la caja hasta que
termina. Antes de destrabarla hay que saber que hace el CLI en el modo del panel (proceso
vivo, `--input-format stream-json`) cuando le llega un segundo mensaje a mitad de turno:

  - ¿lo toma en el MISMO turno (un solo `result`, y la respuesta obedece al segundo)?
  - ¿lo deja para despues (dos `result`)?
  - ¿lo rechaza o se rompe?

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_mensaje_en_curso
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import shutil  # noqa: E402
import tempfile  # noqa: E402

from app.voz import seguir
from app.voz import sesiones_movil as sm

# ⚠ En una carpeta TEMPORAL, no en el proyecto: si no, la charla de prueba queda mezclada
# con las de Martin en `/sesiones`. Al terminar se borra todo.
CARPETA = Path(tempfile.mkdtemp(prefix="sonda_fila_"))

PRIMERO = ("Usá la herramienta Bash para correr exactamente `sleep 8`. Cuando termine, "
           "contestá con una sola línea que diga: primero listo.")
SEGUNDO = "Cambio de planes: además, terminá tu respuesta con la palabra BANANA."


def main():
    modelo = sys.argv[sys.argv.index("--modelo") + 1] if "--modelo" in sys.argv else "haiku"
    cmd = [sm._claude_bin(), "-p", "--input-format", "stream-json",
           "--output-format", "stream-json", "--verbose", "--replay-user-messages",
           "--model", modelo, "--permission-mode", "default",
           "--permission-prompt-tool", "stdio", "--allowedTools", "Bash"]
    p = subprocess.Popen(cmd, cwd=str(CARPETA), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", bufsize=1,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    t0 = time.time()
    eventos = []

    def mandar(texto):
        p.stdin.write(json.dumps({"type": "user", "message": {
            "role": "user", "content": [{"type": "text", "text": texto}]}}) + "\n")
        p.stdin.flush()

    mandar(PRIMERO)
    mandado_segundo = False
    resultados = 0
    limite = time.time() + 120
    try:
        while time.time() < limite:
            linea = p.stdout.readline()
            if not linea:
                break
            if not linea.startswith("{"):
                continue
            d = json.loads(linea)
            tipo, s = d.get("type"), round(time.time() - t0, 1)
            if tipo == "assistant":
                for b in (d.get("message") or {}).get("content") or []:
                    if b.get("type") == "tool_use":
                        eventos.append((s, "usa herramienta", b.get("name")))
                        if not mandado_segundo:
                            # ⭐ Mientras corre el `sleep 8`: el momento exacto que interesa.
                            time.sleep(1)
                            mandar(SEGUNDO)
                            mandado_segundo = True
                            eventos.append((round(time.time() - t0, 1), "MANDO el segundo", ""))
                    elif b.get("type") == "text" and b.get("text", "").strip():
                        eventos.append((s, "texto", b["text"].strip()[:120]))
            elif tipo == "user":
                for b in (d.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "text":
                        eventos.append((s, "el CLI tomó un mensaje del usuario", b["text"][:50]))
                    elif isinstance(b, dict) and b.get("type") == "tool_result":
                        eventos.append((s, "terminó la herramienta", ""))
            elif tipo == "result":
                resultados += 1
                eventos.append((s, f"RESULT #{resultados}",
                                (d.get("result") or "")[:120] + (" [error]" if d.get("is_error") else "")))
                if resultados >= 2 or (mandado_segundo and "BANANA" in (d.get("result") or "")):
                    break
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=15)
        except Exception:
            p.kill()
    for s, que, detalle in eventos:
        print(f"{s:6.1f} s  {que}  {detalle}")
    print()
    banana = any("BANANA" in (e[2] or "") for e in eventos)
    if resultados == 1 and banana:
        print("CONCLUSION: lo toma en el MISMO turno (un solo result, y obedece al segundo).")
    elif resultados >= 2:
        print("CONCLUSION: lo deja para DESPUES: termina el primero y arranca otro turno.")
    else:
        print("CONCLUSION: no se sabe; mirar los eventos. stderr:",
              (p.stderr.read() if p.stderr else "")[:300])


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(seguir.carpeta_de(CARPETA), ignore_errors=True)
        shutil.rmtree(CARPETA, ignore_errors=True)
