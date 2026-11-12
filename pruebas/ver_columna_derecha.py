"""La columna de la derecha de /sesiones se ESTIRA y tiene PIEZAS con pestañas (2026-11-10).

Martín: *"hay cosas de Claude Code que podríamos agregar a este panel, como la terminal o el
navegador dentro del mismo panel"*. Las dos necesitan lugar y la columna medía 300 px fijos.
Esta es la pieza 0 de ese plan: el lugar. Lo que cuida la prueba:
  · que se pueda ensanchar arrastrando su borde, que el ancho se recuerde, y que NUNCA deje
    a la charla sin lugar (ni se achique hasta desaparecer);
  · que con una sola pieza (Entorno) la columna se vea como siempre, sin pestañas;
  · que con dos, la pestaña cambie la pieza y cada una se entere de cuándo se la mira y
    cuándo no — es lo que le va a permitir a una terminal o a una filmación no gastar nada
    mientras nadie la ve;
  · que cerrada siga midiendo cero SIN salir de la grilla (regla de antes: con
    `display:none` la conversación se corre de pista).

⚠ Fija su propio aspecto y sus propios datos: no lee el estilo que haya puesto de verdad ni
toca carpetas o charlas de nadie. Al panel solo le llegan pedidos de lectura.

Correr con:  python -m pruebas.ver_columna_derecha   (con el panel prendido)
"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS

BASE = "http://127.0.0.1:8750"
fallas = []
AHORA = time.time()
SID = "colder-0000-0000-000000000000"
SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa"], "ocultas": []},
            "proyectos": [{"proyecto": "alfa", "cwd": "D:\\pruebas\\alfa", "vivo": False, "sesiones": [
                {"id": SID, "nombre": "charla de prueba", "ts": AHORA - 600, "ultimo": "claude",
                 "viva": False, "ocupada": False, "interactiva": False, "detalle": "x"}]}]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None, "mensajes": [
    {"de": "vos", "texto": "hola", "imgs": []},
    {"de": "claude", "texto": "Una respuesta cualquiera para que haya charla.", "imgs": []}]}
ENTORNO = {"ok": True, "maquina": "compu-de-prueba", "carpeta": "D:\\pruebas\\alfa", "nombre": "alfa",
           "remoto_posible": False, "remoto": {}, "contexto": None, "conectores": [],
           "conectores_de": "ahora", "cerebro": "claude", "navegador": None}
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}


def campos_del_estilo(k):
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def revisar(nombre, obtenido, esperado=True):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def montar(nav, aspecto, ancho=1500):
    ctx = nav.new_context(viewport={"width": ancho, "height": 900}, reduced_motion="reduce")
    errores, pedidos = [], {"entorno": 0}

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            cuerpo = CHAT
        elif camino == "/movil/entorno":
            pedidos["entorno"] += 1
            cuerpo = ENTORNO
        elif camino in ("/estaticos/terminal.js", "/estaticos/escritorio.js"):
            # Esta prueba mide el MECANISMO de las piezas, con una de mentira. La terminal de
            # verdad (que el panel sirve desde que se reinició) tiene su propia prueba,
            # `ver_terminal`: acá se la deja afuera para que la columna arranque con una sola.
            # Lo mismo el Escritorio remoto (`ver_escritorio`), desde el 2026-11-12.
            return r.fulfill(status=200, content_type="application/javascript", body="")
        elif camino == "/aspecto" and r.request.method == "GET":
            cuerpo = aspecto
        elif r.request.method != "GET" or camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
            cuerpo = {"ok": True}
        else:
            return r.continue_()
        return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    # ⚠ Solo en la PRIMERA carga: después se recarga la página a propósito para ver qué recuerda.
    pag.add_init_script("""if (!sessionStorage.getItem('yaLimpie')) { localStorage.clear();
        localStorage.setItem('sesDerecha', '1'); sessionStorage.setItem('yaLimpie', '1'); }""")
    abrir(pag)
    return ctx, pag, errores, pedidos


def abrir(pag, recargar=False):
    if recargar:
        pag.reload(wait_until="domcontentloaded")
    else:
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=20000)
    pag.wait_for_timeout(500)
    pag.evaluate("""sid => { pendientes = {}; falladas = {}; visto = {};
      abiertas = [{sid, cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'charla de prueba', cerebro: ''}];
      irTab(sid); firma = ''; cargar(); }""", SID)
    pag.wait_for_selector("#hilo .msg.claude", timeout=20000)
    pag.wait_for_timeout(700)


MEDIR = """() => { const q = s => document.querySelector(s), r = s => q(s).getBoundingClientRect();
  const cs = getComputedStyle(q('#derecha'));
  return {col: Math.round(r('#derecha').width + (parseFloat(cs.marginLeft) || 0)),
          charla: Math.round(r('#cuerpo').width),
          guardado: localStorage.getItem('sesDerAncho'),
          pestanas: [getComputedStyle(q('#derTabs')).display, [...document.querySelectorAll('#derTabs button')].map(b => b.textContent + (b.classList.contains('sel') ? '*' : ''))],
          entorno: [q('#derEntorno').hidden, q('#derEntorno').textContent.includes('compu-de-prueba')],
          visible: cs.visibility, display: cs.display}; }"""


def arrastrar(pag, dx):
    """Agarra el tirador por el medio y lo corre `dx` px (negativo = ensanchar la columna)."""
    c = pag.evaluate("""() => { const r = document.querySelector('#tiradorDer').getBoundingClientRect();
                         return [r.left + r.width / 2, r.top + r.height / 2]; }""")
    pag.mouse.move(c[0], c[1])
    pag.mouse.down()
    pag.mouse.move(c[0] + dx / 2, c[1], steps=4)
    pag.mouse.move(c[0] + dx, c[1], steps=4)
    pag.mouse.up()
    pag.wait_for_timeout(150)


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)

    # --- 1. De fábrica: como siempre, y ahora se estira -------------------------------------
    ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO))
    # Entorno pide sus datos en su propia vuelta (cada segundo y medio): se la espera.
    try:
        pag.wait_for_function("() => document.querySelector('#derEntorno').textContent.includes('compu-de-prueba')",
                              timeout=6000)
    except Exception:
        pass
    m = pag.evaluate(MEDIR)
    revisar("de fábrica mide los 300 px de siempre", m["col"], 300)
    revisar("⭐ con una sola pieza no hay pestañas: la columna se ve como antes",
            m["pestanas"], ["none", ["Entorno*"]])
    revisar("y Entorno muestra lo suyo", m["entorno"], [False, True])
    antes = m
    arrastrar(pag, -220)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ arrastrando el borde se ensancha ({antes['col']} → {m['col']} px)",
            abs(m["col"] - 520) <= 3)
    revisar(f"y ese lugar sale de la charla ({antes['charla']} → {m['charla']} px)",
            abs((antes["charla"] - m["charla"]) - 220) <= 3)
    revisar("el ancho queda guardado", abs(int(m["guardado"] or 0) - 520) <= 3)
    abrir(pag, recargar=True)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ y al recargar la página lo recuerda ({m['col']} px)", abs(m["col"] - 520) <= 3)
    arrastrar(pag, -2000)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ por más que tires, a la charla le quedan por lo menos 420 px ({m['charla']})",
            m["charla"] >= 415)
    arrastrar(pag, 3000)
    m = pag.evaluate(MEDIR)
    revisar(f"y no se achica hasta desaparecer: piso de 260 px ({m['col']})", m["col"], 260)
    pag.dblclick("#tiradorDer", position={"x": 3, "y": 300})
    pag.wait_for_timeout(150)
    m = pag.evaluate(MEDIR)
    revisar("doble clic en el borde: vuelve al ancho de fábrica y olvida el guardado",
            [m["col"], m["guardado"]], [300, None])

    # --- 2. Con una segunda pieza: pestañas, y cada una sabe cuándo se la mira ---------------
    pag.evaluate("""() => { window.avisos = [];
      Paneles.registrar({id: 'prueba', titulo: 'Prueba', anchoMin: 520,
        alMostrar: c => { avisos.push('mostrar'); c.textContent = 'hola, soy otra pieza'; },
        alOcultar: () => avisos.push('ocultar')}); }""")
    m = pag.evaluate(MEDIR)
    revisar("⭐ con dos piezas aparecen las pestañas, y sigue a la vista la que estaba",
            [m["pestanas"], m["entorno"][0], pag.evaluate("() => avisos")],
            [["flex", ["Entorno*", "Prueba"]], False, []])
    pedidos["entorno"] = 0
    pag.click("#derTabs button[data-pieza='prueba']")
    pag.wait_for_timeout(3600)                # más que una vuelta del refresco de Entorno
    m = pag.evaluate(MEDIR)
    revisar("⭐ la pestaña cambia la pieza y le avisa a la que llega",
            [m["pestanas"][1], m["entorno"][0], pag.evaluate("() => avisos"),
             pag.evaluate("() => document.querySelector('.derPane[data-pieza=\"prueba\"]').textContent")],
            [["Entorno", "Prueba*"], True, ["mostrar"], "hola, soy otra pieza"])
    revisar("⭐ mientras se mira otra pieza, Entorno no le pide nada al panel", pedidos["entorno"], 0)
    revisar(f"la pieza que pide más ancho lo recibe si nunca arrastraste ({m['col']} px)", m["col"], 520)
    pag.click("#btnDerecha")
    pag.wait_for_timeout(200)
    m = pag.evaluate(MEDIR)
    revisar("⭐ al cerrar la columna, la pieza se entera de que ya no la ven",
            pag.evaluate("() => avisos"), ["mostrar", "ocultar"])
    revisar("⭐ cerrada mide cero y NO sale de la grilla (sin `display:none`)",
            [m["col"], m["visible"], m["display"] != "none"], [0, "hidden", True])
    pag.click("#btnDerecha")
    pag.wait_for_timeout(200)
    revisar("y al abrirla de nuevo vuelve la misma pieza, avisada otra vez",
            [pag.evaluate("() => avisos"), pag.evaluate("() => Paneles.actual()")],
            [["mostrar", "ocultar", "mostrar"], "prueba"])
    arrastrar(pag, 120)                        # la achico a mano: 520 → 400
    pag.click("#derTabs button[data-pieza='entorno']")
    pag.wait_for_timeout(900)
    m = pag.evaluate(MEDIR)
    revisar("volviendo a Entorno, se ve y vuelve a pedir sus datos",
            [m["entorno"], pedidos["entorno"] >= 1], [[False, True], True])
    pag.click("#derTabs button[data-pieza='prueba']")
    pag.wait_for_timeout(200)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ desde que arrastraste manda TU ancho: la pieza ya no lo cambia sola ({m['col']} px)",
            abs(m["col"] - 400) <= 3)
    revisar("sin errores de JS", errores, [])
    ctx.close()

    # --- 3. Con Vidrio: el mismo tirador, y lo de Entorno se lee -----------------------------
    ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO, estilo="vidrio", **campos_del_estilo("vidrio")))
    antes = pag.evaluate(MEDIR)
    arrastrar(pag, -200)
    m = pag.evaluate(MEDIR)
    revisar(f"Vidrio: el tirador ensancha igual ({antes['col']} → {m['col']} px)",
            abs((m["col"] - antes["col"]) - 200) <= 3)
    lee = pag.evaluate("""() => { const e = document.querySelector('#derEntorno .tarjDer'), r = e.getBoundingClientRect();
      const a = document.elementFromPoint(r.left + 30, r.top + 14);
      return !!a && e.contains(a); }""")
    revisar("Vidrio: la tarjeta de Entorno está a la vista (nada la tapa)", lee)
    revisar("sin errores de JS con Vidrio", errores, [])
    ctx.close()

    # --- 4. Dos columnas a la izquierda: la charla igual conserva su piso (2026-11-12) -------
    # El bug real: con la columna de charlas a la vista, la primera columna de la grilla es
    # MÁS ANCHA que el `aside`, y el tope se calculaba con "la ventana menos el aside". Al
    # agrandar el Escritorio la charla quedó de 130 px. Acá se arma ese caso a mano (primera
    # columna de 640 px con un `aside` de 230) para no depender del nombre de ningún estilo.
    ctx, pag, errores, pedidos = montar(nav, dict(ASPECTO, estilo="vidrio", **campos_del_estilo("vidrio")), ancho=1700)
    pag.add_style_tag(content="aside{max-width:230px !important;justify-self:start}")
    pag.evaluate("""() => { for (const e of [document.documentElement, document.body, document.querySelector('main')])
                              if (e) e.style.setProperty('--lat', '640px'); }""")
    pag.wait_for_timeout(250)
    caso = pag.evaluate("""() => { const a = document.querySelector('aside').getBoundingClientRect().width;
      const c = document.querySelector('#cuerpo').getBoundingClientRect();
      return {aside: Math.round(a), izquierda: Math.round(c.left), vieja: Math.round(innerWidth - a - 420)}; }""")
    revisar(f"el caso está bien armado: la charla empieza bastante más allá del aside ({caso})",
            caso["izquierda"] - caso["aside"] >= 250)
    arrastrar(pag, -3000)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ con dos columnas a la izquierda, tirando a fondo la charla conserva sus 420 px ({m['charla']})",
            m["charla"] >= 415)
    revisar(f"…y la cuenta vieja la habría aplastado (daba {caso['vieja']} px de columna; hoy mide {m['col']})",
            caso["vieja"] - m["col"] >= 250)
    pag.evaluate("() => Paneles.agrandar()")
    pag.wait_for_timeout(200)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ y con ⤢ Agrandar tampoco la aplasta ({m['charla']} px de charla)", m["charla"] >= 415)
    # La charla se queda sin lugar SIN que cambie la ventana (se abre otra columna a la izquierda).
    pag.evaluate("""() => { for (const e of [document.documentElement, document.body, document.querySelector('main')])
                              if (e) e.style.setProperty('--lat', '820px'); }""")
    pag.wait_for_timeout(500)
    m = pag.evaluate(MEDIR)
    revisar(f"⭐ si se abre otra columna a la izquierda, la de la derecha cede sola ({m['charla']} px de charla)",
            m["charla"] >= 415)
    revisar("sin errores de JS con dos columnas", errores, [])
    ctx.close()
    nav.close()

print()
if fallas:
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
    sys.exit(1)
print("TODO BIEN")
