"""Las skills que puede usar una sesion de Claude Code, y cuales ya uso cada charla.

Pedido de Martin el 2026-08-18: en los chats del panel queria un boton que despliegue
las skills disponibles (como cuando tipea "/" en Claude Code) y que ademas marque
cuales ya se estan ocupando dentro de esa sesion. Este modulo pone los datos; los
botones viven en `app/estaticos/atajos.js`.

Tres preguntas, tres funciones:
- `catalogo(cwd)`: que skills hay para invocar — las globales de `~/.claude/skills`
  mas las del proyecto (`<cwd>/.claude/skills`) mas las que traen los plugins,
  leyendo el frontmatter de cada SKILL.md. No hay API que preguntar: la carpeta ES
  el registro.
- `comandos(cwd)`: los comandos propios de Martin (`~/.claude/commands/*.md` y los del
  proyecto). Van en la misma seccion "Comandos" del menu, atras de los de siempre.
- `rotas(cwd)`: las carpetas de skills a las que les falta el SKILL.md. Existen para
  contestar "cree una skill y no aparece" (Martin, 2026-08-23): si el archivo quedo
  mal puesto, el menu lo dice en vez de esconder la skill en silencio.
- `usadas(cwd, sid)`: cuales invoco ya ESA conversacion, leido de su `.jsonl`. Una
  skill aparece de dos maneras segun quien la pidio: como bloque `tool_use` de la
  herramienta `Skill` (la eligio Claude) o como `<command-name>` en un mensaje del
  usuario (la tipeo Martin con la barrita). Se cuentan las dos.
- `usadas_proyecto(cwd)`: cuantas veces se invoco cada una en TODAS las charlas de
  ese proyecto (pedido del 2026-08-18: "que ya esten marcadas las skills que ya
  estoy ocupando"). Una conversacion nueva no uso ninguna, pero el proyecto si.

La lectura del `.jsonl` es incremental, como en `gasto.py`: de cada archivo se
recuerda hasta donde se leyo y solo se lee lo nuevo. La primera pasada de una charla
gorda (45 MB medidos) paga el archivo entero UNA vez — y esto se pide recien cuando
se abre el boton, no cada 3 segundos.
"""

import json
import re
import time
from pathlib import Path

from app.voz import seguir

# Las carpetas globales. La prueba las reemplaza por unas de mentira.
CARPETA_SKILLS = Path.home() / ".claude" / "skills"
CARPETA_COMANDOS = Path.home() / ".claude" / "commands"
CARPETA_PLUGINS = Path.home() / ".claude" / "plugins"
# Los "prompts" de Codex: su equivalente de un comando con barrita (`/nombre`).
# ⚠ Al 2026-08-28 la carpeta sigue vacia en esta maquina. Eso NO quiere decir que
# Codex no tenga nada: ver `catalogo_codex()` aca abajo.
CARPETA_PROMPTS_CODEX = Path.home() / ".codex" / "prompts"

# ⭐⭐ Codex SI tiene las skills de Martin, desde el 2026-08-19: cada una es un symlink
# de `~/.codex/skills/<nombre>` a la carpeta real de `~/.claude/skills/<nombre>`. Son
# enlaces UNO POR SKILL a proposito — enlazar la carpeta contenedora rompe a Claude
# Code (deja de cargar las skills de usuario), asi que eso no se toca.
#
# ⚠ Esto corrige la decision del 2026-08-23, que se tomo sobre una premisa falsa
# ("Codex no usa las skills de Claude") y dejaba el menu de una charla de Codex
# diciendo que no habia nada. Comprobado el 2026-08-28 con `codex debug prompt-input`
# (lista las 14 con su ruta) y con un `codex exec` real que leyo el cuerpo del
# SKILL.md, no solo la descripcion.
#
# Se invocan con `$nombre`, no con `/nombre`: la barrita es de Claude.
CARPETA_SKILLS_CODEX = Path.home() / ".codex" / "skills"
# La ruta nueva que nombra la doc oficial de Codex (`$HOME/.agents/skills`). Existe en
# esta maquina y ahi vive `prompt-master`. Se miran las dos porque Codex esta migrando.
CARPETA_SKILLS_AGENTS = Path.home() / ".agents" / "skills"

# archivo -> {"pos": hasta donde se leyo, "usadas": [nombres en orden],
#             "ultima": la invocada despues del ultimo mensaje del usuario}
_archivos = {}

_RE_COMANDO = re.compile(r"<command-name>/?([\w:-]+)</command-name>")


def _descripcion(texto):
    """La descripcion del frontmatter, cortada para caber en un menu.

    Las descripciones reales traen atras un "Use when ..." larguisimo que es para
    el modelo, no para un menu: se corta ahi. Y si aun asi es larga, al punto o a
    los 160 caracteres.
    """
    # ⚠ Las comillas SIMPLES tambien: un frontmatter con dos puntos adentro de la
    # descripcion se escribe en YAML entre comillas simples (`notas` y `kanban` lo
    # hacen), y sin sacarlas el menu mostraba `'Alinea el Kanban…` con la comilla
    # colgando adelante.
    d = texto.strip().strip('"\'').strip()
    for marca in (" Use when", " use when", " NOT for", " Not for"):
        i = d.find(marca)
        if i > 0:
            d = d[:i]
    if len(d) > 160:
        corte = d.rfind(". ", 40, 160)
        d = d[:corte + 1] if corte > 0 else d[:157] + "…"
    return d.strip().rstrip(",;")


def _leer_skill(md):
    """El (nombre, descripcion) del frontmatter de un SKILL.md, o None si no se pudo."""
    try:
        crudo = md.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return None
    nombre, desc = md.parent.name, ""
    # El frontmatter es el bloque entre los dos primeros "---". Hay skills con el
    # formato roto (una tiene "---" como descripcion): se cae con gracia al nombre
    # de la carpeta y descripcion vacia, que alcanza para el menu.
    partes = crudo.split("---")
    cuerpo = partes[1] if len(partes) >= 3 else crudo
    for linea in cuerpo.splitlines():
        if linea.startswith("name:"):
            n = linea[5:].strip()
            if n:
                nombre = n
        elif linea.startswith("description:"):
            desc = _descripcion(linea[12:])
    return {"nombre": nombre, "descripcion": desc}


def _raices_skills(cwd):
    """Donde vive una skill tuya: la carpeta global y la del proyecto."""
    raices = [CARPETA_SKILLS]
    if cwd:
        raices.append(Path(cwd) / ".claude" / "skills")
    return raices


def _skills_de_plugins():
    """Los SKILL.md que traen los plugins instalados.

    Un plugin se guarda en `~/.claude/plugins/repos/<duenio>/<repo>/<plugin>/skills/…`,
    pero la profundidad cambia segun de donde venga, asi que se prueban unos cuantos
    niveles en vez de adivinar uno solo. Son carpetas chicas: sale barato.
    """
    if not CARPETA_PLUGINS.is_dir():
        return []
    encontrados = []
    for hondo in range(1, 6):
        patron = "/".join(["*"] * hondo) + "/skills/*/SKILL.md"
        encontrados += sorted(CARPETA_PLUGINS.glob(patron))
    return encontrados


def catalogo(cwd=""):
    """Todas las skills invocables desde esa carpeta: las tuyas + las de los plugins."""
    salida, vistos = [], set()
    archivos = []
    for base in _raices_skills(cwd):
        if base.is_dir():
            archivos += sorted(base.glob("*/SKILL.md"))
    archivos += _skills_de_plugins()
    for md in archivos:
        s = _leer_skill(md)
        if s and s["nombre"] not in vistos:
            vistos.add(s["nombre"])
            salida.append(s)
    return salida


def rotas(cwd=""):
    """Las carpetas de skills SIN un SKILL.md adentro: estan ahi pero no las ve nadie.

    Pedido de Martin (2026-08-23): "creo una skill y no aparece en la lista". Casi
    siempre es esto — el archivo quedo con otro nombre, o una carpeta adentro de otra.
    Antes el menu la salteaba callado y no habia forma de distinguir "esta mal puesta"
    de "nunca se creo".
    """
    salida = []
    for base in _raices_skills(cwd):
        if not base.is_dir():
            continue
        try:
            hijos = sorted(base.iterdir())
        except OSError:
            continue
        for d in hijos:
            try:
                if d.is_dir() and not (d / "SKILL.md").is_file():
                    salida.append(d.name)
            except OSError:
                continue
    return salida


def _leer_comando(md, base):
    """El (nombre, descripcion) de un comando propio.

    El nombre sale de la ruta, como en Claude Code: `commands/limpiar.md` es
    `/limpiar` y `commands/git/subir.md` es `/git:subir`. La descripcion sale del
    frontmatter si lo tiene, y si no del primer renglon con texto — muchos comandos
    son un .md pelado sin encabezado.
    """
    try:
        crudo = md.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return None
    partes = md.relative_to(base).with_suffix("").parts
    if not partes:
        return None
    desc, cuerpo = "", crudo
    if crudo.lstrip().startswith("---"):
        trozos = crudo.split("---")
        if len(trozos) >= 3:
            cuerpo = "---".join(trozos[2:])
            for linea in trozos[1].splitlines():
                if linea.startswith("description:"):
                    desc = _descripcion(linea[12:])
    if not desc:
        for linea in cuerpo.splitlines():
            t = linea.strip().lstrip("#").strip()
            if t:
                desc = _descripcion(t)
                break
    return {"nombre": ":".join(partes), "descripcion": desc}


def comandos(cwd=""):
    """Los comandos propios: `~/.claude/commands` y los del proyecto."""
    salida, vistos = [], set()
    raices = [CARPETA_COMANDOS]
    if cwd:
        raices.append(Path(cwd) / ".claude" / "commands")
    for base in raices:
        if not base.is_dir():
            continue
        for md in sorted(base.rglob("*.md")):
            c = _leer_comando(md, base)
            if c and c["nombre"] not in vistos:
                vistos.add(c["nombre"])
                salida.append(c)
    return salida


def prompts_codex(cwd=""):
    """Los prompts propios de Codex: `~/.codex/prompts` y los del proyecto.

    Es lo mismo que `comandos()` pero del otro cerebro, y se lee igual (un .md por
    prompt, el nombre sale de la ruta). Se separa a proposito en vez de mezclarlos:
    una charla de Codex no puede invocar una skill de Claude ni al reves, y ofrecer
    algo que ahi no anda es peor que no ofrecerlo.
    """
    salida, vistos = [], set()
    raices = [CARPETA_PROMPTS_CODEX]
    if cwd:
        raices.append(Path(cwd) / ".codex" / "prompts")
    for base in raices:
        if not base.is_dir():
            continue
        for md in sorted(base.rglob("*.md")):
            c = _leer_comando(md, base)
            if c and c["nombre"] not in vistos:
                vistos.add(c["nombre"])
                salida.append(c)
    return salida


def _a_pedido(carpeta):
    """¿Esta skill esta puesta para que Codex NO la dispare sola?

    Codex lee `<skill>/agents/openai.yaml`; con `allow_implicit_invocation: false` la
    skill existe y anda, pero solo si la nombras vos. Es el caso de `grill-me`, y sin
    esta marca el menu la ofreceria igual que a las demas y pareceria rota cuando
    Codex no la levanta solo. No se usa una libreria de YAML por una linea: alcanza
    con leerla, y ante la duda se devuelve False (ofrecerla de mas no rompe nada).
    """
    try:
        crudo = (carpeta / "agents" / "openai.yaml").read_text(
            encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return False
    for linea in crudo.splitlines():
        izq, sep, der = linea.partition(":")
        if sep and izq.strip() == "allow_implicit_invocation":
            return der.strip().strip('"\'').lower() in ("false", "no", "off")
    return False


def _raices_skills_codex(cwd):
    """Donde busca Codex una skill de usuario, de la vieja a la nueva.

    La cuarta es el alcance de repositorio: Codex escanea `.agents/skills` desde la
    carpeta de trabajo hasta la raiz del repo.
    """
    raices = [CARPETA_SKILLS_CODEX, CARPETA_SKILLS_AGENTS]
    if cwd:
        raices.append(Path(cwd) / ".agents" / "skills")
    return raices


def catalogo_codex(cwd=""):
    """Las skills que puede invocar una charla de CODEX, con `$nombre`.

    Se saltean las carpetas que empiezan con punto: adentro de `~/.codex/skills` esta
    `.system` con las que trae Codex de fabrica (imagegen, skill-creator...). Mismo
    criterio que del lado de Claude, donde el menu tampoco lista los comandos que ya
    vienen con el CLI: esta lista es la de las skills TUYAS.
    """
    salida, vistos = [], set()
    for base in _raices_skills_codex(cwd):
        if not base.is_dir():
            continue
        for md in sorted(base.glob("*/SKILL.md")):
            if md.parent.name.startswith("."):
                continue
            s = _leer_skill(md)
            if s and s["nombre"] not in vistos:
                vistos.add(s["nombre"])
                s["a_pedido"] = _a_pedido(md.parent)
                salida.append(s)
    return salida


def _texto_usuario(d):
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    return " ".join(b.get("text", "") for b in (c or []) if isinstance(b, dict))


def _skills_de_linea(d):
    """Las skills que esta linea invoca, en orden. Puede haber mas de una."""
    nombres = []
    tipo = d.get("type")
    if tipo == "user":
        # La barrita tipeada por Martin queda como <command-name> en su mensaje.
        nombres += _RE_COMANDO.findall(_texto_usuario(d))
    elif tipo == "assistant":
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            entrada = b.get("input") or {}
            if b.get("name") == "Skill":
                n = (entrada.get("skill") or "").strip()
            elif b.get("name") == "SlashCommand":
                n = (entrada.get("command") or "").strip().lstrip("/").split(" ")[0]
            else:
                continue
            if n:
                nombres.append(n)
    return nombres


def _es_usuario_real(d):
    """¿Esta linea es algo que ESCRIBIO el usuario? (no un tool_result ni un aviso)."""
    if d.get("type") != "user":
        return False
    t = _texto_usuario(d).strip()
    return bool(t) and not t.startswith("<") and "system-reminder" not in t[:120]


def usadas(cwd, sid):
    """Que skills uso ya esa conversacion. Devuelve {"usadas": [...], "ultima": ""}.

    `ultima` es la skill invocada DESPUES del ultimo mensaje real del usuario: si la
    sesion esta pensando ahora, esa es la que esta corriendo. Quien sabe si esta
    pensando es el que llama (el panel); aca solo se lee el archivo.
    """
    vacio = {"usadas": [], "ultima": ""}
    if not cwd or not sid:
        return vacio
    jsonl = seguir.carpeta_de(cwd) / f"{sid}.jsonl"
    try:
        est = jsonl.stat()
    except OSError:
        return vacio
    clave = str(jsonl)
    e = _archivos.get(clave)
    if e is None or est.st_size < e["pos"]:
        e = _archivos[clave] = {"pos": 0, "usadas": [], "ultima": ""}
    if est.st_size > e["pos"]:
        try:
            with open(jsonl, "rb") as f:
                f.seek(e["pos"])
                crudo = f.read()
        except OSError:
            return {"usadas": list(e["usadas"]), "ultima": e["ultima"]}
        # La ultima linea puede estar a medio escribir: se corta en el ultimo salto
        # y lo que falte se lee la proxima vez.
        fin = crudo.rfind(b"\n")
        if fin >= 0:
            e["pos"] += fin + 1
            for linea in crudo[:fin].decode("utf-8", errors="replace").splitlines():
                # Antes de pagar el json.loads (hay lineas de 1 MB): solo interesan
                # las que pueden traer una skill o un turno del usuario, y los
                # tool_result — que tambien son type:user — se saltean de una.
                if '"tool_result"' in linea and "<command-name>" not in linea:
                    continue
                if ('"user"' not in linea and '"Skill"' not in linea
                        and '"SlashCommand"' not in linea):
                    continue
                try:
                    d = json.loads(linea)
                except Exception:
                    continue
                nombres = _skills_de_linea(d)
                for n in nombres:
                    if n not in e["usadas"]:
                        e["usadas"].append(n)
                    e["ultima"] = n
                # Un mensaje real del usuario cierra el turno anterior: lo que
                # corria ya no corre. (Si ese mismo mensaje ES una skill tipeada,
                # `nombres` ya la dejo como ultima.)
                if not nombres and _es_usuario_real(d):
                    e["ultima"] = ""
    if len(_archivos) > 300:
        # Que no crezca para siempre: se tira todo y se relee al proximo pedido.
        actual = _archivos.pop(clave)
        _archivos.clear()
        _archivos[clave] = actual
    return {"usadas": list(e["usadas"]), "ultima": e["ultima"]}


# --- Cuantas veces se uso cada skill en TODO el proyecto --------------------------
# Pedido de Martin (2026-08-18): "me gustaria que ya esten marcadas las skills que ya
# estoy ocupando". Abrir el menu en una conversacion recien nacida mostraba la lista
# entera en blanco, aunque en el proyecto ya se estuvieran usando ocho de las trece:
# `usadas()` mira UNA charla, y una charla nueva no uso nada todavia. Esto mira las
# 133 conversaciones del proyecto.
# carpeta -> {"pos": {archivo: hasta donde se leyo}, "veces": {skill: n}, "ts": cuando}
_proyectos = {}
_PROYECTO_SEG = 30      # el menu se abre a mano: mirar el disco mas seguido no aporta


def usadas_proyecto(cwd):
    """Cuantas veces se invoco cada skill en TODAS las conversaciones del proyecto.

    Incremental como `usadas()`, y aca la diferencia es de otro orden: medido el
    2026-08-18 en wpp-transcriptor son 133 archivos y 305 MB. La primera pasada los
    lee enteros UNA vez (~4 s); despues cada vuelta es un stat por archivo y solo los
    bytes nuevos, y encima queda 30 s cacheado.
    """
    if not cwd:
        return {}
    try:
        carpeta = seguir.carpeta_de(cwd)
        archivos = sorted(carpeta.glob("*.jsonl"))
    except OSError:
        return {}
    clave = str(carpeta)
    e = _proyectos.get(clave)
    if e is None:
        e = _proyectos[clave] = {"pos": {}, "veces": {}, "ts": 0.0}
    elif time.time() - e["ts"] < _PROYECTO_SEG:
        return dict(e["veces"])
    e["ts"] = time.time()

    tamanos = {}
    for j in archivos:
        try:
            tamanos[str(j)] = j.stat().st_size
        except OSError:
            pass
    # ⚠ Si algun archivo ACHICO, lo leido ya no vale y sumar lo nuevo contaria de mas.
    # Es rarisimo (Claude Code solo agrega al final), asi que se recuenta la carpeta
    # entera en vez de llevar la cuenta por archivo: mas simple y no se puede
    # desincronizar.
    if any(t < e["pos"].get(r, 0) for r, t in tamanos.items()):
        e["pos"], e["veces"] = {}, {}

    for ruta, tam in tamanos.items():
        pos = e["pos"].get(ruta, 0)
        if tam <= pos:
            continue
        try:
            with open(ruta, "rb") as f:
                f.seek(pos)
                crudo = f.read()
        except OSError:
            continue
        # La ultima linea puede estar a medio escribir: se corta en el ultimo salto y
        # lo que falte se lee la proxima vez (mismo criterio que `usadas`).
        fin = crudo.rfind(b"\n")
        if fin < 0:
            continue
        e["pos"][ruta] = pos + fin + 1
        for linea in crudo[:fin].decode("utf-8", errors="replace").splitlines():
            if '"tool_result"' in linea and "<command-name>" not in linea:
                continue
            if ('"user"' not in linea and '"Skill"' not in linea
                    and '"SlashCommand"' not in linea):
                continue
            try:
                d = json.loads(linea)
            except Exception:
                continue
            for n in _skills_de_linea(d):
                e["veces"][n] = e["veces"].get(n, 0) + 1

    if len(_proyectos) > 20:
        actual = _proyectos.pop(clave)
        _proyectos.clear()
        _proyectos[clave] = actual
    return dict(e["veces"])
