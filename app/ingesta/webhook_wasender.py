"""
Servicio de transcripcion para WhatsApp (WaSenderAPI).

Dos modos:
  - /transcribe : lo llama TU n8n (VPS). Recibe el payload de WaSenderAPI,
                  baja el audio/video, transcribe en la 4070, analiza con Gemini
                  y DEVUELVE el JSON (n8n decide que hacer, ej. mandarlo a Telegram).
                  Protegido con el header X-Auth-Token (LAPTOP_SHARED_SECRET).
  - /webhook    : modo directo (WaSenderAPI -> laptop). Manda el resultado a Telegram
                  el mismo. Verifica X-Webhook-Signature. (queda como alternativa)

Se expone a internet con un tunel de cloudflared (ver wpp-config.ejemplo.yml).

Correr:  uvicorn webhook_wasender:app --host 0.0.0.0 --port 8080
"""

import os
import json
import uuid
import asyncio
import mimetypes
import tempfile
import threading
from pathlib import Path

os.environ.pop("SSLKEYLOGFILE", None)  # Avast rompe el SSL de Python

import truststore
truststore.inject_into_ssl()

from dotenv import load_dotenv

from app.rutas import ENV, WPP_FOTOS
load_dotenv(ENV)

import shutil
import requests
from fastapi import FastAPI, Request, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse

from app.nucleo import core
from app.voz import buzon
from app.nucleo import analizar_gemini
from app.nucleo import procesar
from app.nucleo import entrantes      # guardar el audio recibido para el Estudio

WASENDER_API_KEY     = os.environ.get("WASENDER_API_KEY", "")
WEBHOOK_SECRET       = os.environ.get("WASENDER_WEBHOOK_SECRET", "")
LAPTOP_SHARED_SECRET = os.environ.get("LAPTOP_SHARED_SECRET", "")
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_DEST_ID     = os.environ.get("TELEGRAM_DEST_ID", "")
EVOLUTION_API_URL    = os.environ.get("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_API_KEY    = os.environ.get("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE   = os.environ.get("EVOLUTION_INSTANCE", "")
# ⭐ Solo escucha (2026-08-21): al numero viejo lo bloquearon por mandar mensajes.
# El nuevo recibe audios y NO contesta por WhatsApp; la transcripcion sale por
# Telegram, como siempre. Perilla WPP_SOLO_ESCUCHA en el .env.
WPP_SOLO_ESCUCHA     = os.environ.get("WPP_SOLO_ESCUCHA", "").strip() not in ("", "0", "no")

DECRYPT_URL = "https://www.wasenderapi.com/api/decrypt-media"

# Los GRUPOS no se procesan. Desde que este numero esta en un grupo de trabajo,
# cada audio que manda cualquiera de los 11 se transcribiria y le llegaria a
# Martin por Telegram: GPU, tokens de Gemini y charla ajena metida en el pipeline
# sin que nadie lo pida. Regla al reves de la de Telegram (alla los grupos SI se
# usan a proposito): aca hay que nombrar explicitamente el grupo que se quiere.
# WPP_GRUPOS_OK en el .env, JIDs separados por coma ("...@g.us").
GRUPOS_OK = {g.strip() for g in os.environ.get("WPP_GRUPOS_OK", "").split(",") if g.strip()}

app = FastAPI(title="Transcriptor WhatsApp")


# ---------------------- Telegram (salida, modo directo) --------
def tg_enviar(texto: str):
    if not (TELEGRAM_TOKEN and TELEGRAM_DEST_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for i in range(0, len(texto), 3900):
        # Reintentos con espera: un hipo de DNS no puede tirar a la basura la
        # transcripcion de una hora de audio (paso: NameResolutionError transitorio).
        for intento in range(4):
            try:
                requests.post(url, json={"chat_id": TELEGRAM_DEST_ID,
                                         "text": texto[i:i + 3900]}, timeout=30)
                break
            except Exception as e:
                core.log(f"  Error enviando a Telegram (intento {intento + 1}/4): {e}")
                if intento < 3:
                    import time as _t
                    _t.sleep(5 * (intento + 1))       # 5s, 10s, 15s


# ---------------------- Evolution API (salida, WhatsApp directo) --------
def evolution_enviar(remote_jid: str, texto: str):
    """Manda un mensaje de WhatsApp via Evolution API, directo desde la laptop
    (sin pasar por n8n para el camino de vuelta). remote_jid se manda TAL CUAL
    llego del webhook (aunque sea @lid) -- no hace falta el numero real, ver
    PIZARRA 2026-08-11. Mismos reintentos que tg_enviar: un hipo de red no
    puede perder una transcripcion que ya está lista."""
    if WPP_SOLO_ESCUCHA:
        core.log("  WhatsApp en solo escucha: la transcripcion sale por Telegram nomas.")
        return
    if not (EVOLUTION_API_URL and EVOLUTION_API_KEY and EVOLUTION_INSTANCE and remote_jid):
        return
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    for i in range(0, len(texto), 3900):
        for intento in range(4):
            try:
                requests.post(url, headers=headers,
                              json={"number": remote_jid, "text": texto[i:i + 3900]}, timeout=30)
                break
            except Exception as e:
                core.log(f"  Error enviando a WhatsApp/Evolution (intento {intento + 1}/4): {e}")
                if intento < 3:
                    import time as _t
                    _t.sleep(5 * (intento + 1))       # 5s, 10s, 15s


_NOMBRES_GRUPO = {}


def nombre_grupo(jid: str) -> str:
    """El nombre visible de un grupo ("Audios"), para no guardar el JID pelado.

    Se le pregunta a Evolution UNA vez por grupo y queda en memoria: en la bandeja del
    Estudio "Audios" se lee, y `120363000000000000@g.us` no. Si la consulta falla se
    devuelve el JID — que la bandeja se vea fea nunca puede costar una transcripcion.
    """
    if not str(jid).endswith("@g.us"):
        return jid
    if jid in _NOMBRES_GRUPO:
        return _NOMBRES_GRUPO[jid]
    nombre = jid
    try:
        r = requests.get(f"{EVOLUTION_API_URL}/group/findGroupInfos/{EVOLUTION_INSTANCE}",
                         params={"groupJid": jid}, headers={"apikey": EVOLUTION_API_KEY},
                         timeout=20)
        if r.status_code == 200:
            nombre = (r.json() or {}).get("subject") or jid
    except Exception as e:
        core.log(f"  (no pude leer el nombre del grupo {jid}: {e})")
    _NOMBRES_GRUPO[jid] = nombre
    return nombre


# ---------------------- WaSenderAPI (media) --------------------
def _msg_obj(payload: dict):
    data = payload.get("data") or {}
    m = data.get("messages")
    if isinstance(m, list):
        return m[0] if m else None
    return m


def _media_del_mensaje(msg: dict):
    contenido = (msg or {}).get("message") or {}
    for clave in ("audioMessage", "videoMessage", "imageMessage"):
        if clave in contenido and contenido[clave]:
            return clave, contenido[clave]
    doc = contenido.get("documentMessage")
    if doc and str(doc.get("mimetype", "")).startswith(("audio/", "video/", "image/")):
        return "documentMessage", doc
    return None, None


def bajar_media(msg: dict) -> Path:
    body = {"data": {"messages": msg}}
    headers = {"Authorization": f"Bearer {WASENDER_API_KEY}"}
    r = requests.post(DECRYPT_URL, json=body, headers=headers, timeout=120)  # media pesada tarda mas en desencriptar
    r.raise_for_status()
    j = r.json()
    public_url = j.get("publicUrl") or j.get("public_url")
    if not public_url:
        raise RuntimeError(f"decrypt-media no devolvio publicUrl: {j}")

    _, media = _media_del_mensaje(msg)
    mime = (media or {}).get("mimetype", "").split(";")[0]
    ext = mimetypes.guess_extension(mime) or (".ogg" if mime.startswith("audio") else ".mp4")
    if ext == ".oga":
        ext = ".ogg"

    dest = Path(tempfile.gettempdir()) / f"wa_{msg.get('key', {}).get('id', 'msg')}{ext}"
    with requests.get(public_url, stream=True, timeout=(30, 300)) as resp:  # (conectar, leer): margen para media pesada
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
    return dest


# ---------------------- Procesamiento --------------------------
def _texto_para_telegram(remitente, datos, analisis):
    partes = [f"📱 WhatsApp de {remitente}", "",
              "📝 Transcripcion:", datos.get("transcripcion") or "(sin voz detectada)", "",
              analizar_gemini.formato_legible(analisis)]
    return "\n".join(partes)


# Esta linea de WhatsApp le llega HOY a un cirujano real: el default queda en
# "clinica" a proposito para no cambiarle el analisis a nadie sin querer.
# Otros numeros/otros clientes van con PERFIL_DEFECTO_WHATSAPP distinto, o
# pasando "perfil" en el payload que arma n8n.
PERFIL_DEFECTO_WHATSAPP = "clinica"


def procesar_mensaje(msg: dict, remitente: str, perfil: str = PERFIL_DEFECTO_WHATSAPP) -> dict:
    """Baja el media (audio/video/imagen), lo procesa y arma el texto para Telegram."""
    archivo = bajar_media(msg)
    try:
        cuerpo = procesar.procesar_a_texto(archivo, perfil=perfil,
                                           origen="whatsapp", de=remitente)
        return {
            "ok": True,
            "remitente": remitente,
            "texto_telegram": f"📱 WhatsApp de {remitente}\n\n{cuerpo}",
        }
    finally:
        try:
            Path(archivo).unlink(missing_ok=True)
        except Exception:
            pass


def _remitente(msg):
    k = msg.get("key") or {}
    return k.get("cleanedSenderPn") or k.get("remoteJid") or "desconocido"


def _grupo_prohibido(msg):
    """Devuelve el JID del grupo si hay que ignorar el mensaje, o None.

    En un grupo, remoteJid es el grupo y participant es quien hablo; por eso no
    alcanza con mirar el remitente.
    """
    jid = str((msg.get("key") or {}).get("remoteJid") or "")
    if jid.endswith("@g.us") and jid not in GRUPOS_OK:
        return jid
    return None


# ---------------------- Endpoints ------------------------------
@app.get("/")
def salud():
    return {"ok": True, "servicio": "transcriptor-whatsapp"}


@app.post("/transcribe")
async def transcribe(request: Request, x_auth_token: str = Header(default="")):
    """Lo llama n8n. Devuelve el JSON con transcripcion + analisis."""
    if LAPTOP_SHARED_SECRET and x_auth_token != LAPTOP_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="token invalido")

    payload = await request.json()
    msg = _msg_obj(payload)
    if not msg:
        return {"ok": True, "skip": True, "motivo": "sin mensaje"}
    if (msg.get("key") or {}).get("fromMe"):
        return {"ok": True, "skip": True, "motivo": "mensaje propio"}
    grupo = _grupo_prohibido(msg)
    if grupo:
        core.log(f"/transcribe: ignoro el grupo {grupo}")
        return {"ok": True, "skip": True, "motivo": "grupo no autorizado"}
    tipo, _ = _media_del_mensaje(msg)
    if not tipo:
        return {"ok": True, "skip": True, "motivo": "no es audio/video"}

    remitente = _remitente(msg)
    perfil = payload.get("perfil") or (payload.get("data") or {}).get("perfil") or PERFIL_DEFECTO_WHATSAPP
    core.log(f"/transcribe: {remitente} ({tipo}, perfil={perfil})")
    return await asyncio.to_thread(procesar_mensaje, msg, remitente, perfil)


# ---------------------- Hablarle a Laura por WhatsApp --------------------
# Pedido de Martin el 2026-08-15: escribirle por WhatsApp y que conteste igual que por
# Telegram, con la MISMA sesion y la misma memoria. Por eso no habla con el CLI: le deja
# la pregunta a voz.py por el buzon de archivos, igual que el bot de Telegram (dos
# procesos sobre la misma sesion la bifurcarian).
#
# ⭐ SOLO MARTIN. Laura ejecuta comandos en esta PC: un WhatsApp abierto seria darle la
# computadora a cualquiera que sepa el numero. Sin `MI_WHATSAPP` configurado, esto queda
# APAGADO, no "abierto por las dudas" (mismo criterio que la pagina de llamada).
# Puede haber VARIOS identificadores separados por coma: WhatsApp ya no siempre manda el
# numero. A Martin lo identifica con un "lid" (un codigo interno de Meta) que no se parece
# en nada a su telefono, asi que hay que listar los dos.
MIS_WHATSAPP = {x.strip() for x in os.environ.get("MI_WHATSAPP", "").split(",") if x.strip()}
LAURA_ESPERA = 620          # lo mismo que aguanta el bot de Telegram


def _es_martin(quien: str) -> bool:
    """Comparacion EXACTA contra la parte de adelante del jid, no 'contiene'.

    Con `in` alcanzaria que un identificador ajeno tuviera adentro la cadena de uno
    autorizado para colarse. Y lo que se cuela acá tiene una Laura que ejecuta comandos
    en la maquina: el 2026-08-15 llego un mensaje de Lautaro por este mismo camino.
    """
    if not MIS_WHATSAPP:
        return False
    return str(quien or "").split("@")[0].strip() in MIS_WHATSAPP


# Quien esta esperando una respuesta de Laura por WhatsApp. Se anota en disco a proposito:
# si el servicio se reinicia mientras Laura piensa, el hilo que esperaba muere y la
# respuesta queda huerfana en el buzon. Paso el 2026-08-15 y Martin se quedo esperando
# sin saber que su respuesta existia. Con esto, al arrancar se rescata y se manda.
ESPERANDO = Path(__file__).resolve().parent.parent.parent / "wpp_esperando.json"

# El buzon de Laura tiene un solo casillero de pregunta/respuesta. Si llegan dos
# audios juntos, el segundo pisaria al primero antes de que voz.py lo levante.
# Los serializamos aca para que cada charla termine antes de entregar la siguiente.
_LAURA_WPP_LOCK = threading.Lock()

# El lock de Whisper evita que dos transcripciones usen la GPU a la vez, pero un
# Lock comun no promete respetar el orden de llegada. Estos turnos se reservan en
# el endpoint, antes de lanzar los hilos, y forman una fila FIFO para los audios
# que Martin le manda a Laura por WhatsApp.
_MEDIA_WPP_COND = threading.Condition()
_MEDIA_WPP_RESERVADOS = 0
_MEDIA_WPP_ACTUAL = 0


def _reservar_turno_media_wpp():
    global _MEDIA_WPP_RESERVADOS
    with _MEDIA_WPP_COND:
        turno = _MEDIA_WPP_RESERVADOS
        _MEDIA_WPP_RESERVADOS += 1
        return turno


def _procesar_en_turno_media_wpp(turno, trabajo):
    """Ejecuta una transcripcion cuando le toca y siempre libera al siguiente."""
    global _MEDIA_WPP_ACTUAL
    with _MEDIA_WPP_COND:
        while turno != _MEDIA_WPP_ACTUAL:
            _MEDIA_WPP_COND.wait()
    try:
        return trabajo()
    finally:
        with _MEDIA_WPP_COND:
            _MEDIA_WPP_ACTUAL += 1
            _MEDIA_WPP_COND.notify_all()


def _anotar_espera(pid, jid):
    try:
        ESPERANDO.write_text(json.dumps({"pid": pid, "jid": jid}), encoding="utf-8")
    except Exception:
        pass


def _olvidar_espera():
    try:
        ESPERANDO.unlink(missing_ok=True)
    except Exception:
        pass


@app.on_event("startup")
async def rescatar_respuesta_colgada():
    """Si un reinicio corto una charla a la mitad, mandar la respuesta que quedo."""
    try:
        if not ESPERANDO.exists():
            return
        pendiente = json.loads(ESPERANDO.read_text(encoding="utf-8"))
        r = buzon.sacar_respuesta(pendiente["pid"])
        if r:
            core.log("rescate: mandando por WhatsApp una respuesta que quedo colgada")
            evolution_enviar(pendiente["jid"], r)
        _olvidar_espera()
    except Exception as e:
        core.log(f"rescate: no pude ({e})")


def _charla_con_laura(jid: str, texto: str):
    """Pasa las charlas de WhatsApp a Laura de a una."""
    with _LAURA_WPP_LOCK:
        return _charla_con_laura_una(jid, texto)


def _charla_con_laura_una(jid: str, texto: str):
    """Le pregunta a Laura y manda la respuesta por WhatsApp cuando este lista.

    Corre en un hilo y contesta por su cuenta a proposito: si respondiera dentro del
    pedido HTTP, una respuesta larga de Laura chocaria con el timeout de n8n y se
    perderia. Asi n8n corta enseguida y la respuesta llega igual.
    """
    import time as _t
    pid = buzon.dejar_pregunta(texto, origen="whatsapp")
    _anotar_espera(pid, jid)          # por si el servicio se reinicia mientras Laura piensa
    inicio = _t.monotonic()

    # ¿hay alguien del otro lado? Si voz.py esta apagado, decirlo en vez de dejarlo esperando
    while not buzon.pregunta_tomada():
        if _t.monotonic() - inicio > buzon.SIN_VOZ_SEG:
            buzon.abandonar()
            evolution_enviar(jid, "Laura no esta despierta: el asistente de voz esta "
                                  "apagado en la compu. Prendelo desde el panel.")
            return
        _t.sleep(0.5)

    while True:
        r = buzon.sacar_respuesta(pid)
        if r is not None:
            evolution_enviar(jid, r)
            _olvidar_espera()
            return
        if _t.monotonic() - inicio > LAURA_ESPERA:
            evolution_enviar(jid, "Se me hizo muy largo y corte. Probá de nuevo.")
            return
        _t.sleep(0.5)


@app.post("/laura")
async def laura(request: Request, x_auth_token: str = Header(default="")):
    """Un texto de WhatsApp para Laura. Lo llama n8n; contesta por WhatsApp aparte."""
    if LAPTOP_SHARED_SECRET and x_auth_token != LAPTOP_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="token invalido")

    d = await request.json()
    texto = str(d.get("texto") or "").strip()
    jid = str(d.get("jid") or "").strip()
    quien = str(d.get("quien") or jid)

    if not texto or not jid:
        return {"ok": True, "skip": "sin texto o sin destino"}

    # ⭐⭐ NINGUN grupo le habla a Laura, ni siquiera el buzon "Audios" autorizado.
    # El agujero: `quien` lo arma n8n, y en un grupo puede venir el PARTICIPANTE — o sea
    # Martin hablando en cualquier grupo — con lo cual `_es_martin` daba True y Laura
    # habria empezado a contestar en todos los grupos donde el escribe. Hasta hoy no
    # pasaba solo porque Evolution ignoraba los grupos enteros; al abrirlos (2026-08-18,
    # para que ande el buzon de audios) esto pasa a ser la unica barrera.
    # Pedido textual de Martin: "no quiero que conteste mensajes randoms de otro grupo".
    # El buzon es para AUDIOS: los textos que caigan ahi tampoco se contestan.
    if jid.endswith("@g.us") or str(d.get("remoteJid") or "").endswith("@g.us"):
        core.log(f"/laura: ignoro texto del grupo {jid}")
        return {"ok": True, "skip": "los grupos no le hablan a Laura"}

    if not _es_martin(quien):
        core.log(f"/laura: ignoro texto de {quien} (no es Martin)")
        return {"ok": True, "skip": "no autorizado"}

    core.log(f"/laura: {texto[:60]}")
    asyncio.create_task(asyncio.to_thread(_charla_con_laura, jid, texto))
    return {"ok": True, "encolado": True}


@app.post("/procesar-media")
async def procesar_media(file: UploadFile = File(...), perfil: str = Form(default="generico"),
                          remote_jid: str = Form(default=""),
                          x_auth_token: str = Header(default="")):
    """Lo llama n8n con el media YA bajado de Evolution API (audio/video/imagen).
    Corre el sistema COMPLETO (transcripcion + analisis Gemini con perfil, o
    descripcion+OCR si es imagen).

    Con remote_jid: responde EN SEGUNDO PLANO por Evolution API directo desde
    la laptop (aviso "recibido" al toque + la transcripcion cuando termina) y
    devuelve al toque, SIN esperar a Whisper. Antes n8n se quedaba con la
    ejecucion abierta esperando la respuesta sincrona -- con audios largos o
    una tanda junta eso son minutos de un lugar de ejecucion ocupado en un n8n
    que puede estar compartido con otros flujos.

    Sin remote_jid: se comporta como antes (sincrono, devuelve el texto en la
    respuesta) -- por si algun otro caller lo necesita asi el dia de manana."""
    if LAPTOP_SHARED_SECRET and x_auth_token != LAPTOP_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="token invalido")

    # ⚠ Los GRUPOS se filtran ACA TAMBIEN, no solo en /transcribe. Este endpoint no lo
    # hacia —n8n le manda el media ya bajado— y con el guardado del Estudio puesto eso
    # dejo de ser inofensivo: la charla de un grupo de trabajo no solo se transcribia,
    # ahora ademas quedaria guardada en disco. Solo entra el grupo que Martin autorizo
    # a mano en WPP_GRUPOS_OK (hoy: su buzon "Audios").
    if remote_jid and str(remote_jid).endswith("@g.us") and str(remote_jid) not in GRUPOS_OK:
        core.log(f"/procesar-media: ignoro el grupo {remote_jid}")
        return {"ok": True, "skip": True, "motivo": "grupo no autorizado"}

    nombre = file.filename or "media.bin"
    ext = Path(nombre).suffix or ".bin"
    tmp = Path(tempfile.gettempdir()) / f"evo_{uuid.uuid4().hex}{ext}"
    tmp.write_bytes(await file.read())
    core.log(f"/procesar-media: {nombre} (perfil={perfil}, remote_jid={remote_jid or '(sincrono)'})")

    if not remote_jid:
        try:
            texto = await asyncio.to_thread(procesar.procesar_a_texto, tmp, perfil)
            return {"ok": True, "texto": texto}
        except Exception as e:
            core.log(f"  Error en /procesar-media: {e}")
            return {"ok": False, "texto": f"No se pudo procesar el archivo: {e}"}
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    # Si el que manda es Martin, esto NO es material para transcribir y archivar: le esta
    # hablando a Laura. Una foto suya va a parar al disco y ella la MIRA (una descripcion
    # de Gemini no reemplaza ver la captura), y un audio suyo es lo mismo que hablarle.
    # Pedido del 2026-08-15, despues de mandar una captura por WhatsApp y que se la comiera
    # el transcriptor sin que Laura se enterara.
    if _es_martin(remote_jid):
        es_imagen_laura = ext.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")
        cola = "" if es_imagen_laura else entrantes.cola_abrir(
            tmp, origen="whatsapp", de=remote_jid)
        turno_media = None if es_imagen_laura else _reservar_turno_media_wpp()

        def _para_laura():
            try:
                if es_imagen_laura:
                    WPP_FOTOS.mkdir(parents=True, exist_ok=True)
                    destino = WPP_FOTOS / f"wpp_{uuid.uuid4().hex[:10]}{ext}"
                    shutil.copy(tmp, destino)
                    _charla_con_laura(remote_jid,
                        f"[Te mande una foto por WhatsApp; esta guardada en {destino} — "
                        f"abrila con la herramienta Read antes de contestar.]")
                else:
                    # También lo mostramos mientras se prepara, pero no se copia a la
                    # bandeja hasta que Gemini terminó. Hablarle a Laura no espera ese
                    # último paso: recibe su transcripción apenas Whisper termina.
                    def avanzar(pct, paso):
                        if cola:
                            entrantes.cola_actualizar(cola, pct=round(float(pct) * .76), paso=paso)

                    datos, _ = _procesar_en_turno_media_wpp(
                        turno_media, lambda: core.procesar_archivo(tmp, progreso=avanzar))
                    dicho = (datos.get("transcripcion") or "").strip()
                    if not dicho:
                        if cola:
                            entrantes.cola_fallar(cola, "no se detectó voz")
                        evolution_enviar(remote_jid, "No te escuche nada en ese audio.")
                        return
                    _charla_con_laura(remote_jid, dicho)
                    try:
                        if cola:
                            entrantes.cola_actualizar(cola, pct=84,
                                                      paso="Haciendo el análisis inteligente…")
                        analisis = analizar_gemini.analizar(datos)
                        if not isinstance(analisis, dict) or analisis.get("error"):
                            detalle = analisis.get("error") if isinstance(analisis, dict) else ""
                            raise RuntimeError(detalle or "Gemini no devolvió un análisis válido")
                        if cola:
                            entrantes.cola_actualizar(cola, pct=96,
                                                      paso="Guardando texto y análisis…")
                        guardado = entrantes.guardar(
                            tmp, origen="whatsapp", de=remote_jid, texto=dicho,
                            segmentos=datos.get("segmentos"), analisis=analisis)
                        if not guardado:
                            raise RuntimeError("no se pudo guardar el audio para el Estudio")
                        if cola:
                            entrantes.cola_terminar(cola, archivo=guardado,
                                                    paso="Texto y análisis listos para editar")
                    except Exception as e:
                        # La conversación con Laura ya siguió; este fallo sólo afecta la
                        # copia del Estudio y queda claro en la cola, sin mandarle un
                        # segundo mensaje confuso por WhatsApp.
                        core.log(f"  (no se pudo dejar el audio listo en el estudio: {e})")
                        if cola:
                            entrantes.cola_fallar(cola, e)
            except Exception as e:
                core.log(f"  Error mandandole el media a Laura: {e}")
                if cola:
                    entrantes.cola_fallar(cola, e)
                evolution_enviar(remote_jid, f"No pude con ese archivo: {e}")
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass

        asyncio.create_task(asyncio.to_thread(_para_laura))
        return {"ok": True, "aviso": "va a Laura"}

    # ⭐ Un GRUPO autorizado (hoy: "Audios") es un buzon para el Estudio, no una consulta.
    # Ahi no vuelve el analisis entero: mandar cinco audios y recibir cinco pantallas de
    # texto es justo el desorden que Martin quiso evitar creando el grupo (2026-08-17).
    es_buzon = str(remote_jid).endswith("@g.us")
    evolution_enviar(remote_jid, "📥 Recibido, transcribiendo..." if es_buzon else
        "Recibido, procesando... Si hay varios audios juntos o es uno largo, puede tardar unos minutos.")

    def _trabajo():
        try:
            quien = nombre_grupo(remote_jid) if es_buzon else remote_jid
            texto = procesar.procesar_a_texto(tmp, perfil,
                                              origen="whatsapp", de=quien)
            if es_buzon:
                dur = entrantes.duracion(tmp)
                evolution_enviar(remote_jid, "✅ Guardado en el Estudio (%d:%02d)." %
                                 (dur // 60, dur % 60))
            else:
                evolution_enviar(remote_jid, texto)
        except Exception as e:
            core.log(f"  Error en /procesar-media: {e}")
            evolution_enviar(remote_jid, f"No se pudo procesar el archivo: {e}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    asyncio.create_task(asyncio.to_thread(_trabajo))
    return {"ok": True, "aviso": "procesando en segundo plano"}


# ---------------------- Subida directa de audios LARGOS --------------------
# Para audios de 1h+ que no entran por Telegram (20MB) ni WhatsApp (~16MB).
# GET /subir = pagina simple (celular o PC). POST /subir-audio = recibe el archivo,
# responde al toque y transcribe en segundo plano; el resultado llega por Telegram.
# OJO: por el tunel de Cloudflare el tope es ~100MB por subida (~2h de mp3).
# Para mas, usar la direccion local (http://IP-de-la-laptop:8080/subir) sin tope.

def _pagina_subir():
    """Arma la pagina con las <option> de perfil vigentes (se lee la carpeta
    perfiles/ en cada pedido, asi un perfil nuevo aparece sin reiniciar)."""
    from app.nucleo import analizar_gemini
    opciones = "".join(
        f'<option value="{p}"{" selected" if p == analizar_gemini.PERFIL_DEFECTO else ""}>{p}</option>'
        for p in analizar_gemini.perfiles_disponibles())
    return f"""<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Subir audio largo</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:480px;margin:40px auto;padding:0 16px;background:#111;color:#eee}}
 h1{{font-size:1.3em}} input,button,select{{width:100%;padding:12px;margin:8px 0;border-radius:8px;border:1px solid #444;
 background:#1c1c1c;color:#eee;font-size:1em;box-sizing:border-box}}
 button{{background:#2563eb;border:0;font-weight:600;cursor:pointer}} button:disabled{{opacity:.5}}
 #msg{{margin-top:14px;padding:12px;border-radius:8px;display:none}}
 .ok{{background:#14532d}} .err{{background:#7f1d1d}} small{{color:#888}}
</style></head><body>
<h1>🎙 Subir audio largo</h1>
<p>Se transcribe en la compu y el resultado te llega por <b>Telegram</b>.</p>
<input type=password id=clave placeholder="Clave">
<input type=file id=archivo accept="audio/*,video/*">
<select id=perfil title="Que tipo de analisis hacerle">{opciones}</select>
<button id=btn onclick=subir()>Subir y transcribir</button>
<div id=msg></div>
<small>Audios de horas: ok. Por internet el tope es ~100MB; en casa usa la direccion local.</small>
<script>
const $=id=>document.getElementById(id);
$('clave').value=localStorage.getItem('clave')||'';
async function subir(){{
  const f=$('archivo').files[0], m=$('msg');
  if(!f){{alert('Elegi un archivo');return}}
  localStorage.setItem('clave',$('clave').value);
  $('btn').disabled=true;$('btn').textContent='Subiendo... (no cierres la pagina)';
  const fd=new FormData();fd.append('clave',$('clave').value);fd.append('file',f);fd.append('perfil',$('perfil').value);
  try{{
    const r=await fetch('/subir-audio',{{method:'POST',body:fd}});
    const j=await r.json();
    m.style.display='block';
    if(r.ok){{m.className='ok';m.textContent='Recibido ('+(f.size/1048576).toFixed(0)+' MB). Transcribiendo... el resultado llega por Telegram en unos minutos.'}}
    else{{m.className='err';m.textContent='Error: '+(j.detail||r.status)}}
  }}catch(e){{m.style.display='block';m.className='err';m.textContent='Error de red: '+e}}
  $('btn').disabled=false;$('btn').textContent='Subir y transcribir';
}}
</script></body></html>"""


@app.get("/subir")
async def pagina_subir():
    return HTMLResponse(_pagina_subir())


@app.post("/subir-audio")
async def subir_audio(file: UploadFile = File(...), clave: str = Form(default=""),
                       perfil: str = Form(default="generico")):
    if LAPTOP_SHARED_SECRET and clave != LAPTOP_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="clave incorrecta")

    nombre = file.filename or "audio.bin"
    ext = Path(nombre).suffix or ".bin"
    tmp = Path(tempfile.gettempdir()) / f"subida_{uuid.uuid4().hex}{ext}"
    with open(tmp, "wb") as f:                    # a disco en streaming: no carga 100MB en RAM
        shutil.copyfileobj(file.file, f)
    mb = tmp.stat().st_size / 1048576
    core.log(f"/subir-audio: {nombre} ({mb:.0f} MB, perfil={perfil})")

    def _trabajo():
        try:
            texto = procesar.procesar_a_texto(tmp, perfil=perfil)
            tg_enviar(f"🎙 Audio subido ({nombre}, {mb:.0f} MB):\n\n{texto}")
        except Exception as e:
            tg_enviar(f"⚠️ Error transcribiendo el audio subido ({nombre}): {e}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    asyncio.create_task(asyncio.to_thread(_trabajo))
    return {"ok": True, "mb": round(mb), "aviso": "procesando: el resultado llega por Telegram"}


@app.post("/webhook")
async def webhook(request: Request, x_webhook_signature: str = Header(default="")):
    """Modo directo (alternativa): WaSenderAPI -> laptop -> Telegram."""
    if WEBHOOK_SECRET and x_webhook_signature != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="firma invalida")

    payload = await request.json()
    msg = _msg_obj(payload)
    if not msg or (msg.get("key") or {}).get("fromMe"):
        return {"ok": True, "ignorado": True}
    grupo = _grupo_prohibido(msg)
    if grupo:
        core.log(f"/webhook: ignoro el grupo {grupo}")
        return {"ok": True, "ignorado": "grupo no autorizado"}
    tipo, _ = _media_del_mensaje(msg)
    if not tipo:
        return {"ok": True, "ignorado": "no es audio/video"}

    remitente = _remitente(msg)
    perfil = payload.get("perfil") or PERFIL_DEFECTO_WHATSAPP

    def _trabajo():
        try:
            res = procesar_mensaje(msg, remitente, perfil)
            tg_enviar(res["texto_telegram"])
        except Exception as e:
            tg_enviar(f"⚠️ WhatsApp de {remitente}: error ({e})")

    asyncio.create_task(asyncio.to_thread(_trabajo))
    return {"ok": True}
