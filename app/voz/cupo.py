"""Cuentakilometros de tokens: cuanto consumiste de cada cupo de Claude.

Por que existe: cada pregunta a Claude REENVIA toda la conversacion anterior. La
numero 50 le manda las 49 previas completas. Eso no se ve en ningun lado hasta que
te quedas sin cupo, y ahi Laura se calla y nadie sabe por que.

De donde salen los numeros: Claude Code guarda cada mensaje en su .jsonl con el
`usage` real (input, output, cache escrito, cache leido). Los leemos de ahi. Ojo con
esto, que es lo importante: mide TODAS tus sesiones de Claude Code, no solo las de
Laura. Las charlas de programacion son la mayor parte del consumo y Laura sola no
las ve. Medido el 2026-08-11: de 186 M de cache leido en 5 horas, 123 M eran una
sola conversacion de VS Code. El 66 %.

Lo que NO se puede: saber cuanto cupo te da tu plan. No esta en el disco. El
.credentials.json trae `subscriptionType` y `rateLimitTier` (que plan tenes) pero
nada del consumo. Asi que esto arranca siendo un ODOMETRO y no un tanque de nafta:
sabe cuanto gastaste, no cuanto te queda. Se convierte en tanque calibrandolo una vez
contra /usage (ver los LIMITE_* mas abajo).

SON TRES CUPOS, no uno, y el que se llena primero no es el que uno espera. Medido el
2026-08-11: el de 5 horas estaba al 14 %, el semanal al 58 % y el semanal de Fable al
83 %. Vigilar solo el de 5 horas es vigilar justo el que nunca se llena.

Y LAURA NO ES EL PROBLEMA, que era la sospecha que empezo todo esto. Medido por
modelo, 7 dias (ponderado):

    sonnet-5   (Laura)          2,7 M    0,2 %
    opus-4-8                  554,3 M   40,7 %
    opus-5     (VS Code)       409,4 M   30,1 %
    fable-5                   392,6 M   28,8 %

Laura corre Sonnet (MODELO en claude_voz.py) y sale 0,2 % de la semana. Ni siquiera
toca el cupo de Fable, que es el apretado. Hablarle mas al asistente de voz no te
deja sin cupo: lo que consume son las sesiones de programacion.

Uso desde la raiz del proyecto:
    python -m app.voz.cupo            # los tres cupos, con barra y porcentaje
    python -m app.voz.cupo 24         # el desglose por proyecto de las ultimas 24 h
"""

import json
import time
import threading
from datetime import datetime

from app.rutas import CLAUDE_PROYECTOS

VENTANA_SEG = 5 * 3600        # la ventana de la "sesion"
VENTANA_SEMANA = 7 * 24 * 3600

# ⭐ La semana de Claude NO es "los ultimos 7 dias": es una ventana FIJA que se
# renueva cada 7 dias en un momento puntual (se ve en /usage como "resets ...").
# Medir 7 dias moviles la sobreestima fuerte justo despues de cada renovacion:
# el 2026-08-11 el cupo se renovo y esto seguia mostrando la semana VIEJA entera
# como si nada. ANCLA_SEMANA es una renovacion conocida; las siguientes caen cada
# 7 dias justos y _ventana_semanal() mide solo desde la ultima.
# Dato de Martin (2026-08-11, leido de /usage): se renueva LOS MARTES A LAS 7 DE
# LA MAÑANA. El 11/8/2026 fue martes; de ahi en adelante cae cada 7 dias justos.
ANCLA_SEMANA = datetime(2026, 8, 11, 7, 0).timestamp()

# OJO calibracion: hasta el 19/8/2026 corre una promo de +50% en los limites
# semanales (visto en la config local de Claude Code). Los LIMITE_* de abajo se
# calibraron DURANTE la promo: despues del 19/8 hay que recalibrar contra /usage,
# porque los limites reales van a ser mas chicos.


def _ventana_semanal():
    """Segundos desde la ultima renovacion semanal (entre 0 y 7 dias)."""
    pasado = (time.time() - ANCLA_SEMANA) % VENTANA_SEMANA
    return max(pasado, 60.0)      # recien renovada: ventana minima, no cero

# Fable tiene su PROPIO cupo semanal, aparte del general. Es el que se llena primero.
MODELO_FABLE = "fable"

# --- Calibracion --------------------------------------------------------------
# Cuantos "tokens equivalentes de entrada" te da el plan en cada ventana. El limite
# NO esta en ningun archivo del disco: hay que sacarlo comparando lo que mide esto
# contra lo que dice /usage. Calibrado el 2026-08-11, plan Claude Max:
#
#   sesion 5 h  ->  medi   30,8 M  y /usage decia 12 %   ->  limite ~257 M
#   semana 7 d  ->  medi 1.362,4 M y /usage decia 58 %   ->  limite ~2.350 M
#
# OJO con la ventana de 5 h: la de Claude es FIJA (dice "resets in 3h"), esta es
# MOVIL. La movil siempre abarca igual o mas, asi que el aviso puede adelantarse un
# poco. Para avisar, errar por adelantado es el lado correcto.
LIMITE_SESION = 257_000_000
LIMITE_SEMANA = 2_350_000_000
#   Fable 7 d   ->  medi  394,3 M  y /usage decia 83 %   ->  limite ~475 M
LIMITE_SEMANA_FABLE = 475_000_000

AVISO_PORCENTAJE = 70         # avisa cuando pasaste este % de CUALQUIER limite
# Para RE-armar el aviso hace falta bajar de este otro numero, no del de arriba. Sin esa
# separacion, un cupo que queda oscilando en el filo del 70 % te avisa una y otra vez.
REARMAR_PORCENTAJE = 65
AVISO_TURNOS = 50             # ...y cuando la charla llega a esta cantidad de turnos
REFRESCO_SEG = 180            # cada cuanto recalcula la sesion, en segundo plano
REFRESCO_SEMANA = 1800        # la semanal se mueve despacio y cuesta mas de leer

# Peso de cada tipo de token, proporcional a lo que cuesta. Los limites del plan van
# por consumo real, no por token pelado: un token de salida sale ~5 veces un token de
# entrada, y uno leido del cache ~un decimo. Sin estos pesos, los 186 M de cache leido
# tapaban por completo los 756 mil de salida, que son los que de verdad pesan.
PESOS = {"input_tokens": 1.0,
         "cache_creation_input_tokens": 1.25,
         "cache_read_input_tokens": 0.1,
         "output_tokens": 5.0}

_cache = {}                   # clave de cupo -> (cuando se midio, datos)
_lock = threading.Lock()


def _cuando(d):
    """Timestamp de una linea del .jsonl, o None si no se puede leer."""
    ts = d.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def medir(ventana=VENTANA_SEG, modelo=None):
    """Suma el usage de TODAS las sesiones de Claude Code dentro de la ventana.

    modelo: si se pasa, cuenta SOLO los mensajes de ese modelo (por ejemplo "fable",
    que tiene cupo semanal propio). Los transcripts guardan message.model.
    """
    ahora = time.time()
    tot = dict.fromkeys(PESOS, 0)
    por_proyecto = {}
    archivos = 0
    if not CLAUDE_PROYECTOS.is_dir():
        return {"totales": tot, "por_proyecto": {}, "archivos": 0,
                "ponderado": 0.0, "ventana": ventana, "error": "no encontre las sesiones"}
    for p in CLAUDE_PROYECTOS.glob("*/*.jsonl"):
        try:
            # Si no se toco en la ventana no lo abro. El margen de una hora es por si
            # el reloj del archivo y el de los mensajes no coinciden.
            if ahora - p.stat().st_mtime > ventana + 3600:
                continue
        except OSError:
            continue
        archivos += 1
        entrada = por_proyecto.setdefault(p.parent.name, dict.fromkeys(PESOS, 0))
        try:
            with p.open(encoding="utf-8", errors="replace") as f:
                for linea in f:
                    if '"usage"' not in linea:       # filtro barato antes de parsear
                        continue
                    try:
                        d = json.loads(linea)
                    except Exception:
                        continue
                    t = _cuando(d)
                    if t is None or ahora - t > ventana:
                        continue
                    msg = d.get("message") or {}
                    if modelo and modelo not in (msg.get("model") or ""):
                        continue
                    u = msg.get("usage") or {}
                    for k in PESOS:
                        v = u.get(k) or 0
                        entrada[k] += v
                        tot[k] += v
        except OSError:
            continue
    por_proyecto = {k: v for k, v in por_proyecto.items() if sum(v.values())}
    return {"totales": tot, "por_proyecto": por_proyecto, "archivos": archivos,
            "ponderado": sum(tot[k] * PESOS[k] for k in PESOS), "ventana": ventana}


# Los TRES cupos que corren en paralelo. Cada uno con su ventana, su limite y cada
# cuanto vale la pena volver a medirlo. El nombre es como se dice en voz alta.
CUPOS = [
    ("sesion", "cupo de las cinco horas"   , VENTANA_SEG,    None,         "LIMITE_SESION",       REFRESCO_SEG),
    ("semana", "cupo semanal",               VENTANA_SEMANA, None,         "LIMITE_SEMANA",       REFRESCO_SEMANA),
    ("fable",  "cupo semanal de Fable"   ,   VENTANA_SEMANA, MODELO_FABLE, "LIMITE_SEMANA_FABLE", REFRESCO_SEMANA),
]


def datos(clave="sesion", max_edad=None):
    """La ultima medicion de un cupo. Recalcula si esta vieja (~3 s la semanal)."""
    cupo = next(c for c in CUPOS if c[0] == clave)
    _, _, ventana, modelo, _, refresco = cupo
    if ventana == VENTANA_SEMANA:
        ventana = _ventana_semanal()      # la semana fija de Claude, no 7 dias moviles
    if max_edad is None:
        max_edad = refresco
    with _lock:
        guardado = _cache.get(clave)
        if guardado and (time.time() - guardado[0]) < max_edad:
            return guardado[1]
    d = medir(ventana, modelo)                   # afuera del lock: tarda 1 a 3 s
    with _lock:
        _cache[clave] = (time.time(), d)
    return d


def porcentaje(clave="sesion"):
    """Cuanto de ese cupo usaste, 0-100. None si su limite no esta calibrado."""
    limite = globals().get(next(c[4] for c in CUPOS if c[0] == clave))
    if not limite:
        return None
    return 100.0 * datos(clave)["ponderado"] / limite


def estado(claves=None):
    """[(nombre hablado, porcentaje), ...] ordenado del mas apretado al menos.

    claves: para mirar solo algunos cupos. Sirve para no dar una pista falsa: Laura
    corre Sonnet y NO consume el cupo de Fable, asi que cuando ella se queda sin cupo
    nombrarle Fable manda a mirar el lugar equivocado.
    """
    filas = []
    for clave, nombre, _, _, cte, _ in CUPOS:
        if claves and clave not in claves:
            continue
        pct = porcentaje(clave)
        if pct is not None:
            filas.append((nombre, pct))
    return sorted(filas, key=lambda x: -x[1])


# Los cupos que SI consume Laura (corre Sonnet, ver MODELO en claude_voz.py).
CUPOS_DE_LAURA = ("sesion", "semana")

# ⭐ Los cupos por los que vale la pena INTERRUMPIRTE hablando. Fable queda afuera a
# pedido: es el que menos importa saber cuando estas laburando, porque no es algo sobre
# lo que puedas hacer nada en el momento. Se sigue midiendo y se sigue viendo en
# `python -m app.voz.cupo` — lo unico que no hace es abrir la boca.
CUPOS_QUE_AVISAN = ("sesion", "semana")


_cruzados = set()             # cupos que ya avisaron: no repiten hasta bajar de nuevo


def frase_aviso(nombre, pct):
    """Como se dice en voz alta. Corto y sin numeros raros: lo lee Piper."""
    return (f"Ojo, estas llegando al limite: ya usaste el {pct:.0f} por ciento "
            f"del {nombre}.")


def _vigilar(al_cruzar=None):
    """Mide en segundo plano y, si un cupo cruza el umbral, avisa UNA vez.

    El aviso no se dice aca: se lo pasamos a al_cruzar(frase), que en voz.py espera a
    que no estes hablando ni escuchando antes de abrir la boca. Un aviso que te corta
    la frase en la mitad es peor que no avisar.
    """
    while True:
        for clave, nombre, _, _, _, _ in CUPOS:
            try:
                datos(clave, max_edad=0)         # fuerza el recalculo
                pct = porcentaje(clave)
            except Exception as e:
                print(f"cupo: fallo medir {clave}:", e, flush=True)
                continue
            if pct is None:
                continue
            if clave not in CUPOS_QUE_AVISAN:
                continue                         # se mide, pero no te interrumpe (Fable)
            if pct >= AVISO_PORCENTAJE and clave not in _cruzados:
                _cruzados.add(clave)
                print(f"cupo: {nombre} al {pct:.0f}% -> aviso", flush=True)
                if al_cruzar:
                    try:
                        al_cruzar(frase_aviso(nombre, pct))
                    except Exception as e:
                        print("cupo: no pude avisar:", e, flush=True)
            elif pct < REARMAR_PORCENTAJE and clave in _cruzados:
                _cruzados.discard(clave)         # se reseteo la ventana: puede volver a avisar
                print(f"cupo: {nombre} bajo al {pct:.0f}%, aviso rearmado", flush=True)
        time.sleep(REFRESCO_SEG)


def arrancar_vigilancia(al_cruzar=None):
    """Mide en segundo plano, asi consultar el porcentaje es instantaneo.

    al_cruzar: funcion que recibe la frase a decir cuando un cupo pasa el umbral.
    """
    threading.Thread(target=_vigilar, args=(al_cruzar,), daemon=True).start()


def _m(n):
    """Numero grande en algo que se pueda decir en voz alta."""
    if n >= 1e6:
        return f"{n / 1e6:.1f} millones".replace(".0 ", " ")
    if n >= 1000:
        return f"{n / 1000:.0f} mil"
    return str(int(n))


def aviso_cupo():
    """Frase corta si te queda poco de ALGUN cupo, o None.

    Va PEGADA AL FINAL de la respuesta. Avisa por el mas apretado de los tres, no
    solo por el de 5 horas: medido el 2026-08-11, el de 5 horas estaba al 12 % y el
    semanal de Fable al 83 %. Vigilar solo la sesion era vigilar el que nunca se
    llena, y te ibas a quedar sin cupo igual, sin aviso.
    """
    filas = estado(claves=CUPOS_QUE_AVISAN)        # sin Fable: no te interrumpe por eso
    if not filas:
        return None
    nombre, pct = filas[0]
    if pct < AVISO_PORCENTAJE:
        return None
    return f"Ojo, del {nombre} te queda un {max(0, 100 - pct):.0f} por ciento."


def main(argv=None):
    argv = argv or []
    horas = float(argv[0]) if argv else 5.0
    d = medir(int(horas * 3600))
    t = d["totales"]
    print(f"\nUltimas {horas:g} horas ({d['archivos']} sesiones tocadas)\n")
    print(f"  {'proyecto':40} {'ponderado':>13}")
    for proy, e in sorted(d["por_proyecto"].items(),
                          key=lambda x: -sum(x[1][k] * PESOS[k] for k in PESOS)):
        pond = sum(e[k] * PESOS[k] for k in PESOS)
        pct = 100 * pond / d["ponderado"] if d["ponderado"] else 0
        print(f"  {proy[:40]:40} {pond:>13,.0f}  {pct:4.0f}%")
    print()
    for k in PESOS:
        print(f"  {k:34} {t[k]:>14,}  (peso {PESOS[k]})")
    print(f"\n  EQUIVALENTE PONDERADO: {d['ponderado']:,.0f}  (~{_m(d['ponderado'])})")

    print("\n  LOS TRES CUPOS (del mas apretado al menos):\n")
    for clave, nombre, ventana, modelo, cte, _ in CUPOS:
        limite = globals().get(cte)
        if ventana == VENTANA_SEMANA:
            ventana = _ventana_semanal()
        m = medir(ventana, modelo)
        if limite:
            pct = 100 * m["ponderado"] / limite
            barra = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
            print(f"  {nombre:30} [{barra}] {pct:4.0f}%   "
                  f"{_m(m['ponderado'])} de {_m(limite)}")
        else:
            print(f"  {nombre:30} sin calibrar ({_m(m['ponderado'])} usados)")
    aviso = aviso_cupo()
    print(f"\n  Aviso hablado ahora: {aviso or '(ninguno, todo por debajo del ' + str(AVISO_PORCENTAJE) + '%)'}")
    print("\n  Para recalibrar: escribi /usage en Claude Code y compara los porcentajes")
    print("  con estos. Si difieren, ajusta los LIMITE_* de arriba de este archivo.")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
