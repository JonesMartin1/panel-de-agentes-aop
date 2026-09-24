"""El borrador de cada conversacion, del lado del servidor.

Pedido de Martin (2026-08-18): *"quiero que lo que yo escriba dentro de una sesion quede
guardado como borrador y se pueda ver en todas, con una señalizacion que diga que esta en
borrador, que tenga un color y una animacion"*. Aca se prueba la mitad de abajo: guardar,
borrar, el tope, y el anticipo que viaja en la lista de conversaciones.

Llama a las funciones de `panel.py` DIRECTO, sin levantar el servidor (mismo truco que
`probar_arbol_archivos.py`: el vigilante de servicios solo arranca cuando lo sirve
uvicorn, asi que importar el panel no prende ni apaga nada).

⚠ Escribe en un archivo TEMPORAL, nunca en el `borradores_sesiones.json` de verdad: esto
guarda lo que Martin dejo a medio escribir y una prueba no puede pisarlo.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_borradores
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import panel
from app.voz import sesiones_movil

ok = fallo = 0


def chequear(que, condicion, detalle=""):
    global ok, fallo
    if condicion:
        ok += 1
        print(f"  ok   {que}")
    else:
        fallo += 1
        print(f"  FALLA {que}" + (f"  ({detalle})" if detalle else ""))


class PedidoFalso:
    """Lo minimo que le pide FastAPI a un Request: su `json()`."""

    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


tmp = Path(tempfile.mkdtemp(prefix="borradores_"))
panel.BORRADORES_SESIONES = tmp / "borradores_sesiones.json"

print("\n== Guardar y leer ==")
chequear("sin archivo todavia, no hay ningun borrador", panel._borradores() == {})
panel._guardar_borrador("s1", "esto lo dejo a medio escribir")
chequear("el texto se guarda tal cual",
         panel._borradores()["s1"]["texto"] == "esto lo dejo a medio escribir")
chequear("y queda con la hora de cuando se guardo",
         panel._borradores()["s1"]["ts"] > 0)
chequear("el archivo es un JSON legible", isinstance(
    json.loads(panel.BORRADORES_SESIONES.read_text(encoding="utf-8")), dict))
panel._guardar_borrador("s2", "otra conversacion, otro borrador")
chequear("cada conversacion tiene el suyo", sorted(panel._borradores()) == ["s1", "s2"])
panel._guardar_borrador("s1", "cambie de idea")
chequear("volver a guardar pisa el anterior",
         panel._borradores()["s1"]["texto"] == "cambie de idea")

print("\n== Vaciar la caja BORRA el borrador ==")
# ⚠ Esto es lo que apaga la chapa. Guardando la cadena vacia, toda conversacion en la que
# alguna vez escribiste algo se quedaba con el "✎ Borrador" puesto para siempre.
panel._guardar_borrador("s2", "")
chequear("vacio borra la entrada", "s2" not in panel._borradores())
panel._guardar_borrador("s1", "   \n  ")
chequear("solo espacios y saltos tambien borran", "s1" not in panel._borradores())
chequear("y no se lleva puestas las demas", panel._borradores() == {})

print("\n== El tope: es una caja de texto, no un archivo ==")
panel._guardar_borrador("s3", "x" * (panel.BORRADOR_MAX + 500))
chequear(f"se corta en {panel.BORRADOR_MAX} letras",
         len(panel._borradores()["s3"]["texto"]) == panel.BORRADOR_MAX)

print("\n== Guardar despierta a la bandeja ==")
# La lista de conversaciones se cachea 2 s. Si guardar no invalidara ese cache, la chapa
# tardaria hasta dos segundos en aparecer mientras escribis.
panel._SESIONES_ULTIMA["datos"] = {"proyectos": []}
panel._guardar_borrador("s4", "algo")
chequear("guardar invalida el cache de /movil/sesiones",
         panel._SESIONES_ULTIMA["datos"] is None)

print("\n== El endpoint ==")
r = asyncio.run(panel.movil_borrador(PedidoFalso({"sid": "", "texto": "hola"})))
chequear("sin sesion no guarda nada", r.get("ok") is False)
r = asyncio.run(panel.movil_borrador(PedidoFalso({"sid": "nueva-123", "texto": "hola"})))
# ⚠ Una pestaña sin estrenar tiene un id provisorio que no significa nada en otra
# pantalla ni mañana: ese borrador se queda en el navegador donde lo escribiste.
chequear("una charla sin estrenar no se guarda en el servidor", r.get("ok") is False)
chequear("y no dejo basura", "nueva-123" not in panel._borradores())
r = asyncio.run(panel.movil_borrador(PedidoFalso({"sid": "s9", "texto": "medio mensaje"})))
chequear("una conversacion de verdad si", [r.get("ok"), r.get("hay")], [True, True])
chequear("y se lee de vuelta", panel._borradores()["s9"]["texto"] == "medio mensaje")
r = asyncio.run(panel.movil_borrador(PedidoFalso({"sid": "s9", "texto": ""})))
chequear("mandando vacio lo borra", [r.get("ok"), r.get("hay")], [True, False])
chequear("/movil/borradores devuelve el mapa entero",
         panel.movil_borradores() == panel._borradores())

print("\n== El anticipo que viaja en la lista de conversaciones ==")
# ⭐ En la lista va un ANTICIPO, no el texto entero: esa lista se guarda en el navegador
# para que la pantalla aparezca dibujada, y un borrador largo la engordaria al pedo.
largo = "Primera linea del borrador\n\n   y despues sigue " + "muy largo " * 40
panel.BORRADORES_SESIONES.write_text("{}", encoding="utf-8")
panel._guardar_borrador("viva-1", largo)
panel._guardar_borrador("viva-2", "   ")           # vacia: no tiene que marcar nada
listar_real = sesiones_movil.listar
panel._SESIONES_ULTIMA["datos"] = None
try:
    sesiones_movil.listar = lambda: [
        {"proyecto": "proyecto-de-mentira", "cwd": str(tmp), "sesiones": [
            {"id": "viva-1", "nombre": "Una charla"},
            {"id": "viva-2", "nombre": "Otra charla"},
            {"id": "viva-3", "nombre": "Y una sin borrador"}]}]
    d = panel.movil_sesiones()
finally:
    sesiones_movil.listar = listar_real
    panel._SESIONES_ULTIMA["datos"] = None
ses = {s["id"]: s for s in d["proyectos"][0]["sesiones"]}
chequear("la sesion con borrador viene marcada", "borrador" in ses["viva-1"])
chequear("el anticipo no pasa de 120 letras", len(ses["viva-1"]["borrador"]) <= 120)
chequear("y viene en UNA sola linea, sin saltos ni espacios de mas",
         "\n" not in ses["viva-1"]["borrador"] and "  " not in ses["viva-1"]["borrador"])
chequear("empieza por donde empieza el borrador",
         ses["viva-1"]["borrador"].startswith("Primera linea del borrador y despues"))
chequear("una con el borrador vacio NO se marca", "borrador" not in ses["viva-2"])
chequear("y una que nunca tuvo, tampoco", "borrador" not in ses["viva-3"])

for f in tmp.iterdir():
    f.unlink()
tmp.rmdir()

print(f"\n{ok} bien, {fallo} mal")
raise SystemExit(1 if fallo else 0)
