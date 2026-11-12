"""El botón ⟳ que ESPERA, en pantalla, con un Chrome de verdad (Playwright).

    python -m pruebas.ver_reinicio_espera

Sirve la página principal del panel (`panel.PAGINA`, la real) desde un servidor chico en
otro puerto. Las rutas del reinicio son de mentira y anotan lo que les llega: acá no se
reinicia nada ni se toca el panel prendido. Deja las capturas en
resultados/ver_reinicio_espera/.
"""
import socket
import sys
import threading
import time

import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright

import panel
from app.rutas import ESTATICOS, RESULTADOS

SALIDA = RESULTADOS / "ver_reinicio_espera"
OK, MAL = [], []
# Nombres inventados: acá no va ningún cliente.
TRES = [{"sid": "a", "cwd": "C:/p", "nombre": "Reportes"},
        {"sid": "b", "cwd": "C:/p", "nombre": "Migración de <datos>"},
        {"sid": "c", "cwd": "C:/p", "nombre": "Flujos"}]
E = {"trabajando": [], "pendiente": False, "pedidos": [], "cancelados": 0, "caido": False}


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    print(("  ✓ " if cond else "  ✗ ") + nombre + ("" if cond else f"  {detalle}"))


def armar():
    app = FastAPI()
    app.mount("/estaticos", StaticFiles(directory=str(ESTATICOS)), name="estaticos")

    @app.get("/")
    def pagina():
        return HTMLResponse(panel.PAGINA)

    @app.post("/reiniciar-todo")
    def reiniciar(d: dict = Body(default=None)):
        ya = bool((d or {}).get("ya"))
        E["pedidos"].append("ya" if ya else "esperar")
        if ya or not E["trabajando"]:
            E["pendiente"], E["caido"] = False, True       # "se muere" el panel
            return {"ok": True}
        E["pendiente"] = True
        return {"ok": True, "esperando": E["trabajando"]}

    @app.get("/reiniciar-todo/estado")
    def estado():
        if E["caido"]:
            return JSONResponse({"detail": "caido"}, status_code=503)
        if E.get("saliendo"):
            return {"ok": True, "pendiente": False, "reiniciando": True, "trabajando": []}
        return {"ok": True, "pendiente": E["pendiente"], "trabajando": E["trabajando"]}

    @app.post("/reiniciar-todo/cancelar")
    def cancelar():
        E["cancelados"] += 1
        E["pendiente"] = False
        return {"ok": True}

    # Todo lo demás que pide la página (estado de servicios, chat, placa…): un objeto vacío.
    @app.api_route("/{resto:path}", methods=["GET", "POST"])
    def resto_de_la_pagina(resto: str):
        return {}
    return app


def puerto_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    puerto = puerto_libre()
    srv = uvicorn.Server(uvicorn.Config(armar(), host="127.0.0.1", port=puerto, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{puerto}/"
    velo = "#veloReinicio"

    def limpio(**cambios):
        E.update(trabajando=[], pendiente=False, pedidos=[], cancelados=0, caido=False, saliendo=False)
        E.update(cambios)

    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pag = nav.new_page(viewport={"width": 1100, "height": 720})
        pag.on("dialog", lambda d: d.accept())          # el "¿Reiniciar…?" de siempre

        # 1. Con sesiones trabajando: no reinicia, muestra a quiénes espera.
        limpio(trabajando=TRES)
        pag.goto(base)
        pag.wait_for_selector("#btnReiniciarTodo")
        chequeo("al abrir, sin nada pendiente, no hay cartel", pag.locator(velo).count() == 0)
        pag.click("#btnReiniciarTodo")
        pag.wait_for_selector(velo)
        texto = pag.inner_text(velo)
        chequeo("el pedido sale SIN el «ya»: espera", E["pedidos"] == ["esperar"], E["pedidos"])
        chequeo("dice que reinicia cuando terminen", "apenas terminen" in texto, texto[:80])
        chequeo("cuenta cuántas son", "Hay 3 sesiones" in texto, texto[:160])
        chequeo("y las nombra", all(n in texto for n in ("Reportes", "Flujos")), texto)
        chequeo("un nombre con < se muestra como texto",
                "Migración de <datos>" in texto and pag.locator(velo + " datos").count() == 0)
        chequeo("ofrece reiniciar ya igual y cancelar",
                pag.locator("#veloYa").count() == 1 and pag.locator("#veloNo").count() == 1)
        pag.screenshot(path=str(SALIDA / "1_esperando.png"))

        # 2. Una termina: la lista se actualiza sola.
        E["trabajando"] = TRES[:1]
        pag.wait_for_function("document.querySelector('#veloQuienes').children.length === 1", timeout=8000)
        chequeo("al terminar dos, queda una en la lista", "Hay una sesión" in pag.inner_text(velo))

        # 3. Cancelar.
        pag.click("#veloNo")
        pag.wait_for_timeout(500)
        chequeo("Cancelar saca el cartel y avisa al servidor",
                pag.locator(velo).count() == 0 and E["cancelados"] == 1, E)

        # 4. Quedó pendiente y se recarga la página: el cartel vuelve solo.
        limpio(trabajando=TRES[:2], pendiente=True)
        pag.reload()
        pag.wait_for_selector(velo)
        chequeo("un reinicio pendiente reaparece al volver a abrir el panel",
                "Hay 2 sesiones" in pag.inner_text(velo) and not E["pedidos"])

        # 5. Lo cancelan desde otra pantalla: este cartel se va solo.
        E["pendiente"] = False
        pag.wait_for_selector(velo, state="detached", timeout=8000)
        chequeo("si se cancela en otra pantalla, el cartel se va", pag.locator(velo).count() == 0)

        # 6. Reiniciar ya igual.
        limpio(trabajando=TRES)
        pag.reload()
        pag.wait_for_selector("#btnReiniciarTodo")
        pag.click("#btnReiniciarTodo")
        pag.wait_for_selector("#veloYa")
        pag.click("#veloYa")
        pag.wait_for_function("document.querySelector('#veloReinicio').innerText.includes('Reiniciando')", timeout=8000)
        chequeo("«Reiniciar ya igual» manda el pedido con «ya»", E["pedidos"] == ["esperar", "ya"], E["pedidos"])
        chequeo("y pasa al cartel de reiniciando", pag.locator("#veloYa").count() == 0)
        pag.screenshot(path=str(SALIDA / "2_reiniciando.png"))

        # 7. Sin nadie trabajando: reinicia en el acto, como siempre.
        limpio()
        pag.goto(base)
        pag.wait_for_selector("#btnReiniciarTodo")
        pag.click("#btnReiniciarTodo")
        pag.wait_for_function("document.querySelector('#veloReinicio') && "
                              "document.querySelector('#veloReinicio').innerText.includes('Reiniciando')", timeout=8000)
        chequeo("sin nadie trabajando va derecho a reiniciar", E["pedidos"] == ["esperar"] and pag.locator("#veloYa").count() == 0)

        # 8. Estaba esperando y terminó la última: el panel sale a reiniciarse solo. Primero
        #    lo dice (todavía contesta unos segundos) y después directamente deja de contestar.
        reiniciando = ("document.querySelector('#veloReinicio') && "
                       "document.querySelector('#veloReinicio').innerText.includes('Reiniciando')")
        for caso, cambio in (("avisa que sale a reiniciar", {"saliendo": True}),
                             ("deja de contestar", {"caido": True})):
            limpio(trabajando=TRES[:1], saliendo=False)
            pag.goto(base)
            pag.wait_for_selector("#btnReiniciarTodo")
            pag.click("#btnReiniciarTodo")
            pag.wait_for_selector("#veloYa")
            E.update(cambio)
            try:
                pag.wait_for_function(reiniciando, timeout=8000)
                paso = pag.locator("#veloYa").count() == 0
            except Exception:
                paso = False
            chequeo(f"esperando, el panel {caso}: el cartel pasa a «reiniciando», no desaparece", paso,
                    pag.locator("#veloReinicio").count())
        nav.close()
    srv.should_exit = True
    print(f"ver_reinicio_espera: {len(OK)} bien, {len(MAL)} mal · capturas en {SALIDA}")
    return not MAL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
