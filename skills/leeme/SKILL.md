---
name: leeme
description: Ponerle voz a un artefacto — un reproductor arriba del informe con tres acentos (argentino, mexicano, colombiano) que cuenta la idea en 2-4 minutos, con el audio embebido en la propia página. Use when se publica un artefacto de informe, plan, propuesta, diagnóstico o resumen para el usuario, o cuando pide "leeme esto", "léeme el informe", "que se pueda escuchar", "ponele voz". Not for artefactos que son una herramienta interactiva (un maquetador, una calculadora, una réplica de pantalla), donde no hay nada que narrar.
version: 1.0.1
---

# Léeme — artefactos que se escuchan

> Vive en `~/.claude/skills/`, así que está disponible en **todos los proyectos**,
> no en uno solo. El script se llama por ruta absoluta y escribe sus temporales
> en el temp del sistema: se puede correr parado en cualquier repo sin dejarle
> nada.

Un artefacto narrado se **lee igual que cualquier otro**, pero arriba trae un
reproductor: elegís el acento, das play, y una voz cuenta la idea en 2-4 minutos.
Sirve para leer el informe manejando, o para pasárselo a alguien del equipo sin
tener que explicárselo.

## Cómo se usa

Escribí el artefacto como siempre. Antes de publicarlo:

```bash
python ~/.claude/skills/leeme/scripts/narrar.py \
  --html mi-informe.html --guion guion.txt
```

Eso genera el audio con las tres voces, lo mete en el HTML y agrega el
reproductor después del encabezado. Recién ahí llamás a `Artifact`.

Es idempotente: si corregís el guión y lo volvés a correr, reemplaza la
narración anterior en vez de apilar otra.

## El guión es lo que importa

**El guión NO es el artefacto leído en voz alta.** Si transcribís la página, sale
un audio que nadie escucha hasta el final. Escribilo como se lo contarías al
usuario por teléfono:

- **Arrancá por la conclusión**, no por el método. "El bot le pedía el nombre
  tres veces a la misma persona" gana a "analizamos las ejecuciones del
  workflow".
- **Frases cortas.** Lo que en un texto es una coma, hablando es un punto.
- **Nada de listas ni tablas**: un número suelto se recuerda, seis no. Los datos
  finos que queden en la página, que para eso está.
- **Sin markdown, sin emojis, sin viñetas.** Se leen literalmente y suenan mal.
- **Los números, como se pronuncian**: "nueve mil ciento treinta y tres
  renglones", no "9.133". Y "$ 140.000" decilo "ciento cuarenta mil pesos".
- **Terminá con lo que sigue**, o con lo que necesitás del otro.

Largo: **350 a 550 palabras** (2,5 a 4 minutos). Es el punto donde entra la idea
completa sin que se haga largo.

## Presupuesto de peso

El audio va **embebido** en la página, no por URL: el artefacto publicado bloquea
los pedidos a otro host, así que un `<audio src="https://...">` no sonaría. Eso
tiene un costo en bytes:

| Guión | Peso con las 3 voces |
|---|---|
| 100 palabras | ~0,8 MB |
| 400 palabras | ~3,5 MB |
| 900 palabras | ~8 MB |

El tope del artefacto es **16 MB**. El script avisa si el guión se pasa de 900
palabras y muestra el peso final. Si necesitás más, sacá voces: cada una es un
tercio del audio.

## Las voces

| Botón | Voz | Acento |
|---|---|---|
| Elena | `es-AR-ElenaNeural` | argentino (la que arranca) |
| Dalia | `es-MX-DaliaNeural` | mexicano |
| Salomé | `es-CO-SalomeNeural` | colombiano |

Son voces neuronales de Microsoft vía `edge-tts`: gratis, sin API key y sin
cuenta. La velocidad va en `+6%` porque a velocidad normal suenan lentas para un
informe; se cambia con `--rate`.

## Requisitos

```bash
pip install edge-tts truststore
```

`truststore` hace falta en máquinas donde un antivirus o un proxy corporativo mete
su propio certificado: sin eso `edge-tts` corta con `CERTIFICATE_VERIFY_FAILED` al
conectarse a Microsoft. El script lo activa solo si está instalado.

## Detalles del reproductor

- Las clases van prefijadas `nrr-` para no pisar el CSS del artefacto.
- Los colores salen de las variables del artefacto (`--brand`, `--panel`,
  `--ink`…) cuando existen, con un fallback propio. Así hereda el tema y se ve
  bien en claro y en oscuro sin tocar nada.
- `preload="none"`: la página abre rápido y el audio recién se baja al dar play.
- Se inserta después de `</header>`; si no hay, después del `</h1>`; si tampoco,
  arriba de todo.

## Cuándo NO usarla

Si el artefacto es una **herramienta** —un maquetador, una réplica de pantalla
para probar, una calculadora— no tiene sentido: el usuario va a tocar, no a
escuchar. La narración es para informes, planes, diagnósticos y propuestas.
