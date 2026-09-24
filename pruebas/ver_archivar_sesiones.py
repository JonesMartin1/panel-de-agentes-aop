"""Archivar conversaciones para que no aparezcan más en la bandeja.

Pedido de Martín (2026-08-17): en la compu con **clic derecho**, en el celular
**deslizando la fila hacia la izquierda**. No borra nada: es una lista de ids que vive
en el servidor (`sesiones_archivadas.json`), así que archivás en un lado y desaparece
en el otro; y se puede devolver.

Esta prueba cubre la parte de la COMPU. El envío al servidor se intercepta, así que no
archiva ninguna conversación de verdad ni deja basura en el disco.

Correr con:  python -m pruebas.ver_archivar_sesiones   (con el panel prendido)
"""
import json
import time
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
fallas = []
saltados = []
pedidos = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def filas(pag):
    return pag.evaluate("() => document.querySelectorAll('#cuerpo .correo[data-sid]').length")


def esta(pag, sid):
    """¿Está esa conversación en la lista que se ve ahora?

    ⚠ Se pregunta por el SID y no por el total de filas: la bandeja crece sola mientras
    corre la prueba (aparece una conversación nueva, o Martín está usando la pantalla),
    así que "quedan N-1 filas" fallaba sin que nada estuviera roto. Lo que se quiere
    afirmar es que ESA fila se fue, y eso no depende de cuántas haya (2026-08-17).
    """
    return pag.evaluate("s => !!document.querySelector(s)",
                        '#cuerpo .correo[data-sid="' + sid + '"]')


def dedos(cdp, tipo, puntos):
    """Un dedo de verdad por CDP. ⚠ En touchEnd hay que mandar los dedos QUE SE LEVANTAN,
    no una lista vacía: con la lista vacía Chrome no dispara el evento de soltar y el
    gesto queda a medio camino (lección de `probar_pizarra_movil.py`)."""
    cdp.send("Input.dispatchTouchEvent", {
        "type": tipo,
        "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(puntos)]})


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # ⭐⭐ El envío se ataja para no archivar nada de verdad, PERO el fingido tiene que
        # ser coherente: lo que acá se contesta "ok" también tiene que verse archivado en
        # `/movil/sesiones`, que es de donde la pantalla saca la verdad (2026-08-27).
        # ⚠ Antes esta prueba solo atajaba el POST y contestaba `{"ok":true}` mientras el
        # servidor no se enteraba de nada. Pasaba igual porque la pantalla se guardaba SU
        # propio Set de archivadas en el navegador y ese Set le ganaba al servidor — o sea
        # que pasaba GRACIAS al defecto que había que arreglar (la charla devuelta desde el
        # celular quedaba archivada para siempre en la compu). Arreglado el defecto, la
        # prueba se cayó: estaba midiendo un mundo imposible, servidor diciendo "no está
        # archivada" y pantalla mostrándola archivada.
        finge = {}          # sid -> True/False, lo que este navegador cree haber cambiado

        def atajar(ruta):
            d = ruta.request.post_data_json
            pedidos.append(d)
            finge[d.get("sid")] = bool(d.get("archivar", True))
            ruta.fulfill(status=200, content_type="application/json", body='{"ok":true}')
        pag.route("**/movil/archivar", atajar)

        # ⚠ La bandeja se INVENTA, no se le pide al panel. Dos motivos, los dos ya
        # aprendidos acá: contra el panel real `/movil/sesiones` puede tardar minutos
        # cuando hay una charla de Codex escribiendo un rollout grande (2026-08-25), y
        # además la lista de verdad se mueve sola mientras corre la prueba. Lo que esta
        # prueba mira es el GESTO sobre la página real (clic derecho, botón Devolver),
        # no de dónde salieron las filas.
        def _ses(clave, cuantas, ya_archivadas=()):
            filas_ = []
            for i in range(1, cuantas + 1):
                sid_ = f"{clave}-{i}"
                s = {"id": sid_, "nombre": f"Charla {clave} {i}",
                     "ts": time.time() - 60 * i, "cuando": time.time() - 60 * i,
                     "ultimo": "claude", "viva": False, "interactiva": False,
                     "ocupada": False, "detalle": "hace un rato", "cerebro": ""}
                # El estado inicial del servidor, y encima lo que la prueba fingió cambiar.
                if finge.get(sid_, sid_ in ya_archivadas):
                    s["archivada"] = True
                filas_.append(s)
            return filas_

        def bandeja(ruta):
            ruta.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"ok": True, "laura": "",
                 "carpetas": {"orden": [], "ocultas": [], "aspecto": {}, "iconosPropios": []},
                 "proyectos": [
                     {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False,
                      "sesiones": _ses("prueba-archivar", 4)},
                     # ⚠ Una SEGUNDA carpeta, con una ya archivada de entrada: sin esto el
                     # chequeo de "las archivadas siguen la carpeta donde estás parado" se
                     # saltea siempre, porque necesita repartir archivadas entre carpetas.
                     {"proyecto": "otro-proyecto", "cwd": str(RAIZ / "pruebas"), "vivo": False,
                      "sesiones": _ses("prueba-otro", 3, ya_archivadas={"prueba-otro-2"})}]}))
        pag.route("**/movil/sesiones*", bandeja)

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("() => { archPend = {}; guardarArchPend(); viendoArchivadas = false;"
                     "         abiertas = []; activa = null; guardar(); pintarTabs();"
                     "         irProyecto(TODAS); }")
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        antes = filas(pag)
        revisar("la bandeja tiene conversaciones", antes > 2, True)
        # ⚠ El servidor puede tener conversaciones archivadas DE VERDAD (las que archivó
        # Martín): viven en `sesiones_archivadas.json` y llegan marcadas con `archivada`,
        # así que borrar la copia del navegador no las hace desaparecer. La prueba no las
        # toca y mide todo contra ese piso — antes daba los números absolutos y empezó a
        # fallar sola el día que hubo una archivada real (2026-08-17).
        base = pag.evaluate("() => { const b = document.getElementById('verArch');"
                            "  return b ? Number((b.textContent.match(/\\((\\d+)\\)/) || [0, 0])[1]) : 0; }")
        print(f"     (el servidor ya tenía {base} archivadas de verdad: se mide sobre eso)")

        # --- Clic derecho: se va de la bandeja ---
        sid = pag.evaluate("() => document.querySelector('#cuerpo .correo[data-sid]').dataset.sid")
        pag.click("#cuerpo .correo[data-sid]", button="right")
        pag.wait_for_timeout(700)
        revisar("con el clic derecho se va de la lista", esta(pag, sid), False)
        revisar("se le avisó al servidor", pedidos and pedidos[-1],
                {"sid": sid, "archivar": True})
        revisar("y aparece el botón de archivadas",
                pag.evaluate("() => document.getElementById('verArch').textContent"),
                f"🗄 archivadas ({base + 1})")
        pag.screenshot(path=str(SALIDA / "sesiones_archivar.png"))

        # --- Verlas, y devolver la que archivé ---
        pag.click("#verArch")
        pag.wait_for_timeout(600)
        revisar("entrando a archivadas, está la que saqué", filas(pag), base + 1)
        revisar("con su propio título",
                pag.evaluate("() => document.querySelector('#cuerpo .cabeza b').textContent"),
                "Archivadas")

        # ⭐ Lo nuevo (2026-08-17): un BOTÓN por fila. El clic derecho seguía andando, pero
        # no lo descubre nadie, así que archivar era un camino de ida desde la pantalla.
        hay = lambda sel: pag.evaluate("s => !!document.querySelector(s)", sel)
        mia = '#cuerpo .correo[data-sid="' + sid + '"]'
        revisar("cada archivada trae su botón de devolver", hay(mia + " .devolver"), True)
        revisar("y dice de qué carpeta salió", hay(mia + " .dedonde"), True)
        revisar("acá no ofrece empezar una conversación",
                pag.evaluate("() => document.querySelectorAll('#cuerpo .tit.nueva').length"), 0)
        pag.screenshot(path=str(SALIDA / "sesiones_archivadas.png"))
        pag.click(mia + " .devolver")
        pag.wait_for_timeout(700)
        revisar("el botón la devuelve a la bandeja", pedidos[-1], {"sid": sid, "archivar": False})
        revisar("y la lista de archivadas vuelve a como estaba", filas(pag), base)

        # El clic derecho tiene que seguir haciendo lo mismo: archivar y devolver.
        pag.click("#verArch")
        pag.wait_for_timeout(600)
        pag.click(mia, button="right")
        pag.wait_for_timeout(700)
        pag.click("#verArch")
        pag.wait_for_timeout(600)
        pag.click(mia, button="right")
        pag.wait_for_timeout(700)
        revisar("clic derecho ahí también la devuelve", pedidos[-1], {"sid": sid, "archivar": False})
        pag.click("#verArch")
        pag.wait_for_timeout(600)
        revisar("volviendo a la bandeja, está de nuevo", esta(pag, sid), True)

        # --- ⭐ Lo nuevo (2026-08-17): las archivadas SIGUEN LA CARPETA ---
        # Adentro de un proyecto se ven solo las de ese proyecto; "Todas" las junta a
        # todas. ⚠ Se mide contra el reparto REAL del servidor, nunca contra números
        # escritos a mano: acá las archivadas son las de Martín y cambian solas.
        # ⚠ `datos` se nombra pelado, sin `window.`: la página lo declara con `let` y eso
        # no cuelga del window (misma piedra que `typeof estado` en la pizarra).
        reparto = pag.evaluate("""() => {
          const c = {};
          for (const x of datos.proyectos)
            for (const s of x.sesiones)
              if (esArchivada(s)) c[x.proyecto] = (c[x.proyecto] || 0) + 1;
          return c;
        }""")
        elegido = max(reparto, key=reparto.get) if reparto else None
        if not elegido:
            saltados.append("archivadas por carpeta (el servidor no tiene ninguna archivada)")
        else:
            cuantas_ahi = reparto[elegido]
            total_arch = sum(reparto.values())
            pag.evaluate("p => irProyecto(p)", elegido)
            pag.wait_for_timeout(800)
            revisar("adentro de la carpeta, el botón cuenta solo las de ahí",
                    pag.evaluate("() => document.getElementById('verArch').textContent"),
                    f"🗄 archivadas ({cuantas_ahi})")
            pag.click("#verArch")
            pag.wait_for_timeout(600)
            revisar("y la lista muestra solo esas", filas(pag), cuantas_ahi)
            revisar("el título dice de qué carpeta son",
                    pag.evaluate("() => document.querySelector('#cuerpo .cabeza b').textContent"),
                    "Archivadas de " + elegido)
            revisar("sin la chapa del proyecto, que acá sobra",
                    pag.evaluate("() => document.querySelectorAll('#cuerpo .dedonde').length"), 0)
            pag.screenshot(path=str(SALIDA / "sesiones_archivadas_carpeta.png"))
            # Y en "Todas" siguen estando todas juntas: es el lugar fijo donde buscarlas.
            pag.evaluate("() => irProyecto(TODAS)")
            pag.wait_for_timeout(800)
            revisar("en Todas siguen estando todas juntas", filas(pag), total_arch)
            revisar("ahí sí dice de qué carpeta salió cada una",
                    pag.evaluate("() => document.querySelectorAll('#cuerpo .dedonde').length"),
                    total_arch)
            pag.click("#verArch")
            pag.wait_for_timeout(600)

        # --- Que el menú del navegador no aparezca encima ---
        revisar("el clic derecho no abre el menú del navegador",
                pag.evaluate("""() => {
                  const el = document.querySelector('#cuerpo .correo[data-sid]');
                  const ev = new MouseEvent('contextmenu', {bubbles:true, cancelable:true});
                  el.dispatchEvent(ev);
                  return ev.defaultPrevented;
                }"""), True)

        pag.evaluate("() => { archPend = {}; guardarArchPend(); }")
        revisar("errores de javascript en la página", errores, [])

        # --- Y el celular: deslizar la fila hacia la izquierda ---
        # Los dedos van por CDP (Input.dispatchTouchEvent), que es lo más parecido a una
        # mano de verdad; Playwright solo, con tap(), no hace arrastres con el dedo.
        tel = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errores_tel = []
        tel.on("pageerror", lambda e: errores_tel.append(str(e)))
        tel.route("**/movil/archivar", atajar)
        tel.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json", body="{}")
            if r.request.method == "POST" else r.continue_())
        tel.goto(BASE + "/movil", wait_until="domcontentloaded")
        tel.wait_for_timeout(2500)
        # ⚠⚠ La app del celular la sirve el panel DESDE LA MEMORIA (`MOVIL_HTML` es una
        # constante de `panel.py`), así que hasta que Martín no lo reinicie esta parte mide
        # la versión vieja. En vez de reventar con un ReferenceError críptico, se dice en
        # criollo qué falta hacer. La compu no tiene este problema: `sesiones.html` se
        # sirve del disco y la prueba ve el código recién escrito.
        if not tel.evaluate("() => typeof guardarArchPend === 'function'"):
            saltados.append("TODO EL CELULAR: el panel todavía sirve el MOVIL_HTML viejo "
                            "(reiniciá el panel y volvé a correr esto)")
            nav.close()
            for s in saltados:
                print(f"SALTADO  {s}")
            print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
            raise SystemExit(1 if fallas else 0)
        tel.evaluate("() => { archPend = {}; guardarArchPend(); ir('nueva'); }")
        # ⚠ Se espera AL DATO, no al reloj. `/movil/sesiones` tarda entre medio segundo y
        # varios, según lo ocupado que esté el panel (con una sesión contestando se midieron
        # más de 2 s), así que con la espera fija la prueba fallaba sola diciendo que el
        # celular no lista nada, y después reventaba con un null (2026-08-17).
        tel.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        cuantas = tel.evaluate("() => document.querySelectorAll('#cuerpo .correo[data-sid]').length")
        revisar("el celular lista conversaciones", cuantas > 2, True)

        # ⚠ La caja y el sid se leen EN EL MISMO evaluate, de una. La lista se repinta cada
        # 3 s y se reordena sola (la conversación que está escribiendo salta arriba), así
        # que leyéndolos por separado el sid ya era de otra fila para cuando llegaba el
        # dedo: el gesto archivaba bien, pero se lo comparaba contra el sid equivocado y la
        # prueba fallaba sola cada tantas corridas (visto el 2026-08-17).
        fila0 = tel.evaluate("""() => {
          const el = document.querySelector('#cuerpo .correo[data-sid]');
          const r = el.getBoundingClientRect();
          return {sid: el.dataset.sid, x: r.x, y: r.y, w: r.width, h: r.height};
        }""")
        sid_tel = fila0["sid"]
        cdp = tel.context.new_cdp_session(tel)
        y = fila0["y"] + fila0["h"] / 2
        x0 = fila0["x"] + fila0["w"] - 30
        dedos(cdp, "touchStart", [(x0, y)])
        for paso in range(1, 7):
            dedos(cdp, "touchMove", [(x0 - paso * 30, y)])
            tel.wait_for_timeout(30)
        dedos(cdp, "touchEnd", [(x0 - 180, y)])
        tel.wait_for_timeout(1200)
        revisar("deslizando a la izquierda, la fila se archiva",
                pedidos[-1], {"sid": sid_tel, "archivar": True})
        # ⚠ Otra vez esperar AL DATO y no al reloj: la fila se va recién cuando vuelve
        # `/movil/sesiones`, que tarda entre medio segundo y varios. Con la espera fija
        # de 1,2 s fallaba sola diciendo que no había desaparecido, cuando un segundo
        # después ya no estaba (2026-08-17).
        try:
            tel.wait_for_function(
                "s => !document.querySelector('#cuerpo .correo[data-sid=\"' + s + '\"]')",
                arg=sid_tel, timeout=15000)
        except Exception:
            pass
        revisar("y desaparece de la lista", esta(tel, sid_tel), False)
        tel.screenshot(path=str(SALIDA / "movil_archivar.png"))

        # Un deslizamiento VERTICAL no tiene que archivar nada: eso es scrollear.
        caja2 = tel.locator("#cuerpo .correo[data-sid]").first.bounding_box()
        antes_pedidos = len(pedidos)
        x1, y1 = caja2["x"] + caja2["width"] - 40, caja2["y"] + caja2["height"] / 2
        dedos(cdp, "touchStart", [(x1, y1)])
        for paso in range(1, 6):
            dedos(cdp, "touchMove", [(x1 - 6, y1 - paso * 35)])
            tel.wait_for_timeout(30)
        dedos(cdp, "touchEnd", [(x1 - 6, y1 - 175)])
        tel.wait_for_timeout(800)
        revisar("scrollear con el dedo NO archiva", len(pedidos), antes_pedidos)

        # ⭐ Ver las archivadas y devolverlas DESDE EL CELULAR (lo nuevo del 2026-08-17).
        # Esto vive en panel.py, o sea que no existe hasta que se reinicie el panel: si
        # todavía no está, se avisa y NO se da por probado. Nunca marcar verde lo que no corrió.
        if not tel.evaluate("() => !!document.querySelector('.barra-proy .op-arch')"):
            saltados.append("celular: ver las archivadas y devolverlas "
                            "(el panel todavía sirve el MOVIL_HTML viejo — reinicialo y repetí)")
        else:
            tel.click(".barra-proy .op-arch")
            # ⚠ Esperar AL DATO y no al reloj, otra vez: la vista se redibuja recién cuando
            # vuelve `/movil/sesiones`, que con el panel ocupado tarda varios segundos. Con
            # los 900 ms fijos la prueba fallaba sola diciendo que el celular no había
            # entrado a las archivadas, cuando un segundo después ya estaba adentro
            # (visto el 2026-08-17, y es la misma piedra que este archivo ya tiene anotada
            # dos veces más arriba).
            mia_tel = '#cuerpo .correo[data-sid="' + sid_tel + '"]'
            try:
                tel.wait_for_function(
                    "s => (document.querySelector('.barra-proy .quien b') || {}).textContent"
                    " === 'Archivadas' && !!document.querySelector(s)",
                    arg=mia_tel + " .devolver", timeout=15000)
            except Exception:
                pass
            revisar("el celular entra a las archivadas",
                    tel.evaluate("() => document.querySelector('.barra-proy .quien b').textContent"),
                    "Archivadas")
            revisar("la que archivé con el dedo está ahí, con su botón",
                    tel.evaluate("s => !!document.querySelector(s)", mia_tel + " .devolver"), True)
            antes_dev = len(pedidos)
            tel.click(mia_tel + " .devolver")
            tel.wait_for_timeout(900)
            revisar("el botón la devuelve a la bandeja", pedidos[-1],
                    {"sid": sid_tel, "archivar": False})
            revisar("y salió un solo pedido", len(pedidos), antes_dev + 1)
            tel.screenshot(path=str(SALIDA / "movil_archivadas.png"))

        tel.evaluate("() => { archPend = {}; guardarArchPend(); }")
        revisar("errores de javascript en el celular", errores_tel, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_archivar.png'}")
    for s in saltados:
        print(f"SALTADO  {s}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
