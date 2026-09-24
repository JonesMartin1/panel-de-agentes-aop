"""
Ruteo del comando "Venus, WhatsApp" (y que no pise a los demás).

Correr con:  python -m pruebas.test_ruteo_whatsapp

NO ejecuta los handlers (no abre nada): solo verifica en qué comando cae cada
frase. El orden de los patrones en acciones.COMANDOS está elegido a mano —
"poné whatsapp" tiene que abrir WhatsApp y no buscarlo como canción en Spotify,
y "mandale un whatsapp a juan" tiene que seguir yendo al LLM/Laura.
"""

import re

from app.voz import acciones

CASOS = [
    # (frase, handler esperado; None = ningún comando fijo, va al LLM/Laura)
    ("WhatsApp.", "traer_whatsapp"),
    ("whatsapp", "traer_whatsapp"),
    ("El WhatsApp, por favor", "traer_whatsapp"),
    ("dale, whatsapp", "traer_whatsapp"),
    ("abrí whatsapp", "traer_whatsapp"),
    ("abrime el whatsapp", "traer_whatsapp"),
    ("traeme el whatsapp", "traer_whatsapp"),
    ("poné whatsapp", "traer_whatsapp"),
    ("mostrame el whatsapp", "traer_whatsapp"),
    ("dame el whatsapp", "traer_whatsapp"),
    ("podés traerme el whatsapp", "traer_whatsapp"),
    ("whats app", "traer_whatsapp"),        # Whisper a veces lo separa
    ("wasap", "traer_whatsapp"),            # ...o lo escribe fonético
    # "chat" es sinónimo de WhatsApp (pedido 2026-08-11): mismo comando.
    ("chat", "traer_whatsapp"),
    ("Chat.", "traer_whatsapp"),
    ("el chat, por favor", "traer_whatsapp"),
    ("abrí el chat", "traer_whatsapp"),
    ("traeme el chat", "traer_whatsapp"),
    ("poné el chat", "traer_whatsapp"),
    ("chad", "traer_whatsapp"),             # Whisper suele escribir así el "chat"
    # ...pero ChatGPT y la chatarra no son WhatsApp.
    ("abrí chat gpt", "abrir_app"),
    ("abrí chatgpt", "abrir_app"),
    ("chatarra", None),
    # Regresiones: nada de esto puede caer en traer_whatsapp.
    ("abrí chrome", "abrir_app"),
    ("abrí spotify", "abrir_app"),
    ("poné bring me to life", "poner_musica"),
    ("poné spotify", "poner_musica"),
    ("pausa", "media_playpause"),
    ("seguí", "media_playpause"),
    ("escritorio dos", "ir_escritorio"),
    ("2", "ir_escritorio"),
    ("borra la última palabra", "borrar_palabra"),
    ("borra todo", "borrar_texto"),
    ("qué hora es", "hora"),
    ("copiá", "copiar_seleccion"),
    ("dejá de leer", "dejar_de_leer"),
    # Hablar DE WhatsApp no es pedir la ventana: eso es tarea para Laura.
    ("mandale un whatsapp a juan", None),
    ("decile a laura que me mande un whatsapp", None),
    ("escribile un whatsapp a mamá", None),
    ("mandale un chat a juan", None),
]


def ruteo(texto):
    t = acciones._norm(texto)
    for patron, fn in acciones.COMANDOS:
        if re.search(patron, t):
            return fn.__name__
    return None


def main():
    fallos = 0
    for frase, esperado in CASOS:
        real = ruteo(frase)
        if real != esperado:
            fallos += 1
            print(f"FALLO  {frase!r} -> {real}  (esperaba {esperado})")
    print(f"{len(CASOS) - fallos}/{len(CASOS)} casos OK")
    return fallos


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
