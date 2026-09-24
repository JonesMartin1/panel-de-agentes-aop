---
name: 3d
description: "Genera, regenera, mejora o integra soluciones 3D: convierte imágenes en GLB local y puede incorporar modelos, personajes, productos o escenas existentes en una web, app, hero o visor. Usar cuando el usuario invoque /3d o pida trabajar con 3D, especialmente con Hunyuan3D, rigs, interacción web y una GPU de 8 GB."
---

# Generación e integración 3D

> Necesita **Hunyuan3D-2 instalado localmente** (ver [references/hunyuan-local.md](references/hunyuan-local.md)).
> Las rutas de esa referencia son las de la instalación original (`D:\IA\modelos-3d`):
> si en esta máquina está en otro lado, usar la ruta real y no inventarla. Si Hunyuan no
> está instalado, decirlo y no intentar instalarlo sin autorización: son varios GB.
> Para integrar un GLB que ya existe en una web no hace falta Hunyuan.

## Flujo

### Comportamiento predeterminado de `/3d`

Si el usuario adjunta una imagen e invoca `/3d` sin más texto, ejecutar el flujo completo sin pedir destino, calidad, nombre ni parámetros:

- Generar automáticamente el mejor GLB viable con esta computadora y guardarlo, junto con sus archivos de trabajo, en una carpeta nueva dentro de `generados` en la carpeta de modelos 3D. Usar un nombre corto derivado del sujeto si es evidente; si no, usar fecha y hora. Nunca sobrescribir otro trabajo.
- Crear o reutilizar un visor web local, levantarlo en un puerto libre y entregar la dirección `http://127.0.0.1:<puerto>` junto con la ruta del GLB. El enlace es local y dura mientras el servidor siga encendido; no publicarlo en Internet.
- Elegir multivista, resolución, textura UV y optimización automáticamente según la referencia y la memoria disponible. Priorizar calidad usable dentro de 8 GB.
- Preguntar sólo si falta la imagen, existe un bloqueo real, se requiere autorización nueva o hay una decisión que cambia materialmente el resultado. No pedir confirmaciones de rutina.
- No integrar el resultado en un proyecto existente a menos que el usuario indique ese destino.

## Flujo técnico

1. Identificar la imagen fuente y las restricciones de licencia, estilo y GPU. No descargar, instalar, publicar ni sobrescribir sin autorización aplicable.
2. Inspeccionar la referencia. Para personajes complejos, no confiar en reconstrucción de vista única: generar una lámina ortográfica coherente con frente, izquierda, espalda y derecha. Mantener exactamente diseño, pose, proporciones y paneles de color; usar fondo transparente o blanco puro, sin piso, sombra, texto, perspectiva ni microdetalle.
3. Recortar la lámina en cuatro vistas iguales y verificar visualmente que ninguna vista cambie la identidad o geometría.
4. Generar la geometría. Leer [references/hunyuan-local.md](references/hunyuan-local.md) antes de iniciar procesos o consumir GPU. Durante la generación, aplicar su modo exclusivo: apagar por los controles seguros del panel cualquier otro modelo de cómputo y dejar Hunyuan como único modelo en la GPU.
5. Inspeccionar silueta, frente, perfil y espalda. Si la geometría no es reconocible, corregir las vistas antes de subir resolución o pasos. Detenerse y explicar el consumo concreto si hay falta de VRAM.
   - Para defectos localizados o piezas aparentemente duplicadas, leer [references/reparaciones-locales.md](references/reparaciones-locales.md) antes de modificar el GLB.
   - Si el modelo ya está aprobado en varias vistas y el defecto está limitado a una zona, no regenerar el objeto completo. Primero mirarlo sin textura y rotarlo: si el defecto desaparece es de textura; si conserva volumen o altera la silueta es de geometría.
   - Si una pieza parece duplicada pero desaparece al quitar la textura, revisar el atlas UV: la proyección puede haber impreso esa pieza sobre la superficie que tiene detrás por falta de oclusión. Limpiar sólo el sector afectado del islote UV, reconstruyendo el material de base desde una zona sana equivalente, y volver a incrustar la textura en una copia del GLB. No borrar geometría en este caso.
   - Antes de borrar, comprobar si la pieza incorrecta es un componente separado o si quedó fusionada a la malla principal. Un conteo de componentes no alcanza: verificar también a qué componente pertenecen las caras de la zona defectuosa.
   - Si es un componente separado, retirar sólo ese componente. Si está fusionado, hacer una reparación local sobre una copia: delimitar la zona por posición y vistas, eliminar únicamente las caras erróneas, cerrar o reconstruir la superficie faltante y suavizar la unión. No aplicar remallado global ni alterar las partes ya validadas.
   - Si no existe un perímetro local inequívoco —por ejemplo, hay miles de bordes abiertos o no-manifold en todo el volumen— no simular una reparación con tapas planas, esferas ni primitivas internas. Generar una superficie cerrada nueva desde una copia, conservando la malla y el color fuente como referencia; verificar estanqueidad y el resultado visual desde frente, perfil, espalda y el ángulo del defecto antes de activarla.
   - Conservar UV y textura fuera de la reparación. Si cambió la topología local, volver a proyectar u hornear esa zona —o generar una textura nueva sobre la copia— sin sobrescribir la versión aceptada.
   - Si una reconstrucción cerrada suaviza un detalle importante, se puede recuperar sólo esa pieza desde la malla UV aprobada: recortarla dentro de una frontera material o estructural natural (por ejemplo, el interior de un recipiente), separarla apenas por su normal y probar el giro. Rechazar la variante si aparece junta, parpadeo de profundidad o cambio de silueta; nunca superponerla a lo largo de la piel exterior completa.
   - Cuando la selección automática de caras no sea inequívoca, no hacer un corte amplio por aproximación: pasar a selección visual en Blender o pedir la referencia mínima necesaria.
6. Para una GPU de 8 GB, evitar el texturizador nativo pesado. Para borradores usar `scripts/bake_multiview_colors.py`. Si se pide más definición, usar `scripts/bake_uv_multiview.py` para desempaquetar UV y hornear las cuatro vistas en una textura 2K; requiere `xatlas`, OpenCV, Pillow, SciPy y Trimesh. No vender subdivisión o reescalado como detalle real: si la referencia no contiene el grano, grabado o textura que se necesita, pedir una foto de primer plano. Conservar la versión anterior hasta validar el resultado.
   - Si el usuario necesita expresamente la textura nativa de Hunyuan en Windows, leer primero [references/hunyuan-textura-windows.md](references/hunyuan-textura-windows.md). Es una excepción pesada: sólo correrla sobre una copia web de densidad moderada, con los pesos locales conocidos y con la memoria GPU monitoreada. La textura generada puede inventar material o decoración; validar siempre frente y perfil y conservar sólo la geometría si no respeta la referencia.
7. Optimizar sólo lo necesario para el destino. Conservar el modelo maestro y producir una copia web; no borrar originales.
8. Si el usuario pide que un personaje humanoide sea animable o configurable, leer [references/unirig-local.md](references/unirig-local.md). Riggear el maestro aprobado, validar deformaciones reales y recién después crear la copia web. No confundir una oscilación del objeto entero con animación corporal: para esto deben existir esqueleto y pesos de piel utilizables.
   - Si el personaje debe sostener un arma, herramienta u objeto con ambas manos, o apuntarlo siguiendo el cursor, leer [references/rig-web-armas.md](references/rig-web-armas.md). Resolver el objeto con una orientación completa y metas físicas de agarre; no montarlo directamente en una muñeca ni orientar todo con un solo vector.
9. Al incorporar cualquier solución 3D a una web, app, hero, visor o herramienta interactiva, leer [references/integracion-3d.md](references/integracion-3d.md). Aplicar sus contratos de ejes, espacios, anclajes, jerarquía, interacción, rendimiento y validación; no tratar la integración como una simple carga del GLB.
10. Cuando ya no se necesite Hunyuan, ejecutar el cierre de sesión de [references/hunyuan-local.md](references/hunyuan-local.md): apagar Hunyuan y restaurar exactamente los modelos y servicios que se habían detenido al liberar la GPU. No dejar la máquina en modo exclusivo después de terminar ni encender algo que ya estaba apagado antes.

## Criterio de salida

- Entregar la ruta del GLB y de sus archivos de trabajo.
- Informar qué generador, variante y parámetros se usaron.
- Indicar limitaciones visibles y si el color es UV o por vértice. La proyección UV mejora definición, pero no inventa geometría ni detalles ausentes en las referencias.
- En una reparación localizada, entregar comparativas desde el ángulo del defecto y desde las vistas que ya estaban aprobadas. Verificar que desapareció el volumen o silueta duplicada, que no quedaron agujeros ni caras no manifold y que el resto del modelo no cambió.
- Si se integró, confirmar encuadre, ejes, anclajes, interacción, carga diferida, rendimiento, movimiento reducido y fallback 2D en los tamaños relevantes.
- Si se riggeó, informar cantidad de huesos, qué partes se probaron y si la animación usa huesos reales o sólo transforma el objeto completo.
- Si sostiene un objeto a dos manos, confirmar que culata o apoyo, empuñadura y guardamanos coinciden con el cuerpo; que el objeto conserva un eje superior estable; y que ambas manos permanecen sobre sus metas en el centro y los extremos del recorrido.
- Registrar la combinación exitosa de vistas, parámetros y postproceso dentro de la carpeta de trabajo para poder repetirla.
- Si se usó Hunyuan, confirmar al entregar que quedó apagado y que se restauró el estado previo de los demás modelos y servicios, salvo que el usuario haya pedido mantener la generación activa.

## Propiedad intelectual

Para personajes o diseños de terceros, advertir antes del uso comercial. No usar assets marcados `NoAI` como entrada generativa y verificar licencias y atribución de cualquier modelo externo.
