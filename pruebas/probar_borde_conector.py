"""Todo el borde conecta, no solo los 4 puntitos (pedido de Martin, 2026-08-17).

Se puede tirar una flecha desde CUALQUIER punto del contorno de una figura, una
imagen, una nota, un pin o un texto. Donde la agarraste queda CLAVADA: la flecha
sigue ese punto cuando la figura se mueve, se agranda o se rota, en vez de
resbalar por el borde como hacia el enganche viejo (que sigue existiendo para las
flechas que se atan por cercania).

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_borde_conector
"""

import sys

import requests
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, obtenido, esperado, tolerancia=None):
    if tolerancia is None:
        ok = obtenido == esperado
    else:
        ok = (obtenido is not None and esperado is not None
              and all(abs(a - b) <= tolerancia for a, b in zip(obtenido, esperado)))
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido}" +
          ("" if ok else f"  (esperaba {esperado})"))
    if not ok:
        fallas.append(que)


def main():
    rect = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "rectangulo", "x1": 25, "y1": 30, "x2": 45, "y2": 48},
                         timeout=5).json()
    nota = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "nota", "texto": "destino", "x": 70, "y": 40},
                         timeout=5).json()
    fijos = [rect["id"], nota["id"]]
    errores, creados = [], []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1400, "height": 800})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            banda = '.borde-conector[data-dueno="%d"]' % rect["id"]

            def prender():
                """Simula el 'pasar el mouse por encima' que arma la banda."""
                pg.evaluate("id => conectoresDe[id](true)", rect["id"])
                pg.wait_for_timeout(150)

            revisar("cada objeto tiene su banda de borde", pg.locator(banda).count(), 1)
            revisar("apagada no recibe el mouse",
                    pg.evaluate("s => getComputedStyle(document.querySelector(s)).pointerEvents", banda),
                    "none")
            prender()
            revisar("prendida si",
                    pg.evaluate("s => getComputedStyle(document.querySelector(s)).pointerEvents", banda),
                    "stroke")
            revisar("los puntitos apagados tampoco roban el clic",
                    pg.evaluate("getComputedStyle(document.querySelector"
                                "('.conector:not(.activo)')).pointerEvents"), "none")

            # --- Tirar una flecha desde UN CUARTO del borde de arriba ----------
            # Ni el medio ni una esquina: justo donde no hay ningun puntito.
            caja = pg.evaluate("""id => {
                const it = estado.items.find(i => i.id === id);
                const r = tablero.getBoundingClientRect();
                return {x: r.left + PX(it.x1 + (it.x2-it.x1)*0.25), y: r.top + PY(it.y1),
                        finX: r.left + PX(70), finY: r.top + PY(42)};
            }""", rect["id"])
            antes = pg.evaluate("estado.items.map(i => i.id)")
            pg.mouse.move(caja["x"], caja["y"])
            pg.wait_for_timeout(200)
            pg.mouse.down()
            pg.mouse.move(caja["finX"], caja["finY"], steps=12)
            pg.mouse.up()
            pg.wait_for_timeout(1300)
            nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
            creados += [i["id"] for i in nuevas]
            revisar("nacio una flecha", nuevas[0]["tipo"] if nuevas else None, "flecha")
            if not nuevas:
                raise SystemExit("sin flecha no se puede seguir")
            flecha = nuevas[0]
            revisar("quedo atada al rectangulo y a la nota",
                    [flecha["atadaA"]["inicio"], flecha["atadaA"]["fin"]], [rect["id"], nota["id"]])
            ancla = flecha["atadaA"]["anclaInicio"]
            revisar("clavada a un cuarto del borde de arriba",
                    [ancla["fx"], ancla["fy"]], [0.25, 0], 0.03)

            # --- Mover el rectangulo: el punto clavado tiene que acompanar -----
            def punto_inicio():
                return pg.evaluate("id => { const f = estado.items.find(i => i.id === id);"
                                   "        return [f.x1, f.y1]; }", flecha["id"])

            esperado_antes = pg.evaluate("""ids => {
                const r = estado.items.find(i => i.id === ids[0]);
                return [r.x1 + (r.x2-r.x1)*0.25, r.y1];
            }""", fijos)
            revisar("la flecha arranca en ese punto", punto_inicio(), esperado_antes, 0.15)

            requests.put(BASE + "/pizarra/item/%d" % rect["id"],
                         json={"x1": 25, "y1": 10, "x2": 45, "y2": 28}, timeout=5)
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(900)
            pg.evaluate("id => reatarFlechas(id)", rect["id"])
            pg.wait_for_timeout(1300)
            revisar("tras mover la figura sigue clavada en el mismo punto",
                    punto_inicio(), [30, 10], 0.15)

            # --- Agrandar: el punto acompana en PROPORCION ---------------------
            requests.put(BASE + "/pizarra/item/%d" % rect["id"],
                         json={"x1": 25, "y1": 10, "x2": 65, "y2": 28}, timeout=5)
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(900)
            pg.evaluate("id => reatarFlechas(id)", rect["id"])
            pg.wait_for_timeout(1300)
            revisar("al agrandar acompana en proporcion (un cuarto sigue siendo un cuarto)",
                    punto_inicio(), [35, 10], 0.15)

            # --- El puntito de arriba tambien clava DONDE ESTA -----------------
            requests.put(BASE + "/pizarra/item/%d" % rect["id"],
                         json={"x1": 25, "y1": 30, "x2": 45, "y2": 48}, timeout=5)
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(900)
            prender()
            punto = pg.locator('.conector[data-dueno="%d"]' % rect["id"]).nth(0).bounding_box()
            antes = pg.evaluate("estado.items.map(i => i.id)")
            pg.mouse.move(punto["x"] + punto["width"] / 2, punto["y"] + punto["height"] / 2)
            pg.mouse.down()
            # Se la lleva a la DERECHA: antes eso hacia que la flecha naciera en
            # el borde derecho, ignorando el puntito de arriba del que tiraste.
            pg.mouse.move(caja["finX"], caja["finY"], steps=12)
            pg.mouse.up()
            pg.wait_for_timeout(1300)
            nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
            creados += [i["id"] for i in nuevas]
            a2 = nuevas[0]["atadaA"]["anclaInicio"] if nuevas else None
            revisar("el puntito de arriba nace ARRIBA aunque la lleves a la derecha",
                    [a2["fx"], a2["fy"]] if a2 else None, [0.5, 0], 0.03)

            # --- Con el dedo: la banda se prende al seleccionar ----------------
            movil = nav.new_page(viewport={"width": 390, "height": 844},
                                 device_scale_factor=2, is_mobile=True, has_touch=True)
            movil.on("pageerror", lambda e: errores.append("movil: " + str(e)))
            movil.goto(BASE + "/pizarra")
            movil.wait_for_timeout(2500)
            revisar("con el dedo, sin seleccionar, el borde esta apagado",
                    movil.locator('.borde-conector.activo').count(), 0)
            movil.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }",
                           rect["id"])
            movil.wait_for_timeout(400)
            revisar("con el dedo, al seleccionar se prende",
                    movil.locator('.borde-conector.activo').count(), 1)
            revisar("y con el dedo la banda es mas gruesa",
                    movil.evaluate("+document.querySelector('.borde-conector')"
                                   ".getAttribute('stroke-width')"), 18)
            movil.screenshot(path="pruebas/borde_conector_movil.png")

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
