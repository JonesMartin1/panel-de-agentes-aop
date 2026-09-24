"""Pasar los colores escritos a mano de las pantallas a variables con respaldo.

    #232a35   ->   var(--c232a35,#232a35)

Se corrio una vez, el 2026-08-29, para que exista el modo claro. Queda guardado porque es
la unica forma de auditar QUE se convirtio y que no, y de repetirlo si alguna pantalla
vuelve a llenarse de colores a mano.

⭐ Por que con respaldo y con el color adentro del nombre. Las dos cosas son la clave:

  1. **El respaldo hace que el modo oscuro quede idéntico por construccion.** Si nadie
     define `--c232a35`, `var()` usa lo que hay despues de la coma, que es exactamente el
     color de siempre. O sea: mientras el tema sea oscuro, no cambia un solo pixel, y no
     hace falta creerme — sale de como funciona `var()`.
  2. **El nombre lleva el color adentro**, asi que `aspecto.js` no necesita ninguna tabla:
     en modo claro barre las hojas de estilo, encuentra los `--cXXXXXX` que hay y le
     calcula a cada uno su version clara. Un color nuevo que alguien escriba mañana con
     esta forma entra solo.

⚠ Lo que NO se toca, y por que:
  - `aspecto.js`: ahi viven las definiciones. Convertirlo seria morderse la cola (ya paso
     una vez ese mismo dia con las sombras: quedo `--sombra-0:var(--sombra-0)`).
  - Los colores que NO estan en una propiedad CSS: un `ctx.fillStyle` de la pizarra, un
     `fill="#..."` de un SVG, un color de dato. `var()` no existe fuera del CSS, y ahi
     poner la variable rompe el dibujo en vez de vestirlo. Se reportan al final.
  - La paleta de DIBUJO de la pizarra y `COLORES_NOTA`: son colores de objeto, no de
     interfaz. Un papelito amarillo tiene que seguir amarillo en cualquier tema.
  - Las entidades HTML: `&#127916;` matchea un hex y no lo es.

    python -m pruebas.pasar_colores_a_variables --simular   # no escribe nada
    python -m pruebas.pasar_colores_a_variables
"""
import re
import sys
from collections import Counter

from app.rutas import RAIZ

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARCHIVOS = ["panel.py", "app/estaticos/sesiones.html"]
HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
# Bloques enteros que quedan afuera: colores de objeto, no de interfaz.
AFUERA = re.compile(r"(COLORES_NOTA\s*=.*?\]|PALETA\w*\s*=.*?\]|conic-gradient\([^)]*\))", re.S)


def propiedad(linea, pos):
    """La propiedad CSS a la que pertenece este color, mirando para atras en la linea."""
    m = re.findall(r"([a-zA-Z-]+)\s*:\s*[^;:]*$", linea[:pos])
    return m[-1].lower() if m else ""


def convertible(linea, m):
    """¿Este color esta en una propiedad CSS donde `var()` funciona?"""
    antes = linea[max(0, m.start() - 2):m.start() + 1]
    if re.search(r"&#\d", antes):
        return False, "entidad HTML"
    # ⚠⚠ Si ya es el respaldo de una variable, NO se vuelve a convertir. Sin esto, una
    # segunda corrida escribe `var(--cX,var(--cX,#x))` y encima le pisa los arreglos a
    # mano — los colores que a proposito quedaron literales (texto claro sobre un boton
    # de color) volvian a engancharse y se daban vuelta de nuevo. Paso el 2026-08-29.
    if re.search(r"var\(--c[0-9a-f]{6},\s*$", linea[:m.start()]):
        return False, "ya es el respaldo de una variable"
    # Y un color dejado literal a mano se respeta: se marca con este comentario al lado.
    if "no-tema" in linea:
        return False, "marcado como no-tema"
    # En un atributo de SVG (fill="#fff") `var()` no vale: es atributo, no CSS.
    izq = linea[:m.start()]
    if re.search(r"(fill|stroke|stop-color|bgcolor|content)\s*=\s*[\"']?$", izq):
        return False, "atributo SVG/HTML"
    p = propiedad(linea, m.start())
    if not p:
        return False, "no esta en una propiedad CSS"
    # `--algo:#fff` es una definicion de variable: puede convertirse igual, pero si el
    # nombre de la variable es el mismo que generariamos, se muerde la cola.
    if p.startswith("--") and p[3:] == m.group(1).lower():
        return False, "se definiria a si misma"
    return True, p


# Los colores translucidos, que son otro problema del mismo tipo: `rgba(255,255,255,.06)`
# es un separador que se ve sobre un fondo oscuro y desaparece sobre uno claro. Se pasan a
# la MISMA familia de variables, pero en su version "tres numeros":
#
#     rgba(255,255,255,.06)  ->  rgba(var(--cffffff-rgb,255,255,255),.06)
#
# ⚠ El negro puro queda AFUERA: `rgba(0,0,0,.5)` es una sombra, y darla vuelta la
# convertiria en un halo blanco alrededor de cada caja.
RGBA = re.compile(r"rgba\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3}),\s*([^)]+)\)")


def convertir_rgba(txt):
    n = [0]

    def rep(m):
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        if r == g == b == 0:
            return m.group(0)                    # es una sombra: no se toca
        if max(r, g, b) > 255:
            return m.group(0)
        hx = "".join(f"{v:02x}" for v in (r, g, b))
        n[0] += 1
        return f"rgba(var(--c{hx}-rgb,{r},{g},{b}),{m.group(4)})"

    return RGBA.sub(rep, txt), n[0]


def main():
    simular = "--simular" in sys.argv
    total, saltados = 0, Counter()
    ejemplos = {}
    usados = set()
    for arch in ARCHIVOS:
        p = RAIZ / arch
        txt = p.read_text(encoding="utf-8")
        # Los bloques de afuera se tapan con espacios para que las posiciones no se muevan.
        tapado = AFUERA.sub(lambda m: " " * len(m.group(0)), txt)
        salida, n = [], 0
        for i, linea in enumerate(txt.splitlines(keepends=True)):
            lt = tapado.splitlines(keepends=True)[i] if i < len(tapado.splitlines()) else linea
            trozo, ultimo = [], 0
            for m in HEX.finditer(linea):
                # Si el bloque estaba tapado, este color no existe para nosotros.
                if lt[m.start():m.end()] != m.group(0):
                    continue
                ok, motivo = convertible(linea, m)
                if not ok:
                    saltados[motivo] += 1
                    ejemplos.setdefault(motivo, f"{arch}:{i+1}  {linea.strip()[:70]}")
                    continue
                col = m.group(1).lower()
                usados.add(col)
                trozo.append(linea[ultimo:m.start()])
                trozo.append(f"var(--c{col},#{col})")
                ultimo = m.end()
                n += 1
            trozo.append(linea[ultimo:])
            salida.append("".join(trozo))
        nuevo, nrgba = convertir_rgba("".join(salida))
        total += n
        print(f"{arch}: {n} colores a variable, {nrgba} translucidos")
        if not simular:
            p.write_text(nuevo, encoding="utf-8")

    print(f"\n{total} convertidos, {len(usados)} colores distintos")
    print("\nsalteados a proposito:")
    for motivo, n in saltados.most_common():
        print(f"  {n:4}  {motivo}")
        print(f"        ej: {ejemplos[motivo]}")
    if simular:
        print("\n(--simular: no se escribio nada)")


if __name__ == "__main__":
    main()
