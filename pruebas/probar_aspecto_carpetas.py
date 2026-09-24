"""El icono, el color y el apodo de cada carpeta viven en el SERVIDOR (2026-08-25).

Pedido de Martin: *"que no importa si abro desde el celular, la app de escritorio o desde
otro navegador, siempre tengan estos iconos"*. Y arriba de eso, la condicion que manda:
*"porfa no pierdas lo que ya tengo porque tarde mucho en ponerlos"*.

Esta prueba mira el corazon del asunto sin abrir ningun navegador: importa `panel.py` y le
llama a las funciones, con la ruta del archivo apuntada a un temporal. NO toca el
`aspecto_carpetas.json` de verdad ni los logs de verdad.

    python -m pruebas.probar_aspecto_carpetas
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# La consola de Windows viene en cp1252 y esta prueba esta llena de emojis (son el dato).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import panel                                              # noqa: E402

BIEN, MAL = [], []


def probar(nombre, cond, detalle=""):
    (BIEN if cond else MAL).append(nombre)
    print(("  ok  " if cond else "  MAL ") + nombre + (f"   [{detalle}]" if detalle and not cond else ""))


class Pedido:
    """Lo minimo que los endpoints usan de un Request: `await request.json()`."""

    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


def guardar(**cuerpo):
    return asyncio.run(panel.carpetas_aspecto_guardar(Pedido(cuerpo)))


def sembrar(**cuerpo):
    return asyncio.run(panel.carpetas_aspecto_sembrar(Pedido(cuerpo)))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="aspecto_carp_"))
    panel.ASPECTO_CARPETAS = tmp / "aspecto_carpetas.json"
    panel.LOGS = tmp                                    # los respaldos, tambien al temporal

    print("\n--- Un cambio suelto se guarda y se lee ---")
    guardar(carpeta="Recetas", icono="🎨")
    guardar(carpeta="Recetas", color="azul")
    e = panel._aspecto_carpetas()
    probar("el icono queda guardado", e["carpetas"].get("Recetas", {}).get("icono") == "🎨")
    probar("el color queda guardado", e["carpetas"].get("Recetas", {}).get("color") == "azul")
    probar("guardar el color NO borro el icono",
           e["carpetas"]["Recetas"].get("icono") == "🎨")

    print("\n--- Un campo vacio lo saca, y solo a ese ---")
    guardar(carpeta="Recetas", color="")
    e = panel._aspecto_carpetas()
    probar("el color se fue", "color" not in e["carpetas"].get("Recetas", {}))
    probar("el icono sigue", e["carpetas"]["Recetas"].get("icono") == "🎨")
    guardar(carpeta="Recetas", icono="")
    probar("sin nada adentro, la carpeta desaparece de la lista",
           "Recetas" not in panel._aspecto_carpetas()["carpetas"])

    print("\n--- ⭐ Sembrar NO pisa lo que ya estaba (la regla que pidio Martin) ---")
    guardar(carpeta="Tienda", icono="💵")
    guardar(carpeta="Blog", icono="🔥")
    r = sembrar(origen="compu",
                carpetas={"Tienda": {"icono": "🤖"},          # choca con el 💵 guardado
                          "Estudio": {"icono": "🕴", "apodo": "Estudio SA"}},
                iconosPropios=["🐱", "🍕"])
    e = panel._aspecto_carpetas()
    probar("lo que ya estaba se respeta", e["carpetas"]["Tienda"]["icono"] == "💵")
    probar("lo que faltaba se suma", e["carpetas"]["Estudio"]["icono"] == "🕴")
    probar("el apodo tambien viaja", e["carpetas"]["Estudio"]["apodo"] == "Estudio SA")
    probar("una carpeta ajena al sembrado no se toca",
           e["carpetas"]["Blog"]["icono"] == "🔥")
    probar("los iconos propios se suman al juego",
           e["iconosPropios"] == ["🐱", "🍕"], str(e["iconosPropios"]))

    print("\n--- ⭐ Lo que no coincide queda anotado, no se decide solo ---")
    choques = [c for c in e["choques"] if c["carpeta"] == "Tienda"]
    probar("el choque quedo anotado", len(choques) == 1, str(e["choques"]))
    if choques:
        c = choques[0]
        probar("dice que estaba guardado y que llego",
               c["guardado"] == "💵" and c["llego"] == "🤖" and c["origen"] == "compu",
               json.dumps(c, ensure_ascii=False))

    print("\n--- ⭐ El respaldo con fecha, antes de mezclar nada ---")
    copias = list(tmp.glob("aspecto_carpetas_compu_*.json"))
    probar("quedo una copia de lo que mando el navegador", len(copias) == 1)
    if copias:
        crudo = json.loads(copias[0].read_text(encoding="utf-8"))
        probar("la copia tiene lo original, sin mezclar",
               crudo["carpetas"]["Tienda"]["icono"] == "🤖")

    print("\n--- Sembrar dos veces no duplica el juego de iconos ---")
    sembrar(origen="celu", carpetas={}, iconosPropios=["🐱", "🌵"])
    e = panel._aspecto_carpetas()
    probar("sin repetidos y con el nuevo", e["iconosPropios"] == ["🐱", "🍕", "🌵"],
           str(e["iconosPropios"]))

    print("\n--- Un navegador nuevo (vacio) no rompe nada ---")
    r = sembrar(origen="otro", carpetas={}, iconosPropios=[])
    probar("no siembra nada y avisa", r == {"ok": True, "sembradas": 0, "choques": 0}, str(r))
    probar("y no deja copia al pedo", not list(tmp.glob("aspecto_carpetas_otro_*.json")))

    print("\n--- Basura y excesos: lo que entra se limpia ---")
    guardar(carpeta="Musica", icono="x" * 90, apodo="  Música  ", color=123)
    a = panel._aspecto_carpetas()["carpetas"]["Musica"]
    probar("el icono se recorta", len(a["icono"]) == panel.CARP_MAX_LARGO["icono"])
    probar("el apodo llega sin espacios de sobra", a["apodo"] == "Música")
    probar("un color que no es texto se ignora", "color" not in a)
    guardar(iconosPropios=["🐶"] * 5)
    probar("los iconos propios no se repiten",
           panel._aspecto_carpetas()["iconosPropios"] == ["🐶"])

    print("\n--- El apodo es el ROTULO: la llave sigue siendo la carpeta real ---")
    guardar(carpeta="Clinica", apodo="Clínica Turnos")
    e = panel._aspecto_carpetas()
    probar("se guarda bajo el nombre real de la carpeta", "Clinica" in e["carpetas"])
    probar("y el apodo no crea una carpeta nueva",
           "Clínica Turnos" not in e["carpetas"])

    print("\n--- El archivo es JSON legible, no un mamarracho ---")
    crudo = panel.ASPECTO_CARPETAS.read_text(encoding="utf-8")
    probar("se puede leer con un editor de textos", "\n" in crudo and "Clinica" in crudo)

    print(f"\n{len(BIEN)} bien, {len(MAL)} mal")
    for m in MAL:
        print("   MAL:", m)
    print("temporal:", tmp)
    return 1 if MAL else 0


if __name__ == "__main__":
    sys.exit(main())
