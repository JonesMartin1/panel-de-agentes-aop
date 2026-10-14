"""Sonda contra el CLI de VERDAD: ¿se pueden habilitar los subagentes en las sesiones del panel?

⚠ GASTA TOKENS (poco: modelo chico). Se corre a mano, en una carpeta temporal.

Las sesiones del panel NO tienen permitido `Agent`/`Task` porque heredaron la lista de Laura,
y Laura los saco por un bug viejo: "los sub-agentes devolvian un session_id que NO era el de
la charla, y al reanudarlo Laura arrancaba en blanco" (`claude_voz.py`). Esto mide si ese
problema sigue en la version instalada, y que manda el CLI mientras trabaja un subagente:

  1. el `session_id` del resultado es el de la charla (no el del subagente);
  2. retomar la charla con `--resume` recuerda lo anterior;
  3. con `--forward-subagent-text`, que llega del subagente mientras trabaja.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_subagentes
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

CARPETA = Path(tempfile.mkdtemp(prefix="sonda_sub_"))
for i in range(3):
    (CARPETA / f"nota{i}.txt").write_text(f"nota {i}", encoding="utf-8")


def turno(texto, extra):
    cmd = [sm._claude_bin(), "-p", "--input-format", "stream-json", "--output-format",
           "stream-json", "--verbose", "--model", "haiku", "--forward-subagent-text",
           "--allowedTools", "Agent", "Task", "Glob", "Read", *extra]
    p = subprocess.run(cmd, cwd=str(CARPETA), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300,
                       input=json.dumps({"type": "user", "message": {"role": "user",
                                         "content": [{"type": "text", "text": texto}]}}) + "\n",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    init, res, sub = None, None, []
    for linea in p.stdout.splitlines():
        if not linea.startswith("{"):
            continue
        d = json.loads(linea)
        if d.get("type") == "system" and d.get("subtype") == "init" and not init:
            init = d.get("session_id")
        if d.get("parent_tool_use_id"):
            c = (d.get("message") or {}).get("content") or []
            txt = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            sub.append((d.get("type"), d.get("session_id"), txt[:60]))
        if d.get("type") == "result":
            res = d
    return init, res, sub


def main():
    try:
        init, res, sub = turno("Usá la herramienta Agent para lanzar un subagente que cuente "
                               "cuántos archivos .txt hay en esta carpeta. Después decime el "
                               "número y recordá la palabra CEBOLLA.", [])
        sid = (res or {}).get("session_id")
        print("id al arrancar:", init, "| id del resultado:", sid)
        print("respuesta:", ((res or {}).get("result") or "")[:120])
        print("mensajes del subagente:", len(sub))
        for s in sub[:6]:
            print("   ", s)
        _, res2, _ = turno("¿Qué palabra te pedí recordar? Contestá solo la palabra.",
                           ["--resume", sid] if sid else [])
        print()
        print("1) el resultado trae el id de la charla:", "SI" if sid and sid == init else "NO")
        print("2) retomar recuerda lo anterior:",
              "SI" if "CEBOLLA" in ((res2 or {}).get("result") or "").upper() else "NO")
        print("3) llega texto del subagente mientras trabaja:", "SI" if sub else "NO")
    finally:
        shutil.rmtree(seguir.carpeta_de(CARPETA), ignore_errors=True)
        shutil.rmtree(CARPETA, ignore_errors=True)


if __name__ == "__main__":
    main()
