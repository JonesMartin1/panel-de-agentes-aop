"""Regresion: dos audios de WhatsApp no pueden pisarse en el buzon de Laura."""

import ast
import threading
import time
from pathlib import Path


RUTA = Path(__file__).resolve().parents[1] / "app" / "ingesta" / "webhook_wasender.py"


def _cargar_wrapper():
    arbol = ast.parse(RUTA.read_text(encoding="utf-8"))
    funcion = next(
        nodo for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
        and nodo.name == "_charla_con_laura"
    )
    espacio = {
        "_LAURA_WPP_LOCK": threading.Lock(),
        "_charla_con_laura_una": None,
    }
    exec(compile(ast.Module(body=[funcion], type_ignores=[]), str(RUTA), "exec"), espacio)
    return espacio


def main():
    espacio = _cargar_wrapper()
    candado = threading.Lock()
    activos = 0
    max_activos = 0
    recibidos = []

    def charla_falsa(jid, texto):
        nonlocal activos, max_activos
        with candado:
            activos += 1
            max_activos = max(max_activos, activos)
        time.sleep(0.08)
        recibidos.append((jid, texto))
        with candado:
            activos -= 1

    espacio["_charla_con_laura_una"] = charla_falsa
    hilos = [
        threading.Thread(target=espacio["_charla_con_laura"], args=("martin", "audio 1")),
        threading.Thread(target=espacio["_charla_con_laura"], args=("martin", "audio 2")),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert max_activos == 1, f"hubo {max_activos} charlas simultaneas"
    assert recibidos == [("martin", "audio 1"), ("martin", "audio 2")], recibidos
    print("OK: las charlas simultaneas de WhatsApp pasan por Laura de a una")


if __name__ == "__main__":
    main()
