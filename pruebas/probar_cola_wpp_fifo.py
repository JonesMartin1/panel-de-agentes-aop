"""Regresion: los audios de Laura conservan el orden de llegada antes de Whisper."""

import ast
import threading
import time
from pathlib import Path


RUTA = Path(__file__).resolve().parents[1] / "app" / "ingesta" / "webhook_wasender.py"


def _cargar_cola():
    arbol = ast.parse(RUTA.read_text(encoding="utf-8"))
    nombres = {"_reservar_turno_media_wpp", "_procesar_en_turno_media_wpp"}
    funciones = [
        nodo for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef) and nodo.name in nombres
    ]
    espacio = {
        "_MEDIA_WPP_COND": threading.Condition(),
        "_MEDIA_WPP_RESERVADOS": 0,
        "_MEDIA_WPP_ACTUAL": 0,
    }
    exec(compile(ast.Module(body=funciones, type_ignores=[]), str(RUTA), "exec"), espacio)
    return espacio


def main():
    espacio = _cargar_cola()
    reservar = espacio["_reservar_turno_media_wpp"]
    procesar = espacio["_procesar_en_turno_media_wpp"]
    turnos = [reservar() for _ in range(4)]
    assert turnos == [0, 1, 2, 3], turnos

    candado = threading.Lock()
    activos = 0
    max_activos = 0
    orden = []

    def trabajo(numero, falla=False):
        def ejecutar():
            nonlocal activos, max_activos
            with candado:
                activos += 1
                max_activos = max(max_activos, activos)
                orden.append(numero)
            time.sleep(0.04)
            with candado:
                activos -= 1
            if falla:
                raise RuntimeError("falla esperada")
        try:
            procesar(numero, ejecutar)
        except RuntimeError:
            pass

    # Arrancan deliberadamente al reves: manda el numero de llegada, no el azar
    # con que Windows les dio un hilo. El turno 1 falla y aun asi libera al 2.
    hilos = [
        threading.Thread(target=trabajo, args=(turno, turno == 1))
        for turno in reversed(turnos)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=2)
        assert not hilo.is_alive(), "la fila quedo trabada"

    assert orden == [0, 1, 2, 3], orden
    assert max_activos == 1, f"hubo {max_activos} trabajos simultaneos"

    codigo = RUTA.read_text(encoding="utf-8")
    bloque = codigo[codigo.index("if _es_martin(remote_jid):"):
                    codigo.index("# ⭐ Un GRUPO autorizado")]
    assert bloque.index("_reservar_turno_media_wpp()") < bloque.index("asyncio.create_task")
    assert "_procesar_en_turno_media_wpp(" in bloque
    print("OK: WhatsApp reserva turnos al llegar y transcribe en FIFO, incluso si uno falla")


if __name__ == "__main__":
    main()
