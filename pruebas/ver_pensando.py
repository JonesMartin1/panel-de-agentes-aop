"""Mira cómo se ve la burbuja de "pensando" mientras una sesión piensa.

No manda un mensaje de verdad (tardaría un minuto y ensuciaría una charla): finge
que hay un turno en vuelo y saca dos capturas separadas por medio segundo, así se
ve que los puntitos se mueven y que el relojito cuenta.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

SALIDA = Path(__file__).resolve().parents[1] / "resultados"
errores = []


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
        pg.goto("http://127.0.0.1:8750/sesiones", wait_until="networkidle")
        pg.wait_for_timeout(2500)

        # Abrimos la primera sesión que haya y le colgamos un turno en vuelo.
        abierta = pg.evaluate("""() => {
            const p = datos.proyectos.find(x => x.sesiones.length);
            if (!p) return null;
            const s = p.sesiones[0];
            abiertas = [{sid: s.id, cwd: p.cwd, nombre: s.nombre || s.id.slice(0,8)}];
            activa = s.id;
            enVuelo[s.id] = 'probando la animación';
            arranque[s.id] = Date.now() - 8000;   // como si llevara 8 segundos
            firma = ''; pintarTabs(); pintarSesion();
            return s.nombre || s.id;
        }""")
        if not abierta:
            print("no hay ninguna sesión para probar")
            return
        pg.wait_for_timeout(1800)
        caja = pg.locator(".msg.pensa")
        print("burbuja visible:", caja.count() == 1 and caja.is_visible())
        print("texto:", caja.inner_text().replace("\n", " "))
        caja.scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SALIDA / "ver_pensando_1.png"))
        pg.wait_for_timeout(600)                  # medio ciclo de la animación
        pg.screenshot(path=str(SALIDA / "ver_pensando_2.png"))
        opacidades = pg.evaluate(
            "() => [...document.querySelectorAll('.msg.pensa .pts i')]"
            ".map(i => getComputedStyle(i).opacity)")
        print("opacidad de cada puntito:", opacidades, "(distintas = está animando)")
        print("punto de la pestaña pulsando:",
              pg.locator(".tab .viva.late").count() == 1)

        # Segunda parte: una sesión que está trabajando de verdad (proceso vivo y
        # movido recién) tiene que mostrar la burbuja aunque el turno no lo hayas
        # mandado vos desde acá — que es lo que fallaba.
        cual = pg.evaluate("""() => {
            const ahora = Date.now()/1000;
            const s = datos.proyectos.flatMap(p =>
                p.sesiones.map(s => ({...s, cwd: p.cwd})))
                .find(s => s.viva && (ahora - (s.ts||0)) < 45);
            if (!s) return null;
            abiertas = [{sid: s.id, cwd: s.cwd, nombre: s.nombre || s.id.slice(0,8)}];
            activa = s.id; enVuelo = {}; arranque = {};
            firma = ''; pintarTabs(); pintarSesion();
            return s.nombre || s.id;
        }""")
        if cual:
            pg.wait_for_timeout(1500)
            caja2 = pg.locator(".msg.pensa")
            print("sesión que trabaja:", cual, "| burbuja sin turno propio:",
                  caja2.count() == 1)
            if caja2.count():
                caja2.scroll_into_view_if_needed()
                pg.wait_for_timeout(1200)
                print("texto:", caja2.inner_text().replace("\n", " "))
                pg.screenshot(path=str(SALIDA / "ver_pensando_3.png"))
        else:
            print("no había ninguna sesión trabajando justo ahora")
        b.close()
    print("errores de JS:", errores or "ninguno")


if __name__ == "__main__":
    main()
