"""La columna derecha y el control remoto de las sesiones del panel (2026-10-20).

Pedido de Martin, con capturas del Claude Desktop: el interruptor "Remote Control" (la
charla publicada en claude.ai/code para seguirla desde el celular) y la columna con
Entorno, Contexto y Conectores. Lo que se mide aca, sin gastar tokens ni abrir nada:

  1. `_atajar` (en el hilo que lee al CLI) anota los conectores del `system`/`init` y se
     queda con la respuesta a un pedido de control del PANEL, sin mandarla a la cola.
  2. ⭐⭐ Un turno que el CLI arranca SOLO —porque le escribieron desde claude.ai— lo
     atiende `_vigia_remoto`: contesta el permiso, la marca trabajando mientras dura y al
     terminar suelta el candado. Sin esto el CLI se queda esperando un permiso que nadie
     contesta, y desde el celular parece colgado.
  3. Quieta, el vigia NO agarra el candado: escribirle desde el panel tiene que andar.
  4. Una charla publicada no se duerme por falta de memoria (cortaria el puente).

    python -m pruebas.probar_entorno_remoto
    python -m pruebas.probar_entorno_remoto --mutar

La parte de verdad contra el CLI la mide `pruebas/sonda_remote_control.py`.
"""
import json
import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.voz import sesiones_movil as sm


class ProcFalso:
    """Un proceso que no es nada: vivo, con un stdin que anota lo que se le escribe."""
    pid = 999_999

    def __init__(self):
        self.escrito = []
        este = self

        class Stdin:
            def write(self, s):
                este.escrito.append(s)

            def flush(self):
                pass
        self.stdin = Stdin()

    def poll(self):
        return None


def viva_falsa():
    v = sm._Viva(ProcFalso(), r"C:\carpeta\falsa", "aaaabbbb-prueba", "opus", "")
    return v


def correr(callar=False):
    r = {}

    def chequear(titulo, condicion, detalle=""):
        r[titulo] = bool(condicion)
        if not callar:
            print(f"  ok   {titulo}" if condicion
                  else f"  MAL  {titulo}" + (f" -> {detalle}" if detalle else ""))

    if not callar:
        print("\n1) Lo que ve el hilo que lee al CLI")
    v = viva_falsa()
    init = json.dumps({"type": "system", "subtype": "init", "tools": ["a", "b"],
                       "mcp_servers": [{"name": "claude-in-chrome", "status": "connected"},
                                       {"name": "gmail", "status": "failed"}],
                       "claude_code_version": "2.1.296"})
    chequear("el init no se le saca a la cola (el turno lo sigue viendo)",
             sm._atajar(v, init + "\n") is False)
    chequear("y deja anotados los conectores con su estado",
             v.init.get("conectores") == [{"nombre": "claude-in-chrome", "estado": "connected"},
                                          {"nombre": "gmail", "estado": "failed"}],
             v.init)
    ev = threading.Event()
    v.respuestas["panel-123"] = [ev, None]
    resp = json.dumps({"type": "control_response", "response": {
        "subtype": "success", "request_id": "panel-123",
        "response": {"session_url": "https://claude.ai/code/x"}}})
    chequear("la respuesta a un pedido del panel no va a la cola", sm._atajar(v, resp) is True)
    chequear("y le llega al que la esperaba",
             ev.is_set() and (v.respuestas["panel-123"][1] or {}).get("subtype") == "success")
    otra = json.dumps({"type": "control_response", "response": {"request_id": "ajena"}})
    chequear("una respuesta que no es del panel sigue de largo", sm._atajar(v, otra) is False)

    if not callar:
        print("\n2) Un turno que llega desde claude.ai")
    v = viva_falsa()
    v.remoto = {"url": "https://claude.ai/code/x", "estado": "conectado"}
    mandados = []
    original = sm._mandar_control
    sm._mandar_control = lambda p, cand, rid, resp: mandados.append((rid, resp))
    hilo = threading.Thread(target=sm._vigia_remoto, args=(v,), daemon=True)
    try:
        hilo.start()
        time.sleep(0.6)
        chequear("quieta, el vigia no tiene agarrado el candado", not v.turno.locked())
        clave = v.clave()
        for d in ({"type": "user", "message": {"role": "user", "content": [
                       {"type": "text", "text": "hola desde el celular"}]}},
                  {"type": "control_request", "request_id": "r1", "request": {
                       "subtype": "can_use_tool", "tool_name": "Write", "input": {}}}):
            v.cola.put(json.dumps(d) + "\n")
        time.sleep(1.2)
        chequear("con un turno remoto corriendo, la charla figura trabajando",
                 sm.EN_CURSO.get(clave) is v.proc and v.turno.locked())
        chequear("y el permiso que pidio se contesta (no queda colgado)",
                 [m[0] for m in mandados] == ["r1"], mandados)
        v.cola.put(json.dumps({"type": "result", "subtype": "success"}) + "\n")
        time.sleep(1.2)
        chequear("al terminar suelta el candado y deja de figurar trabajando",
                 not v.turno.locked() and clave not in sm.EN_CURSO)
        v.ultimo = 0
        chequear("una charla publicada no se duerme por falta de memoria",
                 not sm._dormible(v, time.time(), piso=0))
        v.remoto = None
        time.sleep(0.6)
        chequear("al apagarlo el vigia se va solo", not hilo.is_alive())
    finally:
        v.remoto = None
        sm._mandar_control = original
        sm.EN_CURSO.pop(v.clave(), None)

    if not callar:
        print("\n3) Lo que pide la columna")
    e = sm.entorno("", "")
    chequear("sin charla contesta igual, con la maquina y sin control remoto",
             e.get("ok") and e.get("maquina") and e.get("remoto_posible") is False, e)
    chequear("el control remoto no se prende en una charla sin empezar",
             sm.remoto(r"C:\x", "", True).get("ok") is False)
    return r


MUTACIONES = [
    ("el hilo que lee deja de anotar los conectores",
     lambda: setattr(sm, "_atajar", lambda v, l: False),
     ["y deja anotados los conectores con su estado",
      "la respuesta a un pedido del panel no va a la cola"]),
    ("el vigia deja de atender los permisos",
     lambda: setattr(sm, "_atender_pedido", lambda v, d, c: None),
     ["y el permiso que pidio se contesta (no queda colgado)"]),
    ("una charla publicada se puede dormir",
     lambda: setattr(sm, "_dormible", lambda v, a, piso=None: True),
     ["una charla publicada no se duerme por falta de memoria"]),
]


def mutar():
    print("\nProbando la prueba: se rompe cada regla a proposito\n")
    bien = mal = 0
    for nombre, romper, deben_fallar in MUTACIONES:
        guardado = {n: getattr(sm, n) for n in ("_atajar", "_atender_pedido", "_dormible")}
        try:
            romper()
            r = correr(callar=True)
            cayo = [t for t in deben_fallar if not r.get(t, True)]
        finally:
            for n, v in guardado.items():
                setattr(sm, n, v)
        falta = [t for t in deben_fallar if t not in cayo]
        if falta:
            mal += 1
            print(f"  MAL  {nombre}")
            for t in falta:
                print(f"       el chequeo '{t}' siguio en verde con el defecto puesto")
        else:
            bien += 1
            print(f"  ok   {nombre} -> la cazan {len(cayo)} chequeos")
    print(f"\n{'LA PRUEBA SIRVE' if mal == 0 else 'HAY CHEQUEOS DE ADORNO'} — "
          f"{bien} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


def main():
    if "--mutar" in sys.argv:
        return mutar()
    r = correr()
    mal = sum(1 for v in r.values() if not v)
    print(f"\n{'TODO BIEN' if mal == 0 else 'HAY PROBLEMAS'} — "
          f"{len(r) - mal} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
