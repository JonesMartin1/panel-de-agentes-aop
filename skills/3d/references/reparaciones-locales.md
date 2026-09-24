# Reparaciones locales comprobadas

## Decisión principal

Antes de cortar una malla, comparar el defecto con el mismo GLB usando un material liso, sin textura:

- Si el volumen o la silueta incorrecta sigue presente, el defecto es geométrico.
- Si desaparece, el defecto está en la textura o su proyección UV. No modificar la geometría.

Esta comprobación tiene prioridad sobre la impresión producida por una captura texturada: una fotografía proyectada puede simular profundidad y parecer una segunda pieza.

## Pieza duplicada por proyección sin oclusión

Caso comprobado el 2026-08-23 con una cafetera De'Longhi: el portafiltro real estaba bien, pero la vista frontal también lo había impreso sobre el panel situado detrás. Desde un costado parecía haber dos portafiltros. El análisis sin textura mostró una sola pieza y evitó cortar por error la varilla de vapor.

Procedimiento reutilizable:

1. Conservar el GLB maestro y trabajar sobre una copia.
2. Crear una previsualización de diagnóstico con material liso. Si hace falta delimitar geometría, colorear en rojo las caras candidatas antes de borrarlas y rotar el modelo en el visor.
3. Si la malla es correcta, localizar en el atlas UV el detalle impreso sobre la superficie posterior.
4. Enmascarar solamente esa impresión. Reconstruir el sustrato desde una zona sana del mismo islote y material, respetando dirección, brillo y grano; en metal cepillado conviene usar una franja limpia vecina y mezclar los bordes suavemente.
5. Incrustar la textura reparada en un GLB nuevo. No sobrescribir el maestro ni la versión previamente aceptada.
6. Verificar en el navegador el ángulo que revelaba el defecto, ambos costados y las vistas ya aprobadas. El trabajo termina sólo cuando desaparece el fantasma, queda la pieza geométrica real y no cambian las zonas sanas.

## Si el defecto sí es geométrico

Comprobar primero componentes conexos y luego pertenencia de las caras de la zona. Si la pieza está separada, retirar únicamente ese componente. Si está fusionada, seleccionar visualmente la región, eliminar sólo esas caras, cerrar la abertura y suavizar la unión. Una selección dudosa se previsualiza coloreada; no se ejecuta como corte aproximado.

## Pieza aparentemente duplicada por perspectiva

Antes de modelar una segunda aleta, brazo, asa, ala u otra pieza lateral, comprobar las dos vistas cardinales y la vista opuesta. En una perspectiva oblicua, el componente simétrico del otro lado puede aparecer por detrás y parecer una segunda pieza del mismo costado. Si las vistas frontal y posterior confirman una sola extensión por lado, conservar esa continuidad; no reconstruir como objetos apilados lo que en realidad es una única pieza o una sola pieza por cada lado.

Caso comprobado el 2026-08-25 con una cabeza EVA: dos prolongaciones que parecían estar en el mismo perfil eran las extensiones izquierda y derecha superpuestas por la cámara. Agregar placas independientes produjo barras flotantes y una silueta doble. La solución fue mantener la extensión continua ya presente en la malla y modificar sólo sus materiales focales.

## Elegir la reparación según el tamaño y la función del detalle

En una malla generada y fusionada, no aplicar la misma técnica a todas las partes:

- Conservar las piezas grandes cuya silueta ya fue aprobada. Para bandas, cambios de material o separaciones que deben envolver un volumen existente, pintar o asignar material sobre su topología real suele preservar mejor frente y perfil que superponer una primitiva nueva.
- Usar geometría independiente conformada para detalles pequeños y focales —por ejemplo lentes dentro de una cavidad ocular— cuando necesiten profundidad o un material propio. Proyectar cada punto sobre la superficie y verificar que toda la pieza golpee la misma capa.
- Evitar paneles amplios construidos con rayos sobre mallas con capas, cavidades o superficies cercanas. Distintos puntos pueden caer en capas diferentes; al triangularlos aparecen puentes, láminas flotantes o caras que atraviesan el cuerpo. Si ocurre, descartar esa variante en vez de ocultarla con color o doble cara.
- Una pieza cerrada nueva no es automáticamente una mejora. Rechazarla si conserva la dirección pero empeora la continuidad, la proporción o el perfil respecto de la geometría aprobada.

Para separar un inserto delantero de una extensión continua, puede usarse también la profundidad real de los vértices: conservar el material secundario sólo en la parte delantera y devolver el barrido posterior al material estructural. Validar siempre desde el perfil que expuso la confusión.

## Malla abierta de alcance global y detalle selectivo

Si el diagnóstico encuentra bordes abiertos o no-manifold por miles y repartidos por todo el cuerpo, no hay un agujero local para rellenar: una tapa plana, esfera interior o Grid Fill amplio seguirá mostrando una cavidad o deformará la silueta. En ese caso:

1. Conservar el maestro UV y la última versión aprobada; trabajar siempre en un GLB nuevo.
2. Reconstruir una superficie cerrada a partir de la copia —por ejemplo, con una reconstrucción de superficie local— y transferir el color desde el maestro como referencia. Confirmar que sea estanca antes de considerar el acabado.
3. Rotar la versión nueva desde el ángulo del defecto, frente, perfil, espalda y base. El chequeo topológico no sustituye esa inspección visual.
4. Si la reconstrucción suavizó una zona focal, recuperar sólo esa zona desde el maestro UV de alta definición. El recorte tiene que terminar en una frontera natural: interior, junta, borde o cambio de material.
5. Desplazar la capa recuperada apenas sobre su normal para evitar z-fighting. Si genera una línea, un cambio de tono o un salto de silueta, descartar la capa amplia y reducirla; no ocultar la junta con otra primitiva.
6. Más caras o una textura reescalada no crean información. Para mejorar grano, perforaciones, grabados o metal fino por encima de la referencia, pedir una vista cercana específica de esa pieza.

Caso comprobado el 2026-08-23: la base de un mate tenía una apertura no local. La superficie cerrada resolvió el volumen; una superposición UV sobre todo el cuello dejó una junta visible y se descartó. La recuperación limitada a yerba y bombilla conservó el cierre y mejoró el detalle perceptible.

## Reemplazar una parte de un personaje con skin

Si el modelo tiene esqueleto y pesos, no retirar cabeza, manos u otra pieza con un plano de corte global. Ese corte también elimina hombros, collar, pelo, accesorios o armadura que comparten altura, y una pieza nueva sobredimensionada puede ocultar el daño hasta que se corrige la proporción.

Procedimiento comprobado:

1. Congelar la pose neutral y hornear la malla evaluada sólo cuando ya se registraron los índices influidos por los huesos de la parte que se reemplaza.
2. Construir la selección con grupos semánticos del rig. Para una cabeza AccuRIG, incluir cabeza, cara, mandíbula, ojos, dientes y lengua; no incluir cuello, clavículas ni hombros salvo que la referencia nueva también los reemplace.
3. Eliminar esos vértices por índice en la copia horneada. Usar un corte geométrico únicamente como fallback cuando no existen pesos confiables.
4. Montar la pieza nueva con un contrato explícito de frente y arriba. Calibrar primero el ancho contra el cuerpo completo, después el anclaje vertical contra cuello y collar; una cámara favorable no corrige una escala incorrecta.
5. Revisar frente, ambos tres cuartos, perfil y espalda. Comprobar especialmente que no haya hombros planos, cuello flotante, solapamiento con el pecho ni accesorios laterales desaparecidos.

Caso comprobado el 2026-08-25 con EVA-01: el corte horizontal borraba las torres de los hombros y obligaba a una cabeza enorme para disimularlo. La selección por pesos faciales preservó hombros y torso; una cabeza de aproximadamente el 44% del ancho total y un anclaje cercano al tercio de su altura recuperaron una proporción coherente.

## Registro del caso comprobado

- En la instalación original, la cafetera reparada quedó en `generados\cafetera-delonghi-corregida-20260823-040010\` dentro de la carpeta de modelos 3D, con su script `reparar_textura_local.py` al lado.
- Originales conservados: malla maestra, textura anterior y GLB texturado anterior.
