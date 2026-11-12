"""La pieza "Escritorio" EN PANTALLA, con un Chrome de verdad (Playwright) y SIN ningun RustDesk.

    python -m pruebas.ver_escritorio

Sirve en otro puerto (no el panel) el `escritorio.js` real y las rutas reales de
`app/voz/escritorio.py`, montadas sobre la puerta de mentira de `probar_escritorio`. Mira lo
que solo se ve en un navegador: que un clic en la imagen ACHICADA caiga en el pixel correcto de
la pantalla remota, que las teclas lleguen en orden, y que la pieza pase sola por sus estados.
Deja las capturas en resultados/ver_escritorio/.
"""
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright

from app.rutas import RESULTADOS
from app.voz import escritorio
from pruebas.probar_escritorio import Montaje, Proc

SALIDA = RESULTADOS / "ver_escritorio"
OK, MAL = [], []


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    print(("  ✓ " if cond else "  ✗ ") + nombre + ("" if cond else f"  {str(detalle)[:400]}"))


PAGINA = """<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#0f1420;font-family:Segoe UI,system-ui,sans-serif">
<!-- Armada como en el panel: la columna es una caja flexible de alto fijo, y la pieza un hijo
     que se estira y scrollea (`.derPane`). Importa: de eso depende que la imagen entre entera. -->
<div style="display:flex;flex-direction:column;width:%dpx;height:%dpx">
<div id="caja" style="flex:1 1 auto;min-height:0;overflow-y:auto;padding:12px 12px 20px"></div></div>
<script src="/estaticos/escritorio.js"></script>
<script>Escritorio.iniciar({agrandar: () => { window.agrando = (window.agrando || 0) + 1; }});
Escritorio.mostrar(document.getElementById('caja'));</script>"""


def main():
    m = Montaje()
    m.oficiales.append(Proc("oficial"))          # arranca con el RustDesk de siempre abierto
    f = m.falsa
    app = FastAPI()
    app.include_router(escritorio.crear_router())

    @app.get("/")
    def pagina(ancho: int = 424, alto: int = 632):
        return HTMLResponse(PAGINA % (ancho, alto))

    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=Montaje._libre(), log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{srv.config.port}/"
    SALIDA.mkdir(parents=True, exist_ok=True)
    # La puerta de mentira anota TAMBIEN lo que la pieza pide sola (la imagen, el estado).
    # Las cuentas de "que mandaste" miran solo lo que hace una persona: `hechas()`.
    SOLAS = ("screenshot", "list_sessions", "list_peers", "get_session")
    hechas = lambda: [c for c in f.llamadas if c[0] not in SOLAS]

    def esperar(cond, seg=6):
        fin = time.time() + seg
        while time.time() < fin:
            if cond():
                return True
            time.sleep(0.05)
        return False

    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            pag = nav.new_page(viewport={"width": 430, "height": 640})
            errores = []
            pag.on("pageerror", lambda e: errores.append(str(e)))
            pag.goto(base)

            # 1. Apagada, con el RustDesk de siempre abierto: lo avisa antes de cerrarlo.
            pag.wait_for_selector("[data-prender]")
            texto = pag.inner_text("#caja")
            chequeo("apagada: avisa que va a cerrar tu RustDesk de siempre",
                    "Tu RustDesk de siempre está abierto" in texto
                    and pag.inner_text("[data-prender]") == "Cerrar mi RustDesk y prender", texto)
            chequeo("y que las sesiones van a poder conectarse sin pedir permiso",
                    "sin pedir permiso en la laptop" in texto)
            chequeo("mirar no prendió nada", not m.lanzados and not m.matados)
            pag.screenshot(path=str(SALIDA / "1_apagada.png"))
            pag.click("[data-prender]")
            pag.wait_for_selector("[data-equipos] .escrEq")
            chequeo("prender cierra el de siempre y abre la de prueba",
                    m.matados == ["oficial"] and m.lanzados == ["prueba.exe"], (m.matados, m.lanzados))

            # 2. Elegir un equipo.
            filas = pag.eval_on_selector_all(".escrEq", "fs => fs.map(f => [f.innerText.replace(/\\s+/g,' ').trim(), !!f.querySelector('.bola.si')])")
            chequeo("lista los equipos recientes con su punto de en línea",
                    filas == [["Fox SERVER", True], ["ventas1 SILVA", False]], filas)
            pag.screenshot(path=str(SALIDA / "2_elegir.png"))
            pag.click(".escrEq >> text=Fox")
            pag.wait_for_selector("form[data-clave] input")
            chequeo("pide la contraseña del equipo, en un campo tapado",
                    pag.get_attribute("form[data-clave] input", "type") == "password"
                    and "Fox" in pag.inner_text("#caja"))
            # Escribir despacio mientras la pieza se refresca cada 3 s: no se borra.
            pag.locator("form[data-clave] input").press_sequentially("mala", delay=900)
            chequeo("la contraseña a medio escribir sobrevive a los refrescos",
                    pag.input_value("form[data-clave] input") == "mala")
            pag.keyboard.press("Enter")
            pag.wait_for_function("document.querySelector('#caja').innerText.includes('Esa contraseña no es')")
            chequeo("contraseña mala: lo dice y no la muestra", "mala" not in pag.inner_text("#caja"))
            pag.fill("form[data-clave] input", "buena")
            pag.keyboard.press("Enter")
            pag.wait_for_selector(".escrLienzo img")
            pag.wait_for_function("(() => { const i = document.querySelector('.escrLienzo img'); return i && i.naturalWidth === 800; })()")
            medida = pag.eval_on_selector(".escrLienzo img", "i => [i.naturalWidth, i.naturalHeight, Math.round(i.getBoundingClientRect().width)]")
            chequeo("la pantalla llega (800x600) y se dibuja achicada al ancho de la columna",
                    medida[:2] == [800, 600] and 380 <= medida[2] <= 400, medida)
            chequeo("antes de tocar: 'mirando'", pag.inner_text("[data-modo]") == "mirando"
                    and pag.inner_text("[data-control]") == "Tomar control")
            pag.screenshot(path=str(SALIDA / "3_pantalla.png"))

            # 3. Un clic en la imagen ACHICADA cae en el pixel correcto de la pantalla REMOTA.
            caja = pag.eval_on_selector(".escrLienzo img", "i => { const c = i.getBoundingClientRect(); return [c.left, c.top, c.width, c.height]; }")
            escala = 800 / caja[2]
            f.llamadas.clear()
            pag.mouse.click(caja[0] + 100, caja[1] + 75)
            chequeo("el clic llega", esperar(lambda: any(n == "mouse" for n, _ in f.llamadas)), f.llamadas)
            ult = [a for n, a in f.llamadas if n == "mouse"][-1]
            chequeo("…en el pixel REMOTO que corresponde, no en el de la imagen chica",
                    ult["action"] == "click" and abs(ult["x"] - 100 * escala) <= 2 and abs(ult["y"] - 75 * escala) <= 2
                    and ult["x"] > 150, (ult, escala))
            chequeo("tocar la imagen tomó el control solo",
                    [n for n, _ in f.llamadas] == ["mouse", "request_control", "mouse"], f.llamadas)
            pag.wait_for_function("document.querySelector('[data-modo]').textContent === 'con control'")
            chequeo("y la barra lo dice", pag.inner_text("[data-control]") == "Soltar")

            # 4. El teclado, con la pantalla enfocada: en orden.
            f.llamadas.clear()
            pag.keyboard.type("ab", delay=20)
            pag.keyboard.press("Enter")
            pag.keyboard.type("c", delay=20)
            esperar(lambda: len(hechas()) >= 3)
            chequeo("letras juntas, la tecla y la letra siguiente, en el orden en que se tipearon",
                    hechas() == [("type_text", {"session_id": ult["session_id"], "text": "ab"}),
                                   ("press_key", {"session_id": ult["session_id"], "key": "Enter"}),
                                   ("type_text", {"session_id": ult["session_id"], "text": "c"})], f.llamadas)
            f.llamadas.clear()
            pag.keyboard.press("Control+c")
            pag.keyboard.press("F5")
            pag.keyboard.press("ArrowLeft")
            esperar(lambda: len(hechas()) >= 3)
            chequeo("Ctrl+C, F5 y la flecha van como teclas con nombre",
                    [(a.get("key"), a.get("modifiers")) for _, a in hechas()]
                    == [("c", ["ctrl"]), ("VK_F5", None), ("ArrowLeft", None)], f.llamadas)

            # 5. Arrastrar, la rueda y el clic derecho.
            f.llamadas.clear()
            pag.mouse.move(caja[0] + 40, caja[1] + 40)
            pag.mouse.down()
            pag.mouse.move(caja[0] + 120, caja[1] + 90, steps=5)
            pag.mouse.up()
            esperar(lambda: bool(hechas()))
            d = hechas()[-1][1]
            chequeo("arrastrar manda desde y hasta, en pixeles remotos",
                    d.get("action") == "drag" and abs(d["x"] - 40 * escala) <= 2 and abs(d["to_x"] - 120 * escala) <= 2
                    and abs(d["to_y"] - 90 * escala) <= 2, d)
            f.llamadas.clear()
            pag.mouse.move(caja[0] + 60, caja[1] + 60)
            pag.mouse.wheel(0, 300)
            esperar(lambda: bool(hechas()))
            chequeo("la rueda baja", hechas() and hechas()[-1][0] == "scroll"
                    and hechas()[-1][1]["direction"] == "down" and hechas()[-1][1]["amount"] == 3, hechas())
            f.llamadas.clear()
            pag.mouse.click(caja[0] + 60, caja[1] + 60, button="right")
            esperar(lambda: bool(hechas()))
            chequeo("clic derecho", hechas() and hechas()[-1][1].get("action") == "right_click", hechas())
            # El botón "Der" (para el celular): el PRÓXIMO toque es derecho, y solo ese.
            f.llamadas.clear()
            pag.click("[data-derecho]")
            pag.mouse.click(caja[0] + 60, caja[1] + 60)
            pag.mouse.click(caja[0] + 60, caja[1] + 60)
            esperar(lambda: len(hechas()) >= 2)
            chequeo("«Der»: el próximo toque es derecho y el siguiente vuelve a ser común",
                    [a.get("action") for _, a in hechas()] == ["right_click", "click"], f.llamadas)

            # 6. La fila de abajo (lo que se usa en el celular).
            f.llamadas.clear()
            pag.fill("form[data-texto] input", "hola desde abajo")
            pag.click("form[data-texto] button:text('Escribir')")
            pag.click("[data-tecla='Meta']")
            esperar(lambda: len(hechas()) >= 2)
            chequeo("escribir desde la fila de abajo, y la tecla Windows",
                    [(n, a.get("text") or a.get("key")) for n, a in hechas()]
                    == [("type_text", "hola desde abajo"), ("press_key", "Meta")], f.llamadas)

            # 7. La pantalla cambia sola.
            antes = pag.get_attribute(".escrLienzo img", "src")
            f.color = (40, 160, 70)
            chequeo("cuando la pantalla remota cambia, la imagen se actualiza",
                    esperar(lambda: pag.get_attribute(".escrLienzo img", "src") != antes, 6))
            pedidos = [n for n, _ in f.llamadas]
            pag.wait_for_timeout(1500)
            chequeo("la imagen se sigue pidiendo sola", len([n for n, _ in f.llamadas if n == "screenshot"])
                    > len([n for n in pedidos if n == "screenshot"]))
            pag.click("[data-agrandar]")
            chequeo("el ⤢ le pide a la columna que se agrande", pag.evaluate("window.agrando") == 1)
            pag.screenshot(path=str(SALIDA / "4_con_control.png"))

            # 7b. Columna ANCHA y BAJA (el Escritorio agrandado en una ventana chica): la
            #     pantalla entra entera, sin scroll, y el clic sigue cayendo donde corresponde.
            baja = nav.new_page(viewport={"width": 1100, "height": 440})
            baja.on("pageerror", lambda e: errores.append(str(e)))
            baja.goto(base + "?ancho=1060&alto=420")
            baja.wait_for_function("(() => { const i = document.querySelector('.escrLienzo img'); return i && i.naturalWidth === 800; })()")
            baja.wait_for_timeout(300)
            g = baja.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
              const i = r('.escrLienzo img'), c = r('#caja'), p = r('form[data-texto]'), k = document.querySelector('#caja');
              return {img: [Math.round(i.left), Math.round(i.top), Math.round(i.width), Math.round(i.height)],
                      imgAbajo: Math.round(i.bottom), pieArriba: Math.round(p.top), pieAbajo: Math.round(p.bottom),
                      cajaAbajo: Math.round(c.bottom), scroll: k.scrollHeight - k.clientHeight}; }""")
            chequeo("ventana baja: la pantalla entra ENTERA, arriba de la fila de escribir, y nada scrollea",
                    g["imgAbajo"] <= g["pieArriba"] and g["pieAbajo"] <= g["cajaAbajo"] and g["scroll"] <= 1
                    and g["img"][3] >= 200, g)
            chequeo("…sin deformarse (sigue siendo 4:3) y más angosta que la columna",
                    abs(g["img"][2] / g["img"][3] - 800 / 600) < 0.02 and g["img"][2] < 900, g)
            f.llamadas.clear()
            baja.mouse.click(g["img"][0] + g["img"][2] * 0.75, g["img"][1] + g["img"][3] * 0.5)
            esperar(lambda: bool(hechas()))
            cl = hechas()[-1][1] if hechas() else {}
            chequeo("y el clic en 3/4 del ancho y mitad del alto cae en (600, 300) de la pantalla remota",
                    abs(cl.get("x", 0) - 600) <= 3 and abs(cl.get("y", 0) - 300) <= 3, cl)
            baja.screenshot(path=str(SALIDA / "4b_ventana_baja.png"))
            baja.close()

            # 7c. Sumar OTRA compu sin cerrar la primera (2026-11-12: "que pueda seguir
            #     conectando equipos, pero no me desconectes el de Farah").
            fox = ult["session_id"]
            pag.click("[data-sumar]")
            pag.wait_for_selector("form[data-conectar]")
            chequeo("«+ Equipo» muestra la lista y la primera SIGUE conectada",
                    fox in f.sesiones and f.sesiones[fox]["ready"]
                    and pag.inner_text(".escrChips").strip() == "Fox"
                    and pag.inner_text(".escrTit") == "Conectar otro equipo", (list(f.sesiones), pag.inner_text("#caja")[:200]))
            pag.screenshot(path=str(SALIDA / "4c_sumar_equipo.png"))
            pag.click("[data-volver]")
            pag.wait_for_selector(".escrLienzo img")
            chequeo("«Volver» regresa a la pantalla sin tocar nada", pag.inner_text(".escrTit") == "Fox" and fox in f.sesiones)
            pag.click("[data-sumar]")
            pag.wait_for_selector("[data-equipos] .escrEq")
            pag.click(".escrEq >> text=ventas1")
            pag.wait_for_selector("form[data-clave] input")
            pag.fill("form[data-clave] input", "buena")
            pag.keyboard.press("Enter")
            pag.wait_for_function("document.querySelectorAll('.escrChips button').length === 2 && !!document.querySelector('.escrLienzo img')")
            botones = pag.eval_on_selector_all(".escrChips button", "bs => bs.map(b => [b.textContent, b.classList.contains('on')])")
            chequeo("quedan las DOS conectadas, con un botón cada una y la nueva a la vista",
                    len(f.sesiones) == 2 and f.sesiones[fox]["ready"] and botones == [["Fox", False], ["ventas1", True]],
                    (botones, list(f.sesiones)))
            pag.screenshot(path=str(SALIDA / "4d_dos_equipos.png"))
            pag.click(".escrChips button >> text=Fox")
            pag.wait_for_function("document.querySelector('.escrTit').textContent === 'Fox'")
            chequeo("el botón de cada compu cambia cuál se mira, sin cerrar ninguna", len(f.sesiones) == 2)
            pag.click("[data-apagar]")
            pag.wait_for_timeout(300)
            chequeo("«Apagar» con conexiones abiertas NO apaga al primer toque: avisa cuántas corta",
                    "2 conexiones" in pag.inner_text("[data-apagar]") and len(f.sesiones) == 2
                    and bool([p for p in m.prueba if p.vivo]), pag.inner_text("[data-apagar]"))
            pag.click(".escrChips button >> text=ventas1")
            pag.wait_for_function("document.querySelector('.escrTit').textContent === 'ventas1'")
            pag.click("[data-cortar]")
            pag.wait_for_function("document.querySelector('.escrTit').textContent === 'Fox'")
            chequeo("«Desconectar» cierra SOLO la que se mira: la otra sigue abierta",
                    list(f.sesiones) == [fox] and f.sesiones[fox]["ready"], list(f.sesiones))
            pag.wait_for_timeout(5200)          # que se desarme el segundo toque de Apagar

            # 8. Soltar, desconectar y apagar.
            pag.click("[data-control]")
            pag.wait_for_function("document.querySelector('[data-modo]').textContent === 'mirando'")
            chequeo("soltar devuelve el control", f.sesiones[ult["session_id"]]["mode"] == "human")
            pag.click("[data-cortar]")
            pag.wait_for_selector("form[data-conectar]")
            chequeo("desconectar vuelve a la lista de equipos", not f.sesiones)
            pag.click("[data-apagar]")
            pag.wait_for_selector("[data-prender]")
            chequeo("apagar cierra la de prueba y reabre tu RustDesk de siempre",
                    m.lanzados[-1] == "oficial.exe" and not [p for p in m.prueba if p.vivo], m.lanzados)

            # 9. La página suelta, para el celular.
            cel = nav.new_page(viewport={"width": 390, "height": 760})
            cel.on("pageerror", lambda e: errores.append(str(e)))
            cel.goto(base + "escritorio")
            cel.wait_for_selector("[data-prender]")
            chequeo("la página suelta /escritorio muestra la misma pieza", "Escritorio remoto" in cel.inner_text("body"))
            cel.screenshot(path=str(SALIDA / "5_celular.png"))
            chequeo("sin errores de JavaScript", not errores, errores)
            nav.close()
    finally:
        srv.should_exit = True
        m.desarmar()
    print(f"ver_escritorio: {len(OK)} bien, {len(MAL)} mal · capturas en {SALIDA}")
    return not MAL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
