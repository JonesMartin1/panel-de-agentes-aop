# Panel de agentes AOP

**AOP = Agent Orchestrator Panel**: un panel para orquestar agentes de IA (Claude Code y
Codex) desde tu propia PC, con transcriptor de WhatsApp y Telegram y asistente de voz.

Dos cosas en una, corriendo en tu PC:

1. **Transcriptor**: le mandás audios o videos (por Telegram, WhatsApp o arrastrándolos) y te
   devuelve el texto y un resumen. La transcripción se hace **en tu placa de video**: el audio
   no se sube a ningún servicio.
2. **Asistente de voz**: decís "Venus" y le pedís cosas a la PC (abrir programas, poner música,
   dictar donde esté el cursor), o decís "Laura" y charlás con Claude o ChatGPT por voz.

Todo se maneja desde un panel web en `http://localhost:8750`.

---

## Instalación paso a paso

Son unos 30-40 minutos, casi todo esperando descargas. Andá en orden: cada paso termina con
**"Anduvo si…"**, y si eso no pasa, no sigas al siguiente (mirá el paso 16).

Todos los comandos se pegan en **Anaconda PowerShell Prompt** (se instala en el paso 2), uno
por vez.

### 1. Lo que necesitás

- **Windows 10 u 11.** No anda en Mac ni en Linux: usa partes de Windows para el audio y las ventanas.
- **Placa de video NVIDIA** (de 6 GB o más de memoria, idealmente). Sin NVIDIA no transcribe.
- **Unos 10 GB libres** en disco: 6 para los modelos y el resto para los programas.
- **Micrófono**, si vas a usar el asistente de voz.
- Opcional, para hablar con Laura: cuenta de **Claude** (plan Pro o Max) o de **ChatGPT Plus**.

### 2. Los programas de base

Abrí **PowerShell** (tecla Windows → escribí "PowerShell" → Enter) y pegá:

```powershell
winget install -e --id Git.Git
winget install -e --id Anaconda.Miniconda3
winget install -e --id Gyan.FFmpeg
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Google.Chrome
```

Si alguno dice que ya está instalado, está bien. **Cerrá esa ventana** cuando termine.

Desde ahora usá **Anaconda PowerShell Prompt**: tecla Windows → escribí "Anaconda
PowerShell" → Enter.

**Anduvo si** en Anaconda PowerShell Prompt estos tres comandos muestran un número de versión:

```powershell
git --version
ffmpeg -version
node --version
```

Y con `nvidia-smi` tiene que aparecer el nombre de tu placa.

### 3. Bajar el proyecto

```powershell
cd $HOME
git clone https://github.com/JonesMartin1/panel-de-agentes-aop.git wpp-transcriptor
cd wpp-transcriptor
```

**Anduvo si** existe la carpeta `wpp-transcriptor` en tu carpeta de usuario, con `panel.py` adentro.

### 4. El entorno de Python y las librerías

```powershell
conda create -n wpp python=3.11 -y
conda activate wpp
pip install -r requirements.txt
playwright install chromium
```

Tarda varios minutos. Si `pip` falla con un error de **certificado** (pasa en redes que
revisan el tráfico, como algunas oficinas o antivirus), repetilo así:

```powershell
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

**Anduvo si** termina con `Successfully installed …` y sin líneas rojas de `ERROR`.

⚠ **Cada vez que abras una ventana nueva**, antes de nada: `conda activate wpp` y
`cd $HOME\wpp-transcriptor`. Si te olvidás, vas a ver errores de "No module named…".

### 5. Tus claves (el archivo `.env`)

```powershell
copy .env.ejemplo .env
notepad .env
```

Se abre el Bloc de notas. Para arrancar alcanza con **dos líneas**:

- `WPP_MODELOS=` → una carpeta con lugar para los modelos, por ejemplo `C:\IA\modelos`.
  No hace falta crearla.
- `GEMINI_API_KEY=` → la clave de Gemini, que es **gratis**: entrá a
  <https://aistudio.google.com/apikey>, tocá "Create API key" y pegala.

Guardá (Ctrl+S) y cerrá. **Todo lo demás del archivo es opcional**: lo que quede vacío
simplemente apaga esa parte, no rompe nada. Cada línea tiene su explicación.

⚠ **El `.env` es solo tuyo**: no lo mandes a nadie ni lo subas a GitHub (ya está excluido).

### 6. Bajar los modelos (una sola vez)

El proyecto **no baja los modelos solo**: si no están, no arranca. Pegá esta línea tal cual.
Baja los cuatro modelos de Whisper, unos 5 GB, a la carpeta que pusiste en `WPP_MODELOS`:

```powershell
python -c "import truststore; truststore.inject_into_ssl(); from faster_whisper import download_model; from app.rutas import DIR_MODELOS; [print(download_model(m, cache_dir=str(DIR_MODELOS))) for m in ('large-v3', 'large-v3-turbo', 'small', 'tiny')]"
```

Después, la voz que habla (Piper). **Cambiá `C:\IA\modelos` en la primera línea** si en el
`.env` pusiste otra carpeta:

```powershell
$m = "C:\IA\modelos"
New-Item -ItemType Directory -Force "$m\piper" | Out-Null
$u = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_AR/daniela/high/es_AR-daniela-high.onnx"
Invoke-WebRequest $u -OutFile "$m\piper\es_AR-daniela-high.onnx"
Invoke-WebRequest "$u.json" -OutFile "$m\piper\es_AR-daniela-high.onnx.json"
```

**Anduvo si** el primer comando imprime cuatro rutas (una por modelo) y en la carpeta
`piper` quedan los dos archivos `es_AR-daniela-high`.

### 7. Primera prueba: transcribir un audio

Grabá cualquier cosa con la **Grabadora de sonidos** de Windows (o usá un audio de WhatsApp
que tengas guardado) y pasale la ruta:

```powershell
python -m app.nucleo.transcribir "C:\ruta\a\tu\audio.m4a" --analizar
```

Tip: podés **arrastrar el archivo** a la ventana y se escribe la ruta sola.

**Anduvo si** aparece el texto de lo que dijiste y después un análisis. Si llegaste acá, el
corazón del proyecto funciona. Lo que sigue es opcional.

### 8. El panel y el asistente de voz

```powershell
python panel.py
```

Dejá esa ventana abierta (si la cerrás, se apaga todo) y abrí en Chrome
<http://localhost:8750>.

1. Tocá **Probar micrófono** y hablá: te tiene que dar un veredicto.
2. Prendé **Voz**. Tarda unos 20 segundos; cuando está lista dice *"Listo, te escucho"*.
3. Decí **"Venus, qué hora es"**.

**Anduvo si** te contesta la hora en voz alta.

### 9. Hablar con Laura (Claude o ChatGPT) — opcional

Para Claude:

```powershell
npm install -g @anthropic-ai/claude-code
claude
```

La primera vez te abre el navegador para iniciar sesión con tu cuenta de Claude. Cuando
entres, escribí `/exit`.

Para ChatGPT, lo mismo con `npm install -g @openai/codex` y `codex login`.

En el `.env`, `CLAUDE_VOZ_MODO=lectura` hace que Laura solo **lea y busque**. Con
`completo` también puede escribir archivos y ejecutar comandos en tu PC: cambialo solo cuando
te sientas cómodo.

**Anduvo si** después de reiniciar la Voz desde el panel, "Laura, contame un chiste" te
contesta.

### 10. Mandarle audios por Telegram — opcional

1. En Telegram, buscá **@BotFather**, escribile `/newbot` y seguí los pasos. Te da un
   **token**: pegalo en `TELEGRAM_TOKEN=` del `.env`.
2. En el panel prendé **Servidor**, buscá tu bot en Telegram y escribile `/start`: te
   contesta con tu **id** (un número).
3. Poné ese número en `TELEGRAM_DEST_ID=` y en `TELEGRAM_ALLOWED_IDS=`, y reiniciá el
   Servidor desde el panel.

⚠ `TELEGRAM_ALLOWED_IDS` es quien puede **hablarle a Laura**, y Laura puede ejecutar
comandos en tu PC. Poné **solo tu id**.

**Anduvo si** le mandás un audio al bot y te devuelve la transcripción.

**WhatsApp** pide bastante más: un servicio que conecte tu número (WaSenderAPI, pago, o
Evolution API en un servidor propio) y un túnel de Cloudflare para que tu PC reciba los
mensajes. Si no lo necesitás, salteálo: con Telegram alcanza.

### 11. El cuaderno de notas en Obsidian — opcional

La idea es un **cuaderno compartido entre vos y las IAs**: una carpeta de archivos de
texto (`.md`) que vos leés y ordenás con **Obsidian**, y donde Laura y Claude anotan qué se
hizo en cada proyecto, qué se decidió, qué quedó pendiente y qué está roto. Así, cuando
volvés a un proyecto un mes después, el estado está escrito y no hay que acordarse.

**1. Instalar Obsidian** (es gratis):

```powershell
winget install -e --id Obsidian.Obsidian
```

**2. Crear el cuaderno:** abrí Obsidian → **Create new vault** → nombre `notas` → elegí dónde
guardarlo, por ejemplo `C:\IA\notas`. Adentro creá dos notas:

- `Proyectos.md`: el índice, con un renglón por proyecto enlazado así: `[[wpp-transcriptor]]`.
- `Convenciones.md`: las reglas de formato. Para empezar alcanza con esto: cada nota de
  proyecto empieza con estos tres datos, prosa corta, fechas completas (nunca "ayer") y un
  `## Bugs` al final:

  ```markdown
  ---
  estado: activo
  actualizado: 2026-09-24
  cliente: propio
  ---
  ```

  `estado` puede ser `activo`, `pausado`, `produccion` o `archivado`.

**3. Que Claude lo use:** abrí `notepad $HOME\.claude\CLAUDE.md` (si no existe, se crea) y
pegá esto al final, **cambiando la ruta** por la de tu cuaderno:

```markdown
# Cuaderno de notas (Obsidian)
`C:\IA\notas` es mi cuaderno compartido: notas .md enlazadas con [[dobles corchetes]].
La nota central es Proyectos.md y el formato está en Convenciones.md.
Al terminar algo importante (una función, un arreglo grande, una decisión, algo que se
rompió), actualizá la nota del proyecto: prosa corta, con la fecha, y refrescá `actualizado`.
Si el proyecto no tiene nota, creala y enlazala desde Proyectos.md.
Los bugs van en `## Bugs` al final: una viñeta por bug con fecha, estado y qué se ve.
Nada de claves, tokens ni datos de clientes en el cuaderno.
```

Ese archivo es tu configuración personal de Claude: vale para **todos** tus proyectos, no
solo para este.

**4. Que Laura lo alcance:** Laura solo puede tocar las carpetas que figuran en `CARPETAS`,
en `app/voz/claude_voz.py`. Agregá ahí la de tu cuaderno, por ejemplo `r"C:\IA\notas"`, y
reiniciá la Voz desde el panel.

**Anduvo si** después de terminar algo le decís a Claude *"anotalo en el cuaderno"* y en
Obsidian aparece la nota del proyecto con lo que se hizo.

### 12. El mapa del código con graphify — opcional

**graphify** arma un **mapa del proyecto**: qué archivo llama a cuál, cómo se conectan las
piezas y por qué se decidió cada cosa. Sirve para que Claude conteste preguntas como *"¿qué
pasa cuando llega un audio?"* mirando el mapa en vez de leer archivos enteros: responde más
rápido y gasta mucho menos. Necesita Claude instalado (paso 9).

**1. Instalarlo** (una sola vez en la PC):

```powershell
winget install -e --id astral-sh.uv
```

Cerrá y volvé a abrir la ventana, y después:

```powershell
uv tool install graphifyy
graphify install
```

`graphify install` le agrega a Claude el comando `/graphify`.

**2. Armar el mapa de este proyecto**, parado en la carpeta del proyecto:

```powershell
claude
```

Y adentro de Claude escribí `/graphify .`. La primera vez tarda unos minutos. Queda en la
carpeta `graphify-out/`, que no se sube a GitHub: cada uno arma el suyo.

**3. Que se actualice solo con cada commit:**

```powershell
graphify hook install
```

Desde ahí, cada commit actualiza el mapa del código solo, sin gastar nada. Los documentos
largos (`README.md`, `INTERFAZ.md`) no se actualizan solos: cuando cambien mucho, corré
`/graphify --update` desde Claude.

El archivo `.graphifyignore` ya deja afuera del mapa los audios, videos e imágenes:
graficarlos obligaría a transcribirlos y le pelearía la placa de video al asistente.

**Anduvo si** existe `graphify-out\graph.json` y, en Claude, `/graphify query "qué pasa cuando llega un audio de Telegram"` te contesta nombrando archivos del proyecto.

### 13. Las skills (atajos para Claude) — opcional

Las **skills** le enseñan a Claude a hacer tareas concretas siempre de la misma manera. Se usan
escribiendo `/nombre` en Claude, o solas cuando reconoce el pedido. Vienen en la carpeta
`skills/` del proyecto:

- `/notas`: deja al día la nota del proyecto en tu cuaderno de Obsidian (paso 11).
- `/avisar`: te manda un mensaje al celular cuando algo termina o se rompe.
- `/buzon`: lo que le decís a Laura por voz le llega a la sesión de Claude.
- `/pizarra`: pega papelitos en el pizarrón del panel.
- `/paralelo`: prepara un proyecto para trabajar con 2-3 agentes a la vez.
- `/grill-me`: te interroga sobre un plan antes de ejecutarlo.
- `/leeme`: le pone voz a un informe.
- `/3d`: convierte una imagen en un modelo 3D (necesita Hunyuan3D, pesado).

Para instalarlas todas, parado en la carpeta del proyecto:

```powershell
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse -Force .\skills\* $HOME\.claude\skills\
Remove-Item $HOME\.claude\skills\README.md
```

`avisar` y `buzon` necesitan un paso más de configuración (el bot de Telegram y un *hook*):
está explicado en [`skills/README.md`](skills/README.md), junto con `prompt-master`, que se baja
de su autor original.

**Anduvo si** en una sesión nueva de Claude escribís `/` y aparecen `notas`, `avisar`,
`grill-me` y las demás.

Si las skills del repo cambian, las tuyas no cambian solas: después de un `git pull`, volvé a
correr el `Copy-Item` de arriba.

### 14. Actualizar a la última versión

```powershell
conda activate wpp
cd $HOME\wpp-transcriptor
git pull
pip install -r requirements.txt
```

Cerrá el panel y volvé a abrirlo (`python panel.py`) para que tome los cambios.

### 15. Lo que no va a andar, y está bien

El proyecto nació en una máquina concreta y algunas partes necesitan que las configures:

| Qué | Qué hacer |
|---|---|
| El servicio "Túnel" del panel | Necesita tu propio túnel de Cloudflare: copiá `wpp-config.ejemplo.yml` como `wpp-config.yml` y completalo. Solo hace falta para WhatsApp y para hablarle a Laura desde el celular |
| El acceso directo "Servidor IA" y `launcher.vbs` | Apuntan a la carpeta original. Usá `python panel.py`, o editá `launcher.vbs` con tu ruta |
| Los `.bat` de `lanzadores/` | Tienen rutas de ejemplo (`D:\IA\...`). Cambialas por las tuyas antes de usarlos |
| El generador 3D | Necesita Hunyuan3D-2 instalado aparte (ver la skill `3d`) |
| Las carpetas que Laura puede tocar | De fábrica, la carpeta que contiene al proyecto. Sumá las tuyas en `CARPETAS`, en `app/voz/claude_voz.py` |
| La sensibilidad del micrófono | Está calibrada para unos auriculares en particular. Si se dispara solo o no te escucha, abrí un issue |

### 16. Si algo falla

1. Fijate que la ventana tenga `(wpp)` al principio de la línea. Si no, `conda activate wpp`.
2. Mirá la carpeta `logs/`: `voz.log`, `telegram.log` y `webhook.log` dicen qué pasó.
3. Casi todo lo que "no anda" es una clave vacía en el `.env` o un modelo que no se bajó (paso 6).
4. Si tenés Claude instalado (paso 9), abrí `claude` en la carpeta del proyecto y decile:
   *"Leé el README y ayudame con este error"*, y pegale el error.

---

# Cómo funciona por dentro

Lo que sigue es el manual de trabajo del proyecto: la arquitectura, las decisiones y las
trampas que ya costaron caro. Para usar el proyecto no hace falta leerlo; para modificarlo, sí.
Está escrito en primera persona del día a día en que se armó, en una laptop con Windows 11 y
una RTX 4070 de 8 GB: las rutas `D:\IA\...` que aparecen son las de esa máquina.

Dos grandes piezas que conviven:

1. **Transcriptor de WhatsApp/Telegram**: recibe audios y videos, los transcribe con Whisper local (GPU) y los analiza con Gemini.
2. **Asistente de voz** ("Venus" y "Laura"): manos libres estilo Alexa para controlar la PC, dictar texto y conversar con Claude.

> Entorno Python: el conda `wpp` de la instalación. GPU CUDA para Whisper `turbo`.
> Si tu red intercepta HTTPS (antivirus, proxy): conda/pip/Python necesitan el cert store de Windows (`truststore` / `--trusted-host`).

---

## Arranque

| Cómo | Qué hace |
|---|---|
| Acceso directo **"Servidor IA"** (escritorio) → `launcher.vbs` | Lanza `panel.py --auto`: prende TODO (servidor + voz). Al estar lista, la voz dice **"Listo, te escucho"** |
| Panel web | `http://localhost:8750` — tarjetas Servidor / Voz / Conversación en vivo, con botones Prender/Apagar |

> **Nada de esto arranca solo con Windows.** Verificado: no hay entradas del proyecto en las
> carpetas de Inicio, ni en las claves `Run` del registro, ni en tareas programadas. Si prendés
> la máquina y no tocás el acceso directo, el asistente no existe. (Sí arrancan solos, por su
> cuenta, Ollama y el túnel de n8n.)

### ⏸ Pausar escucha (para llamadas, Discord o jugar)

En la tarjeta de Voz hay un botón **"Pausar escucha"**. Deja de escuchar "Venus"/"Laura"
pero **no descarga los modelos**, así que pausar y volver son **instantáneos** — contra los
~20 s que tarda prender la voz de cero. **F9 y los atajos siguen funcionando.**

Cómo está hecho: el panel crea o borra `pausa_escucha.flag` (definido en `app/rutas.py`) y
`voz.py` lo lee **cada medio segundo en un hilo aparte**. A propósito no se consulta el disco
dentro del callback de audio, que corre decenas de veces por segundo.

El micrófono se abre en **WASAPI modo compartido**, así que Discord, WhatsApp y los juegos
pueden usarlo al mismo tiempo: el asistente no te lo bloquea. Lo que sí conviene es pausarlo,
para que no se autodispare con la conversación ni le pelee la GPU al juego.

## Los servicios

| Servicio | Archivo | Qué es |
|---|---|---|
| Bot de Telegram | `bot_telegram.py` | Recibe audios/videos por Telegram, responde transcripción + análisis. Límite API: 20 MB (avisa). Los mensajes de **texto** van a **Laura** (misma sesión que por voz): el bot deja la pregunta en un buzón de archivos (`app/voz/buzon.py`) y la atiende `voz.py`, que es quien tiene el proceso `claude` vivo — por eso hablar con Laura por Telegram necesita el servicio de voz prendido. **Dos candados independientes** en el `.env`: `TELEGRAM_EQUIPO_IDS` (quién puede transcribir — vacío = abierto, pensado para compartirlo con el equipo de devs) y `TELEGRAM_ALLOWED_IDS` (quién puede hablarle a Laura — SIEMPRE solo Martín: ella ejecuta comandos en la máquina, así que sumar gente a un candado nunca abre el otro) |
| Webhook WhatsApp | `webhook_wasender.py` | Recibe webhooks de WasenderAPI (puerto 8080), desencripta media, transcribe. También sirve **`/subir`**: página web para subir audios largos (>20 MB) directo; resultado va a Telegram |
| Túnel Cloudflare | `cloudflared` | Expone el webhook en tu hostname (el de `wpp-config.yml`) (subidas por túnel: tope ~100 MB; por LAN `http://IP:8080/subir` sin tope). El mismo túnel también expone `/laura-voz` (ver "Laura por llamada" abajo), como una ruta aparte del mismo hostname — sin DNS nueva |
| Voz | `voz.py` | El asistente completo (ver abajo). También levanta, en un hilo propio (`app/voz/llamada.py`), el servidor de "Laura por llamada" |
| Panel | `panel.py` | Servidor FastAPI del panel (puerto 8750). Endpoints: `/status`, `/start[/voz]`, `/stop[/voz]`, `/micros`, `/micro`, `/medidor`, `/chat` |

## El asistente de voz (`voz.py`)

- **Wake words**: **"Venus"** = asistente local (comandos y respuestas rápidas con Gemini) · **"Laura"** = Claude Code por voz (modo completo: puede leer/escribir archivos y ejecutar comandos, con confirmación hablada antes de tocar nada).
- **Teclas**: `F9` dicta donde esté el cursor · `Shift+F9` asistente · `Ctrl+F9` Claude.
- **Venus**: un comando por vez (así lo quiere Martín). "Venus, escribí/anotá..." = dictado manos libres. Números solos = cambiar de escritorio. Al captar lo que dijiste responde **"Ok"** (no tocar, así lo quiere).
- **Laura no dice nada al captar.** El "Entiendo." se sacó el 2026-08-10: la música de espera ya avisa que está trabajando, y encima `winsound` reproduce de a uno, así que la música se lo cortaba a mitad de palabra. Para volver a activarlo, buscar `ENTIENDO_TEXTO` en `app/voz/voz.py`.
- **Laura**: conversacional (tras responder te da **4 s para empezar a hablar** — `SEGUIMIENTO` —, hasta 25 idas y vueltas sin volver a nombrarla). Una vez que arrancaste, tu turno lo cierran `SIL_CORTE` (2,5 s de silencio) y `MAX_CLAUDE` (45 s de tope): bajar `SEGUIMIENTO` no te corta al medio de una frase. La cola que se siente son ~5 s: 0,35 de margen + los 4 s + el aviso "Cierro" (~0,7 s). Si molesta, lo que queda por sacar es el aviso, no el número. Interrupción real por voz: "pará / basta / cortala / stop". Música de espera suave mientras piensa (`musica_espera.wav`). **Si terminás haciendo otra cosa mientras ella trabaja, espera un silencio y anuncia "Laura terminó. ..."** (no se descarta el trabajo largo). Tope por tarea: 10 min.
- **Sesión de Laura**: proceso `claude` persistente (stream-json, ~3 s por turno) + sesión guardada en `claude_sesion.json` — sobrevive reinicios. "Olvidate" archiva la actual y arranca otra.

### 📅 El "día de Laura": una sesión nueva por día, y volver si hace falta

Cada pregunta a Laura **reenvía toda la conversación anterior**: la número 50 le manda las
49 previas completas. Por eso una charla que dura días se encarece sola. Pero tirar el
historial todos los días no cuesta nada de verdad, porque **lo que importa está en el
`README.md` y el `CLAUDE.md`, no en la charla** — su identidad y las reglas se le pasan en
cada arranque con `--append-system-prompt`. La sesión es el hilo; el conocimiento está en el repo.

**El día NO arranca a la medianoche, arranca a la 1 de la tarde** (`CORTE_HORA = 13`).
Con el corte a las 12 la sesión se partía en dos en plena madrugada, que es cuando se
trabaja acá. Todo lo anterior a las 13:00 cuenta como el día anterior.

La primera vez que le hablás en un día nuevo, **antes de gastar un solo token**, contesta:

> *"Hola, hoy es nuestra primera sesión del día. ¿Querés continuar con la sesión
> anterior o empezamos un proyecto nuevo?"*

Ese saludo lo dice **Piper, no Claude** — cuesta cero. Y lo que hayas preguntado queda
guardado en `_pendiente`: se contesta en cuanto elegís, no se pierde.

| Le decís | Qué hace |
|---|---|
| "continuá" · "seguí con la anterior" · "la de ayer" · "dale" | retoma la misma sesión, ahora contada como de hoy |
| "empecemos un proyecto nuevo" · "de cero" · "no" | archiva la de ayer y abre una limpia |
| "¿de qué hablamos ayer?" · "no me acuerdo" · "¿dónde quedamos?" | **te resume la sesión anterior** y arranca el día |
| cualquier otra cosa ("poné música") | resuelve el día con sesión nueva y **atiende tu pedido igual** |

El resumen **no reabre la sesión vieja**: lee su `.jsonl` de `CLAUDE_SESIONES` y le pasa la
charla como texto a la sesión de hoy. Sale más barato y no hay que malabarear dos procesos.
Las sesiones de Laura son chicas (contesta en dos frases: ~4.000 tokens un día entero).

⚠ **Cuatro trampas que costaron encontrar, las cuatro cubiertas por `pruebas/test_dia_laura.py`:**

- **"seguí con la anterior" apretaba play.** El patrón de `media_playpause` tiene `segu[ií]`.
  Por eso la respuesta al saludo se intercepta en `_manejar_texto` **antes que
  `acciones.ejecutar`**, y es lo primero de la función.
- **"no, continuemos" elegía sesión nueva**, porque ganaba el "no". Ahora el verbo explícito
  (`_SIGUE_VERBO`) se mira antes que el sí/no suelto.
- **"continuá donde quedamos" pedía un resumen**, porque ganaba el "quedamos". Mismo arreglo.
  "¿Dónde quedamos?" **pelado** sí es un resumen: preguntás para poder decidir.
- **El resumen se detectaba a sí mismo.** El prompt lleva la charla de ayer adentro; si ayer
  dijiste "de qué hablamos", el detector se disparaba con su propio pedido y se llamaba a sí
  mismo **para siempre**. De ahí el `crudo=True` en `resumen_de()`.

Y `GRACIA_CORTE` (30 min): si venías hablando hace un rato, **no te interrumpe** con la
pregunta del día aunque el reloj haya cruzado las 13:00. Espera un hueco de verdad.
- **Modelos**: Whisper `turbo` en CUDA para transcribir; wake word con `tiny` en **CPU** int8 (inmune a la GPU cargada, ~0,5 s constante).

### 📱 WhatsApp: "Venus, WhatsApp"

Trae la ventana de WhatsApp **al escritorio virtual que estás mirando** y la pone al
frente (con `pyvda`, el mismo que cambia de escritorio). Si no está abierto, lo abre
(protocolo `whatsapp:`). El detalle importante: si WhatsApp quedó en otro escritorio,
**la ventana viene a vos** — no te saltea a vos al escritorio de ella, que es lo que
hace Windows si la activás por la barra de tareas. También entra por "abrí/traeme/poné
el whatsapp". "Mandale un whatsapp a Juan" NO dispara esto: eso sigue siendo charla
para Laura. Casos en `pruebas/test_ruteo_whatsapp.py` — correr eso si se toca el orden
de `COMANDOS` en `app/voz/acciones.py`.

### 🎵 Spotify: "Venus, poné tal canción"

Busca y reproduce con la **API oficial** (`app/voz/spotify.py`), no automatizando la
ventana: pone la canción exacta en ~1 s sin depender del foco. **Necesita Premium** —
los endpoints de reproducción de la API son solo Premium.

Setup, una sola vez (ver el encabezado de `app/voz/spotify.py`):

1. `developer.spotify.com/dashboard` → Create app. Redirect URI **exacta**:
   `http://127.0.0.1:8888/callback` — con **`127.0.0.1`, no `localhost`**: Spotify rechaza `localhost`.
2. `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` en el `.env`.
3. `python -m app.voz.spotify --autorizar` → se abre el navegador, aceptás, y el token
   queda en `spotify_token.json` (fuera de git). El access token se renueva solo, pero
   ⚠ el dashboard marca **"Refresh Token Lifetime: 180 days"**: cada ~180 días hay que
   volver a correr `--autorizar`. Si Venus dice "no pude renovar el token de Spotify",
   es eso — no está roto, se venció la autorización.
4. Probar sin la voz: `python -m app.voz.spotify "californication"`.

⚠ **El paso 3 falló cuatro veces seguidas y siempre por lo mismo: el servidor local
sale de aire antes de que llegue el clic.** `--autorizar` abre el navegador y se queda
esperando, pero si nadie aprieta *Agree* dentro de la ventana, el server se cierra y el
navegador se come un `ERR_CONNECTION_REFUSED` con el código ya en la mano. Ojo que **el
código igual sirve**: quedó en la barra de direcciones. Dos salidas, en orden de comodidad:

- **Volver a levantar el server y apretar *Reload* en esa misma pestaña.** El navegador
  reenvía el mismo `?code=...` y se canjea al toque. No hay que aceptar de nuevo ni copiar nada.
- Copiar la URL completa y `python -m app.voz.spotify --codigo "<esa URL>"`.

En los dos casos hay **~10 minutos** desde el *Agree*: pasado eso, `invalid_grant` y a
aceptar otra vez. Y `ERR_CONNECTION_REFUSED` en `127.0.0.1:8888` **no es el antivirus** —
es que el server ya no está escuchando. Antes de sospechar del firewall, mirá si el
proceso sigue vivo.

Qué entiende, y a qué lo traduce:

| Le decís | Busca |
|---|---|
| "poné Californication" | el tema |
| "poneme algo de Soda Stereo" · "la radio de Nirvana" · "lo mejor de Queen" | el **artista** (sus temas top) |
| "tocame mi lista de correr" · "la playlist de entrenamiento" | la **playlist** |
| "poné Spotify" (a secas) | abre la app, no busca un tema llamado "Spotify" |

**Si Spotify no está abierto, lo abre** y espera hasta 25 s a que se registre como
dispositivo antes de darle play.

⚠ Tres cosas de `COMANDOS` en `acciones.py` que no hay que romper:
- El comando de Spotify va **antes** de `media_playpause`, que tiene `reproduc[ií]` en su
  patrón: si no, "reproducí tal canción" solo apretaría play sin poner nada.
- `_norm()` **saca los acentos**, así que los patrones van **sin tildes** (llega `pone`, no
  `poné`). Poner `[eé]` ahí no sirve para nada.
- **El ancla `^` sola no alcanza: hay que dejar entrar la cortesía.** `\W*` se come los
  signos, **no las palabras**. "¿Puedes poner la radio de los Red Hot Chili Peppers?"
  **no matcheaba nada** y se lo comía el LLM, que contestaba "No pude hacer eso" —
  falló tres veces al hilo el 2026-08-11 y parecía que Spotify estaba roto, cuando el
  token andaba perfecto. Cualquier comando nuevo tiene que tolerar `puedes / podés /
  podrías / por favor / quiero que / me` adelante, y el verbo con sus pegotes
  (`ponerme`, `ponémelo`), porque **así se habla**. Un `^` pelado te hace creer que el
  bug está tres capas más abajo.

### 🔋 Cupo de tokens: te avisa antes de quedarte sin nada

`app/voz/cupo.py` suma el `usage` real de **todas** tus sesiones de Claude Code (los
`.jsonl` lo guardan por mensaje), no solo las de Laura. Corré `python -m app.voz.cupo`
para ver los tres cupos.

**Son tres, y el que se llena no es el que uno espera.** Medido el 2026-08-11 (plan Max):

| Cupo | Estaba | Límite calibrado |
|---|---|---|
| sesión de 5 horas | **14 %** | ~257 M |
| semanal | 58 % | ~2.350 M |
| **semanal de Fable** | **83 %** | ~475 M |

Vigilar solo el de 5 horas es vigilar justo el que nunca se llena.

⭐ Pero **el de Fable no habla**: se mide y se ve en el medidor, y nada más
(`CUPOS_QUE_AVISAN`). Es el que menos importa saber en el momento, porque no es algo
sobre lo que se pueda hacer nada mientras trabajás. El aviso hablado sale solo por el
**de 5 horas** y el **semanal**.

Y **Laura no es el problema**, que era la sospecha original. Por modelo, 7 días:
`sonnet-5` (Laura) **0,2 %** · `opus-4-8` 40,7 % · `opus-5` (VS Code) 30,1 % ·
`fable-5` 28,8 %. Hablarle más al asistente no te deja sin cupo; lo que consume son las
sesiones de programación.

**Dos avisos distintos:**

1. **Al 70 %** (`AVISO_PORCENTAJE`), **por iniciativa propia**, sin que le hables a nadie:
   *"Ojo, estás llegando al límite: ya usaste el 82 por ciento del cupo semanal de Fable."*
   Lo dice `_avisar_sistema()` en `voz.py`, que **espera un hueco**: que no estés hablando,
   que no esté hablando ella, y que la escucha **no esté en pausa** (si pausaste estás en
   una llamada). Espera hasta una hora; no lo tira, lo guarda. Se rearma al bajar del 65 %
   (`REARMAR_PORCENTAJE`), para que un cupo en el filo no te avise diez veces.
2. **Cuando se agota**, en vez de "No pude hablar con Claude": dice que fue el cupo, **no
   reintenta** (reintentar un límite es regalar 10 s para fallar igual) y te recuerda que
   Venus sigue andando.

⚠ **Cómo calibrarlo** (hace falta una vez): `/usage` en Claude Code y comparar con
`python -m app.voz.cupo`. El límite del plan **no está en el disco** — `.credentials.json`
trae qué plan tenés, nada del consumo. Los `LIMITE_*` están arriba de `cupo.py`.

⚠ **Tres detalles que costaron:**
- **La ventana de 5 h de Claude es FIJA** ("resets in 3h"), la de acá es **móvil**: mide
  igual o más, así que el aviso puede adelantarse. Para avisar, errar por adelantado va bien.
- **El patrón de "sin cupo" va en dos versiones.** El ancho se usa sobre el mensaje de
  error; el **angosto** sobre la respuesta de Laura, porque con `429` o `quota` a secas un
  *"el archivo tiene 429 líneas"* te hacía escuchar "me quedé sin cupo" estando todo bien.
- **`SIN_SENAL_SEG` (120 s) no reemplaza a `TIMEOUT` (600 s)**: una tarea larga sigue
  mandando eventos por el stream, así que si no llega **ninguno** está colgada. Bajar el
  total rompería los refactors largos; esto corta los cuelgues sin tocarlos.

### 🔊 Lectura automática: Venus te lee las respuestas de una sesión de Claude Code

En el panel hay un selector **proyecto → sesión**. Elegís una, apretás "Leer esta", y
cada respuesta que esa sesión termine se lee en voz alta — sin pedirle "leeme" cada vez.
**Una sola sesión a la vez** (el parlante tiene un solo dueño): elegir otra suelta la
anterior. Se apaga con el botón o por voz: **"Venus, dejá de leer"**.

Cómo funciona: todo Claude Code escribe su conversación EN VIVO en un `.jsonl` (carpetas
en `CLAUDE_PROYECTOS`, registro de sesiones vivas con nombre en `CLAUDE_REGISTRO`).
`app/voz/seguir.py` mira el archivo elegido como una cinta que avanza; el panel escribe
la elección en `seguir_lectura.json` (la perilla on/off, mismo patrón que
`pausa_escucha.flag`) y un hilo en `voz.py` la lee cada segundo. Para hablar usa la
espera-de-hueco de los avisos del sistema: no te pisa, no habla en pausa.

⚠ Detalles con historia:
- **Fin de respuesta**: el jsonl no trae marcador utilizable (`stopReason` viene vacío).
  Regla doble: llega tu próximo mensaje → lo anterior terminó; o el archivo queda quieto
  `QUIETUD_SEG` (5 s). Costado conocido: una herramienta lenta a mitad de turno hace que
  el texto previo se lea durante la espera — en la práctica te va contando lo que hace.
- **Se lee SOLO el texto del asistente**: afuera herramientas, pensamiento interno,
  sub-agentes (`isSidechain`) y mensajes sintéticos. Y los resultados de herramienta
  llegan como `type=user` — sin filtrarlos, cerrarían turnos que no terminaron.
- Arranca desde el **final** del archivo: seguir una sesión es escuchar lo que venga,
  no que te recite el historial. Tope `LECTURA_MAX` (4.000 caracteres ≈ 2 min de voz):
  el resto "queda en pantalla". Cortás con "pará", como siempre.
- Hay 6 casos en `pruebas/test_seguir.py` — correr eso si se toca el extractor.

### ✏️ Escribir en sesión: "Venus, escribí en la sesión del disco: ..."

La ida del círculo (la lectura automática es la vuelta): dictás y el texto aterriza en
la sesión de Claude Code que elijas. **El destino es UNA perilla con dos manos**: el
selector del panel o la voz — cualquiera de los dos lo cambia (`escribir_en.json`), y
el panel lo refleja solo.

Formas de usarlo (⭐ regla 2026-08-11: **"Venus, escribí" va SIEMPRE a la sesión
elegida** — para dictar donde esté el cursor está F9, que no cambió):
- **"Venus, seleccioná la sesión del disco"** → solo gira la perilla (también sirven
  "elegí / cambiá a / pasá a la sesión..."). Sin sesión elegida, "Venus escribí" no
  adivina: te dice cómo elegir una.
- **"Venus, escribí: hola qué tal"** o **"Venus, escribí"** (y dictás después) → trae
  al frente la ventana de la sesión elegida y pega ahí.
- **"Venus, escribí en la sesión del tango: hola"** → el combo: elige Y escribe en una
  sola frase.

Y el remate del flujo: **"Venus, enter"** aprieta Enter **donde esté el cursor en ese
momento** — sin tocar ninguna ventana. Es para cuando ya dictaste, revisaste el texto en
pantalla, y solo falta la tecla. A propósito NO va a la sesión elegida: te movería el
foco justo cuando estás trabajando. También valen "dale enter" y "apretá enter"; la
frase tiene que SER eso — "el enter del teclado" no manda nada.

⚠ Reglas de seguridad, en orden de importancia:
- **Pega pero NO manda... salvo que VOS digas "enter" al final**: *"escribí: dale para
  adelante, enter"* pega Y manda. La palabra dicha es tu firma — no es Venus mandando
  sola, sos vos autorizando en la misma frase. Solo la palabra "enter" al FINAL (no
  "entre", que es castellano común; "la tecla enter del teclado" en el medio no manda),
  y "enter" solo, sin texto adelante, no hace nada. Vale también para F9.
- **Verifica la ventana DESPUÉS de activarla**: si la que quedó al frente no es la
  buscada, no pega nada y avisa. Pegar en la ventana equivocada es peor que no pegar.
- **Ante el empate no adivina**: "del disco" con dos sesiones de disco vivas → te pide
  que aclares. El puntaje es por palabras del título + proyecto, con prefijos de 4
  letras o más ("tienda" encuentra "Tienda2", que lleva el número pegado).
- El riesgo residual documentado: el foco dentro de VS Code queda donde estaba. Si el
  cursor estaba en el editor y no en el chat, el texto se pega en el archivo abierto —
  por eso avisa dónde escribió, y un Ctrl+Z lo deshace.
- Casos en `pruebas/test_escribir.py` (patrón y buscador, sin arrancar el asistente).

### 📞 Laura por llamada: hablarle desde el celular, en vivo, desde donde sea

Ni Telegram ni WhatsApp soportan llamadas de bot (es una limitación de esas plataformas,
no de este proyecto). La alternativa: una página web en `https://<tu-hostname>/laura-voz`
— la abrís en el navegador del celular, mantenés apretado el botón para hablar, soltás, y
te contesta con audio real. Es la MISMA Laura, mismo proceso, misma memoria que por
micrófono y por Telegram — la respuesta también respeta el saludo del "día de Laura".

No es una llamada de telefonía real (no hay interrupción a mitad de frase, es
"mantené y hablá, soltá y escuchá"), pero corre sobre el mismo Whisper turbo + Piper que
ya está cargado en la GPU: no se duplica ningún modelo. `app/voz/llamada.py` recibe esos
objetos ya cargados por parámetro (nunca los importa), justo para poder probarse sin
levantar el asistente entero.

**Seguridad, en capas** (Laura ejecuta comandos en esta PC — no es solo transcribir):
1. El servidor solo escucha en `127.0.0.1:8760`: nadie en la misma wifi lo encuentra por
   IP, únicamente por el hostname del túnel.
2. Requiere el header `X-Laura-Token` con el secreto de `LAURA_VOZ_TOKEN` (`.env`). Sin
   ese secreto configurado, la llamada queda **apagada**, nunca "abierta por las dudas".
   La página lo pide una vez y lo guarda en `sessionStorage` (se olvida al cerrar la pestaña).
3. Los intentos fallidos se cuentan por IP real (`CF-Connecting-IP`, la que manda
   Cloudflare) y se bloquean 10 minutos pasados 5 intentos.
4. **Recomendado además** (no lo hace el código, se configura una vez en el dashboard):
   [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
   sobre el path `/laura-voz*` de tu hostname — gratis hasta 50 usuarios, exige un
   login (código a tu email) ANTES de que el pedido llegue siquiera a esta máquina. Hay
   que crear la Access Application con el path acotado a `/laura-voz*`: el resto del
   hostname (`/webhook`, `/subir`, `/procesar-media`) lo llaman n8n y WasenderAPI sin
   login interactivo, y gatear el hostname entero rompería esos flujos.

La ruta `/laura-voz` vive en el MISMO túnel y hostname que el webhook (`wpp-config.yml`,
regla de `path` antes de la genérica): no hace falta una DNS nueva.

### Micrófono (zona de gotchas ⚠)

- Micrófono actual: **ROG CETRA OPEN WIRELESS** (dongle USB). Elegible desde el panel (persiste en `config_dictado.json`).
- Niveles de referencia: ROG puesto hablando ≈ 0.05 rms · laptop a distancia ≈ 0.01–0.03 · umbrales `SIL_UMBRAL = WAKE_UMBRAL = 0.008`.
- Panel → **"Probar micrófono (15 s)"**: barra en vivo con veredicto (silencio digital / bajo umbral / justo / bien).
- ⚠ PortAudio congela la lista de dispositivos al arrancar el proceso: `/micros` del panel hace `sd._terminate()+sd._initialize()` para refrescar.
- ⚠ Si tocás la **ganancia de grabación** en Gear Link (Settings → Volume → Record), los cuatro umbrales de arriba quedan desfasados. Hay que volver a medir con "Probar micrófono" y actualizar código y README.

#### ⚠ El ROG no sirve para escucha permanente (auditado el 2026-08-10)

**No se puede arreglar configurándolo.** Recorrí Gear Link entero (`gearlink.asus.com`, versión web
de PC — la app móvil **no ve el dongle**, solo Bluetooth). Esto es todo lo que existe:

| Ajuste | Estado | Sirve |
|---|---|---|
| Noise Gate | **ya venía en OFF** | no era el culpable |
| Perfect Voice | **ya venía en OFF** | no era el culpable |
| **AI Noise Cancellation** | **no tiene interruptor** | la ficha la publicita, Gear Link no la deja apagar |
| **Wear detection** | **no tiene interruptor** | pausa el audio al sacarte un auricular |
| Idle mode | era 5 min → **puesto en "Never"** | ✅ sacó el apagado por inactividad |

Con el Noise Gate apagado y aun así dando ~0.00002, **el causante es la cancelación por IA, que es
permanente**. Por eso el ROG entrega el **mismo** casi-cero (~0.00002 rms, unos −94 dBFS, por debajo
del piso de 16 bits) en dos situaciones distintas: sin ponerse, y puesto pero callado. O sea que
**el rms no puede distinguir esos dos estados y ningún umbral lo va a arreglar** — la información no
está en el dato.

Y no es un defecto de ASUS: **toda la categoría hace esto**, porque mantener el micrófono siempre
habilitado destruye la batería. Los auriculares que sí hacen wake word usan chips dedicados de
ultra-bajo consumo. Ni RealtimeSTT (10,1k ★) ni wyoming-satellite implementan watchdog de micrófono:
corren sobre micrófonos tontos, cableados y siempre encendidos, donde el problema no existe.

**Ojo con "Never"**: ya no se duermen, así que se descargan si los dejás fuera del estuche. Guardalos
en el estuche cuando no los uses.

**Lo que conviene a futuro**: un micrófono de escritorio siempre encendido como principal (tipo
ReSpeaker USB Mic Array). Los que traen **AEC en hardware** además cancelan el eco de tus parlantes
en el micrófono, lo que permitiría jubilar el parche de `vad_filter` documentado más abajo.

#### ⚠ Por qué camino de audio entra el micrófono (importa mucho)

El **mismo** micrófono aparece varias veces en la lista de Windows, una por cada camino
de audio. Ejemplo real con el ROG:

| Índice | Camino | Nativa | Sirve |
|---|---|---|---|
| 1 | MME | 44100 | nombre truncado a 31 letras, no coincide |
| 9 | DirectSound | 44100 | anda, pero es emulación legacy |
| **21** | **WASAPI** | 48000 | **el bueno** — necesita `auto_convert` |
| 31 | WDM-KS | 44100 | **no sirve**: `sounddevice` no soporta su API bloqueante |

Antes se tomaba *la primera que coincidiera*, o sea **DirectSound**. El problema: cuando el
dispositivo se va y vuelve (los inalámbricos se duermen, el dongle se re-enumera), un buffer
de captura de DirectSound **se queda entregando ceros sin dar error**. Los callbacks siguen
llegando —así que el watchdog lo ve "vivo"— pero no capta nada. Eso explica el
*"se muere el micrófono a cada rato"* mucho mejor que culpar a los auriculares.

Ahora `_candidatos_micro()` prueba **WASAPI → DirectSound → predeterminado**, en ese orden.
Dos cosas que costaron descubrirse:

- WASAPI en modo compartido **exige la frecuencia nativa** (48000) y nosotros abrimos a 16000
  para Whisper → `Invalid sample rate [PaErrorCode -9997]`. Se arregla con
  `sd.WasapiSettings(auto_convert=True)`, que hace que PortAudio resamplee solo.
- El predeterminado de Windows queda **último**, no segundo: puede ser otro micrófono.

#### ⚠ Nunca quedarse sin micrófono (el bug del 2026-08-11)

**Qué pasó**: la máquina estuvo suspendida y se reenchufó el dongle. Al suspender, Windows
desarma las conexiones de audio y al despertar arma **otras** con el mismo nombre: la que
`voz.py` tenía agarrada desde hacía 4 horas dejó de existir.

El watchdog lo detectó bien y hasta se recuperó pasando a MME — **estaba escuchando**. El
problema vino después: quiso volver al micrófono configurado, y `_cambiar_stream()`
**cerraba el stream que andaba antes de intentar abrir el nuevo**. El nuevo falló con
`AUDCLNT_E_DEVICE_INVALIDATED` y quedó **sin ninguno**: proceso vivo, panel en verde,
sordo, y sin ningún error visible. Es colgar el teléfono que funciona antes de comprobar
que el otro tiene tono.

**Cómo quedó**:

1. `_cambiar_stream()` **abre primero y cierra después**. Si el nuevo no abre, se queda con
   el que andaba. Si un driver no acepta dos streams sobre el mismo dispositivo, recién ahí
   suelta antes — y si eso falla, cae en la red de seguridad.
2. `_asegurar_algun_stream()` es esa red: prueba los caminos del configurado, después el
   predeterminado, y después **cualquier entrada que abra**. La regla es que nunca puede
   quedar sin micrófono.
3. El watchdog ahora **detecta la vuelta de una suspensión** por el salto del reloj (más de
   60 s entre vueltas de un bucle que duerme 5 s), rearma el micrófono de una y refresca la
   lista de dispositivos con `sd._terminate()+sd._initialize()` (PortAudio la congela al
   arrancar y sigue viendo los de antes). Antes se enteraba recién cuando dejaba de llegar
   audio, y para entonces ya se había hecho lío.
4. Si por cualquier motivo `_stream` queda en `None`, el watchdog lo ve en la vuelta
   siguiente y recupera.

⚠ Pendiente conocido: el **medidor del panel** (`/medidor`) usa su propio código para abrir
el micrófono y **no** tiene la preferencia de WASAPI de `voz.py`, así que después de una
suspensión puede fallar con un error de DirectSound aunque la voz esté escuchando bien.

#### Watchdog del micrófono en `app/voz/voz.py`

Distingue **dos medidas que no son lo mismo**:

- **FLUJO** (`_ultimo_callback`): llegó un callback de audio. Es la única prueba confiable de que el
  dispositivo existe — la cancelación de ruido vacía el *contenido* pero no puede parar el flujo de
  samples. Sin un solo callback en `FLUJO_MUERTO_SEG` (8 s), el dispositivo se fue de verdad.
- **CONTENIDO** (`_ultimo_audio_real`): hay audio real (pico > 0.002). Sirve para saber si te escucha,
  **no** para saber si está vivo.

Cambia de micrófono con **solo dos disparadores**, los dos confiables:

1. **Flujo cortado** — no llegan callbacks.
2. **Verdad de campo** (`_captura_vacia`) — una grabación que *tenía* que traer audio (apretaste una
   tecla o dijiste el nombre) volvió en silencio digital (<0.0005). No puede dar falso positivo.

⚠ **La vieja regla de "120 s pasivos sin pico" se eliminó el 2026-08-10.** Causaba cambios de micrófono
en plena sesión: te quedabas callado dos minutos, el gate de la IA daba casi-cero, y el watchdog
saltaba al array de la laptop — que **sí** capta los parlantes, o sea justo la condición que hace
alucinar a Whisper. Un falso positivo acá sale más caro que un falso negativo.

Además hay **`REFRACTARIO_SEG`** (60 s, "refractory period", como el `--wake-refractory-seconds` de
wyoming-satellite): después de cambiar de micrófono no se vuelve a cambiar por ese rato, en ninguna
de las dos direcciones. Sin eso rebotaba entre dos micrófonos. Cuando el configurado revive, **vuelve
solo** y avisa (¡el "default de Windows" puede ser el mismo micrófono muerto, por eso se sondea de
verdad en vez de confiar!).

### Latencia: medirla antes de tocar nada

`voz.py` loguea sus tiempos en líneas `tiempos:` de `logs/voz.log`. Para leerlas:

```
python -m pruebas.analizar_tiempos        # todo
python -m pruebas.analizar_tiempos 50     # últimas 50 muestras
```

⚠ Esas líneas van con prefijo propio porque **`/chat` del panel parsea con `startswith`**:
poner un timestamp adelante de las otras líneas rompe la conversación en vivo.

Lo medido el 2026-08-10, que descartó dos culpables y encontró el real:

| Etapa | Medición | Veredicto |
|---|---|---|
| Transcribir (Whisper `large-v3-turbo` int8 en GPU) | 12,5× tiempo real, sin espera de lock | **no es el cuello** |
| **Síntesis del TTS (Piper)** | ~30 ms por letra → **344 letras = 10,3 s de silencio** | **era el cuello** |
| Respuesta completa | mediana 14 s, máx 31 s | |

El arreglo fue **sintetizar por trozos** y empezar a reproducir el primero mientras se
generan los demás: la primera palabra pasó de **10,3 s a ~1,7 s** en una respuesta larga,
sin tocar la calidad de la voz. Los trozos crecen 10 % cada uno — ver el aviso en `CLAUDE.md`
sobre por qué ese número no se toca sin volver a medir.

Sigue pendiente medir el LLM por separado (Gemini para Venus, Claude para Laura) para saber
cuánto de la respuesta total es el modelo pensando.

### Otros gotchas que costaron sangre

- ⚠ El system prompt de Laura **no puede tener `\n`** al pasar por el `.CMD` de Windows (rompía `--resume` silenciosamente). Se aplana con regex en `claude_voz.py`.
- ⚠ Usar `dontAsk`, **no** `bypassPermissions` (rompe `--resume`). Sin herramienta `Task` (pisaba el session_id).
- ⚠ Para interrumpir a Laura: `control_request` tipo `interrupt` por stdin (requiere CLI ≥ 2.1.226). **Nunca matar el proceso** — la consulta quedaba pendiente y contestaba después.
- ⚠ Whisper con parlantes: `vad_filter=True` + descartar `no_speech_prob > 0.45`, si no alucina el propio initial_prompt ("Laura/Venus") y se autodispara. Fragmentos de wake con >2 s de antigüedad se descartan (cola de audio con YouTube de fondo).

## Estructura de carpetas

La raíz tiene **solo lo que corre**: los módulos que se importan entre sí y los archivos
que `panel.py` y los lanzadores buscan por ruta. El resto está agrupado.

```
wpp-transcriptor/
├─ launcher.vbs           ← entrada principal (el acceso directo "Servidor IA" apunta acá: NO mover)
├─ panel.py               ← panel web 8750: prende y apaga todos los servicios
├─ config_dictado.json · claude_sesion.json · wpp-config.yml · musica_espera.wav · .env
│
├─ app/                   ← TODO el código
│   ├─ rutas.py           ← ⭐ las rutas del proyecto, en un solo lugar
│   ├─ nucleo/            ← core.py · transcribir.py · procesar.py · analizar_gemini.py
│   ├─ voz/               ← voz.py · asistente.py · dictado.py · escucha.py
│   │                        claude_voz.py · cerebro.py · acciones.py
│   ├─ web/               ← navegador.py · agente_web.py
│   ├─ ingesta/           ← bot_telegram.py · webhook_wasender.py
│   └─ generar_musica_espera.py
│
├─ lanzadores/            ← los .bat (Chrome IA, Iniciar WhatsApp, bot Telegram, Transcribir)
├─ pruebas/               ← las pruebas (probar_*, ver_*, test_*)
├─ skills/                ← atajos para Claude Code (ver skills/README.md)
├─ herramientas/          ← utilidades sueltas (actualizar Claude Code, sincronizar skills)
├─ logs/                  ← voz.log (fuente del chat en vivo), telegram.log, webhook.log, tunel.log
├─ resultados/            ← salida de cada transcripción (audio, frames, texto). NO versionado
└─ graphify-out/          ← grafo de conocimiento generado con /graphify. NO versionado
```

### Cómo se lanza cada cosa

Los módulos son un paquete de Python, así que **se lanzan con `-m` desde la raíz del
proyecto** (nunca por ruta al `.py`, porque entonces Python no encuentra el paquete `app`):

```
python -m app.voz.voz                  ← el asistente de voz
python -m app.ingesta.bot_telegram     ← el bot de Telegram
python -m uvicorn app.ingesta.webhook_wasender:app --host 0.0.0.0 --port 8080
python -m app.nucleo.transcribir "archivo.ogg" [--analizar]
```

`panel.py` ya los lanza así (con `cwd` en la raíz), y los `.bat` de `lanzadores/` también.
Si agregás un servicio al panel, acordate de que `"match"` en el dict `SERVICIOS` es el
texto con el que identifica al proceso: tiene que ser el nombre del módulo.

### ⭐ `app/rutas.py`: las rutas van todas acá

Antes cada módulo buscaba sus archivos con `Path(__file__).with_name("config_dictado.json")`,
o sea **al lado de sí mismo**. Funcionaba con todo suelto en la raíz, pero se rompía en
silencio en cuanto el módulo cambiaba de carpeta. Ahora hay una sola fuente de verdad:

```python
from app.rutas import RAIZ, ENV, CONFIG_DICTADO, MUSICA_ESPERA, LOGS, RESULTADOS
```

`rutas.py` vive siempre en `app/`, así que sabe dónde está la raíz. **Si necesitás una ruta
nueva, agregala ahí y no la escribas a mano en otro módulo.** Así los archivos se pueden
mover de carpeta sin romper nada.

**Control de versiones**: el proyecto tiene git desde 2026-08-10. `.env`, `resultados/`,
`logs/` y `claude_sesion.json` están fuera por `.gitignore` (claves y datos de terceros).
Ya no hace falta guardar `.bak` a mano.

## Archivos principales

| Archivo | Rol |
|---|---|
| `app/rutas.py` | Las rutas del proyecto, en un solo lugar |
| `app/voz/voz.py` | Asistente completo: wake, dictado, comandos, watchdog del micro |
| `app/voz/claude_voz.py` | Puente con Claude Code (proceso persistente, sesión, interrupción) |
| `app/voz/cerebro.py` / `app/voz/acciones.py` | Intención → acción local (abrir apps, escritorios, ventanas) |
| `app/web/navegador.py` / `app/web/agente_web.py` | Control del navegador por voz (browser-use) |
| `panel.py` | Panel web 8750 + medidor de micro + chat en vivo |
| `app/ingesta/webhook_wasender.py` | WhatsApp + página `/subir` para audios largos |
| `app/ingesta/bot_telegram.py` | Bot de Telegram |
| `app/nucleo/` | Pipeline: `core.py`, `transcribir.py`, `procesar.py`, `analizar_gemini.py` |
| `config_dictado.json` | Micrófono elegido |
| `claude_sesion.json` | Sesión persistente de Laura |
| `.env` | Claves (Telegram, Wasender, Gemini). **No commitear** |
| `logs/` | `voz.log` (fuente del chat en vivo del panel), `telegram.log`, `webhook.log`, `tunel.log` |

## Pendientes

- Voz más natural para Piper (TTS) — pendiente viejo.
- Timers/recordatorios por voz (Etapa 3 del roadmap).
- Probar la página `/subir` con un audio real de 1 hora.
- Revisar si `escucha.py` (wake words con **Porcupine/Picovoice**) sigue en uso: `voz.py` hace el wake con Whisper `tiny` en CPU. Parecen dos caminos paralelos para lo mismo y uno puede estar muerto.
- Que funcione sin placa NVIDIA: hoy Whisper está fijo en `cuda` (`app/nucleo/core.py`).
- Que el nombre con el que Laura te saluda y las carpetas que puede tocar se configuren desde el `.env`.

## Roadmap

Etapa 2: sistema/ventanas/archivos ✓ (parcial) · Etapa 3: productividad (timers/recordatorios) · Etapa 4: navegador avanzado · Etapa 5: manos libres (wake word) ✓ · Etapa 6: integraciones (Kommo/n8n/Calendar) · Etapa 7: modo autónomo con frenos.

## Licencia

GPL-3.0: podés usar, estudiar, modificar y compartir este proyecto. Si distribuís una versión
modificada, tiene que ser abierta también y con la misma licencia. El texto completo está en
[`LICENSE`](LICENSE).
