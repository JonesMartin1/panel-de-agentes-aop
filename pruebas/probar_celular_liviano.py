"""Lo que viaja al celular pesa poco: se comprime y no se manda de nuevo lo que no cambio.

Nace del 2026-11-23 (Martin: *"la app del celular tambien tiene que andar super
rapidisimo"*). Prueba la pieza `app/voz/aligerar.py` de dos maneras:

  1. contra un panel DE MENTIRA armado aca, donde se controla que contesta cada ruta;
  2. contra el `panel.py` de verdad, sin levantarlo (no corre su arranque: ni vigias, ni
     trabajos, ni servicios) y pidiendole solo cosas de leer.

Lo que no se puede romper:
  · la respuesta descomprimida es IDENTICA a la de antes;
  · "no cambio" se contesta solo si de verdad no cambio;
  · los canales en vivo y las rutas que no estan en la lista pasan sin tocar;
  · la pagina del celular sigue sin guardarse (regla del 2026-08-17).

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_celular_liviano [--mutar]
"""
import gzip
import json
import re
import sys
import tempfile
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.testclient import TestClient

from app.voz import aligerar

ok = fallo = 0
CALLADO = False


def chequear(que, condicion, detalle=""):
    global ok, fallo
    if condicion:
        ok += 1
        if not CALLADO:
            print(f"  ok   {que}")
    else:
        fallo += 1
        if not CALLADO:
            print(f"  FALLA {que}" + (f"  ({detalle})" if detalle else ""))


TMP = Path(tempfile.mkdtemp(prefix="liviano_"))
(TMP / "grande.js").write_text("// archivo de la pagina\n" + "var x = 1;\n" * 400, encoding="utf-8")
FOTO = bytes([0xFF, 0xD8]) + b"foto que ya viene comprimida " * 300
ESTADO = {"lista":[{"id": i, "nombre": "charla numero %d" % i} for i in range(200)]}


def panel_de_mentira():
    app = FastAPI()

    @app.get("/movil/sesiones")
    def sesiones():
        return {"proyectos": ESTADO["lista"]}

    @app.get("/movil/borradores")
    def borradores():
        return {"a": "corto"}

    @app.get("/otra/cosa")
    def otra():
        return {"proyectos": ESTADO["lista"]}

    @app.post("/movil/sesiones")
    def escribir():
        return {"proyectos": ESTADO["lista"]}

    @app.get("/movil/envivo")
    def envivo():
        def chorro():
            for i in range(3):
                yield ("data: " + "x" * 600 + "\n\n").encode()
        return StreamingResponse(chorro(), media_type="text/event-stream")

    @app.get("/movil", response_class=HTMLResponse)
    def pagina():
        return HTMLResponse("<html>" + "<p>hola</p>" * 400 + "</html>",
                            headers={"Cache-Control": "no-store, must-revalidate"})

    @app.get("/estaticos/grande.js")
    def archivo():
        return FileResponse(TMP / "grande.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-store"})

    @app.get("/estaticos/tercero.js")
    def tercero():
        return FileResponse(TMP / "grande.js", media_type="application/javascript",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/fondo/windows")
    def fondo():
        from fastapi.responses import Response
        return Response(FOTO, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/movil/chat")
    def roto():
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "no hay " * 300}, status_code=404)

    app.add_middleware(aligerar.Aligerar)
    return app


def crudo(c, ruta, **cabeceras):
    """El pedido tal cual viaja: sin que el cliente de prueba descomprima por su cuenta."""
    with c.stream("GET", ruta, headers={"Accept-Encoding": "gzip", **cabeceras}) as r:
        return r, b"".join(r.iter_raw())


def pieza():
    c = TestClient(panel_de_mentira())
    sin_pieza = json.dumps({"proyectos": ESTADO["lista"]}, separators=(",", ":")).encode()

    r, cuerpo = crudo(c, "/movil/sesiones")
    chequear("la lista viaja comprimida", r.headers.get("content-encoding") == "gzip"
             and len(cuerpo) < len(sin_pieza) / 3, f"{len(cuerpo)} de {len(sin_pieza)} bytes")
    chequear("y descomprimida es IDENTICA a la de antes", gzip.decompress(cuerpo) == sin_pieza)
    chequear("el largo anunciado es el del cuerpo que viaja",
             r.headers.get("content-length") == str(len(cuerpo)))
    marca = r.headers.get("etag")
    chequear("trae su huella y obliga a preguntar siempre antes de usar la guardada",
             bool(marca) and r.headers.get("cache-control") == "no-cache", str(dict(r.headers)))

    r2, cuerpo2 = crudo(c, "/movil/sesiones", **{"If-None-Match": marca})
    chequear("si el telefono ya la tiene, se contesta 304 y no viaja NADA",
             r2.status_code == 304 and cuerpo2 == b"", f"{r2.status_code}, {len(cuerpo2)} bytes")
    chequear("el 304 repite la huella", r2.headers.get("etag") == marca)

    ESTADO["lista"][0]["nombre"] = "cambio el nombre"
    try:
        r3, cuerpo3 = crudo(c, "/movil/sesiones", **{"If-None-Match": marca})
        chequear("⭐ si CAMBIO, viaja la nueva aunque el telefono diga que tiene una",
                 r3.status_code == 200 and b"cambio el nombre" in gzip.decompress(cuerpo3)
                 and r3.headers.get("etag") != marca, str(r3.status_code))
    finally:
        ESTADO["lista"][0]["nombre"] = "charla numero 0"

    r, cuerpo = crudo(c, "/movil/borradores")
    chequear("lo chico no se comprime (no vale la vuelta) pero lleva huella",
             "content-encoding" not in r.headers and cuerpo == b'{"a":"corto"}' and r.headers.get("etag"))

    with c.stream("GET", "/movil/sesiones", headers={"Accept-Encoding": "identity"}) as r:
        cuerpo = b"".join(r.iter_raw())
    chequear("a quien no acepta comprimido se le manda sin comprimir",
             "content-encoding" not in r.headers and cuerpo == sin_pieza)

    r, cuerpo = crudo(c, "/otra/cosa")
    chequear("una ruta que NO esta en la lista pasa sin tocar",
             "content-encoding" not in r.headers and "etag" not in r.headers and cuerpo == sin_pieza)

    r, cuerpo = crudo(c, "/movil/envivo")
    chequear("⭐ el canal en vivo pasa sin tocar (ni comprimido ni juntado)",
             "content-encoding" not in r.headers and "etag" not in r.headers
             and r.headers.get("content-type", "").startswith("text/event-stream")
             and cuerpo.count(b"data: ") == 3)

    r = c.post("/movil/sesiones")
    chequear("un pedido que no es de leer (POST) pasa sin tocar",
             "etag" not in r.headers and r.json() == {"proyectos": ESTADO["lista"]})

    r, cuerpo = crudo(c, "/movil/chat")
    chequear("una respuesta de error pasa sin tocar",
             r.status_code == 404 and "etag" not in r.headers and "content-encoding" not in r.headers)

    r, cuerpo = crudo(c, "/movil")
    chequear("⭐ la PAGINA se comprime pero sigue sin guardarse (regla del 17/08)",
             r.headers.get("content-encoding") == "gzip" and "etag" not in r.headers
             and r.headers.get("cache-control") == "no-store, must-revalidate",
             str(dict(r.headers)))

    original = (TMP / "grande.js").read_bytes()
    r, cuerpo = crudo(c, "/estaticos/grande.js")
    chequear("un archivo de la pagina sin version: comprimido, con huella y preguntando siempre",
             gzip.decompress(cuerpo) == original and r.headers.get("cache-control") == "no-cache"
             and bool(r.headers.get("etag")), str(dict(r.headers)))
    r304, _ = crudo(c, "/estaticos/grande.js", **{"If-None-Match": r.headers.get("etag", "")})
    chequear("y si no cambio, 304", r304.status_code == 304)
    r, cuerpo = crudo(c, "/estaticos/grande.js?v=1763900000")
    chequear("⭐ CON version se guarda en el telefono para siempre",
             r.headers.get("cache-control") == aligerar.PARA_SIEMPRE
             and gzip.decompress(cuerpo) == original, r.headers.get("cache-control"))
    r, cuerpo = crudo(c, "/estaticos/tercero.js")
    chequear("el que ya traia su propia regla de guardado la conserva",
             r.headers.get("cache-control") == "public, max-age=86400")
    r, cuerpo = crudo(c, "/fondo/windows?v=foto.jpg%3A1763900000")
    chequear("⭐ la foto de fondo con version se guarda para siempre, y NO se pasa por gzip",
             r.headers.get("cache-control") == aligerar.PARA_SIEMPRE and cuerpo == FOTO
             and "content-encoding" not in r.headers, str(dict(r.headers)))
    r, cuerpo = crudo(c, "/fondo/windows")
    r304, nada = crudo(c, "/fondo/windows", **{"If-None-Match": r.headers.get("etag", "")})
    chequear("y sin version pregunta siempre, pero no viaja si es la misma",
             r.headers.get("cache-control") == "no-cache" and r304.status_code == 304 and nada == b"")
    r, cuerpo = crudo(c, "/estaticos/grande.js", Range="bytes=0-9")
    chequear("un pedido por pedazos pasa sin tocar",
             "content-encoding" not in r.headers and cuerpo == original[:10], f"{r.status_code} {cuerpo[:20]}")


def versiones():
    html = ('<script src="/estaticos/grande.js"></script>\n<script src="/estaticos/no-existe.js">'
            '</script>\n<script src="/pizarra/rough.js"></script>')
    sale = aligerar.versionar(html, TMP)
    fecha = int((TMP / "grande.js").stat().st_mtime)
    chequear("al archivo que existe se le pega la fecha", f'/estaticos/grande.js?v={fecha}"' in sale, sale)
    chequear("el que no existe y el de otra carpeta quedan como estaban",
             'src="/estaticos/no-existe.js"' in sale and 'src="/pizarra/rough.js"' in sale)
    import os
    os.utime(TMP / "grande.js", (fecha + 50, fecha + 50))
    chequear("si el archivo cambia, cambia la direccion (y el telefono baja el nuevo)",
             f"?v={fecha + 50}" in aligerar.versionar(html, TMP))
    os.utime(TMP / "grande.js", (fecha, fecha))


def panel_de_verdad():
    import panel
    c = TestClient(panel.app)                  # sin `with`: no corre el arranque del panel
    r, cuerpo = crudo(c, "/movil")
    pagina = gzip.decompress(cuerpo).decode("utf-8") if r.headers.get("content-encoding") == "gzip" else ""
    chequear("la pagina del celular sale comprimida a menos de un tercio",
             0 < len(cuerpo) < len(panel.MOVIL_HTML.encode("utf-8")) / 3,
             f"{len(cuerpo)} de {len(panel.MOVIL_HTML.encode('utf-8'))} bytes")
    chequear("y sigue con no-store", r.headers.get("cache-control") == "no-store, must-revalidate")
    guiones = re.findall(r'<script src="(/estaticos/[^"]+)"', pagina)
    chequear("todos sus archivos salen con version",
             len(guiones) >= 10 and all(re.search(r"\?v=\d+$", g) for g in guiones), str(guiones))
    sin_version = re.sub(r"\?v=\d+", "", pagina)
    chequear("sacandole las versiones, la pagina es la misma de siempre",
             sin_version == panel.MOVIL_HTML)
    pesados = 0
    for g in guiones:
        r, cuerpo = crudo(c, g)
        pesados += r.headers.get("cache-control") == aligerar.PARA_SIEMPRE and r.status_code == 200
    chequear("y cada uno se sirve para guardar para siempre", pesados == len(guiones),
             f"{pesados} de {len(guiones)}")

    r, cuerpo = crudo(c, "/movil/pestanas")
    r2, cuerpo2 = crudo(c, "/movil/pestanas", **{"If-None-Match": r.headers.get("etag", "x")})
    chequear("un dato del panel de verdad, pedido dos veces: la segunda no viaja",
             r.status_code == 200 and r2.status_code == 304 and cuerpo2 == b"",
             f"{r.status_code} y {r2.status_code}")

    # La app misma: lo que se cambio en MOVIL_HTML
    h = panel.MOVIL_HTML
    chequear("la app ya no precarga TODAS las pestañas al abrir",
             "pestanas.forEach(precargar)" not in h and "slice(0, PRECARGAR_MAX)" in h)
    m = re.search(r"const PRECARGAR_MAX = (\d+);", h)
    chequear("y el tope de precarga es chico", bool(m) and 1 <= int(m.group(1)) <= 8)
    junto = re.search(r"await Promise\.all\(\[\s*pedirJson\('/status'\)(.*?)\]\);", h, re.S)
    chequear("el inicio no espera al gasto", bool(junto) and "/gasto" not in junto.group(1)
             and "pedirJson('/gasto').then" in h)


GRUPOS = [("La pieza, contra un panel de mentira", pieza),
          ("Las versiones de los archivos", versiones),
          ("El panel de verdad (sin levantarlo)", panel_de_verdad)]


def _corre_bien(grupo):
    """Si el grupo pasa entero con lo que haya puesto ahora."""
    global fallo
    antes = fallo
    grupo()
    bien = fallo == antes
    fallo = antes
    return bien


def mutar():
    global CALLADO, fallo, ok
    cazadas = total = 0

    def probar(nombre, grupo, romper, arreglar):
        nonlocal cazadas, total
        global CALLADO, fallo, ok
        total += 1
        romper()
        antes, ok_antes = fallo, ok
        CALLADO = True
        try:
            grupo()
        except Exception:
            fallo += 1
        finally:
            CALLADO = False
            arreglar()
        cazo = fallo > antes
        fallo, ok = antes, ok_antes
        cazadas += cazo
        print(f"  {'cazada ' if cazo else 'NO CAZADA'}  {nombre}")

    g = {}

    def poner(nombre, valor):
        def romper():
            g[nombre] = getattr(aligerar, nombre)
            setattr(aligerar, nombre, valor)
        return romper, lambda: setattr(aligerar, nombre, g[nombre])

    print("\n== Mutaciones ==")
    probar("la huella no mira el contenido (siempre 'no cambio')", pieza,
           *poner("huella", lambda cuerpo: '"fija"'))
    # ⚠ El canal en vivo tiene DOS defensas (no esta en la lista, y ademas se reconoce por
    # su tipo): rompiendo una sola la otra lo salva y el chequeo no puede fallar. Se rompen
    # las dos, y de paso queda probado que cada una sola alcanza.
    probar("el canal en vivo entra en la lista (sola, NO tiene que romper nada)",
           lambda: chequear("", False) if _corre_bien(pieza) else None,
           *poner("DATOS", aligerar.DATOS | {"/movil/envivo"}))

    def sin_defensas():
        import inspect
        g["DATOS"], g["Aligerar"] = aligerar.DATOS, aligerar.Aligerar
        fuente = inspect.getsource(aligerar.Aligerar)
        viejo = 'or cab.get("content-type", "").startswith("text/event-stream")'
        assert viejo in fuente, "la mutacion ya no encuentra la defensa por tipo"
        exec(fuente.replace(viejo, ""), aligerar.__dict__)
        aligerar.DATOS = g["DATOS"] | {"/movil/envivo"}

    def con_defensas():
        aligerar.DATOS, aligerar.Aligerar = g["DATOS"], g["Aligerar"]

    probar("el canal en vivo sin ninguna de sus dos defensas", pieza, sin_defensas, con_defensas)
    probar("la pagina se trata como un dato (se guardaria en el telefono)", pieza,
           *poner("PAGINAS", set()))
    probar("todo se guarda para siempre, con version o sin ella", pieza,
           *poner("re", type("r", (), {"search": staticmethod(lambda *a, **k: True),
                                       "sub": staticmethod(re.sub)})))
    probar("se comprime tambien lo chico", pieza, *poner("MINIMO_COMPRIMIR", 1))
    probar("se pasan por gzip tambien las fotos", pieza, *poner("SE_COMPRIME", ("",)))
    probar("la foto de fondo queda fuera de la lista", pieza, *poner("ARCHIVOS_SUELTOS", set()))
    probar("las versiones no miran la fecha del archivo", versiones,
           *poner("versionar", lambda html, carpeta: html.replace('.js"', '.js?v=1"')))
    probar("la pagina del panel sale sin versiones", panel_de_verdad,
           *poner("versionar", lambda html, carpeta: html))
    print(f"\n  {cazadas} de {total} mutaciones cazadas")
    return cazadas == total


if __name__ == "__main__":
    for titulo, grupo in GRUPOS:
        print(f"\n== {titulo} ==")
        grupo()
    todo_bien = fallo == 0
    if "--mutar" in sys.argv and todo_bien:
        todo_bien = mutar()
    print(f"\n{ok} ok, {fallo} fallas" + ("  — TODO BIEN" if todo_bien else "  — HAY PROBLEMAS"))
    sys.exit(0 if todo_bien else 1)
