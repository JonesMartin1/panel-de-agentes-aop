"""Prueba los DOS candados del bot: transcribir (equipo) y hablarle a Laura.

Uso, desde la raiz del proyecto:
    python -m pruebas.test_bot_telegram_auth

El punto central a proteger: sumar gente a EQUIPO_IDS (para que prueben la
transcripcion) NUNCA tiene que abrirles la conversacion con Laura, que ejecuta
comandos en la PC de Martin. Son listas independientes, no una compartida.

NO levanta el bot ni pega contra Telegram: solo prueba las funciones de
autorizacion con un "Update" de mentira (lo unico que usan es .effective_user.id).
"""

from app.ingesta import bot_telegram as bt

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:62} -> {obtenido!r}")


class _Usuario:
    def __init__(self, uid):
        self.id = uid


class _UpdateFalso:
    """Lo minimo que _autorizado_equipo/_autorizado_laura miran: .effective_user.id."""
    def __init__(self, uid):
        self.effective_user = _Usuario(uid) if uid is not None else None


MARTIN = 111222333
COLEGA = 555111222
DESCONOCIDO = 999888777

print("=== Equipo cerrado a una lista (Martin + un colega agregado) ===")
bt.EQUIPO_IDS = {MARTIN, COLEGA}
bt.LAURA_IDS = {MARTIN}

_check("Martin transcribe", bt._autorizado_equipo(_UpdateFalso(MARTIN)), True)
_check("el colega agregado transcribe", bt._autorizado_equipo(_UpdateFalso(COLEGA)), True)
_check("un desconocido NO transcribe", bt._autorizado_equipo(_UpdateFalso(DESCONOCIDO)), False)

print("\n=== Laura: SOLO Martin, aunque el colega ya transcriba ===")
_check("Martin le habla a Laura", bt._autorizado_laura(_UpdateFalso(MARTIN)), True)
_check("el colega del equipo NO le habla a Laura", bt._autorizado_laura(_UpdateFalso(COLEGA)), False)
_check("un desconocido NO le habla a Laura", bt._autorizado_laura(_UpdateFalso(DESCONOCIDO)), False)

print("\n=== Equipo ABIERTO (vacio = cualquiera transcribe) ===")
bt.EQUIPO_IDS = set()
_check("un desconocido SI transcribe con el equipo abierto",
       bt._autorizado_equipo(_UpdateFalso(DESCONOCIDO)), True)
_check("pero Laura sigue cerrada aunque el equipo este abierto",
       bt._autorizado_laura(_UpdateFalso(DESCONOCIDO)), False)
_check("y Laura sigue dejando pasar solo a Martin",
       bt._autorizado_laura(_UpdateFalso(MARTIN)), True)

print("\n=== Laura vacia (sin configurar) NO se abre por defecto ===")
bt.LAURA_IDS = set()
_check("ni Martin le habla a Laura si LAURA_IDS quedo vacia",
       bt._autorizado_laura(_UpdateFalso(MARTIN)), False)

print("\n=== Update sin effective_user (no deberia pasar nunca) ===")
_check("equipo abierto igual filtra sin usuario", bt._autorizado_equipo(_UpdateFalso(None)), True)
bt.EQUIPO_IDS = {MARTIN}
_check("equipo cerrado sin usuario -> no", bt._autorizado_equipo(_UpdateFalso(None)), False)
_check("laura sin usuario -> no", bt._autorizado_laura(_UpdateFalso(None)), False)

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    raise SystemExit(1)
print("todo ok")
