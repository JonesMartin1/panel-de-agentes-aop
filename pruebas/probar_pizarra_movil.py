"""La pizarra en el telefono, probada con gestos de dedo de verdad.

Abre /movil en un iPhone emulado (mismo tamano y con pantalla tactil), entra a la
pestaña Pizarra — que es la pizarra ENTERA metida en la pagina, no un resumen — y
comprueba los tres gestos que importan:

  1. un dedo sobre el fondo corre el lienzo (y NO dibuja un recuadro de seleccion),
  2. dos dedos hacen zoom,
  3. un dedo sobre una nota la mueve, y la posicion queda guardada en el servidor.

Los gestos se mandan por CDP (Input.dispatchTouchEvent), que es lo mas parecido a
un dedo real que se puede hacer sin un telefono: Playwright solo, con tap(), no
manda multi-touch.

    python -m pruebas.probar_pizarra_movil
"""
import json
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
IPHONE = {"width": 390, "height": 844}      # iPhone 15/16, el que usa Martin


def estado():
    return json.loads(urllib.request.urlopen(BASE + "/pizarra/estado", timeout=5).read())


def dedos(cdp, tipo, puntos):
    """⚠ En touchEnd hay que mandar los dedos QUE SE LEVANTAN, no una lista vacia:
    con la lista vacia Chrome no dispara el 'pointerup' y el arrastre queda a medio
    camino — se ve moverse en pantalla pero no se guarda. Costo un rato de creer
    que el arrastre con el dedo estaba roto cuando el roto era el simulador."""
    cdp.send("Input.dispatchTouchEvent", {
        "type": tipo,
        "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(puntos)]})


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport=IPHONE, has_touch=True, is_mobile=True,
                              device_scale_factor=3)
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        # ⚠ Esperar a que la app termine de cargar ANTES de tocar la pestaña: al
        # arrancar restaura del servidor cual estaba activa, y si uno toca antes,
        # esa restauracion le pisa la eleccion.
        pag.wait_for_selector("#tabs .tab", timeout=5000)
        pag.wait_for_timeout(1200)
        pag.get_by_text("Pizarra", exact=True).click()
        marco = pag.frame_locator("iframe[title='Pizarra']")
        marco.locator("#tablero").wait_for(timeout=8000)
        lienzo = pag.frame(url=lambda u: u.endswith("/pizarra"))
        cdp = ctx.new_cdp_session(pag)

        def camara():
            return lienzo.evaluate("({x:camara.x, y:camara.y, zoom:camara.zoom})")

        # --- 1) un dedo corre el lienzo ---------------------------------------
        antes = camara()
        dedos(cdp, "touchStart", [(300, 300)])
        for x in (280, 250, 220, 200):
            dedos(cdp, "touchMove", [(x, 300 - (300 - x) // 2)])
        dedos(cdp, "touchEnd", [(200, 250)])
        despues = camara()
        paneo = abs(despues["x"] - antes["x"]) > 1
        marquee = lienzo.evaluate("document.querySelectorAll('.marquee').length")
        print(f"1) un dedo corre el lienzo: {'OK' if paneo else 'FALLA'} "
              f"(camara.x {antes['x']:.1f} -> {despues['x']:.1f}) | "
              f"recuadros de seleccion dibujados: {marquee} (tiene que ser 0)")

        # --- 2) dos dedos hacen zoom ------------------------------------------
        z0 = camara()["zoom"]
        dedos(cdp, "touchStart", [(180, 400), (220, 400)])
        for sep in (40, 80, 140, 200):
            dedos(cdp, "touchMove", [(200 - sep // 2, 400), (200 + sep // 2, 400)])
        dedos(cdp, "touchEnd", [(100, 400), (300, 400)])
        z1 = camara()["zoom"]
        print(f"2) dos dedos hacen zoom: {'OK' if z1 > z0 * 1.5 else 'FALLA'} "
              f"({z0*100:.0f}% -> {z1*100:.0f}%)")

        # --- 3) un dedo mueve una nota ----------------------------------------
        lienzo.evaluate("encuadrarTodo()")
        pag.wait_for_timeout(300)
        nota = next(i for i in estado()["items"] if i["tipo"] == "nota")
        caja = marco.locator(f".item[data-id='{nota['id']}']").bounding_box()
        x0, y0 = caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2
        dedos(cdp, "touchStart", [(x0, y0)])
        for dx in (10, 25, 40, 55):
            dedos(cdp, "touchMove", [(x0 + dx, y0 + dx // 2)])
        dedos(cdp, "touchEnd", [(x0 + 55, y0 + 27)])
        pag.wait_for_timeout(700)
        ahora = next(i for i in estado()["items"] if i["id"] == nota["id"])
        movida = abs(ahora["x"] - nota["x"]) > 0.2 or abs(ahora["y"] - nota["y"]) > 0.2
        print(f"3) un dedo mueve una nota: {'OK' if movida else 'FALLA'} "
              f"(x {nota['x']:.1f} -> {ahora['x']:.1f})")
        # dejarla donde estaba: esta es la pizarra de verdad, no una de prueba
        urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/pizarra/item/{nota['id']}",
            data=json.dumps({"x": nota["x"], "y": nota["y"]}).encode(),
            headers={"Content-Type": "application/json"}, method="PUT"), timeout=5)

        lienzo.evaluate("encuadrarTodo()")
        pag.wait_for_timeout(400)
        pag.screenshot(path=str(SALIDA / "movil_pizarra_lienzo.png"))
        print(f"errores de javascript: {errores or 'ninguno'}")
        nav.close()


if __name__ == "__main__":
    main()
