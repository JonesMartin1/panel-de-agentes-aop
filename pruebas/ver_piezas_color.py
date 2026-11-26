"""¿Cada pieza de vidrio de /sesiones toma su propio color?

Pedido de Martín (2026-11-16, con captura): *"me gustaría poder cambiarle el color a cada
tarjeta en este panel"*. Hasta ese día el vidrio tenía UN color para todas las piezas.
Ahora el 🎨 (Vidrio → Color de cada pieza) guarda `aspecto.piezas` y `aspecto.js` define
`--pz-<pieza>`, que cada pieza usa antes del vidrio común.

  1. Sin elegir nada, todas las piezas tienen el MISMO vidrio (nada se mueve).
  2. Con un color por pieza (magenta, verde, azul, amarillo: colores que no se parecen a
     nada de la pantalla), cada pieza se tiñe del suyo y no de otro.
  3. En el 🎨 están las cinco filas, y mover una rueda pinta la pieza y la guarda en
     `piezas` (lo que viaja al panel).
`--mutar` rompe cada pieza a propósito y exige que la prueba la cace.
Usa el armado de `ver_vbandeja` (página del disco, datos de mentira; panel prendido en 8750).
"""
import json
import re
import sys

from playwright.sync_api import sync_playwright

from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ⚠ La charla va en ROJO y no en azul: el fondo de la prueba es azulado, y con azul la hoja
# "pasaba" aunque no usara su color (lo cazó `--mutar`).
COLORES = {"riel": "#ff00ff", "lista": "#00ff00", "hoja": "#ff0000", "caja": "#ffff00"}

FONDOS = """() => {
  const bg = (e, p) => e ? getComputedStyle(e, p || null).backgroundColor : '';
  return {riel: bg(document.querySelector('aside')), lista: bg(document.getElementById('colCharlas')),
          hoja: bg(document.body, '::before'), caja: bg(document.querySelector('.caja'))};
}"""


def rgb(txt):
    """'rgba(…)' o 'color(srgb …)' → (r, g, b) entre 0 y 1."""
    nums = [float(x) for x in re.findall(r"-?[\d.]+(?:e-?\d+)?", txt or "")]
    if txt.startswith("color(") and len(nums) >= 3:
        return tuple(nums[:3])
    if len(nums) >= 3:
        return tuple(n / 255 for n in nums[:3])
    return (0, 0, 0)


def domina(txt, canal):
    """¿El canal pedido manda sobre los otros? (magenta = r y b, amarillo = r y g…)"""
    r, g, b = rgb(txt)
    c = {"r": r, "g": g, "b": b}
    if canal == "#ff00ff":
        return r > g + .04 and b > g + .04
    if canal == "#00ff00":
        return g > r + .04 and g > b + .04
    if canal == "#ff0000":
        return r > g + .04 and r > b + .02
    if canal == "#ffff00":
        return r > b + .04 and g > b + .04
    return False


def montar(nav, piezas, cambios=None):
    original = vb.aspecto
    vb.aspecto = lambda e: dict(original(e), piezas=piezas)
    try:
        return vb.montar(nav, "vbandeja", cambios, abrir=True)
    finally:
        vb.aspecto = original


def correr(nav, cambios=None):
    fallas = []
    # 1. Sin elegir nada: las piezas de vidrio comunes iguales entre sí.
    ctx, pag, err = montar(nav, {}, cambios)
    f = pag.evaluate(FONDOS)
    if not (f["riel"] == f["lista"] == f["caja"] and f["riel"]):
        fallas.append("sin elegir nada, las piezas no tienen el mismo vidrio: %s" % f)
    base = f
    ctx.close()
    # 2. Un color por pieza: cada una el suyo.
    ctx, pag, err = montar(nav, COLORES, cambios)
    pag.wait_for_timeout(300)
    f = pag.evaluate(FONDOS)
    for k, c in COLORES.items():
        if not domina(f[k], c):
            fallas.append("la pieza %r no tomó su color %s (quedó %s)" % (k, c, f[k]))
    pag.screenshot(path=str(vb.SALIDA / "piezas_color.png"))
    # 3. El 🎨: cinco filas, y la rueda pinta y guarda.
    enviados = []
    pag.on("request", lambda r: enviados.append(r.post_data or "")
           if r.method == "POST" and r.url.endswith("/aspecto") else None)
    try:
        pag.click("#aspectoBtn", timeout=3000)
        pag.wait_for_timeout(300)
        pag.evaluate("() => document.querySelectorAll('#aspectoPanel details').forEach(d => { d.open = true; })")
    except Exception:
        fallas.append("no se pudo abrir el 🎨")
    filas = pag.evaluate("() => [...document.querySelectorAll('#aspectoPanel .parte[data-pz]')].map(e => e.dataset.pz)")
    if filas != ["riel", "lista", "barra", "hoja", "caja"]:
        fallas.append("el 🎨 no tiene las cinco filas de 'Color de cada pieza': %s" % filas)
    pag.evaluate("""() => { const r = document.querySelector('#aspectoPanel .rueda[data-pz-rueda="lista"]');
        if (!r) return; r.value = '#ff8800'; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); }""")
    pag.wait_for_timeout(500)
    lista = pag.evaluate(FONDOS)["lista"]
    r_, g_, b_ = rgb(lista)
    if not (r_ > g_ > b_):
        fallas.append("mover la rueda de la lista no la pintó de naranja (quedó %s)" % lista)
    if not any('"piezas"' in d and "#ff8800" in d for d in enviados):
        fallas.append("el color elegido no viajó al panel adentro de 'piezas'")
    if err:
        fallas.append("errores en la página: " + "; ".join(err))
    ctx.close()
    return fallas


MUTACIONES = {
    "la lista no usa su color": {
        "sesiones.html": [("body.con-col #colCharlas{background-color:var(--pz-lista,var(--vd-vidrio))}",
                           "body.con-col #colCharlas{background-color:var(--vd-vidrio)}")]},
    "la charla no usa su color": {
        "sesiones.html": [("body::before{background-color:var(--pz-hoja,", "body::before{background-color:var(--pz-nada,")]},
    "aspecto.js no aplica las piezas": {
        "aspecto.js": [("    piezasVidrio(r);\n", "\n")]},
    "la rueda no guarda": {
        "aspecto.js": [("else aspecto.piezas = Object.assign({}, aspecto.piezas, {[k]: v});", "else {}")]},
}


def main():
    mutar = "--mutar" in sys.argv
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav)
        for f in fallas:
            print("FALLA:", f)
        print("Color de cada pieza:", "todo bien" if not fallas else "%d fallas" % len(fallas))
        malas = list(fallas)
        if mutar:
            for nombre, cambios in MUTACIONES.items():
                cazada = bool(correr(nav, cambios))
                print(("cazada   " if cazada else "NO CAZADA") + " · " + nombre)
                if not cazada:
                    malas.append(nombre)
        nav.close()
    sys.exit(1 if malas else 0)


if __name__ == "__main__":
    main()
