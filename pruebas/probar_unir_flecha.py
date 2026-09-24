"""La punta de la flecha se UNE al objeto, sin espacio y donde vos la soltaste
(reclamo de Martin, 2026-08-17: "no me deja seleccionar la punta del cuadradito
para unirlas, siempre hay un espacio").

Eran dos cosas juntas:
  1. la punta se iba al MEDIO del lado, ignorando donde la habias soltado
     (puntoDeApoyo apoya la flecha en el punto del borde que mira al otro
     extremo, no donde la soltaste);
  2. y encima quedaba ATAR_GAP=0,8 afuera del borde: el "espacio".

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_unir_flecha
"""

import sys

import requests
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, obtenido, esperado, tol=0.12):
    ok = (obtenido is not None
          and all(abs(a - b) <= tol for a, b in zip(obtenido, esperado)))
    print(f"{'ok  ' if ok else 'MAL '} {que}: {[round(v, 2) for v in obtenido] if obtenido else None}"
          + ("" if ok else f"  (esperaba {esperado})"))
    if not ok:
        fallas.append(que)


def main():
    cuad = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "rectangulo", "x1": 55, "y1": 70, "x2": 65, "y2": 78},
                         timeout=5).json()
    circ = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "circulo", "x1": 78, "y1": 70, "x2": 88, "y2": 78},
                         timeout=5).json()
    flecha = requests.post(BASE + "/pizarra/agregar",
                           json={"tipo": "flecha", "x1": 30, "y1": 74, "x2": 45, "y2": 74},
                           timeout=5).json()
    fijos = [cuad["id"], circ["id"], flecha["id"]]
    errores = []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1400, "height": 900})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            def soltar_punta_en(x, y):
                """Agarra la manija de la punta de la flecha y la suelta en (x,y)
                de la escena. Devuelve donde quedo la punta y su ancla."""
                pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }",
                            flecha["id"])
                pg.wait_for_timeout(350)
                m = pg.locator('.forma-manija[data-dueno="%d"]' % flecha["id"]).nth(1).bounding_box()
                destino = pg.evaluate("""xy => { const r = tablero.getBoundingClientRect();
                    return [r.left + PX(xy[0]), r.top + PY(xy[1])]; }""", [x, y])
                pg.mouse.move(m["x"] + m["width"] / 2, m["y"] + m["height"] / 2)
                pg.mouse.down()
                pg.mouse.move(destino[0], destino[1], steps=14)
                pg.mouse.up()
                pg.wait_for_timeout(1600)
                return pg.evaluate("""id => { const f = estado.items.find(i => i.id === id);
                    return {punta:[f.x2, f.y2], atada:f.atadaA}; }""", flecha["id"])

            # --- Soltarla EN la esquina de arriba-izquierda: ahi se queda ------
            r = soltar_punta_en(55, 70)
            revisar("soltada en la esquina, queda EN la esquina", r["punta"], [55, 70])
            revisar("sin espacio hasta el borde", [r["punta"][0] - 55], [0])
            pegada = r["atada"]["fin"] == cuad["id"] and r["atada"].get("anclaFin") is not None
            print(f"{'ok  ' if pegada else 'MAL '} queda atada al cuadrado y clavada: {r['atada']}")
            if not pegada:
                fallas.append("queda atada y clavada")

            # --- Soltarla en el MEDIO del cuadrado: sale al borde mas cercano --
            r = soltar_punta_en(57, 74)   # adentro, cerca del lado izquierdo
            revisar("soltada adentro, sale al borde mas cercano", r["punta"], [55, 74])

            # --- Soltarla en el medio del lado derecho -------------------------
            r = soltar_punta_en(65, 74)
            revisar("soltada en el lado derecho, se queda ahi", r["punta"], [65, 74])

            # --- Mover el cuadrado: la punta lo acompana ----------------------
            r = soltar_punta_en(55, 70)   # de vuelta a la esquina
            requests.put(BASE + "/pizarra/item/%d" % cuad["id"],
                         json={"x1": 55, "y1": 60, "x2": 65, "y2": 68}, timeout=5)
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(800)
            pg.evaluate("id => reatarFlechas(id)", cuad["id"])
            pg.wait_for_timeout(1200)
            r2 = pg.evaluate("""id => { const f = estado.items.find(i => i.id === id);
                return [f.x2, f.y2]; }""", flecha["id"])
            revisar("al mover el cuadrado la punta sigue en su esquina", r2, [55, 60])

            # --- Y en un circulo, apoya sobre la elipse, sin espacio ----------
            r = soltar_punta_en(78, 74)   # borde izquierdo del circulo
            en_elipse = pg.evaluate("""ids => {
                const f = estado.items.find(i => i.id === ids[0]);
                const c = estado.items.find(i => i.id === ids[1]);
                const cx = (c.x1+c.x2)/2, cy = (c.y1+c.y2)/2;
                const rx = Math.abs(c.x2-c.x1)/2, ry = Math.abs(c.y2-c.y1)/2;
                const dx = (f.x2-cx)/rx, dy = (f.y2-cy)/ry;
                return Math.abs(Math.sqrt(dx*dx + dy*dy) - 1);   // 0 = justo sobre la elipse
            }""", [flecha["id"], circ["id"]])
            revisar("en el circulo apoya JUSTO sobre la elipse", [en_elipse], [0], 0.05)

            pg.screenshot(path="pruebas/unir_flecha.png")
            nav.close()
    finally:
        for iid in fijos:
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)

    ok_js = not errores
    print(f"{'ok  ' if ok_js else 'MAL '} sin errores de JavaScript: {errores or '[]'}")
    if not ok_js:
        fallas.append("errores de JavaScript")
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
