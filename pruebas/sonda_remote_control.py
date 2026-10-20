"""Sonda contra el CLI de VERDAD: ¿se puede prender el Remote Control desde el panel?

No gasta tokens: no se manda ningun mensaje, solo el pedido de control.

Lo que hace el Claude Desktop por dentro (leido en el binario 2.1.296): un
`control_request` con `subtype: "remote_control"` y `enabled: true|false`. Esta sonda:
  1. arranca el CLI como lo arranca el panel (`-p` stream-json, proceso vivo);
  2. prende el control remoto y anota la respuesta (las claves; los secretos se tapan);
  3. escucha unos segundos lo que el CLI escribe SOLO, fuera de un turno;
  4. lo apaga y cierra.

Corre en una carpeta temporal y se limpia sola.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_remote_control
"""
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.voz import seguir  # noqa: E402
from app.voz import sesiones_movil as sm  # noqa: E402

CARPETA = Path(tempfile.mkdtemp(prefix="sonda_rc_"))
SECRETOS = ("secret", "token", "key")


def tapar(v):
    """Lo que tenga cara de secreto se muestra solo por su largo."""
    if isinstance(v, dict):
        return {k: (f"<{len(str(x))} letras>" if any(s in k.lower() for s in SECRETOS)
                    else tapar(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [tapar(x) for x in v]
    return v


def main():
    cmd = [sm._claude_bin(), "-p", "--input-format", "stream-json", "--output-format",
           "stream-json", "--verbose", "--model", "haiku",
           "--permission-prompt-tool", "stdio"]
    p = subprocess.Popen(cmd, cwd=str(CARPETA), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", bufsize=1,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    cola = queue.Queue()
    threading.Thread(target=lambda: [cola.put(l) for l in p.stdout], daemon=True).start()

    def pedir(rid, req):
        p.stdin.write(json.dumps({"type": "control_request", "request_id": rid,
                                  "request": req}) + "\n")
        p.stdin.flush()

    def escuchar(seg, rid=None):
        fin, vistos = time.time() + seg, []
        while time.time() < fin:
            try:
                l = cola.get(timeout=0.5).strip()
            except queue.Empty:
                continue
            try:
                d = json.loads(l)
            except Exception:
                vistos.append(("texto", l[:120]))
                continue
            vistos.append((d.get("type"), d.get("subtype") or
                           (d.get("response") or {}).get("subtype")))
            if rid and d.get("type") == "control_response" and \
                    (d.get("response") or {}).get("request_id") == rid:
                return d, vistos
        return None, vistos

    try:
        r, vistos = None, []
        pedir("rc-on", {"subtype": "remote_control", "enabled": True, "name": "sonda-panel"})
        r, vistos = escuchar(40, "rc-on")
        print("1) respuesta al prender:", json.dumps(tapar(r), ensure_ascii=False)[:1500])
        print("   lineas en el medio:", vistos[:20])
        _, solos = escuchar(15)
        print("2) lo que escribio solo, fuera de turno (15 s):", solos[:20])
        pedir("rc-off", {"subtype": "remote_control", "enabled": False})
        r2, _ = escuchar(20, "rc-off")
        print("3) respuesta al apagar:", json.dumps(tapar(r2), ensure_ascii=False)[:600])
    finally:
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=10)
        except Exception:
            sm._matar_arbol(p)
        err = p.stderr.read()[-800:] if p.stderr else ""
        if err.strip():
            print("stderr:", err)
        shutil.rmtree(seguir.carpeta_de(CARPETA), ignore_errors=True)
        shutil.rmtree(CARPETA, ignore_errors=True)


if __name__ == "__main__":
    main()
