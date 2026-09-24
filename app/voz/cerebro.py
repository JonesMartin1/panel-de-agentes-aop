"""
Cerebro LLM local (Ollama + Qwen3-4B) para el asistente.
Se usa como RESPALDO: si acciones.ejecutar no matchea un comando fijo,
se le pregunta al LLM y responde en lenguaje natural (breve, para leer en voz).
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)

import io
import re
import json
import base64
import requests

from app.voz import acciones
from app.nucleo import analizar_gemini

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELO = "qwen3:4b-instruct-2507-q4_K_M"   # LOCAL para texto/tool-calling (la vision va por Gemini nube)

SYSTEM = (
    "Sos un asistente de voz en espanol rioplatense (Argentina). "
    "Respondes SIEMPRE breve: 1 o 2 frases, claro y natural. "
    "No uses markdown, ni listas, ni emojis, ni parentesis con aclaraciones, "
    "porque tu respuesta se lee en voz alta. Si no sabes algo, decilo corto."
)

SYSTEM_AGENTE = (
    "Sos un asistente de voz en espanol rioplatense que CONTROLA la computadora del usuario. "
    "Si el pedido corresponde a una accion disponible (abrir/cerrar apps, escritorios, volumen, "
    "musica, bloquear, captura, buscar en la web, mirar la pantalla, controlar el navegador), "
    "LLAMA la herramienta adecuada con sus datos. "
    "Si es una pregunta o charla, responde vos mismo en 1 o 2 frases. "
    "Si no podes hacer algo, deci simplemente 'No pude hacer eso' o 'No entendi el comando', en UNA frase. "
    "NUNCA inventes excusas como que no tenes acceso a la pantalla o al sistema (SI tenes control). "
    "Siempre breve, sin markdown ni emojis, porque se lee en voz alta."
)


def _limpiar(texto):
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    texto = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
                   r"\U00002190-\U000021FF\U00002B00-\U00002BFF]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def responder(texto):
    """Devuelve la respuesta del LLM (str) o None si falla."""
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": MODELO,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": texto},
            ],
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 220},
        }, timeout=90)
        r.raise_for_status()
        contenido = _limpiar(r.json().get("message", {}).get("content", ""))
        return contenido or None
    except Exception as e:
        print("error LLM:", e, flush=True)
        return None


def _monitor_del_cursor(sct):
    import pyautogui
    x, y = pyautogui.position()
    for i, mon in enumerate(sct.monitors):
        if i == 0:
            continue
        if mon["left"] <= x < mon["left"] + mon["width"] and mon["top"] <= y < mon["top"] + mon["height"]:
            return i
    return 1


def _monitor_foreground(sct):
    """Monitor donde esta la VENTANA ACTIVA (mas robusto que el mouse)."""
    import ctypes
    from ctypes import wintypes
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        for i, mon in enumerate(sct.monitors):
            if i == 0:
                continue
            if mon["left"] <= cx < mon["left"] + mon["width"] and mon["top"] <= cy < mon["top"] + mon["height"]:
                return i
    except Exception:
        pass
    return None


def _monitor_objetivo(sct):
    """La ventana activa primero; si no, el mouse."""
    return _monitor_foreground(sct) or _monitor_del_cursor(sct)


def _captura_jpg(monitor=None):
    """Captura un monitor y devuelve JPEG en bytes (liviano). monitor=None -> donde esta el cursor."""
    import mss
    from PIL import Image
    with mss.MSS() as sct:
        try:
            idx = int(monitor)
        except (TypeError, ValueError):
            idx = _monitor_objetivo(sct)
        if not (1 <= idx < len(sct.monitors)):
            idx = _monitor_objetivo(sct)
        raw = sct.grab(sct.monitors[idx])
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    MAXW = 1280
    if img.width > MAXW:
        h = int(img.height * MAXW / img.width)
        img = img.resize((MAXW, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def ver_pantalla(pregunta, monitor=None):
    """Captura el monitor (el del cursor por defecto) y se lo manda a Gemini (nube). Reintenta si falla."""
    try:
        jpg = _captura_jpg(monitor)
    except Exception as e:
        print("error captura:", e, flush=True)
        return None
    import time as _t
    for intento in range(3):
        try:
            return _limpiar(analizar_gemini.responder_pantalla(jpg, pregunta)) or None
        except Exception as e:
            print(f"error vision (intento {intento+1}):", e, flush=True)
            _t.sleep(1.0)
    return None


def transformar_texto(instruccion, texto):
    """Aplica una instruccion (corregir/traducir/mejorar...) a un texto. Devuelve SOLO el resultado."""
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": MODELO,
            "messages": [
                {"role": "system", "content":
                    "Sos un editor de texto. Aplicas la instruccion al texto y devolves UNICAMENTE "
                    "el texto resultante: sin comillas, sin explicaciones, sin markdown, sin prefijos."},
                {"role": "user", "content": f"Instruccion: {instruccion}\n\nTexto:\n{texto}"},
            ],
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0.3, "num_predict": 1000},
        }, timeout=90)
        r.raise_for_status()
        out = r.json().get("message", {}).get("content", "")
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
        out = re.sub(r'^["“”\']+|["“”\']+$', "", out).strip()   # comillas envolventes
        return out or None
    except Exception as e:
        print("error transformar:", e, flush=True)
        return None


def clic_visual(descripcion):
    """Captura el monitor del cursor, le pide a Gemini donde esta el elemento y hace clic ahi."""
    import io
    import mss
    import pyautogui
    from PIL import Image
    try:
        with mss.MSS() as sct:
            idx = _monitor_objetivo(sct)
            mon = sct.monitors[idx]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
        if img.width > 1600:
            img = img.resize((1600, int(img.height * 1600 / img.width)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        box = analizar_gemini.ubicar_elemento(buf.getvalue(), descripcion)
        if not box:
            return "No encontre eso en la pantalla."
        ymin, xmin, ymax, xmax = box
        fx = (xmin + xmax) / 2 / 1000.0     # 0-1 (independiente de resolucion/DPI)
        fy = (ymin + ymax) / 2 / 1000.0
        sx = int(mon["left"] + fx * mon["width"])
        sy = int(mon["top"] + fy * mon["height"])
        pyautogui.click(sx, sy)
        return "Listo, hice clic."
    except Exception as e:
        print("error clic_visual:", e, flush=True)
        return "No pude hacer el clic."


def resumir_pagina(pregunta):
    """Lee la pagina abierta en el Chrome IA y la resume/responde con el modelo local."""
    try:
        from app.web import navegador
        titulo, texto = navegador.leer_pagina()
    except Exception:
        return "No pude leer la pagina. Fijate que este abierto el Chrome IA."
    if not (texto or "").strip():
        return "La pagina esta vacia o todavia no cargo."
    base = f"Pagina: {titulo}\n\nContenido:\n{texto[:5000]}\n\n"
    if pregunta:
        base += f"Responde breve (1-2 frases, para leer en voz): {pregunta}"
    else:
        base += "Resumi el contenido en 1-2 frases, para leer en voz."
    return responder(base) or "No pude resumir la pagina."


_historial = []      # memoria corta de la conversacion (ultimos turnos)
_MAX_HIST = 8


def _recordar(usuario, asistente):
    _historial.append({"role": "user", "content": usuario})
    if asistente:
        _historial.append({"role": "assistant", "content": asistente})
    del _historial[:-_MAX_HIST]     # dejar solo los ultimos


def olvidar():
    _historial.clear()


def agente(texto):
    """Tool-calling con MEMORIA: el LLM ve los turnos anteriores. Devuelve texto para hablar."""
    try:
        mensajes = [{"role": "system", "content": SYSTEM_AGENTE}] + list(_historial) + [{"role": "user", "content": texto}]
        r = requests.post(OLLAMA_URL, json={
            "model": MODELO,
            "messages": mensajes,
            "tools": acciones.TOOLS,
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0.2, "num_predict": 220},
        }, timeout=90)
        r.raise_for_status()
        msg = r.json().get("message", {})

        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            resultados = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                nombre = fn.get("name")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if nombre == "mirar_pantalla":                 # vision: la maneja el propio cerebro
                    resultados.append(ver_pantalla(args.get("pregunta", ""), args.get("monitor")))
                    continue
                if nombre == "web_leer":                        # leer/resumir la pagina web
                    resultados.append(resumir_pagina(args.get("pregunta", "")))
                    continue
                accion = acciones.DISPATCH.get(nombre)
                if accion:
                    try:
                        resultados.append(accion(args))
                    except Exception as e:
                        print(f"error ejecutando {nombre}:", e, flush=True)
            resultados = [x for x in resultados if x]
            if resultados:
                resp = " ".join(resultados)
                _recordar(texto, resp)
                return resp

        # sin herramienta -> respuesta conversacional
        resp = _limpiar(msg.get("content", "")) or None
        _recordar(texto, resp)
        return resp
    except Exception as e:
        print("error agente:", e, flush=True)
        return None


if __name__ == "__main__":
    import sys
    print(responder(" ".join(sys.argv[1:]) or "Hola, ¿cómo estás?"))
