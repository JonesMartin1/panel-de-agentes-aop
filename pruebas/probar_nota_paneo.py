"""Prueba puntual: al arrastrar una nota, los puntitos de conexion la siguen y
la nota NO salta a su posicion vieja cuando se panea el lienzo.

Nace de dos bugs reales (2026-08-14): el arrastre movia el DOM pero no el estado
en memoria, asi que cualquier repintado por camara redibujaba la posicion vieja.

    python -m pruebas.probar_nota_paneo
"""

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"


def main():
    nota = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "nota", "texto": "prueba mover", "x": 28, "y": 80},
                         timeout=5).json()
    sel = '.item[data-id="%d"]' % nota["id"]
    errores = []
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pg = navegador.new_page(viewport={"width": 1400, "height": 800})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(3000)

            centro = pg.evaluate(
                "sel => { const r = document.querySelector(sel).getBoundingClientRect();"
                "        return [r.x + r.width / 2, r.y + r.height / 2]; }", sel)

            pg.mouse.move(centro[0], centro[1])
            pg.mouse.down()
            pg.mouse.move(centro[0] + 200, centro[1] - 60, steps=8)
            pg.mouse.up()
            pg.wait_for_timeout(600)

            x_arrastrada = pg.evaluate("sel => document.querySelector(sel).getBoundingClientRect().x", sel)
            dist_conector = pg.evaluate(
                "sel => { const r = document.querySelector(sel).getBoundingClientRect();"
                "        const ds = [...document.querySelectorAll('.conector')]"
                "          .map(e => { const c = e.getBoundingClientRect();"
                "                      return Math.hypot(c.x - r.x, c.y - r.y); });"
                "        return Math.round(Math.min(...ds)); }", sel)

            # Panear con el boton del medio: la nota no debe volver a su lugar viejo.
            pg.mouse.move(700, 300)
            pg.mouse.down(button="middle")
            pg.mouse.move(760, 340, steps=5)
            x_paneo = pg.evaluate("sel => document.querySelector(sel).getBoundingClientRect().x", sel)
            pg.mouse.up(button="middle")
            pg.wait_for_timeout(2500)
            x_final = pg.evaluate("sel => document.querySelector(sel).getBoundingClientRect().x", sel)
            navegador.close()
    finally:
        requests.delete(BASE + "/pizarra/item/%d" % nota["id"], timeout=5)

    print("errores JS:", errores if errores else "ninguno")
    print("x tras arrastrar: %.0f | durante el paneo (~+60): %.0f | tras refrescar: %.0f"
          % (x_arrastrada, x_paneo, x_final))
    print("conector mas cercano a la esquina de la nota:", dist_conector, "px (chico = la sigue)")

    salto = abs(x_paneo - (x_arrastrada + 60)) > 25
    print("VEREDICTO:", "MAL, la nota salto al panear" if salto else "OK, la nota no salta")


if __name__ == "__main__":
    main()
