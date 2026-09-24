"""Una imagen enviada desde Sesiones se ve como miniatura desde el primer instante.

Pedido de Martín (2026-08-23): una foto grande enviada desde la computadora ocupaba
media conversación y, mientras subía, dejaba abajo el texto feo "(imagen)". Esta prueba
sirve la pantalla real del disco, pero inventa cada endpoint que podría escribir: comprueba
la foto ya guardada y la vista previa de una foto nueva sin mandarle nada a una sesión real.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_envio_imagen_sesion
"""
import json
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
SID = "imagen-prueba-0000-0000-000000000000"
CWD = r"D:\IA\wpp-transcriptor"
SVG = "data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600">'
    '<rect width="1200" height="600" fill="#7558a8"/>'
    '</svg>', safe="")
DATOS = {"proyectos": [{"proyecto": "Prueba de imagen", "cwd": CWD, "sesiones": []}],
         "carpetas": {"orden": [], "ocultas": []}}
CHAT = {"mensajes": [{"de": "vos", "texto": "Foto ya guardada", "imgs": [SVG]}]}
MODELOS = {"ok": True, "modelo": "opus", "defecto": "opus",
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]}
fallas = []


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}" + (f": {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def falso(pag):
    """No sale ningún pedido que pueda tocar las conversaciones reales de Martín."""
    pag.route("**/movil/sesiones", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(DATOS)))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHAT)))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(MODELOS)))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/movil/novedad", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    # El trabajo queda deliberadamente pensando: así la vista previa sigue visible para
    # medirla, igual que durante una subida real, pero sin abrir ningún turno de verdad.
    pag.route("**/movil/mandar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "sid": SID, "segundo_plano": True,
                         "trabajo": "imagen-prueba"})))
    pag.route("**/movil/trabajo/*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok": true, "estado": "trabajando"}'))


def main():
    errores = []
    salida = RAIZ / "resultados" / "envio_imagen_sesion.png"
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1400, "height": 900})
        pag = ctx.new_page()
        pag.on("pageerror", lambda e: errores.append(str(e)))
        falso(pag)
        # La página es exactamente la que se va a ver, leída del disco y sin reiniciar.
        pagina = (RAIZ / "app" / "estaticos" / "sesiones.html").read_text(encoding="utf-8")
        pag.route(BASE + "/sesiones", lambda r: r.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=pagina))
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length")
        pag.evaluate("""(sid) => {
          abiertas = [{sid, cwd: datos.proyectos[0].cwd, nombre: 'Prueba de imagen'}];
          activa = sid; firma = ''; guardar(); pintarTabs(); pintarSesion();
        }""", SID)
        pag.wait_for_function("() => document.querySelectorAll('#hilo .msg.vos img').length === 1")

        # Una foto de 1200×600 revela tanto si se estira a la burbuja como si se deforma.
        pag.evaluate("""async () => {
          const lienzo = document.createElement('canvas'); lienzo.width = 1200; lienzo.height = 600;
          const lapiz = lienzo.getContext('2d'); lapiz.fillStyle = '#7558a8'; lapiz.fillRect(0, 0, 1200, 600);
          const blob = await new Promise(ok => lienzo.toBlob(ok, 'image/png'));
          sumarFotos([new File([blob], 'foto-grande.png', {type: 'image/png'})]);
          mandar();
        }""")
        pag.wait_for_function("""() => {
          const fotos = [...document.querySelectorAll('#hilo .msg.vos img')];
          return fotos.length === 2 && fotos.every(i => i.complete) && fotos[1].src.startsWith('blob:');
        }""", timeout=15000)
        pag.screenshot(path=str(salida), full_page=True)
        estado = pag.evaluate("""() => {
          const burbujas = [...document.querySelectorAll('#hilo .msg.vos')];
          const fotos = [...document.querySelectorAll('#hilo .msg.vos img')].map(i => {
            const r = i.getBoundingClientRect(); return {ancho: r.width, alto: r.height, src: i.src};
          });
          return {fotos, burbujas: burbujas.map(b => b.getBoundingClientRect().width),
                  provisional: burbujas.at(-1).textContent.trim()};
        }""")
        ctx.close()
        nav.close()

    revisar("la foto ya guardada entra como miniatura", estado["fotos"][0]["ancho"] <= 420,
            f"{estado['fotos'][0]['ancho']:.0f} px")
    revisar("la vista previa también queda proporcionada", estado["fotos"][1]["ancho"] <= 420
            and round(estado["fotos"][1]["ancho"] / estado["fotos"][1]["alto"], 1) == 2.0,
            f"{estado['fotos'][1]['ancho']:.0f}×{estado['fotos'][1]['alto']:.0f}")
    revisar("la burbuja abraza la foto y no deja un bloque vacío",
            all(ancho <= 446 for ancho in estado["burbujas"]),
            ", ".join(f"{ancho:.0f} px" for ancho in estado["burbujas"]))
    revisar("la vista previa aparece de inmediato", estado["fotos"][1]["src"].startswith("blob:"))
    revisar("no queda el cartel provisional feo", estado["provisional"] != "(imagen)",
            repr(estado["provisional"]))
    revisar("sin errores de JavaScript", errores == [], str(errores))
    print("\nTODO BIEN" if not fallas else "\nFALLARON: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
