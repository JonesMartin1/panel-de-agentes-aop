# Molde de auto-mejora para skills

Bloque estándar para que una skill **aprenda de sus propios errores** en vez de repetirlos.
Copiá la sección "Auto-mejora" al final de cualquier `SKILL.md` nueva y creá su `LECCIONES.md`.

Nació de un caso real: durante días se publicaron workflows reiniciando el container de n8n,
tumbando los bots de todos los clientes ~40s cada vez, hasta que el usuario lo cortó. Esa
lección no puede depender de que alguien se acuerde — tiene que estar escrita, arriba, con la
evidencia al lado.

---

## Principio rector

**La regla enterrada no se dispara; la regla de arriba con ejemplo, sí.**
Se confirmó tres veces afinando el prompt de un bot: una instrucción agregada al final del
documento no cambiaba el comportamiento, y la misma instrucción movida a la zona crítica —
con un ejemplo concreto — funcionaba al primer intento.

Aplicado a una skill: lo que puede romper producción va **en las primeras 30 líneas del
`SKILL.md`**, no en un `reference/`.

---

## a) Cuándo se escribe una lección (y cuándo NO)

**SÍ, escribir lección** si pasó alguna de estas:

| Disparador | Ejemplo |
|---|---|
| Algo **rompió o causó daño** | Caída de un servicio, pérdida de datos, efecto sobre terceros |
| Un paso documentado **no funcionó** | El comando de la skill falló y hubo que rodearlo |
| Apareció una **capacidad nueva** que cambia cómo se trabaja | "cada ejecución guarda el snapshot del workflow" |
| Un **supuesto resultó falso** | "la retención era de 14 días" → en realidad 2,5 |

**NO escribir** si:
- Ya está cubierto por una regla existente → **afinar la que hay**, no agregar una gemela.
- Es un dato del proyecto, no del uso de la herramienta → va a la memoria del proyecto.
- Es una corazonada sin evidencia reproducible → **sin evidencia no se escribe**, se propone.

> Esta última es la más importante. Una skill que acumula creencias sin verificar termina
> siendo peor que no tener skill: da instrucciones equivocadas con tono de autoridad.

## b) Protocolo de actualización

1. **Anotar** en `LECCIONES.md` con el formato fijo de abajo (arriba del todo, más nueva primero).
2. **¿Es crítica?** (puede romper producción, perder datos o afectar a terceros)
   → subir la regla a **"Reglas de oro"** en la zona crítica del `SKILL.md`, con ejemplo.
   Si no es crítica, queda solo en `LECCIONES.md`.
3. **¿Cambia un procedimiento?** → **editar el paso existente**. Nunca dejar el paso viejo al
   lado del nuevo: dos versiones de la verdad es como se pudre una skill.
4. **Subir `version`** en el frontmatter (patch para una lección, minor si cambió un comando)
   y agregar una línea al changelog del final.
5. **Avisar al usuario en UNA línea**: qué se aprendió y qué archivo cambió.
   Ejemplo: `📝 Aprendido: el CLI de import está roto en 2.x → n8n-server v1.1 (LECCIONES.md)`

### Autonomía

- **Con evidencia dura** (un comando que falló, un id de ejecución, un mensaje de error,
  una medición) → actualizar sola y avisar.
- **Sin evidencia dura** (criterio, estilo, preferencia) → proponer y esperar el OK.

### Formato de lección (fijo)

```markdown
## AAAA-MM-DD · Título corto en una línea
- **Síntoma:** qué se vio (lo observable, no la teoría).
- **Causa raíz:** por qué pasó.
- **Regla:** qué hacer de ahora en más, en imperativo.
- **Evidencia:** el comando, el id, la medición que lo prueba.
- **Vigencia:** hasta cuándo vale / qué la invalidaría (opcional pero recomendado).
```

## c) Supuestos verificables

Una skill inteligente **chequea sus premisas al correr** en vez de confiar en notas viejas.
Cada `SKILL.md` lleva una tabla así, y sus comandos de diagnóstico la validan:

| Supuesto | Cómo se verifica solo | Si cambió |
|---|---|---|
| *(la premisa)* | *(el comando que la mide)* | *(qué reglas hay que re-testear)* |

Cuando un supuesto no se cumple: **avisar y marcar las lecciones que dependen de él** como
"a re-testear", en lugar de seguir aplicándolas a ciegas. Una regla nacida de una versión
vieja del software puede ser hoy un obstáculo.

## d) Poda (que no se convierta en un basurero)

- `SKILL.md`: tope **~150 líneas**. Si crece, el detalle baja a `reference/`.
- `LECCIONES.md`: hasta ~10 lecciones vigentes; las viejas van a `LECCIONES-ARCHIVO.md`.
- Lección contradicha o vencida → marcarla **OBSOLETA con fecha y motivo**, *no borrarla*:
  borrar una lección invita a re-descubrir el error por las malas.
- Revisar supuestos cuando cambia la versión de la herramienta o el servidor.

---

## Detalle operativo: una skill recién creada puede no estar disponible en la misma sesión

Claude Code lee el catálogo de skills al arrancar la sesión, y en versiones recientes
también lo relee en caliente. Si una skill nueva no aparece (`Unknown skill: <nombre>`),
reiniciar la sesión lo arregla. Mientras tanto se puede usar igual **corriendo sus scripts
a mano**: no dependen de que la skill esté registrada.

## Bloque para pegar en `SKILL.md`

```markdown
## Auto-mejora

Esta skill se corrige a sí misma. Seguí el protocolo de
[_molde-automejora.md](../_molde-automejora.md):

- **Si algo rompió, un paso falló, apareció una capacidad nueva o un supuesto resultó falso**
  → escribí la lección en `LECCIONES.md` (formato fijo: síntoma · causa · regla · evidencia ·
  vigencia). Si es crítica, subí la regla a "Reglas de oro" acá arriba, con ejemplo.
- **Con evidencia dura, actualizá sola y avisá en una línea.** Sin evidencia, proponé primero.
- Al terminar: subí `version` y agregá la línea al changelog.
- No dupliques reglas: afiná la existente. No dejes el paso viejo al lado del nuevo.
```
