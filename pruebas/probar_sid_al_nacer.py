"""Una charla NUEVA avisa su id apenas nace, sin esperar a que termine el primer turno.

El bug que trajo Martin el 2026-08-23 con una captura: abris una pestaña nueva, mandas
el primer mensaje con una imagen, y la pantalla se queda en "Sin mensajes todavia" con
la burbuja de pensando durante TODO el turno — siete minutos — aunque la sesion ya
estuviera contestando avances. Pasaba porque la pestaña recien se enteraba del id de
verdad cuando el turno entero volvia: hasta entonces preguntaba por el chat con el id
vacio y no habia nada que leer.

Se prueba con el CLI de mentira (`cli_falso_sesion.py`): no se habla con Claude, no se
gasta un token y no se toca ningun archivo del proyecto.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_sid_al_nacer
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

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


def probar_claude(cwd):
    print("\n1) El id llega en el MEDIO del primer turno, no al final")
    avisos, fin = [], {}

    def al_nacer(sid):
        avisos.append((sid, time.time()))

    def turno():
        try:
            r, sid = sm.mandar(cwd, "", "lento", al_nacer=al_nacer)
            fin["sid"], fin["cuando"] = sid, time.time()
        except Exception as e:
            fin["error"] = str(e)

    h = threading.Thread(target=turno, daemon=True)
    h.start()
    hasta = time.time() + 25
    while not avisos and time.time() < hasta:
        time.sleep(0.05)
    ok(bool(avisos), "avisa el id de la charla que nace")
    sigue = "sid" not in fin
    ok(sigue, "y lo avisa MIENTRAS el turno todavia corre (ese era el bug)")
    h.join(timeout=25)
    ok(fin.get("sid") and fin["sid"] == avisos[0][0],
       "el id avisado es el mismo que devuelve el turno al terminar")
    ok(len(avisos) == 1, "se avisa una sola vez, no una por mensaje del CLI")
    ok(not sm.PARTOS, "al terminar el turno no queda ningun parto anotado")
    return fin.get("sid") or ""


def probar_parar_recien_nacida(cwd):
    print("\n2) Parar encuentra el proceso por el id NUEVO, en pleno primer turno")
    avisos, fin = [], {}

    def turno():
        try:
            sm.mandar(cwd, "", "largo", al_nacer=lambda s: avisos.append(s))
            fin["ok"] = True
        except Exception as e:
            fin["error"] = str(e)

    h = threading.Thread(target=turno, daemon=True)
    h.start()
    hasta = time.time() + 25
    while not avisos and time.time() < hasta:
        time.sleep(0.05)
    ok(bool(avisos), "la charla larga tambien avisa su id al nacer")
    sid = avisos[0] if avisos else "x"
    ok(sm.EN_CURSO.get(sm._clave(cwd, "")) is not None,
       "el proceso sigue anotado con la clave con la que arranco")
    ok(sm._otra_clave(sid) == sm._clave(cwd, ""),
       "y queda emparejado con su id de verdad, para que Parar lo encuentre")
    ok(sm.parar(cwd, sid) is True, "Parar por el id NUEVO corta el turno")
    h.join(timeout=25)
    ok(fin.get("error") == "parado", "el turno vuelve cortado, no fallado")
    ok(not sm.PARTOS, "y el parto quedo olvidado")


def probar_panel():
    print("\n3) El panel publica ese id en la ficha del trabajo, en el acto")
    import panel
    from app.voz import sesiones_movil
    visto = {}
    original = sesiones_movil.mandar
    try:
        def falso(cwd, sid, texto, modelo="", cerebro="", esfuerzo="", velocidad="",
                  al_nacer=None):
            al_nacer("sid-real")
            # Mirando la ficha DESDE ADENTRO del turno: si el id ya esta publicado, la
            # pantalla lo puede ver mientras la sesion piensa.
            with panel._TRABAJOS_CANDADO:
                visto["ficha"] = panel._TRABAJOS_MOVIL["t1"].get("sid_nuevo")
            with panel._TURNOS_CANDADO:
                visto["candado"] = "sid-real" in panel._TURNOS_ABIERTOS
            return "listo", "sid-real"
        sesiones_movil.mandar = falso
        panel._TRABAJOS_MOVIL["t1"] = {
            "id": "t1", "estado": "trabajando", "cwd": "X", "sid": "",
            "sid_nuevo": "", "creado": time.time(), "terminado": None}
        panel._correr_trabajo_movil("t1", "X", "", "hola", "", "")
        t = panel._TRABAJOS_MOVIL.pop("t1")
        ok(visto.get("ficha") == "sid-real",
           "la ficha del trabajo ya tenia el id mientras el turno corria")
        ok(visto.get("candado") is True,
           "y la charla recien nacida cuenta como ocupada (no se le puede mandar otro)")
        ok(t["estado"] == "terminado" and t["sid_nuevo"] == "sid-real",
           "al terminar, la ficha queda igual que siempre")
        with panel._TURNOS_CANDADO:
            ok("sid-real" not in panel._TURNOS_ABIERTOS,
               "y el candado se suelta al terminar")
    finally:
        sesiones_movil.mandar = original


def probar_pantalla():
    print("\n4) Lo que la pantalla tiene que hacer con ese id")
    js = Path("app/estaticos/sesiones.html").read_text(encoding="utf-8")
    ok("function mudarPestana(" in js, "la mudanza de id vive en una sola funcion")
    ok("e.sid_nuevo && e.sid_nuevo !== clave" in js,
       "la pestaña se muda apenas el trabajo publica el id")
    ok("if (!clave.startsWith('nueva-')) f.append('segundo_plano'" not in js,
       "las charlas nuevas ya no van por el camino directo")
    movil = Path("panel.py").read_text(encoding="utf-8")
    ok("const mudarA = (sidNuevo, extras)" in movil,
       "la pantalla del celular tiene la misma mudanza en una sola funcion")
    ok("if (e.sid_nuevo) mudarA(e.sid_nuevo, null);" in movil,
       "y tambien se muda apenas el trabajo publica el id")
    ok("if (!p.virgen) f.append('segundo_plano', '1');" not in movil,
       "en el celular las charlas nuevas tampoco van por el camino directo")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sid_al_nacer_"))
    preparar(tmp)
    cwd = str(tmp)
    try:
        probar_claude(cwd)
        limpiar()
        probar_parar_recien_nacida(cwd)
        limpiar()
        probar_panel()
        probar_pantalla()
    finally:
        limpiar()
    print("\n%d bien, %d mal" % (len(VERDES), len(ROJOS)))
    for r in ROJOS:
        print("  FALLA:", r)
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
