"""El selector de preguntas con opciones (AskUserQuestion) en la pantalla /sesiones.

Cuando la sesion pregunta algo con opciones, en el hilo aparece un cartel con las
opciones como BOTONES, un campo "Otra respuesta…" y — si hay varias preguntas o
seleccion multiple — un boton Responder (pedido de Martin, 2026-08-18).

⚠ `/movil/chat` y `/movil/responder` se INTERCEPTAN: el panel vivo todavia no tiene
el campo `pregunta` ni el endpoint nuevo (estan en memoria hasta el reinicio), asi que
la prueba corre sin reiniciarlo — y ademas contestar de verdad necesitaria un proceso
`claude` esperando. Deja una captura en resultados/pregunta_sesiones.png.

Correr con:  D:/IA/envs/wpp/python.exe -m pruebas.ver_pregunta_sesion  (panel prendido)
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8750"
RAIZ = Path(__file__).resolve().parents[1]
CAPTURA = RAIZ / "resultados" / "pregunta_sesiones.png"
SID = "prueba-pregunta-0000"
fallas = []

UNA = {"hora": 111.0, "preguntas": [{
    "pregunta": "¿Cómo publico la demo?", "titulo": "Acceso", "multi": False,
    "opciones": [
        {"etiqueta": "Con usuario y contraseña",
         "detalle": "Agrego login antes de publicar: los datos no quedan abiertos."},
        {"etiqueta": "Abierta, es solo una demo",
         "detalle": "Sin login. Cualquiera con el link ve todo."},
        {"etiqueta": "Solo por túnel SSH",
         "detalle": "No se publica: entrás vos con ssh -L y nadie más."}]}]}

DOS = {"hora": 222.0, "preguntas": [
    {"pregunta": "¿Qué colores llevo?", "titulo": "Colores", "multi": True,
     "opciones": [{"etiqueta": "Azul", "detalle": ""},
                  {"etiqueta": "Verde", "detalle": ""},
                  {"etiqueta": "Arena", "detalle": ""}]},
    {"pregunta": "¿Con qué letra?", "titulo": "Letra", "multi": False,
     "opciones": [{"etiqueta": "La de siempre", "detalle": ""},
                  {"etiqueta": "Monoespaciada", "detalle": ""}]}]}

MODELOS = {"ok": True, "modelo": "opus", "defecto": "opus",
           "modelos": [{"id": "opus", "nombre": "Opus (200 mil)"}]}


def revisar(que, obtenido, esperado=True):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


def main():
    estado = {"pregunta": UNA}       # lo que /movil/chat contesta AHORA
    respuestas = []                  # lo que la pantalla mando a /movil/responder

    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_context(viewport={"width": 1400, "height": 900}).new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def chat(ruta):
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"mensajes": [
                             {"de": "vos", "texto": "publicá la demo"},
                             {"de": "claude", "texto": "Antes de publicar necesito "
                              "que decidas una cosa."}],
                             "pregunta": estado["pregunta"]}))

        def responder(ruta):
            respuestas.append(ruta.request.post_data_json)
            ruta.fulfill(status=200, content_type="application/json",
                         body=json.dumps({"ok": True}))

        pag.route("**/movil/chat*", chat)
        pag.route("**/movil/responder", responder)
        pag.route("**/movil/modelo*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(MODELOS)))

        pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
        pag.wait_for_selector("#cuerpo .correo[data-sid]", timeout=20000)
        pag.evaluate("""sid => {
          const p = datos.proyectos[0];
          abiertas = [{sid, cwd: p.cwd, nombre: 'De prueba'}];
          activa = null; grupoAbierto = ''; guardar(); irTab(sid);
        }""", SID)
        pag.wait_for_selector(".pregunta", timeout=8000)
        # El turno está en vuelo, como cuando lo mandaste vos: así al contestar la
        # pregunta tiene que VOLVER la burbuja de "pensando" (la sesión sigue
        # trabajando con tu respuesta). El texto calza con el último mensaje 'vos'
        # para que no se dibuje duplicado (la guarda `yaLlego`).
        pag.evaluate("""() => { enVuelo[activa] = 'publicá la demo';
                                arranque[activa] = Date.now(); firma = ''; }""")

        # --- El selector, dibujado ------------------------------------------------
        revisar("la pregunta está a la vista",
                pag.inner_text(".pregunta .pPreg"), "¿Cómo publico la demo?")
        revisar("con su chapa de tema", pag.inner_text(".pregunta .pTit"), "ACCESO")
        revisar("las tres opciones son botones",
                pag.evaluate("() => document.querySelectorAll('.pregunta .pOp').length"), 3)
        revisar("cada opción muestra su detalle",
                pag.evaluate("""() => document.querySelector(
                    '.pregunta .pOp span').textContent.includes('login')"""), True)
        revisar("está el campo de respuesta libre",
                pag.is_visible(".pregunta .pOtra input"), True)
        revisar("y reemplaza a la burbuja de pensando",
                pag.evaluate("() => document.querySelector('#hilo .msg.pensa')"), None)
        # ⚠ Nada del selector puede ser rojo: preguntar no es un error (regla de
        # Martín). Se mira el color computado del borde del cartel.
        revisar("el cartel no es rojo",
                pag.evaluate("""() => {
                  const c = getComputedStyle(document.querySelector('.pregunta'))
                      .borderLeftColor.match(/\\d+/g).map(Number);
                  return c[0] > 180 && c[1] < 90 && c[2] < 90;
                }"""), False)
        CAPTURA.parent.mkdir(exist_ok=True)
        pag.screenshot(path=str(CAPTURA))

        # --- Una pregunta simple: tocar la opción ES contestar --------------------
        pag.click(".pregunta .pOp[data-q='0'][data-o='2']")
        pag.wait_for_timeout(400)
        revisar("tocar una opción manda la elección",
                respuestas and respuestas[-1].get("respuestas"),
                {"¿Cómo publico la demo?": "Solo por túnel SSH"})
        revisar("con la carpeta y la sesión de la pestaña",
                bool(respuestas) and respuestas[-1].get("sid") == SID
                and bool(respuestas[-1].get("cwd")), True)
        revisar("y el selector se esconde al toque (sin esperar al servidor)",
                pag.evaluate("() => document.querySelector('.pregunta')"), None)
        revisar("volviendo a la burbuja de pensando (la sesión sigue trabajando)",
                pag.evaluate("() => !!document.querySelector('#hilo .msg.pensa')"), True)

        # --- Llega una pregunta NUEVA (otra hora): aparece de vuelta --------------
        estado["pregunta"] = DOS
        pag.wait_for_selector(".pregunta", timeout=8000)
        revisar("una pregunta nueva vuelve a dibujarse",
                pag.evaluate("() => document.querySelectorAll('.pregunta .pBloque').length"), 2)
        revisar("con varias preguntas hay UN botón Responder",
                pag.evaluate("() => document.querySelectorAll('.pregunta .pMandar').length"), 1)

        # Responder incompleto avisa qué falta en vez de mandar a medias.
        pag.click(".pregunta .pMandar")
        pag.wait_for_timeout(300)
        revisar("incompleto NO manda nada", len(respuestas), 1)
        revisar("y avisa qué falta",
                pag.evaluate("() => document.querySelector('.pregunta .pNota')"
                             ".textContent.includes('Falta contestar')"), True)

        # La multiSelect junta varias con ', '; lo tipeado le gana a los botones.
        pag.click(".pregunta .pOp[data-q='0'][data-o='0']")
        pag.click(".pregunta .pOp[data-q='0'][data-o='2']")
        revisar("las marcadas quedan encendidas",
                pag.evaluate("() => document.querySelectorAll('.pregunta .pOp.puesta').length"), 2)
        # ⚠ El hilo se rearma cada 3 s: lo tipeado y lo marcado tienen que sobrevivir
        # al repintado (misma familia que las marcas de texto).
        pag.fill(".pregunta .pOtra input[data-q='1']", "con la letra del panel")
        pag.wait_for_timeout(3600)
        revisar("lo tipeado sobrevive al repintado de cada 3 s",
                pag.input_value(".pregunta .pOtra input[data-q='1']"),
                "con la letra del panel")
        revisar("y lo marcado también",
                pag.evaluate("() => document.querySelectorAll('.pregunta .pOp.puesta').length"), 2)
        pag.click(".pregunta .pMandar")
        pag.wait_for_timeout(400)
        revisar("completo manda todo junto",
                respuestas and respuestas[-1].get("respuestas"),
                {"¿Qué colores llevo?": "Azul, Arena",
                 "¿Con qué letra?": "con la letra del panel"})

        revisar("sin errores de JS", errores, [])
        nav.close()

    print()
    print(f"captura: {CAPTURA}")
    if fallas:
        print(f"{len(fallas)} mal:", *fallas, sep="\n  - ")
        sys.exit(1)
    print("todo bien")


if __name__ == "__main__":
    main()
