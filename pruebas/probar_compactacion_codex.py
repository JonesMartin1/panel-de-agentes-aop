"""Compactar Codex: pregunta antes del techo y rescata una charla que ya lo llenó.

No abre ningún turno real: contexto, conversación y `mandar()` están falseados.

    D:\IA\envs\wpp\python.exe -m pruebas.probar_compactacion_codex
"""
import json
import sys
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm

ok = fallo = 0


def probar(que, condicion):
    global ok, fallo
    if condicion:
        ok += 1
        print("  ok   ", que)
    else:
        fallo += 1
        print("  FALLA", que)


class CodexFalso:
    def __init__(self, tokens, ventana=258_400, resumen="resumen completo " * 8,
                 filas=None, falla_resumen=False, falla_siembras=0):
        self.tokens, self.ventana, self.resumen = tokens, ventana, resumen
        self.filas = filas or []
        self.falla_resumen, self.falla_siembras = falla_resumen, falla_siembras
        self.resumenes, self.siembras, self.apagadas = [], [], []

    def __enter__(self):
        self.originales = {
            "es_codex": sm.es_codex,
            "codex_contexto": sm.codex_contexto,
            "mandar": sm.mandar,
            "conversacion": sm.conversacion,
            "codex_modelo_de": sm.codex_modelo_de,
            "codex_esfuerzo_de": sm.codex_esfuerzo_de,
            "codex_velocidad_de": sm.codex_velocidad_de,
            "apagar_sesion": sm.apagar_sesion,
        }
        self.ruta = sm.AJUSTES_SESIONES
        self.tmp = Path(tempfile.gettempdir()) / "probar_compactacion_codex.json"
        self.tmp.write_text("{}", encoding="utf-8")
        sm.AJUSTES_SESIONES = self.tmp
        sm.es_codex = lambda sid: bool(sid)
        sm.codex_contexto = lambda sid: {
            "tokens": self.tokens, "tope": self.ventana, "nivel": "", "aviso": ""}
        sm.codex_modelo_de = lambda sid: "gpt-prueba"
        sm.codex_esfuerzo_de = lambda sid: "high"
        sm.codex_velocidad_de = lambda sid: "fast"
        sm.conversacion = lambda cwd, sid, ultimos=40: list(self.filas)[-ultimos:]
        sm.apagar_sesion = lambda cwd, sid: self.apagadas.append(sid)

        def mandar(cwd, sid, texto, modelo="", cerebro="", esfuerzo="", velocidad="",
                   al_nacer=None):
            datos = {"sid": sid, "texto": texto, "modelo": modelo,
                     "cerebro": cerebro, "esfuerzo": esfuerzo,
                     "velocidad": velocidad}
            if sid:
                self.resumenes.append(datos)
                if self.falla_resumen:
                    raise RuntimeError("context_window_exceeded")
                return self.resumen, sid
            self.siembras.append(datos)
            if self.falla_siembras:
                self.falla_siembras -= 1
                raise RuntimeError("falla pasajera")
            return "seguimos", "codex-nueva"

        sm.mandar = mandar
        return self

    def __exit__(self, *args):
        for nombre, valor in self.originales.items():
            setattr(sm, nombre, valor)
        sm.AJUSTES_SESIONES = self.ruta
        self.tmp.unlink(missing_ok=True)

    def marcas(self):
        return json.loads(self.tmp.read_text(encoding="utf-8"))


print("\n--- Pregunta antes de que Codex llene la ventana ---")
with CodexFalso(180_879) as f:
    probar("debajo del 70 por ciento no pregunta",
           sm.pide_compactar("D:/x", "codex-vieja") == "")
with CodexFalso(180_880) as f:
    pregunta = sm.pide_compactar("D:/x", "codex-vieja")
probar("en el 70 por ciento pide permiso", "¿" in pregunta and "compact" in pregunta)

print("\n--- Si ya llenó la ventana, ofrece rescatarla ---")
with CodexFalso(266_448) as f:
    pregunta = sm.pide_compactar("D:/x", "codex-vieja")
probar("explica el límite y el rescate", "límite" in pregunta and "rescatar" in pregunta)

print("\n--- Camino preventivo: resumen real y continuación con las mismas perillas ---")
filas = [{"de": "vos", "texto": "seguí con el arreglo"}]
with CodexFalso(190_000, filas=filas) as f:
    sid, resumen = sm.compactar("D:/x", "codex-vieja")
    marcas = f.marcas()
probar("le pide el resumen a la vieja", len(f.resumenes) == 1)
probar("la nueva nace en Codex", len(f.siembras) == 1
       and f.siembras[0]["cerebro"] == "codex")
probar("conserva modelo, esfuerzo y velocidad",
       (f.siembras[0]["modelo"], f.siembras[0]["esfuerzo"],
        f.siembras[0]["velocidad"]) == ("gpt-prueba", "high", "fast"))
probar("devuelve la nueva y el resumen",
       sid == "codex-nueva" and resumen == f.resumen.strip())
probar("marca la continuidad ida y vuelta",
       marcas.get("codex-vieja", {}).get("sigue_en") == "codex-nueva"
       and marcas.get("codex-nueva", {}).get("viene_de") == "codex-vieja")

print("\n--- Camino de rescate: no vuelve a golpear el hilo que ya rebota ---")
filas = [
    {"de": "vos", "texto": "arreglá el webhook sin perder lo anterior"},
    {"de": "claude", "texto": "quedó pendiente probar el caso de ocho polos"},
]
with CodexFalso(266_448, filas=filas) as f:
    sid, resumen = sm.compactar("D:/x", "codex-llena")
probar("no manda ningún turno a la charla llena", f.resumenes == [])
probar("rescata los últimos intercambios visibles",
       "Martin: arreglá el webhook" in f.siembras[0]["texto"]
       and "Asistente: quedó pendiente" in f.siembras[0]["texto"])
probar("la siembra aclara que es un rescate", "RESCATE DEL HILO" in f.siembras[0]["texto"])
probar("nace una continuación utilizable", sid == "codex-nueva" and len(resumen) > 40)

print("\n--- Si el resumen falla por una carrera, también usa el rescate ---")
with CodexFalso(190_000, filas=filas, falla_resumen=True) as f:
    sid, _ = sm.compactar("D:/x", "codex-vieja")
probar("intentó resumir una vez", len(f.resumenes) == 1)
probar("y de todos modos abrió la continuación", sid == "codex-nueva")

print("\n--- El nombre no se convierte en el texto técnico de la siembra ---")
originales = (sm._ajustes, sm.es_codex, sm._codex_mensajes, sm._CODEX_SIDS)
primeros_original = getattr(sm, "_codex_primeros", None)
sm._ajustes = lambda: {"codex-nueva": {"viene_de": "codex-vieja"}}
sm.es_codex = lambda sid: sid.startswith("codex-")
sm._codex_mensajes = lambda sid: (
    [{"de": "vos", "texto": sm.SIEMBRA[:100]}] if sid == "codex-nueva" else
    [{"de": "vos", "texto": "Arreglar sesiones largas de Codex"}])
if primeros_original is not None:
    # Compatible con la optimización de lectura que otra sesión tiene en curso.
    sm._codex_primeros = sm._codex_mensajes
sm._CODEX_SIDS = {"codex-nueva": {"cwd": "D:/x"},
                  "codex-vieja": {"cwd": "D:/x"}}
sm._CODEX_TITULOS.pop("codex-nueva", None)
try:
    probar("hereda el nombre humano de la charla vieja",
           sm._codex_titulo("codex-nueva") == "Arreglar sesiones largas de Codex")
finally:
    sm._ajustes, sm.es_codex, sm._codex_mensajes, sm._CODEX_SIDS = originales
    if primeros_original is not None:
        sm._codex_primeros = primeros_original
    sm._CODEX_TITULOS.pop("codex-nueva", None)

print(f"\n{ok} bien, {fallo} mal")
sys.exit(1 if fallo else 0)
