"""Copiar deja las DOS caras de lo mismo en el portapapeles
(pedido de Martin, 2026-08-17: "cuando hago la copia en la pizarra me gustaria
que se copien los objetos, y si quiero trasladar esto a otro lugar, que se copie
como PNG").

Una sola copia lleva dos formatos: los OBJETOS como texto (con una marca propia)
y la FOTO como imagen. Cada destino agarra el que entiende — la pizarra pega los
objetos editables, WhatsApp o Word pegan el dibujo. Es lo que hacen Excalidraw y
Figma, y reemplaza al truco de adivinar "esta imagen es mia" por el tamaño del
archivo, que se rompia en cuanto el PNG salia distinto por un byte.

Deja la pizarra como estaba: crea sus objetos y borra todo al final.

    python -m pruebas.probar_copiar_imagen
"""

import sys
import time

import requests
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
fallas = []


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}" + (f": {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def mirar_portapapeles(pg):
    """Que hay en el portapapeles del sistema, ahora."""
    return pg.evaluate("""async () => {
        let tipos = [];
        try { tipos = (await navigator.clipboard.read()).flatMap(i => i.types); } catch (e) {}
        let texto = '';
        try { texto = await navigator.clipboard.readText(); } catch (e) {}
        return {tipos: tipos.sort(), texto: texto};
    }""")


def esperar_copia(pg, segundos=30):
    """Espera a que la copia este completa en el portapapeles.
    ⚠ No se usa wait_for_function con una funcion async: devuelve una PROMESA, que
    siempre es 'verdadera', asi que se cumplia al instante y se leia el
    portapapeles de la corrida anterior. Se espera desde Python, que si aguarda."""
    arranque = time.time()
    while time.time() - arranque < segundos:
        info = mirar_portapapeles(pg)
        if "image/png" in info["tipos"] and info["texto"].startswith("pizarra-ia/objetos:"):
            return time.time() - arranque, info
        pg.wait_for_timeout(150)
    return None, mirar_portapapeles(pg)


def esperar_nuevos(pg, antes, segundos=8):
    limite = time.time() + segundos
    while time.time() < limite:
        nuevas = pg.evaluate("ids => estado.items.filter(i => !ids.includes(i.id))", antes)
        if nuevas:
            return nuevas
        pg.wait_for_timeout(200)
    return []


def main():
    rect = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "rectangulo", "x1": 30, "y1": 40, "x2": 42, "y2": 50},
                         timeout=5).json()
    nota = requests.post(BASE + "/pizarra/agregar",
                         json={"tipo": "nota", "texto": "copiame", "x": 50, "y": 45},
                         timeout=5).json()
    fijos = [rect["id"], nota["id"]]
    errores, creados = [], []
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            ctx = nav.new_context(viewport={"width": 1400, "height": 900},
                                  permissions=["clipboard-read", "clipboard-write"])
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            # --- Ctrl+C con dos objetos seleccionados -------------------------
            pg.evaluate("ids => { seleccion = new Set(ids); pintarSeleccion(); }", fijos)
            pg.wait_for_timeout(300)
            # ⚠ Vaciar el portapapeles ANTES: si no, quedan restos de la corrida
            # anterior y la espera se cumple sola sin haber copiado nada.
            pg.evaluate("() => navigator.clipboard.writeText('')")
            pg.keyboard.press("Control+c")
            tardo, info = esperar_copia(pg)
            revisar("la copia entra en el portapapeles rapido",
                    tardo is not None and tardo < 8,
                    f"{tardo:.1f} s" if tardo is not None else "no llego nunca")
            revisar("la copia lleva las dos caras: objetos y foto",
                    info["tipos"] == ["image/png", "text/plain"], str(info["tipos"]))
            revisar("el texto son los objetos, con su marca",
                    '"tipo":"rectangulo"' in info["texto"] and '"tipo":"nota"' in info["texto"],
                    info["texto"][:70] + "...")

            # --- Pegar ADENTRO: tienen que venir los objetos, no la foto -------
            antes = pg.evaluate("estado.items.map(i => i.id)")
            pg.keyboard.press("Control+v")
            nuevas = esperar_nuevos(pg, antes)
            creados += [i["id"] for i in nuevas]
            revisar("pegar adentro trae los OBJETOS, no la foto",
                    sorted(i["tipo"] for i in nuevas) == ["nota", "rectangulo"],
                    str([i["tipo"] for i in nuevas]))

            # --- Y en OTRA pestaña tambien, que es lo que la copia interna no podia --
            otra = ctx.new_page()
            otra.on("pageerror", lambda e: errores.append("otra: " + str(e)))
            otra.goto(BASE + "/pizarra")
            otra.wait_for_timeout(2500)
            revisar("en la otra pestaña no hay copia interna",
                    otra.evaluate("copiados.length") == 0)
            antes = otra.evaluate("estado.items.map(i => i.id)")
            otra.keyboard.press("Control+v")
            nuevas = esperar_nuevos(otra, antes)
            creados += [i["id"] for i in nuevas]
            revisar("y aun asi pega los objetos (viajan en el portapapeles)",
                    sorted(i["tipo"] for i in nuevas) == ["nota", "rectangulo"],
                    str([i["tipo"] for i in nuevas]))

            # --- Una imagen de AFUERA sigue entrando como imagen ---------------
            # Primero traer lo que pego la otra pestaña, o aparece como "nuevo".
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(1200)
            antes = pg.evaluate("estado.items.map(i => i.id)")
            pg.evaluate("""async () => {
                const c = document.createElement('canvas');
                c.width = 40; c.height = 30;
                const g = c.getContext('2d');
                g.fillStyle = '#ff8800'; g.fillRect(0, 0, 40, 30);
                const blob = await new Promise(r => c.toBlob(r, 'image/png'));
                const dt = new DataTransfer();
                dt.items.add(new File([blob], 'y.png', {type: 'image/png'}));
                document.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt,
                                                                    bubbles: true, cancelable: true}));
            }""")
            nuevas = esperar_nuevos(pg, antes)
            creados += [i["id"] for i in nuevas]
            revisar("una imagen de afuera sigue entrando como imagen",
                    len(nuevas) == 1 and nuevas[0]["tipo"] == "imagen",
                    str([i["tipo"] for i in nuevas]))

            # --- El boton 📋 hace lo mismo que Ctrl+C (es el del telefono) -----
            revisar("el boton de copiar existe en las Acciones",
                    pg.locator("#propsCopiarImg").count() == 1)
            revisar("y hace lo mismo que Ctrl+C",
                    "copiarSeleccion" in pg.evaluate(
                        "document.getElementById('propsCopiarImg').onclick.toString()"))

            nav.close()
    finally:
        for iid in creados + fijos:
            requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)

    revisar("sin errores de JavaScript", not errores, str(errores))
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
