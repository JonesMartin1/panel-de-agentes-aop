"""Prueba el seguidor de sesiones: que extrae, que ignora y cuando cierra un turno.

Uso, desde la raiz del proyecto:
    python -m pruebas.test_seguir

Escribe un .jsonl de mentira en el temp y lo sigue de verdad, como hara voz.py.
NO toca ninguna sesion real ni levanta ningun servicio.
"""

import json
import time
import tempfile
from pathlib import Path

from app.voz import seguir

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:56} -> {obtenido!r}")


def _linea(tipo, texto=None, **extra):
    """Arma una linea del jsonl como las escribe Claude Code (lo minimo que se usa)."""
    if tipo == "asistente":
        d = {"type": "assistant",
             "message": {"model": "claude-sonnet-5",
                         "content": [{"type": "text", "text": texto}]}}
    elif tipo == "usuario":
        d = {"type": "user", "message": {"role": "user",
             "content": [{"type": "text", "text": texto or "hola"}]}}
    elif tipo == "herramienta":
        d = {"type": "assistant",
             "message": {"model": "claude-sonnet-5",
                         "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}
    elif tipo == "resultado":     # los resultados de herramienta llegan como type=user
        d = {"type": "user", "message": {"role": "user",
             "content": [{"type": "tool_result", "content": "salida"}]}}
    elif tipo == "pensando":
        d = {"type": "assistant",
             "message": {"model": "claude-sonnet-5",
                         "content": [{"type": "thinking", "thinking": texto}]}}
    else:
        raise ValueError(tipo)
    d.update(extra)
    return json.dumps(d) + "\n"


def main():
    ruta = Path(tempfile.gettempdir()) / "test_seguir_sesion.jsonl"

    # Historia previa: el seguidor arranca desde el FINAL, esto no debe leerse nunca.
    ruta.write_text(_linea("asistente", "esto es viejo y no se lee"), encoding="utf-8")

    quietud_original = seguir.QUIETUD_SEG
    seguir.QUIETUD_SEG = 0.3          # para no esperar 5 segundos por caso
    try:
        s = seguir.Seguidor(ruta)

        print("\n=== Arranca desde el final ===")
        _check("sin escribir nada, no hay novedades", s.novedades(), [])

        print("\n=== Un turno con herramientas en el medio ===")
        with ruta.open("a", encoding="utf-8") as f:
            f.write(_linea("asistente", "Voy a mirar el archivo."))
            f.write(_linea("herramienta"))
            f.write(_linea("resultado"))
            f.write(_linea("pensando", "esto es interno"))
            f.write(_linea("asistente", "Listo, ya lo arregle."))
        _check("mientras escribe, todavia nada", s.novedades(), [])
        time.sleep(seguir.QUIETUD_SEG + 0.2)
        _check("con el archivo quieto, sale el texto junto",
               s.novedades(), ["Voy a mirar el archivo.\nListo, ya lo arregle."])

        print("\n=== Tu proximo mensaje cierra el turno anterior ===")
        with ruta.open("a", encoding="utf-8") as f:
            f.write(_linea("asistente", "Segunda respuesta."))
            f.write(_linea("usuario", "gracias"))
        _check("el mensaje del usuario la despacha al instante",
               s.novedades(), ["Segunda respuesta."])

        print("\n=== Lo que NO se lee ===")
        with ruta.open("a", encoding="utf-8") as f:
            f.write(_linea("asistente", "soy un subagente", isSidechain=True))
            f.write(_linea("pensando", "rumiando"))
            f.write(_linea("herramienta"))
            f.write(json.dumps({"type": "assistant",
                                "message": {"model": "<synthetic>",
                                            "content": [{"type": "text",
                                                         "text": "error sintetico"}]}}) + "\n")
        time.sleep(seguir.QUIETUD_SEG + 0.2)
        _check("subagentes, pensamiento, herramientas y sinteticos", s.novedades(), [])

        print("\n=== Linea que llega partida en dos escrituras ===")
        entera = _linea("asistente", "Llegue entera aunque me escribieron en dos partes.")
        with ruta.open("a", encoding="utf-8") as f:
            f.write(entera[:40])
        s.novedades()                     # lee la mitad: debe guardarla sin romperse
        with ruta.open("a", encoding="utf-8") as f:
            f.write(entera[40:])
        # La linea completa recien la VE en la proxima llamada, y ahi arranca su
        # quietud: hace falta una llamada que la junte y otra, despues de la espera,
        # que la despache. Es exactamente el ciclo de 1 s de voz.py.
        s.novedades()
        time.sleep(seguir.QUIETUD_SEG + 0.2)
        _check("se rearma con la segunda mitad", s.novedades(),
               ["Llegue entera aunque me escribieron en dos partes."])
    finally:
        seguir.QUIETUD_SEG = quietud_original
        try:
            ruta.unlink()
        except OSError:
            pass

    print("\n" + ("TODO OK" if not _fallos else f"{len(_fallos)} FALLOS:"))
    for f in _fallos:
        print("  -", f)
    return 1 if _fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
