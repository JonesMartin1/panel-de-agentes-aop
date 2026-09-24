"""Mandar un mensaje y salir de la charla: la respuesta NO te tiene que arrastrar de vuelta.

Bug que reportó Martín el 2026-08-23: *"cuando yo mando un mensaje a un chat, a veces salgo
de ese chat mientras está pensando y me lleva directamente a ese chat cuando me devuelve la
primera respuesta, eso está re mal"*.

El "a veces" era exacto: pasaba SOLO en el primer mensaje de una charla nueva, que es el
único momento en que la conversación cambia de id (de `nueva-…` al de verdad). Al volver la
respuesta, `mandar()` hacía `activa = r.sid` a secas y te metía adentro, estuvieras donde
estuvieras. Compactar y mudar de cerebro ya lo hacían bien (`if (activa === viejo)`); esto
era el único que faltaba.

Lo que fija, en las DOS pantallas (`/sesiones` y la app del celular):
  * si te fuiste, seguís donde estás: la charla se muda de id igual, pero sola;
  * y queda marcada como pendiente en la compu, para que la veas y entres vos;
  * la barra de direcciones tampoco salta a la charla que ya no estás mirando;
  * ⭐ y el caso normal sigue andando: si te quedaste, la pestaña sigue siendo la activa —
    si no, el arreglo habría roto lo que sí funcionaba.

⚠ Nada de esto toca una sesión de verdad: `/movil/mandar`, `/movil/chat` y los borradores
están INVENTADOS acá adentro. Mandar de verdad sería un turno contra una charla de Martín.
⚠ La app del celular vive dentro de `panel.py` (`MOVIL_HTML`), que el panel prendido tiene
en memoria: se le sirve la del DISCO para poder correr esto sin reiniciarlo.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_no_secuestra_chat   (panel prendido)
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
# ⭐ Normalmente las pantallas del disco. Con estas dos variables se le puede dar otra
# versión, y así se comprueba que la prueba VE FALLAR a la vieja — una prueba que pasa
# con y sin el arreglo no prueba nada (la lección de `probar_gesto_pestanas.py`):
#   git show HEAD:app/estaticos/sesiones.html > /tmp/viejo.html
#   SESIONES_HTML=/tmp/viejo.html PANEL_PY=/tmp/viejo_panel.py python -m pruebas.ver_no_secuestra_chat
SESIONES_HTML = Path(os.environ.get("SESIONES_HTML")
                     or (RAIZ / "app" / "estaticos" / "sesiones.html"))
PANEL_PY = Path(os.environ.get("PANEL_PY") or (RAIZ / "panel.py"))


def html_del_panel(nombre):
    """Una pantalla embebida, sacada del `panel.py` que se esté probando."""
    arbol = ast.parse(PANEL_PY.read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == nombre for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit(f"No encontre {nombre} en {PANEL_PY}")
OTRA = "otra-prueba-0000-0000-000000000000"
NUEVA1 = "recien-nacida-1111-1111-111111111111"
NUEVA2 = "recien-nacida-2222-2222-222222222222"
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                       {"de": "claude", "texto": "acá andamos", "imgs": []}]}
MODELOS = {"ok": True, "modelo": "opus", "defecto": "opus",
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]}

fallas = []
proximo_sid = [NUEVA1]      # con qué id contesta el próximo /movil/mandar


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def servidor_falso(pag):
    """Todo lo que tocaría datos de verdad, contestado acá adentro."""
    def mandar(ruta):
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "sid": proximo_sid[0],
                                      "respuesta": "listo"}))

    pag.route("**/movil/mandar", mandar)
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(MODELOS)))
    # ⚠ Dos rutas separadas y sin comodín al final: `**/movil/borrador*` le pegaría a las
    # dos y Playwright prueba de la última a la primera.
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))


# --- la compu: /sesiones ---------------------------------------------------------
def compu(nav):
    print("--- /sesiones (la compu) ---")
    pag = nav.new_context(viewport={"width": 1400, "height": 900}).new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    # La página se sirve del disco (o de la versión que pidan): el resto de los pedidos
    # sigue yendo al panel prendido, que es lo que le da los datos de arranque.
    # ⚠ La dirección va ENTERA y sin comodines: con `**/sesiones` también caía
    # `/movil/sesiones` —la lista de conversaciones— y la página arrancaba sin datos.
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    # ⚠ Generoso a propósito: `/movil/sesiones` recorre las 144 conversaciones del disco
    # y en frío tarda varios segundos. Con 30 s la prueba salía roja sola de vez en cuando.
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(1500)

    def preparar(nueva):
        """Dos pestañas: una sin estrenar (donde se escribe) y otra cualquiera."""
        pag.evaluate("""([nueva, otra]) => {
          const p = datos.proyectos[0];
          abiertas = [{sid: nueva, cwd: p.cwd, nombre: 'Recién nacida'},
                      {sid: otra,  cwd: p.cwd, nombre: 'La otra'}];
          pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(nueva);
        }""", [nueva, OTRA])
        pag.wait_for_timeout(700)

    # --- 1) mando y me voy a otra pestaña mientras piensa -------------------------
    # `mandar()` se llama SIN await: se va a dormir en el fetch y el `irTab` de abajo
    # corre antes de que llegue la respuesta. Es exactamente lo que hace Martín.
    proximo_sid[0] = NUEVA1
    preparar("nueva-uno")
    pag.evaluate("""(otra) => {
      document.getElementById('texto').value = 'armame algo largo';
      mandar();
      irTab(otra);
    }""", OTRA)
    pag.wait_for_function("(n) => abiertas.some(t => t.sid === n)", arg=NUEVA1,
                          timeout=30000)
    pag.wait_for_timeout(600)
    est = pag.evaluate("""(n) => ({activa, sids: abiertas.map(t => t.sid),
      pendiente: !!pendientes[n], url: location.search})""", NUEVA1)
    revisar("me fui: sigo parado en la otra pestaña", est["activa"], OTRA)
    revisar("pero la charla igual se mudó a su id de verdad", NUEVA1 in est["sids"], True)
    revisar("y queda marcada para que entre yo", est["pendiente"], True)
    revisar("la barra de direcciones tampoco salta sola", NUEVA1 in est["url"], False)

    # --- 2) mando y me voy a la bandeja ------------------------------------------
    proximo_sid[0] = NUEVA2
    preparar("nueva-dos")
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'y esto también';
      mandar();
      irProyecto(TODAS);
    }""")
    pag.wait_for_function("(n) => abiertas.some(t => t.sid === n)", arg=NUEVA2,
                          timeout=30000)
    pag.wait_for_timeout(600)
    est = pag.evaluate("() => ({activa, caja: getComputedStyle($('#caja')).display})")
    revisar("me fui a la bandeja: no me mete adentro de la charla", est["activa"], None)
    revisar("y la caja de escribir sigue escondida", est["caja"], "none")

    # --- 3) el caso normal: me quedo ---------------------------------------------
    proximo_sid[0] = NUEVA1
    preparar("nueva-tres")
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'me quedo mirando';
      mandar();
    }""")
    pag.wait_for_function("(n) => abiertas.some(t => t.sid === n)", arg=NUEVA1,
                          timeout=30000)
    pag.wait_for_timeout(600)
    est = pag.evaluate("""(n) => ({activa, pendiente: !!pendientes[n],
      url: location.search})""", NUEVA1)
    revisar("si me quedé, la pestaña sigue siendo la activa", est["activa"], NUEVA1)
    revisar("y NO se marca como pendiente (la estoy mirando)", est["pendiente"], False)
    revisar("la dirección sí toma el id nuevo", NUEVA1 in est["url"], True)
    revisar("sin errores de JS en la compu", errores, [])
    pag.context.close()


# --- el celular: MOVIL_HTML ------------------------------------------------------
def celular(nav):
    print("\n--- la app del celular ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    # ⚠ Las pestañas del teléfono viven en el servidor: sin taparlas, la prueba le movería
    # a Martín las de su celular de verdad.
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
    revisar("la app del celular carga con el código nuevo", errores, [])

    def preparar(nueva):
        pag.evaluate("""([nueva, otra]) => {
          const cwd = (listaSes && (listaSes.proyectos || [])[0] || {}).cwd || 'D:\\\\IA';
          pestanas = [{sid: nueva, cwd, nombre: 'Recién', virgen: true},
                      {sid: otra,  cwd, nombre: 'La otra', virgen: false}];
          guardar(); ir(nueva);
        }""", [nueva, OTRA])
        pag.wait_for_timeout(700)

    proximo_sid[0] = NUEVA1
    preparar("nueva-uno")
    pag.evaluate("""(otra) => {
      document.getElementById('texto').value = 'armame algo largo';
      mandar();
      ir(otra);
    }""", OTRA)
    pag.wait_for_function("(n) => pestanas.some(p => p.sid === n)", arg=NUEVA1,
                          timeout=30000)
    pag.wait_for_timeout(600)
    est = pag.evaluate("""(n) => ({activa, sids: pestanas.map(p => p.sid)})""", NUEVA1)
    revisar("en el celular tampoco me arrastra", est["activa"], OTRA)
    revisar("y la charla igual se mudó a su id", NUEVA1 in est["sids"], True)

    # ⚠ El agujero viejo del celular: irse a OTRA pestaña sin estrenar también te traía
    # de vuelta, porque la condición miraba `activa.startsWith('nueva-')`.
    proximo_sid[0] = NUEVA2
    pag.evaluate("""() => {
      const cwd = pestanas[0].cwd;
      pestanas = [{sid: 'nueva-a', cwd, nombre: 'Una', virgen: true},
                  {sid: 'nueva-b', cwd, nombre: 'Otra', virgen: true}];
      guardar(); ir('nueva-a');
    }""")
    pag.wait_for_timeout(700)
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'y esta otra';
      mandar();
      ir('nueva-b');
    }""")
    pag.wait_for_function("(n) => pestanas.some(p => p.sid === n)", arg=NUEVA2,
                          timeout=30000)
    pag.wait_for_timeout(600)
    revisar("irse a otra charla sin estrenar tampoco te devuelve",
            pag.evaluate("() => activa"), "nueva-b")

    # el caso normal: me quedo
    proximo_sid[0] = NUEVA1
    preparar("nueva-tres")
    pag.evaluate("""() => {
      document.getElementById('texto').value = 'me quedo';
      mandar();
    }""")
    pag.wait_for_function("(n) => pestanas.some(p => p.sid === n)", arg=NUEVA1,
                          timeout=30000)
    pag.wait_for_timeout(600)
    revisar("si me quedo, la pestaña sigue siendo la activa",
            pag.evaluate("() => activa"), NUEVA1)
    revisar("sin errores de JS en el celular", errores, [])
    ctx.close()


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        compu(nav)
        celular(nav)
        nav.close()
    print(f"\n{'todo bien' if not fallas else str(len(fallas)) + ' en rojo: ' + str(fallas)}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
