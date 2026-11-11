"""Las pastillas de proyecto llevan su color en Vidrio, y "Cerrar todas las pestañas" (2026-11-10).

Dos pedidos de Martín sobre la barra de arriba de `/sesiones`, con una captura del estilo
Vidrio: *"las ventanitas que están acá arriba creo que perdieron mucha identidad porque ahora
no tienen colores"* y *"me gustaría que cuando aprieto clic derecho sobre alguna de ellas me
salte la opción cerrar todas las pestañas"*.

    python -m pruebas.ver_pastillas_color            (con el panel prendido)
    python -m pruebas.ver_pastillas_color --mutar    (rompe cada pieza y exige que se note)

Lo que esta prueba cuida:
  · en Vidrio, la pastilla de una carpeta CON color lleva ese color en su superficie, y el
    nombre sigue en blanco (teñido era lo que no se leía sobre la foto);
  · una pastilla sin color elegido queda como estaba;
  · ⭐ el color sigue aunque la forma de las pastillas no sea la de fábrica: la regla del
    casco que les devuelve una superficie pesa más que una regla común y lo tapaba;
  · fuera de Vidrio no cambió nada: el estilo de siempre y Carta celeste pintan como antes;
  · "Cerrar todas las pestañas" está en el menú del botón derecho (pastilla y charla), vacía
    la barra de un clic, y durante medio minuto queda "↩ Volver a abrir", que las devuelve
    en el mismo orden sin pisar lo que hayas abierto en el medio.

⚠ Datos inventados, interceptados en el contexto: no se lee ni se escribe ninguna charla de
verdad, y nada que no sea un GET sale hacia el panel.
⚠ `--mutar` cambia el HTML EN MEMORIA, al servirlo a la página de prueba: el archivo del
disco no se toca nunca (hay otras sesiones mirándolo).
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
VERDE = "#1df500"          # un color de la rueda, como el que él le puso a una carpeta


def ses(sid, nombre):
    return {"id": sid, "nombre": nombre, "ts": AHORA - 600, "ultimo": "vos",
            "viva": False, "ocupada": False, "interactiva": False, "detalle": "x"}


# Cuatro carpetas: una con un tono de la fila, una con un color de la rueda, una sin color y
# otra con tono. Cinco pestañas abiertas entre las cuatro.
CARPETAS = ["alfa", "beta", "gama", "delta"]
ABIERTAS = [("alfa-1", "alfa", "uno"), ("alfa-2", "alfa", "dos"), ("beta-1", "beta", "tres"),
            ("gama-1", "gama", "cuatro"), ("delta-1", "delta", "cinco")]
TABS = [{"sid": s, "cwd": "D:\\pruebas\\" + c, "nombre": n, "cerebro": ""} for s, c, n in ABIERTAS]
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": CARPETAS, "ocultas": [],
                         "aspecto": {"alfa": {"color": "azul"}, "beta": {"color": VERDE},
                                     "delta": {"color": "arena"}}},
            "proyectos": [{"proyecto": c, "cwd": "D:\\pruebas\\" + c, "vivo": False,
                           "sesiones": [ses(s, n) for s, cc, n in ABIERTAS if cc == c]}
                          for c in CARPETAS]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None,
        "mensajes": [{"de": "claude", "texto": "hola", "imgs": []}]}
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}


def campos_del_estilo(k):
    """Los campos del estilo, leídos de aspecto.js: así la prueba mide lo que la pantalla usa."""
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def aspecto_de(estilo):
    return dict(ASPECTO, estilo=estilo, **campos_del_estilo(estilo)) if estilo else dict(ASPECTO)


# El color de verdad de cada pastilla: se pinta un punto con ese color y se lee el punto.
# Así da igual cómo lo escriba el navegador (`rgba()`, `color(srgb …)`).
MEDIR = """() => {
  const lienzo = document.createElement('canvas'); lienzo.width = lienzo.height = 1;
  const cx = lienzo.getContext('2d', {willReadFrequently: true});
  const rgba = c => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c;
                      cx.fillRect(0, 0, 1, 1); return [...cx.getImageData(0, 0, 1, 1).data]; };
  const sal = {};
  document.querySelectorAll('#tabs .grupo').forEach(g => {
    const e = getComputedStyle(g);
    sal[g.dataset.grupo] = {pintada: g.classList.contains('pintada'),
      fondo: rgba(e.backgroundColor), tinta: rgba(e.color), filo: e.boxShadow !== 'none'};
  });
  return sal;
}"""
BARRA = """() => ({sids: abiertas.map(t => t.sid), activa,
  pastillas: document.querySelectorAll('#tabs .grupo').length,
  charlas: document.querySelectorAll('#tabs .tab[data-i]').length,
  volver: (document.querySelector('#tabVolver') || {textContent: ''}).textContent,
  ultimo: document.querySelector('#tabs').lastElementChild.id,
  menu: document.getElementById('menuTarjeta').classList.contains('abierto'),
  guardadas: localStorage.getItem('sesTabs')})"""
OPCIONES = "() => [...document.querySelectorAll('#menuTarjeta .op')].map(o => o.textContent.trim())"


def cerca(color, r, g, b, a, margen=5):
    return all(abs(x - y) <= margen for x, y in zip(color, (r, g, b, a)))


def montar(nav, html, estilo):
    ctx = nav.new_context(viewport={"width": 1500, "height": 800}, device_scale_factor=2,
                          reduced_motion="reduce")
    errores = []
    aspecto = aspecto_de(estilo)

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        if camino == "/sesiones" and html is not None:
            return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
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
    pag.wait_for_timeout(600)
    pag.evaluate("""tabs => { pendientes = {}; falladas = {}; visto = {};
      abiertas = tabs; irTab('alfa-1'); }""", TABS)
    pag.wait_for_selector("#tabs .grupo[data-grupo='delta']", timeout=10000)
    pag.mouse.move(750, 600)                 # el puntero lejos de la barra: nada "encendido"
    pag.wait_for_timeout(600)
    return ctx, pag, errores


def reponer(pag, ahora, antes):
    """Si la barra no quedó como estaba, se la vuelve a armar a mano para poder seguir.

    Con el código sano no hace nada. Hace falta al MUTAR: sin el botón de volver las
    pestañas no vuelven, y los pasos de abajo se quedaban esperando una que ya no existe
    (la prueba se caía en vez de decir qué chequeo falló)."""
    if ahora["sids"] == antes["sids"]:
        return
    pag.evaluate("tabs => { abiertas = tabs; irTab('alfa-1'); }", TABS)
    pag.wait_for_timeout(400)


def correr(nav, html=None, fotos=False, callado=False):
    """Toda la prueba sobre una página. Devuelve los nombres de los chequeos que fallaron."""
    fallas = []

    def revisar(nombre, bien, detalle=""):
        if not callado:
            print(("ok   " if bien else "MAL  ") + nombre + (f"  -> {detalle}" if detalle and not bien else ""))
        if not bien:
            fallas.append(nombre)

    def decir(texto):
        if not callado:
            print(texto)

    # --- 1. Vidrio: el color vuelve a la pastilla ---------------------------------------
    decir("\nVidrio: las pastillas con color")
    ctx, pag, errores = montar(nav, html, "vidrio")
    m = pag.evaluate(MEDIR)
    revisar("la pantalla está en Vidrio (si no, lo de abajo no mide nada)",
            pag.evaluate("() => document.documentElement.classList.contains('vidrio')"))
    revisar("la carpeta con color se anota como pintada, y la que no tiene, no",
            [m["alfa"]["pintada"], m["beta"]["pintada"], m["gama"]["pintada"]] == [True, True, False],
            str([m[c]["pintada"] for c in CARPETAS]))
    # El tono medio del verde de la rueda es rgb(19,117,10); plegada va al 62 % (158 de 255).
    revisar("⭐ Vidrio: la pastilla pintada lleva el color de su carpeta",
            cerca(m["beta"]["fondo"], 19, 117, 10, 158), str(m["beta"]["fondo"]))
    revisar("y un filo de su color alrededor", m["beta"]["filo"])
    revisar("el nombre sigue en blanco: la misma tinta que una pastilla sin color",
            m["beta"]["tinta"] == m["gama"]["tinta"], f"{m['beta']['tinta']} / {m['gama']['tinta']}")
    revisar("una pastilla sin color queda como estaba (sin superficie ni filo)",
            m["gama"]["fondo"][3] == 0 and not m["gama"]["filo"], str(m["gama"]))
    revisar("la del proyecto desplegado se enciende más que las plegadas",
            m["alfa"]["fondo"][3] > m["delta"]["fondo"][3] + 20,
            f"{m['alfa']['fondo'][3]} contra {m['delta']['fondo'][3]}")
    if fotos:
        pag.screenshot(path=str(SALIDA / "pastillas_vidrio.png"),
                       clip={"x": 0, "y": 0, "width": 1500, "height": 120})
    pag.evaluate("() => { formas.grupo = 'pildora'; aplicarFormas(); }")
    pag.wait_for_timeout(400)
    p = pag.evaluate(MEDIR)
    revisar("⭐ con otra forma (píldora) el color sigue",
            cerca(p["beta"]["fondo"], 19, 117, 10, 158), str(p["beta"]["fondo"]))
    revisar("y la que no tiene color lleva la superficie neutra de esa forma",
            0 < p["gama"]["fondo"][3] < 40, str(p["gama"]["fondo"]))
    if fotos:
        pag.screenshot(path=str(SALIDA / "pastillas_vidrio_pildora.png"),
                       clip={"x": 0, "y": 0, "width": 1500, "height": 120})

    # --- 2. El menú del botón derecho: cerrar todas, y volver atrás ----------------------
    decir("\nBotón derecho: «Cerrar todas las pestañas»")
    antes = pag.evaluate(BARRA)
    pag.click("#tabs .grupo[data-grupo='gama']", button="right")
    pag.wait_for_timeout(300)
    revisar("con el botón derecho sobre una pastilla sale «Cerrar todas las pestañas»",
            any("Cerrar todas las pestañas" in o for o in pag.evaluate(OPCIONES)))
    if fotos:
        pag.screenshot(path=str(SALIDA / "pastillas_menu.png"),
                       clip={"x": 0, "y": 0, "width": 1500, "height": 640})
    revisar("y la de siempre sigue estando («Cerrar las de este proyecto»)",
            any("Cerrar las de este proyecto" in o for o in pag.evaluate(OPCIONES)))
    if pag.locator("#menuTarjeta .op[data-hace='cerrar-todas']").count():
        pag.click("#menuTarjeta .op[data-hace='cerrar-todas']")
    pag.wait_for_timeout(500)
    d = pag.evaluate(BARRA)
    revisar("⭐ «Cerrar todas» vacía la barra",
            [len(d["sids"]), d["pastillas"], d["charlas"]] == [0, 0, 0],
            str([len(d["sids"]), d["pastillas"], d["charlas"]]))
    revisar("queda guardado así (un F5 no las trae de vuelta)", d["guardadas"] == "[]", str(d["guardadas"]))
    revisar("te deja en la bandeja y el menú se cierra", d["activa"] is None and not d["menu"])
    revisar("⭐ queda a mano «Volver a abrir»", "Volver a abrir las 5" in d["volver"], repr(d["volver"]))
    revisar("y el ＋ sigue siendo el último de la fila", d["ultimo"] == "tabMas", d["ultimo"])
    if fotos:
        pag.mouse.move(750, 600)
        pag.screenshot(path=str(SALIDA / "pastillas_volver.png"),
                       clip={"x": 0, "y": 0, "width": 1500, "height": 120})
    if pag.locator("#tabVolver").count():
        pag.click("#tabVolver")
    pag.wait_for_timeout(500)
    d = pag.evaluate(BARRA)
    revisar("⭐ «Volver a abrir» las devuelve en el mismo orden", d["sids"] == antes["sids"], str(d["sids"]))
    revisar("y volvés a la charla que estabas leyendo", d["activa"] == antes["activa"], str(d["activa"]))
    revisar("el botón de volver se va apenas lo usás", d["volver"] == "")
    reponer(pag, d, antes)

    pag.click("#tabs .tab[data-sid='alfa-2']", button="right")
    pag.wait_for_timeout(300)
    revisar("sobre una conversación el menú también la ofrece",
            any("Cerrar todas las pestañas" in o for o in pag.evaluate(OPCIONES)))
    pag.keyboard.press("Escape")

    # Cerrás todas, abrís otra en el medio y te arrepentís: vuelven sin pisarte la de ahora.
    pag.evaluate("() => cerrarTodas()")
    pag.wait_for_timeout(300)
    pag.evaluate("t => abrirSesion(t.cwd, t.sid, t.nombre)", TABS[3])
    pag.wait_for_timeout(300)
    if pag.locator("#tabVolver").count():
        pag.click("#tabVolver")
    pag.wait_for_timeout(500)
    d = pag.evaluate(BARRA)
    revisar("si abriste otra en el medio, vuelven todas sin repetir ninguna",
            d["sids"] == antes["sids"], str(d["sids"]))
    revisar("y no te saca de la charla que abriste", d["activa"] == "gama-1", str(d["activa"]))
    reponer(pag, d, antes)

    # El medio minuto: pasado ese rato el botón se va solo, y recién ahí se tira el borrador
    # de una charla que nunca llegaste a estrenar.
    pag.clock.install()
    pag.evaluate("""() => { abiertas.push({sid: 'nueva-1', cwd: 'D:\\\\pruebas\\\\gama', nombre: 'Nueva', cerebro: ''});
                            borradores['nueva-1'] = 'a medio escribir'; cerrarTodas(); }""")
    pag.wait_for_timeout(300)
    medio = pag.evaluate("() => ({volver: !!document.querySelector('#tabVolver'), borrador: borradores['nueva-1'] || ''})")
    pag.clock.fast_forward(31000)
    pag.wait_for_timeout(400)
    fin = pag.evaluate("() => ({volver: !!document.querySelector('#tabVolver'), borrador: borradores['nueva-1'] || '', n: abiertas.length})")
    revisar("mientras se puede volver atrás, el borrador de una charla sin estrenar se conserva",
            medio == {"volver": True, "borrador": "a medio escribir"}, str(medio))
    revisar("pasado el medio minuto el botón se va solo y la barra sigue vacía",
            fin == {"volver": False, "borrador": "", "n": 0}, str(fin))
    revisar("sin errores de JavaScript en Vidrio", not errores, "; ".join(errores)[:300])
    ctx.close()
    if html is not None:                     # una mutación solo necesita lo de arriba
        return fallas

    # --- 3. Fuera de Vidrio no cambió nada ----------------------------------------------
    decir("\nLos otros estilos, como siempre")
    ctx, pag, errores = montar(nav, html, "")
    m = pag.evaluate(MEDIR)
    # El fondo de siempre: el tono OSCURO del color, opaco. Para ese verde, rgb(14,55,15).
    revisar("en el estilo de siempre la pastilla pintada lleva su fondo opaco de siempre",
            cerca(m["beta"]["fondo"], 14, 55, 15, 255), str(m["beta"]["fondo"]))
    revisar("y su nombre teñido del color vivo", cerca(m["beta"]["tinta"], 29, 245, 0, 255), str(m["beta"]["tinta"]))
    revisar("sin errores de JavaScript en el estilo de siempre", not errores, "; ".join(errores)[:300])
    ctx.close()
    ctx, pag, errores = montar(nav, html, "celeste")
    m = pag.evaluate(MEDIR)
    revisar("en Carta celeste el color sigue tiñendo el nombre, sin superficie",
            cerca(m["beta"]["tinta"], 29, 245, 0, 255) and m["beta"]["fondo"][3] == 0, str(m["beta"]))
    revisar("sin errores de JavaScript en Carta celeste", not errores, "; ".join(errores)[:300])
    ctx.close()
    return fallas


# Cada mutación rompe UNA pieza y dice qué chequeo tiene que notarlo.
BASE_REGLA = "html.carta.vidrio #tabs .grupo.pintada{"
MUTACIONES = [
    ("sacarle el color a la pastilla", BASE_REGLA, "html.carta.vidrio #tabs .grupo.pintadaNO{",
     "⭐ Vidrio: la pastilla pintada lleva el color de su carpeta"),
    ("sacar el #tabs del selector", BASE_REGLA, "html.carta.vidrio .grupo.pintada{",
     "⭐ con otra forma (píldora) el color sigue"),
    ("que «Cerrar todas» no cierre nada", "function cerrarTodas(){\n  if (!abiertas.length) return;",
     "function cerrarTodas(){\n  return;", "⭐ «Cerrar todas» vacía la barra"),
    ("sacar el botón de volver", "(cerradasRecien ? '<div class=\"tab volver\"",
     "(false ? '<div class=\"tab volver\"", "⭐ queda a mano «Volver a abrir»"),
    ("que volver a abrir pise lo que abriste", "abiertas = c.tabs.concat(abiertas.filter(t => !eran.has(t.sid)));",
     "abiertas = c.tabs.concat(abiertas);", "si abriste otra en el medio, vuelven todas sin repetir ninguna"),
]

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    if "--mutar" in sys.argv:
        original = (ESTATICOS / "sesiones.html").read_text(encoding="utf-8").replace("\r\n", "\n")
        cazadas = 0
        for nombre, viejo, nuevo, chequeo in MUTACIONES:
            if original.count(viejo) != 1:
                print(f"NO SE PUDO MUTAR  {nombre}: el texto a cambiar aparece {original.count(viejo)} veces")
                continue
            cayo = chequeo in correr(nav, html=original.replace(viejo, nuevo), callado=True)
            cazadas += cayo
            print(("cazada   " if cayo else "PASÓ DE LARGO  ") + nombre + "  ->  " + chequeo)
        nav.close()
        print(f"\n{'LA PRUEBA SIRVE' if cazadas == len(MUTACIONES) else 'HAY CHEQUEOS DE ADORNO'} — "
              f"{cazadas} de {len(MUTACIONES)} mutaciones cazadas\n")
        raise SystemExit(0 if cazadas == len(MUTACIONES) else 1)
    fallas = correr(nav, fotos=True)
    nav.close()

print(f"\n{'TODO BIEN' if not fallas else 'HAY PROBLEMAS'} — {len(fallas)} mal\n")
raise SystemExit(1 if fallas else 0)
