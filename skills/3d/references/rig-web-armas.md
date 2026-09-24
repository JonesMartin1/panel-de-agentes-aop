# Rigs web con armas u objetos a dos manos

Esta es una extensión especializada de [integracion-3d.md](integracion-3d.md). Leer primero la guía general y usar esta referencia cuando un personaje riggeado deba sostener un arma, herramienta u objeto largo con ambas manos, especialmente si la mirada y el objeto siguen el cursor en Three.js.

## Resultado buscado

La lectura visual debe sostener cuatro contactos simultáneos:

- la culata o apoyo toca el hombro o el cuerpo;
- la mano dominante coincide con la empuñadura o gatillo;
- la mano secundaria coincide con el guardamanos o apoyo delantero;
- el cañón sigue la mirada sin que el arma role o muestre un costado como si fuera su parte superior.

Una pose matemáticamente alcanzable puede seguir viéndose mal. El criterio final es la silueta renderizada: codos con flexión creíble, palmas visibles sobre el objeto, cabeza alineada y ausencia de intersecciones.

## Arquitectura estable

### El objeto es independiente de las muñecas

Montar el arma bajo el mismo pivote general del personaje, no como hija de una mano. Primero se orienta y posiciona el objeto; después cada brazo resuelve su propia meta hacia él.

Montarla en una muñeca y llevar la otra mano hacia el arma forma un circuito: la mano mueve el arma y el arma vuelve a mover la cadena. Al girar, esto produce cruces, deriva e intersecciones.

### Medir el GLB, no adivinar sus ejes

Calcular el `Box3` del objeto y registrar:

- eje longitudinal: la dimensión mayor;
- eje superior: el que realmente representa arriba en el asset;
- eje de espesor o lateral;
- centro, longitud y escala final.

Crear marcadores `Object3D` en coordenadas locales del arma para:

- `butt` o apoyo trasero;
- `muzzle` o punta;
- `triggerGrip`;
- `supportGrip`.

Los puntos deben incluir altura y espesor. Ponerlos sólo sobre la línea central hace que las manos atraviesen el cuerpo del arma. El gatillo suele estar más abajo; el apoyo delantero va debajo y sobre el lado visible del guardamanos.

Si se refleja la escala para invertir culata y cañón, no confiar en el signo del eje. La dirección física autoritativa es siempre:

```js
const forward = muzzleWorld.clone().sub(buttWorld).normalize();
```

Verificar visualmente qué extremo es la boca antes de animar.

## Orientación sin torsión

Un solo `setFromUnitVectors()` alinea el cañón, pero deja libre el roll. Si la rotación inicial ya estaba torcida, el rifle sigue torcido; si se aplican correcciones sucesivas, puede acumular roll.

Construir una base ortogonal completa en cada cuadro:

```js
const forward = headDirection.clone().normalize();
const up = new THREE.Vector3(0, 1, 0)
  .addScaledVector(forward, -forward.y);
if (up.lengthSq() < 0.0001) up.set(0, 0, 1);
up.normalize();

const side = forward.clone().cross(up).normalize();
const worldMatrix = new THREE.Matrix4().makeBasis(forward, up, side);
const desiredWorld = new THREE.Quaternion().setFromRotationMatrix(worldMatrix);

const parentWorld = mount.parent.getWorldQuaternion(new THREE.Quaternion());
mount.quaternion.copy(parentWorld.invert().multiply(desiredWorld));
```

Este ejemplo supone que el arma usa X longitudinal, Y superior y Z lateral. Adaptar el orden a los ejes medidos del asset.

Invariantes:

- calcular la orientación deseada en mundo;
- convertirla una sola vez al espacio local del padre;
- no asignar un cuaternión mundial directamente a `object.quaternion` si tiene un padre rotado;
- no mezclar cuaternios locales y mundiales en la misma operación;
- no agregar un roll de presentación arbitrario para arreglar la toma;
- si se aplica un giro alrededor del cañón, volver a medir el cañón después de la corrección anterior. Usar un eje viejo también desvía la puntería.

Para un hero frontal conviene proyectar el `up` global sobre el plano perpendicular al cañón, como arriba. Mantiene la parte superior del arma vertical incluso cuando el cañón sigue el cursor.

## Orden de resolución por cuadro

1. Aplicar la pose base y restaurar gradualmente los huesos desde sus cuaternios de reposo.
2. Orientar torso y cabeza.
3. Construir la base completa del arma y convertir mundo → local.
4. Llevar la culata al bolsillo del hombro dominante. El desplazamiento del bolsillo debe rotar con el torso o pivote; no usar un offset fijo de pantalla.
5. Actualizar matrices mundiales.
6. Leer los marcadores de gatillo y apoyo en mundo.
7. Resolver ambos brazos con IK de dos huesos y pole vectors.
8. Actualizar matrices después de orientar brazo superior, antebrazo y cada mano.
9. Orientar las palmas usando un hueso de referencia conocido, preferentemente `Index1`; no elegir simplemente el primer hijo porque en rigs de Character Creator suele ser el pulgar.
10. Renderizar y validar la silueta.

## IK de brazos

Con hombro `S`, meta `T`, largo superior `a` e inferior `b`:

```js
const toTarget = T.clone().sub(S);
const reach = THREE.MathUtils.clamp(
  toTarget.length(),
  Math.abs(a - b) + 0.01,
  a + b - 0.01
);
const direction = toTarget.normalize();
const along = (a * a - b * b + reach * reach) / (2 * reach);
const height = Math.sqrt(Math.max(a * a - along * along, 0));
```

Proyectar el pole vector del codo sobre el plano perpendicular a `direction` y construir el codo con `along` y `height`. Los pole vectors deben rotar con el torso. Para una toma de precisión, los codos suelen quedar bajos y levemente abiertos.

Conservar el cuaternión de reposo exportado por el rig al orientar cada hueso. Corregir sólo la dirección hacia el hijo; si se parte de identidad se retuercen las placas y pesos del personaje.

No forzar una meta fuera de alcance. Si la distancia hombro→agarre supera `a + b`, diagnosticar en este orden:

1. postura del torso;
2. ubicación local del marcador;
3. escala y posición del arma;
4. recién después, amplitud permitida del hombro o clavícula.

Reducir el alcance al máximo exacto suele dejar el brazo casi recto y empeora la silueta. No mover la clavícula a ciegas sólo para satisfacer una distancia. Una postura de tiro levemente lateral acerca naturalmente el hombro de apoyo al guardamanos.

## Manos y puntos de agarre

Resolver posición y orientación por separado:

- mano dominante: meta en la empuñadura; el índice puede seguir aproximadamente el cañón;
- mano de apoyo: meta debajo y sobre el lado visible del guardamanos; orientar la palma sin rolls grandes;
- usar el hueso `Index1` si existe, con fallback explícito;
- mantener pequeños los giros adicionales de palma. Un roll amplio puede hacer que la mano llegue al punto pero cuelgue vertical o muestre el dorso equivocado.

La mano no está agarrando si sólo apunta hacia la meta: medir la distancia entre la posición mundial real del hueso de mano y el marcador. Para calibrar, exponer temporalmente posiciones redondeadas en un atributo de diagnóstico y retirarlo al terminar.

## Diagnóstico visual y numérico

Registrar temporalmente:

- `butt`, `muzzle`, `triggerGrip`, `supportGrip`;
- hombro, codo y mano de cada lado;
- distancias hombro→meta y mano→meta;
- largos de brazo superior e inferior.

Una captura aislada no alcanza. Probar como mínimo:

- cursor al centro;
- extremo izquierdo;
- extremo derecho;
- tamaño de escritorio usado por el usuario;
- celular;
- consola sin errores propios de la aplicación.

Mirar estas relaciones:

- la parte superior del arma sigue siendo la parte superior en todo el recorrido;
- cara y cañón apuntan al mismo lado;
- culata permanece en el hombro;
- mano trasera no migra al cañón;
- mano delantera no flota ni cuelga;
- los codos conservan flexión;
- ninguna mano atraviesa el arma o el pecho.

## Fallos observados y por qué fallan

- **Arma hija de la muñeca:** genera dependencia circular con el segundo brazo.
- **Alinear sólo el cañón:** deja el roll indeterminado y el arma se ve torcida.
- **Mezclar cuaternios locales y mundiales:** duplica la rotación del padre y produce giros difíciles de predecir.
- **Euler fijo más correcciones sucesivas:** funciona en una captura y se rompe al mover el cursor.
- **Roll de presentación:** puede esconder un problema en un ángulo, pero no define qué lado es arriba.
- **Usar el eje del cañón medido antes de otra rotación:** el giro deja de ser puramente axial y cambia la puntería.
- **Metas sobre la línea central:** las manos atraviesan el volumen del arma.
- **Offsets en coordenadas de pantalla:** al girar el personaje dejan de representar gatillo, guardamanos y codos.
- **Primer hijo de la mano como guía:** suele elegir el pulgar y orientar mal la palma.
- **Meta delantera inalcanzable:** el brazo queda extendido o la mano flota.
- **Avanzar la clavícula para forzar alcance:** puede enderezar todo el brazo y empeorar la lectura.
- **Roll grande de la mano de apoyo:** la mano llega pero queda vertical o colgando.
- **Validar sólo en el centro:** oculta inversiones y torsiones que aparecen en los extremos.

## Caso validado: EVA y rifle

Estos valores documentan un caso real; sirven como referencia de escala, no como constantes universales.

- Personaje: `eva-hero-accurig.glb`, rig AccuRIG/Character Creator.
- Arma web: `eva-rifle-web.glb`.
- Bounding box del rifle: aproximadamente `[22.8163, 8.2061, 1.6990]`.
- Eje longitudinal medido: X. Eje superior: Y. Espesor: Z.
- La escala X se refleja para corregir culata y cañón; la dirección final se valida con marcadores.
- Escala visual: `bodyHeight * 0.54 / rifleLength`.
- Marcadores longitudinales: boca `-0.49 X`, culata `+0.49 X`.
- Empuñadura: `+0.26 X`, `-0.26 Y`, `+0.18 Z`, expresado como fracción del tamaño de cada eje.
- Apoyo delantero: `+0.19 X`, `-0.10 Y`, `-0.55 Z`.
- Bolsillo del hombro dominante: offset aproximado `[0.035, -0.035, 0.13]`, rotado por el cuaternión mundial del pivote.
- Torso de combate: yaw local aproximado `-0.36`, para acercar el hombro secundario sin estirar el brazo.
- Base de puntería: X sigue la mirada; Y es el `up` global proyectado; Z es `X × Y`.
- La mano dominante y la mano de apoyo terminaron coincidiendo con sus marcadores en mundo; la validación se hizo al centro y en ambos extremos del cursor.

La mejora decisiva no fue otro valor de Euler: fue reemplazar la alineación de un solo vector por una base completa y mover los agarres a coordenadas locales reales del objeto.

## Visor local en Windows

Para que el visor sobreviva al final de una sesión, no depender de un proceso atado a una terminal temporal. Iniciar el servidor como proceso oculto persistente, con ruta absoluta y carpeta de trabajo explícita:

```powershell
Start-Process -FilePath (Get-Command python).Source `
  -ArgumentList '-m','http.server','4173','--bind','0.0.0.0' `
  -WorkingDirectory 'C:\ruta\a\tu\proyecto-web' `
  -WindowStyle Hidden
```

Comprobar por separado `127.0.0.1` y la IP remota (por ejemplo, la de Tailscale). Al cambiar módulos JS servidos sin empaquetador, actualizar el query de versión del `<script type="module">` para evitar que el celular conserve una copia anterior.
