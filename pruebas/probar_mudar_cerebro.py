"""Mudar una charla al otro cerebro: resumen de la vieja + siembra en el otro CLI.

Pedido de Martin el 2026-08-20 ("no podemos hacer que cambie cuando yo quiera?"):
el cerebro se elegia solo al nacer la charla, y una ya andando no se podia pasar
de Claude a Codex ni al reves.

Aca no se habla con ningun CLI de verdad: se falsean `mandar`, `es_codex` y
`conversacion` y se mira que la jugada sea la correcta — a quien le pide el
resumen, con que cerebro siembra, y que la charla vieja quede marcada.

    python -m pruebas.probar_mudar_cerebro
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


class Falso:
    """Reemplaza mandar(), es_codex() y conversacion() mientras dura el bloque."""

    def __init__(self, de_codex=False, resumen="resumen largo de mentira " * 3,
                 nace="nacida1234", filas=None, revienta_resumen=False,
                 falla_siembras=0, nace_vacia=False):
        self.de_codex, self.resumen, self.nace = de_codex, resumen, nace
        self.filas = filas or []
        self.revienta_resumen, self.nace_vacia = revienta_resumen, nace_vacia
        self.falla_siembras = falla_siembras
        self.resumenes, self.siembras = [], []

    def __enter__(self):
        self._mandar, self._es, self._conv = sm.mandar, sm.es_codex, sm.conversacion
        self._ruta = sm.AJUSTES_SESIONES
        self._tmp = Path(tempfile.gettempdir()) / "probar_mudar_cerebro.json"
        self._tmp.write_text("{}", encoding="utf-8")
        sm.AJUSTES_SESIONES = self._tmp

        def mandar(cwd, sid, texto, modelo="", cerebro=""):
            if sid:                       # el pedido de resumen a la charla vieja
                self.resumenes.append((sid, modelo))
                if self.revienta_resumen:
                    raise RuntimeError("se quedo sin cupo")
                return self.resumen, sid
            self.siembras.append((texto, cerebro))
            if self.falla_siembras > 0:
                self.falla_siembras -= 1
                raise RuntimeError("529 pasajero")
            return "una frase", ("" if self.nace_vacia else self.nace)

        sm.mandar = mandar
        sm.es_codex = lambda sid: self.de_codex
        sm.conversacion = lambda cwd, sid, ultimos=40: self.filas
        return self

    def __exit__(self, *a):
        sm.mandar, sm.es_codex, sm.conversacion = self._mandar, self._es, self._conv
        sm.AJUSTES_SESIONES = self._ruta
        self._tmp.unlink(missing_ok=True)

    def marcas(self):
        return json.loads(self._tmp.read_text(encoding="utf-8"))


print("\n--- De Claude a Codex, el camino feliz ---")
with Falso() as f:
    sid, para, aviso = sm.mudar_cerebro("D:/x", "vieja")
    marcas = f.marcas()
probar("vuelve el id nuevo y quien entra", sid == "nacida1234" and para == "Codex")
probar("sin nada que avisar, el aviso viene vacio", aviso == "")
probar("el resumen se le pidio a la vieja", f.resumenes and f.resumenes[0][0] == "vieja")
probar("la siembra nace con Codex", f.siembras and f.siembras[0][1] == "codex")
probar("la siembra lleva el resumen", f.resumen.strip() in f.siembras[0][0])
probar("la siembra dice de donde viene", "Claude" in f.siembras[0][0]
       and "Codex" in f.siembras[0][0])
probar("la vieja queda con su sigue_en",
       marcas.get("vieja", {}).get("sigue_en") == "nacida1234")

print("\n--- De Codex a Claude, el camino de vuelta ---")
with Falso(de_codex=True) as f:
    sid, para, _ = sm.mudar_cerebro("D:/x", "codex-vieja")
probar("entra Claude", para == "Claude")
probar("la siembra nace con Claude (cerebro vacio)", f.siembras[0][1] == "")
probar("a la vieja de Codex no se le manda modelo", f.resumenes[0][1] == "")

print("\n--- Si la vieja no resume, sale el plan B: la charla pelada ---")
filas = [{"de": "vos", "texto": "hola, en que quedamos con el panel"},
         {"de": "claude", "texto": "quedamos en probar el boton nuevo del celular"}]
with Falso(revienta_resumen=True, filas=filas) as f:
    sid, para, _ = sm.mudar_cerebro("D:/x", "vieja")
probar("la mudanza sale igual", sid == "nacida1234")
probar("el traspaso lleva la charla pelada",
       "Martin: hola" in f.siembras[0][0] and "Asistente:" in f.siembras[0][0])

print("\n--- Resumen corto y flojo: tambien cae al plan B ---")
with Falso(resumen="ok.", filas=filas) as f:
    sm.mudar_cerebro("D:/x", "vieja")
probar("no siembra con un resumen de dos letras", "Martin: hola" in f.siembras[0][0])

print("\n--- Sin resumen y sin charla: no se muda nada ---")
with Falso(revienta_resumen=True, filas=[]) as f:
    try:
        sm.mudar_cerebro("D:/x", "vieja")
        probar("avisa que no pudo", False)
    except RuntimeError as e:
        probar("avisa que no pudo", "traspaso" in str(e))
probar("y no sembro nada", f.siembras == [])

print("\n--- La siembra falla una vez: se reintenta (el resumen ya se pago) ---")
with Falso(falla_siembras=1) as f:
    sid, _, _ = sm.mudar_cerebro("D:/x", "vieja")
probar("al segundo intento nace", sid == "nacida1234" and len(f.siembras) == 2)

print("\n--- Una charla que YA sigue en otra no se muda (naceria un tenedor) ---")
with Falso() as f:
    sm.AJUSTES_SESIONES.write_text(
        json.dumps({"vieja": {"sigue_en": "otra999"}}), encoding="utf-8")
    try:
        sm.mudar_cerebro("D:/x", "vieja")
        probar("se niega y lo explica", False)
    except RuntimeError as e:
        probar("se niega y lo explica", "sigue en otra" in str(e))
probar("y no gasto ni un turno", f.resumenes == [] and f.siembras == [])

print("\n--- Tampoco se compacta una que ya sigue en otra ---")
with Falso() as f:
    sm.AJUSTES_SESIONES.write_text(
        json.dumps({"vieja": {"sigue_en": "otra999"}}), encoding="utf-8")
    try:
        sm.compactar("D:/x", "vieja")
        probar("compactar tambien se niega", False)
    except RuntimeError as e:
        probar("compactar tambien se niega", "sigue en otra" in str(e))

print("\n--- Si Codex viene al limite del cupo, la mudanza avisa ---")
from app.voz import codex_voz          # noqa: E402
_cupo = codex_voz.cupo
codex_voz.cupo = lambda: {"usado": 95.0}
try:
    with Falso() as f:
        _, _, aviso = sm.mudar_cerebro("D:/x", "vieja")
    probar("se muda igual pero lo dice", "95" in aviso and "cupo" in aviso)
finally:
    codex_voz.cupo = _cupo

print("\n--- Si el CLI del otro cerebro no esta, lo dice en criollo ---")
with Falso() as f:
    _mandar_falso = sm.mandar
    def sin_cli(cwd, sid, texto, modelo="", cerebro=""):
        if sid:
            return _mandar_falso(cwd, sid, texto, modelo=modelo, cerebro=cerebro)
        raise FileNotFoundError("WinError 2")
    sm.mandar = sin_cli
    try:
        sm.mudar_cerebro("D:/x", "vieja")
        probar("mensaje amable en vez de WinError", False)
    except RuntimeError as e:
        probar("mensaje amable en vez de WinError",
               "No encuentro el programa" in str(e))
    finally:
        sm.mandar = _mandar_falso

print("\n--- La nueva no devuelve id: se avisa y la vieja sigue ---")
with Falso(nace_vacia=True) as f:
    try:
        sm.mudar_cerebro("D:/x", "vieja")
        probar("avisa que no arranco", False)
    except RuntimeError as e:
        probar("avisa que no arranco", "Codex" in str(e))
    marcas = f.marcas()
probar("no dejo una marca a ningun lado", marcas == {})

print("\n--- Sin sid no hay nada que mudar ---")
with Falso() as f:
    try:
        sm.mudar_cerebro("D:/x", "")
        probar("corta antes de empezar", False)
    except RuntimeError:
        probar("corta antes de empezar", True)

print(f"\n{ok} bien, {fallo} mal")
sys.exit(1 if fallo else 0)
