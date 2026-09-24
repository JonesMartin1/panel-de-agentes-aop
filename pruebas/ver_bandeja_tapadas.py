"""La bandeja, vista de verdad: una conversación continuada se muestra UNA sola vez.

Pedido de Martín (2026-08-21) mirando el proyecto Farah: cuatro filas que en realidad
eran dos charlas, cada una duplicada con su continuación, y la que se había mudado a
Codex llamada "[Esta charla venia corriendo con Claude y Martin la acaba de".
*"Se ve y se siente feo trabajar así"*.

El servidor marca `tapada` en la charla vieja cuando su continuación está en la misma
lista (`sesiones_movil.listar`, probado sin navegador en `probar_bandeja_tapadas.py`).
Acá se mira lo otro: que las DOS pantallas —la compu y el celular— no la dibujen, no la
cuenten y no la manden a las archivadas.

⚠ No hace falta el panel prendido: las dos pantallas se sirven del disco (la del celular
sale del `MOVIL_HTML` de `panel.py`) y todos los pedidos están interceptados, así que no
se toca ninguna sesión real.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_bandeja_tapadas
"""
import ast
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8750"
CWD = "C:\\EspacioDeTrabajo\\Farah"
fallas = []

# La bandeja de Farah tal cual la contestaría el servidor con el arreglo puesto: dos
# conversaciones de verdad, cada una con su continuación. Las viejas vienen tapadas.
SESIONES = {
    "ok": True, "laura": "",
    "proyectos": [{"proyecto": "Farah", "cwd": CWD, "vivo": False, "sesiones": [
        {"id": "idea", "nombre": "Idea sobre el proyecto", "ts": 5, "viva": False,
         "interactiva": False, "ultimo": "claude", "detalle": "guardada, hace 5 h",
         "sigue_en": "continuacion", "tapada": True},
        {"id": "continuacion", "nombre": "Continuación Farah: validación demo",
         "ts": 8, "viva": False, "interactiva": False, "ultimo": "claude",
         "detalle": "guardada, hace 2 h"},
        {"id": "explicar", "nombre": "Explicar el proyecto", "ts": 6, "viva": False,
         "interactiva": False, "ultimo": "claude", "detalle": "guardada, hace 3 h",
         "sigue_en": "01a0-codex", "tapada": True},
        # La mudada: ya NO se llama como el texto del traspaso, hereda el nombre.
        {"id": "01a0-codex", "nombre": "Explicar el proyecto", "ts": 7, "viva": False,
         "interactiva": False, "ultimo": "claude", "cerebro": "codex",
         "detalle": "codex, hace 3 h"}]}]}

VISIBLES = ["Continuación Farah: validación demo", "Explicar el proyecto"]


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + que + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(que)


def movil_html():
    """El HTML del celular, sacado del `panel.py` del disco."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


def json_fijo(cuerpo):
    return lambda r: r.fulfill(status=200, content_type="application/json",
                               body=json.dumps(cuerpo))


def enchufar(pag, html, ruta_pagina):
    """Sirve la pantalla del disco y contesta todo lo que pida al arrancar."""
    pag.route(ruta_pagina, lambda r: r.fulfill(status=200, content_type="text/html",
                                               body=html))
    pag.route("**/estaticos/*", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(RAIZ / "app" / "estaticos" / r.request.url.split("/")[-1].split("?")[0])
        .read_text(encoding="utf-8")))
    pag.route("**/movil/sesiones*", json_fijo(SESIONES))
    pag.route("**/movil/pestanas*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true}' if r.request.method == "POST"
        else '{"pestanas": [], "activa": "panel"}'))
    pag.route("**/movil/borradores*", json_fijo({}))
    pag.route("**/movil/borrador", json_fijo({"ok": True}))
    pag.route("**/movil/chat*", json_fijo({"mensajes": []}))
    pag.route("**/movil/modelo*", json_fijo({"ok": True, "modelos": [], "esfuerzos": []}))
    pag.route("**/marcas*", json_fijo({}))
    pag.route("**/status*", json_fijo({"servicios": {}, "encendido": False,
                                       "pausado": False, "pensando": False}))
    pag.route("**/chat", json_fijo({"items": []}))
    pag.route("**/gasto*", json_fijo({}))
    pag.route("**/sesion/modelo*", json_fijo({"ok": False}))
    pag.route("**/sesion/cerebro*", json_fijo({"ok": True, "activo": "claude",
                                               "cerebros": []}))


def titulos(pag):
    """Los títulos de las filas que SON conversaciones (sin la de 'empezar una')."""
    return pag.eval_on_selector_all(
        ".correo[data-sid]:not([data-sid=''])",
        "l => l.map(f => f.querySelector('.tit').childNodes[0].textContent.trim())")


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)

    # --- 1. La pantalla grande (se sirve del disco: anda sin reiniciar el panel) -----
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    enchufar(pag, (RAIZ / "app" / "estaticos" / "sesiones.html").read_text(encoding="utf-8"),
             re.compile(r"/sesiones(\?.*)?$"))
    pag.add_init_script("localStorage.clear();")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector(".correo", timeout=8000)

    revisar("la compu dibuja una fila por conversación, no por continuación",
            sorted(titulos(pag)), sorted(VISIBLES))
    revisar("no queda ninguna chapa 'sigue en otra' a la vista",
            pag.eval_on_selector_all(".sigue", "l => l.length"), 0)
    revisar("el contador dice dos",
            pag.evaluate("() => ((document.querySelector('#cuerpo small')"
                         " || {}).textContent || '').trim().split(' ')[0]"), "2")
    revisar("la carpeta también cuenta dos",
            pag.evaluate("() => (document.querySelector('.carpeta[data-proy=\"Farah\"] .num')"
                         " || {}).textContent || ''"), "2")
    revisar("y la mudada sigue marcada como Codex",
            pag.eval_on_selector_all(".correo .cer", "l => l.map(c => c.textContent.trim())"),
            ["Codex"])
    revisar("sin errores de JS", errores, [])
    pag.screenshot(path=str(RAIZ / "resultados" / "bandeja_tapadas.png"))
    ctx.close()

    # --- 2. El celular (el MOVIL_HTML del panel.py del disco) ------------------------
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                          is_mobile=True, device_scale_factor=3)
    pag = ctx.new_page()
    errores_m = []
    pag.on("pageerror", lambda e: errores_m.append(str(e)))
    # ⚠ "**/movil" NO matchea "/movil?c=...": va con regex (lección del 2026-08-20).
    enchufar(pag, movil_html(), re.compile(r"/movil(\?.*)?$"))
    pag.add_init_script("localStorage.clear(); localStorage.setItem('activa','nueva');")
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_selector(".correo", timeout=8000)

    revisar("el celular dibuja las mismas dos", sorted(titulos(pag)), sorted(VISIBLES))
    revisar("tampoco muestra la chapa 'sigue en otra'",
            pag.eval_on_selector_all(".sigue", "l => l.length"), 0)
    revisar("sin errores de JS en el celular", errores_m, [])
    pag.screenshot(path=str(RAIZ / "resultados" / "bandeja_tapadas_movil.png"))
    ctx.close()
    nav.close()

print("\n" + ("todo bien" if not fallas else "FALLAN: " + ", ".join(fallas)))
sys.exit(1 if fallas else 0)
