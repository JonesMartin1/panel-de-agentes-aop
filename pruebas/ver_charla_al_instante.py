"""Mandar un mensaje o cambiar de charla se ve AL INSTANTE, aunque el panel tarde (2026-11-10).

Pedido de Martín: *"cuando mando un prompt o una conversación, tarda en cambiar en el
panel y yo necesito que sea algo automático e inmediato"*.

La causa, leída en el código: en `/sesiones` cada repintado esperaba la respuesta de
`/movil/chat` antes de dibujar nada. Mandabas un mensaje y tu burbuja no aparecía hasta que
volvía el pedido; cambiabas de pestaña y seguías viendo la charla anterior. Ahora la pantalla
guarda lo último que vio de cada charla (`chatVisto`) y dibuja con eso en el mismo instante,
mientras pide lo fresco.

    python -m pruebas.ver_charla_al_instante
    python -m pruebas.ver_charla_al_instante --viejo     (el HTML de git: tienen que caer)

Lo que esta prueba cuida:
  · que con el panel LENTO (acá se le agregan 3 s a cada respuesta) cambiar de pestaña y
    mandar un mensaje cambien la pantalla en el mismo instante, sin esperar esos 3 s;
  · que la memoria no reemplace al disco: después del dibujo instantáneo se pide lo fresco
    igual, y el repintado de cada 3 s sigue pidiendo siempre;
  · que con el panel lento los pedidos no se apilen (uno por vez).

⚠ Datos inventados, interceptados en el contexto: no se lee ni se escribe ninguna charla de
verdad, y nada que no sea un GET sale hacia el panel (un envío de prueba no puede llegar).
⚠ "En el mismo instante" se mide SIN reloj: se cambia de pestaña y se lee la pantalla dentro
de la misma llamada, antes de que pueda volver ningún pedido. Un chequeo por milisegundos
daría verde o rojo según cómo esté de cargada la máquina.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8750"
VIEJO = "--viejo" in sys.argv
AHORA = time.time()
fallas = []


def ses(sid, nombre):
    return {"id": sid, "nombre": nombre, "ts": AHORA - 600, "ultimo": "claude",
            "viva": False, "ocupada": False, "interactiva": False, "detalle": "x"}


SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": ["alfa"], "ocultas": []},
            "proyectos": [{"proyecto": "alfa", "cwd": "D:\\pruebas\\alfa", "vivo": False,
                           "sesiones": [ses("alfa-1", "la primera"), ses("alfa-2", "la segunda")]}]}
# Lo que contesta el chat de cada charla. Se cambia a mano durante la prueba.
HILOS = {"alfa-1": ["soy la primera"], "alfa-2": ["soy la segunda"]}

# El panel "lento": a cada pedido del chat se le agrega una demora ADENTRO de la página, y se
# anotan. ⚠ No se demora en el interceptor de Python: ahí frenaría a la prueba entera y no se
# podría mirar la pantalla mientras el pedido está en vuelo, que es justo lo que se mide.
ESPIA = """
window.__demora = 0; window.__pedidos = [];
const __fetch = window.fetch;
window.fetch = async (u, o) => {
  if (String(u).startsWith('/movil/chat')){
    window.__pedidos.push(String(u));
    if (window.__demora) await new Promise(r => setTimeout(r, window.__demora));
  }
  return __fetch(u, o);
};
"""


def revisar(nombre, condicion, detalle=""):
    print(("ok   " if condicion else "MAL  ") + nombre + (f"  -> {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallas.append(nombre)


def portero(r):
    camino, _, consulta = r.request.url.split(BASE, 1)[-1].partition("?")
    if camino == "/sesiones" and VIEJO:
        html = subprocess.run(["git", "show", "HEAD:app/estaticos/sesiones.html"], cwd=RAIZ,
                              capture_output=True, check=True).stdout
        return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
    if camino == "/movil/sesiones":
        cuerpo = SESIONES
    elif camino == "/movil/chat":
        sid = consulta.split("sid=")[-1].split("&")[0]
        cuerpo = {"ok": True, "ocupada": False, "pregunta": None, "tareas": None,
                  "mensajes": [{"de": "claude", "texto": t, "imgs": []} for t in HILOS.get(sid, [])]}
    elif camino == "/aspecto" and r.request.method == "GET":
        cuerpo = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
                  "letra": "normal", "velo": "media", "rastro": "tema"}
    elif r.request.method != "GET" or camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
        cuerpo = {"ok": True}
    else:
        return r.continue_()
    return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))


HILO = "() => (document.querySelector('#hilo') || {innerText: ''}).innerText"
PEDIDOS = "s => window.__pedidos.filter(u => u.includes('sid=' + s)).length"

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores = []
    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    pag.add_init_script("localStorage.clear();" + ESPIA)
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=15000)
    pag.wait_for_timeout(500)
    pag.evaluate("""() => { pendientes = {}; falladas = {}; visto = {};
      abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'la primera', cerebro: ''},
                  {sid: 'alfa-2', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'la segunda', cerebro: ''}];
      guardar(); pintarTabs(); irTab('alfa-1'); }""")
    pag.wait_for_function("() => (document.querySelector('#hilo') || {innerText: ''})"
                          ".innerText.includes('soy la primera')", timeout=10000)
    print("\nCon el panel rápido: se abren las dos charlas una vez, para que la pantalla las conozca")
    pag.evaluate("() => irTab('alfa-2')")
    pag.wait_for_function("() => document.querySelector('#hilo').innerText.includes('soy la segunda')",
                          timeout=10000)
    pag.evaluate("() => irTab('alfa-1')")
    pag.wait_for_function("() => document.querySelector('#hilo').innerText.includes('soy la primera')",
                          timeout=10000)
    pag.wait_for_timeout(400)

    print("\nAhora el panel tarda 3 segundos en contestar cada pedido")
    pag.evaluate("() => { window.__demora = 3000; }")
    antes = pag.evaluate(PEDIDOS, "alfa-2")
    visto = pag.evaluate("() => { irTab('alfa-2'); return document.querySelector('#hilo').innerText; }")
    revisar("al cambiar de pestaña, la otra charla ya está dibujada en el mismo instante",
            "soy la segunda" in visto, repr(visto[:60]))
    pag.wait_for_timeout(300)
    revisar("y lo fresco se pide igual (la memoria no reemplaza al panel)",
            pag.evaluate(PEDIDOS, "alfa-2") > antes)
    HILOS["alfa-2"].append("esto llegó después")
    pag.wait_for_function("() => document.querySelector('#hilo').innerText.includes('esto llegó después')",
                          timeout=12000)
    revisar("cuando vuelve el pedido, lo nuevo reemplaza a lo de memoria", True)

    visto = pag.evaluate("""() => { document.querySelector('#texto').value = 'mensaje de prueba al instante';
                                    mandar(); return document.querySelector('#hilo').innerText; }""")
    revisar("al mandar un mensaje, tu burbuja aparece en el mismo instante",
            "mensaje de prueba al instante" in visto, repr(visto[-80:]))

    print("\nCon el panel MUY lento (9 s por pedido): los pedidos no se apilan")
    pag.evaluate("() => irTab('alfa-1')")
    pag.wait_for_timeout(300)
    pag.evaluate("() => { window.__demora = 9000; }")
    pag.wait_for_timeout(3600)              # un tic del reloj de 3 s larga un pedido lento
    en_vuelo = pag.evaluate(PEDIDOS, "alfa-1")
    pag.wait_for_timeout(6600)              # dos tics más, con aquel todavía en vuelo
    nuevos = pag.evaluate(PEDIDOS, "alfa-1") - en_vuelo
    revisar("mientras un pedido sigue en vuelo, el reloj de 3 s no larga otro arriba",
            nuevos == 0, f"largó {nuevos} más")

    print("\nY con el panel otra vez rápido")
    pag.evaluate("() => { window.__demora = 0; }")
    pag.wait_for_timeout(9500)              # que vuelvan los lentos que quedaron en vuelo
    base = pag.evaluate(PEDIDOS, "alfa-1")
    pag.wait_for_timeout(7000)
    revisar("el repintado de cada 3 s sigue pidiendo siempre (nunca se queda con la memoria)",
            pag.evaluate(PEDIDOS, "alfa-1") - base >= 2, str(pag.evaluate(PEDIDOS, "alfa-1") - base))
    revisar("sin errores de JavaScript en la página", not errores, "; ".join(errores)[:200])
    nav.close()

if VIEJO:
    clave = {"al cambiar de pestaña, la otra charla ya está dibujada en el mismo instante",
             "al mandar un mensaje, tu burbuja aparece en el mismo instante",
             "mientras un pedido sigue en vuelo, el reloj de 3 s no larga otro arriba"}
    cayeron = clave & set(fallas)
    print(f"\n{'LA PRUEBA SIRVE' if cayeron == clave else 'HAY CHEQUEOS DE ADORNO'} — con el HTML "
          f"de git caen {len(cayeron)} de los {len(clave)} chequeos clave\n")
    raise SystemExit(0 if cayeron == clave else 1)
print(f"\n{'TODO BIEN' if not fallas else 'HAY PROBLEMAS'} — {len(fallas)} mal\n")
raise SystemExit(1 if fallas else 0)
