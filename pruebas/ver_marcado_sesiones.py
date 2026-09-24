"""Las dos pantallas de sesiones, de verdad, mostrando markdown dibujado.

`probar_marcado.py` prueba el dibujante suelto; esto prueba el CABLEADO: que la
pagina de la compu (`/sesiones`) y la del celular (`/movil`) carguen
`/estaticos/marcado.js`, lo usen en las burbujas de Claude y no queden asteriscos
a la vista. Deja dos capturas para mirarlas.

⚠ Solo LEE: la conversacion es inventada (se intercepta `/movil/chat`) y el guardado
de pestañas del celular se corta (`/movil/pestanas`), asi que no aparece ninguna
pestaña fantasma en el telefono de Martin ni se le escribe a ninguna sesion real.

Correr con:  python -m pruebas.ver_marcado_sesiones   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://localhost:8750"
SID = "demo-marcado"
CWD = str(RAIZ)

CHARLA = {"mensajes": [
    {"de": "vos", "texto": "Lee claude.md y la skill de cohexistencia entre sesiones",
     "imgs": []},
    {"de": "claude", "imgs": [], "texto":
     "Leído: `CLAUDE.md` del proyecto, la skill **paralelo** y `PIZARRA.md` entera.\n\n"
     "## Cómo convivo con otras sesiones\n\n"
     "- **Dueño de la máquina: uno solo.** El que toca `app/voz/` o `panel.py`.\n"
     "- **Techo: 2 agentes acá** (3 excepcional).\n"
     "- **Pizarra**: anoto mi tarea antes de tocar nada.\n\n"
     "## Lo que veo ahora en el repo\n\n"
     "Hay **trabajo sin commitear** justo en la zona de interfaz:\n\n"
     "```python\ndef hola(nombre):\n    return f\"hola {nombre}\"\n```\n\n"
     "1. **¿Esos cambios son míos para seguir?**\n"
     "2. **¿Soy el dueño de la máquina** en esta sesión?"},
]}

fallas = []


def revisar(que, ok, detalle=""):
    print(f"{'ok  ' if ok else 'MAL '} {que}{'' if ok else '  ' + detalle}")
    if not ok:
        fallas.append(que)


def preparar(pagina):
    """La charla inventada, y el guardado de pestañas del celular cortado."""
    pagina.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))
    pagina.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}")
        if r.request.method == "POST" else r.continue_())


def mirar(pagina, nombre):
    """Lo que se VE en la burbuja de Claude: ni un asterisco, ni un numeral."""
    visto = pagina.evaluate(
        "() => { const b = [...document.querySelectorAll('.msg.claude')].pop();"
        "        return b ? b.innerText : ''; }")
    negritas = pagina.evaluate("() => document.querySelectorAll('.msg.claude b').length")
    revisar(f"{nombre}: se dibujo la burbuja de Claude", len(visto) > 100, repr(visto[:80]))
    for sobra in ("**", "##", "```"):
        revisar(f"{nombre}: no se ve {sobra!r}", sobra not in visto)
    revisar(f"{nombre}: hay negritas de verdad", negritas >= 4, f"encontre {negritas}")
    revisar(f"{nombre}: quedo el bloque de codigo", "def hola(nombre):" in visto)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # --- La pantalla grande ---
        pag = nav.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        preparar(pag)
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_timeout(2200)
        pag.evaluate("s => abrirSesion(s.cwd, s.sid, 'Prueba de markdown')",
                     {"cwd": CWD, "sid": SID})
        pag.wait_for_timeout(1200)
        mirar(pag, "compu")
        pag.screenshot(path=str(SALIDA / "marcado_sesiones.png"))
        revisar("compu: sin errores de javascript", not errores, str(errores))

        # --- El telefono ---
        tel = nav.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errores_tel = []
        tel.on("pageerror", lambda e: errores_tel.append(str(e)))
        preparar(tel)
        tel.goto(BASE + "/movil", wait_until="domcontentloaded")
        tel.wait_for_timeout(2200)
        tel.evaluate("s => abrir(s.cwd, s.sid, 'Prueba de markdown')", {"cwd": CWD, "sid": SID})
        tel.wait_for_timeout(1200)
        mirar(tel, "celular")
        tel.screenshot(path=str(SALIDA / "marcado_movil.png"))
        revisar("celular: sin errores de javascript", not errores_tel, str(errores_tel))

        nav.close()

    print(f"\ncapturas: {SALIDA / 'marcado_sesiones.png'} y {SALIDA / 'marcado_movil.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
