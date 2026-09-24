"""Buzon entre el bot de Telegram y Laura (el Claude Code del asistente de voz).

Pedido del 2026-08-11: hablarle a Laura por Telegram desde el telefono, como si
fuera la charla de voz — misma sesion, misma memoria, mismos permisos.

Por que un buzon de archivos y no otra cosa: el proceso `claude` persistente (el
que tiene la conversacion en la memoria) vive DENTRO de voz.py. Si el bot abriera
su propio `claude --resume` sobre la misma sesion habria DOS procesos escribiendo
la misma charla y se bifurcaria en silencio: la Laura del telefono no sabria lo que
hablaste por voz cinco minutos antes. Aca hay UNA sola Laura: el bot deja la
pregunta en un archivo, voz.py la atiende con el proceso de siempre y deja la
respuesta en otro. Mismo patron que escribir_en.json / pausa_escucha.flag.

Protocolo (dos archivos en la raiz, ignorados por git):

  laura_pregunta.json  {"id", "texto", "ts"}   la escribe el bot; voz.py la BORRA
                                               al tomarla (el borrado es el "ya la
                                               agarre, estoy en eso")
  laura_respuesta.json {"id", "texto"}         la escribe voz.py; el bot la borra
                                               al leerla

El id evita respuestas fantasma: el bot solo acepta la respuesta cuyo id coincide
con su pregunta, asi una respuesta vieja de una corrida anterior no se cuela.
"""

import json
import time

from app.rutas import LAURA_PREGUNTA, LAURA_RESPUESTA

# Si voz.py no levanto la pregunta en este tiempo, no esta corriendo: su vigilante
# mira el buzon cada medio segundo, asi que 8 s es un monton hasta con la maquina
# ocupada. (El bot manda de a UNA pregunta por vez, asi que nunca hay cola aca.)
SIN_VOZ_SEG = 8.0

# Una pregunta que nadie levanto en este tiempo es de una corrida muerta del bot
# (el bot vivo se rinde a los SIN_VOZ_SEG y la borra el mismo). Contestarla seria
# gastarle un turno a Laura para hablarle a nadie.
PREGUNTA_VIEJA_SEG = 60.0


def _leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return None


# --- Lado del bot (app/ingesta/bot_telegram.py) -----------------------------------

def dejar_pregunta(texto, origen="telegram", leer=False):
    """Deja la pregunta en el buzon. Devuelve el id para reclamar la respuesta.

    `origen` es "telegram" (el bot) o "panel" (el chat de la pagina 8750): cambia
    la marca de contexto que recibe Laura y el prefijo con el que queda en el log.
    Los dos clientes comparten este buzon a proposito -- hay UNA sola Laura -- pero
    por lo mismo mandan de a uno: el que escribe segundo pisaria al primero.

    `leer`: ademas de contestar por escrito, que lo diga por los parlantes (el
    interruptor 🔊 del chat del panel).
    """
    pid = str(time.time_ns())
    LAURA_PREGUNTA.write_text(
        json.dumps({"id": pid, "texto": texto, "ts": time.time(), "origen": origen,
                    "leer": bool(leer)}, ensure_ascii=False),
        encoding="utf-8")
    return pid


def pregunta_tomada():
    """True si voz.py ya levanto la pregunta (la saco del buzon)."""
    return not LAURA_PREGUNTA.exists()


def sacar_respuesta(pid):
    """La respuesta si ya esta (y la consume). None si todavia no llego."""
    d = _leer(LAURA_RESPUESTA)
    if not d or d.get("id") != pid:
        return None
    try:
        LAURA_RESPUESTA.unlink()
    except OSError:
        pass
    return d.get("texto") or ""


def abandonar():
    """El bot se rinde (voz apagada o timeout): limpia su pregunta si sigue ahi."""
    try:
        LAURA_PREGUNTA.unlink(missing_ok=True)
    except OSError:
        pass


# --- Lado de voz.py (_vigilar_telegram) --------------------------------------------

def sacar_pregunta():
    """La pregunta pendiente (y la consume), o None si no hay nada atendible."""
    d = _leer(LAURA_PREGUNTA)
    if not d or not d.get("texto"):
        return None
    if time.time() - d.get("ts", 0) > PREGUNTA_VIEJA_SEG:
        try:
            LAURA_PREGUNTA.unlink(missing_ok=True)
        except OSError:
            pass
        print("buzon: descarto una pregunta vieja (el bot que la dejo ya no espera)",
              flush=True)
        return None
    try:
        LAURA_PREGUNTA.unlink()
    except OSError:
        return None            # otro hilo se la llevo primero
    return d


def dejar_respuesta(pid, texto):
    LAURA_RESPUESTA.write_text(
        json.dumps({"id": pid, "texto": texto}, ensure_ascii=False), encoding="utf-8")
