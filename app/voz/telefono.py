"""Laura por telefono: una llamada de verdad, con la pantalla del celular apagada.

Pedido del 2026-08-16, despues de chocar contra dos paredes:
  - en el navegador del iPhone, iOS suspende el microfono apenas bloqueas la
    pantalla o salis de la app, y con el microfono abierto manda la salida al
    parlante en vez de a los auriculares Bluetooth;
  - por Discord, la RECEPCION de audio esta rota desde que Discord impuso el
    cifrado punta a punta (DAVE): el bot entra al canal y habla, pero no oye.
Una llamada telefonica no tiene ninguno de esos problemas: el celular la maneja
como lo que es, sigue con la pantalla apagada, suena en los auriculares y no
depende de ninguna app.

COMO FUNCIONA: Twilio te llama al celular; cuando atendes, abre una conexion
permanente (websocket) contra esta maquina y le manda el audio de la llamada en
vivo, en trozos de 20 ms. Aca se juntan esos trozos, se detecta cuando dejaste de
hablar, lo transcribe el MISMO Whisper del microfono, se lo pregunta a la MISMA
Laura (misma sesion y misma memoria) y la respuesta vuelve por el mismo camino
con la voz Piper de siempre.

ARQUITECTURA: igual que app/voz/llamada.py y app/voz/discord_voz.py — corre en un
hilo DENTRO de voz.py y recibe el modelo y la voz YA cargados. Sin las claves de
Twilio en el .env queda apagado, no a medias.

SEGURIDAD: Twilio solo puede llamar a TU numero (TELEFONO_DESTINO), y en la cuenta
de prueba encima tiene que estar verificado. El websocket no acepta nada que no
traiga un streamSid de una llamada que arrancamos nosotros.
"""

import io
import json
import time
import wave
import base64
import audioop
import asyncio
import tempfile
import threading
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response

PUERTO = 8761
TASA_TEL = 8000           # Twilio manda y espera 8 kHz mulaw, siempre
TASA_WHISPER = 16000
TROZO_MS = 20             # 160 bytes de mulaw = 20 ms
SILENCIO_CORTE = 1.1      # segundos callado que cierran la frase
UMBRAL_VOZ = 700          # energia RMS del PCM 16 bit; el ruido de linea queda abajo
MIN_HABLADO = 0.4         # segundos de voz para que cuente como algo dicho

app = FastAPI()

_modelo = None
_lock = None
_piper = None
_preguntar = None
_vocab = None
_cfg = {}                 # sid, token, numero_twilio, destino, url_publica
_llamada_activa = False


# --- Audio: el telefono habla en mulaw 8k, Whisper y Piper en PCM ---------------
def _mulaw_a_wav(mulaw: bytes) -> Path:
    """Lo que dijiste, listo para Whisper: PCM 16 bit a 16 kHz."""
    pcm = audioop.ulaw2lin(mulaw, 2)
    pcm, _ = audioop.ratecv(pcm, 2, 1, TASA_TEL, TASA_WHISPER, None)
    ruta = Path(tempfile.gettempdir()) / f"laura_tel_{int(time.time()*1000)}.wav"
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TASA_WHISPER)
        w.writeframes(pcm)
    return ruta


def _voz_a_mulaw(texto: str) -> bytes:
    """La respuesta, en el formato que entiende la linea telefonica."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        _piper.synthesize_wav(texto, w)
    buf.seek(0)
    with wave.open(buf, "rb") as r:
        pcm = r.readframes(r.getnframes())
        tasa, canales, ancho = r.getframerate(), r.getnchannels(), r.getsampwidth()
    if canales == 2:
        pcm = audioop.tomono(pcm, ancho, 0.5, 0.5)
    if ancho != 2:
        pcm = audioop.lin2lin(pcm, ancho, 2)
    pcm, _ = audioop.ratecv(pcm, 2, 1, tasa, TASA_TEL, None)
    return audioop.lin2ulaw(pcm, 2)


def _transcribir(ruta: str) -> str:
    with _lock:
        segmentos, _ = _modelo.transcribe(ruta, language="es", beam_size=1,
                                          vad_filter=True, initial_prompt=_vocab)
        return " ".join(s.text.strip() for s in segmentos).strip()


# --- La llamada -----------------------------------------------------------------
@app.post("/telefono/twiml")
async def twiml(request: Request):
    """Lo que Twilio pide apenas atendes: 'conectame el audio a esta direccion'."""
    ws = _cfg["url_publica"].replace("https://", "wss://").replace("http://", "ws://")
    return Response(content=(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Connect>'
        f'<Stream url="{ws}/telefono/stream" />'
        '</Connect></Response>'), media_type="application/xml")


@app.websocket("/telefono/stream")
async def stream(ws: WebSocket):
    """El audio de la llamada, en los dos sentidos."""
    global _llamada_activa
    await ws.accept()
    _llamada_activa = True
    stream_sid = None
    juntado = bytearray()
    ultimo_sonido = 0.0
    hablado = 0.0
    hablando_yo = False
    print("telefono: llamada conectada", flush=True)

    async def decir(texto):
        """Manda la respuesta a la llamada, en trozos de 20 ms como pide Twilio."""
        nonlocal hablando_yo
        hablando_yo = True
        mulaw = await asyncio.to_thread(_voz_a_mulaw, texto)
        paso = int(TASA_TEL * TROZO_MS / 1000)      # 160 bytes
        for i in range(0, len(mulaw), paso):
            await ws.send_text(json.dumps({
                "event": "media", "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(mulaw[i:i+paso]).decode()}}))
            await asyncio.sleep(TROZO_MS / 1000 * 0.9)   # apenas mas rapido que el reloj
        hablando_yo = False

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            ev = msg.get("event")
            if ev == "start":
                stream_sid = msg["start"]["streamSid"]
                print(f"telefono: stream {stream_sid} arrancado", flush=True)
                await decir("Hola, te escucho.")
                ultimo_sonido = time.time()
                continue
            if ev == "stop":
                break
            if ev != "media" or hablando_yo:
                continue                              # mientras hablo yo, no escucho

            trozo = base64.b64decode(msg["media"]["payload"])
            juntado += trozo
            pcm = audioop.ulaw2lin(trozo, 2)
            ahora = time.time()
            if audioop.rms(pcm, 2) > UMBRAL_VOZ:
                hablado += TROZO_MS / 1000
                ultimo_sonido = ahora

            # ¿Terminaste de hablar? Igual que en el navegador, pero midiendo aca.
            if hablado >= MIN_HABLADO and ahora - ultimo_sonido > SILENCIO_CORTE:
                audio, juntado, hablado = bytes(juntado), bytearray(), 0.0
                ruta = _mulaw_a_wav(audio)
                try:
                    dicho = await asyncio.to_thread(_transcribir, str(ruta))
                finally:
                    ruta.unlink(missing_ok=True)
                if not dicho:
                    continue
                print("telefono dicho:", dicho, flush=True)
                respuesta = await asyncio.to_thread(_preguntar, dicho) or "No te entendi."
                print("telefono respuesta:", respuesta, flush=True)
                await decir(respuesta)
                ultimo_sonido = time.time()
            elif len(juntado) > TASA_TEL * 30:        # 30 s sin cortar: soltar lastre
                juntado = bytearray()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("telefono: se corto la llamada:", e, flush=True)
    finally:
        _llamada_activa = False
        print("telefono: llamada terminada", flush=True)


def llamar():
    """Que suene tu celular. Devuelve (ok, detalle)."""
    if not _cfg.get("sid"):
        return False, "faltan las claves de Twilio en el .env"
    if _llamada_activa:
        return False, "ya hay una llamada en curso"
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{_cfg['sid']}/Calls.json",
        auth=(_cfg["sid"], _cfg["token"]),
        data={"To": _cfg["destino"], "From": _cfg["numero_twilio"],
              "Url": f"{_cfg['url_publica']}/telefono/twiml"},
        timeout=30)
    if r.status_code >= 300:
        return False, f"Twilio rechazo la llamada: {r.text[:200]}"
    return True, "te estoy llamando"


def arrancar(modelo, model_lock, piper_voz, preguntar_fn, vocab=None, cfg=None,
             puerto=PUERTO):
    """Levanta el servidor de la llamada. Sin claves, queda apagado."""
    global _modelo, _lock, _piper, _preguntar, _vocab, _cfg
    cfg = cfg or {}
    if not cfg.get("sid") or not cfg.get("token") or not cfg.get("destino"):
        print("telefono: faltan claves de Twilio en el .env (queda apagado)", flush=True)
        return None
    _modelo, _lock, _piper, _preguntar, _vocab, _cfg = (
        modelo, model_lock, piper_voz, preguntar_fn, vocab, cfg)
    hilo = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning"),
        daemon=True, name="telefono")
    hilo.start()
    print(f"telefono: escuchando en 127.0.0.1:{puerto} (/telefono)", flush=True)
    return hilo
