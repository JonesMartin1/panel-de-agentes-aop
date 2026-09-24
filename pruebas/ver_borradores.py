"""El borrador de cada conversacion, en la pantalla.

Pedido de Martin (2026-08-18): *"quiero que lo que yo escriba dentro de una sesion quede
guardado como borrador y se pueda ver en todas, con una señalizacion que diga que esta en
borrador, que tenga un color y una animacion"*.

Lo que fija:
  * escribir en una conversacion y NO mandar guarda el borrador en el servidor;
  * la bandeja (Todas) muestra la chapa "✎ Borrador" con lo que dejaste escrito;
  * ⭐ el color NO es ninguno de los tres del semaforo (verde/amarillo/rojo): un borrador
    no es un estado de la conversacion, es algo tuyo a medio escribir;
  * ⭐ y se MUEVE de verdad: la prueba mide la animacion computada, no la clase;
  * volver a la conversacion devuelve el texto ENTERO a la caja (no el anticipo cortado);
  * vaciar la caja apaga la chapa, y mandar el mensaje tambien;
  * un borrador escrito en OTRA pantalla (el celular) aparece aca solo.

⚠ El servidor de borradores esta INVENTADO adentro de la prueba (un diccionario), asi que
corre sin reiniciar el panel y sin tocar el `borradores_sesiones.json` de verdad, que
tiene lo que Martin dejo escrito. `/movil/mandar` tambien: mandar de verdad seria un turno
contra una sesion suya.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_borradores   (con el panel prendido)
"""
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SALIDA = RAIZ / "pruebas"
BASE = "http://127.0.0.1:8750"
CHARLA = {"mensajes": [{"de": "claude" if i % 2 else "vos",
                        "texto": f"Renglón {i} de la conversación.", "imgs": []}
                       for i in range(8)]}
# Los tres del semáforo, en el formato que devuelve el navegador.
SEMAFORO = ["rgb(61, 220, 132)", "rgb(245, 158, 11)", "rgb(239, 68, 68)",
            "rgb(255, 107, 107)", "rgb(168, 240, 198)", "rgb(255, 208, 138)"]
BORRADOR = "Esto lo dejé a medio escribir y me fui a hacer otra cosa."

fallas = []
guardados = {}          # el servidor de borradores, inventado


def revisar(que, obtenido, esperado):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def servidor_falso(pag):
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(CHARLA)))

    def leer(ruta):
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps(guardados))

    def escribir(ruta):
        d = json.loads(ruta.request.post_data or "{}")
        sid, texto = d.get("sid") or "", d.get("texto") or ""
        if texto.strip():
            guardados[sid] = {"texto": texto, "ts": 1}
        else:
            guardados.pop(sid, None)
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps({"ok": True, "hay": sid in guardados}))

    # ⚠ Dos rutas distintas y sin comodín al final: `**/movil/borrador*` le pegaría a las
    # dos y Playwright prueba de la última a la primera (la piedra de `ver_marcas_texto`).
    pag.route("**/movil/borradores", leer)
    pag.route("**/movil/borrador", escribir)
    # Mandar de verdad seria un turno contra una sesion de Martin.
    pag.route("**/movil/mandar", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "respuesta": "listo", "sid": r.request.url and ""})))


def chapa(pag, sid):
    """Lo que muestra la fila de esa conversacion en la bandeja."""
    return pag.evaluate("""(sid) => {
      const f = document.querySelector('#cuerpo .correo[data-sid="' + sid + '"]');
      if (!f) return null;
      const ch = f.querySelector('.borra'), pre = f.querySelector('.bpre');
      if (!ch) return {hay: false};
      const e = getComputedStyle(ch), p = getComputedStyle(ch.querySelector('.plu'));
      return {hay: true, dice: ch.textContent.trim(), anticipo: pre ? pre.textContent : '',
              color: e.color, borde: e.borderTopColor,
              anima: e.animationName, dura: parseFloat(e.animationDuration),
              animaPluma: p.animationName, duraPluma: parseFloat(p.animationDuration)};
    }""", sid)


def celular(nav):
    """Lo mismo en la app del telefono, que es la pantalla de la captura de Martin.

    ⚠⚠ La app del celular vive DENTRO de `panel.py` (`MOVIL_HTML`), así que el panel que
    está corriendo sirve todavía la versión vieja: la prueba le sirve la del DISCO
    interceptando `/movil`. Es la única forma de probar esto sin reiniciar el panel.
    ⚠ Y se le tapan las pestañas (`/movil/pestanas`), que viven en el servidor: sin eso la
    prueba le movería a Martín las pestañas de su teléfono de verdad.
    """
    import panel                     # el modulo fresco del disco, no el que corre
    print("\n--- la app del celular ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    servidor_falso(pag)
    pestanas = {"pestanas": [], "activa": "panel"}
    pag.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True} if r.request.method == "POST" else pestanas)))
    pag.route("**/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=panel.MOVIL_HTML))
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof hayBorrador === 'function'", timeout=30000)
    pag.wait_for_timeout(2500)
    revisar("la app del celular carga con el código nuevo, sin errores", errores, [])

    guardados.clear()
    sid = pag.evaluate("""() => {
      const p = (listaSes || {proyectos: []}).proyectos.find(x => x.sesiones.length);
      if (!p) return '';
      abrir(p.cwd, p.sesiones[0].id, p.sesiones[0].nombre);
      return p.sesiones[0].id; }""")
    if not sid:
        revisar("(el celular no encontró conversaciones para probar)", True, False)
        ctx.close()
        return
    pag.wait_for_timeout(1200)
    pag.fill("#texto", BORRADOR)
    pag.wait_for_timeout(1300)
    revisar("escribir en el celular guarda el borrador",
            (guardados.get(sid) or {}).get("texto"), BORRADOR)

    pag.evaluate("() => ir('nueva')")            # la bandeja del telefono
    pag.wait_for_selector("#cuerpo .correo", timeout=20000)
    pag.wait_for_timeout(800)
    c = pag.evaluate("""(sid) => {
      const f = document.querySelector('#cuerpo .correo[data-sid="' + sid + '"]');
      const ch = f && f.querySelector('.borra');
      if (!ch) return {hay: false};
      const e = getComputedStyle(ch);
      return {hay: true, dice: ch.textContent.trim(), color: e.color,
              anima: e.animationName, dura: parseFloat(e.animationDuration)};
    }""", sid)
    revisar("la bandeja del celular muestra la chapa", c["hay"], True)
    revisar("con el mismo lavanda que en la compu", c.get("color"), "rgb(196, 181, 253)")
    revisar("y también se mueve",
            [c.get("anima") != "none", (c.get("dura") or 0) > 0], [True, True])
    pag.screenshot(path=str(SALIDA / "borradores_movil.png"))

    pag.evaluate("(sid) => ir(sid)", sid)
    pag.wait_for_timeout(1200)
    revisar("y volver a la conversación devuelve lo escrito",
            pag.input_value("#texto"), BORRADOR)
    revisar("errores de javascript en el celular", errores, [])
    ctx.close()


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1320, "height": 760})
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))
        servidor_falso(pag)
        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_function("() => datos && datos.proyectos.length", timeout=40000)
        # Se arranca de cero: nada guardado de una corrida anterior.
        pag.evaluate("() => { borradores = {}; guardarBorradores(); abiertas = []; "
                     "activa = null; guardar(); }")

        # --- Escribir y NO mandar ---------------------------------------------------
        sids = pag.evaluate("""() => {
          const con = datos.proyectos.filter(p => p.sesiones.length);
          const a = con[0].sesiones[0];
          const b = (con[0].sesiones[1] || (con[1] || {sesiones:[]}).sesiones[0]);
          abrirSesion(con[0].cwd, a.id, a.nombre);
          return [a.id, b ? b.id : ''];
        }""")
        sid, otro = sids[0], sids[1]
        pag.wait_for_selector("#cuerpo .msg", timeout=20000)
        pag.fill("#texto", BORRADOR)
        pag.wait_for_timeout(1300)          # el respiro de 700 ms + el viaje
        revisar("lo que escribí queda guardado en el servidor",
                (guardados.get(sid) or {}).get("texto"), BORRADOR)
        revisar("y la caja NO se vacía sola", pag.input_value("#texto"), BORRADOR)
        revisar("la pestaña de arriba muestra la plumita",
                pag.evaluate("(sid) => !!document.querySelector("
                             "'#tabs .tab[data-sid=\"' + sid + '\"] .plu')", sid), True)

        # --- La bandeja lo muestra ---------------------------------------------------
        pag.evaluate("() => irProyecto(TODAS)")
        pag.wait_for_selector("#cuerpo .correo .borra", timeout=20000)
        c = chapa(pag, sid)
        revisar("la fila de la bandeja tiene la chapa", c["hay"], True)
        revisar("y dice que está en borrador", c["dice"], "✎Borrador")
        revisar("con lo que dejaste escrito abajo", c["anticipo"], BORRADOR)
        revisar("⭐ el color es el lavanda del borrador", c["color"], "rgb(196, 181, 253)")
        revisar("⭐ y NO es ninguno de los tres del semáforo",
                [c["color"] in SEMAFORO, c["borde"] in SEMAFORO], [False, False])
        revisar("⭐ la chapa se mueve de verdad",
                [c["anima"] != "none", c["dura"] > 0], [True, True])
        revisar("y la plumita late aparte",
                [c["animaPluma"] != "none", c["duraPluma"] > 0], [True, True])
        pag.screenshot(path=str(SALIDA / "borradores.png"))

        # --- Volver a la conversación devuelve el texto ENTERO ------------------------
        pag.evaluate("(sid) => irTab(sid)", sid)
        pag.wait_for_selector("#cuerpo .msg", timeout=20000)
        revisar("volver a la conversación te devuelve lo escrito",
                pag.input_value("#texto"), BORRADOR)

        # --- Un borrador escrito en el CELULAR aparece acá solo -----------------------
        if otro:
            guardados[otro] = {"texto": "esto lo escribí desde el teléfono", "ts": 1}
            pag.evaluate("() => cargar()")
            pag.wait_for_timeout(1500)
            pag.evaluate("() => irProyecto(TODAS)")
            pag.wait_for_timeout(1200)
            c2 = chapa(pag, otro)
            revisar("un borrador escrito en otra pantalla aparece en la bandeja",
                    bool(c2 and c2["hay"]), True)
            revisar("y al abrir esa conversación, la caja lo trae",
                    (pag.evaluate("(sid) => { irTab(sid); return 1; }", otro) and
                     (pag.wait_for_timeout(600) or pag.input_value("#texto"))),
                    "esto lo escribí desde el teléfono")

        # --- Vaciar la caja apaga la chapa -------------------------------------------
        pag.evaluate("(sid) => irTab(sid)", sid)
        pag.wait_for_timeout(500)
        pag.fill("#texto", "")
        pag.wait_for_timeout(1300)
        revisar("vaciar la caja borra el borrador del servidor", sid in guardados, False)
        pag.evaluate("() => irProyecto(TODAS)")
        pag.wait_for_timeout(1200)
        revisar("y la chapa se apaga en la bandeja",
                (chapa(pag, sid) or {}).get("hay", False), False)

        # --- Mandar el mensaje también lo apaga --------------------------------------
        pag.evaluate("(sid) => irTab(sid)", sid)
        pag.wait_for_selector("#cuerpo .msg", timeout=20000)
        pag.fill("#texto", "esto sí lo mando")
        pag.wait_for_timeout(1300)
        revisar("(vuelve a haber borrador antes de mandar)", sid in guardados, True)
        pag.evaluate("() => mandar()")
        pag.wait_for_timeout(2000)
        revisar("⭐ mandarlo deja la conversación sin borrador", sid in guardados, False)
        revisar("y la caja queda vacía", pag.input_value("#texto"), "")

        # Se limpia lo que quedó en este navegador: la prueba no deja rastro.
        pag.evaluate("() => { borradores = {}; guardarBorradores(); abiertas = []; "
                     "activa = null; guardar(); }")
        revisar("errores de javascript", errores, [])
        ctx.close()

        celular(nav)
        nav.close()

    print(f"\ncaptura: {SALIDA / 'borradores.png'}")
    print("TODO BIEN" if not fallas else f"FALLARON {len(fallas)}: " + ", ".join(fallas))
    raise SystemExit(1 if fallas else 0)


if __name__ == "__main__":
    main()
