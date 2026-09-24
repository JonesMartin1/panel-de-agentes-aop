"""Lo nuevo del 2026-08-25, en las DOS pantallas de verdad y con el backend de verdad.

Cuatro cosas, y las cuatro tienen que estar igual en la compu y en el celular:

  1. **Plan mode en una charla de Codex**: el selector "Plan primero" existe (estaba
     bloqueado a propósito) y la tarjeta del plan aparece con Aprobar / Seguir planeando.
  2. **Aprobar manda el turno siguiente**: en Codex el turno que dejó el plan ya murió,
     así que la decisión viaja como el mensaje que sigue. Se comprueba que salga de
     verdad por `/movil/mandar` y con qué texto.
  3. **⚡ Skills y comandos en el celular**, que era la única de las tres cajas de
     escribir sin el botón — y en una charla de Codex el menú lista los prompts de
     Codex, no las skills de Claude.
  4. **Los botones ⌕ Revisar y Avisame**, con el texto que le mandan a cada cerebro.

No necesita el panel prendido: el HTML de las dos pantallas se lee del disco (el del
celular vive adentro de `panel.py`). No manda ningún turno de verdad ni gasta un token:
`/movil/mandar` está interceptado y solo se anota qué se le pidió.

    python -m pruebas.ver_plan_codex_y_atajos
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
from app.nucleo import skills                             # noqa: E402
from app.voz import sesiones_movil as sm                   # noqa: E402

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
fallas = []

CWD = "D:\\pruebas\\alfa"
SID = "cdx-plan-1"
PLAN = "Plan: 1) tocar el CSS, 2) correr la prueba, 3) avisarte."
MANDADOS = []          # lo que las pantallas quisieron mandar como turno


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
    return {"ok": True, "laura": "",
            "carpetas": {"orden": [], "ocultas": [], "aspecto": {}, "iconosPropios": []},
            "proyectos": [{"proyecto": "alfa", "cwd": CWD, "vivo": False,
                           "sesiones": [{"id": SID, "nombre": "la de Codex", "ts": 1,
                                         "ultimo": "claude", "viva": False,
                                         "cerebro": "codex", "interactiva": False,
                                         "ocupada": False, "detalle": ""}]}]}


def chat_json():
    """El hilo, con el plan pendiente que hoy tenga el backend de verdad."""
    return {"mensajes": [{"quien": "vos", "texto": "cambiame el color", "ts": 1},
                         {"quien": "claude", "texto": PLAN, "ts": 2}],
            "ocupada": False, "pregunta": sm.pregunta_de(CWD, SID), "tareas": None}


def anotar_mandado(r):
    """`/movil/mandar` interceptado: se anota el texto y se contesta que salió bien."""
    datos = r.request.post_data or ""
    for trozo in datos.split("name=\"texto\""):
        pass
    MANDADOS.append(datos)
    return r.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "sid": SID, "respuesta": "listo",
                                      "cerebro": "codex", "modelo": "", "esfuerzo": "",
                                      "velocidad": "", "pide_compactar": None}))


def montar(pag):
    pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                          body="{}"))
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
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(chat_json())))
    # ⭐ Backend de verdad: el mismo que corre el panel.
    pag.route("**/movil/modelo?*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(panel.movil_modelo_leer(sid=SID, cwd=CWD))))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(panel.skills_de_sesion(sid=SID, cwd=CWD))))
    pag.route("**/movil/plan", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(decidir(r.request.post_data_json or {}))))
    pag.route("**/movil/mandar", anotar_mandado)


def decidir(d):
    """Lo mismo que hace `/movil/plan` con una charla de Codex, sin el async."""
    texto = sm.responder_plan_codex(CWD, SID, bool(d.get("aprobar")),
                                    (d.get("comentario") or "").strip())
    if texto is None:
        return {"ok": False, "error": "Ese plan ya no está esperando respuesta."}
    return {"ok": True, "mandar": texto}


def sembrar_plan():
    """Deja un plan de Codex esperando, como después de un turno en modo plan."""
    sm.poner_modo(SID, "plan")
    sm._anotar_plan_codex(CWD, SID, PLAN)


with sync_playwright() as p:
    tmp = Path(tempfile.mkdtemp(prefix="plan_codex_ver_"))
    sm.AJUSTES_SESIONES = tmp / "ajustes_sesiones.json"
    sm._CODEX_SIDS[SID] = {"ruta": str(tmp / "no-existe.jsonl")}
    skills.CARPETA_PROMPTS_CODEX = tmp / "prompts"
    (tmp / "prompts").mkdir()
    (tmp / "prompts" / "deploy.md").write_text(
        "---\ndescription: Subir al VPS\n---\nHacelo.", encoding="utf-8")
    HTML_MOVIL = movil_html()
    nav = p.chromium.launch(channel="chrome", headless=True)

    # --- 1. La compu -----------------------------------------------------------------
    print("\n--- 1. La compu, en una charla de Codex ---")
    sembrar_plan()
    MANDADOS.clear()
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    montar(pag)
    pag.add_init_script("localStorage.clear(); localStorage.setItem('sesTabs',"
                        + json.dumps(json.dumps([{"sid": SID, "cwd": CWD,
                                                  "nombre": "la de Codex",
                                                  "cerebro": "codex"}])) + ");")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    # La pestaña existe pero ninguna está elegida hasta que se entra a una.
    pag.wait_for_timeout(1200)
    pag.evaluate("([cwd, sid]) => abrirSesion(cwd, sid, 'la de Codex', false, 'codex')",
                 [CWD, SID])
    pag.wait_for_selector(".pregunta.plan", timeout=15000)

    revisar("el selector de Modo se ve en una charla de Codex",
            pag.eval_on_selector("#modo", "e => e.options.length >= 2"), True)
    revisar("con 'Plan primero' adentro",
            pag.eval_on_selector("#modo", "e => [...e.options].some(o => /Plan/.test(o.text))"),
            True)
    revisar("la tarjeta NO repite el plan entero (ya se lee arriba)",
            pag.eval_on_selector(".pregunta.plan .pPlan", "e => e.textContent.includes('acá arriba')"),
            True)
    revisar("y están los dos botones de decidir",
            pag.eval_on_selector(".pregunta.plan",
                                 "e => !!e.querySelector('.pAprueba') && !!e.querySelector('.pSigue')"),
            True)
    revisar("el botón ⌕ Revisar existe", pag.locator("#revisar").count(), 1)
    # ⭐ Desde el 2026-08-25 Revisar vive adentro del ⚙, con lo demás de la charla, y
    #    Avisame quedó como campanita suelta: es una opción del envío y tiene que verse
    #    encendida sin abrir nada (pedido de Martín, *"que se compacten por categoría"*).
    revisar("y está adentro del menú de la charla",
            pag.eval_on_selector("#revisar", "e => !!e.closest('.ajustes-modelo-menu')"), True)
    revisar("el botón Avisame existe", pag.locator("#avisarTarea").count(), 1)
    revisar("y sigue a la vista, afuera del menú",
            pag.is_visible("#avisarTarea"), True)
    pag.click("#avisarTarea")
    revisar("y se enciende al tocarlo",
            pag.eval_on_selector("#avisarTarea", "e => e.classList.contains('sel')"), True)

    print("\n--- 2. Aprobar el plan manda el turno siguiente ---")
    pag.click(".pregunta.plan .pAprueba")
    pag.wait_for_timeout(900)
    revisar("salió UN turno", len(MANDADOS), 1)
    revisar("con el mensaje de aprobado", "Aprobado" in (MANDADOS[0] if MANDADOS else ""),
            True)
    revisar("⭐ y la charla salió de plan mode", sm.modo_de(SID), "")
    revisar("sin errores de JS en la compu", errores, [])

    print("\n--- 3. ⌕ Revisar, en la compu ---")
    MANDADOS.clear()
    if not pag.eval_on_selector("#ajustesModelo", "n => n.classList.contains('abierto')"):
        pag.click("#ajustesModeloBoton")
        pag.wait_for_timeout(150)
    pag.click("#revisar")
    pag.wait_for_timeout(900)
    revisar("mandó el pedido de revisión", len(MANDADOS), 1)
    # Apretar una acción cierra el menú: ya está hecho y lo que sigue pasa en el hilo.
    revisar("y el menú se cerró solo",
            pag.eval_on_selector("#ajustesModelo", "n => n.classList.contains('abierto')"),
            False)
    revisar("y a Codex se lo pide en criollo, no con la skill de Claude",
            "code-review" not in (MANDADOS[0] if MANDADOS else "")
            and "commite" in (MANDADOS[0] if MANDADOS else ""), True)
    ctx.close()

    # --- 4. El celular ----------------------------------------------------------------
    print("\n--- 4. El celular, la misma charla ---")
    sembrar_plan()
    MANDADOS.clear()
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                          is_mobile=True, device_scale_factor=3)
    cel = ctx.new_page()
    errores_cel = []
    cel.on("pageerror", lambda e: errores_cel.append(str(e)))
    montar(cel)
    cel.add_init_script("localStorage.clear();"
                        "localStorage.setItem('pestanas', " + json.dumps(json.dumps(
                            [{"sid": SID, "cwd": CWD, "nombre": "la de Codex"}]))
                        + "); localStorage.setItem('activa', " + json.dumps(SID) + ");")
    cel.goto(BASE + "/movil", wait_until="domcontentloaded")
    cel.wait_for_selector(".pregunta.plan", timeout=15000)

    revisar("el selector de Modo también está en el teléfono",
            cel.evaluate("""() => [...document.querySelectorAll('.ajusSes select')]
                              .some(s => [...s.options].some(o => /Plan/.test(o.text)))"""),
            True)
    revisar("la tarjeta tampoco repite el plan entero",
            cel.eval_on_selector(".pregunta.plan .pPlan",
                                 "e => e.textContent.includes('acá arriba')"), True)
    revisar("el botón ⌕ Revisar está en el encabezado",
            cel.evaluate("""() => [...document.querySelectorAll('.ajusSes button')]
                              .some(b => /Revisar/.test(b.textContent))"""), True)
    # ⚠ La perilla nueva hizo que las cuatro se aplastaran hasta quedar en la flechita
    # sola: la fila se desliza, así que no hay excusa para dejarlas ilegibles.
    revisar("y las perillas siguen siendo legibles, no pastillas vacías",
            cel.evaluate("""() => [...document.querySelectorAll('.ajusSes select')]
                              .every(s => s.getBoundingClientRect().width >= 80)"""), True)

    print("\n--- 5. ⚡ Skills y comandos, que en el celular no existía ---")
    revisar("el botón ⚡ está en la caja de escribir",
            cel.locator("#atajosAqui button.at-boton").count(), 1)
    revisar("y entra en el renglón sin partirlo en dos",
            cel.evaluate("""() => {
              const c = document.querySelector('#escribir');
              return c.scrollHeight <= c.clientHeight + 2;
            }"""), True)
    cel.tap("#atajosAqui button.at-boton")
    cel.wait_for_selector(".at-menu", timeout=8000)
    cel.wait_for_timeout(600)
    revisar("en una charla de Codex el menú ofrece SUS prompts",
            cel.eval_on_selector(".at-menu", "e => e.textContent.includes('Prompts de Codex')"),
            True)
    revisar("con el que está creado",
            cel.eval_on_selector(".at-menu", "e => e.textContent.includes('/deploy')"), True)
    revisar("y NO ofrece skills de Claude, que ahí no andan",
            cel.eval_on_selector(".at-menu", "e => e.textContent.includes('/security-review')"),
            False)
    revisar("dice dónde se crean los prompts",
            cel.eval_on_selector(".at-menu", "e => e.textContent.includes('prompts')"), True)
    cel.keyboard.press("Escape")

    print("\n--- 6. Aprobar el plan, desde el teléfono ---")
    cel.tap(".pregunta.plan .pAprueba")
    cel.wait_for_timeout(900)
    revisar("salió UN turno", len(MANDADOS), 1)
    revisar("con el mensaje de aprobado", "Aprobado" in (MANDADOS[0] if MANDADOS else ""),
            True)
    revisar("y la charla salió de plan mode", sm.modo_de(SID), "")
    revisar("sin errores de JS en el celular", errores_cel, [])

    cel.screenshot(path=str(RAIZ / "pruebas" / "plan_codex_movil.png"), full_page=False)
    ctx.close()
    nav.close()

    print()
    if fallas:
        print("FALLÓ:", len(fallas))
        for f in fallas:
            print("  -", f)
        sys.exit(1)
    print("TODO BIEN")
