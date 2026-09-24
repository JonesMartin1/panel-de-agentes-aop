"""Prueba el buzon de Laura por Telegram: ida, vuelta, ids y preguntas viejas.

Uso, desde la raiz del proyecto:
    python -m pruebas.test_buzon

Redirige los archivos del buzon al temp: NO toca los reales ni levanta servicios.
"""

import json
import time
import tempfile
from pathlib import Path

from app.voz import buzon

# Redirigir el buzon a archivos de mentira ANTES de usarlo. Las funciones leen los
# globales del modulo, asi que pisarlos alcanza.
_tmp = Path(tempfile.gettempdir())
buzon.LAURA_PREGUNTA = _tmp / "prueba_laura_pregunta.json"
buzon.LAURA_RESPUESTA = _tmp / "prueba_laura_respuesta.json"
buzon.LAURA_PREGUNTA.unlink(missing_ok=True)
buzon.LAURA_RESPUESTA.unlink(missing_ok=True)

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:56} -> {obtenido!r}")


# --- Ida y vuelta completa, como la usan el bot y voz.py ---------------------------
print("ida y vuelta:")
_check("sin pregunta, voz no saca nada", buzon.sacar_pregunta(), None)

pid = buzon.dejar_pregunta("hola Laura, desde el telefono")
_check("con pregunta puesta, todavia no fue tomada", buzon.pregunta_tomada(), False)

p = buzon.sacar_pregunta()
_check("voz saca el texto", p and p["texto"], "hola Laura, desde el telefono")
_check("voz saca el mismo id", p and p["id"], pid)
_check("al sacarla queda tomada", buzon.pregunta_tomada(), True)
_check("no se puede sacar dos veces", buzon.sacar_pregunta(), None)

_check("sin respuesta aun, el bot no ve nada", buzon.sacar_respuesta(pid), None)
buzon.dejar_respuesta(pid, "hola Martin, aca estoy")
_check("respuesta con id ajeno NO se entrega", buzon.sacar_respuesta("otro-id"), None)
_check("respuesta con id propio si", buzon.sacar_respuesta(pid), "hola Martin, aca estoy")
_check("y se consume al leerla", buzon.sacar_respuesta(pid), None)

# --- Abandono: el bot se rinde y limpia -------------------------------------------
print("abandono:")
buzon.dejar_pregunta("¿hay alguien?")
buzon.abandonar()
_check("tras abandonar no queda pregunta", buzon.sacar_pregunta(), None)

# --- Pregunta vieja: de una corrida muerta del bot, no se contesta -----------------
print("pregunta vieja:")
buzon.LAURA_PREGUNTA.write_text(json.dumps(
    {"id": "viejo", "texto": "fantasma", "ts": time.time() - buzon.PREGUNTA_VIEJA_SEG - 1}),
    encoding="utf-8")
_check("una pregunta vencida se descarta", buzon.sacar_pregunta(), None)
_check("y ademas se borra del disco", buzon.LAURA_PREGUNTA.exists(), False)

# --- Un archivo roto no tira el vigilante ------------------------------------------
print("archivo roto:")
buzon.LAURA_PREGUNTA.write_text("esto no es json", encoding="utf-8")
_check("json roto -> None, sin explotar", buzon.sacar_pregunta(), None)
buzon.LAURA_PREGUNTA.unlink(missing_ok=True)

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    raise SystemExit(1)
print("todo ok")
