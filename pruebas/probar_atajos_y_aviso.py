"""Dos cosas chicas del 2026-08-25, las dos sin navegador ni tokens:

1. **El menu ⚡ en una charla de CODEX** lista los prompts propios de Codex
   (`~/.codex/prompts`), no las skills de Claude — decision de Martin del 2026-08-23.
   Y si todavia no creo ninguno, el menu tiene que poder decirlo: por eso el endpoint
   manda tambien la carpeta donde se crean.
2. **El aviso al celular cuando termina una tarea** tiene que decir QUE termino. Hasta
   hoy decia siempre "la tarea larga de Codex" —aunque fuera Claude— y no nombraba ni
   el proyecto ni la charla. Eso se lee en el telefono, sin la pantalla al lado.

    python -m pruebas.probar_atajos_y_aviso
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import panel                                              # noqa: E402
from app.nucleo import skills                             # noqa: E402
from app.voz import sesiones_movil as sm                   # noqa: E402

BIEN, MAL = [], []
CWD = str(Path(__file__).resolve().parent.parent)
SID_CDX = "cdx-atajos-1"


def probar(nombre, cond, detalle=""):
    (BIEN if cond else MAL).append(nombre)
    print(("  ok  " if cond else "  MAL ") + nombre +
          (f"   [{detalle}]" if detalle and not cond else ""))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="atajos_aviso_"))
    sm._CODEX_SIDS[SID_CDX] = {"ruta": str(tmp / "no-existe.jsonl")}

    print("--- Sin ningun prompt creado, el menu no miente ---")
    vacia = tmp / "prompts_que_no_existen"
    skills.CARPETA_PROMPTS_CODEX = vacia
    probar("no inventa prompts que no estan", skills.prompts_codex() == [])
    r = panel.skills_de_sesion(sid=SID_CDX, cwd=CWD)
    probar("el menu sabe que la charla es de Codex", r.get("cerebro") == "codex")
    # ⚠⚠ Este chequeo decia lo contrario hasta el 2026-08-28: exigia `skills == []` con
    # el nombre "no le manda skills de Claude, que ahi no andan". Era falso — las skills
    # estan enlazadas en `~/.codex/skills` desde el 19/08 y Codex las usa — y la prueba
    # sostenia la creencia equivocada en vez de cazarla. Se da vuelta a proposito.
    cod_reales = tmp / "codex_skills"
    (cod_reales / "pizarra").mkdir(parents=True)
    (cod_reales / "pizarra" / "SKILL.md").write_text(
        "---\nname: pizarra\ndescription: El pizarron visual.\n---\n", encoding="utf-8")
    skills.CARPETA_SKILLS_CODEX = cod_reales
    skills.CARPETA_SKILLS_AGENTS = tmp / "agents_que_no_existen"
    r = panel.skills_de_sesion(sid=SID_CDX, cwd=CWD)
    probar("SI le manda las skills que Codex tiene de verdad",
           [s["nombre"] for s in (r.get("skills") or [])] == ["pizarra"],
           str(r.get("skills")))
    probar("y dice DONDE estan enlazadas, para poder explicarlo",
           str(cod_reales) in (r.get("carpeta_skills") or ""), r.get("carpeta_skills"))
    probar("los prompts siguen siendo otra cosa, y siguen vacios",
           r.get("prompts") == [])
    probar("y dice DONDE se crean, para poder explicarlo",
           str(vacia) in (r.get("carpeta") or ""), r.get("carpeta"))

    print("\n--- Con prompts creados, los lista ---")
    carpeta = tmp / "prompts"
    carpeta.mkdir()
    (carpeta / "deploy.md").write_text(
        "---\ndescription: Subir al VPS y reiniciar\n---\nHace el deploy.",
        encoding="utf-8")
    (carpeta / "repasar.md").write_text("# Repasar la rama\nMira los commits.",
                                        encoding="utf-8")
    skills.CARPETA_PROMPTS_CODEX = carpeta
    lista = skills.prompts_codex()
    nombres = [p["nombre"] for p in lista]
    probar("aparecen los dos", sorted(nombres) == ["deploy", "repasar"], str(nombres))
    d = next(p for p in lista if p["nombre"] == "deploy")
    probar("la descripcion sale del encabezado", d["descripcion"] == "Subir al VPS y reiniciar")
    rep = next(p for p in lista if p["nombre"] == "repasar")
    probar("y si no tiene encabezado, del primer renglon",
           "Repasar" in rep["descripcion"], rep["descripcion"])
    r = panel.skills_de_sesion(sid=SID_CDX, cwd=CWD)
    probar("el endpoint los devuelve", len(r.get("prompts") or []) == 2)

    print("\n--- Una charla de Claude sigue viendo sus skills, no los prompts ---")
    r = panel.skills_de_sesion(sid="una-de-claude-que-no-existe", cwd=CWD)
    probar("no la trata como de Codex", r.get("cerebro") != "codex")
    probar("y le manda el catalogo de skills", isinstance(r.get("skills"), list))
    probar("sin prompts de Codex mezclados", "prompts" not in r)

    print("\n--- El aviso al celular dice QUE paso ---")
    t = panel._aviso_tarea(CWD, {"ok": True, "cerebro": "codex", "sid": SID_CDX,
                                 "respuesta": "Listo, quedo arreglado el boton."},
                           "terminado")
    probar("nombra el cerebro de verdad", "Codex" in t, t)
    probar("nombra el proyecto", "wpp-transcriptor" in t, t)
    probar("y cuenta como arranca la respuesta", "quedo arreglado el boton" in t, t)

    t = panel._aviso_tarea(CWD, {"ok": True, "cerebro": "", "sid": "",
                                 "respuesta": "Hecho."}, "terminado")
    probar("una charla de Claude NO se avisa como Codex",
           "Claude" in t and "Codex" not in t, t)

    t = panel._aviso_tarea(CWD, {"ok": False, "cerebro": "codex", "sid": SID_CDX,
                                 "error": "se corto la red"}, "fallo")
    probar("cuando falla, dice por que", "se corto la red" in t, t)
    probar("y se nota que fallo", t.lower().startswith("fall"), t)

    largo = panel._aviso_tarea(CWD, {"ok": True, "cerebro": "", "sid": "",
                                     "respuesta": "x" * 5000}, "terminado")
    probar("una respuesta larguisima no manda una novela al telefono",
           len(largo) < 400, str(len(largo)))

    print(f"\n{len(BIEN)} bien, {len(MAL)} mal")
    for m in MAL:
        print("   MAL:", m)
    print("temporal:", tmp)
    return 1 if MAL else 0


if __name__ == "__main__":
    sys.exit(main())
