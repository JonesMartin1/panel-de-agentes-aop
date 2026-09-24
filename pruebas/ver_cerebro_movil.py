"""Los dos cerebros (Claude y Codex) en la app del celular.

Pedido de Martín (2026-08-19), después de que quedara andando en la compu: *"¿podés
hacerlo para el celular también?"*. Son dos piezas, las dos solo pantalla:
 1. En el INICIO, el interruptor del cerebro de Laura (la misma perilla que el selector
    del panel grande y que decirle "pasate a Codex" por voz), con la frase del traspaso
    a la vista un rato.
 2. En las SESIONES: chapita "Codex" en la bandeja, elegir con qué cerebro nace una
    charla nueva y, en una charla de Codex, sus selectores de modelo, esfuerzo y velocidad.

⚠ El HTML del celular vive DENTRO de `panel.py` (la constante `MOVIL_HTML`): acá se lee
el `panel.py` del disco y se sirve ese HTML, así la prueba corre sin reiniciar nada.
⚠ TODOS los endpoints se interceptan: ni el cerebro de verdad de Laura ni ninguna
sesión real se tocan.

Correr con:  python -m pruebas.ver_cerebro_movil   (no hace falta el panel prendido)
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
CWD = "D:\\pruebas\\alfa"
SID_CLAUDE = "charla-claude-0001"
SID_CODEX = "charla-codex-0002"
SID_NACIDA = "codex-nacida-0003"
fallas = []

# El cerebro de mentira: la prueba le cambia el activo y el GET devuelve lo último.
estado = {"activo": "claude"}
FRASE = "Listo, ahora piensa Codex. Le paso lo que veníamos hablando."

CHARLA = {"mensajes": [{"de": "vos", "texto": "hola"},
                       {"de": "claude", "texto": "hola, ¿en qué andamos?"}]}

MODELO_CLAUDE = {"ok": True, "modelo": "opus", "defecto": "opus",
                 "esfuerzo": "", "contexto": {"tokens": 42000, "nivel": "bien"},
                 "modelos": [{"id": "opus", "nombre": "Opus"},
                             {"id": "haiku", "nombre": "Haiku"}],
                 "esfuerzos": [{"id": "", "nombre": "Esfuerzo normal"},
                               {"id": "high", "nombre": "Alto"}]}
MODELO_CODEX = {"ok": True, "modelo": "gpt-5.6-sol", "defecto": "gpt-5.6-sol",
                "modelos": [{"id": "gpt-5.6-sol", "nombre": "GPT-5.6 Sol"},
                            {"id": "gpt-5.6-luna", "nombre": "GPT-5.6 Luna"}],
                "esfuerzo": "high",
                "esfuerzos": [{"id": "", "nombre": "Esfuerzo de fábrica"},
                               {"id": "low", "nombre": "Esfuerzo bajo"},
                               {"id": "high", "nombre": "Esfuerzo alto"}],
                "velocidad": "", "velocidades": [
                    {"id": "", "nombre": "Velocidad estándar"},
                    {"id": "priority", "nombre": "Velocidad rápida"}],
                "cerebro": "codex",
                "contexto": {"tokens": 88000, "nivel": "bien"}}


def sesiones_json():
    return {"ok": True, "laura": "",
            "proyectos": [{"proyecto": "alfa", "cwd": CWD, "vivo": False,
                           "sesiones": [
                               {"id": SID_CLAUDE, "nombre": "la de Claude", "ts": 2,
                                "ultimo": "vos", "viva": False, "interactiva": False,
                                "detalle": ""},
                               {"id": SID_CODEX, "nombre": "la de Codex", "ts": 1,
                                "ultimo": "vos", "viva": False, "interactiva": False,
                                "detalle": "", "cerebro": "codex"}]}]}


def html_del_panel(nombre):
    """Una pantalla embebida, sacada del `panel.py` del disco."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == nombre for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit(f"No encontré {nombre} en panel.py")


def movil_html():
    return html_del_panel("MOVIL_HTML")


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

    HTML = movil_html()
    cambios, mandados, esfuerzos_guardados, velocidades_guardadas = [], [], [], []

    def json_fijo(cuerpo):
        return lambda r: r.fulfill(status=200, content_type="application/json",
                                   body=json.dumps(cuerpo))

    def cerebro(ruta):
        if ruta.request.method == "POST":
            d = ruta.request.post_data_json or {}
            cambios.append(d)
            estado["activo"] = d.get("cerebro") or "claude"
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True, "activo": estado["activo"],
                                          "frase": FRASE}))
        else:
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True, "activo": estado["activo"],
                                          "defecto": "claude",
                                          "cerebros": [{"id": "claude", "nombre": "Claude"},
                                                       {"id": "codex", "nombre": "Codex"}]}))

    def modelo(ruta):
        if ruta.request.method == "POST":
            ruta.fulfill(status=200, content_type="application/json",
                         body='{"ok":true,"modelo":"opus"}')
            return
        sid = re.search(r"sid=([^&]*)", ruta.request.url)
        sid = sid.group(1) if sid else ""
        es_codex = "codex" in sid or "cerebro=codex" in ruta.request.url
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps(MODELO_CODEX if es_codex else MODELO_CLAUDE))

    def mandar(ruta):
        mandados.append(ruta.request.post_data or "")
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "respuesta": "acá Codex",
                                      "sid": SID_NACIDA, "aviso": ""}))

    def esfuerzo(ruta):
        d = ruta.request.post_data_json or {}
        esfuerzos_guardados.append(d)
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "esfuerzo": d.get("esfuerzo", "")}))

    def velocidad(ruta):
        d = ruta.request.post_data_json or {}
        velocidades_guardadas.append(d)
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "velocidad": d.get("velocidad", "")}))

    pag.route("**/sesion/cerebro*", cerebro)
    pag.route("**/sesion/modelo", json_fijo({**MODELO_CLAUDE, "codex": MODELO_CODEX}))
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                              body=HTML))
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(sesiones_json())))
    pag.route("**/movil/pestanas*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true}' if r.request.method == "POST"
        else '{"pestanas": [], "activa": "panel"}'))
    pag.route("**/movil/borradores*", json_fijo({}))
    pag.route("**/movil/borrador", json_fijo({"ok": True}))
    pag.route("**/movil/donde*", json_fijo({"ok": True}))
    pag.route("**/movil/chat*", json_fijo(CHARLA))
    pag.route("**/movil/modelo*", modelo)
    pag.route("**/movil/esfuerzo", esfuerzo)
    pag.route("**/movil/velocidad", velocidad)
    pag.route("**/movil/mandar", mandar)
    pag.route("**/status*", json_fijo({"servicios": {}, "encendido": False,
                                       "pausado": False, "pensando": False}))
    pag.route("**/chat", json_fijo({"items": []}))
    pag.route("**/gasto*", json_fijo({}))
    pag.route("**/marcas*", json_fijo({}))

    pag.add_init_script("localStorage.clear(); localStorage.setItem('activa','panel');")
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")

    # --- 1. El interruptor del cerebro en el inicio -----------------------------------
    pag.wait_for_selector(".cerebros", timeout=8000)
    revisar("el inicio muestra los dos cerebros",
            pag.eval_on_selector_all(".cerebros button",
                                     "l => l.map(b => b.textContent.trim())"),
            ["Claude", "Codex"])
    revisar("arranca con Claude puesto",
            pag.eval_on_selector_all(".cerebros button",
                                     "l => l.map(b => b.classList.contains('puesto'))"),
            [True, False])
    revisar("todo entra en el ancho del teléfono",
            pag.evaluate("() => document.querySelector('.cerebros')"
                         ".getBoundingClientRect().right <= window.innerWidth + 1"), True)

    pag.tap(".cerebros button:nth-child(2)")
    pag.wait_for_timeout(800)
    revisar("tocar Codex se lo pide al servidor", cambios, [{"cerebro": "codex"}])
    revisar("el botón de Codex queda encendido con su color",
            pag.evaluate("() => { const b = document.querySelectorAll('.cerebros button')[1];"
                         " return b.classList.contains('puesto') && b.classList.contains('codex'); }"),
            True)
    revisar("y la frase del traspaso queda a la vista",
            pag.eval_on_selector(".cerebroAviso", "e => e.textContent.trim()"), FRASE)
    pag.wait_for_timeout(500)
    revisar("el inicio de Codex muestra Modelo, Esfuerzo y Velocidad",
            pag.evaluate("() => document.querySelectorAll('.ajusSes.laura select').length"), 3)

    # --- 2. La chapita en la bandeja --------------------------------------------------
    pag.evaluate("() => ir('nueva')")
    pag.wait_for_selector(".correo[data-sid]", timeout=8000)
    revisar("la charla de Codex lleva su chapita",
            pag.evaluate("() => { const f = document.querySelector('.correo[data-sid=%s]');"
                         " const c = f && f.querySelector('.cer');"
                         " return c ? c.textContent.trim() : null; }"
                         % json.dumps(SID_CODEX)), "Codex")
    revisar("la de Claude no lleva ninguna",
            pag.evaluate("() => !!document.querySelector('.correo[data-sid=%s] .cer')"
                         % json.dumps(SID_CLAUDE)), False)

    # --- 3. Adentro de una charla de Codex, sin las perillas de Claude ----------------
    pag.evaluate("([cwd, sid]) => abrir(cwd, sid, 'la de Codex')", [CWD, SID_CODEX])
    pag.wait_for_selector(".ajusSes .cerSes", timeout=8000)
    revisar("dice de quién es la charla",
            pag.eval_on_selector(".ajusSes .cerSes", "e => e.textContent.trim()"), "Codex")
    revisar("tiene Modelo, Esfuerzo y Velocidad",
            pag.evaluate("() => document.querySelectorAll('.ajusSes select').length"), 3)
    revisar("muestra el esfuerzo que devolvió el servidor",
            pag.eval_on_selector(".ajusSes select:nth-of-type(2)", "e => e.value"), "high")
    pag.select_option(".ajusSes select:nth-of-type(2)", "low")
    pag.wait_for_timeout(200)
    revisar("cambiarlo guarda id de sesión y nivel",
            esfuerzos_guardados[-1] if esfuerzos_guardados else None,
            {"sid": SID_CODEX, "esfuerzo": "low"})
    pag.select_option(".ajusSes select:nth-of-type(3)", "priority")
    pag.wait_for_timeout(200)
    revisar("cambiar velocidad guarda id y tier",
            velocidades_guardadas[-1] if velocidades_guardadas else None,
            {"sid": SID_CODEX, "velocidad": "priority"})
    # Desde el 2026-08-20 la charla nacida sí tiene UN botón: mudarse al otro cerebro.
    revisar("su único botón es mudarse a Claude",
            pag.evaluate("() => [...document.querySelectorAll('.ajusSes button')]"
                         ".map(b => b.textContent.trim())"), ["→ Claude"])
    revisar("el contexto sí se muestra (88 k del rollout)",
            pag.eval_on_selector(".ajusSes .ctxSes", "e => e.textContent.trim()"), "88 k")

    # --- 4. Y en una de Claude las perillas siguen enteras ----------------------------
    pag.evaluate("([cwd, sid]) => abrir(cwd, sid, 'la de Claude')", [CWD, SID_CLAUDE])
    pag.wait_for_selector(".ajusSes select", timeout=8000)
    revisar("la de Claude tiene sus dos selectores",
            pag.evaluate("() => document.querySelectorAll('.ajusSes select').length"), 2)
    revisar("y sus botones: compactar y mudarse a Codex",
            pag.evaluate("() => [...document.querySelectorAll('.ajusSes button')]"
                         ".map(b => b.textContent.trim())"), ["Compactar", "→ Codex"])
    revisar("las listas de Claude no se pisaron con las vacías de Codex",
            pag.evaluate("() => [...document.querySelectorAll('.ajusSes select')[0].options]"
                         ".map(o => o.value)"), ["opus", "haiku"])

    # --- 5. Una charla nueva elige con qué cerebro nace -------------------------------
    pag.evaluate("cwd => abrir(cwd, '', 'Nueva')", CWD)
    pag.wait_for_selector(".eligeCer", timeout=8000)
    revisar("la pestaña sin estrenar ofrece elección manual o automática",
            pag.eval_on_selector_all(".eligeCer button",
                                     "l => l.map(b => b.textContent.trim())"),
            ["Claude", "Codex", "Auto"])
    revisar("con Claude puesto de fábrica",
            pag.eval_on_selector_all(".eligeCer button",
                                     "l => l.map(b => b.classList.contains('puesto'))"),
            [True, False, False])
    pag.tap(".eligeCer button:nth-of-type(3)")
    revisar("Auto queda guardado hasta que nazca la charla",
            pag.evaluate("() => pestanas.find(x => x.sid === activa).cerebro"), "auto")
    pag.tap(".eligeCer button:nth-of-type(2)")
    pag.wait_for_timeout(500)
    revisar("elegir Codex lo deja marcado",
            pag.evaluate("() => { const b = document.querySelectorAll('.eligeCer button')[1];"
                         " return b.classList.contains('puesto') && b.classList.contains('codex'); }"),
            True)
    revisar("y queda guardado en la pestaña",
            pag.evaluate("() => pestanas.find(x => x.sid === activa).cerebro"), "codex")
    revisar("antes del primer mensaje también aparecen las tres perillas",
            pag.evaluate("() => document.querySelectorAll('.eligeCer select').length"), 3)

    pag.fill("#texto", "hola codex")
    pag.evaluate("() => mandar()")
    pag.wait_for_timeout(1200)
    revisar("el primer mensaje viaja con cerebro=codex",
            bool(mandados) and bool(re.search(
                r'name="cerebro"\r?\n\r?\ncodex', mandados[-1])), True)
    revisar("y lleva el modelo elegido",
            bool(mandados) and bool(re.search(
                r'name="modelo"\r?\n\r?\ngpt-5.6-sol', mandados[-1])), True)
    revisar("la pestaña se muda al id que nació",
            pag.evaluate("() => activa"), SID_NACIDA)
    pag.wait_for_timeout(800)
    revisar("y la charla nacida ya se muestra como de Codex",
            pag.evaluate("() => { const c = document.querySelector('.ajusSes .cerSes');"
                         " return c ? c.textContent.trim() : null; }"), "Codex")

    revisar("sin errores de JS", errores, [])

    # --- 6. La barra del panel grande tiene las mismas tres perillas -----------------
    ctx_pc = nav.new_context(viewport={"width": 1440, "height": 900})
    pc = ctx_pc.new_page()
    errores_pc = []
    pc.on("pageerror", lambda e: errores_pc.append(str(e)))
    pc.route("**/panel-codex-prueba", lambda r: r.fulfill(
        status=200, content_type="text/html", body=html_del_panel("PAGINA")))
    pc.route("**/sesion/cerebro*", json_fijo({"ok": True, "activo": "codex",
             "defecto": "claude", "cerebros": [{"id": "claude", "nombre": "Claude"},
                                                   {"id": "codex", "nombre": "Codex"}]}))
    pc.route("**/sesion/modelo*", json_fijo({**MODELO_CLAUDE, "codex": MODELO_CODEX}))
    pc.route("**/status*", json_fijo({"servicios": {}, "encendido": False,
                                       "pausado": False, "pensando": False}))
    pc.route("**/chat*", json_fijo({"items": []}))
    pc.route("**/gasto*", json_fijo({}))
    pc.route("**/marcas*", json_fijo({}))
    pc.goto(BASE + "/panel-codex-prueba", wait_until="domcontentloaded")
    pc.wait_for_timeout(1200)
    revisar("el panel grande muestra Modelo, Esfuerzo y Velocidad de Codex",
            pc.evaluate("""() => ['selModeloCodex','selEsfuerzoCodex','selVelocidadCodex']
              .filter(id => getComputedStyle(document.getElementById(id)).display !== 'none').length"""), 3)
    revisar("el panel grande no tiene errores de JS", errores_pc, [])
    ctx_pc.close()
    nav.close()

print()
if fallas:
    print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
    sys.exit(1)
print("todo bien")
