"""Charlas de Claude Code que corren en OTRA maquina, adentro del riel de /sesiones.

Pedido de Martin (2026-11-16): tiene sesiones corriendo en un servidor, con OTRA cuenta de
Claude, y las quiere en el panel sabiendo de un vistazo cuales son de su cuenta y cuales no.
Segunda vuelta, el mismo dia: no en una carpeta aparte, sino ADENTRO de sus proyectos — al
escribir elige con que cuenta nace la charla, igual que elige Claude o Codex.

Como esta armado, en cuatro piezas:

1. LOS SITIOS. Una maquina remota tiene una carpeta propia (`REMOTAS/<nombre>`, su "cajon
   de arena") y ademas puede tener PREPARADOS proyectos de esta maquina: cada uno es un par
   carpeta-de-aca / carpeta-de-alla escrito en `maquinas.json`. Solo en una carpeta
   preparada se ofrece el servidor: una charla remota trabaja sobre los archivos de ALLA,
   no sobre este disco, y eso no puede pasar por accidente.

2. EL ESPEJO. Un hilo copia por SSH las transcripciones de cada sitio a la carpeta de
   transcripciones del proyecto local, asi que el panel las lista, las lee, les pone
   nombre y las archiva con el mismo codigo que a cualquier charla. Solo se trae lo que
   crecio y se le cambia el `cwd` de cada renglon por la carpeta local.

3. EL REGISTRO. Como ahora conviven en la misma carpeta con las charlas comunes, lo que
   dice que una charla es remota es su ID, anotado en `charlas.json` ANTES de que su copia
   toque el disco. De ahi sale la marca en pantalla y, sobre todo, el guardia.

4. EL DESVIO Y EL GUARDIA. Un mensaje a una charla remota NO arranca un `claude` aca: viaja
   por SSH al `despachar.sh` de la otra maquina, que lo corre alla, suelto. Y
   `sesiones_movil._arrancar_viva` se niega a levantar un proceso local sobre una charla
   remota. ⚠⚠ Es lo que no se puede romper: un `claude --resume` local sobre la copia
   correria con la cuenta de ESTA maquina y partiria la charla en dos sin que nadie se entere.

Si el servidor esta apagado no pasa nada raro: el riel muestra la ultima copia y lo unico
que falla, con un error que lo dice, es mandar.
"""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from app.rutas import REMOTAS, REMOTAS_MAQUINAS
from app.voz import seguir

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ID_OK = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_RUTA_REMOTA_OK = re.compile(r"^/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
CEREBRO = "servidor:"   # lo que manda la pantalla en `cerebro` para nacer en otra maquina
LENTO_SEG = 30          # cada cuanto se mira cuando nadie esta mandando nada
RAPIDO_SEG = 3          # idem mientras hay un pedido en vuelo: es lo que se ve "en vivo"
CUENTA_VALE_SEG = 3600  # cada cuanto se vuelve a preguntar con que cuenta corre cada lado
ESPERA_MAX_SEG = 2 * 3600

_candado = threading.Lock()
_hilo = None
_en_vuelo = 0                     # pedidos mandados que todavia no volvieron
_cuentas = {}                     # nombre de maquina -> mail de la cuenta de alla
_cuenta_local = {"mail": "", "cuando": 0.0}
_cuentas_cuando = 0.0
_charlas = {"datos": None, "mtime": None}


# ---------------------------------------------------------------- configuracion

def maquinas():
    """Las maquinas declaradas en `maquinas.json`. Sin archivo, ninguna: todo lo de este
    modulo queda apagado y el panel se comporta exactamente como antes."""
    try:
        datos = json.loads(REMOTAS_MAQUINAS.read_text(encoding="utf-8"))
    except Exception:
        return []
    buenas = []
    for m in datos if isinstance(datos, list) else []:
        if not isinstance(m, dict):
            continue
        if not all(isinstance(m.get(k), str) and m.get(k) for k in
                   ("nombre", "ssh", "base", "cwd_remoto", "despachar")):
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}", m["nombre"]):
            continue
        if not _RUTA_REMOTA_OK.match(m["cwd_remoto"]):
            continue
        buenas.append(m)
    return buenas


def _maquina(nombre):
    for m in maquinas():
        if m["nombre"] == nombre:
            return m
    return None


def carpeta_local(m):
    """La carpeta propia de esa maquina en ESTE disco: su cajon de arena."""
    return REMOTAS / m["nombre"]


def _plana(ruta):
    return str(seguir.carpeta_de(ruta)).lower()


def sitios(m):
    """Los pares carpeta-de-aca / carpeta-de-alla de esa maquina: [{m, local, remoto, fijo}].

    El primero es siempre el cajon de arena (`fijo`: ahi TODO corre alla). Los demas son los
    proyectos preparados, donde conviven charlas de aca y de alla.
    """
    salida = [{"m": m, "local": carpeta_local(m), "remoto": m["cwd_remoto"], "fijo": True}]
    vistos = {_plana(carpeta_local(m))}
    for p in m.get("proyectos") or []:
        if not isinstance(p, dict):
            continue
        local, remoto = p.get("local"), p.get("remoto")
        if not (isinstance(local, str) and local and isinstance(remoto, str)
                and _RUTA_REMOTA_OK.match(remoto) and ".." not in remoto):
            continue
        if _plana(local) in vistos:
            continue
        vistos.add(_plana(local))
        salida.append({"m": m, "local": Path(local), "remoto": remoto, "fijo": False})
    return salida


def _sitio_de(m, cwd):
    """El sitio de esa maquina que corresponde a esa carpeta de aca, o None."""
    try:
        plana = _plana(cwd)
    except Exception:
        return None
    for s in sitios(m):
        if _plana(s["local"]) == plana:
            return s
    return None


def carpetas():
    """Los cajones de arena de todas las remotas (creandolos si faltan), para el riel."""
    salida = []
    for m in maquinas():
        try:
            carpeta_local(m).mkdir(parents=True, exist_ok=True)
            salida.append(str(carpeta_local(m)))
        except OSError:
            pass
    return salida


def maquina_de(cwd):
    """La maquina de la que esa carpeta es el cajon de arena, o None si es otra cosa."""
    if not cwd:
        return None
    for m in maquinas():
        s = _sitio_de(m, cwd)
        if s is not None and s["fijo"]:
            return m
    return None


def es_remota(cwd):
    """¿Esa CARPETA es de otra maquina entera? (Un proyecto preparado no: ahi depende de
    cada charla, ver `charla()`.)"""
    return maquina_de(cwd) is not None


# -------------------------------------------------------------------- registro

def _archivo_charlas():
    return REMOTAS / "charlas.json"


def _leer_charlas():
    f = _archivo_charlas()
    try:
        mtime = f.stat().st_mtime_ns
    except OSError:
        return {}
    if _charlas["datos"] is None or _charlas["mtime"] != mtime:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            _charlas["datos"] = d if isinstance(d, dict) else {}
        except Exception:
            _charlas["datos"] = {}
        _charlas["mtime"] = mtime
    return _charlas["datos"]


def charla(sid):
    """Si esa charla corre en otra maquina, {maquina, local}; si no, None."""
    sid = (sid or "").strip()
    if not sid:
        return None
    c = _leer_charlas().get(sid)
    return c if isinstance(c, dict) else None


def _anotar_charla(sid, sitio):
    """Deja escrito que esa charla es remota. ⚠ Se llama ANTES de copiar su transcripcion:
    el guardia mira este registro, y una copia en el disco sin su anotacion es una charla
    que se podria levantar aca."""
    with _candado:
        d = dict(_leer_charlas())
        nuevo = {"maquina": sitio["m"]["nombre"], "local": str(sitio["local"])}
        if d.get(sid) == nuevo:
            return
        d[sid] = nuevo
        REMOTAS.mkdir(parents=True, exist_ok=True)
        tmp = _archivo_charlas().with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, _archivo_charlas())
        _charlas["datos"], _charlas["mtime"] = None, None


def es_de_otra_maquina(cwd, sid="", desde=""):
    """Lo que pregunta el guardia: ¿levantar esto aca seria levantar una charla de otra
    maquina? Por la carpeta (el cajon de arena), por la charla o por la que se quiere copiar."""
    return es_remota(cwd) or charla(sid) is not None or charla(desde) is not None


def destino(cwd, sid="", cerebro=""):
    """A donde va un turno: el sitio de la otra maquina, o None si corre aca.

    Con charla nacida manda el REGISTRO, no lo que diga la pantalla. Sin charla, va alla si
    la carpeta es un cajon de arena o si la pantalla lo pidio (`cerebro` = "servidor:<nombre>").
    ⚠ Lo que no se puede resolver sale como error y NO como None: None quiere decir "corre
    aca", y una charla remota que cae aca es justo lo que no puede pasar.
    """
    sid = (sid or "").strip()
    c = charla(sid)
    if c is not None:
        m = _maquina(c.get("maquina"))
        if m is None:
            raise RuntimeError("Esa charla es de una máquina (%s) que ya no está configurada."
                               % c.get("maquina"))
        s = _sitio_de(m, c.get("local") or cwd) or _sitio_de(m, cwd)
        if s is None:
            raise RuntimeError("Esa charla es de %s, pero su carpeta ya no está preparada ahí."
                               % m["nombre"])
        return s
    m = maquina_de(cwd)
    if m is not None:
        return _sitio_de(m, cwd)
    if not sid and (cerebro or "").startswith(CEREBRO):
        nombre = cerebro[len(CEREBRO):]
        m = _maquina(nombre)
        if m is None:
            raise RuntimeError("No conozco ninguna máquina llamada %s." % nombre[:40])
        s = _sitio_de(m, cwd)
        if s is None:
            raise RuntimeError("Esta carpeta no está preparada en %s: allá no hay dónde "
                               "trabajar." % m["nombre"])
        return s
    return None


# ------------------------------------------------------------------------- ssh

def _ssh(m, comando, entrada=None, espera=20):
    """Corre `comando` en la maquina remota. Devuelve (codigo, salida en bytes).

    `BatchMode` para que jamas se quede esperando una clave que nadie va a tipear, y sin
    ventana: esto corre adentro del panel, que no tiene consola.
    """
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", m["ssh"], comando],
            input=entrada, capture_output=True, timeout=espera,
            creationflags=_SIN_VENTANA)
        return r.returncode, r.stdout
    except Exception as e:
        return 255, str(e).encode("utf-8", "replace")


def _comilla(texto):
    """Entre comillas simples para el shell de alla."""
    return "'" + str(texto).replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------- espejo

def _estado_de(m):
    return REMOTAS / (m["nombre"] + ".estado.json")


def _leer_estado(m):
    try:
        d = json.loads(_estado_de(m).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _transcripciones(sitio):
    """Donde guarda Claude Code, ALLA, las charlas de esa carpeta: aplana la ruta igual que
    aca (todo lo que no sea letra, numero o guion pasa a ser un guion)."""
    return (sitio["m"]["base"].rstrip("/") + "/"
            + re.sub(r"[^A-Za-z0-9-]", "-", sitio["remoto"]))


def traducir(renglones, sitio):
    """Le cambia a cada renglon el `cwd` de alla por la carpeta local.

    Se reemplaza el campo EXACTO (`"cwd":"/ruta"`): adentro de un texto las comillas van
    escapadas, asi que el contenido de la charla no se toca aunque nombre esa ruta.
    """
    viejo = ('"cwd":' + json.dumps(sitio["remoto"])).encode("utf-8")
    nuevo = ('"cwd":' + json.dumps(str(sitio["local"]))).encode("utf-8")
    return renglones.replace(viejo, nuevo)


def sincronizar(m):
    """Trae lo que crecio de las transcripciones de esa maquina. Devuelve cuantas cambio.

    Un solo viaje para mirar todos los sitios (cada conexion cuesta un par de segundos), y
    despues uno por cada charla que crecio.
    ⚠ Solo se anota como traido lo que termina en salto de renglon: si se copia medio
    renglon (alla estan escribiendo en este instante), el lector del panel se encuentra con
    un JSON roto. La cola incompleta se vuelve a pedir en la vuelta siguiente.
    """
    lista = sitios(m)
    carpeta_local(m).mkdir(parents=True, exist_ok=True)
    mirar = "; ".join(
        "(cd %s 2>/dev/null && stat -c '%d %%s %%Y %%n' *.jsonl 2>/dev/null)"
        % (_comilla(_transcripciones(s)), i) for i, s in enumerate(lista))
    codigo, salida = _ssh(m, mirar + "; true")
    if codigo == 255:
        return 0
    estado = _leer_estado(m)
    cambiadas = 0
    for renglon in salida.decode("utf-8", "replace").splitlines():
        partes = renglon.split(" ", 3)
        if len(partes) != 4 or not all(p.isdigit() for p in partes[:3]):
            continue
        cual, tam, mtime, nombre = int(partes[0]), int(partes[1]), int(partes[2]), partes[3].strip()
        if cual >= len(lista):
            continue
        if not nombre.endswith(".jsonl") or not _ID_OK.match(nombre[:-6]):
            continue                       # solo charlas: nada con barras ni nombres raros
        sitio = lista[cual]
        # ⚠ ANTES de que la copia toque el disco, y tambien para las que ya estaban: el
        # guardia mira este registro.
        _anotar_charla(nombre[:-6], sitio)
        destino_local = seguir.carpeta_de(sitio["local"])
        hecho = int(estado.get(nombre) or 0)
        local = destino_local / nombre
        if tam == hecho and (local.exists() or tam == 0):
            continue
        if tam < hecho or (hecho and not local.exists()):
            hecho = 0                      # alla la reescribieron, o aca falta: de cero
        if tam == 0:
            continue
        codigo, trozo = _ssh(m, "tail -c +%d %s" % (
            hecho + 1, _comilla(_transcripciones(sitio) + "/" + nombre)), espera=60)
        if codigo != 0 or not trozo:
            continue
        corte = trozo.rfind(b"\n")
        if corte == -1:
            continue
        entero = trozo[:corte + 1]
        destino_local.mkdir(parents=True, exist_ok=True)
        with open(local, "wb" if hecho == 0 else "ab") as f:
            f.write(traducir(entero, sitio))
        try:
            os.utime(local, (mtime, mtime))    # la bandeja ordena por fecha: la de alla
        except OSError:
            pass
        estado[nombre] = hecho + len(entero)
        cambiadas += 1
    if cambiadas:
        tmp = _estado_de(m).with_suffix(".tmp")
        tmp.write_text(json.dumps(estado), encoding="utf-8")
        os.replace(tmp, _estado_de(m))
    return cambiadas


# --------------------------------------------------------------------- cuentas

def _mail_de(texto):
    try:
        d = json.loads(texto)
        return str(d.get("email") or "") if d.get("loggedIn") else ""
    except Exception:
        return ""


def _refrescar_cuentas():
    global _cuentas_cuando
    for m in maquinas():
        orden = m.get("cuenta_cmd")
        if not orden:
            continue
        codigo, salida = _ssh(m, orden, espera=30)
        if codigo == 0:
            _cuentas[m["nombre"]] = _mail_de(salida.decode("utf-8", "replace"))
    try:
        r = subprocess.run("claude auth status", shell=True, capture_output=True, timeout=30,
                           creationflags=_SIN_VENTANA)
        _cuenta_local["mail"] = _mail_de(r.stdout.decode("utf-8", "replace"))
    except Exception:
        pass
    _cuentas_cuando = time.time()


def _cuenta(m):
    """{maquina, mail, propia} de esa maquina. `propia` = es la misma cuenta que la de aca.

    No toca la red: devuelve lo ultimo que averiguo el hilo. Mientras no se sepa el mail va
    vacio y `propia` en False — ante la duda se marca como ajena, que es lo que hay que notar.
    """
    mail = _cuentas.get(m["nombre"], "")
    return {"maquina": m["nombre"], "mail": mail,
            "propia": bool(mail) and mail == _cuenta_local["mail"]}


def cuenta_de(cwd):
    """La cuenta de un cajon de arena, o None si la carpeta es comun."""
    m = maquina_de(cwd)
    return _cuenta(m) if m is not None else None


def cuenta_de_charla(sid):
    """La cuenta con la que corre esa charla, o None si corre aca."""
    c = charla(sid)
    if c is None:
        return None
    m = _maquina(c.get("maquina"))
    if m is None:       # la maquina se saco de la config: sigue siendo ajena, y se dice
        return {"maquina": str(c.get("maquina") or "?"), "mail": "", "propia": False}
    return _cuenta(m)


def marcar(proyectos):
    """Le pega a la lista del riel lo que la pantalla necesita para distinguir cuentas.

    - cada charla remota lleva `cuenta` (la chapa, el tinte y el icono salen de ahi);
    - un cajon de arena lleva `cuenta` tambien en la carpeta;
    - una carpeta donde se puede ELEGIR el servidor lleva `servidores`: es lo que hace
      aparecer la opcion en el selector de la caja de escribir.
    A lo demas no le toca nada: sin maquinas, la lista sale exactamente igual que antes.
    """
    ms = maquinas()
    if not ms:
        return proyectos
    asegurar_hilo()
    por_carpeta = {}
    for m in ms:
        for s in sitios(m):
            por_carpeta.setdefault(_plana(s["local"]), []).append(s)
    for p in proyectos:
        try:
            aca = por_carpeta.get(_plana(p.get("cwd")), [])
        except Exception:
            aca = []
        if aca:
            p["servidores"] = [dict(_cuenta(s["m"]), fijo=s["fijo"]) for s in aca]
            fijos = [s for s in aca if s["fijo"]]
            if fijos:
                p["cuenta"] = _cuenta(fijos[0]["m"])
        for s in p.get("sesiones") or []:
            c = cuenta_de_charla(s.get("id")) or p.get("cuenta")
            if c:
                s["cuenta"] = c
    return proyectos


# ------------------------------------------------------------------------ hilo

def _vuelta():
    for m in maquinas():
        try:
            sincronizar(m)
        except Exception as e:
            print("remotas: no pude copiar las charlas de %s: %s" % (m.get("nombre"), e),
                  flush=True)


def _bucle():
    while True:
        try:
            if time.time() - _cuentas_cuando > CUENTA_VALE_SEG:
                _refrescar_cuentas()
            _vuelta()
        except Exception as e:
            print("remotas: fallo una vuelta del espejo:", e, flush=True)
        hasta = time.time() + LENTO_SEG
        while time.time() < hasta:
            if _en_vuelo > 0:
                time.sleep(RAPIDO_SEG)
                break
            time.sleep(1)


def asegurar_hilo():
    """Prende el hilo del espejo la primera vez que hace falta. Sin maquinas, no prende."""
    global _hilo
    with _candado:
        if _hilo is not None and _hilo.is_alive():
            return
        if not maquinas():
            return
        _hilo = threading.Thread(target=_bucle, daemon=True, name="remotas-espejo")
        _hilo.start()


# ---------------------------------------------------------------------- mandar

def _leer_respuesta(salida):
    """De lo que imprime `despachar.sh` saca (sesion, estado, texto)."""
    sesion, estado, resto = "", "", []
    for renglon in salida.decode("utf-8", "replace").splitlines():
        if not sesion and renglon.startswith("SESION: "):
            sesion = renglon[8:].strip()
        elif not estado and renglon.startswith("ESTADO: "):
            estado = renglon[8:].strip()
        elif estado:
            resto.append(renglon)
    return sesion, estado, "\n".join(resto).strip()


def mandar(cwd, sid, texto, al_nacer=None, cerebro=""):
    """Un turno contra una charla de otra maquina. Devuelve (respuesta, sesion).

    La forma es la de `sesiones_movil.mandar`, que es quien la llama: los errores salen
    como excepcion con un texto que se le puede mostrar a Martin tal cual.
    """
    global _en_vuelo
    sid = (sid or "").strip()
    if sid and not _ID_OK.match(sid):
        raise RuntimeError("Esa charla no tiene un id que el servidor entienda.")
    sitio = destino(cwd, sid, cerebro)
    if sitio is None:
        raise RuntimeError("Eso no es de ninguna máquina remota.")
    m = sitio["m"]
    orden = m["despachar"] + " --en " + _comilla(sitio["remoto"]) + ((" " + sid) if sid else "")
    with _candado:
        _en_vuelo += 1
    try:
        proc = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "ServerAliveInterval=30", m["ssh"], orden],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=_SIN_VENTANA)
        proc.stdin.write(texto.encode("utf-8"))
        proc.stdin.close()
        primero = proc.stdout.readline()
        sesion = _leer_respuesta(primero)[0]
        if not sesion or not _ID_OK.match(sesion):
            resto = primero + proc.stdout.read()
            proc.wait()
            aviso = (resto.decode("utf-8", "replace").strip()
                     or proc.stderr.read().decode("utf-8", "replace").strip())
            raise RuntimeError("No pude mandarlo a %s: %s" % (
                m["nombre"], aviso[:200] or "no contestó (¿está apagada o sin red?)"))
        _anotar_charla(sesion, sitio)          # antes de que exista su copia aca
        if not sid and al_nacer:
            # La pantalla se engancha a la charla leyendo el DISCO: se espera a que la
            # copia exista aca antes de avisarle que nacio.
            local = seguir.carpeta_de(sitio["local"]) / (sesion + ".jsonl")
            for _ in range(10):
                try:
                    sincronizar(m)
                except Exception:
                    pass
                if local.exists():
                    break
                time.sleep(1)
            try:
                al_nacer(sesion)
            except Exception:
                pass
        salida = primero + proc.stdout.read()
        proc.wait()
        _s, estado, respuesta = _leer_respuesta(salida)
        # Si la conexion se corto a mitad, el trabajo siguio alla: se le pregunta.
        limite = time.time() + ESPERA_MAX_SEG
        while estado in ("", "trabajando") and time.time() < limite:
            time.sleep(5)
            codigo, salida = _ssh(m, m["despachar"] + " --ver " + sesion, espera=30)
            if codigo == 0:
                _s, estado, respuesta = _leer_respuesta(salida)
        try:
            sincronizar(m)
        except Exception:
            pass
        if estado != "listo":
            raise RuntimeError("En %s el pedido terminó mal (%s): %s" % (
                m["nombre"], estado or "sin respuesta", respuesta[:200]))
        return respuesta, sesion
    finally:
        with _candado:
            _en_vuelo -= 1
