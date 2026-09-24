"""
Puente al Codex CLI (OpenAI) para el asistente de voz: el OTRO cerebro de Laura.

Es el gemelo de `claude_voz.py`. Misma cara hacia afuera (preguntar, cancelar,
olvidar, compactar, esperando_dia, responder_dia, resumen_de...) para que quien la
usa —`voz.py`, el chat del panel, Telegram— no tenga que saber con cual esta
hablando. El que elige es `app/voz/cerebro.py`.

DIFERENCIAS con el de Claude, que explican por que este archivo no es una copia:

  * No hay proceso persistente. `codex exec` es de un solo turno: se le pasa la
    consulta, contesta y se muere. Para seguir la charla se reanuda por id
    (`codex exec resume <id>`), que es justo lo que hacemos. Arranca en ~1 s, asi
    que no vale la pena el protocolo por stdin que si le hace falta a Claude.
  * No existe `--append-system-prompt`. Las reglas largas de Laura se le mandan
    pegadas al PRIMER mensaje de cada sesion; la capa corta que debe valer en cada
    turno va escondida como `developer_instructions`.
  * Cancelar SI mata el proceso, al reves que en Claude: como cada turno es su
    propio proceso, matarlo no deja nada colgado en la sesion.
  * Los permisos no son una lista de herramientas sino un "sandbox": en modo
    lectura va `read-only`, y en modo completo `workspace-write` mas las carpetas
    de `CARPETAS` sumadas con `--add-dir`.

La sesion se guarda en `codex_sesion.json`, aparte de la de Claude: los ids no son
intercambiables, y ademas asi cada cerebro tiene su propia memoria de la charla.
"""

import os
import json
import time
import shutil
import psutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from app.rutas import (CODEX_SESION, CODEX_SESIONES, AJUSTES_SESIONES,
                       CERT_NODE_CODEX, CERT_BUNDLE_CODEX)
from app.voz import claude_voz as _cl
from app.voz.prompt_master_auto import argumento_codex

# Lo que es identico en los dos cerebros se importa, no se copia: si Martin cambia
# el estilo de Laura o el "dia" que arranca a las 13:00, cambia para los dos.
CWD = _cl.CWD
MODO = _cl.MODO
CARPETAS = _cl.CARPETAS
CORTE_HORA = _cl.CORTE_HORA
GRACIA_CORTE = _cl.GRACIA_CORTE
SALUDO_DIA = _cl.SALUDO_DIA
PROMPT_RESUMEN = _cl.PROMPT_RESUMEN
RESUMEN_LARGO_MAX = _cl.RESUMEN_LARGO_MAX
SYSTEM = _cl.SYSTEM
_plano = _cl._plano
_limpiar = _cl._limpiar
pide_sesion_nueva = _cl.pide_sesion_nueva

# Catalogo del Codex instalado en esta maquina, releido el 2026-09-12 contra el CLI
# 0.153.4. Va explicitamente en cada turno para que lo elegido en el panel no dependa
# de un cambio posterior en ~/.codex/config.toml.
# ⚠ Esta lista ENVEJECE: es una copia a mano de lo que el CLI publica. Cuando OpenAI
# saca un modelo, aca no aparece hasta que alguien lo agrega — y al reves, un modelo
# retirado sigue en la perilla y falla recien al mandar el turno (asi se fueron `gpt-5.4`
# y `gpt-5.4-mini`, que ya no estan en el catalogo). Antes de tocarla, correr
# `codex debug models` y copiar de ahi los `slug`, los `supported_reasoning_levels` y
# los `additional_speed_tiers`.
# ⭐ El CLI deja ese catalogo cacheado en `~/.codex/models_cache.json` (con `fetched_at`,
# `client_version` y un `visibility` que dice cuales se listan): de ahi salieron estos
# datos sin correr el CLI.
# ⚠⚠ PERO ese cache NO es lo que el CLI local puede USAR: es lo que el servidor publica
# para todos. El 2026-09-12 traia `gpt-6-astra` con el CLI instalado en 0.148.0, y el turno
# murio con un 400: "The 'gpt-6-astra' model requires a newer version of Codex". O sea que
# un modelo listado ahi puede exigir una version mas nueva y el cache no lo dice. Si algun
# dia se lee de ese archivo en vez de a mano, esto hay que resolverlo igual.
MODELO = "gpt-5.6-terra"
MODELOS = {
    "gpt-5.6-terra":       "GPT-5.6 Terra",
    "gpt-6-astra":         "GPT-6 Astra",
    "gpt-5.6-sol":         "GPT-5.6 Sol",
    "gpt-5.6-luna":        "GPT-5.6 Luna",
    "gpt-5.5":             "GPT-5.5",
    "gpt-5.3-codex-spark": "GPT-5.3 Codex Spark",
}
_ESFUERZOS_POR_MODELO = {
    "gpt-6-astra":         ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-sol":         ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-terra":       ("low", "medium", "high", "xhigh", "max", "ultra"),
    "gpt-5.6-luna":        ("low", "medium", "high", "xhigh", "max"),
    "gpt-5.5":             ("low", "medium", "high", "xhigh"),
    "gpt-5.3-codex-spark": ("low", "medium", "high", "xhigh"),
}
# Los que no publican tier rapido (`additional_speed_tiers` vacio en el catalogo).
_SIN_VELOCIDAD_RAPIDA = ("gpt-5.3-codex-spark",)
_NOMBRES_ESFUERZO = {
    "":       "Esfuerzo de fábrica",
    "low":    "Esfuerzo bajo",
    "medium": "Esfuerzo medio",
    "high":   "Esfuerzo alto",
    "xhigh":  "Esfuerzo muy alto",
    "max":    "Esfuerzo máximo",
    "ultra":  "Esfuerzo ultra",
}
VELOCIDADES = {
    "":         "Velocidad estándar",
    "priority": "Velocidad rápida",
}
TIMEOUT = 600            # sin NINGUNA señal por este rato = colgado; mientras mande eventos puede trabajar lo que quiera
SIN_SENAL_SEG = 120      # si no manda ni un evento en este rato, no piensa: esta muerto

_SESION_FILE = CODEX_SESION

_SESION = None            # thread_id de Codex -> la charla sigue
_DIA = None
_HISTORIAL = []
_ultimo_turno = 0.0

_CANCELADO = False
_en_vuelo = None          # el Popen del turno que esta corriendo AHORA (para cancelar)
_esperando_dia = False
_pendiente = None
_turnos = 0

_lock_turno = threading.RLock()   # un turno por vez, igual que en el otro cerebro


def _dia_de(ts=None):
    """A que 'dia de Laura' pertenece un momento (el dia arranca a las 13:00)."""
    t = datetime.fromtimestamp(ts if ts else time.time())
    if t.hour < CORTE_HORA:
        t -= timedelta(days=1)
    return t.strftime("%Y-%m-%d")


def _cargar_sesion():
    global _SESION, _DIA, _HISTORIAL, _ultimo_turno
    try:
        d = json.loads(_SESION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    act = d.get("actual") or {}
    _HISTORIAL = d.get("historial") or []
    _SESION = act.get("session_id")
    _DIA = act.get("dia")
    _ultimo_turno = float(act.get("ts") or 0)
    if _SESION:
        print(f"codex: sesion guardada {_SESION[:8]} del dia {_DIA} "
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
        print("codex: no pude guardar la sesion:", e, flush=True)


def sesion_anterior():
    """La sesion mas reciente de un dia distinto al de hoy. None si no hay."""
    hoy = _dia_de()
    if _SESION and _DIA and _DIA != hoy:
        return {"session_id": _SESION, "dia": _DIA, "ts": _ultimo_turno}
    for s in _HISTORIAL:
        if s.get("dia") != hoy and s.get("session_id"):
            return s
    return None


def _archivo_de(session_id):
    """El .jsonl de una sesion de Codex. Se busca por id: la carpeta es la del dia."""
    try:
        for p in CODEX_SESIONES.rglob(f"*{session_id}.jsonl"):
            return p
    except Exception:
        pass
    return None


def _charla_de(session_id, max_chars=30000):
    """La conversacion de una sesion vieja en texto pelado, para poder resumirla.

    El rollout de Codex trae MUCHO mas que la charla (instrucciones internas,
    estado del mundo, llamadas a herramientas). Nos quedamos solo con los mensajes
    de usuario y de asistente, que es lo unico que Martin reconoce como "la charla".
    """
    p = _archivo_de(session_id)
    if not p:
        return ""
    partes = []
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            for linea in f:
                try:
                    d = json.loads(linea)
                except Exception:
                    continue
                if d.get("type") != "response_item":
                    continue
                pay = d.get("payload") or {}
                if pay.get("type") != "message":
                    continue
                rol = pay.get("role")
                if rol not in ("user", "assistant"):
                    continue           # 'developer' son las instrucciones, no la charla
                txt = " ".join(c.get("text", "") for c in (pay.get("content") or [])
                               if isinstance(c, dict) and c.get("text"))
                txt = txt.strip()
                if txt:
                    partes.append(("Yo: " if rol == "user" else "Vos: ") + txt)
    except Exception as e:
        print("codex: no pude leer la charla vieja:", e, flush=True)
        return ""
    charla = "\n".join(partes)
    return charla[-max_chars:] if len(charla) > max_chars else charla


def _archivar_actual():
    """Guarda la charla de hoy en el historial y deja lugar para una nueva."""
    global _SESION, _DIA, _turnos
    if _SESION:
        _HISTORIAL.insert(0, {"session_id": _SESION, "dia": _DIA or _dia_de(),
                              "ts": _ultimo_turno})
    _SESION = None
    _DIA = _dia_de()
    _turnos = 0


_cargar_sesion()


# --- El cupo: cuanto del limite de la cuenta lleva gastado Codex ------------------
# Codex anota en cada turno, adentro del rollout de la sesion, cuanto del limite de
# la cuenta lleva usado (`rate_limits`). Leerlo de ahi es gratis: no hay que
# preguntarle nada a OpenAI. Lo usa `cerebro_grande` para pasarse solo a Claude
# ANTES de chocar el limite, en vez de enterarse recien cuando Codex deja de contestar.
CUPO_CACHE_SEG = 60      # el cupo se mueve despacio: releer el disco en cada turno es al pedo
_cupo_cache = (0.0, None)


def cupo():
    """Cuanto cupo lleva gastado la cuenta de Codex. None si no hay de donde leerlo.

    Devuelve {"usado": porcentaje 0-100, "resets_at": epoch o None}. El dato es de
    la CUENTA, no de la charla: sirve el rollout mas nuevo que haya, aunque sea de
    una sesion usada a mano en la terminal.
    """
    global _cupo_cache
    ahora = time.time()
    if ahora - _cupo_cache[0] < CUPO_CACHE_SEG:
        return _cupo_cache[1]
    dato = None
    try:
        rollouts = sorted(CODEX_SESIONES.rglob("rollout-*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        # Si el mas nuevo recien empieza y todavia no anoto nada, probar el anterior.
        for p in rollouts[:3]:
            dato = _cupo_de(p)
            if dato:
                break
    except Exception as e:
        print("codex: no pude leer el cupo:", e, flush=True)
    _cupo_cache = (ahora, dato)
    return dato


def _cupo_de(p):
    """El ultimo `rate_limits` de un rollout, leyendo solo la cola del archivo."""
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            cola = f.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    for linea in reversed(cola.splitlines()):
        if '"rate_limits"' not in linea:
            continue
        try:
            rl = (json.loads(linea).get("payload") or {}).get("rate_limits") or {}
        except Exception:
            continue        # una linea cortada por la lectura de la cola, o basura
        # Hay dos ventanas (la de horas y la de semanas): manda la mas llena.
        usados = [v.get("used_percent") for v in (rl.get("primary"), rl.get("secondary"))
                  if isinstance(v, dict) and v.get("used_percent") is not None]
        if not usados:
            continue
        return {"usado": max(usados),
                "resets_at": (rl.get("primary") or {}).get("resets_at")}
    return None


def _codex_bin():
    return shutil.which("codex") or shutil.which("codex.cmd") or "codex"


def _memoria_indice():
    """El indice de la memoria de Laura, para pegarlo al primer mensaje.

    El CLI de Claude carga MEMORY.md solo al arrancar; Codex no tiene nada asi, de
    modo que se lo damos igual que las reglas. Solo el indice (una linea por
    recuerdo): el detalle esta en los archivos de esa carpeta y ya sabe leerlos.
    """
    try:
        texto = (Path(_cl.MEMORIA_DIR) / "MEMORY.md").read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if not texto:
        return ""
    return ("\n\nTU MEMORIA GUARDADA (el indice; cada recuerdo es un archivo en esa "
            "misma carpeta que podes abrir si necesitas el detalle):\n" + texto)


def modelo_actual():
    """El modelo elegido para el Codex de Laura."""
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        m = (d.get("laura_codex") or {}).get("modelo")
        if m in MODELOS:
            return m
    except Exception:
        pass
    return MODELO


def esfuerzos_del_modelo(modelo=None):
    """Opciones que el catalogo local declara para ese modelo."""
    modelo = modelo if modelo in MODELOS else modelo_actual()
    ids = ("",) + _ESFUERZOS_POR_MODELO[modelo]
    return {k: _NOMBRES_ESFUERZO[k] for k in ids}


# Compatibilidad con las pantallas/pruebas anteriores: el catalogo completo. Para
# pintar una perilla se usa `esfuerzos_del_modelo`, que elimina los no soportados.
ESFUERZOS = _NOMBRES_ESFUERZO


def _guardar_ajuste(campo, valor):
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    d.setdefault("laura_codex", {})[campo] = valor
    try:
        AJUSTES_SESIONES.write_text(json.dumps(d, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    except Exception as e:
        print(f"codex: no pude guardar {campo}:", e, flush=True)
    return valor


def poner_modelo(modelo):
    """Guarda el modelo de Laura y limpia perillas incompatibles."""
    modelo = modelo if modelo in MODELOS else MODELO
    _guardar_ajuste("modelo", modelo)
    try:
        ajuste = (json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
                  .get("laura_codex") or {})
    except Exception:
        ajuste = {}
    if (ajuste.get("esfuerzo") or "") not in esfuerzos_del_modelo(modelo):
        _guardar_ajuste("esfuerzo", "")
    if (ajuste.get("velocidad") or "") not in velocidades_del_modelo(modelo):
        _guardar_ajuste("velocidad", "")
    return modelo


def esfuerzo_actual():
    """Cuanto piensa antes de contestar (`-c model_reasoning_effort`). Vacio = fabrica."""
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        e = (d.get("laura_codex") or {}).get("esfuerzo")
        if e and e in esfuerzos_del_modelo():
            return e
    except Exception:
        pass
    return ""


def poner_esfuerzo(esfuerzo):
    """Guarda el esfuerzo del Codex de Laura. Devuelve el que quedo puesto.

    Va bajo la llave "laura_codex" del mismo archivo de ajustes que usan las
    sesiones y el Claude de Laura ("laura"): una perilla por cerebro, sin pisarse.
    """
    if esfuerzo not in esfuerzos_del_modelo():
        esfuerzo = ""
    return _guardar_ajuste("esfuerzo", esfuerzo)


def velocidades_del_modelo(modelo=None):
    """Spark no publica tier rápido; el resto del catálogo sí."""
    modelo = modelo if modelo in MODELOS else modelo_actual()
    return ({"": VELOCIDADES[""]} if modelo in _SIN_VELOCIDAD_RAPIDA else VELOCIDADES)


def velocidad_actual():
    try:
        d = json.loads(AJUSTES_SESIONES.read_text(encoding="utf-8"))
        v = (d.get("laura_codex") or {}).get("velocidad") or ""
        if v in velocidades_del_modelo():
            return v
    except Exception:
        pass
    return ""


def poner_velocidad(velocidad):
    if velocidad not in velocidades_del_modelo():
        velocidad = ""
    return _guardar_ajuste("velocidad", velocidad)


def _args_comunes():
    """Las banderas que van SIEMPRE, y antes del subcomando (`resume` no las acepta)."""
    args = ["exec", "--json", "--skip-git-repo-check", "-C", CWD]
    args += ["-c", argumento_codex()]
    m = modelo_actual()
    if m:
        args += ["-m", m]
    e = esfuerzo_actual()
    if e:
        args += ["-c", f"model_reasoning_effort={e}"]
    if velocidad_actual() == "priority":
        args += ["-c", 'service_tier="priority"']
    if MODO == "completo":
        # ⭐ 2026-08-20 (pedido de Martin: "quiero que Codex pueda hacer todo lo que
        # hacen mis sesiones de Claude"): acceso completo, igual que el cerebro de
        # Claude, que corre con `dontAsk` y por Bash no tiene jaula de disco.
        # Con `workspace-write` Codex solo escribia en la carpeta del proyecto y en
        # CARPETAS, asi que se le caian las tareas de siempre: el known_hosts del
        # SSH al VPS, la config global de git, y cualquier OTRO proyecto de
        # EspacioDeTrabajo. La red ya iba habilitada por lo mismo.
        # Las `--add-dir` quedan igual: no cuestan nada y siguen marcando el
        # espacio de trabajo aunque el sandbox no lo exija.
        args += ["--sandbox", "danger-full-access"]
        for d in CARPETAS:
            if os.path.isdir(d):
                args += ["--add-dir", d]
    else:
        args += ["--sandbox", "read-only"]
    return args


def precalentar():
    """No hace falta calentar nada: cada turno arranca su propio proceso (~1 s).

    Existe para que el gemelo tenga la misma cara que el de Claude, que si necesita
    levantar un proceso persistente antes de la primera consulta.
    """
    return


def _matar_arbol(p):
    """Mata el proceso y TODOS sus hijos. `codex` en Windows lanza node por debajo:
    matando solo al padre, el hijo sigue escribiendo la charla y el proximo turno
    choca con "already has an active writer" (paso el 2026-08-20)."""
    try:
        padre = psutil.Process(p.pid)
        for hijo in padre.children(recursive=True):
            try:
                hijo.kill()
            except Exception:
                pass
        padre.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


CANDADOS = Path.home() / ".codex" / "thread-writer-locks"


def _hay_escritor_vivo(sesion):
    """¿Quedo algun proceso de codex trabajando sobre esa charla?"""
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() not in ("codex.exe", "node.exe"):
                continue
            if sesion in " ".join(p.info["cmdline"] or []):
                return True
        except Exception:
            pass
    return False


def _soltar_candado(sesion):
    """Borra el candado que dejo un codex muerto sobre la charla.

    Codex marca cada charla con un archivo en `~/.codex/thread-writer-locks`
    mientras la esta escribiendo. Si el proceso se cae mal —el certificado que
    corto el turno el 2026-08-22— el archivo queda ahi y CUALQUIER reanudacion
    posterior rebota con "already has an active writer": la charla queda muerta
    para siempre y Laura se pasa a Claude. Solo se borra si de verdad no quedo
    ningun proceso escribiendo, para no pisarle la charla a uno vivo.
    """
    if not sesion or _hay_escritor_vivo(sesion):
        return False
    candado = CANDADOS / f"{sesion}.lock"
    try:
        if candado.exists():
            candado.unlink()
            print(f"codex: candado huerfano liberado ({sesion[:8]})", flush=True)
            return True
    except Exception as e:
        print("codex: no pude liberar el candado:", e, flush=True)
    return False


def cancelar():
    """Corta el turno en curso. Aca SI se mata el proceso: cada turno es uno propio."""
    global _CANCELADO
    p = _en_vuelo
    if p is not None and p.poll() is None:
        _CANCELADO = True
        _matar_arbol(p)
        print("codex: turno cortado", flush=True)


def olvidar():
    """Arranca una charla nueva. La que dejas NO se pierde: queda archivada."""
    global _esperando_dia, _pendiente
    _esperando_dia = False
    _pendiente = None
    _archivar_actual()
    _guardar_sesion()


def compactar():
    """Resume la charla de ahora y sigue en una sesion nueva sembrada con ese resumen."""
    global _esperando_dia, _pendiente
    if not _SESION:
        return "Esta charla recién empieza: no hay nada que compactar."
    from app.voz.sesiones_movil import PEDIDO_RESUMEN, SIEMBRA
    with _lock_turno:
        viejo = _SESION
        resumen = preguntar(PEDIDO_RESUMEN, crudo=True, para_voz=False)
        if not resumen or len(resumen) < 40:
            return "No pude resumir la charla, así que la dejé como estaba."
        _esperando_dia = False
        _pendiente = None
        _archivar_actual()
        _guardar_sesion()
        preguntar(SIEMBRA.format(resumen=resumen), crudo=True, para_voz=False)
        print(f"codex: compactada {viejo[:8]} -> {(_SESION or '-')[:8]}", flush=True)
    return "Listo, resumí lo que veníamos hablando y seguimos en una charla nueva."


def _turno(consulta):
    """Un turno contra `codex exec`. Devuelve (texto, error) — error None si salio bien.

    La consulta va por la ENTRADA ESTANDAR (el `-` del final) y no como argumento:
    un pedido de resumen lleva la charla de ayer adentro y pasa largo el limite de
    Windows para la linea de comandos.
    """
    global _SESION, _en_vuelo, _turnos
    cmd = [_codex_bin()] + _args_comunes()
    if _SESION:
        cmd += ["resume", _SESION, "-"]
    else:
        cmd += ["-"]
        # Sesion nueva: las reglas de Laura van pegadas al primer mensaje. Codex no
        # tiene una bandera para el system prompt; una vez adentro de la charla,
        # viajan solas en cada turno reanudado. El indice de la memoria va tambien:
        # a Claude se lo carga solo su CLI, pero Codex no sabe que existe, y sin
        # esto los dos cerebros recordaban distinto.
        consulta = SYSTEM + _memoria_indice() + "\n\n---\n\n" + consulta

    env = dict(os.environ)
    env.pop("SSLKEYLOGFILE", None)
    # ⭐ Avast inspecciona el HTTPS y Node no lee el almacen de certificados de
    # Windows: sin esto el turno se cae solo a mitad de camino ("websocket closed
    # by server", 2026-08-22) y Laura termina saltando a Claude. Las sesiones del
    # panel ya lo hacian; este cerebro se habia quedado afuera.
    if CERT_NODE_CODEX.exists():
        env["NODE_EXTRA_CA_CERTS"] = str(CERT_NODE_CODEX)
    # Y el certificado para la parte Rust del CLI, que es la que abre el stream.
    if CERT_BUNDLE_CODEX.exists():
        env["SSL_CERT_FILE"] = str(CERT_BUNDLE_CODEX)
        env["NODE_EXTRA_CA_CERTS"] = str(CERT_BUNDLE_CODEX)
    try:
        # ⚠ CREATE_NO_WINDOW, por lo mismo que en `claude_voz.py`: el CLI se lanza por un
        # .cmd desde un servicio sin consola, y sin la marca cada consulta abre una ventana
        # negra en la pantalla (2026-09-06). La salida sigue viniendo por los pipes.
        proc = subprocess.Popen(cmd, cwd=CWD, env=env, shell=False,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", bufsize=1,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return None, f"no pude arrancar codex: {e}"

    _en_vuelo = proc
    try:
        proc.stdin.write(consulta)
        proc.stdin.close()
    except Exception as e:
        return None, f"no pude escribirle a codex: {e}"

    texto = ""
    previa = _SESION
    # ⭐ El reloj corre desde la ULTIMA señal, no desde el arranque del turno (mismo
    # esquema que las sesiones del panel): un Codex que trabaja largo y va mandando
    # eventos no se corta nunca. El limite duro de 10 minutos lo mataba en plena
    # tarea (2026-08-20). Y vigila un hilo aparte porque el `for` de abajo se BLOQUEA
    # leyendo: si Codex se cuelga mudo, nadie llegaba a mirar el reloj.
    estado = {"latido": time.time(), "fin": False, "vencido": False}

    def _vigilar():
        while not estado["fin"] and proc.poll() is None:
            time.sleep(2)
            if time.time() - estado["latido"] > TIMEOUT:
                estado["vencido"] = True
                _matar_arbol(proc)
                return
    threading.Thread(target=_vigilar, daemon=True).start()

    try:
        for linea in proc.stdout:
            estado["latido"] = time.time()
            linea = linea.strip()
            if not linea:
                continue
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            tipo = d.get("type")
            if tipo == "thread.started":
                sid = d.get("thread_id")
                if sid and sid != _SESION:
                    _guardar_sesion(sid)
            elif tipo == "item.completed":
                item = d.get("item") or {}
                if item.get("type") == "agent_message":
                    texto = (item.get("text") or "").strip()
            elif tipo == "error":
                return None, str(d.get("message") or "error de codex")
    finally:
        estado["fin"] = True
        _en_vuelo = None

    codigo = proc.wait()
    if _CANCELADO:
        return "", None
    if estado["vencido"]:
        return None, f"estuvo {TIMEOUT // 60} minutos sin dar señales y lo corte"
    if not texto:
        err = ""
        try:
            err = (proc.stderr.read() or "").strip()[-400:]
        except Exception:
            pass
        if codigo != 0 or err:
            return None, err or f"codex termino con codigo {codigo}"
        if time.time() - estado["latido"] > SIN_SENAL_SEG:
            return None, f"no mando nada por {SIN_SENAL_SEG:.0f} segundos"
        return None, "no devolvio respuesta"

    _turnos += 1
    print("codex sesion: %s -> %s | turnos=%s" % (
        (previa or "-")[:8], (_SESION or "-")[:8], _turnos), flush=True)
    return texto, None


def esperando_dia():
    """True si dijo el saludo del dia y espera que elijas (lo consulta voz.py)."""
    return _esperando_dia


def resumen_de(sesion=None):
    """Resume una sesion anterior pasandole la charla vieja como texto a la de hoy."""
    s = sesion or sesion_anterior()
    if not s or not s.get("session_id"):
        return "No tengo guardada ninguna sesion anterior para resumirte."
    charla = _charla_de(s["session_id"])
    if not charla:
        return f"Tengo anotada la sesion del {s.get('dia')} pero no encontre la charla."
    print(f"codex: resumo la sesion {s['session_id'][:8]} del {s.get('dia')} "
          f"({len(charla)} caracteres)", flush=True)
    return preguntar(PROMPT_RESUMEN.format(dia=s.get("dia") or "anterior", charla=charla),
                     crudo=True)


def responder_dia(texto):
    """Interpreta tu respuesta al saludo del dia. Misma logica que en el otro cerebro.

    Los patrones (que gana entre "seguimos", "de que hablamos" y "empecemos de cero")
    se importan de `claude_voz`: estan calibrados a mano y hay 24 casos de prueba.
    Devuelve None si lo que dijiste NO era una respuesta al saludo.
    """
    global _esperando_dia, _pendiente, _DIA
    t = _plano(texto)
    sigue = resumen = nueva = False
    if _cl._SIGUE_VERBO.search(t):
        sigue = True
    elif _cl._RESUMEN.search(t):
        resumen = True
    elif _cl._SIGUE_FUERTE.search(t):
        sigue = True
    elif _cl._NUEVA_FUERTE.search(t) or _cl._NO_SUELTO.match(t):
        nueva = True
    elif _cl._SI_SUELTO.match(t):
        sigue = True
    if not (sigue or nueva or resumen):
        _esperando_dia = False
        _pendiente = None
        _archivar_actual()
        _guardar_sesion()
        print("codex: no contestaste el saludo, arranco sesion nueva y sigo tu pedido",
              flush=True)
        return None

    _esperando_dia = False
    pendiente, _pendiente = _pendiente, None

    if resumen:
        anterior = sesion_anterior()
        _archivar_actual()
        _guardar_sesion()
        return resumen_de(anterior)

    if sigue:
        _DIA = _dia_de()
        _guardar_sesion()
        print(f"codex: seguimos con la sesion {(_SESION or '-')[:8]}", flush=True)
        return preguntar(pendiente) if pendiente else "Dale, seguimos donde quedamos."

    _archivar_actual()
    _guardar_sesion()
    print(f"codex: sesion nueva del dia {_DIA}", flush=True)
    if pendiente:
        return preguntar(pendiente)
    return "Listo, arrancamos de cero. Contame."


def preguntar(consulta, reintentar=True, crudo=False, para_voz=True):
    """Manda la consulta a Codex. Misma firma y mismos caminos que el de Claude."""
    global _CANCELADO, _esperando_dia, _pendiente

    if not crudo:
        if (not _esperando_dia and _SESION and _DIA and _DIA != _dia_de()
                and (time.time() - _ultimo_turno) > GRACIA_CORTE):
            _esperando_dia = True
            _pendiente = consulta
            print(f"codex: primer turno del dia {_dia_de()} (la sesion abierta es del {_DIA})",
                  flush=True)
            return SALUDO_DIA

        if (not _esperando_dia and len(consulta) <= RESUMEN_LARGO_MAX
                and _cl._RESUMEN.search(_plano(consulta))):
            anterior = sesion_anterior()
            if anterior:
                return resumen_de(anterior)

    with _lock_turno:
        _CANCELADO = False
        texto, error = _turno(consulta)

    if _CANCELADO:
        print("codex: consulta cancelada (se mantiene la conversacion)", flush=True)
        return ""
    if error:
        print("codex fallo:", error, flush=True)
        if reintentar:
            print("codex: reintento", flush=True)
            # Respiro antes de reanudar: si el turno anterior se corto, que el proceso
            # muerto suelte la charla o el resume choca con "active writer". Si aun
            # asi quedo el candado y no hay nadie escribiendo, lo sacamos a mano:
            # sin esto la charla queda inservible y Laura se pasa a Claude.
            time.sleep(3)
            _soltar_candado(_SESION)
            return preguntar(consulta, reintentar=False, crudo=crudo, para_voz=para_voz)
        return "No pude hablar con Codex."

    texto = _limpiar(str(texto)) if para_voz else str(texto).strip()
    if not texto:
        return "Codex no me devolvio respuesta."
    return texto


if __name__ == "__main__":
    import sys
    print(preguntar(" ".join(sys.argv[1:]) or "Decime en una frase quien sos."))
