"""Salir de una charla en el celular te deja ARRIBA de la bandeja, en las últimas.

Pedido de Martín (2026-08-24): *"no me gusta que cuando salgo del chat me mueva a
cualquier parte de la lista de sesiones, yo siempre quiero ver las últimas"*.

La causa: el scroll es del contenedor `#cuerpo`, que es el MISMO para todas las vistas.
Adentro de una charla queda abajo de todo (el hilo se lee por el final) y al cambiarle el
contenido por la lista el navegador se lo deja puesto, así que caías a media bandeja.

Se prueban las dos mitades, que van juntas:
  · volver de una charla (y cambiar de carpeta) empieza arriba de todo;
  · un repintado de los de cada 3 s NO te mueve el scroll — esa regla ya existía y
    romperla sería peor que el bug: te saltaría al principio mientras estás leyendo.

⚠ No hace falta el panel prendido: el HTML del celular sale del `MOVIL_HTML` del
`panel.py` del disco y todos los pedidos están interceptados, así que no se toca ninguna
conversación de verdad.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_bandeja_arriba_movil
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
CWD = "D:\\IA\\wpp-transcriptor"
CWD2 = "C:\\EspacioDeTrabajo\\Otro"
fallas = []

# Una bandeja larga de verdad: 30 conversaciones, la más nueva primero (ts más alto).
# Con pocas filas no habría scroll y la prueba no probaría nada.
def charlas(prefijo, cuantas):
    return [{"id": f"{prefijo}{i}", "nombre": f"Conversación {prefijo} {i}",
             "ts": 1000 - i, "viva": False, "interactiva": False, "ultimo": "claude",
             "detalle": f"guardada, hace {i} h"} for i in range(cuantas)]


SESIONES = {"ok": True, "laura": "", "proyectos": [
    {"proyecto": "wpp-transcriptor", "cwd": CWD, "vivo": False,
     "sesiones": charlas("a", 30)},
    {"proyecto": "Otro", "cwd": CWD2, "vivo": False, "sesiones": charlas("b", 25)}]}

# Un hilo largo, para que adentro de la charla el scroll quede bien abajo: si la charla
# no scrollea, volver daría cero por casualidad y el chequeo no valdría nada.
CHAT = {"mensajes": [{"de": "vos" if i % 2 else "claude",
                      "texto": f"Mensaje número {i} del hilo de prueba. " * 6,
                      "hora": "15:00"} for i in range(60)],
        "ocupada": False, "nombre": "Conversación a 10"}


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (("  → " + detalle) if detalle else ""))
    if not ok:
        fallas.append(que)


def movil_html():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


def json_fijo(cuerpo):
    return lambda r: r.fulfill(status=200, content_type="application/json",
                               body=json.dumps(cuerpo))


def enchufar(pag):
    # ⚠ El comodín va PRIMERO: Playwright prueba las rutas de la última a la primera,
    # así que registrado al final se comía hasta el HTML de la app.
    pag.route("**/*", json_fijo({"ok": True}))
    pag.route(re.compile(r"/movil(\?.*)?$"), lambda r: r.fulfill(
        status=200, content_type="text/html", body=movil_html()))
    pag.route("**/estaticos/*", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(RAIZ / "app" / "estaticos" / r.request.url.split("/")[-1].split("?")[0])
        .read_text(encoding="utf-8")))
    pag.route("**/movil/sesiones*", json_fijo(SESIONES))
    pag.route("**/movil/pestanas*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true}' if r.request.method == "POST"
        else '{"pestanas": [], "activa": "nueva"}'))
    pag.route("**/movil/borradores*", json_fijo({}))
    pag.route("**/movil/borrador", json_fijo({"ok": True}))
    pag.route("**/movil/chat*", json_fijo(CHAT))
    pag.route("**/movil/modelo*", json_fijo({"ok": True, "modelos": [], "esfuerzos": []}))
    pag.route("**/marcas*", json_fijo({}))
    pag.route("**/status*", json_fijo({"servicios": {}, "encendido": False,
                                       "pausado": False, "pensando": False}))
    pag.route("**/chat", json_fijo({"items": []}))
    pag.route("**/gasto*", json_fijo({}))
    pag.route("**/sesion/*", json_fijo({"ok": False}))


def scroll(pag):
    return pag.evaluate("() => document.querySelector('#cuerpo').scrollTop")


def primera_fila(pag):
    return pag.evaluate("""() => {
      const f = document.querySelector('.correo[data-sid]:not([data-sid=""])');
      return f ? f.querySelector('.tit').childNodes[0].textContent.trim() : '';
    }""")


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                          is_mobile=True, device_scale_factor=3)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    enchufar(pag)
    pag.add_init_script("localStorage.clear(); localStorage.setItem('activa','nueva');")
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_selector(".correo[data-sid]", timeout=8000)

    revisar("la bandeja abre con la última conversación arriba",
            primera_fila(pag) == "Conversación a 0", primera_fila(pag))

    # --- 1. Bajar hasta el fondo de la bandeja y entrar a una charla de ahí ----------
    pag.evaluate("() => document.querySelector('#cuerpo').scrollTo(0, 99999)")
    pag.wait_for_timeout(80)
    bajo = scroll(pag)
    revisar("la bandeja de prueba es larga (si no, no se probaría nada)", bajo > 300,
            f"scroll={bajo:.0f}")

    pag.evaluate("() => document.querySelectorAll('.correo[data-sid]')[12].click()")
    pag.wait_for_selector("#cabecera", timeout=8000)
    pag.wait_for_timeout(400)
    dentro = scroll(pag)
    revisar("adentro de la charla el hilo queda abajo de todo", dentro > 200,
            f"scroll={dentro:.0f}")

    # --- 2. La flecha ← de la cabecera: la salida de una charla ----------------------
    pag.evaluate("() => document.querySelector('#titulo .volver').click()")
    pag.wait_for_selector(".correo[data-sid]", timeout=8000)
    pag.wait_for_timeout(150)
    vuelta = scroll(pag)
    revisar("al salir de la charla la bandeja empieza arriba", vuelta == 0,
            f"scroll={vuelta:.0f}")
    revisar("y arriba están las últimas", primera_fila(pag) == "Conversación a 0",
            primera_fila(pag))

    # --- 3. Un repintado de los de cada 3 s NO puede moverte el scroll ---------------
    pag.evaluate("() => document.querySelector('#cuerpo').scrollTo(0, 500)")
    pag.wait_for_timeout(60)
    antes = scroll(pag)
    pag.evaluate("() => { elegirFirma = ''; pintarElegir(); }")
    pag.wait_for_timeout(150)
    despues = scroll(pag)
    revisar("leyendo la bandeja, un repintado te deja donde estabas",
            abs(despues - antes) < 5, f"{antes:.0f} → {despues:.0f}")

    # --- 4. Cambiar de carpeta también empieza arriba --------------------------------
    pag.evaluate("() => elegirProyecto('Otro')")
    pag.wait_for_timeout(250)
    otra = scroll(pag)
    revisar("cambiando de carpeta la lista arranca arriba", otra == 0, f"scroll={otra:.0f}")

    revisar("sin errores de JS", not errores, "; ".join(errores[:2]))
    pag.screenshot(path=str(RAIZ / "resultados" / "bandeja_arriba_movil.png"))
    ctx.close()
    nav.close()

print("\n" + ("todo bien" if not fallas else "FALLAN: " + ", ".join(fallas)))
sys.exit(1 if fallas else 0)
