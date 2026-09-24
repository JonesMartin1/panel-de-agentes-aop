"""Un `claude -p --input-format stream-json` de mentira, para probar sin gastar tokens.

Habla el mismo protocolo que el CLI de verdad (un JSON por linea en stdin, mensajes
`result` por stdout) y sabe hacer las tres cosas que hay que probar:

  - `fondo`   : lanza un proceso hijo que vive 60 s (el equivalente a un `npm run build`
                mandado a segundo plano) y contesta con su pid.
  - `mirar`   : dice si ese hijo SIGUE VIVO. Con un proceso por turno, no llegaba nunca.
  - `largo`   : no contesta hasta que le manden el `interrupt` por stdin.

Cualquier otro texto se contesta al toque. Lo lanza `probar_sesion_persistente.py`.
"""
import json
import os
import subprocess
import sys
import time

import psutil


def main():
    argv = sys.argv[1:]
    sid = ""
    if "--resume" in argv:
        i = argv.index("--resume")
        if i + 1 < len(argv):
            sid = argv[i + 1]
    if not sid:
        sid = "ses-nacida-%d" % os.getpid()
    turno = 0
    hijo = None
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
        except Exception:
            continue
        if d.get("type") == "control_response":
            continue
        if d.get("type") == "control_request":
            # El interrupt del boton Parar: se corta el turno, el proceso sigue vivo.
            if (d.get("request") or {}).get("subtype") == "interrupt":
                print(json.dumps({"type": "control_response", "response": {
                    "subtype": "success", "request_id": d.get("request_id"),
                    "response": {}}}), flush=True)
                print(json.dumps({"type": "result", "subtype": "error_during_execution",
                                  "is_error": True, "result": "interrumpido",
                                  "session_id": sid}), flush=True)
            continue
        if d.get("type") != "user":
            continue
        turno += 1
        # El CLI de verdad abre cada turno con un `system`/`init` que ya trae el
        # session_id: es de ahi de donde la pantalla se entera del id de una charla
        # recien nacida sin esperar a que termine el turno (ver `probar_sid_al_nacer`).
        print(json.dumps({"type": "system", "subtype": "init", "session_id": sid,
                          "tools": []}), flush=True)
        texto = ""
        for c in ((d.get("message") or {}).get("content") or []):
            if isinstance(c, dict) and c.get("type") == "text":
                texto += c.get("text") or ""
        texto = texto.strip()
        if texto == "largo":
            continue                      # calladito hasta que llegue el interrupt
        if texto == "fondo":
            # Un hijo que sobrevive al turno: es lo que el bug mataba.
            hijo = subprocess.Popen([sys.executable, "-c",
                                     "import time; time.sleep(60)"])
            resp = "fondo %d" % hijo.pid
        elif texto == "mirar":
            vivo = "no"
            if hijo is not None:
                try:
                    vivo = "si" if psutil.pid_exists(hijo.pid) and \
                        psutil.Process(hijo.pid).status() != psutil.STATUS_ZOMBIE else "no"
                except Exception:
                    vivo = "no"
            resp = "hijo %s" % vivo
        elif texto == "lento":
            time.sleep(2)
            resp = "listo"
        else:
            resp = "turno %d pid %d texto %s" % (turno, os.getpid(), texto[:40])
        print(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                           "content": []}}), flush=True)
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                          "result": resp, "session_id": sid,
                          "turno": turno}), flush=True)


if __name__ == "__main__":
    main()
