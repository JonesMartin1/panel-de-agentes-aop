"""SONDA de la pieza "Escritorio" contra el RustDesk DE VERDAD. No es una prueba de rutina.

    set SONDA_CLAVE=<contraseña del equipo>      (opcional: si RustDesk ya la recuerda, no hace falta)
    python -m pruebas.sonda_escritorio --equipo <nombre que figura en la lista>

⚠⚠ TOCA COSAS REALES, y por eso se corre solo con el OK de Martin:
  · CIERRA su RustDesk de siempre (lo reabre al final, pase lo que pase);
  · abre la version de prueba de RustDesk y le prende la aprobacion automatica un rato;
  · ENTRA a la compu que se le diga y hace UN clic inofensivo: abre el menu Inicio y lo cierra
    con Escape. No escribe nada.
Sirve la pieza en otro puerto (no el panel) y la maneja con un Chrome de Playwright, igual que
`ver_escritorio` pero sin puerta de mentira. Las capturas quedan en resultados/sonda_escritorio/
(pueden mostrar la pantalla de un tercero: esa carpeta no se versiona).
"""
import argparse
import os
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright

from app.rutas import RESULTADOS
from app.voz import escritorio

SALIDA = RESULTADOS / "sonda_escritorio"
PAGINA = """<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#0f1420;font-family:Segoe UI,system-ui,sans-serif">
<div id="caja" style="width:900px;height:640px;padding:12px;box-sizing:content-box"></div>
<script src="/estaticos/escritorio.js"></script>
<script>Escritorio.iniciar({}); Escritorio.mostrar(document.getElementById('caja'));</script>"""


def paso(texto):
    print(time.strftime("%H:%M:%S"), texto, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equipo", required=True, help="el nombre tal cual figura en la lista de equipos")
    ap.add_argument("--solo-mirar", action="store_true", help="no hace el clic en Inicio")
    a = ap.parse_args()
    clave = os.environ.get("SONDA_CLAVE", "")
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); puerto = s.getsockname()[1]; s.close()
    app = FastAPI()
    app.include_router(escritorio.crear_router())
    app.get("/")(lambda: HTMLResponse(PAGINA))
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    SALIDA.mkdir(parents=True, exist_ok=True)
    bien = False
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            pag = nav.new_page(viewport={"width": 940, "height": 680})
            errores = []
            pag.on("pageerror", lambda e: errores.append(str(e)))
            pag.goto(f"http://127.0.0.1:{puerto}/")
            pag.wait_for_selector("[data-prender], form[data-conectar]", timeout=20000)
            if pag.locator("[data-prender]").count():
                paso("apagada: " + pag.inner_text("[data-prender]"))
                t0 = time.time()
                pag.click("[data-prender]")
                pag.wait_for_selector("form[data-conectar]", timeout=90000)
                paso(f"prendida en {time.time() - t0:.0f} s")
            pag.wait_for_selector("[data-equipos] .escrEq", timeout=30000)
            paso(f"equipos en la lista: {pag.locator('.escrEq').count()}")
            fila = pag.locator(".escrEq", has_text=a.equipo)
            if not fila.count():
                paso("NO ESTA ese equipo en la lista")
                return False
            t0 = time.time()
            fila.first.click()
            pag.wait_for_selector("form[data-clave] input, .escrLienzo img", timeout=90000)
            if pag.locator("form[data-clave] input").count():
                if not clave:
                    paso("pide contraseña y no me pasaron ninguna (SONDA_CLAVE)")
                    return False
                pag.fill("form[data-clave] input", clave)
                pag.keyboard.press("Enter")
                pag.wait_for_function(
                    "document.querySelector('.escrLienzo img') || document.querySelector('#caja').innerText.includes('Esa contraseña no es')",
                    timeout=60000)
                if not pag.locator(".escrLienzo img").count():
                    paso("la contraseña ya no vale")
                    return False
            pag.wait_for_function("(() => { const i = document.querySelector('.escrLienzo img'); return i && i.naturalWidth > 0; })()",
                                  timeout=60000)
            ancho, alto, dibujado = pag.eval_on_selector(
                ".escrLienzo img", "i => [i.naturalWidth, i.naturalHeight, Math.round(i.getBoundingClientRect().width)]")
            paso(f"PANTALLA a la vista en {time.time() - t0:.0f} s: {ancho}x{alto}, dibujada a {dibujado} px · modo «{pag.inner_text('[data-modo]')}»")
            pag.screenshot(path=str(SALIDA / "1_pantalla.png"))
            # Cuantas imagenes distintas llegan en 6 s (el reloj de la otra compu no alcanza: se cuentan los pedidos)
            src0 = pag.get_attribute(".escrLienzo img", "src")
            if not a.solo_mirar:
                caja = pag.eval_on_selector(".escrLienzo img", "i => { const c = i.getBoundingClientRect(); return [c.left, c.top, c.width]; }")
                escala = caja[2] / ancho
                t0 = time.time()
                pag.mouse.click(caja[0] + 22 * escala, caja[1] + (alto - 20) * escala)     # el boton Inicio
                pag.wait_for_function("document.querySelector('[data-modo]').textContent === 'con control'", timeout=30000)
                paso(f"clic en Inicio mandado; tomo el control en {time.time() - t0:.1f} s")
                cambio = False
                for _ in range(40):
                    if pag.get_attribute(".escrLienzo img", "src") != src0:
                        cambio = True
                        break
                    pag.wait_for_timeout(150)
                paso(f"la imagen {'CAMBIO' if cambio else 'no cambio'} a los {time.time() - t0:.1f} s del clic")
                pag.wait_for_timeout(1500)
                pag.screenshot(path=str(SALIDA / "2_inicio_abierto.png"))
                pag.click("[data-tecla='Escape']")
                pag.wait_for_timeout(2500)
                pag.screenshot(path=str(SALIDA / "3_inicio_cerrado.png"))
                aviso = pag.inner_text(".escrAviso") if pag.locator(".escrAviso:not([hidden])").count() else ""
                paso("aviso en pantalla: " + (aviso or "ninguno"))
                pag.click("[data-control]")
                pag.wait_for_function("document.querySelector('[data-modo]').textContent === 'mirando'", timeout=30000)
                paso("control devuelto")
            pag.click("[data-cortar]")
            pag.wait_for_selector("form[data-conectar]", timeout=30000)
            paso("desconectado")
            pag.click("[data-apagar]")
            pag.wait_for_selector("[data-prender]", timeout=30000)
            paso("apagado desde la pieza")
            paso("errores de JavaScript: " + (str(errores) if errores else "ninguno"))
            bien = not errores
            nav.close()
    finally:
        r = escritorio.apagar()          # pase lo que pase: sin aprobacion automatica y con su RustDesk abierto
        prueba, oficiales = escritorio._procesos()
        paso(f"cierre: version de prueba abierta={len(prueba)} · RustDesk de siempre abierto={len(oficiales)} "
             f"· aprobacion automatica={'SI' if escritorio._auto_puesta() else 'no'} · reabierto ahora={r.get('reabierto')}")
        srv.should_exit = True
    return bien


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
