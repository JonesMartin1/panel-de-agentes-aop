---
name: pizarra
description: Escribir en el pizarron visual del usuario — el tablero blanco con papelitos que se ve en el panel del Servidor IA (http://127.0.0.1:8750/pizarra), el mismo que Laura llena por voz. Use when el usuario dice "anota esto en la pizarra", "escribi en la pizarra tal cosa", "poneme eso en el pizarron", "dejamelo en la pizarra", o tipea /pizarra. NOT for el archivo PIZARRA.md de un repo (eso es coordinacion entre agentes, otra cosa distinta con nombre parecido), ni para el cuaderno de Obsidian (skill notas), ni para avisarle al celular (skill avisar).
version: 1.0.0
---

# Pizarra — dejar una nota en el pizarron del panel

> Vive en `~/.claude/skills/`, asi que sirve desde **cualquier proyecto**.

## Lo primero: cual pizarra

Hay dos cosas con el mismo nombre y **se confunden todo el tiempo**:

| Si el usuario dice… | Es… | Que se hace |
|---|---|---|
| "anotalo en la pizarra", "escribi en la pizarra" | el **pizarron visual** del panel | esta skill |
| "anotalo en la PIZARRA del repo", "dejalo en la pizarra para el otro agente" | el archivo `PIZARRA.md` del proyecto | editar ese `.md` (skill `paralelo`) |

⭐ **Por defecto, "la pizarra" es la visual**: es la que el usuario tiene abierta en la
pantalla. `PIZARRA.md` es un archivo de coordinacion entre agentes.
Si de verdad hay duda, preguntar en una linea antes de escribir en el lugar equivocado.

## Como se usa

```bash
python ~/.claude/skills/pizarra/scripts/pizarra.py "lo que hay que anotar"
python ~/.claude/skills/pizarra/scripts/pizarra.py "Falta probar el webhook" --de mi-proyecto
python ~/.claude/skills/pizarra/scripts/pizarra.py "IDEAS" --tipo texto
python ~/.claude/skills/pizarra/scripts/pizarra.py --listar
python ~/.claude/skills/pizarra/scripts/pizarra.py --borrar 12
```

- `--tipo nota` (por defecto) es un papelito de color; `--tipo texto` es texto suelto, para titulos.
- `--de` pone quien la escribio en la primera linea. **Usalo siempre que la nota
  salga de un proyecto que no sea obvio**: en el pizarron se mezclan las de todos.
- `--color "#a0d8ef"` si querés uno fijo; sin eso va rotando solo.
- `--x` y `--y` son 0 a 100 (porcentaje del tablero). Casi nunca hace falta: se acomodan solas.
- `--listar` antes de `--borrar`, para saber que numero tiene cada una.

## Reglas

1. **Corto.** Es un papelito en un tablero, no un informe: un par de renglones.
   Si la explicacion es larga, va en el chat y en la pizarra queda el titular.
2. **No borrar lo que no pusiste vos** salvo que el usuario lo pida. El pizarron es suyo
   y tiene cosas puestas a mano y por Laura.
3. Solo anda **en la maquina donde corre el panel de wpp-transcriptor, y con el panel
   prendido**. Si el panel esta apagado el script lo dice y no rompe nada: contarselo,
   no reintentar en loop.
4. No es un canal para avisar: **nadie mira el pizarron todo el tiempo**. Si es algo
   urgente, ademas mandar un aviso al celular con la skill `avisar`.
