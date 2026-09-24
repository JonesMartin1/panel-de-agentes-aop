"""Deslizar el dedo cambia de pestaña, PERO seleccionar texto para copiarlo no.

Martín, 2026-08-23: *"a veces estoy hablando en una sesión y me va transportando entre
varias sesiones"* y *"quiero copiar un texto desde el celular y no puedo porque cuando lo
quiero seleccionar a la izquierda o a la derecha me navega entre las pestañas"*.

Los dos síntomas eran el mismo gesto: el pase entre pestañas de la app del celular miraba
solo dónde empezó y dónde terminó el dedo (70 px y |dx|>|dy|), y marcar texto es también
arrastrar el dedo a los costados. Ahora se separan por CÓMO se hace el gesto: un pase es
rápido (menos de medio segundo), derecho y con un dedo; una selección es lenta, va y viene,
y deja texto marcado.

Corre el JS REAL de la app: se lee el `MOVIL_HTML` del `panel.py` del disco y se le
despachan toques de verdad (touchstart/touchmove/touchend) en un Chrome con pantalla de
teléfono. ⚠ Todos los endpoints están interceptados: no se toca ninguna sesión real.

Correr con:  python -m pruebas.probar_gesto_pestanas   (no hace falta el panel prendido)
"""
import ast
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
# Normalmente el panel.py del disco. Con PANEL_PY se le puede dar otro: asi se
# comprueba que esta prueba VE el bug viejo (se corre contra la version anterior
# sacada del git y tiene que salir en rojo). Una prueba que pasa con el codigo roto
# no prueba nada.
PANEL = Path(os.environ.get("PANEL_PY") or (RAIZ / "panel.py"))
BASE = "http://127.0.0.1:8750"
CWD = "D:\\pruebas\\alfa"
SID_1 = "charla-uno-0001"
SID_2 = "charla-dos-0002"
fallas = []

PESTANAS = {"pestanas": [{"sid": SID_1, "cwd": CWD, "nombre": "la uno"},
                         {"sid": SID_2, "cwd": CWD, "nombre": "la dos"}],
            "activa": SID_1}

CHARLA = {"mensajes": [
    {"de": "vos", "texto": "dame el comando"},
    {"de": "claude", "texto": "Corré esto: python -m app.voz.voz --sin-micro. "
                              "Es una linea larga a proposito, para tener texto que "
                              "seleccionar con el dedo de punta a punta de la pantalla."}]}

# El gesto de mentira: despacha toques de verdad sobre la pantalla, con sus tiempos.
# `pasos` son puntos {x, y, ms}: el primero es apoyar el dedo, el ultimo levantarlo.
GESTO = """
window.PRUEBA_gesto = async (pasos, ops) => {
  ops = ops || {};
  const blanco = document.querySelector(ops.sobre || '#cuerpo');
  const mk = (p, id) => new Touch({identifier: id, target: blanco,
                                   clientX: p.x, clientY: p.y});
  const ev = (tipo, lista, cambiados) => blanco.dispatchEvent(new TouchEvent(tipo, {
        touches: lista, targetTouches: lista, changedTouches: cambiados,
        bubbles: true, cancelable: true}));
  const dormir = ms => new Promise(r => setTimeout(r, ms));
  const dedos = ops.dedos || 1;
  const mano = p => { const l = [mk(p, 0)];
                      if (dedos > 1) l.push(mk({x: p.x + 40, y: p.y}, 1));
                      return l; };
  ev('touchstart', mano(pasos[0]), mano(pasos[0]));
  for (let i = 1; i < pasos.length; i++){
    await dormir(pasos[i].ms || 20);
    const t = mano(pasos[i]);
    if (i < pasos.length - 1) ev('touchmove', t, t);
    else ev('touchend', [], t);
  }
  await dormir(80);
};
// Marca texto de verdad en la pantalla, como cuando aparecen las manijitas.
window.PRUEBA_marcar = () => {
  const p = document.querySelector('#cuerpo .md, #cuerpo .correo, #cuerpo p, #cuerpo div');
  const r = document.createRange();
  r.selectNodeContents(p);
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  return String(s).trim().length > 0;
};
window.PRUEBA_soltar = () => window.getSelection().removeAllRanges();
"""


def html_del_panel(nombre):
    """Una pantalla embebida, sacada del `panel.py` del disco."""
    arbol = ast.parse(PANEL.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == nombre for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit(f"No encontre {nombre} en panel.py")


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


with sync_playwright() as p:
    # Usa el Chrome ya instalado: Playwright puede actualizar su paquete antes que
    # el navegador descargado y dejar las pruebas visuales sin ejecutable.
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 390, "height": 844},
                          has_touch=True, is_mobile=True, device_scale_factor=3)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))

    HTML = html_del_panel("MOVIL_HTML")

    def json_fijo(cuerpo):
        return lambda r: r.fulfill(status=200, content_type="application/json",
                                   body=json.dumps(cuerpo))

    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                              body=HTML))
    pag.route("**/movil/pestanas*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true}' if r.request.method == "POST" else json.dumps(PESTANAS)))
    pag.route("**/movil/sesiones*", json_fijo({"ok": True, "laura": "", "proyectos": [
        {"proyecto": "alfa", "cwd": CWD, "vivo": False, "sesiones": [
            {"id": SID_1, "nombre": "la uno", "ts": 2, "ultimo": "claude",
             "viva": False, "interactiva": False, "detalle": ""},
            {"id": SID_2, "nombre": "la dos", "ts": 1, "ultimo": "vos",
             "viva": False, "interactiva": False, "detalle": ""}]}]}))
    pag.route("**/movil/chat*", json_fijo(CHARLA))
    pag.route("**/movil/borradores*", json_fijo({}))
    pag.route("**/movil/borrador", json_fijo({"ok": True}))
    pag.route("**/movil/donde*", json_fijo({"ok": True}))
    pag.route("**/movil/modelo*", json_fijo({"ok": True, "modelo": "opus",
                                             "defecto": "opus", "modelos": [],
                                             "esfuerzo": "", "esfuerzos": []}))
    pag.route("**/pizarra*", lambda r: r.fulfill(status=200, content_type="text/html",
                                                 body="<html><body>pizarra</body></html>"))
    pag.route("**/status*", json_fijo({"servicios": {}, "encendido": False,
                                       "pausado": False, "pensando": False}))
    pag.route("**/sesion/cerebro*", json_fijo({"ok": True, "activo": "claude",
                                               "defecto": "claude", "cerebros": []}))
    pag.route("**/sesion/modelo*", json_fijo({"ok": True, "modelo": "opus"}))
    pag.route("**/chat", json_fijo({"items": []}))
    pag.route("**/gasto*", json_fijo({}))
    pag.route("**/marcas*", json_fijo({}))

    pag.add_init_script("localStorage.clear();")
    pag.add_init_script(GESTO)
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_timeout(1200)

    def donde():
        return pag.evaluate("() => activa")

    def parado_en(sid):
        pag.evaluate("sid => ir(sid)", sid)
        pag.wait_for_timeout(250)

    def gesto(pasos, **ops):
        pag.evaluate("([pasos, ops]) => PRUEBA_gesto(pasos, ops)", [pasos, ops])
        pag.wait_for_timeout(150)

    # Un pase de manual: rapido, derecho, un dedo. 120 px a la izquierda en ~120 ms.
    PASE_IZQ = [{"x": 300, "y": 400}, {"x": 250, "y": 402, "ms": 40},
                {"x": 200, "y": 401, "ms": 40}, {"x": 180, "y": 400, "ms": 40}]
    PASE_DER = [{"x": 80, "y": 400}, {"x": 130, "y": 402, "ms": 40},
                {"x": 180, "y": 401, "ms": 40}, {"x": 200, "y": 400, "ms": 40}]

    print("--- lo que TIENE que seguir andando -------------------------------------")
    parado_en(SID_1)
    revisar("arranca parado en la primera charla", donde(), SID_1)
    gesto(PASE_IZQ)
    revisar("un pase a la izquierda pasa a la charla siguiente", donde(), SID_2)
    gesto(PASE_DER)
    revisar("y uno a la derecha vuelve", donde(), SID_1)

    print("--- seleccionar texto para copiarlo NO puede cambiar de pestaña ----------")
    parado_en(SID_1)
    # Marcar texto es lento: el telefono pide medio segundo con el dedo apoyado antes
    # de mostrar las manijitas, y recien ahi uno arrastra.
    gesto([{"x": 300, "y": 400}, {"x": 290, "y": 401, "ms": 300},
           {"x": 240, "y": 402, "ms": 300}, {"x": 180, "y": 400, "ms": 300}])
    revisar("arrastrar despacio (marcando texto) no te mueve", donde(), SID_1)

    parado_en(SID_1)
    revisar("hay texto de verdad para marcar en la pantalla",
            pag.evaluate("() => PRUEBA_marcar()"), True)
    gesto(PASE_IZQ)
    revisar("con texto marcado, un pase rapido tampoco te mueve", donde(), SID_1)
    pag.evaluate("() => PRUEBA_soltar()")

    parado_en(SID_1)
    pag.evaluate("() => PRUEBA_marcar()")
    gesto(PASE_IZQ)
    revisar("y la seleccion sigue viva despues del gesto",
            pag.evaluate("() => String(window.getSelection()).trim().length > 0"), True)
    pag.evaluate("() => PRUEBA_soltar()")

    print("--- los otros gestos de la mano ------------------------------------------")
    parado_en(SID_1)
    # En L: bajas leyendo y despues te vas al costado. Mirando solo el punto final,
    # esto pasaba por pase.
    gesto([{"x": 300, "y": 300}, {"x": 302, "y": 420, "ms": 40},
           {"x": 250, "y": 415, "ms": 40}, {"x": 180, "y": 412, "ms": 40}])
    revisar("bajar y despues ir al costado (una L) es scroll, no pase", donde(), SID_1)

    parado_en(SID_1)
    gesto([{"x": 300, "y": 400}, {"x": 280, "y": 400, "ms": 40},
           {"x": 265, "y": 400, "ms": 40}, {"x": 260, "y": 400, "ms": 40}])
    revisar("un movimiento corto (40 px) no alcanza", donde(), SID_1)

    parado_en(SID_1)
    gesto(PASE_IZQ, dedos=2)
    revisar("con dos dedos (agrandando para leer) no cambia", donde(), SID_1)

    parado_en(SID_1)
    pag.evaluate("""() => { const pre = document.createElement('pre');
        pre.id = 'codigoLargo'; pre.textContent = 'python -m app.voz.voz --sin-micro';
        document.querySelector('#cuerpo').appendChild(pre); }""")
    gesto(PASE_IZQ, sobre="#codigoLargo")
    revisar("arrastrar dentro de un bloque de codigo lo desplaza a el, no cambia",
            donde(), SID_1)

    print("--- lo de antes que sigue en pie ----------------------------------------")
    pag.evaluate("() => ir('pizarra')")
    pag.wait_for_timeout(300)
    gesto(PASE_IZQ)
    revisar("en la pizarra el dedo mueve el lienzo, no la pestaña",
            donde(), "pizarra")

    revisar("sin errores de JS", errores, [])
    nav.close()

print()
if fallas:
    print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
    sys.exit(1)
print("todo bien")
