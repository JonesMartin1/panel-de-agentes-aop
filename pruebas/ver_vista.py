"""La pestaña "Vista" de la columna derecha, en pantalla (2026-11-16).

Pedido de Martín: *"si una sesión me crea un PDF o me muestra una imagen, me gustaría poder verlo
acá"*. Es la cuarta pestaña de la columna (Entorno, Terminal, Escritorio, Vista).

    python -m pruebas.ver_vista            (con el panel prendido en 8750)
    python -m pruebas.ver_vista --mutar    (rompe cada pieza y exige que se note)
    python -m pruebas.ver_vista --fotos    (deja capturas en pruebas/)

Lo que cuida:
  · la pestaña aparece y muestra la grilla con lo de la charla (la foto se ve de verdad);
  · tocar un PDF lo abre en el visor del navegador, adentro de la columna; ‹ › y Esc andan;
  · el filtro PDF / Fotos;
  · lo que aparece después llega solo y con el aro de "nuevo", sin robar la pantalla;
  · ⭐ escondida NO pide nada (es una pieza que no puede gastar mientras nadie la mira);
  · con el panel sin reiniciar avisa que falta el ⟳ en vez de quedarse en blanco;
  · ELIMINAR: el ⋯ y el botón derecho abren el menú; "Quitar" saca la tarjeta al toque y ofrece
    Deshacer; la papelera pide un SEGUNDO toque y, mirando uno en grande, pasa al de al lado.

⚠ Datos inventados: `sesiones.html`, `aspecto.js`, `menu.js` y `vista.js` se sirven del disco y
`/vista/*` se contesta acá. No toca ninguna charla real.
"""
import io
import json
import sys
from urllib.parse import parse_qs, urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright

from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = vb.BASE
ESTATICOS = vb.ESTATICOS
SALIDA = vb.SALIDA


def png(color):
    b = io.BytesIO()
    Image.new("RGB", (320, 200), color).save(b, "PNG")
    return b.getvalue()


def pdf():
    """Un PDF chiquito pero de verdad (una página con un texto), para que el visor lo dibuje."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    flujo = b"BT /F1 24 Tf 40 100 Td (Informe de prueba) Tj ET"
    salida = b"%PDF-1.4\n"
    pos = []
    for i, o in enumerate(objs, 1):
        pos.append(len(salida))
        cuerpo = (b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream") if o is None else o.encode()
        salida += b"%d 0 obj\n" % i + cuerpo + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in pos)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return salida


ARCH = {"foto1": ("captura.png", "imagen", "abrió", png((70, 130, 200))),
        "doc1": ("informe final.pdf", "pdf", "creó", pdf()),
        "foto2": ("del celular.jpg", "imagen", "tuya", png((200, 120, 60))),
        "foto3": ("después.png", "imagen", "creó", png((60, 180, 90)))}


def fila(ident):
    nom, tipo, como, datos = ARCH[ident]
    return {"id": ident, "nombre": nom, "ruta": "D:\\pruebas\\alfa\\" + nom, "tipo": tipo, "como": como,
            "cuando": "2026-11-16T10:00:00Z", "bytes": len(datos), "ts": 0}


def montar(nav, cambios=None, estado=None):
    """Como `ver_vbandeja.montar`, más `vista.js` del disco y `/vista/*` contestado acá."""
    estado = estado if estado is not None else {}
    estado.setdefault("ids", ["doc1", "foto1", "foto2"])
    estado.setdefault("pedidos", 0)
    estado.setdefault("codigo", 200)
    estado.setdefault("fuera", set())          # lo quitado o mandado a la papelera
    estado.setdefault("acciones", [])          # [(que, id)] de lo que pidió la página
    ctx = nav.new_context(viewport={"width": 1500, "height": 850}, reduced_motion="reduce")
    errores = []

    def portero(r):
        url = r.request.url
        camino = url.split(BASE, 1)[-1].split("?")[0]
        for archivo in ("sesiones.html", "aspecto.js", "menu.js", "vista.js"):
            if camino.endswith("/" + archivo) or (archivo == "sesiones.html" and camino == "/sesiones"):
                cuerpo = (ESTATICOS / archivo).read_text(encoding="utf-8")
                for viejo, nuevo in (cambios or {}).get(archivo, []):
                    assert viejo in cuerpo, "la mutación no encontró: " + viejo
                    cuerpo = cuerpo.replace(viejo, nuevo)
                tipo = "text/html" if archivo.endswith(".html") else "application/javascript"
                return r.fulfill(status=200, content_type=tipo + "; charset=utf-8", body=cuerpo)
        # El resto de los archivos de la página, también del disco: si se los pide al panel real y
        # justo está ocupado (compactando una charla), la página no termina de abrir y la prueba se
        # cae por algo que no es de ella. Pasó dos veces seguidas el 2026-11-16.
        if camino.startswith("/estaticos/"):
            f = (ESTATICOS / camino[len("/estaticos/"):]).resolve()
            if f.is_file() and ESTATICOS.resolve() in f.parents:
                tipo = {".js": "application/javascript", ".css": "text/css"}.get(f.suffix, "application/octet-stream")
                return r.fulfill(status=200, content_type=tipo, body=f.read_bytes())
        if camino == "/vista/lista":
            estado["pedidos"] += 1
            if estado["codigo"] == 404:
                return r.fulfill(status=404, content_type="application/json", body="{}")
            sid = parse_qs(urlsplit(url).query).get("sid", [""])[0]
            ids = [i for i in estado["ids"] if i not in estado["fuera"]] if sid == "alfa-1" else []
            return r.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"ok": True, "archivos": [fila(i) for i in ids]}))
        if camino in ("/vista/quitar", "/vista/devolver", "/vista/papelera"):
            que = camino.rsplit("/", 1)[-1]
            ident = json.loads(r.request.post_data or "{}").get("id", "")
            estado["acciones"].append((que, ident))
            (estado["fuera"].discard if que == "devolver" else estado["fuera"].add)(ident)
            return r.fulfill(status=200, content_type="application/json", body='{"ok": true}')
        if camino == "/vista/crudo":
            ident = parse_qs(urlsplit(url).query).get("id", [""])[0]
            nom, tipo, _, datos = ARCH[ident]
            return r.fulfill(status=200, body=datos,
                             content_type="application/pdf" if tipo == "pdf" else "image/png")
        if camino == "/movil/sesiones":
            cuerpo = vb.SESIONES
        elif camino == "/movil/chat":
            cuerpo = vb.CHAT
        elif camino == "/aspecto" and r.request.method == "GET":
            cuerpo = vb.aspecto("vidrio")
        elif r.request.method != "GET" or camino.startswith(("/movil/", "/carpetas/", "/charlas/",
                                                             "/fijados", "/escritorio/", "/terminal/")):
            cuerpo = {"ok": True}
        else:
            return r.continue_()
        return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    # ⚠ Corre también adentro del visor de PDF, donde no hay localStorage: sin el `&&` ese
    # cuadro tira un error que no es de la página.
    pag.add_init_script("window.localStorage && localStorage.clear()")
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded", timeout=90000)
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=20000)
    pag.evaluate("() => { abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa',"
                 " nombre: 'arreglar el login', cerebro: ''}]; irTab('alfa-1'); }")
    pag.wait_for_timeout(600)
    return ctx, pag, errores, estado


CAJA = "#derecha > .derPane[data-pieza='vista']"


def correr(nav, cambios=None, fotos=False):
    fallas = []

    def chequear(ok, que):
        if not ok:
            fallas.append(que)

    ctx, pag, err, est = montar(nav, cambios)
    tabs = pag.eval_on_selector_all("#derTabs button", "bs => bs.map(b => b.textContent)")
    chequear("Vista" in tabs, "no aparece la pestaña Vista: %s" % tabs)
    if "Vista" not in tabs:
        ctx.close()
        return fallas + (["errores en la página: " + "; ".join(err)] if err else [])

    # Escondida (columna cerrada): no pide nada.
    antes = est["pedidos"]
    pag.wait_for_timeout(4600)
    chequear(est["pedidos"] == antes, "con la columna cerrada pidió la lista %d veces" % (est["pedidos"] - antes))

    pag.evaluate("() => { verDerecha(true); Paneles.mostrar('vista'); }")
    pag.wait_for_selector(CAJA + " .vsTarj", timeout=5000)
    pag.wait_for_timeout(500)
    tarj = pag.eval_on_selector_all(CAJA + " .vsTarj", "ts => ts.map(t => t.dataset.id)")
    chequear(tarj == ["doc1", "foto1", "foto2"], "la grilla no tiene lo de la charla: %s" % tarj)
    cuenta = pag.text_content(CAJA + " .vsCuenta") or ""
    chequear("3 archivos" in cuenta and "1 PDF" in cuenta, "la cuenta dice: %r" % cuenta)
    ancho = pag.evaluate("() => document.getElementById('derecha').getBoundingClientRect().width")
    chequear(ancho >= 400, "la columna no se ensanchó para la Vista (%d px)" % ancho)
    vista_foto = pag.evaluate("() => { const i = document.querySelector(\"" + CAJA +
                              " .vsTarj[data-id=foto1] img\"); return i ? i.naturalWidth : -1; }")
    chequear(vista_foto > 0, "la miniatura de la foto no se dibujó (%s)" % vista_foto)
    chequear(not pag.query_selector(CAJA + " .vsTarj.nuevo"), "la primera vez algo salió marcado como nuevo")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_grilla.png"))

    # Abrir el PDF.
    pag.click(CAJA + " .vsTarj[data-id=doc1]")
    pag.wait_for_timeout(1200)
    marco = pag.query_selector(CAJA + " iframe")
    src = (marco.get_attribute("src") if marco else "") or ""
    chequear("/vista/crudo" in src and "id=doc1" in src, "el PDF no se abrió en el visor: %r" % src)
    chequear("informe final.pdf" in (pag.text_content(CAJA + " .vsTit") or ""), "el título no es el del PDF")
    enl = pag.query_selector(CAJA + " a.vsB")
    aparte = enl.get_attribute("target") if enl else None
    chequear(aparte == "_blank", "«Aparte» no abre en otra pestaña")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_pdf.png"))

    # › va a la foto de al lado, Esc vuelve a la grilla.
    pag.click(CAJA + " button[data-a=sig]")
    pag.wait_for_timeout(300)
    chequear(pag.query_selector(CAJA + " .vsLienzo img") is not None and
             "captura.png" in (pag.text_content(CAJA + " .vsTit") or ""), "› no pasó a la siguiente")
    pag.keyboard.press("ArrowRight")
    pag.wait_for_timeout(200)
    chequear("del celular.jpg" in (pag.text_content(CAJA + " .vsTit") or ""), "la flecha → no pasó a la siguiente")
    chequear(pag.get_attribute(CAJA + " button[data-a=sig]", "disabled") is not None, "› sigue andando en el último")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_foto.png"))
    pag.keyboard.press("Escape")
    pag.wait_for_timeout(200)
    chequear(pag.query_selector(CAJA + " .vsGrilla") is not None, "Esc no volvió a la grilla")

    # Filtro.
    pag.click(CAJA + " button[data-f=pdf]")
    pag.wait_for_timeout(200)
    chequear(pag.eval_on_selector_all(CAJA + " .vsTarj", "ts => ts.length") == 1, "el filtro PDF no filtra")
    pag.click(CAJA + " button[data-f=todo]")

    # Llega uno nuevo: aparece solo, primero y con el aro, sin abrirse.
    est["ids"] = ["foto3", "doc1", "foto1", "foto2"]
    pag.wait_for_timeout(4800)
    tarj = pag.eval_on_selector_all(CAJA + " .vsTarj", "ts => ts.map(t => t.dataset.id)")
    chequear(tarj[:1] == ["foto3"], "lo nuevo no apareció solo arriba: %s" % tarj)
    nuevos = pag.eval_on_selector_all(CAJA + " .vsTarj.nuevo", "ts => ts.map(t => t.dataset.id)")
    chequear(nuevos == ["foto3"], "el aro de nuevo no está (o está de más): %s" % nuevos)
    chequear(pag.query_selector(CAJA + " iframe, " + CAJA + " .vsLienzo") is None, "lo nuevo se abrió solo")

    # --- Eliminar.
    def tocar(sel, **k):
        try:
            pag.click(sel, timeout=2500, **k)
        except Exception:
            fallas.append("no se pudo tocar " + sel)
    def menu_botones():
        return pag.eval_on_selector_all(".vsMenu button", "bs => bs.map(b => b.dataset.m)")
    try:
        pag.hover(CAJA + " .vsTarj[data-id=foto1]", timeout=2500)
    except Exception:
        fallas.append("no está la tarjeta de la foto para abrirle el ⋯")
    tocar(CAJA + " .vsTarj[data-id=foto1] .vsMas")
    pag.wait_for_timeout(200)
    chequear(menu_botones() == ["aparte", "copiar", "quitar", "papelera"], "el ⋯ no abrió el menú: %s" % menu_botones())
    chequear(pag.query_selector(CAJA + " .vsLienzo") is None, "tocar el ⋯ abrió la tarjeta")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_menu.png"))
    tocar(".vsMenu button[data-m=quitar]")
    pag.wait_for_timeout(150)                 # menos que una vuelta: tiene que ser al toque
    tarj = pag.eval_on_selector_all(CAJA + " .vsTarj", "ts => ts.map(t => t.dataset.id)")
    chequear("foto1" not in tarj, "«Quitar» no la sacó al toque: %s" % tarj)
    chequear(("quitar", "foto1") in est["acciones"], "«Quitar» no le avisó al panel: %s" % est["acciones"])
    chequear(pag.query_selector(".vsMenu") is None, "el menú quedó abierto")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_quitada.png"))
    des = pag.query_selector(CAJA + " .vsAviso button[data-a=deshacer]")
    chequear(des is not None, "después de quitar no hay «Deshacer»")
    if des:
        des.click()
        pag.wait_for_timeout(700)
        tarj = pag.eval_on_selector_all(CAJA + " .vsTarj", "ts => ts.map(t => t.dataset.id)")
        chequear("foto1" in tarj and ("devolver", "foto1") in est["acciones"], "«Deshacer» no la devolvió: %s" % tarj)

    # La papelera, mirando uno en grande: primer toque arma, segundo manda, y pasa al de al lado.
    tocar(CAJA + " .vsTarj[data-id=foto1]")
    pag.wait_for_timeout(300)
    tocar(CAJA + " .vsBarra button[data-menu]")
    pag.wait_for_timeout(150)
    tocar(".vsMenu button[data-m=papelera]")
    pag.wait_for_timeout(150)
    armado = pag.evaluate("() => { const b = document.querySelector('.vsMenu button[data-m=papelera]');"
                          " return b ? b.className + '|' + b.textContent : ''; }")
    chequear("armada" in armado and "Seguro" in armado, "el primer toque de la papelera no pide confirmar: %r" % armado)
    chequear(("papelera", "foto1") not in est["acciones"], "la papelera salió con UN solo toque")
    if fotos:
        pag.screenshot(path=str(SALIDA / "vista_papelera_armada.png"))
    tocar(".vsMenu button[data-m=papelera]")
    pag.wait_for_timeout(300)
    chequear(("papelera", "foto1") in est["acciones"], "el segundo toque no mandó a la papelera")
    tit = pag.text_content(CAJA + " .vsTit") if pag.query_selector(CAJA + " .vsTit") else ""
    chequear(tit and "captura.png" not in tit, "después de la papelera no pasó al de al lado: %r" % tit)
    chequear("Papelera" in (pag.evaluate("s => (document.querySelector(s) || {}).textContent || ''", CAJA + " .vsAviso")), "no avisa que fue a la Papelera")
    pag.keyboard.press("Escape")
    pag.wait_for_timeout(200)

    # Botón derecho sobre una tarjeta: el mismo menú; Esc lo cierra.
    tocar(CAJA + " .vsTarj[data-id=doc1]", button="right")
    pag.wait_for_timeout(150)
    chequear(len(menu_botones()) == 4, "el botón derecho no abre el menú")
    pag.keyboard.press("Escape")
    pag.wait_for_timeout(150)
    chequear(pag.query_selector(".vsMenu") is None, "Esc no cerró el menú")
    chequear(pag.query_selector(CAJA + " .vsGrilla") is not None, "Esc con el menú abierto también cerró otra cosa")

    # Otra pestaña de la columna: deja de pedir.
    pag.evaluate("() => Paneles.mostrar('entorno')")
    antes = est["pedidos"]
    pag.wait_for_timeout(4600)
    chequear(est["pedidos"] == antes, "mirando otra pestaña siguió pidiendo (%d)" % (est["pedidos"] - antes))

    # Una charla sin nada.
    pag.evaluate("() => { abiertas.push({sid: 'alfa-6', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'migrar', cerebro: ''});"
                 " irTab('alfa-6'); Paneles.mostrar('vista'); }")
    pag.wait_for_timeout(900)
    nota = pag.text_content(CAJA + " .vsNota") or ""
    chequear("todavía no tiene" in nota, "una charla sin archivos no lo dice: %r" % nota)
    chequear(not err, "errores en la página: " + "; ".join(err))
    ctx.close()

    # Panel sin reiniciar: avisa.
    ctx, pag, err, est = montar(nav, cambios, {"codigo": 404})
    pag.evaluate("() => { verDerecha(true); Paneles.mostrar('vista'); }")
    try:      # se espera la respuesta, no un tiempo fijo: con el panel ocupado 0,9 s no alcanzaba
        pag.wait_for_function("s => { const n = document.querySelector(s); return n && !/Buscando/.test(n.textContent); }",
                              arg=CAJA + " .vsNota", timeout=8000)
    except Exception:
        pass
    nota = pag.text_content(CAJA + " .vsNota") or ""
    chequear("reiniciar" in nota, "con el panel viejo no avisa: %r" % nota)
    ctx.close()
    return fallas


MUTACIONES = {
    "papelera de un solo toque": {"vista.js": [("if (armada === id) return accion('papelera', id);",
                                                 "return accion('papelera', id);")]},
    "quitar sin deshacer": {"vista.js": [("(aviso.deshacer ? '<button data-a=\"deshacer\">Deshacer</button>' : '')", "''")]},
    "el ⋯ abre la tarjeta": {"vista.js": [("      e.stopPropagation();\n      const r = m.getBoundingClientRect();",
                                           "      return abrir(m.dataset.menu);\n      const r = m.getBoundingClientRect();")]},
    "la pestaña no se registra": {"sesiones.html": [("Paneles.registrar({id: 'vista'", "({id: 'vista'")]},
    "no vuelve a pedir": {"vista.js": [("reloj = setInterval(pedir, 4000);", "")]},
    "sigue pidiendo escondida": {"vista.js": [("    visible = false;\n    cerrarMenu();\n    clearInterval(reloj);",
                                               "    visible = true;")]},
    "el PDF como imagen": {"vista.js": [("(sel.tipo === 'pdf'\n", "(false\n")]},
    "sin aro de nuevo": {"vista.js": [("(vi.has(a.id) ? '' : ' nuevo')", "''")]},
    "lo nuevo se abre solo": {"vista.js": [("archivos = d.archivos || [];",
                                           "archivos = d.archivos || []; if (vistos[sid] && archivos[0] && !vistos[sid].has(archivos[0].id)) abierto = archivos[0].id;")]},
}


if __name__ == "__main__":
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav, fotos="--fotos" in sys.argv)
        print("vista en pantalla:", "TODO BIEN" if not fallas else "FALLAS")
        for f in fallas:
            print("  ✗", f)
        bien = not fallas
        if "--mutar" in sys.argv:
            for nombre, cambios in MUTACIONES.items():
                f = correr(nav, cambios)
                print(f"  mutación «{nombre}»: {'CAZADA (' + f[0] + ')' if f else 'NO SE NOTÓ ✗'}")
                bien = bien and bool(f)
        nav.close()
    sys.exit(0 if bien else 1)
