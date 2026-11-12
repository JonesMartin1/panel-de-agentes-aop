"""La tarjeta "Enlaces y archivos" EN PANTALLA, con un Chrome de verdad (Playwright).

    python -m pruebas.ver_fijados

Levanta un servidor chico aparte (otro puerto, no el panel) con el `entorno.js` real, las
rutas reales de `fijados.py` sobre un archivo de datos temporal, y un `/movil/entorno` falso
que cambia en cada pedido para forzar el redibujo, como pasa con el panel de verdad.
Nunca abre ninguna ventana: `os.startfile` y el Explorador se reemplazan por anotadores.
Deja las capturas en resultados/ver_fijados/.
"""
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS, RESULTADOS
from app.voz import fijados

SALIDA = RESULTADOS / "ver_fijados"
OK, MAL = [], []
ABIERTOS, MOSTRADOS = [], []
ESTADO = {"viejo": False, "n": 0}


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    print(("  ✓ " if cond else "  ✗ ") + nombre + ("" if cond else f"  {detalle}"))


def armar(cwd):
    app = FastAPI()

    @app.middleware("http")
    async def panel_viejo(request: Request, siguiente):
        if ESTADO["viejo"] and request.url.path.startswith("/fijados"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await siguiente(request)

    app.include_router(fijados.crear_router())

    @app.get("/estaticos/entorno.js")
    def js():
        return FileResponse(ESTATICOS / "entorno.js", headers={"Cache-Control": "no-store"})

    @app.get("/movil/entorno")
    def entorno():
        ESTADO["n"] += 1           # cambia en cada pedido: obliga a redibujar, como en el panel
        return {"ok": True, "maquina": "MartinLaptop", "carpeta": cwd, "nombre": "proyecto",
                "remoto_posible": False, "cerebro": "claude",
                "contexto": {"tokens": 40000 + ESTADO["n"] * 1000, "tope": 200000},
                "conectores": [{"nombre": "kapso", "estado": ""}], "conectores_de": "configurados"}

    @app.get("/")
    def pagina():
        return HTMLResponse("""<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#0f1420;font-family:Segoe UI,system-ui,sans-serif">
<div id="caja" class="entornoCaja" style="width:300px;padding:12px"></div>
<script src="/estaticos/entorno.js"></script>
<script>
  const u = {cwd: %r, sid: 'ses-uno', nombre: 'proyecto'};
  window.cambiarSid = s => { u.sid = s; refrescar(); };
  async function refrescar(){ try { Entorno.pintar(document.getElementById('caja'), await Entorno.pedir(u), u); } catch(e){} }
  Entorno.iniciar({ubicacion: () => u, alCambiar: refrescar});
  refrescar(); setInterval(refrescar, 300);
</script>""" % cwd)
    return app


def puerto_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ver_fijados_"))
    fijados.FIJADOS = tmp / "fijados.json"
    fijados.os.startfile = lambda ruta: ABIERTOS.append(ruta)
    fijados._mostrar_en_explorador = lambda ruta: MOSTRADOS.append(str(ruta))
    proyecto = tmp / "proyecto"; proyecto.mkdir()
    (proyecto / "Presupuesto cliente.pdf").write_bytes(b"%PDF-1.4")
    (proyecto / "instalar.exe").write_bytes(b"MZ")
    SALIDA.mkdir(parents=True, exist_ok=True)

    puerto = puerto_libre()
    srv = uvicorn.Server(uvicorn.Config(armar(str(proyecto)), host="127.0.0.1", port=puerto,
                                        log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{puerto}/"
    tarjeta = "details.tarjDer[data-t='fijados']"
    MAS_P = tarjeta + " [data-fij-mas='proyecto']"
    MAS_S = tarjeta + " [data-fij-mas='sesion']"

    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pag = nav.new_page(viewport={"width": 324, "height": 640})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        # 1. Panel sin reiniciar: la columna queda como hoy.
        ESTADO["viejo"] = True
        pag.goto(base)
        pag.wait_for_selector("details.tarjDer[data-t='entorno']")
        pag.wait_for_timeout(800)
        chequeo("panel viejo: no aparece la tarjeta", pag.locator(tarjeta).count() == 0)
        chequeo("panel viejo: el resto se dibuja igual",
                pag.locator("details.tarjDer").count() == 3, pag.locator("details.tarjDer").count())
        pag.screenshot(path=str(SALIDA / "1_panel_viejo.png"))

        # 2. Panel nuevo: aparece debajo de Entorno, vacía y con la explicación.
        ESTADO["viejo"] = False
        pag.reload()
        pag.wait_for_selector(tarjeta)
        orden = pag.eval_on_selector_all("details.tarjDer", "ds => ds.map(d => d.dataset.t)")
        chequeo("aparece segunda, debajo de Entorno", orden[:2] == ["entorno", "fijados"], orden)
        chequeo("vacía: dos apartados, Proyecto y Esta sesión, cada uno con «+ Agregar»",
                pag.eval_on_selector_all(tarjeta + " .fijSec", "s => s.map(x => x.textContent)")
                == ["Proyecto", "Esta sesión"]
                and pag.locator(MAS_P).count() == 1 and pag.locator(MAS_S).count() == 1
                and pag.locator(tarjeta + " .fijForm").count() == 0
                and pag.locator(tarjeta + " .notaDer").count() == 0)
        pag.screenshot(path=str(SALIDA / "2_vacia.png"))

        # 3. «+ Agregar» abre la caja con el foco; escribir despacio mientras la columna se
        #    refresca cada 300 ms no borra nada.
        pag.locator(MAS_P).click()
        caja = pag.locator(tarjeta + " .fijForm input")
        chequeo("«+ Agregar» abre la caja con el foco",
                caja.count() == 1 and pag.evaluate("document.activeElement && document.activeElement.name === 't'"))
        texto = "https://github.com/JonesMartin1/wpp-transcriptor"
        caja.press_sequentially(texto, delay=45)
        pag.wait_for_timeout(900)
        chequeo("lo escrito sobrevive a los refrescos", caja.input_value() == texto, caja.input_value())
        pag.screenshot(path=str(SALIDA / "3_escribiendo.png"))
        caja.press("Enter")
        pag.wait_for_function("document.querySelectorAll(\"details[data-t='fijados'] .fij\").length === 1")
        chequeo("Enter agrega el enlace", "github.com/JonesMartin1" in pag.inner_text(tarjeta))
        pag.wait_for_timeout(400)
        chequeo("y la caja se cierra sola", pag.locator(tarjeta + " .fijForm").count() == 0
                and pag.locator(MAS_P).count() == 1)
        href = pag.get_attribute(tarjeta + " .fij a", "href")
        chequeo("el enlace abre en pestaña nueva",
                href == texto and pag.get_attribute(tarjeta + " .fij a", "target") == "_blank", href)

        # Esc cancela, y salir de la caja vacía también la cierra.
        pag.locator(MAS_P).click()
        pag.locator(tarjeta + " .fijForm input").fill("algo a medias")
        pag.keyboard.press("Escape")
        pag.wait_for_timeout(400)
        chequeo("Esc cancela", pag.locator(tarjeta + " .fijForm").count() == 0
                and pag.locator(tarjeta + " .fij").count() == 1)
        pag.locator(MAS_P).click()
        pag.locator("details.tarjDer[data-t='entorno'] summary").click()
        pag.locator("details.tarjDer[data-t='entorno'] summary").click()
        pag.wait_for_timeout(500)
        chequeo("salir de la caja vacía la cierra", pag.locator(tarjeta + " .fijForm").count() == 0)

        # 4. Un archivo y un programa.
        for ruta in ('"' + str(proyecto / "Presupuesto cliente.pdf") + '"', str(proyecto / "instalar.exe")):
            pag.locator(MAS_P).click()
            pag.locator(tarjeta + " .fijForm input").fill(ruta)
            pag.locator(tarjeta + " .fijForm input").press("Enter")
            pag.wait_for_timeout(500)
        chequeo("se agregan el archivo y el programa", pag.locator(tarjeta + " .fij").count() == 3,
                pag.locator(tarjeta + " .fij").count())
        chequeo("el resumen cuenta 3", pag.inner_text(tarjeta + " summary .resumen") == "3")
        pag.locator(tarjeta + " button.txt", has_text="Presupuesto cliente.pdf").click()
        pag.wait_for_timeout(500)
        chequeo("clic en el PDF lo abre en la compu",
                len(ABIERTOS) == 1 and ABIERTOS[0].endswith("Presupuesto cliente.pdf"), ABIERTOS)
        chequeo("y lo avisa", "Abierto en la compu" in pag.inner_text(tarjeta))
        pag.locator(tarjeta + " button.txt", has_text="instalar.exe").click()
        pag.wait_for_timeout(500)
        chequeo("clic en el .exe NO lo corre", len(ABIERTOS) == 1 and len(MOSTRADOS) == 1,
                (ABIERTOS, MOSTRADOS))
        chequeo("y explica por qué", "Es un programa" in pag.inner_text(tarjeta))
        pag.mouse.move(5, 600)
        pag.wait_for_timeout(300)
        pag.screenshot(path=str(SALIDA / "4_con_tres.png"))

        # 5. Algo que no es enlace ni ruta.
        pag.locator(MAS_P).click()
        pag.locator(tarjeta + " .fijForm input").fill("javascript:alert(1)")
        pag.locator(tarjeta + " .fijForm input").press("Enter")
        pag.wait_for_timeout(500)
        chequeo("javascript: se rechaza y avisa",
                pag.locator(tarjeta + " .fijAviso.mal").count() == 1
                and pag.locator(tarjeta + " .fij").count() == 3)
        chequeo("lo rechazado queda en la caja para corregirlo",
                pag.locator(tarjeta + " .fijForm input").input_value() == "javascript:alert(1)")
        antes = pag.inner_text("details.tarjDer[data-t='contexto'] summary")
        pag.wait_for_timeout(900)
        chequeo("con texto en la caja, la columna sigue viva (Contexto cambia)",
                pag.inner_text("details.tarjDer[data-t='contexto'] summary") != antes)
        pag.screenshot(path=str(SALIDA / "5_rechazo.png"))

        # 6. Sacar una fila.
        fila = pag.locator(tarjeta + " .fij", has_text="instalar.exe")
        fila.hover()
        fila.locator(".fijQuitar").click()
        pag.wait_for_timeout(500)
        chequeo("la × saca la fila", pag.locator(tarjeta + " .fij").count() == 2)

        # 6b. El apartado de la SESIÓN: lo de acá no lo ve otra charla, lo del proyecto sí.
        pag.locator(MAS_S).click()
        pag.locator(tarjeta + " .fijForm[data-ambito='sesion'] input").fill("https://tarea.com/123")
        pag.locator(tarjeta + " .fijForm input").press("Enter")
        pag.wait_for_timeout(600)
        sec = "(() => { const d = document.querySelector(\"details[data-t='fijados']\"); let a = ''; const r = {proyecto: [], sesion: []};"               " for (const n of d.querySelectorAll('.fijSec, .fij')) { if (n.classList.contains('fijSec')) a = n.textContent === 'Proyecto' ? 'proyecto' : 'sesion';"               " else r[a].push(n.innerText.replace('×','').replace(/\s+/g,'').trim()); } return r; })()"
        r = pag.evaluate(sec)
        chequeo("lo agregado en la sesión queda en su apartado",
                r["sesion"] == ["🔗tarea.com/123"] and "🔗tarea.com/123" not in r["proyecto"], r)
        pag.screenshot(path=str(SALIDA / "6_dos_apartados.png"))
        pag.evaluate("cambiarSid('ses-dos')")
        pag.wait_for_timeout(700)
        r2 = pag.evaluate(sec)
        chequeo("en otra charla: el proyecto sigue, la sesión está vacía",
                r2["proyecto"] == r["proyecto"] and r2["sesion"] == [], r2)
        pag.evaluate("cambiarSid('')")
        pag.wait_for_timeout(700)
        chequeo("charla sin id: no aparece el apartado de la sesión",
                pag.locator(MAS_S).count() == 0 and pag.locator(MAS_P).count() == 1)
        pag.evaluate("cambiarSid('ses-uno')")
        pag.wait_for_timeout(700)
        fila = pag.locator(tarjeta + " .fij", has_text="tarea.com")
        fila.hover(); fila.locator(".fijQuitar").click()
        pag.wait_for_timeout(600)
        chequeo("la × de la sesión saca solo esa", pag.evaluate(sec)["sesion"] == []
                and pag.evaluate(sec)["proyecto"] == r["proyecto"])

        # 7. Plegar la tarjeta queda guardado.
        pag.locator(tarjeta + " > summary").click()
        pag.reload(); pag.wait_for_selector(tarjeta)
        pag.wait_for_timeout(500)
        chequeo("plegada queda plegada al volver", not pag.eval_on_selector(tarjeta, "d => d.open"))
        chequeo("sin errores de JavaScript", not errores, errores)
        nav.close()
    srv.should_exit = True
    print(f"ver_fijados: {len(OK)} bien, {len(MAL)} mal · capturas en {SALIDA}")
    return not MAL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
