"""Si el envío rebota, lo que escribiste vuelve a la caja (y no se puede escribir a ciegas).

Bug que trajo Martín el 2026-08-23 desde el celular, con una captura: le escribió a una
sesión de Codex que todavía estaba contestando, le saltó el cartel *"Esa sesión está
contestando algo. Esperá a que termine y mandalo de nuevo"* — y el texto que había escrito
ya no estaba en ningún lado. Había que volver a escribirlo entero.

Dos arreglos, en las dos pantallas:
  * la caja se BLOQUEA mientras la sesión contesta y lo dice en el cartelito gris (la compu
    ya lo hacía; el celular no, y por eso lo dejaba mandar para rebotarlo después);
  * si igual rebota (el estado llegó viejo, se cortó la red), lo escrito VUELVE: a la caja
    si seguís parado ahí, y al borrador de esa charla siempre.

⚠ Nada de esto toca una sesión de verdad: `/movil/mandar` y `/movil/chat` están inventados
acá adentro. No se gasta un token.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_no_pierde_lo_escrito   (panel prendido)
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

SID = "ocupada-4444-4444-444444444444"
ESCRITO = "podemos ponerle el arma del modelo 3d?"
REBOTE = "Esa sesión está contestando algo. Esperá a que termine y mandalo de nuevo."
CHARLA = [{"de": "vos", "texto": "hola", "imgs": []},
          {"de": "claude", "texto": "el rig nuevo ya está funcionando", "imgs": []}]

fallas = []
ocupada = [False]          # lo que contesta /movil/chat en este momento


def esperar(pag, expr, ms=15000):
    """Esperar sin explotar: si no pasa, la prueba dice MAL y sigue (asi tambien sirve
    para comprobar que VE FALLAR a la version vieja, donde esto no anda)."""
    try:
        pag.wait_for_function(expr, timeout=ms)
        return True
    except Exception:
        return False


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
    """El envío SIEMPRE rebota, como cuando la sesión ya está contestando."""
    pag.route("**/movil/mandar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": False, "error": REBOTE})))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": ocupada[0],
                         "pregunta": None, "tareas": None})))
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
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(1500)
    pag.evaluate("""(sid) => {
      const p = datos.proyectos[0];
      abiertas = [{sid, cwd: p.cwd, nombre: 'La que rebota'}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
    }""", SID)
    pag.wait_for_timeout(800)

    # 1) la caja se bloquea sola mientras la sesión contesta
    ocupada[0] = True
    pag.evaluate("() => { firma = ''; }")
    esperar(pag, "() => document.getElementById('texto').disabled")
    est = pag.evaluate("() => ({bloq: $('#texto').disabled, dice: $('#texto').placeholder})")
    revisar("con la sesión contestando, la caja está bloqueada", est["bloq"], True)
    revisar("y el cartelito lo explica",
            "trabajando" in est["dice"] or "esperá" in est["dice"], True)

    # 2) se destraba sola cuando la sesión termina (no queda bloqueada para siempre)
    ocupada[0] = False
    pag.evaluate("() => { firma = ''; }")
    esperar(pag, "() => !document.getElementById('texto').disabled")
    revisar("cuando termina, la caja se destraba sola",
            pag.evaluate("() => $('#texto').disabled"), False)

    # 3) si igual rebota, lo escrito vuelve a la caja
    pag.evaluate("""(txt) => {
      const c = document.getElementById('texto');
      c.value = txt; c.dispatchEvent(new Event('input'));
      mandar();
    }""", ESCRITO)
    pag.wait_for_timeout(2500)
    est = pag.evaluate("""() => ({caja: $('#texto').value,
                                 falla: Object.keys(falladas).length > 0})""")
    revisar("** lo que escribiste volvió a la caja", est["caja"], ESCRITO)
    revisar("y la charla queda marcada como fallada", est["falla"], True)

    # 4) Un mensaje largo agranda la caja, pero al mandarlo tiene que volver a su alto
    # normal. Dejamos el pedido deliberadamente pendiente para medir el estado exacto que
    # mostró la captura de Martín: mensaje enviado, sesión trabajando y caja vacía.
    alto = pag.evaluate("""() => {
      const original = window.fetch;
      window.fetch = (url, opciones) => String(url).includes('/movil/mandar')
        ? new Promise(() => {}) : original(url, opciones);
      const c = document.getElementById('texto');
      c.value = ('una instrucción bastante larga para comprobar el alto de la caja. ').repeat(20);
      c.dispatchEvent(new Event('input'));
      const grande = c.getBoundingClientRect().height;
      mandar();
      return {grande, despues: c.getBoundingClientRect().height, valor: c.value};
    }""")
    revisar("el mensaje largo agrandó la caja", alto["grande"] > 100, True)
    revisar("** al mandarlo la caja volvió a ser compacta", alto["despues"] < 70, True)
    revisar("y quedó vacía", alto["valor"], "")
    revisar("sin errores de JS en la compu", errores, [])
    pag.context.close()


def celular(nav):
    print("\n--- la app del celular ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag)
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
    pag.evaluate("""(sid) => {
      const cwd = (listaSes && (listaSes.proyectos || [])[0] || {}).cwd || 'D:\\\\IA';
      pestanas = [{sid, cwd, nombre: 'La que rebota', virgen: false}];
      guardar(); ir(sid);
    }""", SID)
    pag.wait_for_timeout(1000)

    # 1) la caja se bloquea (esto en el celular no existía: te dejaba mandar y rebotaba)
    ocupada[0] = True
    pag.evaluate("() => { firmaChat[activa] = ''; pintarSesion(); }")
    esperar(pag, "() => document.getElementById('texto').disabled")
    est = pag.evaluate("() => ({bloq: $('#texto').disabled, "
                       "dice: $('#texto').placeholder, boton: $('#mandar').disabled})")
    revisar("en el celular la caja también se bloquea", est["bloq"], True)
    revisar("y el botón Enviar también", est["boton"], True)
    revisar("y el cartelito lo explica", "contestando" in est["dice"], True)

    # 2) se destraba sola
    ocupada[0] = False
    pag.evaluate("() => { firmaChat[activa] = ''; pintarSesion(); }")
    esperar(pag, "() => !document.getElementById('texto').disabled")
    revisar("y se destraba cuando la sesión termina",
            pag.evaluate("() => $('#texto').disabled"), False)

    # 3) si igual rebota, lo escrito vuelve
    pag.evaluate("""(txt) => {
      const c = document.getElementById('texto');
      c.value = txt; ajustarCaja(c);
      mandar();
    }""", ESCRITO)
    pag.wait_for_timeout(2500)
    revisar("** lo que escribiste volvió a la caja",
            pag.evaluate("() => $('#texto').value"), ESCRITO)
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
