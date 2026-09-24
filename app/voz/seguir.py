"""Seguir una sesion de Claude Code y sacarle las respuestas para leerlas en voz alta.

La idea completa: todo lo que escribe cualquier Claude Code queda grabado EN VIVO en
un .jsonl (uno por sesion, en carpetas por proyecto). Este modulo mira ese archivo
como quien mira una cinta que avanza: cuando aparece una respuesta terminada, la
devuelve para que voz.py la diga con Piper. El Claude seguido ni se entera.

Quien elige QUE sesion seguir es el panel (selector proyecto -> sesion), que escribe
la eleccion en seguir_lectura.json. Una sola sesion a la vez: el parlante tiene un
solo dueno y lo elige el usuario. Eso resuelve el problema real de esta maquina, que
un martes a la madrugada tenia CINCO sesiones vivas en un mismo proyecto.

Como se detecta "respuesta terminada": el jsonl no trae un marcador de fin de turno
utilizable (stopReason viene vacio), asi que la regla es doble:
  - llego un mensaje nuevo DEL USUARIO -> lo anterior seguro termino, se lee;
  - el archivo quedo quieto QUIETUD_SEG -> lo acumulado se lee.
El costado conocido de la segunda regla: si un turno tiene una herramienta lenta en
el medio (un comando de 2 minutos), el texto previo a la herramienta se lee durante
la espera. En la practica es casi una funcion: te va contando lo que hace.
"""

import json
import re
import threading
import time
import unicodedata
from pathlib import Path

from app.rutas import CLAUDE_PROYECTOS, CLAUDE_REGISTRO

QUIETUD_SEG = 5.0         # archivo quieto este tiempo = la respuesta esta terminada
RECIENTES_HORAS = 48      # sesiones guardadas mas viejas que esto no se ofrecen
MAX_SESIONES = 10         # tope del listado por proyecto


def carpeta_de(cwd):
    """La carpeta de transcripciones de un proyecto: la ruta 'aplanada'.

    ⚠ Claude Code aplana la ruta cambiando por un guion TODO lo que no sea letra,
    numero o guion — no solo los dos puntos, las barras y los puntos. Acá se
    cambiaban solo esos cuatro, así que cualquier proyecto con un ESPACIO en la
    ruta (o con una tilde) apuntaba a una carpeta que no existe y la pantalla
    mostraba "0 conversaciones" teniendo las charlas ahí mismo: pasó con
    "Proyectos Personales" el 2026-08-17, y le pasa igual a cualquier carpeta con tilde.
    Ejemplos: "C:\\Proyectos Personales\\Mi-Landing" ->
    "C--Proyectos-Personales-Mi-Landing"; "…\\Next.js" -> "…-Next-js".
    """
    plano = re.sub(r"[^A-Za-z0-9-]", "-", str(cwd))
    return CLAUDE_PROYECTOS / plano


# ⚠ Los pids de los procesos que el PANEL deja prendidos entre turnos (los de
# `sesiones_movil`, desde el 2026-08-20: viven para no matarle los comandos en segundo
# plano a la sesion). Sin esta lista, una charla del panel quedaria pintada como
# "trabajando" para siempre — el proceso existe, pero entre turnos no esta haciendo
# nada. Lo llena y lo vacia `sesiones_movil`.
PIDS_PANEL = set()


def _es_del_panel(pid):
    """Si ese pid es (o cuelga de) un proceso que dejamos prendido nosotros.

    ⚠ Se mira la cadena de padres porque en Windows `claude` es un .cmd: nosotros nos
    quedamos con el pid del .cmd y el que se anota en el registro de Claude Code es el
    del node hijo. Comparando solo el pid de arriba, este filtro no atrapaba ninguno.
    """
    import psutil
    if pid in PIDS_PANEL:
        return True
    try:
        proc = psutil.Process(pid)
        for _ in range(3):
            proc = proc.parent()
            if proc is None:
                return False
            if proc.pid in PIDS_PANEL:
                return True
    except Exception:
        pass
    return False


# --- La foto de quien esta vivo, UNA sola vez por barrido ------------------------
# ⚠⚠ Por que existe (2026-09-03). `sesiones_de()` llama a `_vivas()` sin cache, y
# `sesiones_movil.listar()` llama a `sesiones_de()` UNA VEZ POR PROYECTO: con 32 carpetas
# eso son 32 recorridas del registro, todas devolviendo lo mismo. Y no cuesta igual en
# todos lados: si `PIDS_PANEL` esta vacio —como en cualquier prueba suelta— el camino caro
# ni se ejecuta, asi que el problema SOLO aparece con el panel vivo y una prueba de
# escritorio no lo puede ver. Medido con el panel corriendo y 15 sesiones abiertas:
# `/movil/sesiones` volvia a tardar 7-13 s mientras `/status` seguia en 0,07 s.
# ⭐ Es el mismo patron que ya se usa en `panel._barrer` y en `sesiones_movil._codex_procs`:
# una foto corta, compartida, con candado — los endpoints sincronos de FastAPI corren en
# hilos distintos y sin el candado los 32 barren igual que antes.
_VIVAS_FOTO = {"ts": 0.0, "datos": {}}
_VIVAS_SEG = 1.5
_vivas_lock = threading.Lock()


def _vivas():
    """Sesiones registradas cuyo proceso sigue vivo: {sessionId: nombre}."""
    with _vivas_lock:
        if time.time() - _VIVAS_FOTO["ts"] < _VIVAS_SEG:
            return _VIVAS_FOTO["datos"]
    datos = _vivas_de_verdad()
    with _vivas_lock:
        _VIVAS_FOTO["datos"] = datos
        _VIVAS_FOTO["ts"] = time.time()
    return datos


def olvidar_vivas():
    """Tira la foto: la usa quien acaba de prender o apagar una sesion y no puede
    esperar hasta 1,5 s para que la pantalla lo refleje."""
    with _vivas_lock:
        _VIVAS_FOTO["ts"] = 0.0


def _vivas_de_verdad():
    import psutil
    resultado = {}
    if not CLAUDE_REGISTRO.is_dir():
        return resultado
    for p in CLAUDE_REGISTRO.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        sid, pid = d.get("sessionId"), d.get("pid")
        if not sid or not pid:
            continue
        try:
            if PIDS_PANEL and _es_del_panel(int(pid)):
                continue          # es un proceso nuestro esperando el proximo mensaje
            if not psutil.pid_exists(int(pid)):
                continue
            # ⚠ VIVA e INTERACTIVA no son lo mismo, y confundirlas costo dos
            # vueltas (2026-08-17). Viva = hay un proceso corriendo para esa
            # sesion, y eso incluye los turnos que lanza el propio panel, que
            # duran lo que tarda la respuesta: eso es lo que se pinta en verde
            # como "trabajando". Interactiva = una ventana de Claude Code abierta
            # de verdad (sin `-p`), que es el unico caso donde escribirle desde
            # aca bifurca la conversacion y hay que bloquear la caja.
            interactiva = True
            try:
                linea = " ".join(psutil.Process(int(pid)).cmdline())
                interactiva = " -p " not in f" {linea} " and not linea.rstrip().endswith(" -p")
            except Exception:
                pass
            resultado[sid] = {"nombre": d.get("name") or sid[:8],
                              "cwd": d.get("cwd") or "",
                              "interactiva": interactiva}
        except Exception:
            continue
    return resultado


def proyectos():
    """Proyectos con sesiones vivas: [{cwd, nombre, vivas}]. El nombre es la ultima
    parte de la ruta ('wpp-transcriptor'), que es como se lo nombra hablando."""
    grupos = {}
    for datos in _vivas().values():
        cwd = datos["cwd"]
        if not cwd:
            continue
        clave = str(carpeta_de(cwd)).lower()      # d:\ y D:\ son la misma carpeta
        g = grupos.setdefault(clave, {"cwd": cwd, "nombre": Path(cwd).name, "vivas": 0})
        g["vivas"] += 1
    return sorted(grupos.values(), key=lambda g: -g["vivas"])


_titulos = {}                 # (ruta, mtime) -> titulo, para no releer archivos grandes


def _titulo_de(jsonl):
    """El titulo de la conversacion (el mismo que muestra la pestana de VS Code).

    Esta guardado ADENTRO del propio .jsonl, en lineas {"type":"ai-title"}. Cambia
    a lo largo de la charla (esta sesion lleva 223), asi que vale la ULTIMA. Se busca
    de atras para adelante por bloques: los archivos llegan a 8 MB y leerlos enteros
    para sacar un titulo seria pagar el asado para llevarse la servilleta.
    """
    ruta = Path(jsonl)
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        return None
    clave = (str(ruta), mtime)
    if clave in _titulos:
        return _titulos[clave]
    titulo = None
    try:
        with ruta.open("rb") as f:
            f.seek(0, 2)
            fin = f.tell()
            paso = 128 * 1024
            leido = b""
            while fin > 0 and len(leido) < 2 * 1024 * 1024:   # tope: 2 MB de busqueda
                inicio = max(0, fin - paso)
                f.seek(inicio)
                leido = f.read(fin - inicio) + leido
                fin = inicio
                if b'"ai-title"' in leido:
                    break
        for linea in reversed(leido.split(b"\n")):
            if b'"ai-title"' not in linea:
                continue
            try:
                d = json.loads(linea.decode("utf-8", errors="replace"))
                if d.get("type") == "ai-title" and d.get("aiTitle"):
                    titulo = d["aiTitle"].strip()
                    break
            except Exception:
                continue                  # la primera linea del bloque puede venir cortada
    except OSError:
        pass
    # ⚠⚠ El tope tiene que ser MAS GRANDE que la cantidad de conversaciones que hay en el
    # disco, o el cache no sirve para nada: estaba en 200 con 215 archivos, asi que se
    # vaciaba entero en cada recorrida y los titulos se volvian a leer SIEMPRE — 0,12 s de
    # los 0,18 s que tardaba `listar()`, en cada pedido de la pantalla de sesiones
    # (2026-08-18). Cada entrada es una ruta y un titulo: 2000 no son nada de memoria.
    if len(_titulos) > 2000:
        _titulos.clear()
    _titulos[clave] = titulo
    return titulo


def _hace(segundos):
    """'hace 2 min' / 'hace 3 h', para el selector del panel."""
    if segundos < 90:
        return "hace un momento"
    if segundos < 3600:
        return f"hace {segundos / 60:.0f} min"
    if segundos < 86400:
        return f"hace {segundos / 3600:.0f} h"
    return f"hace {segundos / 86400:.0f} dias"


def sesiones_de(cwd, horas=RECIENTES_HORAS):
    """Las sesiones de un proyecto, vivas primero, con nombre amigable si lo tienen.

    Devuelve [{id, nombre, viva, detalle, jsonl}]. Salen del propio disco (los .jsonl
    del proyecto) cruzados con el registro de vivas para ponerles nombre.

    `horas` es cuanto para atras se mira. Por voz alcanza con las ultimas 48 (es para
    "segui leyendo lo de recien"), pero la lista del CELULAR necesita mucho mas: ahi
    uno entra a buscar el proyecto de la semana pasada.
    """
    carpeta = carpeta_de(cwd)
    if not carpeta.is_dir():
        return []
    vivas = _vivas()
    ahora = time.time()
    filas = []
    for p in carpeta.glob("*.jsonl"):
        try:
            edad = ahora - p.stat().st_mtime
        except OSError:
            continue
        if edad > horas * 3600:
            continue
        sid = p.stem
        viva = sid in vivas
        # El nombre visible es el TITULO de la conversacion (el de la pestana de
        # VS Code), que vive adentro del propio archivo. El nombre tecnico del
        # registro (wpp-transcriptor-a5) queda de respaldo para las vivas sin titulo.
        titulo = _titulo_de(p)
        if viva:
            nombre = titulo or vivas[sid]["nombre"]
        else:
            nombre = titulo or sid[:8]
        filas.append({
            "id": sid,
            "nombre": nombre,
            "viva": viva,
            "interactiva": bool(viva and vivas[sid].get("interactiva")),
            "detalle": ("activa, " if viva else "guardada, ") + _hace(edad),
            "jsonl": str(p),
            # la fecha cruda, para poder ordenar y filtrar del lado de la pantalla
            "ts": p.stat().st_mtime,
            "_edad": edad,
        })
    filas.sort(key=lambda f: (not f["viva"], f["_edad"]))
    for f in filas:
        f.pop("_edad")
    return filas[:MAX_SESIONES]


def vivas_con_titulo():
    """Todas las sesiones VIVAS de todos los proyectos, con su titulo legible.

    Para el dictado por voz ("escribi en la sesion del disco"): ahi no hay selector,
    hay que encontrar la sesion por como suena su nombre.
    """
    filas = []
    for sid, datos in _vivas().items():
        cwd = datos["cwd"]
        if not cwd:
            continue
        jsonl = carpeta_de(cwd) / f"{sid}.jsonl"
        titulo = _titulo_de(jsonl) if jsonl.exists() else None
        filas.append({"id": sid, "cwd": cwd, "jsonl": str(jsonl),
                      "nombre": titulo or datos["nombre"],
                      "proyecto": Path(cwd).name})
    return filas


def _palabras(texto):
    """Palabras 'planas' (minusculas, sin acentos) y sin las de relleno."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    relleno = {"la", "el", "los", "las", "de", "del", "en", "a", "y", "que", "con",
               "un", "una", "mi", "sesion", "session", "conversacion", "charla"}
    return {p for p in t.replace("-", " ").split() if len(p) > 1 and p not in relleno}


def buscar_sesion(frase, candidatas=None):
    """La sesion viva cuyo titulo mas se parece a la frase dicha, o None.

    Se compara por palabras significativas: "la sesion del disco" tiene que
    encontrar "Investigar y clasificar ocupacion de disco C urgente". Empate o
    cero coincidencias = None: mejor decir "no se cual" que escribir en la equivocada.
    """
    objetivo = _palabras(frase)
    if not objetivo:
        return None

    def coincide(palabra, conjunto):
        # Igualdad, o prefijo con piso de 4 letras: "tienda" tiene que encontrar
        # "Tienda2" (el numero viene pegado al nombre). El piso evita que "el",
        # "de" o "com" enganchen media lista.
        if palabra in conjunto:
            return True
        return len(palabra) >= 4 and any(
            len(c) >= 4 and (c.startswith(palabra) or palabra.startswith(c))
            for c in conjunto)

    puntuadas = []
    for s in (candidatas if candidatas is not None else vivas_con_titulo()):
        palabras = _palabras(s["nombre"] + " " + s.get("proyecto", ""))
        puntos = sum(1 for p in objetivo if coincide(p, palabras))
        if puntos:
            puntuadas.append((puntos, s))
    if not puntuadas:
        return None
    puntuadas.sort(key=lambda x: -x[0])
    if len(puntuadas) > 1 and puntuadas[0][0] == puntuadas[1][0]:
        return None                      # empate: no adivinar, que el usuario aclare
    return puntuadas[0][1]


def _texto_de(linea):
    """El texto hablable de una linea del jsonl, o None si no aporta.

    Se queda SOLO con los bloques de texto de los mensajes del asistente. Afuera:
    herramientas (tool_use), pensamiento interno (thinking), sub-agentes (isSidechain,
    que son conversaciones internas, no respuestas al usuario) y mensajes sinteticos.
    """
    try:
        d = json.loads(linea)
    except Exception:
        return None
    if d.get("type") != "assistant" or d.get("isSidechain"):
        return None
    msg = d.get("message") or {}
    if (msg.get("model") or "") == "<synthetic>":
        return None
    contenido = msg.get("content")
    if isinstance(contenido, str):
        return contenido.strip() or None
    if isinstance(contenido, list):
        partes = [b.get("text", "") for b in contenido
                  if isinstance(b, dict) and b.get("type") == "text"]
        texto = "\n".join(p for p in partes if p.strip()).strip()
        return texto or None
    return None


def _es_turno_usuario(linea):
    """True si la linea es un mensaje del usuario de la conversacion principal."""
    try:
        d = json.loads(linea)
    except Exception:
        return False
    if (d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta")
            or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly")):
        return False
    # Claude Code guarda el resumen automático al quedarse sin contexto como `user`,
    # aunque no lo escribió Martín. Las dos banderas de arriba lo distinguen: en 557
    # historiales reales aparecieron juntas 84 veces y siempre fueron estos resúmenes.
    # Los resultados de herramientas tambien llegan como type=user: no son el usuario.
    contenido = (d.get("message") or {}).get("content")
    if isinstance(contenido, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in contenido)
    return isinstance(contenido, str)


class Seguidor:
    """Cola de lectura sobre un .jsonl: entrega las respuestas a medida que terminan.

    Arranca desde el FINAL del archivo a proposito: seguir una sesion no es que te
    lea todo lo que ya paso, es que te lea lo que diga de ahora en adelante.
    """

    def __init__(self, jsonl):
        self.ruta = Path(jsonl)
        try:
            self._pos = self.ruta.stat().st_size
        except OSError:
            self._pos = 0
        self._resto = b""                # cola de una linea que llego incompleta
        self._partes = []                # texto del turno en curso
        self._ultima_linea = None        # cuando llego la ultima linea NUEVA

    def _lineas_nuevas(self):
        try:
            tam = self.ruta.stat().st_size
        except OSError:
            return []
        if tam < self._pos:              # el archivo se trunco/roto: arrancar de nuevo
            self._pos = 0
            self._resto = b""
        if tam == self._pos:
            return []
        with self.ruta.open("rb") as f:
            f.seek(self._pos)
            datos = f.read()
            self._pos = f.tell()
        crudo = self._resto + datos
        lineas = crudo.split(b"\n")
        self._resto = lineas[-1]         # lo que no termino en \n queda para despues
        return [l.decode("utf-8", errors="replace") for l in lineas[:-1] if l.strip()]

    def _cerrar_turno(self):
        texto = "\n".join(self._partes).strip()
        self._partes = []
        return texto or None

    def novedades(self):
        """Respuestas terminadas desde la ultima llamada. Llamar cada ~1 s."""
        listas = []
        for linea in self._lineas_nuevas():
            self._ultima_linea = time.time()
            if self._partes and _es_turno_usuario(linea):
                t = self._cerrar_turno()    # hablo el usuario: lo anterior termino
                if t:
                    listas.append(t)
            texto = _texto_de(linea)
            if texto:
                self._partes.append(texto)
        if (self._partes and self._ultima_linea
                and time.time() - self._ultima_linea > QUIETUD_SEG):
            t = self._cerrar_turno()        # archivo quieto: la respuesta esta completa
            if t:
                listas.append(t)
        return listas
