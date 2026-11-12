"""Con muchas carpetas, ¿el riel avisa que hay más abajo y deja volver a las escondidas?

Pedido de Martín (2026-11-12): *"a medida que voy añadiendo proyectos, se van saliendo
otros y eso está reee mal"*. No se iban: el riel de "Vidrio con bandeja" se desplaza con la
barra escondida, y las carpetas que no entraban quedaban abajo sin ninguna señal. Además la
fila "Escondidas" (el único camino para devolver una carpeta sacada) estaba oculta en ese
estilo.

Con 30 carpetas de mentira (3 escondidas), en la tira de emojis:
  1. aparece la pastilla "▾ N" con N > 0 y el borde de abajo se desvanece;
  2. tocarla baja hasta el final: "Agregar una carpeta" queda a la vista y la pastilla se va;
  3. "Escondidas" se ve, y tocarla abre el riel con nombres y las 3 para devolver.
`--mutar` rompe cada pieza a propósito y exige que la prueba la cace.
Usa el armado de `ver_vbandeja` (página del disco, datos de mentira; panel prendido en 8750).
"""
import copy
import sys

from playwright.sync_api import sync_playwright

from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def muchas():
    d = copy.deepcopy(vb.SESIONES)
    for i in range(1, 29):
        d["proyectos"].append({"proyecto": "p%02d" % i, "cwd": "D:\\pruebas\\p%02d" % i, "vivo": False,
                               "manual": True, "sesiones": [vb.ses("p%02d-1" % i, "charla %d" % i, 5000 + i)]})
    d["carpetas"] = {"orden": [], "ocultas": ["p26", "p27", "p28"]}
    return d


def correr(nav, cambios=None):
    fallas = []
    original = vb.SESIONES
    vb.SESIONES = muchas()
    try:
        ctx, pag, err = vb.montar(nav, "vbandeja", cambios, abrir=False)
        pag.wait_for_timeout(500)
        ver = lambda s: pag.evaluate("s => { const e = document.querySelector(s);"
                                     " return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; }", s)
        texto = pag.evaluate("() => (document.querySelector('#masAbajo button') || {}).textContent || ''")
        abajo = pag.evaluate("() => document.getElementById('paneProy').classList.contains('hay-abajo')")
        if not (ver("#masAbajo") and texto.startswith("▾ ") and int(texto.split()[1]) > 0 and abajo):
            fallas.append("con 27 carpetas a la vista no avisa que hay más abajo (pastilla %r, degradé %s)" % (texto, abajo))
        pag.screenshot(path=str(vb.SALIDA / "riel_muchas.png"), clip={"x": 0, "y": 0, "width": 120, "height": 850})
        try:
            pag.click("#masAbajo button", timeout=3000)
        except Exception:
            fallas.append("no se pudo tocar la pastilla de 'más abajo'")
        pag.wait_for_timeout(900)
        sumar_visible = pag.evaluate("""() => { const p = document.getElementById('paneProy').getBoundingClientRect();
            const s = document.getElementById('sumar').getBoundingClientRect();
            return s.height > 0 && s.top >= p.top - 1 && s.bottom <= p.bottom + 1; }""")
        if not sumar_visible or ver("#masAbajo"):
            fallas.append("tocar la pastilla no bajó hasta 'Agregar una carpeta' (o la pastilla no se fue)")
        if not ver("#verOcultas"):
            fallas.append("'Escondidas' no se ve: no hay cómo devolver una carpeta sacada")
        else:
            try:
                pag.click("#verOcultas", timeout=3000)
            except Exception:
                fallas.append("no se pudo tocar 'Escondidas'")
            pag.wait_for_timeout(400)
            n = pag.evaluate("() => [...document.querySelectorAll('.carpeta.escondida')].filter(e => e.offsetParent).length")
            ancho = pag.evaluate("() => document.body.classList.contains('riel-ancho')")
            if not (ancho and n == 3):
                fallas.append("tocar 'Escondidas' no abrió el riel con las 3 para devolver (riel ancho %s, %s a la vista)" % (ancho, n))
            # Se ven como una carpeta más, apagada: sin cajita con borde, con la letra de las
            # demás y el ↩ solo al pasar ("esto se ve horrible", captura del 2026-11-12).
            m = pag.evaluate("""() => { const e = document.querySelector('.carpeta.escondida');
                const n = document.querySelector('#carpetas .carpeta[data-proy] .nom');
                if (!e || !n) return null;
                const s = getComputedStyle(e), sn = getComputedStyle(e.querySelector('.nom'));
                return {borde: parseFloat(s.borderTopWidth), fondo: s.backgroundColor,
                        letra: parseFloat(sn.fontSize), letraCarpeta: parseFloat(getComputedStyle(n).fontSize),
                        vol: getComputedStyle(e.querySelector('.vol')).opacity,
                        ico: !!e.querySelector('.icoEsc')}; }""")
            if not m or m["borde"] > 0 or m["fondo"] not in ("rgba(0, 0, 0, 0)", "transparent") \
                    or abs(m["letra"] - m["letraCarpeta"]) > 1.5 or m["vol"] != "0" or not m["ico"]:
                fallas.append("las escondidas no se ven como una carpeta más (caja, letra o ↩ siempre a la vista): %s" % m)
            pag.evaluate("() => { const p = document.getElementById('paneProy'); p.scrollTop = p.scrollHeight; }")
            pag.wait_for_timeout(300)
            pag.screenshot(path=str(vb.SALIDA / "riel_escondidas.png"), clip={"x": 0, "y": 450, "width": 300, "height": 400})
        if err:
            fallas.append("errores en la página: " + "; ".join(err))
        ctx.close()
    finally:
        vb.SESIONES = original
    return fallas


MUTACIONES = {
    "no avisa que hay más abajo": {
        "sesiones.html": [("caja.classList.toggle('hay', resto > 4 && ocultas > 0);", "")]},
    "la pastilla no baja": {
        "sesiones.html": [("b.onclick = () => p.scrollTo(", "b.onclick = () => (")]},
    "'Escondidas' vuelve a estar oculta": {
        "sesiones.html": [(" html.carta.vbandeja body:not(.riel-ancho) .carpeta.escondida{display:none !important}",
                           " html.carta.vbandeja #verOcultas,html.carta.vbandeja .carpeta.escondida{display:none !important}")]},
    "la fila vuelve a llamarse como el botón (cajitas)": {
        "sesiones.html": [("'<div class=\"carpeta escondida\" data-volver=", "'<div class=\"carpeta escondida devolver\" data-volver=")]},
}


def main():
    mutar = "--mutar" in sys.argv
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav)
        for f in fallas:
            print("FALLA:", f)
        print("Riel con muchas carpetas:", "todo bien" if not fallas else "%d fallas" % len(fallas))
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
