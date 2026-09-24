---
name: sincro-skills
description: Mantiene las skills de Martin visibles para sus dos cerebros, Claude Code y Codex, creando los enlaces que falten en las dos direcciones. Use when Martin dice "sincronizá las skills", "Codex no ve tal skill", "Claude no encuentra la skill que hice", "por qué no aparece la skill", o tipea /sincro-skills; y como diagnostico cuando una skill existe pero un cerebro no la lista. Not for traer una skill de internet (para eso esta traer-skill, que la audita antes de dejarla entrar), ni para el menu del panel, ni para crear una skill nueva.
---

# Sincronizar las skills entre Claude y Codex

Martín trabaja con dos cerebros y cada uno busca las skills en su propia carpeta. Una
skill escrita de un lado no existe para el otro hasta que hay un enlace.

Este script recorre las carpetas y crea el que falte, **en las dos direcciones**. Corre
solo, colgado del gancho `UserPromptSubmit`, así que normalmente no hay que invocarlo.

## Cuándo lo vas a necesitar a mano

- Martín dice que un cerebro no ve una skill que el otro sí.
- Apareció un aviso de **choque de nombres** y hay que resolverlo con él.
- Hay que revisar qué haría antes de que lo haga.

## Cómo se usa

```
python ~/.claude/skills/sincro-skills/scripts/sincro.py --simular
```

`--simular` dice qué haría sin tocar nada: **empezá siempre por ahí**. Sin argumentos
enlaza. Con `--json` sale para una pantalla. Con `--deshacer` saca los enlaces y deja
las carpetas reales intactas.

## Lo que hay que saber antes de tocarlo

- ⭐ **Enlace por skill, jamás la carpeta contenedora.** Enlazar `~/.claude/skills`
  entera hace que Claude Code deje de cargar las skills de usuario.
- ⭐ **Hay tres carpetas pero dos lectores.** Codex mira `~/.codex/skills` **y**
  `~/.agents/skills`; Claude solo la suya. La pregunta no es "¿está en las tres?" sino
  "¿la ve cada cerebro?". Razonarlo por carpetas crea enlaces de más.
- ⭐ **Un enlace se detecta con `os.readlink()`, nunca con `is_symlink()`**: en Windows
  son junctions y `is_symlink()` contesta `False` igual.
- Si hay un **choque** (el mismo nombre como carpeta real de los dos lados) no toca
  ninguna de las dos y avisa: elegir por él puede pisarle trabajo. Eso lo decide Martín.

El detalle completo, con el porqué de cada regla, está en el encabezado de
`scripts/sincro.py`. Se prueba con `pruebas/probar_sincro.py` (y `--mutar` para
verificar que los chequeos pueden fallar). No usa red, ni GPU, ni gasta tokens.

## Para las skills que vienen de internet

Esta skill **no** es la puerta de entrada. Una skill bajada de un desconocido son
instrucciones que los dos agentes van a obedecer sin preguntar: eso pasa por
`traer-skill`, que la deja en cuarentena y la mide antes de que entre.
