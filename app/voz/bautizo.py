"""Bautizo: toda charla nueva nace con nombre y subproyecto (pedido de Martín, 2026-11-16).

*"Cuando empiezo una nueva sesión ya debe tener nombre y estar subcategorizada."* Antes
nacía como "(sin nombre)" y suelta, y había que ponerle las dos cosas a mano.

Cómo: apenas el panel conoce el id de la charla nueva, un hilo le pregunta a Haiku un nombre
corto y en qué subproyecto de la carpeta va, mirando el primer mensaje. Es la misma consulta
corta del Ctrl+K de la terminal (`terminales.sugerir`): sin herramientas, sin conectores, sin
CLAUDE.md ni memoria de ningún proyecto, sin guardar la charla. ~8 s y centavos de centavo.

⭐ Lo que ya tiene puesto NO se pisa: si la charla nació con el ＋ de un subproyecto, o la
bautizó la skill chief, o Martín le cambió el nombre mientras Haiku pensaba, eso manda. Por
eso se vuelve a leer justo antes de escribir.
⭐ Si Haiku falla o tarda, el nombre sale del primer mensaje y el subproyecto queda vacío:
nunca se inventa un grupo sin entender el pedido.
"""
import json
import re
import shutil
import subprocess
import tempfile

TOPE_NOMBRE = 40
TOPE_GRUPO = 30

_SISTEMA = ("Ordenas charlas de trabajo en una bandeja. Te pasan el proyecto, los "
            "subproyectos que ya existen y el primer mensaje de una charla nueva. Devolve SOLO "
            "un JSON en una linea: {\"nombre\": \"...\", \"grupo\": \"...\"}. nombre: de 2 a 5 "
            "palabras en castellano, que diga de que se trata (por ejemplo 'Botón de pausa' o "
            "'Deploy de la web'), sin comillas, sin punto final, sin emojis. grupo: uno de los "
            "subproyectos existentes copiado EXACTO si el tema entra ahi; si ninguno encaja, o "
            "si no hay ninguno, inventa uno de una o dos palabras con mayuscula inicial que "
            "sirva para agrupar otras charlas del mismo tema (por ejemplo 'Diseño', 'Deploy', "
            "'Bugs', 'Contenido'); nunca uses el nombre del proyecto como grupo.")


def _limpio(texto, tope):
    t = " ".join(str(texto or "").replace('"', "").split()).strip(" .`'")
    if len(t) > tope:
        t = t[:tope].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    return t[:1].upper() + t[1:]


def nombre_de_respaldo(texto):
    """El nombre cuando Haiku no contesta: el comienzo del primer mensaje, sin la marca de
    imagen ni el saludo de la skill chief."""
    t = re.sub(r"\[Te paso una imagen[^\]]*\]", " ", texto or "")
    objetivo = re.search(r"^\s*OBJETIVO:\s*(.+)$", t, re.M | re.I)
    if objetivo:
        t = objetivo.group(1)
    return _limpio(t, TOPE_NOMBRE)


def proponer(texto, grupos, proyecto=""):
    """(nombre, grupo). Corre en un hilo: el programa tarda unos segundos en arrancar."""
    respaldo = nombre_de_respaldo(texto), ""
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude or not (texto or "").strip():
        return respaldo
    entrada = (f"Proyecto: {proyecto or '(sin nombre)'}\n"
               f"Subproyectos que ya existen: {', '.join(grupos) if grupos else '(ninguno)'}\n\n"
               f"Primer mensaje:\n{(texto or '')[:3000]}")
    # ⚠ Una carpeta vacía, como en `terminales.sugerir`: en la del proyecto leería su
    # CLAUDE.md y su memoria, miles de letras que no hacen falta para ponerle un nombre.
    with tempfile.TemporaryDirectory(prefix="bautizo_") as vacia:
        try:
            r = subprocess.run(
                [claude, "-p", "--model", "haiku", "--tools", "", "--no-session-persistence",
                 "--strict-mcp-config", "--setting-sources", "", "--output-format", "json",
                 "--system-prompt", _SISTEMA],
                input=entrada, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=90, cwd=vacia,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            d = json.loads(r.stdout or "{}")
        except Exception:
            return respaldo
    if d.get("is_error"):
        return respaldo
    return interpretar(str(d.get("result") or ""), grupos, respaldo)


def interpretar(salida, grupos, respaldo=("", "")):
    """De lo que contestó Haiku a (nombre, grupo). Un grupo que coincide con uno existente
    salvo mayúsculas se escribe como el existente: dos grupos "web" y "Web" serían dos."""
    m = re.search(r"\{.*\}", salida or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    nombre = _limpio(d.get("nombre"), TOPE_NOMBRE) or respaldo[0]
    grupo = " ".join(str(d.get("grupo") or "").replace('"', "").split()).strip(" .")
    for g in grupos:
        if g.lower() == grupo.lower():
            grupo = g
            break
    else:
        grupo = _limpio(grupo, TOPE_GRUPO)
    return nombre, grupo
