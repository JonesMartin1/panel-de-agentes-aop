"""El selector de preguntas con opciones (AskUserQuestion) en el CELULAR.

Pedido de Martín (2026-08-18): el backend ya mandaba la pregunta adentro de
`/movil/chat` y en el teléfono no se dibujaba nada — quedaba diciendo "pensando"
para siempre y no había forma de contestarla desde ahí. Esta prueba mide lo mismo
que `ver_pregunta_sesion.py` mide en la compu, pero a 390 px y con el dedo.

⚠ `/movil/responder` se intercepta: la prueba no tiene una sesión de Claude de
verdad esperando del otro lado, y lo que importa medir es QUÉ manda la pantalla.

Correr con:  python -m pruebas.ver_pregunta_movil   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
SID = "prueba-preg-movil-0000"
CWD = "D:/IA/wpp-transcriptor"
fallas = []

# Una pregunta sola, como las que hace Claude Code cuando frena a consultar algo.
UNA = {"hora": 1000.0, "preguntas": [
    {"pregunta": "¿Reinicio el panel ahora?", "titulo": "Reinicio", "multi": False,
     "opciones": [{"etiqueta": "Sí, dale", "detalle": "Corta 3 segundos"},
                  {"etiqueta": "Mejor después", "detalle": "Sigo con lo otro"}]}]}

# Dos preguntas juntas: acá hace falta el botón Responder, no alcanza con tocar.
DOS = {"hora": 2000.0, "preguntas": [
    {"pregunta": "¿Qué toco primero?", "titulo": "Orden", "multi": False,
     "opciones": [{"etiqueta": "El panel", "detalle": ""},
                  {"etiqueta": "La voz", "detalle": ""}]},
    {"pregunta": "¿Corro las pruebas?", "titulo": "Pruebas", "multi": False,
     "opciones": [{"etiqueta": "Sí", "detalle": ""}, {"etiqueta": "No", "detalle": ""}]}]}

MODELOS = {"ok": True, "modelo": "sonnet", "defecto": "opus", "contexto": None,
           "esfuerzo": "high",
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"},
                       {"id": "sonnet", "nombre": "Sonnet"}],
           "esfuerzos": [{"id": "", "nombre": "Esfuerzo normal"},
                         {"id": "low", "nombre": "Esfuerzo bajo"},
                         {"id": "medium", "nombre": "Esfuerzo medio"},
                         {"id": "high", "nombre": "Esfuerzo alto"},
                         {"id": "xhigh", "nombre": "Esfuerzo muy alto"},
                         {"id": "max", "nombre": "Esfuerzo maximo"}]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    contestadas, esfuerzos = [], []
    pregunta = {"actual": UNA}

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True, device_scale_factor=3)
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"mensajes": [{"de": "vos", "texto": "arreglá el panel"}],
                             "pregunta": pregunta["actual"]})))

        def responder(ruta):
            contestadas.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')

        def modelo(ruta):
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps(MODELOS))

        def esfuerzo(ruta):
            esfuerzos.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True,
                                          "esfuerzo": esfuerzos[-1]["esfuerzo"]}))

        pag.route("**/movil/responder", responder)
        pag.route("**/movil/modelo*", modelo)
        pag.route("**/movil/esfuerzo", esfuerzo)
        pag.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json", body='{"ok":true}')
            if r.request.method == "POST" else r.continue_())

        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("""([cwd, sid]) => abrir(cwd, sid, 'De prueba')""", [CWD, SID])
        pag.wait_for_selector(".pregunta", timeout=15000)

        # --- Se ve la pregunta, no "pensando" -------------------------------------
        revisar("dibuja el selector y no la burbuja de pensando",
                pag.evaluate("() => !!document.querySelector('.pregunta') && "
                             "!document.querySelector('.pensando')"), True)
        revisar("muestra el título de la pregunta",
                pag.evaluate("() => document.querySelector('.pregunta .pTit').textContent"),
                "Reinicio")
        revisar("y la pregunta entera",
                pag.evaluate("() => document.querySelector('.pregunta .pPreg').textContent"),
                "¿Reinicio el panel ahora?")
        revisar("con las dos opciones como botones",
                pag.evaluate("() => [...document.querySelectorAll('.pregunta .pOp b')]"
                             ".map(b => b.textContent)"), ["Sí, dale", "Mejor después"])
        revisar("el detalle de cada una también se lee",
                pag.evaluate("() => document.querySelector('.pregunta .pOp span').textContent"),
                "Corta 3 segundos")
        revisar("hay campo para contestar con tus palabras",
                pag.evaluate("() => !!document.querySelector('.pregunta .pOtra input')"), True)
        # ⚠ Con UNA pregunta simple no va el botón Responder: tocar la opción alcanza.
        revisar("con una pregunta sola no hace falta Responder",
                pag.evaluate("() => !!document.querySelector('.pregunta .pMandar')"), False)

        # --- Que entre en la pantalla del teléfono --------------------------------
        revisar("el selector entra en el ancho del teléfono",
                pag.evaluate("""() => {
                  const c = document.querySelector('.pregunta').getBoundingClientRect();
                  return c.left >= -1 && c.right <= window.innerWidth + 1;
                }"""), True)
        # Los botones se tocan con el dedo: Apple pide 44 px de alto como mínimo.
        revisar("los botones son tocables con el dedo (44 px o más)",
                pag.evaluate("""() => [...document.querySelectorAll('.pregunta .pOp')]
                  .every(b => b.getBoundingClientRect().height >= 44)"""), True)
        # El campo de texto a 16 px o iOS hace zoom solo y descoloca la pantalla.
        revisar("el campo no dispara el zoom de iOS",
                pag.evaluate("""() => parseFloat(getComputedStyle(
                  document.querySelector('.pregunta .pOtra input')).fontSize) >= 16"""), True)

        # --- Tocar una opción la contesta -----------------------------------------
        pag.click(".pregunta .pOp")
        pag.wait_for_timeout(900)
        revisar("tocar la opción manda la elección con su sesión",
                contestadas[-1] if contestadas else None,
                {"cwd": CWD, "sid": SID,
                 "respuestas": {"¿Reinicio el panel ahora?": "Sí, dale"}})
        revisar("y el selector desaparece sin esperar al servidor",
                pag.evaluate("() => !!document.querySelector('.pregunta')"), False)

        # --- Contestar con tus palabras -------------------------------------------
        pregunta["actual"] = {"hora": 1500.0, "preguntas": UNA["preguntas"]}
        pag.wait_for_timeout(3500)
        pag.wait_for_selector(".pregunta", timeout=15000)
        pag.fill(".pregunta .pOtra input", "ninguna de las dos, esperá")
        pag.click(".pregunta .pManda")
        pag.wait_for_timeout(900)
        revisar("lo escrito a mano va tal cual",
                contestadas[-1]["respuestas"],
                {"¿Reinicio el panel ahora?": "ninguna de las dos, esperá"})

        # --- Dos preguntas juntas: hace falta Responder ---------------------------
        pregunta["actual"] = DOS
        pag.wait_for_timeout(3500)
        pag.wait_for_selector(".pregunta", timeout=15000)
        revisar("con dos preguntas aparece el botón Responder",
                pag.evaluate("() => !!document.querySelector('.pregunta .pMandar')"), True)
        # Sin contestar las dos, avisa cuál falta en vez de mandar algo a medias.
        pag.click('.pregunta .pOp[data-q="0"][data-o="0"]')
        pag.wait_for_timeout(300)
        antes = len(contestadas)
        pag.click(".pregunta .pMandar")
        pag.wait_for_timeout(700)
        revisar("a medio contestar no manda nada", len(contestadas), antes)
        revisar("y avisa cuál falta",
                pag.evaluate("() => document.querySelector('.pregunta .pNota').textContent"),
                "Falta contestar: Pruebas")
        pag.click('.pregunta .pOp[data-q="1"][data-o="1"]')
        pag.wait_for_timeout(300)
        pag.click(".pregunta .pMandar")
        pag.wait_for_timeout(900)
        revisar("con las dos contestadas manda las dos",
                contestadas[-1]["respuestas"],
                {"¿Qué toco primero?": "El panel", "¿Corro las pruebas?": "No"})

        # --- El esfuerzo, la perilla nueva ----------------------------------------
        pregunta["actual"] = None
        pag.wait_for_timeout(3500)
        revisar("el selector de esfuerzo está en la fila de ajustes",
                pag.evaluate("() => [...document.querySelectorAll('.ajusSes select')].length"), 2)
        revisar("muestra el que dijo el servidor",
                pag.evaluate("() => document.querySelectorAll('.ajusSes select')[1].value"),
                "high")
        revisar("y se pinta porque no es el de fábrica",
                pag.evaluate("() => document.querySelectorAll('.ajusSes select')[1]"
                             ".classList.contains('puesto')"), True)
        pag.select_option(".ajusSes select >> nth=1", "max")
        pag.wait_for_timeout(800)
        revisar("elegirlo lo manda al servidor con su sesión",
                esfuerzos[-1] if esfuerzos else None, {"sid": SID, "esfuerzo": "max"})

        pag.screenshot(path="resultados/pregunta_movil.png", full_page=True)
        revisar("sin errores de JS", errores, [])
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
