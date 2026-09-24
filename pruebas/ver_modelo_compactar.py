"""Elegir el modelo de cada sesión y compactarla, en `/sesiones`.

Pedido de Martín (2026-08-18), el mismo día que apareció de dónde salía el drenaje de
tokens: su configuración global tenía el modelo en `opus[1m]` —la ventana de un millón—,
así que ninguna charla se compactaba nunca y cada comando releía la conversación entera.
Pidió tres cosas: *"poder elegir el modelo de Claude de manera sencilla desde cada
sesión"*, *"poder compactar la sesión"* y *"que también avise cuando estoy ocupando
muchos tokens y cuando sea buena idea compactar"*.

⭐ El servidor está INVENTADO acá (`page.route`), igual que en `ver_marcas_texto.py`:
`/movil/modelo` y `/movil/compactar` viven en `panel.py` y no existen hasta reiniciarlo.
Así esto corre con el panel viejo prendido, sin compactar ninguna sesión de verdad —que
además costaría dos turnos de Claude— y sin reiniciar nada.

⚠ Compactar de verdad NO se prueba apretando el botón hasta el final: se intercepta el
pedido. Igual que el ▶ de los bloques de código, que abriría una ventana de PowerShell.

Correr con:  python -m pruebas.ver_modelo_compactar   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
SID = "prueba-modelo-0000"
SID_NUEVO = "prueba-modelo-compactada-1111"
fallas = []

CHARLA = {"mensajes": [
    {"de": "vos", "texto": "arreglame el panel"},
    {"de": "claude", "texto": "Listo, quedó arreglado."},
]}

MODELOS = [{"id": "opus", "nombre": "Opus (200 mil)"},
           {"id": "opus[1m]", "nombre": "Opus (1 millon)"},
           {"id": "sonnet", "nombre": "Sonnet"},
           {"id": "haiku", "nombre": "Haiku"}]
MODELOS_CODEX = [{"id": "gpt-5.6-sol", "nombre": "GPT-5.6 Sol"},
                 {"id": "gpt-5.6-luna", "nombre": "GPT-5.6 Luna"}]
ESFUERZOS_CODEX = [{"id": "", "nombre": "Esfuerzo de fábrica"},
                   {"id": "high", "nombre": "Esfuerzo alto"}]
VELOCIDADES_CODEX = [{"id": "", "nombre": "Velocidad estándar"},
                     {"id": "priority", "nombre": "Velocidad rápida"}]


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def abrir_ajustes(pag):
    """Dejar abierto el menú ⚙: ahí adentro viven el cerebro, las perillas y las acciones."""
    if not pag.eval_on_selector("#ajustesModelo", "n => n.classList.contains('abierto')"):
        pag.click("#ajustesModeloBoton")
        pag.wait_for_timeout(150)


def main():
    # El "servidor": con qué modelo corre la sesión y cuánto contexto arrastra.
    estado = {"modelo": "opus", "modelo_codex": "gpt-5.6-sol",
              "esfuerzo_codex": "", "velocidad_codex": "",
              "tokens": 40_000, "nivel": "", "aviso": ""}
    guardados = []          # los POST de modelo que llegaron
    esfuerzos_guardados = []
    velocidades_guardadas = []
    compactados = []        # los pedidos de compactar que llegaron

    def ruta_modelo(ruta):
        req = ruta.request
        if req.method == "GET":
            es_codex = "cerebro=codex" in req.url
            if es_codex:
                ruta.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"ok": True, "cerebro": "codex",
                     "modelo": estado["modelo_codex"], "modelos": MODELOS_CODEX,
                     "defecto": "gpt-5.6-sol", "esfuerzo": estado["esfuerzo_codex"],
                     "esfuerzos": ESFUERZOS_CODEX,
                     "velocidad": estado["velocidad_codex"],
                     "velocidades": VELOCIDADES_CODEX, "modos": [], "contexto": None}))
                return
            ruta.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"ok": True, "modelo": estado["modelo"], "modelos": MODELOS,
                 "defecto": "opus",
                 "contexto": {"tokens": estado["tokens"], "tope": 200_000,
                              "nivel": estado["nivel"], "aviso": estado["aviso"]}}))
            return
        d = req.post_data_json or {}
        guardados.append(d)
        estado["modelo"] = d.get("modelo", "opus")
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "modelo": estado["modelo"]}))

    def ruta_esfuerzo(ruta):
        d = ruta.request.post_data_json or {}
        esfuerzos_guardados.append(d)
        estado["esfuerzo_codex"] = d.get("esfuerzo", "")
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "esfuerzo": estado["esfuerzo_codex"]}))

    def ruta_velocidad(ruta):
        d = ruta.request.post_data_json or {}
        velocidades_guardadas.append(d)
        estado["velocidad_codex"] = d.get("velocidad", "")
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "velocidad": estado["velocidad_codex"]}))

    def ruta_compactar(ruta):
        compactados.append(ruta.request.post_data_json or {})
        ruta.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "sid": SID_NUEVO, "resumen": "veníamos arreglando el panel"}))

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # ⚠ El orden importa y al revés de lo que uno escribe: Playwright prueba las
        # rutas de la ÚLTIMA a la primera, así que la específica va después.
        # ⚠ La bandeja va inventada desde el 2026-08-25: `/movil/sesiones` del panel de
        # verdad puede tardar minutos cuando hay una charla de Codex con un rollout
        # gigante creciendo, y esta prueba mide el selector de modelo, no el panel.
        pag.route("**/movil/sesiones*", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "laura": "", "proyectos": [
                {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False, "sesiones": [
                    {"id": SID, "nombre": "De prueba", "ts": 2, "ultimo": "vos",
                     "viva": False, "interactiva": False, "detalle": ""}]}]})))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        pag.route("**/movil/modelo*", ruta_modelo)
        pag.route("**/movil/esfuerzo", ruta_esfuerzo)
        pag.route("**/movil/velocidad", ruta_velocidad)
        pag.route("**/movil/compactar", ruta_compactar)

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)

        # Una pestaña de mentira parada en un proyecto de verdad.
        pag.evaluate("""sid => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'De prueba'}];
          grupoAbierto = ''; activa = null; guardar();
          irTab(sid);
        }""", SID)
        pag.wait_for_selector("#hilo [data-msg]", timeout=15000)
        pag.wait_for_timeout(1200)

        # --- El selector de modelo ---
        # ⚠ Las perillas viven adentro del botón ⚙ desde que se unificaron (2026-08-18);
        # el 2026-08-25 entraron ahí también el cerebro y las acciones. Sin abrir ese
        # menú no se puede tocar ninguna: esta prueba se había quedado sin abrirlo.
        abrir_ajustes(pag)
        revisar("el selector ofrece los cuatro modelos",
                pag.evaluate("() => [...document.querySelectorAll('#modelo option')]"
                             ".map(o => o.value)"),
                ["opus", "opus[1m]", "sonnet", "haiku"])
        revisar("y muestra el que tiene puesto la sesión",
                pag.evaluate("() => document.getElementById('modelo').value"), "opus")
        # Apagado en el de fábrica: lo que hay que ver de un vistazo es cuando NO lo está.
        revisar("con el de fábrica no se pinta",
                pag.evaluate("() => document.getElementById('modelo').classList.contains('puesto')"),
                False)

        # Elegir otro tiene que llegar al servidor y quedar pintado.
        pag.select_option("#modelo", "haiku")
        pag.wait_for_timeout(700)
        revisar("elegir un modelo lo guarda en el servidor",
                [g.get("modelo") for g in guardados], ["haiku"])
        revisar("y lo manda con el id de la sesión",
                guardados[0].get("sid") if guardados else None, SID)
        revisar("elegido uno distinto al de fábrica, se pinta",
                pag.evaluate("() => document.getElementById('modelo').classList.contains('puesto')"),
                True)

        # --- Las tres perillas de Codex ---
        pag.evaluate("""() => {
          abiertas[0].cerebro='codex'; abiertas[0].modelo=''; abiertas[0].esfuerzo='';
          abiertas[0].velocidad=''; modeloPedido=''; refrescarModelo();
        }""")
        pag.wait_for_timeout(700)
        revisar("Codex muestra su selector de modelo", pag.evaluate(
            "() => [...document.querySelectorAll('#modelo option')].map(o=>o.value)"),
            ["gpt-5.6-sol", "gpt-5.6-luna"])
        revisar("Codex muestra su selector de esfuerzo", pag.evaluate(
            "() => [...document.querySelectorAll('#esfuerzo option')].map(o=>o.value)"),
            ["", "high"])
        revisar("Codex muestra Estándar y Rápida", pag.evaluate(
            "() => [...document.querySelectorAll('#velocidad option')].map(o=>o.value)"),
            ["", "priority"])
        pag.select_option("#velocidad", "priority")
        pag.wait_for_timeout(300)
        revisar("la velocidad se guarda con el id de la sesión",
                velocidades_guardadas[-1] if velocidades_guardadas else {},
                {"sid": SID, "velocidad": "priority"})
        # El resto de esta prueba mide Compactar, que pertenece a Claude.
        pag.evaluate("""() => {
          abiertas[0].cerebro=''; abiertas[0].modelo=''; abiertas[0].esfuerzo='';
          abiertas[0].velocidad=''; modeloPedido=''; refrescarModelo();
        }""")
        pag.wait_for_timeout(700)

        # --- El aviso de cuánto arrastra la charla ---
        # ⭐ Es lo que se relee en CADA mensaje, no lo que gastó en total: ese número es
        # el que se vuelve a pagar con cada comando y cada archivo que abre.
        revisar("con poco contexto el aviso queda apagado",
                pag.evaluate("() => document.getElementById('contexto').className"), "ctx bien")
        revisar("y dice cuánto arrastra",
                pag.evaluate("() => document.getElementById('contexto').textContent"), "40 k")

        estado.update(tokens=160_000, nivel="medio", aviso="Ya va por 160 mil de contexto")
        pag.evaluate("() => { modeloPedido = ''; refrescarModelo(); }")
        pag.wait_for_timeout(700)
        revisar("pasado el umbral, el chip avisa", pag.evaluate(
            "() => document.getElementById('contexto').className"), "ctx medio")
        revisar("el botón todavía no se enciende (avisa, no apura)", pag.evaluate(
            "() => document.getElementById('compactar').classList.contains('conviene')"), False)

        estado.update(tokens=555_000, nivel="mucho",
                      aviso="Esta charla arrastra 555 mil en cada mensaje: compactala.")
        pag.evaluate("() => { modeloPedido = ''; refrescarModelo(); }")
        pag.wait_for_timeout(700)
        revisar("con mucho contexto el chip lo grita", pag.evaluate(
            "() => document.getElementById('contexto').className"), "ctx mucho")
        revisar("y ahí sí se enciende el botón Compactar", pag.evaluate(
            "() => document.getElementById('compactar').classList.contains('conviene')"), True)
        revisar("el aviso completo está a mano en el título", pag.evaluate(
            "() => document.getElementById('contexto').title"),
            "Esta charla arrastra 555 mil en cada mensaje: compactala.")
        # ⚠⚠ El aspecto elegido (`aspecto.js`) pinta `.caja button` con el color de
        # acento de Martín, y ese acento puede ser cualquier cosa. Si le gana al aviso,
        # el botón encendido se ve IGUAL que apagado y el aviso no avisa nada. Se mide
        # el color de verdad, no la clase: la clase estaba bien y el color podía no.
        colores = pag.evaluate("""() => {
          const c = x => getComputedStyle(document.getElementById(x)).color;
          return {chip: c('contexto'), boton: c('compactar'), enviar:
                  getComputedStyle(document.querySelector('.caja button:last-child')).color};
        }""")
        print("    colores:", colores)
        revisar("el chip de aviso no queda del color de acento",
                colores["chip"] != colores["enviar"], True)
        revisar("y el botón encendido tampoco",
                colores["boton"] != colores["enviar"], True)
        pag.screenshot(path=str(SALIDA / "modelo_compactar.png"))

        # --- Compactar: dos toques ---
        # ⚠ El primero solo pregunta. Esto deja la pestaña en una sesión NUEVA y cuesta
        # dos turnos de Claude: un clic de más no puede alcanzar.
        # ⭐ Desde el 2026-08-25 el botón vive adentro del ⚙, con el resto de lo que es de
        #    esta charla, así que primero hay que abrir ese menú.
        abrir_ajustes(pag)
        pag.click("#compactar")
        pag.wait_for_timeout(300)
        revisar("el primer toque pregunta y no manda nada", compactados, [])
        revisar("y el botón lo dice", pag.evaluate(
            "() => document.getElementById('compactar').textContent"), "⇲ ¿compacto?")

        pag.click("#compactar")
        pag.wait_for_timeout(1500)
        revisar("el segundo toque sí compacta",
                [c.get("sid") for c in compactados], [SID])
        revisar("y manda la carpeta, que es donde corre el turno",
                bool(compactados and compactados[0].get("cwd")), True)
        revisar("la pestaña se muda a la sesión nueva",
                pag.evaluate("() => (abiertas[0]||{}).sid"), SID_NUEVO)
        revisar("y es la que estás mirando",
                pag.evaluate("() => activa"), SID_NUEVO)
        # La vieja no se cierra ni se borra: sigue en la bandeja, entera.
        revisar("no queda ninguna pestaña colgada de la sesión vieja",
                pag.evaluate("() => abiertas.filter(t => t.sid === '%s').length" % SID), 0)

        # --- Una charla sin estrenar no tiene qué compactar ---
        pag.evaluate("""() => {
          const p = datos.proyectos[0];
          abiertas = [{sid: 'nueva-999', cwd: p.cwd, nombre: 'Sin estrenar'}];
          activa = null; guardar(); irTab('nueva-999');
        }""")
        pag.wait_for_timeout(1200)
        revisar("en una pestaña sin estrenar, el botón Compactar no está",
                pag.evaluate("() => document.getElementById('compactar').style.display"), "none")

        revisar("ningún error de JS en toda la prueba", errores, [])
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} cosas mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
