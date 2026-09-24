"""
El medidor de cupo de Codex y el desvio automatico a Claude.

Lo que se prueba, que es lo que puede romperse en silencio:

 1. Que `codex_voz.cupo()` lea de verdad el `rate_limits` de un rollout (con la
    ventana mas llena mandando), y devuelva None si no hay de donde leer.
 2. Que `cerebro_grande` se pase solo a Claude cuando Codex viene al limite,
    ANTES de preguntar — sin esto, Laura se entera del cupo recien cuando Codex
    deja de contestar.
 3. Que si Martin pide Codex sabiendo que esta al limite, se le haga caso
    (con aviso) y no se lo devuelva solo — y que la proteccion se rearme cuando
    el cupo baja.

Todo con cupo de mentira y una carpeta de rollouts de mentira: no se habla con
ningun cerebro. Correr:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_cupo_codex
"""

import json
import tempfile
from pathlib import Path

from app.voz import cerebro_grande as cg
from app.voz import codex_voz as cx
from app.voz import claude_voz as _cl

fallas = []


def igual(que, esperado, caso):
    if que != esperado:
        fallas.append(f"{caso}: esperaba {esperado!r} y dio {que!r}")


def _rollout(carpeta, nombre, lineas):
    p = Path(carpeta) / "2026" / "08" / "20" / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return p


LINEA_CUPO = json.dumps({"timestamp": "t", "type": "event_msg", "payload": {
    "type": "token_count",
    "rate_limits": {"primary": {"used_percent": 8.0, "window_minutes": 43200,
                                "resets_at": 1789782792},
                    "secondary": {"used_percent": 55.5, "window_minutes": 300}}}})
LINEA_RUIDO = json.dumps({"type": "response_item", "payload": {"type": "message"}})

# --- 1. Leer el cupo de un rollout de verdad (de mentira) ------------------------
sesiones_real, cache_real = cx.CODEX_SESIONES, cx._cupo_cache
with tempfile.TemporaryDirectory() as tmp:
    _rollout(tmp, "rollout-a.jsonl", [LINEA_RUIDO, LINEA_CUPO, LINEA_RUIDO])
    cx.CODEX_SESIONES = Path(tmp)
    cx._cupo_cache = (0.0, None)
    c = cx.cupo()
    igual(c and c.get("usado"), 55.5, "manda la ventana mas llena")
    igual(c and c.get("resets_at"), 1789782792, "cuando se renueva")

with tempfile.TemporaryDirectory() as tmp:
    _rollout(tmp, "rollout-b.jsonl", [LINEA_RUIDO])   # sin rate_limits anotado
    cx.CODEX_SESIONES = Path(tmp)
    cx._cupo_cache = (0.0, None)
    igual(cx.cupo(), None, "sin dato devuelve None")
cx.CODEX_SESIONES, cx._cupo_cache = sesiones_real, cache_real

# --- 2 y 3. El desvio del interruptor, con cupo de mentira ------------------------
# Se guarda el estado real de cerebro.json para dejarlo igual que estaba.
cfg_real = cg._leer_config()
cupo_real = cx.cupo
precal_real = _cl.precalentar
_cl.precalentar = lambda: None          # que la prueba no levante un Claude de verdad
try:
    # Estando al limite, pedir Codex a mano lo pone igual, pero avisando.
    cx.cupo = lambda: {"usado": 95.0, "resets_at": None}
    cg.usar("claude")
    frase = cg.usar("codex")
    igual(cg.activo(), "codex", "te hace caso aunque este al limite")
    if "95" not in (frase or "") or "cupo" not in (frase or ""):
        fallas.append(f"al elegirlo a mano no avisa del cupo: {frase!r}")
    igual(cg._leer_config().get("cupo_ok"), True, "queda anotado que lo elegiste sabiendo")

    # Con `cupo_ok` puesto, el desvio lo respeta y no te devuelve a Claude.
    igual(cg._esquivar_cupo(), "", "respeta al que insistio")
    igual(cg.activo(), "codex", "sigue en codex si insististe")

    # Sin `cupo_ok` (el caso normal: el cupo se lleno solo mientras charlabas),
    # el desvio cambia a Claude antes de preguntar y lo dice.
    cfg = cg._leer_config()
    cfg.pop("cupo_ok", None)
    cg._guardar_config(cfg)
    cg._cache = (0.0, None)
    aviso = cg._esquivar_cupo()
    igual(cg.activo(), "claude", "se paso solo a claude")
    if "95" not in aviso or "Claude" not in aviso:
        fallas.append(f"el aviso no dice que paso: {aviso!r}")
    cfg = cg._leer_config()
    cfg.pop("traspaso", None)           # el cambio deja traspaso: no ensuciar la charla real
    cg._guardar_config(cfg)

    # Con el cupo renovado, elegir Codex no deja `cupo_ok` y el desvio no toca nada.
    cx.cupo = lambda: {"usado": 12.0, "resets_at": None}
    frase = cg.usar("codex")
    igual(cg._leer_config().get("cupo_ok"), None, "con cupo sano no queda la marca")
    if "cupo" in (frase or ""):
        fallas.append(f"avisa del cupo cuando esta sano: {frase!r}")
    igual(cg._esquivar_cupo(), "", "con cupo sano no desvia")
    igual(cg.activo(), "codex", "con cupo sano se queda en codex")

    # Y si el cupo baja estando `cupo_ok` puesto, la proteccion se rearma sola.
    cfg = cg._leer_config()
    cfg["cupo_ok"] = True
    cg._guardar_config(cfg)
    cg._esquivar_cupo()
    igual(cg._leer_config().get("cupo_ok"), None, "la marca se borra al renovarse el cupo")

    # Si no se puede leer el cupo, no se toca nada: mejor probar y que falle el
    # fallback de siempre, que desviar a ciegas.
    cx.cupo = lambda: None
    igual(cg._esquivar_cupo(), "", "sin dato no desvia")
finally:
    cx.cupo = cupo_real
    _cl.precalentar = precal_real
    cg._guardar_config(cfg_real)        # cerebro.json vuelve exacto a como estaba
    cg._cache = (0.0, None)

# --- 4. La perilla de esfuerzo de Codex (sus niveles, no los de Claude) ----------
ajustes_real = cx.AJUSTES_SESIONES
with tempfile.TemporaryDirectory() as tmp:
    cx.AJUSTES_SESIONES = Path(tmp) / "ajustes.json"
    igual(cx.poner_esfuerzo("high"), "high", "guarda un esfuerzo valido")
    igual(cx.esfuerzo_actual(), "high", "y se relee del archivo")
    igual(cx.poner_esfuerzo("minimal"), "minimal", "minimal existe solo en codex")
    igual(cx.poner_esfuerzo("xhigh"), "", "un nivel de claude no vale para codex")
    igual(cx.esfuerzo_actual(), "", "y queda el de fabrica")
cx.AJUSTES_SESIONES = ajustes_real

if fallas:
    print("FALLAS:")
    for f in fallas:
        print(" -", f)
    raise SystemExit(1)
print(f"OK: el cupo se lee del rollout, el interruptor esquiva el limite y la "
      f"perilla de esfuerzo guarda bien (quedo puesto: {cg.como_se_llama()})")
