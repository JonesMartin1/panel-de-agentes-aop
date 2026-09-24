"""
Acciones del asistente de voz. EXTENSIBLE: agrega entradas a COMANDOS.
Cada comando: (regex, handler). El handler recibe el match y devuelve
el texto que el asistente va a DECIR por voz.
"""

import os
import re
import time
import ctypes
import datetime
import subprocess
import unicodedata
import urllib.parse
from pathlib import Path

import keyboard
import requests
try:
    from pyvda import AppView, VirtualDesktop, get_virtual_desktops
except Exception:
    VirtualDesktop = None
    AppView = None

# ⚠ Todo lo que se lanza por `shell=True` pasa por un cmd.exe, y la voz corre SIN
# consola: sin esta marca, cada vez que Laura abre una app o busca algo en Google
# parpadea una ventana negra en la pantalla (2026-09-06). Al `start` no le cambia
# nada: igual abre el programa.
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NUM = {"uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
       "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}

APPS = {
    "chrome": "chrome", "navegador": "chrome", "google": "chrome",
    "code": "code", "vs code": "code", "visual studio code": "code", "codigo": "code",
    "explorador": "explorer", "archivos": "explorer",
    "bloc de notas": "notepad", "notepad": "notepad",
    "calculadora": "calc", "calc": "calc",
    "spotify": "spotify", "whatsapp": "whatsapp", "terminal": "wt", "cmd": "cmd",
}


def _norm(t):
    t = t.lower().strip()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t


def _num(s):
    s = s.strip().lower()
    return int(s) if s.isdigit() else NUM.get(s)


# ---------------- Handlers ----------------
def ir_escritorio(m):
    n = _num(m.group(1))
    if not n or VirtualDesktop is None:
        return "No pude cambiar de escritorio."
    total = len(get_virtual_desktops())
    n = max(1, min(n, total))
    VirtualDesktop(number=n).go()
    return f"Escritorio {n}."


def escritorio_sig(m):
    if VirtualDesktop is None:
        return "No disponible."
    actual = VirtualDesktop.current().number
    total = len(get_virtual_desktops())
    n = min(actual + 1, total)
    VirtualDesktop(number=n).go()
    return f"Escritorio {n}."


def escritorio_ant(m):
    if VirtualDesktop is None:
        return "No disponible."
    n = max(VirtualDesktop.current().number - 1, 1)
    VirtualDesktop(number=n).go()
    return f"Escritorio {n}."


def abrir_app(m):
    pedido = _norm(m.group(1))
    for nombre, cmd in APPS.items():
        if nombre in pedido:
            if cmd == "whatsapp":
                return traer_whatsapp()   # trae la ventana si ya esta abierta
            try:
                subprocess.Popen(f'start "" {cmd}', shell=True, creationflags=SIN_VENTANA)
                return f"Abriendo {nombre}."
            except Exception:
                return f"No pude abrir {nombre}."
    return _abrir_web(m.group(1))   # no es app conocida -> abrir como pagina web


# "WhatsApp" y las formas en que Whisper lo escribe cuando lo decis hablado.
# "chat" (y "chad", que es como Whisper suele escribirlo dicho en castellano)
# tambien abre WhatsApp — pedido 2026-08-11: mismo comando, dos nombres. El \b
# y el (?!\s*gpt) van ADENTRO de la alternativa: "chatarra" no es el chat, y
# "abri chat gpt" tiene que seguir siendo abrir_app, no traer WhatsApp.
_RE_WHATSAPP = r"(?:whats?\s*ap+|was+ap+|[gh]uas+ap+|chats?\b(?!\s*gpt)|chads?\b)"


def _ventana_whatsapp():
    """Busca la ventana de la app de escritorio de WhatsApp, aunque este en otro
    escritorio virtual (ahi sigue "visible", solo que tapada). Devuelve hwnd o None."""
    user32 = ctypes.windll.user32
    encontrada = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def mirar(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        largo = user32.GetWindowTextLengthW(hwnd)
        if not largo:
            return True
        buf = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buf, largo + 1)
        # Titulo EXACTO (con o sin contador de no leidos): una pestania
        # "WhatsApp - Google Chrome" no es la app y no hay que traerla.
        t = _norm(buf.value).strip()
        if t == "whatsapp" or re.fullmatch(r"\(\d+\)\s*whatsapp", t):
            encontrada.append(hwnd)
            return False
        return True

    user32.EnumWindows(mirar, 0)
    return encontrada[0] if encontrada else None


def _traer_al_frente(hwnd):
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE: estaba minimizada
    if user32.SetForegroundWindow(hwnd):
        return True
    # Windows no deja robar el foco desde un proceso de fondo; el toque de Alt
    # lo habilita (truco conocido). Se suelta SIEMPRE o queda Alt apretado.
    keyboard.press("alt")
    try:
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        keyboard.release("alt")


def traer_whatsapp(m=None):
    """"Venus, WhatsApp": trae la ventana AL escritorio que estas mirando (no te
    lleva al de ella) y la pone al frente; si no esta abierta, la abre."""
    hwnd = _ventana_whatsapp()
    if hwnd:
        try:
            if AppView is not None:
                AppView(hwnd=hwnd).move(VirtualDesktop.current())
        except Exception as e:
            print("whatsapp: no pude moverlo de escritorio:", e, flush=True)
        if _traer_al_frente(hwnd):
            return "Ahi lo tenes."
        # No le pude dar el foco: que lo levante la propia app por el protocolo.
    try:
        subprocess.Popen('start "" whatsapp:', shell=True, creationflags=SIN_VENTANA)
        return "Abriendo WhatsApp."
    except Exception:
        return "No pude abrir WhatsApp."


def volumen(m):
    accion = _norm(m.group(0))
    if "silen" in accion or "mut" in accion:
        keyboard.send("volume mute")
        return "Silenciado."
    tecla = "volume up" if ("sub" in accion or "mas" in accion) else "volume down"
    for _ in range(5):
        keyboard.send(tecla)
    return "Listo."


_RE_PIZARRA = (r"(?:anot[aá]|escrib[ií]|pon[eé]|agreg[aá]|dej[aá]|sum[aá]|carg[aá]|met[eé])\w*"
                r"(?:me|le|lo)?\s+(?:en|a|sobre)\s+(?:la\s+|mi\s+)?pizarra\s*(?:que\s+)?[\s,:.\-]*(.+)"
                r"|^\W*(?:en|a|sobre)\s+(?:la\s+|mi\s+)?pizarra[\s,:.\-]+"
                r"(?:anot[aá]|escrib[ií]|pon[eé]|agreg[aá]|sum[aá])?\w*\s*(?:que\s+)?[\s,:.\-]*(.+)"
                r"|^\W*pizarra[\s,:.\-]+(.+)")


def es_anotar_pizarra(texto):
    """¿Este pedido es 'anota tal cosa en la pizarra'? Lo usa voz.py para
    resolverlo sin molestar al LLM incluso cuando estas hablando con Laura."""
    return bool(re.search(_RE_PIZARRA, _norm(texto)))


def anotar_pizarra(m):
    """"anota en la pizarra que hay que llamar a Juan" -> crea una nota en la pizarra
    web del panel (http://localhost:8750/pizarra). Va ANTES de poner_musica en
    COMANDOS: ese patron es "pon(e|er)... + lo que sea" y se comeria "pone X en
    la pizarra" como si fuera una cancion si quedara despues."""
    # El patron tiene tres alternativas; solo una captura texto en cada match.
    texto = next((g for g in m.groups() if g), "").strip(" .,:;")
    if not texto:
        return "¿Que anoto en la pizarra?"
    try:
        requests.post("http://127.0.0.1:8750/pizarra/agregar",
                       json={"tipo": "nota", "texto": texto}, timeout=5)
        return "Anotado en la pizarra."
    except Exception:
        return "No pude anotar en la pizarra. ¿Esta prendido el panel?"


def poner_musica(m):
    """"pone tal cancion" -> la busca y la reproduce con la API de Spotify."""
    pedido = m.group(1).strip()
    # "poneme EN SPOTIFY tal cosa" o "pone tal cosa EN SPOTIFY": el nombre de la app
    # se iba adentro de la busqueda y la ensuciaba. Se saca de las dos puntas, solo
    # si queda algo que buscar despues.
    sin_app = re.sub(r"^(?:en|por|con|desde)\s+(?:el\s+|la\s+)?spotify\b[\s,:]*", "",
                     pedido).strip()
    sin_app = re.sub(r"[\s,]+(?:en|por|de)\s+(?:el\s+|la\s+)?spotify\W*$", "",
                     sin_app).strip()
    if sin_app:
        pedido = sin_app
    # "pone spotify" a secas es ABRIR la app, no poner una cancion llamada Spotify.
    if _norm(pedido).strip(" .") in ("spotify", "el spotify", "la spotify"):
        try:
            subprocess.Popen('start "" spotify', shell=True, creationflags=SIN_VENTANA)
            return "Abriendo spotify."
        except Exception:
            return "No pude abrir spotify."
    # Import adentro y no arriba: si falta el token o las credenciales, que falle
    # SOLO este comando y no el arranque entero del asistente.
    try:
        from app.voz import spotify
    except Exception as e:
        return f"No pude cargar Spotify: {e}"
    try:
        r = spotify.poner(pedido)
        # Gracia para el vigilante de la charla: sin esto, la cancion que pediste
        # arrancaba y se pausaba al medio segundo porque "habia actividad" (Venus
        # confirmando "Poniendo tal...").
        try:
            from app.voz import media_pausa
            media_pausa.dar_gracia()
        except Exception:
            pass
        return r
    except Exception as e:
        return f"No pude poner eso: {e}"


def media_playpause(m):
    """"pausa" pausa TODO lo que suene (Spotify, video en Chrome, lo que sea) por las
    sesiones de medios de Windows; "reproduci/play/segui" lo trae de vuelta. La tecla
    play/pause queda de RESPALDO para reproductores que no se registran en Windows —
    pero solo si la API no vio nada, porque la tecla es un toggle a ciegas."""
    palabra = _norm(m.group(1) if (m.lastindex or 0) >= 1 else m.group(0))
    quiere_pausa = palabra.startswith(("pausa", "para"))
    try:
        from app.voz import media_pausa
        if quiere_pausa:
            return "Pausado." if media_pausa.pausar_manual() else "No habia nada sonando."
        # Escalera del play: 1) lo que pausamos nosotros (charla o "pausa" tuya);
        # 2) el reproductor ACTUAL de Windows aunque lo hayas pausado vos a mano
        # ayer; 3) la tecla, ultimo recurso.
        if media_pausa.reanudar_manual():
            return "Va de nuevo."
        if media_pausa.dar_play():
            return "Play."
    except Exception as e:
        print("media por sesiones fallo, uso la tecla:", e, flush=True)
    keyboard.send("play/pause media")
    return "Ok."


def copiar_seleccion(m):
    """"Venus, copia": Ctrl+C sobre lo que tengas seleccionado. No toca el foco."""
    keyboard.send("ctrl+c")
    return "Copiado."


def pegar_portapapeles(m):
    """"Venus, pega": Ctrl+V donde este el cursor. No toca el foco."""
    keyboard.send("ctrl+v")
    return "Pegado."


def media_next(m):
    keyboard.send("next track")
    return "Siguiente."


def media_prev(m):
    keyboard.send("previous track")
    return "Anterior."


def hora(m):
    ahora = datetime.datetime.now().strftime("%H:%M")
    return f"Son las {ahora}."


# --- Edicion de texto en el campo enfocado ---
def borrar_texto(m):
    keyboard.send("ctrl+a")
    time.sleep(0.05)
    keyboard.send("delete")
    return "Listo, borrado."


def borrar_palabra(m):
    keyboard.send("ctrl+backspace")
    return "Listo."


def seleccionar_todo(m):
    keyboard.send("ctrl+a")
    return "Seleccionado."


def dejar_de_leer(m):
    """Apaga la lectura automatica de sesiones (la perilla es el archivo de rutas)."""
    from app.rutas import SEGUIR_LECTURA
    if not SEGUIR_LECTURA.exists():
        return "No estaba leyendo ninguna sesion."
    try:
        SEGUIR_LECTURA.unlink()
        return "Listo, no leo mas."
    except OSError:
        return "No pude apagar la lectura."


# ---------------- Registro (orden importa) ----------------
COMANDOS = [
    # Apagar la lectura automatica va PRIMERO: "deja de leer" no puede caer en ningun
    # otro patron (y "borra"/"para" andan cerca en la lista).
    (r"(?:dej[aá]\w*|par[aá]|basta|corta) (?:de )?le(?:er|erme|yendo)"
     r"|no (?:me )?(?:sigas|estes) leyendo|apag[aá]\w* la lectura", dejar_de_leer),
    # "copia" / "pega" PELADOS (o con un "esto/aca" de yapa). Anclados de punta a
    # punta a proposito: "copia el archivo x a y" es tarea para Laura, no un Ctrl+C.
    (r"^\W*copi(?:a|ar|ame|alo)(?:\s+(?:esto|eso|el texto|la seleccion))?\W*$",
     copiar_seleccion),
    (r"^\W*peg(?:a|ar|ame|alo)(?:\s+(?:esto|eso|aca|ahi))?\W*$",
     pegar_portapapeles),
    # Si nombras "palabra", NUNCA borres todo el campo (antes "borra la primera palabra"
    # caia en el borrado general y se llevaba todo por delante).
    (r"(?:borr\w*|elimin\w*).*\bpalabras?\b", borrar_palabra),
    # "borra" a secas ya alcanza (selecciona todo y borra). Va DESPUES de borrar_palabra
    # para no pisar "borra la ultima palabra"; "borra la memoria" lo agarra voz.py antes.
    (r"\b(?:borr\w*|elimin\w*|limpi\w*)\b", borrar_texto),
    (r"seleccion(a|ar|ame|alo|alos)", seleccionar_todo),
    # Whisper transcribe mal las frases cortas ("escritorio dos" -> "espiritorio o no"):
    # aceptamos variantes del sustantivo y numero en digito o palabra.
    (r"(?:escritorio|escritori[oa]s?|espiritorio|espiritori[oa]|escrito rio|es critorio)"
     r"[\s,.:]*(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b", ir_escritorio),
    # Solo el numero ("Venus" -> "3") tambien cambia de escritorio. Anclado a TODA la
    # frase (^...$) a proposito: si dijeras "poné el 3" o "borra 2 palabras" NO entra aca.
    (r"^\W*(\d{1,2}|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\W*$", ir_escritorio),
    (r"(siguiente escritorio|escritorio siguiente|proximo escritorio)", escritorio_sig),
    (r"(escritorio anterior|anterior escritorio)", escritorio_ant),
    # WhatsApp va ANTES de Spotify y de abrir_app a proposito: "pone whatsapp" no es
    # una cancion, y "abri whatsapp" tiene que TRAER la ventana si ya esta abierta.
    # Dos formas: "whatsapp" pelado (con cortesia opcional) o verbo + whatsapp.
    (rf"^\W*(?:(?:dale|por\s*favor|porfa|che|a\s*ver)[\s,]+)*(?:(?:el|la|mi|al)\s+)?"
     rf"{_RE_WHATSAPP}(?:[\s,]+(?:por\s*favor|porfa|dale|aca|aqui|ya|ahora))*\W*$"
     rf"|^\W*(?:(?:pod[e]s|puedes|podrias|quiero que|necesito que|me|por\s*favor|dale|a\s*ver)"
     rf"[\s,]+)*(?:trae\w*|mostra\w*|abr[ie]\w*|pon[ei]\w*|lleva\w*|dame)"
     rf"[\s,]+(?:(?:me|el|la|a|al|en|un|mi)\s+)*{_RE_WHATSAPP}\b", traer_whatsapp),
    # Pizarra VA ANTES de Spotify a proposito: "pone [algo] en la pizarra" contiene
    # "pone... + lo que sea" y sin este orden lo agarraria poner_musica primero.
    # Tres formas, todas resueltas ACA (sin pasar por el LLM: ~20 ms contra varios
    # segundos si tiene que pensarlo Claude):
    #   1) "anota/pone/agrega/suma ... EN|A|SOBRE la pizarra ..."
    #   2) "en la pizarra anota ..."      (el destino primero)
    #   3) "pizarra: ..." / "pizarra, ..."  (lo mas corto de todo)
    (_RE_PIZARRA, anotar_pizarra),
    # Spotify VA ANTES de abrir_app y de media_playpause a proposito:
    #  - "reproduci tal cancion" caeria en media_playpause (que tiene "reproduci")
    #    y solo apretaria play, sin poner nada.
    #  - _norm() SACA LOS ACENTOS, asi que el patron va sin tildes: llega "pone",
    #    no "poné". No agregar [eé] aca, no sirve de nada.
    # Anclado con ^ para que no se dispare en medio de una frase larga. PERO el ancla
    # sola no alcanza: \W* se come los signos, NO las palabras, y pedir las cosas por
    # favor es lo normal. "Puedes poner la radio de..." no matcheaba NADA y se lo comia
    # el LLM, que contestaba "No pude hacer eso" (pasó 3 veces seguidas el 2026-08-11).
    # De ahi el grupo de cortesia opcional. Sin tildes: _norm() las saca.
    (r"^\W*(?:(?:pod[e]s|puedes|podrias|quiero que|necesito que|me|por favor|dale|a ver)"
     # Tras el verbo va [\s,.:]+ y NO \s+: Whisper pone coma cuando haces una pausita
     # ("Reproduci, bring me to life") y con \s+ el comando caia en media_playpause,
     # que apretaba play/pause y contestaba "Ok." sin poner nada (2026-08-11).
     r"[\s,]+)*(?:pon(?:e|er)(?:me|melo|mela|lo|la)?|reproduci(?:me)?|toca(?:me)?|"
     r"escucha(?:me)?|quiero escuchar|haceme escuchar)[\s,.:]+(.+)", poner_musica),
    (r"(?:abri|abrir|abre|abrime|entr[aá]|entrar|entrame|llev[aá]me|met[eé]te?|meti)\s+(?:a |al |el |la |en |a la |los |las )?(.+)", abrir_app),
    (r"(sub[ií].*volumen|baj[aá].*volumen|volumen.*(?:arriba|abajo)|silenci|mute|mut[eé]a)", volumen),
    (r"(pausa|pausar|reproduc[ií]|play|segu[ií]|par[aá] la m[uú]sica)", media_playpause),
    (r"(siguiente canci[oó]n|proxima canci[oó]n|pasa.*canci[oó]n)", media_next),
    (r"(canci[oó]n anterior|tema anterior|volv[eé].*canci[oó]n)", media_prev),
    (r"(qu[eé] hora es|la hora)", hora),
]


def ejecutar(texto):
    """Devuelve (respuesta, True) si matcheo un comando; (None, False) si no."""
    t = _norm(texto)
    for patron, fn in COMANDOS:
        m = re.search(patron, t)
        if m:
            try:
                return fn(m), True
            except Exception as e:
                return f"Hubo un error: {e}", True
    return None, False


# ============================================================
#  HERRAMIENTAS para tool-calling del LLM (parametros directos)
# ============================================================
def t_escritorio(numero):
    if VirtualDesktop is None:
        return "No puedo cambiar de escritorio."
    total = len(get_virtual_desktops())
    try:
        n = int(numero)
    except (TypeError, ValueError):
        return "No entendi que escritorio."
    n = max(1, min(n, total))
    VirtualDesktop(number=n).go()
    return f"Escritorio {n}."


def t_abrir(app):
    key = _norm(str(app))
    if re.search(_RE_WHATSAPP, key):
        return traer_whatsapp()   # trae la ventana si ya esta abierta
    cmd = None
    for nombre, c in APPS.items():
        if nombre in key or key in nombre:
            cmd = c
            break
    cmd = cmd or key
    try:
        subprocess.Popen(f'start "" {cmd}', shell=True, creationflags=SIN_VENTANA)
        return f"Abriendo {app}."
    except Exception:
        return f"No pude abrir {app}."


def t_cerrar(app):
    key = _norm(str(app))
    exe = None
    for nombre, c in APPS.items():
        if nombre in key:
            exe = c
            break
    exe = exe or key
    name = exe if exe.lower().endswith(".exe") else exe + ".exe"
    r = subprocess.run(f'taskkill /IM "{name}" /F', shell=True, capture_output=True,
                       creationflags=SIN_VENTANA)
    return f"Cerre {app}." if r.returncode == 0 else f"No encontre {app} abierto."


def t_volumen(accion):
    a = _norm(str(accion))
    if "silenc" in a or "mut" in a:
        keyboard.send("volume mute")
        return "Silenciado."
    tecla = "volume up" if ("sub" in a or "mas" in a or "arriba" in a) else "volume down"
    for _ in range(5):
        keyboard.send(tecla)
    return "Listo."


def t_media(accion):
    a = _norm(str(accion))
    if "sig" in a or "proxim" in a or "next" in a:
        keyboard.send("next track"); return "Siguiente."
    if "ant" in a or "prev" in a:
        keyboard.send("previous track"); return "Anterior."
    # Igual que media_playpause: sesiones de Windows primero, tecla de respaldo.
    try:
        from app.voz import media_pausa
        if "paus" in a or "para" in a or "stop" in a:
            return "Pausado." if media_pausa.pausar_manual() else "No habia nada sonando."
        if "play" in a or "reproduc" in a or "segu" in a or "reanud" in a:
            if media_pausa.reanudar_manual():
                return "Va de nuevo."
            if media_pausa.dar_play():
                return "Play."
    except Exception as e:
        print("t_media por sesiones fallo, uso la tecla:", e, flush=True)
    keyboard.send("play/pause media"); return "Ok."


def t_hora():
    return "Son las " + datetime.datetime.now().strftime("%H:%M") + "."


def t_bloquear():
    subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True,
                     creationflags=SIN_VENTANA)
    return "Bloqueando la computadora."


def t_captura():
    try:
        import pyautogui
        carpeta = Path.home() / "Pictures"
        carpeta.mkdir(exist_ok=True)
        p = carpeta / ("captura_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png")
        pyautogui.screenshot(str(p))
        return "Captura guardada en Imagenes."
    except Exception:
        return "No pude sacar la captura."


def t_buscar_web(consulta):
    q = urllib.parse.quote(str(consulta))
    subprocess.Popen(f'start "" "https://www.google.com/search?q={q}"', shell=True,
                     creationflags=SIN_VENTANA)
    return f"Buscando {consulta}."


# --- Navegador (Chrome IA via Playwright) ---
SITIOS = {"gmail": "mail.google.com", "youtube": "youtube.com", "kommo": "kommo.com",
          "google": "google.com", "whatsapp web": "web.whatsapp.com", "whatsapp": "web.whatsapp.com",
          "chatgpt": "chatgpt.com", "wikipedia": "wikipedia.org", "maps": "maps.google.com",
          "drive": "drive.google.com", "calendario": "calendar.google.com", "calendar": "calendar.google.com",
          "instagram": "instagram.com", "facebook": "facebook.com"}


# muletillas/cortesia que ensucian el destino ("entra a instagram por favor")
_CORTESIA = re.compile(r"\b(por\s*favor|porfa|porfis|please|gracias|dale|che|ahora|ya|"
                       r"si\s*podes|te\s*lo\s*pido|un\s*segundo|un\s*toque)\b")
# palabras que NO son un sitio (frases cortadas: "pueden entrar en")
_NO_SITIO = {"", "en", "a", "el", "la", "los", "las", "un", "una", "al", "ahi", "aca",
             "eso", "esto", "algo", "ese", "esa", "internet", "la web", "web", "pagina"}


def _limpiar_sitio(sitio):
    """Saca cortesia/puntuacion y convierte 'punto com' hablado en '.com'."""
    s = _norm(str(sitio))
    s = _CORTESIA.sub(" ", s)
    s = re.sub(r"\s*punto\s*(com|net|org|ar|com\.ar)\b", r".\1", s)   # "dolarhoy punto com"
    s = re.sub(r"[¿?¡!,.;:]+$", "", s.strip())                        # puntuacion final
    return re.sub(r"\s+", " ", s).strip()


def _url_de(sitio):
    """Convierte un pedido ('youtube', 'wikipedia', 'tal.com') en una URL."""
    s = _limpiar_sitio(sitio)
    for k, v in SITIOS.items():
        if k in s:
            return "https://" + v
    if s.startswith("http"):
        return s
    if "." in s and " " not in s:            # parece dominio
        return "https://" + s
    return "https://" + s.replace(" ", "") + ".com"   # una palabra -> .com


def _abrir_web(sitio):
    limpio = _limpiar_sitio(sitio)
    if limpio in _NO_SITIO or len(limpio) < 3:      # frase cortada: no inventar un .com
        return "No entendi a donde queres entrar."
    url = _url_de(sitio)
    nav = None
    try:
        from app.web import navegador
        nav = navegador if navegador.esta_disponible() else None
    except Exception as e:
        print("navegador no disponible:", e, flush=True)
    if nav is not None:
        try:
            nav.abrir(url)
        except Exception as e:                       # la pestania ya se abrio; NO abrir otro browser
            print("abrir en Chrome IA fallo:", e, flush=True)
            return f"Abri {limpio}, pero puede que no haya cargado bien."
        return f"Abriendo {limpio} en el navegador."
    subprocess.Popen(f'start "" "{url}"', shell=True, creationflags=SIN_VENTANA)   # fallback: navegador por defecto
    return f"Abriendo {limpio}."


def t_web_abrir(sitio):
    return _abrir_web(sitio)


def t_web_clic(texto):
    try:
        from app.web import navegador
        navegador.clic(str(texto))
        return f"Clic en {texto}."
    except Exception:
        return f"No encontre {texto} en la pagina."


def t_web_escribir(texto):
    try:
        from app.web import navegador
        navegador.escribir(str(texto))
        return "Escrito."
    except Exception:
        return "No pude escribir."


def t_web_navegar(accion):
    try:
        from app.web import navegador
        navegador.navegar(str(accion))
        return "Listo."
    except Exception:
        return "No pude."


def t_web_cerrar_pestanas(_=None):
    try:
        from app.web import navegador
        n = navegador.cerrar_pestanas()
        return f"Cerre {n} pestañas." if n else "No habia pestañas para cerrar."
    except Exception:
        return "No pude cerrar las pestañas."


def t_web_cerrar_pestana(_=None):
    try:
        from app.web import navegador
        navegador.cerrar_pestana_actual()
        return "Cerre la pestaña."
    except Exception:
        return "No pude cerrar la pestaña."


# Esquema de herramientas (formato OpenAI/Ollama) que ve el LLM
TOOLS = [
    {"type": "function", "function": {"name": "escritorio",
        "description": "Cambiar a un escritorio virtual por su numero",
        "parameters": {"type": "object", "properties": {
            "numero": {"type": "integer", "description": "numero de escritorio, 1 a N"}},
            "required": ["numero"]}}},
    {"type": "function", "function": {"name": "abrir",
        "description": "Abrir una aplicacion o programa",
        "parameters": {"type": "object", "properties": {
            "app": {"type": "string", "description": "nombre: chrome, code, spotify, calculadora, explorador, whatsapp..."}},
            "required": ["app"]}}},
    {"type": "function", "function": {"name": "cerrar",
        "description": "Cerrar una aplicacion que este abierta",
        "parameters": {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]}}},
    {"type": "function", "function": {"name": "volumen",
        "description": "Controlar el volumen del sistema",
        "parameters": {"type": "object", "properties": {
            "accion": {"type": "string", "description": "subir, bajar o silenciar"}}, "required": ["accion"]}}},
    {"type": "function", "function": {"name": "media",
        "description": "Controlar reproduccion de musica o video",
        "parameters": {"type": "object", "properties": {
            "accion": {"type": "string", "description": "pausa, siguiente o anterior"}}, "required": ["accion"]}}},
    {"type": "function", "function": {"name": "hora",
        "description": "Decir la hora actual", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "bloquear",
        "description": "Bloquear la computadora", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "captura",
        "description": "Sacar una captura de pantalla", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "buscar_web",
        "description": "Buscar algo en Google en el navegador",
        "parameters": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]}}},
    {"type": "function", "function": {"name": "mirar_pantalla",
        "description": "Mirar la pantalla del usuario para leer, describir o responder sobre lo que se ve "
                       "(un error, un texto, una ventana, que hay abierto, etc.). Usar cuando el usuario "
                       "diga 'esto', 'aca', 'la pantalla', 'lo que estoy viendo', o pregunte por algo visible.",
        "parameters": {"type": "object", "properties": {
            "pregunta": {"type": "string", "description": "que quiere saber el usuario sobre la pantalla"},
            "monitor": {"type": "integer", "description": "opcional: numero de monitor (1, 2, 3). Si el usuario no lo aclara, omitir y se usa el del cursor."}},
            "required": ["pregunta"]}}},
    {"type": "function", "function": {"name": "web_abrir",
        "description": "Abrir una pagina web en el navegador del asistente (Chrome IA). Ej: gmail, youtube, kommo, o una URL.",
        "parameters": {"type": "object", "properties": {"sitio": {"type": "string"}}, "required": ["sitio"]}}},
    {"type": "function", "function": {"name": "web_clic",
        "description": "Hacer clic en un boton o link de la pagina web abierta, por su texto.",
        "parameters": {"type": "object", "properties": {"texto": {"type": "string", "description": "el texto del boton/link a clickear"}}, "required": ["texto"]}}},
    {"type": "function", "function": {"name": "web_escribir",
        "description": "Escribir texto en el campo enfocado de la pagina web.",
        "parameters": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}}},
    {"type": "function", "function": {"name": "web_navegar",
        "description": "Navegar en la pagina: atras, adelante, recargar, scrollear arriba/abajo.",
        "parameters": {"type": "object", "properties": {"accion": {"type": "string", "description": "atras, adelante, recargar, arriba o abajo"}}, "required": ["accion"]}}},
    {"type": "function", "function": {"name": "web_leer",
        "description": "Leer o resumir el contenido de la pagina web abierta en el navegador (Chrome IA).",
        "parameters": {"type": "object", "properties": {"pregunta": {"type": "string", "description": "que quiere saber de la pagina; vacio = resumen"}}}}},
    {"type": "function", "function": {"name": "web_cerrar_pestanas",
        "description": "Cerrar TODAS las pestañas del navegador (deja una en blanco).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "web_cerrar_pestana",
        "description": "Cerrar solo la pestaña actual del navegador.",
        "parameters": {"type": "object", "properties": {}}}},
]

DISPATCH = {
    "escritorio": lambda a: t_escritorio(a.get("numero")),
    "abrir":      lambda a: t_abrir(a.get("app", "")),
    "cerrar":     lambda a: t_cerrar(a.get("app", "")),
    "volumen":    lambda a: t_volumen(a.get("accion", "")),
    "media":      lambda a: t_media(a.get("accion", "")),
    "hora":       lambda a: t_hora(),
    "bloquear":   lambda a: t_bloquear(),
    "captura":    lambda a: t_captura(),
    "buscar_web": lambda a: t_buscar_web(a.get("consulta", "")),
    "web_abrir":  lambda a: t_web_abrir(a.get("sitio", "")),
    "web_clic":   lambda a: t_web_clic(a.get("texto", "")),
    "web_escribir": lambda a: t_web_escribir(a.get("texto", "")),
    "web_navegar": lambda a: t_web_navegar(a.get("accion", "")),
    "web_cerrar_pestanas": lambda a: t_web_cerrar_pestanas(),
    "web_cerrar_pestana": lambda a: t_web_cerrar_pestana(),
    # web_leer lo maneja cerebro.agente (resume con LLM), no va por aca
}
