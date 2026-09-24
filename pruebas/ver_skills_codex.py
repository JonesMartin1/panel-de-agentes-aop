"""El menú ⚡ de una charla de CODEX: que liste sus skills, y con `$nombre`.

⚠⚠ Por qué existe esta prueba. Hasta el 2026-08-28 el menú de una charla de Codex
mostraba "Todavía no tenés ningún prompt de Codex" y, en el pie, "Codex no usa las
skills de Claude: usa sus propios prompts". Las dos cosas empujaban a la misma
conclusión falsa — que Codex estaba pelado — cuando desde el 2026-08-19 tiene las 14
skills de Martín enlazadas en `~/.codex/skills`. La pantalla fue durante nueve días la
fuente de una creencia equivocada, y eso es peor que un botón que no anda: un botón
roto se ve, un cartel que miente se cree.

No necesita el panel prendido ni ninguna sesión de verdad: arma una página de mentira,
le inyecta el `atajos.js` del disco y le sirve un `/skills` inventado con
`cerebro: "codex"`. (Lección del 2026-08-25: las pruebas de pantalla que no miden la
bandeja no tienen por qué depender del panel real, que puede tardar minutos.)

⭐ Se verifica AL REVÉS: con `--viejo` le devuelve al menú el defecto de antes (a
propósito, mutando el archivo en memoria) y exige que los chequeos que importan
FALLEN. Un chequeo que no puede fallar no prueba nada.

⚠ La mutación NO sale de git: `atajos.js` tenía cambios sin commitear, así que en
`HEAD` el menú de Codex directamente no existe y la comparación no probaría lo que
dice probar. Se reconstruye acá el defecto exacto que había en el disco.

Correr con:  python -m pruebas.ver_skills_codex
             python -m pruebas.ver_skills_codex --viejo
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
ATAJOS = RAIZ / "app" / "estaticos" / "atajos.js"
VIEJO = "--viejo" in sys.argv

# Lo que devuelve `GET /skills` en una charla de Codex desde el 2026-08-28: las DOS
# listas, que son cosas distintas. `grill-me` viene marcada `a_pedido` porque su
# `agents/openai.yaml` tiene `allow_implicit_invocation: false`.
RESPUESTA = {
    "ok": True, "cerebro": "codex",
    "skills": [
        {"nombre": "pizarra", "descripcion": "Escribir en el pizarrón visual.",
         "a_pedido": False},
        {"nombre": "avisar", "descripcion": "Tocarle el timbre a Martín.",
         "a_pedido": False},
        {"nombre": "grill-me", "descripcion": "Entrevista exigente.", "a_pedido": True},
    ],
    "prompts": [],
    "carpeta_skills": "C:\\Users\\usuario\\.codex\\skills",
    "carpeta": "C:\\Users\\usuario\\.codex\\prompts",
    "usadas": [], "corriendo": "", "proyecto": {}, "comandos": [], "rotas": [],
}

# ⚠ La caja va pegada ABAJO como en las pantallas de verdad: el menú siempre se abre
# hacia arriba (la caja de escribir vive contra el borde inferior), así que con el
# botón arriba de todo el menú queda fuera de la pantalla y no se puede ni tocar.
PAGINA = """<!doctype html><meta charset="utf-8"><body style="background:#0e131b;margin:0">
<div class="caja" style="position:fixed;bottom:12px;left:12px;display:flex;gap:8px">
  <textarea id="txt"></textarea><span id="donde"></span></div>
<script src="/estaticos/atajos.js"></script>
<script>
  window.pegado = [];
  Atajos.montar({
    contenedor: document.getElementById('donde'),
    sesion: () => ({sid: 'x', cwd: 'D:/IA/wpp-transcriptor'}),
    insertar: t => window.pegado.push(t),
    acciones: {compactar: () => {}, nueva: () => {}, modelo: () => {}},
  });
</script></body>"""

fallas = []
CLAVES = set()          # los chequeos que TIENEN que fallar con el archivo viejo


def revisar(que, obtenido, esperado, clave=False):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if clave:
        CLAVES.add(que)
    if not ok:
        fallas.append(que)


# Las tres mentiras que tenía el menú antes del 2026-08-28, cada una como un
# reemplazo de texto. Si alguna deja de aplicar es que el código se movió: la prueba
# lo grita en vez de seguir contra un archivo que ya no tiene el defecto (y entonces
# "el defecto se caza" sería un resultado inventado).
MUTACIONES = [
    ("no listaba ninguna skill",
     "const skillsHtml = (r.skills || []).map(s => filaHtml('$' + s.nombre",
     "const skillsHtml = [].map(s => filaHtml('$' + s.nombre"),
    # ⚠ El `$` en vez de `/` NO va como mutación: no fue nunca un defecto viejo (antes
    # no se listaba ninguna skill, así que no había nada que invocar). Se chequea igual
    # más abajo, pero como afirmación de lo que tiene que hacer hoy, no como algo que
    # el archivo viejo pudiera desmentir.
    # El pie entero, no solo la frase: si quedara la parte que nombra la carpeta de los
    # enlaces, el chequeo de "explica dónde están" pasaría igual con el defecto puesto
    # y sería un chequeo de adorno.
    ("el pie afirmaba que Codex no usa las skills",
     """'<div class="pie">Las skills son las mismas que las de Claude (están enlazadas en ' +
      '<b>' + esc(r.carpeta_skills || '~/.codex/skills') + '</b>), pero acá se llaman con ' +
      '<b>$nombre</b>.<br>Un prompt es otra cosa: un archivo <b>' +""",
     """'<div class="pie">Codex no usa las skills de Claude: usa sus propios prompts.<br>' +
      'Cada uno es un archivo <b>' +"""),
    ("/model decía 'modelo de Claude' también en una charla de Codex",
     "filaHtml(c.id, descDe(c, 'codex'),",
     "filaHtml(c.id, c.desc,"),
]


def js_de_atajos():
    """El atajos.js a probar: el del disco, o con el defecto viejo puesto."""
    js = ATAJOS.read_text(encoding="utf-8")
    if not VIEJO:
        return js
    for que, viejo, nuevo in MUTACIONES:
        if viejo not in js:
            print(f"MAL: no pude reponer el defecto '{que}': el código se movió y "
                  f"esta prueba ya no está mutando lo que dice mutar.")
            sys.exit(2)
        js = js.replace(viejo, nuevo)
    return js


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_context(viewport={"width": 1200, "height": 800}).new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        pag.route("http://prueba.local/", lambda r: r.fulfill(
            status=200, content_type="text/html", body=PAGINA))
        pag.route("**/estaticos/atajos.js", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=js_de_atajos()))
        pag.route("**/skills*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(RESPUESTA)))

        pag.goto("http://prueba.local/", wait_until="domcontentloaded")
        pag.wait_for_selector("#btnAtajos")
        pag.click("#btnAtajos")
        pag.wait_for_selector(".at-menu .fila", timeout=5000)

        filas = pag.eval_on_selector_all(
            ".at-menu .fila", "fs => fs.map(f => f.querySelector('.nombre').textContent)")
        texto = pag.inner_text(".at-menu")
        pie = pag.inner_text(".at-menu .pie")

        # --- lo que estaba mal ---------------------------------------------------
        revisar("las skills de Codex aparecen en el menú",
                any(n.startswith("$") for n in filas), True, clave=True)
        revisar("están las tres que mandó el servidor",
                sorted(n for n in filas if n.startswith("$")),
                ["$avisar", "$grill-me", "$pizarra"], clave=True)
        revisar("se invocan con $ y NO con la barrita de Claude",
                "/pizarra" in filas, False)
        revisar("el pie ya no dice que Codex no usa las skills",
                "no usa las skills" in pie.lower(), False, clave=True)
        revisar("y explica dónde están enlazadas",
                ".codex\\skills" in pie, True, clave=True)

        # --- lo que ya andaba y no se rompe --------------------------------------
        revisar("sin prompts propios lo sigue diciendo (no sale en blanco)",
                "Todavía no tenés ningún prompt de Codex" in texto, True)
        # ⚠ Sin red: con el defecto puesto la fila NO existe, y un locator que espera
        # 30 s y revienta abortaría la corrida antes de contar los chequeos. Que falte
        # el elemento ES el fallo que se quiere ver, no un error de la prueba.
        def chapa_de(fila):
            loc = pag.locator(".at-menu .fila", has_text=fila).locator(".chapa")
            try:
                return loc.first.inner_text(timeout=1500)
            except Exception:
                return "(no está la fila)"

        revisar("la que Codex no dispara sola queda marcada",
                chapa_de("grill-me"), "a pedido", clave=True)
        revisar("una normal no lleva esa marca",
                pag.locator(".at-menu .fila", has_text="pizarra")
                   .locator(".chapa").count(), 0)
        revisar("/model ya no dice 'modelo de Claude' en una charla de Codex",
                "modelo de Claude" in texto, False, clave=True)
        revisar("dice el de Codex", "modelo de Codex" in texto, True, clave=True)
        # Los comandos que acá no hacen nada siguen sin ofrecerse.
        revisar("no se ofrecen los comandos que son de Claude",
                any(n in filas for n in ("/init", "/code-review")), False)

        # --- tocar una skill la pega en la caja ----------------------------------
        try:
            pag.locator(".at-menu .fila", has_text="pizarra").first.click(timeout=1500)
        except Exception:
            pass                                  # no está: lo dice el chequeo de abajo
        revisar("tocarla pega $nombre en el mensaje",
                pag.evaluate("window.pegado"), ["$pizarra "], clave=True)

        revisar("la pantalla no tiró ningún error de JS", errores, [])
        nav.close()

    if VIEJO:
        # Al revés: con el archivo de git los chequeos clave TIENEN que fallar.
        cayeron = sorted(set(fallas) & CLAVES)
        print(f"\n--viejo: de {len(CLAVES)} chequeos clave fallaron {len(cayeron)}")
        for c in cayeron:
            print("   cayó:", c)
        if not cayeron:
            print("\nMAL: con el atajos.js VIEJO no falló ninguno. Los chequeos no "
                  "prueban nada: el defecto que dicen cazar no lo cazan.")
            return 1
        print("\nBien: el defecto viejo se caza. Los chequeos pueden fallar.")
        return 0

    print(f"\n{'TODO BIEN' if not fallas else str(len(fallas)) + ' MAL'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
