"""Radiografía del color escrito a mano en las pantallas.

No prueba nada: cuenta. Sirve para contestar UNA pregunta antes de meterse con el
modo claro — ¿los grises de las pantallas son una paleta chica repetida (y entonces
se pueden agrupar en unos pocos roles) o son cientos de valores únicos, cada uno
usado una vez (y entonces no hay roles que extraer)?

    python -m pruebas.mapa_de_grises

Agrupa por VALOR y por PROPIEDAD CSS, porque el mismo gris no significa lo mismo
como `background` que como `color`: en el modo claro uno tiene que irse al blanco
y el otro al negro. Saltea lo que no es color de interfaz: las entidades HTML
(`&#127916;` matchea un hex y no lo es), la paleta de dibujo de la pizarra y los
colores de las notas, que son colores de OBJETO y no cambian con el tema.
"""
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from app.rutas import RAIZ  # noqa: E402

ARCHIVOS = [RAIZ / 'panel.py', RAIZ / 'app' / 'estaticos' / 'sesiones.html']

# Bloques que NO son aspecto: colores de objeto que el tema no toca.
SALTEAR_BLOQUE = re.compile(
    r'(COLORES_NOTA\s*=.*?\]|PALETA\w*\s*=.*?\]|conic-gradient\([^)]*\))', re.S)
HEX = re.compile(r'#[0-9a-fA-F]{6}\b')
ENTIDAD = re.compile(r'&#\d')


def luz(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return .2126 * r + .7152 * g + .0722 * b


def satura(h):
    v = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return max(v) - min(v)


def propiedad(linea, pos):
    """La propiedad CSS a la que pertenece este color, mirando para atrás."""
    izq = linea[:pos]
    m = re.findall(r'([a-zA-Z-]+)\s*:\s*[^;:]*$', izq)
    return m[-1].lower() if m else '?'


def main():
    porvalor = Counter()
    porprop = defaultdict(Counter)
    donde = defaultdict(Counter)
    for arch in ARCHIVOS:
        txt = arch.read_text(encoding='utf-8')
        txt = SALTEAR_BLOQUE.sub(lambda m: ' ' * len(m.group(0)), txt)
        for linea in txt.splitlines():
            for m in HEX.finditer(linea):
                if ENTIDAD.search(linea[max(0, m.start() - 2):m.start() + 1]):
                    continue
                h = m.group(0).lower()
                p = propiedad(linea, m.start())
                porvalor[h] += 1
                porprop[h][p] += 1
                donde[h][arch.name] += 1

    total = sum(porvalor.values())
    print(f'{total} colores escritos a mano, {len(porvalor)} valores distintos\n')
    acum = 0
    print(f'{"color":9} {"veces":>5} {"acum%":>6}  {"luz":>4} {"sat":>4}  propiedades')
    for h, n in porvalor.most_common():
        acum += n
        props = ' '.join(f'{p}×{c}' for p, c in porprop[h].most_common(3))
        print(f'{h:9} {n:5} {100*acum/total:5.1f}%  {luz(h):.2f} {satura(h):.2f}  {props}')

    grises = [h for h in porvalor if satura(h) < .18]
    print(f'\n{len(grises)} de {len(porvalor)} valores son casi grises (sat<.18); '
          f'suman {sum(porvalor[h] for h in grises)} de {total} usos')
    n20 = sum(n for _, n in porvalor.most_common(20))
    print(f'los 20 más usados cubren {100*n20/total:.0f}% de los usos')

    # ¿Y si en vez de 196 valores hubiera K peldaños de luminosidad? El modo claro
    # necesita que cada gris tenga un rol ("fondo hundido", "texto apagado") y el rol
    # se puede leer de la luminosidad. Lo que hay que saber es cuánto se movería cada
    # color al redondearlo al peldaño más cercano: si el movimiento es imperceptible,
    # el modo oscuro queda igual que hoy y el claro sale de invertir la escala.
    # Umbral: 0.03 de luminosidad relativa es donde se empieza a notar un salto de gris.
    print('\n¿cuánto se movería cada gris al redondearlo a K peldaños?')
    print(f'{"K":>3} {"error medio":>11} {"peor":>6} {"usos que se notarían":>21}')
    for k in (8, 12, 16, 24, 32):
        pasos = [i / (k - 1) for i in range(k)]
        peor, suma, notorios = 0, 0, 0
        for h, n in porvalor.items():
            if satura(h) >= .30:
                continue                     # los saturados son acento, no escala
            e = min(abs(luz(h) - p) for p in pasos)
            peor = max(peor, e)
            suma += e * n
            if e > .03:
                notorios += n
        usos = sum(n for h, n in porvalor.items() if satura(h) < .30)
        print(f'{k:>3} {suma/usos:11.3f} {peor:6.3f} {notorios:12} de {usos}')


if __name__ == '__main__':
    main()
