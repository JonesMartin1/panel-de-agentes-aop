"""
Voz: dictado + asistente en UN solo proceso (comparten un unico modelo Whisper).

  F9 (solo)   -> DICTADO: transcribe y PEGA el texto donde tengas el cursor.
  Shift+F9    -> ASISTENTE: transcribe, ejecuta la accion (acciones.py) o pregunta
                 al LLM local (cerebro.py), y te contesta por VOZ (Piper es-AR).
  Ctrl+F9     -> CLAUDE: manda el pedido al Claude Code CLI (solo lectura) sin tener
                 que nombrarlo. Tambien sirve decir "Claude, ..." con Shift+F9, y los
                 seguimientos siguen yendo a Claude por 150s (ver _CONTINUIDAD).

Un solo modelo cargado = mitad de VRAM, sin conflictos. Nunca resignas el dictado.
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)

import ctypes                       # DPI-aware PARA TODO el proceso (antes de pyautogui/mss)
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)   # PER_MONITOR_AWARE_V2
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import re
import sys
import json
import time
import wave
import queue
import tempfile
import threading
import winsound
from pathlib import Path

# ⭐ El log en UTF-8 y sin morir por un caracter raro. Todo lo que se ve del
# asistente sale por print a logs/voz.log, y Python lo escribia con la
# codificacion del sistema (cp1252): un emoji en una respuesta de Laura tiraba
# UnicodeEncodeError DENTRO del print. El 2026-08-14 eso mato el hilo del buzon
# (un 🔊 en una respuesta) y desde ahi el chat del panel y Telegram quedaron sin
# contestar, sin ningun mensaje de error visible. errors="replace" es el seguro:
# un caracter que no entre se dibuja mal, pero nunca tumba nada. De paso arregla
# los acentos rotos que se veian en el chat del panel.
for _salida in (sys.stdout, sys.stderr):
    try:
        _salida.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.nucleo import core
from faster_whisper import WhisperModel
import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
from piper import PiperVoice

from app.voz import acciones
from app.voz import cerebro
from app.voz import escucha

from app.rutas import (CONFIG_DICTADO, MUSICA_ESPERA, LOGS, PAUSA_ESCUCHA,
                       SEGUIR_LECTURA, ESCRIBIR_EN, MIC_BLOQUEADO,
                       AVISOS_HABLADOS, CORTAR_VOZ, ESCUCHAR_YA, PENSANDO,
                       NUEVA_SESION, COMPACTAR_LAURA)
from app.rutas import VOZ_PIPER as _VOZ_PIPER

VOZ_PIPER = str(_VOZ_PIPER)
SR = 16000
MIN_SEG = 0.3
SONIDO = False           # beeps del dictado (True para reactivar)
CFG_FILE = CONFIG_DICTADO


# El MISMO microfono aparece varias veces, una por cada camino de audio de Windows
# (MME, DirectSound, WASAPI, WDM-KS). Antes se tomaba "la primera que coincida", que
# daba DirectSound: una capa de emulacion legacy que, cuando el dispositivo se va y
# vuelve (los inalambricos se duermen, el dongle se re-enumera), se queda entregando
# CEROS sin dar error. Los callbacks siguen llegando, asi que parece vivo, pero no
# capta nada -> "una grabacion que tenia que traer audio volvio vacia".
# WASAPI es el camino nativo de Windows y se recupera bien de esos cambios.
# WDM-KS queda AFUERA: sounddevice no soporta su API bloqueante
# ("Blocking API not supported yet", PaErrorCode -9999). Probado el 2026-08-10.
_APIS_PREFERIDAS = ("Windows WASAPI", "Windows DirectSound", "MME")


def _extra_de(indice):
    """WASAPI en modo compartido EXIGE la frecuencia nativa del dispositivo (48000)
    y nosotros abrimos a 16000 para Whisper: sin auto_convert tira
    'Invalid sample rate [PaErrorCode -9997]'. Con auto_convert, PortAudio
    resamplea solo. Probado el 2026-08-10."""
    try:
        if indice is None:
            return None
        if _api_de(indice) == "Windows WASAPI":
            return sd.WasapiSettings(auto_convert=True)
    except Exception:
        pass
    return None


def _candidatos_micro(nombre=None):
    """(indice, extra, api) del micro elegido, del camino de audio mas robusto al
    menos. Si el primero no abre, se prueba el siguiente antes de rendirse."""
    if nombre is None:
        try:
            nombre = json.loads(CFG_FILE.read_text(encoding="utf-8")).get("microfono")
        except Exception:
            nombre = None
    if not nombre:
        return []
    orden = []
    try:
        apis = sd.query_hostapis()
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] <= 0 or d["name"] != nombre:
                continue
            api = apis[d["hostapi"]]["name"]
            if api not in _APIS_PREFERIDAS:
                continue
            orden.append((_APIS_PREFERIDAS.index(api), i, api))
        orden.sort()
    except Exception:
        pass
    return [(i, _extra_de(i), api) for _, i, api in orden]


def _device(nombre=None):
    """Indice del microfono elegido, por el camino de audio mas robusto."""
    cands = _candidatos_micro(nombre)
    return cands[0][0] if cands else None


def _api_de(indice):
    """Nombre del camino de audio de un dispositivo, para poder loguearlo."""
    try:
        if indice is None:
            return "predeterminado"
        return sd.query_hostapis()[sd.query_devices(indice)["hostapi"]]["name"]
    except Exception:
        return "?"


def _beep(freq, dur):
    if SONIDO:
        try:
            winsound.Beep(freq, dur)
        except Exception:
            pass


# --- Modelo unico (turbo) + voz Piper ---
model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16",
                     download_root=core.DIR_MODELOS, local_files_only=True)
# Modelo chico SOLO para oir el nombre (Laura/Venus), EN CPU a proposito:
# en la GPU competia con el turbo + video + monitores (VRAM 91%) y un chequeo de
# 0.1s se estiraba hasta 5.9s. En CPU tarda ~0.5s SIEMPRE, pase lo que pase en la
# GPU, y encima le libera memoria al resto. Probado: detecta igual de bien.
modelo_wake = WhisperModel("tiny", device="cpu", compute_type="int8",
                           download_root=core.DIR_MODELOS, local_files_only=True)
voz = PiperVoice.load(VOZ_PIPER)
_WAV = str(Path(tempfile.gettempdir()) / "voz_tts.wav")
_lock = threading.Lock()
_model_lock = threading.Lock()      # modelo grande (comandos/dictado)
_wake_lock = threading.Lock()       # modelo chico (nombre); separado para que no se traben entre si


# --- Interrupcion (barge-in) -------------------------------------------------
# Cada vez que apretas F9 empieza una "epoca" nueva: se corta el audio que este
# sonando y todo trabajo viejo queda invalidado (no habla ni actua tarde).
_epoca = 0
_epoca_lock = threading.Lock()


def _nueva_epoca():
    global _epoca
    with _epoca_lock:
        _epoca += 1
        return _epoca


def _vigente(ep):
    return ep is None or ep == _epoca


def _interrumpir(motivo=""):
    """Corta el habla actual y cancela lo que estuviera haciendo.

    El motivo queda en voz_eventos.log CON hora: sin eso, un corte por voz y uno
    por tecla se ven igual y no hay forma de saber si te escucho cuando la
    llamaste encima o si te cortaste vos sin querer.
    """
    _nueva_epoca()
    if motivo:
        _evento(f"INTERRUMPIDA por {motivo}"
                + (" (estaba hablando)" if _hablando else "")
                + (" (estaba pensando)" if _procesando else ""))
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)     # frena el audio ya mismo
    except Exception:
        pass
    try:
        from app.voz import cerebro_grande as claude_voz
        claude_voz.cancelar()                            # mata la consulta a Claude en vuelo
    except Exception:
        pass


def _dur_wav(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 10.0


# Log aparte, CON hora. voz.log no puede llevar timestamps al inicio de la linea
# porque /chat del panel parsea con startswith y se rompe el chat entero; pero sin
# hora no se puede reconstruir que paso antes de que (por ejemplo) se corte una
# lectura por la mitad. Solucion: un archivo aparte solo para diagnosticar.
_LOG_EVENTOS = LOGS / "voz_eventos.log"


def _evento(texto):
    try:
        with open(_LOG_EVENTOS, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {texto}\n")
    except Exception:
        pass


def _medir(etiqueta, t0, extra=""):
    """Loguea cuanto tardo una etapa, para saber DONDE se va el tiempo.

    El prefijo 'tiempos:' es a proposito: /chat del panel parsea con una lista
    blanca de prefijos, asi que estas lineas no aparecen en la conversacion en
    vivo. OJO: NO ponerle timestamp al inicio de las OTRAS lineas del log; el
    parser usa startswith y se rompe todo el chat. La version con hora va a
    logs/voz_eventos.log.
    """
    linea = f"{etiqueta}={time.time() - t0:.2f}s" + (f"  {extra}" if extra else "")
    print(f"tiempos: {linea}", flush=True)
    _evento(linea)


# Piper tarda ~30 ms por letra en textos largos, asi que sintetizar la respuesta
# COMPLETA antes de abrir la boca son 10 s de silencio en una respuesta de Laura
# (medido: 344 letras -> 10,34 s). Se corta en pedazos, se empieza a reproducir el
# primero y los demas se generan mientras suena. Como Piper va a 1,12x tiempo real
# (mas rapido de lo que se escucha), alcanza a generarlos y no quedan huecos.
# El PRIMER trozo va corto a proposito: lo que de verdad se siente es cuanto tarda
# en decir la primera palabra. Los siguientes van mas grandes (suenan mejor y ya
# quedan tapados por la reproduccion del anterior).
# Los trozos CRECEN de a poco, y el cuanto no es a gusto: sale de la medicion.
# Piper sintetiza a ~30 ms por letra y hablar cuesta ~33,7 ms por letra (medido:
# 344 letras -> 10,34 s de sintesis y ~11,6 s de audio). Para que el trozo
# siguiente este listo antes de que termine de sonar el actual hace falta:
#     0,030 * L(n+1) <= 0,0337 * L(n)   ->   L(n+1) <= 1,12 * L(n)
# O sea que puede crecer 12% por trozo como maximo. Se usa 10% para tener margen.
# Con una rampa mas agresiva quedan huecos de silencio en el medio de la frase.
TTS_TROZO_1 = 60          # letras del primer trozo (~1,8 s hasta la primera palabra)
TTS_CRECIMIENTO = 1.10    # cuanto crece cada trozo respecto del anterior
TTS_TROZO_MAX = 140       # tope: de aca no crece mas
TTS_TROZO_MIN = 25        # un resto mas corto que esto se pega al anterior
# DOS juegos de archivos: cada llamada a hablar() alterna, asi un productor rezagado
# de la llamada anterior no puede pisar los wav de la actual.
#
# ⭐ CUANTOS archivos por juego NO es a gusto, es una cuenta. En el aire hay:
#   1 que esta SONANDO  +  TTS_COLA esperando en la cola  +  1 que se esta escribiendo
# Habia 3 con una cola de 2, o sea uno MENOS que los 4 necesarios, y el comentario
# de antes afirmaba que asi "nunca se sobreescribe uno que suena". Estaba mal por uno:
# el productor abria en "wb" justo el archivo que el consumidor tenia sonando, lo
# truncaba, y winsound tiraba el DING de error de Windows. Nunca se vio porque Laura
# contesta en 1 a 3 frases (<=3 trozos, no llega a dar la vuelta). Aparecio el
# 2026-08-11 con el primer resumen de sesion: 507 letras, 8 trozos, varios dings.
# Por eso el numero se DERIVA de la cola: si cambia una, cambia la otra sola.
# ⭐ Cuantos trozos mira el filtro anti-eco (_es_su_propio_eco). ANTES comparaba
# contra la respuesta COMPLETA, y ese era el motivo real de "le digo Laura mientras
# habla y no me da bola": en una respuesta de 2000 letras (un minuto de voz),
# CUALQUIER palabra que ella diga en cualquier momento alcanzaba para descartar lo
# que captaba el microfono. Tu llamado moria como si fuera su propio eco.
# El eco solo puede venir de lo que esta SONANDO, asi que la ventana son los ultimos
# trozos y nada mas. Van 3 y no 1 por el retraso: entre que el parlante suena, el
# microfono lo capta y el fragmento se cierra (0,35 s de silencio) pueden haber
# pasado uno o dos trozos. Con 3 el margen sobra (~6-12 s de audio hacia atras) y
# sigue siendo 10 veces menos agresivo que la respuesta entera.
# Bajarlo a 1 = mas riesgo de que se autodispare con su propia voz. Subirlo mucho =
# volves al problema de antes, imposible cortarla hablando.
ECO_VENTANA = 3
TTS_COLA = 2              # cuanto se adelanta el productor
TTS_ARCHIVOS = TTS_COLA + 3        # 1 sonando + los de la cola + 1 escribiendose + 1 de margen
# ⭐ Y el nombre lleva el PID. Antes eran "voz_tts_00.wav" a secas, en el temp de
# Windows: DOS procesos del asistente escribian los MISMOS archivos y se cortaban el
# audio mutuamente. Paso el 2026-08-11: arranco un segundo proceso en medio de una
# lectura de 2 minutos y los dings fueron de eso, no de la rotacion. Con el PID
# adentro, dos instancias no pueden pisarse ni queriendo (el panel abriendo un
# duplicado, el /medidor, o alguien importando el modulo para mirar una constante).
_WAV_TROZOS = [[str(Path(tempfile.gettempdir()) / f"voz_tts_{os.getpid()}_{g}{i}.wav")
                for i in range(TTS_ARCHIVOS)] for g in range(2)]


def _limpiar_wav_huerfanos():
    """Borra los wav de trozos que dejaron procesos que ya no existen.

    Ahora que el nombre lleva el PID, cada corrida deja su propio juego de archivos.
    Sin esto se irian acumulando de a 10 por reinicio, y el asistente se reinicia seguido.
    """
    mio = f"voz_tts_{os.getpid()}_"
    for p in Path(tempfile.gettempdir()).glob("voz_tts_*.wav"):
        if p.name.startswith(mio):
            continue
        try:
            p.unlink()                    # si otro proceso lo tiene abierto, Windows no deja
        except OSError:
            pass


_limpiar_wav_huerfanos()
_tts_gen = 0              # contador de llamadas, para alternar el juego de archivos


def _piezas_tts(texto):
    """Cortes minimos: por pausas (punto, coma, dos puntos) y, si una pieza sigue
    siendo larga, por palabras. Nunca corta una palabra al medio."""
    piezas = []
    for oracion in re.split(r"(?<=[.!?…])\s+", texto.strip()):
        for clausula in re.split(r"(?<=[,;:])\s+", oracion):
            if not clausula.strip():
                continue
            if len(clausula) <= TTS_TROZO_1:
                piezas.append(clausula)
                continue
            buf = ""
            for palabra in clausula.split():
                if buf and len(buf) + len(palabra) + 1 > TTS_TROZO_1:
                    piezas.append(buf)
                    buf = palabra
                else:
                    buf = (buf + " " + palabra).strip()
            if buf:
                piezas.append(buf)
    return piezas


def _partir_para_tts(texto):
    """Arma los trozos a sintetizar: el primero corto, los demas mas largos."""
    def _limite(n):
        return min(TTS_TROZO_MAX, round(TTS_TROZO_1 * (TTS_CRECIMIENTO ** n)))

    trozos, buf = [], ""
    for pz in _piezas_tts(texto):
        cand = (buf + " " + pz).strip() if buf else pz
        if buf and len(cand) > _limite(len(trozos)):
            trozos.append(buf)
            buf = pz
        else:
            buf = cand
        if len(buf) >= _limite(len(trozos)):   # ya alcanza para arrancar a hablar
            trozos.append(buf)
            buf = ""
    if buf:
        if trozos and len(buf) < TTS_TROZO_MIN:
            trozos[-1] = (trozos[-1] + " " + buf).strip()
        else:
            trozos.append(buf)
    return [t for t in trozos if t.strip()]


def hablar(texto, ep=None):
    global _hablando, _texto_hablando
    if not texto or not _vigente(ep):
        return
    # Si llego hasta aca, la respuesta YA existe: dejo de estar "pensando" aunque
    # todavia falte decirla. Va en hablar() y no en cada camino porque todos los
    # caminos terminan aca. Pedido de Martin el 2026-08-14: veia los puntitos con la
    # respuesta ya escrita en el panel, y con razon — a esa altura no estoy pensando,
    # estoy leyendo en voz alta.
    _marcar_pensando(False)
    with _lock:
        if not _vigente(ep):                 # te adelantaste mientras esperaba el turno
            return
        # Guardamos QUE esta diciendo: si el micro capta justo eso, es su propio eco
        # y no vos. Es lo que permite escucharte mientras habla sin autodispararse.
        # ⭐ Es una VENTANA de los ultimos trozos (ver ECO_VENTANA mas abajo), no la
        # respuesta entera: arranca vacia porque hasta que no suene el primer trozo
        # no hay eco posible, solo la sintesis en silencio.
        _texto_hablando = ""
        _hablando = True
        global _tts_gen
        _tts_gen += 1
        # Cada llamada usa su PROPIO juego de archivos (alterna entre dos): si un
        # productor de la llamada anterior quedo rezagado, no puede pisar los wav
        # que esta usando esta. Antes compartian los 3 y se corrompia el audio.
        rutas = _WAV_TROZOS[_tts_gen % 2]
        parar = threading.Event()
        productor = None
        try:
            trozos = _partir_para_tts(texto)
            _t0 = time.time()
            # Si toca este numero, TTS_ARCHIVOS lo sigue solo (ver el comentario alla).
            cola = queue.Queue(maxsize=TTS_COLA)

            def _sintetizar():
                for i, tr in enumerate(trozos):
                    if parar.is_set() or not _vigente(ep):
                        break
                    ruta = rutas[i % len(rutas)]
                    try:
                        with wave.open(ruta, "wb") as wf:
                            voz.synthesize_wav(tr, wf)
                    except Exception as e:
                        print("error TTS:", e, flush=True)
                        break
                    # put CON timeout: si el consumidor se fue (te adelantaste), la
                    # cola queda llena para siempre y un put a secas dejaba este
                    # hilo bloqueado eternamente, con archivos a medio escribir.
                    entregado = False
                    while not entregado and not parar.is_set():
                        try:
                            cola.put((ruta, _dur_wav(ruta), tr), timeout=0.2)
                            entregado = True
                        except queue.Full:
                            pass
                    if not entregado:
                        break
                # La marca de fin tambien va con REINTENTO. Con un put de un solo
                # intento, si la cola estaba llena la marca se perdia en silencio y
                # el consumidor se quedaba esperando para siempre CON EL _lock
                # TOMADO: Laura no volvia a hablar nunca mas (pasado el 2026-08-10,
                # en la primera respuesta de 4 trozos). No volver a poner un put
                # sin reintento aca.
                entregado = False
                while not entregado and not parar.is_set():
                    try:
                        cola.put(None, timeout=0.2)
                        entregado = True
                    except queue.Full:
                        pass

            productor = threading.Thread(target=_sintetizar, daemon=True)
            productor.start()

            primero = True
            cortado = False
            sonando = []                     # los ultimos trozos que salieron por el parlante
            while True:
                # get CON timeout, no a secas: si por cualquier motivo no llega la
                # marca de fin, se sale igual al ver que el productor ya murio. Es el
                # cinturon de seguridad para no volver a colgar hablar() nunca.
                try:
                    item = cola.get(timeout=0.3)
                except queue.Empty:
                    if not productor.is_alive():
                        break                # no viene nada mas
                    if not _vigente(ep):
                        cortado = True
                        break
                    continue
                if item is None:
                    break
                if not _vigente(ep):
                    cortado = True
                    break
                ruta, dur, tr = item
                if primero:
                    # Esto es lo que de verdad se siente: cuanto tardo en decir la
                    # PRIMERA palabra. Antes era la sintesis del texto entero.
                    # Todo con "clave=valor": asi lo levanta pruebas/analizar_tiempos.py
                    _medir("tts_primera_palabra", _t0,
                           f"letras={len(tr)} total={len(texto)} trozos={len(trozos)}")
                    primero = False
                # La ventana anti-eco se corre JUSTO ANTES de reproducir, asi que
                # siempre dice lo que esta saliendo por el parlante en este momento.
                sonando = (sonando + [tr])[-ECO_VENTANA:]
                _texto_hablando = acciones._norm(" ".join(sonando))
                winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC)
                fin = time.time() + dur + 0.05
                while time.time() < fin:
                    if not _vigente(ep):     # "para / basta": cortar en el acto
                        winsound.PlaySound(None, winsound.SND_PURGE)
                        cortado = True
                        break
                    time.sleep(0.05)
                if cortado:
                    break
            if cortado:
                # Queda registrado CON hora: asi se puede ver si te cortó porque te
                # adelantaste vos o si se corto sola (eco de sus propios parlantes).
                _evento(f"tts CORTADO por te-adelantaste  letras={len(texto)} "
                        f"trozos={len(trozos)} a los {time.time() - _t0:.1f}s")
            else:
                _medir("tts_total", _t0, f"letras={len(texto)}")
        except Exception as e:
            print("error TTS:", e, flush=True)
        finally:
            # Frenar y ESPERAR al productor antes de salir. Si no, seguia
            # sintetizando por su cuenta y la proxima vez que hablara habia dos
            # hilos escribiendo wav a la vez.
            parar.set()
            if productor is not None:
                try:                          # vaciar la cola: si no, sigue trabado
                    while True:
                        cola.get_nowait()
                except Exception:
                    pass
                productor.join(timeout=3.0)
                if productor.is_alive():
                    _evento("AVISO: el productor de TTS no termino en 3s")
            _hablando = False
            _texto_hablando = ""
            _silenciar_hasta(0.4)            # margen por el eco de los parlantes


# --- "Ey" de confirmacion del wake word ---------------------------------------
# Se sintetiza UNA vez al arrancar (no agrega demora) y se baja el volumen para
# que sea un aviso suave, no una interrupcion.
_WAV_EY = str(Path(tempfile.gettempdir()) / "voz_ey.wav")      # abre el micro
_WAV_OK = str(Path(tempfile.gettempdir()) / "voz_ok.wav")      # te escuche, cierro
_WAV_NADA = str(Path(tempfile.gettempdir()) / "voz_nada.wav")      # no llegue a escuchar nada
_WAV_CIERRO = str(Path(tempfile.gettempdir()) / "voz_cierro.wav")  # fin de la charla con Laura
_WAV_ENTIENDO = str(Path(tempfile.gettempdir()) / "voz_entiendo.wav")  # cierre de LAURA
_WAV_MUSICA = str(MUSICA_ESPERA)
EY_TEXTO = "Te escucho."
OK_TEXTO = "Ok."                  # cierre de VENUS (no tocar: al usuario le gusta asi)
NADA_TEXTO = "No te escuché."
CIERRO_TEXTO = "Cierro."          # corto a proposito: suena tras CADA respuesta de Laura
ENTIENDO_TEXTO = "Entiendo."      # cierre de LAURA (Venus sigue diciendo "Ok")
EY_VOLUMEN = 0.30          # 0-1: bajalo/subilo a gusto


def _preparar_avisito(path, texto, volumen=EY_VOLUMEN):
    """Sintetiza un aviso corto con la voz del asistente y le baja el volumen."""
    tmp = path + ".tmp"
    try:
        with wave.open(tmp, "wb") as wf:
            voz.synthesize_wav(texto, wf)
        with wave.open(tmp, "rb") as r:
            params = r.getparams()
            datos = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16)
        with wave.open(path, "wb") as w:
            w.setparams(params)
            w.writeframes((datos * volumen).astype(np.int16).tobytes())
        return True
    except Exception as e:
        print(f"no pude preparar el aviso {texto!r}:", e, flush=True)
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


_EY_OK = _preparar_avisito(_WAV_EY, EY_TEXTO)
_EY_DUR = _dur_wav(_WAV_EY) if _EY_OK else 0.0
_OK_OK = _preparar_avisito(_WAV_OK, OK_TEXTO)
_NADA_OK = _preparar_avisito(_WAV_NADA, NADA_TEXTO)
_CIERRO_OK = _preparar_avisito(_WAV_CIERRO, CIERRO_TEXTO)
# El "Entiendo." de Laura ya no se usa, asi que no se genera: son ~0,5 s menos de
# arranque. Para volver a activarlo: descomentar esto y el _sonar() de
# _cerrar_por_silencio (buscar ENTIENDO_TEXTO).
# _ENTIENDO_OK = _preparar_avisito(_WAV_ENTIENDO, ENTIENDO_TEXTO)


# El micro se abre YA y el saludo suena en paralelo, asi que los parlantes se lo
# meten en la grabacion. Esto lo saca del principio para que no ensucie el pedido.
# Whisper capta el saludo entero o solo la cola ("Escucho.", "Escucha."), por eso
# van todas las variantes: si queda pegado adelante rompe los comandos (sobre todo
# el de solo-un-numero, que exige que el numero sea TODA la frase).
_ECO_SALUDO = re.compile(
    r"^(?:\W*(?:te\s+escucho|escucho|escucha|escuchando|entiendo|cierro|"
    r"no\s+te\s+escuch\w*|okey|ok|ey)\b[\s,.:;¿?¡!-]*)+", re.IGNORECASE)


def _sonar_ey():
    """Aviso corto de 'te escucho'. No bloquea: sigue grabando mientras suena."""
    if not _EY_OK:
        return
    try:
        winsound.PlaySound(_WAV_EY, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def _sonar(path, ok=True):
    if not ok:
        return
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def _pegar(texto):
    try:
        previo = pyperclip.paste()
    except Exception:
        previo = ""
    pyperclip.copy(texto)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.25)
    try:
        pyperclip.copy(previo)
    except Exception:
        pass


# --- Grabacion ---
_grabando = False
_buf = []
_modo = None
_shift = _ctrl = _alt = False


# --- Manos libres (wake word) ---
#   "Laura" -> Claude      |      "Venus" -> asistente local
# Porcupine es mejor, pero necesita cuenta: si algun dia estan los .ppn, se usa solo.
# Mientras tanto: deteccion con el propio Whisper, sin cuentas ni descargas.
_wake_porcupine = escucha.iniciar()
WAKE_ON = True

# --- Pausa de escucha (para llamadas y juegos) --------------------------------
# El panel crea/borra un archivo y aca se lee cada medio segundo. A proposito NO
# se consulta el disco dentro de _cb: ese callback corre decenas de veces por
# segundo y tocar el filesystem ahi seria una barbaridad.
# Pausar apaga SOLO la palabra clave; los modelos quedan cargados, asi que volver
# es instantaneo (en vez de los ~20 s que tarda prender la voz de cero) y F9 y los
# atajos siguen funcionando igual.
_pausado = PAUSA_ESCUCHA.exists()
ESCUCHAR_VENCE = 15       # segundos: un boton 🎙 apretado hace mas de esto ya no vale


def _marcar_pensando(si):
    """Deja (o saca) la señal de 'estoy resolviendo algo ahora'.

    Es solo para que el panel pueda mostrar los puntitos aunque el pedido no haya
    salido de su caja de texto: le hablas por microfono y la animacion aparece
    igual. Nunca puede tirar una excepcion — esto es cosmetico y no vale romper un
    turno por no poder escribir un archivo.
    """
    try:
        if si:
            if not PENSANDO.exists():
                _evento("pensando: EMPIEZA")
            PENSANDO.write_text("1", encoding="utf-8")
        else:
            if PENSANDO.exists():
                _evento("pensando: termina")
            PENSANDO.unlink(missing_ok=True)
    except Exception:
        pass


_marcar_pensando(False)   # si el proceso anterior murio pensando, la señal quedo puesta


def _vigilar_pausa():
    """Mira las dos señales que deja el panel: la pausa y el corte.

    Van juntas en el mismo hilo porque las dos son "mirar si existe un archivo"
    cada medio segundo. La pausa es un estado (queda puesta hasta que la saques);
    el corte es un pulso: se ve una vez, se borra y se interrumpe.
    """
    global _pausado
    while True:
        try:
            ahora = PAUSA_ESCUCHA.exists()
            if ahora != _pausado:
                _pausado = ahora
                estado = "PAUSADA (no escucho la palabra clave)" if ahora else "REANUDADA"
                print(f"escucha: {estado}", flush=True)
                _evento(f"escucha {estado}")
            # El boton ✋ del panel: lo mismo que llamarla por el nombre mientras
            # habla, pero desde la pantalla. Se borra ANTES de interrumpir: si
            # _interrumpir() fallara, el pulso no puede quedar repitiendose solo.
            if CORTAR_VOZ.exists():
                CORTAR_VOZ.unlink(missing_ok=True)
                print("corte: pedido desde el panel", flush=True)
                _interrumpir("boton del panel")
            # Los botones 🎙 del panel: apretar el boton ES decir el nombre. No se
            # reimplementa nada -- entra por _disparar_wake, el mismo punto que el
            # wake word, asi que hereda el "Te escucho", los tiempos de silencio,
            # el "No te escuche" si no hablas y el ruteo a Laura o a Venus. Si se
            # grabara aparte (en el navegador, por ejemplo) habria que mantener dos
            # versiones de todo eso y se irian separando con el tiempo.
            # El boton "Nueva sesion" del chat del panel: lo mismo que decirle
            # "arranquemos una sesion nueva". La charla que dejas queda archivada,
            # no se pierde (ver claude_voz.olvidar).
            if NUEVA_SESION.exists():
                NUEVA_SESION.unlink(missing_ok=True)
                print("sesion nueva: pedida desde el panel", flush=True)
                try:
                    cerebro.olvidar()
                    from app.voz import cerebro_grande as _cv
                    _cv.olvidar()
                    _avisar_sistema_async("Listo, empecemos de nuevo.")
                except Exception as e:
                    print("no pude arrancar la sesion nueva:", e, flush=True)
            # El boton "Compactar" del chat del panel: le pide un resumen a la charla
            # de ahora y sigue en una nueva sembrada con el, para dejar de arrastrar
            # el contexto entero en cada turno (ver claude_voz.compactar).
            # ⚠ Va en un hilo: son DOS turnos de Claude y este bucle es el que
            # atiende el microfono. Corriendolo aca la deja sorda un minuto largo.
            if COMPACTAR_LAURA.exists():
                COMPACTAR_LAURA.unlink(missing_ok=True)
                print("compactar: pedido desde el panel", flush=True)

                def _compactar_aparte():
                    try:
                        from app.voz import cerebro_grande as _cv
                        _avisar_sistema_async(_cv.compactar())
                    except Exception as e:
                        print("no pude compactar la sesion:", e, flush=True)
                        _avisar_sistema_async("No pude compactar la charla.")

                threading.Thread(target=_compactar_aparte, daemon=True).start()
            if ESCUCHAR_YA.exists():
                modo = "claude"
                viejo = False
                try:
                    modo = (ESCUCHAR_YA.read_text(encoding="utf-8").strip()
                            or "claude")
                    # Un pedido de hace rato NO se atiende: visto en la primera
                    # prueba, un boton apretado con la voz reiniciandose quedaba
                    # esperando y la hacia decir "Te escucho" sola en cuanto
                    # arrancaba, sin que nadie estuviera apretando nada.
                    viejo = time.time() - ESCUCHAR_YA.stat().st_mtime > ESCUCHAR_VENCE
                except Exception:
                    pass
                ESCUCHAR_YA.unlink(missing_ok=True)
                if modo not in ("claude", "local"):
                    modo = "claude"
                if viejo:
                    print("escuchar: pedido viejo, lo descarto", flush=True)
                else:
                    print(f"escuchar: pedido desde el panel ({modo})", flush=True)
                    _disparar_wake(modo)
        except Exception:
            pass
        time.sleep(0.5)


threading.Thread(target=_vigilar_pausa, daemon=True).start()

try:                       # levantar Claude YA, en paralelo: asi tu 1er pedido no espera el arranque
    from app.voz import cerebro_grande as claude_voz
    claude_voz.precalentar()
except Exception as e:
    print("no pude precalentar Claude:", e, flush=True)

# OJO: depende del microfono. Con el auricular BT pegado a la boca la voz llega
# 0.05-0.20; con el micro de la LAPTOP a distancia de silla, apenas 0.01-0.03.
# Calibrado para que funcione con los dos (el ruido de fondo medido es <0.006).
SIL_UMBRAL = 0.008        # RMS por debajo de esto = silencio
SIL_CORTE = 2.5           # silencio que cierra un COMANDO (bajo = te corta antes de terminar)
CORTE_RAPIDO = 0.7        # si a esta altura YA dijiste un comando conocido, se ejecuta sin esperar
SIL_CORTE_DICTADO = 2.8   # ...pero dictando hacés pausas para pensar: hay que tener paciencia
MAX_MANOS_LIBRES = 12     # tope de grabacion de un COMANDO (Venus: NO TOCAR, al usuario le gusta asi)
MAX_CLAUDE = 45           # hablando con Laura explicas cosas largas (con 12s te cortaba al medio)
MAX_DICTADO = 60          # dictando podes hablar largo
ESPERA_INICIO = 3.0       # tras el saludo: si no arrancas a hablar, cierra solo
ESPERA_INICIO_DICTADO = 5 # dictando das mas tiempo para ordenar la idea
# Segundos que Laura sigue escuchando DESPUES de contestar, para conversar de ida y
# vuelta sin volver a nombrarla. SOLO aplica a Laura/Claude: Venus (comandos) no,
# porque ahi el usuario prefiere nombrarla cada vez. 0 = apagado.
#
# OJO: esta es la ventana para que EMPIECES a hablar, no cuanto podes hablar. Una vez
# que arrancaste manda SIL_CORTE (2,5 s de silencio cierra tu turno) y MAX_CLAUDE
# (45 s de tope). Bajar esto NO te corta al medio de una frase.
#
# Historia, para no volver a subirlo sin motivo: estaba en 15 s y se sentia como que
# esperaba encima, con el micro abierto juntando ruido. Se bajo a 6 y seguia
# pareciendo mucho. Quedo en 4, que es lo que el usuario eligio.
# La cola real que se percibe NO es solo este numero, son tres cosas sumadas:
#   0,35 s de margen (el "sordo" que pasa _seguir_escuchando)
# + SEGUIMIENTO segundos de micro abierto en silencio
# + el aviso "Cierro" (~0,7 s de audio), que el usuario decidio MANTENER para saber
#   que dejo de escuchar.
# O sea ~5 s de cola. Si algun dia molesta de nuevo, lo que queda por sacar es el
# aviso (el "cierro" en la llamada a _cerrar_por_silencio de mas abajo), no el numero.
SEGUIMIENTO = 4
MAX_SEGUIDOS = 25         # tope de idas y vueltas sin nombrarla (freno anti-bucle, no un limite de charla)
_seguidos = 0

# Bajo a proposito: solo necesitamos oir el NOMBRE (lo que siga se descarta), asi que
# no hay que esperar la pausa larga. Esto es lo que mas acelera el "Te escucho".
WAKE_SILENCIO = 0.35      # silencio que cierra un fragmento a revisar
WAKE_MIN = 0.30           # fragmentos mas cortos: ruido
WAKE_MAX = 4.0            # mas largos: charla/musica de fondo, ni se transcriben
WAKE_NO_VOZ_MAX = 0.45    # si Whisper cree que no habia voz, no es tu wake word
# Mientras el asistente HABLA tambien te escuchamos, para poder frenarlo por voz.
# MEDIDO aca: con AURICULARES su eco es 0.0048 (no sale por parlantes) -> muchisimo margen.
# Por PARLANTES en cambio llega a 0.068 y se pisa con tu voz (0.05-0.12): ahi el volumen
# NO alcanza para distinguir y quien decide es _es_su_propio_eco(), comparando el TEXTO.
# Este umbral sirve para los dos casos: con auriculares te escucha comodo, y con parlantes
# solo hace que se transcriba de mas (el filtro de texto descarta su propio eco).
WAKE_UMBRAL_HABLANDO = 0.035
# Palabras para cortarlo. Ancladas a TODA la frase: "para" suelto es comunisimo
# ("para mí", "para que"), asi que solo cuenta si es lo unico que decis.
_PARAR = re.compile(r"^\W*(?:basta|callate|calla|silencio|stop|para|para[aá]|pare|"
                    r"cortala|corta|ya esta|suficiente|shh+)\W*$")
# RMS para EMPEZAR a juntar un fragmento. Ruido de fondo medido: hasta 0.006.
# 0.008 funciona tanto con el auricular (voz 0.05+) como con el micro de la
# laptop a distancia (voz 0.01-0.03, que con 0.015 quedaba AFUERA y Venus no oia).
WAKE_UMBRAL = 0.008

# Variantes: Whisper escribe estos nombres de muchas formas.
_WAKE_LAURA = r"(?:h?ey\s+|oye\s+|hola\s+)?(?:laura|lawra|laur|glaura|la ura)"
# OJO: NO incluir "venis" (de "¿venis?", comunisimo) para no dispararlo por error.
_WAKE_VENUS = r"(?:venus|venuz|vennus|benus|benuz|ve nus)"
_WAKE_RX = re.compile(r"\b(" + _WAKE_LAURA + r")\b|\b(" + _WAKE_VENUS + r")\b")
# El nombre PELADO ("Venus.", "¡Laura!"), sin nada mas en el fragmento. Es la llave
# que le gana al filtro anti-eco: ella dice los nombres ADENTRO de frases; un
# fragmento que es SOLO el nombre sos vos llamandola.
_WAKE_PURO = re.compile(r"^\W*(?:" + _WAKE_LAURA + r"|" + _WAKE_VENUS + r")\W*$")

# Palabras sin contenido: si lo que sigue al wake word es solo esto, te cortamos
# la frase al medio -> conviene abrir el micro y esperar en vez de ejecutar basura.
_VACIAS = {"y", "e", "o", "u", "que", "pero", "si", "no", "a", "al", "de", "del", "en",
           "el", "la", "lo", "los", "las", "un", "una", "unos", "unas", "se", "me", "te",
           "es", "eh", "ah", "em", "mmm", "este", "esta", "esto", "bueno", "ok", "por"}


def _resto_util(resto):
    """True si lo que sigue al wake word parece un pedido de verdad."""
    utiles = [w for w in re.findall(r"\w+", resto) if w not in _VACIAS]
    return len(" ".join(utiles)) >= 3

_hablando = False         # el asistente esta hablando
_procesando = False       # transcribio y esta decidiendo/esperando al LLM, todavia no habla
_texto_hablando = ""      # ...y esto es lo que dice (para reconocer su propio eco)
_mudo_hasta = 0.0         # ignorar el micro hasta este instante (eco de parlantes)
_seg = []                 # fragmento de voz que se esta juntando
_seg_activo = False
_seg_t0 = 0.0
_seg_ultimo = 0.0
_seg_largos = 0           # fragmentos tirados por largos MIENTRAS ella hablaba (ver _cb)


def _silenciar_hasta(segundos):
    global _mudo_hasta
    _mudo_hasta = time.time() + segundos


def _cb(indata, frames, t, status):
    global _seg, _seg_activo, _seg_t0, _seg_ultimo
    global _ultimo_audio_real, _ultimo_callback, _captura_vacia
    # DOS medidas distintas, no confundirlas (ver el bloque del watchdog mas abajo):
    #  - FLUJO: llego un callback. Es la UNICA prueba confiable de que el
    #    dispositivo sigue existiendo, porque la cancelacion de ruido puede
    #    vaciar el contenido pero no puede detener el flujo de samples.
    _ultimo_callback = time.time()
    #  - CONTENIDO: hay audio de verdad. Sirve para saber si te escucha, NO para
    #    saber si el micro esta vivo: el ROG entrega ~0.00002 tanto sin ponerse
    #    como puesto y callado. No alcanza con != 0 (es 300x menos que el piso
    #    de un micro real, ~0.005), por eso se compara contra 0.002.
    if float(np.abs(indata).max()) > 0.002:
        _ultimo_audio_real = time.time()
        # Si el micro volvio a entregar audio de verdad, la evidencia de "grabacion
        # vacia" quedo vieja: limpiarla o dispararia un cambio sin motivo mas tarde.
        _captura_vacia = False
    if _grabando:
        _buf.append(indata.copy())
        return
    # _pausado va aca y no mas arriba a proposito: el chequeo de _grabando ya paso,
    # asi que F9 y los atajos siguen andando con la escucha pausada. Y el FLUJO y el
    # CONTENIDO se siguen marcando arriba, asi que el watchdog no se queda ciego.
    if not WAKE_ON or _pausado or time.time() < _mudo_hasta:
        _seg, _seg_activo = [], False
        return

    if _wake_porcupine:                      # motor dedicado (si algun dia esta)
        try:
            modo = escucha.procesar(indata)
        except Exception:
            return
        if modo:
            _disparar_wake(modo)
        return

    # Sin motor dedicado: juntamos fragmentos de voz y los revisa Whisper.
    ahora = time.time()
    rms = float(np.sqrt(np.mean(np.square(indata))))
    umbral = WAKE_UMBRAL_HABLANDO if _hablando else WAKE_UMBRAL
    if rms > umbral:
        if not _seg_activo:
            _seg, _seg_activo, _seg_t0 = [], True, ahora
        _seg.append(indata.copy())
        _seg_ultimo = ahora
    elif _seg_activo:
        _seg.append(indata.copy())
        if ahora - _seg_ultimo > WAKE_SILENCIO:          # se cerro el fragmento
            frames_seg, _seg, _seg_activo = list(_seg), [], False
            dur = sum(len(f) for f in frames_seg) / float(SR)
            if WAKE_MIN <= dur <= WAKE_MAX:
                threading.Thread(target=_revisar_wake,
                                 args=(frames_seg, time.time()), daemon=True).start()
    if _seg_activo and ahora - _seg_t0 > WAKE_MAX:       # musica/TV de fondo: descartar
        # Si esto pasa MIENTRAS ella habla, puede haberse llevado puesto tu
        # "Laura" (su propia voz mantiene el volumen arriba y el fragmento nunca
        # se cierra por silencio). Solo contamos: escribir en disco dentro del
        # callback del microfono seria una barbaridad, lo vuelca _revisar_wake.
        global _seg_largos
        if _hablando or _procesando:
            _seg_largos += 1
        _seg, _seg_activo = [], False


def _es_su_propio_eco(texto):
    """True si lo que captamos aparece en lo que el asistente esta diciendo ahora.

    Es LA defensa contra el auto-disparo: medido, su eco (0.068) se pisa con tu voz
    (0.05-0.12), asi que por volumen no se pueden separar. Comparar el texto si.
    Cualquier largo cuenta: si ella dijo esa palabra, no la tomamos como tuya."""
    if not _hablando or not _texto_hablando:
        return False
    n = re.sub(r"[^\w\s]", "", acciones._norm(texto)).strip()
    return bool(n) and n in re.sub(r"[^\w\s]", "", _texto_hablando)


def _revisar_wake(frames_seg, t_cierre=None):
    """Transcribe un fragmento corto y ve si dijiste la palabra clave (o 'basta')."""
    if _grabando:
        return
    t0 = time.time()
    # ⭐ Llamarla ENCIMA (mientras habla o mientras piensa con la musica de espera)
    # es el caso mas dificil que tiene el wake word: el fragmento trae SU voz
    # mezclada con la tuya. Cuando se descarta uno de esos, hoy no quedaba rastro
    # de por que, asi que "a veces no me escucha" no se podia diagnosticar. Ahora
    # cada descarte en ese estado queda anotado con hora en voz_eventos.log.
    encima = _hablando or _procesando
    try:
        audio = np.concatenate(frames_seg, axis=0).flatten().astype("float32")
        # Con musica/video en los PARLANTES, el micro genera fragmentos de ruido sin
        # parar y hacen COLA en el lock: cuando decias "Venus" esperaba 1.5-2s detras
        # del ruido. Si un fragmento espero demasiado, ya fue: descartarlo.
        if t_cierre and (time.time() - t_cierre) > 2.0:
            if encima:
                _evento(f"wake ENCIMA perdido: el fragmento espero "
                        f"{time.time() - t_cierre:.1f}s en la cola y se vencio")
            return
        with _wake_lock:                      # lock propio: no espera a la transcripcion de comandos
            if t_cierre and (time.time() - t_cierre) > 2.0:
                if encima:
                    _evento(f"wake ENCIMA perdido: se vencio esperando el turno "
                            f"({time.time() - t_cierre:.1f}s)")
                return                        # se vencio mientras esperaba el turno
            # vad_filter=True es CLAVE: sin el, con ruido o silencio Whisper ALUCINA y
            # escupe justo lo del initial_prompt ("Laura"/"Venus") -> se disparaba solo.
            segs, _ = modelo_wake.transcribe(audio, language="es", beam_size=1,
                                             condition_on_previous_text=False,
                                             vad_filter=True,
                                             initial_prompt="Laura. Venus.")
            segs = list(segs)
            texto = " ".join(s.text.strip() for s in segs).strip()
    except Exception as e:
        print("wake: error transcribiendo:", e, flush=True)
        return
    if not texto or not segs:
        return
    # Segunda defensa: Whisper nos dice cuanto cree que NO habia voz. Medido: voz real
    # de verdad ~0.01, ruido alucinado 0.65-0.80. Con 0.45 separamos comodo.
    no_voz = max(s.no_speech_prob for s in segs)
    if no_voz > WAKE_NO_VOZ_MAX:
        print(f"wake: descarto {texto!r} (no_speech={no_voz:.2f}, suena a ruido)", flush=True)
        # Encima de ella, este es el descarte que mas duele: si el fragmento trae
        # las dos voces mezcladas, Whisper sube el no_speech y tu llamado muere
        # como si fuera ruido. Si esto aparece con un texto que TIENE el nombre,
        # el umbral (WAKE_NO_VOZ_MAX) es el que hay que revisar, no el microfono.
        if encima and _WAKE_RX.search(acciones._norm(texto)):
            _evento(f"wake ENCIMA perdido por ruido: {texto!r} no_speech={no_voz:.2f} "
                    f"(umbral {WAKE_NO_VOZ_MAX})")
        return
    n = acciones._norm(texto)
    # Tercera defensa: si es EXACTAMENTE lo que esta diciendo, es su eco, no vos...
    # SALVO que sea una llamada PURA: el nombre pelado o un "basta/para" solo. Ella
    # dice esas palabras ADENTRO de frases (las lecturas nombran a Venus todo el
    # tiempo, y "para" esta en cualquier oracion); un fragmento que es SOLO eso sos
    # vos. Sin esta excepcion, mientras leia una respuesta que nombraba a Venus era
    # IMPOSIBLE callarla: tu "Venus" y tu "para" morian como eco (paso el 2026-08-11).
    # El costo asumido: si un corte de audio aisla justo el nombre de su propia voz,
    # se auto-interrumpe una vez y te dice "te escucho" — molesto pero recuperable,
    # que es mejor trato que "imposible de callar".
    if _es_su_propio_eco(texto) and not (_WAKE_PURO.match(n) or _PARAR.match(n)):
        if _WAKE_RX.search(n):
            _evento(f"wake ENCIMA perdido por eco: {texto!r} (lo tomo como su propia voz)")
        return
    if _hablando and _PARAR.match(n):         # "basta" / "callate" / "para" -> frenala
        print(f"stop por voz: {texto!r}", flush=True)
        _interrumpir(f"voz {texto!r}")
        return
    m = _WAKE_RX.search(n)
    if not m:
        return
    # Laura = SOLO Claude.  Venus = SOLO la computadora (no deriva a Claude).
    modo = "claude" if m.group(1) else "local"
    # El nombre SOLO despierta: lo que venga pegado se descarta. Un unico flujo,
    # siempre igual: nombre -> "Te escucho" -> recien ahi hablas.
    resto = n[m.end():].strip(" ,.:;-¿?!¡")
    print(f"wake word: {texto!r} -> {modo} (reconocido en {time.time()-t0:.2f}s)"
          + (f" (ignoro: {resto!r})" if resto else ""), flush=True)
    if encima:
        # La llamaste encima y te oyo: queda anotado con hora para poder comparar
        # contra las veces que NO te oyo (los "wake ENCIMA perdido" de arriba).
        global _seg_largos
        largos, _seg_largos = _seg_largos, 0
        _evento(f"wake ENCIMA oido: {texto!r} en {time.time() - t0:.2f}s"
                + (f"  (antes se habian tirado {largos} fragmentos por largos)" if largos else ""))
    _disparar_wake(modo)


def _disparar_wake(modo):
    """Dijiste la palabra clave: cortamos todo, decimos '¿Ey?' y RECIEN AHI grabamos."""
    global _seguidos
    _seguidos = 0                      # la nombraste: arranca una conversacion nueva
    print("wake word ->", modo, flush=True)
    _interrumpir(f"nombre ({modo})")
    # en un hilo aparte: nunca bloquear el callback del microfono
    threading.Thread(target=_abrir_micro_tras_ey, args=(modo, _epoca), daemon=True).start()


def _abrir_micro_tras_ey(modo, ep):
    """Dice 'Te escucho' y RECIEN AHI abre el micro: esa es tu señal para hablar."""
    global _grabando, _buf, _modo
    _silenciar_hasta(_EY_DUR + 0.4)    # que el propio saludo no dispare la deteccion
    _sonar_ey()
    # Margen MINIMO. Con +0.35 quedaba una zona muerta justo cuando arrancas a hablar y
    # se perdian las palabras cortas ("2"). Del eco que se cuele se encarga _ECO_SALUDO.
    time.sleep(_EY_DUR + 0.10)
    if not _vigente(ep) or _grabando:
        return                         # te adelantaste con una tecla
    _buf = []
    _modo = modo
    _grabando = True
    print("te escucho -> micro abierto", flush=True)
    # sordo=0: el saludo ya termino, asi que escuchamos desde el primer instante
    threading.Thread(target=_cerrar_por_silencio, args=(ep, None, 0.0), daemon=True).start()


def _vistazo(frames_seg):
    """Transcripcion rapida (modelo chico) para ver si YA dijiste un comando conocido."""
    try:
        audio = np.concatenate(frames_seg, axis=0).flatten().astype("float32")
        if len(audio) < SR * MIN_SEG:
            return ""
        with _wake_lock:
            segs, _ = modelo_wake.transcribe(audio, language="es", beam_size=1,
                                             condition_on_previous_text=False,
                                             initial_prompt=_VOCAB)
            t = " ".join(s.text.strip() for s in segs).strip()
        return _ECO_SALUDO.sub("", t).strip()
    except Exception as e:
        print("vistazo fallo:", e, flush=True)
        return ""


def _cerrar_por_silencio(ep, espera_inicio=None, sordo=None, aviso_nada="nada"):
    """Sin tecla que soltar: cierra la grabacion cuando dejas de hablar."""
    global _grabando
    t0 = ultimo_sonido = time.time()
    hablo = False
    dictando = (_modo == "dictado")       # dictar necesita mucha mas paciencia que un comando
    corte = SIL_CORTE_DICTADO if dictando else SIL_CORTE
    tope = MAX_DICTADO if dictando else (MAX_CLAUDE if _modo == "claude" else MAX_MANOS_LIBRES)
    if espera_inicio is None:
        espera_inicio = ESPERA_INICIO_DICTADO if dictando else ESPERA_INICIO
    sordo_hasta = t0 + (_EY_DUR + 0.15 if sordo is None else sordo)   # el eco de los parlantes no cuenta
    ultimo_sonido = sordo_hasta
    rms_max = 0.0
    vistazo_hecho = False
    vistos = 0
    while _grabando and _vigente(ep):
        time.sleep(0.08)
        ahora = time.time()
        # Mirar TODOS los bloques nuevos, no solo el ultimo: llegan cada ~32ms y
        # sondeamos cada 80ms, asi que mirando _buf[-1] se perdian 2 de cada 3
        # (una palabra corta como "2" podia pasar desapercibida).
        nuevos, vistos = _buf[vistos:], len(_buf)
        if nuevos and ahora > sordo_hasta:
            rms = max(float(np.sqrt(np.mean(np.square(b)))) for b in nuevos)
            rms_max = max(rms_max, rms)
            if rms > SIL_UMBRAL:
                ultimo_sonido = ahora
                hablo = True
        if ahora - t0 > tope:
            break
        # Comando conocido ("escritorio 2", "borra", "subi el volumen"): ejecutarlo YA,
        # sin esperar la pausa larga. Un solo intento por turno, y solo en modo comandos.
        if (hablo and not vistazo_hecho and not dictando and _modo == "local"
                and ahora - ultimo_sonido > CORTE_RAPIDO):
            vistazo_hecho = True
            texto_v = _vistazo(list(_buf))
            if texto_v:
                resp, ok = acciones.ejecutar(texto_v)     # si matchea, YA lo ejecuto
                if ok:
                    print(f"comando rapido: {texto_v!r} -> {resp}", flush=True)
                    _grabando = False
                    if _vigente(ep):
                        hablar(resp, ep)
                    return
        if hablo and ahora - ultimo_sonido > corte:
            break
        # OJO: la espera cuenta desde que EMPEZAMOS a escuchar (no desde el saludo),
        # si no el tiempo del "Te escucho" te comia la ventana para arrancar.
        if not hablo and ahora > sordo_hasta + espera_inicio:
            break
    if not _grabando or not _vigente(ep):
        return                          # ya te adelantaste con una tecla
    _grabando = False
    frames = list(_buf)
    dur = time.time() - t0
    print(f"micro cerrado: {dur:.1f}s, hablaste={hablo}, "
          f"volumen_max={rms_max:.4f} (umbral {SIL_UMBRAL})", flush=True)
    if frames and rms_max < 0.0005:
        # VERDAD DE CAMPO: dijiste el nombre (abriste el micro) y llego SILENCIO
        # DIGITAL. Sabemos que TENIA que haber audio, asi que esto no puede dar
        # falso positivo -> fallback ya.
        global _captura_vacia
        _captura_vacia = True
        print("grabacion en silencio digital -> fuerzo cambio de micro", flush=True)
    if not hablo or not frames:
        if aviso_nada == "nada":
            _sonar(_WAV_NADA, _NADA_OK)      # "No te escuché": no te quedes esperando respuesta
        elif aviso_nada == "cierro":
            _sonar(_WAV_CIERRO, _CIERRO_OK)  # "Cierro": termino la charla con Laura
        return
    # Laura NO avisa nada al captar lo que dijiste: la musica de espera ya dice que
    # esta trabajando, asi que el "Entiendo." era un sonido de mas en cada turno
    # (el usuario lo pidio sacar el 2026-08-10). Encima winsound reproduce de a uno,
    # asi que la musica se lo cortaba a mitad de palabra.
    # Venus SI sigue diciendo "Ok": eso el usuario lo quiere asi, no tocarlo.
    if _modo != "claude":
        _sonar(_WAV_OK, _OK_OK)
    threading.Thread(target=_procesar, args=(frames, _modo, ep, True), daemon=True).start()


def _seguir_escuchando(modo, ep):
    """Despues de que Laura contesta deja el micro abierto: conversas sin nombrarla."""
    global _grabando, _buf, _modo, _seguidos
    if modo != "claude":                 # solo Laura conversa; Venus (comandos) no
        return
    if not SEGUIMIENTO or _grabando or not _vigente(ep):
        return
    if _seguidos >= MAX_SEGUIDOS:        # cortamos la cadena: volve a nombrarla
        print("fin de la conversacion (tope de idas y vueltas)", flush=True)
        return
    _seguidos += 1
    print(f"sigo escuchando... (turno {_seguidos}/{MAX_SEGUIDOS})", flush=True)
    _buf = []
    _modo = modo
    _grabando = True
    # Si no seguis la charla avisa "Cierro" (corto), para que sepas que dejo de escuchar.
    threading.Thread(target=_cerrar_por_silencio,
                     args=(ep, SEGUIMIENTO, 0.35, "cierro"), daemon=True).start()


# Estos tres van ACA ARRIBA, no junto al watchdog: _abrir_stream_inicial() se
# ejecuta a nivel de modulo unas lineas mas abajo, y si _abrir se define despues
# revienta con "name '_abrir' is not defined" y el asistente no arranca.
def _abrir(dispositivo, extra="auto"):
    if extra == "auto":
        extra = _extra_de(dispositivo)
    s = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                       callback=_cb, device=dispositivo, extra_settings=extra)
    s.start()
    return s


def _cerrar(s):
    try:
        if s is not None:
            s.stop(); s.close()
    except Exception:
        pass


def _refrescar_dispositivos():
    """PortAudio CONGELA la lista de dispositivos cuando arranca el proceso. Tras
    suspender la maquina o reenchufar el dongle sigue viendo los de antes, que ya
    no existen. Reiniciarlo es el mismo truco que usa /micros en panel.py."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception as e:
        print("micro: no pude refrescar la lista de dispositivos:", e, flush=True)


def _abrir_stream_inicial():
    """Prueba los caminos de audio del micro elegido, del mejor al peor, y solo
    como ultimo recurso el predeterminado de Windows (que puede ser OTRO micro)."""
    for idx, extra, api in _candidatos_micro() + [(None, None, "predeterminado")]:
        try:
            s = _abrir(idx, extra)
            print(f"micro: [{idx}] via {api} a {SR} Hz", flush=True)
            _evento(f"micro abierto: [{idx}] via {api}")
            return s
        except Exception as e:
            print(f"micro: no pude abrir [{idx}] via {api} ({e})", flush=True)
    raise RuntimeError("no pude abrir ningun microfono")


def _abrir_stream_al_arrancar():
    """El bloqueo de privacidad no apaga a Laura: solo le saca el microfono.

    WhatsApp, Telegram y el chat del panel usan el buzon que atiende este mismo
    proceso, asi que deben seguir funcionando aunque Martin haya bloqueado el
    microfono desde el panel. El watchdog queda vivo y lo recupera cuando se
    levanta la bandera.
    """
    if MIC_BLOQUEADO.exists():
        print("micro: bloqueado a proposito; Laura arranca sin escucha local",
              flush=True)
        _evento("microfono bloqueado al arrancar; canales escritos siguen activos")
        return None
    return _abrir_stream_inicial()


_stream = _abrir_stream_al_arrancar()

# --- Watchdog del microfono ---------------------------------------------------
# Un inalambrico APAGADO (o en el estuche) sigue figurando en Windows pero entrega
# SILENCIO DIGITAL (0.0000 exacto, ni ruido de fondo). Si eso pasa 15s:
#   1) nos pasamos solos al microfono predeterminado de Windows y avisamos, y
#   2) desde ahi sondeamos el configurado cada ~5s: cuando revive (lo prendieron),
#      VOLVEMOS solos a el y avisamos.
_ultimo_audio_real = time.time()   # ultima vez que llego audio con CONTENIDO real
_ultimo_callback = time.time()     # ultima vez que llego un callback (FLUJO de samples)
_en_fallback = False
_ultimo_cambio = 0.0               # cuando cambiamos de micro por ultima vez
_captura_vacia = False             # una grabacion CON verdad de campo volvio vacia
_mic_bloqueado_aviso = False       # ya avisamos que el bloqueo del panel esta activo

# Verificado en Gear Link el 2026-08-10: el ROG tiene cancelacion de ruido por IA
# que NO se puede desactivar (el Noise Gate y Perfect Voice ya estaban en OFF y
# igual entrega ~0.00002). Entrega ese mismo casi-cero cuando NO te lo pusiste y
# cuando lo tenes puesto pero estas callado. O sea: el rms NO puede distinguir
# esos dos estados, y ningun umbral lo va a arreglar porque la informacion no
# esta en el dato. Por eso el watchdog ya NO usa "silencio pasivo" como evidencia:
# eso causaba cambios de micro en plena sesion (visto en voz.log el 2026-08-10).
#
# Sin un solo callback en este tiempo, el dispositivo se fue DE VERDAD (lo
# desenchufaste, se apago, PortAudio lo perdio). Es el unico criterio pasivo
# confiable: la cancelacion de ruido afecta el CONTENIDO, no el FLUJO de samples.
FLUJO_MUERTO_SEG = 8.0
# "Refractory period" (asi lo llama wyoming-satellite en --wake-refractory-seconds):
# despues de cambiar de micro, no volver a cambiar por este rato. Sin esto el
# watchdog rebota entre dos microfonos mientras estas trabajando.
REFRACTARIO_SEG = 60.0
# Si tras reabrir el micro el problema vuelve dentro de este rato, reabrir no
# alcanzo y recien ahi se salta a otro microfono. Evita perder tus auriculares
# por un stream que se habia quedado dormido y se arreglaba solo reabriendolo.
REINTENTO_SEG = 90.0
_ultimo_reabierto = 0.0


def _sondear(dispositivo, seg=0.8):
    """Abre el micro un instante: True si entrega audio DE VERDAD (no el ~0.00002
    del gate de un inalambrico sin ponerse)."""
    vivo = [False]
    def cb(indata, frames, t, status):
        if float(np.abs(indata).max()) > 0.002:
            vivo[0] = True
    try:
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                            callback=cb, device=dispositivo,
                            extra_settings=_extra_de(dispositivo)):
            time.sleep(seg)
    except Exception:
        return False
    return vivo[0]


def _asegurar_algun_stream():
    """Ultimo recurso: abrir CUALQUIER microfono que ande. La regla es que el
    asistente nunca puede quedarse sin ninguno: el proceso queda vivo, el panel lo
    muestra en verde, y esta sordo sin que nadie se entere."""
    global _stream
    if _stream is not None:
        return True
    for idx, extra, api in _candidatos_micro() + [(None, None, "predeterminado")]:
        try:
            _stream = _abrir(idx, extra)
            print(f"micro: recuperado con [{idx}] via {api}", flush=True)
            _evento(f"micro RECUPERADO con [{idx}] via {api}")
            return True
        except Exception:
            continue
    # Ni el configurado ni el predeterminado: probar cualquier entrada que abra.
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] <= 0:
                continue
            try:
                _stream = _abrir(i)
                print(f"micro: recuperado con [{i}] {d['name']}", flush=True)
                _evento(f"micro RECUPERADO con [{i}] {d['name']}")
                return True
            except Exception:
                continue
    except Exception:
        pass
    print("micro: NO pude abrir ningun microfono", flush=True)
    _evento("micro: NO pude abrir ningun microfono")
    return False


def _cambiar_stream(dispositivo, extra="auto"):
    """Cambia de microfono SIN quedarse nunca sin ninguno.

    El orden importa y antes estaba al revés: cerraba el stream que ANDABA y
    despues intentaba abrir el nuevo. El 2026-08-11, tras suspender la maquina y
    reenchufar el dongle, el nuevo no abrio (AUDCLNT_E_DEVICE_INVALIDATED) y quedo
    sin ningun microfono: proceso vivo, panel en verde, sordo y sin avisar.
    Es colgar el telefono que funciona antes de ver si el otro tiene tono.
    """
    global _stream
    viejo = _stream
    # 1) AGARRAR ANTES DE SOLTAR. Si el nuevo no abre, no perdimos nada.
    try:
        _stream = _abrir(dispositivo, extra)
        _cerrar(viejo)
        return
    except Exception as e1:
        primera = e1
    # 2) Algunos drivers no dejan dos streams sobre el MISMO dispositivo, asi que
    #    para ese caso si hay que soltar antes. Si esto falla, se recupera en (3).
    _cerrar(viejo)
    _stream = None
    try:
        _stream = _abrir(dispositivo, extra)
        return
    except Exception as e2:
        # Python borra la variable del "except" al salir del bloque: guardarla
        # aparte, o el raise de abajo muere con "cannot access local variable".
        segunda = e2
        print(f"micro: no pude abrir [{dispositivo}]: {e2} "
              f"(agarrando-antes-de-soltar dio: {primera})", flush=True)
    # 3) Quedamos sin nada: recuperar con lo que sea ANTES de propagar el error.
    if not _asegurar_algun_stream():
        raise RuntimeError(f"no pude abrir ningun microfono ({segunda})")
    raise RuntimeError(f"no pude usar [{dispositivo}] ({segunda}), quedé con otro")


def _reabrir_configurado():
    """Reabre el micro elegido probando sus caminos de audio. Devuelve (idx, api)
    o (None, None). Es el PRIMER escalon del watchdog: si el stream quedo muerto
    entregando ceros, esto lo revive y te quedas en TU microfono."""
    for idx, extra, api in _candidatos_micro():
        try:
            _cambiar_stream(idx, extra)
            return idx, api
        except Exception as e:
            print(f"watchdog: no pude reabrir [{idx}] via {api} ({e})", flush=True)
    return None, None


def _buscar_micro_vivo(evitar=None):
    """Sondea los microfonos disponibles y devuelve (indice, nombre) del primero
    que entregue audio de verdad. OJO: el 'predeterminado de Windows' puede ser el
    MISMO inalambrico muerto, por eso se prueba de verdad en vez de confiar."""
    vistos = set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0 or i == evitar:
            continue
        nm = (d["name"] or "").strip()
        low = nm.lower()
        if not nm or nm in vistos:
            continue
        if any(j in low for j in ("mapper", "primary sound", "speaker", "@system32",
                                  "wave", "input (")):
            continue
        vistos.add(nm)
        if _sondear(i, seg=0.6):
            return i, nm
    return None, None


def _watchdog_micro():
    """Cambia de microfono SOLO con evidencia confiable. Dos disparadores:

      1) FLUJO CORTADO: no llega un solo callback hace FLUJO_MUERTO_SEG. El
         dispositivo se fue de verdad.
      2) VERDAD DE CAMPO: una grabacion que TENIA que traer audio (apretaste una
         tecla o dijiste el nombre) volvio en silencio digital.

    Lo que ya NO dispara nada es el silencio pasivo: con la cancelacion de ruido
    del ROG, estar callado y no tener el micro puesto dan el mismo valor, asi que
    ese dato no distingue nada y solo causaba cambios de micro en plena sesion.
    """
    global _ultimo_audio_real, _en_fallback, _ultimo_cambio, _captura_vacia, _ultimo_reabierto
    global _stream, _ultimo_callback, _mic_bloqueado_aviso
    dispositivo_config = _device()          # el elegido en el panel (None = predeterminado)
    anterior = time.time()
    while True:
        time.sleep(5)
        ahora = time.time()

        # --- La maquina volvio de suspenderse ---------------------------------
        # El reloj salta muchisimo mas que los 5 s del sleep. Al suspender, Windows
        # desarma las conexiones de audio y al despertar arma OTRAS con el mismo
        # nombre: la que teniamos agarrada ya no existe. Antes esto se descubria
        # recien cuando dejaba de llegar audio, y para entonces ya se habia hecho
        # lio. Ahora se rearma de una, y refrescando la lista de dispositivos
        # (PortAudio la congela al arrancar y sigue viendo los de antes).
        salto = ahora - anterior
        anterior = ahora

        # --- Bloqueo A PROPOSITO desde el panel (interruptor de privacidad) ---
        # Con el maestro de Windows apagado ningun microfono puede abrirse:
        # pelear es inutil y ruidoso (el 2026-08-13 este watchdog quedo ciclando
        # errores -9996 y "recupero" el PC Speaker como si fuera un micro).
        # Bandera puesta = esperar callado. Al levantarse, rearmar todo igual
        # que al volver de una suspension.
        if MIC_BLOQUEADO.exists():
            if not _mic_bloqueado_aviso:
                _mic_bloqueado_aviso = True
                print("micro: bloqueado a proposito desde el panel, watchdog en espera",
                      flush=True)
                _evento("microfono bloqueado desde el panel (privacidad)")
            continue
        if _mic_bloqueado_aviso:
            _mic_bloqueado_aviso = False
            print("micro: bloqueo levantado, rearmo el microfono", flush=True)
            _cerrar(_stream)
            _stream = None
            _refrescar_dispositivos()
            dispositivo_config = _device()
            _asegurar_algun_stream()
            _ultimo_audio_real = _ultimo_callback = _ultimo_cambio = time.time()
            _captura_vacia = False
            _en_fallback = False
            _evento("microfono desbloqueado, rearmado")
            continue

        if salto > 60:
            print(f"micro: la maquina estuvo suspendida ({salto / 60:.0f} min), "
                  f"rearmo el microfono", flush=True)
            _evento(f"suspension detectada ({salto / 60:.0f} min), rearmo el microfono")
            _cerrar(_stream)
            _stream = None
            _refrescar_dispositivos()
            dispositivo_config = _device()      # puede haber cambiado de indice
            _asegurar_algun_stream()
            # Poner en hora los dos relojes: si no, el chequeo de "flujo cortado"
            # dispararia en el acto por los minutos que estuvo suspendida.
            _ultimo_audio_real = _ultimo_callback = _ultimo_cambio = time.time()
            _captura_vacia = False
            _en_fallback = False
            continue

        # --- Red de seguridad: quedarse sin microfono es inaceptable ----------
        if _stream is None:
            print("micro: no hay ningun stream abierto, recupero", flush=True)
            _asegurar_algun_stream()
            _ultimo_cambio = time.time()
            continue

        if _grabando or _hablando:          # no manosear el audio en medio de un uso
            continue
        if not _en_fallback:
            sin_flujo = ahora - _ultimo_callback
            if _captura_vacia:
                motivo = "una grabacion que tenia que traer audio volvio vacia"
            elif sin_flujo > FLUJO_MUERTO_SEG:
                motivo = f"no llega un callback hace {sin_flujo:.0f}s"
            else:
                continue
            if (ahora - _ultimo_cambio) < REFRACTARIO_SEG:
                continue                    # refractario: recien cambiamos, esperar
            # PRIMER ESCALON: reabrir TU microfono, no cambiarte de microfono.
            # Un stream de captura puede quedar muerto entregando ceros (pasa con
            # DirectSound cuando el dispositivo se va y vuelve). Reabrirlo lo revive
            # y te quedas en tus auriculares, que es lo que querias. Solo si el
            # problema vuelve dentro de REINTENTO_SEG se acepta que el micro esta
            # realmente mal y se salta a otro.
            if (ahora - _ultimo_reabierto) > REINTENTO_SEG:
                print(f"MICRO SIN AUDIO ({motivo}) -> reabro el mismo micro", flush=True)
                idx_r, api_r = _reabrir_configurado()
                if idx_r is not None:
                    _ultimo_reabierto = time.time()
                    _captura_vacia = False
                    _ultimo_audio_real = time.time()
                    print(f"watchdog: micro reabierto [{idx_r}] via {api_r}", flush=True)
                    _evento(f"micro REABIERTO [{idx_r}] via {api_r} por: {motivo}")
                    continue                # darle una chance antes de cambiar
            # SEGUNDO ESCALON: reabrir no alcanzo, buscar otro microfono.
            print(f"MICRO MUERTO ({motivo}) | reabrirlo no alcanzo | contenido hace "
                  f"{ahora - _ultimo_audio_real:.0f}s, flujo hace {sin_flujo:.1f}s "
                  f"-> busco uno vivo...", flush=True)
            idx, nm = _buscar_micro_vivo(evitar=dispositivo_config)
            if idx is None:
                print("watchdog: ningun micro vivo, reintento en 5s", flush=True)
                continue
            try:
                _cambiar_stream(idx)
                _ultimo_audio_real = _ultimo_cambio = time.time()
                _captura_vacia = False
                _en_fallback = True
                print(f"watchdog: cambie al micro vivo [{idx}] {nm}", flush=True)
                hablar("Tu microfono no responde. Paso a usar el de la computadora.")
            except Exception as e:
                print("watchdog: no pude cambiar de micro:", e, flush=True)
        else:
            if (ahora - _ultimo_cambio) < REFRACTARIO_SEG:
                continue                    # refractario tambien para volver
            if _sondear(dispositivo_config):
                print("MICRO RECUPERADO: vuelvo al configurado", flush=True)
                try:
                    _cambiar_stream(dispositivo_config)
                    _ultimo_audio_real = _ultimo_cambio = time.time()
                    _captura_vacia = False
                    _en_fallback = False
                    hablar("Tu microfono volvio. Lo uso de nuevo.")
                except Exception as e:
                    print("watchdog: no pude volver al micro configurado:", e, flush=True)


threading.Thread(target=_watchdog_micro, daemon=True).start()


# Detecta pedidos sobre la pantalla -> vision directa (sin depender del ruteo del LLM)
_PANTALLA = re.compile(
    r"\b(pantalla|monitor)\b"
    r"|que (ves|veo)\b"
    r"|que estas viendo|que estoy viendo|estas viendo|estoy viendo"
    r"|lo que (estoy |estas )?(veo|viendo|ves)"
    r"|mira (esto|aca|esta|el|lo que)"
    r"|fijate"
    r"|lee(me)? (esto|el error|la|lo que|aca)"
    r"|que (es|dice|significa|hay) (esto|aca|ahi)"
    r"|describi (esto|la|lo|aca)"
)


def _es_pantalla(texto):
    return bool(_PANTALLA.search(acciones._norm(texto)))


def _monitor_pedido(texto):
    m = re.search(r"monitor\s*(\d+)", acciones._norm(texto))
    return int(m.group(1)) if m else None


# --- Dictar a UNA sesion de Claude Code ("Venus, escribi en la sesion del disco...") --
# La perilla de destino es escribir_en.json: la gira este comando O el selector del
# panel, y los dos ven lo mismo. El texto se PEGA pero nunca se manda: el Enter es tuyo.
_ES_ESCRIBIR_SESION = re.compile(
    r"^\W*escrib\w*\s+(?:me\s+|le\s+)?(?:a|en)\s+(?:la\s+)?sesi[oó]n\b[\s,.:]*(.*)$",
    re.IGNORECASE)

# "Venus, enter" -> aprieta Enter DONDE ESTE EL CURSOR, sin tocar ninguna ventana.
# Es para cuando ya estas escribiendo ahi (dictaste, revisaste en pantalla) y solo
# falta la tecla. NO va a la sesion elegida a proposito: mandaria el foco a otra
# ventana justo cuando estas trabajando en esta. Estricto: la frase tiene que SER
# eso ("enter", "dale enter", "apreta enter") — "el enter del teclado" no manda nada.
_ES_ENTER = re.compile(
    r"^\W*(?:(?:dale|apret[aá]\w*|mand[aá]\w*|dal[eé])\s+)?enter\W*$", re.IGNORECASE)


def _apretar_enter(ep=None):
    """Enter en la ventana activa, la que estes usando en este momento."""
    keyboard.send("enter")
    print("dictado: [ENTER en la ventana activa]", flush=True)
    hablar("Mandado.", ep)


# "Venus, selecciona la sesion del disco" -> solo gira la perilla, no escribe nada.
# Exige la palabra "sesion": "selecciona todo" tiene que seguir cayendo en acciones
# (que ahi es Ctrl+A). Y se intercepta ANTES de acciones.ejecutar por lo mismo.
_ES_SELECCIONAR_SESION = re.compile(
    r"^\W*(?:seleccion\w+|eleg[ií]\w*|cambi[aá]\w*(?:\s+a)?|pas[aá]\w*(?:\s+a)?)\s+"
    r"(?:la\s+)?sesi[oó]n\b[\s,.:]*(.*)$", re.IGNORECASE)


def _seleccionar_sesion(frase, ep=None):
    """Cambia el destino del dictado. La perilla es la misma que la del panel."""
    from app.voz import seguir
    frase = frase.strip(" ,.:")
    if not frase:
        actual = _leer_destino()
        if actual:
            hablar(f"Ahora escribo en {_nombre_corto(actual['nombre'])}. "
                   "Para cambiar, decime cual.", ep)
        else:
            hablar("Decime cual: por ejemplo, selecciona la sesion del disco.", ep)
        return
    s = seguir.buscar_sesion(frase)
    if not s:
        hablar(f"No encontre una sola sesion abierta que suene a {frase}. "
               "Proba con otras palabras o miralas en el panel.", ep)
        return
    _guardar_destino(s)
    print(f"destino de escritura: {s['nombre']}", flush=True)
    hablar(f"Listo, escribo en {_nombre_corto(s['nombre'])}.", ep)


def _leer_destino():
    try:
        d = json.loads(ESCRIBIR_EN.read_text(encoding="utf-8"))
        return d if d.get("nombre") else None
    except Exception:
        return None


def _guardar_destino(s):
    try:
        ESCRIBIR_EN.write_text(json.dumps(
            {"id": s.get("id"), "nombre": s.get("nombre"), "cwd": s.get("cwd"),
             "jsonl": s.get("jsonl")}, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print("no pude guardar el destino de escritura:", e, flush=True)


def _nombre_corto(nombre, tope=6):
    return " ".join(str(nombre).split()[:tope])


# "hola como estas ENTER" -> pega Y manda. La palabra dicha al final es tu firma:
# no es Venus mandando sola, sos vos autorizando el envio en la misma frase. SOLO
# "enter" (no "entre", que es castellano comun; no "mandalo", que aparece en frases
# normales). Y "enter" solo, sin texto adelante, no manda nada.
# Antes del "enter" solo se traga espacios y una coma: el "?" o el "!" que Whisper
# pone antes ("¿como estas? Enter.") son PARTE de la frase y tienen que quedar.
_FINAL_ENTER = re.compile(r"[\s,]*\benter\b\W*$", re.IGNORECASE)


def _sacar_enter_final(texto):
    """(texto_sin_el_enter, hay_que_mandar). El 'enter' del final se saca del texto."""
    m = _FINAL_ENTER.search(texto or "")
    if m and texto[:m.start()].strip():
        return texto[:m.start()].strip(), True
    return texto, False


def _pegar_y_mandar(texto, mandar):
    _pegar(texto)
    if mandar:
        time.sleep(0.15)                 # que el pegado termine de asentarse
        keyboard.send("enter")


def _enfocar_sesion(s):
    """Trae al frente la ventana de VS Code de esa sesion. (True/False, titulo_activo).

    La ventana lleva el titulo de la conversacion adentro de su propio titulo
    ("Investigar y clasificar... - wpp-transcriptor - Visual Studio Code"), asi que se
    puntua por palabras del titulo + nombre del proyecto. Y DESPUES de activar se
    VERIFICA cual quedo al frente: pegar en la ventana equivocada es peor que no pegar.
    """
    from app.voz import seguir
    import pygetwindow as gw
    objetivo = seguir._palabras(s.get("nombre", ""))
    proyecto = seguir._palabras(Path(s.get("cwd", "")).name)
    candidatas = []
    for w in gw.getAllWindows():
        titulo = w.title or ""
        if "visual studio code" not in titulo.lower():
            continue
        pal = seguir._palabras(titulo)
        puntos = len(objetivo & pal) + 2 * len(proyecto & pal)
        if puntos:
            candidatas.append((puntos, w))
    if not candidatas:
        return False, None
    candidatas.sort(key=lambda x: -x[0])
    ventana = candidatas[0][1]
    try:
        if ventana.isMinimized:
            ventana.restore()
    except Exception:
        pass

    def _es_la_buscada():
        try:
            activa = gw.getActiveWindow()
        except Exception:
            return False, ""
        titulo = (activa.title if activa else "") or ""
        pal = seguir._palabras(titulo)
        return bool((objetivo & pal) or (proyecto and proyecto <= pal)), titulo

    # Windows le NIEGA el foco a un proceso de fondo (proteccion anti-secuestro): el
    # primer intento real termino con la ventana asomada pero el foco en Chrome, y un
    # error de coleccion: "Error code 0 - The operation completed successfully". El
    # destrabe clasico es inyectar una tecla (Alt) justo antes: para Windows, quien
    # acaba de mandar input tiene permiso de usuario. Venus inyecta teclas todo el
    # tiempo, asi que es su derecho. Tres intentos, verificando con paciencia.
    import win32gui
    titulo_activo = ""
    for intento in range(3):
        try:
            if intento > 0:
                keyboard.press_and_release("alt")
                time.sleep(0.05)
            win32gui.ShowWindow(ventana._hWnd, 9)          # SW_RESTORE
            win32gui.SetForegroundWindow(ventana._hWnd)    # si esta en otro escritorio, te lleva
        except Exception as e:
            print(f"activar ventana (intento {intento + 1}): {e}", flush=True)
        fin = time.time() + 1.2                            # el foco tarda en viajar
        while time.time() < fin:
            ok, titulo_activo = _es_la_buscada()
            if ok:
                return True, titulo_activo
            time.sleep(0.15)
    return False, titulo_activo


def _enfocar_cajita():
    """Foco a la cajita de Claude DENTRO de la ventana ya traida al frente.

    Enfocar la ventana no alcanza: el foco interno de VS Code queda donde estaba
    (editor, terminal, scrollback) y el Ctrl+V cae ahi — paso el 2026-08-11, tres
    dictados que "anduvieron" y no aparecieron nunca. El atajo TIENE que ser con
    tecla de funcion: el oficial (ctrl+escape) lo intercepta Windows y abre el menu
    Inicio (el dictado de prueba termino buscandose en Bing), y ctrl+alt+8 escribia
    el caracter "¾" cuando el foco YA estaba en la cajita (la webview se come la
    tecla y AltGr+8 es ¾ — cada dictado llegaba con su ¾ de regalo). F10 no produce
    caracter nunca. El atajo vive en el keybindings.json de VS Code
    (ctrl+alt+f10 -> claude-vscode.focus): si se borra de ahi, esto vuelve a fallar.
    """
    keyboard.send("ctrl+alt+f10")
    time.sleep(0.4)


def _escribir_en_sesion(resto, ep=None):
    """Resuelve destino + texto de "escribi en la sesion [X][: texto]" y lo ejecuta."""
    from app.voz import seguir
    frase_destino, texto = resto, ""
    for sep in (":", ","):               # "en la sesion del disco: reviza el panel"
        if sep in resto:
            frase_destino, texto = resto.split(sep, 1)
            break
    frase_destino = frase_destino.strip(" ,.:")
    texto = texto.strip()

    if frase_destino:
        s = seguir.buscar_sesion(frase_destino)
        if not s:
            hablar(f"No encontre una sola sesion abierta que suene a {frase_destino}. "
                   "Proba con otras palabras o elegila en el panel.", ep)
            return
        _guardar_destino(s)              # la voz giro la perilla: el panel lo va a ver
        print(f"destino de escritura: {s['nombre']}", flush=True)
    else:
        s = _leer_destino()
        if not s:
            hablar("No hay ninguna sesion elegida para escribir. "
                   "Decime en cual, o elegila en el panel.", ep)
            return

    ok, titulo_activo = _enfocar_sesion(s)
    if not ok:
        hablar(f"No pude traer al frente la sesion {_nombre_corto(s['nombre'])}. "
               "No escribi nada.", ep)
        print(f"escritura ABORTADA: quedo al frente {titulo_activo!r}", flush=True)
        return
    _enfocar_cajita()
    if texto:
        texto, mandar = _sacar_enter_final(texto)
        print(f"dictado: [a {_nombre_corto(s['nombre'])}] {texto}"
              + ("  [ENTER]" if mandar else ""), flush=True)
        _pegar_y_mandar(texto, mandar)
        hablar("Listo, mandado." if mandar else "Listo, lo escribi. Mandalo vos.", ep)
    else:
        # Sin texto en la misma frase: la ventana correcta ya quedo al frente, asi que
        # el dictado comun de siempre pega justo donde tiene que pegar.
        _abrir_micro_tras_ey("dictado", ep)


# Transformar el texto SELECCIONADO (corregir/traducir/mejorar/reformular/tono)
_TRANSFORMAR = re.compile(
    r"(corrig|correg|mejor|reformul|parafrase|reescrib|resum).{0,25}(esto|el texto|la seleccion|lo que seleccion|seleccionad|lo\b)"
    r"|(traduc|convert|pas[aá]lo|pas[aá] esto).{0,30}(ingles|espanol|castellano|portugues|frances|italiano|aleman)"
    r"|(hacelo|hazlo|hacer|hace|ponelo|ponlo|ponerlo|dejalo|volvelo|hacela?).{0,25}mas ?(formal|corto|largo|simple|profesional|claro|amable|serio|breve)"
)


def _es_transformacion(texto):
    t = acciones._norm(texto)
    if "pagina" in t or " web" in t:
        return False
    return bool(_TRANSFORMAR.search(t))


def _copiar_seleccion():
    """Copia lo que tengas seleccionado. Devuelve (texto, portapapeles_previo)."""
    try:
        prev = pyperclip.paste()
    except Exception:
        prev = ""
    try:
        pyperclip.copy("__sel_vacia__")     # centinela: distingue "sin seleccion" de "copio vacio"
        keyboard.send("ctrl+c")
        time.sleep(0.18)
        sel = pyperclip.paste()
    except Exception:
        sel = ""
    if not sel.strip() or sel == "__sel_vacia__":
        sel = ""
    return sel, prev


def _restaurar_portapapeles(prev):
    try:
        pyperclip.copy(prev)
    except Exception:
        pass


# "Venus, leeme" -> lee EN VOZ ALTA lo que tengas seleccionado
# "leeme" sale mal seguido (Whisper escribio "Dejeme"): aceptamos las variantes.
# "dejame" NO se incluye a proposito: es una frase real en rioplatense.
_ES_LEER = re.compile(r"^\W*(?:lee\w*|leer|leme|le\s+me|dejeme|lleame|lieme)\b")
MAX_LECTURA = 3000        # tope de caracteres (Piper tarda y no querés 10 minutos de audio)


def _leer_seleccion(ep=None):
    sel, prev = _copiar_seleccion()
    _restaurar_portapapeles(prev)           # no le robamos el portapapeles al usuario
    if not sel:
        return "No hay texto seleccionado."
    sel = re.sub(r"\s+", " ", sel).strip()
    if len(sel) > MAX_LECTURA:
        sel = sel[:MAX_LECTURA].rsplit(" ", 1)[0] + ". Corto acá, era muy largo."
    print(f"leyendo seleccion ({len(sel)} caracteres)", flush=True)
    return sel


def _transformar_seleccion(instruccion):
    sel, prev = _copiar_seleccion()
    if not sel:
        _restaurar_portapapeles(prev)
        return "No hay texto seleccionado."
    res = cerebro.transformar_texto(instruccion, sel)
    if not res:
        _restaurar_portapapeles(prev)
        return "No pude transformar el texto."
    pyperclip.copy(res)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.25)
    _restaurar_portapapeles(prev)
    return None   # el texto pegado ES el resultado; no hace falta hablar


_CLIC = re.compile(r"\b(clic|click|clickea|toca|apreta|presiona|pulsa)")

# Reproducir/abrir algo EN EL NAVEGADOR dicho natural: "pone la cancion X", "reproduci el
# tercer video", "ver el segundo video", "mostrame el video de X", "dale al primer resultado".
# Exige un sustantivo-objeto (video/cancion/...) para no pisar la vision ("que estas viendo?").
_WEB_PLAY = re.compile(
    r"\b(pon\w*|reproduc\w+|dale (?:a|al|play)|abr[ií]\w*|mostr\w*|muestr\w*|ver|vamos a ver|anda a|"
    r"eleg\w*|seleccion\w*|clic\w*|click\w*|toca\w*|apreta\w*|pulsa\w*|dale click)\b"
    r"[^.]*\b(video|videos|clip|cancion|tema|musica|pelicula|peli|capitulo|resultado|enlace|link)\b"
)

# Cerrar la pestania / salir de un sitio: "cerra esto", "sali de youtube", "cerra la pestania"
_CERRAR_TAB = re.compile(
    r"\b(cerr[aá]\w*|cerrame|sal[ií]\w*|and[aá]te)\b[^.]*"
    r"\b(pestani?a|pestana|esto|esta|la pagina|el sitio|la web|youtube|el navegador|de aca)\b"
)


# "Venus, escribi" -> dicta y PEGA donde tengas el cursor (dictado manos libres).
# Se matchea sobre el texto ORIGINAL (no normalizado) para no perder tildes ni mayusculas.
# OJO: "escrib..." no colisiona con "escritorio" (escriB vs escriT).
_ES_DICTADO = re.compile(
    r"^\W*(?:escrib\w*|anot[aá]\w*|anotar|dict[aá]\w*|dictar|redact\w*|tom[aá]\s+nota|toma\s+nota)"
    r"\b[\s,.:¿?¡!-]*", re.IGNORECASE)


def _objetivo_clic(texto):
    """Si es un comando de clic/reproduccion, devuelve QUE clickear; si no, None."""
    n = acciones._norm(texto)
    if _WEB_PLAY.search(n):                       # "pone/reproduci/ver el video X" -> clic por DOM
        return n
    if not _CLIC.search(n):
        return None
    m = re.search(r"(?:en|sobre|al?)\s+(.+)$", n)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"(?:clic\w*|click\w*|toca\w*|apreta\w*|presiona\w*|pulsa\w*)\s+(.+)$", n)
    return m2.group(1).strip() if m2 else "el elemento principal"


# "Claude, ..." -> consulta al Claude Code CLI (cerebro grande, SOLO LECTURA).
# Whisper escribe el nombre de mil formas (cloud, clod, clau...), por eso las variantes.
_CLAUDE_ALIAS = r"(?:claude|cloud|clod|claud|clode|glaude|klaude|clau|clot)"
_ES_CLAUDE = re.compile(
    r"^\W*(?:hola|che|oye|ey|hey)?\s*" + _CLAUDE_ALIAS + r"\b"          # "Claude, fijate..."
    r"|\b(?:pregunt\w+|consult\w+|deci\w*|decile|habla\w*)\s+(?:a|con|le a)?\s*" + _CLAUDE_ALIAS + r"\b"
)


def _consulta_claude(texto):
    """Si el pedido es para Claude, devuelve la consulta SIN el nombre; si no, None."""
    n = acciones._norm(texto)
    if not _ES_CLAUDE.search(n):
        return None
    limpio = re.sub(r"^\W*(?:hola|che|oye|ey|hey)?\s*" + _CLAUDE_ALIAS + r"\b[\s,.:]*", "", n)
    limpio = re.sub(r"^\W*(?:pregunt\w+|consult\w+|deci\w*|decile|habla\w*)\s+(?:a|con|le a)?\s*"
                    + _CLAUDE_ALIAS + r"\b[\s,.:]*", "", limpio)
    return (limpio.strip() or texto).strip()


# Vocabulario para sesgar a Whisper en modo asistente (nombres de sitios/apps que el
# usuario nombra seguido y que se transcriben mal, ej. dolarhoy.com -> "dollaroy.com").
_VOCAB = (
    "Escritorio 1. Escritorio 2. Escritorio 3. Escritorio 4. "
    "Claude, fijate esto. Comandos para la computadora. Sitios: dolarhoy.com, Instagram, YouTube, Gmail, "
    "WhatsApp, Kommo, ChatGPT, Google Drive, Google Calendar, Facebook, Wikipedia, "
    "Mercado Libre, Infobae, Clarin, La Nacion, Netflix, Spotify, Twitch, LinkedIn. "
    "Leeme esto. Leeme en voz alta. Escribi. Borra. "
    "Claude Code, VS Code, Cursor, Whisper, Piper, Ollama, n8n, Kommo, Supabase, "
    "Corrientes Capital, pymes, Martin. "
    "Acciones: abri, entra, reproduci, pausa, clic, escritorio, volumen, pestania."
)


# Continuidad: despues de que Claude contesta, los pedidos que NO son comandos locales
# siguen yendo a Claude por un rato (asi "si, contame mas" no cae en el modelo chico).
_CONTINUIDAD = 150         # segundos
_ultimo_claude = 0.0


def _musica_espera_arrancar():
    if not Path(_WAV_MUSICA).exists():
        return
    try:
        winsound.PlaySound(_WAV_MUSICA,
                           winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
    except Exception as e:
        print("musica: no pudo arrancar:", e, flush=True)


def _musica_espera_parar():
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


# --- Que se oye mientras piensa -------------------------------------------------
# Si estabas escuchando algo (musica, un video, un audio), lo que suena mientras
# ella piensa es ESO, no la musiquita: la charla ya te lo habia pausado y aca te lo
# devolvemos hasta que arranque a hablar (pedido de Martin, 2026-08-16). La
# musiquita queda para cuando no habia nada sonando. ⚠ Solo vuelve lo que pausamos
# NOSOTROS por la charla: si lo pausaste vos a mano, se queda quieto — nunca le
# apretamos play a algo que vos paraste.
_espera_con_media = False


def _espera_arrancar():
    global _espera_con_media
    _espera_con_media = False
    try:
        from app.voz import media_pausa
        if media_pausa.devolver_mientras_piensa():
            _espera_con_media = True
            print("media: te devuelvo lo que sonaba mientras pienso", flush=True)
            return
    except Exception as e:
        print("media: no pude devolver lo que sonaba:", e, flush=True)
    _musica_espera_arrancar()


def _espera_parar(ep):
    """Termino de pensar: se calla lo que estaba sonando para poder hablarte.

    ⭐ La musiquita solo se para si SEGUIMOS siendo el turno vigente. Si la cortaste
    llamandola mientras pensaba, _interrumpir() ya purgo el audio y el "Te escucho"
    YA esta sonando: winsound purga TODO el proceso, asi que este parar se comia el
    aviso a mitad de palabra y te quedabas sin saber si te habia escuchado.
    Tu musica, en cambio, se vuelve a pausar SIEMPRE — tambien si la cortaste —,
    porque si no te quedaba la cancion sonando encima del "Te escucho"."""
    global _espera_con_media
    if _espera_con_media:
        _espera_con_media = False
        try:
            from app.voz import media_pausa
            media_pausa.pausar_por_charla()
        except Exception as e:
            print("media: no pude volver a pausar:", e, flush=True)
    elif _vigente(ep):
        _musica_espera_parar()


def _marcar_claude():
    """Laura acaba de hablar: por _CONTINUIDAD segundos podes seguirle sin nombrarla."""
    global _ultimo_claude
    _ultimo_claude = time.time()


def _preguntar_claude(consulta, ep=None):
    """Consulta a Claude y contesta por voz. Marca la conversacion como 'caliente'."""
    global _ultimo_claude
    print("claude:", consulta, flush=True)    # sin aviso hablado: al usuario le resultaba molesto
    from app.voz import cerebro_grande as claude_voz
    _espera_arrancar()
    try:
        r = claude_voz.preguntar(consulta)
    except Exception as e:
        print("claude_voz fallo:", e, flush=True)
        r = "No pude hablar con Claude."
    finally:
        _espera_parar(ep)
    if not _vigente(ep):
        # Mientras Laura trabajaba hiciste otra cosa. Antes esto se DESCARTABA en
        # silencio y los trabajos largos morian sin aviso. Ahora: si hay respuesta
        # real (no la cortaste vos), espera un momento de silencio y te la dice.
        if r and not getattr(claude_voz, "_CANCELADO", False):
            print("claude termino tarde: aviso apenas haya silencio", flush=True)
            threading.Thread(target=_avisar_cuando_libre, args=(r,), daemon=True).start()
        else:
            print("claude: descartado (interrumpido)", flush=True)
        return
    print("claude respuesta:", r, flush=True)
    _ultimo_claude = time.time()
    hablar(r, ep)


AVISO_ESPERA_MAX = 3600   # cuanto espera un hueco para avisarte, antes de rendirse


def _avisar_sistema(texto, prefijo="aviso sistema"):
    """Dice algo por iniciativa propia, sin que le hayas preguntado nada.

    Espera a que haya un hueco de verdad: que no estes hablando vos, que no este
    hablando ella, y que la escucha NO este en pausa — si pausaste es porque estas en
    una llamada o jugando, y ahi un aviso hablado es una molestia y no un favor. Se
    queda esperando hasta una hora; no lo tira, lo guarda para cuando puedas oirlo.

    prefijo: con que etiqueta queda en el log (el /chat del panel filtra por eso).
    """
    fin = time.time() + AVISO_ESPERA_MAX
    while time.time() < fin:
        if not (_grabando or _hablando or _pausado):
            print(f"{prefijo}: {texto}", flush=True)
            # Con la epoca REAL, no con None: None es "invencible" (_vigente lo deja
            # hablar pase lo que pase) y una lectura de dos minutos no habia forma de
            # callarla — el asistente encolaba SU respuesta detras de la lectura y
            # parecia que Venus te ignoraba. Con la epoca vigente, decir "Venus",
            # "para" o apretar Shift+F9 la corta en el acto, como a todo lo demas.
            hablar(texto, _epoca)
            return
        time.sleep(2.0)
    print(f"{prefijo} descartado, nunca hubo un hueco: {texto}", flush=True)


def _avisar_sistema_async(texto):
    """El vigilante del cupo no puede quedarse esperando: mide en el mismo hilo."""
    threading.Thread(target=_avisar_sistema, args=(texto,), daemon=True).start()


# --- Pausar la musica/video mientras hay charla, y reanudar al terminar -----------
# Pedido 2026-08-11: que lo que este sonando (Spotify, YouTube...) se pause cuando
# hablas con Venus/Laura Y cuando ellas te hablan, y que despues vuelva solo.
MEDIA_QUIETUD = 6.0   # silencio total antes de reanudar. MAS que SEGUIMIENTO (4 s):
                      # si no, la musica volvia en el hueco entre pregunta y repregunta.


def _vigilar_media():
    """Pausa lo que suena cuando arranca la charla (en cualquier direccion) y lo
    reanuda cuando todo quedo quieto un rato. Solo reanuda LO QUE PAUSO EL: si vos
    pausaste algo a mano, no lo toca."""
    from app.voz import media_pausa
    en_pausa_por_charla = False
    ultimo_activo = 0.0
    while True:
        # _procesando cubre el hueco entre "dejaste de grabar" y "Laura empieza a
        # hablar": ahi esta esperando al LLM (a veces resumiendo la sesion, 10-20s).
        # Sin esto, ese hueco silencioso pasaba de MEDIA_QUIETUD y el vigilante daba
        # por terminada la charla a mitad de una pregunta, reanudando la musica antes
        # de tiempo (2026-08-11: asi es como Spotify se ponia en play solo).
        activo = _grabando or _hablando or _procesando
        ahora = time.time()
        if activo:
            ultimo_activo = ahora
            # en_gracia(): acabas de PEDIR musica ("play", "pone tal cancion") — no
            # pausarte lo que pediste porque "hay actividad" (es Venus confirmando).
            if not en_pausa_por_charla and not media_pausa.en_gracia():
                nuevas = media_pausa.pausar_por_charla()
                if nuevas:
                    print(f"media: pauso {len(nuevas)} app(s) mientras hablamos", flush=True)
                en_pausa_por_charla = True
        elif en_pausa_por_charla and (ahora - ultimo_activo) > MEDIA_QUIETUD:
            # reanudar_por_charla NO toca lo que pausaste vos con "Venus, pausa":
            # si en el medio dijiste "pausa", esa tanda paso a ser tuya y se queda
            # quieta hasta que digas "reproduci". Sin esto, tu orden se deshacia
            # sola a los 6 segundos.
            reanudadas = media_pausa.reanudar_por_charla()
            if reanudadas:
                print("media: charla terminada, reanudo", flush=True)
            en_pausa_por_charla = False
        time.sleep(0.3)


# --- Lectura automatica: te lee las respuestas de UNA sesion de Claude Code -------
LECTURA_MAX = 4000        # tope por respuesta (~2 min de voz); el resto queda en pantalla


def _vigilar_lectura():
    """Sigue la sesion elegida en el panel y lee sus respuestas al terminar.

    El panel escribe seguir_lectura.json (que sesion) y aca se mira cada segundo —
    mismo patron que pausa_escucha.flag. Si el archivo no esta, no se lee nada: ese
    archivo ES la perilla de prendido/apagado. La espera del hueco para hablar es la
    misma de los avisos del sistema: no te pisa, no habla en pausa.
    """
    from app.voz import seguir
    from app.voz import cerebro_grande as claude_voz
    seguidor = None
    nombre = ""
    while True:
        try:
            cfg = json.loads(SEGUIR_LECTURA.read_text(encoding="utf-8")) \
                if SEGUIR_LECTURA.exists() else None
        except Exception:
            cfg = None
        if not cfg or not cfg.get("jsonl"):
            if seguidor is not None:
                print("lectura: apagada", flush=True)
                seguidor = None
            time.sleep(1.0)
            continue
        if seguidor is None or str(seguidor.ruta) != cfg["jsonl"]:
            seguidor = seguir.Seguidor(cfg["jsonl"])
            nombre = cfg.get("nombre") or "la sesion elegida"
            print(f"lectura: sigo a {nombre} ({cfg['jsonl']})", flush=True)
            _avisar_sistema_async(f"Listo, te leo lo que diga {nombre}.")
        try:
            for texto in seguidor.novedades():
                # _limpiar es el de Laura: saca markdown, links y bloques de codigo,
                # que leidos en voz alta son ruido puro.
                texto = claude_voz._limpiar(texto)
                if not texto:
                    continue
                if len(texto) > LECTURA_MAX:
                    texto = (texto[:LECTURA_MAX].rsplit(" ", 1)[0]
                             + ". Corto aca, el resto esta en pantalla.")
                _avisar_sistema(texto, prefijo=f"lectura respuesta [{nombre}]")
        except Exception as e:
            print("lectura: fallo leyendo la sesion:", e, flush=True)
        time.sleep(1.0)


# --- Avisos hablados: cualquier proyecto de la maquina puede hacerla hablar ---------
# `avisar.py --hablar` deja una linea JSON en ~/.claude/avisos_hablados.jsonl y aca se
# la come. Sirve para lo que uno quiere ENTERARSE en el momento y no cuando mira el
# telefono: se cayo un bot de un cliente, se desconecto un WhatsApp, fallo un backup.
# El aviso igual sale al celular por el canal de siempre: esto es un canal MAS, no un
# reemplazo, porque si la voz esta apagada aca no lo escucha nadie.
AVISO_HABLADO_VENCE = 3600     # mas viejo que esto no se lee: llega descolgado y confunde


def _vigilar_avisos_hablados():
    """Lee en voz alta los avisos que dejan otros proyectos, cuando haya un hueco.

    Se renombra el archivo antes de leerlo: asi un proyecto que escribe justo en ese
    momento no pierde su aviso (le falla el rename, no la escritura) y no hay forma de
    leer dos veces lo mismo. La espera del hueco es la de siempre (_avisar_sistema):
    no te pisa, no habla si pausaste la escucha.
    """
    tomado = AVISOS_HABLADOS.with_suffix(".leyendo")
    while True:
        time.sleep(2.0)
        try:
            if not AVISOS_HABLADOS.exists() or AVISOS_HABLADOS.stat().st_size == 0:
                continue
            if tomado.exists():          # quedo de una vuelta anterior que murio a la mitad
                tomado.unlink()
            AVISOS_HABLADOS.rename(tomado)
            lineas = tomado.read_text(encoding="utf-8", errors="replace").splitlines()
            tomado.unlink()
        except Exception as e:
            print("avisos hablados: no pude tomar el archivo:", e, flush=True)
            continue
        for linea in lineas:
            if not linea.strip():
                continue
            try:
                a = json.loads(linea)
            except Exception:
                a = {"texto": linea}
            texto = (a.get("texto") or "").strip()
            if not texto:
                continue
            viejo = time.time() - float(a.get("cuando") or 0)
            if a.get("cuando") and viejo > AVISO_HABLADO_VENCE:
                print(f"aviso hablado vencido ({int(viejo / 60)} min): {texto}", flush=True)
                continue
            proyecto = a.get("proyecto") or "un proyecto"
            _avisar_sistema(f"Aviso de {proyecto}. {texto}",
                            prefijo=f"aviso hablado [{proyecto}]")


# --- Laura por Telegram: atiende el buzon que deja el bot ---------------------------
# El proceso `claude` persistente (la memoria de Laura) vive en ESTE proceso, asi que
# el bot de Telegram no puede hablarle directo: deja la pregunta en un archivo
# (app/voz/buzon.py) y aca se la pasamos al mismo proceso de siempre. Una sola Laura:
# lo que le digas por el telefono y por el microfono es la misma conversacion.
_MARCA_TELEGRAM = (
    "[Este mensaje llega POR TELEGRAM, escrito desde el telefono, no por voz. El bot "
    "esta cerrado por lista blanca al user id de Martin: quien escribe por este canal "
    "ES Martin, tratalo con la misma confianza que por microfono. Responde por "
    "escrito, en texto plano sin markdown; EXTENDETE MUCHO MAS que por voz: acá "
    "Martin lo lee en pantalla y no hay apuro, así que da respuestas largas, con "
    "detalles, explicaciones completas, y usa saltos de linea para separar ideas. "
    "No la respuesta minima: la que el merece.] ")

# Lo mismo pero escrito desde el panel de la maquina (el chat de la pagina 8750).
# Se separa de Telegram porque el contexto real es distinto: aca Martin esta
# sentado frente a la PC, puede pasarte archivos y ver lo que hacés al toque.
_MARCA_PANEL = (
    "[Este mensaje llega ESCRITO desde el chat del panel, en la misma computadora "
    "(no por voz y no por Telegram): es Martin, sentado frente a la PC. Contesta CORTO "
    "Y AL GRANO, igual que por microfono: 1 a 3 frases, texto plano, sin markdown, sin "
    "listas, sin bloques de codigo y sin rutas largas. La respuesta puede leerse en voz "
    "alta, asi que tiene que sonar bien dicha. Si el tema da para mas, resumi lo "
    "esencial y ofrece el detalle en vez de largarlo todo. Si te paso una imagen, la "
    "ruta viene en el mensaje: abrila con la herramienta Read antes de contestar.] ")


def _vigilar_telegram():
    """Contesta por el buzon, en silencio: nada de esto sale por el parlante.

    ⚠ El bucle entero va adentro de un try: si este hilo se muere, Laura deja de
    contestar por Telegram Y por el chat del panel, y no avisa nadie — quedás
    escribiendo al vacio. Pasó el 2026-08-14: un emoji en una respuesta reventó el
    print del log y el hilo se murió ahi mismo. Un error atendiendo UN mensaje no
    puede costar el canal entero.
    """
    # ⚠ Va por el interruptor, no por claude_voz directo: si no, el chat del panel y
    # Telegram siguen hablandole a Claude aunque hayas puesto Codex, y no hay forma de
    # notarlo salvo preguntandole con cual esta pensando (pasó el 2026-08-19).
    from app.voz import buzon
    from app.voz import cerebro_grande as claude_voz
    while True:
        try:
            _atender_buzon(buzon, claude_voz)
        except Exception as e:
            print("buzon: error atendiendo un mensaje (sigo vivo):", e, flush=True)
            time.sleep(1.0)


def _atender_buzon(buzon, claude_voz):
    """Una vuelta del buzon: mira si hay pregunta, la contesta y deja la respuesta."""
    try:
        p = buzon.sacar_pregunta()
    except Exception as e:
        print("buzon: fallo mirando el buzon:", e, flush=True)
        p = None
    if not p:
        time.sleep(0.5)
        return
    texto = p["texto"]
    # De donde vino: el buzon lo usan el bot de Telegram y el chat del panel.
    # Cambia la marca de contexto y el prefijo del log (y con eso, el color de
    # la burbuja en el chat del panel).
    panel = p.get("origen") == "panel"
    etiqueta = "panel" if panel else "telegram"
    marca = _MARCA_PANEL if panel else _MARCA_TELEGRAM
    # ⚠ Nada de marcas de diagnostico en esta linea: el /chat del panel la muestra
    # TAL CUAL en tu burbuja. Un "[leer]" que puse para depurar termino apareciendo
    # adentro de cada mensaje de Martin. Lo que sirva para diagnosticar va al log de
    # eventos, que no se dibuja en ningun lado.
    print(f"{etiqueta} pregunta:", re.sub(r"\s+", " ", texto), flush=True)
    if p.get("leer"):
        _evento(f"{etiqueta}: la respuesta va tambien en voz alta")
    _marcar_pensando(True)
    try:
        # El mismo enganche del saludo del dia que usa la voz: si Laura pregunto
        # "¿seguimos o empezamos de nuevo?", lo que escribas por Telegram es la
        # respuesta a eso. Y si no lo era, responder_dia devuelve None y la
        # consulta sigue su camino normal.
        r = None
        if claude_voz.esperando_dia():
            r = claude_voz.responder_dia(texto)
        if r is None:
            r = claude_voz.preguntar(marca + texto, para_voz=False)
    except Exception as e:
        print(f"{etiqueta}: fallo la consulta:", e, flush=True)
        r = "Se me rompio algo atendiendo tu mensaje. Probemos de nuevo en un rato."
    finally:
        _marcar_pensando(False)
    r = (r or "").strip() or "Me interrumpieron aca en el medio y no llegue a contestarte."
    # ⭐ La respuesta se DEJA antes de imprimirla. Es al reves de lo que sale natural,
    # y es a proposito: el print es lo unico de aca que puede fallar (el log tiene una
    # codificacion, la respuesta puede traer cualquier cosa). Si falla despues de
    # dejarla, vos ya tenes tu respuesta y solo se pierde una linea del log.
    try:
        buzon.dejar_respuesta(p["id"], r)
    except Exception as e:
        print(f"{etiqueta}: no pude dejar la respuesta:", e, flush=True)
    # El log es por lineas (el /chat del panel lo parsea asi): la respuesta va aplanada
    # AL LOG, pero al telefono viaja tal cual, con sus saltos de linea.
    print(f"{etiqueta} respuesta:", re.sub(r"\s+", " ", r), flush=True)
    # El interruptor de leer en voz alta del chat del panel: ademas de escribirla,
    # decirla. En un hilo aparte para no demorar la respuesta escrita, y por
    # _avisar_sistema para heredar el respeto por la pausa y la espera del hueco. El
    # prefijo del log es otro a proposito: la burbuja del chat ya la puso
    # "panel respuesta:", y con el mismo prefijo saldria repetida.
    if p.get("leer") and r:
        threading.Thread(target=_avisar_sistema, args=(r,),
                         kwargs={"prefijo": "panel leido"}, daemon=True).start()


def _avisar_cuando_libre(texto):
    """Espera a que no estes hablando/grabando y recien ahi anuncia el resultado."""
    global _ultimo_claude
    fin = time.time() + 180
    while time.time() < fin and (_grabando or _hablando):
        time.sleep(0.5)
    print("claude respuesta (tardia):", texto, flush=True)
    _ultimo_claude = time.time()          # podes contestarle sin nombrarla
    hablar("Laura termino. " + texto, _epoca)   # epoca real: se corta si tomas el turno


def _procesar(frames, modo, ep=None, manos_libres=False):
    global _captura_vacia, _procesando
    if not frames:
        return
    audio = np.concatenate(frames, axis=0).flatten().astype("float32")
    if len(audio) < SR * MIN_SEG:
        return
    if float(np.abs(audio).max()) < 0.0005:
        # VERDAD DE CAMPO: apretaste una tecla y grabaste SILENCIO DIGITAL.
        # Micro muerto seguro -> el watchdog cambia en <5s.
        _captura_vacia = True
        print("grabacion (tecla) en silencio digital -> fuerzo cambio de micro", flush=True)
        return
    _t0 = time.time()
    _t_lock = _t0
    try:
        with _model_lock:
            _t_lock = time.time()            # cuanto se espero el turno del modelo
            segs, _ = model.transcribe(audio, language="es", vad_filter=True,
                                       beam_size=1, condition_on_previous_text=False,
                                       initial_prompt=(None if modo == "dictado" else _VOCAB))
            texto = " ".join(s.text.strip() for s in segs).strip()
    except Exception as e:
        print("error transcribiendo:", e, flush=True)
        return
    _medir("transcribir", _t0,
           f"audio={len(audio) / SR:.1f}s cola={_t_lock - _t0:.2f}s")
    texto = _ECO_SALUDO.sub("", texto).strip()   # el saludo se cuela por los parlantes
    if not _vigente(ep):                     # te adelantaste: no contestes algo viejo
        return
    if not texto:                            # hubo ruido pero no se entendio nada
        print("no se entendio nada", flush=True)
        if manos_libres:
            _sonar(_WAV_NADA, _NADA_OK)      # sin esto quedaba mudo y no sabias que paso
        return
    if modo == "dictado":
        texto, mandar = _sacar_enter_final(texto)   # "... enter" al final = pegar Y mandar
        print("dictado:", texto + ("  [ENTER]" if mandar else ""), flush=True)
        _pegar_y_mandar(texto, mandar)
        return
    print("comando:", texto, flush=True)
    _t0 = time.time()
    _procesando = True
    _marcar_pensando(True)          # que el panel muestre los puntitos tambien por voz
    try:
        _manejar_texto(texto, modo, ep)
    finally:
        _procesando = False
        _marcar_pensando(False)
    _medir("respuesta_total", _t0, "(decidir + LLM + sintesis + reproduccion)")
    if manos_libres:                     # veniamos de la palabra clave: segui escuchando
        _seguir_escuchando(modo, ep)


def _manejar_texto(texto, modo, ep=None):
    """Rutea un pedido ya transcripto (viene de una tecla o de un wake word)."""
    # Frases cortas que despliegan un procedimiento completo. Va antes del cambio de
    # cerebro porque el procedimiento lo ejecuta el que ya esté puesto; no cambia la
    # charla ni saltea las reglas de confirmación del cerebro grande.
    try:
        from app.voz import ordenes_reutilizables
        _orden, _respuesta_local = ordenes_reutilizables.resolver(texto)
        if _respuesta_local:
            print("claude respuesta:", _respuesta_local, flush=True)
            hablar(_respuesta_local, ep)
            return
        if _orden:
            texto = _orden
    except Exception as e:
        print("orden reutilizable: no pude resolverla:", e, flush=True)
    # "Laura, pasate a Codex" / "volvé a Claude": cambiar de cerebro grande va PRIMERO
    # que todo, incluso que el saludo del dia. Si esto se ruteara como una consulta
    # normal, se la comeria el cerebro que justo esta puesto: te contestaria que si y
    # no cambiaria nada. Ver `app/voz/cerebro_grande.py`.
    try:
        from app.voz import cerebro_grande as _cg
        _otro = _cg.pedido_de_cambio(texto)
        if _otro:
            r = _cg.usar(_otro)
            print("claude respuesta:", r, flush=True)     # que quede en el chat del panel
            if _vigente(ep):
                hablar(r, ep)
            return
    except Exception as e:
        print("cerebro grande: no pude cambiar:", e, flush=True)
    # ANTES QUE TODO: si Laura saludo por ser la primera vez del dia, esto es tu
    # respuesta. Tiene que ganarle a acciones.ejecutar, porque "segui con la anterior"
    # matchea el patron de media_playpause (tiene "segu[ií]") y en vez de contestarte
    # apretaria play.
    try:
        from app.voz import cerebro_grande as claude_voz
        if claude_voz.esperando_dia():
            print("claude: respuesta al saludo del dia:", texto, flush=True)
            _espera_arrancar()
            try:
                r = claude_voz.responder_dia(texto)
            finally:
                _espera_parar(ep)
            if r:                            # None = no era una respuesta: seguí ruteando
                # El prefijo "claude respuesta:" es OBLIGATORIO: es de donde el /chat
                # del panel saca la conversacion en vivo. Sin esta linea la respuesta
                # se escuchaba pero no quedaba en ningun lado, ni en el log ni en el
                # panel (pasó con el primer resumen de sesion, el 2026-08-11).
                print("claude respuesta:", r, flush=True)
                if _vigente(ep):
                    _marcar_claude()
                    hablar(r, ep)
                return
    except Exception as e:
        print("claude: no pude resolver el saludo del dia:", e, flush=True)
    # Arrancar de cero a mano. UNA sola frase ("arranquemos una sesion nueva"), ver
    # claude_voz._NUEVA_SESION: antes esto enganchaba con "olvida" suelto y te borraba
    # la charla del dia por decir "olvidate de eso" en el medio de una conversacion.
    try:
        from app.voz import cerebro_grande as _cv
        _pide_nueva = _cv.pide_sesion_nueva(texto)
    except Exception as e:
        print("claude: no pude mirar si pedias sesion nueva:", e, flush=True)
        _pide_nueva = False
    if _pide_nueva:
        cerebro.olvidar()
        try:
            from app.voz import cerebro_grande as claude_voz
            claude_voz.olvidar()
        except Exception:
            pass
        hablar("Listo, empecemos de nuevo.", ep)
        return
    if modo == "claude":                      # Ctrl+F9 -> directo a Claude, sin nombrarlo
        # ...salvo anotar en la pizarra: eso se resuelve ACA, en milisegundos, en
        # vez de esperar varios segundos a que lo piense el LLM. Es el UNICO
        # comando que se adelanta en modo Claude, y solo dispara con un verbo de
        # anotar o con "pizarra" al principio, asi que preguntarle algo sobre la
        # pizarra en medio de una charla sigue yendo a Claude como siempre.
        try:
            if acciones.es_anotar_pizarra(texto):
                resp, ok = acciones.ejecutar(texto)
                if ok:
                    print("respuesta:", resp, flush=True)
                    hablar(resp, ep)
                    return
        except Exception as e:
            print("via rapida de pizarra fallo, sigo con Claude:", e, flush=True)
        _preguntar_claude(texto, ep)
        return
    consulta = _consulta_claude(texto)        # "Claude, ..." -> cerebro grande (solo lectura)
    if consulta:
        _preguntar_claude(consulta, ep)
        return
    if _ES_ENTER.match(texto):                # "Venus, enter" -> Enter en la sesion elegida
        _apretar_enter(ep)
        return
    ms = _ES_SELECCIONAR_SESION.match(texto)  # "selecciona la sesion X" -> gira la perilla
    if ms:                                    # (ANTES de acciones: "seleccion\w+" alla es Ctrl+A)
        _seleccionar_sesion(ms.group(1).strip(), ep)
        return
    me = _ES_ESCRIBIR_SESION.match(texto)     # "escribi EN LA SESION x" va ANTES que el
    if me:                                    # dictado comun, que tambien arranca con "escribi"
        _escribir_en_sesion(me.group(1).strip(), ep)
        return
    md = _ES_DICTADO.match(texto)             # "Venus, escribi ..." -> a la SESION ELEGIDA
    if md:
        # Para dictar donde este el cursor esta F9: por eso la palabra hablada va
        # SIEMPRE a la sesion seleccionada (pedido 2026-08-11). Sin sesion elegida
        # no adivina: te dice como elegir una.
        resto = texto[md.end():].strip()      # texto ORIGINAL: conserva tildes y mayusculas
        destino = _leer_destino()
        if not destino:
            hablar("No hay ninguna sesion elegida. Decime: Venus, selecciona tal sesion. "
                   "O elegila en el panel. Para escribir donde este el cursor, usa efe nueve.", ep)
            return
        ok, titulo_activo = _enfocar_sesion(destino)
        if not ok:
            hablar(f"No pude traer al frente la sesion {_nombre_corto(destino['nombre'])}. "
                   "No escribi nada.", ep)
            print(f"escritura ABORTADA: quedo al frente {titulo_activo!r}", flush=True)
            return
        _enfocar_cajita()
        if _resto_util(acciones._norm(resto)):
            resto, mandar = _sacar_enter_final(resto)
            print(f"dictado: [a {_nombre_corto(destino['nombre'])}] {resto}"
                  + ("  [ENTER]" if mandar else ""), flush=True)
            _pegar_y_mandar(resto, mandar)    # lo dijiste todo junto: pegalo ya
        else:
            print("dictado: te escucho para escribir", flush=True)
            _abrir_micro_tras_ey("dictado", ep)   # la ventana correcta ya esta al frente
        return
    n_txt = acciones._norm(texto)
    if _ES_LEER.match(n_txt) and not re.search(r"pantalla|monitor|pagina|\bweb\b", n_txt):
        hablar(_leer_seleccion(ep), ep)      # "leeme" -> lee en voz alta la seleccion
        return
    if _es_transformacion(texto):            # transformar texto seleccionado (corregir/traducir/...)
        r = _transformar_seleccion(texto)
        if r:
            hablar(r, ep)
        return
    if _CERRAR_TAB.search(acciones._norm(texto)):   # "cerra esto" / "sali de youtube"
        try:
            from app.web import navegador
            if navegador._puerto_ok() and navegador.cerrar_pestana_actual():
                hablar("Cerre la pestana.", ep)
                return
        except Exception as e:
            print("cerrar tab fallo:", e, flush=True)
    if _WEB_PLAY.search(acciones._norm(texto)):   # reproducir/clickear en el navegador -> browser-use (robusto)
        print("web task:", texto, flush=True)
        hablar("Dame un segundo.", ep)             # aviso: la tarea de navegador tarda unos segundos
        r = None
        try:
            from app.web import agente_web
            r = agente_web.ejecutar_tarea(texto)
        except Exception as e:
            print("agente_web fallo:", e, flush=True)
        hablar(r or "No pude hacerlo en el navegador.", ep)
        return
    objetivo = _objetivo_clic(texto)         # clic (otras apps): visual con Gemini
    if objetivo:
        print("clic objetivo:", repr(objetivo), flush=True)
        hecho = False
        try:
            from app.web import navegador
            if navegador._puerto_ok():          # intenta DOM sobre la pestania que estas mirando (hasFocus)
                hecho = navegador.clic_inteligente(objetivo)
        except Exception as e:
            print("clic DOM fallo:", e, flush=True)
        print("clic resultado:", "DOM ok" if hecho else "DOM no encontro, voy visual", flush=True)
        if hecho:
            hablar("Listo.", ep)
        else:
            r = cerebro.clic_visual(objetivo)     # fallback visual (Gemini) sobre lo que se ve
            if r:
                hablar(r, ep)
        return
    resp, ok = acciones.ejecutar(texto)      # via rapida: comandos fijos
    if not ok:
        if _es_pantalla(texto):              # pedido de pantalla -> vision directa (confiable)
            resp = cerebro.ver_pantalla(texto, _monitor_pedido(texto)) or "No pude leer la pantalla."
        elif modo != "local" and time.time() - _ultimo_claude < _CONTINUIDAD:
            _preguntar_claude(texto, ep)     # veniamos hablando con Claude: seguí con el
            return                           # (modo "local" = dijiste Venus: no deriva)
        else:
            resp = cerebro.agente(texto) or "No te entendi, podes repetir?"
    if not _vigente(ep):                     # te adelantaste: no contestes algo viejo
        print("respuesta descartada (interrumpido)", flush=True)
        return
    print("respuesta:", resp, flush=True)
    hablar(resp, ep)


def _on_key(ev):
    global _shift, _ctrl, _alt, _grabando, _buf, _modo
    n = (ev.name or "").lower()
    if "shift" in n:
        _shift = (ev.event_type == "down"); return
    if "ctrl" in n:
        _ctrl = (ev.event_type == "down"); return
    if "alt" in n:
        _alt = (ev.event_type == "down"); return
    if n == "f9":
        if ev.event_type == "down":
            if _grabando:
                return
            if _ctrl and not _alt:
                _modo = "claude"            # Ctrl+F9 -> directo a Claude (sin nombrarlo)
            elif _shift:
                _modo = "asistente"
            elif not _alt:
                _modo = "dictado"
            else:
                return                      # alt + F9 -> ignorar
            if _modo == "dictado":
                # F9 solo NO la interrumpe: estas dictando en otra ventana, no
                # hablandole. Ella sigue con lo suyo y vos dictas en paralelo
                # (con auriculares su voz no se cuela: eco medido 0.005).
                pass
            else:
                _interrumpir("tecla")       # Shift/Ctrl+F9 = tomar el turno: corta todo
            _buf = []
            _grabando = True
            _beep(880, 90)
        elif ev.event_type == "up":
            if _grabando:
                _grabando = False
                _beep(560, 90)
                frames = list(_buf)
                modo = _modo
                threading.Thread(target=_procesar, args=(frames, modo, _epoca), daemon=True).start()


keyboard.hook(_on_key)

# El vigilante del cupo (avisaba hablando al 70 %) se saco el 2026-08-14, a pedido de
# Martin y junto con la tarjeta del panel: no medía el uso real del plan, lo estimaba
# contra limites puestos a ojo y daba la mitad de lo que mostraba Claude. Un aviso
# hablado con un numero inventado interrumpe Y desinforma. `app/voz/cupo.py` sigue
# ahi por si algun dia se puede medir de verdad, pero nadie lo llama.

# La lectura automatica de sesiones: tambien al final y por lo mismo (usa
# _avisar_sistema, definida a mitad del archivo).
try:
    threading.Thread(target=_vigilar_lectura, daemon=True).start()
except Exception as e:
    print("no pude arrancar la lectura automatica:", e, flush=True)

# Los avisos hablados que dejan otros proyectos (mismo motivo para arrancarlo aca:
# usa _avisar_sistema, que se define a mitad del archivo).
try:
    threading.Thread(target=_vigilar_avisos_hablados, daemon=True).start()
except Exception as e:
    print("no pude arrancar los avisos hablados:", e, flush=True)

# El pausador de musica/video durante la charla (winsdk; si falta, avisa y sigue).
try:
    threading.Thread(target=_vigilar_media, daemon=True).start()
except Exception as e:
    print("no pude arrancar el pausador de media:", e, flush=True)

# Laura por Telegram: atiende las preguntas que el bot deja en el buzon. Tambien al
# final del archivo, como todos los vigilantes (usan funciones de mas arriba).
try:
    threading.Thread(target=_vigilar_telegram, daemon=True).start()
except Exception as e:
    print("no pude arrancar el buzon de Telegram:", e, flush=True)

# Laura por llamada (pagina web para hablarle desde el celular, en vivo). Se le
# PASAN el modelo y la voz ya cargados (nunca los importa el mismo): cargarlos de
# nuevo duplicaria VRAM. Sin LAURA_VOZ_TOKEN en el .env queda apagado, no abierto.
try:
    from app.voz import llamada as _llamada
    from app.voz import cerebro_grande as _claude_voz_llamada

    def _preguntar_por_llamada(texto):
        # Mismo enganche que _vigilar_telegram(): si Laura acaba de saludar por ser
        # la primera charla del dia, esto ES la respuesta a esa pregunta, no un
        # pedido nuevo. Sin este paso, _esperando_dia se queda prendido para SIEMPRE
        # (nadie mas lo apaga) y las otras vias (voz, Telegram) tambien se rompen.
        r = None
        if _claude_voz_llamada.esperando_dia():
            r = _claude_voz_llamada.responder_dia(texto)
        if r is None:
            r = _claude_voz_llamada.preguntar(texto, para_voz=False)
        return r

    def _historial_por_llamada(max_turnos=12):
        # Reusa _charla_de (pensada para resumir un DIA VIEJO) sobre la sesion de
        # HOY: el formato "Yo: .../Vos: ..." es el mismo, solo hay que separarlo en
        # burbujas en vez de mandarlo entero como texto de prompt.
        sid = _claude_voz_llamada._SESION
        if not sid:
            return []
        texto = _claude_voz_llamada._charla_de(sid, max_chars=8000)
        turnos = []
        for linea in texto.splitlines():
            if linea.startswith("Yo: "):
                dicho = linea[4:]
                if dicho.startswith(_MARCA_TELEGRAM):
                    # Lo que escribiste por Telegram trae pegado el aviso interno
                    # de contexto: se lo mandamos a Laura, pero mostrado tal cual
                    # ensucia la burbuja con un parrafo que no dijiste vos.
                    dicho = dicho[len(_MARCA_TELEGRAM):]
                turnos.append({"quien": "vos", "texto": dicho})
            elif linea.startswith("Vos: "):
                turnos.append({"quien": "laura", "texto": linea[5:]})
        return turnos[-max_turnos:]

    _llamada.arrancar(model, _model_lock, voz, _preguntar_por_llamada, vocab=_VOCAB,
                      historial_fn=_historial_por_llamada)
except Exception as e:
    print("no pude arrancar la llamada por celular:", e, flush=True)

# Laura por TELEFONO (Twilio): una llamada de verdad al celular. Es lo unico que
# funciona con la pantalla apagada Y con auriculares Bluetooth — el navegador del
# iPhone no deja lo primero y Discord todavia no puede recibir audio.
try:
    import os as _os_tel
    from app.voz import telefono as _telefono

    _telefono.arrancar(model, _model_lock, voz, _preguntar_por_llamada, vocab=_VOCAB,
                       cfg={"sid": _os_tel.getenv("TWILIO_SID", ""),
                            "token": _os_tel.getenv("TWILIO_TOKEN", ""),
                            "numero_twilio": _os_tel.getenv("TWILIO_NUMERO", ""),
                            "destino": _os_tel.getenv("TELEFONO_DESTINO", ""),
                            "url_publica": _os_tel.getenv("TELEFONO_URL_PUBLICA", "")})
except Exception as e:
    print("no pude arrancar la llamada telefonica:", e, flush=True)

# Laura por Discord: la MISMA charla, pero por un canal de voz. Es lo unico que
# funciona con la pantalla del celular bloqueada y con auriculares Bluetooth —
# Safari no deja ninguna de las dos cosas. Mismo modelo y misma voz ya cargados.
try:
    import os as _os
    from app.voz import discord_voz as _discord_voz

    _discord_voz.arrancar(model, _model_lock, voz, _preguntar_por_llamada,
                          token=_os.getenv("DISCORD_BOT_TOKEN", ""),
                          usuario_id=_os.getenv("DISCORD_USUARIO_ID", "") or 0,
                          vocab=_VOCAB)
except Exception as e:
    print("no pude arrancar el bot de Discord:", e, flush=True)

print("Voz ACTIVA.  F9 = dictar  |  Shift+F9 = asistente  |  Ctrl+F9 = Claude."
      + ("  |  'Laura' = Claude, 'Venus' = asistente"
         + (" (Porcupine)." if _wake_porcupine else " (Whisper).") if WAKE_ON else ""), flush=True)
# Aviso HABLADO de que ya esta escuchando: sin esto, al prender la compu no habia
# forma de saber cuando el asistente quedaba listo (los modelos tardan ~20s en cargar).
hablar("Listo, te escucho.")
keyboard.wait()
