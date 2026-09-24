"""
Agente de navegador con browser-use (Gemini) conectado por CDP al Chrome IA.

Reemplaza el clic casero: en vez de adivinar selectores/pestania, el LLM lee la
pagina (DOM) y decide que clickear. Mucho mas robusto para "poné el tercer video",
"reproducí Tres Acordes", "abrí el primer resultado", etc.

- Se conecta al Chrome IA YA ABIERTO (puerto 9222): mantiene tus sesiones y pestañas.
- DOM-only (use_vision=False): mas rapido y NO manda capturas de pantalla a la nube.
- Nunca cierra tu navegador (keep_alive).
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)                 # Avast rompe el SSL de Python
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")  # sin telemetria
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

import truststore
truststore.inject_into_ssl()                          # usar el cert store de Windows

import asyncio
from pathlib import Path
from dotenv import load_dotenv

from app.rutas import ENV

load_dotenv(ENV)

from browser_use import Agent, ChatGoogle, Browser

CDP = "http://localhost:9222"
MODELO = "gemini-2.5-flash"
_API_KEY = os.environ.get("GEMINI_API_KEY")


def _tarea(instruccion):
    return (
        "Estas conectado al navegador que el usuario tiene abierto. "
        "Trabaja sobre la pestaña que el usuario esta mirando (normalmente la de YouTube "
        "u otra con contenido, NO una pestaña en blanco ni la de Google si hay otra mejor). "
        f"El usuario pidio por voz: \"{instruccion}\". "
        "Si se refiere a un video, una cancion, una pelicula o un resultado, HACE CLIC para "
        "abrirlo/reproducirlo. Respeta el orden si lo menciona (primer, segundo, tercero = de "
        "arriba hacia abajo). Si menciona un titulo o nombre, busca el que mas se parezca. "
        "No abras pestañas nuevas ni cierres nada salvo que el pedido lo diga. "
        "Haces SOLO lo que pidio y despues terminas. "
        "Respondes en UNA frase corta en español rioplatense, para leer en voz alta."
    )


async def _correr(instruccion, max_steps=8):
    if not _API_KEY:
        return "Falta la clave de Gemini."
    llm = ChatGoogle(model=MODELO, api_key=_API_KEY, temperature=0.0)
    browser = Browser(cdp_url=CDP, keep_alive=True)     # conecta al Chrome IA; NO lo cierra
    agent = Agent(
        task=_tarea(instruccion),
        llm=llm,
        browser=browser,
        use_vision=False,          # DOM-only: mas rapido y privado
        flash_mode=True,           # sin "pensar" largo: mas rapido
        use_judge=False,
        enable_planning=False,
        max_actions_per_step=4,
        enable_signal_handler=False,   # se llama desde un hilo worker (no el principal)
    )
    try:
        hist = await agent.run(max_steps=max_steps)      # keep_alive=True -> no cierra el navegador
    finally:
        try:
            await browser.stop()                         # desconecta el CDP sin matar tu Chrome
        except Exception:
            pass
    res, ok = "", False
    try:
        res = (hist.final_result() or "").strip()
        errores = hist.has_errors()
        if errores:
            print("browser-use errores:", hist.errors(), flush=True)
        try:
            hizo_click = any("click" in (a or "").lower() for a in (hist.action_names() or []))
        except Exception:
            hizo_click = False
        ok = bool(hist.is_done()) or (not errores and hizo_click)
    except Exception as e:
        print("browser-use sin resultado:", e, flush=True)
    if res:
        return res
    return "Listo." if ok else "No pude hacerlo en el navegador."


def ejecutar_tarea(instruccion, max_steps=8):
    """Sincrono (para llamar desde el hilo de voz). Devuelve una frase corta para TTS."""
    try:
        return asyncio.run(_correr(instruccion, max_steps))
    except Exception as e:
        print("error agente_web:", e, flush=True)
        return "No pude controlar el navegador."


if __name__ == "__main__":
    import sys
    tarea = " ".join(sys.argv[1:]) or "decime en una frase que video esta primero en la pagina, no hagas clic en nada"
    print(ejecutar_tarea(tarea))
