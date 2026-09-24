"""Una pregunta con opciones DE VERDAD, contra una sesión real de Claude Code.

Es la prueba que faltaba: `probar_pregunta_sesion.py` mide el protocolo con procesos
de mentira, y `ver_pregunta_sesion.py` / `ver_pregunta_movil.py` miden la pantalla con
la respuesta del servidor interceptada. Acá se arranca `claude` posta, se lo hace
frenar con AskUserQuestion, se lee la pregunta como la lee la pantalla y se le
contesta eligiendo una opción — punta a punta.

⚠ GASTA TOKENS (un turno corto con haiku) y arranca una sesión nueva. No es para
correr todos los días: es para cuando se toca el camino de la pregunta.

Correr con:  python -m pruebas.probar_pregunta_real
"""
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.rutas import RAIZ
from app.voz import sesiones_movil as sm

fallas = []
PEDIDO = ("Usá la herramienta AskUserQuestion para preguntarme con qué color pinto "
          "la pared, con dos opciones: Azul y Verde. No hagas nada más.")


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    cwd = str(RAIZ)
    salida = {}

    def turno():
        try:
            salida["r"] = sm.mandar(cwd, "", PEDIDO, modelo="haiku")
        except Exception as e:
            salida["error"] = e

    print("arrancando una sesión de verdad (tarda ~20 s)...")
    hilo = threading.Thread(target=turno, daemon=True)
    hilo.start()

    # La pantalla pregunta cada 3 s; acá se hace lo mismo hasta que aparezca.
    preg, t0 = None, time.time()
    while time.time() - t0 < 180:
        preg = sm.pregunta_de(cwd, "")
        if preg:
            break
        if not hilo.is_alive():
            break
        time.sleep(2)

    revisar("la sesión frenó a preguntar", bool(preg), True)
    if not preg:
        print("\nno hubo pregunta. Lo que contestó:", salida)
        sys.exit(1)

    q = preg["preguntas"][0]
    print(f"\n   preguntó: {q['pregunta']!r}")
    print(f"   opciones: {[o['etiqueta'] for o in q['opciones']]}\n")
    revisar("trae la pregunta escrita", bool(q["pregunta"].strip()), True)
    revisar("trae dos opciones para elegir", len(q["opciones"]), 2)
    revisar("y viene con hora, para saber si es nueva", isinstance(preg["hora"], float), True)

    # Elegir una opción, igual que tocando el botón en la pantalla.
    elegida = q["opciones"][0]["etiqueta"]
    print(f"   eligiendo {elegida!r} ...")
    revisar("contestarla devuelve que había algo que contestar",
            sm.responder_pregunta(cwd, "", {q["pregunta"]: elegida}), True)
    revisar("y deja de estar pendiente", sm.pregunta_de(cwd, ""), None)

    hilo.join(timeout=180)
    respuesta, sid = (salida.get("r") or ("", ""))
    revisar("el turno terminó y siguió solo", bool(respuesta), True)
    revisar("y quedó una sesión de verdad", bool(sid), True)
    print(f"\n   siguió y contestó: {(respuesta or '')[:200]}")
    print(f"   sesión: {sid}")
    # Que de verdad se haya quedado con lo que elegimos, no con la otra.
    revisar("la respuesta habla de lo que elegimos",
            elegida.lower() in (respuesta or "").lower(), True)

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien: la pregunta con opciones anda punta a punta")


if __name__ == "__main__":
    main()
