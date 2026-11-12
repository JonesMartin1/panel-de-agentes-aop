"""El estilo "Vidrio con bandeja" (2026-11-11).

Pedido de Martín, mirando el boceto "Bandeja": *"crealo como estilo nuevo con la temática que
ya tengo"*. Es la piel de Vidrio entera (clases `carta` y `vidrio`) más la clase `vbandeja`:
las carpetas se achican a una tira de emojis y, con una charla abierta, aparece al lado la
lista de charlas de esa carpeta (`#colCharlas`) con cuatro filtros.

    python -m pruebas.ver_vbandeja            (con el panel prendido en 8750)
    python -m pruebas.ver_vbandeja --mutar    (rompe cada pieza y exige que se note)

Lo que cuida:
  · ⭐ con el estilo Vidrio de siempre NO cambia nada: ni la clase, ni la lista, ni el ancho
    del riel (la columna de charlas se había descartado el 2026-08-16 para esa pantalla);
  · con Vidrio con bandeja: riel angosto con solo el emoji, la lista a la vista, sin
    archivadas ni tapadas, la más nueva arriba y la abierta marcada;
  · los filtros cuentan bien; tocar otra charla de la lista abre ESA charla;
  · sin charla abierta (la bandeja en el medio) la lista no se duplica al costado.

⚠ Datos inventados y ningún pedido que no sea GET llega al panel: todo lo que escribe se
contesta acá. La página y `aspecto.js` se sirven del disco, así no depende de reiniciar.
"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
SALIDA = RAIZ / "pruebas"
AHORA = time.time()
CWD = "D:\\pruebas\\alfa"


def ses(id_, nombre, hace, **extra):
    s = {"id": id_, "nombre": nombre, "ts": AHORA - hace, "ultimo": "vos", "viva": False,
         "ocupada": False, "interactiva": False, "detalle": "guardada, hace un rato"}
    s.update(extra)
    return s


SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa", "beta"], "ocultas": []},
            "proyectos": [
                {"proyecto": "alfa", "cwd": CWD, "vivo": True, "sesiones": [
                    ses("alfa-1", "arreglar el login", 4000),
                    ses("alfa-2", "pantalla de pagos", 30, viva=True, ocupada=True,
                        detalle="activa, recién"),
                    ses("alfa-3", "revisar textos", 900, ultimo="claude", sub="Web"),
                    ses("alfa-4", "una archivada", 10, archivada=True),
                    ses("alfa-5", "una tapada", 20, tapada=True),
                    ses("alfa-6", "migrar la base", 90000)]},
                {"proyecto": "beta", "cwd": "D:\\pruebas\\beta", "vivo": False, "sesiones": [
                    ses("beta-1", "otra carpeta", 50)]}]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None,
        "mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                     {"de": "claude", "texto": "una respuesta", "imgs": []}]}


def campos_del_estilo(k):
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def aspecto(estilo):
    return dict({"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
                 "letra": "normal", "velo": "media", "rastro": "tema", "estilo": estilo},
                **campos_del_estilo(estilo))


MEDIR = """() => {
  const cl = document.documentElement.classList, col = document.getElementById('colCharlas');
  const vis = e => !!e && getComputedStyle(e).display !== 'none';
  const nom = document.querySelector('.carpeta[data-proy="alfa"] .nom');
  return {carta: cl.contains('carta'), vidrio: cl.contains('vidrio'), vbandeja: cl.contains('vbandeja'),
    conCol: document.body.classList.contains('con-col'), colVisible: vis(col),
    colAncho: col ? Math.round(col.getBoundingClientRect().width) : 0,
    riel: Math.round(document.querySelector('aside').getBoundingClientRect().width),
    nomVisible: vis(nom),
    items: [...document.querySelectorAll('#colCharlas .cc-it')].map(x => x.dataset.sid),
    sel: [...document.querySelectorAll('#colCharlas .cc-it.sel')].map(x => x.dataset.sid),
    subs: [...document.querySelectorAll('#colCharlas .cc-sub')].map(x => x.dataset.sub),
    abrirCol: vis(document.getElementById('abrirCol')),
    // Las dos pestañas del borde: ¿se pisan entre sí? ¿alguna cae arriba de una carpeta?
    pisan: (() => {
      const rs = ['anchoRiel', 'abrirCol'].map(i => document.getElementById(i)).filter(vis)
                   .map(e => e.getBoundingClientRect());
      const toca = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
      const malas = [];
      if (rs.length === 2 && toca(rs[0], rs[1])) malas.push('entre ellas');
      document.querySelectorAll('#carpetas .carpeta, #sumar').forEach(c => {
        const r = c.getBoundingClientRect();
        // un borde de 3 px de cortesía: la pestaña va montada sobre el filo del riel
        const adentro = {left: r.left, right: r.right - 3, top: r.top, bottom: r.bottom};
        if (r.width && rs.some(p => toca(p, adentro))) malas.push(c.dataset.proy || c.id);
      });
      return malas;
    })(),
    activa: typeof activa === 'undefined' ? null : activa};
}"""


MENU_ARRIBA = """() => { const c = document.getElementById('menuPantallas'), b = document.getElementById('barraArriba');
  if (!c || !b) return {cabe: false, estado: 'sin menú'};
  const rc = c.getBoundingClientRect(), rb = b.getBoundingClientRect();
  return {cabe: rc.right <= rb.right + 1 && c.scrollWidth <= c.clientWidth + 1,
          estado: c.classList.contains('mini') ? 'mini' : c.classList.contains('compacto') ? 'compacto' : 'completo'}; }"""


def montar(nav, estilo, cambios=None, abrir=True):
    ctx = nav.new_context(viewport={"width": 1500, "height": 850}, reduced_motion="reduce")
    errores = []

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        for archivo in ("sesiones.html", "aspecto.js", "menu.js"):
            if camino.endswith("/" + archivo) or (archivo == "sesiones.html" and camino == "/sesiones"):
                cuerpo = (ESTATICOS / archivo).read_text(encoding="utf-8")
                for viejo, nuevo in (cambios or {}).get(archivo, []):
                    assert viejo in cuerpo, "la mutación no encontró: " + viejo
                    cuerpo = cuerpo.replace(viejo, nuevo)
                tipo = "text/html" if archivo.endswith(".html") else "application/javascript"
                return r.fulfill(status=200, content_type=tipo + "; charset=utf-8", body=cuerpo)
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            cuerpo = CHAT
        elif camino == "/aspecto" and r.request.method == "GET":
            cuerpo = aspecto(estilo)
        elif camino == "/movil/elegir-carpeta":
            cuerpo = {"ok": True, "ruta": "D:\\pruebas\\gamma"}
        elif camino == "/movil/carpeta":
            pedido = json.loads(r.request.post_data or "{}")
            ruta = pedido.get("ruta", "")
            if "inexistente" in ruta and not pedido.get("crear"):
                cuerpo = {"ok": False, "puede_crear": True, "error": "esa carpeta no existe"}
            else:
                cuerpo = {"ok": True, "nombre": ruta.split("\\")[-1], "cwd": ruta}
        elif r.request.method != "GET":
            cuerpo = {"ok": True}
        elif camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
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
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=20000)
    if abrir:
        pag.evaluate("() => { abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa',"
                     " nombre: 'arreglar el login', cerebro: ''}]; irTab('alfa-1'); }")
    pag.wait_for_timeout(900)
    return ctx, pag, errores


def correr(nav, cambios=None, fotos=False):
    fallas = []

    def chequear(ok, que):
        if not ok:
            fallas.append(que)

    def tocar(pag, sel):
        try:
            pag.click(sel, timeout=3000)
        except Exception:
            fallas.append("no se pudo tocar " + sel)

    # 1. Vidrio de siempre: nada nuevo.
    ctx, pag, err = montar(nav, "vidrio", cambios)
    m = pag.evaluate(MEDIR)
    chequear(m["vidrio"] and not m["vbandeja"], "Vidrio: lleva la clase vbandeja")
    chequear(not m["colVisible"] and not m["conCol"], "Vidrio: se ve la lista de charlas al costado")
    chequear(m["riel"] > 150 and m["nomVisible"], "Vidrio: el riel se achicó o perdió los nombres")
    chequear(not pag.evaluate("() => getComputedStyle(document.getElementById('anchoRiel')).display !== 'none'"),
             "Vidrio: se ve el botón » del riel, que es solo de la bandeja")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_vidrio_de_siempre.png"))
    chequear(not err, "Vidrio: errores en la página: " + "; ".join(err))
    ctx.close()

    # 2. Vidrio con bandeja, con una charla abierta.
    ctx, pag, err = montar(nav, "vbandeja", cambios)
    m = pag.evaluate(MEDIR)
    chequear(m["carta"] and m["vidrio"] and m["vbandeja"], "Bandeja: faltan las clases carta/vidrio/vbandeja")
    chequear(m["colVisible"] and 320 <= m["colAncho"] <= 360, "Bandeja: la lista no está a la vista (%s px)" % m["colAncho"])
    chequear(m["riel"] <= 70 and not m["nomVisible"], "Bandeja: el riel no quedó en tira de íconos (%s px)" % m["riel"])
    # Las subcarpetas primero (como ClickUp), después las sueltas de la más nueva a la más vieja.
    chequear(m["subs"] == ["Web"], "Bandeja: falta la subcarpeta Web como grupo: %s" % m["subs"])
    chequear(m["items"] == ["alfa-3", "alfa-2", "alfa-1", "alfa-6"],
             "Bandeja: la lista no es la esperada (sin archivadas ni tapadas, subcarpetas arriba): %s" % m["items"])
    chequear(m["sel"] == ["alfa-1"], "Bandeja: no está marcada la charla abierta: %s" % m["sel"])
    menu = pag.evaluate(MENU_ARRIBA)
    chequear(menu["cabe"] and menu["estado"] == "completo",
             "Con lugar de sobra el menú de arriba no está entero o está cortado (%s)" % menu)
    chequear(m["abrirCol"], "Bandeja: no se ve la pestaña del borde de la lista")
    chequear(not m["pisan"], "Bandeja: las pestañas del borde pisan algo: %s" % m["pisan"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_charla.png"))
    # Plegar la subcarpeta esconde sus charlas; desplegarla las devuelve.
    tocar(pag, "#colCharlas .cc-sub[data-sub='Web']")
    chequear(pag.evaluate(MEDIR)["items"] == ["alfa-2", "alfa-1", "alfa-6"], "Plegar Web no escondió sus charlas")
    tocar(pag, "#colCharlas .cc-sub[data-sub='Web']")
    chequear(pag.evaluate(MEDIR)["items"][:1] == ["alfa-3"], "Desplegar Web no devolvió sus charlas")
    # La pestaña del borde de la lista la contrae (queda la tira de emojis) y la vuelve a abrir.
    tocar(pag, "#abrirCol")
    m = pag.evaluate(MEDIR)
    chequear(not m["colVisible"] and m["riel"] <= 70 and m["abrirCol"],
             "La pestaña no contrajo la lista (lista=%s, riel=%s, pestaña=%s)" % (m["colVisible"], m["riel"], m["abrirCol"]))
    chequear(not m["pisan"], "Contraída: las pestañas del borde pisan algo: %s" % m["pisan"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_contraida.png"))
    tocar(pag, "#abrirCol")
    m = pag.evaluate(MEDIR)
    chequear(m["colVisible"] and m["abrirCol"], "La pestaña no volvió a abrir la lista")
    # La pestaña del borde del riel: muestra el nombre entero de las carpetas, y vuelve a la tira.
    tocar(pag, "#anchoRiel")
    m = pag.evaluate(MEDIR)
    chequear(m["riel"] >= 200 and m["nomVisible"] and m["colVisible"],
             "La pestaña no ensanchó el riel con los nombres (riel=%s, nombre=%s)" % (m["riel"], m["nomVisible"]))
    chequear(not m["pisan"], "Riel ancho: las pestañas del borde pisan algo: %s" % m["pisan"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_riel_ancho.png"))
    tocar(pag, "#anchoRiel")
    m = pag.evaluate(MEDIR)
    chequear(m["riel"] <= 70 and not m["nomVisible"], "La pestaña no volvió a la tira de emojis (%s px)" % m["riel"])
    # Contraída Y con riel ancho: las dos pestañas comparten el hueco, una arriba y otra al medio.
    tocar(pag, "#abrirCol")
    tocar(pag, "#anchoRiel")
    m = pag.evaluate(MEDIR)
    chequear(not m["pisan"], "Contraída con riel ancho: las pestañas pisan algo: %s" % m["pisan"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_contraida_ancha.png"))
    tocar(pag, "#anchoRiel")
    tocar(pag, "#abrirCol")
    # Los bordes se estiran: la lista se ensancha arrastrando su borde, y la pestaña la sigue.
    def caja(sel):
        return pag.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect();"
                            " return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, l: r.left, r: r.right}; }", sel)

    def arrastrar(sel, dx, dy):
        c = caja(sel)
        # Un borde se agarra bien abajo, lejos de las pestañas (que van encima de él).
        y = c["y"] + 250 if sel.startswith("#borde") else c["y"]
        c = dict(c, y=y)
        pag.mouse.move(c["x"], c["y"])
        pag.mouse.down()
        for i in range(1, 9):
            pag.mouse.move(c["x"] + dx * i / 8, c["y"] + dy * i / 8)
        pag.mouse.up()
        pag.wait_for_timeout(250)

    antes = pag.evaluate(MEDIR)["colAncho"]
    arrastrar("#bordeCol", 120, 0)
    m = pag.evaluate(MEDIR)
    chequear(m["colAncho"] >= antes + 100, "Estirar el borde no ensanchó la lista (%s → %s)" % (antes, m["colAncho"]))
    lista, pest = caja("#colCharlas"), caja("#abrirCol")
    chequear(abs(pest["x"] - (lista["r"] + 7)) <= 1.5,
             "La pestaña no siguió al borde estirado (borde %s, pestaña %s)" % (lista["r"], pest["x"]))
    # Tirando del borde de la tira, el riel se abre con nombres.
    arrastrar("#bordeRiel", 170, 0)
    m = pag.evaluate(MEDIR)
    chequear(m["riel"] >= 200 and m["nomVisible"], "Tirar del borde de la tira no abrió el riel (%s px)" % m["riel"])
    chequear(not m["pisan"], "Estirado: las pestañas pisan algo: %s" % m["pisan"])
    # Con las dos columnas anchas, el menú de pantallas de arriba no puede quedar cortado:
    # pasa a solo íconos ("Servidores" quedaba a la mitad, captura del 2026-11-12).
    pag.wait_for_timeout(200)
    menu = pag.evaluate(MENU_ARRIBA)
    chequear(menu["cabe"] and menu["estado"] == "compacto",
             "Columnas anchas: el menú de arriba quedó cortado o no se achicó (%s)" % menu)
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_estirada.png"))
        c = caja("#bordeCol")
        pag.mouse.move(c["x"], c["y"] + 150)
        pag.wait_for_timeout(300)
        pag.screenshot(path=str(SALIDA / "vbandeja_pestana_hover.png"),
                       clip={"x": c["x"] - 60, "y": caja("#abrirCol")["y"] - 60, "width": 120, "height": 120})
        pag.mouse.move(5, 5)
    arrastrar("#bordeRiel", -200, 0)
    chequear(pag.evaluate(MEDIR)["riel"] <= 70, "Achicar el borde del riel no volvió a la tira")
    # La pestaña se mueve arrastrándola, y moverla NO cuenta como clic.
    y0 = caja("#anchoRiel")["y"]
    arrastrar("#anchoRiel", 0, 260)
    m = pag.evaluate(MEDIR)
    chequear(abs(caja("#anchoRiel")["y"] - (y0 + 260)) <= 3, "La pestaña del riel no se movió al arrastrarla")
    chequear(m["riel"] <= 70, "Mover la pestaña la apretó (abrió el riel)")
    chequear(not m["pisan"], "Pestaña movida: pisa algo: %s" % m["pisan"])
    # Contraída, si las dos quedan a la misma altura en el mismo hueco, la de la lista se corre.
    tocar(pag, "#abrirCol")
    arrastrar("#abrirCol", 0, caja("#anchoRiel")["y"] - caja("#abrirCol")["y"])
    chequear(not pag.evaluate(MEDIR)["pisan"], "Contraída: las dos pestañas se encimaron")
    tocar(pag, "#abrirCol")
    # Achicar la lista por debajo del mínimo la contrae al soltar.
    arrastrar("#bordeCol", -330, 0)
    m = pag.evaluate(MEDIR)
    chequear(not m["colVisible"] and m["abrirCol"], "Achicar la lista de más no la contrajo")
    tocar(pag, "#abrirCol")
    # La barrita del nombre se esconde con su ︿ y vuelve con la rayita de arriba.
    VER_CAB = """() => { const v = s => { const e = document.querySelector(s);
        return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; };
      return {caja: v('#cuerpo > .cab-fija .cab-caja'), rayita: v('#cuerpo > .cab-fija .mostrarCab')}; }"""
    chequear(pag.evaluate(VER_CAB) == {"caja": True, "rayita": False}, "La barrita del nombre no está a la vista")
    tocar(pag, "#cuerpo > .cab-fija .ocultarCab")
    chequear(pag.evaluate(VER_CAB) == {"caja": False, "rayita": True}, "El ︿ no escondió la barrita del nombre")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_cab_oculta.png"))
    tocar(pag, "#cuerpo > .cab-fija .mostrarCab")
    chequear(pag.evaluate(VER_CAB) == {"caja": True, "rayita": False}, "La rayita no devolvió la barrita del nombre")
    # Los filtros entran enteros en el ancho que tenga la lista (no se cortan ni se esconden).
    ENTRAN = """() => { const f = document.querySelector('#colCharlas .cc-filtros');
      if (!f) return {ok: false, cortados: ['sin filtros']};
      const r = f.getBoundingClientRect();
      const cortados = [...f.children].filter(s => s.scrollWidth > s.clientWidth + 1 ||
        s.getBoundingClientRect().right > r.right + 1).map(s => s.textContent);
      return {ok: !cortados.length, cortados, corto: [...f.querySelectorAll('.corto')].some(x => getComputedStyle(x).display !== 'none')}; }"""
    m = pag.evaluate(ENTRAN)
    chequear(m["ok"], "Los filtros se cortan con la lista de ancho normal: %s" % m["cortados"])
    pag.evaluate("() => { colW = 250; aplicarAnchos(); }")
    pag.wait_for_timeout(150)
    m = pag.evaluate(ENTRAN)
    chequear(m["ok"] and m["corto"], "Con la lista angosta los filtros se cortan o no pasan a la palabra corta: %s" % m["cortados"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_filtros_angosta.png"), clip={"x": 0, "y": 0, "width": 420, "height": 140})
    pag.evaluate("() => { colW = 344; aplicarAnchos(); }")
    # La cabecera de la lista edita la carpeta: el ícono abre su menú y el nombre se escribe ahí.
    tocar(pag, "#colCharlas [data-cc-ico]")
    chequear(pag.is_visible("#menuTarjeta.abierto"), "El ícono de la cabecera de la lista no abrió el menú de la carpeta")
    pag.keyboard.press("Escape")
    tocar(pag, "#colCharlas [data-cc-nom]")
    try:
        pag.fill("#colCharlas .cc-cabEdit", "Alfa nueva", timeout=3000)
        pag.keyboard.press("Enter")
    except Exception:
        fallas.append("Tocar el nombre de la carpeta en la lista no lo volvió editable")
    chequear(pag.evaluate("() => (document.querySelector('#colCharlas [data-cc-nom]') || {}).textContent") == "Alfa nueva"
             and pag.evaluate("() => apodos.alfa") == "Alfa nueva",
             "El nombre nuevo de la carpeta no quedó en la cabecera de la lista")
    pag.evaluate("() => { delete apodos.alfa; colFirma = ''; pintarColCharlas(); }")
    # Editar desde la lista: menú (botón derecho y ⋯), color, nombre y arrastrar.
    envios = []
    pag.on("request", lambda r: envios.append((r.url, r.post_data or "")) if r.method == "POST" else None)
    fila6 = "#colCharlas .cc-it[data-sid='alfa-6']"
    try:
        pag.click(fila6, button="right", timeout=3000)
    except Exception:
        fallas.append("no se pudo tocar con el botón derecho " + fila6)
    chequear(pag.is_visible("#menuTarjeta.abierto"), "Botón derecho en una charla de la lista no abrió su menú")
    tocar(pag, "#menuTarjeta .tonos .tono[data-tono='verde'], #menuTarjeta .tonos .tono:not(.nada)")
    chequear(pag.evaluate("s => { const e = document.querySelector(s); return !!e && e.classList.contains('pintada'); }", fila6),
             "Elegir un color en el menú no pintó la charla en la lista")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_menu_charla.png"))
    pag.keyboard.press("Escape")
    try:
        pag.hover("#colCharlas .cc-it[data-sid='alfa-1']", timeout=3000)
    except Exception:
        pass
    tocar(pag, "#colCharlas .cc-it[data-sid='alfa-1'] .cc-mas")
    chequear(pag.is_visible("#menuTarjeta.abierto"), "El ⋯ de una charla de la lista no abrió su menú")
    pag.keyboard.press("Escape")
    try:
        pag.dblclick(fila6 + " b", timeout=3000)
        pag.fill("#colCharlas .cc-nomEdit", "base nueva", timeout=3000)
        pag.keyboard.press("Enter")
    except Exception:
        fallas.append("Doble clic en el nombre no lo volvió editable")
    pag.wait_for_timeout(400)
    chequear(any("/movil/nombre" in u and "base nueva" in d for u, d in envios),
             "Cambiar el nombre en la lista no lo guardó")
    try:
        pag.drag_and_drop(fila6, "#colCharlas .cc-sub[data-sub='Web']", timeout=3000)
    except Exception:
        fallas.append("no se pudo arrastrar " + fila6)
    pag.wait_for_timeout(800)
    chequear(any("/movil/subproyecto" in u and "alfa-6" in d and "Web" in d for u, d in envios),
             "Arrastrar una charla al subproyecto Web no la cambió de subproyecto")
    # Crear una subcarpeta desde la cabecera (📁＋): queda arriba y VACÍA, recibe charlas
    # arrastradas, y vacía se puede borrar. Esc no crea nada.
    pag.wait_for_timeout(600)
    tocar(pag, "#colCharlas [data-cc-nuevasub]")
    try:
        pag.keyboard.type("Nada")
        pag.keyboard.press("Escape")
    except Exception:
        pass
    pag.wait_for_timeout(200)
    chequear("Nada" not in pag.evaluate(MEDIR)["subs"], "Esc al crear una subcarpeta igual la creó")
    tocar(pag, "#colCharlas [data-cc-nuevasub]")
    try:
        pag.fill("#colCharlas .cc-subcrear input", "Docs", timeout=3000)
        pag.keyboard.press("Enter")
    except Exception:
        fallas.append("El 📁＋ no abrió el renglón para escribir el nombre de la subcarpeta")
    pag.wait_for_timeout(300)
    m = pag.evaluate(MEDIR)
    chequear(m["subs"][:1] == ["Docs"] and pag.is_visible("#colCharlas .cc-subvacia"),
             "La subcarpeta nueva no quedó arriba y vacía: %s" % m["subs"])
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_subcarpeta_nueva.png"), clip={"x": 80, "y": 0, "width": 380, "height": 460})
    # Vacía, se borra desde su menú.
    try:
        pag.click("#colCharlas .cc-sub[data-sub='Docs']", button="right", timeout=3000)
        pag.click("#menuTarjeta [data-hace='borrar']", timeout=3000)
    except Exception:
        fallas.append("Una subcarpeta vacía no ofrece 'Borrar' en su menú")
    pag.wait_for_timeout(300)
    chequear("Docs" not in pag.evaluate(MEDIR)["subs"], "Borrar la subcarpeta vacía no la sacó")
    # Otra vez, y ahora se le arrastra una charla.
    tocar(pag, "#colCharlas [data-cc-nuevasub]")
    try:
        pag.fill("#colCharlas .cc-subcrear input", "Docs", timeout=3000)
        pag.keyboard.press("Enter")
        pag.wait_for_timeout(300)
        pag.drag_and_drop("#colCharlas .cc-it[data-sid='alfa-1']", "#colCharlas .cc-sub[data-sub='Docs']", timeout=3000)
    except Exception:
        fallas.append("no se pudo arrastrar una charla a la subcarpeta nueva")
    pag.wait_for_timeout(600)
    chequear(any("/movil/subproyecto" in u and "alfa-1" in d and "Docs" in d for u, d in envios),
             "Arrastrar una charla a la subcarpeta nueva (vacía) no la metió adentro")
    pag.wait_for_timeout(3500)          # que el refresco de mentira deje todo como antes
    # Los filtros.
    tocar(pag, "#colCharlas [data-colf='trabajando']")
    chequear(pag.evaluate(MEDIR)["items"] == ["alfa-2"], "Filtro Trabajando no da solo la que trabaja")
    tocar(pag, "#colCharlas [data-colf='espera']")
    chequear(pag.evaluate(MEDIR)["items"] == ["alfa-3"], "Filtro Te esperan no da solo la que espera")
    tocar(pag, "#colCharlas [data-colf='quieta']")
    chequear(pag.evaluate(MEDIR)["items"] == ["alfa-1", "alfa-6"], "Filtro Quietas mal")
    tocar(pag, "#colCharlas [data-colf='todas']")
    # Tocar otra charla de la lista abre ESA.
    tocar(pag, "#colCharlas .cc-it[data-sid='alfa-6']")
    pag.wait_for_timeout(700)
    m = pag.evaluate(MEDIR)
    chequear(m["activa"] == "alfa-6" and m["sel"] == ["alfa-6"],
             "Tocar 'migrar la base' no la abrió (activa=%s, marcada=%s)" % (m["activa"], m["sel"]))
    chequear(not err, "Bandeja: errores en la página: " + "; ".join(err))
    ctx.close()

    # 3. Vidrio con bandeja, sin charla abierta: la bandeja va en el medio, sin duplicar.
    ctx, pag, err = montar(nav, "vbandeja", cambios, abrir=False)
    m = pag.evaluate(MEDIR)
    chequear(not m["colVisible"] and m["riel"] <= 70, "Sin charla abierta: la lista se duplica al costado")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_sin_charla.png"))
    # La bandeja de una carpeta: el "+" de empezar va UNO solo (el ✚ escondido no puede tomar
    # tamaño: se veía "+➕", captura del 2026-11-12), y se crea una subcarpeta desde ahí.
    pag.evaluate("() => irProyecto('alfa')")
    pag.wait_for_timeout(600)
    letra = pag.evaluate("() => { const e = document.querySelector('#cuerpo .correo .ini.mas:not(.carpetaMas)');"
                         " return e ? getComputedStyle(e).fontSize : null; }")
    chequear(letra == "0px", "El ícono de 'Empezar una conversación' muestra el ✚ escondido (letra %s): se ven dos +" % letra)
    tocar(pag, "#cuerpo [data-nueva-subcarpeta]")
    try:
        pag.fill("#cuerpo .nomSubB", "Docs", timeout=3000)
        pag.keyboard.press("Enter")
    except Exception:
        fallas.append("La fila 'Nueva subcarpeta' de la bandeja no deja escribir el nombre")
    pag.wait_for_timeout(400)
    chequear(pag.is_visible("#cuerpo .subgrupo[data-g='Docs']") and pag.is_visible("#cuerpo .subvaciaB"),
             "Crear una subcarpeta desde la bandeja no la mostró (vacía)")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_bandeja_subcarpeta.png"), clip={"x": 300, "y": 100, "width": 900, "height": 420})
    pag.evaluate("() => { delete subVacias.alfa; guardarSubAjustes(); }")
    # "Agregar una carpeta": se escribe la ruta, o se elige con el selector de Windows.
    pedidos = []
    pag.on("request", lambda r: pedidos.append(r.post_data or "") if r.url.endswith("/movil/carpeta") else None)
    tocar(pag, "#sumar")
    chequear(pag.is_visible("#menuTarjeta #sumarRuta") and pag.is_visible("#menuTarjeta #sumarElegir"),
             "Agregar una carpeta no muestra el campo y el botón Elegir")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vbandeja_agregar_carpeta.png"))
    try:
        pag.fill("#sumarRuta", "D:\\pruebas\\inexistente", timeout=3000)
        pag.keyboard.press("Enter")
        pag.wait_for_selector("#sumarCrear", state="visible", timeout=3000)
        pag.click("#sumarCrear", timeout=3000)
        pag.wait_for_timeout(400)
    except Exception:
        fallas.append("Una ruta que no existe no ofreció el botón Crearla")
    chequear(any("inexistente" in d and '"crear": true' in d.replace('"crear":true', '"crear": true') for d in pedidos),
             "Crearla no mandó a crear la carpeta escrita")
    tocar(pag, "#sumar")
    tocar(pag, "#sumarElegir")
    pag.wait_for_timeout(500)
    chequear(any("gamma" in d for d in pedidos), "Elegir de mis archivos no agregó la carpeta elegida")
    chequear(not err, "Sin charla: errores en la página: " + "; ".join(err))
    ctx.close()
    return fallas


MUTACIONES = {
    "aplicar() no pone la clase vbandeja": {
        "aspecto.js": [("cl.toggle('vbandeja', carta && bandeja);", "")]},
    "la lista muestra archivadas y tapadas": {
        "sesiones.html": [("p.sesiones.filter(s => !s.tapada && !esArchivada(s))", "p.sesiones.filter(s => true)")]},
    "la lista sale también con el Vidrio de siempre": {
        "sesiones.html": [("document.documentElement.classList.contains('vbandeja') && !!activa",
                           "document.documentElement.classList.contains('vidrio') && !!activa")]},
    "la lista no agrupa por subcarpeta": {
        "sesiones.html": [("const grupos = p ? agruparSub(filas, p.proyecto, vacias) : null;", "const grupos = null;")]},
    "las pestañas se pisan (sin correr la de la lista)": {
        "sesiones.html": [("Math.abs(ya - yb) < 46)", "false)")]},
    "el borde no estira nada": {
        "sesiones.html": [("colW = Math.max(COL_MIN, Math.min(topeCol(), w));", "")]},
    "la pestaña no sigue al borde": {
        "sesiones.html": [("body.con-col #abrirCol{margin-left:calc(var(--rr) + var(--cw,344px) + 12px)}",
                           "body.con-col #abrirCol{margin-left:calc(var(--rr) + 356px)}")]},
    "el ︿ no esconde la barrita del nombre": {
        "sesiones.html": [("document.body.classList.toggle('cab-oculta', cabOculta);\n}",
                           "\n}")]},
    "los filtros no pasan a la palabra corta": {
        "sesiones.html": [("#colCharlas .cc-filtros .largo{display:none}", "#colCharlas .cc-filtros .largo{}")]},
    "el nombre de la carpeta no se edita en la lista": {
        "sesiones.html": [("col.querySelector('[data-cc-nom]').onclick = e => editarNombreCarpeta(e.currentTarget, p.proyecto);", "")]},
    "Elegir no agrega lo que elegiste": {
        "sesiones.html": [("inp.value = r.ruta;\n    agregar(r.ruta);", "inp.value = r.ruta;")]},
    "el menú de arriba no mide su renglón": {
        "sesiones.html": [('<div id="barraArriba" data-menu-fila>', '<div id="barraArriba">')]},
    "el ⋯ de la barra vuelve a pisar el + de la bandeja": {
        "sesiones.html": [(" html.carta #cuerpo button.mas{flex:none;", " html.carta #cuerpo .mas{flex:none;")]},
    "la bandeja no crea subcarpetas": {
        "sesiones.html": [("if (el.dataset.nuevaSubcarpeta !== undefined) return crearSubEnBandeja(el, p);", "")]},
    "no se pueden tener subcarpetas vacías": {
        "sesiones.html": [("vacias.forEach(k => { if (k && !g.has(k)) g.set(k, []); });", "")]},
    "el botón derecho de la lista no abre menú": {
        "sesiones.html": [("el.oncontextmenu = e => abrirMenuCharla(e, sid, el);", "")]},
    "el color no se ve en la lista": {
        "sesiones.html": [("(tn ? ' pintada' : '')", "''")]},
    "arrastrar no cambia de subproyecto": {
        "sesiones.html": [("if (g !== ll.g) asignarSub(ll.sid, g);", "")]},
    "mover la pestaña cuenta como clic": {
        "sesiones.html": [("if (Date.now() - pestMovida < 400) return;", "")]},
    "la pestaña de la lista no contrae nada": {
        "sesiones.html": [("const mostrar = hay && !colPlegada;", "const mostrar = hay;")]},
    "» del riel no muestra los nombres": {
        "sesiones.html": [("document.body.classList.toggle('riel-ancho', rielAncho);", "")]},
}


def main():
    mutar = "--mutar" in sys.argv
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav, fotos=True)
        for f in fallas:
            print("FALLA:", f)
        print("Vidrio con bandeja:", "todo bien" if not fallas else "%d fallas" % len(fallas))
        sin_cazar = []
        if mutar and not fallas:
            for nombre, cambios in MUTACIONES.items():
                cazada = bool(correr(nav, cambios))
                print(("cazada   " if cazada else "NO CAZADA"), "·", nombre)
                if not cazada:
                    sin_cazar.append(nombre)
        nav.close()
    sys.exit(1 if fallas or sin_cazar else 0)


if __name__ == "__main__":
    main()
