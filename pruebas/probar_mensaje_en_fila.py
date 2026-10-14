"""Escribirle a una charla MIENTRAS trabaja (2026-09-27), como en Claude Code.

El mensaje va al MISMO proceso que esta en pleno turno (`sesiones_movil.encolar`) y el
CLI lo toma en la proxima pausa. Que el CLI de verdad lo acepte y lo lea en el mismo turno
se midio con `sonda_mensaje_en_curso.py` (gasta tokens). Aca se prueba lo del panel con el
CLI de mentira, sin gastar nada:

  - que solo se encole con un turno corriendo, y nunca con una pregunta pendiente;
  - ⚠ el caso borde: si el mensaje llega cuando el turno ya cerraba, el CLI arranca OTRO
    turno con el — el panel tiene que seguir leyendo hasta ese resultado, no perderlo;
  - que el hilo muestre el mensaje en fila (Claude Code lo guarda como `queued_command`);
  - que `/movil/mandar` encole en vez de rechazar "esta contestando algo".

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_mensaje_en_fila
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_mensaje_en_fila --mutar
"""
import inspect
import json
import sys
import tempfile
import textwrap
import threading
import time
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


def pruebas_proceso(cwd):
    print("\n1) Solo se encola con un turno corriendo")
    _, sid = sm.mandar(cwd, "", "hola")
    ok(bool(sid), f"la charla nace ({sid})")
    ok(sm.encolar(cwd, sid, "sin turno")[0] is False,
       "sin turno corriendo no se encola (es un mensaje comun)")

    print("\n2) El caso borde: el mensaje llega cuando el turno ya cerraba")
    salida = {}
    t0 = time.time()
    h = threading.Thread(target=lambda: salida.update(r=sm.mandar(cwd, sid, "lento")))
    h.start()
    time.sleep(0.8)
    ok(sm.en_turno(cwd, sid), "mientras corre, el panel sabe que esta en turno")
    encolado = sm.encolar(cwd, sid, "y ahora esto")
    ok(encolado == (True, ""), f"se encola ({encolado})")
    h.join(timeout=40)
    # ⚠ Si no tachara lo que el CLI ya tomo, igual llegaria a la respuesta correcta, pero
    # 20 s tarde (el resguardo): por eso se mide el tiempo, no solo el texto.
    ok(time.time() - t0 < 12, f"sin esperas de mas ({time.time() - t0:.1f} s)")
    r = (salida.get("r") or ("", ""))[0]
    ok("texto y ahora esto" in r,
       f"el panel siguio leyendo hasta la respuesta del mensaje en fila ({r[:60]!r})")
    ok(sm.VIVAS[sid].encolados == [], "y no queda nada en fila")
    ok(not sm.en_turno(cwd, sid), "al terminar, la charla queda libre")
    _, sid2 = sm.mandar(cwd, sid, "de nuevo")
    ok(sid2 == sid, "el turno siguiente anda normal (no quedo ningun resto)")

    print("\n2b) Le escribís justo mientras la charla sigue SOLA (terminó un subagente)")
    r1, _ = sm.mandar(cwd, sid, "autonomo")
    r2, _ = sm.mandar(cwd, sid, "hola")          # la continuacion sola llega en el medio
    ok("texto hola" in r2 and "continuacion sola" not in r2,
       f"la respuesta es la de TU mensaje, no la de la continuación ({r2[:40]!r})")

    print("\n3) Con una pregunta pendiente no se encola: se contesta arriba")
    viva = sm.VIVAS[sid]
    viva.turno.acquire()
    try:
        with sm._CANDADO_PREGUNTAS:
            sm.PREGUNTAS[sm._clave(cwd, sid)] = {"request_id": "x", "input": {},
                                                  "hora": time.time()}
        bien, motivo = sm.encolar(cwd, sid, "hola")
        ok(bien is False and "preguntando" in motivo, "dice que conteste la pregunta")
    finally:
        with sm._CANDADO_PREGUNTAS:
            sm.PREGUNTAS.pop(sm._clave(cwd, sid), None)
        viva.turno.release()

    print("\n4) Un proceso sin la devolucion de mensajes no recibe nada en fila")
    viva.turno.acquire()
    try:
        viva.con_replay = False
        ok(sm.encolar(cwd, sid, "hola")[0] is False, "sin replay no se encola")
    finally:
        viva.con_replay = True
        viva.turno.release()


def pruebas_hilo():
    print("\n5) El hilo muestra el mensaje en fila (como lo guarda Claude Code)")
    tmp = Path(tempfile.mkdtemp(prefix="fila_hilo_"))
    j = tmp / "x.jsonl"
    lineas = [
        {"type": "user", "message": {"role": "user", "content": "corré las pruebas"}},
        {"type": "attachment", "timestamp": "2026-09-27T20:28:24.729Z", "attachment": {
            "type": "queued_command", "commandMode": "prompt",
            "prompt": [{"type": "text", "text": "y después commiteá"}]}},
    ]
    j.write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    filas = sm._filas_de(j)
    ok([f["texto"] for f in filas if f["de"] == "vos"] == ["corré las pruebas", "y después commiteá"],
       "el mensaje en fila aparece como tuyo, en su lugar")


def pruebas_endpoint():
    print("\n6) /movil/mandar encola en vez de rechazar 'esta contestando'")
    from fastapi.testclient import TestClient
    import panel
    tmp = Path(tempfile.mkdtemp(prefix="fila_ep_"))
    panel.MIS_MENSAJES = tmp / "m.jsonl"
    llamados = []
    viejo_en, viejo_enc = panel_mod_attrs = (sm.en_turno, sm.encolar)
    sm.en_turno = lambda cwd, sid: True
    sm.encolar = lambda cwd, sid, texto: (llamados.append(texto), (True, ""))[1]
    try:
        r = TestClient(panel.app).post("/movil/mandar", data={
            "cwd": "C:/p", "sid": "ses-x", "texto": "también esto"}).json()
    finally:
        sm.en_turno, sm.encolar = viejo_en, viejo_enc
    ok(r == {"ok": True, "encolado": True}, f"contesta encolado ({r})")
    ok(llamados == ["también esto"], "y le pasa el mensaje al proceso")
    ok(panel.MIS_MENSAJES.exists(), "el mensaje igual quedo guardado en mis mensajes")


def correr_todo():
    tmp = Path(tempfile.mkdtemp(prefix="fila_"))
    preparar(tmp)
    try:
        pruebas_proceso(str(tmp))
    finally:
        limpiar()
    pruebas_hilo()
    pruebas_endpoint()


MUTACIONES = {
    "se deja de leer con un mensaje en fila": (
        "_turno", "if viva.encolados and not viva.interrumpida and not d.get(\"is_error\"):",
        "if False:"),
    "no se tacha lo que el CLI ya tomo": ("_turno", "viva.encolados.remove(e)", "pass"),
    "se acepta el resultado de una continuacion sola": (
        "_turno", "if not propio_tomado and not viva.interrumpida:", "if False:"),
    "se encola sin turno corriendo": ("encolar", "or not v.turno.locked() ", ""),
    "el hilo ignora el mensaje en fila": ("_filas_de", 'if a.get("type") == "queued_command":',
                                          "if False:"),
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
        sm._HILOS.clear()
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
            sm._HILOS.clear()
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
