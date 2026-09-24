"""Abrir una conversación te tiene que dejar SIEMPRE en lo último que se dijo.

Pedido de Martín (2026-08-17): "hay veces donde entro en una sesión y estoy en
cualquier lado de la conversación". La causa era que el contenedor conserva el scroll
de la pantalla anterior, y el pintado solo bajaba si YA estabas abajo.

Se prueba con una conversación inventada larga (se intercepta `/movil/chat`), porque
lo que importa es que haya bastante para scrollear. ⚠ No toca "Enviar": no arranca
ningún proceso `claude` ni escribe en ninguna sesión de verdad.

Correr con:  python -m pruebas.ver_scroll_sesiones   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
CWD = str(RAIZ)
fallas = []

# 60 idas y vueltas: alcanza de sobra para que la conversación no entre en pantalla.
CHARLA = {"mensajes": [
    {"de": ("vos" if i % 2 == 0 else "claude"), "imgs": [],
     "texto": (f"Mensaje número {i} de la charla de prueba.\n\n"
               f"Un párrafo más para que ocupe alto de verdad y haya que scrollear.")}
    for i in range(60)]}
CHARLA["mensajes"][-1]["texto"] = "ESTE ES EL ÚLTIMO MENSAJE DE LA CONVERSACIÓN."


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}{'' if ok else '  ' + detalle}")
    if not ok:
        fallas.append(que)


def falta(pag):
    """Cuánto falta para el final del todo, en píxeles. 0 = estás abajo de todo."""
    return pag.evaluate("() => { const c = document.getElementById('cuerpo');"
                        "  return Math.round(c.scrollHeight - c.scrollTop - c.clientHeight); }")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("() => { abiertas = []; activa = null; guardar(); pintarTabs(); pintar(); }")
        pag.wait_for_timeout(300)

        # --- Abrir una conversación: cae en el final ---
        pag.evaluate("c => abrirSesion(c, 'demo-scroll-a', 'Charla A')", CWD)
        pag.wait_for_timeout(1200)
        revisar("al abrirla, quedás al final", falta(pag) <= 4, f"faltan {falta(pag)} px")
        revisar("y se ve el último mensaje",
                pag.evaluate("() => document.querySelector('#cuerpo').innerText"
                             ".includes('ESTE ES EL ÚLTIMO MENSAJE')"), True)
        pag.screenshot(path=str(SALIDA / "sesiones_scroll_final.png"))

        # --- Te vas a leer arriba, saltás a otra pestaña y volvés: otra vez al final ---
        pag.evaluate("() => { document.getElementById('cuerpo').scrollTop = 0; }")
        pag.wait_for_timeout(300)
        revisar("subiendo a mano, te quedás arriba", falta(pag) > 500, f"faltan {falta(pag)} px")
        pag.evaluate("c => abrirSesion(c, 'demo-scroll-b', 'Charla B')", CWD)
        pag.wait_for_timeout(1000)
        revisar("la segunda pestaña también abre al final", falta(pag) <= 4, f"faltan {falta(pag)} px")
        pag.evaluate("() => irTab('demo-scroll-a')")
        pag.wait_for_timeout(1000)
        revisar("volviendo a la primera, otra vez al final", falta(pag) <= 4, f"faltan {falta(pag)} px")

        # --- Desde la bandeja scrolleada hacia abajo, abrir una charla ---
        pag.evaluate("() => irProyecto(datos.proyectos[0].proyecto)")
        pag.wait_for_timeout(800)
        revisar("entrando a una carpeta, la bandeja arranca arriba",
                pag.evaluate("() => document.getElementById('cuerpo').scrollTop") == 0)
        pag.evaluate("() => { document.getElementById('cuerpo').scrollTop = 400; }")
        pag.wait_for_timeout(200)
        pag.evaluate("c => abrirSesion(c, 'demo-scroll-c', 'Charla C')", CWD)
        pag.wait_for_timeout(1000)
        revisar("abriendo una charla desde la lista scrolleada, al final",
                falta(pag) <= 4, f"faltan {falta(pag)} px")

        pag.evaluate("() => { abiertas = []; activa = null; guardar(); }")
        revisar("sin errores de javascript", not errores, str(errores))
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_scroll_final.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
