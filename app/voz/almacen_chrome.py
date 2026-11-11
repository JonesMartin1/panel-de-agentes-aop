"""Leer UNA llave del almacen local de una extension de Chrome, sin librerias.

⭐⭐ Por que existe (2026-11-10). El panel averigua cual de los navegadores conectados es
el de cada proyecto leyendo del disco el `bridgeDeviceId` que la extension de Claude guarda
adentro del perfil. Hasta hoy lo buscaba con una expresion regular sobre los bytes crudos,
y eso andaba SOLO mientras el dato estuviera en un archivo sin comprimir.

El almacen es una base LevelDB, y LevelDB comprime sus tablas (`.ldb`) con Snappy. Snappy
reemplaza lo repetido por una referencia hacia atras: como al lado vive otra llave que
empieza igual (`bridgeDefaultDisplayName`), el texto `bridgeDeviceId` deja de estar
escrito entero y la expresion regular no lo encuentra NUNCA. Medido ese dia: de los
cuatro perfiles de Martin fallaban dos — el Chrome de base, que heredan casi todas las
carpetas, y el del trabajo, que usan trece. La sesion arrancaba con "no sabemos cual
es tu navegador" y terminaba preguntandoselo a el.

Aca se lee el formato de verdad: las tablas (descomprimiendo solo el bloque donde puede
estar la llave) y el registro de escritura (`.log`), y gana el valor con el numero de
secuencia mas alto, que es exactamente lo que haria LevelDB. Un borrado tambien cuenta:
si lo ultimo que paso con la llave fue que la borraron, la respuesta es "no esta".

⚠ Solo LECTURA y sin tomar el candado de LevelDB: Chrome tiene la base abierta. Por eso
tampoco se usa una libreria (todas quieren abrirla como dueñas).
⚠ Ante cualquier cosa rara (archivo cortado, bloque ilegible) ese archivo se saltea: una
respuesta vacia hace que la sesion avise, y eso es mejor que inventar un navegador.
"""
import struct
from pathlib import Path

_MAGIA_TABLA = bytes.fromhex("57fb808b247547db")
_BLOQUE_LOG = 32768
# Resultado por tabla ya leida. Una `.ldb` no cambia nunca despues de escrita, asi que
# releerla es tirar tiempo: lo unico que se vuelve a leer es el `.log`, que si crece.
_CACHE_TABLAS = {}


def _varint(b, i):
    """(numero, posicion siguiente) de un entero de largo variable."""
    n = corr = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << corr
        if c < 0x80:
            return n, i
        corr += 7


def descomprimir_snappy(b):
    """Un bloque Snappy "crudo" (el que usa LevelDB), descomprimido."""
    largo, i = _varint(b, 0)
    sal = bytearray()
    n = len(b)
    while i < n:
        t = b[i]
        i += 1
        tipo = t & 3
        if tipo == 0:                                   # texto literal
            cuanto = t >> 2
            if cuanto >= 60:
                extra = cuanto - 59
                cuanto = int.from_bytes(b[i:i + extra], "little")
                i += extra
            cuanto += 1
            sal += b[i:i + cuanto]
            i += cuanto
            continue
        if tipo == 1:                                   # copia corta
            cuanto = 4 + ((t >> 2) & 7)
            atras = ((t >> 5) << 8) | b[i]
            i += 1
        elif tipo == 2:
            cuanto = (t >> 2) + 1
            atras = b[i] | (b[i + 1] << 8)
            i += 2
        else:
            cuanto = (t >> 2) + 1
            atras = int.from_bytes(b[i:i + 4], "little")
            i += 4
        if atras <= 0 or atras > len(sal):
            raise ValueError("snappy: referencia fuera de rango")
        desde = len(sal) - atras
        if atras >= cuanto:
            sal += sal[desde:desde + cuanto]
        else:                                           # se pisa a si misma: de a uno
            for k in range(cuanto):
                sal.append(sal[desde + k])
    if len(sal) != largo:
        raise ValueError("snappy: largo distinto al anunciado")
    return bytes(sal)


def _bloque(datos, desde, largo):
    """El contenido de un bloque de una tabla, ya descomprimido si hacia falta."""
    crudo = datos[desde:desde + largo]
    tipo = datos[desde + largo]
    if tipo == 0:
        return crudo
    if tipo == 1:
        return descomprimir_snappy(crudo)
    raise ValueError("bloque con una compresion que no conozco")


def _entradas(bloque):
    """Las (llave, valor) de un bloque, deshaciendo el ahorro de prefijos."""
    reinicios = struct.unpack_from("<I", bloque, len(bloque) - 4)[0]
    fin = len(bloque) - 4 * (reinicios + 1)
    i = 0
    llave = b""
    while i < fin:
        comun, i = _varint(bloque, i)
        propio, i = _varint(bloque, i)
        largo_v, i = _varint(bloque, i)
        llave = llave[:comun] + bloque[i:i + propio]
        i += propio
        yield llave, bloque[i:i + largo_v]
        i += largo_v


def _de_tabla(datos, buscada):
    """(secuencia, valor o None si fue borrada) mas nuevo de esa llave en una `.ldb`."""
    if len(datos) < 48 or datos[-8:] != _MAGIA_TABLA:
        raise ValueError("no es una tabla de LevelDB")
    pie = datos[-48:]
    _, i = _varint(pie, 0)
    _, i = _varint(pie, i)
    d_ind, i = _varint(pie, i)
    l_ind, i = _varint(pie, i)
    mejor = None
    # El indice trae, por bloque, una llave mayor o igual a la ultima de ese bloque. La
    # buscada solo puede estar en el primer bloque cuya marca no sea menor que ella (y en
    # el siguiente, si varias versiones de la llave quedaron partidas entre dos).
    faltan = 2
    for marca, puntero in _entradas(_bloque(datos, d_ind, l_ind)):
        if marca[:-8] < buscada:
            continue
        d, j = _varint(puntero, 0)
        l, _ = _varint(puntero, j)
        for llave, valor in _entradas(_bloque(datos, d, l)):
            if llave[:-8] != buscada:
                continue
            rotulo = int.from_bytes(llave[-8:], "little")
            sec, tipo = rotulo >> 8, rotulo & 0xFF
            if mejor is None or sec > mejor[0]:
                mejor = (sec, valor if tipo == 1 else None)
        faltan -= 1
        if not faltan:
            break
    return mejor


def _de_registro(datos, buscada):
    """Lo mismo, del `.log`: lo escrito hace poco y todavia no pasado a una tabla."""
    mejor = None
    armando = None
    i = 0
    n = len(datos)
    while i + 7 <= n:
        resto = _BLOQUE_LOG - (i % _BLOQUE_LOG)
        if resto < 7:                       # la cola de un bloque no lleva nada
            i += resto
            continue
        largo, tipo = struct.unpack_from("<HB", datos, i + 4)
        if tipo == 0 and largo == 0:        # espacio reservado y sin usar
            i += resto
            continue
        cuerpo = datos[i + 7:i + 7 + largo]
        i += 7 + largo
        if tipo == 1:
            lote, armando = cuerpo, None
        elif tipo == 2:
            armando = bytearray(cuerpo)
            continue
        elif tipo == 3:
            if armando is not None:
                armando += cuerpo
            continue
        elif tipo == 4:
            if armando is None:
                continue
            lote, armando = bytes(armando + cuerpo), None
        else:
            continue
        try:
            sec = int.from_bytes(lote[:8], "little")
            cuantos = struct.unpack_from("<I", lote, 8)[0]
            j = 12
            for k in range(cuantos):
                marca = lote[j]
                j += 1
                lk, j = _varint(lote, j)
                llave = lote[j:j + lk]
                j += lk
                valor = None
                if marca == 1:
                    lv, j = _varint(lote, j)
                    valor = lote[j:j + lv]
                    j += lv
                if llave == buscada and (mejor is None or sec + k >= mejor[0]):
                    mejor = (sec + k, valor)
        except (IndexError, struct.error):
            continue                        # un lote cortado por la mitad: se saltea
    return mejor


def leer_llave(carpeta, llave):
    """El valor vigente de `llave` en esa base LevelDB, en bytes. None si no esta."""
    buscada = llave.encode() if isinstance(llave, str) else llave
    mejor = None
    try:
        archivos = [f for f in Path(carpeta).iterdir()
                    if f.suffix.lower() in (".ldb", ".log")]
    except OSError:
        return None
    for f in archivos:
        try:
            if f.suffix.lower() == ".log":
                hallado = _de_registro(f.read_bytes(), buscada)
            else:
                e = f.stat()
                firma = (str(f), e.st_size, e.st_mtime, buscada)
                if firma not in _CACHE_TABLAS:
                    if len(_CACHE_TABLAS) > 400:
                        _CACHE_TABLAS.clear()
                    _CACHE_TABLAS[firma] = _de_tabla(f.read_bytes(), buscada)
                hallado = _CACHE_TABLAS[firma]
        except Exception:
            continue
        if hallado and (mejor is None or hallado[0] > mejor[0]):
            mejor = hallado
    return mejor[1] if mejor else None
