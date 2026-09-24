"""El explorador de archivos de /sesiones, mirado en un navegador de verdad.

⭐ El servidor esta INVENTADO entero (misma receta que `ver_estudio.py`): se
interceptan con `page.route` hasta la propia pagina y las direcciones nuevas, asi
que esto corre con el panel viejo vivo, sin reiniciarlo y sin leer un solo archivo
de verdad. Es la unica forma de probar una pantalla cuyas rutas todavia no existen
en el panel que esta corriendo.

Lo que se mira: que el arbol se dibuje a la izquierda, que una carpeta se abra y
pida sus hijos recien ahi, que tocar un archivo lo muestre a la derecha con sus
numeros de renglon, y que la cruz devuelva la conversacion. Y la captura, que es
donde aparecen los defectos que el codigo no muestra.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_arbol_archivos
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

from app.rutas import ESTATICOS, RESULTADOS

CWD = r"D:\IA\wpp-transcriptor"
SALIDA = RESULTADOS / "capturas"

# El "disco" inventado: que hay adentro de cada carpeta.
DISCO = {
    "": [{"nombre": "app", "dir": True, "bytes": 0, "ts": 1e9},
         {"nombre": "pruebas", "dir": True, "bytes": 0, "ts": 1e9},
         {"nombre": "CLAUDE.md", "dir": False, "bytes": 8123, "ts": 1e9},
         {"nombre": "panel.py", "dir": False, "bytes": 402311, "ts": 1e9},
         {"nombre": "launcher.vbs", "dir": False, "bytes": 900, "ts": 1e9}],
    "app": [{"nombre": "estaticos", "dir": True, "bytes": 0, "ts": 1e9},
            {"nombre": "rutas.py", "dir": False, "bytes": 7200, "ts": 1e9}],
    "app/estaticos": [{"nombre": "sesiones.html", "dir": False, "bytes": 51200, "ts": 1e9},
                      {"nombre": "menu.js", "dir": False, "bytes": 3100, "ts": 1e9}],
    "pruebas": [{"nombre": "probar_arbol_archivos.py", "dir": False, "bytes": 5100, "ts": 1e9}],
}
TEXTO = "def hola():\n    return 'buenas'\n\n# tres renglones y este comentario\n"

SESIONES = {"proyectos": [{"proyecto": "wpp-transcriptor", "cwd": CWD, "vivo": False,
                           "sesiones": [{"id": "s1", "nombre": "Una charla", "viva": False,
                                         "detalle": "hace 5 min", "ultimo": "claude",
                                         "ts": 1}]}]}

ok = fallo = 0


def chequear(que, condicion, detalle=""):
    global ok, fallo
    if condicion:
        ok += 1
        print(f"  ok   {que}")
    else:
        fallo += 1
        print(f"  FALLA {que}" + (f"  ({detalle})" if detalle else ""))


def json_handler(cuerpo):
    """Fabrica de handlers. ⚠ NO puede ser un lambda con dos parametros: Playwright
    mira cuantos acepta y con dos le pasa el Request como segundo."""
    def handler(ruta):
        ruta.fulfill(status=200, content_type="application/json",
                     body=json.dumps(cuerpo))
    return handler


def archivo_handler(ruta_disco, tipo):
    def handler(ruta):
        ruta.fulfill(status=200, content_type=tipo,
                     body=Path(ruta_disco).read_text(encoding="utf-8"))
    return handler


def lista_handler(ruta):
    q = parse_qs(urlparse(ruta.request.url).query)
    sub = (q.get("sub") or [""])[0]
    items = DISCO.get(sub)
    cuerpo = ({"ok": True, "sub": sub, "items": items, "de_mas": 0} if items is not None
              else {"ok": False, "error": "esa carpeta no existe"})
    ruta.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))


def ver_handler(ruta):
    q = parse_qs(urlparse(ruta.request.url).query)
    r = (q.get("ruta") or [""])[0]
    ruta.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": True, "ruta": r, "nombre": r.split("/")[-1], "bytes": len(TEXTO),
         "ts": 1755400000, "completo": CWD + "\\" + r.replace("/", "\\"),
         "tipo": "texto", "texto": TEXTO, "cortado": False}))


with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 1400, "height": 900})
    errores = []
    pagina.on("pageerror", lambda e: errores.append(str(e)))

    # ⚠ El comodin va PRIMERO: Playwright prueba las rutas de la ultima a la primera,
    # asi que uno puesto al final se come a las especificas y la pagina llega vacia.
    pagina.route("**/*", lambda r: r.fulfill(status=200, content_type="text/plain", body=""))
    pagina.route("**/sesiones", archivo_handler(ESTATICOS / "sesiones.html", "text/html"))
    pagina.route("**/estaticos/marcado.js",
                 archivo_handler(ESTATICOS / "marcado.js", "application/javascript"))
    pagina.route("**/estaticos/menu.js",
                 archivo_handler(ESTATICOS / "menu.js", "application/javascript"))
    pagina.route("**/movil/sesiones", json_handler(SESIONES))
    pagina.route("**/movil/novedad", json_handler({}))
    pagina.route("**/movil/chat", json_handler({"mensajes": []}))
    pagina.route("**/archivos/lista*", lista_handler)
    pagina.route("**/archivos/ver*", ver_handler)

    pagina.goto("http://localhost:8750/sesiones", wait_until="domcontentloaded")
    pagina.wait_for_timeout(900)

    print("\n== La columna de la izquierda ==")
    chequear("existe el piso de los proyectos", pagina.locator("#paneProy").count() == 1)
    chequear("existe el piso del explorador", pagina.locator("#paneArch").count() == 1)
    chequear("sin carpeta elegida, avisa que hay que elegir una",
             "Elegí una carpeta" in pagina.locator("#arbol").inner_text())
    chequear("el explorador queda ABAJO de los proyectos",
             pagina.locator("#paneArch").bounding_box()["y"] >
             pagina.locator("#paneProy").bounding_box()["y"])

    print("\n== El arbol de la carpeta ==")
    pagina.locator('.carpeta[data-proy="wpp-transcriptor"]').click()
    pagina.wait_for_selector("#arbol .nodo")
    nodos = pagina.locator("#arbol .nodo")
    nombres = [nodos.nth(i).inner_text().strip() for i in range(nodos.count())]
    chequear("estan los archivos de la raiz", any("panel.py" in n for n in nombres),
             str(nombres))
    chequear("las carpetas van primero", "app" in nombres[0] or "app" in nombres[1])
    chequear("el titulo dice de que proyecto es",
             "wpp-transcriptor" in pagina.locator("#arbolNom").inner_text())

    print("\n== Abrir una carpeta ==")
    pagina.locator('#arbol .nodo[data-r="app"]').click()
    pagina.wait_for_selector('#arbol .nodo[data-r="app/rutas.py"]')
    chequear("los hijos aparecen adentro", True)
    # ⚠ La sangria NO se mide en la caja de la fila: la fila ocupa todo el ancho y
    # arranca en x=0 siempre (la sangria es `padding-left`). Se mide el NOMBRE.
    hijo = pagina.locator('#arbol .nodo[data-r="app/rutas.py"] .nom').bounding_box()
    padre = pagina.locator('#arbol .nodo[data-r="app"] .nom').bounding_box()
    chequear("y con sangria, como en VS Code", hijo["x"] > padre["x"],
             f"{hijo['x']} vs {padre['x']}")
    pagina.locator('#arbol .nodo[data-r="app"]').click()
    pagina.wait_for_timeout(150)
    chequear("volver a tocarla la cierra",
             pagina.locator('#arbol .nodo[data-r="app/rutas.py"]').count() == 0)

    print("\n== Abrir un archivo ==")
    pagina.locator('#arbol .nodo[data-r="panel.py"]').click()
    pagina.wait_for_selector("#cuerpo .codigo")
    chequear("el nombre esta arriba", "panel.py" in pagina.locator("#cuerpo .vCab").inner_text())
    chequear("se ve el contenido", "buenas" in pagina.locator("#cuerpo").inner_text())
    chequear("y los numeros de renglon",
             pagina.locator("#cuerpo .codigo .ren").inner_text().strip().startswith("1"))
    chequear("el archivo queda marcado en el arbol",
             pagina.locator('#arbol .nodo.sel[data-r="panel.py"]').count() == 1)
    pagina.wait_for_timeout(3300)      # el repintado de cada 3 s no lo tiene que tapar
    chequear("sigue abierto despues del repintado",
             pagina.locator("#cuerpo .codigo").count() == 1)

    SALIDA.mkdir(parents=True, exist_ok=True)
    pagina.screenshot(path=str(SALIDA / "arbol_archivos.png"))

    print("\n== Un .md se lee dibujado ==")
    pagina.locator('#arbol .nodo[data-r="CLAUDE.md"]').click()
    # ⚠ Esperar `.vCab` NO sirve: el del archivo anterior ya esta en pantalla y la
    # espera se cumple al instante, asi que se mide la vista vieja (la trampa de
    # siempre en estas pruebas: no midas contra un mundo que se mueve). Se espera
    # algo que solo existe en la vista NUEVA: el boton de "verlo tal cual".
    pagina.wait_for_selector("#vCrudo")
    chequear("un .md NO se muestra como codigo", pagina.locator("#cuerpo .codigo").count() == 0)
    chequear("se dibuja el markdown", pagina.locator("#cuerpo .md").count() == 1)
    chequear("y tiene el boton para verlo tal cual",
             "tal cual" in pagina.locator("#cuerpo .vCab").inner_text())
    pagina.locator("#vCrudo").click()
    pagina.wait_for_selector("#cuerpo .codigo")
    chequear("apretandolo aparece el texto pelado con renglones",
             pagina.locator("#cuerpo .codigo .ren").count() == 1)

    print("\n== Cerrarlo ==")
    pagina.locator("#vCerrar").click()
    pagina.wait_for_timeout(300)
    chequear("vuelve la bandeja", pagina.locator("#cuerpo .cabeza").count() == 1)
    chequear("y el archivo se desmarca", pagina.locator("#arbol .nodo.sel").count() == 0)

    print("\n== Ancho de la columna ==")
    antes = pagina.locator("aside").bounding_box()["width"]
    pagina.mouse.move(antes - 2, 500)
    pagina.mouse.down()
    pagina.mouse.move(antes + 90, 500, steps=6)
    pagina.mouse.up()
    pagina.wait_for_timeout(200)
    ahora = pagina.locator("aside").bounding_box()["width"]
    chequear("se ensancha arrastrando el borde", ahora > antes + 60, f"{antes} -> {ahora}")

    print("\n== Ctrl+B esconde la columna entera, como en VS Code ==")
    ancho_antes = pagina.locator("section#cuerpo").bounding_box()["width"]
    pagina.keyboard.press("Control+b")
    pagina.wait_for_timeout(250)
    chequear("se va la columna entera", not pagina.locator("aside").is_visible())
    chequear("y la conversacion se queda con la pantalla",
             pagina.locator("section#cuerpo").bounding_box()["width"] > ancho_antes + 150)
    chequear("queda el boton para traerla de vuelta",
             pagina.locator("#btnLateral").is_visible())
    pagina.locator("#btnLateral").click()
    pagina.wait_for_timeout(250)
    chequear("el boton la trae de vuelta", pagina.locator("aside").is_visible())
    # Escribiendo en un campo tambien tiene que andar: es donde uno esta parado casi
    # siempre en esta pantalla.
    pagina.locator("#buscar").click()
    pagina.keyboard.press("Control+b")
    pagina.wait_for_timeout(250)
    chequear("anda con el cursor en una caja de texto",
             not pagina.locator("aside").is_visible())
    pagina.keyboard.press("Control+b")
    pagina.wait_for_timeout(250)
    chequear("y vuelve con el mismo ancho de antes",
             abs(pagina.locator("aside").bounding_box()["width"] - ahora) < 2)

    print("\n== Y el ▾ del explorador sigue siendo otra cosa ==")
    pagina.locator("#arbolPlegar").click()
    pagina.wait_for_timeout(200)
    chequear("pliega SOLO el arbol", not pagina.locator("#arbol").is_visible())
    chequear("y los proyectos se quedan", pagina.locator("#carpetas").is_visible())
    pagina.locator("#arbolPlegar").click()
    pagina.wait_for_timeout(200)
    chequear("y lo devuelve", pagina.locator("#arbol").is_visible())

    print("\n== En 'Todas' se queda la ultima carpeta que miraste ==")
    chequear("el titulo dice que eso son ARCHIVOS, no solo el proyecto",
             pagina.locator("#arbolNom").inner_text().startswith("Archivos"))
    pagina.locator("#carpetas .carpeta").first.click()          # ✉ Todas
    pagina.wait_for_timeout(600)
    chequear("el arbol NO se vacia al volver a Todas",
             pagina.locator("#arbol .nodo").count() > 0)
    chequear("y sigue diciendo de que carpeta es",
             "wpp-transcriptor" in pagina.locator("#arbolNom").inner_text())

    chequear("ni un error de JavaScript en toda la corrida", not errores, str(errores[:2]))
    navegador.close()

print(f"\nCaptura en {SALIDA / 'arbol_archivos.png'}")
print(f"{ok} verdes, {fallo} en rojo")
sys.exit(1 if fallo else 0)
