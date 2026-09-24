"""La perilla del navegador de cada carpeta, en las DOS pantallas.

Pedido de Martin (2026-08-28): que una sesion del panel pueda probar una web como hace
Codex. Cada carpeta declara CON QUE perfil de Chrome trabajan sus conversaciones, y ese
campo es el interruptor: sin perfil, esa carpeta no abre paginas. No hay perilla por
conversacion, igual que en Codex.

Recorre, con las dos pantallas de verdad y el backend de verdad (las funciones de
`panel.py`):

  1. en `/sesiones`, el menu de la carpeta ofrece los perfiles del disco y avisa cual es
     el Chrome personal (el que tiene todas sus cuentas);
  2. elegir uno sube SOLO ese campo y le pone la marca a la carpeta en la lista;
  3. los sitios permitidos se guardan y se leen normalizados;
  4. en el celular se ve lo mismo, sobre el mismo dato;
  5. ⚠⚠ un panel VIEJO (404, porque todavia no se reinicio) NO se traga en silencio:
     la pantalla lo dice. Es la trampa que casi cuesta los iconos el 2026-08-25 —
     un 404 no le hace saltar el `catch` a `fetch`.

⚠ NO toca `aspecto_carpetas.json` de verdad: la ruta se apunta a un temporal antes de
empezar. Tampoco hace falta el panel prendido, ni se abre ningun Chrome.

    python -m pruebas.ver_navegador_carpeta
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import panel                                              # noqa: E402

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
PROYECTOS = ["alfa", "beta"]
fallas = []

# ⚠ Los perfiles tienen que EXISTIR en el disco: el backend de verdad rechaza una ruta
# que no parezca un perfil de Chrome, y con rutas inventadas esta prueba estaria midiendo
# el rechazo en vez de la perilla. Se arman dos de mentira en el temporal, con el
# `Local State` que Chrome deja la primera vez. No se abre ninguno.
PERFILES = []


def armar_perfiles(tmp):
    for nombre, personal in (("Personal", True), ("chrome-alfa", False)):
        d = tmp / nombre
        d.mkdir(parents=True, exist_ok=True)
        (d / "Local State").write_text("{}", encoding="utf-8")
        PERFILES.append({"ruta": str(d), "personal": personal,
                         "nombre": "El Chrome de siempre" if personal else "chrome-alfa"})


def revisar(nombre, obtenido, esperado):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def movil_html():
    """El HTML del celular, del `panel.py` DEL DISCO (no del panel corriendo)."""
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontre MOVIL_HTML en panel.py")


def sesiones_json():
    e = panel._aspecto_carpetas()
    return {"ok": True, "laura": "",
            "carpetas": {"orden": [], "ocultas": [],
                         "aspecto": e["carpetas"], "iconosPropios": e["iconosPropios"]},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False,
                           "sesiones": [{"id": n + "-1", "nombre": "charla de " + n,
                                         "ts": 1, "ultimo": "vos", "viva": False,
                                         "interactiva": False, "detalle": ""}]}
                          for n in PROYECTOS]}


def montar(pag, movil, perfiles_404=False, guardar_404=False):
    """El backend de verdad, y todo lo demas cortado antes de salir a la red."""
    pag.route("**/*", lambda r: r.fulfill(status=200,
                                          content_type="application/json", body="{}"))
    pag.route("**/estaticos/*", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(ESTATICOS / r.request.url.rsplit("/", 1)[1]).read_text(encoding="utf-8")))
    pag.route("**/sesiones*", lambda r: r.fulfill(
        status=200, content_type="text/html",
        body=(ESTATICOS / "sesiones.html").read_text(encoding="utf-8")))
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                              body=movil))
    pag.route("**/movil/sesiones*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(sesiones_json())))
    # Lo que el celular pide al arrancar. Sin esto no llega a dibujar ni el ☰.
    fijo = lambda cuerpo: (lambda r: r.fulfill(                        # noqa: E731
        status=200, content_type="application/json", body=json.dumps(cuerpo)))
    pag.route("**/movil/pestanas*", fijo({"pestanas": [], "activa": "nueva"}))
    pag.route("**/movil/borradores*", fijo({}))
    pag.route("**/movil/donde*", fijo({"ok": True}))
    pag.route("**/status*", fijo({"servicios": {}, "encendido": False}))
    pag.route("**/carpetas/aspecto/sembrar", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok":true}'))
    # ⭐ El guardado es el de verdad: `_aspecto_aplicar` de `panel.py`.
    pag.route("**/carpetas/aspecto", lambda r: (
        r.fulfill(status=404, body="Not Found") if guardar_404 else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps(panel._aspecto_aplicar(r.request.post_data_json or {})))))
    pag.route("**/carpetas/navegadores*", lambda r: (
        r.fulfill(status=404, body="Not Found") if perfiles_404 else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "perfiles": PERFILES}))))


def abrir(nav, movil_txt, celular=False, **kw):
    # ⚠ `has_touch` no es decorativo: sin eso Playwright no sabe tocar y la app del
    # celular se maneja a dedo.
    pag = nav.new_page(viewport={"width": 430, "height": 900}, has_touch=True,
                       is_mobile=True) if celular else nav.new_page(
        viewport={"width": 1400, "height": 900})
    montar(pag, movil_txt, **kw)
    # ⚠ `activa` = 'nueva' es lo que hace que el celular arranque en una vista con el ☰;
    # sin eso se queda esperando una charla que no existe y no dibuja el cajon.
    pag.add_init_script("localStorage.clear();"
                        "localStorage.setItem('activa','nueva');"
                        "localStorage.setItem('sesAspectoSembrado2','1');"
                        "localStorage.setItem('movilAspectoSembrado2','1')")
    pag.goto(BASE + ("/movil" if celular else "/sesiones"),
             wait_until="domcontentloaded")
    return pag


def main():
    tmp = Path(tempfile.mkdtemp(prefix="naveg_carp_"))
    panel.ASPECTO_CARPETAS = tmp / "aspecto_carpetas.json"
    armar_perfiles(tmp)
    ALFA = PERFILES[1]["ruta"]
    movil_txt = movil_html()
    print(f"\nArchivo de mentira: {panel.ASPECTO_CARPETAS}\n")

    with sync_playwright() as p:
        nav = p.chromium.launch()

        # --- 1 y 2. La compu: elegir el navegador de una carpeta ---------------------
        print("--- 1. El menu de la carpeta, en la compu ---")
        pag = abrir(nav, movil_txt)
        pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=8000)
        pag.click("#carpetas .carpeta[data-proy='alfa']", button="right")
        pag.wait_for_selector("#menuTarjeta.abierto #carpNaveg", timeout=5000)
        pag.wait_for_timeout(400)
        opciones = pag.eval_on_selector_all(
            "#carpNaveg option", "os => os.map(o => o.textContent)")
        revisar("ofrece los perfiles del disco, con el personal marcado", opciones,
                ["Sin navegador", "El Chrome de siempre (todas tus cuentas)",
                 "chrome-alfa"])
        revisar("sin navegador, avisa que esa carpeta no abre paginas",
                "no abren páginas" in pag.text_content("#carpNavegAviso"), True)

        print("\n--- 2. Elegir uno ---")
        pag.select_option("#carpNaveg", ALFA)
        pag.wait_for_timeout(600)
        e = panel._aspecto_carpetas()
        revisar("el perfil se guardo en el servidor",
                (e["carpetas"].get("alfa") or {}).get("navegador"), ALFA)
        revisar("y NO se toco ninguna otra carpeta", "beta" in e["carpetas"], False)
        revisar("el aviso deja de hablar de paginas cerradas",
                "no abren páginas" in pag.text_content("#carpNavegAviso"), False)
        revisar("la carpeta queda marcada en la lista",
                pag.locator("#carpetas .carpeta[data-proy='alfa'] .naveg").count(), 1)
        revisar("y la otra carpeta NO",
                pag.locator("#carpetas .carpeta[data-proy='beta'] .naveg").count(), 0)

        print("\n--- 3. Los sitios permitidos ---")
        pag.click("#carpetas .carpeta[data-proy='alfa']", button="right")
        pag.wait_for_selector("#menuTarjeta.abierto #carpSitios", timeout=5000)
        pag.fill("#carpSitios", "  https://Ejemplo.web.app/ , LOCALHOST ")
        pag.eval_on_selector("#carpSitios", "el => el.blur()")
        pag.wait_for_timeout(600)
        e = panel._aspecto_carpetas()
        revisar("los sitios se guardan normalizados",
                (e["carpetas"].get("alfa") or {}).get("sitios"),
                "ejemplo.web.app, localhost")
        revisar("y el perfil sigue puesto (se manda SOLO el campo tocado)",
                (e["carpetas"].get("alfa") or {}).get("navegador"), ALFA)

        # --- 4. El celular, sobre el mismo dato --------------------------------------
        print("\n--- 4. El mismo dato en el celular ---")
        cel = abrir(nav, movil_txt, celular=True)
        cel.wait_for_selector(".menu", timeout=8000)
        cel.tap(".menu")                       # ☰: el cajon de proyectos
        cel.wait_for_selector("#cajon .carpeta[data-proy]", timeout=8000)
        cel.wait_for_timeout(400)
        cel.tap(".carpeta[data-proy='alfa'] .editar-carp")
        cel.wait_for_selector("#editorCarp.abierto .naveg-edit", timeout=5000)
        cel.wait_for_timeout(500)
        revisar("el celular muestra el perfil que se eligio en la compu",
                cel.input_value("#editorCarp .naveg-edit"), ALFA)
        revisar("y sus sitios permitidos",
                cel.input_value("#editorCarp .naveg-sitios"),
                "ejemplo.web.app, localhost")
        cel.select_option("#editorCarp .naveg-edit", "")
        cel.wait_for_timeout(700)
        revisar("sacarle el navegador desde el celular tambien manda",
                (panel._aspecto_carpetas()["carpetas"].get("alfa") or {}).get("navegador"),
                None)
        revisar("pero no le borra los sitios que ya tenia",
                (panel._aspecto_carpetas()["carpetas"].get("alfa") or {}).get("sitios"),
                "ejemplo.web.app, localhost")

        # --- 5. El panel viejo, que contesta 404 -------------------------------------
        print("\n--- 5. Con el panel todavia sin reiniciar (404) ---")
        vieja = abrir(nav, movil_txt, guardar_404=True)
        vieja.wait_for_selector("#carpetas .carpeta[data-proy='beta']", timeout=8000)
        vieja.click("#carpetas .carpeta[data-proy='beta']", button="right")
        vieja.wait_for_selector("#menuTarjeta.abierto #carpNaveg", timeout=5000)
        vieja.wait_for_timeout(400)
        vieja.select_option("#carpNaveg", ALFA)
        vieja.wait_for_timeout(700)
        revisar("con 404 NO se hace el sota: lo dice en pantalla",
                "No se guardó" in vieja.text_content("#carpNavegAviso"), True)
        revisar("y no se invento un guardado que nunca paso",
                "beta" in panel._aspecto_carpetas()["carpetas"], False)

        # --- 6. Sin la lista de perfiles ---------------------------------------------
        print("\n--- 6. Si no se puede leer la lista de perfiles ---")
        sinlista = abrir(nav, movil_txt, perfiles_404=True)
        sinlista.wait_for_selector("#carpetas .carpeta[data-proy='beta']", timeout=8000)
        sinlista.click("#carpetas .carpeta[data-proy='beta']", button="right")
        sinlista.wait_for_selector("#menuTarjeta.abierto #carpNaveg", timeout=5000)
        sinlista.wait_for_timeout(400)
        revisar("el selector queda con 'Sin navegador' y nada mas",
                sinlista.eval_on_selector_all("#carpNaveg option",
                                              "os => os.map(o => o.textContent)"),
                ["Sin navegador"])

        nav.close()

    revisar("el archivo de verdad de Martin no se tocó",
            str(panel.ASPECTO_CARPETAS).startswith(str(tmp)), True)
    print("\n" + ("TODO BIEN" if not fallas
                  else "FALLARON %d: %s" % (len(fallas), ", ".join(fallas))) + "\n")
    return 0 if not fallas else 1


if __name__ == "__main__":
    raise SystemExit(main())
