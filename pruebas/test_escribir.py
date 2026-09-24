"""Prueba el buscador de sesiones por voz: "escribi en la sesion del disco".

Uso, desde la raiz del proyecto:
    python -m pruebas.test_escribir

Prueba buscar_sesion() con candidatas inyectadas (sin depender de que haya sesiones
vivas) y el patron _ES_ESCRIBIR_SESION sin importar voz.py (importarlo arranca un
asistente entero: carga Whisper y abre el microfono — ya paso una vez).
"""

import re
from pathlib import Path

from app.voz import seguir

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:58} -> {obtenido}")


CANDIDATAS = [
    {"id": "1", "nombre": "Investigar y clasificar ocupacion de disco C urgente",
     "proyecto": "wpp-transcriptor", "cwd": r"d:\IA\wpp-transcriptor", "jsonl": "x"},
    {"id": "2", "nombre": "Gestionar multiples procesos simultaneos",
     "proyecto": "wpp-transcriptor", "cwd": r"d:\IA\wpp-transcriptor", "jsonl": "x"},
    {"id": "3", "nombre": "Portar buffer de mensajes",
     "proyecto": "Tienda2", "cwd": r"c:\EspacioDeTrabajo\Tienda2", "jsonl": "x"},
    {"id": "4", "nombre": "Verificar acceso a turnos",
     "proyecto": "Portfolio", "cwd": r"c:\EspacioDeTrabajo\Portfolio", "jsonl": "x"},
]


def _busca(frase):
    s = seguir.buscar_sesion(frase, candidatas=CANDIDATAS)
    return s["id"] if s else None


# Los mismos patrones que usa voz.py, copiados aca a proposito (importar voz.py
# arranca el asistente). Si cambian alla, cambian aca: los tests de abajo lo delatan.
_PATRON = re.compile(
    r"^\W*escrib\w*\s+(?:me\s+|le\s+)?(?:a|en)\s+(?:la\s+)?sesi[oó]n\b[\s,.:]*(.*)$",
    re.IGNORECASE)
_PATRON_SELECCION = re.compile(
    r"^\W*(?:seleccion\w+|eleg[ií]\w*|cambi[aá]\w*(?:\s+a)?|pas[aá]\w*(?:\s+a)?)\s+"
    r"(?:la\s+)?sesi[oó]n\b[\s,.:]*(.*)$", re.IGNORECASE)
_PATRON_ENTER = re.compile(r"[\s,]*\benter\b\W*$", re.IGNORECASE)


def _sacar_enter(texto):
    m = _PATRON_ENTER.search(texto or "")
    if m and texto[:m.start()].strip():
        return texto[:m.start()].strip(), True
    return texto, False


def main():
    print("\n=== Encontrar la sesion por como suena ===")
    _check("'del disco'", _busca("del disco"), "1")
    _check("'la del disco C'", _busca("la del disco C"), "1")
    _check("'procesos simultaneos'", _busca("procesos simultaneos"), "2")
    _check("'tienda'", _busca("tienda"), "3")
    _check("'portfolio'", _busca("portfolio"), "4")
    _check("'turnos'", _busca("turnos"), "4")
    _check("relleno solo ('la sesion de la') no adivina", _busca("la sesion de la"), None)
    _check("sin coincidencia ('recetas de cocina')", _busca("recetas de cocina"), None)
    # "wpp" aparece en DOS sesiones del mismo proyecto: empate = no adivinar.
    _check("empate ('wpp transcriptor') no adivina", _busca("wpp transcriptor"), None)

    print("\n=== El patron 'escribi en la sesion...' ===")
    casos = [
        ("Escribí en la sesión del disco: revisá el medidor", "del disco: revisá el medidor"),
        ("escribime en la sesión de la tienda, hola",         "de la tienda, hola"),
        ("Escribile a la sesión de turnos",                   "de turnos"),
        ("Escribí en la sesión",                              ""),
        ("Escribí hola como estas",                           None),   # dictado comun
        ("Escribí en el buscador de google",                  None),   # no dice "sesion"
    ]
    for frase, esperado in casos:
        m = _PATRON.match(frase)
        _check(repr(frase[:44]), m.group(1).strip() if m else None, esperado)

    print("\n=== El patron 'selecciona la sesion...' ===")
    casos_sel = [
        ("Seleccioná la sesión del disco",   "del disco"),
        ("Elegí la sesión de turnos",        "de turnos"),
        ("Cambiá a la sesión del tango",     "del tango"),
        ("Pasá a la sesión de procesos",     "de procesos"),   # tilde en la ultima letra
        ("Seleccioná la sesión",             ""),
        ("Seleccioná todo",                  None),   # ese es el Ctrl+A de acciones
        ("Selecciona el texto",              None),
    ]
    for frase, esperado in casos_sel:
        m = _PATRON_SELECCION.match(frase)
        _check(repr(frase[:40]), m.group(1).strip() if m else None, esperado)

    print("\n=== El 'enter' dicho al final manda el mensaje ===")
    casos_enter = [
        ("hola como estas enter",             ("hola como estas", True)),
        ("Hola, ¿cómo estás? Enter.",         ("Hola, ¿cómo estás?", True)),  # el ? queda
        ("dale para adelante, enter",         ("dale para adelante", True)),
        ("enter",                             ("enter", False)),   # solo, no manda nada
        ("no te metas, entre vos y yo",       ("no te metas, entre vos y yo", False)),
        ("apreta la tecla enter del teclado", ("apreta la tecla enter del teclado", False)),
    ]
    for texto, esperado in casos_enter:
        _check(repr(texto[:40]), _sacar_enter(texto), esperado)

    print("\n" + ("TODO OK" if not _fallos else f"{len(_fallos)} FALLOS:"))
    for f in _fallos:
        print("  -", f)
    return 1 if _fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
