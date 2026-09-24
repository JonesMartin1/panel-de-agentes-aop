"""Mute de TODOS los microfonos a nivel de Windows (IAudioEndpointVolume).

Es el respaldo del interruptor "Microfono de Windows" del panel. Corre como
subproceso (`python -m app.mic_windows leer|permitir|silenciar`) A PROPOSITO:
comtypes adentro de un servidor multihilo termina en crash nativo del proceso
entero — probado el 2026-08-13 dos veces, incluso con un hilo dedicado para
COM. En un proceso aparte, si COM explota, muere el subproceso y el panel
sigue vivo.

Por que mute y no la llave de Privacidad y seguridad de Windows: esa clave
(ConsentStore, HKCU) resulto ser un placebo para programas de escritorio —
medido: con "Deny" el audio seguia llegando identico por WASAPI. El mute del
dispositivo si corta de verdad: 15840/15840 muestras en cero exacto.

⚠ NO intentar "sincronizar" la pantalla de Privacidad y seguridad de Windows
escribiendo el registro (ConsentStore): se probo el 2026-08-13 y en este
Windows (build 26200) esa pantalla escribe en el registro pero LEE de la cache
interna del servicio de privacidad — el interruptor no se mueve, y el estado
oficial queda desincronizado, lo que puede bloquear apps de la tienda (Claude
incluida) sin que ninguna pantalla lo muestre. Esa pagina se maneja solo desde
Configuracion; este modulo hace el corte real y verificable, que es el mute.

Imprime JSON en stdout: {"permitido": true/false}
(permitido = queda al menos un microfono activo sin silenciar)
"""
import json
import sys

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from pycaw.constants import EDataFlow, DEVICE_STATE


def _endpoints():
    enum = AudioUtilities.GetDeviceEnumerator()
    col = enum.EnumAudioEndpoints(EDataFlow.eCapture.value, DEVICE_STATE.ACTIVE.value)
    return [col.Item(i) for i in range(col.GetCount())]


def _vol(dev):
    return cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                POINTER(IAudioEndpointVolume))


def main():
    accion = sys.argv[1] if len(sys.argv) > 1 else "leer"
    if accion in ("permitir", "silenciar"):
        for d in _endpoints():
            _vol(d).SetMute(0 if accion == "permitir" else 1, None)
    vols = [_vol(d) for d in _endpoints()]
    permitido = any(not v.GetMute() for v in vols) if vols else True
    print(json.dumps({"permitido": permitido}))


if __name__ == "__main__":
    main()
