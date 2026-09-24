"""El boton Avisame apretado con el turno YA corriendo (pedido de Martin, 2026-08-29).

Hasta hoy "Avisame" era una bandera del navegador que se consumia al MANDAR:

  - apretarlo mientras la sesion pensaba NO hacia nada para ese turno;
  - encima quedaba armado en silencio para el mensaje siguiente;
  - y en el celular se apagaba la variable pero no la LUZ, asi que el boton se veia
    amarillo mintiendo.

Ahora el "quiero que me avises" vive en la FICHA del trabajo y se lee al terminar, asi
que se puede prender y apagar en el medio con `POST /movil/avisar`.

Lo que se prueba aca, todo en memoria: **nunca se manda un mensaje de verdad** (se
reemplaza `panel._avisar`) y **nunca corre un turno de verdad** (se reemplaza
`panel._ejecutar_turno_movil`). No toca GPU, microfono, servicios ni tokens.

Correr con:  D:/IA/envs/wpp/python.exe -m pruebas.probar_avisar_en_curso
Y con `--viejo` repone el defecto de antes (el aviso congelado al arrancar el hilo) y
exige que los chequeos que importan FALLEN: un chequeo que no puede fallar es un adorno.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel  # noqa: E402

VIEJO = "--viejo" in sys.argv
fallas = []
CLAVE_VIEJO = []          # los chequeos que el modo --viejo tiene que ver caer


def revisar(que, obtenido, esperado=True, clave=False):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)
    if clave:
        CLAVE_VIEJO.append((que, ok))


# --- El andamio: un turno de mentira y un cartero de mentira -------------------------
AVISOS = []


def _cartero(texto):
    AVISOS.append(texto)


def _correr_como_antes(trabajo_id, cwd, sid, texto, cerebro, esfuerzo,
                       modelo="", velocidad="", avisar=False):
    """El codigo VIEJO, tal como estaba hasta el 2026-08-29: el aviso es un argumento
    que se congela al arrancar el hilo, asi que lo que pases despues no existe."""
    resultado = panel._ejecutar_turno_movil(cwd, sid, texto, cerebro, esfuerzo,
                                            modelo, velocidad)
    with panel._TRABAJOS_CANDADO:
        t = panel._TRABAJOS_MOVIL.get(trabajo_id)
        if not t:
            return
        t.update(resultado)
        t["estado"] = "terminado" if resultado.get("ok") else "fallo"
        t["terminado"] = time.time()
        estado = t["estado"]
    if avisar and estado in ("terminado", "fallo"):
        panel._avisar(panel._aviso_tarea(cwd, resultado, estado))


def ficha(ident, sid="S-1", sid_nuevo="", estado="trabajando", avisar=False,
          terminado=None, cwd="D:/IA/wpp-transcriptor"):
    t = {"id": ident, "estado": estado, "cwd": cwd, "sid": sid, "sid_nuevo": sid_nuevo,
         "respuesta": "listo", "error": "", "cerebro": "claude", "avisar": avisar,
         "creado": time.time(), "terminado": terminado}
    panel._TRABAJOS_MOVIL[ident] = t
    return t


def limpiar():
    panel._TRABAJOS_MOVIL.clear()
    AVISOS.clear()


class Pedido:
    """Lo minimo que `movil_avisar` le pide a un Request de FastAPI."""

    def __init__(self, datos):
        self.datos = datos

    async def json(self):
        return self.datos


def avisar_ep(**datos):
    return asyncio.run(panel.movil_avisar(Pedido(datos)))


# ==== 1) Apretarlo EN EL MEDIO del turno ============================================
# El corazon del pedido: la sesion ya esta pensando y recien ahi te das cuenta de que
# viene larga. El turno de mentira aprieta el boton a mitad de camino.
turno_real = panel._ejecutar_turno_movil
correr_real = panel._correr_trabajo_movil
avisar_real = panel._avisar
panel._avisar = _cartero
if VIEJO:
    panel._correr_trabajo_movil = _correr_como_antes

try:
    for prendo, esperado, titulo in ((True, 1, "prendido en el medio"),
                                     (False, 0, "apagado en el medio")):
        limpiar()
        ficha("t1", sid="S-1", avisar=not prendo)

        def _turno(*a, **k):
            # ⭐ Esto es el dedo de Martin: el boton se toca MIENTRAS el turno corre.
            r = avisar_ep(sid="S-1", quiero=prendo)
            # (no va como "clave": el endpoint es nuevo en los dos modos, asi que esto
            # no puede caer con el defecto viejo puesto y seria un adorno marcarlo)
            revisar(f"{titulo}: el servidor dice que lo engancho",
                    r.get("enganchado"), True)
            return {"ok": True, "respuesta": "termine de hacer la cosa",
                    "sid": "S-1", "aviso": ""}

        panel._ejecutar_turno_movil = _turno
        panel._correr_trabajo_movil("t1", "D:/IA/wpp-transcriptor", "S-1", "hacelo",
                                    "claude", "high")
        # Solo el caso "prendido" distingue: con el codigo viejo el aviso no sale.
        revisar(f"{titulo}: avisos mandados", len(AVISOS), esperado,
                clave=bool(esperado))
        if esperado and AVISOS:      # con --viejo no hay ninguno: de eso se trata
            print("     el aviso dice:", AVISOS[0])
            revisar("el aviso nombra el proyecto", "wpp-transcriptor" in AVISOS[0])
            revisar("el aviso cuenta QUE termino",
                    "termine de hacer la cosa" in AVISOS[0])
finally:
    panel._ejecutar_turno_movil = turno_real
    panel._correr_trabajo_movil = correr_real

# ==== 2) Buscar el turno vivo de una charla =========================================
limpiar()
ficha("viejo", sid="S-1", estado="terminado", terminado=time.time() - 10)
vivo_ficha = ficha("vivo", sid="S-1")
with panel._TRABAJOS_CANDADO:
    vivo, ultimo = panel._trabajos_de_sesion("S-1")
revisar("encuentra el turno vivo y no el que ya termino",
        (vivo or {}).get("id"), "vivo")
revisar("y de paso se acuerda del ultimo terminado", (ultimo or {}).get("id"), "viejo")

# Una charla que NACIO en este turno cambia de id en el medio: la pantalla puede tener
# el viejo o el nuevo, y las dos puntas tienen que encontrar el mismo trabajo.
limpiar()
ficha("recien-nacida", sid="", sid_nuevo="S-2")
with panel._TRABAJOS_CANDADO:
    vivo, _ = panel._trabajos_de_sesion("S-2")
revisar("una charla recien nacida se encuentra por su id nuevo",
        (vivo or {}).get("id"), "recien-nacida")

limpiar()
ficha("de-otra", sid="S-9")
with panel._TRABAJOS_CANDADO:
    vivo, ultimo = panel._trabajos_de_sesion("S-1")
revisar("no agarra el turno de OTRA charla", (vivo, ultimo), (None, None))

# ==== 3) El endpoint, caso por caso =================================================
limpiar()
ficha("t2", sid="S-1")
r = avisar_ep(sid="S-1", quiero=True)
revisar("prender: engancha", r.get("enganchado"), True)
revisar("prender: queda escrito en la ficha", panel._TRABAJOS_MOVIL["t2"]["avisar"], True)
r = avisar_ep(sid="S-1", quiero=False)
revisar("apagar: tambien engancha", r.get("enganchado"), True)
revisar("apagar: queda escrito en la ficha",
        panel._TRABAJOS_MOVIL["t2"]["avisar"], False)

# Sin ningun turno: el boton NO miente, avisa que no engancho nada y la pantalla lo usa
# para comportarse como siempre (queda armado para el mensaje que mandes).
limpiar()
r = avisar_ep(sid="S-1", quiero=True)
revisar("sin ningun turno: no engancha", r.get("enganchado"), False)
revisar("sin ningun turno: lo dice", r.get("motivo"), "sin_turno")
revisar("sin ningun turno: no manda ningun aviso", len(AVISOS), 0)

# ⭐ La regla que mas importa: el aviso NO se pierde en silencio. Si apretaste justo
# cuando terminaba, sale igual.
limpiar()
ficha("t3", sid="S-1", estado="terminado", terminado=time.time() - 5)
r = avisar_ep(sid="S-1", quiero=True)
revisar("termino recien: lo dice", r.get("motivo"), "recien_termino")
revisar("termino recien: manda el aviso igual", len(AVISOS), 1)

# Pero una charla que termino hace rato no dispara nada: eso seria ruido.
limpiar()
ficha("t4", sid="S-1", estado="terminado",
      terminado=time.time() - panel.AVISO_RECIEN_SEG - 30)
r = avisar_ep(sid="S-1", quiero=True)
revisar("termino hace rato: no manda nada", (r.get("motivo"), len(AVISOS)),
        ("sin_turno", 0))

# Apagarlo cuando ya termino tampoco puede disparar un aviso.
limpiar()
ficha("t5", sid="S-1", estado="terminado", terminado=time.time() - 5)
r = avisar_ep(sid="S-1", quiero=False)
revisar("apagar algo que ya termino no manda nada", len(AVISOS), 0)

limpiar()
revisar("sin sesion contesta que falta", avisar_ep(quiero=True).get("ok"), False)

panel._avisar = avisar_real
limpiar()

# ==== 4) El contrato con las DOS pantallas ==========================================
# ⚠ En modo --viejo los archivos se leen de git (la version ANTERIOR al arreglo): un
# chequeo de texto no se puede mutar en memoria, asi que la unica mutacion honesta es
# preguntarle a la version que no tenia el arreglo.
RAIZ = Path(panel.__file__).parent


def _texto(rel):
    if not VIEJO:
        return (RAIZ / rel).read_text(encoding="utf-8")
    import subprocess
    return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=RAIZ, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


fuente = _texto("panel.py")
compu = _texto("app/estaticos/sesiones.html")

revisar("existe el endpoint", '@app.post("/movil/avisar")' in fuente)
revisar("el chat cuenta si ese turno ya tiene aviso pedido",
        '"avisando": avisando' in fuente)
for nombre, texto in (("el celular", fuente), ("la compu", compu)):
    revisar(f"{nombre} le pregunta al servidor", "'/movil/avisar'" in texto, clave=True)
    revisar(f"{nombre} enciende el boton con lo que dice el servidor",
            "avisando" in texto and "pintarAviso" in texto, clave=True)
    revisar(f"{nombre} sabe cuando el servidor no engancho nada",
            "sin_turno" in texto or "enganchado" in texto)
    revisar(f"{nombre} avisa si el turno termino justo", "recien_termino" in texto)

# ⚠ Los dos defectos viejos, escritos al reves para que una vuelta atras se cace:
revisar("el celular ya no deja el boton encendido mintiendo",
        "avisarTarea = false; }" not in fuente, clave=True)
revisar("una charla sin estrenar ya no queda afuera del aviso (celular)",
        "!p.virgen && avisarTarea" not in fuente, clave=True)
revisar("una charla sin estrenar ya no queda afuera del aviso (compu)",
        "avisarTarea && !clave.startsWith" not in compu, clave=True)

# ==== Resultado =====================================================================
if VIEJO:
    print("\n--- modo --viejo: los chequeos clave TIENEN que caer ---")
    cayeron = [q for q, ok in CLAVE_VIEJO if not ok]
    print(f"cayeron {len(cayeron)} de {len(CLAVE_VIEJO)} chequeos clave")
    for q in cayeron:
        print("   cayo:", q)
    if not cayeron:
        print("\nMAL: con el defecto viejo puesto no fallo NADA. La prueba es un adorno.")
        sys.exit(1)
    print("\nOK: la prueba caza el defecto viejo.")
    sys.exit(0)

print()
if fallas:
    print(f"FALLARON {len(fallas)}:")
    for f in fallas:
        print("   -", f)
    sys.exit(1)
print("OK: el aviso se puede pedir con el turno ya corriendo.")
