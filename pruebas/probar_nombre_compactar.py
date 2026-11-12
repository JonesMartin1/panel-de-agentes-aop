"""Compactar (o mudar de cerebro) no le borra a la charla el nombre ni el subproyecto.

Queja de Martín el 2026-11-11: "si compacto una charla, pierde el lindo nombre que le
había puesto". El alias y el subproyecto se guardan por id, y la continuación nace con
id nuevo. `_marcar_continuacion` ahora se los pasa (`_heredar_etiquetas`).

Corre sobre archivos temporales: no toca la configuración real, ni servicios, ni tokens.

    python -m pruebas.probar_nombre_compactar           # los chequeos
    python -m pruebas.probar_nombre_compactar --mutar   # sin la herencia, tienen que caer
"""
import json
import sys
import tempfile
from pathlib import Path

from app.voz import sesiones_movil as sm

FALLAS = []


def ver(cond, que):
    print(("  ok   " if cond else "  FALLA ") + que)
    if not cond:
        FALLAS.append(que)


def correr():
    FALLAS.clear()
    tmp = Path(tempfile.mkdtemp(prefix="nombre_compactar_"))
    nombres, subs, ajustes = tmp / "n.json", tmp / "s.json", tmp / "a.json"
    viejos = (sm.NOMBRES_SESIONES, sm.SUBPROYECTOS_SESIONES, sm.AJUSTES_SESIONES)
    sm.NOMBRES_SESIONES, sm.SUBPROYECTOS_SESIONES, sm.AJUSTES_SESIONES = nombres, subs, ajustes
    try:
        ajustes.write_text("{}", encoding="utf-8")
        nombres.write_text(json.dumps({"viejo": "🧾Presupuestos", "otra": "Propio"}),
                           encoding="utf-8")
        subs.write_text(json.dumps({"viejo": "Descalzo"}), encoding="utf-8")

        sm._marcar_continuacion("viejo", "nuevo")
        n = json.loads(nombres.read_text(encoding="utf-8"))
        s = json.loads(subs.read_text(encoding="utf-8"))
        a = json.loads(ajustes.read_text(encoding="utf-8"))
        ver(n.get("nuevo") == "🧾Presupuestos", "la continuación hereda el nombre (emoji incluido)")
        ver(s.get("nuevo") == "Descalzo", "la continuación hereda el subproyecto")
        ver(n.get("viejo") == "🧾Presupuestos", "la vieja conserva su nombre")
        ver(a.get("viejo", {}).get("sigue_en") == "nuevo", "la marca sigue_en se escribe igual")

        # Dos compactaciones seguidas: el nombre viaja por toda la cadena.
        sm._marcar_continuacion("nuevo", "tercera")
        n = json.loads(nombres.read_text(encoding="utf-8"))
        ver(n.get("tercera") == "🧾Presupuestos", "con dos compactaciones el nombre llega a la tercera")

        # Si la nueva ya tiene nombre propio, no se pisa.
        sm._marcar_continuacion("viejo", "otra")
        n = json.loads(nombres.read_text(encoding="utf-8"))
        ver(n.get("otra") == "Propio", "no pisa un nombre que la nueva ya tenía")

        # Sin nombre en la vieja, no inventa nada.
        sm._marcar_continuacion("sin_nombre", "hija")
        n = json.loads(nombres.read_text(encoding="utf-8"))
        s = json.loads(subs.read_text(encoding="utf-8"))
        ver("hija" not in n and "hija" not in s, "una charla sin nombre no le deja nada a la hija")

        # Sin archivo de subproyectos todavía: no rompe y no lo crea.
        subs.unlink()
        sm._marcar_continuacion("viejo", "cuarta")
        ver(not subs.exists(), "sin archivo de subproyectos no crea uno")
        n = json.loads(nombres.read_text(encoding="utf-8"))
        ver(n.get("cuarta") == "🧾Presupuestos", "y el nombre igual pasa")
    finally:
        sm.NOMBRES_SESIONES, sm.SUBPROYECTOS_SESIONES, sm.AJUSTES_SESIONES = viejos
    return len(FALLAS)


if __name__ == "__main__":
    if "--mutar" in sys.argv:
        original = sm._heredar_etiquetas
        sm._heredar_etiquetas = lambda viejo, nuevo: None
        try:
            caidas = correr()
        finally:
            sm._heredar_etiquetas = original
        print("\nmutación (sin herencia): %s" % ("CAZADA, cayeron %d" % caidas if caidas
                                                  else "NO CAZADA: la prueba es un adorno"))
        sys.exit(0 if caidas else 1)
    fallas = correr()
    print("\n%s" % ("todo bien" if not fallas else "%d fallas" % fallas))
    sys.exit(1 if fallas else 0)
