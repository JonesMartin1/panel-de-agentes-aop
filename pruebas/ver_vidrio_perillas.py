"""Las perillas del vidrio en el 🎨 (2026-11-10).

Pedido de Martín: *"siento que tengo limitaciones a la hora de configurar el vidrio"*. Hasta
ese día el 🎨 tenía una sola fila (Opaco / Normal / Vidrio) que movía solo el desenfoque; el
resto del material del estilo Vidrio era número fijo en la hoja de Sesiones. Eligió las cuatro
perillas que se le ofrecieron: opacidad de los paneles, desenfoque con deslizador, color del
vidrio, y brillo del borde + grano.

    python -m pruebas.ver_vidrio_perillas            (con el panel prendido)
    python -m pruebas.ver_vidrio_perillas --mutar    (rompe cada pieza y exige que se note)

Lo que cuida:
  · ⭐ sin elegir nada, el vidrio es EXACTAMENTE el de antes (los mismos números de la hoja);
  · cada perilla llega a la pantalla: se mide el panel de verdad (su color, su desenfoque, su
    borde, su grano), no las clases;
  · el desenfoque acepta un número Y las tres palabras de siempre (los estilos las usan);
  · en el 🎨 hay una sección "Vidrio" con cuatro deslizadores y los colores; moverlos cambia
    la pantalla en vivo y al soltar se manda a guardar con su campo;
  · el ↺ aparece solo en lo que cambiaste y lo devuelve a fábrica;
  · elegir el estilo Vidrio otra vez deja el material de fábrica;
  · `panel.py` deja pasar los cuatro campos nuevos (si no, se pierden al recargar).

⚠ Datos inventados: nada que no sea un GET llega al panel, y `--mutar` cambia el código EN
MEMORIA, al servirlo a la página de prueba. Los archivos del disco no se tocan.
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

SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa"], "ocultas": []},
            "proyectos": [{"proyecto": "alfa", "cwd": "D:\\pruebas\\alfa", "vivo": False,
                           "sesiones": [{"id": "alfa-1", "nombre": "uno", "ts": AHORA - 600,
                                         "ultimo": "vos", "viva": False, "ocupada": False,
                                         "interactiva": False, "detalle": "x"}]}]}
CHAT = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None,
        "mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                     {"de": "claude", "texto": "una respuesta", "imgs": []}]}


def campos_del_estilo(k):
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


VIDRIO = dict({"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
               "letra": "normal", "velo": "media", "rastro": "tema", "estilo": "vidrio"},
              **campos_del_estilo("vidrio"))

# Lo que mide cada vez: el riel (un panel), la hoja de la charla y el vidrio de las barras.
# Los colores se leen pintándolos en un punto, así da igual cómo los escriba el navegador.
MEDIR = """() => {
  const lienzo = document.createElement('canvas'); lienzo.width = lienzo.height = 1;
  const cx = lienzo.getContext('2d', {willReadFrequently: true});
  const rgba = c => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c;
                      cx.fillRect(0, 0, 1, 1); return [...cx.getImageData(0, 0, 1, 1).data]; };
  const riel = getComputedStyle(document.querySelector('aside'));
  const hoja = getComputedStyle(document.body, '::before');
  const barras = getComputedStyle(document.body, '::after');
  const blur = s => { const m = /blur\\(([\\d.]+)px\\)/.exec(s.backdropFilter); return m ? +(+m[1]).toFixed(1) : 0; };
  return {vidrio: document.documentElement.classList.contains('vidrio'),
    panel: rgba(riel.backgroundColor), hoja: rgba(hoja.backgroundColor),
    barras: rgba(barras.backgroundColor), blur: blur(riel),
    filo: rgba(riel.borderTopColor)[3],
    grano: riel.backgroundImage.includes('feTurbulence'),
    granoOp: (/opacity='([\\d.]+)'/.exec(decodeURIComponent(riel.backgroundImage)) || [0, null])[1],
    luz: +((/rgba\\(255, 255, 255, ([\\d.]+)\\) 0px 1px 0px 0px inset/.exec(riel.boxShadow) || [0, 0])[1])};
}"""


def montar(nav, aspecto, cambios=None):
    """La pantalla con `aspecto`. `cambios` = {archivo: (viejo, nuevo)} para las mutaciones."""
    ctx = nav.new_context(viewport={"width": 1500, "height": 850}, reduced_motion="reduce")
    errores, guardados = [], []

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        for archivo, (viejo, nuevo) in (cambios or {}).items():
            if camino.endswith("/" + archivo) or (archivo == "sesiones.html" and camino == "/sesiones"):
                cuerpo = (ESTATICOS / archivo).read_text(encoding="utf-8").replace(viejo, nuevo)
                tipo = "text/html" if archivo.endswith(".html") else "application/javascript"
                return r.fulfill(status=200, content_type=tipo + "; charset=utf-8", body=cuerpo)
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            cuerpo = CHAT
        elif camino == "/aspecto" and r.request.method == "GET":
            cuerpo = aspecto
        elif r.request.method != "GET":
            if camino == "/aspecto":
                guardados.append(r.request.post_data_json)
                cuerpo = {"ok": True, "aspecto": r.request.post_data_json}
            else:
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
    pag.evaluate("() => { abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'uno', cerebro: ''}];"
                 " irTab('alfa-1'); }")
    pag.wait_for_selector("#hilo .msg.claude", timeout=15000)
    pag.wait_for_timeout(700)
    return ctx, pag, errores, guardados


def cerca(a, b, margen=4):
    return all(abs(x - y) <= margen for x, y in zip(a, b))


def correr(nav, cambios=None, fotos=False, callado=False):
    fallas = []

    def revisar(nombre, bien, detalle=""):
        if not callado:
            print(("ok   " if bien else "MAL  ") + nombre + (f"  -> {detalle}" if detalle and not bien else ""))
        if not bien:
            fallas.append(nombre)

    def decir(t):
        if not callado:
            print(t)

    # --- 1. De fábrica: los números de siempre -------------------------------------------
    decir("\nSin elegir nada: el vidrio de antes")
    ctx, pag, errores, _ = montar(nav, VIDRIO, cambios)
    fab = pag.evaluate(MEDIR)
    revisar("la pantalla está en Vidrio (si no, lo de abajo no mide nada)", fab["vidrio"])
    revisar("⭐ el panel es el velo blanco de siempre (8,5 %)", cerca(fab["panel"], [255, 255, 255, 22], 2), str(fab["panel"]))
    revisar("la hoja de la charla, el fondo al 50 %", abs(fab["hoja"][3] - 128) <= 3, str(fab["hoja"]))
    revisar("el desenfoque de Vidrio: 18 px × 1,7", fab["blur"] == 30.6, str(fab["blur"]))
    revisar("el borde, al 18 % de blanco", abs(fab["filo"] - 46) <= 2, str(fab["filo"]))
    revisar("el filo de luz de arriba, al 34 %", abs(fab["luz"] - .34) < .02, str(fab["luz"]))
    revisar("y el grano de siempre (7 %)", fab["grano"] and fab["granoOp"] == ".07", str(fab["granoOp"]))
    revisar("sin variables escritas en el <html> (manda la hoja)",
            pag.evaluate("() => ['--vd-vidrio','--vd-hoja','--vd-b','--vd-grano'].every("
                         "k => !document.documentElement.style.getPropertyValue(k))"))
    ctx.close()

    # --- 2. Cada perilla llega a la pantalla ----------------------------------------------
    decir("\nCon cada perilla puesta")
    elegido = dict(VIDRIO, vidrio="0.5", vdOpaco="90", vdTinte="#c08a5a", vdBrillo="200", vdGrano="0")
    ctx, pag, errores2, _ = montar(nav, elegido, cambios)
    m = pag.evaluate(MEDIR)
    revisar("⭐ el desenfoque toma el número del deslizador (18 px × 0,5)", m["blur"] == 9, str(m["blur"]))
    revisar("⭐ con la opacidad alta el panel casi tapa la foto", m["panel"][3] > 200, str(m["panel"]))
    revisar("y la hoja de la charla también", m["hoja"][3] > 220, str(m["hoja"]))
    revisar("⭐ el color del vidrio tiñe el panel (más rojo que azul)", m["panel"][0] > m["panel"][2] + 8, str(m["panel"]))
    revisar("las barras de arriba son el mismo vidrio que el panel", cerca(m["barras"], m["panel"], 3),
            f"{m['barras']} / {m['panel']}")
    revisar("⭐ el brillo al doble: el borde pasa de 18 % a 36 %", abs(m["filo"] - 92) <= 3, str(m["filo"]))
    revisar("y el filo de luz de arriba también se duplica (34 % → 68 %)", abs(m["luz"] - .68) < .02, str(m["luz"]))
    revisar("⭐ con el grano en 0 no hay grano", not m["grano"], "")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vidrio_perillas_solido.png"), clip={"x": 0, "y": 0, "width": 1500, "height": 500})
    ctx.close()
    elegido = dict(VIDRIO, vdOpaco="0", vdGrano="200", vidrio="mucho")
    ctx, pag, errores3, _ = montar(nav, elegido, cambios)
    m = pag.evaluate(MEDIR)
    revisar("con la opacidad en 0 los paneles son invisibles (solo el desenfoque)", m["panel"][3] <= 2, str(m["panel"]))
    revisar("el desenfoque sigue entendiendo las palabras de siempre ('mucho')", m["blur"] == 30.6, str(m["blur"]))
    revisar("el grano al doble (14 %)", m["granoOp"] == "0.140", str(m["granoOp"]))
    if fotos:
        pag.screenshot(path=str(SALIDA / "vidrio_perillas_transparente.png"), clip={"x": 0, "y": 0, "width": 1500, "height": 500})
    ctx.close()

    # --- 3. El 🎨: la sección, en vivo, guardar y el ↺ ------------------------------------
    decir("\nEl 🎨")
    ctx, pag, errores4, guardados = montar(nav, VIDRIO, cambios)
    pag.click("#aspectoBtn")
    pag.wait_for_timeout(400)
    pag.evaluate("() => { const d = document.querySelector('#aspectoPanel details[data-sec=\"vidrio\"]'); if (d) d.open = true; }")
    pag.wait_for_timeout(300)
    sec = pag.evaluate("""() => { const d = document.querySelector('#aspectoPanel details[data-sec="vidrio"]');
      if (!d) return null;
      return {deslices: [...d.querySelectorAll('.desliz')].map(x => x.dataset.desliz),
              tintes: [...d.querySelectorAll('.ops[data-campo="vdTinte"] .op')].map(o => o.textContent.trim()),
              rueda: !!d.querySelector('#aspRuedaVd'),
              quitar: d.querySelectorAll('.quitar').length,
              aviso: !!d.querySelector('.avisoVidrio'),
              viejaFila: !!document.querySelector('#aspectoPanel .ops[data-campo="vidrio"]')}; }""")
    revisar("⭐ el 🎨 tiene una sección «Vidrio»", sec is not None)
    sec = sec or {"deslices": [], "tintes": [], "rueda": False, "quitar": -1, "aviso": True, "viejaFila": True}
    revisar("con los cuatro deslizadores", sec["deslices"] == ["vidrio", "vdOpaco", "vdBrillo", "vdGrano"], str(sec["deslices"]))
    revisar("y los colores del vidrio más la rueda", len(sec["tintes"]) == 5 and sec["rueda"], str(sec["tintes"]))
    revisar("sin ↺ mientras está todo de fábrica", sec["quitar"] == 0, str(sec["quitar"]))
    revisar("con el estilo Vidrio puesto no avisa que falta el estilo", not sec["aviso"])
    revisar("la fila vieja de tres pastillas ya no está", not sec["viejaFila"])
    if fotos:
        caja = pag.evaluate("() => { const r = document.querySelector('#aspectoPanel details[data-sec=\"vidrio\"]').getBoundingClientRect();"
                            " return {x: r.x, y: r.y, width: r.width, height: r.height}; }")
        pag.screenshot(path=str(SALIDA / "vidrio_perillas_panel.png"), clip=caja)

    def mover(k, valor, soltar=True):
        pag.evaluate("""([k, v, s]) => { const i = document.querySelector('#aspectoPanel .desliz[data-desliz="' + k + '"] input');
          i.value = v; i.dispatchEvent(new Event('input', {bubbles: true}));
          if (s) i.dispatchEvent(new Event('change', {bubbles: true})); }""", [k, valor, soltar])
        pag.wait_for_timeout(250)

    antes = len(guardados)
    mover("vdOpaco", 85, soltar=False)
    vivo = pag.evaluate(MEDIR)
    revisar("⭐ mover la opacidad cambia el panel en el acto, sin soltar", vivo["panel"][3] > 180, str(vivo["panel"]))
    revisar("y mientras arrastrás no se manda nada a guardar", len(guardados) == antes)
    revisar("el numerito de al lado sigue a la barra",
            pag.evaluate("() => document.querySelector('#aspectoPanel .desliz[data-desliz=\"vdOpaco\"] .val').textContent") == "85 %")
    mover("vdOpaco", 85)
    revisar("⭐ al soltar se manda a guardar, con su campo", bool(guardados) and guardados[-1].get("vdOpaco") == "85",
            str(guardados[-1].get("vdOpaco") if guardados else None))
    mover("vidrio", 100)
    revisar("el desenfoque del deslizador también se guarda", guardados[-1].get("vidrio") == "1.00", str(guardados[-1].get("vidrio")))
    revisar("y la pantalla lo toma (18 px)", pag.evaluate(MEDIR)["blur"] == 18)
    pag.click("#aspectoPanel .ops[data-campo='vdTinte'] .op[data-v='azulado']")
    pag.wait_for_timeout(300)
    t = pag.evaluate(MEDIR)
    revisar("elegir «Azulado» tiñe el panel de azul", t["panel"][2] > t["panel"][0] + 8, str(t["panel"]))
    revisar("y se guarda", guardados[-1].get("vdTinte") == "azulado", str(guardados[-1].get("vdTinte")))
    revisar("⭐ ahora hay ↺ en lo que cambiaste (opacidad y desenfoque)",
            pag.evaluate("() => [...document.querySelectorAll('#aspectoPanel .desliz.puesto')].map(x => x.dataset.desliz)")
            == ["vidrio", "vdOpaco"])
    pag.click("#aspectoPanel .desliz[data-desliz='vidrio'] .quitar")
    pag.wait_for_timeout(300)
    revisar("el ↺ del desenfoque lo vuelve al de Vidrio (30,6 px)", pag.evaluate(MEDIR)["blur"] == 30.6)
    pag.click("#aspectoPanel .desliz[data-desliz='vdOpaco'] .quitar")
    pag.wait_for_timeout(300)
    revisar("el ↺ de la opacidad la vuelve a fábrica", guardados[-1].get("vdOpaco") == "", str(guardados[-1].get("vdOpaco")))
    pag.click("#aspectoPanel .esti[data-esti='vidrio']")
    pag.wait_for_timeout(400)
    v = pag.evaluate(MEDIR)
    revisar("⭐ volver a elegir el estilo Vidrio deja el material de fábrica (sin tinte)",
            cerca(v["panel"], [255, 255, 255, 22], 2), str(v["panel"]))
    revisar("sin errores de JavaScript", not (errores + errores2 + errores3 + errores4),
            "; ".join(errores + errores2 + errores3 + errores4)[:300])
    ctx.close()

    # --- 4. Fuera de Vidrio el 🎨 lo avisa ------------------------------------------------
    ctx, pag, errores5, _ = montar(nav, {"tipo": "segoe", "color": "celeste", "fondo": "azulado",
                                         "img": "", "letra": "normal", "velo": "media", "rastro": "tema"}, cambios)
    pag.click("#aspectoBtn")
    pag.wait_for_timeout(400)
    revisar("con otro estilo, la sección avisa que esto se ve con Vidrio",
            pag.evaluate("() => !!document.querySelector('#aspectoPanel details[data-sec=\"vidrio\"] .avisoVidrio')"))
    revisar("sin errores de JavaScript con el estilo de siempre", not errores5, "; ".join(errores5)[:300])
    ctx.close()
    return fallas


# --- 5. El panel deja pasar los campos (se lee el código: probarlo de verdad pide reiniciarlo)
def lista_blanca():
    src = (RAIZ / "panel.py").read_text(encoding="utf-8")
    i = src.index("async def aspecto_guardar")
    tramo = src[i:i + 6000]
    return [k for k in ("vdOpaco", "vdTinte", "vdBrillo", "vdGrano") if '"' + k + '"' not in tramo]


MUTACIONES = [
    ("que el desenfoque no entienda números", "aspecto.js",
     "(isFinite(parseFloat(v)) ? Math.max(0, Math.min(3, parseFloat(v))) : 1)", "1",
     "⭐ el desenfoque toma el número del deslizador (18 px × 0,5)"),
    ("que la opacidad no llegue a la hoja", "sesiones.html",
     "background-color:var(--vd-hoja,color-mix(", "background-color:var(--vd-hojaNO,color-mix(",
     "y la hoja de la charla también"),
    ("que el brillo no multiplique el borde", "sesiones.html",
     "--vd-filo:rgba(255,255,255,calc(.18 * var(--vd-b,1)));", "--vd-filo:rgba(255,255,255,.18);",
     "⭐ el brillo al doble: el borde pasa de 18 % a 36 %"),
    ("que el grano en 0 deje el grano", "aspecto.js",
     "g ? GRANO((.07 * g / 100).toFixed(3)) : 'none'", "GRANO((.07 * g / 100).toFixed(3))",
     "⭐ con el grano en 0 no hay grano"),
    ("escribir las variables aunque no elijas nada", "aspecto.js",
     "if (opElegida || tinte){", "if (true){",
     "sin variables escritas en el <html> (manda la hoja)"),
    ("guardar mientras arrastrás", "aspecto.js",
     "        val.textContent = d.texto(+barra.value);\n        aplicar();",
     "        val.textContent = d.texto(+barra.value);\n        aplicar(); guardar();",
     "y mientras arrastrás no se manda nada a guardar"),
]

if __name__ == "__main__":
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        if "--mutar" in sys.argv:
            cazadas = 0
            for nombre, archivo, viejo, nuevo, chequeo in MUTACIONES:
                texto = (ESTATICOS / archivo).read_text(encoding="utf-8")
                if texto.count(viejo) != 1:
                    print(f"NO SE PUDO MUTAR  {nombre}: aparece {texto.count(viejo)} veces")
                    continue
                cayo = chequeo in correr(nav, cambios={archivo: (viejo, nuevo)}, callado=True)
                cazadas += cayo
                print(("cazada   " if cayo else "PASÓ DE LARGO  ") + nombre + "  ->  " + chequeo)
            nav.close()
            print(f"\n{'LA PRUEBA SIRVE' if cazadas == len(MUTACIONES) else 'HAY CHEQUEOS DE ADORNO'} — "
                  f"{cazadas} de {len(MUTACIONES)} mutaciones cazadas\n")
            raise SystemExit(0 if cazadas == len(MUTACIONES) else 1)
        fallas = correr(nav, fotos=True)
        nav.close()
    falta = lista_blanca()
    print(("ok   " if not falta else "MAL  ") + "panel.py guarda los cuatro campos nuevos" +
          (f"  -> faltan {falta}" if falta else ""))
    if falta:
        fallas.append("lista blanca")
    print(f"\n{'TODO BIEN' if not fallas else 'HAY PROBLEMAS'} — {len(fallas)} mal\n")
    raise SystemExit(1 if fallas else 0)
