"""Prueba de la foto de procesos del panel (`_barrer`, `_foto`, `vivo`, `/status`).

Por que existe: `/status` hacia SIETE barridos completos de procesos por pedido
(uno por cada `vivo()`), y la pantalla lo pide cada 2,5 s por pestaña abierta. Medido
el 2026-08-18 en la maquina de Martin: 404 procesos, 0,048 s el barrido con `cmdline`,
o sea 0,34 s de CPU pura por pedido. Esto fija que ahora se barra UNA sola vez y que
la foto se comparta entre pestañas — que es lo unico que hace falta romper para que
el problema vuelva sin que nadie se entere.

No levanta el servidor ni mata ningun proceso: cuenta los barridos de verdad
reemplazando `psutil.process_iter` por uno de mentira. Se corre con:
    python -m pruebas.probar_foto_procesos
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import panel

OK = MAL = 0


def chequear(nombre, cond):
    global OK, MAL
    print(("  ok   " if cond else "  MAL  ") + nombre)
    if cond:
        OK += 1
    else:
        MAL += 1


# --- Procesos de mentira, con la forma que mira `_barrer` -------------------------

class ProcFalso:
    def __init__(self, pid, nombre, cmdline):
        self.pid = pid
        self.info = {"pid": pid, "name": nombre, "cmdline": cmdline}


# Uno por servicio, mas ruido: el propio panel (que se descarta por "panel.py") y
# una consola cualquiera que NOMBRA a un servicio sin ser el.
MUNDO = [
    ProcFalso(101, "python.exe", ["python.exe", "-m", "app.ingesta.bot_telegram"]),
    ProcFalso(102, "python.exe", ["python.exe", "-m", "uvicorn",
                                  "app.ingesta.webhook_wasender:app"]),
    ProcFalso(103, "cloudflared.exe", ["cloudflared.exe", "tunnel", "run"]),
    ProcFalso(104, "python.exe", ["python.exe", "-m", "app.voz.voz"]),
    ProcFalso(105, "python.exe", ["python.exe", "panel.py"]),
    ProcFalso(106, "cmd.exe", ["cmd.exe", "/c", "type", "panel.py"]),
]

barridos = {"n": 0}


def iter_falso(campos=None):
    barridos["n"] += 1
    return list(MUNDO)


panel.psutil.process_iter = iter_falso


def limpiar():
    """Cada chequeo arranca sin foto guardada y sin barridos contados."""
    panel._invalidar_foto()
    barridos["n"] = 0


# --- El barrido reconoce a cada servicio y descarta el ruido ----------------------

limpiar()
foto = panel._foto()
chequear("un solo barrido para armar la foto entera", barridos["n"] == 1)
chequear("encuentra el bot de Telegram", [p.pid for p in foto["telegram"]] == [101])
chequear("encuentra el webhook", [p.pid for p in foto["webhook"]] == [102])
chequear("encuentra el tunel por proc_name", [p.pid for p in foto["tunel"]] == [103])
chequear("encuentra la voz", [p.pid for p in foto["voz"]] == [104])
chequear("hay una entrada por servicio y ninguna de mas",
         set(foto) == set(panel.SERVICIOS))
chequear("la consola que solo NOMBRA panel.py no se cuela",
         all(106 not in [p.pid for p in v] for v in foto.values()))

# --- La foto se comparte: eso es todo el arreglo ----------------------------------

limpiar()
for _ in range(20):
    panel.vivo("voz")
chequear("veinte llamadas a vivo() dentro de la ventana = un solo barrido",
         barridos["n"] == 1)

limpiar()
panel.status()
chequear("un /status entero barre UNA vez (antes eran siete)", barridos["n"] == 1)

# --- Un /status contesta lo mismo que antes --------------------------------------

r = panel.status()
chequear("/status marca vivos los cuatro servicios",
         all(r["servicios"][n]["vivo"] for n in panel.SERVICIOS))
chequear("/status dice que el servidor esta encendido", r["encendido"] is True)
chequear("/status trae el label de cada servicio",
         all(r["servicios"][n]["label"] == panel.SERVICIOS[n]["label"]
             for n in panel.SERVICIOS))

# --- Y sigue viendo caerse las cosas ----------------------------------------------

limpiar()
panel._foto()                           # foto tomada con la voz todavia andando
voz = MUNDO.pop(3)                      # y recien ahi se cae
chequear("con la foto vieja todavia la ve viva (esa es la ventana)",
         panel.vivo("voz"))
panel._invalidar_foto()
chequear("vencida la foto, se entera de que se cayo", not panel.vivo("voz"))
r = panel.status()
chequear("/status apaga el semaforo de la voz", r["servicios"]["voz"]["vivo"] is False)
chequear("/status deja el servidor encendido igual (la voz no es del servidor)",
         r["encendido"] is True)
MUNDO.insert(3, voz)

# --- La foto vence sola ------------------------------------------------------------

limpiar()
panel._foto()
panel._SNAP["ts"] = time.time() - panel._SNAP_SEG - 0.1
panel._foto()
chequear("pasada la ventana vuelve a barrer", barridos["n"] == 2)
chequear("la ventana es corta (no mas de 3 s de retraso en el semaforo)",
         panel._SNAP_SEG <= 3)

# --- fresco=True no se conforma con la foto guardada ------------------------------

limpiar()
panel._foto()
panel.vivo("voz", fresco=True)
chequear("vivo(fresco=True) barre aunque la foto este fresca", barridos["n"] == 2)
panel._procs("voz", fresco=True)
chequear("_procs(fresco=True) tambien", barridos["n"] == 3)

# ⚠ Esto es lo que evita el bug de "prender algo recien caido y que no pase nada":
# start_one pregunta fresco, asi que no puede creerle a una foto de hace un segundo.
limpiar()
panel._foto()                            # la voz figura viva en la foto
MUNDO.pop(3)                             # ...pero se acaba de caer
lanzados = []
panel.subprocess.Popen = lambda *a, **k: lanzados.append(a)
try:
    panel.start_one("voz")
    chequear("start_one lanza el servicio recien caido pese a la foto vieja",
             len(lanzados) == 1)
finally:
    MUNDO.insert(3, voz)

# Y despues de prender o apagar, la foto guardada no puede quedar mintiendo.
chequear("start_one invalida la foto", panel._SNAP["ts"] == 0.0)

limpiar()
panel._foto()
matados = []
for p in MUNDO:
    p.terminate = lambda p=p: matados.append(p.pid)
    p.kill = p.terminate
panel.stop_one("voz")
chequear("stop_one apunta al proceso de ese servicio", matados == [104])
chequear("stop_one invalida la foto", panel._SNAP["ts"] == 0.0)

print(f"\n{OK} ok, {MAL} mal")
sys.exit(1 if MAL else 0)
