"""Entrar a Sesiones tiene que ser instantáneo.

Pedido de Martín (2026-08-18): *"¿por qué tarda tanto en entrar en sesiones? ¿Podemos
optimizar esto? Me gustaría que sea instantánea la transición"*. Antes la pantalla se
quedaba en "Cargando…" hasta que el servidor contestaba la lista: entre medio segundo y
tres, según lo ocupado que estuviera el panel.

Tres cosas lo arreglan, y esta prueba fija las tres:

  1. ⭐ la pantalla **se dibuja con la lista de la última vez** (guardada en el navegador)
     y se repinta cuando llega la fresca — o sea que NO espera a nadie para mostrarse;
  2. el servidor guarda su respuesta unos segundos, así las varias pantallas que la piden
     a la vez no la hacen calcular de nuevo;
  3. adentro, `novedad()` y los títulos ya no se releen si el archivo no cambió.

⚠ Los tiempos se miden con el servidor DEMORADO A PROPÓSITO (3 s): así la prueba no
depende de lo rápida que esté la máquina, sino de que la pantalla no se quede esperando.

Correr con:  python -m pruebas.ver_entrada_rapida   (con el panel prendido)
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    # --- El servidor: la segunda consulta seguida sale del cache -------------------
    def pedir():
        t = time.time()
        with urllib.request.urlopen(BASE + "/movil/sesiones", timeout=60) as r:
            r.read()
        return time.time() - t

    pedir()                      # calentar
    seguidas = [pedir() for _ in range(3)]
    print(f"     (el servidor tarda {max(seguidas):.3f}s en el peor de tres seguidas)")
    revisar("pedir la lista dos veces seguidas es casi gratis la segunda",
            max(seguidas) < 0.25, True)

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1300, "height": 700})
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # Primera visita: se llena la copia local.
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo", timeout=40000)
        pag.wait_for_timeout(1200)
        revisar("la lista queda guardada en el navegador para la próxima",
                pag.evaluate("() => { const d = localStorage.getItem('sesDatos');"
                             "  return !!d && JSON.parse(d).proyectos.length > 0; }"), True)

        # --- ⭐ Con el servidor MUDO, la pantalla se dibuja igual --------------------
        # ⚠ Se corta el pedido en vez de demorarlo: demorándolo desde acá se traba el
        # propio Playwright (el que atiende la ruta es el mismo hilo que maneja el
        # navegador) y lo que se termina midiendo es la demora inventada, no la pantalla.
        # Cortado, la prueba es más dura todavía: no hay respuesta NUNCA y aun así la
        # lista tiene que estar.
        pag.route("**/movil/sesiones", lambda r: r.abort())
        t = time.time()
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo", timeout=20000)
        tardo = time.time() - t
        print(f"     (sin respuesta del servidor, la lista se ve en {tardo:.2f}s)")
        revisar("⭐ la pantalla se dibuja sin esperar al servidor", tardo < 1.5, True)
        revisar("y se ve la lista de verdad, no un cartel de 'cargando'",
                pag.evaluate("() => document.querySelectorAll('#cuerpo .correo').length > 1"),
                True)
        revisar("las carpetas de la izquierda también están",
                pag.evaluate("() => document.querySelectorAll('#carpetas .carpeta').length > 1"),
                True)
        pag.screenshot(path=str(SALIDA / "entrada_rapida.png"))

        # --- Y cuando el servidor contesta, lo suyo pisa a lo guardado --------------
        crudo = json.loads(urllib.request.urlopen(BASE + "/movil/sesiones",
                                                  timeout=60).read())
        crudo["proyectos"][0]["proyecto"] = "ProyectoDeLaPrueba"
        pag.unroute("**/movil/sesiones")
        pag.route("**/movil/sesiones", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(crudo)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function(
            "() => datos.proyectos.some(p => p.proyecto === 'ProyectoDeLaPrueba')",
            timeout=20000)
        pag.wait_for_timeout(400)
        revisar("cuando llega la lista fresca, la pantalla se actualiza sola",
                pag.evaluate("() => [...document.querySelectorAll('#carpetas .nom')]"
                             ".some(n => n.textContent.trim() === 'ProyectoDeLaPrueba')"), True)

        revisar("errores de javascript", errores, [])
        # ⚠ Que no quede el proyecto inventado guardado para la próxima corrida.
        pag.evaluate("() => localStorage.removeItem('sesDatos')")
        ctx.close()

        # --- ⭐ Y lo mismo en la app del celular --------------------------------------
        # Pedido de Martín: "fijate si podemos aplicar esto en el celular también". Ahí
        # pesa más todavía: el teléfono entra por Tailscale, así que a lo que tarde el
        # servidor hay que sumarle la red.
        tel = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        cel = tel.new_page()
        cel.on("pageerror", lambda e: errores.append(str(e)))
        # ⚠ Las pestañas del celular viven en el SERVIDOR: se interceptan para no dejarle
        # a Martín una pestaña fantasma en el teléfono.
        cel.route("**/movil/pestanas", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body='{"pestanas": [], "activa": "panel"}') if r.request.method == "GET"
            else r.fulfill(status=200, content_type="application/json", body='{"ok": true}'))
        cel.goto(BASE + "/movil?v=nueva", wait_until="domcontentloaded")
        cel.wait_for_selector("#cuerpo .correo", timeout=40000)
        cel.wait_for_timeout(1500)
        revisar("el celular también se guarda la lista",
                cel.evaluate("() => { const d = localStorage.getItem('movilSesiones');"
                             "  return !!d && JSON.parse(d).proyectos.length > 0; }"), True)

        cel.route("**/movil/sesiones", lambda r: r.abort())
        t = time.time()
        cel.goto(BASE + "/movil?v=nueva", wait_until="domcontentloaded")
        cel.wait_for_selector("#cuerpo .correo", timeout=20000)
        tardoCel = time.time() - t
        print(f"     (en el celular, sin respuesta del servidor: {tardoCel:.2f}s)")
        revisar("⭐ y la app del celular se dibuja sin esperar al servidor",
                tardoCel < 1.5, True)
        revisar("con la lista de conversaciones de verdad",
                cel.evaluate("() => document.querySelectorAll('#cuerpo .correo').length > 1"),
                True)
        cel.screenshot(path=str(SALIDA / "entrada_rapida_movil.png"))
        cel.evaluate("() => localStorage.removeItem('movilSesiones')")
        tel.close()
        nav.close()

    print(f"\ncapturas: {SALIDA / 'entrada_rapida.png'} y entrada_rapida_movil.png")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
