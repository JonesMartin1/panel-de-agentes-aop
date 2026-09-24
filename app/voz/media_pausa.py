"""Pausa la musica o el video mientras hablas con el asistente, y lo reanuda despues.

Pedido del 2026-08-11: que la musica o el video se pausen cuando hablas con Venus o
Laura Y cuando ellas te hablan (comandos, lecturas), y que al terminar todo vuelva a
sonar solo.

Usa las sesiones de medios de Windows (GlobalSystemMediaTransportControls, via el
paquete `winsdk`), que es EL mecanismo correcto: Spotify, Chrome/YouTube, Edge y VLC
se registran ahi con su estado real. Eso permite dos cosas que el toggle de la tecla
play/pause no puede: pausar SOLO lo que esta sonando (un toggle a ciegas le daria
play a algo que estaba quieto) y reanudar SOLO lo que pausamos nosotros (si vos ya
lo habias pausado a mano, no lo tocamos).

winsdk es async: cada llamada corre su propio bucle con asyncio.run. Tarda 50-200 ms,
por eso esto se usa desde el hilo vigilante de voz.py y nunca desde el callback del
microfono.

Instalacion (ya hecha, documentada por si se rearma el entorno):
    pip install winsdk --trusted-host pypi.org --trusted-host files.pythonhosted.org
"""

import asyncio

_REPRODUCIENDO = 4      # PlaybackStatus.PLAYING del enum de Windows


async def _sesiones():
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Manager)
    manager = await _Manager.request_async()
    return list(manager.get_sessions())


async def _pausar_async():
    pausadas = []
    for s in await _sesiones():
        try:
            if s.get_playback_info().playback_status == _REPRODUCIENDO:
                if await s.try_pause_async():
                    pausadas.append(s.source_app_user_model_id)
        except Exception:
            continue
    return pausadas


async def _reanudar_async(apps):
    for s in await _sesiones():
        try:
            if (s.source_app_user_model_id in apps
                    and s.get_playback_info().playback_status != _REPRODUCIENDO):
                await s.try_play_async()
        except Exception:
            continue


async def _dar_play_async():
    """Play al reproductor 'actual' de Windows (el del cartelito de volumen), este
    pausado por quien este. Si no hay actual, el primero pausado que encuentre."""
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Manager)
    manager = await _Manager.request_async()
    actual = manager.get_current_session()
    vistos = set()
    candidatas = ([actual] if actual else []) + list(manager.get_sessions())
    for s in candidatas:
        if s is None:
            continue
        app = s.source_app_user_model_id
        if app in vistos:
            continue
        vistos.add(app)
        try:
            if s.get_playback_info().playback_status != _REPRODUCIENDO:
                if await s.try_play_async():
                    return app
        except Exception:
            continue
    return None


def dar_play():
    """El "Venus, play": arranca el reproductor actual aunque NO lo hayamos pausado
    nosotros (vos lo pausaste a mano ayer, hoy decis play, y tiene que sonar)."""
    try:
        app = asyncio.run(_dar_play_async())
    except Exception as e:
        print("media: no pude dar play:", e, flush=True)
        return None
    if app:
        dar_gracia()
    return app


def pausar():
    """Pausa lo que este SONANDO. Devuelve las apps pausadas (para reanudar solo esas)."""
    try:
        return asyncio.run(_pausar_async())
    except Exception as e:
        print("media: no pude pausar:", e, flush=True)
        return []


def reanudar(apps):
    """Vuelve a darle play SOLO a lo que pausamos nosotros."""
    if not apps:
        return
    try:
        asyncio.run(_reanudar_async(set(apps)))
    except Exception as e:
        print("media: no pude reanudar:", e, flush=True)


# --- Los dos bolsillos: pausa POR CHARLA y pausa TUYA -----------------------------
# La distincion importa por una trampa concreta: cuando decis "Venus, pausa", el
# vigilante de la charla YA pauso la musica para escucharte — y 6 segundos despues
# la iba a reanudar, DESHACIENDO tu orden. Por eso: lo pausado por charla vuelve
# solo al callarse todos; lo pausado por VOS no vuelve hasta que digas "reproduci".
import threading as _threading
import time as _time

_lock = _threading.Lock()
_por_charla = set()       # lo que pauso el vigilante mientras alguien hablaba
_manual = set()           # lo que pausaste vos con "pausa"

# Periodo de GRACIA: si acabas de pedir musica ("play", "reproduci", "pone tal
# cancion"), el vigilante de la charla NO pausa por unos segundos. Sin esto, la
# cancion que pediste arrancaba y el vigilante te la pausaba al medio segundo
# porque "habia actividad" (Venus confirmando y la ventana de repregunta).
_gracia_hasta = 0.0


def dar_gracia(segundos=15.0):
    global _gracia_hasta
    _gracia_hasta = _time.time() + segundos


def en_gracia():
    return _time.time() < _gracia_hasta


def pausar_por_charla():
    """El vigilante, al arrancar una charla. Devuelve cuantas pauso."""
    nuevas = pausar()
    with _lock:
        _por_charla.update(nuevas)
    return nuevas


def reanudar_por_charla():
    """El vigilante, cuando todos se callaron. NO toca lo que pausaste vos."""
    with _lock:
        apps = set(_por_charla)
        _por_charla.clear()
    reanudar(apps)
    return apps


def hay_por_charla():
    """True si hay algo pausado POR la charla, o sea: estabas escuchando algo de
    verdad cuando arrancaste a hablar. Lo que pausaste VOS a mano no cuenta —
    eso lo querés quieto."""
    with _lock:
        return bool(_por_charla)


def devolver_mientras_piensa():
    """Mientras Laura piensa te devolvemos lo que estabas escuchando, en vez de la
    musiquita de espera (pedido de Martin, 2026-08-16).

    NO se olvida de que es "de la charla": sigue anotado, asi que cuando ella
    arranca a hablar se vuelve a pausar y al final de todo se reanuda como siempre.
    Devuelve False si no habia nada sonando — ahi va la musiquita."""
    with _lock:
        apps = set(_por_charla)
    if not apps:
        return False
    reanudar(apps)
    return True


def pausar_manual():
    """Tu "Venus, pausa": pausa todo lo que suena Y se queda pausado hasta que
    lo pidas. Lo que el vigilante habia pausado por la charla pasa a ser tuyo
    (para vos ESO era lo que estaba sonando). True si quedo algo pausado."""
    nuevas = pausar()
    with _lock:
        _manual.update(nuevas)
        _manual.update(_por_charla)   # adopta la pausa de la charla: ahora es tuya
        _por_charla.clear()
        return bool(_manual)


def reanudar_manual():
    """Tu "Venus, reproduci": vuelve TODO lo pausado, tuyo y de la charla."""
    with _lock:
        apps = _manual | _por_charla
        _manual.clear()
        _por_charla.clear()
    if not apps:
        return False
    reanudar(apps)
    dar_gracia()              # que el vigilante no pause lo que acabas de pedir
    return True


if __name__ == "__main__":
    import sys, time
    if "--probar" in sys.argv:
        p = pausar()
        print("pausadas:", p or "(nada estaba sonando)")
        if p:
            time.sleep(3)
            reanudar(p)
            print("reanudadas")
    else:
        async def _ver():
            for s in await _sesiones():
                info = s.get_playback_info()
                estado = "SONANDO" if info.playback_status == _REPRODUCIENDO else "quieta"
                print(f"  {estado:8} {s.source_app_user_model_id}")
        asyncio.run(_ver())
