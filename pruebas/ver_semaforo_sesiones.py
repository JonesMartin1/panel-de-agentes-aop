"""El semáforo de la lista de sesiones: verde te espera, amarillo trabaja, rojo falló.

Los tres colores los eligió Martín el 2026-08-17 ("verde para el que me está esperando,
amarillo naranjoso para el que esté trabajando, y rojo para el que haya fallado"), y
esta prueba los deja fijados junto con la regla de cuándo se aplica cada uno:

  * lo último que mandaste falló             → ROJO, y dice por qué;
  * viva y escribiendo (menos de 45 s)       → AMARILLO, "trabajando";
  * viva pero quieta, habló Claude último    → VERDE, "te está esperando";
  * NO viva y habló Claude último            → VERDE: las charlas que arrancás desde
    el celular no dejan proceso abierto, y son justo las que esperan respuesta;
  * lo mismo pero de hace horas              → SIGUE VERDE: el verde se apaga cuando la
    ABRÍS, no con el reloj (pedido de Martín, 2026-08-17). Hubo un tope de una hora y se
    sacó: apagaba solo respuestas que nadie había leído todavía;
  * si el último que habló fuiste vos        → sin marcar, la pelota no es tuya.

Se prueba con datos INVENTADOS metidos en la página (`datos = …`), única forma de fijar
todos los casos a la vez: con las sesiones de verdad el resultado depende de qué esté
corriendo en ese momento. No toca ninguna sesión real.

Correr con:  python -m pruebas.ver_semaforo_sesiones   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
fallas = []

# (id, nombre, viva, interactiva, hace cuántos segundos se movió, quién habló último, clase)
# ⚠ `interactiva` = una VENTANA de Claude Code abierta en la compu. Un turno lanzado
# desde el panel o el celular también está "vivo", pero solo mientras piensa: por eso
# ése cuenta como trabajando aunque haga rato que no escribe (puede estar minutos
# adentro de una herramienta), y la ventana abierta se juzga por el reloj.
CASOS = [
    ("i", "Candado real ocupado",       False, False,      300, "claude", "trabajando"),
    ("a", "Ventana escribiendo",     True,  True,         5, "claude", "trabajando"),
    ("b", "Ventana quieta, te espera", True, True,      300, "claude", "espera"),
    ("c", "Ventana quieta, le toca a ella", True, True, 300, "vos",    ""),
    ("h", "Turno del panel pensando", True, False,      300, "claude", "trabajando"),
    ("d", "Del celular, recién",     False, False,      120, "claude", "espera"),
    ("e", "Del celular, de hace 4 h", False, False, 4 * 3600, "claude", "espera"),
    ("f", "Última palabra tuya",     False, False,      120, "vos",    ""),
    ("g", "Esta falló",              False, False,      120, "claude", "fallada"),
]
FALLA = "el turno se pasó de 10 minutos"

ARMAR = """(casos) => {
  const ahora = Date.now() / 1000;
  falladas = {g: 'el turno se pasó de 10 minutos'};
  datos = {proyectos: [{proyecto: 'PruebaColores', cwd: 'D:/PruebaColores', vivo: true,
    sesiones: casos.map(c => ({id: c[0], nombre: c[1], viva: c[2], interactiva: c[3],
      ocupada: c[0] === 'i',
      detalle: (c[2] ? 'activa' : 'guardada') + ', prueba',
      ts: ahora - c[4], ultimo: c[5]}))}]};
  proy = 'PruebaColores'; activa = null; firma = '';
  pintarCarpetas(); pintarLista();
}"""

COLORES = {"espera": "rgb(61, 220, 132)",       # verde
           "trabajando": "rgb(245, 158, 11)",   # amarillo naranjoso
           "fallada": "rgb(239, 68, 68)"}       # rojo


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        pag = nav.new_page(viewport={"width": 1400, "height": 760})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("() => { abiertas = []; activa = null; guardar(); pintarTabs(); }")
        pag.evaluate(ARMAR, CASOS)
        pag.wait_for_timeout(500)

        for sid, nombre, _viva, _inter, _hace, _quien, esperada in CASOS:
            clase = pag.evaluate(
                "s => { const el = document.querySelector('.correo[data-sid=\"' + s + '\"]');"
                "       return el ? el.className.replace('correo','').trim() : 'NO ESTA'; }", sid)
            revisar(nombre, clase, esperada)

        # Y que cada estado tenga SU color, que es de lo que se trata todo esto.
        for clase, color in COLORES.items():
            revisar(f"el color de '{clase}'", pag.evaluate(
                "c => getComputedStyle(document.querySelector('.correo.' + c)).borderLeftColor",
                clase), color)

        revisar("la que espera lo dice",
                pag.evaluate("() => document.querySelector('.correo.espera .baj').innerText"
                             ".includes('te está esperando')"), True)
        revisar("la que falló cuenta el motivo",
                pag.evaluate("() => document.querySelector('.correo.fallada .baj').innerText"
                             ".includes('" + FALLA + "')"), True)
        pag.screenshot(path=str(SALIDA / "sesiones_semaforo.png"))

        # Abrir la conversación que falló limpia la marca: ya la viste.
        pag.evaluate("() => { falladas = {}; guardar(); }")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_semaforo.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
