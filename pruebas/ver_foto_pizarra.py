"""El 📋 de la barra de la pizarra: guardar como imagen lo elegido.

Pedido de Martín desde el teléfono (2026-08-23): *"¿podés poner 📋 en la tabla de
herramientas de la pizarra que sea para copiar?"* y, al preguntarle qué tenía que hacer,
*"¿y si me lo guarda como imagen en el celular?"*.

Lo que fija esta prueba:
  * el 📋 está en la barra y se ve en el teléfono;
  * la barra sigue entrando en DOS renglones (con 18 botones son 9 y 9 justos);
  * sin nada elegido guarda la pizarra ENTERA, y con objetos elegidos solo esos;
  * en el teléfono la foto se va por la hoja de compartir (que es el único camino a la
    galería del iPhone) y llega como un archivo `pizarra.png` de verdad;
  * cerrar la hoja de compartir no baja ningún archivo;
  * en la computadora no hay hoja de compartir: el archivo se baja derecho;
  * mientras dibuja, el botón avisa que está trabajando y después vuelve a la normalidad.

⚠ La pizarra vive DENTRO de `panel.py` (la constante `PAGINA_PIZARRA`), que el panel
prendido tiene cargada en memoria: acá se lee el `panel.py` **del disco** y se sirve desde
la prueba, así que esto mide lo de recién sin reiniciar el panel.

⚠ **No toca la pizarra de verdad**: el estado que ve la página es inventado y el dibujo
(`/pizarra/png`) está interceptado, así que no se crea, no se mueve y no se borra nada, ni
se levanta el navegador que dibuja los PNG.

Correr con:  python -m pruebas.ver_foto_pizarra    (no hace falta el panel prendido)
"""
import ast
import base64
import json
import re
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TELEFONO = {"width": 390, "height": 844}
COMPU = {"width": 1400, "height": 900}
fallas = []

# Un PNG de 1x1 de verdad: lo que devuelve el servidor de mentira cuando le piden el
# dibujo. Alcanza para que el navegador arme el File y lo comparta o lo baje.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QzwAEAAoAAf/nBeMAAAAASUVORK5CYII=")

# La pizarra inventada: tres objetos con la forma que devuelve /pizarra/estado.
ITEMS = [{"id": 101, "tipo": "rectangulo", "x1": 10, "y1": 10, "x2": 30, "y2": 25,
          "color": "#5eb8ff", "relleno": "", "bloqueado": False, "creado": 1},
         {"id": 102, "tipo": "rectangulo", "x1": 40, "y1": 10, "x2": 60, "y2": 25,
          "color": "#7ee787", "relleno": "", "bloqueado": False, "creado": 2},
         {"id": 103, "tipo": "rectangulo", "x1": 70, "y1": 10, "x2": 90, "y2": 25,
          "color": "#ffa657", "relleno": "", "bloqueado": False, "creado": 3}]
ESTADO = {"items": ITEMS, "fondo": "#0f1216",
          "coloresObjetos": ["#5eb8ff", "#7ee787", "#ffa657"],
          "coloresFondos": ["#0f1216", "#1a1f28"]}

# Lo que le pasa al navegador ANTES de cargar la página: la hoja de compartir de mentira.
# ⚠ `navigator.share` no existe en Chrome de escritorio, así que se define a mano.
COMPARTIR_OK = """
window.__compartido = [];
Object.defineProperty(navigator, 'canShare', {value: () => true, configurable: true});
Object.defineProperty(navigator, 'share', {configurable: true, value: async d => {
  const f = d.files[0];
  window.__compartido.push({nombre: f.name, tipo: f.type, bytes: f.size});
}});
"""
COMPARTIR_CANCELADO = """
window.__compartido = [];
Object.defineProperty(navigator, 'canShare', {value: () => true, configurable: true});
Object.defineProperty(navigator, 'share', {configurable: true, value: async () => {
  throw new DOMException('el usuario cerró la hoja', 'AbortError');
}});
"""


def pagina_pizarra():
    """El HTML de la pizarra, sacado del `panel.py` del disco (no del panel corriendo)."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "PAGINA_PIZARRA" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré PAGINA_PIZARRA en panel.py")


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + que + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(que)


HTML = pagina_pizarra()
ROUGH = (RAIZ / "app" / "estaticos" / "rough.js").read_text(encoding="utf-8")


def montar(ctx, pedidos):
    """Todo el servidor, inventado: la página, el estado y el dibujo del PNG."""
    ctx.route(re.compile(r"/pizarra$"), lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=HTML))
    ctx.route(re.compile(r"/pizarra/estado"), lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(ESTADO)))

    def dibujar(ruta):
        pedidos.append(ruta.request.url)
        ruta.fulfill(status=200, content_type="image/png", body=PNG)

    ctx.route(re.compile(r"/pizarra/png"), dibujar)
    # La librería del dibujo a mano alzada va de verdad (la de la carpeta), que es lo
    # que la página necesita para pintar; el resto de los `/estaticos/` no pinta nada
    # que esta prueba mire.
    ctx.route(re.compile(r"/pizarra/rough\.js"), lambda r: r.fulfill(
        status=200, content_type="application/javascript", body=ROUGH))
    ctx.route(re.compile(r"/estaticos/"), lambda r: r.fulfill(
        status=200, content_type="application/javascript", body=""))


def ids_pedidos(url):
    return sorted(int(x) for x in url.split("ids=")[1].split("&")[0].split(",") if x)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)

        # ---------------- 1) El teléfono ----------------
        pedidos = []
        ctx = nav.new_context(viewport=TELEFONO, has_touch=True, is_mobile=True,
                              device_scale_factor=3)
        ctx.add_init_script(COMPARTIR_OK)
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        bajados = []
        pag.on("download", lambda d: bajados.append(d.suggested_filename))
        montar(ctx, pedidos)
        pag.goto("http://localhost:8750/pizarra", wait_until="domcontentloaded")
        pag.wait_for_function("() => typeof estado !== 'undefined' && estado.items.length",
                              timeout=10000)

        revisar("el 📋 está en la barra y se ve",
                pag.evaluate("() => { const b=document.getElementById('btnFoto');"
                             " return !!(b && b.offsetParent && b.textContent.trim()==='📋'); }"),
                True)
        revisar("dice para qué sirve (no es un ícono mudo)",
                pag.evaluate("() => (document.getElementById('btnFoto').title||'')"
                             ".toLowerCase().includes('imagen')"), True)
        # Con 18 botones tienen que quedar dos renglones parejos: si entra un botón más,
        # la barra se va a tres filas y hay que achicarlos (está anotado en el CSS).
        filas = pag.evaluate("""() => {
          const bs=[...document.querySelectorAll('#toolbar button')].filter(b=>b.offsetParent);
          const arriba=[...new Set(bs.map(b=>b.offsetTop))].sort((a,b)=>a-b);
          return {renglones: arriba.length, botones: bs.length,
                  porRenglon: arriba.map(t => bs.filter(b=>b.offsetTop===t).length)};
        }""")
        revisar("la barra del teléfono sigue en dos renglones", filas["renglones"], 2)
        revisar("y los 18 botones quedan 9 y 9", filas["porRenglon"], [9, 9])

        # --- Sin nada elegido: la pizarra entera ---
        pag.click("#btnFoto")
        pag.wait_for_function("() => window.__compartido.length === 1", timeout=10000)
        revisar("sin elegir nada, guarda TODA la pizarra",
                ids_pedidos(pedidos[-1]), [101, 102, 103])
        compartido = pag.evaluate("() => window.__compartido[0]")
        revisar("llega a la hoja de compartir como pizarra.png",
                compartido["nombre"], "pizarra.png")
        revisar("y como imagen de verdad", compartido["tipo"], "image/png")
        revisar("con el dibujo adentro (no un archivo vacío)",
                compartido["bytes"] > 0, True)
        revisar("compartir NO baja además un archivo", bajados, [])
        revisar("el botón vuelve a la normalidad al terminar",
                pag.evaluate("() => { const b=document.getElementById('btnFoto');"
                             " return b.textContent.trim()+'|'+b.classList.contains('apagado'); }"),
                "📋|false")

        # --- Con dos objetos elegidos: solo esos ---
        pag.evaluate("() => { seleccion=new Set([101,103]); pintarSeleccion(); }")
        pag.click("#btnFoto")
        pag.wait_for_function("() => window.__compartido.length === 2", timeout=10000)
        revisar("con dos elegidos, guarda solo esos dos",
                ids_pedidos(pedidos[-1]), [101, 103])
        pag.evaluate("() => { seleccion.clear(); pintarSeleccion(); }")

        # --- Mientras dibuja, el botón avisa ---
        # ⚠ No se demora la red para mirarlo: se llama a la función y se lee el botón en
        # el MISMO turno, antes de que ningún `await` haya podido volver. Frenar el PNG
        # desde el interceptor bloquea también a la prueba (Playwright sincrónico atiende
        # las dos cosas en el mismo hilo) y el chequeo llegaba tarde, con el botón ya vuelto.
        revisar("mientras dibuja, el botón muestra que está trabajando",
                pag.evaluate("() => { const b=document.getElementById('btnFoto');"
                             " guardarComoFoto(b);"
                             " return b.textContent.trim()!=='📋' && b.classList.contains('apagado'); }"),
                True)
        pag.wait_for_function("() => window.__compartido.length === 3", timeout=10000)
        revisar("y al terminar vuelve a estar disponible",
                pag.evaluate("() => { const b=document.getElementById('btnFoto');"
                             " return b.textContent.trim()==='📋' && !b.classList.contains('apagado'); }"),
                True)
        revisar("la página no tiró ningún error", errores, [])
        pag.screenshot(path=str(RAIZ / "pruebas" / "pizarra_foto_movil.png"))
        ctx.close()

        # ---------------- 2) Cerrar la hoja de compartir no baja nada ----------------
        pedidos2 = []
        ctx2 = nav.new_context(viewport=TELEFONO, has_touch=True, is_mobile=True,
                               device_scale_factor=3, accept_downloads=True)
        ctx2.add_init_script(COMPARTIR_CANCELADO)
        pag2 = ctx2.new_page()
        bajados2 = []
        pag2.on("download", lambda d: bajados2.append(d.suggested_filename))
        montar(ctx2, pedidos2)
        pag2.goto("http://localhost:8750/pizarra", wait_until="domcontentloaded")
        pag2.wait_for_function("() => typeof estado !== 'undefined' && estado.items.length",
                               timeout=10000)
        pag2.click("#btnFoto")
        pag2.wait_for_timeout(1200)
        revisar("cerrar la hoja de compartir no baja ningún archivo", bajados2, [])
        revisar("y el botón queda listo para volver a intentarlo",
                pag2.evaluate("() => { const b=document.getElementById('btnFoto');"
                              " return b.textContent.trim()==='📋' && !b.classList.contains('apagado'); }"),
                True)
        ctx2.close()

        # ---------------- 3) La computadora: se baja el archivo ----------------
        pedidos3 = []
        ctx3 = nav.new_context(viewport=COMPU, accept_downloads=True)
        pag3 = ctx3.new_page()
        montar(ctx3, pedidos3)
        pag3.goto("http://localhost:8750/pizarra", wait_until="domcontentloaded")
        pag3.wait_for_function("() => typeof estado !== 'undefined' && estado.items.length",
                               timeout=10000)
        revisar("en la compu el 📋 también está", pag3.is_visible("#btnFoto"), True)
        with pag3.expect_download(timeout=10000) as bajada:
            pag3.click("#btnFoto")
        revisar("en la compu se baja el archivo derecho",
                bajada.value.suggested_filename, "pizarra.png")
        pag3.screenshot(path=str(RAIZ / "pruebas" / "pizarra_foto_barra.png"))
        ctx3.close()

        nav.close()

    print()
    if fallas:
        print("FALLARON %d: %s" % (len(fallas), ", ".join(fallas)))
        raise SystemExit(1)
    print("Todo bien.")


if __name__ == "__main__":
    main()
