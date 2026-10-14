"""El @ de la caja de escribir (2026-09-27): nombrar un archivo del proyecto como en Claude Code.

Se prueba la busqueda del servidor (`/archivos/buscar`) sobre un proyecto de mentira en una
carpeta temporal, y el detector de "estoy escribiendo un @" de `arroba.js` corriendolo en
node. No toca ningun proyecto real.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_arroba
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_arroba --mutar
"""
import inspect
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

import panel

VERDES, ROJOS = [], []
RAIZ = Path(__file__).resolve().parent.parent


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def armar():
    tmp = Path(tempfile.mkdtemp(prefix="arroba_"))
    for r in ("panel.py", "app/voz/sesiones_movil.py", "app/estaticos/sesiones.html",
              "pruebas/probar_panel.py", "docs/Panel de control.md", "README.md",
              "node_modules/panel/index.js", ".git/panel.pack"):
        (tmp / r).parent.mkdir(parents=True, exist_ok=True)
        (tmp / r).write_text("x", encoding="utf-8")
    return tmp


def correr_todo():
    tmp = armar()
    original = panel._arbol_raiz
    panel._arbol_raiz = lambda cwd: tmp if cwd == "conocida" else None
    panel._ARROBA_CACHE.clear()
    cliente = TestClient(panel.app)
    buscar = lambda q, cwd="conocida": cliente.get("/archivos/buscar",
                                                   params={"cwd": cwd, "q": q}).json()
    try:
        print("\n1) Lo que sugiere, en un orden que tenga sentido")
        r = buscar("pan")["archivos"]
        ok(r[:1] == ["panel.py"], f"'pan' pone primero panel.py ({r[:3]})")
        ok(r.index("docs/Panel de control.md") < r.index("pruebas/probar_panel.py"),
           "el que EMPIEZA con 'pan' va antes que el que solo lo contiene")
        ok(buscar("smov")["archivos"][:1] == ["app/voz/sesiones_movil.py"],
           "las letras salteadas, en orden, encuentran igual ('smov' → sesiones_movil.py)")
        ok(buscar("zzz")["archivos"] == [], "si no hay nada, lista vacía")

        print("\n2) No se mete donde no tiene que meterse")
        todos = buscar("")["archivos"]
        ok(not any(x.startswith(("node_modules/", ".git/")) for x in todos),
           "saltea node_modules y .git")
        ok(buscar("pan", cwd="C:/Windows") == {"ok": False, "archivos": []},
           "una carpeta que el panel no conoce no se busca")

        print("\n2b) En un repo de git respeta el .gitignore, como Claude Code")
        (tmp / "logs").mkdir(exist_ok=True)
        (tmp / "logs" / "panel.log").write_text("x", encoding="utf-8")
        (tmp / ".gitignore").write_text("logs/\nnode_modules/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(tmp)], capture_output=True)
        panel._ARROBA_CACHE.clear()
        r = buscar("pan")["archivos"]
        ok("logs/panel.log" not in r and "panel.py" in r,
           f"lo ignorado por git no se sugiere ({r[:4]})")
    finally:
        panel._arbol_raiz = original
        panel._ARROBA_CACHE.clear()

    print("\n3) arroba.js sabe cuándo estás escribiendo un @")
    js = (RAIZ / "app/estaticos/arroba.js").as_posix()
    casos = ["mirá @pan", "@", "mail@dominio.com", "ya puse @panel.py y sigo", "hola"]
    prog = ("global.window={};global.document={createElement:()=>({}),head:{appendChild(){}}};"
            "require(%r);const f=window.Arroba._arrobaActual;"
            "console.log(JSON.stringify(%s.map(v=>{const r=f({value:v,selectionStart:v.length});"
            "return r?r.q:null})))" % (js, json.dumps(casos)))
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8")
    salida = json.loads(r.stdout) if r.returncode == 0 else None
    ok(salida == ["pan", "", None, None, None],
       "abre con '@pan' y '@', no con un mail ni con un @ ya terminado"
       + ("" if salida else f" (node: {r.stderr[:200]})"))


MUTACIONES = {
    "sin saltear carpetas ocultas y pesadas": (
        "_arroba_indice",
        "dirs[:] = sorted(d for d in dirs if d not in ARBOL_ESCONDIDO and not d.startswith(\".\"))",
        "dirs[:] = sorted(dirs)"),
    "el nombre no pesa más que la ruta": ("_arroba_puntaje", "return (0, len(r))", "return (2, len(r))"),
}


def mutar():
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(panel, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        espacio = dict(vars(panel))
        exec(compile(fuente.replace(viejo, nuevo, 1), panel.__file__, "exec"), espacio)
        setattr(panel, funcion, espacio[funcion])
        antes = len(ROJOS)
        silencio = sys.stdout
        sys.stdout = open("nul" if sys.platform == "win32" else "/dev/null", "w")
        try:
            correr_todo()
        except Exception:
            ROJOS.append("excepcion")
        finally:
            sys.stdout.close()
            sys.stdout = silencio
            setattr(panel, funcion, original)
        cayo = len(ROJOS) > antes
        del ROJOS[antes:]
        caidas += cayo
        print(("  ok   " if cayo else "  FALLA ") + f"mutacion cazada: {nombre}")
        if not cayo:
            ROJOS.append("mutacion no cazada: " + nombre)
    return caidas


def main():
    correr_todo()
    if "--mutar" in sys.argv and not ROJOS:
        print("\n=== Las mutaciones: cada pieza tiene que poder fallar ===")
        n = mutar()
        print(f"\n{n} de {len(MUTACIONES)} mutaciones cazadas")
    print(f"\n{len(VERDES)} bien, {len(ROJOS)} mal")
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
