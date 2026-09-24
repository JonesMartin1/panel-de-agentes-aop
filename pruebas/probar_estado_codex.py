"""El rollout de Codex distingue tarea activa de tarea terminada y expone `ts`."""
import json
import tempfile
import time
from pathlib import Path

from app.voz import sesiones_movil as sm


class ProcesoVivo:
    def poll(self):
        return None


def evento(tipo):
    return json.dumps({"type": "event_msg", "payload": {"type": tipo}})


viejo_sids = dict(sm._CODEX_SIDS)
viejo_barrida = sm._CODEX_BARRIDA[0]
viejo_en_curso = dict(sm.EN_CURSO)
try:
    with tempfile.TemporaryDirectory() as td:
        raiz = Path(td)
        rollout = raiz / "rollout-prueba.jsonl"
        sid = "estado-codex-prueba"
        rollout.write_text(evento("task_started") + "\n", encoding="utf-8")
        ahora = time.time()
        sm._CODEX_SIDS.clear()
        sm._CODEX_SIDS[sid] = {"ruta": str(rollout), "cwd": str(raiz),
                               "ts": ahora, "mtime": ahora}
        sm._CODEX_BARRIDA[0] = time.time() + 3600
        sm.EN_CURSO[sid] = ProcesoVivo()
        assert sm._codex_turno_activo(sid), "task_started no quedó trabajando"

        rollout.write_text(evento("task_started") + "\n" + ("x" * 2048) + "\n",
                           encoding="utf-8")
        assert sm._codex_turno_activo(sid, cola=1024), \
            "perdió el turno cuando task_started quedó fuera de la cola"

        rollout.write_text(evento("task_started") + "\n" + evento("task_complete") + "\n",
                           encoding="utf-8")
        assert not sm._codex_turno_activo(sid), "task_complete siguió trabajando"

        rollout.write_text(evento("task_started") + "\n", encoding="utf-8")
        sm.EN_CURSO.clear()
        assert not sm._codex_turno_activo(sid), "un registro huérfano quedó trabajando"

        filas = sm.codex_sesiones_de(raiz)
        fila = next(x for x in filas if x["id"] == sid)
        assert fila["ts"] == ahora, "Codex no expuso ts para el semáforo"
        assert fila["viva"] is False, "la terminada salió viva"
finally:
    sm._CODEX_SIDS.clear()
    sm._CODEX_SIDS.update(viejo_sids)
    sm._CODEX_BARRIDA[0] = viejo_barrida
    sm.EN_CURSO.clear()
    sm.EN_CURSO.update(viejo_en_curso)

print("TODO BIEN: trabajando, cola larga, terminado y ts de Codex")
