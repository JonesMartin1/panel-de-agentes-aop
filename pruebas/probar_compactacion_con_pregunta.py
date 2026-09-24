"""La compactación automática no se adelanta y la pregunta sobrevive una recarga."""
from app.voz import sesiones_movil as sm
import panel


assert sm.AUTOCOMPACT["opus[1m]"] == "1000000", \
    "Opus 1M volvió a recibir una ventana artificial más chica"

originales = (sm.conversacion, sm.pide_compactar, sm.pregunta_de, sm.tareas_de,
              panel._codex_turno_realmente_activo)
try:
    sm.conversacion = lambda *a, **k: []
    sm.pide_compactar = lambda cwd, sid: "¿La compacto?"
    sm.pregunta_de = lambda *a, **k: None
    sm.tareas_de = lambda *a, **k: None
    panel._codex_turno_realmente_activo = lambda sid: False
    chat = panel.movil_chat("D:/proyecto", "sesion-larga")
finally:
    (sm.conversacion, sm.pide_compactar, sm.pregunta_de, sm.tareas_de,
     panel._codex_turno_realmente_activo) = originales

assert chat["pide_compactar"] == "¿La compacto?", \
    "GET /movil/chat perdió la pregunta de compactar"

compu = open("app/estaticos/sesiones.html", encoding="utf-8").read()
movil = open("panel.py", encoding="utf-8").read()
for nombre, pantalla in (("compu", compu), ("celular", movil)):
    assert "d.pide_compactar" in pantalla, f"{nombre} no recupera la pregunta al recargar"
    assert "Elegí si querés compactar antes de seguir" in pantalla, \
        f"{nombre} no frena Enviar hasta que Martín decida"

print("TODO BIEN: pregunta persistente y compactación sólo después del permiso")
