"""La charla de Codex se refresca leyendo SOLO lo nuevo, no el rollout entero.

Bug que trajo Martín el 2026-08-25 con dos capturas: *"¿por qué cuando me muevo entre
pestañas, esa en específico, tarda tanto?"*. Esa charla (Portafolio) tiene un rollout de
741 MB, y para juntar los 40 mensajes que muestra la pantalla hacían falta 128 MB de cola;
el bucle que la duplicaba leía 255 MB EN CADA REFRESCO — cada 3 segundos, y por cada
pantalla abierta. Cambiar a esa pestaña tardaba de 6 a 20 s y el panel quedaba tan ocupado
que las demás pestañas también se arrastraban.

Acá se comprueba, con un rollout de mentira:
  * que la lista de mensajes es EXACTAMENTE la misma que daba la versión vieja;
  * que el segundo refresco lee unos pocos bytes en vez del archivo;
  * que un renglón cortado a la mitad (Codex escribiendo mientras leemos) no se pierde
    ni se duplica;
  * que el título se saca de la cabeza del archivo y no leyéndolo entero;
  * que dos pantallas pidiendo al mismo tiempo no se pisan.

⚠ No toca ninguna sesión de verdad ni el panel: el rollout se fabrica en una carpeta
temporal. No gasta un token.

Correr con:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_ventana_codex
"""
import json
import sys
import tempfile
import threading
from pathlib import Path

from app.voz import sesiones_movil as sm

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fallas = []
leidos = [0]                      # bytes que las funciones pidieron al disco


def revisar(que, ok, detalle=""):
    print(("ok   " if ok else "MAL  ") + que + (f"  {detalle}" if detalle else ""))
    if not ok:
        fallas.append(que)


# --- el rollout de mentira ------------------------------------------------------------
def linea_mensaje(quien, texto, n):
    return json.dumps({"type": "response_item",
                       "timestamp": f"2026-08-25T12:{n % 60:02d}:00.000Z",
                       "payload": {"type": "message",
                                   "role": "user" if quien == "vos" else "assistant",
                                   "content": [{"type": "input_text", "text": texto}]}})


def linea_ruido(n):
    """Una salida de herramienta: lo que llena el 99 % de un rollout de verdad."""
    return json.dumps({"type": "response_item",
                       "timestamp": "2026-08-25T12:00:00.000Z",
                       "payload": {"type": "function_call_output",
                                   "output": f"linea {n} de salida " + "x" * 900}})


def escribir_rollout(ruta, mensajes, ruido_por_mensaje=40):
    with open(ruta, "w", encoding="utf-8") as f:
        for i, (quien, texto) in enumerate(mensajes):
            f.write(linea_mensaje(quien, texto, i) + "\n")
            for k in range(ruido_por_mensaje):
                f.write(linea_ruido(i * 1000 + k) + "\n")


# --- la versión VIEJA, para comparar contra ella --------------------------------------
def vieja(ruta, ultimos):
    """El algoritmo que había antes: cola que se duplica y json.loads en cada renglón."""
    est = ruta.stat()
    cola = 512 * 1024
    while True:
        inicio = max(0, est.st_size - cola)
        with open(ruta, "rb") as f:
            f.seek(inicio)
            if inicio:
                f.readline()
            lineas = f.read().decode("utf-8", errors="replace").splitlines()
        filas = []
        for linea in lineas:
            try:
                d = json.loads(linea)
            except Exception:
                continue
            if d.get("type") != "response_item":
                continue
            pay = d.get("payload") or {}
            if pay.get("type") != "message" or pay.get("role") not in ("user", "assistant"):
                continue
            txt = " ".join(c.get("text", "") for c in (pay.get("content") or [])
                           if isinstance(c, dict) and c.get("text")).strip()
            txt = sm._limpiar(txt)
            if not txt or txt.startswith("<") or sm._es_reglas_codex(txt):
                continue
            filas.append({"de": "vos" if pay["role"] == "user" else "claude",
                          "texto": sm._recortar(txt), "h": sm._hora_local(linea)})
        if len(filas) >= ultimos or inicio == 0:
            return filas[-ultimos:]
        cola = min(est.st_size, cola * 2)


def limpiar_caches():
    sm._CODEX_HILOS.clear()
    sm._CODEX_VENTANAS.clear()
    sm._CODEX_TITULOS.clear()


with tempfile.TemporaryDirectory() as tmp:
    RUTA = Path(tmp) / "rollout-de-mentira.jsonl"
    SID = "0000ffff-0000-0000-0000-000000000000"

    # Toda lectura pasa por `_codex_pedazo`: contarla ahí mide exactamente cuánto disco
    # se come cada refresco, que es de lo que se trata este arreglo.
    real_pedazo = sm._codex_pedazo

    def pedazo_contado(p, desde, hasta_max):
        leidos[0] += max(0, hasta_max - desde)
        return real_pedazo(p, desde, hasta_max)

    sm._codex_pedazo = pedazo_contado
    sm._codex_archivo = lambda sid: RUTA

    mensajes = []
    for i in range(60):
        mensajes.append(("vos", f"pregunta numero {i}"))
        mensajes.append(("codex", f"respuesta numero {i}"))
    escribir_rollout(RUTA, mensajes)
    peso = RUTA.stat().st_size
    print(f"rollout de mentira: {peso/1048576:.1f} MB, {len(mensajes)} mensajes "
          f"entre {len(mensajes)*40} renglones de ruido\n")

    # --- 1. lo mismo que la versión vieja ---------------------------------------------
    print("--- 1. dice lo mismo que la versión vieja ---")
    limpiar_caches()
    leidos[0] = 0
    nuevo = sm._codex_mensajes(SID, 40)
    esperado = vieja(RUTA, 40)
    revisar("mismos 40 mensajes que antes del arreglo", nuevo == esperado,
            f"{len(nuevo)} mensajes")
    revisar("el último es el último de verdad",
            nuevo[-1]["texto"] == "respuesta numero 59", nuevo[-1]["texto"])
    primera = leidos[0]
    print(f"     (la primera lectura leyó {primera/1024:.0f} KB de {peso/1024:.0f} KB)")

    # --- 2. el refresco siguiente lee solo lo nuevo ------------------------------------
    print("\n--- 2. mientras la sesión trabaja, cada refresco lee solo lo nuevo ---")
    leidos[0] = 0
    sm._codex_mensajes(SID, 40)
    revisar("sin cambios en el archivo, no lee nada", leidos[0] == 0, f"{leidos[0]} bytes")

    with open(RUTA, "a", encoding="utf-8") as f:
        f.write(linea_mensaje("codex", "esto lo escribió recién", 61) + "\n")
    leidos[0] = 0
    filas = sm._codex_mensajes(SID, 40)
    revisar("el mensaje nuevo aparece", filas[-1]["texto"] == "esto lo escribió recién",
            filas[-1]["texto"])
    revisar("y para eso leyó apenas lo que se escribió",
            leidos[0] < 2000, f"{leidos[0]} bytes (antes: {primera/1024:.0f} KB)")

    # cien turnos más, uno por uno, como cuando la sesión está trabajando
    leidos[0] = 0
    for i in range(100):
        with open(RUTA, "a", encoding="utf-8") as f:
            f.write(linea_ruido(90000 + i) + "\n")
            if i % 10 == 0:
                f.write(linea_mensaje("codex", f"turno {i}", i) + "\n")
        sm._codex_mensajes(SID, 40)
    revisar("cien refrescos seguidos leen menos que UNA lectura vieja",
            leidos[0] < primera, f"{leidos[0]/1024:.0f} KB contra {primera/1024:.0f} KB")

    # --- 3. un renglón cortado a la mitad ---------------------------------------------
    print("\n--- 3. Codex escribiendo justo mientras leemos ---")
    entera = linea_mensaje("codex", "quedó cortado a la mitad", 7)
    with open(RUTA, "a", encoding="utf-8") as f:
        f.write(entera[:len(entera) // 2])          # sin el final y sin el salto de línea
    filas = sm._codex_mensajes(SID, 40)
    revisar("el renglón a medio escribir no se muestra",
            all("cortado a la mitad" not in x["texto"] for x in filas))
    with open(RUTA, "a", encoding="utf-8") as f:
        f.write(entera[len(entera) // 2:] + "\n")   # Codex termina de escribirlo
    filas = sm._codex_mensajes(SID, 40)
    cuantos = sum(1 for x in filas if "cortado a la mitad" in x["texto"])
    revisar("cuando se termina de escribir aparece UNA sola vez", cuantos == 1,
            f"{cuantos} veces")

    # --- 4. el título sale de la cabeza -----------------------------------------------
    print("\n--- 4. el título no lee el archivo entero ---")
    limpiar_caches()
    leidos[0] = 0
    titulo = sm._codex_titulo(SID)
    revisar("el título es el primer mensaje tuyo", titulo == "pregunta numero 0", titulo)
    revisar("y para sacarlo no leyó todo el rollout", leidos[0] < peso / 2,
            f"{leidos[0]/1024:.0f} KB de {peso/1024:.0f} KB")

    # --- 5. dos pantallas al mismo tiempo ---------------------------------------------
    print("\n--- 5. la compu y el celular pidiendo a la vez ---")
    limpiar_caches()
    sm._codex_mensajes(SID, 40)
    with open(RUTA, "a", encoding="utf-8") as f:
        f.write(linea_mensaje("codex", "mensaje compartido", 9) + "\n")
    sm._CODEX_HILOS.clear()                 # que las 8 tengan que ir al archivo
    salidas = []

    def pedir():
        salidas.append(sm._codex_mensajes(SID, 40))

    hilos = [threading.Thread(target=pedir) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    revisar("las 8 leen exactamente lo mismo",
            all(s == salidas[0] for s in salidas))
    repetido = sum(1 for x in salidas[0] if x["texto"] == "mensaje compartido")
    revisar("y el mensaje nuevo no quedó repetido", repetido == 1, f"{repetido} veces")

    sm._codex_pedazo = real_pedazo

print("\n" + ("TODO BIEN" if not fallas else "Falló: " + ", ".join(fallas)))
if fallas:
    raise SystemExit(1)
