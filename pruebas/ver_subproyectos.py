"""Los subproyectos en las DOS pantallas, mirados en un navegador (2026-11-10).

Compañera de `probar_subproyectos.py` (que prueba el servidor). Acá se abre /sesiones y la
app del celular con datos de mentira y se mira:
  · que la carpeta con subproyectos se parta en grupos con su título, y que se plieguen;
  · que la carpeta sin subproyectos se vea con la lista de siempre (sin ningún título);
  · que el botón ⊞ de al lado del lápiz abra la elección y mande el pedido correcto;
  · que en la columna de la izquierda las charlas abiertas también se agrupen.

⚠ No escribe nada: todo pedido que no sea de lectura se contesta acá mismo y no llega al
panel. La app del celular se sirve desde el `panel.py` del disco (el panel prendido puede
tener una versión vieja en memoria), así se mira lo que de verdad está escrito.

Correr con:  python -m pruebas.ver_subproyectos   (con el panel prendido)
Deja capturas en pruebas/subproy_*.png.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import panel                                              # noqa: E402

BASE = "http://127.0.0.1:8750"
AQUI = Path(__file__).resolve().parent
AHORA = time.time()
fallas = []


def ses(i, nombre, sub=None, viva=False):
    s = {"id": f"subp-{i:04d}-0000-0000-000000000000", "nombre": nombre, "ts": AHORA - 60 * i,
         "ultimo": "vos", "viva": viva, "ocupada": False, "interactiva": False, "detalle": "x"}
    if sub:
        s["sub"] = sub
    return s


SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa", "beta"], "ocultas": []},
            "proyectos": [
                {"proyecto": "alfa", "cwd": "D:\\pruebas\\alfa", "vivo": False, "sesiones": [
                    ses(1, "charla uno", "Descalzo"), ses(2, "charla dos", "Migración"),
                    ses(3, "charla tres"), ses(4, "charla cuatro", "Descalzo")]},
                {"proyecto": "beta", "cwd": "D:\\pruebas\\beta", "vivo": False, "sesiones": [
                    ses(5, "charla cinco"), ses(6, "charla seis")]}]}


def revisar(nombre, obtenido, esperado=True):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def contexto(nav, ancho, alto, movil=False):
    ctx = nav.new_context(viewport={"width": ancho, "height": alto}, reduced_motion="reduce",
                          has_touch=movil, is_mobile=movil)
    mandados, errores = [], []

    def portero(r):
        camino = r.request.url.split(BASE, 1)[-1].split("?")[0]
        if camino == "/movil" and movil:
            return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=panel.MOVIL_HTML)
        if camino == "/movil/sesiones":
            cuerpo = SESIONES
        elif camino == "/movil/chat":
            # El ＋ de un subproyecto abre una charla: el hilo vacío viene con su lista.
            cuerpo = {"ok": True, "mensajes": []}
        elif r.request.method != "GET":
            if camino == "/movil/subproyecto":
                mandados.append(json.loads(r.request.post_data or "{}"))
            cuerpo = {"ok": True}
        elif camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
            cuerpo = {"ok": True}
        else:
            return r.continue_()
        return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e) + " | " + (e.stack or "")[:400]))
    pag.add_init_script("localStorage.clear();")
    return ctx, pag, mandados, errores


def compu(nav):
    print("\n--- La pantalla grande ---")
    ctx, pag, mandados, errores = contexto(nav, 1400, 900)
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=20000)
    pag.click("#carpetas .carpeta[data-proy='beta']")
    pag.wait_for_timeout(600)
    revisar("beta (sin subproyectos): ningún título de grupo",
            pag.locator("#cuerpo .subgrupo").count(), 0)
    revisar("beta: sus dos charlas en la lista", pag.locator("#cuerpo .correo[data-sid^='subp']").count(), 2)
    pag.screenshot(path=str(AQUI / "subproy_compu_beta.png"))
    pag.click("#carpetas .carpeta[data-proy='alfa']")
    pag.wait_for_timeout(600)
    titulos = pag.locator("#cuerpo .subgrupo .nom").all_inner_texts()
    revisar("alfa: los grupos, en orden y 'Sin subproyecto' al final",
            [t.strip().lower() for t in titulos], ["descalzo", "migración", "sin subproyecto"])
    pag.screenshot(path=str(AQUI / "subproy_compu_alfa.png"))
    # Plegar Descalzo: sus dos charlas se esconden, el resto sigue.
    pag.locator("#cuerpo .subgrupo").first.click()
    pag.wait_for_timeout(300)
    revisar("plegado Descalzo quedan 2 charlas a la vista",
            pag.locator("#cuerpo .correo[data-sid^='subp']").count(), 2)
    pag.locator("#cuerpo .subgrupo").first.click()
    pag.wait_for_timeout(300)
    revisar("desplegado vuelven las 4", pag.locator("#cuerpo .correo[data-sid^='subp']").count(), 4)
    # El ⊞ de la charla tres (sin subproyecto) → elegir Descalzo.
    fila = pag.locator("#cuerpo .correo[data-sid='subp-0003-0000-0000-000000000000']")
    fila.hover()
    fila.locator(".lapiz.subp").click()
    pag.wait_for_timeout(300)
    revisar("el ⊞ abre el menú", pag.locator("#menuTarjeta.abierto").count(), 1)
    opciones = pag.locator("#menuTarjeta .op").all_inner_texts()
    revisar("el menú ofrece los existentes y uno nuevo",
            [o.strip() for o in opciones], ["· Descalzo", "· Migración", "＋ Nuevo subproyecto…"])
    pag.screenshot(path=str(AQUI / "subproy_compu_menu.png"))
    pag.locator("#menuTarjeta .op[data-sub='Descalzo']").click()
    pag.wait_for_timeout(500)
    revisar("manda el pedido correcto", mandados[-1:] ,
            [{"sid": "subp-0003-0000-0000-000000000000", "subproyecto": "Descalzo"}])
    revisar("no se abrió la charla al tocar el ⊞",
            pag.locator("#cuerpo .correo[data-sid='subp-0003-0000-0000-000000000000']").count(), 1)
    # ⭐ Arrastrar (2026-11-11): la charla dos (Migración) se suelta sobre el título Descalzo.
    pag.wait_for_timeout(800)
    pag.locator("#cuerpo .correo[data-sid='subp-0002-0000-0000-000000000000']").drag_to(
        pag.locator("#cuerpo .subgrupo[data-g='Descalzo']"))
    pag.wait_for_timeout(500)
    revisar("arrastrar al título de otro grupo la cambia de subproyecto", mandados[-1:],
            [{"sid": "subp-0002-0000-0000-000000000000", "subproyecto": "Descalzo"}])
    pag.wait_for_timeout(800)
    # Y soltada en "Sin subproyecto" (sobre una charla de ese grupo) le saca el que tenía.
    pag.locator("#cuerpo .correo[data-sid='subp-0001-0000-0000-000000000000']").drag_to(
        pag.locator("#cuerpo .correo[data-g='']").first)
    pag.wait_for_timeout(500)
    revisar("soltada sobre una charla sin subproyecto le saca el suyo", mandados[-1:],
            [{"sid": "subp-0001-0000-0000-000000000000", "subproyecto": ""}])
    n = len(mandados)
    pag.wait_for_timeout(800)
    pag.locator("#cuerpo .correo[data-sid='subp-0004-0000-0000-000000000000']").drag_to(
        pag.locator("#cuerpo .subgrupo[data-g='Descalzo']"))
    pag.wait_for_timeout(500)
    revisar("soltarla en su mismo grupo no manda nada", len(mandados), n)
    # La columna de la izquierda: las charlas ABIERTAS de cada carpeta también se agrupan.
    # Se abren como pestañas sin entrar a ninguna, así la bandeja sigue a la vista.
    pag.evaluate("""() => { abiertas = [1, 2, 5].map(i => ({sid: 'subp-000' + i + '-0000-0000-000000000000',
                      cwd: i === 5 ? 'D:\\\\pruebas\\\\beta' : 'D:\\\\pruebas\\\\alfa', nombre: 'x', cerebro: ''}));
                      datos.proyectos.forEach(p => p.sesiones.forEach(s => {
                        if (s.id.startsWith('subp-0003')) s.sub = 'Descalzo'; }));
                      pintarCarpetas(); }""")
    pag.wait_for_timeout(400)
    revisar("izquierda: alfa agrupa sus abiertas",
            [t.strip().lower() for t in pag.locator("#carpetas .subgrupo .nom").all_inner_texts()],
            ["descalzo", "migración"])
    revisar("izquierda: beta muestra su abierta sin ningún título",
            pag.locator("#carpetas .subcarpeta[data-subsid^='subp-0005']").count(), 1)
    pag.screenshot(path=str(AQUI / "subproy_compu_izquierda.png"))
    # ⭐ El ＋ de un subproyecto (2026-11-11): abre una charla nueva que lleva el grupo anotado,
    # y cuando la charla nace con su id de verdad, se le asigna.
    pag.click("#carpetas .carpeta[data-proy='alfa']")
    pag.wait_for_timeout(600)
    revisar("el título 'Sin subproyecto' no lleva ＋",
            pag.locator("#cuerpo .subgrupo[data-g=''] .masSub").count(), 0)
    pag.locator("#cuerpo .subgrupo[data-g='Migración'] .masSub").click()
    pag.wait_for_timeout(500)
    nueva = pag.evaluate("() => abiertas.find(t => t.sid.startsWith('nueva-') && t.sub) || null")
    revisar("el ＋ abre una pestaña nueva con el subproyecto anotado",
            (nueva or {}).get("sub"), "Migración")
    revisar("y queda parada en ella", pag.evaluate("() => activa.startsWith('nueva-')"), True)
    pag.evaluate("""() => { const t = abiertas.find(t => t.sid.startsWith('nueva-') && t.sub);
                            mudarPestana(t, t.sid, 'subp-0099-0000-0000-000000000000'); }""")
    pag.wait_for_timeout(500)
    revisar("al nacer la charla se le asigna el subproyecto", mandados[-1:],
            [{"sid": "subp-0099-0000-0000-000000000000", "subproyecto": "Migración"}])
    revisar("y la pestaña ya no lo lleva anotado",
            pag.evaluate("() => abiertas.some(t => t.sub)"), False)

    # ⭐ Cada subproyecto a gusto (2026-11-11): fijarlo arriba, color, moverlo y renombrarlo.
    pag.click("#carpetas .carpeta[data-proy='alfa']")
    pag.wait_for_timeout(800)
    titulos = lambda: [t.strip().lower() for t in pag.locator("#cuerpo .subgrupo .nom").all_inner_texts()]
    revisar("de entrada, por movimiento reciente", titulos(), ["descalzo", "migración", "sin subproyecto"])
    revisar("'Sin subproyecto' no tiene menú ni se arrastra",
            [pag.locator("#cuerpo .subgrupo[data-g=''] .menuSub").count(),
             pag.locator("#cuerpo .subgrupo[data-g='']").get_attribute("draggable")], [0, None])
    pag.locator("#cuerpo .subgrupo[data-g='Migración']").click(button="right")
    pag.wait_for_timeout(300)
    revisar("el botón derecho del título abre su menú", pag.locator("#menuTarjeta.abierto").count(), 1)
    pag.screenshot(path=str(AQUI / "subproy_compu_menu_grupo.png"))
    pag.locator("#menuTarjeta [data-hace='fijar']").click()
    pag.wait_for_timeout(400)
    revisar("fijada, Migración pasa arriba", titulos(), ["migración", "descalzo", "sin subproyecto"])
    revisar("y lleva su 📌", pag.locator("#cuerpo .subgrupo[data-g='Migración'] .pinSub").count(), 1)
    revisar("la columna de la izquierda también la pone arriba",
            [t.strip().lower() for t in pag.locator("#carpetas .subgrupo .nom").all_inner_texts()][:1],
            ["migración"])
    pag.locator("#cuerpo .subgrupo[data-g='Migración'] .menuSub").click()
    pag.wait_for_timeout(300)
    pag.locator("#menuTarjeta .tono[data-tono='rosa']").click()
    pag.wait_for_timeout(300)
    revisar("el color se ve en el título (su puntito)",
            pag.locator("#cuerpo .subgrupo[data-g='Migración'] .ptoSub").count(), 1)
    revisar("y el menú queda abierto para probar otro", pag.locator("#menuTarjeta.abierto").count(), 1)
    pag.evaluate("() => cerrarMenuTarjeta()")
    revisar("queda guardado", pag.evaluate("() => JSON.parse(localStorage.getItem('sesSubAjustes'))"),
            {"alfa|Migración": {"fija": True, "color": "rosa"}})
    pag.locator("#cuerpo .subgrupo[data-g='Migración']").click(button="right")
    pag.wait_for_timeout(300)
    pag.locator("#menuTarjeta [data-hace='fijar']").click()
    pag.wait_for_timeout(400)
    revisar("soltada, vuelve a su lugar", titulos(), ["descalzo", "migración", "sin subproyecto"])
    # Moverla arrastrando el título: soltada en la mitad de arriba de Descalzo cae antes.
    pag.locator("#cuerpo .subgrupo[data-g='Migración']").drag_to(
        pag.locator("#cuerpo .subgrupo[data-g='Descalzo']"), target_position={"x": 20, "y": 1})
    pag.wait_for_timeout(400)
    revisar("arrastrada arriba de Descalzo, queda primera", titulos(),
            ["migración", "descalzo", "sin subproyecto"])
    revisar("el orden queda guardado", pag.evaluate("() => JSON.parse(localStorage.getItem('sesSubOrden'))"),
            {"alfa": ["Migración", "Descalzo"]})
    # Renombrarla: muda sus charlas en el servidor y se lleva color y lugar.
    pag.once("dialog", lambda d: d.accept("Mudanza"))
    pag.locator("#cuerpo .subgrupo[data-g='Migración']").click(button="right")
    pag.wait_for_timeout(300)
    pag.locator("#menuTarjeta [data-hace='nombre']").click()
    pag.wait_for_timeout(600)
    revisar("renombrar manda el nombre nuevo para su charla",
            {"sid": "subp-0002-0000-0000-000000000000", "subproyecto": "Mudanza"} in mandados, True)
    revisar("y se lleva el color y el lugar",
            pag.evaluate("() => [subAjustes['alfa|Mudanza'], subOrden.alfa]"),
            [{"color": "rosa"}, ["Mudanza", "Descalzo"]])

    # ⭐ La ✕ del «Volver a abrir» (2026-11-11): saca el aviso y las pestañas quedan cerradas.
    pag.evaluate("() => cerrarTodas()")
    pag.wait_for_timeout(300)
    revisar("después de cerrar todas aparece el «Volver a abrir» con su ✕",
            pag.locator("#tabVolver [data-olvidar]").count(), 1)
    pag.hover("#tabVolver")
    pag.locator("#tabVolver [data-olvidar]").click()
    pag.wait_for_timeout(400)
    revisar("la ✕ saca el aviso", pag.locator("#tabVolver").count(), 0)
    revisar("y no reabre ninguna pestaña", pag.evaluate("() => abiertas.length"), 0)
    revisar("queda guardado así (un F5 no las trae)",
            pag.evaluate("() => localStorage.getItem('sesTabs')"), "[]")
    revisar("sin errores de la página", errores, [])
    ctx.close()


def celu(nav):
    print("\n--- El celular ---")
    ctx, pag, mandados, errores = contexto(nav, 390, 844, movil=True)
    # ⚠ Con "domcontentloaded" se queda esperando para siempre en modo celular: alcanza con
    # que la página arranque y tenga sus funciones.
    pag.goto(BASE + "/movil", wait_until="commit")
    pag.wait_for_function("typeof elegirProyecto === 'function'", timeout=20000)
    pag.wait_for_timeout(1500)
    pag.evaluate("() => elegirProyecto('beta')")
    pag.wait_for_timeout(800)
    if pag.locator("#cuerpo .correo[data-sid^='subp']").count() == 0:
        # No arrancó en la bandeja: se va a la pestaña del más, que es donde vive.
        pag.evaluate("() => { activa = 'nueva'; elegirFirma = ''; pintarElegir(); }")
        pag.wait_for_timeout(800)
    revisar("beta (sin subproyectos): ningún título de grupo",
            pag.locator("#cuerpo .subgrupo").count(), 0)
    revisar("beta: sus dos charlas", pag.locator("#cuerpo .correo[data-sid^='subp']").count(), 2)
    pag.screenshot(path=str(AQUI / "subproy_celu_beta.png"))
    pag.evaluate("() => elegirProyecto('alfa')")
    pag.wait_for_timeout(800)
    titulos = pag.locator("#cuerpo .subgrupo .nom").all_inner_texts()
    revisar("alfa: los mismos grupos que la compu",
            [t.strip().lower() for t in titulos], ["descalzo", "migración", "sin subproyecto"])
    pag.screenshot(path=str(AQUI / "subproy_celu_alfa.png"))
    pag.locator("#cuerpo .subgrupo").first.click()
    pag.wait_for_timeout(400)
    revisar("plegado Descalzo quedan 2", pag.locator("#cuerpo .correo[data-sid^='subp']").count(), 2)
    pag.locator("#cuerpo .subgrupo").first.click()
    pag.wait_for_timeout(400)
    fila = pag.locator("#cuerpo .correo[data-sid='subp-0002-0000-0000-000000000000']")
    fila.locator(".lapiz").first.click()
    pag.wait_for_timeout(400)
    revisar("el ⊞ abre la hoja", pag.locator("#hojaSub.abierto").count(), 1)
    revisar("la hoja ofrece sacarla de su subproyecto",
            pag.locator("#hojaSub [data-hace='sacar']").count(), 1)
    pag.screenshot(path=str(AQUI / "subproy_celu_hoja.png"))
    pag.locator("#hojaSub [data-hace='sacar']").click()
    pag.wait_for_timeout(600)
    revisar("manda el pedido de sacarla", mandados[-1:],
            [{"sid": "subp-0002-0000-0000-000000000000", "subproyecto": ""}])
    revisar("sin errores de la página", errores, [])
    ctx.close()


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        compu(nav)
        celu(nav)
        nav.close()
    print(f"\n{'TODO BIEN' if not fallas else str(len(fallas)) + ' MAL'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
