"""La bandeja no muestra dos veces la misma conversacion.

Historia: el 2026-08-21 Martin mando una captura del proyecto Farah con cuatro filas
que en realidad eran DOS charlas — cada una con su continuacion al lado, una viva y la
otra muerta con la chapa "sigue en otra" — y la mudada a Codex llamada "[Esta charla
venia corriendo con Claude y Martin la acaba de", que es el texto del traspaso. Su
palabra fue: "se ve y se siente feo trabajar asi".

Lo que se prueba aca:
  - `listar()` marca `tapada` en la charla vieja SOLO si su continuacion esta en la
    misma lista (si no, la vieja se sigue viendo: nunca se esconde algo inalcanzable).
  - `_codex_titulo` saltea la cocina de compactar/mudar y, mientras no tenga un mensaje
    tuyo, se llama como la charla que continua.
  - `_mudar_borrador` (panel) pasa lo que dejaste escrito a la continuacion.

No se habla con ningun CLI: esta todo falseado.

    python -m pruebas.probar_bandeja_tapadas
"""
import json
import sys
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm

ok = fallo = 0


def probar(que, condicion):
    global ok, fallo
    if condicion:
        ok += 1
        print("  ok   ", que)
    else:
        fallo += 1
        print("  FALLA", que)


def listar_con(sesiones, codex, ajustes):
    """Corre `listar()` con un solo proyecto de mentira y devuelve sus sesiones."""
    orig = (sm.seguir.proyectos, sm.seguir.sesiones_de, sm.novedad,
            sm.codex_sesiones_de, sm._ids_laura, sm._ajustes,
            sm.CLAUDE_PROYECTOS, sm.CARPETAS_SESIONES)
    vacia = Path(tempfile.mkdtemp(prefix="bandeja_vacia_"))
    sm.seguir.proyectos = lambda: [{"nombre": "Farah", "cwd": "C:/EspacioDeTrabajo/Farah"}]
    sm.seguir.sesiones_de = lambda cwd, horas=0: [dict(s) for s in sesiones]
    sm.novedad = lambda cwd, sid: ("claude", 0)
    sm.codex_sesiones_de = lambda cwd: [dict(s) for s in codex]
    sm._ids_laura = lambda: set()
    sm._ajustes = lambda: ajustes
    sm.CLAUDE_PROYECTOS = vacia
    sm.CARPETAS_SESIONES = vacia / "no_existe.json"
    try:
        return {s["id"]: s for s in sm.listar()[0]["sesiones"]}
    finally:
        (sm.seguir.proyectos, sm.seguir.sesiones_de, sm.novedad,
         sm.codex_sesiones_de, sm._ids_laura, sm._ajustes,
         sm.CLAUDE_PROYECTOS, sm.CARPETAS_SESIONES) = orig
        vacia.rmdir()


VIEJA = {"id": "vieja", "nombre": "Explicar el proyecto", "viva": False, "ts": 1}
NUEVA = {"id": "nueva", "nombre": "Continuacion", "viva": False, "ts": 2}

print("\n--- La compactada se tapa; la que sigue viva, no ---")
f = listar_con([VIEJA, NUEVA], [], {"vieja": {"sigue_en": "nueva"},
                                    "nueva": {"viene_de": "vieja"}})
probar("las dos siguen viajando en la respuesta", len(f) == 2)
probar("la vieja queda tapada", f["vieja"].get("tapada") is True)
probar("y dice a donde siguio", f["vieja"].get("sigue_en") == "nueva")
probar("la continuacion NO se tapa", not f["nueva"].get("tapada"))

print("\n--- Si la continuacion no esta a la vista, la vieja se muestra igual ---")
f = listar_con([VIEJA], [], {"vieja": {"sigue_en": "fantasma"}})
probar("no se tapa", not f["vieja"].get("tapada"))
probar("pero conserva la chapa 'sigue en otra'", f["vieja"].get("sigue_en") == "fantasma")

print("\n--- Cadena de tres: solo queda la ultima ---")
f = listar_con([VIEJA, NUEVA, {"id": "ultima", "nombre": "La viva", "ts": 3}], [],
               {"vieja": {"sigue_en": "nueva"}, "nueva": {"sigue_en": "ultima"}})
probar("la primera tapada", f["vieja"].get("tapada") is True)
probar("la del medio tambien", f["nueva"].get("tapada") is True)
probar("la ultima no", not f["ultima"].get("tapada"))

print("\n--- La mudanza a Codex tapa la de Claude (y al reves) ---")
cx = {"id": "01a0-codex", "nombre": "x", "cerebro": "codex", "ts": 3, "ultimo": None}
f = listar_con([VIEJA], [cx], {"vieja": {"sigue_en": "01a0-codex"},
                               "01a0-codex": {"viene_de": "vieja"}})
probar("la charla de Claude queda tapada", f["vieja"].get("tapada") is True)
probar("la de Codex se muestra", not f["01a0-codex"].get("tapada"))
f = listar_con([NUEVA], [dict(cx, ts=1)], {"01a0-codex": {"sigue_en": "nueva"}})
probar("una charla de Codex mudada tambien se tapa",
       f["01a0-codex"].get("tapada") is True)

print("\n--- Sin continuaciones no cambia nada ---")
f = listar_con([VIEJA, NUEVA], [], {})
probar("nadie tapado", not any(s.get("tapada") for s in f.values()))

# --- El nombre de una charla de Codex ---------------------------------------------
SIEMBRA = sm.SIEMBRA_CEREBRO.format(de="Claude", para="Codex", resumen="lo de siempre")


def titulo_con(mensajes, ajustes=None, titulo_viejo="Explicar el proyecto"):
    orig = (sm._codex_mensajes, sm._ajustes, sm.seguir._titulo_de,
            dict(sm._CODEX_SIDS))
    sm._codex_mensajes = lambda sid, ultimos=0: [dict(m) for m in mensajes]
    sm._ajustes = lambda: (ajustes or {})
    sm.seguir._titulo_de = lambda ruta: titulo_viejo
    sm._CODEX_SIDS["01a0-codex"] = {"ruta": "x", "cwd": "C:/EspacioDeTrabajo/Farah",
                                    "ts": 0, "mtime": 0}
    sm._CODEX_TITULOS.clear()
    try:
        return sm._codex_titulo("01a0-codex")
    finally:
        (sm._codex_mensajes, sm._ajustes, sm.seguir._titulo_de) = orig[:3]
        sm._CODEX_SIDS.clear()
        sm._CODEX_SIDS.update(orig[3])
        sm._CODEX_TITULOS.clear()


print("\n--- El titulo no es el texto del traspaso ---")
t = titulo_con([{"de": "vos", "texto": SIEMBRA}, {"de": "claude", "texto": "Seguimos."}],
               {"01a0-codex": {"viene_de": "vieja"}})
probar("no arranca con la siembra", not t.startswith("[Esta charla"))
probar("hereda el nombre de la charla que continua", t == "Explicar el proyecto")

print("\n--- Apenas le escribis, manda tu mensaje ---")
t = titulo_con([{"de": "vos", "texto": SIEMBRA},
                {"de": "claude", "texto": "Seguimos."},
                {"de": "vos", "texto": "dale, arrancá con el excel"}],
               {"01a0-codex": {"viene_de": "vieja"}})
probar("el titulo es lo que escribiste vos", t == "dale, arrancá con el excel")

print("\n--- El pedido de resumen tampoco titula nada ---")
t = titulo_con([{"de": "vos", "texto": sm.PEDIDO_RESUMEN},
                {"de": "vos", "texto": "seguimos con esto"}])
probar("saltea el pedido de resumen", t == "seguimos con esto")

print("\n--- Sin nada de donde agarrarse, el id (como siempre) ---")
probar("cae al id", titulo_con([]) == "01a0-cod")
probar("y si no hay charla vieja tampoco inventa",
       titulo_con([{"de": "vos", "texto": SIEMBRA}], {}) == "01a0-cod")

print("\n--- El nombre heredado NO se cachea (vale hasta tu primer mensaje) ---")
titulo_con([{"de": "vos", "texto": SIEMBRA}], {"01a0-codex": {"viene_de": "vieja"}})
probar("no quedo pegado en el cache", "01a0-codex" not in sm._CODEX_TITULOS)

# --- El borrador se muda con vos ---------------------------------------------------
print("\n--- Lo que dejaste escrito se va a la continuacion ---")
import panel  # noqa: E402  (solo para las funciones; no levanta el servidor)

_ruta = panel.BORRADORES_SESIONES
tmp = Path(tempfile.gettempdir()) / "probar_borradores_tapadas.json"
panel.BORRADORES_SESIONES = tmp
try:
    tmp.write_text(json.dumps({"vieja": {"texto": "media frase", "ts": 1}}),
                   encoding="utf-8")
    d = panel._mudar_borrador("vieja", "nueva")
    probar("la vieja se queda sin borrador", "vieja" not in d)
    probar("y la continuacion lo hereda", d["nueva"]["texto"] == "media frase")
    probar("quedo guardado en el disco",
           json.loads(tmp.read_text(encoding="utf-8")).get("nueva"))

    tmp.write_text(json.dumps({"vieja": {"texto": "vieja", "ts": 1},
                               "nueva": {"texto": "lo que estoy escribiendo", "ts": 2}}),
                   encoding="utf-8")
    d = panel._mudar_borrador("vieja", "nueva")
    probar("si la nueva ya tiene algo escrito, manda lo suyo",
           d["nueva"]["texto"] == "lo que estoy escribiendo")
    probar("y la vieja igual se limpia", "vieja" not in d)

    tmp.write_text(json.dumps({"otra": {"texto": "x", "ts": 1}}), encoding="utf-8")
    d = panel._mudar_borrador("vieja", "nueva")
    probar("sin borrador que mudar no toca nada", d == {"otra": {"texto": "x", "ts": 1}})
finally:
    panel.BORRADORES_SESIONES = _ruta
    tmp.unlink(missing_ok=True)

print("\n--- Los subagentes de /paralelo no son conversaciones ---")
# Diagnostico de la sesion orquestadora (2026-08-21) y verificado a mano sobre los
# rollouts reales: 33 charlas con thread_source "user" y 5 auxiliares con "subagent",
# que aparecian en la bandeja como charlas gemelas tituladas con el pedido heredado.
_meta = Path(tempfile.mkdtemp(prefix="rollouts_"))


def rollout(nombre, extra):
    p = _meta / nombre
    p.write_text(json.dumps({"type": "session_meta", "payload": dict(
        {"id": nombre, "cwd": "C:/EspacioDeTrabajo/Farah"}, **extra)}), encoding="utf-8")
    return p


try:
    probar("una charla de Martin entra",
           sm._codex_meta(rollout("normal", {"thread_source": "user",
                                             "source": "exec"})) is not None)
    probar("una abierta en VS Code tambien",
           sm._codex_meta(rollout("vscode", {"thread_source": "user",
                                             "source": "vscode"})) is not None)
    probar("la de un subagente NO",
           sm._codex_meta(rollout("sub", {"thread_source": "subagent",
                                          "source": {"subagent": {}}})) is None)
    probar("un rollout viejo sin la marca sigue entrando",
           sm._codex_meta(rollout("viejo", {})) is not None)
finally:
    for f in _meta.iterdir():
        f.unlink()
    _meta.rmdir()

print("\n--- Las dos pantallas saltean las tapadas ---")
compu = open("app/estaticos/sesiones.html", encoding="utf-8").read()
movil = open("panel.py", encoding="utf-8").read()


def definicion(texto, nombre):
    """La linea donde se define `const <nombre> = ...`, o "" si no esta.

    ⚠ Se busca la DEFINICION y no un pedazo de expresion suelto. Antes esto preguntaba
    por el texto literal `"!s.archivada && !s.tapada"`, y el 2026-08-27 un cambio que no
    tocaba las tapadas para nada —sacar el Set de archivadas del navegador— hizo fallar
    dos chequeos sin que el invariante se hubiera roto. Un chequeo pegado a la redaccion
    grita cuando alguien reordena y se calla cuando alguien rompe.
    """
    for linea in texto.splitlines():
        if linea.strip().startswith(f"const {nombre} ="):
            return linea
    return ""


for pantalla, texto in (("la compu", compu), ("el celular", movil)):
    probar(f"{pantalla}: la bandeja saltea las tapadas",
           "!s.tapada" in definicion(texto, "enBandeja"))
probar("la compu no las dibuja en la bandeja", "filter(s => !s.tapada)" in compu)
probar("la compu no las manda a las archivadas", "guardada(s) && !s.tapada" in compu)
probar("el celular no las manda a las archivadas", "!enBandeja(s) && !s.tapada" in movil)

print(f"\n{ok} bien, {fallo} mal")
sys.exit(1 if fallo else 0)
