"""El tope de compactar: pasado el limite, se PREGUNTA — ya no se compacta solo.

Historia: el 2026-08-18 el tope compactaba solo (742 millones de tokens en un dia y
una charla arrastrando 574 mil por mensaje). El 2026-08-20 Martin lo dio vuelta:
compactar sin avisar le abria una sesion nueva de golpe, la pestaña vieja seguia
escribiendo a la charla compactada (doble compactada, visto en logs) y la
continuacion no entendia el trabajo. Ahora: `pide_compactar` arma la pregunta,
`resolver_continuacion` redirige los turnos de una charla que ya sigue en otra, y
`conversacion` cose el hilo escondiendo la cocina del resumen.

Aca no se habla con Claude de verdad: se falsean `contexto` y los archivos.

    python -m pruebas.probar_tope_automatico
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


class Contexto:
    """Reemplaza contexto() mientras dura el bloque."""

    def __init__(self, tokens, revienta=False):
        self.tokens, self.revienta = tokens, revienta

    def __enter__(self):
        self._ctx = sm.contexto
        if self.revienta:
            sm.contexto = lambda *a, **k: (_ for _ in ()).throw(OSError("disco raro"))
        else:
            sm.contexto = lambda cwd, sid, **k: {"tokens": self.tokens}
        return self

    def __exit__(self, *a):
        sm.contexto = self._ctx


# El tope depende del MODELO de la sesion (2026-08-20): "vieja" no esta en los
# ajustes reales, asi que corre con el de fabrica.
TOPE = sm.tope_auto_de("vieja")

print("\n--- Debajo del tope: no pregunta nada ---")
with Contexto(TOPE - 1):
    probar("sin pregunta", sm.pide_compactar("D:/x", "vieja") == "")

print("\n--- Pasado el tope: PREGUNTA (no compacta) ---")
with Contexto(TOPE + 1):
    p = sm.pide_compactar("D:/x", "vieja")
probar("pregunta en criollo", "¿" in p and "compacto" in p.lower())
probar("dice cuanto arrastra", "mil" in p or "millones" in p)

print("\n--- Justo en el tope: tambien pregunta ---")
with Contexto(TOPE):
    probar("pregunta", sm.pide_compactar("D:/x", "vieja") != "")

print("\n--- Si no puede medir el contexto, no molesta ---")
with Contexto(0, revienta=True):
    probar("sin pregunta", sm.pide_compactar("D:/x", "vieja") == "")

print("\n--- Sesion recien nacida (sin id): nada que preguntar ---")
with Contexto(999_999):
    probar("sin pregunta", sm.pide_compactar("D:/x", "") == "")

print("\n--- Se le puede pasar otro tope ---")
with Contexto(50_000):
    probar("respeta el tope pedido",
           sm.pide_compactar("D:/x", "vieja", tope=40_000) != "")

print("\n--- El tope es el mismo numero que 'muy caro' ---")
probar("TOPE_AUTO == MUY_CARO", sm.TOPE_AUTO == sm.MUY_CARO)

print("\n--- El tope mira la ventana del modelo (2026-08-20) ---")
# Con 200 mil de ventana el CLI compacta solo al ~80 %: el nuestro llega antes.
probar("con 200 mil pregunta antes que el CLI (80%)", TOPE < 200_000 * 0.8)
probar("y no es un numero ridiculo de chico", TOPE >= 100_000)
_aj = sm._ajustes
sm._ajustes = lambda: {"grande": {"modelo": "opus[1m]"}}
try:
    probar("con la ventana del millon manda el costo (TOPE_AUTO)",
           sm.tope_auto_de("grande") == sm.TOPE_AUTO)
finally:
    sm._ajustes = _aj

print("\n--- La compactada queda marcada ida y vuelta ---")
_ruta = sm.AJUSTES_SESIONES
tmp = Path(tempfile.gettempdir()) / "probar_ajustes_sesiones.json"
tmp.write_text("{}", encoding="utf-8")
sm.AJUSTES_SESIONES = tmp
try:
    sm._marcar_continuacion("vieja", "nuevo1234")
    d = json.loads(tmp.read_text(encoding="utf-8"))
    probar("quedo anotado el sigue_en", d.get("vieja", {}).get("sigue_en") == "nuevo1234")
    probar("y el viene_de al reves", d.get("nuevo1234", {}).get("viene_de") == "vieja")
    sm._marcar_continuacion("vieja", "")
    d = json.loads(tmp.read_text(encoding="utf-8"))
    probar("sin id nuevo no pisa la marca", d.get("vieja", {}).get("sigue_en") == "nuevo1234")

    print("\n--- El servidor redirige a la continuacion (el bug de la pestaña vieja) ---")
    sm._marcar_continuacion("nuevo1234", "nuevo5678")
    probar("sigue la cadena hasta la viva",
           sm.resolver_continuacion("vieja") == "nuevo5678")
    probar("la viva se devuelve tal cual",
           sm.resolver_continuacion("nuevo5678") == "nuevo5678")
    probar("sin id no inventa nada", sm.resolver_continuacion("") == "")
    # Un ciclo escrito a mano en el archivo no puede colgar el servidor.
    d = json.loads(tmp.read_text(encoding="utf-8"))
    d["a"] = {"sigue_en": "b"}
    d["b"] = {"sigue_en": "a"}
    tmp.write_text(json.dumps(d), encoding="utf-8")
    probar("un ciclo no lo cuelga", sm.resolver_continuacion("a") in ("a", "b"))
finally:
    sm.AJUSTES_SESIONES = _ruta
    tmp.unlink(missing_ok=True)

print("\n--- El hilo cosido: la charla anterior arriba, sin la cocina del resumen ---")
_aj = sm._ajustes
_filas = sm._filas_de
viejas = [
    {"de": "vos", "texto": "arreglame el estudio", "h": "10:00"},
    {"de": "claude", "texto": "listo, quedo andando", "h": "10:01"},
    {"de": "vos", "texto": sm.PEDIDO_RESUMEN[:120], "h": "10:02"},
    {"de": "claude", "texto": "RESUMEN SECRETO que Martin no tiene que ver", "h": "10:03"},
]
nuevas = [
    {"de": "vos", "texto": sm.SIEMBRA[:80], "h": "10:04"},
    {"de": "claude", "texto": "Seguimos desde el estudio.", "h": "10:05"},
    {"de": "vos", "texto": "dale, segui", "h": "10:06"},
]
sm._ajustes = lambda: {"nueva111": {"viene_de": "vieja000"}}
sm._filas_de = lambda jsonl: (viejas if "vieja000" in str(jsonl) else list(nuevas))
try:
    hilo = sm.conversacion("D:/x", "nueva111")
    textos = [f["texto"] for f in hilo]
    probar("la charla vieja quedo cosida arriba", textos[0] == "arreglame el estudio")
    probar("el pedido de resumen no se ve",
           not any(sm.PEDIDO_RESUMEN[:40] in t for t in textos))
    probar("el resumen tampoco", not any("SECRETO" in t for t in textos))
    probar("la siembra tampoco", not any(t.startswith("[Esta charla") for t in textos))
    probar("hay una costura en el medio", any(f["de"] == "marca" for f in hilo))
    marca = [i for i, f in enumerate(hilo) if f["de"] == "marca"][0]
    probar("la costura separa lo viejo de lo nuevo",
           hilo[marca - 1]["texto"] == "listo, quedo andando"
           and hilo[marca + 1]["texto"] == "Seguimos desde el estudio.")
    probar("lo nuevo sigue abajo", textos[-1] == "dale, segui")
finally:
    sm._ajustes = _aj
    sm._filas_de = _filas

print("\n--- La siembra lleva los mensajes textuales de Martin ---")
probar("SIEMBRA tiene el hueco {ultimos}", "{ultimos}" in sm.SIEMBRA)
probar("y avisa que mandan sobre el resumen", "mandan" in sm.SIEMBRA)

print("\n--- Laura NO usa este camino (tiene el suyo, cuando esta quieta) ---")
# ⛔ Se intento meterle a `claude_voz.preguntar()` el tope de antes-del-turno y se
# saco el mismo dia: el vigilante del panel ya le pide la compactacion cuando la
# charla esta QUIETA (`AUTOCOMPACTAR_EN`), que no la deja muda en medio de una
# charla hablada. Esta prueba existe para que no vuelva a entrar.
cv_txt = open("app/voz/claude_voz.py", encoding="utf-8").read()
probar("claude_voz no compacta ni pregunta antes del turno",
       "compactar_si_hace_falta" not in cv_txt and "pide_compactar" not in cv_txt)
import panel  # noqa: E402  (solo para leer los numeros, no levanta el servidor)
probar("el tope de Laura (quieta) es mas bajo que el del celular",
       panel.AUTOCOMPACTAR_EN < sm.TOPE_AUTO)
probar("el panel ya no compacta solo",
       "compactar_si_hace_falta" not in open("panel.py", encoding="utf-8").read())

print(f"\n{ok} bien, {fallo} mal")
sys.exit(1 if fallo else 0)
