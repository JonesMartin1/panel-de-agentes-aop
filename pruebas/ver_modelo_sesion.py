"""El modelo de cada sesión y el botón de compactarla, en `/sesiones`.

Pedido de Martín (2026-08-18), el mismo día que salió de dónde venía el drenaje de
tokens: *"me gustaría dos cosas: poder elegir el modelo de Claude de manera sencilla
desde cada sesión, y poder compactar la sesión en cada sesión"*.

⚠⚠ Los dos endpoints nuevos se INTERCEPTAN acá, y por dos razones distintas:
  - `/movil/modelo` porque el panel vivo todavía no lo tiene (los endpoints de
    `panel.py` están en memoria y esta prueba corre sin reiniciarlo);
  - `/movil/compactar` porque compactar de verdad son DOS turnos de Claude contra una
    sesión real de Martín: cuesta tokens y la deja en una sesión nueva.
O sea que se prueba toda la pantalla sin tocar ni una conversación de verdad.

Correr con:  python -m pruebas.ver_modelo_sesion   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
SID = "prueba-modelo-0000"
SID_NUEVO = "prueba-modelo-compactada-1111"
fallas = []

MODELOS = {"ok": True, "modelo": "sonnet", "defecto": "opus", "modelos": [
    {"id": "opus", "nombre": "Opus (200 mil)"},
    {"id": "opus[1m]", "nombre": "Opus (1 millon)"},
    {"id": "fable", "nombre": "Fable"},
    {"id": "sonnet", "nombre": "Sonnet"},
    {"id": "haiku", "nombre": "Haiku"},
], "esfuerzo": "", "esfuerzos": [
    {"id": "", "nombre": "Esfuerzo normal"},
    {"id": "high", "nombre": "Esfuerzo alto"},
]}
CODEX = {"ok": True, "modelo": "", "defecto": "", "modelos": [],
         "cerebro": "codex", "esfuerzo": "medium", "esfuerzos": [
             {"id": "", "nombre": "Esfuerzo de fabrica"},
             {"id": "low", "nombre": "Esfuerzo bajo"},
             {"id": "medium", "nombre": "Esfuerzo medio"},
             {"id": "high", "nombre": "Esfuerzo alto"},
         ]}
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola"},
                       {"de": "claude", "texto": "hola, ¿en qué andamos?"}]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def abrir_ajustes(pag):
    """Dejar abierto el menú ⚙, donde ahora viven el cerebro, las perillas y las acciones."""
    if not pag.eval_on_selector("#ajustesModelo", "n => n.classList.contains('abierto')"):
        pag.click("#ajustesModeloBoton")
        pag.wait_for_timeout(150)


def main():
    puestos, esfuerzos_puestos, compactados = [], [], []

    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome")
        pag = nav.new_context(viewport={"width": 1400, "height": 900}).new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def modelo(ruta):
            if ruta.request.method == "POST":
                puestos.append(ruta.request.post_data_json)
                ruta.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True,
                                              "modelo": puestos[-1]["modelo"]}))
            else:
                if "cerebro=codex" in ruta.request.url or "codex-prueba" in ruta.request.url:
                    ruta.fulfill(status=200, content_type="application/json",
                                 body=json.dumps(CODEX))
                    return
                ruta.fulfill(status=200, content_type="application/json",
                             body=json.dumps(MODELOS))

        def esfuerzo(ruta):
            esfuerzos_puestos.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True,
                                          "esfuerzo": esfuerzos_puestos[-1]["esfuerzo"]}))

        def compactar(ruta):
            compactados.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True, "sid": SID_NUEVO,
                                          "resumen": "veníamos probando esto"}))

        pag.route("**/movil/modelo*", modelo)
        pag.route("**/movil/esfuerzo", esfuerzo)
        pag.route("**/movil/compactar", compactar)
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        pag.evaluate("""sid => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'De prueba'}];
          activa = null; grupoAbierto = ''; guardar(); irTab(sid);
        }""", SID)
        pag.wait_for_timeout(1800)

        # --- Un solo botón para los ajustes -------------------------------------
        revisar("los ajustes están unificados en un solo botón",
                pag.is_visible("#ajustesModeloBoton"), True)
        revisar("el selector no ocupa lugar hasta abrir el botón",
                pag.is_visible("#modelo"), False)
        revisar("y el cerebro también entró al menú (ya no es un botón suelto)",
                pag.is_visible("#cerebro"), False)
        pag.click("#ajustesModeloBoton")
        revisar("al abrirlo aparece el selector de modelo",
                pag.is_visible("#modelo"), True)
        pag.screenshot(path="resultados/ajustes_sesion_unificados.png")
        revisar("trae los cinco modelos",
                pag.evaluate("() => [...document.querySelectorAll('#modelo option')]"
                             ".map(o => o.value)"),
                ["opus", "opus[1m]", "fable", "sonnet", "haiku"])
        revisar("muestra el que dijo el servidor, no el primero",
                pag.evaluate("() => document.querySelector('#modelo').value"), "sonnet")
        # ⚠ Pintado = "esta sesión NO está en el de fábrica". Es lo único que hay que
        # poder ver de un vistazo; el estado normal no se anuncia.
        revisar("se pinta porque no es el de fábrica",
                pag.evaluate("() => document.querySelector('#modelo').classList"
                             ".contains('puesto')"), True)

        pag.select_option("#modelo", "haiku")
        pag.wait_for_timeout(700)
        revisar("elegir uno lo manda al servidor con su sesión",
                puestos[-1] if puestos else None, {"sid": SID, "modelo": "haiku"})

        # --- Compactar: dos toques ------------------------------------------------
        # ⭐ Desde el 2026-08-25 Compactar y Revisar viven ADENTRO del botón ⚙, con el
        #    resto de lo que es de esta charla (Martín: *"sería mejor que se compacten
        #    por categoría"*). Por eso hay que abrir el menú antes de tocarlos.
        abrir_ajustes(pag)
        revisar("el botón de compactar está en el menú de la charla",
                pag.is_visible("#compactar"), True)
        pag.click("#compactar")
        pag.wait_for_timeout(300)
        revisar("el primer toque NO compacta nada", len(compactados), 0)
        revisar("el primer toque pregunta",
                pag.evaluate("() => document.querySelector('#compactar').textContent"),
                "⇲ ¿compacto?")
        pag.click("#compactar")
        pag.wait_for_timeout(1500)
        revisar("el segundo toque sí manda el pedido",
                compactados[-1]["sid"] if compactados else None, SID)
        # ⭐ Lo que importa de verdad: la pestaña se MUDA a la sesión nueva. Si esto no
        # pasa, seguís escribiéndole a la charla vieja y compactar no sirvió de nada.
        revisar("la pestaña queda en la sesión nueva",
                pag.evaluate("() => abiertas[0].sid"), SID_NUEVO)
        revisar("y es la que estás mirando",
                pag.evaluate("() => activa"), SID_NUEVO)
        revisar("la dirección de la barra también",
                pag.evaluate("() => new URL(location.href).searchParams.get('c')"),
                SID_NUEVO)
        revisar("el botón vuelve a su texto",
                pag.evaluate("() => document.querySelector('#compactar').textContent"),
                "⇲ Compactar")

        # --- Una pestaña sin estrenar --------------------------------------------
        # Todavía no existe la conversación: no hay qué compactar ni dónde guardar el
        # modelo. El botón se esconde en vez de fallar cuando lo apretás.
        pag.evaluate("""() => {
          abiertas.push({sid: 'nueva-9999', cwd: abiertas[0].cwd, nombre: 'Sin estrenar'});
          irTab('nueva-9999');
        }""")
        pag.wait_for_timeout(1200)
        abrir_ajustes(pag)
        revisar("en una pestaña sin estrenar no se ofrece compactar",
                pag.is_visible("#compactar"), False)
        revisar("una charla nueva ofrece ruteo automático",
                pag.evaluate("() => [...document.querySelectorAll('#cerebro option')]"
                             ".map(o => o.value)"), ["", "codex", "auto"])
        pag.select_option("#cerebro", "auto")
        revisar("Auto queda elegido hasta analizar el primer mensaje",
                pag.evaluate("() => abiertas.find(x => x.sid === activa).cerebro"), "auto")

        # La captura de Martín era exactamente este caso: una pestaña de Codex en
        # Sesiones sin ninguna perilla para indicar cuánto debía pensar.
        pag.evaluate("""() => {
          abiertas.push({sid: 'codex-prueba', cwd: abiertas[0].cwd,
                          nombre: 'Codex de prueba', cerebro: 'codex'});
          modeloPedido = ''; irTab('codex-prueba');
        }""")
        pag.wait_for_timeout(1000)
        revisar("Codex también muestra un solo botón de ajustes",
                pag.is_visible("#ajustesModeloBoton"), True)
        revisar("Codex mantiene el esfuerzo guardado en el resumen",
                "medio" in pag.inner_text("#ajustesModeloBoton").lower(), True)
        abrir_ajustes(pag)
        revisar("Codex muestra su selector de esfuerzo al abrirlo", pag.is_visible("#esfuerzo"), True)
        revisar("y no inventa un selector de modelo", pag.is_visible("#modelo"), False)
        revisar("muestra el esfuerzo guardado", pag.input_value("#esfuerzo"), "medium")
        pag.select_option("#esfuerzo", "high")
        pag.wait_for_timeout(300)
        revisar("cambiar esfuerzo de Codex llega al servidor",
                esfuerzos_puestos[-1] if esfuerzos_puestos else None,
                {"sid": "codex-prueba", "esfuerzo": "high"})

        revisar("sin errores de JS", errores, [])
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
