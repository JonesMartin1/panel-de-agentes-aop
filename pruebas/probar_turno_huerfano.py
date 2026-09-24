"""Un turno de Codex TERMINA aunque deje algo corriendo en segundo plano.

⭐⭐ El bug que trajo Martin el 2026-08-22: *"si yo apago los modelos, el panel funciona
mal y las sesiones quedan trabadas"*. `for linea in p.stdout` termina cuando se CIERRA EL
PIPE, no cuando muere el proceso. Una sesion de Codex levanto el generador 3D, Codex
contesto y se fue, el Hunyuan quedo HUERFANO con el pipe agarrado, y el turno se quedo
esperando para siempre: el pedido HTTP nunca contestaba y la pestaña quedaba en
"pensando" con la caja bloqueada.

Aca se reproduce con un CLI de mentira que hace exactamente eso (contesta, se va, y deja
un hijo agarrado a la salida). No gasta un token ni habla con Codex.

    python -m pruebas.probar_turno_huerfano
"""
import subprocess
import sys
import textwrap
import time

from app.voz import sesiones_movil as sm

bien = malo = 0


def ok(cond, que):
    global bien, malo
    if cond:
        bien += 1
        print("  ok   ", que)
    else:
        malo += 1
        print("  MAL  ", que)


# Un "codex" que contesta, se va, y deja un hijo vivo con el MISMO stdout heredado.
CLI_FALSO = textwrap.dedent(r"""
    import subprocess, sys, time
    sys.stdin.read()
    print('{"type":"item.completed","item":{"type":"agent_message","text":"listo"}}',
          flush=True)
    # el hijo hereda stdout: el pipe queda abierto aunque yo me muera (esto es el Hunyuan)
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    sys.exit(0)
""")


def arrancar():
    p = subprocess.Popen([sys.executable, "-c", CLI_FALSO],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    p.stdin.write("hola")
    p.stdin.close()
    return p


print("Un CLI que contesta, se va, y deja un hijo agarrado a su salida")

# --- como era antes: `for linea in p.stdout` -----------------------------------------
# ⚠ Va en OTRO proceso a proposito: si se hace acá, el hilo que queda bloqueado leyendo
# el pipe se lleva puesta la salida del test al terminar (en Windows sale con un codigo
# raro y sin imprimir nada). Que se cuelgue es justo lo que se quiere demostrar, asi que
# se lo encierra y se lo mata por timeout.
VIEJO = textwrap.dedent(r"""
    import subprocess, sys
    CLI = %r
    p = subprocess.Popen([sys.executable, "-c", CLI], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8")
    p.stdin.write("hola"); p.stdin.close()
    for _ in p.stdout:      # <- el bucle de antes
        pass
    print("VOLVIO")
""") % CLI_FALSO
try:
    r = subprocess.run([sys.executable, "-c", VIEJO], capture_output=True, text=True,
                       timeout=10)
    colgado = "VOLVIO" not in (r.stdout or "")
except subprocess.TimeoutExpired:
    colgado = True
ok(colgado, "la forma VIEJA se cuelga (si esto sale MAL, el bug ya no se reproduce)")

# --- como es ahora -------------------------------------------------------------------
p2 = arrancar()
estado = {"fin": False, "vencido": False, "huerfano": False, "latido": time.time()}
arranco = time.time()
lineas = list(sm._lineas_hasta_que_muera(p2, estado, gracia=1.0))
tardo = time.time() - arranco
ok(tardo < 12, "la forma NUEVA vuelve sola (tardó %.1f s)" % tardo)
ok(any("agent_message" in l for l in lineas), "y no se pierde la respuesta del turno")
ok(estado["huerfano"] is True, "queda anotado que algo se quedó con la salida")
try:
    p2.kill()
except Exception:
    pass

# --- y no corta antes de tiempo cuando el CLI se porta bien --------------------------
print("\nUn CLI normal, que cierra su salida al terminar")
p3 = subprocess.Popen(
    [sys.executable, "-c",
     'import sys; sys.stdin.read(); print("{\\"type\\":\\"a\\"}"); '
     'print("{\\"type\\":\\"b\\"}")'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, encoding="utf-8")
p3.stdin.write("hola")
p3.stdin.close()
estado3 = {"fin": False, "vencido": False, "huerfano": False, "latido": time.time()}
lineas3 = list(sm._lineas_hasta_que_muera(p3, estado3, gracia=1.0))
ok(len(lineas3) == 2, "llegan todas las lineas, no se pierde ninguna")
ok(estado3["huerfano"] is False, "y no se lo marca como huérfano sin motivo")

print("\n%d en verde, %d en rojo" % (bien, malo))
if malo:
    raise SystemExit(1)
