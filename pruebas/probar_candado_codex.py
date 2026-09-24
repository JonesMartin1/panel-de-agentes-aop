"""El primer turno Codex no acepta un segundo escritor cuando ya tiene id."""
from app.voz import sesiones_movil as sm

cwd = r"C:\EspacioDeTrabajo\_prueba-candado-codex"
sid = "sid-que-acaba-de-nacer"
viejas = set(sm._RESERVAS_CODEX)
try:
    primera = sm._reservar_codex(cwd, "")
    assert primera, "no reservo el turno nuevo"
    sm._agregar_reserva_codex(primera, cwd, sid)
    assert sm._reservar_codex(cwd, sid) is None, "dejo entrar un segundo escritor"
    sm._liberar_reservas_codex(primera)
    segunda = sm._reservar_codex(cwd, sid)
    assert segunda, "no libero la charla al terminar"
    sm._liberar_reservas_codex(segunda)
finally:
    with sm._CANDADO_RESERVAS_CODEX:
        sm._RESERVAS_CODEX.clear()
        sm._RESERVAS_CODEX.update(viejas)

print("TODO BIEN: una charla Codex no acepta dos escritores")
