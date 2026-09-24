"""Plan mode en las sesiones del panel: primero el plan, despues los cambios.

Pedido de Martin el 2026-08-20: las opciones de plan mode de Claude Code, en las
sesiones del panel. En "plan" el CLI trabaja solo lectura, arma un plan y frena a
pedir permiso (ExitPlanMode por stdio, medido ese dia con el CLI real); la pantalla
lo muestra como tarjeta en el hilo y Martin lo aprueba o pide cambios. Aprobado, el
CLI sale solo de plan mode y ejecuta en el mismo turno — por eso aca ademas se
limpia el modo guardado.

Aca no se habla con Claude de verdad: se falsean el proceso y los archivos.

    python -m pruebas.probar_plan_sesiones
"""
import json
import re
import tempfile
import threading
from pathlib import Path

from app.voz import sesiones_movil as sm

ok = fallo = 0


def probar(que, condicion):
    global ok, fallo
    if condicion:
        ok += 1
        print("  ok   ", que)
    else:
        fallo += 1
        print("  FALLA", que)


class ProcFalso:
    """Un stdin que anota lo que el panel le escribe al CLI."""

    def __init__(self):
        self.escrito = []
        self.stdin = self

    def write(self, s):
        self.escrito.append(s)

    def flush(self):
        pass

    def lineas(self):
        return [json.loads(l) for l in self.escrito]


class VivaFalsa:
    def __init__(self, sid, modo):
        self.sid, self.modo = sid, modo


# Los ajustes van a un archivo de mentira: la perilla real de Martin no se toca.
_tmp = Path(tempfile.mkdtemp()) / "ajustes.json"
_ajustes_real = sm.AJUSTES_SESIONES
sm.AJUSTES_SESIONES = _tmp

try:
    print("\n--- La perilla del modo, guardada por sesion ---")
    probar("de fabrica es el normal", sm.modo_de("s1") == "")
    probar("poner plan lo devuelve", sm.poner_modo("s1", "plan") == "plan")
    probar("y queda guardado", sm.modo_de("s1") == "plan")
    probar("un modo inventado cae al normal", sm.poner_modo("s1", "turbo") == "")
    probar("MODOS tiene normal y plan", set(sm.MODOS) == {"", "plan"})

    print("\n--- El plan pendiente, visto por la pantalla ---")
    clave = sm._clave("D:/x", "s1")
    proc = ProcFalso()
    viva = VivaFalsa("s1", "plan")
    ent = {"request_id": "r1", "tipo": "plan",
           "input": {"plan": "## Plan\n1. tocar tal archivo", "planFilePath": "p.md"},
           "hora": 123.0, "proc": proc, "candado": threading.Lock(), "viva": viva}
    sm.PREGUNTAS[clave] = dict(ent)
    p = sm.pregunta_de("D:/x", "s1")
    probar("llega como plan", p and p.get("plan", "").startswith("## Plan"))
    probar("sin lista de preguntas", p and "preguntas" not in p)
    probar("con su hora", p and p.get("hora") == 123.0)

    print("\n--- responder_pregunta NO se lo puede llevar por delante ---")
    probar("dice que no", sm.responder_pregunta("D:/x", "s1", {"a": "b"}) is False)
    probar("y el plan sigue pendiente", clave in sm.PREGUNTAS)
    probar("sin escribirle nada al CLI", proc.escrito == [])

    print("\n--- Rechazado con comentario: sigue planeando ---")
    sm.poner_modo("s1", "plan")
    probar("habia plan", sm.responder_plan("D:/x", "s1", False, "sin la parte 2") is True)
    d = proc.lineas()[-1]["response"]["response"]
    probar("es un deny", d["behavior"] == "deny")
    probar("con el comentario adentro", "sin la parte 2" in d["message"])
    probar("el pendiente se fue", clave not in sm.PREGUNTAS)
    probar("la sesion sigue en plan", sm.modo_de("s1") == "plan")
    probar("la viva tambien", viva.modo == "plan")

    print("\n--- Aprobado: ejecuta y sale de plan mode ---")
    proc.escrito.clear()
    sm.PREGUNTAS[clave] = dict(ent)
    probar("habia plan", sm.responder_plan("D:/x", "s1", True) is True)
    d = proc.lineas()[-1]["response"]["response"]
    probar("es un allow", d["behavior"] == "allow")
    probar("con el input tal cual", d["updatedInput"] == ent["input"])
    probar("el modo guardado vuelve a normal", sm.modo_de("s1") == "")
    probar("la viva tambien", viva.modo == "")

    print("\n--- Sin plan pendiente, no hay nada que decidir ---")
    probar("dice que no", sm.responder_plan("D:/x", "s1", True) is False)

    print("\n--- El arranque del proceso, segun el modo ---")
    fuente = Path(sm.__file__).read_text(encoding="utf-8")
    probar("plan prende --permission-mode plan",
           '"plan" if modo == "plan" else "default"' in fuente)
    probar("el turno atiende ExitPlanMode", '"ExitPlanMode"' in fuente)
    probar("mandar le pasa el modo al proceso", "modo_de(sid))" in fuente)
    probar("cambiar el modo rearranca el proceso", '"cambio el modo"' in fuente)

    print("\n--- Las pantallas y los endpoints ---")
    panel = (Path(sm.__file__).parents[2] / "panel.py").read_text(encoding="utf-8")
    compu = (Path(sm.__file__).parents[2] / "app" / "estaticos" /
             "sesiones.html").read_text(encoding="utf-8")
    probar("endpoint del modo", '@app.post("/movil/modo")' in panel)
    probar("endpoint del plan", '@app.post("/movil/plan")' in panel)
    probar("el modo viaja en /movil/modelo", '"modos":' in panel.replace(" ", ""))
    for nombre, src in (("celular", panel), ("compu", compu)):
        probar("tarjeta del plan en la pantalla %s" % nombre, "htmlPlan" in src)
        probar("aprobar desde la pantalla %s" % nombre, "responderPlan(true)" in src)
        probar("la pantalla %s deja ver planes pendientes" % nombre,
               "d.pregunta.plan" in src)
    probar("selector de modo en el celular", "cambiarModoSes" in panel)
    probar("selector de modo en la compu", "$('#modo')" in compu)

    # ⭐ 2026-08-25: hasta ese dia esta prueba afirmaba lo contrario ("Codex no tiene
    # plan mode aca") y el endpoint lo rechazaba a mano. Ahora Codex tambien lo tiene,
    # emulado con la jaula de solo lectura. El detalle vive en `probar_plan_codex.py`;
    # aca solo se cuida que el bloqueo viejo no vuelva por descuido.
    print("\n--- Codex tambien tiene plan mode (2026-08-25) ---")
    probar("el endpoint ya no lo rechaza",
           "Las charlas de Codex no tienen plan mode" not in panel)
    probar("y el selector de modo le llega a una charla de Codex",
           '"modo": "", "modos": []' not in panel)
finally:
    sm.AJUSTES_SESIONES = _ajustes_real
    sm.PREGUNTAS.clear()

print("\n%d bien, %d mal" % (ok, fallo))
raise SystemExit(1 if fallo else 0)
