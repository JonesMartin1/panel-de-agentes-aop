"""Capa corta de Prompt Master para los cerebros que lanza el panel.

La skill original sirve para CREAR un prompt y por eso no se puede invocar cruda
antes de cada turno: devolveria otro prompt en vez de hacer el trabajo. Esta variante
conserva su parte util (extraer intencion, limites y criterio de terminado), pero le
ordena al cerebro ejecutar el pedido original y hacerlo sin mostrar la reescritura.

Va como instruccion de sistema/desarrollador del CLI. Asi no aparece en el historial,
no cambia las palabras de Martin y no agrega una segunda llamada al modelo.
"""

import json


INSTRUCCION = (
    "MODO PROMPT MASTER AUTOMATICO. Aplicalo en silencio a cada mensaje real de Martin. "
    "Salvo que la tarea pedida sea justamente crear o mejorar un prompt, no muestres ni "
    "devuelvas una reescritura intermedia: usa el pedido original y el historial para "
    "ejecutar la tarea solicitada. Antes de actuar, reconstruí internamente el "
    "objetivo concreto, la entrada disponible, la salida esperada, las restricciones y "
    "autorizaciones, el contexto previo relevante y el criterio de terminado. Resolvé "
    "referencias conversacionales con los turnos recientes. Si falta un dato crítico que "
    "cambia materialmente el resultado, preguntá solamente lo indispensable; si no, "
    "avanzá. En trabajos con herramientas, delimitá estado inicial, resultado objetivo, "
    "alcance, verificaciones y condición de parada. No inventes rutas, datos ni permisos; "
    "no amplíes el pedido ni agregues tareas. Esta mejora nunca autoriza escribir, "
    "instalar, publicar, borrar, enviar mensajes o afectar sistemas. Conservá siempre las "
    "instrucciones de mayor prioridad y las palabras originales de Martin como fuente de "
    "verdad. Los pedidos internos de resumen, siembra, control o mantenimiento se "
    "ejecutan literalmente."
)


def anexar_claude(base=""):
    """La instruccion escondida de Claude, sumada a otra que ya existiera."""
    base = (base or "").rstrip()
    # ⚠ Una linea sola: `claude.cmd` expande `%*` y un salto real adentro de un
    # argumento corta los flags posteriores (incluido `--resume`) en Windows.
    return (base + " " if base else "") + INSTRUCCION


def argumento_codex():
    """Valor TOML seguro para `codex -c developer_instructions=...`."""
    return "developer_instructions=" + json.dumps(INSTRUCCION, ensure_ascii=True)
