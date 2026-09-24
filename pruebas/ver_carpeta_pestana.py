"""La carpeta marcada a la izquierda tiene que ser la del proyecto de la pestaña
que estas mirando (pedido de Martin, 2026-08-17).

Antes `proy` (la carpeta pintada) solo cambiaba al hacer clic en la barra izquierda,
asi que uno abria una charla de un proyecto, se iba a mirar otra carpeta, volvia a la
pestaña... y seguia marcado el proyecto equivocado.

⚠ Esta prueba SOLO lee y hace clic en pestañas: nunca toca "Enviar", asi que no
arranca ningun proceso `claude` ni escribe en ninguna sesion real.

Correr con:  python -m pruebas.ver_carpeta_pestana   (con el panel prendido)
"""
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

# La consola de Windows es cp1252 y aca se imprimen nombres de proyectos con acentos.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
fallas = []


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def marcada(pagina):
    """El nombre del proyecto que se ve MARCADO en la barra izquierda."""
    return pagina.evaluate(
        "() => { const c = document.querySelector('.carpeta.sel');"
        "        return c ? c.querySelector('.nom').textContent : null; }")


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1400, "height": 900})
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        # ⚠ networkidle NUNCA llega en este panel (hace polling solo).
        pagina.goto("http://localhost:8750/sesiones", wait_until="domcontentloaded")
        # ⚠⚠ Y tampoco sirve una espera fija: `/movil/sesiones` tarda entre medio segundo y
        # varios según lo ocupado que esté el panel. Con 2,5 s clavados, esta prueba fallaba
        # una de cada dos corridas diciendo "no hay dos proyectos" — y no era cierto, era
        # que todavía no habían llegado. Se espera AL DATO (2026-08-18).
        pagina.wait_for_function("() => datos && datos.proyectos.length > 1", timeout=40000)
        pagina.wait_for_timeout(400)

        # Dos proyectos con conversaciones, lo mas separados posible en la lista:
        # asi se prueba de paso que la carpeta marcada se acerque sola con el scroll.
        pares = pagina.evaluate(
            "() => { const c = datos.proyectos.filter(p => p.sesiones.length);"
            "        return c.length < 2 ? null : [c[0], c[c.length-1]]; }")
        if not pares:
            print("MAL: hacen falta dos proyectos con conversaciones para probar")
            raise SystemExit(1)
        a, b = pares
        print(f"proyecto A: {a['proyecto']}   proyecto B: {b['proyecto']}\n")

        # --- Una pestaña del proyecto A: la carpeta marcada es A ---
        pagina.evaluate("p => irProyecto(p)", a["proyecto"])
        pagina.wait_for_timeout(300)
        sid_a = a["sesiones"][0]["id"]
        pagina.evaluate("s => abrirSesion(s.cwd, s.sid, s.nom)",
                        {"cwd": a["cwd"], "sid": sid_a, "nom": a["sesiones"][0]["nombre"]})
        pagina.wait_for_timeout(700)
        revisar("con la pestaña de A abierta, la carpeta marcada", marcada(pagina), a["proyecto"])

        # --- Me voy a mirar la carpeta B (esto suelta la pestaña, como Gmail) ---
        pagina.evaluate("p => irProyecto(p)", b["proyecto"])
        pagina.wait_for_timeout(400)
        revisar("mirando la carpeta B, la marcada", marcada(pagina), b["proyecto"])
        revisar("mirando una carpeta no hay pestaña activa",
                pagina.evaluate("() => activa"), None)

        # --- Vuelvo a la pestaña de A con un clic REAL: la carpeta tiene que volver a A ---
        # el clic va a la izquierda del rotulo, lejos de la cruz de cerrar
        pagina.click("#tabs .tab", position={"x": 12, "y": 14})
        pagina.wait_for_timeout(700)
        revisar("volviendo a la pestaña de A, la marcada", marcada(pagina), a["proyecto"])
        revisar("volviendo a la pestaña de A, la sesion activa",
                pagina.evaluate("() => activa"), sid_a)

        # --- Dos pestañas de proyectos distintos: la carpeta sigue a la que mirás ---
        sid_b = b["sesiones"][0]["id"]
        pagina.evaluate("s => abrirSesion(s.cwd, s.sid, s.nom)",
                        {"cwd": b["cwd"], "sid": sid_b, "nom": b["sesiones"][0]["nombre"]})
        pagina.wait_for_timeout(700)
        revisar("abriendo una pestaña de B, la marcada", marcada(pagina), b["proyecto"])
        pagina.screenshot(path=str(SALIDA / "sesiones_carpeta_pestana.png"))
        pagina.evaluate("s => irTab(s)", sid_a)
        pagina.wait_for_timeout(700)
        revisar("saltando de la pestaña de B a la de A, la marcada",
                marcada(pagina), a["proyecto"])

        # --- Al cerrar la pestaña te vas a "Todas" ---
        # ⚠ Cambió el 2026-08-17, a pedido de Martín ("cuando le doy X a las sesiones,
        # quiero que me lleve a todas"): antes te dejaba en la carpeta de esa charla.
        # Si volviera a fallar acá, mirá `cerrar()` en sesiones.html antes de tocar nada.
        pagina.evaluate("() => cerrar(abiertas.findIndex(t => t.sid === activa))")
        pagina.wait_for_timeout(500)
        revisar("cerrando la pestaña, quedás en Todas", marcada(pagina), "Todas")

        # --- Y ahora TODOS los proyectos de la lista, uno por uno -------------
        # La pregunta de Martin fue justo esta: ¿anda para todos o solo para los
        # dos que probe? Los que no tienen ninguna conversacion se prueban con una
        # pestaña NUEVA, que es la unica forma de entrar ahi.
        print()
        todos = pagina.evaluate("() => datos.proyectos.map("
                                "p => ({proyecto:p.proyecto, cwd:p.cwd, vivo:p.vivo,"
                                "       sid:(p.sesiones[0]||{}).id || ''}))")
        for x in todos:
            pagina.evaluate("s => abrirSesion(s.cwd, s.sid, s.proyecto)", x)
            pagina.wait_for_timeout(260)
            revisar(("pestaña nueva en " if not x["sid"] else "pestaña de ") + x["proyecto"] +
                    (" (vivo)" if x["vivo"] else ""), marcada(pagina), x["proyecto"])
        print(f"\n{len(todos)} proyectos probados")

        revisar("errores de javascript en la pagina", errores, [])
        navegador.close()

    print()
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
