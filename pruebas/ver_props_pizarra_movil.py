"""La hoja de propiedades de la pizarra, en el teléfono: entera y con cómo guardarla.

Pedido de Martín (2026-08-17): "me queda recortado el menú de propiedades del objeto, me
gustaría poder también un botoncito para desplegarlo o guardarlo".

Lo que fija esta prueba:
  * la hoja tiene su cabecera con el ▾ (solo en el teléfono);
  * el ▾ la deja en una tira fina, y se acuerda de cómo la dejaste;
  * abierta, entra en pantalla (no se come más de la mitad) y si no entra, se corre
    con el dedo con la cabecera pegada arriba — nunca queda una sección cortada sin
    forma de llegar a ella;
  * con la barra de herramientas guardada, la hoja baja y usa ese lugar.

⚠ Solo selecciona un objeto por código y mira medidas: no mueve, no borra y no cambia
nada del tablero.

Correr con:  python -m pruebas.ver_props_pizarra_movil   (con el panel prendido)
"""
import json
import sys
import urllib.request

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
    d = json.loads(urllib.request.urlopen(BASE + "/pizarra/estado", timeout=10).read())
    libres = [i for i in d["items"] if not i.get("bloqueado")]
    if not libres:
        print("MAL: no hay ningún objeto libre en el tablero para probar")
        raise SystemExit(1)
    # ⚠ Se busca una FIGURA (rectángulo/círculo), que es la que tiene todas las
    # secciones. Antes se agarraba el primer objeto libre y el día que ese primero
    # pasó a ser una imagen —que solo tiene cuatro— la prueba falló sola (2026-08-17).
    figuras = [i for i in libres if i.get("tipo") in ("rectangulo", "circulo")]
    item = (figuras or libres)[0]["id"]

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport=TELEFONO, has_touch=True)
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/pizarra", wait_until="domcontentloaded")
        pag.wait_for_timeout(2200)
        pag.evaluate("() => { localStorage.removeItem('propsPlegado');"
                     "         localStorage.removeItem('barraPlegada');"
                     "         document.getElementById('panelProps').classList.remove('plegado');"
                     "         document.getElementById('toolbar').classList.remove('plegado');"
                     "         document.body.classList.remove('barra-plegada'); }")
        medir = """id => {
          if (id) { seleccion = new Set([id]); refrescarPanel(); }
          const pp = document.getElementById('panelProps'), c = pp.getBoundingClientRect();
          return {visible: getComputedStyle(pp).display !== 'none',
                  alto: Math.round(c.height),
                  arriba: Math.round(c.top), abajo: Math.round(innerHeight - c.bottom),
                  cortado: pp.scrollHeight > pp.clientHeight + 2,
                  cabecera: !!document.getElementById('propsCabecera').offsetParent,
                  // Desde el rediseño del 2026-08-17 se ve UNA sección por vez,
                  // elegida con pestañitas: se cuentan las pestañas y la abierta.
                  pestanas: document.querySelectorAll('#chipsProps .chip').length,
                  pestanas_visibles: !!document.getElementById('chipsProps').offsetParent,
                  ancho: Math.round(c.width),
                  // ⚠ `offsetParent`: plegada, la sección sigue teniendo la clase
                  // pero no se ve (la esconde la hoja). Lo que importa es si se VE.
                  abierta: !!(document.querySelector('#panelProps .grupo.abierto')||{}).offsetParent,
                  controles: [...pp.querySelectorAll('.grupo.abierto .accion, .grupo.abierto .sw,'
                                                   + ' .grupo.abierto input')].length};
        }"""
        # ⭐ Lo que Martín marcó el 2026-08-17: la hoja NO se puede montar encima de la
        # barra de herramientas. La barra cambia de alto (dos renglones abierta, uno
        # guardada), así que el lugar de la hoja se calcula midiéndola, no con un número.
        pisan = """() => {
          const a = document.getElementById('panelProps').getBoundingClientRect();
          const b = document.getElementById('toolbar').getBoundingClientRect();
          return !(a.bottom <= b.top || b.bottom <= a.top ||
                   a.right <= b.left || b.right <= a.left);
        }"""
        abierto = pag.evaluate(medir, item)
        revisar("la hoja no se monta sobre la barra", pag.evaluate(pisan), False)
        revisar("con algo seleccionado, la hoja se ve", abierto["visible"], True)
        revisar("y tiene su cabecera con el botón", abierto["cabecera"], True)
        revisar("con una pestañita por sección que aplica", abierto["pestanas"] >= 4, True)
        revisar("y una sección abierta con sus controles",
                abierto["abierta"] and abierto["controles"] > 2, True)
        # Con el rediseño la hoja son dos renglones: pestañas + la sección elegida.
        revisar("y ocupa dos renglones, no media pantalla", abierto["alto"] <= 140, True)
        revisar("y sin que quede nada abajo de la pantalla", abierto["arriba"] >= 0, True)
        pag.screenshot(path=str(SALIDA / "pizarra_props_movil.png"))

        # --- Guardarla ---
        pag.click("#btnProps")
        pag.wait_for_timeout(400)
        plegado = pag.evaluate(medir, None)
        # ⭐ Guardada se esconde ENTERA: queda un botón chiquito contra el borde, no la
        # fila de pestañitas (Martín, 2026-08-17: "quiero que se oculte completo").
        revisar("guardándola queda solo un botón", plegado["alto"] <= 48, True)
        revisar("de ancho de botón, no de pantalla", plegado["ancho"] <= 60, True)
        revisar("sin ninguna sección a la vista", plegado["abierta"], False)
        revisar("y sin las pestañitas tampoco", plegado["pestanas_visibles"], False)
        revisar("el botón dice qué trae de vuelta",
                pag.evaluate("() => document.getElementById('btnProps').textContent"), "🎛")
        pag.screenshot(path=str(SALIDA / "pizarra_props_plegado.png"))

        pag.reload(wait_until="domcontentloaded")
        pag.wait_for_timeout(2000)
        revisar("y se acuerda de que la guardaste",
                pag.evaluate(medir, item)["abierta"], False)
        pag.click("#btnProps")
        pag.wait_for_timeout(400)
        revisar("volviendo a tocarlo, vuelve la sección",
                pag.evaluate(medir, None)["abierta"], True)

        # --- Con la barra de herramientas guardada, la hoja baja ---
        antes = pag.evaluate(medir, None)["abajo"]
        pag.click("#btnPlegar")
        pag.wait_for_timeout(400)
        despues = pag.evaluate(medir, None)["abajo"]
        revisar("guardando la barra, la hoja baja y usa ese lugar", despues < antes, True)
        revisar("y tampoco tapa el botón de volver a abrirla", pag.evaluate(pisan), False)

        pag.evaluate("() => { localStorage.removeItem('propsPlegado');"
                     "         localStorage.removeItem('barraPlegada'); }")
        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncapturas: {SALIDA / 'pizarra_props_movil.png'} y pizarra_props_plegado.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
