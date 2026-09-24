"""Dibujar ENCIMA de los objetos, no solo en el vacio (pedido de Martin, 2026-08-17).

Con una herramienta armada (flecha, linea, rectangulo, circulo, lapiz) tiene que
poder arrancarse el trazo en cualquier punto del lienzo: sobre el fondo, sobre una
figura y tambien sobre una nota, un pin o un texto. Antes solo salia sobre el fondo
o adentro del SVG, asi que empezar una flecha encima de una nota no hacia
absolutamente nada.

Lo que NO tiene que dibujar: los controles (panel de propiedades, zoom, manijas).

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_dibujar_encima
"""

import sys

import requests
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido}" +
          ("" if ok else f"  (esperaba {esperado})"))
    if not ok:
        fallas.append(que)


def main():
    base_items = [
        requests.post(BASE + "/pizarra/agregar",
                      json={"tipo": "nota", "texto": "encima", "x": 28, "y": 45},
                      timeout=5).json(),
        requests.post(BASE + "/pizarra/agregar",
                      json={"tipo": "pin", "texto": "pin", "x": 28, "y": 68},
                      timeout=5).json(),
        requests.post(BASE + "/pizarra/agregar",
                      json={"tipo": "rectangulo", "x1": 58, "y1": 42, "x2": 72, "y2": 55},
                      timeout=5).json(),
    ]
    nota, pin, rect = base_items
    fijos = [i["id"] for i in base_items]
    errores, creados = [], []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1400, "height": 800})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            def dibujar_desde(herr, sel, dx=200, dy=110):
                """Arma la herramienta y arrastra desde el centro de `sel`.
                Devuelve el tipo de lo que se creo, o None si no se creo nada."""
                # Se arma por codigo y no clickeando el boton: el boton ALTERNA,
                # y si la herramienta ya estaba puesta la apagaba (me comio una
                # hora de diagnostico al escribir esta prueba).
                pg.evaluate("""t => {
                    herramienta = t;
                    document.querySelectorAll('.herr-btn').forEach(b =>
                        b.classList.toggle('armado', b.dataset.tool === t));
                    tablero.classList.add('armando');
                    if(seleccion.size){ seleccion.clear(); pintarSeleccion(); }
                }""", herr)
                antes = pg.evaluate("estado.items.map(i => i.id)")
                caja = pg.locator(sel).first.bounding_box()
                x, y = caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2
                pg.mouse.move(x, y)
                pg.mouse.down()
                pg.mouse.move(x + dx, y + dy, steps=10)
                pg.mouse.up()
                pg.wait_for_timeout(1100)
                nuevo = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
                for it in nuevo:
                    creados.append(it["id"])
                return nuevo[0]["tipo"] if nuevo else None

            revisar("flecha empezando encima de una NOTA",
                    dibujar_desde("flecha", '.item[data-id="%d"]' % nota["id"]), "flecha")
            revisar("flecha empezando encima de un PIN",
                    dibujar_desde("flecha", '.item[data-id="%d"]' % pin["id"]), "flecha")
            revisar("flecha empezando encima de un RECTANGULO",
                    dibujar_desde("flecha", '.forma-wrap[data-id="%d"] .forma-tapa' % rect["id"]),
                    "flecha")
            revisar("flecha en el fondo vacio (lo de siempre)",
                    dibujar_desde("flecha", "#tablero"), "flecha")
            revisar("linea empezando encima de una NOTA",
                    dibujar_desde("linea", '.item[data-id="%d"]' % nota["id"]), "linea")
            revisar("rectangulo empezando encima de una NOTA",
                    dibujar_desde("rectangulo", '.item[data-id="%d"]' % nota["id"]), "rectangulo")
            revisar("lapiz empezando encima de una NOTA",
                    dibujar_desde("lapiz", '.item[data-id="%d"]' % nota["id"]), "lapiz")

            # Y los controles siguen siendo controles: con la flecha armada, tocar
            # el panel de propiedades o el zoom no puede dibujar nada.
            pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }", nota["id"])
            pg.wait_for_timeout(400)
            revisar("tocar el ZOOM no dibuja", dibujar_desde("flecha", "#zoomUI", 60, 40), None)
            revisar("tocar las PROPIEDADES no dibuja",
                    dibujar_desde("flecha", "#propsColores", 60, 40), None)

            # Con el dedo, en pantalla de telefono: el mismo gesto sobre una nota.
            movil = nav.new_page(viewport={"width": 390, "height": 844},
                                 device_scale_factor=2, is_mobile=True, has_touch=True)
            movil.on("pageerror", lambda e: errores.append("movil: " + str(e)))
            movil.goto(BASE + "/pizarra")
            movil.wait_for_timeout(2500)
            movil.evaluate("""() => {
                herramienta='flecha';
                document.querySelectorAll('.herr-btn').forEach(b =>
                    b.classList.toggle('armado', b.dataset.tool === 'flecha'));
            }""")
            antes = movil.evaluate("estado.items.map(i => i.id)")
            caja = movil.locator('.item[data-id="%d"]' % nota["id"]).first.bounding_box()
            x, y = caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2
            movil.mouse.move(x, y)
            movil.mouse.down()
            movil.mouse.move(x + 90, y + 120, steps=10)
            movil.mouse.up()
            movil.wait_for_timeout(1200)
            nuevo = movil.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
            for it in nuevo:
                creados.append(it["id"])
            revisar("en el telefono, flecha desde encima de una NOTA",
                    nuevo[0]["tipo"] if nuevo else None, "flecha")
            movil.screenshot(path="pruebas/flecha_encima_movil.png")

            nav.close()
    finally:
        for iid in creados + fijos:
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)

    revisar("sin errores de JavaScript", errores, [])
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
