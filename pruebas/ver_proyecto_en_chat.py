"""Adentro de una charla del celular tiene que verse DE QUÉ PROYECTO es.

Pedido de Martín (2026-08-17): "me molesta no ver acá a qué proyecto pertenece este
chat". En la compu se ve por la carpeta marcada a la izquierda; en el teléfono no hay
nada, y con varias conversaciones abiertas uno le termina escribiendo a la equivocada.

Lo que fija esta prueba:
  * al lado del nombre de la charla aparece el proyecto, como chapita;
  * sale de la CARPETA que guarda la pestaña, así que también funciona con un proyecto
    que no esté en la lista de arriba;
  * se ve como chapita y no como parte del título (que va en mayúsculas).

⚠ La conversación se intercepta y el guardado de pestañas también: no toca ninguna
sesión de verdad.

Correr con:  python -m pruebas.ver_proyecto_en_chat   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                       {"de": "claude", "texto": "Listo, ya está.", "imgs": []}]}
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        pag.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}")
            if r.request.method == "POST" else r.continue_())
        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        pag.wait_for_timeout(2200)

        pag.evaluate("c => abrir(c, 'demo-proyecto', 'Interfaz')", str(RAIZ))
        pag.wait_for_timeout(1600)
        chapa = "() => (document.querySelector('#titulo .eti')||{}).textContent"
        revisar("se ve el proyecto de la charla", pag.evaluate(chapa), "wpp-transcriptor")
        estilo = pag.evaluate("""() => { const s = getComputedStyle(
              document.querySelector('#titulo .eti'));
            return {fondo: s.backgroundColor, mayusculas: s.textTransform}; }""")
        revisar("como chapita, con su fondo", estilo["fondo"] != "rgba(0, 0, 0, 0)", True)
        revisar("y sin las mayúsculas del título", estilo["mayusculas"], "none")
        pag.screenshot(path=str(SALIDA / "movil_proyecto_en_chat.png"),
                       clip={"x": 0, "y": 0, "width": 390, "height": 240})

        # Una carpeta que NO está en la lista de proyectos: igual tiene que decirlo,
        # porque el nombre sale de la ruta que guarda la pestaña.
        pag.evaluate("() => abrir('C:/Trabajo/ProyectoInventado', 'demo-2', 'Otra')")
        pag.wait_for_timeout(1400)
        revisar("y también con una carpeta que no está en la lista",
                pag.evaluate(chapa), "ProyectoInventado")

        pag.evaluate("() => { pestanas = []; guardar(); }")
        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'movil_proyecto_en_chat.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
