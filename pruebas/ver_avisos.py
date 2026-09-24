"""Prueba de pantalla de la pestaña Avisos (los Recordatorios del iPhone).

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_avisos

⚠ NO habla con el panel de verdad: la propia pagina y sus endpoints se interceptan con
`page.route`, receta de `ver_estudio.py`. Dos motivos: la ruta `/avisos` no existe hasta
que se reinicie el panel, y una prueba nunca tiene que meterle recordatorios inventados
a la cola real de Martin. El lado del servidor lo cubre `pruebas/probar_avisos.py`.

Deja capturas al lado: en esta pantalla los defectos se ven mirando, no leyendo.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # emojis en consola cp1252

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "app" / "estaticos" / "avisos.html"
MENU = RAIZ / "app" / "estaticos" / "menu.js"
FALLAS = []
TOTAL = 0

# El estado que devuelve el servidor inventado. Se cambia entre etapa y etapa.
ESTADO = {}


def chequear(que, ok, detalle=""):
    global TOTAL
    TOTAL += 1
    print(("  OK   " if ok else "  FALLA ") + que + (" -> " + detalle if detalle else ""))
    if not ok:
        FALLAS.append(que)


def con_datos():
    return {
        "ok": True, "ultima_sync": "2026-08-17T14:00:00", "hace_min": 4, "corridas": 12,
        "dormido": False, "nunca": False,
        "espejo": [
            {"nombre": "Llamar al contador", "vence": "2026-08-17T18:00:00",
             "vence_iso": "2026-08-17T18:00:00", "lista": "Trabajo"},
            {"nombre": "Comprar pan", "vence": None, "vence_iso": None, "lista": "Personal"},
            {"nombre": "Renovar el seguro", "vence": "2027-01-10T09:00:00",
             "vence_iso": "2027-01-10T09:00:00", "lista": "Personal"},
        ],
        "salientes": [
            {"id": "abc123", "nombre": "Revisar el backup del VPS",
             "creado": "2026-08-17T13:55:00", "entregas": 0, "ultima_entrega": None},
        ],
    }


def main():
    html = PAGINA.read_text(encoding="utf-8")
    menu = MENU.read_text(encoding="utf-8")
    pedidos = []

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1180, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def sirve_pagina(r):
            r.fulfill(status=200, content_type="text/html", body=html)

        def sirve_menu(r):
            r.fulfill(status=200, content_type="application/javascript", body=menu)

        def sirve_lista(r):
            r.fulfill(status=200, content_type="application/json", body=json.dumps(ESTADO))

        def anota(r):
            pedidos.append((r.request.url, r.request.post_data))
            r.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True}))

        pag.route("**/avisos", sirve_pagina)
        pag.route("**/estaticos/menu.js", sirve_menu)
        pag.route("**/avisos/lista", sirve_lista)
        pag.route("**/avisos/nuevo", anota)
        pag.route("**/avisos/quitar", anota)

        # ---------------------------------------------------------------- 1
        print("\n1. todavia no se conecto ningun telefono")
        ESTADO.clear()
        ESTADO.update({"ok": True, "espejo": [], "salientes": [], "ultima_sync": None,
                       "hace_min": None, "corridas": 0, "dormido": False, "nunca": True,
                       "url_tailscale": "https://mi-pc.tailnet-ejemplo.ts.net"})
        pag.goto("http://127.0.0.1:8750/avisos", wait_until="domcontentloaded")
        pag.wait_for_selector("#guia", timeout=8000)
        pag.wait_for_timeout(400)
        chequear("el instructivo se abre solo",
                 pag.locator("#guia").get_attribute("open") is not None)
        guia = pag.locator("#guia").inner_text()
        url = pag.locator("#urlSync").inner_text()
        # ⚠ El error que no avisa: abierta desde la compu, `location.origin` es
        # 127.0.0.1, que en el telefono es el telefono. El Atajo quedaria armado y
        # mudo. La direccion buena la dice el servidor.
        chequear("la direccion es la de Tailscale, no la de esta pantalla",
                 url == "https://mi-pc.tailnet-ejemplo.ts.net/avisos/sync", url)
        chequear("y explica por que no es la que estas viendo en la barra",
                 "red privada" in pag.locator("#urlNota").inner_text(),
                 pag.locator("#urlNota").inner_text()[:60])
        chequear("estan los siete pasos", guia.count("\n") > 10 and "POST" in guia)
        # ⚠ El paso del "Si" es el que uno saca por parecer de mas: sin el, cada corrida
        # con la cola vacia crea un recordatorio en blanco en el telefono.
        chequear("y avisa por que el paso del 'Si' no se saca",
                 "vacío" in guia and "Si" in guia)
        chequear("el chip dice que nunca se conecto",
                 "no se conectó" in pag.locator("#estadoTxt").inner_text(),
                 pag.locator("#estadoTxt").inner_text())
        # ⚠ La regla de color de estas pantallas: el rojo es SOLO para lo que esta mal.
        clase = pag.locator("#estado").get_attribute("class") or ""
        chequear("y no se pinta como si fuera un error", clase.strip() == "", repr(clase))
        pag.screenshot(path=str(Path(__file__).with_name("avisos_sin_telefono.png")))

        # ---------------------------------------------------------------- 2
        print("\n2. con recordatorios de verdad")
        ESTADO.clear()
        ESTADO.update(con_datos())
        pag.goto("http://127.0.0.1:8750/avisos", wait_until="domcontentloaded")
        pag.wait_for_selector(".fila", timeout=8000)
        filas = pag.locator(".fila:not(.saliente)")
        chequear("estan los tres del telefono", filas.count() == 3, str(filas.count()))
        primera = filas.nth(0).inner_text()
        chequear("lo que vence primero va arriba", "contador" in primera, primera)
        chequear("se ve en que lista esta", "Trabajo" in primera, primera)
        chequear("el chip dice hace cuanto se sincronizo",
                 "hace 4 min" in pag.locator("#estadoTxt").inner_text(),
                 pag.locator("#estadoTxt").inner_text())
        chequear("y que esta al dia",
                 "vivo" in (pag.locator("#estado").get_attribute("class") or ""))
        chequear("el instructivo queda plegado (a mano, sin ocupar la pantalla)",
                 pag.locator("#guia").get_attribute("open") is None)
        chequear("pero sigue estando", pag.locator("#guia summary").count() == 1)

        print("\n3. lo que sale del panel se distingue de lo que ya esta en el telefono")
        sal = pag.locator(".fila.saliente")
        chequear("aparece en su propia seccion", sal.count() == 1, str(sal.count()))
        chequear("dice que va en camino", "en camino" in sal.inner_text(), sal.inner_text())
        borde = pag.evaluate(
            "getComputedStyle(document.querySelector('.fila.saliente')).borderStyle")
        chequear("se ve distinto (borde punteado)", borde == "dashed", borde)

        print("\n4. lo que vence pronto se marca, y lo lejano no")
        pronto = pag.locator(".cuando.pronto")
        chequear("solo uno esta marcado como que vence pronto", pronto.count() == 1,
                 str(pronto.count()))
        color = pag.evaluate("getComputedStyle(document.querySelector('.cuando.pronto')).color")
        # Ambar, no rojo: "vence pronto" es un estado normal, no algo roto.
        chequear("y en ambar, no en rojo", color == "rgb(224, 196, 138)", color)

        print("\n5. anotar algo desde el panel")
        pag.fill("#texto", "Pagar el hosting")
        pag.click("#nuevo button")
        pag.wait_for_timeout(400)
        nuevos = [d for u, d in pedidos if "nuevo" in u]
        chequear("se manda al servidor", len(nuevos) == 1, str(len(nuevos)))
        chequear("con el texto que escribiste",
                 nuevos and json.loads(nuevos[0]).get("nombre") == "Pagar el hosting",
                 nuevos[0] if nuevos else "")
        chequear("y la caja queda vacia para el siguiente",
                 pag.input_value("#texto") == "", repr(pag.input_value("#texto")))

        print("\n6. sacar de la cola algo que todavia no se fue")
        pag.click(".fila.saliente .x")
        pag.wait_for_timeout(400)
        quitados = [d for u, d in pedidos if "quitar" in u]
        chequear("se manda el pedido de quitar", len(quitados) == 1, str(len(quitados)))
        chequear("con el id de ese y no de otro",
                 quitados and json.loads(quitados[0]).get("id") == "abc123",
                 quitados[0] if quitados else "")

        print("\n7. cuando el telefono hace rato que no aparece")
        ESTADO.clear()
        ESTADO.update(con_datos())
        ESTADO.update({"hace_min": 900, "dormido": True})
        pag.evaluate("firma = ''")
        pag.evaluate("cargar()")
        pag.wait_for_timeout(400)
        txt = pag.locator("#estadoTxt").inner_text()
        chequear("lo avisa en criollo", "no aparece" in txt and "horas" in txt, txt)
        clase = pag.locator("#estado").get_attribute("class") or ""
        chequear("en ambar y NO en rojo (no es un error)", "dormido" in clase, clase)
        fondo = pag.evaluate("getComputedStyle(document.getElementById('estado')).borderColor")
        chequear("el borde no es rojo", not fondo.startswith("rgb(2") or "61, 51, 32" in fondo,
                 fondo)
        chequear("explica que lo que anotes se va a levantar igual",
                 "Atajo" in pag.locator("#estadoDer").inner_text(),
                 pag.locator("#estadoDer").inner_text())

        print("\n8. el menu de pantallas")
        menu_txt = pag.locator("#menuPantallas").inner_text()
        for pantalla in ("Panel", "Sesiones", "Pizarra", "Estudio", "Avisos"):
            chequear("esta " + pantalla, pantalla in menu_txt)
        aca = pag.locator("#menuPantallas a.aca")
        chequear("y Avisos figura como la pantalla actual",
                 aca.count() == 1 and "Avisos" in aca.inner_text(),
                 aca.inner_text() if aca.count() else "ninguna")

        print("\n9. en el telefono")
        # 390x844 = el iPhone que usa Martin. Va a abrir esta pantalla desde el celular
        # tanto o mas que desde la compu.
        pag.set_viewport_size({"width": 390, "height": 844})
        pag.wait_for_timeout(300)
        ancho = pag.evaluate("document.documentElement.scrollWidth")
        chequear("no queda scroll horizontal", ancho <= 390, str(ancho))
        caja = pag.locator("#texto").bounding_box()
        chequear("la caja de escribir sigue siendo usable",
                 caja and caja["width"] > 180, str(caja["width"]) if caja else "no esta")
        pag.screenshot(path=str(Path(__file__).with_name("avisos_movil.png")), full_page=True)

        pag.set_viewport_size({"width": 1180, "height": 900})
        pag.wait_for_timeout(200)
        pag.screenshot(path=str(Path(__file__).with_name("avisos_pantalla.png")))

        chequear("ningun error de JavaScript", not errores, "; ".join(errores[:2]))
        nav.close()

    print("\n%d chequeos, %d fallas" % (TOTAL, len(FALLAS)))
    if FALLAS:
        for f in FALLAS:
            print("  -", f)
        return 1
    print("Capturas: pruebas/avisos_pantalla.png, avisos_movil.png, avisos_sin_telefono.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
