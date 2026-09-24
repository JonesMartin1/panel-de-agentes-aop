"""Pintar y subrayar texto adentro de una conversación (el marcador de `/sesiones`).

Pedido de Martín (2026-08-17): *"poder pintar o subrayar el texto de las conversaciones
seleccionándolo, apretando clic derecho, y que aparezca un botón que diga subrayar o algo
así, que ofrezca varias opciones de color, varias formas de subrayarlo, la opacidad"*.

⭐ El servidor de las marcas está INVENTADO acá (`page.route`), igual que en
`ver_estudio.py`: las rutas `/marcas*` y `/estaticos/marcas.js` viven en `panel.py` y no
existen hasta que se reinicie el panel. Así esto corre con el panel viejo prendido, sin
tocar ni una marca de verdad y sin reiniciar nada.

⭐⭐ Lo que de verdad hay que probar acá es que la marca SOBREVIVE AL REPINTADO: el hilo se
rearma entero cada 3 segundos, así que una marca pegada al DOM duraría un suspiro.

Correr con:  python -m pruebas.ver_marcas_texto   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ, ESTATICOS

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
SID = "prueba-marcas-0000"
fallas = []

# La conversación es de mentira y con un texto conocido: así se sabe exactamente qué
# letras van del 0 al 10 y se puede comprobar el pedazo pintado.
FRASE = "Los pasos, en orden para configurar el dominio."
# ⚠ Un mensaje LARGO a propósito: el servidor guarda solo las primeras 300 letras de lo
# marcado, así que una marca más larga que eso es el caso que hay que probar (ver abajo).
LARGO = ("Explicación larga de las que uno subraya enteras. " * 12).strip()
CHARLA = {"mensajes": [
    {"de": "vos", "texto": "¿como sigo?"},
    {"de": "claude", "texto": FRASE},
    {"de": "claude", "texto": LARGO},
]}


# Buscar el punto del DOM que cae en la letra N de un mensaje. Es la vuelta que hace el
# propio marcador para anclar una marca, y acá hace falta por lo mismo: una vez pintado,
# el texto del mensaje está partido en varios nodos.
PUNTO = """
const puntoEn = (m, pos) => {
  const it = document.createTreeWalker(m, NodeFilter.SHOW_TEXT);
  let n = 0, t;
  while ((t = it.nextNode())){
    if (n + t.nodeValue.length >= pos) return {node: t, off: pos - n};
    n += t.nodeValue.length;
  }
  return null;
};
"""


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    guardadas = {SID: []}          # el "servidor" de marcas, en memoria
    pedidos = []

    def ruta_marcas(ruta):
        req = ruta.request
        if req.method == "GET":
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"marcas": {SID: guardadas[SID]}}))
            return
        d = req.post_data_json or {}
        pedidos.append((req.url.split("/marcas")[1], d))
        if req.url.endswith("/poner"):
            guardadas[SID] = [m for m in guardadas[SID]
                              if not (m["msg"] == d["msg"] and m["ini"] == d["ini"]
                                      and m["fin"] == d["fin"])]
            guardadas[SID].append({k: d[k] for k in
                                   ("id", "msg", "ini", "fin", "color", "forma", "op", "texto")})
        elif req.url.endswith("/quitar"):
            guardadas[SID] = [] if d.get("todas") else \
                [m for m in guardadas[SID] if m["id"] != d.get("id")]
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "marcas": guardadas[SID]}))

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # ⚠⚠ EL ORDEN IMPORTA Y AL REVÉS DE LO QUE UNO ESCRIBE: Playwright prueba las
        # rutas de la ÚLTIMA a la primera. `**/marcas*` también le pega a
        # `/estaticos/marcas.js`, así que puesto último se comía el script y la página
        # cargaba sin marcador — todo en rojo por la prueba, no por el producto. La
        # general va primero y la específica después, que es la que tiene que ganar.
        # ⚠ Y hacen falta DOS patrones: en los comodines de Playwright, `*` no cruza la
        # barra, así que `**/marcas*` agarra `/marcas?sid=…` pero NO `/marcas/poner` —
        # que se iba al panel de verdad y volvía 404 (la ruta todavía no existe allá).
        pag.route("**/marcas*", ruta_marcas)
        pag.route("**/marcas/*", ruta_marcas)
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        pag.route("**/estaticos/marcas.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript",
            body=(ESTATICOS / "marcas.js").read_text(encoding="utf-8")))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        revisar("el marcador cargó", pag.evaluate("() => !!window.Marcas"), True)

        # Una pestaña de mentira parada en un proyecto de verdad.
        pag.evaluate("""sid => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'De prueba'}];
          grupoAbierto = ''; activa = null; guardar();
          irTab(sid);
        }""", SID)
        pag.wait_for_selector("#hilo [data-msg]", timeout=15000)
        revisar("los mensajes llevan su número de ancla",
                pag.evaluate("() => [...document.querySelectorAll('#hilo [data-msg]')]"
                             ".map(x => x.dataset.msg)"), ["0", "1", "2"])

        # --- ⭐⭐ Una marca LARGA (de las que uno hace de verdad) se tiene que ver ---
        # El servidor guarda solo las primeras 300 letras de lo marcado. Pidiendo que
        # coincidieran letra por letra, TODA marca más larga que eso se daba por rota y no
        # se dibujaba: se guardaba bien y no aparecía nunca. Es el "no están andando los
        # subrayados" del 2026-08-18, y por eso este chequeo va primero.
        guardadas[SID] = [{"id": "larga", "msg": 2, "ini": 0, "fin": 420,
                           "color": "amarillo", "forma": "marcador", "op": .4,
                           "texto": LARGO[:300]}]
        pag.evaluate("sid => Marcas.cargar(sid).then(() => { firma=''; pintarSesion(); })", SID)
        pag.wait_for_timeout(1200)
        revisar("una marca de más de 300 letras se dibuja igual",
                pag.evaluate("""() => {
                  const e = [...document.querySelectorAll('#hilo [data-msg=\\"2\\"] .mkc')];
                  return e.reduce((n, x) => n + x.textContent.length, 0);
                }"""), 420)
        pag.screenshot(path=str(SALIDA / "marcas_larga.png"))
        guardadas[SID] = []
        pag.evaluate("sid => Marcas.cargar(sid).then(() => { firma=''; pintarSesion(); })", SID)
        pag.wait_for_timeout(1000)

        # --- Seleccionar "Los pasos" del segundo mensaje y abrir el menú ---
        # ⚠ La selección se arma a mano con un Range: arrastrar el mouse sobre un texto
        # dibujado con markdown es frágil y lo que se quiere probar es el menú, no el
        # gesto del navegador.
        abrio = pag.evaluate("""() => {
          const m = document.querySelector('#hilo [data-msg="1"]');
          const t = m.firstChild.nodeType === 3 ? m.firstChild
                  : document.createTreeWalker(m, NodeFilter.SHOW_TEXT).nextNode();
          const r = document.createRange();
          r.setStart(t, 0); r.setEnd(t, 10);          // "Los pasos"
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
          const caja = m.getBoundingClientRect();
          const ev = new MouseEvent('contextmenu', {bubbles:true, cancelable:true,
                                                    clientX: caja.left + 30,
                                                    clientY: caja.top + 10});
          t.parentElement.dispatchEvent(ev);
          return !!document.getElementById('menuMarcas');
        }""")
        revisar("con texto seleccionado, el clic derecho abre el menú", abrio, True)
        revisar("ofrece los seis colores de siempre",
                pag.evaluate("() => document.querySelectorAll('#menuMarcas .col[data-color]').length"), 6)
        revisar("y varias formas de marcar",
                pag.evaluate("() => [...document.querySelectorAll('#menuMarcas .fr')]"
                             ".map(x => x.textContent)"),
                ["Resaltado", "Subrayado", "Marcador", "Recuadro"])
        revisar("con su barrita de opacidad",
                pag.evaluate("() => !!document.querySelector('#menuMarcas .op input')"), True)
        revisar("y el botón de copiar lo seleccionado",
                pag.evaluate("() => !!document.querySelector('#menuMarcas .bt[data-hacer=copiar]')"),
                True)
        revisar("y la rueda para elegir un color cualquiera",
                pag.evaluate("() => !!document.querySelector('#menuMarcas .col.propio input[type=color]')"),
                True)
        pag.screenshot(path=str(SALIDA / "marcas_menu.png"))

        # --- ⭐ Tocar el color YA pinta: no hay botón "Pintar" ---
        # Pedido de Martín (2026-08-18): "no me gusta tener que apretar Pintar para que se
        # pinte". El color es el botón, y el toque siguiente retoca lo mismo en vez de
        # apilar otra marca encima.
        revisar("no hay ningún botón de Pintar",
                pag.evaluate("() => !!document.querySelector('#menuMarcas .bt.pintar')"), False)
        pag.click('#menuMarcas .col[data-color="verde"]')
        pag.wait_for_timeout(900)
        revisar("tocar el color pinta solo", len(guardadas[SID]), 1)
        revisar("el menú se queda para seguir retocando",
                pag.evaluate("() => (document.querySelector('#menuMarcas .tit')||{}).textContent"),
                "Lo que acabás de pintar")
        pag.click('#menuMarcas .fr[data-forma="subrayado"]')
        pag.wait_for_timeout(900)
        revisar("y cambiar la forma retoca esa misma, no agrega otra",
                len(guardadas[SID]), 1)
        revisar("se le avisó al servidor con las letras exactas",
                [(m["msg"], m["ini"], m["fin"], m["color"], m["forma"]) for m in guardadas[SID]],
                [(1, 0, 10, "verde", "subrayado")])
        revisar("y se guardó qué decía, para no pintar al voleo después",
                guardadas[SID][0]["texto"], FRASE[:10])
        revisar("la marca se ve en pantalla",
                pag.evaluate("() => { const e = document.querySelector('#hilo .mkc');"
                             "  return e ? e.textContent : null; }"), FRASE[:10])
        # ⚠ Lleva además `elegida`: recién pintada queda agarrada, con su contorno, que es
        # lo que el menú abierto está por seguir cambiando.
        revisar("con la forma elegida",
                pag.evaluate("() => document.querySelector('#hilo .mkc').className"),
                "mkc f-subrayado elegida")
        pag.screenshot(path=str(SALIDA / "marcas_pintado.png"))

        # --- ⭐⭐ Lo que importa: sobrevive al repintado de cada 3 segundos ---
        pag.evaluate("() => { firma = ''; return pintarSesion(); }")
        pag.wait_for_timeout(1200)
        revisar("la marca sobrevive al repintado",
                pag.evaluate("() => { const e = document.querySelector('#hilo .mkc');"
                             "  return e ? e.textContent : null; }"), FRASE[:10])
        revisar("y no se duplicó", pag.evaluate("() => document.querySelectorAll('#hilo .mkc').length"), 1)

        # --- Una marca cuyo texto ya no coincide NO se pinta ---
        guardadas[SID].append({"id": "vieja", "msg": 1, "ini": 11, "fin": 20,
                               "color": "rosa", "forma": "resaltado", "op": .4,
                               "texto": "otra cosa que ya no está"})
        pag.evaluate("sid => Marcas.cargar(sid).then(() => { firma=''; pintarSesion(); })", SID)
        pag.wait_for_timeout(1200)
        revisar("una marca cuyo texto cambió no se dibuja",
                pag.evaluate("() => document.querySelectorAll('#hilo .mkc').length"), 1)
        guardadas[SID] = [m for m in guardadas[SID] if m["id"] != "vieja"]

        # --- ⭐⭐ El menú tiene que seguir andando la SEGUNDA vez ---
        # Regresión de verdad, la que hizo decir "aprieto el botón y no pasa nada"
        # (2026-08-18): cerrar el menú sacaba el cartel pero dejaba enganchadas sus
        # escuchas del documento, y esa escucha zombi cerraba el menú SIGUIENTE en el
        # mousedown — o sea antes de que llegara el clic. El primer marcado salía bien y
        # de ahí en más ningún botón hacía nada.
        # ⚠ Acá ya NO se puede tomar "el primer nodo de texto y contar desde ahí": pintar
        # partió el texto en pedazos (la marca es un `span` en el medio), así que el
        # primero mide 10 letras. Se busca el punto por POSICIÓN, igual que hace el
        # propio marcador — si no, la prueba revienta con un `setStart` fuera de rango.
        pag.evaluate(PUNTO + """() => {
          const m = document.querySelector('#hilo [data-msg="1"]');
          const a = puntoEn(m, 11), b = puntoEn(m, 20);
          const r = document.createRange();
          r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
          const c = m.getBoundingClientRect();
          a.node.parentElement.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true,
                cancelable:true, clientX: c.left + 60, clientY: c.top + 10}));
        }""")
        pag.click('#menuMarcas .col[data-color="celeste"]')
        pag.wait_for_timeout(900)
        revisar("el menú sigue funcionando la segunda vez", len(guardadas[SID]), 2)
        # Se saca la segunda para seguir con una sola, como estaba.
        pag.evaluate("""() => {
          const e = [...document.querySelectorAll('#hilo .mkc')].pop();
          const c = e.getBoundingClientRect();
          getSelection().removeAllRanges();
          e.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true, cancelable:true,
                          clientX: c.left + 3, clientY: c.top + 3}));
        }""")
        pag.click('#menuMarcas .bt.sacar')
        pag.wait_for_timeout(900)
        revisar("y la tercera también", len(guardadas[SID]), 1)

        # --- Una selección que cruza VARIOS mensajes deja una marca en cada uno ---
        pag.evaluate(PUNTO + """() => {
          const a = document.querySelector('#hilo [data-msg="0"]');
          const b = document.querySelector('#hilo [data-msg="1"]');
          const p1 = puntoEn(a, 2), p2 = puntoEn(b, 25);
          const r = document.createRange();
          r.setStart(p1.node, p1.off); r.setEnd(p2.node, p2.off);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
          const c = b.getBoundingClientRect();
          p2.node.parentElement.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true,
                cancelable:true, clientX: c.left + 20, clientY: c.top + 8}));
        }""")
        pag.click('#menuMarcas .col[data-color="naranja"]')
        pag.wait_for_timeout(1200)
        revisar("una selección que cruza dos mensajes deja marca en los dos",
                sorted({m["msg"] for m in guardadas[SID]}), [0, 1])
        pag.screenshot(path=str(SALIDA / "marcas_varios.png"))
        # Se dejan solo la primera para el resto de la prueba.
        guardadas[SID] = guardadas[SID][:1]
        pag.evaluate("sid => Marcas.cargar(sid).then(() => { firma=''; pintarSesion(); })", SID)
        pag.wait_for_timeout(1000)

        # --- Un color elegido a dedo con la rueda del sistema ---
        # ⚠ El selector de color del sistema no se puede abrir desde una prueba: se le
        # pone el valor al input y se dispara el `change`, que es exactamente lo que hace
        # el navegador cuando soltás el color.
        pag.evaluate(PUNTO + """() => {
          const m = document.querySelector('#hilo [data-msg="1"]');
          const a = puntoEn(m, 26), b = puntoEn(m, 36);
          const r = document.createRange();
          r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
          const c = m.getBoundingClientRect();
          a.node.parentElement.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true,
                cancelable:true, clientX: c.left + 90, clientY: c.top + 10}));
          const p = document.querySelector('#menuMarcas .col.propio input');
          p.value = '#12ab56';
          p.dispatchEvent(new Event('change', {bubbles:true}));
        }""")
        # ⭐ Soltar el color de la rueda ya pinta, igual que tocar uno de los seis.
        pag.wait_for_timeout(1200)
        revisar("la rueda queda marcada como el color elegido",
                pag.evaluate("() => !!document.querySelector('#menuMarcas .col.propio.sel')"), True)
        revisar("se pinta con el color elegido a dedo",
                [m["color"] for m in guardadas[SID] if m["ini"] == 26], ["#12ab56"])
        revisar("y en pantalla se dibuja con ese color",
                pag.evaluate("""() => {
                  const e = [...document.querySelectorAll('#hilo .mkc')]
                    .find(x => x.style.getPropertyValue('--mkc') === '#12ab56');
                  return !!e;
                }"""), True)
        pag.screenshot(path=str(SALIDA / "marcas_color_propio.png"))
        guardadas[SID] = guardadas[SID][:1]
        pag.evaluate("sid => Marcas.cargar(sid).then(() => { firma=''; pintarSesion(); })", SID)
        pag.wait_for_timeout(1000)

        # --- ⭐ Agarrar una marca con el clic de siempre y cambiarle el color ---
        # Pedido de Martín (2026-08-18): "poder seleccionar ese subrayado y ahí recién
        # cambiarle el color, como lo ofrece el Adobe PDF".
        agarrada = pag.evaluate("""() => {
          const e = document.querySelector('#hilo .mkc');
          const c = e.getBoundingClientRect();
          getSelection().removeAllRanges();
          e.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true,
                          clientX: c.left + 4, clientY: c.top + 4}));
          const m = document.getElementById('menuMarcas');
          return {menu: !!m, dice: m ? m.querySelector('.tit').textContent : '',
                  marcada: !!document.querySelector('#hilo .mkc.elegida')};
        }""")
        revisar("con el clic normal se agarra la marca", agarrada["menu"], True)
        revisar("y el menú habla de ELLA, no de pintar", agarrada["dice"], "Esta marca")
        revisar("la marca agarrada se ve marcada", agarrada["marcada"], True)
        pag.screenshot(path=str(SALIDA / "marcas_agarrada.png"))
        pag.click('#menuMarcas .col[data-color="rosa"]')
        pag.wait_for_timeout(1000)
        revisar("cambiarle el color la cambia en el acto",
                [m["color"] for m in guardadas[SID]], ["rosa"])
        revisar("sigue agarrada después de cambiarla, para seguir probando colores",
                pag.evaluate("() => !!document.querySelector('#hilo .mkc.elegida')"), True)
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(900)
        revisar("con Escape se suelta",
                pag.evaluate("() => !!document.querySelector('#hilo .mkc.elegida')"), False)
        revisar("y no quedó ningún menú abierto",
                pag.evaluate("() => !!document.getElementById('menuMarcas')"), False)

        # --- Clic derecho SOBRE la marca: cambiarla y sacarla ---
        saco = pag.evaluate("""() => {
          const e = document.querySelector('#hilo .mkc');
          const c = e.getBoundingClientRect();
          getSelection().removeAllRanges();
          e.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true, cancelable:true,
                                          clientX: c.left + 4, clientY: c.top + 4}));
          const menu = document.getElementById('menuMarcas');
          return menu ? menu.textContent.includes('Sacar la marca') : false;
        }""")
        revisar("clic derecho sobre una marca ofrece sacarla", saco, True)
        pag.click('#menuMarcas .bt.sacar')
        pag.wait_for_timeout(1000)
        revisar("y la saca de verdad", guardadas[SID], [])
        revisar("la pantalla queda limpia",
                pag.evaluate("() => document.querySelectorAll('#hilo .mkc').length"), 0)

        # --- Sin selección y fuera de una marca, el clic derecho no es nuestro ---
        propio = pag.evaluate("""() => {
          getSelection().removeAllRanges();
          const m = document.querySelector('#hilo [data-msg="0"]');
          const c = m.getBoundingClientRect();
          const ev = new MouseEvent('contextmenu', {bubbles:true, cancelable:true,
                                     clientX: c.left + 5, clientY: c.top + 5});
          m.dispatchEvent(ev);
          return {menu: !!document.getElementById('menuMarcas'), frenado: ev.defaultPrevented};
        }""")
        revisar("sin nada seleccionado no aparece el menú", propio["menu"], False)
        revisar("y el del navegador sigue saliendo", propio["frenado"], False)

        # Dejar la barra como estaba: esto corre contra el panel de verdad.
        pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                guardar(); pintarTabs(); }""")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print()
    print("captura:", SALIDA / "marcas_pintado.png")
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas) if fallas else "TODO BIEN")


if __name__ == "__main__":
    main()
