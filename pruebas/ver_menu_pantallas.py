"""El menú de pantallas tiene que estar en LAS CINCO y llevar a todas.

Pedido de Martín (2026-08-17): "me gustaria en todas las pestañas poder entrar a todas
las pestañas". Antes cada pantalla solo tenía un "volver al panel", así que para ir de
la Pizarra al Estudio había que pasar por el panel.

No necesita el panel prendido ni reiniciarlo: importa `panel.py` para sacarle el HTML
de las páginas que viven adentro, lee los dos estáticos del disco, y sirve todo con
`page.route` (como `ver_estudio.py`). Importar no prende nada: el vigilante de
servicios es un evento de arranque de FastAPI y solo corre bajo uvicorn.

    python -m pruebas.ver_menu_pantallas
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # los emojis de los titulos

from playwright.sync_api import sync_playwright

import panel
from app.rutas import ESTATICOS, RESULTADOS

SALIDA = RESULTADOS / "capturas"
# ⚠ Este orden es el de `PANTALLAS` en menu.js y se compara tal cual: agregar una
# pantalla al menú es agregarla ACÁ también, o esta prueba se pone roja sola.
ESPERADAS = ["/", "/sesiones", "/pizarra", "/estudio", "/avisos"]
ok = fallas = 0


def chequeo(titulo, cond, detalle=""):
    global ok, fallas
    if cond:
        ok += 1
        print(f"  OK   {titulo}")
    else:
        fallas += 1
        print(f"  MAL  {titulo} {detalle}")


def paginas():
    """El HTML de todas: dos viven adentro de panel.py, las demás son archivos."""
    return {
        "/": panel.PAGINA,
        "/pizarra": panel.PAGINA_PIZARRA,
        "/sesiones": (ESTATICOS / "sesiones.html").read_text(encoding="utf-8"),
        "/estudio": (ESTATICOS / "estudio.html").read_text(encoding="utf-8"),
        "/avisos": (ESTATICOS / "avisos.html").read_text(encoding="utf-8"),
    }


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    htmls = paginas()
    menu = (ESTATICOS / "menu.js").read_text(encoding="utf-8")

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1500, "height": 900})

        # ⚠ Playwright prueba las rutas de la ULTIMA a la primera: el comodin va PRIMERO.
        # ⚠ Y un script NO se puede contestar con "{}" de JSON: el navegador tira
        #   "rough is not defined" y la prueba lo cuenta como error de la pantalla
        #   siendo del servidor inventado. Cada cosa con su tipo.
        def comodin(r):
            if r.request.resource_type == "script":
                return r.fulfill(status=200, content_type="application/javascript",
                                 body="window.rough={svg:()=>({})};")
            r.fulfill(status=200, content_type="application/json",
                      body='{"proyectos":[],"items":[],"sesiones":[],"pestanas":[]}')

        pag.route("**/*", comodin)
        pag.route("**/estaticos/menu.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=menu))
        # ⚠ El handler NO puede ser `lambda r, h=html: ...`: Playwright mira cuántos
        #   parámetros acepta y, si son dos, le pasa el Request como segundo — o sea que
        #   `h` deja de ser el HTML y termina mandando un objeto Request como cuerpo.
        #   Va una fábrica de handlers de UN solo parámetro.
        def sirviendo(html):
            return lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8",
                                       body=html)

        for ruta, html in htmls.items():
            pag.route(f"http://panel.local{ruta}", sirviendo(html))

        # Un solo oyente para toda la corrida: un error de JS deja la pantalla a medio
        # dibujar sin avisar. Se vacia al empezar cada pantalla.
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        for ruta in ESPERADAS:
            print(f"\n--- {ruta}")
            errores.clear()
            pag.goto(f"http://panel.local{ruta}", wait_until="domcontentloaded")
            pag.wait_for_timeout(900)   # networkidle NUNCA llega: estas paginas hacen polling

            m = pag.evaluate("""() => {
                const n = document.getElementById('menuPantallas');
                if (!n) return null;
                const r = n.getBoundingClientRect();
                return {
                  destinos: [...n.querySelectorAll('a')].map(a => new URL(a.href).pathname),
                  aca: [...n.querySelectorAll('a.aca')].map(a => new URL(a.href).pathname),
                  visible: r.width > 0 && r.height > 0 && r.top >= 0,
                  clickeable: getComputedStyle(n.querySelector('a.aca')||n).pointerEvents,
                };
            }""")

            chequeo("la pantalla tiene el menú", m is not None)
            if not m:
                continue
            chequeo("lleva a todas las pantallas", m["destinos"] == ESPERADAS,
                    f"({m['destinos']})")
            chequeo("se ve (no quedó tapado ni de alto cero)", m["visible"])
            chequeo("marca la pantalla en la que estás", m["aca"] == [ruta], f"({m['aca']})")
            chequeo("y esa marcada no se puede clickear", m["clickeable"] == "none")

            # Un clic de verdad, para que no sea solo un href bien escrito.
            otra = "/estudio" if ruta != "/estudio" else "/pizarra"
            pag.click(f'#menuPantallas a[href="{otra}"]')
            pag.wait_for_timeout(700)
            chequeo(f"desde acá se entra a {otra}",
                    pag.evaluate("location.pathname") == otra,
                    f"(quedó en {pag.evaluate('location.pathname')})")
            pag.go_back()
            pag.wait_for_timeout(400)

            chequeo("sin errores de JS", not errores, str(errores[:2]))
            pag.goto(f"http://panel.local{ruta}", wait_until="domcontentloaded")
            pag.wait_for_timeout(500)
            caja = "header" if ruta in ("/", "/pizarra") else "#barra"
            pag.locator(caja).first.screenshot(
                path=str(SALIDA / f"menu{ruta.replace('/', '_') or '_panel'}.png"))

        nav.close()

    print(f"\n{ok} bien, {fallas} mal")
    print(f"capturas en {SALIDA}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
