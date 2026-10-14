"""Botón del medio del mouse sobre una conversación: pestaña nueva DEL NAVEGADOR.

Pedido de Martín (2026-08-19): *"me gustaría poder hacer click con el botón del medio del
mouse sobre las sesiones y se me abran en una nueva pestaña las conversaciones"*. Primero
se leyó como "pestaña de la barra del panel"; el 2026-10-10 lo aclaró: *"tiene que abrirse
una nueva pestaña en el navegador"*, como cualquier enlace de Chrome.

Lo que más importa acá es lo que NO pasa: que el botón del medio no te cambie de pantalla.
Por eso la mitad de los chequeos miran que después del clic sigas parado en la lista.

⚠ `/movil/sesiones`, `/movil/chat` y `/movil/donde` se interceptan en el CONTEXTO (no en
la página): así la pestaña nueva también ve la lista inventada y no le toca ni una
conversación a Martín. El navegador de Playwright tiene su propio perfil, así que el
`localStorage.clear()` de acá no le borra las pestañas abiertas en su Chrome.

Correr con:  python -m pruebas.ver_boton_medio   (con el panel prendido)
"""
import json
import sys
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"
fallas = []

PROYECTOS = ["alfa", "beta"]
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": PROYECTOS, "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-" + str(k), "nombre": "charla " + str(k) + " de " + n,
                                         "ts": 10 - k, "ultimo": "vos", "viva": False,
                                         "interactiva": False, "detalle": "lo último dicho"}
                                        for k in range(3)]}
                          for n in PROYECTOS]}


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def tabs(pag):
    """Las conversaciones abiertas en la barra del panel (del estado, no del DOM)."""
    return pag.evaluate("() => abiertas.map(t => t.sid)")


def enLaLista(pag):
    """¿Seguís mirando la bandeja? (y no adentro de una conversación)"""
    return pag.evaluate("() => activa === null && !!document.querySelector('#cuerpo .correo')")


def clicMedio(pag, selector):
    caja = pag.locator(selector).first.bounding_box()
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2,
                    button="middle")


def donde(r):
    sid = parse_qs(urlparse(r.request.url).query).get("sid", [""])[0]
    proy = sid.split("-")[0]
    r.fulfill(status=200, content_type="application/json",
              body=json.dumps({"ok": True, "cwd": "D:\\pruebas\\" + proy, "nombre": "charla " + sid}))


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores = []
    nuevas = []          # las pestañas del NAVEGADOR que se abrieron
    ctx.on("page", lambda pg: nuevas.append(pg))

    ctx.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    ctx.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"mensajes":[]}'))
    ctx.route("**/movil/donde*", donde)
    # Nada de escrituras: si algo sale para el panel de verdad, muere acá y se anota.
    # ⚠ Menos `aspecto/sembrar`: lo manda toda página que arranca con el `localStorage`
    # vacío (pasa los colores viejos al servidor), no el botón del medio. Igual muere acá.
    escapados = []
    ctx.route("**/carpetas/**", lambda r: (
              None if "/carpetas/aspecto/sembrar" in r.request.url
              else escapados.append(r.request.url),
              r.fulfill(status=200, content_type="application/json", body='{"ok":true}')))

    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=8000)
    pag.wait_for_timeout(700)
    nuevas.clear()          # la propia `pag` cuenta como página nueva del contexto
    pag.evaluate("() => localStorage.clear()")   # que la pestaña nueva no herede nada

    revisar("arranca en la lista, sin pestañas", (tabs(pag), enLaLista(pag)), ([], True))

    # --- 1. El gesto: abre una pestaña del navegador y NO te mueve de la lista ---------
    clicMedio(pag, "#cuerpo .correo[data-sid='alfa-0']")
    pag.wait_for_timeout(800)
    revisar("⭐ el botón del medio abre UNA pestaña del navegador", len(nuevas), 1)
    if nuevas:
        n = nuevas[0]
        n.wait_for_load_state("domcontentloaded")
        revisar("la pestaña nueva apunta a esa charla",
                parse_qs(urlparse(n.url).query).get("c"), ["alfa-0"])
        n.wait_for_timeout(1500)
        revisar("y adentro entra a esa conversación", n.evaluate("() => activa"), "alfa-0")
        n.close()
    revisar("⭐ y a vos te deja donde estabas", enLaLista(pag), True)

    # --- 2. Ctrl+clic hace lo mismo (para el mouse sin rueda) -------------------------
    nuevas.clear()
    caja = pag.locator("#cuerpo .correo[data-sid='beta-1']").first.bounding_box()
    pag.keyboard.down("Control")
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
    pag.keyboard.up("Control")
    pag.wait_for_timeout(800)
    revisar("Ctrl+clic también abre una pestaña del navegador",
            [parse_qs(urlparse(x.url).query).get("c") for x in nuevas], [["beta-1"]])
    for x in nuevas:
        x.close()
    revisar("y tampoco te mueve", enLaLista(pag), True)

    # --- 3. Lo de siempre sigue igual --------------------------------------------------
    # ⚠ El clic común TIENE que seguir entrando ahí mismo: el gesto nuevo no puede
    # robarle el viejo.
    nuevas.clear()
    pag.click("#cuerpo .correo[data-sid='beta-0']")
    pag.wait_for_timeout(600)
    revisar("el clic común sigue entrando a la conversación",
            pag.evaluate("() => activa"), "beta-0")
    revisar("sin abrir pestañas del navegador", len(nuevas), 0)

    pag.evaluate("() => { activa = null; irProyecto(TODAS); }")
    pag.wait_for_timeout(500)

    # El ✚ de "Empezar una conversación" no se abre con el botón del medio: no es una
    # conversación que exista, y abrir una charla nueva a escondidas no sirve de nada.
    nuevas.clear()
    clicMedio(pag, "#cuerpo .correo[data-nueva]")
    pag.wait_for_timeout(500)
    revisar("el ✚ no abre nada con el botón del medio", len(nuevas), 0)
    revisar("y no te saca de la lista", enLaLista(pag), True)

    # Adentro de una carpeta, esa misma fila viene con el sid VACÍO.
    pag.evaluate("() => irProyecto('alfa')")
    pag.wait_for_timeout(500)
    clicMedio(pag, "#cuerpo .correo[data-sid='']")
    pag.wait_for_timeout(500)
    revisar("y adentro de una carpeta tampoco (sid vacío)", len(nuevas), 0)
    pag.evaluate("() => irProyecto(TODAS)")
    pag.wait_for_timeout(400)

    # --- 4. Lo mismo sobre una CARPETA de la columna izquierda (2026-10-10) -----------
    nuevas.clear()
    clicMedio(pag, "#carpetas .carpeta[data-proy='beta']")
    pag.wait_for_timeout(800)
    revisar("⭐ el botón del medio sobre una carpeta abre una pestaña del navegador",
            [parse_qs(urlparse(x.url).query).get("p") for x in nuevas], [["beta"]])
    if nuevas:
        n = nuevas[0]
        n.wait_for_load_state("domcontentloaded")
        n.wait_for_timeout(1500)
        revisar("y la pestaña nueva queda parada en esa carpeta",
                n.evaluate("() => [proy, activa]"), ["beta", None])
        revisar("mostrando las charlas de esa carpeta y no las de otra",
                n.evaluate("""() => [...document.querySelectorAll('#cuerpo .correo[data-sid]')]
                                     .map(e => e.dataset.sid).filter(Boolean).sort()"""),
                ["beta-0", "beta-1", "beta-2"])
        n.close()
    revisar("y a vos no te cambió de carpeta", pag.evaluate("() => proy === TODAS"), True)

    nuevas.clear()
    caja = pag.locator("#carpetas .carpeta[data-proy='alfa']").first.bounding_box()
    pag.keyboard.down("Control")
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
    pag.keyboard.up("Control")
    pag.wait_for_timeout(800)
    revisar("Ctrl+clic sobre una carpeta hace lo mismo",
            [parse_qs(urlparse(x.url).query).get("p") for x in nuevas], [["alfa"]])
    for x in nuevas:
        x.close()

    # "Todas" también (pedido de Martín, 2026-10-10): la bandeja entera en otra pestaña.
    # ⚠ Se la prueba con vos parado en OTRA carpeta y el sitio guardado: si la pestaña
    # nueva supiera que viene del panel, te copiaría la carpeta en vez de ir a "Todas".
    pag.evaluate("() => { irProyecto('alfa'); guardarSitio(); }")
    pag.wait_for_timeout(400)
    nuevas.clear()
    clicMedio(pag, "#carpetas .carpeta[data-proy='" + "✉ Todas las conversaciones" + "']")
    pag.wait_for_timeout(800)
    revisar("⭐ 'Todas' con el botón del medio abre la bandeja en otra pestaña",
            [urlparse(x.url).query for x in nuevas], [""])
    if nuevas:
        n = nuevas[0]
        n.wait_for_load_state("domcontentloaded")
        n.wait_for_timeout(1500)
        revisar("y la pestaña nueva muestra Todas, no tu carpeta",
                n.evaluate("() => [proy === TODAS, activa]"), [True, None])
        n.close()
    revisar("y a vos te deja en tu carpeta", pag.evaluate("() => proy"), "alfa")
    pag.evaluate("() => irProyecto(TODAS)")
    pag.wait_for_timeout(400)

    revisar("se le come el desplazamiento automático también en las carpetas",
            pag.evaluate("""() => {
              const el = document.querySelector('#carpetas .carpeta[data-proy="beta"]');
              const ev = new MouseEvent('mousedown', {button: 1, bubbles: true, cancelable: true});
              el.dispatchEvent(ev);
              return ev.defaultPrevented;
            }"""), True)

    # Entrar a una carpeta común deja la dirección con `?p=` (para F5 y favoritos), y
    # la flecha ← vuelve a la bandeja de todas.
    pag.click("#carpetas .carpeta[data-proy='alfa']")
    pag.wait_for_timeout(500)
    revisar("entrar a una carpeta escribe ?p= en la dirección",
            parse_qs(urlparse(pag.url).query).get("p"), ["alfa"])
    pag.go_back()
    pag.wait_for_timeout(500)
    revisar("y la flecha ← vuelve a 'Todas'", pag.evaluate("() => proy === TODAS"), True)

    # ⚠ Chrome le prende el desplazamiento automático al botón del medio: si no se frena
    # el mousedown, queda el iconito redondo dando vueltas por la pantalla.
    revisar("se le come el desplazamiento automático de Chrome",
            pag.evaluate("""() => {
              const el = document.querySelector('#cuerpo .correo[data-sid]');
              const ev = new MouseEvent('mousedown', {button: 1, bubbles: true, cancelable: true});
              el.dispatchEvent(ev);
              return ev.defaultPrevented;
            }"""), True)

    revisar("sin errores de JS", errores, [])
    revisar("no se le escribió nada al panel de verdad", escapados, [])
    nav.close()

print("")
print("todo bien" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
