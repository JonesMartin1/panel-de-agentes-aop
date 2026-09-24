"""Dice si el WhatsApp del transcriptor sigue vinculado. Lo usa el vigia.

Sale con codigo 0 si la instancia de Evolution esta conectada (`open`) y con 1 si
esta caida o si no se pudo preguntar. No manda ningun aviso por su cuenta: de eso
se encarga `vigilar.py` leyendo `vigilar.json`, que ya trae las reglas anti-ruido
(avisa en el cambio de estado, no repite, aguanta N fallos seguidos).

Existe porque el 2026-08-29 Martin mando seis audios por WhatsApp y no llego
ninguno: la instancia `Laura` estaba en `close` desde el 27 a las 09:02 y **nadie
aviso**. La laptop estaba impecable (tunel 200 desde afuera, webhook vivo, Whisper
y el Estudio andando), asi que mirar de este lado no habria encontrado nada nunca.
El eslabon que se muere en silencio es el vinculo de WhatsApp con el telefono, y
solo se ve preguntandole a Evolution.

⚠⚠ **El aviso de este chequeo TIENE que salir por Telegram.** Los avisos de
WhatsApp de la skill `avisar` salen por ESTA MISMA instancia (`instancia: Laura`
en `~/.claude/whatsapp.json`): un aviso de "se cayo Laura" mandado por WhatsApp
viaja por el cable que se corto y no lo lee nadie. Por eso `vigilar.json` dice
`"canal": "telegram"` y no es un detalle de gusto.

Se corre solo:
    python -m app.ingesta.chequeo_instancia          # 0 = conectada, 1 = caida
    python -m app.ingesta.chequeo_instancia --decir  # ademas imprime el estado
"""
import os
import sys
import json
import urllib.error
import urllib.request

# Esta laptop intercepta HTTPS (Avast): sin truststore, preguntarle a Evolution
# muere con CERTIFICATE_VERIFY_FAILED. Mismo motivo que en panel.py:24.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from app.rutas import ENV

# 8 s y no mas: `vigilar.py` mata el comando entero a los 15 s y un comando matado
# cuenta como caida. Con la consulta mas el arranque de Python entra holgado, asi
# que una red lenta no se confunde con un WhatsApp desvinculado.
TIMEOUT = 8


def _del_env(clave):
    """Lee una variable del .env sin depender de que este cargado el entorno.

    El vigia corre desde el Programador de tareas, donde no hay nada seteado.
    """
    valor = os.environ.get(clave)
    if valor:
        return valor.strip()
    try:
        for linea in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
            linea = linea.strip()
            if linea.startswith("#") or "=" not in linea:
                continue
            k, _, v = linea.partition("=")
            if k.strip() == clave:
                return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def estado_instancia():
    """(estado, detalle). `estado` es 'open', 'close', otro texto de Evolution, o ''.

    Con '' el detalle dice por que no se pudo preguntar: eso NO es lo mismo que
    "esta caida", pero para el vigia cuenta igual como fallo — un chequeo que no
    puede mirar no puede decir que esta todo bien (leccion del 2026-08-27: un log
    vacio no es evidencia de salud, es evidencia de nada).
    """
    url = (_del_env("EVOLUTION_API_URL") or "").rstrip("/")
    key = _del_env("EVOLUTION_API_KEY")
    inst = _del_env("EVOLUTION_INSTANCE")
    if not (url and key and inst):
        return "", "falta EVOLUTION_API_URL/API_KEY/INSTANCE en el .env"
    pedido = urllib.request.Request(url + "/instance/fetchInstances",
                                    headers={"apikey": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return "", "Evolution contesto HTTP %s" % e.code
    except Exception as e:
        return "", "no pude preguntarle a Evolution: %s" % str(e)[:120]
    filas = datos if isinstance(datos, list) else (datos.get("data") or [])
    for fila in filas:
        # Evolution cambio la forma de esta respuesta entre versiones: a veces la
        # instancia viene anidada en "instance" y a veces plana. Se aceptan las dos.
        ins = fila.get("instance") if isinstance(fila, dict) and fila.get("instance") else fila
        if not isinstance(ins, dict):
            continue
        nombre = ins.get("instanceName") or ins.get("name")
        if nombre != inst:
            continue
        estado = ins.get("connectionStatus") or ins.get("status") or ins.get("state") or ""
        return estado, "la instancia %r figura %r" % (inst, estado)
    return "", "Evolution no conoce ninguna instancia %r" % inst


def main(argv):
    estado, detalle = estado_instancia()
    if "--decir" in argv:
        print(detalle)
    if estado == "open":
        return 0
    # El texto va a parar al aviso que le llega al celular, asi que dice QUE pasa
    # y que hay que hacer, no solo que algo anda mal.
    print("El WhatsApp del transcriptor esta desvinculado (%s). "
          "Los audios que le manden NO entran al Estudio. Se levanta escaneando el "
          "QR de la instancia en el manager de Evolution." % detalle)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
