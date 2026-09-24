"""Mira la tarjeta de la placa de video del panel, con el servidor inventado.

No necesita el panel prendido ni reiniciarlo: sirve `panel.PAGINA` interceptado con
`page.route`, como `ver_encabezado_panel.py`. Prueba los tres estados que importan:
la placa con modelos adentro, Ollama apagado (que se pueda PRENDER) y la maquina sin
placa NVIDIA (la tarjeta se esconde entera).

    python -m pruebas.ver_placa
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # los emojis del titulo

from playwright.sync_api import sync_playwright

import panel
from app.rutas import RESULTADOS, ESTATICOS

SALIDA = RESULTADOS / "capturas"
ok = fallas = 0

LLENA = {"ok": True, "usado": 6101, "total": 8188, "pct": 75,
         "placa": "NVIDIA GeForce RTX 4070 Laptop GPU",
         "procesos": [
             {"pid": 55696, "nombre": "Voz de Laura", "servicio": "voz",
              "detalle": "Whisper turbo + la palabra clave + Piper",
              "cmd": "python.exe -m app.voz.voz"},
             {"pid": 53360, "nombre": "Bot de Telegram", "servicio": "telegram",
              "detalle": "Whisper para los audios que entran",
              "cmd": "python.exe -m app.ingesta.bot_telegram"},
             {"pid": 61000, "nombre": "ComfyUI", "servicio": "",
              "detalle": "algo que prendiste por afuera", "cmd": "python.exe comfyui"},
         ],
         # Los dos que el panel sabe prender: apagados, o sea con boton Prender.
         "modelos": [
             {"clave": "ollama", "nombre": "Ollama", "detalle": "el cerebro chico local",
              "instalado": True, "vivo": False, "cargando": False, "puerto": 11434},
             {"clave": "hunyuan", "nombre": "Generador 3D (Hunyuan)",
              "detalle": "Hunyuan3D 2mini, imagen a modelo 3D",
              "instalado": True, "vivo": False, "cargando": False, "puerto": 7860},
         ]}

# Ollama prendido con un modelo adentro, y el Hunyuan todavia cargando sus pesos.
TOPE = {**LLENA, "usado": 8000, "pct": 98,
        "modelos": [
            {"clave": "ollama", "nombre": "Ollama", "detalle": "", "instalado": True,
             "vivo": True, "cargando": False, "puerto": 11434, "cargados": ["qwen2.5:7b"]},
            {"clave": "hunyuan", "nombre": "Generador 3D (Hunyuan)", "detalle": "",
             "instalado": True, "vivo": False, "cargando": True, "puerto": 7860},
        ]}

SIN_PLACA = {"ok": False, "error": "No encontre nvidia-smi.", "modelos": []}

# ⭐ El caso que trajo Martin: 1 GB usado y NINGUN modelo. Ese giga es Windows.
SIN_MODELOS = {"ok": True, "usado": 1008, "total": 8188, "pct": 12,
               "placa": "NVIDIA GeForce RTX 4070 Laptop GPU", "procesos": [],
               "escritorio": {"cuantos": 20,
                              "nombres": ["el escritorio", "el navegador", "WhatsApp"]},
               "modelos": LLENA["modelos"]}


def chequeo(titulo, cond, detalle=""):
    global ok, fallas
    if cond:
        ok += 1
        print(f"  OK   {titulo}")
    else:
        fallas += 1
        print(f"  MAL  {titulo} {detalle}")


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    estado = {"d": LLENA}
    apagados = []

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1500, "height": 1000})
        pag.on("pageerror", lambda e: print("  error de JS:", e))
        # ⚠ Playwright prueba las rutas de la ULTIMA a la primera: el comodin va PRIMERO.
        pag.route("**/*", lambda r: r.fulfill(status=200,
                                              content_type="application/json", body="{}"))
        pag.route("**/estaticos/menu.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript",
            body=(ESTATICOS / "menu.js").read_text(encoding="utf-8")))
        pag.route("**/placa", lambda r: r.fulfill(json=estado["d"]))
        pag.route("**/placa/apagar/*", lambda r: (
            apagados.append(r.request.url.rsplit("/", 1)[-1]),
            r.fulfill(json={"ok": True, "nombre": "eso"}))[1])
        # ⚠ `*` no cruza barras y la URL tiene DOS segmentos (`/hunyuan/prender`): con
        # `*` el comodin de arriba se la comia y contestaba "{}" sin que se notara.
        pag.route("**/placa/modelo/**", lambda r: (
            apagados.append("/".join(r.request.url.split("/")[-2:])),
            r.fulfill(json={"ok": True}))[1])
        pag.route("**/panel-de-prueba", lambda r: r.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=panel.PAGINA))
        # El confirm de "¿Apagar …?": se acepta solo, si no la prueba queda colgada.
        pag.on("dialog", lambda d: d.accept())

        pag.goto("http://panel.local/panel-de-prueba", wait_until="domcontentloaded")
        pag.wait_for_timeout(1200)

        print("Con la placa ocupada")
        bq = pag.locator("#bqPlaca")
        chequeo("la tarjeta se ve", bq.is_visible())
        txt = pag.locator("#plcTxt").inner_text()
        chequeo("dice cuanto va usado en GB", "6,0 GB de 8,0 GB" in txt, txt)
        chequeo("y de que placa habla", "RTX 4070" in txt, txt)
        chequeo("no repite la marca larga", "NVIDIA GeForce" not in txt, txt)
        barra = pag.locator("#plcBarra")
        chequeo("la barra sigue al porcentaje", barra.evaluate("e=>e.style.width") == "75%")
        chequeo("a 75% todavia no esta en alarma",
                barra.get_attribute("class") == "", barra.get_attribute("class"))
        filas = pag.locator("#plcLista .svc")
        chequeo("una fila por hallazgo + una por modelo", filas.count() == 5, filas.count())
        lista = pag.locator("#plcLista").inner_text()
        chequeo("aparece la Voz", "Voz de Laura" in lista)
        chequeo("los servicios del panel se identifican", "servicio del panel" in lista)
        chequeo("lo prendido por afuera igual se ve", "ComfyUI" in lista)
        chequeo("Ollama aparece aunque este apagado", "Ollama" in lista)
        chequeo("el generador 3D tambien", "Generador 3D (Hunyuan)" in lista, lista)
        chequeo("los dos ofrecen PRENDERSE",
                lista.count("Prender") == 2, lista.count("Prender"))
        pag.screenshot(path=str(SALIDA / "placa_ocupada.png"))

        print("\nApagar algo")
        pag.locator("#plcLista .svc").first.locator(".mini").click()
        pag.wait_for_timeout(600)
        chequeo("el boton manda el pid correcto", "55696" in apagados, apagados)

        print("\nPrender el generador 3D")
        pag.locator("#plcLista .svc").last.locator(".mini").click()
        pag.wait_for_timeout(600)
        chequeo("pide prender el hunyuan", "hunyuan/prender" in apagados, apagados)

        print("\nCon la placa al tope, Ollama cargado y el Hunyuan cargando")
        estado["d"] = TOPE
        pag.evaluate("pintarPlaca()")
        pag.wait_for_timeout(700)
        chequeo("a 98% la barra avisa",
                pag.locator("#plcBarra").get_attribute("class") == "tope")
        lista = pag.locator("#plcLista").inner_text()
        chequeo("dice QUE modelo tiene cargado Ollama", "qwen2.5:7b" in lista, lista)
        chequeo("y ahora ofrece apagarlo", "Apagar" in lista)
        chequeo("el que carga avisa que carga", "cargando" in lista, lista)
        # ⚠ Apagarlo a mitad de cargar deja los pesos por la mitad: no tiene que haber boton.
        ultima = pag.locator("#plcLista .svc").last
        chequeo("mientras carga no hay boton", ultima.locator(".mini").count() == 0)
        pag.screenshot(path=str(SALIDA / "placa_tope.png"))

        print("\nCon la placa usada pero SIN ningun modelo (la pregunta de Martin)")
        estado["d"] = SIN_MODELOS
        pag.evaluate("pintarPlaca()")
        pag.wait_for_timeout(700)
        lista = pag.locator("#plcLista").inner_text()
        chequeo("dice que no hay ningun modelo", "Ningún modelo cargado" in lista, lista)
        chequeo("y de quien es entonces ese giga", "Windows dibujando" in lista, lista)
        chequeo("con cuantos programas son", "20 programas" in lista, lista)
        chequeo("y algunos nombres", "el escritorio" in lista, lista)
        chequeo("los dos modelos se siguen pudiendo prender",
                lista.count("Prender") == 2, lista.count("Prender"))
        pag.screenshot(path=str(SALIDA / "placa_sin_modelos.png"))

        print("\nEn una maquina sin placa NVIDIA")
        estado["d"] = SIN_PLACA
        pag.evaluate("pintarPlaca()")
        pag.wait_for_timeout(700)
        chequeo("la tarjeta se esconde entera",
                not pag.locator("#bqPlaca").is_visible())

        nav.close()

    print(f"\n{ok} en verde, {fallas} en rojo")
    print("capturas en", SALIDA)
    if fallas:
        raise SystemExit(1)


main()
