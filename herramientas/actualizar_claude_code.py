"""Actualiza el CLI de Claude Code cuando no queda ninguna sesion abierta.

Por que existe: Windows no deja reemplazar un .exe que esta corriendo, y el de Claude
pesa 287 MB. Como la actualizacion se pide DESDE una charla de Claude Code, el que la
pide es justamente uno de los procesos que hay que cerrar. Entonces esto se lanza, se
queda esperando, y actualiza solo cuando cerraste todo.

Se corre con el .bat del escritorio (doble clic). A mano:
    D:\\IA\\envs\\wpp\\python.exe herramientas/actualizar_claude_code.py
"""

import os
import subprocess
import sys
import time

# ⚠ Avast deja SSLKEYLOGFILE apuntando a un dispositivo suyo (aswMonFltProxy) y eso rompe
# el SSL de Node: sin sacarlo, npm no puede ni bajar el paquete. Es la misma vacuna que ya
# se pone en app/ingesta/bot_telegram.py y webhook_wasender.py.
os.environ.pop("SSLKEYLOGFILE", None)

ESPERA_MAX_MIN = 15


def _sesiones_abiertas():
    """Cuantos claude.exe hay vivos. psutil es lo que ya usa todo el proyecto."""
    import psutil
    n = 0
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "").lower() == "claude.exe":
                n += 1
        except psutil.Error:
            pass
    return n


def _version():
    try:
        r = subprocess.run("claude --version", shell=True, capture_output=True, text=True)
        return (r.stdout or "").strip() or "no se pudo leer"
    except Exception:
        return "no se pudo leer"


def main():
    antes = _version()
    print()
    print("  ACTUALIZAR CLAUDE CODE")
    print("  ======================")
    print()
    print("  Tenes ahora: %s" % antes)
    print()
    print("  Cerra TODAS las ventanas de Claude Code: la charla desde la que")
    print("  pediste esto, las del panel del Servidor IA, y cualquier otra.")
    print("  Yo espero solo. No cierres esta ventana.")
    print()

    limite = time.time() + ESPERA_MAX_MIN * 60
    while True:
        n = _sesiones_abiertas()
        if n == 0:
            break
        if time.time() > limite:
            print()
            print("  Pasaron %d minutos y siguen abiertas %d. Lo dejo para otro momento."
                  % (ESPERA_MAX_MIN, n))
            input("  Enter para salir ")
            return 1
        print("\r  ... todavia hay %d sesion(es) abiertas, sigo esperando   " % n, end="")
        sys.stdout.flush()
        time.sleep(3)

    print("\r  Listo, no queda ninguna abierta.                          ")
    print()
    print("  Actualizando: son 287 MB, tarda un rato.")
    print()
    r = subprocess.run("npm i -g @anthropic-ai/claude-code@latest", shell=True)
    print()
    if r.returncode != 0:
        print("  npm termino con error (codigo %d). No se actualizo nada." % r.returncode)
        input("  Enter para salir ")
        return 1
    print("  ------------------------------------------------")
    print("  Ahora tenes: %s" % _version())
    print("  ------------------------------------------------")
    print()
    print("  Si algo quedo raro, para volver a la de antes:")
    print("    npm i -g @anthropic-ai/claude-code@%s" % antes.split()[0])
    print()
    print("  Abri el panel del Servidor IA y avisale a Claude que ya actualizaste.")
    print()
    input("  Enter para salir ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
