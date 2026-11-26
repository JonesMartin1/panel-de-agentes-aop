"""Las charlas de OTRA maquina en el riel de /sesiones (`app/voz/remotas.py`).

    python -m pruebas.probar_remotas            # los chequeos
    python -m pruebas.probar_remotas --mutar    # ademas rompe cada regla y exige que se note

No toca la red, ni el servidor, ni `~/.claude`: el SSH es de mentira y todo se escribe en
una carpeta temporal. Lo que cuida:

- que la copia no deje nunca medio renglon (el lector del panel se encontraria un JSON roto);
- que el `cwd` de cada renglon quede apuntando a la carpeta local;
- que una charla remota quede ANOTADA como tal antes de que su copia toque el disco, tambien
  cuando vive adentro de un proyecto comun, mezclada con las de aca;
- que lo que no se puede resolver salga como ERROR y no como "corre aca";
- que con el servidor apagado no explote nada;
- que la chapa de cuenta no diga "es la tuya" cuando todavia no se sabe de quien es;
- que un pedido que termino mal salga como error y no como respuesta;
- y, sobre el modulo de sesiones de verdad, que una charla remota no arranque un `claude`
  local ni por `mandar` ni por `_arrancar_viva`.
"""
import io
import json
import re
import sys
import tempfile
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "app" / "voz" / "remotas.py"
SID_A = "11111111-2222-3333-4444-555555555555"
SID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SID_P = "99999999-8888-7777-6666-555555555555"      # nace adentro de un proyecto comun
SID_LOCAL = "00000000-0000-0000-0000-000000000001"  # una charla de aca, del mismo proyecto
CAJON = "/trabajo"
REMOTO_PROY = "/trabajo/proy"
BASE = "/alla/charlas"


def renglon(i, cwd=CAJON, texto="hola"):
    return (json.dumps({"n": i, "cwd": cwd, "texto": texto}, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


class Servidor:
    """El otro lado, de mentira: carpetas con archivos y lo que contesta `despachar.sh`."""

    def __init__(self):
        self.carpetas = {BASE + "/-trabajo": {}, BASE + "/-trabajo-proy": {}}
        self.caido = False
        self.cuenta = json.dumps({"loggedIn": True, "email": "otra@ejemplo.com"})
        self.ver = b""
        self.pedidos = []
        self.al_traer = None        # para mirar el registro EN EL MOMENTO de la copia

    def ssh(self, m, comando, entrada=None, espera=20):
        self.pedidos.append(comando)
        if self.caido:
            return 255, b"ssh: connect to host: timed out"
        if "stat -c" in comando:
            salida = ""
            for carpeta, idx in re.findall(r"cd '([^']*)' 2>/dev/null && stat -c '(\d+) ", comando):
                for n, c in self.carpetas.get(carpeta, {}).items():
                    salida += "%s %d %d %s\n" % (idx, len(c), 1700000000, n)
            return 0, salida.encode()
        if comando.startswith("tail -c +"):
            desde = int(comando.split("+", 1)[1].split(" ", 1)[0])
            ruta = comando.split("'", 1)[1].rstrip("'")
            carpeta, nombre = ruta.rsplit("/", 1)
            if self.al_traer:
                self.al_traer(nombre)
            return 0, self.carpetas.get(carpeta, {}).get(nombre, b"")[desde - 1:]
        if "--ver" in comando:
            return 0, self.ver
        if "auth status" in comando:
            return 0, self.cuenta.encode()
        return 1, b""


class ProcesoFalso:
    def __init__(self, salida):
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None
        self.stdout = io.BytesIO(salida)
        self.stderr = io.BytesIO(b"")

    def wait(self):
        return 0


def cargar(fuente, tmp, servidor):
    """El modulo, armado desde su texto (asi se puede mutar) y enchufado a lo de mentira."""
    mod = types.ModuleType("remotas_prueba")
    mod.__file__ = str(FUENTE)
    exec(compile(fuente, str(FUENTE), "exec"), mod.__dict__)
    mod.REMOTAS = tmp / "remotas"
    mod.REMOTAS_MAQUINAS = mod.REMOTAS / "maquinas.json"
    mod.REMOTAS.mkdir(parents=True, exist_ok=True)
    (tmp / "proyecto").mkdir()
    (tmp / "otra").mkdir()
    mod.REMOTAS_MAQUINAS.write_text(json.dumps([
        {"nombre": "servidor", "ssh": "servidor", "base": BASE, "cwd_remoto": CAJON,
         "despachar": "/alla/despachar.sh", "cuenta_cmd": "auth status",
         "proyectos": [{"local": str(tmp / "proyecto"), "remoto": REMOTO_PROY},
                       {"local": str(tmp / "tramposa"), "remoto": "/trabajo/../etc"},
                       {"local": str(tmp / "rara"), "remoto": "/tra bajo; rm"}]},
        {"nombre": "../mala", "ssh": "x", "base": "/x", "cwd_remoto": "/x", "despachar": "/x"},
        {"nombre": "incompleta"},
    ]), encoding="utf-8")
    proyectos = tmp / "proyectos"

    class Seguir:
        @staticmethod
        def carpeta_de(ruta):
            return proyectos / re.sub(r"[^A-Za-z0-9-]", "-", str(ruta))

    mod.seguir = Seguir
    mod._ssh = servidor.ssh
    lanzados = []

    class Sub:
        PIPE = -1
        CREATE_NO_WINDOW = 0

        @staticmethod
        def Popen(args, **kw):
            lanzados.append(args)
            return ProcesoFalso(servidor.despacho)

        @staticmethod
        def run(*a, **kw):
            return types.SimpleNamespace(returncode=0, stdout=servidor.local.encode())

    mod.subprocess = Sub
    mod.time = types.SimpleNamespace(time=__import__("time").time, sleep=lambda s: None)
    mod.asegurar_hilo = lambda: None          # en la prueba no hay hilo: se llama a mano
    mod.lanzados = lanzados
    servidor.despacho = b""
    servidor.local = json.dumps({"loggedIn": True, "email": "yo@ejemplo.com"})
    return mod


def chequeos(fuente):
    """Corre todo contra esa version del modulo. Devuelve [(nombre, ok, detalle)]."""
    res = []

    def anotar(nombre, ok, detalle=""):
        res.append((nombre, bool(ok), detalle))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        srv = Servidor()
        mod = cargar(fuente, tmp, srv)
        ms = mod.maquinas()
        anotar("la configuracion deja pasar solo las maquinas bien escritas",
               [m["nombre"] for m in ms] == ["servidor"], str([m.get("nombre") for m in ms]))
        m = ms[0]
        cajon = mod.carpeta_local(m)
        proyecto = tmp / "proyecto"
        ss = mod.sitios(m)
        anotar("los sitios: el cajon primero, y solo los proyectos con una ruta sana",
               [(str(s["local"]), s["remoto"], s["fijo"]) for s in ss]
               == [(str(cajon), CAJON, True), (str(proyecto), REMOTO_PROY, False)],
               str([(s["remoto"], s["fijo"]) for s in ss]))
        s_cajon, s_proy = ss[0], ss[1]
        d_cajon = mod.seguir.carpeta_de(cajon)
        d_proy = mod.seguir.carpeta_de(proyecto)

        anotar("solo el cajon es una CARPETA remota; un proyecto preparado no",
               mod.es_remota(str(cajon)) and not mod.es_remota(str(proyecto))
               and not mod.es_remota(str(tmp / "otra")) and not mod.es_remota(""))

        # --- traducir
        contenido = json.dumps({"cwd": REMOTO_PROY, "texto": 'dice "cwd":"/trabajo/proy" adentro'},
                               separators=(",", ":")).encode() + b"\n"
        d = json.loads(mod.traducir(contenido, s_proy))
        anotar("el cwd de cada renglon pasa a ser la carpeta local",
               d["cwd"] == str(proyecto), d["cwd"])
        anotar("el texto de la charla no se toca aunque nombre esa ruta",
               d["texto"] == 'dice "cwd":"/trabajo/proy" adentro', d["texto"])

        # --- la copia: nunca medio renglon, y cada charla a SU carpeta
        entero = renglon(1) + renglon(2)
        medio = renglon(3)
        srv.carpetas[BASE + "/-trabajo"][SID_A + ".jsonl"] = entero + medio[:20]
        srv.carpetas[BASE + "/-trabajo"]["notas.jsonl"] = renglon(9)
        srv.carpetas[BASE + "/-trabajo"]["../" + SID_B + ".jsonl"] = renglon(9)
        srv.carpetas[BASE + "/-trabajo-proy"][SID_P + ".jsonl"] = renglon(1, REMOTO_PROY)
        anotados_al_traer = {}
        srv.al_traer = lambda nombre: anotados_al_traer.setdefault(
            nombre, mod.charla(nombre[:-6]) is not None)
        n = mod.sincronizar(m)
        srv.al_traer = None
        f = d_cajon / (SID_A + ".jsonl")
        lineas = f.read_bytes().splitlines() if f.exists() else []
        sanas = 0
        for linea in lineas:
            try:
                json.loads(linea)
                sanas += 1
            except Exception:
                pass
        anotar("la primera copia trae solo renglones enteros",
               n == 2 and len(lineas) == 2 and sanas == 2,
               "copiadas=%s renglones=%s sanos=%s" % (n, len(lineas), sanas))
        anotar("lo que no tiene nombre de charla no se copia",
               sorted(p.name for p in d_cajon.glob("*")) == [SID_A + ".jsonl"]
               and not list(tmp.rglob("notas.jsonl")),
               str(sorted(p.name for p in d_cajon.glob("*"))))
        fp = d_proy / (SID_P + ".jsonl")
        anotar("la charla de un proyecto preparado cae en la carpeta de ESE proyecto",
               fp.exists() and json.loads(fp.read_bytes().splitlines()[0])["cwd"] == str(proyecto),
               str(sorted(p.name for p in d_proy.glob("*")) if d_proy.exists() else "no existe"))
        anotar("queda anotada como remota ANTES de que su copia toque el disco",
               anotados_al_traer.get(SID_P + ".jsonl") is True
               and anotados_al_traer.get(SID_A + ".jsonl") is True, str(anotados_al_traer))
        c = mod.charla(SID_P)
        anotar("el registro dice de que maquina es y en que carpeta vive",
               c == {"maquina": "servidor", "local": str(proyecto)}, str(c))
        anotar("una charla de aca, del mismo proyecto, no figura como remota",
               mod.charla(SID_LOCAL) is None and mod.charla("") is None)

        srv.carpetas[BASE + "/-trabajo"][SID_A + ".jsonl"] = entero + medio + renglon(4)
        mod.sincronizar(m)
        lineas = f.read_bytes().splitlines()
        try:
            ns = [json.loads(x)["n"] for x in lineas]
        except Exception as e:
            ns = "roto: %s" % e
        anotar("la segunda vuelta agrega lo nuevo sin repetir ni romper", ns == [1, 2, 3, 4],
               str(ns))
        antes = len(srv.pedidos)
        anotar("sin cambios no se trae nada, y mirar todo es UN solo viaje",
               mod.sincronizar(m) == 0 and len(srv.pedidos) == antes + 1)

        srv.carpetas[BASE + "/-trabajo"][SID_A + ".jsonl"] = renglon(7)
        mod.sincronizar(m)
        anotar("si alla la charla se achico, aca se rehace de cero",
               [json.loads(x)["n"] for x in f.read_bytes().splitlines()] == [7])

        srv.caido = True
        try:
            r = mod.sincronizar(m)
            anotar("con el servidor apagado no explota ni borra nada",
                   r == 0 and f.read_bytes() == mod.traducir(renglon(7), s_cajon))
        except Exception as e:
            anotar("con el servidor apagado no explota ni borra nada", False, repr(e))
        srv.caido = False

        # --- a donde va un turno
        def va(cwd, sid="", cerebro=""):
            try:
                s = mod.destino(str(cwd), sid, cerebro)
                return None if s is None else s["remoto"]
            except RuntimeError as e:
                return "ERROR: " + str(e)

        anotar("una charla comun de un proyecto preparado corre aca",
               va(proyecto, SID_LOCAL) is None and va(proyecto) is None, str(va(proyecto, SID_LOCAL)))
        anotar("la charla remota de ese proyecto va alla, sin que la pantalla lo diga",
               va(proyecto, SID_P) == REMOTO_PROY, str(va(proyecto, SID_P)))
        anotar("una nueva va alla solo si la pantalla lo pide",
               va(proyecto, "", "servidor:servidor") == REMOTO_PROY
               and va(proyecto, "", "codex") is None and va(proyecto, "", "auto") is None)
        anotar("en el cajon va alla siempre, se pida lo que se pida",
               va(cajon) == CAJON and va(cajon, "", "codex") == CAJON and va(cajon, SID_A) == CAJON)
        r = va(tmp / "otra", "", "servidor:servidor")
        anotar("pedir el servidor en una carpeta SIN preparar es un error, no 'corre aca'",
               isinstance(r, str) and r.startswith("ERROR") and "preparada" in r, str(r))
        r = va(proyecto, "", "servidor:inventada")
        anotar("pedir una maquina que no existe es un error",
               isinstance(r, str) and r.startswith("ERROR"), str(r))
        anotar("el servidor no se le puede pedir a una charla de aca ya nacida",
               va(proyecto, SID_LOCAL, "servidor:servidor") is None)
        mod._anotar_charla(SID_B, {"m": {"nombre": "desaparecida"}, "local": proyecto})
        r = va(proyecto, SID_B)
        anotar("una charla de una maquina que ya no esta configurada es un error, no 'corre aca'",
               isinstance(r, str) and r.startswith("ERROR"), str(r))

        # --- lo que mira el guardia
        anotar("el guardia: por la carpeta, por la charla y por la que se quiere copiar",
               mod.es_de_otra_maquina(str(cajon)) and mod.es_de_otra_maquina(str(proyecto), SID_P)
               and mod.es_de_otra_maquina(str(proyecto), "", SID_P)
               and mod.es_de_otra_maquina(str(proyecto), SID_B)
               and not mod.es_de_otra_maquina(str(proyecto), SID_LOCAL)
               and not mod.es_de_otra_maquina(str(proyecto)))

        # --- la cuenta
        c = mod.cuenta_de(str(cajon))
        anotar("mientras no se sabe la cuenta, NO se marca como propia",
               c is not None and c["mail"] == "" and c["propia"] is False, str(c))
        mod._cuenta_local["mail"] = ""
        anotar("ni aunque tampoco se sepa la de aca", mod.cuenta_de(str(cajon))["propia"] is False)
        mod._refrescar_cuentas()
        c = mod.cuenta_de_charla(SID_P)
        anotar("otra cuenta: ajena", c["mail"] == "otra@ejemplo.com" and c["propia"] is False,
               str(c))
        srv.cuenta = json.dumps({"loggedIn": True, "email": "yo@ejemplo.com"})
        mod._refrescar_cuentas()
        anotar("la misma cuenta: propia", mod.cuenta_de_charla(SID_P)["propia"] is True)
        anotar("una carpeta comun y una charla comun no tienen cuenta",
               mod.cuenta_de(str(proyecto)) is None and mod.cuenta_de_charla(SID_LOCAL) is None)
        c = mod.cuenta_de_charla(SID_B)
        anotar("la de una maquina que ya no esta sigue marcada como ajena",
               c is not None and c["propia"] is False, str(c))

        # --- marcar
        lista = [{"cwd": str(tmp / "otra"), "sesiones": [{"id": "x"}]},
                 {"cwd": str(cajon), "sesiones": [{"id": SID_A}]},
                 {"cwd": str(proyecto), "sesiones": [{"id": SID_P}, {"id": SID_LOCAL}]}]
        mod.marcar(lista)
        anotar("a una carpeta comun la lista no le toca nada",
               "cuenta" not in lista[0] and "servidores" not in lista[0]
               and "cuenta" not in lista[0]["sesiones"][0])
        anotar("el cajon va marcado entero, y solo ofrece su servidor",
               bool(lista[1].get("cuenta")) and bool(lista[1]["sesiones"][0].get("cuenta"))
               and [s["fijo"] for s in lista[1].get("servidores", [])] == [True])
        anotar("en un proyecto preparado se marca SOLO la charla remota",
               "cuenta" not in lista[2] and bool(lista[2]["sesiones"][0].get("cuenta"))
               and "cuenta" not in lista[2]["sesiones"][1]
               and [(s["maquina"], s["fijo"]) for s in lista[2].get("servidores", [])]
               == [("servidor", False)], str(lista[2]))

        # --- mandar
        srv.despacho = ("SESION: %s\nESTADO: listo\nhecho\nsegundo renglon\n" % SID_B).encode()
        mod._anotar_charla(SID_B, s_cajon)
        nacidas = []
        try:
            r = mod.mandar(str(cajon), "", "hola", al_nacer=nacidas.append)
        except Exception as e:
            r = repr(e)
        anotar("un pedido nuevo devuelve la respuesta y la sesion que nacio",
               r == ("hecho\nsegundo renglon", SID_B) and nacidas == [SID_B], str(r))
        mod.lanzados.clear()
        try:
            mod.mandar(str(proyecto), SID_P, "seguí")
        except Exception:
            pass
        orden = mod.lanzados[-1][-1] if mod.lanzados else ""
        anotar("seguir una charla le pasa su id y SU carpeta al otro lado",
               orden == "/alla/despachar.sh --en '%s' %s" % (REMOTO_PROY, SID_P), orden)

        nuevo = "bbbbbbbb-1111-2222-3333-444444444444"
        srv.despacho = ("SESION: %s\nESTADO: listo\nnacio alla\n" % nuevo).encode()
        mod.lanzados.clear()
        try:
            r = mod.mandar(str(proyecto), "", "hola", cerebro="servidor:servidor")
        except Exception as e:
            r = repr(e)
        anotar("una charla nueva pedida al servidor nace alla y queda anotada",
               r == ("nacio alla", nuevo) and mod.charla(nuevo) is not None
               and mod.lanzados[-1][-1] == "/alla/despachar.sh --en '%s'" % REMOTO_PROY, str(r))

        srv.despacho = ("SESION: %s\nESTADO: error\nse rompio\n" % SID_A).encode()
        try:
            r = mod.mandar(str(cajon), SID_A, "hola")
            anotar("un pedido que termino mal sale como error", False, str(r))
        except RuntimeError as e:
            anotar("un pedido que termino mal sale como error", "se rompio" in str(e), str(e))

        srv.despacho = b""
        try:
            mod.mandar(str(cajon), SID_A, "hola")
            anotar("si el otro lado no contesta, lo dice", False)
        except RuntimeError as e:
            anotar("si el otro lado no contesta, lo dice", "No pude mandarlo" in str(e), str(e))

        mod.lanzados.clear()
        try:
            mod.mandar(str(cajon), "abc; rm -rf /", "hola")
            anotar("un id raro se rechaza ANTES de salir a la red", False)
        except RuntimeError:
            anotar("un id raro se rechaza ANTES de salir a la red", not mod.lanzados,
                   str(mod.lanzados))

        srv.despacho = ("SESION: %s\n" % SID_A).encode()      # se corto la conexion
        srv.ver = ("SESION: %s\nESTADO: listo\ntermino igual\n" % SID_A).encode()
        try:
            r = mod.mandar(str(cajon), SID_A, "hola")
        except Exception as e:
            r = repr(e)
        anotar("si se corta la conexion, pregunta como termino", r == ("termino igual", SID_A),
               str(r))

        mod.lanzados.clear()
        try:
            mod.mandar(str(tmp / "otra"), "", "hola")
            anotar("mandar a una carpeta comun se niega sin salir a la red", False)
        except RuntimeError:
            anotar("mandar a una carpeta comun se niega sin salir a la red", not mod.lanzados)
    return res


MUTACIONES = [
    ("copiar medio renglon",
     'corte = trozo.rfind(b"\\n")', "corte = len(trozo) - 1"),
    ("no traducir el cwd",
     "return renglones.replace(viejo, nuevo)", "return renglones"),
    ("copiar cualquier nombre de archivo",
     'if not nombre.endswith(".jsonl") or not _ID_OK.match(nombre[:-6]):', "if False:"),
    ("copiar la charla sin anotarla antes como remota",
     "        _anotar_charla(nombre[:-6], sitio)\n", "        pass\n"),
    ("mirar solo la carpeta para saber si una charla es remota",
     "return es_remota(cwd) or charla(sid) is not None or charla(desde) is not None",
     "return es_remota(cwd)"),
    ("dar por local una charla cuya maquina ya no esta configurada",
     '''        if m is None:
            raise RuntimeError("Esa charla es de una máquina (%s) que ya no está configurada."
                               % c.get("maquina"))''',
     "        if m is None:\n            return None"),
    ("dar por local un pedido al servidor en una carpeta sin preparar",
     '''        if s is None:
            raise RuntimeError("Esta carpeta no está preparada en %s: allá no hay dónde "
                               "trabajar." % m["nombre"])''',
     "        if s is None:\n            return None"),
    ("aceptar como carpeta de alla una ruta con puntos o espacios",
     'and _RUTA_REMOTA_OK.match(remoto) and ".." not in remoto):', "):"),
    ("dar por propia una cuenta que no se conoce",
     '"propia": bool(mail) and mail == _cuenta_local["mail"]}',
     '"propia": mail == _cuenta_local["mail"]}'),
    ("marcar todas las charlas de un proyecto preparado",
     'c = cuenta_de_charla(s.get("id")) or p.get("cuenta")',
     'c = cuenta_de_charla(s.get("id")) or p.get("cuenta") or (aca and _cuenta(aca[0]["m"]))'),
    ("no decirle al otro lado en que carpeta trabajar",
     'orden = m["despachar"] + " --en " + _comilla(sitio["remoto"]) + ((" " + sid) if sid else "")',
     'orden = m["despachar"] + ((" " + sid) if sid else "")'),
    ("devolver como respuesta un pedido que termino mal",
     'if estado != "listo":', "if False:"),
    ("dejar salir a la red un id sin forma de id",
     "if sid and not _ID_OK.match(sid):", "if False:"),
    ("no preguntar como termino si se corto la conexion",
     'while estado in ("", "trabajando") and time.time() < limite:', "while False:"),
]


def sesiones_de_verdad():
    """Sobre `sesiones_movil` real: una charla remota no arranca nada local."""
    res = []
    from app.voz import remotas, sesiones_movil as sm
    with tempfile.TemporaryDirectory() as t:
        cajon = str(Path(t) / "servidor")
        proyecto = str(Path(t) / "proyecto")
        viejos = (remotas.es_de_otra_maquina, remotas.destino, remotas.mandar)
        viejo_popen, viejo_conseguir = sm.subprocess.Popen, sm._conseguir_viva
        lanzo = []

        def popen_trampa(*a, **kw):
            lanzo.append(a)
            raise RuntimeError("LANZO UN PROCESO LOCAL")

        def destino(cwd, sid="", cerebro=""):
            if str(cwd) == cajon or sid == SID_P or (not sid and cerebro == "servidor:x"):
                return {"remoto": "/alla"}
            return None

        try:
            remotas.es_de_otra_maquina = lambda cwd, sid="", desde="": (
                str(cwd) == cajon or SID_P in (sid, desde))
            remotas.destino = destino
            remotas.mandar = lambda cwd, sid, texto, al_nacer=None, cerebro="": ("desde alla", SID_P)
            sm.subprocess.Popen = popen_trampa
            sm._conseguir_viva = lambda *a, **kw: popen_trampa("conseguir_viva")
            for nombre, args, kw in (
                    ("el guardia frena el arranque local en el cajon de una maquina",
                     (cajon, SID_A, "", ""), {}),
                    ("el guardia frena una charla remota que vive en un proyecto comun",
                     (proyecto, SID_P, "", ""), {}),
                    ("el guardia frena bifurcar una charla remota",
                     (proyecto, "", "", ""), {"desde": SID_P})):
                try:
                    sm._arrancar_viva(*args, **kw)
                    res.append((nombre, False, "arranco"))
                except RuntimeError as e:
                    res.append((nombre, not lanzo and "otra máquina" in str(e), str(e)))
            if not sm.freno_puesto():
                for nombre, args, kw in (
                        ("un mensaje a una charla remota de un proyecto comun viaja al otro lado",
                         (proyecto, SID_P, "hola"), {}),
                        ("una charla nueva pedida al servidor no arranca nada aca",
                         (proyecto, "", "hola"), {"cerebro": "servidor:x"}),
                        ("aunque pidan Codex: en el cajon manda la maquina",
                         (cajon, "", "hola"), {"cerebro": "codex"})):
                    try:
                        r = sm.mandar(*args, **kw)
                    except Exception as e:
                        r = repr(e)
                    res.append((nombre, r == ("desde alla", SID_P) and not lanzo, str(r)))
                # y lo comun sigue yendo por el camino de siempre
                try:
                    sm.mandar(proyecto, SID_LOCAL, "hola")
                    res.append(("una charla comun del mismo proyecto sigue corriendo aca", False, ""))
                except RuntimeError as e:
                    res.append(("una charla comun del mismo proyecto sigue corriendo aca",
                                "LANZO UN PROCESO LOCAL" in str(e), str(e)))
        finally:
            remotas.es_de_otra_maquina, remotas.destino, remotas.mandar = viejos
            sm.subprocess.Popen, sm._conseguir_viva = viejo_popen, viejo_conseguir
    return res


def main():
    fuente = FUENTE.read_text(encoding="utf-8")
    res = chequeos(fuente) + sesiones_de_verdad()
    malos = [r for r in res if not r[1]]
    for nombre, ok, detalle in res:
        print(("  ok   " if ok else "  MAL  ") + nombre + ("" if ok or not detalle else "  -> " + detalle))
    print("%d chequeos, %d mal" % (len(res), len(malos)))
    if malos:
        return 1
    if "--mutar" in sys.argv:
        sin_cazar = 0
        for titulo, viejo, nuevo in MUTACIONES:
            if fuente.count(viejo) != 1:
                print("  MAL  mutacion '%s': el texto a romper aparece %d veces" % (
                    titulo, fuente.count(viejo)))
                sin_cazar += 1
                continue
            try:
                rotos = [r[0] for r in chequeos(fuente.replace(viejo, nuevo)) if not r[1]]
            except Exception as e:
                rotos = ["exploto: %r" % e]
            if rotos:
                print("  ok   rompi '%s' y lo cazo: %s" % (titulo, rotos[0]))
            else:
                print("  MAL  rompi '%s' y NO lo noto nadie" % titulo)
                sin_cazar += 1
        print("%d mutaciones, %d sin cazar" % (len(MUTACIONES), sin_cazar))
        if sin_cazar:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
