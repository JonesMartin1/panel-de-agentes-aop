"""Dibuja el icono de Laura para la pantalla de inicio del iPhone.

Se corre UNA vez y deja `app/estaticos/icono_laura.png` (180x180, que es la medida
que pide Apple para el apple-touch-icon). Queda versionado, asi que no hace falta
volver a correrlo salvo que se quiera cambiar el dibujo.

El dibujo: fondo oscuro como el del panel y cuatro barras de onda de voz en el
celeste de la casa. Sin transparencia ni esquinas redondeadas a proposito — iOS
recorta y redondea solo, y si el fondo es transparente lo rellena de negro.

    python -m pruebas.hacer_icono_laura
"""
from PIL import Image, ImageDraw

from app.rutas import ESTATICOS

LADO = 180
FONDO = (11, 13, 18)         # #0b0d12, el fondo del panel
CELESTE = (94, 184, 255)     # #5eb8ff, el azul de la casa
SUAVE = (42, 110, 168)       # #2a6ea8, para las barras de los costados


def main():
    # Se dibuja al triple y se achica: los bordes redondeados quedan sin escalones.
    esc = 3
    img = Image.new("RGB", (LADO * esc, LADO * esc), FONDO)
    d = ImageDraw.Draw(img)
    centro = LADO * esc / 2
    ancho = 16 * esc                 # grosor de cada barra
    hueco = 12 * esc                 # aire entre barras
    # La onda: alta en el medio, corta en las puntas. Ojo con el alto — es el radio
    # (se dibuja para arriba y para abajo del centro), y ademas iOS le recorta las
    # esquinas al icono, asi que la barra mas alta no puede pasar de ~66.
    altos = [34, 62, 46, 24]
    colores = [SUAVE, CELESTE, CELESTE, SUAVE]
    total = len(altos) * ancho + (len(altos) - 1) * hueco
    x = centro - total / 2
    for alto, color in zip(altos, colores):
        h = alto * esc
        d.rounded_rectangle([x, centro - h, x + ancho, centro + h],
                            radius=ancho / 2, fill=color)
        x += ancho + hueco
    img = img.resize((LADO, LADO), Image.LANCZOS)
    destino = ESTATICOS / "icono_laura.png"
    img.save(destino, "PNG")
    print("icono guardado en", destino.name, img.size)


if __name__ == "__main__":
    main()
