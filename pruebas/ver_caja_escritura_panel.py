"""La caja de la PC crece al escribir y vuelve a un renglón al enviarse."""
import ast
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent


def pagina_panel():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(x, "id", "") == "PAGINA" for x in nodo.targets)):
            return nodo.value.value
    raise RuntimeError("No encontré PAGINA")


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    pag = nav.new_page(viewport={"width": 1280, "height": 800})
    pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pag.route("**/", lambda r: r.fulfill(status=200, content_type="text/html", body=pagina_panel()))
    pag.goto("http://127.0.0.1:8750/", wait_until="domcontentloaded")
    pag.fill("#txtChat", "Texto largo para comprobar que la caja crece. " * 15)
    pag.dispatch_event("#txtChat", "input")
    grande = pag.locator("#txtChat").evaluate("e => e.getBoundingClientRect().height")
    pag.evaluate("() => { const c=document.querySelector('#txtChat'); c.value=''; autoAlto(c); }")
    chico = pag.locator("#txtChat").evaluate("e => e.getBoundingClientRect().height")
    print(f"altos: grande={grande:.1f}, chico={chico:.1f}")
    assert grande > chico + 20, "la caja no creció"
    assert chico <= 42, "la caja no volvió a un renglón"
    print("ok   crece al escribir y se repliega al enviar")
    nav.close()
