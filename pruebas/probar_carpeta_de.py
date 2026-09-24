r"""La ruta de un proyecto -> la carpeta donde Claude Code guarda sus .jsonl.

Se escribio despues del bug del 2026-08-17: "Proyectos Personales" tiene un ESPACIO,
`carpeta_de()` cambiaba por guion solo los dos puntos, las barras y los puntos, y la
pantalla de sesiones mostraba "0 conversaciones" con las charlas ahi mismo. Claude Code
aplana cambiando TODO lo que no sea letra, numero o guion.

    python -m pruebas.probar_carpeta_de
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.voz import seguir

# ruta real -> nombre de carpeta que usa Claude Code (todos verificados en el disco)
CASOS = [
    (r"C:\Proyectos Personales\Mi-Landing", "C--Proyectos-Personales-Mi-Landing"),
    (r"D:\IA\wpp-transcriptor", "D--IA-wpp-transcriptor"),
    (r"c:\EspacioDeTrabajo\Next.js", "c--EspacioDeTrabajo-Next-js"),
    (r"c:\EspacioDeTrabajo\Diseño\SistemaDeGestion",
     "c--EspacioDeTrabajo-Dise-o-SistemaDeGestion"),
    (r"c:\EspacioDeTrabajo\Clinica\Turnos-clinica", "c--EspacioDeTrabajo-Clinica-Turnos-clinica"),
]

ok = fallas = 0
for ruta, esperado in CASOS:
    da = seguir.carpeta_de(ruta).name
    if da == esperado:
        ok += 1
        print(f"  OK   {ruta}")
    else:
        fallas += 1
        print(f"  MAL  {ruta}\n       esperaba {esperado}\n       dio      {da}")

# Y que de verdad encuentre las conversaciones del proyecto del bug, si sigue existiendo.
carpeta = seguir.carpeta_de(r"C:\Proyectos Personales\Mi-Landing")
if carpeta.is_dir():
    filas = seguir.sesiones_de(r"C:\Proyectos Personales\Mi-Landing", horas=24 * 30)
    if filas:
        ok += 1
        print(f"  OK   encuentra {len(filas)} conversación(es) en Mi-Landing")
        for f in filas:
            print(f"       · {f['nombre']} — {f['detalle']}")
    else:
        fallas += 1
        print("  MAL  la carpeta existe pero no lista ninguna conversación")
else:
    print("  --   Mi-Landing no está en el disco: se saltea ese chequeo")

print(f"\n{ok} bien, {fallas} mal")
sys.exit(1 if fallas else 0)
