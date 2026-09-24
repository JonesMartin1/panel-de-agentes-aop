"""Se le puede enganchar una flecha a CUALQUIER cosa de la pizarra
(pedido de Martin, 2026-08-17: "de todos los objetos, de las imagenes tambien,
de lo que sea que yo ponga en la pantalla").

Los nueve tipos: nota, pin, texto, rectangulo, circulo, imagen, linea, flecha y
lapiz. Los seis que tienen adentro se conectan desde CUALQUIER punto del borde
(banda); los tres que son puro trazo, desde sus 3 puntitos (principio, mitad y
final) — si tuvieran banda taparia el objeto entero y arrastrar una linea
crearia una flecha en vez de moverla, que es justo lo que se comprueba al final.

En los nueve, el punto queda CLAVADO: se mueve el objeto y la flecha lo sigue.

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_conectar_todo
"""

import base64
import io
import sys
import time

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

from app.rutas import RESULTADOS

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def esperar_nuevos(pg, antes, segundos=6):
    """Espera a que aparezca lo recien creado en vez de dormir un rato fijo: el
    objeto entra en `estado.items` recien cuando vuelve el refresco, y con un
    sleep fijo la prueba fallaba una de cada tres veces sin que nada estuviera mal."""
    limite = time.time() + segundos
    while time.time() < limite:
        nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
        if nuevas:
            return nuevas
        pg.wait_for_timeout(200)
    return []


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}" + (f": {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def imagen_de_prueba():
    im = Image.new("RGB", (120, 80), (90, 150, 220))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    archivo = requests.post(BASE + "/pizarra/imagen",
                            json={"datos": imagen_de_prueba()}, timeout=10).json()["archivo"]
    # Todos en una franja de abajo, lejos de lo que Martin tenga puesto arriba.
    DEFS = [
        ("nota",       {"tipo": "nota", "texto": "n", "x": 8, "y": 86}),
        ("pin",        {"tipo": "pin", "texto": "p", "x": 20, "y": 86}),
        ("texto",      {"tipo": "texto", "texto": "t", "x": 30, "y": 86}),
        ("rectangulo", {"tipo": "rectangulo", "x1": 36, "y1": 82, "x2": 44, "y2": 90}),
        ("circulo",    {"tipo": "circulo", "x1": 47, "y1": 82, "x2": 55, "y2": 90}),
        ("imagen",     {"tipo": "imagen", "archivo": archivo, "x1": 58, "y1": 82, "x2": 66, "y2": 90}),
        ("linea",      {"tipo": "linea", "x1": 69, "y1": 82, "x2": 77, "y2": 90}),
        ("flecha",     {"tipo": "flecha", "x1": 80, "y1": 82, "x2": 88, "y2": 90}),
        ("lapiz",      {"tipo": "lapiz", "puntos": [{"x": 90, "y": 82}, {"x": 94, "y": 86},
                                                    {"x": 97, "y": 90}]}),
    ]
    objetos = []
    for nombre, cuerpo in DEFS:
        objetos.append((nombre, requests.post(BASE + "/pizarra/agregar",
                                              json=cuerpo, timeout=5).json()["id"]))
    fijos = [i for _, i in objetos]
    errores, creados = [], []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            pg = nav.new_page(viewport={"width": 1400, "height": 900})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(3000)

            for nombre, iid in objetos:
                pg.evaluate("id => conectoresDe[id] && conectoresDe[id](true)", iid)
                pg.wait_for_timeout(200)

                # De donde se tira: del borde si hay banda, del primer puntito si
                # es puro trazo. En la banda se elige un punto que NO sea ninguno
                # de los 4 puntitos, para probar que el borde entero sirve.
                tiene_banda = pg.locator('.borde-conector[data-dueno="%d"]' % iid).count() == 1
                if tiene_banda:
                    desde = pg.evaluate("""id => {
                        const it = estado.items.find(i => i.id === id);
                        const c = cajaDe(it), r = tablero.getBoundingClientRect();
                        return [r.left + PX(Math.min(c.x1,c.x2) + Math.abs(c.x2-c.x1)*0.3),
                                r.top + PY(Math.min(c.y1,c.y2))];
                    }""", iid)
                else:
                    b = pg.locator('.conector[data-dueno="%d"]' % iid).first.bounding_box()
                    desde = [b["x"] + b["width"] / 2, b["y"] + b["height"] / 2]

                hasta = pg.evaluate("""() => { const r = tablero.getBoundingClientRect();
                                              return [r.left + PX(50), r.top + PY(65)]; }""")
                antes = pg.evaluate("estado.items.map(i => i.id)")
                pg.mouse.move(desde[0], desde[1])
                pg.wait_for_timeout(120)
                pg.mouse.down()
                pg.mouse.move(hasta[0], hasta[1], steps=12)
                pg.mouse.up()
                nuevas = esperar_nuevos(pg, antes)
                creados += [i["id"] for i in nuevas]
                fl = nuevas[0] if nuevas else None
                atada = fl and fl["tipo"] == "flecha" and fl["atadaA"]["inicio"] == iid
                clavada = bool(fl and fl["atadaA"].get("anclaInicio"))
                revisar(f"{nombre}: nace una flecha atada a el", bool(atada),
                        "" if atada else f"salio {fl}")
                revisar(f"{nombre}: el punto queda clavado", clavada)

                if not (atada and clavada):
                    continue

                # Mover el objeto: la flecha tiene que acompanar ese punto.
                p0 = pg.evaluate("id => { const f = estado.items.find(i => i.id === id);"
                                 "        return [f.x1, f.y1]; }", fl["id"])
                pg.evaluate("""ids => {
                    const it = estado.items.find(i => i.id === ids[0]);
                    const d = 6;
                    if(it.puntos) it.puntos = it.puntos.map(q => ({x:q.x, y:q.y-d}));
                    else if(it.y1 != null){ it.y1 -= d; it.y2 -= d; }
                    else it.y -= d;
                    const cuerpo = it.puntos ? {puntos: it.puntos}
                                 : (it.y1 != null ? {y1: it.y1, y2: it.y2} : {y: it.y});
                    return fetch('/pizarra/item/' + it.id, {method:'PUT',
                        headers:{'Content-Type':'application/json'}, body: JSON.stringify(cuerpo)});
                }""", [iid])
                pg.wait_for_timeout(400)
                pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
                pg.wait_for_timeout(700)
                pg.evaluate("id => reatarFlechas(id)", iid)
                pg.wait_for_timeout(1000)
                p1 = pg.evaluate("id => { const f = estado.items.find(i => i.id === id);"
                                 "        return [f.x1, f.y1]; }", fl["id"])
                subio = abs((p0[1] - p1[1]) - 6) < 0.6 and abs(p0[0] - p1[0]) < 0.6
                revisar(f"{nombre}: la flecha acompana al mover el objeto", subio,
                        "" if subio else f"{p0} -> {p1}")

            # --- Y una linea se sigue pudiendo MOVER, no crea una flecha -------
            # Es la contracara de no ponerle banda a los objetos de puro trazo.
            linea_id = dict(objetos)["linea"]
            pg.evaluate("id => conectoresDe[id](true)", linea_id)
            medio = pg.evaluate("""id => {
                const it = estado.items.find(i => i.id === id);
                const r = tablero.getBoundingClientRect();
                return [r.left + PX(it.x1 + (it.x2-it.x1)*0.25),
                        r.top + PY(it.y1 + (it.y2-it.y1)*0.25)];
            }""", linea_id)
            x_antes = pg.evaluate("id => estado.items.find(i => i.id === id).x1", linea_id)
            antes = pg.evaluate("estado.items.map(i => i.id)")
            pg.mouse.move(medio[0], medio[1])
            pg.mouse.down()
            pg.mouse.move(medio[0] - 100, medio[1], steps=10)
            pg.mouse.up()
            pg.wait_for_timeout(1200)
            x_despues = pg.evaluate("id => estado.items.find(i => i.id === id).x1", linea_id)
            nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
            creados += [i["id"] for i in nuevas]
            revisar("arrastrar una linea por su cuerpo la MUEVE (no crea una flecha)",
                    abs(x_despues - x_antes) > 2 and not nuevas,
                    f"x {x_antes:.1f} -> {x_despues:.1f}, creo {len(nuevas)}")

            pg.screenshot(path=str(RESULTADOS.parent / "pruebas" / "conectar_todo.png"))
            nav.close()
    finally:
        for iid in creados + fijos:
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)
        try:
            (RESULTADOS / "pizarra_imagenes" / archivo).unlink()
        except OSError:
            pass

    revisar("sin errores de JavaScript", not errores, str(errores))
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
