"""Elegir el fondo, la tipografía y el color de la pantalla de sesiones.

Pedido de Martín (2026-08-17): "hay manera de poner un fondo y elegir la tipografía y
elegir el color de la interfaz". El botón 🎨 de la barra abre tres perillas.

Lo que esta prueba fija:
  * el botón abre y cierra el panel, y se cierra tocando afuera;
  * elegir tipografía cambia la letra de verdad (no solo la marca en el panel);
  * elegir color repinta el acento (la carpeta marcada, el ＋, los botones);
  * elegir fondo cambia el fondo de la página;
  * la elección sobrevive al F5;
  * ⭐ el semáforo NO se toca: verde/amarillo/rojo siguen siendo los mismos con
    cualquier tema, porque son el idioma de los estados y no decoración.

Correr con:  python -m pruebas.ver_aspecto_sesiones   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def variable(pag, nombre):
    return pag.evaluate("n => getComputedStyle(document.documentElement)"
                        ".getPropertyValue(n).trim()", nombre)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 860})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("() => { aspecto = Object.assign({}, ASPECTO_BASE); aplicarAspecto();"
                     "         abiertas = []; activa = null; guardar(); pintarTabs();"
                     "         irProyecto(TODAS); }")
        pag.wait_for_timeout(600)

        # --- El panel se abre y se cierra ---
        revisar("de entrada el panel está cerrado",
                pag.evaluate("() => document.getElementById('asp').classList.contains('abierto')"),
                False)
        pag.click("#aspBtn")
        pag.wait_for_timeout(300)
        revisar("el 🎨 lo abre",
                pag.evaluate("() => document.getElementById('asp').classList.contains('abierto')"),
                True)
        revisar("con las tres perillas",
                pag.evaluate("() => [...document.querySelectorAll('#asp .rub')]"
                             ".map(r => r.textContent)"),
                ["Tipografía", "Color", "Fondo"])

        # --- Tipografía ---
        pag.click('#asp .ops[data-campo="tipo"] .op[data-v="mono"]')
        pag.wait_for_timeout(300)
        revisar("eligiendo monoespaciada, la página cambia de letra",
                "Consolas" in pag.evaluate("() => getComputedStyle(document.body).fontFamily"),
                True)

        # --- Color ---
        pag.click('#asp .ops[data-campo="color"] .op[data-v="rosa"]')
        pag.wait_for_timeout(300)
        revisar("eligiendo rosa, el acento cambia", variable(pag, "--acento"), "#f9a8d4")
        revisar("y la carpeta marcada se pinta con eso",
                pag.evaluate("() => getComputedStyle(document.querySelector('.carpeta.sel')).color"),
                "rgb(249, 168, 212)")

        # --- Fondo ---
        pag.click('#asp .ops[data-campo="fondo"] .op[data-v="negro"]')
        pag.wait_for_timeout(300)
        revisar("eligiendo negro, el fondo cambia",
                pag.evaluate("() => getComputedStyle(document.body).backgroundColor"),
                "rgb(7, 8, 11)")
        pag.screenshot(path=str(SALIDA / "sesiones_aspecto.png"))

        # --- ⭐ El semáforo no se toca con ningún tema ---
        pag.evaluate("""() => {
          const ahora = Date.now() / 1000;
          datos = {proyectos: [{proyecto:'PruebaTema', cwd:'D:/PruebaTema', vivo:true, sesiones:[
            {id:'v', nombre:'Te espera', viva:false, interactiva:false,
             detalle:'guardada, prueba', ts:ahora-120, ultimo:'claude'},
            {id:'a', nombre:'Trabajando', viva:true, interactiva:false,
             detalle:'activa, prueba', ts:ahora-5, ultimo:'claude'}]}]};
          proy = 'PruebaTema'; activa = null; firma = ''; pintarCarpetas(); pintarLista();
        }""")
        pag.wait_for_timeout(400)
        revisar("con otro tema, el verde de 'te espera' es el mismo",
                pag.evaluate("() => getComputedStyle(document.querySelector('.correo.espera'))"
                             ".borderLeftColor"), "rgb(61, 220, 132)")
        revisar("y el amarillo de 'trabajando' también",
                pag.evaluate("() => getComputedStyle(document.querySelector('.correo.trabajando'))"
                             ".borderLeftColor"), "rgb(245, 158, 11)")

        # --- La imagen de fondo ---
        # Se le mete una imagen mínima inventada en vez de abrir el explorador de
        # archivos: lo que importa es que quede detrás de todo y que las superficies se
        # vuelvan translúcidas, no de dónde salió el archivo.
        pag.evaluate("""() => {
          aspecto.img = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf'
                      + 'FcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
          aplicarAspecto(); pintarAspecto();
        }""")
        pag.wait_for_timeout(400)
        revisar("con imagen, el fondo de la página la usa",
                "url(\"data:image/png" in
                pag.evaluate("() => getComputedStyle(document.body).backgroundImage"), True)
        revisar("y la barra se vuelve translúcida para que se vea",
                pag.evaluate("() => getComputedStyle(document.getElementById('barra'))"
                             ".backgroundColor").startswith("rgba("), True)
        revisar("aparece el botón de sacarla",
                pag.evaluate("() => !!document.getElementById('aspSacar')"), True)
        pag.click("#aspSacar")
        pag.wait_for_timeout(300)
        revisar("sacándola, el fondo vuelve a ser liso",
                pag.evaluate("() => getComputedStyle(document.body).backgroundImage"), "none")

        # --- La foto de Windows (la que se cambia sola) ---
        pag.click("#aspWin")
        pag.wait_for_timeout(1200)
        usada = pag.evaluate("() => aspecto.img")
        revisar("el botón 🪟 pone una dirección, no una copia pegada",
                usada.startswith("/"), True)
        # Que la dirección elegida devuelva una imagen de verdad (sea la ruta nueva del
        # panel o el puente de mientras).
        r = pag.request.get(BASE + usada)
        revisar("y esa dirección trae una imagen",
                r.headers.get("content-type"), "image/jpeg")
        revisar("de un tamaño de foto de verdad", len(r.body()) > 200_000, True)
        pag.screenshot(path=str(SALIDA / "sesiones_fondo_windows.png"))

        # --- Se cierra tocando afuera, y la elección sobrevive al F5 ---
        pag.click("#cuerpo", position={"x": 600, "y": 400})
        pag.wait_for_timeout(300)
        revisar("tocando afuera se cierra",
                pag.evaluate("() => document.getElementById('asp').classList.contains('abierto')"),
                False)
        pag.reload(wait_until="domcontentloaded")
        pag.wait_for_timeout(2200)
        revisar("después de recargar sigue el color elegido",
                variable(pag, "--acento"), "#f9a8d4")
        revisar("y la tipografía elegida",
                "Consolas" in pag.evaluate("() => getComputedStyle(document.body).fontFamily"),
                True)

        # Dejarlo como estaba, que esta es la pantalla que Martín usa.
        pag.evaluate("() => { aspecto = Object.assign({}, ASPECTO_BASE); aplicarAspecto(); }")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_aspecto.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
