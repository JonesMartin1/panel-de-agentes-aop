"""La cabecera de una charla del celular no se despega de arriba.

El 2026-08-24 Martin mando una captura: adentro de una charla, deslizando para abajo
estando arriba de todo, quedaba una banda enorme de la foto de fondo entre la barra de
estado y el titulo, con las burbujas colgando. Es el "rebote" de iOS: cuando el scroller
se estira mas alla de su tope, el `position:sticky` se va con el contenido, porque el
borde contra el que se pega ya no esta donde uno lo ve.

El arreglo es `overscroll-behavior:none` en `#cuerpo` (sin rebote no hay de donde
despegarse). ⚠ Chromium no hace ese rebote, asi que aca NO se puede reproducir el bug:
lo que se fija es que la regla siga puesta en el scroller que corresponde y que la
cabecera siga siendo sticky — las dos mitades del arreglo, cada una inutil sin la otra.

⚠ El HTML del celular vive DENTRO de `panel.py` (`MOVIL_HTML`), asi que se lee del disco
y se sirve aca: el panel prendido tiene el de ayer en memoria hasta que se lo reinicie.

    python -m pruebas.ver_cabecera_pegada_movil
"""
import ast
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAIZ = Path(__file__).resolve().parent.parent


def html_movil():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(x, "id", "") == "MOVIL_HTML" for x in nodo.targets)):
            return nodo.value.value
    raise RuntimeError("No encontré MOVIL_HTML en panel.py")


fallas = []


def revisar(nombre, valor):
    print(("ok   " if valor else "MAL  ") + nombre)
    if not valor:
        fallas.append(nombre)


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    pag = nav.new_page(viewport={"width": 390, "height": 844})
    pag.route("**/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                          body="{}"))
    pag.route("**/movil", lambda r: r.fulfill(status=200, content_type="text/html",
                                              body=html_movil()))
    pag.goto("http://127.0.0.1:8750/movil", wait_until="domcontentloaded")

    # Una charla de mentira: la cabecera de siempre y burbujas de sobra para poder
    # scrollear. Se arma a mano para no depender de ninguna conversación de verdad.
    pag.evaluate("""() => {
      const c = document.querySelector('#cuerpo');
      c.className = 'charla';
      c.innerHTML = '<div id="cabecera"><div id="titulo"><span class="nom">Nueva</span></div></div>'
        + Array.from({length: 40}, (_, i) =>
            `<div class="msg ${i % 2 ? 'ia' : 'vos'}">mensaje de prueba ${i}</div>`).join('');
      document.body.classList.add('enCharla');
    }""")

    est = pag.evaluate("""() => {
      const c = getComputedStyle(document.querySelector('#cuerpo'));
      const h = getComputedStyle(document.querySelector('#cabecera'));
      return {rebote: c.overscrollBehaviorY, scroll: c.overflowY,
              pega: h.position, arriba: h.top};
    }""")
    print(f"#cuerpo: overflow-y={est['scroll']}, overscroll-behavior-y={est['rebote']}")
    revisar("el cuerpo es el que scrollea", est["scroll"] in ("auto", "scroll"))
    revisar("el cuerpo no rebota (overscroll-behavior:none)", est["rebote"] == "none")
    revisar("la cabecera sigue pegada arriba (sticky top:0)",
            est["pega"] == "sticky" and est["arriba"] == "0px")

    # Y que el sticky de verdad cumpla: con la charla scrolleada, la cabecera se queda
    # arriba de todo y ninguna burbuja le pasa por encima del borde superior.
    # ⚠ Todo en UN solo evaluate: la app repinta sola cada pocos segundos y, como acá no
    # hay ninguna charla de verdad abierta, en ese repintado le saca la clase `charla`
    # al cuerpo — y con ella el `padding-top:0` que el sticky necesita. Midiendo en el
    # mismo tick en que se pone la clase, el repintado no se mete en el medio.
    med = pag.evaluate("""() => {
      const c = document.querySelector('#cuerpo');
      c.classList.add('charla');
      c.scrollTo(0, 600);
      const cr = c.getBoundingClientRect();
      const h = document.querySelector('#cabecera').getBoundingClientRect();
      return {hueco: h.top - cr.top, alto: h.height, corrida: c.scrollTop};
    }""")
    revisar("la charla quedó scrolleada de verdad", med["corrida"] > 300)
    print(f"hueco entre el borde del cuerpo y la cabecera: {med['hueco']:.1f} px")
    revisar("scrolleada, la cabecera no deja hueco arriba", abs(med["hueco"]) <= 1)
    revisar("la cabecera se sigue viendo entera", med["alto"] > 20)
    nav.close()

if fallas:
    raise SystemExit("Falló: " + ", ".join(fallas))
print("todo bien")
