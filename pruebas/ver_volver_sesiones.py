"""Volver a Sesiones desde otra pantalla del panel te deja donde estabas.

Pedido de Martín (2026-08-18): *"si estoy navegando por el panel y salgo de sesiones para
entrar a otra pestaña, cuando vuelva a sesiones quiero estar exactamente donde lo dejé"*.

⚠⚠ Esto convive con una decisión CONTRARIA que sigue en pie: *"siempre se entra por la
bandeja de Todas"* (2026-08-17). No se pisan porque no hablan del mismo momento: entrar de
cero —un favorito, el acceso del escritorio, la barra de direcciones— es venir a ver qué
hay; VOLVER desde otra pantalla del panel es seguir donde estabas. Se distinguen mirando
de dónde venís (`document.referrer`), y esta prueba fija las dos cosas.

Lo que fija:
  * salir a la Pizarra por el menú y volver por el menú devuelve la MISMA conversación y
    el MISMO renglón (el scroll), no la bandeja ni el final del hilo;
  * también la carpeta donde estabas parado y el filtro que habías escrito;
  * ⭐ entrando de cero (sin venir del panel) sigue abriendo la bandeja de Todas;
  * una dirección con conversación (`?c=…`) le gana a todo: si abriste ese link, es
    porque querés ir ahí.

⚠ La conversación se inventa y las pestañas viven en el `localStorage` del navegador de
la prueba: no toca nada real.

Correr con:  python -m pruebas.ver_volver_sesiones   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
# Una charla larga, para que haya scroll de verdad que devolver.
CHARLA = {"mensajes": [{"de": "claude" if i % 2 else "vos",
                        "texto": f"Renglón {i} de una conversación bien larga.", "imgs": []}
                       for i in range(60)]}
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def preparar(pag):
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))


def donde(pag):
    return pag.evaluate("""() => ({
      activa, proy, viendoArchivadas,
      scroll: Math.round(document.getElementById('cuerpo').scrollTop),
      filtro: (document.getElementById('filtro') || {}).value || ''})""")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1300, "height": 700})
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        preparar(pag)
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)

        # --- Una charla abierta, leída por la mitad ---------------------------------
        sid = pag.evaluate("""() => {
          const a = datos.proyectos.find(p => p.sesiones.length);
          abrirSesion(a.cwd, a.sesiones[0].id, a.sesiones[0].nombre);
          return a.sesiones[0].id; }""")
        pag.wait_for_selector("#cuerpo .msg", timeout=20000)
        pag.evaluate("() => { document.getElementById('cuerpo').scrollTop = 420; }")
        pag.wait_for_timeout(400)
        antes = donde(pag)
        revisar("arranco con una charla abierta y leída por la mitad",
                [antes["activa"] == sid, antes["scroll"] > 300], [True, True])

        # --- Me voy a la Pizarra POR EL MENÚ y vuelvo POR EL MENÚ -------------------
        # ⚠ Tiene que ser por el menú: es lo que deja el `referrer`, que es como se sabe
        # que estás navegando adentro del panel y no entrando de cero.
        pag.click('#menuPantallas a[href="/pizarra"]')
        pag.wait_for_timeout(1800)
        revisar("me fui a la pizarra", pag.evaluate("() => location.pathname"), "/pizarra")
        pag.click('#menuPantallas a[href="/sesiones"]')
        pag.wait_for_selector("#cuerpo .msg", timeout=30000)
        pag.wait_for_timeout(1200)
        vuelta = donde(pag)
        revisar("al volver, la misma conversación", vuelta["activa"], sid)
        revisar("⭐ y en el mismo renglón, no al final del hilo",
                abs(vuelta["scroll"] - antes["scroll"]) <= 12, True)
        pag.screenshot(path=str(SALIDA / "volver_sesiones.png"))

        # --- Lo mismo parado en una carpeta y con un filtro escrito -----------------
        carpeta = pag.evaluate("""() => {
          const p = datos.proyectos.find(x => x.sesiones.length);
          irProyecto(p.proyecto); return p.proyecto; }""")
        pag.wait_for_selector("#filtro", timeout=20000)
        pag.fill("#filtro", "re")
        pag.wait_for_timeout(500)
        pag.click('#menuPantallas a[href="/estudio"]')
        pag.wait_for_timeout(1600)
        pag.click('#menuPantallas a[href="/sesiones"]')
        pag.wait_for_selector("#filtro", timeout=30000)
        pag.wait_for_timeout(1400)
        v = donde(pag)
        revisar("vuelve a la carpeta donde estabas", v["proy"], carpeta)
        revisar("y con el filtro que habías escrito", v["filtro"], "re")

        # --- ⭐ Entrando DE CERO, la bandeja de siempre ------------------------------
        limpio = nav.new_context(viewport={"width": 1300, "height": 700})
        p2 = limpio.new_page()
        p2.on("pageerror", lambda e: errores.append(str(e)))
        preparar(p2)
        p2.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        p2.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)
        p2.wait_for_timeout(600)
        d2 = donde(p2)
        revisar("entrando de cero se abre la bandeja de Todas",
                [d2["activa"], d2["proy"]], [None, "✉ Todas las conversaciones"])

        # Y en ESA misma pestaña, una dirección con conversación le gana a todo.
        p2.goto(f"{BASE}/sesiones?c={sid}", wait_until="domcontentloaded")
        p2.wait_for_function("() => activa", timeout=30000)
        revisar("una dirección con conversación manda por encima de todo",
                p2.evaluate("() => activa"), sid)
        limpio.close()

        pag.evaluate("""() => { abiertas = []; activa = null; guardar();
                                localStorage.removeItem('sesSitio'); }""")
        revisar("errores de javascript", errores, [])
        ctx.close()
        nav.close()

    print(f"\ncaptura: {SALIDA / 'volver_sesiones.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
