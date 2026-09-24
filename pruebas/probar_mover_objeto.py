"""Un objeto FINITO se puede mover, y hay un asa dedicada para hacerlo
(reclamo de Martin, 2026-08-17: "me falta un botón para mover el objeto, porque
cada vez que intento tocar en alguno de los bordes quiere crear una flecha").

Al hacer conectable TODO el borde quedó un agujero: la banda mide 11 px con el
mouse y 18 con el dedo, mitad para adentro y mitad para afuera. En una barra de
8 px de alto eso tapa la figura ENTERA — no queda ni un pixel de "adentro" para
agarrar, y cada toque creaba una flecha en vez de moverla.

Dos arreglos: la banda nunca pasa del 40 % del lado corto, y hay un ASA de mover
(un tirador azul abajo del objeto) que corre el objeto siempre, sin pelear con
nada.

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_mover_objeto
"""

import sys
import time

import requests
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}" + (f": {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def esperar_cambio(pg, iid, campo, valor0, segundos=6):
    """Espera a que el objeto se haya movido de verdad, en vez de dormir un rato."""
    limite = time.time() + segundos
    ultimo = valor0
    while time.time() < limite:
        ultimo = pg.evaluate("a => estado.items.find(i => i.id === a[0])[a[1]]", [iid, campo])
        if abs(ultimo - valor0) > 0.5:
            return ultimo
        pg.wait_for_timeout(200)
    return ultimo


def main():
    # Una barra finita, como la que le fallaba: 30 unidades de ancho por 1 de alto.
    barra = requests.post(BASE + "/pizarra/agregar",
                          json={"tipo": "rectangulo", "x1": 20, "y1": 60, "x2": 50, "y2": 61},
                          timeout=5).json()
    nota = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "nota", "texto": "movete", "x": 70, "y": 60},
                         timeout=5).json()
    fijos = [barra["id"], nota["id"]]
    errores, creados = [], []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1400, "height": 900})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            # --- La banda no puede taparle el cuerpo a una figura finita -------
            pg.evaluate("id => conectoresDe[id](true)", barra["id"])
            pg.wait_for_timeout(200)
            ancho_banda = pg.evaluate(
                "id => +document.querySelector('.borde-conector[data-dueno=\"'+id+'\"]')"
                "        .getAttribute('stroke-width')", barra["id"])
            alto_px = pg.evaluate("""id => { const it = estado.items.find(i => i.id === id);
                return LY(Math.abs(it.y2 - it.y1)); }""", barra["id"])
            # El minimo de 4 px es a proposito: por debajo no se podria enganchar
            # nada en una figura finita. Lo que importa es que quede nucleo libre.
            revisar("la banda no se come la barra finita",
                    ancho_banda <= max(4, alto_px * 0.4) + 0.01 and ancho_banda < alto_px,
                    f"banda {ancho_banda:.1f} px sobre una barra de {alto_px:.1f} px")

            # --- Arrastrar el CENTRO de la barra la mueve, no crea una flecha ---
            centro = pg.evaluate("""id => { const it = estado.items.find(i => i.id === id);
                const r = tablero.getBoundingClientRect();
                return [r.left + PX((it.x1+it.x2)/2), r.top + PY((it.y1+it.y2)/2)]; }""",
                                 barra["id"])
            antes_ids = pg.evaluate("estado.items.map(i => i.id)")
            x0 = pg.evaluate("id => estado.items.find(i => i.id === id).x1", barra["id"])
            pg.mouse.move(centro[0], centro[1])
            pg.mouse.down()
            pg.mouse.move(centro[0] - 150, centro[1], steps=12)
            pg.mouse.up()
            x1 = esperar_cambio(pg, barra["id"], "x1", x0)
            nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes_ids)
            creados += [i["id"] for i in nuevas]
            revisar("arrastrar el centro de la barra la MUEVE",
                    abs(x1 - x0) > 2 and not nuevas,
                    f"x {x0:.1f} -> {x1:.1f}, creo {len(nuevas)} objetos")

            # --- El asa de mover: existe, se ve al seleccionar, y mueve ---------
            for nombre, iid, campo in (("la barra", barra["id"], "x1"),
                                       ("la nota", nota["id"], "x")):
                pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }", iid)
                pg.wait_for_timeout(400)
                asa = '.asa-mover[data-dueno="%d"]' % iid
                revisar(f"{nombre}: tiene asa de mover", pg.locator(asa).count() == 1)
                visible = pg.evaluate("s => document.querySelector(s).classList.contains('visible')", asa)
                revisar(f"{nombre}: el asa se ve al seleccionarla", visible)
                if not visible:
                    continue
                caja = pg.locator(asa).bounding_box()
                v0 = pg.evaluate("a => estado.items.find(i => i.id === a[0])[a[1]]", [iid, campo])
                antes_ids = pg.evaluate("estado.items.map(i => i.id)")
                pg.mouse.move(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
                pg.mouse.down()
                pg.mouse.move(caja["x"] + caja["width"] / 2 - 120,
                              caja["y"] + caja["height"] / 2 - 60, steps=12)
                pg.mouse.up()
                v1 = esperar_cambio(pg, iid, campo, v0)
                nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes_ids)
                creados += [i["id"] for i in nuevas]
                revisar(f"{nombre}: arrastrando el asa se mueve",
                        abs(v1 - v0) > 2 and not nuevas,
                        f"{campo} {v0:.1f} -> {v1:.1f}, creo {len(nuevas)} objetos")

            # --- Sin seleccionar, el asa no estorba ----------------------------
            pg.evaluate("limpiarSeleccion()")
            pg.wait_for_timeout(300)
            revisar("sin seleccionar, ningun asa recibe el dedo",
                    pg.evaluate("[...document.querySelectorAll('.asa-mover')]"
                                ".every(a => getComputedStyle(a).pointerEvents === 'none')"))

            # --- Y con el dedo el asa es mas grande ---------------------------
            movil = nav.new_page(viewport={"width": 390, "height": 844},
                                 device_scale_factor=2, is_mobile=True, has_touch=True)
            movil.on("pageerror", lambda e: errores.append("movil: " + str(e)))
            movil.goto(BASE + "/pizarra")
            movil.wait_for_timeout(2500)
            movil.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }",
                           barra["id"])
            movil.wait_for_timeout(400)
            lado = movil.evaluate("id => document.querySelector('.asa-mover[data-dueno=\"'+id+'\"]')"
                                  "        .getBoundingClientRect().width", barra["id"])
            revisar("con el dedo el asa es grande", lado >= 28, f"{lado:.0f} px")
            movil.screenshot(path="pruebas/asa_mover_movil.png")

            nav.close()
    finally:
        for iid in creados + fijos:
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)

    revisar("sin errores de JavaScript", not errores, str(errores))
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
