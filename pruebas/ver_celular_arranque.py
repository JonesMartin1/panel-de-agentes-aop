"""Al abrir la app del celular no sale una avalancha de pedidos, y el inicio no espera al gasto.

Nace del 2026-11-23 (Martin: *"la app del celular tambien tiene que andar super
rapidisimo"*). Ese dia el telefono tenia 173 pestañas guardadas y, cada vez que abria la
app, las pedia a TODAS juntas: unos 9 MB para bajar y 3,5 GB de archivos para leer del lado
del panel. Aca se abre la app de verdad en un Chrome con tamaño de telefono, con 60
pestañas guardadas, y se cuenta lo que pide.

⚠ No toca el panel que esta corriendo ni escribe nada: la pagina sale del `panel.py` del
disco y TODOS los pedidos los contesta esta prueba (el que se le escape, se anota y falla).

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_celular_arranque [--mutar]
"""
import ast
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.rutas import ESTATICOS, RAIZ

BASE = "http://celular.prueba"            # no existe: todo lo contesta la prueba
CUANTAS = 60
fallas = []


def revisar(que, bien, detalle=""):
    print(("  ok   " if bien else "  MAL  ") + que + (f"  ({detalle})" if detalle and not bien else ""))
    if not bien:
        fallas.append(que)


def movil_html():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


PESTANAS = [{"sid": f"charla-{i:03d}", "cwd": "D:\\pruebas\\alfa", "nombre": f"Charla {i}"}
            for i in range(CUANTAS)]


def correr(html, activa, demora_gasto=0.0, version_fondo="foto.jpg:1763900000", cambiar_js=None):
    """Abre la app y devuelve lo que se vio: pedidos de charla, cuantos a la vez, etc."""
    visto = {"chats": [], "a_la_vez": 0, "en_vuelo": 0, "escapados": [], "errores": [],
             "gasto": 0, "inicio_ms": None, "fondos": []}

    def atender(ruta):
        u = urlparse(ruta.request.url)
        camino = u.path

        def dar(cuerpo, tipo="application/json"):
            ruta.fulfill(status=200, content_type=tipo,
                         body=cuerpo if isinstance(cuerpo, (str, bytes)) else json.dumps(cuerpo))

        if camino == "/movil":
            return dar(html, "text/html")
        if camino.startswith("/estaticos/"):
            f = ESTATICOS / camino.rsplit("/", 1)[-1]
            js = f.read_text(encoding="utf-8") if f.exists() else ""
            if cambiar_js and f.name == "aspecto.js":
                js = cambiar_js(js)
            return dar(js, "application/javascript")
        if camino == "/fondo/windows/version":
            return dar({"v": version_fondo})
        if camino == "/fondo/windows":
            visto["fondos"].append(camino + ("?" + u.query if u.query else ""))
            return dar(b"", "image/jpeg")
        if camino == "/movil/chat":
            sid = parse_qs(u.query).get("sid", [""])[0]
            visto["chats"].append(sid)
            time.sleep(0.05)                       # que tarde algo, como por el telefono
            return dar({"mensajes": [{"de": "claude", "texto": "hola desde " + sid}],
                        "ocupada": False})
        if camino == "/movil/pestanas":
            return dar({"pestanas": PESTANAS, "activa": activa} if ruta.request.method == "GET"
                       else {"ok": True})
        if camino == "/movil/sesiones" and demora_gasto and "lista_colgada" not in visto:
            # La lista tambien se deja colgada en esta corrida: cuando llega, la app
            # repinta, y ese segundo dibujo taparia justo lo que se quiere medir (cuanto
            # tarda el PRIMERO, que es el que ve Martin al abrir).
            visto["lista_colgada"] = ruta
            return
        if camino == "/movil/sesiones":
            return dar({"ok": True, "laura": "", "carpetas": {"orden": [], "ocultas": [], "aspecto": {}},
                        "proyectos": [{"proyecto": "alfa", "cwd": "D:\\pruebas\\alfa", "vivo": False,
                                       "sesiones": [{"id": p["sid"], "nombre": p["nombre"], "ts": 1,
                                                     "ultimo": "vos", "viva": False,
                                                     "interactiva": False, "detalle": ""}
                                                    for p in PESTANAS]}]})
        if camino == "/gasto":
            visto["gasto"] += 1
            # ⚠ Estos pedidos se atienden DE A UNO: dormir aca frenaria tambien a los
            # demas y la prueba mediria su propio servidor. El gasto lento se imita
            # dejandolo SIN contestar; se contesta al final, desde afuera.
            if demora_gasto:
                visto["gasto_colgado"] = ruta
                return
            return dar({"ok": True, "hoy": {}, "claude": {}, "codex": {}})
        if camino == "/status":
            return dar({"servicios": {}, "encendido": False, "pausado": False})
        if camino == "/chat":
            return dar({"items": []})
        if camino in ("/movil/envivo",):
            return ruta.abort()
        if camino.startswith(("/movil/", "/sesion/", "/kpis/", "/carpetas/", "/fijados", "/aspecto",
                              "/fondo/", "/charlas/", "/marcas")):
            return dar({"ok": False})
        if camino.endswith((".png", ".ico", ".json", ".jpg", ".webp", ".woff2")):
            return dar(b"", "application/octet-stream")
        visto["escapados"].append(camino)
        return dar({"ok": False})

    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True, device_scale_factor=3)
        pag = ctx.new_page()
        pag.on("pageerror", lambda e: visto["errores"].append(str(e)))

        # Cuantos pedidos de charla hay en el aire a la vez: se cuenta cuando SALEN del
        # navegador y cuando vuelven, no adentro de `atender` (que va de a uno).
        def salio(pedido):
            if "/movil/chat" in pedido.url:
                visto["en_vuelo"] += 1
                visto["a_la_vez"] = max(visto["a_la_vez"], visto["en_vuelo"])

        def volvio(pedido):
            if "/movil/chat" in pedido.url:
                visto["en_vuelo"] -= 1

        pag.on("request", salio)
        pag.on("requestfinished", volvio)
        pag.on("requestfailed", volvio)
        pag.route("**/*", atender)
        # Lo que el telefono ya tenia guardado de la vez anterior
        pag.add_init_script("localStorage.setItem('pestanas', %s); localStorage.setItem('activa', %s);"
                            % (json.dumps(json.dumps(PESTANAS)), json.dumps(activa)))
        t0 = time.time()
        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        if activa == "panel":
            try:
                pag.wait_for_function("document.querySelector('#cuerpo').dataset.vista === 'panel'",
                                      timeout=8000)
                visto["inicio_ms"] = (time.time() - t0) * 1000
            except Exception:
                pass
            for colgado in ("gasto_colgado", "lista_colgada"):
                if visto.get(colgado):
                    visto[colgado].fulfill(status=200, content_type="application/json",
                                           body='{"ok": false}')
                    visto[colgado] = None
        pag.wait_for_timeout(4500)
        nav.close()
    return visto


def chequeos(html, cambiar_js=None):
    print("\n== Abrir la app parado en una charla, con %d pestañas guardadas ==" % CUANTAS)
    v = correr(html, "charla-000", cambiar_js=cambiar_js)
    revisar("la foto de fondo (2 MB) se pide UNA vez y con su version",
            v["fondos"] == ["/fondo/windows?v=foto.jpg%3A1763900000"], str(v["fondos"]))
    distintas = sorted(set(v["chats"]))
    revisar("la charla abierta se pide", "charla-000" in distintas, str(distintas[:8]))
    revisar("se precargan algunas mas, pero pocas (no las %d)" % CUANTAS,
            2 <= len(distintas) <= 7, f"se pidieron {len(distintas)} charlas distintas")
    revisar("y son las PRIMERAS de la lista, que son las ultimas que abriste",
            all(int(s.split("-")[1]) <= 6 for s in distintas), str(distintas))
    revisar("nunca mas de tres pedidos de charla a la vez", v["a_la_vez"] <= 3,
            f"llego a haber {v['a_la_vez']} juntos")
    revisar("ningun pedido se le escapo a la prueba", not v["escapados"], str(v["escapados"][:5]))
    revisar("la pagina no tiro errores", not v["errores"], str(v["errores"][:2]))

    print("\n== Abrir la app en el inicio, con el gasto y la lista que no contestan ==")
    v = correr(html, "panel", demora_gasto=1)
    revisar("el inicio se dibuja sin esperar al gasto",
            v["inicio_ms"] is not None and v["inicio_ms"] < 2500,
            f"tardo {v['inicio_ms'] and round(v['inicio_ms'])} ms")
    revisar("y el gasto igual se pide", v["gasto"] >= 1)
    revisar("la pagina no tiro errores", not v["errores"], str(v["errores"][:2]))

    print("\n== Un panel que no sabe decir la version de la foto ==")
    v = correr(html, "charla-000", version_fondo="", cambiar_js=cambiar_js)
    revisar("la foto se pide igual, con la direccion pelada (no queda sin fondo)",
            v["fondos"] == ["/fondo/windows"], str(v["fondos"]))


def cambiar(html, viejo, nuevo, es_regex=False):
    sale = re.sub(viejo, nuevo, html, count=1, flags=re.S) if es_regex else html.replace(viejo, nuevo, 1)
    assert sale != html, "la mutacion ya no encuentra su texto: " + viejo[:60]
    return sale


if __name__ == "__main__":
    HTML = movil_html()
    chequeos(HTML)
    bien = not fallas
    if "--mutar" in sys.argv and bien:
        print("\n== Mutaciones (se cambian en memoria, el archivo no se toca) ==")
        cazadas = 0
        rotas = [
            ("precargar todas las pestañas juntas, como antes",
             cambiar(HTML, r"\(async \(\) => \{\s*for \(const p of pestanas\.filter\(x => x\.sid !== activa\)"
                           r"\.slice\(0, PRECARGAR_MAX\)\)\s*await precargar\(p\);\s*\}\)\(\);",
                     "pestanas.forEach(precargar);", es_regex=True)),
            ("precargar cuarenta en vez de cinco",
             cambiar(HTML, "const PRECARGAR_MAX = 5;", "const PRECARGAR_MAX = 40;")),
            ("precargar pocas, pero todas a la vez",
             cambiar(HTML, "      await precargar(p);\n  })();", "      precargar(p);\n  })();")),
            ("el inicio vuelve a esperar al gasto",
             cambiar(HTML, "pedirJson('/gasto').then(g => { if (g && g.ok) gastoMovil = g; }).catch(() => {});",
                     "await pedirJson('/gasto').catch(() => {});")),
        ]
        def sin_esperar(js):
            return cambiar(js, ": (fondoPreguntado ? FOTO_WINDOWS : '');", ": FOTO_WINDOWS;")

        def sin_respaldo(js):
            return cambiar(js, "if (primera && !versionFondo) aplicar();", "")

        rotas += [("la foto se pide sin esperar su version (se baja dos veces)", (HTML, sin_esperar)),
                  ("sin version no hay respaldo (la pantalla queda sin foto)", (HTML, sin_respaldo))]
        for nombre, roto in rotas:
            fallas.clear()
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                chequeos(*roto) if isinstance(roto, tuple) else chequeos(roto)
            cazo = bool(fallas)
            cazadas += cazo
            print(f"  {'cazada ' if cazo else 'NO CAZADA'}  {nombre}" + (f"  → {fallas[0]}" if cazo else ""))
        fallas.clear()
        bien = cazadas == len(rotas)
        print(f"\n  {cazadas} de {len(rotas)} mutaciones cazadas")
    print("\nTODO BIEN" if bien else "\nHAY PROBLEMAS: " + "; ".join(fallas))
    sys.exit(0 if bien else 1)
