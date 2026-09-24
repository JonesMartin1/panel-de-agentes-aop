"""Testing adversarial: el que escribe el codigo nunca es el que lo juzga.

El disparador no fue teorico. Un agente le entrego trabajo a Martin diciendo que
andaba, y no andaba. De ahi sale todo lo de aca: esto NO es un proceso de gestion
para que el ciclo quede prolijo, es un detector de mentiras. Si en diez corridas no
atrapa ningun "anda" falso, es ceremonia y hay que discutirlo.

EL CICLO, cinco pasos y vuelve (decidido con Martin el 2026-08-29):

  1. Planificacion  — la spec con escenarios Given/When/Then. La redacta la sesion y
                      la aprueba Martin con un boton: es el modo plan que YA existe,
                      no hay pantalla nueva. Aca entra ya aprobada.
  2. Implementacion — una sesion de Claude escribe el codigo.
  3. Contraste      — tres revisores de contexto limpio con consigna de REFUTAR:
                      uno de Claude que abre el sistema en el navegador y lo usa como
                      una persona, y dos de Codex que leen. Ver el reparto abajo.
  4. Despliegue     — solo con el paso 3 en verde, o con Martin desempatando a favor.
  5. QA             — la vuelta humana, que reabre la planificacion. No es de este modulo.

EL REPARTO, y por que es asi:

  ⭐ El navegador es de Claude y no se toca. `navegador_de(cwd)` solo lo aplica
  `_arrancar_viva`, o sea las sesiones de Claude; las de Codex se lanzan por otro camino
  y lo unico que reciben es el sandbox. NO se le construye soporte de Chrome a Codex:
  Claude mira la pantalla y Codex trabaja sobre lo que Claude dejo escrito.

  ⭐⭐ El EXPEDIENTE lo escribe el revisor que miro, nunca el implementador. Si el
  expediente lo armara el que escribio el codigo, Codex estaria leyendo la version de
  los hechos del acusado — y el acusado es justo el que dijo "anda" cuando no andaba.
  Por eso el archivo lo escribe ESTE modulo con el texto que devolvio el revisor: la
  sesion que implementa no tiene por donde tocarlo.

  ⚠ Los revisores nacen SIN sid (contexto limpio) en cada vuelta, a proposito. Un
  revisor que ya vio la vuelta anterior arrastra su propio juicio y deja de ser
  independiente.

LA REGLA DE EVIDENCIA: un hallazgo sin evidencia no cuenta como hallazgo y se descarta,
aunque lo firmen los tres. Una opinion sin respaldo es exactamente el acto de fe que
origino todo esto. Lo descartado NO se tira en silencio: queda contado en la ficha.

  ⭐ Y su reverso, que en este proyecto costo caro: el informe vacio es una respuesta
  valida. A un agente al que se le pide encontrar problemas, va a encontrar problemas.
  Por eso a los tres se les dice que "esta todo bien" es un resultado.

EL TOPE: dos vueltas de implementar-contrastar. Si sigue en rojo, es EMPATE REAL y ahi
—y solo ahi— suena el telefono de Martin. Nunca un aviso por hallazgo suelto: el 25/08
el vigia de WhatsApp mando siete avisos seguidos y por eso hoy la regla es una sola cosa.

⚠ Esto corre contra los sistemas REALES, incluidos los de clientes. Decision explicita
de Martin del 2026-08-29, con el riesgo planteado y aceptado. Lo que NO cambia por esa
decision: las sesiones no pueden ejecutar JavaScript en la pagina (`CHROME_JS` sigue
prohibido en `_arrancar_viva`) y lo irreversible se sigue frenando y preguntando.
"""
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.rutas import ADVERSARIAL, PIZARRA_IMAGENES

# Dos vueltas de implementar-contrastar antes de darle el empate a Martin. No es un
# numero al azar: con una sola, cualquier hallazgo real lo despierta; con tres o mas, el
# ciclo se pasa la madrugada quemando tokens sobre algo que ya no converge.
MAX_VUELTAS = 2
# Cuantos revisores de Codex. Dos, mas el de Claude que mira, son los "2-3 GPT" del
# dibujo. Ojo si se sube: los de Codex no ocupan lugar en `VIVAS` (cada turno es un
# proceso que nace y muere), pero cada uno es un turno pago.
LECTORES = 2

_CORRIDAS = {}                    # id -> ficha (lo que se ve en la tarjeta del panel)
_CANDADO = threading.RLock()


# --------------------------------------------------------------------------- ficha

def _ahora():
    return time.time()


def _ficha_nueva(cwd, tarea, spec):
    cid = "adv_%d" % int(_ahora() * 1000)
    return {
        "id": cid,
        "cwd": str(cwd),
        "proyecto": Path(cwd).name,
        "tarea": tarea,
        "spec": spec,
        "estado": "implementando",
        "vuelta": 1,
        "creado": _ahora(),
        "actualizado": _ahora(),
        "sid_implementador": "",
        "expediente": "",
        "captura": "",
        "hallazgos": [],
        "descartados": 0,
        "refutacion": "",
        "veredicto": "",
        "error": "",
        "avisado": False,
        "desempate": "",
        "pasos": [],
    }


def _archivo(cid):
    return ADVERSARIAL / ("%s.json" % cid)


def _guardar(t):
    """La ficha al disco despues de CADA paso.

    No es prolijidad: el hilo de la corrida no sobrevive a un reinicio del panel, asi
    que si el estado vive solo en memoria, reiniciar deja a Martin sin saber que paso.
    """
    t["actualizado"] = _ahora()
    try:
        ADVERSARIAL.mkdir(parents=True, exist_ok=True)
        _archivo(t["id"]).write_text(
            json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("adversarial: no pude guardar la ficha:", e, flush=True)


def _paso(t, texto):
    """El rastro que se ve en la tarjeta. En criollo: lo lee Martin, no un programador."""
    t["pasos"].append({"hora": _ahora(), "que": texto})
    print("adversarial [%s]: %s" % (t["id"], texto), flush=True)
    _guardar(t)


# --------------------------------------------------------------------- los hallazgos

# Cada revisor contesta en bloques con este formato. Se pide asi y no en JSON porque un
# modelo que falla el JSON no contesta nada, y aca perder el hallazgo es peor que
# parsearlo con cuidado.
_HALLAZGO = re.compile(r"^\s*HALLAZGO\s*:\s*(.+)$", re.I)
_EVIDENCIA = re.compile(r"^\s*EVIDENCIA\s*:\s*(.+)$", re.I)
_ESCENARIO = re.compile(r"^\s*ESCENARIO\s*:\s*(.+)$", re.I)


def _parsear(texto, quien):
    """Los hallazgos de un revisor. Devuelve (con evidencia, cuantos se descartaron).

    ⭐ El que no trae EVIDENCIA se descarta. Esa es la regla entera del metodo: una
    opinion sin respaldo no vale, la firme quien la firme. Y se DEVUELVE cuantos se
    cayeron, porque descartar en silencio se lee como "no encontro nada", que es un
    resultado bien distinto.
    """
    hallazgos, descartados = [], 0
    actual = None
    for linea in (texto or "").splitlines():
        m = _HALLAZGO.match(linea)
        if m:
            if actual is not None:
                if actual["evidencia"]:
                    hallazgos.append(actual)
                else:
                    descartados += 1
            actual = {"de": quien, "que": m.group(1).strip(),
                      "evidencia": "", "escenario": ""}
            continue
        if actual is None:
            continue
        m = _EVIDENCIA.match(linea)
        if m:
            actual["evidencia"] = m.group(1).strip()
            continue
        m = _ESCENARIO.match(linea)
        if m:
            actual["escenario"] = m.group(1).strip()
    if actual is not None:
        if actual["evidencia"]:
            hallazgos.append(actual)
        else:
            descartados += 1
    return hallazgos, descartados


def _formato():
    """El formato que se le pide a los tres revisores, igual para todos."""
    return (
        "Contesta SOLO con este formato, sin markdown ni parrafos sueltos.\n"
        "Por cada problema, un bloque:\n"
        "HALLAZGO: que esta mal, en una linea\n"
        "EVIDENCIA: el respaldo concreto (ver abajo que cuenta como respaldo)\n"
        "ESCENARIO: cual escenario de la especificacion no se cumple\n"
        "\n"
        "⚠ Un HALLAZGO sin EVIDENCIA se descarta y no cuenta. No lo escribas.\n"
        "⭐ Si no encontraste nada, contesta la palabra VERDE y nada mas. "
        "\"Esta todo bien\" es un resultado valido y esperado: no inventes hallazgos "
        "de adorno para justificar la revision.")


def _diff(cwd):
    """Lo que se toco, para los que leen. Vacio si no es un repo git o si no hay nada."""
    partes = []
    for args in (["diff"], ["diff", "--staged"]):
        try:
            # ⚠ creationflags: el ciclo corre adentro del panel, que no tiene consola,
            # y sin la marca cada `git diff` abre una ventana negra (2026-09-06).
            p = subprocess.run(["git", "-C", str(cwd)] + args, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if p.returncode == 0 and p.stdout.strip():
                partes.append(p.stdout)
        except Exception:
            pass
    texto = "\n".join(partes)
    # Un diff gigante se come el turno del revisor sin aportar: se corta diciendolo.
    if len(texto) > 20000:
        texto = texto[:20000] + "\n[... diff cortado aca: era mas largo]"
    return texto


# ------------------------------------------------------------------ los tres papeles

def _implementar(t, hallazgos):
    """Paso 2. La MISMA sesion en las dos vueltas: tiene que saber que hizo antes."""
    from app.voz import sesiones_movil
    if hallazgos:
        pedido = (
            "Los revisores encontraron esto contra tu implementacion. Por cada uno: si es "
            "real, arreglalo; si es falso, deci POR QUE con evidencia concreta (no "
            "\"lo probe y anda\").\n\n" + _lista(hallazgos))
    else:
        pedido = (
            "Implementa esto: %s\n\n"
            "La especificacion aprobada, que es la vara con la que te van a juzgar:\n%s\n\n"
            "Cuando termines, deci en una linea que tocaste. No digas que funciona si no "
            "lo probaste." % (t["tarea"], t["spec"]))
    respuesta, sid_nuevo = sesiones_movil.mandar(
        t["cwd"], t["sid_implementador"], pedido)
    if sid_nuevo:
        t["sid_implementador"] = sid_nuevo
    return respuesta or ""


def _mirar(t):
    """Paso 3a. Claude de contexto limpio, con el navegador de esa carpeta.

    Nace sin sid a proposito: un revisor que ya vio la vuelta anterior arrastra su
    propio juicio y deja de ser independiente.
    """
    from app.voz import sesiones_movil
    pedido = (
        "Sos revisor adversarial y NO escribiste este codigo. Tu trabajo no es "
        "arreglarlo: es refutar que funcione. No edites ningun archivo.\n\n"
        "Abri el sistema en el navegador y usalo como lo usaria una persona, contra "
        "estos escenarios:\n%s\n\n"
        "Lo que se pidio era: %s\n\n"
        "EVIDENCIA, para vos, es de primera mano: que pantalla abriste, que hiciste y "
        "que viste. \"Leyendo el codigo parece que\" NO es evidencia para este papel.\n\n"
        "%s\n\n"
        "⭐ Ademas, y esto va UNA sola vez al final de tu respuesta: sacale una captura a "
        "la pantalla que mejor muestre lo que encontraste (o a la que probaste, si esta "
        "todo bien), guardala en disco y pega la ruta del archivo asi:\n"
        "CAPTURA: C:\\ruta\\al\\archivo.png\n"
        "Esa captura se cuelga en el pizarron de Martin con tu analisis abajo, que es "
        "como el mira lo que paso. Si no pudiste sacar ninguna, no escribas la linea."
        % (t["spec"], t["tarea"], _formato()))
    respuesta, _sid = sesiones_movil.mandar(t["cwd"], "", pedido)
    return respuesta or ""


def _leer(t, n, expediente, diff):
    """Paso 3b. Codex de contexto limpio, sobre el expediente de un TERCERO.

    Lo que lee no lo escribio el implementador (ver el encabezado del modulo): esa es
    la unica razon por la que su veredicto vale algo.
    """
    from app.voz import sesiones_movil
    pedido = (
        "Sos revisor adversarial numero %d y NO escribiste este codigo. No edites "
        "ningun archivo: leelo y juzgalo.\n\n"
        "Lo que se pidio: %s\n\n"
        "La especificacion aprobada:\n%s\n\n"
        "El expediente del revisor que abrio el sistema en el navegador (lo escribio un "
        "tercero, NO el que implemento):\n%s\n\n"
        "Lo que se toco:\n%s\n\n"
        "EVIDENCIA, para vos, es archivo y linea mas el escenario que no se cumple.\n\n"
        "%s" % (n, t["tarea"], t["spec"], expediente or "(sin expediente)",
                diff or "(sin cambios en git)", _formato()))
    respuesta, _sid = sesiones_movil.mandar(t["cwd"], "", pedido, cerebro="codex")
    return respuesta or ""


def _lista(hallazgos):
    return "\n".join(
        "- [%s] %s\n  evidencia: %s\n  escenario: %s"
        % (h["de"], h["que"], h["evidencia"], h["escenario"] or "(no dijo cual)")
        for h in hallazgos)


# ------------------------------------------------------------------------- el aviso

def _avisar_empate(t):
    """El telefono suena UNA vez y solo por el empate real.

    ⭐ El mensaje dice QUE se discute, no "hay una decision pendiente": se lee en el
    celular, sin contexto y sin el panel a mano.
    """
    if t.get("avisado"):
        return
    from app.voz.sesiones_movil import _mandar_aviso_espera
    primero = t["hallazgos"][0] if t["hallazgos"] else None
    que = primero["que"] if primero else "un hallazgo"
    refuta = " ".join((t.get("refutacion") or "").split())[:200] or "no contesto"
    texto = ("Empate en el contraste de %s. El revisor dice: %s. El que lo escribio "
             "contesta: %s. Nadie lo pudo demostrar en %d vueltas, asi que lo tenes que "
             "cortar vos: entra al panel y elegi a quien le das la razon."
             % (t["proyecto"], que, refuta, MAX_VUELTAS))
    t["avisado"] = bool(_mandar_aviso_espera(texto, t["proyecto"]))
    _guardar(t)


# ------------------------------------------------------------------ el pizarron

# El pizarron VISUAL del panel, el de los papelitos — no el `PIZARRA.md` del repo, que es
# otra cosa con nombre parecido. Se le escribe por HTTP igual que la skill `pizarra`:
# este modulo corre adentro del panel, pero importarlo seria una dependencia al reves.
PANEL = "http://127.0.0.1:8750"
# ⭐ La marca con la que reconocemos NUESTRAS notas. Existe por una regla de Martin: en su
# pizarron hay cosas puestas a mano y por Laura, y no se borra lo que uno no puso. Con
# esto `limpiar_pizarra()` puede barrer las suyas sin tocar una sola ajena.
MARCA = "adversarial:"
# Ambar para lo que te espera y rojo solo para lo que se rompio: el rojo es para lo que
# esta mal, no para un estado normal (pedido de Martin).
COLOR = {"verde": "#7bc47f", "empate": "#e8b84b", "fallo": "#e05c5c"}


def _pedir_panel(ruta, datos=None, metodo=None):
    pedido = urllib.request.Request(
        PANEL + ruta,
        data=json.dumps(datos).encode("utf-8") if datos is not None else None,
        headers={"Content-Type": "application/json"},
        method=metodo or ("POST" if datos is not None else "GET"))
    with urllib.request.urlopen(pedido, timeout=8) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


# Que tan ancha se cuelga la captura en el tablero, en unidades del pizarron. El alto
# sale del alto real de la imagen: estirarla seria mentir sobre lo que se vio.
ANCHO_CAPTURA = 420
# El fondo del bloque: un rectangulo grande color carbon, con el trazo dibujado de la
# pizarra. Pedido de Martin: "atras de todo el analisis tiene que haber rectangulo negro
# grande en modo pizarra de color carbon". El analisis va escrito ENCIMA en claro, como
# tiza — de ahi que sea un `texto` y no un papelito de color.
CARBON = "#23262b"
TIZA = "#e8eaed"
MARGEN_BLOQUE = 28.0        # aire entre el borde del carbon y lo que lleva adentro
MARGEN_TABLERO = 80.0       # aire entre el bloque y lo que ya habia en el pizarron
ALTO_TEXTO = 96.0           # lo que se le reserva al analisis debajo de la foto
# ⚠ Lo que mide una nota que no declara tamaño: el CSS del pizarron le pone
# `max-width:220px`. Si esto se queda corto, el buscador de hueco cree que hay lugar
# donde no lo hay y le cuelga el bloque encima a un papelito de Martin.
ANCHO_NOTA = 220.0
ALTO_NOTA = 140.0
_CAPTURA = re.compile(r"^\s*CAPTURA\s*:\s*(.+)$", re.I | re.M)
_IMAGENES_OK = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _captura_de(texto):
    """La ruta de la captura que dejo el revisor que miro, si dejo alguna."""
    m = _CAPTURA.search(texto or "")
    if not m:
        return None
    ruta = Path(m.group(1).strip().strip('"').strip("'"))
    if ruta.suffix.lower() not in _IMAGENES_OK or not ruta.is_file():
        return None
    return ruta


def _colgar_captura(ruta, cid):
    """Copia la captura al deposito del pizarron. Devuelve (nombre, ancho, alto).

    ⚠ Se COPIA, no se mueve ni se enlaza: el archivo original es de la sesion que la
    saco y puede desaparecer cuando esa sesion se apague; el pizarron tiene que seguir
    mostrando la evidencia meses despues.
    """
    try:
        from PIL import Image
        PIZARRA_IMAGENES.mkdir(parents=True, exist_ok=True)
        destino = PIZARRA_IMAGENES / ("adv_%s%s" % (cid, ruta.suffix.lower()))
        destino.write_bytes(ruta.read_bytes())
        with Image.open(destino) as im:
            ancho, alto = im.size
        return destino.name, ancho, alto
    except Exception as e:
        print("adversarial: no pude colgar la captura:", e, flush=True)
        return None


def _caja_de(item):
    """La caja (x1, y1, x2, y2) que ocupa un item en el tablero, o None si no se sabe.

    ⚠⚠ Aca estaba el bug que destapo el pedido de Martin de "que no pise nada". Una NOTA
    se posiciona por su CENTRO (el pizarron la dibuja con `translate(-50%,-50%)`), no por
    su esquina: tomar su `x` como borde derecho se queda corto la MITAD del ancho, y con
    `w = 420` eso son 210 unidades — suficiente para que el bloque nuevo le caiga encima
    al papelito de la corrida anterior. Las FIGURAS van por sus dos puntos, y pueden
    venir al reves (x2 < x1) si se dibujaron de derecha a izquierda.
    """
    tipo = item.get("tipo") or "nota"
    if tipo in ("nota", "texto", "pin"):
        x, y = item.get("x"), item.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        ancho = float(item.get("w") or ANCHO_NOTA)
        alto = float(item.get("h") or ALTO_NOTA)
        return (x - ancho / 2, y - alto / 2, x + ancho / 2, y + alto / 2)
    if all(isinstance(item.get(c), (int, float)) for c in ("x1", "y1", "x2", "y2")):
        return (min(item["x1"], item["x2"]), min(item["y1"], item["y2"]),
                max(item["x1"], item["x2"]), max(item["y1"], item["y2"]))
    xs, ys = [], []
    for punto in (item.get("puntos") or []):        # el lapiz: dibujo libre
        if isinstance(punto, dict):
            xs.append(punto.get("x"))
            ys.append(punto.get("y"))
        elif isinstance(punto, (list, tuple)) and len(punto) >= 2:
            xs.append(punto[0])
            ys.append(punto[1])
    xs = [v for v in xs if isinstance(v, (int, float))]
    ys = [v for v in ys if isinstance(v, (int, float))]
    if xs and ys:
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def _se_pisan(a, b):
    """Si dos cajas se superponen. Tocarse justo por el borde no cuenta como pisarse."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _lugar_libre(ancho, alto):
    """Un hueco donde el bloque entero no toque NADA de lo que ya hay en el tablero.

    ⚠ No es cosmetica: el pizarron es de Martin y ahi tiene sus dibujos. Colgarle la
    evidencia encima seria pisarle el trabajo, aunque despues se pueda borrar.

    La columna se fija a la derecha de lo AJENO (no de lo nuestro), asi los bloques no se
    van corriendo para siempre hacia la derecha; adentro de esa columna se baja hasta el
    primer hueco libre, contando tambien las corridas anteriores.
    """
    try:
        estado = _pedir_panel("/pizarra/estado")
    except Exception:
        return 0.0, 0.0                  # tablero ilegible: que no frene la corrida
    ajenas, todas = [], []
    for item in (estado.get("items") or []):
        caja = _caja_de(item)
        if caja is None:
            continue
        todas.append(caja)
        if not str(item.get("nombre") or "").startswith(MARCA):
            ajenas.append(caja)
    if not todas:
        return 0.0, 0.0
    x = (max(c[2] for c in ajenas) + MARGEN_TABLERO) if ajenas else 0.0
    y = min(c[1] for c in todas)         # arranca a la altura de lo mas alto que hay
    for _ in range(200):                 # 200 bloques apilados es mas que de sobra
        if not any(_se_pisan((x, y, x + ancho, y + alto), c) for c in todas):
            return x, y
        y += alto + MARGEN_TABLERO / 2
    return x, y




def _anotar_pizarra(t):
    """La captura de lo que se vio, con el analisis abajo. Al terminar la corrida.

    ⭐ Pedido de Martin: "no quiero solo el papelito, quiero la captura que hace con el
    analisis abajo". La captura es la evidencia que se entiende de un vistazo; el texto
    solo es el pie de foto.

    ⚠ Se anota UNA vez, al final, y no en cada paso: un papelito por vuelta y por
    hallazgo taparia el tablero, que es donde el tiene sus dibujos. Y no se anota nada
    mientras la corrida esta corriendo — para mirar eso esta la tarjeta del panel.

    Si el revisor no dejo captura, sube el texto solo: quedarse sin nota por no tener
    foto seria perder el veredicto entero.
    """
    cara = {"verde": "verde", "empate": "te espera", "fallo": "se corto"}
    if t["estado"] not in cara:
        return
    if t["estado"] == "verde":
        detalle = "Nadie lo pudo refutar con evidencia."
    elif t["estado"] == "fallo":
        detalle = t.get("error") or "se corto sin veredicto"
    else:
        primero = t["hallazgos"][0] if t["hallazgos"] else None
        detalle = primero["que"] if primero else "sin hallazgo a la vista"
    texto = "%s %s\n%s\n%s" % (t["proyecto"], cara[t["estado"]],
                              t["tarea"][:70], detalle[:120])
    try:
        # 1) Primero se mide el bloque, porque de su tamaño depende donde entra.
        alto_foto = 0.0
        ruta = _captura_de(t.get("expediente") or "")
        colgada = _colgar_captura(ruta, t["id"]) if ruta else None
        if colgada:
            _nombre, ancho_real, alto_real = colgada
            # El alto sale de la proporcion real: una captura estirada miente sobre lo
            # que se vio, y lo que se vio es justamente el punto.
            alto_foto = ANCHO_CAPTURA * (alto_real / ancho_real) if ancho_real else 240
        ancho = ANCHO_CAPTURA + 2 * MARGEN_BLOQUE
        alto = 2 * MARGEN_BLOQUE + alto_foto + ALTO_TEXTO
        x, y = _lugar_libre(ancho, alto)

        # 2) El fondo carbon va PRIMERO: el pizarron dibuja en el orden de la lista, asi
        # que el primero es el que queda atras. Colgado ultimo taparia la foto entera.
        # ⚠ En una figura el relleno y el trazo salen del MISMO campo (`o.fill=it.color`
        # en el dibujante): no hay carbon adentro y color de veredicto en el borde. Por
        # eso el veredicto vive en la tiza del analisis, no en el marco.
        _pedir_panel("/pizarra/agregar",
                     {"tipo": "rectangulo",
                      "x1": x, "y1": y, "x2": x + ancho, "y2": y + alto,
                      "color": CARBON, "relleno": "solido", "grosor": 2,
                      "nombre": MARCA + t["id"]})

        # 3) La captura, apoyada arriba del carbon.
        if colgada:
            nombre = colgada[0]
            _pedir_panel("/pizarra/agregar",
                         {"tipo": "imagen", "archivo": nombre,
                          "x1": x + MARGEN_BLOQUE, "y1": y + MARGEN_BLOQUE,
                          "x2": x + MARGEN_BLOQUE + ANCHO_CAPTURA,
                          "y2": y + MARGEN_BLOQUE + alto_foto,
                          "nombre": MARCA + t["id"]})
            t["captura"] = nombre

        # 4) El analisis, en tiza sobre el carbon. Es `texto` y no `nota` a proposito:
        # un papelito amarillo flotando sobre un mantel negro seria otra cosa.
        # ⚠ El texto se posiciona por su CENTRO (translate(-50%,-50%)) y la imagen por su
        # caja: por eso va en la mitad del ancho, o queda corrido media caja.
        _pedir_panel("/pizarra/agregar",
                     {"tipo": "texto", "texto": texto,
                      "x": x + ancho / 2,
                      "y": y + MARGEN_BLOQUE + alto_foto + ALTO_TEXTO / 2,
                      "w": ANCHO_CAPTURA, "h": ALTO_TEXTO,
                      "colorTexto": COLOR.get(t["estado"], TIZA),
                      "color": COLOR.get(t["estado"], TIZA),
                      "nombre": MARCA + t["id"]})
    except Exception as e:
        # Que no llegue al pizarron no puede tumbar la corrida: el veredicto ya esta
        # en la ficha y en la tarjeta, que es la fuente de verdad.
        print("adversarial: no pude anotar en el pizarron:", e, flush=True)


def _borrar_nota(cid):
    """Saca la nota de ESA corrida, si la hay. Devuelve cuantas saco.

    Se usa cuando el veredicto cambia (el empate que Martin desempata): sin esto el
    tablero quedaba diciendo "te espera" para siempre por algo ya resuelto, y aparecian
    dos papelitos de la misma corrida.
    """
    try:
        estado = _pedir_panel("/pizarra/estado")
    except Exception:
        return 0
    sacadas = 0
    for item in (estado.get("items") or []):
        if str(item.get("nombre") or "") != MARCA + cid:
            continue
        try:
            _pedir_panel("/pizarra/item/%s" % item["id"], metodo="DELETE")
            sacadas += 1
        except Exception:
            pass
    return sacadas


def limpiar_pizarra():
    """Saca del pizarron SOLO las notas que puso este modulo. Devuelve cuantas saco."""
    try:
        estado = _pedir_panel("/pizarra/estado")
    except Exception as e:
        print("adversarial: no pude leer el pizarron:", e, flush=True)
        return 0
    sacadas = 0
    for item in (estado.get("items") or []):
        if not str(item.get("nombre") or "").startswith(MARCA):
            continue            # de Martin o de Laura: no se toca
        try:
            _pedir_panel("/pizarra/item/%s" % item["id"], metodo="DELETE")
            sacadas += 1
        except Exception:
            pass
    return sacadas


# -------------------------------------------------------------------- la orquestacion

def _contrastar(t):
    """Paso 3 entero. Devuelve la lista de hallazgos CON evidencia."""
    _paso(t, "mira la pantalla un revisor de contexto limpio")
    expediente = _mirar(t)
    t["expediente"] = expediente
    hallazgos, descartados = _parsear(expediente, "el que miro")
    diff = _diff(t["cwd"])
    for i in range(1, LECTORES + 1):
        _paso(t, "lee el expediente el revisor %d de Codex" % i)
        h, d = _parsear(_leer(t, i, expediente, diff), "lector %d de Codex" % i)
        hallazgos += h
        descartados += d
    t["descartados"] = descartados
    t["hallazgos"] = hallazgos
    if descartados:
        _paso(t, "descarto %d opinion(es) sin evidencia: no cuentan como hallazgo"
                 % descartados)
    return hallazgos


def _correr(cid, desde_vuelta=1):
    """El cuerpo del hilo. Cada paso queda escrito en la ficha antes de seguir."""
    with _CANDADO:
        t = _CORRIDAS.get(cid)
    if not t:
        return
    try:
        for vuelta in range(desde_vuelta, MAX_VUELTAS + 1):
            t["vuelta"] = vuelta
            t["estado"] = "implementando"
            _paso(t, "vuelta %d: implementa" % vuelta)
            respuesta = _implementar(t, t["hallazgos"] if vuelta > 1 else [])
            if vuelta > 1:
                t["refutacion"] = respuesta
            t["estado"] = "contrastando"
            _guardar(t)
            if not _contrastar(t):
                t["estado"] = "verde"
                t["veredicto"] = ("Nadie pudo refutarlo con evidencia en la vuelta %d."
                                  % vuelta)
                _paso(t, "VERDE: nadie lo pudo refutar con evidencia")
                _anotar_pizarra(t)
                return
            _paso(t, "ROJO: %d hallazgo(s) con evidencia" % len(t["hallazgos"]))
        # Se acabaron las vueltas y sigue en rojo: eso es el empate real, y recien
        # aca se molesta a Martin.
        t["estado"] = "empate"
        t["veredicto"] = ("Sigue en rojo despues de %d vueltas y el que lo escribio no "
                          "acepta el hallazgo." % MAX_VUELTAS)
        _paso(t, "EMPATE: lo tiene que cortar Martin")
        _anotar_pizarra(t)
        _avisar_empate(t)
    except Exception as e:
        t["estado"] = "fallo"
        t["error"] = str(e)
        _paso(t, "se corto: %s" % e)
        _anotar_pizarra(t)


# ------------------------------------------------------------------------- la puerta

def arrancar(cwd, tarea, spec=""):
    """Larga una corrida en segundo plano y devuelve su ficha.

    No bloquea: el ciclo entero son varios turnos de varios minutos cada uno, y Martin
    cierra la laptop apenas lo larga — ese es justamente el cambio de habito que busca.
    """
    cwd = str(cwd or "").strip()
    tarea = (tarea or "").strip()
    if not cwd or not Path(cwd).is_dir():
        raise ValueError("Esa carpeta no existe.")
    if not tarea:
        raise ValueError("Falta decir que hay que implementar.")
    t = _ficha_nueva(cwd, tarea, (spec or "").strip() or tarea)
    with _CANDADO:
        _CORRIDAS[t["id"]] = t
    _paso(t, "arranca sobre %s" % t["proyecto"])
    hilo = threading.Thread(target=_correr, args=(t["id"],), daemon=True)
    hilo.start()
    return t


def resolver(cid, a_favor):
    """El desempate de Martin. Devuelve la ficha, o None si esa corrida no existe.

    A favor del que lo escribio: queda en verde y se puede desplegar. A favor del
    revisor: una vuelta mas de implementar y contrastar, con los hallazgos puestos.
    """
    with _CANDADO:
        t = _CORRIDAS.get(cid)
    if not t or t["estado"] != "empate":
        return None
    t["desempate"] = a_favor
    # El papelito del empate ya no vale: lo sacamos antes de poner el nuevo, asi queda
    # UNO por corrida y el tablero no dice "te espera" por algo que ya cortaste.
    _borrar_nota(t["id"])
    if a_favor == "implementador":
        t["estado"] = "verde"
        t["veredicto"] = "Martin le dio la razon al que lo escribio."
        _paso(t, "desempate: le diste la razon al que lo escribio")
        _anotar_pizarra(t)
    else:
        t["estado"] = "implementando"
        t["avisado"] = False        # otra vuelta, otro empate posible: otro aviso
        _paso(t, "desempate: le diste la razon al revisor, va otra vuelta")
        threading.Thread(target=_correr, args=(t["id"], MAX_VUELTAS), daemon=True).start()
    _guardar(t)
    return t


_CARPETAS = {"cuando": 0.0, "lista": []}
_CARPETAS_VALE_SEG = 300


def carpetas():
    """Los proyectos para el selector de la tarjeta, con cache de 5 minutos.

    ⚠ A proposito NO se usa `sesiones_movil.listar()`, que es lo que alimenta la
    bandeja: esa lee el ULTIMO mensaje de cada charla de cada proyecto y el 25/08 dejo
    al panel entero haciendo cola por minutos. Aca alcanza con el nombre y la ruta.
    """
    if _ahora() - _CARPETAS["cuando"] < _CARPETAS_VALE_SEG and _CARPETAS["lista"]:
        return _CARPETAS["lista"]
    from app.rutas import CLAUDE_PROYECTOS
    from app.voz import sesiones_movil
    salida, vistos = [], set()
    try:
        for carpeta in CLAUDE_PROYECTOS.iterdir():
            if not carpeta.is_dir():
                continue
            cwd = sesiones_movil._cwd_de_carpeta(carpeta)
            if not cwd or cwd.lower() in vistos:
                continue
            vistos.add(cwd.lower())
            salida.append({"cwd": cwd, "nombre": Path(cwd).name})
    except Exception as e:
        print("adversarial: no pude listar los proyectos:", e, flush=True)
    salida.sort(key=lambda c: c["nombre"].lower())
    _CARPETAS.update({"cuando": _ahora(), "lista": salida})
    return salida


def estado(cid):
    with _CANDADO:
        t = _CORRIDAS.get(cid)
    if t:
        return t
    try:                            # el panel se reinicio: la ficha sobrevivio al hilo
        return json.loads(_archivo(cid).read_text(encoding="utf-8"))
    except Exception:
        return None


def listar(cwd=""):
    """Las corridas, la mas nueva primero. Con `cwd`, solo las de esa carpeta."""
    vistas, salida = set(), []
    with _CANDADO:
        fichas = list(_CORRIDAS.values())
    try:
        for p in sorted(ADVERSARIAL.glob("adv_*.json"), reverse=True)[:50]:
            try:
                fichas.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    except Exception:
        pass
    for t in fichas:
        if t["id"] in vistas:
            continue                # la de memoria manda: es la que esta viva
        vistas.add(t["id"])
        if cwd and str(t.get("cwd", "")).lower() != str(cwd).lower():
            continue
        salida.append(t)
    return sorted(salida, key=lambda x: x.get("creado", 0), reverse=True)
