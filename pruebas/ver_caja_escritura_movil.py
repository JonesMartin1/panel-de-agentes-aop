"""Regresión de la caja de escritura de /movil en un iPhone de 390 px."""
import ast
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent


def html_movil():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(x, "id", "") == "MOVIL_HTML" for x in nodo.targets)):
            return nodo.value.value
    raise RuntimeError("No encontré MOVIL_HTML")


fallas = []


def revisar(nombre, valor):
    print(("ok   " if valor else "MAL  ") + nombre)
    if not valor:
        fallas.append(nombre)


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    pag = nav.new_page(viewport={"width": 390, "height": 844})
    pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                           body="{}"))
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                               body=html_movil()))
    pag.goto("http://127.0.0.1:8750/movil", wait_until="domcontentloaded")
    pag.evaluate("""() => {
      const e=document.querySelector('#escribir'); e.style.display='flex';
      document.querySelector('#texto').value=''; ajustarCaja(document.querySelector('#texto'));
    }""")

    medidas = pag.evaluate("""() => {
      const e=document.querySelector('#escribir').getBoundingClientRect();
      const t=document.querySelector('#texto').getBoundingClientRect();
      return {campo:t.width, entra:e.right <= innerWidth + 1};
    }""")
    revisar("el campo conserva un ancho cómodo", medidas["campo"] >= 105)
    revisar("la barra entra completa en la pantalla", medidas["entra"])

    pag.fill("#texto", "Una frase larga para comprobar el crecimiento. " * 8)
    pag.dispatch_event("#texto", "input")
    alto_grande = pag.locator("#texto").evaluate("e => e.getBoundingClientRect().height")
    pag.evaluate("() => { const c=document.querySelector('#texto'); c.value=''; ajustarCaja(c); }")
    alto_chico = pag.locator("#texto").evaluate("e => e.getBoundingClientRect().height")
    print(f"altos: grande={alto_grande:.1f}, chico={alto_chico:.1f}")
    revisar("crece cuando el texto ocupa varias líneas", alto_grande > alto_chico + 20)
    revisar("vuelve a un renglón después de enviar", alto_chico < 55)
    nav.close()

if fallas:
    raise SystemExit("Falló: " + ", ".join(fallas))
