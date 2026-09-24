"""La columna de la izquierda se desplaza, y la BARRA está a la vista para arrastrarla.

Pedido de Martín (2026-09-13), con una captura de `/sesiones` en su monitor vertical:
"me falta un botón para poder desplazarme en esta barra para abajo", y enseguida la
corrección que define esto: **"en vez de un botón, quiero que sea la barra que
desplaza"**.

Eran dos cosas y la primera era un defecto de verdad:

  1. ⚠⚠ Con el explorador de archivos PLEGADO, la lista de proyectos se quedaba **sin
     ningún scroll**. `body.arbol-plegado #paneProy{max-height:none}` le sacaba el tope
     pero el piso seguía en `flex:0 0 auto`: crecía hasta el alto de sus carpetas, el
     `aside` (que es `overflow:hidden`) lo recortaba, y el final de la lista —Escondidas
     y "＋ Agregar una carpeta…"— quedaba inalcanzable. Ni la rueda llegaba: el que
     desbordaba era el aside, que no scrollea.
  2. Y sin scroll no hay barra que mostrar. Con el scroll arreglado, la barra se dibuja
     a mano (`::-webkit-scrollbar`) para que sea de las CLÁSICAS: ocupa su ancho, se ve
     siempre que haya algo que desplazar y se puede agarrar con el mouse. La de fábrica
     de Chrome en Windows se esconde sola.

⚠⚠ **Esto NO se puede medir en headless**: ahí Chrome usa barras superpuestas y toda
barra mide cero, la nueva y la vieja — el instrumento diría "no hay barra" con el CSS
puesto. Por eso abre una ventana de verdad (`headless=False`) y, antes de medir nada,
comprueba que en ESA ventana la barra de fábrica ocupe ancho. Si no, no mide: avisa.

No toca ningún endpoint que escriba: solo lee la pantalla y mueve el mouse sobre la
barra. No manda mensajes ni arranca ninguna sesión.

Correr con:  python -m pruebas.ver_barra_columna            (con el panel prendido)
             python -m pruebas.ver_barra_columna --viejo    # tiene que FALLAR
"""
import subprocess
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
VIEJO = "--viejo" in sys.argv
SALIDA = RAIZ / "pruebas" / ("barra_columna_viejo.png" if VIEJO else "barra_columna.png")
# Los chequeos que el código de ANTES no puede pasar: son los que prueban que esto existe.
CLAVE = ("con el explorador plegado la lista tiene algo que desplazar",
         "y el aside ya no recorta nada por su cuenta",
         "la barra ocupa su ancho (o sea: se ve, no es de las que se esconden)",
         "con la rueda adentro de la columna se llega al final de la lista")

fallas = []


def leer(rel):
    if VIEJO:
        return subprocess.run(["git", "show", "HEAD:" + rel], cwd=RAIZ,
                              capture_output=True, encoding="utf-8").stdout
    return (RAIZ / rel).read_text(encoding="utf-8")


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}" + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


# Carpetas de mentira para que la lista desborde SIEMPRE, tenga Martín tres proyectos o
# treinta: lo que se prueba es el desplazamiento, no cuántas carpetas tiene hoy.
RELLENAR = """(n) => {
  const c = document.querySelector('#carpetas');
  for (let i = 0; i < n; i++){
    const d = document.createElement('div');
    d.className = 'carpeta relleno';
    d.innerHTML = '<span>📁</span><span class="nom">Carpeta de prueba ' + i + '</span>';
    c.appendChild(d);
  }
}"""
VACIAR = """() => { document.querySelectorAll('#carpetas .carpeta').forEach((d, i) => {
  if (i > 2) d.remove(); }); }"""

MEDIR = """() => {
  const p = document.querySelector('#paneProy'), a = document.querySelector('aside');
  const s = document.querySelector('#sumar').getBoundingClientRect();
  return {barra: p.offsetWidth - p.clientWidth,
          sobra: p.scrollHeight - p.clientHeight,
          asideDesborda: a.scrollHeight - a.clientHeight,
          finalALaVista: s.top >= 0 && Math.round(s.bottom) <= window.innerHeight};
}"""
# ⚠ El control del instrumento: en esta ventana, ¿una barra común ocupa ancho? En
# headless da cero y la prueba entera estaría midiendo humo.
BARRA_DE_FABRICA = """() => {
  const t = document.createElement('div');
  t.style.cssText = 'position:fixed;top:-500px;width:100px;height:50px;overflow-y:scroll';
  t.innerHTML = '<div style="height:300px"></div>';
  document.body.appendChild(t);
  const w = t.offsetWidth - t.clientWidth; t.remove(); return w;
}"""


def main():
    html = leer("app/estaticos/sesiones.html")
    with sync_playwright() as pw:
        # ⚠ Ventana de verdad a propósito: ver el comentario de arriba.
        nav = pw.chromium.launch(channel="chrome", headless=False)
        pag = nav.new_page(viewport={"width": 460, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route(BASE + "/sesiones", lambda r: r.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=html))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(3000)

        defabrica = pag.evaluate(BARRA_DE_FABRICA)
        if not defabrica:
            print("Esta ventana usa barras superpuestas (miden 0): acá no se puede medir "
                  "si la barra se ve. Correlo en una ventana normal de Chrome.")
            nav.close()
            return 2
        print(f"(el instrumento sirve: una barra común mide {defabrica} px acá)\n")

        # --- Con el explorador PLEGADO, que es como lo tiene él en la captura ---------
        pag.evaluate("document.body.classList.add('arbol-plegado')")
        pag.evaluate(RELLENAR, 12)
        pag.wait_for_timeout(400)
        d = pag.evaluate(MEDIR)
        revisar("con el explorador plegado la lista tiene algo que desplazar",
                d["sobra"] > 0, f"sobran {d['sobra']} px")
        revisar("y el aside ya no recorta nada por su cuenta",
                d["asideDesborda"] == 0, f"desborda {d['asideDesborda']} px")
        revisar("la barra ocupa su ancho (o sea: se ve, no es de las que se esconden)",
                d["barra"] >= 8, f"{d['barra']} px")
        revisar("la barra es más fina que la de fábrica, no un tablón",
                0 < d["barra"] <= defabrica, f"{d['barra']} contra {defabrica} px")
        revisar("el final de la lista todavía no se ve (si no, no habría nada que probar)",
                not d["finalALaVista"])

        # --- Bajar de verdad: con la rueda adentro de la columna ---------------------
        # ⚠ Arrastrar el pulgar NO se puede simular: la barra no es parte de la página y
        # los clics sintéticos no la agarran. Lo que sí se mide es lo que la hace
        # arrastrable — que ocupe ancho, o sea que no sea de las superpuestas (arriba) —
        # y que la columna se desplace de verdad hasta el final.
        centro = pag.evaluate("""() => {
          const r = document.querySelector('#paneProy').getBoundingClientRect();
          return [Math.round(r.left + 60), Math.round((r.top + r.bottom) / 2)];}""")
        pag.mouse.move(*centro)
        for _ in range(6):
            pag.mouse.wheel(0, 900)
            pag.wait_for_timeout(120)
        pag.wait_for_timeout(300)
        d2 = pag.evaluate(MEDIR)
        bajo = pag.evaluate("Math.round(document.querySelector('#paneProy').scrollTop)")
        revisar("con la rueda adentro de la columna se llega al final de la lista",
                d2["finalALaVista"], f"bajó {bajo} px")
        pag.screenshot(path=str(SALIDA))

        # --- Con la lista corta no aparece ninguna barra de adorno --------------------
        pag.evaluate(VACIAR)
        pag.wait_for_timeout(300)
        d3 = pag.evaluate(MEDIR)
        revisar("con pocas carpetas no hay barra ni nada que desplazar",
                d3["barra"] == 0 and d3["sobra"] == 0,
                f"barra {d3['barra']} px, sobra {d3['sobra']} px")

        # --- Y el explorador DESPLEGADO sigue como estaba -----------------------------
        pag.evaluate("document.body.classList.remove('arbol-plegado')")
        pag.evaluate(RELLENAR, 12)
        pag.wait_for_timeout(400)
        d4 = pag.evaluate(MEDIR)
        revisar("con el explorador abierto la lista sigue con su tope y su barra",
                d4["sobra"] > 0 and d4["barra"] >= 8,
                f"sobran {d4['sobra']} px, barra {d4['barra']} px")
        revisar("y el explorador conserva su propio lugar abajo",
                pag.evaluate("document.querySelector('#arbol').clientHeight") > 0)

        revisar("ningún error de JavaScript en la pantalla", not errores, str(errores[:2]))
        nav.close()

    print(f"\nla captura quedó en {SALIDA}")
    if VIEJO:
        cayeron = [f for f in fallas if f in CLAVE]
        print(f"\n--viejo: cayeron {len(cayeron)} de {len(CLAVE)} chequeos clave")
        for c in cayeron:
            print("   -", c)
        return 0 if len(cayeron) == len(CLAVE) else 1
    if fallas:
        print(f"\n{len(fallas)} mal:", *fallas, sep="\n  - ")
        return 1
    print("\ntodo bien")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
