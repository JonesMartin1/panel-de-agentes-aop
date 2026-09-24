"""Elegir VARIOS objetos con el dedo, en la pizarra del celular.

Pedido de Martín (2026-08-17). Con el mouse alcanza con arrastrar un recuadro sobre el
fondo, pero en el teléfono ese mismo gesto corre el lienzo (un dedo = panear, decidido
el 2026-08-16), así que no había ninguna forma de seleccionar más de un objeto.

Ahora hay un ⬚ en la barra: mientras está prendido, arrastrar con el dedo dibuja el
recuadro en vez de correr el lienzo, y **se apaga solo al soltar** — si quedara puesto,
la pizarra dejaría de poder recorrerse con el dedo.

Lo que fija esta prueba:
  * el ⬚ está en el teléfono y NO en la compu (ahí ya se arrastra el recuadro);
  * sin el modo, un dedo sobre el fondo CORRE el lienzo y no dibuja recuadro;
  * con el modo, el mismo gesto dibuja el recuadro y NO mueve el lienzo;
  * al soltar, el modo se apaga solo.

⚠ Solo hace gestos sobre el fondo vacío: no mueve, no crea y no borra nada.

Correr con:  python -m pruebas.ver_multiseleccion_movil   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def dedos(cdp, tipo, puntos):
    """⚠ En touchEnd van los dedos QUE SE LEVANTAN, no una lista vacía (lección de
    `probar_pizarra_movil.py`)."""
    cdp.send("Input.dispatchTouchEvent", {
        "type": tipo,
        "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(puntos)]})


def arrastrar(pag, cdp, x0, y0, pasos=6, dx=38, dy=26):
    """Un dedo arrastrando por el fondo. Devuelve si vio el recuadro a mitad de camino."""
    vioMarco = False
    dedos(cdp, "touchStart", [(x0, y0)])
    for k in range(1, pasos + 1):
        dedos(cdp, "touchMove", [(x0 + k * dx, y0 + k * dy)])
        pag.wait_for_timeout(40)
        if pag.evaluate("() => !!document.querySelector('.marquee')"):
            vioMarco = True
    dedos(cdp, "touchEnd", [(x0 + pasos * dx, y0 + pasos * dy)])
    pag.wait_for_timeout(500)
    return vioMarco


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # --- En la compu no aparece: ahí el recuadro ya se arrastra con el mouse ---
        pc = nav.new_page(viewport={"width": 1400, "height": 800})
        pc.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        pc.wait_for_timeout(2000)
        revisar("en la compu el ⬚ no está a la vista",
                pc.evaluate("() => !!document.getElementById('btnMulti').offsetParent"), False)
        pc.close()

        pag = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        pag.wait_for_timeout(2200)
        cdp = pag.context.new_cdp_session(pag)
        revisar("en el teléfono sí está",
                pag.evaluate("() => !!document.getElementById('btnMulti').offsetParent"), True)

        # Un punto del fondo, lejos de la barra y de la hoja de propiedades.
        x0, y0 = 60, 260

        # --- Sin el modo: el dedo corre el lienzo ---
        antes = pag.evaluate("() => camara.x")
        vio = arrastrar(pag, cdp, x0, y0)
        revisar("sin el modo, el dedo corre el lienzo",
                abs(pag.evaluate("() => camara.x") - antes) > 1, True)
        revisar("y no dibuja ningún recuadro", vio, False)

        # --- Con el modo: dibuja el recuadro y NO mueve el lienzo ---
        pag.click("#btnMulti")
        pag.wait_for_timeout(300)
        revisar("el botón queda marcado mientras está puesto",
                pag.evaluate("() => document.getElementById('btnMulti').classList.contains('armado')"),
                True)
        pag.screenshot(path=str(SALIDA / "pizarra_multi_movil.png"))
        antes = pag.evaluate("() => camara.x")
        vio = arrastrar(pag, cdp, x0, y0)
        revisar("con el modo, el dedo dibuja el recuadro", vio, True)
        revisar("y el lienzo NO se movió",
                abs(pag.evaluate("() => camara.x") - antes) < 0.01, True)
        revisar("al soltar, el modo se apaga solo",
                pag.evaluate("() => multiDedo"), False)
        revisar("y el botón queda sin marcar",
                pag.evaluate("() => document.getElementById('btnMulti').classList.contains('armado')"),
                False)

        # Y después de eso, el dedo vuelve a correr el lienzo.
        antes = pag.evaluate("() => camara.x")
        arrastrar(pag, cdp, x0, y0)
        revisar("y el dedo vuelve a correr el lienzo",
                abs(pag.evaluate("() => camara.x") - antes) > 1, True)

        revisar("sin errores de javascript", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'pizarra_multi_movil.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
