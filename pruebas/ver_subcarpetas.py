"""Las charlas activas colgando de su carpeta, como subcarpetas (2026-10-10).

Pedido de Martín: *"me gustaría poder ver las sesiones activas como subcarpetas"*.
Activa = abierta en la barra de pestañas, o trabajando aunque no esté abierta. Clic entra,
botón del medio abre otra pestaña del navegador, la flechita las pliega, y arrastrar una
carpeta sigue moviendo carpetas (las subcarpetas no cuentan como carpeta).

⚠ Todo con datos inventados interceptados en el contexto: no toca charlas de Martín.

Correr con:  python -m pruebas.ver_subcarpetas   (con el panel prendido)
"""
import json
import sys
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"
fallas = []

PROYECTOS = ["alfa", "beta", "gama"]
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": PROYECTOS, "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-" + str(k), "nombre": "charla " + str(k) + " de " + n,
                                         "ts": 10 - k, "ultimo": "vos", "viva": False,
                                         # gama-2 está trabajando sin estar abierta
                                         "ocupada": n == "gama" and k == 2,
                                         "interactiva": False, "detalle": "lo último dicho"}
                                        for k in range(3)]}
                          for n in PROYECTOS]}


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def columna(pag):
    """La columna como se lee: carpetas y, con sangría, sus charlas colgadas."""
    return pag.evaluate("""() => [...document.querySelectorAll('#carpetas > div')]
      .filter(e => e.dataset.proy && e.dataset.proy.indexOf('Todas') < 0 || e.dataset.subsid)
      .map(e => e.dataset.subsid ? '  ' + e.dataset.subsid : e.dataset.proy)""")


def donde(r):
    sid = parse_qs(urlparse(r.request.url).query).get("sid", [""])[0]
    r.fulfill(status=200, content_type="application/json",
              body=json.dumps({"ok": True, "cwd": "D:\\pruebas\\" + sid.split("-")[0],
                               "nombre": "charla " + sid}))


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores, nuevas, escritos = [], [], []
    ctx.on("page", lambda pg: nuevas.append(pg))
    ctx.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    ctx.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"mensajes":[]}'))
    ctx.route("**/movil/donde*", donde)
    ctx.route("**/carpetas/**", lambda r: (
        escritos.append(r.request.url.split("/carpetas/")[1]) if r.request.method == "POST" else None,
        r.fulfill(status=200, content_type="application/json", body='{"ok":true}')))

    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.add_init_script("if (!sessionStorage.getItem('ya')) { localStorage.clear(); sessionStorage.setItem('ya', '1'); }")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=8000)
    pag.wait_for_timeout(800)
    nuevas.clear()

    revisar("sin nada abierto, solo cuelga la que está trabajando",
            columna(pag), ["alfa", "beta", "gama", "  gama-2"])
    revisar("y se marca como trabajando",
            pag.evaluate("() => document.querySelector('[data-subsid=\"gama-2\"]').classList.contains('trabaja')"), True)

    # Abrir dos charlas de alfa y una de beta: quedan colgando cada una de la suya.
    for sid in ["alfa-1", "beta-0", "alfa-2"]:
        pag.evaluate("() => { activa = null; irProyecto(TODAS); }")
        pag.wait_for_timeout(300)
        pag.click("#cuerpo .correo[data-sid='" + sid + "']")
        pag.wait_for_timeout(500)
    revisar("⭐ las abiertas cuelgan de su carpeta, en el orden de las pestañas",
            columna(pag), ["alfa", "  alfa-1", "  alfa-2", "beta", "  beta-0", "gama", "  gama-2"])
    revisar("la que estás leyendo se marca",
            pag.evaluate("() => [...document.querySelectorAll('.subcarpeta.sel')].map(e => e.dataset.subsid)"),
            ["alfa-2"])

    # Clic en una subcarpeta = entrar a esa charla.
    pag.click(".subcarpeta[data-subsid='beta-0']")
    pag.wait_for_timeout(500)
    revisar("⭐ clic en una subcarpeta entra a esa charla", pag.evaluate("() => activa"), "beta-0")
    revisar("y la marca pasa a ella",
            pag.evaluate("() => [...document.querySelectorAll('.subcarpeta.sel')].map(e => e.dataset.subsid)"),
            ["beta-0"])

    # Botón del medio = otra pestaña del navegador, sin moverte.
    caja = pag.locator(".subcarpeta[data-subsid='alfa-1']").bounding_box()
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2, button="middle")
    pag.wait_for_timeout(800)
    revisar("el botón del medio la abre en otra pestaña del navegador",
            [parse_qs(urlparse(x.url).query).get("c") for x in nuevas], [["alfa-1"]])
    for x in nuevas:
        x.close()
    revisar("y te deja donde estabas", pag.evaluate("() => activa"), "beta-0")

    # Plegar alfa: sus charlas se esconden y queda guardado.
    pag.click("[data-plegar='alfa']")
    pag.wait_for_timeout(300)
    revisar("⭐ la flechita pliega las charlas de esa carpeta",
            columna(pag), ["alfa", "beta", "  beta-0", "gama", "  gama-2"])
    revisar("plegar no te cambia de carpeta ni de charla", pag.evaluate("() => activa"), "beta-0")
    pag.reload(wait_until="domcontentloaded")
    pag.wait_for_timeout(1800)
    revisar("y sigue plegada al recargar",
            [x for x in columna(pag) if x.startswith("  alfa")], [])
    pag.click("[data-plegar='alfa']")
    pag.wait_for_timeout(300)
    revisar("la flechita la vuelve a desplegar",
            [x for x in columna(pag) if x.startswith("  alfa")], ["  alfa-1", "  alfa-2"])

    # Cerrar una pestaña la saca de la columna.
    pag.evaluate("() => { abiertas = abiertas.filter(t => t.sid !== 'alfa-1'); pintarTabs(); }")
    pag.wait_for_timeout(300)
    revisar("cerrar la pestaña la descuelga",
            [x for x in columna(pag) if x.startswith("  alfa")], ["  alfa-2"])

    # Arrastrar una carpeta: se mueve la carpeta y sus charlas vuelven a colgar de ella.
    escritos.clear()
    a = pag.locator("#carpetas .carpeta[data-proy='alfa']").bounding_box()
    g = pag.locator("#carpetas .carpeta[data-proy='gama']").bounding_box()
    pag.mouse.move(a["x"] + 40, a["y"] + a["height"] / 2)
    pag.mouse.down()
    pag.mouse.move(a["x"] + 40, a["y"] + a["height"] / 2 + 10, steps=3)
    g = pag.locator("#carpetas .carpeta[data-proy='gama']").bounding_box()
    pag.mouse.move(g["x"] + 40, g["y"] + g["height"] - 3, steps=8)
    pag.mouse.up()
    pag.wait_for_timeout(500)
    revisar("⭐ arrastrar alfa abajo de gama la mueve, con sus charlas detrás",
            columna(pag), ["beta", "  beta-0", "gama", "  gama-2", "alfa", "  alfa-2"])
    revisar("y guarda el orden nuevo", "orden" in escritos, True)

    # El ícono de la pestaña del navegador es el de la carpeta (con las pestañas de Chrome
    # en columna solo se ve eso, y antes eran todas el mismo globito).
    def icono_pestana():
        return pag.evaluate("""() => { const l = document.querySelector('link[rel=icon]');
          if (!l) return ''; const m = decodeURIComponent(l.href).match(/central">(.*)<\\/text>/);
          return m ? m[1] : '?'; }""")
    pag.evaluate("() => { iconos.beta = '🐮'; pintarCarpetas(); }")
    pag.evaluate("() => { activa = null; irProyecto(TODAS); }")
    pag.wait_for_timeout(300)
    revisar("en 'Todas' la pestaña tiene un ícono fijo", icono_pestana(), "🗂")
    pag.click("#cuerpo .correo[data-sid='beta-1']")
    pag.wait_for_timeout(500)
    revisar("⭐ en una charla de beta, la pestaña lleva el ícono de beta", icono_pestana(), "🐮")
    pag.click(".subcarpeta[data-subsid='alfa-2']")
    pag.wait_for_timeout(500)
    revisar("en una de alfa (sin ícono elegido), el de carpeta común", icono_pestana(), "📁")
    pag.evaluate("() => { iconos.alfa = '🦊'; pintarCarpetas(); }")
    revisar("cambiar el ícono de la carpeta cambia el de la pestaña en el acto", icono_pestana(), "🦊")
    pag.evaluate("() => { activa = null; irProyecto('beta'); }")
    pag.wait_for_timeout(300)
    revisar("la bandeja de una carpeta también lleva su ícono", icono_pestana(), "🐮")

    revisar("sin errores de JS", errores, [])
    nav.close()

print("")
print("todo bien" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
