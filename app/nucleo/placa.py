"""La placa de video: quien la esta ocupando, y prender o apagar los modelos.

Pedido de Martin (2026-08-22): *"me gustaria poder apagar o prender los modelos que
ocupo para este panel desde el panel"*. Venia de tener que pedirle a una sesion de
Codex que matara Ollama y Whisper a mano para que entrara el generador 3D — la placa
son 8 GB y no entran todos juntos.

⭐⭐ **El truco esta en la columna `type` de `nvidia-smi pmon`**, y costo encontrarlo:
`nvidia-smi --query-compute-apps` en esta laptop devuelve VEINTE procesos que no tienen
nada que ver (explorer.exe, Telegram, WhatsApp, la interfaz de Avast). En Windows con
WDDM todo lo que dibuja una ventana aparece ahi. `pmon` en cambio marca cada proceso
como `C` (computo), `G` (graficos) o `C+G`: los modelos son `C` PELADO y el escritorio
entero es `C+G`. Filtrando por eso la lista queda limpia — al escribir esto daba
exactamente dos: `app.voz.voz` y `app.ingesta.bot_telegram`, que son los dos que cargan
Whisper. Ver `pruebas/probar_placa.py`, que trae la salida real de `pmon` de ese dia.

⚠ **Cuanta memoria usa CADA proceso no se puede saber en esta maquina**: la columna
viene en `-` (Windows no la expone con WDDM). Por eso la pantalla muestra el total de la
placa y la LISTA de quien la ocupa, y no un numero por modelo. No es que falte hacerlo.
"""
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request

import psutil

from app.rutas import (OLLAMA_EXE, HUNYUAN_DIR, HUNYUAN_PY, HUNYUAN_CACHE,
                       HUNYUAN_PESOS, HUNYUAN_GRADIO, REMBG_CACHE)

# Cuanto vale una foto de la placa antes de volver a preguntar. `pmon` tarda ~1 s: sin
# esto, la tarjeta del panel (que repregunta sola) dejaria un nvidia-smi corriendo casi
# todo el tiempo.
FRESCO_SEG = 4.0
_CACHE = {"t": 0.0, "d": None}
_CANDADO = threading.Lock()

SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# ⭐ Que sobreviva a que se cierre el panel: los modelos tardan minutos en cargar y seria
# absurdo que reiniciar el panel te tire abajo el generador a mitad de una pieza.
SUELTO = getattr(subprocess, "DETACHED_PROCESS", 0) | SIN_VENTANA


# --- Los modelos que el panel sabe prender ------------------------------------------
# Pedido de Martin (2026-08-22): primero Ollama, y despues *"si me gustaria que aparezca
# el hunyuan tambien"*. Agregar otro es agregar una entrada aca, nada mas.
#   puerto : por donde se sabe si YA esta andando
#   raiz   : la CARPETA del modelo; un proceso es suyo si su comando la nombra
#   exes   : nombres de ejecutable que son suyos con solo verlos
#   cmd    : con que se lo prende (lista, sin shell)
#   cwd    : desde donde (varios solo andan parados en su carpeta)
#   env    : lo que hay que agregarle al entorno
#   tarda  : si carga lento, la tarjeta lo muestra "cargando" en vez de mentir
#
# ⚠⚠ **NUNCA reconocer un proceso por una palabra suelta de su linea de comando.**
# La primera version usaba `match`: "ollama" para uno y "gradio_app.py" para el otro, y
# las dos estaban mal de una forma peligrosa (2026-08-22, lo trajo Martin: *"si yo apago
# los modelos, el panel funciona mal y las sesiones quedan trabadas"*):
#   - "ollama" aparece en la linea de comando de CUALQUIER cosa que la mencione — entre
#     ellas el `bash` con el que una sesion de Claude Code corre comandos. Apretar
#     "Apagar Ollama" mientras una sesion investigaba algo sobre Ollama le mataba el
#     proceso a la sesion. Medido: 4 procesos ajenos matcheaban en ese momento.
#   - "gradio_app.py" existe IGUAL en `TripoSR`, que es otro generador que vive al lado:
#     apagar Hunyuan se llevaba puesto TripoSR.
# Por eso ahora se reconoce por la CARPETA del modelo o por el nombre del ejecutable.
MODELOS = {
    "ollama": {
        "nombre": "Ollama",
        "detalle": "el cerebro chico local",
        "puerto": 11434,
        "raiz": None,                    # no vive en una carpeta nuestra: va por el .exe
        "exes": ("ollama.exe", "ollama_llama_server.exe", "ollama app.exe"),
        "cmd": [None, "serve"],          # el exe se resuelve al vuelo (ver `_exe_de`)
        "exe": OLLAMA_EXE,
        "busca_en_path": "ollama",
        "cwd": None,
        "env": {},
        "tarda": False,
    },
    "hunyuan": {
        "nombre": "Generador 3D (Hunyuan)",
        "detalle": "Hunyuan3D 2mini, imagen a modelo 3D",
        "puerto": 7860,
        # ⚠ Su carpeta, no "gradio_app.py": TripoSR tiene un archivo con ese mismo nombre.
        "raiz": HUNYUAN_DIR,
        "exes": (),
        "exe": HUNYUAN_PY,
        "cmd": [None, "gradio_app.py",
                "--model_path", "tencent/Hunyuan3D-2mini",
                "--subfolder", "hunyuan3d-dit-v2-mini-turbo",
                # ⚠ Los tres de abajo son lo que hace que ENTRE en 8 GB: sin texturas,
                # en modo poca memoria. Sacarlos es quedarse sin placa a mitad de camino.
                "--disable_tex", "--low_vram_mode",
                "--host", "127.0.0.1", "--port", "7860",
                "--cache-path", str(HUNYUAN_GRADIO)],
        "cwd": HUNYUAN_DIR,
        "env": {"HF_HOME": str(HUNYUAN_CACHE),
                "HY3DGEN_MODELS": str(HUNYUAN_PESOS),
                "U2NET_HOME": str(REMBG_CACHE)},
        "tarda": True,                   # carga 1,68 GB de pesos antes de abrir el 7860
        "procesos": (),
    },
}
OLLAMA_PUERTO = MODELOS["ollama"]["puerto"]


def _correr(cmd, seg=8):
    """Un comando corto, sin ventana negra. Devuelve su salida o '' si fallo."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=seg,
                           creationflags=SIN_VENTANA)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def hay_placa():
    return shutil.which("nvidia-smi") is not None


def memoria():
    """Cuanta memoria de la placa esta usada, en MiB. {} si no hay placa NVIDIA."""
    salida = _correr(["nvidia-smi", "--query-gpu=memory.used,memory.total,name",
                      "--format=csv,noheader,nounits"], seg=6)
    linea = (salida or "").strip().splitlines()
    if not linea:
        return {}
    partes = [x.strip() for x in linea[0].split(",")]
    try:
        usado, total = int(partes[0]), int(partes[1])
    except (ValueError, IndexError):
        return {}
    return {"usado": usado, "total": total,
            "pct": round(usado * 100 / total) if total else 0,
            "placa": partes[2] if len(partes) > 2 else ""}


def _pmon():
    """Una sola pasada de `nvidia-smi pmon`, partida en computo y graficos.

    Devuelve {"computo": [pid...], "graficos": [pid...]}. `C` pelado son los modelos;
    `C+G` es todo lo que dibuja una ventana en Windows.
    """
    salida = _correr(["nvidia-smi", "pmon", "-c", "1"], seg=10)
    d = {"computo": [], "graficos": []}
    for linea in (salida or "").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        campos = linea.split()
        if len(campos) < 3:
            continue
        tipo = campos[2].upper()
        if "C" not in tipo and "G" not in tipo:
            continue
        try:
            pid = int(campos[1])
        except ValueError:
            continue
        d["graficos" if "G" in tipo else "computo"].append(pid)
    return d


def _pids_computo():
    """Los pids que estan usando la placa PARA CALCULAR (type `C`, sin `G`).

    Ver el comentario de arriba: sin este filtro entra el escritorio entero.
    """
    return _pmon()["computo"]


def escritorio(pids):
    """Que es ese pedazo de placa que NO es de ningun modelo.

    ⭐ Martin lo preguntó apenas vio la tarjeta (2026-08-22): *"¿cuál es ese proceso que
    ocupa 1 GB de mi gráfica?"* — la lista estaba vacía y el medidor marcaba 1 GB, así que
    el número quedaba sin dueño. No es un proceso: son VEINTE programas dibujando ventanas
    (el explorador, WhatsApp, Telegram, el navegador, Avast). Es el piso normal de Windows
    y no se puede bajar apagando modelos, que era la conclusión peligrosa.
    """
    nombres, vistos = [], set()
    for pid in pids:
        try:
            n = psutil.Process(pid).name()
        except Exception:
            continue
        lindo = {"explorer.exe": "el escritorio", "msedgewebview2.exe": "el navegador",
                 "WhatsApp.Root.exe": "WhatsApp", "Telegram.exe": "Telegram",
                 "AvastUI.exe": "Avast", "WindowsTerminal.exe": "la terminal",
                 "ArmouryCrate.exe": "Armoury Crate"}.get(n)
        if lindo and lindo not in vistos:
            vistos.add(lindo)
            nombres.append(lindo)
    return {"cuantos": len(pids), "nombres": nombres[:4]}


def _bautizar(proc):
    """Un nombre en criollo para el proceso, mirando con que lo lanzaron.

    Devuelve (nombre, detalle). Lo que no se reconoce sale con su nombre de archivo:
    mejor una fila fea que esconderle a Martin algo que le esta comiendo la placa.
    """
    try:
        nombre_exe = (proc.name() or "").lower()
        cmd = " ".join(proc.cmdline() or "").lower()
    except Exception:
        return "", ""
    conocidos = [
        ("app.voz.voz", "Voz de Laura", "Whisper turbo + la palabra clave + Piper"),
        ("app.ingesta.bot_telegram", "Bot de Telegram", "Whisper para los audios que entran"),
        ("app.ingesta.webhook_wasender", "Webhook de WhatsApp", "Whisper para los audios que entran"),
        ("hunyuan", "Generador 3D (Hunyuan)", "el que te comio la placa el 22/8"),
        ("triposr", "Generador 3D (TripoSR)", ""),
        ("gradio", "Una interfaz Gradio", "alguna pantalla de modelos"),
        ("comfyui", "ComfyUI", ""),
    ]
    for aguja, lindo, detalle in conocidos:
        if aguja in cmd:
            return lindo, detalle
    if "ollama" in nombre_exe or "ollama" in cmd:
        return "Ollama", "el cerebro chico local"
    return proc.name() or "?", cmd[-70:]


def procesos(pids=None):
    """Quien esta ocupando la placa ahora: [{pid, nombre, detalle, cmd}]."""
    filas = []
    for pid in (_pids_computo() if pids is None else pids):
        try:
            p = psutil.Process(pid)
            nombre, detalle = _bautizar(p)
            if not nombre:
                continue
            filas.append({"pid": pid, "nombre": nombre, "detalle": detalle,
                          "exe": p.name(),
                          "cmd": " ".join(p.cmdline() or "")[:300]})
        except Exception:
            # murio entre el pmon y el psutil: no es un error, es una carrera normal
            continue
    return filas


# --- Ollama -------------------------------------------------------------------------

def _puerto_abierto(puerto, seg=0.4):
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=seg):
            return True
    except OSError:
        return False


def _exe_de(m):
    """El ejecutable de ese modelo, o '' si no esta instalado en esta maquina."""
    if m.get("busca_en_path"):
        hallado = shutil.which(m["busca_en_path"])
        if hallado:
            return hallado
    exe = m.get("exe")
    return str(exe) if exe and exe.exists() else ""


def es_de(m, nombre_exe, cmd):
    """¿Ese proceso es de ese modelo? Por su ejecutable o por SU CARPETA, nunca por una
    palabra suelta. Ver el aviso grande de `MODELOS`: reconocerlo por una palabra hacia
    que apagar un modelo matara procesos ajenos (hasta el bash de una sesion)."""
    if (nombre_exe or "").lower() in tuple(n.lower() for n in (m.get("exes") or ())):
        return True
    raiz = m.get("raiz")
    return bool(raiz) and str(raiz).lower() in (cmd or "").lower()


def _procesos_de(m):
    """Los procesos vivos de ese modelo."""
    encontrados = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if es_de(m, p.info.get("name"), " ".join(p.info.get("cmdline") or "")):
                encontrados.append(p)
        except Exception:
            continue
    return encontrados


def ollama_exe():
    """Donde esta el ollama.exe, o '' si no esta instalado."""
    return _exe_de(MODELOS["ollama"])


def ollama_cargados():
    """Que modelos tiene Ollama METIDOS en la placa ahora mismo (`/api/ps`).

    Es la respuesta literal a "que modelos ocupo": el servidor puede estar prendido y
    con la placa libre, porque descarga los modelos solo despues de un rato sin uso.
    """
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/ps" % OLLAMA_PUERTO, timeout=1.5) as r:
            import json
            d = json.loads(r.read().decode("utf-8", "replace"))
        return [m.get("name") or m.get("model") or "?" for m in (d.get("models") or [])]
    except Exception:
        return []


def modelo_estado(clave):
    """Como esta ese modelo: instalado, andando, o cargando todavia.

    ⭐ `cargando` existe por Hunyuan: se come 1,68 GB de pesos ANTES de abrir el 7860,
    o sea que hay un rato largo con el proceso vivo y el puerto mudo. Sin este estado,
    la tarjeta decia "apagado" mientras cargaba y daban ganas de apretar Prender otra vez.
    """
    m = MODELOS[clave]
    exe = _exe_de(m)
    vivo = _puerto_abierto(m["puerto"])
    corriendo = bool(_procesos_de(m)) if not vivo else True
    d = {"clave": clave, "nombre": m["nombre"], "detalle": m["detalle"],
         "instalado": bool(exe), "vivo": vivo,
         "cargando": corriendo and not vivo, "puerto": m["puerto"]}
    if clave == "ollama" and vivo:
        d["cargados"] = ollama_cargados()
    return d


def modelos_estado():
    return [modelo_estado(c) for c in MODELOS]


def modelo_prender(clave):
    """Lo levanta SUELTO del panel (sobrevive a reiniciarlo) y no espera a que cargue."""
    m = MODELOS.get(clave)
    if not m:
        return {"ok": False, "error": "no se que es '%s'" % str(clave)[:20]}
    exe = _exe_de(m)
    if not exe:
        return {"ok": False, "error": "%s no esta instalado en esta maquina." % m["nombre"]}
    if _puerto_abierto(m["puerto"]) or _procesos_de(m):
        return {"ok": True, "ya": True}
    cmd = [exe] + [x for x in m["cmd"][1:]]
    entorno = dict(os.environ)
    entorno.update(m.get("env") or {})
    try:
        subprocess.Popen(cmd, cwd=str(m["cwd"]) if m.get("cwd") else None, env=entorno,
                         creationflags=SUELTO, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}
    _CACHE["t"] = 0.0
    if m.get("tarda"):
        # No se espera: cargar los pesos son minutos. La tarjeta lo muestra "cargando"
        # y se pone en verde sola cuando el puerto contesta.
        return {"ok": True, "cargando": True}
    for _ in range(20):
        time.sleep(0.25)
        if _puerto_abierto(m["puerto"]):
            return {"ok": True}
    return {"ok": True, "cargando": True}


def modelo_apagar(clave):
    """Cierra todo lo de ese modelo: el servidor y lo que tenga cargado en la placa."""
    m = MODELOS.get(clave)
    if not m:
        return {"ok": False, "error": "no se que es '%s'" % str(clave)[:20]}
    procesos = _procesos_de(m)
    for p in procesos:
        try:
            for h in p.children(recursive=True):
                try:
                    h.terminate()
                except Exception:
                    pass
            p.terminate()
        except Exception:
            continue
    time.sleep(1.0)
    for p in _procesos_de(m):
        try:
            p.kill()
        except Exception:
            continue
    _CACHE["t"] = 0.0
    return {"ok": True, "matados": len(procesos)}


# --- Apagar algo que esta ocupando la placa -----------------------------------------

def apagar_pid(pid):
    """Cierra un proceso, PERO solo si de verdad esta usando la placa.

    ⚠ La guarda no es decorativa: este endpoint recibe un numero del navegador. Sin
    ella, `/placa/apagar/4` seria un "mata cualquier proceso de Windows" abierto en el
    panel. Solo se puede apagar lo que la propia lista esta mostrando.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return {"ok": False, "error": "pid invalido"}
    if pid not in _pids_computo():
        return {"ok": False, "error": "Ese proceso ya no esta usando la placa."}
    try:
        p = psutil.Process(pid)
        nombre = _bautizar(p)[0]
        for h in p.children(recursive=True):
            try:
                h.terminate()
            except Exception:
                pass
        p.terminate()
        try:
            p.wait(timeout=6)
        except Exception:
            p.kill()
        _CACHE["t"] = 0.0            # la proxima foto tiene que ser nueva
        return {"ok": True, "nombre": nombre}
    except psutil.AccessDenied:
        return {"ok": False, "error": "Windows no me deja cerrar ese (es de otro dueño)."}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# --- La foto entera, que es lo que mira la pantalla ----------------------------------

def estado(fresco=False):
    """Todo junto y cacheado: memoria, quien la ocupa y como esta Ollama."""
    with _CANDADO:
        if not fresco and _CACHE["d"] and time.time() - _CACHE["t"] < FRESCO_SEG:
            return _CACHE["d"]
    modelos = modelos_estado()
    if not hay_placa():
        d = {"ok": False, "error": "No encontre nvidia-smi: sin placa NVIDIA a la vista.",
             "modelos": modelos}
    else:
        # ⚠ Sin este filtro, un modelo de la lista que esta andando salia DOS veces: una
        # como fila fija (con su boton Apagar) y otra como hallazgo del barrido de la
        # placa. Se queda la fila fija, que es la que sabe prenderlo de vuelta.
        foto = _pmon()
        sueltos = [p for p in procesos(foto["computo"])
                   if not any(es_de(MODELOS[c], p.get("exe"), p.get("cmd"))
                              for c in MODELOS)]
        d = {"ok": True, **memoria(), "procesos": sueltos, "modelos": modelos,
             "escritorio": escritorio(foto["graficos"])}
    with _CANDADO:
        _CACHE["t"], _CACHE["d"] = time.time(), d
    return d
