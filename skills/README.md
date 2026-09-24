# Skills para Claude Code

Atajos que le enseñan a Claude a hacer tareas concretas de una manera fija. Se usan escribiendo
`/nombre` en Claude (por ejemplo `/notas`), o solas cuando Claude reconoce el pedido ("anotalo
en el cuaderno", "avisame cuando termines").

Son copias de las que usa Martín, adaptadas para que anden en cualquier máquina. Si él mejora
las suyas, las de acá no se actualizan solas: hay que volver a copiarlas.

| Skill | Qué hace | Necesita |
|---|---|---|
| `notas` | Repasa la sesión y deja al día la nota del proyecto en tu cuaderno de Obsidian | El cuaderno (paso 11 del README) |
| `avisar` | Te manda un mensaje al celular por Telegram o WhatsApp cuando algo termina o se rompe. Trae `vigilar.py`, que vigila servicios y avisa solo | Un bot de Telegram (ver abajo) |
| `buzon` | Lo que le decís a Laura por voz le llega a la sesión de Claude que corresponda | El hook de abajo |
| `pizarra` | Pega papelitos en el pizarrón del panel (`localhost:8750/pizarra`) | El panel prendido |
| `paralelo` | Prepara un proyecto para que trabajen 2-3 agentes a la vez sin pisarse | git |
| `grill-me` | Te interroga sobre un plan antes de ejecutarlo, para encontrarle los agujeros | Nada |
| `leeme` | Le pone voz a un informe: un reproductor con tres acentos arriba de la página | `pip install edge-tts truststore` |
| `3d` | Convierte una imagen en un modelo 3D y lo integra en una web | Hunyuan3D-2 instalado (pesado, opcional) |

`_molde-automejora.md` no es una skill: es el molde que usan las demás para anotar lo que
aprenden. Va en la misma carpeta.

## Instalarlas

Desde la carpeta del proyecto:

```powershell
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse -Force .\skills\* $HOME\.claude\skills\
Remove-Item $HOME\.claude\skills\README.md
```

⚠ Si ya tenías una skill con el mismo nombre, se reemplaza.

Abrí una sesión nueva de Claude y escribí `/`: tienen que aparecer en la lista.

### prompt-master (de otro autor)

Martín también usa `prompt-master`, que arma prompts optimizados para cada herramienta de IA.
No está copiada acá porque es de otra persona (licencia MIT): se baja de su repositorio
original, así recibís sus actualizaciones:

```powershell
git clone https://github.com/nidhinjs/prompt-master.git $HOME\.claude\skills\prompt-master
```

## Configurar `avisar`

Creá `%USERPROFILE%\.claude\telegram.json` con el token de tu bot (el mismo de
`TELEGRAM_TOKEN` en el `.env`) y tu id de Telegram:

```json
{"token": "el token de @BotFather", "chat_id": "tu id", "nombre": "tu nombre"}
```

Para que además anote en el cuaderno: `setx CUADERNO_NOTAS "C:\IA\notas"` (con tu carpeta) y
reabrí la terminal.

Probala: `python $HOME\.claude\skills\avisar\scripts\avisar.py "hola desde avisar"`. Te tiene
que llegar el mensaje al Telegram.

⚠ **La skill solo manda, nunca lee.** El bot del proyecto usa el mismo token para recibir
mensajes, y si otro programa los lee, se los roba.

## Configurar `buzon` (el hook)

Para que lo que le decís a Laura llegue solo a la sesión, Claude tiene que revisar el buzón
antes de cada mensaje tuyo. Eso es un *hook* en `%USERPROFILE%\.claude\settings.json`. Lo más
fácil es pedírselo a Claude: *"agregá a mi settings.json este hook"* y pegarle esto:

```json
"hooks": {
  "UserPromptSubmit": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python \"$HOME/.claude/skills/buzon/scripts/buzon.py\" pendientes 2>/dev/null || true",
          "timeout": 15,
          "statusMessage": "Revisando buzon de Laura"
        }
      ]
    }
  ]
}
```

Se prueba escribiendo una entrada a mano:
`python $HOME\.claude\skills\buzon\scripts\buzon.py escribir --texto "decime hola"`, y en tu
próximo mensaje a Claude tiene que aparecer "BUZON - mensajes de Laura sin atender".
