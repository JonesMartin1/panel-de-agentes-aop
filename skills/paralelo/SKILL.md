---
name: paralelo
description: Preparar ("estampar") un proyecto para que varios agentes de Claude trabajen en simultáneo sin pisarse — crea .worktreeinclude, PIZARRA.md, la sección "Trabajo en paralelo" en el CLAUDE.md del proyecto y la línea de .gitignore, con un mapa de dueños que el usuario confirma. Use when el usuario tipea /paralelo, pide "prepará este proyecto para multiagente", "quiero varios agentes acá", "estampá el proyecto", o va a arrancar un segundo agente en un proyecto que no tiene PIZARRA.md. Not for repartir u orquestar tareas en un proyecto ya estampado (eso se hace a mano leyendo PIZARRA.md), ni para proyectos sin git (ofrecer `git init` primero).
version: 1.1.0
---

# Paralelo — estampar un proyecto para trabajo multiagente

> Vive en `~/.claude/skills/`, así que está disponible en **todos los proyectos**.
> "Estampar" = dejar el proyecto listo para que 2-3 sesiones de Claude convivan
> sin pisarse. Se corre una vez por proyecto; después la coordinación diaria es
> leer y actualizar `PIZARRA.md`.

## Las reglas universales (valen en todo proyecto, estampado o no)

1. **Techo: 2-3 agentes a la vez EN TODA LA MÁQUINA**, no por proyecto. La GPU,
   la cuota de tokens y la atención del usuario son globales aunque los repos no.
2. **Un solo "dueño de la máquina" por proyecto**: la única sesión que puede
   reiniciar servicios, usar puertos/GPU/micrófono/base de datos, publicar en
   caliente (n8n) o hacer polling con tokens únicos (Telegram). Los demás
   agentes no tocan nada de eso — ni "solo un segundo".
3. **El segundo agente nace en worktree** (`claude -w nombre-tarea`) con una
   **spec de 5 líneas** escrita antes: qué hace, qué archivos toca, qué NO toca.
   Sin spec no se larga: el reparto por carpetas no alcanza, los choques son en
   las interfaces.
4. **El worktree muere el mismo día**: tarea chica → merge → borrar. Las ramas
   paralelas que envejecen terminan en conflictos que cuestan más de lo que
   ahorraron ("drift and rot").
5. **Pizarra**: si existe `PIZARRA.md`, leerla al arrancar; anotar qué se toma
   antes de tocar nada; al terminar, mover a Hecho y dejar lo aprendido.
6. **El orquestador es el usuario**: disparo manual, nada de orquestación automática
   ni agent teams (7× tokens y la evidencia no los banca para proyectos de una
   persona). El panel para ver todo es `claude agents`.

## Cómo se cierra una tarea (el formato de reporte)

Cuando un agente termina —o se traba— informa en este formato, no en prosa suelta:

```
DECISIÓN:      qué se hizo o qué se propone, en una línea.
POR QUÉ:       la razón, no el procedimiento.
EVIDENCIA:     cada afirmación marcada CONFIRMADO / DEDUCIDO / NO SÉ.
FALTA:         lo que no se pudo verificar, y por qué no.
PRÓXIMO PASO:  el comando exacto que sigue, copiable.
CUÁNDO PARAR:  la condición que dice "esto ya está" o "esto no va más".
```

El renglón que hace el trabajo es **EVIDENCIA**. Obliga a separar lo que se
verificó de lo que se supuso, que es donde se pierden las horas.

> Pasó el 2026-08-24 en `wpp-transcriptor`: un plan arrancó con dos supuestos que
> sonaban obvios y los dos eran falsos (el "avisame cuando termine" ya existía, y
> `notify_when_idle` no servía para lo que se quería). Se descubrió recién
> trabajando. Con el renglón EVIDENCIA los dos habrían salido marcados DEDUCIDO
> desde el principio, que es la señal de "andá a verificar esto".

`NO SÉ` es una respuesta válida y barata. Un `CONFIRMADO` que era `DEDUCIDO`
cuesta una tarde.

## El ledger: qué costó cada tarea

Un `docs/LEDGER.md` **de solo agregar**, una línea por tarea que valga la pena
recordar:

```
| fecha | quién (modelo) | qué | cómo salió | costo |
```

- **quién**: el modelo (`Opus`, `Codex`…), o el nombre del usuario si fue a mano.
- **qué**: lo que se pidió, en una frase. No el archivo que se tocó.
- **cómo salió**: `hecho`, `hecho a medias`, `abandonado`, `salió al revés`.
- **costo**: lo que diga el panel al terminar. Si no se miró, va `sin medir` —
  es información honesta y muestra cuánto no se está midiendo.

Nunca se edita ni se borra una línea vieja: si algo salió mal y después se
arregló, se agrega una línea nueva abajo. Se anota **al cerrar la tarea**, junto
con el borrado de la entrada de la pizarra.

Existe porque sin esto "esa función salió cara" es una sensación y no un dato:
la pizarra se borra al terminar, el historial guarda las decisiones pero no el
gasto, y los contadores de tokens son del día, no de la tarea. Una tarea de
cinco minutos no va acá.

## El cementerio de rutas muertas

Una sección al final del historial de la pizarra con **lo que se probó y NO
anduvo**. Es distinta del historial normal, que archiva lo que sí funcionó.

Cada entrada: qué se intentó, qué pasó exactamente (el error textual), y el
estado — `probado` (no anda, con evidencia), `pendiente` (a medias, se puede
retomar) o `muerto` (no va a andar nunca, y por qué).

Sirve para que ningún agente vuelva a chocar contra la misma pared. El riesgo
real es que estos callejones quedan anotados **adentro de una entrada larga de
la pizarra**, y la pizarra se borra al terminar la tarea: el aprendizaje se va
con ella.

## El freno de mano (`STOP`)

Un archivo `STOP` en la raíz del repo hace que **no arranquen turnos nuevos** de
agente. Los que ya están corriendo siguen, y se paran con el botón de siempre.

Es *fail-closed*: si el archivo está, no arranca nada, aunque sea por error. Lo
que tiene adentro se muestra como motivo, así el que lo encuentra sabe quién lo
puso y por qué. Se saca borrando el archivo.

Tres reglas al implementarlo:

1. El chequeo va **donde arranca un turno**, no en el bucle principal ni en el
   `main`: tiene que atrapar todos los caminos de entrada.
2. **No toca lo que ya está corriendo.** Un freno que mata turnos en curso no es
   un freno, es un `kill`, y ya existe el botón para eso.
3. `STOP` va al `.gitignore`. Es estado local de esta máquina, no del repo.

Va con su prueba, que verifica las tres cosas: con `STOP` no arranca, sin `STOP`
arranca, y un turno en curso no se corta. La prueba tiene que dejar el archivo
`STOP` como lo encontró.

## Qué crea el estampado (4 piezas)

Antes de nada: verificar que hay git y **al menos un commit** (`claude -w` falla
sin commits). Si no hay git, ofrecer `git init` y frenar hasta que el usuario decida.

### 1. Línea en `.gitignore`

```
# --- Worktrees de Claude Code (sesiones paralelas) ---
.claude/worktrees/
```

### 2. `.worktreeinclude` en la raíz

Listar SOLO los archivos gitignorados que un worktree nuevo necesita para
**arrancar**: `.env`, tokens de API estáticos, configs con claves. Detectarlos
comparando `.gitignore` con lo que el código lee al iniciar.

**NO copiar estado vivo** (sesiones guardadas, flags, tokens que se refrescan
solos, bases sqlite en uso): de eso es dueño el checkout principal, y una copia
divergente causa bugs silenciosos.

```
# Archivos ignorados por git que un worktree nuevo necesita para arrancar.
# Solo claves/config estática — el estado vivo NO se copia.
.env
```

### 3. Sección "Trabajo en paralelo (multiagente)" en el CLAUDE.md del proyecto

Con el **mapa de dueños** ya confirmado (ver abajo). Plantilla:

```markdown
## Trabajo en paralelo (multiagente)

- Al arrancar, leé `PIZARRA.md` y anotá qué tarea tomás y qué zona tocás; al
  terminar, movela a Hecho y dejá lo aprendido en Lecciones.
- **Dueño de la máquina**: una sola sesión a la vez toca <zonas calientes>,
  reinicia servicios, o usa <recursos únicos>. Si no sos el dueño, no reiniciás
  nada.
- Lo que no necesita la máquina (<zonas frías: tests, docs, refactors>) va en
  worktree: `claude -w nombre-tarea`, spec de 5 líneas antes, merge y borrado el
  mismo día.
- Techo: 2 agentes en este proyecto (3 excepcional). El techo es de la máquina,
  no del repo.
```

### 4. `PIZARRA.md` en la raíz (versionada)

```markdown
# Pizarra — coordinación entre agentes

Cada sesión lee esto al arrancar. Antes de tocar nada, anotá tu tarea en
"En curso" (fecha · quién · qué · zona); al terminar, movela a "Hecho" y dejá
lo aprendido en "Lecciones". La escribe sobre todo quien lanza los agentes:
un agente en worktree ya nace con su tarea y no puede escribir en el checkout
principal.

## En curso

## Hecho

## Decisiones

## Lecciones
```

## Cómo armar el mapa de dueños (el único paso con criterio)

Es lo que NO se puede templatear. Para proponerlo:

1. Mirar `README.md`, `CLAUDE.md`, configs y los procesos corriendo
   (`Get-CimInstance Win32_Process` en Windows).
2. Identificar los **recursos únicos**: puertos, GPU, micrófono u otro hardware,
   bases de datos, tokens de API con polling, destinos de publicación en
   caliente, archivos de estado vivo.
3. Proponerle al usuario el mapa (zonas calientes + recursos → un dueño; zonas
   frías → worktrees) y **esperar su confirmación** antes de escribir la
   sección. AskUserQuestion va bien acá.

## Precauciones

- **No tocar servicios corriendo** durante el estampado: son 4 archivos de
  texto, cero reinicios.
- No commitear nada salvo que el usuario lo pida.
- Si el proyecto ya tiene una sección de paralelo o una PIZARRA.md, actualizar
  lo que falte en vez de duplicar.
- Explicar sin jerga, salvo que el usuario sea programador y prefiera el término técnico.
