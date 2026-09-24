"""Devolver una archivada tiene que valer en TODAS las pantallas, no solo en la que tocaste.

Bug que trajo Martin el 2026-08-27: *"no me deja mandar a mi pestana principal las
sesiones archivadas"*, y en las dos pantallas.

La causa: cada navegador se guardaba su PROPIO Set de ids archivados en `localStorage`
(`sesArchivadas`) y la pantalla lo mezclaba con el flag del servidor:

    archivadas.has(s.id) || s.archivada          <- el defecto

Ese Set solo se vaciaba en el navegador donde apretabas Devolver. Devolvias desde el
celular: el servidor la sacaba de `sesiones_archivadas.json` y en el celular volvia, pero
la compu seguia teniendola en SU copia y ahi quedaba archivada PARA SIEMPRE — el Devolver
de la compu ya no la mostraba (para el servidor no estaba archivada) y no habia ningun
boton capaz de rescatarla. Es el mismo defecto que tenian los iconos de carpeta antes de
`aspecto_carpetas.json`: identidad guardada por navegador = cada pantalla con su verdad.

El arreglo: manda el servidor. Lo local pasa a ser SOLO el cambio en vuelo (`archPend`),
y se borra apenas el servidor lo confirma.

Que se prueba, con DOS navegadores de verdad (dos contextos = dos `localStorage`
separados, que es exactamente lo que el bug necesitaba para aparecer):
  1. Archivo en el celular -> desaparece de la bandeja del celular.
  2. La compu, recien abierta, la ve archivada (el servidor mando el dato).
  3. Devuelvo desde la compu -> vuelve a la bandeja de la compu.
  4. ⭐ El CELULAR, al refrescar, la tiene de vuelta en la bandeja.   <- el bug
  5. Y al reves: archivo en la compu, devuelvo en el celular, la compu la recupera.
  6. Sin senal (el POST falla), archivar igual esconde la fila y aguanta un refresco:
     el pendiente no se pierde por no tener servidor.
  7. Ningun error de JS en ninguna de las dos pantallas.

⚠ No necesita el panel prendido ni toca ninguna conversacion de verdad: las dos paginas
se leen del disco y el servidor esta inventado aca adentro (por eso ve el codigo recien
escrito y no el que el panel tiene en memoria).

⭐ Con `--viejo` se sirven las paginas con el defecto puesto de vuelta (dos reemplazos de
texto) y se exige que los pasos 4 y 5 FALLEN. Una prueba que no puede cazar la version
anterior no prueba nada.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_devolver_archivada
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_devolver_archivada --viejo
"""
import ast
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
VIEJO = "--viejo" in sys.argv

A = "aaaaaaaa-1111-1111-1111-111111111111"   # la que se archiva desde el celular
B = "bbbbbbbb-2222-2222-2222-222222222222"   # la que se archiva desde la compu
C = "cccccccc-3333-3333-3333-333333333333"   # la de la prueba sin senal

# La unica fuente de verdad, igual que `sesiones_archivadas.json` en el panel de verdad.
SERVIDOR = {"archivadas": set(), "caido": False}

fallas = []
esperadas = []      # las que con --viejo TIENEN que fallar


def revisar(que, ok, detalle="", cazadora=False):
    """`cazadora` marca los chequeos que existen para cazar el bug: son los que con
    --viejo tienen que dar MAL. Si con --viejo salen bien, la prueba es decoracion."""
    print(("ok   " if ok else "MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)
    if cazadora:
        esperadas.append((que, ok))


# --- Las dos paginas, leidas del disco -------------------------------------------

def _con_el_defecto(texto):
    """Devuelve el codigo a como estaba antes del arreglo, con dos reemplazos.

    (a) el pendiente se OR-ea con el flag del servidor en vez de pisarlo, y
    (b) nunca se suelta cuando el servidor confirma.
    Juntos son, exactamente, el Set pegajoso por navegador que tenia el bug.
    """
    nuevo = "const esArchivada = s => (s.id in archPend) ? archPend[s.id] : !!s.archivada;"
    viejo = "const esArchivada = s => archPend[s.id] === true || !!s.archivada;"
    suelta = "  if (ok && archPend[sid] === si){ delete archPend[sid]; guardarArchPend(); }"
    for aguja in (nuevo, suelta):
        if aguja not in texto:
            raise SystemExit(f"No encontre para mutar:\n  {aguja}")
    return texto.replace(nuevo, viejo).replace(suelta, "  /* el viejo nunca lo soltaba */")


def html_movil():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == "MOVIL_HTML"):
            t = ast.literal_eval(nodo.value)
            return _con_el_defecto(t) if VIEJO else t
    raise SystemExit("No encontre MOVIL_HTML en panel.py")


def html_sesiones():
    t = (ESTATICOS / "sesiones.html").read_text(encoding="utf-8")
    return _con_el_defecto(t) if VIEJO else t


# --- El servidor inventado --------------------------------------------------------

def _sesion(sid, nombre):
    s = {"id": sid, "nombre": nombre, "ts": time.time() - 300, "cuando": time.time() - 300,
         "ultimo": "claude", "viva": False, "interactiva": False, "ocupada": False,
         "detalle": "hace un rato", "cerebro": ""}
    # ⚠ El flag se calcula EN CADA pedido, como lo hace `/movil/sesiones`: si se
    # precalculara, la prueba no veria el efecto de archivar.
    if sid in SERVIDOR["archivadas"]:
        s["archivada"] = True
    return s


def cablear(pag, errores):
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())

    # Catch-all primero: en Playwright gana la ruta registrada DESPUES, asi que este
    # queda de red y las especificas de abajo lo tapan.
    pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                          body="{}") if "/" in r.request.url else r.abort())

    def bandeja(r):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "laura": "", "carpetas": {"orden": [], "ocultas": [],
                                                   "aspecto": {}, "iconosPropios": []},
             "proyectos": [{"proyecto": "wpp", "cwd": str(RAIZ), "vivo": False,
                            "sesiones": [_sesion(A, "Vigia del VPS"),
                                         _sesion(B, "Bot de Kommo"),
                                         _sesion(C, "Estudio de audios")]}]}))
    pag.route("**/movil/sesiones*", bandeja)

    def archivar(r):
        if SERVIDOR["caido"]:
            return r.abort()
        d = json.loads(r.request.post_data or "{}")
        sid, si = d.get("sid"), d.get("archivar", True)
        SERVIDOR["archivadas"].add(sid) if si else SERVIDOR["archivadas"].discard(sid)
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "archivadas": len(SERVIDOR["archivadas"])}))
    pag.route("**/movil/archivar", archivar)

    pag.route("**/movil/borradores*", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/movil/novedad*", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    pag.route("**/carpetas/aspecto*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"ok": true, "carpetas": {}, "iconosPropios": [], "choques": []}'))
    pag.route("**/skills*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"cerebro": "claude", "prompts": [], "carpeta": ""}'))
    # ⚠ El inicio del celular pinta antes de que la prueba lo mande a la lista, y
    # `pintarPanel()` hace `Object.values(e.servicios)`. Con el `{}` del catch-all
    # reventaba y ensuciaba el chequeo de "sin errores de JS" con un error que era de
    # la prueba, no del panel.
    pag.route("**/status*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"servicios": {}, "encendido": false, "pausado": false}'))
    pag.route("**/chat*", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"items": []}'))

    def estatico(r):
        arch = ESTATICOS / Path(r.request.url.split("?")[0]).name
        r.fulfill(status=200, content_type="application/javascript",
                  body=arch.read_text(encoding="utf-8")) if arch.exists() else r.fulfill(
                      status=404, body="")
    pag.route("**/estaticos/*", estatico)
    pag.route("**/*.js", estatico)


# --- Lo que se le pregunta a cada pantalla ----------------------------------------
#
# ⚠ Se pregunta por el SID, nunca por "cuantas filas hay": la bandeja de la maquina de
# Martin se mueve sola y un conteo absoluto falla sin que nada este roto (leccion vieja
# de ver_archivar_sesiones.py).

# ⚠ `typeof`, no `listaSes || datos`: cada pantalla tiene UNA sola de las dos variables y
# nombrar la que no existe tira ReferenceError en vez de dar undefined.
EN_BANDEJA = """(sid) => {
  const d = (typeof listaSes !== 'undefined') ? listaSes : datos;
  const s = d.proyectos.flatMap(p => p.sesiones).find(x => x.id === sid);
  return s ? !esArchivada(s) : null;
}"""


def en_bandeja(pag, sid):
    """¿Esa charla esta en la bandeja principal (o sea, NO archivada) para esta pantalla?"""
    return pag.evaluate(EN_BANDEJA, sid)


def refrescar_celu(pag):
    pag.evaluate("async () => { await traerSesiones(); elegirFirma = ''; await pintar(); }")
    pag.wait_for_timeout(250)


def refrescar_compu(pag):
    pag.evaluate("async () => { firma = ''; await cargar(); }")
    pag.wait_for_timeout(250)


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    errores = []

    # El telefono y la computadora: DOS contextos, o sea dos localStorage distintos.
    # Con uno solo el bug es invisible, porque el Set pegajoso lo comparten.
    ctx_celu = nav.new_context(viewport={"width": 390, "height": 844},
                               device_scale_factor=3, is_mobile=True, has_touch=True)
    ctx_compu = nav.new_context(viewport={"width": 1600, "height": 950})

    celu, compu = ctx_celu.new_page(), ctx_compu.new_page()
    cablear(celu, errores)
    cablear(compu, errores)

    cuerpo_movil, cuerpo_ses = html_movil(), html_sesiones()
    celu.route(BASE + "/movil", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=cuerpo_movil))
    compu.route(BASE + "/sesiones", lambda r: r.fulfill(
        status=200, content_type="text/html; charset=utf-8", body=cuerpo_ses))

    celu.goto(BASE + "/movil", wait_until="domcontentloaded")
    celu.wait_for_function("() => typeof archivarSesion === 'function'", timeout=60000)
    celu.evaluate("async () => { activa = 'nueva'; await pintar(); }")
    celu.wait_for_timeout(400)

    compu.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    compu.wait_for_function("() => typeof archivar === 'function'", timeout=60000)
    compu.wait_for_timeout(400)
    refrescar_compu(compu)

    print(f"\n--- Ida: archivo en el CELULAR, devuelvo en la COMPU{'  [con el defecto puesto]' if VIEJO else ''}")
    revisar("arranca en la bandeja de las dos",
            en_bandeja(celu, A) is True and en_bandeja(compu, A) is True,
            f"celu={en_bandeja(celu, A)} compu={en_bandeja(compu, A)}")

    celu.evaluate("sid => archivarSesion(sid, true)", A)
    celu.wait_for_timeout(700)
    revisar("1. archivada desde el celular, se va de su bandeja",
            en_bandeja(celu, A) is False)
    revisar("   y el servidor se entero", A in SERVIDOR["archivadas"],
            str(sorted(x[:8] for x in SERVIDOR["archivadas"])))

    refrescar_compu(compu)
    revisar("2. la compu la ve archivada sin que nadie se lo diga ahi",
            en_bandeja(compu, A) is False)

    compu.evaluate("sid => archivar(sid, false)", A)
    compu.wait_for_timeout(700)
    revisar("3. Devolver desde la compu la trae de vuelta ahi",
            en_bandeja(compu, A) is True)
    revisar("   y el servidor la solto", A not in SERVIDOR["archivadas"],
            str(sorted(x[:8] for x in SERVIDOR["archivadas"])))

    refrescar_celu(celu)
    revisar("4. ** y el CELULAR la recupera al refrescar",
            en_bandeja(celu, A) is True, cazadora=True)

    print("\n--- Vuelta: archivo en la COMPU, devuelvo en el CELULAR")
    compu.evaluate("sid => archivar(sid, true)", B)
    compu.wait_for_timeout(700)
    revisar("5. archivada desde la compu, se va de su bandeja",
            en_bandeja(compu, B) is False)

    refrescar_celu(celu)
    revisar("   el celular la ve archivada", en_bandeja(celu, B) is False)

    celu.evaluate("sid => archivarSesion(sid, false)", B)
    celu.wait_for_timeout(700)
    revisar("6. Devolver desde el celular la trae de vuelta ahi",
            en_bandeja(celu, B) is True)

    refrescar_compu(compu)
    revisar("7. ** y la COMPU la recupera al refrescar",
            en_bandeja(compu, B) is True, cazadora=True)

    print("\n--- Sin senal: el cambio no se pierde")
    SERVIDOR["caido"] = True
    celu.evaluate("sid => archivarSesion(sid, true)", C)
    celu.wait_for_timeout(900)
    revisar("8. archivar sin servidor igual esconde la fila",
            en_bandeja(celu, C) is False)
    revisar("   el servidor NO se entero (estaba caido)", C not in SERVIDOR["archivadas"])
    refrescar_celu(celu)
    revisar("9. y aguanta un refresco: el pendiente no se perdio",
            en_bandeja(celu, C) is False)
    SERVIDOR["caido"] = False

    revisar("10. sin errores de JS en ninguna pantalla", errores == [], str(errores[:3]))
    nav.close()

print()
if VIEJO:
    # Con el defecto puesto, los dos chequeos cazadores TIENEN que fallar.
    vivas = [q for q, ok in esperadas if ok]
    if vivas:
        print("La prueba NO sirve: con el defecto puesto igual dio bien -> " + "; ".join(vivas))
        raise SystemExit(1)
    print("BIEN: con el defecto puesto, la prueba lo caza "
          f"({len(esperadas)} chequeos cazadores en rojo, como tiene que ser).")
    raise SystemExit(0)

print("TODO BIEN" if not fallas else "Fallo: " + ", ".join(fallas))
if fallas:
    raise SystemExit(1)
