"""Tu mensaje llega al cerebro con los saltos de linea que escribiste, ni uno mas.

El bug (captura de Martin del 2026-08-22, charla del Portafolio): el mensaje se veia
DOS veces en `/sesiones`. En el rollout de Codex estaba una sola vez, pero guardado
como `Listo, ahora si\\r\\r\\n\\r\\r\\nCarga el hunyuan...`: el navegador manda CRLF y
Windows le sumaba otro \\r al escribirle al CLI. Como la burbuja provisoria se borra
comparando tu texto con el que aparece en el hilo, nunca coincidian y quedaba pegada.

No gasta un token: no habla con ningun CLI.
"""
import re
from pathlib import Path

from app.rutas import RAIZ
from app.voz import sesiones_movil as sm

bien = malo = 0


def ok(cond, que):
    global bien, malo
    if cond:
        bien += 1
        print("  ok   ", que)
    else:
        malo += 1
        print("  MAL  ", que)


# --- el texto que de verdad llego ese dia -------------------------------------------
CRUDO = "Listo, ahora si\r\n\r\nCarga el hunyuan y intenta crear el eva"
ESCRITO = "Listo, ahora si\n\nCarga el hunyuan y intenta crear el eva"

print("Limpieza de saltos")
ok(sm._saltos_limpios(CRUDO) == ESCRITO, "el CRLF del navegador queda como lo escribiste")
ok(sm._saltos_limpios("a\r\r\nb") == "a\n\nb", "el \\r\\r\\n ya guardado tambien se limpia")
ok(sm._saltos_limpios("viejo\rmac") == "viejo\nmac", "un \\r suelto es un salto igual")
ok(sm._saltos_limpios("sin saltos") == "sin saltos", "un renglon solo no se toca")
ok(sm._saltos_limpios(None) == "", "texto vacio no explota")
ok("\r" not in sm._saltos_limpios(CRUDO), "no queda ningun \\r")

# --- `mandar()` limpia antes de repartir a cualquiera de los dos cerebros -----------
# ⚠ Se falsean los DOS caminos antes de llamar a nada: un id que `es_codex` no conozca
# cae en el de Claude y arranca un CLI de verdad.
print("\nLa puerta de entrada de los dos cerebros")
llego = {}


class VivaFalsa:
    class _Turno:
        def acquire(self, timeout=0):
            return True

        def release(self):
            pass

    turno = _Turno()


def _anotar(quien):
    def _f(*a, **k):
        llego[quien] = a[2] if quien == "codex" else a[1]
        return ("listo", None)
    return _f


viejos = (sm.es_codex, sm.codex_mandar, sm._conseguir_viva, sm._turno)
try:
    sm.es_codex = lambda s: s == "charla-de-codex"
    sm.codex_mandar = _anotar("codex")
    sm._conseguir_viva = lambda *a, **k: VivaFalsa()
    sm._turno = _anotar("claude")

    sm.mandar(RAIZ, "charla-de-codex", CRUDO)
    ok(llego.get("codex") == ESCRITO, "a Codex le llega el texto limpio")

    sm.mandar(RAIZ, "charla-de-claude", CRUDO)
    ok(llego.get("claude") == ESCRITO, "a Claude le llega el texto limpio")
finally:
    sm.es_codex, sm.codex_mandar, sm._conseguir_viva, sm._turno = viejos

# --- el cinturon de la pantalla ------------------------------------------------------
# `suelto()` es lo que decide si la burbuja provisoria se borra. Aunque algo vuelva a
# ensuciar el texto, dos mensajes que solo difieren en espacios tienen que dar iguales.
# ⚠ El resto de esa logica (cuando se borra el eco) se prueba CORRIENDOLA de verdad en
# `probar_eco_mensaje.py`, contra las dos pantallas. Aca solo se mira que la limpieza
# siga estando en las dos.
print("\nEl cinturon de las dos pantallas")
for nombre, texto in (
        ("/sesiones", (Path(RAIZ) / "app" / "estaticos" / "sesiones.html")
                      .read_text(encoding="utf-8")),
        ("/movil", (Path(RAIZ) / "panel.py").read_text(encoding="utf-8"))):
    m = re.search(r"const suelto = [\s\S]{0,300}?;", texto)
    ok(m is not None, "%s: sigue existiendo `suelto()`" % nombre)
    if m:
        ok(r"\s+" in m.group(0), "%s: aplasta los espacios antes de comparar" % nombre)
        ok(r"\[[^\]]*\]" in m.group(0), "%s: saca el corchete de contexto" % nombre)

print("\n%d en verde, %d en rojo" % (bien, malo))
if malo:
    raise SystemExit(1)
