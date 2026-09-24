"""Prueba visual del envío Estudio → Sesiones, sin tocar datos ni charlas reales."""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "app" / "estaticos" / "estudio.html"
CAPTURAS = RAIZ / "resultados"
FALLAS = []


def chequear(texto, condicion, detalle=""):
    print(("  OK   " if condicion else "  FALLA ") + texto +
          ((" -> " + detalle) if detalle else ""))
    if not condicion:
        FALLAS.append(texto)


def main():
    html = PAGINA.read_text(encoding="utf-8")
    enviados = []
    preparado = []
    sesiones = {"proyectos": [{
        "proyecto": "wpp-transcriptor", "cwd": str(RAIZ), "sesiones": [
            {"id": "ocupada", "nombre": "Otra tarea", "cerebro": "codex",
             "ocupada": True, "ts": time.time()},
            {"id": "destino-123", "nombre": "Ideas para videos", "cerebro": "codex",
             "ocupada": False, "ts": time.time() - 10},
        ]
    }]}

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome", headless=True)
        pagina = navegador.new_page(viewport={"width": 1180, "height": 900})
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))

        pagina.route("**/estudio", lambda r: r.fulfill(
            status=200, content_type="text/html", body=html))
        pagina.route("**/estudio/lista", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "archivos": ["video.mp4"]})))
        pagina.route("**/estudio/perfiles", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "perfiles": ["generico"], "defecto": "generico"})))
        pagina.route("**/estudio/proyectos", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "proyectos": [], "cuentas": {}, "total": 0})))
        pagina.route("**/estudio/cola", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "items": []})))
        pagina.route("**/estudio/entrantes", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "audios": []})))
        pagina.route("**/movil/sesiones", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(sesiones)))

        def preparar(route, request):
            preparado.append(json.loads(request.post_data or "{}"))
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "ok": True, "tipo": "video", "fragmentos": 2,
                "ruta_medio": r"D:\IA\wpp-transcriptor\resultados\estudio\seleccion.mp4",
                "ruta_contexto": r"D:\IA\wpp-transcriptor\resultados\estudio\seleccion.md",
                "ruta_mosaico": r"D:\IA\wpp-transcriptor\resultados\estudio\seleccion.jpg",
                "advertencia": "",
            }))

        pagina.route("**/estudio/preparar-sesion", preparar)

        def mandar(route, request):
            enviados.append(request.post_data or "")
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "segundo_plano": True,
                                           "trabajo": "trabajo-1"}))

        pagina.route("**/movil/mandar", mandar)
        pagina.route("**/sesiones?c=*", lambda r: r.fulfill(
            status=200, content_type="text/html", body="<title>Sesión abierta</title>listo"))

        pagina.goto("http://127.0.0.1:8750/estudio", wait_until="domcontentloaded")
        pagina.wait_for_timeout(500)
        pagina.evaluate("""() => {
          localStorage.setItem('sesSitio', JSON.stringify({activa:'destino-123'}));
          modo = 'video';
          pistas = [
            {id:901, archivo:'video.mp4', tipo:'video', nombre:'primer momento', dur:30, ini:2, fin:8},
            {id:902, archivo:'video.mp4', tipo:'video', nombre:'segundo momento', dur:30, ini:14, fin:21}
          ];
          pintarMedios(); pintar();
        }""")

        pagina.locator("#btnPasarSesion").click()
        pagina.wait_for_selector("#pasarSesion.abierto")
        pagina.wait_for_function("!document.querySelector('#sesDestino').disabled")
        texto = pagina.locator(".pasarTarjeta").inner_text()
        chequear("el botón abre una hoja propia de la pantalla", "Pasar a una sesión" in texto)
        chequear("explica todo lo que va a viajar",
                 "video armado" in texto and "transcripción con tiempos" in texto and
                 "mosaico visual" in texto, texto[:180])
        chequear("recuerda la última conversación usada",
                 "Ideas para videos" in pagina.locator("#sesDestino option:checked").inner_text(),
                 pagina.locator("#sesDestino option:checked").inner_text())
        chequear("una conversación ocupada no se puede elegir",
                 pagina.locator("#sesDestino").evaluate(
                     "e => [...e.options].some(o => o.textContent.includes('Otra tarea') && o.disabled)"))

        CAPTURAS.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURAS / "estudio_a_sesion.png"), full_page=True)
        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.wait_for_timeout(200)
        tarjeta = pagina.locator(".pasarTarjeta").bounding_box()
        chequear("en el celular la hoja entra completa",
                 tarjeta and tarjeta["width"] <= 390 and tarjeta["y"] >= 0, str(tarjeta))
        chequear("los campos táctiles no provocan zoom de iPhone",
                 pagina.locator("#sesPedido").evaluate("e => getComputedStyle(e).fontSize") == "16px")
        pagina.screenshot(path=str(CAPTURAS / "estudio_a_sesion_movil.png"), full_page=True)

        pagina.locator("#sesPedido").fill("Elegí los mejores momentos para un reel.")
        pagina.locator("#sesEnviar").click()
        pagina.wait_for_function("() => location.pathname === '/sesiones'", timeout=8000)
        chequear("primero prepara la selección", len(preparado) == 1, str(preparado))
        chequear("manda exactamente los dos cortes",
                 len(preparado[0].get("pistas", [])) == 2, str(preparado[0]))
        cuerpo = enviados[0] if enviados else ""
        chequear("usa la conversación elegida", "destino-123" in cuerpo and str(RAIZ) in cuerpo)
        chequear("la sesión recibe las tres rutas del paquete",
                 "seleccion.mp4" in cuerpo and "seleccion.md" in cuerpo and
                 "seleccion.jpg" in cuerpo)
        chequear("también recibe la indicación de Martín", "mejores momentos para un reel" in cuerpo)
        chequear("el turno queda trabajando aunque la página se vaya", "segundo_plano" in cuerpo)
        chequear("al terminar abre la conversación elegida",
                 pagina.url.endswith("/sesiones?c=destino-123"), pagina.url)
        chequear("no hubo errores de JavaScript", not errores, " | ".join(errores))
        navegador.close()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d" % len(FALLAS)))
    print("Capturas:", CAPTURAS / "estudio_a_sesion.png", "y",
          CAPTURAS / "estudio_a_sesion_movil.png")
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
