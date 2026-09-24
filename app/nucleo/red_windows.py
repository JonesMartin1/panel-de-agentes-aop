"""Callar el traceback de asyncio cuando un navegador corta la conexion de golpe.

⭐ Que es el ruido: en Windows, asyncio usa el "proactor". Cuando un cliente HTTP se
va sin avisar (cerraste la pestaña, se bloqueo el celular, el refresco de cada 3 s se
aborto), el transporte cierra su punta con `socket.shutdown()` sobre un socket que
Windows YA reseteo, y eso levanta `ConnectionResetError [WinError 10054]`. Como pasa
adentro de un callback del bucle de eventos, no lo puede atrapar nadie: asyncio lo
imprime entero, con traceback, en la consola del panel.

⚠ Por que importa que este callado: no rompe nada (el pedido ya estaba muerto), pero
son 8 renglones de traceback por cada cliente que se va, y tapan los mensajes de
verdad de las sesiones. Un log lleno de ruido inofensivo es un log que no se lee.

⚠ Por que no alcanza con un `loop.set_exception_handler`: cuando el `shutdown()`
revienta, el original nunca llega a cerrar el socket ni a marcar el transporte como
cerrado, asi que ademas de gritar deja el descriptor colgado. Este parche completa a
mano esa limpieza — es lo mismo que hace CPython en el camino feliz.
"""

import asyncio.proactor_events

_PUESTO = [False]


def silenciar_reset_windows():
    """Parcha el transporte del proactor para que un corte del cliente no grite.

    Se llama una sola vez, antes de levantar uvicorn. En sistemas que no usan el
    proactor (Linux, Mac) no hace nada malo: el modulo existe igual y el parche
    simplemente nunca se ejecuta.
    """
    if _PUESTO[0]:
        return
    base = asyncio.proactor_events._ProactorBasePipeTransport
    original = base._call_connection_lost

    def _call_connection_lost(self, exc):
        try:
            original(self, exc)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # El cliente ya no esta. Terminamos el cierre que quedo a medias, para
            # no dejar el socket abierto ni el transporte sin marcar.
            try:
                if self._sock is not None:
                    self._sock.close()
            except Exception:
                pass
            self._sock = None
            servidor = self._server
            if servidor is not None:
                servidor._detach()
                self._server = None
            self._called_connection_lost = True

    base._call_connection_lost = _call_connection_lost
    _PUESTO[0] = True
