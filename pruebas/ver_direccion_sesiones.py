"""Cada conversación con su propia dirección web, en las dos pantallas.

Pedido de Martín (2026-08-18): "quiero que cada conversación tenga su propia dirección
web, para poder guardarla en favoritos y tener varias pestañas del navegador, cada una
en una conversación distinta. Al abrir una conversación la barra de direcciones tiene
que cambiar sola, y al entrar con esa dirección la app tiene que abrirse ya parada en
esa conversación. Vale para la app del celular y para la página de sesiones."

Lo que fija esta prueba:
  * al abrir una charla, la barra de direcciones pasa a `?c=<id>` sola;
  * ⭐ el TÍTULO de la página pasa a ser el nombre de la charla — de ahí sale el nombre
    del favorito y el de la pestaña del navegador; sin eso, seis pestañas dicen las seis
    "Sesiones" y el favorito no se distingue de ningún otro;
  * entrando con esa dirección DESDE CERO (un navegador que nunca vio esta página, o
    sea sin nada guardado) la charla se abre igual: la carpeta la resuelve el servidor;
  * dos pestañas del navegador, cada una en una conversación, no se pisan;
  * la flecha ← vuelve a la bandeja;
  * una dirección que apunta a algo borrado avisa en vez de no hacer nada;
  * lo mismo en la app del celular.

⚠ La conversación se INVENTA (`page.route` sobre `/movil/chat`) y el guardado de
pestañas del celular se bloquea: si no, quedaría una pestaña fantasma en el teléfono
de Martín.

Correr con:  python -m pruebas.ver_direccion_sesiones   (con el panel prendido)
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
INVENTADA = "00000000-1111-2222-3333-444444444444"
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                       {"de": "claude", "texto": "hola, te escucho", "imgs": []}]}
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def dos_sesiones():
    """Dos conversaciones de verdad para probar: (sid, cwd, nombre) cada una."""
    with urllib.request.urlopen(BASE + "/movil/sesiones", timeout=60) as r:
        d = json.loads(r.read())
    filas = [(s["id"], p["cwd"], s["nombre"])
             for p in d["proyectos"] for s in p["sesiones"] if not s["id"].startswith("nueva-")]
    if len(filas) < 2:
        print("No hay dos conversaciones en el disco para probar.")
        raise SystemExit(1)
    return filas[0], filas[1]


def sin_tocar_nada(pag):
    """La charla se inventa y no se le escribe a nadie."""
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))
    # ⚠ El celular guarda sus pestañas EN EL SERVIDOR: sin este corte, la prueba le
    # dejaría a Martín una pestaña abierta en el teléfono.
    pag.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"pestanas": [], "activa": "panel"}') if r.request.method == "GET"
        else r.fulfill(status=200, content_type="application/json", body='{"ok": true}'))


def main():
    (sid1, cwd1, nom1), (sid2, _, nom2) = dos_sesiones()
    print(f"probando con {nom1!r} y {nom2!r}\n")
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # ---------------------------------------------------------------- la compu
        ctx = nav.new_context(viewport={"width": 1300, "height": 850})
        pag = ctx.new_page()
        pag.on("pageerror", lambda e: errores.append(str(e)))
        sin_tocar_nada(pag)
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo", timeout=30000)
        revisar("la bandeja no ensucia la dirección", pag.evaluate("() => location.search"), "")

        # Abrir una conversación cambia la barra de direcciones y el título.
        pag.evaluate("([c, s, n]) => abrirSesion(c, s, n)", [cwd1, sid1, nom1])
        pag.wait_for_timeout(900)
        revisar("al abrir una charla, la dirección es la suya",
                pag.evaluate("() => location.search"), f"?c={sid1}")
        revisar("y el título de la pestaña del navegador es su nombre",
                pag.title(), f"{nom1} · Sesiones")

        # Recargar esa dirección: vuelve a la misma charla (acá la tiene guardada).
        pag.reload(wait_until="domcontentloaded")
        pag.wait_for_timeout(1500)
        revisar("recargando esa dirección se abre la misma charla",
                pag.evaluate("() => activa"), sid1)

        # ⭐ La prueba que importa: un navegador que NUNCA vio esta página (sin nada
        # guardado) entrando derecho por la dirección. Es el caso del favorito.
        limpio = nav.new_context(viewport={"width": 1300, "height": 850})
        pag2 = limpio.new_page()
        pag2.on("pageerror", lambda e: errores.append(str(e)))
        sin_tocar_nada(pag2)
        pag2.goto(f"{BASE}/sesiones?c={sid1}", wait_until="domcontentloaded")
        pag2.wait_for_function("() => activa", timeout=30000)
        revisar("desde cero, la dirección sola abre la charla",
                pag2.evaluate("() => activa"), sid1)
        revisar("y aparece como pestaña abierta",
                pag2.evaluate("() => abiertas.some(t => t.sid === arguments0)".replace(
                    "arguments0", json.dumps(sid1))), True)
        pag2.screenshot(path=str(SALIDA / "direccion_desde_cero.png"))

        # Dos pestañas del navegador, cada una en su conversación, sin pisarse.
        otra = limpio.new_page()
        otra.on("pageerror", lambda e: errores.append(str(e)))
        sin_tocar_nada(otra)
        otra.goto(f"{BASE}/sesiones?c={sid2}", wait_until="domcontentloaded")
        otra.wait_for_function("() => activa", timeout=30000)
        otra.wait_for_timeout(1200)
        revisar("la segunda pestaña abre LA SUYA", otra.evaluate("() => activa"), sid2)
        revisar("y la primera se quedó donde estaba", pag2.evaluate("() => activa"), sid1)
        revisar("cada una con su propio título",
                [pag2.title(), otra.title()], [f"{nom1} · Sesiones", f"{nom2} · Sesiones"])
        # ⚠ Las dos ventanas comparten el localStorage: la barra de pestañas es una sola
        # y tiene que quedar con las DOS charlas, no con la última que se abrió.
        pag2.wait_for_timeout(800)
        revisar("la barra de arriba junta las charlas de las dos ventanas",
                sorted(pag2.evaluate("() => abiertas.map(t => t.sid)")) ==
                sorted([sid1, sid2]), True)
        revisar("y ninguna se movió de la suya",
                [pag2.evaluate("() => activa"), otra.evaluate("() => activa")], [sid1, sid2])
        otra.close()

        # La flecha ← del navegador: de la charla, a la bandeja.
        pag.go_back()
        pag.wait_for_timeout(1200)
        revisar("la flecha ← vuelve a la bandeja",
                pag.evaluate("() => [location.search, activa]"), ["", None])
        revisar("y el título vuelve al de la pantalla", pag.title(), "Sesiones")

        # Una dirección que apunta a algo que ya no existe: lo dice.
        pag.goto(f"{BASE}/sesiones?c={INVENTADA}", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .choque", timeout=30000)
        revisar("una dirección borrada avisa en vez de no hacer nada",
                "ya no existe" in pag.inner_text("#cuerpo .choque"), True)
        revisar("y te deja en la bandeja igual", pag.evaluate("() => activa"), None)
        ctx.close(); limpio.close()

        # ---------------------------------------------------------------- el celular
        tel = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        cel = tel.new_page()
        cel.on("pageerror", lambda e: errores.append(str(e)))
        sin_tocar_nada(cel)
        cel.goto(f"{BASE}/movil?c={sid1}", wait_until="domcontentloaded")
        cel.wait_for_function("() => activa && activa !== 'panel'", timeout=30000)
        revisar("en el celular, la dirección también abre la charla",
                cel.evaluate("() => activa"), sid1)
        revisar("y el título es el de la charla", cel.title().endswith(" · Laura"), True)
        cel.screenshot(path=str(SALIDA / "direccion_movil.png"))

        # Y moviéndose adentro de la app, la dirección sigue sola.
        cel.evaluate("() => ir('pizarra')")
        cel.wait_for_timeout(600)
        revisar("yendo a otra pantalla, la dirección la sigue",
                cel.evaluate("() => location.search"), "?v=pizarra")
        cel.evaluate("s => ir(s)", sid1)
        cel.wait_for_timeout(600)
        revisar("y volviendo a la charla, vuelve a ser la suya",
                cel.evaluate("() => location.search"), f"?c={sid1}")
        tel.close()
        nav.close()

    revisar("errores de javascript", errores, [])
    print(f"\ncapturas: {SALIDA / 'direccion_desde_cero.png'} y direccion_movil.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
