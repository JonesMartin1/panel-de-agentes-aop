"""Chequeos chicos del contrato de tareas largas del panel."""

import time

import panel


def probar_registro_termina():
    original = panel._ejecutar_turno_movil
    try:
        panel._ejecutar_turno_movil = lambda *a, **k: {
            "ok": True, "respuesta": "listo", "sid": "sid-nuevo", "aviso": ""
        }
        ident = "prueba-trabajo"
        panel._TRABAJOS_MOVIL[ident] = {
            "id": ident, "estado": "trabajando", "cwd": "X", "sid": "sid-viejo",
            "creado": time.time(), "terminado": None,
        }
        panel._correr_trabajo_movil(ident, "X", "sid-viejo", "hacelo", "codex", "high")
        t = panel._TRABAJOS_MOVIL.pop(ident)
        assert t["estado"] == "terminado"
        assert t["sid_nuevo"] == "sid-nuevo"
        assert t["respuesta"] == "listo"
        assert t["terminado"]
    finally:
        panel._ejecutar_turno_movil = original


def probar_registro_falla_y_cancela():
    original = panel._ejecutar_turno_movil
    try:
        panel._ejecutar_turno_movil = lambda *a, **k: {"ok": False, "error": "cortado"}
        for ident, cancelando, esperado in (
            ("prueba-falla", False, "fallo"), ("prueba-cancelada", True, "cancelado")
        ):
            panel._TRABAJOS_MOVIL[ident] = {
                "id": ident, "estado": "trabajando", "cwd": "X", "sid": "S",
                "creado": time.time(), "cancelando": cancelando,
            }
            panel._correr_trabajo_movil(ident, "X", "S", "x", "", "")
            assert panel._TRABAJOS_MOVIL.pop(ident)["estado"] == esperado
    finally:
        panel._ejecutar_turno_movil = original


def probar_contrato_pantalla():
    fuente = open(panel.__file__, encoding="utf-8").read()
    assert 'f.append(\'segundo_plano\', \'1\')' in fuente
    assert "@app.get(\"/movil/trabajo/{trabajo_id}\")" in fuente
    assert "@app.post(\"/movil/trabajo/{trabajo_id}/cancelar\")" in fuente
    assert "e.estado === 'trabajando'" in fuente
    assert "f.append('avisar', '1')" in fuente


if __name__ == "__main__":
    probar_registro_termina()
    probar_registro_falla_y_cancela()
    probar_contrato_pantalla()
    print("OK: tareas largas del celular")
