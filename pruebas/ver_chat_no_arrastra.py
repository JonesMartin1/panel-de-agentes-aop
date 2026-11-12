"""¿Subir en una charla que se está escribiendo te arrastra de vuelta abajo?

Pedido de Martín (2026-11-12): *"cuando subo en una conversación me arrastra para abajo"*.
La charla te sigue hacia abajo mientras crece; antes decidía si seguirte MIDIENDO la
distancia al final (< 90 px) en cada repintado, y la rueda de Chrome sube animada: si
subías poco, o si llegaba algo en medio de la animación, te devolvía al final. Ahora sigue
la intención (`sigueAbajo` en sesiones.html, `window.chatSigue` en envivo.js).

Acá la charla de mentira suma un mensaje en cada pedido (como una que está escribiendo), y:
  1. estando abajo, te sigue;
  2. subís un poquito con la rueda (menos de 90 px) → el repintado NO te baja;
  3. subís mucho → tampoco;
  4. bajás vos hasta el final → te vuelve a seguir.
`--mutar` rompe la regla y exige que la prueba lo cace.

Sirve `sesiones.html` y `aspecto.js` del disco (mismo armado que `ver_vbandeja`); necesita
el panel prendido en 8750 para el resto de los archivos.
"""
import json
import sys

from playwright.sync_api import sync_playwright

from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LARGO = "Una respuesta larga de prueba para que la charla tenga alto de sobra. " * 6


def correr(nav, cambios=None):
    fallas = []
    cuenta = {"n": 40}

    def chat(r):
        cuenta["n"] += 1
        mensajes = []
        for i in range(cuenta["n"]):
            mensajes.append({"de": "vos" if i % 2 == 0 else "claude",
                             "texto": ("pregunta %d" % i) if i % 2 == 0 else LARGO + str(i), "imgs": []})
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps(dict(vb.CHAT, mensajes=mensajes)))

    ctx, pag, err = vb.montar(nav, "vidrio", cambios, abrir=False)
    pag.route("**/movil/chat*", chat)
    pag.evaluate("() => { abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa',"
                 " nombre: 'arreglar el login', cerebro: ''}]; irTab('alfa-1'); }")
    pag.wait_for_timeout(1500)
    resto = "() => { const c = document.getElementById('cuerpo'); return Math.round(c.scrollHeight - c.scrollTop - c.clientHeight); }"
    alto = pag.evaluate("() => { const c = document.getElementById('cuerpo'); return c.scrollHeight - c.clientHeight; }")
    if alto < 600:
        fallas.append("la charla de prueba no quedó con scroll (%s px)" % alto)
    # 1. Abajo: el repintado con un mensaje nuevo te sigue.
    pag.wait_for_timeout(3600)
    if pag.evaluate(resto) > 5:
        fallas.append("Estando abajo, un mensaje nuevo no te siguió (quedaste a %s px)" % pag.evaluate(resto))
    caja = pag.evaluate("() => { const r = document.getElementById('cuerpo').getBoundingClientRect();"
                        " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }")
    pag.mouse.move(caja["x"], caja["y"])
    # 2. Subir POQUITO (el caso que antes te devolvía: quedabas a menos de 90 px).
    pag.mouse.wheel(0, -60)
    pag.wait_for_timeout(400)
    antes = pag.evaluate(resto)
    pag.wait_for_timeout(3600)            # pasa por lo menos un repintado con mensaje nuevo
    despues = pag.evaluate(resto)
    if not (antes > 20 and despues >= antes - 5):
        fallas.append("Subiste un poquito y el repintado te bajó (a %s px del final, después %s)" % (antes, despues))
    # 3. Subir mucho: tampoco te baja.
    pag.mouse.wheel(0, -900)
    pag.wait_for_timeout(500)
    antes = pag.evaluate(resto)
    pag.wait_for_timeout(3600)
    despues = pag.evaluate(resto)
    if not (antes > 400 and despues >= antes - 5):
        fallas.append("Subiste a leer y el repintado te bajó (de %s px a %s px del final)" % (antes, despues))
    # 4. Bajás vos hasta el final: te vuelve a seguir.
    pag.mouse.wheel(0, 50000)
    pag.wait_for_timeout(600)
    pag.wait_for_timeout(3600)
    if pag.evaluate(resto) > 5:
        fallas.append("Volviste al final y ya no te sigue (quedaste a %s px)" % pag.evaluate(resto))
    if err:
        fallas.append("errores en la página: " + "; ".join(err))
    ctx.close()
    return fallas


MUTACIONES = {
    "el repintado mide la distancia como antes": {
        "sesiones.html": [("const abajo = entrando || sigueAbajo;",
                           "const abajo = entrando || c.scrollHeight - c.scrollTop - c.clientHeight < 90;")]},
    "la rueda no suelta el seguimiento": {
        "sesiones.html": [("c.addEventListener('wheel', e => { if (e.deltaY < 0) soltar(); }, {passive: true});", ""),
                          ("else if (c.scrollTop < ultimoTop - 2) sigueAbajo = false;", "")]},
    "llegar al final no vuelve a seguir": {
        "sesiones.html": [("if (resto < 40) sigueAbajo = true;", "if (false) sigueAbajo = true;")]},
}


def main():
    mutar = "--mutar" in sys.argv
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav)
        for f in fallas:
            print("FALLA:", f)
        print("La charla no te arrastra:", "todo bien" if not fallas else "%d fallas" % len(fallas))
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
