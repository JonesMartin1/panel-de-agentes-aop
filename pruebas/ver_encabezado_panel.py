"""Mira el encabezado del panel: los ESTADOS a la izquierda, las PESTAÑAS a la derecha.

No necesita el panel prendido ni reiniciarlo: importa `panel.py` y sirve el HTML de
`PAGINA` interceptado con `page.route`, como hace `ver_estudio.py`. Importar no prende
nada (el vigilante de servicios es un evento de arranque de FastAPI y solo corre bajo
uvicorn). Todos los `fetch` que hace la página se contestan con datos inventados.

    python -m pruebas.ver_encabezado_panel
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # los emojis del titulo

from playwright.sync_api import sync_playwright

import panel
from app.rutas import RESULTADOS, ESTATICOS

SALIDA = RESULTADOS / "capturas"
ok = fallas = 0


def chequeo(titulo, cond, detalle=""):
    global ok, fallas
    if cond:
        ok += 1
        print(f"  OK   {titulo}")
    else:
        fallas += 1
        print(f"  MAL  {titulo} {detalle}")


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1500, "height": 900})
        pag.on("pageerror", lambda e: print("  error de JS:", e))

        # La pagina de verdad, pero el servidor entero inventado.
        # ⚠ Playwright prueba las rutas de la ULTIMA a la primera: el comodin va PRIMERO,
        #   o se come a las especificas y la pagina llega vacia.
        pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
        # ⚠⚠ El menu hay que servirlo DE VERDAD. Las pestañas del encabezado dejaron de
        #   estar escritas en `PAGINA` y ahora las dibuja `menu.js` adentro del
        #   `<nav id="menuPantallas" class="pestanas">`, que llega VACIO. Con el comodin
        #   de arriba el script se contestaba con "{}" de JSON, el JS no corria nunca, y
        #   la prueba moria en `nav.querySelector('a[href="/sesiones"]')` con un
        #   "Cannot read properties of null" que parece un bug de la pantalla siendo de
        #   la prueba. Es la misma piedra anotada en la PIZARRA para `rough.js`: cada
        #   cosa con su tipo.
        pag.route("**/estaticos/menu.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript",
            body=(ESTATICOS / "menu.js").read_text(encoding="utf-8")))
        pag.route("**/escribir", lambda r: r.fulfill(json={
            "destino": {"id": "x", "nombre": "Investigar y clasificar ocupacion de disco C urgente"},
            "proyectos": []}))
        pag.route("**/panel-de-prueba", lambda r: r.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=panel.PAGINA))

        pag.goto("http://panel.local/panel-de-prueba", wait_until="domcontentloaded")
        pag.wait_for_timeout(1500)  # networkidle NUNCA llega: la pagina hace polling

        # Con el destino puesto, el chip del lapiz tiene que aparecer.
        pag.evaluate("""() => {
            const ce = document.getElementById('chipEsc');
            ce.style.display = '';
            document.getElementById('chipEscTxt').textContent =
                '\\u270f\\ufe0f Investigar y clasificar ocupacion de disco C urgente';
        }""")
        pag.wait_for_timeout(200)

        cajas = pag.evaluate("""() => {
            const caja = el => { const r = el.getBoundingClientRect();
                                 return {x: r.x, der: r.right, y: r.y, alto: r.height}; };
            const nav = document.querySelector('header .pestanas');
            return {
                esc: caja(document.getElementById('chipEsc')),
                voz: caja(document.getElementById('chipVoz')),
                nav: caja(nav),
                pestana: caja(nav.querySelector('a[href="/sesiones"]')),
                enNav: nav.querySelectorAll('a').length,
                estadosEnNav: nav.querySelectorAll('span.chip').length,
                header: caja(document.querySelector('header')),
                raya: getComputedStyle(nav).borderLeftWidth,
            };
        }""")

        # ⚠ No va un número a mano acá: las pestañas ya no están escritas en `PAGINA`,
        #   las dibuja `menu.js`, y agregar una pantalla al menú ponía esta prueba en
        #   rojo sola (pasó al sumar Avisos: esperaba 4 y eran 6). Lo que importa no es
        #   cuántas son sino que estén TODAS las del menú y ninguna suelta por afuera.
        cuantas = (ESTATICOS / "menu.js").read_text(encoding="utf-8").count("{ href:")
        chequeo("todas las pantallas del menú viven en la barra de la derecha",
                cajas["enNav"] == cuantas, f"(hay {cajas['enNav']} y el menú tiene {cuantas})")
        chequeo("ningun estado quedó adentro de las pestañas", cajas["estadosEnNav"] == 0)
        chequeo("el chip de escritura quedó a la IZQUIERDA de las pestañas",
                cajas["esc"]["der"] <= cajas["nav"]["x"],
                f"(termina en {cajas['esc']['der']:.0f}, la barra arranca en {cajas['nav']['x']:.0f})")
        chequeo("las pestañas están pegadas al borde derecho",
                cajas["nav"]["der"] >= cajas["header"]["der"] - 2)
        chequeo("hay una rayita separando las dos zonas", cajas["raya"] != "0px", cajas["raya"])
        chequeo("todo sigue en UNA sola fila",
                abs(cajas["voz"]["y"] - cajas["pestana"]["y"]) < 3)
        chequeo("el encabezado no creció de alto", cajas["header"]["alto"] < 60,
                f"({cajas['header']['alto']:.0f} px)")

        # El hover de una pestaña tiene que notarse (antes no pasaba nada).
        antes = pag.eval_on_selector('a[href="/pizarra"]', "el => getComputedStyle(el).backgroundColor")
        pag.hover('a[href="/pizarra"]')
        pag.wait_for_timeout(350)
        despues = pag.eval_on_selector('a[href="/pizarra"]', "el => getComputedStyle(el).backgroundColor")
        chequeo("al pasar el mouse, la pestaña se prende", antes != despues, f"({antes} -> {despues})")

        pag.mouse.move(700, 500)
        pag.wait_for_timeout(250)
        pag.locator("header").screenshot(path=str(SALIDA / "encabezado_panel.png"))

        # Ventana angosta: que no se rompa ni se monte.
        pag.set_viewport_size({"width": 980, "height": 900})
        pag.wait_for_timeout(300)
        angosto = pag.evaluate("""() => {
            const h = document.querySelector('header').getBoundingClientRect();
            const n = document.querySelector('header .pestanas').getBoundingClientRect();
            return {desborde: n.right - h.right, alto: h.height};
        }""")
        chequeo("con la ventana angosta las pestañas no se salen",
                angosto["desborde"] <= 2, f"(se pasan {angosto['desborde']:.0f} px)")
        pag.locator("header").screenshot(path=str(SALIDA / "encabezado_panel_angosto.png"))

        nav.close()

    print(f"\n{ok} bien, {fallas} mal")
    print(f"capturas en {SALIDA}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
