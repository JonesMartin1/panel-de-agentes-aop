"""Prueba pura: no abre micrófono, Whisper, Claude ni Codex."""

from app.voz import ordenes_reutilizables as ordenes


def main():
    instruccion, respuesta = ordenes.resolver("Revisá este proyecto")
    assert "revisar el proyecto" in instruccion and not respuesta
    assert "no modifiques" in instruccion.lower()

    instruccion, _ = ordenes.resolver("Corré las pruebas")
    assert "pruebas relevantes" in instruccion

    instruccion, _ = ordenes.resolver("Buscame errores")
    assert "seguridad" in instruccion and "evidencia" in instruccion

    instruccion, respuesta = ordenes.resolver("¿Qué funciones de voz hay?")
    assert not instruccion
    assert all(o["nombre"] in respuesta for o in ordenes.ORDENES)

    instruccion, respuesta = ordenes.resolver("Decime las órdenes reutilizables")
    assert not instruccion
    assert all(o["nombre"] in respuesta for o in ordenes.ORDENES)

    # Una frase normal que contiene palabras parecidas no puede ser secuestrada.
    assert ordenes.resolver("¿Por qué buscaste errores ayer?") == ("", "")
    assert ordenes.resolver("Quiero revisar si este proyecto me conviene") == ("", "")
    assert ordenes.resolver("Las pruebas que corriste ayer fallaron") == ("", "")
    print("OK: órdenes reutilizables por voz")


if __name__ == "__main__":
    main()
