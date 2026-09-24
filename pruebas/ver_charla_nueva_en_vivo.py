"""Una charla NUEVA se ve en vivo desde el primer turno, no cuando termina.

Bug que trajo Martín el 2026-08-23 con una captura del panel: abrió una pestaña nueva en
Portafolio, mandó una imagen con "quiero rediseñar mi portafolio para que se vea así", y la
pantalla se quedó siete minutos mostrando *"Sin mensajes todavía. Escribí abajo para
empezar."* con la burbuja de "pensando" — mientras la sesión ya venía contestando avances
cada dos minutos. Su pregunta fue "¿qué pasó con la sesión en la que estaba?".

La causa: la pestaña recién se enteraba del id de verdad cuando el turno ENTERO volvía.
Hasta entonces le preguntaba al servidor por el chat con el id vacío, y ahí no hay nada que
leer. Ahora el servidor publica el id apenas el CLI lo anuncia (`sid_nuevo` en la ficha del
trabajo) y la pestaña se muda en el acto.

⚠ Nada de esto toca una sesión de verdad: `/movil/mandar`, `/movil/trabajo/…` y
`/movil/chat` están INVENTADOS acá adentro. No se gasta un token.

Para comprobar que la prueba VE FALLAR a la versión vieja (una prueba que pasa con y sin el
arreglo no prueba nada):

    git show HEAD:app/estaticos/sesiones.html > D:/IA/tmp_viejo.html
    git show HEAD:panel.py > D:/IA/tmp_viejo_panel.py
    SESIONES_HTML=D:/IA/tmp_viejo.html PANEL_PY=D:/IA/tmp_viejo_panel.py \\
        D:/IA/envs/wpp/python.exe -m pruebas.ver_charla_nueva_en_vivo

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_charla_nueva_en_vivo   (panel prendido)
"""
import ast
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
SESIONES_HTML = Path(os.environ.get("SESIONES_HTML")
                     or (RAIZ / "app" / "estaticos" / "sesiones.html"))
PANEL_PY = Path(os.environ.get("PANEL_PY") or (RAIZ / "panel.py"))

NUEVA = "recien-nacida-3333-3333-333333333333"
VACIO = {"mensajes": [], "ocupada": False, "pregunta": None, "tareas": None}
# Lo que la sesión ya venía contestando mientras la pantalla mostraba el cartel de vacío.
VIVO = {"mensajes": [{"de": "vos", "texto": "quiero rediseñarlo así", "imgs": []},
                     {"de": "claude", "texto": "ya vi la referencia, voy con esto",
                      "imgs": []}],
        "ocupada": True, "pregunta": None, "tareas": None}

fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def html_del_panel(nombre):
    arbol = ast.parse(PANEL_PY.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == nombre for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit(f"No encontre {nombre} en {PANEL_PY}")


def servidor_falso(pag):
    """El turno queda PENSANDO para siempre, con la charla ya nacida y contestando."""
    pag.route("**/movil/mandar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "segundo_plano": True, "trabajo": "t1"})))
    # La ficha del trabajo: sigue trabajando, pero el id de la charla YA existe.
    pag.route("**/movil/trabajo/t1", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "estado": "trabajando", "cwd": "X", "sid": "",
                         "sid_nuevo": NUEVA, "respuesta": "", "error": ""})))
    # El chat solo tiene mensajes si se lo pide POR EL ID DE VERDAD. Con el id vacío
    # —lo que hacía la pantalla vieja durante todo el primer turno— no hay nada.
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(VIVO if ("sid=" + NUEVA) in r.request.url else VACIO)))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "opus", "defecto": "opus",
                         "modelos": [{"id": "opus", "nombre": "Opus"}]})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))


def compu(nav):
    print("--- /sesiones (la compu) ---")
    pag = nav.new_context(viewport={"width": 1400, "height": 900}).new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(1500)
    pag.evaluate("""() => {
      const p = datos.proyectos[0];
      abiertas = [{sid: 'nueva-envivo', cwd: p.cwd, nombre: 'Recién nacida'}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab('nueva-envivo');
    }""")
    pag.wait_for_timeout(700)
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'quiero rediseñarlo así';
      mandar();
    }""")
    # La ficha se consulta cada 1,2 s: en 8 s la pestaña ya tendría que haberse mudado.
    try:
        pag.wait_for_function("(n) => abiertas.some(t => t.sid === n)", arg=NUEVA,
                              timeout=8000)
    except Exception:
        pass
    pag.wait_for_timeout(1200)
    est = pag.evaluate("""(n) => {
      const hilo = document.getElementById('hilo');
      const texto = hilo ? hilo.innerText : '';
      return {mudo: abiertas.some(t => t.sid === n), activa,
              ve: texto.includes('voy con esto'),
              vacio: texto.includes('Sin mensajes todavía'),
              pensando: !!document.querySelector('#hilo .pensa')};
    }""", NUEVA)
    revisar("la pestaña se mudó al id de verdad en plena pensada", est["mudo"], True)
    revisar("y sigo parado en ella", est["activa"], NUEVA)
    revisar("** VE lo que la sesión está contestando", est["ve"], True)
    revisar("** y ya no dice 'Sin mensajes todavía'", est["vacio"], False)
    revisar("la burbuja de pensando sigue puesta (el turno no terminó)",
            est["pensando"], True)
    revisar("sin errores de JS en la compu", errores, [])
    pag.context.close()


def celular(nav):
    print("\n--- la app del celular ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    # ⚠ Las pestañas del teléfono viven en el servidor: sin tapar esto, la prueba le
    # movería a Martín las de su celular de verdad.
    pag.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True} if r.request.method == "POST"
                        else {"pestanas": [], "activa": "panel"})))
    pag.route("**/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=html_del_panel("MOVIL_HTML")))
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function'", timeout=30000)
    pag.wait_for_timeout(2000)
    pag.evaluate("""() => {
      const cwd = (listaSes && (listaSes.proyectos || [])[0] || {}).cwd || 'D:\\\\IA';
      pestanas = [{sid: 'nueva-envivo', cwd, nombre: 'Recién', virgen: true}];
      guardar(); ir('nueva-envivo');
    }""")
    pag.wait_for_timeout(700)
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'quiero rediseñarlo así';
      mandar();
    }""")
    try:
        pag.wait_for_function("(n) => pestanas.some(p => p.sid === n)", arg=NUEVA,
                              timeout=8000)
    except Exception:
        pass
    pag.wait_for_timeout(1200)
    est = pag.evaluate("""(n) => ({
      mudo: pestanas.some(p => p.sid === n),
      ve: document.body.innerText.includes('voy con esto'),
      vacio: document.body.innerText.includes('Sin mensajes todavía')})""", NUEVA)
    revisar("en el celular también se muda en plena pensada", est["mudo"], True)
    revisar("** y ve lo que la sesión está contestando", est["ve"], True)
    revisar("** sin el cartel de charla vacía", est["vacio"], False)
    revisar("sin errores de JS en el celular", errores, [])
    ctx.close()


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        try:
            compu(nav)
            celular(nav)
        finally:
            nav.close()
    print("\n" + ("todo bien" if not fallas else "FALLAN: " + ", ".join(fallas)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
