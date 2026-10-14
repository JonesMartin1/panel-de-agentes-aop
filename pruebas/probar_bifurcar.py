"""Bifurcar una charla (2026-09-27): probar otro camino sin perder la original.

El primer mensaje de una pestaña "copia" arranca el proceso con
`--resume <original> --fork-session`, que sigue la charla con un id NUEVO. Que el CLI de
verdad lo haga asi (recuerda, id nuevo, original intacta) se midio con
`sonda_bifurcar.py`. Aca se prueba lo del panel con el CLI de mentira, sin gastar tokens.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_bifurcar
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_bifurcar --mutar
"""
import inspect
import sys
import tempfile
import textwrap
from pathlib import Path

from app.voz import seguir, sesiones_movil as sm

VERDES, ROJOS = [], []


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def preparar(carpeta):
    cli = Path(__file__).with_name("cli_falso_sesion.py")
    cmd = carpeta / "claude_falso.cmd"
    cmd.write_text('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, cli), encoding="utf-8")
    sm._claude_bin = lambda: str(cmd)
    sm.es_codex = lambda sid: sid.startswith("codex-")
    sm.modelo_de = lambda sid: "haiku"
    sm.esfuerzo_de = lambda sid: ""
    sm.contexto = lambda cwd, sid, cola=0: {"tokens": 0}


def limpiar():
    for viva in list(sm.VIVAS.values()):
        try:
            sm._matar_arbol(viva.proc)
        except Exception:
            pass
    sm.VIVAS.clear()
    seguir.PIDS_PANEL.clear()


def correr_todo():
    tmp = Path(tempfile.mkdtemp(prefix="bifurcar_"))
    preparar(tmp)
    cwd = str(tmp)
    try:
        print("\n1) La copia nace de la original, con id propio")
        _, orig = sm.mandar(cwd, "", "hola")
        ok(bool(orig), f"la original existe ({orig})")
        r, copia = sm.mandar(cwd, "", "probemos otro camino", desde=orig)
        ok(copia == "copia-de-" + orig, f"la copia tiene id nuevo, hecho desde la original ({copia})")
        viva = sm.VIVAS.get(copia)
        cmd = " ".join(viva.proc.args) if viva and isinstance(viva.proc.args, list) else str(
            getattr(viva, "proc", None) and viva.proc.args)
        ok("--fork-session" in cmd and ("--resume " + orig) in cmd,
           "el proceso arrancó con --resume <original> --fork-session")
        ok(sm.VIVAS.get(orig) is not None and sm.VIVAS[orig] is not viva,
           "la original sigue con su propio proceso: no se tocó")

        print("\n2) Los mensajes siguientes de la copia siguen en la copia")
        _, otra = sm.mandar(cwd, copia, "seguimos")
        ok(otra == copia, "el segundo mensaje continúa la copia, no crea otra")

        print("\n3) Lo que no se bifurca")
        try:
            sm.mandar(cwd, "", "x", desde="codex-123")
            ok(False, "una charla de Codex no se bifurca")
        except RuntimeError as e:
            ok("Codex" in str(e), "una charla de Codex no se bifurca (lo dice)")
        _, nueva = sm.mandar(cwd, orig, "con sid", desde="otra")
        ok(nueva == orig, "con sid, `desde` se ignora: es un mensaje común a esa charla")
    finally:
        limpiar()


MUTACIONES = {
    "el arranque no bifurca": ("_arrancar_viva",
                               'cmd += ["--resume", desde, "--fork-session"]', "pass"),
    "mandar pierde el desde": ("mandar", 'desde = desde if (desde and not sid) else ""',
                               'desde = ""'),
}


def mutar():
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(sm, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        espacio = dict(vars(sm))
        exec(compile(fuente.replace(viejo, nuevo, 1), sm.__file__, "exec"), espacio)
        setattr(sm, funcion, espacio[funcion])
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
            setattr(sm, funcion, original)
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
