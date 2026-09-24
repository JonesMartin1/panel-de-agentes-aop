"""Verifica el vigia del WhatsApp del transcriptor SIN tocar la red ni avisar a nadie.

Lo que se prueba de verdad:
  1. `chequeo_instancia` distingue 'open' de 'close' y devuelve el codigo correcto.
  2. No puede decir "esta todo bien" cuando no pudo mirar (Evolution caido, .env
     incompleto, la instancia no existe). Un chequeo ciego que da verde es peor que
     no tener chequeo: fue exactamente lo que dejo pasar dos dias en silencio.
  3. `vigilar.json` manda por TELEGRAM. Esta es la regla que mas facil se rompe
     "ordenando": los avisos de WhatsApp salen por la MISMA instancia que se vigila.
  4. El comando del config se para en la raiz del proyecto y usa el Python del env.

Con --mutar rompe cada regla a proposito y exige que el chequeo la cace. Un chequeo
que no puede fallar es un adorno.

    python -m pruebas.probar_vigia_whatsapp
    python -m pruebas.probar_vigia_whatsapp --mutar
"""
import io
import sys
import json
import copy
import contextlib

from app.rutas import VIGILAR
from app.ingesta import chequeo_instancia as ci

bien = 0
mal = 0


def check(titulo, condicion, detalle=""):
    global bien, mal
    if condicion:
        bien += 1
        print("  ok  %s" % titulo)
    else:
        mal += 1
        print("  MAL %s %s" % (titulo, detalle))


def _fingir_evolution(respuesta=None, revienta=None):
    """Reemplaza la consulta HTTP por una respuesta de mentira.

    Se parchea `urlopen` y no `estado_instancia`, asi la prueba pasa por el parseo
    real (que es donde estan los formatos raros de Evolution) en vez de saltearlo.
    """
    class Falsa:
        def __init__(self, cuerpo):
            self._c = json.dumps(cuerpo).encode()
        def read(self):
            return self._c
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def falso(pedido, timeout=None):
        if revienta:
            raise revienta
        return Falsa(respuesta)
    return falso


def cuerpo(nombre="Laura", estado="open", anidado=False):
    fila = {"instanceName": nombre, "connectionStatus": estado,
            "owner": "5490000000000@s.whatsapp.net"}
    return [{"instance": fila}] if anidado else [fila]


def correr(env_ok=True, **kw):
    """Corre el chequeo con Evolution fingido. Devuelve (codigo, lo que imprimio)."""
    orig_url, orig_env = ci.urllib.request.urlopen, ci._del_env
    ci.urllib.request.urlopen = _fingir_evolution(**kw)
    if env_ok:
        ci._del_env = lambda c: {"EVOLUTION_API_URL": "https://ejemplo",
                                 "EVOLUTION_API_KEY": "x",
                                 "EVOLUTION_INSTANCE": "Laura"}.get(c, "")
    else:
        ci._del_env = lambda c: ""
    salida = io.StringIO()
    try:
        with contextlib.redirect_stdout(salida):
            codigo = ci.main([])
    finally:
        ci.urllib.request.urlopen = orig_url
        ci._del_env = orig_env
    return codigo, salida.getvalue()


def probar_chequeo(mutar=False):
    print("\n--- el chequeo distingue conectada de caida ---")

    codigo, texto = correr(respuesta=cuerpo(estado="open"))
    check("instancia 'open' -> codigo 0 (no avisa)", codigo == 0, "dio %s" % codigo)
    check("y no dice nada alarmante", "desvinculado" not in texto)

    codigo, texto = correr(respuesta=cuerpo(estado="close"))
    check("instancia 'close' -> codigo 1 (avisa)", codigo == 1, "dio %s" % codigo)
    check("el aviso dice QUE pasa, no solo que algo fallo",
          "desvinculado" in texto and "Estudio" in texto, "decia: %r" % texto[:80])
    check("y dice como se arregla", "QR" in texto)

    codigo, _ = correr(respuesta=cuerpo(estado="connecting"))
    check("un estado a medias ('connecting') NO cuenta como sana", codigo == 1)

    codigo, _ = correr(respuesta=cuerpo(estado="open", anidado=True))
    check("entiende la respuesta anidada en 'instance'", codigo == 0)

    print("\n--- no puede dar verde cuando no pudo mirar ---")

    codigo, texto = correr(revienta=OSError("se cayo la red"))
    check("Evolution inalcanzable -> codigo 1", codigo == 1)
    check("y lo dice, no lo disfraza de instancia caida",
          "no pude preguntarle" in texto, "decia: %r" % texto[:90])

    codigo, texto = correr(respuesta=cuerpo(nombre="OtraCosa", estado="open"))
    check("si la instancia configurada no existe -> codigo 1", codigo == 1)
    check("y avisa que no la conoce", "no conoce" in texto)

    codigo, texto = correr(env_ok=False, respuesta=cuerpo())
    check("sin credenciales en el .env -> codigo 1", codigo == 1)
    check("y avisa que falta config", "falta EVOLUTION" in texto)

    codigo, _ = correr(respuesta=[])
    check("Evolution sin ninguna instancia -> codigo 1", codigo == 1)


def probar_config(cfg):
    print("\n--- vigilar.json ---")
    check("existe", bool(cfg))
    if not cfg:
        return
    check("*** avisa por TELEGRAM (no por el WhatsApp que vigila)",
          cfg.get("canal") == "telegram", "dice %r" % cfg.get("canal"))
    check("y explica por que, para que nadie lo 'ordene'",
          any("whatsapp" in str(v).lower() and "telegram" in str(v).lower()
              for k, v in cfg.items() if k.startswith("_")))
    check("lo dice ademas en voz alta", cfg.get("hablar") is True)
    check("aguanta un hipo de red antes de gritar",
          int(cfg.get("fallos_seguidos", 0)) >= 2)
    check("no le escribe al grupo del equipo", not cfg.get("grupo"))

    ches = cfg.get("chequeos") or []
    check("tiene el chequeo del WhatsApp", len(ches) >= 1)
    if not ches:
        return
    cmd = str(ches[0].get("comando") or "")
    check("se para en la raiz del proyecto", "cd /d" in cmd and "wpp-transcriptor" in cmd,
          "comando: %r" % cmd[:70])
    check("usa el Python del env wpp, no el del sistema",
          "envs\\wpp\\python.exe" in cmd or "envs/wpp/python.exe" in cmd)
    check("lo lanza con -m (si no, no encuentra el paquete app)",
          "-m app.ingesta.chequeo_instancia" in cmd)


def mutaciones(cfg):
    """Rompe cada regla a proposito y exige que el chequeo de arriba la cace."""
    global bien, mal
    print("\n=== --mutar: cada regla rota tiene que hacer fallar la prueba ===")
    casos = [
        ("el canal pasa a whatsapp (el cable que se corta)",
         lambda c: c.update({"canal": "whatsapp"})),
        ("se borra la explicacion de por que es telegram",
         lambda c: [c.pop(k) for k in list(c) if k.startswith("_")]),
        ("avisa al primer fallo (ruido por cualquier hipo)",
         lambda c: c.update({"fallos_seguidos": 1})),
        ("el comando ya no se para en la raiz",
         lambda c: c["chequeos"][0].update(
             {"comando": '"D:\\IA\\envs\\wpp\\python.exe" -m app.ingesta.chequeo_instancia'})),
        ("el comando usa el Python del sistema",
         lambda c: c["chequeos"][0].update(
             {"comando": "cd /d D:\\IA\\wpp-transcriptor && python -m app.ingesta.chequeo_instancia"})),
        ("se le pone que avise al grupo del equipo",
         lambda c: c.update({"grupo": True})),
    ]
    cazadas = 0
    for titulo, romper in casos:
        roto = copy.deepcopy(cfg)
        romper(roto)
        antes_mal = mal
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            probar_config(roto)
        if mal > antes_mal:
            cazadas += 1
            print("  ok  cazada: %s" % titulo)
        else:
            print("  MAL SE ESCAPO: %s" % titulo)
        mal = antes_mal          # la mutacion no cuenta como error real
    # El contador de aciertos tambien se ensucio con las corridas mutadas.
    print("\n  %d de %d mutaciones cazadas" % (cazadas, len(casos)))
    return cazadas == len(casos)


def main():
    mutar = "--mutar" in sys.argv
    # El vigilar.json propio si existe; si no, el molde que viene con el proyecto.
    archivo = VIGILAR if VIGILAR.exists() else VIGILAR.with_name("vigilar.ejemplo.json")
    try:
        cfg = json.loads(archivo.read_text(encoding="utf-8"))
    except Exception as e:
        print("no pude leer vigilar.json:", e)
        cfg = {}

    probar_chequeo()
    probar_config(cfg)

    todas = True
    if mutar and cfg:
        antes_bien = bien
        todas = mutaciones(cfg)
        globals()["bien"] = antes_bien

    print("\n%d bien, %d mal" % (bien, mal))
    if mal or not todas:
        print("HAY ALGO ROTO")
        return 1
    print("TODO BIEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
