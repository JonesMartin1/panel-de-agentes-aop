"""Los botones que esconden las barras de arriba de `/sesiones`.

Pedido de Martín (2026-08-18), en tres pasos:
  1. *"me gustaría poder ocultar cada sección individualmente"* → se hizo un menú 👁 con
     una tilde por franja y lo rechazó apenas lo vio: *"no me convence"*;
  2. *"quiero un botón simple para ocultar ambas, así tengo la pantalla del chat completa
     si así lo quisiera"* → el ⤢;
  3. *"un botón para cada una individualmente"* → además, el ☰ y el ⧉.
O sea que lo que no quería era ELEGIR EN UN MENÚ: un botón por cosa, a la vista y de un
toque, ofrece lo mismo y sí le sirve. Esta prueba reemplaza a `ver_secciones.py`.

Lo que fija:
  * el ☰ esconde el menú de pantallas y el ⧉ la fila de conversaciones, cada uno por su
    cuenta, y sus botones quedan tenues pero a la vista para volver a prenderlos;
  * el ⤢ esconde las dos barras juntas, de un toque;
  * ⭐⭐ escondidas, aparece el ⤡ flotando sobre la charla: es el ÚNICO camino de vuelta y
    tiene que estar SIEMPRE visible, no aparecer al pasar el mouse;
  * el Esc también vuelve;
  * la conversación de verdad gana el alto de las dos barras;
  * queda como lo dejaste entre visitas;
  * el ◧ y Ctrl+B siguen siendo otra cosa (la columna izquierda) y no se pisan.

⚠ No toca nada real: todo vive en el `localStorage` del navegador de la prueba.

Correr con:  python -m pruebas.ver_pantalla_completa   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def estado(pag):
    return pag.evaluate("""() => {
      // ⚠ Acá NO sirve `offsetParent`: para un elemento con `position:fixed` siempre da
      // null, así que el botón de volver figuraba escondido estando a la vista.
      const ve = id => {
        const e = document.getElementById(id);
        if (!e) return false;
        const s = getComputedStyle(e), r = e.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' &&
               r.width > 0 && r.height > 0;
      };
      const c = document.getElementById('cuerpo').getBoundingClientRect();
      const off = id => document.getElementById(id).classList.contains('off');
      return {barraArriba: ve('barraArriba'), barraTabs: ve('barra'),
              volver: ve('salirPleno'), botonPleno: ve('btnPleno'),
              menu: ve('menuPantallas'),
              botMenu: ve('btnMenu'), botTabs: ve('btnTabs'),
              menuApagado: off('btnMenu'), tabsApagado: off('btnTabs'),
              altoCharla: Math.round(c.height), arribaCharla: Math.round(c.top),
              columna: !document.body.classList.contains('lateral-oculto')};
    }""")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 820})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body='{"mensajes":[]}'))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=30000)

        antes = estado(pag)
        revisar("de entrada están las dos barras",
                [antes["barraArriba"], antes["barraTabs"]], [True, True])
        revisar("y el botón de volver no molesta a nadie", antes["volver"], False)

        # --- ⭐ Un botón para cada una, por separado ---------------------------------
        # ⚠ El ▭ esconde la barra de arriba ENTERA, no solo las pastillas de las pantallas:
        # "yo quiero que se oculte la barra entera, no solo las pestañas". Dejar la tira
        # vacía con los botones adentro no le devolvía a la conversación ni un pixel.
        pag.click("#btnMenu")
        pag.wait_for_timeout(350)
        e = estado(pag)
        revisar("el ▭ esconde la barra de arriba ENTERA",
                [e["barraArriba"], e["botMenu"], e["botTabs"]], [False, False, False])
        revisar("y la fila de conversaciones se queda donde estaba", e["barraTabs"], True)
        revisar("la conversación gana el lugar que ocupaba la barra",
                antes["altoCharla"] < e["altoCharla"], True)
        revisar("⭐ y aparece el ⤡ para traerla de vuelta", e["volver"], True)
        pag.click("#salirPleno")
        pag.wait_for_timeout(350)
        revisar("el ⤡ la devuelve", estado(pag)["barraArriba"], True)

        pag.click("#btnTabs")
        pag.wait_for_timeout(350)
        e = estado(pag)
        revisar("el ⧉ esconde SOLO la fila de conversaciones",
                [e["barraTabs"], e["barraArriba"]], [False, True])
        revisar("y su botón queda tenue pero a la vista, para volver a prenderlo",
                [e["tabsApagado"], e["botTabs"]], [True, True])
        # ⭐ Escondiendo las dos y volviendo con Esc, la fila de conversaciones sigue
        # escondida: si la sacaste vos, es porque la querés así. El ⤡ solo devuelve lo
        # que hace falta para volver a tener botones.
        pag.click("#btnMenu")
        pag.wait_for_timeout(300)
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(400)
        e = estado(pag)
        revisar("volviendo, la barra de arriba vuelve y lo tuyo se respeta",
                [e["barraArriba"], e["barraTabs"]], [True, False])
        pag.click("#btnTabs")
        pag.wait_for_timeout(400)
        e = estado(pag)
        revisar("y el ⧉ devuelve las conversaciones",
                [e["barraTabs"], e["tabsApagado"]], [True, False])

        # --- Un toque: se van las dos ------------------------------------------------
        pag.click("#btnPleno")
        pag.wait_for_timeout(400)
        e = estado(pag)
        revisar("el ⤢ esconde las DOS barras de una",
                [e["barraArriba"], e["barraTabs"]], [False, False])
        revisar("⭐ y deja a la vista el camino de vuelta", e["volver"], True)
        revisar("la conversación arranca arriba de todo", e["arribaCharla"] <= 2, True)
        revisar("y se queda con el alto de las dos barras",
                e["altoCharla"] > antes["altoCharla"] + 60, True)
        pag.screenshot(path=str(SALIDA / "pantalla_completa.png"))

        # ⭐ El botón de volver tiene que verse SIEMPRE, sin pasarle el mouse por encima.
        revisar("el ⤡ se ve sin tener que buscarlo con el mouse",
                pag.evaluate("""() => {
                  const b = document.getElementById('salirPleno');
                  const s = getComputedStyle(b);
                  return s.display !== 'none' && +s.opacity > .5 &&
                         s.visibility === 'visible';
                }"""), True)
        # y es él quien recibe el clic ahí arriba, no algo que le quede encima
        revisar("y nada se le pone encima",
                pag.evaluate("""() => {
                  const b = document.getElementById('salirPleno').getBoundingClientRect();
                  const q = document.elementFromPoint(b.left + b.width / 2,
                                                      b.top + b.height / 2);
                  return !!q && q.id === 'salirPleno';
                }"""), True)

        # --- Se acuerda --------------------------------------------------------------
        pag.reload(wait_until="domcontentloaded")
        pag.wait_for_timeout(1800)
        e = estado(pag)
        revisar("al volver sigue a pantalla completa",
                [e["barraArriba"], e["barraTabs"], e["volver"]], [False, False, True])

        # --- Y se sale, con el botón y con Esc ---------------------------------------
        pag.click("#salirPleno")
        pag.wait_for_timeout(400)
        e = estado(pag)
        revisar("el ⤡ devuelve las dos barras",
                [e["barraArriba"], e["barraTabs"], e["volver"]], [True, True, False])
        revisar("y el menú de pantallas vuelve entero",
                pag.evaluate("""() => [...document.querySelectorAll('#menuPantallas a .nom')]
                                 .filter(n => n.offsetParent).length"""), 6)
        pag.click("#btnPleno")
        pag.wait_for_timeout(300)
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(400)
        revisar("y con Esc también se vuelve", estado(pag)["barraArriba"], True)

        # --- La columna izquierda es OTRA cosa y no se pisan -------------------------
        pag.keyboard.press("Control+b")
        pag.wait_for_timeout(400)
        revisar("Ctrl+B sigue escondiendo solo la columna",
                [estado(pag)["columna"], estado(pag)["barraArriba"]], [False, True])
        pag.click("#btnPleno")
        pag.wait_for_timeout(400)
        e = estado(pag)
        revisar("con las dos cosas escondidas queda la charla sola",
                [e["columna"], e["barraArriba"], e["barraTabs"], e["volver"]],
                [False, False, False, True])
        pag.screenshot(path=str(SALIDA / "pantalla_completa_sin_columna.png"))
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(300)
        pag.keyboard.press("Control+b")
        pag.wait_for_timeout(300)

        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncapturas: {SALIDA / 'pantalla_completa.png'} y pantalla_completa_sin_columna.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
