"""Esfuerzo por sesión de Codex sin gastar ningún turno real."""
import json
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm
from app.voz import codex_voz


class Entrada:
    def write(self, _texto):
        pass

    def close(self):
        pass


class Proceso:
    def __init__(self, cmd, **_kwargs):
        comandos.append(cmd)
        self.stdin = Entrada()
        self.stderr = iter(())
        self.stdout = iter([
            json.dumps({"type": "thread.started", "thread_id": SID_NUEVO}) + "\n",
            json.dumps({"type": "item.completed", "item": {
                "type": "agent_message", "text": "ok"}}) + "\n",
        ])
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.returncode = -1


SID_NUEVO = "01a01fff-1111-2222-3333-444455556666"
comandos = []
fallas = []


def probar(nombre, condicion):
    print(("ok   " if condicion else "MAL  ") + nombre)
    if not condicion:
        fallas.append(nombre)


ruta_ajustes = sm.AJUSTES_SESIONES
popen = sm.subprocess.Popen
cupo = codex_voz.cupo
tmp = Path(tempfile.gettempdir()) / "prueba_esfuerzo_codex_sesiones.json"
tmp.write_text("{}", encoding="utf-8")
sm.AJUSTES_SESIONES = tmp
sm.subprocess.Popen = Proceso
try:
    probar("la lista de Codex coincide con el modelo",
           "ultra" in sm._codex_esfuerzos("gpt-5.6-sol")
           and "ultra" not in sm._codex_esfuerzos("gpt-5.6-luna"))
    probar("un nivel inválido vuelve al de fábrica",
           sm.poner_codex_esfuerzo("sid", "maximo-inventado") == "")
    sm.poner_codex_esfuerzo("sid", "high")
    probar("el nivel queda guardado por id", sm.codex_esfuerzo_de("sid") == "high")

    respuesta, _ = sm.codex_mandar("D:/IA/wpp-transcriptor", "sid", "hola")
    probar("el turno falso contestó", respuesta == "ok")
    probar("el CLI recibió el esfuerzo guardado",
           "model_reasoning_effort=high" in comandos[-1])

    respuesta, sid = sm.mandar("D:/IA/wpp-transcriptor", "", "hola",
                               "gpt-5.6-luna", "codex", "max", "priority")
    probar("una charla nueva devuelve su id", respuesta == "ok" and sid == SID_NUEVO)
    probar("el modelo elegido antes de nacer llega al CLI",
           "gpt-5.6-luna" in comandos[-1])
    probar("la perilla elegida antes de nacer llega al CLI",
           "model_reasoning_effort=max" in comandos[-1])
    probar("la velocidad rápida llega al CLI",
           'service_tier="priority"' in comandos[-1])
    probar("al nacer quedan persistidas las tres perillas",
           sm.codex_modelo_de(SID_NUEVO) == "gpt-5.6-luna"
           and sm.codex_esfuerzo_de(SID_NUEVO) == "max"
           and sm.codex_velocidad_de(SID_NUEVO) == "priority")

    codex_voz.cupo = lambda: {"usado": 20}
    probar("Auto manda una implementación técnica a Codex",
           sm.ruteo_automatico("implementá el endpoint del panel")[:2]
           == ("codex", "medium"))
    probar("Auto sube el esfuerzo para una auditoría difícil",
           sm.ruteo_automatico("auditá la seguridad del código")[:2]
           == ("codex", "high"))
    probar("Auto baja el esfuerzo para una consulta mecánica",
           sm.ruteo_automatico("listá los archivos del repo")[:2]
           == ("codex", "low"))
    probar("Auto deja una tarea general en Claude",
           sm.ruteo_automatico("redactá un mail para el equipo")[0] == "claude")
    codex_voz.cupo = lambda: {"usado": 95}
    cerebro, _, motivo = sm.ruteo_automatico("arreglá el bug del endpoint")
    probar("Auto evita Codex cuando está por quedarse sin cupo",
           cerebro == "claude" and "límite" in motivo)
finally:
    sm.AJUSTES_SESIONES = ruta_ajustes
    sm.subprocess.Popen = popen
    codex_voz.cupo = cupo
    tmp.unlink(missing_ok=True)

if fallas:
    raise SystemExit(1)
print("todo bien")
