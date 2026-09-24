"""El tamaño de los botones de /sesiones, y que no crezcan con el zoom.

Pedido de Martín el 2026-09-12, con una captura de `/sesiones` ampliada: *"me gustaría poder
encojer más los botones de la interfaz, o que queden en un tamaño fijo cuando llego a cierto
grado de zoom"*. El texto de las conversaciones ya tenía su multiplicador (`--escala`), pero
los controles estaban escritos en píxeles fijos (38 px de alto, 14 px de letra): crecían tal
cual con el zoom y no había con qué achicarlos.

Lo que se mide acá:
  · con todo en "Normales" la barra queda EXACTAMENTE como estaba (38 px). Es lo primero:
    una perilla nueva no puede moverle la pantalla a quien no elige nada;
  · "Mínimos" achica de verdad y el lugar que se libera se lo queda la caja de escribir,
    que es el punto del pedido (los botones no son lo que uno viene a mirar);
  · "Quedan fijos" compensa el zoom: ampliando la página al doble, el botón mide la mitad
    en píxeles CSS, o sea el MISMO tamaño real en pantalla. Con "Crecen", no.
  · la elección viaja al servidor (`botones`, `botonesZoom`) y la referencia del zoom NO
    (`aspectoZoomRef` es del navegador: el teléfono tiene otra densidad);
  · y el texto del chat NO se mueve con esta perilla — para eso está la del tamaño del texto.

⚠ El zoom se simula pisando `devicePixelRatio`, que es exactamente lo que el zoom del
navegador cambia, y disparando `resize`, que es como se entera `aspecto.js`. Playwright no
sabe cambiarle el zoom a una página ya abierta.

⚠ No toca el aspecto de verdad de Martín: `/aspecto` está interceptado en las dos puntas.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_tamano_botones
             (no hace falta el panel prendido; con `--viejo` sirve los archivos de git y
              los chequeos clave TIENEN que fallar)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
VIEJO = "--viejo" in sys.argv
SID = "botones-5555-5555-555555555555"
SALIDA = RAIZ / "pruebas" / "tamano_botones.png"
# Los chequeos que el código de ANTES no puede pasar: son los que prueban que esto existe.
CLAVE = ("mínimos achica el botón", "mínimos achica la letra del botón",
         "el lugar que se libera se lo queda la caja de escribir",
         "con el zoom al doble el botón mide la mitad",
         "o sea: el mismo tamaño real en pantalla",
         "las filas de la columna también achican",
         "la conversación en vivo va a la derecha, no abajo de los controles",
         "la caja de escribirle a Laura ya no es una rendija")


def del_disco(rel):
    if VIEJO:
        return subprocess.run(["git", "show", "HEAD:" + rel], cwd=RAIZ,
                              capture_output=True, encoding="utf-8").stdout
    return (RAIZ / rel).read_text(encoding="utf-8")


SESIONES_HTML = del_disco("app/estaticos/sesiones.html")
ASPECTO_JS = del_disco("app/estaticos/aspecto.js")

CHARLA = [{"de": "vos", "texto": "hola", "imgs": []},
          {"de": "claude", "texto": "listo", "imgs": []}]

fallas = []
guardados = []          # lo que la pantalla le mandó a /aspecto


def revisar(que, ok, detalle=""):
    print(("  ok   " if ok else "  MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def servidor_falso(pag, aspecto):
    # ⚠⚠ Las dos puntas de /aspecto: sin esto la prueba le cambiaría el aspecto REAL a
    # Martín (ya pasó con la pizarra el 2026-08-29, y se descubrió por una queja suya).
    pag.route("**/estaticos/aspecto.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript; charset=utf-8", body=ASPECTO_JS))
    pag.route("**/aspecto", lambda r: (
        guardados.append(json.loads(r.request.post_data or "{}"))
        if r.request.method == "POST" else None,
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "aspecto": json.loads(r.request.post_data)}
                                  if r.request.method == "POST" else aspecto))))
    pag.route("**/fondo/windows/version", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"v": ""}'))
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "laura": "", "proyectos": [
            {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False, "sesiones": [
                {"id": SID, "nombre": "La de los botones", "ts": 2, "ultimo": "vos",
                 "viva": False, "interactiva": False, "detalle": ""}]}]})))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": False,
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "opus", "defecto": "opus",
                         "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}],
                         "esfuerzo": "normal",
                         "esfuerzos": [{"id": "normal", "nombre": "normal"}],
                         "velocidad": "normal",
                         "velocidades": [{"id": "normal", "nombre": "normal"}],
                         "modo": "", "modos": [{"id": "", "nombre": "Normal"}],
                         "contexto": {"tokens": 183000, "nivel": "medio"}})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"cerebro": "claude", "prompts": [], "carpeta": ""})))
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=SESIONES_HTML))


MEDIR = """() => {
  const cs = el => el ? getComputedStyle(el) : null;
  const alto = s => s ? Math.round(parseFloat(s.height)) : 0;
  const env = document.querySelector('#enviar');
  const txt = document.querySelector('#texto');
  const tab = document.querySelector('.tab');
  const carp = document.querySelector('.carpeta');
  const burb = document.querySelector('#hilo .msg') || document.querySelector('.msg');
  const r = (el) => el ? Math.round(el.getBoundingClientRect().height) : 0;
  return {
    ui: parseFloat(getComputedStyle(document.documentElement)
                   .getPropertyValue('--ui') || '1'),
    enviar: r(env),
    enviarLetra: env ? parseFloat(cs(env).fontSize) : 0,
    caja: txt ? Math.round(txt.getBoundingClientRect().width) : 0,
    tab: r(tab),
    carpeta: r(carp),
    burbuja: burb ? parseFloat(cs(burb).fontSize) : 0,
    dpr: window.devicePixelRatio,
  };
}"""

# Pisar el zoom es pisar el devicePixelRatio y avisar con `resize`: es literalmente lo que
# hace el navegador al apretar Ctrl + rueda.
ZOOM = """(v) => {
  Object.defineProperty(window, 'devicePixelRatio', {value: v, configurable: true});
  window.dispatchEvent(new Event('resize'));
}"""

ABRIR_CHARLA = """(sid) => {
  const p = datos.proyectos[0];
  abiertas = [{sid, cwd: p.cwd, nombre: 'La de los botones', cerebro: ''}];
  pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
}"""


def preparar(nav, aspecto):
    ctx = nav.new_context(viewport={"width": 1590, "height": 1000})
    pag = ctx.new_page()
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag, aspecto)
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(900)
    pag.evaluate(ABRIR_CHARLA, SID)
    pag.wait_for_timeout(900)
    return pag


ASP = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "letra": "normal"}

with sync_playwright() as nav_p:
    nav = nav_p.chromium.launch(channel="chrome", headless=True)

    # ─── 1. Los cuatro pasos ────────────────────────────────────────────────────
    print("\n=== los cuatro tamaños ===")
    medidas = {}
    for paso in ("normal", "chicos", "minimos", "grandes"):
        pag = preparar(nav, dict(ASP, botones=paso, botonesZoom="crece"))
        m = pag.evaluate(MEDIR)
        medidas[paso] = m
        print(f"  {paso:8s} --ui {m['ui']:.2f} · Enviar {m['enviar']:3d} px "
              f"(letra {m['enviarLetra']:.1f}) · caja {m['caja']:4d} px · "
              f"pestaña {m['tab']:3d} · carpeta {m['carpeta']:3d}")
        if paso == "minimos":
            pag.screenshot(path=str(SALIDA), clip={"x": 0, "y": 0,
                                                   "width": 1590, "height": 130})
        pag.context.close()

    n, mini = medidas["normal"], medidas["minimos"]
    # ⭐ Lo primero de todo: sin elegir nada, nada se movió. Los 38 px están escritos en el
    # CSS desde 2026-08-25 y una perilla nueva no puede cambiárselos a nadie.
    revisar("en Normales el botón sigue midiendo 38 px", n["enviar"] == 38,
            f"{n['enviar']} px")
    revisar("en Normales el multiplicador es exactamente 1", abs(n["ui"] - 1) < .001,
            f"--ui {n['ui']}")
    revisar("mínimos achica el botón", mini["enviar"] < n["enviar"] - 6,
            f"{n['enviar']} -> {mini['enviar']} px")
    revisar("mínimos achica la letra del botón",
            mini["enviarLetra"] < n["enviarLetra"] - 2,
            f"{n['enviarLetra']} -> {mini['enviarLetra']} px")
    # ⭐ El pedido no es "que los botones sean chiquitos": es que dejen de comerse la
    # pantalla. Lo que se libera tiene que ir a parar a donde uno escribe.
    revisar("el lugar que se libera se lo queda la caja de escribir",
            mini["caja"] > n["caja"] + 20, f"{n['caja']} -> {mini['caja']} px")
    revisar("y los cuatro pasos van en orden",
            medidas["minimos"]["enviar"] < medidas["chicos"]["enviar"]
            < medidas["normal"]["enviar"] < medidas["grandes"]["enviar"],
            " < ".join(str(medidas[k]["enviar"])
                       for k in ("minimos", "chicos", "normal", "grandes")))
    revisar("las pestañas de arriba achican con los botones",
            mini["tab"] < n["tab"], f"{n['tab']} -> {mini['tab']} px")
    revisar("las filas de la columna también achican",
            mini["carpeta"] < n["carpeta"], f"{n['carpeta']} -> {mini['carpeta']} px")
    # ⚠ Y lo que NO tiene que moverse: el texto de la conversación tiene su propia perilla.
    revisar("el texto del chat no lo toca esta perilla",
            abs(mini["burbuja"] - n["burbuja"]) < .2,
            f"{n['burbuja']} -> {mini['burbuja']} px")

    # ─── 2. Que no crezcan con el zoom ──────────────────────────────────────────
    print("\n=== el zoom del navegador ===")
    pag = preparar(nav, dict(ASP, botones="normal", botonesZoom="crece"))
    antes = pag.evaluate(MEDIR)
    pag.evaluate(ZOOM, antes["dpr"] * 2)
    pag.wait_for_timeout(200)
    creciendo = pag.evaluate(MEDIR)
    print(f"  crecen:  {antes['enviar']} px -> {creciendo['enviar']} px "
          f"(dpr {antes['dpr']} -> {creciendo['dpr']})")
    revisar("con 'crecen', el zoom no cambia los píxeles CSS (o sea: se agranda en pantalla)",
            creciendo["enviar"] == antes["enviar"],
            f"{antes['enviar']} -> {creciendo['enviar']} px")
    pag.context.close()

    pag = preparar(nav, dict(ASP, botones="normal", botonesZoom="fijo"))
    fijo_antes = pag.evaluate(MEDIR)
    revisar("recién prendido, 'quedan fijos' no mueve nada", fijo_antes["enviar"] == 38,
            f"{fijo_antes['enviar']} px")
    pag.evaluate(ZOOM, fijo_antes["dpr"] * 2)
    pag.wait_for_timeout(200)
    fijo_doble = pag.evaluate(MEDIR)
    print(f"  fijos:   {fijo_antes['enviar']} px -> {fijo_doble['enviar']} px "
          f"(dpr {fijo_antes['dpr']} -> {fijo_doble['dpr']})")
    revisar("con el zoom al doble el botón mide la mitad",
            abs(fijo_doble["enviar"] - fijo_antes["enviar"] / 2) <= 2,
            f"{fijo_antes['enviar']} -> {fijo_doble['enviar']} px")
    revisar("o sea: el mismo tamaño real en pantalla",
            abs(fijo_doble["enviar"] * fijo_doble["dpr"]
                - fijo_antes["enviar"] * fijo_antes["dpr"]) <= 4,
            f"{fijo_antes['enviar'] * fijo_antes['dpr']:.0f} -> "
            f"{fijo_doble['enviar'] * fijo_doble['dpr']:.0f} px reales")
    # ⚠ El tope: un zoom bestial no puede dejar botones de 13 px, imposibles de apretar.
    pag.evaluate(ZOOM, fijo_antes["dpr"] * 6)
    pag.wait_for_timeout(200)
    tope = pag.evaluate(MEDIR)
    print(f"  al 600 %: --ui {tope['ui']:.2f} · Enviar {tope['enviar']} px")
    revisar("y hay un piso: no se achican hasta desaparecer", tope["ui"] >= .40,
            f"--ui {tope['ui']}")
    # ⚠ El piso tiene que estar LEJOS del zoom que se usa de verdad: si se tocara al 200 %,
    # "quedan fijos" dejaría de estar fijo justo donde uno lo prende. Es el bug que tuvo la
    # primera versión (piso .55) y por eso este chequeo mide el 200 %, no el 600 %.
    revisar("al 200 % el piso todavía no se toca", fijo_doble["ui"] > .41,
            f"--ui {fijo_doble['ui']}")
    # Y al volver el zoom a lo de antes, vuelve el tamaño de antes.
    pag.evaluate(ZOOM, fijo_antes["dpr"])
    pag.wait_for_timeout(200)
    revisar("sacando el zoom vuelven a su tamaño",
            pag.evaluate(MEDIR)["enviar"] == fijo_antes["enviar"])
    pag.context.close()

    # ─── 3. Que la elección viaje (y la referencia del zoom NO) ─────────────────
    print("\n=== lo que se guarda ===")
    pag = preparar(nav, dict(ASP, botones="normal", botonesZoom="crece"))
    pag.evaluate("() => document.querySelector('#aspectoBtn').click()")
    pag.wait_for_timeout(300)
    pag.evaluate("""() => {
      const d = document.querySelector('#aspectoPanel details[data-sec="botones"]');
      if (d) d.open = true;
    }""")
    pag.wait_for_timeout(200)
    hay = pag.evaluate("""() => !!document.querySelector(
        '#aspectoPanel .ops[data-campo="botones"] .op[data-v="minimos"]')""")
    revisar("el 🎨 tiene la sección de los botones", hay)
    # ⭐⭐ El panel del 🎨 TAMBIÉN sigue a --ui (segunda captura de Martín, el mismo día:
    # *"se ve re mal esto con el zoom"*, con el panel ocupando la pantalla de arriba abajo
    # al 175 %). Era justo el que uno abre para arreglar el problema, y era de los peores.
    panel_antes = pag.evaluate("() => document.querySelector('#aspectoPanel').offsetWidth")
    if hay:
        guardados.clear()
        pag.evaluate("""() => document.querySelector(
            '#aspectoPanel .ops[data-campo="botones"] .op[data-v="minimos"]').click()""")
        pag.wait_for_timeout(400)
        chico = pag.evaluate(MEDIR)
        revisar("eligiéndolo en el 🎨 los botones achican al toque",
                chico["enviar"] < 34, f"{chico['enviar']} px")
        panel_chico = pag.evaluate(
            "() => document.querySelector('#aspectoPanel').offsetWidth")
        revisar("y el propio panel del 🎨 achica con ellos",
                panel_chico < panel_antes - 40, f"{panel_antes} -> {panel_chico} px")
        revisar("el 🎨 no se sale de la pantalla por la derecha",
                pag.evaluate("""() => {
                  const b = document.querySelector('#aspectoPanel')
                              .getBoundingClientRect();
                  return b.right <= window.innerWidth && b.left >= 0;
                }"""))
        revisar("y la elección sale para el servidor",
                any(g.get("botones") == "minimos" for g in guardados),
                str([g.get("botones") for g in guardados]))
        # ⭐⭐ La referencia del zoom es de ESTA pantalla y no puede viajar: el teléfono
        # tiene otra densidad y otra ampliación de sistema.
        pag.evaluate("""() => document.querySelector(
            '#aspectoPanel .ops[data-campo="botonesZoom"] .op[data-v="fijo"]').click()""")
        pag.wait_for_timeout(400)
        revisar("prender 'fijos' también viaja",
                any(g.get("botonesZoom") == "fijo" for g in guardados))
        revisar("pero la referencia del zoom NO viaja al servidor",
                not any("botonesRef" in g or "aspectoZoomRef" in g for g in guardados))
        revisar("la referencia quedó guardada en este navegador",
                pag.evaluate("() => !!localStorage.getItem('aspectoZoomRef')"))
    pag.context.close()

    # ─── 4. El panel sin reiniciar: tiene que DECIRLO ───────────────────────────
    # ⚠⚠ La trampa del 2026-08-25, otra vez: el panel de Martín todavía no conoce estos dos
    # campos, así que los tira al reescribir el archivo y la elección se pierde en el
    # próximo F5. "No falló" no es lo mismo que "salió bien": el cartel tiene que aparecer.
    print("\n=== el panel todavía sin reiniciar ===")
    pag = preparar(nav, dict(ASP, botones="normal", botonesZoom="crece"))
    pag.route("**/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(dict(ASP, tintaLetras="", burbujaVos="", ok="")     # sin `botones`
                        if r.request.method != "POST"
                        else {"ok": True, "aspecto": dict(ASP, tintaLetras="",
                                                          burbujaVos="", ok="")})))
    pag.evaluate("() => document.querySelector('#aspectoBtn').click()")
    pag.wait_for_timeout(300)
    pag.evaluate("""() => {
      const d = document.querySelector('#aspectoPanel details[data-sec="botones"]');
      if (d) d.open = true;
      const op = document.querySelector(
        '#aspectoPanel .ops[data-campo="botones"] .op[data-v="minimos"]');
      if (op) op.click();
    }""")
    pag.wait_for_timeout(600)
    visible = pag.evaluate("""() => {
      const c = document.querySelector('#aspectoViejo');
      return !!c && c.style.display !== 'none';
    }""")
    revisar("con el panel sin reiniciar, el 🎨 avisa que no viaja", visible)
    pag.context.close()

    # ─── 5. El 🎨 abierto, a la forma de ventana de la captura de Martín ─────────
    # Su segunda captura del 2026-09-12: Chrome al 175 % en una ventana angosta y alta
    # (1438x2559 físicos = ~822x1462 px CSS). El panel llegaba de arriba abajo y se comía
    # un tercio del ancho. Acá quedan las dos fotos, una al lado de la otra.
    print("\n=== el 🎨 abierto en su ventana (822x1462 px CSS) ===")
    for paso, nombre in (("normal", "paleta_normal.png"), ("minimos", "paleta_minimos.png")):
        ctx = nav.new_context(viewport={"width": 822, "height": 1462})
        pag = ctx.new_page()
        pag.on("dialog", lambda d: d.dismiss())
        servidor_falso(pag, dict(ASP, botones=paso, botonesZoom="crece"))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => typeof mandar === 'function'", timeout=90000)
        pag.wait_for_timeout(900)
        pag.evaluate("() => document.querySelector('#aspectoBtn').click()")
        pag.wait_for_timeout(300)
        pag.evaluate("""() => {
          const d = document.querySelector('#aspectoPanel details[data-sec="letra"]');
          if (d) d.open = true;
        }""")
        pag.wait_for_timeout(300)
        m = pag.evaluate("""() => {
          const b = document.querySelector('#aspectoPanel').getBoundingClientRect();
          return {ancho: Math.round(b.width), alto: Math.round(b.height),
                  pantalla: window.innerWidth};
        }""")
        print(f"  {paso:8s} el 🎨 mide {m['ancho']}x{m['alto']} px "
              f"({100 * m['ancho'] // m['pantalla']} % del ancho de la ventana)")
        pag.screenshot(path=str(RAIZ / "pruebas" / nombre))
        ctx.close()

    # ─── 6. El panel principal, en la misma ventana ─────────────────────────────
    # Tercera captura de Martín el mismo día: *"este panel se ve muy mal"*, con
    # localhost:8750 en su monitor vertical. La columna de la conversación en vivo quedaba
    # de una palabra por renglón y los once botones de abajo ocupaban cuatro filas.
    # ⚠ Se monta `PAGINA` con las piezas de `foto_pantallas.py` para no repetir el andamiaje.
    print("\n=== el panel principal (1425x2380 px CSS, su monitor vertical) ===")
    # ⚠ `PAGINA` se saca del panel.py que corresponda: con `--viejo` tiene que ser el de
    # git, o los dos chequeos del layout medirían el código nuevo y darían verde siempre.
    from pruebas.foto_pantallas import constante, montar
    html_panel = constante("PAGINA", del_disco("panel.py"))
    for paso, nombre in (("normal", "panel_normal.png"), ("minimos", "panel_minimos.png")):
        ctx = nav.new_context(viewport={"width": 1425, "height": 2380})
        pag = ctx.new_page()
        pag.on("dialog", lambda d: d.dismiss())
        montar(pag, html_panel, dict(ASP, img="", velo="media", botones=paso,
                                     botonesZoom="crece"))
        pag.wait_for_timeout(700)
        m = pag.evaluate("""() => {
          const b = document.querySelector('.barra-chat button');
          const t = document.querySelector('.escribir textarea');
          const filas = new Set([...document.querySelectorAll('.barra-chat button')]
                                .map(n => Math.round(n.getBoundingClientRect().top)));
          // Dónde cae cada chat: el bug era que la conversación en vivo se iba a una
          // segunda fila DEBAJO de la columna de controles, con la celda de al lado vacía.
          const caja1 = document.querySelector('.cols > .col:first-child')
                          .getBoundingClientRect();
          const vivo = document.querySelector('[data-bloque="vivo"]').getBoundingClientRect();
          return {boton: b ? Math.round(b.getBoundingClientRect().height) : 0,
                  caja: t ? Math.round(t.getBoundingClientRect().width) : 0,
                  filas: filas.size,
                  vivo_a_la_derecha: vivo.left >= caja1.right - 1,
                  // Cuánto del alto de la pantalla usa la columna de controles.
                  alto_controles: Math.round(caja1.height)};
        }""")
        print(f"  {paso:8s} botón de la barra {m['boton']} px · caja de Laura {m['caja']} px"
              f" · los botones ocupan {m['filas']} fila(s)")
        pag.screenshot(path=str(RAIZ / "pruebas" / nombre), full_page=False)
        ctx.close()
        medidas["panel_" + paso] = m
    revisar("en el panel principal los botones también achican",
            medidas["panel_minimos"]["boton"] < medidas["panel_normal"]["boton"] - 3,
            f"{medidas['panel_normal']['boton']} -> {medidas['panel_minimos']['boton']} px")
    revisar("y los once botones de la barra ocupan menos filas",
            medidas["panel_minimos"]["filas"] <= medidas["panel_normal"]["filas"],
            f"{medidas['panel_normal']['filas']} -> {medidas['panel_minimos']['filas']}")
    # ⭐⭐ El arreglo del layout, que es lo que de verdad le movía la pantalla: en dos
    # columnas los dos chats se apilan a la DERECHA. Antes la conversación en vivo caía en
    # una segunda fila abajo a la izquierda, en 360 px, con medio panel vacío al lado.
    pn = medidas["panel_normal"]
    revisar("la conversación en vivo va a la derecha, no abajo de los controles",
            pn["vivo_a_la_derecha"])
    revisar("la columna de controles usa el alto entero de la pantalla",
            pn["alto_controles"] > 2000, f"{pn['alto_controles']} px de 2380")
    # Y la caja de escribirle a Laura deja de ser una rendija: era 235 px en 1425 de ancho.
    revisar("la caja de escribirle a Laura ya no es una rendija",
            pn["caja"] > 600, f"{pn['caja']} px")
    pag.context.close()
    nav.close()

print(f"\ncaptura (con los botones en mínimos): {SALIDA}")
if VIEJO:
    cayeron = [c for c in CLAVE if c in fallas]
    print(f"\n--viejo: cayeron {len(cayeron)} de {len(CLAVE)} chequeos clave")
    raise SystemExit(0 if len(cayeron) == len(CLAVE) else 1)
print("\n" + ("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas)))
if fallas:
    raise SystemExit(1)
