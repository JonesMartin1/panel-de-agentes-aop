"""Las sesiones del panel pueden crear y guardar skills, y nada mas de `.claude`.

Pedido de Martin el 2026-11-11: le pedia al panel "crea una skill" y la sesion la dejaba
en C:\\tmp porque el portero le negaba escribir en ~/.claude/skills. Corre sin tokens:
    python -m pruebas.probar_permiso_skills
"""
from app.voz.sesiones_movil import _es_escritura_de_skill as es

CASOS = [
    # (herramienta, entrada, esperado)
    ("Write", {"file_path": r"C:\Users\marti\.claude\skills\video-tutorial\SKILL.md"}, True),
    ("Write", {"file_path": "C:/Users/marti/.claude/skills/video-tutorial/scripts/motor.py"}, True),
    ("Edit", {"file_path": r"C:\Users\marti\.claude\skills\avisar\SKILL.md"}, True),
    ("MultiEdit", {"file_path": r"D:\IA\repo\.claude\skills\x\SKILL.md"}, True),
    ("NotebookEdit", {"notebook_path": r"C:\Users\marti\.claude\skills\x\n.ipynb"}, True),
    # lo que NO tiene que pasar
    ("Write", {"file_path": r"C:\Users\marti\.claude\settings.json"}, False),
    ("Write", {"file_path": r"C:\Users\marti\.claude\kommo.json"}, False),
    ("Write", {"file_path": r"C:\Users\marti\.claude\skills"}, False),
    ("Write", {"file_path": r"C:\Users\marti\.claude\skills\..\settings.json"}, False),
    ("Write", {"file_path": r"C:\Users\marti\.claude\skills\x\..\..\telegram.json"}, False),
    ("Write", {"file_path": r"C:\Users\marti\skills\x\SKILL.md"}, False),
    ("Bash", {"command": r"cp a C:\Users\marti\.claude\skills\x\SKILL.md"}, False),
    ("Write", {}, False),
    (None, None, False),
]


def main():
    malos = 0
    for herr, ent, esperado in CASOS:
        dio = es(herr, ent)
        ok = dio == esperado
        malos += not ok
        print("ok " if ok else "MAL", herr, ent, "->", dio)
    print(f"{len(CASOS) - malos}/{len(CASOS)} bien")
    raise SystemExit(1 if malos else 0)


if __name__ == "__main__":
    main()
