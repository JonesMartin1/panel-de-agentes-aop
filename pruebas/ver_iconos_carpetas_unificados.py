"""Los íconos de las carpetas son los MISMOS en la compu, en el celular y en otro navegador.

Pedido de Martín (2026-08-25), textual: *"que no importa si abro desde el celular, la app
de escritorio o desde otro navegador, siempre tengan estos iconos, que estén unificados
digamos. Porfa no pierdas lo que ya tengo porque tardé mucho en ponerlos"*.

Hasta ese día había DOS juegos y los dos vivían en el navegador: `sesIconos` / `sesTonos` /
`sesApodos` / `sesIconosPropios` en `/sesiones`, y `movilAspectoCarpetas` en `/movil`, cada
uno con su propia paleta de emojis. Ahora la fuente de verdad es `aspecto_carpetas.json`.

Esta prueba recorre el camino completo con las DOS pantallas de verdad y el backend de
verdad (le llama a las funciones de `panel.py`), en este orden:

  1. el Chrome de Martín, con sus íconos ya puestos, siembra lo suyo al abrir `/sesiones`;
  2. el celular —`localStorage` vacío, o sea "otro navegador"— los ve todos;
  3. lo que cambia en el celular aparece en una compu recién abierta;
  4. un navegador que trae algo distinto NO pisa: queda anotado como choque.

⚠ NO toca `aspecto_carpetas.json` de verdad ni los logs de verdad: la ruta se apunta a un
temporal antes de empezar. Tampoco necesita el panel prendido — el HTML de las dos
pantallas se lee del disco (el del celular vive dentro de `panel.py`, y el panel que está
corriendo tiene en memoria el viejo hasta que se lo reinicie).

    python -m pruebas.ver_iconos_carpetas_unificados
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import panel                                              # noqa: E402

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
fallas = []

PROYECTOS = ["alfa", "beta", "gama"]

# Lo que Martín ya tenía en SU Chrome: esto es lo que no se puede perder.
LO_DE_MARTIN = """
  localStorage.clear();
  localStorage.setItem('sesIconos', JSON.stringify({alfa: '⚡', beta: '💼'}));
  localStorage.setItem('sesTonos', JSON.stringify({'g:alfa': 'violeta', 'otracosa': 'azul'}));
  localStorage.setItem('sesApodos', JSON.stringify({beta: 'Lo de Beta'}));
  localStorage.setItem('sesIconosPropios', JSON.stringify(['🐱', '🌵']));
"""


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def movil_html():
    """El HTML del celular, del `panel.py` DEL DISCO (no del panel corriendo)."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


def sesiones_json():
    """Lo que devuelve `/movil/sesiones`, con el aspecto REAL que tenga el servidor."""
    e = panel._aspecto_carpetas()
    return {"ok": True, "laura": "",
            "carpetas": {"orden": [], "ocultas": [],
                         "aspecto": e["carpetas"], "iconosPropios": e["iconosPropios"]},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-1", "nombre": "charla de " + n,
                                         "ts": 1, "ultimo": "vos", "viva": False,
                                         "interactiva": False, "detalle": ""}]}
                          for n in PROYECTOS]}


def montar(pag, escapados):
    """Las rutas: el backend de verdad, y todo lo demás cortado antes de salir."""
    # ⚠⚠ El colador va PRIMERO (Playwright evalúa de la última registrada a la primera):
    # así ningún pedido se escapa al panel de verdad ni siquiera por accidente. Acá tapa
    # TODO, así que por él pasan los pedidos normales de la pantalla; lo que se vigila es
    # que no caiga ninguna ESCRITURA de carpetas, que significaría que la ruta que la
    # maneja no la agarró y el cambio se habría perdido (o peor, ido al panel de verdad).
    pag.route("**/*", lambda r: (
        escapados.append(r.request.url) if "/carpetas/" in r.request.url else None,
        r.fulfill(status=200, content_type="application/json", body="{}")))
    pag.route("**/estaticos/*", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(ESTATICOS / r.request.url.rsplit("/", 1)[1]).read_text(encoding="utf-8")))
    pag.route("**/sesiones*", lambda r: r.fulfill(
        status=200, content_type="text/html",
        body=(ESTATICOS / "sesiones.html").read_text(encoding="utf-8")))
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                              body=HTML_MOVIL))
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(sesiones_json())))
    # ⭐ Y acá el backend DE VERDAD: las mismas funciones que corre el panel.
    pag.route("**/carpetas/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(panel._aspecto_aplicar(r.request.post_data_json or {}))))
    pag.route("**/carpetas/aspecto/sembrar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(panel._aspecto_sembrar(r.request.post_data_json or {}))))
    pag.route("**/carpetas/aspecto?*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, **panel._aspecto_carpetas()})))
    # El selector de navegador de cada carpeta (2026-08-28). Tambien es el backend de
    # verdad, pero se le atan las manos al disco: lo unico que se quiere de esta prueba
    # es que su pedido no cuente como una escritura perdida.
    pag.route("**/carpetas/navegadores*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(panel.carpetas_navegadores())))


def abrir(nav, movil, arranque=""):
    """Un navegador NUEVO (contexto propio = otro localStorage), en la pantalla que sea."""
    ctx = (nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                           is_mobile=True, device_scale_factor=3) if movil
           else nav.new_context(viewport={"width": 1400, "height": 900}))
    pag = ctx.new_page()
    errores, escapados = [], []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    montar(pag, escapados)
    pag.add_init_script(arranque or "localStorage.clear();")
    if movil:
        pag.add_init_script("localStorage.setItem('activa','nueva');")
    pag.goto(BASE + ("/movil" if movil else "/sesiones"), wait_until="domcontentloaded")
    return pag, errores, escapados


with sync_playwright() as p:
    tmp = Path(tempfile.mkdtemp(prefix="iconos_carp_"))
    panel.ASPECTO_CARPETAS = tmp / "aspecto_carpetas.json"
    panel.LOGS = tmp
    real = RAIZ / "aspecto_carpetas.json"
    habia_real = real.exists()
    HTML_MOVIL = movil_html()

    nav = p.chromium.launch(channel="chrome", headless=True)

    # --- 1. El Chrome de Martín sube lo suyo, sin que él haga nada -------------------
    print("\n--- 1. La compu de Martín, con sus íconos ya puestos ---")
    pag, errores, escapados = abrir(nav, movil=False, arranque=LO_DE_MARTIN)
    # ⚠ Esperar al DATO, no al reloj: "Todas" también tiene `data-proy`, así que el
    # selector genérico se cumple antes de que lleguen los proyectos de verdad.
    pag.wait_for_selector("#carpetas .carpeta[data-proy='gama']", timeout=15000)
    pag.wait_for_timeout(800)
    e = panel._aspecto_carpetas()
    revisar("el ícono que tenía puesto subió solo",
            (e["carpetas"].get("alfa") or {}).get("icono"), "⚡")
    revisar("y el de la otra carpeta también",
            (e["carpetas"].get("beta") or {}).get("icono"), "💼")
    revisar("el color viajó con la llave de la carpeta",
            (e["carpetas"].get("alfa") or {}).get("color"), "violeta")
    revisar("el apodo también", (e["carpetas"].get("beta") or {}).get("apodo"), "Lo de Beta")
    revisar("los íconos que agregó a mano no se perdieron", e["iconosPropios"], ["🐱", "🌵"])
    # ⚠ `sesTonos` mezcla carpetas (`g:`) y conversaciones: lo que no es carpeta no viaja.
    revisar("el color de una conversación NO se coló como carpeta",
            "otracosa" in e["carpetas"], False)
    revisar("quedó la copia de respaldo, por las dudas",
            len(list(tmp.glob("aspecto_carpetas_compu_*.json"))), 1)
    revisar("sin errores de JS en la compu", errores, [])
    revisar("ninguna escritura de carpetas se perdió por el camino", escapados, [])
    pag.context.close()

    # --- 2. El celular, que nunca vio nada de esto ------------------------------------
    print("\n--- 2. El celular, con el navegador en cero ---")
    cel, errores_cel, escapados_cel = abrir(nav, movil=True)
    cel.wait_for_selector(".menu", timeout=15000)
    cel.tap(".menu")
    cel.wait_for_selector("#cajon .carpeta[data-proy]", timeout=15000)
    cel.wait_for_timeout(600)
    revisar("ve el ícono que Martín eligió en la compu",
            cel.eval_on_selector("#cajon .carpeta[data-proy='alfa'] .ic", "e => e.textContent"), "⚡")
    revisar("y el de la otra",
            cel.eval_on_selector("#cajon .carpeta[data-proy='beta'] .ic", "e => e.textContent"), "💼")
    revisar("el apodo se ve igual",
            cel.eval_on_selector("#cajon .carpeta[data-proy='beta'] .nom", "e => e.textContent"),
            "Lo de Beta")
    revisar("el color, también",
            cel.evaluate("""() => document.querySelector("#cajon .carpeta[data-proy='alfa']")
                              .style.getPropertyValue('--carp-color')"""), "#c4b5fd")
    cel.tap("#cajon .carpeta[data-proy='gama'] .editar-carp")
    cel.wait_for_selector("#editorCarp.abierto")
    revisar("y los íconos que agregó a mano están en la paleta del teléfono",
            cel.evaluate("""() => ["🐱","🌵"].every(i =>
                              !!document.querySelector('#editorCarp [data-ico="' + i + '"]'))"""), True)

    # --- 3. Lo que cambia en el celular vuelve a la compu -----------------------------
    print("\n--- 3. Cambia algo en el celular ---")
    cel.tap("#editorCarp [data-ico='🎯']")
    cel.wait_for_selector("#editorCarp.abierto")
    cel.wait_for_timeout(500)
    revisar("el cambio del celular llegó al servidor",
            (panel._aspecto_carpetas()["carpetas"].get("gama") or {}).get("icono"), "🎯")
    revisar("sin errores de JS en el celular", errores_cel, [])
    revisar("y ninguna escritura de carpetas se perdió", escapados_cel, [])
    cel.context.close()

    print("\n--- 4. Otro navegador de la compu, recién abierto ---")
    otra, errores_otra, escapados_otra = abrir(nav, movil=False)
    otra.wait_for_selector("#carpetas .carpeta[data-proy]", timeout=15000)
    otra.wait_for_timeout(1200)
    # ⚠ En la pantalla grande el ícono va en el PRIMER span de la fila (sin clase); el que
    # tiene clase `.ic` es el del celular. Son dos HTML distintos para el mismo dato.
    revisar("ve el ícono que se eligió en el celular",
            otra.eval_on_selector("#carpetas .carpeta[data-proy='gama'] span:first-child",
                                  "e => e.textContent.trim()"), "🎯")
    revisar("y los que venían de antes",
            otra.eval_on_selector("#carpetas .carpeta[data-proy='alfa'] span:first-child",
                                  "e => e.textContent.trim()"), "⚡")
    revisar("el apodo, igual",
            otra.eval_on_selector("#carpetas .carpeta[data-proy='beta'] .nom",
                                  "e => e.textContent.trim()"), "Lo de Beta")
    revisar("sin errores de JS", errores_otra, [])
    otra.context.close()

    # --- 5. ⭐ Un navegador con algo distinto NO pisa: queda anotado -------------------
    print("\n--- 5. Un navegador viejo, con otros íconos ---")
    viejo, errores_viejo, _ = abrir(nav, movil=False, arranque="""
      localStorage.clear();
      localStorage.setItem('sesIconos', JSON.stringify({alfa: '🔒', gama: '🧪'}));
    """)
    viejo.wait_for_selector("#carpetas .carpeta[data-proy]", timeout=15000)
    viejo.wait_for_timeout(1200)
    e = panel._aspecto_carpetas()
    revisar("lo que ya estaba guardado NO se pisó",
            (e["carpetas"].get("alfa") or {}).get("icono"), "⚡")
    # Los DOS desacuerdos quedan anotados, con lo que había y lo que llegó: `alfa` (⚡ contra
    # 🔒) y `gama`, que el celular acaba de poner en 🎯 y este navegador traía en 🧪.
    revisar("los desacuerdos quedan anotados para que Martín elija",
            [(c["carpeta"], c["guardado"], c["llego"]) for c in e["choques"]],
            [("alfa", "⚡", "🔒"), ("gama", "🎯", "🧪")])
    revisar("y lo que en el servidor faltaba, se sumó",
            (e["carpetas"].get("gama") or {}).get("icono"), "🎯")
    revisar("sin errores de JS", errores_viejo, [])
    viejo.context.close()

    # --- 6. ⭐⭐ Contra un panel SIN REINICIAR (que contesta 404) no se pierde nada ------
    # Este fue un bug de verdad, encontrado el mismo día: un 404 no le hace saltar el
    # `catch` a `fetch`, así que la pantalla se marcaba "ya sembré" sin haber subido nada.
    # Después del reinicio no lo reintentaba nunca y, al leer un servidor vacío, le
    # borraba los íconos a Martín — justo lo que él pidió que no pasara.
    print("\n--- 6. Con el panel todavía sin reiniciar ---")
    viejo_panel = nav.new_context(viewport={"width": 1400, "height": 900})
    pag6 = viejo_panel.new_page()
    err6, esc6 = [], []
    montar(pag6, esc6)
    pag6.on("pageerror", lambda e: err6.append(str(e)))
    # El panel de antes no conoce estos endpoints: 404, como en la vida real.
    pag6.route("**/carpetas/aspecto/sembrar", lambda r: r.fulfill(status=404, body="Not Found"))
    pag6.route("**/carpetas/aspecto", lambda r: r.fulfill(status=404, body="Not Found"))
    pag6.add_init_script(LO_DE_MARTIN)
    pag6.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag6.wait_for_selector("#carpetas .carpeta[data-proy='gama']", timeout=15000)
    pag6.wait_for_timeout(1200)
    revisar("con 404 NO se da por sembrado",
            pag6.evaluate("() => localStorage.getItem('sesAspectoSembrado2')"), None)
    revisar("y sigue mostrando los íconos que tenía guardados",
            pag6.eval_on_selector("#carpetas .carpeta[data-proy='alfa'] span:first-child",
                                  "e => e.textContent.trim()"), "⚡")
    revisar("que además siguen en el navegador, sin borrarse",
            pag6.evaluate("() => JSON.parse(localStorage.getItem('sesIconos')).alfa"), "⚡")
    revisar("sin errores de JS", err6, [])
    viejo_panel.close()

    revisar("el archivo de verdad de Martín no se tocó", real.exists(), habia_real)
    nav.close()

print("")
print("TODO BIEN" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
