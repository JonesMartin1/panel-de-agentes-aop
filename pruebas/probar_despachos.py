"""La tarjeta "Despachos" de la sesión chief (`app/voz/despachos.py` + `/movil/despachos`).

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_despachos
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_despachos --mutar

No arranca ningún turno ni toca datos reales: los trabajos van a un archivo temporal, el
turno del panel se reemplaza por uno que no hace nada y los mensajes se guardan aparte.
Lo que importa cuidar:
  · que solo se listen los despachos de ESA sesión, también después de compactarse;
  · que quien llama a `/movil/mandar` sin `jefe` no note ningún cambio;
  · que un despacho que cae en fila tenga id, y que su respuesta NO salga hacia Aura;
  · que "se cortó" (reinicio del panel) no se disfrace de "terminó".
"""
import contextlib
import inspect
import io
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

import panel
from app.ingesta import trabajos
from app.voz import despachos
from app.voz import sesiones_movil as sm

OK, MAL = [], []
AHORA = 1_000_000.0
JEFE, JEFE_VIEJO = "jefe-nuevo-0001", "jefe-viejo-0001"


def chequeo(nombre, cond, detalle=""):
    (OK if cond else MAL).append(nombre)
    if not cond:
        print(f"  ✗ {nombre} {detalle}")


def ficha(ident, jefe, sid, estado="trabajando", hace=60, cerro=None, **extra):
    """Una ficha como las del panel. `hace` y `cerro`: segundos antes de AHORA."""
    return {"id": ident, "jefe": jefe, "sid": sid, "sid_nuevo": "", "estado": estado,
            "cwd": "C:/proyecto", "cerebro": "", "respuesta": "texto que no debe viajar",
            "creado": AHORA - hace, "terminado": None if cerro is None else AHORA - cerro,
            **extra}


# Las charlas que "siguen en otra": el chief compactado y un destino compactado.
SIGUE = {JEFE_VIEJO: JEFE, "datos-vieja": "datos-nueva"}
resolver = lambda s: SIGUE.get(s, s)
nombres = lambda cwd, sid, cerebro="": {"reportes-1": "Reportes", "flujos-1": "Flujos"}.get(sid, "")


def armar(fichas, sid=JEFE, pregunta_de=None, nombre_de=nombres):
    return despachos.armar(fichas, sid, ahora=AHORA, resolver=resolver,
                           nombre_de=nombre_de, pregunta_de=pregunta_de)


def pruebas_logica():
    # --- de quién son
    r = armar([ficha("t1", JEFE, "reportes-1")])
    chequeo("lista lo que despachó esa sesión", len(r) == 1 and r[0]["sid"] == "reportes-1", r)
    chequeo("con el nombre de la charla destino", r and r[0]["nombre"] == "Reportes", r)
    chequeo("trabajando se muestra como «trabaja», desde que se mandó",
            r and r[0]["estado"] == "trabaja" and r[0]["desde"] == AHORA - 60, r)
    chequeo("un trabajo sin jefe no aparece", armar([ficha("t1", "", "reportes-1")]) == [])
    chequeo("el de otro jefe no aparece", armar([ficha("t1", "otro-jefe", "reportes-1")]) == [])
    chequeo("sin sesión no hay nada", armar([ficha("t1", JEFE, "reportes-1")], sid="") == [])
    chequeo("lo que se manda a sí misma no cuenta", armar([ficha("t1", JEFE, JEFE)]) == [])

    # --- compactaciones
    r = armar([ficha("t1", JEFE_VIEJO, "reportes-1")])
    chequeo("el chief compactado conserva sus despachos de antes", len(r) == 1, r)
    r = armar([ficha("t1", JEFE_VIEJO, "reportes-1")], sid=JEFE_VIEJO)
    chequeo("y se ven igual parado en su charla vieja", len(r) == 1, r)
    r = armar([ficha("t1", JEFE, "datos-vieja")])
    chequeo("un destino compactado apunta a la charla vigente",
            r and r[0]["sid"] == "datos-nueva", r)

    # --- charla que está naciendo
    r = armar([ficha("t1", JEFE, "")])
    chequeo("una charla nueva sin id todavía: renglón sin enlace",
            r and r[0]["sid"] == "" and r[0]["nombre"] == "charla nueva", r)
    r = armar([ficha("t1", JEFE, "", sid_nuevo="flujos-1")])
    chequeo("apenas nace, usa su id de verdad", r and r[0]["sid"] == "flujos-1", r)

    # --- cada estado
    for estado, quiere in (("en_fila", "trabaja"), ("en_cola", "trabaja"),
                           ("terminado", "termino"), ("fallo", "fallo"),
                           ("interrumpido", "corto"), ("cancelado", "paro"),
                           ("algo-raro", "corto")):
        r = armar([ficha("t1", JEFE, "reportes-1", estado, hace=600, cerro=120)])
        chequeo(f"{estado} se muestra como «{quiere}»", r and r[0]["estado"] == quiere, r)
    r = armar([ficha("t1", JEFE, "reportes-1", "terminado", hace=600, cerro=120)])
    chequeo("lo terminado cuenta el tiempo desde que cerró", r and r[0]["desde"] == AHORA - 120, r)

    # --- te pregunta algo
    preg = lambda cwd, sid: {"hora": AHORA - 30} if sid == "flujos-1" else None
    r = armar([ficha("t1", JEFE, "flujos-1")], pregunta_de=preg)
    chequeo("con una pregunta esperando dice «pregunta», desde que preguntó",
            r and r[0]["estado"] == "pregunta" and r[0]["desde"] == AHORA - 30, r)
    r = armar([ficha("t1", JEFE, "flujos-1", "terminado", cerro=10)], pregunta_de=preg)
    chequeo("la pregunta gana también sobre «terminó» (el plan se anota al cerrar)",
            r and r[0]["estado"] == "pregunta", r)
    r = armar([ficha("t1", JEFE, "flujos-1", "fallo", cerro=10)], pregunta_de=preg)
    chequeo("pero no tapa un «falló»", r and r[0]["estado"] == "fallo", r)
    r = armar([ficha("t1", JEFE, "reportes-1")], pregunta_de=preg)
    chequeo("la pregunta de otra charla no se le cuelga a esta", r and r[0]["estado"] == "trabaja", r)

    # --- ventana, tope y orden
    h = 3600
    chequeo("lo terminado hace más de 12 horas se va",
            armar([ficha("t1", JEFE, "reportes-1", "terminado", hace=14 * h, cerro=13 * h)]) == [])
    chequeo("lo que sigue vivo no se va aunque sea viejo",
            len(armar([ficha("t1", JEFE, "reportes-1", hace=14 * h)])) == 1)
    chequeo("uno largo que cerró hace poco sigue a la vista",
            len(armar([ficha("t1", JEFE, "reportes-1", "terminado", hace=14 * h, cerro=h)])) == 1)
    muchas = [ficha(f"t{i}", JEFE, f"dest-{i}", "terminado", hace=100 + i, cerro=50) for i in range(12)]
    muchas.append(ficha("vivo", JEFE, "dest-vivo", hace=5000))
    r = armar(muchas)
    chequeo("no pasa del tope de renglones", len(r) == despachos.TOPE, len(r))
    chequeo("lo que se mueve va arriba, aunque sea lo más viejo", r and r[0]["trabajo"] == "vivo", r[:1])
    chequeo("después, lo más nuevo primero", [f["trabajo"] for f in r[1:3]] == ["t0", "t1"], r[1:3])
    r = armar([ficha("viejo", JEFE, "reportes-1", "terminado", hace=900, cerro=600),
               ficha("nuevo", JEFE, "reportes-1", hace=60)])
    chequeo("dos despachos a la misma charla: un renglón, el más nuevo",
            len(r) == 1 and r[0]["trabajo"] == "nuevo", r)

    # --- qué viaja
    r = armar([ficha("t1", JEFE, "reportes-1")])
    chequeo("cada renglón lleva lo justo, sin la respuesta del trabajo",
            r and set(r[0]) == {"trabajo", "sid", "cwd", "nombre", "cerebro", "estado", "desde"}, r)

    def revienta(*a):
        raise RuntimeError("sin nombre")
    r = armar([ficha("t1", JEFE, "reportes-1")], nombre_de=revienta)
    chequeo("si no se puede nombrar la charla, va su id corto", r and r[0]["nombre"] == "reportes", r)


def pruebas_panel():
    tmp = Path(tempfile.mkdtemp(prefix="despachos_"))
    viejo_db = trabajos.usar(tmp / "trabajos.sqlite")
    guardado = {k: getattr(panel, k) for k in ("MIS_MENSAJES", "_guardar_borrador",
                "_correr_trabajo_movil", "_ultima_respuesta")}
    viejo_en, viejo_enc = sm.en_turno, sm.encolar
    ocupada, encolados, vueltas, creados = {"v": False}, [], [], []
    panel.MIS_MENSAJES = tmp / "m.jsonl"
    panel._guardar_borrador = lambda *a, **k: None
    panel._correr_trabajo_movil = lambda *a, **k: None       # ningún turno de verdad
    panel._ultima_respuesta = lambda cwd, sid: "listo"
    sm.en_turno = lambda cwd, sid: ocupada["v"]
    sm.encolar = lambda cwd, sid, texto: (encolados.append(texto), (True, ""))[1]
    c = TestClient(panel.app)

    def mandar(**datos):
        r = c.post("/movil/mandar", data={"cwd": "C:/proyecto", "texto": "hacé tal cosa",
                                          **datos}).json()
        if r.get("trabajo"):
            creados.append(r["trabajo"])
        return r

    try:
        # --- el campo jefe en la ficha
        r = mandar(sid="pd-dest-1", segundo_plano="1", jefe="pd-jefe-1")
        t = panel._ficha(r.get("trabajo") or "") or {}
        chequeo("con jefe arranca el trabajo como siempre", r.get("ok") and r.get("trabajo"), r)
        chequeo("la ficha guarda quién lo despachó", t.get("jefe") == "pd-jefe-1", t)
        chequeo("y queda en el disco", (trabajos.leer(r.get("trabajo") or "") or {}).get("jefe") == "pd-jefe-1")
        pub = c.get("/movil/trabajo/" + (r.get("trabajo") or "x")).json()
        chequeo("/movil/trabajo no muestra el jefe", pub.get("ok") and "jefe" not in pub, pub)

        r = mandar(sid="pd-dest-2", segundo_plano="1")
        t = panel._ficha(r.get("trabajo") or "") or {}
        chequeo("sin jefe la ficha queda como las de siempre", r.get("ok") and "jefe" not in t, t)
        r = mandar(sid="pd-dest-3", segundo_plano="1", jefe="pd-dest-3")
        t = panel._ficha(r.get("trabajo") or "") or {}
        chequeo("mandarse a sí misma no es despachar", r.get("ok") and "jefe" not in t, t)

        # --- la tarjeta, por HTTP
        d = c.get("/movil/despachos", params={"cwd": "C:/proyecto", "sid": "pd-jefe-1"}).json()
        chequeo("/movil/despachos lista el despacho del jefe",
                d.get("ok") and [i["sid"] for i in d.get("items", [])] == ["pd-dest-1"], d)
        chequeo("con la hora del servidor", isinstance(d.get("ahora"), float), d.get("ahora"))
        chequeo("y sin la respuesta del trabajo", "respuesta" not in str(d), d)
        d = c.get("/movil/despachos", params={"sid": "pd-dest-2"}).json()
        chequeo("una charla que no despachó nada: lista vacía", d == {"ok": True, "ahora": d.get("ahora"), "items": []}, d)
        chequeo("sin sesión: lista vacía", c.get("/movil/despachos").json().get("items") == [])

        # --- el pedido que cae en un turno que ya corría
        ocupada["v"] = True
        r = mandar(sid="pd-dest-4")
        chequeo("en fila y sin jefe contesta EXACTAMENTE como antes", r == {"ok": True, "encolado": True}, r)
        r = mandar(sid="pd-dest-5", jefe="pd-jefe-1")
        hijo = r.get("trabajo") or ""
        chequeo("en fila y con jefe trae id de trabajo",
                r.get("ok") and r.get("encolado") and bool(hijo), r)
        t = panel._ficha(hijo) or {}
        chequeo("su ficha nace «en_fila» con el jefe", t.get("estado") == "en_fila" and t.get("jefe") == "pd-jefe-1", t)
        chequeo("los dos mensajes llegaron al proceso", len(encolados) == 2, encolados)
        d = c.get("/movil/despachos", params={"sid": "pd-jefe-1"}).json()
        fila = next((i for i in d.get("items", []) if i["sid"] == "pd-dest-5"), {})
        chequeo("la tarjeta lo muestra trabajando", fila.get("estado") == "trabaja", d)
        ocupada["v"] = False                      # el turno donde se metió terminó
        hasta = time.time() + 6
        while time.time() < hasta and (panel._ficha(hijo) or {}).get("estado") == "en_fila":
            time.sleep(0.1)
        t = panel._ficha(hijo) or {}
        chequeo("cuando ese turno cierra, el despacho en fila cierra con su respuesta",
                t.get("estado") == "terminado" and t.get("respuesta") == "listo", t)

        # --- reinicio del panel
        cortadas = {t["id"]: t for t in trabajos.marcar_interrumpidos()}
        primero = cortadas.get(creados[0]) or {}
        chequeo("tras un reinicio la ficha conserva el jefe", primero.get("jefe") == "pd-jefe-1", primero)
        r = despachos.armar(list(cortadas.values()), "pd-jefe-1")
        chequeo("y la tarjeta dice «se cortó», no «terminó»",
                [i["estado"] for i in r if i["sid"] == "pd-dest-1"] == ["corto"], r)
    finally:
        with panel._TRABAJOS_CANDADO:
            for i in [k for k, t in panel._TRABAJOS_MOVIL.items()
                      if str(t.get("sid") or "").startswith("pd-dest-")]:
                panel._TRABAJOS_MOVIL.pop(i, None)
        with panel._TURNOS_CANDADO:
            for s in [s for s in panel._TURNOS_ABIERTOS if str(s).startswith("pd-dest-")]:
                panel._TURNOS_ABIERTOS.discard(s)
        for k, v in guardado.items():
            setattr(panel, k, v)
        sm.en_turno, sm.encolar = viejo_en, viejo_enc
        trabajos.usar(viejo_db)


def correr():
    OK.clear(); MAL.clear()
    pruebas_logica()
    pruebas_panel()
    return not MAL


def _armar_roto(viejo, nuevo):
    """`armar` con un renglón cambiado. Se arma en memoria: el archivo no se toca."""
    fuente = inspect.getsource(despachos)
    if viejo not in fuente:
        raise SystemExit(f"la mutación ya no encuentra «{viejo}» en despachos.py")
    ns = {}
    exec(compile(fuente.replace(viejo, nuevo, 1), "despachos_roto", "exec"), ns)
    return ns["armar"]


def mutaciones():
    """Rompe cada regla a propósito y exige que la prueba se ponga roja."""
    seguir = panel._seguir_en_fila
    casos = {
        "lista los despachos de cualquier jefe": lambda: setattr(despachos, "armar", _armar_roto(
            "if not jefe or vigente(jefe) != yo:", "if not jefe:")),
        "no sigue al chief compactado": lambda: setattr(despachos, "armar", _armar_roto(
            "vistos[s] = (resolver(s) if resolver else s) or s", "vistos[s] = s")),
        "«se cortó» pasa por «terminó»": lambda: setattr(despachos, "armar", _armar_roto(
            '"interrumpido": "corto"', '"interrumpido": "termino"')),
        "no mira si la charla te pregunta algo": lambda: setattr(despachos, "armar", _armar_roto(
            "if preg:", "if False:")),
    }
    cazadas = 0
    for nombre, romper in casos.items():
        original = despachos.armar
        romper()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                paso = correr()
        finally:
            despachos.armar = original
            panel._seguir_en_fila = seguir
        print(f"  mutación «{nombre}»: {'CAZADA' if not paso else 'NO SE NOTÓ ✗'}")
        cazadas += not paso
    return cazadas == len(casos)


if __name__ == "__main__":
    bien = correr()
    print(f"despachos: {len(OK)} bien, {len(MAL)} mal")
    if "--mutar" in sys.argv:
        bien = mutaciones() and bien
    sys.exit(0 if bien else 1)
