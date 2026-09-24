"""La barra de arriba de `/sesiones` son DOS filas, no una.

Pedido de Martín (2026-08-18), mirando la barra llena de conversaciones: *"no me gusta
que las sesiones ocupen el mismo lugar que las pestañas, se me hace incómodo trabajar
así. Que las pestañas estén arriba"*. En su vocabulario las "pestañas" son las pantallas
del panel (Panel, Sesiones, Pizarra, Estudio, Avisos) y las "sesiones" son las
conversaciones abiertas. Así que:

    fila 1 (arriba)  el ◧ y el menú de pantallas — la chapa de la aplicación
    fila 2           las conversaciones, solas y a TODO lo ancho

Esto reemplaza a `ver_menu_achica.py`, que probaba lo contrario: cuando compartían
renglón, el menú se achicaba a iconos para hacerles lugar. Esa maquinaria sigue viva en
`menu.js` (`data-menu-rival`) por si alguna pantalla vuelve a compartir fila, pero hoy no
la usa ninguna y el menú se ve siempre entero.

⚠ No toca nada real: las pestañas de la compu viven solo en el `localStorage` del
navegador y al terminar se deja la barra como estaba.

Correr con:  python -m pruebas.ver_barra_dos_filas   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
ANCHO = 1500
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def cajas(pag):
    return pag.evaluate("""() => {
      const c = el => { const r = document.getElementById(el).getBoundingClientRect();
                        return {top: Math.round(r.top), abajo: Math.round(r.bottom),
                                izq: Math.round(r.left), der: Math.round(r.right),
                                alto: Math.round(r.height)}; };
      const t = document.getElementById('tabs');
      return {arriba: c('barraArriba'), abajo: c('barra'), menu: c('menuPantallas'),
              tabs: c('tabs'), anchoTabs: t.clientWidth,
              cortadas: t.scrollWidth > t.clientWidth,
              menuEntero: !document.getElementById('menuPantallas')
                            .classList.contains('compacto')};
    }""")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": ANCHO, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body='{"mensajes":[]}'))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=30000)
        pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                guardar(); pintarTabs(); }""")
        pag.wait_for_timeout(400)

        c = cajas(pag)
        revisar("el menú de pantallas va en la fila de ARRIBA",
                c["menu"]["abajo"] <= c["tabs"]["top"] + 1, True)
        revisar("y las conversaciones en la de abajo",
                c["tabs"]["top"] >= c["arriba"]["abajo"] - 1, True)
        revisar("las dos filas juntas no ocupan más que antes dos renglones de menú",
                c["abajo"]["abajo"] < 95, True)
        revisar("sin ninguna abierta, las conversaciones tienen toda la pantalla",
                c["anchoTabs"] >= ANCHO - 2, True)

        # --- Muchas conversaciones abiertas: siguen teniendo todo el ancho -------------
        # ⚠ Todas del MISMO proyecto y ese grupo desplegado: de proyectos distintos
        # quedarían plegadas en pastillas y no ocuparían lugar, que es para lo que sirven.
        hubo = pag.evaluate("""() => {
          const p = datos.proyectos.find(x => x.sesiones.length >= 4);
          if (!p) return 0;
          abiertas = p.sesiones.slice(0, 12).map((s, i) => ({sid: s.id, cwd: p.cwd,
                        nombre: 'Conversación bastante larga ' + (i + 1)}));
          activa = null; grupoAbierto = p.proyecto; guardar(); pintarTabs();
          return abiertas.length;
        }""")
        if hubo < 4:
            print("MAL  no hay ningún proyecto con cuatro conversaciones para probar")
            fallas.append("no había con qué armar la prueba")
        else:
            pag.wait_for_timeout(700)
            print(f"     (se abrieron {hubo} pestañas del mismo proyecto)")
            c = cajas(pag)
            revisar("con la barra llena, las conversaciones siguen teniendo todo el ancho",
                    c["anchoTabs"] >= ANCHO - 2, True)
            revisar("⭐ y el menú ya no se achica para hacerles lugar",
                    c["menuEntero"], True)
            revisar("se leen los nombres de las seis pantallas",
                    pag.evaluate("""() => [...document.querySelectorAll('#menuPantallas a .nom')]
                                     .filter(n => n.offsetParent).length"""), 6)
            revisar("ninguna conversación se mete en la fila del menú",
                    c["tabs"]["top"] >= c["menu"]["abajo"] - 1, True)
            pag.screenshot(path=str(SALIDA / "barra_dos_filas.png"),
                           clip={"x": 0, "y": 0, "width": ANCHO, "height": 110})

            # El ◧ sigue estando y sigue escondiendo la columna izquierda.
            pag.click("#btnLateral")
            pag.wait_for_timeout(400)
            revisar("el ◧ de la fila de arriba sigue escondiendo la columna",
                    pag.evaluate("() => document.body.classList.contains('lateral-oculto')"),
                    True)
            pag.click("#btnLateral")
            pag.wait_for_timeout(400)

            pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                    guardar(); pintarTabs(); }""")
            pag.wait_for_timeout(400)

        revisar("errores de javascript", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'barra_dos_filas.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
