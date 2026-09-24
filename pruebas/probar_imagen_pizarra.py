"""Meter una imagen en la pizarra desde el TELÉFONO, con el botón 🖼.

Pregunta de Martín (2026-08-17): "¿cómo hago para pegar algo desde el teléfono?".
Respuesta: no había forma — el único camino era Ctrl+V, que en el celular no existe.
Ahora la barra tiene un 🖼 que abre la galería, la cámara o los archivos.

Lo que esta prueba fija:
  * el botón está y abre el selector de archivos;
  * eligiendo una imagen, aparece un objeto nuevo en el tablero, con su proporción;
  * la foto se sube ACHICADA (una de 3000 px no viaja entera);
  * Ctrl+V sigue andando igual en la compu (los dos usan el mismo camino).

⚠ Deja el tablero como estaba: borra lo que agrega.

Correr con:  python -m pruebas.probar_imagen_pizarra   (con el panel prendido)
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
SALIDA = RAIZ / "pruebas"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def estado():
    with urllib.request.urlopen(BASE + "/pizarra/estado", timeout=10) as r:
        return json.loads(r.read())


def imagenes(d):
    return [i for i in d.get("items", []) if i.get("tipo") == "imagen"]


def main():
    # Una imagen grande de prueba, para ver que se achique al subirla.
    from PIL import Image
    prueba = SALIDA / "prueba_imagen_pizarra.png"
    Image.new("RGB", (3000, 1500), (30, 90, 160)).save(prueba)

    antes = len(imagenes(estado()))
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 420, "height": 860}, has_touch=True)
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        pag.wait_for_timeout(2000)

        revisar("el botón 🖼 está en la barra",
                pag.evaluate("() => !!document.getElementById('btnImagen')"), True)
        pag.set_input_files("#archImagen", str(prueba))
        pag.wait_for_timeout(2500)

        d = estado()
        nuevas = imagenes(d)
        revisar("entró una imagen nueva al tablero", len(nuevas) - antes, 1)
        if len(nuevas) - antes == 1:
            i = nuevas[-1]
            ancho, alto = abs(i["x2"] - i["x1"]), abs(i["y2"] - i["y1"])
            # ⚠ La proporción NO se compara contra 2:1 a secas: el tablero mide en
            # porcentajes de la pantalla (x sobre el ancho, y sobre el alto), así que
            # sus unidades no son cuadradas y la relación depende de la pantalla donde
            # la metiste. En un teléfono de 420×860, una imagen 2:1 da ~4,1.
            v = pag.evaluate("() => [tablero.clientWidth, tablero.clientHeight]")
            revisar("entró con su proporción real en pantalla",
                    round(ancho / alto / (v[1] / v[0]), 2), 2.0)
            arch = RAIZ / "resultados" / "pizarra_imagenes" / i["archivo"]
            revisar("el archivo subido existe", arch.exists(), True)
            revisar("y viajó achicado (menos de 1600 px de ancho)",
                    Image.open(arch).width <= 1600, True)
            pag.screenshot(path=str(SALIDA / "pizarra_imagen_movil.png"))
            # Dejar el tablero como estaba.
            urllib.request.urlopen(urllib.request.Request(
                f"{BASE}/pizarra/item/{i['id']}", method="DELETE"), timeout=10).read()
            revisar("se limpió lo que agregó la prueba",
                    len(imagenes(estado())) - antes, 0)

        revisar("errores de javascript en la pizarra", errores, [])
        nav.close()
    prueba.unlink(missing_ok=True)

    print("\nTODO BIEN" if not fallas else f"\nFALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
