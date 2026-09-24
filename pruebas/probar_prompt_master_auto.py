"""Prompt Master llega escondido a los cuatro lanzadores, sin gastar turnos reales."""

import json
import tomllib

from app.voz import claude_voz, codex_voz
from app.voz import prompt_master_auto as pm
from app.voz import sesiones_movil as sm


VERDES = []
ROJOS = []


def probar(nombre, condicion):
    (VERDES if condicion else ROJOS).append(nombre)
    print(("ok   " if condicion else "MAL  ") + nombre)


def instruccion_codex(args):
    valores = [args[i + 1] for i, valor in enumerate(args[:-1])
               if valor == "-c" and args[i + 1].startswith("developer_instructions=")]
    if len(valores) != 1:
        return None
    return tomllib.loads(valores[0]).get("developer_instructions")


class Entrada:
    def __init__(self):
        self.texto = ""

    def write(self, texto):
        self.texto += texto

    def close(self):
        pass


class Proceso:
    _pid = 910_000

    def __init__(self, cmd):
        Proceso._pid += 1
        self.pid = Proceso._pid
        self.cmd = cmd
        self.stdin = Entrada()
        self.stderr = iter(())
        if "exec" in cmd:
            self.stdout = iter([
                json.dumps({"type": "thread.started", "thread_id": "sid-nuevo"}) + "\n",
                json.dumps({"type": "item.completed", "item": {
                    "type": "agent_message", "text": "ok"}}) + "\n",
            ])
        else:
            self.stdout = iter(())
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.returncode = -1


comandos = []
procesos = []


def popen_falso(cmd, **_kwargs):
    comandos.append(cmd)
    p = Proceso(cmd)
    procesos.append(p)
    return p


def main():
    probar("la instrucción automática es compacta", len(pm.INSTRUCCION) < 1800)
    probar("no tiene saltos que corten claude.cmd", "\n" not in pm.INSTRUCCION)
    probar("la mejora normal no devuelve otro prompt",
           "no muestres ni devuelvas una reescritura intermedia" in pm.INSTRUCCION)
    probar("crear un prompt sigue permitido",
           "Salvo que la tarea pedida sea justamente crear o mejorar un prompt"
           in pm.INSTRUCCION)
    probar("conserva los permisos del pedido original",
           "nunca autoriza" in pm.INSTRUCCION
           and "instrucciones de mayor prioridad" in pm.INSTRUCCION)

    junto = pm.anexar_claude("REGLAS BASE")
    probar("se anexa sin borrar las reglas anteriores",
           junto.startswith("REGLAS BASE") and junto.endswith(pm.INSTRUCCION))
    probar("el valor de Codex es TOML válido",
           tomllib.loads(pm.argumento_codex())["developer_instructions"] == pm.INSTRUCCION)

    args_claude = claude_voz._args_comunes()
    i = args_claude.index("--append-system-prompt")
    oculto_claude = args_claude[i + 1]
    probar("Laura Claude recibe Prompt Master",
           claude_voz.SYSTEM in oculto_claude and pm.INSTRUCCION in oculto_claude)

    args_codex = codex_voz._args_comunes()
    probar("Laura Codex recibe Prompt Master", instruccion_codex(args_codex) == pm.INSTRUCCION)

    popen_real = sm.subprocess.Popen
    barrendero_real = sm._arrancar_barrendero
    try:
        sm.subprocess.Popen = popen_falso
        sm._arrancar_barrendero = lambda: None

        viva = sm._arrancar_viva("D:/IA/wpp-transcriptor", "", "haiku", "")
        cmd_claude = comandos[-1]
        j = cmd_claude.index("--append-system-prompt")
        probar("Sesiones Claude recibe Prompt Master", cmd_claude[j + 1] == pm.INSTRUCCION)

        respuesta, _ = sm.codex_mandar(
            "D:/IA/wpp-transcriptor", "sid", "mensaje original",
            "gpt-5.6-luna", "low", "")
        cmd_codex = comandos[-1]
        probar("Sesiones Codex recibe Prompt Master",
               instruccion_codex(cmd_codex) == pm.INSTRUCCION and respuesta == "ok")
        probar("el mensaje original llega intacto",
               procesos[-1].stdin.texto == "mensaje original")
    finally:
        sm.subprocess.Popen = popen_real
        sm._arrancar_barrendero = barrendero_real
        sm.VIVAS.clear()
        sm.EN_CURSO.clear()
        sm.seguir.PIDS_PANEL.clear()

    print("%d en verde, %d en rojo" % (len(VERDES), len(ROJOS)))
    if ROJOS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
