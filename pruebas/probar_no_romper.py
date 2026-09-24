"""Las reglas de "No romper (costaron sangre)" del CLAUDE.md, pero ejecutables.

Hasta hoy esas reglas estaban escritas en prosa. Un agente distraido las rompe y
nadie se entera hasta que Laura queda sorda a las 3 de la manana. Aca cada regla
es un chequeo que corre en menos de dos segundos.

⭐ LA REGLA DE LAS REGLAS: cada invariante viaja con su MUTACION, o sea con la
forma exacta de romperlo. Con `--mutar` se aplica esa mutacion (en memoria, nunca
en el disco) y se exige que el chequeo FALLE. Un chequeo que no puede fallar es un
adorno, no una regla. La idea es de Ruben Marcus: "una regla que no puede hacer
fallar la version anterior del archivo es decoracion".

    python -m pruebas.probar_no_romper           # ¿esta todo bien hoy?
    python -m pruebas.probar_no_romper --mutar   # ¿los chequeos sirven para algo?
    python -m pruebas.probar_no_romper --todo    # las dos cosas

No importa ningun modulo, no toca la GPU ni el microfono, no gasta tokens y se
puede correr con todos los servicios prendidos: lee los archivos como texto.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Esto corre desde el gancho pre-commit, que captura la salida con $(...). Ahi
# Windows le da a Python una consola cp1252 y CUALQUIER caracter raro (una flecha,
# un acento, un simbolo) revienta con UnicodeEncodeError. El commit se frena solo,
# con un traceback en vez de un motivo: exactamente lo que este chequeo tiene que
# evitar. Con errors="replace" un caracter feo sale como "?" y nada mas.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")


# --- Ayudas ----------------------------------------------------------------------

def cuerpo(texto, firma):
    """El cuerpo de una funcion: desde su `def` hasta el `def` de arriba de todo
    siguiente. Sirve para preguntar por el ORDEN de las cosas adentro de una."""
    desde = texto.find(firma)
    if desde == -1:
        return ""
    hasta = texto.find("\ndef ", desde + 1)
    return texto[desde:hasta if hasta != -1 else len(texto)]


def antes_que(cuerpo_texto, primero, segundo):
    """¿`primero` aparece antes que `segundo`? Los dos tienen que estar."""
    a = cuerpo_texto.find(primero)
    b = cuerpo_texto.find(segundo)
    if a == -1:
        return f"no aparece `{primero}`"
    if b == -1:
        return f"no aparece `{segundo}`"
    if a > b:
        return f"`{segundo}` quedo ANTES de `{primero}`"
    return ""


def entradas_de_servicios(texto_panel):
    """Las entradas del dict SERVICIOS de panel.py, como (nombre, texto crudo)."""
    desde = texto_panel.find("SERVICIOS = {")
    hasta = texto_panel.find("\n}", desde)
    if desde == -1 or hasta == -1:
        return []
    bloque = texto_panel[desde:hasta]
    trozos = re.split(r'\n    "', bloque)[1:]
    return [(t.split('"', 1)[0], t) for t in trozos]


# --- Los invariantes -------------------------------------------------------------
#
# Cada uno es un dict con:
#   clave    nombre corto
#   titulo   la regla en criollo, tal como esta en el CLAUDE.md
#   por_que  que se rompe en la vida real si se incumple
#   archivos que archivos necesita leer
#   mira     funcion(textos: dict[ruta -> str]) -> "" si esta bien, o el motivo
#   mutacion (archivo, buscar, reemplazar): como se rompe la regla a proposito

INVARIANTES = [
    {
        "clave": "micro-agarrar-antes-de-soltar",
        "titulo": "_cambiar_stream() abre el microfono nuevo ANTES de cerrar el viejo",
        "por_que": ("Al reves, el 2026-08-11 quedo sin ningun microfono tras suspender la "
                    "maquina: proceso vivo, panel en verde, sorda y sin avisar a nadie."),
        "archivos": ["app/voz/voz.py"],
        "mira": lambda t: antes_que(cuerpo(t["app/voz/voz.py"], "def _cambiar_stream("),
                                    "_abrir(", "_cerrar("),
        "mutacion": ("app/voz/voz.py",
                     "        _stream = _abrir(dispositivo, extra)\n        _cerrar(viejo)",
                     "        _cerrar(viejo)\n        _stream = _abrir(dispositivo, extra)"),
    },
    {
        "clave": "wasapi-primero",
        "titulo": "El microfono se abre por WASAPI antes que por DirectSound",
        "por_que": ("DirectSound se queda entregando ceros SIN dar error cuando el "
                    "dispositivo se va y vuelve. Era la causa real del 'se muere el "
                    "microfono a cada rato'."),
        "archivos": ["app/voz/voz.py"],
        "mira": lambda t: _wasapi_primero(t["app/voz/voz.py"]),
        "mutacion": [
            ("app/voz/voz.py",
             '_APIS_PREFERIDAS = ("Windows WASAPI", "Windows DirectSound", "MME")',
             '_APIS_PREFERIDAS = ("Windows DirectSound", "Windows WASAPI", "MME")'),
            # La que importa: dejar la lista declarada pero que nadie la use.
            ("app/voz/voz.py",
             "orden.append((_APIS_PREFERIDAS.index(api), i, api))",
             "orden.append((0, i, api))"),
        ],
    },
    {
        "clave": "wasapi-auto-convert",
        "titulo": "WASAPI se abre con auto_convert=True",
        "por_que": ("WASAPI compartido exige la frecuencia nativa (48000) y nosotros "
                    "abrimos a 16000 para Whisper: sin auto_convert no abre nunca "
                    "(PaErrorCode -9997)."),
        "archivos": ["app/voz/voz.py"],
        "mira": lambda t: _auto_convert_ok(t["app/voz/voz.py"]),
        "mutacion": [
            ("app/voz/voz.py",
             "sd.WasapiSettings(auto_convert=True)",
             "sd.WasapiSettings(auto_convert=False)"),
            # La que importa: el objeto se sigue armando, pero no llega al stream.
            ("app/voz/voz.py",
             "callback=_cb, device=dispositivo, extra_settings=extra)",
             "callback=_cb, device=dispositivo)"),
        ],
    },
    {
        "clave": "tts-crecimiento",
        "titulo": "Los trozos del TTS crecen como mucho 12 % cada uno",
        "por_que": ("Piper tarda ~30 ms por letra y hablar cuesta ~33,7 ms por letra: si "
                    "un trozo crece mas de 12 % no llega a estar listo y queda un hueco "
                    "de silencio en medio de la frase."),
        "archivos": ["app/voz/voz.py"],
        "mira": lambda t: _crecimiento_ok(t["app/voz/voz.py"]),
        "mutacion": [
            ("app/voz/voz.py", "TTS_CRECIMIENTO = 1.10", "TTS_CRECIMIENTO = 1.35"),
            # La que importa: la constante queda en 1.10 y el calculo usa otra cosa.
            ("app/voz/voz.py",
             "round(TTS_TROZO_1 * (TTS_CRECIMIENTO ** n))",
             "round(TTS_TROZO_1 * (1.35 ** n))"),
        ],
    },
    {
        "clave": "prompt-una-linea",
        "titulo": "El system prompt de Laura se aplana a UNA sola linea",
        "por_que": ("Los saltos de linea rompen el .CMD de Windows y matan `--resume` "
                    "en silencio: la sesion arranca de cero sin que nadie se entere."),
        "archivos": ["app/voz/claude_voz.py"],
        "mira": lambda t: (
            "" if re.search(r'SYSTEM\s*=\s*re\.sub\(\s*r?"\\s\+"\s*,\s*" "\s*,\s*SYSTEM\s*\)',
                            t["app/voz/claude_voz.py"])
            else "ya no se aplana SYSTEM con re.sub(r'\\s+', ' ', SYSTEM)"),
        "mutacion": ("app/voz/claude_voz.py",
                     'SYSTEM = re.sub(r"\\s+", " ", SYSTEM).strip()',
                     "SYSTEM = SYSTEM.strip()"),
    },
    {
        "clave": "corte-a-las-13",
        "titulo": "El dia de Laura corta a las 13:00, no a la medianoche",
        "por_que": ("Aca se trabaja de noche: con el corte a las 12 la sesion se partia "
                    "al medio de la charla."),
        "archivos": ["app/voz/claude_voz.py"],
        "mira": lambda t: _corte_ok(t["app/voz/claude_voz.py"]),
        "mutacion": [
            ("app/voz/claude_voz.py", "CORTE_HORA = 13", "CORTE_HORA = 0"),
            # La que importa: CORTE_HORA sigue en 13 y el dia vuelve a cortar
            # a medianoche porque nadie la mira.
            ("app/voz/claude_voz.py", "if t.hour < CORTE_HORA:", "if t.hour < 0:"),
        ],
    },
    {
        "clave": "saludo-del-dia-primero",
        "titulo": "La respuesta al saludo del dia se intercepta ANTES de acciones.ejecutar",
        "por_que": ("'segui con la anterior' matchea el patron de media_playpause (tiene "
                    "'segu[ii]'): sin esto, en vez de contestarte aprieta play."),
        "archivos": ["app/voz/voz.py"],
        "mira": lambda t: antes_que(cuerpo(t["app/voz/voz.py"], "def _manejar_texto("),
                                    "responder_dia(", "acciones.ejecutar("),
        "mutacion": ("app/voz/voz.py",
                     "            print(\"claude: respuesta al saludo del dia:\", texto, flush=True)\n"
                     "            _espera_arrancar()\n"
                     "            try:\n"
                     "                r = claude_voz.responder_dia(texto)",
                     "            print(\"claude: respuesta al saludo del dia:\", texto, flush=True)\n"
                     "            _espera_arrancar()\n"
                     "            try:\n"
                     "                r = None"),
    },
    {
        "clave": "servicios-cmd-y-match",
        "titulo": "En SERVICIOS, cada 'match' aparece adentro de su propio 'cmd'",
        "por_que": ("Si no, el panel cree que el servicio esta apagado cuando en realidad "
                    "esta corriendo, y te deja prender un segundo encima."),
        "archivos": ["panel.py"],
        "mira": lambda t: _servicios_coherentes(t["panel.py"]),
        "mutacion": ("panel.py", '"match": "app.voz.voz"', '"match": "app.voz.vozz"'),
    },
    {
        "clave": "lanzar-con-guion-m",
        "titulo": "Los modulos propios se lanzan con -m, nunca por ruta al .py",
        "por_que": ("Lanzado por ruta, Python no encuentra el paquete `app` y el import "
                    "falla."),
        "archivos": ["panel.py"],
        "mira": lambda t: _lanzan_con_m(t["panel.py"]),
        "mutacion": ("panel.py",
                     '"cmd": [PY, "-m", "app.ingesta.bot_telegram"]',
                     '"cmd": [PY, "app/ingesta/bot_telegram.py"]'),
    },
    {
        "clave": "prefijos-del-chat",
        "titulo": "Los prefijos del /chat existen en las DOS puntas: quien filtra y quien imprime",
        "por_que": ("El chat en vivo del panel se dibuja del voz.log filtrando por esos "
                    "prefijos: si se renombra uno, la conversacion desaparece de la "
                    "pantalla sin que nada tire error. Y mirar solo el lado del panel no "
                    "alcanza: si el que IMPRIME deja de hacerlo, el filtro queda ahi, en "
                    "verde, esperando un texto que ya no llega."),
        "archivos": None,   # el panel filtra, pero los emisores viven repartidos por app/
        "mira": lambda t: _prefijos_ok(t),
        "mutacion": [
            ("panel.py", 'ln.startswith("claude respuesta: ")',
             'ln.startswith("claude contesto: ")'),
            # La que importa: el panel sigue filtrando y el emisor desaparece.
            ("app/voz/voz.py",
             'print(f"{etiqueta} pregunta:", re.sub(r"\\s+", " ", texto), flush=True)',
             'print("pregunta del buzon:", re.sub(r"\\s+", " ", texto), flush=True)'),
        ],
    },
    {
        "clave": "parar-interrumpe",
        "titulo": "parar() corta con el interrupt por stdin, no matando el proceso",
        "por_que": ("Matandole el arbol se muere TODO lo que la sesion mando a segundo "
                    "plano, y el turno siguiente solo ve 'No completion record was "
                    "found'. El registro del background vive adentro del proceso."),
        "archivos": ["app/voz/sesiones_movil.py"],
        "mira": lambda t: (
            "" if "_interrumpir(viva)" in cuerpo(t["app/voz/sesiones_movil.py"], "def parar(")
            else "parar() ya no llama a _interrumpir(): volvio a matar el proceso"),
        "mutacion": ("app/voz/sesiones_movil.py",
                     "    if not _interrumpir(viva):",
                     "    if not _apagar_viva(viva, 'parar'):"),
    },
    {
        "clave": "sesion-vive-entre-turnos",
        "titulo": "mandar() reusa el proceso vivo de la sesion, no arranca uno por mensaje",
        "por_que": ("Un `claude -p` por mensaje mata el trabajo en segundo plano de la "
                    "sesion. Tiene que ser el MISMO proceso (VIVAS)."),
        "archivos": ["app/voz/sesiones_movil.py"],
        "mira": lambda t: (
            "" if "_conseguir_viva(" in cuerpo(t["app/voz/sesiones_movil.py"], "def mandar(")
            else "mandar() ya no usa _conseguir_viva(): la sesion dejo de vivir entre turnos"),
        "mutacion": ("app/voz/sesiones_movil.py",
                     "    viva = _conseguir_viva(cwd, sid, modelo, esf, modo_de(sid))",
                     "    viva = _arrancar_viva(cwd, sid, modelo, esf, modo_de(sid))"),
    },
    {
        "clave": "no-dormir-con-trabajo-abajo",
        "titulo": "El barrendero nunca apaga una sesion que tiene trabajo en segundo plano",
        "por_que": ("Desde el 2026-09-03 las sesiones se duermen por falta de memoria y no "
                    "por un tope fijo, asi que el barrido pasa MUCHO mas seguido que la "
                    "hora vieja. `turno.locked()` solo cuida el turno en curso, y el "
                    "trabajo en segundo plano DURA MAS que el turno: sin este guardian, "
                    "dormir por presion mata justo lo que protege la regla de que el "
                    "proceso viva entre turnos, y el sintoma es trabajo que desaparece en "
                    "silencio. Ademas hay que buscar el claude.exe con _cli_de(): "
                    "`viva.proc` es el .cmd que lo lanza, y contar SUS hijos da siempre "
                    "por lo menos uno (el propio CLI)."),
        "archivos": ["app/voz/sesiones_movil.py"],
        "mira": lambda t: _guardian_background(t["app/voz/sesiones_movil.py"]),
        "mutacion": ("app/voz/sesiones_movil.py",
                     "            and not _tiene_trabajo_abajo(viva))",
                     "            )"),
    },
    {
        "clave": "rutas-en-rutas-py",
        "titulo": "Ningun modulo de app/ arma rutas con Path(__file__) ni absolutas",
        "por_que": ("Asi se rompio en 11 lugares al armar `app/`: el archivo se busca al "
                    "lado del modulo y no del proyecto, y se rompe en silencio en cuanto "
                    "el modulo cambia de carpeta. Las rutas van en app/rutas.py."),
        "archivos": None,   # barre todo app/**.py
        "mira": lambda t: _rutas_centralizadas(t),
        "mutacion": ("app/voz/voz.py",
                     '_APIS_PREFERIDAS = (',
                     '_UNA_RUTA_MAL = Path(__file__).with_name("cosa.json")\n_APIS_PREFERIDAS = ('),
    },
    {
        "clave": "navegador-sin-javascript",
        "titulo": "La sesion con navegador NO puede ejecutar JavaScript en la pagina",
        "por_que": ("`javascript_tool` se saltea la interfaz entera: puede mandar un "
                    "formulario sin apretar ningun boton, o sea justo lo que las reglas "
                    "del navegador le piden que no haga sin preguntar. Es el UNICO "
                    "candado duro que corre siempre, porque un clic viaja como "
                    "coordenadas y el panel no puede ver que boton es."),
        "archivos": ["app/voz/sesiones_movil.py"],
        # Se miran las DOS puntas: que el lanzador pase el flag, y que la constante que
        # pasa sea de verdad la herramienta de JavaScript. Vaciar la constante rompe el
        # candado sin tocar el lanzador, y al reves tambien.
        "mira": lambda t: _js_prohibido(t["app/voz/sesiones_movil.py"]),
        "mutacion": ("app/voz/sesiones_movil.py",
                     'cmd += ["--chrome", "--disallowedTools", CHROME_JS,',
                     'cmd += ["--chrome",'),
    },
    {
        "clave": "chrome-se-abre-al-usarlo",
        "titulo": "El Chrome del proyecto se abre al USARLO, no al abrir la charla",
        "por_que": ("Como el navegador de base lo hereda toda carpeta, abrirlo en el "
                    "arranque significa una ventana de Chrome en cada charla de cada "
                    "proyecto, la use o no — que es de lo que se quejo Martin el "
                    "2026-08-29. Y para tener ese momento hubo que sacar el atajo de "
                    "permitir el servidor entero: sin pedido de permiso no hay donde "
                    "enterarse de que la sesion va a navegar."),
        "archivos": ["app/voz/sesiones_movil.py"],
        "mira": lambda t: _chrome_perezoso(t["app/voz/sesiones_movil.py"]),
        "mutacion": ("app/voz/sesiones_movil.py",
                     "    if perfil:\n        # ⚠ Aca NO se abre el Chrome",
                     "    if perfil:\n        abrir_chrome_perfil(perfil)\n"
                     "        # ⚠ Aca NO se abre el Chrome"),
    },
    {
        "clave": "prompt-navegador-una-linea",
        "titulo": "Las reglas del navegador viajan en UNA sola linea",
        "por_que": ("Van pegadas al --append-system-prompt, y un `\\n` rompe el .CMD de "
                    "Windows y mata `--resume` EN SILENCIO. Es la misma regla por la que "
                    "el system prompt de Laura se aplana."),
        "archivos": ["app/voz/sesiones_movil.py"],
        "mira": lambda t: _reglas_navegador_planas(t["app/voz/sesiones_movil.py"]),
        "mutacion": ("app/voz/sesiones_movil.py",
                     '    "Tenes el Chrome de este proyecto',
                     '    "Tenes el Chrome de este proyecto.\\n'),
    },
    {
        "clave": "claude-md-apunta-al-chequeo",
        "titulo": "El CLAUDE.md sigue diciendo que estas reglas se pueden correr",
        "por_que": ("Si se pierde el puntero a pruebas.probar_no_romper, la proxima sesion "
                    "lee las reglas como prosa y no se entera de que hay un chequeo que las "
                    "verifica en dos segundos. El mecanismo no se rompe: se vuelve invisible, "
                    "que es peor porque nadie lo va a extranar."),
        "archivos": ["CLAUDE.md"],
        "mira": lambda t: ("" if "pruebas.probar_no_romper" in t["CLAUDE.md"]
                           else "el CLAUDE.md ya no menciona pruebas.probar_no_romper"),
        "mutacion": ("CLAUDE.md", "pruebas.probar_no_romper", "pruebas.probar_todo"),
    },
    {
        "clave": "semaforo-en-variables",
        "titulo": "El verde, el rojo y el ambar de estado salen de una variable",
        "por_que": ("Para que Martin pueda ELEGIR esos colores tienen que salir de "
                    "--ok/--mal/--aviso. Uno escrito a mano no se ve roto: ese elemento "
                    "y solo ese deja de obedecer al color elegido, y eso se descubre "
                    "mirando la pantalla con lupa. Antes del 2026-08-29 habia once verdes "
                    "distintos y el panel usaba otro que el celular para decir lo mismo."),
        "archivos": ["panel.py", "app/estaticos/sesiones.html"],
        # En lambda como los demas: la lista se arma antes de que existan las funciones.
        "mira": lambda t: _semaforo_en_variables(t),
        "mutacion": ("app/estaticos/sesiones.html",
                     ".tab.fallada .bola{background:var(--mal-txt)}",
                     ".tab.fallada .bola{background:#ff6b6b}"),
    },
    {
        "clave": "tintas-con-respaldo",
        "titulo": "Todo color de pantalla enganchado a una tinta lleva su respaldo",
        "por_que": ("El tema claro anda porque cada color se escribe "
                    "`var(--cRRGGBB,#rrggbb)`: el respaldo ES el color de siempre, y por "
                    "eso el tema oscuro queda identico sin depender de ningun calculo. "
                    "Un `var(--cRRGGBB)` sin respaldo se ve bien en claro y deja el "
                    "elemento SIN COLOR en oscuro — que es el tema que usa todos los "
                    "dias. Se rompe con una coma de menos y no lo avisa nadie."),
        "archivos": ["panel.py", "app/estaticos/sesiones.html"],
        "mira": lambda t: _tintas_con_respaldo(t),
        "mutacion": ("panel.py", "var(--c232a35,#232a35)", "var(--c232a35)"),
    },
    {
        "clave": "tintas-solo-con-tinte",
        "titulo": "Sin tinte elegido, en oscuro las tintas se BORRAN",
        "por_que": ("Es lo que sostiene que el tema oscuro quede identico por "
                    "construccion: `aplicar()` hace `removeProperty` y cada "
                    "`var(--cRRGGBB,#rrggbb)` cae en su respaldo, que es el color de "
                    "siempre. Desde el tinte por rol (2026-08-29) esa misma vuelta "
                    "ADEMAS define tintas cuando hay un color elegido — si alguien "
                    "simplifica el `if` y las define siempre, la pantalla de quien no "
                    "eligio nada pasa a depender de un calculo, y las capturas 'pixel a "
                    "pixel' dejan de valer sin que nada avise."),
        "archivos": ["app/estaticos/aspecto.js"],
        "mira": lambda t: ("" if _borra_tintas(t["app/estaticos/aspecto.js"])
                           else "aplicar() ya no borra las tintas cuando no hay tinte"),
        "mutacion": ("app/estaticos/aspecto.js",
                     "if (!claro && !tin) {", "if (false) {"),
    },
    {
        "clave": "vigia-avisa-por-telegram",
        "titulo": "El vigia del WhatsApp avisa por Telegram, no por WhatsApp",
        "por_que": ("Los avisos de WhatsApp de la skill `avisar` salen por la MISMA "
                    "instancia de Evolution que este vigia mira ('Laura', en "
                    "~/.claude/whatsapp.json). Puesto en whatsapp, el aviso de que se "
                    "cayo WhatsApp viaja por el cable cortado y no llega nunca: el vigia "
                    "queda mudo justo cuando hace falta, que es el mismo silencio que "
                    "dejo pasar dos dias el 2026-08-29. Se ve bien y no sirve para nada."),
        # El vigilar.json de cada uno no se versiona: la regla se cuida en el molde, que
        # es de donde lo copia todo el que instala el proyecto.
        "archivos": ["vigilar.ejemplo.json"],
        "mira": lambda t: ("" if '"canal": "telegram"' in t["vigilar.ejemplo.json"]
                           else "vigilar.ejemplo.json ya no avisa por telegram"),
        "mutacion": ("vigilar.ejemplo.json", '"canal": "telegram"', '"canal": "whatsapp"'),
    },
    {
        "clave": "cli-sin-ventana-negra",
        "titulo": "Nada que corra en un servicio abre una consola",
        "por_que": ("Los servicios los lanza el panel SIN consola, asi que cuando uno de "
                    "ellos arranca un programa de consola (un .cmd como `claude` o "
                    "`codex`, ffmpeg, ssh, git, o cualquier cosa por `shell=True`) Windows "
                    "le regala al hijo una consola nueva y VISIBLE: una ventana negra que "
                    "se le planta a Martin encima de lo que este haciendo. Se arreglo en "
                    "sesiones_movil.py el 2026-08-17 y en otros siete archivos el "
                    "2026-09-06, cuando volvio a aparecer por todos los lugares que habian "
                    "quedado afuera de aquel arreglo. La salida se captura igual por los "
                    "pipes: la marca no esconde ningun log."),
        "archivos": ["app/voz/claude_voz.py", "app/voz/codex_voz.py",
                     "app/voz/sesiones_movil.py", "app/voz/acciones.py",
                     "app/voz/spotify.py", "app/voz/adversarial.py",
                     "app/nucleo/core.py", "app/nucleo/entrantes.py"],
        "mira": lambda t: _cli_sin_ventana(t),
        "mutacion": [
            ("app/voz/claude_voz.py",
             'errors="replace", bufsize=1,\n'
             '                                 creationflags=getattr(subprocess, '
             '"CREATE_NO_WINDOW", 0))',
             'errors="replace", bufsize=1)'),
            ("app/voz/codex_voz.py",
             'errors="replace", bufsize=1,\n'
             '                                creationflags=getattr(subprocess, '
             '"CREATE_NO_WINDOW", 0))',
             'errors="replace", bufsize=1)'),
        ],
    },
]

# ⭐ El piso. La idea es de Marcus y es simple: el que hace el cambio no puede
# tocar la vara que lo mide. Sin esto, la salida mas facil para un agente al que
# el commit se le frena es borrar el invariante que le molesta, y el chequeo
# quedaria en verde con menos reglas que ayer. Si agregas una, subi el numero.
MINIMO_INVARIANTES = 19


# --- Chequeos que no entran en una linea -----------------------------------------

# ⭐ LA TRAMPA DE ESTOS CUATRO: es facilisimo escribir el chequeo sobre la
# DECLARACION de la constante ("¿dice 13?") y creer que con eso alcanza. No
# alcanza: si el codigo deja de USARLA, la constante queda de adorno, el chequeo
# sigue en verde y la regla ya no protege nada. Le paso exactamente eso a Ruben
# Marcus: un mutante que borraba un arreglo real le paso 20 de 22 chequeos porque
# el invariante leia la declaracion de una constante en vez de su uso. Por eso
# cada uno de estos mira las dos cosas, y trae una mutacion "borro el uso y dejo
# la declaracion" que lo demuestra.

def _llamada(texto, i):
    """El texto de una llamada, desde su `(` hasta el parentesis que la cierra.
    ⚠ Hace falta contar parentesis y no cortar por cantidad de letras: con un
    trozo fijo el chequeo se lleva puesta la llamada de al lado, encuentra ahi el
    `creationflags` del vecino y da verde por el motivo equivocado."""
    nivel = 0
    for j in range(i, len(texto)):
        if texto[j] == "(":
            nivel += 1
        elif texto[j] == ")":
            nivel -= 1
            if nivel == 0:
                return texto[i:j + 1]
    return texto[i:]


def _cli_sin_ventana(t):
    for arch, texto in t.items():
        for m in re.finditer(r"subprocess\.(Popen|run|call|check_output)\s*\(", texto):
            abre = texto.index("(", m.start())
            if "creationflags" not in _llamada(texto, abre):
                linea = texto[:m.start()].count("\n") + 1
                return (f"{arch}:{linea}: hay un subprocess.{m.group(1)} sin "
                        "creationflags. Corriendo adentro de un servicio, eso le abre "
                        "una consola negra en la pantalla")
    return ""


def _wasapi_primero(texto):
    if not re.search(r'_APIS_PREFERIDAS\s*=\s*\(\s*"Windows WASAPI"', texto):
        return "WASAPI ya no es el primero de _APIS_PREFERIDAS"
    if "_APIS_PREFERIDAS.index(" not in cuerpo(texto, "def _candidatos_micro("):
        return ("_candidatos_micro() ya no ordena por _APIS_PREFERIDAS.index(): la lista "
                "quedo declarada pero de adorno, y el micro se abre por cualquier camino")
    return ""


def _auto_convert_ok(texto):
    if "WasapiSettings(auto_convert=True)" not in cuerpo(texto, "def _extra_de("):
        return "_extra_de() ya no devuelve sd.WasapiSettings(auto_convert=True)"
    # Y que ese objeto LLEGUE al stream: sin extra_settings, WASAPI compartido no
    # abre a 16 kHz y el asistente se queda sordo con el objeto bien armado al lado.
    sin = sum(1 for m in re.finditer(r"sd\.InputStream\(", texto)
              if "extra_settings" not in texto[m.start():m.start() + 400])
    if sin:
        return f"hay {sin} sd.InputStream() que se abre sin pasarle extra_settings"
    return ""


def _crecimiento_ok(texto):
    m = re.search(r"^TTS_CRECIMIENTO\s*=\s*([\d.]+)", texto, re.M)
    if not m:
        return "no encontre TTS_CRECIMIENTO"
    valor = float(m.group(1))
    if valor > 1.12:
        return f"TTS_CRECIMIENTO = {valor}: pasa de 1.12 y va a dejar huecos de silencio"
    if "TTS_CRECIMIENTO **" not in cuerpo(texto, "def _partir_para_tts("):
        return ("_partir_para_tts() ya no calcula el largo del trozo con TTS_CRECIMIENTO: "
                "la constante quedo de adorno")
    return ""


def _corte_ok(texto):
    m = re.search(r"^CORTE_HORA\s*=\s*(\d+)", texto, re.M)
    if not m:
        return "no encontre CORTE_HORA"
    if int(m.group(1)) != 13:
        return f"CORTE_HORA = {m.group(1)}, tiene que ser 13"
    if "t.hour < CORTE_HORA" not in cuerpo(texto, "def _dia_de("):
        return ("_dia_de() ya no compara contra CORTE_HORA: el dia de Laura volvio a "
                "cortar a medianoche y la constante quedo de adorno")
    return ""


def _servicios_coherentes(texto):
    entradas = entradas_de_servicios(texto)
    if not entradas:
        return "no pude leer el dict SERVICIOS"
    fallas = []
    for nombre, crudo in entradas:
        m = re.search(r'"match":\s*"([^"]+)"', crudo)
        if not m:
            continue                      # el tunel se identifica por proc_name
        if m.group(1) not in crudo.split('"cmd"', 1)[-1]:
            fallas.append(f'{nombre}: el match "{m.group(1)}" no esta en su cmd')
    return "; ".join(fallas)


def _lanzan_con_m(texto):
    entradas = entradas_de_servicios(texto)
    if not entradas:
        return "no pude leer el dict SERVICIOS"
    fallas = []
    for nombre, crudo in entradas:
        m = re.search(r'"cmd":\s*\[PY,\s*("[^"]*")', crudo)
        if m and m.group(1) != '"-m"':
            fallas.append(f'{nombre}: se lanza con PY, {m.group(1)} en vez de "-m"')
    return "; ".join(fallas)


# Los que nombra el CLAUDE.md como imprescindibles para el /chat del panel.
PREFIJOS_DEL_CHAT = [
    "comando: ", "respuesta: ", "claude respuesta: ", "dictado: ", "aviso sistema: ",
    "lectura respuesta [", "lectura: ", "telegram pregunta: ", "telegram respuesta: ",
]


def _emisores_de(prefijo, textos):
    """Quien IMPRIME este prefijo. Hay que reconocer las tres formas que usamos,
    porque si no el chequeo grita por un prefijo que si se emite:

        print("claude respuesta:", r)          -> literal
        _avisar_sistema(t, prefijo="aviso sistema")  -> por parametro
        print(f"{etiqueta} pregunta:", t)      -> con la 1ra palabra en una variable

    La tercera es la que casi me hace anunciar un bug que no existia. Para no
    aceptar cualquier print con variable, se exige ademas que la palabra que falta
    ("telegram") aparezca como texto en el mismo archivo.
    """
    raiz = prefijo.rstrip(" ").rstrip("[").rstrip(" ").rstrip(":")
    palabras = raiz.split()
    literal = re.compile(r'(?:print\(\s*|prefijo\s*=\s*)f?["\']' + re.escape(raiz))
    interp = (re.compile(r'print\(\s*f["\']\{[^}]+\}\s+' + re.escape(" ".join(palabras[1:])))
              if len(palabras) > 1 else None)
    valor = re.compile(r'["\']' + re.escape(palabras[0]) + r'["\']')
    salida = []
    for ruta, texto in textos.items():
        if literal.search(texto) or (interp and interp.search(texto) and valor.search(texto)):
            salida.append(ruta)
    return salida


def _prefijos_ok(textos):
    panel = textos.get("panel.py", "")
    if not panel:
        return "no pude leer panel.py"
    faltan = [p for p in PREFIJOS_DEL_CHAT if f'ln.startswith("{p}")' not in panel]
    if faltan:
        return "el /chat ya no filtra por: " + ", ".join(repr(p) for p in faltan)
    huerfanos = [p for p in PREFIJOS_DEL_CHAT if not _emisores_de(p, textos)]
    if huerfanos:
        return ("el /chat filtra por prefijos que ya no imprime NADIE (la conversacion "
                "no va a aparecer en la pantalla y nada tira error): "
                + ", ".join(repr(p) for p in huerfanos))
    return ""


# Excepciones al "las rutas van en rutas.py", con su razon. NO agregar nada aca sin
# entender por que: cada linea es deuda que alguien va a tener que pagar.
EXCEPCIONES_RUTAS = {
    # Deuda real, anotada el 2026-08-25: deberia ser una constante de rutas.py.
    "app/ingesta/webhook_wasender.py": "PENDIENTE: ESPERANDO deberia vivir en rutas.py",
    # Deuda real, anotada el 2026-08-25: carpeta de datos al lado del modulo.
    "app/nucleo/analizar_gemini.py": "PENDIENTE: DIR_PERFILES deberia vivir en rutas.py",
}


def _guardian_background(texto):
    """Dormir una sesion por falta de memoria no puede llevarse su trabajo de fondo."""
    d = cuerpo(texto, "def _dormible(")
    if "_tiene_trabajo_abajo(" not in d:
        return ("_dormible() ya no consulta _tiene_trabajo_abajo(): dormir por falta de "
                "memoria se lleva puesto el trabajo en segundo plano")
    if "turno.locked()" not in d:
        return "_dormible() ya no mira si hay un turno en curso"
    if "_cli_de(" not in cuerpo(texto, "def _tiene_trabajo_abajo("):
        return ("_tiene_trabajo_abajo() ya no busca el claude.exe con _cli_de(): contando "
                "los hijos del .cmd la respuesta es siempre 'si trabaja' y no se duerme "
                "ninguna sesion nunca")
    if "_dormible(" not in cuerpo(texto, "def _barrer_vivas("):
        return "_barrer_vivas() ya no filtra por _dormible(): puede apagar una que trabaja"
    return ""


def _js_prohibido(texto):
    """El lanzador tiene que pasar --disallowedTools con la herramienta de JavaScript."""
    cuerpo_lanzador = cuerpo(texto, "def _arrancar_viva(")
    if '"--disallowedTools", CHROME_JS' not in cuerpo_lanzador:
        return "_arrancar_viva() ya no pasa --disallowedTools con CHROME_JS"
    if not re.search(r'CHROME_JS\s*=\s*"mcp__claude-in-chrome__javascript_tool"', texto):
        return "CHROME_JS ya no apunta a la herramienta de JavaScript del navegador"
    return ""


def _chrome_perezoso(texto):
    """El Chrome del proyecto NO se abre al arrancar la sesion, sino al usarlo.

    Se miran las dos puntas: que el lanzador no lo abra, y que el portero SI lo abra.
    Con solo la primera, sacar la apertura de los dos lados dejaria a las sesiones sin
    navegador y la regla diria que esta todo bien.
    """
    if "abrir_chrome_perfil(" in cuerpo(texto, "def _arrancar_viva("):
        return ("_arrancar_viva() volvio a abrir el Chrome al arrancar: una ventana en "
                "cada charla de cada proyecto, la use o no")
    if "_asegurar_chrome(viva)" not in cuerpo(texto, "def _turno("):
        return ("_turno() ya no abre el Chrome al pedir una herramienta del navegador: "
                "la sesion se queda sin navegador")
    if "mcp__claude-in-chrome\"" in cuerpo(texto, "def _permitidas_de("):
        return ("_permitidas_de() volvio a permitir el servidor entero: sin pedido de "
                "permiso no hay ningun momento donde abrir la ventana")
    # ⚠⚠ La otra mitad, y es la que no se ve: sin `permissions.ask` el CLI concede solo
    # las herramientas del navegador que considera de lectura, el portero no se entera y
    # la ventana no se abre. Medido contra el CLI real el 2026-08-29.
    if '"--settings", json.dumps(AJUSTES_CHROME)' not in cuerpo(texto,
                                                               "def _arrancar_viva("):
        return ("_arrancar_viva() ya no pasa --settings con AJUSTES_CHROME: las "
                "herramientas de lectura del navegador se van a conceder solas")
    if not re.search(r'AJUSTES_CHROME\s*=\s*\{"permissions": \{"ask": '
                     r'\["mcp__claude-in-chrome"\]\}\}', texto):
        return "AJUSTES_CHROME ya no pide preguntar por las herramientas del navegador"
    return ""


def _reglas_navegador_planas(texto):
    """REGLAS_NAVEGADOR no puede traer un salto de linea adentro.

    Se lee el TEXTO del archivo y no la constante importada a proposito: este chequeo
    corre desde el gancho pre-commit y no importa ningun modulo. Un `\\n` escrito
    adentro de los pedazos de cadena es exactamente el defecto que se busca.
    """
    m = re.search(r"REGLAS_NAVEGADOR = \((.*?)\n\)", texto, re.S)
    if not m:
        return "no encuentro REGLAS_NAVEGADOR en sesiones_movil.py"
    if "\\n" in m.group(1) or "\\r" in m.group(1):
        return "REGLAS_NAVEGADOR tiene un salto de linea: rompe --resume en silencio"
    return ""


def _tintas_con_respaldo(textos):
    """Ninguna tinta puede quedar sin su color de respaldo.

    La forma buena es `var(--c232a35,#232a35)`. Sin la coma y el color, en el tema oscuro
    —que no define ninguna tinta a proposito— ese elemento se queda sin color: hereda el
    del padre o cae en el negro del navegador. Y como el que lo escribe suele estar
    probando el tema claro, ahi se ve perfecto.
    """
    import re as _re
    malas = []
    for arch, t in textos.items():
        for m in _re.finditer(r"var\(--c([0-9a-f]{6})(-rgb)?\s*([,)])", t):
            if m.group(3) == ")":
                malas.append(f"{arch}: --c{m.group(1)}{m.group(2) or ''} sin respaldo")
    return "; ".join(malas[:3])


def _borra_tintas(js):
    """En tema oscuro y sin tinte elegido, `aplicar()` tiene que BORRAR cada tinta.

    Se busca la vuelta entera —la condicion y los dos `removeProperty`— y no solo la
    palabra: definirlas con su valor original parece lo mismo y no lo es. Borrando, el
    respaldo del `var()` es la unica fuente del color y no hay calculo que pueda salir mal.
    """
    import re as _re
    m = _re.search(r"if \(!claro && !tin\) \{(.{0,220}?)\}", js, _re.S)
    return bool(m and m.group(1).count("removeProperty") >= 2)


def _semaforo_en_variables(textos):
    """El verde, el rojo y el ambar de estado no pueden volver a escribirse a mano.

    El 2026-08-29, para que Martin pudiera ELEGIR esos colores, hubo que juntarlos: habia
    once verdes distintos repartidos, y el panel decia #22c55e donde el celular decia
    #3ddc84 para significar lo MISMO. Ahora salen de `--ok`, `--mal` y `--aviso` (con sus
    peldanos -2, -txt, -bd y -bg), que calcula `aspecto.js`.

    Un color de estado escrito a mano no rompe nada a la vista: simplemente ESE elemento
    deja de obedecer al color elegido, y el defecto se descubre mirando la pantalla con
    lupa. Por eso es una regla y no un comentario.

    ⛔ Lo que NO cuenta como falta, y por eso se saltea: la rueda arcoiris (`conic-gradient`
    es un adorno fijo), las paletas de acento copiadas en las pantallas (`arena: [...]`),
    la paleta de DIBUJO de la pizarra (que son colores de objetos, no de estado) y las
    entidades HTML como `&#127916;`, que son emojis y no colores.
    """
    import colorsys
    familias = []
    for ruta, texto in textos.items():
        if ruta == "panel.py":
            # Solo las dos pantallas convertidas; la pizarra tiene su paleta de dibujo.
            # El tramo del panel termina donde arranca la seccion de la pizarra: su
            # paleta de papelitos (COLORES_NOTA) es de dibujo, no de estado.
            i, f = texto.find("PAGINA = "), texto.find("\n# --- Pizarra:")
            j = texto.find("MOVIL_HTML = ")
            tramos = [("PAGINA", texto[i:f]), ("MOVIL_HTML", texto[j:])]
        elif ruta.endswith("sesiones.html"):
            tramos = [("sesiones.html", texto)]
        else:
            continue
        for nombre, s in tramos:
            for m in re.finditer(r"#[0-9a-fA-F]{6}\b", s):
                h = m.group(0).lower()
                r, g, b = (int(h[k:k + 2], 16) / 255 for k in (1, 3, 5))
                hh, lum, sat = colorsys.rgb_to_hls(r, g, b)
                hh *= 360
                # ⚠ Los umbrales no son a gusto: con sat>=.30 y lum<=.93 el chequeo
                # marcaba `#e7f3ee`, que es el texto casi blanco de la burbuja verde de
                # WhatsApp del celular — un blanco con un dedo de verde, no un estado.
                # Un casi-blanco tiene poca sustancia de color aunque la cuenta de
                # saturacion diga que no.
                if sat < .40 or lum < .12 or lum > .88:
                    continue
                if not (90 <= hh <= 165 or hh >= 335 or hh <= 18 or 30 <= hh <= 62):
                    continue
                ini = s.rfind("\n", 0, m.start()) + 1
                linea = s[ini:s.find("\n", m.end())]
                if (s[m.start() - 1:m.start()] == "&" or "conic-gradient" in linea
                        or re.search(r"(arena|turquesa|celeste|violeta|fucsia)\s*:", linea)):
                    continue
                familias.append(f"{nombre} tiene {h} a mano: {linea.strip()[:60]}")
    return "; ".join(familias[:3])


def _rutas_centralizadas(textos):
    fallas = []
    for ruta, texto in textos.items():
        if ruta == "app/rutas.py" or not ruta.startswith("app/"):
            continue
        if ruta in EXCEPCIONES_RUTAS:
            continue
        if "Path(__file__)" in texto:
            fallas.append(f"{ruta}: usa Path(__file__)")
        if re.search(r'["\'][A-Za-z]:[\\/]+IA[\\/]+wpp-transcriptor', texto):
            fallas.append(f"{ruta}: tiene una ruta absoluta al proyecto")
    return "; ".join(fallas)


# --- Motor -----------------------------------------------------------------------

def _leer(archivos):
    """Los textos que necesita un invariante. `None` = todos los .py de app/ MAS
    panel.py (que no vive en app/ pero es la otra punta de varias reglas)."""
    if archivos is None:
        salida = {}
        for p in sorted(RAIZ.joinpath("app").rglob("*.py")) + [RAIZ / "panel.py"]:
            salida[p.relative_to(RAIZ).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        return salida
    return {a: RAIZ.joinpath(a).read_text(encoding="utf-8", errors="replace") for a in archivos}


def _mutaciones_de(inv):
    """Un invariante puede traer una mutacion sola o una lista. Siempre lista."""
    m = inv["mutacion"]
    return list(m) if isinstance(m, list) else [m]


def rotos_ahora():
    """Los invariantes que no se cumplen, SIN imprimir nada. Lo usa el gancho de
    fin de turno, que necesita el resultado y no la pantalla."""
    rotos = []
    for inv in INVARIANTES:
        motivo = inv["mira"](_leer(inv["archivos"]))
        if motivo:
            rotos.append((inv, motivo))
    return rotos


def mirar_todo():
    """¿Esta el arbol como tiene que estar? Devuelve la lista de los que fallaron."""
    print("\n=== Las reglas, contra el codigo de hoy ===\n")
    porclave = {i["clave"]: m for i, m in rotos_ahora()}
    rotos = []
    for inv in INVARIANTES:
        motivo = porclave.get(inv["clave"], "")
        if motivo:
            rotos.append((inv, motivo))
            print(f"  ROTO  {inv['titulo']}")
            print(f"        -> {motivo}")
            print(f"        por que importa: {inv['por_que']}")
        else:
            print(f"  ok    {inv['titulo']}")
    return rotos


def mutar_todo():
    """¿Sirven de algo los chequeos? Se rompe cada regla a proposito y se exige que
    el chequeo la cace. El que no la caza es un adorno."""
    print("\n=== Las mutaciones: cada regla tiene que poder fallar ===\n")
    adornos = []
    for inv in INVARIANTES:
        muts = _mutaciones_de(inv)
        for n, (archivo, buscar, reemplazar) in enumerate(muts, 1):
            de = f"{inv['titulo']}" + (f"  [mutacion {n} de {len(muts)}]" if len(muts) > 1 else "")
            textos = _leer(inv["archivos"])
            if archivo not in textos:
                textos = _leer([archivo] + list(textos))
            if buscar not in textos[archivo]:
                adornos.append((inv, "la mutacion ya no encaja con el codigo: "
                                     f"no encontre en {archivo} el texto que habia que romper"))
                print(f"  VIEJA {de}")
                print(f"        -> la mutacion no encaja mas con {archivo}")
                continue
            textos[archivo] = textos[archivo].replace(buscar, reemplazar, 1)
            motivo = inv["mira"](textos)
            if motivo:
                print(f"  ok    {de}  (roto a proposito -> {motivo[:64]})")
            else:
                adornos.append((inv, f"la mutacion {n} pasa igual con la regla rota"))
                print(f"  ADORNO {de}")
                print("        -> lo rompi y el chequeo siguio en verde: no sirve de nada")
    return adornos


def main():
    args = sys.argv[1:]
    solo_mutar = "--mutar" in args
    todo = "--todo" in args or not args

    if len(INVARIANTES) < MINIMO_INVARIANTES:
        print(f"\nHAY MENOS REGLAS QUE ANTES: {len(INVARIANTES)}, y el piso es "
              f"{MINIMO_INVARIANTES}.")
        print("Alguien saco un invariante. Si fue a proposito, bajale el piso a mano y "
              "explica por que; si no, volve a ponerlo.")
        return 1

    rotos, adornos = [], []
    if todo or not solo_mutar:
        rotos = mirar_todo()
    if todo or solo_mutar:
        adornos = mutar_todo()

    print()
    if not rotos and not adornos:
        print(f"TODO BIEN - {len(INVARIANTES)} reglas, todas cumplidas y todas capaces de fallar.")
        if EXCEPCIONES_RUTAS:
            pendientes = [r for r, m in EXCEPCIONES_RUTAS.items() if m.startswith("PENDIENTE")]
            if pendientes:
                print(f"\n[!] Deuda anotada a proposito ({len(pendientes)} archivos con rutas fuera de "
                      "rutas.py, en EXCEPCIONES_RUTAS):")
                for r in pendientes:
                    print(f"    {r}: {EXCEPCIONES_RUTAS[r]}")
        return 0

    if rotos:
        print(f"HAY {len(rotos)} REGLA(S) ROTA(S). Cada una esta explicada arriba y en el CLAUDE.md.")
    if adornos:
        print(f"HAY {len(adornos)} CHEQUEO(S) QUE NO SIRVEN:")
        for inv, motivo in adornos:
            print(f"    {inv['clave']}: {motivo}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
