"""Las marcas de la derecha de las carpetas, en columna (2026-10-10).

Pedido de Martín, con una captura: *"me da toc esto"*. El 🌐, el puntito de "algo vivo", el
número y la flechita de las subcarpetas se corrían según qué marcas tuviera cada renglón, y
los renglones sin color terminaban 14 px más allá que los pintados. Ahora cada marca tiene
su lugar fijo (vacío si no corresponde) y todos los renglones el mismo margen.

⚠ Datos inventados, interceptados en el contexto: no toca carpetas de Martín.

Correr con:  python -m pruebas.ver_marcas_en_columna   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"
fallas = []

# Cuatro carpetas con combinaciones distintas: con y sin vivo, con y sin charla trabajando
# (flechita), números de una y dos cifras.
PROYECTOS = ["alfa", "beta", "gama", "delta"]
CUANTAS = {"alfa": 1, "beta": 12, "gama": 3, "delta": 0}
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": PROYECTOS, "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": n in ("alfa", "gama"),
                           "sesiones": [{"id": n + "-" + str(k), "nombre": "charla " + str(k),
                                         "ts": 10 - k, "ultimo": "vos", "viva": False,
                                         "ocupada": n == "gama" and k == 0,
                                         "interactiva": False, "detalle": "x"}
                                        for k in range(CUANTAS[n])]}
                          for n in PROYECTOS]}


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores = []
    ctx.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    ctx.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"mensajes":[]}'))
    ctx.route("**/carpetas/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true}'))
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=8000)
    pag.wait_for_timeout(800)
    # Íconos propios en alfa y gama (así aparece el puntito de vivo), color en beta.
    pag.evaluate("() => { iconos.alfa = '🦊'; iconos.gama = '🐮'; pintarCarpetas(); }")
    pag.wait_for_timeout(200)

    def bordes(sel):
        """El borde derecho de esa marca en cada carpeta (None si no está)."""
        return pag.evaluate("""s => ['alfa','beta','gama','delta'].map(n => {
          const e = document.querySelector("#carpetas .carpeta[data-proy='" + n + "'] " + s);
          return e ? Math.round(e.getBoundingClientRect().right) : null; })""", sel)

    for nombre, sel in [("el número", ".num"),
                        ("el lugar del 🌐", ".naveg, .h-naveg"),
                        ("el lugar del puntito", ".vive, .h-vive"),
                        ("el lugar de la flechita", ".plegar, .h-plegar")]:
        b = bordes(sel)
        revisar("⭐ " + nombre + " queda a la misma altura en todas", len(set(b)) == 1 and None not in b, True)
        if len(set(b)) != 1:
            print("     bordes:", b)

    revisar("el borde derecho de los renglones es el mismo",
            len(set(pag.evaluate("""() => [...document.querySelectorAll('#carpetas .carpeta[data-proy]')]
              .map(e => Math.round(e.getBoundingClientRect().right))"""))), 1)
    revisar("solo gama tiene flechita de verdad",
            pag.evaluate("() => [...document.querySelectorAll('#carpetas [data-plegar]')].map(e => e.dataset.plegar)"),
            ["gama"])
    # Pasar el mouse no corre nada (ya no aparece ninguna ✕: sacar va por el botón derecho).
    antes = bordes(".num")
    pag.hover("#carpetas .carpeta[data-proy='beta']")
    pag.wait_for_timeout(250)
    revisar("al pasar el mouse no se mueve nada", bordes(".num"), antes)
    revisar("y el número sigue a la vista",
            pag.evaluate("() => getComputedStyle(document.querySelector(\"#carpetas .carpeta[data-proy='beta'] .num\")).visibility"),
            "visible")

    revisar("sin errores de JS", errores, [])
    nav.close()

print("")
print("todo bien" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
