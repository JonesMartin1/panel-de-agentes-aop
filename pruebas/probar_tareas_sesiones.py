"""La lista de tareas de una sesion (TodoWrite), en vivo en la pantalla.

Pedido de Martin el 2026-08-20: ver la lista de tareas que el agente se anota y
va tildando mientras trabaja, como en Claude Code de VS Code. El turno captura
cada TodoWrite que pasa por el stream, guarda la ultima foto en TAREAS y la
pantalla la dibuja como tarjetita al final del hilo (viaja adentro de
/movil/chat, campo `tareas`, junto con la pregunta con opciones).

Aca no se habla con Claude de verdad: se prueban las piezas con datos falsos.

    python -m pruebas.probar_tareas_sesiones
"""
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


class VivaFalsa:
    def __init__(self, cwd, sid):
        self.cwd, self.sid = cwd, sid
        self.proc = None

    def clave(self):
        return sm._clave(self.cwd, self.sid)


try:
    print("\n--- Guardar la foto de la lista ---")
    clave = sm._clave("D:/x", "s1")
    sm._guardar_tareas(clave, [
        {"content": "Leer el archivo", "activeForm": "Leyendo el archivo",
         "status": "completed"},
        {"content": "Tocar el codigo", "activeForm": "Tocando el codigo",
         "status": "in_progress"},
        {"content": "Correr las pruebas", "activeForm": "Corriendo las pruebas",
         "status": "pending"}])
    t = sm.tareas_de("D:/x", "s1")
    probar("la lista llega entera", t and len(t["lista"]) == 3)
    probar("con su hora", t and t.get("hora", 0) > 0)
    probar("el texto y el estado", t and t["lista"][0] == {
        "texto": "Leer el archivo", "activo": "Leyendo el archivo",
        "estado": "completed"})
    probar("la fila en curso trae el gerundio",
           t and t["lista"][1]["activo"] == "Tocando el codigo")

    print("\n--- Lo raro no rompe ---")
    sm._guardar_tareas(clave, [
        {"content": "Algo", "status": "volando"},        # estado inventado
        "no soy un dict",                                 # basura en el medio
        {"content": "", "status": "pending"},             # sin texto: se salta
        {"content": "x" * 999, "status": "pending"}])     # texto larguisimo
    t = sm.tareas_de("D:/x", "s1")
    probar("la basura se filtra", t and len(t["lista"]) == 2)
    probar("el estado inventado cae a pendiente",
           t and t["lista"][0]["estado"] == "pending")
    probar("el texto larguisimo se recorta", t and len(t["lista"][1]["texto"]) == 300)

    print("\n--- Una lista vacia la borra de la pantalla ---")
    sm._guardar_tareas(clave, [])
    probar("ya no hay tarjeta", sm.tareas_de("D:/x", "s1") is None)
    probar("y sin lista tampoco", sm.tareas_de("D:/x", "sin-nada") is None)

    print("\n--- La lista se muda cuando la sesion cambia de id ---")
    # El primer turno de una charla nueva guarda bajo "nueva:<carpeta>"; al nacer
    # el id, la tarjeta tiene que seguir a la sesion y no quedar huerfana.
    viva = VivaFalsa("D:/x", "")
    sm._guardar_tareas(viva.clave(), [{"content": "Nacer", "status": "pending"}])
    probar("antes de nacer se ve por la carpeta",
           sm.tareas_de("D:/x", "") is not None)
    sm._remapear(viva, "sid-nuevo")
    probar("despues de nacer se ve por el id",
           sm.tareas_de("D:/x", "sid-nuevo") is not None)
    probar("y la clave vieja quedo libre", sm.tareas_de("D:/x", "") is None)

    print("\n--- El turno captura los TodoWrite del stream ---")
    fuente = Path(sm.__file__).read_text(encoding="utf-8")
    probar("mira los mensajes del asistente", 'elif t == "assistant":' in fuente)
    probar("busca la herramienta TodoWrite", '"TodoWrite"' in fuente)
    probar("y guarda la foto", "_guardar_tareas(clave," in fuente)

    print("\n--- El endpoint y las pantallas ---")
    panel = (Path(sm.__file__).parents[2] / "panel.py").read_text(encoding="utf-8")
    compu = (Path(sm.__file__).parents[2] / "app" / "estaticos" /
             "sesiones.html").read_text(encoding="utf-8")
    probar("las tareas viajan en /movil/chat",
           '"tareas": sesiones_movil.tareas_de(cwd, sid)' in panel)
    for nombre, src in (("celular", panel), ("compu", compu)):
        probar("tarjeta de tareas en la pantalla %s" % nombre, "htmlTareas" in src)
        probar("la pantalla %s lee d.tareas" % nombre, "d.tareas" in src)
        probar("estilo de la fila en curso en %s" % nombre, ".tFila.haciendo" in src)
    probar("el celular la cachea entre repintados", "cacheTareas" in panel)
finally:
    sm.TAREAS.clear()

print("\n%d bien, %d mal" % (ok, fallo))
raise SystemExit(1 if fallo else 0)
