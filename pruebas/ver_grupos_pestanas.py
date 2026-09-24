"""Las pestañas de conversaciones, AGRUPADAS POR PROYECTO.

Pedido de Martín (2026-08-17), mirando la barra de arriba de `/sesiones`: *"¿se te ocurre
alguna manera de poder ordenar esto por proyectos? Cada chat sea un proyecto, el cual yo
pueda cerrar también, y cuando yo apriete sobre el proyecto, pueda desplegarlo o traerlo
de vuelta"*. O sea los grupos de pestañas del navegador: una pastilla por proyecto, con
cuántas charlas tiene adentro, que se pliega y se despliega, y cuya ✕ las cierra a todas.

⚠ No toca NADA real: las pestañas de la compu viven solo en el `localStorage` del
navegador (no hay POST al servidor, a diferencia del celular), la conversación se
intercepta con `page.route`, y al terminar se deja la barra como estaba.

Correr con:  python -m pruebas.ver_grupos_pestanas   (con el panel prendido)
"""
import json
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


CHARLA = {"mensajes": [{"de": "yo", "texto": "hola"},
                       {"de": "claude", "texto": "hola, ¿en qué andamos?"}],
          "nombre": "de mentira", "viva": False}


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        # La conversación es inventada: abrir una pestaña no va a leer nada de verdad.
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2500)
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)

        # ⚠ Las pestañas se arman con conversaciones DE VERDAD (ids y carpetas reales):
        # el grupo sale de `proyectoDe()`, que compara la ruta contra los proyectos que
        # conoce el panel. Con datos inventados caerían todas en "Sin carpeta" y la
        # prueba no probaría el agrupado.
        armado = pag.evaluate("""() => {
          const con = datos.proyectos.filter(p => p.sesiones.length >= 2);
          if (con.length < 2) return null;
          const [a, b] = con;
          abiertas = [
            {sid: a.sesiones[0].id, cwd: a.cwd, nombre: 'A uno'},
            {sid: b.sesiones[0].id, cwd: b.cwd, nombre: 'B uno'},
            {sid: a.sesiones[1].id, cwd: a.cwd, nombre: 'A dos'},
          ];
          activa = null; grupoAbierto = ''; pendientes = {}; falladas = {};
          guardar(); pintarTabs();
          return {a: a.proyecto, b: b.proyecto, sidA: a.sesiones[0].id};
        }""")
        if not armado:
            print("MAL  hacen falta dos proyectos con dos conversaciones cada uno")
            fallas.append("no había con qué armar la prueba")
            nav.close()
            return
        pa, pb = armado["a"], armado["b"]
        pill = lambda n: '#tabs .grupo[data-grupo="' + n + '"]'
        texto = lambda sel: pag.evaluate("s => (document.querySelector(s)||{}).textContent", sel)
        cuantos = lambda sel: pag.evaluate("s => document.querySelectorAll(s).length", sel)

        # --- Una pastilla por proyecto, con la cuenta de adentro ---
        revisar("hay una pastilla por proyecto", cuantos("#tabs .grupo"), 2)
        revisar("la del primer proyecto dice cuántas tiene",
                pag.evaluate("s => document.querySelector(s + ' .cuantas').textContent", pill(pa)),
                "2")
        revisar("y la del segundo también",
                pag.evaluate("s => document.querySelector(s + ' .cuantas').textContent", pill(pb)),
                "1")
        # ⭐ Es el punto del pedido: plegadas, las charlas no ocupan lugar en la barra.
        revisar("plegadas, no se ve ninguna pestaña", cuantos("#tabs .tab[data-i]"), 0)
        revisar("el ＋ sigue estando igual", cuantos("#tabs #tabMas"), 1)
        pag.screenshot(path=str(SALIDA / "grupos_plegados.png"))

        # --- Tocar la pastilla la despliega ---
        pag.click(pill(pa))
        pag.wait_for_timeout(500)
        revisar("tocando el proyecto se despliegan SUS conversaciones",
                cuantos("#tabs .tab[data-i]"), 2)
        revisar("la pastilla queda marcada como abierta",
                pag.evaluate("s => document.querySelector(s).classList.contains('abierto')",
                             pill(pa)), True)
        revisar("y la flecha cambia",
                pag.evaluate("s => document.querySelector(s + ' .flecha').textContent", pill(pa)),
                "▾")
        # ⭐ La caja ABRAZA a la pastilla y a las charlas que muestra (pedido de Martín,
        # 2026-08-18: "me gustaría que esta pastilla pueda abrazar a las sesiones que
        # muestra"), como los grupos de pestañas de Chrome.
        abrazo = pag.evaluate("""s => {
          const c = document.getElementById('abrazo').getBoundingClientRect();
          const g = document.querySelector(s).getBoundingClientRect();
          const ts = [...document.querySelectorAll('#tabs .tab[data-i]')]
                       .map(t => t.getBoundingClientRect());
          const otras = [...document.querySelectorAll('#tabs .grupo')]
                       .filter(x => !x.classList.contains('abierto'))
                       .map(x => x.getBoundingClientRect());
          return {ve: getComputedStyle(document.getElementById('abrazo')).display !== 'none',
                  pastilla: g.left > c.left && g.right < c.right,
                  charlas: ts.every(t => t.left > c.left && t.right < c.right),
                  ajenas: otras.every(o => o.right < c.left || o.left > c.right)};
        }""", pill(pa))
        revisar("la caja del grupo abraza a la pastilla y a sus charlas",
                [abrazo["ve"], abrazo["pastilla"], abrazo["charlas"]], [True, True, True])
        revisar("y no se lleva puesta a ninguna pastilla ajena", abrazo["ajenas"], True)
        pag.screenshot(path=str(SALIDA / "grupos_desplegado.png"))

        # --- Se ve UNO SOLO a la vez: abrir otro pliega el anterior ---
        pag.click(pill(pb))
        pag.wait_for_timeout(500)
        revisar("abrir otro proyecto pliega el anterior", cuantos("#tabs .tab[data-i]"), 1)
        # ⚠ Se le sacan el ✕ y el puntito: una conversación VIVA lleva un ● adelante, así
        # que comparar el texto pelado hacía fallar la prueba según lo que estuviera
        # corriendo en la máquina en ese momento — de nuevo, no medir contra un mundo que
        # se mueve.
        revisar("y la que se ve es la del proyecto que tocaste",
                texto("#tabs .tab[data-i]").replace("✕", "").replace("●", "").strip(), "B uno")

        # --- Volver a tocarlo lo pliega ---
        pag.click(pill(pb))
        pag.wait_for_timeout(500)
        revisar("tocarlo de nuevo lo pliega", cuantos("#tabs .tab[data-i]"), 0)
        revisar("sin nada desplegado, la caja no abraza el aire",
                pag.evaluate("() => getComputedStyle(document.getElementById('abrazo'))"
                             ".display"), "none")

        # --- El grupo de la charla que estás LEYENDO se despliega solo ---
        pag.evaluate("s => irTab(s)", armado["sidA"])
        pag.wait_for_timeout(900)
        revisar("entrando a una charla, su grupo se despliega solo",
                pag.evaluate("s => document.querySelector(s).classList.contains('abierto')",
                             pill(pa)), True)
        revisar("y la charla queda seleccionada", cuantos("#tabs .tab.sel"), 1)

        # ⭐ Plegar el grupo de la charla abierta la saca de la pantalla: si no, quedaría
        # la conversación a la vista sin ninguna pestaña que la muestre.
        pag.click(pill(pa))
        pag.wait_for_timeout(900)
        revisar("plegar el grupo de la charla abierta te devuelve a la bandeja",
                pag.evaluate("() => activa"), None)

        # --- El semáforo del grupo plegado ---
        # Plegado tiene que seguir avisando: si una de adentro te contestó, la pastilla se
        # pone verde. Sin esto, esconder el grupo esconde justo lo que hay que saber.
        pag.evaluate("""s => { pendientes[s] = true; grupoAbierto = ''; pintarTabs(); }""",
                     armado["sidA"])
        pag.wait_for_timeout(400)
        revisar("plegado, el grupo avisa que adentro alguna te espera",
                pag.evaluate("s => document.querySelector(s).classList.contains('espera')",
                             pill(pa)), True)
        revisar("con su bolita", cuantos(pill(pa) + " .bola"), 1)
        pag.screenshot(path=str(SALIDA / "grupos_semaforo.png"))
        pag.evaluate("() => { pendientes = {}; guardar(); pintarTabs(); }")

        # --- La ✕ de la pastilla cierra TODAS las de ese proyecto ---
        pag.click(pill(pa) + " .x")
        pag.wait_for_timeout(900)
        revisar("la ✕ del proyecto cierra todas sus charlas",
                pag.evaluate("() => abiertas.length"), 1)
        revisar("y deja las del otro proyecto donde estaban",
                pag.evaluate("() => abiertas[0].nombre"), "B uno")
        revisar("queda una sola pastilla", cuantos("#tabs .grupo"), 1)

        # --- ⭐ Mover las pastillas: cambia el orden de los proyectos ---
        # ⚠ El arrastre se dispara a mano con eventos `drag*`. El arrastre NATIVO del
        # navegador no se puede simular de forma confiable desde Playwright, y lo que hay
        # que probar es nuestro código, que vive justo en esos tres manejadores.
        tres = pag.evaluate("""() => {
          const con = datos.proyectos.filter(p => p.sesiones.length >= 1);
          if (con.length < 3) return null;
          const [a, b, c] = con;
          abiertas = [
            {sid: a.sesiones[0].id, cwd: a.cwd, nombre: 'A uno'},
            {sid: b.sesiones[0].id, cwd: b.cwd, nombre: 'B uno'},
            {sid: c.sesiones[0].id, cwd: c.cwd, nombre: 'C uno'},
          ];
          activa = null; grupoAbierto = a.proyecto; pendientes = {}; falladas = {};
          guardar(); pintarTabs();
          return [a.proyecto, b.proyecto, c.proyecto];
        }""")
        if not tres:
            print("  (salteado: hacen falta tres proyectos con conversaciones)")
        else:
            revisar("tres proyectos, tres pastillas", cuantos("#tabs .grupo"), 3)
            # El primero está desplegado: su pestaña tiene que viajar con la pastilla.
            orden = pag.evaluate("""nombre => {
              const tabs = document.getElementById('tabs');
              const el = tabs.querySelector('.grupo[data-grupo="' + nombre + '"]');
              const dt = new DataTransfer();
              el.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
              const x = document.getElementById('tabMas').getBoundingClientRect().left + 2;
              tabs.dispatchEvent(new DragEvent('dragover',
                    {bubbles:true, cancelable:true, clientX:x, dataTransfer:dt}));
              el.dispatchEvent(new DragEvent('dragend', {bubbles:true, dataTransfer:dt}));
              return [...tabs.querySelectorAll('.grupo')].map(g => g.dataset.grupo);
            }""", tres[0])
            revisar("arrastrando la pastilla al final, el proyecto queda último",
                    orden, [tres[1], tres[2], tres[0]])
            revisar("y la lista real quedó en ese mismo orden",
                    pag.evaluate("() => abiertas.map(t => t.nombre)"),
                    ["B uno", "C uno", "A uno"])
            # ⭐ Lo que más se puede romper: el grupo desplegado se parte y sus charlas
            # quedan colgando del proyecto de al lado.
            revisar("la charla desplegada viajó pegada a su pastilla",
                    pag.evaluate("""nombre => {
                      const p = document.querySelector('#tabs .grupo[data-grupo="' + nombre + '"]');
                      const s = p.nextElementSibling;
                      return !!s && s.classList.contains('tab') && s.textContent.includes('A uno');
                    }""", tres[0]), True)
            pag.screenshot(path=str(SALIDA / "grupos_movidos.png"))

        # Dejar la barra como estaba: esto corre contra el panel de verdad.
        pag.evaluate("""() => { abiertas = []; activa = null; grupoAbierto = '';
                                pendientes = {}; falladas = {}; guardar(); pintarTabs(); }""")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print()
    print("captura:", SALIDA / "grupos_desplegado.png")
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas) if fallas else "TODO BIEN")


if __name__ == "__main__":
    main()
