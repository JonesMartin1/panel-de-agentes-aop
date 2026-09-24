"""Cuánto cuesta refrescar la charla más pesada de Codex, antes y después del arreglo.

Se corre contra los rollouts DE VERDAD (solo lectura, no toca nada). Es la medición que
justifica la ventana incremental: con el rollout de 741 MB de Portafolio, cada refresco
de la pantalla —cada 3 segundos, en la compu y en el celular— leía y parseaba 255 MB.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.ver_ventana_codex_real
"""
import json
import sys
import time

from app.voz import sesiones_movil as sm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def vieja(ruta, ultimos=40):
    """El algoritmo anterior: cola que se duplica y json.loads en CADA renglón."""
    est = ruta.stat()
    leidos = 0
    cola = 512 * 1024
    while True:
        inicio = max(0, est.st_size - cola)
        with open(ruta, "rb") as f:
            f.seek(inicio)
            if inicio:
                f.readline()
            crudo = f.read()
        leidos += len(crudo)
        filas = []
        for linea in crudo.decode("utf-8", errors="replace").splitlines():
            try:
                d = json.loads(linea)
            except Exception:
                continue
            if d.get("type") != "response_item":
                continue
            pay = d.get("payload") or {}
            if pay.get("type") != "message" or pay.get("role") not in ("user", "assistant"):
                continue
            if any(isinstance(c, dict) and c.get("text") for c in (pay.get("content") or [])):
                filas.append(1)
        if len(filas) >= ultimos or inicio == 0:
            return len(filas), leidos
        cola = min(est.st_size, cola * 2)


sm._codex_barrer()
pesos = []
for sid in list(sm._CODEX_SIDS):
    p = sm._codex_archivo(sid)
    if p:
        pesos.append((p.stat().st_size, sid, p))
pesos.sort(reverse=True)
tam, sid, ruta = pesos[0]
print(f"la charla más pesada: {tam/1048576:.0f} MB\n")

print("--- ANTES (lo que hacía cada refresco) ---")
ini = time.time()
cuantos, leidos = vieja(ruta)
print(f"  {time.time()-ini:6.2f}s   leyó {leidos/1048576:6.1f} MB   ({cuantos} mensajes)")

print("\n--- AHORA ---")
ini = time.time()
filas = sm._codex_mensajes(sid, 40)
print(f"  primera vez:  {time.time()-ini:6.2f}s   ({len(filas)} mensajes)")
for i in (1, 2, 3):
    sm._CODEX_HILOS.clear()          # como cuando la sesión escribió y el cache se cae
    ini = time.time()
    sm._codex_mensajes(sid, 40)
    print(f"  refresco {i}:   {time.time()-ini:6.3f}s")

print("\n--- la bandeja: título de las 63 charlas (1,4 GB en total) ---")
sm._CODEX_TITULOS.clear()
ini = time.time()
for _, s, _p in pesos:
    sm._codex_titulo(s)
print(f"  {time.time()-ini:6.2f}s   (antes leía cada rollout entero)")
