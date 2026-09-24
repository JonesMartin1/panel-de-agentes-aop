"""Los estilos completos, el tinte por rol y el color de cada tarjeta del panel.

Pedido de Martin el 2026-08-29: *"hay mas cosas que me gustaria poder editar"* -> *"mas
colores sobre el panel"*. En la entrevista eligio las cuatro zonas que faltaban (las cajas,
las letras, los botones grises y cada tarjeta con su color) y, puesto a elegir entre veinte
perillas sueltas o combinaciones ya armadas, eligio las combinaciones.

Lo que esta prueba comprueba, en orden de importancia:

  1. ⭐ **Ningun estilo deja un texto ilegible.** Por cada estilo y cada una de las cinco
     pantallas se mide el contraste real (WCAG) de CADA texto contra el fondo que tiene
     detras, con el mismo medidor de `ver_modo_claro.py`. Un estilo que rompe la
     legibilidad no se publica: es la garantia que reemplaza a "el sistema no te deja
     armar algo ilegible", que valia mientras todo se derivaba de un color solo.
  2. ⭐ **Sin elegir nada, no se define ni una tinta**: cada `var(--cRRGGBB,#rrggbb)` cae
     en su respaldo y la pantalla queda como siempre. Es lo mismo que sostiene el tema
     oscuro, y el tinte no lo puede romper.
  3. El tinte CONSERVA la luminosidad de cada gris: cambia el matiz y nada mas. Eso es lo
     que mantiene la jerarquia (el titulo mas claro que el subtitulo). Si se aplanara, la
     pantalla se volveria ilegible de otra forma: todo el texto igual de importante.
  4. Las señales (el semaforo) NO se tiñen, aunque se elija un tinte.
  5. Los siete bloques del panel quedan con siete colores distintos, y sin estilo no se
     pinta ninguno (ni aparece el filito).
  6. ⭐ El "volver a lo mio" devuelve la combinacion EXACTA de antes, incluso despues de
     probar tres estilos seguidos — tiene que devolver lo suyo, no el estilo del medio.
  7. Y que `previo` no se lleve la foto de fondo adentro (seria duplicar cientos de kB en
     el almacenamiento del navegador cada vez que mira un estilo).

⚠ No necesita el panel prendido: las paginas se leen del disco.

Con `--viejo` se sirve el `aspecto.js` como estaba en git (`HEAD`) y se exige que los
chequeos CLAVE fallen: un chequeo que no puede fallar no prueba nada.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_estilos
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
ASPECTO = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
           "letra": "normal", "velo": "media", "rastro": "tema"}
# Un violeta cualquiera para probar el tinte: no se parece a ningun gris de las pantallas,
# asi que si algo queda violeta es porque lo tiño esto y no por casualidad.
TINTE = "#8b5cf6"

fallas, claves = [], []


def revisar(que, ok, detalle="", clave=False):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if clave:
        claves.append((que, ok))


def motor():
    if VIEJO:
        return subprocess.run(["git", "show", "HEAD:app/estaticos/aspecto.js"], cwd=RAIZ,
                              capture_output=True, text=True, encoding="utf-8").stdout
    return (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")


MOTOR = motor()
enviados = []


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

    def ruta(r):
        if r.request.method != "GET":
            try:
                enviados.append(json.loads(r.request.post_data or "{}"))
            except Exception:
                enviados.append({})
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "aspecto": enviados[-1]}))
        r.fulfill(status=200, content_type="application/json", body=json.dumps(aspecto))

    pag.route("**/aspecto", ruta)
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    pag.wait_for_timeout(420)


def var(pag, nombre):
    return pag.evaluate(
        "n => getComputedStyle(document.documentElement).getPropertyValue(n).trim()", nombre)


def hexa(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def numeros(css):
    css = (css or "").strip()
    if css.startswith("#"):
        return [float(v) for v in hexa(css)]
    return [float(x) for x in re.findall(r"[\d.]+", css)][:3]


def luz(c):
    return (.2126 * c[0] + .7152 * c[1] + .0722 * c[2]) / 255


def constantes_js(fuente, nombre):
    """Las claves de un objeto literal `const NOMBRE = { ... };` de aspecto.js."""
    m = re.search(r"const " + nombre + r" = \{(.*?)\n  \};", fuente, re.S)
    if not m:
        m = re.search(r"const " + nombre + r" = \{(.*?)\};", fuente, re.S)
    return re.findall(r"^\s{4}(\w+):", m.group(1), re.M) if m else []


def campos_js(js, k):
    """Los campos que pisa un estilo, leidos del propio `ESTILOS` de aspecto.js."""
    m = re.search(k + r": \{nom: '[^']*', bloques: \w+, campos: \{(.*?)\}\}", js, re.S)
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1))) if m else {}


def abrir_panel(pag):
    pag.click("#aspectoBtn")
    pag.wait_for_timeout(150)
    pag.evaluate("() => document.querySelectorAll('#aspectoPanel details')"
                 ".forEach(d => { d.open = true; })")
    pag.wait_for_timeout(120)


def main():
    print("=== los estilos, el tinte y las tarjetas" + (" (VIEJO)" if VIEJO else ""))
    pags = paginas()
    js = (ESTATICOS / "aspecto.js").read_text(encoding="utf-8")
    panel_py = (RAIZ / "panel.py").read_text(encoding="utf-8")
    estilos = constantes_js(js, "ESTILOS")
    bloques = constantes_js(js, "BLOQUES")

    # --- Lo estatico: que el HTML y el servidor acompañen ---------------------------
    lista = re.search(r"limpio = \{k: d\.get\(k\) for k in \((.*?)\)\s*\n\s*if d\.get",
                      panel_py, re.S)
    faltan = [c for c in ("tintaLetras", "tintaCajas", "bloques", "estilo", "previo")
              if not lista or f'"{c}"' not in lista.group(1)]
    revisar("los campos nuevos estan en la lista blanca de /aspecto (viajan al celular)",
            not faltan, ", ".join(faltan))
    marcados = set(re.findall(r'data-bloque="(\w+)"', panel_py))
    revisar("los siete bloques del panel estan marcados con data-bloque",
            marcados == set(bloques), f"HTML {sorted(marcados)} vs JS {sorted(bloques)}")
    revisar("hay cinco estilos para elegir", len(estilos) == 5, ", ".join(estilos))
    # ⚠ El acento de un estilo no puede ser verde, rojo ni ambar: son el semaforo. Se mira
    # el matiz de cada uno contra los tres de fabrica.
    peligro = []
    for m in re.finditer(r"color: '(#[0-9a-f]{6})'", js):
        c = hexa(m.group(1))
        mx, mn = max(c), min(c)
        if mx - mn < 40:
            continue                       # gris: no se parece a ninguna señal
        verde = c[1] == mx and c[1] - max(c[0], c[2]) > 30
        rojo = c[0] == mx and c[0] - max(c[1], c[2]) > 60
        ambar = c[0] > 200 and 120 < c[1] < 210 and c[2] < 90
        if verde or rojo or ambar:
            peligro.append(m.group(1))
    revisar("ningun acento de estilo se parece al semaforo", not peligro,
            ", ".join(peligro))
    # ⚠⚠ Y que la copia de abajo diga lo mismo que el codigo. Si se desincronizan, el
    # chequeo de contraste estaria midiendo unos colores que la pantalla nunca va a usar:
    # daria verde con estilos que en la realidad quedan ilegibles.
    difieren = [k for k in estilos if campos_js(js, k) != ESTILO_CAMPOS.get(k)]
    revisar("la copia de los estilos de esta prueba coincide con aspecto.js",
            not difieren, "; ".join(f"{k}: {campos_js(js, k)}" for k in difieren[:2]))

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1280, "height": 900})

        # --- 2. Sin elegir nada: ni una tinta definida ------------------------------
        montar(pag, pags["panel"], dict(ASPECTO))
        revisar("sin tinte, las tintas NO se definen (manda el respaldo de siempre)",
                var(pag, "--c232a35") == "", repr(var(pag, "--c232a35")))
        revisar("sin estilo, ningun bloque tiene color",
                pag.evaluate("() => document.querySelectorAll('.bq-color').length") == 0)

        # --- 3 y 4. El tinte: cambia el matiz, no la luz, y no toca las señales -----
        gris_antes = "#7d8592"                       # el gris de los subtitulos
        montar(pag, pags["panel"], dict(ASPECTO, tintaLetras=TINTE, tintaCajas=TINTE))
        tenido = var(pag, "--c7d8592")
        revisar("con tinte puesto, las tintas SI se definen", tenido.startswith("#"), tenido)
        if tenido.startswith("#"):
            a, b = hexa(gris_antes), hexa(tenido)
            revisar("⭐ el tinte conserva la luminosidad del gris (la jerarquia se mantiene)",
                    abs(luz(a) - luz(b)) < .03,
                    f"{gris_antes} luz {luz(a):.3f} -> {tenido} luz {luz(b):.3f}", clave=True)
            revisar("y le cambia el matiz de verdad",
                    max(abs(x - y) for x, y in zip(a, b)) > 8, f"{gris_antes} -> {tenido}",
                    clave=True)
        # La jerarquia, medida de verdad: un texto claro sigue mas claro que uno apagado.
        claro_t, apagado_t = var(pag, "--ce8eaed"), var(pag, "--c616977")
        if claro_t and apagado_t:
            revisar("el texto principal sigue siendo mas claro que el apagado",
                    luz(numeros(claro_t)) > luz(numeros(apagado_t)) + .15,
                    f"{claro_t} vs {apagado_t}")
        # ⚠ Este NO va marcado como clave, y no es un olvido: con el motor viejo no se tiñe
        # NADA, así que pasaría igual. Lo que cuida es otra cosa — que un cambio futuro en
        # el teñido no se lleve puesto el semáforo — y para eso sirve aunque no discrimine
        # contra la versión de git.
        revisar("el semaforo NO se tiñe (es una señal, no un gris)",
                var(pag, "--ok").lower() == "#3ddc84", var(pag, "--ok"))

        # --- 5. Los bloques del panel ------------------------------------------------
        montar(pag, pags["panel"], dict(ASPECTO, estilo="neon"))
        cols = pag.evaluate("""() => [...document.querySelectorAll('[data-bloque]')]
            .map(e => e.style.getPropertyValue('--bloque'))""")
        puestos = [c for c in cols if c]
        revisar("con un estilo puesto, los siete bloques se pintan",
                len(puestos) == 7, f"{len(puestos)} de {len(cols)}", clave=True)
        revisar("y los siete colores son distintos entre si",
                len(set(puestos)) == 7, ", ".join(puestos[:3]), clave=True)
        revisar("el filito solo aparece en los bloques con color",
                pag.evaluate("() => document.querySelectorAll('.bq-color').length")
                == len(puestos))

        # --- 6. El deshacer -----------------------------------------------------------
        # Lo suyo: una combinacion armada a mano, como la que Martin tiene de verdad.
        mio = dict(ASPECTO, fondo="carbon", burbujaVos="#46a047", pizBarra="#ff00ea",
                   rastro="verdoso", sombra="marcada")
        montar(pag, pags["panel"], mio)
        abrir_panel(pag)
        del enviados[:]
        # ⚠ La guarda no es defensiva de mas: con `--viejo` el motor no tiene estilos y sin
        # esto la prueba se cuelga 30 s en el primer click y muere ANTES del resumen — o
        # sea que el modo mutacion no reportaba nada, que es peor que reportar mal.
        hay_estilos = pag.evaluate("() => !!document.querySelector('#aspectoPanel .esti')")
        revisar("el panel tiene la fila de estilos", hay_estilos, clave=True)
        if not hay_estilos:
            for q in ("aplicar un estilo pisa lo elegido a mano",
                      "aparece el boton de volver a lo mio",
                      "⭐ volver devuelve LO SUYO, no el estilo del medio"):
                revisar(q, False, "este motor no tiene estilos", clave=True)
        # Tres estilos seguidos, que es lo que uno hace mirando cual le gusta.
        for cual in (("terminal", "papel", "neon") if hay_estilos else ()):
            pag.click(f"#aspectoPanel .esti[data-esti='{cual}']")
            pag.wait_for_timeout(220)
        tras_estilos = enviados[-1] if enviados else {}
        if hay_estilos:
            revisar("aplicar un estilo pisa lo elegido a mano",
                    tras_estilos.get("fondo") == "negro" and not tras_estilos.get("pizBarra"),
                    json.dumps({k: tras_estilos.get(k) for k in ("fondo", "pizBarra")}),
                    clave=True)
            revisar("⚠ y el previo NO se lleva la foto adentro (pesaria cientos de kB)",
                    "img" not in (tras_estilos.get("previo") or {}),
                    ", ".join(sorted((tras_estilos.get("previo") or {}).keys()))[:70])
        hay_volver = pag.evaluate("() => !!document.getElementById('aspVolver')")
        if hay_estilos:
            revisar("aparece el boton de volver a lo mio", hay_volver, clave=True)
        if hay_volver:
            pag.click("#aspVolver")
            pag.wait_for_timeout(300)
            fin = enviados[-1] if enviados else {}
            iguales = {k: fin.get(k) for k in
                       ("fondo", "burbujaVos", "pizBarra", "rastro", "sombra", "estilo")}
            revisar("⭐ volver devuelve LO SUYO, no el estilo del medio",
                    iguales == {"fondo": "carbon", "burbujaVos": "#46a047",
                                "pizBarra": "#ff00ea", "rastro": "verdoso",
                                "sombra": "marcada", "estilo": ""},
                    json.dumps(iguales), clave=True)
            revisar("y el boton de volver desaparece cuando ya no hay a donde volver",
                    not pag.evaluate("() => !!document.getElementById('aspVolver')"))

        # --- El motor no se muere con ningun estilo ----------------------------------
        errores, malos = [], []
        pag.on("pageerror", lambda e: "rough" in str(e) or errores.append(str(e)))
        for cual, html in pags.items():
            for est in estilos:
                del errores[:]
                montar(pag, html, dict(ASPECTO, estilo=est, **ESTILO_CAMPOS.get(est, {})))
                if errores:
                    malos.append(f"{cual}/{est}: {errores[0][:60]}")
        revisar("ningun estilo tira errores de JavaScript en las cinco pantallas",
                not malos, "; ".join(malos[:3]))

        # --- 1. Lo importante: ningun estilo deja algo ilegible ----------------------
        # ⚠ Se compara contra el tema de FABRICA, igual que `ver_modo_claro`: lo que ya era
        # flojo antes no es un defecto del estilo, y perseguirlo seria perseguir fantasmas
        # ajenos. Falla solo lo que estaba bien y el estilo rompio.
        # ⭐⭐ Antes de creerle al medidor, que se demuestre capaz de fallar. Se le pone un
        # fondo GRIS MEDIO, que es el caso que ya está documentado como el peor (no hay
        # tema que lea bien encima de eso), y tienen que aparecer textos rotos. Sin este
        # chequeo, los veinticinco de abajo podrían estar dando verde porque no miden nada.
        # ⚠ Ojo con la idea de mutar el TINTE para esto: no se puede, y es a propósito —
        # el teñido conserva la luminosidad, así que un tinte no puede volver ilegible un
        # texto ni queriendo. Solo le cambia el matiz.
        montar(pag, pags["panel"], dict(ASPECTO))
        patron = {d["marca"]: d["ratio"] for d in pag.evaluate(CONTRASTES)}
        montar(pag, pags["panel"], dict(ASPECTO, fondo="#8a8a8a"))
        rotos_mut = [m for m, d in {d["marca"]: d for d in pag.evaluate(CONTRASTES)}.items()
                     if m in patron and d["ratio"] < MINIMO <= patron[m]]
        # ⚠ Va sin `clave` aunque sea de los importantes: `clave` en este proyecto quiere
        # decir "tiene que caer con el codigo de git", y este no cae — el fondo libre ya
        # existia en HEAD, asi que el motor viejo tambien lo pinta gris y tambien lo caza.
        # Lo que este chequeo prueba es que el MEDIDOR sirve, no que el estilo es nuevo.
        revisar("⭐ el medidor caza un fondo ilegible puesto a proposito",
                len(rotos_mut) > 5, f"{len(rotos_mut)} textos rotos con un gris medio")

        for cual, html in pags.items():
            montar(pag, html, dict(ASPECTO))
            base = {d["marca"]: d["ratio"] for d in pag.evaluate(CONTRASTES)}
            for est in estilos:
                montar(pag, html, dict(ASPECTO, estilo=est, **ESTILO_CAMPOS.get(est, {})))
                ahora = {d["marca"]: d for d in pag.evaluate(CONTRASTES)}
                rotos = [(m.split("|")[-1], base[m], d) for m, d in ahora.items()
                         if m in base and d["ratio"] < MINIMO <= base[m]]
                rotos.sort(key=lambda x: x[2]["ratio"])
                # ⚠ Sin `clave`: con el motor viejo el estilo ni se aplica, así que la
                # pantalla queda igual y estos pasarían solos. Que puedan fallar lo prueba
                # la mutación de arriba, que es donde vive esa garantía.
                revisar(f"[{cual}/{est}] no se vuelve ilegible ningun texto ({len(ahora)})",
                        not rotos,
                        "; ".join(f"'{t}' {a}->{d['ratio']} ({d['tinta']} sobre {d['fondo']})"
                                  for t, a, d in rotos[:3]))

        montar(pag, pags["panel"], dict(ASPECTO, estilo="neon", **ESTILO_CAMPOS["neon"]))
        pag.screenshot(path=str(RAIZ / "pruebas" /
                                f"estilos{'_viejo' if VIEJO else ''}.png"))
        # Y el 🎨 tal como lo abre Martin: SIN desplegar las secciones a mano, que es lo
        # que hay que mirar para saber si el panel entra en la pantalla o no.
        # ⚠⚠ Primero se limpia `aspectoAbiertas`, y esto es una leccion: el panel RECUERDA
        # que secciones dejaste abiertas, y esta misma prueba las abrio todas unos pasos
        # antes. Sin limpiar, se median 1922 px y el chequeo acusaba al panel de algo que
        # habia hecho el andamiaje. Una prueba que se ensucia a si misma miente igual que
        # una mal escrita.
        pag.evaluate("() => localStorage.removeItem('aspectoAbiertas')")
        montar(pag, pags["panel"], dict(ASPECTO, estilo="neon", **ESTILO_CAMPOS["neon"]))
        pag.click("#aspectoBtn")
        pag.wait_for_timeout(200)
        caja = pag.query_selector("#aspectoPanel")
        if caja:
            caja.screenshot(path=str(RAIZ / "pruebas" /
                                     f"estilos_menu{'_viejo' if VIEJO else ''}.png"))
        alto = pag.evaluate("() => document.getElementById('aspectoPanel').scrollHeight")
        # ⚠ Que entre en un telefono sin scroll: el pedido nacio justo de que no entraba.
        revisar("el 🎨 cerrado entra en una pantalla de telefono", alto < 640, f"{alto} px")
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


# ⚠⚠ Los campos de cada estilo se repiten ACA a mano, y no es un descuido: el andamiaje le
# sirve a la pagina un `/aspecto` ya resuelto, como si Martin hubiera apretado el estilo y
# el servidor se lo hubiera guardado. Si en vez de eso mandara solo `estilo: 'neon'`, se
# estaria probando que el motor lee el nombre — no que la pantalla con ese estilo puesto se
# lee bien, que es lo unico que importa acá. Tienen que coincidir con ESTILOS de aspecto.js;
# si no coinciden, el chequeo de contraste miente y por eso se comparan mas abajo.
ESTILO_CAMPOS = {
    "terminal": {"fondo": "negro", "color": "#2dd4bf", "tintaLetras": "#5eead4",
                 "tintaCajas": "#0f766e", "sombra": "nada", "vidrio": "nada",
                 "tipo": "mono", "espaciado": "sueltas"},
    "calido": {"fondo": "carbon", "color": "#e2cdb0", "tintaLetras": "#f0d9b5",
               "tintaCajas": "#4a3b28", "sombra": "suave", "tipo": "cambria",
               "renglon": "aireados"},
    "papel": {"fondo": "papel", "color": "#3f6ea8", "tintaLetras": "#8b5e34",
              "tintaCajas": "#d9c3a5", "sombra": "suave", "vidrio": "nada",
              "tipo": "georgia", "renglon": "aireados"},
    "neon": {"fondo": "negro", "color": "#f0abfc", "tintaLetras": "#d8b4fe",
             "tintaCajas": "#4c1d95", "sombra": "marcada", "vidrio": "mucho",
             "tipo": "trebu", "letraFx": "resplandor"},
    "nordico": {"fondo": "azulado", "color": "#7aa2ff", "tintaLetras": "#bcd0f5",
                "tintaCajas": "#1e3a5f", "tipo": "calibri", "tipoTitulo": "cambria"},
}


if __name__ == "__main__":
    main()
