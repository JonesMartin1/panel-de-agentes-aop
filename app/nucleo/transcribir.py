"""
Transcriptor CLI de audios/videos - Whisper local en la RTX 4070.

Uso (desde la carpeta del proyecto, con -m para que resuelva el paquete `app`):
    python -m app.nucleo.transcribir "C:\\ruta\\archivo.ogg"
    python -m app.nucleo.transcribir "C:\\ruta\\video.mp4"
    python -m app.nucleo.transcribir "archivo.ogg" --analizar   (agrega analisis con Gemini)
    python -m app.nucleo.transcribir "archivo.ogg" --analizar --perfil ventas
    python -m app.nucleo.transcribir --perfiles   (lista los perfiles disponibles)

Lo mas comodo es arrastrar el archivo sobre lanzadores/Transcribir (arrastrar aca).bat

Deja los resultados en resultados/<nombre>/
"""

import sys
import json
from app.nucleo import core


def main():
    argv = sys.argv[1:]
    if "--perfiles" in argv:
        from app.nucleo import analizar_gemini
        print("Perfiles disponibles:", ", ".join(analizar_gemini.perfiles_disponibles()))
        return

    perfil = "generico"
    if "--perfil" in argv:
        i = argv.index("--perfil")
        if i + 1 < len(argv):
            perfil = argv[i + 1]
            del argv[i:i + 2]
        else:
            del argv[i]

    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print('Uso: python transcribir.py "<ruta al audio o video>" [--analizar] [--perfil NOMBRE]')
        sys.exit(1)

    datos, out = core.procesar_archivo(args[0])

    print("\nTRANSCRIPCION:")
    print(" ", datos["transcripcion"] or "(no se detecto voz)")

    if "--analizar" in flags:
        print(f"\nAnalizando con Gemini (perfil: {perfil})...")
        from app.nucleo import analizar_gemini
        analisis = analizar_gemini.analizar(datos, perfil=perfil)
        datos["analisis_ia"] = analisis
        with open(out / "datos.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print("\n" + analizar_gemini.formato_legible(analisis))

    print(f"\n=== LISTO ===\n  Carpeta: {out}")


if __name__ == "__main__":
    main()
