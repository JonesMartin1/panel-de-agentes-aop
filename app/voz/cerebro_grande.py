"""
El interruptor entre los dos cerebros GRANDES de Laura: Claude Code y Codex (OpenAI).

⚠ No confundir con `cerebro.py`, que es el LLM LOCAL (Ollama) que resuelve comandos
y charla corta. "Cerebro grande" es como el resto del proyecto llama al que piensa
de verdad y tiene manos para tocar la computadora.

Quien le pregunta a Laura —`voz.py`, el chat del panel, Telegram— habla con este
modulo, que reenvia todo al que este puesto. Asi cambiar de cerebro es cambiar una
palabra en un archivo, y no tocar los quince lugares que llaman a `preguntar()`.

    from app.voz import cerebro_grande
    cerebro_grande.preguntar("hola")     # va al que este activo
    cerebro_grande.usar("codex")         # y desde aca en mas, al otro

CADA CEREBRO LLEVA SU PROPIA CHARLA. Los ids de sesion no son intercambiables (una
conversacion de Claude no se puede reanudar en Codex), asi que al cambiar no se
"muda" el hilo: se retoma la charla que ese cerebro tenia. Es a proposito y hay que
decirlo cuando se cambia, o parece que Laura se quedo sin memoria.

PERO EL QUE ENTRA SE ENTERA DE LO QUE VENIAMOS HABLANDO: al cambiar se copian los
ultimos caracteres de la charla del que se va y se le pegan al primer mensaje del
que entra ("traspaso"). No es la misma sesion —el que entra no puede seguir la del
otro— pero al menos no te hace repetir todo. Se le pide el resumen al que se va NO,
a proposito: sumaba varios segundos a cada cambio y el texto pelado alcanza.

Cual esta puesto vive en `cerebro.json` y no en una variable: el panel es OTRO
proceso, y una variable de aca no se enteraria nunca de que apretaste el boton.
Mismo criterio que el modelo elegido (ver `claude_voz.modelo_actual`).
"""

import json
import re
import time

from app.rutas import CEREBRO

CEREBROS = {
    "claude": {"modulo": "app.voz.claude_voz", "nombre": "Claude"},
    "codex":  {"modulo": "app.voz.codex_voz",  "nombre": "Codex"},
}
DEFECTO = "claude"

# Cuanto de la charla que se va le pasamos al que entra. 8000 caracteres son varios
# turnos de Laura (contesta en dos frases) y no le comen la ventana al que llega.
TRASPASO_MAX = 8000

# A este porcentaje de cupo gastado, Codex ya no se usa: `preguntar` se pasa solo a
# Claude ANTES de chocar el limite (el dato sale de `codex_voz.cupo()`). Si Martin
# pide Codex sabiendo que esta al limite, se le respeta (llave `cupo_ok` en
# cerebro.json) hasta que el cupo baje del tope.
CUPO_TOPE = 90

# Se relee del disco, pero no en cada llamada: `preguntar` puede correr varias veces
# por turno y abrir el archivo cada vez es al pedo. Medio segundo de cache alcanza
# para enterarse enseguida de un cambio hecho desde el panel.
_CACHE_SEG = 0.5
_cache = (0.0, None)


def _leer_config():
    """Todo `cerebro.json`: cual esta puesto y el traspaso pendiente, si hay."""
    try:
        d = json.loads(CEREBRO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _guardar_config(d):
    CEREBRO.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def activo():
    """Cual esta puesto ahora: "claude" o "codex"."""
    global _cache
    ahora = time.time()
    if _cache[1] and ahora - _cache[0] < _CACHE_SEG:
        return _cache[1]
    valor = DEFECTO
    d = _leer_config()
    if d.get("activo") in CEREBROS:
        valor = d["activo"]
    _cache = (ahora, valor)
    return valor


def como_se_llama(clave=None):
    """El nombre para decir en voz alta ("Claude", "Codex")."""
    return CEREBROS[clave or activo()]["nombre"]


def modulo(clave=None):
    """El modulo del cerebro pedido, importado a demanda."""
    import importlib
    return importlib.import_module(CEREBROS[clave or activo()]["modulo"])


def usar(clave):
    """Cambia de cerebro y devuelve una frase corta para decir en voz alta."""
    global _cache
    if clave not in CEREBROS:
        return None
    if clave == activo():
        return f"Ya estabas hablando con {como_se_llama(clave)}."
    sale = activo()
    charla = _charla_que_se_va(sale)
    cfg = _leer_config()
    cfg["activo"] = clave
    # El traspaso se guarda ACA y no se le manda al que entra en el momento: si no,
    # apretar el boton del panel dispararia una consulta entera (y varios segundos)
    # sin que Martin haya preguntado nada.
    if charla:
        cfg["traspaso"] = {"para": clave, "de": como_se_llama(sale), "texto": charla}
    else:
        cfg.pop("traspaso", None)
    # Si pide Codex estando al limite del cupo, se le avisa pero se le hace caso:
    # `cupo_ok` le dice a `preguntar` que no lo devuelva solo a Claude.
    aviso_cupo = ""
    if clave == "codex":
        c = _cupo_usado()
        if c is not None and c >= CUPO_TOPE:
            cfg["cupo_ok"] = True
            aviso_cupo = f" Ojo que ya gastó el {c:.0f} por ciento de su cupo."
        else:
            cfg.pop("cupo_ok", None)
    else:
        cfg.pop("cupo_ok", None)
    try:
        _guardar_config(cfg)
    except Exception as e:
        print("cerebro grande: no pude guardar la eleccion:", e, flush=True)
        return "No pude cambiar de cerebro."
    _cache = (0.0, None)
    print(f"cerebro grande: ahora pienso con {como_se_llama(clave)}"
          f"{' (le paso %d caracteres de la charla)' % len(charla) if charla else ''}",
          flush=True)
    try:
        modulo(clave).precalentar()          # que la primera consulta ya salga rapida
    except Exception:
        pass
    if charla:
        return (f"Listo, ahora pienso con {como_se_llama(clave)}, "
                "y le paso lo que veniamos hablando." + aviso_cupo)
    return (f"Listo, ahora pienso con {como_se_llama(clave)}. "
            "Ojo que cada uno se acuerda de su propia charla." + aviso_cupo)


# --- El traspaso: que el que entra sepa de que veniamos hablando -----------------
_PLANTILLA = (
    "[Contexto: hasta recien Martin venia hablando con {de} y acaba de cambiarte a vos. "
    "Abajo va lo ultimo de esa charla para que no pierda el hilo. Leelo y usalo si hace "
    "falta, pero no lo comentes ni lo resumas: contesta solo lo que te dice al final.]\n\n"
    "{charla}\n\n"
    "[Fin de lo anterior. Esto es lo que te dice ahora:]\n\n{consulta}"
)


def _charla_que_se_va(clave):
    """Lo ultimo que hablamos con el cerebro que sale, en texto pelado."""
    try:
        m = modulo(clave)
        sid = getattr(m, "_SESION", None)
        if not sid:
            return ""
        return m._charla_de(sid, max_chars=TRASPASO_MAX) or ""
    except Exception as e:
        print("cerebro grande: no pude leer la charla del que se va:", e, flush=True)
        return ""


def _con_traspaso(consulta):
    """Le pega el traspaso al primer mensaje despues de un cambio, y lo borra."""
    cfg = _leer_config()
    t = cfg.get("traspaso") or {}
    if not t.get("texto") or t.get("para") != activo():
        return consulta
    cfg.pop("traspaso", None)
    try:
        _guardar_config(cfg)
    except Exception as e:
        # Si no lo puedo borrar, mejor no usarlo: se repetiria en cada turno.
        print("cerebro grande: no pude borrar el traspaso, lo salteo:", e, flush=True)
        return consulta
    print(f"cerebro grande: le paso a {como_se_llama()} {len(t['texto'])} caracteres "
          "de lo que veniamos hablando", flush=True)
    return _PLANTILLA.format(de=t.get("de") or "el otro cerebro",
                             charla=t["texto"], consulta=consulta)


# --- El medidor de cupo: pasarse a Claude ANTES de que Codex choque el limite ----
def _cupo_usado():
    """El porcentaje de cupo gastado de Codex, o None si no se puede saber."""
    try:
        c = modulo("codex").cupo()
        return c.get("usado") if c else None
    except Exception:
        return None


def _esquivar_cupo():
    """Si Codex viene al limite, cambia a Claude y devuelve la frase que lo avisa.

    Es la mitad preventiva del fallback: `_si_fallo_probar_el_otro` actua cuando
    Codex YA no contesta; esto lo ve venir (el `rate_limits` que Codex anota en sus
    rollouts) y cambia antes, asi el turno no paga un intento que va a fallar.
    Devuelve "" si no hay que hacer nada.
    """
    c = _cupo_usado()
    if c is None:
        return ""
    cfg = _leer_config()
    if c < CUPO_TOPE:
        if cfg.get("cupo_ok"):          # el cupo se renovo: la proteccion se rearma
            cfg.pop("cupo_ok", None)
            _guardar_config(cfg)
        return ""
    if cfg.get("cupo_ok"):              # Martin lo eligio sabiendo del cupo: se respeta
        return ""
    print(f"cerebro grande: Codex va {c:.0f}% del cupo, me paso a Claude antes de chocar",
          flush=True)
    usar("claude")
    return (f"Ojo: Codex ya gastó el {c:.0f} por ciento de su cupo, "
            "así que seguí con Claude.")


def preguntar(consulta, reintentar=True, crudo=False, para_voz=True):
    """Igual que el `preguntar` del cerebro puesto, pero entregando el traspaso.

    Esta definido aca (y no reenviado por `__getattr__`) justo para poder meter el
    traspaso en el medio sin tocar los dos cerebros. Con `crudo` no se toca: esos
    son los pedidos internos (resumenes, siembra), no lo que Martin esta diciendo.
    """
    if crudo:
        return modulo().preguntar(consulta, reintentar=reintentar, crudo=True,
                                  para_voz=para_voz)

    consulta = _con_traspaso(consulta)
    clave = activo()
    aviso = ""
    if clave == "codex":
        aviso = _esquivar_cupo()
        if aviso:
            clave = activo()                    # ahora es Claude
            consulta = _con_traspaso(consulta)  # `usar` dejo el traspaso listo
    # ⭐ Esta marca es la que hace que en el chat del panel se vea QUIEN contesto.
    # La lee `/chat` en panel.py: si le cambias el texto, cambialo alla tambien.
    print(f"cerebro turno: {clave}", flush=True)
    r = modulo(clave).preguntar(consulta, reintentar=reintentar, crudo=False,
                                para_voz=para_voz)
    r = _si_fallo_probar_el_otro(r, consulta, clave, para_voz)
    if aviso and isinstance(r, str) and r:
        return aviso + " " + r
    return r


# --- Si un cerebro se cae, seguimos con el otro ----------------------------------
# Las frases con las que cada cerebro avisa que no pudo. Son suyas (`claude_voz` y
# `codex_voz`): si alla cambian, aca hay que tocarlo.
_FALLAS = ("no pude hablar con", "no me devolvio respuesta")


def _si_fallo_probar_el_otro(r, consulta, clave, para_voz):
    """Cuando el cerebro puesto no contesta, se cambia al otro y se le pregunta a el.

    Es para cuando uno se cae de verdad (se quedo sin cupo, no arranca el CLI): antes
    te quedabas con un "no pude hablar con Claude" y a mano tenias que cambiar vos.
    El cambio queda hecho, asi que el resto de la charla sigue con el que anduvo.
    """
    if not r or not any(f in str(r).lower() for f in _FALLAS):
        return r
    otro = next((k for k in CEREBROS if k != clave), None)
    if not otro:
        return r
    print(f"cerebro grande: {como_se_llama(clave)} no contesto, paso a "
          f"{como_se_llama(otro)}", flush=True)
    usar(otro)                              # deja el traspaso listo para el que entra
    print(f"cerebro turno: {otro}", flush=True)
    r2 = modulo(otro).preguntar(_con_traspaso(consulta), reintentar=False, crudo=False,
                                para_voz=para_voz)
    if not r2 or any(f in str(r2).lower() for f in _FALLAS):
        return f"No me contesta ninguno de los dos cerebros, ni {como_se_llama(clave)} ni {como_se_llama(otro)}."
    return (f"{como_se_llama(clave)} no me contesto, asi que segui con "
            f"{como_se_llama(otro)}. {r2}")


# --- "Laura, pasate a Codex" ----------------------------------------------------
# Lo dice hablando, asi que el patron tiene que aguantar el dictado. "Codex" le sale
# bien a Whisper, pero "Claude" lo escribe de mil formas ("cloud", "clod", "clau").
# El verbo es obligatorio: sin el, mencionar a Codex en una charla ("que te parece
# Codex?") cambiaria de cerebro en vez de contestarte.
_PEDIDO = re.compile(
    r"\b(pas[aá]\w*|cambi[aá]\w*|and[aá]|volv[eé]\w*|us[aá]\w*|habl[aá]\w*|pon[eé]\w*)\b"
    r"[^.]{0,30}?\b(codex|cod[eé]s|claude|cloud|clod|cla[uw]d\w*|gpt|open ?a\.?i)\b",
    re.IGNORECASE)
_ES_CODEX = re.compile(r"\b(codex|cod[eé]s|gpt|open ?a\.?i)\b", re.IGNORECASE)


def pedido_de_cambio(texto):
    """Si estas pidiendo cambiar de cerebro, devuelve cual. Si no, None.

    Lo llama `voz.py` ANTES de rutear, igual que el saludo del dia: si no, "pasate
    a Codex" se le manda como pregunta al cerebro que justo esta puesto, te contesta
    que si, y no cambia nada.
    """
    if not texto or not _PEDIDO.search(texto):
        return None
    return "codex" if _ES_CODEX.search(texto) else "claude"


def __getattr__(nombre_attr):
    """Todo lo demas (preguntar, cancelar, olvidar, _SESION...) va al cerebro puesto.

    PEP 562: esto corre solo cuando el atributo no existe en este modulo, asi que
    `activo`, `usar` y compania siguen siendo de aca.
    """
    return getattr(modulo(), nombre_attr)
