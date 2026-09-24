"""Mover las carpetas de la barra lateral y sacarlas de la lista.

Pedido de Martín (2026-08-18): *"quiero poder mover las carpetas y sacarlas de acá.
Además quiero poder que esto tenga una animación linda"*.

⚠ `/carpetas/orden` y `/carpetas/ocultar` se INTERCEPTAN: el panel vivo todavía no
tiene los endpoints (están en memoria hasta el reinicio), así que esto corre sin
reiniciarlo — y sobre todo, no le toca a Martín el orden ni las carpetas de verdad.
`/movil/sesiones` también se inventa, para tener una lista conocida y estable: con la
real, el chequeo del orden dependería de qué proyectos tenga hoy en el disco.

Correr con:  python -m pruebas.ver_mover_carpetas   (con el panel prendido)
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# La consola de Windows viene en cp1252 y acá los rótulos traen ✕ y ✉: sin esto la prueba
# se corta a la mitad con un UnicodeEncodeError que no tiene nada que ver con la pantalla.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []

PROYECTOS = ["alfa", "beta", "gama", "delta"]
TODAS_TXT = "✉ Todas las conversaciones"      # el mismo rótulo que usa la pantalla
SESIONES = {"ok": True, "laura": "",
            "carpetas": {"orden": [], "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\\\pruebas\\\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-1", "nombre": "charla de " + n,
                                         "ts": 1, "ultimo": "vos", "viva": False,
                                         "detalle": ""}]}
                          for n in PROYECTOS]}

guardado = {"orden": None, "ocultas": [],
            "aspecto": {}, "iconosPropios": [], "sembrado": None}

# ⚠⚠ La hora del archivo REAL antes de empezar, para chequear al final que siga igual.
# El 2026-08-19, una corrida de la prueba hermana (la del celular) se quedó sin registrar
# la intercepción de `/carpetas/…` y los pedidos salieron al panel de verdad: le dejó a
# Martín cuatro nombres inventados en el orden y una carpeta escondida que él no sacó.
_real = Path(__file__).resolve().parent.parent / "orden_carpetas.json"
sello_archivo = _real.stat().st_mtime if _real.exists() else None


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def nombres(pag):
    """Las carpetas visibles, en el orden en que se ven (sin 'Todas')."""
    return pag.evaluate("""() => [...document.querySelectorAll('#carpetas .carpeta[data-proy]')]
      .map(c => c.dataset.proy).filter(p => !p.includes('Todas'))""")


with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    pag = nav.new_page(viewport={"width": 1400, "height": 900})
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))

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

    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(SESIONES)))
    # El colador va PRIMERO: lo que no reconozcan los dos de abajo muere acá y se anota.
    escapados = []
    pag.route("**/carpetas/**", lambda r: (escapados.append(r.request.url),
              r.fulfill(status=200, content_type="application/json", body='{"ok":true}')))
    # ⭐ Desde el 2026-08-25 el ícono, el color y el apodo de cada carpeta también viven en
    # el servidor (pedido de Martín: que sean los mismos entren por donde entren). El
    # servidor de mentira aplica la misma regla que el de verdad: cambia SOLO el campo que
    # vino, así dos pantallas abiertas a la vez no se pisan.
    def aspecto(ruta):
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

    # El selector de navegador del menú de carpeta pide los perfiles de Chrome del disco
    # (2026-08-28). Se contesta vacío: acá no se prueba esa perilla, pero si no se
    # intercepta, el pedido se le escapa al panel de verdad y lo caza el chequeo final.
    pag.route("**/carpetas/navegadores*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true,"perfiles":[]}'))
    pag.route("**/carpetas/orden*", orden)
    pag.route("**/carpetas/ocultar*", ocultar)
    pag.route("**/carpetas/aspecto", aspecto)
    pag.route("**/carpetas/aspecto/sembrar", sembrar)

    # Sin nada guardado: el navegador tiene que arrancar con la lista del servidor.
    pag.add_init_script("localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy]", timeout=8000)
    pag.wait_for_timeout(900)

    revisar("arranca con las cuatro carpetas", nombres(pag), PROYECTOS)

    # --- ⚠⚠ Se arrastra la FILA ENTERA, no un agarre al costado -------------------
    # Segunda vuelta del pedido: "no me gusta tener que agarrar el costado, tendría
    # que poder seleccionar la carpeta entera y así moverla". Hubo un ⠿ y se sacó.
    revisar("ya no hay agarre al costado",
            pag.evaluate("() => document.querySelectorAll('#carpetas .carpeta .asa').length"), 0)
    revisar("cada carpeta tiene su botón de sacar",
            pag.evaluate("() => document.querySelectorAll('#carpetas [data-sacar]').length"), 4)
    revisar("la ✕ quieta no se ve",
            pag.evaluate("""() => getComputedStyle(
              document.querySelector('#carpetas [data-sacar]')).opacity"""), "0")

    # --- ⭐⭐ Un clic sin mover ENTRA al proyecto; recién moviendo, arrastra --------
    # Es lo que hace que el mismo renglón sirva para las dos cosas.
    pag.click("#carpetas .carpeta[data-proy='beta']")
    pag.wait_for_timeout(400)
    revisar("un clic quieto entra al proyecto",
            pag.evaluate("() => proy"), "beta")
    pag.click("#carpetas .carpeta[data-proy*='Todas']")
    pag.wait_for_timeout(400)

    # Movimiento por debajo del umbral: sigue siendo un clic, no un arrastre.
    caja = pag.locator("#carpetas .carpeta[data-proy='alfa']").bounding_box()
    pag.mouse.move(caja["x"] + 60, caja["y"] + caja["height"] / 2)
    pag.mouse.down()
    pag.mouse.move(caja["x"] + 62, caja["y"] + caja["height"] / 2 + 1)
    pag.mouse.up()
    pag.wait_for_timeout(400)
    revisar("un temblor de la mano no arrastra: entra igual",
            pag.evaluate("() => proy"), "alfa")
    pag.click("#carpetas .carpeta[data-proy*='Todas']")
    pag.wait_for_timeout(400)

    # --- Mover: arrastrar 'gama' arriba de todo -----------------------------------
    caja = pag.locator("#carpetas .carpeta[data-proy='gama']").bounding_box()
    arriba = pag.locator("#carpetas .carpeta[data-proy='alfa']").bounding_box()
    pag.mouse.move(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
    pag.mouse.down()
    pag.wait_for_timeout(120)
    # ⚠ Apenas apretás TODAVÍA no es un arrastre: hace falta pasar el umbral. Eso es
    # justo lo que deja que el mismo renglón siga sirviendo para entrar al proyecto.
    revisar("apretada y quieta, todavía no se levanta",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='gama']").classList.contains('deslizando')"""), False)
    # Hasta arriba del todo, por encima de la mitad de 'alfa'
    pag.mouse.move(arriba["x"] + arriba["width"] / 2, arriba["y"] + 3, steps=12)
    pag.wait_for_timeout(220)
    revisar("pasado el umbral, la carpeta se levanta",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='gama']").classList.contains('deslizando')"""), True)
    pag.mouse.up()
    pag.wait_for_timeout(400)

    revisar("gama quedó primera", nombres(pag)[0], "gama")
    revisar("y el orden nuevo se guardó en el servidor", guardado["orden"],
            ["gama", "alfa", "beta", "delta"])
    revisar("soltada, ya no está levantada",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='gama']").classList.contains('deslizando')"""), False)

    # ⚠⚠ Arrastrar NO puede además ENTRAR al proyecto: soltar la carpeta donde la
    # moviste no puede cambiarte de carpeta de yapa. Se sigue en 'Todas'.
    revisar("arrastrar no entró a esa carpeta", pag.evaluate("() => proy"), TODAS_TXT)

    # --- Sacar una de la lista ------------------------------------------------------
    pag.hover("#carpetas .carpeta[data-proy='beta']")
    pag.click("#carpetas [data-sacar='beta']")
    pag.wait_for_timeout(700)
    revisar("beta salió de la lista", "beta" in nombres(pag), False)
    revisar("y el servidor se enteró", guardado["ocultas"], ["beta"])
    # ⚠⚠ Esconder NO borra: la carpeta sigue existiendo en los datos, solo no se pinta.
    revisar("los datos siguen teniendo las cuatro",
            pag.evaluate("() => datos.proyectos.length"), 4)

    # --- El camino de vuelta TIENE que estar a la vista ---------------------------
    # Una lista que se desarma sin poder rearmarse es una trampa; ya pasó con el
    # explorador desaparecido por una llave vieja (INTERFAZ.md).
    revisar("aparece el pie 'Escondidas'",
            pag.evaluate("() => !!document.querySelector('#verOcultas')"), True)
    revisar("y dice cuántas hay",
            pag.evaluate("() => document.querySelector('#verOcultas .num').textContent"), "1")
    pag.click("#verOcultas")
    pag.wait_for_timeout(250)
    revisar("desplegado, ofrece devolverla",
            pag.evaluate("""() => !!document.querySelector("[data-volver='beta']")"""), True)
    pag.click("[data-volver='beta']")
    pag.wait_for_timeout(450)
    revisar("beta volvió a la lista", "beta" in nombres(pag), True)
    revisar("y volvió a SU lugar, no al final", nombres(pag), ["gama", "alfa", "beta", "delta"])
    revisar("el servidor la sacó de las escondidas", guardado["ocultas"], [])

    # --- Buscando por nombre se ven también las escondidas -------------------------
    # Si escribís el nombre de una que sacaste y no aparece, parece que se borró.
    pag.hover("#carpetas .carpeta[data-proy='delta']")
    pag.click("#carpetas [data-sacar='delta']")
    pag.wait_for_timeout(700)
    pag.fill("#buscar", "delta")
    pag.wait_for_timeout(300)
    revisar("buscándola, la escondida aparece igual", nombres(pag), ["delta"])
    pag.fill("#buscar", "")
    pag.wait_for_timeout(300)

    # --- El orden aguanta un refresco de la lista ---------------------------------
    # ⚠ El refresco de cada 20 s no puede devolverte el orden viejo del servidor.
    SESIONES["carpetas"] = {"orden": ["gama", "alfa", "beta", "delta"], "ocultas": ["delta"]}
    pag.evaluate("() => cargar()")
    pag.wait_for_timeout(600)
    revisar("tras refrescar, el orden se mantiene", nombres(pag), ["gama", "alfa", "beta"])

    # --- ⭐ La identidad visual de cada carpeta (botón derecho) --------------------
    # Pedido de Martín: "editar la identidad visual de cada carpeta, así como hacemos
    # con casi todas las cosas… fijate cómo tenemos armado el de sesiones".
    pag.evaluate("""() => ['sesTonos','sesIconos','sesIconosPropios']
                            .forEach(k => localStorage.removeItem(k))""")
    pag.click("#carpetas .carpeta[data-proy='alfa']", button="right")
    pag.wait_for_timeout(300)
    revisar("el botón derecho abre el menú",
            pag.evaluate("() => document.querySelector('#menuTarjeta').classList.contains('abierto')"),
            True)
    revisar("y dice que es de una carpeta",
            pag.evaluate("() => document.querySelector('#menuTarjeta .rub').textContent"), "Carpeta")
    revisar("ofrece los seis tonos, el sin color y la rueda",
            pag.evaluate("""() => document.querySelectorAll(
              '#menuTarjeta .tonos:not(.iconos) .tono').length"""), 7)
    revisar("y los íconos con su 'el de siempre'",
            pag.evaluate("() => document.querySelectorAll('#menuTarjeta [data-ico]').length"), 17)

    # Pintar: se ve EN EL ACTO y el menú NO se cierra (probar tres tonos son tres clics).
    pag.click("#menuTarjeta .tono[data-tono='violeta']")
    pag.wait_for_timeout(250)
    revisar("tocar un tono pinta la carpeta",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='alfa']").classList.contains('pintada')"""), True)
    revisar("el menú se queda abierto para probar otro",
            pag.evaluate("() => document.querySelector('#menuTarjeta').classList.contains('abierto')"),
            True)

    # ⭐⭐ La carpeta y SU PASTILLA comparten identidad: son el mismo proyecto.
    revisar("el color se guarda con la misma llave que la pastilla del proyecto",
            pag.evaluate("() => JSON.parse(localStorage.getItem('sesTonos'))['g:alfa']"),
            "violeta")

    # El ícono propio
    pag.click("#menuTarjeta [data-ico='🔥']")
    pag.wait_for_timeout(250)
    revisar("el ícono elegido se ve en la carpeta",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='alfa'] span").textContent"""), "🔥")
    revisar("y se guarda aparte de los del explorador",
            pag.evaluate("() => JSON.parse(localStorage.getItem('sesIconos'))['alfa']"), "🔥")

    # --- ⭐ Agregar íconos propios ("me gustaría poder agregar iconos") --------------
    # ⭐⭐ Sin `prompt()` del navegador: Martín vio ese cartel y dijo "se ve muy feo".
    # El ＋ abre un buscador adentro del mismo menú.
    revisar("hay un ＋ para agregar uno tuyo",
            pag.evaluate("() => !!document.querySelector('#menuTarjeta .tono.mas')"), True)
    pag.click("#menuTarjeta .tono.mas")
    pag.wait_for_timeout(250)
    revisar("el ＋ abre el buscador adentro del menú, no un cartel del navegador",
            pag.evaluate("() => !!document.querySelector('#menuTarjeta .buscaIco')"), True)
    revisar("y el cursor ya está adentro para escribir",
            pag.evaluate("() => document.activeElement.className"), "buscaIco")
    revisar("de entrada muestra el catálogo entero",
            pag.evaluate("() => document.querySelectorAll('#menuTarjeta .galeria [data-ico]').length > 100"),
            True)

    # Buscar por palabra: es lo que reemplaza a saber el atajo de emojis de Windows.
    pag.fill("#menuTarjeta .buscaIco", "cohete")
    pag.wait_for_timeout(200)
    revisar("buscando 'cohete' aparece el 🚀 primero",
            pag.evaluate("""() => document.querySelector(
              '#menuTarjeta .galeria [data-ico]').dataset.ico"""), "🚀")
    pag.press("#menuTarjeta .buscaIco", "Enter")
    pag.wait_for_timeout(250)
    revisar("el que elegís se le pone a la carpeta sin elegirlo de nuevo",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='alfa'] span").textContent"""), "🚀")
    revisar("y queda guardado en el juego",
            pag.evaluate("() => JSON.parse(localStorage.getItem('sesIconosPropios'))"), ["🚀"])
    revisar("elegido, el buscador se cierra y vuelve la fila",
            pag.evaluate("() => !!document.querySelector('#menuTarjeta .tono.mas')"), True)
    revisar("el menú no se cierra al agregarlo",
            pag.evaluate("() => document.querySelector('#menuTarjeta').classList.contains('abierto')"),
            True)

    # ⭐ El juego es de TODAS las carpetas, no de la que estabas mirando cuando lo pegaste.
    # (el menú abierto tapa la lista, así que primero se cierra como lo haría él)
    pag.evaluate("() => cerrarMenuTarjeta()")
    pag.click("#carpetas .carpeta[data-proy='beta']", button="right")
    pag.wait_for_timeout(300)
    revisar("el ícono agregado está disponible para otra carpeta",
            pag.evaluate("""() => !!document.querySelector(
              "#menuTarjeta .tono.propio[data-ico='🚀']")"""), True)

    # ⚠ Pegar uno que NO está en el catálogo tiene que servir igual: va primero, marcado.
    # Y una bandera son dos códigos: cortarla al medio deja un garabato, así que se corta
    # por grafemas y no por caracteres.
    pag.click("#menuTarjeta .tono.mas")
    pag.fill("#menuTarjeta .buscaIco", "🇦🇷 y algo más")
    pag.wait_for_timeout(200)
    revisar("lo que pegás va primero aunque no esté en el catálogo",
            pag.evaluate("""() => document.querySelector(
              '#menuTarjeta .galeria .pegado').dataset.ico"""), "🇦🇷")
    pag.click("#menuTarjeta .galeria .pegado")
    pag.wait_for_timeout(250)
    revisar("de un texto largo se queda con el primer signo, entero",
            pag.evaluate("() => JSON.parse(localStorage.getItem('sesIconos'))['beta']"), "🇦🇷")

    # Buscar algo que no existe avisa, en vez de dejar un hueco mudo.
    pag.click("#menuTarjeta .tono.mas")
    pag.fill("#menuTarjeta .buscaIco", "zzzz")
    pag.wait_for_timeout(200)
    revisar("si no encuentra nada lo dice",
            pag.evaluate("() => !!document.querySelector('#menuTarjeta .nada-hay')"), True)
    pag.press("#menuTarjeta .buscaIco", "Escape")
    pag.wait_for_timeout(200)
    revisar("Escape vuelve a la fila sin cerrar el menú",
            pag.evaluate("""() => !!document.querySelector('#menuTarjeta .tono.mas')
              && document.querySelector('#menuTarjeta').classList.contains('abierto')"""), True)

    # Sacar uno del juego NO despinta a las carpetas que ya lo usan.
    pag.click("#menuTarjeta .tono.propio[data-ico='🚀']", button="right")
    pag.wait_for_timeout(250)
    revisar("botón derecho lo saca del juego",
            pag.evaluate("() => JSON.parse(localStorage.getItem('sesIconosPropios'))"), ["🇦🇷"])
    revisar("pero la carpeta que lo usaba lo conserva",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='alfa'] span").textContent"""), "🚀")
    pag.evaluate("() => cerrarMenuTarjeta()")
    pag.click("#carpetas .carpeta[data-proy='alfa']", button="right")
    pag.wait_for_timeout(300)
    revisar("y el menú de esa carpeta lo sigue mostrando puesto",
            pag.evaluate("""() => !!document.querySelector(
              "#menuTarjeta .tono[data-ico='🚀'].sel")"""), True)

    # El apodo: rótulo nuevo, pero la LLAVE sigue siendo el nombre real de la carpeta —
    # si no, la lista dejaría de encontrar sus conversaciones.
    pag.evaluate("() => { window.prompt = () => 'Lo de Juan'; }")
    pag.click("#menuTarjeta [data-hace='nombre']")
    pag.wait_for_timeout(350)
    revisar("el apodo se muestra en la lista",
            pag.evaluate("""() => document.querySelector(
              "#carpetas .carpeta[data-proy='alfa'] .nom").textContent"""), "Lo de Juan")
    revisar("pero la llave sigue siendo el nombre real",
            pag.evaluate("""() => !!document.querySelector(
              "#carpetas .carpeta[data-proy='alfa']")"""), True)
    revisar("y entrar sigue funcionando con el nombre real",
            pag.evaluate("""() => { irProyecto('alfa'); return proy; }"""), "alfa")

    # ⚠ Pintada Y seleccionada: el color le gana a `.sel`, así que "estás parado acá" lo
    # cuenta la barrita de la izquierda, que no se pinta nunca.
    pag.wait_for_timeout(300)
    revisar("pintada y seleccionada a la vez sigue marcada",
            pag.evaluate("""() => { const c = document.querySelector(
              "#carpetas .carpeta[data-proy='alfa']");
              return c.classList.contains('sel') && c.classList.contains('pintada'); }"""), True)

    # --- ⭐⭐ Y todo eso vive en el SERVIDOR, no en este navegador (2026-08-25) ---------
    # El pedido de Martín fue que los íconos estén "no importa si abro desde el celular, la
    # app de escritorio o desde otro navegador". Lo que sigue es la mitad que lo cumple:
    # cada cosa que eligió arriba tiene que haber salido para el servidor.
    revisar("el ícono elegido subió al servidor",
            (guardado["aspecto"].get("alfa") or {}).get("icono"), "🚀")
    revisar("el color también", (guardado["aspecto"].get("alfa") or {}).get("color"), "violeta")
    revisar("y el apodo", (guardado["aspecto"].get("alfa") or {}).get("apodo"), "Lo de Juan")
    # ⚠ Lo que queda es 🇦🇷 y no 🚀 porque más arriba se probó justamente sacar uno del
    # juego con el botón derecho: el servidor tiene que tener el juego COMO QUEDÓ.
    revisar("el juego de íconos propios también viaja", guardado["iconosPropios"], ["🇦🇷"])
    revisar("y este navegador sembró lo suyo al arrancar",
            (guardado["sembrado"] or {}).get("origen"), "compu")

    revisar("sin errores de JS", errores, [])
    revisar("no se le escribió nada al panel de verdad", escapados, [])
    revisar("y el archivo real no se tocó",
            _real.stat().st_mtime if _real.exists() else None, sello_archivo)
    nav.close()

print()
if fallas:
    print(f"{len(fallas)} mal:")
    for f in fallas:
        print("  - " + f)
    sys.exit(1)
print("todo bien")
