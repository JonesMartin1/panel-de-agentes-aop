"""Prueba del puente de Avisos (los Recordatorios del iPhone).

Corre contra un archivo de juguete, NO contra el de verdad: lo primero que hace es
apuntar `avisos.AVISOS` a un temporal. Si esto tocara el archivo real, una corrida de
la prueba le borraria a Martin la cola de cosas que todavia no llegaron al telefono.

    D:/IA/envs/wpp/python.exe -m pruebas.probar_avisos
"""
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # emojis en consola cp1252

from app.nucleo import avisos

# ⚠ ANTES de cualquier llamada: el modulo importo AVISOS a su propio espacio de
# nombres, asi que se pisa aca y todo lo demas escribe en el temporal.
_TMP = Path(tempfile.mkdtemp(prefix="avisos_prueba_"))
avisos.AVISOS = _TMP / "avisos.json"

_bien = _mal = 0


def ok(condicion, que, detalle=""):
    global _bien, _mal
    if condicion:
        _bien += 1
        print("  ✓", que)
    else:
        _mal += 1
        print("  ✗", que, "->", detalle)


def limpiar():
    if avisos.AVISOS.exists():
        avisos.AVISOS.unlink()


# ---------------------------------------------------------------- leer lo que sube

print("\n[1] Lo que manda el telefono se entiende")
limpiar()
avisos.sincronizar(
    "Comprar pan|2026-08-18T09:00:00|Personal\n"
    "Llamar al contador|2026-08-18T15:30:00|Trabajo\n"
    "Sin fecha ni lista||\n"
)
e = avisos.estado()
ok(len(e["espejo"]) == 3, "entraron los tres", len(e["espejo"]))
nombres = [r["nombre"] for r in e["espejo"]]
ok("Comprar pan" in nombres, "el nombre sale limpio", nombres)
pan = [r for r in e["espejo"] if r["nombre"] == "Comprar pan"][0]
ok(pan["lista"] == "Personal", "la lista viene con el recordatorio", pan["lista"])
ok(pan["vence_iso"] == "2026-08-18T09:00:00", "la fecha ISO se entiende", pan["vence_iso"])
suelto = [r for r in e["espejo"] if r["nombre"] == "Sin fecha ni lista"][0]
ok(suelto["vence"] is None and suelto["lista"] is None,
   "sin fecha ni lista no inventa nada", suelto)
ok(e["espejo"][0]["nombre"] == "Comprar pan",
   "ordena por fecha: lo que vence primero, arriba", e["espejo"][0]["nombre"])
ok(e["espejo"][-1]["nombre"] == "Sin fecha ni lista",
   "lo que no tiene fecha va al final", e["espejo"][-1]["nombre"])

print("\n[2] Un nombre con | adentro no rompe la linea")
limpiar()
# ⚠ El caso que rompe un split ingenuo: el separador aparece DENTRO del nombre.
avisos.sincronizar("Revisar el archivo a|b.txt|2026-08-19T10:00:00|Trabajo\n")
r = avisos.estado()["espejo"][0]
ok(r["nombre"] == "Revisar el archivo a|b.txt", "el nombre queda entero", r["nombre"])
ok(r["lista"] == "Trabajo", "y la lista sigue siendo la correcta", r["lista"])

print("\n[3] Una fecha en otro formato no se pierde")
limpiar()
avisos.sincronizar("Dentista|18/08/2026 14:00|Personal\nRaro|mañana a la tarde|Personal\n")
esp = {r["nombre"]: r for r in avisos.estado()["espejo"]}
ok(esp["Dentista"]["vence_iso"] == "2026-08-18T14:00:00",
   "entiende el formato argentino", esp["Dentista"]["vence_iso"])
ok(esp["Raro"]["vence_iso"] is None and esp["Raro"]["vence"] == "mañana a la tarde",
   "lo que no entiende lo guarda crudo igual", esp["Raro"])

print("\n[4] El espejo se reemplaza entero, no se acumula")
limpiar()
avisos.sincronizar("Uno||\nDos||\n")
avisos.sincronizar("Tres||\n")
e = avisos.estado()
ok(len(e["espejo"]) == 1 and e["espejo"][0]["nombre"] == "Tres",
   "lo que se tildo en el telefono desaparece de la pantalla", e["espejo"])


# ---------------------------------------------------------------- lo que sale del panel

print("\n[5] Lo anotado en el panel viaja al telefono")
limpiar()
avisos.crear("Sacar la basura")
salida = avisos.sincronizar("Comprar pan||Personal\n")
ok(salida.strip() == "Sacar la basura", "el Atajo se lo lleva en la respuesta", repr(salida))

print("\n[6] Vuelve en el espejo -> se da por llegado y sale de la cola")
# El telefono ya lo creo, asi que en la corrida siguiente aparece entre los suyos.
salida = avisos.sincronizar("Comprar pan||Personal\nSacar la basura||Personal\n")
ok(salida.strip() == "", "no se lo manda dos veces", repr(salida))
ok(len(avisos.estado()["salientes"]) == 0, "la cola queda vacia",
   avisos.estado()["salientes"])

print("\n[7] Si el Atajo se muere, se vuelve a intentar (y no para siempre)")
limpiar()
avisos.crear("Pagar la luz")
intentos = 0
for _ in range(6):
    # El telefono nunca lo confirma: se corta el wifi justo despues de recibirlo.
    if avisos.sincronizar("Otra cosa||\n").strip():
        intentos += 1
ok(intentos == avisos.ENTREGAS_MAX,
   "se reintenta %d veces y despues se lo da por entregado" % avisos.ENTREGAS_MAX, intentos)
ok(len(avisos.estado()["salientes"]) == 0, "no queda dando vueltas para siempre",
   avisos.estado()["salientes"])

print("\n[8] Sacar uno de la cola antes de que se vaya")
limpiar()
s = avisos.crear("Algo que despues no quise")
ok(avisos.quitar(s["id"]) is True, "se saca por su id")
ok(avisos.sincronizar("").strip() == "", "y ya no se lo manda al telefono")
ok(avisos.quitar("no-existe") is False, "quitar algo que no esta avisa que no estaba")

print("\n[9] El separador no se puede colar por el texto que escribis")
limpiar()
s = avisos.crear("Comprar pan | leche | huevos")
ok("|" not in s["nombre"], "el | del texto se cambia", s["nombre"])
# ⚠ Por que importa: si el nombre viajara con "|", la linea que suba el telefono
# despues se partiria mal, no coincidiria, y se lo estaria mandando para siempre.
avisos.sincronizar("")
vuelve = s["nombre"] + "||Personal"
ok(avisos.sincronizar(vuelve + "\n").strip() == "",
   "y asi vuelve igual y se da por llegado")

print("\n[10] Casos de borde que no tienen que romper nada")
limpiar()
ok(avisos.crear("") is None, "no deja anotar algo vacio")
ok(avisos.crear("   ") is None, "ni solo espacios")
ok(avisos.sincronizar("") == "", "un telefono sin nada pendiente no rompe")
ok(avisos.sincronizar("\n\n  \n") == "", "las lineas vacias se ignoran")
e = avisos.estado()
ok(e["espejo"] == [], "y el espejo queda vacio, no con basura", e["espejo"])
ok(e["nunca"] is False and e["hace_min"] is not None,
   "igual queda registrado que el telefono aparecio", e)

print("\n[11] El archivo roto no voltea el panel")
limpiar()
avisos.AVISOS.write_text("{ esto no es json", encoding="utf-8")
e = avisos.estado()
ok(e["espejo"] == [] and e["salientes"] == [], "arranca de cero en vez de reventar", e)
ok(avisos.crear("Después de lo roto") is not None, "y se puede seguir usando")

print("\n[12] El estado que lee la pantalla")
limpiar()
e = avisos.estado()
ok(e["nunca"] is True, "sin ninguna corrida, avisa que nunca se conecto")
ok(e["dormido"] is False, "y no lo llama dormido (no es lo mismo)", e["dormido"])
avisos.sincronizar("Algo||\n")
e = avisos.estado()
ok(e["hace_min"] == 0 and e["dormido"] is False, "recien sincronizado esta al dia", e)
ok(e["corridas"] == 1, "cuenta las corridas del Atajo", e["corridas"])

print("\n[13] Los endpoints del panel, de punta a punta")
# ⚠ Se IMPORTA panel.py y se lo llama con TestClient, no se levanta el servidor: el
# vigilante de servicios es un evento de arranque de uvicorn, asi que importar no
# prende ni apaga nada (misma receta que `probar_unir_audios.py`). Y como el modulo
# `avisos` ya apunta al temporal, el panel escribe ahi tambien.
limpiar()
import panel                                                   # noqa: E402
from fastapi.testclient import TestClient                       # noqa: E402

cli = TestClient(panel.app)                                     # sin `with`: no dispara startup
r = cli.post("/avisos/nuevo", json={"nombre": "Probar el puente"})
ok(r.status_code == 200 and r.json().get("ok"), "POST /avisos/nuevo anota", r.text[:60])
r = cli.post("/avisos/sync", content="Comprar pan|2026-08-18T09:00:00|Personal".encode("utf-8"))
ok(r.status_code == 200, "POST /avisos/sync contesta", str(r.status_code))
ok(r.text.strip() == "Probar el puente",
   "y le devuelve al Atajo lo que hay que crear", repr(r.text))
r = cli.get("/avisos/lista")
d = r.json()
ok(d["ok"] and len(d["espejo"]) == 1 and len(d["salientes"]) == 1,
   "GET /avisos/lista trae las dos listas", str(d)[:90])
# Segun como quede configurada la accion del Atajo, el cuerpo puede llegar como JSON.
r = cli.post("/avisos/sync", content=b'{"texto": "Desde JSON||Personal"}')
ok(r.status_code == 200 and cli.get("/avisos/lista").json()["espejo"][0]["nombre"] == "Desde JSON",
   "el cuerpo tambien se acepta como JSON", r.text[:40])
r = cli.post("/avisos/nuevo", json={"nombre": "   "})
ok(r.status_code == 400, "anotar algo vacio se rechaza con un error claro", str(r.status_code))
r = cli.get("/avisos")
ok(r.status_code == 200 and "Avisos" in r.text, "GET /avisos sirve la pantalla",
   str(r.status_code))

print("\n%d bien, %d mal" % (_bien, _mal))
raise SystemExit(1 if _mal else 0)
