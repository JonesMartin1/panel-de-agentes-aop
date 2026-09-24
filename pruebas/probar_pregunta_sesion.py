"""El selector de preguntas con opciones (AskUserQuestion): el flujo del backend.

Cuando una sesion del panel pregunta algo con opciones, `mandar()` (stream-json
bidireccional) recibe un `control_request` del CLI, lo publica en `PREGUNTAS`, la
pantalla lo ve por `pregunta_de()` y lo contesta `responder_pregunta()`, que escribe
el `control_response` con `updatedInput.answers`. Todo lo que NO sea AskUserQuestion
se deniega en el acto, igual que hacia dontAsk.

⚠ El `claude` de verdad no se toca: aca corre un CLI DE MENTIRA (un .cmd que lanza un
script python) que emite los mismos eventos que se midieron en vivo el 2026-08-18.
Probar con el real costaria un turno y dependeria de que el modelo quiera preguntar.

Correr con:  D:/IA/envs/wpp/python.exe -m pruebas.probar_pregunta_sesion
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voz import sesiones_movil as sm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
fallas = []


def revisar(que, obtenido, esperado=True):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


# --- El CLI de mentira -------------------------------------------------------------
# Emite lo mismo que el de verdad: primero pide permiso para un Bash (tiene que
# volver denegado, como con dontAsk), despues manda la pregunta con opciones, y al
# final devuelve en `result` TODO lo que le contestaron, para poder revisarlo.
FINTO_PY = '''
import json, os, sys
def w(d):
    sys.stdout.write(json.dumps(d) + "\\n"); sys.stdout.flush()
sys.stdin.readline()                    # el mensaje del usuario
# ⭐ El id de la charla viaja YA en el init, como hace el CLI de verdad: es lo que
# hace que la pantalla se mude al id real en plena pensada (ver PARTOS).
w({"type": "system", "subtype": "init", "session_id": "finto-123"})
w({"type": "assistant", "session_id": "finto-123", "message": {"role": "assistant",
   "content": [{"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
       {"content": "mirar el panel", "activeForm": "Mirando el panel",
        "status": "in_progress"}]}}]}})
w({"type": "control_request", "request_id": "r1",
   "request": {"subtype": "can_use_tool", "tool_name": "Bash",
               "input": {"command": "dir"}}})
r1 = json.loads(sys.stdin.readline())
w({"type": "control_request", "request_id": "r2",
   "request": {"subtype": "can_use_tool", "tool_name": "AskUserQuestion",
               "input": {"questions": [{
                   "question": "\\u00bfLa A o la B?", "header": "Letra",
                   "multiSelect": False,
                   "options": [{"label": "La A", "description": "la primera"},
                               {"label": "La B", "description": "la segunda"}]}]}}})
r2 = json.loads(sys.stdin.readline())
w({"type": "result", "subtype": "success", "is_error": False,
   "result": json.dumps({"r1": r1, "r2": r2}),
   "session_id": "finto-123"})
sys.stdin.read()                        # esperar a que mandar() cierre el stdin
'''


def preparar_finto(tmp):
    script = tmp / "finto_claude.py"
    script.write_text(FINTO_PY, encoding="utf-8")
    cmd = tmp / "finto_claude.cmd"
    # ⚠ Sin %* a proposito: el finto ignora las banderas (-p, --model, etc.).
    cmd.write_text('@echo off\r\nset PYTHONIOENCODING=utf-8\r\n'
                   f'"{sys.executable}" "{script}"\r\n', encoding="ascii")
    return cmd


def correr(contestar=None, espera=None, por_id=False):
    """Lanza mandar() con el finto en un hilo. `contestar(preg, sid)` corre cuando la
    pregunta aparece publicada; con `espera` se achica ESPERA_RESPUESTA (el caso
    de que nadie conteste).

    ⭐ Con `por_id=True` se imita lo que hace la pantalla de verdad en una charla
    NUEVA: se pasa `al_nacer` (como hace `/movil/mandar`) y, apenas el CLI anuncia el
    id, todo se pregunta y se contesta con ESE id, no con la carpeta.
    """
    vieja = sm.ESPERA_RESPUESTA
    if espera:
        sm.ESPERA_RESPUESTA = espera
    caja = {}
    nacidos = []

    def _turno():
        try:
            caja["r"] = sm.mandar(str(RAIZ), "", "hola finto",
                                  al_nacer=(nacidos.append if por_id else None))
        except Exception as e:
            caja["e"] = e

    h = threading.Thread(target=_turno)
    h.start()
    if contestar:
        fin = time.time() + 15
        preg = None
        while time.time() < fin and preg is None:
            if por_id and not nacidos:
                time.sleep(0.05)
                continue
            sid = nacidos[0] if por_id else ""
            preg = sm.pregunta_de(str(RAIZ), sid)
            if preg is None:
                time.sleep(0.05)
        caja["sid_nacido"] = nacidos[0] if nacidos else ""
        caja["preg"] = preg
        if preg:
            contestar(preg, caja["sid_nacido"])
    h.join(timeout=40)
    caja["colgado"] = h.is_alive()
    sm.ESPERA_RESPUESTA = vieja
    return caja


def main():
    tmp = Path(tempfile.mkdtemp(prefix="pregunta_finto_"))
    cmd = preparar_finto(tmp)
    bin_viejo = sm._claude_bin
    sm._claude_bin = lambda: str(cmd)
    try:
        # --- 1. La pregunta llega, se publica, se contesta con una opcion ---------
        caja = correr(contestar=lambda preg, sid: sm.responder_pregunta(
            str(RAIZ), "", {"¿La A o la B?": "La B"}))
        revisar("el turno termino", caja.get("colgado"), False)
        preg = caja.get("preg") or {}
        qs = preg.get("preguntas") or [{}]
        revisar("la pregunta se publico traducida", qs[0].get("pregunta"), "¿La A o la B?")
        revisar("con su titulo", qs[0].get("titulo"), "Letra")
        revisar("y sus opciones con detalle",
                [(o["etiqueta"], o["detalle"]) for o in qs[0].get("opciones", [])],
                [("La A", "la primera"), ("La B", "la segunda")])
        respuesta, sid = caja.get("r", ("", ""))
        revisar("el id de la sesion vuelve como siempre", sid, "finto-123")
        d = json.loads(respuesta or "{}")
        bash = ((d.get("r1") or {}).get("response") or {}).get("response") or {}
        revisar("el Bash volvio DENEGADO (el espiritu de dontAsk se mantiene)",
                bash.get("behavior"), "deny")
        revisar("con el mensaje de dontAsk",
                "dontAsk" in str(bash.get("message")), True)
        ask = ((d.get("r2") or {}).get("response") or {}).get("response") or {}
        revisar("la pregunta volvio PERMITIDA", ask.get("behavior"), "allow")
        revisar("con la eleccion adentro de updatedInput.answers",
                (ask.get("updatedInput") or {}).get("answers"),
                {"¿La A o la B?": "La B"})
        revisar("y las questions originales siguen en el updatedInput",
                len((ask.get("updatedInput") or {}).get("questions") or []), 1)
        revisar("no quedo pregunta pendiente", sm.pregunta_de(str(RAIZ), ""), None)
        revisar("ni proceso en curso", sm.EN_CURSO, {})

        # --- 1.b Charla NUEVA: la pregunta del primer turno, pedida por el id ------
        # ⚠⚠ El caso que estuvo roto hasta el 2026-09-13: el turno de una charla nueva
        # arranca como "nueva:<carpeta>" y ahi guarda la pregunta, pero la pantalla se
        # muda al id real apenas el CLI lo anuncia y desde entonces pregunta por ESE
        # id. Sin mirar los dos nombres, los botones no aparecian nunca en el primer
        # turno: la charla quedaba frenada esperandote con la pantalla en "pensando".
        # ⚠ `espera` corta a los 25 s a proposito: si esto se rompe, la pregunta nunca
        # aparece y el turno se quedaria los 10 minutos de ESPERA_RESPUESTA esperando a
        # un humano — o sea, la prueba parecia colgada en vez de fallar.
        caja = correr(por_id=True, espera=25,
                      contestar=lambda preg, sid: sm.responder_pregunta(
                          str(RAIZ), sid, {"¿La A o la B?": "La A"}))
        revisar("la charla nueva publico su id antes de preguntar",
                caja.get("sid_nacido"), "finto-123")
        revisar("la pregunta del PRIMER turno se ve pidiendola por el id real",
                bool((caja.get("preg") or {}).get("preguntas")), True)
        d = json.loads(caja.get("r", ("{}", ""))[0] or "{}")
        ask = ((d.get("r2") or {}).get("response") or {}).get("response") or {}
        revisar("y contestarla por el id real llega al CLI", ask.get("behavior"), "allow")
        revisar("con la eleccion adentro",
                (ask.get("updatedInput") or {}).get("answers"),
                {"¿La A o la B?": "La A"})
        revisar("la lista de tareas tambien se ve por el id real",
                [t["texto"] for t in
                 (sm.tareas_de(str(RAIZ), caja.get("sid_nacido")) or {}).get("lista", [])],
                ["mirar el panel"])
        revisar("el turno termino", caja.get("colgado"), False)

        # --- 2. Texto libre: si ninguna opcion sirve, va lo que escribiste --------
        caja = correr(contestar=lambda preg, sid: sm.responder_pregunta(
            str(RAIZ), "", {"cualquier llave": "que sean las dos, mitad y mitad"}))
        d = json.loads(caja.get("r", ("{}", ""))[0] or "{}")
        ask = ((d.get("r2") or {}).get("response") or {}).get("response") or {}
        revisar("el texto libre viaja igual que una opcion (con una sola pregunta "
                "la llave no importa)",
                (ask.get("updatedInput") or {}).get("answers"),
                {"¿La A o la B?": "que sean las dos, mitad y mitad"})

        # --- 3. Nadie contesta: se deniega sola y el turno sigue ------------------
        caja = correr(espera=3)
        revisar("sin respuesta el turno igual termina", caja.get("colgado"), False)
        d = json.loads(caja.get("r", ("{}", ""))[0] or "{}")
        ask = ((d.get("r2") or {}).get("response") or {}).get("response") or {}
        revisar("la pregunta colgada se deniega sola", ask.get("behavior"), "deny")
        revisar("diciendole al modelo que siga con su mejor criterio",
                "Nobody answered" in str(ask.get("message")), True)
        revisar("y no queda pendiente fantasma", sm.pregunta_de(str(RAIZ), ""), None)
    finally:
        sm._claude_bin = bin_viejo

    # --- 4. responder_pregunta a solas: varias preguntas, todas o ninguna ---------
    class FintoProc:
        def __init__(self):
            self.stdin = io.StringIO()

    clave_cwd, clave_sid = "C:/finto", "ses-finto"
    ent = {"request_id": "rX", "hora": time.time(), "proc": FintoProc(),
           "candado": threading.Lock(),
           "input": {"questions": [{"question": "uno"}, {"question": "dos"}]}}
    sm.PREGUNTAS[sm._clave(clave_cwd, clave_sid)] = ent
    revisar("faltando una respuesta NO se contesta",
            sm.responder_pregunta(clave_cwd, clave_sid, {"uno": "a"}), False)
    revisar("y la pregunta sigue pendiente",
            sm.pregunta_de(clave_cwd, clave_sid) is not None, True)
    revisar("con las dos respuestas si",
            sm.responder_pregunta(clave_cwd, clave_sid, {"uno": "a", "dos": "b"}), True)
    escrito = json.loads(ent["proc"].stdin.getvalue())
    revisar("el control_response lleva las dos",
            ((escrito.get("response") or {}).get("response") or {})
            .get("updatedInput", {}).get("answers"), {"uno": "a", "dos": "b"})
    revisar("y la pregunta se saco de pendientes",
            sm.pregunta_de(clave_cwd, clave_sid), None)
    revisar("contestar lo que ya no espera devuelve False",
            sm.responder_pregunta(clave_cwd, clave_sid, {"uno": "a"}), False)

    # --- 5. La sesion de Laura no se lista: _ids_laura() ---------------------------
    tmpj = tmp / "claude_sesion.json"
    ruta_vieja = sm.CLAUDE_SESION
    sm.CLAUDE_SESION = tmpj
    try:
        tmpj.write_text(json.dumps({
            "actual": {"session_id": "hoy-1"},
            "historial": [{"session_id": "ayer-1"}, {"session_id": "ayer-2"}]}),
            encoding="utf-8")
        revisar("junta la sesion de hoy Y las del historial",
                sm._ids_laura(), {"hoy-1", "ayer-1", "ayer-2"})
        tmpj.write_text(json.dumps({"actual": {"session_id": "hoy-2"},
                                    "historial": []}), encoding="utf-8")
        revisar("se RELEE cuando el archivo cambia (sin cache)",
                sm._ids_laura(), {"hoy-2"})
        tmpj.unlink()
        revisar("sin archivo, conjunto vacio y ningun error", sm._ids_laura(), set())
    finally:
        sm.CLAUDE_SESION = ruta_vieja

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
