"""Verifica el Estudio de video y su entrada desde la app móvil, sin tocar datos reales."""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import panel  # noqa: E402

HTML = Path("app/estaticos/estudio.html").read_text(encoding="utf-8")
FALLAS = []


def chequear(que, ok, detalle=""):
    print(("  OK   " if ok else "  FALLA ") + que + (" -> " + detalle if detalle else ""))
    if not ok:
        FALLAS.append(que)


def json_respuesta(route, data):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(data))


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True)

        print("\n1. entrada desde Laura móvil")
        movil = ctx.new_page()
        errores_movil = []
        movil.on("pageerror", lambda e: errores_movil.append(str(e)))
        movil.route(re.compile(r".*/movil(?:\?.*)?$"), lambda r: r.fulfill(
            status=200, content_type="text/html", body=panel.MOVIL_HTML))
        movil.goto("http://127.0.0.1:8750/movil", wait_until="domcontentloaded")
        movil.wait_for_timeout(300)
        boton = movil.locator('#abajo .dest[data-href="/estudio"]')
        chequear("Estudio aparece en la barra del celular", boton.count() == 1)
        chequear("el botón es visible y cómodo para el dedo", boton.is_visible())
        chequear("la app móvil no tiene errores de JavaScript", not errores_movil,
                 " | ".join(errores_movil[:2]))
        movil.close()

        print("\n2. Estudio de video en pantalla de teléfono")
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route(re.compile(r".*/estudio(?:\?.*)?$"), lambda r: r.fulfill(
            status=200, content_type="text/html", body=HTML))
        pag.route("**/estaticos/*.js", lambda r: r.fulfill(status=200,
                                                            content_type="text/javascript", body=""))
        pag.route("**/estudio/lista", lambda r: json_respuesta(r, {
            "ok": True, "archivos": ["audio_prueba.mp3", "video_prueba.mp4"]}))
        pag.route("**/estudio/perfiles", lambda r: json_respuesta(r, {
            "ok": True, "perfiles": ["generico"], "defecto": "generico"}))
        pag.route("**/estudio/proyectos", lambda r: json_respuesta(r, {
            "ok": True, "proyectos": [], "cuentas": {"": 2}, "total": 2}))
        estado_video = {"listo": False}

        def entrantes(route):
            video = {"archivo": "video_prueba.mp4", "tipo": "video",
                     "origen": "telegram", "de": "Martin Jones", "cuando": 1787244000,
                     "dur": 12.0, "texto": "Martín muestra una caja y explica cómo abrirla" if estado_video["listo"] else "",
                     "proyecto": "", "segs": 1 if estado_video["listo"] else 0,
                     "tiene_analisis": True}
            json_respuesta(route, {"ok": True, "audios": [{"archivo": "audio_prueba.mp3", "tipo": "audio",
                "origen": "telegram", "de": "Martin Jones", "cuando": 1787243900,
                "dur": 8.0, "texto": "Audio de prueba para la otra pestaña",
                "proyecto": "", "segs": 0, "tiene_analisis": False},
              video]})

        pag.route("**/estudio/entrantes", entrantes)
        def segmentos(route):
            json_respuesta(route, {"ok": True, "segmentos": (
                [{"inicio": 0.5, "fin": 3.0, "texto": "Martín muestra una caja"}]
                if estado_video["listo"] else [])})

        pag.route("**/estudio/segmentos/*", segmentos)
        # Antes de que exista un trabajo, la pantalla pregunta acá. Durante el POST
        # real este mismo endpoint devuelve el porcentaje y el paso actual.
        pag.route("**/estudio/progreso/*", lambda r: json_respuesta(r, {
            "ok": True, "en_curso": False, "pct": 0, "paso": "Esperando…"}))
        transcripciones = []

        def transcribir(route, request):
            transcripciones.append(request.url)
            estado_video["listo"] = True
            json_respuesta(route, {"ok": True, "texto": "Martín muestra una caja",
                                   "segmentos": [{"inicio": 0.5, "fin": 3.0,
                                                  "texto": "Martín muestra una caja"}]})

        pag.route("**/estudio/transcribir/*", transcribir)
        pag.route("**/estudio/onda/*", lambda r: json_respuesta(r, {
            "ok": True, "picos": [0.2, 0.8, 0.4, 0.7]}))
        pag.route("**/estudio/miniaturas/*", lambda r: r.fulfill(
            status=200, content_type="image/svg+xml",
            body='<svg xmlns="http://www.w3.org/2000/svg" width="480" height="270"><rect width="480" height="270" fill="#123"/></svg>'))
        pag.route("**/estudio/analisis/*", lambda r: json_respuesta(r, {
            "ok": True, "texto": "Resumen del video", "visual": [
                {"segundo": 6.0, "descripcion": "abre la caja"}]}))
        pag.route("**/estudio/audio/*", lambda r: r.fulfill(status=204, body=""))
        escuchar_laura = []
        pag.route("**/escuchar/claude", lambda r: (
            escuchar_laura.append(r.request.url), json_respuesta(r, {"ok": True})
        )[-1])
        pag.goto("http://127.0.0.1:8750/estudio", wait_until="domcontentloaded")
        pag.wait_for_timeout(700)

        chequear("hay una salida clara para volver a Laura", pag.locator("#volverMovil").is_visible())
        chequear("audio y video tienen entradas separadas", pag.locator("[data-medio]").count() == 2)
        chequear("abre en audio cuando hay de los dos", pag.locator("[data-medio='audio'].sel").count() == 1)
        pag.locator("[data-medio='video']").tap()
        pag.wait_for_timeout(150)
        chequear("la pestaña Video deja claro dónde estás", pag.locator("[data-medio='video'].sel").count() == 1)
        chequear("el video se distingue en la bandeja", pag.locator(".tipoMedia").inner_text() == "VIDEO")
        pag.wait_for_selector("video.previewVideo")
        chequear("el video se prepara solo antes de entrar a editar", bool(transcripciones))
        chequear("no ofrece una fila sin texto ni pide generarlo a mano",
                 pag.locator("[data-preparar]").count() == 0)
        pag.locator("[data-medio='audio']").tap()
        pag.wait_for_timeout(100)
        chequear("la fila de audio está separada de la de video", pag.locator(".pista").count() == 0)
        pag.locator('.mas[data-sumar="audio_prueba.mp3"]').click()
        pag.wait_for_timeout(100)
        chequear("cada tipo conserva su propio armado", pag.locator(".pista").count() == 1)
        pag.locator("[data-medio='video']").tap()
        pag.wait_for_timeout(100)
        chequear("al volver, sigue esperando el armado de video", pag.locator("video.previewVideo").count() == 1)
        chequear("tiene una tira de miniaturas para cortar mirando",
                 pag.locator("[data-miniaturas='0']").count() == 1)
        pag.locator("[data-miniaturas='0']").click(position={"x": 150, "y": 25})
        pag.wait_for_timeout(100)
        chequear("tocar una miniatura mueve el cursor",
                 pag.evaluate("typeof pistas[0].pos === 'number' && pistas[0].pos > 0"),
                 str(pag.evaluate("pistas[0].pos")))
        pag.locator('[data-veranal="0"]').click()
        pag.wait_for_selector('[data-vermomento="0"]')
        chequear("el análisis muestra momentos para navegar", "abre la caja" in pag.locator(".descripcionMomento").inner_text())
        chequear("la descripción visual se puede seleccionar y copiar",
                 pag.locator(".descripcionMomento").evaluate("e => getComputedStyle(e).userSelect") == "text",
                 str(pag.locator(".descripcionMomento").evaluate("e => getComputedStyle(e).userSelect")))
        pag.locator('[data-vermomento="0"]').click()
        pag.wait_for_timeout(100)
        chequear("un momento del análisis lleva a su segundo",
                 abs(pag.evaluate("pistas[0].pos") - 6.0) < 0.1, str(pag.evaluate("pistas[0].pos")))
        pag.locator('[data-selecmomento="0"]').click()
        pag.wait_for_timeout(100)
        chequear("un momento visual se puede sumar como tramo a la fila",
                 pag.evaluate("pistas.length === 2 && pistas[1].ini === 6 && pistas[1].fin > 6"),
                 str(pag.evaluate("pistas.map(p => [p.ini, p.fin])")))
        chequear("se puede previsualizar la fila antes de exportar", pag.locator("#btnVista").is_visible())
        pag.locator("#btnVista").click()
        chequear("la vista previa se abre", pag.locator("#vistaArmado.abierta").count() == 1)
        pag.locator("[data-cerrar-vista]").click()
        pag.locator('[data-vertexto="0"]').click()
        pag.wait_for_selector(".frase")
        chequear("al generar desde la bandeja aparecen cortes por frase",
                 "Martín muestra una caja" in pag.locator(".frase").inner_text())
        chequear("generar el texto no activa a Laura", not escuchar_laura)
        chequear("el botón conserva claro que arma videos", "video" in pag.locator("#btnUnir").inner_text().lower(),
                 pag.locator("#btnUnir").inner_text())
        chequear("el silencio de audio no confunde al editar video",
                 not pag.locator("#controlSilencio").is_visible())
        # El video todavía no es una fuente mientras prepara texto Y análisis: se
        # muestra esta tarjeta de avance, no un reproductor ni un botón manual.
        pag.evaluate("""() => {
          const a = recibidos.find(x => x.archivo === 'video_prueba.mp4');
          a.segs = 1; a.tiene_analisis = false; a.texto = 'todavía no importa';
          preparandoTexto.add(a.archivo);
          avancesVideo.set(a.archivo, {pct: 84, paso: 'Analizando el video y sus momentos…'});
          pistas = pistas.filter(p => p.archivo !== a.archivo);
          modo = 'video'; pintar(); pintarBandeja();
        }""")
        chequear("muestra el porcentaje mientras prepara el video",
                 pag.locator(".progresoVideo strong").inner_text() == "84%")
        chequear("explica el paso que está haciendo",
                 "Analizando el video" in pag.locator(".progresoVideo .proPaso").inner_text())
        chequear("el progreso no muestra el video antes del análisis inteligente",
                 pag.locator("video.previewVideo").count() == 0)
        chequear("no hay scroll horizontal en el teléfono",
                 pag.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                 str(pag.evaluate("[document.documentElement.scrollWidth, innerWidth]")))
        chequear("el Estudio móvil no tiene errores de JavaScript", not errores,
                 " | ".join(errores[:2]))
        pag.screenshot(path="resultados/ver_estudio_video_movil.png", full_page=True)
        pag.close()
        nav.close()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d: %s" % (len(FALLAS), FALLAS)))
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
