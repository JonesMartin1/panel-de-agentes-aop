"""El bug del trabajo en segundo plano, contra el CLI de VERDAD: un comando en segundo plano que
sobrevive de un turno al siguiente.

Son dos turnos con haiku en una carpeta temporal (gasta poco, pero gasta: no es una
prueba para correr a cada rato). El turno 1 manda algo largo a segundo plano con
`run_in_background` y el turno 2 le pide la salida con `BashOutput`. Si el proceso de la
sesion se reciclara entre turnos, el turno 2 contestaria "no completion record was
found", que es exactamente el sintoma que trajo Martin el 2026-08-20.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_fondo_real
"""
import re
import sys
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm

UNO = ("Corré este comando EN SEGUNDO PLANO (Bash con run_in_background) y no esperes a "
       "que termine: ping -n 25 127.0.0.1 . Contestame SOLO con el shell id que te "
       "devolvió, sin ninguna otra palabra.")
DOS = ("Leé con BashOutput la salida de ese comando que dejaste en segundo plano. "
       "Contestame en UNA línea: primero VIVE o MURIO según si sigue corriendo, y "
       "después las primeras palabras de la salida que llevaba.")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="fondo_real_"))
    sid = ""
    try:
        print("turno 1: mando el comando a segundo plano...", flush=True)
        r1, sid = sm.mandar(str(tmp), "", UNO, modelo="haiku")
        print("  ->", r1[:200], flush=True)
        print("  sesion:", sid, flush=True)
        print("turno 2: le pido la salida de ese mismo comando...", flush=True)
        r2, _ = sm.mandar(str(tmp), sid, DOS, modelo="haiku")
        print("  ->", r2[:300], flush=True)

        malo = re.search(r"no completion record|previous session|MURIO", r2, re.I)
        bueno = re.search(r"\bVIVE\b|running|sigue corriendo", r2, re.I)
        if malo and not bueno:
            print("\nFALLA: el comando de segundo plano no sobrevivio al turno.")
            return 1
        if not bueno:
            print("\nDUDOSO: la respuesta no dice claro si vivia. Leela arriba.")
            return 1
        print("\nOK: el comando seguia vivo en el turno siguiente. Bug cerrado.")
        return 0
    finally:
        if sid:
            sm.apagar_sesion(str(tmp), sid)


if __name__ == "__main__":
    sys.exit(main())
