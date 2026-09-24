"""Los dos botones de cada bloque de código: copiar y correr en PowerShell.

Pedido de Martín (2026-08-18), señalando con un recuadro la esquina de un bloque de código
adentro de una conversación: *"me gustaría ahí tener dos botones, uno para correr en
PowerShell el comando y otro para copiar el texto del comando, tal y como se puede hacer
con Claude Code"*.

⚠⚠ Correr de verdad NO se prueba apretando: abriría una ventana de PowerShell en la máquina
de Martín con lo que diga el bloque. Lo que se prueba es todo lo que se puede sin eso: que
los botones estén, que copiar copie EXACTAMENTE el comando, que correr pida confirmación
antes de hacer nada, y que recién con el segundo toque salga el pedido al servidor — que se
intercepta acá y no llega a ningún lado.

Correr con:  python -m pruebas.ver_botones_codigo   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
SID = "prueba-botones-0000"
fallas = []

CMD = "cd c:\\EspacioDeTrabajo\\MiProyecto\npython app.py"
CHARLA = {"mensajes": [
    {"de": "vos", "texto": "¿como lo levanto?"},
    {"de": "claude", "texto": "Reinicialo:\n\n```bash\n" + CMD + "\n```\n\nY listo."},
]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    pedidos = []

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1400, "height": 900},
                              permissions=["clipboard-read", "clipboard-write"])
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # ⚠ El pedido de correr se ATAJA acá: si llegara al panel abriría una ventana de
        # PowerShell de verdad en la máquina.
        def atajar(ruta):
            pedidos.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')
        pag.route("**/correr", atajar)
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        proy = pag.evaluate("""sid => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'De prueba'}];
          activa = null; grupoAbierto = ''; guardar(); irTab(sid);
          return p.cwd;
        }""", SID)
        pag.wait_for_selector("#hilo .md-bloque", timeout=15000)

        revisar("el bloque de código trae sus dos botones",
                pag.evaluate("() => [...document.querySelectorAll('#hilo .md-bt')]"
                             ".map(b => b.dataset.md)"), ["copiar", "correr"])
        # ⚠ El texto se lee del `<pre>`, no de lo que se mandó: es lo que de verdad se
        # copia y se corre, y si el dibujado del markdown le agregara algo, se vería acá.
        revisar("y el comando quedó dibujado tal cual",
                pag.evaluate("() => document.querySelector('#hilo .md-pre').textContent"),
                CMD)
        pag.screenshot(path=str(SALIDA / "botones_codigo.png"))

        # --- Copiar ---
        pag.evaluate("() => navigator.clipboard.writeText('nada')")
        pag.click('#hilo .md-bt[data-md="copiar"]')
        pag.wait_for_timeout(700)
        # ⚠ Al leerlo de vuelta, Windows devuelve los saltos de línea como `\r\n`: es del
        # portapapeles del sistema, no de lo que copiamos. Se comparan normalizados.
        revisar("copiar deja el comando en el portapapeles",
                pag.evaluate("() => navigator.clipboard.readText()").replace("\r\n", "\n"),
                CMD)
        revisar("y el botón avisa que copió",
                pag.evaluate("""() => document.querySelector('#hilo .md-bt[data-md="copiar"]')
                                 .textContent"""), "✓ copiado")

        # --- Correr: el primer toque NO corre, pregunta ---
        pag.click('#hilo .md-bt[data-md="correr"]')
        pag.wait_for_timeout(400)
        revisar("el primer toque no manda nada", pedidos, [])
        revisar("pregunta antes, en el propio botón",
                pag.evaluate("""() => document.querySelector('#hilo .md-bt[data-md="correr"]')
                                 .textContent"""), "▶ ¿corro esto?")

        # --- El segundo toque sí ---
        pag.click('#hilo .md-bt[data-md="correr"]')
        pag.wait_for_timeout(800)
        revisar("el segundo toque manda el comando entero",
                pedidos and pedidos[-1].get("cmd"), CMD)
        revisar("y lo manda a correr en la carpeta de la conversación",
                pedidos[-1].get("cwd"), proy)
        revisar("salió UN solo pedido, no dos", len(pedidos), 1)
        revisar("el botón avisa que salió",
                pag.evaluate("""() => document.querySelector('#hilo .md-bt[data-md="correr"]')
                                 .textContent"""), "✓ va")

        # --- La pregunta se cae sola si no la confirmás ---
        pag.click('#hilo .md-bt[data-md="correr"]')
        pag.wait_for_timeout(4600)
        revisar("si no confirmás, la pregunta se va sola",
                pag.evaluate("""() => !!document.querySelector('#hilo .md-bt.pregunta')"""),
                False)
        revisar("y sigue sin haberse corrido nada de más", len(pedidos), 1)

        # --- Un clic en el bloque no le abre el menú de marcas ni selecciona nada ---
        revisar("apretar los botones no dispara otra cosa de la pantalla",
                pag.evaluate("() => !!document.getElementById('menuMarcas')"), False)

        pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                guardar(); pintarTabs(); }""")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    # --- Y lo que va a ver Martín en la ventana ---
    # ⚠ Se prueba el SCRIPT, no la ventana: se le pide a PowerShell que lo corra sin
    # `-NoExit` y capturando la salida, así no se abre nada en la pantalla. Importar
    # `panel.py` tampoco prende nada (el vigilante arranca solo cuando lo sirve uvicorn,
    # misma vuelta que `probar_unir_audios.py`).
    import base64
    import subprocess

    import panel
    script = panel._script_powershell('echo "hola che"\necho segunda')
    b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", b64],
                       capture_output=True, text=True, timeout=90)
    salida = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    # Primero el comando escrito (como si lo hubieras tipeado), después lo que devuelve.
    revisar("la ventana muestra el comando antes de correrlo",
            salida[:2], ['PS> echo "hola che"', "PS> echo segunda"])
    revisar("y abajo su salida de verdad", salida[2:4], ["hola che", "segunda"])

    print()
    print("captura:", SALIDA / "botones_codigo.png")
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas) if fallas else "TODO BIEN")


if __name__ == "__main__":
    main()
