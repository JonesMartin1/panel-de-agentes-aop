"""El proceso de una sesion del panel VIVE ENTRE TURNOS (arreglo del 2026-08-20).

El bug que trajo Martin desde otro proyecto: cada mensaje arrancaba su propio `claude -p`, y
al terminar el turno se le cerraba el stdin y se le mataba el arbol. Todo lo que la
sesion hubiera mandado a segundo plano (un `npm run build`) moria a mitad de camino, y
el turno siguiente se encontraba con "No completion record was found for this background
shell command from the previous session".

Aca se prueba con un CLI de mentira (`cli_falso_sesion.py`, lanzado por un .cmd como el
`claude` real de Windows): no se habla con Claude, no se gasta un token y no se toca
ningun archivo del proyecto.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_sesion_persistente
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

from app.voz import seguir, sesiones_movil as sm

VERDES, ROJOS = [], []


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def preparar(carpeta):
    """Un `claude` falso: un .cmd que lanza python, igual que el de Windows."""
    cli = Path(__file__).with_name("cli_falso_sesion.py")
    cmd = carpeta / "claude_falso.cmd"
    cmd.write_text('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, cli),
                   encoding="utf-8")
    sm._claude_bin = lambda: str(cmd)
    sm.es_codex = lambda sid: False
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


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sesion_persistente_"))
    preparar(tmp)
    cwd = str(tmp)
    hijo_fondo = 0
    try:
        print("\n1) La charla nace y el proceso queda prendido")
        r1, sid = sm.mandar(cwd, "", "hola")
        ok(bool(sid), "la sesion nueva devuelve su id (%s)" % sid)
        ok("turno 1" in r1, "contesta el primer turno")
        viva = sm.VIVAS.get(sid)
        ok(viva is not None, "el proceso quedo registrado con el id nuevo")
        ok(viva is not None and viva.viva(), "y sigue VIVO despues del turno")
        ok(sm._clave(cwd, "") not in sm.VIVAS,
           "la clave 'nueva:carpeta' quedo libre para la proxima pestana")
        pid1 = viva.proc.pid
        ok(pid1 in seguir.PIDS_PANEL, "el pid se avisa para que no cuente como 'abierta'")

        print("\n2) El segundo mensaje entra al MISMO proceso")
        r2, sid2 = sm.mandar(cwd, sid, "de nuevo")
        ok(sid2 == sid, "sigue siendo la misma conversacion")
        ok("turno 2" in r2, "el CLI cuenta dos turnos: es el mismo proceso vivo")
        ok(sm.VIVAS[sid].proc.pid == pid1, "y el pid no cambio")
        ok(sm.EN_CURSO.get(sid) is None, "al terminar, la sesion no queda 'ocupada'")

        print("\n3) ** Lo del bug: lo mandado a segundo plano sobrevive al turno")
        rf, _ = sm.mandar(cwd, sid, "fondo")
        hijo_fondo = int(rf.split()[-1])
        ok(psutil.pid_exists(hijo_fondo), "el turno dejo un hijo corriendo")
        rm, _ = sm.mandar(cwd, sid, "mirar")
        ok(rm == "hijo si", "en el turno SIGUIENTE ese hijo sigue vivo (antes moria)")

        print("\n4) Parar corta el turno pero NO mata el proceso")
        fallo = {}

        def largo():
            try:
                sm.mandar(cwd, sid, "largo")
            except Exception as e:
                fallo["e"] = str(e)
        h = threading.Thread(target=largo, daemon=True)
        h.start()
        hasta = time.time() + 10
        while sm.EN_CURSO.get(sid) is None and time.time() < hasta:
            time.sleep(0.05)
        ok(sm.EN_CURSO.get(sid) is not None, "la sesion figura ocupada mientras piensa")
        ok(sm.parar(cwd, sid) is True, "Parar dice que si habia algo que cortar")
        h.join(timeout=15)
        ok(fallo.get("e") == "parado", "el turno vuelve como 'parado'")
        ok(sm.VIVAS.get(sid) is not None and sm.VIVAS[sid].viva(),
           "** el proceso sigue vivo despues de Parar")
        ok(psutil.pid_exists(hijo_fondo), "y lo de segundo plano tampoco murio")
        r5, _ = sm.mandar(cwd, sid, "seguimos")
        ok("texto seguimos" in r5, "y la charla sigue contestando despues de Parar")

        print("\n5) Cambiar el modelo rearranca (es una bandera de la linea de comando)")
        r6, _ = sm.mandar(cwd, sid, "otra vez", modelo="sonnet")
        ok("turno 1" in r6, "el proceso nuevo arranca su cuenta de cero")
        ok(sm.VIVAS[sid].proc.pid != pid1, "y es otro pid")
        ok(not psutil.pid_exists(pid1), "el viejo se apago")
        ok(pid1 not in seguir.PIDS_PANEL, "y su pid se saco de la lista")

        print("\n6) Apagar a mano (lo que hacen compactar y mudar de cerebro)")
        pid2 = sm.VIVAS[sid].proc.pid
        sm.apagar_sesion(cwd, sid)
        time.sleep(0.5)
        ok(sid not in sm.VIVAS, "la sesion se saca del registro")
        ok(not psutil.pid_exists(pid2), "y su proceso se cierra")

        print("\n7) Dos pestanas nuevas de la misma carpeta no se mezclan")
        ra, sa = sm.mandar(cwd, "", "una")
        rb, sb = sm.mandar(cwd, "", "otra")
        ok(sa != sb, "cada pestana nueva nace con su propia conversacion")
        ok("turno 1" in ra and "turno 1" in rb, "ninguna hereda el turno de la otra")
    finally:
        limpiar()
        if hijo_fondo:
            try:
                psutil.Process(hijo_fondo).kill()
            except Exception:
                pass

    print("\n%d en verde, %d en rojo" % (len(VERDES), len(ROJOS)))
    for r in ROJOS:
        print("  x " + r)
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
