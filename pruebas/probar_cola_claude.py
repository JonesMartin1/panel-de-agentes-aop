"""El chat corrido en uno: una respuesta tardia NO puede contestar la pregunta siguiente.

El bug (2026-08-18): un turno de Laura se caia por timeout, su result llegaba
tarde y quedaba en la cola; la pregunta siguiente lo levantaba como si fuera su
respuesta y de ahi en adelante CADA pregunta del chat del panel aparecia
contestada con la respuesta de la anterior. El arreglo son dos mitades en
claude_voz.py: cada linea de la cola viaja con SU proceso (lo ajeno se ignora),
y antes de mandar un turno se vacia lo que haya quedado de turnos viejos.

Corre sin claude, sin micro y sin GPU: procesos de mentira y la cola de verdad.
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_cola_claude
"""
import json
import threading

from app.voz import claude_voz as cv


class Falso:
    """Un "proceso" con lo minimo que _turno_ya le pide: stdin y poll()."""

    def __init__(self):
        self.stdin = self

    def write(self, s):
        pass

    def flush(self):
        pass

    def poll(self):
        return None


def resultado(texto):
    return json.dumps({"type": "result", "result": texto, "num_turns": 1})


def en_un_rato(entradas, demora=0.2):
    """Mete lineas en la cola un rato despues, como un proceso que contesta."""
    def meter():
        for e in entradas:
            cv._cola.put(e)
    t = threading.Timer(demora, meter)
    t.start()
    return t


OK = [0]


def chequear(nombre, cond):
    assert cond, "FALLO: " + nombre
    OK[0] += 1
    print("  ok -", nombre)


def vaciar():
    while not cv._cola.empty():
        cv._cola.get_nowait()


# 1) EL BUG TAL CUAL: un result viejo esperando en la cola antes de preguntar.
vaciar()
viejo, nuevo = Falso(), Falso()
cv._vivo = nuevo
cv._cola.put((viejo, resultado("respuesta VIEJA")))
en_un_rato([(nuevo, resultado("respuesta NUEVA"))])
texto, error = cv._turno_ya("pregunta uno")
chequear("la respuesta tardia del turno viejo se descarta", texto == "respuesta NUEVA")
chequear("sin error en el turno sano", error is None)

# 2) El resto del viejo llega EN MEDIO del turno (despues del vaciado): se ignora.
vaciar()
cv._vivo = nuevo
en_un_rato([(viejo, resultado("respuesta VIEJA"))], demora=0.1)
en_un_rato([(nuevo, resultado("otra NUEVA"))], demora=0.4)
texto, error = cv._turno_ya("pregunta dos")
chequear("lo del proceso viejo en pleno turno tampoco cuenta", texto == "otra NUEVA")

# 3) El None (murio) de un proceso VIEJO no corta el turno del proceso vivo.
vaciar()
cv._vivo = nuevo
en_un_rato([(viejo, None)], demora=0.1)
en_un_rato([(nuevo, resultado("sigo viva"))], demora=0.4)
texto, error = cv._turno_ya("pregunta tres")
chequear("el 'se murio' del viejo no mata al turno vivo", texto == "sigo viva")

# 4) El None del proceso PROPIO si corta, como siempre.
vaciar()
cv._vivo = nuevo
en_un_rato([(nuevo, None)], demora=0.1)
texto, error = cv._turno_ya("pregunta cuatro")
chequear("si muere MI proceso, el turno avisa", error == "el proceso se cerro")

print(f"\n{OK[0]} chequeos, todos en verde")
