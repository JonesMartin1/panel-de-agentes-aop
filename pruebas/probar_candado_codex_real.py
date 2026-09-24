"""El panel no acepta otro mensaje si Codex sigue escribiendo de verdad.

Reproduce las dos capturas de Martin del 2026-08-25: el proceso de Codex seguia vivo,
pero el set en memoria del panel habia perdido el id. `/movil/chat` decia libre y el
celular lanzaba otro `codex resume`; recien el CLI lo frenaba con `thread-store conflict`.

No arranca Codex ni toca una charla real.
"""
import sys

from fastapi.testclient import TestClient

import panel
from app.voz import sesiones_movil as sm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SID = "01a030ae-prueba-candado-real"
CWD = r"C:\EspacioDeTrabajo\Portafolio"

bien = malo = 0


def revisar(condicion, texto):
    global bien, malo
    if condicion:
        bien += 1
        print("ok  ", texto)
    else:
        malo += 1
        print("MAL ", texto)


original_es_codex = sm.es_codex
original_activo = sm._codex_turno_activo
original_conversacion = sm.conversacion
original_pregunta = sm.pregunta_de
original_tareas = sm.tareas_de
turnos_anteriores = set(panel._TURNOS_ABIERTOS)

try:
    sm.es_codex = lambda sid: sid == SID
    sm._codex_turno_activo = lambda sid: sid == SID
    sm.conversacion = lambda cwd, sid, ultimos=40: []
    sm.pregunta_de = lambda cwd, sid: None
    sm.tareas_de = lambda cwd, sid: None
    panel._TURNOS_ABIERTOS.clear()       # la condicion exacta del incidente

    cliente = TestClient(panel.app)

    chat = cliente.get("/movil/chat", params={"cwd": CWD, "sid": SID}).json()
    revisar(chat.get("ocupada") is True,
            "el chat ve trabajando aunque el set en memoria este vacio")

    respuesta = cliente.post("/movil/mandar", data={
        "cwd": CWD, "sid": SID, "texto": "un buen modelo", "segundo_plano": "1"
    }).json()
    revisar(respuesta.get("ok") is False,
            "el servidor rechaza el segundo envio antes de abrir otro Codex")
    revisar("contestando" in respuesta.get("error", ""),
            "y devuelve el aviso corto, no thread-store conflict")
    revisar(not panel._TRABAJOS_MOVIL,
            "no deja un trabajo fantasma por el envio rechazado")
finally:
    sm.es_codex = original_es_codex
    sm._codex_turno_activo = original_activo
    sm.conversacion = original_conversacion
    sm.pregunta_de = original_pregunta
    sm.tareas_de = original_tareas
    panel._TURNOS_ABIERTOS.clear()
    panel._TURNOS_ABIERTOS.update(turnos_anteriores)

print(f"\n{bien} en verde, {malo} en rojo")
if malo:
    raise SystemExit(1)
