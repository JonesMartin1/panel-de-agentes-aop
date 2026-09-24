"""
Control del navegador (Chrome dedicado 'IA') via Playwright + CDP.
El Chrome se abre con "Chrome IA.bat" (puerto 9222, perfil propio).

Comandos concretos: abrir, leer, clic, escribir, navegar.
"""

import os
os.environ.pop("SSLKEYLOGFILE", None)

import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # coords fisicas reales (multi-monitor)
except Exception:
    pass

import re
import time
import subprocess
import urllib.request
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

_ORDINAL = {"primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2,
            "tercer": 3, "tercero": 3, "tercera": 3, "cuarto": 4, "cuarta": 4,
            "quinto": 5, "quinta": 5, "ultimo": -1, "ultima": -1}

CDP = "http://localhost:9222"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PERFIL = r"D:\IA\chrome-ia"


def _puerto_ok():
    try:
        urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
        return True
    except Exception:
        return False


def _asegurar_chrome():
    """Si el Chrome IA no esta abierto, lo abre solo (con el perfil logueado) y espera."""
    if _puerto_ok():
        return True
    try:
        subprocess.Popen([CHROME, "--remote-debugging-port=9222",
                          f"--user-data-dir={PERFIL}", "https://www.google.com"])
    except Exception as e:
        print("no pude abrir el Chrome IA:", e, flush=True)
        return False
    for _ in range(24):          # espera hasta ~12s a que levante
        if _puerto_ok():
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False


def _titulo_ventana_frente():
    """Titulo de la ventana de Windows que esta al frente (la que el usuario mira)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        wt = (buf.value or "").strip()
    except Exception:
        return ""
    # sacar el sufijo "- Google Chrome" / "- Chrome" para quedarnos con el titulo de la pestaña
    return re.sub(r"\s*[-–—]\s*(Google\s+)?Chrome\s*$", "", wt).strip()


def _pagina_activa(ctx):
    """Devuelve la pestaña que el usuario REALMENTE esta mirando.

    Con varias VENTANAS de Chrome, hasFocus/visibilityState dan True en todas
    (cada una es la activa de su ventana). El unico desempate confiable es
    preguntarle a Windows que VENTANA esta al frente (por su titulo)."""
    pages = [pg for pg in ctx.pages if not pg.is_closed()]
    if not pages:
        return ctx.new_page()

    def _real(pg):
        u = pg.url or ""
        return bool(u) and not u.startswith(("about:", "chrome:", "edge:", "devtools:"))

    # 1) la pestania cuyo titulo coincide con la VENTANA que esta al frente en Windows
    wt = _titulo_ventana_frente()
    if wt:
        for pg in pages:
            if not _real(pg):
                continue
            try:
                t = (pg.title() or "").strip()
            except Exception:
                continue
            if len(t) >= 3 and (t in wt or wt in t):
                print("pagina activa (ventana al frente):", pg.url, flush=True)
                return pg

    # 2) fallback: alguna con foco/visible y URL real
    for pg in reversed(pages):
        try:
            if _real(pg) and (pg.evaluate("document.hasFocus()") or
                              pg.evaluate("document.visibilityState") == "visible"):
                print("pagina activa (foco/visible):", pg.url, flush=True)
                return pg
        except Exception:
            continue
    # 3) fallback final: ultima con URL real
    for pg in reversed(pages):
        if _real(pg):
            print("pagina activa (fallback):", pg.url, flush=True)
            return pg
    return pages[-1]


@contextmanager
def _chrome():
    """Conecta al Chrome IA por CDP (lo abre solo si no esta). Devuelve la pestaña activa."""
    _asegurar_chrome()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP, timeout=8000)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _pagina_activa(ctx)
            page.set_default_timeout(8000)              # nada se cuelga: falla a los 8s
            page.set_default_navigation_timeout(15000)
            yield page
        finally:
            browser.close()   # solo cierra la conexion CDP, no el navegador


def esta_disponible():
    return _asegurar_chrome()


def leer_pagina():
    with _chrome() as page:
        try:
            titulo = page.title()
        except Exception:
            titulo = ""
        try:
            texto = page.inner_text("body", timeout=8000)
        except Exception:
            texto = ""
        return titulo, texto[:6000]


def _rect_monitor_cursor():
    """Rectangulo del monitor donde esta el mouse."""
    import mss
    import pyautogui
    x, y = pyautogui.position()
    with mss.MSS() as sct:
        for mon in sct.monitors[1:]:
            if mon["left"] <= x < mon["left"] + mon["width"] and mon["top"] <= y < mon["top"] + mon["height"]:
                return mon
        return sct.monitors[1]


def _hwnds_chrome_ia():
    """HWNDs visibles del proceso Chrome IA (el que escucha en 9222)."""
    import ctypes
    from ctypes import wintypes
    import psutil
    pids = set()
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == 9222 and c.status == "LISTEN" and c.pid:
                pids.add(c.pid)
                # incluir procesos hijos (Chrome usa varios)
        # el proceso que escucha es el browser principal; sus ventanas top-level son las del Chrome IA
    except Exception:
        pass
    if not pids:
        return []
    user32 = ctypes.windll.user32
    res = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value in pids:
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                if cls.value == "Chrome_WidgetWin_1":     # ventana principal de Chrome
                    r = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                    area = (r.right - r.left) * (r.bottom - r.top)
                    res.append((area, hwnd))
        return True

    user32.EnumWindows(cb, 0)
    res.sort(reverse=True)                                # la mas grande primero = ventana real
    return [h for _, h in res]


def _colocar_en_monitor_cursor():
    """Trae la ventana del Chrome IA al escritorio virtual actual y al monitor del cursor (API Windows)."""
    import ctypes
    try:
        mon = _rect_monitor_cursor()
        hwnds = _hwnds_chrome_ia()
        if not hwnds:
            return
        hwnd = hwnds[0]
        # 1) traerla al escritorio virtual actual
        try:
            from pyvda import AppView, VirtualDesktop
            AppView(hwnd=hwnd).move(VirtualDesktop.current())
        except Exception:
            pass
        # 2) mover/redimensionar al monitor del cursor + al frente (coords fisicas, requiere DPI-aware)
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)                 # SW_RESTORE
        user32.SetWindowPos(hwnd, 0, mon["left"], mon["top"], mon["width"], mon["height"], 0x0040)  # SWP_SHOWWINDOW
        user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print("no pude colocar la ventana:", e, flush=True)


def abrir(url):
    """Abre la URL en una PESTAÑA NUEVA, en el monitor del cursor, y la trae al frente."""
    _asegurar_chrome()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP, timeout=8000)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            page.set_default_navigation_timeout(20000)
            u = url.strip()
            if not u.startswith("http"):
                u = "https://" + u
            page.goto(u, wait_until="domcontentloaded", timeout=20000)
            try:
                page.bring_to_front()
            except Exception:
                pass
            _colocar_en_monitor_cursor()      # escritorio virtual actual + monitor del cursor (API Windows)
            return page.title()
        finally:
            browser.close()


def clic(texto):
    with _chrome() as page:
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            page.get_by_role("button", name=texto, exact=False).first.click(timeout=4000)
        except Exception:
            try:
                page.get_by_role("link", name=texto, exact=False).first.click(timeout=4000)
            except Exception:
                page.get_by_text(texto, exact=False).first.click(timeout=4000)
        return True


def escribir(texto):
    with _chrome() as page:
        page.keyboard.type(texto)
        return True


def cerrar_pestanas():
    """Cierra TODAS las pestañas y deja una en blanco (para no cerrar el navegador)."""
    _asegurar_chrome()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP, timeout=8000)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            viejas = [pg for pg in ctx.pages if not pg.is_closed()]
            blank = ctx.new_page()                 # dejar una en blanco primero
            n = 0
            for pg in viejas:
                try:
                    pg.close(); n += 1
                except Exception:
                    pass
            return n
        finally:
            browser.close()


def cerrar_pestana_actual():
    """Cierra la pestaña activa (deja una en blanco si era la ultima)."""
    _asegurar_chrome()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP, timeout=8000)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _pagina_activa(ctx)
            restantes = [pg for pg in ctx.pages if not pg.is_closed() and pg != page]
            if not restantes:
                ctx.new_page()
            page.close()
            return True
        finally:
            browser.close()


def es_foreground():
    """True si la ventana activa de Windows es el Chrome IA (el usuario esta mirando el navegador)."""
    try:
        import ctypes
        fg = ctypes.windll.user32.GetForegroundWindow()
        return fg in _hwnds_chrome_ia()
    except Exception:
        return False


def clic_inteligente(descripcion):
    """Clic por DOM (preciso, SIN mover el mouse): por titulo/texto o por posicion. True si clickeo."""
    _asegurar_chrome()
    d = descripcion.lower().strip()
    # indice (primer/segundo/... o numero)
    idx = None
    for k, v in _ORDINAL.items():
        if re.search(r"\b" + k + r"\b", d):
            idx = v
            break
    m = re.search(r"\b(\d+)\b", d)
    if m:
        idx = int(m.group(1))
    # titulo: sacar muletillas y quedarnos con el texto real a buscar
    titulo = re.sub(r"\b(el|la|los|las|un|una|de|del|al|en|sobre|que|dice|se|llama|llamado|titulad[oa]|"
                    r"nombre|aparece|ahi|aca|mi|navegador|verdad|porfa|porfavor|che|quiero|busca\w*|"
                    r"primer\w*|segund\w*|tercer\w*|cuart\w*|quint\w*|ultim\w*|"
                    r"pon\w*|reproduc\w+|dale|play|abr[ií]\w*|abrime|ver|mostr\w*|muestr\w*|puede\w*|pod[eé]s|"
                    r"eleg\w*|seleccion\w*|clic\w*|click\w*|toca\w*|apreta\w*|pulsa\w*|hacer|haces|hace|"
                    r"video|clip|cancion|tema|musica|pelicula|peli|capitulo|resultado|link|enlace|boton|item|opcion|pesta\w+)\b|\d+", "", d)
    titulo = re.sub(r"[¿?¡!,.]", " ", titulo)
    titulo = re.sub(r"\s+", " ", titulo).strip()
    print(f"clic_inteligente: desc={descripcion!r} idx={idx} titulo={titulo!r}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP, timeout=8000)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _pagina_activa(ctx)
            page.set_default_timeout(6000)
            try:
                page.bring_to_front()
                page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass

            base = "https://www.youtube.com" if "youtube.com" in (page.url or "") else ""

            def _activar(el):
                """Si el elemento es un link, NAVEGA a su href (evita el lio de 'no visible'); si no, clickea."""
                try:
                    href = el.get_attribute("href", timeout=2000)
                except Exception:
                    href = None
                if href and not href.startswith("javascript"):
                    u = href if href.startswith("http") else base + href
                    page.goto(u, wait_until="domcontentloaded", timeout=15000)
                    return True
                el.click(timeout=4000, force=True)
                return True

            # 1) por TITULO/TEXTO (lo mas confiable: "el video que dice Shake It")
            if len(titulo) >= 3:
                for intento in (
                    lambda: page.get_by_role("link", name=titulo, exact=False).first,
                    lambda: page.locator(f"a[title*='{titulo}' i]").first,
                    lambda: page.get_by_text(titulo, exact=False).first,
                ):
                    try:
                        if _activar(intento()):
                            return True
                    except Exception:
                        continue

            # 2) por TIPO + POSICION
            if "video" in d:
                cards = page.locator("ytd-rich-item-renderer, ytd-video-renderer, "
                                     "ytd-compact-video-renderer, ytd-grid-video-renderer")
                nc = cards.count()
                if nc:
                    i = (nc - 1) if idx == -1 else (min(idx - 1, nc - 1) if idx else 0)
                    try:
                        return _activar(cards.nth(i).locator("a[href*='/watch']").first)
                    except Exception:
                        return False
                loc = page.locator("a[href*='/watch']")
            elif any(w in d for w in ("resultado", "link", "enlace", "noticia")):
                loc = page.locator("a[href]:visible")
            elif "boton" in d:
                loc = page.locator("button:visible, [role=button]:visible")
                n = loc.count()
                if n:
                    i = (n - 1) if idx == -1 else (min(idx - 1, n - 1) if idx else 0)
                    loc.nth(i).click(timeout=5000, force=True)
                    return True
                return False
            else:
                loc = page.locator("a[href]:visible")
            n = loc.count()
            if n:
                i = (n - 1) if idx == -1 else (min(idx - 1, n - 1) if idx else 0)
                try:
                    return _activar(loc.nth(i))
                except Exception:
                    return False
            return False
        finally:
            browser.close()


def navegar(accion):
    with _chrome() as page:
        a = accion.lower()
        if "atras" in a or "volver" in a:
            page.go_back()
        elif "adelante" in a:
            page.go_forward()
        elif "recarg" in a or "actualiz" in a:
            page.reload()
        elif "abajo" in a:
            page.mouse.wheel(0, 800)
        elif "arriba" in a:
            page.mouse.wheel(0, -800)
        return True


if __name__ == "__main__":
    print("Chrome IA disponible:", esta_disponible())
    if esta_disponible():
        t, txt = leer_pagina()
        print("Titulo:", t)
        print("Texto (inicio):", txt[:300])
