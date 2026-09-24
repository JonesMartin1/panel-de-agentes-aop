"""La compactacion se decide antes de seguir, tambien despues de recargar.

Sirve las dos pantallas desde el codigo del disco y simula una charla de Codex que
ya llenó la ventana. No toca sesiones reales ni consume tokens.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_pregunta_compactar
              (panel prendido en el puerto 8750)
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
SID = "compactar-4444-4444-444444444444"
PREGUNTA = ("Esta charla de Codex llegó al límite de contexto. ¿La compacto para "
            "rescatarla y seguir en una nueva? El hilo viejo queda entero acá.")
CHARLA = [{"de": "vos", "texto": "seguimos", "imgs": []},
          {"de": "claude", "texto": "Sí, pero antes elegí qué hacer con el contexto.",
           "imgs": []}]
SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["wpp"], "ocultas": []},
            "proyectos": [{"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False,
                           "sesiones": [{"id": SID, "nombre": "Charla larga", "ts": 2,
                                         "ultimo": "claude", "viva": False,
                                         "interactiva": False, "detalle": "",
                                         "cerebro": "codex"}]}]}

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
    # La bandeja también es inventada. Así la prueba no queda atada a una conversación
    # gigante que el panel real esté leyendo justo en ese momento.
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": False,
                         "pide_compactar": PREGUNTA,
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "cerebro": "codex", "modelo": "gpt-5.5",
                         "defecto": "gpt-5.5",
                         "modelos": [{"id": "gpt-5.5", "nombre": "GPT-5.5"}]})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/movil/novedad", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"cerebro":"codex","prompts":[],"carpeta":""}'))
    pag.route("**/carpetas/aspecto*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true,"carpetas":{},"iconosPropios":[],"choques":[]}'))


def estado(pag, boton):
    return pag.evaluate("""(boton) => ({
      pregunta: document.querySelector('.pideComp')?.innerText || '',
      caja: document.getElementById('texto').disabled,
      boton: document.getElementById(boton).disabled,
      ayuda: document.getElementById('texto').placeholder
    })""", boton)


def comprobar_bloqueo(pag, lugar, boton):
    pag.wait_for_selector(".pideComp", timeout=15000)
    e = estado(pag, boton)
    revisar(f"{lugar}: muestra la pregunta", PREGUNTA in e["pregunta"], True)
    revisar(f"{lugar}: bloquea la caja", e["caja"], True)
    revisar(f"{lugar}: bloquea Enviar", e["boton"], True)
    revisar(f"{lugar}: explica por que", "Elegí si querés compactar" in e["ayuda"], True)


def compu(nav):
    print("--- /sesiones (la compu) ---")
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof irTab === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.evaluate("""(sid) => {
      const p = datos.proyectos[0];
      abiertas = [{sid, cwd: p.cwd, nombre: 'Charla larga'}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
    }""", SID)
    comprobar_bloqueo(pag, "compu", "enviar")

    pag.reload(wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof irTab === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(800)
    comprobar_bloqueo(pag, "compu después de recargar", "enviar")

    pag.locator(".pideComp button.despues").click()
    pag.wait_for_function("() => !document.getElementById('texto').disabled")
    e = estado(pag, "enviar")
    revisar("compu: Ahora no destraba la caja", e["caja"], False)
    revisar("compu: Ahora no destraba Enviar", e["boton"], False)
    revisar("compu: Ahora no saca la pregunta", e["pregunta"], "")
    revisar("compu: sin errores de JS", errores, [])
    ctx.close()


def celular(nav):
    print("\n--- la app del celular ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    pag.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True} if r.request.method == "POST"
                        else {"pestanas": [{"sid": SID, "cwd": str(RAIZ),
                                             "nombre": "Charla larga", "virgen": False}],
                              "activa": SID})))
    pag.route("**/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=html_del_panel("MOVIL_HTML")))
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof ir === 'function'", timeout=30000)
    pag.wait_for_timeout(1200)
    pag.evaluate("""(sid) => {
      const cwd = (listaSes && (listaSes.proyectos || [])[0] || {}).cwd || 'D:\\\\IA';
      pestanas = [{sid, cwd, nombre: 'Charla larga', virgen: false}];
      guardar(); ir(sid);
    }""", SID)
    comprobar_bloqueo(pag, "celular", "mandar")

    pag.reload(wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof ir === 'function'", timeout=30000)
    pag.wait_for_timeout(1200)
    # Reabrimos la misma pestaña después de que terminó la restauración inicial. Lo que
    # se está probando no es el guardado de pestañas sino que el GET vuelva a traer la
    # decisión pendiente, aunque toda la memoria JS anterior haya desaparecido.
    pag.evaluate("""async ([sid, cwd]) => {
      pestanas = [{sid, cwd, nombre: 'Charla larga', virgen: false}];
      activa = sid;
      for (const k of Object.keys(cacheChat)) delete cacheChat[k];
      pideCompactar = {}; cargasChat = {}; firmaChat = {};
      guardar(); pintarTabs();
      const p = pestanas[0];
      const d = await pedirChat(p);
      guardarChat(p, d);
      dibujarSesion(p, d.mensajes);
    }""", [SID, str(RAIZ)])
    comprobar_bloqueo(pag, "celular después de recargar", "mandar")

    pag.locator(".pideComp button.despues").click()
    pag.wait_for_function("() => !document.getElementById('texto').disabled")
    e = estado(pag, "mandar")
    revisar("celular: Ahora no destraba la caja", e["caja"], False)
    revisar("celular: Ahora no destraba Enviar", e["boton"], False)
    revisar("celular: Ahora no saca la pregunta", e["pregunta"], "")
    revisar("celular: sin errores de JS", errores, [])
    ctx.close()


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        try:
            compu(nav)
            celular(nav)
        finally:
            nav.close()
    print("\n" + ("TODO BIEN" if not fallas else "FALLAN: " + ", ".join(fallas)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
