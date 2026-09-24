"""Que la bandeja se refresque sola: al volver de una charla a "Todas" no puede
quedar mostrando lo de antes. Cuenta los pedidos a /movil/sesiones."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    nav = p.chromium.launch()
    pag = nav.new_page(viewport={"width": 1500, "height": 900})
    errores, pedidos = [], []
    pag.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("request", lambda r: pedidos.append(r.url) if "/movil/sesiones" in r.url else None)

    pag.goto("http://127.0.0.1:8750/sesiones")
    pag.wait_for_timeout(2500)
    print("arranca en:", pag.inner_text("h1, .titulo, #titulo").split("\n")[0])
    print("pedidos al cargar:", len(pedidos))

    filas = pag.query_selector_all(".correo")
    print("conversaciones en la bandeja:", len(filas))

    # entrar a una conversación y volver: tiene que pedir la lista de nuevo
    antes = len(pedidos)
    if filas:
        filas[0].click()
        pag.wait_for_timeout(1500)
        pag.click(".carpeta")
        pag.wait_for_timeout(1500)
    print("pedidos tras volver a Todas:", len(pedidos) - antes)

    # y sola, sin tocar nada
    antes = len(pedidos)
    pag.wait_for_timeout(9000)
    print("pedidos en 9 s quieto:", len(pedidos) - antes)

    print("errores de javascript:", errores or "ninguno")
    pag.screenshot(path="pruebas/bandeja_viva.png")
    nav.close()
