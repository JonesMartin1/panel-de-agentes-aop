"""El markdown de las sesiones, dibujado: que no queden asteriscos a la vista.

Prueba `app/estaticos/marcado.js` — el dibujante que usan las dos pantallas de
sesiones (la de la compu y la del celular) — corriendolo de verdad en un navegador,
que es donde vive. No hace falta que el panel este prendido: el archivo se inyecta
en una pagina en blanco.

Ademas del listado de casos, deja una captura de una burbuja con una respuesta larga
de verdad en `pruebas/marcado_burbuja.png`, para MIRARLA: los defectos de pantalla se
ven ahi, no leyendo el codigo (leccion del 2026-08-14).

    python -m pruebas.probar_marcado
"""
from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS, RAIZ

SALIDA = RAIZ / "pruebas" / "marcado_burbuja.png"

# (nombre, texto que llega, lo que TIENE que aparecer, lo que NO puede aparecer)
CASOS = [
    ("negrita",       "Esto es **importante** hoy",
     ["<b>importante</b>"], ["**"]),
    ("titulo",        "## Como convivo\ntexto",
     ['class="md-tit md-t2"', "Como convivo"], ["##"]),
    ("codigo suelto", "las rutas van en `app/rutas.py`",
     ["md-cod", "app/rutas.py"], ["`"]),
    ("viñetas",       "- uno\n- dos",
     ["<ul", "<li>uno</li>", "<li>dos</li>"], ["- uno"]),
    ("numerada",      "1. primero\n2. segundo",
     ["<ol", "<li>primero</li>"], ["1. primero"]),
    ("raya",          "arriba\n---\nabajo",
     ["md-raya"], ["<li>--"]),
    ("cita",          "> me dijo esto",
     ["md-cita", "me dijo esto"], ["&gt; me"]),
    ("enlace",        "esta en [el panel](http://localhost:8750/pizarra) ahora",
     ['href="http://localhost:8750/pizarra"', ">el panel</a>"], ["]("]),
    ("tabla",         "| a | b |\n|---|---|\n| 1 | 2 |",
     ["<table", "<th>a</th>", "<td>2</td>"], ["|---|"]),
    # Adentro de un bloque de codigo NO se toca nada: un ** ahi es un **.
    ("bloque ```",    "mira:\n```python\nx = a ** 2\n```\nlisto",
     ["md-pre", "x = a ** 2"], ['<b>']),
    ("** en codigo",  "poné `a ** b` ahi",
     ["md-cod", "a ** b"], ["<b>"]),
    # ⚠ Regresion: la marca interna de lo guardado es un NUL, no un espacio. Con un
    # espacio, un " 3 " del texto se comia el numero y aparecia "undefined".
    ("numero suelto", "hay 3 casos y 12 archivos",
     ["hay 3 casos y 12 archivos"], ["undefined"]),
    ("multiplicar",   "la cuenta es 2 * 3 * 4 nomas",
     ["2 * 3 * 4"], ["<i>"]),
    # Lo que llega es texto de afuera: si trae HTML, se ve como texto.
    ("inyeccion",     "ojo con <script>alert(1)</script> y <b>esto</b>",
     ["&lt;script&gt;"], ["<script", "<b>esto"]),
    ("ampersand",     "uno & dos",
     ["&amp;"], []),
    ("vacio",         "", [], ["undefined"]),
]

LARGO = """Leído: `CLAUDE.md` del proyecto, la skill **paralelo** y `PIZARRA.md` entera.

## Cómo convivo con otras sesiones

- **Dueño de la máquina: uno solo.** El que toca `app/voz/`, `app/ingesta/` o `panel.py`.
- **Techo: 2 agentes acá** (3 excepcional).
  - lo que no necesita la máquina va en *worktree*
- **Pizarra**: anoto mi tarea antes de tocar nada.

## Lo que veo ahora en el repo

Hay **trabajo sin commitear** justo en la zona de interfaz:

```python
def hola(nombre):
    return f"hola {nombre}"
```

1. **¿Esos cambios son míos para seguir?**
2. **¿Soy el dueño de la máquina** en esta sesión?

Decime eso y arranco anotándome en la [Pizarra](http://localhost:8750/pizarra)."""

PAGINA = """<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#0b0d12;color:#e8ecf1;
             font:14px/1.5 Segoe UI,system-ui,sans-serif;padding:18px">
<div id="burbuja" style="padding:9px 13px;border-radius:13px;background:#171c24;
     border-left:3px solid #a78bfa;max-width:760px;white-space:pre-wrap;
     word-break:break-word;font-size:13.6px;line-height:1.5"></div>"""


def main():
    fallas = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 900, "height": 900})
        pag.set_content(PAGINA)
        pag.add_script_tag(path=str(ESTATICOS / "marcado.js"))

        for nombre, entrada, esperados, prohibidos in CASOS:
            html = pag.evaluate("t => md(t)", entrada)
            for e in esperados:
                if e not in html:
                    fallas.append(f"{nombre}: falta {e!r} en {html!r}")
            for p_ in prohibidos:
                if p_ in html:
                    fallas.append(f"{nombre}: sobra {p_!r} en {html!r}")

        # La respuesta larga, dibujada y mirada: ni un asterisco ni un numeral suelto.
        pag.evaluate("t => document.getElementById('burbuja')"
                     ".innerHTML = '<div class=\"md\">' + md(t) + '</div>'", LARGO)
        visto = pag.inner_text("#burbuja")
        for sobra in ("**", "##", "```"):
            if sobra in visto:
                fallas.append(f"largo: se sigue viendo {sobra!r} en la pantalla")
        if "def hola(nombre):" not in visto:
            fallas.append("largo: se perdio el bloque de codigo")
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.evaluate("md('probando')")
        if errores:
            fallas.append("errores de JS: " + " | ".join(errores))

        pag.locator("#burbuja").screenshot(path=str(SALIDA))
        nav.close()

    print(f"captura: {SALIDA}")
    if fallas:
        print(f"\n{len(fallas)} FALLA(S):")
        for f in fallas:
            print("  -", f)
        raise SystemExit(1)
    print(f"OK: {len(CASOS)} casos + la respuesta larga, sin asteriscos a la vista")


if __name__ == "__main__":
    main()
