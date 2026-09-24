"""Plan mode en las charlas de CODEX (2026-08-25).

Pedido de Martin: *"no tengo la opcion en codex para el modo plan, fijate bien"*. Tenia
razon, y estaba bloqueado a proposito. Codex SI tiene plan mode, pero vive en el canal
`app-server` que usa la app de escritorio; a `codex exec` —por donde entra el panel— no
se le puede pedir (`-c collaboration_mode=plan` contesta `unknown configuration field`).
Asi que el del panel es EMULADO, y lo que de verdad garantiza que no toque nada es la
jaula de solo lectura. **Eso es lo primero que mira esta prueba.**

No abre ningun navegador ni gasta un token: reemplaza el proceso de Codex por uno de
mentira que anota con que argumentos lo llamaron y contesta un plan escrito a mano.

    python -m pruebas.probar_plan_codex
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import panel                                              # noqa: E402
from app.voz import sesiones_movil as sm                   # noqa: E402

BIEN, MAL = [], []
CWD = str(Path(__file__).resolve().parent.parent)
SID = "cdx-de-mentira-1"


def probar(nombre, cond, detalle=""):
    (BIEN if cond else MAL).append(nombre)
    print(("  ok  " if cond else "  MAL ") + nombre +
          (f"   [{detalle}]" if detalle and not cond else ""))


class Pedido:
    """Lo minimo que los endpoints usan de un Request: `await request.json()`."""

    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


# --- El Codex de mentira ----------------------------------------------------------
# Habla el mismo protocolo que `codex exec --json`: un JSON por linea en stdout, con
# `thread.started` primero y el `item.completed` con la respuesta despues. Lo unico que
# agrega es dejar anotado en LLAMADAS con que argumentos y con que texto lo llamaron.

LLAMADAS = []
RESPUESTA = ["Plan: 1) mirar el archivo, 2) cambiar la funcion, 3) correr la prueba."]


class _Entrada:
    def __init__(self, caja):
        self.caja = caja

    def write(self, t):
        self.caja.append(t)

    def close(self):
        pass

    def reconfigure(self, **kw):
        pass

    def flush(self):
        pass


class _ProcesoFalso:
    def __init__(self, cmd):
        self.pid = -1
        self.returncode = None
        self._texto = []
        self.stdin = _Entrada(self._texto)
        self.stderr = iter(())
        LLAMADAS.append({"cmd": cmd, "texto": self._texto})
        lineas = [json.dumps({"type": "thread.started", "thread_id": SID}),
                  json.dumps({"type": "item.completed",
                              "item": {"type": "agent_message",
                                       "text": RESPUESTA[0]}})]
        self.stdout = iter(l + "\n" for l in lineas)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -1


class _SubprocesoFalso:
    """Se pone en lugar del modulo `subprocess` adentro de sesiones_movil."""

    PIPE = -1

    @staticmethod
    def Popen(cmd, **kw):
        p = _ProcesoFalso(cmd)
        p.returncode = 0          # ya "termino": el lector corta y no espera de gusto
        return p


def ultima():
    return LLAMADAS[-1] if LLAMADAS else {"cmd": [], "texto": []}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="plan_codex_"))
    sm.AJUSTES_SESIONES = tmp / "ajustes_sesiones.json"
    # Que el panel crea que esta charla es de Codex sin ir a leer ~/.codex.
    sm._CODEX_SIDS[SID] = {"ruta": str(tmp / "no-existe.jsonl")}
    real_subprocess = sm.subprocess
    sm.subprocess = _SubprocesoFalso

    print("--- La perilla existe para Codex (antes estaba bloqueada) ---")
    r = asyncio.run(panel.movil_modo_poner(Pedido({"sid": SID, "modo": "plan"})))
    probar("el panel deja poner plan mode en una charla de Codex", r.get("ok") is True)
    probar("y queda guardado", sm.modo_de(SID) == "plan")
    r = panel.movil_modelo_leer(sid=SID, cwd=CWD)          # este endpoint es sync
    probar("el selector de modo le llega a la pantalla",
           len(r.get("modos") or []) >= 2, str(r.get("modos")))
    probar("con el plan puesto marcado", r.get("modo") == "plan")

    print("\n--- ⭐ Lo que importa: el turno corre con el disco en SOLO LECTURA ---")
    LLAMADAS.clear()
    respuesta, sid = sm.mandar(CWD, SID, "cambiame el color del boton")
    cmd = ultima()["cmd"]
    probar("va con --sandbox read-only",
           "read-only" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only",
           " ".join(str(x) for x in cmd))
    probar("y NUNCA con acceso completo", "danger-full-access" not in cmd)
    probar("y tampoco con permiso de escritura en la carpeta",
           "workspace-write" not in cmd)
    mandado = "".join(ultima()["texto"])
    probar("el mensaje va con la instruccion de planear adelante",
           mandado.startswith("[MODO PLAN"))
    probar("y lo que pediste sigue estando", "cambiame el color del boton" in mandado)

    print("\n--- La respuesta ES el plan, y queda esperando tu decision ---")
    p = sm.pregunta_de(CWD, SID)
    probar("la pantalla ve un plan pendiente", bool(p and p.get("plan")))
    probar("marcado como de Codex", bool(p and p.get("codex")) is True)
    probar("con el texto que contesto Codex", (p or {}).get("plan") == RESPUESTA[0])
    probar("y NO se lo confunde con una pregunta de opciones",
           sm.responder_pregunta(CWD, SID, {"lo que sea": "si"}) is False)
    probar("el camino de Claude se niega a contestarlo (no tiene proceso vivo)",
           sm.responder_plan(CWD, SID, True) is False)
    probar("y el plan sigue esperando despues de ese intento",
           bool(sm.pregunta_de(CWD, SID)))

    print("\n--- Seguir planeando: no sale del modo y le llega el pedido de cambios ---")
    texto = asyncio.run(panel.movil_plan(Pedido(
        {"cwd": CWD, "sid": SID, "aprobar": False, "comentario": "tocá el CSS, no el HTML"})))
    probar("el panel devuelve el mensaje que hay que mandarle", bool(texto.get("mandar")))
    probar("que dice que todavia no", "no lo apruebo" in texto["mandar"])
    probar("y lleva tu comentario", "tocá el CSS" in texto["mandar"])
    probar("la charla SIGUE en plan mode", sm.modo_de(SID) == "plan")
    probar("y la tarjeta ya no esta colgada", sm.pregunta_de(CWD, SID) is None)
    probar("contestar dos veces el mismo plan no hace nada",
           asyncio.run(panel.movil_plan(Pedido(
               {"cwd": CWD, "sid": SID, "aprobar": False}))).get("ok") is False)

    print("\n--- Aprobar: sale del modo y el turno siguiente puede tocar archivos ---")
    LLAMADAS.clear()
    sm.mandar(CWD, SID, "dale de nuevo")                  # deja otro plan esperando
    texto = asyncio.run(panel.movil_plan(Pedido(
        {"cwd": CWD, "sid": SID, "aprobar": True})))
    probar("devuelve el mensaje de aprobado", "Aprobado" in (texto.get("mandar") or ""))
    probar("⭐ la charla SALE de plan mode", sm.modo_de(SID) == "")
    LLAMADAS.clear()
    sm.mandar(CWD, SID, texto["mandar"])
    cmd = ultima()["cmd"]
    probar("y ese turno ya NO va en solo lectura", "read-only" not in cmd,
           " ".join(str(x) for x in cmd))
    probar("sin la instruccion de planear pegada adelante",
           not "".join(ultima()["texto"]).startswith("[MODO PLAN"))

    print("\n--- Un mensaje escrito a mano descuelga la tarjeta ---")
    sm.poner_modo(SID, "plan")
    sm.mandar(CWD, SID, "otra cosa")
    probar("queda un plan esperando", bool(sm.pregunta_de(CWD, SID)))
    sm.poner_modo(SID, "")
    sm.mandar(CWD, SID, "mejor hacelo directo")
    probar("mandar otro mensaje saca el plan viejo de la pantalla",
           sm.pregunta_de(CWD, SID) is None)

    print("\n--- Codex sin plan mode se sigue comportando igual que siempre ---")
    LLAMADAS.clear()
    sm.mandar(CWD, SID, "hola")
    cmd = ultima()["cmd"]
    probar("la jaula vuelve a ser la de siempre", "read-only" not in cmd)
    probar("y el mensaje viaja pelado", "".join(ultima()["texto"]) == "hola")

    sm.subprocess = real_subprocess
    print(f"\n{len(BIEN)} bien, {len(MAL)} mal")
    for m in MAL:
        print("   MAL:", m)
    print("temporal:", tmp)
    return 1 if MAL else 0


if __name__ == "__main__":
    sys.exit(main())
