"""Reiniciar el panel no corta a las sesiones — paso 1 (2026-11-11).

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_reinicio_sin_corte
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_reinicio_sin_corte --mutar

No arranca ningún proceso ni reinicia nada: los procesos son de mentira, las charlas son
archivos armados en una carpeta temporal y el reinicio de verdad se reemplaza por un
anotador. Lo que importa cuidar:
  · que una charla que quedó trabajando sola tras un reinicio se reconozca por el disco, y
    que una quieta NO haga esperar a nadie;
  · que el mensaje que llega la espere en vez de matarle el proceso;
  · que su trabajo no figure "interrumpido" mientras sigue, y que cierre con lo que dijo;
  · que el botón ⟳ no reinicie con alguien a mitad de turno, salvo que se lo pidan igual.
"""
import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from fastapi.testclient import TestClient

import panel
from app.ingesta import trabajos
from app.voz import sesiones_movil as sm

OK, MAL = [], []


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {detalle}")


# --- renglones como los que escribe el CLI en el archivo de una charla -------------------
PEDIDO = {"type": "user", "message": {"role": "user", "content": "hacé tal cosa"}}
PIDE = {"type": "assistant", "message": {"stop_reason": "tool_use",
                                         "content": [{"type": "tool_use", "name": "Bash"}]}}
RESULTADO = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}
PIENSA = {"type": "assistant", "message": {"stop_reason": "end_turn",
                                           "content": [{"type": "thinking", "thinking": "…"}]}}
DICE = {"type": "assistant", "message": {"stop_reason": "end_turn",
                                         "content": [{"type": "text", "text": "listo"}]}}
CIERRE = {"type": "system", "subtype": "stop_hook_summary"}
CUENTAS = [{"type": "last-prompt"}, {"type": "mode"}, {"type": "cost-state"}]


def escribir(ruta, renglones, cola=""):
    ruta.write_text("\n".join(json.dumps(r) for r in renglones) + "\n" + cola, encoding="utf-8")
    return ruta


class Proceso:
    """Un proceso de mentira: lo único que se le pregunta es si tiene hijos."""

    def __init__(self, hijos=0):
        self._hijos = hijos

    def children(self, recursive=False):
        return [object()] * self._hijos


@contextlib.contextmanager
def puesto(modulo, **cambios):
    """Reemplaza cosas de un módulo y las devuelve al salir."""
    antes = {k: getattr(modulo, k) for k in cambios}
    for k, v in cambios.items():
        setattr(modulo, k, v)
    try:
        yield
    finally:
        for k, v in antes.items():
            setattr(modulo, k, v)


def pruebas_disco(tmp):
    f = tmp / "charla.jsonl"
    ab = sm.turno_abierto_en_disco
    chequeo("turno cerrado con su marca de cierre", not ab(escribir(f, [PEDIDO, PIDE, RESULTADO, PIENSA, DICE, CIERRE] + CUENTAS)))
    chequeo("cerrado también si falta la marca pero el asistente ya contestó", not ab(escribir(f, [PEDIDO, DICE] + CUENTAS)))
    chequeo("abierto: pidió una herramienta", ab(escribir(f, [PEDIDO, PIDE])))
    chequeo("abierto: volvió el resultado y el modelo todavía no habló", ab(escribir(f, [PEDIDO, PIDE, RESULTADO])))
    chequeo("abierto: un pensamiento suelto no es un cierre", ab(escribir(f, [PEDIDO, PIDE, RESULTADO, PIENSA])))
    chequeo("los renglones de contabilidad del final no cuentan", ab(escribir(f, [PEDIDO, PIDE, RESULTADO] + CUENTAS)))
    chequeo("abierto: recién llegó el pedido", ab(escribir(f, [DICE, CIERRE, PEDIDO])))
    chequeo("un archivo que no existe no está abierto", not ab(tmp / "no-existe.jsonl"))
    chequeo("un archivo vacío no está abierto", not ab(escribir(f, [])))
    chequeo("un renglón roto al final se saltea", not ab(escribir(f, [PEDIDO, DICE, CIERRE], cola='{"type": "user", "mess')))
    gordo = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x" * 600_000}]}}
    chequeo("abierto aunque lo último sea un renglón enorme", ab(escribir(f, [PEDIDO, DICE, CIERRE, PEDIDO, PIDE, gordo])))
    adjunto = {"type": "attachment", "attachment": {"type": "otro", "datos": "x" * 600_000}}
    chequeo("cerrado aunque después venga un adjunto enorme", not ab(escribir(f, [PEDIDO, DICE, CIERRE, adjunto])))


def pruebas_suelta(tmp):
    sid = "suelta-0001"
    archivo = tmp / (sid + ".jsonl")
    comun = dict(_viva_de=lambda cwd, s: None, es_codex=lambda s: False)
    with puesto(sm.seguir, carpeta_de=lambda cwd: tmp):
        escribir(archivo, [PEDIDO, PIDE])
        with puesto(sm, sueltos_de=lambda s: [], **comun):
            chequeo("sin proceso de antes no hay nada suelto", not sm.suelta_trabajando("C:/p", sid))
        with puesto(sm, sueltos_de=lambda s: [Proceso()], **comun):
            chequeo("proceso de antes + turno abierto = sigue trabajando", sm.suelta_trabajando("C:/p", sid))
            chequeo("sin id no se pregunta nada", not sm.suelta_trabajando("C:/p", ""))
            viejo = time.time() - sm.SUELTA_MUDA_SEG - 60
            os.utime(archivo, (viejo, viejo))
            chequeo("callada hace rato y sin nada corriendo: colgada, no se la espera",
                    not sm.suelta_trabajando("C:/p", sid))
        with puesto(sm, sueltos_de=lambda s: [Proceso(hijos=1)], **comun):
            chequeo("callada pero con una herramienta corriendo: sigue trabajando",
                    sm.suelta_trabajando("C:/p", sid))
        escribir(archivo, [PEDIDO, DICE, CIERRE] + CUENTAS)
        with puesto(sm, sueltos_de=lambda s: [Proceso(hijos=1)], **comun):
            chequeo("proceso de antes con el turno CERRADO: no hay nada que esperar",
                    not sm.suelta_trabajando("C:/p", sid))
        escribir(archivo, [PEDIDO, PIDE])

        class Manejada:
            viva = staticmethod(lambda: True)
        with puesto(sm, sueltos_de=lambda s: [Proceso()], es_codex=lambda s: False,
                    _viva_de=lambda cwd, s: Manejada()):
            chequeo("la que maneja este panel no está suelta", not sm.suelta_trabajando("C:/p", sid))
        with puesto(sm, sueltos_de=lambda s: [Proceso()], _viva_de=lambda cwd, s: None,
                    es_codex=lambda s: True):
            chequeo("una charla de Codex no entra en esto", not sm.suelta_trabajando("C:/p", sid))


def pruebas_espera():
    faltan = {"n": 3}

    def trabaja(cwd, sid):
        faltan["n"] -= 1
        return faltan["n"] >= 0

    with puesto(sm, suelta_trabajando=trabaja):
        tardo = sm.esperar_suelta("C:/p", "x", pausa=0.02)
    chequeo("espera mientras la suelta trabaja y después sigue", tardo > 0 and faltan["n"] == -1, (tardo, faltan))
    with puesto(sm, suelta_trabajando=lambda cwd, sid: False):
        t0 = time.time()
        chequeo("sin nadie trabajando no espera nada",
                sm.esperar_suelta("C:/p", "x", pausa=5) == 0 and time.time() - t0 < 1)
    # Una que no termina nunca. (Corta sola a las 150 vueltas: si el tope no anduviera, la
    # prueba tiene que ponerse roja, no quedarse colgada.)
    vueltas = {"n": 0}

    def no_termina(cwd, sid):
        vueltas["n"] += 1
        return vueltas["n"] < 150

    with puesto(sm, suelta_trabajando=no_termina):
        sm.esperar_suelta("C:/p", "x", tope=0.1, pausa=0.02)
    chequeo("no espera para siempre: tiene tope", vueltas["n"] < 50, vueltas["n"])

    # El mensaje que llega: primero espera, después limpia, después arranca.
    orden = []
    with puesto(sm, esperar_suelta=lambda cwd, sid: orden.append("esperar") or 0,
                _matar_huerfanos=lambda sid: orden.append("matar") or 0,
                _arrancar_viva=lambda *a, **k: orden.append("arrancar") or "viva-nueva",
                _barrer_vivas=lambda: None):
        r = sm._conseguir_viva("C:/carpeta-de-prueba", "sin-anotar-0001", "m", "e")
    chequeo("un mensaje a una charla sin anotar ESPERA antes de matar y arrancar",
            orden == ["esperar", "matar", "arrancar"] and r == "viva-nueva", orden)


def pruebas_trabajos(tmp):
    viejo_db = trabajos.usar(tmp / "trabajos.sqlite")
    guardado = {k: getattr(panel, k) for k in ("_ultima_respuesta", "_seguir_suelta",
                "_avisar")}
    creados = []

    def ficha(ident, sid, estado="trabajando", **extra):
        t = {"id": ident, "estado": estado, "cwd": "C:/p", "sid": sid, "sid_nuevo": "",
             "respuesta": "", "error": "", "creado": time.time(), "terminado": None, **extra}
        with panel._TRABAJOS_CANDADO:
            panel._TRABAJOS_MOVIL[ident] = t
        trabajos.guardar(t)
        creados.append(ident)
        return t

    try:
        # --- el corte al arrancar deja afuera a las que siguen
        ficha("rs-sigue", "rs-ses-1")
        ficha("rs-corta", "rs-ses-2")
        ficha("rs-cola", "rs-ses-1", estado="en_cola")
        cortados = [t["id"] for t in trabajos.marcar_interrumpidos(
            conservar=lambda t: t.get("sid") == "rs-ses-1" and t.get("estado") != "en_cola")]
        chequeo("al arrancar no se corta el trabajo de una charla que sigue",
                "rs-sigue" not in cortados and trabajos.leer("rs-sigue")["estado"] == "trabajando", cortados)
        chequeo("los demás se cortan como siempre",
                "rs-corta" in cortados and trabajos.leer("rs-corta")["estado"] == "interrumpido", cortados)
        chequeo("sin `conservar` corta todo (como antes)",
                "rs-sigue" in [t["id"] for t in trabajos.marcar_interrumpidos()])

        # --- qué fichas se siguen
        with puesto(sm, suelta_trabajando=lambda cwd, sid: sid == "rs-ses-1"):
            chequeo("se sigue la que tiene su charla trabajando", panel._sigue_suelta({"estado": "trabajando", "sid": "rs-ses-1"}))
            chequeo("y la que entró en fila en ese mismo turno", panel._sigue_suelta({"estado": "en_fila", "sid": "rs-ses-1"}))
            chequeo("se mira el id de verdad de una charla recién nacida",
                    panel._sigue_suelta({"estado": "trabajando", "sid": "", "sid_nuevo": "rs-ses-1"}))
            chequeo("una en cola no: nunca llegó a mandarse", not panel._sigue_suelta({"estado": "en_cola", "sid": "rs-ses-1"}))
            chequeo("otra charla no", not panel._sigue_suelta({"estado": "trabajando", "sid": "rs-ses-2"}))
            chequeo("sin id no se puede seguir", not panel._sigue_suelta({"estado": "trabajando", "sid": ""}))

        # --- seguir por el disco hasta que termina
        avisos, vueltas, vistas = [], [], []
        panel._ultima_respuesta = lambda cwd, sid: "esto contestó"
        panel._avisar = lambda texto: avisos.append(texto)

        def trabaja_dos_veces():
            faltan = {"n": 2}

            def f(cwd, sid):
                vistas.append(sid in panel._sueltas_seguidas())
                faltan["n"] -= 1
                return faltan["n"] >= 0
            return f

        ficha("rs-a", "rs-ses-3", avisar=True, jefe="rs-jefe")
        with puesto(sm, suelta_trabajando=trabaja_dos_veces(), turno_cerrado=lambda cwd, sid: True):
            panel._seguir_suelta("rs-a", pausa=0.01)
        t = panel._ficha("rs-a")
        chequeo("mientras la sigue, la charla figura ocupada", vistas and all(vistas), vistas)
        chequeo("y al terminar deja de figurar", "rs-ses-3" not in panel._sueltas_seguidas())
        chequeo("cierra TERMINADO con lo que dijo la charla",
                t["estado"] == "terminado" and t["respuesta"] == "esto contestó", t)
        chequeo("dice que hubo un reinicio en el medio", "reinició" in (t.get("aviso") or ""), t.get("aviso"))
        chequeo("conserva quién lo despachó (para la tarjeta)", t.get("jefe") == "rs-jefe")
        chequeo("queda en el disco", trabajos.leer("rs-a")["estado"] == "terminado")
        chequeo("si habías pedido aviso, sale", len(avisos) == 1, avisos)

        ficha("rs-b", "rs-ses-4")
        with puesto(sm, suelta_trabajando=lambda cwd, sid: False, turno_cerrado=lambda cwd, sid: False):
            panel._seguir_suelta("rs-b", pausa=0.01)
        chequeo("si el proceso desapareció con el turno ABIERTO, eso sí es un corte",
                panel._ficha("rs-b")["estado"] == "interrumpido", panel._ficha("rs-b"))

        ficha("rs-c", "rs-ses-5")

        def cancelan(cwd, sid):
            panel._poner_estado("rs-c", estado="cancelado")
            return True
        with puesto(sm, suelta_trabajando=cancelan, turno_cerrado=lambda cwd, sid: True):
            panel._seguir_suelta("rs-c", pausa=0.01)
        chequeo("si lo cancelaron mientras tanto, no lo pisa", panel._ficha("rs-c")["estado"] == "cancelado")

        # --- el arranque del panel, entero
        seguidos = []
        panel._seguir_suelta = lambda trabajo_id, pausa=3.0: seguidos.append(trabajo_id)
        ficha("rs-e", "rs-ses-7")
        ficha("rs-f", "rs-ses-8")
        with puesto(sm, suelta_trabajando=lambda cwd, sid: sid == "rs-ses-7"):
            panel._arrancar_trabajos()
        hasta = time.time() + 3
        while time.time() < hasta and "rs-e" not in seguidos:
            time.sleep(0.05)
        chequeo("al arrancar el panel, sigue al que quedó trabajando", seguidos == ["rs-e"], seguidos)
        chequeo("y no lo marca como interrumpido", trabajos.leer("rs-e")["estado"] == "trabajando")
        chequeo("el que no tenía a nadie atrás sí se corta", trabajos.leer("rs-f")["estado"] == "interrumpido")
    finally:
        with panel._TRABAJOS_CANDADO:
            for i in [k for k in panel._TRABAJOS_MOVIL if str(k).startswith("rs-")]:
                panel._TRABAJOS_MOVIL.pop(i, None)
        with panel._SUELTAS_CANDADO:
            for s in [s for s in panel._SUELTAS if str(s).startswith("rs-")]:
                panel._SUELTAS.pop(s, None)
        for k, v in guardado.items():
            setattr(panel, k, v)
        trabajos.usar(viejo_db)


def pruebas_boton():
    reinicios, quienes = [], {"lista": []}
    espera_real = panel._reiniciar_cuando_libre
    alguien = [{"sid": "rs-ses-9", "cwd": "C:/p", "nombre": "Reportes"}]
    c = TestClient(panel.app)

    def calmar(seg=0.6):
        time.sleep(seg)

    with puesto(panel, _reiniciar_ya=lambda: reinicios.append(1) or {"ok": True},
                _quienes_trabajan=lambda: list(quienes["lista"]),
                _reiniciar_cuando_libre=lambda pedido: espera_real(pedido, pausa=0.05)):
        try:
            r = c.post("/reiniciar-todo").json()
            chequeo("sin nadie trabajando reinicia en el acto", len(reinicios) == 1 and "esperando" not in r, r)

            reinicios.clear(); quienes["lista"] = alguien
            r = c.post("/reiniciar-todo").json()
            chequeo("con alguien a mitad de turno NO reinicia", not reinicios, reinicios)
            chequeo("y dice a quién espera", [q["nombre"] for q in r.get("esperando", [])] == ["Reportes"], r)
            panel._REINICIO["reiniciando"] = False
            e = c.get("/reiniciar-todo/estado").json()
            chequeo("queda pendiente, a la vista de cualquier pantalla",
                    e.get("pendiente") and e.get("trabajando") == alguien and not e.get("reiniciando"), e)
            c.post("/reiniciar-todo")
            calmar(0.3)
            chequeo("mientras trabaja sigue sin reiniciar", not reinicios)
            quienes["lista"] = []
            calmar()
            chequeo("apenas termina, reinicia solo — y una sola vez", len(reinicios) == 1, reinicios)
            e = c.get("/reiniciar-todo/estado").json()
            chequeo("y deja de estar pendiente", not e.get("pendiente"))
            chequeo("pero avisa que salió a reiniciar (no es lo mismo que cancelado)", e.get("reiniciando"), e)

            reinicios.clear(); quienes["lista"] = alguien
            c.post("/reiniciar-todo")
            c.post("/reiniciar-todo/cancelar")
            quienes["lista"] = []
            calmar()
            chequeo("cancelado no reinicia aunque después queden todas quietas", not reinicios, reinicios)

            reinicios.clear(); quienes["lista"] = alguien
            r = c.post("/reiniciar-todo", json={"ya": True}).json()
            chequeo("«reiniciar ya igual» reinicia aunque haya alguien trabajando",
                    len(reinicios) == 1 and "esperando" not in r, (reinicios, r))
        finally:
            panel._REINICIO.update(pendiente=False, reiniciando=False)
            calmar(0.2)

    # Quién cuenta como trabajando.
    class Viva:
        def __init__(self, sid, tomado=False):
            self.cwd, self.sid = "C:/p", sid
            self.turno = type("C", (), {"locked": staticmethod(lambda: tomado)})()
        viva = staticmethod(lambda: True)

    tmp = Path(tempfile.mkdtemp(prefix="reinicio_vivas_"))
    escribir(tmp / "rs-sola.jsonl", [PEDIDO, PIDE])
    escribir(tmp / "rs-quieta.jsonl", [PEDIDO, DICE, CIERRE])
    vivas = {"a": Viva("rs-turno", tomado=True), "b": Viva("rs-sola"), "c": Viva("rs-quieta")}
    with puesto(sm, VIVAS=vivas, es_codex=lambda s: False), puesto(sm.seguir, carpeta_de=lambda cwd: tmp):
        ahora = sorted(s for _, s in sm.trabajando_ahora())
    chequeo("cuenta la que tiene el turno tomado y la que arrancó un turno sola",
            ahora == ["rs-sola", "rs-turno"], ahora)
    chequeo("no cuenta una quieta", "rs-quieta" not in ahora)


def correr():
    OK.clear(); MAL.clear()
    tmp = Path(tempfile.mkdtemp(prefix="reinicio_"))
    pruebas_disco(tmp)
    pruebas_suelta(tmp)
    pruebas_espera()
    pruebas_trabajos(tmp)
    pruebas_boton()
    return not MAL


def _roto(modulo, nombre, viejo, nuevo):
    """Esa función con un renglón cambiado, armada en memoria: el archivo no se toca.

    ⚠ Se arma ADENTRO del módulo de verdad y no en una copia de sus nombres: la función
    rota tiene que ver los mismos reemplazos que le pone la prueba (el proceso de
    mentira, la respuesta de mentira). Con una copia veía los originales, fallaba por
    otra cosa y la mutación figuraba «cazada» por el motivo equivocado.
    """
    fuente = textwrap.dedent(inspect.getsource(getattr(modulo, nombre)))
    if viejo not in fuente:
        raise SystemExit(f"la mutación ya no encuentra «{viejo}» en {nombre}")
    exec(compile(fuente.replace(viejo, nuevo, 1), nombre + "_roto", "exec"), vars(modulo))
    return getattr(modulo, nombre)


MUTACIONES = {
    "no ve el turno abierto cuando lo último es un resultado": (
        sm, "turno_abierto_en_disco", 'if tipo == "user":\n                return True',
        'if tipo == "user":\n                return False'),
    "espera a cualquier proceso de antes, aunque esté quieto": (
        sm, "suelta_trabajando", "if not turno_abierto_en_disco(ruta):", "if False:"),
    "no le pone tope a la espera": (
        sm, "esperar_suelta", "if time.time() - desde >= tope:", "if False:"),
    "el mensaje que llega mata al proceso sin esperarlo": (
        sm, "_conseguir_viva", "esperar_suelta(cwd, sid)", "pass"),
    "al arrancar corta también a la que sigue": (
        trabajos, "marcar_interrumpidos", "if conservar is not None and conservar(t):", "if False:"),
    "da por terminado un turno que quedó abierto": (
        panel, "_seguir_suelta", 'if sesiones_movil.turno_cerrado(cwd, sid) else ""', 'if True else ""'),
    "el botón reinicia con alguien a mitad de turno": (
        panel, "_pedir_reinicio", "quienes = [] if ya else _quienes_trabajan()", "quienes = []"),
    "no cuenta el turno que la sesión arrancó sola": (
        sm, "trabajando_ahora", "if callada <= SOLA_RECIENTE_SEG and turno_abierto_en_disco(ruta):", "if False:"),
}


def mutaciones():
    """Rompe cada regla a propósito y exige que la prueba se ponga roja."""
    cazadas = 0
    for nombre, (modulo, funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(modulo, funcion)
        _roto(modulo, funcion, viejo, nuevo)
        caidos = []
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                paso = correr()
            caidos = list(MAL)
        except Exception as e:
            paso, caidos = False, ["reventó: " + str(e)[:80]]
        finally:
            setattr(modulo, funcion, original)
            panel._REINICIO["pendiente"] = False
        # Se muestra QUÉ chequeo cayó: una mutación cazada por un chequeo que no tiene
        # nada que ver es una prueba que pasa por el motivo equivocado.
        print(f"  mutación «{nombre}»: " + (f"CAZADA por «{caidos[0]}»" + (f" (+{len(caidos) - 1})" if len(caidos) > 1 else "")
                                             if not paso else "NO SE NOTÓ ✗"))
        cazadas += not paso
    return cazadas == len(MUTACIONES)


if __name__ == "__main__":
    bien = correr()
    print(f"reinicio sin corte: {len(OK)} bien, {len(MAL)} mal")
    if "--mutar" in sys.argv:
        bien = mutaciones() and bien
    sys.exit(0 if bien else 1)
