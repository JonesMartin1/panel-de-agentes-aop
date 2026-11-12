"""La tarjeta "Despachos" EN PANTALLA, con un Chrome de verdad (Playwright).

    python -m pruebas.ver_despachos

Levanta un servidor chico aparte (otro puerto, no el panel) con el `entorno.js` real y dos
rutas de mentira: `/movil/entorno` y `/movil/despachos`, que contesta según el caso que se
esté mirando. No toca el panel ni ninguna charla. Deja las capturas en
resultados/ver_despachos/.
"""
import socket
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS, RESULTADOS

SALIDA = RESULTADOS / "ver_despachos"
OK, MAL = [], []
ESTADO = {"caso": "viejo", "pedidos": 0}

# Nombres inventados: acá no va ningún cliente.
LLENO = [("t1", "ses-reportes", "Reportes", "trabaja", 240),
         ("t2", "ses-flujos", "Flujos", "pregunta", 30),
         ("t3", "ses-datos", "Datos", "termino", 120),
         ("t4", "ses-altas", "Altas", "fallo", 300),
         ("t5", "ses-cobros", "Cobros", "corto", 4000),
         ("t6", "ses-stock", "Stock", "paro", 20),
         ("t7", "", "charla nueva", "trabaja", 10),
         ("t8", "ses-rara", "<b>Rara</b>", "termino", 60),
         ("t9", "ses-larga", "Un nombre bien largo de charla que no entra en un renglón", "trabaja", 70)]
QUIETOS = [f for f in LLENO if f[3] in ("termino", "fallo")]


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    print(("  ✓ " if cond else "  ✗ ") + nombre + ("" if cond else f"  {detalle}"))


def armar():
    app = FastAPI()

    @app.get("/estaticos/entorno.js")
    def js():
        return FileResponse(ESTATICOS / "entorno.js", headers={"Cache-Control": "no-store"})

    @app.get("/movil/entorno")
    def entorno():
        return {"ok": True, "maquina": "MiCompu", "carpeta": "C:/proyecto", "nombre": "proyecto",
                "remoto_posible": False, "cerebro": "claude",
                "contexto": {"tokens": 40000, "tope": 200000},
                "conectores": [{"nombre": "uno", "estado": ""}], "conectores_de": "configurados"}

    @app.get("/movil/despachos")
    def despachos():
        ESTADO["pedidos"] += 1
        caso = ESTADO["caso"]
        if caso == "viejo":
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if caso == "sin-items":        # lo que contesta una prueba que intercepta /movil/*
            return {"ok": True}
        ahora = time.time()
        filas = {"vacio": [], "lleno": LLENO, "quietos": QUIETOS}[caso]
        return {"ok": True, "ahora": ahora, "items": [
            {"trabajo": t, "sid": sid, "cwd": "C:/proyecto", "nombre": nombre, "cerebro": "",
             "estado": estado, "desde": ahora - hace} for t, sid, nombre, estado, hace in filas]}

    @app.get("/")
    def pagina(lento: str = "", sinabrir: str = ""):
        # `lento`: la pantalla NO refresca sola (como una charla quieta, que pide cada 10 s).
        return HTMLResponse("""<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#0f1420;font-family:Segoe UI,system-ui,sans-serif">
<div id="caja" class="entornoCaja" style="width:300px;padding:12px"></div>
<script src="/estaticos/entorno.js"></script>
<script>
  const u = {cwd: 'C:/proyecto', sid: 'ses-chief', nombre: 'Chief'};
  window.abiertos = [];
  async function refrescar(){ try { Entorno.pintar(document.getElementById('caja'), await Entorno.pedir(u), u); } catch(e){} }
  Entorno.iniciar(Object.assign({ubicacion: () => u, alCambiar: refrescar},
    %s ? {} : {abrir: (c, s, n, cer) => window.abiertos.push([c, s, n, cer])}));
  refrescar(); if (!%s) setInterval(refrescar, 300);
</script>""" % ("true" if sinabrir else "false", "true" if lento else "false"))
    return app


def puerto_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    puerto = puerto_libre()
    srv = uvicorn.Server(uvicorn.Config(armar(), host="127.0.0.1", port=puerto, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{puerto}/"
    tarjeta = "details.tarjDer[data-t='despachos']"
    fila = lambda nombre: tarjeta + f" .desp:has(.txt:text-is('{nombre}'))"

    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pag = nav.new_page(viewport={"width": 324, "height": 640})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # 1. Panel sin reiniciar, charla que no despachó nada, y respuesta sin lista.
        for caso, nombre in (("viejo", "panel viejo (404)"), ("vacio", "charla sin despachos"),
                             ("sin-items", "respuesta sin lista")):
            ESTADO["caso"] = caso
            pag.goto(base)
            pag.wait_for_selector("details.tarjDer[data-t='entorno']")
            pag.wait_for_timeout(700)
            chequeo(f"{nombre}: no aparece la tarjeta", pag.locator(tarjeta).count() == 0)
            chequeo(f"{nombre}: el resto se dibuja igual",
                    pag.locator("details.tarjDer").count() == 3, pag.locator("details.tarjDer").count())

        # 2. Con despachos: va primera y dice lo justo.
        ESTADO["caso"] = "lleno"
        pag.goto(base)
        pag.wait_for_selector(tarjeta)
        orden = pag.eval_on_selector_all("details.tarjDer", "ds => ds.map(d => d.dataset.t)")
        chequeo("aparece primera, arriba de Entorno", orden[:2] == ["despachos", "entorno"], orden)
        chequeo("el resumen cuenta lo que sigue en curso",
                pag.inner_text(tarjeta + " summary .resumen") == "4 en curso",
                pag.inner_text(tarjeta + " summary .resumen"))
        # Con nombres de verdad, largos: el nombre tiene el renglón entero y el estado va abajo.
        larga = tarjeta + " .desp:has(.txt:text('Un nombre bien largo'))"
        m = pag.eval_on_selector(larga, """e => { const n = e.querySelector('.txt').getBoundingClientRect(),
            c = e.querySelector('.cuando').getBoundingClientRect(), f = e.getBoundingClientRect();
            return {nombre: n.width, fila: f.width, abajo: c.top >= n.bottom - 1,
                    entero: c.right <= f.right + 1 && c.width > 0}; }""")
        chequeo("un nombre largo usa casi todo el ancho del renglón",
                m["nombre"] >= m["fila"] - 40, m)
        chequeo("y el estado va debajo, entero", m["abajo"] and m["entero"], m)
        chequeo("un renglón por despacho", pag.locator(tarjeta + " .desp").count() == len(LLENO))
        textos = {"Reportes": "trabaja · 4 min", "Flujos": "te pregunta algo",
                  "Datos": "terminó hace 2 min", "Altas": "falló hace 5 min",
                  "Cobros": "se cortó hace 1 h 6 min", "Stock": "se paró hace menos de 1 min"}
        for nombre, quiere in textos.items():
            dice = pag.inner_text(fila(nombre) + " .cuando")
            chequeo(f"{nombre}: «{quiere}»", dice == quiere, dice)

        # El rojo es solo para lo que está mal.
        color = lambda n: pag.eval_on_selector(fila(n) + " .cuando", "e => getComputedStyle(e).color")
        rojo = color("Altas")
        chequeo("«falló» va en el tono de lo que está mal", rojo == "rgb(247, 161, 161)", rojo)
        chequeo("ningún otro estado usa ese rojo",
                all(color(n) != rojo for n in textos if n != "Altas"),
                {n: color(n) for n in textos})

        # Enlaces, y lo que viene raro.
        href = pag.get_attribute(fila("Reportes"), "href")
        chequeo("el renglón es un enlace a esa charla", href == "/?c=ses-reportes", href)
        nueva = pag.locator(tarjeta + " .desp", has_text="charla nueva")
        chequeo("una charla que todavía no tiene id va sin enlace",
                nueva.count() == 1 and nueva.evaluate("e => e.tagName") == "DIV")
        chequeo("un nombre con < se muestra como texto, no como HTML",
                pag.locator(tarjeta + " .desp b").count() == 0
                and "<b>Rara</b>" in pag.inner_text(tarjeta))
        pag.screenshot(path=str(SALIDA / "1_con_despachos.png"))

        # 3. Tocar un renglón abre esa charla sin recargar la página.
        pag.locator(fila("Reportes")).click()
        pag.wait_for_timeout(300)
        abiertos = pag.evaluate("window.abiertos")
        chequeo("clic: le pide a la pantalla que abra esa charla",
                abiertos == [["C:/proyecto", "ses-reportes", "Reportes", ""]], abiertos)
        chequeo("y no navega", "c=" not in pag.url, pag.url)
        pag.locator(tarjeta + " .desp", has_text="charla nueva").click()
        chequeo("clic en la que no tiene id no hace nada", len(pag.evaluate("window.abiertos")) == 1)

        # Sin esa ayuda de la pantalla, el enlace igual lleva a la charla.
        pag.goto(base + "?sinabrir=1")
        pag.wait_for_selector(tarjeta)
        pag.locator(fila("Datos")).click()
        pag.wait_for_url("**c=ses-datos*", timeout=5000)
        chequeo("sin `abrir`, el enlace lleva a la dirección de la charla", "c=ses-datos" in pag.url, pag.url)

        # 4. Con algo en curso se vuelve a pedir sola, aunque la pantalla no refresque.
        pag.goto(base + "?lento=1")
        pag.wait_for_selector(tarjeta)
        antes = ESTADO["pedidos"]
        pag.wait_for_timeout(9500)
        chequeo("con algo en curso se refresca sola cada ~4 s",
                2 <= ESTADO["pedidos"] - antes <= 3, ESTADO["pedidos"] - antes)
        ESTADO["caso"] = "quietos"
        pag.goto(base + "?lento=1")
        pag.wait_for_selector(tarjeta)
        antes = ESTADO["pedidos"]
        pag.wait_for_timeout(6000)
        chequeo("con todo cerrado no pide de más", ESTADO["pedidos"] == antes, ESTADO["pedidos"] - antes)
        chequeo("y el resumen no dice «en curso»", pag.locator(tarjeta + " summary .resumen").count() == 0)
        pag.screenshot(path=str(SALIDA / "2_todo_cerrado.png"))

        # 5. Plegarla queda guardado, como las demás.
        pag.locator(tarjeta + " > summary").click()
        pag.reload(); pag.wait_for_selector(tarjeta)
        chequeo("plegada queda plegada al volver", not pag.eval_on_selector(tarjeta, "d => d.open"))
        chequeo("sin errores de JavaScript", not errores, errores)
        nav.close()
    srv.should_exit = True
    print(f"ver_despachos: {len(OK)} bien, {len(MAL)} mal · capturas en {SALIDA}")
    return not MAL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
