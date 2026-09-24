"""Elegir el color de una parte tiene que PINTAR esa parte, en las cuatro pantallas.

Pedido de Martin el 2026-08-29: "quiero poder editar el color de algunos elementos de la
pizarra... no solo de la pizarra, tambien del panel principal". Eligio cuatro partes: las
burbujas del chat, los botones y los estados (el semaforo), la barra de arriba, y la barra
de herramientas de la pizarra.

Lo que esta prueba comprueba de verdad, y no de palabra:

  1. SIN elegir nada, todo se ve como antes. Es lo mas importante: el cambio no puede
     cambiarle la pantalla a quien no pidio nada. El verde de "encendido" tiene que seguir
     saliendo verde, y la barra de arriba del panel tiene que seguir siendo transparente.
  2. CON un color elegido, el elemento se pinta de ese color. Se usa magenta puro
     (#ff00ff) a proposito: no se parece a nada de la pantalla, asi que si aparece es
     porque la variable llego hasta ahi y no porque algo ya era parecido.
  3. Las dos barras conviven con UNA sola variable y dos "como estaba" distintos: el
     encabezado del panel es transparente y la barra de la pizarra tiene su fondo. Por eso
     `--barra` no se define cuando no hay color elegido (si se definiera, aunque fuera en
     `transparent`, le ganaria al respaldo y la pizarra quedaria de vidrio).

⚠ No necesita el panel prendido ni toca ninguna sesion: las paginas se leen del `panel.py`
y del `sesiones.html` DEL DISCO, y el servidor esta inventado aca adentro con `route`. Por
eso ve el codigo recien escrito y no el que el panel tiene cargado en memoria.

Con `--viejo` sirve las paginas como estaban en git (`HEAD`) y exige que los chequeos
marcados como clave FALLEN: un chequeo que no puede fallar no prueba nada.

⚠ Clave son SOLO los que miran un elemento de la PANTALLA (el puntito, el boton Prender,
las dos barras). Los que leen la variable de CSS no pueden fallar con --viejo y no estan
marcados: el motor (`aspecto.js`) se sirve del disco en las dos corridas a proposito, asi
que la variable existe igual. Marcarlos como clave los volvia decoracion, que es la trampa
en la que ya se cayo dos veces en este repo.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_colores_por_parte
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VIEJO = "--viejo" in sys.argv
BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
MAGENTA = "#ff00ff"
RGB_MAGENTA = "rgb(255, 0, 255)"

fallas, claves_ok = [], []
# ⚠ Las capturas de la corrida --viejo van a otro archivo: con el mismo nombre pisaban a
# las buenas, y despues uno mira el PNG y ve la pantalla VIEJA creyendo que es la nueva.
# (Me paso: se pierden diez minutos buscando un bug que no existe.)
SUFIJO = "_viejo" if VIEJO else ""


def revisar(que, ok, detalle="", clave=False):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if clave:
        claves_ok.append((que, ok))


def de_git(ruta):
    """El archivo como esta en git. Sirve para reponer el defecto y verificar al reves."""
    return subprocess.run(["git", "show", f"HEAD:{ruta}"], cwd=RAIZ,
                          capture_output=True, text=True, encoding="utf-8").stdout


def constante(nombre, fuente):
    """El texto de una constante de panel.py, sin importar el modulo (que levantaria
    FastAPI entero). El arbol de sintaxis lo da sin ejecutar una linea."""
    for nodo in ast.parse(fuente).body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == nombre):
            return ast.literal_eval(nodo.value)
    raise SystemExit(f"No encontre {nombre} en panel.py")


def paginas():
    panel_py = de_git("panel.py") if VIEJO else (RAIZ / "panel.py").read_text(encoding="utf-8")
    ses = (de_git("app/estaticos/sesiones.html") if VIEJO
           else (ESTATICOS / "sesiones.html").read_text(encoding="utf-8"))
    return {"panel": constante("PAGINA", panel_py),
            "celular": constante("MOVIL_HTML", panel_py),
            "pizarra": constante("PAGINA_PIZARRA", panel_py),
            "sesiones": ses}


def montar(pag, html, aspecto):
    """Sirve la pagina con el aspecto pedido y todo lo demas cortado.

    El `aspecto.js` va del disco SIEMPRE (tambien con --viejo): lo que se esta verificando
    es que las PANTALLAS usen las variables, no el motor que las calcula.
    """
    # ⚠ EL ORDEN IMPORTA Y ES AL REVES DE LO QUE PARECE: Playwright prueba las rutas de la
    # ULTIMA registrada a la primera, asi que el atrapatodo va PRIMERO y lo especifico
    # despues. Al reves, el atrapatodo se comia el `/aspecto` y la pagina se pintaba con
    # los colores de fabrica: la prueba fallaba entera por si misma, no por el codigo.
    # Todo lo que no sea pantalla se contesta vacio: esto mira colores, no datos, y sin eso
    # la pagina se queda esperando al panel.
    pag.route(f"{BASE}/**", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "items": [], "proyectos": [], "mensajes": [],
                         "servicios": {}})))
    pag.route(BASE + "/", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    pag.route("**/pizarra/rough.js", lambda r: r.fulfill(status=200, body=""))
    pag.route("**/fondo/**", lambda r: r.fulfill(status=200, body=""))
    for est in ("menu.js", "marcado.js", "atajos.js"):
        pag.route(f"**/estaticos/{est}", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=""))
    pag.route("**/estaticos/aspecto.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(ESTATICOS / "aspecto.js").read_text(encoding="utf-8")))
    pag.route("**/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(aspecto))
        if r.request.method == "GET" else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "aspecto": aspecto})))
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    pag.wait_for_timeout(320)


def var(pag, nombre):
    return pag.evaluate(
        "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", nombre)


def definida(pag, nombre):
    """Si la variable esta DEFINIDA (no vacia). Distinto de valer 'transparent'."""
    return var(pag, nombre) != ""


def fondo_de(pag, sel):
    return pag.evaluate(
        """s => { const e = document.querySelector(s);
                  return e ? getComputedStyle(e).backgroundColor : 'NO ESTA'; }""", sel)


def fondo_de_clases(pag, html):
    """El fondo de un elemento armado a mano con esas clases.

    Hace falta porque varios elementos del semaforo los dibuja el JS con datos del panel
    (el chip 'encendido' no existe hasta que /estado contesta). Lo que se esta probando es
    la REGLA de CSS, no que el panel conteste: pegando el elemento en la pagina, la regla
    se aplica igual y el chequeo no depende de datos inventados.
    """
    return pag.evaluate(
        """h => { const d = document.createElement('div');
                  d.innerHTML = h; document.body.appendChild(d);
                  const e = d.firstElementChild.lastElementChild || d.firstElementChild;
                  const c = getComputedStyle(e).backgroundColor;
                  d.remove(); return c; }""", html)


def main():
    pgs = paginas()
    con_color = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
                 "letra": "normal", "velo": "media", "rastro": "tema",
                 "ok": MAGENTA, "mal": MAGENTA, "aviso": MAGENTA,
                 "burbujaVos": MAGENTA, "burbujaIa": MAGENTA,
                 "barra": MAGENTA, "pizBarra": MAGENTA}
    sin_color = dict(con_color, ok="", mal="", aviso="", burbujaVos="", burbujaIa="",
                     barra="", pizBarra="")

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1400, "height": 900})

        print("\n--- 1. Sin elegir nada: todo como estaba ---")
        montar(pag, pgs["panel"], sin_color)
        verde = var(pag, "--ok")
        revisar("el verde de encendido sigue siendo verde", verde.lower() == "#3ddc84", verde)
        revisar("la barra de arriba NO se define (queda transparente)",
                not definida(pag, "--barra"), var(pag, "--barra") or "(sin definir)")
        cab = fondo_de(pag, "header")
        revisar("y el encabezado del panel se ve transparente",
                cab in ("rgba(0, 0, 0, 0)", "transparent"), cab)
        pag.screenshot(path=str(RAIZ / "pruebas" / f"colores_parte_panel_sin{SUFIJO}.png"))

        montar(pag, pgs["pizarra"], sin_color)
        barra_piz = fondo_de(pag, "#toolbar")
        fondo2 = var(pag, "--fondo2")
        revisar("la barra de la pizarra conserva su fondo de siempre",
                barra_piz not in ("rgba(0, 0, 0, 0)", "transparent", "NO ESTA"),
                f"{barra_piz} (--fondo2 = {fondo2})")

        print("\n--- 2. Con un color elegido: la parte se pinta ---")
        montar(pag, pgs["panel"], con_color)
        revisar("el semaforo toma el color elegido", var(pag, "--ok").lower() == MAGENTA,
                var(pag, "--ok"))
        punto = fondo_de_clases(pag, '<span class="chip on"><span class="pto"></span></span>')
        revisar("y el puntito de 'encendido' del panel sale pintado",
                punto == RGB_MAGENTA, punto, clave=True)
        prender = fondo_de_clases(pag, '<div><button class="prender">Prender</button></div>')
        revisar("y el boton Prender tambien", prender == RGB_MAGENTA, prender, clave=True)
        cab = fondo_de(pag, "header")
        revisar("la barra de arriba se pinta", cab == RGB_MAGENTA, cab, clave=True)
        pag.screenshot(path=str(RAIZ / "pruebas" / f"colores_parte_panel_con{SUFIJO}.png"))

        montar(pag, pgs["pizarra"], con_color)
        barra_piz = fondo_de(pag, "#toolbar")
        revisar("la barra de herramientas de la pizarra se pinta",
                barra_piz == RGB_MAGENTA, barra_piz, clave=True)
        pag.screenshot(path=str(RAIZ / "pruebas" / f"colores_parte_pizarra{SUFIJO}.png"))

        print("\n--- 3. Las burbujas, que eran el otro pedido ---")
        montar(pag, pgs["sesiones"], con_color)
        revisar("la burbuja tuya toma el color elegido",
                var(pag, "--burbuja-vos").lower() == MAGENTA, var(pag, "--burbuja-vos"))
        revisar("y el borde de la burbuja de la sesion tambien",
                var(pag, "--burbuja-ia-borde").lower() == MAGENTA,
                var(pag, "--burbuja-ia-borde"))

        print("\n--- 4. El celular recibe lo mismo (es la misma variable) ---")
        montar(pag, pgs["celular"], con_color)
        revisar("el semaforo del celular sigue el color elegido",
                var(pag, "--ok").lower() == MAGENTA, var(pag, "--ok"))
        revisar("y el ambar de atencion tambien",
                var(pag, "--aviso").lower() == MAGENTA, var(pag, "--aviso"))

        print("\n--- 5. La escalera de tonos sale toda del mismo color ---")
        montar(pag, pgs["panel"], dict(sin_color, ok=MAGENTA))
        peldanos = {n: var(pag, "--ok" + n) for n in ("", "-2", "-txt", "-bd", "-bg")}
        distintos = len(set(peldanos.values()))
        revisar("los cinco peldanos del verde son distintos entre si", distintos == 5,
                json.dumps(peldanos))
        revisar("el mas claro es mas claro que el mas oscuro",
                peldanos["-txt"] != peldanos["-bg"])

        print("\n--- 6. El panel del 🎨, que es lo que Martin toca ---")
        montar(pag, pgs["panel"], dict(sin_color, ok=MAGENTA))
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(160)
        # ⚠ Desde los estilos (2026-08-29) las secciones del 🎨 vienen plegadas, y
        # Playwright no clickea lo que no se ve: el ↺ de una parte vive adentro de una.
        pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                     ".forEach(d => { d.open = true; })")
        pag.wait_for_timeout(150)
        # ⚠ Se cuenta DENTRO de la seccion "Cada parte" y no en todo el panel. Desde los
        # estilos (2026-08-29) hay tres grupos de filas con la misma pinta: estas siete, las
        # dos del tinte general y las siete de las tarjetas del panel. Contar el panel
        # entero daba 16 y el chequeo fallaba sin que estas siete tuvieran nada malo.
        dentro = "#aspectoPanel .sec[data-sec=partes] "
        filas = pag.eval_on_selector_all(dentro + ".parte", "n => n.length")
        revisar("hay una fila por parte", filas == 7, f"{filas} filas")
        nombres = pag.eval_on_selector_all(
            dentro + ".parte .nom", "n => n.map(e => e.textContent)")
        revisar("y cada una dice de que parte es", "Barra de arriba" in nombres,
                ", ".join(nombres))
        ruedas = pag.eval_on_selector_all(
            dentro + ".rueda[data-rueda]", "n => n.length")
        revisar("cada parte tiene su rueda", ruedas == 7, f"{ruedas} ruedas")
        # El ↺ solo aparece donde hay un color elegido: si estuviera siempre, seria un
        # boton que no hace nada en seis de las siete filas.
        quitar = pag.eval_on_selector_all("#aspectoPanel .parte .quitar", "n => n.length")
        revisar("el ↺ esta solo en la parte que tiene color puesto", quitar == 1,
                f"{quitar} botones de quitar")
        pag.click("#aspectoPanel .parte[data-parte='ok'] .quitar")
        pag.wait_for_timeout(160)
        revisar("y al apretarlo esa parte vuelve al color de fabrica",
                var(pag, "--ok").lower() == "#3ddc84", var(pag, "--ok"))
        # Y el cartel de "el panel esta viejo": aparece solo si el servidor devolvio un
        # guardado SIN los campos nuevos (o sea, si los esta tirando).
        pag.evaluate("""() => window.fetch('/aspecto', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:'{}'})""")
        pag.wait_for_timeout(200)
        pag.screenshot(path=str(RAIZ / "pruebas" / f"colores_parte_menu{SUFIJO}.png"))
        errores = pag.evaluate("() => window.__errores || []")
        revisar("y el panel del aspecto no tira errores de javascript", not errores,
                str(errores))

        nav.close()

    print()
    if VIEJO:
        cayeron = [q for q, ok in claves_ok if not ok]
        print(f"MUTACION: de {len(claves_ok)} chequeos clave, cayeron {len(cayeron)}")
        for q in cayeron:
            print("   cayo:", q)
        if len(cayeron) == len(claves_ok):
            print("BIEN: con las pantallas de git fallan TODOS los que importan.")
            return 0
        print("MAL: alguno paso igual con el codigo viejo, o sea que no prueba lo que dice.")
        return 1
    if fallas:
        print(f"{len(fallas)} MAL:")
        for f in fallas:
            print("   -", f)
        return 1
    print("TODO BIEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
