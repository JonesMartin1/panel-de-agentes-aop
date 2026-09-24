"""Dos cosas del celular que molestaban, marcadas por Martín el 2026-08-17:

  1. **con el teclado abierto, la barra de abajo (Inicio/Hablar/Pizarra/Sesiones)
     quedaba flotando en el medio de la pantalla** — iOS achica la ventana visual pero
     no el alto de la página, así que la barra pegada al final se veía arriba del
     teclado. Ahora se esconde mientras escribís y vuelve sola;
  2. **la barra de herramientas de la pizarra no se podía guardar**: son dos renglones
     encima del tablero y a veces uno quiere mirar lo que hay. Ahora se pliega a un
     solo botón y se acuerda de cómo la dejaste.

Correr con:  python -m pruebas.ver_barra_pizarra_movil   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
TELEFONO = {"width": 390, "height": 844}
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # --- 1) La barra de abajo con el teclado abierto ---
        # El teclado no se puede abrir de verdad en un navegador de escritorio, así que
        # se simula lo que ve la página: la ventana visual encogida. Es exactamente la
        # señal que mira el código.
        tel = nav.new_page(viewport=TELEFONO, has_touch=True)
        errores = []
        tel.on("pageerror", lambda e: errores.append(str(e)))
        tel.goto(BASE + "/movil", wait_until="domcontentloaded")
        tel.wait_for_timeout(2200)
        revisar("sin teclado, la barra de abajo se ve",
                tel.evaluate("() => !!document.getElementById('abajo').offsetParent"), True)
        # Tocar la caja de escribir = teclado afuera. Es la señal que mira el código:
        # el foco, no el tamaño de la ventana (agregada a la pantalla de inicio, la app
        # se achica entera con el teclado y la cuenta de tamaños nunca daba).
        # Se usa el buscador de la bandeja, que siempre está: en una conversación la
        # caja de escribir puede estar escondida (si esa sesión está abierta en la compu
        # solo se mira) y ahí no habría teclado que probar.
        tel.evaluate("() => ir('nueva')")
        tel.wait_for_timeout(1800)
        tel.focus("#filtroSes")
        tel.wait_for_timeout(500)
        revisar("escribiendo, la barra de abajo se esconde",
                tel.evaluate("() => !!document.getElementById('abajo').offsetParent"), False)
        tel.evaluate("() => document.getElementById('filtroSes').blur()")
        tel.wait_for_timeout(500)
        revisar("al soltar la caja, vuelve sola",
                tel.evaluate("() => !!document.getElementById('abajo').offsetParent"), True)
        # Y el refuerzo por si el teclado sale sin que enfoquemos nada nosotros.
        tel.evaluate("""() => {
          Object.defineProperty(window.visualViewport, 'height', {value: 380, configurable: true});
          window.visualViewport.dispatchEvent(new Event('resize'));
        }""")
        tel.wait_for_timeout(400)
        revisar("y si el teclado sale solo, también se esconde",
                tel.evaluate("() => !!document.getElementById('abajo').offsetParent"), False)
        revisar("errores de javascript en la app", errores, [])

        # --- 2) Guardar la barra de herramientas de la pizarra ---
        piz = nav.new_page(viewport=TELEFONO, has_touch=True)
        errores_p = []
        piz.on("pageerror", lambda e: errores_p.append(str(e)))
        piz.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        piz.wait_for_timeout(2000)
        piz.evaluate("() => localStorage.removeItem('barraPlegada')")
        piz.reload(wait_until="domcontentloaded")
        piz.wait_for_timeout(1800)

        alto = lambda: round(piz.evaluate(
            "() => document.getElementById('toolbar').getBoundingClientRect().height"))
        visibles = lambda: piz.evaluate(
            "() => [...document.querySelectorAll('#toolbar button')]"
            ".filter(b => b.offsetParent).length")
        revisar("abierta, están todas las herramientas", visibles() > 10, True)
        entera = alto()
        revisar("y ocupa dos renglones", entera < 120, True)

        piz.click("#btnPlegar")
        piz.wait_for_timeout(500)
        revisar("guardándola, queda un solo botón", visibles(), 1)
        # Plegada tiene que ser UN renglón de botón y nada más (40 px + el marco).
        revisar("y ocupa un solo botón de alto", alto() <= 56, True)
        piz.screenshot(path=str(SALIDA / "pizarra_barra_plegada.png"))

        piz.reload(wait_until="domcontentloaded")
        piz.wait_for_timeout(1800)
        revisar("y se acuerda de que la guardaste", visibles(), 1)
        piz.click("#btnPlegar")
        piz.wait_for_timeout(500)
        revisar("volviendo a tocarlo, vuelven todas", visibles() > 10, True)
        revisar("errores de javascript en la pizarra", errores_p, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'pizarra_barra_plegada.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
