"""Botón del medio del mouse sobre una conversación: se abre arriba sin sacarte de la lista.

Pedido de Martín (2026-08-19): *"me gustaría poder hacer click con el botón del medio del
mouse sobre las sesiones y se me abran en una nueva pestaña las conversaciones"*. Es el
hábito del navegador: vas marcando las tres o cuatro que te interesan de un saque y
después las recorrés, en vez de entrar y volver por cada una.

Lo que más importa acá es lo que NO pasa: que el botón del medio no te cambie de pantalla.
Por eso la mitad de los chequeos miran que después del clic sigas parado en la lista.

⚠ `/movil/sesiones` y `/movil/chat` se interceptan: la lista es inventada, así que la
prueba no depende de qué conversaciones tenga hoy y no le toca ni una a Martín. El
navegador de Playwright tiene su propio perfil, así que el `localStorage.clear()` de acá
no le borra las pestañas abiertas en su Chrome.

Correr con:  python -m pruebas.ver_boton_medio   (con el panel prendido)
"""
import json
import sys

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
    """Las conversaciones abiertas arriba, en orden.

    ⚠ Se lee del estado y NO del DOM: la barra agrupa por proyecto y el grupo plegado no
    dibuja sus pestañas, así que contarlas en pantalla daba de menos sin que faltara
    ninguna. Que la pestaña se VEA se chequea aparte, y ahí sí mirando la pantalla.
    """
    return pag.evaluate("() => abiertas.map(t => t.sid)")


def enLaLista(pag):
    """¿Seguís mirando la bandeja? (y no adentro de una conversación)"""
    return pag.evaluate("() => activa === null && !!document.querySelector('#cuerpo .correo')")


def clicMedio(pag, selector):
    caja = pag.locator(selector).first.bounding_box()
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2,
                    button="middle")


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    pag = nav.new_page(viewport={"width": 1400, "height": 900})
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))

    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"mensajes":[]}'))
    # Nada de escrituras: si algo sale para el panel de verdad, muere acá y se anota.
    escapados = []
    pag.route("**/carpetas/**", lambda r: (escapados.append(r.request.url),
              r.fulfill(status=200, content_type="application/json", body='{"ok":true}')))

    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=8000)
    pag.wait_for_timeout(700)

    revisar("arranca en la lista, sin pestañas", (tabs(pag), enLaLista(pag)), ([], True))

    # --- 1. El gesto: abre arriba y NO te mueve de la lista ---------------------------
    clicMedio(pag, "#cuerpo .correo[data-sid='alfa-0']")
    pag.wait_for_timeout(400)
    revisar("el botón del medio abre la pestaña", tabs(pag), ["alfa-0"])
    revisar("⭐ y te deja donde estabas", enLaLista(pag), True)
    revisar("la pestaña parpadea para que la veas",
            pag.evaluate("""() => { const t = document.querySelector('#tabs .tab[data-sid]');
                                    return !!t && t.className.includes('recien'); }"""), True)
    pag.wait_for_timeout(1800)
    revisar("y el parpadeo se apaga solo",
            pag.evaluate("""() => !!document.querySelector('#tabs .tab.recien')"""), False)
    revisar("después del parpadeo sigue abierta", tabs(pag), ["alfa-0"])

    # --- 2. Varias de un saque, que es para lo que sirve ------------------------------
    clicMedio(pag, "#cuerpo .correo[data-sid='alfa-1']")
    pag.wait_for_timeout(300)
    clicMedio(pag, "#cuerpo .correo[data-sid='beta-0']")
    pag.wait_for_timeout(400)
    revisar("tres marcadas sin moverse de la bandeja", sorted(tabs(pag)),
            ["alfa-0", "alfa-1", "beta-0"])
    revisar("y seguís en la lista", enLaLista(pag), True)
    revisar("la de otro proyecto se ve igual (su grupo queda desplegado)",
            pag.evaluate("""() => { const t = document.querySelector('#tabs .tab[data-sid="beta-0"]');
                                    return !!t && t.offsetParent !== null; }"""), True)

    # La misma dos veces no la duplica.
    clicMedio(pag, "#cuerpo .correo[data-sid='alfa-0']")
    pag.wait_for_timeout(400)
    revisar("la misma dos veces no se duplica", len(tabs(pag)), 3)

    # --- 3. Ctrl+clic hace lo mismo (para el mouse sin rueda) -------------------------
    caja = pag.locator("#cuerpo .correo[data-sid='beta-1']").first.bounding_box()
    pag.keyboard.down("Control")
    pag.mouse.click(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
    pag.keyboard.up("Control")
    pag.wait_for_timeout(400)
    revisar("Ctrl+clic también abre atrás", sorted(tabs(pag)),
            ["alfa-0", "alfa-1", "beta-0", "beta-1"])
    revisar("y tampoco te mueve", enLaLista(pag), True)

    # --- 4. Lo de siempre sigue igual --------------------------------------------------
    # ⚠ El clic común TIENE que seguir entrando: el gesto nuevo no puede robarle el viejo.
    pag.click("#cuerpo .correo[data-sid='beta-0']")
    pag.wait_for_timeout(600)
    revisar("el clic común sigue entrando a la conversación",
            pag.evaluate("() => activa"), "beta-0")
    revisar("y ya no estás en la lista", enLaLista(pag), False)

    # Volver a la bandeja de TODAS para el resto (adentro de una carpeta, la fila de
    # arrancar viene con el sid vacío en vez de `data-nueva`: las dos se chequean).
    pag.evaluate("() => { activa = null; irProyecto(TODAS); }")
    pag.wait_for_timeout(500)

    # El ✚ de "Empezar una conversación" no se abre con el botón del medio: no es una
    # conversación que exista, y abrir una charla nueva a escondidas no sirve de nada.
    antes = len(tabs(pag))
    clicMedio(pag, "#cuerpo .correo[data-nueva]")
    pag.wait_for_timeout(400)
    revisar("el ✚ no abre nada con el botón del medio", len(tabs(pag)), antes)
    revisar("y no te saca de la lista", enLaLista(pag), True)

    # Adentro de una carpeta, esa misma fila viene con el sid VACÍO: sin la guarda, el
    # botón del medio le abría atrás una charla nueva fantasma que nadie pidió.
    pag.evaluate("() => irProyecto('alfa')")
    pag.wait_for_timeout(500)
    antes = len(tabs(pag))
    clicMedio(pag, "#cuerpo .correo[data-sid='']")
    pag.wait_for_timeout(400)
    revisar("y adentro de una carpeta tampoco (sid vacío)", len(tabs(pag)), antes)
    pag.evaluate("() => irProyecto(TODAS)")
    pag.wait_for_timeout(400)

    # ⚠ Chrome le prende el desplazamiento automático al botón del medio: si no se frena
    # el mousedown, queda el iconito redondo dando vueltas por la pantalla.
    revisar("se le come el desplazamiento automático de Chrome",
            pag.evaluate("""() => {
              const el = document.querySelector('#cuerpo .correo[data-sid]');
              const ev = new MouseEvent('mousedown', {button: 1, bubbles: true, cancelable: true});
              el.dispatchEvent(ev);
              return ev.defaultPrevented;
            }"""), True)

    # --- 5. La pestaña abierta atrás se puede usar ------------------------------------
    # ⚠ Primero hay que desplegar la pastilla del proyecto: la barra agrupa, y el grupo
    # que quedó plegado no dibuja sus pestañas. Es el mismo camino que hace él.
    if not pag.query_selector("#tabs .tab[data-sid='alfa-1']"):
        pag.click("#tabs .grupo[data-grupo='alfa']")
        pag.wait_for_timeout(400)
    revisar("la pestaña abierta atrás se puede ir a buscar",
            pag.evaluate("""() => !!document.querySelector('#tabs .tab[data-sid="alfa-1"]')"""), True)
    pag.click("#tabs .tab[data-sid='alfa-1']")
    pag.wait_for_timeout(600)
    revisar("tocando la pestaña se entra a esa charla", pag.evaluate("() => activa"), "alfa-1")

    revisar("sin errores de JS", errores, [])
    revisar("no se le escribió nada al panel de verdad", escapados, [])
    nav.close()

print("")
print("todo bien" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
