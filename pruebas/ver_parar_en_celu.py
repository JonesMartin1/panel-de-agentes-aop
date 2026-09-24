"""En el celular, el boton ⏹ Parar tiene que APARECER cuando la charla esta pensando.

Bug que trajo Martin con una captura el 2026-08-26: la sesion llevaba casi cinco minutos
pensando y abajo solo estaban Avisame y Enviar. El ⏹ no estaba por ningun lado, asi que
no habia forma de cortar un turno desde el telefono.

La causa: el CSS de la app del celular tiene `#parar{...;display:none}` (asi arranca
escondido), y el JS lo prendia con `style.display = ''`. Borrar el estilo de linea
devuelve el elemento a la REGLA del CSS, o sea otra vez a `display:none`: el boton no
aparecia nunca. En la pantalla de la compu no pasaba porque alla el `display:none` esta
en el propio tag, y `''` si lo muestra.

Arreglo: prenderlo con `'block'` (la caja de escribir es flex, se comporta igual que Enviar).

⚠ No toca ninguna sesion de verdad ni necesita el panel prendido: la pagina se sirve
leyendola del `panel.py` del disco y el servidor esta inventado aca adentro. Justamente por
eso ve el codigo que acabas de escribir y no el que el panel tiene cargado en memoria.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_parar_en_celu
"""
import ast
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
SID = "celu-parar-7777-7777-777777777777"
CHARLA = [{"de": "vos", "texto": "levantá el servidor", "imgs": [], "h": "11:13"},
          {"de": "claude", "texto": "voy por prioridad de cliente", "imgs": [], "h": "11:14"}]

fallas = []
estado = {"ocupada": True, "ts": time.time()}


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def html_movil():
    """El HTML de la app del celular, sacado de panel.py sin importar el modulo.

    Importarlo levantaria el panel entero (FastAPI, rutas, archivos): aca solo hace falta
    el texto de la constante, y el arbol de sintaxis lo da sin ejecutar una sola linea.

    Con `--del-panel` lo pide al panel que esta corriendo. Sirve para lo otro: comprobar
    que DESPUES de reiniciarlo el telefono recibe de verdad el arreglo, porque el panel
    tiene esta pagina cargada en memoria y hasta el reinicio sigue mandando la vieja.
    """
    if "--del-panel" in sys.argv:
        import urllib.request
        with urllib.request.urlopen(BASE + "/movil", timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == "MOVIL_HTML"):
            return ast.literal_eval(nodo.value)
    raise SystemExit("No encontre MOVIL_HTML en panel.py")


def servidor_falso(pag, paradas):
    def bandeja(r):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "proyectos": [
                {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": True, "sesiones": [
                    {"id": SID, "nombre": "VPS-Seguridad", "ts": estado["ts"],
                     "ultimo": "claude", "viva": estado["ocupada"], "interactiva": False,
                     "ocupada": estado["ocupada"], "detalle": "activa"}]}]}))
    pag.route("**/movil/sesiones*", bandeja)
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": estado["ocupada"],
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "opus", "defecto": "opus",
                         "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]})))
    pag.route("**/movil/borradores*", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/movil/donde*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": false}'))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"cerebro": "claude", "prompts": [], "carpeta": ""})))
    pag.route("**/marcas*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"marcas": []}'))

    def parar(r):
        paradas.append(json.loads(r.request.post_data or "{}"))
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "paro": True}))
    pag.route("**/movil/parar", parar)

    # Los .js de la pagina salen del disco, no del panel: misma idea que el HTML.
    def estatico(r):
        arch = ESTATICOS / Path(r.request.url.split("?")[0]).name
        if arch.exists():
            r.fulfill(status=200, content_type="application/javascript",
                      body=arch.read_text(encoding="utf-8"))
        else:
            r.fulfill(status=404, body="")
    pag.route("**/estaticos/*", estatico)
    pag.route("**/movil/manifest.json", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/icono*", lambda r: r.fulfill(status=404, body=""))


# El telefono de Martin: iPhone parado, con dedo en vez de mouse.
with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 390, "height": 844},
                          device_scale_factor=3, is_mobile=True, has_touch=True)
    pag = ctx.new_page()
    errores, paradas, avisos = [], [], []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: (avisos.append(d.message), d.dismiss()))
    servidor_falso(pag, paradas)
    cuerpo = html_movil()
    pag.route(BASE + "/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=cuerpo))
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof pintar === 'function'", timeout=60000)
    # Se entra a la charla, igual que tocandola en la lista.
    pag.evaluate("""async (sid) => {
      await traerSesiones();
      pestanas = [{sid, cwd: sesiones[0] ? sesiones[0].cwd : '', nombre: 'VPS-Seguridad'}];
      activa = sid; recienAbierta = true;
      await pintar();
    }""", SID)
    pag.wait_for_timeout(1200)

    revisar("la charla se ve pensando",
            pag.evaluate("() => !!document.querySelector('#cuerpo .msg.pensando')"))
    revisar("** el botón ⏹ se ve en el teléfono", pag.is_visible("#parar"))
    revisar("y está adentro de la caja de escribir, al lado de Enviar",
            pag.evaluate("() => document.querySelector('#parar')?.parentElement?.id") == "escribir")
    caja = pag.evaluate("() => { const b = document.querySelector('#parar').getBoundingClientRect();"
                        "  return {x: b.x, an: b.width, al: b.height}; }")
    revisar("con tamaño de botón y dentro de la pantalla",
            caja["an"] > 30 and caja["al"] > 30 and 0 < caja["x"] < 390, str(caja))

    # Se aprieta: el pedido tiene que salir con el id de esta charla. (Si el botón está
    # escondido no se lo espera 30 s: ya falló arriba y el click sobra.)
    if pag.is_visible("#parar"):
        pag.click("#parar")
        pag.wait_for_timeout(1000)
    revisar("apretarlo manda el corte de ESTA charla",
            bool(paradas) and paradas[-1].get("sid") == SID, str(paradas[-1:]))

    # Y cuando la charla deja de trabajar, el botón se va: no queda un freno colgado.
    estado["ocupada"] = False
    estado["ts"] = time.time() - 600
    pag.evaluate("""async () => {
      falladas = {}; await traerSesiones(); firmaChat = {}; await pintar();
    }""")
    pag.wait_for_timeout(1200)
    revisar("terminada la charla, el ⏹ se esconde", not pag.is_visible("#parar"))

    revisar("sin errores de JS", errores == [], str(errores))
    nav.close()

print("\n" + ("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas)))
if fallas:
    raise SystemExit(1)
