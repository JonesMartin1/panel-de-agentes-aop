"""Avisos: el puente entre el panel y los Recordatorios del iPhone.

## Por que existe esto y no una conexion directa

Apple no deja entrar a los Recordatorios desde afuera. Se probaron los tres caminos
y los tres estan cerrados (investigado el 2026-08-17, esta escrito en INTERFAZ.md):
CalDAV de iCloud dejo de exponer los recordatorios "actualizados" a partir de iOS 13,
la app Recordatorios dejo de aceptar cuentas CalDAV de terceros en la misma version,
y los puentes que existen (TaskBridge y compania) son solo para Mac.

O sea que el unico camino oficial pasa por el propio telefono. Lo hace un **Atajo**
(la app Atajos de iOS) que corre cada tanto y en UNA sola corrida hace las dos mitades:

    iPhone  →  panel : te manda todo lo que tenes pendiente
    panel   →  iPhone: se lleva lo que anotaste desde la compu

## El protocolo, a proposito, es texto pelado

Nada de JSON: el Atajo se arma A DEDO en la pantalla del telefono, y cada campo que
haya que llenar ahi es un toque mas y una cosa mas que se puede escribir mal. Con
texto plano el Atajo son 7 acciones.

    Lo que sube el telefono, una linea por recordatorio:
        nombre|cuando vence|en que lista

    Lo que contesta el panel, una linea por recordatorio a crear:
        nombre

⚠ El nombre puede tener "|" adentro, asi que al partir la linea se cortan los DOS
ultimos separadores y no el primero (`rsplit`). La fecha se guarda **tal como la
mando el telefono** y solo se INTENTA entender: si el formato no es el esperado se
muestra igual el texto crudo, en vez de perder el dato o romperse.

## Como sabe que un recordatorio ya llego al telefono

No hay acuse de recibo: el Atajo puede morirse justo despues de que el panel le
entrego la lista (se corta el wifi, lo cerraste). Por eso lo que sale del panel no
se borra al entregarse — se borra cuando **vuelve en el espejo** del telefono, que
es la unica prueba de que existe alla. Si despues de `ENTREGAS_MAX` intentos no
volvio nunca, se da por entregado igual y se saca: pasa cuando lo creaste y lo
tildaste enseguida (el espejo solo trae los pendientes), y sin este tope se lo
estaria mandando al telefono para siempre.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from app.rutas import AVISOS

# Cuantas veces se le ofrece un recordatorio al telefono antes de darlo por entregado.
ENTREGAS_MAX = 3
# Cuantos recordatorios del telefono se guardan (el espejo se reemplaza entero en
# cada sincronizacion; el tope es para que un accidente no deje un archivo enorme).
ESPEJO_MAX = 500

# ⚠ Es una FUNCION y no un diccionario suelto a proposito. Siendo un diccionario de
# modulo, `dict(_VACIO)` copia el nivel de arriba pero las listas de adentro siguen
# siendo LAS MISMAS: con el archivo todavia sin crear, lo que anotabas se guardaba en
# esa lista compartida y reaparecia mas tarde solo. Lo cazo `pruebas/probar_avisos.py`.
def _vacio() -> dict:
    return {"espejo": [], "salientes": [], "ultima_sync": None, "corridas": 0}


# --------------------------------------------------------------- el archivo

def _leer() -> dict:
    """Lo que hay guardado. Si el archivo no existe o quedo roto, arranca de cero."""
    try:
        with open(AVISOS, encoding="utf-8") as f:
            datos = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _vacio()
    if not isinstance(datos, dict):              # el archivo quedo con cualquier cosa
        return _vacio()
    for clave, valor in _vacio().items():        # tolera un archivo de una version vieja
        datos.setdefault(clave, valor)
    return datos


def _guardar(datos: dict) -> None:
    tmp = AVISOS.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    tmp.replace(AVISOS)                          # asi nunca queda un json a medio escribir


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------- fechas

def _entender_fecha(crudo: str) -> str | None:
    """Intenta leer la fecha que mando el telefono. Devuelve ISO, o None si no entiende.

    El Atajo la manda en ISO 8601 si se configuro asi, pero si Martin toco algo
    puede llegar en formato argentino (17/8/2026 21:00) o en ingles. Se prueban
    varios y si ninguno entra **no pasa nada**: el texto crudo se muestra igual.
    """
    crudo = (crudo or "").strip()
    if not crudo:
        return None
    try:                                          # ISO 8601, lo esperado
        return datetime.fromisoformat(crudo.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    for formato in ("%d/%m/%Y %H:%M", "%d/%m/%Y, %H:%M", "%d/%m/%Y",
                    "%d/%m/%y %H:%M", "%d/%m/%y", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(crudo, formato).isoformat()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------- el espejo

def _parsear(texto: str) -> list[dict]:
    """El texto que sube el telefono -> la lista de recordatorios."""
    recordatorios = []
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        # rsplit y no split: el NOMBRE es lo que puede tener "|" adentro.
        partes = linea.rsplit("|", 2)
        nombre = partes[0].strip()
        if not nombre:
            continue
        vence = partes[1].strip() if len(partes) > 1 else ""
        lista = partes[2].strip() if len(partes) > 2 else ""
        recordatorios.append({
            "nombre": nombre,
            "vence": vence or None,               # el texto tal cual lo mando el telefono
            "vence_iso": _entender_fecha(vence),  # el mismo, entendido (o None)
            "lista": lista or None,
        })
        if len(recordatorios) >= ESPEJO_MAX:
            break
    return recordatorios


def sincronizar(texto: str) -> str:
    """La corrida del Atajo: recibe lo que hay en el iPhone, contesta lo que falta crear.

    Devuelve el cuerpo de la respuesta: un nombre por linea, o vacio si no hay nada
    que mandar (el Atajo en ese caso no crea nada y no molesta).
    """
    datos = _leer()
    datos["espejo"] = _parsear(texto)
    datos["ultima_sync"] = _ahora()
    datos["corridas"] = int(datos.get("corridas") or 0) + 1

    en_el_telefono = {r["nombre"] for r in datos["espejo"]}

    quedan, van = [], []
    for s in datos.get("salientes", []):
        if s.get("nombre") in en_el_telefono:
            continue                              # ✓ llego: se saca de la cola
        if int(s.get("entregas") or 0) >= ENTREGAS_MAX:
            continue                              # se lo dio por entregado (ver el docstring)
        s["entregas"] = int(s.get("entregas") or 0) + 1
        s["ultima_entrega"] = datos["ultima_sync"]
        quedan.append(s)
        van.append(s["nombre"])

    datos["salientes"] = quedan
    _guardar(datos)
    return "\n".join(van)


# --------------------------------------------------------------- lo que sale del panel

def crear(nombre: str) -> dict | None:
    """Anota algo desde el panel para que aparezca en el iPhone. Devuelve el saliente."""
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    # ⚠ El "|" es el separador del protocolo: si el nombre lo trae, la linea que suba
    # el telefono despues se partiria mal y el recordatorio nunca se daria por llegado.
    nombre = nombre.replace("|", "/").replace("\n", " ")[:200]
    datos = _leer()
    saliente = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "creado": _ahora(),
        "entregas": 0,
        "ultima_entrega": None,
    }
    datos.setdefault("salientes", []).append(saliente)
    _guardar(datos)
    return saliente


def quitar(ident: str) -> bool:
    """Saca uno de la cola antes de que se vaya al telefono (o si ya no lo querés)."""
    datos = _leer()
    antes = len(datos.get("salientes", []))
    datos["salientes"] = [s for s in datos.get("salientes", []) if s.get("id") != ident]
    if len(datos["salientes"]) == antes:
        return False
    _guardar(datos)
    return True


# --------------------------------------------------------------- para la pantalla

def estado() -> dict:
    """Todo lo que necesita dibujar la pestaña Avisos, en un solo pedido."""
    datos = _leer()
    ultima = datos.get("ultima_sync")
    hace_min = None
    if ultima:
        try:
            hace_min = int((datetime.now() - datetime.fromisoformat(ultima)).total_seconds() // 60)
        except ValueError:
            hace_min = None

    # El espejo se ordena por fecha: primero lo que vence (y lo mas cercano arriba),
    # despues lo que no tiene fecha, respetando el orden en que vino el telefono.
    def orden(r):
        return (0, r["vence_iso"]) if r.get("vence_iso") else (1, "")

    return {
        "espejo": sorted(datos.get("espejo", []), key=orden),
        "salientes": datos.get("salientes", []),
        "ultima_sync": ultima,
        "hace_min": hace_min,
        "corridas": int(datos.get("corridas") or 0),
        # El puente esta "dormido" si hace mas de 12 h que el telefono no aparece.
        # No es un error (podes haber estado sin señal): es un dato para la pantalla.
        "dormido": hace_min is not None and hace_min > 12 * 60,
        "nunca": ultima is None,
    }


def vencidos_hoy() -> list[dict]:
    """Los que vencen dentro de las proximas 24 h. Para que Laura los pueda decir."""
    limite = datetime.now() + timedelta(hours=24)
    salida = []
    for r in _leer().get("espejo", []):
        if not r.get("vence_iso"):
            continue
        try:
            if datetime.fromisoformat(r["vence_iso"]) <= limite:
                salida.append(r)
        except ValueError:
            continue
    return salida
