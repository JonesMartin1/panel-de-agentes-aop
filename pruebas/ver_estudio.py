"""Prueba de pantalla del Estudio: la bandeja de audios y la fila de union.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_estudio

⚠ NO habla con el panel de verdad: la pagina y sus cuatro endpoints se interceptan con
`page.route` y los audios son inventados. Dos motivos: la ruta `/estudio` no existe
hasta reiniciar el panel, y una prueba nunca tiene que ensuciar la carpeta real de
audios de Martin. El lado del servidor (ffmpeg, fichas, borrado) ya lo cubre
`pruebas/probar_unir_audios.py`, que si usa archivos de verdad.

Deja `pruebas/estudio_pantalla.png` para mirar como quedo — en esta pantalla los
defectos se ven en la captura, no leyendo el codigo.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# ⚠ Sin esto, un emoji del texto de la pantalla (el 📱 del canal) revienta el print
# con cp1252 y la prueba se corta a la mitad. Es la misma piedra que dejo muda a Laura
# por horas el 2026-08-14 — ver "Lecciones" en PIZARRA.md.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "app" / "estaticos" / "estudio.html"
CREATE_NO_WINDOW = 0x08000000
FALLAS = []

FRASES = [
    {"inicio": 0.0, "fin": 1.0, "texto": "hola, como andas"},
    {"inicio": 1.0, "fin": 2.0, "texto": "te mando el presupuesto de la obra"},
    {"inicio": 2.0, "fin": 3.0, "texto": "cualquier cosa avisame, chau"},
]

AUDIOS = [
    {"archivo": "a1.wav", "origen": "whatsapp", "de": "5493794000000", "cuando": int(time.time()) - 120,
     "dur": 3.0, "texto": "che, fijate el presupuesto de la obra que te mande ayer"},
    {"archivo": "a2.wav", "origen": "telegram", "de": "Martin Jones", "cuando": int(time.time()) - 7200,
     "dur": 2.0, "texto": "acordate de llamar al contador por el tema de las facturas"},
    {"archivo": "a3.wav", "origen": "disco", "de": "grabacion-vieja", "cuando": int(time.time()) - 400000,
     "dur": 1.0, "texto": "prueba de sonido, uno dos tres"},
]


def chequear(que, ok, detalle=""):
    print(("  OK   " if ok else "  FALLA ") + que + (" -> " + detalle if detalle else ""))
    if not ok:
        FALLAS.append(que)


def wav_de_prueba():
    """Un wav real, para que el navegador pueda dibujar la onda de verdad."""
    f = Path(__file__).with_name("_tmp_onda.wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=3", str(f)],
                   check=True, creationflags=CREATE_NO_WINDOW)
    datos = f.read_bytes()
    f.unlink(missing_ok=True)
    return datos


def main():
    onda = wav_de_prueba()
    html = PAGINA.read_text(encoding="utf-8")

    with sync_playwright() as p:
        # Usa el Chrome de la máquina: Playwright puede actualizarse sin bajar de nuevo
        # su Chromium empaquetado, y eso no tiene que dejar al Estudio sin prueba visual.
        nav = p.chromium.launch(channel="chrome", headless=True)
        pag = nav.new_page(viewport={"width": 1180, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        pag.route("**/estudio", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        pag.route("**/estudio/entrantes", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "audios": AUDIOS})))
        pag.route("**/estudio/onda/**", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "picos": [0.2, 0.9, 0.5] * 113 + [0.4]})))
        # Las bandejas: dos creadas, y los audios de prueba arrancan sin clasificar.
        pag.route("**/estudio/proyectos", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "proyectos": ["Tienda", "Curso"],
                             "cuentas": {"": 3}, "total": 3})))
        movidos = []

        def cazar_mover(route, request):
            movidos.append(json.loads(request.post_data or "{}"))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True}))

        pag.route("**/estudio/mover", cazar_mover)
        subidas = []

        def cazar_subir(route, request):
            subidas.append(request.post_data or "")
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "audios": AUDIOS,
                                           "guardados": [], "errores": []}))

        pag.route("**/estudio/subir", cazar_subir)
        pag.route("**/estudio/perfiles", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "perfiles": ["generico", "reuniones", "ventas"],
                             "defecto": "generico"})))
        pag.route("**/estudio/analisis/**", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "texto": "RESUMEN: pide un presupuesto.\nTAREAS: mandar precios."})))
        analisis_pedidos = []

        def cazar_analizar(route, request):
            analisis_pedidos.append(json.loads(request.post_data or "{}"))
            # `dicho` viaja en la respuesta real, para poder copiar la transcripcion
            # sin pedirla de nuevo: el simulacro tiene que devolverlo igual.
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "letras": 1234,
                                           "texto": "RESUMEN DEL ARMADO: tres puntos.",
                                           "dicho": "hola, como andas te mando el presupuesto"}))

        pag.route("**/estudio/analizar", cazar_analizar)
        pag.route("**/estudio/texto", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "letras": 60,
                             "texto": "hola, como andas te mando el presupuesto de la obra"})))
        pag.route("**/estudio/lista", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "archivos": [a["archivo"] for a in AUDIOS]})))
        pag.route("**/estudio/audio/**", lambda r: r.fulfill(
            status=200, content_type="audio/wav", body=onda))
        # La onda la mide el SERVIDOR con ffmpeg: el navegador ya no decodifica el audio
        # entero (con media hora de audio se plantaba y dejaba una raya).
        pag.route("**/estudio/onda/**", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "picos": ([0.2, 0.9, 0.5] * 113) + [0.4]})))

        # ⚠ networkidle no llega nunca en estas pantallas (hay polling): domcontentloaded + espera.
        pag.goto("http://127.0.0.1:8750/estudio", wait_until="domcontentloaded")
        pag.wait_for_selector(".rec", timeout=8000)
        pag.wait_for_timeout(700)

        print("\n1. la bandeja muestra lo que llego")
        filas = pag.locator(".rec")
        chequear("estan los tres audios", filas.count() == 3, str(filas.count()))
        primera = filas.nth(0).inner_text()
        chequear("se ve de quien vino", "5493794000000" in primera, primera.split("\n")[0])
        chequear("se ve hace cuanto", "hace 2 min" in primera or "recién" in primera)
        chequear("se ve lo que DICE el audio", "presupuesto de la obra" in primera)
        chequear("el canal se distingue", "📱" in filas.nth(0).inner_text() or
                 "📱" in filas.nth(0).inner_html())

        # Soltar sobre el recuadro también burbujea al documento. Tiene que salir UNA
        # sola petición: antes un video largo se copiaba dos veces por este camino.
        pag.evaluate("""() => {
          const datos = new DataTransfer();
          datos.items.add(new File(['una copia'], 'una.wav', {type: 'audio/wav'}));
          document.querySelector('#soltar').dispatchEvent(new DragEvent('drop', {
            bubbles: true, cancelable: true, dataTransfer: datos
          }));
        }""")
        pag.wait_for_timeout(300)
        chequear("soltar un archivo lo sube una sola vez", len(subidas) == 1, str(len(subidas)))

        print("\n1b. las bandejas (proyectos)")
        chips = pag.locator(".chipb")
        chequear("estan Todos, Sin clasificar, las dos bandejas y el ＋",
                 chips.count() == 5, str(chips.count()))
        chequear("Todos arranca elegido", "sel" in (pag.locator(".chipb.sel").first.get_attribute("class") or "")
                 and "Todos" in pag.locator(".chipb.sel").first.inner_text(),
                 pag.locator(".chipb.sel").first.inner_text())
        chequear("cada chip dice cuantos audios tiene",
                 "3" in pag.locator(".chipb").first.inner_text(),
                 pag.locator(".chipb").first.inner_text())
        # Mandar el primer audio a una bandeja
        pag.locator("select.proy").first.select_option("Tienda")
        pag.wait_for_timeout(400)
        chequear("elegir bandeja avisa al servidor",
                 bool(movidos) and movidos[0].get("proyecto") == "Tienda", str(movidos[:1]))
        chequear("y no lo suma a la fila sin querer", pag.evaluate("pistas.length") == 0,
                 str(pag.evaluate("pistas.length")))
        # Filtrar por bandeja
        pag.locator('.chipb[data-band="Tienda"]').click()
        pag.wait_for_timeout(400)
        chequear("al entrar a la bandeja queda solo ese audio",
                 pag.locator(".rec").count() == 1, str(pag.locator(".rec").count()))
        pag.locator('.chipb[data-band=""]').click()
        pag.wait_for_timeout(400)
        chequear("en 'Sin clasificar' quedan los otros dos",
                 pag.locator(".rec").count() == 2, str(pag.locator(".rec").count()))
        pag.locator('.chipb[data-band="*"]').click()
        pag.wait_for_timeout(400)
        chequear("y en Todos estan los tres", pag.locator(".rec").count() == 3,
                 str(pag.locator(".rec").count()))

        print("\n2. buscar por lo que dice")
        pag.fill("#buscar", "contador")
        pag.wait_for_timeout(200)
        chequear("queda solo el que lo dice", pag.locator(".rec").count() == 1,
                 str(pag.locator(".rec").count()))
        chequear("y es el correcto", "contador" in pag.locator(".rec").nth(0).inner_text())
        pag.fill("#buscar", "no dice esto ninguno")
        pag.wait_for_timeout(200)
        chequear("avisa cuando no hay ninguno", "Ninguno" in pag.locator("#bandeja").inner_text())
        pag.fill("#buscar", "")
        pag.wait_for_timeout(200)
        chequear("al vaciar vuelven todos", pag.locator(".rec").count() == 3)

        print("\n3. sumar a la fila")
        pag.locator(".rec").nth(0).click()
        pag.wait_for_timeout(400)
        chequear("aparece una pista en la fila", pag.locator(".pista").count() == 1)
        chequear("la bandeja lo marca", "en la fila" in pag.locator(".rec").nth(0).inner_text())
        pag.locator(".rec").nth(1).click()
        pag.wait_for_timeout(400)
        chequear("se suma el segundo", pag.locator(".pista").count() == 2)

        print("\n4. el mismo audio dos veces no se pisa")
        pag.locator(".rec").nth(0).click()
        pag.wait_for_timeout(600)
        chequear("hay tres pistas", pag.locator(".pista").count() == 3)
        chequear("la bandeja dice que esta dos veces",
                 "×2" in pag.locator(".rec").nth(0).inner_text(),
                 pag.locator(".rec").nth(0).inner_text().split("\n")[0])
        anchos = pag.eval_on_selector_all(
            ".pista canvas", "cs => cs.map(c => c.width)")
        chequear("las tres ondas se dibujaron", len(anchos) == 3 and all(a > 0 for a in anchos),
                 str(anchos))
        chequear("la onda vino medida del servidor, sin decodificar acá",
                 pag.evaluate("pistas[0].picos.length") == 340,
                 str(pag.evaluate("pistas[0].picos.length")))

        print("\n5. la cuenta de lo que va a salir")
        total = pag.locator("#total").inner_text()
        # 3 + 2 + 3 = 8 s de audio + 2 silencios de 0,4 = 8,8
        chequear("suma los audios y los silencios", "8,8 s" in total, total)
        chequear("el boton de unir se habilita", not pag.locator("#btnUnir").is_disabled())

        print("\n6. sacar de la fila NO borra el audio")
        pag.locator(".pista .quitar").nth(2).click()
        pag.wait_for_timeout(300)
        chequear("queda una pista menos", pag.locator(".pista").count() == 2)
        chequear("el audio sigue en la bandeja", pag.locator(".rec").count() == 3)
        chequear("y ya no dice que esta dos veces",
                 "×2" not in pag.locator(".rec").nth(0).inner_text())

        print("\n7. cortar leyendo el texto (lo que dice, con marcas de tiempo)")
        textos_guardados = []

        def segmentos(route, request):
            if request.method == "POST":
                textos_guardados.append(json.loads(request.post_data or "{}"))
                return route.fulfill(status=200, content_type="application/json",
                                     body=json.dumps({"ok": True}))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "segmentos": FRASES}))

        pag.route("**/estudio/segmentos/**", segmentos)
        pag.locator(".pista [data-vertexto]").nth(0).click()
        pag.wait_for_selector(".pista .texto.abierto .frase", timeout=8000)
        chequear("se ven las tres frases", pag.locator(".frase").count() == len(FRASES),
                 str(pag.locator(".frase").count()))
        chequear("cada frase muestra su minuto", "0:01" in pag.locator(".frase").nth(1).inner_text(),
                 pag.locator(".frase").nth(1).inner_text().split("\n")[0])
        dice = pag.locator('.frase [data-editar="1"]').first
        chequear("el texto se puede editar ahí mismo", dice.get_attribute("contenteditable") == "true")
        dice.fill("te mando el presupuesto corregido")
        dice.press("Tab")
        pag.wait_for_timeout(450)
        chequear("la corrección se guarda sola", bool(textos_guardados), str(textos_guardados[:1]))
        chequear("guarda el texto corregido con sus tiempos",
                 textos_guardados[-1]["segmentos"][1]["texto"] == "te mando el presupuesto corregido",
                 str(textos_guardados[-1].get("segmentos", [])[1:2]))
        chequear("editar no reproduce el audio", pag.evaluate("sonando === null"))
        pag.locator('[data-desde="1"]').click(force=True)
        pag.wait_for_timeout(250)
        chequear("'desde' recorta el principio en esa frase",
                 abs(pag.evaluate("pistas[0].ini") - 1.0) < 0.01,
                 str(pag.evaluate("pistas[0].ini")))
        pag.locator('[data-hasta="1"]').click(force=True)
        pag.wait_for_timeout(250)
        chequear("'hasta' recorta el final en esa frase",
                 abs(pag.evaluate("pistas[0].fin") - 2.0) < 0.01,
                 str(pag.evaluate("pistas[0].fin")))
        chequear("las frases que quedaron afuera se ven apagadas",
                 pag.locator(".frase.afuera").count() == 2,
                 str(pag.locator(".frase.afuera").count()))

        print("\n8. la marca y la tijera")
        caja = pag.locator('[data-onda]').nth(0).bounding_box()
        pag.mouse.click(caja["x"] + caja["width"] * 0.5, caja["y"] + caja["height"] / 2)
        pag.wait_for_timeout(250)
        pos = pag.evaluate("pistas[0].pos")
        chequear("tocar la onda deja la marca donde tocaste", abs(pos - 1.5) < 0.15, str(pos))
        chequear("la marca se ve", pag.locator(".cursor.puesto").count() >= 1)
        antes = pag.evaluate("pistas.length")
        pag.locator(".pista [data-partir]").nth(0).click()
        pag.wait_for_timeout(400)
        chequear("partir deja una pista mas", pag.evaluate("pistas.length") == antes + 1,
                 str(pag.evaluate("pistas.length")))
        chequear("la primera termina en el corte",
                 abs(pag.evaluate("pistas[0].fin") - 1.5) < 0.15, str(pag.evaluate("pistas[0].fin")))
        chequear("la segunda empieza en el corte",
                 abs(pag.evaluate("pistas[1].ini") - 1.5) < 0.15, str(pag.evaluate("pistas[1].ini")))
        chequear("y las dos son del mismo archivo",
                 pag.evaluate("pistas[0].archivo === pistas[1].archivo"))
        # Sin marca la tijera parte por el MEDIO del pedazo: es lo que uno espera de una
        # tijera sin apuntar. (La primera versión de esta prueba esperaba un aviso; el
        # aviso es sólo para el caso en que no entra nada de los dos lados.)
        pag.evaluate("pistas[1].pos = undefined")
        antes2 = pag.evaluate("pistas.length")
        pag.locator(".pista [data-partir]").nth(1).click()
        pag.wait_for_timeout(300)
        chequear("sin marca parte por el medio del pedazo",
                 pag.evaluate("pistas.length") == antes2 + 1, str(pag.evaluate("pistas.length")))
        pag.evaluate("pistas[0].ini = 0; pistas[0].fin = 0.3; pistas[0].pos = undefined")
        pag.locator(".pista [data-partir]").nth(0).click()
        pag.wait_for_timeout(300)
        chequear("un pedazo demasiado corto no se parte: avisa",
                 "muy corto" in pag.locator("#aviso").inner_text(),
                 pag.locator("#aviso").inner_text()[:60])

        print("\n9. mandarse el resultado al celular")
        pedidos = []

        def cazar(route, request):
            pedidos.append(json.loads(request.post_data or "{}"))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "error": ""}))

        pag.route("**/estudio/unir", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "archivo": "unido_prueba.mp3", "dur": 8.8})))
        pag.route("**/estudio/mandar", cazar)
        pag.click("#btnUnir")
        pag.wait_for_selector("#salida button.mandar", timeout=8000)
        chequear("aparecen los dos botones de mandar",
                 pag.locator("#salida button.mandar").count() == 2)
        chequear("y el de descargar sigue estando", pag.locator("#salida a.descargar").count() == 1)
        pag.locator('[data-mandar="whatsapp"]').click()
        pag.wait_for_timeout(500)
        chequear("pide mandarlo por whatsapp",
                 bool(pedidos) and pedidos[0].get("por") == "whatsapp", str(pedidos[:1]))
        chequear("y manda el archivo que salio de unir",
                 bool(pedidos) and pedidos[0].get("archivo") == "unido_prueba.mp3")
        chequear("avisa en pantalla que salio", "te lo mandé" in pag.locator("#dicho").inner_text(),
                 pag.locator("#dicho").inner_text())

        pag.screenshot(path=str(Path(__file__).with_name("estudio_pantalla.png")), full_page=True)

        print("\n9b. el analisis")
        chequear("se puede analizar SIN armar el mp3 (el boton esta arriba)",
                 pag.locator("#btnAnalizar").is_visible())
        chequear("y se puede elegir el lente",
                 pag.locator("#perfil option").count() == 3,
                 str(pag.locator("#perfil option").count()))
        pag.select_option("#perfil", "ventas")
        pag.locator("#btnAnalizar").click()
        pag.wait_for_timeout(600)
        chequear("manda el perfil elegido",
                 bool(analisis_pedidos) and analisis_pedidos[0].get("perfil") == "ventas",
                 str(analisis_pedidos[:1])[:80])
        chequear("manda las pistas con su recorte",
                 bool(analisis_pedidos) and len(analisis_pedidos[0].get("pistas") or []) >= 1)
        chequear("muestra el analisis en pantalla",
                 "RESUMEN DEL ARMADO" in pag.locator("#analisis").inner_text(),
                 pag.locator("#analisis").inner_text()[:40])
        chequear("y dice sobre cuanto texto lo hizo",
                 "1.234" in pag.locator("#dichoAnal").inner_text(),
                 pag.locator("#dichoAnal").inner_text())
        # Copiar: se le da permiso al navegador y se lee el portapapeles de vuelta.
        ctx = pag.context
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        pag.locator('[data-copiar="anal"]').click()
        pag.wait_for_timeout(400)
        pegado = pag.evaluate("navigator.clipboard.readText()")
        chequear("copiar el analisis lo deja en el portapapeles",
                 "RESUMEN DEL ARMADO" in pegado, pegado[:40])
        chequear("y avisa que copio", "copiado" in pag.locator("#dichoAnal").inner_text(),
                 pag.locator("#dichoAnal").inner_text())
        pag.locator('[data-copiar="dicho"]').click()
        pag.wait_for_timeout(400)
        pegado2 = pag.evaluate("navigator.clipboard.readText()")
        chequear("copiar lo que dice trae la transcripcion",
                 "hola, como andas" in pegado2, pegado2[:40])
        pag.locator("[data-cerrar-anal]").click()
        pag.wait_for_timeout(200)
        chequear("se puede cerrar el panel",
                 "abierto" not in (pag.locator("#analisis").get_attribute("class") or ""))
        # El analisis de UN audio, el que ya venia hecho de cuando entro
        pag.locator(".pista [data-veranal]").first.click()
        pag.wait_for_timeout(500)
        chequear("el 🧠 de una pista muestra su analisis guardado",
                 "pide un presupuesto" in pag.locator(".texto.analisis.abierto").first.inner_text(),
                 pag.locator(".texto.analisis.abierto").first.inner_text()[:50])

        print("\n10. sacar y PONER frases sobre el mismo audio")

        def una_pista_entera():
            """Deja UNA pista, entera, con su texto abierto — para probar cada caso limpio."""
            pag.evaluate("pistas.length = 0; sumar(recibidos[0].archivo);")
            pag.wait_for_timeout(250)
            pag.evaluate("pistas[0].frases = %s; pistas[0].abierto = true; pintar();"
                         % json.dumps(FRASES))
            pag.wait_for_timeout(250)

        una_pista_entera()
        pag.locator('[data-sacar="1"]').first.click(force=True)   # sacar la del MEDIO
        pag.wait_for_timeout(350)
        chequear("sacar NO parte la pista: sigue habiendo una sola",
                 pag.evaluate("pistas.length") == 1, str(pag.evaluate("pistas.length")))
        chequear("la frase queda marcada como sacada",
                 pag.evaluate("pistas[0].fuera").
                 __eq__([1]) or pag.evaluate("pistas[0].fuera") == [1],
                 str(pag.evaluate("pistas[0].fuera")))
        chequear("se ve tachada y con el boton de poner",
                 pag.locator(".frase.afuera").count() == 1 and
                 pag.locator('.frase.afuera [data-sacar="1"]').inner_text().strip().endswith("poner"),
                 pag.locator('.frase.afuera [data-sacar="1"]').inner_text())
        # El agujero viaja al servidor como DOS tramos del mismo archivo
        tramos = pag.evaluate("paraEnviar()")
        chequear("el agujero viaja como dos tramos", len(tramos) == 2, str(tramos))
        chequear("el primero termina donde empezaba la frase",
                 abs(tramos[0]["fin"] - 1.0) < 0.02, str(tramos[0]))
        chequear("el segundo arranca donde terminaba",
                 abs(tramos[1]["ini"] - 2.0) < 0.02, str(tramos[1]))
        chequear("la duracion resta el pedazo sacado",
                 abs(pag.evaluate("duraPista(pistas[0])") - 2.0) < 0.05,
                 str(pag.evaluate("duraPista(pistas[0])")))

        # ⭐ Y lo que faltaba: volver a ponerla
        pag.locator('[data-sacar="1"]').first.click(force=True)
        pag.wait_for_timeout(350)
        chequear("volver a ponerla la devuelve",
                 pag.evaluate("pistas[0].fuera").__len__() == 0,
                 str(pag.evaluate("pistas[0].fuera")))
        chequear("y el audio vuelve a durar lo de antes",
                 abs(pag.evaluate("duraPista(pistas[0])") - 3.0) < 0.05,
                 str(pag.evaluate("duraPista(pistas[0])")))
        chequear("ya no queda ninguna tachada", pag.locator(".frase.afuera").count() == 0)

        # Varias sacadas juntas: tres tramos
        pag.locator('[data-sacar="0"]').first.click(force=True)
        pag.locator('[data-sacar="2"]').first.click(force=True)
        pag.wait_for_timeout(350)
        chequear("sacar la primera y la ultima deja un solo tramo del medio",
                 len(pag.evaluate("paraEnviar()")) == 1, str(pag.evaluate("paraEnviar()")))

        # ⚠ Una frase puede estar afuera por DOS motivos: la sacaste, o quedó fuera del
        # recorte de las manijas. En el segundo caso "poner" no ponía nada — el botón
        # existía y no hacía lo que decía.
        una_pista_entera()
        pag.evaluate("pistas[0].ini = 2.0; colocar(pistas[0]); pintarTexto(pistas[0]);")
        pag.wait_for_timeout(250)
        chequear("con el recorte movido, las primeras quedan afuera",
                 pag.locator(".frase.afuera").count() == 2,
                 str(pag.locator(".frase.afuera").count()))
        pag.locator('[data-sacar="0"]').first.click(force=True)
        pag.wait_for_timeout(300)
        chequear("poner una frase que estaba fuera del RECORTE estira el recorte",
                 abs(pag.evaluate("pistas[0].ini")) < 0.02, str(pag.evaluate("pistas[0].ini")))
        chequear("y esa frase queda adentro de verdad",
                 pag.evaluate("frasePuesta(pistas[0], 0)"))

        # ⚠ Whisper a veces termina la ULTIMA frase despues del final del audio (visto:
        # audio de 24,51 s con la frase marcada hasta 26,03). Se veia tachada sin que
        # nadie la sacara y "poner" no la podia poner, porque el recorte no se puede
        # estirar mas alla del final. Ahora las frases se recortan al largo real.
        pag.evaluate("pistas.length = 0; sumar(recibidos[0].archivo);")
        pag.wait_for_timeout(250)
        pag.evaluate("""pistas[0].frases = %s;
                        pistas[0].frases[2].fin = 4.6;
                        acomodarFrases(pistas[0]);
                        pistas[0].abierto = true; pintar();""" % json.dumps(FRASES))
        pag.wait_for_timeout(250)
        chequear("una frase que se pasa del final NO aparece tachada",
                 pag.locator(".frase.afuera").count() == 0,
                 str(pag.locator(".frase.afuera").count()))
        chequear("y cuenta como puesta",
                 pag.evaluate("frasePuesta(pistas[0], 2)"))
        chequear("el audio no se estira mas alla de lo que dura",
                 abs(pag.evaluate("duraPista(pistas[0])") - 3.0) < 0.05,
                 str(pag.evaluate("duraPista(pistas[0])")))

        # ⭐⭐ LA REGLA, no el caso. Este mismo boton ya fallo DOS veces por dos motivos
        # distintos: una frase fuera del recorte de las manijas, y una frase que Whisper
        # termina despues del final del audio. Las dos veces se arreglo el motivo y se
        # agrego un chequeo para ESE motivo — y al mes aparecio otro motivo.
        # Entonces aca no se chequea un motivo: se chequea la promesa del boton. Se deja
        # la frase afuera de todas las maneras que existen y despues de apretar "＋ poner"
        # NO PUEDE quedar ninguna tachada. Si mañana aparece un tercer motivo, esto lo
        # agarra sin que nadie lo haya adivinado antes.
        print("\n10b. la promesa del boton: si dice 'poner', pone")
        motivos = [
            ("sacada a mano", "pistas[0].fuera = [0, 2];"),
            ("fuera del recorte por delante", "pistas[0].ini = 2.5;"),
            ("fuera del recorte por atras", "pistas[0].fin = 0.5;"),
            ("una frase que se pasa del final del audio",
             "pistas[0].frases[2].fin = 9.9; acomodarFrases(pistas[0]);"),
            ("todo junto", "pistas[0].fuera = [1]; pistas[0].ini = 2.5;"
                           " pistas[0].frases[2].fin = 9.9; acomodarFrases(pistas[0]);"),
        ]
        for nombre, ajuste in motivos:
            una_pista_entera()
            pag.evaluate(ajuste + " colocar(pistas[0]); pintarTexto(pistas[0]);")
            pag.wait_for_timeout(200)
            # Se aprietan todos los "poner" que haya, uno por vez. El tope evita quedarse
            # colgado justo cuando el boton no hace nada, que es el defecto que se busca.
            for _ in range(len(FRASES) + 1):
                if not pag.locator(".frase.afuera .pone").count():
                    break
                pag.locator(".frase.afuera .pone").first.click(force=True)
                pag.wait_for_timeout(200)
            quedaron = pag.locator(".frase.afuera").count()
            chequear("con la frase %s, 'poner' la pone" % nombre, quedaron == 0,
                     "quedaron %d tachadas" % quedaron)
            chequear("  y suena el audio entero de nuevo",
                     abs(pag.evaluate("duraPista(pistas[0])") - 3.0) < 0.05,
                     str(pag.evaluate("duraPista(pistas[0])")))

        print("\n11. la pantalla explica como se une")
        chequear("con UN audio el boton no dice 'Unir'",
                 pag.locator("#btnUnir").inner_text() == "Armar el audio",
                 pag.locator("#btnUnir").inner_text())
        chequear("y explica como pegar otro",
                 "PEGAR dos" in pag.locator("#ayudaFila").inner_text(),
                 pag.locator("#ayudaFila").inner_text()[:70])
        pag.evaluate("sumar(recibidos[1].archivo);")
        pag.wait_for_timeout(350)
        chequear("con dos, el boton dice cuantos une",
                 pag.locator("#btnUnir").inner_text() == "Unir los 2 audios",
                 pag.locator("#btnUnir").inner_text())
        chequear("y explica que se pegan en ese orden",
                 "en este orden" in pag.locator("#ayudaFila").inner_text(),
                 pag.locator("#ayudaFila").inner_text()[:70])

        print("\n12. sin ningun audio todavia (la primera vez que entras)")
        # ⚠ Este caso existe por un bug visto en vivo: con la bandeja vacia, la firma
        # del refresco daba '' igual que la lista del arranque, el "no repintar si no
        # cambio" se disparaba en la PRIMERA vuelta y la pantalla se quedaba para
        # siempre en "Buscando…". Justo lo que ve alguien que entra por primera vez.
        pag2 = nav.new_page(viewport={"width": 1180, "height": 900})
        err2 = []
        pag2.on("pageerror", lambda e: err2.append(str(e)))
        pag2.route("**/estudio", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        pag2.route("**/estudio/entrantes", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "audios": []})))
        pag2.route("**/estudio/lista", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "archivos": []})))
        # ⚠ Estas dos tambien: el arranque las espera con `await` ANTES de pintar la
        # bandeja, asi que si van al panel de verdad la pantalla se queda en "Buscando…"
        # el tiempo que tarde el server (y `/estudio/perfiles` importa google-genai la
        # primera vez, que no es gratis). Una prueba de pantalla no puede depender de eso.
        pag2.route("**/estudio/perfiles", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "perfiles": ["generico"], "defecto": "generico"})))
        pag2.route("**/estudio/proyectos", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "proyectos": [], "cuentas": {}, "total": 0})))
        pag2.goto("http://127.0.0.1:8750/estudio", wait_until="domcontentloaded")
        pag2.wait_for_timeout(900)
        texto = pag2.locator("#bandeja").inner_text()
        chequear("no se queda en 'Buscando…'", "Buscando" not in texto, texto[:60])
        chequear("explica que hay que mandar un audio", "Mandale uno" in texto, texto[:80])
        chequear("sin errores de JavaScript (bandeja vacia)", not err2, " | ".join(err2[:2]))
        pag2.close()
        chequear("sin errores de JavaScript", not errores, " | ".join(errores[:2]))
        nav.close()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d: %s" % (len(FALLAS), FALLAS)))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
