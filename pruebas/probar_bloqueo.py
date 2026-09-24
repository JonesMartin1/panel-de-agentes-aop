"""Prueba del bloqueo de objetos en la pizarra (pedido de Martin, 2026-08-14).

Un objeto bloqueado: NO lo agarra el recuadro de seleccion, NO se mueve al
arrastrarlo ni con las flechas, y NO se borra. SI se selecciona con un clic
(para cambiarle propiedades) y se desbloquea desde el menu de clic derecho.

    python -m pruebas.probar_bloqueo
"""

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"


def main():
    nota = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "nota", "texto": "bloqueada", "x": 24, "y": 80},
                         timeout=5).json()
    vecina = requests.post(BASE + "/pizarra/agregar",
                           json={"tipo": "nota", "texto": "libre", "x": 40, "y": 80},
                           timeout=5).json()
    errores = []
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pg = navegador.new_page(viewport={"width": 1400, "height": 800})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(3000)

            sel = '.item[data-id="%d"]' % nota["id"]
            centro = pg.evaluate(
                "s => { const r = document.querySelector(s).getBoundingClientRect();"
                "        return [r.x + r.width / 2, r.y + r.height / 2]; }", sel)

            # Bloquear por el menu de clic derecho.
            pg.mouse.click(centro[0], centro[1])
            pg.wait_for_timeout(300)
            pg.mouse.click(centro[0], centro[1], button="right")
            pg.wait_for_timeout(400)
            opciones = pg.eval_on_selector_all(".menuCtx div", "els => els.map(e => e.textContent)")
            pg.click('.menuCtx div:text("Bloquear")')
            pg.wait_for_timeout(1500)
            marcado = pg.evaluate("id => !!estado.items.find(i => i.id === id).bloqueado", nota["id"])

            # Intentar moverla: no debe moverse.
            x_antes = pg.evaluate("id => estado.items.find(i => i.id === id).x", nota["id"])
            pg.mouse.move(centro[0], centro[1])
            pg.mouse.down()
            pg.mouse.move(centro[0] + 150, centro[1] - 50, steps=8)
            pg.mouse.up()
            pg.wait_for_timeout(1200)
            x_despues = pg.evaluate("id => estado.items.find(i => i.id === id).x", nota["id"])

            # Sigue seleccionable con un clic (para cambiarle propiedades).
            seleccionada = pg.evaluate("id => seleccion.has(id)", nota["id"])
            panel = pg.evaluate("document.getElementById('panelProps').style.display")

            # Recuadro sobre las dos: solo debe agarrar la libre.
            pg.evaluate("limpiarSeleccion()")
            pg.wait_for_timeout(200)
            pg.mouse.move(centro[0] - 120, centro[1] - 90)
            pg.mouse.down()
            pg.mouse.move(centro[0] + 420, centro[1] + 90, steps=8)
            pg.mouse.up()
            pg.wait_for_timeout(500)
            tras_marquee = sorted(pg.evaluate("[...seleccion]"))

            navegador.close()
    finally:
        for iid in (nota["id"], vecina["id"]):
            requests.post(BASE + "/pizarra/item/%d" % iid, timeout=5) if False else None
            requests.put(BASE + "/pizarra/item/%d" % iid, json={"bloqueado": False}, timeout=5)
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)

    print("errores JS:", errores if errores else "ninguno")
    print("menu:", opciones)
    print("quedo marcada como bloqueada:", marcado)
    print("x antes %.1f -> despues %.1f (no debe cambiar)" % (x_antes, x_despues))
    print("sigue seleccionable con clic:", seleccionada, "| panel de propiedades:", panel)
    print("recuadro -> selecciono:", tras_marquee,
          "| la bloqueada (id %d) NO debe estar; la libre (id %d) si" % (nota["id"], vecina["id"]))

    ok = (marcado and abs(x_antes - x_despues) < 0.01 and seleccionada
          and nota["id"] not in tras_marquee and vecina["id"] in tras_marquee)
    print("VEREDICTO:", "OK" if ok else "MAL")


if __name__ == "__main__":
    main()
