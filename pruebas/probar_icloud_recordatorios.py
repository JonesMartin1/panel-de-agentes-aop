"""Probador: ¿se pueden ver los Recordatorios del iPhone desde esta compu?

Apple NO tiene una API web de Recordatorios. El unico camino oficial es CalDAV
(el mismo protocolo del calendario), donde cada lista de recordatorios es un
"calendario" y cada recordatorio es un VTODO.

⚠ El gran SI-PERO: si la cuenta se paso al Recordatorios "nuevo" (el que Apple
empuja desde iOS 13, con etiquetas, subtareas y listas inteligentes), Apple movio
las listas a un almacen privado y por CalDAV NO se ven — el servidor contesta bien,
te lista los calendarios, y las listas de recordatorios no aparecen o aparecen vacias.
No hay forma de saberlo leyendo documentacion: se prueba y se ve. Eso hace esto.

Como se corre:
    1) en el iPhone/appleid.apple.com generar una "contrasena para aplicacion"
       (Sign-In and Security -> App-Specific Passwords). NO es la clave del Apple ID.
    2) dejarla en el .env del proyecto (que esta fuera de git):
           ICLOUD_USUARIO=tu-apple-id@ejemplo.com
           ICLOUD_CLAVE_APP=xxxx-xxxx-xxxx-xxxx
    3) D:/IA/envs/wpp/python.exe -m pruebas.probar_icloud_recordatorios

No escribe nada: solo mira. Si el veredicto es verde, el camino CalDAV sirve y la
pestana Avisos puede hablar directo con iCloud desde el panel, sin el telefono en el
medio. Si es rojo, va el plan B (un Atajo en el iPhone que le pasa la lista al panel).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # emojis en consola cp1252

from app.rutas import ENV

URL_ICLOUD = "https://caldav.icloud.com"


def main() -> int:
    from dotenv import dotenv_values

    cfg = dotenv_values(ENV) or {}
    usuario = (cfg.get("ICLOUD_USUARIO") or "").strip()
    clave = (cfg.get("ICLOUD_CLAVE_APP") or "").strip()

    if not usuario or not clave:
        print("✖ Falta la configuracion. En", ENV, "tienen que estar estas dos lineas:")
        print("    ICLOUD_USUARIO=tu-apple-id@ejemplo.com")
        print("    ICLOUD_CLAVE_APP=xxxx-xxxx-xxxx-xxxx   (contrasena para aplicacion)")
        return 2

    try:
        import caldav
    except ImportError:
        print("✖ Falta la libreria caldav. Se instala con:")
        print("    D:/IA/envs/wpp/python.exe -m pip install caldav"
              " --trusted-host pypi.org --trusted-host files.pythonhosted.org")
        return 2

    print(f"→ Entrando a iCloud como {usuario} …")
    try:
        cliente = caldav.DAVClient(url=URL_ICLOUD, username=usuario, password=clave)
        principal = cliente.principal()
    except Exception as e:
        print(f"✖ No se pudo entrar: {type(e).__name__}: {e}")
        print("  Si dice 401/403: la contrasena para aplicacion esta mal o vencida.")
        print("  Si dice SSL/certificado: es la laptop que intercepta HTTPS.")
        return 1

    calendarios = principal.calendars()
    print(f"✓ Entro. Apple contesta con {len(calendarios)} colecciones.\n")

    listas_tareas, solo_calendario, con_pendientes = [], [], 0
    for cal in calendarios:
        try:
            soporta = cal.get_supported_components()
        except Exception:
            soporta = []
        nombre = getattr(cal, "name", None) or str(cal.url)
        if "VTODO" in soporta:
            listas_tareas.append(cal)
            try:
                tareas = cal.todos()          # solo las pendientes
            except Exception as e:
                print(f"  📋 {nombre}: acepta tareas pero fallo al leerlas ({type(e).__name__})")
                continue
            con_pendientes += len(tareas)
            print(f"  📋 {nombre}: {len(tareas)} pendiente(s)")
            for t in tareas[:5]:
                v = t.icalendar_component
                print(f"       · {v.get('summary')}"
                      + (f"  (vence {v.get('due').dt})" if v.get("due") else ""))
        else:
            solo_calendario.append(nombre)

    if solo_calendario:
        print(f"\n  (y {len(solo_calendario)} calendario(s) comunes, sin tareas: "
              + ", ".join(solo_calendario[:6]) + ")")

    print()
    if listas_tareas and con_pendientes:
        print("✅ VERDE: se ven las listas de Recordatorios Y su contenido.")
        print("   El panel puede leerlos y escribirlos solo, sin el telefono en el medio.")
        return 0
    if listas_tareas:
        print("🟡 AMARILLO: aparecen listas de tareas pero todas vacias.")
        print("   Puede ser que de verdad no tengas pendientes, o que sea el sintoma")
        print("   clasico de la cuenta 'actualizada' (las listas figuran y el contenido")
        print("   vive en el almacen privado de Apple). Cargá un recordatorio de prueba")
        print("   en el iPhone y volvé a correr esto: si no aparece, es lo segundo.")
        return 0
    print("🔴 ROJO: Apple contesta, pero NO expone ninguna lista de recordatorios.")
    print("   Es la cuenta 'actualizada' al Recordatorios nuevo. Por CalDAV no hay vuelta.")
    print("   Va el plan B: un Atajo en el iPhone que le pasa la lista al panel.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
