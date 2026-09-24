"""Cuando pegás un texto largo, en /sesiones tiene que crecer SOLO la caja de escribir.

Martín trajo una captura el 2026-08-25: pegó la salida de un PowerShell y la barra de abajo
entera se estiró — el botón Enviar quedó como una plancha verde de punta a punta, "Subir
imagen" y "Buscar archivo" se treparon arriba y el resto de las perillas quedaron flotando
en el medio. Tres alturas distintas en una sola fila.

⚠ Nada de esto toca una sesión de verdad: las rutas del panel están inventadas acá adentro.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_caja_crece_compu   (panel prendido)
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
SALIDA = RAIZ / "pruebas" / "caja_crece_compu.png"

SID = "larga-5555-5555-555555555555"
PEGOTE = ("SISTEMA_UNO  AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA 25/8/2026 00:00:00\n"
          "SISTEMA_DOS  BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB 25/8/2026 00:00:00\n") * 6
CHARLA = [{"de": "vos", "texto": "pasame lo que salga", "imgs": []},
          {"de": "codex", "texto": "$res | Sort-Object base,FNUMCOMP", "imgs": []}]

fallas = []


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def servidor_falso(pag):
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": False,
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/modelo*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "modelo": "gpt-5.5", "defecto": "gpt-5.5",
                         "modelos": [{"id": "gpt-5.5", "nombre": "GPT-5.5"}],
                         "esfuerzo": "alto", "esfuerzos": [{"id": "alto", "nombre": "alto"}],
                         "velocidad": "estandar",
                         "velocidades": [{"id": "estandar", "nombre": "estándar"}],
                         "modo": "", "modos": [{"id": "", "nombre": "Normal"},
                                               {"id": "plan", "nombre": "Plan primero"}]})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"cerebro": "codex", "prompts": [], "carpeta": ""})))


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    # La pantalla de Martín: 2560 de ancho es donde se le vio feo.
    pag = nav.new_context(viewport={"width": 2560, "height": 1000}).new_page()
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
      abiertas = [{sid, cwd: p.cwd, nombre: 'La del pegote', cerebro: 'codex'}];
      pendientes = {}; activa = null; grupoAbierto = ''; guardar(); irTab(sid);
    }""", SID)
    pag.wait_for_timeout(1000)

    # Chico: un renglón. Grande: el pegote de PowerShell.
    def medir():
        return pag.evaluate("""() => {
          const r = e => { const n = document.querySelector(e);
            if (!n || n.offsetParent === null) return null;
            const b = n.getBoundingClientRect(); return {arriba: b.top, abajo: b.bottom,
              alto: b.height, ancho: b.width}; };
          return {caja: r('#caja'), texto: r('#texto'), enviar: r('#enviar'),
                  subir: r('#subirImagen'), cerebro: r('#cerebro'),
                  avisar: r('#avisarTarea')};
        }""")

    chico = medir()
    pag.evaluate("""(t) => { const c = document.querySelector('#texto');
      c.value = t; c.dispatchEvent(new Event('input')); }""", PEGOTE)
    pag.wait_for_timeout(400)
    grande = medir()

    print(f"caja:   {chico['caja']['alto']:.0f} px  ->  {grande['caja']['alto']:.0f} px")
    print(f"texto:  {chico['texto']['alto']:.0f} px  ->  {grande['texto']['alto']:.0f} px"
          f"   (ancho {grande['texto']['ancho']:.0f} px)")
    for cual in ("enviar", "subir", "cerebro", "avisar"):
        a, b = chico.get(cual), grande.get(cual)
        if a and b:
            print(f"{cual:8s} alto {a['alto']:.0f} -> {b['alto']:.0f}"
                  f"   base {a['abajo']:.0f} -> {b['abajo']:.0f}")

    revisar("la caja de escribir crece con el pegote",
            grande["texto"]["alto"] > chico["texto"]["alto"] + 20)

    # ⭐ Lo que Martín pidió: que se extienda SOLO la caja. Los botones no cambian de alto
    #    y siguen apoyados en la misma línea de abajo.
    for cual in ("enviar", "subir", "cerebro", "avisar"):
        a, b = chico.get(cual), grande.get(cual)
        if not a or not b:
            continue
        revisar(f"«{cual}» no se estira", abs(a["alto"] - b["alto"]) < 2,
                f"{a['alto']:.0f} -> {b['alto']:.0f}")

    bases = [v["abajo"] for k, v in grande.items()
             if k not in ("caja", "texto") and v]
    if bases:
        revisar("todos los botones apoyan en la misma línea",
                max(bases) - min(bases) < 3, f"desparramo {max(bases)-min(bases):.0f} px")

    revisar("la caja de texto no queda angosta", grande["texto"]["ancho"] >= 500,
            f"{grande['texto']['ancho']:.0f} px")

    pag.screenshot(path=str(SALIDA), clip={"x": 0, "y": max(0, grande["caja"]["arriba"] - 30),
                                           "width": 2560,
                                           "height": grande["caja"]["alto"] + 60})
    print(f"captura: {SALIDA}")
    nav.close()

print("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas))
if fallas:
    raise SystemExit(1)
