---
name: avisar
description: Mandarle un mensaje al usuario al celular desde cualquier proyecto, por Telegram o por WhatsApp — para avisarle que algo terminó, que algo se rompió, o para hacerle una pregunta cuando no está mirando la pantalla. Use when el usuario dice "avisame", "avisame por Telegram", "avisame por WhatsApp", "hablá conmigo", "comunicate conmigo", "mandame un mensaje", "decime cuando termines", "tocame el timbre", o tipea /avisar; y también cuando una tarea larga que él pidió termina o falla y ya se fue de la pantalla. Not for leer o responder mensajes (esta skill NO lee por ningún canal: el bot de wpp-transcriptor hace polling con el mismo token de Telegram y se rompería), ni para escribirle a otra persona que no sea el usuario.
version: 1.7.0
---

# Avisar — tocarle el timbre al usuario (Telegram o WhatsApp)

> Vive en `~/.claude/skills/`, así que está disponible en **todos los proyectos**.
> Sirve para lo mismo que un mensaje a un compañero: "terminé", "se rompió esto",
> "necesito que decidas algo". Le llega al celular aunque no esté frente a la PC.

## ⛔ Reglas de oro (leer SIEMPRE antes de usarla)

1. **SOLO ENVIAR. NUNCA LEER, por ningún canal.** Nada de `getUpdates`,
   `setWebhook` ni `deleteWebhook`. El bot de `wpp-transcriptor` hace
   long-polling con **el mismo token** de Telegram: si esta skill lee, le roba los
   mensajes y se caen la transcripción y la Laura de Telegram, sin ningún error
   visible.
   *Lo que NO se hace:* `curl .../getUpdates`.
   *Lo que sí:* `avisar.py "texto"`, y si querés respuesta, pedísela en el chat de Claude.

2. **Las credenciales no se escriben nunca en un comando ni en un repo.** Viven en
   `~/.claude/telegram.json` y `~/.claude/whatsapp.json`, fuera de todo proyecto,
   y solo las lee el script.
   *Lo que NO se hace:* `curl -X POST https://api.telegram.org/bot8825.../sendMessage`.

3. **Un aviso es una interrupción en el celular de una persona.** Se usa cuando de
   verdad vale: terminó algo largo, se rompió algo, hace falta una decisión suya.
   No para narrar el avance paso a paso ni para confirmar cosas triviales.

4. **Decí siempre qué pasó, no solo que pasó algo.** "Listo" no sirve leído en el
   colectivo. "Terminé el refactor de acciones.py: 40/40 tests OK, falta reiniciar
   la voz" sí.

## Configuración (una sola vez)

`~/.claude/telegram.json` (para el canal por defecto):

```json
{"token": "el token de tu bot de @BotFather", "chat_id": "tu id de Telegram", "nombre": "tu nombre"}
```

`~/.claude/whatsapp.json` (opcional, necesita una instancia de Evolution API):

```json
{"url": "https://tu-evolution/", "apikey": "...", "instancia": "...", "numero": "549..."}
```

Para que además deje registro en el cuaderno de Obsidian, una variable de entorno con la
carpeta del cuaderno: `setx CUADERNO_NOTAS "C:\IA\notas"` (y reabrir la terminal). Sin
eso, el aviso sale igual y simplemente no se anota.

## Cómo se usa

```bash
python ~/.claude/skills/avisar/scripts/avisar.py "el texto del aviso"          # Telegram (por defecto)
python ~/.claude/skills/avisar/scripts/avisar.py --por whatsapp "el texto"     # WhatsApp (Evolution API)
python ~/.claude/skills/avisar/scripts/avisar.py --por ambos "algo importante" # los dos canales
python ~/.claude/skills/avisar/scripts/avisar.py --archivo salida.txt          # textos largos o con comillas
python ~/.claude/skills/avisar/scripts/avisar.py --proyecto mi-proyecto "Listo"
python ~/.claude/skills/avisar/scripts/avisar.py --hablar "Se cayó el bot"
python ~/.claude/skills/avisar/scripts/avisar.py --adjuntar informe.pdf "Te mando el informe"
```

- **`--categoria`** (`tarea` / `produccion` / `decision` / `general` / `error`, por defecto
  `general`): además de mandar el mensaje, deja una línea anotada en el cuaderno de
  Obsidian (la carpeta de `CUADERNO_NOTAS`), en una nota distinta por categoría. Sirve
  para ponerse al día leyendo esas notas cuando se perdió el hilo de lo que hicieron otras
  sesiones. `error` se agrupa por proyecto. Best-effort: si el cuaderno no está, el aviso
  sale igual.
- **`--solo-obsidian`**: anota en el cuaderno sin mandar nada al celular.
- **`--hablar`**: además de mandarlo al celular, **Laura lo dice en voz alta**. Deja
  el aviso en `~/.claude/avisos_hablados.jsonl` y `voz.py` (wpp-transcriptor) lo lee
  cuando hay un hueco de verdad — no pisa una charla, y no habla si se pausó la escucha.
  Es para lo que conviene saber **en el momento**, no para cada tarea que termina. Nunca
  reemplaza al mensaje al celular: si la voz está apagada, ahí no lo escucha nadie. Los
  avisos de más de una hora se descartan.
- **Telegram es el canal por defecto.** WhatsApp va cuando el usuario lo pide, o cuando
  el aviso es de esos que no puede perderse.
- **Si el canal elegido falla, se prueba solo con el otro** y el mensaje aclara
  "no pude por telegram". Un aviso que no llega es peor que uno por el otro canal.
- El **nombre del proyecto** sale solo de la carpeta actual y va como encabezado.
  Con 2-3 agentes a la vez, sin eso no se sabe cuál de todos está hablando.
- Los textos de más de 3900 caracteres se parten solos en varios mensajes.
- El script **imprime por dónde salió** cuando anduvo; si no, muere con el error.
  No hay "se mandó" silencioso.

## Que el PROYECTO avise solo, sin ninguna sesión de Claude abierta

Si algo se cae de madrugada, conviene enterarse. Para eso está `vigilar.py`, **listo
para usar en cualquier proyecto** — no hay que programar un watchdog nuevo cada vez.

1. Dejá un `vigilar.json` en la raíz del proyecto:

```json
{
  "proyecto": "mi-proyecto",
  "canal": "telegram",
  "fallos_seguidos": 2,
  "chequeos": [
    {"nombre": "Mi API",          "url": "https://ejemplo.com/health"},
    {"nombre": "Bot de Telegram", "proceso": "app.ingesta.bot_telegram"},
    {"nombre": "Algo en un VPS",  "comando": "ssh vps 'docker ps --format {{.Names}} | grep -q n8n'"}
  ]
}
```

2. Probalo sin molestar a nadie: `vigilar.py --config vigilar.json --probar --una-vez`
3. Dejalo corriendo, de una de las dos formas:
   - **Programador de tareas de Windows / cron**: `--una-vez` cada 5 minutos.
   - **Dentro de un servicio que ya corre**: un hilo con `--cada 60`, o llamando a
     `una_vuelta()` desde el código.

Tres tipos de chequeo: `url` (responde con código < 400), `proceso` (hay un proceso
vivo con ese texto en su línea de comando) y `comando` (termina con código 0) — con
`comando` se puede mirar cualquier cosa: docker, ssh, una consulta a la base, un archivo.

⚠ Si lo que vigilás es **el propio canal de aviso** (por ejemplo, la instancia de WhatsApp
por la que salen los avisos), poné `"canal": "telegram"`: si no, el aviso de que se cayó
WhatsApp viaja por el cable cortado y no llega nunca.

**Las reglas anti-ruido ya vienen puestas** (no las reinventes en cada proyecto):
avisa solo cuando algo pasa de andar a no andar y cuando vuelve; no repite hasta que
se recupere; y aguanta `fallos_seguidos` chequeos antes de gritar, porque un hipo de
red no es una caída y un aviso falso te enseña a ignorar los avisos. El estado se
guarda al lado del config, así el modo `--una-vez` desde un cron recuerda la corrida
anterior.

## Cuándo conviene usarla sin que te la pidan

Si el usuario pidió que le avises, **avisá sin preguntar** cuando:

- terminó una tarea larga que él pidió y ya no está mirando la pantalla;
- algo se rompió en producción (un bot, un servicio caído);
- estás bloqueado esperando una decisión suya y no se puede seguir sin eso.

En cambio **no avises** por cada paso de una tarea en curso: eso va en el chat.

## Lo que esta skill NO puede hacer (y qué hacer en su lugar)

- **No puede leer la respuesta.** Si el usuario le contesta al bot en Telegram, ese
  mensaje va a la Laura de `wpp-transcriptor`, no al agente que escribió. Para
  contestarle a este agente, hay que volver al chat de Claude Code.
- **No le escribe a otra persona.** El destino de los dos canales es el usuario, a
  propósito: el `chat_id` de Telegram y el `numero` de WhatsApp están fijos en la
  config. Para escribirle a un cliente está el bot del proyecto, no esta skill.

## Supuestos verificables

| Supuesto | Cómo se verifica | Si cambió |
|---|---|---|
| El bot de wpp-transcriptor usa el mismo token | comparar `token` de `~/.claude/telegram.json` con `TELEGRAM_TOKEN` del `.env` del proyecto | si fueran distintos, la regla de oro 1 se relaja (pero seguiría sin leer) |
| Un antivirus o proxy puede romper el SSL de Python | el script cae solo a `curl` si urllib falla | si no pasa, el fallback simplemente no se usa |
| La instancia de Evolution está conectada | `GET {url}/instance/fetchInstances` con la apikey → `connectionStatus: open` | si está cerrada, WhatsApp falla y el aviso sale por Telegram; hay que re-escanear el QR |

## Auto-mejora

Esta skill se corrige a sí misma. Seguí el protocolo de
[_molde-automejora.md](../_molde-automejora.md):

- **Si algo rompió, un paso falló, apareció una capacidad nueva o un supuesto resultó falso**
  → escribí la lección en [LECCIONES.md](LECCIONES.md) (síntoma · causa · regla · evidencia ·
  vigencia). Si es crítica, subí la regla a "Reglas de oro" acá arriba, con ejemplo.
- **Con evidencia dura, actualizá sola y avisá en una línea.** Sin evidencia, proponé primero.
- Al terminar: subí `version` y agregá la línea al changelog.
- No dupliques reglas: afiná la existente. No dejes el paso viejo al lado del nuevo.

## Changelog

- **1.7.0** (2026-09-24) — Versión para compartir: la carpeta del cuaderno sale de la
  variable `CUADERNO_NOTAS` en vez de una ruta fija, y se sacó el envío a un grupo de
  WhatsApp, que era de un equipo en particular.
- **1.5.0** (2026-08-13) — `--hablar`: el aviso además se le pasa a **Laura para
  que lo diga en voz alta**, por un buzón de una línea JSON en
  `~/.claude/avisos_hablados.jsonl`.
- **1.4.0** (2026-08-13) — Categoría `error`, agrupada por proyecto en el cuaderno, y
  `--solo-obsidian`.
- **1.3.0** (2026-08-13) — `--categoria`: además del aviso, deja registro en una nota
  del cuaderno por categoría.
- **1.2.0** (2026-08-12) — `vigilar.py`: watchdog **genérico y reusable** para que el
  proyecto avise solo, sin sesión de Claude abierta. Probado con un ciclo completo:
  4 chequeos con el servicio caído dieron **1 solo aviso**, y la recuperación avisó una vez.
- **1.1.0** (2026-08-12) — Canal de **WhatsApp** por Evolution API, `--por ambos` y
  respaldo automático entre canales.
- **1.0.0** (2026-08-12) — Primera versión. La regla de oro 1 (nunca leer) sale de un
  choque real conocido: dos procesos haciendo `getUpdates` con el mismo token se
  roban los mensajes entre sí.
