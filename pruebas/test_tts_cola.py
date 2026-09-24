"""Prueba de regresion del productor/consumidor del TTS por trozos.

El bug que esto vigila (paso el 2026-08-10, dos veces):

  hablar() sintetiza en un hilo productor y reproduce en el consumidor, con una
  cola de tamano 2. El productor avisa que termino poniendo None. Si ese put se
  hacia de UN SOLO INTENTO y la cola estaba llena en ese momento, la marca se
  perdia en silencio y el consumidor quedaba esperando PARA SIEMPRE en get() con
  el _lock de hablar() tomado -> Laura no volvia a hablar nunca mas.

Se reproduce con >=3 trozos y un consumidor mas lento que el productor.

    python -m pruebas.test_tts_cola
"""

import queue
import threading
import time

MAXSIZE = 2
TIMEOUT_PUT = 0.2
TIMEOUT_GET = 0.3


def correr(n_trozos, seg_sintesis, seg_reproduccion, con_reintento, con_timeout_get,
           limite=10.0):
    """True si la simulacion TERMINO sola; False si quedo colgada.

    El caso colgado se mide desde AFUERA, en un hilo aparte: adentro no sirve
    chequear el reloj, porque cola.get() sin timeout no vuelve nunca y entonces
    nunca se llega a evaluar la guarda. (Primera version de esta prueba tenia
    justo ese defecto y se colgaba ella misma.)
    """
    fin = {}

    def correr_una():
        fin["ok"] = _simular(n_trozos, seg_sintesis, seg_reproduccion,
                             con_reintento, con_timeout_get)

    h = threading.Thread(target=correr_una, daemon=True)
    h.start()
    h.join(timeout=limite)
    return bool(fin.get("ok"))


def _simular(n_trozos, seg_sintesis, seg_reproduccion, con_reintento, con_timeout_get):
    """Simula una llamada a hablar(). Puede no volver nunca: por eso corre en un
    hilo daemon, para que el proceso pueda terminar igual."""
    cola = queue.Queue(maxsize=MAXSIZE)
    parar = threading.Event()

    def productor():
        for i in range(n_trozos):
            if parar.is_set():
                break
            time.sleep(seg_sintesis)                  # "sintetizar" el trozo
            entregado = False
            while not entregado and not parar.is_set():
                try:
                    cola.put(i, timeout=TIMEOUT_PUT)
                    entregado = True
                except queue.Full:
                    pass
            if not entregado:
                break
        # ---- la linea que causaba el cuelgue ----
        if con_reintento:
            entregado = False
            while not entregado and not parar.is_set():
                try:
                    cola.put(None, timeout=TIMEOUT_PUT)
                    entregado = True
                except queue.Full:
                    pass
        else:
            try:
                cola.put(None, timeout=0.5)           # un solo intento: se puede perder
            except queue.Full:
                pass

    hilo = threading.Thread(target=productor, daemon=True)
    hilo.start()

    reproducidos = 0
    try:
        while True:
            if con_timeout_get:
                try:
                    item = cola.get(timeout=TIMEOUT_GET)
                except queue.Empty:
                    if not hilo.is_alive():
                        break                         # cinturon de seguridad
                    continue
            else:
                item = cola.get()                     # a secas: puede colgar
            if item is None:
                break
            reproducidos += 1
            time.sleep(seg_reproduccion)              # "reproducir" el trozo
        return reproducidos == n_trozos
    finally:
        parar.set()
        try:
            while True:
                cola.get_nowait()
        except queue.Empty:
            pass
        hilo.join(timeout=2.0)


def main():
    # CLAVE para que el escenario sea fiel: la reproduccion de un trozo tiene que
    # durar MAS que el timeout del put de la marca (0,5 s en la version vieja). Si
    # no, el consumidor vacia la cola antes de que el put expire y el bug no aparece.
    # En la realidad cada trozo son 2-5 s de audio, asi que 0,7 s ya es conservador.
    # (Con 0,12 s la prueba pasaba siempre y daba confianza falsa.)
    SINTESIS, REPRODUCCION = 0.02, 0.7
    casos = [1, 2, 3, 4, 6]
    print(f"Escenario: sintesis {SINTESIS}s por trozo, reproduccion {REPRODUCCION}s "
          f"(mas que el timeout de 0,5s de la marca vieja).\n")

    print("--- ANTES (put de la marca sin reintento, get sin timeout)")
    fallos_antes = 0
    for n in casos:
        ok = correr(n, SINTESIS, REPRODUCCION, con_reintento=False,
                    con_timeout_get=False, limite=10.0)
        if not ok:
            fallos_antes += 1
        print(f"   {n} trozo(s): {'termino' if ok else 'COLGADO'}")

    print("\n--- AHORA (marca con reintento + get con timeout)")
    fallos_ahora = 0
    for n in casos:
        ok = correr(n, SINTESIS, REPRODUCCION, con_reintento=True,
                    con_timeout_get=True, limite=10.0)
        if not ok:
            fallos_ahora += 1
        print(f"   {n} trozo(s): {'termino' if ok else 'COLGADO'}")

    print()
    if fallos_antes == 0:
        print("ATENCION: la prueba no logro reproducir el bug viejo; revisar los tiempos.")
    else:
        print(f"El bug viejo se reprodujo en {fallos_antes} de {len(casos)} casos.")
    if fallos_ahora:
        print(f"FALLA: la version nueva colgo en {fallos_ahora} casos.")
        raise SystemExit(1)
    print("OK: la version nueva termina en todos los casos.")


if __name__ == "__main__":
    main()
