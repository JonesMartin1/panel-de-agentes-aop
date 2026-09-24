# La interfaz de este proyecto — contexto para la sesión que la maneja

Martín puso una sesión a cargo de las pantallas (2026-08-17). Esto es lo que hay que saber
antes de tocar un pixel: qué pantallas existen, dónde vive cada una, qué está decidido y no
se discute, con qué se prueba, y qué está roto hoy.

Lo demás del proyecto (Whisper, el micrófono, el bot, la GPU) está en `README.md`; las reglas
de convivencia entre sesiones, en `CLAUDE.md` y `PIZARRA.md`. Acá va solo la pantalla.

---

## 1. Las pantallas

Todo se sirve desde `panel.py` (FastAPI, puerto 8750). No hay build, ni framework, ni npm:
es HTML+CSS+JS a mano, dentro de strings de Python, salvo las dos piezas que ya salieron a
archivo aparte.

| Pantalla | URL | Dónde vive | Tamaño |
|---|---|---|---|
| **Panel de escritorio** | `/` | `panel.py` → `PAGINA` (líneas ~264-1002) | ~740 líneas |
| **Pizarra** (lienzo tipo Miro) | `/pizarra` | `panel.py` → `PAGINA_PIZARRA` (~1362-4307) | ~2.950 líneas |
| **App del celular** | `/movil` | `panel.py` → `MOVIL_HTML` (~4940-5917) | ~980 líneas |
| **Sesiones de Claude Code** | `/sesiones` | `app/estaticos/sesiones.html` | 474 líneas |
| **Estudio de audio y video** | `/estudio` | `app/estaticos/estudio.html` | ~1.400 líneas |
| **Avisos** (Recordatorios del iPhone) | `/avisos` | `app/estaticos/avisos.html` | ~290 líneas |
| **Markdown compartido** | `/estaticos/marcado.js` | `app/estaticos/marcado.js` | ~150 líneas |
| **Aspecto compartido** | `/estaticos/aspecto.js` | `app/estaticos/aspecto.js` | ~330 líneas |
| **Direcciones compartidas** | `/estaticos/direccion.js` | `app/estaticos/direccion.js` | ~95 líneas |
| **Marcador de texto** | `/estaticos/marcas.js` | `app/estaticos/marcas.js` | ~300 líneas |
| **Menú de pantallas** | `/estaticos/menu.js` | `app/estaticos/menu.js` | ~70 líneas |

⭐ **El menú que lleva de una pantalla a otra está en UN solo lugar: `app/estaticos/menu.js`.**
Cada pantalla de la compu pone `<nav id="menuPantallas"></nav>` donde lo quiere y carga ese
script; los estilos los trae él, así que se ve igual en las cinco aunque cada página tenga su
propia hoja. **Agregar una pantalla nueva es agregar un renglón a `PANTALLAS` ahí** — no tocar
las cinco páginas. La pantalla en la que estás parado se marca y no se puede clickear.
En el teléfono no aparece: la pizarra esconde el `<header>` abajo de 700 px y la app del
celular tiene su propia barra de abajo.

⭐ **Lo que está en `app/estaticos/` se edita como un archivo normal; lo que está adentro de
`panel.py` hay que escaparlo mentalmente dos veces** (es un string de Python con JS adentro,
y el JS usa backticks). Cuando una pantalla pasa de ~200 líneas, conviene mudarla a
`app/estaticos/` y servirla con `FileResponse` — así se hizo con `sesiones.html` y con
`marcado.js`. **Ese es el camino para lo que venga.**

### La ventana de escritorio (2026-08-17)

El panel **también se abre como app de Windows**, sin navegador alrededor:
`app/escritorio.py` (WebView2, el motor que ya trae Windows 11 — no hay Electron ni npm).
No es una pantalla nueva: es **la misma `/` de siempre metida en una ventana propia**, con
ícono en la barra de tareas y en la bandeja del reloj. `launcher.vbs` la abre en vez del
navegador; la línea vieja quedó comentada ahí al lado por si hay que volver.

- ⭐ **Es un proceso APARTE del panel**, a propósito: acá el panel se reinicia seguido y la
  ventana se cerraría sola en cada reinicio. Un vigilante la deja en "Esperando al panel"
  mientras no contesta y **la devuelve sola a la misma pantalla** cuando vuelve.
- **La cruz la esconde en la bandeja, no apaga nada.** Salir de verdad es desde el ícono del
  reloj, y tampoco apaga los servicios.
- **Reiniciar el panel se hace desde la bandeja** (hace falta cada vez que se toca `panel.py`).
  Va sin `--auto`, así que no prende lo que Martín tenga apagado, y ⚠ **primero pregunta si hay
  una sesión de Claude contestando adentro**: corren como hijas del panel y un reinicio en el
  medio les mata la respuesta. Si la hay, avisa y no reinicia (`_sesion_contestando`).
  ⚠ Para encontrar el panel **no alcanza con buscar "panel.py" en la línea de comando**:
  cualquier consola que lo nombre la tiene igual (probado: daba 5 procesos, uno solo era el
  panel). Tiene que ser un python cuyo *argumento* sea `panel.py`.
- El acceso del escritorio y el de la barra de tareas abren la ventana, y **si el panel no está,
  lo prende** (ahí sí con `--auto`): alcanza un solo ícono para todo.
- ⚠⚠ **La posición guardada se acomoda antes de usarla** (`_acomodar`). El 2026-08-17 quedó
  guardado `y = -33`: la barra de título 33 px arriba del borde de la pantalla, o sea la ventana
  entera a la vista y **sin ningún lugar de dónde agarrarla**. Ahora la barra nunca puede quedar
  fuera, ni al guardar ni al abrir, y la bandeja tiene **"Acomodar la ventana"** como rescate —
  ahí se llega siempre, aunque la ventana no se vea.
- ⭐ **Los tamaños de ventana van en píxeles LÓGICOS y esta pantalla está al 175 %**: 1320×880
  "chicos" son 2310×1540 de verdad, casi todo el monitor, y al salir de maximizada parecía roto.
  Por eso el tamaño de rescate se calcula como una parte del monitor (`_tamano_comodo`), no fijo.
- Lanzarla dos veces no abre dos ventanas: la segunda le toca el timbre a la primera por un
  socket (puerto 8751) y se va.
- Prueba: `pruebas/ver_ventana_escritorio.py` (10 chequeos) — abre la ventana contra un
  **puerto muerto** para poder mirar lo que se ve cuando el panel no está, que es justo lo
  que no se puede probar con el panel prendido.

### Botón del medio: abrir una charla sin salir de la lista (2026-08-19)

Pedido de Martín: *"me gustaría poder hacer click con el botón del medio del mouse sobre
las sesiones y se me abran en una nueva pestaña las conversaciones"*. Vive en
`abrirSesion(cwd, sid, nombre, fondo)` y en el enganche de las filas de `pintarLista()`.

- ⭐ **"Nueva pestaña" es la barra de arriba de la app, no una del navegador.** El gesto
  sirve para marcar tres o cuatro de un saque desde la bandeja y recorrerlas después, en
  vez de entrar y volver por cada una. **Ctrl+clic hace lo mismo** (el mouse sin rueda
  también tiene que poder).
- ⭐⭐ **Lo que define el gesto es lo que NO hace: no te mueve de la lista.** Por eso la
  mitad de los chequeos de la prueba miran que después del clic sigas parado en la bandeja.
- ⚠ Como la pantalla no cambia en nada, **la pestaña nueva parpadea 1,5 s** (`.tab.recien`)
  y se la lleva a la vista con `scrollIntoView`: sin eso el clic se siente como si no
  hubiera pasado nada. El parpadeo se apaga con un **repintado**, no sacando la clase a
  mano: la barra se redibuja sola cada pocos segundos y se lo llevaría puesto antes.
- ⚠ **El grupo del proyecto queda desplegado** al abrir atrás: si la pestaña cae adentro
  de una pastilla plegada, no se ve nada y volvemos al problema anterior.
- ⚠ **Sin `sid` no abre nada.** La fila "Empezar una conversación" viene con `data-nueva`
  en "Todas" y con el **sid vacío** adentro de una carpeta: sin esa guarda, el botón del
  medio abría atrás una charla nueva fantasma. Y una charla nueva en segundo plano no
  sirve para nada — a una charla nueva vas a escribirle.
- ⚠ Hay que comerse el `mousedown` del botón 1: Chrome le prende el **desplazamiento
  automático** y te deja el iconito redondo dando vueltas.
- ⚠ Los gestos van como **propiedad** (`el.onauxclick = …`), no con `addEventListener`: la
  lista se reengancha en cada repintado y así no se apilan diez copias del mismo gesto.
- Prueba: `pruebas/ver_boton_medio.py` (22 chequeos). ⚠ Cuenta las pestañas **del estado,
  no del DOM**: la barra agrupa por proyecto y el grupo plegado no dibuja las suyas, así
  que contarlas en pantalla daba de menos sin que faltara ninguna.

### Mover las carpetas de la barra lateral, y sacarlas (2026-08-18)

Pedido de Martín: *"quiero poder mover las carpetas y sacarlas de acá. Además quiero
poder que esto tenga una animación linda"*. En la columna de proyectos de `/sesiones`
cada carpeta tiene ahora un agarre **⠿** para arrastrarla y una **✕** para sacarla.

- ⚠⚠ **Sacar NO borra NADA**: ni la carpeta del disco, ni sus conversaciones, ni la
  entrada de `carpetas_sesiones.json`. Es una lista de nombres que la pantalla saltea,
  exactamente la misma idea que `sesiones_archivadas.json` con las charlas. La prueba
  lo fija mirando que `datos.proyectos` siga teniendo las cuatro.
- ⭐ **Vive en el SERVIDOR** (`ORDEN_CARPETAS` → `orden_carpetas.json`, con
  `GET/POST /carpetas/orden` y `POST /carpetas/ocultar`), no en el navegador: la misma
  lista de proyectos está en el cajón del celular y un orden guardado en una sola
  pantalla dejaría a la otra mostrando cualquier cosa.
  ⚠ Viaja **adentro de `/movil/sesiones`**, no como pedido aparte: esa respuesta es la
  que las pantallas guardan para dibujarse al instante, así que con un pedido separado
  el primer pintado saldría con el orden viejo y saltaría un segundo después.
- ⭐ **Lo que no está en el orden guardado va al final**, no arriba. Así una carpeta
  nueva no obliga a reescribir el orden ni se cuela en un lugar que no le diste vos.
- ⭐⭐ **La animación de mover es FLIP**, que es la única forma de que se entienda qué
  se movió: se anota dónde estaba cada renglón, se mueve el nodo, se mide dónde quedó,
  se lo manda de vuelta al lugar viejo con un `transform` y se lo suelta en el cuadro
  siguiente — el navegador anima el camino. Sin eso el reordenado es un salto seco.
- ⚠⚠ **Se arrastra la FILA ENTERA, y eso se resuelve con un UMBRAL, no con dos zonas.**
  La primera versión tenía un agarre ⠿ al costado y Martín lo rechazó apenas lo vio:
  *"no me gusta tener que agarrar el costado, tendría que poder seleccionar la carpeta
  entera y así moverla"*. El problema de fondo es que esa misma fila ya era el clic que
  ENTRA al proyecto. La salida es `UMBRAL_MOVER` (5 px): el `mousedown` no arrastra
  nada, solo anota dónde empezó; recién cuando el puntero se corre más de 5 px esto pasa
  a ser un arrastre, y soltar sin llegar es un clic de los de siempre. Así el gesto
  corto y el largo conviven en el mismo lugar. **La lección general: cuando dos gestos
  quieren el mismo elemento, se separan por CÓMO se hacen, no partiendo el elemento en
  pedacitos** — partirlo es lo que se siente incómodo.
  ⚠ Y `movioCarpeta` corta el clic que sigue a un arrastre: soltar la carpeta donde la
  moviste no puede además cambiarte de carpeta.
- ⚠ **"Todas" no se puede mover**: es la bandeja, no un proyecto.
- ⚠ La ✕ está **invisible hasta pasar por encima**, y el número se esconde cuando
  aparece: si no, bailan las dos en el mismo lugar. Veinte carpetas con íconos fijos son
  cuarenta cosas compitiendo con el nombre, que es lo único que se viene a leer acá.

**La identidad visual de cada carpeta** (mismo día, pedido seguido): *"me gustaría poder
editar la identidad visual de cada carpeta, así como hacemos con casi todas las cosas en
este proyecto. Fijate cómo tenemos armado el de sesiones"*. Botón derecho encima de una
carpeta y sale el **mismo `#menuTarjeta`** de las tarjetitas, con sus mismos estilos:
seis tonos + rueda libre + sin color, dieciséis **íconos** (más los que agregue él) +
"el de siempre", cambiarle el nombre y sacarla.

- ⭐⭐ **La carpeta y su pastilla de arriba comparten identidad**, porque son el MISMO
  proyecto: el color usa la misma llave (`claveGrupo` → `g:<nombre>`) y el apodo el
  mismo `sesApodos`. Elegís el color una vez y aparece en los dos lados. Dos identidades
  para la misma cosa sería justo lo que confunde.
- ⚠ **El apodo es solo el RÓTULO.** `data-proy`, `irProyecto` y `proy` siguen usando el
  nombre real de la carpeta: renombrando la llave, la lista dejaría de encontrar sus
  conversaciones. La prueba lo fija entrando por el nombre real después de renombrar.
- ⚠⚠ **El color le gana a `.sel`** (va en el `style` del elemento), así que una carpeta
  pintada Y seleccionada perdía la marca de "estás parado acá". Se cuenta con una
  **barrita a la izquierda que no se pinta nunca** — la misma solución que el puntito
  del semáforo en las pestañas.
- ⚠ Con **ícono propio se pierde el 📂/📁**, que es lo que contaba si el proyecto tiene
  algo vivo. Ese estado pasa a un **puntito** al lado del nombre, que tampoco se pinta.
- ⭐ **Los íconos se pueden agregar** (pedido seguido: *"me gustaría poder agregar
  iconos"*). Al final de la fila hay un **＋ punteado** que abre un **buscador adentro
  del propio menú**: escribís "fuego" y aparece el 🔥. Lo que elegís queda **en el juego
  para todas las carpetas**, no solo para la que tenías abierta — van a
  `sesIconosPropios`. Botón derecho encima de uno tuyo lo saca del juego, y **las
  carpetas que ya lo usan lo conservan** (el ícono se guarda por su valor, no por su
  lugar en la lista): sacar una opción no puede cambiarte tres carpetas de golpe. Por
  eso mismo, el que la carpeta ya tiene puesto **siempre aparece en la fila** aunque no
  esté en el juego, o el menú diría "ninguno" mientras la carpeta luce uno.
  - ⭐⭐ **Nada de `prompt()`.** La primera versión abría el cartel del navegador
    ("localhost:8750 says…") y Martín lo vio y dijo ***"se ve muy feo esto"***. Un
    cartel gris del sistema arriba de todo, tapando media pantalla, canta que es un
    agregado. **Regla: en estas pantallas, lo que se pide se pide adentro de la
    pantalla.** (⚠ Quedan `prompt()` en "Cambiarle el nombre" y en "sumar carpeta" —
    misma fealdad, todavía sin cambiar.)
  - ⭐ Y el buscador no es solo estética: con el `prompt()` **había que saber el atajo de
    los emojis de Windows** (`Win` + `.`) para poder usar la función. El catálogo
    (`CATALOGO_ICONOS`, ~170 emojis con palabras **en criollo y con sinónimos** —
    "plata" y "guita" traen el 💰) convierte "agregar un ícono" en elegir de una grilla.
    Se busca sin tildes ni mayúsculas (`sinTildes`).
  - ⚠ **Lo que pegás va primero y marcado**, aunque no esté en el catálogo: si pegás un
    emoji y no pasa nada, es un callejón sin salida. Se distingue "buscó" de "pegó" con
    `/^[a-z0-9 ]+$/` sobre el texto ya sin tildes.
  - ⚠ Se corta con `Intl.Segmenter` (`primerSigno`), no con `[0]`: un ícono es UN signo,
    pero una bandera o una familia son varios códigos y cortarlas al medio deja un
    garabato. Un renglón entero adentro del cuadradito de 22 px descuadra la lista.
  - ⚠ La fila de íconos se repinta **sola**, sin rearmar el menú entero: rehacerlo le
    cierra al navegador el selector de color si está abierto (misma razón por la que el
    color se marca a mano). Y `esc()` de esta pantalla **no escapa comillas** — el ícono
    lo escribe él, así que el `data-ico` lleva `&quot;` a mano.
  - ⚠ Al escribir en la galería el menú **cambia de alto**, así que la posición se
    recalcula (`ubicar()`, con el `clientX/Y` guardado): abriéndolo abajo de todo, el
    menú se iba de la pantalla. Y el input **corta los eventos de teclado**
    (`stopPropagation`), o los atajos de una tecla de la pantalla se disparan mientras
    escribís. `Escape` y "← volver a los de siempre" vuelven a la fila sin cerrar el menú.
- ⚠ `ICONOS` a secas **ya existía** en esta pantalla (los del explorador de archivos,
  por tipo de archivo). El juego nuevo es `ICONOS_CARPETA`; se cazó con `node --check`
  sobre el `<script>` extraído, que es una forma barata de verificar el JS de adentro
  del HTML sin abrir el navegador.
- ⭐⭐ **El ícono, el color y el apodo viven en el SERVIDOR** (`ASPECTO_CARPETAS` →
  `aspecto_carpetas.json`, con `GET/POST /carpetas/aspecto`), y **viajan adentro de
  `/movil/sesiones`** igual que el orden. Ver *"Los íconos de las carpetas, iguales en
  todos lados"* más abajo. ⚠ Hasta el 2026-08-25 esto vivía en el `localStorage`
  (`sesTonos`, `sesApodos`, `sesIconos`, `sesIconosPropios`) con el argumento de que "el
  orden cambia qué se ve y el color es cómo se ve en esta pantalla". **Ese argumento estaba
  mal y Martín lo corrigió**: la identidad es del PROYECTO, no de la pantalla. El
  `localStorage` sigue existiendo como espejo para el primer cuadro y como respaldo.
- ⭐⭐ **El camino de vuelta está SIEMPRE a la vista**: un pie "Escondidas (n)" que se
  despliega y ofrece devolver cada una. Misma regla que el ⤡ de pantalla completa —
  una lista que se desarma sin poder rearmarse es una trampa, y acá ya pasó una vez
  (el explorador desaparecido por la llave vieja `sesArbolPlegado2`).
- ⚠ **Buscando por nombre se ven también las escondidas**: si escribís el nombre de una
  que sacaste y no aparece, parece que se borró de verdad.
- ⚠ Si sacás la carpeta donde estás parado, la bandeja vuelve a **Todas**: quedarse
  mirando una carpeta que ya no está en la lista no tiene con qué volver.
- ⚠ En medio de un arrastre **no se repinta** y **no se adopta el orden del servidor**
  (misma lección que las pestañas de arriba): el refresco de cada 20 s te sacaba el
  renglón que estás moviendo, o te pisaba el orden que estás armando.
- ⚠⚠ **No alcanza con no adoptar durante el arrastre** (2026-08-19): la respuesta que ya
  venía viajando cuando soltaste vuelve con el orden VIEJO y te deshace el cambio un rato
  después, sin motivo visible. Por eso `adoptarCarpetas(d, sello)`: una respuesta solo
  vale si salió en un momento **tranquilo** —nada cambiado desde entonces (`selloCarp`) y
  ningún cambio nuestro viajando (`escribiendoCarp`)—, y **el aviso al servidor va antes
  de repintar**, porque repintar sale a pedir la lista de nuevo. Salió a la luz armando lo
  mismo en el celular, donde el refresco es cada 3 s y por eso pasaba seguido.
- Prueba: `pruebas/ver_mover_carpetas.py` (54 chequeos). ⚠ Intercepta
  `/carpetas/orden`, `/carpetas/ocultar` y `/movil/sesiones`: corre sin reiniciar el
  panel y **sin tocarle a Martín el orden, las carpetas ni los colores de verdad**.
  Los tres chequeos que más valen son los del umbral: un clic quieto entra, un temblor
  de la mano de 2 px entra igual, y recién pasados los 5 px la carpeta se levanta.

### Lo mismo en el celular: mover y sacar carpetas del cajón (2026-08-19)

Pedido de Martín, apenas quedó hecho en la pantalla grande: *"¿y en el celu?"*. Vive en
`MOVIL_HTML` (dentro de `panel.py`), en el cajón ☰ de la vista de conversaciones.

- ⭐ **Es la misma función y los MISMOS datos**: el orden y las escondidas viven en el
  servidor y viajan adentro de `/movil/sesiones`, así que lo que acomodás en la compu ya
  está acomodado en el teléfono, y al revés. No hay un pedido aparte a propósito: esa
  respuesta es la que el teléfono tiene cacheada para dibujarse al instante.
- ⭐⭐ **El GESTO es distinto al de la compu, y eso no es una inconsistencia.** Allá
  alcanza con arrastrar porque el mouse no hace scroll; acá el dedo ya tiene ocupado el
  arrastre para recorrer el cajón. Entonces: **deslizar a la izquierda la saca** (el mismo
  gesto con el que se archiva una conversación, para no aprender dos cosas) y
  **mantenerla apretada la levanta** para moverla (`LARGO_MOVER`, 380 ms, con un golpecito
  de vibración que es el único aviso de que se levantó). La regla de fondo sí es la misma
  que en la compu: cuando dos gestos se pelean el mismo renglón, se separan por **cómo**
  se hacen, no partiendo el renglón en pedacitos.
- ⚠ **Hay una línea que cuenta los gestos** abajo de la lista (`.pista-carp`). En el
  teléfono no hay hover que los sugiera: sin el cartel, no existen.
- ⚠⚠ **El freno del clic (`movioCarpeta`) se limpia al EMPEZAR el toque, no al usarlo.**
  Con el dedo, un arrastre puede terminar sin que el navegador dispare ningún clic; el
  freno quedaba puesto y **se comía el próximo toque** — movías una carpeta, después
  tocabas otra y no entraba, sin nada que lo explicara.
- ⚠ Mientras está levantada se hace `preventDefault()` en `touchmove` (por eso ese
  listener va con `{passive:false}`): si no, la carpeta sube con el dedo y la lista se va
  para el otro lado al mismo tiempo.
- La carpeta levantada necesita **fondo propio** (`.tomada`): sin eso se ven las de abajo
  a través de ella y no se entiende cuál estás agarrando.
- ⭐ **Color e ícono ya se pueden editar acá** (2026-08-20): cada carpeta tiene un lápiz
  chico que abre una hoja desde abajo con los tonos, rueda libre y los íconos.
  El lápiz frena sus eventos táctiles para no levantar, deslizar ni abrir la carpeta por
  accidente. ⚠ **Desde el 2026-08-25 es la MISMA identidad que la compu** (antes cada
  pantalla guardaba la suya en su navegador, y con paletas distintas): mismos seis tonos
  —guardados por NOMBRE, no por hex—, mismos dieciséis íconos más los que Martín agregó
  con el ＋ allá, y el apodo se muestra acá también. Ver la sección de abajo.
- Prueba: `pruebas/ver_carpetas_movil.py` (ahora también cubre el editor visual). ⚠ Lee `MOVIL_HTML` del
  `panel.py` **del disco** y lo sirve ella misma: el panel corriendo tiene el HTML viejo
  en memoria hasta que se lo reinicie, así que sin esto la prueba mediría lo de ayer.
  Los gestos se arman a mano con `TouchEvent`: Playwright sabe tocar, no deslizar ni
  mantener apretado.

### Los íconos de las carpetas, iguales en todos lados (2026-08-25)

Pedido de Martín, textual: *"que no importa si abro desde el celular, la app de escritorio
o desde otro navegador, siempre tengan estos iconos, que estén unificados digamos. Porfa
no pierdas lo que ya tengo porque tardé mucho en ponerlos"*.

**El problema**: había DOS juegos de identidad visual y los dos vivían en el navegador —
`sesIconos` / `sesTonos` / `sesApodos` / `sesIconosPropios` en `/sesiones`, y
`movilAspectoCarpetas` en `MOVIL_HTML`—, **con paletas distintas** (dieciséis emojis acá,
otros dieciséis allá, siete colores sueltos que no existían del otro lado). Así, "el mismo
ícono en las dos pantallas" no era un descuido de sincronización: era **imposible de
elegir**. Y otra máquina, otro navegador o el teléfono arrancaban en cero.

- ⭐ **Fuente de verdad**: `aspecto_carpetas.json` (`ASPECTO_CARPETAS` en `app/rutas.py`),
  `{"carpetas": {nombre: {icono, color, apodo}}, "iconosPropios": [...], "choques": [...]}`.
  Se lee con `GET /carpetas/aspecto` y se escribe con `POST /carpetas/aspecto`.
- ⭐ **Viaja adentro de `/movil/sesiones`**, no como pedido aparte — misma razón que el
  orden: esa respuesta es la que las pantallas guardan para dibujarse al instante, y como
  pedido separado el primer pintado saldría sin íconos y aparecerían de golpe después.
- ⭐⭐ **Se manda SOLO el campo que tocaste** (`{carpeta, icono}`, no el objeto entero), y
  un campo en `""` lo borra. Con las dos pantallas abiertas a la vez, mandar el objeto
  completo significaría que cambiar el color en el celular te borre el ícono que acabás de
  poner en la compu.
- ⭐⭐ **El sembrado, que es la parte delicada**: `POST /carpetas/aspecto/sembrar` sube de
  una vez lo que ese navegador ya tenía. Tres reglas, las tres a propósito: **no pisa
  nunca** (lo ya guardado se respeta; sembrar es traer lo que falta), **lo que no coincide
  no se decide solo** (queda en `choques` para que Martín elija — así lo pidió: *"mostrame
  los choques primero"*), y **copia con fecha en `logs/aspecto_carpetas_<origen>_*.json`**
  antes de mezclar nada. Cada navegador siembra UNA vez (`sesAspectoSembrado` /
  `movilAspectoSembrado` en su `localStorage`).
- ⚠⚠ **Antes de sembrar, el cliente NO adopta las ausencias del servidor**, solo suma. Si
  no, el primer refresco de un navegador con íconos y un servidor vacío se los limpiaría
  — exactamente lo que Martín pidió que no pasara.
- ⚠⚠⚠ **Un 404 NO le hace saltar el `catch` a `fetch`**, y eso casi cuesta los íconos el
  mismo día. La primera versión hacía `try { await fetch(...) } catch { return }` y después
  marcaba la llave de "ya sembré": contra el panel **todavía sin reiniciar** —que no conoce
  el endpoint y contesta 404— la pantalla se anotaba como sembrada **sin haber subido
  nada**, no lo reintentaba nunca más y, con `aspectoCarpListo` en verdadero, el primer
  refresco le borraba los íconos de la pantalla. Se da por sembrado **solo si el servidor
  dijo que sí** (`r.ok` y `ok:true` en el cuerpo). Por eso las llaves llevan un 2
  (`sesAspectoSembrado2`, `movilAspectoSembrado2`): los navegadores que alcanzaron a
  marcarse mal tienen que volver a sembrar. Lo fija el paso 6 de
  `ver_iconos_carpetas_unificados.py`, que sirve 404 a propósito.
  **La lección general: cuando el cliente nuevo puede hablar con el servidor viejo —y acá
  siempre puede, porque el panel se reinicia a mano—, "no falló" no es lo mismo que "salió
  bien".**
- ⚠ **Los colores van por NOMBRE** (`azul`, `violeta`, …), no por hex: son los seis tonos
  de `/sesiones`, y así el que elegís en el celular queda marcado en la compu. La rueda
  libre sigue guardando hex, que las dos pantallas entienden. En el celular se traduce con
  `TONOS_CARP` (el tono claro de cada uno, que es el que sirve para el `color-mix`).
- ⚠ **`sesTonos` mezcla carpetas y conversaciones** (`g:<nombre>` contra el sid): al subir
  viajan solo las claves `g:`. Un color de conversación colándose como carpeta pintaría
  una carpeta que nadie pintó.
- ⚠ El apodo sigue siendo **solo el rótulo**: la llave es el nombre real de la carpeta.
- Pruebas: `pruebas/probar_aspecto_carpetas.py` (25 chequeos del backend, sin navegador) y
  `pruebas/ver_iconos_carpetas_unificados.py` (las dos pantallas de verdad contra el
  backend de verdad: la compu siembra → el celular lo ve → cambia algo → otra compu recién
  abierta lo ve → un navegador viejo no pisa y queda el choque anotado). Las dos apuntan
  el archivo a un temporal: no tocan el de Martín. `ver_mover_carpetas.py` y
  `ver_carpetas_movil.py` también cubren ahora que cada cambio suba al servidor.

### El navegador de cada carpeta (2026-08-28)

Pedido de Martín: que una sesión del panel pueda probar una web como hace Codex — abrir la
página, hacer clic, escribir, mirar qué pasó y contarlo. Claude Code lo trae adentro
(`--chrome` + las herramientas `mcp__claude-in-chrome__*`), y maneja el Chrome **de
verdad**, con las sesiones ya logueadas.

En pantalla es **un renglón más de la identidad de la carpeta**: un selector con los
perfiles de Chrome del disco (`GET /carpetas/navegadores`) y un campo de sitios
permitidos. Vive en el menú de botón derecho de `/sesiones` y en la hoja del lapicito del
celular, y se guarda con el **mismo** `POST /carpetas/aspecto` que el ícono y el color.

- ⭐⭐ **La carpeta ES el interruptor.** Sin perfil declarado, esa carpeta no abre páginas;
  con perfil, TODAS sus conversaciones pueden. **No hay perilla por conversación** a
  propósito: es como lo hace Codex, que nunca te hace prender nada (sus plugins están
  siempre disponibles y el modelo los usa cuando hacen falta).
- ⭐⭐ **Y hay un navegador POR DEFECTO que heredan las carpetas que no dicen nada**
  (2026-08-28, pedido de Martín: *"¿y para todos los proyectos?"*). Sin eso había que
  marcar las 23 carpetas a mano y **cada carpeta nueva nacía sin navegador**, o sea que el
  problema volvía solo. Vive en `defecto` dentro del mismo `aspecto_carpetas.json` y se
  elige desde el mismo menú ("Y para todos los proyectos").
  ⚠⚠ Son **tres** estados, no dos: la carpeta puede traer otro perfil (lo pisa), puede
  traer `ninguno` (lo apaga solo ahí) o puede no traer nada (hereda). El apagado necesita
  una palabra propia porque **vacío ya significaba "no dije nada"**. Los `sitios` se
  heredan por separado: una carpeta puede quedarse con el navegador de base y apretarle el
  candado solo a ella.
  ⚠⚠ **Un panel viejo BORRA el `defecto` sin decir nada.** Pasó el mismo día que se armó:
  `_aspecto_carpetas()` rearma el archivo a partir de las llaves que conoce, así que un
  panel que todavía no fue reiniciado lee el archivo, no ve `defecto`, y al guardar
  cualquier otra cosa lo escribe sin esa llave. Es la misma familia que el 404 de los
  íconos: cliente nuevo hablando con servidor viejo. **Después de tocar este archivo hay
  que reiniciar el panel antes de configurar nada desde la pantalla**, o el primer cambio
  de color te borra el navegador de base.
  ⚠ Las dos pantallas hacen la MISMA cuenta que el lanzador (`navegEfectivo()` acá,
  `navegador_de()` allá): si se separan, la pantalla miente sobre con qué va a trabajar.
  Por eso la marca 🌐 y el aviso del menú miran el navegador **efectivo**, no el declarado
  — casi ninguna carpeta declara el suyo.
- ⭐ **La contención de verdad es el perfil**, no una lista de reglas: si el Chrome de un
  proyecto solo tiene ese proyecto logueado, el daño posible ya está acotado por construcción.
  Por eso el selector **avisa** cuál es el Chrome personal ("todas tus cuentas").
- ⭐⭐ **El perfil es la frontera entre trabajos, y esa frontera no se cruza.** Si tenés un
  Chrome por trabajo (perfiles **internos** de tu Chrome personal), cada carpeta usa el del
  trabajo al que pertenece, decidido por vos y no adivinado por el nombre de la carpeta. Las
  carpetas que no dicen nada heredan el de base.
  ⚠ Por eso el **navegador de base es `chrome-prueba`**, el perfil aislado, y no el
  personal: una carpeta nueva puede probar cosas, pero no nace con las manos sobre tus
  cuentas.
- ⚠⚠⚠ **Un perfil dedicado NO aísla nada si le iniciás sesión de Google.** Pasó el mismo
  día que se armó el primero: la sincronización le trajo las extensiones (por eso la Web
  Store decía "Instalados" antes de instalar nada), 27 KB de marcadores, 25 MB de
  historial, la base de autocompletado y 190 KB de contraseñas guardadas. O sea que el
  perfil "dedicado" era el personal con otro nombre, y con él se cae el argumento entero de
  arriba. **Un perfil para un cliente se crea sin loguearse en Chrome** (la extensión de la
  Web Store se instala igual estando deslogueado; la cuenta que sí hace falta es la de
  Claude) y después se inicia sesión únicamente en el sitio de ese cliente.
- ⭐⭐ **Cómo sabe una sesión CUÁL de los navegadores conectados es el suyo.** El puente no
  habla de perfiles: habla de identificadores ("Browser 1", "Browser 2" y un uuid). Con dos
  Chrome prendidos —y siempre hay dos, porque uno es el de todos los días— la sesión no
  tenía forma de elegir y terminaba **preguntando**; elegir mal ahí es trabajar sobre el
  Chrome que tiene el banco abierto. La salida no cuesta un token: la extensión guarda ese
  identificador **adentro del perfil**, en su almacenamiento local, con la llave
  `bridgeDeviceId`. `id_navegador_de()` lo lee del disco y la sesión arranca con la orden de
  usar ese y ningún otro. Comprobado contra los dos perfiles: los ids leídos del disco son
  exactamente los que devolvió `list_connected_browsers`.
  ⭐ Efecto de regalo: **ya no importa si el identificador cambia** al reinstalar Chrome —
  se relee en cada arranque y entra en la firma que decide si el proceso se rearranca. El
  riesgo de "identidad inestable" que se anotó al planear esto quedó neutralizado.
  ⚠ Si ese perfil todavía no conectó su extensión, la sesión **avisa en vez de adivinar**:
  agarrar otro navegador sería exactamente el accidente que esto evita.
- ⭐⭐ **La ventana de Chrome se abre RECIÉN cuando la sesión la usa** (2026-08-29, queja
  suya: *"¿por qué cada vez que entro en una nueva sesión de otro proyecto se me abre un
  navegador?"*). Y era exactamente lo que hacía: como el navegador de base lo hereda todo,
  ninguna carpeta se quedó sin navegador, así que `_arrancar_viva` abría un Chrome en cada
  charla de cada proyecto **por las dudas**. Ahora la abre `_asegurar_chrome()` en la
  primera herramienta del navegador que la sesión de verdad pide: una charla donde nunca
  navega no muestra ninguna ventana.
  ⚠ **Lo que hubo que resignar para tenerlo**: el atajo de permitir el servidor entero
  (`mcp__claude-in-chrome` en `--allowedTools`) **se sacó**. Con él no había ningún pedido
  de permiso, o sea ningún momento donde enterarse de que la sesión iba a navegar. Ahora
  **toda** herramienta de Chrome pasa por el portero de `_turno` — que ya era el camino de
  las carpetas con lista de sitios — y sin lista se concede sola. Cuesta un ida y vuelta
  local por acción, invisible al lado de un clic real.
  ⚠⚠ **Y sacarlo del allowlist NO alcanzaba: son DOS piezas.** El CLI concede por su
  cuenta las herramientas que considera de lectura — medido contra el CLI real con
  `pruebas/sonda_portero_chrome.py`: `list_connected_browsers` se ejecutó **sin pedir
  ningún permiso**. Con eso, una sesión que arranca preguntando qué navegadores hay se
  habría encontrado con los ajenos y el suyo cerrado, y ninguna prueba gratis lo podía
  ver, porque el que decide es el CLI. La segunda pieza es `AJUSTES_CHROME`
  (`{"permissions": {"ask": ["mcp__claude-in-chrome"]}}`) pasado por `--settings`: con eso
  no queda ninguna afuera. Si alguna vez hay que tocar esto, correr la sonda — es lo único
  que mide al que decide.
  ⚠ La ventana se abre **antes** de conceder el permiso y **solo si** el dominio pasa: si
  se abriera después, la sesión preguntaría por los navegadores conectados con el Chrome
  todavía arrancando y se rendiría; y un pedido prohibido no tiene por qué dejar una
  ventana abierta al pedo.
  ⚠ El `bridgeDeviceId` se lee del disco **con el Chrome cerrado** y eso anda: la extensión
  lo dejó escrito la primera vez que ese perfil se abrió. Un perfil que nunca se estrenó no
  tiene id, el prompt lo dice en vez de adivinar, y cuando la extensión lo escriba la firma
  cambia y el proceso se rearranca solo con la línea correcta.
- ⚠⚠ **El guardado NO usa `anotarCarpetas`.** Ese se come los errores con un `catch` vacío,
  y acá el servidor **puede decir que no** (un perfil que ya no existe, o un panel viejo que
  contesta 404 sin conocer el campo). Un permiso guardado a medias y en silencio es peor que
  uno que falla fuerte: es la misma lección que casi cuesta los íconos el 2026-08-25. La
  pantalla escribe "No se guardó: …" abajo del selector.
- ⚠ **El perfil NO se espeja en el `localStorage`**, a diferencia del ícono y el color. No
  se dibuja en el primer cuadro, y un teléfono con el dato viejo se lo podría **sembrar** de
  vuelta al servidor: que un perfil de Chrome reaparezca solo porque quedó guardado en un
  navegador es exactamente lo que no queremos. `guardarAspectoCarp()` del celular lo saca
  antes de escribir.
- ⚠ El que está puesto **siempre aparece en la lista**, aunque el disco ya no lo tenga
  ("no lo encuentro"): si no, el menú diría "sin navegador" mientras la carpeta tiene uno.
  Misma regla que el ícono que la carpeta usa y ya no está en el juego.
- La marca de la fila (🌐) va **apagada y nunca en rojo**: tener navegador es un estado
  normal, no un problema.
- Pruebas: `pruebas/ver_navegador_carpeta.py` (17 chequeos, las dos pantallas contra el
  backend de verdad, incluido el caso del panel que contesta 404) y
  `pruebas/probar_navegador_carpeta.py` (64 del lanzamiento y del portero, con `--mutar`:
  14 defectos repuestos, los 14 cazados — entre ellos volver a abrir el Chrome al arrancar,
  abrirlo en cada pedido, no abrirlo nunca, abrirlo antes de mirar el dominio y dejar que
  el CLI conceda solo las de lectura) y `pruebas/sonda_portero_chrome.py` (contra el CLI de
  verdad; **gasta tokens**, se corre a mano, y con `--sin-ask` tiene que fallar). ⚠ Las de
  carpetas que ya existían (`ver_mover_carpetas`, `ver_carpetas_movil`,
  `ver_iconos_carpetas_unificados`) tuvieron que **interceptar `/carpetas/navegadores`**: sin
  eso el pedido se les escapaba al panel de verdad y lo cazaba su chequeo final.

### El rastro: ver lo que la sesión HACE mientras trabaja (2026-08-28)

Pedido de Martín: *"me gustaría ir viendo cómo razona"*. En el hilo aparece ahora un
renglón por cada herramienta que usa, en criollo y en vivo: "entró a tal dirección", "hizo
clic", "escribió «REGUERA»", "miró la pantalla", "leyó la consola", "corrió tal comando".

- ⛔⛔ **El pensamiento NO se puede mostrar, y no es que lo filtremos.** Claude Code lo tapa
  en las dos puntas: en el `.jsonl` el bloque `thinking` queda con **cero letras** y sólo
  su firma, y por el chorro en vivo llega igual de vacío (probado el 2026-08-28 forzando
  esfuerzo alto: llegó el bloque, sin nada adentro). El rastro es lo que hay, y en la
  práctica alcanza — con esto en pantalla, los nueve clics a ciegas de aquella
  charla se veían pasar en vez de intuirse.
- ⚠⚠ **El recorte del hilo cuenta lo HABLADO, no los pasos** (`_ultimos_mensajes`). Un
  solo turno puede usar sesenta herramientas: contándolas, el tope de 40 se llenaba de
  rastro y la conversación —lo único que uno viene a leer— se caía por arriba. Los pasos
  viajan de arriba, pegados a lo que se dijo.
- El paso va **apagado, sin burbuja y con una rayita a la izquierda**: no es algo que dijo,
  es el detalle de abajo. Nunca en rojo.
- `TodoWrite` y `AskUserQuestion` **no** generan paso: ya se dibujan como tarjeta y como
  botones, y repetirlos sería ruido.
- ⭐ **El color se elige** (pedido de Martín el mismo día): fila "Color del rastro" en el
  🎨, con seis opciones más la rueda libre. `tema` —el de fábrica— apaga el acento contra
  el fondo, o sea que sigue lo que ya elegiste; cualquier otro valor lo pisa. Sale del
  mismo `aspecto.js` que la tipografía y el fondo, y las dos pantallas lo toman por
  `var(--rastro)`, `var(--rastro-bg)` y `var(--rastro-borde)`.
  ⚠⚠ Los colores del rastro estaban **escritos a mano** en las dos pantallas y por eso no
  seguían el tema: eso era un defecto, no una decisión. Si mañana se agrega otra pieza al
  hilo, va con variables desde el principio.
  ⚠ Y como avisa el encabezado de `aspecto.js`: **el campo nuevo hay que sumarlo también a
  la lista blanca de `/aspecto` en `panel.py`**, o se guarda en ese navegador y no viaja a
  ningún otro. Hasta que el panel se reinicie, el servidor lo descarta en silencio.
- Prueba: `pruebas/probar_rastro_pasos.py` (22 chequeos, con `--mutar`). La mutación que
  más importa es la del recorte, porque es la que rompe la pantalla en silencio.

### El explorador de archivos de `/sesiones` (2026-08-17)

Pedido de Martín: *"quiero el explorador de archivos del proyecto al lateral izquierdo,
como Visual Studio"*. La columna izquierda de `/sesiones` tiene ahora **dos pisos**:
arriba los proyectos de siempre (la referencia Gmail) y abajo el **árbol de archivos**
de la carpeta donde estás parado. Tocás un archivo y se lee a la derecha.

- ⭐ **Es de MIRAR: no edita, no borra, no mueve nada.** No hay una sola ruta que
  escriba. Para cambiar un archivo está la conversación, que sabe lo que hace.
- ⭐ **La única llave del backend es la carpeta raíz** (`_arbol_raiz()` en `panel.py`):
  se abre solo un proyecto que el panel YA conoce (tiene transcripciones de Claude Code,
  o está en `carpetas_sesiones.json`), y todo lo de adentro se compara **después de
  `resolve()`**, así que ni un `..` ni un enlace simbólico salen de ahí. Sin eso, esto
  sería "leé cualquier archivo del disco" por una dirección, y el panel se publica por
  Tailscale.
- **Los hijos de una carpeta se piden recién al abrirla** (`GET /archivos/lista`): un
  proyecto real tiene miles de archivos. Rutas: `/archivos/lista`, `/archivos/ver`
  (texto/imagen/binario/pesado, con tope de 400 kB de texto) y `/archivos/crudo` (solo
  imágenes).
- Un `.md` se muestra **dibujado** con `marcado.js` y hay un botón para verlo tal cual;
  el resto va con números de renglón en columna aparte (adentro del texto se copiarían).
- El ancho de la columna se arrastra del borde (`--lat`) y el explorador se pliega; las
  dos cosas se acuerdan en el `localStorage` (`sesLatAncho`, `sesArbolPlegado`).
- **`Ctrl+B` esconde la COLUMNA ENTERA** (proyectos + archivos), como en VS Code, y la
  conversación se queda con toda la pantalla. Vuelve con el mismo atajo o con el **◧** de
  la barra de arriba, que está siempre a la vista — escondida no habría con qué traerla
  de vuelta. El ▾ de la cabecera del explorador es otra cosa y sigue igual: pliega solo
  el árbol y deja los proyectos. Anda con el cursor adentro de una caja de texto (en un
  campo pelado Ctrl+B no hace nada propio). ⚠ Se exige Ctrl **sin** Shift ni Alt:
  Ctrl+Shift+B es del navegador.
- ⭐ **En "Todas" el árbol NO se vacía**: se queda con la última carpeta que miraste
  (`sesArbolCwd`), como VS Code. Antes quedaba un cartelito justo en la pantalla donde
  Martín más para, y el explorador parecía no existir.
- ⚠⚠ **La llave del plegado es `sesArbolPlegado2`, con el 2.** La primera versión de
  Ctrl+B plegaba este panel, así que a quien lo probó le quedó guardado "plegado" para
  siempre: el explorador desaparecido y sin pista de por qué (le pasó a Martín el mismo
  día). Cambiarle el nombre a la llave los devuelve a todos a "abierto" una sola vez.
  **Lección: si un atajo cambia de significado, la marca que dejó en el navegador queda,
  y el usuario se come el estado viejo del atajo viejo.**
- ⚠ El título de la cabecera dice siempre **"Archivos · proyecto"**, no solo el proyecto:
  plegada, esa tira decía "▸ wpp-transcriptor" y no había forma de saber que ahí adentro
  estaban los archivos (misma regla que los dos botoncitos de la pizarra).
- ⚠⚠ Esconder la columna va con **`grid-template-columns:1fr`**, no con `0 1fr`: con el
  `<aside>` en `display:none` deja de ser hijo de la grilla y la conversación se acomoda
  sola en la PRIMERA pista — la de ancho cero. O sea, la pantalla quedaba en blanco. Lo
  cazó `ver_arbol_archivos.py` midiendo el ancho, no el ojo.
- ⚠ **Mientras mirás un archivo, `pintarSesion()` sale sin hacer nada**: el repintado de
  cada 3 s te tapaba el archivo con la conversación. Y al mandar un mensaje el archivo se
  cierra solo, o la pantalla volvía a él en el siguiente repintado.
- Pruebas: `pruebas/probar_arbol_archivos.py` (34 chequeos, llama a las funciones de
  `panel.py` sin levantar el servidor) y `pruebas/ver_arbol_archivos.py` (23 en
  navegador, con el servidor entero inventado — corre sin reiniciar el panel).

### La barra de arriba de `/sesiones`: DOS filas (2026-08-18)

Martín: *"no me gusta que las sesiones ocupen el mismo lugar que las pestañas, se me hace
incómodo trabajar así. Que las pestañas estén arriba"*. ⚠ En su vocabulario **"pestañas"
son las PANTALLAS del panel** (Panel, Sesiones, Pizarra…) y **"sesiones" son las
conversaciones abiertas**; en el código es al revés (`.tab` es una charla). Confundirlos es
hacer justo lo contrario de lo que pidió.

    fila 1 (#barraArriba)   ◧   👁   …   Panel · Sesiones · Pizarra · Estudio · Avisos
    fila 2 (#barra)         las conversaciones, a TODO lo ancho

- Antes compartían renglón y el menú se comía ~700 px justo del lado donde las
  conversaciones crecen. **Las pestañas siguen agrupadas por proyecto** (pastillas que se
  pliegan), que es lo otro que mantiene corta esa fila.
- ⭐ **Cada tarjetita se pinta, se le cambia la FORMA y se renombra**, la del proyecto y la
  de la charla (botón derecho encima). El color vive en `sesTonos`, la forma en `sesFormas`
  y el apodo del proyecto en `sesApodos`, los tres locales.
  ⚠⚠ **Color y forma tienen granularidad distinta, y no es un descuido**: el color es de
  ESA tarjeta (para distinguir una de otra) y la forma vale para **todas las de su clase**
  (es cómo se ven las de proyecto o las de conversación). El rótulo del menú lo dice, o uno
  elige una forma creyendo que pinta una sola y se le mueven todas.
  **Nueve figuras**: redondeada (la de siempre), cuadrada, píldora, pestaña, hoja, arco,
  cortada, flecha y cinta. Cada una se escribe UNA vez para los dos tipos (el selector
  nombra a la pestaña y a la pastilla juntas), o serían dieciocho reglas casi iguales.
  ⚠ Pestaña, cortada y flecha se dibujan con `clip-path`, que **corta el borde**: la
  silueta la hace el FONDO, y por eso en esos modos el fondo va más claro que la barra —
  con el de siempre no se distinguían de la redondeada (visto en captura).
  ⚠ El menú tiene ancho fijo (252 px): con nueve figuras se estiraba media pantalla y
  quedaba cortado contra el borde.
- ⭐ **Y cualquier color con la rueda**, no solo los seis tonos: se guarda el `#rrggbb` y de
  ahí salen los tres tonos de la tarjeta (fondo teñido, borde medio, texto vivo). ⚠ Si el
  color elegido es oscuro, **el texto se aclara solo** o queda letra negra sobre negro.
  Como en el 🎨: se aplica en el `input` y se guarda en el `change`.
  ⚠ El apodo es **solo el rótulo de la pastilla**: la carpeta del disco no se toca y
  `grupoDe`/`grupoAbierto` siguen usando el nombre real como llave.
  ⚠ El color va en el `style` del elemento, así que le gana al fondo del semáforo: **el
  estado queda contado por el PUNTITO**, que no se pinta nunca. Los tonos son apagados y
  ninguno es el verde/amarillo/rojo del semáforo. La prueba lo verifica.
  ⭐ El color se aplica en el acto y **sin cerrar el menú** (probar tres tonos son tres
  clics, no doce): por eso el menú se repinta a mano, porque después de `pintarTabs()` el
  elemento que tocaste ya no existe.
  Prueba: `pruebas/ver_tarjetas.py` (17 chequeos).
- ⭐ **La pastilla ABRAZA a sus charlas** (`#abrazo`), como los grupos de pestañas de
  Chrome: un marco redondeado que va de la pastilla a su última conversación. ⚠⚠ Es un div
  **dibujado detrás**, no un contenedor: meter las pestañas adentro de un `<div>` rompería
  el arrastre, que mueve NODOS con `insertBefore` sobre `#tabs` y recorre el grupo con
  `nextElementSibling`. Así el DOM queda plano; lo único que hay que recordar es llamar a
  `acomodarAbrazo()` después de cada pintado y dentro de `deslizando()`. Va **primera** en
  `#tabs` (al final rompía "el ＋ es el último de la fila") y se mide con `offsetLeft`,
  no con `getBoundingClientRect`, para no descolocarse con la fila corrida.
- **El menú ya no se achica** acá: `menu.js` solo cede lugar cuando comparte renglón con
  alguien marcado `data-menu-rival`, y desde esta separación no lo usa ninguna pantalla.
  El mecanismo (completo → iconos → un botón) queda en `menu.js` por si alguna vuelve a
  compartir fila. ⚠⚠ Se intentó que se achicara TAMBIÉN estando solo, midiendo lo que le
  dejan sus hermanos en la fila: **no funciona** y se revirtió — en varias cabeceras hay
  hermanos elásticos (`flex:1`) que se llevan todo el sobrante, así que la cuenta veía cero
  lugar y guardaba el menú en una pantalla de 1500 px (le pasó al Estudio).
- ⚠ Lo que sí quedó de ese intento, porque era un bug de verdad: `medir()` saca el menú del
  renglón (`position:absolute` + `width:max-content`) antes de medirlo. Quieto en su lugar,
  `offsetWidth` devuelve lo que OCUPA y no lo que NECESITA: envuelto en dos líneas medía 562
  en vez de 700, y como el resultado se cachea para siempre, una medición mal hecha dejaba
  el menú roto toda la sesión.
- Prueba: `pruebas/ver_barra_dos_filas.py` (11 chequeos).

### Esconder las barras de arriba: un botón por cosa (2026-08-18)

A la izquierda de la fila de arriba hay cuatro interruptores, todos de un toque:

    ◧  la columna izquierda (y Ctrl+B)      ▭  ESTA barra, entera
    ⧉  la fila de conversaciones            ⤢  las dos barras juntas, pantalla completa

Se guardan en `sesVer` (▭ y ⧉), `sesPleno` (⤢) y `sesLateralOculto` (◧). El ⧉ queda tenue
**pero sigue estando** cuando su fila está escondida: es con lo que se vuelve.

- ⚠⚠ **Lección de producto, y salió cara — llevó cuatro vueltas**:
  1. *"me gustaría poder ocultar cada sección individualmente"* → se hizo un menú 👁 con una
     tilde por franja. Lo rechazó apenas lo vio: *"no me convence"*.
  2. *"quiero un botón simple para ocultar ambas, así tengo la pantalla del chat completa"*
     → el ⤢.
  3. *"un botón para cada una individualmente"* → un botón por barra.
  4. *"no me convence ese botón de hamburguesa, yo quiero que se oculte la barra entera, no
     solo las pestañas"* → el que escondía las pastillas del menú ahora se lleva **la fila
     entera, con sus propios botones adentro**, y dejó de ser un ☰.
  Dos cosas para llevarse: **lo que no quería era ELEGIR EN UN MENÚ** (el menú y los botones
  ofrecían exactamente lo mismo; la diferencia son los gestos que cuesta el resultado y que
  un botón a la vista se descubre solo), y **esconder algo es devolver EL LUGAR que ocupaba**
  — media barra vacía con los controles adentro no es esconderla. La hamburguesa además
  jugaba en contra: ☰ quiere decir "abrir un menú", justo lo contrario.
- ⭐⭐ **Escondida la fila de arriba (con el ▭ o con el ⤢) se van TODOS los botones**: por eso
  aparece el **⤡ flotando** sobre la charla, arriba a la derecha. Es el único camino de
  vuelta, así que está SIEMPRE visible — nada de "aparece al pasar el mouse": quien no sepa
  que está no lo encuentra nunca. `Esc` hace lo mismo, para el que ya lo sabe. Una pantalla
  que se desarma sin poder rearmarse es una trampa, y acá ya pasó una vez (el explorador
  desaparecido por una llave vieja, `sesArbolPlegado2`).
- ⭐ **El ⤡ devuelve la barra de arriba y sale de pantalla completa, pero NO toca la fila de
  conversaciones**: si la escondiste vos con el ⧉, es porque la querés escondida. Vuelve lo
  necesario para tener botones otra vez y el resto lo decidís desde ahí.
- **La columna izquierda es otra cosa** y sigue con lo suyo (◧ y Ctrl+B): las dos se llevan
  bien y juntas dejan la charla sola en la pantalla. El ▾ del explorador **pliega** el
  árbol, tampoco es lo mismo.
- ⚠ Al arrancar se limpia lo que hubiera quedado guardado del menú 👁 (`sesFranjas`): se
  respeta solo lo de la columna y **el resto vuelve a la vista**. Lo que se borra tiene que
  dejar todo visible, nunca escondido, o quedaría media pantalla apagada por un botón que
  ya no existe.
- Prueba: `pruebas/ver_pantalla_completa.py` (20 chequeos). ⚠ Ahí adentro: para saber si el
  ⤡ se ve **no sirve `offsetParent`** — con `position:fixed` siempre da null y el botón
  figuraba escondido estando a la vista.

### Los dos botones de cada bloque de código (2026-08-18)

Pedido de Martín señalando la esquina de un bloque: *"dos botones, uno para correr en
PowerShell el comando y otro para copiar el texto, tal y como se puede hacer con Claude
Code"*. Los dibuja `marcado.js`, así que aparecen en **todas** las pantallas que muestran
markdown (sesiones, celular, el visor de archivos).

- **📋 copia** el comando tal cual, con sus saltos de línea.
- **▶ corre** el bloque en una **ventana nueva y visible** de PowerShell (`-NoExit`): casi
  todo lo que se corre así es levantar un servidor o un script largo, y escondido no se
  vería ni el error ni la dirección que imprime. Arranca parado en la carpeta de la
  conversación abierta (`window.MD_CWD`).
- ⚠⚠ **Pide dos toques**: el primero cambia el botón a "▶ ¿corro esto?" y se cae solo a los
  4 s. Esto ejecuta lo que diga el bloque en la máquina de Martín; un clic de más no puede
  alcanzar. Todo lo que se corre queda en `logs/correr.log`.
- ⚠ El script viaja en **`-EncodedCommand`** (base64 de UTF-16LE), no como texto en la línea
  de comando: así un comando de varios renglones, con comillas o tildes, llega tal cual. Con
  `-Command` a secas los saltos de línea y las comillas se rompen de maneras difíciles de ver.
- ⚠ **Un solo escucha delegado en `document`** para todos los bloques: el hilo se rearma
  cada 3 s y engancharlos uno por uno obligaría a re-engancharlos en cada repintado y en
  cada pantalla.
- ⚠ Al leerlo de vuelta, el portapapeles de Windows devuelve `\r\n` — es del sistema, no de
  lo que se copió (piedra de la prueba, no del producto).
- Prueba: `pruebas/ver_botones_codigo.py` (13 chequeos). **Correr de verdad no se prueba
  apretando**: se intercepta el pedido, o abriría una ventana con lo que diga el bloque.

### El borrador de cada conversación (2026-08-18)

Pedido de Martín: *"quiero que lo que yo escriba dentro de una sesión quede guardado como
borrador y se pueda ver en todas, con una señalización que diga que está en borrador, que
tenga un color y una animación"* (señalando la bandeja de **Todas**). Es el borrador del
correo: escribís media frase, te vas, y la conversación queda marcada hasta que la mandes.

    escribís en /sesiones  →  se guarda solo  →  la bandeja muestra  ✎ Borrador  + lo escrito
    volvés a entrar        →  la caja te devuelve el texto ENTERO

- ⭐ **Vive en el SERVIDOR** (`BORRADORES_SESIONES` → `borradores_sesiones.json`), como las
  marcas y el modelo: es la MISMA conversación en la compu y en el teléfono, así que lo que
  empezaste a escribir en una pantalla tiene que estar en la otra. La copia del
  `localStorage` (`sesBorradores` / `movilBorradores`) es solo para que la chapa aparezca en
  el acto mientras escribís.
- ⚠⚠ **El color es LAVANDA y no toca el semáforo.** Verde, amarillo y rojo dicen en qué anda
  la CONVERSACIÓN (te espera, trabaja, falló); un borrador no es un estado de ella, es algo
  tuyo a medio escribir. Por eso va como **chapa al lado del título** y no pintando la fila:
  el borde izquierdo lo sigue mandando el semáforo, que es el idioma de esta pantalla.
- ⚠ La animación es **un respiro lento de 2,6 s** (el aro de la chapa) más la plumita
  latiendo: la bandeja puede tener veinte borradores y veinte parpadeos rápidos serían una
  calesita. La prueba mide el **color y la animación computados**, no la clase.
- ⚠ **Vacío BORRA la entrada, no guarda una cadena vacía** (`_guardar_borrador`): si no,
  toda conversación en la que alguna vez escribiste algo se quedaba con la chapa puesta
  para siempre. Y del lado de la pantalla, vacío se guarda como `''` —que quiere decir "de
  ésta sabemos que no tiene"—, porque si se borraba la entrada caía al anticipo que trae la
  lista, que todavía es el viejo, y la chapa no se apagaba.
- ⚠ **En la lista viaja un ANTICIPO de 120 letras, no el texto entero**: esa lista se guarda
  en el navegador para que la pantalla aparezca dibujada. El texto completo lo devuelve
  `GET /movil/borradores`, que va aparte justamente porque la lista está topeada (20
  proyectos, 20 charlas, último mes) y un borrador viejo tiene que poder recuperarse igual.
  **A la caja de escribir nunca se le devuelve el anticipo**: sería comerse la mitad de lo
  que escribiste sin avisar.
- ⚠ Se guarda con un **respiro de 700 ms** (no en cada tecla) y se manda ya al cambiar de
  conversación, al cerrar la pestaña y en `pagehide`/`visibilitychange`, con `keepalive`
  para que el pedido llegue aunque te estés yendo.
- ⚠⚠ El borrador de la conversación que estás **mirando** no lo pisa nunca la respuesta del
  servidor: ese lo estás escribiendo vos ahora mismo. Solo se devuelve a la caja si está
  **vacía** (el caso "lo escribí en el celular y entro por la compu").
- **Mandar el mensaje lo borra en el servidor**, adentro de `/movil/mandar`: así mandar
  desde el celular también le apaga la chapa a la compu.
- Las charlas **sin estrenar** (`nueva-…`) guardan su borrador solo en ese navegador: el id
  es provisorio y no significa nada en otra pantalla. Cerrar esa pestaña lo limpia.
- Está en las **dos** pantallas (`/sesiones` y la app del celular), con la misma chapa y el
  mismo color, y también en las pestañas de arriba (la ✎ chiquita) y en la pastilla de un
  proyecto plegado, para que un borrador no desaparezca al plegar el grupo.
- Pruebas: `pruebas/probar_borradores.py` (24 chequeos, backend con un archivo temporal) y
  `pruebas/ver_borradores.py` (24 en navegador, las dos pantallas). ⚠ La del navegador
  **inventa el servidor de borradores** y le sirve el `MOVIL_HTML` del disco interceptando
  `/movil`: es la única forma de probar el celular sin reiniciar el panel. Y le tapa
  `/movil/pestanas`, que vive en el servidor, para no moverle las pestañas del teléfono.

### El modelo de cada sesión, compactar, y el aviso de cuánto arrastra (2026-08-18)

Salió de una investigación, no de un capricho: Martín preguntó *"qué puede estar generando
un drenaje absurdo de tokens"* y el culpable era **una sola perilla de su configuración
global de Claude Code: `"model": "opus[1m]"`**, la ventana de un millón. Con esa ventana la
charla no se compacta nunca, así que **cada comando y cada edición vuelve a leer la
conversación entera**. Medido sobre sus propios `.jsonl`: una sesión de esa madrugada se
comió **286 millones de tokens en 675 llamadas** con apenas 71 mensajes suyos y un pico de
**997 mil de contexto**; el proyecto entero, **1.640 millones en un día**. De ahí los tres
pedidos: elegir el modelo por sesión, poder compactar, y que avise cuándo conviene.

Hay tres controles nuevos, en la caja de escribir de `/sesiones` y en la barra del chat del
panel: **el selector de modelo**, **el chip de contexto** y **⇲ Compactar**.

- ⭐ **El modelo vive en el SERVIDOR** (`ajustes_sesiones.json`, una entrada por sesión más
  la de `"laura"`), no en el navegador: lo usa quien LANZA el proceso `claude`, no la
  pantalla. Elegido en la compu, el celular lo respeta solo.
- ⚠ **`--model` va SIEMPRE, aunque sea el de fábrica.** Sin él manda el `model` del
  settings global, que es justo el `opus[1m]` que se quería dejar de heredar.
- ⭐ El selector **se pinta solo cuando NO está en el de fábrica**: lo que hay que ver de un
  vistazo es "esta sesión corre con algo distinto", no el estado normal.
- ⚠⚠ **`/compact` NO se puede pedir desde afuera.** Probado el 2026-08-18:
  `echo /compact | claude -p --resume <id>` devuelve vacío, **cero turnos y cero tokens** —
  el CLI lo ignora. Así que compactar es a mano y son **dos turnos**: se le pide a la sesión
  vieja que resuma en qué anda y con ese resumen se **arranca una nueva** en la misma
  carpeta (`PEDIDO_RESUMEN` y `SIEMBRA` en `sesiones_movil.py`). **La vieja no se toca ni se
  borra**: queda entera y se puede volver a abrir.
- ⚠ Compactar **pide dos toques**, como el ▶ de los bloques de código: cuesta dos turnos y
  deja la pestaña en una sesión NUEVA. Si el resumen sale corto o falla, **no se compacta
  nada** — arrancar en blanco en silencio sería hacerle perder el hilo justo cuando cree
  que lo está salvando.
- ⭐⭐ **El chip mide el contexto de AHORA, no lo gastado en total** (`contexto()` en
  `sesiones_movil.py`): sale del último `usage` del `.jsonl` (input + cache leído + cache
  escrito), que es exactamente lo que se relee en cada mensaje. Ese es el número que se
  vuelve a pagar con cada comando; el acumulado no se puede bajar, éste sí.
  ⚠ Se leen los **últimos 400 KB** del archivo, nunca el archivo entero (llegan a 45 MB), y
  queda cacheado por (archivo, mtime, tamaño) como en `novedad()`. Medido: 0-4 ms.
- ⚠ **Los umbrales van en tokens de verdad, no en porcentaje del techo** (`CARO` 120 mil,
  `MUY_CARO` 250 mil): con la ventana de un millón, 300 mil son el 30 % del techo y ya es
  carísimo en cada turno. También avisa pasado el 75 % del techo, porque ahí el CLI compacta
  solo y esa compactación la elige él, no vos.
- ⚠ Los tonos del aviso son **ámbar apagado**, nunca rojo (regla de Martín: el rojo es para
  lo que está mal). Y el botón Compactar **se enciende solo cuando de verdad conviene**: si
  estuviera siempre igual, dejaría de querer decir algo.
- ⚠⚠ La prueba **mide el color computado, no la clase**: `aspecto.js` pinta `.caja button`
  con el color de acento de Martín, y si le ganara al aviso, encendido y apagado se verían
  igual.
- **Laura es aparte porque su proceso vive en `voz.py`**: el panel deja la señal
  (`compactar.flag`, como `nueva_sesion.flag`) y el trabajo lo hace allá, **en un hilo** —
  son dos turnos de Claude y ese bucle es el que atiende el micrófono. El modelo lo relee
  del archivo antes de cada turno (`_revisar_modelo`) y si cambió **se rearranca con
  `--resume`**, así que la charla sigue igual y cuesta los ~10 s del arranque.
- **El celular todavía no tiene los controles**, pero hereda el modelo elegido en la compu.
- Prueba: `pruebas/ver_modelo_compactar.py` (24 chequeos, con el servidor de modelos y de
  compactar **inventado**: compactar de verdad costaría dos turnos y mudaría una sesión).

### Modelo, Esfuerzo y Velocidad de Codex en todas las pantallas (2026-08-21)

Codex tiene las mismas tres perillas en el panel de Laura y en Sesiones, tanto en la PC
como en el celular. También se eligen antes de mandar el primer mensaje de una charla nueva:
la pestaña conserva las opciones hasta recibir su id real y entonces las guarda en
`ajustes_sesiones.json`.

- **Modelo:** Terra, **GPT-6 Astra** (desde el 2026-09-12, con el CLI 0.153.4), Sol, Luna,
  5.5 o Codex Spark; se manda con `-m` en cada turno. La lista vive en `MODELOS` de
  `app/voz/codex_voz.py` y es una copia a mano del catálogo del CLI: envejece, así que un
  modelo nuevo no aparece hasta que alguien lo agrega. Los retirados se sacan (`gpt-5.4` y
  `gpt-5.4-mini` ya no existen); una charla que tenía uno cae sola en el de fábrica.
- **Esfuerzo:** la lista cambia con el modelo para no ofrecer niveles incompatibles.
- **Velocidad:** Estándar no agrega ninguna bandera; Rápida usa el tier `priority` real.
  Codex Spark solo publica Estándar en el catálogo instalado.
- Las pruebas `probar_esfuerzo_codex_sesiones.py`, `ver_modelo_compactar.py` y
  `ver_cerebro_movil.py` cubren comando, persistencia y las cuatro superficies visuales.

### Una conversación, UNA fila: las continuadas se tapan (2026-08-21)

Martín mandó la captura de la bandeja de Farah: cuatro filas que eran dos charlas, cada
una duplicada con su continuación (una viva y la otra muerta con la chapa "⇲ sigue en
otra"), y la que se había mudado a Codex llamada **"[Esta charla venia corriendo con
Claude y Martin la acaba de"** — el texto del traspaso. Textual: *"se ve y se siente feo
trabajar así"*.

- **El servidor decide, las pantallas obedecen.** `listar()` marca `tapada: true` en la
  charla vieja **solo si su continuación está en esa misma lista**. Si la nueva quedó
  fuera de la ventana de tiempo o le borraron el archivo, la vieja se sigue mostrando con
  su chapa: nunca se esconde algo que no se pueda alcanzar por otro lado.
- **Se marca, no se saca** (misma regla que las archivadas): la fila viaja en el JSON y
  las dos pantallas la saltean —en la bandeja, en los contadores y en las archivadas—.
  Una tapada NO va al cajón de archivadas: no la guardaste vos, la conversación siguió.
- **No se pierde nada**: el hilo de la continuación ya trae la charla vieja cosida arriba
  (`conversacion()`, 2026-08-20), y un turno que caiga en la vieja lo redirige
  `resolver_continuacion()`. Es la MISMA conversación, no dos.
- **El borrador se muda con vos**: `_mudar_borrador()` en `panel.py` pasa lo que dejaste a
  medio escribir a la continuación (si la nueva ya tiene algo escrito, manda lo suyo). Sin
  esto, el texto quedaba en una fila que dejó de dibujarse.
- **El nombre de una charla de Codex** sale de su primer mensaje —Codex no tiene
  `ai-title` como Claude—, así que ahora `_codex_titulo()` saltea la siembra y el pedido de
  resumen, y mientras no le escribas nada se llama **como la charla que continúa**.
- Pruebas: `probar_bandeja_tapadas.py` (31, sin navegador) y `ver_bandeja_tapadas.py`
  (las dos pantallas del disco, sin panel prendido; capturas en
  `resultados/bandeja_tapadas*.png`).

### Archivar y devolver: manda el servidor (2026-08-27)

Bug que trajo Martín: *"no me deja mandar a mi pestaña principal las sesiones
archivadas"*, y **en las dos pantallas**.

- ⚠⚠ **La causa: cada navegador se guardaba SU propio Set de ids en `localStorage`**
  (`sesArchivadas`) y la pantalla lo mezclaba con el flag del servidor —
  `archivadas.has(s.id) || s.archivada`. Ese Set solo se vaciaba en el navegador donde
  apretabas Devolver. Devolvías desde el celular: el servidor la sacaba de
  `sesiones_archivadas.json` y en el celular volvía, pero **la compu seguía teniéndola en
  su copia y ahí quedaba archivada para siempre** — y su botón Devolver ya no la mostraba
  (para el servidor no estaba archivada), así que no había ningún camino de vuelta.
- ⭐⭐ **Es la MISMA enfermedad que los íconos de carpeta antes de `aspecto_carpetas.json`
  (2026-08-25)**: identidad guardada por navegador = cada pantalla con su propia verdad,
  y el que pierde es siempre el que no tocó el botón. Cuando un dato tiene que valer en el
  celular, en la app de escritorio y en otro navegador, **vive en el servidor y punto**.
- **Cómo quedó**: la verdad es `s.archivada` (de `sesiones_archivadas.json`) y nada más.
  Lo local pasó a ser `archPend` = `{sid: true|false}` con **solo el cambio en vuelo**,
  para que la fila desaparezca en el acto y para no perder el cambio si el panel no
  contesta. Apenas el servidor confirma, la entrada se borra y manda él.
- ⚠ El pendiente se suelta **después** de recargar la lista, nunca antes: soltándolo con
  los datos viejos todavía en memoria, la fila pega un salto de vuelta por un instante.
- ⚠ La copia vieja (`sesArchivadas`) se **borra** al cargar, a propósito: sus ids son
  justo los que quedaron pegados. Lo que de verdad archivaste ya está en el servidor.
- ⚠⚠ **`ver_archivar_sesiones.py` pasaba GRACIAS al bug**: atajaba el POST contestando
  `{"ok":true}` mientras el servidor no se enteraba de nada, y era el Set local el que
  sostenía la vista. Arreglado el defecto se cayó, porque estaba midiendo un mundo
  imposible. Ahora su fingido es coherente (lo que contesta "ok" también se ve archivado
  en `/movil/sesiones`) y **la bandeja se inventa** en vez de pedírsela al panel.
- Pruebas: `ver_devolver_archivada.py` (nueva, 14 chequeos, **dos navegadores** = dos
  `localStorage`, que es lo que el bug necesitaba para aparecer; con `--viejo` sirve las
  páginas con el defecto puesto y exige que los dos chequeos que importan fallen) y
  `ver_archivar_sesiones.py` actualizada.

### La tarjeta de gasto del tablero y los dos vigías (2026-08-18)

La segunda vuelta del drenaje, ya con el plan escrito en el cuaderno: **medir el gasto
siempre, no solo cuando algo huele mal**. Es lo mismo que hace `ccusage` (la herramienta
que usa la comunidad): leer el `usage` exacto de los `.jsonl` de `~/.claude/projects`.

- **`app/nucleo/gasto.py`** (nuevo, sin GPU ni dependencias): lectura **incremental** —
  de cada archivo se recuerda hasta dónde se leyó y solo se lee lo nuevo. Primera pasada
  del día real: 1,1 s; las siguientes, 0,01 s. ⚠⚠ **El mismo `usage` aparece repetido en
  varias líneas seguidas** (una por bloque de la respuesta): se cuenta UNA vez por id de
  mensaje o el total da el doble. ⚠ Se cuenta TODO (input + output + cache leído +
  escrito): el cache leído es el "contexto releído" donde vivía el drenaje.
- **La cuarta cifra del tablero de arriba** (`#cifGasto`, "tokens hoy") con `GET /gasto`
  cada 5 minutos. El título del cuadrito trae la última hora y las 3 sesiones que más
  gastan. Rojo **solo** si la última hora pasa `QUEMA_ALTA` (regla de Martín: rojo = mal).
- **Vigía de quema** en el mismo hilo del vigilante de servicios: si la última hora pasa
  `QUEMA_ALTA` (40M), aviso al celular con la sesión que más gasta; se rearma cuando baja
  a la mitad. Mismas reglas anti-ruido: avisa en el cambio de estado, no repite.
- **Autocompactación de Laura**: si su charla arrastra más de `AUTOCOMPACTAR_EN` (160 mil)
  y está QUIETA (voz prendida, sin `PENSANDO`, sin otra compactación pedida), el panel
  deja el mismo `compactar.flag` del botón y voz.py hace el resto. Refractario de 30 min.
- Prueba: `pruebas/probar_gasto.py` (15 chequeos, con transcripciones de mentira).
- Los hooks oficiales de Claude Code se evaluaron y **quedaron descartados a propósito**:
  el `.jsonl` ya trae el gasto exacto, un hook global agregaría riesgo sin dato nuevo.

### La quinta cifra: cuánta máquina queda, y el botón de soltarla (2026-09-03)

Sale del pedido de Martín: *"quiero poder tener todas las sesiones vivas que se me ocurra
y que no se rompa nada"*. Ya no hay tope de sesiones prendidas — se duermen solas cuando
falta memoria (`_barrer_vivas`, ver el `CLAUDE.md`) — así que hacía falta poder **ver** eso
y poder soltar la máquina a mano.

- **`#cifMaqCaja`**, quinta cifra del tablero de arriba, con `GET /sesiones/maquina` cada
  15 s: los GB libres y cuántas sesiones hay prendidas. El globito lista cada sesión con su
  RAM y marca las que están trabajando. Es la cifra que explica por qué una charla vieja
  tarda 8 s en volver: estaba dormida.
- ⚠ **Estar apretado de memoria NO es un error**: es el sistema haciendo su trabajo. Va en
  `var(--acento)`, **no en rojo** (regla de Martín: el rojo es solo para lo que está mal).
- **Botón `💤 Soltar máquina`** al lado del ⟳, con `POST /sesiones/liberar`. Duerme las que
  se puedan dormir y **no reinicia nada**. Contesta cuántas durmió **y cuántas quedaron
  trabajando**: sin ese segundo número, un "0 dormidas" se lee como que el botón está roto
  cuando en realidad estaban todas ocupadas.
- ⚠ **El ⟳ de al lado no hace esto** y nunca lo hizo: apaga `SERVICIOS` y relanza el panel,
  sin tocar un solo proceso de sesión. Era justamente el agujero — Martín reiniciaba para
  destrabar y los 450 MB de cada sesión seguían ahí.
- Ninguno de los dos caminos toca una sesión con trabajo en segundo plano. Eso no es una
  decisión de pantalla: está en el guardián del `CLAUDE.md` y tiene su regla en
  `probar_no_romper`.

### El botón ⚡ Skills y comandos de las cajas de escribir (2026-08-18/21)

Pedido de Martín por voz: *"que me aparezcan las opciones que suelen aparecer cuando
escribo la barrita en Claude Code"*. Primero fueron dos botones; el 2026-08-21 Martín
pidió **unificarlos en uno solo**, manteniendo adentro dos secciones claras. Las skills
siguen marcando **cuáles ya usó esa sesión**.

Están en la caja de `/sesiones` y en la barra del chat de Laura del panel.

- ⭐ **Vive en `app/estaticos/atajos.js`** (compartido, como `menu.js` y `marcas.js`):
  `Atajos.montar({contenedor, sesion, insertar, acciones})`. Los datos los pone
  `GET /skills` (backend `app/nucleo/skills.py`): el catálogo sale de
  `~/.claude/skills/*/SKILL.md` (más las del proyecto en `<cwd>/.claude/skills`), y
  las usadas del propio `.jsonl` de la conversación — una skill aparece como
  `tool_use` de `Skill`/`SlashCommand` (la eligió Claude) o como `<command-name>` en
  un mensaje (la tipeó Martín). Lectura incremental como `gasto.py`; el archivo más
  gordo (45 MB) paga 0,14 s UNA vez.
- ⭐ Las chapas son **tres**, de la más fuerte a la más débil: **● en uso** (la última
  invocada después del último mensaje del usuario, Y la sesión está pensando ahora —
  eso lo resuelve el endpoint: `PENSANDO` para Laura, los turnos abiertos del panel y
  `EN_CURSO` para el resto), **✓ usada** (ya se invocó en ESA charla) y **✓ 8** (se usa
  en el PROYECTO, en otras conversaciones). Tonos apagados, nunca el verde del semáforo,
  y los tres distintos entre sí — la prueba compara el color computado, porque marcar
  todo igual es lo mismo que no marcar.
- ⭐⭐ **La marca del proyecto** (`usadas_proyecto()` en `skills.py`, campo `proyecto`
  de `GET /skills`), pedida el 2026-08-18: *"me gustaría que ya estén marcadas las
  skills que ya estoy ocupando"*. El problema era que `usadas()` mira UNA charla, así
  que abrir el menú en una conversación recién nacida mostraba las trece skills en
  blanco — cuando en este proyecto ya se usan ocho. Lo de esta charla le **gana** a lo
  del proyecto: si ya la usaste acá, la chapa dice "usada" y no el número.
  ⚠ Es el mismo recorrido incremental de `usadas()` pero sobre TODA la carpeta del
  proyecto: 133 conversaciones y 305 MB medidos acá. Primera pasada **1,8 s**, después
  **0,008 s** incremental y **0,0015 s** cacheada (30 s). Es lo único caro del endpoint,
  y el menú dice "Leyendo…" mientras tanto.
  ⚠ Si un `.jsonl` **achica**, se recuenta la carpeta entera en vez de sumar lo nuevo
  encima: sumar contaría de más y no hay forma de saber cuánto aportó lo que se fue.
  Pasa casi nunca (Claude Code solo agrega al final), así que lo simple gana.
  ⚠ El conteo mide **invocaciones explícitas** (la herramienta `Skill`, `SlashCommand`
  o la barrita tipeada). Una skill cuyas reglas están copiadas en el `CLAUDE.md` global
  se cumple **sin invocarla** y por eso figura en cero: le pasa a `notas`, que tiene 8
  usos en otros proyectos y 0 acá aunque la nota del cuaderno sí se venga actualizando.
  El número es un piso, no la verdad completa.
- ⚠⚠ **Los comandos con equivalente en la pantalla EJECUTAN ese equivalente**, no se
  escriben: `/compact` mandado como texto a una sesión se ignora (probado el
  2026-08-18, cero turnos). `/compact` aprieta el botón Compactar (con su flujo de dos
  toques), `/clear` abre una conversación nueva, `/model` abre los ajustes unificados. Solo los
  que son skills de verdad (`/init`, `/code-review`, `/security-review`) se escriben
  en la caja. Los de terminal (`/status`, `/help`…) no se ofrecen: ofrecer algo que
  acá no hace nada es peor que no ofrecerlo — el pie del menú lo dice.
- ⚠ El CSS del archivo va con `button.at-boton` a propósito: `.caja button` y
  `.barra-chat button` tienen la misma especificidad y pintan todo como Enviar; el
  empate lo gana el `<style>` inyectado al montar, que llega último.
- ⚠ Cerrar el menú **desengancha sus escuchas** (la lección de `marcas.js`): la prueba
  abre, cierra y reabre tres veces por los tres caminos (clic afuera, Escape, item).
- ⭐⭐ **"Creo una skill y no aparece"** (Martín, 2026-08-23). Eran dos agujeros, los dos
  del lado de la búsqueda, no del menú:
  1. **Los comandos propios no se pedían nunca.** La sección "Comandos" era una lista
     de seis fija adentro de `atajos.js`, así que un `.md` puesto en
     `~/.claude/commands/` (o en `<cwd>/.claude/commands/`) no aparecía jamás. Ahora los
     trae `skills.comandos(cwd)` y van atrás de los seis, con la chapa **tuyo**. El
     nombre sale de la ruta igual que en Claude Code (`git/subir.md` → `/git:subir`), y
     la descripción del frontmatter o, si no tiene, del primer renglón con texto.
  2. **Una carpeta de skill sin `SKILL.md` adentro desaparecía callada.** Es el error
     típico al crearla a mano (el archivo quedó con otro nombre, o una carpeta de más).
     Ahora `skills.rotas(cwd)` las lista al final de Skills, en ámbar y sin poder
     tocarlas: **⚠ sin SKILL.md**. Sirve para distinguir "está mal puesta" de "nunca se
     creó", que antes se veían igual. El pie del menú dice dónde va una skill nueva.
  También entran ahora las skills que traen los **plugins** (`~/.claude/plugins`, a
  cualquier profundidad hasta cinco niveles antes de `skills/*/SKILL.md`).
  ⚠ El catálogo se lee del disco en cada apertura del menú: una skill nueva aparece sin
  reiniciar nada. Lo que sí necesita reiniciar el panel es el endpoint `/skills` cuando
  se le agregan campos, porque `panel.py` está en memoria — mientras tanto `atajos.js`
  degrada solo (sin `comandos` ni `rotas` en la respuesta, no dibuja ninguna de las dos).
- Pruebas: `pruebas/probar_skills.py` (36 chequeos, backend con carpetas y `.jsonl` de
  mentira) y `pruebas/ver_botones_skills.py` (30 en navegador; intercepta `/skills` y
  sirve `atajos.js` del disco, así corre sin reiniciar el panel). La del navegador
  arma las **cuatro** combinaciones posibles de una vez: corriendo, usada en esta
  charla, usada solo en el proyecto, y nunca en ningún lado — más la carpeta rota y el
  comando propio.
- **El celular todavía no los tiene** (misma deuda que el selector de modelo ahí).

En `/sesiones`, la misma vuelta del 2026-08-21 reemplazó el clip sin nombre por dos
acciones explícitas: **Subir imagen** y **Buscar archivo**. Buscar archivo abre el selector
nativo de Windows y pega en el mensaje la ruta relativa a la carpeta de la charla, entre
comillas de código. Puede elegir cualquier documento de la computadora; si está en otro
disco y una ruta relativa no existe, pega la absoluta. El navegador solo no puede hacerlo
porque oculta la ruta local como `C:\fakepath`, por eso la elección pasa por un endpoint
del panel.

### El modelo de cada sesión y compactarla (2026-08-18)

Pedido de Martín después de encontrar de dónde salía el drenaje de tokens: *"poder elegir
el modelo de Claude de manera sencilla desde cada sesión, y poder compactar la sesión en
cada sesión… también para vos en este panel general"*. Dos controles nuevos, en dos lados:

    /sesiones, en la caja de escribir     un selector de modelo + ⇲ Compactar
    /, barra del chat de Laura            lo mismo, para su propia charla

- ⭐⭐ **El diagnóstico que lo motivó, porque explica los defaults**: su configuración
  global de Claude Code tenía `"model": "opus[1m]"` — la ventana de **un millón**. Con esa
  ventana la charla **no se compacta nunca**, así que cada comando y cada edición vuelve a
  leer la conversación ENTERA. Medido sobre sus propios `.jsonl`: una sesión de esa noche
  se comió **286 millones de tokens en 675 llamadas**, con un pico de **997 mil** de
  contexto; el proyecto entero, **1.640 millones en un día**. Por eso el de fábrica acá es
  `opus` a secas (200 mil) y el millón es una opción, no el default.
- ⭐ **El modelo va SIEMPRE en `--model`, aunque sea el de fábrica** (`mandar()` en
  `app/voz/sesiones_movil.py`). Sin esa bandera se hereda el `model` del settings global,
  que es justo lo que se quería dejar de heredar.
- ⭐ **Se guarda en el SERVIDOR** (`ajustes_sesiones.json`, ruta `AJUSTES_SESIONES`), una
  entrada por sesión más la de Laura bajo la llave `"laura"`. No es un gusto de pantalla:
  el modelo lo usa **quien lanza el proceso `claude`**, no el navegador. Y así se elige en
  la compu y vale igual desde el celular.
- ⚠⚠ **Compactar es a mano: el `/compact` de adentro no se puede pedir desde afuera.**
  Probado el 2026-08-18: `echo /compact | claude -p --resume <id>` contesta vacío, **cero
  turnos y cero tokens** — el CLI lo ignora. Así que son DOS turnos: se le pide a la
  sesión que resuma en qué anda y con ese resumen se **arranca una sesión nueva** en la
  misma carpeta. La vieja **no se toca ni se borra**: queda entera en el disco.
- ⚠ Los dos turnos van con el **mismo modelo** (se lee una vez al empezar): sin eso, la
  siembra caía en el de fábrica y una charla que corría en Haiku seguía en Opus.
- ⚠ La siembra se **reintenta una vez**: cuando se llega a ella el resumen ya se pagó, y
  perderlo por un `529 Overloaded` pasajero (visto probando esto) es tirar el turno más
  caro de los dos.
- ⭐ **La pestaña se muda a la sesión nueva** (`t.sid = r.sid` + `fijarDireccion`). Si no,
  seguís escribiéndole a la charla vieja y compactar no sirvió de nada. La prueba lo fija.
- ⚠ **Dos toques**, como el ▶ de los bloques de código: el primero cambia el botón a
  "⇲ ¿compacto?" y se cae solo a los 5 s. Cuesta tokens y cambia de sesión: un clic de más
  no puede alcanzar. En el panel de Laura, en cambio, va con `confirm()` — ahí el botón
  vive entre "Cortar" y "Nueva sesión", que ya preguntan así.
- ⚠ En una pestaña **sin estrenar** el botón se esconde y el selector avisa: no hay
  conversación que compactar ni id bajo el cual guardar el modelo.
- El selector **se pinta solo cuando NO está en el de fábrica**: lo único que hay que ver
  de un vistazo es "esta sesión está corriendo con algo distinto".
- **Laura es otro proceso**: el panel solo escribe el archivo y la bandera `compactar.flag`
  (mismo mecanismo que `nueva_sesion.flag`); el trabajo lo hace `voz.py`. El cambio de
  modelo lo levanta `_revisar_modelo()` antes de cada turno y **rearranca el proceso
  persistente con `--resume`**, así que la charla sigue igual y cuesta los ~10 s del
  arranque. ⚠ Compactar allá corre **en un hilo**: son dos turnos y ese bucle es el que
  atiende el micrófono.
- **Falta**: los mismos dos controles en la pestaña Sesiones del celular (`MOVIL_HTML`).
  Hoy el celular **respeta** el modelo elegido en la compu (vive en el servidor), pero no
  lo puede cambiar ni compactar desde ahí.
- Prueba: `pruebas/ver_modelo_sesion.py` (15 chequeos). ⚠ Intercepta `/movil/modelo`
  —el panel vivo todavía no lo tiene, así que corre **sin reiniciarlo**— y sobre todo
  `/movil/compactar`: compactar de verdad son dos turnos contra una sesión real de Martín.

### El marcador de texto de las conversaciones (2026-08-18)

Pedido de Martín: *"poder pintar o subrayar el texto de las conversaciones seleccionándolo,
apretando clic derecho, con varias opciones de color, varias formas y la opacidad"*.
Seleccionás adentro de una charla, botón derecho, y sale un menú con seis colores más una
rueda para elegir cualquiera, cuatro formas (resaltado, subrayado, marcador, recuadro), la
opacidad y "sacar la marca". Vive en `app/estaticos/marcas.js` (`window.Marcas`).

- ⭐ **Vive en un archivo compartido**, como `marcado.js` y `menu.js`: la compu pinta y
  borra, el celular por ahora solo **muestra**. Es la misma conversación en las dos
  pantallas, así que la marca tiene que dibujarse igual en las dos.
- ⭐⭐ **Cómo se ancla, que es lo único delicado**: NO se guarda HTML ni un pedazo de DOM
  (el hilo se rearma entero cada 3 s y se perdería en el primer repintado). Se guardan
  cuatro números y el texto: en qué mensaje (`data-msg`, su posición en la charla), desde
  y hasta qué letra contadas sobre el texto pelado, y qué decía. Al repintar se vuelven a
  buscar esas letras. **Si el texto ya no coincide, esa marca no se dibuja**: mejor no
  pintar nada que pintar el pedazo equivocado.
- Se dibuja envolviendo pedazos de nodos de TEXTO, nunca reemplazando el HTML del mensaje:
  así una selección que cruza una negrita o un bloque de código no rompe el markdown.
- Una selección que **cruza varios mensajes** deja una marca en cada uno.
- ⭐⭐ **No hay botón "Pintar": el color ES el botón** (pedido de Martín, 2026-08-18: *"no me
  gusta tener que apretar Pintar para que se pinte"*). Tocás un color o una forma y queda
  pintado; el menú **se queda abierto** y a partir de ahí cada toque RETOCA lo mismo en vez
  de apilar otra marca encima, así se prueban colores hasta que guste. Lo recién pintado
  queda agarrado (contorno punteado) y "Sacar la marca" lo deshace en el acto.
  ⚠ La opacidad es la excepción: solo retoca lo ya pintado. Mover el deslizador no puede
  ser la manera de pintar sin querer un pedazo que estabas por copiar.
- ⭐ **Una marca ya hecha se AGARRA con el clic de siempre** (pedido de Martín, "como lo
  ofrece el Adobe PDF"): queda con contorno punteado, el menú se abre **debajo de ella**
  —en el puntero le tapaba justo lo que ibas a cambiar— y ahí le cambiás color, forma u
  opacidad en el acto. Se suelta con Escape o tocando afuera. ⚠ Lo agarrado se guarda en
  una variable del módulo y se vuelve a marcar en cada repintado: en el DOM se soltaría
  solo a los 3 segundos.
- Backend: `MARCAS_CHAT` en `rutas.py`, y `GET /marcas`, `POST /marcas/poner` y
  `POST /marcas/quitar` en `panel.py`. Nada de esto toca los archivos de Claude Code.
- ⚠⚠ **Cerrar un menú es sacar el cartel Y desenganchar sus escuchas.** La primera versión
  solo lo sacaba de pantalla y dejaba vivos sus `mousedown`/`keydown` del documento: al
  abrir el menú siguiente, esa escucha zombi lo cerraba **en el mousedown**, antes de que
  llegara el clic. El primer marcado salía bien y de ahí en más ningún botón hacía nada —
  Martín lo vio como *"aprieto el botón y no pasa nada"*.
- Prueba: `pruebas/ver_marcas_texto.py` (26 chequeos) con el **servidor de marcas
  inventado**, así corre sin tocar una marca de verdad.

### Entrar a Sesiones es instantáneo (2026-08-18)

Martín: *"¿por qué tarda tanto en entrar en sesiones? Me gustaría que sea instantánea la
transición"*. Tardaba entre medio segundo y tres, mostrando "Cargando…". Ahora: **0,43 s la
primera vez desde un navegador, 0,06 s las siguientes.** Tres cosas, en orden de cuánto
aportan:

1. ⭐⭐ **La pantalla se dibuja con la lista de la última vez** (`sesDatos` en el
   localStorage, 25 kB) y se repinta cuando llega la fresca. Es lo que la hace instantánea:
   por más rápido que sea el servidor, ir y volver cuesta. ⚠ Lo primero que ves puede estar
   viejo; el semáforo se corrige en cuanto llega la respuesta.
2. **`novedad()` guarda lo averiguado por (archivo, mtime, tamaño)** en `sesiones_movil.py`.
   Se llamaba una vez por conversación (74) y cada llamada leía 200 kB: ~15 MB de disco por
   pedido, y la pantalla lo pide al entrar y cada 20 s. Si el archivo no cambió, la
   respuesta no puede haber cambiado.
3. ⚠⚠ **El cache de títulos (`_titulos` en `seguir.py`) tenía tope 200 con 215 archivos en
   el disco**: se vaciaba entero en cada recorrida y los títulos se releían SIEMPRE. Eran
   0,12 s de los 0,18 s que quedaban. **Un cache con tope más chico que el conjunto de
   trabajo no es un cache, es puro costo.** Ahora 2000.
4. La respuesta de `/movil/sesiones` se guarda **2 segundos** en el panel: la piden varias
   pantallas a la vez (sesiones al entrar y cada 20 s, el celular cada 15 s, cada pestaña
   abierta la suya). ⚠ Archivar y renombrar **invalidan** ese cache, o el cambio tardaba
   dos segundos en verse.

⭐ **Lo mismo en la app del celular** (pedido aparte: *"fijate si podemos aplicar esto en el
celular también"*), donde pesa más porque entra por Tailscale y a lo que tarde el servidor
hay que sumarle la red:
- la lista se guarda igual (`movilSesiones`) y `pintarElegir()` **dibuja con lo guardado y
  después refresca** — antes cada pintado empezaba con un `await fetch`, y ese pintado
  corre **cada 3 segundos**;
- ⚠ la app **ya no espera dos idas y vueltas para dibujar la primera pantalla**:
  `pintarTabs(); pintar();` corre antes del `(async () => …)` que pide `/movil/pestanas` y
  `/movil/sesiones`. Lo que llega después repinta solo si algo cambió;
- ⚠ `verificarFalladas()` y `sembrarVisto()` van SOLO con datos frescos (viven en
  `traerSesiones()`): deciden mirando fechas y con una lista vieja borrarían marcas rojas o
  darían por leídas conversaciones que no lo están.

Resultado medido: `listar()` 0,37 s → 0,06 s; el endpoint 0,55-0,75 s → 0,015 s cuando sale
del cache; la pantalla de la compu **0,43 s la primera vez y 0,06 s las siguientes**; el
celular **0,24 s y 0,07 s**. Prueba: `pruebas/ver_entrada_rapida.py` (12 chequeos, las dos
pantallas) — ⚠ mide con el servidor **cortado** (`route.abort()`), no demorado: demorar
desde Playwright traba el propio Playwright y terminás midiendo tu propia demora.

### Volver a Sesiones y caer donde lo dejaste (2026-08-18)

Martín: *"si estoy navegando por el panel y salgo de sesiones para entrar a otra pestaña,
cuando vuelva a sesiones quiero estar exactamente donde lo dejé"*. Al salir se guarda la
vista en `sesSitio` (conversación abierta, carpeta, archivadas sí/no, filtro y **scroll**) y
al volver se devuelve tal cual.

- ⚠⚠ **Convive con la decisión CONTRARIA que sigue en pie**: *"siempre se entra por la
  bandeja de Todas"* (2026-08-17). No se pisan porque no hablan del mismo momento: **entrar
  de cero** —un favorito, el acceso del escritorio, la barra de direcciones— es venir a ver
  qué hay y va a la bandeja; **volver** desde otra pantalla del panel es seguir donde
  estabas. Se distinguen con `document.referrer`: si viene de `/`, `/pizarra`, `/estudio`
  o `/avisos`, es una vuelta.
- **Una dirección con conversación (`?c=…`) le gana a todo**: si abriste ese link es porque
  querés ir ahí.
- ⚠ Se guarda con `pagehide` (y con `visibilitychange`), no con `beforeunload`: éste no
  siempre corre al navegar y algunos navegadores lo tratan como "voy a preguntar si querés
  salir".
- ⚠ El scroll y el filtro se devuelven con **pendientes** (`scrollPendiente`,
  `filtroPendiente`) que aplica el primer pintado, no escribiéndolos al entrar: `cargar()`
  termina un segundo después y repinta todo, así que lo escrito antes se perdía. El scroll
  de una charla además se vuelve a poner cuando cargan las imágenes, igual que `alFinal`.
- Prueba: `pruebas/ver_volver_sesiones.py` (9 chequeos), que fija las dos reglas juntas.

### Una dirección web por conversación (2026-08-18)

Pedido de Martín: *"quiero que cada conversación tenga su propia dirección web, para poder
guardarla en favoritos y tener varias pestañas del navegador, cada una en una conversación
distinta"*. Vive en `app/estaticos/direccion.js`, compartido por las dos pantallas que
abren charlas.

    /sesiones?c=<id>     una charla en la compu      /sesiones     la bandeja
    /movil?c=<id>        la misma en el celular      /movil?v=panel|pizarra|hablar|nueva

- ⭐ **El título de la página cambia con la charla.** El navegador guarda el favorito con
  el título del momento y la pestaña muestra ese texto: sin esto, seis pestañas dicen las
  seis "Sesiones" y el favorito no se distingue de ningún otro. Era la mitad del pedido.
- ⭐ **En la dirección va SOLO el id**, nunca la carpeta del disco: una dirección con la
  ruta adentro es larga, se rompe si el proyecto se mueve, y queda escrita en los
  favoritos. La carpeta la resuelve `GET /movil/donde` (glob a
  `~/.claude/projects/*/<id>.jsonl` + el `cwd` que Claude deja escrito adentro).
  ⚠ **No se resuelve con `/movil/sesiones`**: esa lista está topeada (20 proyectos, 20
  charlas de cada uno, último mes) porque es para elegir a ojo, y un favorito sirve
  justamente para volver a una charla de hace tres meses. El nombre que devuelve respeta
  el alias de `/movil/nombre` o la misma charla se llama distinto según por dónde entres.
- **Al entrar, la dirección MANDA** sobre lo guardado (el `localStorage` de la compu, las
  pestañas del servidor en el celular): si abriste ese link es porque querés ir ahí.
- ⚠ `entrarPorDireccion()` va **al final** de `sesiones.html`: abrir una charla dibuja la
  pantalla entera, incluido el explorador de archivos, y llamándola antes reventaba con
  `Cannot access 'arb' before initialization`.
- ⚠ Las charlas sin estrenar (`nueva-…`) **no** van a la dirección: ese id es provisorio y
  no significa nada en otra ventana. Cuando consiguen el de verdad, la dirección se
  **reemplaza** (`empujar:false`), no se empuja: la entrada anterior ya no lleva a nada.
- ⚠ **Varias ventanas del navegador comparten el `localStorage`**, así que la barra de
  pestañas de arriba es una sola: sin cuidado, la ventana B le pisaba a la A lo que había
  abierto. Se adopta la lista nueva con el evento `storage`, pero **no** qué charla estás
  mirando — eso lo manda la dirección de esa ventana, que es todo el punto.
- Prueba: `pruebas/ver_direccion_sesiones.py` (20 chequeos), incluido el caso que importa:
  un navegador **sin nada guardado** entrando derecho por la dirección.

### El 🎨: lo que se puede configurar (2026-08-18)

Todo vive en `app/estaticos/aspecto.js` y se guarda en el SERVIDOR (`/aspecto`), así que
elegís en la compu y el teléfono queda igual. Hoy se elige: **tipografía** (9, todas las
que ya trae Windows), **tamaño del texto** de las conversaciones (4 pasos), **color de
acento** (8 a mano + rueda libre), **fondo** (3 oscuros + 2 claros + **rueda libre** + foto
propia + la del escritorio de Windows), **cuánto se ve la foto**, y **volver a lo de
fábrica**. Después se sumaron el **color del rastro** (2026-08-28), el **color de cada
parte**, los **efectos** —sombra, vidrio, movimiento—, el **fondo con rueda** y los
**estilos** con el tinte por rol y el color de cada tarjeta (2026-08-29): las cinco
secciones de abajo. ⭐ Desde los estilos, el panel está **plegado en secciones**: si venís a
buscar una opción de las viejas, está adentro de una.

- ⭐ **El tamaño es un MULTIPLICADOR (`--escala`), no un tamaño fijo.** Cada pantalla tiene
  su medida pensada (la burbuja del celular es más grande que la de la compu): va como
  `font-size: calc(13.6px * var(--escala,1))` y la proporción se mantiene.
- ⭐ **Los colores del chat se DERIVAN del acento** (`mezcla()`): una sola perilla pinta la
  app entera y no se puede armar una combinación ilegible.
- ⚠⚠ **Un campo nuevo hay que sumarlo a la lista blanca de `POST /aspecto` en `panel.py`.**
  Si no, se guarda en el navegador donde lo probaste y no viaja al teléfono: anda en la
  pantalla donde lo estabas mirando y en ninguna otra.
- ⚠ Ningún color **de la fila** puede ser verde, amarillo ni rojo: son el semáforo de las
  conversaciones. Con la rueda se puede igual — ahí la decisión es de Martín.
- ⚠ La rueda aplica en el `input` y guarda en el `change`: guardando en cada movimiento son
  cien avisos al servidor por un color. Y no se redibuja el panel en el medio, o el
  navegador cierra su propio selector.
- Prueba: `pruebas/ver_config_aspecto.py` (22 chequeos) y `pruebas/ver_aspecto_global.py`.

### El color de cada parte, no un acento para todo (2026-08-29)

Martín: *"quiero poder editar el color de algunos elementos de la pizarra"*, y enseguida
*"no solo de la pizarra, también del panel principal"*. Eligió cuatro: **las burbujas del
chat**, **los botones y los estados**, **la barra de arriba** y **la barra de herramientas
de la pizarra**. En el 🎨 hay una sección nueva, *Color de cada parte*, con una fila por
parte: el nombre, una rueda y un ↺ que devuelve ESA parte al tema.

- ⭐⭐ **Lo caro no fue la perilla, fue juntar los colores.** Antes de esto había **once
  verdes distintos** repartidos en cinco pantallas, y el panel decía `#22c55e` donde el
  celular y `/sesiones` decían `#3ddc84` **para significar lo mismo**. Elegir "el verde" no
  era una variable: era un trabajo de 183 reemplazos. Ahora el semáforo sale de `--ok`,
  `--mal` y `--aviso`, cada uno con cinco peldaños que `aspecto.js` deriva de UN color:
  `--ok` (el punto, el botón), `--ok-2` (el hover, más hundido), `--ok-txt` (el texto que
  se lee sobre oscuro), `--ok-bd` (el borde) y `--ok-bg` (el fondito).
- ⚠ **Efecto colateral que Martín va a ver**: el panel pasó a usar el verde del celular
  (`#3ddc84`) en vez del suyo (`#22c55e`). Es el precio de que "el verde" sea uno solo.
- ⭐⭐ **`--barra` y `--piz-barra` NO se definen cuando no hay color elegido**, y eso es a
  propósito: así cada pantalla pone su propio "como estaba" en el segundo argumento de
  `var()` —el encabezado del panel es `transparent`, la barra de la pizarra es `--fondo2`—
  y una sola variable convive con dos defaults distintos. Definirla con un valor, **aunque
  fuera `transparent`**, le gana al respaldo y le deja la barra de la pizarra de vidrio a
  quien no eligió nada.
- ⭐ El semáforo arranca con su color **de fábrica** y no con el acento: si el verde de
  "encendido" siguiera al tema, dejaría de avisar. Cambiarlo se puede — es su pantalla —
  pero hay que elegirlo a propósito.
- ⛔ **Lo que la conversión NO tocó, y no se toca**: la rueda arcoíris (`conic-gradient`),
  las paletas de acento copiadas en las pantallas (`arena: [...]`), la paleta de DIBUJO de
  la pizarra y `COLORES_NOTA` (son colores de objetos, no de estado), y las entidades HTML
  tipo `&#127916;` — que son **emojis y no colores**, y el patrón `#[0-9a-f]{6}` las come.
- ⚠ `POST /aspecto` ahora **devuelve lo que guardó**. Con eso la pantalla se entera sola de
  que el panel está viejo (tira los campos que no conoce) y lo dice en el 🎨 en vez de
  dejar el color aplicado acá y mudo en el teléfono.
- Pruebas: `pruebas/ver_colores_por_parte.py` (18 chequeos en las cuatro pantallas, con
  `--viejo`: contra las de git caen los 4 que miran un elemento) y la regla
  `semaforo-en-variables` de `pruebas/probar_no_romper.py`, que impide que un verde vuelva
  a escribirse a mano.

### El tema claro, y los efectos (2026-08-29)

Martín, el mismo día y después de lo de arriba: *"me gustaría poder cambiar más
características"*. De cuatro opciones eligió **modo claro** y **efectos** (sombra, vidrio,
movimiento). En el 🎨 aparecen tres filas nuevas —*Sombra*, *Vidrio*, *Movimiento*— y dos
fondos nuevos, **Claro** y **Papel**, que no son "otro color de fondo": dan vuelta la
pantalla entera.

**Cómo anda el tema claro, que es lo que hay que entender antes de tocarlo.** Las cinco
pantallas tenían **749 colores escritos a mano, 196 distintos**, y no eran una paleta sino
acumulación: había cuatro grises azulados casi iguales (`#8b93a1`, `#8b94a3`, `#8b96a5`,
`#8b9ab0`). Escribir un tema claro a mano habría sido reescribir cinco pantallas y
mantenerlas en dos versiones para siempre. En vez de eso, cada color quedó así:

    border:1px solid var(--c232a35,#232a35)

- ⭐⭐ **El respaldo ES el color de siempre, y por eso el tema oscuro quedó idéntico por
  construcción.** Mientras el tema sea oscuro, `aspecto.js` **borra** esas variables en vez
  de definirlas, así que cada `var()` cae en su respaldo. No hay que confiar en ningún
  cálculo: verificado igual con `pruebas/foto_pantallas.py`, que fotografía las cinco
  pantallas antes y después y compara **píxel a píxel** — 0 de 1.152.000 distintos.
- ⭐ **El nombre lleva el color adentro**, así que no hay ninguna tabla que mantener: en
  claro se barre el HTML, se juntan los `--cRRGGBB` que existan y se le calcula a cada uno
  su versión clara. Un color nuevo escrito mañana con esa forma entra solo.
- ⚠⚠ **Se barre TODO el HTML, no las hojas de estilo.** Un color puede estar en un
  `style="..."` pegado al elemento (el botón "Reiniciar todo") o adentro de un `<script>`
  que arma la pantalla. Mirando solo los `<style>`, esos se quedaban en su versión oscura:
  gris claro sobre blanco, o sea invisible.
- ⚠⚠ **Y el barrido usa `document.body?.innerHTML`.** El archivo corre apenas se lee, y en
  la app del celular eso pasa **antes de que exista el `<body>`**: sin la guarda revienta y
  se muere el archivo entero — la pantalla queda sin botón 🎨 y sin acento, **sin que nada
  avise**. Lo cazó la comparación de capturas, no una prueba de colores: se veía "casi
  bien".
- ⭐ **Un color CON COLOR nunca se trata como una superficie.** El rojo de "roto"
  (`#ef4444`) tiene la luminosidad justo arriba del corte de los grises, así que con la
  cuenta de las superficies salía un rojo **clarito**: invisible sobre blanco y, peor, ya
  no gritaba. Los cromáticos (saturación > .30) van siempre a la franja de tinta, encerrada
  entre .20 y .42 para que sigan siendo rojo, verde y ámbar reconocibles de reojo.
- ⚠ La burbuja tuya en claro va **clarita con letra oscura**. La primera versión hacía lo
  contrario y quedaba ilegible por un motivo que no se ve venir: el texto de adentro no
  siempre pide `--burbuja-vos-txt`, muchas veces es un color de la pantalla **que ya se dio
  vuelta solo**, así que quedaba negro sobre azul.
- ⚠ Un texto claro sobre un **botón de color fuerte** (que en claro sigue oscuro) tiene que
  quedar literal, sin variable, o se da vuelta y desaparece. Se marca con `<!--no-tema-->`
  en la línea y el conversor lo respeta.
- ⛔ **`rgba(0,0,0,…)` NO se convierte**: son sombras, y darlas vuelta las volvería un halo
  blanco alrededor de cada caja. Los otros translúcidos sí, en su forma de tres números:
  `rgba(var(--cffffff-rgb,255,255,255),.06)` es una rayita que se ve clara sobre el tema
  oscuro y oscura sobre el claro.

**Los efectos.** *Sombra* (sin / suave / normal / marcada) sale de cuatro peldaños
(`--sombra-0..3` y `--sombra-arriba`): antes había catorce sombras de elevación distintas,
casi todas variaciones de las mismas tres. Las que son **señal** —el aro de foco, el
`inset` de lo seleccionado, el resplandor del punto encendido— quedaron afuera a propósito:
apagarlas dejaría la pantalla sin decir dónde estás parado. *Vidrio* multiplica el
desenfoque que las pantallas ya tenían (`blur(calc(16px * var(--vidrio,1)))`), y en
"Vidrio" además transparenta las superficies. *Movimiento* apaga las animaciones con una
regla sobre el selector universal y `animation:none` — **no** con duración cero: una
animación acelerada al infinito parpadea, y una cortada a la fuerza puede dejar el elemento
invisible si su último fotograma lo era.

- ⚠⚠ **`aspecto.js` tiene su CSS adentro de un template literal**: un acento invertido en un
  comentario **corta la cadena** y el archivo deja de ser JavaScript válido. Pasó ese mismo
  día. Después de tocarlo, `node --check app/estaticos/aspecto.js`.
- ⚠ El conversor (`pruebas/pasar_colores_a_variables.py`) es **idempotente**: si se corre
  dos veces sin la guarda, escribe `var(--cX,var(--cX,#x))` y encima pisa los arreglos
  hechos a mano. Ya pasó; ahora saltea lo que ya es respaldo de una variable.
- Pruebas: `pruebas/ver_modo_claro.py` (21 chequeos; mide el **contraste real** de cada
  texto contra su fondo y lo compara con el mismo texto en oscuro, así lo que ya era flojo
  antes no cuenta como defecto del tema claro), `pruebas/ver_efectos.py` (24, con `--viejo`:
  caen los 6 clave), `pruebas/foto_pantallas.py` (el antes/después píxel a píxel) y la regla
  `tintas-con-respaldo` de `probar_no_romper.py`, que impide que una tinta quede sin su
  color de respaldo — se rompe con una coma de menos y en el tema oscuro deja el elemento
  sin color.

### El fondo, con rueda: cualquier color (2026-08-29)

Martín, mirando la fila de cinco fondos: *"me gustaría poder elegir el color también"*. Al
lado de *Azulado · Negro · Carbón · Claro · Papel* hay ahora una **rueda**, igual que la del
acento y la del rastro. El color elegido se guarda en el MISMO campo (`aspecto.fondo` pasa
a ser un `'#rrggbb'` en vez de una de las cinco palabras), así que no hubo que tocar la
lista blanca de `POST /aspecto`: `fondo` ya viajaba al teléfono desde el 2026-08-17.

- ⭐⭐ **El tema claro se prende SOLO, por la luminosidad del color elegido** (corte en la
  mitad). No es una perilla aparte y no puede serlo: un fondo blanco con las letras claras
  de siempre es una pantalla en blanco, y nadie va a ir a buscar el interruptor que lo
  arregla. La bandera que los fondos `claro` y `papel` traen escrita a mano, acá se calcula.
- ⭐ **Un fondo es tres cosas, no una**: el color, la **superficie** donde se apoyan las
  tarjetas (`--fondo2`) y si el tema es claro. De un color pelado, la superficie se saca
  mezclando hacia el **blanco** —5 % si es oscuro, 50 % si es claro—, que es para donde van
  los cinco de la fila (`#0b0d12` → `#0f1320`, `#f2f4f8` → `#ffffff`).
- ⚠⚠ **Nada puede volver a pedir `FONDOS[aspecto.fondo]`**: con la rueda, ese índice no
  existe y se caería en el azulado sin avisar. Todo pasa por `fondoDe()`, que devuelve la
  misma tupla de cuatro que tienen los cinco de la fila — así el resto de `aplicar()` no se
  entera de si el fondo salió de la fila o de la rueda.
- ⚠ `fondoDe()` devuelve **hex, no `rgb(…)`**, y por eso existe `mezclaHex()`: más abajo
  esos dos valores se vuelven a mezclar y se les pone transparencia, y tanto `mezcla()`
  como `conAlfa()` leen los dígitos del hex a mano con `substr`. Con un `rgb(…)` adentro no
  se rompen: devuelven un color cualquiera, que es peor.
- ⚠ Mientras arrastrás la rueda, al cruzar el corte **la pantalla se da vuelta entera**. Se
  ve raro un segundo y está bien: soltás y queda.
- Un **gris medio** (luz cerca de .5) va a quedar flojo elija lo que elija el corte: no hay
  tema que lea bien encima de eso. No se le prohíbe —se ve al instante y es su pantalla—,
  pero no esperar que un `#808080` quede prolijo.
- Prueba: `pruebas/ver_fondo_a_gusto.py` (31 chequeos, con `--viejo`: contra el `aspecto.js`
  de git caen los 7 clave). Mide el contraste de cada texto con el mismo medidor de
  `ver_modo_claro.py`, y `foto_pantallas.py` confirma que los cinco de la fila y el tema
  oscuro siguen **idénticos** (0 de 1.152.000 píxeles).

### Los estilos: pintar todo junto, y bien (2026-08-29)

Cuarta vuelta del mismo día. Martín: *"hay más cosas que me gustaría poder editar"* →
*"más colores sobre el panel"*. En la entrevista eligió las cuatro zonas que faltaban (las
cajas y el mando, las letras, los botones grises y cada tarjeta con su color) y, puesto a
elegir entre veinte perillas sueltas o combinaciones armadas, eligió **las combinaciones**.

Arriba del 🎨 hay ahora una fila de **estilos** —*El de siempre, Terminal, Nocturno cálido,
Papel, Neón, Nórdico*— que pintan todo de una, y debajo el retoque fino.

**Lo que hace que sean dos perillas y no veinte: el teñido por ROL.** No hay una variable
por elemento. Se reusa el barrido de tintas del tema claro y cada uno de los 196 grises se
clasifica solo, por su luminosidad, con los cortes que ya estaban medidos: **abajo de .25
es superficie** (la tiñe *las cajas*, y ahí caen los botones grises sin necesitar perilla
propia), **arriba de .40 es letra**, en el medio se interpola, y lo que tiene **saturación
> .30 no se toca nunca** porque es el semáforo.

- ⭐⭐ **El teñido conserva la luminosidad de cada gris y solo le cambia el matiz.** Es lo
  que mantiene la jerarquía: el título sigue más claro que el subtítulo. Y tiene un efecto
  lateral que vale oro — **un tinte no puede volver ilegible un texto ni queriendo**, así
  que la garantía que se perdía al abrir las dos puntas (letras y cajas por separado) vuelve
  por otro lado.
- ⚠⚠ **Sin tinte elegido las tintas se siguen BORRANDO en oscuro.** Es lo mismo que sostiene
  el tema claro y ahora tiene su regla en `probar_no_romper` (`tintas-solo-con-tinte`), con
  mutación: si alguien simplifica el `if` y las define siempre, la pantalla de quien no
  eligió nada pasa a depender de un cálculo y las capturas píxel a píxel dejan de valer.
- ⭐ **Un estilo pisa TODO lo de color** y guarda lo anterior en `previo`, de donde sale el
  *"↺ Volver a lo mío"*. Decisión de Martín sobre las otras dos opciones. El `previo`
  guarda **solo los campos que el estilo pisa**, no el aspecto entero: adentro está `img`,
  que con una foto propia son cientos de kB, y duplicarla en cada estilo que mira reventaría
  el almacenamiento del navegador.
- ⚠ Un estilo **no toca** la tipografía, el tamaño del texto ni la foto: no son color, y
  pisarle el tamaño "Enorme" a quien lo puso porque ve mejor así sería una grosería.
- ⚠ Probar tres estilos seguidos y volver tiene que devolver **lo suyo**, no el estilo del
  medio: por eso `previo` solo se escribe cuando **no** venís de un estilo.

**Las siete tarjetas del panel.** Se marcan con `data-bloque` en el HTML de `PAGINA` (nunca
por `nth-child`: esta misma semana se agregó una tarjeta). Se pinta **el título y un filito**
—elección suya sobre el borde entero y el fondo— y el color sale de **girar el matiz del
acento**, así los siete son hermanos y ninguno desafina.

- ⚠⚠ **Girar en HSL conserva la "L" de esa rueda, que NO es la luz que ve el ojo.** El
  turquesa de Terminal girado daba un violeta con contraste **2,7** sobre el fondo negro
  (ilegible) donde el turquesa daba 15,4. `girar()` termina devolviéndole al resultado la
  luminosidad percibida del original. Lo cazó la prueba, no el ojo.
- ⚠ Y para el color elegido a mano no sirve `claroDe()`: un color poco saturado cae en su
  franja de **superficie** y termina casi blanco — justo lo que no puede pasarle a un texto
  (pasó con los títulos en Papel: 1,3 de contraste). Para eso está `aTinta()`.
- El paso entre bloques es de **150° y no de 45°**: con 45 quedan repartidos en la rueda
  pero los que se ven **uno al lado del otro** salen casi iguales.
- ⚠ El acento de *Papel* es **azul tinta y no terracota**: un terracota tira a rojo y el
  rojo es el semáforo. Lo cazó el chequeo que mide el matiz de cada acento.

**El 🎨 se reorganizó en dos niveles**: estilos arriba y seis secciones plegadas. Medido:
con una sección abierta el panel mide 742 px y hay que hacer scroll; cerradas mide **441** y
entra entero en el teléfono. Qué secciones dejás abiertas **se recuerda** (en el navegador,
no en el servidor: es cómo tenés ordenado el panel, no cómo se ven las pantallas) — sin eso,
elegir un color cerraba la sección que estabas usando en cada clic.

- ⚠ El aviso de "el panel quedó viejo" salió **afuera** de las secciones: adentro quedaba
  escondido atrás de un renglón cerrado justo cuando hay que leerlo.
- ⚠ Las pruebas que clickean opciones del 🎨 tienen que **abrir los `<details>` primero**:
  Playwright no clickea lo que no se ve, y sin eso se cuelgan 30 s y mueren. Ya está puesto
  en `ver_config_aspecto`, `ver_aspecto_global` y `ver_colores_por_parte`.
- Prueba: `pruebas/ver_estilos.py` (48 chequeos, con `--viejo` caen los 6 clave). Mide el
  contraste de **cada estilo × cada pantalla** con el medidor de `ver_modo_claro`, y antes
  de creerle se valida a sí misma: le pone un **gris medio de fondo** y exige que cace los
  textos rotos. Aparte verifica que la copia de los estilos que usa coincida con `ESTILOS`
  de `aspecto.js` — desincronizadas, estaría midiendo colores que la pantalla nunca usa.

### La letra: efectos, y cualquier tipografía instalada (2026-08-29)

Quinta vuelta del mismo día, mirando la sección *Letra* del 🎨 ya reiniciado: *"me gustaría
más efectos y estilos para las letras, aparte de poder seleccionar lo que yo quiera"*.

Se sumaron cuatro perillas —**Grosor** (fina/normal/negrita), **Espacio entre letras**,
**Renglones** (apretados/normal/aireados) y **Efecto del texto** (sombra/resplandor)—, la
**letra de los títulos** por separado, y un desplegable con **todas las tipografías
instaladas** en la máquina (52 en la de Martín) además de las nueve de la fila.

- ⭐⭐ **Cada efecto se prende con una CLASE en el `<html>`, no con una regla fija.** La
  primera versión puso una sola regla en el `body` con `var(--peso,400)` y sus respaldos, y
  parecía inofensiva porque los respaldos eran los valores del navegador. Pero **una regla
  que existe siempre le gana a la de la pantalla**: el celular y `/sesiones` declaran su
  propio interlineado en el `body` y quedaron con **62.000 y 6.700 píxeles distintos**. Sin
  clase no hay regla, y sin regla no hay nada que pisar. Lo cazó `foto_pantallas.py`.
- ⭐ **La tipografía de los TÍTULOS sí va con una regla fija**, y arregla algo que estaba
  roto desde antes: varias pantallas tienen un `*{font-family:Segoe UI}` —el selector
  universal le gana a la herencia del `body`—, así que elegir "Con serifa" nunca les cambió
  los títulos. Ahora `h1,h2,h3` piden `var(--tipo-titulo,var(--tipo))`, y sin letra propia
  elegida la variable **no se define** para que caiga en el respaldo (el mismo truco de las
  barras y las tintas). Con la tipografía de fábrica queda idéntico: cero píxeles.
- ⚠⚠ **El nombre de una fuente elegida a mano se valida con una lista de caracteres
  permitidos.** Y acá hay un dato que corrige la intuición: por el camino de `setProperty`
  **no se puede inyectar CSS** — el navegador trata el texto como valor de una variable y no
  deja cerrar la regla. Se comprobó rompiendo el candado a propósito (`ver_letra.py
  --mutar`): con la validación apagada, la pantalla igual se veía bien. Lo que el candado sí
  evita es que ese texto se cuele donde el nombre **se concatena a mano** (el
  `style="font-family:'X'"` de cada opción del desplegable) y que quede guardado un valor
  con comillas esperando a que alguien lo use en otro lado.
- ⛔ El desplegable **no ofrece fuentes de símbolos** (Wingdings, Webdings, Marlett, Segoe
  MDL2): elegir una deja las cinco pantallas en jeroglíficos y ni el botón de volver se lee.
- ⚠ Las fuentes se detectan **midiendo el ancho de un texto** con cada candidata contra la
  genérica. `queryLocalFonts()` daría la lista completa pero abre un cartel de permiso y en
  el teléfono no existe.
- ⚠ Una fuente que solo está en la PC **no está en el celular**: ahí cae en Segoe. El panel
  lo avisa con un renglón ámbar cuando la elegida no es una de las nueve.
- ⚠⚠ **Sombra y resplandor son los únicos de toda la tanda que la prueba de contraste no
  puede juzgar**: mide el color del texto contra el fondo, y una sombra no cambia ese
  número. Por eso el resplandor es flojo (7 px, .55 de alfa) y no el neón que uno querría.
- ⭐ **Los estilos ahora traen su tipografía y su efecto, pero NUNCA el tamaño del texto.**
  La tipografía es estética; el tamaño es que se vea. Pisarle el "Enorme" a quien lo puso
  porque lee mejor así sería una grosería disfrazada de estilo. Tiene su chequeo.
- Prueba: `pruebas/ver_letra.py` (30 chequeos; `--viejo` para los 9 clave y **`--mutar`**,
  que rompe la validación del nombre y exige que caigan los 4 chequeos hostiles —contra git
  no sirven, porque ese motor ni acepta fuentes libres).

### El modelo de cada charla y el botón Compactar (2026-08-18)

Martín: *"quiero poder elegir el modelo de Claude de manera sencilla desde cada sesión, y
poder compactar la sesión"*. Salió de encontrar de dónde venía un drenaje de tokens: su
config global tenía `"model": "opus[1m]"` — la ventana de un millón —, así que ninguna
charla se compactaba y **cada comando releía la conversación entera**. Medido ese día:
una sola sesión, 286 millones de tokens en 675 llamadas, pico de 997 mil de contexto.

Están en las **tres** pantallas, con el mismo dato detrás:

    /sesiones   selector + ⇲ Compactar en la caja de escribir (id `modelo`, `compactar`)
    /movil      la fila `.ajusSes`, abajo del título de la charla
    /           barra del chat: `selModelo` + `btnCompactar` + el chip `ctxLaura`

- ⭐⭐ **El modelo vive en el SERVIDOR** (`ajustes_sesiones.json`, una entrada por sesión
  más la llave `laura`), nunca en el `localStorage`: lo usa quien LANZA el proceso
  `claude`, no la pantalla. Por eso se elige en la compu y el teléfono lo respeta solo.
  La lista es `MODELOS` en `app/voz/sesiones_movil.py` — un renglón por modelo y aparece
  en las tres pantallas.
- ⭐ **`--model` va SIEMPRE, aunque sea el de fábrica**: sin él se hereda el `model` del
  settings global, que es justo lo que había que dejar de heredar.
- ⚠⚠ **`/compact` no se puede pedir desde afuera.** Probado: `echo /compact | claude -p
  --resume <id>` contesta vacío, cero turnos, cero tokens. Así que compactar es a mano y
  son **dos turnos**: se le pide un resumen a la charla vieja y con eso se ARRANCA una
  nueva (`compactar()` en `sesiones_movil.py`, `PEDIDO_RESUMEN` + `SIEMBRA`). La vieja
  **no se borra**: queda entera en la bandeja.
- ⚠ Los dos turnos van con el **mismo modelo**: `mandar` sin sid caía en el de fábrica y
  una charla que corría en Haiku seguía en Opus sin que nadie lo pidiera. Y la siembra se
  reintenta una vez: para cuando falla, el resumen ya se pagó (un 529 pasajero lo tiraba).
- ⭐ **Compactar cambia el sid**, así que la pantalla tiene que MUDAR la pestaña a la
  sesión nueva (y la dirección `?c=`). Si no, seguís escribiéndole a la charla vieja y no
  sirvió de nada — es lo que verifican las dos pruebas.
- **Dos toques en la compu, confirmación en el celular**: son dos turnos de Claude, y con
  el dedo un roce al desplazar no puede arrancarlos.
- ⭐ **`AUTOCOMPACT`** (mismo módulo): `--autocompact` recibe un tamaño de ventana, no
  el punto exacto de disparo. Con 400 mil, Claude compactó solo a 316.853 (~80 %) antes
  de que Martín pudiera elegir. Ahora Opus 1M conserva su millón real y el panel pregunta
  persistentemente desde 250 mil; la decisión sobrevive recargas y bloquea Enviar hasta
  elegir “Sí, compactar” o “Ahora no”.
- ⭐⭐ **Opus 5.5 (2026-09-22) da vuelta la ventana de fábrica.** Opus 5 traía 200 mil y
  el millón se pedía con el sufijo `[1m]`; Opus 5.5 (`claude-opus-5-5`) **viene con un
  millón nativo** y es el Opus de fábrica del CLI desde la **2.1.280**. Como el panel
  manda el alias `opus` —que apunta siempre al Opus más nuevo del CLI instalado—, la
  perilla que dice *200 mil* pasaría a arrastrar hasta 800 mil sin compactar el día que
  se actualiza el CLI. Por eso `opus` entró a `AUTOCOMPACT` con `"200000"`: el rótulo
  vuelve a decir la verdad y `TOPES["opus"]` sigue valiendo 200 mil. **Los dos renglones
  van juntos**: sacar uno sin el otro deja el medidor midiendo contra un techo que no es.
  ⚠ Un alias solo vale lo que sepa el **CLI instalado**: con un binario anterior a la
  2.1.280, `opus` sigue siendo Opus 5 y el rótulo adelanta (misma lección que Codex Astra
  el 2026-09-12). Se verifica con `grep claude-opus-5-5` sobre el `claude.exe` de
  `AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/`.
- ⚠ **Laura corre en `voz.py`, que es otro proceso**: el modelo se relee del archivo antes
  de cada turno (`_revisar_modelo`) y si cambió, el proceso persistente se rearranca con
  `--resume` — la charla sigue igual y cuesta los ~10 s del arranque. Compactar va por
  `compactar.flag`, como `nueva_sesion.flag`, y **en un hilo**: son dos turnos y ese bucle
  es el que atiende el micrófono.
- ⚠⚠ **`lanzadores/Reiniciar panel.bat` solo mataba `python.exe`**, y el acceso del
  escritorio levanta el panel con **pythonw.exe**: el .bat corría entero, decía que
  reiniciaba y no mataba nada — media hora buscando por qué el cambio no aparecía en
  pantalla. Ahora busca los dos y relanza con el mismo ejecutable que estaba corriendo.
- Pruebas: `pruebas/ver_modelo_sesion.py` (15 chequeos) y `pruebas/ver_modelo_movil.py`
  (12, con teléfono emulado). Las dos interceptan `/movil/compactar`: compactar de verdad
  cuesta dos turnos contra una sesión real de Martín.

### El selector de preguntas con opciones (AskUserQuestion) (2026-08-18)

Pedido de Martín: cuando una sesión del panel hace una pregunta con opciones (las
decisiones de diseño de Claude Code), la pantalla tiene que mostrar **un selector de
verdad**: las opciones como botones para tocar, más un campo "Otra respuesta…" para
contestar con tus palabras — igual que la terminal. Vive en `/sesiones`; el cartel
aparece EN EL HILO, en lugar de la burbuja de "pensando" (la sesión no está pensando:
te está esperando a vos).

- ⭐⭐ **Cómo se consiguió, porque el CLI no lo regala** (medido en esta máquina el
  2026-08-18): con `claude -p` a secas AskUserQuestion **ni existe** ("is disabled for
  this session"), aunque vaya en `--allowedTools`; con `--permission-prompt-tool stdio`
  aparece pero **dontAsk la deniega solo**, sin preguntarle a nadie. Lo que anda:
  `--permission-mode default` + `--permission-prompt-tool stdio` + stream-json
  bidireccional. Ahí la pregunta llega por stdout como `control_request`
  `{subtype:"can_use_tool", tool_name:"AskUserQuestion"}` y se contesta por stdin con
  `control_response` `{behavior:"allow", updatedInput:{...questions, answers:{pregunta:
  elección}}}`. La elección puede ser una etiqueta, varias unidas con `", "`
  (multiSelect) o **texto libre** — el CLI distingue solo y se lo dice al modelo.
- ⚠⚠ **La regla sagrada ("dontAsk, no bypassPermissions") se mantiene en efecto**:
  en modo default el CLI nos pregunta a NOSOTROS por stdio, y `mandar()` deniega en el
  acto todo `can_use_tool` que no sea AskUserQuestion, con el mismo mensaje que daba
  dontAsk. Lo único nuevo que se abre es que la pregunta llegue al humano en vez de
  morir denegada. bypassPermissions no aparece por ningún lado.
- **El viaje completo**: `mandar()` en `sesiones_movil.py` (ahora stream-json
  bidireccional) publica la pregunta en `PREGUNTAS`; viaja a la pantalla **adentro de
  `/movil/chat`** (campo `pregunta` — la página ya pide eso cada 3 s, no es un pedido
  más); la elección vuelve por `POST /movil/responder` → `responder_pregunta()` escribe
  el `control_response` y el turno sigue solo.
- **Gestos**: con UNA pregunta simple, tocar la opción ES contestar (un gesto, como en
  la terminal). Con varias preguntas o multiSelect aparece un botón **Responder** que
  avisa qué falta en vez de mandar a medias. Lo tipeado en "Otra respuesta…" le gana a
  los botones. Al contestar, el cartel se esconde al toque y vuelve la burbuja de
  "pensando".
- ⚠ **Lo marcado y lo tipeado sobreviven al repintado de cada 3 s** (el hilo se rearma
  entero): viven en variables de afuera (`pregElecciones`) y los textos se capturan y
  devuelven alrededor del `innerHTML` (`guardarPregunta`/`restaurarPregunta`), con el
  foco incluido. Misma familia que las marcas de texto.
- ⚠ **Si nadie contesta en `ESPERA_RESPUESTA` (10 min), se deniega sola** y el turno
  sigue con el mejor criterio del modelo — un turno no puede quedar colgado para
  siempre esperando a alguien que se fue. El reloj del turno (`TIMEOUT`) **descuenta**
  lo que se espera al humano: una pregunta abierta no puede matar el turno por timeout.
- ⚠ Una pestaña **sin estrenar** también pregunta por el chat (con `sid` vacío)
  mientras su primer mensaje está en vuelo: ese turno vive bajo la clave
  `nueva:<cwd>` y sin eso el selector no aparecía en una charla recién nacida.
- Tonos del **acento**, nunca rojo: preguntar no es un error.
- **El celular todavía no dibuja el selector** (misma deuda que los botones de skills
  ahí): el backend ya le manda la pregunta por `/movil/chat`, falta solo el dibujo en
  `MOVIL_HTML`.
- Pruebas: `pruebas/probar_pregunta_sesion.py` (26 chequeos, con un `claude` DE MENTIRA
  que emite los mismos eventos que el real — probar con el de verdad costaría un turno
  y dependería de que el modelo quiera preguntar) y `pruebas/ver_pregunta_sesion.py`
  (20 en navegador, intercepta `/movil/chat` y `/movil/responder`, corre sin reiniciar
  el panel; deja captura en `resultados/pregunta_sesiones.png`).
- ⏳ **Falta reiniciar el panel** para que ande en vivo: `mandar()` nuevo,
  `/movil/responder` y el campo `pregunta` de `/movil/chat` están en memoria hasta el
  reinicio. Tras reiniciar, correr `pruebas/probar_parar.py` (usa el panel vivo) para
  confirmar que Parar sigue cortando el turno con el `mandar()` nuevo.

### Quién le habla a quién

- Las **dos pantallas de sesiones** (la de la compu y la pestaña "Sesiones" del celular) comen
  de los MISMOS endpoints: `/movil/sesiones`, `/movil/chat`, `/movil/mandar`, `/movil/nombre`,
  `/movil/novedad`, `/movil/carpeta`. El backend real es `app/voz/sesiones_movil.py`
  (+ `app/voz/seguir.py`, que sabe leer los `.jsonl` de Claude Code).
- El **chat del panel** y el de la pestaña "Panel" del celular leen `/chat`, que **parsea
  `logs/voz.log` por prefijos** (`comando:`, `respuesta:`, `claude respuesta:`, `dictado:`,
  `aviso sistema:`, `lectura:`, `telegram pregunta:`…). ⚠ Tocar un prefijo del log rompe el
  chat en silencio.
- La **pizarra del celular** es la MISMA página `/pizarra` metida en un `<iframe>`.
- El **Estudio** come de `/estudio/entrantes`, que lista lo que hay en
  `resultados/estudio/entrantes/`. Ahí caen solos los audios y videos que Martín manda por
  Telegram: los guarda `app/nucleo/entrantes.py`, enganchado en `procesar_a_texto()` — el
  único punto por el que pasan los tres caminos de ingesta. Cada pieza viene con su
  transcripción; en video también queda la interpretación visual cronológica de Gemini.
  El original se conserva para que el mismo recorte temporal corte imagen y sonido juntos,
  y al armar sale mp3 o mp4 según el tipo. Audio y video no se mezclan en una misma fila.
  ⚠ Si se toca ese guardado hay que reiniciar **el bot de Telegram y el webhook**, no solo el panel.
  Desde el 2026-08-20 la barra inferior de `/movil` tiene entrada directa a Estudio; a 390 px
  la propia pantalla muestra una vuelta clara a Laura, oculta el menú grande y no desborda.
  ⭐ Para CORTAR se usa la transcripción con marcas de tiempo (`GET /estudio/segmentos/{n}`,
  aparte de la lista a propósito: son ~200 frases por audio y la lista se pide cada 20 s).
  Tocás una frase y recortás ahí — este proyecto puede hacerlo porque ya transcribe todo lo
  que entra; Whisper calcula esas marcas igual, tirarlas era el desperdicio.
  Desde 2026-08-24, los videos tienen además reproductor sincronizado con ese cursor, una
  tira de ocho miniaturas para saltar mirando y una **Vista previa** que recorre los tramos
  que se van a exportar. La lectura visual de Gemini dejó de ser solo texto: cada momento
  detectado es un botón que lleva al segundo correspondiente para cortar o revisar.
  Desde 2026-08-24 cada uno de esos momentos tiene además **＋ elegir**: conserva el botón de
  ver para revisar el segundo exacto y suma a la fila un clip desde ese cambio visual hasta el
  siguiente (o hasta diez segundos si es el último). Así se pueden armar selecciones por lo que
  se ve, no sólo por lo que se escucha; sus bordes siguen siendo ajustables con las manijas.
  La descripción queda fuera de los botones y se puede seleccionar/copiar como texto normal, sin
  activar la vista previa ni sumar accidentalmente el clip.
  Ese mismo día el Estudio se separó en dos mesas visibles, **Audios** y **Videos**. No son
  dos discos ni dos listas de proyectos: ambas usan las mismas bandejas, búsqueda y carpeta
  de entrantes. La separación está en lo que se edita: cada proyecto conserva una fila de
  audio y otra de video, para poder volver a cualquiera sin mezclar imagen, silencio o salida.
  En Video la mesa es opaca para que el fondo elegido de la aplicación no se coma el texto;
  el reproductor ocupa el ancho de la tarjeta y las acciones quedan en una barra debajo, no
  flotando a sus costados como si fuera una onda de audio.
  ⚠ **`.medio` es la clase de las pestañas Audio/Video, no del cuerpo de una pista.** Cuando
  ambos compartían ese nombre, el `display:flex` de la pestaña acomodaba onda y transcripción
  en un solo renglón y comprimía el texto hasta dejar una letra por línea. El cuerpo se llama
  `.contenidoPista`. En el celular, además, los tres botones de cada frase bajan debajo del
  texto: dejarlos al costado volvía a estrecharla aunque la caja exterior ya estuviera bien.
  `ver_transcripcion_estudio.py` fija ambos anchos en computadora y celular.
  Un video recién subido no se muestra como fuente ni como pista mientras se prepara: primero
  Whisper genera los fragmentos y después Gemini interpreta sus momentos visuales. Solo cuando
  LAS DOS cosas quedaron guardadas aparece ya listo para cortar por frases; una fila con texto
  pero sin análisis inteligente sigue siendo una preparación, no un video listo para editar.
  La espera nunca queda muda: la subida muestra sus bytes/porcentaje y, después, la tarjeta de
  preparación indica el paso real y el porcentaje de Whisper y Gemini. Recargar el Estudio se
  engancha al mismo trabajo, no inicia una segunda preparación. Si Gemini falla, el video sigue
  oculto y la tarjeta ofrece reintentar; nunca queda una fuente a medio hacer. Los temporales
  `_subiendo_…` no son fuentes y no entran en la bandeja mientras la copia todavía se está
  guardando.
  La misma regla vale desde 2026-08-24 para los **audios nuevos**: tanto los que llegan por
  WhatsApp (incluso los que Martín le manda a Laura) como los que se sueltan desde esta página
  se ven primero en la Cola en vivo. Whisper y Gemini terminan antes de copiar la fuente y su
  ficha, por eso cuando aparece para editar ya trae texto, cortes y análisis guardado; no hay
  una ventana en la que se pueda elegir un audio a medio preparar.
  Desde 2026-08-24 hay además una **Cola en vivo** arriba de la bandeja. Es una ventana corta de
  lo que está entrando, independiente de la mesa que esté abierta: muestra audio y video, si vino
  de WhatsApp/Telegram o de esta página, y el paso real hasta que queda listo. La subida desde el
  disco aparece desde el primer byte; WhatsApp y Telegram escriben la misma ficha compartida, por
  eso se ven aunque los procese otro servicio. Los terminados quedan unos minutos como
  confirmación y después desaparecen: la cola no reemplaza el historial de fuentes editables.
  ⚠ La caja nace escondida por CSS cuando está vacía; al poblarla hay que imponer
  `display: block`, no resetear el estilo con `''`, porque eso la dejaba invisible aunque el
  endpoint ya tuviera los trabajos en curso (bug arreglado el 2026-08-24).
  El botón **Analizar** de abajo analiza el armado completo, con los recortes que quedaron puestos.
  Desde 2026-08-24 ese resultado ya no es un cartel pasajero: queda guardado con la combinación
  exacta de pistas, cortes y perfil elegido. Al volver a esa misma fila se abre de nuevo; si se
  cambia un corte o el perfil, no muestra una lectura vieja como si correspondiera al nuevo armado.
  ⚠ Al soltar un archivo dentro de su recuadro hay que cortar la burbuja del evento: el
  recuadro y el `document` tienen cada uno una escucha para permitir soltar en ambos lugares;
  sin `stopPropagation()` los dos llaman a la carga y se guardan dos copias gigantes.
  Desde el 2026-08-24 el texto de cada frase se corrige ahí mismo y se guarda solo
  (`POST /estudio/segmentos/{n}`). Copiar y Analizar esperan cualquier guardado pendiente:
  una corrección recién tipeada no puede salir con el texto anterior.
  Desde 2026-08-25, **Pasar a una sesión** convierte la fila elegida en un solo paquete para
  continuar el trabajo en una conversación existente. Antes de mandar, guarda cualquier
  corrección pendiente y prepara una copia de los cortes, una ficha Markdown con transcripción,
  tiempos recalculados sobre el armado y el análisis ya guardado; si es video suma un mosaico
  visual. La hoja recuerda la última conversación libre y permite agregar el pedido de Martín.
  El medio no viaja en base64: el mensaje enviado por `/movil/mandar` contiene las rutas locales
  estables que creó `POST /estudio/preparar-sesion`, y después abre esa conversación. No se llama
  otra vez a Whisper ni a Gemini y nunca se modifican los originales.

---

- ⭐ **Avisos** (`/avisos`) es la única pantalla cuyo dato NO vive en esta máquina: es un
  espejo de los Recordatorios del iPhone. **No hay conexión directa con Apple y no la va a
  haber** — se investigaron los tres caminos el 2026-08-17 y los tres se cerraron en iOS 13:
  (a) el CalDAV de iCloud dejó de exponer los recordatorios "actualizados" (el proyecto más
  nuevo que lo intenta lo dice en su propio README: *"en algunas cuentas eso es cero listas"*);
  (b) la app Recordatorios dejó de aceptar cuentas CalDAV de terceros, así que poner un
  servidor propio acá tampoco sirve; (c) los puentes que existen (TaskBridge y compañía) son
  **solo para Mac**. El puente lo hace un **Atajo del propio teléfono** contra
  `POST /avisos/sync`. Backend en `app/nucleo/avisos.py`.
  ⚠ Consecuencia para cualquiera que toque esta pantalla: **lo que muestra es una foto de
  hace un rato**, no el estado de este segundo. Por eso el chip de arriba siempre dice cuándo
  fue la última vez que el teléfono apareció — sin eso no se puede confiar en nada de lo que
  se ve. Y **el probador `pruebas/probar_icloud_recordatorios.py`** queda por si algún día
  Apple reabre la puerta: corre en un minuto y dice verde/amarillo/rojo.

---

- ⭐⭐ **El selector de preguntas con opciones (AskUserQuestion) vive en DOS pantallas y hay
  que tocar las dos.** Cuando una sesión frena a preguntar algo con opciones, la pregunta
  viaja adentro de `GET /movil/chat` (campo `pregunta`) y la elección vuelve por
  `POST /movil/responder`. El dibujo está duplicado a propósito, porque son dos HTML
  distintos: en `app/estaticos/sesiones.html` (la compu) y en `MOVIL_HTML` de `panel.py`
  (el teléfono, agregado el 2026-08-18 — antes el backend ya la mandaba y el celular no
  dibujaba nada: quedaba en "pensando" para siempre, sin forma de contestar).
  Las dos copias tienen las mismas cinco piezas: `htmlPregunta()`, `guardarPregunta()` /
  `restaurarPregunta()` (el hilo se rearma en cada repintado y lo marcado o tipeado se
  perdería), `juntarRespuestas()`, `responderPregunta()` y **un solo escucha delegado** sobre
  el contenedor del hilo — enganchar botón por botón obligaría a re-engancharlos cada vez.
  ⚠ **Si tocás una, tocá la otra**: son la misma función para el usuario.
  ⚠ En el celular los botones van a **44 px de alto** (se tocan con el dedo) y el campo de
  texto a **16 px** (menos que eso e iOS hace zoom solo y te descoloca la pantalla).
  ⭐ Con UNA pregunta simple, tocar la opción YA es la respuesta (un gesto). Con varias
  preguntas, o con selección múltiple, aparece el botón Responder y, si falta contestar
  alguna, lo avisa en la notita del pie en vez de mandar algo a medias.
  Probado: `ver_pregunta_sesion.py` (compu), `ver_pregunta_movil.py` (teléfono, 22 ok) y
  `probar_pregunta_real.py`, que lo mide contra una sesión de Claude de verdad.

- ⭐ **El modelo y el esfuerzo son DOS selectores hermanos, y están en tres lugares**: la barra
  del chat de Laura en el panel (`selModelo` + `selEsfuerzo`), la fila `.ajusSes` de cada
  charla en el celular, y la misma fila en `/sesiones`. Los tres leen del SERVIDOR (`/movil/modelo`
  y `/sesion/modelo`), así que lo que se elige en una pantalla se ve en las otras: es un dato,
  no tres ajustes. El esfuerzo se agregó el 2026-08-18 (`--effort` del CLI, cinco niveles).
  ⚠ **El valor vacío ("Esfuerzo normal") es el de fábrica y NO se pinta como "puesto"**: es el
  único que no manda el flag. Ponerle un nivel por defecto a todas las sesiones les cambiaría
  el comportamiento sin que nadie lo haya pedido.
  ⚠ En Windows, un `<select>` sin `appearance:none` queda BLANCO adentro de la barra oscura;
  apagada la apariencia hay que dibujarle la flecha de fondo. Vale para los dos.

- ⭐ **Las sesiones Codex usan el mismo semáforo que las de Claude** (2026-08-20): amarillo
  entre el último `task_started` y `task_complete`/`turn_aborted`; verde cuando terminó y
  todavía no la abriste. Dos datos son obligatorios en `codex_sesiones_de`: `viva` sale de
  los eventos reales del rollout y la hora tiene que viajar como `ts` — `cuando` no la lee
  el semáforo y hacía que todas parecieran vistas. Pruebas: `probar_estado_codex.py` y
  `ver_semaforo_sesiones.py`.
- ⭐ **Un video viejo del Estudio se puede poner al día** (2026-08-20): si no tiene segmentos,
  el texto vacío ofrece “Generar fragmentos editables”. Whisper procesa el original sin
  duplicarlo, completa la misma ficha y al terminar aparecen las frases con sus cortes.
  Importar `core` es tardío en el endpoint: abrir el panel no carga la GPU.

### La tarjeta de la placa de video (2026-08-22)

Pedido de Martín: *"me gustaría poder apagar o prender los modelos que ocupo para este panel
desde el panel"*. Venía de tener que pedirle a una sesión de Codex que matara Ollama y Whisper
a mano para que entrara el generador 3D — la placa son 8 GB y no entran todos juntos.

Vive en `PAGINA` (`<section id="bqPlaca">`, abajo de Voz), con `pintarPlaca()` cada 6 s contra
`GET /placa`. Backend en **`app/nucleo/placa.py`** (no importa Whisper: habla con `nvidia-smi`
por afuera, como `entrantes`).

- ⭐⭐ **Quién ocupa la placa sale de `nvidia-smi pmon`, NO de `--query-compute-apps`.** Ese
  último, en esta laptop, devuelve **veinte** procesos que no tienen nada que ver
  (`explorer.exe`, Telegram, WhatsApp, la interfaz de Avast): en Windows con WDDM todo lo que
  dibuja una ventana aparece ahí. `pmon` trae una columna `type` que dice `C` (cómputo), `G`
  (gráficos) o `C+G`: **los modelos son `C` pelado y el escritorio entero es `C+G`**. Con ese
  filtro la lista queda limpia. `probar_placa.py` guarda la salida REAL de ese día para que,
  si alguien "simplifica" el filtro, se ponga en rojo con datos de verdad.
- ⚠ **Cuánta memoria usa CADA proceso no se puede saber acá**: la columna viene en `-` (WDDM no
  la expone). Por eso se muestra el total de la placa y la LISTA de quién la ocupa, y no un
  número por modelo. No es que falte hacerlo.
- ⭐ **Cuando NO hay ningún modelo, la tarjeta explica de quién es lo que igual figura usado.**
  Martín lo preguntó apenas la vio (2026-08-22): *"¿cuál es ese proceso que ocupa 1 GB de mi
  gráfica?"* — el medidor marcaba 1 GB y la lista estaba vacía, así que el número quedaba sin
  dueño y parecía que había algo escondido. **No es un proceso: son ~20 programas dibujando
  ventanas** (el explorador, el navegador, WhatsApp, Telegram, Avast). Es el piso normal de
  Windows y no baja apagando modelos — que era la conclusión peligrosa. Sale de la misma pasada
  de `pmon`, contando los `C+G` en vez de tirarlos (`placa.escritorio()`).
- ⚠ **`/placa/apagar/{pid}` recibe un número del navegador.** Solo mata lo que está en la lista
  de cómputo del momento; si no, sería un "matá cualquier proceso de Windows" abierto en el
  panel. Y si el pid resulta ser un servicio del panel (Voz, Bot de Telegram), no lo mata a
  mano: usa el `stop_one()` de siempre, que lleva la cuenta de encendidos y apagados.
- ⭐ **Lo que el panel sabe PRENDER vive en `placa.MODELOS`, y sumar otro es una entrada más**
  (dict con `puerto`, `match`, `cmd`, `cwd`, `env`). Hoy están **Ollama** y el **generador 3D
  (Hunyuan3D 2mini)** — el segundo lo pidió Martín apenas vio la tarjeta. Se lanzan con
  `DETACHED_PROCESS`: **reiniciar el panel no te los apaga**, que es justo lo que querés cuando
  un modelo tardó cinco minutos en cargar.
  - ⚠ Los flags del Hunyuan (`--disable_tex --low_vram_mode`) y sus tres variables de entorno
    (`HF_HOME`, `HY3DGEN_MODELS`, `U2NET_HOME`) **no son decoración**: sin los primeros no entra
    en 8 GB, y sin las segundas se vuelve a bajar los pesos al disco C. Salieron del comando con
    el que la sesión que lo instaló lo dejó andando el 2026-08-22.
  - ⭐ **Tres estados, no dos**: apagado / **cargando** / prendido. Hunyuan se come 1,68 GB de
    pesos ANTES de abrir el 7860, así que hay un rato largo con el proceso vivo y el puerto mudo;
    sin el estado del medio la tarjeta decía "apagado" y daban ganas de apretar Prender otra vez.
    Mientras carga **no hay botón**: cortarlo ahí deja los pesos por la mitad.
  - ⚠ Un modelo de la lista que está andando **no puede salir también como hallazgo del barrido**
    (`estado()` filtra con `es_de()`), o aparecería dos veces: una con Prender y otra con Apagar.
  - ⚠⚠ **NUNCA reconocer un proceso por una palabra suelta de su línea de comando.** La primera
    versión usaba `match`: `"ollama"` y `"gradio_app.py"`. Las dos estaban mal de forma peligrosa
    (Martín: *"si yo apago los modelos, las sesiones del panel andan muy mal"*): **"ollama"
    aparece en el comando del `bash` con el que una sesión de Claude Code corre comandos** —
    medidos 4 procesos ajenos matcheando a la vez, todos de sesiones—, y **`gradio_app.py` existe
    igual en `TripoSR`**, que vive en la carpeta de al lado. Va por **carpeta del modelo**
    (`raiz`) o **nombre del ejecutable** (`exes`): `placa.es_de()`, probado en `probar_placa.py`.
- **Whisper no tiene botón propio**: vive adentro de la Voz y del Bot de Telegram, y Martín
  eligió apagarlo con el botón de ellos (2026-08-22) antes que agregar un "soltar la placa" que
  lo descargue sin matar la voz.
- El color de la barra **no es un semáforo de "está mal"**: la placa llena de modelos andando es
  lo normal acá. Verde hasta 80 %, ámbar hasta 95 %, rojo recién cuando ya no entra nada — el
  rojo es solo para lo que está mal (ver sección 2).
- Pruebas: `probar_placa.py` (28, sin tocar la placa) y `ver_placa.py` (21, con capturas de
  ocupada, al tope con un modelo cargando, y una máquina sin placa NVIDIA donde la tarjeta se
  esconde entera). ⚠ En `ver_placa.py`, la ruta del modelo va con `**/placa/modelo/**`: el `*`
  de Playwright **no cruza barras** y la URL tiene dos segmentos (`/hunyuan/prender`), así que
  con `*` el comodín se la comía y contestaba `{}` sin que se notara.

### El 📋 de la pizarra: guardar como imagen (2026-08-23)

Martín, desde el celular: *"¿cómo hago para copiar algo en la pizarra en el celular?"*, y
después *"¿podés poner 📋 en la tabla de herramientas que sea para copiar?"*. Preguntado qué
tenía que hacer el botón, respondió lo que en realidad quería: ***"¿y si me lo guarda como
imagen en el celular?"***. Vive en `PAGINA_PIZARRA` (`#btnFoto` + `guardarComoFoto`).

- ⭐⭐ **En el teléfono "copiar" no servía para nada y por eso hubo que preguntar.** El 📋 de
  la hoja de propiedades copia al portapapeles, pero **sin Ctrl+V no hay forma de pegar de
  vuelta en la pizarra**: la copia quedaba en la nada. Lo que se hace adentro del tablero es
  **⧉ Duplicar**; lo que uno quiere afuera es **la foto**. Son tres cosas distintas con el
  mismo nombre en criollo — antes de programar "copiar", preguntar cuál de las tres.
- ⭐ **Reusa `/pizarra/png`**, el mismo endpoint del Ctrl+C (dibuja con un navegador de
  verdad, ver sección 5): no hay un segundo dibujante que se desincronice.
- ⭐⭐ **En el teléfono va por `navigator.share` con el archivo, y eso NO es un capricho: es
  el único camino a las Fotos del iPhone.** Un `<a download>` deja el PNG enterrado en
  Archivos y hay que salir a buscarlo. La hoja de compartir además trae Copiar y WhatsApp
  gratis. En la compu es al revés (`(pointer:coarse)` decide): el archivo se baja derecho,
  porque ahí la hoja de compartir de Windows es una vuelta de más.
- ⚠ **Safari solo deja compartir dentro del gesto del dedo** y el dibujo tarda ~1 s: si se
  pasa, `share` tira `NotAllowedError`. Por eso el archivo bajado quedó de red abajo — ese
  camino no necesita gesto y el botón nunca se queda sin hacer nada. Cerrar la hoja
  (`AbortError`) **no** baja nada: cerrarla es una decisión, no una falla.
- ⭐ **Sin nada elegido saca la pizarra ENTERA.** Un botón que no hace nada hasta que
  selecciones algo no se entiende, y "todo" es lo que uno espera de una cámara.
- ⚠ Con 18 botones la barra del teléfono queda en **dos filas de 9 justas** (348 px de los
  360 que hay a 390 px de ancho). **El próximo botón la tira a tres filas**: ahí hay que
  achicarlos, y está anotado en el CSS al lado del `36px`.
- Prueba: `pruebas/ver_foto_pizarra.py` (18 chequeos). Sirve el `PAGINA_PIZARRA` del **disco**
  —el panel prendido tiene el viejo en memoria— e inventa el estado y el PNG: no toca la
  pizarra de verdad ni levanta el navegador que dibuja. ⚠ Lo de "el botón avisa mientras
  trabaja" **no se prueba demorando la red**: Playwright sincrónico atiende el interceptor en
  el mismo hilo y el chequeo llegaba tarde. Se llama a la función y se lee el botón en el
  mismo turno, antes de que ningún `await` haya podido volver.

## 2. Lo que Martín ya decidió (no se revierte sin preguntarle)

Estas son decisiones suyas, dichas explícito. Cambiarlas "porque queda mejor" es rehacer algo
que ya se discutió:

- **Las sesiones van en pestañas, nunca en una columna al lado del chat.** La referencia
  visual que dio es **Gmail**: proyectos como carpetas a la izquierda, conversaciones como
  bandeja, la charla abierta como pestaña propia.
- **Las pestañas van agrupadas por proyecto, uno solo desplegado a la vez** (2026-08-17):
  una pastilla por proyecto que se pliega y se despliega, y cuya ✕ cierra todas las charlas
  de ese proyecto. Plegada tiene que seguir mostrando el semáforo de lo que hay adentro, y
  el grupo de la charla que estás leyendo va siempre desplegado.
- **Las archivadas siguen la carpeta donde estás parado** (2026-08-17): adentro de un
  proyecto se ven solo las suyas; en **"Todas"** están todas juntas. ⚠ Ese "Todas" no es un
  detalle: es el lugar fijo donde ir a buscar lo archivado sin acordarse de qué proyecto
  salió. Contarlas por carpeta **sin** él ya se probó y el botón desaparecía al moverte.
- **La pizarra en el teléfono es el LIENZO**, no una lista. Se probó como lista y la rechazó:
  "quiero la misma pizarra que veo, mover cosas, como Excalidraw o Miro". **Un dedo corre el
  lienzo, dos dedos hacen zoom** (Miro y Figma, no Excalidraw).
- **Con el dedo, tocar algo nunca lo modifica.** Tocar una nota la abre; Editar y Borrar están
  adentro, y borrar pide confirmación.
- **Los botones de la barra de la pizarra van siempre visibles y apagados** (`opacity:.28` +
  `pointer-events:none`), nunca apareciendo y desapareciendo: si se ocultan, los demás se
  corren bajo el dedo entre un toque y el otro.
- **Lo que Claude/Laura escribe se lee dibujado; lo que escribís vos se muestra tal cual.**
- **Las respuestas habladas son cortas (1 a 3 frases) y sin markdown ni emojis.** El mismo
  texto sirve para leer y para escuchar.
- **Pausar escucha y Cortar son dos botones distintos**: pausar apaga la palabra clave y queda
  puesto; cortar suelta el turno de ahora y no deja nada apagado.
- **A una sesión que está abierta en la compu solo se la mira**, no se le escribe: dos procesos
  sobre la misma sesión la parten en dos. La pantalla lo avisa y ofrece arrancar una nueva.
- **La sesión de Laura no se lista** entre las sesiones (es la del asistente, no una
  charla). Desde el 2026-08-18 el filtro vive en el backend (`_ids_laura()` en
  `sesiones_movil.py`) y tapa **todos** sus ids — el de hoy Y el historial de
  `claude_sesion.json` —, releyendo el archivo en cada pasada porque cambia durante el
  día (el corte es a las 13:00). Filtrar solo la de hoy dejaba las de ayer en la
  bandeja con un título cualquiera, y abrirlas era bifurcarle la charla.
- **Un turno por sesión** (candado `_TURNOS_ABIERTOS` en `panel.py`).

---

## 3. Cómo se toca sin romper nada

**Reiniciar o no reiniciar** (esto se paga caro si se confunde):

| Qué tocaste | Hace falta |
|---|---|
| `app/estaticos/*.html` o `*.js` | **Nada**: se sirven con `FileResponse`, se leen del disco en cada pedido. Refrescar la pestaña. |
| Cualquier HTML/JS/endpoint **adentro de `panel.py`** | **Reiniciar el panel**: los strings y las rutas están en memoria. |
| `app/voz/sesiones_movil.py`, `seguir.py` | Reiniciar el panel (los importa al arrancar). |
| `app/voz/voz.py` y compañía | Reiniciar la voz por el panel (`POST /stop/voz`, esperar 3 s, `POST /start/voz`; tarda ~20 s). |

Reiniciar el panel: matar el proceso python que tenga `panel.py` en la línea de comando y
relanzarlo **sin `--auto`** si no querés que prenda todo. ⚠ Si tocaste el dict `SERVICIOS`,
hay que cambiar `"cmd"` **y** `"match"`, o el panel cree que un servicio está apagado.

**Antes de reiniciar nada**: `python -c "import py_compile; py_compile.compile('panel.py', doraise=True)"`.
El Python es `D:\IA\envs\wpp\python.exe`, nunca el del sistema.

**Las rutas de archivos van en `app/rutas.py`**, en ningún otro lado. Los estáticos se sirven
con `FileResponse(ESTATICOS / "…")`.

---

## 4. Cómo se prueba una pantalla (esto no es opcional acá)

⭐ **La lección más cara del proyecto en materia de interfaz**: los defectos de pantalla se ven
**sacando una captura y mirándola**, no leyendo el código. Los dos bugs que quedaban el
2026-08-14 aparecieron ahí. Playwright ya está instalado y hay ~9 pruebas de pantalla en
`pruebas/`.

Recetas que ya funcionan (copiar de ahí, no reinventar):

- `pruebas/probar_marcado.py` — la función pura, inyectada en una página en blanco. No necesita
  el panel prendido.
- `pruebas/ver_marcado_sesiones.py` — las dos pantallas de verdad, con la conversación
  **inventada** (`page.route` sobre `/movil/chat`).
- `pruebas/ver_carpeta_pestana.py` — navegación real por `/sesiones`, 24 chequeos.
- `pruebas/probar_pizarra_movil.py` — gestos de dedo de verdad por CDP.
- ⭐ `pruebas/ver_estudio.py` — **el servidor entero inventado**, incluida la propia página: se
  interceptan con `page.route` hasta `/estudio` y `/estudio/audio/*`. Sirve para probar una
  pantalla cuyas rutas **todavía no existen en el panel vivo**, sin reiniciarlo y sin tocar
  nada real. El único dato de verdad es el audio (un tono que genera ffmpeg) para que el
  navegador lo decodifique y la onda se dibuje como se va a dibujar en serio.
- `pruebas/probar_estudio_video.py` recorta y une videos reales inventados con ffmpeg;
  `pruebas/ver_estudio_video_movil.py` verifica el recorrido desde Laura, la vista previa y
  el editor a 390×844 sin tocar los datos vivos.
- ⭐ `pruebas/probar_unir_audios.py` — **importa `panel.py` y llama a la función** en vez de
  levantar el servidor: el evento de arranque de FastAPI (el vigilante de servicios) solo corre
  cuando lo sirve uvicorn, así que importar no prende ni vigila nada.

Reglas aprendidas probando:

- ⚠ **`wait_until="networkidle"` NUNCA llega en este panel** (hace polling cada 330 ms): va
  `domcontentloaded` + una espera fija.
- ⚠ **Nunca escribirle a una sesión real desde una prueba**: se interceptan `/movil/chat` y el
  POST a `/movil/pestanas` (ese último persiste en el servidor y le aparecería una pestaña
  fantasma en el teléfono).
- ⚠ **No se puede probar un turno de Laura desde una sesión de Laura**: el pedido espera a que
  termine el turno que lo hizo, y el turno espera la respuesta. Deadlock.
- ⚠ En CDP, `touchEnd` con lista vacía **no** dispara `pointerup`: el arrastre se ve moverse y
  no se guarda, y parece un bug del producto siendo del simulador.
- Teléfono emulado: 390×844 (iPhone 15/16, el que usa Martín) con `has_touch=True`.
- Un `page.on("pageerror")` en toda prueba: un error de JS deja la pantalla a medio dibujar sin
  avisar.
- ⭐⭐ **No midas contra un mundo que se mueve.** Estas pantallas leen datos VIVOS: la bandeja
  crece sola mientras corre la prueba, la lista se reordena cada 3 s (la conversación que está
  escribiendo salta arriba) y el servidor puede tener estado real de Martín. Tres formas de la
  misma trampa, las tres vistas el 2026-08-17 en `ver_archivar_sesiones.py`:
  (a) **nunca esperar números absolutos** ("quedan N-1 filas", "hay 0 archivadas"): se pregunta
  por el SID (`esta(pag, sid)`) o se mide contra el piso leído al empezar;
  (b) **la caja y el sid de una fila se leen en UN solo `evaluate`**, o entre las dos llamadas
  ya es otra fila y el dedo toca lo que no era;
  (c) **esperar al dato, no al reloj** (`wait_for_selector`, no `wait_for_timeout`):
  `/movil/sesiones` tarda entre 0,5 s y varios segundos según lo ocupado que esté el panel.
- ⚠ **`panel.py` se recarga solo al guardarlo** (uvicorn con reload), así que un cambio en
  `MOVIL_HTML` puede quedar vivo sin que nadie reinicie. No lo des por sentado en ninguno de
  los dos sentidos: **preguntale a la página** (`'loQueAgregaste' in urlopen('/movil').read()`).

---

## 5. Los gotchas de pantalla, juntos

Todo esto ya costó una tarde alguna vez:

- ⭐ **Lo que escribiste no se puede perder por un envío que rebota.** La caja se vacía apenas
  tocás Enviar (para que se sienta instantáneo), así que si el turno vuelve con error lo que
  habías escrito se evaporaba: pasó el 2026-08-23 en el celular, escribiéndole a una sesión que
  todavía estaba contestando. Ahora las dos pantallas tienen `devolverLoEscrito()`: vuelve a la
  caja si seguís parado en esa charla y no escribiste otra cosa, y **siempre** queda como
  borrador de esa conversación. Y antes de llegar a eso, la caja se **bloquea sola mientras la
  sesión contesta** en las dos pantallas — la compu lo hacía con el `ocupada` de `/movil/chat`;
  el celular ahora lo guarda en `cacheOcupada` desde el mismo pedido. ⚠ Ese dato tiene que
  refrescarse en cada repintado del chat: si se guardara una sola vez al abrir, la caja quedaría
  trabada para siempre después del primer turno. Prueba: `pruebas/ver_no_pierde_lo_escrito.py`.
- ⭐⭐ **Una charla NUEVA no puede esperar al final del primer turno para tener id.** Nace con
  un id provisorio de la pantalla (`nueva-…`) y el de verdad lo pone el CLI. Mientras la
  pestaña no lo sepa, le pregunta a `/movil/chat` con el id vacío y **no hay nada que leer**:
  eso era lo que Martín veía el 2026-08-23 — siete minutos de "Sin mensajes todavía" con la
  burbuja de pensando, mientras la sesión contestaba avances cada dos minutos ("¿qué pasó con
  la sesión en la que estaba?"). Ahora el servidor avisa el id apenas el CLI lo anuncia
  (`al_nacer` → ficha del trabajo → `sid_nuevo`) y las dos pantallas se mudan **en plena
  pensada**, con `mudarPestana()` / `mudarA()`. ⚠ Dos cosas para no romperlo:
  1. **la mudanza se hace en UN solo lugar** por pantalla — hay que mover con la pestaña todo
     lo que esté guardado bajo la clave vieja (el eco en vuelo, el relojito, las fotos, lo que
     cortaste con Parar), y preguntar `activa === clave` ANTES de tocar nada, o te arrastra de
     vuelta a la charla que dejaste (ver `ver_no_secuestra_chat.py`);
  2. mientras nace, la charla tiene **dos nombres a la vez** y el proceso está anotado bajo
     uno solo: `PARTOS` los empareja para que **Parar la encuentre por cualquiera de los dos**.
  Pruebas: `pruebas/ver_charla_nueva_en_vivo.py` (las dos pantallas, con el servidor
  inventado) y `pruebas/probar_sid_al_nacer.py` (el lado del servidor, con el CLI falso).

- ⭐⭐ **Cambiar de ventana en el celular no puede esperar la red ni dejar que la vista vieja
  vuelva encima.** El Inicio conserva su último dibujo mientras refresca y sus cinco datos se
  piden a la vez, no encadenados; así cada vuelta por Tailscale suma una sola vez. Al abrir una
  charla, la precarga y el dibujado comparten el mismo pedido, en vez de leer dos veces el mismo
  historial. Si la app abrió parada en Sesiones, el Inicio también se arma en segundo plano: el
  primer toque a Laura no espera esa primera carga. Las conversaciones de Codex reaprovechan la
  lectura completa que la bandeja ya hizo para sacarles el título: sobre Eva (86 MB), reabrir
  bajó de 323 ms a 1,3 ms dentro de la laptop. ⚠ Todo pintado que espera datos lleva el número
  de la vista: cuando vuelve, solo toca el DOM si Martín sigue parado ahí. Sin eso una respuesta
  tardía del Inicio o de la bandeja te puede devolver a una ventana que ya habías dejado.
- ⭐⭐ **En el celular el scroll es del CONTENEDOR, y el contenedor es UNO SOLO.** Todas las
  vistas (el inicio, la bandeja, una charla) se dibujan adentro del mismo `#cuerpo`, así que
  el scroll no se reinicia al cambiar de pantalla: lo hereda la que entra. Adentro de una
  charla el hilo queda abajo de todo y, al volver, la bandeja aparecía **a media lista**, en
  una conversación de hace tres días (Martín, 2026-08-24: *"cuando salgo del chat me mueve a
  cualquier parte de la lista, yo siempre quiero ver las últimas"*). `pintarElegir()` sube a
  0 cuando la lista es **otra** —volviste de una charla, cambiaste de carpeta, entraste a las
  archivadas—, comparando `dataset.vista` y `listaDibujada`. ⚠⚠ **Nunca en un repintado de
  los de cada 3 s**: eso te tiraría al principio mientras leés, que es peor que el bug que
  arregla (misma regla que las firmas de acá abajo). El botón "Sesiones" de la barra de abajo
  ya subía desde el 2026-08-17, pero adentro de una charla esa barra no existe: la salida es
  la flecha ←, y esa no lo hacía. Prueba: `pruebas/ver_bandeja_arriba_movil.py`.
- ⭐ **Repintar de gusto te tira el scroll.** Todas las vistas comparan una **firma** de lo que
  van a dibujar y si no cambió no tocan el DOM (`firma`, `firmaChat`, `firmaPanel`). Es la
  razón por la que se puede repintar cada 3 s sin que la pantalla se pelee con el dedo.
- ⭐⭐ **En el iPhone, un `position:sticky` adentro de un scroller que REBOTA se despega.**
  El 2026-08-24 Martín mandó la captura: adentro de una charla del celular, deslizando para
  abajo estando arriba de todo, la cabecera (título + perillas) se iba con el contenido y
  quedaba una banda enorme de la foto de fondo entre la barra de estado y el título, con las
  burbujas colgando. No es la cabecera: es el **rebote** de iOS (`rubber band`) — el sticky se
  pega al borde del scroller, y en pleno rebote ese borde ya no está donde uno lo ve.
  El arreglo es una palabra: `overscroll-behavior:none` en **`#cuerpo`**, que es el que
  scrollea. ⚠ En el `<body>` no serviría: iOS ignora `overscroll-behavior` en el scroller del
  documento. La pizarra ya lo tenía puesto desde siempre, por otro motivo (que no se pueda
  "tirar para recargar" arriba del lienzo). ⚠ **Chromium no hace ese rebote**, así que el bug
  no se puede reproducir en una prueba de navegador: `pruebas/ver_cabecera_pegada_movil.py`
  fija las dos mitades del arreglo (la regla en el scroller que corresponde y el sticky de la
  cabecera), cada una inútil sin la otra.
- ⭐ **Los pintados se pisan entre sí**: cada uno espera su `fetch`, y el de la pestaña vieja
  puede terminar después del de la nueva. En el celular se resolvió con `cacheChat` + número de
  pintado (`pintadoNro`); **la página de escritorio todavía no lo tiene**.
- ⭐⭐ **El ECO (la burbuja provisoria) se borra CONTANDO, no ubicando. No volver a "acordarse
  de la posición".** El eco de lo que acabás de mandar desaparece cuando ese mensaje aparece en
  el hilo. Cómo se decide eso costó tres intentos y los dos primeros están mal:
  1. *"mirá los últimos 4 mensajes"* → se duplicaba si la sesión contestaba varias veces seguidas.
  2. *"guardá en qué POSICIÓN estaba el hilo al mandar y mirá de ahí en adelante"* (2026-08-21) →
     ⚠⚠ **`/movil/chat` devuelve solo los ÚLTIMOS 40 mensajes** (`ultimos=40`). Pasada esa marca
     la lista deja de crecer, la posición guardada cae siempre al final, `slice()` da vacío y no
     se mira ni un mensaje: **en toda charla larga el eco quedaba pegado y veías tu mensaje DOS
     veces** hasta que terminaba el turno. Verificado: con la lógica vieja, hilo corto → `true`,
     hilo de 60 → `false`. Martín lo reportó dos veces el 2026-08-22, la segunda ya con este
     "arreglo" puesto.
  3. **(lo que hay)** cuántas veces está tu texto entre lo tuyo del hilo; si ahora está una más
     que al mandarlo, llegó. No depende de posiciones ni de cuántos mensajes devuelva el
     servidor, y aguanta que mandes dos veces lo mismo (`cuentaTuya()`).
  Está **en las dos pantallas** (`sesiones.html` y `MOVIL_HTML`), que tenían el mismo error.
  `suelto()` normaliza antes de comparar: saca el corchete de contexto (la marca de una imagen),
  el 📎 que agrega el servidor cuando la foto no está en disco, y aplasta los espacios (el
  navegador manda CRLF). Prueba: **`pruebas/probar_eco_mensaje.py`**, que corre el JS REAL de las
  dos pantallas con node, incluido el hilo de 60 mensajes.
- **Aparte, y real:** el texto llegaba al CLI con un `\r` de más (`\r\r\n`) porque el navegador
  manda CRLF y Windows lo volvía a convertir al escribir por stdin. Arreglado en el servidor con
  `_saltos_limpios()` (`sesiones_movil.py`, la única puerta de los dos cerebros) —
  `pruebas/probar_saltos_mensaje.py`. ⚠ Ese defecto era cierto pero **no era la causa** de que se
  viera doble: el eco se rompía igual sin un solo salto de línea.
- ⭐⭐ **Un turno que termina NO decide qué pantalla estás mirando.** Reportado por Martín el
  2026-08-23: *"mando un mensaje, salgo de ese chat mientras está pensando, y me lleva
  directamente a ese chat cuando me devuelve la primera respuesta"*. El "a veces" y el "la
  primera" eran la pista entera: pasaba **solo en el primer mensaje de una charla nueva**,
  el único momento en que la conversación cambia de id (de `nueva-…` al de verdad).
  `mandar()` (en `sesiones.html`) hacía `activa = r.sid` a secas al volver el turno, sin
  fijarse si vos seguías ahí — y `fijarDireccion()` encima te reescribía la barra de
  direcciones. Ahora se guarda `seguisAca = activa === clave` **antes** de tocar nada y las
  dos cosas van atrás de esa pregunta; si te fuiste, la pestaña se muda al id nuevo y queda
  marcada como pendiente, que es lo que ya hacía bien.
  ⚠ La regla vale para todo lo que vuelva de un `await` largo: **la pestaña se muda, vos
  no**. Al compactar y al mudar de cerebro ya estaba resuelta así (`if (activa === viejo)`).
  ⚠⚠ **Estaba en las DOS pantallas**, con una variante peor en la app del celular
  (`MOVIL_HTML` de `panel.py`): ahí la condición era
  `activa === p.sid || activa.startsWith('nueva-')`, y las dos mitades fallaban — la
  primera se comparaba contra el id **ya mudado**, así que nunca daba verdadera, y la
  segunda te traía a esta charla aunque te hubieras ido a **otra** sin estrenar.
  Prueba: `pruebas/ver_no_secuestra_chat.py`, que corre las dos pantallas con el `fetch`
  de `/movil/mandar` inventado, y con `SESIONES_HTML=`/`PANEL_PY=` apuntando a la versión
  vieja se la ve fallar.
- ⭐⭐ **Un gesto con el dedo no se define por DÓNDE empieza y termina, sino por CÓMO se hace.**
  El pase entre pestañas del celular (`#cuerpo` en `MOVIL_HTML`) miraba solo el punto de salida
  y el de llegada: 70 px de corrida y `|dx| > |dy|`. **Marcar texto para copiarlo es exactamente
  eso**, así que Martín intentaba seleccionar una respuesta y la app le cambiaba de conversación
  —y como `ir()` repinta, la selección se perdía en el acto: *"no puedo copiar"* (2026-08-23).
  Los mismos falsos positivos daban el otro síntoma, *"me va transportando entre varias
  sesiones"*. Lo que separa los dos gestos:
  - **el tiempo** — un pase dura menos de medio segundo; para seleccionar, el teléfono pide el
    dedo apoyado ~½ s antes de mostrar las manijitas, y recién ahí uno arrastra;
  - **la selección viva** — si hay texto marcado (al empezar o al soltar), no era un pase;
  - **los dedos** — con dos estás agrandando para leer;
  - **dónde arrancó** — adentro de un `pre`, `code`, `table`, `input`, `textarea` o iframe, el
    dedo es de ese elemento;
  - ⚠ **el desvío vertical se mide DURANTE todo el gesto, no en el punto final**: un movimiento
    en L —bajás leyendo y después vas al costado— llegaba con `|dx| > |dy|` y pasaba por pase.
  Es la misma regla que ya estaba escrita para el asa de mover y el borde conectable: **dos
  gestos sobre el mismo elemento se separan por cómo se hacen, no partiendo el elemento.**
  Prueba: `pruebas/probar_gesto_pestanas.py` (13 verdes), que despacha toques de verdad con sus
  tiempos sobre el JS real. ⭐ Acepta `PANEL_PY=` para correrla contra otra versión del panel:
  contra el `panel.py` anterior sale **6 en rojo**. Una prueba de gesto que no ve fallar la
  versión vieja no prueba nada — los toques sintéticos son fáciles de escribir "a favor".
- **En una columna flex con `max-height`, los hijos se encogen**: la fila de colores quedó de
  alto 0 y no se veía un solo color. Va `flex:0 0 auto`.
- ⭐ **Nunca buscar el DOM de una fila por el nombre del archivo que muestra.** En el Estudio el
  mismo audio puede entrar dos veces (una cortina que se repite), y `querySelector` devuelve
  siempre el primero: la segunda fila quedaba sin onda y sin manijas. Cada fila lleva su propio
  `id`, que es de la FILA y no del contenido. Corolario: al sacar una fila, el archivo se borra
  del servidor solo si ninguna otra lo está usando.
- **Una manija que vive en el extremo (0 % o 100 %) no puede estar adentro de algo con
  `overflow:hidden`**: queda partida al medio contra el borde y agarrarla es pescar 6 px. El
  contenedor no recorta y adentro va un `.lienzo` que sí, que es lo que necesita las esquinas
  redondeadas.
- **`white-space:pre-wrap` en una tarjeta entera** hace que los saltos de línea del propio HTML
  se dibujen como espacio: cada nota tenía un hueco enorme arriba y abajo. Va solo en el `div`
  del texto.
- **`fill:transparent` literal no siempre recibe un clic REAL de mouse** aunque
  `pointer-events:all` "debería" alcanzar; las pruebas con `force=True` no lo reproducen.
- **Dos elementos con el mismo `id` en páginas distintas del mismo archivo**: `getElementById`
  devolvía el otro (`btnLeer`), el interruptor nunca mostraba su estado y encima le pisaba el
  texto al ajeno.
- **El estado de un interruptor no vive en el `localStorage`** si tiene que ser el mismo en
  todas las pestañas y entradas: una pestaña vieja lo apagaba sola y no había forma de saberlo.
  Va en el servidor (`leer_panel.flag`, `pestanas_movil.json`).
- **`touch-action:none`** es lo que hace que existan los gestos propios; sin eso el navegador se
  queda el gesto. Los `gesturestart/change/end` de Safari se cancelan aparte.
- **En iOS el ícono sale del `apple-touch-icon`, NO del manifest**, y se congela al agregar a
  inicio: para cambiarlo hay que borrar el acceso y volver a agregarlo.
- **El micrófono del navegador exige HTTPS**: la app del celular anda por `tailscale serve
  --https=443` (certificado real dentro de la red privada).
- ⚠ **Un `time.sleep` adentro de un `async def` congela el panel entero.** Si la espera es
  bloqueante, el endpoint va con `def` normal y FastAPI lo manda a un hilo. Pasó dos veces
  (`/chat/mandar`, `/movil/hablar`).
- ⚠ **Cuidado con los emojis en cualquier texto que termine en un `print`**: un 🔊 mató el hilo
  del buzón y dejó a Laura muda por horas, sin ningún error visible.
- ⭐ **Bajar al final de una charla no es `scrollTop = scrollHeight`.** Las imágenes de las
  burbujas todavía no cargaron, ocupan alto cero, y al llegar empujan la conversación: hay que
  volver a bajar en el `load` de cada una. Y el contenedor es **el mismo** para todas las
  vistas, así que conserva el scroll de la pantalla anterior: al entrar a una vista hay que
  forzar la posición una vez (bandera `recienAbierta`), sin pisarla en los repintados.
- ⚠⚠ **Un turno pedido desde el celular muere a los 10 minutos** (`TIMEOUT = 600` en
  `app/voz/sesiones_movil.py`, `subprocess.run`). Si una tarea larga se pasa, el trabajo se
  hizo pero la pantalla muestra un error y la respuesta se pierde. Sin resolver.
- ⚠⚠ **Este tipo de sesión corre ADENTRO del panel** (`/movil/mandar` → `claude --resume`, en
  un `to_thread`). O sea que **reiniciar el panel mientras contestás mata tu propia
  respuesta**. Los cambios de `panel.py` se dejan en disco y se aplican en un reinicio hecho
  entre turnos, con Martín avisado — nunca en el medio de uno.

De la ventana de escritorio (`app/escritorio.py`), todos del 2026-08-17:

- ⚠⚠ **No le hables por JS a la ventana antes de que la página cargue.** Que exista la ventana
  de Windows no quiere decir que WebView2 haya terminado de arrancar adentro: un `evaluate_js`
  en el medio del arranque **le traba el hilo y la ventana queda NEGRA para siempre**, con todo
  lo que preguntes devolviendo `None` y sin un solo error. Va
  `ventana.events.loaded.wait(25)` primero. Media hora de "¿por qué no se ve nada?".
- ⭐ **`localhost` en Python cuesta 2 segundos en esta máquina** (prueba `::1` primero y se
  cuelga); por `127.0.0.1` y con un abridor sin proxy, 0,05 s. Y un puerto cerrado **no
  rebota**, se lo traga el firewall: darse cuenta de que algo está apagado siempre cuesta el
  timeout entero. Por eso el chequeo de salud va a `127.0.0.1` y con timeout corto. Lo mismo
  vale para cualquier prueba o vigilante que le pregunte al panel.
- **Para capturar una ventana de Windows: `PrintWindow` con `PW_RENDERFULLCONTENT`**, no una
  captura de pantalla. La ventana puede estar tapada por el Chrome de Martín, y traerla al
  frente le roba el foco en el medio (`SetForegroundWindow` encima falla si el pedido viene de
  un proceso de fondo). Y si sacás la captura por coordenadas, **el proceso que la saca tiene
  que ser DPI-aware** (`SetProcessDpiAwareness(2)`) o `GetWindowRect` te miente 1,5× y capturás
  la ventana de al lado. La receta entera está en `pruebas/ver_ventana_escritorio.py`.
- ⚠ El Chrome de Martín con el panel abierto **se llama igual que la ventana** ("Servidor IA"):
  para encontrar la de verdad hay que mirar además la clase (`WindowsForms…`).
- **La barra de título la dibuja Windows, no la página**, y a la ventana ACTIVA le pone el color
  de acento del sistema — que acá es un verde fosforescente que cortaba la pantalla al medio
  (Martín lo marcó con rojo el 2026-08-17). Se pinta con `DwmSetWindowAttribute` y los atributos
  35/36/34 (fondo, texto, borde), con el color **al revés** (`0x00BBGGRR`, no `0xRRGGBB`).
  ⚠ Hay que reintentar unas cuantas veces: al arrancar, `ventana.native` todavía no existe y el
  pintado se pierde en silencio.
- ⚠⚠ **`PrintWindow` NO muestra la barra de título pintada**: la dibuja siempre con el color por
  defecto (#202020). Medí ahí y vas a "comprobar" que el arreglo no anduvo cuando sí anduvo. Y
  al revés: una ventana **sin foco** tampoco muestra el verde. Para mirar la barra de verdad hay
  que capturar la PANTALLA con la ventana arriba (`HWND_TOPMOST` + `SWP_NOACTIVATE`, que la sube
  sin robarle el foco a Martín).
- ⭐⭐ **Para PRENDER algo escondido, `style.display = 'block'`, nunca `= ''`.** Poner `''` no
  enciende nada: borra el estilo de línea y devuelve el elemento a la regla del CSS. Si lo que lo
  escondía era el CSS (`#parar{…;display:none}`), el elemento vuelve a esconderse y **no aparece
  jamás**. Eso tenía el botón ⏹ Parar del celular: la charla pensaba hace cinco minutos y abajo
  solo estaban Avisame y Enviar, sin forma de cortar el turno desde el teléfono (captura de
  Martín, 2026-08-26). En `/sesiones` el mismo código andaba porque allá el `display:none` está
  en el propio tag, y ahí sí `''` lo muestra — o sea que **copiar la línea de una pantalla a la
  otra es justo lo que lo rompe**. Regla: si el elemento arranca escondido por CSS, prendelo con
  el display que corresponda. Prueba: `pruebas/ver_parar_en_celu.py`.

### El botón "⟳ Reiniciar todo" del encabezado del panel (2026-08-18)

Pedido de Martín por Telegram: reinicio completo — panel + todos los servicios — desde la
pantalla. `POST /reiniciar-todo` apaga los servicios, lanza suelto `lanzadores/Reiniciar
panel.bat` con el parámetro nuevo `auto` (relanza con `--auto`, que prende todo) y se deja
matar. ⚠ El gotcha está en el front: después de pedirlo hay que esperar a ver el panel
**MORIR y VOLVER** (`/status` en poll; recarga tras un error de red, o a los 15 s por si el
corte fue muy rápido). Si preguntás enseguida te contesta el panel viejo y la página se
recarga sin haber reiniciado nada. A los 2 minutos sin volver, el velo avisa que lo levanten
con el acceso del escritorio.

### Plan mode en las charlas de Codex, y el ⚡ en el celular (2026-08-25)

Pedido de Martín: *"no tengo la opción en codex para el modo plan, fijate bien"*. Tenía razón
y **estaba bloqueado a propósito**. Lo que apareció al investigar es lo que hay que saber:

⭐ **Codex SÍ tiene plan mode, pero no por donde entra el panel.** En el binario están las
pantallas ("Sí, implementá este plan"), el comando `/plan` y hasta un
`plan_mode_reasoning_effort` propio — pero eso vive en el canal **app-server**, el JSON-RPC que
usa la app de escritorio (`turn/start` con `collaborationMode`). El panel entra por
`codex exec`, y ahí no existe: probado, `-c collaboration_mode=plan` contesta textual
`unknown configuration field`. Traerlo nativo es rehacer el lanzador de Codex entero — hoy es
un proceso por turno, ahí sería un servicio con conexión abierta.

**Por eso el del panel es emulado, y lo que garantiza que no toque nada es la JAULA**
(`--sandbox read-only` en `codex_mandar`), no la instrucción. La instrucción
(`INSTRUCCION_PLAN_CODEX`) es un pedido; la jaula es un candado. **No sacarla "porque el
modelo ya entendió".**

⚠ **La diferencia con Claude, que es la que explica todo el diseño**: en Claude el proceso vive
entre turnos y el plan llega como un pedido de permiso, así que aprobar continúa el MISMO
turno contestando por stdin. En Codex el turno que dejó el plan **ya murió** cuando la tarjeta
aparece en pantalla. Por eso `/movil/plan` devuelve `mandar` con el texto del turno siguiente y
**lo manda la pantalla**, por `mandar()`: así hereda el semáforo de ocupada, el botón Parar, el
segundo plano y el hilo dibujándose en vivo, en vez de duplicar todo eso en el servidor.

- `mandar(forzado)` en las dos pantallas acepta un mensaje impuesto. **Se comprueba que sea
  texto y no un evento** (`typeof forzado === 'string'`): a `mandar` también la llaman desde un
  onclick y desde el Enter. Un mensaje impuesto **no vacía la caja ni se lleva tus fotos**.
- La tarjeta del plan de Codex **no repite el plan**: ya se lee arriba, en la respuesta. Viaja
  `codex: true` adentro de `pregunta` para que `htmlPlan` muestre solo la decisión.
- El bloqueo estaba en **un solo lugar**: `/movil/modelo` devolvía `"modos": []` para Codex, y
  las dos pantallas arman el selector con esa lista. Arreglarlo ahí lo hizo aparecer en las dos.

**El ⚡ Skills y comandos en el celular.** `MOVIL_HTML` era la única de las tres cajas de
escribir que nunca montó `atajos.js`. Ahora sí, con `etiqueta: '⚡'` (el nombre completo no
entra en el ancho del teléfono). En una charla de **Codex** el menú lista los **prompts de
Codex** (`~/.codex/prompts`), no las skills de Claude — decisión de Martín del 2026-08-23 —, y
si no hay ninguno **lo dice y explica dónde se crean**, en vez de salir en blanco.
⚠ **Esa decisión quedó revertida el 2026-08-28**: ver más abajo, la sección de ese día. La
premisa era falsa y el menú terminó enseñando algo que no era cierto.

⚠ **Gotcha que cazó la prueba de pantalla**: `.ajusSes select` tenía `min-width:0`, y al sumar
la cuarta perilla las pastillas **se aplastaron hasta quedar en la flechita sola**. La fila ya
sabe deslizarse (`overflow-x:auto`): ahora tienen `min-width:86px` y se lee lo que dicen. Si
agregás otra perilla al encabezado, mirá la captura — esto no se nota leyendo el código.

---

### La barra de escribir de /sesiones, agrupada por categoría (2026-08-25)

Dos capturas de Martín en el mismo día. La primera: *"esta barra para escribir está muy mal
cuando hago zoom"*. Con Chrome al 110 % la caja de escribir había quedado en **28 px de ancho**
—una rendija donde solo se veía la barra de scroll— y encima alta, porque cualquier frase
metida en 28 px se parte en treinta renglones (eso era su otra queja, *"queda grande el
cuadro"*, que no era del alto sino del ancho).

⭐ **La regla que explica el defecto: los botones no se achican y la caja era el único elástico
de la fila, así que TODO el recorte lo pagaba ella.** Y zoom del navegador (más la ampliación
de Windows) = menos píxeles CSS: su monitor de 2560 al 110 % son ~1590 px de ancho útil, y con
la fila cargada eso no alcanzaba.

El primer arreglo fue defensivo — `flex-wrap:wrap` + `min-width:280px` en el textarea, así los
botones del final bajan a un segundo renglón en vez de comerse el lugar de escribir. Con eso
llegó la segunda captura: *"mejor… pero no me gusta que se extiendan, sería mejor que se
compacten por categoría"*. **El wrap quedó igual, de red de seguridad**, pero ahora no se usa
porque la fila entra entera:

    [🖼 🔎 ⚡]  [=========== la caja ===========]  [⚙ Claude · Opus]  [183 k]  [🔔]  [Enviar]  [⏹]
     traer algo          donde escribís              esta charla        cuánto  aviso   mandar
                                                                      arrastra

- **Traer algo al mensaje** (subir imagen, buscar archivo, skills y comandos): pegados en
  `#grupoTraer`, con el dibujito solo y el nombre entero en el `title`. El ⚡ va con
  `etiqueta: '⚡'`, el mismo camino que ya usaba el celular.
- **Esta charla**: cerebro, modelo, esfuerzo, velocidad, modo, **Compactar** y **Revisar**, todo
  adentro del botón ⚙. El rótulo muestra **solo las dos primeras** perillas (cerebro y modelo):
  con las cinco se pasaba del tope de 250 px y quedaba cortado con puntos suspensivos.
- **Avisame quedó AFUERA**, como campanita: es una opción del envío y tiene que verse encendida
  de un vistazo, no escondida atrás de un clic.
- ⭐⭐ **La campanita también sirve con el turno YA corriendo** (pedido de Martín, 2026-08-29):
  es cuando de verdad se usa — te das cuenta de que la cosa viene larga *mientras* piensa, no
  antes de mandar. Hasta ese día era una bandera del navegador que se consumía al MANDAR, así
  que apretarla ahí **no hacía nada para ese turno** y encima quedaba armada en silencio para el
  mensaje siguiente. Tres reglas de este botón, que no se revierten:
  - **Manda el servidor, no el navegador.** El "quiero que me avises" vive en la ficha del
    trabajo (`_TRABAJOS_MOVIL[id]["avisar"]`) y `_correr_trabajo_movil` lo lee **al terminar**,
    no como argumento congelado al arrancar el hilo. Se prende y se apaga con
    `POST /movil/avisar` (`{sid, quiero}`), que busca el turno vivo de esa charla **por `sid` y
    por `sid_nuevo`** — una charla recién nacida cambia de id en el medio.
  - **La luz sale de `/movil/chat`** (campo `avisando`), no de la memoria del navegador: por eso
    sobrevive a un F5 y se ve encendida en la otra pantalla. ⚠ En `/sesiones` se pinta **antes**
    del corte por `firma`: mientras la sesión piensa el html no cambia y de ahí para abajo no se
    llega nunca.
  - **El aviso no se pierde en silencio.** Si apretaste justo cuando terminaba (menos de
    `AVISO_RECIEN_SEG`, 120 s), el aviso sale igual y la pantalla te lo dice; si no hay ningún
    turno vivo, el botón vuelve a valer para el próximo mensaje **y lo aclara** en vez de quedar
    encendido mintiendo. Ese era el otro defecto del celular: apagaba la variable pero no la
    clase `.sel`. Se prueba con `pruebas/probar_avisar_en_curso.py` (36 chequeos, `--viejo` 8/8).
- ⚠ **Compactar no lleva `data-cierra`.** Las acciones del menú lo cierran al apretarlas, pero
  Compactar **pregunta primero y se confirma con un segundo toque en el mismo botón**: si se
  cerrara con el primero, habría que reabrirlo para confirmar.
- ⚠ **La clase se llama `grupo-iconos`, no `grupo`.** `.grupo` ya existe en esta pantalla: es la
  píldora que agrupa las pestañas por proyecto. Con ese nombre, la fila de iconos se comía ese
  estilo y quedaba 14 px más alta que el resto (se midió así, no se dedujo).
- El alto de la caja se unificó en **`ajustarCaja()`** (una sola regla para escribir, abrir un
  borrador, pegar una ruta y mandar) y se **remide cuando cambia el ANCHO**, con un
  `ResizeObserver` que compara solo el ancho —ajustar el alto vuelve a disparar el observador—.
  Sin eso, sacar el zoom con texto escrito dejaba la caja con el alto de cuando era angosta.

**Medido** (`pruebas/ver_caja_zoom.py`, cuatro anchos + el zoom cambiado en caliente): a 1590 px
la caja pasó de **236 → 919 px**; a 1280, de **28 → 609 px**, en un solo renglón y sin desbordar.
Al mandar vuelve a 39 px en las tres pantallas (`/sesiones` 39, celular 44, chat del panel 40).

⚠ **Si movés algo de esta barra, corré también** `ver_caja_crece_compu`, `ver_botones_skills`,
`ver_modelo_sesion`, `ver_modelo_compactar` y `ver_plan_codex_y_atajos`: las cuatro últimas
tocan botones que ahora viven adentro del ⚙ y tienen que abrir el menú antes.

---

### El tamaño de los botones, y que no crezcan con el zoom (2026-09-12)

Pedido de Martín con una captura de `/sesiones` ampliada: *"me gustaría poder encojer más los
botones de la interfaz, o que queden en un tamaño fijo cuando llego a cierto grado de zoom"*.

⭐ **La causa, que es la continuación directa de la barra de arriba**: el texto de las
conversaciones ya tenía su multiplicador (`--escala`) desde el 2026-08-17, pero **los
controles estaban escritos en píxeles fijos** (38 px de alto, 14 px de letra). O sea que
ampliando la página para leer mejor, los botones se ampliaban igual y no había ninguna perilla
para achicarlos: la herramienta crecía junto con lo que uno vino a leer.

En el 🎨 hay una sección nueva, **Botones y barras**, con dos filas: el **tamaño**
(Mínimos ·72 / Chicos ·85 / Normales 1 / Grandes ·1,15) y **qué hacen con el zoom**
(Crecen / Quedan fijos). Sale de `app/estaticos/aspecto.js` y las pantallas lo leen como
`calc(38px * var(--ui,1))`.

- ⭐ **Es un MULTIPLICADOR, igual que `--escala`, y por la misma razón**: cada pantalla tiene
  sus medidas pensadas. `Normales` vale 1 y **no mueve un píxel** — verificado con
  `foto_pantallas.py`: 0 de 1.152.000 en `sesiones.png`. Una perilla nueva no puede moverle
  la pantalla a quien no elige nada.
- ⭐ **`--bh` (el alto de la fila) se define UNA vez, en `.caja`**, el padre de todos los
  controles de la barra de escribir. Antes el 38 estaba repetido en seis reglas y bastaba
  olvidarse de una para que un botón quedara más alto que sus vecinos.
- ⭐⭐ **"Quedan fijos" es compensar el zoom, y la referencia es del NAVEGADOR, no del
  aspecto.** `--ui` pasa a valer `paso × (ref / devicePixelRatio)`, donde `ref` es el dPR del
  momento en que se prendió (llave `aspectoZoomRef` del `localStorage`). Al doble de zoom, el
  botón mide la mitad en píxeles CSS: **el mismo tamaño real en pantalla**, y lo único que
  crece es el texto. ⚠ Esa referencia **no puede viajar al servidor**: el teléfono tiene otra
  densidad y otra ampliación de sistema, y con la de la laptop puesta ahí los botones saldrían
  de cualquier tamaño. Lo que viaja es la ELECCIÓN (`botones`, `botonesZoom`).
  ⚠ Y no puede vivir adentro de `aspecto` ni aunque el servidor la tirara: la respuesta de
  `/aspecto` hace `Object.assign({}, BASE, d)`, o sea que pisa el objeto entero y se la
  llevaría puesta apenas contesta.
- ⚠⚠ **El piso del tope se midió, no se eligió a ojo.** Con el primer número que puse (.55) el
  tope ya se tocaba **al 200 % de zoom**, o sea que "quedan fijos" dejaba de estar fijo justo
  en el zoom donde uno lo prende — y la prueba lo mostró porque mide el tamaño REAL, no el
  CSS. Quedó en `.40` (aguanta hasta el 250 %) con techo en 2. El tope igual hace falta: sin
  él, un zoom al 500 % deja botones de 8 px, imposibles de apretar.
- ⚠ El zoom se detecta por `devicePixelRatio` y se recalcula en el `resize` **solo si ese
  número cambió**: agrandar la ventana con el mouse dispara decenas de `resize` por segundo y
  ahí no hay nada que recalcular.
- ⚠ **`menu.js` también sigue a `--ui`**, y no es un detalle estético: con las pestañas
  achicadas y el menú de pantallas en su tamaño, media barra quedaba grande y la otra chica
  (se vio en la captura de la prueba). Su `medir()` cachea los tres anchos, así que un cambio
  de `--ui` después de medir deja el cache viejo — hoy no molesta porque `acomodar()` sale sin
  hacer nada cuando el menú no comparte renglón, y desde el 2026-08-18 no lo comparte.
  ⚠⚠ Y ahí me comí la trampa que el propio archivo avisa: **un acento invertido en un
  comentario corta el template literal** y `menu.js` dejó de ser JS válido. Lo cazó
  `node --check`, que es de correr siempre después de tocar ese CSS.
- ⚠⚠ **La trampa del 2026-08-25, otra vez**: un panel sin reiniciar no conoce los dos campos
  nuevos, los tira al reescribir el archivo y **la elección se pierde en el próximo F5**. Por
  eso la detección de "panel viejo" pregunta por la tanda MÁS NUEVA (`'botones' in guardado`) y
  `hayPartes()` incluye el tamaño elegido: el cartel ámbar aparece y lo dice.
- ⭐⭐ **El panel del 🎨 sigue a `--ui` él mismo** (segunda captura de Martín el mismo día:
  *"se ve re mal esto con el zoom"*, con el 🎨 abierto al 175 % ocupando la pantalla de arriba
  abajo). Era **el peor ofensor y el más fácil de pasar por alto**: es justo la pantalla que
  uno abre para arreglar el problema, así que si esa no achica, el arreglo no se siente. En su
  ventana (angosta y alta: ~822×1462 px CSS) el panel pasa de **290×1136 px, el 35 % del
  ancho**, a **209×842, el 25 %** — y con *Quedan fijos* al 175 % queda como si no hubiera
  zoom. Medido en `ver_tamano_botones.py`, que deja las dos fotos (`pruebas/paleta_*.png`).
  ⚠ Y por eso **el ancho al ubicarlo se MIDE** (`panel.offsetWidth`) en vez de los 290 px
  fijos de antes: con los botones en Grandes, la cuenta vieja lo dejaba salirse por la derecha.
- ⭐⭐ **El panel principal también sigue a `--ui`, y de paso se arregló su LAYOUT en dos
  columnas** (tercera captura del mismo día: *"este panel se ve muy mal"*, con `localhost:8750`
  en su **monitor vertical** — 1425×2380 px CSS). Eran dos cosas distintas y la segunda era la
  que de verdad molestaba:
  - El tamaño: 82 reglas del CSS de `PAGINA` pasaron a `calc(… * var(--ui,1))` con el mismo
    barrido dirigido. ⚠ **El `max-width` del `.wrap` quedó AFUERA a propósito**: achicar los
    controles es para ganar lugar, y escalando eso la pantalla entera se vuelve más angosta —
    lo contrario de lo pedido. ⚠ Y el `top`/`left` de la bolita del interruptor (`.sw::after`)
    hay que escalarlo con ella, o con el interruptor chico se sale del riel.
  - ⭐⭐ **El layout**: el panel tiene dos columnas, controles a la izquierda y *Conversación
    en vivo* a la derecha, en todo ancho por encima de 950 px. La lección que dejó un layout
    anterior de tres columnas: con `display:contents` una columna vacía deja **celdas
    sueltas** en la grilla, y la conversación terminaba en una segunda fila, abajo a la
    izquierda, en 360 px. Si se suma otra tarjeta al panel, medir la grilla en una pantalla
    alta y angosta antes de darla por buena.
- **Qué NO sigue a `--ui` todavía**: la app del celular (`/movil`), el Estudio y la Pizarra.
  La perilla existe y la elección viaja, pero hoy la obedecen `/sesiones`, el panel principal,
  el 🎨 y el menú de pantallas.
- Prueba: `pruebas/ver_tamano_botones.py` (31 chequeos; con `--viejo` caen los 8 clave, y la
  mutación de la detección de panel viejo se caza). Mide el tamaño **real** (píxeles CSS ×
  dPR), que es lo único que contesta la pregunta del pedido. ⚠ Intercepta `/aspecto` en las
  dos puntas: no le toca el aspecto de verdad a Martín.
  ⚠ `ver_config_aspecto.py` es **intermitente** en el chequeo *"el color elegido a mano
  también se guarda en el servidor"*: espera 600 ms al POST y cada tanto no llega. Falló una
  vez y pasó las dos siguientes sin tocar nada. No salir a buscarle causa a eso.
  ⚠⚠ Y `ver_aspecto_global.py` falla *"y el amarillo de 'trabajando' también"* **desde antes
  de esto y no es un defecto**: mide contra el ámbar de fábrica y el aspecto real de Martín
  tiene `aviso` en un beige elegido a mano (`#dfd1b9`). Es el mismo problema que se arregló el
  2026-08-29 para otras dos partes —la prueba mide su gusto— y a `aviso` le quedó pendiente.

---

## 6. Lo que está roto o pendiente HOY (2026-08-17)

Encontrado leyendo y midiendo, no reportado por Martín. En orden de cuánto molesta:

1. **"te está esperando" en las 56 conversaciones.** En la vista "Todas", el estado se calcula
   con `s.ultimo === 'claude'` (`sesiones.html`, `pintarLista`). Como casi toda charla termina
   con Claude hablando, **cada sesión archivada de hace 4 horas dice que te está esperando**:
   el aviso deja de significar algo. Debería mirar además si la sesión está viva y/o qué tan
   reciente es.
2. **La vista "Todas" se cierra sola cada 20 segundos.** `cargar()` hace
   `if (!datos.proyectos.some(p => p.proyecto === proy)) proy = …`, y `TODAS` no es un proyecto
   de la lista: en cada refresco te devuelve a una carpeta.
3. **Al abrir una pestaña desde "Todas", te saca de "Todas"**: `irTab()` pisa `proy` con el
   proyecto de la pestaña. Hay que decidir si en esa vista la marca se queda quieta.
4. **El panel contesta lento** — ✅ *la parte de `/movil/sesiones` está resuelta el
   2026-08-18*; queda lo demás. Confirmada la sospecha y medida: `listar()` tardaba 0,37 s y
   el 90 % era releer archivos que no habían cambiado. Lo que se hizo, y el porqué de cada
   cosa, está en "Entrar a Sesiones es instantáneo" más arriba: **0,37 s → 0,06 s** adentro,
   la respuesta se guarda 2 s en el servidor, y la pantalla se dibuja de una copia local sin
   esperar a nadie (**0,43 s la primera visita, 0,06 s las siguientes**).
   ⚠⚠ Lo que **sigue pendiente**: el panel llega a **59 % de CPU** con las pestañas de
   Martín abiertas, y ahí `/movil/sesiones` recalculado salta a 0,3-1,7 s aunque adentro
   sean 60 ms. O sea que el cuello ya no es esa función sino la CANTIDAD de pedidos:
   `/pensando` se consulta 3 veces por segundo **por pestaña abierta**. Antes de optimizar
   otra función, medir eso.
   `/status` ~0,65 s y `/pensando` 0,2-0,4 s bajo carga siguen sin tocar.
5. **El medidor de micrófono del panel** (`/medidor`) abre el micrófono con su propio código y
   **no** tiene la preferencia de WASAPI de `voz.py`: después de una suspensión puede fallar
   con un error de DirectSound aunque la voz esté escuchando perfecto.
6. **Inconsistencia en la pizarra**: el comentario de `bloqueado`/`libres` dice que un objeto
   bloqueado se puede seleccionar para cambiarle color y tipografía, pero `refrescarPanel()`
   esconde el panel y `aplicarASeleccion()` saltea lo bloqueado. O sobra el comentario o falta
   la funcionalidad.
7. **Sin probar apretándolo**: el botón 🔄 Nueva sesión del chat del panel (probarlo cortaba la
   charla en curso).
8. De la pizarra, acordado con Martín y **no empezado**: (1) lápiz de dibujo libre, (2) crear y
   cambiar entre varias pizarras.

---

### El ⚡ de una charla de Codex mentía: sí tiene las skills (2026-08-28)

Martín mandó una captura del menú ⚡ abierto en una charla de Codex. Decía dos cosas:
*"Todavía no tenés ningún prompt de Codex"* y, en el pie, **"Codex no usa las skills de
Claude: usa sus propios prompts"**. Las dos empujan a la misma conclusión —que Codex está
pelado— y las dos eran falsas desde el 2026-08-19.

⭐⭐ **Lo que la pantalla hizo mal no fue romperse: fue enseñar algo que no era cierto.** Un
botón roto se ve; un cartel que afirma algo se cree. Ese pie fue durante nueve días la fuente
de una creencia equivocada de Martín sobre su propia máquina, y de una conversación entera
planificando construir algo que ya existía.

**Lo que pasaba de verdad.** Las 14 skills de `~/.claude/skills` están enlazadas **una por
una** en `~/.codex/skills` (symlinks del 19/08; `kanban` se sumó el 24/08), más
`~/.agents/skills` —la ruta nueva que nombra la doc de Codex— donde vive `prompt-master`.
Codex las ve y las usa. Lo que está vacío es `~/.codex/prompts`, que es **otra cosa**: el
equivalente de un comando con barrita. El menú listaba solo eso y concluía de más.

- ⚠ **Los enlaces son uno por skill, no la carpeta entera.** Enlazar `~/.claude/skills` como
  carpeta rompe a **Claude Code**, que deja de cargar las skills de usuario. Eso no se toca.
- **Skills de Codex → `$nombre`. Prompts de Codex → `/nombre`.** La barrita es de Claude.
  Verificado contra el binario, no deducido: un `codex exec` con `$pizarra` contestó el
  comando exacto que está en el **cuerpo** del `SKILL.md`, o sea que lo abrió de verdad.
- **`grill-me` no aparece en la lista automática de Codex y no está rota**: su
  `agents/openai.yaml` tiene `allow_implicit_invocation: false`, así que Codex no la dispara
  sola. El menú la marca **"a pedido"** en vez de ofrecerla como si nada.
- **Las de fábrica (`~/.codex/skills/.system`: imagegen, skill-creator…) no se listan**, mismo
  criterio que del lado de Claude, donde el menú tampoco lista los comandos que trae el CLI.
- `usadas` / `proyecto` van **vacíos** en una charla de Codex: esas marcas se leen del `.jsonl`
  de Claude Code y el rollout de Codex tiene otro formato. Mejor sin marca que con una inventada.

⭐ **La herramienta para no volver a adivinar esto: `codex debug prompt-input "hola"`.** Imprime
el bloque `<skills_instructions>` con el nombre y la ruta de cada skill que Codex tiene cargada.
No gasta tokens ni ejecuta nada. Si algún día hay que volver a tocar este menú, se mira eso
primero.

⚠ **Y la trampa que hizo perder el tiempo**: buscar con `Glob` adentro de `~/.codex/skills`
dice que no hay nada, porque **no sigue symlinks**. Esa carpeta se mira con `ls -la`.

Dónde: `app/nucleo/skills.py` (`catalogo_codex()`, `_a_pedido()`), el endpoint `/skills` de
`panel.py` (devolvía `skills: []` a mano) y `pintarCodex()` en `app/estaticos/atajos.js`.
De paso, dos arreglos chicos del mismo menú: `/model` decía *"modelo de **Claude**"* también en
una charla de Codex, y una descripción entre comillas simples en el YAML (`notas`, `kanban`)
salía al menú con la comilla colgando adelante.

Pruebas: `pruebas/ver_skills_codex.py` (nueva, 13 chequeos, **no necesita el panel prendido**:
arma la página y sirve `atajos.js` del disco) y la sección nueva de `pruebas/probar_skills.py`.
**Verificada al revés**: `ver_skills_codex.py --viejo` le repone el defecto al archivo en
memoria y exige que los 8 chequeos clave fallen — fallan los 8. La mutación **no** sale de git
a propósito: `atajos.js` tenía cambios sin commitear, así que en `HEAD` el menú de Codex ni
existe y la comparación no probaría lo que dice probar.

---

## 7. Cómo trabaja esta sesión

- **Zona propia**: las pantallas de arriba y sus endpoints de pantalla. O sea `PAGINA`,
  `PAGINA_PIZARRA` y `MOVIL_HTML` adentro de `panel.py`, todo
  `app/estaticos/`, y las pruebas de pantalla en `pruebas/`.
- **Fuera de la zona**: `app/voz/voz.py` (micrófono, watchdog, TTS), `app/ingesta/`, el pipeline
  de Whisper. Si una pantalla necesita un dato que hoy no existe, el cambio de backend se
  acuerda antes — no se toca de prepo.
- **Reinicio del panel**: hace falta seguido para trabajar acá. Es un recurso de la máquina, así
  que si hay otra sesión trabajando, se avisa en `PIZARRA.md` antes.
- **Antes de tocar nada**: leer `PIZARRA.md` y anotar la tarea en "En curso"; al terminar,
  moverla a "Hecho" con lo aprendido. ⚠ El 2026-08-17 hubo **tres sesiones editando
  `sesiones.html` y `panel.py` al mismo tiempo** y convivieron de casualidad. El techo del
  proyecto es de 2 agentes.
- **Al terminar algo visible**, además: nota corta en `D:\IA\notas\Servidor IA.md` (prosa para
  Martín, sin detalle técnico: ese vive acá y en la Pizarra).
