"""Prueba de la pestaña "Vista" (`app/voz/vista.py`), sin tocar charlas reales.

    python -m pruebas.probar_vista            # los chequeos
    python -m pruebas.probar_vista --mutar    # rompe cada candado y exige que se note

Arma una charla de mentira en una carpeta temporal. Lo que importa cuidar:
  · que aparezca lo que la sesión creó, abrió o nombró, y lo que le mandaste vos;
  · que NO aparezca lo que devolvió una herramienta (un Glob con cien capturas) ni lo que
    traen los avisos del sistema;
  · que solo se sirva un archivo que ESA charla nombró, pedido por código y no por ruta;
  · que otra página no pueda pedirlo ni embeberlo, y que un SVG no pueda correr nada;
  · que lo que la charla agrega después aparezca (se lee solo lo nuevo, pero se lee);
  · ELIMINAR: "quitar" no toca el archivo y se deshace; "papelera" solo sobre lo de esta charla
    y nunca en un disco sin papelera (ahí sería borrar para siempre).
⚠ La papelera es de MENTIRA (borra adentro de la carpeta temporal): la de verdad se probó a mano
con un archivo de prueba y quedó en la Papelera de Windows.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.voz import vista

OK, MAL = [], []


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {detalle}")


def renglon(tipo, contenido, **extra):
    d = {"type": tipo, "timestamp": "2026-11-16T10:00:00Z", "message": {"content": contenido}}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False) + "\n"


def correr():
    OK.clear(); MAL.clear()
    vista._CACHE.clear()
    tmp = Path(tempfile.mkdtemp(prefix="vista_"))
    proyectos = tmp / "projects"; (proyectos / "aplanada").mkdir(parents=True)
    proyecto = tmp / "mi proyecto"; (proyecto / "docs").mkdir(parents=True)
    vista.CLAUDE_PROYECTOS = proyectos
    vista.carpeta_de = lambda cwd: proyectos / "aplanada"
    vista.VISTA_QUITADOS = tmp / "quitados.json"
    a_la_basura = []
    vista._a_la_papelera = lambda r: (a_la_basura.append(r), Path(r).unlink())
    vista._disco_con_papelera = lambda r: "sinpapelera" not in str(r)
    cwd = str(proyecto)

    def archivo(nombre, datos=b"x"):
        p = proyecto / nombre
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(datos)
        return p

    creado = archivo("docs/informe final.pdf", b"%PDF-1.4 hola")
    abierta = archivo("captura.png", b"\x89PNG")
    tuya = archivo("del celular.jpg")
    nombrada = archivo("docs/plano.pdf")
    del_glob = archivo("pruebas/montón.png")
    del_aviso = archivo("aviso.png")
    del_resumen = archivo("resumen.png")
    dibujo = archivo("dibujo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
    ajeno = archivo("ajeno.pdf")              # existe en el disco, pero la charla nunca lo nombra
    texto = archivo("notas.txt")
    sin_papelera = archivo("sinpapelera/foto.png")
    para_tirar = archivo("para tirar.png")

    sid = "charla-1"
    jl = proyectos / "aplanada" / (sid + ".jsonl")
    jl.write_text(
        renglon("assistant", [{"type": "tool_use", "name": "Write",
                               "input": {"file_path": str(creado), "content": "…"}}]) +
        renglon("assistant", [{"type": "tool_use", "name": "Read", "input": {"file_path": str(abierta)}}]) +
        renglon("user", f"[Te paso una imagen; está guardada en {tuya} — abrila] mirá esto") +
        renglon("assistant", [{"type": "text", "text": "Te dejé el plano en docs/plano.pdf y el dibujo en "
                                                       f"{dibujo}. También {proyecto}\\no-existe.pdf."}]) +
        renglon("user", [{"type": "tool_result", "content": f"{del_glob}\n{ajeno}"}]) +
        renglon("user", [{"type": "text", "text": f"<system-reminder>mirá {del_aviso}</system-reminder>hola"}]) +
        renglon("user", f"resumen viejo: {del_resumen}", isCompactSummary=True) +
        renglon("assistant", [{"type": "text", "text": f"y {texto} no es una imagen"}]) +
        renglon("assistant", [{"type": "tool_use", "name": "Read", "input": {"file_path": str(sin_papelera)}}]) +
        renglon("assistant", [{"type": "tool_use", "name": "Read", "input": {"file_path": str(para_tirar)}}]),
        encoding="utf-8")

    lista = vista.lista(cwd, sid)
    por = {Path(a["ruta"]).name: a for a in lista}
    chequeo("lo que la sesión escribió: creó", por.get("informe final.pdf", {}).get("como") == "creó", list(por))
    chequeo("ruta con espacios", "informe final.pdf" in por)
    chequeo("lo que la sesión abrió: abrió", por.get("captura.png", {}).get("como") == "abrió", list(por))
    chequeo("lo que mandaste vos: tuya", por.get("del celular.jpg", {}).get("como") == "tuya", list(por))
    chequeo("ruta relativa en el texto", por.get("plano.pdf", {}).get("como") == "nombró", list(por))
    chequeo("dos rutas en un renglón", "dibujo.svg" in por and "plano.pdf" in por)
    chequeo("lo que no existe no aparece", "no-existe.pdf" not in por)
    chequeo("la salida de una herramienta no cuenta", "montón.png" not in por and "ajeno.pdf" not in por, list(por))
    chequeo("los avisos del sistema no cuentan", "aviso.png" not in por, list(por))
    chequeo("el resumen de una charla compactada no cuenta", "resumen.png" not in por, list(por))
    chequeo("un .txt no es de esta pestaña", "notas.txt" not in por)
    chequeo("tipo pdf / imagen", por.get("plano.pdf", {}).get("tipo") == "pdf"
            and por.get("captura.png", {}).get("tipo") == "imagen")
    chequeo("lo más nuevo primero", lista and Path(lista[0]["ruta"]).name == "para tirar.png",
            [Path(a["ruta"]).name for a in lista])
    chequeo("otra charla no ve nada", vista.lista(cwd, "otra-charla") == [])
    chequeo("un id raro no busca nada", vista.charla_de(cwd, "../../etc") is None)

    # --- lo que la charla agrega después
    nuevo = archivo("después.webp")
    with open(jl, "a", encoding="utf-8") as h:
        h.write(renglon("assistant", [{"type": "tool_use", "name": "Write", "input": {"file_path": str(nuevo)}}]))
    lista2 = vista.lista(cwd, sid)
    chequeo("lo que se agrega después aparece", lista2 and Path(lista2[0]["ruta"]).name == "después.webp",
            [Path(a["ruta"]).name for a in lista2])
    with open(jl, "a", encoding="utf-8") as h:     # un renglón a medio escribir no rompe nada
        h.write('{"type": "assistant", "message": {"content": [{"type": "text", "text": "' + str(ajeno).replace("\\", "\\\\"))
    chequeo("un renglón a medias se espera", "ajeno.pdf" not in {Path(a["ruta"]).name for a in vista.lista(cwd, sid)})

    # --- por HTTP: la puerta y el candado de "solo lo de esta charla"
    app = FastAPI(); app.include_router(vista.crear_router())
    c = TestClient(app, base_url="http://127.0.0.1:8750")
    q = {"cwd": cwd, "sid": sid}
    r = c.get("/vista/lista", params=q)
    chequeo("lista desde el panel: pasa", r.status_code == 200 and len(r.json()["archivos"]) >= 6, r.status_code)
    chequeo("la lista no se guarda en caché", r.headers.get("cache-control") == "no-store")
    ident = vista.id_de(creado)
    r = c.get("/vista/crudo", params={**q, "id": ident}, headers={"sec-fetch-site": "same-origin"})
    chequeo("sirve lo que la charla nombró", r.status_code == 200 and r.content.startswith(b"%PDF"), r.status_code)
    chequeo("el PDF va para mostrar, no para bajar", "attachment" not in r.headers.get("content-disposition", ""),
            r.headers.get("content-disposition"))
    chequeo("el PDF va como PDF", r.headers.get("content-type", "").startswith("application/pdf"),
            r.headers.get("content-type"))
    r = c.get("/vista/crudo", params={**q, "id": vista.id_de(ajeno)})
    chequeo("un archivo que la charla no nombró: no", r.status_code == 404, r.status_code)
    r = c.get("/vista/crudo", params={**q, "id": vista.id_de(texto)})
    chequeo("un .txt nombrado: no", r.status_code == 404, r.status_code)
    r = c.get("/vista/crudo", params={**q, "ruta": str(ajeno)})
    chequeo("pedir por ruta no sirve", r.status_code == 404, r.status_code)
    r = c.get("/vista/crudo", params={"cwd": cwd, "sid": "otra-charla", "id": ident})
    chequeo("el código de otra charla no sirve", r.status_code == 404, r.status_code)
    r = c.get("/vista/crudo", params={**q, "id": vista.id_de(dibujo)})
    chequeo("un SVG va encerrado", "sandbox" in r.headers.get("content-security-policy", ""),
            dict(r.headers))
    r = c.get("/vista/crudo", params={**q, "id": ident}, headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede pedirlo", r.status_code == 403, r.status_code)
    r = c.get("/vista/crudo", params={**q, "id": ident}, headers={"sec-fetch-site": "cross-site"})
    chequeo("otra página no puede embeberlo", r.status_code == 403, r.status_code)
    r = c.get("/vista/lista", params=q, headers={"host": "atacante.com"})
    chequeo("un nombre que no es de esta máquina no pasa", r.status_code == 403, r.status_code)
    r = c.get("/vista/lista", params={"cwd": cwd, "sid": ""})
    chequeo("sin charla: lista vacía", r.status_code == 200 and r.json()["archivos"] == [])

    # --- quitar de la lista
    nombres = lambda: {Path(a["ruta"]).name for a in vista.lista(cwd, sid)}
    id_cap = vista.id_de(abierta)
    r = c.post("/vista/quitar", json={**q, "id": id_cap}, headers={"origin": "http://127.0.0.1:8750"})
    chequeo("quitar: ok", r.status_code == 200 and r.json().get("ok"), r.text)
    chequeo("quitar: deja de verse", "captura.png" not in nombres(), nombres())
    chequeo("quitar: el archivo sigue en el disco", abierta.exists())
    chequeo("quitar: solo en esta charla", "captura.png" in {Path(a["ruta"]).name for a in vista.lista(cwd, sid, True)})
    chequeo("quitado se sigue pudiendo abrir aparte",
            c.get("/vista/crudo", params={**q, "id": id_cap}).status_code == 200)
    r = c.post("/vista/devolver", json={**q, "id": id_cap})
    chequeo("devolver lo trae de vuelta", r.json().get("ok") and "captura.png" in nombres(), nombres())
    r = c.post("/vista/quitar", json={**q, "id": vista.id_de(ajeno)})
    chequeo("no se quita lo que la charla no nombró", not r.json().get("ok"))
    r = c.post("/vista/quitar", json={**q, "id": id_cap}, headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede quitar", r.status_code == 403, r.status_code)

    # --- mandar a la papelera
    r = c.post("/vista/papelera", json={**q, "id": vista.id_de(para_tirar)}, headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede mandar a la papelera", r.status_code == 403 and para_tirar.exists(), r.status_code)
    r = c.post("/vista/papelera", json={**q, "id": vista.id_de(para_tirar)}, headers={"sec-fetch-site": "same-origin"})
    chequeo("papelera: ok", r.json().get("ok"), r.text)
    chequeo("papelera: pasó por la papelera, no por un borrado", a_la_basura == [para_tirar], a_la_basura)
    chequeo("papelera: deja de verse", "para tirar.png" not in nombres())
    r = c.post("/vista/papelera", json={**q, "id": vista.id_de(ajeno)})
    chequeo("papelera: lo que la charla no nombró no se toca", not r.json().get("ok") and ajeno.exists())
    r = c.post("/vista/papelera", json={**q, "id": vista.id_de(sin_papelera)})
    chequeo("papelera: en un disco sin papelera se niega", not r.json().get("ok") and sin_papelera.exists(), r.text)
    r = c.post("/vista/papelera", json={"cwd": cwd, "sid": "otra-charla", "id": vista.id_de(creado)})
    chequeo("papelera: el código de otra charla no sirve", not r.json().get("ok") and creado.exists())
    return not MAL


def mutaciones():
    """Rompe cada candado y exige que la prueba se ponga roja."""
    orig = {k: getattr(vista, k) for k in ("_de_un_renglon", "buscar", "_puerta", "_de_otro_sitio",
                                           "CAB_SVG", "AVISO_SISTEMA", "_leer_nuevo", "ABSOLUTA",
                                           "a_la_papelera", "quitar")}
    import re

    def con_resultados(d, cwd):
        sale = orig["_de_un_renglon"](d, cwd)
        for it in ((d.get("message") or {}).get("content") or []):
            if isinstance(it, dict) and it.get("type") == "tool_result":
                sale += [(r, "nombró") for r in vista._rutas_en(str(it.get("content")), cwd)]
        return sale

    def por_ruta(cwd, sid, ident):
        for p in Path(cwd).rglob("*"):
            if p.is_file() and vista.id_de(p) == ident:
                return p
        return None

    def sin_releer(archivo, cwd):
        est = vista._CACHE.get(str(archivo))
        return est["items"] if est else orig["_leer_nuevo"](archivo, cwd)

    casos = {
        "lee lo que devuelven las herramientas": lambda: setattr(vista, "_de_un_renglon", con_resultados),
        "sirve cualquier archivo del disco": lambda: setattr(vista, "buscar", por_ruta),
        "sin puerta": lambda: setattr(vista, "_puerta", lambda *a, **k: ""),
        "sin mirar Sec-Fetch-Site": lambda: setattr(vista, "_de_otro_sitio", lambda cab: ""),
        "SVG sin encerrar": lambda: setattr(vista, "CAB_SVG", {}),
        "los avisos del sistema cuentan": lambda: setattr(vista, "AVISO_SISTEMA", re.compile(r"(?!x)x")),
        "no relee lo nuevo": lambda: setattr(vista, "_leer_nuevo", sin_releer),
        "la papelera no mira el disco": lambda: setattr(vista, "a_la_papelera",
            lambda cwd, sid, i: orig["a_la_papelera"](cwd, sid, i, _hay_papelera=lambda r: True)),
        "quitar borra el archivo": lambda: setattr(vista, "quitar",
            lambda cwd, sid, i: ((vista.buscar(cwd, sid, i) or Path("x")).unlink(missing_ok=True),
                                 orig["quitar"](cwd, sid, i))[1]),
        "rutas sin espacios": lambda: setattr(vista, "ABSOLUTA", re.compile(
            r"(?<![A-Za-z0-9])([A-Za-z]:[\\/][^\s\"<>|*?`'\[\]()]*?\.(?:pdf|png|jpe?g|gif|webp|bmp|svg))(?![A-Za-z0-9])", re.I)),
    }
    cazadas = 0
    for nombre, romper in casos.items():
        romper()
        with contextlib.redirect_stdout(io.StringIO()):
            paso = correr()
        for k, v in orig.items():
            setattr(vista, k, v)
        print(f"  mutación «{nombre}»: {'CAZADA' if not paso else 'NO SE NOTÓ ✗'}")
        cazadas += not paso
    return cazadas == len(casos)


if __name__ == "__main__":
    bien = correr()
    print(f"vista: {len(OK)} bien, {len(MAL)} mal")
    if "--mutar" in sys.argv:
        bien = mutaciones() and bien
    sys.exit(0 if bien else 1)
