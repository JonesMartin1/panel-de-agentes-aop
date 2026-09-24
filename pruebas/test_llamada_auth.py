"""Prueba el candado de la llamada por celular: token y limite de intentos.

Uso, desde la raiz del proyecto:
    python -m pruebas.test_llamada_auth

NO arranca el servidor (arrancar() levantaria uvicorn en un puerto real): solo
prueba las funciones de candado, fijando el token del modulo a mano.

NO importa voz.py (abriria el microfono): llamada.py esta hecho justo para poder
probarse asi, sin los objetos pesados (Whisper, Piper) que arrancar() recibe
inyectados en vez de importar el mismo.
"""

from fastapi import HTTPException

from app.voz import llamada as ll

_fallos = []


def _check(que, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        _fallos.append(f"{que}: esperaba {esperado!r}, dio {obtenido!r}")
    print(f"  {'ok ' if ok else 'MAL'} {que:56} -> {obtenido!r}")


class _ClienteFalso:
    def __init__(self, host):
        self.host = host


class _RequestFalso:
    def __init__(self, ip=None, cf_ip=None):
        self.client = _ClienteFalso(ip) if ip else None
        self.headers = {"cf-connecting-ip": cf_ip} if cf_ip else {}


def _intenta(request, token):
    try:
        ll._verificar(request, token)
        return "ok"
    except HTTPException as e:
        return e.status_code


ll._token = "el-secreto-correcto"
ll._FALLOS.clear()

print("=== Token correcto / incorrecto ===")
_check("token correcto pasa", _intenta(_RequestFalso(ip="1.1.1.1"), "el-secreto-correcto"), "ok")
_check("token vacio -> 401", _intenta(_RequestFalso(ip="2.2.2.2"), ""), 401)
_check("token incorrecto -> 401", _intenta(_RequestFalso(ip="2.2.2.2"), "otro"), 401)

print("\n=== Sin token configurado, NADIE pasa (ni con la clave vieja) ===")
ll._token = ""
_check("sin token configurado -> 401 igual con la clave correcta",
       _intenta(_RequestFalso(ip="3.3.3.3"), "el-secreto-correcto"), 401)
ll._token = "el-secreto-correcto"

print("\n=== Limite de intentos fallidos, por IP ===")
ll._FALLOS.clear()
ip_atacante = "9.9.9.9"
for i in range(ll.MAX_FALLOS):
    _check(f"intento fallido {i + 1}/{ll.MAX_FALLOS}", _intenta(_RequestFalso(ip=ip_atacante), "mal"), 401)
_check("un intento mas, ahora bloqueado -> 429",
       _intenta(_RequestFalso(ip=ip_atacante), "mal"), 429)
_check("bloqueado AUNQUE mande el token correcto",
       _intenta(_RequestFalso(ip=ip_atacante), "el-secreto-correcto"), 429)
_check("otra IP no se ve afectada por el bloqueo de la primera",
       _intenta(_RequestFalso(ip="8.8.8.8"), "el-secreto-correcto"), "ok")

print("\n=== La IP real es la de Cloudflare (CF-Connecting-IP), no la del tunel ===")
ll._FALLOS.clear()
r = _RequestFalso(ip="127.0.0.1", cf_ip="5.5.5.5")
_check("_ip_de prioriza cf-connecting-ip sobre el client.host del tunel",
       ll._ip_de(r), "5.5.5.5")

print("\n=== Extension del archivo temporal segun el tipo de audio del navegador ===")
_check("webm", ll._sufijo_de("audio/webm;codecs=opus"), ".webm")
_check("ogg", ll._sufijo_de("audio/ogg"), ".ogg")
_check("mp4 (Safari/iOS)", ll._sufijo_de("audio/mp4"), ".mp4")
_check("desconocido -> generico", ll._sufijo_de("lo que sea"), ".bin")

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    raise SystemExit(1)
print("todo ok")
