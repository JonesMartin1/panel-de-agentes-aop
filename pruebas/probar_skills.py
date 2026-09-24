"""Prueba de app/nucleo/skills.py: el catalogo de skills y cuales uso cada sesion.

No toca ni la carpeta real de skills ni las transcripciones de verdad: arma las dos
de mentira y verifica que el catalogo se lea del frontmatter, que las skills usadas
se saquen del .jsonl (por la herramienta Skill Y por la barrita tipeada), que la
lectura sea incremental y que `ultima` se apague cuando el usuario vuelve a hablar.
Se corre con: python -m pruebas.probar_skills
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.nucleo import skills
from app.voz import seguir

OK = MAL = 0


def chequear(nombre, cond):
    global OK, MAL
    print(("  ok   " if cond else "  MAL  ") + nombre)
    if cond:
        OK += 1
    else:
        MAL += 1


def l_usuario(texto):
    return json.dumps({"type": "user", "message": {"content": texto}}) + "\n"


def l_skill(nombre):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": nombre}}]}}) + "\n"


def l_slash(comando):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "SlashCommand",
         "input": {"command": comando}}]}}) + "\n"


def l_resultado(texto):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": texto}]}}) + "\n"


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # --- el catalogo, leido del frontmatter -------------------------------------
    skills.CARPETA_SKILLS = tmp / "skills"
    skills.CARPETA_COMANDOS = tmp / "commands"
    skills.CARPETA_PLUGINS = tmp / "plugins"
    (skills.CARPETA_SKILLS / "avisar").mkdir(parents=True)
    (skills.CARPETA_SKILLS / "avisar" / "SKILL.md").write_text(
        "---\nname: avisar\ndescription: Mandarle un mensaje a Martin al celular. "
        "Use when Martin dice avisame y mil cosas mas.\n---\ncuerpo", encoding="utf-8")
    (skills.CARPETA_SKILLS / "rota").mkdir()
    (skills.CARPETA_SKILLS / "rota" / "SKILL.md").write_text(
        "---\ndescription: ---\n", encoding="utf-8")
    cat = skills.catalogo()
    chequear("el catalogo trae las dos skills", len(cat) == 2)
    chequear("el nombre sale del frontmatter", cat[0]["nombre"] == "avisar")
    chequear("la descripcion corta el 'Use when'",
             cat[0]["descripcion"] == "Mandarle un mensaje a Martin al celular.")
    chequear("una skill con el frontmatter roto cae al nombre de la carpeta",
             cat[1]["nombre"] == "rota")

    proyecto = tmp / "proyecto"
    (proyecto / ".claude" / "skills" / "deploy").mkdir(parents=True)
    (proyecto / ".claude" / "skills" / "deploy" / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Publicar este proyecto.\n---\n",
        encoding="utf-8")
    (proyecto / ".claude" / "skills" / "avisar").mkdir()
    (proyecto / ".claude" / "skills" / "avisar" / "SKILL.md").write_text(
        "---\nname: avisar\ndescription: repetida\n---\n", encoding="utf-8")
    cat = skills.catalogo(str(proyecto))
    chequear("con cwd se suman las skills del proyecto",
             any(s["nombre"] == "deploy" for s in cat))
    chequear("una skill repetida no aparece dos veces",
             sum(1 for s in cat if s["nombre"] == "avisar") == 1)

    # --- las de los plugins, que cuelgan a cualquier profundidad -----------------
    hondo = skills.CARPETA_PLUGINS / "repos" / "alguien" / "repo" / "unplug" / "skills"
    (hondo / "medir").mkdir(parents=True)
    (hondo / "medir" / "SKILL.md").write_text(
        "---\nname: medir\ndescription: Medir cosas.\n---\n", encoding="utf-8")
    chequear("una skill de un plugin tambien entra al catalogo",
             any(s["nombre"] == "medir" for s in skills.catalogo()))

    # --- las carpetas de skills SIN SKILL.md ------------------------------------
    # El caso de "la cree y no aparece": la carpeta esta, el archivo no.
    chequear("sin carpetas huerfanas no avisa nada", skills.rotas() == [])
    (skills.CARPETA_SKILLS / "tresde").mkdir()
    (skills.CARPETA_SKILLS / "tresde" / "tresde.md").write_text("hola", encoding="utf-8")
    chequear("una carpeta sin SKILL.md sale como rota", skills.rotas() == ["tresde"])
    chequear("y NO se cuela en el catalogo como si anduviera",
             not any(s["nombre"] == "tresde" for s in skills.catalogo()))

    # --- los comandos propios ----------------------------------------------------
    skills.CARPETA_COMANDOS.mkdir()
    (skills.CARPETA_COMANDOS / "limpiar.md").write_text(
        "---\ndescription: Dejar el escritorio prolijo.\n---\ncuerpo", encoding="utf-8")
    (skills.CARPETA_COMANDOS / "pelado.md").write_text(
        "\n# Subir todo al servidor\nlo que sea", encoding="utf-8")
    (skills.CARPETA_COMANDOS / "git").mkdir()
    (skills.CARPETA_COMANDOS / "git" / "subir.md").write_text(
        "Hacer el commit y el push.", encoding="utf-8")
    (proyecto / ".claude" / "commands").mkdir()
    (proyecto / ".claude" / "commands" / "deploy.md").write_text(
        "Publicar.", encoding="utf-8")
    coms = {c["nombre"]: c["descripcion"] for c in skills.comandos(str(proyecto))}
    chequear("un comando propio sale con su descripcion del frontmatter",
             coms.get("limpiar") == "Dejar el escritorio prolijo.")
    chequear("uno sin frontmatter cae al primer renglon con texto",
             coms.get("pelado") == "Subir todo al servidor")
    chequear("uno adentro de una subcarpeta se llama con dos puntos",
             coms.get("git:subir") == "Hacer el commit y el push.")
    chequear("y tambien entran los del proyecto", "deploy" in coms)

    # --- las skills que ve CODEX -------------------------------------------------
    # ⚠⚠ Hasta el 2026-08-28 el panel devolvia `skills: []` en una charla de Codex y
    # el menu decia "Codex no usa las skills de Claude". Era falso desde el 19/08: las
    # skills estan enlazadas UNA POR UNA en `~/.codex/skills`. Estos chequeos existen
    # para que la creencia vieja no pueda volver sin que algo falle.
    skills.CARPETA_SKILLS_CODEX = tmp / "codexskills"
    skills.CARPETA_SKILLS_AGENTS = tmp / "agentsskills"
    (skills.CARPETA_SKILLS_CODEX / "pizarra").mkdir(parents=True)
    (skills.CARPETA_SKILLS_CODEX / "pizarra" / "SKILL.md").write_text(
        "---\nname: pizarra\ndescription: Escribir en el pizarron visual. "
        "Use when dice anota esto.\n---\ncuerpo", encoding="utf-8")
    # La que Codex NO dispara sola: existe y anda, pero hay que nombrarla.
    (skills.CARPETA_SKILLS_CODEX / "grill-me" / "agents").mkdir(parents=True)
    (skills.CARPETA_SKILLS_CODEX / "grill-me" / "SKILL.md").write_text(
        "---\nname: grill-me\ndescription: Entrevista exigente.\n---\ncuerpo",
        encoding="utf-8")
    (skills.CARPETA_SKILLS_CODEX / "grill-me" / "agents" / "openai.yaml").write_text(
        "interface:\n  display_name: \"Grill Me\"\npolicy:\n"
        "  allow_implicit_invocation: false\n", encoding="utf-8")
    # Las que trae Codex de fabrica viven en `.system`: no son de Martin.
    (skills.CARPETA_SKILLS_CODEX / ".system" / "imagegen").mkdir(parents=True)
    (skills.CARPETA_SKILLS_CODEX / ".system" / "imagegen" / "SKILL.md").write_text(
        "---\nname: imagegen\ndescription: Hacer imagenes.\n---\n", encoding="utf-8")
    # La ruta nueva que nombra la doc oficial de Codex.
    (skills.CARPETA_SKILLS_AGENTS / "prompt-master").mkdir(parents=True)
    (skills.CARPETA_SKILLS_AGENTS / "prompt-master" / "SKILL.md").write_text(
        "---\nname: prompt-master\ndescription: Escribir prompts.\n---\n",
        encoding="utf-8")
    cod = {s["nombre"]: s for s in skills.catalogo_codex(str(proyecto))}
    chequear("una charla de Codex SI tiene skills (no la lista vacia de antes)",
             len(cod) > 0)
    chequear("las de ~/.codex/skills entran con su descripcion",
             cod.get("pizarra", {}).get("descripcion") == "Escribir en el pizarron visual.")
    chequear("las de ~/.agents/skills tambien (la ruta nueva)", "prompt-master" in cod)
    chequear("la que Codex no dispara sola queda marcada 'a pedido'",
             cod.get("grill-me", {}).get("a_pedido") is True)
    chequear("y una normal NO queda marcada asi",
             cod.get("pizarra", {}).get("a_pedido") is False)
    chequear("las de fabrica (.system) no ensucian la lista de las tuyas",
             "imagegen" not in cod)
    # El alcance de repositorio: Codex escanea `.agents/skills` del proyecto.
    (proyecto / ".agents" / "skills" / "delrepo").mkdir(parents=True)
    (proyecto / ".agents" / "skills" / "delrepo" / "SKILL.md").write_text(
        "---\nname: delrepo\ndescription: Solo de este repo.\n---\n", encoding="utf-8")
    chequear("y las del propio repo (.agents/skills) tambien",
             "delrepo" in {s["nombre"] for s in skills.catalogo_codex(str(proyecto))})
    # Ninguna de las tres carpetas existe: tiene que devolver vacio, no reventar.
    cod_antes = (skills.CARPETA_SKILLS_CODEX, skills.CARPETA_SKILLS_AGENTS)
    skills.CARPETA_SKILLS_CODEX = tmp / "novive"
    skills.CARPETA_SKILLS_AGENTS = tmp / "tampoco"
    chequear("sin ninguna carpeta no revienta, devuelve vacio",
             skills.catalogo_codex(str(tmp / "novive")) == [])
    skills.CARPETA_SKILLS_CODEX, skills.CARPETA_SKILLS_AGENTS = cod_antes

    # ⚠ Una descripcion entre comillas SIMPLES (YAML lo exige cuando adentro hay dos
    # puntos, como en `notas` y `kanban`) salia al menu con la comilla colgando.
    (skills.CARPETA_SKILLS_CODEX / "notas").mkdir()
    (skills.CARPETA_SKILLS_CODEX / "notas" / "SKILL.md").write_text(
        "---\nname: notas\ndescription: 'Deja al dia el cuaderno: bugs y decisiones.'\n"
        "---\n", encoding="utf-8")
    cod2 = {s["nombre"]: s["descripcion"] for s in skills.catalogo_codex("")}
    chequear("una descripcion entre comillas simples sale sin la comilla",
             cod2.get("notas") == "Deja al dia el cuaderno: bugs y decisiones.")

    # --- las usadas, leidas del .jsonl ------------------------------------------
    seguir_antes = seguir.CLAUDE_PROYECTOS
    seguir.CLAUDE_PROYECTOS = tmp / "projects"
    try:
        cwd = "D:\\IA\\proyecto-uno"
        carpeta = seguir.carpeta_de(cwd)
        carpeta.mkdir(parents=True)
        sid = "abcd1234-5678-90ab-cdef-000000000001"
        f = carpeta / f"{sid}.jsonl"

        f.write_text(l_usuario("hola") + l_skill("graphify")
                     + l_resultado("texto con Skill adentro que no cuenta")
                     + l_usuario("<command-name>/avisar</command-name> dale")
                     + l_slash("/notas hoy"), encoding="utf-8")
        skills._archivos.clear()
        r = skills.usadas(cwd, sid)
        chequear("junta la herramienta Skill, la barrita y SlashCommand",
                 r["usadas"] == ["graphify", "avisar", "notas"])
        chequear("un tool_result que nombra Skill no cuenta",
                 "texto" not in r["usadas"])
        chequear("la ultima es la que quedo corriendo", r["ultima"] == "notas")

        # un mensaje real del usuario apaga la "ultima": ya no corre nada
        with open(f, "a", encoding="utf-8") as h:
            h.write(l_usuario("gracias, listo"))
        r = skills.usadas(cwd, sid)
        chequear("un mensaje nuevo del usuario apaga la ultima", r["ultima"] == "")
        chequear("las usadas quedan", r["usadas"] == ["graphify", "avisar", "notas"])

        # incremental: lo nuevo se suma sin releer, la linea cortada espera
        pos = skills._archivos[str(f)]["pos"]
        with open(f, "a", encoding="utf-8") as h:
            h.write(l_skill("graphify"))                 # repetida: no se duplica
            h.write(l_skill("pizarra").rstrip("\n"))     # a medio escribir
        r = skills.usadas(cwd, sid)
        chequear("solo se leyo lo nuevo", skills._archivos[str(f)]["pos"] > pos)
        chequear("una skill repetida no se duplica",
                 r["usadas"].count("graphify") == 1)
        chequear("la linea cortada no se cuenta todavia", "pizarra" not in r["usadas"])
        with open(f, "a", encoding="utf-8") as h:
            h.write("\n")
        r = skills.usadas(cwd, sid)
        chequear("completada la linea, cuenta y es la ultima",
                 "pizarra" in r["usadas"] and r["ultima"] == "pizarra")

        chequear("sin sid devuelve vacio sin romper",
                 skills.usadas(cwd, "") == {"usadas": [], "ultima": ""})
        chequear("una sesion que no existe devuelve vacio",
                 skills.usadas(cwd, "no-existe-1234") == {"usadas": [], "ultima": ""})

        # --- el uso de TODO el proyecto, no el de una charla ---------------------
        # Pedido del 2026-08-18: una conversacion recien abierta no uso ninguna
        # skill, pero el proyecto si, y el menu salia todo en blanco.
        skills._proyectos.clear()
        v = skills.usadas_proyecto(cwd)
        chequear("cuenta las VECES, no si aparece o no", v["graphify"] == 2)
        chequear("junta las tres formas de invocar",
                 v["avisar"] == 1 and v["notas"] == 1 and v["pizarra"] == 1)

        # una charla SEGUNDA del mismo proyecto suma a la cuenta
        f2 = carpeta / "abcd1234-5678-90ab-cdef-000000000002.jsonl"
        f2.write_text(l_skill("avisar") + l_skill("avisar") + l_skill("leeme"),
                      encoding="utf-8")
        skills._proyectos[str(carpeta)]["ts"] = 0.0
        v = skills.usadas_proyecto(cwd)
        chequear("una charla nueva del proyecto suma a la cuenta", v["avisar"] == 3)
        chequear("y trae una skill que la otra charla no uso", v["leeme"] == 1)

        # una charla nueva y VACIA no usa nada, pero el proyecto sigue marcado:
        # ese es exactamente el caso que motivo el pedido
        f3 = carpeta / "abcd1234-5678-90ab-cdef-000000000003.jsonl"
        f3.write_text(l_usuario("recien abro esta"), encoding="utf-8")
        sid3 = "abcd1234-5678-90ab-cdef-000000000003"
        chequear("la charla nueva no uso ninguna skill",
                 skills.usadas(cwd, sid3)["usadas"] == [])
        skills._proyectos[str(carpeta)]["ts"] = 0.0
        chequear("pero el proyecto la sigue marcando",
                 skills.usadas_proyecto(cwd)["avisar"] == 3)

        # incremental: lo ya leido no se vuelve a contar
        v_antes = dict(skills.usadas_proyecto(cwd))
        skills._proyectos[str(carpeta)]["ts"] = 0.0
        chequear("una segunda pasada no cuenta dos veces lo mismo",
                 skills.usadas_proyecto(cwd) == v_antes)
        with open(f2, "a", encoding="utf-8") as h:
            h.write(l_skill("leeme"))
        skills._proyectos[str(carpeta)]["ts"] = 0.0
        chequear("y lo agregado despues si se suma",
                 skills.usadas_proyecto(cwd)["leeme"] == 2)

        # ⚠ si un archivo ACHICA, lo leido ya no vale: se recuenta la carpeta entera
        # en vez de sumar lo nuevo encima (que contaria de mas)
        f2.write_text(l_skill("leeme"), encoding="utf-8")
        skills._proyectos[str(carpeta)]["ts"] = 0.0
        chequear("si un archivo se achica, se recuenta y no queda inflado",
                 skills.usadas_proyecto(cwd)["leeme"] == 1)
        chequear("y el resto del proyecto se recuenta igual de bien",
                 skills.usadas_proyecto(cwd)["graphify"] == 2)

        chequear("sin cwd devuelve vacio sin romper", skills.usadas_proyecto("") == {})
    finally:
        seguir.CLAUDE_PROYECTOS = seguir_antes

print(f"\n{OK} ok, {MAL} mal")
sys.exit(1 if MAL else 0)
