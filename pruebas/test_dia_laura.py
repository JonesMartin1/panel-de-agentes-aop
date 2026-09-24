"""Prueba el "dia de Laura": el corte a las 13:00 y como se interpreta tu respuesta.

Uso, desde la raiz del proyecto:
    python -m pruebas.test_dia_laura

NO lanza Claude ni escribe claude_sesion.json: solo prueba la logica de decision.
Vale la pena mantenerlo porque el orden de los patrones es delicado y ya se
rompio dos veces mientras se escribia:
  - "no, continuemos" elegia sesion NUEVA (ganaba el "no")
  - "continua donde quedamos" pedia un RESUMEN (ganaba el "quedamos")
Los dos casos estan abajo. Si toca los patrones, corra esto antes de reiniciar.
"""

from datetime import datetime

from app.voz import claude_voz as cv

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:46} -> {obtenido}")


def _clasificar(texto):
    """El MISMO orden que responder_dia(), sin sus efectos. Si cambia alla, cambia aca."""
    t = cv._plano(texto)
    if cv._SIGUE_VERBO.search(t):
        return "sigue"
    if cv._RESUMEN.search(t):
        return "resumen"
    if cv._SIGUE_FUERTE.search(t):
        return "sigue"
    if cv._NUEVA_FUERTE.search(t) or cv._NO_SUELTO.match(t):
        return "nueva"
    if cv._SI_SUELTO.match(t):
        return "sigue"
    return "no-es-respuesta"


CASOS = [
    ("continuá con la anterior",           "sigue"),
    ("seguí con la sesión anterior",       "sigue"),
    ("dale, seguimos",                     "sigue"),
    ("la de ayer",                         "sigue"),
    ("volvé a la de ayer",                 "sigue"),
    ("dónde quedamos",                     "resumen"),  # preguntas para poder decidir
    ("continuá donde quedamos",            "sigue"),    # el verbo le gana al "quedamos"
    ("sí",                                 "sigue"),
    ("dale",                               "sigue"),
    ("no, continuemos",                    "sigue"),    # el "no" NO tiene que ganar
    ("empecemos un proyecto nuevo",        "nueva"),
    ("nueva",                              "nueva"),
    ("arranquemos de cero",                "nueva"),
    ("no",                                 "nueva"),
    ("sí, pero nueva",                     "nueva"),
    ("resumime la sesión anterior",        "resumen"),
    ("no me acuerdo de qué hablamos ayer", "resumen"),
    ("de qué hablamos ayer",               "resumen"),
    ("contame lo que hablamos ayer",       "resumen"),
    ("en qué quedamos",                    "resumen"),
    # Estos NO son respuestas al saludo: el enganche tiene que dejarlos pasar, o se
    # come los comandos de siempre cuando ignoras la pregunta del dia.
    ("poné música en Spotify",             "no-es-respuesta"),
    ("qué hora es",                        "no-es-respuesta"),
    ("abrí el chrome",                     "no-es-respuesta"),
]

# El comando SUELTO de arrancar de cero, el que anda en cualquier momento del dia
# (lo usa voz.py). Es a proposito UNA sola frase, pedido de Martin el 2026-08-14:
# antes bastaba con "olvida" y eso enganchaba con "olvidate de eso", una frase
# normal en el medio de una charla que te borraba la sesion entera sin avisar.
CASOS_NUEVA_SUELTA = [
    ("arranquemos una sesión nueva",       True),
    ("arrancá una sesión nueva",           True),
    ("arranquemos sesión nueva",           True),
    ("empecemos una nueva sesión",         True),
    ("iniciemos una sesión nueva",         True),
    ("arranquemos una sección nueva",      True),   # asi lo escribe Whisper a veces
    # Lo que ANTES borraba la sesion y ahora no tiene que hacer nada:
    ("olvidate de eso",                    False),
    ("olvidá lo que te dije recién",       False),
    ("empecemos de nuevo",                 False),
    ("borrá tu memoria",                   False),
    ("reiniciá la memoria",                False),
    ("nueva conversación",                 False),
    ("sesión nueva",                       False),  # sin el verbo no alcanza
    # Y lo que nunca tuvo que dispararlo:
    ("poné música en Spotify",             False),
    ("empecemos un proyecto nuevo",        False),  # eso vale SOLO al saludo del dia
]


def main():
    print(f"\n=== El corte a las {cv.CORTE_HORA}:00 ===")
    for hora, esperado in [(0, "2026-08-10"), (1, "2026-08-10"), (12, "2026-08-10"),
                           (13, "2026-08-11"), (14, "2026-08-11"), (23, "2026-08-11")]:
        ts = datetime(2026, 8, 11, hora, 30).timestamp()
        _check(f"11 de agosto {hora:02d}:30", cv._dia_de(ts), esperado)

    print("\n=== Contestar el saludo del dia ===")
    for texto, esperado in CASOS:
        _check(repr(texto), _clasificar(texto), esperado)

    print("\n=== Arrancar de cero a mano (comando suelto, todo el dia) ===")
    for texto, esperado in CASOS_NUEVA_SUELTA:
        _check(repr(texto), cv.pide_sesion_nueva(texto), esperado)

    print("\n=== Leer la charla de una sesion vieja (para resumirla) ===")
    ant = cv.sesion_anterior()
    if not ant:
        print("  (no hay sesion de un dia anterior todavia: nada que probar)")
    else:
        charla = cv._charla_de(ant["session_id"])
        _check(f"charla del {ant.get('dia')}", bool(charla), True)
        print(f"      {len(charla):,} caracteres  ~{len(charla) // 4:,} tokens")

    # El prompt del resumen LLEVA la charla adentro. Si ayer dijiste "de que hablamos",
    # el detector se dispara con su propio pedido: de ahi el crudo=True en resumen_de().
    prompt = cv.PROMPT_RESUMEN.format(dia="2026-08-10",
                                      charla="Yo: de que hablamos ayer\nVos: de nada")
    print("\n=== La recursion del resumen ===")
    _check("el prompt matchea el detector (por eso crudo=True)",
           bool(cv._RESUMEN.search(cv._plano(prompt))), True)

    # 2026-08-11: un mensaje de contexto de ~1900 caracteres por Telegram tenia de
    # pasada "lo que hablamos por voz lo sabes" (una relativa, no una pregunta). El
    # detector lo tomo como pedido de resumen y el mensaje real NUNCA llego a Laura:
    # se contesto con el resumen de OTRA sesion. Estas dos barreras (el "de" exigido
    # y el tope de largo) son lo que evita que se repita.
    print("\n=== El resumen suelto no se dispara con mensajes largos (2026-08-11) ===")

    def _es_pedido_suelto(texto):
        """La misma condicion que usa preguntar() para el resumen SUELTO."""
        return (len(texto) <= cv.RESUMEN_LARGO_MAX
                and bool(cv._RESUMEN.search(cv._plano(texto))))

    _check("'lo que hablamos' relativa, sola, NO dispara (falta el 'de')",
           bool(cv._RESUMEN.search(cv._plano("lo que hablamos por voz lo sabes"))), False)
    mensaje_contexto = (
        "Soy Martin. Esto es un mensaje de contexto, no un pedido. Es la MISMA "
        "conversacion en los dos casos, misma memoria: lo que hablamos por voz lo "
        "sabes si te escribo por aca, y viceversa. " + "Relleno de mas contexto. " * 20)
    _check("mensaje largo con 'lo que hablamos' de pasada -> no es pedido suelto",
           _es_pedido_suelto(mensaje_contexto), False)
    _check("la misma frase CORTA y con 'de' -> si es un pedido suelto",
           _es_pedido_suelto("de que hablamos?"), True)

    print("\n" + ("TODO OK" if not _fallos else f"{len(_fallos)} FALLOS:"))
    for f in _fallos:
        print("  -", f)
    return 1 if _fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
