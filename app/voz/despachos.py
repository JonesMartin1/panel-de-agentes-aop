"""Los DESPACHOS de una sesión que dirige a otras (la skill `chief`), 2026-11-11.

Pedido de Martín: mientras el chief espera a que otra sesión termine, no había ninguna
señal de vida. Mirando la charla de la otra creyó que había terminado y seguía trabajando.
De acá sale la tarjeta "Despachos" de la columna derecha de `/sesiones`: un renglón por
sesión a la que el chief le mandó algo, con su estado y hace cuánto.

Todo sale de las FICHAS de los trabajos (`_TRABAJOS_MOVIL` en `panel.py`): cuando el pedido
entra por `/movil/mandar` con el campo `jefe`, la ficha guarda quién lo despachó. No hay
ningún registro aparte, así que un reinicio del panel no pierde nada (las fichas viven
también en el disco) y lo que estaba corriendo queda como "se cortó".

Este módulo no sabe nada del panel: `armar` recibe las fichas y tres funciones, y por eso
se puede probar (y romper a propósito) sin levantar nada. `pruebas/probar_despachos.py`.
"""
import time

# Los terminados se quedan a la vista este rato; los que siguen vivos, siempre.
VENTANA_SEG = 12 * 3600
# Más renglones que estos no entran cómodos en la columna.
TOPE = 8
# Los estados de una ficha que quieren decir "todavía no cerró".
VIVOS = ("trabajando", "en_fila", "en_cola")
# Cómo se le dice en la pantalla a cada estado ya cerrado de la ficha.
CERRADOS = {"terminado": "termino", "fallo": "fallo",
            "interrumpido": "corto", "cancelado": "paro"}


def armar(fichas, sid, ahora=None, resolver=None, nombre_de=None, pregunta_de=None):
    """Los renglones de la tarjeta para la sesión `sid`, el más urgente primero.

      fichas       las fichas de los trabajos (dicts); solo cuentan las que traen `jefe`
      resolver     id -> el id vigente de esa charla (una compactada sigue en otra)
      nombre_de    (cwd, sid, cerebro) -> cómo se llama esa charla
      pregunta_de  (cwd, sid) -> la pregunta o el plan que tiene esperando, o None

    Cada renglón: {trabajo, sid, cwd, nombre, cerebro, estado, desde}. `estado` es
    trabaja | pregunta | termino | fallo | corto | paro, y `desde` la hora desde la que
    vale. ⚠ Nunca viaja la respuesta del trabajo: esto se pide cada pocos segundos.
    """
    ahora = time.time() if ahora is None else ahora
    vistos = {}

    def vigente(s):
        s = (s or "").strip()
        if not s:
            return ""
        if s not in vistos:
            try:
                vistos[s] = (resolver(s) if resolver else s) or s
            except Exception:
                vistos[s] = s
        return vistos[s]

    yo = vigente(sid)
    if not yo:
        return []
    # ⭐ Un renglón por sesión destino: si le mandó dos cosas, cuenta la más nueva.
    por_destino = {}
    for t in fichas or []:
        jefe = (t.get("jefe") or "").strip()
        # ⭐ Se compara por el id VIGENTE de los dos lados: el chief cambia de id cada vez
        # que se compacta, y sus despachos de antes tienen que seguirlo.
        if not jefe or vigente(jefe) != yo:
            continue
        vivo = t.get("estado") in VIVOS
        creado = t.get("creado") or 0
        cerro = t.get("terminado") or creado
        if not vivo and ahora - cerro > VENTANA_SEG:
            continue
        destino = vigente(t.get("sid_nuevo") or t.get("sid") or "")
        if destino == yo:
            continue
        clave = destino or "nueva:" + str(t.get("id") or "")
        previo = por_destino.get(clave)
        if previo and (previo["ficha"].get("creado") or 0) >= creado:
            continue
        por_destino[clave] = {"ficha": t, "destino": destino, "vivo": vivo}

    filas = []
    for d in por_destino.values():
        t, destino = d["ficha"], d["destino"]
        cwd, cerebro = t.get("cwd") or "", t.get("cerebro") or ""
        if d["vivo"]:
            estado, desde = "trabaja", t.get("creado") or ahora
        else:
            # Un estado que no conocemos no se disfraza de "terminó".
            estado = CERRADOS.get(t.get("estado"), "corto")
            desde = t.get("terminado") or t.get("creado") or ahora
        # ⭐ "Te pregunta algo" gana sobre trabaja y sobre terminó (el plan de una charla
        # se anota con el turno ya cerrado), pero no tapa un estado malo.
        if destino and pregunta_de and estado in ("trabaja", "termino"):
            try:
                preg = pregunta_de(cwd, destino)
            except Exception:
                preg = None
            if preg:
                estado, desde = "pregunta", (preg.get("hora") or desde)
        nombre = "charla nueva"
        if destino:
            try:
                nombre = (nombre_de(cwd, destino, cerebro) if nombre_de else "") or destino[:8]
            except Exception:
                nombre = destino[:8]
        filas.append({"trabajo": t.get("id") or "", "sid": destino, "cwd": cwd,
                      "nombre": str(nombre)[:60], "cerebro": cerebro,
                      "estado": estado, "desde": desde,
                      "_vivo": estado in ("trabaja", "pregunta"),
                      "_creado": t.get("creado") or 0})
    # Arriba lo que todavía se mueve; adentro de cada grupo, lo más nuevo primero.
    filas.sort(key=lambda f: (f["_vivo"], f["_creado"]), reverse=True)
    return [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas[:TOPE]]
