"""El resumen automático de contexto de Claude no aparece como mensaje de Martín."""
import json
import tempfile
from pathlib import Path

from app.voz import seguir
from app.voz import sesiones_movil as sm


def linea(texto, **campos):
    dato = {"type": "user", "message": {"role": "user", "content": texto}}
    dato.update(campos)
    return json.dumps(dato)


interno = linea(
    "This session is being continued from a previous conversation that ran out of context.",
    isCompactSummary=True,
    isVisibleInTranscriptOnly=True,
)
normal = linea("Este mensaje sí lo escribió Martín")

assert not seguir._es_turno_usuario(interno), "aceptó el resumen interno como mensaje"
assert seguir._es_turno_usuario(normal), "ocultó un mensaje normal de Martín"

with tempfile.TemporaryDirectory() as td:
    archivo = Path(td) / "charla.jsonl"
    archivo.write_text(interno + "\n" + normal + "\n", encoding="utf-8")
    filas = sm._filas_de(archivo)

assert [f["texto"] for f in filas] == ["Este mensaje sí lo escribió Martín"], filas
print("TODO BIEN: el resumen interno de Claude no se dibuja")
