"""El modelo y el botón de compactar en la app del celular.

Pedido de Martín (2026-08-18): lo mismo que quedó en `/sesiones` de la compu, pero
en el teléfono. ⚠ Van ARRIBA, abajo del título de la charla, y no en la caja de
escribir: en 390 px de ancho un selector más deja el campo de texto en nada.

⚠⚠ Los dos endpoints se interceptan: `/movil/compactar` porque compactar de verdad
son dos turnos de Claude contra una sesión real (cuesta tokens y la muda a otra
sesión), y `/movil/modelo` para no depender de lo que Martín tenga elegido hoy —
la prueba fija lo que el servidor contesta y mide la pantalla contra eso.

Correr con:  python -m pruebas.ver_modelo_movil   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
SID = "prueba-movil-0000"
SID_NUEVO = "prueba-movil-compactada-1111"
CWD = "D:/IA/wpp-transcriptor"
fallas = []

MODELOS = {"ok": True, "modelo": "haiku", "defecto": "opus",
           "contexto": {"tokens": 480000, "nivel": "mucho", "aviso": "conviene compactar"},
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"},
                       {"id": "opus[1m]", "nombre": "Opus (1 millon)"},
                       {"id": "fable", "nombre": "Fable"},
                       {"id": "sonnet", "nombre": "Sonnet"},
                       {"id": "haiku", "nombre": "Haiku"}]}
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola"},
                       {"de": "claude", "texto": "hola, ¿en qué andamos?"}]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    puestos, compactados = [], []

    with sync_playwright() as p:
        nav = p.chromium.launch()
        # El teléfono de Martín: iPhone 15/16, con dedo.
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True, device_scale_factor=3)
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        # Compactar pregunta antes de hacer nada: en la prueba se contesta que sí.
        pag.on("dialog", lambda d: d.accept())

        def modelo(ruta):
            if ruta.request.method == "POST":
                puestos.append(ruta.request.post_data_json)
                ruta.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "modelo": puestos[-1]["modelo"]}))
            else:
                ruta.fulfill(status=200, content_type="application/json",
                             body=json.dumps(MODELOS))

        def compactar(ruta):
            compactados.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True, "sid": SID_NUEVO, "resumen": "lo de antes"}))

        pag.route("**/movil/modelo*", modelo)
        pag.route("**/movil/compactar", compactar)
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        # ⚠ El POST de pestañas se ataja: persiste en el SERVIDOR y le aparecería una
        # pestaña fantasma en el teléfono de verdad.
        pag.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json", body='{"ok":true}')
            if r.request.method == "POST" else r.continue_())

        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("""([cwd, sid]) => abrir(cwd, sid, 'De prueba')""", [CWD, SID])
        pag.wait_for_selector(".ajusSes", timeout=15000)

        # --- Lo que se ve ---------------------------------------------------------
        revisar("la fila de ajustes está abajo del título",
                pag.evaluate("() => document.querySelector('#titulo')"
                             ".nextElementSibling.className"), "ajusSes")
        revisar("trae los cinco modelos",
                pag.evaluate("() => [...document.querySelectorAll('.ajusSes option')]"
                             ".map(o => o.value)"),
                ["opus", "opus[1m]", "fable", "sonnet", "haiku"])
        revisar("muestra el que dijo el servidor",
                pag.evaluate("() => document.querySelector('.ajusSes select').value"), "haiku")
        revisar("y se pinta porque no es el de fábrica",
                pag.evaluate("() => document.querySelector('.ajusSes select').classList"
                             ".contains('puesto')"), True)
        # El contexto en criollo: 480.000 se lee "480 k". Es el aviso de cuándo compactar.
        revisar("el chip dice cuánto contexto arrastra",
                pag.evaluate("() => document.querySelector('.ctxSes').textContent.trim()"),
                "480 k")
        revisar("y el botón se enciende porque ya pesa",
                pag.evaluate("() => document.querySelector('.ajusSes button').classList"
                             ".contains('conviene')"), True)
        # ⚠ Que ENTRE en la pantalla del teléfono: si se sale del ancho, el botón queda
        # fuera del alcance del dedo y la fila no sirve de nada.
        revisar("todo entra en el ancho del teléfono",
                pag.evaluate("""() => {
                  const c = document.querySelector('.ajusSes').getBoundingClientRect();
                  return c.right <= window.innerWidth + 1;
                }"""), True)

        # --- Elegir un modelo -----------------------------------------------------
        pag.select_option(".ajusSes select", "fable")
        pag.wait_for_timeout(800)
        revisar("elegir uno lo manda al servidor con su sesión",
                puestos[-1] if puestos else None, {"sid": SID, "modelo": "fable"})

        # --- Compactar ------------------------------------------------------------
        pag.click(".ajusSes button")
        pag.wait_for_timeout(1800)
        revisar("compactar manda el pedido de esa sesión",
                compactados[-1]["sid"] if compactados else None, SID)
        revisar("la pestaña se muda a la sesión nueva",
                pag.evaluate("() => pestanas.find(p => p.sid === activa) ? activa : null"),
                SID_NUEVO)
        revisar("y no quedó la vieja abierta",
                pag.evaluate("() => pestanas.some(p => p.sid === '%s')" % SID), False)

        revisar("sin errores de JS", errores, [])
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
