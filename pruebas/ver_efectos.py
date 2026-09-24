"""Los efectos elegibles: sombra, vidrio y movimiento.

Pedido de Martin el 2026-08-29 ("me gustaria poder cambiar mas caracteristicas"; de cuatro
opciones eligio los efectos y el modo claro). Lo que se comprueba:

  1. SIN elegir nada, las pantallas se ven igual que antes. Es lo mas importante: los
     valores de "normal" son exactamente los que estaban escritos a mano.
  2. Las sombras de elevacion de las pantallas ya no estan escritas a mano: salen de
     `--sombra-0..3` y `--sombra-arriba`. Este es el chequeo CLAVE, porque es lo que hace
     que la perilla llegue a la pantalla y no se quede en una variable que nadie usa.
  3. Las sombras que son SEÑAL (el aro de foco, el inset de lo seleccionado, el resplandor
     del punto encendido) NO se apagan con "Sin sombra": si se apagaran, la pantalla
     dejaria de decir donde estas parado.
  4. El desenfoque de las barras se multiplica por `--vidrio`, asi que "Opaco" lo apaga.
  5. "Quieto" para de verdad la animacion de un elemento cualquiera, y "Sin latidos"
     apaga la animacion pero deja las transiciones (que son respuesta a lo que hacés).

⚠ No necesita el panel prendido ni toca ninguna sesion: las paginas se leen del `panel.py`
y del `sesiones.html` DEL DISCO. Por eso ve el codigo recien escrito y no el que el panel
tiene cargado en memoria.

Con `--viejo` lee las paginas como estaban en git (`HEAD`) y exige que los chequeos marcados
como clave FALLEN. Clave son SOLO los de texto: el motor (`aspecto.js`) se sirve del disco
en las dos corridas a proposito, asi que los que leen una variable no pueden fallar y
marcarlos seria decoracion.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_efectos
"""
import ast
import json
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VIEJO = "--viejo" in sys.argv
BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"

fallas, claves = [], []


def revisar(que, ok, detalle="", clave=False):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if clave:
        claves.append((que, ok))


def de_git(ruta):
    return subprocess.run(["git", "show", f"HEAD:{ruta}"], cwd=RAIZ,
                          capture_output=True, text=True, encoding="utf-8").stdout


def constante(nombre, fuente):
    for nodo in ast.parse(fuente).body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == nombre):
            return ast.literal_eval(nodo.value)
    raise SystemExit(f"No encontre {nombre} en panel.py")


def fuentes():
    panel_py = de_git("panel.py") if VIEJO else (RAIZ / "panel.py").read_text(encoding="utf-8")
    ses = (de_git("app/estaticos/sesiones.html") if VIEJO
           else (ESTATICOS / "sesiones.html").read_text(encoding="utf-8"))
    return {"panel": constante("PAGINA", panel_py),
            "celular": constante("MOVIL_HTML", panel_py),
            "pizarra": constante("PAGINA_PIZARRA", panel_py),
            "sesiones": ses}


# --- 1. Las pantallas no escriben mas su propia sombra de elevacion ----------------
# Una sombra de ELEVACION es la que despega la caja del fondo: tiene desplazamiento o
# desenfoque. La de foco (`0 0 0 3px`) no despega nada — es un aro — y por eso queda afuera
# a proposito: apagarla dejaria la pantalla sin decir donde esta el cursor.
ELEVACION = re.compile(r"box-shadow\s*:\s*([^;\"'}]*)")


def elevaciones_a_mano(css):
    sueltas = []
    for m in ELEVACION.finditer(css):
        v = " ".join(m.group(1).split())
        if "var(--sombra" in v or v.startswith("inset") or v == "none":
            continue
        # ¿Tiene alguna longitud distinta de cero antes del color? Un aro de foco es
        # "0 0 0 3px": sus dos primeras medidas son cero.
        # ⚠ Los ceros se escriben SIN unidad ("0 0 0 2px"), asi que buscar solo `\d+px`
        # dejaba fuera los dos primeros y leia el 2px del aro como si fuera un
        # desplazamiento. Hay que aceptar el cero pelado.
        for capa in v.split(","):
            medidas = re.findall(r"(?:^|\s)(-?[\d.]+)(?:px)?(?=\s|$)", capa.strip())
            if len(medidas) >= 2 and (float(medidas[0]) != 0 or float(medidas[1]) != 0):
                sueltas.append(capa.strip()[:60])
                break
    return sueltas


def chequear_texto():
    fu = fuentes()
    for nombre, css in fu.items():
        sueltas = elevaciones_a_mano(css)
        revisar(f"[{nombre}] ninguna sombra de elevacion escrita a mano",
                not sueltas, "; ".join(sueltas[:3]), clave=True)
    # El vidrio: todo backdrop-filter tiene que pasar por la variable, o "Opaco" no apaga.
    for nombre, css in fu.items():
        blurs = re.findall(r"backdrop-filter\s*:\s*([^;\"'}]+)", css)
        malos = [b for b in blurs if "var(--vidrio" not in b]
        if blurs:
            revisar(f"[{nombre}] el desenfoque de vidrio pasa por --vidrio",
                    not malos, "; ".join(malos[:2]), clave=True)
    # Y las señales siguen ahi: que la conversion no se haya comido el aro de foco.
    aros = sum(len(re.findall(r"box-shadow\s*:\s*0 0 0 \d", css)) for css in fu.values())
    revisar("las sombras de señal (aro de foco) siguen escritas", aros >= 5, f"{aros} aros")


# --- 2. El motor: que cada nivel de verdad cambie lo que dice --------------------
def montar(pag, html, aspecto):
    # ⚠ El orden es al reves de lo que parece: Playwright prueba de la ultima ruta a la
    # primera, asi que el atrapatodo va PRIMERO.
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


def probeta(pag, estilo):
    """Un elemento de mentira con el estilo pedido, para leerle lo COMPUTADO.

    Sirve para el movimiento, que se apaga con una regla sobre el selector universal: lo
    que hay que comprobar es justamente que le pegue a cualquier elemento del documento.
    """
    return pag.evaluate(
        """est => {
             const d = document.createElement('div');
             d.setAttribute('style', est);
             document.body.appendChild(d);
             const c = getComputedStyle(d);
             const r = {anim: c.animationName, trans: c.transitionDuration,
                        sombra: c.boxShadow, blur: c.backdropFilter};
             d.remove(); return r;
           }""", estilo)


ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
           "letra": "normal", "velo": "media", "rastro": "tema"}


def chequear_motor(pag, paginas):
    montar(pag, paginas["panel"], dict(ASPECTO))
    # Sin elegir nada: los valores de siempre, tal cual estaban escritos en las pantallas.
    revisar("sin elegir nada, --sombra-2 es la de siempre",
            var(pag, "--sombra-2") == "0 8px 24px rgba(0,0,0,0.5)", var(pag, "--sombra-2"))
    revisar("sin elegir nada, --sombra-3 es la de siempre",
            var(pag, "--sombra-3") == "0 16px 46px rgba(0,0,0,0.6)", var(pag, "--sombra-3"))
    revisar("sin elegir nada, la de la barra de abajo cae para arriba",
            var(pag, "--sombra-arriba").startswith("0 -18px"), var(pag, "--sombra-arriba"))
    revisar("sin elegir nada, el vidrio queda en 1 (lo de hoy)", var(pag, "--vidrio") == "1.00",
            var(pag, "--vidrio"))
    revisar("sin elegir nada, el <html> no tiene clase de movimiento",
            pag.evaluate("document.documentElement.className.indexOf('movi-') < 0"))

    for nivel, espero in (("nada", "none"), ("suave", None), ("marcada", None)):
        montar(pag, paginas["panel"], dict(ASPECTO, sombra=nivel))
        v = var(pag, "--sombra-2")
        if espero:
            revisar(f"con sombra={nivel} no queda sombra", v == espero, v)
        else:
            blur = float(re.findall(r"([\d.]+)px", v)[1]) if "px" in v else -1
            chico, grande = (blur < 24, blur > 24)
            revisar(f"con sombra={nivel} el desenfoque {'baja' if nivel=='suave' else 'sube'}",
                    chico if nivel == "suave" else grande, v)

    montar(pag, paginas["panel"], dict(ASPECTO, vidrio="nada"))
    revisar("con vidrio=nada el desenfoque queda en cero",
            probeta(pag, "backdrop-filter:blur(calc(16px * var(--vidrio,1)))")["blur"]
            in ("blur(0px)", "none"),
            probeta(pag, "backdrop-filter:blur(calc(16px * var(--vidrio,1)))")["blur"])
    montar(pag, paginas["panel"], dict(ASPECTO, vidrio="mucho"))
    revisar("con vidrio=mucho las superficies se transparentan sin foto",
            var(pag, "--fondo2").startswith("rgba"), var(pag, "--fondo2"))
    revisar("y el desenfoque crece",
            "25.5px" in probeta(pag, "backdrop-filter:blur(calc(15px * var(--vidrio,1)))")["blur"],
            probeta(pag, "backdrop-filter:blur(calc(15px * var(--vidrio,1)))")["blur"])

    montar(pag, paginas["panel"], dict(ASPECTO, movi="poco"))
    p = probeta(pag, "animation:latir 2s infinite;transition:opacity .3s")
    revisar("con movi=poco se para la animacion", p["anim"] == "none", p["anim"])
    revisar("con movi=poco las transiciones siguen vivas",
            p["trans"] not in ("0s", ""), p["trans"])
    montar(pag, paginas["panel"], dict(ASPECTO, movi="nada"))
    p = probeta(pag, "animation:latir 2s infinite;transition:opacity .3s")
    revisar("con movi=nada se para la animacion", p["anim"] == "none", p["anim"])
    revisar("con movi=nada se paran tambien las transiciones", p["trans"] == "0s", p["trans"])

    # Y la pantalla de al lado: que el motor valga igual en el celular y en /sesiones.
    for cual in ("celular", "sesiones"):
        montar(pag, paginas[cual], dict(ASPECTO, sombra="nada"))
        revisar(f"[{cual}] con sombra=nada la variable llega apagada",
                var(pag, "--sombra-1") == "none", var(pag, "--sombra-1"))


def main():
    print("=== los efectos: sombra, vidrio y movimiento" + (" (VIEJO)" if VIEJO else ""))
    chequear_texto()
    paginas = fuentes()
    # El motor se lee SIEMPRE del disco; con --viejo cambian solo las pantallas.
    if VIEJO:
        pg = {k: v for k, v in
              zip(("panel", "celular", "pizarra", "sesiones"),
                  (fuentes()[k] for k in ("panel", "celular", "pizarra", "sesiones")))}
        paginas = pg
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1280, "height": 900})
        chequear_motor(pag, paginas)
        pag.screenshot(path=str(RAIZ / "pruebas" /
                                f"efectos{'_viejo' if VIEJO else ''}.png"))
        nav.close()

    print()
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
