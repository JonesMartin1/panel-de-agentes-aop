"""La ventana de escritorio del panel: el panel de siempre, sin navegador alrededor.

El panel (`panel.py`, puerto 8750) sigue siendo el mismo servidor web y no cambia en
nada: esto es SOLO la ventana que lo muestra, con su propio icono en la barra de
tareas y en la bandeja del reloj. Por dentro usa WebView2, el motor que Windows 11
ya trae puesto — no hay Electron, ni node, ni build: es el mismo HTML de siempre.

    pythonw.exe -m app.escritorio          (asi la lanza launcher.vbs, sin consola)
    python -m app.escritorio --depurar     (con las herramientas de desarrollo)

⭐ Es un proceso APARTE del panel, a proposito. Aca el panel se reinicia seguido
(cada cambio de HTML adentro de `panel.py` lo pide) y si la ventana viviera adentro
se cerraria sola en cada reinicio. Separada, el panel se apaga abajo, la ventana
muestra "esperando al panel" y vuelve sola cuando contesta de nuevo.

⚠ Cerrar la ventana NO apaga nada: se esconde en la bandeja del reloj y la voz, el
bot y el webhook siguen corriendo. Para apagar de verdad estan los botones del
panel, como siempre.

La bandeja tiene "Reiniciar el panel" (hace falta cada vez que se toca `panel.py`),
pero ⚠ **primero pregunta si hay una sesion de Claude contestando adentro**: esas
sesiones corren como hijas del panel y reiniciarlo en el medio les mata la respuesta.
Si la hay, avisa y no reinicia. Ver `_sesion_contestando`.
"""

import ctypes
import json
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.request import ProxyHandler, Request, build_opener

import psutil
import pystray
import webview
from PIL import Image

from app.rutas import ESTATICOS, PAUSA_ESCUCHA, RAIZ, VENTANA_ESCRITORIO, WEBVIEW_DATOS

PUERTO_PANEL = 8750
URL = f"http://localhost:{PUERTO_PANEL}"
# ⭐ Para PREGUNTARLE al panel si esta vivo se usa 127.0.0.1 y un abridor sin proxy
# (ver `_url_salud`), aunque la ventana cargue "localhost". Medido aca (2026-08-17):
#   urlopen a localhost .............. 2,11 s  (prueba ::1 primero y se cuelga)
#   urlopen a 127.0.0.1 sin proxy .... 0,05 s
# Y un puerto cerrado no rebota (el firewall lo traga), asi que "esta apagado"
# siempre cuesta el timeout entero: por eso es corto. Con los 4 s que costaba antes,
# la ventana tardaba 20 s en darse cuenta de que el panel no estaba.
SALUD_TIMEOUT = 1.5
# Puerto de la VENTANA (no del panel): sirve de candado para que haya una sola, y de
# timbre para que el segundo lanzamiento traiga al frente la que ya estaba.
PUERTO_VENTANA = 8751
CREATE_NO_WINDOW = 0x08000000
ICONO_PNG = ESTATICOS / "icono_laura.png"
# Cuanto esperamos a que el panel conteste al arrancar. Prender de cero (uvicorn +
# el vigilante de servicios) tarda unos segundos; con --auto ademas prende todo.
ESPERA_PANEL_SEG = 90
# La primera vez arranca maximizada: el panel es un tablero de tres columnas y con
# la ventana chica se acomoda en dos. Despues se abre como la hayas dejado.
GEOMETRIA_DEFECTO = {"ancho": 1320, "alto": 880, "x": None, "y": None, "maximizada": True}

# Colores de la barra de titulo, para que sea una continuacion del panel y no una
# franja del color de acento de Windows (que en esta maquina es VERDE fosforescente
# y se comia la pantalla). Son los mismos del panel: fondo, texto y borde.
BARRA_FONDO = 0x0B0D12
BARRA_TEXTO = 0xA8B0BD
BARRA_BORDE = 0x1E2636

DEPURAR = "--depurar" in sys.argv
ARRANCAR_OCULTA = "--oculta" in sys.argv     # para el arranque de Windows: solo bandeja

_geo = dict(GEOMETRIA_DEFECTO)
_ultima_url = URL          # la ultima pagina del panel que se vio (para volver ahi)
_saliendo = threading.Event()


# --- Hablar con el panel ----------------------------------------------------------

_sin_proxy = build_opener(ProxyHandler({}))          # ver el comentario de arriba


def _url_salud():
    """La misma URL de la ventana, pero por 127.0.0.1 (ver el comentario de URL).

    Se deriva de URL en vez de ser otra constante a proposito: con dos, cambiar una
    sola deja la ventana mirando un lado y preguntando por el otro — que es
    exactamente el enredo que hizo fallar la prueba la primera vez.
    """
    return URL.replace("localhost", "127.0.0.1")


def _pedir(ruta, metodo="POST", timeout=4):
    with _sin_proxy.open(Request(_url_salud() + ruta, method=metodo), timeout=timeout) as r:
        return r.read()


def _panel_responde(timeout=SALUD_TIMEOUT):
    """/pensando es el endpoint mas liviano del panel (existe para ser instantaneo)."""
    try:
        _pedir("/pensando", metodo="GET", timeout=timeout)
        return True
    except Exception:
        return False


def _procesos_panel():
    """Los procesos del panel DE VERDAD.

    ⚠ No alcanza con buscar "panel.py" en la linea de comando: cualquier consola que
    lo NOMBRE (un grep, una prueba, esta misma sesion) la tiene igual, y darla por
    buena significaria creer que el panel esta prendido cuando no lo esta — o peor,
    matarla al reiniciar. Tiene que ser un python cuyo ARGUMENTO sea panel.py.
    """
    encontrados = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() not in ("python.exe", "pythonw.exe"):
                continue
            if any(str(a).lower().endswith("panel.py") for a in (p.info["cmdline"] or [])[1:]):
                encontrados.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return encontrados


def _panel_vivo():
    """¿Hay un proceso del panel corriendo? (puede estar arrancando y no contestar aun)"""
    return bool(_procesos_panel())


def _sesion_contestando():
    """¿Hay una sesion de Claude contestando ADENTRO del panel?

    ⭐ Las sesiones de la pantalla corren como hijas del panel (`claude --resume` en un
    subprocess), asi que reiniciarlo en el medio de una respuesta la mata y el trabajo
    se pierde. En vez de confiarse, se pregunta: ¿el panel tiene algun hijo claude?
    Ante la duda dice que si — no reiniciar de mas no le hace mal a nadie.
    """
    for p in _procesos_panel():
        try:
            for hijo in p.children(recursive=True):
                quien = ((hijo.name() or "") + " " + " ".join(hijo.cmdline() or [])).lower()
                if "claude" in quien:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def _prender_panel(auto=True):
    """Prende el panel. Con --auto prende ademas servidor y voz, como el acceso.

    Al REINICIAR va sin --auto: los servicios son procesos aparte y siguieron
    corriendo, asi que prenderlos de nuevo estaria prendiendo lo que Martin apago.
    """
    cmd = [sys.executable, str(RAIZ / "panel.py")] + (["--auto"] if auto else [])
    subprocess.Popen(cmd, cwd=str(RAIZ), creationflags=CREATE_NO_WINDOW)


def _reiniciar_panel(icono):
    """Reinicia SOLO el panel, dejando prendidos la voz, el bot y el webhook.

    Es lo que hace falta cuando se toco `panel.py` (tiene las pantallas y las rutas en
    memoria). La ventana no se entera: el vigilante muestra "Esperando al panel" y
    vuelve sola a donde estabas.
    """
    if _sesion_contestando():
        icono.notify("Hay una sesion contestando adentro del panel: reiniciar ahora "
                     "le mata la respuesta. Proba de nuevo en un rato.", "No lo reinicie")
        return False
    procesos = _procesos_panel()
    for p in procesos:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, siguen = psutil.wait_procs(procesos, timeout=8)
    for p in siguen:                       # el que no se fue por las buenas
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    _prender_panel(auto=False)
    icono.notify("Reiniciando el panel. La ventana vuelve sola en unos segundos.",
                 "Servidor IA")
    return True


# --- La pantalla de espera --------------------------------------------------------

def _html_espera(titulo, detalle):
    """Lo que se ve mientras el panel no contesta. Mismos colores que el panel."""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
 :root{{color-scheme:dark}}
 body{{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;
       justify-content:center;gap:14px;background:#0b0d12;color:#e8eaed;
       font-family:Segoe UI,system-ui,sans-serif}}
 h1{{font-size:19px;margin:0;font-weight:600}}
 p{{margin:0;font-size:13.5px;color:#8b93a1;max-width:420px;text-align:center;line-height:1.5}}
 .latido{{display:flex;gap:6px;align-items:flex-end;height:26px;margin-bottom:6px}}
 .latido i{{width:7px;height:8px;border-radius:4px;background:#3ddc84;
            animation:respirar 1.6s infinite ease-in-out}}
 .latido i:nth-child(2){{animation-delay:.25s}} .latido i:nth-child(3){{animation-delay:.5s}}
 .latido i:nth-child(4){{animation-delay:.75s}}
 @keyframes respirar{{0%,100%{{height:8px;opacity:.45}}50%{{height:24px;opacity:1}}}}
</style></head><body>
 <div class="latido"><i></i><i></i><i></i><i></i></div>
 <h1>{titulo}</h1><p>{detalle}</p>
</body></html>"""


# --- La ventana -------------------------------------------------------------------

def _icono_ico():
    """WinForms quiere un .ico de verdad; lo unico que hay es el .png del celular.

    Se genera solo la primera vez (y de nuevo si cambia el .png), asi no hay que
    versionar un binario que se puede reconstruir en una linea.
    """
    ico = ESTATICOS / "icono_laura.ico"
    if not ico.exists() or ico.stat().st_mtime < ICONO_PNG.stat().st_mtime:
        Image.open(ICONO_PNG).save(
            ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
    return ico


def _pintar_barra(ventana, intentos=15):
    """Pinta la barra de titulo con los colores del panel.

    Sin esto, Windows le pone a la ventana ACTIVA su color de acento — un verde que
    corta la pantalla al medio arriba (y por eso en las capturas no se veia: una
    ventana que no tiene el foco usa el color apagado). Se arregla desde Windows,
    no desde el HTML: la barra de titulo la dibuja el sistema, no la pagina.

    Necesita Windows 11 (build 22000+). Si no puede, no pasa nada: queda como estaba.

    ⚠ Reintenta porque la ventana de Windows tarda un instante en existir despues de
    arrancar: si se pide el handle demasiado temprano no hay ninguno y la barra queda
    verde sin que nada avise.
    """
    hwnd = None
    for _ in range(intentos):
        try:
            hwnd = ventana.native.Handle.ToInt32()
            break
        except Exception:
            time.sleep(0.3)
    if hwnd is None:
        return False
    hecho = True
    for atributo, color in ((35, BARRA_FONDO),      # DWMWA_CAPTION_COLOR
                            (36, BARRA_TEXTO),      # DWMWA_TEXT_COLOR
                            (34, BARRA_BORDE)):     # DWMWA_BORDER_COLOR
        # ⚠ DWM quiere el color al reves que el HTML: 0x00BBGGRR, no 0xRRGGBB.
        crudo = ctypes.c_int(((color & 0xFF) << 16) | (color & 0xFF00) | (color >> 16))
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, atributo, ctypes.byref(crudo), ctypes.sizeof(crudo)) != 0:
            hecho = False
    return hecho


def _acomodar(geo):
    """Corrige una posicion desde la que la ventana no se podria agarrar.

    ⭐ Pasó de verdad el 2026-08-17: quedó guardado `y = -33`, o sea la barra de título
    33 px ARRIBA del borde de la pantalla. La ventana se veía entera pero no había de
    dónde agarrarla para moverla, y Windows no ofrece nada obvio para rescatarla.
    Acá se le pone el tope: la barra siempre adentro, y siempre un pedazo agarrable.

    Las cuentas van en pixeles LOGICOS, que es lo que usa pywebview; las medidas de
    Windows vienen en fisicos, por eso se dividen por la escala de la pantalla.
    """
    if geo.get("x") is None or geo.get("y") is None:
        return geo
    try:
        escala = ctypes.windll.user32.GetDpiForSystem() / 96 or 1
        metrica = ctypes.windll.user32.GetSystemMetrics
        izq, arriba = metrica(76) / escala, metrica(77) / escala      # pantalla virtual:
        ancho, alto = metrica(78) / escala, metrica(79) / escala      # todos los monitores
    except Exception:
        return geo
    # Que quede agarrable: nunca arriba del borde, y al menos un pedazo a la vista.
    x = min(max(geo["x"], izq - geo["ancho"] + 220), izq + ancho - 220)
    y = min(max(geo["y"], arriba), arriba + alto - 90)
    return {**geo, "x": int(x), "y": int(y)}


def _leer_geometria():
    try:
        guardado = json.loads(VENTANA_ESCRITORIO.read_text(encoding="utf-8"))
        return _acomodar({**GEOMETRIA_DEFECTO, **{k: guardado.get(k, v)
                                                  for k, v in GEOMETRIA_DEFECTO.items()}})
    except Exception:
        return dict(GEOMETRIA_DEFECTO)


def _guardar_geometria():
    try:
        # Se acomoda tambien al GUARDAR: asi el archivo nunca queda con una posicion
        # imposible, ni siquiera si alguien lo abre a mano para mirarlo.
        _geo.update(_acomodar(_geo))
        VENTANA_ESCRITORIO.write_text(json.dumps(_geo, indent=1), encoding="utf-8")
    except Exception:
        pass                                  # que no impida cerrar la ventana


def _mostrar(ventana, ruta=None):
    """Trae la ventana al frente (y opcionalmente la manda a una pantalla)."""
    if ruta:
        ventana.load_url(URL + ruta)
    ventana.show()
    ventana.restore()


def _pantalla_logica():
    """El tamaño de la pantalla principal en pixeles LOGICOS (los que usa pywebview)."""
    try:
        escala = ctypes.windll.user32.GetDpiForSystem() / 96 or 1
        metrica = ctypes.windll.user32.GetSystemMetrics
        return metrica(0) / escala, metrica(1) / escala
    except Exception:
        return 1280.0, 800.0


def _tamano_comodo():
    """Una ventana que se vea como ventana en ESTA pantalla.

    Un tamaño fijo no sirve: la de Martín va al 175 %, y ahí 1320x880 "logicos" son
    2310x1540 de verdad — o sea casi toda la pantalla, y al salir de maximizada
    parecía que se había roto algo. Se calcula como una parte del monitor.
    """
    ancho, alto = _pantalla_logica()
    return max(940, int(ancho * 0.78)), max(620, int(alto * 0.82))


def _acomodar_ventana(ventana):
    """El rescate: trae la ventana al centro de la pantalla principal.

    Es para cuando quedó en un lugar del que no se la puede agarrar (arriba del borde,
    o en un monitor que ya no está enchufado). Vive en la bandeja porque ahí se puede
    llegar SIEMPRE, aunque la ventana no se vea.
    """
    pantalla_ancho, pantalla_alto = _pantalla_logica()
    ancho, alto = _tamano_comodo()
    ventana.resize(ancho, alto)
    ventana.move(int((pantalla_ancho - ancho) / 2), int((pantalla_alto - alto) / 2))
    _geo.update(ancho=ancho, alto=alto, maximizada=False)
    ventana.show()
    ventana.restore()


def _vigilar_panel(ventana):
    """Si el panel se cae o se reinicia, la ventana lo espera y vuelve sola.

    Sin esto, un reinicio del panel deja el error feo de Chromium ("no se puede
    acceder a este sitio") y hay que refrescar a mano.
    """
    global _ultima_url
    fallos, esperando = 0, False
    while not _saliendo.is_set():
        _saliendo.wait(3)
        if _saliendo.is_set():
            return
        if _panel_responde():
            if esperando:
                ventana.load_url(_ultima_url)   # vuelve a la MISMA pantalla que estabas
                esperando = False
            fallos = 0
        else:
            fallos += 1
            # Dos vueltas en falso (~6 s) antes de tapar la pantalla: un reinicio del
            # panel dura menos que eso y no vale la pena el parpadeo.
            if fallos >= 2 and not esperando:
                actual = ventana.get_current_url() or ""
                if actual.startswith(URL):
                    _ultima_url = actual
                ventana.load_html(_html_espera(
                    "Esperando al panel",
                    "El panel se está reiniciando o se apagó. Cuando vuelva, "
                    "esta ventana sigue sola donde estabas."))
                esperando = True


# --- El icono de la bandeja (al lado del reloj) -----------------------------------

def _bandeja(ventana):
    """El icono del reloj: abrir las pantallas, pausar la escucha y salir.

    Salir cierra la VENTANA, no el panel: los servicios quedan corriendo. Es lo que
    uno espera de una app que vive en la bandeja.
    """
    def ir(ruta):
        return lambda icono, item: _mostrar(ventana, ruta)

    def pausar(icono, item):
        try:
            _pedir("/pausa", metodo="POST")
        except Exception:
            pass

    def salir(icono, item):
        _saliendo.set()
        _guardar_geometria()
        icono.stop()
        ventana.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir el panel", ir("/"), default=True),
        pystray.MenuItem("Pizarra", ir("/pizarra")),
        pystray.MenuItem("Sesiones", ir("/sesiones")),
        pystray.MenuItem("Estudio", ir("/estudio")),
        pystray.Menu.SEPARATOR,
        # El tilde se lee del archivo, no del panel: /status tarda medio segundo y el
        # menu quedaria pegado al abrirlo. La perilla igual se gira por el panel.
        pystray.MenuItem("Pausar escucha", pausar, checked=lambda item: PAUSA_ESCUCHA.exists()),
        pystray.Menu.SEPARATOR,
        # ⚠ Reiniciar el panel NO apaga la voz ni el bot (son procesos aparte), pero SI
        # mata una sesion que este contestando adentro: por eso pregunta primero.
        pystray.MenuItem("Reiniciar el panel", lambda icono, item: _reiniciar_panel(icono)),
        pystray.MenuItem("Acomodar la ventana (traerla al centro)",
                         lambda icono, item: _acomodar_ventana(ventana)),
        pystray.MenuItem("Abrirlo en el navegador", lambda icono, item: webbrowser.open(URL)),
        pystray.MenuItem("Salir (los servicios siguen prendidos)", salir),
    )
    icono = pystray.Icon("servidor_ia", Image.open(ICONO_PNG), "Servidor IA", menu)
    icono.run()


# --- Una sola ventana -------------------------------------------------------------

def _candado():
    """Devuelve el socket-candado, o None si ya habia una ventana (y le toca timbre)."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", PUERTO_VENTANA))
    except OSError:
        try:
            with socket.create_connection(("127.0.0.1", PUERTO_VENTANA), timeout=2) as c:
                c.sendall(b"mostrar")         # la que ya estaba se trae al frente
        except OSError:
            pass
        return None
    s.listen(4)
    return s


def _atender_timbre(servidor, ventana):
    while not _saliendo.is_set():
        try:
            con, _ = servidor.accept()
        except OSError:
            return
        with con:
            _mostrar(ventana)


# --- Arranque ---------------------------------------------------------------------

def _arrancar(ventana, servidor):
    """Corre en un hilo, con la ventana ya en pantalla: espera al panel y lo carga."""
    _pintar_barra(ventana)
    threading.Thread(target=_atender_timbre, args=(servidor, ventana), daemon=True).start()
    threading.Thread(target=_bandeja, args=(ventana,), daemon=True).start()

    if not _panel_responde(timeout=2):
        if not _panel_vivo():
            _prender_panel()
        limite = time.monotonic() + ESPERA_PANEL_SEG
        while time.monotonic() < limite and not _saliendo.is_set():
            if _panel_responde():
                break
            time.sleep(1)

    if _panel_responde():
        ventana.load_url(URL)
    else:
        ventana.load_html(_html_espera(
            "El panel no arranca",
            f"No contesta en {URL} después de {ESPERA_PANEL_SEG} segundos. "
            "Fijate el log del panel; esta ventana lo sigue esperando."))
    threading.Thread(target=_vigilar_panel, args=(ventana,), daemon=True).start()


def main():
    servidor = _candado()
    if servidor is None:
        print("Ya hay una ventana abierta: la traigo al frente.")
        return

    # Para que Windows le de barra de tareas e icono propios en vez de agruparla
    # con cualquier otro python que este corriendo.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MartinJones.ServidorIA")

    webview.settings["ALLOW_DOWNLOADS"] = True   # el mp3 del Estudio, las imagenes de la pizarra

    _geo.update(_leer_geometria())
    ventana = webview.create_window(
        "Servidor IA",
        html=_html_espera("Prendiendo el Servidor IA", "Esperando a que conteste el panel…"),
        width=_geo["ancho"], height=_geo["alto"], x=_geo["x"], y=_geo["y"],
        min_size=(940, 620), background_color="#0b0d12", hidden=ARRANCAR_OCULTA,
        maximized=bool(_geo["maximizada"]), text_select=True, zoomable=True,
    )

    # ⚠ Mientras esta maximizada NO se guarda el tamaño: si no, al volver de
    # maximizada se abriria del tamaño de la pantalla y ya no se podria achicar
    # de una vez. Se guarda el tamaño "chico" y aparte si quedo maximizada.
    def medida(ancho, alto):
        if not _geo["maximizada"]:
            _geo.update(ancho=ancho, alto=alto)

    def lugar(x, y):
        if not _geo["maximizada"]:
            _geo.update(x=x, y=y)

    ventana.events.resized += medida
    ventana.events.moved += lugar
    ventana.events.maximized += lambda: _geo.update(maximizada=True)
    ventana.events.restored += lambda: _geo.update(maximizada=False)

    def al_cerrar():
        """La cruz esconde la ventana en la bandeja; no apaga el Servidor IA."""
        if _saliendo.is_set():
            return True                       # salida de verdad, desde la bandeja
        _guardar_geometria()
        threading.Timer(0.05, ventana.hide).start()   # fuera del hilo de la ventana
        return False                          # ⭐ False = no la cierres

    ventana.events.closing += al_cerrar

    webview.start(_arrancar, (ventana, servidor), icon=str(_icono_ico()),
                  private_mode=False, storage_path=str(WEBVIEW_DATOS), debug=DEPURAR)
    _saliendo.set()
    _guardar_geometria()


if __name__ == "__main__":
    main()
