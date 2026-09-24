"""
Puente al Claude Code CLI (headless) para el asistente de voz.

Decis "Claude, ..." y la consulta va al Claude Code que ya tenes instalado y
logueado (usa tu suscripcion: sin API key ni costo extra).

DOS MODOS (constante MODO, o CLAUDE_VOZ_MODO en el .env):

  "lectura"  -> LEE archivos, busca en el codigo y en internet. NO escribe ni ejecuta.
  "completo" -> ADEMAS escribe/edita archivos y corre comandos (PowerShell, git, etc).

RIESGO del modo completo: la entrada viene de TRANSCRIPCION DE VOZ, que falla seguido
("leeme" salio "Dejeme"). Una frase mal entendida puede borrar o modificar archivos.
Por eso el modo completo esta ACOTADO A CARPETAS (ver CARPETAS): fuera de ahi no toca
archivos. Los comandos de shell SI pueden salirse de esas carpetas: es el precio de
tener PowerShell. Para volver atras: MODO = "lectura".
"""

import os
import re
import sys
import json
import time
import queue
import shutil
import threading
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta

from app.rutas import RAIZ, CLAUDE_SESION, CLAUDE_SESIONES, AJUSTES_SESIONES
from app.voz import cupo
from app.voz.prompt_master_auto import anexar_claude

CWD = str(RAIZ)                           # carpeta donde trabaja (proyecto del asistente)
MODELO = "opus"                           # calidad/velocidad equilibradas para voz
TIMEOUT = 600     # tareas largas (escanear disco, refactors): 3 min quedaba corto
# ...pero un cuelgue no puede costar esos 10 minutos. Una tarea larga sigue mandando
# eventos por el stream; si no llega NADA en este tiempo, no esta pensando, esta muerta.
SIN_SENAL_SEG = 120

# La sesion se guarda en disco: asi Laura NO pierde la conversacion cuando se
# reinicia voz.py (pasa seguido). La rotacion es por DIA.
_SESION_FILE = CLAUDE_SESION

# --- El "dia de Laura" ----------------------------------------------------------
# No arranca a la medianoche: arranca a la 1 de la tarde. El usuario trabaja de
# noche, y con el corte a las 12 la sesion se le partia en dos en plena charla.
# Todo lo que pase antes de las 13:00 cuenta como parte del dia anterior.
# VA ACA ARRIBA a proposito: el system prompt de abajo lo interpola, y definirlo
# despues rompia el import entero con NameError.
CORTE_HORA = 13
# Y aun con el corte bien puesto, si venias hablando hace un rato NO te interrumpe
# con la pregunta del dia: espera a que haya un hueco de verdad.
GRACIA_CORTE = 30 * 60

# "completo" o "lectura". El .env manda si define CLAUDE_VOZ_MODO.
MODO = os.environ.get("CLAUDE_VOZ_MODO", "completo").strip().lower()

# Memoria permanente (la misma que usa Claude Code): ahi guarda lo que le pidas recordar
# entre charlas. Si no puede escribir aca, "acordate de esto" no funciona de verdad.
# Claude Code guarda la memoria de cada carpeta en ~/.claude/projects/<carpeta con los
# separadores cambiados por guiones>/memory. Laura trabaja parada en tu carpeta de usuario.
MEMORIA_DIR = str(Path.home() / ".claude" / "projects"
                  / re.sub(r"[^A-Za-z0-9]", "-", str(Path.home())) / "memory")

# Carpetas donde PUEDE tocar archivos en modo completo (ademas de CWD). De fabrica, la
# carpeta que contiene a este proyecto. Agregá acá tus proyectos; lo que no este listado
# queda fuera de su alcance.
CARPETAS = [str(RAIZ.parent), MEMORIA_DIR]

# Modo lectura: buscar/leer archivos y web. Nada que escriba o ejecute.
TOOLS_LECTURA = ["Read", "Grep", "Glob", "WebSearch", "WebFetch", "TodoWrite"]
TOOLS_NO_LECTURA = ["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "BashOutput",
                    "KillShell", "Task", "Agent", "SlashCommand"]

# Modo completo: todo, incluido Bash (PowerShell) y edicion de archivos.
# SIN "Task": los sub-agentes devolvian un session_id que NO era el de la charla, y al
# reanudarlo Laura arrancaba en blanco ("no hay nada previo en esta conversacion").
# CON "Skill" (2026-08-11): sin el, Laura no puede cargar los skills del usuario
# (n8n-server, graphify...) y para operar el n8n del VPS por Telegram los necesita.
TOOLS_COMPLETO = TOOLS_LECTURA + ["Write", "Edit", "MultiEdit", "NotebookEdit",
                                  "Bash", "BashOutput", "KillShell", "SlashCommand",
                                  "Skill"]

_SYSTEM_BASE = (
    "Sos el cerebro de un asistente de voz en espanol rioplatense (Argentina). "
    # Sin esto adivina mal: en la memoria del proyecto hay un pipeline VIEJO de WhatsApp
    # y creia que el usuario le hablaba por ahi.
    "COMO TE HABLA: el usuario te habla EN VIVO por microfono, sentado frente a su PC "
    "con Windows. Dice 'Laura' y habla; un proceso local (voz.py) lo escucha, lo transcribe "
    "con Whisper en la GPU de la maquina y te manda ese texto; tu respuesta se lee en voz "
    "alta con Piper. NO es WhatsApp, NO pasa por ningun VPS ni por n8n: eso es otro proyecto "
    "distinto del mismo usuario que aparece en la memoria, no confundas. "
    # Sin esto negaba tener memoria entre sesiones... estando dentro de una sesion retomada.
    "TU MEMORIA: la charla se guarda y se retoma sola, incluso si se reinicia el asistente. "
    "Si ves turnos anteriores es porque siguen siendo la misma conversacion: NO digas que "
    "'cada sesion empieza de cero' ni que no tenes memoria. "
    # El dia de Laura arranca a las 13:00, no a la medianoche (CORTE_HORA). El usuario
    # elige cada dia si sigue o empieza limpio, asi que ella tiene que saber que existe.
    f"Cada dia (el dia arranca a las {CORTE_HORA}:00) el usuario elige si continua esta "
    "misma charla o arranca una nueva; las anteriores quedan archivadas y se pueden "
    "retomar o resumir, asi que si te pide un resumen de otro dia es normal que puedas "
    "darselo. Lo que no sobrevive a nada de esto es lo que no hayas escrito en un "
    "archivo de memoria o en el README del proyecto. "
    "Tu respuesta SE LEE EN VOZ ALTA: contesta en 1 a 3 frases cortas, sin markdown, "
    "sin listas, sin bloques de codigo, sin emojis y sin rutas largas de archivos. "
    "NUNCA incluyas links, URLs ni una seccion de fuentes: no se pueden leer en voz. "
    "Si la respuesta es larga, resumi lo esencial y ofrece dar mas detalle. "
    # Hablando se usa muchisimo el 'esto/eso'. Preguntar '¿que cosa?' cuando la respuesta
    # esta en el turno anterior hace que parezca que no te sigue el hilo.
    "HABLADO, NO ESCRITO: el usuario dice todo el tiempo 'esto', 'eso', 'lo que dijiste', "
    "'lo de recien'. Casi siempre se refiere a LO ULTIMO que hablaron, muchas veces a tu "
    "propia respuesta anterior. Resolvelo solo con el contexto de la charla en vez de "
    "preguntar '¿que cosa?'. Si por ejemplo te acabas de explicar algo y te dicen 'guarda "
    "esto', se refieren a esa explicacion. Solo preguntá si de verdad no hay nada reciente "
    "a lo que pueda referirse. "
    "Ademas el texto viene de un dictado: si una palabra suena rara, interpretá por el "
    "contexto lo mas probable en vez de trabarte con la transcripcion literal. "
)

_SYSTEM_LECTURA = (
    "Estas en modo solo lectura: podes leer archivos y buscar en internet, pero no "
    "modificar nada; si te piden cambiar algo, decilo en una frase. "
    "Tampoco podes guardar nada en disco: si te piden recordar algo, aclara que lo vas a "
    "tener presente solo mientras dure esta conversacion. NUNCA digas que guardaste algo."
)

_SYSTEM_COMPLETO = (
    "Tenes acceso completo a la computadora: podes crear y editar archivos y correr "
    "comandos de shell (PowerShell). "
    "PERO lo que recibis viene de un DICTADO POR VOZ que a veces se transcribe mal, asi "
    "que segui SIEMPRE esta regla:\n"
    "1) LEER, buscar, listar, mirar archivos, buscar en internet, o correr comandos que "
    "solo consultan (git status, ls, get-date): hacelo directo, sin preguntar.\n"
    "2) TOCAR ALGO (crear, editar, renombrar, mover o borrar un archivo; instalar o "
    "desinstalar; git commit/push/reset; cambiar configuracion del sistema): NO lo hagas "
    "todavia. Primero deci en UNA frase corta y concreta que archivo vas a tocar y que le "
    "vas a hacer, y termina preguntando '¿lo hago?'. Recien cuando en el turno siguiente "
    "te confirmen (si, dale, hacelo, confirmo), ejecutalo y conta en una frase que hiciste. "
    "Si te dicen que no, o cambian de tema, NO lo hagas.\n"
    "3) Si el pedido suena raro, cortado o no se entiende, pregunta en vez de adivinar: "
    "puede ser un error de transcripcion.\n"
    # Laura tambien pone musica (pedido 2026-08-11): el Spotify del proyecto es un CLI
    # y ella tiene shell. Excepcion explicita a la regla de confirmar: poner una
    # cancion es inocuo y pedir permiso para eso mata la gracia.
    "MUSICA: si te piden poner una cancion, un artista o una playlist, corre DIRECTO "
    "(sin pedir confirmacion, es inocuo): "
    '"' + sys.executable + '" -m app.voz.spotify "lo que pidieron" '
    "— busca en Spotify y lo reproduce (entiende canciones, 'algo de tal artista', "
    "'la radio de X' y playlists; si Spotify esta cerrado lo abre solo). El comando "
    "imprime que puso: tu respuesta es UNA frase con eso (ej: 'Puse tal cancion'). "
    "Si falla, deci el error en una frase, sin tecnicismos.\n"
    "Nunca pidas confirmacion dos veces para lo mismo, y nunca ejecutes 'por las dudas'.\n"
    "MEMORIA ENTRE CHARLAS: si te piden recordar algo para siempre (no solo para esta "
    f"conversacion), guardalo de verdad como archivo en {MEMORIA_DIR} siguiendo el formato "
    "de los que ya estan ahi, y sumá la linea correspondiente en su MEMORY.md. "
    "Eso cuenta como tocar un archivo: avisá que lo vas a guardar y esperá el visto bueno. "
    "NO CONFUNDAS lo hablado con lo guardado: que un dato aparezca en esta conversacion NO "
    "significa que este en un archivo. Antes de decir 'ya esta guardado' tenes que ABRIR el "
    "archivo y verlo con tus propios ojos; si no lo verificaste, no lo afirmes. "
    "Y NUNCA digas que guardaste algo si no escribiste el archivo: si no lo hiciste, deci "
    "que lo vas a recordar solo mientras dure esta charla."
)

SYSTEM = _SYSTEM_BASE + (_SYSTEM_COMPLETO if MODO == "completo" else _SYSTEM_LECTURA)

# CRITICO: sin saltos de linea. El binario `claude` en Windows es un .CMD, y un argumento
# con \n le rompe el parseo: se pierde el --resume que va despues y CADA TURNO ABRE UNA
# SESION NUEVA (Laura decia "no hay nada previo en esta conversacion"). Costo encontrarlo.
SYSTEM = re.sub(r"\s+", " ", SYSTEM).strip()

_SESION = None            # id de sesion -> Claude recuerda los turnos anteriores
_DIA = None               # "dia de Laura" al que pertenece la sesion actual
_HISTORIAL = []           # sesiones de dias anteriores, la mas nueva primero
_ultimo_turno = 0.0       # cuando le hablaste por ultima vez (para no cortarte al medio)

SALUDO_DIA = ("Hola, hoy es nuestra primera sesion del dia. "
              "Queres continuar con la sesion anterior o empezamos un proyecto nuevo?")

# OJO con el orden: "no, continuemos" tiene un "no" adentro. Si mirara el si/no
# primero elegiria sesion nueva justo cuando pediste lo contrario. Por eso las
# palabras que dicen QUE hacer se miran ANTES que el si/no suelto.
# El verbo explicito de continuar se mira PRIMERO que todo: "continua donde quedamos"
# tiene un "quedamos" que tambien matchea el pedido de resumen, y sin esta prioridad
# te resumia en vez de seguir. "Donde quedamos?" pelado si es un pedido de resumen:
# preguntas para decidir, no estas decidiendo.
_SIGUE_VERBO = re.compile(r"\b(continu\w*|segu\w*|retom\w*|dale con|vamos con|"
                          r"volv[ae]\w* a la)\b")
_SIGUE_FUERTE = re.compile(r"\b(la anterior|lo anterior|de ayer|lo de ayer|la de ayer|"
                           r"donde (quedamos|estabamos)|la misma|lo mismo)\b")
_NUEVA_FUERTE = re.compile(r"\b(nuev\w*|otro proyecto|de cero|desde cero|limpi\w*|"
                           r"empec\w*|empez\w*|arranc\w*|borron)\b")
_SI_SUELTO = re.compile(r"^\W*(si|dale|obvio|claro|ok|okey|bueno)\b")
_NO_SUELTO = re.compile(r"^\W*no\b")

# Pedidos de resumen de lo que hablamos antes. Sin tildes: se compara en plano.
#
# OJO con "(de que|que) hablamos": la forma bare "que hablamos" tambien aparece en
# frases que NO son un pedido, como la relativa "lo que hablamos" ("lo que hablamos
# por voz lo sabes") — es una construccion comun del espanol, no una pregunta. El
# 2026-08-11 un mensaje de contexto de ~1900 caracteres por Telegram tenia esa frase
# de pasada, el detector lo tomo como "de que hablamos?" y el mensaje real (nunca
# llego a Laura) se piso con el resumen de OTRA sesion. Por eso esta alternativa
# exige el "de" — "de que hablamos" SI es casi siempre una pregunta real.
_RESUMEN = re.compile(
    r"resum\w*.{0,30}(sesion|charla|conversacion|ayer|lo que hablamos|lo que veniamos)"
    r"|de que (hablamos|charlamos|hablabamos|veniamos hablando|dijimos)"
    r"|no (me acuerdo|recuerdo).{0,35}(hablamos|charlamos|ayer|sesion|quedamos|dijimos)"
    r"|(donde|en que) quedamos"
    r"|(contame|recordame|refrescame|repasame).{0,30}(ayer|la sesion|la charla|lo que hablamos)"
)
# Segunda barrera, ademas del regex mas estricto: un pedido de resumen SUELTO (fuera
# del saludo del dia) es siempre corto. Un mensaje largo (un parrafo pegado, un .md)
# puede coincidir con el patron sin ser un pedido — y ahi el costo de un falso
# positivo es maximo: se DESCARTA el mensaje entero. Ver preguntar().
RESUMEN_LARGO_MAX = 220

# Arrancar sesion nueva A MANO, en cualquier momento del dia (lo usa voz.py; es un
# camino aparte del saludo de las 13:00, que sigue entendiendote por contexto).
# UNA sola frase a proposito, pedido de Martin el 2026-08-14. Antes alcanzaba con
# "olvida" suelto y sin limite de palabra: "olvidate de eso" o "olvida lo que te dije
# recien" -- frases normales en medio de una charla -- te borraban la sesion entera
# sin avisar. Ahora se piden las DOS piezas juntas (un verbo de arrancar + "sesion
# nueva"), con hasta 20 letras en el medio para aguantar el dictado: "arranca UNA
# sesion nueva". "seccion" esta porque Whisper escribe eso cuando decis "sesion".
# Ojo con las raices: "arranquemos" NO empieza con "arranc" sino con "arranqu"
# (y pasa lo mismo con empecemos/empezamos y comencemos/comenzamos), asi que van
# con clase de caracteres. La prueba lo agarro al primer intento.
_NUEVA_SESION = re.compile(
    r"\b(arran[cq]\w*|empe[cz]\w*|comen[cz]\w*|inici\w*)\b.{0,20}"
    r"\b((sesion|seccion) nueva|nueva (sesion|seccion))\b")

PROMPT_RESUMEN = (
    "Abajo esta la conversacion de una sesion anterior nuestra (dia {dia}). "
    "Resumila en 3 o 4 frases cortas para leer EN VOZ ALTA: que hicimos y que quedo "
    "pendiente. Sin markdown, sin listas, sin rutas de archivo largas. "
    # Esto no es un detalle de estilo. El primer resumen arranco con "el dia 9 no me
    # pediste nada de codigo" y el usuario entendio que Laura NO SE ACORDABA de nada:
    # leido en voz alta, la primera frase es lo unico que queda. Nunca abrir negando.
    "ARRANCA por lo que SI pasó, lo mas importante primero. NUNCA empieces por lo que "
    "no pasó, ni por lo que no hicimos, ni aclarando que algo no se hablo: se lee en "
    "voz alta y la primera frase es la unica que le queda. "
    "Si de verdad no hay nada sustancioso, decilo en una sola frase y listo.\n\n"
    "--- CHARLA DEL {dia} ---\n{charla}")


def _plano(t):
    """Minusculas y sin acentos, para comparar contra los patrones de arriba."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def pide_sesion_nueva(texto):
    """True si estas pidiendo explicitamente arrancar de cero (ver _NUEVA_SESION).

    Es la UNICA frase que corta la sesion a mano fuera del saludo del dia. Lo llama
    voz.py; aca vive porque el que sabe que es una "sesion" es este modulo, y asi la
    prueba puede tocarlo sin cargar Whisper ni el microfono.
    """
    return bool(_NUEVA_SESION.search(_plano(texto)))


def _dia_de(ts=None):
    """A que 'dia de Laura' pertenece un momento. Antes de las 13:00 es el dia de ayer."""
    t = datetime.fromtimestamp(ts if ts else time.time())
    if t.hour < CORTE_HORA:
        t -= timedelta(days=1)
    return t.strftime("%Y-%m-%d")


def _cargar_sesion():
    """Lee la sesion actual y el historial. Entiende el formato viejo (un solo id)."""
    global _SESION, _DIA, _HISTORIAL, _ultimo_turno
    try:
        d = json.loads(_SESION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if "actual" not in d and d.get("session_id"):        # formato viejo -> migrar
        d = {"actual": {"session_id": d["session_id"], "ts": float(d.get("ts", 0)),
                        "dia": _dia_de(float(d.get("ts", 0)))}, "historial": []}
    act = d.get("actual") or {}
    _HISTORIAL = d.get("historial") or []
    _SESION = act.get("session_id")
    _DIA = act.get("dia")
    _ultimo_turno = float(act.get("ts") or 0)
    if _SESION:
        print(f"claude: sesion guardada {_SESION[:8]} del dia {_DIA} "
              f"({len(_HISTORIAL)} dias anteriores)", flush=True)


def _guardar_sesion(sid=None):
    global _SESION, _DIA, _ultimo_turno
    if sid:
        _SESION = sid
    if not _DIA:
        _DIA = _dia_de()
    _ultimo_turno = time.time()
    try:
        _SESION_FILE.write_text(json.dumps(
            {"actual": {"session_id": _SESION, "dia": _DIA, "ts": _ultimo_turno},
             "historial": _HISTORIAL[:60]}, indent=2), encoding="utf-8")
    except Exception as e:
        print("no pude guardar la sesion:", e, flush=True)


def sesion_anterior():
    """La sesion mas reciente de un dia distinto al de hoy. None si no hay.

    Mira PRIMERO la sesion actual: si todavia no la archivamos pero es de otro dia,
    esa es "la de ayer". Sin esto, el primer pedido de resumen del dia contestaba
    "no tengo una sesion anterior" teniendola justo ahi.
    """
    hoy = _dia_de()
    if _SESION and _DIA and _DIA != hoy:
        return {"session_id": _SESION, "dia": _DIA, "ts": _ultimo_turno}
    for s in _HISTORIAL:
        if s.get("dia") != hoy and s.get("session_id"):
            return s
    return None


def _charla_de(session_id, max_chars=30000):
    """Saca la conversacion de una sesion vieja de su .jsonl, en texto pelado.

    Asi Laura puede resumir un dia anterior SIN reabrir esa sesion: le pasamos la
    charla como texto a la sesion de hoy. Sale mas barato y no hay que malabarear
    dos procesos. Sus sesiones son chicas (contesta en dos frases), asi que entra.
    """
    p = CLAUDE_SESIONES / f"{session_id}.jsonl"
    if not p.exists():
        return ""
    partes = []
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            for linea in f:
                try:
                    d = json.loads(linea)
                except Exception:
                    continue
                if d.get("type") not in ("user", "assistant"):
                    continue
                msg = d.get("message") or {}
                c = msg.get("content")
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    txt = " ".join(b.get("text", "") for b in c
                                   if isinstance(b, dict) and b.get("type") == "text")
                else:
                    continue
                txt = txt.strip()
                if txt:
                    partes.append(("Yo: " if d["type"] == "user" else "Vos: ") + txt)
    except Exception as e:
        print("no pude leer la charla vieja:", e, flush=True)
        return ""
    charla = "\n".join(partes)
    return charla[-max_chars:] if len(charla) > max_chars else charla


def _archivar_actual():
    """Guarda la sesion de hoy en el historial y deja el lugar limpio para una nueva."""
    global _SESION, _DIA
    if _SESION:
        _HISTORIAL.insert(0, {"session_id": _SESION, "dia": _DIA or _dia_de(),
                              "ts": _ultimo_turno})
    _SESION = None
    _DIA = _dia_de()
    global _turnos
    _turnos = 0                # charla nueva: el contador y los avisos arrancan de cero
    _avisado.clear()
    _apagar()                  # el proceso vivo tiene la sesion vieja: que arranque limpio


_CANCELADO = False        # la ultima consulta la cortamos nosotros (no es un error real)
_en_vuelo = False         # hay una consulta esperando respuesta AHORA (Claude pensando)
_esperando_dia = False    # dijo el saludo del dia y espera que elijas
_pendiente = None         # lo que preguntaste ANTES del saludo: no se pierde
_turnos = 0               # idas y vueltas de esta sesion (el numero lo da el propio CLI)
_avisado = set()          # avisos ya dados: se dicen UNA vez, no en cada respuesta

_cargar_sesion()          # retomamos la charla de antes del reinicio de voz.py


def _claude_bin():
    return shutil.which("claude") or shutil.which("claude.cmd") or "claude"


# --- Proceso PERSISTENTE -------------------------------------------------------
# Arrancar `claude` cuesta ~8s; el modelo casi nada. Por eso dejamos UN proceso vivo
# y le mandamos cada consulta por stdin (stream-json). Medido: 10s el arranque, y
# despues ~3.5s por turno (antes 8-12s SIEMPRE).
_lock_turno = threading.RLock()  # un turno por vez: el protocolo es una pregunta -> un result
                                  # RLock (no Lock) porque compactar() lo sostiene de punta a
                                  # punta y adentro llama a preguntar(), que lo vuelve a pedir
                                  # en el mismo hilo — con un Lock comun eso era un deadlock.
_lock_proc = threading.Lock()    # precalentar() y preguntar() pueden arrancarlo a la vez
_vivo = None                     # Popen del proceso persistente
_cola = queue.Queue()            # lineas que va escupiendo


# --- Con que modelo corre Laura -------------------------------------------------
# ⭐ Elegible desde el panel (pedido de Martin, 2026-08-18). Vive en el mismo archivo
# que el de las sesiones, bajo la llave "laura". Se lee del disco y no de una variable
# porque quien lo cambia es el PANEL, que es otro proceso: la variable de aca no se
# entera nunca. Ver `app/voz/sesiones_movil.py` para la lista de modelos.
_modelo_vivo = None       # con cual arranco el proceso que esta dando vueltas ahora
_esfuerzo_vivo = None     # y con cuanto esfuerzo (--effort); vacio = el de fabrica


def modelo_actual():
    """El modelo elegido para Laura. El de fabrica si no se toco nada."""
    from app.voz.sesiones_movil import MODELOS
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        m = (d.get("laura") or {}).get("modelo")
        if m in MODELOS:
            return m
    except Exception:
        pass
    return MODELO


def esfuerzo_actual():
    """Cuanto se esfuerza Laura en pensar. Vacio = el de fabrica del CLI.

    Misma perilla que la del modelo y guardada al lado (llave "laura" del mismo
    archivo), porque quien la mueve es el panel, que es otro proceso.
    """
    from app.voz.sesiones_movil import ESFUERZOS, ESFUERZO_DEFECTO
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        e = (d.get("laura") or {}).get("esfuerzo")
        if e in ESFUERZOS:
            return e
    except Exception:
        pass
    return ESFUERZO_DEFECTO


def _revisar_modelo():
    """Si le cambiaste el modelo o el esfuerzo desde el panel, el proceso vivo tiene el viejo.

    Se apaga y listo: el proximo turno lo levanta con el nuevo y con `--resume`, asi
    que la charla sigue igual. Cuesta los ~10 s de arranque, una sola vez.
    """
    global _modelo_vivo, _esfuerzo_vivo
    m = modelo_actual()
    e = esfuerzo_actual()
    if _vivo is not None and _modelo_vivo is not None and m != _modelo_vivo:
        print(f"claude: cambio el modelo ({_modelo_vivo} -> {m}), rearranco la sesion",
              flush=True)
        _apagar()
    elif _vivo is not None and _esfuerzo_vivo is not None and e != _esfuerzo_vivo:
        print(f"claude: cambio el esfuerzo ({_esfuerzo_vivo or 'fabrica'} -> "
              f"{e or 'fabrica'}), rearranco la sesion", flush=True)
        _apagar()
    _modelo_vivo = m
    _esfuerzo_vivo = e


def _args_comunes():
    from app.voz.sesiones_movil import AUTOCOMPACT
    global _modelo_vivo, _esfuerzo_vivo
    _modelo_vivo = modelo_actual()
    _esfuerzo_vivo = esfuerzo_actual()
    args = ["--model", _modelo_vivo, "--append-system-prompt", anexar_claude(SYSTEM),
            "--permission-mode", "dontAsk"]
    # Cuanto piensa antes de contestar. Solo va si lo elegiste desde el panel.
    if _esfuerzo_vivo:
        args += ["--effort", _esfuerzo_vivo]
    # Con la ventana de un millon la charla no se compacta nunca sola y cada turno
    # termina releyendo todo. Ver AUTOCOMPACT en sesiones_movil.
    if _modelo_vivo in AUTOCOMPACT:
        args += ["--autocompact", AUTOCOMPACT[_modelo_vivo]]
    if MODO == "completo":
        args += ["--allowedTools", *TOOLS_COMPLETO]
        for d in CARPETAS:
            if os.path.isdir(d):
                args += ["--add-dir", d]
    else:
        args += ["--allowedTools", *TOOLS_LECTURA,
                 "--disallowedTools", *TOOLS_NO_LECTURA]
    return args


def _lector(proc):
    # Cada linea viaja CON su proceso: si un proceso viejo escupe algo tarde (un
    # result que llego despues del timeout), el turno en curso puede reconocerlo
    # como ajeno y tirarlo. Sin la etiqueta, esa respuesta tardia se tomaba como
    # la respuesta de la pregunta SIGUIENTE y el chat quedaba corrido en uno para
    # siempre (visto en el chat del panel, 2026-08-18).
    try:
        for linea in proc.stdout:
            _cola.put((proc, linea))
    except Exception:
        pass
    _cola.put((proc, None))       # el proceso murio


def _arrancar():
    """Levanta el proceso persistente (retomando la charla si hay sesion guardada)."""
    global _vivo
    with _lock_proc:                  # sin esto, precalentar() y la 1er consulta podian
        return _arrancar_ya()         # arrancar DOS procesos y mezclar sus salidas


def _arrancar_ya():
    global _vivo
    if _vivo is not None and _vivo.poll() is None:
        return True                   # otro hilo ya lo levanto mientras esperabamos
    _apagar()
    cmd = [_claude_bin(), "-p",
           "--input-format", "stream-json",
           "--output-format", "stream-json",
           "--verbose"] + _args_comunes()
    if _SESION:
        cmd += ["--resume", _SESION]
    env = dict(os.environ)
    env.pop("SSLKEYLOGFILE", None)
    try:
        # ⚠ CREATE_NO_WINDOW: `claude` en Windows es un .cmd, o sea que lo que arranca es un
        # cmd.exe, y el servicio de voz lo lanza el panel SIN consola. Sin esta marca Windows
        # le regala al hijo una consola nueva y VISIBLE, que queda plantada en la pantalla
        # todo lo que viva el proceso persistente (2026-09-06). Las sesiones del panel ya lo
        # tenian desde el 2026-08-17 (ver `sesiones_movil.py`); este cerebro quedo afuera.
        # La salida se sigue capturando por los pipes: no se pierde nada.
        _vivo = subprocess.Popen(cmd, cwd=CWD, env=env, shell=False,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print("claude: no pude arrancar el proceso persistente:", e, flush=True)
        _vivo = None
        return False
    while not _cola.empty():      # descartar restos del proceso anterior
        try:
            _cola.get_nowait()
        except queue.Empty:
            break
    threading.Thread(target=_lector, args=(_vivo,), daemon=True).start()
    print("claude: proceso listo (las respuestas ahora son rapidas)", flush=True)
    return True


def _apagar():
    global _vivo
    p = _vivo
    _vivo = None
    if p is not None and p.poll() is None:
        try:
            p.kill()
        except Exception:
            pass


def precalentar():
    """Arranca el proceso al inicio para que la PRIMERA consulta ya sea rapida."""
    # El vigilante del cupo NO se arranca aca: lo arranca voz.py al final de su carga,
    # porque necesita la funcion que espera un hueco para hablarte y esa vive alla.
    threading.Thread(target=_arrancar, daemon=True).start()


def cancelar():
    """El usuario interrumpio: ABORTA la generacion en curso, sin matar el proceso.

    Desde CLI 2.1.205+ (esta maquina: 2.1.226) existe la interrupcion real: un
    control_request por stdin corta el turno al instante (probado: el result llega
    en el acto con error_during_execution y len=0), el proceso queda vivo y la
    proxima pregunta sale rapida. NUNCA matar el proceso: eso dejaba la consulta
    pendiente en la sesion y Claude la contestaba despues, pisando lo nuevo."""
    global _CANCELADO
    if _en_vuelo and _vivo is not None and _vivo.poll() is None:
        _CANCELADO = True
        try:
            _vivo.stdin.write(json.dumps({"type": "control_request",
                                          "request_id": f"stop-{int(time.time())}",
                                          "request": {"subtype": "interrupt"}}) + "\n")
            _vivo.stdin.flush()
            print("claude: interrupt enviado (corto la generacion)", flush=True)
        except Exception as e:
            print("claude: no pude mandar el interrupt:", e, flush=True)


def olvidar():
    """Arranca una conversacion nueva con Claude, PERO no tira el historial.

    Antes borraba el archivo entero. Ahora la sesion que dejas se archiva: "empecemos
    de nuevo" no puede hacerte perder para siempre la charla a la que despues quizas
    quieras volver.
    """
    global _esperando_dia, _pendiente
    _esperando_dia = False
    _pendiente = None
    _archivar_actual()
    _guardar_sesion()


def compactar():
    """Resume la charla de ahora y sigue en una sesion NUEVA con ese resumen.

    Pedido de Martin el 2026-08-18, el mismo dia que aparecio de donde salia el
    drenaje de tokens: una charla larga vuelve a leerse entera en CADA turno, y
    hasta ahora la unica salida era "empecemos de nuevo" y perder el hilo.

    La sesion vieja no se borra: se archiva igual que con olvidar(), asi que se
    puede volver a ella. Devuelve una frase corta para decir en voz alta.

    ⚠ El `/compact` de adentro de Claude Code no se puede pedir desde afuera
    (probado: por stdin el CLI lo toma como texto), asi que esto es a mano.
    """
    global _esperando_dia, _pendiente
    if not _SESION:
        return "Esta charla recién empieza: no hay nada que compactar."
    from app.voz.sesiones_movil import PEDIDO_RESUMEN, SIEMBRA
    # Todo el compactado bajo UN solo candado: son dos turnos con Claude (resumen y
    # siembra) y entre uno y otro el proceso viejo se apaga. Si un comando nuevo se
    # colaba justo ahi, arrancaba una sesion en blanco y la siembra se le pegaba atras,
    # mezclada. Sosteniendo el candado de punta a punta, ese comando espera afuera.
    with _lock_turno:
        viejo = _SESION
        resumen = preguntar(PEDIDO_RESUMEN, crudo=True, para_voz=False)
        if not resumen or len(resumen) < 40 or _es_falta_de_cupo(resumen, estricto=True):
            # Sin resumen no se compacta nada: arrancar de cero en silencio seria
            # hacerle perder la charla justo cuando cree que la esta salvando.
            return "No pude resumir la charla, así que la dejé como estaba."
        _esperando_dia = False
        _pendiente = None
        _archivar_actual()             # la vieja queda guardada; el proceso arranca limpio
        _guardar_sesion()
        preguntar(SIEMBRA.format(resumen=resumen), crudo=True, para_voz=False)
        print(f"claude: compactada {viejo[:8]} -> {(_SESION or '-')[:8]}", flush=True)
    return "Listo, resumí lo que veníamos hablando y seguimos en una charla nueva."


def _limpiar(t):
    """Deja texto apto para LEER EN VOZ: sin codigo, markdown, links ni URLs."""
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)              # bloques de codigo
    # cortar la seccion de fuentes/referencias del final (Claude la agrega al buscar en la web)
    t = re.split(r"\n?\s*(?:sources?|fuentes?|referencias?|links?)\s*:", t, flags=re.IGNORECASE)[0]
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)                  # [texto](url) -> texto
    t = re.sub(r"https?://\S+|www\.\S+", "", t)                     # URLs sueltas
    t = re.sub(r"^\s*[-*•]\s*", " ", t, flags=re.MULTILINE)         # vinietas
    t = re.sub(r"[*_`#>\[\]]", "", t)                               # markdown restante
    t = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF]", "", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip(" -–—")


def _turno(consulta):
    """Un turno contra el proceso vivo. Devuelve (texto, error) — error None si salio bien."""
    global _SESION, _en_vuelo
    _en_vuelo = True                               # mientras piensa, cancelar() tiene efecto
    try:
        return _turno_ya(consulta)
    finally:
        _en_vuelo = False


def _descartar_restos():
    """Vacia la cola ANTES de mandar un turno: lo que haya ahi es de un turno viejo.

    Es la mitad del arreglo del chat corrido en uno: si un turno fallo por timeout,
    su result podia llegar tarde, quedar aca, y la pregunta siguiente lo levantaba
    como si fuera su respuesta — y de ahi en adelante CADA pregunta se contestaba
    con la respuesta de la anterior. Entre turno y turno no puede haber nada
    legitimo en la cola (_lock_turno garantiza un turno por vez)."""
    while True:
        try:
            _, linea = _cola.get_nowait()
        except queue.Empty:
            return
        try:
            if json.loads(linea).get("type") == "result":
                print("claude: descarto una respuesta tardia de un turno viejo", flush=True)
        except Exception:
            pass


def _turno_ya(consulta):
    global _SESION
    proc = _vivo                  # MI proceso: lo que venga de otro no es de este turno
    _descartar_restos()
    msg = {"type": "user", "message": {"role": "user",
                                       "content": [{"type": "text", "text": consulta}]}}
    try:
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    except Exception as e:
        return None, f"no pude escribirle al proceso: {e}"

    fin = time.time() + TIMEOUT
    ultima_senal = time.time()
    previa = _SESION
    while time.time() < fin:
        # OJO: aunque hayas cancelado seguimos leyendo hasta el 'result'. Si cortaramos
        # aca, ese result quedaria en la cola y se lo comeria tu PROXIMA pregunta.
        try:
            quien, linea = _cola.get(timeout=1)
        except queue.Empty:
            # No alcanza con el TIMEOUT total: son 10 minutos, y esperar 10 minutos en
            # silencio es lo que hacia que un cupo agotado pareciera un cuelgue. Pero
            # BAJAR el total romperia las tareas largas de verdad. La distincion es que
            # una tarea larga SIGUE MANDANDO eventos (tool_use, texto parcial): si no
            # llega ni una linea en SIN_SENAL_SEG, no esta trabajando, esta colgada.
            if time.time() - ultima_senal > SIN_SENAL_SEG:
                return None, f"no mando nada por {SIN_SENAL_SEG:.0f} segundos"
            continue
        if quien is not proc:
            # Resto de un proceso anterior (llego DESPUES del vaciado de arriba).
            # Ni cuenta como senal de vida ni puede cortar el turno: su None avisa
            # que murio EL VIEJO, no el que esta trabajando ahora.
            continue
        ultima_senal = time.time()
        if linea is None:
            return None, "el proceso se cerro"
        linea = linea.strip()
        if not linea:
            continue
        try:
            data = json.loads(linea)
        except json.JSONDecodeError:
            continue
        sid = data.get("session_id")
        if sid and sid != _SESION:
            _SESION = sid
            _guardar_sesion(sid)                   # sobrevive al reinicio de voz.py
        if data.get("type") != "result":
            continue                               # eventos intermedios (init, tool_use, ...)
        global _turnos
        _turnos = data.get("num_turns") or _turnos
        print("claude sesion: %s -> %s | turnos=%s" % (
            (previa or "-")[:8], (_SESION or "-")[:8], _turnos), flush=True)
        texto = (data.get("result") or "").strip()
        if (data.get("is_error") or not texto) and not _CANCELADO:
            print("claude respuesta vacia/erronea: subtype=%r is_error=%r" % (
                data.get("subtype"), data.get("is_error")), flush=True)
        return texto, None
    return None, "tardo demasiado"


# Como se ve "me quede sin cupo" cuando llega del CLI. Van DOS patrones a proposito:
#
#  - el ANCHO se usa sobre el mensaje de error, donde ya sabemos que algo fallo y una
#    falsa alarma no hace dano: como maximo te explica mal un error real.
#  - el ANGOSTO se usa sobre la RESPUESTA de Laura, y ahi hay que ser estricto: si
#    incluyera "429" o "quota" a secas, un "el archivo tiene 429 lineas" te haria
#    escuchar "me quede sin cupo" estando todo bien.
_SIN_CUPO_ANCHO = re.compile(
    r"usage limit|rate.?limit|limit reached|out of (usage|credit)|quota|"
    r"resets? at|upgrade to|too many requests|\b429\b", re.IGNORECASE)
_SIN_CUPO_ANGOSTO = re.compile(
    r"usage limit reached|claude usage limit|rate limit exceeded|"
    r"you(?:'ve| have) (?:reached|hit) your (?:usage )?limit", re.IGNORECASE)


def _es_falta_de_cupo(texto, estricto=False):
    if not texto:
        return False
    patron = _SIN_CUPO_ANGOSTO if estricto else _SIN_CUPO_ANCHO
    return bool(patron.search(str(texto)))


def _frase_sin_cupo():
    """Que se dice cuando no hay mas cupo. Corto, claro, y con lo que SI se puede hacer."""
    extra = ""
    try:
        # Solo los cupos que Laura consume de verdad: nombrar el de Fable (que ella no
        # toca, porque corre Sonnet) te mandaria a mirar el lugar equivocado.
        filas = cupo.estado(claves=cupo.CUPOS_DE_LAURA)
        if filas:
            nombre, pct = filas[0]
            extra = f" El {nombre} esta al {pct:.0f} por ciento."
    except Exception:
        pass
    return ("Me quede sin cupo de Claude, asi que por ahora no puedo pensar con el "
            "cerebro grande." + extra + " Preguntame a mi que sigo funcionando, "
            "o espera a que se renueve.")


def _con_avisos(texto):
    """Pega los avisos AL FINAL de la respuesta, nunca antes.

    Es un requisito, no un detalle: interrumpirte la respuesta con una advertencia es
    peor que la advertencia. Primero te contesta lo que preguntaste, y despues avisa.
    Cada aviso se dice UNA sola vez por sesion: si lo repitiera en cada respuesta lo
    apagarias el primer dia y entonces no sirve para nada.
    """
    avisos = []
    if _turnos >= cupo.AVISO_TURNOS and "turnos" not in _avisado:
        _avisado.add("turnos")
        avisos.append(f"Ah, y ya vamos {_turnos} idas y vueltas en esta charla. "
                      "Cada pregunta me sale mas cara porque te reenvio todo lo anterior. "
                      "Si queres, arrancamos una nueva.")
    try:
        a = cupo.aviso_cupo()
    except Exception as e:
        print("cupo: no pude mirar el consumo:", e, flush=True)
        a = None
    if a and "cupo" not in _avisado:
        _avisado.add("cupo")
        avisos.append(a)
    return " ".join([texto] + avisos) if avisos else texto


def esperando_dia():
    """True si dijo el saludo del dia y esta esperando que elijas.

    voz.py lo consulta ANTES de rutear: si no, "segui con la anterior" cae en el
    comando de musica (su patron tiene "segu[ií]") y en vez de contestarte apretaria
    play. La respuesta al saludo tiene que ganarle a todo lo demas.
    """
    return _esperando_dia


def resumen_de(sesion=None):
    """Resume una sesion anterior. Le pasa la charla vieja como texto a la de hoy."""
    s = sesion or sesion_anterior()
    if not s or not s.get("session_id"):
        return "No tengo guardada ninguna sesion anterior para resumirte."
    charla = _charla_de(s["session_id"])
    if not charla:
        return f"Tengo anotada la sesion del {s.get('dia')} pero no encontre la charla."
    print(f"claude: resumo la sesion {s['session_id'][:8]} del {s.get('dia')} "
          f"({len(charla)} caracteres)", flush=True)
    # crudo=True es OBLIGATORIO: el prompt lleva la charla de ayer adentro, y si ayer
    # dijiste "de que hablamos" el detector de resumenes se dispararia con su propio
    # pedido y se llamaria a si mismo para siempre.
    return preguntar(PROMPT_RESUMEN.format(dia=s.get("dia") or "anterior", charla=charla),
                     crudo=True)


def responder_dia(texto):
    """Interpreta tu respuesta al saludo del dia.

    Devuelve el texto para hablar, o None si lo que dijiste NO parece una respuesta
    al saludo (ahi resuelve el dia solo, con sesion nueva, y voz.py sigue ruteando
    tu pedido normalmente). Sin esto, si ignorabas el saludo y decias "pone musica",
    este enganche se comia el comando.
    """
    global _esperando_dia, _pendiente, _DIA
    t = _plano(texto)
    # El orden importa y esta elegido a mano (ver los comentarios de los patrones).
    sigue = resumen = nueva = False
    if _SIGUE_VERBO.search(t):
        sigue = True                       # "continua/segui..." manda sobre todo lo demas
    elif _RESUMEN.search(t):
        resumen = True                     # "de que hablamos", "donde quedamos?"
    elif _SIGUE_FUERTE.search(t):
        sigue = True                       # "la de ayer", "la misma"
    elif _NUEVA_FUERTE.search(t) or _NO_SUELTO.match(t):
        nueva = True
    elif _SI_SUELTO.match(t):
        sigue = True                       # "si", "dale" pelados = seguimos
    if not (sigue or nueva or resumen):
        _esperando_dia = False
        _pendiente = None
        _archivar_actual()                 # el dia se resuelve igual: sesion nueva
        _guardar_sesion()
        print("claude: no contestaste el saludo, arranco sesion nueva y sigo tu pedido",
              flush=True)
        return None                        # que voz.py rutee lo que dijiste

    _esperando_dia = False
    pendiente, _pendiente = _pendiente, None

    if resumen:                            # "resumime lo de ayer" tambien es una respuesta
        anterior = sesion_anterior()
        _archivar_actual()                 # el dia arranca igual: la vieja queda archivada
        _guardar_sesion()
        return resumen_de(anterior)

    if sigue:
        _DIA = _dia_de()                   # la misma sesion, pero ya cuenta como de hoy
        _guardar_sesion()
        print(f"claude: seguimos con la sesion {(_SESION or '-')[:8]}", flush=True)
        return preguntar(pendiente) if pendiente else "Dale, seguimos donde quedamos."

    # Nueva: la anterior no se pierde, queda en el historial para poder volver.
    _archivar_actual()
    _guardar_sesion()
    print(f"claude: sesion nueva del dia {_DIA}", flush=True)
    if pendiente:
        return preguntar(pendiente)        # lo que preguntaste antes del saludo, no se pierde
    return "Listo, arrancamos de cero. Contame."


def preguntar(consulta, reintentar=True, crudo=False, para_voz=True):
    """Manda la consulta al proceso persistente. Devuelve texto corto para hablar.

    crudo=True manda el texto tal cual, sin mirar si parece un pedido de resumen ni
    si arranca el dia. Lo usa resumen_de(), que ya viene de esos caminos.

    para_voz=False devuelve la respuesta SIN aplanar para el TTS: conserva saltos de
    linea y puntuacion tal cual. Lo usa Laura por Telegram, donde la respuesta se
    LEE en el telefono y aplanarla dejaria un parrafo gigante de una sola linea.
    """
    global _CANCELADO, _esperando_dia, _pendiente

    if not crudo:
        # Primera charla de un dia nuevo: preguntar ANTES de gastar un solo token. El
        # saludo lo dice Piper, no Claude, asi que esto no cuesta nada. Y tu pregunta
        # queda guardada en _pendiente: se contesta despues de que elijas.
        if (not _esperando_dia and _SESION and _DIA and _DIA != _dia_de()
                and (time.time() - _ultimo_turno) > GRACIA_CORTE):
            _esperando_dia = True
            _pendiente = consulta
            print(f"claude: primer turno del dia {_dia_de()} (la sesion abierta es del {_DIA})",
                  flush=True)
            return SALUDO_DIA

        # Pedido de resumen suelto, sin venir del saludo ("Laura, de que hablamos ayer?")
        # len corto es a proposito: ver el comentario de RESUMEN_LARGO_MAX arriba.
        if (not _esperando_dia and len(consulta) <= RESUMEN_LARGO_MAX
                and _RESUMEN.search(_plano(consulta))):
            anterior = sesion_anterior()
            if anterior:
                return resumen_de(anterior)

    # ⛔ Aca NO va el tope automatico de las sesiones del celular (compactar antes del
    # turno). Laura ya tiene el suyo, y es mejor: el vigilante del panel se lo pide
    # cuando la charla esta QUIETA (160 mil tokens, `AUTOCOMPACTAR_EN` en panel.py).
    # Compactar antes de contestarte serian ~1 minuto de silencio en medio de una charla
    # hablada — justo lo que ese diseño evita. Probado y descartado el 2026-08-18.
    with _lock_turno:                            # un turno por vez (una pregunta -> un result)
        _CANCELADO = False
        # ¿Le cambiaste el modelo desde el panel? El proceso vivo tiene el de antes.
        _revisar_modelo()
        if _vivo is None or _vivo.poll() is not None:
            if not _arrancar():                    # arranca solo si hace falta (o tras cancelar)
                return "No pude hablar con Claude."
        texto, error = _turno(consulta)

    if _CANCELADO:
        print("claude: consulta cancelada (se mantiene la conversacion)", flush=True)
        return ""
    if error:
        print("claude fallo:", error, flush=True)
        _apagar()                                  # que la proxima arranque limpio
        # Si se acabo el cupo, reintentar es regalar diez segundos para volver a fallar
        # por lo mismo. Y sobre todo: hay que DECIR que fue el cupo. Antes contestaba
        # "No pude hablar con Claude" y te quedabas sin saber si era el wifi, el micro,
        # Anthropic caido o el proceso muerto.
        if _es_falta_de_cupo(error):
            return _frase_sin_cupo()
        if reintentar:
            print("claude: reintento con proceso nuevo", flush=True)
            return preguntar(consulta, reintentar=False, crudo=crudo, para_voz=para_voz)
        return "No pude hablar con Claude."

    texto = _limpiar(str(texto)) if para_voz else str(texto).strip()
    # estricto=True: sobre la respuesta hay que pedir la frase completa, no una palabra
    # suelta, o un "el archivo tiene 429 lineas" te avisa de un cupo que esta sano.
    if _es_falta_de_cupo(texto, estricto=True):
        return _frase_sin_cupo()
    if not texto:
        return "Claude no me devolvio respuesta."
    return _con_avisos(texto)


if __name__ == "__main__":
    import sys
    print(preguntar(" ".join(sys.argv[1:]) or "Decime en una frase que hace el archivo voz.py"))
