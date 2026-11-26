"""Cuanto baja y cuanto tarda la app del celular al abrirse. Mide, no aprueba ni desaprueba.

Nace del 2026-11-23 (Martin: *"la app del celular tambien tiene que andar super
rapidisimo"*). Levanta una COPIA del panel en otro puerto con el codigo del disco, abre
`/movil` en un Chrome con tamaño de telefono, y cuenta lo que viaja: una vez con el
telefono "vacio" y otra como al volver a abrir la app.

⚠ Lo que hace que se pueda correr con el panel de verdad prendido:
  · la copia arranca SIN su arranque (`lifespan="off"`): ni vigias, ni trabajos, ni servicios;
  · todo pedido que no sea de LEER se contesta aca con un "no" y nunca llega al panel;
  · no usa `page.route`: Playwright, con eso puesto, le apaga la memoria al navegador, y
    lo que se quiere medir es justamente cuanto sale de esa memoria.
⚠ Lee las charlas y pestañas REALES (solo lectura). Tarda medio minuto.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.medir_celular
"""
import sys
import threading
import time
import urllib.request
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psutil
import uvicorn
from playwright.sync_api import sync_playwright

import panel
from app.voz import seguir

PUERTO = 8763
BASE = f"http://127.0.0.1:{PUERTO}"


async def solo_leer(scope, receive, send):
    """Delante del panel: lo que no es GET no pasa."""
    if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD"):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok": false}'})
        return
    await panel.app(scope, receive, send)


def main():
    # Los procesos de sesion del panel de verdad, para que la lista cueste lo que cuesta alla.
    for p in psutil.process_iter(["cmdline"]):
        if "panel.py" in " ".join(p.info["cmdline"] or []):
            seguir.PIDS_PANEL.update(h.pid for h in p.children() if h.name().lower() == "cmd.exe")
    servidor = uvicorn.Server(uvicorn.Config(solo_leer, host="127.0.0.1", port=PUERTO,
                                             log_level="error", lifespan="off"))
    threading.Thread(target=servidor.run, daemon=True).start()
    time.sleep(2)
    t = time.time()
    urllib.request.urlopen(BASE + "/movil/sesiones", timeout=180).read()
    print(f"armar la lista por primera vez tras arrancar: {time.time() - t:.1f} s")

    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True, device_scale_factor=3)
        pag = ctx.new_page()
        cdp = ctx.new_cdp_session(pag)
        cdp.send("Network.enable")
        pedidos = {}
        cdp.on("Network.responseReceived", lambda e: pedidos.setdefault(e["requestId"], {}).update(
            url=e["response"]["url"], estado=e["response"]["status"],
            memoria=bool(e["response"].get("fromDiskCache"))))
        cdp.on("Network.loadingFinished", lambda e: pedidos.setdefault(e["requestId"], {}).update(
            bytes=e["encodedDataLength"]))
        cdp.on("Network.requestServedFromCache",
               lambda e: pedidos.setdefault(e["requestId"], {}).update(memoria=True))

        def ruta(x):
            u = x["url"]
            return u.split(str(PUERTO), 1)[1].split("?")[0] if str(PUERTO) in u else u[:30]

        def kb(xs):
            return sum(x.get("bytes", 0) for x in xs) / 1024

        def abrir(nombre, espera=12000):
            pedidos.clear()
            t = time.time()
            pag.goto(BASE + "/movil", wait_until="domcontentloaded")
            lista = time.time() - t
            pag.wait_for_timeout(espera)
            ps = [x for x in pedidos.values() if x.get("url")]
            chats = [x for x in ps if ruta(x) == "/movil/chat"]
            archivos = [x for x in ps if ruta(x).startswith("/estaticos/")]
            fondo = [x for x in ps if ruta(x) == "/fondo/windows"]
            print(f"\n== {nombre} ==")
            print(f"pagina lista en {lista:.2f} s | {len(ps)} pedidos en {espera // 1000} s | "
                  f"{kb(ps):.0f} KB bajados en total")
            print(f"  la pagina: {kb([x for x in ps if ruta(x) == '/movil']):.0f} KB")
            print(f"  sus {len(archivos)} archivos: {kb(archivos):.0f} KB "
                  f"({sum(1 for x in archivos if x.get('memoria'))} salieron de la memoria del telefono)")
            print(f"  la foto de fondo: {len(fondo)} pedidos, {kb(fondo):.0f} KB "
                  f"({sum(1 for x in fondo if x.get('memoria'))} de la memoria)")
            print(f"  charlas distintas pedidas: {len({x['url'] for x in chats})} | {kb(chats):.0f} KB "
                  f"en {len(chats)} pedidos")
            print(f"  lista de charlas: {kb([x for x in ps if ruta(x) == '/movil/sesiones']):.0f} KB")
            print(f"  respuestas 'no cambio' (304): {sum(1 for x in ps if x.get('estado') == 304)}")
            print("  los 5 mas pesados: " + ", ".join(
                f"{ruta(x)} {x.get('bytes', 0) / 1024:.0f} KB"
                for x in sorted(ps, key=lambda x: -x.get("bytes", 0))[:5]))

        abrir("Primera vez (telefono sin nada guardado)")
        pag.goto("about:blank")
        abrir("Segunda vez (como al volver a abrir la app)")
        nav.close()


if __name__ == "__main__":
    main()
