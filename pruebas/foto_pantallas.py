"""Una foto de cada pantalla, para comparar el antes y el despues pixel a pixel.

No prueba nada por si sola: es el instrumento del cambio grande del 2026-08-29 (pasar los
grises escritos a mano a una escala de variables, para que exista el modo claro). La
promesa de ese cambio es fuerte y facil de romper sin darse cuenta: **en modo oscuro la
pantalla tiene que quedar EXACTAMENTE igual**. La unica forma honesta de sostenerlo es
fotografiar antes, convertir, fotografiar despues y comparar.

    python -m pruebas.foto_pantallas antes      # antes de tocar nada
    python -m pruebas.foto_pantallas despues    # con el cambio puesto
    python -m pruebas.foto_pantallas comparar   # cuantos pixeles cambiaron

Las fotos van a `pruebas/fotos/<tanda>/<pantalla>.png` y NO se versionan.

⚠ Las paginas se sirven del disco y todo lo demas se contesta vacio: esto mira colores,
no datos. Con datos inventados cada corrida dibujaria cosas distintas (la hora, cuanto
tarda una sesion) y la comparacion daria diferencias que no son del cambio.

⚠⚠ Tiene un piso de RUIDO y conviene saberlo antes de salir a cazar un fantasma: una vez
cada tanto aparecen unos pocos pixeles (se vieron 8) con una diferencia de 1/255, en el
borde de una letra. Es el suavizado de fuentes, que no siempre da igual. Si la diferencia
es de ese tamaño, REPETIR la comparacion antes de buscarle causa: pasó el 2026-08-29 y a
la segunda corrida dio cero. Una diferencia de verdad se ve en miles de pixeles y con
saltos grandes (los dos bugs reales de ese dia dieron 62.000 y 6.700, con 223/255).
"""
import ast
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
FOTOS = RAIZ / "pruebas" / "fotos"
# Sin foto de fondo y con el aspecto de fabrica: es el estado que tiene que quedar igual.
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
           "letra": "normal", "velo": "media", "rastro": "tema"}


def constante(nombre, fuente):
    for nodo in ast.parse(fuente).body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == nombre):
            return ast.literal_eval(nodo.value)
    raise SystemExit(f"No encontre {nombre} en panel.py")


def paginas():
    panel_py = (RAIZ / "panel.py").read_text(encoding="utf-8")
    return {"panel": constante("PAGINA", panel_py),
            "celular": constante("MOVIL_HTML", panel_py),
            "pizarra": constante("PAGINA_PIZARRA", panel_py),
            "sesiones": (ESTATICOS / "sesiones.html").read_text(encoding="utf-8")}


def montar(pag, html, aspecto):
    pag.route(f"{BASE}/**", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "items": [], "proyectos": [], "mensajes": [],
                         "servicios": {}})))
    pag.route(BASE + "/", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    pag.route("**/pizarra/rough.js", lambda r: r.fulfill(status=200, body=""))
    pag.route("**/fondo/**", lambda r: r.fulfill(status=200, body=""))
    for est in ("menu.js", "marcado.js", "atajos.js", "marcas.js", "direccion.js"):
        pag.route(f"**/estaticos/{est}", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=""))
    pag.route("**/estaticos/aspecto.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(ESTATICOS / "aspecto.js").read_text(encoding="utf-8")))
    pag.route("**/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(aspecto))
        if r.request.method == "GET" else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "aspecto": aspecto})))
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    # ⚠ Sin quedarse quieta la pantalla, dos fotos del MISMO codigo ya salen distintas:
    # hay animaciones que respiran. Se apaga el movimiento antes de disparar.
    pag.evaluate("document.documentElement.classList.add('movi-nada')")
    pag.wait_for_timeout(500)


def sacar(tanda, fondo="azulado"):
    destino = FOTOS / tanda
    destino.mkdir(parents=True, exist_ok=True)
    ASPECTO["fondo"] = fondo
    pags = paginas()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        for nombre, html in pags.items():
            ancho, alto = (430, 900) if nombre == "celular" else (1280, 900)
            pag = nav.new_page(viewport={"width": ancho, "height": alto})
            montar(pag, html, dict(ASPECTO))
            pag.screenshot(path=str(destino / f"{nombre}.png"))
            pag.close()
            print(f"  {nombre}.png")
        nav.close()
    print(f"fotos en {destino}")


def comparar():
    from PIL import Image, ImageChops
    a, b = FOTOS / "antes", FOTOS / "despues"
    if not a.is_dir() or not b.is_dir():
        raise SystemExit("faltan las tandas: corré primero 'antes' y despues 'despues'")
    peor = 0
    for foto in sorted(a.glob("*.png")):
        otra = b / foto.name
        if not otra.exists():
            print(f"MAL  {foto.name}: no está en 'despues'")
            peor = max(peor, 1)
            continue
        ia, ib = Image.open(foto).convert("RGB"), Image.open(otra).convert("RGB")
        if ia.size != ib.size:
            print(f"MAL  {foto.name}: cambió de tamaño {ia.size} -> {ib.size}")
            peor = max(peor, 1)
            continue
        dif = ImageChops.difference(ia, ib)
        caja = dif.getbbox()
        # Una sola pasada: leer los pixeles dos veces sobre una imagen grande es lento y
        # ademas `getdata()` esta en camino de desaparecer (Pillow 14).
        pixeles = list(getattr(dif, "get_flattened_data", dif.getdata)())
        distintos = sum(1 for px in pixeles if px != (0, 0, 0))
        maxdif = max((max(px) for px in pixeles), default=0)
        total = ia.size[0] * ia.size[1]
        estado = "ok  " if distintos == 0 else "MAL "
        print(f"{estado} {foto.name}: {distintos} de {total} píxeles distintos"
              + (f", el peor cambia {maxdif}/255, zona {caja}" if distintos else ""))
        peor = max(peor, distintos)
    print()
    print("IDÉNTICAS" if peor == 0 else "HAY DIFERENCIAS: mirá la zona que indica cada línea")
    return peor


if __name__ == "__main__":
    que = sys.argv[1] if len(sys.argv) > 1 else "antes"
    if que == "comparar":
        sys.exit(1 if comparar() else 0)
    # `python -m pruebas.foto_pantallas claro claro` = tanda "claro", con el tema claro.
    sacar(que, sys.argv[2] if len(sys.argv) > 2 else "azulado")
