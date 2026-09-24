"""La barra de escribir de /sesiones cuando la pantalla da menos lugar (zoom del navegador).

Martín trajo una captura el 2026-08-25 con el navegador al 110 %: la caja de escribir quedó
reducida a una rendija de dos centímetros en el medio de la fila —solo se le veía la barra
de scroll—, y encima alta, porque cualquier texto metido en 40 px de ancho se parte en
treinta renglones. Los botones no se achican; el único que paga el zoom es justo el lugar
donde uno escribe.

⭐ Zoom del navegador (y la ampliación de Windows) = la misma pantalla con MENOS píxeles CSS.
Por eso acá se mide con anchos de ventana, que es exactamente lo mismo y se automatiza: su
monitor de 2560 con Windows al 150 % y Chrome al 110 % son ~1590 px CSS de ancho útil.

Se mide con la fila COMPLETA, que es la de la captura: charla trabajando (aparece Parar),
la chapa del contexto encendida y Compactar diciendo "resumiendo…". Ese es el estado más
ancho, y es el que hay que aguantar.

⚠ Nada de esto toca una sesión de verdad: las rutas del panel están inventadas acá adentro.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_caja_zoom   (panel prendido)
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
SESIONES_HTML = Path(os.environ.get("SESIONES_HTML")
                     or (RAIZ / "app" / "estaticos" / "sesiones.html"))
SALIDA = RAIZ / "pruebas" / "caja_zoom.png"

SID = "zoom-7777-7777-777777777777"
# Ancho útil en píxeles CSS y con qué se corresponde en su pantalla.
ANCHOS = [(2560, "sin zoom"), (1900, "con zoom"), (1590, "el de la captura"),
          (1280, "zoom fuerte")]
# Lo mínimo para que escribir sea escribir y no espiar por una ranura.
MINIMO = 300
LARGO = ("Necesito que revises el webhook de wasender y me digas por qué se duplican "
         "los mensajes cuando entran dos audios seguidos. ") * 4
CHARLA = [{"de": "vos", "texto": "hola", "imgs": []},
          {"de": "claude", "texto": "listo", "imgs": []}]

fallas = []


def revisar(que, ok, detalle=""):
    print(("  ok   " if ok else "  MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def servidor_falso(pag):
    # ⚠ La bandeja también va inventada: `/movil/sesiones` del panel de verdad puede
    # tardar minutos cuando hay una charla de Codex con un rollout gigante creciendo
    # (medido el 2026-08-25), y esta prueba mide la barra, no el panel.
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "laura": "", "proyectos": [
            {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False, "sesiones": [
                {"id": SID, "nombre": "La del zoom", "ts": 2, "ultimo": "vos",
                 "viva": False, "interactiva": False, "detalle": ""}]}]})))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": False,
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "opus", "defecto": "opus",
                         "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}],
                         "esfuerzo": "normal",
                         "esfuerzos": [{"id": "normal", "nombre": "normal"}],
                         "velocidad": "normal",
                         "velocidades": [{"id": "normal", "nombre": "normal"}],
                         "modo": "", "modos": [{"id": "", "nombre": "Normal"}],
                         "contexto": {"tokens": 183000, "nivel": "medio"}})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/movil/mandar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "sid": SID, "respuesta": "listo"})))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"cerebro": "claude", "prompts": [], "carpeta": ""})))


# La fila más ancha que puede quedar: la de la captura. Se fuerza desde acá porque
# compactar de verdad implicaría un turno real de un CLI.
FILA_COMPLETA = """() => {
  const p = document.querySelector('#parar');
  if (p) p.style.display = '';
  const b = document.querySelector('#compactar');
  if (b) b.textContent = '⇲ resumiendo…';
}"""

MEDIR = """() => {
  const caja = document.querySelector('#caja');
  const t = document.querySelector('#texto');
  // Los del grupo de iconos se miden de a uno: si uno se sale de la línea, hay que ver
  // cuál es.
  const nietos = [...(document.querySelector('#grupoTraer')?.children || [])];
  const hijos = [...caja.children, ...nietos].filter(n => n.offsetParent !== null).map(n => {
    const b = n.getBoundingClientRect();
    return {id: n.id || n.className, izq: Math.round(b.left), der: Math.round(b.right),
            arriba: Math.round(b.top), abajo: Math.round(b.bottom),
            ancho: Math.round(b.width), alto: Math.round(b.height)};
  });
  const b = t.getBoundingClientRect();
  return {alto_caja: Math.round(caja.getBoundingClientRect().height),
          arriba_caja: Math.round(caja.getBoundingClientRect().top),
          ancho: Math.round(b.width), alto: Math.round(b.height),
          desborda: Math.round(caja.scrollWidth - caja.clientWidth),
          renglones: new Set(hijos.map(h => h.abajo)).size, hijos};
}"""


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    for ancho, cuando in ANCHOS:
        print(f"\n=== {ancho} px de ancho útil ({cuando}) ===")
        pag = nav.new_context(viewport={"width": ancho, "height": 1000}).new_page()
        pag.on("dialog", lambda d: d.dismiss())
        servidor_falso(pag)
        pag.route(BASE + "/sesiones", lambda r: r.fulfill(
            status=200, content_type="text/html; charset=utf-8",
            body=SESIONES_HTML.read_text(encoding="utf-8")))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                              timeout=90000)
        pag.wait_for_timeout(1200)
        pag.evaluate("""(sid) => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'La del zoom', cerebro: ''}];
          pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
        }""", SID)
        pag.wait_for_timeout(1200)
        pag.evaluate(FILA_COMPLETA)

        vacia = pag.evaluate(MEDIR)
        print(f"  vacía:     caja {vacia['alto_caja']:3d} px · texto "
              f"{vacia['ancho']:4d}x{vacia['alto']:3d} px · "
              f"{vacia['renglones']} renglón(es)")
        for h in vacia["hijos"]:
            print(f"      {h['id']:22s} x {h['izq']:5d}..{h['der']:5d}  "
                  f"{h['ancho']:5d}x{h['alto']:3d}  abajo {h['abajo']}")

        pag.evaluate("""(t) => { const c = document.querySelector('#texto');
          c.value = t; c.dispatchEvent(new Event('input')); }""", LARGO)
        pag.wait_for_timeout(300)
        llena = pag.evaluate(MEDIR)
        print(f"  con texto: caja {llena['alto_caja']:3d} px · texto "
              f"{llena['ancho']:4d}x{llena['alto']:3d} px")

        if ancho == 1590:
            pag.screenshot(path=str(SALIDA),
                           clip={"x": 0, "y": max(0, llena["arriba_caja"] - 20),
                                 "width": ancho, "height": llena["alto_caja"] + 40})
            print(f"  captura (con el texto largo puesto): {SALIDA}")

        pag.evaluate("() => mandar()")
        pag.wait_for_timeout(2500)
        pag.evaluate(FILA_COMPLETA)
        despues = pag.evaluate(MEDIR)
        quedo = pag.evaluate("() => document.querySelector('#texto').value")
        print(f"  mandado:   caja {despues['alto_caja']:3d} px · texto "
              f"{despues['ancho']:4d}x{despues['alto']:3d} px · quedó escrito {quedo!r}")

        revisar("la caja de escribir no queda como una rendija",
                vacia["ancho"] >= MINIMO, f"{vacia['ancho']} px de ancho")
        # ⭐ Lo que pidió Martín al ver la barra partida en dos: *"no me gusta que se
        #    extiendan, sería mejor que se compacten por categoría"*. Con los tres de
        #    traer hechos iconos y las perillas adentro del ⚙, entra en un renglón.
        revisar("la barra entra en un solo renglón", vacia["renglones"] == 1,
                f"{vacia['renglones']} renglón(es)")
        revisar("nada se sale de la pantalla", vacia["desborda"] <= 1,
                f"desborda {vacia['desborda']} px")
        revisar("al mandarlo vuelve a su alto normal",
                despues["alto"] <= vacia["alto"] + 3,
                f"{vacia['alto']} -> {despues['alto']} px")
        revisar("y quedó vacía", quedo == "")

        pag.context.close()

    # ⭐ Y el zoom cambiado EN CALIENTE, con el texto ya escrito: es lo que hace Martín
    # (Ctrl + rueda hasta que se ve bien). El alto de la caja está guardado en píxeles,
    # así que si nadie lo vuelve a medir queda con el de la medida anterior: agrandado de
    # cuando era angosta. Lo remide el ResizeObserver de `sesiones.html`.
    print("\n=== cambiar el zoom con el texto ya escrito ===")
    pag = nav.new_context(viewport={"width": 1280, "height": 1000}).new_page()
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.wait_for_timeout(1200)
    pag.evaluate("""(sid) => {
      const p = datos.proyectos[0];
      abiertas = [{sid, cwd: p.cwd, nombre: 'La del zoom', cerebro: ''}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
    }""", SID)
    pag.wait_for_timeout(1200)
    pag.evaluate("""(t) => { const c = document.querySelector('#texto');
      c.value = t; c.dispatchEvent(new Event('input')); }""", LARGO)
    pag.wait_for_timeout(300)
    apretado = pag.evaluate(MEDIR)
    pag.set_viewport_size({"width": 2560, "height": 1000})
    pag.wait_for_timeout(500)
    ancho_de_nuevo = pag.evaluate(MEDIR)
    print(f"  apretado: texto {apretado['ancho']}x{apretado['alto']} px"
          f"  ->  ancho: texto {ancho_de_nuevo['ancho']}x{ancho_de_nuevo['alto']} px")
    revisar("al sacar el zoom, el mismo texto deja de necesitar tantos renglones",
            ancho_de_nuevo["alto"] < apretado["alto"],
            f"{apretado['alto']} -> {ancho_de_nuevo['alto']} px")
    pag.context.close()
    nav.close()

print("\n" + ("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas)))
if fallas:
    raise SystemExit(1)
