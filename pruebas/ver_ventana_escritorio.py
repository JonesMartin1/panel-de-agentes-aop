"""Prueba de la ventana de escritorio (app/escritorio.py), sin tocar nada real.

Abre la ventana apuntando a un PUERTO MUERTO, asi se puede mirar lo que se ve
cuando el panel no contesta — que es justo lo que no se puede probar con el panel
prendido. Comprueba, en este orden:

  1. la ventana abre y muestra "Prendiendo el Servidor IA";
  2. si el panel nunca contesta, pasa sola a "El panel no arranca";
  3. el icono de la bandeja del reloj existe;
  4. la cruz de la ventana la esconde en vez de cerrarla, y el proceso sigue vivo;
  5. lanzarla de nuevo (el timbre por socket) la trae de vuelta.

Deja una captura en `pruebas/ventana_escritorio.png` — ⭐ mirala, que los defectos
de pantalla se ven ahi y no en el codigo.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_ventana_escritorio

⚠ La prueba NO prende ningun panel: `_prender_panel` queda anulado. Sin eso,
arrancaria un panel.py --auto de verdad (con voz, bot y tunel) contra un puerto
que no es el suyo.
"""

import socket
import tempfile
import threading
import time
from ctypes import windll
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image

import webview

from app import escritorio as esc

PUERTO_MUERTO = 8799          # nadie escucha aca: es el punto de la prueba
PUERTO_CANDADO = 8752         # el de verdad es el 8751; no se lo pisamos
CAPTURA = Path(__file__).with_name("ventana_escritorio.png")

fallos = []


def chequear(que, condicion):
    print(("  ok   " if condicion else "  FALLA") + "  " + que)
    if not condicion:
        fallos.append(que)


def ventana_hwnd():
    """El hwnd de la ventana, o None. Ojo: el Chrome con el panel abierto tiene el
    MISMO titulo — por eso ademas se mira la clase (WinForms)."""
    encontrada = []

    def cb(h, _):
        if (win32gui.GetWindowText(h) == "Servidor IA"
                and win32gui.GetClassName(h).startswith("WindowsForms")):
            encontrada.append(h)

    win32gui.EnumWindows(cb, None)
    return encontrada[0] if encontrada else None


def hay_icono_bandeja():
    """pystray registra una ventana escondida con el nombre del icono en la clase."""
    encontrada = []

    def cb(h, _):
        if "servidor_ia" in win32gui.GetClassName(h):
            encontrada.append(h)

    win32gui.EnumWindows(cb, None)
    return bool(encontrada)


def capturar(h, destino):
    """PrintWindow y no una captura de pantalla: la ventana puede estar tapada por
    el Chrome de Martin, y traerla al frente le robaria el foco en el medio."""
    izq, arr, der, aba = win32gui.GetWindowRect(h)
    ancho, alto = der - izq, aba - arr
    dc = win32gui.GetWindowDC(h)
    origen = win32ui.CreateDCFromHandle(dc)
    memoria = origen.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(origen, ancho, alto)
    memoria.SelectObject(bmp)
    windll.user32.PrintWindow(h, memoria.GetSafeHdc(), 2)   # 2 = PW_RENDERFULLCONTENT
    info = bmp.GetInfo()
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                           bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    img.save(destino)
    win32gui.DeleteObject(bmp.GetHandle())
    memoria.DeleteDC()
    origen.DeleteDC()
    win32gui.ReleaseDC(h, dc)
    return img


_avisado = []


def titulo_en_pantalla():
    """El <h1> de la pantalla de espera, preguntandole a la propia pagina."""
    try:
        return webview.windows[0].evaluate_js("document.querySelector('h1').textContent")
    except Exception as e:
        if not _avisado:                       # una vez alcanza: si no, tapa la salida
            _avisado.append(e)
            print(f"  (evaluate_js no contesta: {type(e).__name__}: {e})")
        return None


def esperar_titulo(texto, seg):
    """Espera al DATO y no al reloj: cuanto tarda cada pantalla varia."""
    limite = time.time() + seg
    visto = None
    while time.time() < limite:
        visto = titulo_en_pantalla()
        if visto == texto:
            return True
        time.sleep(0.4)
    print(f"         (esperaba {texto!r}, en pantalla hay {visto!r})")
    return False


def revisar():
    """Corre en un hilo: la ventana necesita el hilo principal para si misma."""
    try:
        h = None
        limite = time.time() + 25
        while time.time() < limite and h is None:
            time.sleep(0.5)
            h = ventana_hwnd()
        chequear("la ventana abre", h is not None)
        if h is None:
            return

        # ⚠⚠ NO preguntarle nada a la pagina antes de esto. Que exista la ventana de
        # Windows no quiere decir que WebView2 ya haya arrancado adentro, y un
        # evaluate_js en el medio del arranque le traba el hilo de la ventana: queda
        # NEGRA para siempre y todo lo que preguntes devuelve None, sin ningun error.
        # Media hora de "¿por que no se ve nada?" viene de aca.
        chequear("la pagina termina de cargar", webview.windows[0].events.loaded.wait(25))

        chequear("mientras espera dice 'Prendiendo el Servidor IA'",
                 esperar_titulo("Prendiendo el Servidor IA", 8))
        chequear("hay icono en la bandeja del reloj", hay_icono_bandeja())

        chequear("si el panel no aparece, avisa en pantalla",
                 esperar_titulo("El panel no arranca", esc.ESPERA_PANEL_SEG + 8))
        img = capturar(h, CAPTURA)
        # El vigilante sigue mirando: cuando confirma que el panel no esta, deja la
        # pantalla que espera el regreso (la misma que se ve al reiniciar el panel).
        chequear("el vigilante deja la pantalla de 'Esperando al panel'",
                 esperar_titulo("Esperando al panel", 15))

        chequear("la captura no salio en blanco", len(img.getcolors(maxcolors=200000) or []) > 20)

        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)    # la cruz
        time.sleep(2)
        chequear("la cruz la esconde, no la cierra", not win32gui.IsWindowVisible(h))
        chequear("el proceso sigue vivo despues de cerrarla", ventana_hwnd() is not None)

        with socket.create_connection(("127.0.0.1", PUERTO_CANDADO), timeout=3) as c:
            c.sendall(b"mostrar")               # como abrir el acceso por segunda vez
        time.sleep(2)
        chequear("lanzarla de nuevo la trae de vuelta", bool(win32gui.IsWindowVisible(h)))
    finally:
        esc._saliendo.set()
        try:
            webview.windows[0].destroy()
        except Exception:
            pass


def main():
    if ventana_hwnd() is not None:
        print("Ya hay una ventana de escritorio abierta. Cerrala primero desde el icono\n"
              "de la bandeja (Salir), o la prueba mide la ventana equivocada.")
        return 1

    print("Ventana de escritorio (panel apagado a proposito, puerto muerto):")
    esc.URL = f"http://localhost:{PUERTO_MUERTO}"
    esc.PUERTO_VENTANA = PUERTO_CANDADO
    esc.ESPERA_PANEL_SEG = 6
    esc._prender_panel = lambda: None                    # ⚠ que no prenda nada de verdad
    temporal = Path(tempfile.mkdtemp(prefix="ventana_prueba_"))
    esc.VENTANA_ESCRITORIO = temporal / "ventana.json"   # no pisar donde la dejo Martin
    esc.WEBVIEW_DATOS = temporal / "webview"

    threading.Thread(target=revisar, daemon=True).start()
    esc.main()                                           # bloquea hasta que se destruye

    print("\n" + ("TODO BIEN" if not fallos else f"{len(fallos)} FALLA(S): " + "; ".join(fallos)))
    print(f"captura: {CAPTURA}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
