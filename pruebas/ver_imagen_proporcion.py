"""Una imagen de la pizarra se tiene que ver IGUAL en el celular y en la compu.

Queja de Martín (2026-08-17): "veo las dimensiones de las imágenes diferentes en el
celular que en el escritorio". La causa es de fondo: el tablero mide la x contra el
ANCHO de la pantalla y la y contra el ALTO, así que sus unidades no son cuadradas y la
misma caja da una forma distinta en cada pantalla. Para las imágenes se arregla
dibujándolas con su proporción (`preserveAspectRatio`) en vez de estiradas a la caja.

Esta prueba mete una imagen 3:1 bien reconocible y compara **la proporción de lo que se
ve** en un teléfono (390×844) y en una pantalla grande (1400×800).

⚠ Deja el tablero como estaba: borra la imagen que agrega.

Correr con:  python -m pruebas.ver_imagen_proporcion   (con el panel prendido)
"""
import json
import sys
import urllib.request

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


def estado():
    return json.loads(urllib.request.urlopen(BASE + "/pizarra/estado", timeout=10).read())


def medir(nav, ancho, alto, item_id):
    """La proporción de la imagen COMO SE VE (ancho/alto en píxeles de pantalla)."""
    pag = nav.new_page(viewport={"width": ancho, "height": alto}, has_touch=(ancho < 500))
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.goto(BASE + "/pizarra", wait_until="domcontentloaded")
    pag.wait_for_timeout(2200)
    r = pag.evaluate("""id => {
      const g = document.querySelector('[data-id="' + id + '"]');
      const im = g && g.querySelector('image');
      if (!im) return null;
      // Lo que se VE: el rectángulo que ocupa la imagen ya dibujada.
      const c = im.getBoundingClientRect();
      return {prop: c.width / c.height, modo: im.getAttribute('preserveAspectRatio')};
    }""", item_id)
    pag.screenshot(path=str(SALIDA / f"pizarra_proporcion_{ancho}.png"))
    pag.close()
    return r, errores


def main():
    from PIL import Image
    prueba = SALIDA / "prueba_proporcion.png"
    Image.new("RGB", (1200, 400), (200, 80, 60)).save(prueba)      # 3:1 bien marcada

    antes = {i["id"] for i in estado()["items"]}
    with sync_playwright() as p:
        nav = p.chromium.launch()
        # Se mete desde el TELÉFONO, que es como la metió Martín.
        pag = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        pag.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        pag.wait_for_timeout(2000)
        pag.set_input_files("#archImagen", str(prueba))
        pag.wait_for_timeout(2500)
        pag.close()

        nuevos = [i for i in estado()["items"] if i["id"] not in antes and i["tipo"] == "imagen"]
        if not nuevos:
            print("MAL: no entró la imagen de prueba")
            raise SystemExit(1)
        item = nuevos[-1]

        tel, e1 = medir(nav, 390, 844, item["id"])
        pc, e2 = medir(nav, 1400, 800, item["id"])
        nav.close()

    print(f"    proporción vista en el teléfono: {tel['prop']:.2f} · en la compu: {pc['prop']:.2f}")
    revisar("la imagen se dibuja con su proporción, no estirada",
            tel["modo"], "xMidYMid meet")
    revisar("en el teléfono se ve 3:1", round(tel["prop"], 1), 3.0)
    revisar("en la compu también", round(pc["prop"], 1), 3.0)
    revisar("o sea: la misma forma en las dos pantallas",
            abs(tel["prop"] - pc["prop"]) < 0.15, True)
    revisar("sin errores de javascript", e1 + e2, [])

    # Dejar el tablero como estaba.
    urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/pizarra/item/{item['id']}", method="DELETE"), timeout=10).read()
    revisar("se limpió la imagen de la prueba",
            any(i["id"] == item["id"] for i in estado()["items"]), False)
    prueba.unlink(missing_ok=True)

    print("\nTODO BIEN" if not fallas else f"\nFALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
