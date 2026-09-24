"""Portero de FIN DE TURNO: que ninguna sesion se vaya dejando una regla rota.

El gancho `pre-commit` (pruebas/gancho_pre_commit.sh) ya cubre al que commitea.
Este cubre al que NO commitea, que en este proyecto son casi todas las sesiones
del panel: trabajan, contestan y se van sin pasar por git.

La idea es de Ruben Marcus, que la tiene en su lista de pendientes con el nombre
"stop hooks": bloquear el fin del turno hasta que los invariantes den verde,
"para que los chequeos no se pudran en silencio".

Se engancha desde `.claude/settings.local.json`:

    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "..."}]}]}

Lee el JSON del gancho por stdin y contesta por stdout:
  - todo bien  -> no imprime nada y sale con 0 (la sesion cierra normal)
  - algo roto  -> {"decision": "block", "reason": "..."} y la sesion tiene que
                  arreglarlo antes de irse.

⚠ `stop_hook_active` es el freno anti-bucle: cuando ya viene de un bloqueo,
NO vuelve a bloquear. Sin eso, un invariante que la sesion no sabe arreglar la
dejaria dando vueltas para siempre.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pruebas.probar_no_romper import INVARIANTES, MINIMO_INVARIANTES, rotos_ahora


def _entrada():
    """El JSON que manda el gancho. Si no viene o viene mal, seguimos igual: este
    portero no puede ser el motivo de que una sesion no cierre."""
    try:
        crudo = sys.stdin.read()
    except Exception:
        return {}
    try:
        return json.loads(crudo) if crudo.strip() else {}
    except Exception:
        return {}


def main():
    datos = _entrada()
    if datos.get("stop_hook_active"):
        return 0                      # ya viene rebotado: no lo trabo de nuevo

    problemas = []
    if len(INVARIANTES) < MINIMO_INVARIANTES:
        problemas.append(
            f"Quedan {len(INVARIANTES)} invariantes y el piso es {MINIMO_INVARIANTES}: "
            "alguien saco uno de pruebas/probar_no_romper.py. Si fue a proposito, "
            "bajale el piso a mano y explica por que.")
    for inv, motivo in rotos_ahora():
        problemas.append(
            f"[{inv['clave']}] {inv['titulo']}\n"
            f"    Que pasa: {motivo}\n"
            f"    Por que importa: {inv['por_que']}")

    if not problemas:
        return 0

    razon = ("Antes de cerrar el turno: se rompio una regla de \"No romper (costaron "
             "sangre)\" del CLAUDE.md.\n\n" + "\n\n".join(problemas) +
             "\n\nArreglalo, o si es a proposito decilo en PIZARRA.md y en el CLAUDE.md. "
             "Para verlo entero: python -m pruebas.probar_no_romper --todo")
    print(json.dumps({"decision": "block", "reason": razon}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
