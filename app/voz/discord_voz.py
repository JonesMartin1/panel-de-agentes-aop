"""Laura por Discord: hablarle desde el celular como si fuera una llamada.

Pedido del 2026-08-16, y nace de dos paredes de Safari en el iPhone que NO tienen
arreglo desde la web:
  - con la pantalla bloqueada o la app en segundo plano, iOS suspende el microfono
    y el audio: la charla se corta sola;
  - con el microfono abierto, iOS manda la salida al parlante y no hay forma de
    elegir los auriculares Bluetooth (bug viejo de WebKit).
Discord no tiene ninguno de los dos problemas: es una llamada de verdad, sigue en
segundo plano, con la pantalla apagada y con los auriculares puestos. Y Martin ya
lo usa todos los dias.

COMO FUNCIONA: el bot se mete SOLO al canal de voz apenas entras vos. Escuchas y
hablas como con cualquier persona; no hay que apretar nada ni escribir comandos.
Cuando te callas un segundo, se cierra la frase, la transcribe el mismo Whisper
del microfono, se la pregunta a la MISMA Laura (misma sesion, misma memoria) y te
contesta hablando en el canal, con la misma voz Piper.

ARQUITECTURA: igual que app/voz/llamada.py — corre en un hilo DENTRO de voz.py y
recibe el modelo Whisper y la voz Piper YA cargados. Cargarlos de nuevo duplicaria
VRAM y competiria por ella. Sin DISCORD_BOT_TOKEN en el .env queda apagado, no a
medias.

SEGURIDAD: solo le contesta a DISCORD_USUARIO_ID (el id de Martin). Cualquier otro
que hable en el canal se ignora en silencio — Laura ejecuta comandos en esta PC,
asi que esto no es un juguete de servidor.
"""

import io
import time
import wave
import asyncio
import tempfile
import threading
from pathlib import Path

import discord
from discord.sinks import WaveSink

SILENCIO_CORTE = 1.0      # segundos sin que llegue voz para dar la frase por cerrada
MIN_AUDIO = 24000         # bytes de PCM: menos que esto es un ruidito, no una frase

# Lo que inyecta voz.py al arrancar (nada se importa de alla: importarlo abre el
# microfono y carga modelos de nuevo).
_modelo = None
_lock = None
_piper = None
_preguntar = None
_usuario_ok = 0
_vocab = None

_bot = None
_hablando = False


def _transcribir(ruta):
    with _lock:
        segmentos, _ = _modelo.transcribe(ruta, language="es", beam_size=1,
                                          vad_filter=True, initial_prompt=_vocab)
        return " ".join(s.text.strip() for s in segmentos).strip()


def _sintetizar(texto):
    """La voz de siempre, a un wav temporal que ffmpeg le pasa a Discord."""
    tmp = Path(tempfile.gettempdir()) / f"laura_discord_{int(time.time()*1000)}.wav"
    with wave.open(str(tmp), "wb") as w:
        _piper.synthesize_wav(texto, w)
    return tmp


class Escucha(WaveSink):
    """Igual que el sink de siempre, pero anotando CUANDO hablo cada uno.

    Discord solo manda paquetes mientras alguien habla, asi que 'hace un segundo
    que no llega nada' es exactamente 'se callo'. Sale gratis: no hay que medir
    volumenes como en el navegador.

    ⚠ py-cord 2.8.1 viene inconsistente: el router de recepcion NUEVO le pide al
    sink `__sink_listeners__` y `walk_children()`, pero los sinks que la propia
    libreria exporta (discord.sinks) son los VIEJOS y no los tienen — grabar
    reventaba con AttributeError. Se los ponemos nosotros, vacios: el audio igual
    llega por `write()`, que es el otro camino del router (2026-08-16).
    """

    __sink_listeners__ = []

    def walk_children(self):
        return []

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ultimo = 0.0
        self.hablo = False

    def write(self, data, user):
        if user == _usuario_ok and not _hablando:
            self.ultimo = time.time()
            self.hablo = True
        super().write(data, user)


async def _ciclo(vc):
    """Escuchar, contestar, volver a escuchar. Hasta que te vas del canal."""
    global _hablando
    while vc.is_connected():
        sink = Escucha()
        listo = asyncio.Event()

        async def cerrar(sink_final, *a):
            listo.set()

        vc.start_recording(sink, cerrar)
        # Esperar a que hables y despues a que te calles.
        while vc.is_connected():
            await asyncio.sleep(0.2)
            if sink.hablo and time.time() - sink.ultimo > SILENCIO_CORTE:
                break
        if not vc.is_connected():
            break
        try:
            vc.stop_recording()
        except Exception:
            pass
        await listo.wait()

        datos = sink.audio_data.get(_usuario_ok)
        if not datos:
            continue
        crudo = datos.file.getvalue()
        if len(crudo) < MIN_AUDIO:
            continue                      # tosiste, o se colo un ruido
        ruta = Path(tempfile.gettempdir()) / f"laura_discord_in_{int(time.time()*1000)}.wav"
        ruta.write_bytes(crudo)
        try:
            dicho = await asyncio.to_thread(_transcribir, str(ruta))
        finally:
            ruta.unlink(missing_ok=True)
        if not dicho:
            continue
        print("discord dicho:", dicho, flush=True)

        respuesta = await asyncio.to_thread(_preguntar, dicho) or "No tengo respuesta para eso."
        print("discord respuesta:", respuesta, flush=True)

        wav = await asyncio.to_thread(_sintetizar, respuesta)
        _hablando = True                  # mientras habla no se escucha a si misma
        fin = asyncio.Event()
        vc.play(discord.FFmpegPCMAudio(str(wav)),
                after=lambda e: vc.loop.call_soon_threadsafe(fin.set))
        await fin.wait()
        _hablando = False
        wav.unlink(missing_ok=True)


_en_canal = False


async def _entrar(canal):
    """Meterse al canal y quedarse escuchando hasta que te vayas."""
    global _en_canal
    if _en_canal:
        return                            # ya hay un ciclo corriendo: no duplicar
    _en_canal = True
    try:
        vc = canal.guild.voice_client
        if vc:
            await vc.move_to(canal)
        else:
            # ⭐ Limpiar el estado de voz ANTES de conectar. Discord se acuerda de
            # que este bot "estaba" en un canal aunque el proceso se haya muerto, y
            # al volver con una sesion nueva cierra el websocket de voz con 4006
            # ("Session is no longer valid"). Mandar channel=None lo borra; sin
            # esto, la voz reiniciada nunca vuelve a entrar (2026-08-16).
            await canal.guild.change_voice_state(channel=None)
            await asyncio.sleep(1.0)
            # timeout corto: si el handshake de voz no cierra, mejor enterarse en
            # 20 s que esperar el minuto entero de la libreria
            vc = await canal.connect(timeout=20.0, reconnect=False)
        print(f"discord: te sigo al canal {canal.name}", flush=True)
        await _ciclo(vc)
    except Exception as e:
        # ⚠ str(e) viene VACIO en los errores tipicos de voz (un timeout de asyncio
        # no trae texto): sin el tipo y el traceback no se diagnostica nada.
        import traceback
        print(f"discord: no pude entrar al canal: {type(e).__name__}: {e!r}", flush=True)
        traceback.print_exc()
    finally:
        _en_canal = False


def _armar_bot():
    intents = discord.Intents.default()
    intents.voice_states = True           # unico que hace falta: saber cuando entras
    bot = discord.Bot(intents=intents)

    @bot.event
    async def on_ready():
        print(f"discord: conectado como {bot.user}", flush=True)
        # ⭐ Si YA estabas en un canal antes de que el bot arrancara, no hay ningun
        # evento que lo avise: los eventos son cambios de estado, y no cambio nada.
        # Asi que al conectarse va a buscarte. Sin esto, el bot se quedaba prendido
        # sin hacer nada y parecia roto (2026-08-16).
        for guild in bot.guilds:
            for canal in guild.voice_channels:
                # voice_states y no members: members necesita el intent privilegiado
                # de miembros, y este bot no lo tiene ni lo necesita.
                if _usuario_ok in canal.voice_states:
                    print(f"discord: ya estabas en {canal.name}, voy para alla", flush=True)
                    await _entrar(canal)
                    return

    @bot.event
    async def on_voice_state_update(miembro, antes, ahora):
        if miembro.id != _usuario_ok:
            return
        # Entraste a un canal: el bot te sigue. Te fuiste: se va.
        if ahora.channel and (not antes.channel or antes.channel != ahora.channel):
            await _entrar(ahora.channel)
        elif antes.channel and not ahora.channel:
            vc = antes.channel.guild.voice_client
            if vc:
                await vc.disconnect(force=True)
                print("discord: te fuiste, me voy", flush=True)

    return bot


def arrancar(modelo, model_lock, piper_voz, preguntar_fn, token=None,
             usuario_id=0, vocab=None):
    """Levanta el bot en un hilo aparte. Sin token o sin id, no arranca."""
    global _modelo, _lock, _piper, _preguntar, _usuario_ok, _vocab, _bot
    if not token or not usuario_id:
        print("discord: falta DISCORD_BOT_TOKEN o DISCORD_USUARIO_ID en el .env "
              "(queda apagado)", flush=True)
        return None
    _modelo, _lock, _piper, _preguntar = modelo, model_lock, piper_voz, preguntar_fn
    _usuario_ok, _vocab = int(usuario_id), vocab

    def correr():
        global _bot
        # El detalle del handshake de voz (incluido el codigo con el que Discord
        # cierra el websocket) NO sale por el log normal: sin esto, un fallo de
        # conexion se ve solo como un TimeoutError pelado.
        import logging
        from app.rutas import LOGS
        arch = logging.FileHandler(LOGS / "discord.log", encoding="utf-8")
        arch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        for nombre in ("discord", "discord.voice", "discord.gateway"):
            lg = logging.getLogger(nombre)
            lg.setLevel(logging.DEBUG)
            lg.addHandler(arch)
        asyncio.set_event_loop(asyncio.new_event_loop())
        _bot = _armar_bot()
        try:
            _bot.run(token)
        except Exception as e:
            print("discord: se cayo el bot:", e, flush=True)

    hilo = threading.Thread(target=correr, daemon=True, name="discord")
    hilo.start()
    print("discord: bot de voz arrancando…", flush=True)
    return hilo
