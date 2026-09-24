"""
Panel de control local: Servidor de IA + Dictado por voz.
  http://localhost:8750

Secciones:
  - Servidor: Bot Telegram + Webhook WhatsApp + Tunel Cloudflare (Prender/Apagar juntos)
  - Dictado por voz (F9): push-to-talk que transcribe y pega el texto (on/off aparte)
"""

import os
import re
import sys
import asyncio
import json
import time
import base64
import queue
import threading
import subprocess
import uuid
from pathlib import Path

import psutil
# ⚠ Esta laptop INTERCEPTA HTTPS: sin esto, cualquier pedido a un servidor de afuera
# muere con CERTIFICATE_VERIFY_FAILED (y a veces disfrazado de "Connection aborted /
# Permission denied", que fue como se vio al mandar un audio por Telegram el
# 2026-08-18). `truststore` hace que Python use el almacen de certificados de Windows,
# que es el que tiene el certificado del que intercepta. `webhook_wasender.py` ya lo
# hacia; el panel no lo necesitaba hasta que empezo a mandar audios al celular.
import truststore
truststore.inject_into_ssl()
import requests
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
import uvicorn

from app.rutas import (PESTANAS_MOVIL, PAUSA_ESCUCHA, SEGUIR_LECTURA, ESCRIBIR_EN,   # rutas en app/rutas.py
                       MIC_BLOQUEADO, PIZARRA_ESTADO, ESTATICOS, RESULTADOS,
                       CORTAR_VOZ, ESCUCHAR_YA, LEER_PANEL, PENSANDO,
                       NUEVA_SESION, ENV, CLAUDE_SESION, NOMBRES_SESIONES,
                       CARPETAS_SESIONES, ORDEN_CARPETAS, ASPECTO_CARPETAS,
                       RAIZ, WINDOWS_FONDOS,
                       SESIONES_ARCHIVADAS,
                       ESTUDIO, ESTUDIO_ENTRANTES, ESTUDIO_MINIATURAS, MARCAS_CHAT, ASPECTO,
                       COMPACTAR_LAURA, BORRADORES_SESIONES,
                       PERFILES_CHROME, PERFIL_CHROME_PERSONAL)
from app.voz import seguir               # listar proyectos/sesiones de Claude Code
# Los audios que entran por WhatsApp/Telegram, para el Estudio. ⚠ Este modulo NO
# importa `core`: si arrastrara Whisper, el panel cargaria la GPU al arrancar.
from app.nucleo import entrantes
# El puente con los Recordatorios del iPhone (pestaña Avisos). Tampoco toca Whisper.
from app.nucleo import avisos as avisos_mod
# El gasto de tokens de Claude Code, leido de sus transcripciones (tarjeta y vigia).
from app.nucleo import gasto
# Quien esta ocupando la placa de video, y prender/apagar Ollama. ⚠ Como `entrantes`:
# no importa nada de Whisper — habla con `nvidia-smi` por afuera.
from app.nucleo import placa
# Callar el traceback de WinError 10054 cuando un navegador corta la conexion de golpe.
from app.nucleo.red_windows import silenciar_reset_windows

PROJ = Path(__file__).parent
# El Python del entorno `wpp` de esta maquina. En otra maquina (quien instalo el proyecto
# con el README) esa carpeta no existe: ahi se usa el mismo Python que corre el panel,
# que es el del entorno donde se instalo todo.
PY = str(PROJ.parent / "envs" / "wpp" / "python.exe")
if not Path(PY).exists():
    PY = sys.executable
CLOUDFLARED = r"C:\cloudflared\cloudflared.exe"
CONFIG = str(PROJ / "wpp-config.yml")
CONFIG_DICTADO = PROJ / "config_dictado.json"
LOGS = PROJ / "logs"
LOGS.mkdir(exist_ok=True)
PORT = 8750
CREATE_NO_WINDOW = 0x08000000

# Los modulos viven en app/ y se lanzan con -m (Popen usa cwd=PROJ, asi que
# Python encuentra el paquete `app`). "match" es el texto que identifica al
# proceso en su linea de comando: si cambia el modulo, cambia aca tambien.
SERVICIOS = {
    "telegram": {"label": "Bot de Telegram", "match": "app.ingesta.bot_telegram",
                 "cmd": [PY, "-m", "app.ingesta.bot_telegram"]},
    "webhook":  {"label": "Webhook WhatsApp", "match": "app.ingesta.webhook_wasender",
                 "cmd": [PY, "-m", "uvicorn", "app.ingesta.webhook_wasender:app", "--host", "0.0.0.0", "--port", "8080"]},
    "tunel":    {"label": "Tunel Cloudflare", "proc_name": "cloudflared.exe",
                 "cmd": [CLOUDFLARED, "tunnel", "--config", CONFIG, "run", "wpp-transcriptor"]},
    "voz": {"label": "Voz (F9 dicta / Shift+F9 asistente)", "match": "app.voz.voz",
            "cmd": [PY, "-m", "app.voz.voz"]},
}
SERVIDOR = ["telegram", "webhook", "tunel"]   # se prenden/apagan juntos

# Con --auto (asi lo lanza el acceso de Inicio de Windows), el panel prende TODO
# solo al arrancar: servidor + voz. Sin el flag se comporta como siempre (botones).
AUTOSTART = "--auto" in sys.argv


# --- Quien esta vivo: UN solo barrido de procesos para todo el panel -------------
# ⚠⚠ Por que existe (2026-08-18). Antes `_procs` hacia un `process_iter` COMPLETO
# —con `cmdline`, que es lo caro— por CADA llamada, y `/status` llama a `vivo()`
# siete veces: cuatro servicios mas los tres de SERVIDOR. Medido en esta maquina:
# 404 procesos, 0,048 s el barrido con `cmdline` contra 0,002 s sin el (24 veces
# mas caro), o sea 0,34 s de CPU pura por pedido — y la pantalla pide `/status`
# cada 2,5 s POR PESTAÑA ABIERTA. Con las pestañas de Martin abiertas eso solo se
# comia mas de medio nucleo sin parar, y era la razon de que `/movil/sesiones`
# saltara de 60 ms a 0,3-1,7 s: quedaba haciendo cola detras de estos barridos.
# Ahora se barre UNA vez y la foto se comparte 1,5 s entre todas las pestañas y el
# vigilante. ⭐ El candado es parte del arreglo, no un adorno: los endpoints
# sincronos de FastAPI corren en hilos distintos, y sin el las tres pestañas
# barrian a la vez igual que antes.
_SNAP = {"ts": 0.0, "por_servicio": {}}
_SNAP_SEG = 1.5
_snap_lock = threading.Lock()


def _barrer():
    """Un unico recorrido de procesos, repartido por servicio."""
    por_servicio = {n: [] for n in SERVICIOS}
    yo = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == yo:
                continue
            # ⚠ Con `.get`, no con corchetes: cuando Windows no deja leer un dato de un
            # proceso ajeno, psutil devuelve el diccionario SIN esa clave (no con la clave
            # vacia). Indexandolo, un `KeyError: 'cmdline'` volteaba el barrido entero y el
            # panel se quedaba sin saber que servicio esta prendido (2026-09-06).
            nm = (p.info.get("name") or "").lower()
            cl = " ".join(p.info.get("cmdline") or [])
            if "panel.py" in cl:
                continue
            for name, svc in SERVICIOS.items():
                pn = (svc.get("proc_name") or "").lower()
                sig = svc.get("match")
                if pn:
                    if nm == pn:
                        por_servicio[name].append(p)
                elif sig and sig in cl and nm.startswith("python"):
                    por_servicio[name].append(p)
        except (psutil.Error, KeyError):
            # `psutil.Error` cubre NoSuchProcess, AccessDenied y ZombieProcess: un proceso
            # ajeno que se muere o se cierra mientras lo miramos no puede tumbar la foto.
            pass
    return por_servicio


def _foto(fresco=False):
    """La foto de los procesos, barrida de nuevo solo si vencio (o si la pedis fresca)."""
    with _snap_lock:
        if fresco or time.time() - _SNAP["ts"] > _SNAP_SEG:
            _SNAP["por_servicio"] = _barrer()
            _SNAP["ts"] = time.time()
        return _SNAP["por_servicio"]


def _invalidar_foto():
    """Despues de prender o apagar algo la foto quedo vieja: que la proxima barra."""
    with _snap_lock:
        _SNAP["ts"] = 0.0


def _procs(name, fresco=False):
    return _foto(fresco).get(name, [])


def vivo(name, fresco=False):
    return len(_procs(name, fresco)) > 0


# --- Vigilante: si un servicio se cae, te avisa al celular -----------------------
# Por que existe (2026-08-12): el Servidor estuvo APAGADO casi un dia entero y nada
# lo dijo. El panel lo mostraba en rojo, pero hay que estar mirando el panel. Un
# servicio caido en silencio es peor que uno que falla ruidosamente: los clientes
# mandan audios que nadie procesa y te enteras cuando te reclaman.
AVISAR = str(Path.home() / ".claude" / "skills" / "avisar" / "scripts" / "avisar.py")
VIGILANTE_SEG = 60          # cada cuanto mira
GRACIA_SEG = 300            # margen tras un apagado/reinicio HECHO DESDE EL PANEL

_esperado = {}              # servicio -> "arriba" | "abajo" (lo que vos pediste)
_silencio_hasta = {}        # servicio -> hasta cuando no molestar (reinicio en curso)
_avisado_caido = set()      # ya avise que este esta caido: no repetir hasta que vuelva


def _avisar(texto):
    """Manda el aviso por WhatsApp (si falla, el script cae solo a Telegram)."""
    try:
        subprocess.Popen([PY, AVISAR, "--por", "whatsapp", "--categoria", "produccion",
                          "--proyecto", "Servidor IA", texto],
                         cwd=str(PROJ), creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        print(f"vigilante: no pude avisar: {e}", flush=True)


def _marcar(name, estado):
    """El panel pidio prender o apagar: eso NO es una falla, es una orden tuya.

    OJO con la marca de "ya avise que esta caido": al PRENDER no se borra a
    proposito. Si se borra, el vigilante ve el servicio vivo pero ya sin la marca
    y se traga el aviso de "volvio a andar" — probado el 2026-08-12: llego la
    caida y nunca la recuperacion. Al APAGAR si se borra: lo apagaste vos, no hay
    nada que recuperar.
    """
    _esperado[name] = estado
    _silencio_hasta[name] = time.time() + GRACIA_SEG
    if estado == "abajo":
        _avisado_caido.discard(name)


# --- Vigia del gasto de tokens (2026-08-18) --------------------------------------
# La leccion del drenaje: 1.640 millones de tokens en un dia y nadie lo vio hasta el
# dia siguiente. Con esto, una quema asi suena en el celular a la PRIMERA hora.
# Mismas reglas anti-ruido que el vigilante: avisa en el cambio de estado, no repite.
QUEMA_ALTA = 40_000_000        # tokens por hora; el drenaje del 17/08 andaba por 60M/h
_quema_avisada = False


def _vigilar_gasto():
    global _quema_avisada
    r = gasto.resumen()                       # adentro recalcula cada 30 s como mucho
    q = r.get("ultima_hora", 0)
    if not _quema_avisada and q >= QUEMA_ALTA:
        _quema_avisada = True
        cual = (r.get("sesiones") or [{}])[0]
        _avisar(f"Claude esta quemando {gasto.lindo(q)} tokens en la ultima hora "
                f"({r.get('linda', '?')} en el dia). La sesion que mas gasta: "
                f"{cual.get('nombre', '?')} con {cual.get('linda', '?')}. "
                "Mira el panel: alguna charla quedo releyendo un contexto gigante.")
    elif _quema_avisada and q < QUEMA_ALTA // 2:
        _quema_avisada = False
        _avisar(f"La quema de tokens volvio a lo normal: {gasto.lindo(q)} en la ultima hora.")


# --- Autocompactacion de Laura (2026-08-18) --------------------------------------
# Si su charla arrastra demasiado contexto y esta quieta, el panel le deja la misma
# señal que el boton Compactar del chat y voz.py hace el resto (resumen -> sesion
# nueva sembrada, la vieja archivada). Laura avisa en voz alta cuando termina.
AUTOCOMPACTAR_EN = 160_000     # tokens de contexto; el chip del chat ya avisa antes
_AUTOCOMPACTAR_CADA = 30 * 60  # refractario: compactar tarda ~1 min y baja el contexto
_autocompactada_ts = 0.0


def _autocompactar_laura():
    global _autocompactada_ts
    if time.time() - _autocompactada_ts < _AUTOCOMPACTAR_CADA:
        return
    # Quieta de verdad: la voz prendida, sin un turno en el aire y sin otra
    # compactacion ya pedida. En medio de un turno no se compacta.
    if not vivo("voz") or COMPACTAR_LAURA.exists() or PENSANDO.exists():
        return
    sid = _sesion_de_laura()
    if not sid:
        return
    from app.voz import sesiones_movil
    ctx = sesiones_movil.contexto(str(RAIZ), sid) or {}
    # El tope mira ademas la ventana del MODELO: con 200 mil el CLI compacta solo al
    # ~80 % y ese resumen lo arma el — compactando al 70 % llegamos antes (2026-08-20).
    tope = min(AUTOCOMPACTAR_EN, int((ctx.get("tope") or 200_000) * 0.7))
    if ctx.get("tokens", 0) < tope:
        return
    _autocompactada_ts = time.time()
    COMPACTAR_LAURA.write_text("automatico: contexto pesado", encoding="utf-8")
    print(f"autocompactar: la charla de Laura arrastra {ctx['tokens']} tokens, "
          "se le pidio la compactacion sola", flush=True)


def _vigilar():
    """Avisa por los CAMBIOS de estado, no en cada vuelta.

    Tres casos, y los tres importan:
      - andaba y se cayo solo            -> aviso de falla
      - lo apagaste vos y quedo apagado  -> recordatorio pasada la gracia (esto es
                                            exactamente lo que paso el 2026-08-12)
      - volvio                           -> aviso de que se recupero, y se rearma
    """
    while True:
        time.sleep(VIGILANTE_SEG)
        for name in SERVICIOS:
            try:
                esta = vivo(name)
                if esta:
                    if name in _avisado_caido:
                        _avisado_caido.discard(name)
                        _avisar(f"{SERVICIOS[name]['label']}: volvio a andar.")
                    _esperado.setdefault(name, "arriba")
                    continue
                if name in _avisado_caido:
                    continue                       # ya avise, no repito
                if time.time() < _silencio_hasta.get(name, 0):
                    continue                       # reinicio en curso, es normal
                if _esperado.get(name) == "abajo":
                    _avisado_caido.add(name)
                    _avisar(f"{SERVICIOS[name]['label']} sigue apagado "
                            f"{GRACIA_SEG // 60} minutos despues de pararlo. "
                            "Si era un reinicio, no volvio a prender.")
                elif _esperado.get(name) == "arriba":
                    _avisado_caido.add(name)
                    _avisar(f"{SERVICIOS[name]['label']} se cayo solo. "
                            "Nadie lo apago desde el panel.")
            except Exception as e:
                print(f"vigilante {name}: {e}", flush=True)
        try:
            _vigilar_gasto()
        except Exception as e:
            print(f"vigia gasto: {e}", flush=True)
        try:
            _autocompactar_laura()
        except Exception as e:
            print(f"autocompactar: {e}", flush=True)


def start_one(name):
    _marcar(name, "arriba")        # lo pediste vos: si no arranca, el vigilante avisa
    # ⚠ Fresco a proposito: con la foto de hasta 1,5 s atras, prender algo que se
    # acaba de caer no haria nada (lo veria "vivo" y volveria sin lanzarlo).
    if vivo(name, fresco=True):
        return
    logf = open(LOGS / f"{name}.log", "a", encoding="utf-8")
    subprocess.Popen(SERVICIOS[name]["cmd"], cwd=str(PROJ),
                     stdout=logf, stderr=subprocess.STDOUT,
                     creationflags=CREATE_NO_WINDOW)
    _invalidar_foto()


def stop_one(name):
    _marcar(name, "abajo")                     # apagado a pedido: no es una falla (pero si queda
    for p in _procs(name, fresco=True):        # apagado pasada la gracia, el vigilante te lo recuerda)
        try:                                   # ⚠ fresco: matar por una foto vieja seria
            p.terminate()                      # apuntarle a pids que ya no estan
        except psutil.Error:
            pass
    _invalidar_foto()


# --- Microfono de Windows: mute a nivel de sistema -------------------------------
# El interruptor del panel NO usa la llave de Privacidad y seguridad de Windows:
# esa clave (ConsentStore en el registro) resulto ser un placebo para programas
# comunes — medido el 2026-08-13: con "Deny" el audio seguia llegando identico por
# WASAPI, y la rama que si corta todo (HKLM) pide administrador. Lo que se usa es
# el MUTE del dispositivo (IAudioEndpointVolume, lo mismo que la tecla de
# silenciar microfono): muteados TODOS los microfonos activos, cualquier programa
# recibe ceros exactos (verificado: 15840/15840 muestras en cero). Laura queda
# sorda a proposito — es el boton de privacidad fuerte; su watchdog no cambia de
# micro por silencio pasivo, asi que no pelea contra esto.

# ⚠ TODO el trabajo COM va en un SUBPROCESO (app/mic_windows.py), nunca en este
# proceso. No "simplificar" llamando a pycaw directo desde un endpoint ni desde
# un hilo propio: comtypes en un servidor multihilo termina en crash nativo del
# panel entero — paso el 2026-08-13 DOS veces (con COM en los handlers y con un
# hilo dedicado tambien: "COM method call without VTable" y muerte muda).

_MIC_CACHE = {"permitido": True, "vence": 0.0}   # para no lanzar un proceso por refresco
_MIC_CACHE_SEG = 10


def _mic_llamar(accion):
    """Corre app/mic_windows.py y devuelve el estado que informo (o None si fallo)."""
    try:
        r = subprocess.run([PY, "-m", "app.mic_windows", accion], cwd=str(PROJ),
                           capture_output=True, text=True, timeout=15,
                           creationflags=CREATE_NO_WINDOW)
        return json.loads(r.stdout.strip()).get("permitido")
    except Exception as e:
        print(f"mic_windows {accion}: {e}", flush=True)
        return None


def mic_permitido():
    """False solo si TODOS los microfonos activos estan silenciados."""
    if time.time() > _MIC_CACHE["vence"]:
        r = _mic_llamar("leer")
        if r is not None:
            _MIC_CACHE["permitido"] = r
        _MIC_CACHE["vence"] = time.time() + _MIC_CACHE_SEG
    return _MIC_CACHE["permitido"]


def _maestro_llamar(estado):
    """Mueve el interruptor maestro de Privacidad y seguridad via
    app/mic_maestro.py (automatiza Configuracion: la ventana se abre sola un
    momento y se cierra). True si quedo en el estado pedido ("on"/"off")."""
    try:
        r = subprocess.run([PY, "-m", "app.mic_maestro", estado], cwd=str(PROJ),
                           capture_output=True, text=True, timeout=60,
                           creationflags=CREATE_NO_WINDOW)
        return json.loads(r.stdout.strip()).get("maestro") == estado
    except Exception as e:
        print(f"mic_maestro {estado}: {e}", flush=True)
        return False


app = FastAPI(title="Panel Servidor IA")


@app.on_event("startup")
def _autostart():
    """Lanzado con --auto (acceso de Inicio): prende servidor + voz sin tocar nada."""
    # El vigilante arranca SIEMPRE, con --auto o sin el: lo que hay que vigilar es
    # que lo que estaba andando siga andando, no como se prendio.
    for n in SERVICIOS:
        _esperado[n] = "arriba" if vivo(n) else "abajo"
    threading.Thread(target=_vigilar, daemon=True).start()
    print("vigilante de servicios activo (avisa por WhatsApp si algo se cae)", flush=True)
    if not AUTOSTART:
        return
    for n in list(SERVIDOR) + ["voz"]:
        try:
            start_one(n)
        except Exception as e:
            print(f"autostart {n}: {e}", flush=True)

PAGINA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Servidor IA</title>
<style>
 :root{color-scheme:dark}
 *{box-sizing:border-box;font-family:Segoe UI,system-ui,sans-serif}
 html,body{height:100%}
 body{margin:0;background:var(--c0b0d12,#0b0d12);color:var(--ce8eaed,#e8eaed);padding:calc(14px * var(--ui,1));overflow:hidden}
 /* ⚠ El ancho maximo del panel NO sigue a --ui, a diferencia de todo lo de adentro:
    achicar los controles es para GANAR lugar, y escalando esto la pantalla entera se
    volveria mas angosta, que es lo contrario de lo que se pidio. */
 .wrap{height:100%;max-width:1900px;margin:0 auto;display:flex;flex-direction:column}
 /* ⭐ El color de la barra de arriba sale de `--barra` (2026-08-29). De fabrica vale
    `transparent`, que es como estuvo siempre: se ve el fondo de la pantalla. Solo si
    Martin le elige un color en el panel de aspecto, la barra se pinta. Por eso no hay
    padding nuevo: agregarselo le moveria la fila 6 px a quien no eligio nada. */
 header{display:flex;align-items:center;gap:calc(9px * var(--ui,1));flex-wrap:wrap;margin:0 calc(2px * var(--ui,1)) calc(12px * var(--ui,1));flex:none;
        background:var(--barra,transparent);border-radius:12px}
 header h1{font-size:calc(18px * var(--ui,1));margin:0 calc(6px * var(--ui,1)) 0 0}
 .chip{display:inline-flex;align-items:center;gap:calc(6px * var(--ui,1));padding:calc(3px * var(--ui,1)) calc(11px * var(--ui,1));border-radius:999px;
       font-size:calc(12px * var(--ui,1));background:var(--c161b23,#161b23);border:1px solid var(--c262e3a,#262e3a);color:var(--c8b93a1,#8b93a1);max-width:calc(330px * var(--ui,1));
       white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .chip .pto{width:calc(7px * var(--ui,1));height:calc(7px * var(--ui,1));border-radius:50%;background:var(--c4b5563,#4b5563);flex:none}
 .chip.on{color:var(--ok-txt)}.chip.on .pto{background:var(--ok);box-shadow:0 0 8px var(--ok)}
 .chip.warn{color:var(--aviso-txt)}.chip.warn .pto{background:var(--aviso)}
 .chip.off .pto{background:var(--mal)}
 /* Dos cosas distintas que antes iban mezcladas en la misma fila: a la IZQUIERDA
    los ESTADOS (Servidor, Voz, lectura, escritura), que solo se miran; a la
    DERECHA las PESTANAS de las otras pantallas, que se clickean. Separadas por
    una rayita, para que un estado no parezca una pestaña mas. */
 /* Solo la POSICION: como se ven los botones lo pone /estaticos/menu.js. */
 .pestanas{margin-left:auto;padding-left:calc(13px * var(--ui,1));border-left:1px solid var(--c262e3a,#262e3a)}
 /* --- Tablero de arriba: el estado de un vistazo -----------------------------
    Mismo idioma que la pantalla del celular: primero si Laura esta al aire, despues
    los numeros duros. Los numeros en monoespaciada con cifras de ancho fijo, para
    que no bailen al cambiar. */
 .mando{display:grid;grid-template-columns:auto 1fr;gap:calc(18px * var(--ui,1));align-items:center;
        background:var(--c121825,#121825);border:1px solid var(--c1e2636,#1e2636);border-radius:16px;
        padding:calc(14px * var(--ui,1)) calc(18px * var(--ui,1));margin:0 calc(2px * var(--ui,1)) calc(13px * var(--ui,1))}
 .mando .aire{display:flex;align-items:center;gap:calc(13px * var(--ui,1))}
 .mando .rot{font-size:calc(12.5px * var(--ui,1));letter-spacing:.2em;text-transform:uppercase;font-weight:800}
 .mando.aire-on .rot{color:var(--ok)} .mando.aire-pausa .rot{color:var(--aviso-txt)}
 .mando.aire-off .rot{color:var(--mal-txt)}
 .mando .latido{display:flex;gap:calc(5px * var(--ui,1));align-items:flex-end;height:calc(22px * var(--ui,1))}
 .mando .latido i{width:calc(6px * var(--ui,1));height:calc(7px * var(--ui,1));border-radius:3px;background:var(--c2a3446,#2a3446)}
 .mando.aire-on .latido i{background:var(--ok);animation:respirar2 1.6s infinite ease-in-out}
 .mando.aire-on .latido i:nth-child(2){animation-delay:.25s}
 .mando.aire-on .latido i:nth-child(3){animation-delay:.5s}
 @keyframes respirar2{0%,100%{height:calc(7px * var(--ui,1));opacity:.5} 50%{height:calc(20px * var(--ui,1));opacity:1}}
 .mando .cifras{display:flex;gap:calc(22px * var(--ui,1));justify-content:flex-end}
 .mando .cifra{text-align:right}
 .mando .cifra b{display:block;font:700 calc(21px * var(--ui,1))/1 ui-monospace,SFMono-Regular,Menlo,monospace;
                 font-variant-numeric:tabular-nums;color:var(--ce8eaed,#e8eaed)}
 .mando .cifra b span{font-size:calc(13px * var(--ui,1));color:var(--c5c6675,#5c6675)}
 .mando .cifra small{display:block;margin-top:calc(4px * var(--ui,1));color:var(--c616977,#616977);font-size:calc(10.5px * var(--ui,1));
                     letter-spacing:.07em;text-transform:uppercase}
 .cols{flex:1;min-height:0;display:grid;grid-template-columns:290px minmax(560px,1fr);gap:calc(13px * var(--ui,1))}
 /* Las explicaciones largas se guardan detras de un "?" chiquito: la primera vez que
    usas algo las necesitas, despues son ruido todos los dias. Es <details> nativo,
    sin JS y sin estado que mantener. */
 /* Servidor, Voz y Sesiones viven en UNA tarjeta (pedido de Martin), separados por
    una linea fina en vez de por tres marcos: menos ruido visual, misma division. */
 .bloque + .bloque{border-top:1px solid var(--c232a35,#232a35);margin-top:calc(14px * var(--ui,1));padding-top:calc(13px * var(--ui,1))}
 .ayuda{margin-top:calc(7px * var(--ui,1))}
 .ayuda summary{list-style:none;cursor:pointer;color:var(--c616977,#616977);font-size:calc(10.8px * var(--ui,1));
                display:inline-flex;align-items:center;gap:calc(5px * var(--ui,1));user-select:none}
 .ayuda summary::-webkit-details-marker{display:none}
 .ayuda summary::before{content:'?';display:inline-flex;align-items:center;
   justify-content:center;width:calc(15px * var(--ui,1));height:calc(15px * var(--ui,1));border-radius:50%;border:1px solid var(--c333b49,#333b49);
   font-size:calc(10px * var(--ui,1));color:var(--c7d8592,#7d8592)}
 .ayuda summary:hover{color:var(--c9aa3b2,#9aa3b2)}
 .ayuda[open] summary{margin-bottom:calc(5px * var(--ui,1))}
 .ayuda .cuerpo{color:var(--c616977,#616977);font-size:calc(10.8px * var(--ui,1));line-height:1.5;
                border-left:2px solid var(--c232a35,#232a35);padding-left:calc(9px * var(--ui,1))}
 .col{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:calc(12px * var(--ui,1));scrollbar-width:thin}
 /* El aspecto elegible (fondo, tipografia y color) lo aplica /estaticos/aspecto.js;
    aca solo se enganchan las superficies y el acento de ESTA pantalla. */
 .card{background:var(--fondo2);border:1px solid var(--c232a35,#232a35);border-radius:14px;padding:calc(12px * var(--ui,1)) calc(14px * var(--ui,1));flex:none}
 .mando{background:var(--fondo2)}
 .chip.on{border-color:var(--acento);color:var(--acento)}
 h2{margin:0 0 calc(2px * var(--ui,1));font-size:calc(14px * var(--ui,1))}
 .sub{color:var(--c7d8592,#7d8592);font-size:calc(11.3px * var(--ui,1));margin-bottom:calc(8px * var(--ui,1));line-height:1.35}
 .estado{display:flex;align-items:center;gap:calc(9px * var(--ui,1));margin:calc(6px * var(--ui,1)) 0 calc(8px * var(--ui,1));font-size:calc(15px * var(--ui,1));font-weight:600}
 .dot{width:calc(11px * var(--ui,1));height:calc(11px * var(--ui,1));border-radius:50%;background:var(--c4b5563,#4b5563);transition:.3s;flex:none}
 .on .dot{background:var(--ok);box-shadow:0 0 10px var(--ok)}.off .dot{background:var(--mal)}
 .svc{display:flex;align-items:center;gap:calc(9px * var(--ui,1));padding:calc(5px * var(--ui,1)) 0;border-top:1px solid var(--c1e242e,#1e242e);font-size:calc(12.6px * var(--ui,1))}
 .svc .d{width:calc(8px * var(--ui,1));height:calc(8px * var(--ui,1));border-radius:50%;background:var(--c4b5563,#4b5563);flex:none}
 .svc.up .d{background:var(--ok)}.svc.down .d{background:var(--mal)}
 .svc .n{flex:1}.svc .s{color:var(--c7d8592,#7d8592);font-size:calc(11px * var(--ui,1))}
 .btns{display:flex;gap:calc(8px * var(--ui,1));margin-top:calc(10px * var(--ui,1))}
 button{flex:1;padding:calc(9px * var(--ui,1));border:0;border-radius:9px;font-size:calc(12.8px * var(--ui,1));font-weight:600;cursor:pointer;transition:.15s}
 .prender{background:var(--ok);color:var(--c05230f,#05230f)}.prender:hover{background:var(--ok-2)}
 .apagar{background:var(--c262c37,#262c37);color:var(--ce8eaed,#e8eaed)}.apagar:hover{background:var(--c333b49,#333b49)}
 .btn-linea{width:100%;padding:calc(7px * var(--ui,1));border-radius:8px;border:1px solid var(--c333b49,#333b49);background:var(--c181d26,#181d26);
            color:var(--ccdd3dc,#cdd3dc);cursor:pointer;font-size:calc(12px * var(--ui,1));margin-top:calc(8px * var(--ui,1))}
 .btn-linea:hover{background:var(--c1f2530,#1f2530)}
 .fila-sw{display:flex;align-items:center;gap:calc(10px * var(--ui,1));margin-top:calc(8px * var(--ui,1));padding:calc(7px * var(--ui,1)) calc(10px * var(--ui,1));border-radius:8px;
          background:var(--c10141b,#10141b);border:1px solid var(--c1e242e,#1e242e)}
 .fila-sw.bloq{border-color:var(--mal-2)}
 .fila-sw .n{flex:1;font-size:calc(12.3px * var(--ui,1));line-height:1.35}
 .fila-sw .s{display:block;color:var(--c7d8592,#7d8592);font-size:calc(10.6px * var(--ui,1))}
 .sw{position:relative;width:calc(42px * var(--ui,1));height:calc(22px * var(--ui,1));border-radius:999px;background:var(--c333b49,#333b49);border:0;
     cursor:pointer;transition:.2s;flex:none;padding:0}
 /* ⚠ El `top`/`left` del circulito escala junto con el circulito: con el interruptor
    achicado y estos dos en 3 px fijos, la bolita se sale por abajo del riel. */
 .sw::after{content:'';position:absolute;top:calc(3px * var(--ui,1));left:calc(3px * var(--ui,1));width:calc(16px * var(--ui,1));height:calc(16px * var(--ui,1));border-radius:50%;
            background:var(--ce8eaed,#e8eaed);transition:.2s}
 .sw.on{background:var(--ok)}
 .sw.on::after{left:calc(23px * var(--ui,1));background:var(--c05230f,#05230f)}
 .sw:disabled{opacity:.4;cursor:default}
 button:disabled{opacity:.4;cursor:default}
 .hint{color:var(--c616977,#616977);font-size:calc(10.8px * var(--ui,1));margin-top:calc(8px * var(--ui,1));line-height:1.45}
 .campo{margin-top:calc(8px * var(--ui,1))}
 .campo label{display:block;color:var(--c7d8592,#7d8592);font-size:calc(10.8px * var(--ui,1));margin-bottom:calc(4px * var(--ui,1))}
 .campo select{width:100%;padding:calc(7px * var(--ui,1)) calc(9px * var(--ui,1));border-radius:8px;background:var(--c0e1117,#0e1117);color:var(--ce8eaed,#e8eaed);
               border:1px solid var(--c262e3a,#262e3a);font-size:calc(12.3px * var(--ui,1))}
 .estado-linea{font-size:calc(11.8px * var(--ui,1));margin-top:calc(7px * var(--ui,1));padding:calc(6px * var(--ui,1)) calc(10px * var(--ui,1));border-radius:8px;background:var(--c10141b,#10141b);
               border:1px solid var(--c1e242e,#1e242e);color:var(--c616977,#616977);display:flex;align-items:center;gap:calc(7px * var(--ui,1))}
 .estado-linea.activo-lec{color:var(--ok-txt);border-color:var(--ok-bd)}
 .estado-linea.activo-esc{color:var(--c93c5fd,#93c5fd);border-color:var(--c1e3a8a,#1e3a8a)}
 .estado-linea a{margin-left:auto;color:var(--c616977,#616977);font-size:calc(11px * var(--ui,1));cursor:pointer;text-decoration:none;flex:none}
 .estado-linea a:hover{color:var(--ce8eaed,#e8eaed)}
 .estado-linea .txt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .barra{height:calc(7px * var(--ui,1));border-radius:5px;background:var(--c20262f,#20262f);overflow:hidden}
 .barra>div{height:100%;border-radius:5px;transition:width .5s;background:var(--ok)}
 /* --- La placa de video: cuanta memoria queda y quien la esta ocupando ---
    ⭐ El color NO es un semaforo de "esta mal": la placa llena de modelos andando es
    lo normal acá. Verde tirando a gris mientras entra otro modelo, ambar cuando ya
    casi no entra nada, y rojo solo cuando de verdad no entra NADA mas (pedido de
    Martin: el rojo es unicamente para lo que esta mal). */
 #plcBarra{background:var(--ok)}
 #plcBarra.lleno{background:var(--aviso-txt)}
 #plcBarra.tope{background:var(--mal)}
 .svc .mini{margin-left:auto;flex:none;padding:calc(3px * var(--ui,1)) calc(9px * var(--ui,1));border-radius:7px;cursor:pointer;
       background:var(--c181d26,#181d26);color:var(--cc9ced8,#c9ced8);border:1px solid var(--c333b49,#333b49);font-size:calc(10.8px * var(--ui,1))}
 .svc .mini:hover:not(:disabled){border-color:var(--c4b5563,#4b5563);color:var(--ce8eaed,#e8eaed)}
 .svc .mini:disabled{opacity:.5;cursor:default}
 .svc .mini.prende{color:var(--ok-txt);border-color:var(--ok-bd)}
 .svc.libre .n{color:var(--c7d8592,#7d8592)}
 .chat-card{flex:1 1 auto;display:flex;flex-direction:column;min-height:0}
 #chat{flex:1;min-height:0;overflow-y:auto;background:var(--c0e1117,#0e1117);border:1px solid var(--c1e242e,#1e242e);
       border-radius:11px;padding:calc(12px * var(--ui,1));margin-top:calc(6px * var(--ui,1));display:flex;flex-direction:column;
       gap:calc(7px * var(--ui,1));scroll-behavior:smooth;scrollbar-width:thin}
 /* Barra de abajo del chat: hablarle sin tocar el microfono, y cortarla. */
 .barra-chat{display:flex;align-items:center;gap:calc(8px * var(--ui,1));margin-top:calc(8px * var(--ui,1));flex-wrap:wrap}
 .barra-chat button{padding:calc(8px * var(--ui,1)) calc(13px * var(--ui,1));border-radius:9px;background:var(--c161b22,#161b22);color:var(--ce8eaed,#e8eaed);
                    border:1px solid var(--c333b49,#333b49);cursor:pointer;font-size:calc(12.6px * var(--ui,1))}
 .barra-chat button:hover:not(:disabled){border-color:var(--c4b5563,#4b5563)}
 .barra-chat .cortar{color:var(--mal-txt)}
 /* El selector de modelo va apagado como los botones: se pinta SOLO cuando no esta
    en el de fabrica, que es la unica vez que importa mirarlo. */
 /* ⚠⚠ `appearance:none` no es cosmetico: en Windows el <select> nativo ignora el
    fondo y queda BLANCO adentro de la barra oscura (visto el 2026-08-18). Apagada la
    apariencia hay que dibujarle la flecha, que va de fondo. */
 #selModelo,#selEsfuerzo,#selModeloCodex,#selEsfuerzoCodex,#selVelocidadCodex,#selCerebro{appearance:none;-webkit-appearance:none;padding:calc(7px * var(--ui,1)) calc(22px * var(--ui,1)) calc(7px * var(--ui,1)) calc(9px * var(--ui,1));
            border-radius:9px;background:var(--c161b22,#161b22) no-repeat right 8px center/9px 6px;
            background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 9 6'><path d='M0 0h9L4.5 6z' fill='%238b94a3'/></svg>");
            color:var(--c8b94a3,#8b94a3);border:1px solid var(--c333b49,#333b49);cursor:pointer;font-size:calc(12.2px * var(--ui,1))}
 #selModelo.puesto,#selEsfuerzo.puesto{color:var(--c8ecbff,#8ecbff);border-color:var(--c2c4a66,#2c4a66)}
 #selModeloCodex.puesto,#selEsfuerzoCodex.puesto,#selVelocidadCodex.puesto{color:var(--ok-txt);border-color:var(--ok-bd)}
 /* Con CUAL de los dos cerebros grandes piensa. Se pinta distinto del resto porque no
    es una perilla fina como el modelo: es con quien estas hablando. Verde suave, no
    rojo — esto no esta mal, esta puesto (ver la regla de colores de la memoria). */
 #selCerebro.otro{color:var(--ok-txt);border-color:var(--ok-bd)}
 /* Las opciones las dibuja Windows: sin esto quedan claras sobre claro. */
 #selModelo option,#selEsfuerzo option,#selModeloCodex option,#selEsfuerzoCodex option,#selVelocidadCodex option,#selCerebro option{background:var(--c161b22,#161b22);color:var(--ce8eaed,#e8eaed)}
 /* Cuanto arrastra la charla, y el boton encendido cuando conviene compactar. Los
    tonos son suaves a proposito: esto informa, no reta — el rojo es para lo roto. */
 .barra-chat .ctx{padding:calc(6px * var(--ui,1)) calc(9px * var(--ui,1));border-radius:9px;background:var(--c161b22,#161b22);color:var(--c6e7889,#6e7889);
                  border:1px solid var(--c333b49,#333b49);font-size:calc(11.6px * var(--ui,1));white-space:nowrap}
 .barra-chat .ctx.medio{color:var(--aviso-txt);border-color:var(--aviso-bg)}
 .barra-chat .ctx.mucho{color:var(--aviso-txt);background:var(--aviso-bg);border-color:var(--aviso-bd)}
 .barra-chat button.conviene{color:var(--aviso-txt);border-color:var(--aviso-bd);background:var(--aviso-bg)}
 #hablarEstado{color:var(--c616977,#616977);font-size:calc(11.4px * var(--ui,1))}
 /* Caja para escribirle: crece sola con el texto, hasta un tope. */
 .escribir{display:flex;align-items:flex-end;gap:calc(6px * var(--ui,1));margin-top:calc(8px * var(--ui,1))}
 .escribir textarea{flex:1;resize:none;max-height:120px;padding:calc(9px * var(--ui,1)) calc(11px * var(--ui,1));border-radius:10px;
                    background:var(--c0e1117,#0e1117);color:var(--ce8eaed,#e8eaed);border:1px solid var(--c262e3a,#262e3a);font-size:calc(13px * var(--ui,1));
                    font-family:inherit;line-height:1.4}
 .escribir textarea:focus{outline:none;border-color:var(--c3b82f6,#3b82f6)}
 .escribir button{padding:calc(9px * var(--ui,1)) calc(12px * var(--ui,1));border-radius:10px;background:var(--c1d4ed8,#1d4ed8);color:#fff;border:0;
                  cursor:pointer;font-size:calc(14px * var(--ui,1));flex:none}
 .escribir button.clip{background:var(--c161b22,#161b22);border:1px solid var(--c333b49,#333b49);color:var(--c9aa3b2,#9aa3b2)}
 .escribir button:disabled{opacity:.4;cursor:default}
 #adjunto{margin-top:calc(8px * var(--ui,1))}
 #adjunto .chapa{display:inline-flex;align-items:center;gap:calc(8px * var(--ui,1));background:var(--c10141b,#10141b);
                 border:1px solid var(--c1e242e,#1e242e);border-radius:9px;padding:calc(5px * var(--ui,1)) calc(8px * var(--ui,1));font-size:calc(11.6px * var(--ui,1));
                 color:var(--c9aa3b2,#9aa3b2)}
 #adjunto img{height:calc(34px * var(--ui,1));border-radius:5px;display:block}
 #adjunto a{color:var(--mal-txt);cursor:pointer;text-decoration:none}
 /* "Laura esta pensando": tres puntitos, del mismo lado que sus respuestas. */
 .pensando{align-self:flex-start;background:var(--burbuja-ia);border-left:3px solid var(--burbuja-ia-borde);
           padding:calc(9px * var(--ui,1)) calc(13px * var(--ui,1));border-radius:13px 13px 13px 3px;display:flex;gap:calc(5px * var(--ui,1));
           align-items:center}
 .pensando i{width:calc(6px * var(--ui,1));height:calc(6px * var(--ui,1));border-radius:50%;background:var(--ca78bfa,#a78bfa);display:block;
             animation:latir 1.1s infinite ease-in-out}
 .pensando i:nth-child(2){animation-delay:.18s}
 .pensando i:nth-child(3){animation-delay:.36s}
 @keyframes latir{0%,80%,100%{opacity:.25;transform:translateY(0)}
                  40%{opacity:1;transform:translateY(-3px)}}
 .escribir textarea:disabled{opacity:.55;cursor:not-allowed}
 /* Visor de imagenes: encima del panel, sin abrir pestañas nuevas. */
 #visor{position:fixed;inset:0;background:rgba(var(--c04060a-rgb,4,6,10),.86);display:none;align-items:center;
        justify-content:center;z-index:60;cursor:zoom-out;padding:calc(26px * var(--ui,1))}
 #visor.abierto{display:flex}
 #visor img{max-width:94vw;max-height:92vh;border-radius:12px;
            box-shadow:var(--sombra-3);cursor:default}
 #visor .cerrar{position:absolute;top:14px;right:20px;color:var(--c9aa3b2,#9aa3b2);font-size:calc(26px * var(--ui,1));
                cursor:pointer;line-height:1}
 /* pantallas mas angostas: los controles se ensanchan un poco, y abajo de 950 una sola
    columna con scroll normal. */
 @media(max-width:1450px){
   .cols{grid-template-columns:360px 1fr}
 }
 @media(max-width:950px){
   body{overflow:auto}
   .cols{display:flex;flex-direction:column}
   .col{overflow:visible}
   #chat{height:60vh;flex:none}
 }
</style></head><body><div class="wrap">

<header>
  <h1>🤖 Servidor IA</h1>
  <span class="chip" id="chipSrv"><span class="pto"></span>Servidor</span>
  <span class="chip" id="chipVoz"><span class="pto"></span>Voz</span>
  <span class="chip" id="chipLec" style="display:none"><span class="pto"></span><span id="chipLecTxt"></span></span>
  <span class="chip" id="chipEsc" style="display:none"><span class="pto"></span><span id="chipEscTxt"></span></span>
  <!-- ⟳ pedido de Martin (2026-08-18): reinicio completo desde la pantalla — apaga
       los servicios, el panel se deja matar por el .bat de lanzadores y vuelve con
       --auto, que prende todo. -->
  <button id="btnReiniciarTodo" onclick="reiniciarTodo()"
    title="Reinicia el panel y todos los servicios (la voz tarda unos 20 s en volver)"
    style="padding:5px 11px;border-radius:8px;border:1px solid var(--c333b49,#333b49);background:var(--c181d26,#181d26);color:var(--cc8d0dc,#c8d0dc);cursor:pointer;font-size:13px">⟳ Reiniciar todo</button>
  <!-- ⭐ Soltar la maquina (2026-09-03). El ⟳ de al lado NO hace esto: reinicia panel y
       servicios y no toca ni un proceso de sesion. Este duerme las sesiones que se puedan
       dormir y no reinicia nada; las dormidas vuelven solas con --resume al escribirles. -->
  <button id="btnSoltar" onclick="soltarMaquina()"
    title="Duerme las sesiones que no esten trabajando para recuperar memoria. No reinicia nada y no se pierde ninguna charla: vuelven solas cuando les escribis."
    style="padding:5px 11px;border-radius:8px;border:1px solid var(--c333b49,#333b49);background:var(--c181d26,#181d26);color:var(--cc8d0dc,#c8d0dc);cursor:pointer;font-size:13px">💤 Soltar máquina</button>
  <!-- Las pestañas las dibuja /estaticos/menu.js, que es el MISMO menu de las cinco
       pantallas: agregar una va alla, no aca. -->
  <nav id="menuPantallas" class="pestanas"></nav>
</header>
<script src="/estaticos/menu.js"></script>
<script src="/estaticos/aspecto.js"></script>
<script src="/estaticos/atajos.js"></script>

<div class="mando" id="mando">
  <div class="aire">
    <div class="latido"><i></i><i></i><i></i></div>
    <div><div class="rot" id="mandoRot">···</div>
         <div style="color:var(--c616977,#616977);font-size:12px;margin-top:3px" id="mandoSub">cargando</div></div>
  </div>
  <div class="cifras">
    <div class="cifra"><b id="cifServ">·</b><small>servicios</small></div>
    <div class="cifra"><b id="cifSes">·</b><small>sesiones vivas</small></div>
    <div class="cifra"><b id="cifDia">·</b><small>dichos hoy</small></div>
    <div class="cifra" id="cifGastoCaja"><b id="cifGasto">·</b><small id="cifGastoSub">tokens hoy</small></div>
    <!-- ⭐ Cuanta maquina queda (2026-09-03). Desde que las sesiones no tienen tope y se
         duermen solas cuando falta memoria, esta es la cifra que explica por que una
         charla vieja tarda 8 s en volver: estaba dormida. -->
    <div class="cifra" id="cifMaqCaja"><b id="cifMaq">·</b><small id="cifMaqSub">maquina</small></div>
  </div>
</div>

<div class="cols">
<div class="col">

<div class="card">

<!-- ⭐ `data-bloque` marca las siete zonas con titulo del panel para que cada una pueda
     tener su color (2026-08-29, "mas colores sobre el panel"). Lo lee aspecto.js, que
     pinta el h2 y un filito al costado. NO se buscan por posicion: un nth-child se rompe
     el dia que se agrega una tarjeta, y esta semana ya se agrego una (el adversarial).
     Si agregas un bloque nuevo, ponele su data-bloque y sumalo a BLOQUES en aspecto.js. -->
<section class="bloque" data-bloque="servidor">
  <h2>📨 Servidor</h2>
  <div class="sub">WhatsApp + Telegram: transcripcion y analisis</div>
  <div id="estadoSrv" class="estado off"><span class="dot"></span><span id="txtSrv">Apagado</span></div>
  <div id="svcsSrv"></div>
  <div class="btns">
    <button class="prender" onclick="acc('start')">Prender</button>
    <button class="apagar"  onclick="acc('stop')">Apagar</button>
  </div>
</section>

<section class="bloque" data-bloque="voz">
  <h2>🎙️ Voz</h2>
  <div class="sub">Dictado y asistente, manos libres</div>
  <div id="estadoVoz" class="estado off"><span class="dot"></span><span id="txtVoz">Apagado</span></div>
  <div id="svcsVoz"></div>
  <div class="campo">
    <label for="micSel">🎤 Microfono</label>
    <select id="micSel" onchange="setMicro()"></select>
  </div>
  <button id="btnMed" class="btn-linea" onclick="probarMic()">🎚 Probar microfono (15 s)</button>
  <div id="medZona" style="display:none;margin-top:7px">
    <div class="barra" style="height:14px"><div id="medBarra" style="background:#666;width:0%"></div></div>
    <div id="medTxt" style="font-size:.8em;color:#aaa;margin-top:3px">midiendo...</div>
  </div>
  <div class="fila-sw" id="micAccFila">
    <span class="n">🔒 Microfono de Windows<span class="s" id="micAccTxt">consultando...</span></span>
    <button class="sw" id="micAccSw" onclick="toggleMicAcc()"
      title="Apaga el microfono en Windows: mute de todos los dispositivos + el interruptor de Privacidad y seguridad. Configuracion se abre sola un momento — es normal. Tarda unos segundos."></button>
  </div>
  <button id="btnPausa" class="btn-linea" onclick="togglePausa()">⏸ Pausar escucha</button>
  <div class="btns">
    <button class="prender" onclick="acc('start/voz')">Prender</button>
    <button class="apagar"  onclick="acc('stop/voz')">Apagar</button>
  </div>
  <details class="ayuda"><summary>como funciona</summary>
    <div class="cuerpo"><b>F9</b> dicta al cursor · <b>Shift+F9</b> asistente ·
    <b>"Venus"</b> o <b>"Laura"</b> manos libres.<br>
    <b>Pausar</b>: para llamadas o juegos, sin descargar modelos — volver es instantaneo
    y F9 sigue andando.</div>
  </details>
</section>

<section class="bloque" id="bqPlaca" data-bloque="placa" style="display:none">
  <h2>🎮 Placa de video</h2>
  <div class="sub">Los modelos que la ocupan. Apagar uno le hace lugar al que sigue.</div>
  <div class="barra" style="height:9px"><div id="plcBarra" style="width:0%"></div></div>
  <div class="sub" id="plcTxt" style="margin:6px 0 0">midiendo...</div>
  <div id="plcLista"></div>
  <details class="ayuda"><summary>que es esto</summary>
    <div class="cuerpo">La placa tiene <b>8 GB</b> y los modelos no entran todos juntos.
    Aca ves cual la esta ocupando ahora y podes apagarlo sin salir del panel.<br>
    <b>Ollama</b> y el <b>generador 3D</b> se prenden tambien desde aca: quedan sueltos del
    panel, asi que reiniciarlo no los apaga. El generador tarda un rato largo en cargar.<br>
    <b>Whisper</b> vive adentro de la Voz y del Bot de Telegram: se apaga con el boton de
    ellos, aca arriba.<br>
    Cuanta memoria usa CADA uno no se puede saber en Windows — se ve el total nomas.</div>
  </details>
</section>

<section class="bloque" data-bloque="sesiones">
  <h2>🧠 Sesiones de Claude Code</h2>
  <div class="sub">Que te lea sus respuestas, o escribir ahi por voz</div>
  <div class="campo">
    <label for="sesProy">Proyecto</label>
    <select id="sesProy" onchange="sesSesiones()"></select>
  </div>
  <div class="campo">
    <label for="sesSes">Sesion</label>
    <select id="sesSes" onchange="sesBotones()"></select>
  </div>
  <div class="btns">
    <button class="prender" id="btnLeer" onclick="lecSeguir()">🔊 Leer esta</button>
    <!-- ⚠ La letra queda literal, sin variable, a proposito: el fondo es un azul fuerte
         que en el tema claro sigue siendo oscuro (es un boton), asi que el texto tiene que
         seguir siendo claro. Si se engancha a una tinta, en el tema claro se da vuelta
         solo y queda casi negro sobre azul. -->
    <button class="prender" id="btnEsc" onclick="escElegir()" style="background:var(--c3b82f6,#3b82f6);color:#eaf2ff"><!--no-tema-->✏️ Escribir aca</button>
  </div>
  <div class="estado-linea" id="lecEstado"><span class="txt">🔊 No esta leyendo ninguna sesion</span></div>
  <div class="estado-linea" id="escEstado"><span class="txt">✏️ Sin destino de escritura</span></div>
  <details class="ayuda"><summary>por voz</summary>
    <div class="cuerpo"><b>"Venus, selecciona la sesion X"</b> elige destino ·
    <b>"Venus, escribi..."</b> escribe ahi · <b>"enter"</b> al final manda ·
    <b>"deja de leer"</b> apaga. Se escribe solo en las vivas 🟢.</div>
  </details>
</section>

<section class="bloque" data-bloque="adversarial">
  <h2>🥊 Testing adversarial</h2>
  <div class="sub">El que escribe el codigo no lo juzga: tres revisores contra el sistema real</div>
  <div class="campo">
    <label for="advProy">Proyecto</label>
    <select id="advProy"></select>
  </div>
  <div class="campo">
    <label for="advTarea">Que hay que implementar</label>
    <textarea id="advTarea" rows="2" placeholder="Pedilo en una linea, como siempre"></textarea>
  </div>
  <details class="ayuda"><summary>la vara (opcional)</summary>
    <div class="cuerpo">Los escenarios contra los que van a juzgarlo. Si lo dejas vacio,
    la vara es el pedido de arriba.<br>
    <textarea id="advSpec" rows="3" style="width:100%;margin-top:6px"
              placeholder="Dado que... cuando... entonces..."></textarea></div>
  </details>
  <div class="btns">
    <button class="prender" id="btnAdv" onclick="advArrancar()">🥊 Contrastar</button>
    <button class="apagar" onclick="advLimpiarPizarra()"
            title="Saca del pizarron solo los papelitos que dejo el contraste. Lo tuyo y lo de Laura no se toca.">🧹 Limpiar pizarron</button>
  </div>
  <div class="sub" id="advMsg" style="margin-top:6px"></div>
  <div id="advLista"></div>
  <details class="ayuda"><summary>como funciona</summary>
    <div class="cuerpo">Una sesion de Claude <b>implementa</b>. Despues, tres revisores de
    contexto limpio tratan de <b>refutar</b> que funcione: uno de Claude abre el sistema en
    el navegador y lo usa como una persona, y dos de Codex leen su expediente, la vara y el
    diff.<br>
    <b>Un hallazgo sin evidencia no cuenta</b>, lo firme quien lo firme.<br>
    Si sale rojo, vuelve solo a implementar (dos vueltas) y no te enteras. Si despues de eso
    nadie pudo demostrar quien tiene razon, <b>ahi si te suena el telefono</b> y lo cortas
    vos con los botones que aparecen aca.</div>
  </details>
</section>

</div>

</div>
<div class="col">

<div class="card chat-card" data-bloque="vivo">
  <h2>💬 Conversacion en vivo</h2>
  <div class="sub">Lo que decis y lo que el asistente hace/contesta, en tiempo real</div>
  <div id="chat"></div>
  <div id="adjunto"></div>
  <div class="escribir">
    <textarea id="txtChat" rows="1" placeholder="Escribile a Laura... (Enter manda, Ctrl+V pega una imagen)"
              onkeydown="teclaChat(event)" oninput="autoAlto(this)"></textarea>
    <button id="btnClip" class="clip" onclick="document.getElementById('fileChat').click()"
            title="Adjuntar una imagen">📎</button>
    <button id="btnMandar" onclick="mandarChat()">➤</button>
    <input type="file" id="fileChat" accept="image/*" multiple style="display:none" onchange="elegirImagenes(this.files)">
  </div>
  <div class="barra-chat">
    <button id="btnLaura" onclick="escuchar('claude')">🎙 Laura</button>
    <button id="btnVenus" onclick="escuchar('local')">🎙 Venus</button>
    <button id="btnCortar" class="cortar" onclick="cortarVoz()">✋ Cortar</button>
    <button id="btnNueva" onclick="sesionNueva()" title="Arrancar de cero. La charla de ahora queda archivada, no se pierde">🔄 Nueva sesion</button>
    <!-- ⭐ Compactar es el termino medio entre seguir arrastrando toda la charla y
         arrancar de cero perdiendo el hilo: resume lo que venian hablando y sigue en
         una sesion nueva sembrada con ese resumen (pedido de Martin, 2026-08-18). -->
    <button id="btnCompactar" onclick="compactarSesion()" title="Resumir esta charla y seguir en una nueva, para que Laura deje de releer todo en cada turno">⇲ Compactar</button>
    <!-- ⚡ Skills y ∕ Comandos: los dibuja /estaticos/atajos.js (pedido de Martin,
         2026-08-18: los dos separados, porque todo junto en la barrita lo confunde). -->
    <span id="atajosLaura" style="display:inline-flex;gap:8px"></span>
    <button id="btnLeerVoz" onclick="toggleLeer()" title="Que ademas te diga la respuesta por los parlantes">🔊 Leer: no</button>
    <!-- ⭐ Con CUAL de los dos cerebros grandes piensa Laura: Claude Code o Codex.
         Es lo mismo que decirle "pasate a Codex" por voz. Ojo: cada uno se acuerda de
         SU propia charla, cambiar no muda la conversacion. Ver app/voz/cerebro_grande.py. -->
    <select id="selCerebro" onchange="cambiarCerebro(this.value)" style="display:none" title="Con cual de los dos cerebros piensa Laura"></select>
    <!-- Con que modelo piensa Laura. Se guarda en el servidor: el proceso vive en
         voz.py y lo relee antes de cada turno. Es del cerebro de Claude: con Codex
         puesto se esconde, porque ahi no manda nada. -->
    <select id="selModelo" onchange="cambiarModelo(this.value)" style="display:none" title="Con que modelo piensa Laura"></select>
    <!-- Cuanto se esfuerza en pensar antes de contestar (--effort del CLI). Bajo es
         rapido y barato; maximo piensa largo. Vacio deja el de fabrica. -->
    <select id="selEsfuerzo" onchange="cambiarEsfuerzo(this.value)" style="display:none" title="Cuanto piensa Laura antes de contestar"></select>
    <select id="selModeloCodex" onchange="cambiarAjusteCodex('modelo',this.value)" style="display:none" title="Con que modelo piensa Codex"></select>
    <select id="selEsfuerzoCodex" onchange="cambiarEsfuerzoCodex(this.value)" style="display:none" title="Cuanto piensa Codex antes de contestar"></select>
    <select id="selVelocidadCodex" onchange="cambiarAjusteCodex('velocidad',this.value)" style="display:none" title="Velocidad de Codex"></select>
    <!-- Cuanto contexto arrastra su charla en cada mensaje: el aviso de cuando
         conviene compactar. -->
    <span class="ctx" id="ctxLaura" style="display:none"></span>
    <span id="hablarEstado"></span>
  </div>
  <details class="ayuda"><summary>los botones</summary>
    <div class="cuerpo">Los 🎙 son lo mismo que decir el nombre: te dice "Te escucho", abre el
    microfono y contesta por los parlantes. Lo que escribis aca lo contesta por escrito.
    <b>Cortar</b> la calla sin apagar nada. <b>Leer</b> le suma la voz a lo escrito.</div>
  </details>
</div>

</div>
</div>

<div id="visor" onclick="cerrarVisor()">
  <span class="cerrar">✕</span>
  <img id="visorImg" src="" onclick="event.stopPropagation()">
</div>

</div><script>
const SRV=['telegram','webhook','tunel'];
// Visor de la imagen que mandaste: se abre encima del panel, se cierra tocando
// afuera o con Escape. Nada de pestañas nuevas — te sacaban del panel para ver una
// captura y despues habia que volver.
function abrirVisor(url){
  document.getElementById('visorImg').src=url;
  document.getElementById('visor').classList.add('abierto');
}
function cerrarVisor(){
  document.getElementById('visor').classList.remove('abierto');
  document.getElementById('visorImg').src='';
}
document.addEventListener('keydown', e=>{ if(e.key==='Escape') cerrarVisor(); });
// ⟳ Reinicio completo (pedido de Martin, 2026-08-18). Despues de pedirlo, hay que
// esperar a ver el panel MORIR y VOLVER: si se pregunta enseguida contesta el panel
// viejo y la pagina se recargaria sin haber reiniciado nada. Por eso el poll solo
// recarga tras un error de red (murio) o pasados 15 s (por si el corte fue tan
// rapido que no lo vimos).
async function reiniciarTodo(){
  if(!confirm('¿Reiniciar el panel y todos los servicios? La voz tarda unos 20 segundos en volver.')) return;
  try{ await fetch('/reiniciar-todo',{method:'POST'}); }
  catch(e){ alert('No pude pedir el reinicio: '+e); return; }
  const v=document.createElement('div');
  v.style.cssText='position:fixed;inset:0;background:rgba(var(--c0b0e13-rgb,11,14,19),.93);z-index:9999;'+
    'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--cc8d0dc,#c8d0dc)';
  v.innerHTML='<div style="font-size:34px">⟳</div>'+
    '<div style="font-size:17px">Reiniciando el panel y los servicios…</div>'+
    '<div style="font-size:13px;color:var(--c616977,#616977)">la voz tarda unos 20 segundos en volver</div>';
  document.body.appendChild(v);
  const desde=Date.now(); let murio=false;
  const t=setInterval(async ()=>{
    try{
      const r=await fetch('/status',{cache:'no-store'});
      if(r.ok && (murio || Date.now()-desde>15000)){ clearInterval(t); location.reload(); }
    }catch(e){ murio=true; }
    if(Date.now()-desde>120000){
      clearInterval(t);
      v.innerHTML='<div style="font-size:17px">El panel no volvio despues de 2 minutos.</div>'+
        '<div style="font-size:13px;color:var(--c616977,#616977)">Levantalo con el acceso Servidor IA del escritorio.</div>';
    }
  },1500);
}
function fila(s){return `<div class="svc ${s.vivo?'up':'down'}"><span class="d"></span>
  <span class="n">${s.label}</span><span class="s">${s.vivo?'activo':'detenido'}</span></div>`;}
function chip(id,cls,txt){const c=document.getElementById(id);c.className='chip '+cls;
  if(txt!==undefined){const t=c.querySelector('span:last-child');if(t)t.textContent=txt;}}

// --- La placa de video: quien la ocupa y prender/apagar los modelos ------------------
// Pedido de Martín (2026-08-22): "poder apagar o prender los modelos que ocupo para
// este panel desde el panel". Antes había que pedirle a una sesión que los matara a
// mano para que entrara el generador 3D.
// ⚠ La tarjeta se esconde entera si la máquina no tiene placa NVIDIA ni Ollama: no
// tiene sentido mostrar un medidor vacío.
let plcOcupado = false;      // hay un prender/apagar en curso: no repintar encima
function plcGigas(mb){return (mb/1024).toFixed(1).replace('.',',') + ' GB';}
async function pintarPlaca(){
  if(plcOcupado) return;
  let j; try{ j = await (await fetch('/placa')).json(); }catch(e){ return; }
  const bq = document.getElementById('bqPlaca');
  const modelos = (j.modelos||[]).filter(m => m.instalado);
  if(!j.ok && !modelos.length){ bq.style.display='none'; return; }
  bq.style.display='';
  const barra = document.getElementById('plcBarra');
  const pct = j.ok ? (j.pct||0) : 0;
  barra.style.width = pct + '%';
  barra.className = pct>=95 ? 'tope' : pct>=80 ? 'lleno' : '';
  document.getElementById('plcTxt').textContent = j.ok
    ? plcGigas(j.usado) + ' de ' + plcGigas(j.total) + ' usados' +
      (j.placa ? ' · ' + j.placa.replace('NVIDIA GeForce ','') : '')
    : (j.error || 'sin placa a la vista');
  // Cada uno que esté ocupando la placa, con su botón. Los que son servicios del panel
  // dicen de quién son, para que no parezca que hay dos formas de apagar lo mismo.
  const filas = (j.procesos||[]).map(p => {
    const sub = p.servicio ? 'servicio del panel' : (p.detalle || 'usando la placa');
    return `<div class="svc up"><span class="d"></span>
      <span class="n">${esc(p.nombre)}<span class="s" style="display:block">${esc(sub)}</span></span>
      <button class="mini" onclick="plcApagar(${p.pid},'${esc(p.nombre).replace(/'/g,"")}')">Apagar</button></div>`;
  });
  // Los que el panel sabe PRENDER van siempre, estén andando o no: si solo aparecieran
  // cuando ocupan la placa, no habría desde dónde levantarlos (que es medio el punto).
  for(const m of modelos){
    const cargados = (m.cargados||[]).join(', ');
    const sub = m.cargando ? 'cargando... abre el ' + m.puerto + ' cuando termina'
              : m.vivo ? (cargados ? 'con ' + cargados + ' en la placa'
                                   : 'prendido en el ' + m.puerto)
              : m.detalle;
    // ⚠ Mientras carga no hay botón: apagarlo a mitad de cargar deja los pesos por la
    // mitad, y prenderlo de nuevo no hace nada porque ya está prendido.
    const boton = m.cargando ? '<span class="s" style="margin-left:auto">cargando</span>'
      : `<button class="mini ${m.vivo?'':'prende'}"
           onclick="plcModelo('${m.clave}','${m.vivo?'apagar':'prender'}')"
           >${m.vivo?'Apagar':'Prender'}</button>`;
    filas.push(`<div class="svc ${m.vivo?'up':m.cargando?'':'libre'}"><span class="d"></span>
      <span class="n">${esc(m.nombre)}<span class="s" style="display:block">${esc(sub)}</span></span>
      ${boton}</div>`);
  }
  // ⭐ De quién es lo que se ve usado cuando NO hay ningún modelo cargado (lo preguntó
  // Martín el 2026-08-22: el medidor marcaba 1 GB y la lista estaba vacía). No es un
  // proceso: son las ventanas de Windows. Sin esta línea, el número quedaba sin dueño y
  // parecía que había algo escondido comiéndose la placa.
  const esc2 = j.escritorio || {};
  if(!(j.procesos||[]).length && esc2.cuantos){
    const quienes = (esc2.nombres||[]).join(', ');
    filas.push(`<div class="svc libre"><span class="d"></span><span class="n">
      Ningún modelo cargado<span class="s" style="display:block">lo usado es Windows dibujando:
      ${esc2.cuantos} programas${quienes ? ' (' + esc(quienes) + '...)' : ''}</span></span></div>`);
  }
  document.getElementById('plcLista').innerHTML = filas.join('');
}
async function plcApagar(pid, nombre){
  if(!confirm('¿Apagar ' + nombre + '? Libera la placa.')) return;
  plcOcupado = true;
  try{
    const r = await (await fetch('/placa/apagar/' + pid, {method:'POST'})).json();
    if(!r.ok) alert(r.error || 'No pude apagarlo.');
  }catch(e){ alert('No pude apagarlo: ' + e); }
  plcOcupado = false; pintarPlaca(); refrescar();
}
async function plcModelo(clave, accion){
  plcOcupado = true;
  const b = event && event.target;
  if(b){ b.disabled = true; b.textContent = accion==='prender' ? 'prendiendo...' : 'apagando...'; }
  try{
    const r = await (await fetch('/placa/modelo/' + clave + '/' + accion, {method:'POST'})).json();
    if(!r.ok) alert(r.error || 'No pude.');
  }catch(e){ alert('No pude: ' + e); }
  plcOcupado = false; pintarPlaca();
}
async function refrescar(){
  try{
    const j=await (await fetch('/status')).json();
    const up=SRV.filter(k=>j.servicios[k].vivo).length;
    const es=document.getElementById('estadoSrv');
    es.className='estado '+(up>0?'on':'off');
    document.getElementById('txtSrv').textContent = up===SRV.length?'Encendido':(up>0?'Parcial...':'Apagado');
    document.getElementById('svcsSrv').innerHTML = SRV.map(k=>fila(j.servicios[k])).join('');
    chip('chipSrv', up===SRV.length?'on':(up>0?'warn':'off'));
    const v=j.servicios.voz;
    const ev=document.getElementById('estadoVoz');
    ev.className='estado '+(v.vivo? ((j.pausado||!j.mic_permitido)?'':'on') :'off');
    document.getElementById('txtVoz').textContent =
      v.vivo ? (!j.mic_permitido ? 'Encendido, microfono bloqueado'
              : j.pausado ? 'Encendido, escucha pausada' : 'Encendido') : 'Apagado';
    ev.style.color = (v.vivo && !j.mic_permitido) ? 'var(--mal-txt)'
                   : (v.vivo && j.pausado) ? 'var(--aviso)' : '';
    document.getElementById('svcsVoz').innerHTML = fila(v);
    chip('chipVoz', v.vivo?((j.pausado||!j.mic_permitido)?'warn':'on'):'off');
    const bp=document.getElementById('btnPausa');
    bp.textContent = j.pausado ? '▶ Reanudar escucha' : '⏸ Pausar escucha';
    bp.style.borderColor = j.pausado ? 'var(--aviso)' : '#333b49';
    bp.disabled = !v.vivo;
    const sw=document.getElementById('micAccSw'), mf=document.getElementById('micAccFila'),
          mt=document.getElementById('micAccTxt');
    sw.className='sw '+(j.mic_permitido?'on':'');
    mf.className='fila-sw '+(j.mic_permitido?'':'bloq');
    mt.textContent=j.mic_permitido?'Los microfonos andan normal'
                                  :'SILENCIADOS a nivel de Windows: nada te escucha';
    mt.style.color=j.mic_permitido?'':'var(--mal-txt)';
    // El tablero de arriba: lo mismo que ya se calculo, pero de un vistazo
    const md=document.getElementById('mando');
    const aire = !v.vivo ? 'off' : (j.pausado||!j.mic_permitido) ? 'pausa' : 'on';
    md.className = 'mando aire-' + aire;
    document.getElementById('mandoRot').textContent =
      aire==='on' ? 'Al aire' : aire==='pausa' ? 'En pausa' : 'Apagada';
    document.getElementById('mandoSub').textContent =
      aire==='on' ? 'deci Laura y te escucha'
      : !v.vivo ? 'la voz esta apagada'
      : !j.mic_permitido ? 'microfono bloqueado en Windows' : 'no te esta escuchando';
    document.getElementById('cifServ').innerHTML = up + '<span>/' + SRV.length + '</span>';
    try{
      const l = await (await fetch('/lectura')).json();
      document.getElementById('cifSes').textContent =
        (l.proyectos||[]).reduce((n,p)=>n+(p.vivas||0),0);
    }catch(e){}
    if(j.leer!==undefined && j.leer!==leerEnVoz){ leerEnVoz=j.leer; pintarLeer(); }
    // Los puntitos salen si esta pensando por cualquier via: lo que mandaste vos
    // desde la caja (pensandoLocal) o lo que le estas hablando por microfono.
    // el estado de "pensando" NO se toma de aca: llega por /pensando, que se pide
    // mucho mas seguido (ver cargarPensando)
  }catch(e){}
}
async function acc(a){
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  await fetch('/'+a,{method:'POST'});
  setTimeout(()=>{document.querySelectorAll('button').forEach(b=>b.disabled=false);refrescar();},1500);
}
// El interruptor de Windows: mute de dispositivo, efecto inmediato, sin reiniciar nada.
// El finally es OBLIGATORIO: si el fetch falla (panel reiniciandose), sin el
// finally el boton quedaba deshabilitado para siempre hasta recargar la pagina.
async function toggleMicAcc(){
  const sw=document.getElementById('micAccSw');
  sw.disabled=true;
  try{
    await fetch('/micacceso',{method:'POST'});
    await refrescar();
  }catch(e){}
  finally{sw.disabled=false;}
}
// Pausar es instantaneo (solo escribe/borra un archivo): sin la espera de acc().
async function togglePausa(){
  const bp=document.getElementById('btnPausa');
  bp.disabled=true;
  await fetch('/pausa',{method:'POST'});
  await refrescar();
  bp.disabled=false;
}
async function cargarMicros(){
  try{
    const j=await (await fetch('/micros')).json();
    const sel=document.getElementById('micSel');
    sel.innerHTML='<option value="">Predeterminado de Windows'+(j.default?' ('+j.default+')':'')+'</option>'
      + j.microfonos.map(m=>`<option value="${m.replace(/"/g,'&quot;')}">${m}</option>`).join('');
    sel.value=j.seleccionado||'';
  }catch(e){}
}
let midiendo=false;
async function probarMic(){
  if(midiendo)return; midiendo=true;
  const btn=document.getElementById('btnMed'), zona=document.getElementById('medZona'),
        barra=document.getElementById('medBarra'), txt=document.getElementById('medTxt');
  zona.style.display='block'; btn.disabled=true; btn.textContent='Midiendo... habla normal';
  for(let i=0;i<18 && midiendo;i++){
    try{
      const j=await (await fetch('/medidor')).json();
      if(j.error){txt.textContent='Error: '+j.error; break;}
      const n=j.nivel, pct=Math.min(100, n/0.15*100);
      barra.style.width=pct+'%';
      if(n<0.0005){barra.style.background='var(--mal-2)'; txt.textContent='SILENCIO DIGITAL (0.0000) — el micro esta apagado o dormido';}
      else if(n<0.008){barra.style.background='var(--aviso-2)'; txt.textContent='nivel '+n.toFixed(4)+' — por DEBAJO del umbral (0.008): no te detecta';}
      else if(n<0.03){barra.style.background='var(--aviso-2)'; txt.textContent='nivel '+n.toFixed(4)+' — te detecta, pero JUSTO. Acercate o subi el mic en Windows';}
      else{barra.style.background='var(--ok-2)'; txt.textContent='nivel '+n.toFixed(4)+' — BIEN';}
    }catch(e){txt.textContent='sin respuesta del panel'; break;}
  }
  midiendo=false; btn.disabled=false; btn.textContent='🎚 Probar microfono (15 s)';
}
async function setMicro(){
  const sel=document.getElementById('micSel'); const v=sel.value; sel.disabled=true;
  await fetch('/micro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({microfono:v})});
  setTimeout(()=>{sel.disabled=false;refrescar();},2800);
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
let chatPrev='';
async function cargarChat(){
  try{
    const j=await (await fetch('/chat')).json();
    const s=JSON.stringify(j.items);
    if(s===chatPrev)return; chatPrev=s;
    const ult=j.items[j.items.length-1];
    ultimaEsSuya = !!(ult && ult.t==='ia');
    // cuantas veces contesto hoy: el chat ya esta pedido, la cuenta sale gratis
    const cd=document.getElementById('cifDia');
    if(cd) cd.textContent = j.items.filter(m=>m.t==='ia').length;
    const c=document.getElementById('chat');
    c.innerHTML=j.items.map(m=>{
      if(m.t==='vos'){
        const dic=m.x.startsWith('(dictado) ');
        const txt=dic?m.x.slice(10):m.x;
        // La imagen que mandaste se ve DE VERDAD, no como una ruta: click para abrirla
        // grande en el visor. La burbuja CON imagen va a ancho fijo, como una tarjeta:
        // la imagen llena ese ancho y el texto va debajo. Sin eso quedaba media burbuja
        // de color vacia al costado de la captura — era justo lo que se veia feo.
        // Varias imagenes en un mismo mensaje: se apilan una abajo de la otra, cada
        // una abre el visor por su cuenta.
        const imgs=(m.imgs||[]);
        const img=imgs.map(u=>`<img src="${u}" onclick="abrirVisor('${u}')" style="width:100%;display:block;border-radius:8px;cursor:zoom-in;margin-bottom:${txt||imgs.length>1?'7px':'0'}">`).join('');
        const ancho=imgs.length?'width:min(360px,82%);':'width:fit-content;';
        return `<div style="align-self:flex-end;background:${dic?'var(--acento-bg)':'var(--burbuja-vos)'};color:var(--burbuja-vos-txt);padding:7px 11px;border-radius:13px 13px 3px 13px;max-width:82%;${ancho}font-size:calc(13.4px * var(--escala,1));line-height:1.45">${dic?'<span style=\"opacity:.6;font-size:.8em\">✏️ dictado</span><br>':''}${img}${esc(txt)}${m.h?`<div style="text-align:right;opacity:.55;font-size:.72em;margin-top:3px">${m.h}</div>`:''}</div>`;
      }
      if(m.t==='ia'){
        const col = m.q==='Laura' ? '#a78bfa' : m.q==='Venus' ? '#5eead4'
                  : m.q==='Sistema' ? 'var(--aviso-txt)' : '#60a5fa';
        return `<div style="align-self:flex-start;background:var(--burbuja-ia);color:var(--ce8e8e8,#e8e8e8);padding:7px 11px;border-radius:13px 13px 13px 3px;max-width:82%;font-size:calc(13.4px * var(--escala,1));line-height:1.45;border-left:3px solid ${col}"><span style="color:${col};font-size:.76em;font-weight:600">${esc(m.q)}</span>${m.h?`<span style="float:right;opacity:.5;font-size:.72em">${m.h}</span>`:''}<br>${esc(m.x)}</div>`;
      }
      return `<div style="align-self:center;color:var(--c6b7280,#6b7280);font-size:.74em;padding:1px 0">· ${esc(m.x)} ·</div>`;
    }).join('');
    pintarPensando();
    c.scrollTop=c.scrollHeight;
  }catch(e){}
}
// La burbuja de los puntitos se agrega DESPUES de dibujar el chat: cargarChat()
// reescribe todo el html cada segundo y medio, asi que si viviera adentro de esa
// lista se borraria sola en el primer refresco.
let pensando=false;        // lo mandaste vos desde la caja
let pensandoRemoto=false;  // lo dice voz.py: puede venir del microfono o de Telegram
let ultimaEsSuya=false;    // el ultimo mensaje del chat ya es una respuesta de ella
function pintarPensando(){
  const c=document.getElementById('chat');
  const vieja=document.getElementById('burbujaPensando');
  if(vieja) vieja.remove();
  // ⭐ Regla de oro, y le gana a la señal del servidor: si lo ultimo que hay en el
  // chat YA es una respuesta suya, no esta pensando. Puede estar leyendotela en voz
  // alta, pero eso no es pensar. Sin esto los puntitos quedaban colgados abajo de una
  // respuesta ya escrita, que es exactamente cuando mas molestan.
  if(ultimaEsSuya) return;
  if(!pensando && !pensandoRemoto) return;
  const d=document.createElement('div');
  d.id='burbujaPensando'; d.className='pensando';
  d.innerHTML='<i></i><i></i><i></i>';
  c.appendChild(d);
  c.scrollTop=c.scrollHeight;
}
// --- Escribirle a Laura (texto + imagen) ------------------------------------
// Va por el mismo buzon que Telegram: una sola Laura para el microfono, el
// telefono y esta caja. La imagen no viaja en el mensaje: se guarda en disco y
// lo que se manda es la ruta, que ella abre con Read.
let imgsAdjuntas=[];   // pueden ir varias en un mismo mensaje
// El interruptor 🔊: que ademas de escribirla, la diga. Queda guardado en el
// navegador, asi que sobrevive a recargar la pagina y a reiniciar el panel.
let leerEnVoz = true;   // lo real lo manda el servidor en /status; esto es hasta que llegue
// OJO con el id: "btnLeer" YA lo usa el boton "Leer esta" de la tarjeta de
// sesiones. Cuando este se llamaba igual, getElementById devolvia el otro (el
// primero del documento): el interruptor no mostraba nunca si estaba prendido y
// encima le cambiaba el texto al de sesiones. Por eso este es btnLeerVoz.
function pintarLeer(){
  const b=document.getElementById('btnLeerVoz');
  b.style.background = leerEnVoz ? 'var(--ok-bd)' : '';
  b.style.borderColor = leerEnVoz ? 'var(--ok)' : '';
  b.textContent = leerEnVoz ? '🔊 Leer: si' : '🔊 Leer: no';
}
async function toggleLeer(){
  const b=document.getElementById('btnLeerVoz');
  b.disabled=true;
  try{
    const j=await (await fetch('/leer',{method:'POST'})).json();
    leerEnVoz=!!j.leer;
  }catch(e){}
  b.disabled=false;
  pintarLeer();
}
function autoAlto(t){
  if(!t.value){ t.style.height='40px'; return; }
  t.style.height='auto'; t.style.height=Math.min(t.scrollHeight,120)+'px';
}
function teclaChat(ev){
  // Enter manda; Shift+Enter hace un salto de linea, como en cualquier chat.
  // Mientras piensa, Enter no hace NADA: podes seguir escribiendo tranquilo, pero
  // el mensaje no sale (el buzon atiende de a uno y el segundo pisaria al primero).
  if(ev.key==='Enter' && !ev.shiftKey){ ev.preventDefault(); if(!ocupada()) mandarChat(); }
}
// Ocupada = pensando lo que le escribiste vos, o resolviendo algo que le dijiste
// por microfono: es la misma Laura, no puede atender dos cosas a la vez.
function ocupada(){ return pensando || pensandoRemoto; }
// Se pregunta 3 veces por segundo: con el refresco general de 2,5 s los puntitos
// aparecian cuando la respuesta YA estaba escrita, que es justo al reves de para
// lo que sirven.
async function cargarPensando(){
  try{
    const j=await (await fetch('/pensando')).json();
    if(!!j.pensando===pensandoRemoto) return;      // sin cambios: no toco el DOM
    pensandoRemoto=!!j.pensando;
    pintarPensando(); pintarMandar();
  }catch(e){}
}
function pintarMandar(){
  const b=document.getElementById('btnMandar');
  if(b) b.disabled = ocupada();
}
function elegirImagenes(fs){
  for(const f of fs||[]) if(f) imgsAdjuntas.push(f);
  pintarAdjuntos();
}
function pintarAdjuntos(){
  document.getElementById('adjunto').innerHTML = imgsAdjuntas.map((f,i)=>
    `<span class="chapa"><img src="${URL.createObjectURL(f)}">`+
    `<span>${esc(f.name||'pegada')}</span><a onclick="quitarImagen(${i})">✕</a></span>`).join('');
}
function quitarImagen(i){
  if(i===undefined) imgsAdjuntas=[]; else imgsAdjuntas.splice(i,1);
  pintarAdjuntos();
  document.getElementById('fileChat').value='';
}
// Ctrl+V con una imagen en el portapapeles (un recorte de pantalla, por ejemplo):
// se engancha en toda la pagina, no solo en la caja, porque uno pega apenas
// recorta, sin acordarse de hacer clic en el campo primero.
document.addEventListener('paste', ev=>{
  const fs=[...(ev.clipboardData&&ev.clipboardData.items||[])]
             .filter(i=>i.type && i.type.startsWith('image/'))
             .map(i=>i.getAsFile()).filter(Boolean);
  if(!fs.length) return;
  elegirImagenes(fs);                       // se SUMAN: pegar de nuevo no pisa la anterior
  document.getElementById('txtChat').focus();
});
async function mandarChat(){
  const t=document.getElementById('txtChat'), b=document.getElementById('btnMandar'),
        e=document.getElementById('hablarEstado');
  const texto=t.value.trim();
  if(!texto && !imgsAdjuntas.length) return;
  if(ocupada()) return;
  const fd=new FormData();
  fd.append('texto', texto);
  imgsAdjuntas.forEach((f,i)=> fd.append('imagenes', f, f.name||('pegada'+i+'.png')));
  // La caja queda LIBRE para seguir escribiendo (pedido de Martin): lo unico que se
  // bloquea es mandar, porque el buzon atiende de a uno y el segundo mensaje pisaria
  // al primero sin avisar. Se limpia al mandar, asi lo que escribas mientras espero
  // ya es el proximo mensaje y no se mezcla con el que salio.
  t.value=''; autoAlto(t); quitarImagen();
  pensando=true; ultimaEsSuya=false; pintarPensando(); pintarMandar();
  t.focus();
  try{
    const j=await (await fetch('/chat/mandar',{method:'POST',body:fd})).json();
    e.textContent = j.ok ? '' : (j.error||'no salio');
  }catch(err){ e.textContent='no salio: '+err; }
  pensando=false; pintarMandar();
  t.focus();
  cargarChat();
}
// --- Los botones 🎙: apretar en vez de decir el nombre -----------------------
// No graban nada aca. Le avisan a voz.py, que hace EXACTAMENTE lo mismo que con
// la palabra clave: "Te escucho", micro abierto, "No te escuche" si te quedas
// callado, y la respuesta por los parlantes. Un solo circuito para las dos
// formas de despertarla, asi no se van separando con el tiempo.
async function escuchar(modo){
  const e=document.getElementById('hablarEstado');
  const b=document.getElementById(modo==='claude'?'btnLaura':'btnVenus');
  b.disabled=true;
  try{
    const j=await (await fetch('/escuchar/'+modo,{method:'POST'})).json();
    e.textContent = j.ok ? 'te escucho... hablá' : (j.motivo||'no se pudo');
  }catch(err){ e.textContent='no se pudo'; }
  b.disabled=false;
  setTimeout(()=>{ e.textContent=''; }, 6000);
}
// Cortar NO es pausar: esto suelta el turno de ahora (lo que dice y lo que le
// esta preguntando a Claude) y no deja nada apagado. Pausar la escucha sigue
// siendo el otro boton, arriba, en la tarjeta de Voz.
// Pide confirmacion a proposito: corta la conversacion del dia. La charla no se
// pierde (queda archivada), pero el hilo con el que venias hablando si.
async function sesionNueva(){
  if(!confirm('¿Arrancar una sesion nueva? La charla de ahora queda archivada.')) return;
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/sesion/nueva',{method:'POST'})).json();
    e.textContent = j.ok ? 'arrancando de cero...' : (j.motivo||'no se pudo');
  }catch(err){ e.textContent='no se pudo'; }
  setTimeout(()=>{ e.textContent=''; cargarChat(); }, 3000);
}
// Compactar: el termino medio entre arrastrar toda la charla y arrancar de cero.
// Le pide un resumen a la sesion de ahora y sigue en una nueva sembrada con el, asi
// no pierde el hilo. Son DOS turnos de Claude, por eso avisa cuanto tarda.
async function compactarSesion(){
  if(!confirm('¿Compactar la charla? Laura la resume y sigue en una sesion nueva con ese resumen. Tarda un minuto.')) return;
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/sesion/compactar',{method:'POST'})).json();
    e.textContent = j.ok ? 'resumiendo la charla...' : (j.motivo||'no se pudo');
  }catch(err){ e.textContent='no se pudo'; }
  setTimeout(()=>{ e.textContent=''; cargarChat(); }, 8000);
}
// ⭐ Con CUAL de los dos cerebros grandes piensa Laura (Claude o Codex). Vive en el
// servidor por lo mismo que el modelo: el que lo usa es voz.py, no esta pantalla.
// Arranca en 'claude' porque es el de fabrica; si el panel no contesta, la barra
// queda como si nada en vez de esconder las perillas sin motivo.
let cerebroActivo='claude';
async function cargarCerebro(){
  try{
    const j=await (await fetch('/sesion/cerebro')).json();
    if(!j.ok) return;
    cerebroActivo=j.activo;
    const s=document.getElementById('selCerebro');
    s.innerHTML=j.cerebros.map(c=>'<option value="'+c.id+'"'+
      (c.id===j.activo?' selected':'')+'>'+c.nombre+'</option>').join('');
    s.style.display = j.cerebros.length ? '' : 'none';
    s.value=j.activo;
    s.classList.toggle('otro', j.activo!==j.defecto);
    cargarModelo();          // el modelo y el esfuerzo solo valen con Claude puesto
  }catch(err){}
}
// Cambiar de cerebro es instantaneo: es una palabra en un archivo que voz.py mira
// antes de cada turno. Lo que NO se muda es la charla — cada uno tiene la suya —, y
// por eso se avisa acá y no en silencio.
async function cambiarCerebro(v){
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/sesion/cerebro',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({cerebro:v})})).json();
    e.textContent = j.ok ? (j.frase||'listo') : 'no se pudo';
  }catch(err){ e.textContent='no se pudo'; }
  cargarCerebro();
  setTimeout(()=>{ e.textContent=''; }, 6000);
}
// Con que modelo piensa Laura. ⚠ Vive en el servidor y no en el navegador: el que
// lo usa es el proceso que lanza `claude` adentro de voz.py, no esta pantalla.
async function cargarModelo(){
  try{
    const j=await (await fetch('/sesion/modelo')).json();
    if(!j.ok) return;
    const s=document.getElementById('selModelo');
    s.innerHTML=j.modelos.map(m=>'<option value="'+m.id+'"'+
      (m.id===j.modelo?' selected':'')+'>'+m.nombre+'</option>').join('');
    // Vacio no se muestra: un <select> sin opciones es una caja en blanco al lado de
    // los botones (asi se veia con el panel sin reiniciar, 2026-08-18).
    // Y con Codex puesto tampoco: el modelo y el esfuerzo son perillas de Claude, y
    // dejarlas ahi hace creer que le estas cambiando el modelo al que esta pensando.
    s.style.display = (j.modelos.length && cerebroActivo==='claude') ? '' : 'none';
    s.value=j.modelo;
    s.classList.toggle('puesto', j.modelo!==j.defecto);
    // ⭐ Cuanto piensa antes de contestar (pedido de Martin, 2026-08-18): la perilla
    // hermana de la del modelo. Vacio = el esfuerzo de fabrica del CLI, y ese es el
    // unico valor que NO se pinta como "puesto".
    const se=document.getElementById('selEsfuerzo');
    if(se && j.esfuerzos){
      se.innerHTML=j.esfuerzos.map(x=>'<option value="'+x.id+'"'+
        (x.id===j.esfuerzo?' selected':'')+'>'+x.nombre+'</option>').join('');
      se.style.display = (j.esfuerzos.length && cerebroActivo==='claude') ? '' : 'none';
      se.value=j.esfuerzo||'';
      se.classList.toggle('puesto', !!j.esfuerzo);
    }
    const sm=document.getElementById('selModeloCodex');
    if(sm && j.codex && j.codex.modelos){
      sm.innerHTML=j.codex.modelos.map(x=>'<option value="'+x.id+'"'+
        (x.id===j.codex.modelo?' selected':'')+'>'+x.nombre+'</option>').join('');
      sm.style.display=(j.codex.modelos.length && cerebroActivo==='codex')?'':'none';
      sm.value=j.codex.modelo;
      sm.classList.toggle('puesto', j.codex.modelo!==j.codex.defecto);
    } else if(sm){ sm.style.display='none'; }
    // El esfuerzo se vuelve a pedir al cambiar modelo: así nunca ofrece un nivel
    // que ese modelo concreto no admite.
    const sc=document.getElementById('selEsfuerzoCodex');
    if(sc && j.codex && j.codex.esfuerzos){
      sc.innerHTML=j.codex.esfuerzos.map(x=>'<option value="'+x.id+'"'+
        (x.id===j.codex.esfuerzo?' selected':'')+'>'+x.nombre+'</option>').join('');
      sc.style.display = (j.codex.esfuerzos.length && cerebroActivo==='codex') ? '' : 'none';
      sc.value=j.codex.esfuerzo||'';
      sc.classList.toggle('puesto', !!j.codex.esfuerzo);
    } else if(sc){ sc.style.display='none'; }
    const sv=document.getElementById('selVelocidadCodex');
    if(sv && j.codex && j.codex.velocidades){
      sv.innerHTML=j.codex.velocidades.map(x=>'<option value="'+x.id+'"'+
        (x.id===j.codex.velocidad?' selected':'')+'>'+x.nombre+'</option>').join('');
      sv.style.display=(j.codex.velocidades.length && cerebroActivo==='codex')?'':'none';
      sv.value=j.codex.velocidad||'';
      sv.classList.toggle('puesto', !!j.codex.velocidad);
    } else if(sv){ sv.style.display='none'; }
    pintarContextoLaura(j.contexto);
  }catch(err){}
}
// El esfuerzo de Codex vale desde el proximo mensaje sin rearrancar nada: cada
// turno suyo ya es un proceso nuevo que lee el ajuste al armar el comando.
async function cambiarEsfuerzoCodex(x){
  return cambiarAjusteCodex('esfuerzo', x);
}
async function cambiarAjusteCodex(campo,x){
  const e=document.getElementById('hablarEstado');
  try{
    const cuerpo={}; cuerpo[campo]=x;
    const j=await (await fetch('/sesion/'+campo+'-codex',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(cuerpo)})).json();
    e.textContent = j.ok ? campo+' de Codex cambiado' : 'no se pudo';
  }catch(err){ e.textContent='no se pudo'; }
  cargarModelo();
  setTimeout(()=>{ e.textContent=''; }, 5000);
}
// ⭐ Cuanto arrastra la charla de Laura en CADA cosa que le pedis (pedido de Martin,
// 2026-08-18). No es lo que gasto en total: es lo que se vuelve a leer cada vez, que
// es lo que se paga de nuevo todo el tiempo. Cuando conviene, el boton Compactar se
// enciende: un aviso que no dice que hacer no sirve de nada.
function pintarContextoLaura(c){
  const chip=document.getElementById('ctxLaura');
  const bot=document.getElementById('btnCompactar');
  if(!chip) return;
  if(!c || !c.tokens){ chip.style.display='none'; if(bot) bot.classList.remove('conviene'); return; }
  chip.style.display='';
  chip.className='ctx '+(c.nivel||'bien');
  chip.textContent = c.tokens>=1000000 ? (c.tokens/1000000).toFixed(1).replace('.',',')+' M'
                                       : Math.round(c.tokens/1000)+' k';
  chip.title = c.aviso || ('La charla de Laura arrastra esto en cada mensaje.');
  if(bot) bot.classList.toggle('conviene', c.nivel==='mucho');
}
async function cambiarModelo(m){
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/sesion/modelo',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({modelo:m})})).json();
    // El proceso vivo tiene el modelo de antes: se rearranca solo en el proximo
    // turno, con --resume, asi que la charla sigue igual. Eso cuesta unos segundos.
    e.textContent = j.ok ? 'modelo cambiado (vale desde el proximo mensaje)' : 'no se pudo';
  }catch(err){ e.textContent='no se pudo'; }
  cargarModelo();
  setTimeout(()=>{ e.textContent=''; }, 5000);
}
// Cuanto se esfuerza Laura en pensar. Mismo camino que el modelo: vive en el
// servidor y el proceso se rearranca solo en el proximo turno, con --resume.
async function cambiarEsfuerzo(x){
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/sesion/esfuerzo',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({esfuerzo:x})})).json();
    e.textContent = j.ok ? 'esfuerzo cambiado (vale desde el proximo mensaje)' : 'no se pudo';
  }catch(err){ e.textContent='no se pudo'; }
  cargarModelo();
  setTimeout(()=>{ e.textContent=''; }, 5000);
}
async function cortarVoz(){
  const e=document.getElementById('hablarEstado');
  try{
    const j=await (await fetch('/cortar',{method:'POST'})).json();
    e.textContent = j.ok ? 'cortada' : (j.motivo||'no se pudo cortar');
  }catch(err){ e.textContent='no se pudo cortar'; }
  setTimeout(()=>{ e.textContent=''; }, 2500);
}
// --- Sesiones de Claude Code: UNA eleccion, dos acciones (leer / escribir) ---
let SES={leyendo:null, destino:null};
async function sesRefrescar(){
  try{
    const [l,e]=await Promise.all([fetch('/lectura').then(r=>r.json()),
                                   fetch('/escribir').then(r=>r.json())]);
    SES.leyendo=l.siguiendo; SES.destino=e.destino;
    const sel=document.getElementById('sesProy');
    const antes=sel.value;
    sel.innerHTML=l.proyectos.map(p=>`<option value="${p.cwd.replace(/"/g,'&quot;')}">${esc(p.nombre)} (${p.vivas} viva${p.vivas>1?'s':''})</option>`).join('')
      || '<option value="">(no hay sesiones vivas)</option>';
    if(antes && [...sel.options].some(o=>o.value===antes)) sel.value=antes;
    else if(sel.value) await sesSesiones();
    const le=document.getElementById('lecEstado');
    if(SES.leyendo){ le.className='estado-linea activo-lec';
      le.innerHTML=`<span class="txt">🔊 Leyendo: ${esc(SES.leyendo.nombre||'?')}</span><a onclick="lecParar()">✕ dejar</a>`; }
    else { le.className='estado-linea';
      le.innerHTML='<span class="txt">🔊 No esta leyendo ninguna sesion</span>'; }
    const ee=document.getElementById('escEstado');
    if(SES.destino){ ee.className='estado-linea activo-esc';
      ee.innerHTML=`<span class="txt">✏️ Escribiendo en: ${esc(SES.destino.nombre||'?')}</span><a onclick="escQuitar()">✕ quitar</a>`; }
    else { ee.className='estado-linea';
      ee.innerHTML='<span class="txt">✏️ Sin destino de escritura</span>'; }
    const cl=document.getElementById('chipLec');
    if(SES.leyendo){cl.style.display='';chip('chipLec','on');
      document.getElementById('chipLecTxt').textContent='🔊 '+(SES.leyendo.nombre||'');}
    else cl.style.display='none';
    const ce=document.getElementById('chipEsc');
    if(SES.destino){ce.style.display='';chip('chipEsc','on');
      document.getElementById('chipEscTxt').textContent='✏️ '+(SES.destino.nombre||'');}
    else ce.style.display='none';
  }catch(e){}
}
async function sesSesiones(){
  const cwd=document.getElementById('sesProy').value;
  if(!cwd) return;
  try{
    const j=await (await fetch('/lectura/sesiones?cwd='+encodeURIComponent(cwd))).json();
    document.getElementById('sesSes').innerHTML=j.sesiones.map(s=>
      `<option value="${s.jsonl.replace(/"/g,'&quot;')}" data-n="${esc(s.nombre)}" data-i="${s.id}" data-v="${s.viva?1:0}">${s.viva?'🟢':'⚪'} ${esc(s.nombre)} — ${esc(s.detalle)}</option>`).join('')
      || '<option value="">(sin sesiones recientes)</option>';
    sesBotones();
  }catch(e){}
}
function sesBotones(){
  const o=document.getElementById('sesSes').selectedOptions[0];
  document.getElementById('btnEsc').disabled = !(o && o.dataset.v==='1');
  document.getElementById('btnLeer').disabled = !(o && o.value);
}
async function lecSeguir(){
  const o=document.getElementById('sesSes').selectedOptions[0];
  if(!o || !o.value) return;
  await fetch('/lectura/seguir',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({jsonl:o.value, nombre:o.dataset.n,
                         cwd:document.getElementById('sesProy').value})});
  sesRefrescar();
}
async function lecParar(){ await fetch('/lectura/parar',{method:'POST'}); sesRefrescar(); }
async function escElegir(){
  const o=document.getElementById('sesSes').selectedOptions[0];
  if(!o || !o.value || o.dataset.v!=='1') return;
  await fetch('/escribir/elegir',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({jsonl:o.value, nombre:o.dataset.n, id:o.dataset.i,
                         cwd:document.getElementById('sesProy').value})});
  sesRefrescar();
}
async function escQuitar(){ await fetch('/escribir/quitar',{method:'POST'}); sesRefrescar(); }
// ⭐ El gasto de tokens del dia, en el tablero de arriba (2026-08-18, el dia del
// drenaje: 1.640 millones quemados y nadie lo vio hasta el dia siguiente). Rojo
// SOLO si la ultima hora viene desbocada — rojo es "algo esta mal", no un estado.
async function verGasto(){
  try{
    const g = await (await fetch('/gasto')).json();
    if(!g.ok) return;
    const b = document.getElementById('cifGasto');
    b.textContent = g.linda;
    b.style.color = g.quema ? 'var(--mal-txt)' : '';
    // ⭐ Codex A LA VISTA y no solo en el globito del mouse (2026-08-20): la cifra
    // grande sigue siendo Claude, y abajo se lee el otro cupo con su porcentaje.
    const sub = document.getElementById('cifGastoSub');
    if (sub) sub.textContent = (g.codex && g.codex.hoy)
      ? 'hoy · Codex ' + g.codex.linda +
        (g.codex.cupo != null ? ' (' + Math.round(g.codex.cupo) + '%)' : '')
      : 'tokens hoy';
    // La cifra grande es Claude (es donde vive el drenaje). Codex se cuenta aparte y
    // se dice en el globito: son dos cupos distintos y mezclarlos no querria decir nada.
    document.getElementById('cifGastoCaja').title =
      'Claude: ' + g.linda + ' · ultima hora ' + g.ultima_hora_linda + ' · ' +
      g.llamadas + ' llamadas hoy' +
      (g.codex ? '\\nCodex: ' + g.codex.linda + ' en ' + g.codex.charlas + ' charlas' +
        (g.codex.cupo!=null ? ' · cupo usado ' + Math.round(g.codex.cupo) + '%' +
          (g.codex.renueva ? ' (se renueva el ' +
            new Date(g.codex.renueva*1000).toLocaleDateString('es-AR') + ')' : '') : '') : '') +
      ((g.sesiones||[]).length ? '\\nLas que mas gastan:\\n' +
        g.sesiones.map(s => '  ' + s.nombre + ': ' + s.linda).join('\\n') : '');
  }catch(e){}
}
// ⚡ Skills y ∕ Comandos en la barra del chat de Laura (los dibuja atajos.js). La
// sesion la resuelve el servidor con de=laura: esta pantalla no sabe el id de la
// charla de Laura, y mejor que siga sin saberlo.
if (window.Atajos) Atajos.montar({
  contenedor: document.getElementById('atajosLaura'),
  sesion: () => ({de: 'laura'}),
  insertar: t => {
    const c = document.getElementById('txtChat');
    c.value = (c.value ? c.value.trimEnd() + ' ' : '') + t;
    autoAlto(c); c.focus();
  },
  // Los comandos con equivalente aca apretan ESE boton: mandarle "/compact" como
  // texto a una sesion no hace nada (el CLI lo ignora desde afuera, probado).
  acciones: {
    compactar: compactarSesion,
    nueva: sesionNueva,
    modelo: () => { const s = document.getElementById('selModelo');
                    if (s){ s.focus(); if (s.showPicker) try{ s.showPicker(); }catch(e){} } }
  }
});
pintarLeer();
// ---- Testing adversarial: el que escribe el codigo no lo juzga ----
// ⚠ El selector de proyectos se llena UNA vez: si se repintara cada 8 s, elegir una
// carpeta mientras corre el refresco te devolvia el cursor a la primera de la lista.
let advCarpetas = false;
const ADV_CARA = {implementando:'⚙ implementando', contrastando:'🥊 contrastando',
                  verde:'✅ verde', empate:'🤝 te espera', fallo:'⚠ se corto'};

function advMsg(txt){ document.getElementById('advMsg').textContent = txt || ''; }

async function advPintar(){
  let j; try{ j = await (await fetch('/adversarial/lista')).json(); }catch(e){ return; }
  const sel = document.getElementById('advProy');
  if(!advCarpetas && (j.carpetas||[]).length){
    sel.innerHTML = j.carpetas.map(c =>
      `<option value="${c.cwd.replace(/"/g,'&quot;')}">${esc(c.nombre)}</option>`).join('');
    advCarpetas = true;
  }
  const zona = document.getElementById('advLista');
  const corridas = (j.corridas||[]).slice(0,4);
  zona.innerHTML = corridas.map(t => {
    const paso = (t.pasos||[]).slice(-1)[0];
    const cara = ADV_CARA[t.estado] || esc(t.estado);
    const vuelta = (t.estado==='implementando'||t.estado==='contrastando')
      ? ` · vuelta ${t.vuelta} de ${j.vueltas}` : '';
    // Cada hallazgo va CON su evidencia: sin eso la tarjeta seria una lista de
    // opiniones, que es justo lo que el metodo no acepta.
    const hall = (t.hallazgos||[]).map(h =>
      `<div class="s" style="display:block;margin-top:4px">• ${esc(h.que)}
         <span style="opacity:.7;display:block">${esc(h.de)}: ${esc(h.evidencia)}</span></div>`).join('');
    const tirados = t.descartados
      ? `<div class="s" style="display:block;opacity:.7">${t.descartados} opinion(es) sin
           evidencia, descartadas</div>` : '';
    const botones = t.estado==='empate'
      ? `<div class="btns" style="margin-top:6px">
           <button class="mini" onclick="advResolver('${t.id}','revisor')">Tiene razon el revisor</button>
           <button class="mini prende" onclick="advResolver('${t.id}','implementador')">Tiene razon el que lo escribio</button>
         </div>` : '';
    const clase = t.estado==='verde' ? 'up' : t.estado==='empate' ? '' : 'libre';
    return `<div class="svc ${clase}" style="align-items:flex-start"><span class="d"></span>
      <span class="n">${esc(t.proyecto)} — ${cara}${vuelta}
        <span class="s" style="display:block">${esc(t.tarea).slice(0,90)}</span>
        <span class="s" style="display:block;opacity:.7">${esc(t.error || (paso ? paso.que : ''))}</span>
        ${hall}${tirados}${botones}</span></div>`;
  }).join('');
}

async function advArrancar(){
  const b = document.getElementById('btnAdv');
  const cwd = document.getElementById('advProy').value;
  const tarea = document.getElementById('advTarea').value.trim();
  if(!cwd){ advMsg('Elegi un proyecto.'); return; }
  if(!tarea){ advMsg('Deci que hay que implementar.'); return; }
  b.disabled = true; advMsg('arrancando...');
  try{
    const r = await fetch('/adversarial/arrancar', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({cwd, tarea, spec: document.getElementById('advSpec').value})});
    const j = await r.json();
    if(!j.ok){ advMsg(j.error || 'no arranco'); }
    else{
      document.getElementById('advTarea').value = '';
      document.getElementById('advSpec').value = '';
      advMsg('Arranco. Podes cerrar esto: si hay empate te aviso al telefono.');
      advPintar();
    }
  }catch(e){ advMsg('no pude arrancar: ' + e); }
  b.disabled = false;
}

async function advLimpiarPizarra(){
  advMsg('barriendo el pizarron...');
  try{
    const j = await (await fetch('/adversarial/limpiar-pizarra',{method:'POST'})).json();
    advMsg(j.sacadas ? `Saque ${j.sacadas} papelito(s) mio(s) del pizarron.`
                     : 'No habia ningun papelito mio en el pizarron.');
  }catch(e){ advMsg('no pude barrer: ' + e); }
}

async function advResolver(id, aFavor){
  advMsg('anotando tu decision...');
  try{
    const r = await fetch('/adversarial/resolver', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, a_favor: aFavor})});
    const j = await r.json();
    advMsg(j.ok ? (aFavor === 'revisor' ? 'Va otra vuelta.' : 'Queda en verde.')
                : (j.error || 'no pude anotarlo'));
  }catch(e){ advMsg('no pude anotarlo: ' + e); }
  advPintar();
}

cargarMicros(); refrescar(); cargarChat(); sesRefrescar(); cargarCerebro();
verGasto(); setInterval(verGasto, 300000);

// ⭐ Cuanta maquina queda y el boton de soltarla (2026-09-03).
async function verMaquina(){
  try{
    const m = await (await fetch('/sesiones/maquina')).json();
    if(!m.ok) return;
    const gb = x => (x/1024).toFixed(1);
    const b = document.getElementById('cifMaq');
    b.textContent = gb(m.mb_libres) + ' GB';
    // ⚠ Estar apretado de memoria NO es un error: es el sistema haciendo su trabajo. Va
    // en el acento, no en rojo (regla de Martin: el rojo es SOLO para lo que esta mal).
    b.style.color = m.apretado ? 'var(--acento)' : '';
    // Las sueltas se SUMAN a la cuenta de abajo: son procesos igual de reales y ocupan
    // igual. Decir solo las que el panel maneja es lo que hacia que el medidor marcara
    // "0 prendidas" con 3,4 GB tomados despues de cada reinicio.
    document.getElementById('cifMaqSub').textContent =
      (m.prendidas + (m.sueltas||0)) === 1 ? '1 sesion prendida'
                                           : (m.prendidas + (m.sueltas||0)) + ' sesiones prendidas';
    document.getElementById('cifMaqCaja').title =
      'Libres: ' + gb(m.mb_libres) + ' GB (por debajo de ' + gb(m.colchon) +
      ' GB se duermen solas)\\nLas sesiones ocupan ' + gb(m.mb_sesiones) + ' GB' +
      ((m.sesiones||[]).length ? '\\n' + m.sesiones.map(s =>
        '  ' + s.proyecto + ' ' + s.sid + ': ' + s.mb + ' MB' +
        (s.trabajando ? ' (trabajando)' : '')).join('\\n') : '') +
      (m.sueltas ? '\\n\\n' + m.sueltas + ' de antes de reiniciar el panel (' +
        gb(m.mb_sueltas) + ' GB): el boton no las toca porque ahi adentro puede estar' +
        '\\nLaura o la charla que tenes abierta. Se limpian solas al reabrir cada una.' : '');
  }catch(e){}
}
async function soltarMaquina(){
  const btn = document.getElementById('btnSoltar');
  const vuelve = () => { btn.textContent = '💤 Soltar máquina'; btn.disabled = false; };
  btn.disabled = true; btn.textContent = 'soltando...';
  try{
    const r = await (await fetch('/sesiones/liberar', {method:'POST'})).json();
    // Se dice cuantas NO se pudieron dormir: si el boton contestara solo "0 dormidas"
    // pareceria roto, cuando en realidad estaban todas trabajando.
    btn.textContent = '💤 ' + r.dormidas + ' dormidas' +
      (r.ocupadas ? ' · ' + r.ocupadas + ' trabajando' : '');
    verMaquina();
    setTimeout(vuelve, 3000);
  }catch(e){ vuelve(); }
}
verMaquina(); setInterval(verMaquina, 15000);
setInterval(refrescar,2500); setInterval(cargarChat,1500);
// La placa cada 6 s: el `nvidia-smi pmon` del servidor tarda ~1 s y ya viene cacheado
// 4 s ahí adentro — pedirla más seguido sería preguntar de gusto.
pintarPlaca(); setInterval(pintarPlaca,6000);
setInterval(cargarPensando,330);
setInterval(sesRefrescar,10000);
// El contexto de Laura crece con cada cosa que le pedis: se vuelve a mirar cada 20 s
// para que el aviso aparezca solo. Del lado del servidor esto es leer 400 KB del final
// de un archivo, y ni eso mientras la charla no cambie (queda cacheado por su fecha).
setInterval(cargarModelo,20000);
// El contraste son turnos de varios minutos: cada 8 s alcanza y sobra. Mirarlo mas
// seguido no lo hace terminar antes, y son tres sesiones de agente ocupadas.
advPintar(); setInterval(advPintar,8000);
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGINA


@app.get("/status")
def status():
    # ⭐ UNA sola foto para toda la respuesta: antes eran siete barridos de procesos
    # (ver `_barrer`). Ademas de barato, asi los cuatro semaforos y el "encendido"
    # hablan del MISMO instante y no pueden contradecirse entre si.
    foto = _foto()
    esta = {n: len(foto.get(n, [])) > 0 for n in SERVICIOS}
    servicios = {n: {"label": SERVICIOS[n]["label"], "vivo": esta[n]} for n in SERVICIOS}
    return {"servicios": servicios, "encendido": all(esta[n] for n in SERVIDOR),
            "pausado": PAUSA_ESCUCHA.exists(), "mic_permitido": mic_permitido(),
            "leer": leer_en_voz(), "pensando": PENSANDO.exists()}


@app.get("/gasto")
def gasto_de_hoy():
    """Cuanto quemo Claude Code hoy en toda la maquina, para la tarjeta del tablero.

    Sale de las transcripciones de ~/.claude/projects (el `usage` exacto de cada
    llamada). `quema` avisa que la ultima hora viene desbocada: la pantalla lo pinta
    de rojo, y el vigilante ya lo esta gritando al celular por su lado.
    """
    try:
        r = gasto.resumen()
        try:
            codex = gasto.codex_hoy()       # el otro cerebro grande, contado aparte
        except Exception:
            codex = {"hoy": 0, "linda": "0", "charlas": 0}
        # El cupo de la cuenta de Codex (el % usado que el anota en sus rollouts):
        # el mismo dato con el que cerebro_grande se pasa solo a Claude al 90 %.
        try:
            from app.voz import codex_voz
            c = codex_voz.cupo()
            if c and c.get("usado") is not None:
                codex["cupo"] = c["usado"]
                codex["renueva"] = c.get("resets_at")
        except Exception:
            pass
        return {"ok": True, **r, "codex": codex,
                "quema": r.get("ultima_hora", 0) >= QUEMA_ALTA}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/start")
def start():
    for n in SERVIDOR:
        start_one(n)
    return {"ok": True}


@app.post("/stop")
def stop():
    for n in SERVIDOR:
        stop_one(n)
    return {"ok": True}


@app.get("/micros")
def micros():
    """Lista microfonos reales (limpios) + el elegido y el default."""
    import sounddevice as sd
    # PortAudio congela la lista de dispositivos al arrancar el proceso: un micro
    # enchufado DESPUES no aparecia (y los desenchufados seguian figurando).
    # Reinicializar refresca la lista sin tener que reiniciar el panel.
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass
    JUNK = ("sound mapper", "primary sound", "pc speaker", "speakers",
            "@system32", "mapper", "wave")

    def _limpios(solo_wasapi):
        hostapis = sd.query_hostapis()
        out, vistos = [], set()
        for d in sd.query_devices():
            if d["max_input_channels"] <= 0:
                continue
            nm = (d["name"] or "").strip()
            if not nm or nm == "Input ()":
                continue
            if any(j in nm.lower() for j in JUNK):
                continue
            if solo_wasapi and "wasapi" not in hostapis[d["hostapi"]]["name"].lower():
                continue
            if nm in vistos:
                continue
            vistos.add(nm)
            out.append(nm)
        return out

    try:
        lista = _limpios(True) or _limpios(False)
    except Exception:
        lista = []

    default_name = None
    try:
        di = sd.default.device[0]
        if di is not None:
            default_name = sd.query_devices(di)["name"]
    except Exception:
        pass
    sel = None
    try:
        sel = json.loads(CONFIG_DICTADO.read_text(encoding="utf-8")).get("microfono")
    except Exception:
        pass
    return {"microfonos": lista, "seleccionado": sel, "default": default_name}


# Las fotos que le mandas viajan como una MARCA de texto con la ruta adentro
# ("[Te paso una imagen...; esta guardada en C:\... ] lo que escribiste"), porque eso
# es lo que Laura necesita para abrirla con Read. Pero en la burbuja eso es ilegible:
# tapaba tu mensaje con una ruta larguisima. Aca se saca la marca, se deja tu texto
# solo y la imagen se muestra de verdad.
#
# OJO: la busqueda NO va anclada al principio. Cuando lo estaba, cualquier cosa
# delante de la marca (un "[leer]" de diagnostico que duro media hora) hacia que no
# matcheara y la ruta entera aparecia en pantalla.
# El separador es el guion LARGO con espacios alrededor, no un guion cualquiera: la
# ruta tiene guiones adentro ("wpp-transcriptor") y con `[—-]` la captura cortaba ahi
# y devolvia "D:\IA\wpp" como nombre de archivo.
_MARCA_IMAGEN = re.compile(
    r"\[Te (?:paso|mande)[^\]]*?guardad[ao]s? en\s+(.+?)\s+[—–-]\s+[^\]]*\]\s*")


def _partir_imagen(texto):
    """Devuelve (texto sin la marca, lista de nombres de archivo).

    Pueden venir varias en un mismo mensaje, separadas por coma.
    """
    m = _MARCA_IMAGEN.search(texto)
    if not m:
        return texto, []
    nombres = [Path(r.strip()).name for r in m.group(1).split(",") if r.strip()]
    return (texto[:m.start()] + texto[m.end():]).strip(), nombres


def _burbuja_tuya(texto, prefijo=""):
    """Burbuja de un mensaje tuyo, con sus imagenes aparte si venian."""
    txt, nombres = _partir_imagen(texto)
    it = {"t": "vos", "x": (prefijo + txt).strip()}
    servibles = [n for n in nombres if (IMAGENES_CHAT / n).exists()]
    if servibles:
        it["imgs"] = [f"/chat/imagen/{n}" for n in servibles]
    elif nombres:
        it["x"] = (prefijo + "📎 " + txt).strip()    # la foto no la sirvo (vino de Telegram)
    return it


@app.get("/chat/imagen/{nombre}")
def chat_imagen(nombre: str):
    """Sirve una imagen del chat. Solo por nombre y solo de esa carpeta."""
    f = IMAGENES_CHAT / Path(nombre).name          # .name corta cualquier ../
    if not f.exists():
        return {"error": "no esta"}
    return FileResponse(str(f))


# Hora de cada mensaje del chat. El log de la voz no la escribe (son prints sueltos
# y cambiarlos rompería los parsers), así que la anota el panel la primera vez que ve
# la línea. Se guarda en disco para que sobreviva a reiniciar el panel; lo escrito
# antes de esto no tiene hora y se muestra sin ella (2026-08-16).
_HORAS_CHAT = {}
_HORAS_ARCH = LOGS / "horas_chat.json"
try:
    _HORAS_CHAT = json.loads(_HORAS_ARCH.read_text(encoding="utf-8"))
except Exception:
    _HORAS_CHAT = {}
_HORAS_SUCIO = [False]


def _hora_de(linea):
    """La hora en que apareció esa línea. La primera vez que se ve, es ahora."""
    clave = str(hash(linea) & 0xFFFFFFFF)
    if clave not in _HORAS_CHAT:
        _HORAS_CHAT[clave] = time.strftime("%H:%M")
        _HORAS_SUCIO[0] = True
        if len(_HORAS_CHAT) > 4000:          # no crecer para siempre
            for k in list(_HORAS_CHAT)[:2000]:
                _HORAS_CHAT.pop(k, None)
    return _HORAS_CHAT[clave]


def _quien_laura(cerebro):
    """El nombre para la burbuja: "Laura" a secas, o "Laura · Codex" si penso el otro.

    Con el cerebro de siempre no se aclara nada (seria ruido en cada burbuja); solo
    se marca cuando NO es el de defecto, que es justo lo que uno quiere notar.
    """
    try:
        from app.voz import cerebro_grande
        if cerebro and cerebro in cerebro_grande.CEREBROS and cerebro != cerebro_grande.DEFECTO:
            return "Laura · " + cerebro_grande.como_se_llama(cerebro)
    except Exception:
        pass
    return "Laura"


@app.get("/chat")
def chat():
    """Conversacion en vivo: parsea el log de voz en burbujas (vos / ella / eventos)."""
    try:
        lineas = (LOGS / "voz.log").read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    except Exception:
        return {"items": []}
    items = []
    # Con que cerebro grande contesto cada respuesta. Se sabe por la marca que deja
    # `cerebro_grande.preguntar` en el log; vale hasta que aparezca la siguiente.
    # Sin esto, leias el historial y no sabias si te contesto Claude o Codex.
    cerebro = ""
    for ln in lineas:
        ln = ln.strip()
        hora = _hora_de(ln) if ln else ""
        if ln.startswith("cerebro turno: "):
            cerebro = ln[len("cerebro turno: "):].strip()
            continue                       # es una marca, no una burbuja
        if ln.startswith("comando: "):
            items.append({"t": "vos", "x": ln[9:]})
        elif ln.startswith("dictado: "):
            items.append({"t": "vos", "x": "(dictado) " + ln[9:]})
        elif ln.startswith("respuesta: "):
            items.append({"t": "ia", "q": "Venus", "x": ln[11:]})
        elif ln.startswith("claude respuesta: "):
            items.append({"t": "ia", "q": _quien_laura(cerebro), "x": ln[18:]})
        elif ln.startswith("aviso sistema: "):
            # Aviso que sale por iniciativa propia (cupo de tokens), sin que le hables.
            # Lo escribe _avisar_sistema() en app/voz/voz.py.
            items.append({"t": "ia", "q": "Sistema", "x": ln[15:]})
        elif ln.startswith("lectura respuesta ["):
            # Respuesta de una sesion de Claude Code leida por la lectura automatica.
            quien, _, txt = ln[len("lectura respuesta ["):].partition("]: ")
            items.append({"t": "ia", "q": quien or "Lectura", "x": txt})
        elif ln.startswith("telegram pregunta: "):
            # Laura por Telegram (el buzon): lo que escribiste desde el telefono...
            items.append(_burbuja_tuya(ln[len("telegram pregunta: "):], "(telegram) "))
        elif ln.startswith("telegram respuesta: "):
            # ...y lo que Laura contesto. Misma Laura, mismo color violeta.
            items.append({"t": "ia", "q": _quien_laura(cerebro), "x": ln[len("telegram respuesta: "):]})
        elif ln.startswith("panel pregunta: "):
            # Lo que escribiste en la caja de texto de abajo del chat.
            items.append(_burbuja_tuya(ln[len("panel pregunta: "):]))
        elif ln.startswith("panel respuesta: "):
            items.append({"t": "ia", "q": _quien_laura(cerebro), "x": ln[len("panel respuesta: "):]})
        elif ln.startswith("llamada dicho: "):
            # Lo que le dijiste por el boton 🎙 del panel o por la pagina del
            # celular. Sin estos dos prefijos, hablarle desde el panel no dejaba
            # NINGUN rastro en el chat del panel: la oias contestar y la burbuja
            # no aparecia nunca.
            items.append({"t": "vos", "x": "(hablado) " + ln[len("llamada dicho: "):]})
        elif ln.startswith("llamada respuesta: "):
            items.append({"t": "ia", "q": _quien_laura(cerebro), "x": ln[len("llamada respuesta: "):]})
        elif ln.startswith("corte: "):
            items.append({"t": "info", "x": "cortada desde el panel"})
        elif ln.startswith("lectura: "):
            items.append({"t": "info", "x": ln[9:]})
        elif ln.startswith("wake word ->"):
            modo = ln.split("->")[-1].strip()
            quien = "Laura" if modo == "claude" else "Venus"
            items.append({"t": "info", "x": f"escuchando a {quien}..."})
        elif ln.startswith("web task:"):
            items.append({"t": "info", "x": "controlando el navegador..."})
        elif ln.startswith("claude:") and "interrupt enviado" in ln:
            items.append({"t": "info", "x": "cortada a mitad de respuesta"})
        elif "MICRO MUERTO" in ln:
            items.append({"t": "info", "x": "micro sin señal, cambiando..."})
        elif "MICRO RECUPERADO" in ln:
            items.append({"t": "info", "x": "micro recuperado"})
        if len(items) and "h" not in items[-1]:
            items[-1]["h"] = hora          # la línea que acabamos de agregar
    if _HORAS_SUCIO[0]:
        try:
            _HORAS_ARCH.write_text(json.dumps(_HORAS_CHAT), encoding="utf-8")
            _HORAS_SUCIO[0] = False
        except Exception:
            pass
    # eventos repetidos seguidos ("escuchando a Venus..." x5) -> uno solo
    depurados = []
    for it in items:
        if depurados and it["t"] == "info" and depurados[-1] == it:
            continue
        depurados.append(it)
    return {"items": depurados[-60:]}


# --- Pizarra: notas y pines que Laura deja por voz -------------------------------
# v1 (2026-08-14): solo notas y pines, sin figuras. Estado en PIZARRA_ESTADO (JSON
# plano, sin base de datos: alcanza para un tablero de un solo usuario). Todavia no
# esta conectado al pipeline de voz en vivo -- hoy se agrega llamando a /pizarra/agregar
# a mano o desde una sesion de Claude Code; falta el patron en acciones.py que
# reconozca "anota en la pizarra..." y llame a este mismo endpoint.
COLORES_NOTA = ["#fff3a0", "#a8e6a1", "#a0d8ef", "#f5b8d0", "#ffcf9e"]
FIGURAS = {"linea", "flecha", "rectangulo", "circulo", "imagen"}   # tipos con x1,y1,x2,y2 en vez de x,y
TRAZOS = {"lapiz"}   # dibujo libre: van con una lista de puntos en vez de x,y o x1,y1,x2,y2
# Propiedades de texto (tipografia, tamano, negrita, cursiva, alineacion, color): valen
# para el texto suelto y para el que va adentro de una figura.
# ⭐ `colorTexto` es aparte de `color` (que en una figura es el trazo/relleno y en una
# nota es el papelito): puede ser un color a mano, "auto" (el opuesto de lo que tiene
# atras, como el texto de Instagram) o "" para volver al de siempre.
CAMPOS_TEXTO = ("fuente", "tamano", "negrita", "cursiva", "alineacion", "colorTexto")


# ⚠ TODAS las modificaciones (cargar-tocar-guardar) van con este candado. Los
# endpoints sync corren en un threadpool: dos borrados simultaneos leian la misma
# lista, y peor, uno llego a leer el archivo A MEDIO ESCRIBIR, parseo mal, cayo
# al default {"items":[]} y GUARDO ESO -- la pizarra entera se vacio sola
# (paso de verdad el 2026-08-14, borrando 10 items seleccionados de un saque).
_PIZARRA_CANDADO = threading.Lock()


def _pizarra_cargar():
    try:
        return json.loads(PIZARRA_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}


def _pizarra_guardar(estado):
    # Escritura atomica: temporal + replace. Nadie puede leer un JSON a medias.
    tmp = PIZARRA_ESTADO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PIZARRA_ESTADO)


PAGINA_PIZARRA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><title>Pizarra</title>
<style>
 :root{color-scheme:dark}
 *{box-sizing:border-box;font-family:Segoe UI,system-ui,sans-serif}
 html,body{height:100%}
 body{margin:0;background:var(--c0b0d12,#0b0d12);color:var(--ce8eaed,#e8eaed)}
 header{display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--c151920,#151920);
        border-bottom:1px solid var(--c232a35,#232a35);position:relative;z-index:5}
 header h1{font-size:16px;margin:0}
 #menuPantallas{margin-left:auto}
 header span{font-size:12px;color:var(--c7d8592,#7d8592)}
 header button{padding:6px 12px;border-radius:8px;border:1px solid var(--c333b49,#333b49);background:var(--c181d26,#181d26);
               color:var(--ccdd3dc,#cdd3dc);cursor:pointer;font-size:12px}
 header button:hover{background:var(--c1f2530,#1f2530)}
 header button.armado{background:var(--c5eb8ff,#5eb8ff);color:var(--c04141f,#04141f);border-color:var(--c5eb8ff,#5eb8ff)}
 /* Barra de herramientas SIEMPRE visible a la izquierda (pedido de Martin):
    ya no se despliega ni se esconde. Con scroll propio por si no entra a lo alto. */
 /* Barra COMPACTA: solo iconos en una columna angosta, el nombre aparece en el
    tooltip del navegador. Ocupa ~44px de ancho en vez de ~200px. */
 /* ⭐ La barra de herramientas se pinta con `--piz-barra` si Martin le eligio un color
   (2026-08-29); si no, con el fondo de siempre. El segundo argumento de var() es
   justamente el "como estaba". */
#toolbar{position:absolute;top:52px;left:10px;z-index:5;
          background:var(--piz-barra,var(--fondo2));
          border:1px solid var(--c232a35,#232a35);border-radius:10px;padding:5px;display:flex;
          flex-direction:column;gap:2px;box-shadow:var(--sombra-2);
          max-height:calc(100vh - 110px);overflow-y:auto;align-items:center}
 #toolbar button{display:flex;align-items:center;justify-content:center;
                 width:30px;height:30px;padding:0;border-radius:7px;
                 border:1px solid transparent;background:transparent;color:var(--ccdd3dc,#cdd3dc);
                 cursor:pointer;font-size:14px;line-height:1}
 #toolbar button:hover{background:var(--c1f2530,#1f2530)}
 #toolbar button.armado{background:var(--c5eb8ff,#5eb8ff);color:var(--c04141f,#04141f)}
 /* Papelera, candado y deshacer viven SIEMPRE en el mismo lugar de la barra,
    apagados cuando no aplican: si aparecieran y desaparecieran, los demas botones
    se correrian bajo el dedo. Van ANTES de las herramientas de dibujo para que en
    el telefono se vean sin correr la barra. En el telefono son el UNICO camino:
    borrar estaba enterrado abajo del panel de propiedades, y desbloquear y
    deshacer vivian solo en el menu del clic derecho, que no existe al tocar. */
 #toolbar button.apagado{opacity:.28;pointer-events:none}
 /* El plegador es solo del telefono: en la compu la barra es una columna angosta a un
    costado y no molesta a nadie. */
 /* ⚠ Van con `#toolbar` adelante a proposito: `#toolbar button{display:flex}` es mas
    especifico que un `#id` solo, asi que con `#btnPlegar{display:none}` pelado los dos
    botones del telefono se veian igual en la compu (2026-08-17). */
 #toolbar #btnPlegar, #toolbar #btnMulti{display:none;color:var(--c7d8a9b,#7d8a9b)}
 #btnBorrar:hover{background:var(--c3b1e22,#3b1e22);color:var(--cff9d9d,#ff9d9d)}
 #toolbar hr{border:0;border-top:1px solid var(--c232a35,#232a35);margin:2px 0;width:20px}
 /* Los fondos ya no ocupan lugar en la barra: salen en un desplegable al lado. */
 #fondos{position:fixed;display:none;flex-wrap:wrap;gap:5px;width:132px;z-index:8;
         background:var(--c151920,#151920);border:1px solid var(--c232a35,#232a35);border-radius:10px;padding:8px;
         box-shadow:var(--sombra-2)}
 #fondos.abierto{display:flex}
 #fondos div{width:22px;height:22px;border-radius:6px;cursor:pointer;
             border:1px solid rgba(var(--cffffff-rgb,255,255,255),.25);transition:transform .1s;
             display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--ccdd3dc,#cdd3dc)}
 #fondos div:hover{transform:scale(1.15)}
 #tablero{position:relative;width:100%;height:calc(100vh - 47px);overflow:hidden;
          background-image:radial-gradient(var(--c1a1f28,#1a1f28) 1px,transparent 1px);background-size:24px 24px;
          cursor:default}
 #tablero.armando{cursor:crosshair}
 #capa{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
 /* ⚠ Segunda capa SVG, ARRIBA de las notas. Las bandas de borde viven aca y no
    en #capa: las notas, pines y textos son divs de HTML que se dibujan encima
    del SVG, asi que la banda de una nota quedaba tapada por la nota misma y el
    borde no se podia agarrar (justo en el objeto que Martin mas usa). */
 #capaAlta{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:4}
 .forma{cursor:move}
 .forma:active{cursor:move}
 .forma-tapa{fill:#00000001;stroke:#00000001;pointer-events:all}
 .item{position:absolute;transform:translate(-50%,-50%);user-select:none;cursor:move}
 .item:active{cursor:move}
 /* Ya no hay cruz de borrar: se borra con clic derecho o con Supr (pedido de
    Martin, 2026-08-14 — la crucecita aparecia todo el tiempo y molestaba). */
 /* Panel de propiedades fijo (island estilo Excalidraw): aparece al seleccionar
    algo, arriba a la derecha. Reemplaza a los botoncitos flotantes de color por
    figura, que se chocaban contra los objetos y eran incomodos de apuntar. */
 /* Oculta por defecto; se muestra con la clase `visible` (ver refrescarPanel). */
 #panelProps{position:absolute;top:52px;right:12px;z-index:6;display:none;
             flex-direction:column;gap:8px;background:var(--c151920,#151920);border:1px solid var(--c232a35,#232a35);
             border-radius:12px;padding:10px;box-shadow:var(--sombra-1);width:136px}
 /* La cabecera con el plegador es SOLO del telefono: en la compu el panel es una
    columna angosta al costado y no tapa nada. */
 #propsCabecera{display:none}
 #panelProps.visible{display:flex}
 /* En la compu el envoltorio de cada seccion no existe para el dibujo: la hoja se
    ve exactamente igual que siempre. En el telefono es la unidad que se muestra. */
 #panelProps .grupo{display:contents}
 #chipsProps{display:none}
 #panelProps .titulo{font-size:11px;color:var(--c7d8592,#7d8592)}
 #panelProps .fila{display:flex;flex-wrap:wrap;gap:6px}
 #panelProps .sw{width:22px;height:22px;border-radius:6px;cursor:pointer;
                 border:1px solid rgba(var(--cffffff-rgb,255,255,255),.18);transition:transform .1s}
 #panelProps .sw:hover{transform:scale(1.12)}
 #panelProps .sw.activo{box-shadow:0 0 0 2px var(--c6965db,#6965db), 0 0 0 3px var(--c151920,#151920)}
 #panelProps .accion{flex:1;display:flex;align-items:center;justify-content:center;
                 height:30px;border-radius:8px;border:1px solid var(--c333b49,#333b49);background:var(--c181d26,#181d26);
                 color:var(--ccdd3dc,#cdd3dc);cursor:pointer;font-size:14px}
 #panelProps .accion:hover{background:var(--c1f2530,#1f2530)}
 /* La opcion elegida queda marcada (violeta), como en Excalidraw. */
 #panelProps .accion.activo{background:var(--ce0dfff,#e0dfff);color:var(--c030064,#030064);border-color:var(--c4440bf,#4440bf)}
 #panelProps input[type=number]{flex:1;height:28px;border-radius:8px;border:1px solid var(--c333b49,#333b49);
                 background:var(--c181d26,#181d26);color:var(--ccdd3dc,#cdd3dc);font-size:12px;padding:0 8px;width:100%}
 /* Tiradores estilo Excalidraw: cuadrado 8x8, blanco, borde violeta, radio 2px.
    SOLO se ven con el objeto seleccionado (clase .visible que pone pintarSeleccion):
    antes estaban siempre a la vista y ensuciaban la pizarra. */
 /* ⚠ z-index arriba de los puntitos de conexion: en una linea, las manijas de las
    puntas caen JUSTO donde estan sus conectores, y si gana el conector no se
    puede volver a estirar la linea. Sin seleccionar, la manija no recibe clics
    (pointer-events:none) y manda el conector, que es lo que se quiere. */
 .forma-manija{position:absolute;width:8px;height:8px;border-radius:2px;background:#fff;
               border:1px solid var(--c6965db,#6965db);transform:translate(-50%,-50%);cursor:nwse-resize;
               pointer-events:none;opacity:0;transition:opacity .15s;z-index:5}
 .forma-manija.visible{opacity:1;pointer-events:auto}
 .forma-rotor{position:absolute;width:10px;height:10px;border-radius:50%;background:#fff;
              border:1px solid var(--c6965db,#6965db);transform:translate(-50%,-50%);cursor:grab;
              pointer-events:none;opacity:0;transition:opacity .15s;z-index:5}
 .forma-rotor.visible{opacity:1;pointer-events:auto}
 /* ⭐ Asa de MOVER (pedido de Martin, 2026-08-17): un tirador dedicado, abajo del
    objeto y afuera, para agarrarlo y correrlo sin pelear con el borde conectable.
    Espeja al rotor, que va arriba. Aparece con el objeto seleccionado. */
 .asa-mover{position:absolute;width:20px;height:20px;border-radius:50%;
            background:var(--c5eb8ff,#5eb8ff);color:var(--c04141f,#04141f);border:2px solid var(--c0b0d12,#0b0d12);
            transform:translate(-50%,-50%);cursor:move;display:flex;
            align-items:center;justify-content:center;font-size:12px;line-height:1;
            pointer-events:none;opacity:0;transition:opacity .15s;z-index:5}
 .asa-mover.visible{opacity:1;pointer-events:auto}
 @media (pointer:coarse){ .asa-mover{width:30px;height:30px;font-size:17px} }
 /* Puntitos de conexion (estilo draw.io): aparecen al pasar el mouse por una
    figura; arrastrar desde uno lanza una flecha que se engancha al destino. */
 /* ⚠ Apagado NO recibe clics. Antes era pointer-events:auto siempre: los 4
    puntitos de CADA objeto quedaban invisibles pero clickeables, robando el clic
    en el medio de cada lado de todo lo que hubiera en la pizarra. */
 .conector{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--c6abdfc,#6abdfc);
           border:2px solid var(--c0b0d12,#0b0d12);transform:translate(-50%,-50%);cursor:crosshair;
           pointer-events:none;opacity:0;transition:opacity .15s;z-index:4}
 .conector.activo{opacity:1;pointer-events:auto}
 /* El contorno ENTERO conecta: una banda gruesa pegada al borde, de la que se
    tira una flecha desde cualquier punto. ⚠ Apagada va pintada con #00000001
    (invisible pero PINTADA), no con "transparent" ni "none": un clic de verdad
    no le llega a lo que no esta pintado — la misma piedra de .forma-tapa. */
 .borde-conector{stroke:#00000001;pointer-events:none;transition:stroke .15s}
 .borde-conector.activo{stroke:rgba(var(--c6abdfc-rgb,106,189,252),.4);pointer-events:stroke;cursor:crosshair}
 /* --- Recortar una imagen. La original queda en fantasma y lo que se conserva se
    ve a pleno: asi se entiende de un vistazo que lo de afuera no se borra, se
    esconde, y que se puede volver a agrandar el recorte. Las esquinas son mas
    grandes que las manijas normales (22 px con el dedo, 12 con el mouse): es la
    unica manija que se arrastra sin poder apuntar fino. */
 /* ⚠ pointer-events:all en las dos que se agarran: #capa (el SVG) lo tiene en
    "none" y se hereda, asi que sin esto las esquinas y el centro del recorte no
    reciben ni el mouse ni el dedo. Es lo mismo que hace .forma-tapa. */
 .recorte-fantasma{opacity:.28}
 .recorte-borde{fill:none;stroke:#fff;stroke-width:1.5;stroke-dasharray:6 4;pointer-events:none}
 .recorte-adentro{fill:#00000001;cursor:move;pointer-events:all}
 .recorte-esq{fill:#fff;stroke:var(--c6965db,#6965db);stroke-width:1.5;pointer-events:all}
 /* La imagen de verdad se esconde mientras se recorta: abajo del fantasma se
    seguiria viendo el recorte VIEJO a pleno y no se entenderia nada. */
 .recorte-oculto{display:none}
 /* Recortando no molestan los tiradores de tamano, el rotor ni los conectores. */
 #tablero.recortando .forma-manija,
 #tablero.recortando .forma-rotor,
 #tablero.recortando .conector{display:none}
 #barraRecorte{position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:9;
               display:none;align-items:center;gap:8px;background:var(--c151920,#151920);
               border:1px solid var(--c232a35,#232a35);border-radius:10px;padding:7px 10px;
               box-shadow:var(--sombra-2)}
 #barraRecorte.abierto{display:flex}
 #barraRecorte span{font-size:12px;color:var(--c7d8592,#7d8592);padding:0 4px}
 #barraRecorte button{padding:7px 12px;border-radius:8px;border:1px solid var(--c333b49,#333b49);
                      background:var(--c181d26,#181d26);color:var(--ccdd3dc,#cdd3dc);cursor:pointer;font-size:12.5px}
 #barraRecorte button:hover{background:var(--c1f2530,#1f2530)}
 #barraRecorte button.ok{background:var(--c5eb8ff,#5eb8ff);color:var(--c04141f,#04141f);border-color:var(--c5eb8ff,#5eb8ff);font-weight:600}
 .menuCtx{position:absolute;z-index:9;background:var(--c151920,#151920);border:1px solid var(--c232a35,#232a35);border-radius:10px;
          padding:6px 0;box-shadow:var(--sombra-2);min-width:170px}
 .menuCtx div{padding:7px 16px;font-size:12.5px;color:var(--ccdd3dc,#cdd3dc);cursor:pointer}
 .menuCtx div:hover{background:var(--c1f2530,#1f2530)}
 .resize{position:absolute;bottom:-7px;right:-7px;width:8px;height:8px;border-radius:2px;
         background:#fff;border:1px solid var(--c6965db,#6965db);cursor:nwse-resize;opacity:0;
         pointer-events:none;transition:.15s}
 .item.seleccionado .resize{opacity:1;pointer-events:auto}
 .nota{min-width:140px;max-width:220px;padding:10px 12px;border-radius:8px;
       box-shadow:var(--sombra-1);color:var(--c1a1a1a,#1a1a1a);font-size:14px;line-height:1.35}
 .nota .txt{outline:none;cursor:text;white-space:pre-wrap;overflow-wrap:break-word}
 .nota .txt:focus{cursor:text;box-shadow:inset 0 0 0 1px rgba(0,0,0,.25);border-radius:3px}
 .pin{display:flex;flex-direction:column;align-items:center;gap:4px}
 .pin .punto{width:16px;height:16px;border-radius:50%;box-shadow:0 0 0 3px rgba(var(--cffffff-rgb,255,255,255),.12)}
 .pin .etiqueta{background:var(--c151920,#151920);border:1px solid var(--c232a35,#232a35);padding:3px 8px;border-radius:10px;
                font-size:12px;white-space:nowrap;color:var(--ce8eaed,#e8eaed);outline:none;cursor:text}
 .pin .etiqueta:focus{box-shadow:inset 0 0 0 1px var(--c4b5563,#4b5563)}
 .fecha{font-size:10px;opacity:.55;margin-top:6px;pointer-events:none}
 .vacio{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
        color:var(--c616977,#616977);font-size:13px;text-align:center;line-height:1.6;pointer-events:none}
 /* Seleccion estilo Excalidraw: violeta var(--c6965db,#6965db), marco solido de 1px con 4px de
    aire; la seleccion multiple suma un marco grupal PUNTEADO (dash 2). Valores
    sacados del codigo real de Excalidraw (theme.scss / interactiveScene.ts). */
 .marquee{position:absolute;border:1px solid var(--c6965db,#6965db);background:rgba(var(--c0000c8-rgb,0,0,200),.04);
          pointer-events:none;z-index:4}
 .item.seleccionado{outline:1px solid var(--c6965db,#6965db);outline-offset:4px}
 /* Bloqueado: se ve el candadito y el cursor deja claro que no se arrastra. */
 .item.bloqueado, .forma-wrap.bloqueado .forma{cursor:not-allowed}
 /* Bloqueado: el objeto queda INTOCABLE (pointer-events:none) y lo unico
    clickeable es su etiqueta con nombre, que aparece arriba. */
 /* El objeto bloqueado es TRANSPARENTE AL MOUSE: un rectangulo bloqueado de
    fondo no roba clics, se puede seleccionar lo que esta encima y arrastrar el
    recuadro por arriba. La regla de la tapa es mas especifica y hay que pisarla. */
 .item.bloqueado{pointer-events:none}
 .forma-wrap.bloqueado, .forma-wrap.bloqueado .forma,
 .forma-wrap.bloqueado .forma-tapa{pointer-events:none}
 .item.bloqueado.seleccionado{outline-style:dashed}
 .etiqueta-bloqueo{position:absolute;transform:translate(-50%,-100%);z-index:5;
                   background:var(--c151920,#151920);border:1px solid var(--c333b49,#333b49);border-radius:8px;
                   padding:2px 8px;font-size:11.5px;color:var(--caab2c0,#aab2c0);white-space:nowrap;
                   cursor:pointer;pointer-events:auto;user-select:none}
 .etiqueta-bloqueo:hover{background:var(--c1f2530,#1f2530);color:var(--ce8eaed,#e8eaed)}
 .etiqueta-bloqueo.seleccionada{border-color:var(--c6965db,#6965db);color:var(--ce8eaed,#e8eaed)}
 .etiqueta-bloqueo[contenteditable="true"]{cursor:text;outline:none;
                   box-shadow:inset 0 0 0 1px rgba(var(--c6965db-rgb,105,101,219),.7)}
 .forma-wrap.bloqueado.seleccionado .forma{filter:drop-shadow(0 0 1.5px var(--caab2c0,#aab2c0))}
 .forma-wrap.seleccionado .forma{filter:drop-shadow(0 0 1.5px var(--c6965db,#6965db))}
 #marcoGrupo{position:absolute;border:1px dashed var(--c6965db,#6965db);pointer-events:none;z-index:3;
             display:none}
 /* Tiradores del marco grupal: agrandan/achican TODA la seleccion a la vez. */
 #marcoGrupo .mg-manija{position:absolute;width:8px;height:8px;border-radius:2px;
             background:#fff;border:1px solid var(--c6965db,#6965db);pointer-events:auto}
 #marcoGrupo .mg-manija[data-esq="nw"]{left:-5px;top:-5px;cursor:nwse-resize}
 #marcoGrupo .mg-manija[data-esq="ne"]{right:-5px;top:-5px;cursor:nesw-resize}
 #marcoGrupo .mg-manija[data-esq="sw"]{left:-5px;bottom:-5px;cursor:nesw-resize}
 #marcoGrupo .mg-manija[data-esq="se"]{right:-5px;bottom:-5px;cursor:nwse-resize}
 #zoomUI{position:absolute;bottom:12px;left:12px;z-index:6;display:flex;align-items:center;
         background:var(--c151920,#151920);border:1px solid var(--c232a35,#232a35);border-radius:10px;overflow:hidden}
 #zoomUI div{padding:8px 12px;cursor:pointer;font-size:13px;color:var(--ccdd3dc,#cdd3dc);user-select:none}
 #zoomUI div:hover{background:var(--c1f2530,#1f2530)}
 #zoomUI .zpct{min-width:54px;text-align:center;font-size:12px;color:var(--c7d8592,#7d8592)}
 /* Texto adentro de una figura (estilo Excalidraw): centrado en las dos
    direcciones, no bloquea el arrastre (pointer-events:none salvo en edicion). */
 .figura-texto{position:absolute;transform:translate(-50%,-50%);color:var(--ce8eaed,#e8eaed);
               font-size:13.5px;line-height:1.25;text-align:center;pointer-events:none;
               max-width:30%;overflow-wrap:break-word;outline:none;z-index:2}
 .figura-texto[contenteditable="true"]{pointer-events:auto;cursor:text;
               box-shadow:inset 0 0 0 1px rgba(var(--c6965db-rgb,105,101,219),.6);border-radius:3px;
               padding:1px 4px;min-width:20px}
 /* Texto suelto: un objeto mas de la pizarra (no va adentro de ninguna figura). */
 .item.texto{background:transparent;box-shadow:none;padding:2px 4px;color:var(--ce8eaed,#e8eaed);
             white-space:pre-wrap;line-height:1.25;max-width:none}
 .item.texto .txt{outline:none;cursor:text;min-width:14px}
 .item.texto .txt:focus{box-shadow:inset 0 0 0 1px rgba(var(--c6965db-rgb,105,101,219),.6);border-radius:3px}
 /* --- Con el dedo (celular y tablet) ---------------------------------------
    ⭐ touch-action:none es lo que hace que la pizarra sea usable en el telefono:
    sin eso el navegador se queda con el gesto (scrollea la pagina, hace zoom de
    TODA la pantalla) y el lienzo nunca lo ve. De paso mata la demora de 300 ms
    del doble toque. Va en el tablero y en todo lo que se arrastra adentro. */
 #tablero, #tablero *{touch-action:none}
 /* el menu de iOS al mantener apretado (copiar/compartir) arruina el arrastre */
 #tablero{-webkit-touch-callout:none}
 body{overscroll-behavior:none}          /* nada de rebote ni "tirar para recargar" */
 /* Los tiradores de 8 px son para el mouse: con el dedo hay que poder agarrarlos. */
 @media (pointer:coarse){
   .forma-manija{width:14px;height:14px} .forma-rotor{width:16px;height:16px}
   .conector{width:14px;height:14px}
 }
 /* --- Telefono: la barra de herramientas va ABAJO, al alcance del pulgar -----
    Arriba a la izquierda hay que estirar la mano y encima tapa el lienzo justo
    donde uno mira. Botones de 44 px, que es el minimo que Apple recomienda para
    tocar sin errar. */
 @media (max-width:700px){
   header{display:none}                  /* el titulo y el "volver" no sirven en el telefono */
   #tablero{height:100dvh}
   /* ⚠ La barra se ENVUELVE en dos filas, no se corre de costado. Con scroll
      horizontal entraban 8 botones y los otros seis —lapiz, linea, flecha,
      rectangulo, circulo y el color— quedaban afuera SIN NINGUNA señal de que
      hubiera mas: Martin pidio poner una imagen desde el telefono, se agrego el 🖼
      y su respuesta fue "yo no veo eso que me decis" (2026-08-17). Una barra que
      esconde la mitad de las herramientas y no lo aparenta es peor que una barra
      de dos renglones. */
   /* ⚠ left+right en vez de left:50% con transform: a un elemento absoluto con solo
      `left` le queda como ancho disponible lo que va DESDE ahí hasta el borde — con
      left:50% eran 195 px y la barra envolvía de a tres botones, en cinco renglones.
      Con los dos lados fijos ocupa el ancho de verdad y entra en dos. */
   #toolbar{top:auto;bottom:calc(10px + env(safe-area-inset-bottom));left:10px;right:10px;
            transform:none;flex-direction:row;flex-wrap:wrap;justify-content:center;
            max-width:none;max-height:none;overflow:visible;padding:5px;gap:3px}
   /* ⚠ 36 px y no 40: con 17 herramientas, 40 px entran de a 8 por renglón y la barra
      se iba a TRES filas, la última con un solo botón. Con 36 entran 9 y quedan dos
      filas parejas (2026-08-17). Si se suma otra herramienta, medir de nuevo.
      ⚠ Medido de nuevo al sumar el 📋 (2026-08-23): son 18 botones = dos filas de 9
      justas. En 390 px de ancho entran 348 de los 360 disponibles; el siguiente botón
      que se agregue tira la barra a tres filas, así que ahí hay que achicarlos. */
   #toolbar button{width:36px;height:36px;font-size:18px;flex:0 0 auto}
   /* Las rayitas separadoras no aportan nada en una barra de dos renglones y comen
      lugar: en el teléfono se van. */
   #toolbar hr{display:none}
   /* Guardar la barra: solo en el teléfono, que es donde tapa el tablero. Plegada
      queda un solo botón, chiquito y contra el borde, para poder volver a abrirla. */
   #toolbar #btnPlegar, #toolbar #btnMulti{display:flex}
   #toolbar.plegado{left:auto;right:10px;padding:4px}
   #toolbar.plegado button:not(#btnPlegar){display:none}
   #toolbar.plegado #btnPlegar{transform:rotate(180deg)}
   /* ⚠ Las propiedades del objeto NO pueden ser la columna angosta del escritorio
      estirada a todo el ancho: asi ocupaba el 65 % de la pantalla del telefono y
      cada boton quedaba del tamaño de una tarjeta. Va como hoja compacta abajo
      (encima de las herramientas, que es donde ya esta la mano) y cada seccion en
      UNA sola linea que se corre con el dedo. */
   /* ⚠ Más alto que antes (36dvh dejaba "Opacidad" cortada al medio y no se veía que
      hubiera scroll) y con la cabecera pegada arriba mientras el resto se corre. */
   /* ⚠ La hoja se apoya SOBRE la barra de herramientas, y la barra mide distinto
      segun este abierta (dos renglones) o guardada: por eso el alto lo mide el JS
      y lo deja en --altoBarra. Con el 64 fijo de antes la hoja se le montaba encima
      y tapaba media barra — Martin: "no me gusta como se sobreponen los menus"
      (2026-08-17). */
   #panelProps{top:auto;bottom:calc(var(--altoBarra,80px) + 18px + env(safe-area-inset-bottom));
               left:8px;right:8px;
               width:auto;max-width:none;max-height:52dvh;overflow-y:auto;
               gap:4px;padding:0 10px 8px}
   /* Con la barra de herramientas guardada, la hoja baja y aprovecha ese lugar. */
   /* ⚠ Cada sección en UN renglón: el nombre a la izquierda y sus botones a la
      derecha, en vez del título arriba y los botones abajo. Apilado en dos pisos, la
      hoja medía más de lo que entra y se cortaba a la mitad de "Capa" — Martín:
      "se ve feo" (2026-08-17). Así baja casi a la mitad y entra entera.
      Es una grilla de dos columnas y el HTML ya viene título/fila alternados, así que
      se emparejan solos; el bloque de texto se convierte en su propia grilla igual. */
   #panelProps.visible{display:grid;grid-template-columns:auto 1fr;align-items:center;
                       column-gap:10px;row-gap:5px}
   #seccionTexto{grid-column:1/-1;display:grid;grid-template-columns:auto 1fr;
                 align-items:center;column-gap:10px;row-gap:5px}
   #panelProps .titulo{font-size:10.5px;white-space:nowrap;text-align:right;opacity:.85}
   #propsOpacidad{width:100%}
   /* La cabecera pasa a ser la fila de pestañitas + el ▾ de guardar. */
   #propsCabecera{grid-column:1/-1;display:flex;align-items:center;gap:8px;
                  position:sticky;top:0;z-index:2;background:var(--c151920,#151920);
                  padding:8px 0 6px;margin-bottom:2px}
   #chipsProps{display:flex;gap:5px;overflow-x:auto;flex:1;min-width:0;
               scrollbar-width:none}
   #chipsProps::-webkit-scrollbar{display:none}
   #chipsProps .chip{flex:0 0 auto;padding:6px 11px;border-radius:9px;background:var(--c1b2130,#1b2130);
                     color:var(--c9aa6b5,#9aa6b5);font-size:12.5px;white-space:nowrap;cursor:pointer}
   #chipsProps .chip.sel{background:var(--c24304a,#24304a);color:var(--ccfe6ff,#cfe6ff)}
   /* Se ve UNA sola seccion: la de la pestañita elegida. */
   #panelProps .grupo{display:none}
   #panelProps .grupo.abierto{grid-column:1/-1;display:grid;
                              grid-template-columns:1fr;align-items:center;
                              column-gap:10px;row-gap:5px}
   /* El nombre de la seccion ya esta en la pestañita: adentro sobra y le come ancho
      a los botones (el bloque de Texto conserva los suyos, que son otros). */
   #panelProps .grupo.abierto > .titulo{display:none}
   /* Con una sola seccion a la vista, la hoja ya no necesita medio celular. */
   #panelProps.visible{max-height:34dvh}
   #btnProps{width:38px;height:30px;border:0;background:var(--c1b2130,#1b2130);color:var(--c9aa6b5,#9aa6b5);
             border-radius:8px;font-size:15px;line-height:1}
   /* ⭐ Plegada se esconde ENTERA: queda un solo boton chiquito contra el borde,
      igual que la barra de herramientas. Antes quedaba toda la fila de pestañitas y
      Martin lo pidio claro: "si aprieto para que se oculte, quiero que se oculte
      completo" (2026-08-17). */
   #panelProps.plegado{left:auto;right:8px;max-height:none;overflow:visible;
                       padding:4px;display:block}
   #panelProps.plegado > *:not(#propsCabecera){display:none}
   #panelProps.plegado #chipsProps{display:none}
   #panelProps.plegado #propsCabecera{padding:0;margin:0}
   /* ⚠ flex:0 0 auto o las filas se APLASTAN a cero: el panel es una columna flex
      con max-height, y al no entrar el contenido los hijos se encogen — la fila de
      colores quedaba de alto 0 y no se veia un solo color. Que no encojan: para
      eso el panel tiene su propio scroll. */
   #panelProps > *{flex:0 0 auto}
   #panelProps .fila{flex-wrap:nowrap;overflow-x:auto;gap:8px;scrollbar-width:none}
   #panelProps .fila::-webkit-scrollbar{display:none}
   #panelProps .sw{width:30px;height:30px;flex:0 0 auto}
   #panelProps .accion{flex:0 0 auto;min-width:44px;height:36px;padding:0 10px}
   #panelProps .titulo{font-size:10px;margin-top:2px}
   #panelProps input[type=number]{flex:0 0 auto;width:70px}
   /* La barra del recorte tambien va abajo, donde ya esta la mano, y no arriba
      contra el zoom. Ocupa el lugar de las propiedades, que recortando se ocultan. */
   #barraRecorte{top:auto;bottom:calc(var(--altoBarra,80px) + 18px + env(safe-area-inset-bottom));
                 left:8px;right:8px;transform:none;justify-content:center;
                 flex-wrap:wrap;gap:6px;padding:8px}
   #barraRecorte button{padding:11px 14px;font-size:14px}
   /* el zoom se va arriba: abajo ya estan las herramientas y las propiedades */
   #zoomUI{top:calc(10px + env(safe-area-inset-top));bottom:auto;left:10px}
   #zoomUI div{padding:10px 14px;font-size:15px}
 }
</style></head><body>
<header>
  <h1>🧷 Pizarra</h1><span id="contador">cargando...</span>
  <nav id="menuPantallas"></nav>
</header>
<script src="/estaticos/menu.js"></script>
<script src="/estaticos/aspecto.js"></script>
<div id="toolbar">
  <button class="herr-btn armado" data-tool="mover" title="Mover / seleccionar" onclick="seleccionarHerramienta(this)">✥</button>
  <button id="btnBorrar" class="apagado" title="Borrar lo seleccionado (Supr)" onclick="borrarSeleccion()">🗑</button>
  <button id="btnDeshacer" class="apagado" title="Deshacer (Ctrl+Z)" onclick="deshacer()">↶</button>
  <button id="btnCandado" class="apagado" title="Bloquear lo seleccionado" onclick="alternarBloqueo()">🔒</button>
  <button id="btnRecortar" class="apagado" title="Recortar la imagen (doble clic sobre ella)" onclick="entrarRecorte()">✂</button>
  <!-- Guardar como imagen (pedido de Martin, 2026-08-23). En el telefono copiar al
       portapapeles no sirve de mucho —no hay Ctrl+V para pegarlo de vuelta— y lo que
       pidio es que la foto le quede EN EL CELULAR: este boton abre la hoja de
       compartir de iOS, donde estan "Guardar imagen" (va al carrete), Copiar y
       WhatsApp. En la compu baja el archivo directamente. -->
  <button id="btnFoto" title="Guardar como imagen: lo elegido, o toda la pizarra"
          onclick="guardarComoFoto(this)">📋</button>
  <!-- Elegir varios objetos CON EL DEDO: con el mouse alcanza con arrastrar sobre el
       fondo, pero en el telefono ese gesto corre el lienzo y no habia ninguna forma
       de seleccionar mas de uno (pedido de Martin, 2026-08-17). Solo en el telefono. -->
  <button id="btnMulti" title="Elegir varios: arrastrá un recuadro" onclick="modoMulti()">⬚</button>
  <hr>
  <button class="herr-btn" data-tool="nota" title="Nota" onclick="seleccionarHerramienta(this)">📝</button>
  <button class="herr-btn" data-tool="texto" title="Texto" onclick="seleccionarHerramienta(this)">🅣</button>
  <!-- Desde el telefono no hay Ctrl+V, asi que sin este boton no habia NINGUNA forma
       de meter una captura en la pizarra (pregunta de Martin, 2026-08-17). Abre la
       galeria, la camara o los archivos: lo decide iOS. Va con las otras herramientas
       de INSERTAR (nota, texto, pin), que es lo que uno busca cuando quiere meter algo. -->
  <button id="btnImagen" title="Poner una imagen: foto, captura o archivo"
          onclick="document.getElementById('archImagen').click()">🖼</button>
  <input type="file" id="archImagen" accept="image/*" hidden onchange="elegirImagen(this)">
  <button class="herr-btn" data-tool="pin" title="Pin" onclick="seleccionarHerramienta(this)">📍</button>
  <hr>
  <button class="herr-btn" data-tool="lapiz" title="Lápiz" onclick="seleccionarHerramienta(this)">✏</button>
  <button class="herr-btn" data-tool="linea" title="Línea" onclick="seleccionarHerramienta(this)">─</button>
  <button class="herr-btn" data-tool="flecha" title="Flecha" onclick="seleccionarHerramienta(this)">↗</button>
  <button class="herr-btn" data-tool="rectangulo" title="Rectángulo" onclick="seleccionarHerramienta(this)">▭</button>
  <button class="herr-btn" data-tool="circulo" title="Círculo" onclick="seleccionarHerramienta(this)">○</button>
  <hr>
  <button id="btnFondo" title="Color de fondo del lienzo" onclick="toggleFondos(event)">🎨</button>
  <!-- Guardar la barra: en el telefono ocupa dos renglones y tapa el tablero. Se pliega
       a un solo boton y se acuerda de como la dejaste (pedido de Martin, 2026-08-17). -->
  <button id="btnPlegar" title="Guardar la barra de herramientas"
          onclick="plegarBarra()">▾</button>
  <div id="fondos"></div>
</div>
<div id="tablero"><svg id="capa">
  <line id="guiaV" stroke="#ff6b6b" stroke-width="1" style="display:none"/>
  <line id="guiaH" stroke="#ff6b6b" stroke-width="1" style="display:none"/>
</svg><svg id="capaAlta"></svg><div id="marcoGrupo">
  <div class="mg-manija" data-esq="nw"></div>
  <div class="mg-manija" data-esq="ne"></div>
  <div class="mg-manija" data-esq="sw"></div>
  <div class="mg-manija" data-esq="se"></div>
</div>
<div id="barraRecorte">
  <span>Recortando</span>
  <button onclick="recorteEntero()">Toda la imagen</button>
  <button onclick="salirRecorte(false)">Cancelar</button>
  <button class="ok" onclick="salirRecorte(true)">Listo</button>
</div>
<div id="panelProps">
  <!-- Guardar las propiedades: en el telefono la hoja tapa medio tablero y ademas se ve
       cortada abajo. Con el ▾ queda una tira fina y se abre de vuelta cuando la
       necesitas (pedido de Martin, 2026-08-17). Solo se muestra en el telefono. -->
  <div id="propsCabecera">
    <div id="chipsProps"></div>
    <button id="btnProps" title="Guardar las propiedades" onclick="plegarProps()">▾</button>
  </div>
  <div class="titulo">Color</div>
  <div class="fila" id="propsColores"></div>
  <div class="titulo" data-sec="punta">Punta</div>
  <div class="fila" data-campo="punta">
    <div class="accion" data-valor="lapiz" title="Lápiz">✏</div>
    <div class="accion" data-valor="birome" title="Birome">🖊</div>
    <div class="accion" data-valor="fibra" title="Fibra">🖍</div>
    <div class="accion" data-valor="resaltador" title="Resaltador">🖌</div>
  </div>
  <div class="titulo" data-sec="grosor">Grosor</div>
  <div class="fila" data-campo="grosor">
    <div class="accion" data-valor="1" title="Fino">─</div>
    <div class="accion" data-valor="2" title="Medio">━</div>
    <div class="accion" data-valor="4" title="Grueso">▬</div>
  </div>
  <div class="titulo" data-sec="trazo">Trazo</div>
  <div class="fila" data-campo="lineaEstilo">
    <div class="accion" data-valor="solido" title="Sólido">—</div>
    <div class="accion" data-valor="rayado" title="Rayado">╌</div>
    <div class="accion" data-valor="punteado" title="Punteado">┄</div>
  </div>
  <div class="titulo" data-sec="relleno">Relleno</div>
  <div class="fila" data-campo="relleno">
    <div class="accion" data-valor="ninguno" title="Sin relleno">□</div>
    <div class="accion" data-valor="hachura" title="Rayitas">▨</div>
    <div class="accion" data-valor="solido" title="Sólido">■</div>
  </div>
  <div class="titulo">Opacidad</div>
  <input type="range" id="propsOpacidad" min="10" max="100" step="10" value="100">
  <div id="seccionTexto">
    <div class="titulo">Tipografía</div>
    <div class="fila" data-campo="fuente">
      <div class="accion" data-valor="manuscrita" title="Manuscrita" style="font-family:'Segoe Script','Comic Sans MS',cursive">Aa</div>
      <div class="accion" data-valor="palo" title="Palo seco" style="font-family:'Segoe UI',system-ui,sans-serif">Aa</div>
      <div class="accion" data-valor="mono" title="Monoespaciada" style="font-family:Consolas,monospace">Aa</div>
    </div>
    <div class="titulo">Tamaño</div>
    <div class="fila" data-campo="tamano">
      <div class="accion" data-valor="14" title="Chico">S</div>
      <div class="accion" data-valor="20" title="Mediano">M</div>
      <div class="accion" data-valor="28" title="Grande">L</div>
      <div class="accion" data-valor="38" title="Enorme">XL</div>
    </div>
    <div class="fila">
      <input type="number" id="propsTamanoNum" min="6" max="200" step="1"
             title="Tamaño exacto en px" placeholder="px">
    </div>
    <div class="titulo">Estilo</div>
    <div class="fila">
      <div class="accion" id="propsNegrita" title="Negrita" style="font-weight:700">B</div>
      <div class="accion" id="propsCursiva" title="Cursiva" style="font-style:italic">I</div>
    </div>
    <div class="titulo">Alineación</div>
    <div class="fila" data-campo="alineacion">
      <div class="accion" data-valor="left" title="Izquierda">⯇</div>
      <div class="accion" data-valor="center" title="Centro">≡</div>
      <div class="accion" data-valor="right" title="Derecha">⯈</div>
    </div>
    <!-- Color del texto: aparte del color del objeto. El primer boton es el
         "opuesto" automatico (como el texto de Instagram), el resto es la misma
         paleta de siempre. -->
    <div class="titulo">Color del texto</div>
    <div class="fila" id="propsColoresTexto"></div>
  </div>
  <div class="titulo" data-sec="capas">Capa</div>
  <div class="fila" data-sec="capas">
    <div class="accion" data-capa="fondo" title="Enviar al fondo">⤓</div>
    <div class="accion" data-capa="bajar" title="Bajar una capa">↓</div>
    <div class="accion" data-capa="subir" title="Subir una capa">↑</div>
    <div class="accion" data-capa="frente" title="Traer al frente">⤒</div>
  </div>
  <div class="titulo" data-sec="acciones">Acciones</div>
  <div class="fila" data-sec="acciones">
    <div class="accion" id="propsCopiarImg" title="Copiar: objetos y foto (Ctrl+C)">📋</div>
    <div class="accion" id="propsDuplicar" title="Duplicar (Ctrl+D)">⧉</div>
    <div class="accion" id="propsBorrar" title="Borrar (Supr)">🗑</div>
  </div>
</div>
<div id="zoomUI">
  <div id="zoomMenos" title="Alejar (Ctrl+rueda)">−</div>
  <div class="zpct" id="zoomPct" title="Volver al 100%">100%</div>
  <div id="zoomMas" title="Acercar (Ctrl+rueda)">+</div>
  <div id="zoomFit" title="Encuadrar todo (Shift+1)">⛶</div>
</div></div>
<script src="/pizarra/rough.js"></script>
<script>
let estado={items:[]};
let bloquear=false;      // arrastrando o editando: no pisar con el auto-refresh
let herramienta='mover';
const tablero=document.getElementById('tablero');
const capa=document.getElementById('capa');
const capaAlta=document.getElementById('capaAlta');
const rc=rough.svg(capa);   // generador de dibujo "a mano alzada" (libreria local)
// El SVG trabaja en PIXELES (sin viewBox): rough.js dibuja el garabato en las
// dos direcciones y un viewBox estirado lo deformaba. Las coordenadas GUARDADAS
// siguen siendo 0-100 (unidades de escena): PX/PY convierten al dibujar.
// CAMARA (modelo de Excalidraw: 3 escalares, sin matrices): x,y es el corrimiento
// en unidades de escena (se SUMA a la coordenada) y zoom multiplica. La camara es
// estado del navegador, no se guarda: cada uno mira la pizarra desde donde quiere.
let camara={x:0, y:0, zoom:1};
const PX=v=>(v+camara.x)*(tablero.clientWidth/100)*camara.zoom;
const PY=v=>(v+camara.y)*(tablero.clientHeight/100)*camara.zoom;
// LX/LY convierten LONGITUDES (anchos, altos): sin el corrimiento de la camara.
// Usar PX para un ancho da negativos en cuanto la camara se corre.
const LX=v=>v*(tablero.clientWidth/100)*camara.zoom;
const LY=v=>v*(tablero.clientHeight/100)*camara.zoom;
const escenaX=px=>px/((tablero.clientWidth/100)*camara.zoom)-camara.x;
const escenaY=px=>px/((tablero.clientHeight/100)*camara.zoom)-camara.y;
const guiaV=document.getElementById('guiaV');
const guiaH=document.getElementById('guiaH');
const FIGURAS=new Set(['linea','flecha','rectangulo','circulo','imagen']);
const TRAZOS=new Set(['lapiz']);
// Tipos "con caja": los que se pueden rotar, recibir texto adentro no (solo
// rect/circulo), y servir de blanco para enganchar flechas.
const CAJA=t=>t==='rectangulo'||t==='circulo'||t==='imagen';
// Rota un punto EN PIXELES alrededor de un centro (grados). En pixeles y no en
// unidades de escena a proposito: la escena no es cuadrada y rotar ahi deforma.
function rotarPx(px, py, cx, cy, ang){
  const r=ang*Math.PI/180, c=Math.cos(r), s=Math.sin(r);
  return {x:cx+(px-cx)*c-(py-cy)*s, y:cy+(px-cx)*s+(py-cy)*c};
}
const PALETA=['#fff3a0','#a8e6a1','#a0d8ef','#f5b8d0','#ffcf9e','#5eb8ff','#e94b3c','#e8eaed'];
// Distancia para "engancharse" a otro objeto, medida EN PIXELES DE PANTALLA (no
// en unidades del lienzo): asi se siente igual con el zoom cerca o lejos. Antes
// era fijo en unidades de escena y alejado costaba muchisimo enganchar.
const UMBRAL_GUIA_PX=10;
const umbralX=()=>UMBRAL_GUIA_PX/((tablero.clientWidth/100)*camara.zoom);
const umbralY=()=>UMBRAL_GUIA_PX/((tablero.clientHeight/100)*camara.zoom);

// --- Guias de alineacion: al mover un objeto entero, se compara contra los
// puntos "alineables" de los demas (centro para nota/pin, esquinas+centro
// para figuras, caja para el lapiz) y si cae cerca de alguno, se pega ahi y
// se muestra una linea punteada. Solo aplica a mover el objeto entero, no a
// los tiradores de agrandar ni a estar dibujando algo nuevo. ---
function puntosDe(it){
  if(it.tipo==='nota' || it.tipo==='pin' || it.tipo==='texto'){
    // La caja REAL de la nota medida del DOM (antes solo contaba el centro, y el
    // marquee que agarraba una punta de la nota no la seleccionaba).
    const el=tablero.querySelector('.item[data-id="'+it.id+'"]');
    if(el){
      const r=el.getBoundingClientRect(), rt=tablero.getBoundingClientRect();
      const x1=escenaX(r.left-rt.left), x2=escenaX(r.right-rt.left);
      const y1=escenaY(r.top-rt.top), y2=escenaY(r.bottom-rt.top);
      return {xs:[x1,x2,(x1+x2)/2], ys:[y1,y2,(y1+y2)/2]};
    }
    return {xs:[it.x], ys:[it.y]};
  }
  if(FIGURAS.has(it.tipo)){
    if(it.angulo){
      // Rotada: la caja que se compara es la de las 4 esquinas YA rotadas.
      const cx=PX((it.x1+it.x2)/2), cy=PY((it.y1+it.y2)/2);
      const pts=[[it.x1,it.y1],[it.x2,it.y2],[it.x1,it.y2],[it.x2,it.y1]]
        .map(([x,y])=>rotarPx(PX(x),PY(y),cx,cy,it.angulo));
      const xs=pts.map(p=>escenaX(p.x)), ys=pts.map(p=>escenaY(p.y));
      const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
      return {xs:[minX,maxX,(minX+maxX)/2], ys:[minY,maxY,(minY+maxY)/2]};
    }
    return {xs:[it.x1,it.x2,(it.x1+it.x2)/2], ys:[it.y1,it.y2,(it.y1+it.y2)/2]};
  }
  if(TRAZOS.has(it.tipo)){
    const xs=it.puntos.map(p=>p.x), ys=it.puntos.map(p=>p.y);
    const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    return {xs:[minX,maxX,(minX+maxX)/2], ys:[minY,maxY,(minY+maxY)/2]};
  }
  return {xs:[], ys:[]};
}

function otrosPuntos(idActual){
  const xs=[], ys=[];
  for(const it of estado.items){
    if(it.id===idActual)continue;
    // Los dibujos a mano alzada NO sirven de referencia (pedido de Martin): su
    // caja es un rectangulo arbitrario alrededor del garabato y engancharse a
    // eso no significa nada. Ellos si se enganchan a los demas.
    if(TRAZOS.has(it.tipo))continue;
    const p=puntosDe(it);
    xs.push(...p.xs); ys.push(...p.ys);
  }
  return {xs, ys};
}

// candX/candY: puntos alineables del objeto que se esta moviendo, YA con dx/dy
// sumado (o sea, donde caeria si no hubiera enganche). Devuelve el dx/dy
// ajustado (igual al que entro si no engancho nada) y donde dibujar la guia.
function ajustarConGuias(idActual, candX, candY, dx, dy){
  const otros=otrosPuntos(idActual);
  let mejorDx=null, guiaX=null, mejorDiffX=umbralX();
  for(const cx of candX)for(const ox of otros.xs){
    const diff=Math.abs((cx+dx)-ox);
    if(diff<mejorDiffX){ mejorDiffX=diff; mejorDx=ox-cx; guiaX=ox; }
  }
  let mejorDy=null, guiaY=null, mejorDiffY=umbralY();
  for(const cy of candY)for(const oy of otros.ys){
    const diff=Math.abs((cy+dy)-oy);
    if(diff<mejorDiffY){ mejorDiffY=diff; mejorDy=oy-cy; guiaY=oy; }
  }
  return {dx: mejorDx!==null?mejorDx:dx, dy: mejorDy!==null?mejorDy:dy, guiaX, guiaY};
}

function mostrarGuias(x, y){
  if(x!=null){
    guiaV.setAttribute('x1',PX(x)); guiaV.setAttribute('x2',PX(x));
    guiaV.setAttribute('y1',0); guiaV.setAttribute('y2',tablero.clientHeight);
    guiaV.style.display='';
  } else guiaV.style.display='none';
  if(y!=null){
    guiaH.setAttribute('y1',PY(y)); guiaH.setAttribute('y2',PY(y));
    guiaH.setAttribute('x1',0); guiaH.setAttribute('x2',tablero.clientWidth);
    guiaH.style.display='';
  } else guiaH.style.display='none';
}

function ocultarGuias(){ guiaV.style.display='none'; guiaH.style.display='none'; }

// --- Deshacer: pila de fotos completas de estado.items. Cada accion que
// cambia algo guarda una foto ANTES de tocar nada; Ctrl+Z pisa el estado del
// servidor con la ultima foto guardada. Es una foto completa (no un
// diff por campo) a proposito: hay demasiados tipos de cambio (mover, agrandar,
// color, texto, crear, borrar) como para escribir el inverso de cada uno sin
// que se termine rompiendo alguno. ---
let deshacerPila=[];
const DESHACER_MAX=30;
function guardarSnapshot(){
  deshacerPila.push(JSON.parse(JSON.stringify(estado.items)));
  if(deshacerPila.length>DESHACER_MAX) deshacerPila.shift();
  refrescarBotonesBarra();
}
// Las acciones que se arrepienten (un arrastre que no movio nada) hacen pop de la
// pila a mano: por eso apagar el boton tiene que pasar por aca tambien.
function olvidarSnapshot(){
  deshacerPila.pop();
  refrescarBotonesBarra();
}
async function deshacer(){
  if(!deshacerPila.length)return;
  const anterior=deshacerPila.pop();
  refrescarBotonesBarra();
  await fetch('/pizarra/restaurar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({items:anterior})});
  refrescar();
}

// --- Seleccion multiple: un click sin arrastrar selecciona (shift+click suma
// o saca de la seleccion); Delete borra todo lo seleccionado de un saque. ---
let seleccion=new Set();

// Combinados: tocar uno trae a todos sus companeros de grupo. Siguen siendo
// objetos independientes; lo unico compartido es la seleccion.
function expandirGrupos(conj){
  const grupos=new Set();
  for(const it of estado.items) if(conj.has(it.id) && it.grupo) grupos.add(it.grupo);
  if(!grupos.size)return conj;
  for(const it of estado.items) if(it.grupo && grupos.has(it.grupo)) conj.add(it.id);
  return conj;
}

function alSeleccionar(id, extender){
  if(!extender) seleccion.clear();
  if(extender && seleccion.has(id)){
    // sacar de la seleccion: si es de un grupo, se van todos sus companeros
    const it=estado.items.find(i=>i.id===id);
    if(it && it.grupo){
      for(const o of estado.items) if(o.grupo===it.grupo) seleccion.delete(o.id);
    } else seleccion.delete(id);
  } else {
    seleccion.add(id);
    adoptarEstilo(id);   // el estilo del ultimo tocado queda para lo proximo
    expandirGrupos(seleccion);
  }
  pintarSeleccion();
}

// Bloqueado: no entra en la seleccion por recuadro, no se mueve, no se estira
// ni se borra. SI se puede seleccionar con un clic para cambiarle propiedades
// (color, grosor, tipografia) y para desbloquearlo.
const bloqueado=id=>{ const it=estado.items.find(i=>i.id===id); return !!(it && it.bloqueado); };
const libres=()=>[...seleccion].filter(id=>!bloqueado(id));

async function bloquearSeleccion(valor){
  if(!seleccion.size)return;
  await Promise.all([...seleccion].map(id=>
    fetch('/pizarra/item/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({bloqueado:!!valor})})));
  ultimoEstadoCrudo='';
  refrescar();
}
const haySeleccionBloqueada=()=>estado.items.some(i=>seleccion.has(i.id) && i.bloqueado);
// El candado de la barra es UN boton que va y viene: con algo bloqueado adentro
// de la seleccion desbloquea, si no bloquea.
function alternarBloqueo(){
  if(!seleccion.size)return;
  bloquearSeleccion(!haySeleccionBloqueada());
}

// Prende y apaga los tres botones de la barra que dependen de la seleccion o del
// historial. Lo llama refrescarPanel() (o sea, cada repintado de la seleccion) y
// tambien guardarSnapshot/deshacer, que mueven la pila sin tocar la seleccion.
function refrescarBotonesBarra(){
  const apagar=(id,v)=>{ const b=document.getElementById(id); if(b) b.classList.toggle('apagado', v); };
  // Recortando no se toca nada mas: la unica salida es Listo o Cancelar.
  const rec=!!recorteEnCurso;
  apagar('btnBorrar', rec || !libres().length);       // lo bloqueado no se borra
  apagar('btnDeshacer', rec || !deshacerPila.length);
  apagar('btnRecortar', rec || !imagenParaRecortar());
  const cand=document.getElementById('btnCandado');
  if(cand){
    const bloq=haySeleccionBloqueada();
    cand.classList.toggle('apagado', rec || !seleccion.size);
    cand.textContent=bloq?'🔓':'🔒';
    cand.title=bloq?'Desbloquear lo seleccionado':'Bloquear lo seleccionado';
  }
}

async function combinarSeleccion(separar){
  if(!seleccion.size)return;
  if(!separar && seleccion.size<2)return;
  await fetch('/pizarra/grupo',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ids:[...seleccion], separar:!!separar})});
  ultimoEstadoCrudo='';   // forzar relectura: cambio el grupo, no las posiciones
  refrescar();
}
function limpiarSeleccion(){ seleccion.clear(); pintarSeleccion(); }
function pintarSeleccion(){
  document.querySelectorAll('.item,.forma-wrap').forEach(el=>{
    const id=Number(el.dataset.id);
    el.classList.toggle('seleccionado', seleccion.has(id));
    el.classList.toggle('bloqueado', bloqueado(id));
  });
  // Manijas y rotor: SOLO del objeto seleccionado, y solo si es uno solo (con
  // varios manda el marco grupal, que tiene sus propios tiradores).
  const unico=seleccion.size===1;
  document.querySelectorAll('.etiqueta-bloqueo').forEach(el=>
    el.classList.toggle('seleccionada', seleccion.has(Number(el.dataset.dueno))));
  document.querySelectorAll('.forma-manija,.forma-rotor,.asa-mover').forEach(el=>{
    const d=Number(el.dataset.dueno);
    el.classList.toggle('visible', unico && seleccion.has(d) && !bloqueado(d));
  });
  // Con el dedo no hay "pasar el mouse por encima": el borde conectable se
  // prende con lo que este seleccionado, que es la unica pista que queda.
  if(TACTIL) for(const id in conectoresDe) conectoresDe[id](seleccion.has(Number(id)));
  refrescarPanel();   // visibilidad y secciones del panel de propiedades
  // Marco grupal punteado alrededor de TODO lo seleccionado (solo con 2+), como
  // Excalidraw: cada objeto conserva su marco solido y el grupo lleva el punteado.
  const marco=document.getElementById('marcoGrupo');
  if(seleccion.size<2){ marco.style.display='none'; return; }
  const rt=tablero.getBoundingClientRect();
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  document.querySelectorAll('.item.seleccionado,.forma-wrap.seleccionado').forEach(el=>{
    const r=el.getBoundingClientRect();
    minX=Math.min(minX,r.left); minY=Math.min(minY,r.top);
    maxX=Math.max(maxX,r.right); maxY=Math.max(maxY,r.bottom);
  });
  if(minX>maxX){ marco.style.display='none'; return; }
  marco.style.left=(minX-rt.left-6)+'px'; marco.style.top=(minY-rt.top-6)+'px';
  marco.style.width=(maxX-minX+12)+'px'; marco.style.height=(maxY-minY+12)+'px';
  marco.style.display='block';
}
async function borrarSeleccion(){
  if(!seleccion.size)return;
  const ids=libres();   // los bloqueados no se borran hasta desbloquearlos
  if(!ids.length)return;
  guardarSnapshot();
  seleccion.clear();
  // UN solo pedido con todos los ids: N DELETEs simultaneos pisandose el archivo
  // de estado fue lo que vacio la pizarra entera el 2026-08-14.
  await fetch('/pizarra/borrar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ids})});
  refrescar();
}

// Pasito del nudge por flechas: nuestro lienzo es 0-100 (porcentaje), no pixeles
// como el de Excalidraw, asi que no tiene sentido copiar su "1px / 5px con Shift"
// literal -- se achica a la misma proporcion (1 a 5) pero en nuestras unidades.
const NUDGE_NORMAL=0.3, NUDGE_SHIFT=1.5;
async function moverSeleccion(dx, dy){
  if(!seleccion.size)return;
  guardarSnapshot();
  const pedidos=[];
  for(const it of estado.items){
    if(!seleccion.has(it.id) || it.bloqueado)continue;
    if(it.tipo==='nota' || it.tipo==='pin' || it.tipo==='texto'){
      it.x+=dx; it.y+=dy;
      pedidos.push(fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({x:it.x,y:it.y})}));
    } else if(FIGURAS.has(it.tipo)){
      it.x1+=dx; it.y1+=dy; it.x2+=dx; it.y2+=dy;
      pedidos.push(fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({x1:it.x1,y1:it.y1,x2:it.x2,y2:it.y2})}));
    } else if(TRAZOS.has(it.tipo)){
      it.puntos=it.puntos.map(p=>({x:p.x+dx,y:p.y+dy}));
      pedidos.push(fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({puntos:it.puntos})}));
    }
  }
  await Promise.all(pedidos);
  // Las figuras movidas arrastran a sus flechas atadas.
  for(const it of estado.items){
    if(seleccion.has(it.id)) await reatarFlechas(it.id);
  }
  refrescar();
}

// Arrastre GRUPAL: agarraste un objeto que ya estaba dentro de una seleccion
// multiple -> se mueve todo el grupo junto (notas, figuras, trazos), con las
// flechas atadas re-apoyandose en vivo. Un clic sin arrastre sigue siendo
// seleccionar/deseleccionar como siempre.
function dragGrupal(e, idAgarrado){
  bloquear=true;
  guardarSnapshot();
  const inicio=xyDesdeEvento(e);
  let movio=false;
  const bases=new Map();
  for(const it of estado.items)
    if(seleccion.has(it.id) && !it.bloqueado) bases.set(it.id, JSON.parse(JSON.stringify(it)));
  const mover=ev=>{
    const p=xyDesdeEvento(ev);
    const dx=p.x-inicio.x, dy=p.y-inicio.y;
    if(Math.hypot(dx,dy)>0.5) movio=true;
    for(const it of estado.items){
      const b=bases.get(it.id);
      if(!b)continue;
      if(it.tipo==='nota'||it.tipo==='pin'||it.tipo==='texto'){
        it.x=b.x+dx; it.y=b.y+dy;
        const el=tablero.querySelector('.item[data-id="'+it.id+'"]');
        if(el){ el.style.left=PX(it.x)+'px'; el.style.top=PY(it.y)+'px'; }
      } else if(FIGURAS.has(it.tipo)){
        it.x1=b.x1+dx; it.y1=b.y1+dy; it.x2=b.x2+dx; it.y2=b.y2+dy;
        if(renderFormas[it.id]) renderFormas[it.id]();
      } else if(TRAZOS.has(it.tipo)){
        it.puntos=b.puntos.map(pt=>({x:pt.x+dx, y:pt.y+dy}));
        if(renderFormas[it.id]) renderFormas[it.id]();
      }
    }
    for(const [id] of bases){
      const it=estado.items.find(i=>i.id===id);
      if(it) reatarEnVivo(it.id);
    }
    pintarSeleccion();
  };
  const soltar=async ev=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    bloquear=false;
    if(!movio){
      olvidarSnapshot();
      alSeleccionar(idAgarrado, ev.shiftKey);
      return;
    }
    const pedidos=[];
    for(const it of estado.items){
      if(!bases.has(it.id))continue;
      let cuerpo=null;
      if(it.tipo==='nota'||it.tipo==='pin'||it.tipo==='texto') cuerpo={x:it.x, y:it.y};
      else if(FIGURAS.has(it.tipo)) cuerpo={x1:it.x1, y1:it.y1, x2:it.x2, y2:it.y2};
      else if(TRAZOS.has(it.tipo)) cuerpo={puntos:it.puntos};
      if(cuerpo) pedidos.push(fetch('/pizarra/item/'+it.id,{method:'PUT',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(cuerpo)}));
    }
    await Promise.all(pedidos);
    for(const [id] of bases){
      const it=estado.items.find(i=>i.id===id);
      if(it) await reatarFlechas(it.id);
    }
    refrescar();
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
}

// --- Redimension GRUPAL (estilo Excalidraw): arrastrar un tirador del marco
// punteado escala TODA la seleccion respecto de la esquina opuesta; cada objeto
// se reubica proporcional a su lugar dentro de la caja original. ---
function bboxSeleccion(){
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(const it of estado.items){
    if(!seleccion.has(it.id))continue;
    const p=puntosDe(it);
    if(!p.xs.length)continue;
    minX=Math.min(minX,...p.xs); maxX=Math.max(maxX,...p.xs);
    minY=Math.min(minY,...p.ys); maxY=Math.max(maxY,...p.ys);
  }
  return {minX,minY,maxX,maxY};
}

document.querySelectorAll('#marcoGrupo .mg-manija').forEach(m=>{
  m.addEventListener('pointerdown', e=>{
    if(e.button!==0)return;
    if(seleccion.size<2)return;
    e.stopPropagation(); e.preventDefault();
    bloquear=true; guardarSnapshot();
    const caja=bboxSeleccion();
    const esq=m.dataset.esq;
    const c0={x: esq.includes('e')?caja.maxX:caja.minX, y: esq.includes('s')?caja.maxY:caja.minY};
    const ancla={x: esq.includes('e')?caja.minX:caja.maxX, y: esq.includes('s')?caja.minY:caja.maxY};
    const bases=new Map();
    for(const it of estado.items)
      if(seleccion.has(it.id) && !it.bloqueado) bases.set(it.id, JSON.parse(JSON.stringify(it)));
    const mover=ev=>{
      const p=xyDesdeEvento(ev);
      let sx=(c0.x-ancla.x)!==0 ? (p.x-ancla.x)/(c0.x-ancla.x) : 1;
      let sy=(c0.y-ancla.y)!==0 ? (p.y-ancla.y)/(c0.y-ancla.y) : 1;
      if(!isFinite(sx) || Math.abs(sx)<0.05) sx=0.05*Math.sign(sx||1);
      if(!isFinite(sy) || Math.abs(sy)<0.05) sy=0.05*Math.sign(sy||1);
      const TXe=v=>ancla.x+(v-ancla.x)*sx, TYe=v=>ancla.y+(v-ancla.y)*sy;
      for(const it of estado.items){
        const b=bases.get(it.id);
        if(!b)continue;
        if(it.tipo==='nota'||it.tipo==='pin'||it.tipo==='texto'){
          it.x=TXe(b.x); it.y=TYe(b.y);
          if(it.tipo==='nota' && b.w) it.w=Math.max(60, Math.round(b.w*Math.abs(sx)));
          const el=tablero.querySelector('.item[data-id="'+it.id+'"]');
          if(el){
            el.style.left=PX(it.x)+'px'; el.style.top=PY(it.y)+'px';
            if(it.w){ el.style.width=it.w+'px'; el.style.maxWidth='none'; el.style.minWidth='none'; }
          }
        } else if(FIGURAS.has(it.tipo)){
          it.x1=TXe(b.x1); it.y1=TYe(b.y1); it.x2=TXe(b.x2); it.y2=TYe(b.y2);
          if(renderFormas[it.id]) renderFormas[it.id]();
        } else if(TRAZOS.has(it.tipo)){
          it.puntos=b.puntos.map(pt=>({x:TXe(pt.x), y:TYe(pt.y)}));
          if(renderFormas[it.id]) renderFormas[it.id]();
        }
      }
      pintarSeleccion();
    };
    const soltar=async()=>{
      document.removeEventListener('pointermove', mover);
      document.removeEventListener('pointerup', soltar);
      bloquear=false;
      ignorarProximoClick=true;
      const pedidos=[];
      for(const it of estado.items){
        if(!bases.has(it.id))continue;
        let cuerpo=null;
        if(it.tipo==='nota'||it.tipo==='pin'||it.tipo==='texto'){ cuerpo={x:it.x, y:it.y}; if(it.w) cuerpo.w=it.w; }
        else if(FIGURAS.has(it.tipo)) cuerpo={x1:it.x1, y1:it.y1, x2:it.x2, y2:it.y2};
        else if(TRAZOS.has(it.tipo)) cuerpo={puntos:it.puntos};
        if(cuerpo) pedidos.push(fetch('/pizarra/item/'+it.id,{method:'PUT',
          headers:{'Content-Type':'application/json'}, body:JSON.stringify(cuerpo)}));
      }
      await Promise.all(pedidos);
      for(const [id] of bases){
        const it=estado.items.find(i=>i.id===id);
        if(it) await reatarFlechas(it.id);
      }
      refrescar();
    };
    document.addEventListener('pointermove', mover);
    document.addEventListener('pointerup', soltar);
  });
});

// Cuerpo listo para POST de una copia del item, corrida dx,dy. atadaA NO se
// copia a proposito: la copia nace suelta (igual que Excalidraw cuando duplicas
// una flecha sin duplicar la figura de la otra punta).
function cuerpoDeCopia(it, dx, dy){
  let cuerpo=null;
  if(it.tipo==='nota' || it.tipo==='pin' || it.tipo==='texto'){
    cuerpo={tipo:it.tipo, texto:it.texto, x:it.x+dx, y:it.y+dy, color:it.color};
    if(it.w) cuerpo.w=it.w;
  } else if(FIGURAS.has(it.tipo)){
    cuerpo={tipo:it.tipo, x1:it.x1+dx, y1:it.y1+dy, x2:it.x2+dx, y2:it.y2+dy, color:it.color};
    if(it.texto) cuerpo.texto=it.texto;
  } else if(TRAZOS.has(it.tipo)){
    cuerpo={tipo:it.tipo, puntos:it.puntos.map(p=>({x:p.x+dx,y:p.y+dy})), color:it.color};
  }
  if(cuerpo) for(const extra of ['grosor','lineaEstilo','relleno','opacidad','angulo','archivo',
                                 'recorte','fuente','tamano','negrita','cursiva','alineacion','colorTexto'])
    if(it[extra]!=null) cuerpo[extra]=it[extra];
  return cuerpo;
}

async function crearCopias(items, dx, dy){
  guardarSnapshot();
  const pedidos=items.map(it=>{
    const cuerpo=cuerpoDeCopia(it, dx, dy);
    return cuerpo && fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(cuerpo)}).then(r=>r.json());
  }).filter(Boolean);
  const creados=await Promise.all(pedidos);
  seleccion=new Set(creados.filter(Boolean).map(c=>c.id));   // lo nuevo queda seleccionado
  refrescar();
}

// Ctrl+D: mismo desplazamiento fijo para todos los tipos (no un porcentaje del
// tamaño), igual que hace Excalidraw -- asi una nota chica y una figura grande
// se despegan del original mas o menos parecido.
const OFFSET_DUPLICAR=3;
async function duplicarSeleccion(){
  if(!seleccion.size)return;
  await crearCopias(estado.items.filter(i=>seleccion.has(i.id)), OFFSET_DUPLICAR, OFFSET_DUPLICAR);
}

// Ctrl+C guarda copias profundas de la seleccion; Ctrl+V las pega corriditas.
// Si el portapapeles del sistema trae una imagen, esa tiene prioridad (el
// listener de 'paste' la maneja antes).
let copiados=[];

// ⭐⭐ Copiar pone las DOS caras de lo mismo en el portapapeles, de una sola vez
// (pedido de Martin, 2026-08-17): los OBJETOS como texto y la FOTO como imagen.
// El portapapeles del sistema admite varios formatos en la misma copia y cada
// destino agarra el que entiende: la pizarra lee los objetos y los pega
// editables; WhatsApp, Word o el chat agarran el PNG y pegan el dibujo.
// Es lo mismo que hacen Excalidraw y Figma, y reemplaza al truco anterior de
// adivinar "esta imagen es mia" comparando el tamaño del archivo, que se rompia
// en cuanto el PNG salia distinto por un byte.
const MARCA_COPIA='pizarra-ia/objetos:';
function textoDeObjetos(items){
  return MARCA_COPIA+JSON.stringify({items});
}
// Devuelve los objetos si el texto pegado es una copia NUESTRA; si no, null.
function objetosDelTexto(texto){
  if(!texto || texto.lastIndexOf(MARCA_COPIA,0)!==0)return null;
  try{
    const d=JSON.parse(texto.slice(MARCA_COPIA.length));
    return (d && Array.isArray(d.items) && d.items.length) ? d.items : null;
  }catch(e){ return null; }
}

async function copiarSeleccion(){
  const items=estado.items.filter(i=>seleccion.has(i.id)).map(i=>JSON.parse(JSON.stringify(i)));
  if(!items.length)return;
  copiados=items;                                   // por si el portapapeles no deja
  const texto=textoDeObjetos(items);
  const png=fetch('/pizarra/png?ids='+items.map(i=>i.id).join(','))
    .then(r=>{ if(!r.ok) throw new Error('el servidor no pudo dibujarlo'); return r.blob(); });
  png.catch(()=>{});   // se atiende abajo; esto evita el "unhandled rejection"
  try{
    // ⚠ El ClipboardItem se arma con la PROMESA del PNG, no con el blob ya
    // listo: el permiso para escribir dura lo que dura el gesto del usuario, y
    // esperar el dibujo con un await antes de pedirlo lo perdia.
    await navigator.clipboard.write([new ClipboardItem({
      'text/plain': new Blob([texto], {type:'text/plain'}),
      'image/png': png
    })]);
  }catch(err){
    // El dibujo falló o el navegador no deja escribir imágenes. Que al menos
    // queden los objetos: copiar adentro de la pizarra es lo que más se usa.
    try{ await navigator.clipboard.writeText(texto); }
    catch(e){ /* ni eso: queda `copiados`, que alcanza para esta misma pestaña */ }
  }
}

// Solo la foto, sin los objetos: para cuando lo querés en otro lado y nada más.
async function copiarComoImagen(){
  const ids=[...seleccion];
  if(!ids.length)return;
  const png=fetch('/pizarra/png?ids='+ids.join(','))
    .then(r=>{ if(!r.ok) throw new Error('el servidor no pudo dibujarlo'); return r.blob(); });
  png.catch(()=>{});
  try{
    await navigator.clipboard.write([new ClipboardItem({'image/png': png})]);
  }catch(err){
    // Sin permiso de portapapeles (pasa en el telefono): que al menos se pueda
    // guardar el archivo, en vez de quedarse sin nada y sin saber por que.
    let blob=null;
    try{ blob=await png; }catch(e){ blob=null; }
    if(!blob){ alert('No se pudo copiar la imagen: '+err.message); return; }
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download='pizarra.png';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 5000);
  }
}

// ⭐ El 📋 de la barra: GUARDAR COMO IMAGEN (pedido de Martin, 2026-08-23, desde el
// telefono: "¿y si me lo guarda como imagen en el celular?"). Es el mismo dibujo que
// ya hace /pizarra/png para Ctrl+C, pero termina en la galeria en vez del portapapeles.
// ⭐ Sin nada elegido saca la pizarra ENTERA: un boton que no hace nada hasta que
// selecciones algo no se entiende, y "todo" es lo que uno espera de una camara.
// ⚠⚠ En el telefono va SI o SI por la hoja de compartir (navigator.share con el
// archivo): es el unico camino a las Fotos del iPhone. Bajarlo lo deja enterrado en
// Archivos y hay que salir a buscarlo. En la compu es al reves y se baja derecho: ahi
// la hoja de compartir de Windows es una vuelta de mas.
// ⚠ Safari solo deja compartir DENTRO del gesto del dedo y el dibujo tarda ~1 s: si se
// pasa, `share` tira NotAllowedError. Por eso el archivo bajado queda de red abajo —
// ese camino no necesita gesto y nunca se queda sin hacer nada.
async function guardarComoFoto(btn){
  const ids = seleccion.size ? [...seleccion] : estado.items.map(i=>i.id);
  if(!ids.length)return;
  const antes=btn.textContent;
  btn.textContent='⏳'; btn.classList.add('apagado');   // ~1 s de dibujo: que se note
  try{
    const r=await fetch('/pizarra/png?ids='+ids.join(','));
    if(!r.ok) throw new Error('el servidor no pudo dibujarla');
    const blob=await r.blob();
    const archivo=new File([blob], 'pizarra.png', {type:'image/png'});
    if(matchMedia('(pointer:coarse)').matches &&
       navigator.canShare && navigator.canShare({files:[archivo]})){
      try{ await navigator.share({files:[archivo]}); return; }
      // Cerrar la hoja de compartir es una decision, no una falla: no se baja nada.
      catch(e){ if(e && e.name==='AbortError')return; }
    }
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download='pizarra.png';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 5000);
  }catch(err){
    alert('No pude guardar la imagen: '+(err.message||err));
  }finally{
    btn.textContent=antes; btn.classList.remove('apagado');
  }
}

// --- Flechas enganchadas (estilo Excalidraw, version simple): una punta de
// flecha soltada CERCA de un rectangulo/circulo queda atada a el (atadaA:
// {inicio:id|null, fin:id|null}) y cuando la figura se mueve, la flecha se
// re-apoya sola sobre su borde, con un gap de aire. El punto de apoyo es la
// interseccion del segmento (centro de la figura -> otro extremo de la flecha)
// con el contorno inflado, igual que hace Excalidraw en modo "orbit". ---
const ATAR_UMBRAL=2.5;   // distancia (en % del tablero) para engancharse
// ⭐ Aire entre la figura y la punta de la flecha: CERO. Estaba en 0,8 (un 0,8 %
// del ancho del tablero, unos 11 px en pantalla grande) para que la punta no
// pisara el trazo de la figura, pero el efecto era que la flecha NUNCA tocaba el
// cuadrado y no se podian unir las dos cosas — el reclamo de Martin del
// 2026-08-17: "siempre hay un espacio". Si alguna vez se quiere el aire de
// vuelta, es este numero y nada mas.
const ATAR_GAP=0;

// Caja {x1,y1,x2,y2} en coordenadas de escena de CUALQUIER objeto enganchable.
// Las notas/textos son HTML de alto variable: su caja se mide del DOM.
function cajaDe(it){
  if(it.tipo==='nota' || it.tipo==='pin' || it.tipo==='texto'){
    const el=tablero.querySelector('.item[data-id="'+it.id+'"]');
    if(el){
      const r=el.getBoundingClientRect(), rt=tablero.getBoundingClientRect();
      return {x1:escenaX(r.left-rt.left), y1:escenaY(r.top-rt.top),
              x2:escenaX(r.right-rt.left), y2:escenaY(r.bottom-rt.top)};
    }
    return {x1:it.x-4, y1:it.y-2, x2:it.x+4, y2:it.y+2};
  }
  // El lapiz no tiene x1..y2: su caja es la que envuelve todos sus puntos. Sin
  // esto cajaDe() devolvia NaN y cualquier cuenta encima daba basura en silencio.
  if(TRAZOS.has(it.tipo)){
    const xs=it.puntos.map(p=>p.x), ys=it.puntos.map(p=>p.y);
    return {x1:Math.min(...xs), y1:Math.min(...ys), x2:Math.max(...xs), y2:Math.max(...ys)};
  }
  return {x1:it.x1, y1:it.y1, x2:it.x2, y2:it.y2};
}
// Los objetos a los que se les puede enganchar una flecha: figuras con caja y
// tambien notas, pines y textos (pedido de Martin, 2026-08-14).
const ENGANCHABLE=t=>t==='rectangulo'||t==='circulo'||t==='imagen'||t==='nota'||t==='pin'||t==='texto';

function centroFigura(f){ const c=cajaDe(f); return {x:(c.x1+c.x2)/2, y:(c.y1+c.y2)/2}; }

function figuraCerca(x, y, excluirId){
  let mejor=null, mejorArea=Infinity;
  for(const it of estado.items){
    if(it.id===excluirId)continue;
    if(!ENGANCHABLE(it.tipo))continue;
    const c=cajaDe(it);
    const minX=Math.min(c.x1,c.x2)-ATAR_UMBRAL, maxX=Math.max(c.x1,c.x2)+ATAR_UMBRAL;
    const minY=Math.min(c.y1,c.y2)-ATAR_UMBRAL, maxY=Math.max(c.y1,c.y2)+ATAR_UMBRAL;
    if(x<minX||x>maxX||y<minY||y>maxY)continue;
    const area=Math.abs(c.x2-c.x1)*Math.abs(c.y2-c.y1);
    if(area<mejorArea){ mejorArea=area; mejor=it; }   // gana la figura mas chica, como Excalidraw
  }
  return mejor;
}

function puntoDeApoyo(fig, desdeX, desdeY){
  const caja=cajaDe(fig);
  const c=centroFigura(fig);
  const dx=desdeX-c.x, dy=desdeY-c.y;
  if(Math.abs(dx)<0.01 && Math.abs(dy)<0.01) return c;
  if(fig.tipo==='circulo'){
    const rx=Math.abs(caja.x2-caja.x1)/2+ATAR_GAP, ry=Math.abs(caja.y2-caja.y1)/2+ATAR_GAP;
    const t=1/Math.sqrt((dx*dx)/(rx*rx)+(dy*dy)/(ry*ry));
    return {x:c.x+dx*t, y:c.y+dy*t};
  }
  const maxX=Math.max(caja.x1,caja.x2)+ATAR_GAP, minX=Math.min(caja.x1,caja.x2)-ATAR_GAP;
  const maxY=Math.max(caja.y1,caja.y2)+ATAR_GAP, minY=Math.min(caja.y1,caja.y2)-ATAR_GAP;
  let t=Infinity;
  if(dx>0) t=Math.min(t,(maxX-c.x)/dx); else if(dx<0) t=Math.min(t,(minX-c.x)/dx);
  if(dy>0) t=Math.min(t,(maxY-c.y)/dy); else if(dy<0) t=Math.min(t,(minY-c.y)/dy);
  if(!isFinite(t)) return c;
  return {x:c.x+dx*t, y:c.y+dy*t};
}

// --- Puntos CLAVADOS del borde ----------------------------------------------
// Una flecha atada puede engancharse de dos maneras. La de siempre es "orbita":
// solo se guarda a QUE figura esta atada y el punto de contacto se recalcula
// apuntando al centro del otro extremo, asi que resbala por el borde cuando las
// cosas se mueven. La nueva es "clavada": se guarda TAMBIEN en que punto del
// borde la enganchaste, como fraccion de la caja ({fx,fy}, 0..1), y ahi se queda
// aunque la figura se mueva, se agrande o se rote. Se guarda en fracciones y no
// en coordenadas para que al agrandar la figura el punto acompane en proporcion.
function puntoAncla(fig, ancla){
  const c=cajaDe(fig);
  const x=Math.min(c.x1,c.x2)+ancla.fx*Math.abs(c.x2-c.x1);
  const y=Math.min(c.y1,c.y2)+ancla.fy*Math.abs(c.y2-c.y1);
  const ang=fig.angulo||0;
  if(!ang) return {x,y};
  // Rotado: el punto gira con la figura. En pixeles, que es donde la rotacion
  // no deforma (el lienzo no es cuadrado), y despues se vuelve a escena.
  const q=rotarPx(PX(x), PY(y), PX((c.x1+c.x2)/2), PY((c.y1+c.y2)/2), ang);
  return {x:escenaX(q.x), y:escenaY(q.y)};
}
// El camino inverso: donde apoyaste el dedo -> que fraccion de la caja es eso.
function anclaDesde(fig, p){
  const c=cajaDe(fig), ang=fig.angulo||0;
  let px=PX(p.x), py=PY(p.y);
  if(ang){
    const q=rotarPx(px, py, PX((c.x1+c.x2)/2), PY((c.y1+c.y2)/2), -ang);
    px=q.x; py=q.y;
  }
  const x=escenaX(px), y=escenaY(py);
  const ancho=Math.abs(c.x2-c.x1)||1, alto=Math.abs(c.y2-c.y1)||1;
  const lim=v=>Math.max(0, Math.min(1, v));
  return {fx:lim((x-Math.min(c.x1,c.x2))/ancho), fy:lim((y-Math.min(c.y1,c.y2))/alto)};
}
// Lleva un punto AL CONTORNO de la figura: el punto del borde mas cercano. Si lo
// soltaste adentro, sale al borde; si lo soltaste en una esquina, se queda en la
// esquina. Trabaja en los ejes de la figura (el punto ya viene desrotado).
function alBorde(fig, c, x, y){
  const minX=Math.min(c.x1,c.x2), maxX=Math.max(c.x1,c.x2);
  const minY=Math.min(c.y1,c.y2), maxY=Math.max(c.y1,c.y2);
  if(fig.tipo==='circulo'){
    const cx=(minX+maxX)/2, cy=(minY+maxY)/2;
    const rx=Math.max(0.01,(maxX-minX)/2), ry=Math.max(0.01,(maxY-minY)/2);
    const dx=x-cx, dy=y-cy;
    if(!dx && !dy) return {x:maxX, y:cy};
    const t=1/Math.sqrt((dx*dx)/(rx*rx)+(dy*dy)/(ry*ry));
    return {x:cx+dx*t, y:cy+dy*t};
  }
  // Rectangular: se pega al lado mas cercano y conserva la otra coordenada.
  const px=Math.max(minX, Math.min(maxX, x)), py=Math.max(minY, Math.min(maxY, y));
  const opciones=[[px-minX,{x:minX,y:py}], [maxX-px,{x:maxX,y:py}],
                  [py-minY,{x:px,y:minY}], [maxY-py,{x:px,y:maxY}]];
  opciones.sort((a,b)=>a[0]-b[0]);
  return opciones[0][1];
}

// El ancla que corresponde a soltar una punta en (p): el punto del borde mas
// cercano, en fracciones de la caja. Es lo que hace que soltar la flecha en la
// esquina del cuadrado la deje EN la esquina.
function anclaEnElBorde(fig, p){
  const c=cajaDe(fig), ang=fig.angulo||0;
  let x=p.x, y=p.y;
  if(ang){
    const q=rotarPx(PX(x), PY(y), PX((c.x1+c.x2)/2), PY((c.y1+c.y2)/2), -ang);
    x=escenaX(q.x); y=escenaY(q.y);
  }
  const b=alBorde(fig, c, x, y);
  const an=Math.abs(c.x2-c.x1)||1, al=Math.abs(c.y2-c.y1)||1;
  return {fx:(b.x-Math.min(c.x1,c.x2))/an, fy:(b.y-Math.min(c.y1,c.y2))/al};
}

// Donde apoya una punta atada a `fig`: clavada si tiene ancla, orbitando si no.
function puntoDeContacto(fig, ancla, haciaX, haciaY){
  return ancla ? puntoAncla(fig, ancla) : puntoDeApoyo(fig, haciaX, haciaY);
}
// Hacia donde "mira" el otro extremo: el punto clavado del otro lado si lo hay,
// si no el centro de su figura, y si esta suelto, la punta misma.
function refDe(fig, ancla, sueltaX, sueltaY){
  if(!fig) return {x:sueltaX, y:sueltaY};
  return ancla ? puntoAncla(fig, ancla) : centroFigura(fig);
}

// Redibujantes por id: cada figura registra su funcion de repintado al crearse,
// para poder redibujar una flecha atada EN VIVO mientras arrastras la figura
// (sin esperar al proximo refresco).
const renderFormas={};
// Asas de mover de notas/pines/textos: hay que reacomodarlas cuando la nota se
// mueve, porque su caja se mide del DOM y no de numeros guardados.
const asasNota={};

function reatarEnVivo(figId){
  for(const fl of estado.items){
    if(fl.tipo!=='flecha' || !fl.atadaA)continue;
    if(fl.atadaA.inicio!==figId && fl.atadaA.fin!==figId)continue;
    const figIni=fl.atadaA.inicio!=null ? estado.items.find(i=>i.id===fl.atadaA.inicio) : null;
    const figFin=fl.atadaA.fin!=null   ? estado.items.find(i=>i.id===fl.atadaA.fin)   : null;
    const aIni=fl.atadaA.anclaInicio||null, aFin=fl.atadaA.anclaFin||null;
    const refIni=refDe(figFin, aFin, fl.x2, fl.y2);
    const refFin=refDe(figIni, aIni, fl.x1, fl.y1);
    if(figIni){ const p=puntoDeContacto(figIni, aIni, refIni.x, refIni.y); fl.x1=p.x; fl.y1=p.y; }
    if(figFin){ const p=puntoDeContacto(figFin, aFin, refFin.x, refFin.y); fl.x2=p.x; fl.y2=p.y; }
    if(renderFormas[fl.id]) renderFormas[fl.id]();
    if(renderFormas['n'+figId]) renderFormas['n'+figId]();   // conectores de la nota
  }
}

// La figura figId se movio o cambio de tamano: re-apoyar todas las flechas atadas a ella.
async function reatarFlechas(figId){
  const pedidos=[];
  for(const fl of estado.items){
    if(fl.tipo!=='flecha' || !fl.atadaA)continue;
    if(fl.atadaA.inicio!==figId && fl.atadaA.fin!==figId)continue;
    const figIni=fl.atadaA.inicio!=null ? estado.items.find(i=>i.id===fl.atadaA.inicio) : null;
    const figFin=fl.atadaA.fin!=null   ? estado.items.find(i=>i.id===fl.atadaA.fin)   : null;
    // referencia para apuntar: el punto clavado del otro lado, el centro de su
    // figura, o la punta suelta
    const aIni=fl.atadaA.anclaInicio||null, aFin=fl.atadaA.anclaFin||null;
    const refIni=refDe(figFin, aFin, fl.x2, fl.y2);
    const refFin=refDe(figIni, aIni, fl.x1, fl.y1);
    if(figIni){ const p=puntoDeContacto(figIni, aIni, refIni.x, refIni.y); fl.x1=p.x; fl.y1=p.y; }
    if(figFin){ const p=puntoDeContacto(figFin, aFin, refFin.x, refFin.y); fl.x2=p.x; fl.y2=p.y; }
    pedidos.push(fetch('/pizarra/item/'+fl.id,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({x1:fl.x1,y1:fl.y1,x2:fl.x2,y2:fl.y2})}));
  }
  if(pedidos.length){ await Promise.all(pedidos); refrescar(); }
}

// Se solto una punta de flecha en (x,y): engancharla o soltarla segun haya figura cerca.
async function intentarAtar(fl, extremo, x, y){
  const fig=figuraCerca(x, y, fl.id);
  const atadaA={inicio:(fl.atadaA&&fl.atadaA.inicio)||null, fin:(fl.atadaA&&fl.atadaA.fin)||null,
                anclaInicio:(fl.atadaA&&fl.atadaA.anclaInicio)||null,
                anclaFin:(fl.atadaA&&fl.atadaA.anclaFin)||null};
  atadaA[extremo]=fig ? fig.id : null;
  const clave=extremo==='inicio'?'anclaInicio':'anclaFin';
  // ⭐ Donde soltaste la punta, AHI queda. Antes esto pasaba por puntoDeApoyo(),
  // que ignora el lugar del suelte y apoya la flecha en el punto del borde que
  // mira al otro extremo: soltabas la punta en la esquina del cuadrado y la
  // flecha se iba sola al medio del lado. Ahora se clava en el punto del contorno
  // mas cercano a donde la soltaste (reclamo de Martin, 2026-08-17).
  atadaA[clave]=fig ? anclaEnElBorde(fig, {x, y}) : null;
  fl.atadaA=atadaA;
  const cuerpo={atadaA};
  if(fig){
    const p=puntoAncla(fig, atadaA[clave]);
    if(extremo==='inicio'){ fl.x1=p.x; fl.y1=p.y; cuerpo.x1=p.x; cuerpo.y1=p.y; }
    else{ fl.x2=p.x; fl.y2=p.y; cuerpo.x2=p.x; cuerpo.y2=p.y; }
  }
  await fetch('/pizarra/item/'+fl.id,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(cuerpo)});
  refrescar();
}

// --- Tipografia: se aplica igual al texto suelto y al de adentro de una figura.
// El tamano se multiplica por el zoom (el texto es HTML, no escala solo). ---
const FUENTES={manuscrita:"'Segoe Script','Comic Sans MS',cursive",
               palo:"'Segoe UI',system-ui,sans-serif",
               mono:"Consolas,'Courier New',monospace"};
function aplicarEstiloTexto(el, it, tamBase){
  el.style.fontFamily=FUENTES[it.fuente||'manuscrita'];
  el.style.fontSize=((it.tamano||tamBase)*camara.zoom)+'px';
  el.style.fontWeight=it.negrita?'700':'400';
  el.style.fontStyle=it.cursiva?'italic':'normal';
  el.style.textAlign=it.alineacion||'center';
  const ct=colorTextoDe(it);
  if(ct) el.style.color=ct;
}

// ¿Que color tiene ATRAS el texto de este objeto? Es lo que mira el "opuesto"
// automatico para decidir si escribe en claro o en oscuro.
function fondoDetrasDe(it){
  if(it.tipo==='nota') return it.color;
  if(it.tipo==='pin') return '#151920';                    // la pastilla de la etiqueta
  // Figura: el texto se apoya en el relleno, salvo que no tenga -- ahi se apoya
  // en el fondo del tablero. Lo mismo para el texto suelto.
  if((it.tipo==='rectangulo'||it.tipo==='circulo') && (it.relleno||'hachura')!=='ninguno')
    return it.color;
  return estado.fondo || '#0b0d12';
}

// Color del texto de un objeto: un color a mano, o el OPUESTO de lo que tiene
// atras (como el texto de Instagram). Devuelve null si no se eligio nada y hay
// que dejar el color de siempre de la hoja de estilos.
function colorTextoDe(it){
  const c=it.colorTexto;
  if(!c) return null;
  if(c!=='auto') return c;
  return contrasteDe(fondoDetrasDe(it));
}

// Claro sobre oscuro y oscuro sobre claro (misma cuenta de luminancia que usa la
// trama de puntitos del fondo).
function contrasteDe(hex){
  if(!hex || hex[0]!=='#' || hex.length<7) return '#e8eaed';
  const lum=parseInt(hex.slice(1,3),16)*0.299+parseInt(hex.slice(3,5),16)*0.587+parseInt(hex.slice(5,7),16)*0.114;
  return lum>140 ? '#16191f' : '#f2f5f9';
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
// Coordenadas de ESCENA del evento (ya no se recortan a 0-100: el lienzo es
// infinito, con la camara te podes ir a donde quieras).
function xyDesdeEvento(e){
  const r=tablero.getBoundingClientRect();
  return {x:escenaX(e.clientX-r.left), y:escenaY(e.clientY-r.top)};
}

// Panel de propiedades fijo (estilo Excalidraw): un solo lugar para cambiar el
// color y accionar sobre TODO lo seleccionado, en vez de un popover flotante
// por figura que se chocaba contra los objetos.
// Estilo ACTUAL: lo que se le pone a lo proximo que dibujes. El panel edita
// esto cuando no hay nada seleccionado pero si hay una herramienta armada
// (mismo comportamiento que Excalidraw).
let estiloActual={};

// Devuelve el estilo actual filtrado para el tipo que se va a crear.
function estiloPara(tipo){
  const e={}, esFig=(tipo==='rectangulo'||tipo==='circulo');
  const permitidos=(tipo==='nota'||tipo==='pin'||tipo==='texto')
    ? ['color','opacidad','fuente','tamano','negrita','cursiva','alineacion','colorTexto']
    : (tipo==='lapiz' ? ['color','grosor','opacidad','punta']
       : ['color','grosor','lineaEstilo','opacidad'].concat(esFig?['relleno','colorTexto']:[]));
  for(const k of permitidos) if(estiloActual[k]!=null) e[k]=estiloActual[k];
  return e;
}

async function aplicarASeleccion(cambio){
  const objetivos=libres();
  if(!objetivos.length){
    // Sin nada seleccionado: el panel configura lo PROXIMO que dibujes.
    Object.assign(estiloActual, cambio);
    refrescarPanel();
    return;
  }
  // Lo que cambias sobre lo seleccionado queda TAMBIEN como estilo actual, asi
  // lo proximo que dibujes sale igual (pedido de Martin, 2026-08-14).
  Object.assign(estiloActual, cambio);
  guardarSnapshot();
  await Promise.all(objetivos.map(id=>
    fetch('/pizarra/item/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(cambio)})));
  refrescar();
}

// Al seleccionar UN objeto, su estilo pasa a ser el estilo actual: la proxima
// figura que dibujes nace con el mismo look que la ultima que tocaste.
const CAMPOS_ESTILO=['color','grosor','lineaEstilo','relleno','opacidad','punta',
                     'fuente','tamano','negrita','cursiva','alineacion','colorTexto'];
function adoptarEstilo(id){
  const it=estado.items.find(i=>i.id===id);
  if(!it || it.bloqueado)return;
  for(const k of CAMPOS_ESTILO) if(it[k]!=null) estiloActual[k]=it[k];
}

// Muestra el panel si hay algo seleccionado O si hay una herramienta armada, y
// prende/apaga las secciones que apliquen a ese tipo.
function refrescarPanel(){
  const panel=document.getElementById('panelProps');
  if(!panel)return;
  const hayLibres=libres().length>0;
  const armada=herramienta!=='mover';
  // ⚠ Los botones de la barra se prenden ANTES del return de abajo: si no, al
  // soltar la seleccion no se apagarian nunca (esa es justo la vuelta que sale
  // por ahi). Y el candado tiene que seguir vivo con algo BLOQUEADO seleccionado,
  // que es el unico caso en el que el panel de propiedades no se muestra.
  refrescarBotonesBarra();
  // Recortando, las propiedades estorban: ocupan el mismo lugar que la barra del
  // recorte en el telefono y no hay nada ahi que aplique a lo que estas haciendo.
  const mostrarPanel=(hayLibres || armada) && !recorteEnCurso;
  // ⚠ La visibilidad va por CLASE, no por `style.display`: en el telefono la hoja se
  // dibuja como GRILLA de dos columnas (nombre a la izquierda, botones a la derecha) y
  // un display puesto a mano le gana a la hoja de estilos — quedaba en flex y se veia
  // apilada y cortada (2026-08-17).
  panel.classList.toggle('visible', mostrarPanel);
  if(!mostrarPanel)return;

  // Tipos involucrados: los seleccionados, o el de la herramienta armada.
  const tipos=hayLibres ? libres().map(id=>{ const i=estado.items.find(x=>x.id===id); return i?i.tipo:''; })
                        : [herramienta];
  const alguno=f=>tipos.some(f);
  const conTexto=alguno(t=>t==='nota'||t==='pin'||t==='texto') ||
                 (hayLibres && estado.items.some(i=>seleccion.has(i.id) && i.texto));
  const conTrazo=alguno(t=>t!=='nota'&&t!=='pin'&&t!=='texto'&&t!=='imagen');
  const conRelleno=alguno(t=>t==='rectangulo'||t==='circulo');
  const mostrar=(sel,v)=>{ const e=document.querySelector(sel); if(e) e.style.display=v?'':'none'; };
  mostrar('#seccionTexto', conTexto);
  const conPunta=alguno(t=>t==='lapiz');
  mostrar('#panelProps .titulo[data-sec="punta"]', conPunta);
  mostrar('#panelProps .fila[data-campo="punta"]', conPunta);
  mostrar('#panelProps .titulo[data-sec="grosor"]', conTrazo);
  mostrar('#panelProps .fila[data-campo="grosor"]', conTrazo);
  mostrar('#panelProps .titulo[data-sec="trazo"]', conTrazo && !alguno(t=>t==='lapiz'));
  mostrar('#panelProps .fila[data-campo="lineaEstilo"]', conTrazo && !alguno(t=>t==='lapiz'));
  mostrar('#panelProps .titulo[data-sec="relleno"]', conRelleno);
  mostrar('#panelProps .fila[data-campo="relleno"]', conRelleno);
  mostrar('#panelProps .titulo[data-sec="capas"]', hayLibres);
  mostrar('#panelProps .fila[data-sec="capas"]', hayLibres);
  mostrar('#panelProps .titulo[data-sec="acciones"]', hayLibres);
  mostrar('#panelProps .fila[data-sec="acciones"]', hayLibres);

  chipsProps();   // que pestañita se ve, segun lo que aplica a esto
  // Marcar la opcion elegida en cada fila (grosor, trazo, relleno, punta,
  // tipografia, tamano, alineacion) y los interruptores de negrita/cursiva.
  const it0=hayLibres ? estado.items.find(i=>seleccion.has(i.id)) : null;
  const DEF={grosor:2, lineaEstilo:'solido', relleno:'hachura', punta:'fibra',
             fuente:'manuscrita', alineacion:'center'};
  const valorDe=campo=>{
    if(it0 && it0[campo]!=null) return it0[campo];
    if(!it0 && estiloActual[campo]!=null) return estiloActual[campo];
    if(campo==='tamano') return it0 ? (it0.tipo==='texto'?20:13.5) : 20;
    return DEF[campo];
  };
  document.querySelectorAll('#panelProps .fila[data-campo]').forEach(fila=>{
    const v=String(valorDe(fila.dataset.campo));
    fila.querySelectorAll('.accion').forEach(b=>b.classList.toggle('activo', b.dataset.valor===v));
  });
  const marcar=(id,campo)=>{
    const b=document.getElementById(id);
    if(b) b.classList.toggle('activo', !!(it0 ? it0[campo] : estiloActual[campo]));
  };
  marcar('propsNegrita','negrita');
  marcar('propsCursiva','cursiva');
  // El color actual se marca con un anillo alrededor del swatch.
  const colorAct=valorDe('color');
  document.querySelectorAll('#propsColores .sw').forEach(sw=>
    sw.classList.toggle('activo', sw.title===colorAct));
  // Idem con el color del texto ("auto" es el opuesto automatico).
  const ctAct=it0 ? (it0.colorTexto||'') : (estiloActual.colorTexto||'');
  document.querySelectorAll('#propsColoresTexto .sw').forEach(sw=>
    sw.classList.toggle('activo', !!ctAct && sw.title===ctAct));

  // El campo del tamano de letra refleja lo seleccionado (o el estilo actual).
  const campoTam=document.getElementById('propsTamanoNum');
  if(campoTam && document.activeElement!==campoTam){
    const it=hayLibres ? estado.items.find(i=>seleccion.has(i.id)) : null;
    campoTam.value = it ? (it.tamano || (it.tipo==='texto'?20:13.5))
                        : (estiloActual.tamano || 20);
  }
}

function armarPanelProps(){
  // (los swatches de color los arma renderPaletas, que suma los personalizados)
  // Filas de opciones (grosor, trazo, relleno): el data-campo de la fila dice
  // que propiedad cambia, el data-valor de cada boton dice a que valor.
  document.querySelectorAll('#panelProps .fila[data-campo]').forEach(fila=>{
    const campo=fila.dataset.campo;
    fila.querySelectorAll('.accion').forEach(btn=>{
      btn.onclick=()=>{
        let v=btn.dataset.valor;
        if(campo==='grosor') v=Number(v);
        aplicarASeleccion({[campo]:v});
      };
    });
  });
  document.getElementById('propsOpacidad').onchange=e=>
    aplicarASeleccion({opacidad:Number(e.target.value)});
  // Negrita y cursiva son interruptores: miran el primer seleccionado y lo invierten.
  const alternar=campo=>{
    const it=estado.items.find(i=>seleccion.has(i.id));
    aplicarASeleccion({[campo]: it ? !it[campo] : true});
  };
  document.getElementById('propsNegrita').onclick=()=>alternar('negrita');
  document.getElementById('propsCursiva').onclick=()=>alternar('cursiva');
  // Tamano exacto: se aplica al salir del campo o con Enter (no en cada tecla,
  // que dispararia un guardado por digito).
  const campoTam=document.getElementById('propsTamanoNum');
  const aplicarTam=()=>{
    const v=Number(campoTam.value);
    if(!v)return;
    aplicarASeleccion({tamano:Math.max(6, Math.min(200, Math.round(v)))});
  };
  campoTam.onchange=aplicarTam;
  campoTam.onkeydown=e=>{ if(e.key==='Enter'){ e.preventDefault(); campoTam.blur(); } };
  document.querySelectorAll('#panelProps .accion[data-capa]').forEach(b=>{
    b.onclick=()=>ordenarSeleccion(b.dataset.capa);
  });
  document.getElementById('propsDuplicar').onclick=()=>duplicarSeleccion();
  document.getElementById('propsBorrar').onclick=()=>borrarSeleccion();
  document.getElementById('propsCopiarImg').onclick=()=>copiarSeleccion();
}

// Guardar la barra de herramientas (telefono): se pliega a un solo boton contra el
// borde y se acuerda de como la dejaste. En el telefono la barra son dos renglones
// encima del tablero, y a veces lo que uno quiere es MIRAR lo que hay (pedido de
// Martin, 2026-08-17). En la compu el boton ni se muestra.
// ⭐ Cuánto mide la barra de herramientas AHORA: la hoja de propiedades y la del
// recorte se apoyan encima suyo, y la barra cambia de alto (dos renglones abierta, uno
// solo guardada, y en la compu es una columna). Se mide y se deja en --altoBarra, que
// es lo que usan las dos hojas para saber dónde termina. Con un número fijo, la hoja se
// le montaba encima y tapaba media barra (2026-08-17).
function acomodarHojas(){
  const t = document.getElementById('toolbar');
  if(!t) return;
  // ⚠ Guardada tambien mide: queda un boton contra el borde de abajo a la derecha, y
  // si la hoja lo tapa no hay forma de volver a abrir la barra (probado: la tapaba).
  const alto = Math.round(t.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--altoBarra', alto + 'px');
}

function pintarBotonBarra(plegada){
  const b=document.getElementById('btnPlegar');
  if(!b)return;
  b.textContent = plegada ? '🧰' : '▾';
  b.title = plegada ? 'Mostrar las herramientas' : 'Guardar la barra de herramientas';
}

function plegarBarra(){
  const plegada = document.getElementById('toolbar').classList.toggle('plegado');
  localStorage.setItem('barraPlegada', plegada ? '1' : '');
  pintarBotonBarra(plegada);
  // Con la barra guardada, la hoja de propiedades baja y usa ese lugar.
  document.body.classList.toggle('barra-plegada', plegada);
  acomodarHojas();
}
if (localStorage.getItem('barraPlegada')){
  document.getElementById('toolbar').classList.add('plegado');
  document.body.classList.add('barra-plegada');
}
pintarBotonBarra(!!localStorage.getItem('barraPlegada'));
// Al arrancar, y de nuevo cuando ya se acomodaron los renglones de la barra.
acomodarHojas();
requestAnimationFrame(acomodarHojas);

// --- Las propiedades, de a UNA seccion (telefono) ---------------------------
// ⭐⭐ Antes la hoja mostraba las siete secciones una abajo de la otra: 530 px de
// pantalla, mas la barra de herramientas, mas la barra de la app = el tablero quedaba
// en una franja. Martin: "pensá una mejor manera de hacer esto" (2026-08-17).
// Ahora arriba hay una fila de pestañitas —Color, Grosor, Trazo, Relleno, Opacidad,
// Capa, Acciones— y abajo se ve SOLO la elegida: la hoja pasa a medir dos renglones.
// Es lo que hacen Canva y Figma en el telefono, y de paso los botones quedan grandes.
//
// El HTML no cambia: al arrancar, cada titulo se envuelve con lo que le sigue en un
// `.grupo`. En la compu ese envoltorio es TRANSPARENTE (`display:contents`), asi que
// ahi no cambia absolutamente nada; en el telefono es la unidad que se muestra.
let grupoAbierto = '';

function armarGruposProps(){
  const panel=document.getElementById('panelProps');
  if(!panel || panel.querySelector('.grupo'))return;
  for(const el of [...panel.children]){
    if(el.id==='propsCabecera')continue;
    let g=null;
    if(el.classList.contains('titulo')){
      g=document.createElement('div');
      g.className='grupo';
      g.dataset.grupo=el.dataset.sec || el.textContent.trim().toLowerCase();
      g.dataset.nombre=el.textContent.trim();
      panel.insertBefore(g, el);
      g.appendChild(el);
      // Todo lo que sigue hasta el proximo titulo es parte de esta seccion.
      while(g.nextElementSibling && !g.nextElementSibling.classList.contains('titulo')
            && g.nextElementSibling.id!=='seccionTexto')
        g.appendChild(g.nextElementSibling);
    } else if(el.id==='seccionTexto'){
      g=document.createElement('div');
      g.className='grupo'; g.dataset.grupo='texto'; g.dataset.nombre='Texto';
      panel.insertBefore(g, el); g.appendChild(el);
    }
  }
}

// Que secciones aplican a lo que esta elegido (refrescarPanel ya escondio las que no)
// y cual se esta viendo. Si la que estaba abierta no aplica, se abre la primera.
function chipsProps(){
  const cont=document.getElementById('chipsProps');
  if(!cont)return;
  const grupos=[...document.querySelectorAll('#panelProps .grupo')]
    .filter(g=>{ const primero=g.firstElementChild;
                 return primero && primero.style.display!=='none'; });
  if(!grupos.some(g=>g.dataset.grupo===grupoAbierto))
    grupoAbierto = grupos.length ? grupos[0].dataset.grupo : '';
  cont.innerHTML=grupos.map(g=>
    '<div class="chip'+(g.dataset.grupo===grupoAbierto?' sel':'')+'" data-ir="'+
    g.dataset.grupo+'">'+g.dataset.nombre+'</div>').join('');
  document.querySelectorAll('#panelProps .grupo').forEach(g=>
    g.classList.toggle('abierto', g.dataset.grupo===grupoAbierto));
  cont.querySelectorAll('.chip').forEach(c=>
    c.onclick=()=>{ grupoAbierto=c.dataset.ir; chipsProps(); });
}

// Lo mismo para la hoja de propiedades: en el telefono tapa medio tablero, y a veces
// uno quiere ver lo que hay abajo sin soltar la seleccion (pedido de Martin,
// 2026-08-17). Plegada queda solo la tira con el titulo.
function plegarProps(){
  const plegada = document.getElementById('panelProps').classList.toggle('plegado');
  localStorage.setItem('propsPlegado', plegada ? '1' : '');
  pintarBotonProps(plegada);
}
// ⚠ Guardada, el boton es lo UNICO que queda de la hoja, asi que tiene que decir que
// trae de vuelta: dos flechitas iguales (esta y la de la barra de herramientas) una
// arriba de la otra no se distinguen. Abierta es la flecha de guardar.
function pintarBotonProps(plegada){
  const b=document.getElementById('btnProps');
  if(!b)return;
  b.textContent = plegada ? '🎛' : '▾';
  b.title = plegada ? 'Mostrar las propiedades' : 'Guardar las propiedades';
}
const propsArrancaPlegada = !!localStorage.getItem('propsPlegado');
if (propsArrancaPlegada)
  document.getElementById('panelProps').classList.add('plegado');
pintarBotonProps(propsArrancaPlegada);

// Desplegable de fondos: se abre al lado del boton de la barra y se cierra al
// elegir un color o al tocar en cualquier otro lado.
function toggleFondos(e){
  e.stopPropagation();
  const menu=document.getElementById('fondos');
  if(menu.classList.contains('abierto')){ menu.classList.remove('abierto'); return; }
  const r=document.getElementById('btnFondo').getBoundingClientRect();
  menu.style.left=(r.right+8)+'px';
  menu.style.top=Math.min(r.top, window.innerHeight-130)+'px';
  menu.classList.add('abierto');
  setTimeout(()=>document.addEventListener('pointerdown', function cerrar(ev){
    if(!menu.contains(ev.target)){ menu.classList.remove('abierto'); document.removeEventListener('pointerdown', cerrar); }
  }), 0);
}

function seleccionarHerramienta(btn){
  // Agarrar otra herramienta a mitad de un recorte lo deja a medias y con el
  // overlay colgado: se cancela, que es lo que espera cualquiera.
  if(recorteEnCurso) salirRecorte(false);
  const t=btn.dataset.tool;
  herramienta=(herramienta===t && t!=='mover')?'mover':t;
  document.querySelectorAll('.herr-btn').forEach(b=>b.classList.toggle('armado', b.dataset.tool===herramienta));
  tablero.classList.toggle('armando', herramienta!=='mover');
  // Armar una herramienta suelta la seleccion: si no, el panel seguiria
  // mostrando las opciones del objeto viejo en vez de las de lo que vas a dibujar.
  if(herramienta!=='mover' && seleccion.size){ seleccion.clear(); pintarSeleccion(); }
  else refrescarPanel();
}

// Al terminar de dibujar algo, la herramienta vuelve sola a "mover" y lo nuevo
// queda seleccionado (comportamiento default de Excalidraw): dibujar dos figuras
// seguidas requiere elegir la herramienta de nuevo, nada de figuras sin querer.
function volverAMover(){
  herramienta='mover';
  document.querySelectorAll('.herr-btn').forEach(b=>b.classList.toggle('armado', b.dataset.tool==='mover'));
  tablero.classList.remove('armando');
  refrescarPanel();
}

let ultimoEstadoCrudo='';

// Reconstruye el dibujo entero desde `estado` (sin ir al servidor). La camara
// llama esto directo en cada zoom/paneo.
// Fondos disponibles: los oscuros nuestros + los picks claros de Excalidraw.
const FONDOS=['#0b0d12','#121212','#16202b','#ffffff','#f8f9fa','#f5faff','#fffce8','#fdf8f6'];

function aplicarFondo(){
  const f=estado.fondo || '#0b0d12';
  tablero.style.background=f;
  // puntitos de la trama: oscuros sobre fondo claro, claros sobre fondo oscuro
  const lum=parseInt(f.slice(1,3),16)*0.299+parseInt(f.slice(3,5),16)*0.587+parseInt(f.slice(5,7),16)*0.114;
  const punto=lum>140 ? 'rgba(0,0,0,.18)' : '#1a1f28';
  tablero.style.backgroundImage='radial-gradient('+punto+' 1px,transparent 1px)';
  tablero.style.backgroundSize='24px 24px';
}

// --- Colores personalizados: viven en el estado de la pizarra (compartidos y
// persistentes). El "+" abre el selector de color del sistema; clic derecho
// sobre un color personalizado permite editarlo o borrarlo. ---
const inputColor=document.createElement('input');
inputColor.type='color'; inputColor.style.display='none';
document.body.appendChild(inputColor);
function elegirColor(inicial, cb){
  inputColor.value=inicial||'#5eb8ff';
  inputColor.onchange=()=>cb(inputColor.value);
  inputColor.click();
}
async function guardarColores(){
  await fetch('/pizarra/colores',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({coloresObjetos:estado.coloresObjetos||[], coloresFondos:estado.coloresFondos||[]})});
}
function menuSwatch(ev, lista){
  const idx=Number(ev.target.dataset.idx);
  ev.preventDefault(); ev.stopPropagation();
  document.querySelectorAll('.menuCtx').forEach(n=>n.remove());
  const menu=document.createElement('div'); menu.className='menuCtx';
  const rt=tablero.getBoundingClientRect();
  menu.style.left=(ev.clientX-rt.left)+'px'; menu.style.top=(ev.clientY-rt.top)+'px';
  const op=(t,fn)=>{ const d=document.createElement('div'); d.textContent=t;
    d.onclick=()=>{ menu.remove(); fn(); }; menu.appendChild(d); };
  op('Editar color', ()=>elegirColor(lista[idx], async c=>{
    lista[idx]=c; await guardarColores(); coloresMemo=''; renderPaletas();
  }));
  op('Borrar color', async()=>{
    lista.splice(idx,1); await guardarColores(); coloresMemo=''; renderPaletas();
  });
  tablero.appendChild(menu);
  setTimeout(()=>document.addEventListener('pointerdown', function cerrar(e2){
    if(!menu.contains(e2.target)){ menu.remove(); document.removeEventListener('pointerdown', cerrar); }
  }),0);
}

function armarSwatchesObjetos(){
  const cont=document.getElementById('propsColores');
  cont.innerHTML='';
  const sumar=(c, idx)=>{
    const sw=document.createElement('div');
    sw.className='sw'; sw.style.background=c; sw.title=c;
    sw.onclick=()=>aplicarASeleccion({color:c});
    if(idx!=null){ sw.dataset.idx=idx; sw.oncontextmenu=ev=>menuSwatch(ev, estado.coloresObjetos); }
    cont.appendChild(sw);
  };
  for(const c of PALETA) sumar(c);
  (estado.coloresObjetos||[]).forEach((c,i)=>sumar(c,i));
  const mas=document.createElement('div');
  mas.className='sw'; mas.textContent='+'; mas.title='Agregar color personalizado';
  mas.style.cssText='display:flex;align-items:center;justify-content:center;color:var(--ccdd3dc,#cdd3dc);background:var(--c181d26,#181d26);font-size:14px';
  mas.onclick=()=>elegirColor('#5eb8ff', async c=>{
    (estado.coloresObjetos=estado.coloresObjetos||[]).push(c);
    await guardarColores(); coloresMemo=''; renderPaletas();
    aplicarASeleccion({color:c});
  });
  cont.appendChild(mas);
}

// La misma paleta, pero para el COLOR DEL TEXTO. Arranca con el "opuesto"
// automatico: pinta el texto claro sobre lo oscuro y oscuro sobre lo claro, que
// es lo que hace falta cuando la figura es celeste y las letras eran blancas.
function armarSwatchesTexto(){
  const cont=document.getElementById('propsColoresTexto');
  if(!cont)return;
  cont.innerHTML='';
  const auto=document.createElement('div');
  auto.className='sw'; auto.dataset.valor='auto';
  auto.title='auto';
  auto.textContent='◐';
  auto.style.cssText='display:flex;align-items:center;justify-content:center;color:var(--ccdd3dc,#cdd3dc);background:var(--c181d26,#181d26);font-size:14px';
  auto.onclick=()=>aplicarASeleccion({colorTexto:'auto'});
  cont.appendChild(auto);
  const sumar=(c, idx)=>{
    const sw=document.createElement('div');
    sw.className='sw'; sw.style.background=c; sw.title=c;
    sw.onclick=()=>aplicarASeleccion({colorTexto:c});
    if(idx!=null){ sw.dataset.idx=idx; sw.oncontextmenu=ev=>menuSwatch(ev, estado.coloresObjetos); }
    cont.appendChild(sw);
  };
  for(const c of PALETA) sumar(c);
  (estado.coloresObjetos||[]).forEach((c,i)=>sumar(c,i));
  const mas=document.createElement('div');
  mas.className='sw'; mas.textContent='+'; mas.title='Agregar color personalizado';
  mas.style.cssText='display:flex;align-items:center;justify-content:center;color:var(--ccdd3dc,#cdd3dc);background:var(--c181d26,#181d26);font-size:14px';
  mas.onclick=()=>elegirColor('#e8eaed', async c=>{
    (estado.coloresObjetos=estado.coloresObjetos||[]).push(c);
    await guardarColores(); coloresMemo=''; renderPaletas();
    aplicarASeleccion({colorTexto:c});
  });
  cont.appendChild(mas);
}

function armarSwatchesFondos(){
  const cont=document.getElementById('fondos');
  cont.innerHTML='';
  const usar=async f=>{
    estado.fondo=f; aplicarFondo();
    cont.classList.remove('abierto');   // elegiste: se cierra el desplegable
    await fetch('/pizarra/fondo',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({color:f})});
  };
  const sumar=(f, idx)=>{
    const sw=document.createElement('div');
    sw.style.background=f; sw.title=f;
    sw.onclick=()=>usar(f);
    if(idx!=null){ sw.dataset.idx=idx; sw.oncontextmenu=ev=>menuSwatch(ev, estado.coloresFondos); }
    cont.appendChild(sw);
  };
  for(const f of FONDOS) sumar(f);
  (estado.coloresFondos||[]).forEach((f,i)=>sumar(f,i));
  const mas=document.createElement('div');
  mas.textContent='+'; mas.title='Agregar fondo personalizado';
  mas.style.cssText='display:flex;align-items:center;justify-content:center;color:var(--ccdd3dc,#cdd3dc);background:var(--c181d26,#181d26);font-size:13px';
  mas.onclick=()=>elegirColor(estado.fondo||'#0b0d12', async c=>{
    (estado.coloresFondos=estado.coloresFondos||[]).push(c);
    await guardarColores(); coloresMemo=''; renderPaletas();
    usar(c);
  });
  cont.appendChild(mas);
}

// Rearma las dos paletas SOLO si las listas personalizadas cambiaron.
let coloresMemo=null;
function renderPaletas(){
  const memo=JSON.stringify([estado.coloresObjetos||[], estado.coloresFondos||[]]);
  if(memo===coloresMemo)return;
  coloresMemo=memo;
  armarSwatchesObjetos();
  armarSwatchesTexto();
  armarSwatchesFondos();
}

function pintarTodo(){
  aplicarFondo();
  renderPaletas();
  document.getElementById('contador').textContent=estado.items.length+' elemento(s)';
  for(const k in renderFormas) delete renderFormas[k];
  for(const k in asasNota) delete asasNota[k];
  for(const k in conectoresDe) delete conectoresDe[k];
  tablero.querySelectorAll('.item,.vacio,.forma-manija,.forma-rotor,.asa-mover,.figura-texto,.menuCtx,.conector,.etiqueta-bloqueo').forEach(n=>n.remove());
  // ⚠ La banda del borde tambien: vive en el SVG y no es .forma-wrap, asi que
  // sin esto se iba apilando una encima de otra en cada repintado.
  capa.querySelectorAll('.forma-wrap').forEach(n=>n.remove());
  capaAlta.querySelectorAll('.borde-conector').forEach(n=>n.remove());
  if(!estado.items.length){
    const v=document.createElement('div');
    v.className='vacio';
    v.innerHTML='Todavia no hay nada aca.<br>Elegi una herramienta arriba a la izquierda, o decile a Laura que anote algo.';
    tablero.appendChild(v);
    return;
  }
  for(const it of estado.items){
    if(FIGURAS.has(it.tipo)) crearForma(it);
    else if(TRAZOS.has(it.tipo)) crearTrazo(it);
    else tablero.appendChild(crearElemento(it));
  }
  // Las guias van SIEMPRE al final del SVG: si quedan antes de las figuras, un
  // rectangulo con relleno (por ejemplo uno bloqueado de fondo) las tapa y la
  // linea roja "desaparece" justo arriba del objeto con el que te alineas.
  capa.appendChild(guiaV); capa.appendChild(guiaH);
  // Las etiquetas van al final: necesitan medir los objetos ya dibujados.
  setTimeout(()=>{ for(const it of estado.items) if(it.bloqueado) crearEtiquetaBloqueo(it); }, 0);
  pintarSeleccion();
  // El overlay del recorte esta dibujado en pixeles: si se hizo zoom o se corrio
  // el lienzo, hay que rehacerlo o queda apuntando al lugar viejo.
  if(recorteEnCurso) dibujarRecorte();
}

// Nombre por defecto de un objeto bloqueado: lo que diga su texto, o el tipo.
const NOMBRES={rectangulo:'Rectángulo', circulo:'Círculo', linea:'Línea', flecha:'Flecha',
               imagen:'Imagen', lapiz:'Dibujo', nota:'Nota', pin:'Pin', texto:'Texto'};
function nombreDe(it){
  if(it.nombre) return it.nombre;
  // OJO: el JS vive dentro de un string de Python, asi que un "\\n" literal se lo
  // come Python y parte la linea. Se usa el codigo del caracter.
  const t=(it.texto||'').trim().split(String.fromCharCode(10))[0];
  return t ? (t.length>26 ? t.slice(0,26)+'…' : t) : (NOMBRES[it.tipo]||'Objeto');
}

// Etiqueta de un objeto bloqueado: unico punto de contacto con el. Un clic lo
// selecciona (para poder desbloquearlo con clic derecho), doble clic edita el
// nombre. El objeto en si no recibe ningun evento.
function crearEtiquetaBloqueo(it){
  const caja=cajaDe(it);
  const et=document.createElement('div');
  et.className='etiqueta-bloqueo';
  et.dataset.dueno=it.id;
  et.textContent=nombreDe(it);
  et.title='Bloqueado — clic para seleccionar, doble clic para renombrar';
  et.style.left=PX((caja.x1+caja.x2)/2)+'px';
  et.style.top=(PY(Math.min(caja.y1,caja.y2))-6)+'px';
  et.onclick=e=>{
    if(et.contentEditable==='true')return;
    e.stopPropagation(); ignorarProximoClick=true;
    alSeleccionar(it.id, e.shiftKey);
  };
  et.ondblclick=e=>{
    e.stopPropagation();
    et.contentEditable=true; bloquear=true; et.focus();
    document.execCommand('selectAll', false, null);
  };
  et.onblur=async()=>{
    if(et.contentEditable!=='true')return;
    et.contentEditable=false; bloquear=false;
    const nombre=et.textContent.trim() || nombreDe(it);
    et.textContent=nombre;
    it.nombre=nombre;
    await fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nombre})});
  };
  et.onkeydown=e=>{
    if(e.key==='Enter'||e.key==='Escape'){ e.preventDefault(); et.blur(); }
  };
  tablero.appendChild(et);
  return et;
}

async function refrescar(){
  if(bloquear)return;
  const r=await fetch('/pizarra/estado');
  const crudo=await r.text();
  // Si nada cambio, no reconstruir el DOM: el rearmado cada 2s hacia parpadear
  // los hovers y se sentia tosco aunque no hubiera ninguna novedad.
  if(crudo===ultimoEstadoCrudo)return;
  ultimoEstadoCrudo=crudo;
  estado=JSON.parse(crudo);
  ajustarImagenes();
  pintarTodo();
}

// --- Que una imagen se vea IGUAL en el telefono y en la compu ----------------
// ⚠⚠ Las unidades del tablero NO son cuadradas: la x se mide contra el ancho de la
// pantalla y la y contra el alto. O sea que la MISMA caja guardada da una forma
// distinta en cada pantalla — una captura metida desde el celular se veia mucho mas
// ancha en el escritorio (Martin, 2026-08-17: "veo las dimensiones de las imagenes
// diferentes en el celular que en el escritorio").
// La cura para las imagenes: al cargar el tablero se les corrige el ALTO de la caja
// para que, EN PIXELES DE ESTA PANTALLA, respeten su proporcion real. La cuenta sale
// de igualar pxW/pxH a la proporcion de la foto y el zoom se cancela solo:
//     altoUnidades = anchoUnidades * (anchoPantalla / altoPantalla) / proporcion
// No se guarda nada: es un ajuste de como se DIBUJA acá. Si despues la movés, ahí sí
// se guarda ya corregida, y la otra pantalla la vuelve a acomodar a la suya.
const RATIO_IMG={};        // archivo -> ancho/alto natural (null = pedida, todavia no llego)

function ajustarImagenes(){
  if(!estado || !estado.items) return;
  const W=tablero.clientWidth, H=tablero.clientHeight;
  if(!W || !H) return;
  let cambio=false;
  for(const it of estado.items){
    if(it.tipo!=='imagen' || !it.archivo) continue;
    const nat=RATIO_IMG[it.archivo];
    if(nat===undefined){                       // primera vez: se mide la foto
      RATIO_IMG[it.archivo]=null;
      const im=new Image();
      im.onload=()=>{ RATIO_IMG[it.archivo]=im.width/im.height;
                      if(ajustarImagenes()) pintarTodo(); };
      im.onerror=()=>{ RATIO_IMG[it.archivo]=0; };
      im.src='/pizarra/imagen/'+it.archivo;
      continue;
    }
    if(!nat) continue;                         // sin medir todavia, o rota
    const r=recorteDe(it);
    const prop=nat*((r.x2-r.x1)/(r.y2-r.y1));  // proporcion de lo que se ve
    const wU=Math.abs(it.x2-it.x1);
    const hU=wU*(W/H)/prop;
    const alto=Math.abs(it.y2-it.y1);
    if(Math.abs(alto-hU) < Math.max(0.05, alto*0.005)) continue;   // ya esta bien
    const x=Math.min(it.x1,it.x2), y=Math.min(it.y1,it.y2);
    it.x1=x; it.x2=x+wU; it.y1=y; it.y2=y+hU;
    cambio=true;
  }
  return cambio;
}

// Repintado por camara agrupado por frame: una rafaga de ruedazos pinta UNA vez.
let rafCamara=null;
function camaraCambio(){
  if(rafCamara)return;
  rafCamara=requestAnimationFrame(()=>{ rafCamara=null; pintarTodo(); });
}

function crearElemento(it){
  let posConect=null;   // reposicionador de los puntitos de conexion
  const div=document.createElement('div');
  div.className='item';
  div.dataset.id=it.id;
  div.style.left=PX(it.x)+'px'; div.style.top=PY(it.y)+'px';
  // Las notas/pines son HTML de tamano fijo: el zoom les entra por transform.
  div.style.transform='translate(-50%,-50%) scale('+camara.zoom+')';
  div.style.opacity=(it.opacidad!=null?it.opacidad:100)/100;
  let txt;
  if(it.tipo==='pin'){
    div.classList.add('pin');
    const punto=document.createElement('div'); punto.className='punto'; punto.style.background=it.color;
    txt=document.createElement('div'); txt.className='etiqueta'; txt.textContent=it.texto;
    const ctPin=colorTextoDe(it); if(ctPin) txt.style.color=ctPin;
    div.append(punto, txt);
  } else if(it.tipo==='texto'){
    div.classList.add('texto');
    div.style.color=it.color;
    txt=document.createElement('div'); txt.className='txt'; txt.textContent=it.texto;
    aplicarEstiloTexto(div, it, 20);
    div.append(txt);
  } else {
    div.classList.add('nota'); div.style.background=it.color;
    const ctNota=colorTextoDe(it); if(ctNota) div.style.color=ctNota;
    if(it.w){ div.style.width=it.w+'px'; div.style.maxWidth='none'; div.style.minWidth='none'; }
    if(it.h){ div.style.height=it.h+'px'; }
    txt=document.createElement('div'); txt.className='txt'; txt.textContent=it.texto;
    const fecha=document.createElement('div'); fecha.className='fecha'; fecha.textContent=it.creado;
    const resize=document.createElement('div'); resize.className='resize'; resize.title='Estirar (ancho y alto)';
    resize.addEventListener('pointerdown', e=>{
      if(e.button!==0)return;
      e.stopPropagation();
      bloquear=true;
      guardarSnapshot();
      const r0=tablero.getBoundingClientRect();
      const px0=e.clientX, py0=e.clientY;
      // getBoundingClientRect viene ESCALADO por el zoom (transform): se divide
      // para trabajar siempre en pixeles "reales" de la nota.
      const anchoInicial=div.getBoundingClientRect().width/camara.zoom;
      const altoInicial=div.getBoundingClientRect().height/camara.zoom;
      const mover=ev=>{
        // *2 porque el div esta centrado (translate -50%,-50%): el borde
        // se mueve la mitad de lo que crece el tamano total.
        let dx=(ev.clientX-px0)/camara.zoom*2, dy=(ev.clientY-py0)/camara.zoom*2;
        // Guias tambien al estirar la nota: la esquina de abajo a la derecha se
        // engancha a los bordes/centros de los demas objetos.
        const rt=tablero.getBoundingClientRect();
        const esq={x:escenaX(ev.clientX-rt.left), y:escenaY(ev.clientY-rt.top)};
        const aj=ajustarConGuias(it.id, [esq.x], [esq.y], 0, 0);
        mostrarGuias(aj.guiaX, aj.guiaY);
        // el enganche viene en unidades de escena: se pasa a pixeles de la nota
        // (sin el zoom, porque el div ya se escala aparte) y por 2 por el centrado.
        dx+=LX(aj.dx)/camara.zoom*2;
        dy+=LY(aj.dy)/camara.zoom*2;
        div.style.width=Math.max(90, Math.min(700, anchoInicial+dx))+'px';
        div.style.height=Math.max(48, Math.min(700, altoInicial+dy))+'px';
        div.style.maxWidth='none'; div.style.minWidth='none';
        if(posConect) posConect();
      };
      const soltar=async()=>{
        document.removeEventListener('pointermove', mover);
        document.removeEventListener('pointerup', soltar);
        bloquear=false;
        ocultarGuias();
        const rr=div.getBoundingClientRect();
        it.w=Math.round(rr.width/camara.zoom); it.h=Math.round(rr.height/camara.zoom);
        await fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({w:it.w, h:it.h})});
        await reatarFlechas(it.id);
      };
      document.addEventListener('pointermove', mover);
      document.addEventListener('pointerup', soltar);
    });
    div.append(txt, fecha, resize);
  }
  // Entrar en edicion del texto. Dispara con doble clic SIEMPRE, y con un solo
  // clic si la nota ya estaba seleccionada (patron "clic selecciona, otro clic
  // edita"): asi editar cuesta un clic pero se puede seguir arrastrando la nota
  // agarrandola del texto.
  function entrarEdicion(seleccionarTodo){
    if(txt.contentEditable==='true')return;
    guardarSnapshot();
    txt.contentEditable=true; bloquear=true; txt.focus();
    if(seleccionarTodo){ document.execCommand('selectAll', false, null); return; }
    // Cursor AL FINAL del texto (no donde tocaste): asi seguis escribiendo de
    // corrido, que es lo que uno espera al entrar a una nota ya escrita.
    const rango=document.createRange();
    rango.selectNodeContents(txt);
    rango.collapse(false);
    const sel=window.getSelection();
    sel.removeAllRanges(); sel.addRange(rango);
  }
  div.dataset.editar='1';
  div._entrarEdicion=entrarEdicion;
  div._esTexto=n=>txt===n || txt.contains(n);
  txt.ondblclick=e=>{ e.stopPropagation(); entrarEdicion(true); };
  txt.onblur=()=>{
    if(txt.contentEditable!=='true')return;
    txt.contentEditable=false; bloquear=false;
    // innerText (no textContent): conserva los saltos de linea que escribiste.
    guardarTexto(it.id, txt.innerText);
  };
  // Enter = salto de linea (pedido de Martin). Se confirma con Escape o clic
  // afuera. insertLineBreak inserta un <br> limpio en vez del <div> que mete
  // el navegador por defecto, que ensuciaba el texto guardado.
  txt.onkeydown=e=>{
    if(e.key==='Enter'){ e.preventDefault(); document.execCommand('insertLineBreak'); }
    else if(e.key==='Escape'){ e.preventDefault(); txt.blur(); }
  };
  hacerArrastrable(div, it.id, txt);
  // Los puntitos de conexion se crean tras insertar el div (necesitan medirlo).
  if(!it.bloqueado)
    setTimeout(()=>{ posConect=crearConectores(it, div); renderFormas['n'+it.id]=posConect; }, 0);
  return div;
}

// Puntas del dibujo a mano alzada. La idea de "adelgaza segun la velocidad" para
// lapiz/birome y "ancho parejo" para fibra/resaltador sale de como lo resuelven
// otras pizarras (Drawesome); Excalidraw todavia no tiene resaltador.
const PUNTAS={
  lapiz:      {factor:0.9, cap:'round',  alfa:0.85, variable:true},
  birome:     {factor:0.7, cap:'round',  alfa:1,    variable:true},
  fibra:      {factor:1.6, cap:'round',  alfa:1,    variable:false},
  resaltador: {factor:6,   cap:'square', alfa:0.35, variable:false, multiplicar:true},
};

// Opciones de rough.js por item, con los defaults de Excalidraw adaptados:
// grosor 2, trazo solido, relleno hachurado. El seed fijo por id hace que el
// garabato sea SIEMPRE el mismo para esa figura (no "baila" al repintar).
function opcionesRough(it){
  const z=camara.zoom;
  const g=(it.grosor||2)*z;   // el trazo se escala con el zoom, como en Excalidraw
  const o={stroke:it.color, strokeWidth:g, roughness:1.2,
           seed:((it.id*7919)%2147483000)+1, preserveVertices:true};
  const est=it.lineaEstilo||'solido';
  if(est==='rayado') o.strokeLineDash=[8*z, 8*z+g];
  else if(est==='punteado') o.strokeLineDash=[1.5*z, 6*z+g];
  if(it.tipo==='rectangulo' || it.tipo==='circulo'){
    const rel=it.relleno||'hachura';
    if(rel!=='ninguno'){
      o.fill=it.color;
      o.fillStyle=rel==='solido'?'solid':'hachure';
      o.fillWeight=g/2; o.hachureGap=g*4;
    }
  }
  return o;
}

// Tira una flecha nueva desde un punto del borde de `it`. `ancla` es {fx,fy}: en
// que fraccion de la caja nace, y ahi queda CLAVADA — la flecha lo sigue cuando
// la figura se mueve, se agranda o se rota. La otra punta, si cae sobre algo, se
// apoya en su borde apuntando al origen (esa sigue orbitando, como siempre).
function tirarFlechaDesde(it, ancla){
  const ns='http://www.w3.org/2000/svg';
  bloquear=true;
  const previa=document.createElementNS(ns,'line');
  previa.setAttribute('stroke','#6abdfc'); previa.setAttribute('stroke-width','2');
  previa.setAttribute('stroke-dasharray','6,5');
  capa.appendChild(previa);
  const origen=puntoAncla(it, ancla);
  previa.setAttribute('x1',PX(origen.x)); previa.setAttribute('y1',PY(origen.y));
  previa.setAttribute('x2',PX(origen.x)); previa.setAttribute('y2',PY(origen.y));
  let fin=origen;
  const mover=ev=>{
    fin=xyDesdeEvento(ev);
    previa.setAttribute('x2',PX(fin.x)); previa.setAttribute('y2',PY(fin.y));
  };
  const soltar=async()=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    bloquear=false;
    previa.remove();
    if(Math.hypot(fin.x-origen.x, fin.y-origen.y)<2)return;   // clic sin arrastre
    const destino=figuraCerca(fin.x, fin.y, it.id);
    guardarSnapshot();
    const cuerpo={tipo:'flecha', color:'var(--ce8eaed,#e8eaed)', x1:origen.x, y1:origen.y,
                  atadaA:{inicio:it.id, fin:destino?destino.id:null,
                          anclaInicio:ancla, anclaFin:null}};
    if(destino){
      const p2=puntoDeApoyo(destino, origen.x, origen.y);
      cuerpo.x2=p2.x; cuerpo.y2=p2.y;
    } else { cuerpo.x2=fin.x; cuerpo.y2=fin.y; }
    await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(cuerpo)});
    refrescar();
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
}

// Con el dedo no existe "pasar por encima": el borde conectable se prende cuando
// el objeto esta seleccionado. En escritorio, al pasar el mouse, como draw.io.
const TACTIL=matchMedia('(pointer:coarse)').matches;
const conectoresDe={};   // id -> mostrar(v)

// ⭐ TODO el borde conecta, no solo 4 puntitos (pedido de Martin, 2026-08-17).
// Los 4 puntitos siguen como atajo y como pista visual de que se puede tirar una
// flecha; la novedad es la BANDA invisible pegada al contorno: se agarra desde
// cualquier punto y la flecha nace exactamente ahi. Sirve para figuras, imagenes,
// notas, pines y textos. Devuelve la funcion que reposiciona todo.
// Objetos que son PURO trazo: una linea, una flecha o un garabato del lapiz. No
// tienen adentro, asi que su borde es el objeto entero.
const PURO_TRAZO=t=>t==='linea'||t==='flecha'||TRAZOS.has(t);

// Los puntos de conexion de un objeto de puro trazo: principio, mitad y final
// del recorrido, en fracciones de su caja (que es como los guarda el ancla).
function anclasDeTrazo(it){
  const pts=TRAZOS.has(it.tipo) ? it.puntos : [{x:it.x1,y:it.y1},{x:it.x2,y:it.y2}];
  const medio=pts.length>2 ? pts[Math.floor(pts.length/2)]
                           : {x:(pts[0].x+pts[1].x)/2, y:(pts[0].y+pts[1].y)/2};
  const c=cajaDe(it);
  const an=Math.abs(c.x2-c.x1)||1, al=Math.abs(c.y2-c.y1)||1;
  const minX=Math.min(c.x1,c.x2), minY=Math.min(c.y1,c.y2);
  const f=p=>[(p.x-minX)/an, (p.y-minY)/al];
  return [f(pts[0]), f(medio), f(pts[pts.length-1])];
}

function crearConectores(it, zona){
  const ns='http://www.w3.org/2000/svg';
  const conectores=[];
  const trazo=PURO_TRAZO(it.tipo);

  // La banda del contorno. Va en el SVG y no como div para poder seguir la forma
  // (un circulo conecta por su elipse, no por su caja) y rotar con la figura.
  // ⚠ Los objetos de puro trazo NO llevan banda: como no tienen adentro, la banda
  // taparia el objeto entero y arrastrar una linea crearia una flecha en vez de
  // moverla. Esos se conectan por sus 3 puntitos (principio, mitad y final), que
  // es lo mismo que hacen draw.io y Excalidraw.
  let banda=null;
  if(!trazo){
    banda=document.createElementNS(ns, it.tipo==='circulo'?'ellipse':'rect');
    banda.classList.add('borde-conector');
    banda.dataset.dueno=it.id;
    banda.setAttribute('fill','none');
    // Ancho de la banda: la mitad cae adentro y la mitad afuera del contorno.
    // ⚠ Con tope segun el lado MAS CORTO del objeto: en una barra finita la banda
    // entera tapaba la figura y no quedaba ni un pixel para agarrarla y moverla —
    // cada toque creaba una flecha en vez de correrla (Martin, 2026-08-17).
    // El ancho real se fija en posicionar(), que es quien conoce el tamaño.
    capaAlta.appendChild(banda);
    banda.addEventListener('pointerdown', e=>{
      if(e.button!==0 || espacio)return;
      if(herramienta!=='mover')return;   // hay una herramienta armada: dejar dibujar
      e.stopPropagation();
      tirarFlechaDesde(it, anclaDesde(it, xyDesdeEvento(e)));
    });
  }

  for(const [fx,fy] of (trazo ? anclasDeTrazo(it) : [[0.5,0],[0.5,1],[0,0.5],[1,0.5]])){
    const c=document.createElement('div');
    c.className='conector'; c.title='Arrastrá para conectar';
    c.dataset.dueno=it.id;
    tablero.appendChild(c);
    conectores.push({el:c, fx, fy});
    c.addEventListener('pointerdown', e=>{
      if(e.button!==0 || espacio)return;
      if(herramienta!=='mover')return;
      e.stopPropagation();
      // ⚠ El puntito ahora clava DONDE ESTA. Antes pasaba su posicion por
      // puntoDeApoyo() y la flecha salia del lado al que la arrastrabas: tirar
      // del puntito de arriba y llevarla a la derecha daba una flecha naciendo
      // en el borde derecho. Los 4 puntitos eran decorativos.
      tirarFlechaDesde(it, {fx, fy});
    });
  }
  const posicionar=()=>{
    const caja=cajaDe(it);
    const ang=it.angulo||0;
    const cx=PX((caja.x1+caja.x2)/2), cy=PY((caja.y1+caja.y2)/2);
    const x=PX(Math.min(caja.x1,caja.x2)), y=PY(Math.min(caja.y1,caja.y2));
    const an=Math.max(1, LX(Math.abs(caja.x2-caja.x1))), al=Math.max(1, LY(Math.abs(caja.y2-caja.y1)));
    if(banda){
      // Nunca mas gruesa que el 40 % del lado corto: siempre queda un nucleo para
      // agarrar y mover. Minimo 4 px, o no se podria conectar en nada finito.
      const tope=Math.max(4, Math.min(an, al)*0.4);
      banda.setAttribute('stroke-width', Math.min(TACTIL?18:11, tope));
      if(it.tipo==='circulo'){
        banda.setAttribute('cx',x+an/2); banda.setAttribute('cy',y+al/2);
        banda.setAttribute('rx',an/2); banda.setAttribute('ry',al/2);
      } else {
        banda.setAttribute('x',x); banda.setAttribute('y',y);
        banda.setAttribute('width',an); banda.setAttribute('height',al);
      }
      if(ang) banda.setAttribute('transform','rotate('+ang+' '+cx+' '+cy+')');
      else banda.removeAttribute('transform');
    }
    // ⚠ Los puntitos van APOYADOS AFUERA del borde, no centrados encima. Miden 9 px
    // (14 con el dedo): en una barra de 8 px de alto, el de arriba y el de abajo
    // tapaban la figura entera y no quedaba nada para agarrar y moverla — cada
    // toque creaba una flecha (Martin, 2026-08-17). Afuera no le roban cuerpo a
    // nada, y siguen enganchando en el mismo punto del contorno.
    const salto=(TACTIL?14:9)/2 + 2;
    for(const {el,fx,fy} of conectores){
      const px=Math.min(caja.x1,caja.x2)+fx*Math.abs(caja.x2-caja.x1);
      const py=Math.min(caja.y1,caja.y2)+fy*Math.abs(caja.y2-caja.y1);
      let ex=PX(px), ey=PY(py);
      if(!trazo){
        if(fx===0) ex-=salto; else if(fx===1) ex+=salto;
        if(fy===0) ey-=salto; else if(fy===1) ey+=salto;
      }
      const p=ang?rotarPx(ex,ey,cx,cy,ang):{x:ex,y:ey};
      el.style.left=p.x+'px'; el.style.top=p.y+'px';
    }
  };
  posicionar();
  const mostrar=v=>{
    // ⚠ Con una herramienta armada los conectores NO se prenden. Si no, pasar el
    // mouse por una linea prende su puntito, el puntito queda encima de la nota
    // que hay abajo, y el dibujo no arranca — el mismo agujero mudo de la flecha
    // sobre las notas, pero por otro lado. Herramienta armada = dejar dibujar.
    const prender=!!v && herramienta==='mover';
    if(prender) posicionar();
    conectores.forEach(c=>c.el.classList.toggle('activo', prender));
    if(banda) banda.classList.toggle('activo', prender);
  };
  conectoresDe[it.id]=mostrar;
  if(TACTIL && seleccion.has(it.id)) mostrar(true);
  zona.addEventListener('mouseenter',()=>mostrar(true));
  zona.addEventListener('mouseleave',()=>mostrar(false));
  if(banda){
    banda.addEventListener('mouseenter',()=>mostrar(true));
    banda.addEventListener('mouseleave',()=>mostrar(false));
  }
  for(const c of conectores){
    c.el.addEventListener('mouseenter',()=>mostrar(true));
    c.el.addEventListener('mouseleave',()=>mostrar(false));
  }
  return posicionar;
}

// ⭐ Asa de MOVER: un tirador dedicado abajo del objeto, para correrlo sin pelear
// con el borde conectable. Nace del reclamo de Martin (2026-08-17): en una figura
// finita el borde ocupa todo y cada toque creaba una flecha en vez de moverla.
// Va afuera y abajo, espejando al rotor (que va arriba), asi no pisa las esquinas
// ni los puntitos del medio de cada lado.
function crearAsaMover(it, arrancar){
  const asa=document.createElement('div');
  asa.className='asa-mover';
  asa.dataset.dueno=it.id;          // pintarSeleccion la muestra si esta seleccionado
  asa.textContent='✥';
  asa.title='Arrastrá para mover';
  asa.addEventListener('pointerdown', arrancar);
  tablero.appendChild(asa);
  return caja=>{
    const ang=it.angulo||0;
    const cx=PX((caja.x1+caja.x2)/2), cy=PY((caja.y1+caja.y2)/2);
    const abajo=PY(Math.max(caja.y1,caja.y2))+22;
    const p=ang?rotarPx(cx, abajo, cx, cy, ang):{x:cx, y:abajo};
    asa.style.left=p.x+'px'; asa.style.top=p.y+'px';
  };
}

function crearManija(grupo, it, campoX, campoY, actualizar){
  const m=document.createElement('div');
  m.className='forma-manija';
  m.dataset.dueno=it.id;   // pintarSeleccion la muestra solo si el objeto esta seleccionado
  m.style.left=PX(it[campoX])+'px'; m.style.top=PY(it[campoY])+'px';
  m.addEventListener('pointerdown', e=>{
    if(e.button!==0)return;
    e.stopPropagation();
    bloquear=true;
    guardarSnapshot();
    // Con la figura rotada, el puntero se "desrota" alrededor del centro (fijado
    // al agarrar) para que el tirador siga la esquina real y no la de pantalla.
    const rT=tablero.getBoundingClientRect();
    const cx0=PX((it.x1+it.x2)/2), cy0=PY((it.y1+it.y2)/2);
    const mover=ev=>{
      let p;
      if(it.angulo){
        const q=rotarPx(ev.clientX-rT.left, ev.clientY-rT.top, cx0, cy0, -it.angulo);
        p={x:escenaX(q.x), y:escenaY(q.y)};
      } else p=xyDesdeEvento(ev);
      // Guias tambien al REDIMENSIONAR: la esquina que arrastras se engancha a
      // los bordes y centros de los demas objetos, igual que al mover. Con la
      // figura rotada no aplica (los ejes ya no coinciden con la pantalla).
      if(!it.angulo){
        const aj=ajustarConGuias(it.id, [p.x], [p.y], 0, 0);
        p={x:p.x+aj.dx, y:p.y+aj.dy};
        mostrarGuias(aj.guiaX, aj.guiaY);
      }
      it[campoX]=p.x; it[campoY]=p.y;
      m.style.left=PX(p.x)+'px'; m.style.top=PY(p.y)+'px';
      actualizar();
    };
    const soltar=async()=>{
      document.removeEventListener('pointermove', mover);
      document.removeEventListener('pointerup', soltar);
      bloquear=false;
      ocultarGuias();
      await fetch('/pizarra/item/'+it.id, {method:'PUT', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({[campoX]:it[campoX], [campoY]:it[campoY]})});
      // La punta de una flecha se engancha/suelta segun donde quedo; una figura
      // que cambio de tamano re-apoya las flechas que tenga atadas.
      if(it.tipo==='flecha') await intentarAtar(it, campoX==='x1'?'inicio':'fin', it[campoX], it[campoY]);
      else await reatarFlechas(it.id);
    };
    document.addEventListener('pointermove', mover);
    document.addEventListener('pointerup', soltar);
  });
  grupo.addEventListener('mouseenter',()=>m.style.opacity='1');
  grupo.addEventListener('mouseleave',()=>m.style.opacity='0.5');
  m.addEventListener('mouseenter',()=>m.style.opacity='1');
  m.addEventListener('mouseleave',()=>m.style.opacity='0.5');
  tablero.appendChild(m);
  return m;
}

// --- Recortar una imagen -----------------------------------------------------
// El recorte NO toca el archivo ni sube nada: se guarda como {x1,y1,x2,y2} en
// FRACCIONES de la imagen original (0..1) y se dibuja agrandando la imagen y
// tapando lo que sobra con un clipPath del tamano de la caja. Elegido asi a
// proposito: se puede volver atras siempre, recortar de nuevo sobre lo ya
// recortado sin ir perdiendo calidad, y el mismo archivo puede estar en dos
// objetos con recortes distintos. Recortar de verdad el .png seria mas simple de
// dibujar y no tendria vuelta atras.
const RECORTE_MIN=0.04;   // 4% del original: mas chico que esto ya no se ve nada
const recorteDe=it=>{
  const r=it.recorte||{};
  return {x1:r.x1||0, y1:r.y1||0, x2:(r.x2==null?1:r.x2), y2:(r.y2==null?1:r.y2)};
};
// Imagen sobre la que se puede recortar: una sola, y no bloqueada.
function imagenParaRecortar(){
  if(seleccion.size!==1)return null;
  const it=estado.items.find(i=>seleccion.has(i.id));
  return (it && it.tipo==='imagen' && !it.bloqueado) ? it : null;
}

let recorteEnCurso=null;

// Pasa un evento del puntero a coordenadas de escena SIN la rotacion de la
// imagen: se recorta siempre en los ejes de la imagen, no en los de la pantalla
// (mismo truco que usa crearManija con una figura rotada).
function puntoRecorte(ev){
  const rc=recorteEnCurso, rt=tablero.getBoundingClientRect();
  let px=ev.clientX-rt.left, py=ev.clientY-rt.top;
  if(rc.angulo){
    const q=rotarPx(px, py, PX(rc.centro.x), PY(rc.centro.y), -rc.angulo);
    px=q.x; py=q.y;
  }
  return {x:escenaX(px), y:escenaY(py)};
}

function entrarRecorte(){
  const it=imagenParaRecortar();
  if(!it || recorteEnCurso)return;
  const r=recorteDe(it);
  const bx=Math.min(it.x1,it.x2), by=Math.min(it.y1,it.y2);
  const bw=Math.abs(it.x2-it.x1), bh=Math.abs(it.y2-it.y1);
  // La caja de hoy muestra solo la fraccion r del original: la imagen entera es
  // mas grande en esa proporcion, y arranca antes de donde arranca la caja.
  const fw=bw/(r.x2-r.x1), fh=bh/(r.y2-r.y1);
  recorteEnCurso={
    it, angulo:it.angulo||0,
    centro:{x:(it.x1+it.x2)/2, y:(it.y1+it.y2)/2},
    entera:{x:bx-r.x1*fw, y:by-r.y1*fh, w:fw, h:fh},
    sel:{x1:bx, y1:by, x2:bx+bw, y2:by+bh}
  };
  // ⚠ El auto-refresco rearma todo el DOM cada 2,5 s y se llevaria puesto el
  // overlay a mitad del recorte. Tambien apaga el arrastre del lienzo con un dedo.
  bloquear=true;
  tablero.classList.add('recortando');
  document.getElementById('barraRecorte').classList.add('abierto');
  dibujarRecorte();
  refrescarPanel();
}

// Vuelve el recorte a la imagen entera, sin salir del modo: es el "me pase" y
// tambien la unica forma de sacar un recorte viejo desde el telefono.
function recorteEntero(){
  if(!recorteEnCurso)return;
  const e=recorteEnCurso.entera;
  recorteEnCurso.sel={x1:e.x, y1:e.y, x2:e.x+e.w, y2:e.y+e.h};
  dibujarRecorte();
}

async function salirRecorte(confirmar){
  const rc=recorteEnCurso;
  if(!rc)return;
  recorteEnCurso=null;
  document.querySelectorAll('.recorte-capa').forEach(n=>n.remove());
  capa.querySelectorAll('.recorte-oculto').forEach(gr=>gr.classList.remove('recorte-oculto'));
  tablero.classList.remove('recortando');
  document.getElementById('barraRecorte').classList.remove('abierto');
  bloquear=false;
  if(!confirmar){ refrescarPanel(); return; }

  const it=rc.it, s=rc.sel, e=rc.entera;
  const nuevo={x1:(s.x1-e.x)/e.w, y1:(s.y1-e.y)/e.h,
               x2:(s.x2-e.x)/e.w, y2:(s.y2-e.y)/e.h};
  const igual=Math.abs(nuevo.x1-recorteDe(it).x1)<1e-6 && Math.abs(nuevo.y1-recorteDe(it).y1)<1e-6 &&
              Math.abs(nuevo.x2-recorteDe(it).x2)<1e-6 && Math.abs(nuevo.y2-recorteDe(it).y2)<1e-6;
  if(igual){ refrescarPanel(); return; }   // no gastar un paso de deshacer al pedazo
  guardarSnapshot();

  let x1=s.x1, y1=s.y1, x2=s.x2, y2=s.y2;
  // ⚠ Con la imagen ROTADA hay que correr la caja. El dibujo gira alrededor del
  // centro de la caja, y al recortar el centro se mueve: sin esto, la imagen
  // "salta" al confirmar y queda en otro lado del que se veia. El corrimiento es
  // d - R(d), con d la distancia entre el centro viejo y el nuevo, y R la
  // rotacion; en PIXELES, porque el lienzo no es cuadrado y rotar en unidades de
  // escena deforma.
  if(rc.angulo){
    const cn={x:(x1+x2)/2, y:(y1+y2)/2};
    const dx=PX(rc.centro.x)-PX(cn.x), dy=PY(rc.centro.y)-PY(cn.y);
    const g=rotarPx(dx, dy, 0, 0, rc.angulo);
    const anchoPx=(tablero.clientWidth/100)*camara.zoom, altoPx=(tablero.clientHeight/100)*camara.zoom;
    const tx=(dx-g.x)/anchoPx, ty=(dy-g.y)/altoPx;
    x1+=tx; x2+=tx; y1+=ty; y2+=ty;
  }
  Object.assign(it, {x1, y1, x2, y2, recorte:nuevo});
  await fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({x1, y1, x2, y2, recorte:nuevo})});
  ultimoEstadoCrudo='';
  refrescar();
}

// Dibuja (o redibuja) el overlay: imagen entera en fantasma, el pedazo que queda
// a pleno encima, el borde punteado y las cuatro esquinas.
function dibujarRecorte(){
  const rc=recorteEnCurso;
  if(!rc)return;
  document.querySelectorAll('.recorte-capa').forEach(n=>n.remove());
  // Se esconde el dibujo real de esta imagen (y se rehace la marca en cada
  // repintado: el zoom rearma todo el SVG desde cero).
  capa.querySelectorAll('.forma-wrap').forEach(gr=>
    gr.classList.toggle('recorte-oculto', Number(gr.dataset.id)===rc.it.id));
  const ns='http://www.w3.org/2000/svg';
  const g=document.createElementNS(ns,'g');
  g.classList.add('recorte-capa');
  if(rc.angulo) g.setAttribute('transform','rotate('+rc.angulo+' '+PX(rc.centro.x)+' '+PY(rc.centro.y)+')');

  const e=rc.entera, s=rc.sel;
  const ex=PX(e.x), ey=PY(e.y), ew=LX(e.w), eh=LY(e.h);
  const sx=PX(Math.min(s.x1,s.x2)), sy=PY(Math.min(s.y1,s.y2));
  const sw=LX(Math.abs(s.x2-s.x1)), sh=LY(Math.abs(s.y2-s.y1));
  const href='/pizarra/imagen/'+rc.it.archivo;

  const img=(clase, clip)=>{
    const im=document.createElementNS(ns,'image');
    im.setAttribute('href',href); im.setAttribute('preserveAspectRatio','none');
    im.setAttribute('x',ex); im.setAttribute('y',ey);
    im.setAttribute('width',ew); im.setAttribute('height',eh);
    im.classList.add(clase);
    if(clip) im.setAttribute('clip-path','url(#recorte-vivo)');
    return im;
  };
  g.appendChild(img('recorte-fantasma', false));
  const clip=document.createElementNS(ns,'clipPath');
  clip.setAttribute('id','recorte-vivo');
  clip.setAttribute('clipPathUnits','userSpaceOnUse');
  const cr=document.createElementNS(ns,'rect');
  cr.setAttribute('x',sx); cr.setAttribute('y',sy);
  cr.setAttribute('width',sw); cr.setAttribute('height',sh);
  clip.appendChild(cr); g.appendChild(clip);
  g.appendChild(img('recorte-nitido', true));

  const borde=document.createElementNS(ns,'rect');
  borde.classList.add('recorte-borde');
  borde.setAttribute('x',sx); borde.setAttribute('y',sy);
  borde.setAttribute('width',sw); borde.setAttribute('height',sh);
  g.appendChild(borde);

  // Arrastrar el medio corre la ventana de recorte sin cambiarle el tamano.
  const adentro=document.createElementNS(ns,'rect');
  adentro.classList.add('recorte-adentro');
  adentro.setAttribute('x',sx); adentro.setAttribute('y',sy);
  adentro.setAttribute('width',sw); adentro.setAttribute('height',sh);
  adentro.addEventListener('pointerdown', ev=>arrastrarRecorte(ev, null));
  g.appendChild(adentro);

  // Esquinas: con el dedo van casi el doble de grandes que las manijas normales.
  const lado=matchMedia('(pointer:coarse)').matches?22:12;
  const ESQ=[['x1','y1','nwse-resize'],['x2','y1','nesw-resize'],
             ['x1','y2','nesw-resize'],['x2','y2','nwse-resize']];
  for(const [cx,cy,cursor] of ESQ){
    const q=document.createElementNS(ns,'rect');
    q.classList.add('recorte-esq');
    q.setAttribute('x',PX(s[cx])-lado/2); q.setAttribute('y',PY(s[cy])-lado/2);
    q.setAttribute('width',lado); q.setAttribute('height',lado);
    q.setAttribute('rx',3);
    q.style.cursor=cursor;
    q.addEventListener('pointerdown', ev=>arrastrarRecorte(ev, [cx,cy]));
    g.appendChild(q);
  }
  capa.appendChild(g);
}

// esquina = ['x1','y2'] para estirar por ahi, o null para correr todo el recorte.
function arrastrarRecorte(ev, esquina){
  if(ev.button!=null && ev.button!==0)return;
  ev.stopPropagation(); ev.preventDefault();
  const rc=recorteEnCurso;
  if(!rc)return;
  const e=rc.entera, inicio=puntoRecorte(ev);
  const base=Object.assign({}, rc.sel);
  const lim=(v,min,max)=>Math.max(min, Math.min(max, v));
  const mover=ev2=>{
    const p=puntoRecorte(ev2);
    const dx=p.x-inicio.x, dy=p.y-inicio.y;
    if(esquina){
      const [cx,cy]=esquina;
      // El minimo se mide contra la esquina de enfrente, que no se mueve.
      const opX=(cx==='x1')?base.x2:base.x1, opY=(cy==='y1')?base.y2:base.y1;
      const minW=e.w*RECORTE_MIN, minH=e.h*RECORTE_MIN;
      rc.sel[cx]=(cx==='x1') ? lim(base.x1+dx, e.x, opX-minW) : lim(base.x2+dx, opX+minW, e.x+e.w);
      rc.sel[cy]=(cy==='y1') ? lim(base.y1+dy, e.y, opY-minH) : lim(base.y2+dy, opY+minH, e.y+e.h);
    } else {
      // Correr la ventana entera: no puede salirse de la imagen.
      const w=base.x2-base.x1, h=base.y2-base.y1;
      const nx=lim(base.x1+dx, e.x, e.x+e.w-w), ny=lim(base.y1+dy, e.y, e.y+e.h-h);
      rc.sel={x1:nx, y1:ny, x2:nx+w, y2:ny+h};
    }
    dibujarRecorte();
  };
  const soltar=()=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
}

function crearForma(it){
  const ns='http://www.w3.org/2000/svg';
  const grupo=document.createElementNS(ns,'g');
  grupo.classList.add('forma-wrap');
  grupo.dataset.id=it.id;
  const tapa=document.createElementNS(ns, (it.tipo==='rectangulo'||it.tipo==='imagen')?'rect':it.tipo==='circulo'?'ellipse':'line');
  tapa.classList.add('forma-tapa');
  // linea/flecha no tienen relleno: necesitan el trazo mas grueso para poder
  // agarrarlas con el mouse. rectangulo/circulo ya tienen area propia (el
  // relleno), un trazo extra ancho los hacia atrapar clics de las figuras
  // vecinas por accidente.
  tapa.setAttribute('stroke-width', (it.tipo==='linea'||it.tipo==='flecha') ? '10' : '0');
  grupo.appendChild(tapa);
  // El dibujo visible lo genera rough.js (a mano alzada) y se REGENERA en cada
  // repintado con el mismo seed: mover la figura no le cambia el garabato. La
  // punta de flecha va como dos rayitas del mismo estilo, no un marker (el
  // marker tenia el color clavado y toda flecha quedaba azul).
  let visR=null;
  let imgEl=null, imgClip=null;
  if(it.tipo==='imagen'){
    imgEl=document.createElementNS(ns,'image');
    imgEl.setAttribute('href','/pizarra/imagen/'+it.archivo);
    imgEl.setAttribute('preserveAspectRatio','none');
    imgEl.classList.add('forma');
    // Recortada: se dibuja la imagen ENTERA, mas grande que la caja, y se tapa
    // lo que sobra con este clipPath. Va en userSpaceOnUse y en el mismo grupo,
    // asi la rotacion y el arrastre se los lleva a los dos juntos.
    const clip=document.createElementNS(ns,'clipPath');
    clip.setAttribute('id','recorte-'+it.id);
    clip.setAttribute('clipPathUnits','userSpaceOnUse');
    imgClip=document.createElementNS(ns,'rect');
    clip.appendChild(imgClip);
    grupo.appendChild(clip);
    imgEl.setAttribute('clip-path','url(#recorte-'+it.id+')');
    grupo.insertBefore(imgEl, tapa);
  }
  const pintar=()=>{
    if(it.tipo==='rectangulo'||it.tipo==='imagen'){
      tapa.setAttribute('x',PX(Math.min(it.x1,it.x2))); tapa.setAttribute('y',PY(Math.min(it.y1,it.y2)));
      tapa.setAttribute('width',LX(Math.abs(it.x2-it.x1))); tapa.setAttribute('height',LY(Math.abs(it.y2-it.y1)));
    } else if(it.tipo==='circulo'){
      tapa.setAttribute('cx',PX((it.x1+it.x2)/2)); tapa.setAttribute('cy',PY((it.y1+it.y2)/2));
      tapa.setAttribute('rx',LX(Math.abs(it.x2-it.x1)/2)); tapa.setAttribute('ry',LY(Math.abs(it.y2-it.y1)/2));
    } else {
      tapa.setAttribute('x1',PX(it.x1)); tapa.setAttribute('y1',PY(it.y1));
      tapa.setAttribute('x2',PX(it.x2)); tapa.setAttribute('y2',PY(it.y2));
    }
    if(imgEl){
      const x=PX(Math.min(it.x1,it.x2)), y=PY(Math.min(it.y1,it.y2));
      const w=LX(Math.abs(it.x2-it.x1)), h=LY(Math.abs(it.y2-it.y1));
      const r=recorteDe(it);
      // ⭐⭐ La imagen se dibuja RESPETANDO SU PROPORCION, no estirada a la caja.
      // Las unidades del tablero no son cuadradas —la x se mide contra el ancho de
      // la pantalla y la y contra el alto—, asi que la MISMA caja da una forma
      // distinta en el telefono que en la compu: una captura metida desde el celular
      // se veia mucho mas ancha en el escritorio (Martin, 2026-08-17). Con `meet` la
      // foto se acomoda adentro de la caja sin deformarse y se ve igual en los dos;
      // lo que puede quedar mas grande que la foto es la caja de seleccion.
      // ⚠ Recortada NO: ahi se dibuja la imagen entera agrandada y se tapa lo que
      // sobra, y esa cuenta necesita que llene la caja exacta (con `meet` el recorte
      // mostraria otro pedazo).
      const recortada = r.x1>0 || r.y1>0 || r.x2<1 || r.y2<1;
      imgEl.setAttribute('preserveAspectRatio', recortada ? 'none' : 'xMidYMid meet');
      // Sin recorte esto da fw=w y x-0*fw=x: la imagen entera, como siempre.
      const fw=w/Math.max(0.001, r.x2-r.x1), fh=h/Math.max(0.001, r.y2-r.y1);
      imgEl.setAttribute('x', x-r.x1*fw); imgEl.setAttribute('y', y-r.y1*fh);
      imgEl.setAttribute('width', fw); imgEl.setAttribute('height', fh);
      imgClip.setAttribute('x',x); imgClip.setAttribute('y',y);
      imgClip.setAttribute('width',w); imgClip.setAttribute('height',h);
    } else {
      const o=opcionesRough(it);
      let n;
      if(it.tipo==='rectangulo'){
        n=rc.rectangle(PX(Math.min(it.x1,it.x2)),PY(Math.min(it.y1,it.y2)),
                       LX(Math.abs(it.x2-it.x1)),LY(Math.abs(it.y2-it.y1)),o);
      } else if(it.tipo==='circulo'){
        n=rc.ellipse(PX((it.x1+it.x2)/2),PY((it.y1+it.y2)/2),
                     LX(Math.abs(it.x2-it.x1)),LY(Math.abs(it.y2-it.y1)),o);
      } else {
        n=rc.line(PX(it.x1),PY(it.y1),PX(it.x2),PY(it.y2),o);
        if(it.tipo==='flecha'){
          const g2=document.createElementNS(ns,'g');
          g2.appendChild(n);
          const dx=PX(it.x2)-PX(it.x1), dy=PY(it.y2)-PY(it.y1);
          const ang=Math.atan2(dy,dx), L=Math.min(20,Math.hypot(dx,dy)*0.4), A=Math.PI/7;
          const oPunta=Object.assign({}, o, {strokeLineDash:undefined, fill:undefined});
          g2.appendChild(rc.linearPath([
            [PX(it.x2)-L*Math.cos(ang-A), PY(it.y2)-L*Math.sin(ang-A)],
            [PX(it.x2), PY(it.y2)],
            [PX(it.x2)-L*Math.cos(ang+A), PY(it.y2)-L*Math.sin(ang+A)]
          ], oPunta));
          n=g2;
        }
      }
      n.classList.add('forma');
      if(visR) grupo.replaceChild(n, visR); else grupo.insertBefore(n, tapa);
      visR=n;
    }
    // Rotacion: el grupo entero gira alrededor del centro (en pixeles, porque
    // la escena no es cuadrada y rotar en unidades de escena deforma).
    if(it.angulo){
      grupo.setAttribute('transform','rotate('+it.angulo+' '+PX((it.x1+it.x2)/2)+' '+PY((it.y1+it.y2)/2)+')');
    } else grupo.removeAttribute('transform');
  };
  pintar();
  grupo.style.opacity=(it.opacidad!=null?it.opacidad:100)/100;
  capa.appendChild(grupo);

  // La cruz va en una ESQUINA, no en el centro: si estuviera en el medio se
  // superponia justo con el punto donde se agarra la figura para arrastrarla,
  // y para no bloquear el arrastre terminaba con pointer-events:none la
  // mayoria del tiempo -- eso es lo que hacia que a veces no se pudiera
  // borrar (el clic le llegaba con el boton todavia "apagado"). En la esquina
  // no hace falta ese jueguito: siempre esta clickeable.
  const esquina=()=>({x:Math.max(it.x1,it.x2), y:Math.min(it.y1,it.y2)});

  // Texto adentro de la figura (rect/circulo): div HTML centrado, NO un <text>
  // del SVG -- el viewBox estirado (preserveAspectRatio=none) deformaria las
  // letras. pointer-events:none para no bloquear el arrastre de la figura.
  let txtFig=null;
  function posicionarTxtFig(){
    if(!txtFig)return;
    txtFig.style.left=PX((it.x1+it.x2)/2)+'px'; txtFig.style.top=PY((it.y1+it.y2)/2)+'px';
    txtFig.style.maxWidth=Math.max(60, PX(Math.max(it.x1,it.x2)-1)-PX(Math.min(it.x1,it.x2)+1))+'px';
    aplicarEstiloTexto(txtFig, it, 13.5);
    txtFig.style.transform='translate(-50%,-50%) rotate('+(it.angulo||0)+'deg)';
  }
  function asegurarTxtFig(){
    if(!txtFig){
      txtFig=document.createElement('div');
      txtFig.className='figura-texto';
      tablero.appendChild(txtFig);
    }
    posicionarTxtFig();
    return txtFig;
  }
  // Doble clic sobre una imagen = recortarla, igual que en Figma. Es el atajo de
  // escritorio; en el telefono se entra por la tijera de la barra.
  if(it.tipo==='imagen'){
    tapa.addEventListener('dblclick', e=>{
      e.stopPropagation();
      if(it.bloqueado)return;
      alSeleccionar(it.id, false);
      entrarRecorte();
    });
  }
  if((it.tipo==='rectangulo'||it.tipo==='circulo') && it.texto) asegurarTxtFig().textContent=it.texto;
  if(it.tipo==='rectangulo'||it.tipo==='circulo'){
    tapa.addEventListener('dblclick', e=>{
      e.stopPropagation();
      guardarSnapshot();
      const t=asegurarTxtFig();
      t.contentEditable=true; bloquear=true; t.focus();
      document.execCommand('selectAll', false, null);
      t.onblur=async()=>{
        if(t.contentEditable!=='true')return;
        t.contentEditable=false; bloquear=false;
        const texto=t.innerText.trim();   // innerText: conserva los saltos de linea
        it.texto=texto;
        if(!texto){ t.remove(); txtFig=null; }
        await fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({texto})});
      };
      t.onkeydown=ev=>{
        if(ev.key==='Enter'){ ev.preventDefault(); document.execCommand('insertLineBreak'); }
        else if(ev.key==='Escape'){ ev.preventDefault(); t.blur(); }
      };
    });
  }

  const refrescarBotones=()=>{ posicionarTxtFig(); };

  // ⭐ El arranque del arrastre vive aparte para que el ASA DE MOVER pueda usar el
  // mismo camino que tocar la figura: un solo lugar donde se mueve una figura.
  const arrancarArrastre=e=>{
    if(e.button!==0 || espacio)return;
    if(herramienta!=='mover')return;   // herramienta de dibujo armada: dejar dibujar ENCIMA de la figura
    e.stopPropagation();
    if(it.bloqueado)return;   // bloqueado: solo se toca por su etiqueta
    if(it.grupo && !seleccion.has(it.id)){ alSeleccionar(it.id, false); }
    if(seleccion.has(it.id) && seleccion.size>1){ dragGrupal(e, it.id); return; }
    bloquear=true;
    guardarSnapshot();
    const inicio=xyDesdeEvento(e);
    let movio=false;
    const base={x1:it.x1,y1:it.y1,x2:it.x2,y2:it.y2};
    const candX=[base.x1,base.x2,(base.x1+base.x2)/2], candY=[base.y1,base.y2,(base.y1+base.y2)/2];
    // Igual que el trazo: durante el arrastre NO se regenera el dibujo a mano
    // alzada (rough.js hace decenas de trazos por figura). Se corre el grupo con
    // un transform y se repinta una sola vez al soltar.
    const mover=ev=>{
      const p=xyDesdeEvento(ev);
      let dx=p.x-inicio.x, dy=p.y-inicio.y;
      if(Math.hypot(dx,dy)>0.5) movio=true;
      const ajuste=ajustarConGuias(it.id, candX, candY, dx, dy);
      dx=ajuste.dx; dy=ajuste.dy;
      it.x1=base.x1+dx; it.y1=base.y1+dy; it.x2=base.x2+dx; it.y2=base.y2+dy;
      // El rotate va con el centro ORIGINAL: el translate se aplica primero y
      // ya lleva la figura (y su centro) al lugar nuevo.
      const rot=it.angulo ? ' rotate('+it.angulo+' '+PX((base.x1+base.x2)/2)+' '+PY((base.y1+base.y2)/2)+')' : '';
      grupo.setAttribute('transform','translate('+LX(dx)+','+LY(dy)+')'+rot);
      refrescarBotones(); refrescarManijas();
      reatarEnVivo(it.id);
      mostrarGuias(ajuste.guiaX, ajuste.guiaY);
    };
    const soltar=async(ev)=>{
      document.removeEventListener('pointermove', mover);
      document.removeEventListener('pointerup', soltar);
      bloquear=false;
      ocultarGuias();
      if(!movio){
        it.x1=base.x1; it.y1=base.y1; it.x2=base.x2; it.y2=base.y2;
        grupo.removeAttribute('transform'); pintar();
        olvidarSnapshot();
        alSeleccionar(it.id, ev.shiftKey);
        return;
      }
      // Se repinta UNA sola vez, ya en la posicion final.
      grupo.removeAttribute('transform');
      pintar(); refrescarBotones(); refrescarManijas();
      alSeleccionar(it.id, false);
      const cuerpo={x1:it.x1,y1:it.y1,x2:it.x2,y2:it.y2};
      // Arrastrar una flecha ENTERA la desengancha (las puntas se fueron de las
      // figuras); mover una figura re-apoya las flechas que la siguen.
      if(it.tipo==='flecha' && it.atadaA && (it.atadaA.inicio!=null || it.atadaA.fin!=null)){
        it.atadaA={inicio:null,fin:null}; cuerpo.atadaA=it.atadaA;
      }
      await fetch('/pizarra/item/'+it.id, {method:'PUT', headers:{'Content-Type':'application/json'},
        body:JSON.stringify(cuerpo)});
      await reatarFlechas(it.id);
    };
    document.addEventListener('pointermove', mover);
    document.addEventListener('pointerup', soltar);
  };
  tapa.addEventListener('pointerdown', arrancarArrastre);

  // Tiradores: arrastrar cada uno cambia SOLO los campos que le tocan, dejando
  // la esquina opuesta fija como ancla (mismo truco que usa Excalidraw: nunca
  // se mueven los dos puntos juntos, eso es lo que hace la tapa). Linea/flecha
  // solo tienen 2 puntas de verdad (sus dos extremos); rectangulo/circulo
  // tienen caja, asi que se agregan las otras 2 esquinas (x1,y2) y (x2,y1).
  let posConectores=()=>{};   // la asigna el bloque de conectores, mas abajo

  // Tirador de ROTACION (estilo Excalidraw): circulo arriba del borde superior,
  // gira alrededor del centro; con Shift se engancha cada 15 grados.
  let rotor=null;
  function posicionarRotor(){
    if(!rotor)return;
    const cx=PX((it.x1+it.x2)/2), cy=PY((it.y1+it.y2)/2);
    const arriba=PY(Math.min(it.y1,it.y2))-22;
    const p=rotarPx(cx, arriba, cx, cy, it.angulo||0);
    rotor.style.left=p.x+'px'; rotor.style.top=p.y+'px';
  }
  if(CAJA(it.tipo)){
    rotor=document.createElement('div');
    rotor.className='forma-rotor'; rotor.title='Rotar (Shift: de a 15°)';
    rotor.dataset.dueno=it.id;
    tablero.appendChild(rotor);
    rotor.addEventListener('pointerdown', e=>{
      if(e.button!==0)return;
      e.stopPropagation();
      bloquear=true; guardarSnapshot();
      const r=tablero.getBoundingClientRect();
      const cx=PX((it.x1+it.x2)/2), cy=PY((it.y1+it.y2)/2);
      const mover=ev=>{
        let ang=Math.atan2((ev.clientY-r.top)-cy, (ev.clientX-r.left)-cx)*180/Math.PI+90;
        if(ev.shiftKey) ang=Math.round(ang/15)*15;
        it.angulo=Math.round(((ang%360)+360)%360);
        pintar(); refrescarManijas(); refrescarBotones();
      };
      const soltar=async()=>{
        document.removeEventListener('pointermove', mover);
        document.removeEventListener('pointerup', soltar);
        bloquear=false;
        await fetch('/pizarra/item/'+it.id,{method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({angulo:it.angulo})});
      };
      document.addEventListener('pointermove', mover);
      document.addEventListener('pointerup', soltar);
    });
  }

  // Cursor por esquina como Excalidraw: nwse en la diagonal principal
  // (arriba-izq / abajo-der), nesw en la otra. Se recalcula al mover porque
  // arrastrando un tirador la esquina puede pasar al otro lado.
  function cursorManija(m, hx, hy){
    const izq = hx <= Math.min(it.x1,it.x2)+0.01, arr = hy <= Math.min(it.y1,it.y2)+0.01;
    m.style.cursor = (izq===arr) ? 'nwse-resize' : 'nesw-resize';
  }
  // El asa de mover, para las figuras que tienen caja (rect, circulo, imagen).
  let posAsa=null;
  if(CAJA(it.tipo) && !it.bloqueado) posAsa=crearAsaMover(it, arrancarArrastre);

  function refrescarManijas(){
    if(posAsa) posAsa({x1:it.x1, y1:it.y1, x2:it.x2, y2:it.y2});
    // Con rotacion, las manijas acompanan a la esquina rotada (rotan en px).
    const ang=it.angulo||0, cx=PX((it.x1+it.x2)/2), cy=PY((it.y1+it.y2)/2);
    const pos=(m,x,y)=>{
      const p=ang?rotarPx(PX(x),PY(y),cx,cy,ang):{x:PX(x),y:PY(y)};
      m.style.left=p.x+'px'; m.style.top=p.y+'px';
    };
    pos(m1,it.x1,it.y1); cursorManija(m1, it.x1, it.y1);
    pos(m2,it.x2,it.y2); cursorManija(m2, it.x2, it.y2);
    if(m3){ pos(m3,it.x1,it.y2); cursorManija(m3, it.x1, it.y2); }
    if(m4){ pos(m4,it.x2,it.y1); cursorManija(m4, it.x2, it.y1); }
    posicionarRotor();
    posConectores();
  }
  const actualizarManija=()=>{
    pintar(); refrescarBotones(); refrescarManijas();
    reatarEnVivo(it.id);
  };
  const m1=crearManija(grupo, it, 'x1', 'y1', actualizarManija);
  const m2=crearManija(grupo, it, 'x2', 'y2', actualizarManija);
  let m3=null, m4=null;
  if(CAJA(it.tipo)){
    m3=crearManija(grupo, it, 'x1', 'y2', actualizarManija);
    m4=crearManija(grupo, it, 'x2', 'y1', actualizarManija);
  }
  // Conectores para TODA figura, no solo las que tienen caja: una linea y una
  // flecha tambien reciben flechas ahora (pedido de Martin, 2026-08-17).
  if(!it.bloqueado) posConectores=crearConectores(it, grupo);

  refrescarManijas();   // deja puestos los cursores por esquina desde el arranque
  renderFormas[it.id]=()=>{ pintar(); refrescarBotones(); refrescarManijas(); };
}

function crearTrazo(it){
  const ns='http://www.w3.org/2000/svg';
  const grupo=document.createElementNS(ns,'g');
  grupo.classList.add('forma-wrap');
  grupo.dataset.id=it.id;
  const puntosStr=p=>p.map(pt=>PX(pt.x)+','+PY(pt.y)).join(' ');
  const punta=it.punta||'fibra';
  const cfg=PUNTAS[punta]||PUNTAS.fibra;
  const anchoBase=(it.grosor||2)*cfg.factor*camara.zoom;

  // El dibujo visible: una sola polilinea para las puntas de ancho parejo
  // (birome, fibra, resaltador) y VARIOS segmentos de distinto ancho para el
  // lapiz, que adelgaza cuanto mas rapido moviste la mano — la velocidad se
  // deduce de la distancia entre puntos guardados, sin datos extra.
  const vis=document.createElementNS(ns,'g');
  vis.classList.add('forma');
  const pintarTrazo=()=>{
    while(vis.firstChild) vis.removeChild(vis.firstChild);
    const comun=el=>{
      el.setAttribute('fill','none'); el.setAttribute('stroke', it.color);
      el.setAttribute('stroke-linecap', cfg.cap); el.setAttribute('stroke-linejoin','round');
    };
    if(!cfg.variable){
      const l=document.createElementNS(ns,'polyline');
      l.setAttribute('points', puntosStr(it.puntos));
      l.setAttribute('stroke-width', anchoBase);
      comun(l); vis.appendChild(l);
      return;
    }
    for(let i=1;i<it.puntos.length;i++){
      const a=it.puntos[i-1], b=it.puntos[i];
      const d=Math.hypot(PX(b.x)-PX(a.x), PY(b.y)-PY(a.y));
      // rapido (segmento largo) => mas fino; lento => mas grueso
      const f=Math.max(0.45, Math.min(1.35, 1.35-d/26));
      const seg=document.createElementNS(ns,'line');
      seg.setAttribute('x1',PX(a.x)); seg.setAttribute('y1',PY(a.y));
      seg.setAttribute('x2',PX(b.x)); seg.setAttribute('y2',PY(b.y));
      seg.setAttribute('stroke-width', anchoBase*f);
      comun(seg); vis.appendChild(seg);
    }
  };
  pintarTrazo();
  const tapa=document.createElementNS(ns,'polyline');
  tapa.classList.add('forma-tapa');
  tapa.setAttribute('points', puntosStr(it.puntos));
  tapa.setAttribute('fill','none'); tapa.setAttribute('stroke-width','10');
  grupo.append(vis, tapa);
  // El resaltador va translucido y mezclado con lo de abajo. El modo depende del
  // fondo: "multiply" es lo correcto sobre papel claro, pero sobre fondo oscuro
  // pinta negro sobre negro y el trazo desaparece — ahi va "screen".
  grupo.style.opacity=((it.opacidad!=null?it.opacidad:100)/100)*cfg.alfa;
  if(cfg.multiplicar){
    const f=estado.fondo||'#0b0d12';
    const lum=parseInt(f.slice(1,3),16)*0.299+parseInt(f.slice(3,5),16)*0.587+parseInt(f.slice(5,7),16)*0.114;
    grupo.style.mixBlendMode = lum>140 ? 'multiply' : 'screen';
  }
  capa.appendChild(grupo);

  tapa.addEventListener('pointerdown', e=>{
    if(e.button!==0 || espacio)return;
    if(herramienta!=='mover')return;   // herramienta de dibujo armada: dejar dibujar ENCIMA de la figura
    e.stopPropagation();
    if(it.bloqueado)return;   // bloqueado: solo se toca por su etiqueta
    if(it.grupo && !seleccion.has(it.id)){ alSeleccionar(it.id, false); }
    if(seleccion.has(it.id) && seleccion.size>1){ dragGrupal(e, it.id); return; }
    bloquear=true;
    guardarSnapshot();
    const inicio=xyDesdeEvento(e);
    let movio=false;
    const base=it.puntos.map(p=>({x:p.x,y:p.y}));
    const xsBase=base.map(p=>p.x), ysBase=base.map(p=>p.y);
    const minXBase=Math.min(...xsBase), maxXBase=Math.max(...xsBase);
    const minYBase=Math.min(...ysBase), maxYBase=Math.max(...ysBase);
    const candX=[minXBase,maxXBase,(minXBase+maxXBase)/2], candY=[minYBase,maxYBase,(minYBase+maxYBase)/2];
    // ⭐ Durante el arrastre NO se regeneran los segmentos: se corre el grupo
    // entero con un transform (una sola operacion). Un garabato puede tener
    // cientos de segmentos y rehacerlos en cada movimiento del mouse hacia que
    // el dibujo se moviera a los tirones y con retraso.
    let ux=0, uy=0;
    const mover=ev=>{
      const p=xyDesdeEvento(ev);
      let dx=p.x-inicio.x, dy=p.y-inicio.y;
      if(Math.hypot(dx,dy)>0.5) movio=true;
      const ajuste=ajustarConGuias(it.id, candX, candY, dx, dy);
      ux=ajuste.dx; uy=ajuste.dy;
      grupo.setAttribute('transform','translate('+LX(ux)+','+LY(uy)+')');
      mostrarGuias(ajuste.guiaX, ajuste.guiaY);
    };
    const soltar=async(ev)=>{
      document.removeEventListener('pointermove', mover);
      document.removeEventListener('pointerup', soltar);
      bloquear=false;
      ocultarGuias();
      if(!movio){
        grupo.removeAttribute('transform');
        olvidarSnapshot();
        alSeleccionar(it.id, ev.shiftKey);
        return;
      }
      // Recien al soltar se pasan los puntos a su lugar definitivo y se repinta.
      it.puntos=base.map(pt=>({x:pt.x+ux, y:pt.y+uy}));
      grupo.removeAttribute('transform');
      pintarTrazo(); tapa.setAttribute('points', puntosStr(it.puntos));
      alSeleccionar(it.id, false);
      await fetch('/pizarra/item/'+it.id, {method:'PUT', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({puntos:it.puntos})});
    };
    document.addEventListener('pointermove', mover);
    document.addEventListener('pointerup', soltar);
  });

  // Al garabato del lapiz tambien se le puede enganchar una flecha: por el
  // principio, la mitad y el final del recorrido.
  let posConectores=()=>{};
  if(!it.bloqueado) posConectores=crearConectores(it, grupo);

  renderFormas[it.id]=()=>{
    const nuevos=puntosStr(it.puntos);
    pintarTrazo(); tapa.setAttribute('points',nuevos);
    posConectores();
  };
}

async function guardarTexto(id, texto){
  texto=texto.trim();
  if(!texto)return; // no se guarda vacio: mejor dejar el texto viejo que perder la nota
  await fetch('/pizarra/item/'+id, {method:'PUT', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({texto})});
}

function hacerArrastrable(div, id, txt){
  // Escucha en document (no pointer capture): capturar el puntero en el propio
  // div rompia la deteccion nativa del doble clic para editar -- con el drag
  // resuelto por afuera, el navegador reconoce el doble clic sin problema.
  const arrancarArrastre=e=>{
    if(e.button!==0)return;
    if(txt.contentEditable==='true')return;   // esta en edicion: dejar el cursor de texto normal
    if(herramienta!=='mover')return;          // hay una herramienta armada: no arrastrar, dejar dibujar
    const itg=estado.items.find(i=>i.id===id);
    if(itg && itg.bloqueado)return;   // bloqueado: solo se toca por su etiqueta
    if(itg && itg.grupo && !seleccion.has(id)){ alSeleccionar(id, false); }
    if(seleccion.has(id) && seleccion.size>1){ dragGrupal(e, id); return; }
    // Clic sobre el texto de una nota YA seleccionada: entra a editar directo.
    const sobreTexto = div._esTexto && div._esTexto(e.target);
    const yaSeleccionada = seleccion.has(id) && seleccion.size===1;
    const inicio=xyDesdeEvento(e);
    let movio=false, ux=null, uy=null;
    bloquear=true;
    guardarSnapshot();
    const mover=ev=>{
      let {x,y}=xyDesdeEvento(ev);
      if(Math.hypot(x-inicio.x,y-inicio.y)>0.5) movio=true;
      const ajuste=ajustarConGuias(id, [x], [y], 0, 0);
      x+=ajuste.dx; y+=ajuste.dy;
      ux=x; uy=y;
      div.style.left=PX(x)+'px'; div.style.top=PY(y)+'px';
      // ⭐ Actualizar TAMBIEN el estado en memoria, no solo el DOM: si entre el
      // arrastre y el proximo refresco ocurre un repintado (zoom, paneo), se
      // redibujaba desde el estado VIEJO y la nota saltaba a su lugar anterior.
      const itm=estado.items.find(i=>i.id===id);
      if(itm){ itm.x=x; itm.y=y; }
      if(renderFormas['n'+id]) renderFormas['n'+id]();   // los puntitos la siguen
      if(asasNota[id]) asasNota[id]();                   // y el asa de mover tambien
      reatarEnVivo(id);   // las flechas atadas a esta nota la siguen mientras la arrastras
      mostrarGuias(ajuste.guiaX, ajuste.guiaY);
    };
    const soltar=async(ev)=>{
      document.removeEventListener('pointermove', mover);
      document.removeEventListener('pointerup', soltar);
      bloquear=false;
      ocultarGuias();
      if(!movio || ux===null){
        olvidarSnapshot();   // no hubo cambio real: no gastar un paso de deshacer
        if(sobreTexto && yaSeleccionada && !ev.shiftKey && div._entrarEdicion){
          div._entrarEdicion(false);   // cursor donde tocaste, sin seleccionar todo
          return;
        }
        alSeleccionar(id, ev.shiftKey);
        return;
      }
      alSeleccionar(id, false);
      await fetch('/pizarra/item/'+id, {method:'PUT', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({x:ux, y:uy})});
      await reatarFlechas(id);
    };
    document.addEventListener('pointermove', mover);
    document.addEventListener('pointerup', soltar);
  };
  div.addEventListener('pointerdown', arrancarArrastre);
  // El asa de mover de las notas, pines y textos: mismo tirador, mismo camino.
  // Se reposiciona en cada repintado porque su caja se mide del DOM.
  const itn=estado.items.find(i=>i.id===id);
  if(itn && !itn.bloqueado){
    const posAsa=crearAsaMover(itn, arrancarArrastre);
    const acomodar=()=>posAsa(cajaDe(itn));
    setTimeout(acomodar, 0);
    asasNota[id]=acomodar;
  }
}

// --- Marquee: con la herramienta "mover", arrastrar sobre el fondo vacio dibuja
// un recuadro y selecciona todo lo que TOCA (interseccion de cajas, no hace falta
// que lo envuelva entero -- mas simple que Excalidraw, que envuelve entero por
// default, pero mas intuitivo para objetos chicos como notas y pines). ---
tablero.addEventListener('pointerdown', e=>{
  if(herramienta!=='mover')return;
  if(e.button!==0 || espacio)return;
  if(e.target!==tablero && e.target!==capa)return;
  bloquear=true;
  const a=xyDesdeEvento(e);
  const marco=document.createElement('div');
  marco.className='marquee';
  tablero.appendChild(marco);
  const pintarMarco=(a,b)=>{
    marco.style.left=PX(Math.min(a.x,b.x))+'px'; marco.style.top=PY(Math.min(a.y,b.y))+'px';
    marco.style.width=(PX(Math.max(a.x,b.x))-PX(Math.min(a.x,b.x)))+'px';
    marco.style.height=(PY(Math.max(a.y,b.y))-PY(Math.min(a.y,b.y)))+'px';
  };
  pintarMarco(a,a);
  const mover=ev=>pintarMarco(a, xyDesdeEvento(ev));
  const soltar=async ev=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    bloquear=false;
    marco.remove();
    const b=xyDesdeEvento(ev);
    if(Math.abs(b.x-a.x)<1 && Math.abs(b.y-a.y)<1)return;  // clic sin arrastrar: lo maneja el click de mas abajo
    ignorarProximoClick=true;
    const cajaMin={x:Math.min(a.x,b.x), y:Math.min(a.y,b.y)};
    const cajaMax={x:Math.max(a.x,b.x), y:Math.max(a.y,b.y)};
    if(!ev.shiftKey) seleccion.clear();
    for(const it of estado.items){
      if(it.bloqueado)continue;   // bloqueado: el recuadro lo ignora
      const p=puntosDe(it);
      if(!p.xs.length)continue;
      const iMin={x:Math.min(...p.xs), y:Math.min(...p.ys)};
      const iMax={x:Math.max(...p.xs), y:Math.max(...p.ys)};
      if(iMin.x<=cajaMax.x && iMax.x>=cajaMin.x && iMin.y<=cajaMax.y && iMax.y>=cajaMin.y) seleccion.add(it.id);
    }
    expandirGrupos(seleccion);
    pintarSeleccion();
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
});

// ⭐ Con una herramienta armada se puede empezar a dibujar en CUALQUIER punto del
// lienzo, TAMBIEN encima de una nota, un pin o un texto. Eso ya lo daban por hecho
// los propios objetos (sus handlers dicen "hay una herramienta armada: no
// arrastrar, dejar dibujar" y se hacen a un lado), pero el dibujo se moria aca:
// el permiso era "el fondo o adentro del SVG", y las notas/pines/textos son divs
// de HTML sueltos en el tablero. Resultado: la flecha no arrancaba encima de una
// nota y no pasaba nada, ni un aviso (2026-08-17).
// Lo unico que queda afuera son los controles, que tambien viven adentro del
// tablero: los paneles, las barras y las manijas.
const UI_PIZARRA='#panelProps,#barraRecorte,#zoomUI,#fondos,.menuCtx,'+
                 '.forma-manija,.forma-rotor,.asa-mover,.conector,.mg-manija,.etiqueta-bloqueo';
const sobreElLienzo=t=>!!t && tablero.contains(t) && !t.closest(UI_PIZARRA);

// --- Dibujar figuras: arrastrar de un punto A a un punto B ---
tablero.addEventListener('pointerdown', e=>{
  if(!FIGURAS.has(herramienta))return;
  if(e.button!==0 || espacio)return;
  if(!sobreElLienzo(e.target))return;
  bloquear=true;
  const a=xyDesdeEvento(e);
  const ns='http://www.w3.org/2000/svg';
  const previa=document.createElementNS(ns, herramienta==='rectangulo'?'rect':herramienta==='circulo'?'ellipse':'line');
  previa.setAttribute('stroke','#5eb8ff'); previa.setAttribute('stroke-width','2');
  previa.setAttribute('stroke-dasharray','6,5');
  previa.setAttribute('fill','none');
  capa.appendChild(previa);
  const dibujar=(a,b)=>{
    if(herramienta==='rectangulo'){
      previa.setAttribute('x',PX(Math.min(a.x,b.x))); previa.setAttribute('y',PY(Math.min(a.y,b.y)));
      previa.setAttribute('width',LX(Math.abs(b.x-a.x))); previa.setAttribute('height',LY(Math.abs(b.y-a.y)));
    } else if(herramienta==='circulo'){
      previa.setAttribute('cx',PX((a.x+b.x)/2)); previa.setAttribute('cy',PY((a.y+b.y)/2));
      previa.setAttribute('rx',LX(Math.abs(b.x-a.x)/2)); previa.setAttribute('ry',LY(Math.abs(b.y-a.y)/2));
    } else {
      previa.setAttribute('x1',PX(a.x)); previa.setAttribute('y1',PY(a.y));
      previa.setAttribute('x2',PX(b.x)); previa.setAttribute('y2',PY(b.y));
    }
  };
  dibujar(a,a);
  const mover=ev=>dibujar(a, xyDesdeEvento(ev));
  const soltar=async ev=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    bloquear=false;
    previa.remove();
    const b=xyDesdeEvento(ev);
    if(Math.abs(b.x-a.x)<1 && Math.abs(b.y-a.y)<1)return;  // clic sin arrastrar: no crear nada
    ignorarProximoClick=true;
    guardarSnapshot();
    const cuerpo=Object.assign({tipo:herramienta,x1:a.x,y1:a.y,x2:b.x,y2:b.y}, estiloPara(herramienta));
    // Una flecha recien dibujada se engancha sola si sus puntas quedaron cerca
    // de un rectangulo o circulo (y la punta se apoya en el borde, con aire).
    if(herramienta==='flecha'){
      const figA=figuraCerca(a.x,a.y,null), figB=figuraCerca(b.x,b.y,null);
      if(figA||figB){
        cuerpo.atadaA={inicio:figA?figA.id:null, fin:figB?figB.id:null};
        if(figA){ const p=puntoDeApoyo(figA, figB?centroFigura(figB).x:b.x, figB?centroFigura(figB).y:b.y); cuerpo.x1=p.x; cuerpo.y1=p.y; }
        if(figB){ const p=puntoDeApoyo(figB, figA?centroFigura(figA).x:a.x, figA?centroFigura(figA).y:a.y); cuerpo.x2=p.x; cuerpo.y2=p.y; }
      }
    }
    const creado=await (await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(cuerpo)})).json();
    if(creado && creado.id) seleccion=new Set([creado.id]);
    volverAMover();
    refrescar();
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
});

// --- Lapiz: dibujo libre, un punto por cada tanto de movimiento del mouse ---
tablero.addEventListener('pointerdown', e=>{
  if(herramienta!=='lapiz')return;
  if(e.button!==0 || espacio)return;
  if(!sobreElLienzo(e.target))return;   // el lapiz tenia el mismo agujero que las figuras
  bloquear=true;
  const ns='http://www.w3.org/2000/svg';
  const previa=document.createElementNS(ns,'polyline');
  previa.setAttribute('fill','none'); previa.setAttribute('stroke','#e8eaed'); previa.setAttribute('stroke-width','2');
  previa.setAttribute('stroke-linecap','round'); previa.setAttribute('stroke-linejoin','round');
  capa.appendChild(previa);
  const puntos=[xyDesdeEvento(e)];
  const actualizar=()=>previa.setAttribute('points', puntos.map(p=>PX(p.x)+','+PY(p.y)).join(' '));
  actualizar();
  const mover=ev=>{
    const p=xyDesdeEvento(ev);
    const ultimo=puntos[puntos.length-1];
    if(Math.hypot(p.x-ultimo.x, p.y-ultimo.y)<0.5)return;  // simplifica: no un punto por cada pixel
    puntos.push(p); actualizar();
  };
  const soltar=async()=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    bloquear=false;
    previa.remove();
    if(puntos.length<2)return;  // clic sin arrastrar: no crear nada
    ignorarProximoClick=true;
    guardarSnapshot();
    const creado=await (await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({tipo:'lapiz',puntos}, estiloPara('lapiz')))})).json();
    if(creado && creado.id) seleccion=new Set([creado.id]);
    volverAMover();
    refrescar();
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
});

// Tras un ARRASTRE que termina sobre el fondo (marquee, dibujar, panear), el
// navegador dispara igual un 'click' en el tablero: sin esta bandera, ese clic
// fantasma limpiaba la seleccion recien hecha (el marquee "no andaba" por esto).
let ignorarProximoClick=false;

// --- Nota y pin: un clic sobre el fondo vacio, con la herramienta armada ---
tablero.addEventListener('click', async e=>{
  if(ignorarProximoClick){ ignorarProximoClick=false; return; }
  if(e.target!==tablero && e.target!==capa)return;
  if(herramienta==='mover'){ limpiarSeleccion(); return; }
  if(herramienta!=='nota' && herramienta!=='pin' && herramienta!=='texto')return;
  const {x,y}=xyDesdeEvento(e);
  const tipo=herramienta;
  if(tipo==='texto'){
    volverAMover();
    await crearNotaEnEdicion(x, y, 'texto');
  } else if(tipo==='nota'){
    volverAMover();
    await crearNotaEnEdicion(x,y);
  } else {
    guardarSnapshot();
    const creado=await (await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({tipo:'pin',texto:'Pin',x,y}, estiloPara('pin')))})).json();
    if(creado && creado.id) seleccion=new Set([creado.id]);
    volverAMover();
    refrescar();
  }
});

tablero.addEventListener('dblclick', async e=>{
  if(e.target!==tablero && e.target!==capa)return;
  const {x,y}=xyDesdeEvento(e);
  await crearNotaEnEdicion(x,y);
});

async function crearNotaEnEdicion(x, y, tipo){
  guardarSnapshot();
  const cuerpo=(tipo==='texto')
    ? Object.assign({tipo:'texto', texto:'Escribí acá', x, y, color:'var(--ce8eaed,#e8eaed)'}, estiloPara('texto'))
    : Object.assign({tipo:'nota', texto:'Nueva nota', x, y}, estiloPara('nota'));
  await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(cuerpo)});
  await refrescar();
  const nuevo=tablero.querySelector('.item:last-child .txt');
  if(nuevo){
    nuevo.contentEditable=true; bloquear=true;
    const rango=document.createRange(); rango.selectNodeContents(nuevo);
    const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(rango);
    nuevo.focus();
  }
}

document.addEventListener('keydown', e=>{
  if(document.activeElement && document.activeElement.isContentEditable)return;  // escribiendo texto: no interceptar
  // Recortando, el teclado es solo de esto: Enter confirma, Escape se arrepiente.
  // Va ANTES de todo lo demas o Escape suelta la seleccion y Supr borra la imagen
  // que estas recortando.
  if(recorteEnCurso){
    if(e.key==='Enter'){ e.preventDefault(); salirRecorte(true); }
    else if(e.key==='Escape'){ e.preventDefault(); salirRecorte(false); }
    return;
  }
  if(e.key==='Escape'){
    herramienta='mover';
    document.querySelectorAll('.herr-btn').forEach(b=>b.classList.toggle('armado', b.dataset.tool==='mover'));
    tablero.classList.remove('armando');
    limpiarSeleccion();
  } else if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='z'){
    e.preventDefault();
    deshacer();
  } else if((e.key==='Delete' || e.key==='Backspace') && seleccion.size){
    e.preventDefault();
    borrarSeleccion();
  } else if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='d' && seleccion.size){
    e.preventDefault();
    duplicarSeleccion();
  } else if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='c' && seleccion.size){
    copiarSeleccion();   // objetos Y foto, en la misma copia
  } else if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key) && seleccion.size){
    e.preventDefault();
    const paso=e.shiftKey?NUDGE_SHIFT:NUDGE_NORMAL;
    const delta={ArrowUp:[0,-paso],ArrowDown:[0,paso],ArrowLeft:[-paso,0],ArrowRight:[paso,0]}[e.key];
    moverSeleccion(delta[0], delta[1]);
  } else if((e.ctrlKey||e.metaKey) && (e.key==='+'||e.key==='=')){
    e.preventDefault(); fijarZoom(camara.zoom+0.1);
  } else if((e.ctrlKey||e.metaKey) && e.key==='-'){
    e.preventDefault(); fijarZoom(camara.zoom-0.1);
  } else if((e.ctrlKey||e.metaKey) && e.key==='0'){
    e.preventDefault(); fijarZoom(1);
  } else if(e.shiftKey && e.code==='Digit1'){
    e.preventDefault(); encuadrarTodo();
  }
});

// --- Capas: 'frente' = se dibuja ultimo (arriba), 'fondo' = primero (abajo) ---
async function ordenarSeleccion(accion){
  if(!seleccion.size)return;
  guardarSnapshot();
  for(const id of seleccion){
    await fetch('/pizarra/item/'+id+'/orden',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({accion})});
  }
  refrescar();
}

// --- Menu contextual (clic derecho), estilo Excalidraw reducido ---
tablero.addEventListener('contextmenu', e=>{
  e.preventDefault();
  document.querySelectorAll('.menuCtx').forEach(n=>n.remove());
  let id=null, n=e.target;
  while(n && n!==tablero){
    if(n.dataset && n.dataset.id){ id=Number(n.dataset.id); break; }
    n=n.parentNode;
  }
  if(id!=null && !seleccion.has(id)) alSeleccionar(id, false);
  const menu=document.createElement('div');
  menu.className='menuCtx';
  const rt=tablero.getBoundingClientRect();
  menu.style.left=Math.min(e.clientX-rt.left, rt.width-190)+'px';
  menu.style.top=Math.min(e.clientY-rt.top, rt.height-180)+'px';
  const op=(texto,fn)=>{
    const d=document.createElement('div'); d.textContent=texto;
    d.onclick=()=>{ menu.remove(); fn(); };
    menu.appendChild(d);
  };
  if(id!=null || seleccion.size){
    const hayBloq=estado.items.some(i=>seleccion.has(i.id) && i.bloqueado);
    if(hayBloq) op('Desbloquear', ()=>bloquearSeleccion(false));
    else op('Bloquear', ()=>bloquearSeleccion(true));
    const hayGrupo=estado.items.some(i=>seleccion.has(i.id) && i.grupo);
    if(seleccion.size>1 && !hayGrupo) op('Combinar', ()=>combinarSeleccion(false));
    if(hayGrupo) op('Separar', ()=>combinarSeleccion(true));
    op('Traer al frente', ()=>ordenarSeleccion('frente'));
    op('Enviar al fondo', ()=>ordenarSeleccion('fondo'));
    op('Copiar  (Ctrl+C)', ()=>copiarSeleccion());
    op('Copiar solo la imagen', ()=>copiarComoImagen());
    op('Duplicar  (Ctrl+D)', ()=>duplicarSeleccion());
    op('Borrar  (Supr)', ()=>borrarSeleccion());
  } else {
    op('Seleccionar todo', ()=>{ seleccion=new Set(estado.items.map(i=>i.id)); pintarSeleccion(); });
    op('Encuadrar todo  (Shift+1)', ()=>encuadrarTodo());
    op('Deshacer  (Ctrl+Z)', ()=>deshacer());
  }
  tablero.appendChild(menu);
  setTimeout(()=>document.addEventListener('pointerdown', function cerrar(ev){
    if(!menu.contains(ev.target)){ menu.remove(); document.removeEventListener('pointerdown', cerrar); }
  }), 0);
});

// --- Meter una imagen en el tablero -----------------------------------------
// La usan los DOS caminos: pegarla con Ctrl+V (compu) y elegirla con el boton 🖼
// (telefono, que no tiene Ctrl+V). Se sube al panel y entra como un objeto mas,
// centrada en lo que estas mirando y con su proporcion real.
async function meterImagen(dataURL){
  const r=await fetch('/pizarra/imagen',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({datos:dataURL})});
  const d=await r.json();
  if(!d.ok)return;
  const img=new Image();
  img.onload=async()=>{
    const wPx=Math.min(420, img.width), hPx=img.height*(wPx/img.width);
    const cx=escenaX(tablero.clientWidth/2), cy=escenaY(tablero.clientHeight/2);
    const w=wPx/((tablero.clientWidth/100)*camara.zoom);
    const h=hPx/((tablero.clientHeight/100)*camara.zoom);
    guardarSnapshot();
    await fetch('/pizarra/agregar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({tipo:'imagen', archivo:d.archivo,
        x1:cx-w/2, y1:cy-h/2, x2:cx+w/2, y2:cy+h/2})});
    refrescar();
  };
  img.src=dataURL;
}

// El boton 🖼: en el telefono abre la galeria, la camara o los archivos (lo decide
// iOS). ⚠ La foto se ACHICA antes de subirla: las del celular pesan 3 o 4 MB y el
// tablero guarda el archivo entero — mismo criterio que ya usa la app para las fotos
// del chat. Una captura de pantalla no pierde nada legible a 1600 px.
async function elegirImagen(input){
  const f=input.files[0];
  input.value='';
  if(!f)return;
  try{
    const bm=await createImageBitmap(f);
    const escala=Math.min(1, 1600/Math.max(bm.width, bm.height));
    const lienzo=document.createElement('canvas');
    lienzo.width=Math.round(bm.width*escala);
    lienzo.height=Math.round(bm.height*escala);
    lienzo.getContext('2d').drawImage(bm,0,0,lienzo.width,lienzo.height);
    // PNG si es chica (una captura queda mas nitida), JPEG si es una foto pesada.
    const png=lienzo.toDataURL('image/png');
    meterImagen(png.length < 900000 ? png : lienzo.toDataURL('image/jpeg', .82));
  }catch(err){
    alert('No pude usar esa imagen: '+err);
  }
}

// --- Pegar una imagen del portapapeles (Ctrl+V) ---
document.addEventListener('paste', e=>{
  if(document.activeElement && document.activeElement.isContentEditable)return;
  const datos=e.clipboardData;
  const cosas=(datos && datos.items) || [];
  // ⭐ Primero lo NUESTRO. La copia lleva los objetos escritos como texto, así que
  // adentro de la pizarra se pegan editables aunque el portapapeles traiga también
  // la foto — y funciona entre pestañas, entre ventanas y entre la compu y el
  // celular, cosa que la copia interna en memoria nunca pudo.
  const mios=objetosDelTexto(datos ? datos.getData('text/plain') : '');
  if(mios){
    e.preventDefault();
    crearCopias(mios, OFFSET_DUPLICAR, OFFSET_DUPLICAR);
    return;
  }
  for(const c of cosas){
    if(!c.type || !c.type.startsWith('image/'))continue;
    e.preventDefault();
    const lector=new FileReader();
    lector.onload=()=>meterImagen(lector.result);
    lector.readAsDataURL(c.getAsFile());
    return;
  }
  // Nada reconocible afuera: la copia interna de esta misma pestaña.
  if(copiados.length){
    e.preventDefault();
    crearCopias(copiados, OFFSET_DUPLICAR, OFFSET_DUPLICAR);
  }
});

// --- Camara: zoom y paneo (comportamiento calcado de Excalidraw) ---
// Rueda sola = paneo; Shift+rueda = paneo horizontal; Ctrl+rueda = zoom centrado
// en el puntero. Espacio+arrastre o boton del medio = paneo con la manito.
function actualizarZoomUI(){ document.getElementById('zoomPct').textContent=Math.round(camara.zoom*100)+'%'; }

function fijarZoom(nuevo, anclaPx, anclaPy){
  nuevo=Math.min(30, Math.max(0.1, nuevo));
  const ax=anclaPx!=null?anclaPx:tablero.clientWidth/2;
  const ay=anclaPy!=null?anclaPy:tablero.clientHeight/2;
  const ex=escenaX(ax), ey=escenaY(ay);   // que punto de escena esta bajo el ancla...
  camara.zoom=nuevo;
  camara.x=ax/((tablero.clientWidth/100)*nuevo)-ex;   // ...y que siga ahi despues
  camara.y=ay/((tablero.clientHeight/100)*nuevo)-ey;
  actualizarZoomUI(); camaraCambio();
}

function encuadrarTodo(){
  if(!estado.items.length){ camara={x:0,y:0,zoom:1}; actualizarZoomUI(); camaraCambio(); return; }
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(const it of estado.items){
    const p=puntosDe(it);
    if(!p.xs.length)continue;
    minX=Math.min(minX,...p.xs); maxX=Math.max(maxX,...p.xs);
    minY=Math.min(minY,...p.ys); maxY=Math.max(maxY,...p.ys);
  }
  const ancho=Math.max(10, maxX-minX+12), alto=Math.max(10, maxY-minY+12);
  const z=Math.min(1, 100/ancho, 100/alto);   // como Excalidraw: encuadrar nunca pasa del 100%
  camara.zoom=z;
  camara.x=50/z-(minX+maxX)/2;
  camara.y=50/z-(minY+maxY)/2;
  actualizarZoomUI(); camaraCambio();
}

tablero.addEventListener('wheel', e=>{
  e.preventDefault();
  if(e.ctrlKey || e.metaKey){
    // El paso es PROPORCIONAL al gesto (formula de Excalidraw): la pinza del
    // touchpad manda muchos eventos con delta chiquito -> pasos suaves; la rueda
    // del mouse manda pocos con delta grande (recortado a 10) -> el 10% de siempre.
    const r=tablero.getBoundingClientRect();
    const delta=Math.max(-10, Math.min(10, e.deltaY));
    let nuevo=camara.zoom - delta/100;
    // amplificacion logaritmica: muy zoomeado, cada paso rinde mas (si no, volver
    // del 800% al 100% seria eterno)
    nuevo += Math.log10(Math.max(1, camara.zoom)) * -Math.sign(e.deltaY) * Math.min(1, Math.abs(e.deltaY)/20);
    fijarZoom(nuevo, e.clientX-r.left, e.clientY-r.top);
    return;
  }
  const kx=(tablero.clientWidth/100)*camara.zoom, ky=(tablero.clientHeight/100)*camara.zoom;
  if(e.shiftKey){ camara.x-=e.deltaY/kx; }
  else { camara.x-=e.deltaX/kx; camara.y-=e.deltaY/ky; }
  camaraCambio();
},{passive:false});

let espacio=false;
document.addEventListener('keydown', e=>{
  if(e.code==='Space' && !e.repeat && !(document.activeElement && document.activeElement.isContentEditable)){
    e.preventDefault(); espacio=true; tablero.style.cursor='grab';
  }
});
document.addEventListener('keyup', e=>{
  if(e.code==='Space'){ espacio=false; tablero.style.cursor=''; }
});

tablero.addEventListener('pointerdown', e=>{
  if(e.button!==1 && !(espacio && e.button===0))return;
  e.preventDefault();
  const kx=(tablero.clientWidth/100)*camara.zoom, ky=(tablero.clientHeight/100)*camara.zoom;
  let px=e.clientX, py=e.clientY;
  tablero.style.cursor='grabbing';
  const mover=ev=>{
    camara.x+=(ev.clientX-px)/kx; camara.y+=(ev.clientY-py)/ky;
    px=ev.clientX; py=ev.clientY;
    camaraCambio();
  };
  const soltar=()=>{
    document.removeEventListener('pointermove', mover);
    document.removeEventListener('pointerup', soltar);
    tablero.style.cursor=espacio?'grab':'';
    ignorarProximoClick=true;   // el clic fantasma tras panear no debe limpiar la seleccion
  };
  document.addEventListener('pointermove', mover);
  document.addEventListener('pointerup', soltar);
});

// --- Con el dedo: un dedo arrastra el lienzo, dos dedos hacen zoom ------------
// Todo lo de abajo se activa SOLO con pointerType==='touch': con mouse la pizarra
// se comporta exactamente igual que siempre.
//
// Por que un dedo panea (como Miro y Figma) y no dos (como Excalidraw): en un
// telefono el gesto natural para "correr el papel" es un dedo. Para mover un
// objeto lo tocas a el directamente, que es igual de natural. Lo que se pierde es
// el recuadro de seleccion multiple con el dedo, que en una pantalla chica no se
// usa igual.
//
// ⭐ Los handlers de siempre (marquee, dibujar, arrastrar) escuchan en burbuja;
// estos van en CAPTURA, asi deciden primero y le cortan el evento al de abajo
// cuando el gesto es de camara.
const dedos = new Map();          // pointerId -> {x,y} de los dedos apoyados
let gestoDedo = null;             // 'pan' | 'pinch' | null
let pinch = null, movioElDedo = false;

// "Elegir varios" con el dedo: mientras esta prendido, arrastrar sobre el fondo
// dibuja el recuadro de seleccion en vez de correr el lienzo. Es de UN SOLO USO —
// se apaga cuando soltas — porque lo normal en el telefono es panear, y dejarlo
// puesto convertiria la pizarra en algo que no se puede recorrer.
let multiDedo = false;

function modoMulti(){
  multiDedo = !multiDedo;
  const b = document.getElementById('btnMulti');
  if(b) b.classList.toggle('armado', multiDedo);
}

const sobreElFondo = t => t===tablero || t===capa;
const centroDedos = () => {
  const [a,b] = [...dedos.values()];
  return {x:(a.x+b.x)/2, y:(a.y+b.y)/2, d:Math.hypot(a.x-b.x, a.y-b.y)};
};

tablero.addEventListener('pointerdown', e=>{
  if(e.pointerType!=='touch')return;
  dedos.set(e.pointerId, {x:e.clientX, y:e.clientY});
  // Dos dedos = zoom, siempre... salvo que ya estes arrastrando algo con el
  // primero: ahi el segundo dedo se ignora hasta que sueltes, en vez de dejar el
  // arrastre a medio camino.
  if(dedos.size===2 && !bloquear){
    const c = centroDedos();
    gestoDedo='pinch'; pinch={cx:c.x, cy:c.y, d:c.d};
    e.stopPropagation(); e.preventDefault();
    return;
  }
  if(dedos.size!==1)return;
  // ⭐ Con el modo "elegir varios" prendido, el dedo NO corre el lienzo: se deja
  // pasar el evento y lo agarra el recuadro de seleccion de siempre, que funciona
  // con cualquier puntero (pedido de Martin, 2026-08-17 — con el dedo no habia
  // ninguna forma de seleccionar varios objetos).
  if(multiDedo && herramienta==='mover' && sobreElFondo(e.target) && !bloquear) return;
  // Un dedo sobre el fondo con la herramienta de mover: correr el lienzo.
  // Sobre un objeto, o con una herramienta de dibujo, no nos metemos.
  if(herramienta==='mover' && sobreElFondo(e.target) && !bloquear){
    gestoDedo='pan';
    e.stopPropagation(); e.preventDefault();
  }
}, true);

tablero.addEventListener('pointermove', e=>{
  if(e.pointerType!=='touch' || !dedos.has(e.pointerId))return;
  // El delta lo sacamos del dedo anterior: movementX no existe en el touch de Safari.
  const antes = dedos.get(e.pointerId);
  const dx = e.clientX-antes.x, dy = e.clientY-antes.y;
  dedos.set(e.pointerId, {x:e.clientX, y:e.clientY});
  if(!gestoDedo)return;
  e.stopPropagation(); e.preventDefault();
  if(Math.abs(dx)>0.5 || Math.abs(dy)>0.5) movioElDedo=true;
  const kx=(tablero.clientWidth/100)*camara.zoom, ky=(tablero.clientHeight/100)*camara.zoom;
  if(gestoDedo==='pan'){
    camara.x+=dx/kx; camara.y+=dy/ky;
    camaraCambio();
    return;
  }
  if(dedos.size<2)return;
  const c = centroDedos(), r = tablero.getBoundingClientRect();
  camara.x+=(c.x-pinch.cx)/kx; camara.y+=(c.y-pinch.cy)/ky;   // el gesto tambien corre el lienzo
  fijarZoom(camara.zoom*(c.d/pinch.d), c.x-r.left, c.y-r.top);
  pinch={cx:c.x, cy:c.y, d:c.d};
}, true);

const soltarDedo = e=>{
  if(e.pointerType!=='touch')return;
  dedos.delete(e.pointerId);
  // "Elegir varios" es de un solo uso: al levantar el dedo vuelve el paneo. Si
  // quedara puesto, la pizarra dejaria de poder recorrerse con el dedo.
  if(multiDedo && dedos.size===0) modoMulti();
  if(gestoDedo==='pinch' && dedos.size===1){
    gestoDedo='pan';             // levantaste un dedo: seguis paneando con el que queda
    return;
  }
  if(gestoDedo && dedos.size===0){
    gestoDedo=null; pinch=null;
    // Solo si de verdad arrastraste: un TOQUE en el fondo tiene que poder
    // deseleccionar como siempre, y para eso el clic no se puede ignorar.
    if(movioElDedo) ignorarProximoClick=true;
    movioElDedo=false;
  }
};
tablero.addEventListener('pointerup', soltarDedo, true);
tablero.addEventListener('pointercancel', soltarDedo, true);

// Safari del iPhone es el unico que ademas manda SUS gestos: sin esto, la pinza
// le hace zoom a la pagina entera (barra de herramientas incluida) en vez de al
// lienzo, y queda todo gigante y torcido.
for(const ev of ['gesturestart','gesturechange','gestureend'])
  document.addEventListener(ev, e=>e.preventDefault(), {passive:false});

document.getElementById('zoomMenos').onclick=()=>fijarZoom(camara.zoom-0.1);
document.getElementById('zoomMas').onclick=()=>fijarZoom(camara.zoom+0.1);
document.getElementById('zoomPct').onclick=()=>fijarZoom(1);
document.getElementById('zoomFit').onclick=()=>encuadrarTodo();

// Al cambiar el tamano de la ventana cambia la escala px<->escena: redibujar todo.
// ⚠ Al cambiar el tamaño de la ventana cambia la relación ancho/alto de la pantalla,
// y con ella la caja que le corresponde a cada imagen: se recalculan antes de repintar.
window.addEventListener('resize', ()=>{ ajustarImagenes(); acomodarHojas(); camaraCambio(); });

armarPanelProps();
armarGruposProps();
renderPaletas();
actualizarZoomUI();
refrescar(); setInterval(refrescar,2000);
</script></body></html>
"""


@app.get("/pizarra", response_class=HTMLResponse)
def pizarra_pagina():
    return PAGINA_PIZARRA


@app.get("/pizarra/rough.js")
def pizarra_roughjs():
    """La libreria rough.js local (dibujo a mano alzada), sin depender de un CDN."""
    return FileResponse(ESTATICOS / "rough.js", media_type="application/javascript")


@app.get("/pizarra/estado")
def pizarra_estado():
    return _pizarra_cargar()


@app.post("/pizarra/agregar")
async def pizarra_agregar(request: Request):
    d = await request.json()
    tipo = d.get("tipo") or "nota"
    with _PIZARRA_CANDADO:
        return _pizarra_agregar_bloqueado(d, tipo)


def _pizarra_agregar_bloqueado(d, tipo):
    estado = _pizarra_cargar()
    items = estado["items"]
    nuevo_id = max((i["id"] for i in items), default=0) + 1

    if tipo in FIGURAS:
        # Las figuras van con dos puntos (x1,y1)-(x2,y2), no con texto ni x,y solo.
        for campo in ("x1", "y1", "x2", "y2"):
            if d.get(campo) is None:
                return {"ok": False, "error": f"falta {campo}"}
        color = d.get("color") or "#5eb8ff"
        nuevo = {"id": nuevo_id, "tipo": tipo, "x1": d["x1"], "y1": d["y1"],
                 "x2": d["x2"], "y2": d["y2"], "color": color,
                 "creado": time.strftime("%Y-%m-%d %H:%M")}
        if d.get("texto"):        # texto adentro de la figura (estilo Excalidraw)
            nuevo["texto"] = d["texto"]
        if d.get("atadaA"):       # flecha enganchada: {"inicio": id|None, "fin": id|None}
            nuevo["atadaA"] = d["atadaA"]
        if d.get("archivo"):      # imagen pegada: nombre del archivo en resultados/pizarra_imagenes
            nuevo["archivo"] = d["archivo"]
        # recorte: {"x1","y1","x2","y2"} en fracciones (0..1) de la imagen original.
        # El archivo NUNCA se toca: recortar es esconder, no cortar.
        for extra in ("grosor", "lineaEstilo", "relleno", "opacidad", "angulo", "grupo", "bloqueado", "nombre", "punta", "recorte") + CAMPOS_TEXTO:
            if d.get(extra) is not None:
                nuevo[extra] = d[extra]
    elif tipo in TRAZOS:
        # El lapiz (dibujo libre) va con una lista de puntos, no con x,y ni x1,y1,x2,y2.
        puntos = d.get("puntos")
        if not puntos or len(puntos) < 2:
            return {"ok": False, "error": "faltan puntos"}
        color = d.get("color") or "#e8eaed"
        nuevo = {"id": nuevo_id, "tipo": tipo, "puntos": puntos, "color": color,
                 "creado": time.strftime("%Y-%m-%d %H:%M")}
        for extra in ("grosor", "opacidad", "grupo", "bloqueado", "nombre", "punta"):
            if d.get(extra) is not None:
                nuevo[extra] = d[extra]
    else:
        texto = (d.get("texto") or "").strip()
        if not texto:
            return {"ok": False, "error": "falta el texto"}
        x = d.get("x") if d.get("x") is not None else 10 + (nuevo_id * 13) % 75
        y = d.get("y") if d.get("y") is not None else 15 + (nuevo_id * 21) % 65
        color = d.get("color") or (COLORES_NOTA[nuevo_id % len(COLORES_NOTA)] if tipo == "nota" else "#e94b3c")
        nuevo = {"id": nuevo_id, "tipo": tipo, "texto": texto, "x": x, "y": y,
                 "color": color, "creado": time.strftime("%Y-%m-%d %H:%M")}
        for medida in ("w", "h"):    # tamano custom (nota estirada a mano, o duplicada de una)
            if d.get(medida) is not None:
                nuevo[medida] = d[medida]
        for extra in ("opacidad", "angulo", "grupo", "bloqueado", "nombre", "punta") + CAMPOS_TEXTO:
            if d.get(extra) is not None:
                nuevo[extra] = d[extra]

    items.append(nuevo)
    _pizarra_guardar(estado)
    return nuevo


@app.put("/pizarra/item/{item_id}")
async def pizarra_actualizar(item_id: int, request: Request):
    """Mover y/o editar el texto de un item ya existente (arrastre o edicion en linea)."""
    d = await request.json()
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        for i in estado["items"]:
            if i["id"] == item_id:
                for campo in ("texto", "x", "y", "x1", "y1", "x2", "y2", "puntos", "color", "w", "h",
                              "atadaA", "grosor", "lineaEstilo", "relleno", "opacidad", "angulo",
                              "grupo", "bloqueado", "nombre", "punta", "recorte") + CAMPOS_TEXTO:
                    if d.get(campo) is not None:
                        i[campo] = d[campo]
                _pizarra_guardar(estado)
                return i
    return {"ok": False, "error": "no existe ese item"}


@app.delete("/pizarra/item/{item_id}")
def pizarra_quitar(item_id: int):
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        estado["items"] = [i for i in estado["items"] if i["id"] != item_id]
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/grupo")
async def pizarra_grupo(request: Request):
    """Combinar/separar: pone (o saca) el mismo id de grupo a varios items de una
    sola pasada. Combinados siguen siendo objetos independientes: lo unico que
    comparten es que seleccionar uno selecciona a todos."""
    d = await request.json()
    ids = set(d.get("ids") or [])
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        if d.get("separar"):
            for i in estado["items"]:
                if i["id"] in ids:
                    i.pop("grupo", None)
        else:
            nuevo = max((i.get("grupo", 0) for i in estado["items"]), default=0) + 1
            for i in estado["items"]:
                if i["id"] in ids:
                    i["grupo"] = nuevo
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/borrar")
async def pizarra_borrar_varios(request: Request):
    """Borra VARIOS items en una sola pasada. Existe para que el cliente no mande
    N DELETEs simultaneos (asi fue como se vacio la pizarra el 2026-08-14)."""
    d = await request.json()
    ids = set(d.get("ids") or [])
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        estado["items"] = [i for i in estado["items"] if i["id"] not in ids]
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/vaciar")
def pizarra_vaciar():
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        estado["items"] = []
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/imagen")
async def pizarra_imagen_subir(request: Request):
    """Recibe una imagen pegada en la pizarra (dataURL base64) y la guarda como
    archivo en resultados/pizarra_imagenes (fuera de git: puede ser cualquier cosa)."""
    d = await request.json()
    m = re.match(r"data:image/(png|jpe?g|gif|webp);base64,(.+)", d.get("datos") or "")
    if not m:
        return {"ok": False, "error": "formato no soportado"}
    ext = "jpg" if m.group(1).startswith("jpe") else m.group(1)
    carpeta = RESULTADOS / "pizarra_imagenes"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = "img_%d.%s" % (int(time.time() * 1000), ext)
    (carpeta / nombre).write_bytes(base64.b64decode(m.group(2)))
    return {"ok": True, "archivo": nombre}


# ⭐ Copiar lo seleccionado COMO IMAGEN (pedido de Martin, 2026-08-17: "si
# selecciono dos objetos y le doy control C, que se copien como imagen PNG").
# Se dibuja con el navegador de verdad, abriendo /pizarra sin cabeza y sacandole
# una foto al recorte: es el MISMO renderizador que ves en pantalla, asi que el
# PNG sale idéntico. Redibujarlo aparte (con PIL, o a mano en un canvas) habria
# significado reescribir rough.js, las notas HTML y las tipografias, y quedaria
# desincronizado del dia que se toque cualquier cosa del dibujo.
_PIZARRA_PNG_JS = """
ids => {
  bloquear = true;                 // que el auto-refresco no vuelva a traer todo
  estado.items = estado.items.filter(i => ids.includes(i.id));
  if (!estado.items.length) return null;
  seleccion.clear();
  for (const sel of ['#toolbar','#zoomUI','#panelProps','#barraRecorte','#marcoGrupo','header']) {
    const e = document.querySelector(sel);
    if (e) e.style.display = 'none';
  }
  const caja = () => {
    let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
    for (const it of estado.items) {
      const p = puntosDe(it);
      if (!p.xs.length) continue;
      a = Math.min(a, ...p.xs); c = Math.max(c, ...p.xs);
      b = Math.min(b, ...p.ys); d = Math.max(d, ...p.ys);
    }
    return [a, b, c, d];
  };
  pintarTodo();
  let [x1, y1, x2, y2] = caja();
  if (!isFinite(x1)) return null;
  // Encuadrar lo elegido en el centro. El techo de 2x es para que no se agrande
  // tanto que se noten los pixeles de las imagenes pegadas.
  const z = Math.min(2, 80 / Math.max(1, x2 - x1), 80 / Math.max(1, y2 - y1));
  camara.zoom = z;
  camara.x = 50 / z - (x1 + x2) / 2;
  camara.y = 50 / z - (y1 + y2) / 2;
  pintarTodo();
  [x1, y1, x2, y2] = caja();          // de nuevo: las notas se miden del DOM ya pintado
  const rt = tablero.getBoundingClientRect(), m = 10;
  return {x: rt.left + PX(x1) - m, y: rt.top + PY(y1) - m,
          width: PX(x2) - PX(x1) + 2 * m, height: PY(y2) - PY(y1) + 2 * m};
}
"""


# La pagina se REUSA entre copias en vez de recargarla: cargarla de nuevo costaba
# casi un segundo (con `networkidle` encima, que espera a que se calme el sondeo
# del estado, y ese sondeo vuelve cada 2 s). Dejarla viva y volver a traer el
# estado es una decima.
_PIZARRA_RESET_JS = """
async () => {
  bloquear = false;
  ultimoEstadoCrudo = '';
  camara = {x: 0, y: 0, zoom: 1};
  for (const sel of ['#toolbar','#zoomUI','#panelProps','#barraRecorte','#marcoGrupo','header']) {
    const e = document.querySelector(sel);
    if (e) e.style.display = '';
  }
  await refrescar();
  return estado.items.length;
}
"""


def _pizarra_dibujar(pagina, ids):
    """Una foto del recorte, con la pagina ya abierta y puesta a cero."""
    recorte = pagina.evaluate(_PIZARRA_PNG_JS, ids)
    if not recorte:
        return None
    return pagina.screenshot(clip=recorte)


def _pizarra_pagina(navegador):
    pagina = navegador.new_page(viewport={"width": 1600, "height": 1000},
                                device_scale_factor=2)
    pagina.goto("http://127.0.0.1:8750/pizarra", wait_until="domcontentloaded")
    # Esperar al DATO (que la pizarra ya tenga su estado), no a un reloj.
    # ⚠ `typeof estado`, NO `window.estado`: la pagina declara sus variables con
    # `let`, y eso no cuelga del window — la espera no se cumplia nunca y cada
    # copia moria a los 20 s.
    pagina.wait_for_function(
        "() => typeof estado !== 'undefined' && estado.items && estado.items.length >= 0",
        timeout=20000)
    pagina.wait_for_timeout(250)     # que terminen de entrar las imagenes pegadas
    return pagina


# ⭐ El navegador que dibuja queda PRENDIDO entre copia y copia. Abrirlo de cero
# tardaba 3 s, y ese retardo era el bug: Ctrl+C parecía no copiar nada porque el
# portapapeles se llenaba tres segundos después (y Safari directamente cancela la
# escritura si tarda tanto). Prendido, una copia sale en menos de un segundo.
# ⚠ Playwright sincrono exige usar el navegador SIEMPRE desde el mismo hilo que lo
# creó, y FastAPI atiende cada pedido en un hilo distinto de su pool: por eso hay
# UN hilo dibujante con su cola, y no un navegador global compartido.
# Tras un rato sin usarlo se cierra solo, para no dejar ~150 MB tomados de gedes.
_PNG_PEDIDOS = queue.Queue()
_PNG_OCIO = 300          # segundos sin dibujar nada antes de cerrar el navegador
_PNG_HILO = None
_PNG_HILO_LOCK = threading.Lock()


def _pizarra_dibujante():
    from playwright.sync_api import sync_playwright
    pw = nav = pagina = None
    ultimo = 0.0

    def cerrar():
        nonlocal pw, nav, pagina
        for apagar in (getattr(nav, "close", None), getattr(pw, "stop", None)):
            if apagar:
                try:
                    apagar()
                except Exception:      # noqa: BLE001 - cerrando, no hay nada que salvar
                    pass
        pw = nav = pagina = None

    while True:
        try:
            ids, respuesta = _PNG_PEDIDOS.get(timeout=30)
        except queue.Empty:
            if nav is not None and time.time() - ultimo > _PNG_OCIO:
                cerrar()
            continue
        try:
            if nav is None:
                pw = sync_playwright().start()
                nav = pw.chromium.launch()
                pagina = _pizarra_pagina(nav)
            else:
                pagina.evaluate(_PIZARRA_RESET_JS)   # la de la copia anterior quedó filtrada
            respuesta.put(("ok", _pizarra_dibujar(pagina, ids)))
        except Exception as e:         # noqa: BLE001 - el navegador falla de mil formas
            cerrar()                   # quedó en mal estado: la próxima abre uno nuevo
            respuesta.put(("error", str(e)))
        ultimo = time.time()


def _pizarra_png(ids, espera=60):
    """Devuelve el PNG de esos items, o None si no hay nada que dibujar."""
    global _PNG_HILO
    with _PNG_HILO_LOCK:
        if _PNG_HILO is None or not _PNG_HILO.is_alive():
            _PNG_HILO = threading.Thread(target=_pizarra_dibujante, daemon=True,
                                         name="pizarra-png")
            _PNG_HILO.start()
    respuesta = queue.Queue()
    _PNG_PEDIDOS.put((ids, respuesta))
    como, dato = respuesta.get(timeout=espera)
    if como == "error":
        raise RuntimeError(dato)
    return dato


@app.get("/pizarra/png")
def pizarra_png(ids: str = ""):
    """?ids=1,2,3 -> el PNG de esos objetos, recortado a lo que ocupan.
    ⚠ Va como `def` y no `async def`: abrir el navegador tarda un par de segundos
    y adentro de un async congelaria el panel entero (misma piedra que
    /movil/hablar y /chat/mandar)."""
    try:
        pedidos = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return JSONResponse({"ok": False, "error": "ids invalidos"}, status_code=400)
    if not pedidos:
        return JSONResponse({"ok": False, "error": "no elegiste nada"}, status_code=400)
    try:
        png = _pizarra_png(pedidos)
    except Exception as e:                     # noqa: BLE001 - el navegador puede fallar de mil formas
        print(f"pizarra png: fallo el dibujo -> {e}", flush=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    if not png:
        return JSONResponse({"ok": False, "error": "no quedo nada para dibujar"}, status_code=404)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/pizarra/imagen/{nombre}")
def pizarra_imagen(nombre: str):
    if not re.fullmatch(r"[\w.-]+", nombre):   # sin ../ ni rutas raras
        return {"ok": False, "error": "nombre invalido"}
    ruta = RESULTADOS / "pizarra_imagenes" / nombre
    if not ruta.exists():
        return {"ok": False, "error": "no existe"}
    return FileResponse(ruta)


@app.post("/pizarra/item/{item_id}/orden")
async def pizarra_ordenar(item_id: int, request: Request):
    """Capas. 'frente' manda el item al final de la lista (se dibuja ultimo, queda
    arriba) y 'fondo' al principio; 'subir'/'bajar' lo corren UN lugar."""
    d = await request.json()
    accion = d.get("accion")
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        items = estado["items"]
        idx = next((i for i, x in enumerate(items) if x["id"] == item_id), None)
        if idx is None:
            return {"ok": False, "error": "no existe ese item"}
        it = items.pop(idx)
        # ⭐ Un objeto bloqueado hace de FONDO: nada puede quedar detras de el
        # (si no, mandar algo "al fondo" lo escondia abajo del rectangulo de
        # fondo y desaparecia). El piso es el lugar justo arriba del ultimo
        # bloqueado. Un bloqueado, en cambio, si puede ir hasta el fondo real.
        piso = 0
        if not it.get("bloqueado"):
            ultimos = [i for i, x in enumerate(items) if x.get("bloqueado")]
            piso = (max(ultimos) + 1) if ultimos else 0
        if accion == "fondo":
            items.insert(piso, it)
        elif accion == "subir":
            items.insert(min(idx + 1, len(items)), it)
        elif accion == "bajar":
            items.insert(max(idx - 1, piso), it)
        else:
            items.append(it)
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/restaurar")
async def pizarra_restaurar(request: Request):
    """Pisa los items con una foto anterior (deshacer, Ctrl+Z). El fondo se
    conserva: el deshacer es de objetos, no del color del lienzo."""
    d = await request.json()
    items = d.get("items")
    if items is None:
        return {"ok": False, "error": "faltan items"}
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        estado["items"] = items
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/colores")
async def pizarra_colores(request: Request):
    """Colores personalizados del usuario (objetos y fondos): se guardan con la
    pizarra. El cliente manda la lista completa; editar/borrar es reemplazarla."""
    d = await request.json()
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        for campo in ("coloresObjetos", "coloresFondos"):
            lista = d.get(campo)
            if lista is None:
                continue
            if (not isinstance(lista, list)
                    or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in lista)):
                return {"ok": False, "error": "lista invalida"}
            estado[campo] = lista[:24]   # tope sano
        _pizarra_guardar(estado)
    return {"ok": True}


@app.post("/pizarra/fondo")
async def pizarra_fondo(request: Request):
    """Color de fondo del lienzo, compartido (queda guardado con la pizarra)."""
    d = await request.json()
    color = d.get("color") or ""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return {"ok": False, "error": "color invalido"}
    with _PIZARRA_CANDADO:
        estado = _pizarra_cargar()
        estado["fondo"] = color
        _pizarra_guardar(estado)
    return {"ok": True}


@app.get("/medidor")
def medidor():
    """Nivel de audio ACTUAL del microfono configurado (captura ~0.4s). Para la
    barra 'Probar microfono' del panel: ver en vivo si la voz llega al umbral."""
    import numpy as np
    import sounddevice as sd
    nombre = None
    try:
        nombre = json.loads(CONFIG_DICTADO.read_text(encoding="utf-8")).get("microfono")
    except Exception:
        pass
    idx = None
    if nombre:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["name"] == nombre:
                idx = i
                break
    niveles = []

    def cb(indata, frames, t, status):
        niveles.append(float(np.sqrt(np.mean(np.square(indata)))))

    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                            callback=cb, device=idx):
            time.sleep(0.4)
        return {"nivel": max(niveles or [0.0]), "micro": nombre or "predeterminado"}
    except Exception as e:
        return {"error": str(e)[:80], "micro": nombre}


@app.post("/micro")
async def set_micro(request: Request):
    data = await request.json()
    nombre = (data.get("microfono") or "").strip() or None
    CONFIG_DICTADO.write_text(json.dumps({"microfono": nombre}), encoding="utf-8")
    # si la voz esta corriendo, reiniciarla para aplicar el cambio de microfono
    if vivo("voz"):
        stop_one("voz")
        time.sleep(1.5)
        start_one("voz")
    return {"ok": True}


@app.post("/start/{name}")
def start_name(name: str):
    if name in SERVICIOS:
        start_one(name)
    return {"ok": True}


@app.post("/stop/{name}")
def stop_name(name: str):
    if name in SERVICIOS:
        stop_one(name)
    return {"ok": True}


def _servicio_del_pid(cmd):
    """Si ese proceso es uno de los servicios del panel, cual. Si no, ''.

    Sirve para que la tarjeta de la placa no tenga DOS formas de apagar lo mismo: si
    lo que ocupa la placa es la Voz, el boton usa el `stop_one` de siempre (que ademas
    lleva la cuenta de encendidos y apagados) en vez de matar un pid a mano.
    """
    bajo = (cmd or "").lower()
    for nombre, s in SERVICIOS.items():
        match = (s.get("match") or "").lower()
        if match and match in bajo:
            return nombre
    return ""


@app.get("/placa")
def placa_estado():
    """Quien esta ocupando la placa de video y como esta Ollama.

    Pedido de Martin (2026-08-22): poder prender y apagar los modelos desde el panel,
    en vez de pedirle a una sesion que los mate a mano para liberar los 8 GB.
    """
    d = placa.estado()
    for p in d.get("procesos") or []:
        p["servicio"] = _servicio_del_pid(p.get("cmd"))
        p["label"] = SERVICIOS.get(p["servicio"], {}).get("label", "")
    return d


@app.post("/placa/apagar/{pid}")
def placa_apagar(pid: int):
    """Cierra lo que esta ocupando la placa. Si es un servicio, por la puerta de siempre."""
    for p in (placa.estado(fresco=True).get("procesos") or []):
        if p["pid"] == pid:
            nombre = _servicio_del_pid(p.get("cmd"))
            if nombre:
                stop_one(nombre)
                return {"ok": True, "nombre": SERVICIOS[nombre]["label"], "servicio": nombre}
            break
    return placa.apagar_pid(pid)


@app.post("/placa/modelo/{clave}/{accion}")
def placa_modelo(clave: str, accion: str):
    """Prender o apagar uno de los modelos que el panel sabe manejar (`placa.MODELOS`)."""
    if accion == "prender":
        return placa.modelo_prender(clave)
    if accion == "apagar":
        return placa.modelo_apagar(clave)
    return {"ok": False, "error": "no se que es '%s'" % accion[:20]}


# --- Cuanta maquina queda, y como soltarla sin reiniciar nada -------------------
# ⭐ Pedido de Martin (2026-09-03): "quiero poder tener todas las sesiones vivas que se me
# ocurra y que no se rompa nada". Las sesiones ya no tienen tope fijo: se duermen solas
# cuando falta memoria (`_barrer_vivas` en sesiones_movil) y reviven con `--resume` al
# tocarlas. Esto es lo que faltaba para VER eso y para soltar la maquina a mano.
# ⚠ El boton ⟳ NO sirve para esto: reinicia panel y servicios y no toca ni un proceso de
# sesion. Es el mismo par que ya existe para la placa de video en `/placa`, que Martin
# pidio en agosto por exactamente el mismo motivo.

@app.get("/sesiones/maquina")
def sesiones_maquina():
    """Cuantos procesos de sesion hay prendidos, cuanto ocupan y cuanto queda libre."""
    from app.voz import sesiones_movil as sm
    with sm._CANDADO_VIVAS:
        vivas = list(sm.VIVAS.values())
    ahora = time.time()
    filas = []
    mios = set()
    for v in vivas:
        cli = sm._cli_de(v)
        mb = 0
        if cli is not None:
            mios.add(cli.pid)
            try:
                mb = cli.memory_info().rss / 1048576
            except psutil.Error:
                mb = 0
        filas.append({"sid": (v.sid or "nueva")[:8],
                      "proyecto": Path(v.cwd).name,
                      "mb": round(mb),
                      # "trabajando" es lo que la deja fuera del barrido: turno en curso
                      # o algo corriendo por debajo.
                      "trabajando": bool(v.turno.locked() or sm._tiene_trabajo_abajo(v)),
                      "quieta_seg": round(ahora - v.ultimo)})
    # ⭐⭐ Los CLI que estan vivos pero que este panel NO maneja. Pasa SIEMPRE despues de
    # reiniciar el panel: `VIVAS` vive en memoria y arranca vacia, pero los procesos
    # siguen ahi comiendo RAM. Sin esta cifra el medidor decia "0 sesiones prendidas" con
    # 3,4 GB tomados — exactamente la ceguera que habia que arreglar.
    # ⚠⚠ Se MUESTRAN, no se matan, y la diferencia no es cosmetica: aca adentro puede
    # estar Laura, una charla que tenes abierta en una terminal, o la sesion desde la que
    # estas leyendo esto. Un barrido ciego desde el boton se llevaria puesta la
    # conversacion en curso. Lo suelto se limpia POR SID al reabrir la charla
    # (`_conseguir_viva`), que es el unico momento en que se sabe cual es cual.
    sueltas, sueltas_mb = 0, 0.0
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "").lower() != "claude.exe" or p.pid in mios:
                continue
            sueltas += 1
            sueltas_mb += p.memory_info().rss / 1048576
        except psutil.Error:
            continue
    libres = sm._ram_libre_mb()
    return {"ok": True,
            "prendidas": len(filas),
            "mb_sesiones": round(sum(f["mb"] for f in filas)),
            "sueltas": sueltas,
            "mb_sueltas": round(sueltas_mb),
            "mb_libres": round(libres),
            "colchon": sm.COLCHON_RAM_MB,
            "apretado": libres < sm.COLCHON_RAM_MB,
            "sesiones": sorted(filas, key=lambda f: -f["mb"])}


@app.post("/sesiones/liberar")
def sesiones_liberar():
    """Suelta la maquina AHORA: duerme todas las sesiones que se puedan dormir.

    ⚠⚠ Pasa por el MISMO guardian que el barrido automatico (`_dormible`): no toca una
    con un turno en curso ni una con trabajo en segundo plano, porque apagarle el proceso
    a esa se lleva puesto lo que mando a correr y el turno siguiente solo veria "No
    completion record was found". Lo unico que se saltea es el piso de quietud: si
    apretaste el boton, lo estas pidiendo vos.
    ⭐ Dormir no pierde nada: la charla queda en el disco y el proceso se vuelve a
    levantar con `--resume` la proxima vez que le escribas.
    """
    from app.voz import sesiones_movil as sm
    ahora = time.time()
    with sm._CANDADO_VIVAS:
        candidatas = [v for v in sm.VIVAS.values() if sm._dormible(v, ahora, piso=0)]
        ocupadas = len(sm.VIVAS) - len(candidatas)
    for v in candidatas:
        sm._apagar_viva(v, "lo pediste vos desde el panel")
    return {"ok": True, "dormidas": len(candidatas), "ocupadas": ocupadas,
            "mb_libres": round(sm._ram_libre_mb())}


@app.post("/reiniciar-todo")
def reiniciar_todo():
    """El boton ⟳ del encabezado: reinicio completo, panel + todos los servicios.
    El panel no puede matarse a si mismo a mitad de una respuesta, asi que apaga
    los servicios, deja lanzado el .bat suelto y contesta; el .bat espera 3 s,
    mata este proceso y lo relanza con --auto, que prende todo de vuelta."""
    for n in SERVICIOS:
        try:
            stop_one(n)
        except Exception as e:
            print(f"reiniciar-todo {n}: {e}", flush=True)
    bat = PROJ / "lanzadores" / "Reiniciar panel.bat"
    subprocess.Popen(["cmd", "/c", str(bat), "3", "auto"], cwd=str(PROJ),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=CREATE_NO_WINDOW)
    return {"ok": True}


@app.get("/lectura")
def lectura_estado():
    """Que sesion se esta leyendo (o None) + los proyectos con sesiones vivas."""
    cfg = None
    try:
        if SEGUIR_LECTURA.exists():
            cfg = json.loads(SEGUIR_LECTURA.read_text(encoding="utf-8"))
    except Exception:
        cfg = None
    try:
        proys = seguir.proyectos()
    except Exception as e:
        print("lectura/proyectos fallo:", e, flush=True)
        proys = []
    return {"siguiendo": cfg, "proyectos": proys}


@app.get("/lectura/sesiones")
def lectura_sesiones(cwd: str):
    try:
        return {"sesiones": seguir.sesiones_de(cwd)}
    except Exception as e:
        print("lectura/sesiones fallo:", e, flush=True)
        return {"sesiones": []}


@app.post("/lectura/seguir")
async def lectura_seguir(request: Request):
    d = await request.json()
    if not d.get("jsonl"):
        return {"ok": False, "error": "falta la sesion"}
    SEGUIR_LECTURA.write_text(json.dumps(
        {"jsonl": d["jsonl"], "nombre": d.get("nombre") or "",
         "cwd": d.get("cwd") or ""}, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/lectura/parar")
def lectura_parar():
    try:
        SEGUIR_LECTURA.unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}


@app.get("/escribir")
def escribir_estado():
    """El destino actual del dictado a sesion + los proyectos con sesiones vivas."""
    destino = None
    try:
        if ESCRIBIR_EN.exists():
            destino = json.loads(ESCRIBIR_EN.read_text(encoding="utf-8"))
    except Exception:
        destino = None
    try:
        proys = seguir.proyectos()
    except Exception as e:
        print("escribir/proyectos fallo:", e, flush=True)
        proys = []
    return {"destino": destino, "proyectos": proys}


@app.post("/escribir/elegir")
async def escribir_elegir(request: Request):
    d = await request.json()
    if not d.get("nombre"):
        return {"ok": False, "error": "falta la sesion"}
    ESCRIBIR_EN.write_text(json.dumps(
        {"id": d.get("id"), "nombre": d["nombre"], "cwd": d.get("cwd") or "",
         "jsonl": d.get("jsonl") or ""}, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.post("/escribir/quitar")
def escribir_quitar():
    try:
        ESCRIBIR_EN.unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}


# El medidor de cupo se saco el 2026-08-14, a pedido de Martin. No medía tu uso real
# del plan: lo estimaba contando los transcripts locales contra unos limites puestos
# a ojo, y daba la mitad de lo que mostraba la pantalla de Claude (25 % contra 46 %).
# Un numero que no es el de verdad es peor que no tener numero, porque decidis con el.
# Claude Code no deja el uso real en ningun archivo de la maquina y el plan no lo
# expone por API, asi que no habia forma de arreglarlo, solo de recalibrarlo a mano
# cada tanto. `app/voz/cupo.py` sigue existiendo (mide y tiene su calibrador por CLI),
# pero ya no lo usa ni el panel ni la voz.


@app.post("/pausa")
def pausa():
    """Pausa/reanuda SOLO la palabra clave, para llamadas, Discord o jugar.

    No apaga la voz ni descarga los modelos: volver es instantaneo, en vez de los
    ~20 s que tarda prender la voz de cero. F9 y los atajos siguen funcionando.
    voz.py lee este archivo cada medio segundo.
    """
    if PAUSA_ESCUCHA.exists():
        PAUSA_ESCUCHA.unlink(missing_ok=True)
    else:
        PAUSA_ESCUCHA.write_text("pausado desde el panel\n", encoding="utf-8")
    return {"pausado": PAUSA_ESCUCHA.exists()}


@app.post("/cortar")
def cortar():
    """El boton ✋: que se calle y suelte lo que este haciendo, ya.

    Es OTRA cosa que pausar (por eso son dos botones, pedido de Martin el
    2026-08-14): pausar apaga la palabra clave y queda puesto hasta que lo
    saques; esto corta el turno de AHORA -- lo que esta diciendo y lo que le
    esta preguntando a Claude -- y no deja nada apagado. Es lo mismo que
    llamarla por el nombre mientras habla, pero con el mouse.

    Deja el pulso en un archivo y vuelve al toque: el que interrumpe de verdad
    es voz.py, que mira la señal cada medio segundo (_vigilar_pausa).
    """
    if not vivo("voz"):
        return {"ok": False, "motivo": "la voz esta apagada"}
    CORTAR_VOZ.write_text("cortar desde el panel\n", encoding="utf-8")
    return {"ok": True}


IMAGENES_CHAT = RESULTADOS / "chat_panel"     # lo que le pegas o adjuntas al chat
# Las extensiones que aceptamos: global, porque la usan el chat del panel Y el
# celular. Estaba adentro de chat_mandar y desde afuera daba NameError.
OK_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def leer_en_voz():
    """¿Hay que decir en voz alta lo que se contesta por el chat del panel?

    Por defecto SI: es lo que Martin pidio. El estado vive en un archivo del
    servidor, no en el navegador, para que una pestaña vieja no lo apague sola.
    """
    try:
        return LEER_PANEL.read_text(encoding="utf-8").strip() != "0"
    except Exception:
        return True


@app.get("/pensando")
def pensando_ep():
    """Solo si esta pensando. Endpoint aparte y minimo a proposito.

    /status trae psutil de todos los servicios y se pide cada 2,5 s: con esa cadencia
    los puntitos aparecian JUSTO cuando la respuesta ya estaba escrita y se quedaban
    un rato de mas. Esto es un exists() de un archivo, asi que se puede preguntar
    varias veces por segundo sin costo.
    """
    return {"pensando": PENSANDO.exists()}


@app.post("/leer")
def leer_toggle():
    """Prende/apaga la lectura en voz alta de las respuestas del chat."""
    nuevo = "0" if leer_en_voz() else "1"
    LEER_PANEL.write_text(nuevo, encoding="utf-8")
    return {"leer": nuevo == "1"}


@app.post("/chat/mandar")
async def chat_mandar(texto: str = Form(""), imagenes: list[UploadFile] = File(None)):
    """Escribirle a Laura desde el panel, con o sin imagenes.

    Va por el MISMO buzon de archivos que usa el bot de Telegram (app/voz/buzon.py):
    el proceso `claude` con la memoria de Laura vive adentro de voz.py, asi que nadie
    mas puede hablarle directo sin bifurcar la conversacion. Una sola Laura para el
    microfono, el telefono y esta caja de texto.

    Las imagenes se guardan en resultados/chat_panel y lo que viaja son las RUTAS:
    Laura las abre con Read (Claude ve imagenes), igual que las fotos de Telegram.
    Pueden ir varias en un mismo mensaje.
    """
    from app.voz import buzon
    texto = (texto or "").strip()
    if not vivo("voz"):
        return {"ok": False, "error": "Laura esta apagada: prendé la voz desde el panel."}
    rutas = []
    for i, imagen in enumerate(imagenes or []):
        if not imagen or not imagen.filename:
            continue
        datos = await imagen.read()
        if not datos:
            continue
        ext = Path(imagen.filename).suffix.lower() or ".png"
        if ext not in OK_EXT:
            return {"ok": False, "error": f"No manejo archivos {ext}."}
        IMAGENES_CHAT.mkdir(parents=True, exist_ok=True)
        # El indice en el nombre evita que dos imagenes del mismo mensaje caigan en el
        # mismo milisegundo y una pise a la otra.
        ruta = IMAGENES_CHAT / f"{int(time.time()*1000)}_{i}{ext}"
        ruta.write_bytes(datos)
        rutas.append(ruta)
    if not texto and not rutas:
        return {"ok": False, "error": "Escribí algo o pegá una imagen."}
    if len(rutas) == 1:
        texto = (f"[Te paso una imagen desde el panel; está guardada en {rutas[0]} — "
                 f"abrila con la herramienta Read antes de contestar.] {texto}").strip()
    elif rutas:
        lista = ", ".join(str(r) for r in rutas)
        texto = (f"[Te paso {len(rutas)} imagenes desde el panel; están guardadas en "
                 f"{lista} — abrilas TODAS con la herramienta Read antes de contestar.] "
                 f"{texto}").strip()

    pid = buzon.dejar_pregunta(texto, origen="panel", leer=leer_en_voz())
    # ⚠ La espera va con asyncio.sleep, NUNCA con time.sleep: esto es un `async def`,
    # y un sleep bloqueante acá le frena el bucle de eventos a uvicorn ENTERO. Pasó el
    # 2026-08-14: mientras Laura pensaba, el panel completo quedaba congelado — el chat
    # no se refrescaba, el estado no respondía y los botones no hacían nada. Parecía que
    # se rompía "todo" cada vez que escribías, y en realidad era este renglón.
    fin = time.time() + buzon.SIN_VOZ_SEG
    while not buzon.pregunta_tomada():
        if time.time() > fin:
            buzon.abandonar()
            return {"ok": False, "error": "Laura no levanta el buzón: fijate si la voz está viva."}
        await asyncio.sleep(0.3)
    # Y ahora la respuesta. El tope es alto porque Laura puede estar leyendo archivos
    # o corriendo comandos antes de contestar.
    fin = time.time() + 600
    while time.time() < fin:
        r = buzon.sacar_respuesta(pid)
        if r is not None:
            return {"ok": True, "respuesta": r}
        await asyncio.sleep(0.4)
    return {"ok": False, "error": "Laura tardó demasiado. Fijate el chat, capaz contesta sola."}


@app.post("/sesion/nueva")
def sesion_nueva():
    """El boton "Nueva sesion" del chat: arrancar de cero sin decirlo por voz.

    Es lo mismo que decirle "arranquemos una sesion nueva". La charla que dejas se
    ARCHIVA, no se borra: se puede volver a ella. Como con el corte, el panel solo
    deja la señal y el que hace el trabajo es voz.py.
    """
    if not vivo("voz"):
        return {"ok": False, "motivo": "la voz esta apagada"}
    NUEVA_SESION.write_text("nueva sesion desde el panel", encoding="utf-8")
    return {"ok": True}


@app.post("/sesion/compactar")
def sesion_compactar():
    """El botón "Compactar" del chat: resumir la charla de Laura y seguir en una nueva.

    Igual que "Nueva sesión", pero sin perder el hilo: le pide un resumen a la charla
    de ahora y siembra la nueva con él. La vieja queda archivada. El panel solo deja
    la señal; el trabajo lo hace voz.py, que es quien tiene el proceso de Laura.
    """
    if not vivo("voz"):
        return {"ok": False, "motivo": "la voz esta apagada"}
    COMPACTAR_LAURA.write_text("compactar desde el panel", encoding="utf-8")
    return {"ok": True}


@app.get("/sesion/modelo")
def sesion_modelo_leer():
    """Con qué modelo piensa Laura, la lista para elegir, y cuánto arrastra su charla.

    El contexto sale del .jsonl de su sesión, igual que el de las pestañas: es lo que
    Laura relee en CADA cosa que le pedís, y por eso es lo que conviene mirar antes de
    compactar.
    """
    from app.voz import sesiones_movil
    from app.voz import claude_voz
    ctx = None
    try:
        sid = _sesion_de_laura()
        if sid:
            ctx = sesiones_movil.contexto(str(RAIZ), sid)
    except Exception:
        pass
    # Las tres perillas de Codex viajan juntas: modelo, esfuerzo compatible y tier.
    try:
        from app.voz import codex_voz
        modelo_cdx = codex_voz.modelo_actual()
        cdx = {"modelo": modelo_cdx,
               "modelos": [{"id": k, "nombre": v}
                            for k, v in codex_voz.MODELOS.items()],
               "defecto": codex_voz.MODELO,
               "esfuerzo": codex_voz.esfuerzo_actual(),
               "esfuerzos": [{"id": k, "nombre": v}
                             for k, v in codex_voz.esfuerzos_del_modelo(modelo_cdx).items()],
               "velocidad": codex_voz.velocidad_actual(),
               "velocidades": [{"id": k, "nombre": v}
                                for k, v in codex_voz.velocidades_del_modelo(modelo_cdx).items()]}
    except Exception:
        cdx = None
    return {"ok": True, "modelo": claude_voz.modelo_actual(),
            "modelos": [{"id": k, "nombre": v} for k, v in sesiones_movil.MODELOS.items()],
            "defecto": claude_voz.MODELO, "contexto": ctx,
            # La perilla hermana: cuanto piensa antes de contestar (--effort).
            "esfuerzo": claude_voz.esfuerzo_actual(),
            "esfuerzos": [{"id": k, "nombre": v}
                          for k, v in sesiones_movil.ESFUERZOS.items()],
            "codex": cdx}


@app.get("/sesion/cerebro")
def sesion_cerebro_leer():
    """Con cuál de los dos cerebros grandes piensa Laura: Claude Code o Codex.

    Es la misma perilla que la voz ("pasate a Codex"): las dos miran el archivo
    `cerebro.json`. Ver `app/voz/cerebro_grande.py`.
    """
    from app.voz import cerebro_grande
    return {"ok": True, "activo": cerebro_grande.activo(),
            "defecto": cerebro_grande.DEFECTO,
            "cerebros": [{"id": k, "nombre": v["nombre"]}
                         for k, v in cerebro_grande.CEREBROS.items()]}


@app.post("/sesion/cerebro")
async def sesion_cerebro_poner(request: Request):
    """Cambiarle el cerebro a Laura.

    Se guarda en el archivo y listo: voz.py (otro proceso) lo relee antes de cada
    turno. No cuesta ni un reinicio. ⚠ La charla NO se muda: cada cerebro retoma la
    suya, y por eso la frase que devuelve lo dice.
    """
    from app.voz import cerebro_grande
    d = await request.json()
    frase = cerebro_grande.usar((d.get("cerebro") or "").strip())
    if frase is None:
        return {"ok": False, "motivo": "ese cerebro no existe"}
    return {"ok": True, "activo": cerebro_grande.activo(), "frase": frase}


@app.post("/sesion/modelo")
async def sesion_modelo_poner(request: Request):
    """Cambiarle el modelo a Laura.

    Se guarda en el archivo y listo: el proceso de Laura vive en voz.py (otro
    proceso) y lo relee antes de cada turno. Si cambió, se rearranca solo con
    `--resume`, así que la charla sigue igual y cuesta los ~10 s del arranque.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    modelo = sesiones_movil.poner_modelo("laura", (d.get("modelo") or "").strip())
    return {"ok": True, "modelo": modelo}


@app.post("/sesion/esfuerzo")
async def sesion_esfuerzo_poner(request: Request):
    """Cuánto se esfuerza Laura en pensar (`--effort` del CLI).

    Igual que el modelo: se guarda en el archivo y voz.py lo relee antes de cada
    turno. Si cambió, rearranca solo con `--resume` y la charla sigue igual.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    esf = sesiones_movil.poner_esfuerzo("laura", (d.get("esfuerzo") or "").strip())
    return {"ok": True, "esfuerzo": esf}


@app.post("/sesion/esfuerzo-codex")
async def sesion_esfuerzo_codex_poner(request: Request):
    """Cuánto piensa el Codex de Laura (`model_reasoning_effort` de su CLI).

    Mismo camino que el esfuerzo de Claude: se guarda en el archivo de ajustes y
    codex_voz lo relee al armar el comando de cada turno. No cuesta ni un reinicio,
    porque Codex arranca un proceso nuevo por turno.
    """
    from app.voz import codex_voz
    d = await request.json()
    esf = codex_voz.poner_esfuerzo((d.get("esfuerzo") or "").strip())
    return {"ok": True, "esfuerzo": esf}


@app.post("/sesion/modelo-codex")
async def sesion_modelo_codex_poner(request: Request):
    """Cambia el modelo del Codex de Laura desde el turno siguiente."""
    from app.voz import codex_voz
    d = await request.json()
    modelo = codex_voz.poner_modelo((d.get("modelo") or "").strip())
    return {"ok": True, "modelo": modelo}


@app.post("/sesion/velocidad-codex")
async def sesion_velocidad_codex_poner(request: Request):
    """Cambia entre el tier estándar y Priority del Codex de Laura."""
    from app.voz import codex_voz
    d = await request.json()
    velocidad = codex_voz.poner_velocidad((d.get("velocidad") or "").strip())
    return {"ok": True, "velocidad": velocidad}


@app.post("/escuchar/{modo}")
def escuchar(modo: str):
    """Los botones 🎙 Laura / 🎙 Venus: apretar en vez de decir el nombre.

    No graba ni transcribe aca: deja el modo en un archivo y voz.py entra por
    _disparar_wake(), el MISMO punto que la palabra clave. Con eso hereda el
    "Te escucho", los tiempos de silencio, el "No te escuche" cuando no hablas y
    el ruteo distinto de cada una (Laura piensa con Claude, Venus resuelve en la
    maquina). La alternativa -- grabar en el navegador -- obligaba a mantener dos
    versiones de todo eso.

    Anda aunque la escucha este pausada: pausar apaga la palabra clave, y esto es
    justamente apretar el boton en vez de decirla.
    """
    if modo not in ("claude", "local"):
        return {"ok": False, "motivo": "modo desconocido"}
    if not vivo("voz"):
        return {"ok": False, "motivo": "la voz esta apagada"}
    ESCUCHAR_YA.write_text(modo, encoding="utf-8")
    return {"ok": True, "modo": modo}


@app.post("/micacceso")
def micacceso():
    """Prende/apaga el microfono a nivel de Windows, en dos capas.

    APAGAR: bandera MIC_BLOQUEADO (el watchdog de voz espera callado en vez de
    pelear) + MUTE de todos los microfonos (corte instantaneo y verificable) +
    el interruptor maestro de Privacidad y seguridad, movido automatizando la
    propia Configuracion (la ventana se abre sola un momento: es normal).
    PRENDER: maestro primero (sin el, nada puede abrir microfonos), despues
    desmutear, y recien ahi se levanta la bandera para que voz rearme solo.
    Tarda unos segundos por la Configuracion. Ojo: un microfono enchufado con
    el bloqueo puesto entra sin mute (el maestro apagado lo frena igual).
    """
    if mic_permitido():
        MIC_BLOQUEADO.write_text("bloqueado desde el panel\n", encoding="utf-8")
        r = _mic_llamar("silenciar")
        if not _maestro_llamar("off"):
            print("micacceso: no pude apagar el maestro de Windows; "
                  "el mute ya corta igual", flush=True)
        permitido = bool(r) if r is not None else False
    else:
        if not _maestro_llamar("on"):
            return {"error": "no pude prender el interruptor de Windows, sigo bloqueado",
                    "permitido": False}
        r = _mic_llamar("permitir")
        if r is None:
            return {"error": "no pude desmutear los microfonos (ver log del panel)",
                    "permitido": False}
        MIC_BLOQUEADO.unlink(missing_ok=True)
        permitido = r
    _MIC_CACHE.update(permitido=permitido, vence=time.time() + _MIC_CACHE_SEG)
    return {"permitido": permitido}


# --- La misma consola, pero para el celular ----------------------------------
# NO es el panel grande "adaptado al ancho": es una pantalla aparte con lo poco que
# se usa estando afuera de casa — ver si algo se cayo, pausarle la escucha porque
# entro una llamada, callarla, y leer lo que dijo mientras no estabas.
# La pizarra SI esta, y es LA MISMA pagina de la compu metida en un iframe: se
# probo primero mostrandola como lista y no era lo que se buscaba — uno quiere el
# lienzo, mover las cosas con el dedo. Los gestos viven en PAGINA_PIZARRA.
#
# ⭐ Se llega por Tailscale (red privada entre la PC y el celular), NO por internet.
# El panel sigue escuchando en 127.0.0.1 y no se abre ningun puerto: sin estar en esa
# red, esta pantalla no existe para nadie. Por eso puede tener todos los botones sin
# el cuidado que habria que tener si estuviera publicada.
MOVIL_HTML = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><title>Laura</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0d12">
<link rel="manifest" href="/movil/manifest.json">
<!-- Para que en el iPhone quede como una app de verdad al "Agregar a inicio":
     el icono lo toma de apple-touch-icon (el manifest lo ignora), el nombre de
     apple-mobile-web-app-title, y las dos "capable" son las que la abren a
     pantalla completa, sin la barra del navegador. La barra de estado va NEGRA
     (no translucent): translucent se mete encima del contenido y habria que
     correr toda la pantalla hacia abajo. -->
<link rel="apple-touch-icon" href="/movil/icono.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="Laura">
<script src="/estaticos/aspecto.js"></script>
<!-- El markdown de Claude, dibujado (negritas, titulos, viñetas, codigo). Trae sus
     propios estilos: son los mismos que usa la pagina de sesiones de la compu. -->
<script src="/estaticos/marcado.js"></script>
<!-- Lo que Martin pinta o subraya en la compu se ve tambien aca: las marcas viven en el
     servidor, no en el navegador. Desde el telefono todavia no se pinta. -->
<script src="/estaticos/marcas.js"></script>
<!-- ⭐ La direccion web de cada conversacion (`/movil?c=<id>`), la MISMA pieza que usa la
     pagina de sesiones de la compu: la barra de direcciones sigue a lo que estas mirando y
     entrando por ahi la app abre parada en esa charla (pedido de Martin, 2026-08-18). -->
<script src="/estaticos/direccion.js"></script>
<!-- ⚡ Skills y comandos, el MISMO botón que la pantalla de la compu y el chat de
     Laura. Se montó acá el 2026-08-25: el celular era la única de las tres cajas de
     escribir sin él, así que desde el teléfono no había forma de elegir una skill. -->
<script src="/estaticos/atajos.js"></script>
<style>
 *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
 /* El fondo, la tipografia y el acento salen de /estaticos/aspecto.js, que es el
    mismo para todas las pantallas: se elige una vez y vale en la compu y aca. */
 body{margin:0;background:var(--c0b0d12,#0b0d12);color:var(--ce8ecf1,#e8ecf1);font:16px/1.45 system-ui,sans-serif;
      display:flex;flex-direction:column;height:100dvh;overflow:hidden}
 /* --- barra de pestañas: se desliza con el dedo, como un navegador --- */
 /* La barra de arriba: las pestañas se corren solas y el 🎨 queda fijo a la derecha. */
 #barraArriba{display:flex;align-items:center;gap:6px;flex:0 0 auto;
              background:var(--barra,var(--fondo2));border-bottom:1px solid var(--c1b2130,#1b2130);
              padding-right:8px}
 /* margin-left:auto: sin pestañas abiertas #tabs se esconde y el 🎨 quedaba
    flotando solo a la izquierda (captura de Martín, 2026-08-20). */
 #aspectoAqui{flex:none;display:flex;align-items:center;margin-left:auto}
 #tabs{display:flex;gap:6px;overflow-x:auto;padding:8px 10px 7px;flex:1;min-width:0;
       scrollbar-width:none}
 #tabs::-webkit-scrollbar{display:none}
 .tab{flex:0 0 auto;padding:8px 13px;border-radius:999px;background:var(--c141926,#141926);color:var(--c9aa6b5,#9aa6b5);
      font-size:13.5px;font-weight:600;white-space:nowrap;border:1px solid transparent}
 .tab.sel{background:var(--c14304a,#14304a);color:var(--ccfe6ff,#cfe6ff);border-color:var(--c2a5b86,#2a5b86)}
 .tab .viva{color:var(--ok);font-size:11px}
 .tab.mas{background:var(--c1b2130,#1b2130);color:var(--c7c8797,#7c8797);font-weight:400}
 .tab.fija{padding:9px 12px;font-size:17px}
 /* --- Navegación abajo, donde llega el pulgar -------------------------------
    Los cuatro destinos fijos viven acá; la barra de arriba queda SOLO para saltar
    entre las sesiones que tenés abiertas, que es lo único que cambia de cantidad. */
 #abajo{flex:0 0 auto;display:flex;background:var(--fondo2);border-top:1px solid var(--c1b2130,#1b2130);
        padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
 /* ⭐ Con foto de fondo, las barras van de vidrio esmerilado en vez de tapas negras:
    la foto se adivina detrás y el texto se sigue leyendo. Sin foto el blur no hace
    nada visible, así que se enciende solo con `con-foto` para no gastar GPU al cuete. */
 html.con-foto #barraArriba,html.con-foto #abajo,html.con-foto #escribir,
 html.con-foto #chapas,html.con-foto #cabecera{
   -webkit-backdrop-filter:blur(calc(16px * var(--vidrio,1)));backdrop-filter:blur(calc(16px * var(--vidrio,1)))}
 /* Con foto, los divisores oscuros se cambian por hilos de luz apenas visibles:
    el vidrio ya separa solo, y el hilo negro sobre la foto ensuciaba. */
 html.con-foto #barraArriba{border-bottom-color:rgba(var(--cffffff-rgb,255,255,255),.06)}
 html.con-foto #cabecera{border-bottom-color:rgba(var(--cffffff-rgb,255,255,255),.08)}
 html.con-foto #abajo,html.con-foto #escribir{border-top-color:rgba(var(--cffffff-rgb,255,255,255),.06)}
 /* ⭐ Con foto, las tarjetas del inicio y las listas dejan de ser tapas negras: vidrio
    oscuro translúcido con borde de luz y una sombra que las despega (segunda vuelta,
    2026-08-20 — el inicio había quedado afuera del prolijado). Sin blur adentro del
    scroll a propósito: en el teléfono lo paga la GPU. */
 html.con-foto .tablero,html.con-foto .cifra,html.con-foto .acto,
 html.con-foto .cerebros button,html.con-foto .tarjeta,html.con-foto #hilo,
 html.con-foto .serv,html.con-foto .elegir,html.con-foto details.proy summary{
   background:rgba(var(--c0d121c-rgb,13,18,28),.84);box-shadow:var(--sombra-1)}
 html.con-foto .tablero,html.con-foto .cifra,html.con-foto .acto,
 html.con-foto .cerebros button,html.con-foto .tarjeta,html.con-foto #hilo{
   border-color:rgba(var(--cffffff-rgb,255,255,255),.08)}
 /* Los estados con color propio recuperan su tinte (la regla de arriba les gana). */
 html.con-foto .acto.prendido{background:rgba(var(--c3d3416-rgb,61,52,22),.82);border-color:var(--aviso-bd)}
 html.con-foto .cerebros button.puesto{background:rgba(var(--c16233a-rgb,22,35,58),.85);border-color:var(--c2c4a66,#2c4a66)}
 html.con-foto .cerebros button.puesto.codex{background:rgba(var(--c122b1f-rgb,18,43,31),.85);border-color:var(--ok-bd)}
 html.con-foto .elegir.nueva{background:rgba(var(--c101725-rgb,16,23,37),.8)}
 html.con-foto details.proy[open] summary{background:rgba(var(--c182032-rgb,24,32,50),.8)}
 html.con-foto .tarjeta .linea{border-bottom-color:rgba(var(--cffffff-rgb,255,255,255),.06)}
 html.con-foto .correo{border-bottom-color:rgba(var(--cffffff-rgb,255,255,255),.07)}
 /* Los rótulos de sección flotan directo sobre la foto: más claros y con sombra,
    o no se leen (se veían grises perdidos en la captura). */
 html.con-foto .rubro,html.con-foto .cerebroAviso{color:var(--cc6d0dc,#c6d0dc);
   text-shadow:0 1px 8px rgba(0,0,0,.85)}
 #abajo .dest{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;
              padding:7px 0;color:var(--c5c6675,#5c6675);font-size:10.5px;letter-spacing:.03em}
 #abajo .dest i{font-size:20px;font-style:normal;line-height:1}
 #abajo .dest.sel{color:var(--c8ecbff,#8ecbff)}
 #abajo .dest.sel i{filter:drop-shadow(0 0 7px rgba(var(--c5eb8ff-rgb,94,184,255),.45))}
 #abajo .dest[data-ir="panel"]{order:1}
 #abajo .dest[data-ir="hablar"]{order:2}
 #abajo .dest[data-ir="pizarra"]{order:3}
 #abajo .dest[data-href="/estudio"]{order:4}
 #abajo .dest[data-ir="nueva"]{order:5}
 /* ⚠ Con el TECLADO abierto la barra de abajo se va: iOS achica la ventana visual
    pero no el alto de la página, así que la barra quedaba flotando en el medio de la
    pantalla, arriba del teclado (Martín la marcó en rojo, 2026-08-17). Mientras
    escribís no la necesitás: vuelve sola al cerrar el teclado. */
 body.teclado #abajo{display:none}
 #tabs.vacia{display:none}
 /* ⚠⚠ `overscroll-behavior:none` NO es un detalle: sin eso, en el iPhone, deslizar
    para abajo estando arriba de todo estira el contenido (el "rebote" de iOS) y la
    CABECERA STICKY SE VA CON EL — se despega de arriba y queda una banda de foto de
    fondo de varios centimetros entre la barra de estado y el titulo de la charla, con
    las burbujas colgando (captura de Martin, 2026-08-24). El sticky solo se pega al
    borde del scroller MIENTRAS el scroller esta en su rango; en pleno rebote ese borde
    ya no esta donde uno lo ve. Con `none` no hay rebote y no hay de donde despegarse.
    Va en #cuerpo, que es el que scrollea: en el <body> no serviria (iOS ignora
    overscroll-behavior en el scroller del documento). */
 #cuerpo{flex:1;overflow:auto;overscroll-behavior:none;
         padding:12px 14px calc(12px + env(safe-area-inset-bottom))}
 /* En una charla el cuerpo pierde el padding de arriba: el sticky de la cabecera se
    calcula contra el borde interno, y con padding quedaba una banda de foto entre las
    pestañas y la cabecera con las burbujas asomando (se vio en la captura, 2026-08-20). */
 #cuerpo.charla{padding-top:0}
 h1{font-size:14px;letter-spacing:.14em;text-transform:uppercase;color:var(--c7c8797,#7c8797);margin:0 0 12px}
 .pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:13px;font-weight:600}
 .on{background:var(--ok-bg);color:var(--ok-txt)} .off{background:var(--mal-bg);color:var(--mal-txt)}
 .zzz{background:var(--aviso-bg);color:var(--aviso-txt)}
 button{width:100%;border:0;border-radius:16px;padding:18px;font-size:18px;font-weight:700;
        color:var(--ce8ecf1,#e8ecf1);background:var(--c1b2130,#1b2130);margin-bottom:10px;transition:transform .06s}
 button:active{transform:scale(.97)}
 .grande{padding:24px} .amarillo{background:var(--aviso-bg);color:var(--aviso-txt)}
 .rojo{background:var(--mal-bg);color:var(--mal-txt)} .azul{background:var(--acento-bg);color:var(--acento)}
 .serv{display:flex;align-items:center;gap:10px;padding:14px;border-radius:14px;
       background:var(--c141926,#141926);margin-bottom:8px}
 .luz{width:12px;height:12px;border-radius:50%;flex:0 0 auto}
 .serv b{flex:1;font-weight:600;font-size:15px} .serv small{color:var(--c7c8797,#7c8797);font-size:13px}
 /* ⭐ La cabecera de la charla: título y perillas JUNTOS y pegados arriba (2026-08-20:
    las perillas vivían sueltas abajo del título y se iban con el scroll — Martín creía
    que el celular no las tenía). Sangra hasta los bordes con márgenes negativos que
    compensan el padding de #cuerpo, y el fondo translúcido deja pasar la foto. */
 #cabecera{position:sticky;top:0;z-index:5;margin:0 -14px 14px;
           padding:9px 14px 8px;background:var(--fondo2);
           border-bottom:1px solid var(--borde,var(--c1b2130,#1b2130));
           box-shadow:var(--sombra-1)}
 #titulo{display:flex;align-items:center;gap:8px;min-width:0;margin:0 0 7px;
         font-size:15.5px;font-weight:700;color:var(--ce8ecf1,#e8ecf1);
         letter-spacing:0;text-transform:none}
 #titulo .nom{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #titulo .lapiz{flex:none;color:var(--acento);opacity:.75;font-size:15px;padding:2px 4px}
 /* La cruz de cerrar es neutra, no roja: cerrar una pestaña no es un error. */
 #titulo .cierra{flex:none;width:30px;height:30px;display:flex;align-items:center;
         justify-content:center;border-radius:50%;background:rgba(var(--cffffff-rgb,255,255,255),.07);
         color:var(--c9aa6b5,#9aa6b5);font-size:14px}
 /* ⭐ La flecha de volver: adentro de una charla las barras se van (pantalla completa,
    como WhatsApp) y esta es la única salida — te deja en la lista de sesiones. */
 #titulo .volver{flex:none;width:30px;height:30px;margin-left:-4px;display:flex;
         align-items:center;justify-content:center;border-radius:50%;
         background:rgba(var(--cffffff-rgb,255,255,255),.07);color:var(--ccfd6df,#cfd6df);font-size:18px}
 body.enCharla #barraArriba,body.enCharla #abajo{display:none}
 /* El proyecto al lado del nombre de la charla. ⚠ Necesita su propia regla: la de la
    lista es `.correo .eti` y acá no hay ningún `.correo`, así que salía como texto
    pelado y se leía pegado al título, en mayúsculas, como si fuera parte del nombre. */
 #titulo .eti{flex:none;background:var(--c1b2436,#1b2436);color:var(--c8b9ab0,#8b9ab0);font-size:11px;border-radius:7px;
        padding:2px 7px;white-space:nowrap;
        text-transform:none;letter-spacing:0;font-weight:600}
 /* Una sombra suave despega cada burbuja de la foto de fondo; la esquina achatada
    apunta a quién habla, como en cualquier mensajería (prolijado del 2026-08-20). */
 /* La burbuja mide lo que mide el texto, no todo el ancho: un "ok" va en una
    burbujita, no en una banda de lado a lado. */
 .msg{margin:10px 0;padding:10px 13px;border-radius:14px;white-space:pre-wrap;
      font-size:calc(15px * var(--escala,1));width:fit-content;max-width:84%;
      word-break:break-word;box-shadow:var(--sombra-0)}
 /* ⭐ Estilo WhatsApp (pedido de Martín, 2026-08-20): lo tuyo en verde a la derecha,
    lo de la sesión en gris pizarra a la izquierda, la horita chiquita abajo. Los
    colores van FIJOS a propósito — acá no manda el tema, manda parecerse a WhatsApp. */
 .vos{background:var(--c005c4b,#005c4b);color:var(--ce7f3ee,#e7f3ee);margin-left:auto;
      border-bottom-right-radius:4px}
 .ia,.claude{background:var(--c202c33,#202c33);color:var(--ce9edef,#e9edef);margin-right:auto;
             border-top-left-radius:4px}
 .info{color:var(--c7c8797,#7c8797);font-size:13px;text-align:center;background:none;padding:2px}
 /* El modelo de la charla y el boton de compactarla, abajo del titulo. Apagados: son
    la herramienta, no lo que uno viene a hacer. El boton se enciende solo cuando la
    charla ya pesa (nivel 'mucho'), que es cuando compactar sirve de verdad. */
 /* ⭐ UNA sola fila, siempre: pastillas chicas que se achican o se deslizan de
    costado antes que envolverse — el chip de contexto colgado solo en una segunda
    fila era lo que se veía amontonado (Martín, 2026-08-20). Con lugar de sobra,
    el chip se va solo a la derecha por el margin-left:auto. */
 .ajusSes{display:flex;gap:6px;align-items:center;margin:0;flex-wrap:nowrap;
          overflow-x:auto;scrollbar-width:none}
 .ajusSes::-webkit-scrollbar{display:none}
 /* Sin la flecha gorda del sistema: pastilla con su ▾ propio, y si no entra el
    nombre se corta con puntitos en vez de guillotinado. */
 /* ⚠ `min-width` en serio, no 0: con `min-width:0` las pastillas se APLASTAN hasta
    quedar en la flechita sola cuando hay muchas — se vio apenas entró la perilla de
    Plan en las charlas de Codex, que son las que más tienen (2026-08-25). La fila ya
    sabe desplazarse sola (`overflow-x:auto`): es mejor deslizarla que no poder leer
    ninguna. */
 .ajusSes select{flex:0 1 auto;min-width:86px;-webkit-appearance:none;appearance:none;
                 background:rgba(var(--cffffff-rgb,255,255,255),.06) url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5"><path d="M0 0l4 5 4-5z" fill="%238b96a5"/></svg>') no-repeat right 7px center;
                 border:1px solid rgba(var(--cffffff-rgb,255,255,255),.09);border-radius:999px;
                 color:var(--caab4c2,#aab4c2);padding:5px 17px 5px 9px;font-size:12px;
                 font-family:inherit;text-overflow:ellipsis;white-space:nowrap}
 .ajusSes select.puesto{color:var(--c8ecbff,#8ecbff);border-color:var(--c2c4a66,#2c4a66);background-color:rgba(var(--c2e5e8a-rgb,46,94,138),.22)}
 .ajusSes button{flex:none;width:auto;margin:0;padding:5px 10px;font-size:12px;
                 background:rgba(var(--cffffff-rgb,255,255,255),.06);border:1px solid rgba(var(--cffffff-rgb,255,255,255),.09);
                 color:var(--caab4c2,#aab4c2);border-radius:999px}
 .ajusSes button.conviene{background:var(--aviso-bg);color:var(--aviso-txt);border-color:var(--aviso-bd)}
 /* La misma fila de pastillas, parada en el INICIO abajo del cerebro (los ajustes de
    la sesión de Laura). El esfuerzo de Codex puesto se pinta verde, su color de
    familia. ⚠ background-color, no background: pisa el ▾ en SVG. */
 .ajusSes.laura{margin:0 2px 16px}
 .ajusSes select.codex.puesto{color:var(--ok-txt);border-color:var(--ok-bd);
        background-color:rgba(var(--c122b1f-rgb,18,43,31),.6)}
 .ctxSes{flex:none;margin-left:auto;font-size:12px;color:var(--c8b96a5,#8b96a5);padding:4px 8px;
         border-radius:999px;background:rgba(var(--cffffff-rgb,255,255,255),.05);
         font-variant-numeric:tabular-nums}
 .ctxSes.mucho{color:var(--aviso-txt);background:var(--c2b2512,#2b2512)}
 /* En una charla de Codex las perillas de Claude no van: en su lugar, de quién es. */
 .ajusSes .cerSes{font-size:12px;font-weight:600;color:var(--ok-txt);background:var(--c122b1f,#122b1f);
        border:1px solid var(--ok-bd);padding:5px 10px;border-radius:999px}
 /* ⭐ Con qué cerebro ARRANCA una charla nueva (Claude o Codex). Solo en una pestaña
    sin estrenar: una charla ya nacida no cambia de cerebro, el id ya dice de quién es. */
 .eligeCer{display:flex;gap:8px;align-items:center;margin:0}
 .eligeCer small{color:var(--c7c8797,#7c8797);font-size:12.5px}
 .eligeCer button{width:auto;margin:0;padding:6px 14px;font-size:13px;
        background:rgba(var(--cffffff-rgb,255,255,255),.06);color:var(--caab4c2,#aab4c2);
        border:1px solid rgba(var(--cffffff-rgb,255,255,255),.09);border-radius:999px}
 .eligeCer button.puesto{color:var(--c8ecbff,#8ecbff);border-color:var(--c2c4a66,#2c4a66);background:var(--c16233a,#16233a)}
 .eligeCer button.puesto.codex{color:var(--ok-txt);border-color:var(--ok-bd);background:var(--c122b1f,#122b1f)}
 /* ⭐ La pregunta con opciones (AskUserQuestion): la sesión frenó y te espera a VOS.
    Tonos del acento, nunca rojo — preguntar no es un error (regla de Martín). Los
    botones van bien altos: acá se tocan con el dedo, no con el mouse. */
 .pregunta{margin:14px 0;padding:14px;border-radius:14px;background:var(--burbuja-ia);
           border-left:3px solid var(--acento,var(--c8ecbff,#8ecbff))}
 .pregunta .pTit{display:inline-block;font-size:11px;letter-spacing:.1em;
                 text-transform:uppercase;color:var(--acento,var(--c8ecbff,#8ecbff));margin-bottom:7px}
 .pregunta .pBloque{margin-bottom:14px}
 .pregunta .pBloque:last-of-type{margin-bottom:4px}
 .pregunta .pPreg{font-size:calc(15px * var(--escala,1));font-weight:600;color:var(--ce8ecf1,#e8ecf1);
                  line-height:1.4;margin-bottom:10px}
 .pregunta .pOps{display:flex;flex-direction:column;gap:8px}
 .pregunta .pOp{width:100%;margin:0;text-align:left;background:var(--c151b26,#151b26);
                border:1px solid var(--c232a35,#232a35);border-radius:12px;padding:13px 14px;
                font-size:15px;font-weight:500;color:var(--ce8ecf1,#e8ecf1)}
 .pregunta .pOp.puesta{background:var(--acento-bg,var(--c16233a,#16233a));border-color:var(--acento,var(--c8ecbff,#8ecbff))}
 .pregunta .pOp b{display:block;font-weight:600}
 .pregunta .pOp.puesta b{color:var(--acento,var(--c8ecbff,#8ecbff))}
 .pregunta .pOp span{display:block;color:var(--c7d8a9b,#7d8a9b);font-size:13px;margin-top:3px;
                     font-weight:400;line-height:1.35}
 .pregunta .pOtra{display:flex;gap:8px;margin-top:10px}
 /* ⚠ 16 px o iOS hace zoom solo al tocar el campo y te descoloca la pantalla. */
 .pregunta .pOtra input{flex:1;min-width:0;background:var(--c151b26,#151b26);border:1px solid var(--c232a35,#232a35);
                        border-radius:12px;color:var(--ce8ecf1,#e8ecf1);padding:12px;font-size:16px;
                        font-family:inherit}
 .pregunta .pOtra input::placeholder{color:var(--c5c6675,#5c6675)}
 .pregunta .pManda,.pregunta .pMandar{width:auto;margin:0;padding:12px 16px;font-size:15px;
                  background:var(--acento-bg,var(--c16233a,#16233a));color:var(--acento,var(--c8ecbff,#8ecbff))}
 .pregunta .pMandar{width:100%;margin-top:12px}
 .pregunta .pNota{color:var(--c7d8a9b,#7d8a9b);font-size:12.5px;margin-top:10px}
 /* El plan propuesto (plan mode): puede ser largo, así que tiene su propio scroll
    para que los botones de decidir queden siempre a mano. */
 .pregunta .pPlan{max-height:45vh;overflow:auto;margin-bottom:14px;padding:10px 12px;
   background:var(--c0d131c,#0d131c);border:1px solid var(--c232a35,#232a35);border-radius:10px;
   font-size:calc(14px * var(--escala,1));line-height:1.5}
 /* ⭐ La lista de tareas de la sesión (TodoWrite, 2026-08-20): lo que el agente se
    anotó para hacer y va tildando mientras trabaja, en vivo. Informa, no pide
    nada: tonos apagados, y solo la fila en curso lleva el acento. */
 .tareas{margin:14px 0;padding:12px 14px;border-radius:14px;background:var(--c0f141d,#0f141d);
         border:1px solid var(--c232a35,#232a35);font-size:14px;line-height:1.5}
 html.con-foto .tareas{background:rgba(var(--c0d121c-rgb,13,18,28),.84)}
 .tareas .tTit{font-size:11px;letter-spacing:.1em;text-transform:uppercase;
         color:var(--c7d8a9b,#7d8a9b);font-weight:700;margin-bottom:6px}
 .tareas .tTit span{color:var(--c8ecbff,#8ecbff);margin-left:6px;letter-spacing:0}
 .tareas .tFila{display:flex;gap:8px;align-items:baseline;color:var(--cc9d2de,#c9d2de);padding:3px 0}
 .tareas .tFila .tIco{flex:none;width:16px;text-align:center;color:var(--c5c6675,#5c6675)}
 .tareas .tFila.hecha{color:var(--c6e7889,#6e7889)}
 .tareas .tFila.hecha .tIco{color:var(--ok-txt)}
 .tareas .tFila.haciendo{color:var(--ce8ecf1,#e8ecf1);font-weight:600}
 .tareas .tFila.haciendo .tIco{color:var(--acento,var(--c8ecbff,#8ecbff))}
 /* --- caja de escribir, pegada abajo --- */
 #escribir{flex:0 0 auto;display:none;gap:8px;align-items:flex-end;
           padding:10px 12px calc(10px + env(safe-area-inset-bottom));
           background:var(--fondo2);border-top:1px solid var(--c1b2130,#1b2130)}
 #texto{flex:1;min-width:0;box-sizing:border-box;overflow-y:auto;
        background:rgba(var(--cffffff-rgb,255,255,255),.07);border:1px solid rgba(var(--cffffff-rgb,255,255,255),.08);
        border-radius:20px;color:var(--ce8ecf1,#e8ecf1);
        padding:12px 16px;font-size:16px;font-family:inherit;resize:none;max-height:120px}
 /* Avisar es una opcion secundaria y compacta. Sin ancho propio heredaba el 100 %
    de los botones grandes y aplastaba el campo hasta dejar las letras en vertical. */
 #avisarTarea{width:auto;flex:0 0 auto;margin:0;padding:12px 10px;font-size:13.5px;
              border-radius:999px;background:rgba(var(--cffffff-rgb,255,255,255),.06);color:var(--caab4c2,#aab4c2)}
 #avisarTarea.sel{background:var(--aviso-bg);color:var(--aviso-txt)}
 #mandar{width:auto;padding:12px 20px;margin:0;font-size:15.5px;border-radius:999px;
         background:var(--acento-bg);color:var(--acento)}
 /* El clip sin caja propia: es un accesorio del renglón, no otro botón más. */
 #clip{width:auto;padding:12px 6px;margin:0;font-size:21px;background:transparent;flex:0 0 auto}
 /* El ⚡ vive al lado del clip y con la misma cara: en el teléfono la barra ya tiene
    cuatro cosas y una quinta con marco propio la parte en dos renglones. El tamaño lo
    pone atajos.js, así que hay que pisarlo acá (su <style> se inyecta después). */
 #atajosAqui{flex:0 0 auto;display:flex;align-items:flex-end}
 #atajosAqui button.at-boton{width:auto;height:auto;padding:12px 6px;margin:0;
   font-size:20px;line-height:1;background:transparent;border:0;color:var(--caab4c2,#aab4c2);
   align-self:flex-end;border-radius:12px}
 #atajosAqui button.at-boton.abierto{background:var(--acento-bg);color:var(--acento)}
 /* Las fotos elegidas se ven ANTES de mandarlas: sin esto uno no sabe si adjuntó
    la que quería (misma lección que en el panel de la compu). */
 #chapas{display:none;gap:8px;padding:0 12px 10px;background:var(--fondo2);overflow-x:auto;order:8}
 #escribir{order:9} #abajo{order:10}
 #chapas.hay{display:flex}
 #chapas .chapa{position:relative;flex:0 0 auto}
 #chapas img{height:62px;border-radius:10px;display:block}
 #chapas .x{position:absolute;top:-6px;right:-6px;width:22px;height:22px;border-radius:50%;
            background:var(--mal-bg);color:var(--mal-txt);font-size:13px;display:flex;align-items:center;
            justify-content:center;border:1px solid var(--mal-bd)}
 /* La foto que mandaste, dibujada adentro de la burbuja; tocarla la abre grande. */
 .msg .foto{width:100%;border-radius:12px;display:block;margin-bottom:8px}
 #visor{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;z-index:30;
        align-items:center;justify-content:center;padding:12px}
 #visor.abierto{display:flex}
 #visor img{max-width:100%;max-height:100%;border-radius:10px}
 .aviso{background:var(--aviso-bg);color:var(--aviso-txt);padding:10px 13px;border-radius:12px;font-size:14px;
        margin-bottom:10px}
 .pensando span{display:inline-block;width:5px;height:5px;margin-left:3px;border-radius:50%;
   background:var(--c7c8797,#7c8797);animation:late 1.2s infinite}
 .pensando span:nth-child(2){animation-delay:.2s} .pensando span:nth-child(3){animation-delay:.4s}
 @keyframes late{0%,60%,100%{opacity:.25} 30%{opacity:1}}
 .elegir{padding:14px;border-radius:14px;background:var(--c141926,#141926);margin-bottom:8px}
 .elegir b{display:block;font-size:15px}
 .elegir .lapiz{float:right;color:var(--c8ecbff,#8ecbff);padding:0 4px}
 /* Proyecto plegable: la fila entera es el botón, con la cantidad a la derecha. */
 details.proy{margin-bottom:10px}
 details.proy summary{list-style:none;padding:13px 14px;border-radius:14px;background:var(--c141926,#141926);
   font-size:15px;font-weight:700;display:flex;align-items:center;gap:8px;cursor:pointer}
 details.proy summary::-webkit-details-marker{display:none}
 details.proy summary::before{content:'▸';color:var(--c7c8797,#7c8797);font-size:13px}
 details.proy[open] summary::before{content:'▾'}
 details.proy[open] summary{margin-bottom:8px;background:var(--c182032,#182032)}
 details.proy .cuantas{margin-left:auto;color:var(--c7c8797,#7c8797);font-size:12px;font-weight:400} .elegir small{color:var(--c7c8797,#7c8797);font-size:13px}
 .elegir.nueva{border:1px dashed var(--c2a5b86,#2a5b86);background:var(--c101725,#101725)}
 .elegir.nueva b{color:var(--c8ecbff,#8ecbff)}
 /* --- Tablero: la pantalla de inicio ---------------------------------------
    La idea no es un CRM de ventas con gráficos de torta, sino el puesto de mando
    de esta casa: lo primero es si Laura está al aire, después los números duros y
    recién ahí las acciones. Los números van en tipografía monoespaciada con cifras
    de ancho fijo — son datos, y así no bailan cuando cambian. */
 .tablero{border-radius:20px;padding:22px 18px;margin-bottom:16px;text-align:center;
          border:1px solid var(--c1e2636,#1e2636);background:var(--c111725,#111725)}
 .tablero .rotulo{font-size:13px;letter-spacing:.22em;text-transform:uppercase;font-weight:800}
 .tablero.aire .rotulo{color:var(--ok)} .tablero.pausa .rotulo{color:var(--aviso-txt)}
 .tablero.off .rotulo{color:var(--mal-txt)}
 .tablero .sub{color:var(--c7c8797,#7c8797);font-size:13.5px;margin-top:10px}
 /* El latido: tres barras que respiran cuando está escuchando y quedan quietas y
    apagadas cuando no. Es el único adorno de la pantalla, y dice algo cierto. */
 .latido{display:flex;gap:6px;justify-content:center;align-items:flex-end;height:34px;margin-top:14px}
 .latido i{width:8px;height:10px;border-radius:4px;background:var(--c2a3446,#2a3446)}
 .tablero.aire .latido i{background:var(--ok);animation:respirar 1.6s infinite ease-in-out}
 .tablero.aire .latido i:nth-child(2){animation-delay:.25s;height:16px}
 .tablero.aire .latido i:nth-child(3){animation-delay:.5s}
 @keyframes respirar{0%,100%{height:10px;opacity:.5} 50%{height:30px;opacity:1}}
 .cifras{display:flex;gap:10px;margin-bottom:20px}
 .cifra{flex:1;background:var(--c141926,#141926);border:1px solid var(--c1e2636,#1e2636);border-radius:16px;padding:14px 10px;
        text-align:center}
 .cifra b{display:block;font:700 26px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
          font-variant-numeric:tabular-nums;color:var(--ce8ecf1,#e8ecf1)}
 .cifra b span{font-size:15px;color:var(--c5c6675,#5c6675)}
 .cifra small{display:block;margin-top:7px;color:var(--c7c8797,#7c8797);font-size:11px;letter-spacing:.06em}
 .rubro{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--c5c6675,#5c6675);
        margin:0 0 9px 4px;font-weight:700}
 .acciones{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}
 .acto{text-align:left;background:var(--c141926,#141926);border:1px solid var(--c1e2636,#1e2636);border-radius:16px;
       padding:14px 16px;margin:0}
 .acto b{display:block;font-size:15.5px;color:var(--ce8ecf1,#e8ecf1)}
 .acto small{display:block;color:var(--c7c8797,#7c8797);font-size:12.5px;margin-top:3px;font-weight:400}
 .acto.prendido{border-color:var(--aviso-bd);background:var(--c1d1a10,#1d1a10)}
 .acto.prendido b{color:var(--aviso-txt)}
 /* ⭐ El cerebro con el que piensa Laura (Claude o Codex), desde el inicio: la misma
    perilla que el panel de la compu y que decirle "pasate a Codex" por voz. Dos
    botones a lo ancho, el puesto encendido con el color de su familia. */
 .cerebros{display:flex;gap:8px;margin-bottom:8px}
 .cerebros button{flex:1;margin:0;padding:11px;font-size:14.5px;font-weight:600;
        background:var(--c141926,#141926);border:1px solid var(--c1e2636,#1e2636);border-radius:12px;color:var(--c7c8797,#7c8797)}
 .cerebros button.puesto{color:var(--c8ecbff,#8ecbff);border-color:var(--c2c4a66,#2c4a66);background:var(--c16233a,#16233a)}
 .cerebros button.puesto.codex{color:var(--ok-txt);border-color:var(--ok-bd);background:var(--c122b1f,#122b1f)}
 .cerebroAviso{color:var(--c8b94a3,#8b94a3);font-size:12.5px;margin:-2px 2px 14px;line-height:1.45}
 .tarjeta{background:var(--c141926,#141926);border:1px solid var(--c1e2636,#1e2636);border-radius:16px;overflow:hidden;
          margin-bottom:20px}
 .tarjeta .linea{display:flex;align-items:center;gap:11px;padding:14px 16px;
                 border-bottom:1px solid var(--c1a2130,#1a2130)}
 .tarjeta .linea:last-child{border-bottom:0}
 .tarjeta .punto{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
 .tarjeta .punto.ok{background:var(--ok)} .tarjeta .punto.no{background:var(--mal-txt)}
 .tarjeta .nombre{flex:1;font-size:15px}
 .tarjeta .accion-txt{color:var(--c5c6675,#5c6675);font-size:12.5px}
 .tarjeta.ultimo{padding:15px 16px;font-size:14.5px;line-height:1.5;color:var(--ccdd6e0,#cdd6e0)}
 /* La conversación no estira la pantalla: caja propia con su scroll, arrancando
    abajo del todo. Antes la página del inicio medía varios metros de largo. */
 #hilo{max-height:42dvh;overflow-y:auto;background:var(--c141926,#141926);border:1px solid var(--c1e2636,#1e2636);
       border-radius:16px;padding:6px 12px;margin-bottom:14px}
 #hilo .msg{margin:9px 0;font-size:calc(14px * var(--escala,1))}
 .msg .hora{display:block;text-align:right;opacity:.45;font-size:11px;margin-top:4px}
 /* La costura de una compactada: una rayita en el hilo, no un cartel (2026-08-20). */
 .marcaHilo{display:flex;align-items:center;gap:10px;color:var(--c8a94a6,#8a94a6);font-size:12px;
            margin:14px 0;text-align:center}
 .marcaHilo::before,.marcaHilo::after{content:'';flex:1;border-top:1px solid rgba(var(--cffffff-rgb,255,255,255),.14)}
 /* El rastro, en un BLOQUE con fondo propio: sueltos sobre el fondo de la pantalla no
    se leen. Apagado pero legible; nunca en rojo. */
 .pasos{background:var(--rastro-bg,rgba(var(--c10151e-rgb,16,21,30),.72));
        border:1px solid var(--rastro-borde,rgba(var(--cffffff-rgb,255,255,255),.10));
        border-radius:12px;padding:9px 13px;margin:6px 0}
 /* ⚠⚠ EN LINEA, separados por un punto: juntar los repetidos no alcanzaba porque en una
    tanda real casi nunca estan pegados, y sesenta renglones tapaban la conversacion. */
 .paso{color:var(--rastro,var(--c9aa5b7,#9aa5b7));font-size:12.5px;line-height:1.7;display:inline;
       overflow-wrap:anywhere}
 .paso + .paso::before{content:' · ';color:var(--c6b7488,#6b7488)}
 .pasos + .msg{margin-top:10px}
 /* La pregunta de compactar, adentro del hilo (ámbar de aviso, no rojo). */
 .pideComp{background:var(--aviso-bg);color:var(--aviso-txt);padding:12px 15px;border-radius:12px;
           font-size:13.5px;margin:10px 0;line-height:1.5}
 .pideComp .botones{display:flex;gap:8px;margin-top:9px}
 .pideComp button{height:44px;padding:0 15px;border:none;border-radius:10px;
                  background:var(--aviso-txt);color:var(--c241f08,#241f08);font-weight:600;font-size:14px}
 .pideComp button.despues{background:var(--c1b2230,#1b2230);color:var(--c9aa3b2,#9aa3b2);font-weight:400}
 /* --- Sesiones estilo correo (referencia de Martín: Gmail) -------------------
    Arriba el proyecto en el que estás parado y el menú; abajo, sus conversaciones
    como filas de bandeja: inicial, título, línea gris y el lápiz para renombrar. */
 .barra-proy{display:flex;align-items:center;gap:12px;padding:4px 2px 14px}
 .barra-proy .menu{font-size:21px;color:var(--c9aa6b5,#9aa6b5);padding:4px 8px}
 .barra-proy .quien b{display:block;font-size:17px}
 .barra-proy .quien small{color:var(--c7c8797,#7c8797);font-size:12px}
 .correo{display:flex;align-items:center;gap:13px;padding:13px 6px;
         border-bottom:1px solid var(--c171d29,#171d29)}
 .correo .ini{width:40px;height:40px;border-radius:50%;background:var(--c22304a,#22304a);color:var(--c8ecbff,#8ecbff);
              display:flex;align-items:center;justify-content:center;font-weight:700;
              font-size:16px;flex:0 0 auto}
 .correo .ini.viva{background:var(--ok-bg);color:var(--ok-txt);box-shadow:0 0 0 2px var(--ok-bd)}
 .correo .ini.mas{background:var(--acento-bg);color:var(--acento)}
 .correo .med{flex:1;min-width:0}
 .correo .tit{font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;
              text-overflow:ellipsis}
 .correo .baj{color:var(--c7c8797,#7c8797);font-size:12.5px;margin-top:2px;white-space:nowrap;
              overflow:hidden;text-overflow:ellipsis}
 .correo .lapiz{color:var(--c5c6675,#5c6675);padding:6px 4px;font-size:15px}
 .correo.nueva .tit{color:var(--c8ecbff,#8ecbff)}
 /* Entrar a las archivadas (cabecera) y devolver una (cada fila). Con el dedo tiene que
    ser un blanco grande: por eso el Devolver es un botón y no un iconito. */
 .barra-proy .op-arch{margin-left:auto;flex:none;font-size:12.5px;color:var(--c9fb4cc,#9fb4cc);
        background:var(--c141a26,#141a26);border:1px solid var(--c232c3b,#232c3b);border-radius:999px;padding:8px 13px;
        white-space:nowrap}
 .correo .devolver{flex:none;font-size:12.5px;color:var(--c8ecbff,#8ecbff);background:var(--c141d2b,#141d2b);
        border:1px solid var(--c24354b,#24354b);border-radius:10px;padding:9px 12px;white-space:nowrap}
 /* ⭐ El MISMO semaforo que la pantalla grande (Martin, 2026-08-17): VERDE la pelota
    es tuya, AMARILLO esta trabajando, ROJO fallo. Los colores son los de sesiones.html
    a proposito: es la misma informacion, no puede cambiar de idioma segun la pantalla. */
 .correo.espera{border-left:3px solid var(--ok);background:var(--c101c16,#101c16);padding-left:9px}
 .correo.espera .tit{color:var(--ok-txt)}
 .correo.espera .baj b{color:var(--ok);font-weight:600}
 .correo.trabajando{border-left:3px solid var(--aviso);background:var(--c1b1710,#1b1710);padding-left:9px}
 .correo.trabajando .tit{color:var(--aviso-txt)}
 .correo.trabajando .baj b{color:var(--aviso);font-weight:600}
 .correo.fallada{border-left:3px solid var(--mal);background:var(--c1e1214,#1e1214);padding-left:9px}
 .correo.fallada .tit{color:var(--mal-txt)}
 .correo.fallada .baj b{color:var(--mal-txt);font-weight:600}
 .pensando .reloj{color:var(--c5c6675,#5c6675);font-size:11.5px;margin-left:8px}
 /* Rojo apagado: es un freno, no un boton que uno quiera apretar de paso. */
 #parar{width:auto;padding:14px 16px;margin:0;font-size:15px;background:var(--mal-bg);
        color:var(--mal-txt);flex:0 0 auto;display:none}
 /* el cajón de proyectos entra desde la izquierda, como el menú del correo */
 #cajon{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;z-index:25}
 #cajon.abierto{display:block}
 #cajon .hoja-proy{position:absolute;left:0;top:0;bottom:0;width:76%;max-width:300px;
        background:var(--c111725,#111725);border-right:1px solid var(--c1e2636,#1e2636);padding:14px 0;overflow-y:auto}
 .carpeta{display:flex;align-items:center;gap:11px;padding:12px 14px;font-size:14.5px;
        position:relative;-webkit-touch-callout:none;user-select:none}
 .carpeta .ic{font-size:15px}
 .carpeta .nom{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .carpeta .num{color:var(--c5c6675,#5c6675);font-size:12px}
 /* "Esta carpeta maneja un navegador". Apagada para no competirle al nombre, que es lo
    unico que se viene a leer aca. Nunca en rojo: es un estado normal. */
 .carpeta .naveg-carp{flex:none;font-size:11px;opacity:.5;line-height:1}
 .carpeta.personalizada{background:color-mix(in srgb,var(--carp-color) 18%,var(--c141926,#141926));
        box-shadow:inset 3px 0 0 var(--carp-color)}
 .carpeta.personalizada.sel{background:color-mix(in srgb,var(--carp-color) 28%,var(--c16233a,#16233a))}
 .carpeta .editar-carp{flex:none;width:32px;height:32px;margin:0 -5px 0 0;padding:0;
        display:flex;align-items:center;justify-content:center;border-radius:50%;
        background:transparent;color:var(--c697689,#697689);font-size:14px;font-weight:400}
 .carpeta .editar-carp:active{background:rgba(var(--cffffff-rgb,255,255,255),.1);color:var(--cdce4ee,#dce4ee)}
 .carpeta.sel{background:var(--c16233a,#16233a);color:var(--c8ecbff,#8ecbff);border-radius:0 999px 999px 0;
              margin-right:12px;font-weight:600}
 /* ⭐ Mover y sacar carpetas, igual que en la pantalla grande (Martin, 2026-08-18).
    La carpeta LEVANTADA necesita fondo propio: si no, mientras la movés se ven las de
    abajo a través de ella y no se entiende cuál estás agarrando. */
 .carpeta.tomada{background:var(--c1b2537,#1b2537);border-radius:10px;z-index:3;
        box-shadow:var(--sombra-2)}
 .carpeta.se-va{transition:transform .28s ease, opacity .28s ease;
        transform:translateX(-110%);opacity:0}
 /* La que acaba de volver se ilumina una vez: es la unica forma de ver DONDE cayo. */
 .carpeta.vuelve{animation:carpVuelve 1.3s ease}
 @keyframes carpVuelve{0%{background:var(--c1d3350,#1d3350)}100%{background:transparent}}
 .carpeta.guardadas{color:var(--c7d8899,#7d8899);font-size:13.5px;border-top:1px solid var(--c1e2636,#1e2636);
        margin-top:6px;padding-top:13px}
 .carpeta.devolver{padding-left:34px;color:var(--c8b9ab0,#8b9ab0);font-size:13.5px}
 .carpeta.devolver .vol{color:var(--c8ecbff,#8ecbff);font-size:12.5px}
 /* El gesto hay que contarlo: en el telefono no hay nada que mirar que lo sugiera. */
 .pista-carp{color:var(--c5c6675,#5c6675);font-size:11.5px;line-height:1.45;padding:2px 14px 10px}
 /* Editor táctil: una hoja desde abajo. El cajón conserva su lugar y la carpeta se
    sigue viendo detrás, así el cambio de color o ícono tiene contexto inmediato. */
 #editorCarp{position:fixed;inset:0;z-index:29;background:rgba(0,0,0,.58);display:none;
        align-items:flex-end}
 #editorCarp.abierto{display:flex}
 #editorCarp .hoja-edit{width:100%;max-height:72dvh;overflow-y:auto;padding:18px 16px
        calc(18px + env(safe-area-inset-bottom));border-radius:24px 24px 0 0;
        background:var(--c151c29,#151c29);border-top:1px solid var(--c2b3547,#2b3547);box-shadow:var(--sombra-arriba)}
 #editorCarp .edit-cab{display:flex;align-items:center;gap:10px;margin-bottom:18px}
 #editorCarp .edit-cab b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #editorCarp .cerrar-edit{width:34px;height:34px;margin:0;padding:0;border-radius:50%;
        background:rgba(var(--cffffff-rgb,255,255,255),.07);color:var(--caab4c2,#aab4c2);font-size:16px}
 #editorCarp .edit-rot{font-size:11px;letter-spacing:.15em;text-transform:uppercase;
        color:var(--c697689,#697689);font-weight:700;margin:15px 0 9px}
 #editorCarp .colores,#editorCarp .icos-edit{display:flex;flex-wrap:wrap;gap:10px}
 /* El navegador del proyecto. Los dos campos van a lo ancho: en el telefono una ruta
    de perfil no entra en media fila. El aviso va apagado y NUNCA en rojo — que la
    carpeta tenga navegador es un estado normal, no un problema. */
 #editorCarp .naveg-edit,#editorCarp .naveg-sitios{width:100%;box-sizing:border-box;
   background:var(--c171d29,#171d29);color:var(--ce8ecf1,#e8ecf1);border:1px solid var(--c2a3342,#2a3342);border-radius:10px;
   padding:11px 12px;font-size:15px;margin:0 0 8px}
 #editorCarp .naveg-aviso{color:var(--c8b96a5,#8b96a5);font-size:12.5px;line-height:1.45}
 #editorCarp .color-edit{width:38px;height:38px;border-radius:50%;border:2px solid transparent;
        box-shadow:inset 0 0 0 1px rgba(var(--cffffff-rgb,255,255,255),.17)}
 #editorCarp .color-edit.sel,#editorCarp .ico-edit.sel{border-color:#fff;
        box-shadow:0 0 0 3px rgba(var(--c8ecbff-rgb,142,203,255),.25)}
 #editorCarp .color-edit.nada{display:flex;align-items:center;justify-content:center;
        background:var(--c222a37,#222a37);color:var(--c8793a4,#8793a4);font-size:17px}
 #editorCarp .rueda-edit{width:38px;height:38px;padding:0;border:0;border-radius:50%;
        overflow:hidden;background:transparent}
 #editorCarp .rueda-edit::-webkit-color-swatch-wrapper{padding:0}
 #editorCarp .rueda-edit::-webkit-color-swatch{border:2px solid var(--c536073,#536073);border-radius:50%}
 #editorCarp .ico-edit{width:46px;height:46px;margin:0;padding:0;border-radius:13px;
        background:var(--c202938,#202938);border:2px solid transparent;font-size:23px}
 /* ⭐ Lo mismo que la pantalla grande (Martin, 2026-08-17: "no son iguales, me faltan
    todos en el celular"): la bandeja TODAS arriba de las carpetas, el buscador de
    carpetas y el boton de sumar una. Si una pantalla tiene algo y la otra no, uno
    nunca sabe cual esta mirando. */
 .carpeta.todas{border-bottom:1px solid var(--c1e2636,#1e2636);margin-bottom:6px;padding-bottom:14px}
 .buscacarp{width:calc(100% - 28px);margin:0 14px 8px;padding:9px 11px;font-size:13.5px;
        background:var(--c0e1420,#0e1420);border:1px solid var(--c222c3d,#222c3d);border-radius:9px;color:var(--cdfe6f0,#dfe6f0)}
 .sumar-carp{color:var(--c8ecbff,#8ecbff);padding:12px 14px;font-size:14px}
 .filtro-ses{width:100%;box-sizing:border-box;margin:0 0 8px;padding:10px 12px;
        font-size:14px;background:var(--c0e1420,#0e1420);border:1px solid var(--c222c3d,#222c3d);border-radius:10px;
        color:var(--cdfe6f0,#dfe6f0)}
 .correo .eti{background:var(--c1b2436,#1b2436);color:var(--c8b9ab0,#8b9ab0);font-size:10.5px;border-radius:6px;
        padding:1px 6px;margin-left:6px;white-space:nowrap;vertical-align:middle}
 /* ⭐ La chapita del OTRO cerebro (Codex), la misma idea que en la compu: se marca
    solo lo que NO es Claude, que es lo que hay que notar. Fija, sin animación: es de
    qué familia es la charla, no un estado que cambie. */
 .correo .cer{background:var(--c122b1f,#122b1f);color:var(--ok-txt);border:1px solid var(--ok-bd);
        font-size:10.5px;font-weight:600;border-radius:6px;padding:1px 6px;
        margin-left:6px;white-space:nowrap;vertical-align:middle}
 /* La chapa de "se compacto y sigue en otra", la misma que en la pantalla grande
    (2026-08-20). Apagada, no es alarma: marca cual es la charla VIEJA. Se toca
    para saltar a la continuacion. */
 .correo .sigue{background:var(--c161b22,#161b22);color:var(--c8b96a5,#8b96a5);border:1px solid var(--c333b49,#333b49);
        font-size:10.5px;border-radius:6px;padding:1px 6px;
        margin-left:6px;white-space:nowrap;vertical-align:middle}
 /* ⭐ La chapa de BORRADOR, la MISMA que en la pantalla grande (pedido de Martin,
    2026-08-18). Lavanda y no verde/amarillo/rojo: esos tres son el semaforo de la
    conversacion y un borrador no es un estado de ella, es algo tuyo a medio escribir.
    Por eso va al lado del nombre y no pintando la fila. La animacion es un respiro lento
    (2,6 s): la bandeja puede tener veinte y veinte parpadeos serian una calesita. */
 .correo .borra{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;
        font-weight:600;color:var(--cc4b5fd,#c4b5fd);background:var(--c241d3a,#241d3a);border:1px solid var(--c4d3d7a,#4d3d7a);
        border-radius:999px;padding:1px 7px;margin-left:6px;white-space:nowrap;
        vertical-align:middle;animation:borradorRespira 2.6s ease-in-out infinite}
 @keyframes borradorRespira{0%,100%{box-shadow:0 0 0 0 rgba(var(--cc4b5fd-rgb,196,181,253),0);
                                    border-color:var(--c4d3d7a,#4d3d7a)}
                            50%{box-shadow:0 0 0 3px rgba(var(--cc4b5fd-rgb,196,181,253),.13);
                                border-color:var(--c7c69bd,#7c69bd)}}
 .correo .borra .plu{animation:latirBorra 2.6s ease-in-out infinite}
 @keyframes latirBorra{0%,100%{opacity:1} 50%{opacity:.35}}
 /* Lo que dejaste escrito, en el renglon de abajo: es lo que uno viene a recordar. */
 .correo .baj .bpre{color:var(--ca99ae0,#a99ae0);font-style:italic}
 /* Y en la pestaña de arriba, la misma señal en chiquito. */
 .tab .plu{color:var(--cc4b5fd,#c4b5fd);font-size:11px;margin-right:4px;
        animation:latirBorra 2.6s ease-in-out infinite}
 /* La pizarra entra como la MISMA pagina de la compu, a pantalla completa. */
 #cuerpo.pleno{padding:0;overflow:hidden}
 #cuerpo.pleno iframe{width:100%;height:100%;border:0;display:block}
 /* --- Hablarle: es una LLAMADA, no una grabadora --------------------------
    Nada de "apretá para grabar": entrás y ya te escucha, la onda se mueve con tu
    voz para que se note, y hay un solo botón, el de cortar. */
 #hablar{display:flex;flex-direction:column;align-items:center;justify-content:center;
         height:100%;gap:20px;text-align:center;padding:8px}
 #estado{font-size:21px;font-weight:700}
 #estado.escuchando{color:var(--ok-txt)} #estado.pensando{color:var(--aviso-txt)}
 #estado.hablando{color:var(--c8ecbff,#8ecbff)}  #estado.problema{color:var(--mal-txt);font-size:16px}
 #onda{display:flex;align-items:center;justify-content:center;gap:8px;height:120px}
 #onda i{width:13px;height:16px;border-radius:8px;background:var(--c2a6ea8,#2a6ea8);
         transition:height .07s linear}
 #onda.viva i{background:var(--c5eb8ff,#5eb8ff)}
 #onda.late i{animation:latir 1.2s infinite ease-in-out}
 #onda.late i:nth-child(2){animation-delay:.15s} #onda.late i:nth-child(3){animation-delay:.3s}
 #onda.late i:nth-child(4){animation-delay:.45s} #onda.late i:nth-child(5){animation-delay:.6s}
 @keyframes latir{0%,100%{height:16px} 50%{height:62px}}
 #dicho{color:var(--c7c8797,#7c8797);font-size:14px;font-style:italic;max-width:300px}
 #respuesta{background:var(--burbuja-ia);border-radius:16px;padding:14px 16px;font-size:calc(15px * var(--escala,1));
            line-height:1.45;max-width:330px;text-align:left;white-space:pre-wrap}
 #colgar{width:76px;height:76px;border-radius:50%;background:var(--mal-bd);color:var(--mal-txt);
         border:2px solid var(--mal);font-size:30px;margin:0;padding:0;flex:0 0 auto}
 #arrancar{width:auto;padding:18px 28px;background:var(--acento-bg);color:var(--acento);margin:0}
 /* ⚠ Al final del todo a proposito: estas reglas pisan a las de arriba (misma
    especificidad, gana la ultima) y son las que enganchan la pantalla al tema
    elegido. Puestas antes, el acento no cambiaba nada. */
 #barraArriba,#abajo,#escribir{background:var(--fondo2)}
 #abajo .dest.sel{color:var(--acento)}
 #abajo .dest.sel i{filter:drop-shadow(0 0 7px color-mix(in srgb,var(--acento) 45%,transparent))}
 .tab.sel{background:var(--acento-bg);color:var(--acento);border-color:var(--acento-bg)}
</style></head><body>

<div id="barraArriba"><div id="tabs"></div><div id="aspectoAqui"></div></div>
<div id="cuerpo"></div>
<div id="escribir">
  <input type="file" id="archivo" accept="image/*" multiple hidden onchange="elegirFotos(this.files)">
  <button id="clip" onclick="document.getElementById('archivo').click()">📎</button>
  <!-- ⚡ Skills y comandos: lo dibuja /estaticos/atajos.js, el MISMO botón que la
       pantalla de la compu y el chat de Laura. Acá era la única de las tres cajas de
       escribir que no lo tenía (2026-08-25). -->
  <span id="atajosAqui"></span>
  <textarea id="texto" rows="1" placeholder="Escribí…"></textarea>
  <button id="avisarTarea" onclick="alternarAviso()" title="Avisarme al celular cuando termine">Avisame</button>
  <button id="mandar" onclick="mandar()">Enviar</button>
  <button id="parar" onclick="parar()">⏹</button>
</div>
<nav id="abajo">
  <div class="dest" data-href="/estudio"><i>&#127916;</i><span>Estudio</span></div>
  <div class="dest" data-ir="panel"><i>🏠</i><span>Inicio</span></div>
  <div class="dest" data-ir="hablar"><i>🎙</i><span>Hablar</span></div>
  <div class="dest" data-ir="pizarra"><i>🧷</i><span>Pizarra</span></div>
  <div class="dest" data-ir="nueva"><i>💬</i><span>Sesiones</span></div>
</nav>
<div id="chapas"></div>
<div id="visor" onclick="this.classList.remove('abierto')"><img id="visorImg"></div>

<script>
const $ = s => document.querySelector(s);
// Las pestañas abiertas viven en el celular, no en el server: cada uno arma las suyas.
let pestanas = JSON.parse(localStorage.getItem('pestanas') || '[]');
let activa = localStorage.getItem('activa') || 'panel';
let sesiones = [];
// Firmas de lo ya dibujado: si la pantalla nueva es idéntica, no se toca el DOM
// (repintar de gusto te tira el scroll y te cierra los desplegables).
let firmaPanel = '', elegirFirma = '', mensajesPanel = [];
// ⭐ Qué lista de conversaciones se dibujó la última vez (carpeta + si estabas en las
// archivadas). Sirve para decidir cuándo la bandeja tiene que empezar ARRIBA de todo:
// ver `pintarElegir`.
let listaDibujada = '';
let panelUltimoHtml = '';
let panelPrecargando = null;
// El gasto del día para la tarjeta del inicio: se pide cada 5 minutos, no en cada repintada.
let gastoMovil = null, gastoPedido = 0;
// (el 'ocupado' global se fue: ahora es enVuelo[sid], uno por pestaña)

// El estado vive en el SERVIDOR: asi es el mismo entren desde el navegador o desde el
// icono de la pantalla de inicio, que en el celular son dos almacenamientos distintos.
// El localStorage queda de respaldo por si el panel no contesta.
const guardar = () => {
  localStorage.setItem('pestanas', JSON.stringify(pestanas));
  localStorage.setItem('activa', activa);
  fetch('/movil/pestanas', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({pestanas, activa})}).catch(()=>{});
};

function pintarAbajo(){
  const donde = ['panel','hablar','pizarra','nueva'].includes(activa) ? activa : 'nueva';
  document.querySelectorAll('#abajo .dest').forEach(d =>
    d.classList.toggle('sel', d.dataset.ir === donde));
}

function pintarTabs(){
  // Arriba SOLO las sesiones abiertas: los cuatro destinos fijos se mudaron a la
  // barra de abajo, donde llega el pulgar (2026-08-16). Si no hay ninguna sesión
  // abierta, esta barra directamente no se muestra y la pantalla gana lugar.
  const t = pestanas.map(p => {
    const viva = sesiones.some(s => s.id === p.sid && s.viva);
    return `<div class="tab ${activa===p.sid?'sel':''}" onclick="ir('${p.sid}')">
              ${viva?'<span class="viva">●</span> ':''}${
                hayBorrador(p.sid) ? '<span class="plu">✎</span>' : ''}${p.nombre}</div>`;
  });
  if (t.length) t.push(`<div class="tab mas" onclick="ir('nueva')">+</div>`);
  $('#tabs').innerHTML = t.join('');
  $('#tabs').classList.toggle('vacia', t.length === 0);
  pintarAbajo();
}

let recienAbierta = false;

// --- La direccion web: una por conversacion -----------------------------------------
// Pedido de Martin (2026-08-18): la barra de direcciones sigue a lo que estas mirando
// (`/movil?c=<id>` una charla, `/movil?v=panel` las pantallas fijas) y entrando por esa
// direccion la app abre ya parada ahi. Lo mecanico esta en /estaticos/direccion.js,
// compartido con la pagina de sesiones de la compu.
// ⚠ Una charla sin estrenar (`nueva-…`) no va a la direccion: ese id es provisorio.
function fijarDireccion(opciones){
  if (!window.Direccion) return;
  const fija = FIJAS.includes(activa);
  const p = pestanas.find(x => x.sid === activa);
  const real = !fija && !!p && !esNueva(activa);
  Direccion.fijar(fija ? {v: activa} : (real ? {c: activa} : {}),
                  Object.assign({titulo: real ? (p.nombre || 'Conversacion') : ''},
                                opciones || {}));
}

function ir(cual){
  // Lo que estabas escribiendo en la otra conversacion se guarda antes de soltarla, y la
  // que abris te devuelve lo suyo (el borrador, pedido de Martin del 2026-08-18).
  if (activa && activa !== cual) soltarBorrador();
  activa = cual; recienAbierta = true;      // que arranque en el ultimo mensaje
  // El inicio tiene varios datos que refresca en vivo. Mientras llegan de nuevo, se
  // muestra la ultima foto del inicio en vez de dejar pegada la ventana anterior.
  if (cual === 'panel' && panelUltimoHtml){
    const caja = $('#cuerpo');
    caja.dataset.vista = 'panel';
    caja.innerHTML = panelUltimoHtml;
  }
  fijarDireccion();
  guardar(); pintarTabs(); pintar();
  // Va DESPUES de `pintar()`: es ahi donde la caja se muestra, y escondida el alto del
  // texto mide cero y quedaba de un renglon con cinco escritos.
  if (!FIJAS.includes(cual)) ponerBorradorEnCaja(cual);
  // la barra se desplaza sola hasta la pestaña elegida: con varias abiertas, la
  // activa puede quedar fuera de la pantalla y uno no sabe donde esta parado
  setTimeout(() => { const s=document.querySelector('.tab.sel'); if(s)
    s.scrollIntoView({inline:'center', block:'nearest', behavior:'smooth'}); }, 30);
}

function cerrar(sid){
  pestanas = pestanas.filter(p => p.sid !== sid);
  if (activa === sid) activa = 'panel';
  guardar(); pintarTabs(); pintar();
}

async function accion(ruta){ await fetch(ruta,{method:'POST'}); pintar(); }

// ⭐ Cambiarle el cerebro a Laura desde el teléfono (pedido de Martín, 2026-08-19):
// la misma perilla que el selector del panel de la compu. Es una palabra en un archivo
// que voz.py relee antes de cada turno, así que es instantáneo y no reinicia nada.
// La charla NO se muda — cada cerebro retoma la suya, con el traspaso de lo último
// hablado —, y por eso la frase que devuelve el servidor se muestra un rato: cuenta
// exactamente eso.
let avisoCerebro = '';
async function cambiarCerebroLaura(v){
  try {
    const j = await (await fetch('/sesion/cerebro', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({cerebro: v})})).json();
    avisoCerebro = j.ok ? (j.frase || 'Listo.') : (j.motivo || 'No se pudo.');
  } catch(e){ avisoCerebro = 'No pude hablar con el panel.'; }
  firmaPanel = ''; pintarPanel();
  setTimeout(() => {
    avisoCerebro = ''; firmaPanel = '';
    if (activa === 'panel') pintarPanel();
  }, 8000);
}

// ⭐ Las perillas de la SESIÓN de Laura desde el inicio (pedido de Martín, 2026-08-20:
// "faltan los botones de configuración de la sesión, tanto para Codex como para
// Claude"): las mismas de la barra de la compu. Todas viven en el servidor — voz.py
// las relee antes de cada turno —, así que acá solo se avisa y se repinta.
function avisoInicio(txt){
  avisoCerebro = txt; firmaPanel = ''; pintarPanel();
  setTimeout(() => {
    avisoCerebro = ''; firmaPanel = '';
    if (activa === 'panel') pintarPanel();
  }, 8000);
}
async function ajusteLaura(ruta, campo, valor){
  try {
    const j = await (await fetch(ruta, {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({[campo]: valor})})).json();
    avisoInicio(j.ok ? 'Listo: vale desde el próximo mensaje.' : 'No se pudo.');
    if (j.ok) pintarPanel();
  } catch(e){ avisoInicio('No pude hablar con el panel.'); }
}
async function compactarLaura(){
  if (!confirm('¿Compactar la charla de Laura? La resume y sigue en una sesión nueva con ese resumen. Tarda un minuto.')) return;
  try {
    const j = await (await fetch('/sesion/compactar', {method:'POST'})).json();
    avisoInicio(j.ok ? 'Resumiendo la charla…' : (j.motivo || 'No se pudo.'));
  } catch(e){ avisoInicio('No pude hablar con el panel.'); }
}
async function nuevaLaura(){
  if (!confirm('¿Arrancar una sesión nueva? La charla de ahora queda archivada, no se pierde.')) return;
  try {
    const j = await (await fetch('/sesion/nueva', {method:'POST'})).json();
    avisoInicio(j.ok ? 'Arrancando de cero…' : (j.motivo || 'No se pudo.'));
  } catch(e){ avisoInicio('No pude hablar con el panel.'); }
}

const FIJAS = ['panel','pizarra','hablar','nueva'];
async function pintar(){
  // En el inicio la caja también se ve: es para escribirme a MÍ, y va por el buzón
  // (el mismo camino que el micrófono y Telegram), así no se bifurca ninguna charla.
  $('#escribir').style.display = (FIJAS.includes(activa) && activa !== 'panel') ? 'none' : 'flex';
  $('#texto').placeholder = activa === 'panel' ? 'Escribile a Laura…' : 'Escribí…';
  // la pizarra va a pantalla completa adentro de la pestaña: sin margen ni scroll
  $('#cuerpo').classList.toggle('pleno', activa==='pizarra');
  // adentro de una charla el cuerpo pega la cabecera al ras (ver #cuerpo.charla)
  $('#cuerpo').classList.toggle('charla', !FIJAS.includes(activa));
  // ⭐ Y la charla va a pantalla completa, como en WhatsApp (pedido de Martín,
  // 2026-08-20): sin la barra de pestañas ni la botonera de abajo. Se vuelve con
  // la flecha de la cabecera, que te deja en la lista de sesiones.
  document.body.classList.toggle('enCharla', !FIJAS.includes(activa));
  // salir de la pestaña suelta el micrófono: nadie quiere que el teléfono siga
  // escuchando porque se fue a mirar otra cosa
  if (activa !== 'hablar' && charla) cortarCharla('');
  if (activa === 'panel')   return pintarPanel();
  if (activa === 'pizarra') return pintarPizarra();
  if (activa === 'hablar')  return pintarHablar();
  if (activa === 'nueva')   return pintarElegir();
  return pintarSesion();
}

async function pintarPanel(enSegundoPlano=false){
  // ⚠ Dónde estabas leyendo ANTES de repintar: el inicio se rearma cada 3 s y, si
  // se manda el scroll al final siempre, no podés subir a leer nada — te tira abajo
  // solo (2026-08-16). Se guarda la posición y solo se baja si ya estabas abajo.
  const viejo = $('#hilo');
  const estabaAbajo = !viejo ||
        (viejo.scrollHeight - viejo.scrollTop - viejo.clientHeight < 60);
  const dondeEstaba = viejo ? viejo.scrollTop : 0;
  const mio = enSegundoPlano ? 0 : ++pintadoNro;
  // Desde el telefono cada espera serial es otra vuelta por Tailscale. Estos datos no
  // dependen entre si, asi que viajan juntos y el inicio espera solo al mas lento.
  const pedirJson = ruta => fetch(ruta).then(r => r.json());
  const pideGasto = Date.now() - gastoPedido > 300000;
  if (pideGasto) gastoPedido = Date.now();
  const [e, c, cbCrudo, mjCrudo, gasto] = await Promise.all([
    pedirJson('/status'), pedirJson('/chat'),
    pedirJson('/sesion/cerebro').catch(() => null),
    pedirJson('/sesion/modelo').catch(() => null),
    pideGasto ? pedirJson('/gasto').catch(() => null) : Promise.resolve(null)
  ]);
  if (!enSegundoPlano && (mio !== pintadoNro || activa !== 'panel')) return;
  mensajesPanel = c.items || [];
  // Con cuál de los dos cerebros piensa (Claude o Codex). Si el pedido falla, la
  // sección no se dibuja y el inicio queda como siempre, sin romper nada.
  let cb = cbCrudo;
  if (cb && (!cb.ok || !(cb.cerebros || []).length)) cb = null;
  // Los ajustes de la sesión de Laura (modelo, esfuerzos, contexto). Si el pedido
  // falla, la fila no se dibuja y el inicio queda como siempre.
  let mj = mjCrudo;
  if (mj && !mj.ok) mj = null;
  // El gasto de tokens del día, con Codex aparte (en el teléfono no hay mouse que
  // pase por arriba de ningún globito). Se pide cada 5 minutos como en la compu;
  // si falla, la tarjeta no se dibuja y listo.
  if (gasto && gasto.ok) gastoMovil = gasto;
  const prendidos = Object.values(e.servicios).filter(s => s.vivo).length;
  const total = Object.values(e.servicios).length;
  const estado = e.pausado ? 'pausa' : e.encendido ? 'aire' : 'off';
  const rotulo = {aire:'Al aire', pausa:'En pausa', off:'Apagada'}[estado];
  const dicho = [...c.items].reverse().find(m => m.t === 'ia' || m.t === 'claude');
  // La fila de perillas de la sesión: con Claude el modelo y el esfuerzo, con Codex
  // su esfuerzo propio; más Compactar, Nueva y el chip de contexto. Reusa las
  // pastillas .ajusSes de la cabecera de las charlas.
  let ajus = '';
  if (cb && mj){
    const op = (lista, val) => (lista || []).map(x =>
      `<option value="${x.id}" ${x.id === val ? 'selected' : ''}>${esc(x.nombre)}</option>`).join('');
    const sel = cb.activo === 'codex'
      ? (mj.codex && (mj.codex.modelos || []).length
         ? `<select class="codex ${mj.codex.modelo !== mj.codex.defecto ? 'puesto' : ''}"
              onchange="ajusteLaura('/sesion/modelo-codex','modelo',this.value)">${
              op(mj.codex.modelos, mj.codex.modelo)}</select>
            <select class="codex ${mj.codex.esfuerzo ? 'puesto' : ''}"
              onchange="ajusteLaura('/sesion/esfuerzo-codex','esfuerzo',this.value)">${
              op(mj.codex.esfuerzos, mj.codex.esfuerzo || '')}</select>
            <select class="codex ${mj.codex.velocidad ? 'puesto' : ''}"
              onchange="ajusteLaura('/sesion/velocidad-codex','velocidad',this.value)">${
              op(mj.codex.velocidades, mj.codex.velocidad || '')}</select>` : '')
      : `<select class="${mj.modelo !== mj.defecto ? 'puesto' : ''}"
           onchange="ajusteLaura('/sesion/modelo','modelo',this.value)">${
           op(mj.modelos, mj.modelo)}</select>
         <select class="${mj.esfuerzo ? 'puesto' : ''}"
           onchange="ajusteLaura('/sesion/esfuerzo','esfuerzo',this.value)">${
           op(mj.esfuerzos, mj.esfuerzo || '')}</select>`;
    const cx = mj.contexto, tok = cx && cx.tokens;
    const chip = tok ? `<span class="ctxSes ${cx.nivel === 'mucho' ? 'mucho' : ''}">${
      tok >= 1000000 ? (tok/1000000).toFixed(1).replace('.',',') + ' M'
                     : Math.round(tok/1000) + ' k'}</span>` : '';
    ajus = `<div class="ajusSes laura">${sel}
      <button class="${cx && cx.nivel === 'mucho' ? 'conviene' : ''}"
              onclick="compactarLaura()">Compactar</button>
      <button onclick="nuevaLaura()">Nueva</button>${chip}</div>`;
  }
  const serv = Object.entries(e.servicios).map(([k,s]) =>
    `<div class="linea" onclick="accion('/${s.vivo?'stop':'start'}/${k}')">
       <span class="punto ${s.vivo?'ok':'no'}"></span>
       <span class="nombre">${s.label}</span>
       <span class="accion-txt">${s.vivo?'apagar':'prender'}</span></div>`).join('');
  const html = `
    <div class="tablero ${estado}">
      <div class="rotulo">${rotulo}</div>
      <div class="latido"><i></i><i></i><i></i></div>
      <div class="sub">${e.pensando ? 'pensando…'
        : estado==='aire' ? 'decí Laura y te escucho'
        : estado==='pausa' ? 'no te está escuchando' : 'la voz está apagada'}</div>
    </div>
    <div class="cifras">
      <div class="cifra"><b>${prendidos}<span>/${total}</span></b><small>servicios</small></div>
      <div class="cifra"><b>${sesiones.filter(s=>s.viva).length}</b><small>sesiones activas</small></div>
      <div class="cifra"><b>${pestanas.length}</b><small>pestañas</small></div>
      ${gastoMovil ? `<div class="cifra"><b>${gastoMovil.linda}</b><small>${
        gastoMovil.codex && gastoMovil.codex.hoy
          ? 'cx ' + gastoMovil.codex.linda +
            (gastoMovil.codex.cupo != null ? ' · ' + Math.round(gastoMovil.codex.cupo) + '%' : '')
          : 'tokens hoy'}</small></div>` : ''}
    </div>
    <div class="rubro">Acciones</div>
    <div class="acciones">
      <button class="acto ${e.pausado?'prendido':''}" onclick="accion('/pausa')">
        <b>${e.pausado?'Volver a escuchar':'Pausar escucha'}</b>
        <small>${e.pausado?'vuelve a atender la palabra clave':'deja de oír hasta que vuelvas'}</small></button>
      <button class="acto" onclick="accion('/cortar')"><b>Que se calle</b>
        <small>corta lo que está diciendo ahora</small></button>
      <button class="acto" onclick="accion('/escuchar/claude')"><b>Hablarle ahora</b>
        <small>abre el micrófono de la computadora</small></button>
    </div>
    ${cb ? `<div class="rubro">Con qué cerebro piensa</div>
    <div class="cerebros">${cb.cerebros.map(x => `
      <button class="${x.id === cb.activo ? 'puesto ' + x.id : ''}"
              onclick="cambiarCerebroLaura('${x.id}')">${esc(x.nombre)}</button>`).join('')}
    </div>` : ''}
    ${ajus}
    ${avisoCerebro ? `<div class="cerebroAviso">${esc(avisoCerebro)}</div>` : ''}
    <div class="rubro">Servicios</div>
    <div class="tarjeta">${serv}</div>
    <div class="rubro">Lo último que dijo</div>
    <div class="tarjeta ultimo">${dicho ? esc(dicho.x||'').slice(0,400) : 'Todavía no dijo nada hoy.'}</div>
    <div class="rubro">Conversación</div>
    <div id="hilo">${c.items.slice(-25).map(m =>
      `<div class="msg ${m.t}">` +
      // las fotos que mandaste vienen aparte en el mismo mensaje: sin esto se veía
      // solo el texto y la imagen se perdía de vista (2026-08-16)
      (m.imgs || []).map(u => `<img class="foto" src="${u}" onclick="verFoto('${u}')">`).join('') +
      `${esc(m.x||'')}${m.h?`<span class="hora">${m.h}</span>`:''}</div>`).join('')}</div>`;
  // Cuando abriste la app parado en Sesiones, este armado corre antes de que toques
  // Laura. Guarda una foto fresca, pero no le roba el cuerpo a la charla que estabas
  // leyendo: al tocar Inicio ya está lista para mostrar.
  if (enSegundoPlano){ panelUltimoHtml = html; return; }
  // ⭐⭐ Si NADA cambió, no se toca el DOM. Rearmar la pantalla cada 3 s aunque no
  // hubiera novedades era lo que te tiraba el scroll: por más que se restaure la
  // posición, el navegador reinicia el contenedor y en el teléfono se nota igual.
  // Ahora el inicio solo se redibuja cuando de verdad hay algo nuevo (2026-08-16).
  const caja0 = $('#cuerpo');
  if (html === firmaPanel && caja0.dataset.vista === 'panel' && !enVuelo['panel']) return;
  firmaPanel = html;
  panelUltimoHtml = html;
  caja0.dataset.vista = 'panel';
  caja0.innerHTML = html;
  const h = $('#hilo');
  if (h && enVuelo['panel']){
    // el turno sigue corriendo: se mantienen tu mensaje y los puntitos hasta que la
    // respuesta aparezca en el hilo de verdad. ⚠ Tu mensaje se agrega SOLO si el
    // buzón todavía no lo registró: si no, se ve dos veces (2026-08-16, la misma
    // piedra que en las pestañas de sesiones).
    const mio = enVuelo['panel'].texto;
    const ya = cuentaPanel(c.items, mio) > (enVuelo['panel'].veces || 0);
    h.insertAdjacentHTML('beforeend',
      (ya ? '' : `<div class="msg vos">${esc(mio)}</div>`) +
      `<div class="msg ia pensando">pensando<span></span><span></span><span></span></div>`);
  }
  if (h) h.scrollTop = estabaAbajo ? h.scrollHeight : dondeEstaba;
  // Las fotos cargan después y al aparecer empujan el contenido: si estabas abajo,
  // hay que volver a bajar cuando terminan; si estabas leyendo arriba, no se toca.
  if (h && estabaAbajo)
    h.querySelectorAll('img.foto').forEach(i =>
      i.addEventListener('load', () => { h.scrollTop = h.scrollHeight; }, {once:true}));
}

// La lista de sesiones, como el correo: a la izquierda un cajón con los proyectos
// (las "carpetas"), y a la derecha las conversaciones de ese proyecto, una por fila.
// Referencia que dio Martín: Gmail (2026-08-16). Antes eran doce desplegables uno
// abajo del otro y había que scrollear a ciegas.
// ⭐ Se entra SIEMPRE por "Todas", igual que en la compu (Martin, 2026-08-17): el
// proyecto que estabas mirando ayer no es el que buscas hoy.
const TODAS = 'Todas las conversaciones';
let proyElegido = TODAS;
let filtroSes = '';       // el buscador de la bandeja Todas
let buscaCarp = '';       // el buscador de carpetas del cajon

// --- El teclado abierto esconde la barra de abajo ---------------------------
// Con el teclado afuera, la barra de abajo (Inicio/Hablar/Pizarra/Sesiones) quedaba
// flotando en el medio de la pantalla, arriba del teclado. Mientras escribís no la
// necesitás, así que se va y vuelve sola.
//
// ⚠⚠ La señal que manda es el FOCO, no el tamaño de la ventana. El primer intento
// miraba `visualViewport.height < innerHeight - 120`, que es lo que se recomienda por
// ahí, y NO funcionó: agregada a la pantalla de inicio, la app se achica entera con el
// teclado, así que los dos números bajan juntos y la cuenta nunca da. El foco en una
// caja de texto es la definición práctica de "hay teclado" en un teléfono y no depende
// de ninguna rareza del navegador (2026-08-17).
const ESCRIBIBLE = 'input, textarea, [contenteditable="true"]';
const verTeclado = si => document.body.classList.toggle('teclado', si);
document.addEventListener('focusin', e => {
  if (e.target.matches && e.target.matches(ESCRIBIBLE)) verTeclado(true);
});
document.addEventListener('focusout', () => setTimeout(() => {
  const a = document.activeElement;
  verTeclado(!!(a && a.matches && a.matches(ESCRIBIBLE)));
}, 80));
// Y de refuerzo, por si el teclado se abre sin foco nuestro (dictado, autocompletar):
// se compara contra el alto MÁS GRANDE visto, no contra `innerHeight`.
// ⚠ Este refuerzo también APAGA la marca cuando la pantalla vuelve a su altura
// (2026-08-20): antes solo la prendía, y si la ventana se achicaba por otra cosa
// —girar el teléfono, un ajuste de iOS— quedaba pegada y la barra de abajo no volvía
// más hasta recargar (captura de Martín). Solo se apaga SIN foco en una caja de
// texto: en la app instalada el teclado NO achica la ventana visual (la app entera
// se encoge), y apagar con foco desharía el arreglo del 2026-08-17.
if (window.visualViewport){
  const vv = window.visualViewport;
  let altoMax = 0;
  const mirar = () => {
    altoMax = Math.max(altoMax, vv.height);
    const a = document.activeElement;
    if (vv.height < altoMax - 120) verTeclado(true);
    else if (!(a && a.matches && a.matches(ESCRIBIBLE))) verTeclado(false);
  };
  vv.addEventListener('resize', mirar);
  // Girar el teléfono cambia cuál es el alto "normal": el máximo viejo no vale más
  // (en apaisado la pantalla entera es más baja que el máximo de parado, y la marca
  // se prendía sola para siempre).
  window.addEventListener('orientationchange', () => { altoMax = 0; setTimeout(mirar, 300); });
  mirar();
}

// --- Archivar deslizando el dedo hacia la izquierda -------------------------
// Pedido de Martín (2026-08-17): sacar de la bandeja las conversaciones que no querés
// ver más. No borra nada — es una lista de ids en el servidor, así que archivás acá y
// también desaparece en la compu.
// ⚠ Solo cuenta el gesto HORIZONTAL: si el dedo se va para abajo es scroll y hay que
// soltar la fila, o la lista se vuelve imposible de recorrer.
// ⭐ Y desde acá también se DESARCHIVAN (Martin, 2026-08-17): el botón 🗄 de la cabecera
// muestra las guardadas y cada una trae su "↩ Devolver". Antes archivabas con el dedo y
// no había vuelta atrás sin ir a la compu, que es dejar a alguien encerrado adentro.
// ⭐⭐ LA VERDAD LA TIENE EL SERVIDOR (`s.archivada`, de sesiones_archivadas.json) y nada
// más. Esto de acá es SOLO lo que todavía no confirmó: `{sid: true|false}`, para que la
// fila desaparezca (o vuelva) en el acto y para no perder el cambio sin señal. En cuanto
// el servidor dice que sí, la entrada se borra y manda él.
// ⚠⚠ NO volver a la versión anterior, que era un Set de ids guardado en el navegador y
// OR-eado con el flag del servidor (`archivadas.has(id) || s.archivada`). Ese Set solo
// crecía y se vaciaba en el navegador donde tocabas: devolver una charla desde la compu
// la sacaba del servidor pero el celular seguía teniéndola en SU copia, así que ahí
// quedaba archivada PARA SIEMPRE y no había ningún botón que la rescatara. Mismo defecto
// que tenían los íconos de carpeta antes de `aspecto_carpetas.json` (2026-08-25).
let archPend = JSON.parse(localStorage.getItem('sesArchPend') || '{}');
// La copia vieja se descarta a propósito: sus ids son justamente los que quedaron
// pegados. Lo que de verdad archivaste ya está en el servidor, que es quien contesta.
localStorage.removeItem('sesArchivadas');
const guardarArchPend = () => localStorage.setItem('sesArchPend', JSON.stringify(archPend));
// ¿Está archivada? Manda el pendiente si hay uno; si no, lo que dice el servidor.
const esArchivada = s => (s.id in archPend) ? archPend[s.id] : !!s.archivada;
let viendoArchivadas = false;
const ARCH_LARGO = 90;          // píxeles hacia la izquierda para que cuente

function verArchivadas(si){
  viendoArchivadas = si;
  abrirCajon(false);
  elegirFirma = '';
  pintarElegir();
}

async function archivarSesion(sid, si){
  archPend[sid] = si; guardarArchPend();
  elegirFirma = '';
  pintar();                          // que desaparezca ya, sin esperar al servidor
  let ok = false;
  try {
    const r = await fetch('/movil/archivar', {method:'POST', headers:{'Content-Type':'application/json'},
                                              body: JSON.stringify({sid, archivar: si})});
    ok = r.ok && (await r.json()).ok !== false;
  } catch (e) { /* el pendiente queda puesto y la pantalla lo sigue respetando */ }
  elegirFirma = '';
  await pintar();                    // ahora la lista ya trae el flag cambiado
  // ⚠ El pendiente se suelta DESPUÉS de repintar con datos frescos, nunca antes: con los
  // viejos todavía en memoria la fila pega un salto de vuelta por un instante.
  if (ok && archPend[sid] === si){ delete archPend[sid]; guardarArchPend(); }
}

function engancharDeslizar(){
  document.querySelectorAll('#cuerpo .correo[data-sid]').forEach(fila => {
    let x0 = 0, y0 = 0, dx = 0, horizontal = null;
    fila.addEventListener('touchstart', e => {
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; horizontal = null;
      fila.style.transition = 'none';
    }, {passive:true});
    fila.addEventListener('touchmove', e => {
      const t = e.touches[0];
      if (horizontal === null){
        const ax = Math.abs(t.clientX - x0), ay = Math.abs(t.clientY - y0);
        if (ax < 8 && ay < 8) return;              // todavía no se sabe para dónde va
        horizontal = ax > ay;
      }
      if (!horizontal) return;                     // es scroll: la fila no se mueve
      dx = Math.min(0, t.clientX - x0);            // solo hacia la izquierda
      fila.style.transform = 'translateX(' + dx + 'px)';
      fila.style.opacity = String(Math.max(.25, 1 + dx / 260));
    }, {passive:true});
    fila.addEventListener('touchend', () => {
      fila.style.transition = 'transform .18s ease, opacity .18s ease';
      if (horizontal && dx < -ARCH_LARGO){
        fila.style.transform = 'translateX(-110%)';
        fila.style.opacity = '0';
        setTimeout(() => archivarSesion(fila.dataset.sid, true), 170);
      } else {
        fila.style.transform = '';
        fila.style.opacity = '';
      }
    });
  });
}

// ⚠ El cajón vive adentro de #cuerpo, que se repinta solo: si no se recuerda que
// estaba abierto, se cierra en la cara del que está buscando una carpeta.
let cajonAbierto = false;
function abrirCajon(si){
  cajonAbierto = si;
  const c = $('#cajon');
  if (c) c.classList.toggle('abierto', si);
}

function elegirProyecto(nombre){
  proyElegido = nombre;
  abrirCajon(false);
  elegirFirma = '';           // forzar el redibujo con el proyecto nuevo
  pintarElegir();
}

function filtrarSes(v){ filtroSes = v.toLowerCase(); elegirFirma = ''; pintarElegir(); }
function buscarCarp(v){ buscaCarp = v.toLowerCase(); elegirFirma = ''; pintarElegir(); }

// Sumar una carpeta que todavia no tiene conversaciones, igual que en la compu.
async function sumarCarpeta(){
  const ruta = prompt('Pegá la ruta completa de la carpeta');
  if (!ruta) return;
  const pedir = cuerpo => fetch('/movil/carpeta', {method:'POST',
        headers:{'Content-Type':'application/json'}, body: JSON.stringify(cuerpo)}).then(r => r.json());
  let r;
  try { r = await pedir({ruta}); } catch(e){ return alert('No pude: ' + e); }
  if (!r.ok && r.puede_crear && confirm('Esa carpeta no existe. ¿La creo?')){
    try { r = await pedir({ruta, crear: true}); } catch(e){ return alert('No pude: ' + e); }
  }
  if (!r.ok) return alert(r.error || 'No pude agregarla');
  elegirProyecto(r.nombre);
}

// --- ⭐ Las carpetas del cajon: moverlas y sacarlas ----------------------------------
// Lo mismo que en la compu (pedido de Martin, 2026-08-18), y con LOS MISMOS datos: el
// orden y las escondidas viven en el servidor (`/carpetas/orden`, `/carpetas/ocultar`) y
// viajan adentro de `/movil/sesiones`, asi que lo que acomodaste en la compu ya esta
// acomodado aca —y al reves— sin un pedido aparte que haria saltar la lista un segundo
// despues de dibujarla.
// ⚠⚠ Sacar NO BORRA NADA: ni la carpeta del disco, ni sus conversaciones, ni su entrada
// en `carpetas_sesiones.json`. Solo deja de mostrarse, y el pie "Escondidas" la devuelve.
// ⭐ El GESTO es distinto al de la compu a proposito. Alla alcanza con arrastrar porque
// el mouse no hace scroll; aca el dedo ya tiene ocupado el arrastre para recorrer el
// cajon, asi que: deslizar a la IZQUIERDA la saca (el mismo gesto con el que se archiva
// una conversacion, para no aprender dos cosas) y MANTENERLA APRETADA la levanta para
// moverla. La regla de fondo es la misma que en la compu: cuando dos gestos se pelean el
// mismo renglon, se separan por COMO se hacen, no partiendo el renglon en pedacitos.
let ordenCarp = [], ocultasCarp = new Set(), viendoOcultas = false;
let aspectoCarp = {};
// El navegador de base que heredan las carpetas que no declaran el suyo.
let navegDefecto = {};
try { aspectoCarp = JSON.parse(localStorage.getItem('movilAspectoCarpetas') || '{}') || {}; }
catch(e){}
let arrastrandoCarp = false, movioCarpeta = false, marcarVuelve = '';
let selloCarp = 0;            // sube con cada cambio nuestro
let escribiendoCarp = 0;      // cambios nuestros todavia viajando al servidor
const LARGO_MOVER = 380;      // ms apretando hasta que la carpeta se levanta
const SACAR_LARGO = 90;       // pixeles hacia la izquierda para que cuente como sacarla

// ⚠⚠ La lista se refresca sola cada pocos segundos, asi que casi siempre hay un pedido
// en el aire, y una respuesta que salio antes de tu cambio vuelve con el orden VIEJO: sin
// esto, medio segundo despues de mover una carpeta la pantalla te la devolvia sola a
// donde estaba, sin ningun motivo visible. Una respuesta solo vale si salio en un momento
// TRANQUILO —nada cambiado desde entonces y ningun cambio nuestro viajando—; el pedido
// que sale con una escritura en curso queda marcado como no confiable de entrada, porque
// el servidor todavia le va a contestar con lo de antes.
function selloAhora(){ return escribiendoCarp ? -1 : selloCarp; }

function adoptarCarpetas(d, sello){
  if (arrastrandoCarp || escribiendoCarp || !d || !d.carpetas) return;
  if (sello !== undefined && sello !== selloCarp) return;
  ordenCarp = d.carpetas.orden || [];
  ocultasCarp = new Set(d.carpetas.ocultas || []);
  // El icono, el color y el apodo vienen por el mismo camino y con el mismo cuidado: una
  // respuesta que salio antes de tu cambio traeria el icono viejo.
  adoptarAspectoCarp(d.carpetas.aspecto, d.carpetas.iconosPropios, d.carpetas.defecto);
}

// Todo cambio nuestro pasa por aca: sube el sello y se anota como "viajando" hasta que el
// servidor conteste. Si el envio falla no se reintenta: quedas con tu cambio en pantalla
// y el proximo refresco tranquilo trae lo que el servidor tenga, que es lo honesto.
function anotarCarpetas(url, cuerpo){
  selloCarp++;
  escribiendoCarp++;
  fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify(cuerpo)})
    .catch(()=>{}).finally(() => { escribiendoCarp--; });
}

// El orden elegido manda; lo que no este en la lista (una carpeta que aparecio despues)
// va al final. Asi una carpeta nueva no obliga a reescribir nada y tampoco se cuela
// arriba de todo sin que la hayas puesto ahi.
function ordenarCarpetas(ps){
  const pos = new Map(ordenCarp.map((n, i) => [n, i]));
  return ps.slice().sort((a, b) => {
    const ia = pos.has(a.proyecto) ? pos.get(a.proyecto) : Infinity;
    const ib = pos.has(b.proyecto) ? pos.get(b.proyecto) : Infinity;
    return ia === ib ? 0 : ia - ib;
  });
}

function guardarOrdenCarpetas(){
  anotarCarpetas('/carpetas/orden', {orden: ordenCarp});
}

// ⭐⭐ La MISMA paleta que la pantalla de la compu, y a proposito (2026-08-25, pedido de
// Martin: "que no importa si abro desde el celular, la app de escritorio o desde otro
// navegador, siempre tengan estos iconos"). Antes cada pantalla tenia su juego: dieciseis
// emojis aca, otros dieciseis alla y siete colores sueltos que no existian del otro lado.
// Con paletas distintas, "el mismo icono en las dos pantallas" era imposible de elegir.
// Los colores van por NOMBRE (los seis tonos de `/sesiones`) y no por hex, asi el que
// elegis aca es exactamente el que se marca alla; la rueda libre sigue guardando hex, que
// las dos pantallas entienden igual.
const TONOS_CARP = {azul:'var(--ca8cdf5,#a8cdf5)', violeta:'var(--cc4b5fd,#c4b5fd)', rosa:'var(--cf9a8d4,#f9a8d4)',
                    turquesa:'var(--c5eead4,#5eead4)', arena:'var(--ce2cdb0,#e2cdb0)', gris:'var(--cc3ccd8,#c3ccd8)'};
const ICONOS_CARP = ['📁','📂','⭐','🔥','🧪','🛠','🎨','🤖','💼','📦','🌱','🎯','⚡','🧩','📊','🔒'];
let iconosPropiosCarp = [];      // los que Martin agrego con el ＋ en la compu
// Hasta que este navegador no haya sembrado lo suyo, el servidor solo SUMA: si adoptara
// sus ausencias, el primer refresco borraria los iconos que todavia no subieron.
// ⚠⚠ La llave lleva un 2 y no es un capricho: la primera version marcaba "ya sembre"
// aunque el panel contestara 404 (un 404 NO le hace saltar el `catch` a `fetch`), asi que
// una pantalla abierta antes del reinicio se anotaba sin haber subido nada y despues no lo
// reintentaba nunca. Cambiar el nombre hace que esos navegadores vuelvan a sembrar.
let aspectoCarpListo = !!localStorage.getItem('movilAspectoSembrado2');

function guardarAspectoCarp(){
  // ⭐ El navegador del proyecto NO se espeja en el telefono (2026-08-28): a diferencia
  // del icono y el color, esto no se dibuja en el primer cuadro, y un telefono con el
  // dato viejo se lo podria SEMBRAR de vuelta al servidor. Que un perfil de Chrome —o
  // sea, con que cuentas trabaja una sesion— vuelva a aparecer solo porque quedo en el
  // almacenamiento de un navegador es exactamente lo que no queremos.
  const espejo = {};
  for (const [n, a] of Object.entries(aspectoCarp)){
    const {navegador, sitios, ...resto} = a || {};
    if (Object.keys(resto).length) espejo[n] = resto;
  }
  localStorage.setItem('movilAspectoCarpetas', JSON.stringify(espejo));
}

// El color guardado puede ser el nombre de un tono (elegido en cualquiera de las dos
// pantallas) o un hex de la rueda. Lo que no reconocemos se usa tal cual.
const colorCarp = v => TONOS_CARP[v] || v || '';
// El apodo es solo el ROTULO: `data-proy` y todo lo demas siguen usando el nombre real.
const apodoCarp = n => (aspectoCarp[n] || {}).apodo || n;
// Con que navegador termina trabajando una carpeta: el suyo, o el de base si no dijo
// nada; "ninguno" es el apagado explicito y no hereda. Misma cuenta que `navegador_de()`.
function navegEfectivo(carpeta){
  const puesto = (aspectoCarp[carpeta] || {}).navegador || '';
  if (puesto === 'ninguno') return '';
  return puesto || navegDefecto.navegador || '';
}

function estiloCarpeta(nombre){
  const a = aspectoCarp[nombre] || {};
  return a.color ? ` style="--carp-color:${colorCarp(a.color)}"` : '';
}

// Lo que llega del servidor adentro de `/movil/sesiones` (mismo camino que el orden).
function adoptarAspectoCarp(ap, propios, defecto){
  if (!ap) return;
  navegDefecto = defecto || {};
  if (aspectoCarpListo) aspectoCarp = {};
  for (const [n, a] of Object.entries(ap))
    aspectoCarp[n] = Object.assign({}, aspectoCarp[n] || {}, a);
  if (Array.isArray(propios) && aspectoCarpListo) iconosPropiosCarp = propios;
  guardarAspectoCarp();
}

// ⭐⭐ Sembrado, una sola vez por navegador. Martin lo pidio explicito: "porfa no pierdas
// lo que ya tengo porque tarde mucho en ponerlos". El servidor no pisa nada de lo que ya
// tenga, deja copia con fecha en `logs/` y anota los choques para que el decida.
async function sembrarAspectoCarp(){
  if (localStorage.getItem('movilAspectoSembrado2')) return;
  // ⚠⚠ Solo se da por sembrado si el servidor DIJO que si: ver el comentario de arriba.
  try {
    const r = await fetch('/carpetas/aspecto/sembrar', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({origen:'celu', carpetas: aspectoCarp})});
    if (!r.ok) return;
    if (!((await r.json().catch(() => ({}))).ok)) return;
  } catch(e){ return; }     // sin panel no se marca: se reintenta el proximo arranque
  localStorage.setItem('movilAspectoSembrado2', '1');
  aspectoCarpListo = true;
}
sembrarAspectoCarp();

function abrirEditorCarp(ev, nombre){
  if (ev){ ev.preventDefault(); ev.stopPropagation(); }
  const a = aspectoCarp[nombre] || {};
  const e = $('#editorCarp');
  if (!e) return;
  e.dataset.proy = nombre;
  e.querySelector('.edit-nombre').textContent = apodoCarp(nombre);
  e.querySelector('.colores').innerHTML =
    Object.entries(TONOS_CARP).map(([k, c]) => `<button class="color-edit ${a.color===k?'sel':''}"
      style="background:${c}" data-color="${k}" aria-label="Elegir color"></button>`).join('') +
    `<button class="color-edit nada ${a.color?'':'sel'}" data-color="" aria-label="Sin color">×</button>` +
    `<input class="rueda-edit" type="color" value="${colorCarp(a.color) || '#8ecbff'}" aria-label="Otro color">`;
  // ⭐ Los iconos que Martin agrego a mano en la compu tambien estan aca, y el que la
  // carpeta YA usa aparece siempre aunque no este en el juego: si no, el editor diria
  // "ninguno" mientras la carpeta luce uno, que es la clase de contradiccion que te hace
  // desconfiar de la pantalla (misma regla que en `/sesiones`).
  const sueltoIco = a.icono && !ICONOS_CARP.includes(a.icono)
                            && !iconosPropiosCarp.includes(a.icono) ? [a.icono] : [];
  e.querySelector('.icos-edit').innerHTML =
    ICONOS_CARP.concat(iconosPropiosCarp, sueltoIco).map(i =>
    `<button class="ico-edit ${a.icono===i?'sel':''}" data-ico="${i}">${i}</button>`).join('') +
    `<button class="ico-edit ${a.icono?'':'sel'}" data-ico="">×</button>`;
  e.querySelectorAll('[data-color]').forEach(b => b.onclick = () => ponerColorCarp(nombre, b.dataset.color));
  // ⚠ Mientras arrastras la rueda se ve en el acto pero NO se manda: serian cien
  // escrituras por un color. Sube al soltar (`change`), igual que en la compu.
  e.querySelector('.rueda-edit').oninput  = x => ponerAspectoCarp(nombre, 'color', x.target.value, false);
  e.querySelector('.rueda-edit').onchange = x => ponerColorCarp(nombre, x.target.value);
  e.querySelectorAll('[data-ico]').forEach(b => b.onclick = () => ponerIconoCarp(nombre, b.dataset.ico));
  pintarNavegCarp(e, nombre, a);
  e.classList.add('abierto');
}

// ⭐⭐ El navegador del proyecto (2026-08-28), la MISMA perilla que en la compu y sobre
// el mismo dato: la carpeta declara con que perfil de Chrome trabajan sus conversaciones,
// y ese campo es el interruptor (sin perfil, esa carpeta no abre paginas). No hay perilla
// por conversacion a proposito, igual que en Codex.
// ⚠ Elegir el perfil desde el telefono no tiene mucho sentido —el navegador vive en la
// laptop y no lo estas viendo—, pero se puede: Martin lo pidio en las dos pantallas.
let perfilesChrome = null;

async function pintarNavegCarp(e, nombre, a){
  const sel = e.querySelector('.naveg-edit');
  const campo = e.querySelector('.naveg-sitios');
  const aviso = e.querySelector('.naveg-aviso');
  if (!sel) return;
  campo.value = a.sitios || '';
  const contar = () => {
    // ⚠ Sin extension conectada, la sesion no sabe cual de los navegadores prendidos es
    // el suyo — y siempre hay mas de uno. Se mira el EFECTIVO (el heredado, si esta
    // carpeta no declara el suyo), o el aviso hablaria de otra cosa que la que va a usar.
    const efectivo = sel.value === 'ninguno' ? ''
                   : (sel.value || navegDefecto.navegador || '');
    const p = (perfilesChrome || []).find(x => x.ruta === efectivo);
    aviso.textContent = !efectivo
      ? 'Sin navegador: las conversaciones de esta carpeta no abren páginas.'
      : (p && !p.conectado
          ? 'Todavía no conectó su extensión de Claude: abrí ese Chrome y activala.'
          : (p && p.personal
              ? 'Ojo: es tu Chrome de siempre, con todas tus cuentas abiertas adentro.'
              : 'Abre solo, y trabaja con lo que esté logueado en ese perfil.'));
  };
  // ⚠ NO se usa `anotarCarpetas` para esto: ese se come los errores con un catch vacio,
  // y aca el servidor puede decir que no (perfil que ya no existe, o panel viejo que
  // contesta 404 sin conocer el campo). Un permiso guardado a medias y en silencio es
  // peor que uno que falla fuerte — la misma leccion que costo los iconos el 2026-08-25.
  const guardar = async (c, v) => {
    let ok = false, error = '';
    try {
      const r = await fetch('/carpetas/aspecto', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({carpeta: nombre, [c]: v || ''})});
      const j = r.ok ? await r.json().catch(()=>({})) : {};
      ok = !!(r.ok && j.ok);
      error = j.error || (r.status === 404 ? '¿el panel viejo? reinicialo' : 'no se pudo');
    } catch(err){ error = 'no llegué al panel'; }
    if (ok){
      aspectoCarp[nombre] = Object.assign({}, aspectoCarp[nombre] || {}, {[c]: v || ''});
      if (!v) delete aspectoCarp[nombre][c];
      guardarAspectoCarp();
      // ⚠ `pintarElegir()` rehace la pantalla ENTERA, y el editor es parte de ese HTML:
      // sin volver a abrirlo, elegir un navegador te cierra la hoja en la cara. Es el
      // mismo remate que ya usa `ponerAspectoCarp` con el color y el icono.
      elegirFirma = ''; pintarElegir();
      setTimeout(() => abrirEditorCarp(null, nombre));
    } else {
      aviso.textContent = 'No se guardó: ' + error;
    }
    return ok;
  };
  if (!perfilesChrome){
    try {
      const r = await fetch('/carpetas/navegadores');
      perfilesChrome = r.ok ? ((await r.json()).perfiles || []) : [];
    } catch(err){ perfilesChrome = []; }
  }
  const puesto = a.navegador || '';
  const nomDe = r => ((perfilesChrome || []).find(x => x.ruta === r) || {}).nombre || r;
  // Tres estados: heredar el de base (vacio), apagarlo solo aca ("ninguno") u otro perfil.
  sel.innerHTML =
    `<option value="">${navegDefecto.navegador
       ? 'El de siempre (' + nomDe(navegDefecto.navegador) + ')' : 'Sin navegador'}</option>` +
    (navegDefecto.navegador
      ? `<option value="ninguno"${puesto === 'ninguno' ? ' selected' : ''}>Ninguno, solo para esta carpeta</option>` : '') +
    perfilesChrome.map(p => `<option value="${p.ruta.replace(/"/g,'&quot;')}"${
      p.ruta === puesto ? ' selected' : ''}>${p.nombre}${
      p.personal ? ' (todas tus cuentas)' : ''}</option>`).join('') +
    // ⚠ El que esta puesto SIEMPRE aparece, aunque el disco ya no lo tenga: si no, el
    // editor diria "sin navegador" mientras la carpeta tiene uno. Misma regla que el
    // icono que la carpeta usa y ya no esta en el juego.
    (puesto && !perfilesChrome.some(p => p.ruta === puesto)
      ? `<option value="${puesto.replace(/"/g,'&quot;')}" selected>${puesto} (no lo encuentro)</option>` : '');
  contar();
  sel.onchange = async () => { if (await guardar('navegador', sel.value)) contar(); };
  campo.onchange = () => guardar('sitios', campo.value.trim());
}

function cerrarEditorCarp(){ const e=$('#editorCarp'); if(e)e.classList.remove('abierto'); }

// Un cambio del editor. Va al servidor SOLO el campo que tocaste (asi el celular no le
// pisa a la compu lo que la compu eligio) y se manda ANTES de repintar, porque repintar
// sale a pedir la lista de nuevo: ver `anotarCarpetas`.
function ponerAspectoCarp(nombre, campo, valor, subir=true){
  aspectoCarp[nombre] = Object.assign({}, aspectoCarp[nombre] || {}, {[campo]: valor});
  if (!valor) delete aspectoCarp[nombre][campo];
  if (!Object.keys(aspectoCarp[nombre]).length) delete aspectoCarp[nombre];
  guardarAspectoCarp();
  if (subir) anotarCarpetas('/carpetas/aspecto', {carpeta: nombre, [campo]: valor || ''});
  elegirFirma=''; pintarElegir(); setTimeout(()=>abrirEditorCarp(null,nombre));
}
function ponerColorCarp(nombre, color){ ponerAspectoCarp(nombre, 'color', color); }
function ponerIconoCarp(nombre, icono){ ponerAspectoCarp(nombre, 'icono', icono); }

// Sacar una carpeta (o devolverla). La animacion corre ANTES de repintar: si no, el
// renglon desaparece de un saque y no se ve que fue lo que se fue.
async function ocultarCarpeta(nombre, ocultar){
  const fila = document.querySelector('#cajon .carpeta[data-proy="' + CSS.escape(nombre) + '"]');
  if (ocultar && fila){
    fila.classList.add('se-va');
    await new Promise(r => setTimeout(r, 280));
  }
  ocultar ? ocultasCarp.add(nombre) : ocultasCarp.delete(nombre);
  if (!ocultar) marcarVuelve = nombre;
  // ⚠ El aviso al servidor va ANTES de repintar: repintar sale a pedir la lista de nuevo,
  // y si en ese momento el cambio todavia no salio, la respuesta vuelve con lo de antes y
  // te deshace lo que acabas de hacer.
  anotarCarpetas('/carpetas/ocultar', {proyecto: nombre, ocultar});
  // Si estabas parado en la que sacaste, la bandeja vuelve a Todas: quedarse mirando una
  // carpeta que ya no esta en la lista no tiene con que volver.
  if (ocultar && proyElegido === nombre) proyElegido = TODAS;
  elegirFirma = '';
  pintarElegir();
}

// Los dos gestos del dedo sobre una carpeta, mas el toque de siempre para entrar.
function engancharCarpetas(){
  document.querySelectorAll('#cajon .carpeta[data-proy]').forEach(fila => {
    let x0 = 0, y0 = 0, dx = 0, horizontal = null, reloj = 0, tomada = false;
    fila.onclick = () => {
      // ⚠ El toque que cierra un arrastre NO entra al proyecto: soltar la carpeta donde
      // la moviste no puede ademas cambiarte de carpeta.
      if (movioCarpeta){ movioCarpeta = false; return; }
      elegirProyecto(fila.dataset.proy);
    };
    const lapiz = fila.querySelector('.editar-carp');
    if (lapiz){
      lapiz.onclick = e => abrirEditorCarp(e, fila.dataset.proy);
      lapiz.addEventListener('touchstart', e => e.stopPropagation(), {passive:true});
      lapiz.addEventListener('touchmove', e => e.stopPropagation(), {passive:true});
      lapiz.addEventListener('touchend', e => e.stopPropagation(), {passive:true});
    }
    fila.addEventListener('touchstart', e => {
      const t = e.touches[0];
      x0 = t.clientX; y0 = t.clientY; dx = 0; horizontal = null; tomada = false;
      // ⚠⚠ El freno se limpia acá, al EMPEZAR el toque, y no cuando se lo usa. Con el
      // dedo, un arrastre puede terminar sin que el navegador dispare ningun clic, y
      // entonces el freno quedaba puesto y se comia el PROXIMO toque: movias una carpeta
      // y despues tocabas otra y no entraba, sin que nada lo explicara.
      movioCarpeta = false;
      fila.style.transition = 'none';
      reloj = setTimeout(() => {
        tomada = true; arrastrandoCarp = true;
        fila.classList.add('tomada');
        if (navigator.vibrate) navigator.vibrate(12);   // el unico aviso de que se levanto
      }, LARGO_MOVER);
    }, {passive:true});
    // ⚠ passive:false porque estando levantada hay que FRENAR el scroll del cajon: si
    // no, la carpeta sube con el dedo y la lista se va para el otro lado.
    fila.addEventListener('touchmove', e => {
      const t = e.touches[0];
      if (tomada){
        e.preventDefault();
        const dy = t.clientY - y0;
        fila.style.transform = 'translateY(' + dy + 'px)';
        // Al pasar el dedo por el medio de una vecina, se cambian de lugar y el punto de
        // partida se muda ahi: asi el renglon queda pegado al dedo y no se va acumulando.
        const hermanas = [...fila.parentNode.querySelectorAll('.carpeta[data-proy]')]
                           .filter(c => c !== fila);
        for (const h of hermanas){
          const r = h.getBoundingClientRect();
          const medio = r.top + r.height / 2;
          const filaVaDespues = h.compareDocumentPosition(fila) & Node.DOCUMENT_POSITION_FOLLOWING;
          const filaVaAntes = h.compareDocumentPosition(fila) & Node.DOCUMENT_POSITION_PRECEDING;
          if (dy < 0 && t.clientY < medio && filaVaDespues){
            h.parentNode.insertBefore(fila, h);
          } else if (dy > 0 && t.clientY > medio && filaVaAntes){
            h.parentNode.insertBefore(fila, h.nextSibling);
          } else continue;
          y0 = t.clientY; fila.style.transform = '';
          break;
        }
        return;
      }
      if (horizontal === null){
        const ax = Math.abs(t.clientX - x0), ay = Math.abs(t.clientY - y0);
        if (ax < 8 && ay < 8) return;              // todavia no se sabe para donde va
        horizontal = ax > ay;
        clearTimeout(reloj);                       // se movio: ya no es "mantener apretado"
      }
      if (!horizontal) return;                     // es scroll del cajon: no se toca
      dx = Math.min(0, t.clientX - x0);            // solo hacia la izquierda
      fila.style.transform = 'translateX(' + dx + 'px)';
      fila.style.opacity = String(Math.max(.25, 1 + dx / 260));
    }, {passive:false});
    fila.addEventListener('touchend', () => {
      clearTimeout(reloj);
      fila.style.transition = 'transform .18s ease, opacity .18s ease';
      if (tomada){
        fila.classList.remove('tomada');
        fila.style.transform = '';
        arrastrandoCarp = false;
        movioCarpeta = true;
        // El orden nuevo sale de como quedaron los renglones. Las escondidas y las que
        // el buscador dejo afuera conservan su lugar detras.
        const vistas = [...fila.parentNode.querySelectorAll('.carpeta[data-proy]')]
                         .map(c => c.dataset.proy);
        ordenCarp = vistas.concat(ordenCarp.filter(n => !vistas.includes(n)));
        guardarOrdenCarpetas();
        elegirFirma = '';        // la lista quedo movida a mano: que el proximo pintado la rearme
        return;
      }
      if (horizontal && dx < -SACAR_LARGO){
        fila.style.transform = 'translateX(-110%)';
        fila.style.opacity = '0';
        movioCarpeta = true;
        setTimeout(() => ocultarCarpeta(fila.dataset.proy, true), 150);
      } else {
        fila.style.transform = '';
        fila.style.opacity = '';
      }
    });
  });
  document.querySelectorAll('#cajon [data-volver]').forEach(x =>
    x.onclick = () => ocultarCarpeta(x.dataset.volver, false));
  const ver = $('#verOcultas');
  if (ver) ver.onclick = () => { viendoOcultas = !viendoOcultas; elegirFirma = ''; pintarElegir(); };
}

const inicial = t => (t || '?').trim()[0].toUpperCase();

// ⭐⭐ EL SEMAFORO, igual que en la pantalla grande (Martin, 2026-08-17). Se copio
// entero a proposito: si las dos pantallas dicen lo mismo con distinto criterio, el
// color deja de significar algo.
//   ROJO       lo ultimo que mandaste fallo
//   AMARILLO   esta trabajando ahora
//   VERDE      te esta esperando a VOS, y todavia no entraste a leerla
// Un turno lanzado desde aca o desde el panel VIVE SOLO MIENTRAS PIENSA: si el proceso
// esta, esta trabajando, aunque haga rato que no escribe (puede pasar minutos adentro
// de una herramienta sin tocar el archivo). Lo unico que puede estar vivo sin hacer
// nada es una ventana de Claude Code abierta en la compu.
let visto    = JSON.parse(localStorage.getItem('sesVisto') || '{}');
let falladas = JSON.parse(localStorage.getItem('sesFalladas') || '{}');
let parados  = {};        // las que cortaste vos: su error no es una falla
const falloQue = v => (v && typeof v === 'object') ? v.que : String(v || 'fallo');
const falloTs  = v => (v && typeof v === 'object') ? (v.ts || 0) : 0;
const guardarMarcas = () => {
  localStorage.setItem('sesVisto', JSON.stringify(visto));
  localStorage.setItem('sesFalladas', JSON.stringify(falladas));
};

function estadoSes(s){
  if (falladas[s.id]) return 'fallada';
  // ⭐⭐ `ocupada` va PRIMERO y es la senal que manda (Martin, 2026-08-23, con la captura
  // de la bandeja: una charla de Codex contestando y en la lista no decia nada). Es el
  // candado real de los turnos abiertos del servidor (`_TURNOS_ABIERTOS`), o sea el
  // mismo que despues rechaza el proximo mensaje. `viva` no alcanza: un turno de Codex
  // lanzado desde el panel puede no aparecer como proceso vivo del listado, asi que la
  // fila quedaba gris mientras adentro la caja decia "Esta contestando". Faltaba solo
  // aca: la pantalla grande ya decidia asi (`estado()` en sesiones.html).
  if (s.ocupada) return 'trabajando';
  const ahora = Date.now() / 1000;
  if (s.viva && !s.interactiva) return 'trabajando';
  if (s.viva && (ahora - (s.ts || 0)) <= 45) return 'trabajando';
  if (s.ultimo !== 'claude') return '';
  // ⭐ Queda VERDE hasta que ENTRES, no importa cuanto pase (Martin, 2026-08-17: "que
  // quede verde hasta que yo entre"). Antes se apagaba sola a la hora y las que te
  // esperaban de anoche amanecian grises, como si ya las hubieras leido.
  if ((visto[s.id] || 0) >= (s.ts || 0)) return '';         // ya entraste a leerla
  return 'espera';
}

// Al estrenar ese criterio se dan por vistas las viejas de una sola vez: si no, la
// primera vez se prende en verde media pantalla de conversaciones de la semana pasada.
function sembrarVisto(lista){
  if (localStorage.getItem('sembradoVisto')) return;
  const corte = Date.now() / 1000 - 3600;
  lista.forEach(s => { if (!s.viva && (s.ts || 0) < corte) visto[s.id] = s.ts || 0; });
  localStorage.setItem('sembradoVisto', '1');
  guardarMarcas();
}

const DICE = {espera: 'te esta esperando', trabajando: 'trabajando', fallada: 'fallo'};

// Si una marcada en rojo escribio DESPUES del error, no fallo nada: se corto la
// conexion y la sesion siguio trabajando. La marca se borra sola.
function verificarFalladas(lista){
  let limpie = false;
  for (const sid of Object.keys(falladas)){
    const s = lista.find(x => x.id === sid);
    if (!s || s.ultimo !== 'claude') continue;
    if ((s.ts || 0) > falloTs(falladas[sid]) + 2){ delete falladas[sid]; limpie = true; }
  }
  if (limpie){ elegirFirma = ''; guardarMarcas(); }
}

// ⭐⭐ La lista de la ultima vez, guardada en el telefono. Es lo que hace que la pantalla
// de conversaciones APAREZCA DIBUJADA en vez de quedarse en blanco esperando (mismo
// arreglo que en la pantalla de la compu, pedido de Martin del 2026-08-18: "fijate si
// podemos aplicar esto en el celular tambien"). Aca pesa mas todavia: el telefono entra
// por Tailscale, asi que al medio segundo del servidor hay que sumarle la red.
// ⚠ Lo primero que ves puede estar viejo; se repinta solo cuando llega lo fresco.
let listaSes = null;
try { listaSes = JSON.parse(localStorage.getItem('movilSesiones') || 'null'); } catch(e){}
if (listaSes && listaSes.proyectos) sesiones = listaSes.proyectos.flatMap(p => p.sesiones);
// ⭐ El orden de las carpetas sale de esta misma copia guardada: por eso el primer
// dibujo —el que se hace sin red— ya las muestra acomodadas como las dejaste.
adoptarCarpetas(listaSes);

async function traerSesiones(){
  const selloAlPedir = selloAhora();   // con que idea de las carpetas salio este pedido
  let d;
  try { d = await (await fetch('/movil/sesiones')).json(); } catch(e){ return null; }
  if (!d || !d.proyectos) return null;
  listaSes = d;
  adoptarCarpetas(d, selloAlPedir);
  try { localStorage.setItem('movilSesiones', JSON.stringify(d)); } catch(e){}
  sesiones = d.proyectos.flatMap(p => p.sesiones);
  // ⚠ Estas dos van SOLO con datos frescos: `sembrarVisto` marca como leidas las viejas
  // y `verificarFalladas` borra marcas rojas — con una lista de hace un rato estarian
  // decidiendo con fechas que ya no valen.
  verificarFalladas(sesiones);
  sembrarVisto(sesiones);
  await traerBorradores();
  return d;
}

// --- ⭐ EL BORRADOR de cada conversacion ---------------------------------------------
// Lo que empezaste a escribirle a una sesion y no mandaste (pedido de Martin, 2026-08-18).
// Vive en el SERVIDOR, asi que el borrador que arrancaste en la compu esta tambien aca —
// y al reves. Esta copia local es para que la chapa aparezca EN EL ACTO al escribir.
// ⚠ Vacio se guarda como '' y no se borra la entrada: '' quiere decir "de esta sabemos
// que no tiene", y es lo que apaga la chapa al toque cuando vacias la caja.
let borradores = {};
try { borradores = JSON.parse(localStorage.getItem('movilBorradores') || '{}') || {}; } catch(e){}
const guardarBorradores = () =>
  localStorage.setItem('movilBorradores', JSON.stringify(borradores));
const borradorDe = (sid, anticipo) =>
  borradores[sid] !== undefined ? borradores[sid] : (anticipo || '');
const hayBorrador = (sid, anticipo) => !!borradorDe(sid, anticipo).trim();
function vistaBorrador(sid, anticipo){
  const t = borradorDe(sid, anticipo).replace(/\\s+/g, ' ').trim();
  return t.length > 70 ? t.slice(0, 70) + '…' : t;
}

// ⚠⚠ El de la conversacion que estas MIRANDO no se pisa nunca: ese lo estas escribiendo
// vos ahora mismo. Lo mismo las charlas sin estrenar, que el servidor ni conoce.
async function traerBorradores(){
  let b;
  try { b = await (await fetch('/movil/borradores')).json(); } catch(e){ return; }
  if (!b || typeof b !== 'object') return;
  const nuevos = {};
  for (const [sid, v] of Object.entries(b))
    if (v && (v.texto || '').trim()) nuevos[sid] = v.texto;
  for (const [sid, t] of Object.entries(borradores))
    if (esNueva(sid) || sid === activa) nuevos[sid] = t;
  if (JSON.stringify(nuevos) === JSON.stringify(borradores)) return;
  borradores = nuevos;
  guardarBorradores();
  elegirFirma = '';                  // que la bandeja repinte con las chapas nuevas
  // Lo escribiste en la compu y entrás por el teléfono: se devuelve a la caja. Solo si
  // está VACÍA — si hay algo tipeado es tuyo y de ahora, y no se pisa.
  const c = $('#texto');
  if (activa && c && !c.value.trim() && (borradores[activa] || '').trim())
    ponerBorradorEnCaja(activa);
}

let borradorTimer = null, borradorPuesto = {};

function anotarBorrador(sid, texto){
  if (!sid || FIJAS.includes(sid)) return;      // el chat de Laura tiene lo suyo
  const antes = hayBorrador(sid);
  borradores[sid] = texto || '';
  guardarBorradores();
  if (antes !== hayBorrador(sid)){ elegirFirma = ''; pintarTabs(); }
  clearTimeout(borradorTimer);
  borradorTimer = setTimeout(() => empujarBorrador(sid), 700);
}

// ⚠ Las charlas sin estrenar no viajan: su id es provisorio y no significa nada afuera.
function empujarBorrador(sid){
  if (!sid || esNueva(sid) || FIJAS.includes(sid)) return;
  const texto = borradores[sid] || '';
  if (borradorPuesto[sid] === texto) return;
  borradorPuesto[sid] = texto;
  fetch('/movil/borrador', {method:'POST', headers:{'Content-Type':'application/json'},
                            body: JSON.stringify({sid, texto}), keepalive: true})
    .catch(() => { delete borradorPuesto[sid]; });
}

function soltarBorrador(){
  clearTimeout(borradorTimer);
  if (activa) empujarBorrador(activa);
}

// ⚠ El borrador ENTERO, nunca el anticipo de 120 letras de la lista: devolverlo cortado
// sería comerse la mitad de lo que escribiste sin avisar.
function ponerBorradorEnCaja(sid){
  const c = $('#texto');
  if (!c) return;
  c.value = borradores[sid] || '';
  ajustarCaja(c);
}

function ajustarCaja(c){
  if (!c) return;
  if (!c.value) { c.style.height = '44px'; return; }
  c.style.height = 'auto';
  c.style.height = Math.min(c.scrollHeight, 120) + 'px';
}

async function pintarElegir(){
  // Primero con lo que ya se sabe, y despues con lo que conteste el servidor. El
  // repintado se saltea solo si quedo igual (la `firma` de mas abajo).
  const mio = ++pintadoNro;
  if (listaSes && listaSes.proyectos && activa === 'nueva') dibujarElegir(listaSes);
  const fresco = await traerSesiones();
  if (mio !== pintadoNro || activa !== 'nueva') return;
  if (fresco) dibujarElegir(fresco);
}

function dibujarElegir(d){
  if (!d.proyectos.length){
    $('#cuerpo').innerHTML = '<div class="aviso">No encontré proyectos con conversaciones guardadas.</div>';
    return;
  }
  // "Todas" es una bandeja sola con lo de todos los proyectos, la ultima arriba;
  // si elegiste una carpeta, solo esa.
  const enTodas = proyElegido === TODAS;
  const p = d.proyectos.find(x => x.proyecto === proyElegido) || d.proyectos[0];
  const marcar = (x, s) => Object.assign({}, s, {_proy: x.proyecto, _cwd: x.cwd});
  // Los números no cuentan las archivadas: si no, arriba decía 68 y en la lista
  // había 67, y esa diferencia te hace desconfiar de todo lo demás.
  // ⭐ Tapada = se compactó o se mudó de cerebro y su continuación está en esta misma
  // lista (2026-08-21). No se dibuja en ningún lado: abrir la continuación ya te
  // muestra esta charla cosida arriba, así que la fila vieja era la MISMA conversación
  // repetida y muerta. Tampoco va a las archivadas: no la guardaste vos, siguió de
  // largo. El servidor solo la tapa cuando la nueva está a la vista.
  const enBandeja = s => !esArchivada(s) && !s.tapada;
  const total = d.proyectos.reduce((n, x) => n + x.sesiones.filter(enBandeja).length, 0);
  // ⭐ Las archivadas siguen la carpeta donde estás parado (pedido de Martín, 2026-08-17):
  // adentro de un proyecto son las de ese proyecto, y en "Todas" están todas juntas —
  // ese es el lugar fijo donde ir a buscar lo que sacaste sin acordarte de dónde salió.
  const guardadas = (enTodas ? d.proyectos : [p])
    .flatMap(x => x.sesiones.filter(s => !enBandeja(s) && !s.tapada).map(s => marcar(x, s)))
    .sort((a, b) => (b.ts || 0) - (a.ts || 0));
  let lista = enTodas
    ? d.proyectos.flatMap(x => x.sesiones.map(s => marcar(x, s)))
                 .sort((a, b) => (b.ts || 0) - (a.ts || 0))
    : p.sesiones.map(s => marcar(p, s));
  lista = viendoArchivadas ? guardadas : lista.filter(enBandeja);
  if (enTodas && filtroSes)
    lista = lista.filter(s => (s.nombre + ' ' + s._proy + ' ' + (s.detalle || ''))
                               .toLowerCase().includes(filtroSes));

  // ⚠ Solo se repinta si cambió algo: si no, se pierde el scroll y el cajón se
  // cierra solo cada 3 segundos.
  const firma = JSON.stringify([proyElegido, filtroSes, buscaCarp,
                                viendoArchivadas, guardadas.length,
                                // ⚠ El orden y las escondidas VAN en la firma: si no,
                                // mover o sacar una carpeta no repinta nada porque la
                                // lista de conversaciones quedo igualita.
                                ordenCarp.join('|'), [...ocultasCarp].join('|'), viendoOcultas,
                                JSON.stringify(aspectoCarp),
                                d.proyectos.map(x => [x.proyecto, x.sesiones.length]),
                                // ⚠ El borrador VA en la firma, como el estado: si no,
                                // escribir media frase y volver a la bandeja no prendia
                                // la chapa porque la lista se creia igual.
                                lista.map(s => s.id + s.nombre + s.viva + s.detalle
                                                    + estadoSes(s) + (s.sigue_en || '')
                                                    + borradorDe(s.id, s.borrador).slice(0, 60))]);
  if (firma === elegirFirma && $('#cuerpo').dataset.vista === 'lista') return;
  elegirFirma = firma;
  // ⭐ ¿Esta lista es la MISMA que se estaba mirando, o es una recién llegada? Si es
  // nueva (volviste de una charla, cambiaste de carpeta, entraste a las archivadas)
  // hay que arrancarla arriba de todo: ver el scroll al final de esta función.
  const otraLista = $('#cuerpo').dataset.vista !== 'lista'
                    || listaDibujada !== proyElegido + '|' + viendoArchivadas;
  listaDibujada = proyElegido + '|' + viendoArchivadas;
  $('#cuerpo').dataset.vista = 'lista';
  const foco = document.activeElement && document.activeElement.id;   // no robarle el teclado al que escribe

  // ⭐ Las carpetas, en el orden que vos les diste y sin las que sacaste. Buscando por
  // nombre aparecen TAMBIEN las escondidas: si escribis el nombre de una que sacaste y
  // no aparece, parece que se borro de verdad.
  const ordenadas = ordenarCarpetas(d.proyectos)
    .filter(x => !buscaCarp || x.proyecto.toLowerCase().includes(buscaCarp));
  const escondidas = ordenadas.filter(x => ocultasCarp.has(x.proyecto));
  const visiblesCarp = buscaCarp ? ordenadas
                                 : ordenadas.filter(x => !ocultasCarp.has(x.proyecto));
  const carpetas = visiblesCarp.map(x => `
    <div class="carpeta ${!enTodas && x.proyecto === p.proyecto ? 'sel' : ''} ${
                          x.proyecto === marcarVuelve ? 'vuelve' : ''}${
                          (aspectoCarp[x.proyecto] || {}).color ? ' personalizada' : ''}"
         data-proy="${esc(x.proyecto)}"${estiloCarpeta(x.proyecto)}>
      <span class="ic">${esc((aspectoCarp[x.proyecto] || {}).icono || (x.vivo ? '📂' : '📁'))}</span>
      <span class="nom">${esc(apodoCarp(x.proyecto))}</span>
      ${navegEfectivo(x.proyecto)
        ? '<span class="naveg-carp" title="Sus conversaciones manejan un navegador">🌐</span>' : ''}
      <span class="num">${x.sesiones.filter(enBandeja).length}</span>
      <button class="editar-carp" aria-label="Editar carpeta">✎</button>
    </div>`).join('')
    // El pie con las escondidas, solo si hay alguna: es el UNICO camino de vuelta, asi
    // que no puede depender de acordarse de un gesto.
    + ((escondidas.length && !buscaCarp)
        ? `<div class="carpeta guardadas" id="verOcultas">
             <span>${viendoOcultas ? '▾' : '▸'}</span>
             <span class="nom">Escondidas</span>
             <span class="num">${escondidas.length}</span>
           </div>` + (viendoOcultas ? escondidas.map(x => `
           <div class="carpeta devolver" data-volver="${esc(x.proyecto)}">
             <span class="nom">${esc(x.proyecto)}</span>
             <span class="vol">↩ devolver</span>
           </div>`).join('') : '')
        : '');
  marcarVuelve = '';

  const filas = lista.map(s => `
    <div class="correo ${estadoSes(s)}" data-sid="${s.id}"
         onclick="abrir('${s._cwd.replace(/\\\\/g,'\\\\\\\\')}','${s.id}','${esc(s.nombre).replace(/'/g,'')}')">
      <div class="ini ${s.viva ? 'viva' : ''}">${esc(inicial(s.nombre))}</div>
      <div class="med">
        <div class="tit">${esc(s.nombre)}${
              s.cerebro === 'codex' ? '<span class="cer">Codex</span>' : ''}${
              // La charla compactada dice a donde siguio: tocarla lleva a la nueva.
              s.sigue_en ? `<span class="sigue" onclick="event.stopPropagation();abrir('${
                  s._cwd.replace(/\\\\/g,'\\\\\\\\')}','${s.sigue_en}','${
                  esc(s.nombre).replace(/'/g,'')}')">⇲ sigue en otra</span>` : ''}${
              enTodas ? '<span class="eti">' + esc(s._proy) + '</span>' : ''}${
              hayBorrador(s.id, s.borrador)
                ? '<span class="borra"><span class="plu">✎</span>Borrador</span>' : ''}</div>
        <div class="baj">${esc(s.detalle || '')}${estadoSes(s)
              ? ' · <b>' + DICE[estadoSes(s)] + '</b>'
                + (estadoSes(s) === 'fallada' ? ' · ' + esc(falloQue(falladas[s.id])) : '')
              : ''}${hayBorrador(s.id, s.borrador)
                ? ' · <span class="bpre">' + esc(vistaBorrador(s.id, s.borrador)) + '</span>' : ''}</div>
      </div>
      ${viendoArchivadas
        ? `<div class="devolver" onclick="event.stopPropagation();archivarSesion('${s.id}',false)">↩ Devolver</div>`
        : `<div class="lapiz" onclick="event.stopPropagation();renombrarEnLista('${s.id}','${esc(s.nombre).replace(/'/g,'')}')">✎</div>`}
    </div>`).join('');

  const nueva = enTodas
    ? `<div class="correo nueva" onclick="abrirCajon(true)">
         <div class="ini mas">✚</div>
         <div class="med"><div class="tit">Empezar una conversación</div>
           <div class="baj">elegís la carpeta y arranca de cero</div></div>
       </div>`
    : `<div class="correo nueva" onclick="abrir('${p.cwd.replace(/\\\\/g,'\\\\\\\\')}','','Nueva')">
         <div class="ini mas">✚</div>
         <div class="med"><div class="tit">Empezar una conversación</div>
           <div class="baj">arranca de cero en este proyecto</div></div>
       </div>`;

  $('#cuerpo').innerHTML = `
    <div class="barra-proy">
      <div class="menu" onclick="abrirCajon(true)">☰</div>
      <div class="quien"><b>${esc(viendoArchivadas ? 'Archivadas' : enTodas ? TODAS : p.proyecto)}</b>
        <small>${viendoArchivadas
                  ? lista.length + ' guardadas' + (enTodas ? '' : ' en ' + esc(p.proyecto))
                    + ' · tocá Devolver'
                  : (enTodas ? total : p.sesiones.filter(enBandeja).length) + ' conversaciones'}</small></div>
      ${(guardadas.length || viendoArchivadas)
        ? `<div class="op-arch" onclick="verArchivadas(${!viendoArchivadas})">${
             viendoArchivadas ? '← bandeja' : '🗄 ' + guardadas.length}</div>`
        : ''}
    </div>
    ${enTodas && !viendoArchivadas ? `<input class="filtro-ses" id="filtroSes" placeholder="Filtrar…"
        value="${esc(filtroSes)}" oninput="filtrarSes(this.value)">` : ''}
    ${viendoArchivadas ? '' : nueva}
    ${filas || `<div class="info">${viendoArchivadas
        ? 'No hay ninguna archivada. Deslizá una conversación hacia la izquierda para guardarla acá.'
        : 'No hay conversaciones acá.'}</div>`}
    <div id="cajon" class="${cajonAbierto ? 'abierto' : ''}"
         onclick="if(event.target===this)abrirCajon(false)">
      <div class="hoja-proy">
        <div class="rubro" style="margin:6px 0 10px 14px">Proyectos</div>
        <input class="buscacarp" id="buscaCarp" placeholder="Buscar carpeta…"
               value="${esc(buscaCarp)}" oninput="buscarCarp(this.value)">
        <div class="carpeta todas ${enTodas ? 'sel' : ''}" onclick="elegirProyecto('${TODAS}')">
          <span class="ic">✉</span><span class="nom">Todas</span><span class="num">${total}</span>
        </div>
        ${carpetas}
        <div class="pista-carp">Tocá ✎ para cambiar color o ícono · deslizá hacia la
             izquierda para sacarla · mantenela apretada para moverla</div>
        <div class="sumar-carp" onclick="sumarCarpeta()">＋ Agregar una carpeta</div>
      </div>
    </div>
    <div id="editorCarp" onclick="if(event.target===this)cerrarEditorCarp()">
      <div class="hoja-edit">
        <div class="edit-cab"><b class="edit-nombre"></b>
          <button class="cerrar-edit" onclick="cerrarEditorCarp()">×</button></div>
        <div class="edit-rot">Color</div><div class="colores"></div>
        <div class="edit-rot">Ícono</div><div class="icos-edit"></div>
        <div class="edit-rot">Navegador del proyecto</div>
        <select class="naveg-edit"><option>cargando…</option></select>
        <input class="naveg-sitios" placeholder="sitios permitidos (vacío = todos)">
        <div class="naveg-aviso"></div>
      </div>
    </div>`;
  if (foco === 'filtroSes' || foco === 'buscaCarp'){
    const c = $('#' + foco);
    if (c){ c.focus(); c.setSelectionRange(c.value.length, c.value.length); }
  }
  // Mirando las archivadas NO se engancha el deslizar: ahí deslizar volvería a archivar
  // lo que ya está archivado. Para sacarlas de ahí está el botón Devolver.
  if (!viendoArchivadas) engancharDeslizar();
  // Las carpetas del cajón sí, siempre: el cajón se repinta con todo lo demás y sin esto
  // los gestos quedan enganchados a renglones que ya no existen.
  engancharCarpetas();
  // ⭐⭐ La bandeja SIEMPRE empieza arriba, que es donde están las últimas conversaciones
  // (pedido de Martín, 2026-08-24: "cuando salgo del chat me mueve a cualquier parte de
  // la lista, yo siempre quiero ver las últimas"). El scroll es del CONTENEDOR `#cuerpo`,
  // que es el mismo para todas las vistas: adentro de una charla queda abajo de todo, y
  // al cambiarle el contenido por la lista el navegador se lo deja puesto — así caías a
  // media lista, en una conversación de hace tres días, sin ningún motivo visible.
  // ⚠ Solo cuando la lista es OTRA (volviste de una charla, cambiaste de carpeta o
  // entraste a las archivadas). En un repintado de los de cada 3 s no se toca nunca:
  // ahí estás leyendo, y saltar al principio solo mientras mirás sería peor que el bug.
  if (otraLista) $('#cuerpo').scrollTop = 0;
}

function nuevaEn(cwd){ abrir(cwd, '', 'Charla nueva'); }

// Ponerle nombre propio a una sesión. El título que le puso Claude no se toca: esto
// es un alias nuestro, guardado en el servidor, así que lo ves igual desde donde
// entres. Con el nombre vacío vuelve al de Claude.
// El mismo lápiz, pero desde la lista del más (ahí la sesión no es una pestaña
// todavía). stopPropagation en el onclick: si no, tocar el lápiz ABRE la sesión.
// ⚠ Se guarda ABIERTO y CERRADO, no solo los abiertos: hay que poder distinguir
// "nunca lo tocaste" (ahí manda el default) de "lo cerraste vos". Con una lista de
// abiertos, el proyecto que está en uso se reabría solo en cada repintado y no
// había forma de cerrarlo (2026-08-16).
const proyEstado = () => JSON.parse(localStorage.getItem('proyectosAbiertos') || '{}');

function recordarAbierto(proyecto, abierto){
  const e = proyEstado();
  e[proyecto] = abierto;
  localStorage.setItem('proyectosAbiertos', JSON.stringify(e));
}

async function renombrarEnLista(sid, actual){
  const nombre = prompt('¿Cómo querés que se llame esta sesión?', actual);
  if (nombre === null) return;
  await fetch('/movil/nombre', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, nombre: nombre.trim()})}).catch(()=>{});
  const p = pestanas.find(x => x.sid === sid);
  if (p && nombre.trim()) p.nombre = nombre.trim().slice(0,14);
  guardar(); pintarTabs(); pintarElegir();
}

async function renombrar(sid){
  const p = pestanas.find(x => x.sid === sid);
  const nombre = prompt('¿Cómo querés que se llame esta sesión?', p ? p.nombre : '');
  if (nombre === null) return;
  const corto = nombre.trim();
  if (p) p.nombre = corto.length > 15 ? corto.slice(0,14) + '…' : (corto || 'Sesión');
  fijarDireccion({empujar: false});       // el titulo de la pestaña del navegador tambien
  guardar(); pintarTabs(); pintar();
  if (esNueva(sid)) return;              // todavía no existe del lado de Claude
  await fetch('/movil/nombre', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, nombre: corto})}).catch(()=>{});
  try { sesiones = (await (await fetch('/movil/sesiones')).json()).proyectos.flatMap(p=>p.sesiones); }
  catch(e){}
}

const esNueva = sid => (sid || '').startsWith('nueva-');

function abrir(cwd, sid, nombre){
  // Sin sid es una sesión NUEVA: se le pone un id provisorio hasta que el primer
  // mensaje vuelva con el de verdad (mandar() lo reemplaza en la pestaña).
  if (!sid) sid = 'nueva-' + Date.now();
  if (!pestanas.some(p => p.sid === sid))
    pestanas.unshift({sid, cwd, nombre: nombre.length>15 ? nombre.slice(0,14)+'…' : nombre,
                      virgen: sid.startsWith('nueva-')});
  const p = pestanas.find(x => x.sid === sid);
  precargar(p);
  ir(sid);
}

// ⭐ Navegar tiene que sentirse INSTANTANEO. Dos cosas lo arruinaban:
//  1) al tocar una pestaña no se dibujaba nada hasta que el servidor contestaba,
//     asi que quedaba la pestaña anterior en pantalla y parecia que no habia
//     pasado nada; ahora se dibuja YA con lo ultimo que se leyo de esa sesion
//     (cache) y despues se refresca;
//  2) los pintados se pisaban entre si: como cada uno espera su fetch, el de la
//     pestaña VIEJA podia terminar despues del de la nueva y sobreescribirla —
//     de ahi el "no siempre me lleva a donde quiero". Cada pintado lleva numero y
//     el que llega tarde se descarta (2026-08-16).
const cacheChat = {};        // sid -> mensajes ya leidos
const cachePreg = {};        // sid -> la pregunta con opciones que esa sesion tiene abierta
const cacheTareas = {};      // sid -> la lista de tareas (TodoWrite) que mostro por ultima vez
const cacheOcupada = {};     // sid -> si tiene un turno corriendo AHORA (lo dice el servidor)
let arranque = {};           // desde cuando piensa cada sesion, para el relojito
// El contador se escribe SOLO en ese pedacito: metido en el repintado cambiaria la
// firma cada segundo y el hilo entero parpadearia.
setInterval(() => {
  const r = document.getElementById('reloj'), t0 = arranque[activa];
  if (!r || !t0) return;
  const seg = Math.round((Date.now() - t0) / 1000);
  r.textContent = seg < 60 ? seg + ' s'
                           : Math.floor(seg / 60) + ' min ' + (seg % 60) + ' s';
}, 1000);
let pintadoNro = 0, firmaChat = {};

// De qué proyecto es una pestaña: la última parte de la carpeta del disco
// ("D:\\IA\\wpp-transcriptor" -> "wpp-transcriptor"), que es como se lo nombra hablando.
function proyectoDe(p){
  return ((p && p.cwd) || '').replace(/[\\\/]+$/, '').split(/[\\\/]/).pop();
}

function dibujarSesion(p, mensajes){
  const viva = sesiones.some(s => s.id === p.sid && s.viva && s.interactiva);
  const ev = enVuelo[p.sid];        // lo que estás mandando EN ESTA pestaña
  // ⭐ La burbuja de "pensando" no puede depender SOLO de que el turno lo hayas
  // mandado desde este teléfono: si recargás la app, o la charla la arrancaste en la
  // compu, se perdía y la sesión parecía muerta estando a full (2026-08-17).
  const ses = sesiones.find(x => x.id === p.sid);
  const pensa = !!(ev || (ses && estadoSes(ses) === 'trabajando'));
  // La estás mirando: no puede quedar marcada como que te espera.
  if (ses && ses.ts) visto[p.sid] = ses.ts;
  // ¿Tu mensaje ya entró al hilo de verdad? Se CUENTA, no se ubica: llegó cuando tu
  // texto está una vez más de las que estaba al mandarlo. Ver el comentario largo de
  // `vecesVuelo` abajo — ubicarlo por posición está mal y se arregló el 2026-08-22.
  const yaLlego = ev && cuentaTuya(mensajes, ev.texto) > (vecesVuelo[p.sid] ?? 0);
  // La pregunta con opciones que trajo el último /movil/chat. Cuando llega una NUEVA
  // (otra hora) se olvida lo marcado de la anterior, y `pregRespondida` la esconde
  // apenas contestás, sin esperar a que el servidor la saque de la lista.
  const preg = cachePreg[p.sid] || null;
  if (preg && preg.hora !== pregHora){ pregHora = preg.hora; pregElecciones = {}; }
  pregActual = preg;
  const pregVisible = preg && preg.hora !== pregRespondida;
  // ⭐ La lista de tareas de la sesión (TodoWrite): viene adentro de /movil/chat y
  // se dibuja al final del hilo, tildándose en vivo mientras trabaja (2026-08-20).
  const tar = cacheTareas[p.sid] || null;
  const preguntaComp = silencioComp[p.sid] > Date.now() ? '' : (pideCompactar[p.sid] || '');
  // En las que están abiertas en la compu no se escribe: solo se mira.
  $('#escribir').style.display = viva ? 'none' : 'flex';
  // ⭐ Y mientras la sesión está contestando, la caja se bloquea Y LO DICE — igual que en
  // la compu (2026-08-23, Martín desde el celular: escribió mientras Codex trabajaba, le
  // saltó "esa sesión está contestando algo" y el texto ya se había borrado).
  const ocupadaAhora = !!cacheOcupada[p.sid] || !!ev || !!preguntaComp;
  $('#texto').disabled = ocupadaAhora;
  $('#mandar').disabled = ocupadaAhora;
  $('#texto').placeholder = preguntaComp ? 'Elegí si querés compactar antes de seguir'
    : ocupadaAhora ? 'Está contestando: esperá a que termine' : 'Escribí…';
  const html =
    // ⭐ El PROYECTO al lado del nombre: adentro de una charla no había forma de saber
    // de qué carpeta era (en la compu se ve marcada a la izquierda, acá no hay nada) y
    // uno le termina escribiendo a la sesión equivocada — pedido de Martín, 2026-08-17.
    // Sale de la ruta que guarda la pestaña, así que siempre está, incluso si el
    // proyecto no figura en la lista de arriba.
    // ⭐ Título y perillas van JUNTOS en una cabecera pegada arriba (2026-08-20): las
    // perillas sueltas se iban con el scroll y parecía que el celular no las tenía.
    // La cruz de cerrar es neutra: cerrar no es un error, el rojo acá sobraba.
    `<div id="cabecera"><h1 id="titulo"><span class="volver" onclick="ir('nueva')">←</span>
       <span class="nom">${esc(p.nombre)}</span>
       ${proyectoDe(p) ? `<span class="eti">${esc(proyectoDe(p))}</span>` : ''}
       <span class="lapiz" onclick="renombrar('${p.sid}')">✎</span>
       <span class="cierra" onclick="cerrar('${p.sid}')">✕</span></h1>` +
    // ⭐ Con qué modelo corre esta charla y el botón de compactarla (pedido de Martín,
    // 2026-08-18). Van ACÁ y no en la caja de escribir: abajo hay 390 px de ancho para
    // el clip, el texto y Enviar, y un selector más ahí deja la caja de texto en nada.
    // La lista la trae verModelo() del servidor, así que lo que elegís en la compu se
    // ve igual acá — es el mismo dato, no dos ajustes distintos.
    dibujarAjustes(p) + `</div>` +
    // ⭐ En una sesión que está abierta en la compu se puede LEER pero no escribir:
    // un turno desde acá corre en paralelo al de allá y la conversación se parte al
    // medio. En vez de dejarte hacerlo y avisarte, se ofrece lo que sí sirve, que es
    // arrancar una charla nueva en ese mismo proyecto.
    (viva ? `<div class="aviso">Esta sesión está abierta en la compu, así que acá solo
             se puede mirar: escribirle desde el teléfono la partiría en dos.
             <button class="azul" style="margin-top:10px"
               onclick="nuevaEn('${p.cwd.replace(/\\\\/g,'\\\\\\\\')}')">Empezar una charla
               nueva en este proyecto</button></div>` : '') +
    // ⭐ `data-msg` es el ancla de las marcas de texto: lo que Martín pinta en la compu
    // se ve también acá (las marcas viven en el servidor). Ver `/estaticos/marcas.js`.
    (mensajes.length ? mensajes.map((m, iM) =>
      // ⭐ La costura de una compactada (2026-08-20): la charla anterior viene cosida
      // arriba y esta rayita es lo único que se ve del corte.
      m.de==='marca'
      ? `<div class="marcaHilo" data-msg="${iM}">${esc(m.texto)}</div>`
      // ⭐ El rastro de lo que va haciendo, un renglon por herramienta. El pensamiento
      // NO se puede mostrar: Claude Code lo tapa en el archivo y en el chorro en vivo.
      // ⚠ Los pasos seguidos van en UN bloque con fondo: sueltos sobre el fondo de la
      // pantalla no se leen. La apertura y el cierre miran al vecino de arriba y de abajo.
      : m.de==='paso'
      ? ((mensajes[iM-1]||{}).de==='paso' ? '' : '<div class="pasos">') +
        `<div class="paso" data-msg="${iM}">${esc(m.texto)}</div>` +
        ((mensajes[iM+1]||{}).de==='paso' ? '' : '</div>')
      : `<div class="msg ${m.de==='vos'?'vos':'claude'}" data-msg="${iM}">` +
      (m.imgs || []).map(u => `<img class="foto" src="${u}" onclick="verFoto('${u}')">`).join('') +
      // Lo tuyo va tal cual lo escribiste; lo de Claude, dibujado. La horita abajo
      // a la derecha, como en WhatsApp (viene del archivo de la sesión).
      `${m.de==='vos' ? esc(m.texto) : marcar(m.texto)}` +
      `${m.h?`<span class="hora">${m.h}</span>`:''}</div>`).join('')
      : '<div class="info">Sin mensajes todavía.</div>') +
    // Tu mensaje se dibuja APENAS tocás Enviar, sin esperar a que el turno termine:
    // el hilo se arma leyendo el archivo donde Claude escribe, y ahí tu mensaje
    // aparece recién cuando lo procesa. Sin esto parecía que no se había mandado.
    // ⚠ Solo mientras NO haya llegado al hilo. Apenas Claude lo procesa, tu mensaje
    // aparece leído del archivo, y si además se seguía dibujando el provisorio se
    // veía DOS VECES (2026-08-16).
    (ev && !yaLlego ? `<div class="msg vos">` +
       (ev.urls||[]).map(u => `<img class="foto" src="${u}">`).join('') +
       `${esc(ev.texto)}<span class="hora">${(new Date).toTimeString().slice(0,5)}</span></div>` : '') +
    (tar ? htmlTareas(tar) : '') +
    // ⭐ Si la sesión frenó a preguntarte algo con opciones, en lugar de "pensando"
    // van los BOTONES para tocar (lo está: te está esperando a vos). Mismo selector
    // que en la compu, pero con el dedo — pedido de Martín, 2026-08-18.
    (pregVisible ? htmlPregunta(preg)
     : pensa ? '<div class="msg claude pensando">pensando<span></span><span></span><span></span>'
             + '<b class="reloj" id="reloj"></b></div>'
     // ⭐ La pregunta de compactar, adentro del hilo y no como cartel del navegador.
     : (preguntaComp && !ev ?
        `<div class="pideComp">${esc(preguntaComp)}
         <div class="botones"><button onclick="compactarSes('${p.sid}', true)">⇲ Sí, compactar</button>
         <button class="despues" onclick="noCompactar('${p.sid}')">Ahora no</button></div></div>` : ''));
  // ⚠ 'block', NO '': el CSS de `#parar` ya lo tiene en `display:none` (así arranca
  // escondido), así que borrar el estilo de línea con '' lo devolvía a esa regla y el
  // botón NO APARECÍA NUNCA en el teléfono, ni con la charla pensando (Martín,
  // 2026-08-26). En la compu no pasa porque allá el `display:none` está en el propio
  // tag. La caja es flex: un `block` acá se comporta igual que Enviar.
  $('#parar').style.display = pensa ? 'block' : 'none';
  if (!ev) arranque[p.sid] = (ses && ses.ts ? ses.ts * 1000 : Date.now());
  // Si no cambió nada, no se toca el DOM: repintar igual te tira el scroll.
  const caja1 = $('#cuerpo');
  if (firmaChat[p.sid] === html && caja1.dataset.vista === 'ses:'+p.sid && !recienAbierta) return;
  firmaChat[p.sid] = html;
  caja1.dataset.vista = 'ses:'+p.sid;
  const caja = $('#cuerpo');
  const abajo = recienAbierta || (caja.scrollHeight - caja.scrollTop - caja.clientHeight < 80);
  // Lo que ya marcaste o tipeaste en el selector de opciones no se puede perder en el
  // repintado: se captura antes de rearmar el hilo y se devuelve después.
  const pregEstado = guardarPregunta(caja);
  caja.innerHTML = html;
  restaurarPregunta(caja, pregEstado);
  // ⭐ Lo que Martín pintó o subrayó en la compu se dibuja también acá: las marcas viven
  // en el servidor y se vuelven a aplicar después de cada repintado (`marcas.js`). Desde
  // el teléfono todavía no se pinta — no hay clic derecho y iOS tapa la selección con su
  // propio menú; eso es una vuelta aparte.
  if (window.Marcas) Marcas.pintar(caja, p.sid);
  if (abajo){
    caja.scrollTop = caja.scrollHeight;
    // ⚠ Las fotos todavía no cargaron: ocupan alto cero y al llegar empujan la charla
    // hacia abajo, así que "el final" quedaba a mitad de camino en cuanto la
    // conversación tenía capturas — que acá son casi todas (2026-08-17). Se vuelve a
    // bajar cuando cada una termina de cargar.
    caja.querySelectorAll('img.foto').forEach(i => {
      if (!i.complete)
        i.addEventListener('load', () => { caja.scrollTop = caja.scrollHeight; }, {once:true});
    });
  }
  recienAbierta = false;
}

// Traer la conversación de una pestaña SIN dibujarla, para que cuando la toques ya
// esté. Se hace al arrancar y al abrir una pestaña nueva: así el primer toque de
// cada sesión tampoco espera al servidor.
let cargasChat = {};

function guardarChat(p, d){
  cacheChat[p.sid] = d.mensajes;
  // ⭐ Si esa charla tiene un turno corriendo, el servidor no acepta otro: lo dice acá
  // (2026-08-23). Con esto la caja se bloquea sola, como en la compu, en vez de dejarte
  // escribir para después rebotarte con un cartel y perder lo que habías escrito.
  cacheOcupada[p.sid] = !!d.ocupada;
  // ⭐ El 🔔 lo enciende el SERVIDOR (`avisando` sale de la ficha del trabajo), no la
  // memoria de este navegador: así sobrevive a un F5 y se ve prendido también en la
  // compu si lo pediste desde el teléfono (2026-08-29).
  cacheAvisando[p.sid] = !!d.avisando;
  if (p.sid === activa) pintarAviso();
  // La decisión de compactar viene del servidor en CADA lectura: no se pierde si
  // recargás, cambiás de navegador o el turno terminó en otra pantalla.
  if (!(silencioComp[p.sid] > Date.now())){
    if (d.pide_compactar) pideCompactar[p.sid] = d.pide_compactar;
    else delete pideCompactar[p.sid];
  }
  cachePreg[p.sid] = (d.pregunta && ((d.pregunta.preguntas || []).length || d.pregunta.plan)) ? d.pregunta : null;
  cacheTareas[p.sid] = (d.tareas && (d.tareas.lista || []).length) ? d.tareas : null;
}

function pedirChat(p){
  if (esNueva(p.sid)) return Promise.resolve({mensajes: []});
  // Abrir una charla lanza el dibujo y la precarga a la vez. Comparten ESTE pedido:
  // antes ambas releian el mismo rollout pesado desde el disco al mismo tiempo.
  if (!cargasChat[p.sid]){
    const url = `/movil/chat?cwd=${encodeURIComponent(p.cwd)}&sid=${p.sid}`;
    cargasChat[p.sid] = fetch(url).then(r => r.json()).finally(() => delete cargasChat[p.sid]);
  }
  return cargasChat[p.sid];
}

function precargarPanel(){
  if (panelUltimoHtml || panelPrecargando) return;
  panelPrecargando = pintarPanel(true).catch(() => {}).finally(() => { panelPrecargando = null; });
}

async function precargar(p){
  if (!p || esNueva(p.sid) || cacheChat[p.sid]) return;
  try {
    guardarChat(p, await pedirChat(p));
  } catch(e){}
}

// --- ⭐ La pregunta con opciones (AskUserQuestion), desde el teléfono ------------
// La misma que ya andaba en la compu, ahora con el dedo (pedido de Martín, 2026-08-18:
// el backend ya la mandaba por /movil/chat y acá no se dibujaba nada). Cuando la sesión
// pregunta algo con opciones, botones de verdad para tocar más un campo para contestar
// con tus palabras; la elección vuelve por `POST /movil/responder` y el proceso `claude`
// sigue esperando mientras tanto.
let pregActual = null;       // la pregunta que trajo el último /movil/chat
let pregHora = 0;            // para olvidar lo marcado cuando llega una pregunta NUEVA
let pregRespondida = 0;      // la hora de la que ya contestaste: se esconde al toque
let pregElecciones = {};     // iQ -> [índices marcados] (con selección múltiple junta varios)

// ⭐ La lista de tareas de la sesión (TodoWrite, 2026-08-20): el agente se la anota
// solo y la va tildando; acá se dibuja como tarjetita que se actualiza en vivo con
// cada repintado. La fila en curso muestra lo que está haciendo AHORA (el gerundio
// que manda el CLI), las hechas quedan tildadas y apagadas.
function htmlTareas(ts){
  const hechas = ts.lista.filter(t => t.estado === 'completed').length;
  return '<div class="tareas"><div class="tTit">Tareas <span>' + hechas + ' de ' +
    ts.lista.length + '</span></div>' +
    ts.lista.map(t => {
      const e = t.estado === 'completed' ? 'hecha'
              : t.estado === 'in_progress' ? 'haciendo' : '';
      const ico = e === 'hecha' ? '✓' : e === 'haciendo' ? '▸' : '○';
      return '<div class="tFila ' + e + '"><span class="tIco">' + ico + '</span>' +
        esc(e === 'haciendo' && t.activo ? t.activo : t.texto) + '</div>';
    }).join('') + '</div>';
}

function htmlPregunta(p){
  // ⭐ El plan de una sesión en plan mode viaja por el mismo canal que la pregunta
  // con opciones (2026-08-20): misma tarjeta, otra decisión (aprobar o seguir).
  if (p.plan) return htmlPlan(p);
  const qs = p.preguntas;
  // Con varias preguntas, o con selección múltiple, hace falta un botón Responder;
  // con UNA pregunta simple, tocar la opción ya es la respuesta (un solo gesto, que
  // con el dedo importa más que en la compu).
  const junto = qs.length > 1 || qs.some(q => q.multi);
  let h = '<div class="pregunta">';
  qs.forEach((q, iQ) => {
    h += '<div class="pBloque">' +
      (q.titulo ? '<div class="pTit">' + esc(q.titulo) + '</div>' : '') +
      '<div class="pPreg">' + esc(q.pregunta) + '</div>' +
      '<div class="pOps">' + q.opciones.map((o, iO) =>
        '<button class="pOp" data-q="' + iQ + '" data-o="' + iO + '"><b>' + esc(o.etiqueta) +
        '</b>' + (o.detalle ? '<span>' + esc(o.detalle) + '</span>' : '') + '</button>'
      ).join('') + '</div>' +
      '<div class="pOtra"><input placeholder="Otra respuesta…" data-q="' + iQ + '">' +
      (junto ? '' : '<button class="pManda" data-q="' + iQ + '">Mandar</button>') +
      '</div></div>';
  });
  if (junto) h += '<button class="pMandar">Responder</button>';
  h += '<div class="pNota">La sesión está esperando esta respuesta para seguir.</div></div>';
  return h;
}

// ⭐ El plan propuesto (plan mode, 2026-08-20): la sesión trabajó solo lectura, armó
// esto y frena a esperarte. Aprobar lo ejecuta ahí mismo (y la saca de plan mode);
// "Seguir planeando" la deja planeando, con lo que escribas como pedido de cambios.
// ⭐ En Codex el plan ES la última respuesta de la charla, que ya se lee justo arriba:
// repetirlo entero adentro de la tarjeta sería media pantalla del teléfono leyendo lo
// mismo dos veces. Por eso ahí la tarjeta muestra solo la decisión (2026-08-25).
function htmlPlan(p){
  return '<div class="pregunta plan"><div class="pTit">Plan propuesto</div>' +
    '<div class="pPlan">' + (p.codex ? 'Codex te dejó el plan en la respuesta de acá arriba.'
                                     : marcar(p.plan)) + '</div>' +
    '<div class="pOps">' +
    '<button class="pOp pAprueba"><b>Aprobar y ejecutar</b>' +
    '<span>Sale de plan mode y se pone a hacerlo</span></button>' +
    '<button class="pOp pSigue"><b>Seguir planeando</b>' +
    '<span>No toca nada; podés pedirle cambios abajo</span></button></div>' +
    '<div class="pOtra"><input placeholder="Cambios que le pedís al plan…" data-q="plan"></div>' +
    '<div class="pNota">La sesión está esperando tu decisión para seguir.</div></div>';
}

async function responderPlan(aprobar, comentario){
  const p = pestanas.find(x => x.sid === activa);
  if (!p || !pregActual || !pregActual.plan) return;
  // Igual que la pregunta: se esconde al toque y vuelve "pensando".
  pregRespondida = pregActual.hora;
  cachePreg[p.sid] = null;
  firmaChat[p.sid] = '';
  let r = null;
  try {
    r = await (await fetch('/movil/plan', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cwd: p.cwd, sid: esNueva(p.sid) ? '' : p.sid,
                            aprobar: !!aprobar, comentario: comentario || ''})})).json();
  } catch(e){}
  // Aprobado, la sesión ya salió de plan mode: el selector tiene que decirlo.
  if (aprobar) modoSes[p.sid] = '';
  // ⭐ Codex: el turno que dejó el plan ya terminó, así que no hay a quién contestarle
  // y la decisión viaja como el mensaje siguiente. Lo manda `mandar()` para no
  // duplicar nada de lo que ese camino ya resuelve (ocupada, Parar, hilo en vivo).
  if (r && r.ok && r.mandar){ pintarSesion(); mandar(r.mandar); return; }
  pintarSesion();
}

// El hilo se rearma entero en cada repintado: lo marcado y lo tipeado viven acá afuera
// y se vuelven a poner después, igual que en la compu.
function guardarPregunta(c){
  const est = {textos: {}, foco: null};
  c.querySelectorAll('.pregunta .pOtra input').forEach(i => {
    if (i.value) est.textos[i.dataset.q] = i.value;
    if (document.activeElement === i) est.foco = i.dataset.q;
  });
  return est;
}

function restaurarPregunta(c, est){
  c.querySelectorAll('.pregunta .pOp').forEach(b => {
    if ((pregElecciones[b.dataset.q] || []).includes(+b.dataset.o)) b.classList.add('puesta');
  });
  if (!est) return;
  c.querySelectorAll('.pregunta .pOtra input').forEach(i => {
    if (est.textos[i.dataset.q]) i.value = est.textos[i.dataset.q];
    if (est.foco === i.dataset.q){
      i.focus();
      i.setSelectionRange(i.value.length, i.value.length);
    }
  });
}

// Junta lo elegido de todas las preguntas: lo tipeado a mano le gana a los botones
// (si escribiste algo es porque ninguna opción te servía). Devuelve null si falta
// contestar alguna, y avisa cuál en la notita del pie.
function juntarRespuestas(card){
  const rs = {};
  for (let iQ = 0; iQ < pregActual.preguntas.length; iQ++){
    const q = pregActual.preguntas[iQ];
    const inp = card.querySelector('.pOtra input[data-q="' + iQ + '"]');
    const tipeado = inp && inp.value.trim();
    const marcadas = (pregElecciones[iQ] || []).map(iO => q.opciones[iO].etiqueta);
    if (tipeado) rs[q.pregunta] = tipeado;
    else if (marcadas.length) rs[q.pregunta] = marcadas.join(', ');
    else {
      const nota = card.querySelector('.pNota');
      if (nota) nota.textContent = 'Falta contestar: ' + (q.titulo || q.pregunta);
      return null;
    }
  }
  return rs;
}

async function responderPregunta(rs){
  const p = pestanas.find(x => x.sid === activa);
  if (!p || !pregActual) return;
  // Se esconde al toque y vuelve la burbuja de "pensando": la respuesta ya salió y
  // dejar los botones a la vista invita a tocar dos veces.
  pregRespondida = pregActual.hora;
  pregElecciones = {};
  cachePreg[p.sid] = null;
  firmaChat[p.sid] = '';
  try {
    await fetch('/movil/responder', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      // Una pestaña sin estrenar manda sid vacío: el servidor guarda ese turno (y su
      // pregunta) bajo la carpeta, igual que /movil/mandar y /movil/parar.
      body: JSON.stringify({cwd: p.cwd, sid: esNueva(p.sid) ? '' : p.sid, respuestas: rs})});
  } catch(e){}
  pintarSesion();
}

// Un solo escucha delegado para todo el selector: el hilo se rearma en cada repintado,
// así que enganchar botón por botón obligaría a re-engancharlos cada vez.
document.getElementById('cuerpo').addEventListener('click', e => {
  if (!pregActual) return;
  const card = e.target.closest && e.target.closest('.pregunta');
  if (!card) return;
  // La tarjeta del plan tiene sus dos botones propios y ninguna opción numerada.
  if (pregActual.plan){
    if (e.target.closest('.pAprueba')) responderPlan(true);
    else if (e.target.closest('.pSigue')){
      const inp = card.querySelector('.pOtra input');
      responderPlan(false, inp && inp.value.trim());
    }
    return;
  }
  const op = e.target.closest('.pOp');
  if (op){
    const iQ = +op.dataset.q, iO = +op.dataset.o;
    const q = pregActual.preguntas[iQ];
    if (q.multi){
      const el = pregElecciones[iQ] || (pregElecciones[iQ] = []);
      const ya = el.indexOf(iO);
      if (ya >= 0) el.splice(ya, 1); else el.push(iO);
      op.classList.toggle('puesta');
    } else if (pregActual.preguntas.length === 1){
      responderPregunta({[q.pregunta]: q.opciones[iO].etiqueta});
    } else {
      pregElecciones[iQ] = [iO];
      card.querySelectorAll('.pOp[data-q="' + iQ + '"]').forEach(b =>
        b.classList.toggle('puesta', b === op));
    }
    return;
  }
  const manda = e.target.closest('.pManda');     // "Mandar" del texto libre (una pregunta)
  if (manda){
    const inp = card.querySelector('.pOtra input[data-q="' + manda.dataset.q + '"]');
    const texto = inp && inp.value.trim();
    if (texto) responderPregunta({[pregActual.preguntas[+manda.dataset.q].pregunta]: texto});
    return;
  }
  if (e.target.closest('.pMandar')){             // "Responder" de las preguntas juntas
    const rs = juntarRespuestas(card);
    if (rs) responderPregunta(rs);
  }
});

// Enter adentro de "Otra respuesta…" manda, como en la caja de abajo.
document.getElementById('cuerpo').addEventListener('keydown', e => {
  if (e.key !== 'Enter' || !pregActual) return;
  const inp = e.target.closest && e.target.closest('.pregunta .pOtra input');
  if (!inp) return;
  e.preventDefault();
  // En la tarjeta del plan, Enter con texto es "seguí planeando con estos cambios".
  if (pregActual.plan){
    const texto = inp.value.trim();
    if (texto) responderPlan(false, texto);
    return;
  }
  const card = inp.closest('.pregunta');
  if (pregActual.preguntas.length === 1){
    const texto = inp.value.trim();
    if (texto) responderPregunta({[pregActual.preguntas[0].pregunta]: texto});
  } else {
    const rs = juntarRespuestas(card);
    if (rs) responderPregunta(rs);
  }
});

// --- El modelo de esta charla y compactarla, desde el teléfono ----------------
// Lo mismo que en la compu y con los MISMOS endpoints: el modelo vive en el servidor
// (lo usa quien lanza el proceso `claude`), así que las dos pantallas muestran uno solo.
let modelosMovil = [], modeloSes = {}, ctxSes = {}, pidiendoModelo = {};
let esfuerzosMovil = [], esfuerzosCodexMovil = [], esfuerzoSes = {};
let velocidadesCodexMovil = [], velocidadSes = {};
// ⭐ Plan mode (2026-08-20): en "plan" la sesión primero muestra el plan y no toca
// nada hasta que lo apruebes. La perilla vive en el servidor, como el modelo.
let modosMovil = [], modoSes = {};
let cerebroSes = {};      // 'codex' si la charla es del otro cerebro; '' si es de Claude

async function verModelo(sid){
  if (pidiendoModelo[sid]) return;
  pidiendoModelo[sid] = true;
  try {
    const p = pestanas.find(x => x.sid === sid) || {};
    const nueva = esNueva(sid);
    const r = await (await fetch('/movil/modelo?sid=' + encodeURIComponent(nueva ? '' : sid) +
                                 '&cwd=' + encodeURIComponent(p.cwd || '') +
                                 '&cerebro=' + encodeURIComponent(nueva ? (p.cerebro || '') : '') +
                                 '&modelo=' + encodeURIComponent(p.modelo || ''))).json();
    if (!r.ok) return;
    cerebroSes[sid] = r.cerebro || '';
    // Los dos CLI tienen catálogos de esfuerzo distintos: no se pisan entre sí.
    if ((r.modelos || []).length) modelosMovil = r.modelos;
    if ((r.esfuerzos || []).length){
      if (r.cerebro === 'codex') esfuerzosCodexMovil = r.esfuerzos;
      else esfuerzosMovil = r.esfuerzos;
    }
    if ((r.modos || []).length) modosMovil = r.modos;
    if ((r.velocidades || []).length) velocidadesCodexMovil = r.velocidades;
    modeloSes[sid] = nueva ? (p.modelo || r.modelo) : r.modelo;
    esfuerzoSes[sid] = nueva ? (p.esfuerzo || r.esfuerzo || '') : (r.esfuerzo || '');
    velocidadSes[sid] = nueva ? (p.velocidad || r.velocidad || '') : (r.velocidad || '');
    if (!nueva){ p.modelo=r.modelo; p.esfuerzo=r.esfuerzo||''; p.velocidad=r.velocidad||''; }
    modoSes[sid] = r.modo || '';
    ctxSes[sid] = r.contexto || null;
    if (activa === sid){ firmaChat[sid] = ''; dibujarSesion(p, cacheChat[sid] || []); }
  } catch(e){} finally { delete pidiendoModelo[sid]; }
}

function chipCtx(sid){
  const c = ctxSes[sid];
  return c && c.tokens
    ? `<span class="ctxSes ${c.nivel || 'bien'}">${c.tokens >= 1000000
        ? (c.tokens/1000000).toFixed(1).replace('.', ',') + ' M'
        : Math.round(c.tokens/1000) + ' k'}</span>` : '';
}

function dibujarAjustes(p){
  // Una pestaña sin estrenar no tiene perillas: tiene la elección de con qué
  // cerebro va a NACER la charla (Claude o Codex), igual que en la compu.
  if (esNueva(p.sid)) return dibujarEligeCerebro(p);
  // Codex tiene las mismas perillas que la pantalla grande — incluido Plan primero
  // desde el 2026-08-25, que antes no existía en ninguna de las dos.
  if (cerebroSes[p.sid] === 'codex'){
    const mod = modeloSes[p.sid] || (modelosMovil[0] || {}).id || '';
    const esf = esfuerzoSes[p.sid] || '';
    const vel = velocidadSes[p.sid] || '';
    const modoCdx = modoSes[p.sid] || '';
    const selModoCdx = modosMovil.length ? `<select
      onchange="cambiarModoSes('${p.sid}', this.value)"
      class="${modoCdx ? 'puesto' : ''}">${modosMovil.map(x =>
        `<option value="${x.id}"${x.id === modoCdx ? ' selected' : ''}>${esc(x.nombre)}</option>`
      ).join('')}</select>` : '';
    const selMod = modelosMovil.length ? `<select
      onchange="cambiarModeloSes('${p.sid}', this.value)"
      class="codex ${mod !== (modelosMovil[0] || {}).id ? 'puesto' : ''}">${modelosMovil.map(x =>
        `<option value="${x.id}"${x.id === mod ? ' selected' : ''}>${esc(x.nombre)}</option>`
      ).join('')}</select>` : '';
    const selEsf = esfuerzosCodexMovil.length ? `<select
      onchange="cambiarEsfuerzoSes('${p.sid}', this.value)"
      class="${esf ? 'puesto' : ''}">${esfuerzosCodexMovil.map(x =>
        `<option value="${x.id}"${x.id === esf ? ' selected' : ''}>${esc(x.nombre)}</option>`
      ).join('')}</select>` : '';
    const selVel = velocidadesCodexMovil.length ? `<select
      onchange="cambiarVelocidadSes('${p.sid}', this.value)"
      class="${vel ? 'puesto' : ''}">${velocidadesCodexMovil.map(x =>
        `<option value="${x.id}"${x.id === vel ? ' selected' : ''}>${esc(x.nombre)}</option>`
      ).join('')}</select>` : '';
    return `<div class="ajusSes"><span class="cerSes">Codex</span>${selMod}${selEsf}${selVel}${selModoCdx}<button
      onclick="revisarCodigoSes('${p.sid}')"
      title="Pedirle que revise los cambios que todavía no commiteaste">⌕ Revisar</button><button
      onclick="mudarCerebroSes('${p.sid}')"
      title="Resumir esta charla y seguirla en una nueva de Claude">→ Claude</button>${chipCtx(p.sid)}</div>`;
  }
  if (!modelosMovil.length) return '';
  const puesto = modeloSes[p.sid] || modelosMovil[0].id;
  const c = ctxSes[p.sid];
  const chip = chipCtx(p.sid);
  // Cuánto piensa antes de contestar: vacío es el de fábrica y por eso no se pinta.
  const esfPuesto = esfuerzoSes[p.sid] || '';
  const selEsf = esfuerzosMovil.length ? `
    <select onchange="cambiarEsfuerzoSes('${p.sid}', this.value)"
            class="${esfPuesto ? 'puesto' : ''}">
      ${esfuerzosMovil.map(x => `<option value="${x.id}"${x.id === esfPuesto ? ' selected' : ''}>${esc(x.nombre)}</option>`).join('')}
    </select>` : '';
  // Plan mode: pintado cuando está puesto, que es lo que hay que notar.
  const modoPuesto = modoSes[p.sid] || '';
  const selModo = modosMovil.length ? `
    <select onchange="cambiarModoSes('${p.sid}', this.value)"
            class="${modoPuesto ? 'puesto' : ''}">
      ${modosMovil.map(x => `<option value="${x.id}"${x.id === modoPuesto ? ' selected' : ''}>${esc(x.nombre)}</option>`).join('')}
    </select>` : '';
  // En el ancho del teléfono el "(200 mil)" no entra y de paso empujaba al resto:
  // acá alcanza "Opus" / "Opus 1M" — la ventana entera se ve en la compu.
  const corto = n => n.replace(' (200 mil)', '').replace(' (1 millon)', ' 1M');
  return `<div class="ajusSes">
    <select onchange="cambiarModeloSes('${p.sid}', this.value)"
            class="${puesto !== modelosMovil[0].id ? 'puesto' : ''}">
      ${modelosMovil.map(m => `<option value="${m.id}"${m.id === puesto ? ' selected' : ''}>${esc(corto(m.nombre))}</option>`).join('')}
    </select>${selEsf}${selModo}
    <button onclick="compactarSes('${p.sid}')"
            class="${c && c.nivel === 'mucho' ? 'conviene' : ''}">Compactar</button>
    <button onclick="revisarCodigoSes('${p.sid}')"
            title="Pedirle que revise los cambios que todavía no commiteaste">⌕ Revisar</button>
    <button onclick="mudarCerebroSes('${p.sid}')"
            title="Resumir esta charla y seguirla en una nueva de Codex">→ Codex</button>
    ${chip}</div>`;
}

// ⭐ Con qué cerebro ARRANCA esta charla (pedido de Martín, 2026-08-19): solo en una
// pestaña sin estrenar, igual que en la compu. Nacida, el id ya dice de quién es y no
// se cambia más. La elección viaja como `cerebro` en /movil/mandar con el primer
// mensaje, y queda guardada EN LA PESTAÑA, así que sobrevive a recargar la app.
function dibujarEligeCerebro(p){
  if (!p.virgen) return '';
  const codex = p.cerebro === 'codex';
  const auto = p.cerebro === 'auto';
  const listaE = codex ? esfuerzosCodexMovil : esfuerzosMovil;
  const mod = p.modelo || modeloSes[p.sid] || (modelosMovil[0] || {}).id || '';
  const esf = p.esfuerzo || esfuerzoSes[p.sid] || '';
  const vel = p.velocidad || velocidadSes[p.sid] || '';
  const perillas = modelosMovil.length ? `<select onchange="ajusteNueva('${p.sid}','modelo',this.value)">${
      modelosMovil.map(x=>`<option value="${x.id}"${x.id===mod?' selected':''}>${esc(x.nombre)}</option>`).join('')}</select>
    <select onchange="ajusteNueva('${p.sid}','esfuerzo',this.value)">${
      listaE.map(x=>`<option value="${x.id}"${x.id===esf?' selected':''}>${esc(x.nombre)}</option>`).join('')}</select>${
    codex && velocidadesCodexMovil.length ? `<select onchange="ajusteNueva('${p.sid}','velocidad',this.value)">${
      velocidadesCodexMovil.map(x=>`<option value="${x.id}"${x.id===vel?' selected':''}>${esc(x.nombre)}</option>`).join('')}</select>` : ''}` : '';
  return `<div class="eligeCer"><small>Arranca con</small>
    <button class="${!codex && !auto ? 'puesto' : ''}" onclick="cerebroNueva('${p.sid}','')">Claude</button>
    <button class="${codex ? 'puesto codex' : ''}" onclick="cerebroNueva('${p.sid}','codex')">Codex</button>
    <button class="${auto ? 'puesto' : ''}" onclick="cerebroNueva('${p.sid}','auto')">Auto</button>
    ${auto ? '' : perillas}</div>`;
}

function cerebroNueva(sid, v){
  const p = pestanas.find(x => x.sid === sid);
  if (!p || !p.virgen) return;
  p.cerebro = v;
  p.modelo = ''; p.esfuerzo = ''; p.velocidad = '';
  delete modeloSes[sid];
  guardar(); firmaChat[sid] = ''; pintarSesion(); verModelo(sid);
}

function ajusteNueva(sid, campo, valor){
  const p = pestanas.find(x => x.sid === sid);
  if (!p || !p.virgen) return;
  p[campo] = valor;
  if (campo === 'modelo'){
    modeloSes[sid] = valor; delete pidiendoModelo[sid];
    guardar(); firmaChat[sid] = ''; verModelo(sid); return;
  }
  if (campo === 'esfuerzo') esfuerzoSes[sid] = valor;
  if (campo === 'velocidad') velocidadSes[sid] = valor;
  guardar(); firmaChat[sid] = ''; pintarSesion();
}

async function cambiarModeloSes(sid, m){
  const r = await (await fetch('/movil/modelo', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, modelo: m})})).json();
  if (r.ok){ modeloSes[sid] = r.modelo; firmaChat[sid] = ''; verModelo(sid); }
}

async function cambiarEsfuerzoSes(sid, x){
  const r = await (await fetch('/movil/esfuerzo', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, esfuerzo: x})})).json();
  if (r.ok){ esfuerzoSes[sid] = r.esfuerzo; firmaChat[sid] = ''; pintarSesion(); }
}

async function cambiarVelocidadSes(sid, x){
  const r = await (await fetch('/movil/velocidad', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, velocidad: x})})).json();
  if (r.ok){ velocidadSes[sid] = r.velocidad; firmaChat[sid] = ''; pintarSesion(); }
}

async function cambiarModoSes(sid, x){
  const r = await (await fetch('/movil/modo', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, modo: x})})).json();
  if (r.ok){ modoSes[sid] = r.modo; firmaChat[sid] = ''; pintarSesion(); }
}

// "Ahora no" a la pregunta de compactar: se calla media hora para esa charla.
function noCompactar(sid){
  silencioComp[sid] = Date.now() + 30 * 60000;
  delete pideCompactar[sid];
  firmaChat[sid] = ''; pintarSesion();
}

// ⚠ Con el dedo va confirmación, no el doble toque de la compu: acá el botón queda
// justo abajo del título y un roce al desplazar no puede arrancar dos turnos. Con
// `directo` (el "Sí" de la pregunta del tope) no se vuelve a preguntar.
async function compactarSes(sid, directo){
  const p = pestanas.find(x => x.sid === sid);
  if (!p || enVuelo[sid]) return;
  if (directo !== true &&
      !confirm('¿Compactar? Resume esta charla y sigue en una nueva con ese resumen. Tarda un rato.')) return;
  enVuelo[sid] = {texto: 'compactando la charla'}; arranque[sid] = Date.now();
  firmaChat[sid] = ''; pintarSesion();
  try {
    const r = await (await fetch('/movil/compactar', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({sid, cwd: p.cwd})})).json();
    if (r.ok && r.sid){
      // La pestaña se muda a la charla nueva; la vieja queda entera en la bandeja.
      // En el hilo no se nota el corte: la conversación viene cosida del servidor.
      delete pideCompactar[sid]; delete pideCompactar[r.sid];
      delete cacheChat[sid]; delete modeloSes[sid]; delete ctxSes[sid];
      p.sid = r.sid; if (activa === sid) activa = r.sid;
      guardar(); fijarDireccion({empujar: false});
    } else alert(r.error || 'No pude compactarla.');
  } catch(e){ alert('No pude compactarla: ' + e); }
  delete enVuelo[sid]; delete arranque[sid];
  firmaChat[activa] = ''; pintarTabs(); pintarSesion();
}

/* ⭐ Revisar el código (2026-08-25). Va como un mensaje MÁS de la charla, no como un
   proceso aparte: el hilo que ves se dibuja de los archivos del propio CLI, así que
   lo que no es un turno de verdad no puede aparecer ahí. Y de paso queda donde sirve
   — podés seguir con "arreglá el segundo" sin cambiar de pantalla.
   Cada cerebro con lo suyo: Claude tiene la skill /code-review; Codex no la tiene (su
   `codex review` es un comando de afuera), así que se le pide en criollo. */
const PEDIDO_REVISION = {
  claude: '/code-review',
  codex: 'Revisá los cambios que todavía no commiteé en este proyecto (mirá el git ' +
         'status y el git diff, incluido lo que está en staged y lo que no se agregó ' +
         'todavía) y decime qué está mal. Primero los errores de verdad, después lo ' +
         'que se pueda simplificar. No arregles nada todavía: quiero leer la lista.'
};

function revisarCodigoSes(sid){
  if (sid !== activa || esNueva(sid) || enVuelo[sid]) return;
  mandar(cerebroSes[sid] === 'codex' ? PEDIDO_REVISION.codex : PEDIDO_REVISION.claude);
}

// ⭐ Mudar la charla al OTRO cerebro (pedido de Martín, 2026-08-20): la resume y
// sigue en una nueva del otro CLI con ese resumen — misma jugada que compactar,
// aterrizando enfrente. La vieja queda entera en la bandeja con su "sigue en".
async function mudarCerebroSes(sid){
  const p = pestanas.find(x => x.sid === sid);
  if (!p || enVuelo[sid]) return;
  const para = cerebroSes[sid] === 'codex' ? 'Claude' : 'Codex';
  if (!confirm('¿Pasar esta charla a ' + para + '? La resume y sigue en una nueva de '
               + para + ' con ese resumen. Tarda un rato.')) return;
  enVuelo[sid] = {texto: 'mudando la charla a ' + para}; arranque[sid] = Date.now();
  firmaChat[sid] = ''; pintarSesion();
  try {
    const r = await (await fetch('/movil/mudar_cerebro', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({sid, cwd: p.cwd})})).json();
    if (r.ok && r.sid){
      // La pestaña se muda a la charla nueva; la vieja queda entera en la bandeja.
      delete cacheChat[sid]; delete modeloSes[sid]; delete ctxSes[sid]; delete cerebroSes[sid];
      p.sid = r.sid; p.cerebro = r.cerebro === 'codex' ? 'codex' : '';
      cerebroSes[r.sid] = p.cerebro;
      if (activa === sid) activa = r.sid;
      guardar(); fijarDireccion({empujar: false});
      if (r.aviso) alert(r.aviso);
    } else alert(r.error || 'No pude mudarla.');
  } catch(e){ alert('No pude mudarla: ' + e); }
  delete enVuelo[sid]; delete arranque[sid];
  firmaChat[activa] = ''; pintarTabs(); pintarSesion();
}

async function pintarSesion(){
  const p = pestanas.find(x => x.sid === activa);
  if (!p) return ir('panel');
  // Con qué modelo corre y cuánto contexto arrastra. Adentro se sale solo si ya lo
  // preguntó, así que no es un pedido por repintado: es uno por charla abierta.
  if (modeloSes[p.sid] === undefined && p.cwd) verModelo(p.sid);
  const mio = ++pintadoNro;
  // Con cache, al toque. Sin cache, igual se dibuja YA el encabezado: el toque
  // tiene que hacer algo visible siempre, aunque la conversación llegue después.
  if (cacheChat[p.sid]) dibujarSesion(p, cacheChat[p.sid]);
  else if (recienAbierta) dibujarSesion(p, [{de:'claude', texto:'Abriendo…'}]);
  // Una charla que todavía no nació no tiene archivo que leer.
  const d = await pedirChat(p);
  if (mio !== pintadoNro || activa !== p.sid) return;   // te fuiste a otra pestaña
  guardarChat(p, d);
  // ⭐ ¿La sesión frenó a preguntarte algo con opciones? Viaja adentro del mismo
  // pedido (campo `pregunta`) y se guarda al lado de la charla, así el repintado
  // siguiente la vuelve a dibujar sin pedirla de nuevo.
  dibujarSesion(p, d.mensajes);
  // Las marcas de texto (lo pintado en la compu) se piden una vez por sesión y se
  // redibuja cuando llegan: es un pedido chico y no vale la pena esperarlo para mostrar
  // la charla. ⚠ `recienAbierta` ya se consumió, así que se fuerza la firma para que el
  // repintado no se saltee por "no cambió nada".
  if (window.Marcas && !marcasPedidas[p.sid] && !esNueva(p.sid)){
    marcasPedidas[p.sid] = true;
    Marcas.cargar(p.sid).then(() => {
      if (activa !== p.sid || !Marcas.cuantas(p.sid)) return;
      firmaChat[p.sid] = '';
      dibujarSesion(p, cacheChat[p.sid] || []);
    });
  }
}
let marcasPedidas = {};

// --- Fotos desde el teléfono ------------------------------------------------
// El clip abre cámara, galería o archivos (lo decide iOS). Antes de subir, la foto
// se REESCALA en el propio teléfono: las del iPhone pesan 3 o 4 MB y con datos
// móviles la subida se hace eterna o se corta. A 1600 puntos se sigue leyendo
// perfecto cualquier captura de pantalla, que es para lo que se usa.
// ⚠ enVuelo es un MAPA por sesión, no una variable suelta. Con una sola, el
// mensaje que mandabas en una pestaña se dibujaba en TODAS las demás: abrías otra
// sesión y ahí estaba el texto de la anterior, como si se hubiera mezclado todo
// (2026-08-16). Lo mismo el "pensando".
let fotos = [], enVuelo = {};
// El hilo del inicio usa {t, x}; las sesiones comunes usan {de, texto}. Los dos
// comparan igual: sin el texto interno que acompaña una foto y sin diferencias de
// saltos o espacios que hacen que el eco se vea dos veces mientras Laura piensa.
const sueltoPanel = t => (t || '').replace(/\[[^\]]*\]/g, '').replace(/📎/g, '')
                                  .replace(/\s+/g, ' ').trim();
function cuentaPanel(mensajes, texto){
  const b = sueltoPanel(texto);
  if(!b) return 0;
  return (mensajes || []).filter(m => m.t === 'vos' && sueltoPanel(m.x) === b).length;
}
// --- ⭐ El ECO: la burbuja provisoria de lo que acabás de mandar --------------------
// Se borra cuando tu mensaje APARECE EN EL HILO. ⚠⚠ Cómo se decide eso costó tres
// intentos, y los dos primeros están mal:
//  1. "mirá los últimos 4" → se duplicaba si la sesión contestaba con varios seguidos.
//  2. "acordate en qué POSICIÓN estaba el hilo al mandarlo" (2026-08-21) → parece
//     razonable, pero `/movil/chat` devuelve **solo los últimos 40 mensajes**: pasada
//     esa marca la lista deja de crecer, la posición guardada cae siempre al final y no
//     se mira ni un mensaje. En toda charla larga el eco quedaba pegado y veías tu
//     mensaje DOS veces hasta que terminaba el turno (reportado dos veces el 2026-08-22,
//     la segunda con el arreglo del punto 2 ya puesto).
//  3. (lo que hay) **contar, no ubicar**: cuántas veces está tu texto entre lo tuyo del
//     hilo. Si ahora está una vez más que al mandarlo, llegó. No depende de posiciones
//     ni de cuántos mensajes devuelva el servidor, y aguanta mandar dos veces lo mismo.
let vecesVuelo = {};
// El texto pelado para comparar: sin el corchete de contexto que el canal le pega
// adelante (la marca de una imagen), sin el clip que el servidor agrega cuando la foto
// no está, y con los espacios aplastados.
const suelto = t => (t || '').replace(/\[[^\]]*\]/g, '').replace(/📎/g, '')
                             .replace(/\s+/g, ' ').trim();
function cuentaTuya(mensajes, texto){
  const b = suelto(texto);
  if(!b) return 0;
  return (mensajes || []).filter(m => m.de === 'vos' && suelto(m.texto) === b).length;
}
// ⭐ La pregunta de compactar (2026-08-20): el servidor ya no compacta solo — cuando la
// charla pasa el tope, el turno vuelve con `pide_compactar` y acá se pregunta.
let pideCompactar = {}, silencioComp = {};
// ⭐⭐ Avisame: desde el 2026-08-29 sirve TAMBIEN con el turno ya corriendo, que es
// cuando de verdad lo necesitas — te das cuenta de que la cosa viene larga MIENTRAS
// piensa, no antes de mandar. Antes era una bandera de este navegador que se consumia
// al MANDAR: apretarlo con el turno andando no hacia nada para ese turno y encima
// quedaba armado en silencio para el mensaje siguiente. Ahora decide el SERVIDOR, que
// es el unico que sabe si hay un turno vivo al que colgarle el aviso.
let avisarTarea = false;
let cacheAvisando = {};
const LADO_MAX = 1600;

function pintarAviso(){
  const b = $('#avisarTarea');
  if (!b) return;
  const enCurso = !!cacheAvisando[activa];
  b.classList.toggle('sel', avisarTarea || enCurso);
  b.title = enCurso ? 'Te aviso al celular cuando termine este turno (tocá para cancelar)'
    : avisarTarea ? 'Te aviso cuando termine el mensaje que mandes'
    : 'Avisarme al celular cuando termine';
}

async function alternarAviso(){
  const sid = (activa && !esNueva(activa)) ? activa : '';
  const quiero = !(avisarTarea || cacheAvisando[activa]);
  let r = null, panelViejo = false;
  if (sid){
    try {
      const resp = await fetch('/movil/avisar', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({sid, quiero})});
      panelViejo = (resp.status === 404);   // el panel corre con el modulo de antes
      r = await resp.json();
    } catch(e){}
  }
  if (r && r.ok && r.enganchado){
    cacheAvisando[activa] = quiero;
    avisarTarea = false;
    pintarAviso();
    return;
  }
  if (r && r.ok && r.motivo === 'recien_termino'){
    // El aviso no se pierde en silencio: apretaste justo cuando terminaba y salio igual.
    cacheAvisando[activa] = false; avisarTarea = false; pintarAviso();
    alert('Ya había terminado: te mandé el aviso igual.');
    return;
  }
  avisarTarea = quiero;
  cacheAvisando[activa] = false;
  pintarAviso();
  if (quiero && panelViejo){
    alert('Reiniciá el panel: esta versión todavía no sabe enganchar el aviso a un turno '
        + 'que ya está corriendo. Por ahora queda pedido para el mensaje que mandes vos.');
  } else if (quiero && cacheOcupada[activa]){
    alert('Esa charla está trabajando, pero el turno no lo largó esta pantalla, así que '
        + 'no puedo engancharle el aviso. Queda pedido para el mensaje que mandes vos.');
  }
}

async function achicar(file){
  if (!file.type.startsWith('image/')) return null;
  const bitmap = await createImageBitmap(file);
  const escala = Math.min(1, LADO_MAX / Math.max(bitmap.width, bitmap.height));
  if (escala === 1 && file.size < 900000) return file;      // ya es chica: va tal cual
  const lienzo = document.createElement('canvas');
  lienzo.width = Math.round(bitmap.width * escala);
  lienzo.height = Math.round(bitmap.height * escala);
  lienzo.getContext('2d').drawImage(bitmap, 0, 0, lienzo.width, lienzo.height);
  const blob = await new Promise(r => lienzo.toBlob(r, 'image/jpeg', 0.85));
  return new File([blob], (file.name || 'foto').replace(/\.[^.]+$/, '') + '.jpg',
                  {type:'image/jpeg'});
}

async function elegirFotos(lista){
  for (const f of lista){
    const chica = await achicar(f);
    if (chica) fotos.push(chica);
  }
  $('#archivo').value = '';
  pintarChapas();
}

function pintarChapas(){
  const c = $('#chapas');
  c.classList.toggle('hay', fotos.length > 0);
  c.innerHTML = fotos.map((f,i) =>
    `<div class="chapa"><img src="${URL.createObjectURL(f)}">
       <div class="x" onclick="sacarFoto(${i})">✕</div></div>`).join('');
}

function sacarFoto(i){ fotos.splice(i,1); pintarChapas(); }

function verFoto(url){
  $('#visorImg').src = url;
  $('#visor').classList.add('abierto');    // se cierra tocando en cualquier lado
}

// Escribirme a MÍ desde el inicio. Va por /chat/mandar, que es la misma puerta del
// chat de la computadora: buzón, una sola Laura, misma memoria. Puede tardar lo que
// tarde el turno, así que mientras tanto se ve tu mensaje y los puntitos.
async function mandarALaura(){
  const t = $('#texto').value.trim();
  if ((!t && !fotos.length) || enVuelo['panel']) return;
  $('#texto').value=''; ajustarCaja($('#texto')); $('#mandar').textContent='…';
  const f = new FormData();
  f.append('texto', t);
  for (const foto of fotos) f.append('imagenes', foto, foto.name);
  enVuelo['panel'] = {texto: t, urls: fotos.map(x => URL.createObjectURL(x)),
                       veces: cuentaPanel(mensajesPanel, t)};
  fotos = []; pintarChapas();
  const h = $('#hilo');
  if (h){
    h.insertAdjacentHTML('beforeend',
      `<div class="msg vos">${esc(t)}</div>
       <div class="msg ia pensando">pensando<span></span><span></span><span></span></div>`);
    h.scrollTop = h.scrollHeight;
  }
  try {
    const r = await (await fetch('/chat/mandar', {method:'POST', body:f})).json();
    if (!r.ok) alert(r.error || 'No pude mandarlo');
  } catch(e){ alert('Se cortó: ' + e); }
  delete enVuelo['panel'];
  $('#mandar').textContent='Enviar';
  pintarPanel();
}

// ⏹ Cortar el turno que esta pensando. Mata el proceso de ese turno: lo que ya
// escribio queda escrito, la charla no se rompe y podes escribirle de nuevo. No es un
// error, asi que NO deja la marca roja (Martin, 2026-08-17).
async function parar(){
  const p = pestanas.find(x => x.sid === activa);
  if (!p) return;
  parados[p.sid] = true;
  $('#parar').textContent = '…';
  try {
    const r = await (await fetch('/movil/parar', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({sid: esNueva(p.sid) ? '' : p.sid, cwd: p.cwd})})).json();
    if (!r.paro) alert('Ya habia terminado: no quedaba nada corriendo.');
  } catch(e){ alert('No pude pararlo: ' + e); }
  $('#parar').textContent = '⏹';
  delete enVuelo[p.sid]; delete arranque[p.sid];
  pintar();
}

// ⭐ Lo que no se pudo mandar NO SE PIERDE (2026-08-23). Vuelve a ser el borrador de esa
// charla, y si seguís parado ahí y no escribiste otra cosa mientras tanto, vuelve también
// a la caja con sus fotos. Antes se borraba apenas apretabas Enviar y, si el servidor lo
// rebotaba —"esa sesión está contestando algo"—, había que escribirlo todo de nuevo.
function devolverLoEscrito(sid, texto, fotosGuardadas){
  fotosGuardadas = fotosGuardadas || [];
  if (!texto && !fotosGuardadas.length) return;
  if (texto) anotarBorrador(sid, texto);
  if (activa !== sid) return;
  const caja = $('#texto');
  if (texto && caja && !caja.value.trim()){ caja.value = texto; ajustarCaja(caja); }
  if (fotosGuardadas.length && !fotos.length){ fotos = fotosGuardadas; pintarChapas(); }
}

// `forzado` es un mensaje que manda la pantalla sola, sin pasar por la caja de
// escribir: hoy lo usa la decisión del plan de Codex. Se comprueba que sea texto y no
// un evento, porque a `mandar` también la llaman desde el botón Enviar.
async function mandar(forzado){
  if (activa === 'panel') return mandarALaura();
  const impuesto = (typeof forzado === 'string' && forzado.trim()) ? forzado.trim() : '';
  const p = pestanas.find(x => x.sid === activa);
  const t = impuesto || $('#texto').value.trim();
  if (!p || (!t && !fotos.length) || enVuelo[p.sid]) return;
  // La caja ya se bloquea sola cuando la sesión está contestando; esto es el cinturón por
  // si el estado llegó viejo. Se corta ANTES de borrar nada de lo que escribiste.
  if (cacheOcupada[p.sid]){
    alert('Esa sesión está contestando algo. Te dejo lo que escribiste para cuando termine.');
    return;
  }
  let clave = p.sid;                       // la pestaña donde estás parado AHORA
  $('#mandar').textContent='…';
  // Un mensaje impuesto no vacía la caja ni se lleva puestas tus fotos: lo que tenías
  // a medio escribir sigue ahí cuando la sesión vuelve a estar libre.
  if (!impuesto){
    $('#texto').value=''; ajustarCaja($('#texto'));
    // Lo mandaste: el borrador ya no existe. Se avisa igual aunque `/movil/mandar` lo borre
    // del lado del servidor, para que la chapa se apague en el acto.
    anotarBorrador(clave, ''); soltarBorrador();
  }
  const fotosParaEnviar = impuesto ? [] : fotos;   // guardadas por si hay que devolverlas
  const f = new FormData();
  // en una pestaña recién creada el sid es provisorio: se manda vacío para que
  // arranque una sesión nueva de verdad
  f.append('cwd', p.cwd); f.append('sid', p.virgen ? '' : p.sid); f.append('texto', t);
  // Con qué cerebro nace una charla NUEVA (con id, el servidor lo deduce solo del sid).
  f.append('cerebro', (p.virgen && p.cerebro) || '');
  f.append('modelo', p.modelo || modeloSes[p.sid] || '');
  f.append('esfuerzo', p.esfuerzo || esfuerzoSes[p.sid] || '');
  f.append('velocidad', p.velocidad || velocidadSes[p.sid] || '');
  // Una charla ya nacida puede seguir trabajando aunque Safari cierre este pedido.
  // ⭐ Las nuevas también van por acá desde el 2026-08-23: antes conservaban el camino
  // sincrono "porque necesitabamos su id real", y eso era el bug — el id llegaba recien
  // al terminar el primer turno y hasta entonces la pantalla no tenia a que charla
  // mirar: quedaba en "Sin mensajes todavia" con la burbuja de pensando aunque la
  // sesion estuviera contestando. Ahora el servidor publica el id apenas nace.
  f.append('segundo_plano', '1');
  // ⭐ El aviso se pide para ESTE mensaje. Dos arreglos del 2026-08-29: (1) las charlas
  // sin estrenar ya no quedan afuera — el aviso se arma al TERMINAR, con el id que la
  // charla ya gano, y el primer turno de una charla nueva suele ser justo el largo;
  // (2) se apaga tambien la LUZ del boton: antes se apagaba la variable y la clase
  // `.sel` quedaba puesta, asi que el boton se veia amarillo mintiendo.
  if (avisarTarea){ f.append('avisar', '1'); avisarTarea = false; pintarAviso(); }
  // Mudarse al id de verdad. Se llama dos veces: apenas el trabajo lo publica (en plena
  // pensada) y al cerrar el turno, por si la charla cambio de id al compactarse.
  const mudarA = (sidNuevo, extras) => {
    if (sidNuevo && sidNuevo !== clave){
      // ⭐⭐ ¿Seguís parado en esta charla? Se pregunta ACÁ, con el id viejo todavía
      // puesto: dos renglones más abajo `clave` ya es el nuevo. Si mandás el primer
      // mensaje de una charla nueva y te vas mientras piensa, la respuesta NO te tiene
      // que arrastrar de vuelta (2026-08-23).
      const seguisAca = activa === clave;
      // lo que está en vuelo se muda con la pestaña, si no el mensaje quedaría colgado
      // de una clave que ya no existe
      enVuelo[sidNuevo] = enVuelo[clave]; delete enVuelo[clave];
      vecesVuelo[sidNuevo] = vecesVuelo[clave]; delete vecesVuelo[clave];
      if (parados[clave]){ parados[sidNuevo] = parados[clave]; delete parados[clave]; }
      clave = sidNuevo;
      p.sid = sidNuevo; p.virgen = false;
      if (seguisAca) activa = sidNuevo;
      // Recien ahora la charla tiene id propio: ahi gana su direccion. Reemplazando y
      // no empujando — la entrada anterior tenia un id provisorio que ya no existe.
      // ⚠ Solo si seguís acá: si te fuiste, la barra de direcciones es de la pantalla
      // que estás mirando ahora.
      if (seguisAca) fijarDireccion({empujar: false});
      guardar(); pintarTabs(); pintar();
    }
    if (!extras) return;
    // La charla nació con el cerebro elegido: se anota ya, sin esperar a verModelo,
    // para que el encabezado muestre la chapita "Codex" desde el primer repintado.
    if (extras.cerebro) p.cerebro = extras.cerebro === 'codex' ? 'codex' : '';
    if (p.cerebro) cerebroSes[clave] = p.cerebro;
    if (Object.prototype.hasOwnProperty.call(extras,'modelo')) modeloSes[clave] = extras.modelo;
    if (Object.prototype.hasOwnProperty.call(extras,'esfuerzo')) esfuerzoSes[clave] = extras.esfuerzo;
    if (Object.prototype.hasOwnProperty.call(extras,'velocidad')) velocidadSes[clave] = extras.velocidad;
  };
  for (const foto of fotosParaEnviar) f.append('imagenes', foto, foto.name);
  enVuelo[clave] = {texto: t, urls: fotosParaEnviar.map(f => URL.createObjectURL(f))};
  vecesVuelo[clave] = cuentaTuya(cacheChat[clave], t);
  if (!impuesto){ fotos = []; pintarChapas(); }
  pintar();
  try {
    let r = await (await fetch('/movil/mandar', {method:'POST', body:f})).json();
    if (r.segundo_plano && r.trabajo){
      // El POST ya termino: desde aca solo consultamos una ficha chica. Si una consulta
      // falla por cambio de red, se reintenta; el CLI no depende de esta conexion.
      while (true){
        await new Promise(ok => setTimeout(ok, 1200));
        try {
          const e = await (await fetch('/movil/trabajo/' + r.trabajo)).json();
          if (!e.ok){ r = e; break; }
          // ⭐ La charla nueva ya tiene su id: la pestaña se muda AHORA, en plena
          // pensada, y el hilo empieza a mostrar lo que la sesión va contestando.
          if (e.sid_nuevo) mudarA(e.sid_nuevo, null);
          if (e.estado === 'trabajando') continue;
          r = {...e, ok: e.estado === 'terminado', sid: e.sid_nuevo || e.sid};
          break;
        } catch(e){ continue; }
      }
    }
    // El turno cerró: si la charla cambió de id (nació recién, o el CLI la compactó a
    // mitad de camino) la pestaña se muda ahora. Si ya se había mudado en el medio, esto
    // solo deja anotadas las perillas con las que quedó.
    if (r.sid) mudarA(r.sid, r);
    // Si lo cortaste vos con el botón ⏹, el turno vuelve con error y eso NO es una
    // falla: no se pinta de rojo.
    if (!r.ok && !parados[clave]){
      falladas[clave] = {que: String(r.error || 'No pude mandarlo').slice(0,200),
                         ts: Date.now()/1000};
      // No se pudo mandar: te lo devuelvo en vez de perderlo. Un mensaje impuesto NO
      // se devuelve a la caja: ahí adentro está lo tuyo, y lo pisaría.
      if (!impuesto){
        devolverLoEscrito(clave, t, fotosParaEnviar);
        alert((r.error || 'No pude mandarlo') + ' Te dejo lo que escribiste en la caja.');
      } else alert(r.error || 'No pude mandarle la decisión del plan.');
    } else if (r.ok) delete falladas[clave];
    // ⭐ El tope ya no compacta solo (2026-08-20): si la charla pasó el límite, el
    // turno vuelve con la pregunta y se dibuja adentro del hilo, sin cartel del
    // navegador. "Ahora no" la silencia media hora.
    if (r.pide_compactar && !(silencioComp[clave] > Date.now()))
      pideCompactar[clave] = r.pide_compactar;
    else delete pideCompactar[clave];
  } catch(e){
    if (!parados[clave]){
      falladas[clave] = {que: 'Se cortó: ' + e, ts: Date.now()/1000};
      if (!impuesto) devolverLoEscrito(clave, t, fotosParaEnviar);
    }
  }
  delete enVuelo[clave]; delete arranque[clave]; delete parados[clave];
  delete vecesVuelo[clave];
  elegirFirma = ''; guardarMarcas();
  $('#mandar').textContent='Enviar'; pintar();
}

// --- Hablarle con el microfono DEL TELEFONO --------------------------------
// Mantenés apretado, hablás, soltás: igual que un audio de WhatsApp. Es la MISMA
// Laura del micrófono de la compu (misma sesión y misma memoria), solo que la voz
// entra por acá. ⚠ El navegador solo entrega el micrófono en HTTPS: por eso la app
// se abre por la dirección con candado de Tailscale, no por la vieja con puerto.
// Es una CHARLA, no un walkie-talkie (pedido de Martín, 2026-08-16): tocás una vez
// y queda escuchando. El teléfono mismo se da cuenta de cuándo dejaste de hablar
// (mide el volumen cada 50 ms y corta tras un segundo de silencio), manda la frase,
// te contesta en voz alta y vuelve a escuchar solo. Mismo ciclo que por micrófono
// en la compu, pero acá el que decide el corte es el navegador.
const UMBRAL_VOZ = 0.02;      // volumen (0 a 1) a partir del cual se considera voz
const SILENCIO_CORTE = 1100;  // ms de silencio que cierran la frase
const MIN_FRASE = 400;        // ms de voz para que cuente como algo dicho

let charla = false, oyendo = false, ocupadoVoz = false;
let mic = null, audioCtx = null, analizador = null, latido = null;
let grabadora = null, trozos = [];

function pintarHablar(){
  if ($('#hablar')) return;                 // no repintar: cortaría la charla
  $('#cuerpo').innerHTML = `<div id="hablar">
      <div id="estado">Conectando…</div>
      <div id="onda"><i></i><i></i><i></i><i></i><i></i></div>
      <div id="dicho"></div><div id="respuesta"></div>
      <button id="colgar" onclick="cortarCharla()">✕</button></div>`;
  $('#colgar').style.display = 'none';
  empezarCharla();                          // ⭐ entrás y ya te escucha: no hay que apretar
}

function decir(texto, clase){
  const e = $('#estado');
  if (!e) return;
  e.textContent = texto;
  e.className = clase || '';
  $('#onda').className = clase === 'escuchando' ? 'viva'
                       : (clase === 'pensando' || clase === 'hablando') ? 'late' : '';
}

async function empezarCharla(){
  try {
    // echoCancellation es lo que evita que se escuche a sí mismo por el parlante.
    mic = await navigator.mediaDevices.getUserMedia({audio:{
      echoCancellation:true, noiseSuppression:true, autoGainControl:true}});
  } catch(e){
    // Safari a veces exige un toque tuyo para dar el micrófono: ahí, y solo ahí,
    // aparece un botón. Si ya diste permiso, esto no se ve nunca más.
    decir('Tocá para hablar conmigo', 'problema');
    $('#respuesta').innerHTML = '<button id="arrancar" onclick="empezarCharla()">Empezar</button>';
    return;
  }
  $('#respuesta').textContent = '';
  $('#colgar').style.display = '';
  charla = true;
  sesionAudio('play-and-record');
  // El contexto se abre con el mismo permiso del micrófono: queda desbloqueado
  // para todo lo que venga después, que ya no cuenta como gesto tuyo.
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') await audioCtx.resume();
  analizador = audioCtx.createAnalyser();
  analizador.fftSize = 2048;
  audioCtx.createMediaStreamSource(mic).connect(analizador);
  escucharFrase();
}

function cortarCharla(){
  charla = oyendo = false;
  clearInterval(latido); latido = null;
  try { if (grabadora && grabadora.state !== 'inactive') grabadora.stop(); } catch(e){}
  if (mic) mic.getTracks().forEach(t => t.stop());
  if (audioCtx) audioCtx.close().catch(()=>{});
  mic = audioCtx = analizador = grabadora = null;
  if (!$('#hablar')) return;
  $('#colgar').style.display = 'none';
  decir('Cortaste. Volvé a entrar a la pestaña para seguir.', 'problema');
  document.querySelectorAll('#onda i').forEach(b => b.style.height = '16px');
}

function escucharFrase(){
  if (!charla || ocupadoVoz) return;
  const tipo = ['audio/webm','audio/mp4','audio/aac'].find(t => MediaRecorder.isTypeSupported(t));
  grabadora = new MediaRecorder(mic, tipo ? {mimeType:tipo} : undefined);
  trozos = [];
  grabadora.ondataavailable = e => { if (e.data.size) trozos.push(e.data); };
  grabadora.onstop = () => mandarVoz();
  grabadora.start();
  oyendo = true;
  decir('Te escucho', 'escuchando');
  const datos = new Float32Array(analizador.fftSize);
  const barras = [...document.querySelectorAll('#onda i')];
  let hablo = 0, ultimoSonido = 0;
  clearInterval(latido);
  latido = setInterval(() => {
    if (!charla || !oyendo) return;
    analizador.getFloatTimeDomainData(datos);
    let suma = 0;
    for (const v of datos) suma += v * v;
    const vol = Math.sqrt(suma / datos.length);
    const ahora = Date.now();
    // La onda se mueve con tu voz: sin esto no hay forma de saber si te oye.
    barras.forEach((b, i) => {
      const factor = [0.55, 0.85, 1, 0.85, 0.55][i];
      b.style.height = Math.min(84, 16 + vol * 900 * factor) + 'px';
    });
    if (vol > UMBRAL_VOZ){ hablo += 50; ultimoSonido = ahora; }
    // Cierra la frase cuando ya dijiste algo y te quedaste callado un segundo.
    if (hablo >= MIN_FRASE && ultimoSonido && ahora - ultimoSonido > SILENCIO_CORTE){
      oyendo = false; clearInterval(latido); latido = null;
      try { grabadora.stop(); } catch(e){}
    }
  }, 50);
}

// ⭐ Hacer sonar la respuesta en un iPhone tiene tres trampas, y las tres daban el
// mismo síntoma: llega el texto y no se escucha nada.
//  1) Con el micrófono abierto, iOS pone la sesión de audio en "grabar y
//     reproducir" y manda el sonido al AURICULAR de arriba, casi inaudible.
//     navigator.audioSession (iOS 16.4+) lo devuelve al parlante.
//  2) El interruptor de silencio del costado apaga los <audio> normales; en modo
//     "playback" el sonido suena igual, como en WhatsApp.
//  3) Reproducir después de un await ya no cuenta como "gesto del usuario" y
//     Safari lo bloquea. Por eso se usa el AudioContext que abrió el toque del
//     botón (basta con despertarlo), en vez de un <audio> nuevo cada vez.
function sesionAudio(tipo){
  try { if (navigator.audioSession) navigator.audioSession.type = tipo; } catch(e){}
}

// ⭐ Por dónde sale mi voz depende de por dónde entra la tuya. Si el micrófono que
// agarró iOS es el de un auricular (AirPods, ROG por Bluetooth, manos libres), hay
// que quedarse en la ruta de llamada: pedir 'playback' ahí manda el sonido al
// PARLANTE del teléfono y el auricular se queda mudo — pasó, 2026-08-16. Sin
// auricular sí conviene 'playback': es lo que lo saca del auricular de arriba y lo
// hace sonar aunque tengas puesto el interruptor de silencio.
function rutaDeSalida(){
  const pista = mic && mic.getAudioTracks && mic.getAudioTracks()[0];
  const etiqueta = ((pista && pista.label) || '').toLowerCase();
  return /airpod|bluetooth|headset|headphone|auricular|manos libres|hands-free/.test(etiqueta)
       ? 'play-and-record' : 'playback';
}

async function reproducir(b64){
  const crudo = atob(b64);
  const bytes = new Uint8Array(crudo.length);
  for (let i = 0; i < crudo.length; i++) bytes[i] = crudo.charCodeAt(i);
  sesionAudio(rutaDeSalida());
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    const buffer = await audioCtx.decodeAudioData(bytes.buffer.slice(0));
    const fuente = audioCtx.createBufferSource();
    fuente.buffer = buffer;
    fuente.connect(audioCtx.destination);
    await new Promise(listo => { fuente.onended = listo; fuente.start(); });
  } catch(e){
    // Último recurso: el reproductor de siempre.
    const son = new Audio('data:audio/wav;base64,' + b64);
    await new Promise(listo => { son.onended = son.onerror = listo; son.play().catch(listo); });
  }
  sesionAudio('play-and-record');                // vuelve a escuchar
}

async function mandarVoz(){
  const audio = new Blob(trozos, {type:(grabadora && grabadora.mimeType) || 'audio/webm'});
  const esMp4 = ((grabadora && grabadora.mimeType) || '').includes('mp4');
  if (!charla) return;
  if (audio.size < 1500) return escucharFrase();     // ruido suelto: seguir escuchando
  ocupadoVoz = true;
  decir('Pensando…', 'pensando');
  const f = new FormData();
  f.append('audio', audio, 'voz.' + (esMp4 ? 'mp4' : 'webm'));
  try {
    const r = await (await fetch('/movil/hablar', {method:'POST', body:f})).json();
    if (r.error || r.detail){
      decir(r.error || r.detail, 'problema');
    } else {
      $('#dicho').textContent = '“' + r.dicho + '”';
      $('#respuesta').textContent = r.respuesta;
      if (r.audio_b64){
        decir('Hablando…', 'hablando');
        // Recién cuando TERMINA de sonar se vuelve a escuchar: si no, se oye a sí
        // misma y se contesta sola.
        await reproducir(r.audio_b64);
      }
    }
  } catch(e){ decir('Se cortó la conexión', 'problema'); }
  ocupadoVoz = false;
  if (charla) escucharFrase();
}

// ⭐ La pizarra del telefono es LA MISMA pagina que la de la compu, metida acá
// adentro (pedido de Martín, 2026-08-16: "que sea la misma pizarra que veo, poder
// mover cosas, como Excalidraw o Miro"). La primera versión mostraba las notas
// como lista y no era eso: uno quiere el lienzo. Los gestos con el dedo (un dedo
// corre el lienzo, dos hacen zoom) viven en la página de la pizarra, no acá.
function pintarPizarra(){
  const caja = $('#cuerpo');
  if (caja.firstElementChild && caja.firstElementChild.tagName === 'IFRAME') return;
  caja.innerHTML = '<iframe src="/pizarra" title="Pizarra"></iframe>';
}

const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
// Lo que escribe Claude se dibuja como markdown (`/estaticos/marcado.js`, el mismo
// que usa la página de sesiones de la compu): antes se leían los asteriscos y los
// numerales crudos. Si el archivo no cargó, mejor texto pelado que pantalla en blanco.
const marcar = t => window.md ? '<div class="md">' + window.md(t) + '</div>' : esc(t);
// Deslizar el dedo cambia de pestaña, como en cualquier app del teléfono: es lo
// que uno intenta antes de buscar la barra de arriba. No se activa dentro de la
// pizarra (ahí el dedo mueve el lienzo) ni sobre una foto.
// ⚠⚠ SELECCIONAR TEXTO PARA COPIARLO ES TAMBIÉN ARRASTRAR EL DEDO A LOS COSTADOS.
// La primera versión miraba solo dónde empezó y dónde terminó el dedo (70 px y
// |dx|>|dy|), así que no los distinguía: Martín intentaba marcar una respuesta para
// copiarla y la app le cambiaba de conversación, y estando en una charla se iba solo
// a otra (2026-08-23). No se arregla partiendo la pantalla en zonas: los dos gestos se
// separan por CÓMO se hacen. Cambiar de pestaña es RÁPIDO, derecho y con un dedo;
// seleccionar arranca con el dedo apoyado (el teléfono pide medio segundo antes de
// mostrar las manijas) y después va y viene. De ahí las cuatro condiciones de abajo.
const SWIPE_MS = 500;      // más lento que esto ya no es un pase, es una selección
const SWIPE_PX = 70;       // lo que hay que correr para que cuente
let sx = 0, sy = 0, sArranque = 0, sDesvio = 0, sVale = false;
// Hay texto marcado en la pantalla: el que arrastró estaba copiando, no navegando.
function haySeleccion(){
  const s = window.getSelection && window.getSelection();
  return !!(s && !s.isCollapsed && String(s).trim());
}
// Zonas donde el dedo hace lo suyo: la caja de escribir y lo que se desplaza a lo
// ancho por su cuenta (un bloque de código largo, una tabla, la pizarra embebida).
function dedoOcupado(el){
  return !!(el && el.closest &&
            el.closest('input, textarea, [contenteditable], pre, code, table, iframe'));
}
$('#cuerpo').addEventListener('touchstart', e => {
  // Un dedo solo: con dos estás agrandando para leer, no cambiando de pestaña.
  sVale = e.touches.length === 1 && !haySeleccion() && !dedoOcupado(e.target);
  if (!sVale) return;
  sx = e.touches[0].clientX; sy = e.touches[0].clientY;
  sArranque = Date.now(); sDesvio = 0;
}, {passive:true});
$('#cuerpo').addEventListener('touchmove', e => {
  if (!sVale) return;
  if (e.touches.length > 1){ sVale = false; return; }
  // El desvío vertical se mide DURANTE todo el gesto, no al final: mirando solo el
  // punto de llegada, un movimiento en L —bajás y después vas al costado— pasaba
  // por deslizada de manual.
  sDesvio = Math.max(sDesvio, Math.abs(e.touches[0].clientY - sy));
}, {passive:true});
$('#cuerpo').addEventListener('touchcancel', () => { sVale = false; }, {passive:true});
$('#cuerpo').addEventListener('touchend', e => {
  if (!sVale || activa === 'pizarra' || !e.changedTouches.length) return;
  sVale = false;
  if (Date.now() - sArranque > SWIPE_MS) return;   // fue lento: estabas seleccionando
  if (haySeleccion()) return;                      // hay texto marcado: no te lo tiro
  const dx = e.changedTouches[0].clientX - sx;
  if (Math.abs(dx) < SWIPE_PX) return;             // apenas se movió: fue un toque
  if (sDesvio > Math.abs(dx) / 2) return;          // se fue para abajo: fue scroll
  const orden = ['panel','hablar','pizarra', ...pestanas.map(p => p.sid)];
  const i = orden.indexOf(activa);
  if (i < 0) return;
  const destino = orden[dx < 0 ? i + 1 : i - 1];
  if (destino) ir(destino);
}, {passive:true});

$('#texto').addEventListener('input', e => {
  ajustarCaja(e.target);
  // ⭐ Cada tecla queda guardada como borrador: aca en el acto, y al servidor con el
  // respiro de 700 ms de `anotarBorrador`.
  anotarBorrador(activa, e.target.value);
});
// Irse de la app (o mandarla al fondo) manda lo que estaba esperando el respiro. El
// `keepalive` del fetch es lo que hace que ese pedido llegue igual.
addEventListener('pagehide', soltarBorrador);
document.addEventListener('visibilitychange', () => { if (document.hidden) soltarBorrador(); });

// ⭐ "Sesiones" es el botón de VOLVER AL PRINCIPIO: te deja arriba de todo, en la
// bandeja con todas las conversaciones, sin importar en qué carpeta habías quedado, si
// habías filtrado algo o dónde estabas parado con el scroll (pedido de Martín,
// 2026-08-17). Los otros tres destinos entran como siempre.
document.querySelectorAll('#abajo .dest').forEach(d =>
  d.addEventListener('click', () => {
    if (d.dataset.href) { location.href = d.dataset.href; return; }
    if (d.dataset.ir === 'nueva'){
      proyElegido = TODAS;
      filtroSes = '';
      buscaCarp = '';
      cajonAbierto = false;
      elegirFirma = '';                 // forzar el redibujo aunque parezca igual
      localStorage.setItem('proyElegido', TODAS);
    }
    ir(d.dataset.ir);
    if (d.dataset.ir === 'nueva')
      // Después de dibujar, al principio de la lista. Sin esto quedaba donde estaba
      // el scroll de la pantalla anterior, que es medio lista abajo.
      setTimeout(() => { const c = $('#cuerpo'); if (c) c.scrollTop = 0; }, 60);
  }));

// ⭐ Entrar por una direccion: `/movil?c=<id>` abre esa charla, `/movil?v=panel` esa
// pantalla. LA DIRECCION MANDA sobre lo que quedo guardado en el servidor: si el link
// dice una conversacion, es porque abriste ese favorito para ir ahi.
// ⚠ Si la charla no esta entre tus pestañas se le pregunta al servidor en que carpeta
// vive (`/movil/donde`): la lista de `/movil/sesiones` esta topeada al ultimo mes y un
// favorito sirve justamente para volver a algo viejo.
async function entrarPorDireccion(){
  if (!window.Direccion) return false;
  const {c, v} = Direccion.leer();
  if (v && FIJAS.includes(v)){ activa = v; return true; }
  if (!c) return false;
  if (pestanas.some(p => p.sid === c)){ activa = c; return true; }
  const d = await Direccion.donde(c);
  if (!d) return false;
  pestanas.unshift({sid: c, cwd: d.cwd,
                    nombre: d.nombre.length > 15 ? d.nombre.slice(0,14)+'…' : d.nombre});
  activa = c;
  return true;
}

// ⭐⭐ Se dibuja ANTES de preguntarle nada a nadie, con lo que quedo guardado en el
// telefono (las pestañas y la lista de conversaciones de la ultima vez). Antes la app
// esperaba DOS idas y vueltas —`/movil/pestanas` y `/movil/sesiones`— para pintar la
// primera pantalla, y por Tailscale eso se siente. Lo que llega despues repinta si algo
// cambio (2026-08-18).
pintarTabs(); pintar();

// --- ⚡ Skills y comandos (los dibuja /estaticos/atajos.js) --------------------
// El mismo botón de las otras dos pantallas. Lo único distinto es la etiqueta (acá
// entra solo el rayo) y de dónde salen las acciones: en el teléfono el modelo es un
// <select> del encabezado de la charla, así que "/model" lo despliega.
if (window.Atajos) Atajos.montar({
  contenedor: $('#atajosAqui'),
  etiqueta: '⚡',
  sesion: () => {
    const p = pestanas.find(x => x.sid === activa) || {};
    return {sid: (p.sid && !esNueva(p.sid)) ? p.sid : '', cwd: p.cwd || ''};
  },
  insertar: texto => {
    const c = $('#texto');
    c.value = (c.value ? c.value.trimEnd() + ' ' : '') + texto;
    ajustarCaja(c); c.focus();
  },
  // Los comandos con equivalente acá aprietan ESE control: mandar "/compact" como
  // texto no hace nada (el CLI lo ignora desde afuera, probado el 2026-08-18).
  acciones: {
    compactar: () => compactarSes(activa),
    nueva: () => {
      const p = pestanas.find(x => x.sid === activa);
      if (p && p.cwd) nuevaEn(p.cwd); else ir('nueva');
    },
    modelo: () => {
      const s = document.querySelector('.ajusSes select');
      if (s){ s.focus(); if (s.showPicker) try { s.showPicker(); } catch(e){} }
    }
  }
});

(async () => {
  try {
    const g = await (await fetch('/movil/pestanas')).json();
    if (g.pestanas && g.pestanas.length){ pestanas = g.pestanas; activa = g.activa || 'panel'; }
  } catch(e){}
  // Despues de leer lo guardado, para poder pisarlo: la direccion es mas especifica.
  if (await entrarPorDireccion()) guardar();
  fijarDireccion({empujar: false});
  // Si arrancaste dentro de una charla, adelantar el Inicio acá aprovecha el rato en
  // que todavía estás leyendo. El primer toque a Laura no espera su pantalla.
  if (activa !== 'panel') precargarPanel();
  await traerSesiones();
  // La flecha ← del navegador (en la app de la pantalla de inicio no hay, pero en el
  // navegador si). `ir()` reescribe la direccion, que ya es la misma: no toca el historial.
  if (window.Direccion) Direccion.alVolver(async estado => {
    if (estado.v && FIJAS.includes(estado.v)) return ir(estado.v);
    if (!estado.c) return ir('panel');
    if (estado.c === activa) return;
    if (pestanas.some(p => p.sid === estado.c)) return ir(estado.c);
    const d = await Direccion.donde(estado.c);
    if (d) abrir(d.cwd, estado.c, d.nombre);
  });
  pintarTabs(); pintar();
  // Traer en segundo plano las conversaciones de las pestañas abiertas: cuando
  // toques una, ya está y se dibuja sin esperar nada.
  pestanas.forEach(precargar);
  setInterval(pintar, 3000);          // el "en vivo": relee el archivo de la sesión
  // cuales estan abiertas en la compu cambia solo cuando Martin abre o cierra una
  // ventana alla: con mirarlo cada 15 s alcanza y no carga al server al pedo
  setInterval(async () => { if (await traerSesiones()) pintarTabs(); }, 15000);
})();
</script></body></html>"""


@app.get("/movil", response_class=HTMLResponse)
def movil():
    """La consola chica. Se abre desde el celular por la red privada de Tailscale.

    ⚠ Va SIN CACHE a proposito. Agregada a la pantalla de inicio, iOS se guarda la
    pagina y al volver a abrirla te muestra la de antes: se arregla algo en el panel,
    Martin abre la app y sigue viendo lo viejo — paso el 2026-08-17 con la barra que
    tapaba el teclado ("sigue apareciendo", y ya estaba arreglado). Que la pida siempre.
    """
    return HTMLResponse(MOVIL_HTML, headers={"Cache-Control": "no-store, must-revalidate"})


def _sesion_de_laura():
    """El id de la sesion que Laura esta usando HOY (micrófono, Telegram y panel)."""
    try:
        d = json.loads(CLAUDE_SESION.read_text(encoding="utf-8"))
        return (d.get("actual") or {}).get("session_id") or ""
    except Exception:
        return ""


# ⭐ La respuesta de recien, por unos segundos. No es por el costo de UNA consulta (con los
# caches de `novedad` y de los titulos quedo en ~60 ms) sino porque la piden VARIAS
# pantallas a la vez: la de sesiones al entrar y cada 20 s, la del celular cada 15 s, y
# cada pestaña del navegador que Martin tenga abierta suma la suya. Dos segundos no se
# notan —la lista cambia cuando alguien escribe, no en el medio de un parpadeo— y sacan de
# encima el trabajo repetido (2026-08-18).
_SESIONES_ULTIMA = {"cuando": 0.0, "datos": None}
_SESIONES_VALE_SEG = 2.0


@app.get("/movil/sesiones")
def movil_sesiones():
    """Las pestañas disponibles: cada sesion de Claude Code, viva o guardada.

    ⭐ La sesion de LAURA no se lista. Es la unica que esta viva todo el dia y a la
    que le hablan tres canales a la vez (micrófono, Telegram, panel): abrirla como
    una pestaña mas significa mandarle turnos EN PARALELO a la charla en curso, que
    es justamente lo que la bifurca. Paso el 2026-08-16 — Martin la abrio sin saber
    (Claude le habia puesto un titulo cualquiera), vio su propia charla de Telegram
    adentro de la pestaña y los turnos se pisaron entre si. Para hablarle a Laura
    desde el celular esta la pestaña Hablar y el chat del panel, que van por el
    buzon: un solo canal, sin duplicar nada.
    """
    ahora = time.time()
    if (_SESIONES_ULTIMA["datos"] is not None
            and ahora - _SESIONES_ULTIMA["cuando"] < _SESIONES_VALE_SEG):
        return _SESIONES_ULTIMA["datos"]
    from app.voz import sesiones_movil
    laura = _sesion_de_laura()
    alias = _nombres_sesiones()
    guardadas = _archivadas()
    borradores = _borradores()
    proyectos = sesiones_movil.listar()
    # La fuente de verdad para aceptar otro mensaje es este candado, no solamente el
    # proceso que el listado alcance a detectar. Si difieren durante unos segundos, la
    # pantalla tiene que mostrar el mismo estado que aplicará POST /movil/mandar.
    with _TURNOS_CANDADO:
        ocupadas = set(_TURNOS_ABIERTOS)
    for p in proyectos:
        p["sesiones"] = [s for s in p["sesiones"] if s.get("id") != laura]
        # ⚠ Lo que dejaste a medio escribir en una charla que después se compactó o se
        # mudó de cerebro se muda con vos a la continuación: la fila vieja ya no se
        # dibuja (queda tapada) y ese borrador quedaría escondido para siempre. Va en
        # una pasada aparte para que la chapa aparezca en la fila nueva AHORA y no en
        # el refresco siguiente.
        for s in p["sesiones"]:
            if s.get("tapada") and borradores.get(s["id"]):
                borradores = _mudar_borrador(s["id"], s.get("sigue_en"))
        for s in p["sesiones"]:            # el nombre que le pusiste vos manda
            # Codex deja la verdad del turno en su rollout y en el proceso. Si el
            # candado en memoria se perdio pero ese escritor sigue vivo, la fila y la
            # caja tienen que continuar bloqueadas (capturas 13:52 y 14:00, 2026-08-25).
            s["ocupada"] = (s["id"] in ocupadas
                            or (s.get("cerebro") == "codex" and s.get("viva")))
            if alias.get(s["id"]):
                s["nombre"] = alias[s["id"]]
                s["mio"] = True
            # ⚠ Las archivadas se MARCAN, no se sacan: la pantalla las esconde de la
            # bandeja pero tiene que poder mostrarlas para desarchivarlas.
            if s["id"] in guardadas:
                s["archivada"] = True
            # ⭐ Lo que empezaste a escribirle y no mandaste. Va un ANTICIPO, no el
            # texto entero: esta lista se guarda en el navegador para que la pantalla
            # aparezca dibujada, y un borrador largo la engordaria al pedo. El texto
            # completo lo devuelve `/movil/borradores`.
            b = (borradores.get(s["id"]) or {}).get("texto", "")
            if b.strip():
                s["borrador"] = " ".join(b.split())[:120]
    # ⭐ El orden elegido y las escondidas viajan CON la lista: las pantallas guardan
    # esta respuesta para dibujarse al instante, así que si fueran otro pedido aparte
    # el primer pintado saldría con el orden viejo y saltaría un momento después.
    # ⭐ La IDENTIDAD de cada carpeta (icono, color, apodo) viaja por el mismo camino y por
    # el mismo motivo: es la respuesta que las pantallas guardan para dibujarse al instante,
    # asi que pidiendola aparte el primer pintado saldria sin iconos y aparecerian de golpe
    # un momento despues. Los `choques` NO van: se miran a mano por `GET /carpetas/aspecto`.
    aspecto_carp = _aspecto_carpetas()
    salida = {"proyectos": [p for p in proyectos if p["sesiones"] or p.get("manual")],
              "laura": laura,
              "carpetas": {**_orden_carpetas(),
                           "aspecto": aspecto_carp["carpetas"],
                           "iconosPropios": aspecto_carp["iconosPropios"],
                           # El navegador de base que heredan las carpetas que no dicen
                           # nada: viaja por el mismo camino, para que las dos pantallas
                           # puedan mostrar "por defecto: tal" sin un pedido aparte.
                           "defecto": aspecto_carp["defecto"]}}
    _SESIONES_ULTIMA["datos"] = salida
    _SESIONES_ULTIMA["cuando"] = time.time()
    return salida


def _archivadas():
    """Los ids de las conversaciones que Martin saco de la bandeja."""
    try:
        return set(json.loads(SESIONES_ARCHIVADAS.read_text(encoding="utf-8")))
    except Exception:
        return set()


# --- El orden de las carpetas de la barra lateral, y cuales estan escondidas ------
# Pedido de Martin (2026-08-18): "quiero poder mover las carpetas y sacarlas de aca".
# ⚠⚠ ESCONDER NO BORRA. No se toca la carpeta del disco, ni sus conversaciones, ni la
# entrada de `carpetas_sesiones.json`: es una lista de nombres que la pantalla saltea,
# igual que `sesiones_archivadas.json` con las charlas. Siempre se puede devolver.
# ⭐ Vive en el SERVIDOR, no en el navegador: la misma lista de proyectos esta en el
# cajon del celular, y un orden guardado en una sola pantalla dejaria a la otra
# mostrando cualquier cosa.

def _orden_carpetas():
    """{"orden": [nombres, en el orden elegido], "ocultas": [nombres]}."""
    try:
        d = json.loads(ORDEN_CARPETAS.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    orden = [x for x in (d.get("orden") or []) if isinstance(x, str)]
    ocultas = [x for x in (d.get("ocultas") or []) if isinstance(x, str)]
    return {"orden": orden, "ocultas": ocultas}


def _guardar_orden_carpetas(orden, ocultas):
    ORDEN_CARPETAS.write_text(
        json.dumps({"orden": orden, "ocultas": sorted(set(ocultas))},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    _SESIONES_ULTIMA["datos"] = None      # que la lista se rehaga ya, sin esperar el cache


@app.get("/carpetas/orden")
def carpetas_orden_leer():
    return {"ok": True, **_orden_carpetas()}


@app.post("/carpetas/orden")
async def carpetas_orden_guardar(request: Request):
    """El orden nuevo de la barra lateral, tal como quedo despues de arrastrar.

    Se guarda la lista COMPLETA de nombres en su orden. Un proyecto que aparezca
    despues (una carpeta nueva con conversaciones) no esta en la lista y la pantalla
    lo pone al final: no hay que reescribir esto cada vez que nace un proyecto.
    """
    d = await request.json()
    orden = d.get("orden")
    if not isinstance(orden, list) or not all(isinstance(x, str) for x in orden):
        return {"ok": False, "error": "el orden tiene que ser una lista de nombres"}
    _guardar_orden_carpetas(orden[:500], _orden_carpetas()["ocultas"])
    return {"ok": True}


@app.post("/carpetas/ocultar")
async def carpetas_ocultar(request: Request):
    """Sacar una carpeta de la barra lateral, o devolverla.

    ⚠⚠ No borra NADA: ni la carpeta, ni sus conversaciones, ni la entrada de
    `carpetas_sesiones.json`. Solo deja de mostrarse, y se puede devolver.
    """
    d = await request.json()
    nombre = (d.get("proyecto") or "").strip()
    if not nombre:
        return {"ok": False, "error": "falta la carpeta"}
    e = _orden_carpetas()
    ocultas = set(e["ocultas"])
    ocultas.add(nombre) if d.get("ocultar", True) else ocultas.discard(nombre)
    _guardar_orden_carpetas(e["orden"], ocultas)
    return {"ok": True, "ocultas": sorted(ocultas)}


# --- La identidad visual de cada carpeta: icono, color y apodo --------------------
# ⭐⭐ Por que esto vive ACA y no en el navegador (2026-08-25, pedido de Martin: "que no
# importa si abro desde el celular, la app de escritorio o desde otro navegador, siempre
# tengan estos iconos"). Habia DOS juegos y los dos guardados por navegador: `sesIconos`,
# `sesTonos`, `sesApodos` y `sesIconosPropios` en `/sesiones`, y `movilAspectoCarpetas` en
# `MOVIL_HTML`, cada uno con su propia paleta de emojis. Resultado: los iconos que armo a
# mano existian en UN Chrome de UNA maquina y en ningun otro lado.
# ⚠ El comentario viejo de `INTERFAZ.md` decia que el color es "como se ve esta pantalla" y
# por eso podia quedarse en el navegador. Estaba equivocado y el pedido lo corrige: la
# identidad es del PROYECTO, igual que su orden en la lista.
_ASPECTO_CARP_CANDADO = threading.Lock()
# ⭐ `navegador` y `sitios` (2026-08-28) viajan por ACA y no por un archivo propio: son
# propiedades del PROYECTO, igual que su icono y su color, y este endpoint ya manda solo
# el campo tocado — o sea que el celular puede cambiar el navegador sin borrarle a la
# compu el icono que acabas de poner. `navegador` es la ruta del perfil de Chrome que usa
# esa carpeta (vacio = esa carpeta no tiene navegador y sus sesiones no lo pueden usar) y
# `sitios` es la lista OPCIONAL de dominios a los que puede entrar, separados por coma.
CARP_CAMPOS = ("icono", "color", "apodo", "navegador", "sitios")
CARP_MAX_LARGO = {"icono": 16, "color": 40, "apodo": 80,
                  "navegador": 260, "sitios": 400}
# ⭐ Lo que una carpeta pone en `navegador` para NO heredar el de base. No es una ruta:
# es la unica forma de distinguir "apagalo aca" de "no dije nada, que herede".
SIN_NAVEGADOR = "ninguno"
CARP_MAX = 500          # carpetas con identidad propia; es una barra lateral, no una base
ICONOS_PROPIOS_MAX = 300


def _carp_limpiar(valor, campo):
    """Un campo del menu de carpeta, o "" si no sirve. Todo lo que entra pasa por aca.

    ⚠ Aca NO se toca el disco: esta funcion corre tambien al LEER el archivo, y si
    chequeara que el perfil exista, desenchufar un disco o renombrar una carpeta le
    borraria a Martin la configuracion sin decirle nada. Que el perfil exista se
    comprueba al GUARDAR, en `_aspecto_aplicar`, que es cuando hay a quien avisarle.
    """
    if not isinstance(valor, str):
        return ""
    v = valor.strip()
    if campo == "sitios":
        # "Ejemplo.web.app, LOCALHOST" -> "ejemplo.web.app, localhost". Se normaliza
        # al entrar y no al comparar: asi el portero de `sesiones_movil` compara texto
        # contra texto, sin volver a limpiar de su lado y sin poder discrepar.
        vistos, dominios = set(), []
        for d in re.split(r"[,\s;]+", v.lower()):
            d = d.strip().strip("/")
            d = re.sub(r"^https?://", "", d)
            if d and d not in vistos:
                vistos.add(d)
                dominios.append(d)
        v = ", ".join(dominios)
    return v[:CARP_MAX_LARGO[campo]]


def _perfil_chrome_ok(ruta):
    """¿Esa ruta es de verdad un perfil de Chrome?

    Valen las DOS formas, y la segunda no es un detalle (2026-08-28): una carpeta de
    datos propia (tiene `Local State` o `Default` adentro) o un perfil INTERNO de Chrome
    (`...\\User Data\\Profile 9`, que tiene su `Preferences` al lado). Martin tiene un
    perfil por agencia y son internos: sin esto no se pueden elegir, y el perfil es
    justo la frontera entre agencias que no se cruzan.

    Sin esta guarda, un perfil mal tipeado abriria un Chrome LIMPIO, sin la extension
    de Claude puesta, y la sesion quedaria diciendo "no encuentro el navegador" sin que
    se entienda por que.
    """
    try:
        p = Path(ruta)
        return p.is_dir() and ((p / "Local State").exists() or (p / "Default").is_dir()
                               or (p / "Preferences").exists())
    except Exception:
        return False


def _aspecto_carpetas():
    """{"carpetas": {nombre: {icono, color, apodo}}, "iconosPropios": [...], "choques": [...]}."""
    try:
        d = json.loads(ASPECTO_CARPETAS.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    carpetas = {}
    for nombre, a in (d.get("carpetas") or {}).items():
        if not isinstance(nombre, str) or not isinstance(a, dict):
            continue
        limpio = {c: _carp_limpiar(a.get(c), c) for c in CARP_CAMPOS}
        limpio = {c: v for c, v in limpio.items() if v}
        if limpio:
            carpetas[nombre] = limpio
    propios = [x for x in (d.get("iconosPropios") or [])
               if isinstance(x, str) and x.strip()][:ICONOS_PROPIOS_MAX]
    choques = [x for x in (d.get("choques") or []) if isinstance(x, dict)]
    # ⭐ El navegador POR DEFECTO (2026-08-28): lo que hereda cualquier carpeta que no
    # diga nada. Sin esto habia que marcar las 23 carpetas a mano y las nuevas nacian
    # sin nada. Una carpeta lo pisa poniendo otro perfil, o lo apaga con "ninguno".
    dd = d.get("defecto") if isinstance(d.get("defecto"), dict) else {}
    defecto = {c: _carp_limpiar(dd.get(c), c) for c in ("navegador", "sitios")}
    return {"carpetas": carpetas, "iconosPropios": propios, "choques": choques,
            "defecto": {c: v for c, v in defecto.items() if v}}


def _guardar_aspecto_carpetas(e):
    ASPECTO_CARPETAS.write_text(json.dumps(e, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    # Que la lista se rehaga ya: el aspecto viaja adentro de `/movil/sesiones`, que tiene
    # cache de 1,5 s, y sin esto el cambio recien se veria en la otra pantalla al rato.
    _SESIONES_ULTIMA["datos"] = None


@app.get("/carpetas/aspecto")
def carpetas_aspecto_leer():
    return {"ok": True, **_aspecto_carpetas()}


@app.post("/carpetas/aspecto")
async def carpetas_aspecto_guardar(request: Request):
    return _aspecto_aplicar(await request.json())


# ⚠ La logica va aparte del endpoint (y sin `async`) a proposito: asi la puede llamar
# derecho una prueba, sin levantar uvicorn ni fabricar un Request. Lo mismo con sembrar.
def _aspecto_aplicar(d):
    """Un cambio puntual del menu de una carpeta: {carpeta, icono?, color?, apodo?}.

    Solo viajan los campos que MANDASTE, y un campo en "" lo borra (volver al de
    siempre). Asi dos pantallas abiertas a la vez no se pisan lo que la otra eligio:
    cambiar el color en el celular no puede borrarte el icono que pusiste en la compu.
    Aparte, {iconosPropios: [...]} reemplaza el juego de iconos agregados a mano.
    """
    if not isinstance(d, dict):
        return {"ok": False, "error": "formato raro"}
    with _ASPECTO_CARP_CANDADO:
        e = _aspecto_carpetas()
        # ⭐ El navegador de base para TODAS las carpetas. Viaja igual que el resto: solo
        # el campo que tocaste, y en "" se borra (o sea, se vuelve a "ninguno heredado").
        if isinstance(d.get("defecto"), dict):
            base = dict(e.get("defecto") or {})
            for campo in ("navegador", "sitios"):
                if campo not in d["defecto"]:
                    continue
                valor = _carp_limpiar(d["defecto"].get(campo), campo)
                if campo == "navegador" and valor and not _perfil_chrome_ok(valor):
                    return {"ok": False,
                            "error": "esa carpeta no parece un perfil de Chrome"}
                base[campo] = valor
                if not valor:
                    base.pop(campo, None)
            e["defecto"] = base
        if isinstance(d.get("iconosPropios"), list):
            vistos, propios = set(), []
            for x in d["iconosPropios"]:
                if isinstance(x, str) and x.strip() and x not in vistos:
                    vistos.add(x)
                    propios.append(x.strip()[:CARP_MAX_LARGO["icono"]])
            e["iconosPropios"] = propios[:ICONOS_PROPIOS_MAX]
        nombre = (d.get("carpeta") or "").strip()
        if nombre:
            actual = dict(e["carpetas"].get(nombre) or {})
            for campo in CARP_CAMPOS:
                if campo not in d:
                    continue                      # lo que no mandaste queda como estaba
                valor = _carp_limpiar(d.get(campo), campo)
                # ⚠ El perfil se comprueba al GUARDAR y se rechaza el pedido entero: es
                # el unico momento en que hay una pantalla esperando para avisarle a
                # Martin que esa carpeta no existe.
                # ⚠ `ninguno` es el "apagalo para ESTA carpeta": no es una ruta, es la
                # forma de decir que no herede el navegador de base. Vacio es otra cosa
                # —"no dije nada, que herede"—, y por eso hacen falta los dos valores.
                if (campo == "navegador" and valor and valor != SIN_NAVEGADOR
                        and not _perfil_chrome_ok(valor)):
                    return {"ok": False,
                            "error": "esa carpeta no parece un perfil de Chrome"}
                actual[campo] = valor
                if not valor:
                    actual.pop(campo, None)       # "" = sacarlo, volver al de siempre
            if actual:
                e["carpetas"][nombre] = actual
            else:
                e["carpetas"].pop(nombre, None)
            if len(e["carpetas"]) > CARP_MAX:
                return {"ok": False, "error": "demasiadas carpetas con identidad propia"}
        _guardar_aspecto_carpetas(e)
    return {"ok": True}


@app.get("/carpetas/navegadores")
def carpetas_navegadores():
    """Los perfiles de Chrome que hay en el disco, para llenar el selector de la carpeta.

    ⚠ El panel NO puede preguntarle al puente de Claude in Chrome que navegadores hay
    conectados: no es un cliente MCP, y el puente vive adentro del proceso `claude`. Asi
    que esto es lo que hay en el disco, que es justo lo que hace falta para poder ABRIR
    el navegador de un proyecto.
    """
    from app.voz import sesiones_movil
    perfiles = []
    vistos = set()

    def sumar(ruta, nombre, personal=False):
        r = str(ruta)
        if r in vistos or not _perfil_chrome_ok(r):
            return
        vistos.add(r)
        # ⭐ `conectado` sale de leer el `bridgeDeviceId` que la extension guarda ADENTRO
        # del perfil: es la unica forma de saber, sin gastar un token, si ese Chrome ya
        # se presento al puente. Sin eso la sesion no sabe cual de los navegadores
        # conectados es el suyo, y elegir mal significa trabajar sobre el que tiene el
        # banco abierto.
        perfiles.append({"ruta": r, "nombre": nombre, "personal": personal,
                         "conectado": bool(sesiones_movil.id_navegador_de(r))})

    # El de todos los dias va PRIMERO pero marcado: es el que tiene todo logueado, y esa
    # marca es lo que la pantalla usa para avisar que ahi adentro estan todas sus cuentas.
    sumar(PERFIL_CHROME_PERSONAL, "El Chrome de siempre", personal=True)
    # ⭐⭐ Los perfiles INTERNOS de Chrome (2026-08-28). Martin tiene uno por trabajo
    # y NO son carpetas de datos aparte: cuelgan de la del personal. El perfil es la
    # frontera entre trabajos, que no se cruzan, asi que tienen que poder elegirse. El nombre sale del `Local State`, que es
    # el que Chrome muestra en su selector: "Profile 9" no le dice nada a nadie.
    try:
        ls = json.loads((PERFIL_CHROME_PERSONAL / "Local State").read_text(
            encoding="utf-8", errors="replace"))
        for carpeta, info in ((ls.get("profile") or {}).get("info_cache") or {}).items():
            if carpeta == "Default":
                continue                      # ese ya entro arriba, como "el de siempre"
            sumar(PERFIL_CHROME_PERSONAL / carpeta,
                  (info.get("name") or carpeta) + " (perfil de Chrome)")
    except Exception as e:
        print("carpetas: no pude leer los perfiles internos de Chrome:", e, flush=True)
    try:
        for hijo in sorted(PERFILES_CHROME.iterdir()):
            if hijo.is_dir() and hijo.name.lower().startswith("chrome"):
                sumar(hijo, hijo.name)
    except Exception as e:
        print("carpetas: no pude listar los perfiles de Chrome:", e, flush=True)
    return {"ok": True, "perfiles": perfiles}


@app.post("/carpetas/aspecto/sembrar")
async def carpetas_aspecto_sembrar(request: Request):
    return _aspecto_sembrar(await request.json())


def _aspecto_sembrar(d):
    """Subir de una vez lo que un navegador YA tenia guardado, sin perder nada.

    ⭐⭐ Esta es la mitad delicada del cambio del 2026-08-25. Martin lo pidio con todas
    las letras: *"porfa no pierdas lo que ya tengo porque tardé mucho en ponerlos"*. Los
    iconos existian solo en el `localStorage` de su Chrome; si el servidor arranca vacio y
    las pantallas se ponen a leer de aca, ese trabajo desaparece de la vista.

    Tres reglas, y las tres son a proposito:
    1. **No pisa nunca.** Una carpeta que ya tiene algo guardado se respeta. Sembrar es
       traer lo que falta, no imponer.
    2. **Lo que no coincide no se decide sola**: queda anotado en `choques` para que Martin
       elija (lo eligio asi cuando se le pregunto: "mostrame los choques primero"). Mientras
       tanto sigue viendose lo que ya estaba guardado.
    3. **Copia con fecha en `logs/`** de todo lo que manda cada navegador, antes de mezclar
       nada. Si la mezcla sale mal, el original esta entero en un archivo.
    """
    if not isinstance(d, dict):
        return {"ok": False, "error": "formato raro"}
    origen = (d.get("origen") or "?").strip()[:20]
    entra = d.get("carpetas") if isinstance(d.get("carpetas"), dict) else {}
    propios = [x for x in (d.get("iconosPropios") or []) if isinstance(x, str) and x.strip()]
    if not entra and not propios:
        return {"ok": True, "sembradas": 0, "choques": 0}   # navegador nuevo, nada que traer

    marca = time.strftime("%Y%m%d-%H%M%S")
    try:
        (LOGS / f"aspecto_carpetas_{origen}_{marca}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass          # el respaldo es una red, no una condicion: si falla igual seguimos

    nuevas = 0
    with _ASPECTO_CARP_CANDADO:
        e = _aspecto_carpetas()
        for nombre, a in entra.items():
            if not isinstance(nombre, str) or not isinstance(a, dict):
                continue
            actual = dict(e["carpetas"].get(nombre) or {})
            for campo in CARP_CAMPOS:
                valor = _carp_limpiar(a.get(campo), campo)
                if not valor:
                    continue
                if not actual.get(campo):
                    actual[campo] = valor         # estaba vacio: se llena, sin discutir
                    nuevas += 1
                elif actual[campo] != valor:
                    e["choques"].append({"carpeta": nombre, "campo": campo,
                                         "guardado": actual[campo], "llego": valor,
                                         "origen": origen, "cuando": marca})
            if actual:
                e["carpetas"][nombre] = actual
        for x in propios:                          # el juego de iconos se SUMA, no se pisa
            x = x.strip()[:CARP_MAX_LARGO["icono"]]
            if x not in e["iconosPropios"]:
                e["iconosPropios"].append(x)
        e["iconosPropios"] = e["iconosPropios"][:ICONOS_PROPIOS_MAX]
        e["choques"] = e["choques"][-200:]
        _guardar_aspecto_carpetas(e)
    return {"ok": True, "sembradas": nuevas, "choques": len(e["choques"])}


@app.post("/movil/archivar")
async def movil_archivar(request: Request):
    """Sacar (o volver a traer) una conversación de la bandeja.

    No borra ni toca NADA de Claude Code: se guarda una lista de ids y la pantalla
    las esconde. Vive en el servidor para que archivar desde la compu también las
    saque del celular (pedido de Martín, 2026-08-17).
    """
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "falta la sesión"}
    guardadas = _archivadas()
    guardadas.add(sid) if d.get("archivar", True) else guardadas.discard(sid)
    SESIONES_ARCHIVADAS.write_text(json.dumps(sorted(guardadas), indent=1), encoding="utf-8")
    _SESIONES_ULTIMA["datos"] = None      # que la lista se rehaga ya, sin esperar el cache
    return {"ok": True, "archivadas": len(guardadas)}


# --- El BORRADOR de cada conversacion -----------------------------------------
# Pedido de Martin (2026-08-18): "quiero que lo que yo escriba dentro de una sesion quede
# guardado como borrador y se pueda ver en TODAS, con una señalizacion que diga que esta
# en borrador, con un color y una animacion". Es el borrador del correo: escribis media
# frase, te vas, y la conversacion queda marcada en la bandeja hasta que la mandes.
#
# ⭐ Vive en el SERVIDOR y no en el navegador, por lo mismo que las marcas y el modelo:
# es la MISMA conversacion en la compu y en el telefono. Empezas a escribir en la compu,
# agarras el celular y el borrador esta ahi.
# ⚠ Nada de esto toca los archivos de Claude Code: es una capa nuestra al costado. Un
# borrador NO es un mensaje mandado — mientras vive aca, la sesion ni se entera.
BORRADOR_MAX = 20_000        # letras por conversacion; es una caja de texto, no un archivo


def _borradores():
    try:
        d = json.loads(BORRADORES_SESIONES.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _guardar_borrador(sid, texto):
    """Guarda (o borra, si quedo vacio) el borrador de una conversacion.

    Devuelve el mapa completo ya guardado. ⚠ Vacio = BORRAR la entrada, no guardar una
    cadena vacia: si no, toda conversacion en la que alguna vez escribiste algo quedaba
    con la chapa de borrador puesta para siempre.
    """
    todos = _borradores()
    texto = (texto or "")[:BORRADOR_MAX]
    if texto.strip():
        todos[sid] = {"texto": texto, "ts": time.time()}
    else:
        todos.pop(sid, None)
    BORRADORES_SESIONES.write_text(json.dumps(todos, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    # Que la bandeja se entere YA: la lista se cachea 2 s y la chapa tiene que
    # aparecer mientras escribis, no dos segundos despues.
    _SESIONES_ULTIMA["datos"] = None
    return todos


def _mudar_borrador(viejo, nuevo):
    """Pasa el borrador de una charla tapada a la que la continúa. Devuelve el mapa.

    ⚠ Si la continuación ya tiene algo escrito, el suyo manda y el viejo se descarta:
    pegarlos uno atrás del otro te dejaría un mensaje mezclado sin que lo pidas.
    Pedido del 2026-08-21, al tapar las charlas compactadas: el borrador vivía en la
    fila que dejó de dibujarse.
    """
    todos = _borradores()
    b = todos.pop(viejo, None)
    if not b:
        return todos
    if nuevo and not (todos.get(nuevo) or {}).get("texto", "").strip():
        todos[nuevo] = b
    try:
        BORRADORES_SESIONES.write_text(json.dumps(todos, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    except Exception as e:
        print("no pude mudar el borrador de la charla compactada:", e, flush=True)
    return todos


@app.get("/movil/borradores")
def movil_borradores():
    """Todos los borradores: `{sid: {texto, ts}}`.

    Va aparte de `/movil/sesiones` a proposito: esa lista esta TOPEADA (20 proyectos, 20
    charlas de cada uno, ultimo mes) porque es para elegir a ojo, y un borrador tiene que
    poder devolverse aunque lo hayas escrito en una charla vieja que ya no figura ahi.
    """
    return _borradores()


@app.post("/movil/borrador")
async def movil_borrador(request: Request):
    """Guardar lo que escribiste y no mandaste (o borrarlo, mandando vacio)."""
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "falta la sesión"}
    # ⚠ Una pestaña sin estrenar tiene un id provisorio (`nueva-…`) que no significa nada
    # en otra pantalla ni mañana: ese borrador se queda en el navegador donde lo escribiste.
    if sid.startswith("nueva-"):
        return {"ok": False, "error": "la conversación todavía no tiene id propio"}
    todos = _guardar_borrador(sid, d.get("texto") or "")
    return {"ok": True, "hay": sid in todos, "cuantos": len(todos)}


# --- El marcador de texto de las conversaciones -------------------------------
# Pedido de Martin (2026-08-17): "poder pintar o subrayar el texto de las conversaciones
# seleccionandolo, apretando clic derecho, con varios colores, varias formas y opacidad".
# ⭐ Se guarda en el SERVIDOR y no en el navegador porque la misma conversacion se ve en
# la compu y en el telefono: con las marcas guardadas en una pantalla, la otra la mostraba
# sin pintar. El telefono hoy las MUESTRA; pintar desde ahi es la vuelta siguiente.
# ⚠ Nada de esto toca los archivos de Claude Code: es una capa nuestra al costado.
MARCAS_MAX = 400        # por conversacion; es un marcador, no un archivo de datos


def _marcas():
    try:
        d = json.loads(MARCAS_CHAT.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _guardar_marcas(todas):
    MARCAS_CHAT.write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")


@app.get("/marcas")
def marcas_de(sid: str = ""):
    """Las marcas de una conversación (o de varias, separadas por coma)."""
    todas = _marcas()
    pedidas = [s.strip() for s in sid.split(",") if s.strip()]
    return {"marcas": {s: todas.get(s, []) for s in pedidas}}


@app.post("/marcas/poner")
async def marcas_poner(request: Request):
    """Pintar un pedazo de un mensaje.

    La marca dice en qué mensaje va (`msg`, su posición en la charla), desde y hasta
    qué letra (`ini`/`fin`, contadas sobre el texto pelado del mensaje), de qué color y
    de qué forma. ⚠ Se guarda además el TEXTO marcado: si el mensaje cambió, la pantalla
    prefiere no pintar nada antes que pintar el pedazo equivocado.
    """
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    try:
        msg, ini, fin = int(d.get("msg")), int(d.get("ini")), int(d.get("fin"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "faltan las posiciones"}
    if not sid or fin <= ini:
        return {"ok": False, "error": "no hay nada seleccionado"}
    todas = _marcas()
    ident = (d.get("id") or "").strip() or f"m{int(time.time()*1000)}"
    lista = [m for m in todas.get(sid, [])
             # Volver a pintar lo mismo REEMPLAZA en vez de apilar: si no, cambiar de
             # color dejaba las dos marcas encimadas y la vieja asomaba por abajo.
             # Y por `id` tambien: asi la pantalla puede volver a anclar una marca que se
             # corrio de lugar (mandandola con su mismo id) sin dejar la vieja duplicada.
             if m.get("id") != ident
             and not (m.get("msg") == msg and m.get("ini") == ini and m.get("fin") == fin)]
    lista.append({"id": ident,
                  "msg": msg, "ini": ini, "fin": fin,
                  # La firma del texto del mensaje: es lo que permite reencontrarlo cuando
                  # el hilo se corre (el chat trae solo los ultimos 40 mensajes).
                  "firma": (d.get("firma") or "")[:40],
                  "color": (d.get("color") or "amarillo")[:20],
                  "forma": (d.get("forma") or "resaltado")[:20],
                  "op": max(0.1, min(1.0, float(d.get("op") or 0.4))),
                  "texto": (d.get("texto") or "")[:300]})
    todas[sid] = lista[-MARCAS_MAX:]
    _guardar_marcas(todas)
    return {"ok": True, "marcas": todas[sid]}


@app.post("/marcas/quitar")
async def marcas_quitar(request: Request):
    """Sacar una marca (o todas las de la conversación, con `todas`)."""
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "falta la sesión"}
    todas = _marcas()
    if d.get("todas"):
        todas.pop(sid, None)
    else:
        ident = (d.get("id") or "").strip()
        todas[sid] = [m for m in todas.get(sid, []) if m.get("id") != ident]
    _guardar_marcas(todas)
    return {"ok": True, "marcas": todas.get(sid, [])}


def _script_powershell(cmd):
    """El scriptcito que se le da a la ventana: PRIMERO muestra el comando, despues lo corre.

    ⭐ Mostrarlo no es decoracion (pedido de Martin, 2026-08-18: *"quiero ver como se
    imprime y se ejecuta el comando"*). Con `-EncodedCommand`, PowerShell ejecuta y no
    muestra nada: se abria una ventana donde aparecia la salida de algo que no se veia que
    fuera. Ahora arriba queda el comando en celeste, como si lo hubieras tipeado vos, y
    debajo su salida — que es lo que uno espera de una terminal.

    ⚠ El comando se mete como texto entre comillas SIMPLES, doblando las que traiga adentro:
    en PowerShell una cadena con comillas simples no interpreta nada de lo que hay adentro
    (ni `$variables`, ni comillas dobles, ni acentos graves) y puede ocupar varios renglones.
    Es lo que permite mostrar y correr el mismo texto sin escaparlo dos veces distintas.
    """
    literal = "'" + (cmd or "").replace("'", "''") + "'"
    return (
        "$Host.UI.RawUI.WindowTitle = 'Servidor IA - comando del panel'\n"
        "$__cmd = " + literal + "\n"
        "Write-Host ''\n"
        "$__cmd -split \"`r?`n\" | ForEach-Object { Write-Host ('PS> ' + $_) -ForegroundColor Cyan }\n"
        "Write-Host ''\n"
        "Invoke-Expression $__cmd\n"
    )


@app.post("/correr")
async def correr_en_powershell(request: Request):
    """Abrir una ventana de PowerShell y correr el comando de un bloque de codigo.

    Pedido de Martin (2026-08-18): los bloques de codigo de las conversaciones tienen dos
    botones, copiar y correr, "tal y como se puede hacer con Claude Code". El de correr
    llega aca.

    ⭐ **Ventana NUEVA y visible, con `-NoExit`**: casi todo lo que Martin corre asi es
    levantar un servidor o un script largo, o sea algo que tiene que quedar prendido y
    mostrando su salida. Corriendolo escondido no veria ni el error ni la direccion que
    imprime, y matarlo despues seria a ciegas. La ventana es suya: la cierra cuando quiera.

    ⚠ El script viaja en `-EncodedCommand` (base64 de UTF-16LE, que es como PowerShell
    espera que se le pase un script desde afuera) y no como texto en la linea de comando:
    asi no hay nada que escapar y un comando de varios renglones, con comillas o con
    tildes, llega tal cual. Con `-Command` a secas los saltos de linea y las comillas se
    rompen de maneras dificiles de ver.

    ⚠ **Esto corre lo que le manden en la maquina de Martin.** No hay lista blanca a
    proposito: es un boton para SU panel, en su LAN/Tailscale, y desde el mismo panel ya se
    le puede hablar a una sesion de Claude Code con `dontAsk`, que puede bastante mas. La
    pantalla pide dos toques antes de llamar aca, y todo lo que se corre queda anotado en
    `logs/correr.log` con la fecha, para poder mirar despues que se ejecuto.
    """
    d = await request.json()
    cmd = (d.get("cmd") or "").strip()
    if not cmd:
        return {"ok": False, "error": "no hay comando"}
    if len(cmd) > 8000:
        return {"ok": False, "error": "comando demasiado largo"}
    pedida = (d.get("cwd") or "").strip()
    try:
        carpeta = pedida if pedida and Path(pedida).is_dir() else str(RAIZ)
    except OSError:
        carpeta = str(RAIZ)
    try:
        b64 = base64.b64encode(_script_powershell(cmd).encode("utf-16-le")).decode("ascii")
        subprocess.Popen(["powershell", "-NoExit", "-EncodedCommand", b64],
                         cwd=carpeta,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except Exception as e:
        return {"ok": False, "error": f"no pude abrirlo: {e}"}
    try:
        with open(LOGS / "correr.log", "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} en {carpeta}\n{cmd}\n")
    except Exception:
        pass                                  # el registro no puede voltear el comando
    return {"ok": True}


def _nombres_sesiones():
    try:
        return json.loads(NOMBRES_SESIONES.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.post("/movil/nombre")
async def movil_nombre(request: Request):
    """Ponerle un nombre propio a una sesion, desde el celular.

    Es un alias NUESTRO, guardado aparte: el titulo que Claude le pone a la charla
    vive adentro de sus archivos y no se toca. Nombre vacio = volver al de Claude.
    """
    d = await request.json()
    sid, nombre = (d.get("sid") or "").strip(), (d.get("nombre") or "").strip()[:60]
    if not sid:
        return {"ok": False, "error": "falta la sesión"}
    alias = _nombres_sesiones()
    if nombre:
        alias[sid] = nombre
    else:
        alias.pop(sid, None)
    NOMBRES_SESIONES.write_text(json.dumps(alias, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    _SESIONES_ULTIMA["datos"] = None      # el nombre nuevo tiene que verse en el acto
    return {"ok": True, "nombre": nombre}


@app.get("/movil/chat")
def movil_chat(cwd: str, sid: str, ultimos: int = 40):
    """La conversacion de una sesion, leida de su archivo (por eso va EN VIVO:
    si Martin le esta hablando desde la compu, esto lo ve aparecer igual)."""
    from app.voz import sesiones_movil
    mensajes = sesiones_movil.conversacion(cwd, sid, ultimos)
    for m in mensajes:
        # La marca interna ("[Te paso una imagen... abrila con Read]") es para Claude,
        # no para tus ojos: se saca del texto y la foto se manda aparte para dibujarla
        # en la burbuja. Mismo tratamiento que en el chat del panel.
        texto, nombres = _partir_imagen(m.get("texto") or "")
        if not nombres:
            continue
        servibles = [n for n in nombres if (IMAGENES_CHAT / n).exists()]
        m["texto"] = texto if servibles else ("📎 " + texto).strip()
        if servibles:
            m["imgs"] = [f"/chat/imagen/{n}" for n in servibles]
    # ⭐ La pregunta con opciones (AskUserQuestion) que la sesion tenga pendiente viaja
    # junto con el chat: la pantalla ya pide esto cada 3 s, asi que no es un pedido mas.
    # La contesta POST /movil/responder (2026-08-18).
    with _TURNOS_CANDADO:
        ocupada = sid in _TURNOS_ABIERTOS
    if not ocupada:
        ocupada = _codex_turno_realmente_activo(sid)
    # ⭐ Si al turno que corre ahora ya le pediste aviso, tiene que VERSE encendido en
    # cualquier pantalla y sobrevivir a un F5: el estado vive en la ficha del trabajo,
    # no en la memoria del navegador que apretó el botón (2026-08-29).
    with _TRABAJOS_CANDADO:
        vivo, _ = _trabajos_de_sesion(sid)
        avisando = bool(vivo and vivo.get("avisar"))
    return {"mensajes": mensajes, "ocupada": ocupada, "avisando": avisando,
            # La pregunta no puede vivir sólo en la respuesta del POST que terminó el
            # turno: al recargar, cambiar de dispositivo o volver más tarde se perdía.
            # Derivarla acá la hace persistente; las pantallas ya consultan este chat.
            "pide_compactar": sesiones_movil.pide_compactar(cwd, sid),
            "pregunta": sesiones_movil.pregunta_de(cwd, sid),
            # ⭐ La lista de tareas que la sesion va tildando (TodoWrite), para
            # dibujarla en vivo en el hilo (2026-08-20).
            "tareas": sesiones_movil.tareas_de(cwd, sid)}


@app.get("/movil/donde")
def movil_donde(sid: str = ""):
    """En que carpeta vive una conversacion, sabiendo solo su id.

    ⭐ Es lo que sostiene las direcciones web de cada conversacion (`/sesiones?c=<id>`,
    `/movil?c=<id>`, pedido de Martin del 2026-08-18): en la direccion va el id pelado,
    asi que al entrar de cero — un favorito, una pestaña nueva, otra computadora — la
    pantalla tiene que averiguar la carpeta antes de poder leer la charla.

    Va derecho al archivo del disco y no a la lista de `/movil/sesiones`, que esta
    topeada al ultimo mes: un favorito sirve justamente para volver a algo viejo.
    """
    from app.voz import sesiones_movil
    d = sesiones_movil.donde(sid)
    if not d:
        return {"ok": False}
    # ⚠ El nombre que se muestra es el ALIAS si Martin le puso uno, igual que en la
    # lista: si no, entrando por la direccion la pestaña aparecia con el titulo que le
    # habia puesto Claude y la MISMA charla se llamaba distinto segun por donde entraras.
    d["nombre"] = _nombres_sesiones().get(sid) or d["nombre"]
    return {"ok": True, **d}


_TURNOS_ABIERTOS = set()      # sesiones con un turno corriendo ahora mismo
_TURNOS_CANDADO = threading.Lock()


def _codex_turno_realmente_activo(sid):
    """La segunda fuente de verdad cuando el candado del panel quedo viejo.

    Codex protege cada hilo con un solo escritor. El 2026-08-25 quedo un proceso real
    trabajando mientras `_TURNOS_ABIERTOS` ya no tenia su id: el celular habilito otro
    envio y el propio CLI tuvo que rechazarlo con `thread-store conflict`. El rollout
    (`task_started` sin cierre) mas el proceso vivo son una prueba mas fuerte que este
    set en memoria; `sesiones_movil` ya sabe medir exactamente esas dos cosas.
    """
    if not sid:
        return False
    try:
        from app.voz import sesiones_movil
        return (sesiones_movil.es_codex(sid)
                and sesiones_movil._codex_turno_activo(sid))
    except Exception:
        return False

# Los trabajos largos no dependen de que el navegador mantenga abierto el pedido HTTP.
# El proceso sigue siendo el mismo de sesiones_movil (y por eso el boton Parar funciona),
# pero el resultado queda aca para que el telefono lo recoja aunque se haya recargado.
_TRABAJOS_MOVIL = {}
_TRABAJOS_CANDADO = threading.Lock()


def _trabajo_publico(t):
    return {k: t.get(k) for k in ("id", "estado", "cwd", "sid", "sid_nuevo", "respuesta",
                                  "error", "aviso", "pide_compactar", "cerebro",
                                  "modelo", "esfuerzo", "velocidad", "ruteo",
                                  "avisar", "creado", "terminado")}


def _ejecutar_turno_movil(cwd, sid, texto, cerebro="", esfuerzo="", modelo="",
                           velocidad="", al_nacer=None):
    """Parte bloqueante comun al envio normal y al trabajo en segundo plano.

    ⭐ `al_nacer` se llama con el id de una charla NUEVA apenas el CLI lo anuncia, sin
    esperar a que termine el turno: es lo que le deja a la pantalla leer el hilo en vivo
    desde el primer mensaje (2026-08-23). De paso, el id recien nacido entra al candado
    de turnos abiertos, asi un segundo envio a esa misma charla se rebota como en
    cualquier otra en vez de partirla al medio.
    """
    from app.voz import sesiones_movil
    nacido = ""

    def _nacio(sid_real):
        nonlocal nacido
        nacido = sid_real
        with _TURNOS_CANDADO:
            _TURNOS_ABIERTOS.add(sid_real)
        if al_nacer:
            al_nacer(sid_real)

    # ⭐ Si la pestaña quedo apuntando a una charla que ya sigue en otra (compactada o
    # mudada de cerebro), el turno va derecho a la continuacion. Sin esto, un celular
    # sin recargar le seguia escribiendo a la vieja y el tope la volvia a compactar:
    # dos continuaciones del mismo tronco y dos turnos carisimos (logs del 2026-08-20).
    sid_usar = sesiones_movil.resolver_continuacion(sid) if sid else sid
    ruteo = ""
    try:
        if sid_usar != sid:
            with _TURNOS_CANDADO:
                _TURNOS_ABIERTOS.add(sid_usar)
        cerebro_usar = cerebro
        esfuerzo_usar = esfuerzo
        if not sid_usar and cerebro == "auto":
            cerebro_usar, esfuerzo_usar, motivo = sesiones_movil.ruteo_automatico(texto)
            ruteo = "%s · esfuerzo %s (%s)" % (
                "Codex" if cerebro_usar == "codex" else "Claude", esfuerzo_usar, motivo)
        respuesta, sid_nuevo = sesiones_movil.mandar(
            cwd, sid_usar, texto, modelo, cerebro_usar, esfuerzo_usar, velocidad,
            al_nacer=_nacio)
        # ⭐ El tope ya no compacta solo (2026-08-20): se mide DESPUES del turno, que es
        # cuando el contexto acaba de crecer, y la pantalla le PREGUNTA a Martin.
        pide = sesiones_movil.pide_compactar(cwd, sid_nuevo or sid_usar)
        sid_final = sid_nuevo or sid_usar
        es_cdx = bool(sid_final and sesiones_movil.es_codex(sid_final))
        modelo_final = (sesiones_movil.codex_modelo_de(sid_final) if es_cdx
                        else sesiones_movil.modelo_de(sid_final))
        esfuerzo_final = (sesiones_movil.codex_esfuerzo_de(sid_final) if es_cdx
                          else sesiones_movil.esfuerzo_de(sid_final))
        velocidad_final = sesiones_movil.codex_velocidad_de(sid_final) if es_cdx else ""
        return {"ok": True, "respuesta": respuesta, "sid": sid_final,
                "aviso": "", "pide_compactar": pide,
                "cerebro": "codex" if es_cdx else cerebro_usar,
                "modelo": modelo_final, "esfuerzo": esfuerzo_final,
                "velocidad": velocidad_final, "ruteo": ruteo}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        with _TURNOS_CANDADO:
            _TURNOS_ABIERTOS.discard(sid)
            _TURNOS_ABIERTOS.discard(sid_usar)
            if nacido:
                _TURNOS_ABIERTOS.discard(nacido)


def _aviso_tarea(cwd, resultado, estado):
    """El texto del aviso al celular cuando termina una tarea larga de Sesiones.

    ⭐ Tiene que decir QUÉ pasó, no solo que pasó algo: esto se lee en el teléfono,
    sin la pantalla al lado y sin contexto. Hasta el 2026-08-25 decía siempre "la
    tarea larga de Codex" —aunque fuera Claude— y no nombraba ni el proyecto, ni la
    charla, ni una palabra de lo que contestó.
    """
    from app.voz import sesiones_movil
    proyecto = Path(cwd).name if cwd else "Servidor IA"
    sid = (resultado.get("sid") or "").strip()
    try:
        charla = sesiones_movil._nombre_charla(cwd, sid) if sid else "una charla nueva"
    except Exception:
        charla = "una charla"
    quien = "Codex" if resultado.get("cerebro") == "codex" else "Claude"
    donde = f"{charla} ({proyecto})" if proyecto and proyecto != charla else charla
    if estado != "terminado":
        return (f"Falló {quien} en {donde}: "
                + str(resultado.get("error") or "sin detalle")[:200])
    primeras = " ".join(str(resultado.get("respuesta") or "").split())[:200]
    cola = f' Arranca diciendo: "{primeras}"' if primeras else ""
    return f"Terminó {quien} en {donde} y te espera en Sesiones.{cola}"


def _correr_trabajo_movil(trabajo_id, cwd, sid, texto, cerebro, esfuerzo,
                           modelo="", velocidad=""):
    """Corre un turno en segundo plano y, si le pediste aviso, te lo manda al terminar.

    ⭐ El "quiero que me avises" se lee de la FICHA al terminar, no de un argumento
    que se congela al arrancar el hilo (2026-08-29). Ese era el bug: el botón Avisame
    solo servía apretado ANTES de mandar, y apretarlo con el turno ya corriendo no
    hacía nada —- encima quedaba armado en silencio para el mensaje siguiente. Ahora
    `POST /movil/avisar` puede prender o apagar la bandeja mientras el turno piensa.
    """
    def _nacio(sid_real):
        # ⭐ El id de una charla nueva se publica en la ficha del trabajo APENAS existe:
        # la pantalla ya lo esta preguntando cada 1,2 s y con eso se muda a la charla de
        # verdad sin esperar el final del turno (2026-08-23).
        with _TRABAJOS_CANDADO:
            t = _TRABAJOS_MOVIL.get(trabajo_id)
            if t and t.get("estado") == "trabajando":
                t["sid_nuevo"] = sid_real

    resultado = _ejecutar_turno_movil(
        cwd, sid, texto, cerebro, esfuerzo, modelo, velocidad, al_nacer=_nacio)
    with _TRABAJOS_CANDADO:
        t = _TRABAJOS_MOVIL.get(trabajo_id)
        if not t:
            return
        t.update(resultado)
        t["sid_nuevo"] = resultado.get("sid") or sid
        t["estado"] = "terminado" if resultado.get("ok") else "cancelado" if t.get("cancelando") else "fallo"
        t["terminado"] = time.time()
        estado = t["estado"]
        quiere_aviso = bool(t.get("avisar"))
    if quiere_aviso and estado in ("terminado", "fallo"):
        _avisar(_aviso_tarea(cwd, resultado, estado))


async def _guardar_imagenes(imagenes, origen):
    """Las fotos que mandas desde el celular, al mismo lugar que las del panel.

    Devuelve (marca, error). La marca es el texto entre corchetes que le dice a
    Claude que abra el archivo con Read — el MISMO formato que ya usan Telegram y
    el chat del panel, para no inventar un tercer dialecto."""
    rutas = []
    for i, imagen in enumerate(imagenes or []):
        if not imagen or not imagen.filename:
            continue
        datos = await imagen.read()
        if not datos:
            continue
        ext = Path(imagen.filename).suffix.lower() or ".jpg"
        if ext not in OK_EXT:
            return None, f"No manejo archivos {ext}."
        IMAGENES_CHAT.mkdir(parents=True, exist_ok=True)
        ruta = IMAGENES_CHAT / f"{int(time.time()*1000)}_{i}{ext}"
        ruta.write_bytes(datos)
        rutas.append(ruta)
    if not rutas:
        return "", None
    if len(rutas) == 1:
        return (f"[Te paso una imagen desde {origen}; está guardada en {rutas[0]} — "
                f"abrila con la herramienta Read antes de contestar.] "), None
    lista = ", ".join(str(r) for r in rutas)
    return (f"[Te paso {len(rutas)} imagenes desde {origen}; están guardadas en {lista} — "
            f"abrilas TODAS con la herramienta Read antes de contestar.] "), None


@app.post("/movil/mandar")
async def movil_mandar(cwd: str = Form(...), sid: str = Form(""), texto: str = Form(""),
                       cerebro: str = Form(""), modelo: str = Form(""),
                       esfuerzo: str = Form(""), velocidad: str = Form(""),
                       segundo_plano: str = Form(""), avisar: str = Form(""),
                       imagenes: list[UploadFile] = File(None)):
    """Un turno contra esa sesion. Puede tardar: el CLI piensa de verdad."""
    from app.voz import sesiones_movil
    marca, error = await _guardar_imagenes(imagenes, "el celular")
    if error:
        return {"ok": False, "error": error}
    texto = (marca + (texto or "").strip()).strip()
    if not texto:
        return {"ok": False, "error": "Escribí algo o mandá una foto."}
    if sid and sid == _sesion_de_laura():
        return {"ok": False, "error": "Esa es la sesión de Laura: hablale por la pestaña "
                                      "Hablar o por el chat, no por acá."}
    # ⭐ Un turno por sesion, y no mas. Dos `claude --resume` a la vez sobre la MISMA
    # sesion la parten al medio: cada proceso escribe su version de la charla. Con el
    # celular en la mano es facil mandar dos seguidos, o mandar desde el telefono
    # mientras contesta en la compu (2026-08-16).
    activo_codex = _codex_turno_realmente_activo(sid)
    with _TURNOS_CANDADO:
        if sid and (sid in _TURNOS_ABIERTOS or activo_codex):
            return {"ok": False, "error": "Esa sesión está contestando algo. Esperá a "
                                          "que termine y mandalo de nuevo."}
        if sid:
            _TURNOS_ABIERTOS.add(sid)
    # ⭐ Lo mandaste: el borrador de esa conversacion ya no existe. Se borra ACA y no
    # solo en la pantalla que mando, para que mandar desde el celular tambien le apague
    # la chapa "✎ Borrador" a la compu (y al reves).
    if sid:
        _guardar_borrador(sid, "")
    if segundo_plano:
        trabajo_id = uuid.uuid4().hex
        trabajo = {"id": trabajo_id, "estado": "trabajando", "cwd": cwd, "sid": sid,
                   "sid_nuevo": "", "respuesta": "", "error": "", "aviso": "",
                   "cerebro": cerebro, "modelo": modelo, "esfuerzo": esfuerzo,
                   "velocidad": velocidad, "ruteo": "", "avisar": bool(avisar),
                   "creado": time.time(), "terminado": None}
        with _TRABAJOS_CANDADO:
            _TRABAJOS_MOVIL[trabajo_id] = trabajo
        threading.Thread(target=_correr_trabajo_movil,
                         args=(trabajo_id, cwd, sid, texto, cerebro, esfuerzo, modelo,
                               velocidad),
                         daemon=True, name="trabajo-movil-" + trabajo_id[:8]).start()
        return {"ok": True, "segundo_plano": True, "trabajo": trabajo_id}
    return await asyncio.to_thread(_ejecutar_turno_movil, cwd, sid, texto, cerebro,
                                   esfuerzo, modelo, velocidad)


@app.get("/movil/trabajo/{trabajo_id}")
def movil_trabajo(trabajo_id: str):
    """Estado y resultado de un turno que el navegador dejo corriendo."""
    with _TRABAJOS_CANDADO:
        t = _TRABAJOS_MOVIL.get(trabajo_id)
        if not t:
            return {"ok": False, "error": "No encuentro ese trabajo."}
        return {"ok": True, **_trabajo_publico(t)}


@app.post("/movil/trabajo/{trabajo_id}/cancelar")
async def movil_cancelar_trabajo(trabajo_id: str):
    from app.voz import sesiones_movil
    with _TRABAJOS_CANDADO:
        t = _TRABAJOS_MOVIL.get(trabajo_id)
        if not t:
            return {"ok": False, "error": "No encuentro ese trabajo."}
        if t.get("estado") != "trabajando":
            return {"ok": True, "paro": False, **_trabajo_publico(t)}
        t["cancelando"] = True
        # Si la charla nacio en este mismo turno, se corta por su id de verdad: es con
        # el que quedo anotado el proceso.
        cwd, sid = t["cwd"], (t.get("sid_nuevo") or t["sid"])
    corte = await asyncio.to_thread(sesiones_movil.parar, cwd, sid)
    return {"ok": True, "paro": corte}


# ⭐ "Avisame" apretado con el turno YA corriendo (pedido de Martín, 2026-08-29).
# Hasta hoy el botón era una bandera del navegador que se consumía al MANDAR: si el
# turno ya estaba pensando, apretarlo no hacía nada para ese turno y encima quedaba
# armado en silencio para el mensaje siguiente. Justo al revés de cuando lo necesitás
# — te das cuenta de que la cosa viene larga MIENTRAS piensa, no antes de mandar.
AVISO_RECIEN_SEG = 120     # si terminó hace menos que esto, el aviso sale igual


def _trabajos_de_sesion(sid, trabajo_id=""):
    """(el trabajo vivo de esa charla, el último que terminó). Con el candado tomado.

    Se busca por `sid` Y por `sid_nuevo`: una charla que nació en este mismo turno
    cambia de id en el medio, y la pantalla puede tener cualquiera de los dos.
    `trabajo_id` gana si viene, que es el caso de la charla recién nacida.
    """
    if trabajo_id:
        t = _TRABAJOS_MOVIL.get(trabajo_id)
        if not t:
            return None, None
        return (t, None) if t.get("estado") == "trabajando" else (None, t)
    vivo = ultimo = None
    for t in _TRABAJOS_MOVIL.values():
        if sid not in (t.get("sid"), t.get("sid_nuevo")):
            continue
        if t.get("estado") == "trabajando":
            if not vivo or t.get("creado", 0) > vivo.get("creado", 0):
                vivo = t
        elif not ultimo or (t.get("terminado") or 0) > (ultimo.get("terminado") or 0):
            ultimo = t
    return vivo, ultimo


@app.post("/movil/avisar")
async def movil_avisar(request: Request):
    """Prender o apagar el aviso al celular del turno que está corriendo AHORA.

    Devuelve `enganchado` para que la pantalla no mienta: si no hay ningún turno vivo
    al que colgarle el aviso, el botón se comporta como siempre (queda armado para el
    mensaje que mandes) y la pantalla lo dice. La regla es que **el aviso no se pierda
    en silencio**: si el turno terminó justo mientras apretabas (o hasta dos minutos
    antes), el aviso sale igual en vez de evaporarse.
    """
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    trabajo_id = (d.get("trabajo") or "").strip()
    quiero = d.get("quiero")
    quiero = True if quiero is None else bool(quiero)
    if not sid and not trabajo_id:
        return {"ok": False, "error": "falta la sesión"}
    texto_ya = ""
    with _TRABAJOS_CANDADO:
        vivo, ultimo = _trabajos_de_sesion(sid, trabajo_id)
        if vivo:
            vivo["avisar"] = quiero
            return {"ok": True, "enganchado": True, "quiero": quiero,
                    "trabajo": vivo.get("id", "")}
        if (quiero and ultimo and ultimo.get("estado") in ("terminado", "fallo")
                and time.time() - (ultimo.get("terminado") or 0) < AVISO_RECIEN_SEG):
            texto_ya = _aviso_tarea(ultimo.get("cwd"), ultimo, ultimo["estado"])
    if texto_ya:
        await asyncio.to_thread(_avisar, texto_ya)
        return {"ok": True, "enganchado": False, "quiero": False,
                "motivo": "recien_termino"}
    return {"ok": True, "enganchado": False, "quiero": quiero, "motivo": "sin_turno"}


@app.post("/movil/parar")
async def movil_parar(request: Request):
    """Cortar el turno que está corriendo en una sesión (el botón Parar).

    Mata el proceso `claude` de ese turno. Lo que ya escribió queda escrito: la
    conversación no se rompe, simplemente deja de pensar y podés escribirle de nuevo.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    cwd = (d.get("cwd") or "").strip()
    corte = await asyncio.to_thread(sesiones_movil.parar, cwd, sid)
    return {"ok": True, "paro": corte}


@app.post("/movil/responder")
async def movil_responder(request: Request):
    """La respuesta a una pregunta con opciones que hizo la sesión (AskUserQuestion).

    La pregunta viaja adentro de `/movil/chat` (campo `pregunta`); la elección vuelve
    por acá como {cwd, sid, respuestas: {pregunta: elección}} — la elección puede ser
    la etiqueta de una opción, varias unidas con ", " o texto libre. El backend le
    escribe el control_response al proceso `claude` que quedó esperando (2026-08-18).
    """
    from app.voz import sesiones_movil
    d = await request.json()
    ok = sesiones_movil.responder_pregunta((d.get("cwd") or "").strip(),
                                           (d.get("sid") or "").strip(),
                                           d.get("respuestas") or {})
    if ok:
        return {"ok": True}
    return {"ok": False, "error": "Esa pregunta ya no está esperando respuesta."}


_ELEGIR_ARCHIVO_LOCK = threading.Lock()


def _ruta_archivo_para_chat(elegido: str, cwd: str) -> tuple[str, bool]:
    """Ruta relativa a la charla; absoluta solo si el archivo está en otro disco."""
    base = Path(cwd).resolve() if cwd and Path(cwd).is_dir() else RAIZ.resolve()
    archivo = Path(elegido).resolve()
    try:
        return os.path.relpath(str(archivo), str(base)), True
    except ValueError:  # En Windows no existe ruta relativa entre C: y D:.
        return str(archivo), False


@app.post("/movil/elegir_archivo")
def movil_elegir_archivo(request: Request):
    """Abre el selector nativo: el navegador oculta la ruta real como C:\\fakepath."""
    # Endpoint sync a propósito: FastAPI lo manda a un hilo y el diálogo no congela
    # el polling de las pantallas mientras Martín elige un documento.
    import tkinter as tk
    from tkinter import filedialog

    # Starlette deja leer JSON solo de forma async; en un endpoint sync el cuerpo ya
    # está disponible en `_body` únicamente en algunos caminos. Recibimos cwd por query
    # para mantener este selector bloqueante fuera del event loop.
    cwd = (request.query_params.get("cwd") or "").strip()
    base = Path(cwd).resolve() if cwd and Path(cwd).is_dir() else RAIZ.resolve()
    if not _ELEGIR_ARCHIVO_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Ya hay un buscador de archivos abierto."}
    raiz = None
    try:
        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        raiz.update()
        elegido = filedialog.askopenfilename(
            parent=raiz, initialdir=str(base), title="Buscar archivo")
        if not elegido:
            return {"ok": False, "cancelado": True}
        ruta, relativa = _ruta_archivo_para_chat(elegido, str(base))
        return {"ok": True, "ruta": ruta, "relativa": relativa}
    except Exception as e:
        return {"ok": False, "error": "No pude abrir el buscador: " + str(e)}
    finally:
        if raiz is not None:
            try:
                raiz.destroy()
            except Exception:
                pass
        _ELEGIR_ARCHIVO_LOCK.release()


@app.get("/movil/modelo")
def movil_modelo_leer(sid: str = "", cwd: str = "", cerebro: str = "",
                       modelo: str = ""):
    """Con qué modelo corre esa sesión, la lista para elegir, y cuánto contexto arrastra.

    ⭐ El modelo es del SERVIDOR, no de la pantalla: lo usa quien lanza el proceso
    `claude`. Elegido en la compu, el celular lo respeta solo.

    Viene junto con el contexto a propósito: son las dos caras de lo mismo (con qué
    corre y cuánto le cuesta), la pantalla las muestra pegadas y así es un pedido y
    no dos.
    """
    from app.voz import sesiones_movil
    if (sid and sesiones_movil.es_codex(sid)) or (not sid and cerebro == "codex"):
        # `modelo` solo adelanta la elección de una pestaña NUEVA. Con id manda el
        # servidor, así un cambio hecho en la compu aparece también en el celular.
        modelo_cdx = (modelo if not sid and modelo in sesiones_movil._codex_modelos()
                      else sesiones_movil.codex_modelo_de(sid))
        return {"ok": True, "modelo": modelo_cdx,
                "modelos": [{"id": k, "nombre": v}
                            for k, v in sesiones_movil._codex_modelos().items()],
                "defecto": next(iter(sesiones_movil._codex_modelos())),
                "esfuerzo": sesiones_movil.codex_esfuerzo_de(sid),
                "esfuerzos": [{"id": k, "nombre": v}
                              for k, v in sesiones_movil._codex_esfuerzos(modelo_cdx).items()],
                "velocidad": sesiones_movil.codex_velocidad_de(sid),
                "velocidades": [{"id": k, "nombre": v}
                                for k, v in sesiones_movil._codex_velocidades(modelo_cdx).items()],
                # ⭐ Plan mode también en Codex (2026-08-25). Acá estaba el bloqueo:
                # las dos pantallas arman el selector con lo que llega en `modos`, así
                # que devolver la lista vacía era lo que lo hacía desaparecer.
                "modo": sesiones_movil.modo_de(sid),
                "modos": [{"id": k, "nombre": v}
                          for k, v in sesiones_movil.MODOS.items()],
                "cerebro": "codex",
                "contexto": sesiones_movil.contexto(cwd, sid)}
    return {"ok": True, "modelo": sesiones_movil.modelo_de(sid),
            "modelos": [{"id": k, "nombre": v} for k, v in sesiones_movil.MODELOS.items()],
            "defecto": sesiones_movil.MODELO_DEFECTO,
            # Cuánto piensa antes de contestar: la misma perilla que en la compu.
            "esfuerzo": sesiones_movil.esfuerzo_de(sid),
            "esfuerzos": [{"id": k, "nombre": v}
                          for k, v in sesiones_movil.ESFUERZOS.items()],
            # ⭐ Plan mode (2026-08-20): en "plan" la sesión primero muestra el plan
            # y no toca nada hasta que Martín lo aprueba desde la pantalla.
            "modo": sesiones_movil.modo_de(sid),
            "modos": [{"id": k, "nombre": v}
                      for k, v in sesiones_movil.MODOS.items()],
            "contexto": sesiones_movil.contexto(cwd, sid) if cwd and sid else None}


@app.post("/movil/modelo")
async def movil_modelo_poner(request: Request):
    """Cambiar el modelo de una sesión. Vale desde el turno siguiente."""
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    valor = (d.get("modelo") or "").strip()
    modelo = (sesiones_movil.poner_codex_modelo(sid, valor)
              if sesiones_movil.es_codex(sid)
              else sesiones_movil.poner_modelo(sid, valor))
    return {"ok": True, "modelo": modelo}


@app.post("/movil/velocidad")
async def movil_velocidad_poner(request: Request):
    """Cambia el tier de una sesión de Codex desde el turno siguiente."""
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    if not sesiones_movil.es_codex(sid):
        return {"ok": False, "error": "La velocidad rápida es una opción de Codex."}
    velocidad = sesiones_movil.poner_codex_velocidad(
        sid, (d.get("velocidad") or "").strip())
    return {"ok": True, "velocidad": velocidad}


@app.post("/movil/esfuerzo")
async def movil_esfuerzo_poner(request: Request):
    """Cambiar cuánto piensa una sesión antes de contestar. Vale desde el turno siguiente."""
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    valor = (d.get("esfuerzo") or "").strip()
    esf = (sesiones_movil.poner_codex_esfuerzo(sid, valor)
           if sesiones_movil.es_codex(sid)
           else sesiones_movil.poner_esfuerzo(sid, valor))
    return {"ok": True, "esfuerzo": esf}


@app.post("/movil/modo")
async def movil_modo_poner(request: Request):
    """Cambiar el modo de una sesión (normal o plan). Vale desde el turno siguiente.

    ⭐ Plan mode (pedido de Martín, 2026-08-20): en "plan" el proceso `claude` se
    relanza con `--permission-mode plan` — trabaja solo lectura, arma un plan y frena
    a esperar la aprobación, que llega por POST /movil/plan.

    ⭐ Desde el 2026-08-25 las charlas de CODEX también lo tienen (antes estaba
    bloqueado acá mismo). Es el mismo modo guardado y la misma tarjeta en la pantalla;
    lo que cambia por dentro es cómo se consigue — ver `INSTRUCCION_PLAN_CODEX`.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    modo = sesiones_movil.poner_modo(sid, (d.get("modo") or "").strip())
    return {"ok": True, "modo": modo}


@app.post("/movil/plan")
async def movil_plan(request: Request):
    """Aprobar o rechazar el plan que una sesión en plan mode dejó esperando.

    El plan viaja adentro de `/movil/chat` (campo `pregunta`, con `plan` en vez de
    `preguntas`); la decisión vuelve por acá como {cwd, sid, aprobar, comentario}.
    Aprobado, la sesión sale de plan mode y ejecuta en el mismo turno; rechazado,
    sigue planeando con el comentario como pedido de cambios (2026-08-20).

    ⭐ En las charlas de CODEX (2026-08-25) el turno que dejó el plan ya terminó, así
    que no hay a quién contestarle: se devuelve `mandar` con el texto del turno que
    sigue y **lo manda la pantalla** por el camino de siempre. Con eso hereda el
    semáforo de ocupada, el botón Parar y el hilo dibujándose en vivo, en vez de
    duplicar todo eso acá.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    cwd = (d.get("cwd") or "").strip()
    sid = (d.get("sid") or "").strip()
    aprobar = bool(d.get("aprobar"))
    comentario = (d.get("comentario") or "").strip()
    if sid and sesiones_movil.es_codex(sid):
        texto = sesiones_movil.responder_plan_codex(cwd, sid, aprobar, comentario)
        if texto is None:
            return {"ok": False, "error": "Ese plan ya no está esperando respuesta."}
        return {"ok": True, "mandar": texto}
    if sesiones_movil.responder_plan(cwd, sid, aprobar, comentario):
        return {"ok": True}
    return {"ok": False, "error": "Ese plan ya no está esperando respuesta."}


@app.post("/movil/compactar")
async def movil_compactar(request: Request):
    """Compactar una sesión: resumirla y seguir en una nueva con ese resumen.

    Devuelve el id NUEVO; la pantalla tiene que mover la pestaña ahí. La sesión
    vieja queda intacta en el disco.

    ⚠ Cuesta dos turnos y el primero lee la charla entera: es lo que se paga UNA
    vez para dejar de pagarlo en cada mensaje. Y va con el mismo candado que
    `/movil/mandar`: dos turnos a la vez sobre la misma sesión la parten al medio.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    cwd = (d.get("cwd") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    if sid == _sesion_de_laura():
        return {"ok": False, "error": "La sesión de Laura se compacta desde el panel."}
    with _TURNOS_CANDADO:
        if sid in _TURNOS_ABIERTOS:
            return {"ok": False, "error": "Esa sesión está contestando algo. Esperá a "
                                          "que termine."}
        _TURNOS_ABIERTOS.add(sid)
    try:
        sid_nuevo, resumen = await asyncio.to_thread(sesiones_movil.compactar, cwd, sid)
        return {"ok": True, "sid": sid_nuevo, "resumen": resumen}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        with _TURNOS_CANDADO:
            _TURNOS_ABIERTOS.discard(sid)


@app.post("/movil/mudar_cerebro")
async def movil_mudar_cerebro(request: Request):
    """Mudar una charla nacida al otro cerebro (Claude ↔ Codex).

    Resume la charla y arranca una nueva en el otro CLI sembrada con ese resumen;
    devuelve el id NUEVO y de quién es, y la pantalla muda la pestaña ahí. La vieja
    queda entera en su CLI, con la chapa de que sigue en la nueva.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    sid = (d.get("sid") or "").strip()
    cwd = (d.get("cwd") or "").strip()
    if not sid:
        return {"ok": False, "error": "Esa pestaña todavía no tiene conversación."}
    if sid == _sesion_de_laura():
        return {"ok": False, "error": "El cerebro de Laura se cambia desde el panel."}
    with _TURNOS_CANDADO:
        if sid in _TURNOS_ABIERTOS:
            return {"ok": False, "error": "Esa sesión está contestando algo. Esperá a "
                                          "que termine."}
        _TURNOS_ABIERTOS.add(sid)
    try:
        sid_nuevo, para, aviso = await asyncio.to_thread(
            sesiones_movil.mudar_cerebro, cwd, sid)
        return {"ok": True, "sid": sid_nuevo, "cerebro": para.lower(), "aviso": aviso}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        with _TURNOS_CANDADO:
            _TURNOS_ABIERTOS.discard(sid)


@app.get("/skills")
def skills_de_sesion(sid: str = "", cwd: str = "", de: str = ""):
    """El catalogo de skills y cuales uso ya esa sesion (el boton ⚡ Skills).

    Con `de=laura` la sesion es la de Laura: su id y su carpeta los sabe el panel,
    no la pantalla. `corriendo` viene resuelto desde aca porque el archivo solo dice
    cual fue la ULTIMA invocada; si esta corriendo ahora lo sabe quien tiene los
    turnos a mano (PENSANDO para Laura, los turnos abiertos para el resto).

    ⭐ Una charla de CODEX devuelve las DOS listas, que son cosas distintas: sus
    `skills` (las de Martin, que Codex ve por los symlinks de `~/.codex/skills`, y se
    invocan con `$nombre`) y sus `prompts` (`~/.codex/prompts`, con `/nombre`).
    ⚠ Hasta el 2026-08-28 esto devolvia `skills: []` a mano, por la decision del
    2026-08-23 de listar solo los prompts. La decision se habia tomado creyendo que
    "Codex no usa las skills de Claude", y era falso: los enlaces existian desde el
    19/08. El menu terminaba diciendole a Martin que no tenia nada justo cuando tenia
    las 14 andando. Se devuelve `cerebro` para que el menu sepa que esta mostrando.
    ⚠ `usadas`/`proyecto` van vacios a proposito: esas marcas se leen del `.jsonl` de
    Claude Code y el rollout de Codex tiene otro formato. Mejor sin marca que con una
    inventada.
    """
    from app.nucleo import skills
    if de != "laura" and sid:
        from app.voz import sesiones_movil
        if sesiones_movil.es_codex(sid):
            return {"ok": True, "cerebro": "codex",
                    "prompts": skills.prompts_codex(cwd),
                    "carpeta": str(skills.CARPETA_PROMPTS_CODEX),
                    "skills": skills.catalogo_codex(cwd),
                    "carpeta_skills": str(skills.CARPETA_SKILLS_CODEX),
                    "usadas": [], "corriendo": "",
                    "proyecto": {}, "comandos": [], "rotas": []}
    if de == "laura":
        sid = _sesion_de_laura()
        cwd = str(RAIZ)
        pensando = PENSANDO.exists()
    else:
        with _TURNOS_CANDADO:
            pensando = sid in _TURNOS_ABIERTOS
        if not pensando:
            # Un turno lanzado desde el celular no pasa por el candado del panel.
            from app.voz import sesiones_movil
            p = sesiones_movil.EN_CURSO.get(sid)
            pensando = p is not None and p.poll() is None
    u = skills.usadas(cwd, sid)
    # ⭐ `proyecto` es el uso acumulado en TODAS las conversaciones de esa carpeta, no
    # en esta charla: pedido de Martin (2026-08-18) para que el menu no aparezca en
    # blanco en una sesion recien abierta. Es lo caro del endpoint la primera vez
    # (~4 s con 305 MB de transcripciones); despues sale cacheado.
    # `comandos` son los TUYOS (`~/.claude/commands`), no los de siempre: esos los
    # tiene la pantalla. `rotas` son las carpetas de skills sin SKILL.md — pedido del
    # 2026-08-23, para que "la cree y no aparece" tenga una respuesta en el menu.
    return {"ok": True, "skills": skills.catalogo(cwd), "usadas": u["usadas"],
            "corriendo": u["ultima"] if pensando else "",
            "proyecto": skills.usadas_proyecto(cwd),
            "comandos": skills.comandos(cwd), "rotas": skills.rotas(cwd)}


ALTO_NOTA = 15      # lo que ocupa una nota de tres renglones, en unidades de tablero
ANCHO_COL = 20      # de una columna a la de al lado


def _pizarra_lugar_libre(items):
    """Donde cae una nota escrita desde el celular.

    Desde el telefono no hay lienzo donde apuntar, asi que la posicion la elige
    el servidor: abajo de la ultima columna y siempre ADENTRO del rectangulo de
    fondo. Sin esto quedan en la posicion por defecto, que puede caer lejisimos
    del fondo -- paso, y hubo que ir a buscarlas a mano.
    """
    fondo = next((i for i in items
                  if i.get("tipo") == "rectangulo" and i.get("nombre") == "fondo"), None)
    if fondo:
        x0, x1 = sorted((fondo["x1"], fondo["x2"]))
        y0, y1 = sorted((fondo["y1"], fondo["y2"]))
        x0, y0, x1, y1 = x0 + 8, y0 + 6, x1 - 8, min(y1 - 4, 94)
    else:
        x0, y0, x1, y1 = 10, 10, 90, 92
    sueltos = [i for i in items if i.get("x") is not None and i.get("y") is not None
               and x0 - 12 <= i["x"] <= x1 + 12]
    if not sueltos:
        return round(x0, 1), round(y0, 1)
    col_x = max(i["x"] for i in sueltos)                       # la columna de mas a la derecha
    columna = [i for i in sueltos if abs(i["x"] - col_x) < ANCHO_COL]
    y = max(i["y"] for i in columna) + ALTO_NOTA
    if y > y1:                                                  # llego abajo: arranca una al lado
        return round(min(col_x + ANCHO_COL, x1), 1), round(y0, 1)
    return round(col_x, 1), round(y, 1)


@app.post("/movil/pizarra/nota")
async def movil_pizarra_nota(request: Request):
    """Una nota escrita desde el celular. Va por la misma puerta que las del
    escritorio; lo unico que agrega es elegirle el lugar."""
    d = await request.json()
    if not (d.get("texto") or "").strip():
        return {"ok": False, "error": "falta el texto"}
    with _PIZARRA_CANDADO:
        x, y = _pizarra_lugar_libre(_pizarra_cargar().get("items", []))
        return _pizarra_agregar_bloqueado({**d, "x": x, "y": y, "w": 250}, "nota")


@app.get("/movil/pestanas")
def movil_pestanas_leer():
    """Las pestañas abiertas y cual estaba activa. Se guardan del lado del server
    para que sean las MISMAS entren desde el navegador o desde el icono de la app."""
    try:
        return json.loads(PESTANAS_MOVIL.read_text(encoding="utf-8"))
    except Exception:
        return {"pestanas": [], "activa": "panel"}


@app.post("/movil/pestanas")
async def movil_pestanas_guardar(request: Request):
    d = await request.json()
    PESTANAS_MOVIL.write_text(json.dumps({
        "pestanas": d.get("pestanas") or [],
        "activa": d.get("activa") or "panel"}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


# --- Hablarle con el microfono DEL TELEFONO ----------------------------------
# El circuito ya existia entero en app/voz/llamada.py (corre adentro de voz.py, con
# el Whisper y el Piper ya cargados): lo unico que faltaba era una puerta comoda
# desde la app. El panel hace de proxy y pone el X-Laura-Token que lee del .env,
# para no tener que guardar el secreto en el celular — adentro de la maquina el
# panel ya es de confianza, y de afuera no se llega sin estar en la tailnet.
# ⚠ Esto NECESITA HTTPS: el navegador no entrega el microfono en una pagina http.
# Por eso el panel se publica con `tailscale serve --https=443` (2026-08-16).
LLAMADA_URL = "http://127.0.0.1:8760/laura-voz"


def _laura_voz_token():
    from dotenv import dotenv_values
    return (dotenv_values(ENV) or {}).get("LAURA_VOZ_TOKEN", "")


@app.post("/movil/hablar")
def movil_hablar(audio: UploadFile = File(...)):
    """Manda lo que grabaste con el telefono a la MISMA Laura del microfono.

    ⚠ `def` normal y NO `async def`: adentro se espera a Laura, que puede tardar
    un minuto largo. En un `async def`, esa espera bloqueante congela el panel
    ENTERO mientras tanto (ya paso con /chat/mandar el 2026-08-14). Asi FastAPI
    lo manda a un hilo y el resto del panel sigue vivo.
    """
    token = _laura_voz_token()
    if not token:
        return JSONResponse({"error": "falta LAURA_VOZ_TOKEN en el .env"}, status_code=503)
    if not vivo("voz"):
        return JSONResponse({"error": "la voz esta apagada"}, status_code=503)
    datos = audio.file.read()
    try:
        r = requests.post(f"{LLAMADA_URL}/hablar",
                          files={"audio": (audio.filename or "voz.webm", datos,
                                           audio.content_type or "audio/webm")},
                          headers={"X-Laura-Token": token}, timeout=300)
        return JSONResponse(r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {"error": r.text[:200]}, status_code=r.status_code)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=502)


@app.post("/movil/carpeta")
async def movil_carpeta(request: Request):
    """Sumar una carpeta a la lista de proyectos, aunque no tenga conversaciones.

    La lista se arma con las carpetas que YA tienen transcripciones de Claude Code,
    asi que un proyecto nuevo no aparecia por ningun lado y no habia forma de
    arrancar una sesion ahi desde el panel (pedido de Martin, 2026-08-17).
    Con `crear: true` ademas la crea en el disco si no existe.
    """
    d = await request.json()
    ruta = (d.get("ruta") or "").strip().strip('"')
    if not ruta:
        return {"ok": False, "error": "falta la ruta"}
    carpeta = Path(ruta)
    if not carpeta.is_absolute():
        return {"ok": False, "error": "poné la ruta completa, con la letra del disco"}
    if not carpeta.exists():
        if not d.get("crear"):
            return {"ok": False, "puede_crear": True, "error": "esa carpeta no existe"}
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {"ok": False, "error": f"no pude crearla: {str(e)[:120]}"}
    if not carpeta.is_dir():
        return {"ok": False, "error": "eso no es una carpeta"}
    try:
        extra = json.loads(CARPETAS_SESIONES.read_text(encoding="utf-8"))
    except Exception:
        extra = []
    if str(carpeta) not in extra:
        extra.append(str(carpeta))
        CARPETAS_SESIONES.write_text(json.dumps(extra, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return {"ok": True, "nombre": carpeta.name, "cwd": str(carpeta)}


@app.post("/movil/novedad")
async def movil_novedad(request: Request):
    """¿Alguna de estas sesiones terminó de escribir?

    Se le pasan solo las que tenés abiertas como pestaña (no las 144 que hay en el
    disco): para cada una devuelve quién habló último y cuándo se tocó el archivo.
    Con eso la pantalla puede marcar en amarillo la que te está esperando, incluso
    si la sesión corre en otra ventana de Claude Code.
    """
    from app.voz import sesiones_movil
    d = await request.json()
    salida = {}
    for p in (d.get("pestanas") or [])[:20]:
        sid, cwd = (p.get("sid") or ""), (p.get("cwd") or "")
        if not sid or not cwd or sid.startswith("nueva-"):
            continue
        quien, ts = sesiones_movil.novedad(cwd, sid)
        salida[sid] = {"ultimo": quien, "ts": ts}
    return salida


@app.get("/sesiones", response_class=HTMLResponse)
def pagina_sesiones():
    """Las sesiones de Claude Code en pantalla grande, estilo bandeja de correo.

    Los proyectos son las carpetas de la izquierda y cada conversación se abre como
    pestaña propia (referencia que dio Martín: Gmail). Usa los MISMOS endpoints que
    la app del celular — `/movil/sesiones`, `/movil/chat`, `/movil/mandar` y
    `/movil/nombre` —, así que las reglas son las de allá: la sesión de Laura no se
    lista, un turno por sesión y a las vivas solo se las mira.
    """
    return FileResponse(ESTATICOS / "sesiones.html", media_type="text/html",
                        headers={"Cache-Control": "no-store"})


# --- El explorador de archivos de la pantalla de Sesiones ----------------------
# Pedido de Martin (2026-08-17): "quiero el explorador de archivos del proyecto al
# lateral izquierdo, como Visual Studio". Es un explorador de MIRAR: lista carpetas
# y muestra un archivo. Aca no hay ni una sola ruta que escriba, mueva ni borre —
# para cambiar algo esta la conversacion, que es la que sabe lo que esta haciendo.
#
# ⭐ La unica llave es la CARPETA RAIZ del proyecto: solo se abre lo que el panel YA
# conoce (una carpeta con conversaciones de Claude Code, o una que Martin sumo a mano
# en `carpetas_sesiones.json`), y todo lo que se pida adentro tiene que caer ADENTRO
# de esa raiz. Se compara despues de `resolve()`, asi que ni un `..` ni un enlace
# simbolico pueden usarse para salir a leer otra cosa del disco.
ARBOL_ESCONDIDO = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
                   ".mypy_cache", ".pytest_cache", ".idea", "$RECYCLE.BIN"}
ARBOL_MAX_ITEMS = 800          # una carpeta con 5.000 archivos no entra en pantalla
ARBOL_MAX_BYTES = 400_000      # cuanto texto se manda de un archivo
ARBOL_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}


def _arbol_raiz(cwd: str):
    """La carpeta del proyecto, SOLO si el panel ya la conoce. Si no, None.

    Se acepta por dos caminos, los mismos que arman la lista de la izquierda: que
    tenga transcripciones de Claude Code (o sea que exista su carpeta aplanada en
    ~/.claude/projects) o que este en `carpetas_sesiones.json`. Cualquier otra ruta
    del disco no se abre: es lo que impide que esto sea "leer cualquier archivo de
    la maquina" por una direccion.
    """
    texto = (cwd or "").strip().strip('"')
    if not texto:
        return None
    ruta = Path(texto)
    if not ruta.is_absolute():
        return None
    try:
        ruta = ruta.resolve()
    except OSError:
        return None
    if not ruta.is_dir():
        return None
    # `carpeta_de` se prueba con la ruta tal cual vino Y con la resuelta: la lista de
    # proyectos las manda como las escribio Claude Code, que no siempre es la forma
    # canonica de Windows.
    if seguir.carpeta_de(texto).is_dir() or seguir.carpeta_de(ruta).is_dir():
        return ruta
    try:
        extra = json.loads(CARPETAS_SESIONES.read_text(encoding="utf-8"))
    except Exception:
        extra = []
    plano = lambda p: str(p).replace("/", "\\").rstrip("\\").lower()
    if plano(ruta) in {plano(e) for e in extra}:
        return ruta
    return None


def _arbol_dentro(raiz: Path, sub: str):
    """La ruta pedida, solo si cae adentro de la raiz. Si no, None."""
    sub = (sub or "").replace("\\", "/").strip("/")
    try:
        destino = (raiz / sub).resolve()
    except OSError:
        return None
    try:
        destino.relative_to(raiz)
    except ValueError:
        return None
    return destino


@app.get("/archivos/lista")
def archivos_lista(cwd: str, sub: str = ""):
    """Lo que hay adentro de una carpeta del proyecto: las carpetas primero.

    Se pide de a una carpeta (no el arbol entero) porque un proyecto real tiene
    miles de archivos y casi todos no se van a mirar nunca: se leen recien cuando
    abris esa rama, que es como se comporta el explorador de VS Code.
    """
    raiz = _arbol_raiz(cwd)
    if not raiz:
        return {"ok": False, "error": "no conozco esa carpeta"}
    carpeta = _arbol_dentro(raiz, sub)
    if not carpeta or not carpeta.is_dir():
        return {"ok": False, "error": "esa carpeta no existe"}
    filas = []
    try:
        with os.scandir(carpeta) as it:
            for e in it:
                if e.name in ARBOL_ESCONDIDO or e.name.startswith("~$"):
                    continue
                try:
                    es_dir = e.is_dir()
                    st = e.stat()
                except OSError:
                    continue          # un archivo bloqueado no puede voltear la lista
                filas.append({"nombre": e.name, "dir": es_dir,
                              "bytes": 0 if es_dir else st.st_size, "ts": st.st_mtime})
    except OSError as err:
        return {"ok": False, "error": f"no pude abrirla: {str(err)[:80]}"}
    filas.sort(key=lambda f: (not f["dir"], f["nombre"].lower()))
    return {"ok": True, "sub": sub, "items": filas[:ARBOL_MAX_ITEMS],
            "de_mas": max(0, len(filas) - ARBOL_MAX_ITEMS)}


@app.get("/archivos/ver")
def archivos_ver(cwd: str, ruta: str):
    """Un archivo para leerlo en pantalla. Nunca escribe nada.

    Devuelve `tipo`: texto (con el contenido), imagen (se pide aparte por
    `/archivos/crudo`), binario o pesado. Del texto van como mucho
    ARBOL_MAX_BYTES: un .jsonl de 8 MB colgaria el navegador.
    """
    raiz = _arbol_raiz(cwd)
    if not raiz:
        return {"ok": False, "error": "no conozco esa carpeta"}
    arch = _arbol_dentro(raiz, ruta)
    if not arch or not arch.is_file():
        return {"ok": False, "error": "ese archivo no existe"}
    try:
        st = arch.stat()
    except OSError as err:
        return {"ok": False, "error": f"no pude leerlo: {str(err)[:80]}"}
    base = {"ok": True, "ruta": ruta, "nombre": arch.name, "bytes": st.st_size,
            "ts": st.st_mtime, "completo": str(arch)}
    if arch.suffix.lower() in ARBOL_IMAGEN:
        return {**base, "tipo": "imagen"}
    if st.st_size > ARBOL_MAX_BYTES * 8:
        return {**base, "tipo": "pesado"}
    try:
        datos = arch.read_bytes()
    except OSError as err:
        return {"ok": False, "error": f"no pude leerlo: {str(err)[:80]}"}
    # Un cero en el primer pedazo = no es texto. Es la misma regla que usa `git`
    # para decidir si un archivo es binario, y acierta con .exe, .wav y .pyc.
    if b"\x00" in datos[:4000]:
        return {**base, "tipo": "binario"}
    return {**base, "tipo": "texto",
            "texto": datos[:ARBOL_MAX_BYTES].decode("utf-8", errors="replace"),
            "cortado": st.st_size > ARBOL_MAX_BYTES}


@app.get("/archivos/crudo")
def archivos_crudo(cwd: str, ruta: str):
    """El archivo tal cual, solo para las IMAGENES del visor."""
    raiz = _arbol_raiz(cwd)
    if not raiz:
        return JSONResponse({"error": "no conozco esa carpeta"}, status_code=404)
    arch = _arbol_dentro(raiz, ruta)
    if not arch or not arch.is_file() or arch.suffix.lower() not in ARBOL_IMAGEN:
        return JSONResponse({"error": "no es una imagen del proyecto"}, status_code=404)
    return FileResponse(arch)


def _wallpaper_de_windows():
    """La foto que Windows tiene AHORA en el escritorio.

    ⭐ No se adivina mirando carpetas: se le PREGUNTA a Windows con
    `SystemParametersInfoW(SPI_GETDESKWALLPAPER)`, que devuelve la ruta exacta del
    archivo puesto en este momento. Con "Windows spotlight" de escritorio esa ruta cae
    en la carpeta del IrisService y CAMBIA sola cada vez que Windows rota la imagen —
    que es justo lo que Martin pidio (2026-08-18: "que se vaya actualizando a medida
    que va actualizando en mi escritorio").

    ⚠ Antes esto leia la carpeta del Spotlight de la PANTALLA DE BLOQUEO
    (`ContentDeliveryManager`), que es otra coleccion: la foto del bloqueo y la del
    escritorio casi nunca son la misma, y por eso el panel mostraba una y el escritorio
    otra. Esa carpeta queda de ultimo recurso.

    Orden: lo que dice Windows -> la copia `TranscodedWallpaper` -> el Spotlight del
    bloqueo. Devuelve un Path o None.
    """
    import ctypes
    try:
        buf = ctypes.create_unicode_buffer(520)
        ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buf, 0)
        if buf.value:
            f = Path(buf.value)
            if f.is_file() and f.stat().st_size > 50_000:
                return f
    except Exception:
        pass
    # Copia que Windows deja del fondo aplicado (sin extension, pero es un JPEG).
    trans = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    if trans.is_file() and trans.stat().st_size > 50_000:
        return trans
    # Ultimo recurso: el Spotlight de la pantalla de bloqueo. Vienen sin extension y
    # mezcladas con iconos chicos y con las verticales del celular, asi que se elige la
    # mas nueva que sea apaisada y pese de verdad.
    try:
        from PIL import Image
        candidatas = []
        for f in WINDOWS_FONDOS.iterdir() if WINDOWS_FONDOS.is_dir() else []:
            if not f.is_file() or f.stat().st_size < 300_000:
                continue
            try:
                with Image.open(f) as im:
                    if im.width > im.height:
                        candidatas.append((f.stat().st_mtime, f))
            except Exception:
                continue
        if candidatas:
            return max(candidatas)[1]
    except Exception:
        pass
    return None


@app.get("/fondo/windows")
def fondo_windows():
    """La foto del escritorio, para usarla de fondo de las pantallas.

    Se sirve sin cache: cuando Windows la cambia, el panel la sigue.
    """
    f = _wallpaper_de_windows()
    if not f:
        return {"ok": False, "error": "no encontre la foto del escritorio"}
    with open(f, "rb") as h:
        tipo = "image/png" if h.read(2) == bytes([0x89, 0x50]) else "image/jpeg"
    return FileResponse(f, media_type=tipo, headers={"Cache-Control": "no-store"})


@app.get("/fondo/windows/version")
def fondo_windows_version():
    """Una firma barata de la foto de ahora (ruta + cuando se guardo).

    La pantalla la consulta cada tanto y solo vuelve a bajar la imagen cuando cambia:
    preguntar cuesta unos bytes, bajar la foto cuesta 2 MB.
    """
    f = _wallpaper_de_windows()
    if not f:
        return {"v": ""}
    try:
        return {"v": f"{f.name}:{int(f.stat().st_mtime)}"}
    except Exception:
        return {"v": f.name}


@app.get("/estaticos/marcado.js")
def estatico_marcado():
    """El dibujante de markdown que comparten la pagina de sesiones y la del celular.

    Vive como archivo aparte para que sea UNO solo: las dos pantallas leen lo que
    escribe Claude, y lo que se arregle o se ajuste ahi vale para las dos.

    ⚠ Esta ruta se perdio una vez (2026-08-18) al pisarse dos sesiones editando
    `panel.py`, y el sintoma fue doble y confuso: las conversaciones mostraban los
    asteriscos y los numerales crudos, y de yapa NINGUNA marca de texto se dibujaba —
    porque las marcas se anclan contando letras sobre el texto YA dibujado, y sin
    markdown esas letras estan en otro lugar.
    """
    return FileResponse(ESTATICOS / "marcado.js", media_type="application/javascript")


@app.get("/estaticos/marcas.js")
def estatico_marcas():
    """El marcador de texto (pintar y subrayar adentro de una conversacion).

    Mismo criterio que `marcado.js`: vive como archivo aparte porque lo usan la pagina
    de sesiones de la compu (que pinta) y la del celular (que por ahora solo muestra lo
    pintado). Una sola manera de dibujar una marca para las dos.
    """
    return FileResponse(ESTATICOS / "marcas.js", media_type="application/javascript")


@app.get("/estaticos/direccion.js")
def estatico_direccion():
    """La direccion web de cada conversacion, compartida por las dos pantallas que
    abren charlas: la de la compu (`/sesiones`) y la app del celular (`/movil`).

    Sin cache: es logica de navegacion y un cambio tiene que verse con F5.
    """
    return FileResponse(ESTATICOS / "direccion.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/estaticos/aspecto.js")
def estatico_aspecto():
    """El aspecto (fondo, tipografia y color) que comparten TODAS las pantallas."""
    return FileResponse(ESTATICOS / "aspecto.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/estaticos/atajos.js")
def estatico_atajos():
    """Los botones ⚡ Skills y ∕ Comandos de las cajas de escribir.

    Mismo criterio que `marcas.js`: archivo aparte porque lo comparten la pagina de
    sesiones y el chat del panel. Los datos los pone `GET /skills`.
    """
    return FileResponse(ESTATICOS / "atajos.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})


@app.get("/aspecto")
def aspecto_leer():
    """Como quiere ver las pantallas. Vive en el servidor para que la eleccion hecha
    en la compu valga tambien en el telefono (pedido de Martin, 2026-08-17)."""
    try:
        return json.loads(ASPECTO.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.post("/aspecto")
async def aspecto_guardar(request: Request):
    d = await request.json()
    if not isinstance(d, dict):
        return {"ok": False, "error": "formato raro"}
    # Solo lo nuestro: la foto puede pesar cientos de kB y el resto son palabras cortas.
    # ⚠ Campo que no este en esta lista NO viaja al telefono: se guarda en el navegador
    # donde lo elegiste y en ningun otro lado. Al agregar una opcion en `aspecto.js`,
    # agregarla aca (`letra` y `velo` son de la tanda del 2026-08-18).
    limpio = {k: d.get(k) for k in ("tipo", "color", "fondo", "img", "letra", "velo",
                                    # el color del rastro (2026-08-28)
                                    "rastro",
                                    # ⭐ y el color de cada parte (2026-08-29): las dos
                                    # burbujas, el semaforo (encendido/roto/atencion) y
                                    # las dos barras. Vacio o ausente = sigue al tema.
                                    "burbujaVos", "burbujaIa", "ok", "mal", "aviso",
                                    "barra", "pizBarra",
                                    # ⭐ Los efectos (2026-08-29): cuanta sombra tienen las
                                    # cajas, si las barras se ven de vidrio esmerilado y
                                    # cuanto se mueve la pantalla.
                                    "sombra", "vidrio", "movi",
                                    # ⭐⭐ Los estilos (2026-08-29, "mas colores sobre el
                                    # panel"): el tinte general de las letras y de las
                                    # cajas, el color de cada tarjeta del panel
                                    # (`bloques`, un dict), el estilo puesto y `previo`,
                                    # que es la copia de lo que habia antes de aplicarlo
                                    # — es lo que hace posible el "volver a lo mio".
                                    "tintaLetras", "tintaCajas", "bloques",
                                    "estilo", "previo",
                                    # ⭐ Y los efectos de la letra (2026-08-29, "mas
                                    # efectos y estilos para las letras"): grosor, espacio
                                    # entre letras, interlineado, sombra/resplandor y la
                                    # tipografia de los titulos. `tipo` ya estaba, pero
                                    # ahora ademas puede traer el NOMBRE de una fuente
                                    # instalada y no solo una de las nueve claves.
                                    "peso", "espaciado", "renglon", "letraFx",
                                    "tipoTitulo",
                                    # ⭐ El tamaño de los BOTONES y que no crezcan con el
                                    # zoom (2026-09-12, "me gustaria poder encojer mas los
                                    # botones de la interfaz"). ⚠ Viaja la ELECCION y nada
                                    # mas: la referencia del zoom con la que se hace la
                                    # cuenta vive en el navegador (`aspectoZoomRef`),
                                    # porque el telefono tiene otra densidad y otra
                                    # ampliacion — con la de la laptop puesta aca, los
                                    # botones saldrian de cualquier tamano.
                                    "botones", "botonesZoom")
              if d.get(k) is not None}
    ASPECTO.write_text(json.dumps(limpio), encoding="utf-8")
    # ⚠ Se devuelve lo GUARDADO, no un "ok" pelado: es como la pantalla se entera de que
    # el panel es viejo y esta tirando los campos que no conoce (2026-08-29). Sin esto,
    # el color se veia en la compu y no llegaba nunca al telefono, sin decir nada.
    return {"ok": True, "aspecto": limpio}


@app.get("/estaticos/menu.js")
def estatico_menu():
    """El menu de pantallas que comparten las cinco paginas de la compu.

    Vive como archivo aparte porque lo usan paginas que estan adentro de este
    archivo (panel, pizarra) y paginas que son estaticos sueltos
    (sesiones, estudio): agregar una pantalla nueva es un renglon alla y aparece
    en todas. Sin cache, para que un cambio se vea con F5 y no haga falta
    reiniciar nada.
    """
    return FileResponse(ESTATICOS / "menu.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- Avisos (Recordatorios del iPhone)

@app.get("/avisos", response_class=HTMLResponse)
def avisos_pagina():
    """La pestaña Avisos: los recordatorios del iPhone y los que salen de acá."""
    return FileResponse(ESTATICOS / "avisos.html", media_type="text/html",
                        headers={"Cache-Control": "no-store"})


_URL_TAILSCALE = {"url": None, "vence": 0.0}


def _url_tailscale():
    """La direccion con la que el CELULAR llega hasta acá, no la de esta compu.

    ⚠ Existe por un error que no avisa: la pantalla de Avisos muestra la dirección
    que hay que pegar adentro del Atajo, y si la abrís desde la compu esa dirección
    es `127.0.0.1`, que en el teléfono no es este panel — es el teléfono mismo. El
    Atajo quedaría armado y no andaría nunca, sin ningún error a la vista.

    Se cachea 10 minutos: `tailscale status` tarda casi un segundo y esto se pide
    cada 20 s desde cada pestaña abierta (misma decisión que `_FONDO_WIN`).
    """
    if _URL_TAILSCALE["url"] is not None and time.time() < _URL_TAILSCALE["vence"]:
        return _URL_TAILSCALE["url"]
    url = ""
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                           text=True, timeout=8, creationflags=CREATE_NO_WINDOW)
        nombre = ((json.loads(r.stdout) or {}).get("Self") or {}).get("DNSName") or ""
        nombre = nombre.rstrip(".")
        if nombre:
            # Se publica con `tailscale serve --https=443`, o sea sin puerto en la URL.
            url = "https://%s" % nombre
    except Exception:
        url = ""                    # sin tailscale la pantalla cae a la del navegador
    _URL_TAILSCALE.update({"url": url, "vence": time.time() + 600})
    return url


@app.get("/avisos/lista")
def avisos_lista():
    """Todo lo que dibuja la pantalla, en un solo pedido."""
    return {"ok": True, "url_tailscale": _url_tailscale(), **avisos_mod.estado()}


@app.post("/avisos/nuevo")
async def avisos_nuevo(request: Request):
    """Anotar algo desde el panel para que aparezca en el iPhone.

    No viaja solo: queda en la cola y se lo lleva el Atajo la próxima vez que corra.
    Por eso la pantalla muestra cuándo fue la última sincronización — si el puente
    está dormido, lo que anotes acá va a tardar en aparecer allá.
    """
    cuerpo = await request.json()
    saliente = avisos_mod.crear((cuerpo or {}).get("nombre", ""))
    if not saliente:
        return JSONResponse({"ok": False, "error": "hace falta un texto"}, status_code=400)
    return {"ok": True, "saliente": saliente}


@app.post("/avisos/quitar")
async def avisos_quitar(request: Request):
    """Sacar de la cola algo que todavía no se fue al teléfono."""
    cuerpo = await request.json()
    return {"ok": avisos_mod.quitar((cuerpo or {}).get("id", ""))}


@app.get("/adversarial/lista")
def adversarial_lista(cwd: str = ""):
    """Todo lo que dibuja la tarjeta: las corridas y los proyectos del selector."""
    from app.voz import adversarial
    return {"ok": True, "corridas": adversarial.listar(cwd),
            "carpetas": adversarial.carpetas(), "vueltas": adversarial.MAX_VUELTAS}


@app.post("/adversarial/arrancar")
async def adversarial_arrancar(request: Request):
    """Larga el contraste sobre una carpeta y vuelve enseguida.

    No espera nada: el ciclo son varios turnos de varios minutos y Martin cierra la
    laptop apenas lo larga. El estado se mira despues en la tarjeta.
    """
    from app.voz import adversarial
    cuerpo = await request.json() or {}
    try:
        corrida = adversarial.arrancar((cuerpo.get("cwd") or "").strip(),
                                       (cuerpo.get("tarea") or "").strip(),
                                       (cuerpo.get("spec") or "").strip())
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return {"ok": True, "corrida": corrida}


@app.post("/adversarial/resolver")
async def adversarial_resolver(request: Request):
    """El desempate: a quien le da la razon Martin cuando nadie pudo demostrar."""
    from app.voz import adversarial
    cuerpo = await request.json() or {}
    a_favor = (cuerpo.get("a_favor") or "").strip()
    if a_favor not in ("revisor", "implementador"):
        return JSONResponse({"ok": False, "error": "hay que elegir a quien"},
                            status_code=400)
    corrida = adversarial.resolver((cuerpo.get("id") or "").strip(), a_favor)
    if not corrida:
        return JSONResponse({"ok": False, "error": "esa corrida no esta empatada"},
                            status_code=400)
    return {"ok": True, "corrida": corrida}


@app.post("/adversarial/limpiar-pizarra")
def adversarial_limpiar_pizarra():
    """Saca del pizarron SOLO los papelitos que puso el contraste.

    ⚠ No es un "vaciar": lo de Martin y lo de Laura no se toca. Reconoce los suyos por
    la marca que les deja al crearlos.
    """
    from app.voz import adversarial
    return {"ok": True, "sacadas": adversarial.limpiar_pizarra()}


@app.post("/avisos/sync")
async def avisos_sync(request: Request):
    """⭐ El endpoint del Atajo del iPhone. Las dos mitades en un solo pedido.

    Recibe el cuerpo como TEXTO PELADO (una línea por recordatorio,
    `nombre|vence|lista`) y contesta también texto pelado: un nombre por línea, los
    que hay que crear en el teléfono. Es feo a propósito — el Atajo se arma a dedo en
    la pantalla del celular y cada campo de JSON sería un toque más y una cosa más
    para escribir mal. Ver `app/nucleo/avisos.py`.

    ⚠ Acepta las dos formas: el cuerpo crudo, o un JSON `{"texto": "..."}`, porque
    según cómo quede configurada la acción "Obtener contenido de URL" el Atajo manda
    una o la otra. Que el puente no se caiga por eso.
    """
    crudo = (await request.body()).decode("utf-8", errors="replace")
    texto = crudo
    if crudo.lstrip().startswith("{"):
        try:
            texto = (json.loads(crudo) or {}).get("texto", "") or ""
        except json.JSONDecodeError:
            texto = crudo                       # era texto que casualmente empezaba con {
    salida = avisos_mod.sincronizar(texto)
    print("avisos: el telefono mando %d y se lleva %d"
          % (len(texto.splitlines()), len(salida.splitlines()) if salida else 0), flush=True)
    return Response(content=salida, media_type="text/plain; charset=utf-8")


# ----------------------------------------------------------------- Estudio de audio
# Pegar varios audios uno atras del otro y que salga uno solo (pedido de Martin,
# 2026-08-17). La pantalla esta en app/estaticos/estudio.html; aca solo vive lo que
# el navegador no puede hacer: guardar los archivos y llamar a ffmpeg.

_NOMBRE_OK = re.compile(r"[\w.-]+")      # sin ../ ni rutas raras, igual que en la pizarra

# El POST de transcribir queda abierto hasta el final, pero la pantalla necesita una
# segunda ventanita para contar qué está pasando mientras tanto. Vive en memoria: es
# estado de trabajo, no algo que haya que dejar guardado si el panel se apaga.
_ESTUDIO_PROGRESOS = {}
_ESTUDIO_PROGRESOS_LOCK = threading.Lock()


def _estudio_progreso_poner(nombre, pct=None, paso=None, en_curso=None, error=None):
    with _ESTUDIO_PROGRESOS_LOCK:
        d = _ESTUDIO_PROGRESOS.setdefault(nombre, {"pct": 0, "paso": "Esperando…",
                                                    "en_curso": False, "error": ""})
        if pct is not None:
            d["pct"] = max(0, min(100, int(pct)))
        if paso is not None:
            d["paso"] = str(paso)[:160]
        if en_curso is not None:
            d["en_curso"] = bool(en_curso)
        if error is not None:
            d["error"] = str(error)[:300]
        d["actualizado"] = time.time()
        return dict(d)


def _estudio_progreso(nombre):
    with _ESTUDIO_PROGRESOS_LOCK:
        d = _ESTUDIO_PROGRESOS.get(nombre)
        return dict(d) if d else {"pct": 0, "paso": "Esperando para preparar el video…",
                                   "en_curso": False, "error": ""}


def _estudio_progreso_empezar(nombre):
    """Reserva un video: dos recargas no pueden arrancar Whisper dos veces."""
    with _ESTUDIO_PROGRESOS_LOCK:
        anterior = _ESTUDIO_PROGRESOS.get(nombre) or {}
        if anterior.get("en_curso"):
            return False
        _ESTUDIO_PROGRESOS[nombre] = {"pct": 1, "paso": "Preparando el video…",
                                      "en_curso": True, "error": "", "actualizado": time.time()}
        return True


def _cola_video_actualizar(nombre, pct=None, paso=None, terminar=False, error=""):
    """Refleja el progreso del video del panel en la cola compartida del Estudio."""
    item = entrantes.cola_de_archivo(nombre)
    if not item:
        return
    if error:
        entrantes.cola_fallar(item.get("id"), error)
    elif terminar:
        entrantes.cola_terminar(item.get("id"), archivo=nombre,
                                paso=paso or "Texto y análisis listos para editar")
    else:
        entrantes.cola_actualizar(item.get("id"), pct=pct, paso=paso, archivo=nombre)


def _estudio_ruta(nombre):
    """La ruta de un audio del Estudio, o None si el nombre es raro o no existe.

    Busca en las dos carpetas: primero las FUENTES (`entrantes/`, donde caen solos los
    audios de WhatsApp y Telegram y tambien los que se suben del disco) y despues las
    uniones ya hechas. Asi el mismo endpoint sirve para escuchar un pedazo y para
    escuchar el resultado, y `_unir_audios` puede usar una union vieja como pista.
    """
    if not nombre or not _NOMBRE_OK.fullmatch(str(nombre)):
        return None
    for carpeta in (ESTUDIO_ENTRANTES, ESTUDIO):
        f = carpeta / nombre
        if f.is_file():
            return f
    return None


def _unir_audios(pistas, silencio, destino):
    """Pega los audios uno atras del otro y deja un mp3 en `destino`.

    Cada pista es {"archivo", "ini", "fin"}: el recorte va en segundos y **no toca el
    archivo original**, son numeros que se le pasan a ffmpeg (misma decision que el
    recorte de imagenes de la pizarra: siempre hay vuelta atras y no se pierde calidad
    al recortar de nuevo). Entre una pista y la siguiente van `silencio` segundos.

    Devuelve (ok, error).
    """
    if not pistas:
        return False, "no hay audios para unir"
    entradas, filtros, etiquetas = [], [], []
    for i, p in enumerate(pistas):
        ruta = _estudio_ruta(p.get("archivo"))
        if not ruta:
            return False, "falta el archivo %s" % p.get("archivo")
        entradas += ["-i", str(ruta)]
        ini = max(0.0, float(p.get("ini") or 0))
        fin = float(p.get("fin") or 0)
        pasos = []
        if ini > 0 or fin > ini:
            corte = ["start=%.3f" % ini] if ini > 0 else []
            if fin > ini:
                corte.append("end=%.3f" % fin)
            pasos.append("atrim=" + ":".join(corte))
        # Despues de cortar, los tiempos tienen que arrancar de cero: sin esto concat
        # respeta el hueco del pedazo que sacamos y quedan silencios al principio.
        pasos.append("asetpts=N/SR/TB")
        # Todas las pistas tienen que quedar en el MISMO formato o concat se planta: un
        # audio de WhatsApp es mono a 16 kHz y un mp3 del telefono es estereo a 44,1.
        pasos.append("aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo")
        if silencio > 0 and i < len(pistas) - 1:
            pasos.append("apad=pad_dur=%.3f" % silencio)   # el silencio va PEGADO al final
        filtros.append("[%d:a]%s[a%d]" % (i, ",".join(pasos), i))
        etiquetas.append("[a%d]" % i)
    filtros.append("%sconcat=n=%d:v=0:a=1[out]" % ("".join(etiquetas), len(pistas)))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *entradas,
           "-filter_complex", ";".join(filtros), "-map", "[out]",
           "-c:a", "libmp3lame", "-b:a", "160k", str(destino)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                           creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg tardo demasiado (mas de 10 minutos)"
    if r.returncode != 0 or not destino.is_file():
        return False, (r.stderr or "ffmpeg no pudo").strip()[:400]
    return True, ""


def _unir_videos(pistas, destino):
    """Recorta y pega videos manteniendo imagen, audio y texto en el mismo tiempo.

    Normaliza cada tramo a 720p/30 fps y AAC antes de concatenar: los videos de
    Telegram pueden mezclar vertical/horizontal, resoluciones y codecs distintos.
    El original nunca se toca; `ini` y `fin` son solo números para ffmpeg.
    """
    if not pistas:
        return False, "no hay videos para unir"
    entradas, filtros, etiquetas = [], [], []
    for i, p in enumerate(pistas):
        ruta = _estudio_ruta(p.get("archivo"))
        if not ruta:
            return False, "falta el archivo %s" % p.get("archivo")
        if ruta.suffix.lower() not in entrantes.EXT_VIDEO:
            return False, "para armar un video, todas las pistas tienen que ser videos"
        entradas += ["-i", str(ruta)]
        ini = max(0.0, float(p.get("ini") or 0))
        fin = float(p.get("fin") or 0)
        corte_v = "trim=start=%.3f" % ini
        corte_a = "atrim=start=%.3f" % ini
        if fin > ini:
            corte_v += ":end=%.3f" % fin
            corte_a += ":end=%.3f" % fin
        filtros.append(
            "[%d:v]%s,setpts=PTS-STARTPTS," % (i, corte_v) +
            "scale=1280:720:force_original_aspect_ratio=decrease," +
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v%d]" % i)
        filtros.append(
            "[%d:a]%s,asetpts=N/SR/TB," % (i, corte_a) +
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a%d]" % i)
        etiquetas.append("[v%d][a%d]" % (i, i))
    filtros.append("%sconcat=n=%d:v=1:a=1[v][a]" % ("".join(etiquetas), len(pistas)))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *entradas,
           "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destino)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200,
                           creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg tardó demasiado (más de 20 minutos)"
    if r.returncode != 0 or not destino.is_file():
        return False, (r.stderr or "ffmpeg no pudo").strip()[:400]
    return True, ""


def _miniaturas_video(ruta, destino, cantidad=8):
    """Arma una tira de fotogramas para elegir un punto del video sin reproducirlo.

    Busca ocho momentos repartidos y los compone en 4x2. Sale a disco como cache: pedir
    la misma tira otra vez es leer un jpg, no volver a abrir el video con ffmpeg.
    """
    ruta, destino = Path(ruta), Path(destino)
    if destino.is_file() and destino.stat().st_mtime >= ruta.stat().st_mtime:
        return True, ""
    dur = entrantes.duracion(ruta)
    if dur <= 0:
        return False, "no pude saber cuánto dura el video"
    cantidad = max(2, min(12, int(cantidad)))
    # El centro de cada parte, en vez del segundo 0: evita ocho fotos negras del fundido.
    tiempos = [min(max(0.0, dur - 0.04), dur * (i + 0.5) / cantidad)
               for i in range(cantidad)]
    entradas, filtros, etiquetas, lugares = [], [], [], []
    # Hacer cada casilla par evita que algunos H.264 verticales salgan un pixel más
    # altos que el pad al redondear (ffmpeg entonces rechaza toda la tira).
    ancho, alto, columnas = 240, 136, 4
    for i, segundo in enumerate(tiempos):
        entradas += ["-ss", "%.3f" % segundo, "-i", str(ruta)]
        filtros.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1[v%d]" %
            (i, ancho, alto, ancho, alto, i))
        etiquetas.append("[v%d]" % i)
        lugares.append("%d_%d" % ((i % columnas) * ancho, (i // columnas) * alto))
    filtros.append("%sxstack=inputs=%d:layout=%s:fill=black[out]" %
                   ("".join(etiquetas), cantidad, "|".join(lugares)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.jpg")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *entradas,
           "-filter_complex", ";".join(filtros), "-map", "[out]", "-frames:v", "1",
           "-q:v", "4", str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg tardó demasiado haciendo las miniaturas"
    if r.returncode != 0 or not tmp.is_file():
        return False, (r.stderr or "ffmpeg no pudo hacer las miniaturas").strip()[:400]
    tmp.replace(destino)
    return True, ""


def _tiempo_estudio(segundos):
    """Reloj corto para la ficha que lee una sesión (00:14 o 1:02:03)."""
    segundos = max(0, int(round(float(segundos or 0))))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return "%d:%02d:%02d" % (horas, minutos, segundos)
    return "%02d:%02d" % (minutos, segundos)


def _contexto_estudio(pistas, silencio, medio, mosaico, perfil=""):
    """La ficha legible que acompaña al medio cuando se lo pasa a una sesión.

    Los tiempos se recalculan sobre el archivo ARMADO. Una frase que estaba en el
    minuto 18 del original puede quedar en 00:06 en la selección; ese segundo es el
    que le sirve a la sesión para mirar el video que recibió.
    """
    es_video = medio.suffix.lower() == ".mp4"
    cursor = 0.0
    frases, visuales, cortes = [], [], []
    analisis_fuente, vistos = [], set()

    for i, p in enumerate(pistas):
        ruta = _estudio_ruta(p["archivo"])
        ini, fin = float(p["ini"]), float(p["fin"])
        cortes.append((ruta, ini, fin, cursor))

        for s in entrantes.segmentos_de(p["archivo"]):
            try:
                desde = float(s.get("inicio") or 0)
                hasta = float(s.get("fin") or desde)
            except (TypeError, ValueError):
                continue
            if desde < ini - 0.01 or desde >= fin:
                continue
            texto = str(s.get("texto") or "").strip()
            if not texto:
                continue
            nuevo_desde = cursor + max(0.0, desde - ini)
            nuevo_hasta = cursor + max(0.0, min(fin, hasta) - ini)
            frases.append((nuevo_desde, max(nuevo_desde, nuevo_hasta), texto))

        analisis = entrantes.analisis_de(p["archivo"])
        if isinstance(analisis, dict):
            for v in (analisis.get("transcripcion_visual") or []):
                if not isinstance(v, dict):
                    continue
                try:
                    segundo = float(v.get("segundo") or 0)
                except (TypeError, ValueError):
                    continue
                descripcion = str(v.get("descripcion") or "").strip()
                if descripcion and ini - 0.01 <= segundo < fin:
                    visuales.append((cursor + max(0.0, segundo - ini), descripcion))
            if p["archivo"] not in vistos:
                vistos.add(p["archivo"])
                try:
                    from app.nucleo import analizar_gemini
                    analisis_fuente.append((ruta, analizar_gemini.formato_legible(analisis)))
                except Exception:
                    pass

        cursor += max(0.0, fin - ini)
        if not es_video and silencio > 0 and i < len(pistas) - 1:
            cursor += silencio

    armado = entrantes.analisis_armado(pistas, perfil)
    lineas = [
        "# Selección enviada desde el Estudio",
        "",
        "- Tipo: %s" % ("video" if es_video else "audio"),
        "- Duración del armado: %s" % _tiempo_estudio(cursor),
        "- Fragmentos elegidos: %d" % len(pistas),
        "- Archivo armado: `%s`" % medio.resolve(),
    ]
    if mosaico:
        lineas.append("- Mosaico visual: `%s`" % mosaico.resolve())

    lineas += ["", "## Transcripción de los fragmentos", ""]
    if frases:
        for desde, hasta, texto in frases:
            lineas.append("[%s–%s] %s" %
                          (_tiempo_estudio(desde), _tiempo_estudio(hasta), texto))
    else:
        texto = entrantes.texto_recortado(pistas)
        lineas.append(texto or "No hay transcripción disponible para estos fragmentos.")

    if es_video:
        lineas += ["", "## Lo que Gemini detectó visualmente en estos fragmentos", ""]
        if visuales:
            for segundo, descripcion in visuales:
                lineas.append("[%s] %s" % (_tiempo_estudio(segundo), descripcion))
        else:
            lineas.append("No hay momentos visuales guardados dentro de estos cortes.")

    lineas += ["", "## Análisis inteligente", ""]
    if isinstance(armado, dict) and str(armado.get("texto") or "").strip():
        lineas.append("### Análisis de este armado")
        lineas.append("")
        lineas.append(str(armado["texto"]).strip())
    elif analisis_fuente:
        lineas.append("Todavía no se pidió un análisis específico de este armado. "
                      "Debajo está el análisis automático de los originales como contexto.")
    else:
        lineas.append("No hay un análisis inteligente guardado para este material.")

    for ruta, texto in analisis_fuente:
        lineas += ["", "### Contexto del original `%s`" % ruta.name, "", texto]

    lineas += ["", "## Origen exacto de cada fragmento", ""]
    for i, (ruta, ini, fin, salida) in enumerate(cortes, 1):
        lineas.append("%d. `%s` — original %s–%s → armado desde %s" %
                      (i, ruta.resolve(), _tiempo_estudio(ini), _tiempo_estudio(fin),
                       _tiempo_estudio(salida)))
    lineas += ["", "Trabajá sobre los fragmentos elegidos, no sobre las partes descartadas.", ""]
    return "\n".join(lineas), cursor


def _preparar_paquete_estudio(pistas, silencio=0.0, proyecto="", perfil=""):
    """Arma el medio y su ficha para compartirlos con Claude o Codex.

    No llama a ningún modelo: reutiliza la transcripción y el análisis que ya están
    guardados. El único trabajo pesado es ffmpeg, igual que al tocar "Armar".
    """
    limpias, tipos = [], set()
    for p in pistas or []:
        if not isinstance(p, dict):
            continue
        archivo = str(p.get("archivo") or "")
        if not _NOMBRE_OK.fullmatch(archivo):
            continue
        ruta = _estudio_ruta(archivo)
        if not ruta or ruta.suffix.lower() not in entrantes.EXT_MEDIA:
            continue
        try:
            ini = max(0.0, float(p.get("ini") or 0))
            fin = float(p.get("fin") or 0)
        except (TypeError, ValueError):
            continue
        dur = entrantes.duracion(ruta)
        if fin <= ini:
            fin = dur
        if dur > 0:
            fin = min(fin, dur)
        if fin <= ini + 0.04:
            continue
        tipo = "video" if ruta.suffix.lower() in entrantes.EXT_VIDEO else "audio"
        tipos.add(tipo)
        limpias.append({"archivo": archivo, "ini": ini, "fin": fin})

    if not limpias:
        return {"ok": False, "error": "no hay fragmentos válidos para enviar"}
    if len(tipos) != 1:
        return {"ok": False, "error": "audio y video se pasan a una sesión por separado"}

    try:
        silencio = max(0.0, min(5.0, float(silencio or 0)))
    except (TypeError, ValueError):
        silencio = 0.0
    ESTUDIO.mkdir(parents=True, exist_ok=True)
    proy = re.sub(r"[^\w-]+", "-", str(proyecto or "").strip())[:30].strip("-")
    sello = time.strftime("%Y-%m-%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    base = "para_sesion_%s%s" % ((proy + "_") if proy else "", sello)
    es_video = "video" in tipos
    medio = ESTUDIO / (base + (".mp4" if es_video else ".mp3"))
    ok, error = (_unir_videos(limpias, medio) if es_video
                 else _unir_audios(limpias, silencio, medio))
    if not ok:
        try:
            medio.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": False, "error": error}

    mosaico = None
    advertencia = ""
    if es_video:
        candidato = ESTUDIO / (base + "_mosaico.jpg")
        ok_mosaico, error_mosaico = _miniaturas_video(medio, candidato)
        if ok_mosaico:
            mosaico = candidato
        else:
            advertencia = "El video y la transcripción están listos, pero no salió el mosaico: " + error_mosaico

    texto, duracion = _contexto_estudio(limpias, silencio, medio, mosaico, perfil)
    contexto = ESTUDIO / (base + ".md")
    contexto.write_text(texto, encoding="utf-8")
    return {"ok": True, "archivo": medio.name, "ruta_medio": str(medio.resolve()),
            "ruta_contexto": str(contexto.resolve()),
            "ruta_mosaico": str(mosaico.resolve()) if mosaico else "",
            "tipo": "video" if es_video else "audio", "dur": duracion,
            "fragmentos": len(limpias), "advertencia": advertencia}


@app.get("/estudio", response_class=HTMLResponse)
def estudio_pagina():
    """El estudio de audio: soltas varios audios, los ordenas y sale uno solo.

    Sin cache, igual que los .js: la pantalla entera vive en este archivo, y con el
    navegador guardandoselo un arreglo se ve arreglado aca y roto en la pantalla de
    Martin. Paso el 2026-08-18 con la ultima frase tachada.
    """
    return FileResponse(ESTATICOS / "estudio.html", media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/estudio/entrantes")
def estudio_entrantes():
    """Los audios disponibles para armar la union, del mas nuevo al mas viejo.

    ⭐ Aca esta el corazon del pedido de Martin: los audios llegan **mandandolos por
    WhatsApp o por Telegram** (los guarda `app/nucleo/entrantes.py` desde el pipeline
    de transcripcion) y se eligen LEYENDO lo que dicen — cada uno viene con su
    transcripcion, el canal por el que entro y quien lo mando. Sin eso habria que
    adivinar cual es cual por un nombre como `evo_968e8c50`.
    """
    return {"ok": True, "audios": entrantes.listar()}


@app.get("/estudio/segmentos/{nombre}")
def estudio_segmentos(nombre: str):
    """La transcripcion CON MARCAS DE TIEMPO de un audio, para cortarlo leyendo.

    Va aparte de `/estudio/entrantes` a proposito: un audio de 13 minutos tiene ~200
    segmentos y la lista se pide cada 20 s desde cada pestaña. Esto se pide una sola
    vez, cuando abris el texto de esa pista.
    """
    if not _NOMBRE_OK.fullmatch(nombre or ""):
        return {"ok": False, "error": "nombre invalido"}
    return {"ok": True, "segmentos": entrantes.segmentos_de(nombre)}


@app.post("/estudio/segmentos/{nombre}")
async def estudio_segmentos_guardar(nombre: str, request: Request):
    """Guarda las correcciones manuales hechas sobre la transcripcion del Estudio."""
    if not _NOMBRE_OK.fullmatch(nombre or ""):
        return {"ok": False, "error": "nombre invalido"}
    d = await request.json()
    segmentos = d.get("segmentos") or []
    if not isinstance(segmentos, list) or len(segmentos) > 5000:
        return {"ok": False, "error": "segmentos invalidos"}
    limpios = []
    try:
        for s in segmentos:
            if not isinstance(s, dict):
                raise ValueError
            texto = str(s.get("texto") or "").strip()
            if len(texto) > 10000:
                return {"ok": False, "error": "una frase es demasiado larga"}
            limpios.append({"inicio": float(s.get("inicio") or 0),
                            "fin": float(s.get("fin") or 0), "texto": texto})
    except (TypeError, ValueError):
        return {"ok": False, "error": "segmentos invalidos"}
    texto = " ".join(s["texto"] for s in limpios if s["texto"])
    ok = await asyncio.to_thread(entrantes.poner_transcripcion, nombre, texto, limpios)
    return {"ok": ok, "error": "no pude guardar la transcripcion" if not ok else ""}


@app.post("/estudio/transcribir/{nombre}")
async def estudio_transcribir(nombre: str):
    """Prepara un video para editar: fragmentos de Whisper + lectura visual de Gemini.

    Un video del Estudio no queda habilitado a mitad de camino: hasta que no tenga texto
    Y análisis inteligente guardado, la pantalla sólo muestra su tarjeta de preparación.
    """
    if not _NOMBRE_OK.fullmatch(nombre or ""):
        return {"ok": False, "error": "nombre invalido"}
    ruta = _estudio_ruta(nombre)
    if not ruta:
        return {"ok": False, "error": "no encuentro el archivo"}
    # Una recarga de la página no puede lanzar una segunda copia de Whisper sobre el
    # mismo video. La pantalla que vuelve se engancha a este progreso por GET.
    if not _estudio_progreso_empezar(nombre):
        return {"ok": True, "en_curso": True}
    try:
        # Imports tardíos: abrir el panel no ocupa la GPU ni inicializa Gemini. Sólo se
        # carga al preparar un video concreto.
        from app.nucleo import core, analizar_gemini
        def avanzar(pct, paso):
            # Whisper es la primera parte del trabajo. Reservamos el último tramo para
            # Gemini, para que 100 % siempre signifique realmente "listo para editar".
            avance = round(pct * 0.78)
            _estudio_progreso_poner(nombre, avance, paso, en_curso=True)
            _cola_video_actualizar(nombre, avance, paso)

        datos, _ = await asyncio.to_thread(core.procesar_archivo, ruta, avanzar)
        _estudio_progreso_poner(nombre, 80, "Guardando los fragmentos…", en_curso=True)
        _cola_video_actualizar(nombre, 80, "Guardando los fragmentos…")
        ok = await asyncio.to_thread(
            entrantes.poner_transcripcion, nombre,
            datos.get("transcripcion") or "", datos.get("segmentos") or [])
        if not ok:
            _estudio_progreso_poner(nombre, paso="No se pudo guardar el texto", en_curso=False,
                                    error="no pude guardar la transcripcion")
            _cola_video_actualizar(nombre, error="no pude guardar la transcripción")
            return {"ok": False, "error": "no pude guardar la transcripcion"}
        _estudio_progreso_poner(nombre, 84, "Analizando el video y sus momentos…", en_curso=True)
        _cola_video_actualizar(nombre, 84, "Analizando el video y sus momentos…")
        analisis = await asyncio.to_thread(analizar_gemini.analizar, datos)
        if not isinstance(analisis, dict) or analisis.get("error"):
            raise RuntimeError((analisis or {}).get("error") or "Gemini no devolvió un análisis válido")
        _estudio_progreso_poner(nombre, 97, "Guardando el análisis inteligente…", en_curso=True)
        _cola_video_actualizar(nombre, 97, "Guardando el análisis inteligente…")
        if not await asyncio.to_thread(entrantes.poner_analisis, nombre, analisis):
            _estudio_progreso_poner(nombre, paso="No se pudo guardar el análisis", en_curso=False,
                                    error="no pude guardar el análisis inteligente")
            _cola_video_actualizar(nombre, error="no pude guardar el análisis inteligente")
            return {"ok": False, "error": "no pude guardar el análisis inteligente"}
        _estudio_progreso_poner(nombre, 100, "Texto y análisis listos para editar", en_curso=False)
        _cola_video_actualizar(nombre, 100, "Texto y análisis listos para editar", terminar=True)
        return {"ok": True, "texto": datos.get("transcripcion") or "",
                "segmentos": entrantes.segmentos_de(nombre), "tiene_analisis": True}
    except Exception as e:
        error = str(e)[:300]
        _estudio_progreso_poner(nombre, paso="No se pudo terminar el análisis del video", en_curso=False,
                                error=error)
        _cola_video_actualizar(nombre, error=error)
        return {"ok": False, "error": error}


@app.get("/estudio/progreso/{nombre}")
def estudio_progreso(nombre: str):
    """El paso y porcentaje del video que se está preparando para el Estudio."""
    if not _NOMBRE_OK.fullmatch(nombre or ""):
        return {"ok": False, "error": "nombre invalido"}
    return {"ok": True, **_estudio_progreso(nombre)}


@app.get("/estudio/cola")
def estudio_cola():
    """La actividad reciente, compartida por la página, WhatsApp y Telegram."""
    return {"ok": True, "items": entrantes.cola_listar()}


@app.get("/estudio/proyectos")
def estudio_proyectos():
    """Las bandejas del Estudio y cuántos audios tiene cada una.

    "Sin clasificar" no es una bandeja de verdad: es dónde caen TODOS los audios al
    llegar. Martín los manda a su proyecto desde la pantalla, que es como pidió que
    fuera — mandar todo sin pensar y clasificar después.
    """
    audios = entrantes.listar()
    cuentas = {}
    for a in audios:
        cuentas[a.get("proyecto") or ""] = cuentas.get(a.get("proyecto") or "", 0) + 1
    return {"ok": True, "proyectos": entrantes.proyectos(),
            "cuentas": cuentas, "total": len(audios)}


@app.post("/estudio/proyectos")
async def estudio_proyectos_guardar(request: Request):
    """Crear, renombrar el orden o borrar bandejas: la pantalla manda la lista entera."""
    d = await request.json()
    return {"ok": True, "proyectos": entrantes.guardar_proyectos(d.get("proyectos") or [])}


@app.post("/estudio/mover")
async def estudio_mover(request: Request):
    """Manda un audio a una bandeja (vacío = sin clasificar)."""
    d = await request.json()
    return {"ok": entrantes.mover(str(d.get("archivo") or ""), d.get("proyecto") or "")}


@app.get("/estudio/analisis/{nombre}")
def estudio_analisis(nombre: str):
    """El analisis que Gemini ya hizo de ese audio cuando entro, listo para leer."""
    if not _NOMBRE_OK.fullmatch(nombre or ""):
        return {"ok": False, "error": "nombre invalido"}
    a = entrantes.analisis_de(nombre)
    if not a:
        return {"ok": True, "texto": "", "visual": [], "vacio": True}
    from app.nucleo import analizar_gemini      # perezoso: el panel arranca sin google-genai
    visual = []
    for v in (a.get("transcripcion_visual") or []):
        if not isinstance(v, dict):
            continue
        try:
            segundo = max(0.0, float(v.get("segundo") or 0))
        except (TypeError, ValueError):
            continue
        descripcion = str(v.get("descripcion") or "").strip()
        if descripcion:
            visual.append({"segundo": segundo, "descripcion": descripcion[:500]})
    return {"ok": True, "texto": analizar_gemini.formato_legible(a), "visual": visual}


@app.post("/estudio/analizar")
async def estudio_analizar(request: Request):
    """Analiza el audio ARMADO (la fila entera, con sus recortes puestos).

    ⭐ No transcribe nada: junta las frases que quedaron adentro de cada recorte —ya
    las tenemos con sus tiempos— y le manda ESE texto a Gemini. O sea que analizar lo
    que armaste no le cuesta ni un segundo de GPU, aunque sean cinco audios de media
    hora. Es la razon por la que guardar los segmentos valia la pena.
    """
    d = await request.json()
    pistas = [p for p in (d.get("pistas") or [])
              if isinstance(p, dict) and _NOMBRE_OK.fullmatch(str(p.get("archivo") or ""))]
    perfil = str(d.get("perfil") or "").strip()
    texto = await asyncio.to_thread(entrantes.texto_recortado, pistas)
    if not texto:
        return {"ok": False, "error": "esos audios no tienen transcripcion con tiempos "
                                      "(son de antes de que existiera); probá con uno nuevo"}

    def _pensar():
        from app.nucleo import analizar_gemini
        kw = {"perfil": perfil} if perfil in analizar_gemini.perfiles_disponibles() else {}
        a = analizar_gemini.analizar({"transcripcion": texto}, **kw)
        return analizar_gemini.formato_legible(a)

    try:
        salida = await asyncio.to_thread(_pensar)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    # Este análisis es de la FILA armada (y de sus cortes), no del audio original.
    # Por eso se guarda aparte: volver a abrir el Estudio o elegir otra bandeja no lo
    # puede borrar, y tampoco pisa el análisis automático que traía cada archivo.
    clave = await asyncio.to_thread(entrantes.guardar_analisis_armado, pistas, perfil, salida, texto)
    # `dicho` viaja tambien para poder copiar la transcripcion sin pedirla de nuevo.
    return {"ok": True, "texto": salida, "letras": len(texto), "dicho": texto,
            "guardado": bool(clave)}


@app.post("/estudio/analizar/guardado")
async def estudio_analisis_armado_guardado(request: Request):
    """Recupera el análisis guardado para la misma fila y el mismo tipo de análisis."""
    d = await request.json()
    pistas = [p for p in (d.get("pistas") or [])
              if isinstance(p, dict) and _NOMBRE_OK.fullmatch(str(p.get("archivo") or ""))]
    perfil = str(d.get("perfil") or "").strip()
    item = await asyncio.to_thread(entrantes.analisis_armado, pistas, perfil)
    if not item:
        return {"ok": True, "guardado": False}
    return {"ok": True, "guardado": True, "texto": item.get("texto") or "",
            "dicho": item.get("dicho") or "", "cuando": item.get("cuando") or 0}


@app.post("/estudio/texto")
async def estudio_texto(request: Request):
    """Lo que DICE la fila con los recortes puestos, para copiar y pegar.

    Es gratis y sale al toque: no toca la GPU ni llama a ningun modelo, solo junta las
    frases que ya estan transcriptas. Va aparte de /estudio/analizar para poder copiar
    la transcripcion sin gastar una llamada a Gemini.
    """
    d = await request.json()
    pistas = [p for p in (d.get("pistas") or [])
              if isinstance(p, dict) and _NOMBRE_OK.fullmatch(str(p.get("archivo") or ""))]
    texto = await asyncio.to_thread(entrantes.texto_recortado, pistas)
    return {"ok": True, "texto": texto, "letras": len(texto)}


@app.post("/estudio/preparar-sesion")
async def estudio_preparar_sesion(request: Request):
    """Prepara el paquete local que después se manda por `/movil/mandar`.

    La conversación recibe rutas a archivos de esta misma máquina, no una copia en
    base64 ni toda la transcripción adentro de la burbuja. Así el mensaje es liviano,
    el material queda estable y Claude/Codex pueden volver a abrirlo durante el turno.
    """
    d = await request.json()
    pistas = d.get("pistas") or []
    return await asyncio.to_thread(
        _preparar_paquete_estudio, pistas, d.get("silencio") or 0,
        str(d.get("proyecto") or ""), str(d.get("perfil") or ""))


@app.get("/estudio/perfiles")
def estudio_perfiles():
    """Los lentes de analisis disponibles (generico, reuniones, ventas, clinica)."""
    from app.nucleo import analizar_gemini
    return {"ok": True, "perfiles": analizar_gemini.perfiles_disponibles(),
            "defecto": analizar_gemini.PERFIL_DEFECTO}


@app.get("/estudio/onda/{nombre}")
def estudio_onda(nombre: str):
    """La forma de la onda ya medida, para no hacérsela decodificar al navegador.

    ⚠ Va con `def` normal: adentro corre ffmpeg la primera vez (después sale de un
    archivo al lado del audio). En un `async def` congelaría el panel entero.
    """
    ruta = _estudio_ruta(nombre)
    if not ruta:
        return {"ok": False, "error": "no existe"}
    return {"ok": True, "picos": entrantes.picos(ruta)}


@app.get("/estudio/miniaturas/{nombre}")
def estudio_miniaturas(nombre: str):
    """Tira de ocho fotos de un video; tocar una lleva a ese momento aproximado."""
    ruta = _estudio_ruta(nombre)
    if not ruta or ruta.suffix.lower() not in entrantes.EXT_VIDEO:
        return JSONResponse({"ok": False, "error": "no existe ese video"}, status_code=404)
    destino = ESTUDIO_MINIATURAS / (ruta.stem + ".jpg")
    ok, error = _miniaturas_video(ruta, destino)
    if not ok:
        return JSONResponse({"ok": False, "error": error}, status_code=500)
    return FileResponse(destino, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


def _estudio_procesar_subida(ruta, nombre):
    """Deja una subida de la página lista para editar, en segundo plano.

    `procesar_a_texto` es el mismo recorrido de WhatsApp y Telegram: Whisper,
    Gemini y recién entonces la copia/ficha del Estudio. El temporal se borra al
    final, nunca desde el request que lanzó este hilo.
    """
    try:
        from app.nucleo import procesar
        procesar.procesar_a_texto(ruta, origen="disco", de=nombre)
    except Exception as e:
        from app.nucleo import core
        core.log(f"  Error preparando subida del Estudio ({nombre}): {e}")
    finally:
        try:
            Path(ruta).unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/estudio/subir")
def estudio_subir(archivos: list[UploadFile] = File(...)):
    """Sumar audios desde el disco de la compu: el camino corto cuando ya estan aca.

    Se guardan con el MISMO mecanismo que lo que llega por WhatsApp (una copia mas su
    ficha al lado), asi los dos caminos terminan en una sola lista para elegir.

    ⚠ Va con `def` normal y no `async def`: ffprobe es bloqueante y FastAPI manda los
    endpoints sincronicos a un hilo. Adentro de un `async` congelaria el panel entero
    (ya paso dos veces, ver /chat/mandar y /movil/hablar).
    """
    ESTUDIO_ENTRANTES.mkdir(parents=True, exist_ok=True)
    guardados, pendientes, errores = [], [], []
    for up in (archivos or []):
        tmp = None
        entregado = False
        try:
            original = Path(up.filename or "audio")
            ext = original.suffix.lower()
            if ext not in entrantes.EXT_MEDIA:
                errores.append("%s no es un audio ni un video" % (original.name or "sin nombre"))
                continue
            # Se escribe primero a un temporal y el hilo de preparación lo entrega al
            # pipeline común. Así la respuesta no queda congelada por Whisper/Gemini y
            # el archivo no aparece como fuente hasta estar completamente listo.
            tmp = ESTUDIO_ENTRANTES / ("_subiendo_%d%s" % (int(time.time() * 1000), ext))
            tmp.write_bytes(up.file.read())
            de = original.stem[:60] or "del disco"
            threading.Thread(target=_estudio_procesar_subida, args=(tmp, de), daemon=True).start()
            entregado = True
            pendientes.append({"nombre": original.name or "archivo", "tipo":
                               "video" if ext in entrantes.EXT_VIDEO else "audio"})
        except Exception as e:
            errores.append("%s: %s" % (up.filename or "archivo", e))
        finally:
            if tmp is not None and not entregado:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
    # Se devuelve la lista entera y no solo lo nuevo: la pantalla repinta la bandeja
    # con esto mismo y no tiene que pedirla de nuevo.
    return {"ok": True, "guardados": guardados, "pendientes": pendientes, "errores": errores,
            "audios": entrantes.listar()}


@app.get("/estudio/lista")
def estudio_lista():
    """Que archivos siguen estando (la pantalla se acuerda de la fila, pero los
    archivos viven aca: si se limpio la carpeta, esa fila ya no sirve)."""
    nombres = []
    for carpeta in (ESTUDIO_ENTRANTES, ESTUDIO):
        if carpeta.is_dir():
            nombres += [f.name for f in carpeta.iterdir() if f.is_file()]
    return {"ok": True, "archivos": sorted(nombres)}


@app.get("/estudio/audio/{nombre}")
def estudio_audio(nombre: str):
    ruta = _estudio_ruta(nombre)
    if not ruta:
        return JSONResponse({"ok": False, "error": "no existe"}, status_code=404)
    return FileResponse(ruta)


@app.post("/estudio/unir")
async def estudio_unir(request: Request):
    """Junta la fila en un mp3 o mp4. El trabajo pesado va a un hilo (`to_thread`):
    ffmpeg puede tardar varios segundos y el panel tiene que seguir contestando."""
    d = await request.json()
    pistas = [p for p in (d.get("pistas") or [])
              if isinstance(p, dict) and _NOMBRE_OK.fullmatch(str(p.get("archivo") or ""))]
    if not pistas:
        return {"ok": False, "error": "no hay pistas para unir"}
    try:
        silencio = max(0.0, min(5.0, float(d.get("silencio") or 0)))
    except (TypeError, ValueError):
        silencio = 0.0
    ESTUDIO.mkdir(parents=True, exist_ok=True)
    # El proyecto va en el NOMBRE del archivo que sale: así, meses después, se sabe de
    # qué era ese mp3 sin abrirlo. Se limpia como un nombre de archivo cualquiera.
    proy = re.sub(r"[^\w-]+", "-", str(d.get("proyecto") or "").strip())[:30].strip("-")
    rutas = [_estudio_ruta(p.get("archivo")) for p in pistas]
    hay_video = any(r and r.suffix.lower() in entrantes.EXT_VIDEO for r in rutas)
    ext = ".mp4" if hay_video else ".mp3"
    destino = ESTUDIO / ("unido_%s%s%s" % (proy + "_" if proy else "",
                                            time.strftime("%Y-%m-%d_%H%M%S"), ext))
    if hay_video:
        ok, err = await asyncio.to_thread(_unir_videos, pistas, destino)
    else:
        ok, err = await asyncio.to_thread(_unir_audios, pistas, silencio, destino)
    if not ok:
        return {"ok": False, "error": err}
    dur = await asyncio.to_thread(entrantes.duracion, destino)
    return {"ok": True, "archivo": destino.name, "dur": dur,
            "tipo": "video" if hay_video else "audio"}


def _env(*claves):
    """Lee variables del .env sin cachearlas (mismo criterio que _laura_voz_token)."""
    from dotenv import dotenv_values
    cfg = dotenv_values(ENV) or {}
    return [(cfg.get(c) or "").strip() for c in claves]


def _mandar_telegram(ruta, titulo):
    """Manda el resultado por Telegram como audio o video reproducible."""
    token, dest = _env("TELEGRAM_TOKEN", "TELEGRAM_DEST_ID")
    if not (token and dest):
        return False, "faltan TELEGRAM_TOKEN o TELEGRAM_DEST_ID en el .env"
    es_video = Path(ruta).suffix.lower() in entrantes.EXT_VIDEO
    metodo, campo, mime = (("sendVideo", "video", "video/mp4") if es_video
                           else ("sendAudio", "audio", "audio/mpeg"))
    datos = {"chat_id": dest}
    if not es_video:
        datos["title"] = titulo
    with open(ruta, "rb") as f:
        r = requests.post("https://api.telegram.org/bot%s/%s" % (token, metodo),
                          data=datos, files={campo: (Path(ruta).name, f, mime)}, timeout=300)
    if r.status_code != 200:
        return False, "Telegram contesto %s: %s" % (r.status_code, r.text[:180])
    return True, ""


def _mandar_whatsapp(ruta):
    """Manda el mp3 por WhatsApp como NOTA DE VOZ, via Evolution API."""
    from urllib.parse import quote
    # ⭐ Solo escucha (2026-08-21): al numero viejo lo bloqueo WhatsApp por mandar
    # mensajes, asi que el nuevo no manda NADA. El audio del Estudio sale por Telegram.
    if (os.environ.get("WPP_SOLO_ESCUCHA", "").strip() not in ("", "0", "no")):
        return False, ("el WhatsApp de Laura esta en solo escucha para no perder el "
                       "numero: mandalo por Telegram")
    url, apikey, inst, numero = _env("EVOLUTION_API_URL", "EVOLUTION_API_KEY",
                                     "EVOLUTION_INSTANCE", "MI_WHATSAPP")
    if not (url and apikey and inst and numero):
        return False, "faltan EVOLUTION_API_URL/_KEY/_INSTANCE o MI_WHATSAPP en el .env"
    # ⚠ El base64 va PELADO: con el prefijo "data:audio/mpeg;base64," esta instancia
    # contesta 400. Ya costo un rato en pruebas/mandar_audio_wpp.py.
    audio64 = base64.b64encode(Path(ruta).read_bytes()).decode()
    # ⚠ El nombre de la instancia tiene espacio Y tilde ("wpp Consultoria 3"): sin
    # url-encodearlo entero, la peticion revienta al querer mandar la URL en ascii.
    r = requests.post("%s/message/sendWhatsAppAudio/%s" % (url.rstrip("/"), quote(inst, safe="")),
                      json={"number": "".join(c for c in numero if c.isdigit()),
                            "audio": audio64},
                      headers={"apikey": apikey}, timeout=180)
    if r.status_code >= 300:
        return False, "Evolution contesto %s: %s" % (r.status_code, r.text[:180])
    return True, ""


@app.post("/estudio/mandar")
async def estudio_mandar(request: Request):
    """Te manda el audio armado AL CELULAR, para tenerlo donde lo vas a reenviar.

    ⭐ El destino es FIJO y sos vos (`TELEGRAM_DEST_ID` / `MI_WHATSAPP` del .env), igual
    que los avisos. Un boton que le mande un audio a un tercero desde una pantalla es un
    error de un solo clic, y de los que no se pueden deshacer; asi, lo peor que puede
    pasar es que te llegue a vos y lo reenvies vos desde el telefono, que es un toque.

    Va a un hilo: subir varios MB por una red lenta bloquearia el panel entero.
    """
    d = await request.json()
    ruta = _estudio_ruta(str(d.get("archivo") or ""))
    if not ruta:
        return {"ok": False, "error": "ese audio ya no esta"}
    por = str(d.get("por") or "telegram").lower()
    if por not in ("telegram", "whatsapp"):
        return {"ok": False, "error": "no se mandar por %s" % por}
    try:
        if por == "telegram":
            ok, err = await asyncio.to_thread(_mandar_telegram, ruta, ruta.stem)
        else:
            ok, err = await asyncio.to_thread(_mandar_whatsapp, ruta)
    except Exception as e:
        ok, err = False, str(e)[:180]
    print("estudio: %s por %s -> %s" % (ruta.name, por, "ok" if ok else err), flush=True)
    return {"ok": ok, "error": err}


@app.post("/estudio/borrar")
async def estudio_borrar(request: Request):
    """Saca un audio de la lista de fuentes: borra la COPIA y su ficha.

    Nunca toca un original de Martin — lo que vive en esta carpeta lo puso el
    pipeline de transcripcion o `/estudio/subir`, y el audio sigue en su WhatsApp.
    """
    d = await request.json()
    return {"ok": entrantes.borrar(str(d.get("archivo") or ""))}


@app.get("/movil/icono.png")
def movil_icono():
    """El icono de la pantalla de inicio (lo dibuja pruebas/hacer_icono_laura.py)."""
    return FileResponse(ESTATICOS / "icono_laura.png", media_type="image/png")


@app.get("/movil/manifest.json")
def movil_manifest():
    """Para que se pueda 'agregar a la pantalla de inicio' y se abra sin barra del navegador."""
    return {"name": "Laura", "short_name": "Laura", "start_url": "/movil",
            "display": "standalone", "background_color": "#0b0d12",
            "theme_color": "#0b0d12",
            "icons": [{"src": "/movil/icono.png", "sizes": "180x180", "type": "image/png"}]}


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:
        _f = open(LOGS / "panel.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = _f
        sys.stderr = _f
    silenciar_reset_windows()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
