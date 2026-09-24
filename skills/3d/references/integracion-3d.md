# Integrar cualquier solución 3D

Leer esta referencia siempre que un GLB, escena, personaje, producto, accesorio o reconstrucción 3D se incorpore a una web, app, hero, visor o herramienta interactiva. La integración no termina cuando el archivo carga: debe conservar identidad visual, relaciones espaciales, interacción, rendimiento y una salida usable en cada tamaño relevante.

Las guías especializadas complementan este contrato:

- personajes animables: [unirig-local.md](unirig-local.md);
- armas, herramientas u objetos sostenidos: [rig-web-armas.md](rig-web-armas.md);
- defectos de malla o textura: [reparaciones-locales.md](reparaciones-locales.md).

## 1. Definir el contrato visual antes de mover el modelo

Escribir primero qué debe permanecer verdadero. Según el caso:

- qué cara es frente, arriba y lateral;
- qué parte debe tocar, mirar, apoyar o seguir a otra;
- qué puede responder al cursor, tacto, scroll o tiempo;
- qué ángulos están aprobados y cuáles exponen defectos;
- qué elemento manda la composición: modelo, cámara, texto, producto o personaje;
- qué debe seguir funcionando si WebGL o la carga fallan.

Estos invariantes son el criterio de terminado. Un valor de Euler, una escala o una captura aislada no lo son.

## 2. Auditar el asset real

Antes de integrarlo, inspeccionar:

- bounding box, centro y dimensiones;
- pivote y transformaciones de la escena raíz;
- ejes locales y signos reales;
- escala y unidades;
- cantidad de mallas, materiales, texturas y esqueletos;
- animaciones incluidas y nombres de huesos;
- extensiones de compresión como `EXT_meshopt_compression` o Draco;
- orientación de normales, transparencia y doble cara;
- licencia, atribución y restricciones.

No asumir que X es derecha, Y es arriba o que el origen coincide con el centro visual. Medir y luego mirar el modelo. Si se refleja una escala para invertir un eje, volver a verificar frente, normales y marcadores: el signo algebraico deja de ser una descripción intuitiva del objeto.

Conservar un maestro y producir una copia web. No optimizar, comprimir, reparar o riggear el único original.

### Verificar otra vez después de exportar

El contrato de ejes debe comprobarse sobre el GLB final dentro del motor que lo consumirá. Una transformación correcta en Blender, NumPy o Trimesh no garantiza que el archivo serializado llegue igual a Three.js: el exportador puede aplicar otra conversión Y-up/Z-up.

En el caso comprobado de la cabeza EVA, la malla fuente era Z-up con frente hacia -Y. Se transformó para horneado a Y-up y frente +Z, pero el GLB exportado por Trimesh todavía llegó a Three.js con arriba en -Z y frente en +Y. La corrección observable fue rotar la raíz `Math.PI / 2` sobre X antes de calcular bounds y cámaras:

```js
model.rotation.x = Math.PI / 2;
model.updateMatrixWorld(true);
```

Ese valor no es una receta universal: se usa sólo cuando los ejes medidos coinciden con ese caso. Después de corregir la raíz, recalcular centro, escala, target y cámaras semánticas. Un ángulo manualmente halagador no corrige el contrato del asset.

## 3. Separar los espacios de coordenadas

Toda integración interactiva combina varios espacios:

- coordenadas de pantalla o puntero;
- coordenadas normalizadas del contenedor;
- mundo de la escena;
- espacio local del padre;
- espacio local del asset;
- espacio de huesos si hay rig.

Nombrar mentalmente cada vector y cuaternión por su espacio. Las reglas más importantes:

- `object.position` y `object.quaternion` son locales al padre;
- `getWorldPosition()` y `getWorldQuaternion()` devuelven mundo;
- para aplicar una orientación mundial a un hijo, convertirla con la inversa del cuaternión mundial del padre;
- los offsets semánticos del asset deben vivir en coordenadas locales del asset;
- los offsets de pose deben rotar con el cuerpo o pivote correspondiente;
- llamar `updateWorldMatrix(true, true)` antes de leer posiciones después de cambiar una cadena.

Mezclar local y mundo suele producir resultados que parecen correctos en el centro y se desarman al girar.

## 4. Jerarquía sin dependencias circulares

Elegir un conductor claro para cada relación:

- escena o pivote conduce al modelo;
- modelo conduce a sus huesos;
- un accesorio independiente puede conducir metas de manos;
- la cámara observa, no corrige la geometría;
- la interfaz produce un objetivo, no muta varias cadenas contradictorias.

Evitar que A mueva B y B vuelva a resolver A en el mismo cuadro. Ejemplo: un objeto a dos manos no debe depender de una muñeca si la segunda mano se resuelve hacia ese mismo objeto.

Cuando varias partes siguen el mismo cursor, calcular un estado compartido y derivar respuestas acotadas. No registrar lógicas separadas que compitan por cabeza, torso, objeto y cámara.

## 5. Orientar con una base completa

Alinear un solo vector deja libre el giro alrededor de ese vector. Esto afecta armas, vehículos, cámaras, carteles, herramientas, ojos, focos y cualquier objeto direccional.

Definir tres ejes ortogonales:

- `forward`: dirección objetivo;
- `up`: arriba deseado proyectado sobre el plano perpendicular a `forward`;
- `side`: producto vectorial que completa la base.

Ejemplo para un asset X-forward, Y-up, Z-side:

```js
const forward = targetDirection.clone().normalize();
const up = desiredUp.clone()
  .addScaledVector(forward, -desiredUp.dot(forward));
if (up.lengthSq() < 0.0001) up.set(0, 0, 1);
up.normalize();

const side = forward.clone().cross(up).normalize();
const frame = new THREE.Matrix4().makeBasis(forward, up, side);
const desiredWorld = new THREE.Quaternion().setFromRotationMatrix(frame);
const parentWorld = object.parent.getWorldQuaternion(new THREE.Quaternion());
object.quaternion.copy(parentWorld.invert().multiply(desiredWorld));
```

Adaptar el orden a los ejes medidos. No sumar rolls o Eulers hasta haber definido qué significa arriba. Si hace falta un giro artístico adicional, aplicarlo sobre el eje actualizado y comprobar que no rompe la dirección.

## 6. Anclajes semánticos, no números de pantalla

Crear marcadores locales (`Object3D` vacíos o nodos equivalentes) para los puntos que importan:

- centro visual;
- base o apoyo;
- frente y extremo;
- pivote de giro;
- agarres;
- punto de emisión;
- contacto con piso o superficie;
- foco de cámara.

Ubicarlos a partir del bounding box y corregirlos mirando el asset. Un anclaje debe incluir los tres ejes; una fracción sobre la longitud no alcanza si el contacto está debajo, arriba o sobre una cara lateral.

Leer los marcadores en mundo durante la animación. Esto hace que el sistema sobreviva a escala, rotación, padres y responsive sin offsets fijos de pantalla.

## 7. Restricciones y animación

Resolver cada cuadro en un orden estable:

1. pose o estado base;
2. entrada normalizada y suavizada;
3. orientación de conductores principales;
4. anclajes y contactos;
5. restricciones secundarias o IK;
6. orientación de piezas terminales;
7. actualización de matrices;
8. render.

Usar amortiguación y límites. El cursor no debe mapearse uno a uno a un giro amplio si el modelo sólo está resuelto en un rango pequeño. Respetar `prefers-reduced-motion` y ofrecer interacción táctil equivalente cuando corresponda.

En rigs, conservar las orientaciones de reposo exportadas. Medir largos reales antes de IK. Una restricción exacta puede dar una silueta peor: si obliga a estirar una extremidad, revisar postura, anclaje y escala antes de deformar el cuerpo.

## 8. Cámara, encuadre y responsive

Normalizar el modelo usando sus bounds, pero encuadrar según el contenido relevante. En personajes, cabeza y pies suelen ser más confiables que el bounding box completo si hay accesorios o geometría flotante.

Separar:

- escala real del modelo;
- zoom o frustum de cámara;
- posición del modelo;
- composición HTML/CSS alrededor del canvas.

No arreglar un modelo pequeño agrandando arbitrariamente el asset si eso rompe contactos; a veces corresponde ajustar la cámara. No arreglar una superposición móvil con el mismo encuadre de escritorio: puede requerir una secuencia vertical distinta.

Validar al menos escritorio usado por el usuario, un ancho angosto y celular. Revisar también zoom del navegador si la interfaz lo hace probable.

En un visor con botones Frente, 3/4, Perfil y Espalda, cada botón debe restaurar una cámara semántica conocida. La órbita manual puede dejar activo el rótulo de una vista mientras la cámara ya está en otra; juzgar los ejes sólo después de volver a pulsar el botón. Capturar las cuatro vistas tras cada cambio de orientación raíz y comprobar cuerno, ojos, centro, silueta y margen. Recalcular el encuadre luego de rotar la raíz para evitar recortes distintos en escritorio y celular.

## 9. Materiales, luz y profundidad

La integración debe conservar la lectura del asset:

- configurar `colorSpace` de texturas;
- revisar tono y exposición;
- usar anisotropía cuando aporte;
- evitar transparencia amplia que lave el volumen;
- controlar `depthWrite`, `renderOrder` y caras dobles sólo cuando el caso lo requiere;
- comprobar que piezas agregadas no queden ocultas por una malla monolítica;
- iluminar forma y marca, no compensar geometría defectuosa con brillo.

Un material correcto se valida girando. Una vista frontal puede esconder caras invertidas, costuras, huecos o z-fighting.

## 10. Rendimiento y carga

- cargar de forma diferida cuando el 3D no sea el primer contenido necesario;
- incluir el decodificador correspondiente a la compresión usada;
- limitar `devicePixelRatio`;
- desactivar `frustumCulled` sólo cuando un rig o bounds incorrectos lo exijan y se haya medido el costo;
- limitar partículas, luces y transparencias;
- pausar o reducir trabajo fuera de pantalla cuando el proyecto lo permita;
- conservar fallback 2D si WebGL o la carga fallan;
- no vender decimación, subdivisión o reescalado como detalle nuevo.

La copia web debe equilibrar peso, textura y deformación. Probar que la optimización no rompa UV, pesos, morphs ni animaciones.

## 11. Diagnóstico que evita probar a ciegas

Combinar evidencia visual y numérica:

- exponer temporalmente ejes, bounds, anclajes y posiciones mundiales;
- medir error entre contacto real y meta;
- capturar centro y extremos de la interacción;
- comparar frente, perfil y reverso cuando el modelo gira;
- mirar consola y estado de carga;
- distinguir errores propios de la app de errores de extensiones del navegador;
- retirar todos los diagnósticos temporales al terminar.

Cambiar un solo supuesto estructural por iteración. Conservar la última versión visualmente aprobada y revertir una prueba que empeora la silueta, aunque su matemática parezca más correcta.

## 12. Fallos generales aprendidos

- **Carga correcta, orientación incorrecta:** faltó auditar ejes y pivote.
- **Frente correcto sólo después de arrastrar:** el botón y la cámara no representan los ejes reales del asset; corregir la raíz y restablecer cámaras semánticas.
- **Apunta bien pero está torcido:** se alineó una dirección sin definir arriba.
- **Funciona en el centro y falla al moverlo:** se mezclaron espacios local/mundo o se acumularon rotaciones.
- **Contacto que flota al girar:** el punto estaba en pantalla o mundo, no en el asset.
- **Dos cadenas se pelean:** la jerarquía creó una dependencia circular.
- **Restricción exacta pero pose fea:** se priorizó distancia sobre silueta y alcance natural.
- **Se ve bien sólo en una captura:** faltaron extremos, perfil o responsive.
- **El celular no muestra el cambio:** caché del módulo o versión del asset sin actualizar.
- **El visor desaparece después:** el servidor estaba ligado a una terminal temporal.
- **La corrección rompe otra parte aprobada:** se editó el maestro o se cambiaron demasiadas variables juntas.

## 13. Servidor y caché en Windows

Un proceso largo iniciado dentro de una terminal temporal puede morir al terminar la sesión. Para un visor que deba seguir accesible, iniciar un proceso oculto persistente con ruta absoluta, carpeta de trabajo explícita y bind `0.0.0.0` si se usará desde otro dispositivo (por ejemplo, por Tailscale). Verificar HTTP por `127.0.0.1` y por la IP remota.

Cuando se sirve JS sin bundler, cambiar el query de versión del módulo o el nombre del asset después de una modificación. Recargar el HTML no garantiza que el celular descarte el módulo anterior.

## Criterio de terminado

La integración está lista cuando:

- el asset carga o cae al fallback previsto;
- frente, arriba, escala y pivote se leen correctamente;
- los anclajes y contactos permanecen unidos durante toda la interacción aprobada;
- no hay saltos, acumulación de roll ni dependencias circulares;
- la silueta sigue siendo convincente en centro y extremos;
- escritorio y celular conservan composición y controles utilizables;
- no hay errores propios de la aplicación;
- el peso y el movimiento son proporcionales al destino;
- la versión anterior y el maestro siguen recuperables;
- los diagnósticos temporales fueron retirados.
