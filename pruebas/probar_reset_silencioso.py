"""El corte brusco de un navegador no tiene que ensuciar la consola del panel.

Que se prueba, contra el asyncio de verdad (no una imitacion):
  1. Sin el parche, un `ConnectionResetError` en el `shutdown()` del socket SE ESCAPA
     del callback — o sea, el ruido de WinError 10054 es real y no lo inventamos.
  2. Con el parche puesto, ese mismo caso NO levanta nada.
  3. Y ademas termina la limpieza que el original dejo a medias: cierra el socket,
     lo suelta, avisa al servidor y marca el transporte como cerrado. Si solo
     tragaramos la excepcion, cada cliente que se va dejaria un socket abierto.
  4. Un cierre normal (sin reset) sigue funcionando igual que antes.
  5. El parche se puede pedir dos veces sin apilarse.
  6. `panel.py` de verdad LLAMA a silenciar_reset_windows() antes de uvicorn.run —
     un parche declarado y nunca invocado es decoracion.

No levanta uvicorn, no abre puertos, no toca el panel prendido ni gasta tokens.

    python -m pruebas.probar_reset_silencioso
"""
import asyncio.proactor_events
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

BIEN, MAL = [], []


def chequeo(nombre, ok, detalle=""):
    (BIEN if ok else MAL).append(nombre)
    print(("  ok   " if ok else "  FALLA") + " " + nombre + (f"  -> {detalle}" if detalle and not ok else ""))


class _SocketQueSeFue:
    """Un socket cuyo `shutdown()` explota igual que en Windows cuando el cliente
    ya se fue: WinError 10054, 'An existing connection was forcibly closed'."""

    def __init__(self, revienta=True):
        self.revienta = revienta
        self.cerrado = False

    def fileno(self):
        return 3          # cualquier cosa que no sea -1: el original chequea eso

    def shutdown(self, como):
        if self.revienta:
            raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")

    def close(self):
        self.cerrado = True


class _ProtocoloMudo:
    def __init__(self):
        self.avisado = False

    def connection_lost(self, exc):
        self.avisado = True


class _ServidorFalso:
    def __init__(self):
        self.sueltos = 0

    def _detach(self):
        self.sueltos += 1


class _TransporteFalso:
    """Lo minimo que `_call_connection_lost` toca de un transporte real."""

    def __init__(self, revienta=True):
        self._called_connection_lost = False
        self._protocol = _ProtocoloMudo()
        self._sock = _SocketQueSeFue(revienta)
        self._server = _ServidorFalso()


def _llamar(func, transporte):
    """Corre el callback y dice si se escapo una excepcion."""
    try:
        func(transporte, None)
        return None
    except BaseException as e:
        return e


def main():
    base = asyncio.proactor_events._ProactorBasePipeTransport
    original = base._call_connection_lost

    print("Corte brusco del cliente (WinError 10054)\n")

    # 1. El ruido existe: sin parche, la excepcion se escapa del callback.
    t = _TransporteFalso()
    salio = _llamar(original, t)
    chequeo("sin el parche, el reset se escapa del callback",
            isinstance(salio, ConnectionResetError),
            f"salio {salio!r}, esperaba ConnectionResetError")
    chequeo("sin el parche, el socket queda SIN cerrar",
            not t._sock.cerrado and not t._called_connection_lost,
            "el original ya limpiaba: revisar si CPython cambio")

    # Ahora si, el parche.
    from app.nucleo.red_windows import silenciar_reset_windows
    silenciar_reset_windows()
    parchado = base._call_connection_lost
    chequeo("el parche reemplazo el metodo", parchado is not original)

    # 2 y 3. Con el parche: ni ruido, ni socket colgado.
    t = _TransporteFalso()
    sock, servidor = t._sock, t._server      # el parche los deja en None: guardarlos antes
    salio = _llamar(parchado, t)
    chequeo("con el parche, el reset ya no grita", salio is None, f"se escapo {salio!r}")
    chequeo("el protocolo igual se entero del cierre", t._protocol.avisado)
    chequeo("el socket quedo cerrado", sock.cerrado)
    chequeo("el transporte solto el socket", t._sock is None)
    chequeo("le aviso al servidor (_detach)", t._server is None and servidor.sueltos == 1)
    chequeo("quedo marcado como cerrado", t._called_connection_lost is True)

    # 4. Un cierre normal no cambia de comportamiento.
    t = _TransporteFalso(revienta=False)
    salio = _llamar(parchado, t)
    chequeo("un cierre limpio sigue andando igual",
            salio is None and t._sock is None and t._called_connection_lost is True,
            f"salio {salio!r}")

    # 5. Idempotente: pedirlo dos veces no apila parches.
    silenciar_reset_windows()
    chequeo("pedirlo dos veces no apila parches",
            base._call_connection_lost is parchado)

    # 6. Que este de verdad ENCHUFADO en el panel, no solo escrito.
    panel = (RAIZ / "panel.py").read_text(encoding="utf-8", errors="replace")
    arranque = panel[panel.find('if __name__ == "__main__":'):]
    llama = "silenciar_reset_windows()" in arranque
    antes = (arranque.find("silenciar_reset_windows()") < arranque.find("uvicorn.run(")
             if llama else False)
    chequeo("panel.py lo llama antes de levantar uvicorn", llama and antes,
            "esta importado pero nunca se ejecuta" if not llama else "queda DESPUES de uvicorn.run")

    print(f"\n{len(BIEN)} bien, {len(MAL)} mal")
    if MAL:
        print("FALLA: " + ", ".join(MAL))
        return 1
    print("TODO BIEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
