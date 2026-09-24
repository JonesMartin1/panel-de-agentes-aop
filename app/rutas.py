"""Rutas del proyecto, en UN solo lugar.

Antes cada modulo resolvia sus archivos con `Path(__file__).with_name("...")`.
Eso funcionaba mientras todos los .py estaban sueltos en la raiz, pero se rompe
en silencio en cuanto un modulo cambia de carpeta: el archivo se busca al lado
del modulo, no del proyecto.

Aca esta la unica fuente de verdad. `rutas.py` vive siempre en `app/`, asi que
la raiz del proyecto es su carpeta padre. Los modulos importan de aca y pueden
moverse libremente entre subcarpetas sin que se rompa ninguna ruta.

    from app.rutas import RAIZ, ENV, CONFIG_DICTADO
"""

from pathlib import Path

from dotenv import dotenv_values

# app/rutas.py -> app/ -> raiz del proyecto
RAIZ = Path(__file__).resolve().parent.parent

# --- Archivos de la raiz ---
ENV            = RAIZ / ".env"
# El vigia del proyecto: que se mira y por donde avisa cuando algo se muere solo.
# Lo lee `vigilar.py` de la skill `avisar` desde el Programador de tareas, sin
# ninguna sesion de Claude abierta. Su estado (`vigilar.json.estado.json`) queda
# al lado y esta ignorado por git: es de esta maquina, no del repo.
VIGILAR        = RAIZ / "vigilar.json"
CONFIG_DICTADO = RAIZ / "config_dictado.json"
CLAUDE_SESION  = RAIZ / "claude_sesion.json"
# Lo mismo pero para el OTRO cerebro (Codex, de OpenAI): su propia charla, su propio
# historial. Los ids de sesion no son intercambiables — una charla de Claude no se
# puede reanudar en Codex — asi que cada uno lleva su archivo. Ver `app/voz/cerebro.py`.
CODEX_SESION   = RAIZ / "codex_sesion.json"
# Cual de los dos cerebros esta puesto ahora ("claude" o "codex"). Vive en un archivo
# y no en una variable a proposito: quien lo cambia puede ser el panel, que es OTRO
# proceso, igual que pasa con el modelo elegido.
CEREBRO        = RAIZ / "cerebro.json"
MUSICA_ESPERA  = RAIZ / "musica_espera.wav"
WPP_CONFIG     = RAIZ / "wpp-config.yml"
# Señal de "no me escuches ahora" (llamada, juego). Si el archivo existe, voz.py
# ignora la palabra clave pero NO descarga los modelos: pausar y volver son
# instantáneos. F9 y los atajos siguen funcionando. Lo crea y borra el panel.
PAUSA_ESCUCHA  = RAIZ / "pausa_escucha.flag"
# Freno de mano de los agentes: si este archivo existe, ninguna sesion del panel
# arranca un turno NUEVO. Lo que ya esta corriendo sigue hasta terminar (se para con
# el boton Parar de siempre). Es "falla cerrada": ante la duda, no arranca. Se pone y
# se saca a mano —  `echo motivo > STOP`  y  `rm STOP`  — porque su gracia es poder
# frenar el enjambre sin abrir ninguna pantalla ni reiniciar nada. Lo que escribas
# adentro vuelve como motivo en el error, asi el que se choca con el freno entiende
# por que esta puesto. Idea tomada del control-room de Ruben Marcus (2026-08-25).
FRENO_AGENTES  = RAIZ / "STOP"
# Señal de "el micrófono está bloqueado A PROPÓSITO" (interruptor de privacidad
# del panel: mute de dispositivos + maestro de Windows apagado). Si existe, el
# watchdog de voz.py espera callado en vez de pelear por reabrir micrófonos que
# Windows no va a dejar abrir. La crea y borra el panel en /micacceso.
MIC_BLOQUEADO  = RAIZ / "mic_bloqueado.flag"
# Señal de "callate y soltá lo que estás haciendo AHORA" (botón ✋ del panel). Es
# de un solo uso: voz.py la ve, la borra e interrumpe. Va por archivo porque el
# panel es otro proceso y no puede llamarle a una función de la voz — mismo
# mecanismo que PAUSA_ESCUCHA, pero al revés: esta no queda puesta.
CORTAR_VOZ     = RAIZ / "cortar_voz.flag"
# Señal de "escuchame ahora" (botones 🎙 Laura / 🎙 Venus del panel): adentro dice
# el modo, "claude" o "local". Es apretar el botón en vez de decir el nombre —
# voz.py hace exactamente lo mismo que con la palabra clave ("Te escucho", micro
# abierto, "No te escuché" si no hablás). También de un solo uso, como CORTAR_VOZ.
ESCUCHAR_YA    = RAIZ / "escuchar_ya.flag"
# ¿Las respuestas del chat del panel se dicen además en voz alta? Adentro dice "1"
# o "0". Vive acá y no en el navegador a propósito: cuando estaba en el localStorage
# del panel, una pestaña con el JS viejo mandaba "no leer" sin que se notara y no
# había forma de saber si el interruptor estaba puesto. Si el archivo no existe,
# se lee en voz alta (es lo que Martín pidió el 2026-08-14).
LEER_PANEL     = RAIZ / "leer_panel.flag"
# "Estoy pensando ahora": lo pone y lo saca voz.py mientras resuelve un pedido,
# venga por donde venga (micrófono, buzón, Telegram). El panel lo mira para
# mostrar los puntitos aunque el mensaje no haya salido de su propia caja.
PENSANDO       = RAIZ / "pensando.flag"
# "Arrancá de cero": el botón del chat del panel, equivalente a decirle
# "arranquemos una sesión nueva". La sesión que dejás NO se pierde, queda archivada.
# De un solo uso, como las otras dos: voz.py la ve, la borra y arranca limpio.
NUEVA_SESION   = RAIZ / "nueva_sesion.flag"
# Token de Spotify (refresh token incluido): NO versionar, es una credencial.
SPOTIFY_TOKEN  = RAIZ / "spotify_token.json"

# Que pestañas tiene abiertas la pantalla del celular y en cual estaba. Vive en el
# SERVIDOR y no en el navegador a proposito: abierto desde el icono de la pantalla de
# inicio y desde el navegador son dos almacenamientos distintos, y las pestañas
# aparecian y desaparecian segun por donde entraras (2026-08-16).
PESTANAS_MOVIL = RAIZ / "pestanas_movil.json"
# Los nombres que Martin le pone a las sesiones desde el celular. Es un alias
# NUESTRO: el titulo de adentro de Claude no se toca (es de sus archivos).
NOMBRES_SESIONES = RAIZ / "nombres_sesiones.json"
# Carpetas que Martin sumo a mano a la lista de proyectos (las que todavia no
# tienen conversaciones no aparecen solas).
CARPETAS_SESIONES = RAIZ / "carpetas_sesiones.json"
# Como quiere ver Martin la lista de proyectos de la barra lateral: en que ORDEN van
# (las que arrastro a mano) y cuales ESCONDIO. Pedido del 2026-08-18: "quiero poder
# mover las carpetas y sacarlas de aca".
# ⚠⚠ Esconder NO borra nada: ni la carpeta del disco, ni sus conversaciones, ni la
# entrada de CARPETAS_SESIONES. Es la misma idea que SESIONES_ARCHIVADAS pero con
# proyectos, y se puede devolver. Vive en el SERVIDOR y no en el navegador a
# proposito: la misma lista esta en el cajon del celular y tiene que verse igual.
ORDEN_CARPETAS = RAIZ / "orden_carpetas.json"
# La IDENTIDAD VISUAL de cada carpeta de proyecto: su icono, su color y el apodo con el
# que Martin la ve. Mas los iconos que agrego a mano al juego (el ＋ del menu).
# ⭐ Vive en el SERVIDOR desde el 2026-08-25, y ese fue un pedido explicito suyo: "que no
# importa si abro desde el celular, la app de escritorio o desde otro navegador, siempre
# tengan estos iconos". Hasta entonces habia DOS juegos sueltos y los dos en el navegador
# —`sesIconos`/`sesTonos`/`sesApodos`/`sesIconosPropios` en `/sesiones` y
# `movilAspectoCarpetas` en `/movil`, con paletas distintas—, asi que otra maquina, otro
# navegador o el telefono arrancaban en cero. Es la misma correccion que ya se le hizo al
# ORDEN de las carpetas: lo que identifica al proyecto no es "como se ve esta pantalla",
# es del proyecto, y tiene que seguirlo a todos lados.
# ⚠ El apodo es solo el ROTULO: la llave sigue siendo el nombre real de la carpeta.
ASPECTO_CARPETAS = RAIZ / "aspecto_carpetas.json"
# Donde quedo la ventana de escritorio (posicion y tamaño), para abrirla igual la
# proxima vez. Ver `app/escritorio.py`.
VENTANA_ESCRITORIO = RAIZ / "ventana_escritorio.json"
# Conversaciones que Martin saco de la bandeja para no verlas mas. Es SOLO una lista
# de ids: no se borra ni se toca ningun archivo de Claude Code, se esconden de la
# lista y se pueden volver a mostrar. Vive en el servidor y no en el navegador a
# proposito: archivas en la compu y tambien desaparece en el celular.
SESIONES_ARCHIVADAS = RAIZ / "sesiones_archivadas.json"
# El aspecto elegido de las pantallas (tipografia, color, fondo y la foto de fondo si
# la hay). Vive en el SERVIDOR y no en cada navegador a proposito: se elige una vez y
# vale para la compu y para el telefono. Ver `app/estaticos/aspecto.js`.
ASPECTO = RAIZ / "aspecto.json"
# Lo que Martin pinta o subraya adentro de una conversacion (el marcador de texto de
# `/sesiones`). Vive en el SERVIDOR y no en el navegador a proposito: es la misma
# conversacion en la compu y en el celular, y con las marcas guardadas en una sola
# pantalla la otra la mostraba sin pintar. Cada marca dice en que mensaje va, desde y
# hasta que letra, de que color y de que forma. NO toca los archivos de Claude Code.
MARCAS_CHAT = RAIZ / "marcas_chat.json"
# Lo que Martin empezo a escribirle a una conversacion y todavia no mando: el BORRADOR.
# Una entrada por sesion (la llave es el id de la conversacion) con el texto y cuando se
# guardo. Vive en el SERVIDOR y no en el navegador a proposito, por lo mismo que las
# marcas: es la misma conversacion en la compu y en el celular, y un borrador guardado en
# una pantalla tiene que verse desde la otra. NO toca los archivos de Claude Code.
BORRADORES_SESIONES = RAIZ / "borradores_sesiones.json"
# Los avisos: el espejo de los Recordatorios del iPhone y la cola de lo que anotaste
# en el panel esperando irse al telefono. Apple no deja entrar a los Recordatorios
# desde afuera (los tres caminos estan cerrados desde iOS 13), asi que el puente lo
# hace un Atajo del propio telefono. Ver `app/nucleo/avisos.py`.
AVISOS = RAIZ / "avisos.json"
# Con que modelo de Claude corre cada cosa: una entrada por sesion (la llave es el id
# de la conversacion) mas la de Laura, bajo la llave "laura". Vive en el SERVIDOR y no
# en el navegador a proposito: el modelo lo usa quien LANZA el proceso `claude`, no la
# pantalla, y ademas se elige en la compu y tiene que valer igual desde el celular.
# Ver `app/voz/sesiones_movil.py` (MODELOS) y `app/voz/claude_voz.py` (modelo_actual).
AJUSTES_SESIONES = RAIZ / "ajustes_sesiones.json"
# En que proyectos una sesion de Codex abierta desde el celular corre SIN jaula de
# disco. Con `workspace-write` Codex no puede escribir `.git/`, asi que no podia ni
# hacer un commit: git muere con "Unable to create '.git/index.lock': Permission
# denied" (2026-08-20). Es el mismo arreglo que ya tiene la Laura de voz en
# `codex_voz.py`, pero por proyecto. Lista opcional: si el archivo no existe vale la
# regla de fabrica (repo git adentro de las raices de trabajo). Ver
# `app/voz/sesiones_movil.py` (proyecto_confiable).
PROYECTOS_CONFIABLES = RAIZ / "proyectos_confiables.json"
# Certificado de la inspeccion HTTPS de Avast para procesos Node/Codex. Python ya
# usa truststore; Node necesita este PEM explícito para no cortar los streams.
CERT_NODE_CODEX = Path.home() / ".codex" / "certs" / "avast-web-shield.pem"
# ⭐ El binario `codex` NO es Node: por dentro es Rust y no mira NODE_EXTRA_CA_CERTS,
# asi que con solo el PEM de arriba se seguia cayendo con "invalid peer certificate:
# UnknownIssuer" (2026-08-22). Este paquete junta las raices de siempre (certifi) mas
# las del almacen de Windows mas la de Avast, y va por SSL_CERT_FILE, que si lo lee.
# Se regenera con `python -m pruebas.armar_bundle_certificados` si Avast rota su raiz.
#
# ⭐ POR QUE hace falta pasarlo SIEMPRE, medido el 2026-08-24: `codex` solo, sin
# ninguna variable puesta, ANDA — lee el almacen de Windows, donde Avast ya dejo su
# raiz. El que rompe es SSL_CERT_FILE mal apuntado: cuando esta seteada, esa lista
# REEMPLAZA a la del sistema. Y el activador de conda la setea si la encuentra vacia
# (`etc/conda/activate.d/openssl_activate.bat` -> `Library\ssl\cacert.pem`, 119 raices,
# CERO de Avast). Como el panel corre en el env `wpp`, todo lo que lanzaba heredaba esa
# lista sin Avast y el stream moria en `wss://chatgpt.com/backend-api/codex/responses`.
# O sea: el peligro no es que falte la variable, es que la ponga otro. Por eso cada
# lanzador la pisa con este paquete en vez de confiar en lo que venga heredado.
CERT_BUNDLE_CODEX = Path.home() / ".codex" / "certs" / "bundle-windows.pem"
# "Compacta tu charla": el boton del chat del panel. Laura le pide un resumen a la
# sesion de ahora, la archiva y arranca una nueva sembrada con ese resumen, asi sigue
# sabiendo de que venian hablando pero deja de arrastrar el contexto entero en cada
# turno. De un solo uso, como NUEVA_SESION: voz.py la ve, la borra y compacta.
COMPACTAR_LAURA = RAIZ / "compactar.flag"

# --- El navegador de cada proyecto (2026-08-28) ---
# ⭐ Las sesiones del panel pueden manejar un Chrome de verdad (`--chrome` de Claude Code,
# herramientas `mcp__claude-in-chrome__*`). Cada carpeta de proyecto declara CUAL perfil
# usa, y eso se guarda en ASPECTO_CARPETAS junto al icono y el color, porque es una
# propiedad del proyecto igual que ellos. Aca van solo las rutas que hacen falta para
# ABRIR ese Chrome cuando no esta prendido.
# ⚠ La ruta del chrome.exe estaba escrita a mano en DOS lados (`app/web/navegador.py` y
# `lanzadores/Chrome IA.bat`). Esta es la unica fuente de verdad; los otros dos quedan
# como estan porque son de la voz y no se tocan en esta tarea.
CHROME_EXE     = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CHROME_EXE_X86 = Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
# El perfil de todos los dias (el que tiene Gmail, el banco y Kommo logueados). Se ofrece
# en la lista, pero elegirlo es una decision consciente de Martin: una sesion con ese
# perfil tiene las manos sobre TODAS sus cuentas abiertas.
PERFIL_CHROME_PERSONAL = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
# Donde viven los perfiles DEDICADOS (uno por cliente). Es `D:\IA`, al lado del proyecto,
# que es donde ya vive `chrome-ia` (el de la voz). El panel busca ahi las carpetas que
# parezcan un perfil de Chrome para armar el selector: no inventa rutas ni las adivina.
PERFILES_CHROME = RAIZ.parent

# --- Carpetas ---
LOGS        = RAIZ / "logs"
RESULTADOS  = RAIZ / "resultados"
# Stickers que Martin manda a guardar ("guardá ese como tal") para reenviarlos despues
# nombrandolos nomas. `catalogo.json` mapea el nombre que el usa -> el archivo .webp.
# Adentro de resultados/ a proposito: son archivos de terceros y ya esta fuera de git.
STICKERS    = RESULTADOS / "stickers"
# Fotos que Martin le manda a Laura POR WHATSAPP. Quedan en disco para que ella las
# abra con Read, igual que las de Telegram: una descripcion de Gemini no reemplaza
# mirar la captura. Adentro de resultados/ porque puede haber datos de clientes.
WPP_FOTOS   = RESULTADOS / "wpp_fotos"
# Las corridas del testing adversarial: una ficha por corrida con la spec, el expediente
# del revisor que miro la pantalla, los hallazgos con su evidencia y el veredicto. Adentro
# de resultados/ a proposito, y eso NO es un detalle de orden: el expediente cuenta lo que
# se vio en sistemas reales de clientes, asi que tiene que quedar fuera de git como las
# fotos de WhatsApp y los stickers. Ver `app/voz/adversarial.py`.
ADVERSARIAL = RESULTADOS / "adversarial"
# Las imagenes pegadas en el pizarron visual. El endpoint `/pizarra/imagen` de panel.py
# guarda aca lo que pegas con Ctrl+V, y el contraste adversarial cuelga aca las capturas
# que saco el revisor que miro la pantalla.
PIZARRA_IMAGENES = RESULTADOS / "pizarra_imagenes"
# Archivos estaticos que el panel sirve tal cual (hoy: rough.js, la libreria
# que dibuja "a mano alzada" en la pizarra — local para no depender de un CDN).
ESTATICOS   = RAIZ / "app" / "estaticos"
# Lo que WebView2 guarda de la ventana de escritorio (localStorage, cache, cookies).
# Va a una carpeta NUESTRA y no a la temporal de Windows a proposito: asi la barra
# plegada de la pizarra y demas interruptores del navegador sobreviven a cerrar la
# ventana, igual que en Chrome. Se puede borrar entera sin romper nada.
WEBVIEW_DATOS = RAIZ / "webview_datos"
# El "estudio" de audio: los archivos que Martin sube para pegarlos uno atras del
# otro, y el mp3 que sale de cada union. Adentro de resultados/ a proposito — casi
# siempre son audios que llegaron por WhatsApp, o sea de terceros, y esa carpeta ya
# esta fuera de git. Los originales NO se tocan nunca: el recorte son numeros que se
# le pasan a ffmpeg al unir (misma idea que el recorte de imagenes de la pizarra).
ESTUDIO     = RESULTADOS / "estudio"
# Los audios que ENTRAN por WhatsApp y Telegram, guardados con una ficha al lado
# (canal, quien lo mando, cuando y que dice) para poder elegirlos en el Estudio
# leyendo su transcripcion. Antes del 2026-08-17 el audio original se tiraba: los
# caminos de ingesta lo bajaban a un temporal y lo borraban tras transcribirlo.
# Ver `app/nucleo/entrantes.py`; se limpian solos a los 30 dias.
ESTUDIO_ENTRANTES = ESTUDIO / "entrantes"
# La cola visible del Estudio. Son fichas chicas, una por archivo en preparación,
# para que el panel y los procesos de WhatsApp se vean entre sí sin compartir memoria.
ESTUDIO_COLA = ESTUDIO / "cola"
# Análisis que Martín pidió para un armado concreto (pistas + cortes + perfil). No se
# mezcla con el análisis automático que trae cada audio al entrar.
ESTUDIO_ANALISIS_ARMADOS = ESTUDIO / "analisis_armados.json"
# Tiras de fotogramas para elegir un corte mirando el video. Son cache: se pueden
# regenerar desde el original, por eso no se mezclan con los videos ni con sus fichas.
ESTUDIO_MINIATURAS = ESTUDIO / "miniaturas"
# Las "bandejas" del Estudio: los proyectos con los que Martin agrupa sus audios. Es
# solo la lista de nombres y su orden — a que proyecto pertenece cada audio vive en la
# ficha del audio, no aca. Existe como archivo propio para poder tener un proyecto
# recien creado que todavia no tiene ningun audio adentro.
ESTUDIO_PROYECTOS = ESTUDIO / "proyectos.json"

# --- Transcripciones de Claude Code ---
# Claude Code guarda cada sesion en un .jsonl dentro de una carpeta con el nombre
# del proyecto "aplanado": los ":" y las "\" se vuelven "-". De ahi sacamos la
# charla de una sesion vieja para que Laura pueda resumirla sin reabrirla.
CLAUDE_PROYECTOS = Path.home() / ".claude" / "projects"
CLAUDE_SESIONES  = CLAUDE_PROYECTOS / str(RAIZ).replace(":", "-").replace("\\", "-").replace("/", "-")
# Codex guarda cada sesion en ~/.codex/sessions/AAAA/MM/DD/rollout-<fecha>-<id>.jsonl.
# La carpeta cambia con el dia, asi que al archivo se lo busca por el id, no por ruta.
CODEX_SESIONES   = Path.home() / ".codex" / "sessions"
# Avisos para que Laura los DIGA en voz alta, dejados por cualquier proyecto de la
# maquina (`avisar.py --hablar`). Una linea JSON por aviso; voz.py las va comiendo y
# las dice cuando hay un hueco. Vive en ~/.claude y no en el proyecto a proposito:
# quien escribe es la skill global `avisar`, que no conoce este repo.
AVISOS_HABLADOS  = Path.home() / ".claude" / "avisos_hablados.jsonl"
# Registro de sesiones VIVAS de Claude Code (un .json por proceso, con pid, nombre
# amigable, cwd y sessionId). Lo escribe el propio Claude Code; de aca sale la lista
# de sesiones que el panel ofrece para la lectura automatica.
CLAUDE_REGISTRO  = Path.home() / ".claude" / "sessions"
# Que sesion esta siguiendo la lectura automatica (lo escribe el panel, lo lee voz.py
# cada segundo — mismo patron que pausa_escucha.flag). Si no existe, no se lee nada.
SEGUIR_LECTURA   = RAIZ / "seguir_lectura.json"
# A que sesion va el dictado "Venus, escribi en la sesion..." — UNA perilla con dos
# manos: la gira el selector del panel o la voz, y los dos ven el mismo estado.
ESCRIBIR_EN      = RAIZ / "escribir_en.json"
# Pizarron interactivo (notas y pines) que Laura llena por voz. Un JSON plano
# alcanza: es un tablero de un solo usuario, sin necesidad de base de datos.
PIZARRA_ESTADO   = RAIZ / "pizarra_estado.json"
# Buzon de Laura por Telegram: el bot deja la pregunta y voz.py — que es quien tiene
# el proceso de Laura vivo — deja la respuesta. Mismo patron perilla, dos archivos.
LAURA_PREGUNTA   = RAIZ / "laura_pregunta.json"
LAURA_RESPUESTA  = RAIZ / "laura_respuesta.json"

# Las fotos del "Contenido destacado de Windows" (Windows Spotlight): las que Windows
# va cambiando sola en la pantalla de bloqueo. Estan aca, sin extension y mezcladas con
# iconos chicos y con las verticales del celular — para usar una hay que elegir la mas
# nueva que sea apaisada y pese de verdad (ver /fondo/windows en panel.py).
WINDOWS_FONDOS = (Path.home() / "AppData" / "Local" / "Packages" /
                  "Microsoft.Windows.ContentDeliveryManager_cw5n1h2txyewy" /
                  "LocalState" / "Assets")

# --- Recursos que viven fuera del proyecto (modelos pesados en D:) ---
# Ollama: el cerebro chico local (`app/voz/cerebro.py` le habla al 11434). Es un .exe
# aparte, instalado por su propio instalador. Se lo busca primero en el PATH; esto es
# el plan B, que es donde lo dejo el instalador en esta maquina.
OLLAMA_EXE    = (Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe")
# El generador 3D (Hunyuan3D 2mini): OTRO proyecto, con su propio entorno de Python y sus
# propias carpetas de pesos. El panel solo lo prende y lo apaga (tarjeta de la placa).
# ⚠ Las tres variables de entorno NO son decoracion: sin `HF_HOME`/`HY3DGEN_MODELS` el
# modelo se baja de nuevo a `~\.cache` y llena el disco chico (por eso las
# puso la sesion que lo instalo el 2026-08-22).
DIR_3D          = Path(r"D:\IA\modelos-3d")
HUNYUAN_DIR     = DIR_3D / "Hunyuan3D-2"
HUNYUAN_PY      = HUNYUAN_DIR / "conda-env" / "python.exe"
HUNYUAN_CACHE   = DIR_3D / "hunyuan-cache"
HUNYUAN_PESOS   = DIR_3D / "hunyuan-models"
HUNYUAN_GRADIO  = DIR_3D / "hunyuan-gradio-cache"
REMBG_CACHE     = DIR_3D / "rembg-cache"
# Los modelos de Whisper y la voz de Piper. En otra maquina se elige la carpeta con
# `WPP_MODELOS` en el .env, sin tocar codigo; sin eso queda la de siempre. Se lee con
# `dotenv_values` y no de `os.environ` porque este modulo se importa ANTES de que los
# demas carguen el .env.
DIR_MODELOS   = Path(dotenv_values(ENV).get("WPP_MODELOS") or r"D:\IA\modelos")
DIR_PORCUPINE = DIR_MODELOS / "porcupine"
VOZ_PIPER     = DIR_MODELOS / "piper" / "es_AR-daniela-high.onnx"
