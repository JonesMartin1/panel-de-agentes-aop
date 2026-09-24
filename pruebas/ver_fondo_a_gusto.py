"""El fondo elegido con la rueda: cualquier color, y la pantalla se acomoda sola.

Pedido de Martin el 2026-08-29, mirando la fila de cinco fondos del panel 🎨: *"me
gustaria poder elegir el color tambien"*. Lo que esta prueba comprueba:

  1. El color elegido LLEGA: el fondo de la pantalla es ese y no uno de los cinco.
  2. La superficie donde se apoyan las tarjetas (`--fondo2`) sale del color elegido, no
     del azulado de fabrica. Sin esto el fondo cambia y las tarjetas quedan de otro color.
  3. ⭐ Un color CLARO da vuelta la pantalla entera solo, sin que haya que elegir nada
     mas: se prende el tema claro, las tintas se dan vuelta y el acento se oscurece. Es
     lo unico que hace que la rueda no sea una trampa — un fondo blanco con las letras
     claras de siempre es una pantalla en blanco.
  4. ⭐ Y ahi tampoco queda nada ilegible: se mide el contraste real (WCAG) de CADA texto
     contra el fondo que tiene detras y se compara con la misma pantalla en oscuro, igual
     que `ver_modo_claro.py` (de ahi se importa el medidor).
  5. La rueda existe en el panel, cambia el fondo al soltarla y GUARDA lo elegido.
  6. Un valor que no es un color ni una de las cinco palabras no rompe nada: cae en el
     azulado de siempre.
  7. `fondo` sigue en la lista blanca de `/aspecto` en `panel.py`, que es lo que hace que
     el color viaje al telefono en vez de quedarse en este navegador.

⚠ No necesita el panel prendido: las paginas se leen del disco.

Con `--viejo` se sirve el `aspecto.js` como estaba en git (`HEAD`) y se exige que los
chequeos CLAVE fallen: un chequeo que no puede fallar no prueba nada.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_fondo_a_gusto
"""
import json
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ
from pruebas.ver_modo_claro import CONTRASTES, MINIMO, paginas

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VIEJO = "--viejo" in sys.argv
BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"

# Un violeta oscuro y una crema clara: uno de cada lado del corte de luminosidad, y
# ninguno parecido a los cinco que ya estan (asi "llego el color" no puede dar bien por
# casualidad).
OSCURO = "#3a1f5c"
CLARO = "#ffe9c9"
ASPECTO = {"tipo": "segoe", "color": "celeste", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}

fallas, claves = [], []


def revisar(que, ok, detalle="", clave=False):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if clave:
        claves.append((que, ok))


def motor():
    """El `aspecto.js` que se le sirve a la pagina: el del disco, o el de git con --viejo."""
    if VIEJO:
        return subprocess.run(["git", "show", "HEAD:app/estaticos/aspecto.js"], cwd=RAIZ,
                              capture_output=True, text=True, encoding="utf-8").stdout
    return (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")


MOTOR = motor()
enviados = []          # lo que la pantalla POSTea a /aspecto, para ver que guarde


def montar(pag, html, aspecto):
    # ⚠ Playwright prueba de la ultima ruta a la primera: el atrapatodo va PRIMERO.
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

    def aspecto_ruta(r):
        if r.request.method != "GET":
            try:
                enviados.append(json.loads(r.request.post_data or "{}"))
            except Exception:
                enviados.append({})
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "aspecto": enviados[-1]}))
        r.fulfill(status=200, content_type="application/json", body=json.dumps(aspecto))

    pag.route("**/aspecto", aspecto_ruta)
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    pag.wait_for_timeout(420)


def var(pag, nombre):
    return pag.evaluate(
        "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", nombre)


def hexa(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def numeros(css):
    """Los tres canales de un color, venga como '#rrggbb' o como 'rgb(r,g,b)'.

    ⚠ Las dos formas conviven a proposito y hay que aguantar las dos: `--fondo2` sale en
    hex (se lo vuelve a mezclar mas adelante) y lo que devuelve `getComputedStyle` siempre
    viene en `rgb(...)`. Leer un hex con la regla de los numeros da cualquier cosa
    ("#442a64" -> 442 y 64) y el chequeo falla sin que nada este roto.
    """
    css = css.strip()
    if css.startswith("#"):
        return [float(v) for v in hexa(css)]
    return [float(x) for x in re.findall(r"[\d.]+", css)][:3]


def lejos(a, b):
    """Cuanto se despega un color de otro, mirando el canal que mas cambio."""
    return max(abs(x - y) for x, y in zip(a, b))


def wcag(a, b):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4

    def luz(c):
        return .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2])

    x, y = luz(a), luz(b)
    return (max(x, y) + .05) / (min(x, y) + .05)


def main():
    print("=== el fondo a gusto (la rueda de color)" + (" (VIEJO)" if VIEJO else ""))
    pags = paginas()

    # 7. El campo viaja al telefono. `fondo` es viejo y ya estaba, pero si alguien lo saca
    #    de la lista el color se veria solo en la compu, y en silencio.
    panel_py = (RAIZ / "panel.py").read_text(encoding="utf-8")
    lista = re.search(r"limpio = \{k: d\.get\(k\) for k in \((.*?)\)\s*\n\s*if d\.get",
                      panel_py, re.S)
    revisar("`fondo` esta en la lista blanca de /aspecto (viaja al celular)",
            bool(lista) and '"fondo"' in lista.group(1))

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1280, "height": 900})

        # --- 1 y 2. Un color oscuro cualquiera -------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, fondo=OSCURO))
        cuerpo = numeros(pag.evaluate("getComputedStyle(document.body).backgroundColor"))
        revisar("el fondo de la pantalla es EL color elegido",
                lejos(cuerpo, hexa(OSCURO)) <= 1,
                f"{cuerpo} vs {hexa(OSCURO)}", clave=True)
        f2 = numeros(var(pag, "--fondo2"))
        revisar("la superficie de las tarjetas sale del color elegido",
                0 < lejos(f2, hexa(OSCURO)) <= 40, f"--fondo2 {var(pag, '--fondo2')}",
                clave=True)
        revisar("con un color oscuro NO se prende el tema claro",
                not pag.evaluate("document.documentElement.classList.contains('tema-claro')"))
        revisar("con un color oscuro las tintas siguen sin definirse (manda el respaldo)",
                var(pag, "--c232a35") == "", var(pag, "--c232a35"))

        # --- 3. Un color claro da vuelta la pantalla sola --------------------------
        montar(pag, pags["panel"], dict(ASPECTO, fondo=CLARO))
        cuerpo = numeros(pag.evaluate("getComputedStyle(document.body).backgroundColor"))
        revisar("con un color claro el fondo tambien es el elegido",
                lejos(cuerpo, hexa(CLARO)) <= 1, str(cuerpo), clave=True)
        revisar("⭐ un color claro prende el tema claro solo",
                pag.evaluate("document.documentElement.classList.contains('tema-claro')"),
                clave=True)
        tinta = var(pag, "--c232a35")
        revisar("y las tintas se dan vuelta (un borde oscuro se aclara)",
                tinta.startswith("#") and int(tinta[1:3], 16) > 0x80, tinta, clave=True)
        acento = var(pag, "--acento")
        revisar("el acento se oscurece para leerse sobre el fondo claro",
                wcag(numeros(acento) if acento.startswith("rgb") else hexa(acento),
                     hexa(CLARO)) >= 4.5,
                f"{acento} sobre {CLARO}", clave=True)
        sem = {n: var(pag, f"--{n}") for n in ("ok", "mal", "aviso")}
        revisar("el semaforo sigue teniendo tres colores distintos",
                len(set(sem.values())) == 3, str(sem))

        # --- 6. Basura: que caiga parada --------------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, fondo="pepe"))
        cuerpo = numeros(pag.evaluate("getComputedStyle(document.body).backgroundColor"))
        revisar("un fondo que no existe cae en el azulado de siempre",
                lejos(cuerpo, hexa("#0b0d12")) <= 1, str(cuerpo))

        # --- 5. La rueda: existe, aplica y guarda ------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, fondo="azulado"))
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(120)
        hay = pag.evaluate("!!document.getElementById('aspRuedaFondo')")
        revisar("el panel 🎨 tiene la rueda de fondo", hay, clave=True)
        if hay:
            revisar("la rueda arranca con el fondo que esta puesto",
                    pag.evaluate("document.getElementById('aspRuedaFondo').value") == "#0b0d12",
                    pag.evaluate("document.getElementById('aspRuedaFondo').value"))
            del enviados[:]
            pag.evaluate("""() => {
                const r = document.getElementById('aspRuedaFondo');
                r.value = '%s';
                r.dispatchEvent(new Event('input'));
                r.dispatchEvent(new Event('change'));
            }""" % OSCURO)
            pag.wait_for_timeout(260)
            cuerpo = numeros(pag.evaluate("getComputedStyle(document.body).backgroundColor"))
            revisar("mover la rueda pinta la pantalla",
                    lejos(cuerpo, hexa(OSCURO)) <= 1, str(cuerpo), clave=True)
            revisar("y al soltarla se guarda en el servidor",
                    any(e.get("fondo") == OSCURO for e in enviados),
                    str([e.get("fondo") for e in enviados])[:60], clave=True)
            # Y "volver a lo de fabrica" tiene que deshacer esto tambien.
            pag.evaluate("document.getElementById('aspFabrica').click()")
            pag.wait_for_timeout(200)
            cuerpo = numeros(pag.evaluate("getComputedStyle(document.body).backgroundColor"))
            revisar("'volver a lo de fabrica' devuelve el fondo de siempre",
                    lejos(cuerpo, hexa("#0b0d12")) <= 1, str(cuerpo))

        # --- El motor no se puede morir en el camino ---------------------------------
        # (mismo motivo que en ver_modo_claro: un error de JS deja la pantalla "casi bien")
        errores = []
        pag.on("pageerror", lambda e: "rough" in str(e) or errores.append(str(e)))
        for cual, html in pags.items():
            for cual_fondo in (OSCURO, CLARO):
                del errores[:]
                montar(pag, html, dict(ASPECTO, fondo=cual_fondo))
                revisar(f"[{cual}/{cual_fondo}] ningun error de JavaScript",
                        not errores, "; ".join(errores[:2]))

        # --- 4. Con el fondo claro elegido a mano, nada queda ilegible ---------------
        for cual, html in pags.items():
            montar(pag, html, dict(ASPECTO, fondo="azulado"))
            osc = {d["marca"]: d["ratio"] for d in pag.evaluate(CONTRASTES)}
            montar(pag, html, dict(ASPECTO, fondo=CLARO))
            cla = {d["marca"]: d for d in pag.evaluate(CONTRASTES)}
            rotos = []
            for marca, d in cla.items():
                antes = osc.get(marca)
                if antes is not None and d["ratio"] < MINIMO <= antes:
                    rotos.append((marca.split("|")[-1], antes, d))
            rotos.sort(key=lambda x: x[2]["ratio"])
            revisar(f"[{cual}] ningun texto se vuelve ilegible con el crema ({len(cla)} textos)",
                    not rotos,
                    "; ".join(f"'{t}' {a}->{d['ratio']} ({d['tinta']} sobre {d['fondo']})"
                              for t, a, d in rotos[:3]))

        montar(pag, pags["panel"], dict(ASPECTO, fondo=CLARO))
        pag.screenshot(path=str(RAIZ / "pruebas" /
                                f"fondo_a_gusto{'_viejo' if VIEJO else ''}.png"))
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
