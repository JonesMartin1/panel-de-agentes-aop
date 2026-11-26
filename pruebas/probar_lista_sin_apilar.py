"""La lista de charlas no se apila ni se queda releyendo el disco.

Nace del 2026-11-23 (Martin: *"investiga por que me esta andando tan lento el panel"*).
Medido ese dia: `/movil/sesiones` tardo 89 segundos en el panel y 2 a 5 armandola sola. La
diferencia era el amontonamiento: cada pestaña la pedia cada 8 s sin esperar la anterior,
cada pedido la armaba entera por su cuenta (hasta 7 a la vez) y todos se frenaban entre si.
Adentro, lo caro era preguntarle a Windows por el padre de cada proceso (una consulta que
trae la tabla ENTERA cada vez) y dos memorias que se vaciaban enteras al llenarse.

Lo que se cuida aca:
  1. la lista se arma DE A UNA, y mientras tanto los demas se llevan la de recien;
  2. si la tiraron a proposito (renombrar, archivar) nadie recibe una vieja;
  3. la foto de "quien esta vivo" tambien se saca de a una;
  4. la tabla de padres se le pide a Windows UNA vez por pasada;
  5. los titulos y las novedades guardan UNA entrada por archivo y nunca se vacian enteros.

No levanta el servidor, no toca procesos ni archivos reales y no gasta tokens.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_lista_sin_apilar [--mutar]
"""
import inspect
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psutil

import panel
from app.voz import seguir, sesiones_movil

ok = fallo = 0
CALLADO = False


def chequear(que, condicion, detalle=""):
    global ok, fallo
    if condicion:
        ok += 1
        if not CALLADO:
            print(f"  ok   {que}")
    else:
        fallo += 1
        if not CALLADO:
            print(f"  FALLA {que}" + (f"  ({detalle})" if detalle else ""))


def en_hilos(funcion, cuantos):
    """Corre `funcion` en varios hilos a la vez y devuelve lo que contesto cada uno."""
    salidas = [None] * cuantos
    largada = threading.Barrier(cuantos)

    def uno(i):
        largada.wait()
        salidas[i] = funcion()

    hilos = [threading.Thread(target=uno, args=(i,)) for i in range(cuantos)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(20)
    return salidas


# --- 1 y 2: el armado de la lista en panel.py ------------------------------------

def lista_de_a_una():
    armados = []
    armar_de_verdad = panel._armar_sesiones

    def armar_lento(demora=0.3):
        time.sleep(demora)
        armados.append(1)
        return {"proyectos": [], "n": len(armados)}

    panel._armar_sesiones = armar_lento
    try:
        # Diez pedidos juntos sobre una lista vacia
        panel._SESIONES_ULTIMA.update(datos=None, cuando=0.0)
        salidas = en_hilos(panel.movil_sesiones, 10)
        chequear("diez pedidos a la vez arman la lista UNA sola vez",
                 len(armados) == 1, f"se armo {len(armados)} veces")
        chequear("y los diez reciben la misma", all(s is salidas[0] for s in salidas))

        # Vencida pero no tirada, con un armado en curso: va la de recien, al toque
        vieja = {"proyectos": [], "n": "vieja"}
        panel._SESIONES_ULTIMA.update(datos=vieja, cuando=time.time() - 60)
        armados.clear()
        primero = threading.Thread(target=panel.movil_sesiones)
        primero.start()
        time.sleep(0.08)
        t = time.time()
        segundo = panel.movil_sesiones()
        tardo = time.time() - t
        primero.join(5)
        chequear("mientras alguien arma, el segundo se lleva la de recien sin esperar",
                 segundo is vieja and tardo < 0.15, f"tardo {tardo:.2f} s")
        chequear("y la nueva queda guardada al terminar",
                 panel._SESIONES_ULTIMA["datos"] is not vieja and len(armados) == 1)

        # Tirada a proposito con un armado en curso: se espera la nueva
        panel._SESIONES_ULTIMA.update(datos=None, cuando=time.time())
        armados.clear()
        primero = threading.Thread(target=panel.movil_sesiones)
        primero.start()
        time.sleep(0.08)
        segundo = panel.movil_sesiones()
        primero.join(5)
        chequear("si la lista fue tirada, el segundo ESPERA la nueva",
                 isinstance(segundo, dict) and segundo.get("n") == 1 and len(armados) == 1,
                 f"recibio {segundo}, armados {len(armados)}")

        # La tiran MIENTRAS se arma: lo armado no se guarda
        panel._SESIONES_ULTIMA.update(datos=None, cuando=0.0)
        armados.clear()
        primero = threading.Thread(target=panel.movil_sesiones)
        primero.start()
        time.sleep(0.08)
        panel._SESIONES_ULTIMA["datos"] = None          # lo que hace renombrar o archivar
        primero.join(5)
        chequear("tirada mientras se armaba: lo armado NO queda guardado",
                 panel._SESIONES_ULTIMA["datos"] is None)
        panel.movil_sesiones()
        chequear("y el pedido siguiente arma de nuevo", len(armados) == 2)

        # Un armado que revienta no deja nada trabado
        def revienta():
            raise RuntimeError("disco roto")
        panel._armar_sesiones = revienta
        panel._SESIONES_ULTIMA.update(datos=None, cuando=0.0)
        try:
            panel.movil_sesiones()
            exploto = False
        except RuntimeError:
            exploto = True
        libre = panel._SESIONES_CANDADO.acquire(blocking=False)
        if libre:
            panel._SESIONES_CANDADO.release()
        chequear("si el armado revienta, el candado queda libre y no queda una marca colgada",
                 exploto and libre and panel._SESIONES_ULTIMA["datos"] is None)
    finally:
        panel._armar_sesiones = armar_de_verdad
        panel._SESIONES_ULTIMA.update(datos=None, cuando=0.0)


# --- 3: la foto de vivas ---------------------------------------------------------

def foto_de_a_una():
    sacadas = []
    de_verdad = seguir._vivas_de_verdad

    def lenta():
        time.sleep(0.3)
        sacadas.append(1)
        return {"n": len(sacadas)}

    seguir._vivas_de_verdad = lenta
    try:
        seguir.olvidar_vivas()
        salidas = en_hilos(seguir._vivas, 8)
        chequear("ocho hilos que encuentran la foto vencida la sacan UNA vez",
                 len(sacadas) == 1, f"se saco {len(sacadas)} veces")
        chequear("y todos se llevan la misma", all(s == {"n": 1} for s in salidas))

        seguir.olvidar_vivas()
        sacadas.clear()
        h = threading.Thread(target=seguir._vivas)
        h.start()
        time.sleep(0.08)
        seguir.olvidar_vivas()            # alguien prendio una sesion mientras se sacaba
        h.join(5)
        seguir._vivas()
        chequear("si la tiran mientras se saca, la proxima consulta saca otra",
                 len(sacadas) == 2, f"se saco {len(sacadas)} veces")
    finally:
        seguir._vivas_de_verdad = de_verdad
        seguir.olvidar_vivas()


# --- 4: la tabla de padres -------------------------------------------------------

def padres_una_vez():
    chequear("hijo de un proceso del panel: es del panel",
             _con_pids({100}, lambda: seguir._es_del_panel(300, {300: 200, 200: 100})))
    chequear("uno que no cuelga de nada nuestro: no es",
             not _con_pids({100}, lambda: seguir._es_del_panel(300, {300: 200, 200: 7})))
    chequear("mas de tres padres arriba ya no se mira (como antes)",
             not _con_pids({100}, lambda: seguir._es_del_panel(
                 500, {500: 400, 400: 300, 300: 200, 200: 100})))

    registro_real, tabla_real = seguir.CLAUDE_REGISTRO, psutil._psplatform.ppid_map
    consultas = []

    def tabla_contada():
        consultas.append(1)
        return tabla_real()

    tmp = Path(tempfile.mkdtemp(prefix="registro_"))
    for i in range(6):
        (tmp / f"{i}.json").write_text(json.dumps(
            {"sessionId": f"sesion-{i}", "pid": os.getpid(), "cwd": "x"}), encoding="utf-8")
    seguir.CLAUDE_REGISTRO = tmp
    psutil._psplatform.ppid_map = tabla_contada
    try:
        vivas = _con_pids({999999999}, seguir._vivas_de_verdad)
        chequear("con seis sesiones registradas, la tabla de padres se pide UNA vez",
                 len(consultas) == 1, f"se pidio {len(consultas)} veces")
        chequear("y las seis siguen saliendo como vivas", len(vivas) == 6, f"salieron {len(vivas)}")
    finally:
        seguir.CLAUDE_REGISTRO = registro_real
        psutil._psplatform.ppid_map = tabla_real


def _con_pids(pids, funcion):
    """Corre `funcion` haciendo de cuenta que el panel tiene prendidos esos procesos."""
    antes = set(seguir.PIDS_PANEL)
    seguir.PIDS_PANEL.clear()
    seguir.PIDS_PANEL.update(pids)
    try:
        return funcion()
    finally:
        seguir.PIDS_PANEL.clear()
        seguir.PIDS_PANEL.update(antes)


# --- 5: las memorias no se vacian enteras ----------------------------------------

def _charla(ruta, titulo, cuando):
    ruta.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hola"}}) + "\n"
        + json.dumps({"type": "ai-title", "aiTitle": titulo}) + "\n", encoding="utf-8")
    os.utime(ruta, (cuando, cuando))


def memorias_por_archivo():
    tmp = Path(tempfile.mkdtemp(prefix="titulos_"))
    guardados, tope = dict(seguir._titulos), seguir._TITULOS_MAX
    seguir._titulos.clear()
    try:
        una = tmp / "aaaa.jsonl"
        base = time.time() - 5000
        _charla(una, "Uno", base)
        chequear("lee el titulo", seguir._titulo_de(una) == "Uno")
        for i in range(40):
            _charla(una, f"Vuelta {i}", base + 1 + i)
            seguir._titulo_de(una)
        chequear("cuando el archivo cambia, el titulo se relee",
                 seguir._titulo_de(una) == "Vuelta 39")
        chequear("una charla que escribio 40 veces ocupa UNA entrada",
                 len(seguir._titulos) == 1, f"ocupa {len(seguir._titulos)}")

        seguir._TITULOS_MAX = 10
        minimo = 99
        for i in range(30):
            otra = tmp / f"otra{i}.jsonl"
            _charla(otra, f"Otra {i}", base)
            seguir._titulo_de(otra)
            minimo = min(minimo, len(seguir._titulos))
        chequear("al pasarse del tope tira lo viejo, NUNCA todo",
                 minimo >= 2 and len(seguir._titulos) <= 10,
                 f"llego a quedar en {minimo}, termino en {len(seguir._titulos)}")
        chequear("y lo recien usado sigue guardado",
                 str(tmp / "otra29.jsonl") in seguir._titulos)

        # sesiones_de: la fecha que devuelve es la del archivo, mirada una sola vez
        carpeta_real = seguir.carpeta_de
        seguir.carpeta_de = lambda cwd: tmp
        try:
            seguir.olvidar_vivas()
            filas = seguir.sesiones_de("x", horas=24)
            chequear("sesiones_de sigue trayendo cada charla con su fecha y su titulo",
                     len(filas) == min(31, seguir.MAX_SESIONES)
                     and all(abs(f["ts"] - Path(f["jsonl"]).stat().st_mtime) < 1e-6
                             for f in filas)
                     and filas[0]["nombre"] == "Vuelta 39"        # la mas nueva, primera
                     and all(f["nombre"].startswith(("Vuelta", "Otra")) for f in filas),
                     f"{len(filas)} filas: {[f['nombre'] for f in filas]}")

            # novedad: una entrada por archivo
            novedades = dict(sesiones_movil._NOVEDADES)
            sesiones_movil._NOVEDADES.clear()
            try:
                sid = "aaaa"
                for i in range(25):
                    _charla(una, f"N {i}", base + 100 + i)
                    quien, cuando = sesiones_movil.novedad("x", sid)
                chequear("novedad: una charla que escribio 25 veces ocupa UNA entrada",
                         len(sesiones_movil._NOVEDADES) == 1,
                         f"ocupa {len(sesiones_movil._NOVEDADES)}")
                chequear("y contesta con la fecha de la ultima version",
                         abs(cuando - (base + 124)) < 1e-3 and quien == "vos", f"{quien} {cuando}")
                chequear("sin cambios, contesta de memoria lo mismo",
                         sesiones_movil.novedad("x", sid) == (quien, cuando))
            finally:
                sesiones_movil._NOVEDADES.clear()
                sesiones_movil._NOVEDADES.update(novedades)
        finally:
            seguir.carpeta_de = carpeta_real
    finally:
        seguir._TITULOS_MAX = tope
        seguir._titulos.clear()
        seguir._titulos.update(guardados)


GRUPOS = [("La lista se arma de a una", lista_de_a_una),
          ("La foto de vivas se saca de a una", foto_de_a_una),
          ("La tabla de padres, una vez por pasada", padres_una_vez),
          ("Las memorias guardan una entrada por archivo", memorias_por_archivo)]


# --- Mutaciones: se rompe cada regla a proposito y el chequeo la tiene que cazar ---

class CandadoDeAdorno:
    """Un candado que deja pasar a todos: lo que habia antes del arreglo."""

    def acquire(self, blocking=True):
        return True

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _reescribir(modulo, funcion, viejo, nuevo):
    """Rearma una funcion del modulo con un pedazo cambiado. Devuelve la original."""
    original = getattr(modulo, funcion)
    fuente = inspect.getsource(original)
    assert viejo in fuente, f"la mutacion de {funcion} ya no encuentra su texto"
    exec(fuente.replace(viejo, nuevo), modulo.__dict__)
    return original


def mutar():
    global CALLADO, fallo
    cazadas = 0

    def probar(nombre, grupo, romper, arreglar):
        nonlocal cazadas
        global CALLADO, fallo, ok
        romper()
        antes, ok_antes = fallo, ok
        CALLADO = True
        try:
            grupo()
        except Exception:
            fallo += 1
        finally:
            CALLADO = False
            arreglar()
        cazo = fallo > antes
        fallo, ok = antes, ok_antes        # las corridas rotas no cuentan en el total
        cazadas += cazo
        print(f"  {'cazada ' if cazo else 'NO CAZADA'}  {nombre}")

    guardado = {}

    def poner(modulo, nombre, valor):
        def romper():
            guardado[nombre] = getattr(modulo, nombre)
            setattr(modulo, nombre, valor)
        return romper

    def sacar(modulo, nombre):
        return lambda: setattr(modulo, nombre, guardado[nombre])

    print("\n== Mutaciones ==")
    probar("sin candado en la lista (cada pedido arma la suya)", lista_de_a_una,
           poner(panel, "_SESIONES_CANDADO", CandadoDeAdorno()), sacar(panel, "_SESIONES_CANDADO"))
    probar("sin devolver la de recien mientras otro arma", lista_de_a_una,
           poner(panel, "_sesiones_guardadas",
                 lambda fresca, _f=panel._sesiones_guardadas: _f(True)),
           sacar(panel, "_sesiones_guardadas"))
    probar("guardando lo armado aunque la hayan tirado en el medio", lista_de_a_una,
           lambda: guardado.__setitem__("ms", _reescribir(
               panel, "movil_sesiones",
               'if _SESIONES_ULTIMA["datos"] is not None:  #', 'if True:  #')),
           lambda: setattr(panel, "movil_sesiones", guardado["ms"]))
    probar("sin candado en la foto de vivas", foto_de_a_una,
           poner(seguir, "_vivas_sacando", CandadoDeAdorno()), sacar(seguir, "_vivas_sacando"))
    probar("sin la tabla de padres compartida (una consulta por proceso)", padres_una_vez,
           poner(seguir, "_mapa_de_padres", lambda: None), sacar(seguir, "_mapa_de_padres"))
    probar("vaciando los titulos enteros al llegar al tope", memorias_por_archivo,
           lambda: guardado.__setitem__("td", _reescribir(
               seguir, "_titulo_de",
               "for vieja in list(_titulos)[:_TITULOS_MAX // 2]:\n            _titulos.pop(vieja, None)",
               "_titulos.clear()")),
           lambda: setattr(seguir, "_titulo_de", guardado["td"]))
    probar("novedades con una entrada por VERSION del archivo", memorias_por_archivo,
           lambda: guardado.__setitem__("nv", _reescribir(
               sesiones_movil, "novedad", "clave = str(jsonl)\n",
               "clave = str(jsonl) + str(est.st_mtime)\n")),
           lambda: setattr(sesiones_movil, "novedad", guardado["nv"]))
    print(f"\n  {cazadas} de 7 mutaciones cazadas")
    return cazadas == 7


if __name__ == "__main__":
    for titulo, grupo in GRUPOS:
        print(f"\n== {titulo} ==")
        grupo()
    todo_bien = fallo == 0
    if "--mutar" in sys.argv and todo_bien:
        todo_bien = mutar()
    print(f"\n{ok} ok, {fallo} fallas" + ("  — TODO BIEN" if todo_bien else "  — HAY PROBLEMAS"))
    sys.exit(0 if todo_bien else 1)
