"""El color propio de cada charla, en la compu y en el celular.

Pedido de Martín (2026-10-10): *"poder editar lo que es el color del chat para cada sesión
individual"* — las dos burbujas y un tinte del fondo, en la compu y en el teléfono.

Lo que fija:
  * el servidor guarda, valida (solo `#rrggbb`) y borra los colores de una charla;
  * una charla con colores pinta SUS burbujas y su tinte, aunque su carpeta tenga otros;
  * ⭐ una charla sin colores propios HEREDA los de su carpeta, color por color (lo que la
    carpeta no eligió sigue con el general del 🎨);
  * una charla de OTRA carpeta no se entera de nada;
  * la lista de conversaciones vuelve a los colores generales;
  * el botón 🎨 del menú ⚙ abre el cuadrito y elegir un color lo manda al servidor, a la
    charla o —con "Toda la carpeta"— a la llave de la carpeta;
  * lo mismo en la app del celular, con su botón 🎨 en los ajustes de la sesión.

⚠ Los colores guardados están INVENTADOS adentro de la prueba: no toca el
`colores_charlas.json` de verdad. Y como el panel que corre puede ser el viejo, la prueba
sirve del DISCO las dos pantallas y los dos `.js` que cambiaron.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_color_charla   (panel prendido)
"""
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
CON = "colr-1111-1111-111111111111"      # la charla con colores propios
SIN = "colr-2222-2222-222222222222"      # la de al lado, sin nada propio: hereda la carpeta
OTRA = "colr-3333-3333-333333333333"     # de otra carpeta, que no eligió nada
CWD, OTRA_CWD = str(RAIZ), str(RAIZ / "pruebas")
CWD_DE = {CON: CWD, SIN: CWD, OTRA: OTRA_CWD}
VOS, IA, TINTE = "#c2185b", "#2e7d32", "#ff9800"
CARPETA_IA, CARPETA_TINTE = "#1565c0", "#7b1fa2"
CHARLA = [{"de": "vos", "texto": "hola", "imgs": []},
          {"de": "claude", "texto": "listo", "imgs": []}]

fallas = []
guardados = {}          # el servidor de colores, inventado
mandados = []           # lo que la pantalla le mandó a /charlas/color


def revisar(que, ok, detalle=""):
    print(("  ok   " if ok else "  MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def clave(cwd):
    """La llave de una carpeta, con la MISMA cuenta que `clave()` de colorcharla.js."""
    return "carpeta:" + cwd.replace("\\", "/").rstrip("/").lower()


def rgb(h):
    return "rgb(" + ", ".join(str(int(h[i:i + 2], 16)) for i in (1, 3, 5)) + ")"


# --- 1. El servidor -------------------------------------------------------------------
def servidor():
    print("\n--- el servidor ---")
    import panel                          # el del disco; sin `with`, no arranca nada
    from fastapi.testclient import TestClient
    tmp = Path(tempfile.mkdtemp()) / "colores_charlas.json"
    panel.COLORES_CHARLAS = tmp           # ⚠ nunca el archivo de verdad
    cli = TestClient(panel.app)
    r = cli.post("/charlas/color", json={"sid": CON, "vos": VOS.upper(), "ia": IA})
    revisar("guarda los colores de una charla", r.json().get("ok"), r.text[:80])
    revisar("y los devuelve", cli.get("/charlas/colores").json()["colores"].get(CON)
            == {"vos": VOS, "ia": IA})
    r = cli.post("/charlas/color", json={"sid": CON, "tinte": "red;background:url(x)"})
    revisar("un color que no es #rrggbb se rechaza", r.json().get("ok") is False, r.text[:80])
    r = cli.post("/charlas/color", json={"sid": "nueva-123", "vos": VOS})
    revisar("una charla sin estrenar no guarda nada", r.json().get("ok") is False)
    cli.post("/charlas/color", json={"sid": CON, "ia": ""})
    revisar("vaciar un color vuelve ese al general",
            cli.get("/charlas/colores").json()["colores"].get(CON) == {"vos": VOS})
    cli.post("/charlas/color", json={"sid": CON, "vos": ""})
    revisar("sin ningún color, la charla sale del archivo",
            CON not in cli.get("/charlas/colores").json()["colores"])
    r = cli.post("/charlas/color", json={"sid": clave(CWD), "tinte": CARPETA_TINTE})
    revisar("guarda los colores de una carpeta",
            cli.get("/charlas/colores").json()["colores"].get(clave(CWD))
            == {"tinte": CARPETA_TINTE}, r.text[:80])
    revisar("la página del celular trae el script",
            '/estaticos/colorcharla.js' in panel.MOVIL_HTML)
    return panel


# --- 2. Las pantallas -----------------------------------------------------------------
def servidor_falso(pag):
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "laura": "", "proyectos": [
            {"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False, "sesiones": [
                {"id": CON, "nombre": "La de colores", "ts": 2, "ultimo": "vos",
                 "viva": False, "interactiva": False, "detalle": ""},
                {"id": SIN, "nombre": "La normal", "ts": 1, "ultimo": "vos",
                 "viva": False, "interactiva": False, "detalle": ""}]},
            {"proyecto": "pruebas", "cwd": OTRA_CWD, "vivo": False, "sesiones": [
                {"id": OTRA, "nombre": "La de otra carpeta", "ts": 0, "ultimo": "vos",
                 "viva": False, "interactiva": False, "detalle": ""}]}]})))
    pag.route("**/movil/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"mensajes": CHARLA, "ocupada": False,
                         "pregunta": None, "tareas": None})))
    pag.route("**/movil/borradores", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/borrador", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true}'))
    pag.route("**/movil/pestanas", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True} if r.request.method == "POST"
                        else {"pestanas": [], "activa": "panel"})))
    pag.route("**/charlas/colores", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"colores": guardados})))

    def poner(ruta):
        d = json.loads(ruta.request.post_data or "{}")
        mandados.append(d)
        ruta.fulfill(status=200, content_type="application/json", body='{"ok": true}')
    pag.route("**/charlas/color", poner)
    # ⚠ Con una fábrica y no con `lambda r, js=js`: Playwright le pasa un segundo
    # argumento al manejador (el pedido) y pisaría el `js` por defecto.
    def del_disco(js):
        return lambda r: r.fulfill(status=200, content_type="application/javascript",
                                   body=(ESTATICOS / js).read_text(encoding="utf-8"))
    for js in ("colorcharla.js", "aspecto.js"):
        pag.route(f"**/estaticos/{js}", del_disco(js))


MIRAR = """() => {
  const c = document.querySelector('#cuerpo');
  const v = c.querySelector('.msg.vos'), ia = c.querySelector('.msg.claude');
  const raiz = getComputedStyle(document.documentElement);
  return {vos: v && getComputedStyle(v).backgroundColor,
          iaBorde: ia && getComputedStyle(ia).borderLeftColor,
          sombra: getComputedStyle(c).boxShadow,
          generalVos: raiz.getPropertyValue('--burbuja-vos').trim(),
          generalIa: raiz.getPropertyValue('--burbuja-ia-borde').trim()};
}"""


def iguales(a, b):
    """Dos colores CSS iguales, sin importar si vienen en hex o en rgb()."""
    a, b = (x.replace(" ", "") for x in (a or "", b or ""))
    if a.startswith("#"):
        a = rgb(a).replace(" ", "")
    if b.startswith("#"):
        b = rgb(b).replace(" ", "")
    return a == b


def tinte_de(m, h):
    return rgb(h).replace(")", "").replace("rgb(", "") in (m["sombra"] or "")


def chequear_pintado(pag, donde, abrir):
    # ⚠ Lo "general" se mide abriendo primero la charla de la otra carpeta, y no leyendo
    # las variables del tema: el celular pinta sus burbujas fijas estilo WhatsApp.
    abrir(OTRA)
    base = pag.evaluate(MIRAR)
    revisar(f"{donde}: la charla de otra carpeta no se entera de nada",
            base["vos"] and not iguales(base["vos"], VOS)
            and not iguales(base["iaBorde"], CARPETA_IA) and base["sombra"] == "none", str(base))
    abrir(CON)
    m = pag.evaluate(MIRAR)
    revisar(f"{donde}: tu burbuja con el color de la charla", iguales(m["vos"], VOS), m["vos"])
    revisar(f"{donde}: la de la sesión con su borde", iguales(m["iaBorde"], IA), m["iaBorde"])
    revisar(f"{donde}: el fondo con el tinte (le gana al de la carpeta)",
            tinte_de(m, TINTE), m["sombra"])
    abrir(SIN)
    m = pag.evaluate(MIRAR)
    revisar(f"{donde}: la de al lado hereda de la carpeta el borde y el tinte",
            iguales(m["iaBorde"], CARPETA_IA) and tinte_de(m, CARPETA_TINTE), str(m))
    revisar(f"{donde}: y lo que la carpeta no eligió sigue con el general",
            m["vos"] == base["vos"], str(m))


def compu(nav):
    print("\n--- la compu (/sesiones) ---")
    pag = nav.new_context(viewport={"width": 1320, "height": 800}).new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag)
    pag.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8",
        body=(ESTATICOS / "sesiones.html").read_text(encoding="utf-8")))
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof mandar === 'function' && datos.proyectos.length"
                          " && window.ColorCharla", timeout=90000)
    pag.wait_for_timeout(1000)

    def abrir(sid):
        pag.evaluate("""(sid) => {
          abiertas = [{sid: sid[0], cwd: sid[1], nombre: 'x', cerebro: ''}];
          pendientes = {}; activa = null; guardar(); irTab(sid[0]); }""", [sid, CWD_DE[sid]])
        pag.wait_for_timeout(900)

    chequear_pintado(pag, "compu", abrir)
    pag.evaluate("() => { activa = null; pintar(); }")
    pag.wait_for_timeout(500)
    revisar("compu: la lista vuelve sin tinte",
            pag.evaluate("() => getComputedStyle(document.querySelector('#cuerpo')).boxShadow")
            == "none")

    abrir(SIN)
    pag.click("#ajustesModeloBoton")
    pag.wait_for_timeout(300)
    revisar("compu: el menú ⚙ tiene el botón de colores", pag.is_visible("#colorCharla"))
    pag.click("#colorCharla")
    pag.wait_for_selector(".cc-cuadro", timeout=3000)
    mandados.clear()
    pag.evaluate("""() => { const i = document.querySelector('.cc-fila[data-k="vos"] input');
      i.value = '#123456'; i.dispatchEvent(new Event('input'));
      i.dispatchEvent(new Event('change')); }""")
    pag.wait_for_timeout(400)
    revisar("compu: elegir un color lo manda al servidor",
            mandados == [{"sid": SIN, "vos": "#123456"}], str(mandados))
    revisar("compu: y se ve al instante en tu burbuja",
            iguales(pag.evaluate(MIRAR)["vos"], "#123456"))
    revisar("compu: el cuadrito dice de dónde sale lo heredado",
            pag.inner_text('.cc-fila[data-k="ia"] small') == "· de la carpeta")
    # ⭐ Ahora para toda la carpeta.
    pag.click('.cc-ambito button[data-a="carpeta"]')
    mandados.clear()
    pag.evaluate("""() => { const i = document.querySelector('.cc-fila[data-k="tinte"] input');
      i.value = '#00897b'; i.dispatchEvent(new Event('input'));
      i.dispatchEvent(new Event('change')); }""")
    pag.wait_for_timeout(400)
    revisar("compu: con 'Toda la carpeta' se guarda en la llave de la carpeta",
            mandados == [{"sid": clave(CWD), "tinte": "#00897b"}], str(mandados))
    revisar("compu: y la charla abierta toma el tinte nuevo de su carpeta",
            tinte_de(pag.evaluate(MIRAR), "#00897b"))
    pag.screenshot(path=str(RAIZ / "pruebas" / "color_charla_compu.png"))
    revisar("compu: sin errores de javascript", not errores, str(errores[:2]))


def celular(nav, panel):
    print("\n--- el celular (/movil) ---")
    ctx = nav.new_context(viewport={"width": 412, "height": 900}, is_mobile=True,
                          has_touch=True)
    pag = ctx.new_page()
    errores = []
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    servidor_falso(pag)
    pag.route("**/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=panel.MOVIL_HTML))
    pag.goto(BASE + "/movil", wait_until="domcontentloaded")
    pag.wait_for_function("() => typeof abrir === 'function' && window.ColorCharla",
                          timeout=30000)
    pag.wait_for_timeout(2500)

    def abrir(sid):
        pag.evaluate("(a) => abrir(a[1], a[0], 'x')", [sid, CWD_DE[sid]])
        pag.wait_for_timeout(1500)

    chequear_pintado(pag, "celular", abrir)
    pag.evaluate("() => ir('panel')")
    pag.wait_for_timeout(600)
    revisar("celular: el inicio vuelve sin tinte",
            pag.evaluate("() => getComputedStyle(document.querySelector('#cuerpo')).boxShadow")
            == "none")
    abrir(SIN)
    boton = pag.locator(".ajusSes button[title^='Elegir los colores']")
    revisar("celular: los ajustes de la sesión tienen el botón 🎨", boton.count() == 1)
    if boton.count():
        boton.first.click()
        pag.wait_for_timeout(300)
        revisar("celular: tocarlo abre el cuadrito", pag.is_visible(".cc-cuadro"))
        revisar("celular: con la opción de toda la carpeta",
                pag.is_visible('.cc-ambito button[data-a="carpeta"]'))
    pag.screenshot(path=str(RAIZ / "pruebas" / "color_charla_movil.png"))
    revisar("celular: sin errores de javascript", not errores, str(errores[:2]))
    ctx.close()


def main():
    panel = servidor()
    guardados.clear()
    guardados[CON] = {"vos": VOS, "ia": IA, "tinte": TINTE}
    guardados[clave(CWD)] = {"ia": CARPETA_IA, "tinte": CARPETA_TINTE}
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        compu(nav)
        celular(nav, panel)
        nav.close()
    print("\n" + ("TODO BIEN" if not fallas else f"FALLAN {len(fallas)}: " + "; ".join(fallas)))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
