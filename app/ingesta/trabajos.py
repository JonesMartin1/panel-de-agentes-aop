"""Los trabajos en segundo plano, guardados en disco (2026-10-27).

Hasta hoy vivian solo en `_TRABAJOS_MOVIL`, un dict en memoria del panel: un reinicio
los borraba, y la pantalla que preguntaba por un trabajo se quedaba con un id que ya no
existia.

Una tabla, `trabajos`: la ficha entera de cada trabajo, como JSON. El dict en memoria
sigue siendo el que se usa (es rapido y todo el panel lo conoce); esto es su respaldo.

Una conexion por operacion y modo WAL: el panel es un proceso con varios hilos y esto
se toca poco, no hace falta mas. La ruta es `TRABAJOS_DB` de `app/rutas.py`; las pruebas
la cambian por una temporal con `usar()`.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

from app.rutas import TRABAJOS_DB

_RUTA = Path(TRABAJOS_DB)
_CANDADO = threading.Lock()
DIAS_GUARDADOS = 30


def usar(ruta):
    """Cambia el archivo (para las pruebas). Devuelve el anterior."""
    global _RUTA
    viejo, _RUTA = _RUTA, Path(ruta)
    return viejo


def _con():
    _RUTA.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_RUTA), timeout=10, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS trabajos (
            id TEXT PRIMARY KEY, estado TEXT, creado REAL, datos TEXT);
    """)
    return c


def _correr(sql, args=(), uno=False, todos=False):
    with _CANDADO:
        c = _con()
        try:
            cur = c.execute(sql, args)
            if uno:
                return cur.fetchone()
            if todos:
                return cur.fetchall()
            c.commit()
            return cur.rowcount
        finally:
            c.close()


def guardar(t):
    """Escribe la ficha entera. Nunca puede voltear al que llama: si falla, avisa y sigue."""
    try:
        datos = {k: v for k, v in dict(t).items() if _serializable(v)}
        _correr("INSERT OR REPLACE INTO trabajos (id, estado, creado, datos) VALUES (?,?,?,?)",
                (datos.get("id"), datos.get("estado"), datos.get("creado") or time.time(),
                 json.dumps(datos, ensure_ascii=False)))
    except Exception as e:
        print("trabajos: no pude guardar en disco:", e, flush=True)


def _serializable(v):
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


def leer(trabajo_id):
    fila = _correr("SELECT datos FROM trabajos WHERE id=?", (trabajo_id,), uno=True)
    return json.loads(fila[0]) if fila else None


def cargar(dias=DIAS_GUARDADOS):
    """Los trabajos de los ultimos `dias`, para volver a llenar el dict al arrancar."""
    desde = time.time() - dias * 86400
    filas = _correr("SELECT datos FROM trabajos WHERE creado >= ?", (desde,), todos=True)
    return [json.loads(f[0]) for f in filas]


# Los estados que quedan "colgados" si el panel se cae: nadie los va a terminar.
VIVOS = ("trabajando", "en_fila", "en_cola")


def marcar_interrumpidos(motivo="Se reinició el panel en medio del trabajo."):
    """Al arrancar: lo que figuraba corriendo ya no lo corre nadie. Devuelve esas fichas.

    ⚠ El turno en si puede haber terminado igual (el proceso de la charla no muere con el
    panel) y su respuesta queda en la charla: por eso el error lo dice.
    """
    salida = []
    for t in cargar():
        if t.get("estado") in VIVOS:
            t["estado"] = "interrumpido"
            t["error"] = t.get("error") or motivo
            t["terminado"] = time.time()
            guardar(t)
            salida.append(t)
    return salida


def podar(dias=DIAS_GUARDADOS):
    desde = time.time() - dias * 86400
    _correr("DELETE FROM trabajos WHERE creado < ?", (desde,))
