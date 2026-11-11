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
    pag.on("pageerror", lambda e: errores.append(str(e)))
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
