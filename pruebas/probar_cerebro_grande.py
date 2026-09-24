"""
El interruptor entre los dos cerebros grandes (Claude y Codex).

Lo que se prueba, que es lo unico que puede romperse en silencio:

 1. Que "pasate a Codex" se entienda hablando, con las mil formas en que Whisper
    escribe "Claude", y que NOMBRAR un cerebro en medio de una charla no cambie nada.
 2. Que el interruptor reenvie de verdad al modulo puesto (si esto falla, Laura
    sigue pensando con el de antes y no hay forma de darse cuenta desde afuera).
 3. Que los dos cerebros tengan la MISMA cara: si a uno le falta una funcion que el
    otro tiene, el dia que cambies se rompe el camino que la usaba.
 4. Que cada uno guarde su charla en SU archivo, que es lo que hace que cambiar de
    cerebro no te pise la conversacion del otro.

Correr:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_cerebro_grande
"""

import json

from app.rutas import CEREBRO, CLAUDE_SESION, CODEX_SESION
from app.voz import cerebro_grande as cg

fallas = []


def igual(que, esperado, caso):
    if que != esperado:
        fallas.append(f"{caso}: esperaba {esperado!r} y dio {que!r}")


# --- 1. Entender el pedido hablado ---------------------------------------------
PEDIDOS = [
    ("pasate a codex", "codex"),
    ("Laura, cambiate a Codex", "codex"),
    ("anda a codex un rato", "codex"),
    ("usa gpt para esto", "codex"),
    ("pasate a open ai", "codex"),
    ("volve a claude", "claude"),
    ("cambiate a cloud", "claude"),          # asi lo escribe Whisper la mitad de las veces
    ("pasate a clod de nuevo", "claude"),
    # Nombrar un cerebro NO es pedir cambiarlo: sin el verbo, no se toca nada.
    ("que te parece codex?", None),
    ("claude es mejor para esto", None),
    ("contame que hace codex", None),
    ("poneme musica", None),
    ("", None),
]
for texto, esperado in PEDIDOS:
    igual(cg.pedido_de_cambio(texto), esperado, f"pedido {texto!r}")

# --- 2. El interruptor reenvia al modulo puesto ---------------------------------
previo = cg.activo()
try:
    for clave, modulo_esperado in (("codex", "app.voz.codex_voz"),
                                   ("claude", "app.voz.claude_voz")):
        cg.usar(clave)
        igual(cg.activo(), clave, f"quedar en {clave}")
        igual(cg.modulo().__name__, modulo_esperado, f"modulo de {clave}")
        # La prueba de fuego: un atributo pedido al interruptor tiene que venir del
        # modulo activo, no del otro. (`preguntar` no: ese lo define el interruptor
        # para poder meter el traspaso, y se prueba aparte mas abajo.)
        igual(cg.cancelar.__module__, modulo_esperado, f"cancelar de {clave}")

    # --- 3. Los dos tienen la misma cara ---------------------------------------
    CARA = ["preguntar", "cancelar", "olvidar", "compactar", "precalentar",
            "esperando_dia", "responder_dia", "resumen_de", "sesion_anterior",
            "pide_sesion_nueva", "_limpiar", "_charla_de", "modelo_actual",
            "esfuerzo_actual", "SALUDO_DIA", "CORTE_HORA"]
    for clave in ("claude", "codex"):
        m = cg.modulo(clave)
        faltan = [f for f in CARA if not hasattr(m, f)]
        igual(faltan, [], f"le falta algo a {clave}")

    # --- 4. Cada uno con su archivo de charla -----------------------------------
    igual(cg.modulo("claude")._SESION_FILE, CLAUDE_SESION, "archivo de sesion de claude")
    igual(cg.modulo("codex")._SESION_FILE, CODEX_SESION, "archivo de sesion de codex")
    if CLAUDE_SESION == CODEX_SESION:
        fallas.append("los dos cerebros escriben la charla en el mismo archivo")

    # Cambiar de cerebro no puede tocar la sesion del otro.
    antes = cg.modulo("claude")._SESION
    cg.usar("codex")
    igual(cg.modulo("claude")._SESION, antes, "la charla de claude sobrevive al cambio")

    # --- 5. El traspaso: el que entra se entera de que veniamos hablando --------
    # Se arma a mano en cerebro.json en vez de hablar de verdad con los dos cerebros
    # (eso serian dos consultas y varios segundos por corrida).
    cg.usar("claude")
    cfg = cg._leer_config()
    cfg["traspaso"] = {"para": "claude", "de": "Codex", "texto": "Yo: probando el traspaso"}
    cg._guardar_config(cfg)

    con = cg._con_traspaso("y ahora que?")
    if "probando el traspaso" not in con or not con.endswith("y ahora que?"):
        fallas.append("el traspaso no se le pego al primer mensaje")
    if "Codex" not in con:
        fallas.append("el traspaso no dice de que cerebro viene")
    # Una sola vez: en el segundo mensaje ya no va.
    igual(cg._con_traspaso("otra cosa"), "otra cosa", "el traspaso se entrega una sola vez")
    igual(cg._leer_config().get("traspaso"), None, "el traspaso queda borrado")

    # Un traspaso dejado para el OTRO cerebro no se entrega.
    cfg = cg._leer_config()
    cfg["traspaso"] = {"para": "codex", "de": "Claude", "texto": "esto no va"}
    cg._guardar_config(cfg)
    igual(cg._con_traspaso("hola"), "hola", "no se entrega el traspaso ajeno")

    # Cambiar de cerebro deja anotado un traspaso PARA el que entra (o ninguno, si
    # el que se va no tenia charla todavia).
    cg.usar("codex")
    t = cg._leer_config().get("traspaso")
    if t is not None and t.get("para") != "codex":
        fallas.append("el cambio dejo el traspaso apuntando al cerebro equivocado")
    cfg = cg._leer_config()
    cfg.pop("traspaso", None)
    cg._guardar_config(cfg)

    # --- 6. Si un cerebro se cae, se sigue con el otro ---------------------------
    # Con cerebros de mentira: hacer fallar a Claude de verdad no se puede pedir.
    class _Falla:
        def preguntar(self, consulta, **kw):
            return "No pude hablar con Claude."

        def precalentar(self):
            pass

    class _Anda:
        def preguntar(self, consulta, **kw):
            return "Listo, era esto."

        def precalentar(self):
            pass

    modulo_real = cg.modulo
    try:
        cg.usar("claude")
        cg.modulo = lambda clave=None: (_Falla() if (clave or cg.activo()) == "claude"
                                        else _Anda())
        r = cg.preguntar("una pregunta cualquiera")
        if "era esto" not in r:
            fallas.append("el cerebro caido no le paso la pregunta al otro")
        if "no me contesto" not in r.lower():
            fallas.append("no avisa que cambio de cerebro por una falla")
        igual(cg.activo(), "codex", "queda puesto el cerebro que anduvo")
    finally:
        cg.modulo = modulo_real
finally:
    cg.usar(previo)                       # dejar la maquina como estaba
    igual(cg.activo(), previo, "volver al cerebro que estaba puesto")

if fallas:
    print("FALLAS:")
    for f in fallas:
        print(" -", f)
    raise SystemExit(1)
print(f"OK: {len(PEDIDOS)} frases entendidas y el interruptor cambia de verdad "
      f"(quedo puesto: {cg.como_se_llama()})")
