"""Que se oye mientras Laura piensa: tu musica, o la musiquita de espera.

Regla pedida por Martin (2026-08-16): si estabas escuchando algo, mientras ella
piensa vuelve ESO y se corta cuando arranca a hablar. Si no habia nada sonando, o
lo pausaste VOS a mano, suena la musiquita y nadie le aprieta play a lo tuyo.

Corre sin tocar el audio de la maquina: se reemplazan las dos funciones que hablan
con Windows (`pausar` y `reanudar`) por unas de mentira.

    python -m pruebas.test_media_espera
"""
from app.voz import media_pausa


class Windows:
    """Las sesiones de medios de Windows, de mentira."""

    def __init__(self, sonando=()):
        self.sonando = set(sonando)     # lo que esta en play ahora mismo
        self.reanudadas = []

    def pausar(self):
        pausadas = list(self.sonando)
        self.sonando.clear()
        return pausadas

    def reanudar(self, apps):
        self.reanudadas.append(set(apps))
        self.sonando.update(apps)


def preparar(sonando=()):
    win = Windows(sonando)
    media_pausa.pausar = win.pausar
    media_pausa.reanudar = win.reanudar
    media_pausa._por_charla.clear()
    media_pausa._manual.clear()
    return win


def caso(nombre, ok):
    print(("OK   " if ok else "FALLA") + " - " + nombre)   # sin acentos ni simbolos: la consola es cp1252
    return ok


def main():
    todo = []

    # 1) Estabas escuchando Spotify: la charla lo pausa, mientras piensa vuelve,
    #    al hablar se pausa de nuevo, y al terminar la charla vuelve para siempre.
    win = preparar({"Spotify"})
    media_pausa.pausar_por_charla()
    todo.append(caso("la charla pausa lo que sonaba", win.sonando == set()))
    todo.append(caso("mientras piensa, vuelve tu musica",
                     media_pausa.devolver_mientras_piensa() and win.sonando == {"Spotify"}))
    media_pausa.pausar_por_charla()
    todo.append(caso("cuando arranca a hablar, se calla", win.sonando == set()))
    media_pausa.reanudar_por_charla()
    todo.append(caso("terminada la charla, vuelve sola", win.sonando == {"Spotify"}))

    # 2) No habia nada sonando: nadie aprieta play, va la musiquita.
    win = preparar()
    media_pausa.pausar_por_charla()
    todo.append(caso("sin nada sonando, no hay nada que devolver",
                     media_pausa.devolver_mientras_piensa() is False))
    todo.append(caso("y no se le dio play a nada", win.reanudadas == []))

    # 3) ⭐ Lo pausaste VOS ("Venus, pausa"): se queda quieto, suena la musiquita.
    win = preparar({"Spotify"})
    media_pausa.pausar_por_charla()      # la charla lo pauso primero
    media_pausa.pausar_manual()          # y vos dijiste "pausa": ahora es tuyo
    todo.append(caso("lo que pausaste vos no cuenta como 'estaba sonando'",
                     media_pausa.hay_por_charla() is False))
    todo.append(caso("y NO se lo devuelve mientras piensa",
                     media_pausa.devolver_mientras_piensa() is False and win.sonando == set()))

    # 4) Un reproductor abierto pero en pausa es lo mismo que nada.
    win = preparar()                     # abierto, pero nada en play
    media_pausa.pausar_por_charla()
    todo.append(caso("un reproductor en pausa no dispara nada",
                     media_pausa.hay_por_charla() is False))

    print(f"\n{sum(todo)}/{len(todo)} casos OK")
    return 0 if all(todo) else 1


if __name__ == "__main__":
    raise SystemExit(main())
