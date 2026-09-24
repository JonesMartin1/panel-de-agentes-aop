"""El tema claro: que se vea, y que el oscuro quede EXACTAMENTE como estaba.

Pedido de Martin el 2026-08-29 ("me gustaria poder cambiar mas caracteristicas" -> eligio
modo claro y efectos). Lo que esta prueba comprueba:

  1. En modo OSCURO no se define ninguna tinta: cada `var(--cRRGGBB,#rrggbb)` cae en su
     respaldo, que es el color de siempre. Es lo que sostiene que el cambio no le toco la
     pantalla a nadie (aparte, `foto_pantallas.py` lo verifica pixel a pixel).
  2. En modo CLARO el fondo se aclara de verdad y las tintas se dan vuelta.
  3. ⭐ **Nada queda ilegible.** Se recorre CADA texto de la pantalla, se calcula el
     contraste real contra el fondo que tiene detras (norma WCAG) y se compara con el
     mismo texto en modo oscuro. Se reporta lo que en claro queda por debajo del minimo
     legible Y que en oscuro estaba bien: asi lo que ya era flojo antes no se cuenta como
     un defecto del tema claro (seria perseguir fantasmas ajenos).
  4. El semaforo sigue distinguiendose: verde, rojo y ambar tienen que seguir siendo
     tres colores distintos y legibles, o el aviso deja de avisar.

⚠ No necesita el panel prendido: las paginas se leen del disco.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_modo_claro
"""
import ast
import json
import sys

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8750"
ESTATICOS = RAIZ / "app" / "estaticos"
# 4.5 es el minimo de la norma para texto chico, que es casi todo lo que hay en estas
# pantallas. Se probo primero con 3.0 (el de texto grande) y tambien pasaba: subirlo no
# costo ningun arreglo, asi que queda la vara alta.
MINIMO = 4.5

fallas = []


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


def constante(nombre, fuente):
    for nodo in ast.parse(fuente).body:
        if (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
                and getattr(nodo.targets[0], "id", "") == nombre):
            return ast.literal_eval(nodo.value)
    raise SystemExit(f"No encontre {nombre} en panel.py")


def paginas():
    panel_py = (RAIZ / "panel.py").read_text(encoding="utf-8")
    return {"panel": constante("PAGINA", panel_py),
            "celular": constante("MOVIL_HTML", panel_py),
            "pizarra": constante("PAGINA_PIZARRA", panel_py),
            "sesiones": (ESTATICOS / "sesiones.html").read_text(encoding="utf-8")}


def montar(pag, html, aspecto):
    pag.route(f"{BASE}/**", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "items": [], "proyectos": [], "mensajes": [],
                         "servicios": {}})))
    pag.route(BASE + "/", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    pag.route("**/pizarra/rough.js", lambda r: r.fulfill(status=200, body=""))
    pag.route("**/fondo/**", lambda r: r.fulfill(status=200, body=""))
    for est in ("menu.js", "marcado.js", "atajos.js", "marcas.js", "direccion.js"):
        pag.route(f"**/estaticos/{est}", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=""))
    pag.route("**/estaticos/aspecto.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript",
        body=(ESTATICOS / "aspecto.js").read_text(encoding="utf-8")))
    pag.route("**/aspecto", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(aspecto))
        if r.request.method == "GET" else
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "aspecto": aspecto})))
    pag.goto(BASE + "/", wait_until="domcontentloaded")
    pag.wait_for_timeout(420)


ASPECTO = {"tipo": "segoe", "color": "celeste", "img": "", "letra": "normal",
           "velo": "media", "rastro": "tema"}

# El contraste de cada texto contra lo que tiene atras. Devuelve una lista de
# {marca, ratio}: la marca identifica al elemento para poder cruzar las dos corridas.
CONTRASTES = """
() => {
  const lin = c => { c /= 255; return c <= .03928 ? c/12.92 : Math.pow((c+.055)/1.055, 2.4); };
  const luz = ([r,g,b]) => .2126*lin(r) + .7152*lin(g) + .0722*lin(b);
  const nums = s => (s.match(/[\\d.]+/g) || []).map(Number);
  // El fondo de verdad: se sube por los padres hasta encontrar uno que tape.
  function fondoDe(el){
    let n = el, capas = [];
    while (n && n !== document.documentElement) {
      const c = nums(getComputedStyle(n).backgroundColor);
      if (c.length >= 3 && (c[3] === undefined || c[3] > .04)) {
        capas.push(c);
        if (c[3] === undefined || c[3] >= .98) break;
      }
      n = n.parentElement;
    }
    const base = nums(getComputedStyle(document.body).backgroundColor);
    let f = (base.length >= 3 && (base[3] === undefined || base[3] > .9))
            ? base.slice(0,3) : [255,255,255];
    for (let i = capas.length - 1; i >= 0; i--) {
      const a = capas[i][3] === undefined ? 1 : capas[i][3];
      f = [0,1,2].map(k => capas[i][k]*a + f[k]*(1-a));
    }
    return f;
  }
  const salida = [];
  document.querySelectorAll('*').forEach(el => {
    // Solo lo que tiene texto propio y se ve.
    const txt = [...el.childNodes].filter(n => n.nodeType === 3)
                 .map(n => n.textContent.trim()).join(' ').trim();
    if (!txt || txt.length > 60) return;
    // ⚠ Un emoji a color (🎨, 🖼) se dibuja con SU paleta, no con el `color` del CSS:
    // medirle el contraste da un numero que no significa nada. Se saltea solo si el
    // texto es todo emoji pictografico; un simbolo monocromo como ➤ SI se mide, porque
    // ese se pinta con el color del CSS y puede quedar invisible de verdad.
    if (![...txt.replace(/\\s/g,'')].some(ch => ch.codePointAt(0) < 0x1F000)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > 4000) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < .15) return;
    const c = nums(cs.color);
    if (c.length < 3) return;
    const alfa = c[3] === undefined ? 1 : c[3];
    const f = fondoDe(el);
    const tinta = [0,1,2].map(k => c[k]*alfa + f[k]*(1-alfa));
    const a = luz(tinta), b = luz(f);
    const ratio = (Math.max(a,b) + .05) / (Math.min(a,b) + .05);
    salida.push({marca: el.tagName + '#' + (el.id||'') + '.' + (el.className||'')
                          + '|' + txt.slice(0,28),
                 txt: txt.slice(0,28), ratio: Math.round(ratio*100)/100,
                 // para poder arreglarlo hay que saber QUE color quedo sobre cual
                 tinta: cs.color, fondo: 'rgb(' + f.map(Math.round).join(',') + ')'});
  });
  return salida;
}
"""


def main():
    print("=== el tema claro")
    pags = paginas()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1280, "height": 900})

        # 1. En oscuro no se define ninguna tinta: manda el respaldo.
        montar(pag, pags["panel"], dict(ASPECTO, fondo="azulado"))
        sin_definir = pag.evaluate(
            "() => getComputedStyle(document.documentElement)"
            ".getPropertyValue('--c232a35').trim()")
        revisar("en oscuro las tintas NO se definen (manda el respaldo)",
                sin_definir == "", repr(sin_definir))
        revisar("en oscuro el <html> no tiene la clase de tema claro",
                not pag.evaluate("document.documentElement.classList.contains('tema-claro')"))

        # 2. En claro se dan vuelta.
        montar(pag, pags["panel"], dict(ASPECTO, fondo="claro"))
        tinta = pag.evaluate("() => getComputedStyle(document.documentElement)"
                             ".getPropertyValue('--c232a35').trim()")
        revisar("en claro la tinta de un borde oscuro se aclara",
                tinta.startswith("#") and int(tinta[1:3], 16) > 0x80, tinta)
        fondo = pag.evaluate("getComputedStyle(document.body).backgroundColor")
        revisar("en claro el fondo de la pantalla es claro",
                sum(int(x) for x in fondo[4:-1].split(",")[:3]) > 600, fondo)
        revisar("en claro el <html> lleva la clase tema-claro",
                pag.evaluate("document.documentElement.classList.contains('tema-claro')"))
        # El semaforo: tres colores distintos y oscuros (para leerse sobre blanco).
        sem = {n: pag.evaluate(f"() => getComputedStyle(document.documentElement)"
                               f".getPropertyValue('--{n}').trim()") for n in
               ("ok", "mal", "aviso")}
        revisar("en claro el semaforo sigue teniendo tres colores distintos",
                len(set(sem.values())) == 3, str(sem))

        # ⚠ Que el motor no se muera en el camino. Esto está por una razón concreta: el
        # barrido de tintas se cayó con `document.body` en null (el archivo corre antes de
        # que exista el body en la app del celular) y **la pantalla seguía viéndose casi
        # bien** — sin botón 🎨 y sin acento, pero sin nada que gritara. Lo cazó la
        # comparación de capturas. Un error de JavaScript acá es una falla, no un aviso.
        # ⚠ `rough` se ignora y no es una excepcion cómoda: la libreria de dibujo a mano
        # alzada de la pizarra la sirve VACIA este mismo andamiaje (no hace falta para
        # mirar colores). El error lo produce la prueba, no el codigo.
        errores = []
        pag.on("pageerror", lambda e: "rough" in str(e) or errores.append(str(e)))
        for cual, html in pags.items():
            for tema in ("azulado", "claro"):
                del errores[:]
                montar(pag, html, dict(ASPECTO, fondo=tema))
                revisar(f"[{cual}/{tema}] el aspecto no tira ningun error de JavaScript",
                        not errores, "; ".join(errores[:2]))

        # 3. Lo importante: que no quede nada ilegible POR CULPA del tema claro.
        for cual, html in pags.items():
            montar(pag, html, dict(ASPECTO, fondo="azulado"))
            osc = {d["marca"]: d["ratio"] for d in pag.evaluate(CONTRASTES)}
            montar(pag, html, dict(ASPECTO, fondo="claro"))
            cla = {d["marca"]: d for d in pag.evaluate(CONTRASTES)}
            rotos = []
            for marca, d in cla.items():
                antes = osc.get(marca)
                if antes is None:
                    continue                     # no estaba en la otra corrida: no comparo
                if d["ratio"] < MINIMO <= antes:
                    rotos.append((marca.split("|")[-1], antes, d))
            rotos.sort(key=lambda x: x[2]["ratio"])
            revisar(f"[{cual}] ningun texto se vuelve ilegible en claro ({len(cla)} textos)",
                    not rotos,
                    "; ".join(f"'{t}' {a}->{d['ratio']} ({d['tinta']} sobre {d['fondo']})"
                              for t, a, d in rotos[:3]))
        nav.close()

    print()
    if fallas:
        print(f"{len(fallas)} MAL:")
        for f in fallas:
            print("   -", f)
        sys.exit(1)
    print("TODO BIEN")


if __name__ == "__main__":
    main()
