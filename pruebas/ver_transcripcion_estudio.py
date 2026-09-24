"""La transcripción del Estudio debe ocupar el ancho de la pista, no una rendija."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "app" / "estaticos" / "estudio.html").read_text(encoding="utf-8")
CAPTURA = RAIZ / "resultados" / "transcripcion_estudio_legible.png"
CAPTURA_MOVIL = RAIZ / "resultados" / "transcripcion_estudio_legible_movil.png"
FALLAS = []


def chequear(que, ok, detalle=""):
    print(("  OK   " if ok else "  FALLA ") + que +
          ((" -> " + detalle) if detalle else ""))
    if not ok:
        FALLAS.append(que)


def responder(route, data):
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps(data, ensure_ascii=False))


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome", headless=True)
        pagina = navegador.new_page(viewport={"width": 1792, "height": 900})
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        pagina.route("**/estudio", lambda r: r.fulfill(
            status=200, content_type="text/html", body=HTML))
        pagina.route("**/estudio/lista", lambda r: responder(r, {"ok": True, "archivos": []}))
        pagina.route("**/estudio/entrantes", lambda r: responder(r, {"ok": True, "audios": []}))
        pagina.route("**/estudio/proyectos", lambda r: responder(
            r, {"ok": True, "proyectos": [], "cuentas": {}, "total": 0}))
        pagina.route("**/estudio/perfiles", lambda r: responder(
            r, {"ok": True, "perfiles": ["generico"], "defecto": "generico"}))
        pagina.route("**/estudio/cola", lambda r: responder(r, {"ok": True, "items": []}))
        pagina.route("**/estudio/analizar/guardado", lambda r: responder(
            r, {"ok": True, "guardado": False}))

        pagina.goto("http://127.0.0.1:8750/estudio", wait_until="domcontentloaded")
        pagina.wait_for_timeout(350)
        pagina.evaluate("""() => {
          modo = 'audio';
          pistas = [{
            id: 7001, archivo: 'recibo.mp3', tipo: 'audio',
            nombre: 'Te mando el recorte porque estoy con el tema de un recibo que necesito controlar',
            dur: 22.1, ini: 0, fin: 22.1, pos: 0,
            picos: Array.from({length: 90}, (_, i) => .25 + (i % 9) / 12),
            abierto: true,
            frases: [
              {inicio: 0, fin: 8.2, texto: 'Te mando el recorte porque estoy con el tema de un recibo que necesito controlar.'},
              {inicio: 8.2, fin: 15.4, texto: 'La fecha de pago se revisó en el extracto y en el comprobante.'},
              {inicio: 15.4, fin: 22.1, texto: 'Después verificamos que todos los datos coincidan.'}
            ]
          }];
          pintarMedios(); pintar();
        }""")
        pagina.wait_for_selector(".pista .texto.abierto .frase")

        medidas = pagina.locator(".pista").evaluate("""p => {
          const contenido = p.querySelector('.contenidoPista');
          const texto = p.querySelector('.texto.abierto');
          const dice = p.querySelector('.dice');
          return {
            pista: p.getBoundingClientRect().width,
            contenido: contenido.getBoundingClientRect().width,
            texto: texto.getBoundingClientRect().width,
            dice: dice.getBoundingClientRect().width,
            altoDice: dice.getBoundingClientRect().height,
            displayContenido: getComputedStyle(contenido).display,
            scroll: document.documentElement.scrollWidth,
            cliente: document.documentElement.clientWidth
          };
        }""")
        chequear("la pista conserva una columna ancha para su contenido",
                 medidas["contenido"] > medidas["pista"] * 0.70, str(medidas))
        chequear("la transcripción usa todo el ancho de esa columna",
                 medidas["texto"] > medidas["contenido"] * 0.95, str(medidas))
        chequear("una frase se lee en renglones normales",
                 medidas["dice"] > 450 and medidas["altoDice"] < 65, str(medidas))
        chequear("el contenedor de la pista no heredó el flex de las pestañas",
                 medidas["displayContenido"] == "block", str(medidas))

        CAPTURA.parent.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURA), full_page=True)

        pagina.set_viewport_size({"width": 390, "height": 844})
        pagina.wait_for_timeout(200)
        movil = pagina.locator(".pista").evaluate("""p => {
          const contenido = p.querySelector('.contenidoPista').getBoundingClientRect();
          const texto = p.querySelector('.texto.abierto').getBoundingClientRect();
          const dice = p.querySelector('.dice').getBoundingClientRect();
          const cortes = p.querySelector('.cortes').getBoundingClientRect();
          return {contenido: contenido.width, texto: texto.width, dice: dice.width,
                  altoDice: dice.height, accionesDebajo: cortes.top >= dice.bottom - 1,
                  scroll: document.documentElement.scrollWidth,
                  cliente: document.documentElement.clientWidth};
        }""")
        chequear("en el celular la transcripción sigue ocupando la tarjeta",
                 movil["texto"] > 320 and movil["texto"] > movil["contenido"] * 0.95,
                 str(movil))
        chequear("cada frase se puede leer sin formar una columna de letras",
                 movil["dice"] > 230 and movil["altoDice"] < 100, str(movil))
        chequear("los botones quedan debajo y no le roban ancho al texto",
                 movil["accionesDebajo"], str(movil))
        chequear("el arreglo no crea desplazamiento horizontal",
                 movil["scroll"] <= movil["cliente"] + 1, str(movil))
        pagina.screenshot(path=str(CAPTURA_MOVIL), full_page=True)
        chequear("no hubo errores de JavaScript", not errores, " | ".join(errores))
        navegador.close()

    print("\n" + ("TODO BIEN" if not FALLAS else "FALLARON %d" % len(FALLAS)))
    print("Capturas:", CAPTURA, "y", CAPTURA_MOVIL)
    return 1 if FALLAS else 0


if __name__ == "__main__":
    raise SystemExit(main())
