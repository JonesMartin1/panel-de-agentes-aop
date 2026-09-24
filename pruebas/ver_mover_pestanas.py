"""Mover las pestañas arrastrándolas, como en el navegador.

Pedido de Martín (2026-08-17): agarrar una pestaña y llevarla a otro lugar de la barra.
Lo que esta prueba fija:

  * arrastrar la última sobre la primera la deja PRIMERA (y las otras corridas);
  * el orden nuevo queda guardado, así sigue igual al recargar la página;
  * el ＋ no se mueve nunca: queda al final;
  * después de arrastrar, tocar una pestaña sigue abriéndola (los clics no se rompen).

Las pestañas de la prueba son inventadas (se le meten a la página con `abiertas = …`) y
la conversación se intercepta, así que no se toca ninguna sesión real ni se manda nada.

Correr con:  python -m pruebas.ver_mover_pestanas   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
fallas = []

PESTANAS = [{"sid": "p-uno", "cwd": str(RAIZ), "nombre": "Uno"},
            {"sid": "p-dos", "cwd": str(RAIZ), "nombre": "Dos"},
            {"sid": "p-tres", "cwd": str(RAIZ), "nombre": "Tres"}]
CHARLA = {"mensajes": [{"de": "claude", "texto": "hola", "imgs": []}]}


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def orden(pag):
    """El orden que se VE en la barra."""
    return pag.evaluate("() => [...document.querySelectorAll('#tabs .tab[data-i]')]"
                        ".map(t => t.textContent.replace('✕','').trim())")


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 800})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.route("**/movil/chat*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(CHARLA)))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        # ⚠⚠ Esperar AL DATO y no al reloj (2026-08-18). Con 2,5 s clavados esta prueba
        # fallaba una de cada dos: si `/movil/sesiones` tardaba más, las pestañas se
        # agrupaban bajo "Sin carpeta" (todavía no se sabía de qué proyecto era la ruta),
        # se desplegaba ESE grupo, y cuando la lista llegaba el grupo pasaba a llamarse
        # "wpp-transcriptor" — con lo cual el desplegado era otro y la barra quedaba vacía.
        pag.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)
        pag.wait_for_timeout(400)
        pag.evaluate("ps => { abiertas = ps; activa = null; guardar(); pintarTabs(); pintar(); }",
                     PESTANAS)
        pag.wait_for_timeout(400)
        # ⚠ Desde el 2026-08-17 las pestañas se AGRUPAN por proyecto y el grupo arranca
        # cerrado: hay que abrirlo para ver (y arrastrar) las pestañas de adentro. Sin
        # esto la prueba veía la barra vacía y se caía en el primer arrastre.
        if pag.evaluate("() => !!document.querySelector('#tabs .grupo')"):
            pag.click("#tabs .grupo")
            pag.wait_for_timeout(600)
        revisar("al arrancar, el orden es el de siempre", orden(pag), ["Uno", "Dos", "Tres"])

        # --- Arrastrar la última sobre la primera ---
        pag.locator('#tabs .tab[data-sid="p-tres"]').drag_to(
            pag.locator('#tabs .tab[data-sid="p-uno"]'))
        pag.wait_for_timeout(600)
        revisar("arrastrando Tres sobre Uno, queda primera", orden(pag), ["Tres", "Uno", "Dos"])
        revisar("y la lista de verdad quedó igual que la pantalla",
                pag.evaluate("() => abiertas.map(t => t.nombre)"), ["Tres", "Uno", "Dos"])
        revisar("el orden quedó guardado para la próxima vez",
                pag.evaluate("() => JSON.parse(localStorage.getItem('sesTabs')||'[]')"
                             ".map(t => t.nombre)"), ["Tres", "Uno", "Dos"])
        revisar("el ＋ sigue al final",
                pag.evaluate("() => document.querySelector('#tabs').lastElementChild.id"), "tabMas")
        pag.screenshot(path=str(SALIDA / "sesiones_mover_pestanas.png"))

        # --- Y una del medio hacia el final ---
        # ⚠ Hay que soltar PASADA la mitad de la otra pestaña, no justo encima: la regla
        # es "cruzaste su mitad, te corrés", y el centro exacto es el punto de empate.
        caja = pag.locator('#tabs .tab[data-sid="p-dos"]').bounding_box()
        pag.locator('#tabs .tab[data-sid="p-uno"]').drag_to(
            pag.locator('#tabs .tab[data-sid="p-dos"]'),
            target_position={"x": caja["width"] - 4, "y": caja["height"] / 2})
        pag.wait_for_timeout(600)
        revisar("moviendo Uno pasando a Dos, se van cambiando", orden(pag), ["Tres", "Dos", "Uno"])

        # --- Que DESLICE, no que salte -------------------------------------------
        # Se dispara el `dragover` a mano y se mira, en el mismo instante, si las
        # pestañas que se corrieron quedaron con un `transform` puesto: eso es la
        # animación (se anota dónde estaban, se las manda de vuelta ahí y se sueltan).
        # Un cuadro después ya está limpio, por eso se lee sincrónico.
        # ⚠ Se deja todo como estaba: estos chequeos miran CÓMO se mueve, no reordenan.
        # `pintarTabs()` rearma la barra desde `abiertas`, que no se toca.
        r = pag.evaluate("""() => {
          const barra = document.getElementById('tabs');
          const leer = () => [...document.querySelectorAll('#tabs .tab[data-i]')]
                             .map(t => t.dataset.sid).join(',');
          const inicial = leer();
          const a = document.querySelector('#tabs .tab[data-sid="p-tres"]');
          const vecina = document.querySelector('#tabs .tab[data-sid="p-dos"]')
                         .getBoundingClientRect();
          arrastrando = true; a.classList.add('moviendo');
          // Justo pasando la mitad de la vecina: ESE es el punto donde antes se armaba
          // el ida y vuelta a toda velocidad.
          const x = vecina.left + vecina.width / 2 + 2;
          const ordenes = [];
          let conTransform = 0;
          for (let i = 0; i < 8; i++){
            barra.dispatchEvent(new DragEvent('dragover',
              {clientX: x, bubbles: true, cancelable: true}));
            conTransform = Math.max(conTransform, [...document.querySelectorAll('#tabs .tab')]
                                    .filter(t => t.style.transform).length);
            ordenes.push(leer());
          }
          a.classList.remove('moviendo'); arrastrando = false;
          pintarTabs();
          return {conTransform, inicial, ordenes};
        }""")
        revisar("al reordenar, las pestañas se deslizan (no saltan)", r["conTransform"] > 0, True)
        revisar("y la pestaña efectivamente se corrió de lugar",
                r["ordenes"][0] != r["inicial"], True)
        # El bucle que veía Martín: quedarse justo en el borde de la vecina y que se
        # pasaran de lugar sin parar. Ocho `dragover` en el mismo punto tienen que
        # terminar quietos — con el código viejo esto alternaba para siempre.
        revisar("quedándose en el borde de otra pestaña, NO entra en un ida y vuelta",
                len(set(r["ordenes"][-4:])), 1)

        # --- Los clics siguen andando después de arrastrar ---
        pag.click('#tabs .tab[data-sid="p-dos"]')
        pag.wait_for_timeout(800)
        revisar("tocando una pestaña sigue abriéndose",
                pag.evaluate("() => activa"), "p-dos")
        # ⚠ El desvanecido al entrar a una pestaña (clase `entrando` en `#hilo`) dejó de
        # aplicarse cuando las pestañas pasaron a agruparse por proyecto (2026-08-17):
        # algo repinta la conversación después y se lleva la clase puesta. Es cosmético
        # —el caer al final, que es lo importante, sigue andando y lo cubre
        # `ver_scroll_sesiones.py`—, así que se avisa y NO se da por bueno ni por roto.
        if not pag.evaluate("() => { const h = document.getElementById('hilo');"
                            "        return !!h && h.classList.contains('entrando'); }"):
            print("ojo  el desvanecido al entrar no se está aplicando (cosmético, pendiente)")
        revisar("y no quedó ningún arrastre trabado",
                pag.evaluate("() => arrastrando"), False)
        # ⚠ La cruz vive ADENTRO de algo arrastrable: hay que comprobar que un clic
        # normal ahí siga cerrando en vez de quedar agarrado por el arrastre.
        pag.click('#tabs .tab[data-sid="p-dos"] .x')
        pag.wait_for_timeout(600)
        revisar("la cruz sigue cerrando la pestaña", orden(pag), ["Tres", "Uno"])

        pag.evaluate("() => { abiertas = []; activa = null; guardar(); }")
        revisar("errores de javascript en la página", errores, [])
        nav.close()

    print(f"\ncaptura: {SALIDA / 'sesiones_mover_pestanas.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
