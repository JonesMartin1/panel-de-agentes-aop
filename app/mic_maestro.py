"""Prende/apaga el interruptor MAESTRO del microfono de Windows — el de arriba
de Configuracion > Privacidad y seguridad > Microfono ("Microphone access").

Como no hay via administrativa sin permisos de administrador, y en este Windows
(build 26200) esa pantalla NO lee el registro (escribe ConsentStore pero LEE la
cache interna del servicio de privacidad — probado con diff de registro), la
unica forma real es manejar la propia app de Configuracion por automatizacion
de interfaz (pywinauto/UIA): se abre sola, se toca el interruptor como si
fueras vos, y se cierra. Que la ventana aparezca un par de segundos es normal.

Con el maestro apagado, abrir un microfono da PaErrorCode -9996 (medido el
2026-08-13): corta de verdad a los programas comunes y a las apps de la tienda.
Corre como subproceso del panel, igual que mic_windows.py: si algo explota,
muere este proceso y el panel sigue.

Uso: python -m app.mic_maestro on|off   ->  {"maestro": "on"/"off"}
"""
import json
import os
import sys
import time

# El auto_id es estable e independiente del idioma de Windows (el titulo de la
# ventana "Settings" no lo es: si algun dia la interfaz esta en espanol, aca
# hay que sumar "Configuracion" a TITULOS).
AUTO_ID = "SystemSettings_CapabilityAccess_Microphone_SystemGlobal_ToggleSwitch"
TITULOS = ("Settings", "Configuración", "Configuracion")


def main():
    querido = 1 if (sys.argv[1] if len(sys.argv) > 1 else "on") == "on" else 0
    from pywinauto import Desktop
    desktop = Desktop(backend="uia")

    # Abrir (o navegar) Configuracion a la pagina del microfono. Si ya estaba
    # abierta en otra pagina, el protocolo ms-settings: la lleva ahi mismo.
    os.startfile("ms-settings:privacy-microphone")

    # Encontrar la ventana RAPIDO (sondeo cada 0.2 s) y correrla fuera de la
    # pantalla al toque: queda un pestañeo de menos de un segundo en vez de la
    # ventana plantada adelante. UIA la puede tocar igual aunque no se vea.
    # (A otro escritorio virtual NO: Windows suspende las apps que no se ven
    # y el interruptor dejaria de responder.)
    win = None
    for _ in range(60):
        time.sleep(0.2)
        for titulo in TITULOS:
            try:
                w = desktop.window(title=titulo)
                if w.exists(timeout=0.2):
                    win = w
                    break
            except Exception:
                pass
        if win is not None:
            break
    if win is None:
        print(json.dumps({"error": "no aparecio la ventana de Configuracion"}))
        return 1
    for _ in range(10):
        try:
            win.move_window(x=-32000, y=200)
            break
        except Exception:
            time.sleep(0.3)

    sw = None
    for _ in range(15):
        try:
            sw = win.child_window(auto_id=AUTO_ID,
                                  control_type="Button").wrapper_object()
            break
        except Exception:
            sw = None
            time.sleep(1)
    if sw is None:
        _cerrar_prolijo(win)
        print(json.dumps({"error": "no encontre el interruptor en Configuracion"}))
        return 1

    if sw.get_toggle_state() != querido:
        sw.iface_toggle.Toggle()
        time.sleep(1.5)
    estado = win.child_window(auto_id=AUTO_ID,
                              control_type="Button").wrapper_object().get_toggle_state()
    _cerrar_prolijo(win)
    print(json.dumps({"maestro": "on" if estado else "off"}))
    return 0 if estado == querido else 1


def _cerrar_prolijo(win):
    """Devolver la ventana a una posicion visible ANTES de cerrarla: Windows
    recuerda la ultima posicion, y si se cierra fuera de pantalla, la proxima
    vez que Martin abra Configuracion a mano no la veria por ningun lado."""
    try:
        win.move_window(x=120, y=120)
    except Exception:
        pass
    try:
        win.close()
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
