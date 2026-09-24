"""Laura por llamada: hablarle desde el celular, desde donde sea, con tu propia voz.

Pedido del 2026-08-11: una forma de hablar con Laura EN VIVO (no notas de voz de ida
y vuelta) sin depender de Telegram ni WhatsApp, que no soportan llamadas de bot.
La solucion es una paginita web: la abris en el navegador del celular, mantenes
apretado un boton para hablar, y te contesta con audio real — la MISMA Laura, mismo
proceso, misma memoria que por microfono y por Telegram.

ARQUITECTURA: esto NO es un proceso aparte. Corre en un hilo DENTRO de voz.py, que ya
tiene cargados en la GPU el modelo Whisper (turbo) y la voz Piper — cargarlos de
nuevo aca duplicaria VRAM y competiria por ella (ver el comentario de `modelo_wake`
en voz.py sobre lo que pasa cuando la VRAM se llena). arrancar() recibe esos objetos
YA cargados en vez de importarlos: asi este archivo se puede probar sin levantar el
asistente entero (mismo motivo que pruebas/test_escribir.py copia regexes en vez de
importar voz.py — importarlo abre el microfono).

SEGURIDAD, en capas (Laura ejecuta comandos en esta PC — esto no es solo transcribir):
  1. Solo escucha en 127.0.0.1: nadie en la misma wifi te encuentra por IP, unicamente
     por el hostname del tunel de Cloudflare (que ya habla HTTPS).
  2. Requiere el header X-Laura-Token con el secreto de LAURA_VOZ_TOKEN (.env). Sin
     token configurado, esto queda apagado en vez de "abierto por las dudas".
  3. Los intentos fallidos se cuentan por IP (via CF-Connecting-IP si el tunel la
     manda) y se bloquean unos minutos: no es fuerza bruta viable contra un secreto
     de 256 bits, pero corta el ruido de raspado automatico.
  4. Recomendado ADEMAS (no lo hace este archivo, se configura en el dashboard de
     Cloudflare): Access de Cloudflare Zero Trust en el path /laura-voz, que exige
     un login antes de que el pedido llegue siquiera a esta maquina. Ver README.
"""

import time
import base64
import secrets
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

PUERTO = 8760

# --- Estado inyectado por arrancar() (nada de esto se importa, se recibe) --------
_modelo = None
_model_lock = None
_piper_voz = None
_preguntar = None
_vocab = None
_token = None
_historial = None      # funcion sin argumentos -> lista de {"quien","texto"}

app = FastAPI()


# --- El candado: un secreto compartido + limite de intentos fallidos --------------
_FALLOS = {}
_LOCK_FALLOS = threading.Lock()
VENTANA_FALLOS_SEG = 600
MAX_FALLOS = 5


def _ip_de(request: Request) -> str:
    # Cloudflare manda la IP real del que pega el pedido en este header; sin el
    # (pegandole directo al puerto, algo que 127.0.0.1 ya deberia impedir) cae al
    # host de la conexion.
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "?")


def _bloqueada(ip: str) -> bool:
    with _LOCK_FALLOS:
        ahora = time.time()
        vivos = [t for t in _FALLOS.get(ip, []) if ahora - t < VENTANA_FALLOS_SEG]
        _FALLOS[ip] = vivos
        return len(vivos) >= MAX_FALLOS


def _registrar_fallo(ip: str):
    with _LOCK_FALLOS:
        _FALLOS.setdefault(ip, []).append(time.time())


def _verificar(request: Request, x_laura_token: str):
    ip = _ip_de(request)
    if _bloqueada(ip):
        raise HTTPException(429, "Demasiados intentos fallidos. Probá de nuevo en unos minutos.")
    if not _token or not secrets.compare_digest(x_laura_token or "", _token):
        _registrar_fallo(ip)
        raise HTTPException(401, "Token invalido.")


# --- Los tres pasos: escuchar, pensar, contestar -----------------------------------

def _sufijo_de(content_type: str) -> str:
    return {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
            "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get((content_type or "").split(";")[0], ".bin")


def _transcribir(ruta: str) -> str:
    # Mismo lock que el dictado y el asistente: un solo Whisper, un turno a la vez
    # (la lección del 2026-08-11 con el core.py del transcriptor de WhatsApp — GPU al
    # 100% y cero avance con varios hilos llamando transcribe() a la vez).
    with _model_lock:
        segmentos, _info = _modelo.transcribe(
            ruta, language="es", vad_filter=True, beam_size=1,
            condition_on_previous_text=False, initial_prompt=_vocab)
        return " ".join(s.text.strip() for s in segmentos).strip()


def _sintetizar(texto: str) -> bytes:
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        _piper_voz.synthesize_wav(texto, wf)
    return buf.getvalue()


@app.post("/laura-voz/hablar")
async def hablar_ep(request: Request, audio: UploadFile = File(...),
                     x_laura_token: str = Header(default="")):
    _verificar(request, x_laura_token)
    datos = await audio.read()
    if not datos:
        raise HTTPException(400, "Audio vacio.")
    ruta = None
    try:
        with tempfile.NamedTemporaryFile(suffix=_sufijo_de(audio.content_type), delete=False) as f:
            f.write(datos)
            ruta = f.name
        dicho = _transcribir(ruta)
    finally:
        if ruta:
            try:
                Path(ruta).unlink(missing_ok=True)
            except OSError:
                pass
    if not dicho:
        raise HTTPException(422, "No te escuché bien, no se entendió nada.")
    print("llamada dicho:", dicho, flush=True)
    respuesta = _preguntar(dicho) or "No tengo respuesta para eso."
    print("llamada respuesta:", respuesta, flush=True)
    audio_wav = _sintetizar(respuesta)
    return JSONResponse({
        "dicho": dicho,
        "respuesta": respuesta,
        "audio_b64": base64.b64encode(audio_wav).decode("ascii"),
    })


@app.get("/laura-voz/historial")
async def historial_ep(request: Request, x_laura_token: str = Header(default="")):
    # Pedido del 2026-08-11: que la pagina muestre el sentido de la charla al
    # abrirla, en vez de arrancar en blanco como si Laura no se acordara de nada
    # (la misma sensacion de "amnesia" que ya paso una vez por Telegram). Se pide
    # de nuevo CADA VEZ que se abre la pagina, a la sesion real -- no se guarda
    # nada en el celular, asi que siempre refleja lo que Laura de verdad recuerda,
    # nunca un historial viejo pegado en el navegador.
    _verificar(request, x_laura_token)
    turnos = _historial() if _historial else []
    return JSONResponse({"turnos": turnos})


@app.get("/laura-voz", response_class=HTMLResponse)
async def pagina():
    return _PAGINA


def arrancar(modelo, model_lock, piper_voz, preguntar_fn, vocab=None, token=None,
             puerto=PUERTO, historial_fn=None):
    """Prende el servidor de llamada. Sin token configurado, queda apagado."""
    global _modelo, _model_lock, _piper_voz, _preguntar, _vocab, _token, _historial
    import os
    _modelo, _model_lock, _piper_voz, _preguntar, _vocab, _historial = (
        modelo, model_lock, piper_voz, preguntar_fn, vocab, historial_fn)
    _token = token or os.environ.get("LAURA_VOZ_TOKEN", "").strip()
    if not _token:
        print("llamada: LAURA_VOZ_TOKEN no esta configurado en el .env, "
              "la llamada por celular queda APAGADA (no abierta).", flush=True)
        return
    threading.Thread(target=_correr, args=(puerto,), daemon=True).start()
    print(f"llamada: escuchando en 127.0.0.1:{puerto} (/laura-voz)", flush=True)


def _correr(puerto):
    uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning")


_PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Laura</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    background: linear-gradient(160deg, #14121f, #1c1830 60%, #241b3a);
    color: #f1eefc; font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
    overflow: hidden;
  }
  #candado {
    position: fixed; inset: 0; background: #0f0d18; display: flex;
    flex-direction: column; align-items: center; justify-content: center;
    gap: 14px; padding: 24px; z-index: 10;
  }
  #candado h1 { font-size: 1.1rem; font-weight: 600; margin: 0 0 6px; }
  #candado input {
    width: 100%; max-width: 320px; padding: 14px 16px; border-radius: 12px;
    border: 1px solid #3a3355; background: #1c1830; color: #f1eefc; font-size: 1rem;
  }
  #candado button {
    width: 100%; max-width: 320px; padding: 14px; border-radius: 12px; border: none;
    background: #8a6ff2; color: white; font-size: 1rem; font-weight: 600;
  }
  #candado p { color: #a89fc9; font-size: 0.85rem; text-align: center; max-width: 320px; }
  header { padding: 18px 20px 10px; text-align: center; }
  header h1 { margin: 0; font-size: 1.15rem; }
  header p { margin: 4px 0 0; color: #9a8fc0; font-size: 0.8rem; }
  #charla {
    flex: 1; overflow-y: auto; padding: 10px 16px; display: flex;
    flex-direction: column; gap: 10px;
  }
  .burbuja { max-width: 82%; padding: 10px 14px; border-radius: 16px; line-height: 1.35; font-size: 0.95rem; }
  .vos { align-self: flex-end; background: #8a6ff2; color: white; }
  .laura { align-self: flex-start; background: #2a2440; color: #f1eefc; }
  #estado { text-align: center; color: #a89fc9; font-size: 0.82rem; min-height: 1.2em; padding-bottom: 4px; }
  #zona-boton { padding: 18px 20px 28px; display: flex; justify-content: center; }
  #hablar {
    width: 96px; height: 96px; border-radius: 50%; border: none; font-size: 2rem;
    background: #8a6ff2; color: white; box-shadow: 0 0 0 0 rgba(138,111,242,.5);
    transition: transform .12s, box-shadow .3s; touch-action: none; user-select: none;
  }
  #hablar.grabando { background: #e0435c; transform: scale(1.08);
    box-shadow: 0 0 0 14px rgba(224,67,92,.18); }
  #hablar.pensando { background: #5b5578; }
  #hablar:disabled { opacity: .6; }
</style>
</head>
<body>

<div id="candado">
  <h1>Para hablar con Laura</h1>
  <input id="token" type="password" placeholder="Tu clave" autocomplete="off">
  <button onclick="guardarToken()">Entrar</button>
  <p>Se guarda solo en este navegador, mientras esta pestaña esté abierta.</p>
</div>

<header>
  <h1>Laura</h1>
  <p>Mantené apretado el botón, hablá, soltá.</p>
</header>
<div id="charla"></div>
<div id="estado"></div>
<div id="zona-boton">
  <button id="hablar">🎙️</button>
</div>

<script>
const TOKEN_KEY = "laura_voz_token";
const candado = document.getElementById("candado");
const tokenInput = document.getElementById("token");
const charla = document.getElementById("charla");
const estado = document.getElementById("estado");
const boton = document.getElementById("hablar");

function token() { return sessionStorage.getItem(TOKEN_KEY) || ""; }

function guardarToken() {
  const v = tokenInput.value.trim();
  if (!v) return;
  sessionStorage.setItem(TOKEN_KEY, v);
  candado.style.display = "none";
  cargarHistorial();
}
if (token()) { candado.style.display = "none"; }
tokenInput.addEventListener("keydown", e => { if (e.key === "Enter") guardarToken(); });

function burbuja(texto, quien) {
  const b = document.createElement("div");
  b.className = "burbuja " + quien;
  b.textContent = texto;
  charla.appendChild(b);
  charla.scrollTop = charla.scrollHeight;
}

async function cargarHistorial() {
  // Se pide de nuevo cada vez que se abre la pagina: nunca se guarda en el
  // celular, asi que siempre muestra lo que Laura de verdad recuerda ahora,
  // ni una version vieja pegada en el navegador ni nada acumulado de mas.
  if (!token()) return;
  charla.innerHTML = "";
  try {
    const r = await fetch("/laura-voz/historial", { headers: { "X-Laura-Token": token() } });
    if (!r.ok) return;
    const d = await r.json();
    (d.turnos || []).forEach(t => burbuja(t.texto, t.quien));
  } catch (e) { /* sin historial no pasa nada grave: se sigue igual */ }
}
if (token()) cargarHistorial();

let mediaRecorder = null;
let chunks = [];
let grabando = false;

async function empezar() {
  if (grabando || boton.disabled) return;
  if (!token()) { candado.style.display = "flex"; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      mandar(new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" }));
    };
    mediaRecorder.start();
    grabando = true;
    boton.classList.add("grabando");
    estado.textContent = "Escuchando...";
  } catch (e) {
    estado.textContent = "No pude usar el micrófono: " + e.message;
  }
}

function terminar() {
  if (!grabando) return;
  grabando = false;
  boton.classList.remove("grabando");
  mediaRecorder.stop();
}

async function mandar(blob) {
  boton.classList.add("pensando");
  boton.disabled = true;
  estado.textContent = "Laura está pensando...";
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  try {
    const r = await fetch("/laura-voz/hablar", {
      method: "POST", body: form, headers: { "X-Laura-Token": token() },
    });
    if (r.status === 401) {
      sessionStorage.removeItem(TOKEN_KEY);
      candado.style.display = "flex";
      estado.textContent = "Esa clave no es correcta.";
      return;
    }
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      estado.textContent = d.detail || "Algo falló.";
      return;
    }
    const d = await r.json();
    burbuja(d.dicho, "vos");
    burbuja(d.respuesta, "laura");
    estado.textContent = "";
    const audio = new Audio("data:audio/wav;base64," + d.audio_b64);
    audio.play().catch(() => { estado.textContent = "Tocá la pantalla para escuchar."; });
  } catch (e) {
    estado.textContent = "No hay conexión con Laura.";
  } finally {
    boton.classList.remove("pensando");
    boton.disabled = false;
  }
}

boton.addEventListener("pointerdown", empezar);
boton.addEventListener("pointerup", terminar);
boton.addEventListener("pointercancel", terminar);
</script>
</body>
</html>"""
