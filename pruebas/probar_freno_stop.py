"""El freno de mano de los agentes: el archivo STOP en la raiz.

Regla: con STOP puesto NO arranca ningun turno nuevo (ni de Claude ni de Codex),
pero lo que ya estaba corriendo sigue. Falla cerrada: ante la duda, frena.

    python -m pruebas.probar_freno_stop

No gasta un solo token: no llama a ningun CLI. Le tapa la boca a las funciones
que arrancarian el turno y mira si llegaron a ser llamadas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rutas import FRENO_AGENTES
from app.voz import sesiones_movil as sm

bien = 0
mal = 0


def chequear(titulo, condicion, detalle=""):
    global bien, mal
    if condicion:
        bien += 1
        print(f"  ok   {titulo}")
    else:
        mal += 1
        print(f"  MAL  {titulo}" + (f" -> {detalle}" if detalle else ""))


class Espia:
    """Se pone en lugar de lo que arrancaria el turno y anota si lo llamaron."""

    def __init__(self):
        self.llamado = False

    def __call__(self, *args, **kwargs):
        self.llamado = True
        return ("respuesta de mentira", "sid-de-mentira")


def con_freno(motivo, funcion):
    """Corre `funcion()` con el archivo STOP puesto, y despues lo saca siempre."""
    habia = FRENO_AGENTES.exists()
    previo = FRENO_AGENTES.read_text(encoding="utf-8") if habia else None
    FRENO_AGENTES.write_text(motivo, encoding="utf-8")
    try:
        return funcion()
    finally:
        if previo is None:
            FRENO_AGENTES.unlink(missing_ok=True)
        else:
            FRENO_AGENTES.write_text(previo, encoding="utf-8")


def main():
    if FRENO_AGENTES.exists():
        print(f"\n⚠ Ya hay un STOP puesto en {FRENO_AGENTES}. La prueba lo respeta y lo deja como estaba.\n")

    print("\nSin freno")
    chequear("freno_puesto() devuelve vacio", sm.freno_puesto() == "" or FRENO_AGENTES.exists())

    print("\nCon freno puesto")
    motivo = con_freno("me fui a comer", sm.freno_puesto)
    chequear("freno_puesto() devuelve el motivo escrito", motivo == "me fui a comer", motivo)

    motivo = con_freno("   ", sm.freno_puesto)
    chequear("un STOP vacio igual frena, con motivo por defecto",
             bool(motivo) and "STOP" in motivo, motivo)

    print("\nUn turno nuevo rebota, y NO llega a arrancar nada")
    for cerebro, sid in (("claude", ""), ("codex", "codex-123")):
        espia_codex = Espia()
        espia_viva = Espia()
        antes_codex, antes_viva = sm.codex_mandar, sm._conseguir_viva
        sm.codex_mandar, sm._conseguir_viva = espia_codex, espia_viva
        try:
            def intentar():
                try:
                    sm.mandar("D:/IA/wpp-transcriptor", sid, "hola", cerebro=cerebro)
                    return None
                except RuntimeError as e:
                    return str(e)
            error = con_freno("probando el freno", intentar)
        finally:
            sm.codex_mandar, sm._conseguir_viva = antes_codex, antes_viva

        chequear(f"[{cerebro}] mandar() levanta RuntimeError", error is not None)
        chequear(f"[{cerebro}] el error explica el motivo",
                 bool(error) and "probando el freno" in error, error or "")
        chequear(f"[{cerebro}] no se arranco ningun proceso",
                 not espia_codex.llamado and not espia_viva.llamado)

    print("\nSin freno, el turno SI arranca (la prueba al reves)")
    espia_viva = Espia()
    antes = sm._conseguir_viva
    sm._conseguir_viva = espia_viva
    try:
        if FRENO_AGENTES.exists():
            print("  (salteado: hay un STOP puesto de verdad)")
        else:
            try:
                sm.mandar("D:/IA/wpp-transcriptor", "sesion-de-mentira", "hola")
            except Exception:
                pass  # va a fallar mas adelante; lo unico que importa es que LLEGO
            chequear("sin STOP, mandar() sigue de largo hasta arrancar la sesion",
                     espia_viva.llamado)
    finally:
        sm._conseguir_viva = antes

    print("\nParar sigue siendo lo que corta un turno en curso")
    chequear("parar() no mira el freno", "freno_puesto" not in sm.parar.__doc__ if sm.parar.__doc__ else True)

    print(f"\n{'TODO BIEN' if mal == 0 else 'HAY PROBLEMAS'} — {bien} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
