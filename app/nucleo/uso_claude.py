"""Cuanto del plan de Claude llevas usado: el MISMO numero que muestra `/usage`.

⭐ Pedido de Martin (2026-11-12): *"me gustaria ver en todo momento mi uso de claude"*.

Historia que importa: en agosto el panel tuvo un "medidor de cupo" (`app/voz/cupo.py`) y
se SACO, porque estimaba a ojo contra limites calibrados a mano y daba 25 % cuando la
pantalla de Claude decia 46 %. En ese momento el uso real no estaba en ningun lado. Hoy si:
Claude Code, para dibujar `/usage`, le pregunta a Anthropic con la sesion iniciada
(`GET https://api.anthropic.com/api/oauth/usage`) y la respuesta trae los porcentajes
reales: la ventana de 5 horas, la semana y la semana de cada modelo con limite propio.
Este modulo hace ese mismo pedido. Medido el 2026-11-12: semana 48 %, Fable 45 %.

Reglas, cada una con su motivo:
- ⚠⚠ La llave se LEE y nada mas. Nunca se renueva desde aca: renovar con el refresh token
  lo rota, y el CLI se quedaria con uno que ya no sirve (deslogueado). Si la llave vencio,
  se contesta "sin dato" y se espera a que Claude Code la renueve solo, cosa que hace en
  cuanto lo usas. Tampoco se imprime ni se guarda en ningun lado.
- No es una API documentada: si cambia la forma de la respuesta, se degrada a "sin dato",
  no rompe el panel.
- Se pregunta como mucho cada `_CACHE_SEG`: varias pantallas abiertas comparten la misma
  respuesta, y el endpoint tiene su propio limite (con un 429 se devuelve la ultima que
  hubo, marcada como vieja).
"""

import json
import threading
import time

import requests

from app.rutas import CREDENCIALES_CLAUDE

URL = "https://api.anthropic.com/api/oauth/usage"
_CACHE_SEG = 120
_CACHE = {"ts": 0.0, "r": None}
_CANDADO = threading.Lock()

# Como se llama cada limite en la pastilla. Lo que no esta aca sale con su clave tal cual
# (mejor un nombre feo que un limite escondido).
_NOMBRES = {"five_hour": "5 horas", "session": "5 horas", "weekly_all": "Semana",
            "seven_day": "Semana"}


def _llave():
    try:
        d = json.loads(CREDENCIALES_CLAUDE.read_text(encoding="utf-8"))
    except Exception:
        return None, "no encontré la sesión de Claude Code en esta máquina"
    o = d.get("claudeAiOauth") or {}
    tok = o.get("accessToken") or ""
    if not tok:
        return None, "Claude Code no tiene una sesión iniciada"
    vence = (o.get("expiresAt") or 0) / 1000
    if vence and vence < time.time():
        return None, "la sesión de Claude Code venció; se renueva sola cuando lo usás"
    return tok, ""


def _limites(d):
    """De la respuesta cruda a una lista prolija. Primero `limits` (la forma nueva, la que
    trae el modelo de cada limite semanal); si no viene, `five_hour` / `seven_day`."""
    salida = []
    for x in d.get("limits") or []:
        if not isinstance(x, dict) or x.get("percent") is None:
            continue
        kind = x.get("kind") or ""
        nombre = _NOMBRES.get(kind, kind.replace("_", " "))
        modelo = (((x.get("scope") or {}).get("model") or {}).get("display_name") or "")
        if kind == "weekly_scoped" and modelo:
            nombre = "Semana · " + modelo
        elif modelo:
            nombre += " · " + modelo
        salida.append({"clave": kind, "nombre": nombre, "pct": round(float(x["percent"])),
                       "renueva": x.get("resets_at") or "", "nivel": x.get("severity") or "normal",
                       "activo": x.get("is_active") is not False})
    claves = {s["clave"] for s in salida}
    for k in ("five_hour", "seven_day"):
        v = d.get(k)
        if isinstance(v, dict) and v.get("utilization") is not None:
            if k == "seven_day" and "weekly_all" in claves:
                continue
            if k == "five_hour" and ({"five_hour", "session"} & claves):
                continue
            salida.append({"clave": k, "nombre": _NOMBRES[k], "pct": round(float(v["utilization"])),
                           "renueva": v.get("resets_at") or "", "nivel": "normal", "activo": True})
    # La de 5 horas primero (es la que corta antes), despues la semana y las de cada modelo.
    orden = {"five_hour": 0, "session": 0, "weekly_all": 1, "seven_day": 1}
    salida.sort(key=lambda s: (orden.get(s["clave"], 2), s["nombre"]))
    return salida


def uso(forzar=False):
    """{"ok": True, "limites": [...], "ts": ..., "viejo": bool} o {"ok": False, "motivo": ...}."""
    with _CANDADO:
        ahora = time.time()
        if not forzar and _CACHE["r"] and ahora - _CACHE["ts"] < _CACHE_SEG:
            return _CACHE["r"]
        tok, motivo = _llave()
        if not tok:
            return {"ok": False, "motivo": motivo}
        try:
            r = requests.get(URL, timeout=12, headers={
                "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "claude-code-panel", "Content-Type": "application/json"})
        except Exception as e:
            return _viejo_o({"ok": False, "motivo": "no pude preguntarle a Anthropic: " + str(e)[:80]})
        if r.status_code == 429:
            return _viejo_o({"ok": False, "motivo": "Anthropic pidió esperar un rato"})
        if r.status_code in (401, 403):
            return {"ok": False, "motivo": "la sesión de Claude Code no sirvió; se renueva sola cuando lo usás"}
        if not r.ok:
            return _viejo_o({"ok": False, "motivo": "Anthropic contestó %s" % r.status_code})
        try:
            limites = _limites(r.json())
        except Exception:
            return _viejo_o({"ok": False, "motivo": "la respuesta cambió de forma"})
        res = {"ok": True, "limites": limites, "ts": ahora, "viejo": False}
        _CACHE.update(ts=ahora, r=res)
        return res


def _viejo_o(error):
    """Si ya hubo un dato bueno, mejor ese marcado como viejo que nada."""
    if _CACHE["r"]:
        return dict(_CACHE["r"], viejo=True)
    return error


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import truststore
    truststore.inject_into_ssl()
    print(json.dumps(uso(forzar=True), ensure_ascii=False, indent=1))
