#!/usr/bin/env python3
"""Vigilante generico: chequea cosas y avisa al usuario cuando CAMBIAN de estado.

    python vigilar.py --config vigilar.json --una-vez     # para cron / Programador de tareas
    python vigilar.py --config vigilar.json --cada 60     # se queda mirando cada 60 s
    python vigilar.py --config vigilar.json --probar      # dice como esta todo, sin avisar

El archivo de config vive en el proyecto (ej. `vigilar.json` en su raiz):

    {
      "proyecto": "mi-proyecto",
      "canal": "telegram",
      "hablar": true,                      // ademas, que Laura lo diga en voz alta
      "chequeos": [
        {"nombre": "Mi API",          "url": "https://ejemplo.com/health"},
        {"nombre": "Bot de Telegram", "proceso": "app.ingesta.bot_telegram"},
        {"nombre": "Algo en un VPS",  "comando": "ssh vps 'docker ps --format {{.Names}} | grep -q n8n'"}
      ]
    }

Tres tipos de chequeo, y con `comando` se puede mirar cualquier cosa:
  url      -> responde con codigo < 400
  proceso  -> hay un proceso vivo cuya linea de comando contiene ese texto
  comando  -> el comando termina bien (codigo 0)

REGLAS (las mismas para todo proyecto, y por eso estan aca y no copiadas a mano):
  - Avisa cuando algo pasa de ANDAR a NO ANDAR, y cuando vuelve. No en cada vuelta.
  - No repite el mismo aviso hasta que se recupere.
  - Aguanta `fallos_seguidos` antes de gritar (default 2): un hipo de red no es
    una caida, y un aviso falso te ensenia a ignorar los avisos.
  - El estado se guarda al lado de la config, asi `--una-vez` desde un cron
    recuerda lo de la corrida anterior.

Solo stdlib (psutil si esta, para `proceso`), para que ande en cualquier proyecto.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

AVISAR = Path(__file__).with_name("avisar.py")
TIMEOUT = 15
FALLOS_PARA_AVISAR = 2       # cuantas veces seguidas tiene que fallar antes de avisar


# --- Los tres tipos de chequeo ------------------------------------------------
def _chequear_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vigilar/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return (True, "") if r.status < 400 else (False, f"responde {r.status}")
    except Exception as e:
        return False, str(e)[:120]


def _chequear_proceso(texto):
    """Busca un proceso vivo cuya linea de comando contenga `texto`."""
    try:
        import psutil
        for p in psutil.process_iter(["cmdline"]):
            try:
                if texto in " ".join(p.info["cmdline"] or []):
                    return True, ""
            except Exception:
                continue
        return False, "no hay ningun proceso asi corriendo"
    except ImportError:
        pass
    # Sin psutil: en Windows preguntamos por PowerShell, en el resto con pgrep.
    if sys.platform == "win32":
        cmd = ["powershell", "-NoProfile", "-Command",
               f"@(Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{texto}*' }}).Count"]
    else:
        cmd = ["pgrep", "-f", texto]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        vivo = (p.stdout.strip() not in ("", "0")) if sys.platform == "win32" else p.returncode == 0
        return (True, "") if vivo else (False, "no hay ningun proceso asi corriendo")
    except Exception as e:
        return False, f"no pude mirar los procesos: {str(e)[:90]}"


def _chequear_comando(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=TIMEOUT)
        if p.returncode == 0:
            return True, ""
        return False, (p.stderr or p.stdout or f"termino con codigo {p.returncode}").strip()[:120]
    except subprocess.TimeoutExpired:
        return False, f"no contesto en {TIMEOUT} s"
    except Exception as e:
        return False, str(e)[:120]


def _chequear(c):
    if c.get("url"):
        return _chequear_url(c["url"])
    if c.get("proceso"):
        return _chequear_proceso(c["proceso"])
    if c.get("comando"):
        return _chequear_comando(c["comando"])
    return False, "chequeo mal escrito: necesita url, proceso o comando"


# --- Estado y aviso -----------------------------------------------------------
def _estado_path(config_path):
    return config_path.with_suffix(config_path.suffix + ".estado.json")


def _leer_estado(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _avisar(texto, proyecto, canal, hablar=False):
    try:
        cmd = [sys.executable, str(AVISAR), "--por", canal,
               "--categoria", "produccion", "--proyecto", proyecto]
        if hablar:                       # ademas, que Laura lo diga en voz alta
            cmd.append("--hablar")
        p = subprocess.run(cmd + [texto], capture_output=True, text=True, timeout=90)
        if p.returncode:
            print(f"  no pude avisar: {(p.stderr or p.stdout).strip()[:200]}")
    except Exception as e:
        print(f"  no pude avisar: {e}")


def una_vuelta(cfg, config_path, avisar=True):
    """Chequea todo una vez. Devuelve cuantos estan caidos."""
    proyecto = cfg.get("proyecto") or config_path.parent.name
    canal = cfg.get("canal", "telegram")
    hablar = bool(cfg.get("hablar", False))
    umbral = int(cfg.get("fallos_seguidos", FALLOS_PARA_AVISAR))
    est_path = _estado_path(config_path)
    est = _leer_estado(est_path)
    caidos = 0

    for c in cfg.get("chequeos", []):
        nombre = c.get("nombre") or c.get("url") or c.get("proceso") or c.get("comando") or "?"
        ok, detalle = _chequear(c)
        e = est.setdefault(nombre, {"fallos": 0, "avisado": False, "desde": None})
        if ok:
            print(f"  OK    {nombre}")
            if e["avisado"] and avisar:
                caido_desde = e.get("desde")
                cuanto = ""
                if caido_desde:
                    mins = int((time.time() - caido_desde) / 60)
                    cuanto = f" (estuvo caido {mins} min)" if mins else ""
                _avisar(f"{nombre}: volvio a andar{cuanto}.", proyecto, canal, hablar)
            e.update({"fallos": 0, "avisado": False, "desde": None})
        else:
            caidos += 1
            e["fallos"] += 1
            e["desde"] = e.get("desde") or time.time()
            print(f"  CAIDO {nombre} — {detalle} (falla {e['fallos']} vez seguida)")
            # El aviso sale recien al cruzar el umbral, y UNA sola vez.
            if e["fallos"] >= umbral and not e["avisado"]:
                e["avisado"] = True
                if avisar:
                    _avisar(f"{nombre} no responde. {detalle}", proyecto, canal, hablar)

    try:
        est_path.write_text(json.dumps(est, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  (no pude guardar el estado: {e})")
    return caidos


def main():
    ap = argparse.ArgumentParser(description="Vigila cosas y avisa cuando cambian de estado.")
    ap.add_argument("--config", required=True, help="el vigilar.json del proyecto")
    ap.add_argument("--una-vez", action="store_true", help="un solo chequeo (para cron)")
    ap.add_argument("--cada", type=int, metavar="SEG", help="quedarse mirando cada N segundos")
    ap.add_argument("--probar", action="store_true", help="chequear y mostrar, SIN avisar")
    a = ap.parse_args()

    config_path = Path(a.config).resolve()
    if not config_path.exists():
        sys.exit(f"No existe {config_path}.")
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        sys.exit(f"No pude leer {config_path}: {e}")
    if not cfg.get("chequeos"):
        sys.exit(f"{config_path} no tiene ningun chequeo.")

    if a.cada:
        print(f"Vigilando {len(cfg['chequeos'])} cosas cada {a.cada} s. Ctrl+C para cortar.")
        while True:
            una_vuelta(cfg, config_path, avisar=not a.probar)
            time.sleep(a.cada)
    else:
        caidos = una_vuelta(cfg, config_path, avisar=not a.probar)
        sys.exit(1 if caidos else 0)


if __name__ == "__main__":
    main()
