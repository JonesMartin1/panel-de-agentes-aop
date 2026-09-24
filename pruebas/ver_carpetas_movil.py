"""Mover y sacar las carpetas del cajón, pero EN EL CELULAR.

Pedido de Martín (2026-08-18), después de que quedara hecho en la pantalla grande: *"¿y
en el celu?"*. Es la misma función y los mismos datos (el orden y las escondidas viven en
el servidor), pero con OTRO gesto: en la compu alcanza con arrastrar porque el mouse no
hace scroll; acá el dedo ya usa el arrastre para recorrer el cajón, así que sacar una
carpeta es deslizarla a la izquierda —igual que se archiva una conversación— y moverla
pide mantenerla apretada primero.

⚠ El HTML del celular vive DENTRO de `panel.py` (la constante `MOVIL_HTML`), así que el
panel que está corriendo sirve el viejo hasta que se lo reinicie. Por eso acá se lee el
`panel.py` del disco y se sirve ese HTML: la prueba corre sin reiniciar nada.
⚠ `/movil/sesiones`, `/carpetas/orden` y `/carpetas/ocultar` también se interceptan: la
lista es inventada (con la real, el chequeo del orden dependería de qué proyectos tenga
hoy en el disco) y así no se le toca a Martín ni una carpeta de verdad.

Correr con:  python -m pruebas.ver_carpetas_movil   (no hace falta el panel prendido)
"""
import ast
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8750"
fallas = []

PROYECTOS = ["alfa", "beta", "gama", "delta"]
ORDEN_SERVIDOR = ["gama", "alfa", "delta", "beta"]      # el orden que ya eligió Martín
OCULTAS_SERVIDOR = ["delta"]

guardado = {"orden": None, "ocultas": list(OCULTAS_SERVIDOR),
            # ⭐ Desde el 2026-08-25 la identidad de cada carpeta (icono, color, apodo)
            # tambien vive en el servidor: lo que Martin elige en la compu tiene que
            # aparecer acá y al revés. `beta` llega ya vestida desde la pantalla grande.
            "aspecto": {"beta": {"icono": "🤖", "color": "arena", "apodo": "Beta SRL"}},
            "iconosPropios": ["🐱"],          # uno que Martin agregó con el ＋ en la compu
            "sembrado": None}

# La hora del archivo REAL antes de empezar: al final se chequea que siga igual.
_real = RAIZ / "orden_carpetas.json"
sello_archivo = _real.stat().st_mtime if _real.exists() else None


def sesiones_json():
    return {"ok": True, "laura": "",
            # El servidor de mentira devuelve lo ÚLTIMO que le guardaron, como el de
            # verdad: si acá quedara fijo el orden inicial, la pantalla se vería
            # deshacer sola cada cambio y la prueba estaría midiendo el molde.
            "carpetas": {"orden": guardado["orden"] or ORDEN_SERVIDOR,
                         "ocultas": guardado["ocultas"],
                         "aspecto": guardado["aspecto"],
                         "iconosPropios": guardado["iconosPropios"]},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-1", "nombre": "charla de " + n,
                                         "ts": 1, "ultimo": "vos", "viva": False,
                                         "interactiva": False, "detalle": ""}]}
                          for n in PROYECTOS]}


def movil_html():
    """El HTML del celular, sacado del `panel.py` del disco (no del panel corriendo)."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


# Los gestos del dedo. Playwright sabe tocar, pero no deslizar ni mantener apretado:
# los eventos se arman a mano, que es exactamente lo que escucha la pantalla.
GESTOS = """
window.__t = (el, tipo, x, y) => {
  const t = new Touch({identifier: 1, target: el, clientX: x, clientY: y,
                       pageX: x, pageY: y, screenX: x, screenY: y});
  el.dispatchEvent(new TouchEvent(tipo, {bubbles: true, cancelable: true,
    touches: tipo === 'touchend' ? [] : [t],
    targetTouches: tipo === 'touchend' ? [] : [t], changedTouches: [t]}));
};
window.__carp = n => [...document.querySelectorAll('#cajon .carpeta[data-proy]')]
                       .find(c => c.dataset.proy === n);
window.__nombres = () => [...document.querySelectorAll('#cajon .carpeta[data-proy]')]
                           .map(c => c.dataset.proy);
"""


def nombres(pag):
    return pag.evaluate("() => __nombres()")


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 390, "height": 844},
                          has_touch=True, is_mobile=True, device_scale_factor=3)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))

    HTML = movil_html()

    def orden(ruta):
        d = ruta.request.post_data_json or {}
        guardado["orden"] = d.get("orden")
        ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')

    def ocultar(ruta):
        d = ruta.request.post_data_json or {}
        if d.get("ocultar"):
            guardado["ocultas"].append(d.get("proyecto"))
        else:
            guardado["ocultas"] = [x for x in guardado["ocultas"] if x != d.get("proyecto")]
        ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')

    def json_fijo(cuerpo):
        return lambda r: r.fulfill(status=200, content_type="application/json",
                                   body=json.dumps(cuerpo))

    # ⚠⚠ El colador va PRIMERO: cualquier pedido a `/carpetas/…` que no reconozcan los
    # dos de abajo muere acá y se anota. Una corrida del 2026-08-19 se quedó sin estas
    # dos líneas y los pedidos salieron al panel DE VERDAD: le dejó cuatro nombres
    # inventados en el orden real y una carpeta escondida que él nunca sacó. La regla es
    # que una prueba de pantalla no puede escribirle datos de verdad ni por accidente.
    escapados = []
    pag.route("**/carpetas/**", lambda r: (escapados.append(r.request.url),
              r.fulfill(status=200, content_type="application/json", body='{"ok":true}')))
    def aspecto(ruta):
        """El servidor de mentira, con la misma regla que el de verdad: se cambia SOLO el
        campo que vino, para que dos pantallas abiertas a la vez no se pisen."""
        d = ruta.request.post_data_json or {}
        if isinstance(d.get("iconosPropios"), list):
            guardado["iconosPropios"] = d["iconosPropios"]
        n = d.get("carpeta")
        if n:
            a = dict(guardado["aspecto"].get(n) or {})
            for campo in ("icono", "color", "apodo"):
                if campo in d:
                    a[campo] = d[campo]
                    if not d[campo]:
                        a.pop(campo, None)
            guardado["aspecto"][n] = a
            if not a:
                guardado["aspecto"].pop(n)
        ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')

    def sembrar(ruta):
        guardado["sembrado"] = ruta.request.post_data_json or {}
        ruta.fulfill(status=200, content_type="application/json",
                     body='{"ok":true,"sembradas":0,"choques":0}')

    # El selector de navegador del editor de carpeta pide los perfiles de Chrome del
    # disco (2026-08-28). Se contesta vacio: aca no se prueba esa perilla, pero sin
    # interceptarlo el pedido se le escapa al panel de verdad y lo caza el chequeo final.
    pag.route("**/carpetas/navegadores*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"perfiles":[]}'))
    pag.route("**/carpetas/orden*", orden)
    pag.route("**/carpetas/ocultar*", ocultar)
    pag.route("**/carpetas/aspecto", aspecto)
    pag.route("**/carpetas/aspecto/sembrar", sembrar)
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html", body=HTML))
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(sesiones_json())))
    pag.route("**/movil/pestanas*", json_fijo({"pestanas": [], "activa": "nueva"}))
    pag.route("**/movil/borradores*", json_fijo({}))
    pag.route("**/movil/donde*", json_fijo({"ok": True}))
    pag.route("**/status*", json_fijo({"servicios": {}, "encendido": False}))

    pag.add_init_script("localStorage.clear(); localStorage.setItem('activa','nueva');")
    pag.add_init_script(GESTOS)
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_selector(".menu", timeout=8000)
    pag.tap(".menu")                                   # ☰: abrir el cajón de proyectos
    pag.wait_for_selector("#cajon .carpeta[data-proy]", timeout=8000)
    pag.wait_for_timeout(400)

    # --- 1. Lo que decidió en la compu ya está acá -----------------------------------
    revisar("respeta el orden del servidor", nombres(pag), ["gama", "alfa", "beta"])
    revisar("la escondida no se muestra", "delta" in nombres(pag), False)
    revisar("Todas no es arrastrable (no tiene data-proy)",
            pag.evaluate("() => !!document.querySelector('#cajon .carpeta.todas[data-proy]')"), False)
    revisar("cuenta el pie de escondidas",
            pag.eval_on_selector("#verOcultas .num", "e => e.textContent.trim()"), "1")
    revisar("dice cómo se hacen los dos gestos",
            pag.eval_on_selector(".pista-carp", "e => e.textContent.toLowerCase().includes('deslizá')"
                                                " && e.textContent.includes('apretada')"), True)

    # --- 1b. ⭐⭐ La identidad elegida en la COMPU ya está acá (2026-08-25) -------------
    # Este teléfono arranca con el `localStorage` vacío —o sea, es "otro navegador"— y aun
    # así tiene que verse todo: era exactamente lo que Martín pedía ("que no importa si
    # abro desde el celular, la app de escritorio o desde otro navegador").
    revisar("el ícono elegido en la compu se ve en el celular",
            pag.eval_on_selector(".carpeta[data-proy='beta'] .ic", "e => e.textContent"), "🤖")
    revisar("y su color también",
            pag.evaluate("() => __carp('beta').style.getPropertyValue('--carp-color')"), "#e2cdb0")
    revisar("y el apodo, que es solo el rótulo",
            pag.eval_on_selector(".carpeta[data-proy='beta'] .nom", "e => e.textContent"), "Beta SRL")
    revisar("pero la llave sigue siendo el nombre real de la carpeta",
            pag.evaluate("() => !!__carp('beta')"), True)
    revisar("este navegador sembró lo suyo una sola vez",
            (guardado["sembrado"] or {}).get("origen"), "celu")

    # Los íconos que Martín agregó a mano en la compu también están en la paleta de acá.
    pag.tap(".carpeta[data-proy='beta'] .editar-carp")
    pag.wait_for_selector("#editorCarp.abierto")
    revisar("el ícono propio de la compu aparece en el editor del celular",
            pag.evaluate("() => !!document.querySelector(\"#editorCarp [data-ico='🐱']\")"), True)
    revisar("y el que la carpeta ya usa está marcado",
            pag.evaluate("() => document.querySelector('#editorCarp .ico-edit.sel').dataset.ico"), "🤖")
    pag.tap("#editorCarp .cerrar-edit")
    pag.wait_for_timeout(200)

    # --- 2. Editar color e ícono sin entrar ni levantar la carpeta -------------------
    pag.tap(".carpeta[data-proy='gama'] .editar-carp")
    pag.wait_for_selector("#editorCarp.abierto")
    revisar("el lápiz abre el editor de esa carpeta",
            pag.eval_on_selector("#editorCarp .edit-nombre", "e => e.textContent"), "gama")
    # ⚠ Los colores van por NOMBRE, no por hex: son los mismos seis tonos que `/sesiones`,
    # así el que elegís acá queda marcado allá (antes cada pantalla tenía su paleta).
    pag.tap("#editorCarp [data-color='violeta']")
    pag.wait_for_selector("#editorCarp.abierto")
    revisar("el color se ve en la fila",
            pag.evaluate("() => __carp('gama').classList.contains('personalizada')"
                         " && __carp('gama').style.getPropertyValue('--carp-color')==='#c4b5fd'"), True)
    pag.tap("#editorCarp [data-ico='🔥']")
    pag.wait_for_selector("#editorCarp.abierto")
    revisar("el ícono elegido reemplaza a la carpeta genérica",
            pag.eval_on_selector(".carpeta[data-proy='gama'] .ic", "e => e.textContent"), "🔥")
    revisar("el aspecto queda guardado en el teléfono",
            pag.evaluate("() => JSON.parse(localStorage.getItem('movilAspectoCarpetas')).gama"),
            {"color": "violeta", "icono": "🔥"})
    # ⭐⭐ Y lo que de verdad se arregló el 2026-08-25: sube al SERVIDOR, así el mismo
    # ícono está en la compu, en otro navegador y en la app de escritorio.
    revisar("el cambio sube al servidor", guardado["aspecto"].get("gama"),
            {"color": "violeta", "icono": "🔥"})
    pag.screenshot(path=str(RAIZ / "resultados" / "prueba_editor_carpetas_movil.png"))
    pag.tap("#editorCarp .cerrar-edit")
    revisar("editar no entra al proyecto",
            pag.eval_on_selector(".barra-proy .quien b", "e => e.textContent"),
            "Todas las conversaciones")

    # --- 3. El camino de vuelta -------------------------------------------------------
    pag.tap("#verOcultas")
    pag.wait_for_timeout(300)
    revisar("desplegar muestra la escondida",
            pag.eval_on_selector_all("[data-volver]", "l => l.map(x => x.dataset.volver)"), ["delta"])
    pag.tap("[data-volver]")
    pag.wait_for_timeout(600)
    revisar("devolver avisa al servidor", guardado["ocultas"], [])
    revisar("y vuelve a su lugar del orden", nombres(pag), ["gama", "alfa", "delta", "beta"])
    revisar("se ilumina la que volvió",
            pag.evaluate("() => !!__carp('delta') && __carp('delta').className.includes('vuelve')"), True)

    # --- 4. Sacar una carpeta con el dedo ---------------------------------------------
    pag.evaluate("""() => {
      const el = __carp('alfa'), r = el.getBoundingClientRect();
      const x = r.left + r.width - 20, y = r.top + r.height / 2;
      __t(el, 'touchstart', x, y);
      for (let i = 1; i <= 8; i++) __t(el, 'touchmove', x - i * 20, y);
      __t(el, 'touchend', x - 160, y);
    }""")
    pag.wait_for_timeout(900)
    revisar("deslizar a la izquierda la saca", guardado["ocultas"], ["alfa"])
    revisar("y deja de verse", nombres(pag), ["gama", "delta", "beta"])
    revisar("el pie vuelve a aparecer",
            pag.eval_on_selector("#verOcultas .num", "e => e.textContent.trim()"), "1")

    # Un deslizamiento corto NO saca nada: es el pulso de la mano, no una decisión.
    pag.evaluate("""() => {
      const el = __carp('gama'), r = el.getBoundingClientRect();
      const x = r.left + r.width - 20, y = r.top + r.height / 2;
      __t(el, 'touchstart', x, y);
      for (let i = 1; i <= 3; i++) __t(el, 'touchmove', x - i * 8, y);
      __t(el, 'touchend', x - 24, y);
    }""")
    pag.wait_for_timeout(500)
    revisar("un deslizamiento corto no saca nada", guardado["ocultas"], ["alfa"])
    revisar("la lista quedó igual", nombres(pag), ["gama", "delta", "beta"])

    # --- 4. Buscando aparecen también las escondidas ----------------------------------
    pag.fill("#buscaCarp", "al")
    pag.wait_for_timeout(600)
    revisar("buscando se ve la escondida", nombres(pag), ["alfa"])
    revisar("y ahí no va el pie de escondidas",
            pag.evaluate("() => !!document.querySelector('#verOcultas')"), False)
    pag.fill("#buscaCarp", "")
    pag.wait_for_timeout(600)
    revisar("vaciar el buscador la vuelve a esconder", nombres(pag), ["gama", "delta", "beta"])

    # --- 5. Mover una carpeta: mantener apretado y recién ahí arrastrar ----------------
    # Arrastrar SIN mantener apretado no mueve nada: eso es el scroll del cajón.
    pag.evaluate("""() => {
      const el = __carp('gama'), r = el.getBoundingClientRect();
      window.__p = {x: r.left + r.width / 2, y: r.top + r.height / 2, h: r.height, el};
      __t(el, 'touchstart', __p.x, __p.y);
      for (let i = 1; i <= 6; i++) __t(el, 'touchmove', __p.x, __p.y + i * __p.h * 0.3);
      __t(el, 'touchend', __p.x, __p.y + __p.h * 1.8);
    }""")
    pag.wait_for_timeout(500)
    revisar("arrastrar sin apretar no mueve (es scroll)", guardado["orden"], None)
    revisar("y la lista sigue igual", nombres(pag), ["gama", "delta", "beta"])

    # Ahora sí: apretar, esperar, y arrastrar una fila hacia abajo.
    pag.evaluate("""() => {
      const el = __carp('gama'), r = el.getBoundingClientRect();
      window.__p = {x: r.left + r.width / 2, y: r.top + r.height / 2, h: r.height, el};
      __t(el, 'touchstart', __p.x, __p.y);
    }""")
    pag.wait_for_timeout(600)                          # más que LARGO_MOVER
    revisar("mantenerla apretada la levanta",
            pag.evaluate("() => __p.el.className.includes('tomada')"), True)
    pag.evaluate("""() => {
      for (let i = 1; i <= 10; i++) __t(__p.el, 'touchmove', __p.x, __p.y + i * __p.h * 0.14);
    }""")
    revisar("mientras se mueve, no se repinta por atrás",
            pag.evaluate("() => arrastrandoCarp"), True)
    pag.evaluate("() => __t(__p.el, 'touchend', __p.x, __p.y + __p.h)")
    pag.wait_for_timeout(700)
    revisar("soltar deja el orden nuevo", nombres(pag), ["delta", "gama", "beta"])
    revisar("y lo guarda en el servidor con la escondida detrás",
            guardado["orden"], ["delta", "gama", "beta", "alfa"])
    revisar("ya no está levantada",
            pag.evaluate("() => !!document.querySelector('#cajon .carpeta.tomada')"), False)
    revisar("y se puede volver a repintar",
            pag.evaluate("() => arrastrandoCarp"), False)

    # --- 6. El toque de siempre sigue entrando al proyecto ----------------------------
    # ⚠ Pero NO el toque que cierra un arrastre: soltar la carpeta donde la moviste no
    # puede además cambiarte de carpeta.
    revisar("el toque que cierra el arrastre no entra",
            pag.evaluate("() => proyElegido"), "Todas las conversaciones")
    pag.tap("#cajon .carpeta[data-proy='beta']")
    pag.wait_for_timeout(700)
    revisar("tocarla sí entra al proyecto", pag.evaluate("() => proyElegido"), "beta")
    revisar("y cierra el cajón", pag.evaluate("() => cajonAbierto"), False)

    # --- 7. Sacar la carpeta donde estás parado te devuelve a Todas -------------------
    pag.tap(".menu")
    pag.wait_for_timeout(400)
    pag.evaluate("""() => {
      const el = __carp('beta'), r = el.getBoundingClientRect();
      const x = r.left + r.width - 20, y = r.top + r.height / 2;
      __t(el, 'touchstart', x, y);
      for (let i = 1; i <= 8; i++) __t(el, 'touchmove', x - i * 20, y);
      __t(el, 'touchend', x - 160, y);
    }""")
    pag.wait_for_timeout(900)
    revisar("sacar donde estabas parado vuelve a Todas",
            pag.evaluate("() => proyElegido"), "Todas las conversaciones")
    revisar("y la bandeja sigue mostrando todo",
            pag.eval_on_selector_all(".correo[data-sid]", "l => l.length"), len(PROYECTOS))

    # --- 8. Una carpeta nueva cae al final, no arriba de todo -------------------------
    PROYECTOS.append("omega")
    pag.evaluate("() => { elegirFirma = ''; pintarElegir(); }")
    pag.wait_for_timeout(800)
    revisar("la carpeta nueva va al final", nombres(pag)[-1], "omega")

    revisar("sin errores de JavaScript", errores, [])
    # El de verdad quedó intacto: ningún pedido se escapó al panel.
    revisar("no se le escribió nada al panel de verdad", escapados, [])
    revisar("y el archivo real no se tocó",
            (RAIZ / "orden_carpetas.json").stat().st_mtime, sello_archivo)
    nav.close()

print("")
print("TODO BIEN" if not fallas else "FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
sys.exit(1 if fallas else 0)
