"""Dice si Laura lleva demasiado tiempo sin micrófono por el bloqueo del panel. Lo usa el vigía.

Sale con código 0 si todo está bien y con 1 si la bandera `mic_bloqueado.flag` lleva
puesta más de `UMBRAL_HORAS`. No manda ningún aviso por su cuenta: de eso se encarga
`vigilar.py` leyendo `vigilar.json`, que ya trae las reglas anti-ruido (avisa una vez al
pasar el umbral y otra cuando se destraba, nunca en cada vuelta).

Existe porque del 2026-09-06 al 2026-09-25 Laura no escuchó a Martín: la bandera del
bloqueo de privacidad había quedado puesta, el interruptor del panel se veía en verde
(miraba solo a Windows) y nadie avisó en diecinueve días. Un bloqueo de una noche es
normal y no molesta a nadie; uno que pasa el día casi seguro es un olvido.

Se corre solo:
    python -m app.voz.chequeo_microfono          # 0 = bien, 1 = bloqueada hace mucho
    python -m app.voz.chequeo_microfono --decir  # además imprime el estado
"""
import sys
import time

from app.rutas import MIC_BLOQUEADO

UMBRAL_HORAS = 24


def estado(ahora=None):
    """(ok, texto). Si no hay bandera, o es reciente, está bien."""
    ahora = time.time() if ahora is None else ahora
    try:
        desde = MIC_BLOQUEADO.stat().st_mtime
    except OSError:
        return True, "Laura tiene el micrófono habilitado."
    horas = (ahora - desde) / 3600
    cuando = time.strftime("%d/%m a las %H:%M", time.localtime(desde))
    if horas < UMBRAL_HORAS:
        return True, f"Micrófono bloqueado desde el {cuando}, hace {horas:.0f} h: todavía es normal."
    dias = horas / 24
    lapso = f"{dias:.0f} días" if dias >= 2 else f"{horas:.0f} horas"
    return False, (f"Laura lleva {lapso} sin micrófono: el bloqueo del panel está puesto "
                   f"desde el {cuando}. Si no fue a propósito, destrabalo desde el panel.")


def main():
    ok, texto = estado()
    if "--decir" in sys.argv or not ok:
        print(texto, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
