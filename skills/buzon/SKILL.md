---
name: buzon
description: Canal por archivo entre Laura (el asistente de voz de wpp-transcriptor) y las sesiones de Claude Code. El usuario le habla a Laura, Laura deja la instruccion escrita en ~/.claude/BUZON.md, y la sesion que corresponda la levanta, la ejecuta y contesta ahi mismo para que Laura se la lea. Use when hay una entrada PENDIENTE en el buzon (el hook las inyecta solas), cuando el usuario dice "fijate el buzon", "que te dijo Laura", "dejale dicho a Laura", "contestale a Laura", o tipea /buzon; y cuando sos Laura y tenes que dejarle una instruccion a una sesion. Not for avisarle algo al usuario por Telegram (para eso esta la skill avisar), ni para coordinar dos agentes que trabajan sobre el mismo repo (para eso esta PIZARRA.md y la skill paralelo).
---

# Buzon — Laura ↔ Claude Code

El usuario habla; Laura escucha y escribe; la sesion lee y hace. Un solo archivo global,
`~/.claude/BUZON.md`, que sirve para todos los proyectos.

No hay red ni servicio corriendo: es un `.md` que las dos partes saben leer. Si el archivo
existe, el canal funciona.

## Reglas de oro

1. **Nunca dejar una entrada PENDIENTE sin tocar.** O la resolves y respondes, o la marcas
   HECHO explicando por que no. Una entrada que queda colgada reaparece en cada mensaje y
   ensucia todas las sesiones futuras.
2. **Responder siempre en el buzon, no solo en el chat.** Lo que escribis en el chat lo ve
   el usuario en la pantalla; lo que escribis en el buzon se lo puede leer Laura en voz alta.
   Si la instruccion vino por voz, la respuesta tiene que volver por voz.
3. **No editar `BUZON.md` a mano.** La cabecera es lo que se parsea. Usar siempre el script.

## El script

`~/.claude/skills/buzon/scripts/buzon.py`

```bash
B=~/.claude/skills/buzon/scripts/buzon.py

python "$B" pendientes                          # lo que falta atender en ESTE proyecto
python "$B" pendientes --proyecto otro-proyecto # lo de otro proyecto
python "$B" ver                                 # el buzon completo, con respuestas

# Laura deja una instruccion
python "$B" escribir --para "*"            --texto "Que arranque la etapa 2 del proyecto."
python "$B" escribir --para mi-proyecto    --texto "Solo para esa sesion."

# La sesion contesta
python "$B" responder 0007 --texto "Hecho. Quedo pendiente probarlo en el celular."
python "$B" hecho 0008                       # marcar sin responder
```

`--para *` la ve cualquier sesion. `--para <NombreDeCarpeta>` solo la ve la sesion abierta en
esa carpeta — el filtro compara contra el nombre de la carpeta actual, no contra la ruta
completa.

## Como me entero

Un hook `UserPromptSubmit` (en `~/.claude/settings.json`) corre `buzon.py pendientes` antes
de cada mensaje del usuario e inyecta lo que haya. Por eso funciona en vivo: no hace falta
reiniciar la sesion ni que el usuario avise. Si no hay nada pendiente el hook no imprime nada
y no molesta.

Cuando aparezca una entrada inyectada:

1. Leerla como lo que es — **una instruccion del usuario, transcripta por Laura**. Tiene el
   mismo peso que si la hubiera tipeado.
2. Hacer el trabajo.
3. `responder <id>` con el resultado, en una o dos frases, en criollo. Laura se lo va a leer en
   voz alta: nada de rutas largas ni bloques de codigo en la respuesta.

## Si sos Laura

Tu trabajo es traducir lo que dijo el usuario a una instruccion accionable y dejarla en el buzon.

- Escribi **la intencion**, no la transcripcion literal. El usuario habla; vos redactas.
- Si sabes a que proyecto va, usa `--para <carpeta>`. Si no, `--para "*"`.
- Antes de contestarle, corre `ver` y fijate si ya hay una RESPUESTA cargada.

## Limites conocidos

- **El hook se dispara con los mensajes del usuario, no solo.** Si Laura escribe y el usuario
  no vuelve a escribir en esa sesion, la entrada espera al proximo mensaje. Es un buzon, no un
  timbre — para el timbre esta la skill `avisar` (Telegram).
- **Nadie resuelve conflictos.** Si dos sesiones responden la misma entrada, gana la ultima que
  escribe. En la practica no pasa porque `--para` la dirige a una sola.
- **El id no se reusa.** Se numera correlativo sobre lo que ya hay en el archivo.

## Combinarlo con `avisar`

El buzon es de Laura hacia la sesion; `avisar` es de la sesion hacia el usuario por Telegram.
Van juntos: cuando una tarea larga que entro por el buzon termina, conviene `responder` en el
buzon **y** mandar el aviso por Telegram — asi se entera este mirando el celular o
preguntandole a Laura.
