"""Prueba de punta a punta del botón Parar: lanza un turno de verdad y lo corta.

Manda un pedido largo a una sesión nueva, espera unos segundos a que el proceso
`claude` esté trabajando, y pide pararlo. Chequea que el proceso existía y que el
turno vuelve como error (que es lo que la pantalla sabe no pintar de rojo).

⚠ Desde el 2026-08-20 el proceso NO tiene que morir: Parar manda el `interrupt` por
stdin y el proceso queda vivo esperando el próximo mensaje, para no llevarse puesto lo
que la sesión haya mandado a segundo plano. Antes esta prueba esperaba lo contrario.
Lo que sigue midiendo es que el turno se corta; el detalle fino, sin gastar tokens ni
depender del panel, está en `probar_sesion_persistente.py`.
"""
import json
import threading
import time
import urllib.request

import psutil

PANEL = "http://127.0.0.1:8750"
CWD = "D:/IA/wpp-transcriptor"
LARGO = ("Sin usar herramientas, escribime un ensayo largo sobre la historia del "
         "ferrocarril argentino, con muchos detalles.")


def _post(ruta, datos):
    req = urllib.request.Request(PANEL + ruta, data=json.dumps(datos).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _mandar(caja):
    import urllib.parse
    cuerpo = urllib.parse.urlencode({"cwd": CWD, "sid": "", "texto": LARGO}).encode()
    req = urllib.request.Request(PANEL + "/movil/mandar", data=cuerpo)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            caja["r"] = json.loads(r.read())
    except Exception as e:
        caja["r"] = {"ok": False, "error": str(e)}


def claudes():
    n = 0
    for p in psutil.process_iter(["cmdline"]):
        c = " ".join(p.info["cmdline"] or [])
        if "claude" in c.lower() and "--output-format" in c:
            n += 1
    return n


def main():
    antes = claudes()
    caja = {}
    hilo = threading.Thread(target=_mandar, args=(caja,), daemon=True)
    hilo.start()

    for _ in range(30):                       # esperar a que arranque el proceso
        time.sleep(1)
        if claudes() > antes:
            break
    corriendo = claudes() > antes
    print("arrancó el turno:", corriendo)
    if not corriendo:
        print("no llegó a arrancar; no se puede probar el corte")
        return

    r = _post("/movil/parar", {"sid": "", "cwd": CWD})
    print("el panel dice que paró:", r)

    hilo.join(timeout=60)
    r = caja.get("r") or {}
    cortado = not r.get("ok") or "parad" in str(r.get("error", "")).lower()
    print("el turno volvió como:", str(r)[:120])
    print("el turno se cortó:", cortado)
    # ⚠ Al revés que antes: el proceso TIENE que seguir vivo (ver el docstring).
    time.sleep(2)
    print("el proceso sigue vivo (así tiene que ser):", claudes() > antes)


if __name__ == "__main__":
    main()
