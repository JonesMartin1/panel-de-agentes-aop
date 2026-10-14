"""La foto de fondo propia de una charla y de una carpeta (2026-10-10).

Pedido de Martín: *"me gustaría poder elegir la foto de atrás de cada sesión y carpeta de
proyectos también"*. Va en el mismo cuadro de los colores de la charla (colorcharla.js) y
manda igual que ellos:  lo de la charla  >  lo de su carpeta  >  la foto general (🎨).
La bandeja de UNA carpeta también muestra la foto de esa carpeta.

⚠ Todo `/charlas/**` se intercepta: así la prueba anda aunque el panel prendido sea uno
viejo sin `/charlas/foto`, y no le cambia la foto a ninguna charla de Martín.

Correr con:  python -m pruebas.ver_foto_charla   (con el panel prendido)
"""
import json
import struct
import sys
import zlib

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

BASE = "http://127.0.0.1:8750"
fallas = []

PROYECTOS = ["alfa", "beta"]
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": PROYECTOS, "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-" + str(k), "nombre": "charla " + str(k) + " de " + n,
                                         "ts": 10 - k, "ultimo": "vos", "viva": False,
                                         "interactiva": False, "detalle": "lo último dicho"}
                                        for k in range(3)]}
                          for n in PROYECTOS]}

FOTO_A = "/charlas/fondo/" + "a" * 20 + ".jpg"     # la de la charla alfa-1
FOTO_B = "/charlas/fondo/" + "b" * 20 + ".jpg"     # la de la carpeta beta
FOTO_N = "/charlas/fondo/" + "c" * 20 + ".jpg"     # la que "devuelve el servidor" al subir
COLORES = {"carpeta:d:/pruebas/beta": {"foto": FOTO_B}, "alfa-1": {"foto": FOTO_A}}


def png(ancho=40, alto=30):
    """Un PNG de verdad, chiquito, sin depender de Pillow."""
    filas = b"".join(b"\x00" + b"\x30\x80\xd0" * ancho for _ in range(alto))
    trozo = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(filas)) + trozo(b"IEND", b""))


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def foto(pag):
    """Qué foto propia tiene la página de fondo ahora ('' = la general o ninguna)."""
    return pag.evaluate("""() => {
      const v = getComputedStyle(document.documentElement).getPropertyValue('--fondo-img');
      const m = v.match(/\\/charlas\\/fondo\\/[^"')]+/);
      return m ? m[0] : '';
    }""")


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores = []
    mandados = []        # lo que la página le mandó a /charlas/foto y /charlas/color

    ctx.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    ctx.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"mensajes":[]}'))
    ctx.route("**/carpetas/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true}'))

    def charlas(r):
        url = r.request.url
        if "/charlas/colores" in url:
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"colores": COLORES}))
        if "/charlas/fondo/" in url:
            return r.fulfill(status=200, content_type="image/png", body=png())
        cuerpo = json.loads(r.request.post_data or "{}")
        if "/charlas/foto" in url:
            mandados.append(("foto", cuerpo.get("sid"), (cuerpo.get("img") or "")[:22]))
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "colores": {"foto": FOTO_N}}))
        mandados.append(("color", cuerpo))
        return r.fulfill(status=200, content_type="application/json", body='{"ok":true}')
    ctx.route("**/charlas/**", charlas)
    # ⚠ Desde el disco: un panel prendido desde antes del 2026-10-10 no lo tiene (404), y
    # la prueba es de este archivo, no de cuándo se reinició el panel.
    ctx.route("**/estaticos/colorcharla.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(RAIZ / "app" / "estaticos" / "colorcharla.js").read_text(encoding="utf-8")))

    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=8000)
    pag.wait_for_timeout(800)

    def aLaBandeja(carpeta="TODAS"):
        pag.evaluate("c => { activa = null; irProyecto(c === 'TODAS' ? TODAS : c); }", carpeta)
        pag.wait_for_timeout(400)

    def entrar(sid):
        aLaBandeja()
        pag.click("#cuerpo .correo[data-sid='" + sid + "']")
        pag.wait_for_timeout(600)

    revisar("en 'Todas' no hay foto propia", foto(pag), "")
    aLaBandeja("beta")
    revisar("⭐ la bandeja de la carpeta beta muestra su foto", foto(pag), FOTO_B)
    revisar("y la página pasa a modo foto (paneles translúcidos)",
            pag.evaluate("() => document.documentElement.classList.contains('con-foto')"), True)
    aLaBandeja("alfa")
    revisar("la carpeta alfa no tiene foto", foto(pag), "")

    entrar("beta-0")
    revisar("⭐ una charla de beta hereda la foto de su carpeta", foto(pag), FOTO_B)
    entrar("alfa-1")
    revisar("⭐ una charla con foto propia muestra la suya", foto(pag), FOTO_A)
    entrar("alfa-0")
    revisar("una charla sin foto, en carpeta sin foto: ninguna", foto(pag), "")
    aLaBandeja()
    revisar("al volver a 'Todas' se va la foto", foto(pag), "")

    # --- Elegir una foto desde el cuadro ----------------------------------------------
    entrar("alfa-0")
    pag.evaluate("() => ColorCharla.editor('alfa-0', null, cwdActiva())")
    pag.wait_for_selector(".cc-cuadro [data-k='foto']")
    revisar("el cuadro tiene la fila de la foto",
            pag.inner_text(".cc-cuadro [data-k='foto'] span"), "Foto de fondo · general")
    pag.set_input_files(".cc-cuadro [data-k='foto'] input[type=file]",
                        files=[{"name": "foto.png", "mimeType": "image/png", "buffer": png(2400, 300)}])
    pag.wait_for_timeout(1200)
    revisar("⭐ la sube achicada como JPEG, a nombre de esta charla",
            [m for m in mandados if m[0] == "foto"], [("foto", "alfa-0", "data:image/jpeg;base64")])
    revisar("⭐ y se ve en el acto", foto(pag), FOTO_N)
    revisar("el cuadro dice que es propia",
            pag.inner_text(".cc-cuadro [data-k='foto'] span"), "Foto de fondo · propia")
    mandados.clear()
    pag.click(".cc-cuadro [data-k='foto'] .cc-x")
    pag.wait_for_timeout(500)
    revisar("la × la saca en el servidor", mandados, [("color", {"sid": "alfa-0", "foto": ""})])
    revisar("y de la pantalla", foto(pag), "")
    pag.keyboard.press("Escape")

    # Con la charla de beta, la × vuelve a la de la carpeta (no a ninguna).
    entrar("beta-1")
    pag.evaluate("() => ColorCharla.editor('beta-1', null, cwdActiva())")
    pag.wait_for_selector(".cc-cuadro [data-k='foto']")
    revisar("en una charla de beta dice de dónde sale la foto",
            pag.inner_text(".cc-cuadro [data-k='foto'] span"), "Foto de fondo · de la carpeta")
    revisar("y la × está apagada (no hay foto propia que sacar)",
            pag.is_disabled(".cc-cuadro [data-k='foto'] .cc-x"), True)
    pag.keyboard.press("Escape")

    # --- Desde el menú de la carpeta (botón derecho) ----------------------------------
    aLaBandeja()
    pag.click("#carpetas .carpeta[data-proy='beta']", button="right")
    pag.wait_for_timeout(300)
    pag.click("#menuTarjeta [data-hace='fondo']")
    pag.wait_for_timeout(300)
    revisar("⭐ el botón derecho de la carpeta abre el cuadro de LA CARPETA",
            pag.inner_text(".cc-cuadro h4"), "Colores y foto de la carpeta beta")
    revisar("sin elegir 'esta charla' (no hay charla)",
            pag.locator(".cc-cuadro .cc-ambito").count(), 0)
    pag.keyboard.press("Escape")

    revisar("sin errores de JS", errores, [])
    nav.close()

print("")
print("todo bien" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
