"""Prueba de "Enlaces y archivos" (`app/voz/fijados.py`), sin abrir ninguna ventana.

    python -m pruebas.probar_fijados            # los chequeos
    python -m pruebas.probar_fijados --mutar    # rompe cada candado y exige que se note

Usa un archivo de datos temporal: no toca la lista real de Martin. Lo que importa cuidar:
  · que "abrir" nunca EJECUTE un programa (un .exe se muestra en el Explorador);
  · que solo se abra lo que ya esta en la lista, por id;
  · que otra pagina no pueda usar las rutas (la puerta de la terminal);
  · que cada carpeta tenga su lista y que no se cuele nada que no sea http/https.
"""
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.voz import fijados

OK, MAL = [], []


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {detalle}")


def correr():
    OK.clear(); MAL.clear()
    tmp = Path(tempfile.mkdtemp(prefix="fijados_"))
    fijados.FIJADOS = tmp / "fijados.json"
    proyecto = tmp / "proyecto"; proyecto.mkdir()
    otro = tmp / "otro"; otro.mkdir()
    (proyecto / "notas.txt").write_text("hola", encoding="utf-8")
    (proyecto / "instalar.exe").write_bytes(b"MZ")
    (proyecto / "atajo.lnk").write_bytes(b"L")
    cwd = str(proyecto)

    # --- interpretar lo pegado
    r, _ = fijados.interpretar("https://github.com/JonesMartin1/wpp-transcriptor", cwd)
    chequeo("enlace https", r and r[0] == "enlace" and r[2] == "github.com/JonesMartin1", r)
    r, _ = fijados.interpretar("www.google.com", cwd)
    chequeo("www sin esquema pasa a https", r and r[1] == "https://www.google.com", r)
    for malo in ("javascript:alert(1)", "file:///C:/Windows/notepad.exe", "data:text/html,x",
                 "ftp://x.com/a"):
        r, motivo = fijados.interpretar(malo, cwd)
        chequeo(f"rechaza {malo.split(':')[0]}", r is None and motivo, r)
    r, _ = fijados.interpretar('"' + str(proyecto / "notas.txt") + '"', cwd)
    chequeo("ruta con comillas (Copiar como ruta)", r and r[0] == "archivo" and r[2] == "notas.txt", r)
    r, _ = fijados.interpretar("notas.txt", cwd)
    chequeo("ruta relativa a la carpeta", r and Path(r[1]) == (proyecto / "notas.txt").resolve(), r)
    r, _ = fijados.interpretar(str(otro), cwd)
    chequeo("carpeta", r and r[0] == "carpeta", r)
    r, motivo = fijados.interpretar(str(proyecto / "no_existe.pdf"), cwd)
    chequeo("archivo inexistente se rechaza", r is None and "encuentro" in motivo, motivo)

    # --- agregar, repetir, listar por carpeta
    a = fijados.agregar(cwd, "https://claude.ai/code")
    chequeo("agregar enlace", a["ok"] and a["item"]["tipo"] == "enlace", a)
    b = fijados.agregar(cwd, str(proyecto / "notas.txt"))
    e = fijados.agregar(cwd, str(proyecto / "instalar.exe"))
    l = fijados.agregar(cwd, str(proyecto / "atajo.lnk"))
    rep = fijados.agregar(cwd.upper(), "https://claude.ai/code")
    chequeo("repetido no se duplica (misma carpeta escrita distinto)",
            rep["ok"] and rep.get("repetido"), rep)
    chequeo("lista de la carpeta", len(fijados.lista(cwd)) == 4, fijados.lista(cwd))
    chequeo("otra carpeta tiene su propia lista", fijados.lista(str(otro)) == [])
    chequeo("nombre propio se respeta",
            fijados.agregar(str(otro), "https://x.com", nombre="Mi enlace")["item"]["nombre"] == "Mi enlace")

    # --- abrir: solo por id, nunca ejecuta
    abiertos, mostrados = [], []
    ab = lambda c, i: fijados.abrir(c, i, _abrir=abiertos.append, _mostrar=mostrados.append)
    r = ab(cwd, b["item"]["id"])
    chequeo("abrir un .txt lo abre", r["ok"] and r["como"] == "abierto" and len(abiertos) == 1, r)
    for nom, it in (("exe", e), ("lnk", l)):
        antes = len(abiertos)
        r = ab(cwd, it["item"]["id"])
        chequeo(f"un .{nom} NO se ejecuta: se muestra en el Explorador",
                r["ok"] and r["como"] == "mostrado" and len(abiertos) == antes, r)
    r = ab(cwd, a["item"]["id"])
    chequeo("un enlace no lo abre el panel", not r["ok"], r)
    r = ab(cwd, "inventado")
    chequeo("un id que no está no abre nada", not r["ok"] and len(abiertos) == 1, r)
    r = ab(str(otro), b["item"]["id"])
    chequeo("el id de otra carpeta no abre nada", not r["ok"], r)
    (proyecto / "notas.txt").unlink()
    chequeo("archivo borrado: la lista lo marca", any(f.get("existe") is False for f in fijados.lista(cwd)))
    r = ab(cwd, b["item"]["id"])
    chequeo("archivo borrado: abrir avisa", not r["ok"] and "ya no está" in r["error"], r)

    # --- el apartado de la SESION: separado del proyecto y de las otras sesiones
    s1 = fijados.agregar(cwd, "https://tarea.com/123", sid="ses-uno", ambito="sesion")
    chequeo("agregar a la sesión", s1["ok"], s1)
    chequeo("lo de la sesión no aparece en el proyecto",
            all(f["destino"] != "https://tarea.com/123" for f in fijados.lista(cwd)))
    chequeo("la sesión ve lo suyo", [f["destino"] for f in fijados.lista(cwd, "ses-uno", "sesion")]
            == ["https://tarea.com/123"])
    chequeo("otra sesión no lo ve", fijados.lista(cwd, "ses-dos", "sesion") == [])
    sa = fijados.agregar(cwd, str(proyecto / "instalar.exe"), sid="ses-uno", ambito="sesion")
    antes = len(abiertos)
    r = fijados.abrir(cwd, sa["item"]["id"], "ses-uno", "sesion",
                      _abrir=abiertos.append, _mostrar=mostrados.append)
    chequeo("en la sesión tampoco se ejecuta un .exe", r.get("como") == "mostrado" and len(abiertos) == antes, r)
    r = fijados.abrir(cwd, sa["item"]["id"], "ses-dos", "sesion", _abrir=abiertos.append, _mostrar=mostrados.append)
    chequeo("el id de una sesión no abre desde otra", not r["ok"], r)
    r = fijados.abrir(cwd, sa["item"]["id"], _abrir=abiertos.append, _mostrar=mostrados.append)
    chequeo("el id de la sesión no abre desde el proyecto", not r["ok"], r)
    r = fijados.agregar(cwd, "https://x.com", sid="", ambito="sesion")
    chequeo("charla sin id: no hay apartado de sesión", not r["ok"] and "arrancó" in r["error"], r)
    r = fijados.agregar(cwd, "https://x.com", sid="../../etc", ambito="sesion")
    chequeo("un sid raro se rechaza", not r["ok"], r)
    chequeo("quitar de la sesión", fijados.quitar(cwd, s1["item"]["id"], "ses-uno", "sesion")["ok"]
            and len(fijados.lista(cwd, "ses-uno", "sesion")) == 1)

    # --- quitar
    q = fijados.quitar(cwd, a["item"]["id"])
    chequeo("quitar", q["ok"] and len(fijados.lista(cwd)) == 3, q)
    chequeo("quitar dos veces avisa", not fijados.quitar(cwd, a["item"]["id"])["ok"])

    # --- la puerta, por HTTP
    app = FastAPI(); app.include_router(fijados.crear_router())
    c = TestClient(app, base_url="http://127.0.0.1:8750")
    q = {"cwd": cwd}
    chequeo("desde el panel: pasa", c.get("/fijados", params=q).status_code == 200)
    d = c.get("/fijados", params={"cwd": cwd, "sid": "ses-uno"}).json()
    chequeo("GET trae los dos apartados", isinstance(d.get("proyecto"), list) and len(d.get("sesion") or []) == 1, d)
    chequeo("GET sin sid: sesion vacía (null)", c.get("/fijados", params=q).json().get("sesion") is None)
    r = c.post("/fijados/agregar", json={"cwd": cwd, "sid": "ses-tres", "ambito": "sesion",
                                         "texto": "https://por-http.com"}).json()
    chequeo("agregar a la sesión por HTTP", r.get("ok") and
            fijados.lista(cwd, "ses-tres", "sesion")[0]["destino"] == "https://por-http.com", r)
    chequeo("con Origin del panel: pasa", c.post("/fijados/agregar", json={"cwd": cwd, "texto": "https://a.com"},
            headers={"origin": "http://127.0.0.1:8750"}).json().get("ok"))
    r = c.post("/fijados/abrir", json={"cwd": cwd, "id": e["item"]["id"]},
               headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede abrir", r.status_code == 403, r.status_code)
    r = c.post("/fijados/agregar", json={"cwd": cwd, "texto": "https://b.com"},
               headers={"origin": "https://pagina-mala.com"})
    chequeo("otra página no puede agregar", r.status_code == 403, r.status_code)
    r = c.get("/fijados", params=q, headers={"host": "atacante.com"})
    chequeo("un nombre que no es de esta máquina no pasa", r.status_code == 403, r.status_code)
    r = c.post("/fijados/abrir", json={"cwd": cwd, "ruta": str(proyecto / "instalar.exe")})
    chequeo("abrir por ruta (sin id) no hace nada", not r.json().get("ok"), r.json())
    return not MAL


def mutaciones():
    """Rompe cada candado y exige que la prueba se ponga roja."""
    casos = {
        "abrir ejecuta programas": lambda: setattr(fijados, "TIPOS_QUE_EJECUTAN", set()),
        "sin puerta": lambda: setattr(fijados, "_puerta", lambda *a, **k: ""),
        "acepta javascript:": lambda: setattr(fijados, "interpretar",
                                             (lambda orig: lambda t, c="": (("enlace", t, "x"), "")
                                              if t.startswith("javascript:") else orig(t, c))(fijados.interpretar)),
    }
    cazadas = 0
    for nombre, romper in casos.items():
        guardado = {k: getattr(fijados, k) for k in ("TIPOS_QUE_EJECUTAN", "_puerta", "interpretar")}
        romper()
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            paso = correr()
        for k, v in guardado.items():
            setattr(fijados, k, v)
        print(f"  mutación «{nombre}»: {'CAZADA' if not paso else 'NO SE NOTÓ ✗'}")
        cazadas += not paso
    return cazadas == len(casos)


if __name__ == "__main__":
    bien = correr()
    print(f"fijados: {len(OK)} bien, {len(MAL)} mal")
    if "--mutar" in sys.argv:
        bien = mutaciones() and bien
    sys.exit(0 if bien else 1)
