# Reglas de trabajo en este proyecto

Leé `README.md` primero: ahí está la arquitectura completa, los servicios y los gotchas.

⭐ **Una sesión del panel puede manejar un navegador de verdad** (desde el 2026-08-28): hay un
navegador por defecto que heredan todas las carpetas, y cada una puede pisarlo con otro perfil
de Chrome o apagarlo con `ninguno`. Si esta carpeta tiene uno, las herramientas
`mcp__claude-in-chrome__*` aparecen solas en la sesión — y **la ventana recién se abre
cuando las usás**, así que una charla que no navega no le tapa la pantalla a nadie. Sirve para probar una web como una
persona: abrir, clickear, escribir, mirar qué pasó y leer la consola. Cómo está armado y qué
NO hay que romper está en `INTERFAZ.md` ("El navegador de cada carpeta") y en la lista de
abajo. Si no tenés esas herramientas, esta carpeta no tiene navegador declarado: pedíselo al
usuario, no intentes rodearlo.

⭐ **El testing adversarial** (desde el 2026-08-29, tarjeta 🥊 en la página principal del
panel y `app/voz/adversarial.py`): un ciclo donde el que escribe el código nunca es el que
lo juzga. Claude implementa; después, tres revisores de contexto limpio tratan de refutar
que funcione — uno de Claude que abre el sistema en el navegador y dos de Codex que leen su
expediente. Nació de un episodio concreto: un agente entregó trabajo diciendo que andaba y
no andaba. Cuatro reglas que **no se tocan sin hablarlo con Martín**, cada una con su
invariante en `pruebas/probar_adversarial.py` (50 chequeos, con `--mutar`):
- ⭐ **El navegador es de Claude.** No se le construye soporte de Chrome a Codex: Codex lee
  y juzga sobre lo que Claude dejó escrito.
- ⭐⭐ **El expediente lo escribe el revisor que MIRÓ, nunca el implementador.** Si lo armara
  el que escribió el código, los que leen estarían juzgando el sumario del acusado.
- ⭐ **Un hallazgo sin evidencia no cuenta**, lo firme quien lo firme. Y lo descartado se
  cuenta a la vista: descartar en silencio se lee como "no encontró nada".
- ⭐ **El teléfono suena una sola vez y solo en el empate real** (dos vueltas sin converger).
  Nunca un aviso por hallazgo suelto.
- ⭐ **Cada corrida cuelga en el pizarrón visual un bloque**: rectángulo carbón de fondo, la
  CAPTURA de lo que se vio encima, y el análisis en tiza abajo (Martín las quiere todas,
  verde incluido), una sola vez al terminar y nunca una por vuelta ni por hallazgo. El fondo
  se cuelga **primero** porque el tablero dibuja en el orden de la lista: colgado último
  taparía la foto. La foto respeta su proporción real —estirarla miente sobre lo que se vio—,
  el bloque se ubica en el primer hueco donde **no toca nada**, y las tres piezas llevan la
  marca `adversarial:<id>` para que el botón 🧹 barra **solo las propias**: en ese tablero hay
  cosas de él y de Laura.
  ⚠ Al medir dónde hay lugar, una **nota se posiciona por su CENTRO** (`translate(-50%,-50%)`)
  y una figura por su caja. Tomar la `x` de una nota como borde derecho se queda corto la
  mitad del ancho — ese fue un bug real, y el chequeo que lo cuida **mide con su propia
  cuenta**, no llamando a la del módulo: con la misma regla torcida, los dos coinciden y la
  prueba pasa por el motivo equivocado.
⚠ Corre contra los sistemas reales que le pases: decidí vos contra qué lo apuntás.

⭐ **Si vas a tocar una pantalla** (el panel, la pizarra, la app del celular, la página de
sesiones), leé `INTERFAZ.md`: ahí está dónde vive cada pantalla, las decisiones de diseño que
ya se tomaron y por qué, cómo se prueba con capturas y qué está roto hoy.

## El grafo del proyecto (graphify)

- Si existe `graphify-out/graph.json`, tiene el grafo del código y los docs (si no, se arma
  con `/graphify`: paso 12 del README). Para preguntas de
  arquitectura ("¿qué llama a X?", "¿cómo se conecta Y con Z?") usá `/graphify query "..."`
  **antes** de ponerte a leer archivos enteros: gasta muchos menos tokens y ya conoce las
  decisiones documentadas (los nodos `rationale`).
- Se actualiza **solo** con cada commit si instalaste el hook (`graphify hook install`; solo
  re-extrae el código tocado, sin LLM). Si cambiaron los `.md` grandes, cada tanto corré
  `/graphify --update` a mano para que el grafo también los refresque.

## Entorno

- Python: el del entorno conda `wpp` (ver la instalación en `README.md`). NUNCA el Python del sistema.
- Si la red intercepta HTTPS (antivirus, proxy de oficina), pip necesita `--trusted-host pypi.org --trusted-host files.pythonhosted.org`.
- Verificar sintaxis antes de reiniciar un servicio: `python -c "import py_compile; py_compile.compile('archivo.py', doraise=True)"`.

## Dónde va cada archivo

- Todo el código vive en `app/`: `nucleo/` (Whisper y análisis), `voz/` (asistente),
  `web/` (navegador), `ingesta/` (Telegram y WhatsApp). La raíz solo tiene `panel.py`,
  `launcher.vbs`, los archivos de config y `musica_espera.wav`. **No ensuciar la raíz.**
- ⭐ **Las rutas van en `app/rutas.py`, en ningún otro lado.** `from app.rutas import RAIZ, ENV, …`
  Nunca escribir `Path(__file__).with_name(...)` ni una ruta absoluta al proyecto dentro de un
  módulo: eso fue exactamente lo que hubo que arreglar en 11 lugares al armar `app/`.
  Si falta una ruta, se agrega a `rutas.py`.
- Los módulos se lanzan **con `-m` desde la raíz**, nunca por ruta al `.py`:
  `python -m app.voz.voz`, `python -m app.ingesta.bot_telegram`,
  `python -m uvicorn app.ingesta.webhook_wasender:app …`. Si se lanza por ruta, Python no
  encuentra el paquete `app` y falla el import.
- En `panel.py`, el dict `SERVICIOS` tiene `"cmd"` (con `-m`) y `"match"` (el texto que
  identifica al proceso en su línea de comando). **Si cambia el módulo, hay que cambiar los dos**,
  o el panel va a creer que el servicio está apagado cuando en realidad corre.
- ⚠ `launcher.vbs` **no se mueve**: el acceso directo "Servidor IA" del escritorio apunta a su ruta.
- Otras carpetas: `lanzadores/` (los `.bat`), `pruebas/`, `logs/`, `resultados/` (salida de
  corridas), `skills/` (atajos para Claude), `herramientas/`, `graphify-out/` (grafo generado).
- `.env`, `resultados/`, `logs/`, `claude_sesion.json`, `wpp-config.yml` y `vigilar.json` están
  ignorados (claves, configuración de cada máquina y datos reales de terceros). No versionar
  nada de eso: los que se configuran traen su `.ejemplo` al lado.
- `.graphifyignore` deja fuera del grafo los `.wav`/`.mp4` (graficarlos los transcribe con
  Whisper y le pelea la VRAM al asistente).

## Reiniciar servicios (siempre por el panel, puerto 8750)

- Voz: `POST http://localhost:8750/stop/voz` → esperar 3 s → `POST /start/voz`. Tarda ~20 s en cargar (Whisper turbo en GPU).
- ⚠ Tras mover módulos o tocar el dict `SERVICIOS`, hay que reiniciar **el panel también**: tiene los comandos y los `match` cargados en memoria y sigue usando los viejos.
- Servidor (Telegram+webhook+túnel): `POST /stop` → `POST /start`.
- Panel mismo: matar proceso python con `panel.py` en el command line y relanzar `panel.py` (sin `--auto` si no querés que prenda todo).
- Para una llamada o para jugar **no hace falta apagar la voz**: usar **"Pausar escucha"** del panel (`POST /pausa`), que solo desactiva la palabra clave y es instantáneo en los dos sentidos. Si cambia algo del HTML o de los endpoints de `panel.py`, hay que reiniciar el panel: los tiene en memoria.
- Logs en `logs/` (`voz.log` es la fuente del chat en vivo del panel — no cambiar los prefijos `comando:`, `respuesta:`, `claude respuesta:`, `dictado:`, `aviso sistema:`, `lectura respuesta [...]:`, `lectura:`, `telegram pregunta:`, `telegram respuesta:` sin actualizar `/chat` en panel.py). ⭐ Si agregás una respuesta hablada por un camino nuevo, **imprimí `claude respuesta:` o `aviso sistema:`**: si no, se escucha y no queda en ningún lado (pasó con el primer resumen de sesión).

## Trabajo en paralelo (multiagente)

- Si hay más de un agente: al arrancar, leé `PIZARRA.md` (se crea con la skill `paralelo`)
  y anotá qué tarea tomás y qué zona tocás. Al terminar, **borrá tu entrada**.
- **Dueño de la máquina**: una sola sesión a la vez toca `app/voz/`, `app/ingesta/` o
  `panel.py`, reinicia servicios, o usa GPU, micrófono, puertos 8750/8080 y el token de
  Telegram. Si no sos el dueño, no reiniciás nada — ni "solo un segundo".
- Lo que no necesita la máquina (`pruebas/`, `app/web/`, docs, refactors, análisis) va en
  worktree: `claude -w nombre-tarea`, con spec de 5 líneas escrita antes, merge y borrado
  el mismo día. Un `.worktreeinclude` con `.env` y `spotify_token.json` hace que se copien al worktree.
- Techo: 2 agentes en este proyecto (3 excepcional). El techo es de la máquina, no del repo.

## No romper (costaron sangre)

⭐ **Estas reglas ahora se pueden correr**: `python -m pruebas.probar_no_romper` las
verifica contra el código en menos de dos segundos (no toca GPU, micrófono ni servicios, y
no gasta tokens). Con `--mutar` rompe cada regla a propósito y exige que el chequeo la cace:
un chequeo que no puede fallar es un adorno. Si tocás algo de esta lista, corrélo antes de
commitear — y si querés que lo corra solo, `cp pruebas/gancho_pre_commit.sh .git/hooks/pre-commit`.
Si agregás una regla acá, agregale su invariante allá.

- El system prompt de Laura se aplana a UNA línea en `app/voz/claude_voz.py` (los `\n` rompen el .CMD de Windows y matan `--resume` en silencio).
- ⭐ **El "día de Laura" corta a las 13:00, no a la medianoche** (`CORTE_HORA` en `claude_voz.py`). Acá se trabaja de noche: con el corte a las 12 la sesión se partía al medio de la charla. Y la respuesta al saludo del día se intercepta **al principio de `_manejar_texto`, antes de `acciones.ejecutar`**: si no, "seguí con la anterior" cae en `media_playpause` (tiene `segu[ií]`) y aprieta play en vez de contestarte. El orden de los patrones en `responder_dia()` está elegido a mano y hay 24 casos en `pruebas/test_dia_laura.py` — **correr eso antes de reiniciar si se toca alguno**.
- `dontAsk`, no `bypassPermissions`. Sin tool `Task`. Interrumpir con `control_request interrupt` por stdin, jamás matar el proceso `claude`.
- ⭐⭐ **El proceso de una sesión del panel VIVE ENTRE TURNOS** (`VIVAS` en `app/voz/sesiones_movil.py`, desde el 2026-08-20). No volver a "un `claude -p` por mensaje": al cerrarle el stdin y matarle el árbol al terminar el turno, se moría **todo lo que la sesión había mandado a segundo plano** (`run_in_background`) y el turno siguiente solo veía "No completion record was found…". Parchear el kill no sirve: el registro del background vive adentro del proceso de Claude Code, así que tiene que ser el MISMO proceso. Por eso `parar()` manda el `interrupt` por stdin en vez de matar, y matar quedó como salida de emergencia. `EN_CURSO` sigue existiendo solo mientras corre el turno (de ahí cuelgan el semáforo `ocupada` y el botón Parar en `panel.py`): no meterle el proceso persistente. Se prueba sin gastar tokens con `pruebas/probar_sesion_persistente.py`.
- ⭐⭐ **No hay tope de sesiones prendidas: se duermen por FALTA DE MEMORIA** (`_barrer_vivas`
  en `app/voz/sesiones_movil.py`, desde el 2026-09-03). Antes eran `MAX_VIVAS = 4` y una hora
  de inactividad; el pedido de Martín fue *"quiero poder tener todas las sesiones vivas que se
  me ocurra y que no se rompa nada"*. Un número fijo no sabe nada de la máquina: con RAM de
  sobra apagaba la quinta al pedo, y ya había volteado una sesión en uso a mitad del ciclo
  adversarial. Ahora, mientras quede más de `COLCHON_RAM_MB` libre no se apaga **ninguna**;
  por debajo se duermen las más viejas sin usar, de a una, remidiendo entre cada una.
  **Dormir no pierde nada**: la charla vive en el disco y el proceso vuelve con `--resume`
  (los mismos ~8 s que ya cuesta cambiarle el modelo). Es además el workaround oficial de la
  fuga de memoria del CLI.
  - ⭐⭐ **El guardián no se toca**: nunca se duerme una sesión con turno en curso **ni con
    trabajo en segundo plano**. `turno.locked()` solo cubre el turno, y el background **dura
    más que el turno** — sin el guardián, dormir por presión mata justo lo que protege la
    regla de acá arriba, y el síntoma es trabajo que desaparece en silencio: peor que la
    lentitud. La señal es que el CLI tenga procesos hijos (medido: trabajando tiene
    `bash`/`python`/`node`, quieta tiene cero). Ante cualquier duda contesta que SÍ trabaja.
  - ⚠⚠ **`viva.proc` NO es el CLI**: en Windows `claude` es un `.cmd`, así que lo que lanza el
    panel es un `cmd.exe` y el `claude.exe` es su **hijo**. Contar los hijos del `.cmd` da
    siempre por lo menos uno —el propio CLI— y el guardián contestaría "trabaja" para todas:
    se vería andar y no dormiría ninguna jamás. Por eso existe `_cli_de()`.
  - ⚠ Al despertar una charla que el panel **no** tiene anotada (`VIVAS` arranca vacío tras
    reiniciar), primero se barren los procesos sueltos con ese sid: dos procesos sobre el
    mismo id corrompen la conversación.
  - El botón **💤 Soltar máquina** del panel (`POST /sesiones/liberar`) hace esto a pedido y
    pasa por el mismo guardián; lo único que se saltea es el piso de quietud. El ⟳ de al lado
    **no** sirve para esto: reinicia panel y servicios y no toca ni un proceso de sesión.
  - Su regla en el chequeo de acá arriba se llama `no-dormir-con-trabajo-abajo`; corrélo
    con `--mutar`, que es la que prueba que el guardián no sea un adorno.
- ⭐⭐ **`_cambiar_stream()` abre el nuevo micrófono ANTES de cerrar el viejo.** No invertir ese orden nunca. Antes cerraba primero y el 2026-08-11, tras suspender la máquina y reenchufar el dongle, el nuevo no abrió (`AUDCLNT_E_DEVICE_INVALIDATED`) y quedó **sin ningún micrófono**: proceso vivo, panel en verde, sordo y sin avisar a nadie. Si el nuevo falla se queda con el que andaba, y como último recurso `_asegurar_algun_stream()` abre cualquiera que funcione. **La regla es que nunca puede quedar sin micrófono.**
- El watchdog detecta que la máquina **volvió de suspenderse** por el salto del reloj (>60 s entre vueltas del bucle de 5 s) y rearma el micrófono solo, refrescando la lista de PortAudio con `sd._terminate()+sd._initialize()` — al suspender, Windows desarma las conexiones de audio y al despertar arma otras con el mismo nombre.
- ⭐ El micrófono se abre por **WASAPI con `auto_convert=True`**, no por DirectSound (`_candidatos_micro()` en `app/voz/voz.py`). DirectSound se queda entregando ceros sin error cuando el dispositivo se va y vuelve, y eso era la causa real del "se muere el micrófono a cada rato". WASAPI en modo compartido exige la frecuencia nativa, así que **sin `auto_convert` no abre a 16 kHz** (`PaErrorCode -9997`). WDM-KS no sirve: `sounddevice` no soporta su API bloqueante. El predeterminado de Windows va **último** en la cadena, porque puede ser otro micrófono.
- Ante una grabación vacía, el watchdog **primero reabre el mismo micrófono** y solo cambia de micrófono si el problema vuelve dentro de `REINTENTO_SEG`. Antes te sacaba de tus auriculares por un stream que se arreglaba reabriéndolo.
- Watchdog del micro en `app/voz/voz.py`: distingue **FLUJO** (llegó un callback = el dispositivo existe) de **CONTENIDO** (hay audio real). Solo cambia de micrófono por flujo cortado (`FLUJO_MUERTO_SEG`) o por verdad de campo (`_captura_vacia`: apretaste una tecla y llegó silencio digital). **No agregar de vuelta la regla de "120 s pasivos"**: la cancelación de ruido por IA del ROG no se puede desactivar y da el mismo casi-cero estando callado que sin ponerse, así que el rms no distingue esos estados. Esa regla causaba cambios de micro en plena sesión. Hay `REFRACTARIO_SEG` (60 s) para que no rebote. Los umbrales (0.0005 silencio digital, 0.002 pico vivo) están calibrados con mediciones reales — no "simplificarlos".
- Wake word corre en CPU (`tiny` int8) a propósito: en GPU con VRAM llena tardaba hasta 6 s. No moverlo a CUDA.
- El TTS sintetiza **por trozos que crecen 10 % cada uno** (`TTS_CRECIMIENTO` en `app/voz/voz.py`). Ese 10 % **no es a gusto**: Piper hace ~30 ms por letra y hablar cuesta ~33,7 ms por letra, así que un trozo puede crecer como máximo 12 % respecto del anterior o no llega a estar listo y **queda un hueco de silencio en medio de la frase**. Antes sintetizaba la respuesta completa: 10,3 s de silencio en una respuesta de 344 letras. No agrandar la rampa "para que suene mejor" sin volver a medir con `python -m pruebas.analizar_tiempos`.
- `vad_filter=True` y descarte por `no_speech_prob>0.45` en el wake: sin eso Whisper alucina "Laura/Venus" con ruido y se autodispara.
- ⭐ **El vigía de WhatsApp avisa por TELEGRAM, no por WhatsApp** (`"canal": "telegram"` en
  `vigilar.json`, y en su molde `vigilar.ejemplo.json`, que es lo que chequea la prueba). Los avisos de WhatsApp de la skill `avisar` salen por la **misma** instancia
  de Evolution que el vigía vigila (`Laura`, en `~/.claude/whatsapp.json`): puesto en whatsapp,
  el aviso de que se cayó WhatsApp viaja por el cable cortado y no llega nunca — un vigía que se
  ve bien y está mudo justo cuando hace falta. Nace del 2026-08-29: la instancia estaba en
  `close` desde el 27 a las 09:02, Martín mandó seis audios al Estudio y **nadie avisó**; la
  laptop entera estaba sana, así que mirar de este lado no lo habría encontrado jamás. El
  chequeo es `app/ingesta/chequeo_instancia.py` y se prueba con
  `python -m pruebas.probar_vigia_whatsapp --mutar`.
- ⭐⭐ **La sesión con navegador NUNCA puede ejecutar JavaScript en la página**
  (`--disallowedTools CHROME_JS` en `_arrancar_viva`, `app/voz/sesiones_movil.py`). Es el
  único candado duro que corre siempre: un clic viaja como `left_click` + coordenadas y el
  panel **no puede ver qué botón es**, así que lo irreversible se frena con una instrucción
  (igual que Codex, que no bloquea nada). `javascript_tool` se saltea la interfaz entera y
  puede mandar un formulario sin apretar ningún botón — o sea, justo lo que la instrucción
  le pide que no haga. Y `REGLAS_NAVEGADOR` va en **una sola línea**, por lo mismo que el
  system prompt de Laura. Se prueba con `pruebas/probar_navegador_carpeta.py` (64 chequeos,
  con `--mutar`) y `pruebas/ver_navegador_carpeta.py` (17, las dos pantallas).
- ⭐⭐ **La ventana de Chrome se abre cuando la sesión USA el navegador, nunca al abrir la
  charla** (`_asegurar_chrome` en `app/voz/sesiones_movil.py`, desde el 2026-08-29). Como el
  navegador de base lo hereda toda carpeta, abrirlo en `_arrancar_viva` era un Chrome nuevo
  en cada charla de cada proyecto, la usara o no. Para tener dónde engancharlo hubo que
  sacar el atajo de permitir el servidor entero (`mcp__claude-in-chrome` en `--allowedTools`):
  **toda** herramienta del navegador pasa hoy por el portero de `_turno`, que sin lista de
  sitios la concede sola. No devolver ese atajo "para ahorrar el permiso": es el único
  momento donde se sabe que la sesión va a navegar. La ventana se abre **antes** de conceder
  y **solo si** el dominio pasa.
  ⚠⚠ **Son DOS piezas y las dos hacen falta**: sacarlo del allowlist no alcanza porque el
  CLI concede por su cuenta las herramientas que considera de lectura (medido:
  `list_connected_browsers` se ejecutó sin pedir nada). La otra es `AJUSTES_CHROME`
  (`permissions.ask`) por `--settings`. Con una sola, una sesión que arranca mirando qué
  navegadores hay se encuentra con los ajenos y el suyo cerrado. Se mide contra el CLI real
  con `pruebas/sonda_portero_chrome.py` (gasta tokens; `--sin-ask` tiene que fallar).

## Estilo

- Comentarios y mensajes al usuario en español (Argentina, voseo). El usuario no es programador profesional: explicar sin jerga.
- El asistente le habla por TTS: los textos que dice deben ser cortos y naturales, sin markdown ni emojis.
