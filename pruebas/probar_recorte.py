"""Prueba del recorte de imagenes de la pizarra (pedido de Martin, 2026-08-17).

Recortar NO toca el archivo: guarda {x1,y1,x2,y2} en fracciones de la imagen
original y dibuja la imagen agrandada con un clipPath encima. Aca se prueba que
el numero que queda guardado sea el que se arrastro, que el dibujo quede con la
geometria correcta, que "Toda la imagen" y "Cancelar" hagan lo suyo, y que el
deshacer devuelva el recorte anterior.

Deja la pizarra como estaba: crea su propia imagen de prueba y la borra al final.

    python -m pruebas.probar_recorte
"""

import base64
import io
import sys

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

from app.rutas import RESULTADOS

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
CAJA = {"x1": 20, "y1": 20, "x2": 40, "y2": 35}   # en unidades de escena (0-100)
fallas = []


def revisar(que, obtenido, esperado, tolerancia=None):
    if tolerancia is None:
        ok = obtenido == esperado
    else:
        ok = all(abs(a - b) <= tolerancia for a, b in zip(obtenido, esperado))
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido}" +
          ("" if ok else f"  (esperaba {esperado})"))
    if not ok:
        fallas.append(que)


def imagen_de_prueba():
    """Mitad izquierda roja, mitad derecha azul: recortando se ve cual quedo."""
    im = Image.new("RGB", (200, 100), (220, 60, 60))
    im.paste((60, 90, 220), (100, 0, 200, 100))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def esquina(pg, i):
    """Centro (en coordenadas del navegador) de la esquina i del recorte."""
    caja = pg.locator(".recorte-esq").nth(i).bounding_box()
    return caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2


def arrastrar(pg, desde, hasta):
    pg.mouse.move(*desde)
    pg.mouse.down()
    pg.mouse.move(*hasta, steps=12)
    pg.mouse.up()
    pg.wait_for_timeout(250)


def recorte_de(pg, iid):
    return pg.evaluate("id => { const it = estado.items.find(i => i.id === id);"
                       "        const r = it.recorte || {};"
                       "        return [r.x1 || 0, r.y1 || 0, r.x2 == null ? 1 : r.x2,"
                       "                r.y2 == null ? 1 : r.y2]; }", iid)


def caja_de(pg, iid):
    return pg.evaluate("id => { const i = estado.items.find(x => x.id === id);"
                       "        return [i.x1, i.y1, i.x2, i.y2]; }", iid)


def main():
    subida = requests.post(BASE + "/pizarra/imagen",
                           json={"datos": imagen_de_prueba()}, timeout=10).json()
    if not subida.get("ok"):
        raise SystemExit("no se pudo subir la imagen de prueba: %s" % subida)
    archivo = subida["archivo"]
    item = requests.post(BASE + "/pizarra/agregar",
                         json=dict(tipo="imagen", archivo=archivo, **CAJA),
                         timeout=10).json()
    iid = item["id"]
    errores = []
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pg = navegador.new_page(viewport={"width": 1400, "height": 800})
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(BASE + "/pizarra")
            pg.wait_for_timeout(2500)

            # ⚠ La caja de la imagen NO es la que se mando: al cargar el tablero,
            # ajustarImagenes() le corrige el ALTO para que la foto respete su
            # proporcion real en ESTA pantalla (las unidades del tablero no son
            # cuadradas). Asi que lo esperado se calcula de la caja DE VERDAD.
            caja0 = caja_de(pg, iid)
            media = [caja0[0] + (caja0[2] - caja0[0]) / 2, caja0[1], caja0[2], caja0[3]]
            print("caja real tras el ajuste de proporcion:", [round(v, 2) for v in caja0])

            # --- Entrar al recorte por la tijera de la barra -------------------
            pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }", iid)
            pg.wait_for_timeout(300)
            revisar("tijera prendida con una imagen seleccionada",
                    pg.evaluate("!document.getElementById('btnRecortar').classList.contains('apagado')"),
                    True)
            pg.click("#btnRecortar")
            pg.wait_for_timeout(400)
            revisar("hay overlay de recorte", pg.locator(".recorte-capa").count(), 1)
            revisar("cuatro esquinas para agarrar", pg.locator(".recorte-esq").count(), 4)
            revisar("barra de recorte visible",
                    pg.evaluate("document.getElementById('barraRecorte').classList.contains('abierto')"), True)
            # ⚠ El panel se muestra por CLASE (.visible), no por style.display: lo
            # cambio la sesion de interfaz el 2026-08-17 porque en el telefono un
            # display puesto a mano le gana a la hoja de estilos.
            revisar("propiedades escondidas mientras se recorta",
                    pg.evaluate("document.getElementById('panelProps')"
                                ".classList.contains('visible')"), False)
            revisar("la imagen de verdad se esconde",
                    pg.locator(".forma-wrap.recorte-oculto").count(), 1)

            # --- Arrastrar la esquina de arriba-izquierda hasta la mitad -------
            # El paso se mide del DOM (distancia entre las dos esquinas de arriba),
            # asi la prueba no depende del zoom ni de donde este la camara.
            nw, ne = esquina(pg, 0), esquina(pg, 1)
            ancho = ne[0] - nw[0]
            arrastrar(pg, nw, (nw[0] + ancho / 2, nw[1]))
            pg.click('#barraRecorte button.ok')
            pg.wait_for_timeout(1200)

            revisar("recorte guardado = mitad derecha", recorte_de(pg, iid), [0.5, 0, 1, 1], 0.02)
            revisar("la caja se achico a la mitad derecha", caja_de(pg, iid), media, 0.4)
            revisar("el overlay se fue", pg.locator(".recorte-capa").count(), 0)
            revisar("la imagen volvio a mostrarse",
                    pg.locator(".forma-wrap.recorte-oculto").count(), 0)

            # La imagen dibujada tiene que ser el DOBLE de ancha que su recuadro:
            # se ve la mitad, asi que la entera mide el doble.
            proporcion = pg.evaluate(
                """id => {
                    const g = document.querySelector('.forma-wrap[data-id="'+id+'"]');
                    const im = g.querySelector('image'), cl = g.querySelector('clipPath rect');
                    return [ +im.getAttribute('width') / +cl.getAttribute('width'),
                             +im.getAttribute('height') / +cl.getAttribute('height') ];
                }""", iid)
            revisar("la imagen se dibuja 2x de ancho y 1x de alto", proporcion, [2, 1], 0.05)
            pg.screenshot(path=str(RESULTADOS.parent / "pruebas" / "recorte_hecho.png"))

            # --- Deshacer devuelve el recorte anterior -------------------------
            pg.click("#btnDeshacer")
            pg.wait_for_timeout(1200)
            revisar("deshacer vuelve a la imagen entera", recorte_de(pg, iid), [0, 0, 1, 1], 0.02)
            revisar("deshacer vuelve la caja", caja_de(pg, iid), caja0, 0.4)

            # --- Cancelar no toca nada ----------------------------------------
            pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }", iid)
            pg.click("#btnRecortar")
            pg.wait_for_timeout(400)
            nw = esquina(pg, 0)
            arrastrar(pg, nw, (nw[0] + 60, nw[1] + 30))
            pg.click('#barraRecorte button:text("Cancelar")')
            pg.wait_for_timeout(800)
            revisar("cancelar deja el recorte como estaba", recorte_de(pg, iid), [0, 0, 1, 1], 0.02)
            revisar("cancelar deja la caja como estaba", caja_de(pg, iid), caja0, 0.4)

            # --- "Toda la imagen" saca un recorte viejo ------------------------
            pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion(); }", iid)
            pg.click("#btnRecortar")
            pg.wait_for_timeout(400)
            nw, ne = esquina(pg, 0), esquina(pg, 1)
            arrastrar(pg, nw, (nw[0] + (ne[0] - nw[0]) / 2, nw[1]))
            pg.click('#barraRecorte button:text("Toda la imagen")')
            pg.wait_for_timeout(300)
            pg.click('#barraRecorte button.ok')
            pg.wait_for_timeout(1000)
            revisar('"toda la imagen" vuelve al original', recorte_de(pg, iid), [0, 0, 1, 1], 0.02)

            # --- Imagen ROTADA: no puede saltar de lugar al confirmar ----------
            # El dibujo gira alrededor del centro de la caja, y al recortar el
            # centro se mueve: si no se corrige, la imagen aparece en otro lado
            # del que se veia. Se compara donde estaba el centro del recorte en
            # PANTALLA contra donde queda el centro de la imagen ya recortada.
            requests.put(BASE + "/pizarra/item/%d" % iid, json={"angulo": 30}, timeout=5)
            pg.evaluate("() => { ultimoEstadoCrudo=''; return refrescar(); }")
            pg.wait_for_timeout(900)
            pg.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion();"
                        "        entrarRecorte(); }", iid)
            pg.wait_for_timeout(300)
            antes = pg.evaluate("""() => {
                const rc = recorteEnCurso, e = rc.entera;
                rc.sel = {x1:e.x + e.w*0.4, y1:e.y + e.h*0.15,
                          x2:e.x + e.w*0.9, y2:e.y + e.h*0.8};
                dibujarRecorte();
                const c = {x:(rc.sel.x1+rc.sel.x2)/2, y:(rc.sel.y1+rc.sel.y2)/2};
                const p = rotarPx(PX(c.x), PY(c.y), PX(rc.centro.x), PY(rc.centro.y), rc.angulo);
                return [p.x, p.y];
            }""")
            pg.click('#barraRecorte button.ok')
            pg.wait_for_timeout(1200)
            despues = pg.evaluate("""id => {
                const it = estado.items.find(i => i.id === id);
                return [PX((it.x1+it.x2)/2), PY((it.y1+it.y2)/2)];
            }""", iid)
            revisar("imagen rotada: el recorte queda donde se veia", despues, antes, 1.0)
            requests.put(BASE + "/pizarra/item/%d" % iid,
                         json={"angulo": 0, "recorte": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                               **CAJA}, timeout=5)

            # --- Y lo mismo con el dedo, en pantalla de telefono ---------------
            movil = navegador.new_page(viewport={"width": 390, "height": 844},
                                       device_scale_factor=2, is_mobile=True, has_touch=True)
            movil.on("pageerror", lambda e: errores.append("movil: " + str(e)))
            movil.goto(BASE + "/pizarra")
            movil.wait_for_timeout(2500)
            movil.evaluate("id => { seleccion.clear(); seleccion.add(id); pintarSeleccion();"
                           "        entrarRecorte(); }", iid)
            movil.wait_for_timeout(500)
            lado = movil.evaluate("+document.querySelector('.recorte-esq').getAttribute('width')")
            revisar("con el dedo las esquinas son grandes", lado, 22)
            movil.screenshot(path=str(RESULTADOS.parent / "pruebas" / "recorte_movil.png"))

            # Con el recorte a medias se tiene que ver el fantasma: lo que se va,
            # apagado; lo que queda, a pleno. Es lo que hace entendible la pantalla.
            movil.evaluate("""() => {
                const e = recorteEnCurso.entera;
                recorteEnCurso.sel = {x1:e.x + e.w*0.45, y1:e.y + e.h*0.2,
                                      x2:e.x + e.w*0.95, y2:e.y + e.h*0.9};
                dibujarRecorte();
            }""")
            movil.wait_for_timeout(300)
            movil.screenshot(path=str(RESULTADOS.parent / "pruebas" / "recorte_movil_medio.png"))
            movil.evaluate("salirRecorte(false)")

            navegador.close()
    finally:
        requests.delete(BASE + "/pizarra/item/%d" % iid, timeout=5)
        try:
            (RESULTADOS / "pizarra_imagenes" / archivo).unlink()
        except OSError:
            pass

    revisar("sin errores de JavaScript", errores, [])
    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
