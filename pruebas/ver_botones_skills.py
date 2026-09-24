"""El botón unificado de Skills/Comandos y Buscar archivo en `/sesiones`.

Pedido de Martín (2026-08-18): *"que me aparezcan las opciones del Cloud que suelen
aparecer cuando escribo la barrita... un botón para desplegar las skills y un botón
para desplegar los comandos"*, y que el de skills marque cuáles ya usó esa sesión y
cuál está corriendo ahora.

⚠ `GET /skills` se INTERCEPTA: el panel vivo todavía no tiene el endpoint (está en
memoria hasta el reinicio), así que la prueba corre sin reiniciarlo — y de paso las
marcas de "usada" y "en uso" se prueban con datos armados, no con lo que justo haya
hecho una sesión de verdad.

Correr con:  python -m pruebas.ver_botones_skills   (con el panel prendido)
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
# ⚠ El panel vivo tampoco tiene la ruta /estaticos/atajos.js hasta el reinicio: se
# sirve desde el disco acá, así la prueba corre sin reiniciar nada.
ATAJOS = Path(__file__).resolve().parents[1] / "app" / "estaticos" / "atajos.js"
SID = "prueba-skills-0000"
fallas = []

# Las cuatro combinaciones que puede haber, una por skill:
#   graphify  corriendo AHORA (y además usada en el proyecto)
#   avisar    usada en ESTA charla (y además en el proyecto)
#   leeme     usada en el PROYECTO pero todavía no en esta charla  ← lo nuevo
#   notas     nunca, en ningún lado
#
# Y desde el 2026-08-23 se prueban además las dos cosas que hacían que una skill recién
# hecha no apareciera nunca: `rotas` (la carpeta está pero le falta el SKILL.md) y
# `comandos` (los propios de ~/.claude/commands, que antes ni se pedían).
SKILLS = {"ok": True, "usadas": ["avisar", "graphify"], "corriendo": "graphify",
          "proyecto": {"graphify": 12, "avisar": 8, "leeme": 5},
          "skills": [
              {"nombre": "graphify", "descripcion": "Cualquier cosa a grafo."},
              {"nombre": "avisar", "descripcion": "Tocarle el timbre a Martín."},
              {"nombre": "leeme", "descripcion": "Ponerle voz a un artefacto."},
              {"nombre": "notas", "descripcion": "Dejar al día el cuaderno."},
          ],
          "rotas": ["tresde"],
          "comandos": [{"nombre": "limpiar", "descripcion": "Dejar el escritorio prolijo."}]}
MODELOS = {"ok": True, "modelo": "opus", "defecto": "opus",
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]}
CHARLA = {"mensajes": [{"de": "vos", "texto": "hola"},
                       {"de": "claude", "texto": "acá andamos"}]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    pedidos, archivos = [], []

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_context(viewport={"width": 1400, "height": 900}).new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def skills(ruta):
            pedidos.append(ruta.request.url)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps(SKILLS))

        def elegir_archivo(ruta):
            archivos.append(ruta.request.url)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True, "ruta": "docs/informe.pdf",
                                          "relativa": True}))

        pag.route("**/estaticos/atajos.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript",
            body=ATAJOS.read_text(encoding="utf-8")))
        pag.route("**/skills*", skills)
        pag.route("**/movil/elegir_archivo*", elegir_archivo)
        pag.route("**/movil/modelo*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(MODELOS)))
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
        pag.wait_for_timeout(1500)

        # --- Una sola puerta para Skills y Comandos ------------------------------
        revisar("skills y comandos tienen un solo botón", pag.is_visible("#btnAtajos"), True)
        revisar("ya no quedan los dos botones viejos",
                pag.locator("#btnSkills, #btnComandos").count(), 0)
        # ⚠ Medido en color computado, no en clases: `.caja button` pinta todos los
        # botones como Enviar, y si le ganara al estilo propio se verían iguales.
        revisar("no se visten como el botón de Enviar",
                pag.evaluate("""() => {
                  const mio = getComputedStyle(document.querySelector('#btnAtajos')).backgroundColor;
                  const enviar = getComputedStyle(document.querySelector(
                      '.caja button[onclick=\"mandar()\"]')).backgroundColor;
                  return mio !== enviar;
                }"""), True)

        # --- Buscar un archivo pega su ruta relativa -----------------------------
        # ⭐ Desde el 2026-08-25 los tres de "traer algo al mensaje" van pegados y con el
        #    dibujito solo (pedido de Martín: *"sería mejor que se compacten por
        #    categoría"*). El nombre entero tiene que quedar en el globito de ayuda: sin
        #    eso, un botón con un emoji y nada más no se entiende.
        revisar("Subir imagen es solo el dibujito", pag.inner_text("#subirImagen"), "🖼")
        revisar("y el nombre está en el globito",
                "Subir imagen" in pag.get_attribute("#subirImagen", "title"), True)
        revisar("Buscar archivo es solo el dibujito", pag.inner_text("#buscarArchivo"), "🔎")
        revisar("y su nombre también está en el globito",
                "Buscar archivo" in pag.get_attribute("#buscarArchivo", "title"), True)
        revisar("los tres van juntos en el mismo grupo",
                pag.eval_on_selector_all("#grupoTraer > *", "n => n.length"), 3)
        pag.click("#buscarArchivo")
        pag.wait_for_timeout(200)
        revisar("el selector recibe la carpeta de esta charla",
                bool(archivos) and "cwd=" in archivos[-1], True)
        revisar("la ruta relativa queda escrita en el mensaje",
                pag.input_value("#texto"), "`docs/informe.pdf`")
        pag.fill("#texto", "")

        # --- El menú unificado ---------------------------------------------------
        pag.click("#btnAtajos")
        pag.wait_for_selector(".at-menu .fila.skill", timeout=5000)
        revisar("pide las skills con la sesión y su carpeta",
                bool(pedidos) and ("sid=" + SID) in pedidos[-1]
                and "cwd=" in pedidos[-1], True)
        revisar("lista las cuatro skills",
                pag.evaluate("() => [...document.querySelectorAll('.at-menu .fila.skill .nombre')]"
                             ".map(e => e.textContent)"),
                ["/graphify", "/avisar", "/leeme", "/notas"])
        pag.screenshot(path="resultados/skills_comandos_archivos_unificados.png")
        revisar("la que está corriendo dice '● en uso'",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/graphify')
                  .querySelector('.chapa').textContent"""), "● en uso")
        revisar("la ya usada dice '✓ usada'",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/avisar')
                  .querySelector('.chapa').textContent"""), "✓ usada")
        revisar("la nunca usada, en ningún lado, no lleva chapa",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/notas').querySelector('.chapa')"""), None)

        # ⭐ Lo del pedido del 2026-08-18: usada EN EL PROYECTO aunque esta charla
        # todavía no la haya tocado. Sin esto, una conversación recién abierta
        # mostraba las trece skills en blanco.
        revisar("la usada en el proyecto queda marcada con cuántas veces",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/leeme')
                  .querySelector('.chapa').textContent"""), "✓ 5")
        revisar("y esa marca es la apagada, no la de esta charla",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/leeme')
                  .querySelector('.chapa').classList.contains('proy')"""), True)
        revisar("el título explica que es del proyecto, no de esta charla",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/leeme')
                  .querySelector('.chapa').title.includes('en este proyecto')"""), True)
        # ⚠ Las tres marcas tienen que verse DISTINTAS: si el color de "usada en el
        # proyecto" fuera el mismo que el de "usada en esta charla", marcar de más
        # sería igual que no marcar nada.
        revisar("las tres marcas se ven de colores distintos",
                pag.evaluate("""() => {
                  const c = id => getComputedStyle([...document.querySelectorAll(
                    '.at-menu .fila')].find(f => f.dataset.id === id)
                    .querySelector('.chapa')).color;
                  return new Set([c('/graphify'), c('/avisar'), c('/leeme')]).size;
                }"""), 3)
        # Esta charla le GANA al proyecto: /avisar está en los dos y muestra "usada".
        revisar("lo de esta charla le gana a lo del proyecto",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/avisar')
                  .querySelector('.chapa').classList.contains('proy')"""), False)

        # --- ⭐ "La creé y no aparece" (2026-08-23) --------------------------------
        # Una carpeta de skill sin SKILL.md adentro sale avisada al final de la lista,
        # en vez de desaparecer callada.
        revisar("la carpeta sin SKILL.md aparece avisada",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila.rota')]
                  .map(f => f.querySelector('.nombre').textContent)"""), ["tresde"])
        revisar("y dice qué le falta",
                pag.evaluate("""() => document.querySelector('.at-menu .fila.rota .chapa')
                  .textContent"""), "⚠ sin SKILL.md")
        # No es un rojo de "se rompió algo": es ámbar de "andá a acomodar un archivo".
        revisar("el aviso no está pintado de rojo",
                pag.evaluate("""() => getComputedStyle(document.querySelector(
                  '.at-menu .fila.rota .chapa')).backgroundColor"""), "rgb(42, 33, 23)")
        revisar("no se cuenta como una skill invocable",
                pag.evaluate("() => document.querySelectorAll('.at-menu .fila.skill').length"), 4)

        # Un comando propio de ~/.claude/commands, atrás de los seis de siempre.
        revisar("el comando propio está en la lista de comandos",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila.comando')]
                  .map(f => f.dataset.id).includes('/limpiar')"""), True)
        revisar("y se distingue de los de siempre",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/limpiar')
                  .querySelector('.chapa').textContent"""), "tuyo")

        # Tocar una la escribe en la caja de texto, lista para completar.
        pag.click(".at-menu .fila[data-id='/notas']")
        pag.wait_for_timeout(200)
        revisar("tocarla la escribe en la caja",
                pag.evaluate("() => document.querySelector('#texto').value"), "/notas ")
        revisar("y el menú se cierra",
                pag.evaluate("() => document.querySelector('.at-menu')"), None)

        # ⚠ La segunda y la tercera vez también: la lección de marcas.js — una escucha
        # zombi de un menú mal cerrado se come el clic del siguiente.
        pag.click("#btnAtajos")
        pag.wait_for_selector(".at-menu .fila.skill", timeout=5000)
        revisar("el menú abre de nuevo tras haberse cerrado",
                pag.evaluate("() => document.querySelectorAll('.at-menu .fila').length"),
                len(SKILLS["skills"]) + len(SKILLS["rotas"])
                + 6 + len(SKILLS["comandos"]))
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(200)
        revisar("Escape lo cierra",
                pag.evaluate("() => document.querySelector('.at-menu')"), None)
        pag.click("#btnAtajos")
        pag.wait_for_selector(".at-menu .fila", timeout=5000)
        pag.click("#cuerpo")
        pag.wait_for_timeout(200)
        revisar("tocar afuera lo cierra",
                pag.evaluate("() => document.querySelector('.at-menu')"), None)

        # --- El menú de comandos --------------------------------------------------
        pag.evaluate("() => { document.querySelector('#texto').value = ''; }")
        pag.click("#btnAtajos")
        # ⚠ Se espera una fila de SKILL, no una cualquiera: mientras dice "Leyendo…" ya
        # están dibujados los seis comandos de siempre, pero los tuyos vienen con la
        # respuesta del servidor y todavía no llegaron.
        pag.wait_for_selector(".at-menu .fila.skill", timeout=5000)
        revisar("el mismo menú incluye los seis comandos y el propio",
                pag.evaluate("() => document.querySelectorAll('.at-menu .fila.comando').length"),
                6 + len(SKILLS["comandos"]))
        revisar("los que acá son un botón lo dicen",
                pag.evaluate("""() => [...document.querySelectorAll('.at-menu .fila')]
                  .find(f => f.dataset.id === '/compact')
                  .querySelector('.chapa').textContent"""), "se hace aca")
        # /compact NO se escribe (mandado como texto el CLI lo ignora): aprieta el
        # botón Compactar de la pantalla, que arranca su flujo de dos toques.
        pag.click(".at-menu .fila[data-id='/compact']")
        pag.wait_for_timeout(400)
        revisar("/compact aprieta el botón Compactar (que pregunta)",
                pag.evaluate("() => document.querySelector('#compactar').textContent"),
                "⇲ ¿compacto?")
        revisar("y no escribió nada en la caja",
                pag.evaluate("() => document.querySelector('#texto').value"), "")
        pag.wait_for_timeout(5300)          # que el "¿compacto?" se caiga solo

        # /init sí es una skill que viaja como texto: se escribe en la caja.
        pag.click("#btnAtajos")
        pag.wait_for_selector(".at-menu .fila", timeout=5000)
        pag.click(".at-menu .fila[data-id='/init']")
        pag.wait_for_timeout(200)
        revisar("/init se escribe en la caja",
                pag.evaluate("() => document.querySelector('#texto').value"), "/init ")

        revisar("sin errores de JS", errores, [])
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
