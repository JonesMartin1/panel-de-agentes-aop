"""El ＋ de la barra de pestañas y el camino para arrancar una conversación.

Pedido de Martín (2026-08-17, en tres vueltas):

  1. que haya un ＋ en la barra de pestañas;
  2. que ese ＋ **lleve a "Todas"** — la bandeja con todas las conversaciones (lo dibujó
     con una flecha del botón a la carpeta "Todas");
  3. que desde ahí se pueda arrancar una charla nueva eligiendo la carpeta, y que cada
     carpeta muestre sus **últimas cinco** conversaciones para entrar a una que ya existe.

⚠ Solo abre pestañas y hace clics: NUNCA toca "Enviar", así que no arranca ningún
proceso `claude` ni escribe en ninguna sesión de verdad (entrar a una conversación
existente es leer su archivo, nada más).

Correr con:  python -m pruebas.ver_boton_nueva   (con el panel prendido)
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


def marcada(pag):
    return pag.evaluate("() => { const c = document.querySelector('.carpeta.sel');"
                        "        return c ? c.querySelector('.nom').textContent : null; }")


def titulo(pag):
    return pag.evaluate("() => (document.querySelector('#cuerpo .cabeza b')||{}).textContent")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.evaluate("() => { abiertas = []; activa = null; desplegada = '';"
                     "         guardar(); pintarTabs(); pintar(); }")
        pag.wait_for_timeout(400)

        revisar("con cero pestañas, el ＋ está igual",
                pag.evaluate("() => !!document.getElementById('tabMas')"), True)

        # --- 2) El ＋ lleva a "Todas", estés en la carpeta que estés ---
        proy = pag.evaluate("() => (datos.proyectos.find(p => p.sesiones.length)"
                            "        || datos.proyectos[0]).proyecto")
        pag.evaluate("p => irProyecto(p)", proy)
        pag.wait_for_timeout(400)
        pag.click("#tabMas")
        pag.wait_for_timeout(900)
        revisar("el ＋ te lleva a Todas (marcado a la izquierda)", marcada(pag), "Todas")
        revisar("y la bandeja que se ve es la de todas", titulo(pag), "Todas las conversaciones")
        revisar("el ＋ no abre ninguna pestaña por sí solo",
                pag.evaluate("() => abiertas.length"), 0)
        pag.screenshot(path=str(SALIDA / "sesiones_boton_nueva.png"))

        # --- El refresco de cada 20 s no te saca de Todas ---
        pag.evaluate("() => cargar()")
        pag.wait_for_timeout(1200)
        revisar("después de refrescar, seguís en Todas", marcada(pag), "Todas")

        # --- 3) Desde Todas se arranca una conversación eligiendo carpeta ---
        revisar("en Todas está la fila de empezar una conversación",
                pag.evaluate("() => !!document.querySelector('#cuerpo .correo[data-nueva]')"), True)
        pag.click("#cuerpo .correo[data-nueva]")
        pag.wait_for_timeout(900)
        revisar("se abre una pestaña sin carpeta todavía",
                pag.evaluate("() => (abiertas.find(t => t.sid===activa)||{}).cwd"), "")
        revisar("la caja de escribir está escondida hasta elegir",
                pag.evaluate("() => getComputedStyle(document.getElementById('caja')).display"),
                "none")
        revisar("se listan todas las carpetas",
                pag.evaluate("() => document.querySelectorAll('#cuerpo .correo').length"),
                pag.evaluate("() => datos.proyectos.length"))
        revisar("volviendo a apretar la fila no apila pestañas vacías",
                pag.evaluate("() => abiertas.filter(t => t.sid.startsWith('nueva-')).length"), 1)

        # --- El ▾ de una carpeta muestra sus últimas cinco ---
        conSesiones = pag.evaluate(
            "() => { const p = datos.proyectos.filter(x => x.sesiones.length)"
            "          .sort((a,b) => b.sesiones.length - a.sesiones.length)[0];"
            "        return {proy: p.proyecto, cuantas: Math.min(5, p.sesiones.length)}; }")
        pag.click(f'#cuerpo .despl[data-abrir="{conSesiones["proy"]}"]')
        pag.wait_for_timeout(700)
        revisar(f"el ▾ de {conSesiones['proy']} muestra sus últimas",
                pag.evaluate("() => document.querySelectorAll('#cuerpo .ult').length"),
                conSesiones["cuantas"])
        revisar("nunca más de cinco",
                pag.evaluate("() => document.querySelectorAll('#cuerpo .ult').length") <= 5, True)

        # --- Entrar a una de esas conversaciones: reemplaza la pestaña vacía ---
        sid = pag.evaluate("() => document.querySelector('#cuerpo .ult').dataset.sid")
        pag.click("#cuerpo .ult")
        pag.wait_for_timeout(1400)
        revisar("tocando una de las últimas, se abre esa conversación",
                pag.evaluate("() => activa"), sid)
        revisar("y no quedó ninguna pestaña vacía dando vueltas",
                pag.evaluate("() => abiertas.filter(t => t.sid.startsWith('nueva-')).length"), 0)

        # --- Y elegir una carpeta sí arranca una charla nueva ahí ---
        pag.click("#tabMas")
        pag.wait_for_timeout(700)
        pag.click("#cuerpo .correo[data-nueva]")
        pag.wait_for_timeout(800)
        elegido = pag.evaluate("() => document.querySelector('#cuerpo .correo .tit').textContent")
        pag.click("#cuerpo .correo .med")
        pag.wait_for_timeout(900)
        revisar("elegida la carpeta, la pestaña ya la tiene",
                pag.evaluate("() => !!(abiertas.find(t => t.sid===activa)||{}).cwd"), True)
        revisar("y ahora sí se puede escribir",
                pag.evaluate("() => getComputedStyle(document.getElementById('caja')).display"),
                "flex")
        revisar("con esa carpeta marcada", marcada(pag), elegido)

        # --- 4) La cruz de una pestaña también te devuelve a "Todas" ---
        pag.evaluate("() => irProyecto(datos.proyectos[0].proyecto)")
        pag.wait_for_timeout(500)
        revisar("estabas parado en una carpeta", marcada(pag) != "Todas", True)
        pag.click("#tabs .tab[data-i] .x")
        pag.wait_for_timeout(900)
        revisar("cerrando una pestaña, quedás en Todas", marcada(pag), "Todas")
        revisar("y viendo la bandeja de todas", titulo(pag), "Todas las conversaciones")
        revisar("sin ninguna pestaña activa", pag.evaluate("() => activa"), None)

        pag.evaluate("() => { abiertas = []; activa = null; guardar(); }")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_boton_nueva.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
