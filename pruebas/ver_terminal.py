"""La terminal adentro de /sesiones, vista en un navegador de verdad (2026-11-10).

Martín: *"hay cosas de Claude Code que podríamos agregar a este panel, como la terminal"*.
`probar_terminal` cuida el lado del servidor (los candados, la memoria, el tope). Esta cuida
lo que se ve y se toca:
  · que la pestaña Terminal aparezca, abra una terminal en la carpeta de la charla, y que lo
    que tipeás llegue a un PowerShell de verdad y vuelva dibujado;
  · que al mirar otra pieza la terminal se desconecte (no gasta mientras no se ve) y al
    volver traiga lo que había;
  · ⭐ que el ▶ de un bloque de código ESCRIBA el comando en la terminal y NO lo ejecute
    (el Enter es de Martín), y que ya no llame a la ventana de PowerShell;
  · que el ＋ abra otra y la ✕ la cierre, y que se entere cuando estirás la columna.

⚠ No usa las terminales del panel: levanta un servidor chico aparte con las mismas rutas
(`crear_router`), en un puerto libre, y la página le habla a ese. Así anda antes y después
de reiniciar el panel, y no deja nada abierto en el de verdad. La página (`sesiones.html`,
`marcado.js`) sí es la del panel prendido; al panel solo le llegan pedidos de lectura.
Fija su propio aspecto y sus propios datos.

Correr con:  python -m pruebas.ver_terminal   (con el panel prendido)
"""
import ctypes
import json
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS
from app.voz import terminales

BASE = "http://127.0.0.1:8750"
fallas = []
AHORA = time.time()
SID = "termin-0000-0000-000000000000"
CARPETA = Path(tempfile.mkdtemp(prefix="ver_terminal_"))
terminales.LOGS = CARPETA                      # que no escriba en el registro de verdad
BLOQUE = 'echo ("pe"+"gado-"+(40+2))'
SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa"], "ocultas": []},
            "proyectos": [{"proyecto": "alfa", "cwd": str(CARPETA), "vivo": False, "sesiones": [
                {"id": SID, "nombre": "charla de prueba", "ts": AHORA - 600, "ultimo": "claude",
                 "viva": False, "ocupada": False, "interactiva": False, "detalle": "x"}]}]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None, "mensajes": [
    {"de": "vos", "texto": "pasame el comando", "imgs": []},
    {"de": "claude", "texto": "Corré esto:\n\n```powershell\n" + BLOQUE + "\n```\n", "imgs": []}]}
ENTORNO = {"ok": True, "maquina": "compu-de-prueba", "carpeta": str(CARPETA), "nombre": "alfa",
           "remoto_posible": False, "remoto": {}, "contexto": None, "conectores": [],
           "conectores_de": "ahora", "cerebro": "claude", "navegador": None}
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}


def campos_del_estilo(k):
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def revisar(nombre, obtenido, esperado=True):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)[:160]
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def consolas_a_la_vista():
    vistas, u32 = set(), ctypes.windll.user32
    tipo = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cada(h, _):
        if u32.IsWindowVisible(h):
            clase = ctypes.create_unicode_buffer(80)
            u32.GetClassNameW(h, clase, 80)
            if clase.value in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"):
                vistas.add(h)
        return True
    u32.EnumWindows(tipo(cada), 0)
    return vistas


def servidor_chico():
    """Las rutas de la terminal en un puerto libre, aceptando a la página del panel."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[BASE], allow_methods=["*"], allow_headers=["*"])
    app.include_router(terminales.crear_router(origenes_extra=(BASE,)))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    fin = time.time() + 10
    while time.time() < fin and not srv.started:
        time.sleep(0.05)
    return srv, f"http://127.0.0.1:{puerto}"


def montar(nav, aspecto, chico):
    ctx = nav.new_context(viewport={"width": 1500, "height": 900}, reduced_motion="reduce")
    errores, pedidos = [], {"correr": 0}

    def portero(r):
        url = r.request.url
        if not url.startswith(BASE):
            # El Ctrl+K se ataja: si no, cada corrida le preguntaría a Claude de verdad.
            if url.split("?")[0].endswith("/terminal/sugerir"):
                pedidos["sugerir"] = pedidos.get("sugerir", 0) + 1
                pedidos["ultimo_pedido"] = r.request.post_data_json
                return r.fulfill(status=200, content_type="application/json", headers={
                    "Access-Control-Allow-Origin": BASE},
                    body=json.dumps({"ok": True, "comando": 'echo ("su"+"gerido-"+(5*5))', "error": ""}))
            return r.continue_()               # lo del servidor chico pasa de largo
        camino = url.split(BASE, 1)[-1].split("?")[0]
        if camino == "/movil/mandar":
            pedidos["mandar"] = pedidos.get("mandar", 0) + 1
        if camino == "/correr":
            pedidos["correr"] += 1
            return r.fulfill(status=200, content_type="application/json", body='{"ok": true}')
        if camino == "/estaticos/terminal.js":  # del disco: el panel puede no servirla todavía
            return r.fulfill(status=200, content_type="application/javascript",
                             body=(ESTATICOS / "terminal.js").read_text(encoding="utf-8"))
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            cuerpo = CHAT
        elif camino == "/movil/entorno":
            cuerpo = ENTORNO
        elif camino == "/aspecto" and r.request.method == "GET":
            cuerpo = aspecto
        elif r.request.method != "GET" or camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
            cuerpo = {"ok": True}
        else:
            return r.continue_()
        return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    pag.add_init_script("localStorage.clear(); localStorage.setItem('sesDerecha', '1');"
                        "window.TERMINAL_BASE = " + json.dumps(chico) + ";")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=20000)
    pag.wait_for_timeout(500)
    pag.evaluate("""([sid, cwd]) => { pendientes = {}; falladas = {}; visto = {};
      abiertas = [{sid, cwd, nombre: 'charla de prueba', cerebro: ''}];
      irTab(sid); firma = ''; cargar(); }""", [SID, str(CARPETA)])
    pag.wait_for_selector("#hilo .md-bloque", timeout=20000)
    pag.wait_for_timeout(600)
    return ctx, pag, errores, pedidos


PANTALLA = """() => { const f = document.querySelector('.derPane[data-pieza="terminal"] .xterm-rows');
  return f ? f.innerText.replace(/\\u00a0/g, ' ') : ''; }"""


def espera_en_pantalla(pag, texto, segundos=30):
    fin = time.time() + segundos
    while time.time() < fin:
        if texto in pag.evaluate(PANTALLA):
            return True
        pag.wait_for_timeout(200)
    return False


def conectada(pag, segundos=30):
    try:
        pag.wait_for_function("() => window.Consola && Consola.estado().conectada", timeout=segundos * 1000)
        return True
    except Exception:
        return False


def main():
    chico, direccion = servidor_chico()
    antes = consolas_a_la_vista()
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch(headless=True)
            ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO), direccion)

            pest = pag.evaluate("() => [...document.querySelectorAll('#derTabs button')].map(b => b.textContent)")
            revisar("⭐ la columna tiene la pestaña Terminal al lado de Entorno", pest, ["Entorno", "Terminal"])
            revisar("y todavía no abrió ninguna: sin mirarla no gasta nada",
                    [len(terminales.lista()), pag.evaluate("() => Consola.estado().visible")], [0, False])
            pag.click("#derTabs button[data-pieza='terminal']")
            revisar("al elegirla se conecta a una terminal", conectada(pag))
            e = pag.evaluate("() => Consola.estado()")
            revisar("⭐ abierta en la carpeta de la charla",
                    [len(terminales.lista()), Path(terminales.lista()[0]["cwd"]) == CARPETA if terminales.lista() else None],
                    [1, True])
            ancho = pag.evaluate("() => Math.round(document.querySelector('#derecha').getBoundingClientRect().width)")
            revisar(f"la columna se ensanchó sola para que entre ({ancho} px)", ancho >= 556)
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            pag.keyboard.type('echo ("ho"+"la-"+(100+23))')
            pag.keyboard.press("Enter")
            revisar("⭐ lo que tipeás llega a un PowerShell de verdad y la respuesta se dibuja",
                    espera_en_pantalla(pag, "hola-123"))

            # Mirar otra pieza la desconecta; al volver trae lo que había.
            pag.click("#derTabs button[data-pieza='entorno']")
            pag.wait_for_timeout(400)
            revisar("⭐ mirando Entorno, la terminal se desconecta (pero sigue viva en el servidor)",
                    [pag.evaluate("() => Consola.estado().conectada"), len(terminales.lista())], [False, 1])
            pag.click("#derTabs button[data-pieza='terminal']")
            revisar("al volver se conecta a LA MISMA", conectada(pag) and
                    pag.evaluate("() => Consola.estado().actual") == e["actual"])
            revisar("⭐ y trae lo que ya se había escrito", espera_en_pantalla(pag, "hola-123", 8))

            # ⭐⭐ El ▶ de un bloque de código: escribe, no ejecuta.
            pag.click("#derTabs button[data-pieza='entorno']")       # desde otra pieza, a propósito
            pag.wait_for_timeout(300)
            pag.hover("#hilo .md-bloque")
            pag.click("#hilo .md-bloque .md-bt[data-md='correr']")
            revisar("el ▶ trae la terminal al frente", conectada(pag) and
                    pag.evaluate("() => Paneles.actual()") == "terminal")
            revisar("⭐ y ESCRIBE el comando del bloque", espera_en_pantalla(pag, '"gado-"', 10))
            pag.wait_for_timeout(1500)
            revisar("⭐⭐ sin ejecutarlo: el Enter es tuyo", "pegado-42" in pag.evaluate(PANTALLA), False)
            revisar("y ya no le pide al panel la ventana de PowerShell", pedidos["correr"], 0)
            pag.keyboard.press("Enter")
            revisar("con tu Enter, corre", espera_en_pantalla(pag, "pegado-42"))

            # Estirar la columna: la terminal se entera.
            cols = pag.evaluate("() => Consola.estado().cols")
            c = pag.evaluate("""() => { const r = document.querySelector('#tiradorDer').getBoundingClientRect();
                                 return [r.left + r.width / 2, r.top + r.height / 2]; }""")
            pag.mouse.move(c[0], c[1])
            pag.mouse.down()
            pag.mouse.move(c[0] - 160, c[1], steps=6)
            pag.mouse.up()
            pag.wait_for_timeout(700)
            nuevas = pag.evaluate("() => Consola.estado().cols")
            revisar(f"⭐ al estirar la columna la terminal gana renglón ({cols} → {nuevas} letras)", nuevas > cols)
            pag.keyboard.type('echo ("ancho="+[Console]::WindowWidth)')
            pag.keyboard.press("Enter")
            revisar("y el PowerShell se entera del ancho nuevo", espera_en_pantalla(pag, "ancho=" + str(nuevas)))

            # Otra terminal, y cerrarla.
            pag.click(".conMas")
            pag.wait_for_function("() => Consola.estado().cuantas === 2 && Consola.estado().conectada", timeout=30000)
            revisar("el ＋ abre otra terminal en la misma carpeta",
                    [len(terminales.lista()), pag.evaluate("() => document.querySelectorAll('.conTab').length")], [2, 2])
            pag.click(".conTab.sel .x")
            pag.wait_for_function("() => Consola.estado().cuantas === 1", timeout=15000)
            pag.wait_for_timeout(600)
            revisar("la ✕ la cierra de verdad y vuelve a la que quedaba",
                    [len([t for t in terminales.lista() if t["viva"]]), conectada(pag, 10)], [1, True])
            revisar("⭐ nada de esto abrió una ventana de consola", consolas_a_la_vista() <= antes)
            revisar("sin errores de JS", errores, [])
            ctx.close()

            # --- La segunda vuelta: ajustes y lo de Cursor -----------------------------------
            # Martín: *"faltan configuraciones de la terminal… me gustaría agregarle cosas que
            # tiene Cursor también"*.
            ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO), direccion)
            pag.click("#derTabs button[data-pieza='terminal']")
            revisar("[2ª] la terminal se conecta", conectada(pag))
            esperar_prompt = lambda: pag.wait_for_function(
                "() => /PS .*>\\s*$/.test((document.querySelector('.derPane[data-pieza=\"terminal\"] .xterm-rows') || {}).innerText || '')",
                timeout=30000)
            esperar_prompt()
            # Ajustes: el tamaño de letra y el cursor se aplican en el acto y quedan guardados.
            pag.click(".conBot[data-hace='ajustes']")
            pag.fill(".conMenu[data-menu='ajustes'] input[data-a='tam']", "17")
            pag.dispatch_event(".conMenu[data-menu='ajustes'] input[data-a='tam']", "change")
            pag.select_option(".conMenu[data-menu='ajustes'] select[data-a='cursor']", "bar")
            e = pag.evaluate("() => Consola.estado()")
            revisar("⭐ ⚙ cambia el tamaño de letra y la forma del cursor en el acto",
                    [e["tam"], e["cursor"]], [17, "bar"])
            revisar("y quedan guardados", pag.evaluate("() => JSON.parse(localStorage.getItem('sesTerm')||'{}').tam"), 17)
            pag.keyboard.press("Escape")
            revisar("Escape cierra el menú de ajustes", pag.evaluate(
                "() => document.querySelector('.conMenu[data-menu=\"ajustes\"]').hidden"))
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            pag.keyboard.press("Control+-")
            revisar("Ctrl − achica la letra", pag.evaluate("() => Consola.estado().tam"), 16)
            pag.keyboard.press("Control+0")
            revisar("Ctrl 0 la vuelve a la de fábrica", pag.evaluate("() => Consola.estado().tam"), 13)

            # Los puntitos y el "falló": la integración del PowerShell.
            pag.keyboard.type("cmd /c exit 3")
            pag.keyboard.press("Enter")
            pag.wait_for_function("() => Consola.estado().fallo", timeout=20000)
            e = pag.evaluate("() => Consola.estado()")
            revisar("⭐ un comando que falla se reconoce, con su código",
                    e["comandos"][-1] if e["comandos"] else None, {"cmd": "cmd /c exit 3", "codigo": 3})
            revisar("⭐ y aparece el cartel de que falló", pag.evaluate(
                "() => !document.querySelector('[data-barra=\"fallo\"]').hidden"))
            revisar("con su puntito rojo al costado", pag.evaluate("() => !!document.querySelector('.conPunto.mal')"))
            pag.click("[data-barra='fallo'] [data-hace='arreglar']")
            pag.wait_for_timeout(300)
            caja_txt = pag.evaluate("() => document.querySelector('#texto').value")
            revisar("⭐⭐ «Arreglalo con la sesión» deja en la caja el comando y su código, SIN mandarlo",
                    ["cmd /c exit 3" in caja_txt, "código 3" in caja_txt, pedidos.get("mandar", 0)], [True, True, 0])
            pag.evaluate("() => { const c = document.querySelector('#texto'); c.value = ''; }")
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            esperar_prompt()
            pag.keyboard.type('echo ("bi"+"en")')
            pag.keyboard.press("Enter")
            # ⚠ Se espera ESTE comando, no "dos comandos": la terminal puede ser la de la parte
            # de arriba (misma carpeta), y su repaso ya trae comandos viejos con su puntito.
            pag.wait_for_function("() => Consola.estado().comandos.some(c => c.cmd.includes('\"bi\"'))", timeout=20000)
            revisar("un comando que anda lleva su puntito verde y se lleva el cartel de falla",
                    [pag.evaluate("() => Consola.estado().comandos.slice(-1)[0].codigo"),
                     pag.evaluate("() => document.querySelector('[data-barra=\"fallo\"]').hidden")], [0, True])

            # Ctrl+K: lo que querés en tus palabras → el comando escrito, sin ejecutar.
            pag.keyboard.press("Control+k")
            revisar("⭐ Ctrl+K abre la barra para pedir un comando", pag.evaluate(
                "() => !document.querySelector('[data-barra=\"pedir\"]').hidden && document.activeElement.closest('[data-barra=\"pedir\"]') !== null"))
            pag.keyboard.type("calculá 25")
            pag.keyboard.press("Enter")
            revisar("⭐ escribe el comando que le devuelve el panel", espera_en_pantalla(pag, '"gado-"') or
                    espera_en_pantalla(pag, '"gerido-"', 15))
            pag.wait_for_timeout(1200)
            revisar("⭐⭐ sin ejecutarlo", "sugerido-25" in pag.evaluate(PANTALLA), False)
            revisar("y al panel le mandó lo pedido con el programa y la carpeta",
                    [(pedidos.get("ultimo_pedido") or {}).get("pedido"), (pedidos.get("ultimo_pedido") or {}).get("shell")],
                    ["calculá 25", "pwsh"])
            pag.keyboard.press("Enter")
            revisar("con tu Enter, corre", espera_en_pantalla(pag, "sugerido-25"))

            # Seleccionar → mandar a la charla.
            filas = pag.locator(".derPane[data-pieza='terminal'] .xterm-rows > div")
            fila = next((i for i in range(filas.count()) if "sugerido-25" in filas.nth(i).inner_text()
                         and "echo" not in filas.nth(i).inner_text()), None)
            if fila is not None:
                # ⚠ Arrastrando con el mouse en el lugar, no sobre el renglón: xterm pone una
                # capa encima de los renglones y es ella la que recibe el mouse.
                caja_f = filas.nth(fila).bounding_box()
                y = caja_f["y"] + caja_f["height"] / 2
                pag.mouse.move(caja_f["x"] + 2, y)
                pag.mouse.down()
                pag.mouse.move(caja_f["x"] + 60, y, steps=5)
                pag.mouse.up()
                pag.wait_for_timeout(300)

            pag.wait_for_timeout(400)          # lo que tarda xterm en volver a medirse, si lo hiciera
            revisar("⭐ al seleccionar aparece «Mandar a la charla», y la selección NO se borra sola",
                    [pag.evaluate("() => !document.querySelector('[data-barra=\"sel\"]').hidden"),
                     bool(pag.evaluate("() => Consola.estado().seleccion"))], [True, True])
            pag.click("[data-barra='sel'] [data-hace='selChat']")
            pag.wait_for_timeout(200)
            revisar("⭐ y lo pega en la caja de la charla, en un bloque", pag.evaluate(
                "() => document.querySelector('#texto').value.includes('```')"))
            pag.evaluate("() => { document.querySelector('#texto').value = ''; }")

            # Buscar.
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            pag.keyboard.press("Control+f")
            revisar("Ctrl+F abre la búsqueda", pag.evaluate(
                "() => !document.querySelector('[data-barra=\"buscar\"]').hidden"))
            pag.keyboard.type("bien")
            pag.keyboard.press("Enter")
            pag.wait_for_timeout(300)
            revisar("y encuentra", "no está" not in pag.evaluate(
                "() => document.querySelector('[data-barra=\"buscar\"] .cuenta').textContent"))
            pag.keyboard.press("Escape")

            # Otro programa: ▾ → CMD.
            pag.click(".conMasSh")
            pag.click(".conMenu[data-menu='shell'] [data-sh='cmd']")
            pag.wait_for_function("() => Consola.estado().shell === 'cmd' && Consola.estado().conectada", timeout=30000)
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            pag.wait_for_timeout(1500)
            pag.keyboard.type("echo %COMSPEC%")
            pag.keyboard.press("Enter")
            revisar("⭐ ▾ abre otra terminal con el programa elegido (CMD)", espera_en_pantalla(pag, "cmd.exe"))
            revisar("y su pestaña dice cuál es", pag.evaluate(
                "() => document.querySelector('.conTab.sel .sh') ? document.querySelector('.conTab.sel .sh').textContent : ''"), "CMD")

            # Renombrar con doble clic.
            pag.dblclick(".conTab.sel")
            pag.keyboard.type("servidor")
            pag.keyboard.press("Enter")
            revisar("doble clic en la pestaña le cambia el nombre, y queda",
                    [pag.evaluate("() => document.querySelector('.conTab.sel').textContent.startsWith('servidor')"),
                     "servidor" in pag.evaluate("() => localStorage.getItem('sesTermNombres') || ''")], [True, True])

            # Agrandar.
            antes = pag.evaluate("() => Math.round(document.querySelector('#derecha').getBoundingClientRect().width)")
            pag.click(".conBot[data-hace='agrandar']")
            pag.wait_for_timeout(300)
            grande = pag.evaluate("() => Math.round(document.querySelector('#derecha').getBoundingClientRect().width)")
            charla = pag.evaluate("() => Math.round(document.querySelector('#cuerpo').getBoundingClientRect().width)")
            pag.click(".conBot[data-hace='agrandar']")
            pag.wait_for_timeout(300)
            vuelta = pag.evaluate("() => Math.round(document.querySelector('#derecha').getBoundingClientRect().width)")
            revisar(f"⤢ agranda la columna dejándole su piso a la charla ({antes} → {grande} px, charla {charla}) y la devuelve",
                    [grande > antes + 200, charla >= 415, abs(vuelta - antes) <= 3], [True, True, True])
            revisar("[2ª] sin errores de JS", errores, [])
            ctx.close()

            # Con Vidrio: se dibuja y se lee.
            # ⚠ Desde cero: si no, se engancha a la última terminal de la carpeta, que es la de
            # CMD de arriba, y ahí un comando de PowerShell no da lo que se espera.
            terminales.cerrar_todas()
            ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO, estilo="vidrio", **campos_del_estilo("vidrio")),
                                                direccion)
            pag.click("#derTabs button[data-pieza='terminal']")
            revisar("Vidrio: la terminal se conecta", conectada(pag))
            # ⚠ Tipear recién con el renglón a la vista: lo que llega antes de que el PowerShell
            # termine de arrancar se pierde, y la prueba fallaba de a ratos por eso.
            pag.wait_for_function(
                "() => /(PS .*>|>)\s*$/.test((document.querySelector('.derPane[data-pieza=\"terminal\"] .xterm-rows') || {}).innerText || '')",
                timeout=30000)
            pag.click(".derPane[data-pieza='terminal'] .xterm")
            pag.keyboard.type('echo ("vi"+"drio-"+(3*3))')
            pag.keyboard.press("Enter")
            revisar("Vidrio: se dibuja lo que contesta", espera_en_pantalla(pag, "vidrio-9"))
            tinta = pag.evaluate("""() => getComputedStyle(document.querySelector('.derPane[data-pieza="terminal"] .xterm-rows')).color""")
            revisar("Vidrio: la letra tiene color (no quedó transparente)", tinta not in ("rgba(0, 0, 0, 0)", "transparent"))
            revisar("sin errores de JS con Vidrio", errores, [])
            ctx.close()
            nav.close()
    finally:
        terminales.cerrar_todas()
        chico.should_exit = True
        time.sleep(0.8)
        shutil.rmtree(CARPETA, ignore_errors=True)
    print()
    if fallas:
        print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
        return 1
    print("TODO BIEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
