"""Una sesión que frena a preguntarte algo se marca en amarillo y toca la campanita (2026-11-10).

Pedido de Martín, con una captura de una charla esperando su respuesta y la lista de
carpetas igual que siempre: *"tengo que tener un nuevo color parpadeante cuando una sesión
esté preguntando algo. Con sonido si se puede."*

Lo que esta prueba cuida:
  · que la carpeta, la pestaña y la lista marquen a la que pregunta — y SOLO a esa: una
    sesión ocupada que no preguntó nada no puede prenderse (sería una alarma falsa);
  · que la campanita suene UNA vez por pregunta, y no en cada refresco de la lista;
  · que el botón de silencio la calle sin apagar el color;
  · que al contestarla (o vencer) la marca se vaya.

⚠ Datos inventados, interceptados en el contexto. El sonido no se escucha: se reemplaza el
audio del navegador por uno de mentira que cuenta las notas.

Correr con:  python -m pruebas.ver_pregunta_avisa   (con el panel prendido)
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8750"
fallas = []
AHORA = time.time()


def ses(sid, nombre, ocupada):
    # `ts` viejo: una sesión que frenó a preguntar está callada, no escribiendo.
    return {"id": sid, "nombre": nombre, "ts": AHORA - 120, "ultimo": "claude",
            "viva": False, "ocupada": ocupada, "interactiva": False, "detalle": "x"}


# alfa: la charla que tenés abierta y, al lado, otra de la misma carpeta que frenó a
# preguntar. beta: otra que pregunta, en una carpeta cuyo grupo de pestañas queda PLEGADO
# (solo se despliega el de la charla que mirás). gama: ocupada, pero trabajando.
PROYECTOS = [("alfa", [ses("alfa-1", "la que mirás", False), ses("alfa-2", "pregunta al lado", True)]),
             ("beta", [ses("beta-1", "pregunta plegada", True)]),
             ("gama", [ses("gama-1", "la que trabaja", True)])]
SESIONES = {"ok": True, "laura": "", "carpetas": {"orden": [n for n, _ in PROYECTOS], "ocultas": []},
            "proyectos": [{"proyecto": n, "cwd": "D:\\pruebas\\" + n, "vivo": False, "sesiones": s}
                          for n, s in PROYECTOS]}
PREGUNTA = {"hora": "h1", "preguntas": [{"pregunta": "¿Sigo?", "titulo": "Duda", "multi": False,
                                         "opciones": [{"etiqueta": "Sí", "detalle": ""}]}]}
# Qué contesta el chat de cada charla. Se cambia a mano durante la prueba.
pendiente = {"alfa-2": dict(PREGUNTA), "beta-1": dict(PREGUNTA)}

# El audio del navegador, de mentira: cada nota que se arma suma uno.
AUDIO_FALSO = """
window.__notas = 0;
window.AudioContext = class {
  constructor(){ this.state = 'running'; this.currentTime = 0; this.destination = {}; }
  resume(){}
  createOscillator(){ window.__notas++; return {frequency: {}, connect(){}, start(){}, stop(){}}; }
  createGain(){ return {gain: {setValueAtTime(){}, linearRampToValueAtTime(){}, exponentialRampToValueAtTime(){}},
                        connect(){}}; }
};
"""


def revisar(nombre, obtenido, esperado=True):
    ok = obtenido == esperado
    print(("ok   " if ok else "MAL  ") + nombre + ": " + repr(obtenido)
          + ("" if ok else "  (esperaba " + repr(esperado) + ")"))
    if not ok:
        fallas.append(nombre)


def portero(r):
    camino, _, consulta = r.request.url.split(BASE, 1)[-1].partition("?")
    if camino == "/movil/sesiones":
        cuerpo = SESIONES
    elif camino == "/movil/chat":
        sid = consulta.split("sid=")[-1].split("&")[0]
        cuerpo = {"ok": True, "mensajes": [{"de": "claude", "texto": "hola", "imgs": []}],
                  "ocupada": sid != "alfa-1", "pregunta": pendiente.get(sid), "tareas": None}
    elif camino == "/aspecto" and r.request.method == "GET":
        cuerpo = {"tipo": "segoe", "color": "celeste", "fondo": "azulado", "img": "",
                  "letra": "normal", "velo": "media", "rastro": "tema"}
    elif r.request.method != "GET" or camino.startswith(("/movil/", "/carpetas/", "/charlas/")):
        cuerpo = {"ok": True}
    else:
        return r.continue_()
    return r.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))


MEDIR = """() => {
  const fila = n => document.querySelector("#carpetas .carpeta[data-proy='" + n + "']");
  const tab = s => document.querySelector("#tabs .tab[data-sid='" + s + "']");
  const grupo = n => document.querySelector("#tabs .grupo[data-grupo='" + n + "']");
  const bola = tab('alfa-2') && tab('alfa-2').querySelector('.bola');
  const bolaG = grupo('beta') && grupo('beta').querySelector('.bola');
  return {
    carpetas: ['alfa', 'beta', 'gama'].filter(n => fila(n).classList.contains('con-pregunta')),
    punto: !!fila('beta').querySelector('.vive.preguntando'),
    pestanas: ['alfa-1', 'alfa-2'].filter(s => tab(s) && tab(s).classList.contains('preguntando')),
    grupos: ['alfa', 'beta'].filter(n => grupo(n) && grupo(n).classList.contains('preguntando')),
    signo: [bola, bolaG].map(b => b ? getComputedStyle(b, '::after').content : null),
    parpadea: bola ? getComputedStyle(bola).animationName : null,
    // La pestaña que pregunta mide de alto lo mismo que la de al lado: si heredara el
    // diseño de otra cosa (pasó: ver el comentario de la hoja) quedaría apilada y enorme.
    altos: [tab('alfa-1'), tab('alfa-2'), grupo('beta')].map(e => e ? Math.round(e.getBoundingClientRect().height) : null),
    estados: datos.proyectos.flatMap(p => p.sesiones.map(s => estadoSesion(s, Date.now() / 1000))),
    notas: window.__notas,
    apagado: document.querySelector('#btnSonido').classList.contains('off'),
  };
}"""
# Una vuelta de refresco, como la que hace sola la pantalla cada tanto. ⚠ Se borra la
# memoria de "a esta ya le pregunté hace poco": la pantalla espera 9 s entre una mirada y
# otra a la misma charla, y la prueba no puede esperar eso.
VUELTA = """async () => { Object.keys(pregMirada).forEach(k => delete pregMirada[k]);
                         await cargar(); await mirarPreguntas(); }"""

with sync_playwright() as p:
    nav = p.chromium.launch(headless=True)
    ctx = nav.new_context(viewport={"width": 1400, "height": 900})
    errores = []
    ctx.route("**/*", portero)
    pag = ctx.new_page()
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.on("dialog", lambda d: d.dismiss())
    pag.add_init_script("localStorage.clear();" + AUDIO_FALSO)
    pag.goto(BASE + "/sesiones", wait_until="domcontentloaded")
    pag.wait_for_selector("#carpetas .carpeta[data-proy='alfa']", timeout=15000)
    pag.wait_for_timeout(700)
    # Tres pestañas abiertas: mirás la primera de alfa.
    pag.evaluate("""() => { pendientes = {}; falladas = {}; visto = {};
      abiertas = [{sid: 'alfa-1', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'la que mirás', cerebro: ''},
                  {sid: 'alfa-2', cwd: 'D:\\\\pruebas\\\\alfa', nombre: 'pregunta al lado', cerebro: ''},
                  {sid: 'beta-1', cwd: 'D:\\\\pruebas\\\\beta', nombre: 'pregunta plegada', cerebro: ''}];
      irTab('alfa-1'); }""")
    pag.wait_for_timeout(600)

    # --- 1. Aparece la pregunta ------------------------------------------------------
    pag.evaluate(VUELTA)
    pag.wait_for_timeout(900)          # la campanita sale con una demora corta al azar
    m = pag.evaluate(MEDIR)
    revisar("⭐ se marcan las carpetas de las que preguntan, y SOLO esas", m["carpetas"], ["alfa", "beta"])
    revisar("con su puntito amarillo", m["punto"])
    revisar("⭐ se marca la pestaña que pregunta, no la que estás mirando", m["pestanas"], ["alfa-2"])
    # La pastilla resume lo que pasa adentro esté plegada o no, igual que con los otros estados.
    revisar("⭐ y la pastilla de cada grupo que tiene una adentro (la plegada también)",
            m["grupos"], ["alfa", "beta"])
    revisar("los dos puntos llevan un «?» (no depende solo del color)", m["signo"], ['"?"', '"?"'])
    revisar("y parpadean", m["parpadea"], "parpadea")
    revisar("⭐ la pestaña y la pastilla que preguntan miden lo mismo que una pestaña cualquiera",
            max(m["altos"]) - min(m["altos"]) <= 4, True)
    if max(m["altos"]) - min(m["altos"]) > 4:
        print("     altos:", m["altos"])
    revisar("⭐ el estado es uno nuevo: la ocupada que NO preguntó sigue «trabajando»",
            m["estados"], ["", "preguntando", "preguntando", "trabajando"])
    revisar("⭐ suena la campanita: dos notas por cada una que pregunta", m["notas"], 4)

    # --- 2. Los refrescos siguientes no vuelven a sonar -------------------------------
    pag.evaluate(VUELTA)
    pag.evaluate(VUELTA)
    pag.wait_for_timeout(900)
    m = pag.evaluate(MEDIR)
    revisar("⭐ una sola vez por pregunta, aunque la lista se refresque", m["notas"], 4)
    revisar("y la marca sigue ahí", m["carpetas"], ["alfa", "beta"])

    # --- 3. El botón de silencio -----------------------------------------------------
    pag.click("#btnSonido")
    pendiente["beta-1"] = dict(PREGUNTA, hora="h2")       # una pregunta NUEVA
    pag.evaluate(VUELTA)
    pag.wait_for_timeout(900)
    m = pag.evaluate(MEDIR)
    revisar("el botón queda apagado", m["apagado"])
    revisar("⭐ silenciada, una pregunta nueva no suena", m["notas"], 4)
    revisar("pero se sigue marcando", m["carpetas"], ["alfa", "beta"])
    pag.click("#btnSonido")
    pag.wait_for_timeout(200)
    revisar("al prenderlo de nuevo te muestra cómo suena", pag.evaluate("() => window.__notas"), 6)

    # --- 4. La contestaste (o venció): se va la marca ---------------------------------
    pendiente["beta-1"] = pendiente["alfa-2"] = None
    pag.evaluate(VUELTA)
    pag.wait_for_timeout(500)
    m = pag.evaluate(MEDIR)
    revisar("⭐ sin pregunta, nada queda marcado",
            [m["carpetas"], m["pestanas"], m["grupos"]], [[], [], []])
    revisar("y vuelven a «trabajando»", m["estados"], ["", "trabajando", "trabajando", "trabajando"])

    revisar("sin errores de JS", errores, [])
    nav.close()

print()
if fallas:
    print("FALLARON " + str(len(fallas)) + ": " + ", ".join(fallas))
    sys.exit(1)
print("TODO BIEN")
