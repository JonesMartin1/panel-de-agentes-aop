"""El botón "Sesiones" del celular te deja SIEMPRE arriba de todo, en Todas.

Pedido de Martín (2026-08-17): "cuando yo le dé a conversaciones tiene que mandarme
siempre a arriba de todo de todos". Es el botón de volver al principio: no importa en
qué carpeta habías quedado, qué habías filtrado ni dónde estaba el scroll.

⚠ El guardado de pestañas se intercepta: no le toca las pestañas del teléfono a nadie.

Correr con:  python -m pruebas.ver_movil_todas   (con el panel prendido)
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


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}")
            if r.request.method == "POST" else r.continue_())
        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)

        # Dejar la pantalla "sucia" a propósito: otra carpeta, un filtro escrito, el
        # scroll abajo y parado en otra pestaña.
        proy = pag.evaluate("() => (sesiones.length, Object.keys({}), "
                            "  [...document.querySelectorAll('#cajon .carpeta')].length)")
        pag.evaluate("() => ir('nueva')")
        pag.wait_for_timeout(1800)
        pag.evaluate("""() => {
          const otra = [...document.querySelectorAll('#cajon .carpeta:not(.todas) .nom')]
                       .map(n => n.textContent)[0];
          if (otra) elegirProyecto(otra);
        }""")
        pag.wait_for_timeout(1500)
        revisar("quedamos en una carpeta, no en Todas",
                pag.evaluate("() => proyElegido !== TODAS"), True)
        pag.evaluate("() => { filtroSes = 'zzz'; ir('pizarra'); }")
        pag.wait_for_timeout(1200)
        revisar("y en otra pantalla", pag.evaluate("() => activa"), "pizarra")

        # --- Ahora sí: tocar "Sesiones" ---
        pag.click('#abajo .dest[data-ir="nueva"]')
        pag.wait_for_timeout(2000)
        revisar("tocando Sesiones, la carpeta es Todas",
                pag.evaluate("() => proyElegido === TODAS"), True)
        revisar("el filtro quedó limpio", pag.evaluate("() => filtroSes"), "")
        revisar("y arranca arriba de todo",
                pag.evaluate("() => document.getElementById('cuerpo').scrollTop"), 0)
        pag.screenshot(path=str(SALIDA / "movil_todas_arriba.png"))

        # Y estando YA en la lista, scrolleado abajo: vuelve arriba igual.
        pag.evaluate("() => { document.getElementById('cuerpo').scrollTop = 900; }")
        pag.wait_for_timeout(300)
        revisar("bajamos a mano", pag.evaluate(
            "() => document.getElementById('cuerpo').scrollTop") > 100, True)
        pag.click('#abajo .dest[data-ir="nueva"]')
        pag.wait_for_timeout(1200)
        revisar("tocándolo de nuevo, vuelve arriba",
                pag.evaluate("() => document.getElementById('cuerpo').scrollTop"), 0)

        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'movil_todas_arriba.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
