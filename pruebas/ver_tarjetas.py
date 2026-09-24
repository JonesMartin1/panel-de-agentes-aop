"""Cambiarle el color y el nombre a una tarjetita de la barra: proyecto o conversación.

Pedido de Martín (2026-08-18), después de la caja que abraza al grupo: *"me gustaría poder
cambiar las tarjetitas, tanto la de sesión como la de proyecto"*. Botón derecho encima de
cualquiera de las dos y sale un menú con seis tonos, "sin color", cambiarle el nombre y
cerrarla.

⚠ "Cambiar la tarjetita" era **la FORMA** (lo aclaró después: *"la forma de las tarjetas me
refería, pero me encanta que pueda elegir el color"*). Así que el menú tiene las dos cosas,
con una diferencia que importa: el COLOR es de esa tarjeta sola —para distinguirla— y la
FORMA vale para todas las de su clase —es cómo se ven las de proyecto o las de charla—.

Lo que fija esta prueba:
  * el menú sale con el botón derecho, en la pastilla y en la pestaña;
  * el color se aplica EN EL ACTO y sin cerrar el menú (probar tres tonos son tres clics);
  * las cuatro formas (redondeada, cuadrada, píldora, pestaña) y que cambiar la de las
    conversaciones NO toca las de proyecto;
  * la caja que abraza al grupo toma el color del proyecto;
  * ⭐ el SEMÁFORO sigue leyéndose en una tarjeta pintada: el puntito no se pinta nunca;
  * el nombre del proyecto se cambia SOLO en la pastilla — la carpeta del disco no se toca;
  * se acuerda entre visitas;
  * el ＋ no tiene menú propio: ahí sale el del navegador.

⚠ No toca nada real: las pestañas de la compu viven en el `localStorage` del navegador de
la prueba y la conversación se intercepta.

Correr con:  python -m pruebas.ver_tarjetas   (con el panel prendido)
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


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 700})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body='{"mensajes":[]}'))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)

        # Dos charlas de un mismo proyecto: así hay pastilla desplegada y pestañas.
        info = pag.evaluate("""() => {
          const a = datos.proyectos.find(p => p.sesiones.length >= 2);
          a.sesiones.slice(0, 2).forEach(s => abrirSesion(a.cwd, s.id, s.nombre));
          return {grupo: a.proyecto, sid: a.sesiones[0].id};
        }""")
        pag.wait_for_timeout(900)

        # --- El menú, en la pastilla del proyecto -----------------------------------
        pag.click("#tabs .grupo.abierto", button="right")
        pag.wait_for_timeout(350)
        revisar("con el botón derecho sale el menú de la tarjeta",
                pag.evaluate("() => document.getElementById('menuTarjeta')"
                             ".classList.contains('abierto')"), True)
        revisar("y dice de qué tarjeta es",
                pag.evaluate("() => document.querySelector('#menuTarjeta .rub').textContent"),
                "Proyecto")
        revisar("ofrece seis tonos más 'sin color'",
                pag.evaluate("() => document.querySelectorAll('#menuTarjeta .tono').length"), 7)
        pag.screenshot(path=str(SALIDA / "tarjetas_menu.png"),
                       clip={"x": 0, "y": 0, "width": 760, "height": 340})

        pag.click('#menuTarjeta .tono[data-tono="rosa"]')
        pag.wait_for_timeout(400)
        r = pag.evaluate("""() => ({
          pastilla: getComputedStyle(document.querySelector('#tabs .grupo.abierto')).backgroundColor,
          caja: getComputedStyle(document.getElementById('abrazo')).borderTopColor,
          menu: document.getElementById('menuTarjeta').classList.contains('abierto'),
          marcado: !!document.querySelector('#menuTarjeta .tono[data-tono="rosa"].sel')})""")
        revisar("el color pinta la pastilla en el acto", r["pastilla"], "rgb(51, 27, 40)")
        revisar("y la caja que la abraza toma ese mismo color", r["caja"], "rgb(107, 59, 83)")
        revisar("el menú se queda abierto, con el tono marcado",
                [r["menu"], r["marcado"]], [True, True])

        pag.click('#menuTarjeta .tono[data-tono=""]')
        pag.wait_for_timeout(350)
        revisar("'sin color' se lo saca",
                pag.evaluate("() => getComputedStyle(document.querySelector"
                             "('#tabs .grupo.abierto')).backgroundColor"), "rgb(26, 33, 48)")
        pag.click('#menuTarjeta .tono[data-tono="rosa"]')
        pag.wait_for_timeout(300)
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(250)
        revisar("y con Esc se cierra",
                pag.evaluate("() => document.getElementById('menuTarjeta')"
                             ".classList.contains('abierto')"), False)

        # --- Lo mismo en una conversación --------------------------------------------
        pag.click("#tabs .tab[data-i]", button="right")
        pag.wait_for_timeout(350)
        revisar("la pestaña de una conversación también tiene el suyo",
                pag.evaluate("() => document.querySelector('#menuTarjeta .rub').textContent"),
                "Conversación")
        pag.click('#menuTarjeta .tono[data-tono="arena"]')
        pag.wait_for_timeout(400)
        revisar("y se pinta igual",
                pag.evaluate("() => getComputedStyle(document.querySelector"
                             "('#tabs .tab[data-i]')).backgroundColor"), "rgb(43, 36, 24)")

        # --- ⭐ La rueda: cualquier otro color ----------------------------------------
        # Pedido de Martín (2026-08-18): "me gustaría poder agregar también colores
        # personalizados". Del color elegido salen los tres tonos de la tarjeta.
        pag.evaluate("""() => { const r = document.getElementById('tonoRueda');
          r.value = '#ff8a3d';
          r.dispatchEvent(new Event('input', {bubbles: true}));
          r.dispatchEvent(new Event('change', {bubbles: true})); }""")
        pag.wait_for_timeout(450)
        libre = pag.evaluate("""() => {
          const s = getComputedStyle(document.querySelector('#tabs .tab[data-i]'));
          return {fondo: s.backgroundColor, texto: s.color,
                  guardado: JSON.parse(localStorage.getItem('sesTonos') || '{}')};
        }""")
        revisar("la rueda pinta con el color que elijas", libre["texto"], "rgb(255, 138, 61)")
        revisar("y el fondo sale teñido de ese color, no plano",
                libre["fondo"], "rgb(55, 36, 26)")
        revisar("el color a mano se guarda tal cual",
                "#ff8a3d" in str(libre["guardado"]).lower(), True)
        # ⚠ Con un color OSCURO el texto se aclara solo: si no, letra negra sobre negro.
        pag.evaluate("""() => { const r = document.getElementById('tonoRueda');
          r.value = '#1a1a2e'; r.dispatchEvent(new Event('change', {bubbles: true})); }""")
        pag.wait_for_timeout(400)
        oscuro = pag.evaluate("() => getComputedStyle(document.querySelector"
                              "('#tabs .tab[data-i]')).color")
        r, g, b = [int(x) for x in oscuro[4:-1].split(",")]
        revisar("⭐ con un color oscuro, la letra se aclara sola para poder leerla",
                (r + g + b) / 3 > 120, True)
        pag.click('#menuTarjeta .tono[data-tono="arena"]')
        pag.wait_for_timeout(300)
        pag.keyboard.press("Escape")

        # --- ⭐ La FORMA de las tarjetas ----------------------------------------------
        # ⚠ La forma va por TIPO (todas las de proyecto / todas las de conversación), no
        # una por una: el color distingue una tarjeta de otra, la forma es cómo se ven las
        # de esa clase. El rótulo del menú lo dice.
        pag.click("#tabs .tab[data-i]", button="right")
        pag.wait_for_timeout(350)
        revisar("el menú ofrece las nueve figuras",
                pag.evaluate("() => [...document.querySelectorAll('#menuTarjeta .forma')]"
                             ".map(f => f.textContent)"),
                ["Redondeada", "Cuadrada", "Píldora", "Pestaña", "Hoja", "Arco",
                 "Cortada", "Flecha", "Cinta"])
        revisar("y el menú entero entra en la pantalla",
                pag.evaluate("""() => { const c = document.getElementById('menuTarjeta')
                                          .getBoundingClientRect();
                  return c.right <= innerWidth && c.bottom <= innerHeight; }"""), True)
        revisar("y avisa que la forma vale para todas las de esa clase",
                "Forma de todas las conversaciones" in pag.evaluate(
                    "() => [...document.querySelectorAll('#menuTarjeta .rub')]"
                    ".map(r => r.textContent).join(' ')"), True)
        for forma, radio in [("cuadrada", "0px"), ("pildora", "999px")]:
            pag.click(f'#menuTarjeta .forma[data-forma="{forma}"]')
            pag.wait_for_timeout(350)
            revisar(f"la forma {forma} se aplica a las pestañas",
                    pag.evaluate("() => getComputedStyle(document.querySelector"
                                 "('#tabs .tab[data-i]')).borderRadius"), radio)
        revisar("y las pastillas de proyecto NO se movieron",
                pag.evaluate("() => getComputedStyle(document.querySelector"
                             "('#tabs .grupo')).borderRadius"), "9px")
        pag.click('#menuTarjeta .forma[data-forma="pestana"]')
        pag.wait_for_timeout(350)
        revisar("la de pestaña recorta la tarjeta en trapecio",
                "polygon" in pag.evaluate("() => getComputedStyle(document.querySelector"
                                          "('#tabs .tab[data-i]')).clipPath"), True)
        pag.click('#menuTarjeta .forma[data-forma="redonda"]')
        pag.wait_for_timeout(300)
        pag.keyboard.press("Escape")

        # --- ⭐ El semáforo se sigue leyendo en una tarjeta pintada -------------------
        pag.evaluate("""s => { pendientes[s] = true; activa = null; guardar(); pintarTabs(); }""",
                     info["sid"])
        pag.wait_for_timeout(400)
        bola = pag.evaluate("""s => {
          const t = document.querySelector('#tabs .tab[data-sid="' + s + '"]');
          const b = t && t.querySelector('.bola');
          return {pintada: getComputedStyle(t).backgroundColor,
                  punto: b ? getComputedStyle(b).backgroundColor : 'no hay'};
        }""", info["sid"])
        revisar("una tarjeta pintada conserva su color", bola["pintada"], "rgb(43, 36, 24)")
        revisar("⭐ y el puntito del semáforo sigue verde igual",
                bola["punto"], "rgb(61, 220, 132)")
        pag.screenshot(path=str(SALIDA / "tarjetas_pintadas.png"),
                       clip={"x": 0, "y": 28, "width": 1100, "height": 72})
        pag.evaluate("s => { delete pendientes[s]; guardar(); pintarTabs(); }", info["sid"])

        # --- Cambiarle el nombre a la pastilla ---------------------------------------
        pag.once("dialog", lambda d: d.accept("Mi proyecto"))
        pag.click("#tabs .grupo.abierto", button="right")
        pag.wait_for_timeout(300)
        pag.click('#menuTarjeta [data-hace="nombre"]')
        pag.wait_for_timeout(600)
        revisar("la pastilla pasa a llamarse como vos quieras",
                "Mi proyecto" in pag.evaluate(
                    "() => document.querySelector('#tabs .grupo.abierto').textContent"), True)
        revisar("⚠ pero la carpeta del disco NO cambia de nombre",
                pag.evaluate("n => [...document.querySelectorAll('#carpetas .nom')]"
                             ".some(e => e.textContent.trim() === n)", info["grupo"]), True)

        # --- Se acuerda ---------------------------------------------------------------
        pag.reload(wait_until="domcontentloaded")
        pag.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)
        pag.wait_for_timeout(600)
        r = pag.evaluate("""n => {
          const g = [...document.querySelectorAll('#tabs .grupo')]
                      .find(x => x.dataset.grupo === n);
          return {fondo: getComputedStyle(g).backgroundColor,
                  dice: g.textContent.includes('Mi proyecto')};
        }""", info["grupo"])
        revisar("al volver, la tarjeta sigue pintada y con su nombre",
                [r["fondo"], r["dice"]], ["rgb(51, 27, 40)", True])

        # --- El ＋ no tiene menú propio ------------------------------------------------
        pag.click("#tabMas", button="right")
        pag.wait_for_timeout(300)
        revisar("el ＋ no se queda con el botón derecho",
                pag.evaluate("() => document.getElementById('menuTarjeta')"
                             ".classList.contains('abierto')"), False)

        pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                guardar(); localStorage.removeItem('sesTonos');
                                localStorage.removeItem('sesApodos');
                                localStorage.removeItem('sesFormas'); pintarTabs(); }""")
        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncapturas: {SALIDA / 'tarjetas_menu.png'} y tarjetas_pintadas.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
