"""El estilo "Carta celeste": el rediseño de /sesiones (2026-11-10).

Martín, después de dos pasadas de retoques: *"se sigue viendo como una aplicación ordinaria;
quiero que sea premium"*. Eligió este rumbo entre cuatro bocetos. La idea es que cada agente
sea un punto y que su tamaño y su anillo digan el estado, así que lo que esta prueba cuida es
justamente eso: que el punto diga la verdad, que las marcas sigan en columna, que la charla
sea una columna de lectura sin cajas, y que SIN el estilo puesto no exista nada de todo esto.

⚠ Datos inventados, interceptados en el contexto: no toca carpetas ni charlas de nadie, y al
panel solo le llegan pedidos de lectura.

Correr con:  python -m pruebas.ver_carta_celeste   (con el panel prendido)
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
SID = "carta-0000-0000-000000000000"


def ses(sid, nombre, hace_min, viva=False, ocupada=False, ultimo="vos"):
    return {"id": sid, "nombre": nombre, "ts": AHORA - hace_min * 60, "ultimo": ultimo,
            "viva": viva, "ocupada": ocupada, "interactiva": False, "detalle": "x"}


# Cuatro carpetas, una por caso: una charla trabajando, una que contestó y nadie abrió,
# una dormida de ayer, y una carpeta vacía.
PROYECTOS = [("alfa", [ses(SID, "charla que trabaja", 0, viva=True, ocupada=True)]),
             ("beta", [ses("beta-1", "charla que espera", 5, ultimo="claude")]),
             ("gama", [ses("gama-1", "charla dormida", 1500)]),
             ("delta", [])]
SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": [n for n, _ in PROYECTOS], "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": n == "alfa",
                           "sesiones": s} for n, s in PROYECTOS]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None, "mensajes": [
    {"de": "vos", "texto": "hola", "imgs": []},
    {"de": "claude", "texto": "Acá va la respuesta, **sin caja**.", "imgs": []}]}
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}


def campos_del_estilo(k):
    """Los campos del estilo, leídos de aspecto.js: así la prueba mide lo que la pantalla usa."""
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def revisar(nombre, obtenido, esperado=True):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def montar(nav, aspecto, movimiento=False):
    # Las medidas de siempre se toman con el movimiento apagado (nada a mitad de camino);
    # la parte 4 lo prende a propósito, porque el movimiento es lo que mide.
    ctx = nav.new_context(viewport={"width": 1400, "height": 900},
                          reduced_motion="no-preference" if movimiento else "reduce")
    errores = []

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            cuerpo = CHAT
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
    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=15000)
    pag.wait_for_timeout(700)
    # Se abre la charla que trabaja, como si la hubieras clickeado.
    pag.evaluate("""sid => { pendientes = {}; falladas = {}; visto = {};
      abiertas = [{sid, cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'charla que trabaja', cerebro: ''}];
      irTab(sid); firma = ''; cargar(); }""", SID)
    pag.wait_for_selector("#hilo .msg.claude", timeout=15000)
    pag.wait_for_timeout(900)
    pag.evaluate("() => document.fonts.ready")
    return ctx, pag, errores


MEDIR = """() => {
  const q = s => document.querySelector(s), est = e => e ? getComputedStyle(e) : null;
  const fila = n => q("#carpetas .carpeta[data-proy='" + n + "']");
  const puntos = n => [...fila(n).querySelectorAll('.estrellas .ast')].map(e => e.className.replace('ast', '').trim());
  const borde = s => [...new Set(['alfa','beta','gama','delta'].map(n => {
    const e = fila(n).querySelector(s); return e ? Math.round(e.getBoundingClientRect().right) : null; }))];
  const ia = q('#hilo .msg.claude'), vos = q('#hilo .msg.vos'), caja = q('#caja'), cu = q('#cuerpo');
  const rc = caja.getBoundingClientRect(), ru = cu.getBoundingClientRect();
  const texto = q('#texto').getBoundingClientRect(), env = q('#enviar').getBoundingClientRect();
  return {
    clases: document.documentElement.className.split(/\\s+/).filter(Boolean).sort(),
    letras: [...new Set([...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/"/g, '')))].sort(),
    puntos: {alfa: puntos('alfa'), beta: puntos('beta'), gama: puntos('gama'), delta: puntos('delta')},
    seVenPuntos: est(fila('alfa').querySelector('.estrellas')).display !== 'none',
    seVeNumero: est(fila('alfa').querySelector('.num')).display !== 'none',
    columnas: [borde('.naveg, .h-naveg').length, borde('.estrellas').length, borde('.plegar, .h-plegar').length],
    cielo: est(q('#cielo')).display !== 'none' ? q('#cielo .res').textContent : null,
    cieloPuntos: q('#cielo').querySelectorAll('.ast').length,
    cabecera: est(q('.carta-cab')).display !== 'none' ? q('.carta-cab h1').textContent : null,
    iaFondo: est(ia).backgroundColor, iaBorde: est(ia).borderLeftWidth,
    vosFondo: est(vos).backgroundColor,
    textoArriba: texto.bottom <= env.top + 1,
    centrada: Math.abs((rc.left + rc.right) / 2 - (ru.left + ru.right) / 2) < 8,
  };
}"""

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)

    # --- 1. Con el estilo puesto ---------------------------------------------------
    ctx, pag, errores = montar(nav, dict(ASPECTO, estilo="celeste", **campos_del_estilo("celeste")))
    m = pag.evaluate(MEDIR)
    revisar("el estilo existe en aspecto.js", bool(campos_del_estilo("celeste")))
    # Solo las clases que deciden el diseño: el <html> lleva además marcas de servicio
    # (`con-luces`, que avisa que el script de las luces cargó) que acá no dicen nada.
    revisar("⭐ la pantalla lleva la clase `carta` y NO las formas de Grok",
            [c for c in m["clases"] if c in ("carta", "vidrio", "estilo-grok", "grok-puro")], ["carta"])
    revisar("las tres tipografías viajan adentro y cargan sin internet",
            m["letras"], ["Archivo", "Chivo Mono", "Piazzolla"])
    revisar("⭐ el punto dice la verdad: trabajando, te espera, dormida y carpeta vacía",
            m["puntos"], {"alfa": ["trabajando"], "beta": ["espera"], "gama": [""], "delta": []})
    revisar("los puntos reemplazan al número de la carpeta",
            [m["seVenPuntos"], m["seVeNumero"]], [True, False])
    revisar("⭐ las marcas de la derecha siguen en columna (globito, puntos, flechita)",
            m["columnas"], [1, 1, 1])
    revisar("la franja «esta noche» resume lo mismo que los puntos",
            m["cielo"], "1 trabajando · 1 te espera")
    revisar("y dibuja una estrella por charla", m["cieloPuntos"], 3)
    revisar("la charla tiene su encabezado con el nombre", m["cabecera"], "charla que trabaja")
    revisar("⭐ lo que dice la sesión va SIN caja: ni fondo ni borde",
            [m["iaFondo"], m["iaBorde"]], ["rgba(0, 0, 0, 0)", "0px"])
    revisar("tu burbuja sí lleva fondo", m["vosFondo"] != "rgba(0, 0, 0, 0)")
    revisar("en la pieza de escribir el texto va arriba y los botones abajo", m["textoArriba"])
    revisar("y la pieza queda centrada debajo de la charla", m["centrada"])
    # Tocar un punto de la franja abre esa charla, igual que su renglón.
    pag.click("#cielo .ast.espera")
    pag.wait_for_timeout(500)
    revisar("tocar un punto de la franja abre esa charla",
            pag.evaluate("() => activa"), "beta-1")
    revisar("sin errores de JS con el estilo puesto", errores, [])
    ctx.close()

    # --- 1 bis. Vidrio: el mismo casco con otra piel -------------------------------
    # ⭐ Lo que importa medir acá es que el texto SE VEA. La primera versión dejó la "hoja"
    # de vidrio dibujada por encima de la charla: todo lo de arriba daba bien (las clases,
    # los puntos, los colores) y en la pantalla no había una sola letra. Por eso se
    # pregunta qué hay EN el punto donde está el texto, no qué clase tiene.
    ctx, pag, errores = montar(nav, dict(ASPECTO, estilo="vidrio", **campos_del_estilo("vidrio")))
    v = pag.evaluate("""() => {
      const ia = document.querySelector('#hilo .msg.claude'), r = ia.getBoundingClientRect();
      const arriba = document.elementFromPoint(r.left + 20, r.top + r.height / 2);
      const riel = document.querySelector('aside'), caja = document.querySelector('#caja');
      return {clases: ['carta', 'vidrio', 'estilo-grok'].filter(c => document.documentElement.classList.contains(c)),
              seLee: !!arriba && (arriba === ia || ia.contains(arriba)),
              quien: arriba ? (arriba.id || arriba.className || arriba.tagName) : null,
              vidrio: [riel, caja].map(e => getComputedStyle(e).backdropFilter !== 'none'),
              franja: getComputedStyle(document.querySelector('#cielo')).display,
              foto: document.documentElement.classList.contains('con-foto')};
    }""")
    revisar("Vidrio: el casco de la carta más su piel, sin las formas de Grok", v["clases"], ["carta", "vidrio"])
    revisar("⭐ Vidrio: el texto de la charla se ve (la hoja va DETRÁS, no encima)", v["seLee"])
    if not v["seLee"]:
        print("     en ese punto hay:", v["quien"])
    revisar("Vidrio: el riel y la pieza de escribir son de vidrio", v["vidrio"], [True, True])
    revisar("Vidrio: sin la franja «esta noche», que es de la carta", v["franja"], "none")
    revisar("Vidrio: siempre hay una foto atrás, aunque no hayas elegido ninguna", v["foto"])
    revisar("sin errores de JS con Vidrio", errores, [])
    ctx.close()

    # --- 3. El diseño pone las formas; el 🎨 sigue mandando --------------------------
    # Martín, con Vidrio ya puesto: *"siento que se pierde mucha personalización con estos
    # cambios; me gustaría poder seguir configurando colores y esas cosas"*. La primera
    # versión escribía a mano la tinta, la letra, la burbuja y el botón Enviar, así que
    # mover esas perillas no hacía nada acá. Se elige a propósito todo FEO y distinto de lo
    # de fábrica: lo que se mide es que cada perilla llegue a la pantalla, no que quede lindo.
    A_GUSTO = {"color": "#ff5fa2", "burbujaVos": "#2e7d32", "burbujaIa": "#ff9800",
               "tipo": "georgia", "tipoTitulo": "verdana", "tintaLetras": "#ff0000",
               "barra": "#123456", "botones": "grandes"}
    LEER = """() => {
      const q = s => document.querySelector(s), e = s => getComputedStyle(q(s));
      const n = c => (c.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
      const tinta = n(e('#hilo .msg.claude').color);
      return {enviar: e('#enviar').backgroundColor, raya: e('#tabs .tab.sel').borderBottomColor,
              vos: e('#hilo .msg.vos').backgroundColor,
              ia: [e('#hilo .msg.claude').borderLeftColor, e('#hilo .msg.claude').borderLeftWidth],
              letra: e('#carpetas .carpeta[data-proy] .nom').fontFamily.split(',')[0].replace(/"/g, ''),
              titulo: [e('.carta-cab h1').fontFamily.split(',')[0].replace(/"/g, ''), e('.carta-cab h1').fontStyle],
              tinta,
              barra: (document.documentElement.classList.contains('vidrio')
                      ? getComputedStyle(document.body, '::after') : e('#barraArriba')).backgroundColor,
              alto: Math.round(q('#carpetas .carpeta[data-proy]').getBoundingClientRect().height)};
    }"""
    for estilo in ("celeste", "vidrio"):
        ctx, pag, errores = montar(nav, dict(ASPECTO, estilo=estilo, **campos_del_estilo(estilo)))
        base = pag.evaluate(LEER)
        ctx.close()
        ctx, pag, errores = montar(nav, dict(dict(ASPECTO, estilo=estilo, **campos_del_estilo(estilo)), **A_GUSTO))
        g = pag.evaluate(LEER)
        revisar(f"⭐ {estilo}: el color de acento pinta el botón Enviar", g["enviar"], "rgb(255, 95, 162)")
        if estilo == "celeste":      # en Vidrio la pestaña elegida es una pastilla, sin raya
            revisar("celeste: y la raya de la pestaña elegida", g["raya"], "rgb(255, 95, 162)")
        revisar(f"⭐ {estilo}: «Tu burbuja» pinta tu burbuja", g["vos"], "rgb(46, 125, 50)")
        revisar(f"{estilo}: «Burbuja de la sesión» va como regla fina al costado",
                g["ia"], ["rgb(255, 152, 0)", "2px"])
        revisar(f"⭐ {estilo}: la tipografía elegida llega a la lista de carpetas", g["letra"], "Georgia")
        revisar(f"{estilo}: la letra de los títulos, también, y derecha", g["titulo"], ["Verdana", "normal"])
        # ⚠ El tinte cambia el MATIZ y conserva la luminosidad (por diseño: así no puede
        # volver ilegible un texto), o sea que un rojo deja el texto rosado claro, no rojo.
        # Por eso se compara contra el mismo texto sin ese tinte, y no contra un rojo.
        revisar(f"⭐ {estilo}: el tinte de las letras tiñe el texto de la charla "
                f"({base['tinta']} → {g['tinta']})",
                g["tinta"][0] - g["tinta"][2] > base["tinta"][0] - base["tinta"][2] + 10)
        revisar(f"{estilo}: la barra de arriba toma su color", g["barra"], "rgb(18, 52, 86)")
        revisar(f"⭐ {estilo}: el tamaño de los botones agranda las filas ({base['alto']} → {g['alto']} px)",
                g["alto"] > base["alto"])
        revisar(f"sin errores de JS a gusto ({estilo})", errores, [])
        ctx.close()

    # --- 4. Vidrio: el movimiento ----------------------------------------------------
    # Martín, con Vidrio andando: *"quiero más animaciones y que se vea más premium"*. Lo que
    # se cuida acá son las tres formas en que el movimiento se rompe sin que nadie avise:
    # una luz que no está donde dice, una entrada que arranca de nuevo en cada repintado
    # (la charla se rearma cada 3 s: sería un parpadeo permanente), y una perilla del 🎨
    # que al apagar el movimiento deje algo invisible.
    vid = dict(ASPECTO, estilo="vidrio", **campos_del_estilo("vidrio"))
    CORREN = """() => [...new Set(document.getAnimations().filter(a => a.playState === 'running')
      .map(a => a.animationName || ('t:' + a.transitionProperty)))].sort()"""
    # ⚠ Mide con su propia cuenta (las dos cajas en la pantalla), no llamando a `moverLuz`.
    LUZ = """([luz, sel]) => { const a = document.getElementById(luz), b = document.querySelector(sel);
      if (!a || !b) return null;
      const r = a.getBoundingClientRect(), s = b.getBoundingClientRect();
      return [getComputedStyle(a).display, Math.max(Math.abs(r.x - s.x), Math.abs(r.y - s.y),
              Math.abs(r.width - s.width), Math.abs(r.height - s.height)) <= 1.5]; }"""
    LUCES = [["luzTab", "#tabs .tab.sel"], ["luzRiel", "#carpetas .carpeta.sel"]]
    VISIBLE = """() => ['aside', '#caja', '#hilo', '#barraArriba'].map(s => getComputedStyle(document.querySelector(s)).opacity)
      .concat([getComputedStyle(document.body, '::before').opacity, getComputedStyle(document.body, '::after').opacity])"""

    ctx, pag, errores = montar(nav, vid, movimiento=True)
    pag.wait_for_timeout(1400)                     # que termine de llegar todo
    corren = pag.evaluate(CORREN)
    revisar("⭐ movimiento: la charla que trabaja prende el brillo de «pensando» y la luz de la pieza",
            [n for n in corren if n in ("vdBrillo", "vdOrbita")], ["vdBrillo", "vdOrbita"])
    revisar("y terminada la llegada no queda ninguna entrada corriendo",
            [n for n in corren if n.startswith("vd") and n not in ("vdBrillo", "vdOrbita", "vdFundido")], [])
    revisar("⭐ cada luz está sobre lo elegido (la pestaña y la carpeta)",
            [pag.evaluate(LUZ, x) for x in LUCES], [["block", True], ["block", True]])
    revisar("las dos barras son UN vidrio: ellas van transparentes y el vidrio es de la página",
            pag.evaluate("""() => [getComputedStyle(document.body, '::after').backdropFilter !== 'none']
              .concat(['#barraArriba', '#barra'].map(s => getComputedStyle(document.querySelector(s)).backdropFilter))"""),
            [True, "none", "none"])
    viaje = pag.evaluate("""() => { abrirSesion('D:\\\\pruebas\\\\beta', 'beta-1', 'charla que espera', false, '');
      const t = id => document.getElementById(id).getAnimations().map(a => a.transitionProperty).filter(Boolean);
      return [t('luzTab').includes('left'), t('luzRiel').includes('top')]; }""")
    revisar("⭐ al cambiar de charla las dos luces VIAJAN (no nacen ya en su lugar)", viaje, [True, True])
    pag.wait_for_timeout(900)
    revisar("y llegan: cada luz queda sobre lo nuevo elegido",
            [pag.evaluate(LUZ, x) for x in LUCES], [["block", True], ["block", True]])
    revisar("la charla quieta apaga la luz de la pieza de escribir",
            "vdOrbita" in pag.evaluate(CORREN), False)
    # ⭐⭐ La entrada sobrevive al repintado. `progreso` es cuánto lleva recorrido la animación
    # del hilo: después de un repintado a los 200 ms tiene que SEGUIR (más de un cuarto), no
    # volver a cero. El control es la última medida: arrancándola de nuevo a propósito da ~0,
    # o sea que la cuenta sabe distinguir las dos cosas.
    ent = pag.evaluate("""async sid => {
      const dormir = ms => new Promise(r => setTimeout(r, ms));
      const progreso = () => { const h = document.querySelector('#hilo');
        const a = h && h.getAnimations().find(x => x.animationName === 'vdEntra');
        return a ? (a.effect.getComputedTiming().progress || 0) : null; };
      irTab(sid);
      for (let i = 0; i < 80 && !document.querySelector('#hilo.entrando'); i++) await dormir(10);
      await dormir(200);
      firma = ''; await pintarSesion();
      const sigue = progreso();
      vdEntrar('hilo', true, [null, document.querySelector('#hilo')], 45);
      const deNuevo = progreso();
      await dormir(1100);
      firma = ''; await pintarSesion();
      return {sigue, deNuevo, tarde: document.querySelector('#hilo').classList.contains('entrando')};
    }""", SID)
    revisar("⭐⭐ un repintado a mitad de la entrada la CONTINÚA (lleva " + str(ent["sigue"]) + " de 1)",
            ent["sigue"] is not None and ent["sigue"] > 0.25)
    revisar("control: arrancada de nuevo a propósito vuelve al principio (" + str(ent["deNuevo"]) + ")",
            ent["deNuevo"] is not None and ent["deNuevo"] < 0.1)
    revisar("y pasado el segundo, un repintado ya no le pone ninguna entrada", ent["tarde"], False)
    revisar("sin errores de JS con el movimiento puesto", errores, [])
    ctx.close()

    # «Sin latidos» del 🎨 apaga las animaciones: todo tiene que quedar a la vista y en su lugar.
    ctx, pag, errores = montar(nav, dict(vid, movi="poco"), movimiento=True)
    pag.wait_for_timeout(600)
    revisar("⭐ «Sin latidos»: no corre ninguna animación del diseño",
            [n for n in pag.evaluate(CORREN) if n.startswith("vd")], [])
    revisar("⭐ y nada queda invisible (riel, pieza, charla, barras y los dos vidrios)",
            pag.evaluate(VISIBLE), ["1"] * 6)
    revisar("«pensando» se sigue leyendo (sin el brillo, vuelve su color)",
            pag.evaluate("() => getComputedStyle(document.querySelector('.msg.pensa')).color") != "rgba(0, 0, 0, 0)")
    revisar("y las luces siguen marcando lo elegido",
            [pag.evaluate(LUZ, x) for x in LUCES], [["block", True], ["block", True]])
    revisar("sin errores de JS en «Sin latidos»", errores, [])
    ctx.close()

    # Con "reducir movimiento" de Windows: nada se mueve y lo elegido se marca igual.
    ctx, pag, errores = montar(nav, vid)
    quieto = pag.evaluate("""() => { abrirSesion('D:\\\\pruebas\\\\beta', 'beta-1', 'charla que espera', false, '');
      return ['luzTab', 'luzRiel'].map(id => document.getElementById(id).getAnimations().length); }""")
    revisar("con «reducir movimiento» las luces no viajan: aparecen en su lugar", quieto, [0, 0])
    pag.wait_for_timeout(500)
    revisar("y no corre ninguna animación del diseño",
            [n for n in pag.evaluate(CORREN) if n.startswith("vd")], [])
    revisar("ni queda nada invisible", pag.evaluate(VISIBLE), ["1"] * 6)
    ctx.close()

    # La sombra del vidrio obedece a la perilla «Sombra», y «Sin sombra» no se lleva el filo de luz.
    ctx, pag, errores = montar(nav, dict(vid, sombra="nada"))
    sin = pag.evaluate("() => getComputedStyle(document.querySelector('aside')).boxShadow")
    ctx.close()
    ctx, pag, errores = montar(nav, dict(vid, sombra="marcada"))
    con = pag.evaluate("() => getComputedStyle(document.querySelector('aside')).boxShadow")
    ctx.close()
    revisar("⭐ «Sin sombra» saca la sombra del vidrio pero deja su filo de luz", "inset" in sin and sin != con)
    revisar("y sin sombra de verdad: lo que cae afuera es transparente (" + sin[-60:] + ")",
            "rgba(0, 0, 0, 0) 0px 0px 0px 0px" in sin)

    # --- 2. Sin el estilo: nada de esto existe -------------------------------------
    # Es también el control de la prueba: si acá diera lo mismo que arriba, lo de arriba no
    # estaría midiendo nada.
    ctx, pag, errores = montar(nav, dict(ASPECTO))
    m = pag.evaluate(MEDIR)
    revisar("⭐ sin el estilo no hay clase `carta`", "carta" in m["clases"], False)
    revisar("ni puntos, ni franja, ni encabezado; el número vuelve",
            [m["seVenPuntos"], m["cielo"], m["cabecera"], m["seVeNumero"]],
            [False, None, None, True])
    revisar("y la burbuja de la sesión vuelve a tener su fondo y su borde",
            [m["iaFondo"] != "rgba(0, 0, 0, 0)", m["iaBorde"]], [True, "3px"])
    revisar("sin errores de JS sin el estilo", errores, [])
    ctx.close()
    nav.close()

print()
if fallas:
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
    sys.exit(1)
print("TODO BIEN")
