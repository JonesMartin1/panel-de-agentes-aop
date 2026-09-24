"""Chequea el color que le pone la lista de /sesiones a cada situación.

Con datos inventados a propósito: con las sesiones de verdad el resultado depende
de qué esté corriendo justo en ese momento y la prueba no probaría nada.

La regla que se verifica (2026-08-17): un turno lanzado desde el panel o el celular
vive SOLO mientras piensa, así que proceso vivo = trabajando aunque haga rato que no
escribe. Solo una ventana de Claude Code abierta en la compu (interactiva) puede
estar viva sin hacer nada, y esa se juzga por el reloj.
"""
import json

from playwright.sync_api import sync_playwright

AHORA = 1_800_000_000          # cualquier instante: la página usa Date.now(), lo fijamos

CASOS = [
    # (qué es, viva, interactiva, hace cuántos segundos habló, quién habló último, esperado)
    ("turno del panel pensando hace rato", True, False, 190, "vos", "trabajando"),
    ("turno del panel recién lanzado", True, False, 3, "vos", "trabajando"),
    ("turno del panel escribiendo", True, False, 5, "claude", "trabajando"),
    ("ventana abierta en la compu, tecleando", True, True, 6, "claude", "trabajando"),
    ("ventana abierta en la compu, quieta y te contestó", True, True, 300, "claude", "espera"),
    ("charla del celular que terminó de contestar", False, False, 120, "claude", "espera"),
    ("… esa misma, pero ya entraste a leerla", False, False, 120, "claude", ""),
    ("charla vieja que ya es historia", False, False, 7200, "claude", ""),
    ("terminó hablando vos y no hay proceso", False, False, 60, "vos", ""),
]


def main():
    sesiones = [{"id": f"s{i}", "nombre": n, "viva": v, "interactiva": inter,
                 "ts": AHORA / 1000 - hace, "ultimo": ult, "detalle": "detalle"}
                for i, (n, v, inter, hace, ult, _) in enumerate(CASOS)]
    datos = {"proyectos": [{"proyecto": "Prueba", "cwd": "D:/prueba", "sesiones": sesiones}]}

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.add_init_script(f"Date.now = () => {AHORA};")
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.goto("http://127.0.0.1:8750/sesiones", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        clases = pg.evaluate("""(d) => {
            datos = d; proy = TODAS; activa = null; abiertas = []; falladas = {};
            // s6 es la que ya leíste: la marca de "visto" es posterior a su respuesta.
            visto = {s6: d.proyectos[0].sesiones[6].ts + 1};
            firma = ''; pintarTabs(); pintar();
            return [...document.querySelectorAll('.correo')]
                .map(e => [e.dataset.sid, e.className.replace('correo','').trim()]);
        }""", datos)

        mapa = dict(clases)
        malas = 0
        for i, (nombre, *_, esperado) in enumerate(CASOS):
            visto = mapa.get(f"s{i}", "(no salió en la lista)")
            ok = visto == esperado
            malas += not ok
            print(("OK  " if ok else "MAL ") + f"{nombre:<45} esperado '{esperado}' / vi '{visto}'")
        pg.screenshot(path="resultados/ver_estado_sesiones.png")

        # Segunda parte: la marca roja se verifica sola. Si la sesión escribió DESPUÉS
        # del error, es que contestó igual (se cortó la página, no la conversación).
        print()
        rojas = pg.evaluate("""(d) => {
            datos = d;
            const ses = datos.proyectos[0].sesiones;
            falladas = {
              s2: {que: 'Se cortó: Failed to fetch', ts: ses[2].ts - 60},  // habló después
              s4: {que: 'Se cortó: Failed to fetch', ts: ses[4].ts + 60},  // falló después
              s0: {que: 'Se cortó: Failed to fetch', ts: ses[0].ts - 60},  // el último sos vos
              s5: 'formato viejo, texto pelado'
            };
            verificarFalladas();
            return Object.keys(falladas);
        }""", datos)
        for sid, dice in [("s2", "contestó después del error: se limpia"),
                          ("s4", "el error es posterior: sigue roja"),
                          ("s0", "sigue pensando, no contestó: sigue roja"),
                          ("s5", "marca vieja con respuesta a la vista: se limpia")]:
            deberia_quedar = sid in ("s4", "s0")
            ok = (sid in rojas) == deberia_quedar
            print(("OK  " if ok else "MAL ") + f"{dice:<50} quedó roja: {sid in rojas}")
        b.close()
    print("errores de JS:", errores or "ninguno")
    print(f"{len(CASOS)-malas}/{len(CASOS)} bien")


if __name__ == "__main__":
    main()
