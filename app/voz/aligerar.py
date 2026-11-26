"""Que lo que viaja al celular pese poco: comprimir, y no mandar de nuevo lo que no cambio.

Nace del 2026-11-23 (Martin: *"la app del celular tambien tiene que andar super
rapidisimo"*). Medido ese dia: abrir la app bajaba 610 KB de pagina y archivos —todo sin
comprimir y todo de nuevo en cada apertura—, y despues la charla abierta volvia a viajar
entera (30 a 70 KB) cada 3 segundos aunque nadie hubiera escrito nada. En la compu eso no
se nota; por el telefono, con datos moviles, es la diferencia entre al toque y esperar.

Es una sola pieza que se pone delante del panel y hace tres cosas, SOLO en las rutas de la
lista de abajo:

  1. COMPRIME (gzip) la respuesta si el navegador lo acepta. La lista de charlas pasa de
     80 KB a 13; la pagina del celular, de 230 a 71.
  2. NO MANDA LO QUE NO CAMBIO. A cada respuesta le pone una huella (`ETag`) calculada
     sobre su contenido. El navegador la guarda y en el pedido siguiente dice cual tiene;
     si es la misma, el panel contesta "304, usa la tuya" sin cuerpo. La pantalla no se
     entera: recibe lo mismo de siempre. ⭐ Sigue siendo SIEMPRE lo ultimo — `no-cache`
     obliga a preguntar cada vez; lo unico que se ahorra es el viaje del contenido.
  3. Los archivos de la pagina pedidos CON VERSION (`/estaticos/x.js?v=123`) se guardan en
     el telefono para siempre: la version es la fecha del archivo, asi que al cambiar el
     archivo cambia la direccion y se baja el nuevo. Las direcciones con version las arma
     `versionar()` cuando se sirve la pagina.

⚠⚠ Lo que NO se toca, y por que la lista es de rutas permitidas y no "todo menos":
  · Los canales que van empujando texto (`/movil/envivo`, el de la terminal). Esta pieza
    junta la respuesta ENTERA antes de mandarla: en un canal asi, el texto en vivo llegaria
    todo junto al final.
  · La PAGINA del celular sigue con `no-store`: se comprime, pero no se guarda. iOS, con la
    app en la pantalla de inicio, mostraba la pagina vieja despues de un arreglo
    (2026-08-17) y esa regla es la que lo evita.
  · Los pedidos por pedazos (`Range`), los que no son GET y lo que no contesto 200.

Se prueba con `python -m pruebas.probar_celular_liviano --mutar`.
"""
import gzip
import hashlib
import re

# Los datos que las pantallas piden una y otra vez: huella + compresion.
DATOS = {"/movil/sesiones", "/movil/chat", "/movil/pestanas", "/movil/borradores",
         "/kpis/revision", "/movil/entorno", "/movil/despachos"}
# Las paginas: solo compresion. Sus reglas de guardado no se tocan.
PAGINAS = {"/", "/movil", "/sesiones", "/pizarra"}
# Los archivos de las paginas: huella + compresion, y guardado largo si vienen con version.
ARCHIVOS = "/estaticos/"
# ⭐ La foto del escritorio que va de fondo: pesa 2 MB y la app la bajaba DOS veces en cada
# apertura (una sin version, y otra con version apenas se enteraba de cual era). Con version
# se guarda para siempre —la version es el nombre y la fecha de la foto, asi que cuando
# Windows la cambia, cambia la direccion—; sin version, huella y "no cambio".
ARCHIVOS_SUELTOS = {"/fondo/windows"}
# Lo que vale la pena comprimir. Una foto ya viene comprimida: pasarla por gzip es gastar
# tiempo para ahorrar nada.
SE_COMPRIME = ("text/", "application/json", "application/javascript", "image/svg")

PARA_SIEMPRE = "public, max-age=31536000, immutable"
MINIMO_COMPRIMIR = 1024            # mas chico que esto no vale la vuelta
TOPE = 8 * 1024 * 1024             # mas grande que esto no se junta en memoria: pasa como viene


def _clase(ruta):
    if ruta in DATOS:
        return "datos"
    if ruta in PAGINAS:
        return "pagina"
    if ruta.startswith(ARCHIVOS) or ruta in ARCHIVOS_SUELTOS:
        return "archivo"
    return None


def huella(cuerpo):
    return '"' + hashlib.blake2b(cuerpo, digest_size=12).hexdigest() + '"'


class Aligerar:
    """Pieza ASGI pura (no `BaseHTTPMiddleware`: ese envuelve tambien los canales en vivo)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        clase = _clase(scope.get("path", "")) if scope["type"] == "http" else None
        if clase is None or scope.get("method") != "GET":
            return await self.app(scope, receive, send)
        pedido = {k.decode("latin-1").lower(): v.decode("latin-1")
                  for k, v in scope.get("headers") or []}
        if "range" in pedido:
            return await self.app(scope, receive, send)

        inicio = None              # el mensaje con el estado y las cabeceras, retenido
        trozos = []
        juntado = 0
        de_largo = False           # se rindio: lo que sigue pasa tal cual

        async def enviar(mensaje):
            nonlocal inicio, juntado, de_largo
            if de_largo:
                return await send(mensaje)
            if mensaje["type"] == "http.response.start":
                inicio = mensaje
                cab = {k.decode("latin-1").lower(): v.decode("latin-1")
                       for k, v in mensaje.get("headers") or []}
                # Nada que no sea un 200 comun, ya comprimido o un canal de eventos.
                if (mensaje["status"] != 200 or "content-encoding" in cab
                        or cab.get("content-type", "").startswith("text/event-stream")):
                    de_largo = True
                    await send(mensaje)
                return
            if mensaje["type"] != "http.response.body":
                return await send(mensaje)
            trozos.append(mensaje.get("body", b""))
            juntado += len(trozos[-1])
            if juntado > TOPE:                         # demasiado grande: se suelta lo juntado
                de_largo = True
                await send(inicio)
                await send({"type": "http.response.body", "body": b"".join(trozos),
                            "more_body": mensaje.get("more_body", False)})
                return
            if mensaje.get("more_body"):
                return
            await self._cerrar(scope, clase, pedido, inicio, b"".join(trozos), send)

        await self.app(scope, receive, enviar)

    async def _cerrar(self, scope, clase, pedido, inicio, cuerpo, send):
        cab = [(k, v) for k, v in inicio.get("headers") or []
               if k.lower() not in (b"content-length", b"etag", b"last-modified")]
        guardado = next((v.decode("latin-1") for k, v in inicio.get("headers") or []
                         if k.lower() == b"cache-control"), "")
        marca = None
        if clase != "pagina":
            marca = huella(cuerpo)
            con_version = clase == "archivo" and re.search(
                r"(^|&)v=", scope.get("query_string", b"").decode("latin-1"))
            if con_version:
                nuevo = PARA_SIEMPRE
            elif clase == "archivo" and "max-age" in guardado:
                nuevo = guardado               # ya tenia su propia regla de guardado: se respeta
            else:
                nuevo = "no-cache"             # se guarda, pero se pregunta SIEMPRE antes de usar
            cab = [(k, v) for k, v in cab if k.lower() != b"cache-control"]
            cab += [(b"cache-control", nuevo.encode()), (b"etag", marca.encode())]
            if marca in [x.strip().removeprefix("W/") for x in
                         pedido.get("if-none-match", "").split(",")]:
                sin_tipo = [(k, v) for k, v in cab if k.lower() != b"content-type"]
                await send({"type": "http.response.start", "status": 304, "headers": sin_tipo})
                await send({"type": "http.response.body", "body": b""})
                return
        tipo = next((v.decode("latin-1") for k, v in cab if k.lower() == b"content-type"), "")
        if not tipo.startswith(SE_COMPRIME):
            cab.append((b"content-length", str(len(cuerpo)).encode()))
            await send({"type": "http.response.start", "status": 200, "headers": cab})
            await send({"type": "http.response.body", "body": cuerpo})
            return
        cab.append((b"vary", b"Accept-Encoding"))
        if len(cuerpo) >= MINIMO_COMPRIMIR and "gzip" in pedido.get("accept-encoding", ""):
            cuerpo = gzip.compress(cuerpo, compresslevel=5)
            cab.append((b"content-encoding", b"gzip"))
        cab.append((b"content-length", str(len(cuerpo)).encode()))
        await send({"type": "http.response.start", "status": 200, "headers": cab})
        await send({"type": "http.response.body", "body": cuerpo})


def versionar(html, carpeta):
    """Le pega a cada `<script src="/estaticos/x.js">` la fecha de su archivo (`?v=…`).

    Con eso el telefono guarda el archivo para siempre y aun asi recibe el nuevo apenas
    cambia. El que no esta en `carpeta` (una ruta que arma el panel a mano) queda como
    estaba, y entonces va por el camino de la huella.
    """
    def con_fecha(m):
        try:
            return f'{m.group(1)}?v={int((carpeta / m.group(2)).stat().st_mtime)}"'
        except OSError:
            return m.group(0)
    return re.sub(r'(<script src="/estaticos/([\w.-]+\.js))"', con_fecha, html)
