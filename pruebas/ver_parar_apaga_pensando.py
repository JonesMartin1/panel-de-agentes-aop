"""Apretaste Parar, el servidor dijo que no quedaba nada: la burbuja tiene que apagarse.

Bug que trajo Martín con dos capturas el 2026-08-25, sobre su propia charla: apretó ⏹ Parar,
le saltó el cartel *"Ya había terminado: no quedaba nada corriendo"* y abajo, en el hilo,
la burbuja de **"pensando · 58 s"** seguía moviéndose.

El motivo no es el botón: `trabajando` sale de la BANDEJA (`/movil/sesiones`), y la bandeja
puede estar vieja. Ese día una charla de Codex con un rollout gigante tenía a `/movil/sesiones`
tardando más de 120 s en contestar, así que la pantalla seguía creyendo el `ocupada: true` de
un rato antes y volvía a encender la burbuja en cada repintado.

Arreglo: desde que se para una charla, no se le cree a ningún dato ANTERIOR a ese momento.
Se vuelve a mirar el estado recién cuando llega uno nuevo (con `ts` posterior).

⚠ Nada de esto toca una sesión de verdad: el panel está inventado acá adentro.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_parar_apaga_pensando   (panel prendido)
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
SESIONES_HTML = Path(os.environ.get("SESIONES_HTML")
                     or (RAIZ / "app" / "estaticos" / "sesiones.html"))

SID = "parar-6666-6666-666666666666"
CHARLA = [{"de": "vos", "texto": "arreglá la barra", "imgs": []},
          {"de": "claude", "texto": "voy con la mixta", "imgs": []}]

fallas = []
# Lo que contesta el panel: arranca con la charla trabajando, como en la captura.
estado = {"ocupada": True, "ts": time.time()}


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def servidor_falso(pag, paradas):
    def bandeja(r):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "laura": "", "proyectos": [
                {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": True, "sesiones": [
                    {"id": SID, "nombre": "La que quedó pensando", "ts": estado["ts"],
                     "ultimo": "claude", "viva": True, "interactiva": False,
                     "ocupada": estado["ocupada"], "detalle": "activa"}]}]}))
    pag.route("**/movil/sesiones*", bandeja)
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": estado["ocupada"],
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "opus", "defecto": "opus",
                         "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    # El caso de la captura: el turno YA había terminado, así que no hay nada que matar.
    def parar(r):
        paradas.append(json.loads(r.request.post_data or "{}"))
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "paro": False}))
    pag.route("**/movil/parar", parar)
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"cerebro": "claude", "prompts": [], "carpeta": ""})))


PENSANDO = "() => !!document.querySelector('#hilo .msg.pensa')"

with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    pag = nav.new_context(viewport={"width": 1600, "height": 950}).new_page()
    errores, paradas, avisos = [], [], []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: (avisos.append(d.message), d.dismiss()))
    servidor_falso(pag, paradas)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=SESIONES_HTML.read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof parar === 'function' && datos.proyectos.length",
                          timeout=90000)
    pag.evaluate("""(sid) => {
      const p = datos.proyectos[0];
      abiertas = [{sid, cwd: p.cwd, nombre: 'La que quedó pensando', cerebro: ''}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
    }""", SID)
    pag.wait_for_timeout(1500)

    revisar("mientras trabaja, la burbuja de pensando está", pag.evaluate(PENSANDO))
    revisar("y el botón Parar se ofrece", pag.is_visible("#parar"))

    # Se aprieta Parar. El turno ya había terminado del lado del servidor, y la bandeja
    # sigue devolviendo el dato viejo (ocupada: true) — que es lo que pasaba de verdad,
    # con `/movil/sesiones` tardando minutos.
    pag.click("#parar")
    pag.wait_for_timeout(1200)
    revisar("el pedido de parar llegó con el id de la charla",
            bool(paradas) and paradas[-1].get("sid") == SID, str(paradas[-1:]))
    revisar("avisa que ya había terminado",
            any("Ya había terminado" in a for a in avisos), str(avisos))
    revisar("** la burbuja de pensando se apaga", not pag.evaluate(PENSANDO))

    # Y no vuelve sola en los repintados siguientes, que es lo que se veía.
    pag.evaluate("() => { firma = ''; pintarSesion(); }")
    pag.wait_for_timeout(2500)
    revisar("** y no vuelve a encenderse con el dato viejo", not pag.evaluate(PENSANDO))
    revisar("el botón Parar vuelve a su texto",
            pag.evaluate("() => document.querySelector('#parar').textContent"), "⏹ Parar")

    # Si la charla vuelve a moverse DE VERDAD (dato nuevo, posterior al corte), la
    # pantalla tiene que volver a mostrarla trabajando: esto no puede sordear la charla.
    estado["ts"] = time.time() + 5
    estado["ocupada"] = True
    pag.evaluate("() => { firma = ''; cargar(); }")
    pag.wait_for_timeout(2500)
    revisar("** con un dato NUEVO vuelve a mostrarse trabajando", pag.evaluate(PENSANDO))

    revisar("sin errores de JS", errores == [], str(errores))
    nav.close()

print("\n" + ("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas)))
if fallas:
    raise SystemExit(1)
