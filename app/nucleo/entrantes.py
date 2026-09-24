"""Los audios y videos que ENTRAN por WhatsApp y Telegram, guardados para el Estudio.

Hasta el 2026-08-17 el audio original se tiraba. Los dos caminos de ingesta lo
bajaban a un archivo temporal, lo transcribian y lo borraban en su `finally`; en
`resultados/` quedaba la transcripcion y el analisis, nunca el sonido. Para poder
PEGAR audios uno atras del otro desde el panel hace falta el audio, asi que ahora
se guarda una copia aca con una ficha al lado que dice de donde vino y que dice.

⭐ Se guarda en UN solo lugar — `procesar.procesar_a_texto()` —, que es por donde
pasan TODOS los caminos: el bot de Telegram, el webhook de WhatsApp y la pagina
`/subir` de audios largos. Poner el guardado en cada camino habria sido copiarlo
tres veces y olvidarse del cuarto.

⚠ Guardar no puede voltear una transcripcion nunca: quien llama envuelve esto en
un `try`. Si el disco esta lleno o el archivo se movio, se pierde la copia y el
usuario igual recibe su texto.

Cada audio son dos archivos hermanos en `resultados/estudio/entrantes/`:

    2026-08-17_2312_9f3a1c.ogg       el audio tal cual llego
    2026-08-17_2312_9f3a1c.json      canal, quien lo mando, cuando y que dice

Van en `resultados/` a proposito: son archivos de terceros y esa carpeta ya esta
fuera de git. Se borran solos a los `RETENCION_DIAS` dias.
"""

import array
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.rutas import (ESTUDIO_ENTRANTES, ESTUDIO_PROYECTOS, ESTUDIO_MINIATURAS, ESTUDIO_COLA,
                       ESTUDIO_ANALISIS_ARMADOS)

# Cuanto se guarda un audio recibido antes de borrarse solo. Son notas de voz
# (unos cientos de KB), pero sin un tope la carpeta crece para siempre.
RETENCION_DIAS = 30

EXT_AUDIO = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".flac", ".oga"}
EXT_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp"}
EXT_MEDIA = EXT_AUDIO | EXT_VIDEO

CREATE_NO_WINDOW = 0x08000000       # que ffprobe no abra una consola en Windows


# La cola no vive dentro del panel: WhatsApp, Telegram y el panel son procesos
# distintos. Una ficha por trabajo permite que todos la lean sin una base de datos,
# y la escritura temporal + replace evita que la pantalla vea medio JSON.
def _cola_ruta(identificador):
    return ESTUDIO_COLA / (Path(str(identificador)).name + ".json")


def _cola_leer(identificador):
    try:
        return json.loads(_cola_ruta(identificador).read_text(encoding="utf-8"))
    except Exception:
        return None


def _cola_guardar(dato):
    ident = str(dato.get("id") or "")
    if not ident:
        return False
    ESTUDIO_COLA.mkdir(parents=True, exist_ok=True)
    destino = _cola_ruta(ident)
    temporal = destino.with_suffix(".json.tmp")
    try:
        temporal.write_text(json.dumps(dato, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(destino)
        return True
    except Exception:
        try:
            temporal.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def cola_abrir(ruta, origen="", de=""):
    """Anota un audio/video que acaba de entrar para que el Estudio lo muestre vivo."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext not in EXT_MEDIA:
        return ""
    ahora = time.time()
    ident = "cola_" + uuid.uuid4().hex
    _cola_guardar({
        "id": ident,
        "archivo": "",
        "nombre": ruta.name,
        "tipo": "video" if ext in EXT_VIDEO else "audio",
        "origen": (origen or "").strip() or "subida",
        "de": (de or "").strip() or ruta.stem or "archivo recibido",
        "estado": "en_curso",
        "pct": 1,
        "paso": "Recibido, esperando su turno…",
        "cuando": ahora,
        "actualizado": ahora,
        "error": "",
    })
    return ident


def cola_actualizar(identificador, pct=None, paso=None, archivo=None):
    """Actualiza una sola ficha de la cola; nunca interfiere con la transcripción."""
    d = _cola_leer(identificador)
    if not d:
        return False
    if pct is not None:
        try:
            d["pct"] = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            pass
    if paso is not None:
        d["paso"] = str(paso)[:160]
    if archivo is not None:
        d["archivo"] = Path(str(archivo)).name
    d["actualizado"] = time.time()
    return _cola_guardar(d)


def cola_terminar(identificador, archivo="", paso="Listo para editar"):
    d = _cola_leer(identificador)
    if not d:
        return False
    d.update({"estado": "listo", "pct": 100, "paso": str(paso)[:160], "error": "",
              "actualizado": time.time()})
    if archivo:
        d["archivo"] = Path(str(archivo)).name
    return _cola_guardar(d)


def cola_fallar(identificador, error):
    d = _cola_leer(identificador)
    if not d:
        return False
    d.update({"estado": "error", "paso": "No se pudo terminar", "error": str(error)[:300],
              "actualizado": time.time()})
    return _cola_guardar(d)


def cola_de_archivo(archivo):
    """Devuelve la ficha más reciente que corresponde a un original del Estudio."""
    buscado = Path(str(archivo)).name
    candidatas = [d for d in cola_listar(limite=80) if d.get("archivo") == buscado]
    return max(candidatas, key=lambda d: d.get("actualizado") or 0, default=None)


def cola_listar(limite=16):
    """Trabajos vivos y los recién terminados: la pantalla los consulta cada poco."""
    if not ESTUDIO_COLA.is_dir():
        return []
    ahora, items = time.time(), []
    for ficha in ESTUDIO_COLA.glob("cola_*.json"):
        try:
            d = json.loads(ficha.read_text(encoding="utf-8"))
        except Exception:
            continue
        estado = d.get("estado") or "en_curso"
        edad = ahora - float(d.get("actualizado") or d.get("cuando") or ahora)
        # La cola es una ventana de actividad, no otro historial eterno. Los listos
        # quedan unos minutos para confirmar que llegaron; los errores duran más.
        vence = 300 if estado == "listo" else 86400 if estado == "error" else None
        if vence is not None and edad > vence:
            try:
                ficha.unlink(missing_ok=True)
            except Exception:
                pass
            continue
        items.append(d)
    items.sort(key=lambda d: (d.get("estado") != "en_curso", -(d.get("actualizado") or 0)))
    return items[:max(1, int(limite or 16))]


def duracion(ruta) -> float:
    """Cuanto dura un audio, en segundos, segun ffprobe. 0.0 si no se pudo leer."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(ruta)],
            capture_output=True, text=True, timeout=30,
            creationflags=CREATE_NO_WINDOW)
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return 0.0


def guardar(ruta, origen="", de="", texto="", segmentos=None, analisis=None) -> str:
    """Copia el audio recibido a la carpeta del Estudio y deja su ficha al lado.

    `origen` es el canal ("whatsapp", "telegram", "subida"), `de` quien lo mando
    y `texto` la transcripcion — que es lo que despues permite ELEGIR el audio
    leyendo lo que dice, en vez de adivinar por un nombre tipo `evo_968e8c50`.
    Si ya se hizo, `analisis` queda en la misma ficha: así el Estudio nunca ve un
    audio nuevo entre el guardado de su copia y el guardado de Gemini.

    ⭐ `segmentos` es la transcripcion CON MARCAS DE TIEMPO ([{inicio, fin, texto}]),
    tal como la devuelve Whisper. Es lo que deja cortar el audio leyendo en vez de
    midiendo: se toca una frase y se recorta ahi. Whisper ya las calcula en cada
    transcripcion, asi que guardarlas no cuesta nada; tirarlas era el desperdicio.

    Devuelve el nombre del archivo guardado, o "" si no era audio ni video.
    """
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext not in EXT_MEDIA or not ruta.exists():
        return ""

    ESTUDIO_ENTRANTES.mkdir(parents=True, exist_ok=True)
    ahora = time.time()
    nombre = "%s_%s%s" % (datetime.fromtimestamp(ahora).strftime("%Y-%m-%d_%H%M"),
                          uuid.uuid4().hex[:6], ext)
    destino = ESTUDIO_ENTRANTES / nombre
    destino.write_bytes(ruta.read_bytes())

    ficha = {
        "archivo": nombre,
        "tipo": "video" if ext in EXT_VIDEO else "audio",
        "origen": (origen or "").strip() or "subida",
        "de": (de or "").strip() or "desconocido",
        "cuando": round(ahora),
        "dur": duracion(destino),
        "texto": (texto or "").strip(),
        # A que "bandeja" (proyecto) pertenece. Vacio = sin clasificar: TODO audio que
        # llega cae ahi y Martin lo manda a su proyecto desde la pantalla. Decidido asi
        # el 2026-08-17: "poder mandar todos los audios y poder elegir a que bandeja van".
        "proyecto": "",
        # Solo los tres campos que hacen falta para cortar: Whisper devuelve varios
        # mas por segmento y la ficha no es el lugar para guardar todo eso.
        "segmentos": [{"inicio": round(float(s.get("inicio", 0)), 2),
                       "fin": round(float(s.get("fin", 0)), 2),
                       "texto": (s.get("texto") or "").strip()}
                      for s in (segmentos or []) if isinstance(s, dict)],
    }
    if analisis is not None:
        ficha["analisis"] = analisis
    destino.with_suffix(".json").write_text(
        json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")

    limpiar()
    return nombre


def listar(limite=200):
    """Los audios recibidos, del mas nuevo al mas viejo.

    Un audio sin su `.json` al lado igual se lista (con lo que se pueda deducir
    del nombre): perder la ficha no tiene que hacer desaparecer el sonido.
    """
    if not ESTUDIO_ENTRANTES.is_dir():
        return []
    fichas = []
    for f in ESTUDIO_ENTRANTES.iterdir():
        if not f.is_file() or f.suffix.lower() not in EXT_MEDIA:
            continue
        # Mientras una subida grande todavía se está copiando, este temporal puede
        # pesar gigas pero todavía NO es una fuente del Estudio. Listarlo hacía que la
        # pantalla intentara transcribir un video incompleto (y se veía duplicado).
        if f.name.startswith("_subiendo_"):
            continue
        d = {"archivo": f.name,
             "tipo": "video" if f.suffix.lower() in EXT_VIDEO else "audio",
             "origen": "subida", "de": "desconocido",
             "cuando": round(f.stat().st_mtime), "dur": 0.0, "texto": "", "proyecto": ""}
        try:
            d.update(json.loads(f.with_suffix(".json").read_text(encoding="utf-8")))
            d["archivo"] = f.name          # la ficha no manda sobre el disco
        except Exception:
            pass
        # ⚠ Los segmentos NO viajan en la lista: un audio de 13 minutos tiene ~200 y
        # esto se pide cada 20 segundos desde cada pestaña abierta. Se piden de a uno
        # con `segmentos_de()` recien cuando hace falta cortar ese audio.
        d["segs"] = len(d.pop("segmentos", None) or [])
        # El analisis tampoco viaja en la lista (es un dict entero por audio): solo si
        # lo tiene. Se pide de a uno con /estudio/analisis cuando lo vas a mirar.
        d["tiene_analisis"] = bool(d.pop("analisis", None))
        fichas.append(d)
    fichas.sort(key=lambda d: d.get("cuando") or 0, reverse=True)
    return fichas[:limite]


def poner_analisis(nombre, analisis) -> bool:
    """Le pega el analisis de Gemini a la ficha de un audio YA guardado.

    Va en dos pasos y no adentro de `guardar()` a proposito: primero se asegura el
    audio (que es lo que no se puede recuperar) y despues, si el analisis sale, se
    agrega. Si Gemini falla o no hay cupo, el audio y su transcripcion ya estan.
    """
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name
    ficha = f.with_suffix(".json")
    if f.parent != ESTUDIO_ENTRANTES or not ficha.exists():
        return False
    try:
        d = json.loads(ficha.read_text(encoding="utf-8"))
    except Exception:
        return False
    d["analisis"] = analisis
    ficha.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def analisis_de(nombre):
    """El analisis guardado de un audio, o None si no tiene."""
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name
    if f.parent != ESTUDIO_ENTRANTES or not f.exists():
        return None
    try:
        return json.loads(f.with_suffix(".json").read_text(encoding="utf-8")).get("analisis")
    except Exception:
        return None


def _pistas_analisis(pistas):
    """La identidad estable de un armado: orden, archivo y el tramo que entra."""
    limpias = []
    for p in pistas or []:
        if not isinstance(p, dict):
            continue
        archivo = Path(str(p.get("archivo") or "")).name
        if not archivo:
            continue
        try:
            ini = round(float(p.get("ini") or 0), 2)
            fin = round(float(p.get("fin") or 0), 2)
        except (TypeError, ValueError):
            continue
        limpias.append({"archivo": archivo, "ini": ini, "fin": fin})
    return limpias


def _clave_analisis_armado(pistas, perfil):
    base = {"pistas": _pistas_analisis(pistas), "perfil": str(perfil or "generico")}
    crudo = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:24], base


def _analisis_armados_leer():
    try:
        datos = json.loads(ESTUDIO_ANALISIS_ARMADOS.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def guardar_analisis_armado(pistas, perfil, texto, dicho):
    """Guarda el análisis que Martín pidió para ESTA fila, sin pisar los originales."""
    clave, base = _clave_analisis_armado(pistas, perfil)
    if not base["pistas"] or not str(texto or "").strip():
        return ""
    datos = _analisis_armados_leer()
    items = datos.get("items") if isinstance(datos.get("items"), dict) else {}
    items[clave] = {**base, "texto": str(texto).strip(), "dicho": str(dicho or "").strip(),
                    "cuando": time.time()}
    # No es un historial infinito: se conservan los últimos 80 armados distintos.
    recientes = sorted(items.items(), key=lambda par: par[1].get("cuando") or 0, reverse=True)[:80]
    datos = {"items": dict(recientes)}
    ESTUDIO_ANALISIS_ARMADOS.parent.mkdir(parents=True, exist_ok=True)
    temporal = ESTUDIO_ANALISIS_ARMADOS.with_suffix(".json.tmp")
    try:
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(ESTUDIO_ANALISIS_ARMADOS)
        return clave
    except Exception:
        try:
            temporal.unlink(missing_ok=True)
        except Exception:
            pass
        return ""


def analisis_armado(pistas, perfil):
    """El análisis ya hecho para la misma fila y el mismo perfil, o None."""
    clave, _ = _clave_analisis_armado(pistas, perfil)
    item = (_analisis_armados_leer().get("items") or {}).get(clave)
    return item if isinstance(item, dict) else None


def texto_recortado(pistas):
    """El texto que va a decir un audio ARMADO, sin volver a transcribir nada.

    ⭐ Esta es la gracia: cada pista es un pedazo de un audio que YA tiene su
    transcripcion con marcas de tiempo, asi que el texto del resultado se arma
    juntando las frases que caen adentro de cada recorte. Analizar lo que armaste
    no cuesta una sola pasada de GPU.
    """
    partes = []
    for p in pistas or []:
        segs = segmentos_de(p.get("archivo"))
        try:
            ini = float(p.get("ini") or 0)
            fin = float(p.get("fin") or 0)
        except (TypeError, ValueError):
            ini, fin = 0.0, 0.0
        for s in segs:
            # Entra la frase que EMPIEZA adentro del pedazo elegido.
            if s.get("inicio", 0) >= ini - 0.01 and (fin <= 0 or s.get("inicio", 0) < fin):
                t = (s.get("texto") or "").strip()
                if t:
                    partes.append(t)
    return " ".join(partes).strip()


def segmentos_de(nombre):
    """La transcripcion con marcas de tiempo de UN audio: [{inicio, fin, texto}].

    Devuelve [] si el audio no tiene ficha o si se guardo antes de que existiera
    esto (las fichas viejas no la tienen y no pasa nada: se corta a mano).
    """
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name        # sin ../ ni rutas raras
    if f.parent != ESTUDIO_ENTRANTES or not f.exists():
        return []
    try:
        ficha = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
    except Exception:
        return []
    return _acomodar(ficha.get("segmentos") or [], ficha.get("dur") or 0)


def poner_transcripcion(nombre, texto, segmentos) -> bool:
    """Completa la ficha de un medio viejo sin duplicar ni tocar el original."""
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name
    ficha = f.with_suffix(".json")
    if f.parent != ESTUDIO_ENTRANTES or not f.exists():
        return False
    try:
        d = json.loads(ficha.read_text(encoding="utf-8")) if ficha.exists() else {}
    except Exception:
        d = {}
    d["archivo"] = f.name
    d["tipo"] = "video" if f.suffix.lower() in EXT_VIDEO else "audio"
    d["dur"] = d.get("dur") or duracion(f)
    d["texto"] = (texto or "").strip()
    d["segmentos"] = [{"inicio": round(float(s.get("inicio") or 0), 2),
                        "fin": round(float(s.get("fin") or 0), 2),
                        "texto": (s.get("texto") or "").strip()}
                       for s in (segmentos or []) if isinstance(s, dict)]
    tmp = ficha.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ficha)
    return True


def _acomodar(segmentos, dur):
    """Recorta las frases al largo real del audio.

    ⚠⚠ Whisper puede terminar la ULTIMA frase DESPUES de que el audio se acabo: cierra
    el bloque con lo que estimo, no con lo que dura el archivo. Visto el 2026-08-18 en un
    audio de 24,51 s con la ultima frase marcada hasta 26,03. Con ese `fin` de mas, en la
    pantalla esa frase no entraba nunca en el recorte: se veia tachada sin que Martin la
    sacara, y "+ poner" no la podia poner (el recorte no se estira mas alla del final).
    Se arregla ACA, en el servidor, y no solo en la pantalla: es un dato malo, y un dato
    malo no tiene que salir de casa. Ademas asi la pantalla vieja que le quedo guardada al
    navegador tambien anda, sin depender de que se acuerde de recargar.
    ⛔ Se recortan, NO se descartan: la pantalla guarda las frases sacadas por NUMERO de
    posicion, y sacar una de la lista correria todas las demas.
    """
    if not dur or dur <= 0:
        return segmentos
    acomodados = []
    for s in segmentos:
        s = dict(s)
        s["inicio"] = round(max(0.0, min(float(s.get("inicio") or 0), dur)), 2)
        s["fin"] = round(max(0.0, min(float(s.get("fin") or 0), dur)), 2)
        acomodados.append(s)
    return acomodados


# ---------------------------------------------------------------- las bandejas
# Un "proyecto" es solo un nombre. Vive en dos lados a proposito: la LISTA de nombres
# en su archivo (para poder crear uno vacio, antes de tener ningun audio) y a cual
# pertenece cada audio, en la ficha del audio. Asi mover un audio es tocar su ficha y
# no hay una tabla central que se pueda desincronizar.
def proyectos():
    """Los nombres de las bandejas, en el orden en que Martin las creo."""
    try:
        guardados = json.loads(ESTUDIO_PROYECTOS.read_text(encoding="utf-8"))
    except Exception:
        guardados = []
    nombres = [str(n).strip() for n in guardados if str(n).strip()]
    # Un audio puede tener un proyecto que ya no este en la lista (se borro la bandeja
    # con audios adentro): igual se muestra, para que no desaparezca de la vista.
    for a in listar():
        if a.get("proyecto") and a["proyecto"] not in nombres:
            nombres.append(a["proyecto"])
    return nombres


def guardar_proyectos(nombres):
    """Pisa la lista de bandejas (crear, renombrar el orden, borrar)."""
    limpios, vistos = [], set()
    for n in nombres or []:
        n = str(n).strip()[:60]
        if n and n.lower() not in vistos:
            vistos.add(n.lower())
            limpios.append(n)
    ESTUDIO_PROYECTOS.parent.mkdir(parents=True, exist_ok=True)
    ESTUDIO_PROYECTOS.write_text(json.dumps(limpios, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return limpios


def mover(nombre, proyecto) -> bool:
    """Manda un audio a una bandeja. `proyecto` vacio lo deja sin clasificar."""
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name
    ficha = f.with_suffix(".json")
    if f.parent != ESTUDIO_ENTRANTES or not f.exists():
        return False
    try:
        d = json.loads(ficha.read_text(encoding="utf-8")) if ficha.exists() else {}
    except Exception:
        d = {}
    d["archivo"] = f.name
    d["proyecto"] = str(proyecto or "").strip()[:60]
    ficha.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def picos(ruta, cuantos=340):
    """La forma de la onda, medida con ffmpeg. Devuelve `cuantos` valores de 0 a 1.

    ⭐ Esto lo hacia el NAVEGADOR con decodeAudioData, y con audios largos no daba:
    media hora de audio son ~400 MB en memoria al descomprimir, y Chrome se plantaba
    dejando una raya en vez de la onda (visto con un audio de 34:33 el 2026-08-17).
    Aca ffmpeg lo baja a 1000 muestras por segundo antes de medir: media hora son 2
    millones de numeros, un instante, y al navegador le llegan 340.

    Se guarda al lado del audio (`.picos.json`) porque no cambia nunca: el archivo no
    se toca, los recortes son numeros que viajan aparte.
    """
    ruta = Path(ruta)
    cache = ruta.with_suffix(".picos.json")
    try:
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ruta), "-ac", "1",
                            "-ar", "1000", "-f", "s16le", "-"],
                           capture_output=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        muestras = array.array("h")
        muestras.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
        if not len(muestras):
            return []
        paso = max(1, len(muestras) // cuantos)
        crudos = []
        for i in range(cuantos):
            trozo = muestras[i * paso:(i + 1) * paso]
            crudos.append(max((abs(v) for v in trozo), default=0))
        tope = max(crudos) or 1
        salida = [round(v / tope, 3) for v in crudos]
    except Exception:
        return []
    try:
        cache.write_text(json.dumps(salida), encoding="utf-8")
    except Exception:
        pass
    return salida


def borrar(nombre) -> bool:
    """Saca un audio recibido y sus caches (onda y tira de miniaturas)."""
    f = ESTUDIO_ENTRANTES / Path(str(nombre)).name       # sin ../ ni rutas raras
    if f.parent != ESTUDIO_ENTRANTES or not f.exists():
        return False
    f.unlink()
    f.with_suffix(".json").unlink(missing_ok=True)
    f.with_suffix(".picos.json").unlink(missing_ok=True)
    (ESTUDIO_MINIATURAS / (f.stem + ".jpg")).unlink(missing_ok=True)
    return True


def limpiar(dias=RETENCION_DIAS) -> int:
    """Borra lo que paso los `dias` de retencion. Devuelve cuantos se fueron."""
    if not ESTUDIO_ENTRANTES.is_dir():
        return 0
    corte = time.time() - dias * 86400
    idos = 0
    for f in list(ESTUDIO_ENTRANTES.iterdir()):
        try:
            if f.is_file() and f.suffix.lower() in EXT_MEDIA and f.stat().st_mtime < corte:
                f.unlink()
                f.with_suffix(".json").unlink(missing_ok=True)
                f.with_suffix(".picos.json").unlink(missing_ok=True)
                (ESTUDIO_MINIATURAS / (f.stem + ".jpg")).unlink(missing_ok=True)
                idos += 1
        except Exception:
            continue          # un archivo abierto por otro proceso no frena la limpieza
    return idos
