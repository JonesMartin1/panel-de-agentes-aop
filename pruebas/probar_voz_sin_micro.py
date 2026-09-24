"""Prueba que bloquear el micro no apague WhatsApp/Telegram/panel.

Extrae solo la funcion de arranque mediante AST: no importa voz.py, no carga
Whisper, no abre la GPU y no toca ningun dispositivo real.
"""

from __future__ import annotations

import ast
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
VOZ = RAIZ / "app" / "voz" / "voz.py"


class Bandera:
    def __init__(self, existe: bool):
        self.existe = existe

    def exists(self) -> bool:
        return self.existe


def cargar_funcion():
    arbol = ast.parse(VOZ.read_text(encoding="utf-8"))
    funcion = next(
        nodo for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef)
        and nodo.name == "_abrir_stream_al_arrancar"
    )
    modulo = ast.Module(body=[funcion], type_ignores=[])
    ast.fix_missing_locations(modulo)
    espacio: dict[str, object] = {}
    exec(compile(modulo, str(VOZ), "exec"), espacio)
    return espacio


def main() -> None:
    espacio = cargar_funcion()
    abrir = espacio["_abrir_stream_al_arrancar"]
    llamadas: list[str] = []

    espacio.update(
        MIC_BLOQUEADO=Bandera(True),
        _evento=lambda texto: llamadas.append(f"evento:{texto}"),
        _abrir_stream_inicial=lambda: llamadas.append("abrir") or object(),
    )
    assert abrir() is None
    assert "abrir" not in llamadas
    assert any(x.startswith("evento:") for x in llamadas)

    llamadas.clear()
    stream = object()
    espacio.update(
        MIC_BLOQUEADO=Bandera(False),
        _abrir_stream_inicial=lambda: llamadas.append("abrir") or stream,
    )
    assert abrir() is stream
    assert llamadas == ["abrir"]
    print("OK: Laura arranca sin micro cuando la privacidad esta bloqueada")


if __name__ == "__main__":
    main()
