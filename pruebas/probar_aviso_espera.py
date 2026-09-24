"""El aviso al celular cuando una sesion del panel te FRENA a esperar una eleccion.

Pedido de Martin el 2026-08-23. Cuando una sesion pregunta con opciones
(AskUserQuestion) o deja un plan para aprobar (ExitPlanMode), el turno NO termina: el
CLI espera la respuesta por stdin. Por eso el boton "Avisame" de la caja nunca sonaba
justo cuando hacia falta. Ahora se programa un aviso por Telegram, con dos reglas
anti-ruido que son las que se prueban aca:

  - si contestas desde la pantalla antes de que salte el reloj, el aviso NO sale;
  - un solo aviso por pregunta, aunque el reloj se programe dos veces.

⚠ No se manda ningun mensaje de verdad: el que larga el aviso se reemplaza por un
apuntador, y para revisar el comando de `avisar.py` se reemplaza el `Popen`.

Correr con:  D:/IA/envs/wpp/python.exe -m pruebas.probar_aviso_espera
"""
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voz import sesiones_movil as sm  # noqa: E402

MANDAR_REAL = sm._mandar_aviso_espera      # el de verdad, antes de reemplazarlo
POPEN_REAL = sm.subprocess.Popen
fallas = []


def revisar(que, obtenido, esperado=True):
    ok = obtenido == esperado
    print(f"{'ok  ' if ok else 'MAL '} {que}: {obtenido!r}" +
          ("" if ok else f"  (esperaba {esperado!r})"))
    if not ok:
        fallas.append(que)


CWD = r"D:\IA\wpp-transcriptor"
SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CLAVE = sm._clave(CWD, SID)

PREGUNTA = {"questions": [{"question": "¿Arranco por el aviso o por las skills?",
                           "header": "Por dónde",
                           "options": [{"label": "El aviso", "description": ""},
                                       {"label": "Las skills", "description": ""}]}]}


def entrada(rid, tipo=None, input_=None):
    ent = {"request_id": rid, "input": input_ if input_ is not None else PREGUNTA,
           "hora": time.time(), "proc": None, "candado": None}
    if tipo:
        ent["tipo"] = tipo
    return ent


# --- 1) El texto del aviso -----------------------------------------------------------
# Se lee en el celular sin ningun contexto: tiene que decir QUE charla, QUE te pregunta
# y hasta cuando espera.
texto = sm._texto_espera(entrada("r1"), CWD, SID)
print("\n  aviso de pregunta:", texto, "\n")
revisar("el aviso nombra el proyecto", "wpp-transcriptor" in texto)
revisar("el aviso trae la pregunta", "¿Arranco por el aviso o por las skills?" in texto)
revisar("el aviso dice donde contestar", "Sesiones" in texto)
revisar("el aviso avisa que se cancela sola",
        str(max(1, sm.ESPERA_RESPUESTA // 60)) in texto and "sigue sin vos" in texto)

texto_plan = sm._texto_espera(entrada("r2", tipo="plan", input_={"plan": "1. hacer algo"}),
                              CWD, SID)
print("  aviso de plan:", texto_plan, "\n")
revisar("el plan se avisa como plan", "plan para aprobar" in texto_plan)

largo = {"questions": [{"question": "x" * 600, "header": "Larga", "options": []}]}
revisar("una pregunta larguisima no manda un mensaje infinito",
        len(sm._texto_espera(entrada("r3", input_=largo), CWD, SID)) < 500)

revisar("una charla sin id se nombra igual", sm._nombre_charla(CWD, ""),
        "una charla nueva")


# --- 2) El reloj: solo suena si NO contestaste ---------------------------------------
mandados = []
sm._mandar_aviso_espera = lambda texto, proyecto: mandados.append((texto, proyecto))
sm.AVISO_ESPERA_SEG = 0.25
tmp = Path(tempfile.mkdtemp()) / "avisar.py"
tmp.write_text("# avisar de mentira\n", encoding="utf-8")
sm.AVISAR_PY = tmp

# a) nadie contesta -> llega el aviso
sm.PREGUNTAS[CLAVE] = entrada("r10")
sm._avisar_espera(CLAVE, CWD, SID, "r10")
time.sleep(0.7)
revisar("sin contestar, avisa una vez", len(mandados), 1)
revisar("el aviso sale con el nombre del proyecto",
        mandados[0][1] if mandados else None, "wpp-transcriptor")
sm.PREGUNTAS.pop(CLAVE, None)

# b) contestaste antes de que saltara -> el telefono NO suena
mandados.clear()
sm.PREGUNTAS[CLAVE] = entrada("r11")
sm._avisar_espera(CLAVE, CWD, SID, "r11")
sm.PREGUNTAS.pop(CLAVE, None)          # esto es contestarla desde la pantalla
time.sleep(0.7)
revisar("contestada a tiempo, no avisa nada", len(mandados), 0)

# c) la sesion siguio y ahora espera OTRA cosa -> no avisa por la vieja
mandados.clear()
sm.PREGUNTAS[CLAVE] = entrada("r12")
sm._avisar_espera(CLAVE, CWD, SID, "r12")
sm.PREGUNTAS[CLAVE] = entrada("r13")
time.sleep(0.7)
revisar("no avisa por una pregunta que ya no esta", len(mandados), 0)
sm.PREGUNTAS.pop(CLAVE, None)

# d) dos relojes por el mismo pedido -> un solo aviso
mandados.clear()
sm.PREGUNTAS[CLAVE] = entrada("r14")
sm._avisar_espera(CLAVE, CWD, SID, "r14")
sm._avisar_espera(CLAVE, CWD, SID, "r14")
time.sleep(0.7)
revisar("un solo aviso por pregunta", len(mandados), 1)
sm.PREGUNTAS.pop(CLAVE, None)

# e) apagado, y sin la skill instalada: ninguna de las dos rompe nada
sm.AVISO_ESPERA_SEG = 0
revisar("en 0 no programa nada", sm._avisar_espera(CLAVE, CWD, SID, "r15"), None)
sm.AVISO_ESPERA_SEG = 0.25
sm.AVISAR_PY = Path(tempfile.gettempdir()) / "no-existe-esta-skill.py"
revisar("sin la skill avisar, no programa nada",
        sm._avisar_espera(CLAVE, CWD, SID, "r16"), None)
sm.AVISAR_PY = tmp


# --- 3) El comando que se larga -------------------------------------------------------
# Sale por Telegram y con el texto como UN argumento: partido, a Martin le llegaria
# la primera palabra sola.
class PopenFalso:
    ultimo = None

    def __init__(self, cmd, **kw):
        PopenFalso.ultimo = cmd


sm.subprocess.Popen = PopenFalso
try:
    revisar("el aviso de verdad se larga", MANDAR_REAL("hola", "wpp-transcriptor"))
    cmd = PopenFalso.ultimo or []
    revisar("va por telegram", "telegram" in cmd and cmd[cmd.index("--por") + 1] == "telegram")
    revisar("queda anotado como decision", "decision" in cmd)
    revisar("dice de que proyecto es", "wpp-transcriptor" in cmd)
    revisar("el texto va entero, en un solo argumento", cmd[-1], "hola")
    revisar("corre avisar.py con este mismo python", cmd[0], sys.executable)
finally:
    sm.subprocess.Popen = POPEN_REAL
    sm._mandar_aviso_espera = MANDAR_REAL

print()
if fallas:
    print(f"{len(fallas)} MAL: " + ", ".join(fallas))
    sys.exit(1)
print("todo verde")
