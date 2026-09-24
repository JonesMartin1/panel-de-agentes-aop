"""El aspecto (fondo, tipografía y color) vale para TODAS las pantallas.

Pedido de Martín (2026-08-17): "me gustaría poder llevar esta configuración visual tanto
a la interfaz de móvil como al resto de pestañas del panel". Antes vivía adentro de
`sesiones.html` y valía para esa sola pantalla y ese solo navegador.

Lo que fija esta prueba:
  * el 🎨 está en las pantallas de la compu y también en la app del celular;
  * lo elegido se guarda en el SERVIDOR, así que la misma elección vale en las otras
    pantallas y en el teléfono — se elige en una y se comprueba en las demás;
  * la tipografía y el fondo se aplican de verdad en cada una;
  * ⭐ el semáforo de las conversaciones NO cambia con el tema.

⚠ Deja el aspecto como estaba al terminar.

Correr con:  python -m pruebas.ver_aspecto_global   (con el panel prendido)
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
PANTALLAS = ["/", "/sesiones", "/pizarra", "/estudio", "/avisos"]
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def guardado():
    with urllib.request.urlopen(BASE + "/aspecto", timeout=10) as r:
        return json.loads(r.read())


def poner(d):
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/aspecto", data=json.dumps(d).encode(), method="POST",
        headers={"Content-Type": "application/json"}), timeout=10).read()


def main():
    antes = guardado()
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # --- El botón está en todas las pantallas de la compu ---
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        pag.on("pageerror", lambda e: errores.append(str(e)))
        for url in PANTALLAS:
            pag.goto(BASE + url, wait_until="domcontentloaded")
            pag.wait_for_timeout(1200)
            revisar(f"el 🎨 está en {url}",
                    pag.evaluate("() => !!document.getElementById('aspectoBtn')"), True)

        # --- Elegir desde UNA pantalla y que quede guardado en el servidor ---
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(1800)
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(400)
        # ⚠ Desde los estilos (2026-08-29) las secciones del 🎨 vienen plegadas y
        # Playwright no clickea lo que no se ve: hay que abrirlas o el click muere
        # esperando 30 s. No cambia lo que mide esta prueba.
        pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                     ".forEach(d => { d.open = true; })")
        pag.wait_for_timeout(150)
        pag.click('#aspectoPanel .ops[data-campo="tipo"] .op[data-v="mono"]')
        pag.wait_for_timeout(300)
        pag.click('#aspectoPanel .ops[data-campo="color"] .op[data-v="rosa"]')
        pag.wait_for_timeout(300)
        pag.click('#aspectoPanel .ops[data-campo="fondo"] .op[data-v="negro"]')
        pag.wait_for_timeout(800)
        g = guardado()
        revisar("lo elegido queda en el servidor",
                [g.get("tipo"), g.get("color"), g.get("fondo")], ["mono", "rosa", "negro"])

        # --- Y las otras pantallas lo toman al abrirlas ---
        for url in ["/", "/pizarra", "/estudio"]:
            pag.goto(BASE + url, wait_until="domcontentloaded")
            pag.wait_for_timeout(1500)
            r = pag.evaluate("""() => ({
              letra: getComputedStyle(document.body).fontFamily,
              fondo: getComputedStyle(document.body).backgroundColor,
              acento: getComputedStyle(document.documentElement)
                        .getPropertyValue('--acento').trim()})""")
            revisar(f"{url} toma la tipografía", "Consolas" in r["letra"], True)
            revisar(f"{url} toma el fondo", r["fondo"], "rgb(7, 8, 11)")
            revisar(f"{url} toma el color", r["acento"], "#f9a8d4")
        # --- ⭐ Las burbujas del chat también siguen al tema (2026-08-18) ------------
        # Martín: "quiero cambiar los colores de todo, absolutamente de todo". Antes el
        # tema llegaba a los marcos y el chat quedaba azul pasara lo que pasara.
        # ⚠⚠ Antes de mirar las burbujas hay que dejar las dos "siguiendo al tema". Desde
        # el 2026-08-29 cada parte puede tener SU color elegido (el 🎨 → Color de cada
        # parte), y esa eleccion pisa al derivado del acento — que es justo lo que este
        # bloque afirma medir. Sin esto, la prueba falla cuando el aspecto guardado tiene
        # una burbuja con color propio, o sea cuando Martin uso la funcion: no estaria
        # midiendo un defecto, estaria midiendo su gusto. (Se restaura todo al final.)
        poner(dict(guardado(), burbujaVos="", burbujaIa=""))
        import json as _json
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=_json.dumps({"mensajes": [{"de": "vos", "texto": "hola", "imgs": []},
                                           {"de": "claude", "texto": "chau", "imgs": []}]})))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(1800)
        pag.evaluate("c => abrirSesion(c, 'demo-tema', 'Prueba')", str(RAIZ))
        pag.wait_for_timeout(1500)
        burbujas = pag.evaluate("""() => ({
          vos: getComputedStyle(document.querySelector('.msg.vos')).backgroundColor,
          borde: getComputedStyle(document.querySelector('.msg.claude')).borderLeftColor})""")
        # Con el acento rosa (#f9a8d4 = 249,168,212) la burbuja tuya tira a rosa y el
        # borde de la de Claude ES el acento.
        revisar("el borde de la burbuja de Claude es el acento",
                burbujas["borde"], "rgb(249, 168, 212)")
        rojo, verde, azul = [int(x) for x in burbujas["vos"][4:-1].split(",")]
        revisar("y tu burbuja se tiñe del mismo lado (más rojo que azul)", rojo > azul, True)
        pag.evaluate("() => { abiertas = []; activa = null; guardar(); }")

        pag.screenshot(path=str(SALIDA / "aspecto_global_compu.png"))
        pag.close()

        # --- El celular: el botón está y el tema es el mismo ---
        tel = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        tel.on("pageerror", lambda e: errores.append(str(e)))
        tel.goto(BASE + "/movil", wait_until="domcontentloaded")
        tel.wait_for_timeout(2200)
        revisar("el 🎨 está en la app del celular",
                tel.evaluate("() => !!document.getElementById('aspectoBtn')"), True)
        r = tel.evaluate("""() => ({
          letra: getComputedStyle(document.body).fontFamily,
          fondo: getComputedStyle(document.body).backgroundColor,
          acento: getComputedStyle(document.documentElement)
                    .getPropertyValue('--acento').trim()})""")
        revisar("y el celular usa lo elegido en la compu",
                [("Consolas" in r["letra"]), r["fondo"], r["acento"]],
                [True, "rgb(7, 8, 11)", "#f9a8d4"])
        tel.screenshot(path=str(SALIDA / "aspecto_global_movil.png"))
        tel.close()

        # --- ⭐ El semáforo de las conversaciones no depende del tema ---
        ses = nav.new_page(viewport={"width": 1400, "height": 900})
        ses.on("pageerror", lambda e: errores.append(str(e)))
        ses.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        ses.wait_for_timeout(1800)
        ses.evaluate("""() => {
          const ahora = Date.now() / 1000;
          datos = {proyectos: [{proyecto:'PruebaTema', cwd:'D:/PruebaTema', vivo:true, sesiones:[
            {id:'v', nombre:'Te espera', viva:false, interactiva:false,
             detalle:'guardada, prueba', ts:ahora-120, ultimo:'claude'},
            {id:'a', nombre:'Trabajando', viva:true, interactiva:false,
             detalle:'activa, prueba', ts:ahora-5, ultimo:'claude'}]}]};
          proy = 'PruebaTema'; activa = null; firma = ''; pintarCarpetas(); pintarLista();
        }""")
        ses.wait_for_timeout(500)
        revisar("con otro tema, el verde de 'te espera' sigue igual",
                ses.evaluate("() => getComputedStyle(document.querySelector('.correo.espera'))"
                             ".borderLeftColor"), "rgb(61, 220, 132)")
        revisar("y el amarillo de 'trabajando' también",
                ses.evaluate("() => getComputedStyle(document.querySelector('.correo.trabajando'))"
                             ".borderLeftColor"), "rgb(245, 158, 11)")
        nav.close()

    # --- ⭐ El fondo de Windows es EL DEL ESCRITORIO, y sigue sus cambios ---------
    # Antes se leía la carpeta del Spotlight de la pantalla de BLOQUEO, que es otra
    # colección: el panel mostraba una foto y el escritorio otra (2026-08-18).
    import ctypes
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buf, 0)   # SPI_GETDESKWALLPAPER
    del_escritorio = buf.value
    r = urllib.request.urlopen(BASE + "/fondo/windows", timeout=30)
    servida = r.read()
    revisar("la foto que sirve el panel es la del escritorio",
            len(servida), os.path.getsize(del_escritorio))
    v1 = json.loads(urllib.request.urlopen(BASE + "/fondo/windows/version", timeout=10).read())
    revisar("y hay una firma barata para saber si cambió",
            bool(v1.get("v")) and os.path.basename(del_escritorio) in v1["v"], True)
    revisar("preguntar la firma no baja la foto", len(json.dumps(v1)) < 200, True)

    poner(antes or {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": ""})
    revisar("errores de javascript", errores, [])
    print(f"\ncapturas: {SALIDA / 'aspecto_global_compu.png'} y aspecto_global_movil.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
