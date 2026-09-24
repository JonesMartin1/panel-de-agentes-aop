"""Prueba los tres botones nuevos de la barra de la pizarra en pantalla de
telefono: papelera, deshacer y candado. Cada uno tiene que apagarse solo cuando
no aplica, y el candado ademas tiene que dar vuelta el icono.

Correr con:  python -m pruebas.ver_papelera_movil
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

# La consola de Windows es cp1252 y los iconos de los botones son emojis: sin esto
# la prueba se cae al IMPRIMIR el resultado, no al probar.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def estado_boton(pagina, ident):
    """(apagado?, icono) de un boton de la barra."""
    return pagina.evaluate(
        "id => { const b = document.getElementById(id);"
        "        return [b.classList.contains('apagado'), b.textContent.trim()]; }",
        ident)


def seleccionar(pagina, bloqueado):
    """Selecciona por codigo el primer objeto libre o bloqueado. El clic real se
    lo come el tablero en el navegador sin cabeza, y lo que se prueba aca es que
    refrescarBotonesBarra() reaccione a la seleccion."""
    return pagina.evaluate(
        """bloq => {
            const it = estado.items.find(i => !!i.bloqueado === bloq);
            if(!it) return false;
            seleccion.clear(); seleccion.add(it.id); pintarSeleccion(); return true;
        }""", bloqueado)


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 390, "height": 844},
                                    device_scale_factor=2, is_mobile=True,
                                    has_touch=True)
        pagina.goto("http://localhost:8750/pizarra", wait_until="networkidle")
        pagina.wait_for_timeout(1500)

        # --- Sin nada seleccionado: los tres apagados ---
        pagina.screenshot(path=str(SALIDA / "papelera_apagada.png"))
        revisar("papelera sin seleccion", estado_boton(pagina, "btnBorrar"), [True, "🗑"])
        revisar("candado sin seleccion", estado_boton(pagina, "btnCandado"), [True, "🔒"])
        revisar("deshacer sin historial", estado_boton(pagina, "btnDeshacer"), [True, "↶"])

        # --- Un objeto libre: papelera y candado (para bloquear) encendidos ---
        if seleccionar(pagina, bloqueado=False):
            pagina.wait_for_timeout(400)
            pagina.screenshot(path=str(SALIDA / "papelera_encendida.png"))
            revisar("papelera con objeto libre", estado_boton(pagina, "btnBorrar"), [False, "🗑"])
            revisar("candado con objeto libre", estado_boton(pagina, "btnCandado"), [False, "🔒"])
        else:
            fallas.append("no hay ningun objeto libre en la pizarra")

        # --- Un objeto bloqueado: la papelera NO, el candado si y dado vuelta ---
        if seleccionar(pagina, bloqueado=True):
            pagina.wait_for_timeout(400)
            pagina.screenshot(path=str(SALIDA / "candado_bloqueado.png"))
            revisar("papelera con objeto bloqueado", estado_boton(pagina, "btnBorrar"), [True, "🗑"])
            revisar("candado con objeto bloqueado", estado_boton(pagina, "btnCandado"), [False, "🔓"])
        else:
            print("aviso: no hay ningun objeto bloqueado para probar el candado")

        # --- El deshacer se prende solo cuando hay algo en la pila ---
        pagina.evaluate("() => guardarSnapshot()")
        revisar("deshacer con historial", estado_boton(pagina, "btnDeshacer"), [False, "↶"])
        pagina.evaluate("() => olvidarSnapshot()")
        revisar("deshacer tras olvidar el paso", estado_boton(pagina, "btnDeshacer"), [True, "↶"])

        navegador.close()

    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
