"""
Bot de Telegram para el equipo de devs.
Manda un audio, video o imagen y devuelve la transcripcion / analisis (imagenes: descripcion + OCR).

Ademas (2026-08-11): los mensajes de TEXTO van a Laura, el Claude Code del asistente
de voz — la MISMA sesion y memoria que por microfono. El bot no habla con el CLI: le
deja la pregunta a voz.py por un buzon de archivos (app/voz/buzon.py) porque el
proceso `claude` persistente vive alla, y dos procesos sobre la misma sesion la
bifurcarian. Si voz.py esta apagado, el bot lo dice en vez de colgarse.

DOS CANDADOS, a proposito separados (2026-08-11): compartir este bot con el equipo
de devs para que prueben la transcripcion NO tiene que abrirles la puerta de Laura,
que ejecuta comandos en la PC de Martin. Por eso son dos listas independientes:
transcribir (EQUIPO_IDS) puede quedar abierta al equipo; Laura (LAURA_IDS) es
SIEMPRE, nada mas, el user id de Martin.

Laura solo en chat PRIVADO (2026-08-11): en el grupo compartido con el equipo,
cualquier texto suelto de un companero disparaba el rechazo de Laura EN PUBLICO
("Laura solo le contesta a Martin"). El texto ahora se ignora en silencio fuera
de un chat privado -- media (audio/video/foto) sigue andando igual en grupos,
que es el uso que se busca al compartir el bot.

.env:
    TELEGRAM_TOKEN=...
    GEMINI_API_KEY=...
    TELEGRAM_EQUIPO_IDS=...    (quien puede TRANSCRIBIR; vacio = abierto al equipo)
    TELEGRAM_ALLOWED_IDS=...   (quien puede hablarle a LAURA; OBLIGATORIO, es Martin
                                solo — ella ejecuta comandos en la maquina, y un bot
                                abierto seria darle la compu a quien encuentre el token)

Correr:  python -m app.ingesta.bot_telegram
"""

import os
import time
import asyncio
import tempfile
from pathlib import Path

os.environ.pop("SSLKEYLOGFILE", None)  # Avast rompe el SSL de Python

import truststore
truststore.inject_into_ssl()

from dotenv import load_dotenv

from app.rutas import ENV
load_dotenv(ENV)

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

from app.nucleo import core
from app.nucleo import procesar
from app.voz import buzon

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Quien puede TRANSCRIBIR (audios/videos/fotos): el equipo de devs. Vacio = abierto
# a cualquiera que tenga el numero — es el uso original del bot, pensado para
# compartirlo sin pedirle antes el user id a cada uno.
EQUIPO_IDS = {int(x) for x in os.environ.get("TELEGRAM_EQUIPO_IDS", "").replace(" ", "").split(",") if x}

# Quien puede hablarle a LAURA. Lista APARTE de EQUIPO_IDS a proposito: Laura
# ejecuta comandos en la PC de Martin, y sumar gente a EQUIPO_IDS para que prueben
# la transcripcion no tiene que darle a nadie mas esa puerta. Vacio = nadie (no
# "abierto" como EQUIPO_IDS): sin lista, Laura queda muda por este canal.
LAURA_IDS = {int(x) for x in os.environ.get("TELEGRAM_ALLOWED_IDS", "").replace(" ", "").split(",") if x}


# Grupos que ya anotamos en el log: el id se imprime una sola vez por grupo.
_GRUPOS_VISTOS = set()


def _autorizado_equipo(update: Update) -> bool:
    if not EQUIPO_IDS:
        return True
    return bool(update.effective_user) and update.effective_user.id in EQUIPO_IDS


def _autorizado_laura(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id in LAURA_IDS


async def responder(msg, texto: str):
    """Responde partiendo el texto si supera el limite de Telegram (4096)."""
    for i in range(0, len(texto), 3900):
        await msg.reply_text(texto[i:i + 3900])


def _anotar_visita(update: Update, donde: str):
    """Deja en el log quien toco la puerta (para sumarlo a una lista sin pedirle
    el id por otro canal: se lee de logs/telegram.log, prefijo visita-captura)."""
    u = update.effective_user
    if u is None:
        return
    print(f"visita-captura: {donde} | id={u.id} | nombre={u.full_name} | "
          f"username=@{u.username or '-'}", flush=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.nucleo import analizar_gemini
    uid = update.effective_user.id if update.effective_user else "?"
    _anotar_visita(update, "start")
    perfiles = ", ".join(analizar_gemini.perfiles_disponibles())
    await update.message.reply_text(
        "Hola. Mandame un audio, video o imagen y te devuelvo la transcripcion / analisis.\n\n"
        f"Para elegir el perfil de analisis, poné el nombre como descripcion del archivo "
        f"(ej: \"{analizar_gemini.PERFIL_DEFECTO}\"). Perfiles: {perfiles}. "
        f"Sin descripcion se usa \"{analizar_gemini.PERFIL_DEFECTO}\".\n\n"
        "Y si me escribis TEXTO, le llega a Laura (el Claude Code de la compu) y te "
        "contesta por aca: misma charla y misma memoria que por voz.\n\n"
        f"Tu user id de Telegram es: {uid}")


# --- Laura por texto ----------------------------------------------------------------
LAURA_TIMEOUT = 620           # apenas mas que el TIMEOUT de claude_voz: tareas largas
_laura_lock = asyncio.Lock()  # una pregunta por vez: el buzon tiene UN solo casillero


async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cualquier texto (no comando) va a Laura y la respuesta vuelve al chat."""
    msg = update.message
    if msg is None:                        # mensajes editados y otros bichos raros
        return
    # Laura es de a uno con Martin: en un grupo (compartido con el equipo para
    # probar la transcripcion) el texto se ignora en silencio, ni "no autorizado"
    # se dice -- eso quedaria peor, contestandole a un companero delante de todos
    # que "esto es solo para Martin". Media (audio/video/foto) SI sigue andando
    # en grupos: ese es justo el uso que se busca compartiendo el bot.
    chat = update.effective_chat
    if chat is not None and chat.type != "private":
        # Se ignora igual que siempre, pero se anota el id UNA vez por grupo. Sin esto,
        # meter al bot en un grupo nuevo y querer mandarle avisos ahi era un callejon:
        # el id de un grupo se saca con getUpdates, y eso esta prohibido en este proyecto
        # (le robaria los mensajes al polling de este mismo bot y lo dejaria sordo).
        if chat.id not in _GRUPOS_VISTOS:
            _GRUPOS_VISTOS.add(chat.id)
            print(f"telegram grupo: id={chat.id} titulo={chat.title!r}", flush=True)
        return
    if not _autorizado_laura(update):
        # A proposito NO dice "no estas autorizado": si es alguien del equipo con
        # acceso a transcribir, que quede claro que ESTE camino es otro, no un
        # permiso que le falta pedir. _autorizado_laura ya devuelve False si
        # LAURA_IDS esta vacio (nadie configurado) o si el id no esta en la lista:
        # nunca se abre "por defecto" como si pasa con la transcripcion.
        _anotar_visita(update, "texto privado sin lista")
        await msg.reply_text(
            "Laura solo le contesta a su dueño por este chat. Si necesitas algo, "
            "mandale un audio, video o foto para transcribir/analizar.")
        return
    texto = (msg.text or "").strip()
    if not texto:
        return
    await _laura_buzon(msg, context, texto)


async def _laura_buzon(msg, context, texto: str):
    """Le deja una pregunta a Laura (voz.py) por el buzon y espera la respuesta.

    Lo usan el texto de Martin y tambien sus fotos con "laura" en la descripcion
    (ahi `texto` lleva la ruta del archivo para que Laura la mire con Read).
    """
    async with _laura_lock:
        pid = buzon.dejar_pregunta(texto)
        inicio = time.monotonic()

        # Primero: ¿alguien atiende? Si voz.py no levanta la pregunta enseguida,
        # no esta corriendo, y eso hay que DECIRLO (no dejarte hablando solo).
        while not buzon.pregunta_tomada():
            if time.monotonic() - inicio > buzon.SIN_VOZ_SEG:
                buzon.abandonar()
                await msg.reply_text(
                    "Laura no esta despierta: el asistente de voz esta apagado en la "
                    "compu. Prendelo desde el panel y volveme a escribir.")
                return
            await asyncio.sleep(0.5)

        # Y ahora la respuesta, mostrando "escribiendo..." mientras Laura piensa.
        aviso_largo = False
        ultimo_typing = 0.0
        while True:
            r = buzon.sacar_respuesta(pid)
            if r is not None:
                await responder(msg, r)
                return
            pasado = time.monotonic() - inicio
            if pasado > LAURA_TIMEOUT:
                await msg.reply_text("Laura no me contesto a tiempo. Proba de nuevo.")
                return
            if not aviso_largo and pasado > 45:
                aviso_largo = True
                await msg.reply_text("Sigo en eso, es una tarea larga. Aguantame...")
            if time.monotonic() - ultimo_typing > 4.0:   # el cartelito dura ~5 s
                ultimo_typing = time.monotonic()
                try:
                    await context.bot.send_chat_action(chat_id=msg.chat_id,
                                                       action=ChatAction.TYPING)
                except Exception:
                    pass
            await asyncio.sleep(1.0)


async def manejar_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    privado = chat is not None and chat.type == "private"

    # FOTOS a Laura (solo en privado): el dueño con "laura" al principio de la
    # descripcion manda la foto a SU Laura por el buzon. Sin esa palabra sigue
    # yendo al analizador de siempre.
    if privado and msg.photo and _autorizado_laura(update):
        caption = (msg.caption or "").strip()
        if caption.lower().startswith("laura"):
            media = msg.photo[-1]
            tmp = Path(tempfile.gettempdir()) / f"tg_{media.file_unique_id}.jpg"
            tg_file = await context.bot.get_file(media.file_id)
            await tg_file.download_to_drive(str(tmp))
            resto = caption[len("laura"):].lstrip(" ,.:;-")
            await _laura_buzon(msg, context,
                               (f"[Te mande una foto por Telegram; esta guardada en {tmp} — "
                                f"mirala con la herramienta Read antes de contestar.] "
                                f"{resto}").rstrip())
            return

    if not _autorizado_equipo(update):
        # En un grupo, el "no estas autorizado" en publico queda peor que el
        # silencio (misma leccion que con el texto de Laura). En privado si se dice.
        if privado:
            await msg.reply_text("No estas autorizado a usar este bot.")
        return

    ext = None
    if msg.photo:
        media = msg.photo[-1]          # la resolucion mas grande
        ext = ".jpg"
    else:
        media = msg.voice or msg.audio or msg.video or msg.video_note or msg.document

    if media is None:
        await msg.reply_text("Mandame un audio, video o imagen.")
        return

    # La API de bots de Telegram NO permite descargar archivos de mas de 20 MB.
    # Sin este aviso, get_file() falla con un error criptico ("File is too big").
    MAX_TELEGRAM = 20 * 1024 * 1024
    tam = getattr(media, "file_size", None)
    if tam and tam > MAX_TELEGRAM:
        await msg.reply_text(
            f"El archivo pesa {tam / 1024 / 1024:.0f} MB y Telegram no deja a los bots "
            "descargar mas de 20 MB.\n\n"
            "Opciones: mandalo como nota de voz (pesa mucho menos), partilo en pedazos, "
            "o mandalo por WhatsApp (aguanta hasta ~16 MB de media, o notas de voz largas).")
        return

    # El caption del mensaje elige el perfil de analisis (ej: mandar el audio
    # con la descripcion "ventas"). Sin caption o con uno que no matchea
    # ningun perfil, procesar_a_texto cae en el generico solo.
    perfil = (msg.caption or "").strip().lower() or None

    await msg.reply_text("Recibido, procesando...")

    tg_file = await context.bot.get_file(media.file_id)
    if ext is None:
        nombre = getattr(media, "file_name", None) or ""
        ext = Path(nombre).suffix or (".oga" if msg.voice else
              (".mp4" if (msg.video or msg.video_note) else ".bin"))
    tmp = Path(tempfile.gettempdir()) / f"tg_{media.file_unique_id}{ext}"
    await tg_file.download_to_drive(str(tmp))

    try:
        kwargs = {"perfil": perfil} if perfil else {}
        # Quien lo mando queda en la ficha del audio guardado, para reconocerlo
        # despues en el Estudio (la pantalla que pega varios audios en uno).
        quien = (msg.from_user.full_name if msg.from_user else "") or "Telegram"
        texto = await asyncio.to_thread(procesar.procesar_a_texto, tmp,
                                        origen="telegram", de=quien, **kwargs)
        await responder(msg, texto)
    except Exception as e:
        await msg.reply_text(f"Error procesando el archivo: {e}")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_TOKEN en el archivo .env")
    core.cargar_modelo()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE |
        filters.PHOTO | filters.Document.ALL,
        manejar_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    print("Bot de Telegram corriendo. Ctrl+C para cortar.", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
