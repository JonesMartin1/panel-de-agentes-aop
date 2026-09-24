"""Las perillas nuevas del 🎨 (2026-08-18: "me gustaría más configuración").

Lo que se agregó y esta prueba fija:
  * TAMAÑO DEL TEXTO de las conversaciones — cuatro pasos, y es un multiplicador:
    cada pantalla conserva su medida propia, la del celular sigue siendo más grande
    que la de la compu;
  * cuatro tipografías más (todas las que ya trae Windows: la app del celular tiene
    que abrir sin internet);
  * tres colores más y ⭐ una RUEDA para elegir cualquier otro, con el tono oscuro de
    las pastillas calculado solo;
  * CUÁNTO SE VE la foto de fondo (el velo negro de encima), que solo aparece cuando
    hay una foto puesta;
  * "volver a lo de fábrica", que deshace todo junto;
  * y que todo eso viaje al TELÉFONO, no solo al navegador donde se eligió (⚠ es lo
    que se rompe si se agrega un campo y no se lo suma a la lista blanca de `/aspecto`).

⚠ Deja el aspecto como estaba al terminar.

Correr con:  python -m pruebas.ver_config_aspecto   (con el panel prendido)
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
CHARLA = {"mensajes": [{"de": "vos", "texto": "una frase para medir", "imgs": []},
                       {"de": "claude", "texto": "otra frase para medir", "imgs": []}]}
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def guardado():
    with urllib.request.urlopen(BASE + "/aspecto", timeout=10) as r:
        return json.loads(r.read())


def poner(d):
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/aspecto", data=json.dumps(d).encode(), method="POST",
        headers={"Content-Type": "application/json"}), timeout=10).read()


def abrir_charla(pag):
    """Una conversación inventada, para poder medir la letra de las burbujas."""
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_timeout(1800)
    pag.evaluate("c => abrirSesion(c, 'demo-config', 'Prueba')", str(RAIZ))
    pag.wait_for_selector(".msg.vos", timeout=15000)


# ⚠ Desde los estilos (2026-08-29) el 🎨 tiene sus secciones PLEGADAS, y Playwright no
# clickea lo que no se ve: sin abrirlas, cada `elegir()` se queda esperando 30 s y muere.
# Se abren todas de una, que es lo mismo que hacía el panel antes de plegarse.
def abrir_secciones(pag):
    pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                 ".forEach(d => { d.open = true; })")
    pag.wait_for_timeout(120)


def elegir(pag, campo, valor):
    # ⚠ El 🎨 es un interruptor: si el panel ya quedó abierto de un paso anterior,
    # apretarlo otra vez lo CIERRA y después no hay nada que tocar.
    if not pag.evaluate("() => document.getElementById('aspectoPanel')"
                        ".classList.contains('abierto')"):
        pag.click("#aspectoBtn")
    pag.wait_for_timeout(300)
    abrir_secciones(pag)
    pag.click(f'#aspectoPanel .ops[data-campo="{campo}"] .op[data-v="{valor}"]')
    pag.wait_for_timeout(500)
    pag.keyboard.press("Escape")
    pag.click("body", position={"x": 5, "y": 5})
    pag.wait_for_timeout(200)


def letra(pag):
    return round(float(pag.evaluate(
        "() => getComputedStyle(document.querySelector('.msg.vos')).fontSize").replace("px", "")), 1)


def main():
    antes = guardado()
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1300, "height": 850})
        pag.on("pageerror", lambda e: errores.append(str(e)))

        poner({"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
               "letra": "normal", "velo": "media"})
        abrir_charla(pag)
        base = letra(pag)
        revisar("de fábrica, la burbuja de la compu mide lo de siempre", base, 13.6)

        # --- El tamaño del texto ---------------------------------------------------
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(400)
        revisar("el 🎨 ofrece elegir el tamaño del texto",
                pag.evaluate("() => !!document.querySelector"
                             "('#aspectoPanel .ops[data-campo=\"letra\"]')"), True)
        revisar("y ofrece volver a lo de fábrica",
                pag.evaluate("() => !!document.getElementById('aspFabrica')"), True)
        revisar("sin foto puesta, no pregunta cuánto se ve la foto",
                pag.evaluate("() => !!document.querySelector"
                             "('#aspectoPanel .ops[data-campo=\"velo\"]')"), False)
        pag.keyboard.press("Escape")
        pag.click("body", position={"x": 5, "y": 5})

        elegir(pag, "letra", "enorme")
        grande = letra(pag)
        revisar("en 'Enorme' la letra de la charla crece", grande > base + 3, True)
        elegir(pag, "letra", "chica")
        chica = letra(pag)
        revisar("y en 'Chica' se achica", chica < base, True)
        elegir(pag, "letra", "grande")

        # --- ⭐ Y viaja al teléfono (o sea: al servidor, no solo a este navegador) ---
        revisar("el tamaño queda guardado en el servidor", guardado().get("letra"), "grande")
        tel = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        tel.on("pageerror", lambda e: errores.append(str(e)))
        tel.goto(BASE + "/movil", wait_until="domcontentloaded")
        tel.wait_for_timeout(2200)
        escala = tel.evaluate("() => getComputedStyle(document.documentElement)"
                              ".getPropertyValue('--escala').trim()")
        revisar("y el celular lo toma sin que nadie se lo diga", escala, "1.14")
        tel.close()

        # --- La rueda de color ------------------------------------------------------
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(300)
        pag.evaluate("""() => {
          const r = document.getElementById('aspRueda');
          r.value = '#ff8a3d';
          r.dispatchEvent(new Event('input', {bubbles: true}));
          r.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        pag.wait_for_timeout(600)
        v = pag.evaluate("""() => ({
          acento: getComputedStyle(document.documentElement).getPropertyValue('--acento').trim(),
          bg: getComputedStyle(document.documentElement).getPropertyValue('--acento-bg').trim(),
          borde: getComputedStyle(document.querySelector('.msg.claude')).borderLeftColor})""")
        revisar("la rueda pinta con el color que elijas", v["acento"], "#ff8a3d")
        revisar("y ese color llega hasta la burbuja del chat", v["borde"], "rgb(255, 138, 61)")
        # El tono oscuro de las pastillas se calcula: tiene que ser oscuro y del mismo palo.
        r, g, b = [int(x) for x in v["bg"][4:-1].split(",")]
        revisar("el fondo del acento sale calculado y queda oscuro", r < 70 and r > b, True)
        revisar("y el color elegido a mano también se guarda en el servidor",
                guardado().get("color"), "#ff8a3d")
        pag.keyboard.press("Escape")
        pag.click("body", position={"x": 5, "y": 5})

        # --- Cuánto se ve la foto ---------------------------------------------------
        poner({"tipo": "segoe", "color": "celeste", "fondo": "azulado",
               "img": "/fondo/windows", "letra": "normal", "velo": "media"})
        abrir_charla(pag)
        velo = lambda: pag.evaluate("() => getComputedStyle(document.documentElement)"
                                    ".getPropertyValue('--fondo-img')")
        revisar("con foto puesta, aparece cuánto se ve",
                pag.evaluate("""() => { document.getElementById('aspectoBtn').click();
                  const hay = !!document.querySelector('#aspectoPanel .ops[data-campo="velo"]');
                  document.getElementById('aspectoPanel').classList.remove('abierto');
                  return hay; }"""), True)
        medio = velo()
        elegir(pag, "velo", "full")
        claro = velo()
        elegir(pag, "velo", "apenas")
        oscuro = velo()
        revisar("'se ve a full' tapa menos que 'media'",
                ("0.34" in claro) and ("0.62" in medio), True)
        revisar("y 'apenas' tapa más", "0.82" in oscuro, True)

        # --- Volver a lo de fábrica -------------------------------------------------
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(300)
        pag.click("#aspFabrica")
        pag.wait_for_timeout(700)
        revisar("volver a lo de fábrica deja todo como salió de la caja",
                {k: guardado().get(k) for k in ("tipo", "color", "fondo", "img", "letra", "velo")},
                {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
                 "letra": "normal", "velo": "media"})
        revisar("y la letra vuelve a la de siempre", letra(pag), 13.6)

        # --- Las tipografías nuevas -------------------------------------------------
        for clave, esperada in [("cambria", "Cambria"), ("candara", "Candara"),
                                ("calibri", "Calibri"), ("comic", "Comic Sans MS")]:
            elegir(pag, "tipo", clave)
            revisar(f"la tipografía {clave} se aplica",
                    esperada in pag.evaluate("() => getComputedStyle(document.body).fontFamily"),
                    True)

        pag.evaluate("() => { abiertas = []; activa = null; guardar(); }")
        pag.screenshot(path=str(SALIDA / "config_aspecto.png"))
        nav.close()

    poner(antes or {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": ""})
    revisar("errores de javascript", errores, [])
    print(f"\ncaptura: {SALIDA / 'config_aspecto.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
