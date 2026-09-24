"""Las charlas de Codex en la pagina de sesiones (2026-08-19).

Lo que se prueba, sin gastar turnos de Codex (todo lee archivos reales del disco):

 1. Que el barrido encuentre rollouts y sepa el cwd de cada uno (session_meta).
 2. Que `es_codex` distinga un id de Codex de uno de Claude (es lo que rutea TODO).
 3. Que las charlas de Codex de un proyecto salgan con su marca `cerebro: "codex"`
    y las de la Laura de voz queden afuera.
 4. Que `donde`, `conversacion`, `novedad` y `contexto` ruteen solos por el id.
 5. Que el tope de Codex pregunte a tiempo. La compactación completa se prueba aparte,
    falseando los turnos para no gastar ni modificar una charla real.

Correr:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_sesiones_codex
"""

import json

from app.rutas import CODEX_SESION, RAIZ
from app.voz import sesiones_movil as sm

fallas = []


def mal(msj):
    fallas.append(msj)


sm._CODEX_BARRIDA[0] = 0.0
sm._codex_barrer()

if not sm._CODEX_SIDS:
    print("OJO: no hay ningun rollout de Codex del ultimo mes; no puedo probar mas.")
    raise SystemExit(0)

# --- 1 y 2: el indice y el ruteo por id ------------------------------------------
sid, ent = next(iter(sm._CODEX_SIDS.items()))
if not ent.get("cwd"):
    mal("el barrido no saco el cwd del session_meta")
if not sm.es_codex(sid):
    mal("es_codex no reconoce un id que esta en el indice")
if sm.es_codex("0123456789abcdef-no-existe"):
    mal("es_codex dice que si a un id inventado")

# --- 3: la lista del proyecto, con marca y sin la Laura de voz --------------------
cwds = {sm._plana(e["cwd"]) for e in sm._CODEX_SIDS.values()}
laura = sm._codex_ids_laura()
for e in list(sm._CODEX_SIDS.values())[:1]:
    ses = sm.codex_sesiones_de(e["cwd"])
    for s in ses:
        if s.get("cerebro") != "codex":
            mal("una charla de Codex salio sin su marca cerebro=codex")
        if s["id"] in laura:
            mal("la charla de la Laura de voz aparece en la bandeja")

# --- 4: el ruteo de las funciones de siempre --------------------------------------
d = sm.donde(sid)
if not d or d.get("cerebro") != "codex":
    mal(f"donde() no encontro la charla de Codex o no la marco: {d}")
mensajes = sm.conversacion(ent["cwd"], sid, 5)
for m in mensajes:
    # "marca" es la costura de una compactada (2026-08-20): la pantalla la dibuja.
    if m["de"] not in ("vos", "claude", "marca"):
        mal("conversacion() devolvio un rol que la pantalla no entiende")
quien, ts = sm.novedad(ent["cwd"], sid)
if quien not in (None, "vos", "claude") or not ts:
    mal(f"novedad() devolvio algo raro: {(quien, ts)}")
ctx = sm.contexto(ent["cwd"], sid)
if "tokens" not in ctx or "tope" not in ctx:
    mal(f"contexto() vino incompleto: {ctx}")

# --- 5: el tope de Codex pregunta antes de llenar su ventana -----------------------
pregunta = sm.pide_compactar(ent["cwd"], sid)
umbral = min(sm.TOPE_AUTO, int(ctx["tope"] * 0.7))
if bool(pregunta) != bool(ctx["tokens"] >= umbral):
    mal("la pregunta de compactar no coincide con el 70 por ciento de la ventana")

if fallas:
    print("FALLAS:")
    for f in fallas:
        print(" -", f)
    raise SystemExit(1)
print(f"OK: {len(sm._CODEX_SIDS)} rollouts indexados, ruteo por id andando, "
      "la bandeja marca el cerebro y el tope de compactar pregunta a tiempo")
