---
name: notas
description: 'Repasa la sesion actual (la charla y, si existen, PIZARRA.md/PLAN.md del proyecto) y deja al dia la nota del proyecto en el cuaderno de Obsidian del usuario: bugs, decisiones, funciones nuevas y pendientes. Use when el usuario dice "anota esto en el cuaderno", "actualiza Obsidian", "repasa y anota lo importante", "dejalo en las notas", "guardalo en el cuaderno", o tipea /notas; tambien como catch-up cuando paso mucho en una sesion larga y nadie fue anotando en el camino. Not for estado efimero sin valor a futuro, ni para duplicar el detalle tecnico que ya vive en el repo (README, PIZARRA, PLAN) - la nota resume y apunta, no copia.'
---

# Notas - repasar y dejar al dia el cuaderno de Obsidian

Version a pedido de la regla "cuaderno de notas" del CLAUDE.md global del usuario:
mismas reglas, pero disparada cuando se pide en vez de depender de que la sesion se de
cuenta sola en el momento justo. Util sobre todo para ponerse al dia despues de una
sesion larga o desordenada donde nadie fue anotando en el camino.

## Antes que nada: donde esta el cuaderno

La ruta del cuaderno esta en el CLAUDE.md global del usuario (`~/.claude/CLAUDE.md`),
en la seccion "Cuaderno de notas (Obsidian)". Si no esta escrita ahi, preguntarsela y
sugerirle agregarla (ver el paso 11 del README de wpp-transcriptor).

Intentar leer `Convenciones.md` adentro del cuaderno. Si da error de permiso, esta
sesion se abrio sin acceso al cuaderno: avisarle al usuario que tiene que abrir la
sesion con acceso a esa carpeta, y no seguir. No intentar esquivar los permisos ni
copiar el cuaderno a otro lugar.

## Proceso

1. Leer Convenciones.md (reglas de formato) y Proyectos.md (para ver si el proyecto
   actual ya tiene nota propia y como se llama).
2. Juntar lo que paso: repasar la conversacion de esta sesion y, si existen,
   PIZARRA.md y PLAN.md/CONTEXTO.md del proyecto. No hace falta leer el codigo: la
   nota es para que la lea una persona, no duplica el detalle tecnico que ya vive en
   el repo.
3. Separar en estas categorias:
   - Funciones nuevas o algo que se termino/publico: prosa en la nota del proyecto,
     con la fecha del estado.
   - Decisiones y cambios de estado: prosa, con fecha y el motivo si se sabe.
   - Pendientes que importan: prosa breve, sin inventar urgencia si no la hay.
   - Bugs: seccion "## Bugs" al final de la nota del proyecto, nunca mezclados con el
     relato. Una vineta por bug: fecha, estado (abierto o arreglado el AAAA-MM-DD), y
     que se ve; despues la causa si se sabe (si no, decir "sin diagnosticar").
4. Si el proyecto no tiene nota todavia, crearla y enlazarla desde Proyectos.md.
5. Actualizar la nota existente en vez de crear una nueva cuando ya hay una. Prosa
   corta para humanos, fechas absolutas (nunca "ayer"), enlaces [[dobles corchetes]]
   solo cuando afirman una relacion real (mismo cliente, mismo proyecto del que
   depende): que dos proyectos hayan compartido codigo no los enlaza.
6. Refrescar el dato `actualizado:` del encabezado de la nota con la fecha de hoy.
7. Nada de secretos, tokens ni datos de clientes en el cuaderno.
8. Al terminar, decirle al usuario en una frase que se anoto. Si la sesion es por voz,
   corto y sin rutas de archivo ni bloques de codigo.

## Que NO hacer

- No volcar la charla entera ni pegar logs: resumir.
- No repetir lo que ya esta en el README/PIZARRA/PLAN del repo: la nota apunta a eso,
  no lo copia.
- No inventar pendientes o urgencia que no salieron de la sesion, para no ensuciar la
  nota con relleno.
