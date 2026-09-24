"""Cuanto gasta Claude Code en esta maquina, leido de sus propias transcripciones.

⭐ Nacio el 2026-08-18, el dia del drenaje: 1.640 millones de tokens en una jornada
y nadie lo vio hasta que Martin pregunto por que se le acababa el cupo. Cada llamada
que hace Claude Code queda anotada con su `usage` exacto en los .jsonl de
~/.claude/projects, asi que el gasto real se puede MEDIR, no adivinar — es lo mismo
que hace `ccusage`, la herramienta que usa la comunidad para esto. Este modulo lo
mide; el panel lo muestra en el tablero y el vigilante lo mira cada tanto.

Dos decisiones que importan:
- Se cuenta TODO lo que entra y sale del modelo (input + output + cache leido +
  cache escrito). El cache leido es mas barato en plata, pero es exactamente el
  "contexto que se relee en cada llamada" donde vivia el drenaje: si se lo dejara
  afuera, el proximo drenaje seria invisible de vuelta.
- ⚠ El mismo `usage` aparece REPETIDO en varias lineas seguidas del .jsonl (una por
  bloque de la respuesta: el texto, cada herramienta que usa). Se cuenta UNA vez por
  id de mensaje, o el total da el doble o el triple del real.

La lectura es incremental: de cada archivo se recuerda hasta donde se leyo y solo se
lee lo nuevo. Los archivos activos llegan a 45 MB; releerlos enteros cada 5 minutos
seria pelearle el disco al resto del panel.
"""

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# La carpeta donde Claude Code escribe una transcripcion por sesion. La prueba la
# reemplaza por una carpeta de mentira.
CARPETA = Path.home() / ".claude" / "projects"

# El ritmo de quema se junta en baldes de 10 minutos: alcanza para "la ultima hora"
# sin guardar cada llamada.
_BALDE_SEG = 600

# archivo -> {"pos": hasta donde se leyo, "ult_id": ultimo id de mensaje contado,
#             "dias": {"AAAA-MM-DD": (tokens, llamadas)}, "baldes": {n: tokens}}
_archivos = {}
_CACHE = {"ts": 0.0, "r": None}
_CANDADO = threading.Lock()


def lindo(n):
    """El numero dicho como lo diria una persona: 850k, 6,5M, 67M, 1.640M."""
    if n >= 10_000_000:
        return f"{n / 1_000_000:,.0f}M".replace(",", ".")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".", ",")
    if n >= 1_000:
        return f"{round(n / 1000)}k"
    return str(n)


def _nombre(ruta):
    """Como mostrar de que sesion es el gasto: proyecto y el principio del id."""
    p = Path(ruta)
    proyecto = p.parent.name
    # Las carpetas se llaman como la ruta con guiones ("D--IA-wpp-transcriptor"):
    # se saca el disco de adelante, que no le dice nada a nadie.
    if len(proyecto) > 3 and proyecto[1:3] == "--":
        proyecto = proyecto[3:]
    return f"{proyecto} · {p.stem[:8]}"


def _actualizar():
    """Lee lo nuevo de cada transcripcion y suma tokens por dia y por balde de tiempo."""
    hoy0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    vivos = set()
    for jsonl in CARPETA.glob("*/*.jsonl"):
        try:
            est = jsonl.stat()
        except OSError:
            continue
        # Un archivo que no se escribio hoy no puede tener gasto de hoy: ni se abre.
        if est.st_mtime < hoy0:
            continue
        clave = str(jsonl)
        vivos.add(clave)
        e = _archivos.get(clave)
        if e is None or est.st_size < e["pos"]:
            e = _archivos[clave] = {"pos": 0, "ids": [], "dias": {}, "baldes": {}}
        if est.st_size <= e["pos"]:
            continue
        try:
            with open(jsonl, "rb") as f:
                f.seek(e["pos"])
                crudo = f.read()
        except OSError:
            continue
        # La ultima linea puede estar a medio escribir: se corta en el ultimo salto
        # y lo que falte se lee la proxima vez.
        fin = crudo.rfind(b"\n")
        if fin < 0:
            continue
        e["pos"] += fin + 1
        for linea in crudo[:fin].decode("utf-8", errors="replace").splitlines():
            if '"usage"' not in linea:
                continue
            try:
                d = json.loads(linea)
            except Exception:
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if not isinstance(u, dict):
                continue
            mid = m.get("id") or d.get("requestId") or ""
            if mid and mid in e["ids"]:
                continue                      # otro bloque de la MISMA llamada
            e["ids"] = (e["ids"] + [mid])[-20:]
            n = (u.get("input_tokens", 0) + u.get("output_tokens", 0)
                 + u.get("cache_creation_input_tokens", 0)
                 + u.get("cache_read_input_tokens", 0))
            if not n:
                continue
            try:
                cuando = datetime.fromisoformat(
                    str(d.get("timestamp", "")).replace("Z", "+00:00")).astimezone()
            except Exception:
                continue
            dia = cuando.strftime("%Y-%m-%d")
            t, c = e["dias"].get(dia, (0, 0))
            e["dias"][dia] = (t + n, c + 1)
            b = int(cuando.timestamp() // _BALDE_SEG)
            e["baldes"][b] = e["baldes"].get(b, 0) + n
        # Podas: los baldes de hace mas de dos horas y los dias viejos no se miran mas.
        corte = int((time.time() - 7200) // _BALDE_SEG)
        e["baldes"] = {k: v for k, v in e["baldes"].items() if k >= corte}
        if len(e["dias"]) > 10:
            for k in sorted(e["dias"])[:-8]:
                e["dias"].pop(k, None)
    for k in list(_archivos):
        if k not in vivos:
            _archivos.pop(k)


def resumen():
    """El gasto de hoy, listo para la pantalla. Recalcula cada 30 s como mucho."""
    with _CANDADO:
        if time.time() - _CACHE["ts"] < 30 and _CACHE["r"] is not None:
            return _CACHE["r"]
        _actualizar()
        hoy = datetime.now().strftime("%Y-%m-%d")
        total = llamadas = 0
        sesiones = []
        corte = int((time.time() - 3600) // _BALDE_SEG)
        ultima_hora = 0
        for ruta, e in _archivos.items():
            t, c = e["dias"].get(hoy, (0, 0))
            if t:
                total += t
                llamadas += c
                sesiones.append((t, _nombre(ruta)))
            ultima_hora += sum(v for k, v in e["baldes"].items() if k >= corte)
        sesiones.sort(reverse=True)
        r = {"hoy": total, "linda": lindo(total), "llamadas": llamadas,
             "ultima_hora": ultima_hora, "ultima_hora_linda": lindo(ultima_hora),
             "sesiones": [{"nombre": n, "tokens": t, "linda": lindo(t)}
                          for t, n in sesiones[:3]]}
        _CACHE["ts"] = time.time()
        _CACHE["r"] = r
        return r


# --- Codex: el gasto del OTRO cerebro grande (2026-08-19) -----------------------
# Desde que Laura piensa con Claude o con Codex, "tokens hoy" a secas engañaba: se
# veia caer el numero al cambiar de cerebro y parecia que no se gastaba nada. Codex
# no anota el usage llamada por llamada como Claude: cada rollout lleva un
# `total_token_usage` ACUMULADO, asi que el gasto de una charla es su ULTIMO total, y
# el del dia es la suma de los ultimos totales de las charlas de hoy.
CARPETA_CODEX = Path.home() / ".codex" / "sessions"
_COLA_BYTES = 300_000      # cuanto se lee del final de cada rollout para buscar el total
_CACHE_CODEX = {"ts": 0.0, "r": None}


def _ultimo_total(p):
    """El ultimo total acumulado anotado en un rollout. 0 si no anoto ninguno."""
    try:
        tam = p.stat().st_size
        with p.open("rb") as f:
            if tam > _COLA_BYTES:
                f.seek(tam - _COLA_BYTES)   # los rollouts grandes no se leen enteros
            cola = f.read().decode("utf-8", errors="replace")
    except Exception:
        return 0
    marca = '"total_token_usage":'
    i = cola.rfind(marca)
    if i < 0:
        return 0
    try:
        d = json.JSONDecoder().raw_decode(cola[i + len(marca):].lstrip())[0]
        return int(d.get("total_tokens") or 0)
    except Exception:
        return 0


def codex_hoy():
    """Tokens que gasto Codex hoy en toda la maquina. Recalcula cada 30 s como mucho."""
    if time.time() - _CACHE_CODEX["ts"] < 30 and _CACHE_CODEX["r"] is not None:
        return _CACHE_CODEX["r"]
    d = datetime.now()
    # Las sesiones se guardan en carpetas por fecha: AAAA/MM/DD.
    carpeta = CARPETA_CODEX / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    total = charlas = 0
    try:
        for p in carpeta.glob("*.jsonl"):
            t = _ultimo_total(p)
            if t:
                total += t
                charlas += 1
    except Exception:
        pass
    r = {"hoy": total, "linda": lindo(total), "charlas": charlas}
    _CACHE_CODEX["ts"] = time.time()
    _CACHE_CODEX["r"] = r
    return r


# --- La fila del LEDGER (2026-08-27) --------------------------------------------
# docs/LEDGER.md tenia cinco filas y las cinco decian "sin medir" en el costo. No
# porque no se pueda medir: este modulo ya lo mide para el tablero. Faltaba el
# puente entre el numero de la pantalla y la fila que se pega al cerrar la tarea.
# La idea es de Marcus, que ordena su ledger por costo para saber que optimizar:
# "no adivino que rol optimizar, ordeno el ledger por costo".

def de_sesion(filtro):
    """Tokens de HOY de las sesiones cuyo nombre contenga `filtro`. Sirve para que
    la fila del ledger diga lo que gasto ESTA tarea y no el dia entero de la
    maquina, que es un techo honesto pero grueso."""
    with _CANDADO:
        _actualizar()
        hoy = datetime.now().strftime("%Y-%m-%d")
        total = llamadas = 0
        cuantas = 0
        for ruta, e in _archivos.items():
            if filtro.lower() not in _nombre(ruta).lower():
                continue
            t, c = e["dias"].get(hoy, (0, 0))
            if t:
                total += t
                llamadas += c
                cuantas += 1
    return {"tokens": total, "linda": lindo(total), "llamadas": llamadas,
            "sesiones": cuantas}


def fila_ledger(quien="Opus (chat del panel)", que="...", como="hecho", sesion=None):
    """La linea de markdown lista para pegar en docs/LEDGER.md, con el gasto real.
    Con `sesion`, mide solo esa; sin ella, el dia entero de la maquina."""
    if sesion:
        s = de_sesion(sesion)
        costo = f"{s['linda']} ({s['llamadas']} llamadas)"
        if not s["tokens"]:
            costo = f"sin medir (no encontre ninguna sesion con '{sesion}')"
    else:
        r = resumen()
        c = codex_hoy()
        costo = f"{r['linda']} ({r['llamadas']} llamadas) - dia entero de la maquina"
        if c["hoy"]:
            costo += f", mas {c['linda']} de Codex"
    return f"| {datetime.now().strftime('%Y-%m-%d')} | {quien} | {que} | {como} | {costo} |"


def _main_ledger():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = resumen()
    c = codex_hoy()
    hoy = datetime.now().strftime("%Y-%m-%d")
    print(f"\nGasto de hoy ({hoy}), medido de las transcripciones:\n")
    print(f"  Claude: {r['linda']} en {r['llamadas']} llamadas"
          f"   (ultima hora: {r['ultima_hora_linda']})")
    print(f"  Codex:  {c['linda']} en {c['charlas']} charlas")
    if r["sesiones"]:
        print("\n  Las sesiones que mas gastaron hoy:")
        for s in r["sesiones"]:
            print(f"     {s['linda']:>10}  {s['nombre']}")
    sesion = None
    if "--sesion" in sys.argv:
        i = sys.argv.index("--sesion")
        sesion = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
    print("\nFila para docs/LEDGER.md (cambiale el 'que' y el 'como salio'):\n")
    print(fila_ledger(sesion=sesion))
    if not sesion:
        print("\n⚠ Sin --sesion el costo es el del DIA en toda la maquina, no el de"
              "\n  una tarea sola. Para la tuya, pasale un pedazo del nombre de la"
              "\n  sesion de la lista de arriba:  --sesion wpp-transcriptor")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main_ledger() if "--ledger" in sys.argv else
                     (print("uso: python -m app.nucleo.gasto --ledger [--sesion TEXTO]") or 0))
