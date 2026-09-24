"""Los efectos de la letra y la tipografia libre.

Pedido de Martin el 2026-08-29, mirando la seccion Letra del 🎨 ya reiniciado: *"me
gustaria mas efectos y estilos para las letras, aparte de poder seleccionar lo que yo
quiera"*. Lo que esta prueba comprueba:

  1. ⭐⭐ **Una tipografia elegida a mano no puede escribir CSS.** El nombre de la fuente
     termina adentro de una regla de estilo y viaja al servidor, asi que un nombre con
     comillas o punto y coma podria cerrar la regla y meter lo que quiera en las cinco
     pantallas. Se prueba con cuatro nombres hostiles: todos tienen que caer en Segoe y
     la pagina tiene que seguir viendose.
  2. ⭐ **Sin elegir nada, la pantalla no se mueve.** El valor "normal" de cada perilla es
     el del navegador y no el numero que uno leeria del CSS de las burbujas: puesto ahi,
     le cambiaria el interlineado a todo el mundo. (Aparte lo verifica `foto_pantallas`.)
  3. Cada perilla llega de verdad al texto: grosor, espacio entre letras, interlineado y
     el efecto (sombra o resplandor), medidos sobre el estilo COMPUTADO del cuerpo.
  4. Los titulos pueden tener su propia tipografia, distinta de la del texto.
  5. Una fuente instalada se aplica, y el panel avisa que en el celular puede verse otra.
  6. ⭐ Los estilos traen su tipografia pero **nunca el tamaño del texto**: la tipografia es
     estetica y el tamaño es que se vea. Pisarle el "Enorme" a quien lo eligio para leer
     mejor seria una grosaria disfrazada de estilo.

⚠ No necesita el panel prendido: las paginas se leen del disco.

Con `--viejo` se sirve el `aspecto.js` de git y se exige que los chequeos CLAVE fallen.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_letra
"""
import json
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ
from pruebas.ver_modo_claro import paginas

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VIEJO = "--viejo" in sys.argv
# ⭐⭐ `--mutar` rompe A PROPOSITO la validacion del nombre de fuente y exige que los ocho
# chequeos hostiles caigan. Hace falta porque contra el codigo de git esos ocho pasan
# solos: el motor viejo no acepta fuentes libres, asi que un nombre raro cae en Segoe sin
# validar nada. O sea que `--viejo` NO puede decir si el candado sirve — solo esto puede.
MUTAR = "--mutar" in sys.argv
BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
           "letra": "normal", "velo": "media", "rastro": "tema"}
# Nombres hostiles: los cuatro intentan salirse de la regla CSS donde termina el valor.
HOSTILES = ["Arial;}html{display:none}", "Arial',sans-serif;color:red;x:'",
            'Arial"</style><script>window.__hack=1</script>', "Arial;}*{opacity:0}"]

fallas, claves, hostiles = [], [], []


def revisar(que, ok, detalle="", clave=False, hostil=False):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if clave:
        claves.append((que, ok))
    if hostil:
        hostiles.append((que, ok))


VALIDACION = "const FUENTE_OK = /^[A-Za-z0-9][A-Za-z0-9 .\\-]{0,39}$/;"


def motor():
    if VIEJO:
        return subprocess.run(["git", "show", "HEAD:app/estaticos/aspecto.js"], cwd=RAIZ,
                              capture_output=True, text=True, encoding="utf-8").stdout
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    if MUTAR:
        if VALIDACION not in js:
            raise SystemExit("No encontre la validacion del nombre de fuente para mutarla:\n"
                             f"  {VALIDACION}\nSi cambio de forma, actualizar esta prueba.")
        js = js.replace(VALIDACION, "const FUENTE_OK = /^[\\s\\S]*$/;")
    return js


MOTOR = motor()


def montar(pag, html, aspecto):
    pag.route(f"{BASE}/**", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "items": [], "proyectos": [], "mensajes": [],
                         "servicios": {}})))
    pag.route(BASE + "/", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    pag.route("**/pizarra/rough.js", lambda r: r.fulfill(status=200, body=""))
    pag.route("**/fondo/**", lambda r: r.fulfill(status=200, body=""))
    for est in ("menu.js", "marcado.js", "atajos.js", "marcas.js", "direccion.js"):
        pag.route(f"**/estaticos/{est}", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=""))
    pag.route("**/estaticos/aspecto.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript", body=MOTOR))
    pag.route("**/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(aspecto))
        if r.request.method == "GET" else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "aspecto": aspecto})))
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    pag.wait_for_timeout(400)


def var(pag, nombre):
    return pag.evaluate(
        "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", nombre)


def cuerpo(pag, prop):
    return pag.evaluate("p => getComputedStyle(document.body)[p]", prop)


def main():
    print("=== la letra: efectos y tipografia libre" + (" (VIEJO)" if VIEJO else ""))
    pags = paginas()
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    panel_py = (RAIZ / "panel.py").read_text(encoding="utf-8")

    lista = re.search(r"limpio = \{k: d\.get\(k\) for k in \((.*?)\)\s*\n\s*if d\.get",
                      panel_py, re.S)
    faltan = [c for c in ("peso", "espaciado", "renglon", "letraFx", "tipoTitulo")
              if not lista or f'"{c}"' not in lista.group(1)]
    revisar("las perillas de letra estan en la lista blanca de /aspecto",
            not faltan, ", ".join(faltan))
    # ⛔ Las fuentes de simbolos no se ofrecen: elegir Wingdings deja las cinco pantallas en
    # jeroglificos y ni el boton de volver se puede leer.
    simbolos = [s for s in ("Wingdings", "Webdings", "Marlett", "Segoe MDL2", "Symbol")
                if "'" + s in js or '"' + s in js]
    revisar("no se ofrece ninguna tipografia de simbolos", not simbolos, ", ".join(simbolos))

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1280, "height": 900})

        # --- 2. Sin elegir nada: lo del navegador -----------------------------------
        montar(pag, pags["panel"], dict(ASPECTO))
        revisar("sin elegir nada el interlineado es el del navegador",
                var(pag, "--renglon") in ("normal", ""), var(pag, "--renglon"))
        revisar("sin elegir nada no hay sombra en el texto",
                var(pag, "--letra-fx") in ("none", ""), var(pag, "--letra-fx"))
        revisar("sin elegir nada el espacio entre letras es el de siempre",
                cuerpo(pag, "letterSpacing") == "normal", cuerpo(pag, "letterSpacing"))
        revisar("sin elegir nada el grosor es el de siempre",
                cuerpo(pag, "fontWeight") == "400", cuerpo(pag, "fontWeight"))

        # --- 1. ⭐⭐ Lo que no puede pasar: que el nombre escriba CSS -----------------
        for i, malo in enumerate(HOSTILES):
            montar(pag, pags["panel"], dict(ASPECTO, tipo=malo))
            fam = var(pag, "--tipo")
            visible = pag.evaluate(
                "() => { const c = getComputedStyle(document.documentElement);"
                " const b = getComputedStyle(document.body);"
                " return c.display !== 'none' && b.opacity !== '0'"
                "        && document.body.offsetHeight > 100; }")
            hackeado = pag.evaluate("() => !!window.__hack")
            # El candado sostiene ESTO: el nombre hostil se descarta entero y queda la
            # familia de siempre, sin un solo caracter del texto raro adentro.
            revisar(f"[hostil {i + 1}] el nombre raro se descarta entero",
                    fam == "'Segoe UI',system-ui,sans-serif", fam[:70], hostil=True)
            # ⚠ Esto NO lo sostiene el candado y por eso va sin bandera: aunque el valor
            # pasara, el navegador no deja cerrar una regla desde el VALOR de una variable
            # CSS puesta con `setProperty`. Lo descubri corriendo `--mutar`: con la
            # validacion rota estos cuatro seguian en verde. Se deja igual como red —
            # mañana el valor podria terminar en otro lado, y ahi si importaria.
            revisar(f"[hostil {i + 1}] y la pantalla se sigue viendo",
                    visible and not hackeado, f"visible={visible} hack={hackeado}")

        # --- 5. Una fuente instalada de verdad ---------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, tipo="Impact"))
        revisar("una tipografia instalada se aplica tal cual",
                "Impact" in var(pag, "--tipo"), var(pag, "--tipo"), clave=True)
        revisar("y el cuerpo de la pagina la usa",
                "Impact" in cuerpo(pag, "fontFamily"), cuerpo(pag, "fontFamily")[:50])
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(150)
        pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                     ".forEach(d => { d.open = true; })")
        pag.wait_for_timeout(120)
        revisar("el panel avisa que esa letra puede no estar en el celular",
                pag.evaluate("() => !!document.querySelector('#aspectoPanel .avisoLetra')"),
                clave=True)
        opciones = pag.evaluate(
            "() => document.querySelectorAll('#aspectoPanel select[data-fuente=tipo] option')"
            ".length")
        revisar("el desplegable ofrece bastantes mas que las nueve de la fila",
                opciones > 20, f"{opciones} opciones", clave=True)
        # Y con una de las nueve, el aviso NO aparece: seria un susto por nada.
        montar(pag, pags["panel"], dict(ASPECTO, tipo="comic"))
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(150)
        pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                     ".forEach(d => { d.open = true; })")
        revisar("con una de las nueve NO avisa nada",
                not pag.evaluate("() => !!document.querySelector('#aspectoPanel .avisoLetra')"))

        # --- 3. Que cada perilla llegue al texto -------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, peso="negrita"))
        revisar("el grosor llega al texto", cuerpo(pag, "fontWeight") == "600",
                cuerpo(pag, "fontWeight"), clave=True)
        montar(pag, pags["panel"], dict(ASPECTO, peso="fina"))
        revisar("y la letra fina tambien", cuerpo(pag, "fontWeight") == "300",
                cuerpo(pag, "fontWeight"))
        montar(pag, pags["panel"], dict(ASPECTO, espaciado="sueltas"))
        revisar("el espacio entre letras llega al texto",
                cuerpo(pag, "letterSpacing").endswith("px")
                and float(cuerpo(pag, "letterSpacing")[:-2]) > .3,
                cuerpo(pag, "letterSpacing"), clave=True)
        montar(pag, pags["panel"], dict(ASPECTO, renglon="aireados"))
        alto = cuerpo(pag, "lineHeight")
        revisar("los renglones se separan de verdad",
                alto.endswith("px") and float(alto[:-2]) > 22, alto, clave=True)
        montar(pag, pags["panel"], dict(ASPECTO, letraFx="sombra"))
        revisar("la sombra del texto llega", "rgba" in cuerpo(pag, "textShadow"),
                cuerpo(pag, "textShadow"), clave=True)
        montar(pag, pags["panel"], dict(ASPECTO, letraFx="resplandor", color="#ff00aa"))
        fx = var(pag, "--letra-fx")
        revisar("el resplandor sale del color del acento", "255, 0, 170" in fx or "255,0,170" in fx,
                fx, clave=True)

        # --- 4. Los titulos con su propia letra --------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, tipo="segoe", tipoTitulo="mono"))
        titulo = pag.evaluate(
            "() => { const h = document.querySelector('h2');"
            " return h ? getComputedStyle(h).fontFamily : ''; }")
        revisar("los titulos pueden tener otra tipografia que el texto",
                "Consolas" in titulo and "Consolas" not in cuerpo(pag, "fontFamily"),
                f"titulo={titulo[:34]} / cuerpo={cuerpo(pag, 'fontFamily')[:30]}", clave=True)
        montar(pag, pags["panel"], dict(ASPECTO, tipo="georgia"))
        titulo = pag.evaluate("() => getComputedStyle(document.querySelector('h2')).fontFamily")
        revisar("y sin elegir nada siguen la del texto", "Georgia" in titulo, titulo[:40])

        # --- 6. Los estilos traen su letra, pero no el tamaño ------------------------
        # ⚠ Sin `clave`: mira el archivo del disco, que con `--viejo` es el mismo. Cuida
        # que nadie meta el tamaño adentro de un estilo mañana, no que hoy sea nuevo.
        revisar("⭐ ningun estilo toca el TAMAÑO del texto",
                not re.search(r"campos: \{[^}]*\bletra:", js), "")
        revisar("y los estilos si traen tipografia",
                len(re.findall(r"campos: \{[^}]*\btipo:", js)) >= 4)

        # --- Que nada se rompa en las cinco pantallas --------------------------------
        errores, malos = [], []
        pag.on("pageerror", lambda e: "rough" in str(e) or errores.append(str(e)))
        for cual, html in pags.items():
            for extra in ({"peso": "negrita", "renglon": "aireados"},
                          {"tipo": "Impact", "letraFx": "resplandor"},
                          {"tipoTitulo": "mono", "espaciado": "juntas"}):
                del errores[:]
                montar(pag, html, dict(ASPECTO, **extra))
                if errores:
                    malos.append(f"{cual}/{list(extra)[0]}: {errores[0][:50]}")
        revisar("ninguna combinacion de letra tira errores de JavaScript",
                not malos, "; ".join(malos[:3]))

        montar(pag, pags["panel"], dict(ASPECTO, tipo="Georgia", peso="negrita",
                                        renglon="aireados", letraFx="sombra"))
        pag.screenshot(path=str(RAIZ / "pruebas" /
                                f"letra{'_viejo' if VIEJO else ''}.png"))
        nav.close()

    print()
    if MUTAR:
        vivos = [q for q, ok in hostiles if ok]
        print(f"--mutar: de {len(hostiles)} chequeos hostiles, cayeron "
              f"{len(hostiles) - len(vivos)}")
        if vivos:
            print("⚠ CON LA VALIDACION ROTA ESTOS SIGUIERON EN VERDE, o sea que el candado "
                  "no es lo que los sostiene:")
            for q in vivos:
                print("   -", q)
            sys.exit(1)
        print("bien: el candado del nombre de fuente es lo que los sostiene")
        return
    if VIEJO:
        vivos = [q for q, ok in claves if ok]
        print(f"--viejo: {len(claves) - len(vivos)} de {len(claves)} chequeos clave fallaron")
        if vivos:
            print("⚠ ESTOS NO PUEDEN FALLAR, o sea que no prueban nada:")
            for q in vivos:
                print("   -", q)
            sys.exit(1)
        print("bien: los chequeos clave son capaces de fallar")
        return
    if fallas:
        print(f"{len(fallas)} MAL:")
        for f in fallas:
            print("   -", f)
        sys.exit(1)
    print("TODO BIEN")


if __name__ == "__main__":
    main()
