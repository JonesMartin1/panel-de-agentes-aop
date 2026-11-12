/* El aspecto de TODAS las pantallas: fondo, tipografía y color.
 *
 * Nació adentro de sesiones.html el 2026-08-17 y valía para esa sola pantalla y para
 * ese solo navegador. Martín: "me gustaría poder llevar esta configuración visual
 * tanto a la interfaz de móvil como al resto de pestañas del panel". Así que vive acá,
 * como marcado.js y menu.js, y la elección se guarda en el SERVIDOR: elegís en la
 * compu y el teléfono queda igual.
 *
 * Cómo se usa en una pantalla:
 *     <script src="/estaticos/aspecto.js"></script>
 * y nada más. El botón 🎨 se mete solo adentro del menú de pantallas (`#menuPantallas`)
 * si esa página lo tiene; si no, en `#aspectoAqui`; y si no hay ninguno de los dos, no
 * dibuja botón — igual aplica el tema (es el caso de la pizarra dentro del iframe del
 * celular, que se viste sola pero no muestra el botón dos veces).
 *
 * Lo que la página tiene que hacer para aprovecharlo: usar las variables. Las de fondo
 * y tipografía se aplican solas al `body`; para el acento, cada pantalla engancha sus
 * propios colores a `var(--acento)` / `var(--acento-bg)` — son paletas escritas a mano
 * en momentos distintos y no hay forma de adivinarlas desde acá.
 *
 * ⚠ Dos reglas que acotan las opciones, y no son capricho:
 *   1. las tipografías son las que YA vienen con Windows: la app del celular tiene que
 *      abrir sin internet, así que nada de traerlas de una web;
 *   2. ningún acento de la fila puede ser verde, amarillo ni rojo: esos tres son el
 *      semáforo de estado de las conversaciones, y si el acento se les parece, el aviso
 *      deja de leerse de un vistazo. (Con la rueda se puede elegir uno igual: ahí la
 *      decisión es de Martín, la fila es lo que ofrecemos nosotros.)
 *
 * Lo que se puede elegir: tipografía, TAMAÑO del texto de las conversaciones, color de
 * acento —ocho a mano o cualquiera con la rueda—, fondo —cinco a mano o cualquiera con la
 * rueda—, foto de fondo, CUÁNTO SE VE esa foto, el color del rastro, el color de cada
 * parte, los efectos (sombra, vidrio, movimiento) y un "volver a lo de fábrica" que
 * deshace todo junto.
 *
 * ⭐⭐ El TEMA CLARO (2026-08-29) no es un fondo más: da vuelta la pantalla entera. Cómo
 * funciona está explicado arriba de `claroDe()`, y hay que leerlo antes de tocar colores
 * acá. En dos líneas: las pantallas escriben `var(--cRRGGBB,#rrggbb)`, el respaldo es el
 * color de siempre —así el tema oscuro queda idéntico sin depender de ningún cálculo— y
 * en claro este archivo barre el HTML y le calcula a cada uno su versión clara.
 *
 * ⚠ Al agregar un campo nuevo hay que sumarlo TAMBIÉN a la lista blanca de `/aspecto`
 * en `panel.py`: si no, se guarda en este navegador y no viaja al teléfono — o sea que
 * anda en la pantalla donde lo probaste y en ninguna otra.
 * ⚠⚠ El CSS de más abajo vive adentro de un template literal: un acento invertido en un
 * comentario CORTA la cadena y el archivo deja de ser JavaScript válido, en silencio.
 * Después de tocarlo: `node --check app/estaticos/aspecto.js`.
 */
(function () {
  const TIPOS = {
    segoe:   ['Segoe UI',      "'Segoe UI',system-ui,sans-serif"],
    georgia: ['Con serifa',    "Georgia,'Times New Roman',serif"],
    mono:    ['Monoespaciada', "Consolas,'Cascadia Mono',monospace"],
    verdana: ['Ancha',         "Verdana,'Segoe UI',sans-serif"],
    trebu:   ['Redondeada',    "'Trebuchet MS','Segoe UI',sans-serif"],
    // Las cuatro de abajo se sumaron el 2026-08-18 ("me gustaría más configuración").
    // Todas vienen con Windows: la app del celular tiene que abrir sin internet.
    cambria: ['Clásica',       "Cambria,Georgia,serif"],
    candara: ['Suave',         "Candara,'Segoe UI',sans-serif"],
    calibri: ['Delgada',       "Calibri,'Segoe UI',sans-serif"],
    comic:   ['Informal',      "'Comic Sans MS','Trebuchet MS',sans-serif"],
  };
  // ⭐⭐ Y CUALQUIER OTRA que esté instalada en la máquina (2026-08-29, pedido de Martín:
  // "me gustaría más efectos y estilos para las letras, aparte de poder seleccionar lo que
  // yo quiera"). Cuando `aspecto.tipo` no es una de las nueve claves de arriba, es el
  // NOMBRE de una fuente y se usa tal cual.
  //
  // ⚠⚠ El nombre se valida con una lista de caracteres permitidos ANTES de usarlo, porque
  // el valor viaja al servidor y vuelve a las cinco pantallas: basta con que algo escriba
  // una porquería en `aspecto.json` una vez.
  // ⚠ Medido, y no es lo que uno supone: por el camino de `setProperty` **no se puede**
  // inyectar CSS — el navegador trata el texto como el valor de una variable y no deja
  // cerrar la regla desde ahí. Se comprobó rompiendo el candado a propósito
  // (`ver_letra.py --mutar`): con la validación apagada, la pantalla igual se veía bien.
  // Lo que el candado sí evita es que ese texto se cuele donde el nombre SÍ se concatena
  // a mano (el `style="font-family:'X'"` de cada opción del desplegable) y que quede
  // guardado un valor con comillas esperando a que alguien lo use en otro lado.
  // ⚠ Y la regla vieja SIGUE valiendo para las nueve de la fila: son las que ya vienen con
  // Windows, porque la app del celular tiene que abrir sin internet. Una fuente elegida a
  // mano puede no existir en el teléfono; ahí cae en Segoe UI y el panel lo avisa.
  const FUENTE_OK = /^[A-Za-z0-9][A-Za-z0-9 .\-]{0,39}$/;
  const esFuenteLibre = v => typeof v === 'string' && !TIPOS[v] && FUENTE_OK.test(v);
  const familiaDe = v => TIPOS[v] ? TIPOS[v][1]
                       : esFuenteLibre(v) ? "'" + v + "'," + TIPOS.segoe[1]
                       : TIPOS.segoe[1];

  // Qué tipografías hay instaladas de verdad. Se mide el ancho de un texto con la fuente
  // pedida y con la genérica: si miden distinto, la fuente existe. Es la forma que anda sin
  // pedirle permiso a nadie y sin internet — `queryLocalFonts()` da la lista completa pero
  // abre un cartel de permiso, y en el teléfono no existe.
  // ⛔ La lista NO trae las de símbolos (Wingdings, Webdings, Marlett, Segoe MDL2): elegir
  // una de esas deja las cinco pantallas en jeroglíficos y ni el botón de volver se lee.
  const CANDIDATAS = ['Arial', 'Arial Black', 'Bahnschrift', 'Bookman Old Style', 'Calibri',
    'Cambria', 'Candara', 'Century Gothic', 'Comic Sans MS', 'Consolas', 'Constantia',
    'Corbel', 'Courier New', 'Ebrima', 'Franklin Gothic Medium', 'Gabriola', 'Gadugi',
    'Garamond', 'Georgia', 'Impact', 'Ink Free', 'Leelawadee UI', 'Lucida Console',
    'Lucida Sans Unicode', 'Malgun Gothic', 'Microsoft Sans Serif', 'MS Gothic', 'MV Boli',
    'Myanmar Text', 'Nirmala UI', 'Palatino Linotype', 'Perpetua', 'Rockwell', 'Segoe Print',
    'Segoe Script', 'Segoe UI', 'Sitka', 'Sylfaen', 'Tahoma', 'Times New Roman',
    'Trebuchet MS', 'Verdana', 'Yu Gothic'];
  let instaladas = null;

  function fuentesInstaladas(){
    if (instaladas) return instaladas;
    try {
      const lienzo = document.createElement('canvas').getContext('2d');
      const texto = 'mmmmmmmmmmlliWWW0O';
      const genericas = ['monospace', 'sans-serif', 'serif'];
      const patron = {};
      genericas.forEach(g => {
        lienzo.font = '72px ' + g;
        patron[g] = lienzo.measureText(texto).width;
      });
      instaladas = CANDIDATAS.filter(f => genericas.some(g => {
        lienzo.font = "72px '" + f + "'," + g;
        return lienzo.measureText(texto).width !== patron[g];
      }));
    } catch (e) {
      instaladas = [];      // sin canvas no se puede medir: queda la fila de nueve
    }
    return instaladas;
  }
  // Cuánto se agranda TODO el texto de las conversaciones. Es un factor y no un tamaño
  // fijo: cada pantalla tiene su medida pensada (la burbuja del celular es más grande
  // que la de la compu), y multiplicando se mantiene esa proporción.
  const LETRAS = {
    chica:  ['Chica',  .88],
    normal: ['Normal', 1],
    grande: ['Grande', 1.14],
    enorme: ['Enorme', 1.3],
  };
  // ⭐⭐ El tamaño de los BOTONES y las barras (2026-09-12, pedido de Martín con una
  // captura de `/sesiones` con el zoom arriba: "me gustaría poder encoger más los botones
  // de la interfaz, o que queden en un tamaño fijo cuando llego a cierto grado de zoom").
  //
  // El problema de fondo: el texto de las conversaciones ya tenía su multiplicador
  // (`--escala`), pero los controles estaban escritos en PÍXELES FIJOS (38 px de alto,
  // 14 px de letra), así que crecían tal cual con el zoom del navegador y no había con qué
  // achicarlos. Subiendo el zoom para leer, la barra de escribir se comía la pantalla.
  //
  // ⚠ Es un MULTIPLICADOR, igual que `--escala`, y por la misma razón: cada pantalla tiene
  // sus medidas pensadas y multiplicando se mantiene la proporción. `normal` vale 1 y no
  // mueve un píxel — se verifica con `foto_pantallas.py`.
  const BOTONES = {
    minimos: ['Mínimos',  .72],
    chicos:  ['Chicos',   .85],
    normal:  ['Normales', 1],
    grandes: ['Grandes',  1.15],
  };
  // ⭐ Y la segunda mitad del pedido: que pasado cierto zoom NO sigan creciendo. `fijo`
  // compensa el zoom del navegador, así los controles se quedan del tamaño REAL que tenían
  // cuando Martín dijo "este me gusta" y lo único que crece al ampliar es el texto.
  const ZOOM_BOTONES = {
    crece: ['Crecen con el zoom', 1],
    fijo:  ['Quedan fijos',       0],
  };
  // ⭐ Los EFECTOS DE LA LETRA (2026-08-29, misma tanda que la fuente libre).
  //
  // ⚠⚠ El valor de "normal" de cada uno tiene que ser EXACTAMENTE lo que la pantalla hace
  // hoy sin que nadie elija nada, o el cambio le mueve la pantalla a todo el mundo. Por eso
  // el interlineado normal es la palabra `normal` (lo del navegador, ~1.2) y NO 1.45, que
  // era el número que uno escribiría de memoria mirando el CSS de las burbujas: puesto ahí,
  // separaba todos los renglones que hoy no declaran interlineado. Lo mismo el espaciado.
  // Se verifica con `foto_pantallas.py`: cero píxeles distintos.
  const PESOS = {
    fina:    ['Fina',    '300'],
    normal:  ['Normal',  '400'],
    negrita: ['Negrita', '600'],
  };
  const ESPACIADOS = {
    juntas:  ['Juntas',  '-.012em'],
    normal:  ['Normal',  'normal'],
    sueltas: ['Sueltas', '.045em'],
  };
  const RENGLONES = {
    apretados: ['Apretados', '1.25'],
    normal:    ['Normal',    'normal'],
    aireados:  ['Aireados',  '1.7'],
  };
  // ⚠ El resplandor se arma en `aplicar()` con el acento, así que su valor acá va vacío.
  // ⚠⚠ Y una advertencia que no se puede probar sola: la prueba de contraste mide el COLOR
  // del texto contra el fondo, y una sombra o un resplandor NO cambian ese número. O sea
  // que estos dos efectos pueden empeorar la lectura sin que ninguna prueba lo cace. Por
  // eso el resplandor es flojo (7 px y .55 de alfa) y no el neón que uno querría.
  const LETRA_FX = {
    nada:       ['Sin efecto', 'none'],
    sombra:     ['Sombra',     '0 1px 2px rgba(0,0,0,.55)'],
    resplandor: ['Resplandor', ''],
  };
  const COLORES = {
    celeste:  ['#8ecbff', '#16233a'],
    violeta:  ['#c4b5fd', '#241d3a'],
    turquesa: ['#5eead4', '#10312c'],
    rosa:     ['#f9a8d4', '#331b28'],
    neutro:   ['#d7dee8', '#242c39'],
    // Sumados el 2026-08-18. ⚠ Ninguno se acerca al semáforo: el arena es una crema
    // apagada, nada que ver con el ámbar fuerte (#f59e0b) de "trabajando".
    azul:     ['#7aa2ff', '#151f38'],
    fucsia:   ['#f0abfc', '#2e1936'],
    arena:    ['#e2cdb0', '#2b2418'],
  };
  // El cuarto valor es la bandera de TEMA CLARO. Los tres oscuros son los de siempre.
  // ⚠ Estos cinco son los que se OFRECEN; el fondo puede ser cualquier color elegido con
  // la rueda, y entonces `aspecto.fondo` no es una clave de acá sino un '#rrggbb'. Todo lo
  // que necesite el fondo tiene que pedirlo a `fondoDe()`, nunca a `FONDOS[aspecto.fondo]`.
  const FONDOS = {
    azulado: ['Azulado', '#0b0d12', '#0f1320'],
    negro:   ['Negro',   '#07080b', '#0c0f16'],
    carbon:  ['Carbón',  '#121317', '#191c23'],
    // ⭐⭐ Los claros (2026-08-29). No son "otro color de fondo": dan vuelta la pantalla
    // entera, porque cada gris escrito en las pantallas está enganchado a una variable
    // `--cRRGGBB` que acá se recalcula. Ver `tintasClaras()`.
    claro:   ['Claro',   '#f2f4f8', '#ffffff', true],
    papel:   ['Papel',   '#f6f2e9', '#fffdf7', true],
  };
  // Cuánto velo negro va ENCIMA de la foto de fondo. Con una foto clara el texto se
  // pierde y con una oscura sobra velo, así que se elige (2026-08-18). Solo aparece
  // cuando hay foto puesta: sin foto no vela nada.
  const VELOS = {
    full:   ['Se ve a full', .34],
    media:  ['Media',        .62],
    apenas: ['Apenas',       .82],
  };
  // ⭐ El color del RASTRO: los renglones que cuentan lo que la sesión va haciendo
  // (2026-08-28, pedido de Martín: "¿podría elegir el color?"). Es el texto del bloque;
  // el fondo del bloque sale de ahí, apenas teñido, así que con elegir uno alcanza.
  // `tema` no es un color: es "seguí el acento", que es lo que hace todo lo demás.
  const RASTROS = {
    tema:   ['El del tema', ''],
    apagado:['Apagado',     '#93a0b4'],
    gris:   ['Gris',        '#7c8797'],
    verdoso:['Verdoso',     '#8fd0b8'],
    lila:   ['Lila',        '#c0b1e8'],
    ambar:  ['Ámbar',       '#dcc08a'],
  };
  // ⭐⭐ Los colores POR PARTE (2026-08-29, pedido de Martín: "quiero poder editar el color
  // de algunos elementos… no solo de la pizarra, también del panel principal"). Hasta hoy
  // había UN acento para todo; ahora cada parte puede tener el suyo.
  //
  // ⚠ Cada una vale `''` = "seguí al tema", que es exactamente lo de antes: sin elegir
  // nada, la pantalla se ve igual que ayer. Un color elegido es siempre '#rrggbb'.
  // ⚠⚠ El verde, el rojo y el ámbar NO son un gusto: son el semáforo (encendido, caído,
  // atención). Se pueden cambiar igual —es su pantalla— pero por eso el que arranca puesto
  // es el de fábrica y no el acento: si el semáforo sigue al tema, deja de avisar.
  const PARTES = {
    burbujaVos: ['Tu burbuja',            ''],
    burbujaIa:  ['Burbuja de la sesión',  ''],
    ok:         ['Encendido',             '#3ddc84'],
    mal:        ['Apagado o roto',        '#ef4444'],
    aviso:      ['Atención',              '#f59e0b'],
    // ⭐ El cuarto color de estado (2026-11-10): una sesión que frenó a PREGUNTARTE algo.
    // Amarillo, y en la pantalla es el único que parpadea. Vive acá, con los otros tres,
    // para que se pueda elegir desde el 🎨 y para que ninguna pantalla lo escriba a mano
    // (regla `semaforo-en-variables`). ⚠ Hoy solo lo usa /sesiones. ⚠ El panel todavía
    // no lo tiene en la lista de campos que guarda (`/aspecto` en panel.py): un color
    // elegido acá vale en este navegador y se pierde al recargar, hasta que se lo agreguen.
    pregunta:   ['Te pregunta algo',      '#ffd60a'],
    barra:      ['Barra de arriba',       ''],
    pizBarra:   ['Barra de la pizarra',   ''],
  };
  // ⭐⭐ Los BLOQUES del panel principal (2026-08-29, "más colores sobre el panel"): las
  // siete zonas con título. Cinco viven adentro de UNA sola tarjeta, separadas por una
  // línea fina, y dos son tarjetas aparte — por eso se marcan con `data-bloque` en el HTML
  // de `PAGINA` y no se buscan por posición: un `nth-child` se rompe el día que se agrega
  // una tarjeta, y acá ya se agregó una (el testing adversarial) esta misma semana.
  //
  // ⚠ Se pinta el TÍTULO y un filito al costado, nada más. Martín eligió eso sobre el
  // borde entero y sobre el fondo: siete marcos de siete colores compiten entre sí y con
  // el semáforo, y sobre un fondo de color el texto apagado de las explicaciones se pierde.
  // El segundo valor es el lugar en la rueda de matices (ver `girar`).
  const BLOQUES = {
    servidor:    ['Servidor',             0],
    voz:         ['Voz',                  1],
    placa:       ['Placa de video',       2],
    sesiones:    ['Sesiones',             3],
    adversarial: ['Testing adversarial',  4],
    vivo:        ['Conversación en vivo', 6],
  };
  // Cuánto se gira el matiz de un bloque al siguiente. ⚠ 150° y no 45°, que es lo que
  // parecía razonable: con 45° los bloques quedan repartidos en la rueda pero los que se
  // ven UNO AL LADO DEL OTRO salen casi iguales (Servidor y Voz, los dos fucsia — se vio
  // en la captura). Girando de a 150° y dando vueltas, la lista queda 0-150-300-90-240-30-180:
  // cada bloque contrasta con el de arriba y con el de abajo, que es cuando sirve.
  const PASO_BLOQUE = 150;

  // ⭐ Los EFECTOS (2026-08-29, pedido de Martín: "me gustaría poder cambiar más
  // características"; de cuatro que le ofrecí eligió esto y el modo claro).
  //
  // La sombra sale de cuatro peldaños (`--sombra-0` a `--sombra-3`, de la más pegada a
  // la más despegada) y NO de escribirla en cada regla: antes había catorce sombras de
  // elevación distintas repartidas en las pantallas, casi todas variaciones de las
  // mismas tres. `normal` reproduce lo de siempre; los otros escalan el desplazamiento,
  // el desenfoque y cuánto tapan.
  // ⚠ Las sombras que NO son decoración —el aro de foco, el `inset` que marca lo
  // seleccionado, el resplandor del punto encendido— no entran acá: son señales, y
  // apagarlas dejaría a la pantalla sin decir dónde estás parado.
  const SOMBRAS = {
    nada:    ['Sin sombra', 0],
    suave:   ['Suave',      .5],
    normal:  ['Normal',     1],
    marcada: ['Marcada',    1.4],
  };
  // Cuánto se ve a través de las barras y los menús flotantes. `normal` es lo de hoy
  // (las cuatro pantallas ya tenían algún `backdrop-filter`); `mucho` además vuelve
  // translúcidas las superficies, que es donde se nota con una foto de fondo puesta.
  const VIDRIOS = {
    nada:   ['Opaco',   0],
    normal: ['Normal',  1],
    mucho:  ['Vidrio',  1.7],
  };
  // ⭐ El desenfoque también puede ser un NÚMERO (2026-11-10, Martín: "siento que tengo
  // limitaciones a la hora de configurar el vidrio"): el deslizador del 🎨 guarda '1.35'
  // y los estilos siguen guardando 'nada' / 'normal' / 'mucho'. Las dos cosas valen.
  const desenfoqueDe = v => VIDRIOS[v] ? VIDRIOS[v][1]
    : (isFinite(parseFloat(v)) ? Math.max(0, Math.min(3, parseFloat(v))) : 1);
  // ⭐ Y el material del estilo Vidrio, que hasta ese día era todo número fijo en la hoja
  // de Sesiones: cuánto tapan los paneles, de qué color es el vidrio, cuánto brilla su
  // borde y cuánto grano tiene. Vacío = el de fábrica, y entonces no se escribe nada y
  // manda la hoja (ver `vidrioFino()`).
  const VD_CAMPOS = ['vdOpaco', 'vdTinte', 'vdBrillo', 'vdGrano'];
  const VD_FAB = {vdOpaco: 20, vdBrillo: 100, vdGrano: 100};
  const VD_TINTES = {
    '':      ['Sin tinte', ''],
    ahumado: ['Ahumado',   '#262a33'],
    azulado: ['Azulado',   '#4f86c6'],
    calido:  ['Cálido',    '#c08a5a'],
    verde:   ['Verdoso',   '#5f9e86'],
  };
  // ⚠ El movimiento se apaga con una clase en el <html> y una regla que gana por
  // `!important`, no tocando las cincuenta animaciones una por una. `poco` apaga los
  // latidos (lo que se mueve solo, para siempre) y deja las transiciones del hover, que
  // son respuesta a lo que hacés; `nada` apaga también esas.
  const MOVIS = {
    normal: ['Normal',        ''],
    poco:   ['Sin latidos',   'movi-poco'],
    nada:   ['Quieto',        'movi-nada'],
  };
  // ⭐⭐ LOS ESTILOS (2026-08-29). Martín pidió poder pintar cuatro zonas más y, puesto a
  // elegir entre veinte perillas sueltas o combinaciones ya armadas, eligió las
  // combinaciones: *"más colores sobre el panel"* no era "quiero elegir veinte veces".
  //
  // Un estilo pisa TODO lo de color de una sola vez —fondo, acento, tinte de letras y de
  // cajas, semáforo, barras, burbujas y efectos— y guarda lo que había en `previo`, que es
  // lo que hace posible el "volver a lo mío". Decisión suya sobre las otras dos opciones
  // (que no pise nada elegido a mano quedaba a medias y no se entendía por qué).
  //
  // ⚠⚠ Un estilo SÍ trae su tipografía y su efecto de letra (2026-08-29, segunda tanda:
  // "más efectos y estilos para las letras"), pero **nunca el TAMAÑO del texto**. La
  // distinción no es caprichosa: la tipografía es estética y el tamaño es que se vea.
  // Pisarle el "Enorme" a alguien que lo puso porque lee mejor así sería una grosería
  // disfrazada de estilo. Tampoco se toca la foto de fondo ni cuánto se ve.
  // ⚠ Ningún acento es verde, amarillo ni rojo: son el semáforo. Por eso "Terminal" es
  // turquesa y no verde fósforo, que es la referencia obvia y estaba a mano.
  // ⚠ De los tintes solo cuenta el MATIZ: `tenida()` conserva la luminosidad de cada gris,
  // así que poner un marrón claro o uno oscuro da el mismo resultado. Se eligieron a la
  // vista igual, para que se entiendan leyendo.
  const LIMPIO = {burbujaVos: '', burbujaIa: '', ok: '', mal: '', aviso: '', pregunta: '', barra: '',
                  pizBarra: '', rastro: 'tema', bloques: {}, tintaLetras: '',
                  tintaCajas: '', sombra: 'normal', vidrio: 'normal', movi: 'normal',
                  // El material del vidrio (2026-11-10): un estilo lo deja de fábrica.
                  vdOpaco: '', vdTinte: '', vdBrillo: '', vdGrano: '',
                  // La letra, menos el tamaño (ver arriba).
                  tipo: 'segoe', tipoTitulo: '', peso: 'normal', espaciado: 'normal',
                  renglon: 'normal', letraFx: 'nada'};
  const ESTILOS = {
    terminal: {nom: 'Terminal', bloques: true, campos: {
      fondo: 'negro', color: '#2dd4bf', tintaLetras: '#5eead4', tintaCajas: '#0f766e',
      sombra: 'nada', vidrio: 'nada', tipo: 'mono', espaciado: 'sueltas'}},
    calido: {nom: 'Nocturno cálido', bloques: true, campos: {
      fondo: 'carbon', color: '#e2cdb0', tintaLetras: '#f0d9b5', tintaCajas: '#4a3b28',
      sombra: 'suave', tipo: 'cambria', renglon: 'aireados'}},
    // ⚠ El acento es AZUL TINTA y no el terracota que pedía el papel: un terracota tira a
    // rojo y el rojo es el semáforo. Lo cazó `ver_estilos.py`, que mide el matiz de cada
    // acento contra los tres del estado. Papel crema con tinta azul y letras marrones.
    papel: {nom: 'Papel', bloques: true, campos: {
      fondo: 'papel', color: '#3f6ea8', tintaLetras: '#8b5e34', tintaCajas: '#d9c3a5',
      sombra: 'suave', vidrio: 'nada', tipo: 'georgia', renglon: 'aireados'}},
    neon: {nom: 'Neón', bloques: true, campos: {
      fondo: 'negro', color: '#f0abfc', tintaLetras: '#d8b4fe', tintaCajas: '#4c1d95',
      sombra: 'marcada', vidrio: 'mucho', tipo: 'trebu', letraFx: 'resplandor'}},
    nordico: {nom: 'Nórdico', bloques: true, campos: {
      fondo: 'azulado', color: '#7aa2ff', tintaLetras: '#bcd0f5', tintaCajas: '#1e3a5f',
      tipo: 'calibri', tipoTitulo: 'cambria'}},
    // ⭐ Grok (2026-10-31, Martín mirando Grok Bot): negro neutro, tu burbuja naranja y
    // formas de pastilla. Nació siendo el único estilo que además CAMBIA FORMAS y mueve
    // cosas (partículas, entradas suaves). ⭐ Desde el 2026-11-10 esas formas son de TODOS
    // los estilos, que pasaron a ser sub-versiones de este: la clase `estilo-grok` se pone
    // con cualquiera, y `grok-puro` solo con este. Ver `aplicar()` y `CSS`.
    // ⚠ El acento es DURAZNO y no el naranja fuerte: un naranja saturado se lee como el
    // rojo del semáforo (`ver_estilos.py` lo mide). El naranja va en tu burbuja, que no
    // es una señal. Y "trabajando" pasa a CELESTE: con burbujas naranjas, un ámbar al
    // lado se confunde con ellas.
    // La foto de fondo no se toca (ningún estilo pisa `img` ni `velo`): sigue siendo la
    // misma en la compu y en el celular.
    grok: {nom: 'Grok', bloques: false, campos: {
      fondo: 'negro', color: '#fed7aa', burbujaVos: '#c2410c', burbujaIa: '#a1a1aa',
      aviso: '#38bdf8', sombra: 'suave', vidrio: 'mucho'}},
    // ⭐⭐ Carta celeste (2026-11-10). Martín: *"se sigue viendo como una aplicación
    // ordinaria; quiero que sea premium"*. No es un séptimo color: es un REDISEÑO, elegido
    // por él entre cuatro bocetos. El fondo es azul noche, la tinta es tiza y cada agente
    // es un punto de una carta del cielo (el tamaño y el anillo dicen el estado).
    // ⚠ La pantalla que lo dibuja entero es /sesiones, que se anota con `data-carta` en su
    // `<html>`: ahí va la clase `carta` y NO las formas de Grok. Las demás pantallas y el
    // celular todavía no tienen su dibujo: toman esta paleta y esta letra sobre las formas
    // de Grok, sin partículas (lo que él NO quiere es que quede recargado).
    // ⚠ El acento es un blanco azulado ("luz de estrella"): lejos del verde, el ámbar y el
    // rojo del semáforo. "Trabajando" va en celeste, como en Grok.
    // ⚠ `tipo: 'Archivo'` no viene con Windows: viaja adentro de este archivo, ver
    // `FUENTES_CARTA`. Sin eso caería en Segoe UI y sería la pantalla de siempre en azul.
    celeste: {nom: 'Carta celeste', bloques: false, campos: {
      fondo: '#080d1b', color: '#cfe0ff', tintaLetras: '#c9d4f2', tintaCajas: '#16204a',
      aviso: '#7fd0ff', sombra: 'nada', vidrio: 'nada', tipo: 'Archivo'}},
    // ⭐⭐ Vidrio (2026-11-10). Carta celeste quedó puesta y Martín dijo "no me termina de
    // cerrar, quiero más ejemplos"; de una segunda mano de cuatro bocetos eligió este:
    // paneles de vidrio esmerilado flotando sobre SU foto de fondo, estilo Apple.
    // Usa el MISMO casco que Carta celeste (la clase `carta`: riel de arriba abajo, charla
    // como columna de lectura, caja en una pieza) y encima le pone otra piel (la clase
    // `vidrio`). Sin estrellas en cursiva ni franja "esta noche": acá la firma es la
    // profundidad — la foto, los paneles y el contenido son tres planos.
    // ⚠ Este estilo NECESITA una foto atrás. No pisa la tuya (`img` no está en `campos`):
    // si no elegiste ninguna, muestra la del escritorio de Windows sin guardarla, y el velo
    // se afloja un escalón porque el vidrio ya oscurece por su cuenta. Ver `ponerFoto()`.
    // ⚠ La letra es Segoe UI Variable, que viene con Windows 11: no hay nada que embeber.
    vidrio: {nom: 'Vidrio', bloques: false, campos: {
      fondo: '#0b1020', color: '#f2f6ff', tintaLetras: '#e3e9f8', tintaCajas: '#1b2440',
      aviso: '#7fd0ff', sombra: 'suave', vidrio: 'mucho', tipo: 'Segoe UI Variable Display'}},
    // ⭐ Vidrio con bandeja (2026-11-11). Martín vio el boceto "Bandeja" (riel de íconos +
    // lista de charlas al lado, como un correo) y pidió: "crealo como estilo nuevo con la
    // temática que ya tengo". Es la MISMA piel de Vidrio (lleva las clases `carta` y
    // `vidrio`) y suma `vbandeja`: las carpetas se achican a una tira de emojis y la lista
    // de charlas de la carpeta queda siempre a la vista al lado de la charla abierta.
    // ⚠ Esa columna se había descartado el 2026-08-16 para la pantalla de siempre; acá
    // vuelve SOLO como estilo a elección. Los demás estilos no la ven. Ver INTERFAZ.md.
    vbandeja: {nom: 'Vidrio con bandeja', bloques: false, campos: {
      fondo: '#0b1020', color: '#f2f6ff', tintaLetras: '#e3e9f8', tintaCajas: '#1b2440',
      aviso: '#7fd0ff', sombra: 'suave', vidrio: 'mucho', tipo: 'Segoe UI Variable Display'}},
  };
  // Los estilos que llevan la piel de vidrio (y por eso siempre una foto atrás).
  const deVidrio = () => aspecto.estilo === 'vidrio' || aspecto.estilo === 'vbandeja';

  const BASE = {tipo: 'segoe', color: 'celeste', fondo: 'azulado', img: '',
                letra: 'normal', velo: 'media', rastro: 'tema',
                // ⭐ El tamaño de los botones y qué hacen con el zoom (2026-09-12).
                // ⚠ A propósito NO están en `LIMPIO`: un estilo pinta, no le cambia a
                // nadie el tamaño de los controles — misma razón que el tamaño del texto.
                botones: 'normal', botonesZoom: 'crece',
                burbujaVos: '', burbujaIa: '', ok: '', mal: '', aviso: '', pregunta: '',
                barra: '', pizBarra: '',
                sombra: 'normal', vidrio: 'normal', movi: 'normal',
                vdOpaco: '', vdTinte: '', vdBrillo: '', vdGrano: '',
                // ⭐ Los efectos de la letra (2026-08-29). `tipo` ahora también puede ser
                // el nombre de una fuente instalada, no solo una de las nueve claves.
                tipoTitulo: '', peso: 'normal', espaciado: 'normal',
                renglon: 'normal', letraFx: 'nada',
                // ⭐ El tinte de las letras y de las cajas, y el color de cada bloque del
                // panel (2026-08-29). Vacío = como siempre. Ver `tenida()` y `BLOQUES`.
                tintaLetras: '', tintaCajas: '', bloques: {},
                // El estilo puesto y la copia de lo que había antes de aplicarlo, que es
                // lo que hace posible el "volver a lo mío". Ver `ESTILOS`.
                estilo: '', previo: null};
  // La foto del escritorio: no es un archivo fijo, es "lo que Windows tenga puesto".
  const FOTO_WINDOWS = '/fondo/windows';
  let versionFondo = '';

  // ⭐ Lo de fábrica es el estilo Vidrio (2026-11-11, Martín: "cualquier persona que se
  // descargue el panel, el primer tema que le aparezca sea el del vidrio"). `BASE` sigue
  // siendo el piso de campos y "El de siempre" (`sacarEstilo`) sigue volviendo a la paleta
  // vieja: esto solo cambia con qué arranca quien todavía no eligió NADA.
  // ⚠ Se usa solo si el navegador no tiene nada guardado: un aspecto viejo, de antes de que
  // existiera el campo `estilo`, no trae esa llave y se le pondría Vidrio sin pedirlo.
  const FABRICA = Object.assign({}, BASE, LIMPIO, ESTILOS.vidrio.campos, {estilo: 'vidrio'});
  const guardadoLocal = leerLocal();
  let aspecto = Object.assign({}, Object.keys(guardadoLocal).length ? BASE : FABRICA,
                              guardadoLocal);

  function leerLocal(){
    try { return JSON.parse(localStorage.getItem('aspecto') || '{}'); }
    catch (e) { return {}; }
  }

  // #rrggbb -> rgba(): con foto de fondo las superficies se vuelven translúcidas, si no
  // la foto queda tapada por las barras y las columnas.
  // Mezcla dos colores (0..1 = cuánto del primero). Se hace a mano y no con
  // `color-mix` de CSS para que ande igual en cualquier navegador, y porque así el
  // valor queda calculado una vez y no en cada repintado.
  const canal = (h, i) => parseInt(h.substr(i, 2), 16);
  function mezcla(a, b, p){
    const c = i => Math.round(canal(a, i) * p + canal(b, i) * (1 - p));
    return 'rgb(' + [c(1), c(3), c(5)].join(',') + ')';
  }
  // La misma mezcla pero devuelta en '#rrggbb'. Hace falta cuando el resultado se vuelve a
  // mezclar o se le pone transparencia: `mezcla()` y `conAlfa()` leen los dígitos del hex
  // a mano con `substr`, así que pasarles un `rgb(…)` devuelve cualquier cosa (y sin
  // romperse, que es lo peor). Se usa para el fondo elegido con la rueda.
  function mezclaHex(a, b, p){
    const c = i => Math.round(canal(a, i) * p + canal(b, i) * (1 - p));
    return '#' + [c(1), c(3), c(5)].map(v => v.toString(16).padStart(2, '0')).join('');
  }

  const conAlfa = (hex, a) =>
    'rgba(' + [1, 3, 5].map(i => parseInt(hex.substr(i, 2), 16)).join(',') + ',' + a + ')';

  // ---- El modo claro -------------------------------------------------------------
  // ⭐⭐ Cómo funciona, porque no es evidente y es lo que lo hace barato (2026-08-29).
  //
  // Las pantallas tenían 749 colores escritos a mano, 196 distintos. No eran una paleta:
  // eran acumulación (había cuatro grises azulados casi iguales). Un tema claro escrito
  // a mano habría sido reescribir cinco pantallas y mantenerlas en dos versiones para
  // siempre. En vez de eso, cada color de las pantallas quedó así:
  //
  //     border:1px solid var(--c232a35,#232a35)
  //
  // El respaldo es el color de SIEMPRE. Mientras el tema sea oscuro nadie define esas
  // variables y la pantalla se ve exactamente igual que antes — no hay que creerlo, es
  // cómo funciona `var()` (verificado igual: cinco capturas, cero píxeles distintos).
  // En modo claro, acá se barren las hojas de estilo, se juntan los `--cRRGGBB` que
  // existen y se le calcula a cada uno su versión clara. Un color nuevo que alguien
  // escriba mañana con esa forma entra solo, sin tocar este archivo.
  const NOMBRE_TINTA = /--c([0-9a-f]{6})\b/g;
  let tintas = null, tintasHojas = -1;

  function tintasDeLaPagina(){
    // ⚠ El resultado se guarda, pero se vuelve a barrer si aparecieron hojas nuevas. La
    // primera vez que corre esto, el <style> de este mismo archivo TODAVÍA NO EXISTE
    // (`aplicar()` se llama antes que `armar()`), así que con guardarlo para siempre el
    // botón 🎨 y su panel se quedaban oscuros adentro de una pantalla clara.
    const hojas = document.querySelectorAll('style');
    if (tintas && hojas.length === tintasHojas) return tintas;
    tintasHojas = hojas.length;
    // ⚠⚠ Se busca en TODO el HTML, no solo en las hojas de estilo. Un color puede estar
    // en un `style="..."` pegado al elemento (el botón "Reiniciar todo" es así) o adentro
    // de un `<script>` que arma la pantalla — y esos dos no aparecen en ningún <style>.
    // Mirando solo las hojas, esos colores se quedaban en su versión oscura: texto gris
    // claro sobre fondo blanco, o sea invisible.
    // ⚠⚠ Con `?.`, y no es un adorno: este archivo corre APENAS se lee, y en la app del
    // celular eso pasa antes de que exista el <body>. Sin la guarda, `document.body` es
    // null, revienta el barrido y se muere el archivo ENTERO — la pantalla queda sin
    // botón 🎨 y sin acento, y nada avisa. (Lo cazó la comparación de capturas, no una
    // prueba de colores: la pantalla se veía "casi bien".) Cuando `armar()` inyecta su
    // hoja, cambia la cantidad de <style> y esto se vuelve a barrer con el body ya puesto.
    const vistas = new Set();
    const todo = (document.head ? document.head.innerHTML : '') +
                 (document.body ? document.body.innerHTML : '');
    let m;
    NOMBRE_TINTA.lastIndex = 0;
    while ((m = NOMBRE_TINTA.exec(todo))) vistas.add(m[1]);
    tintas = [...vistas];
    return tintas;
  }

  const luzDe = (r, g, b) => (.2126 * r + .7152 * g + .0722 * b) / 255;

  // La versión clara de un color oscuro (y al revés). Se da vuelta la LUMINOSIDAD y se
  // conserva el matiz, así el azulado sigue azulado y el violeta de Codex sigue violeta.
  //
  // ⚠ La vuelta no es simétrica y no es un descuido: un gris claro sobre blanco contrasta
  // menos que su espejo oscuro sobre negro. Por eso lo que era superficie se va a la franja
  // .78-1 (fondos que se distinguen apenas entre sí) y lo que era tinta se va a 0-.52
  // (textos que se leen). El corte en .62 sale de mirar dónde caen: los fondos de las
  // pantallas están todos abajo de .25 de luz y los textos arriba de .40.
  function claroDe(hex){
    const c = [1, 3, 5].map(i => parseInt(hex.substr(i, 2), 16));
    const y = luzDe(c[0], c[1], c[2]);
    const inv = 1 - y;
    // ⚠⚠ Un color CON COLOR nunca se va a la franja de las superficies, aunque su
    // luminosidad diga que sí. El rojo de "roto" (#ef4444) tiene la luz justo arriba del
    // corte, así que con la cuenta de los grises salía un rojo CLARITO: invisible sobre
    // un fondo blanco, y encima dejaba de gritar, que es su único trabajo. Los que tienen
    // color van siempre a la franja de tinta, y ahí siguen siendo rojo, verde y ámbar.
    // ⚠ Y se lo encierra entre .20 y .42: abajo de eso el verde de "encendido" quedaba
    // casi negro y el ámbar, marrón — se leen, pero dejan de ser un color que uno
    // reconoce de reojo, que es todo lo que hace un semáforo.
    const obj = cromatico(c) ? Math.min(.42, Math.max(.20, inv * .55))
              : inv >= .62 ? .78 + (inv - .62) / .38 * .22 : inv / .62 * .52;
    return aHex(aLuz(c, obj));
  }

  // Llevar un color a una luminosidad objetivo CONSERVANDO EL MATIZ: aclarando hacia el
  // blanco o escalando hacia el negro. Estaba adentro de `claroDe()`; salió afuera cuando
  // el teñido por rol necesitó lo mismo (2026-08-29). Recibe y devuelve tres canales.
  function aLuz(c, obj){
    const y = luzDe(c[0], c[1], c[2]);
    if (obj > y) {                       // aclarar = acercarse al blanco
      const t = y >= 1 ? 0 : (obj - y) / (1 - y);
      return c.map(v => Math.round(v + (255 - v) * t));
    }
    const f = y <= 0 ? 0 : obj / y;      // oscurecer = escalar, que respeta el matiz
    return c.map(v => Math.min(255, Math.round(v * f)));
  }

  const aHex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
  const canales = h => [1, 3, 5].map(i => canal(h, i));

  // Girar el MATIZ de un color, dejando igual cuán vivo y cuán claro es. Con esto los
  // siete bloques del panel salen de UN acento: son hermanos, giran parejo y ninguno
  // desafina con el resto ni con el tema. Elegir siete colores a mano no daría eso.
  function girar(hex, grados){
    const [r, v, a] = canales(hex).map(x => x / 255);
    const mx = Math.max(r, v, a), mn = Math.min(r, v, a), d = mx - mn;
    let h = 0;
    if (d) h = mx === r ? ((v - a) / d + (v < a ? 6 : 0))
            : mx === v ? (a - r) / d + 2 : (r - v) / d + 4;
    h = ((h * 60 + grados) % 360 + 360) % 360;
    const l = (mx + mn) / 2;
    const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
    // La vuelta a rgb, en su forma corta (la de la norma CSS).
    const k = n => (n + h / 30) % 12;
    const q = s * Math.min(l, 1 - l);
    const f = n => l - q * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
    // ⚠⚠ Y se le devuelve LA LUZ DEL ORIGINAL, que es la mitad del asunto: girar en HSL
    // conserva la "L" de esa rueda, y esa L NO es la luz que ve el ojo. Un turquesa y un
    // violeta con la misma L se leen completamente distinto — medido acá: girando el
    // turquesa del estilo Terminal salía un violeta con contraste 2,7 sobre el fondo
    // negro (ilegible) mientras el turquesa daba 15,4. Lo cazó `ver_estilos.py`.
    return aHex(aLuz([f(0), f(8), f(4)].map(x => Math.round(x * 255)),
                     luzDe(r * 255, v * 255, a * 255)));
  }

  // Un color que tiene que LEERSE como texto sobre el fondo de ahora. En tema claro se
  // hunde a tinta oscura y en oscuro se sube si vino muy apagado.
  // ⚠ No sirve `claroDe()` para esto: un color poco saturado cae en su franja de
  // SUPERFICIE y termina casi blanco — que es exactamente lo que hay que evitar en algo
  // que es texto. (Pasó con los títulos de los bloques en el estilo Papel: gris clarito
  // sobre crema, contraste 1,3.)
  function aTinta(hex, claro){
    const c = canales(hex), y = luzDe(c[0], c[1], c[2]);
    if (claro && y > .38) return aHex(aLuz(c, .30));
    if (!claro && y < .30) return aHex(aLuz(c, .55));
    return hex;
  }
  // ⚠ Un color CON COLOR es una señal (el semáforo, los estados) y no se trata como gris:
  // ni el tema claro ni el teñido por rol lo tocan igual que a una superficie.
  const cromatico = c => (Math.max(...c) - Math.min(...c)) / 255 > .30;

  // ⭐⭐ EL TEÑIDO POR ROL (2026-08-29, pedido de Martín: "más colores sobre el panel", y
  // eligió las cuatro zonas que faltaban: las cajas, el mando, las letras y los botones).
  //
  // No hay una perilla por elemento: hay DOS, y cada uno de los 196 grises que las
  // pantallas escriben a mano se clasifica solo, por su luminosidad. Los cortes no son
  // inventados, están medidos y ya estaban escritos arriba de `claroDe()`: los fondos de
  // las pantallas están todos abajo de .25 de luz y los textos arriba de .40.
  //
  //   luz < .25              → superficie  → la tiñe `tintaCajas`   (y los botones grises)
  //   luz > .40              → letra       → la tiñe `tintaLetras`
  //   entre .25 y .40        → se interpola, para que no haya un salto visible
  //   saturación > .30       → NO SE TOCA: es una señal
  //
  // ⭐ Y el teñido conserva la LUMINOSIDAD original de cada gris: solo le cambia el matiz.
  // Eso es lo que mantiene la jerarquía de la pantalla — el título sigue siendo más claro
  // que el subtítulo, y los dos quedan del mismo tono. Si en vez de esto se pintaran todos
  // los textos del mismo color, se perdería la diferencia entre lo importante y lo apagado.
  const CORTE_SUP = .25, CORTE_TXT = .40;
  // Cuánto se tiñe. Con menos no se nota y con más el gris deja de ser gris: a .38 un
  // violeta se lee como "las letras están violetas" sin que el texto pierda su gris de base.
  const FUERZA_TINTE = .38;

  function tenida(hex){
    // '' = esta tinta no se toca (no hay tinte elegido, o es una señal).
    const letras = esLibre(aspecto.tintaLetras) ? aspecto.tintaLetras : '';
    const cajas  = esLibre(aspecto.tintaCajas)  ? aspecto.tintaCajas  : '';
    if (!letras && !cajas) return '';
    const c = canales(hex);
    if (cromatico(c)) return '';
    const y = luzDe(c[0], c[1], c[2]);
    // Cuánto de "letra" es esta tinta: 0 = superficie pura, 1 = letra pura.
    const p = y <= CORTE_SUP ? 0
            : y >= CORTE_TXT ? 1 : (y - CORTE_SUP) / (CORTE_TXT - CORTE_SUP);
    // ⚠ El rol que no tiene color elegido tira hacia el gris de siempre, o sea que no lo
    // mueve. Así se puede teñir solo las letras y dejar las cajas como estaban.
    const tl = letras ? canales(letras) : c;
    const tc = cajas ? canales(cajas) : c;
    const mez = [0, 1, 2].map(k =>
      Math.round(c[k] * (1 - FUERZA_TINTE) + (tc[k] * (1 - p) + tl[k] * p) * FUERZA_TINTE));
    return aHex(aLuz(mez, y));
  }

  // El acento puede ser uno de la fila de colores o CUALQUIERA elegido con la rueda
  // (2026-08-18), que se guarda como '#rrggbb'. Para el elegido a mano hay que inventarle
  // el fondo del acento (el tono oscuro de las pastillas): sale de mezclarlo con el fondo.
  const esLibre = c => typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c);
  function colorDe(fondo){
    if (esLibre(aspecto.color)) return [aspecto.color, mezcla(aspecto.color, fondo, .13)];
    return COLORES[aspecto.color] || COLORES.celeste;
  }

  // ⭐⭐ El FONDO también puede ser cualquier color (2026-08-29, pedido de Martín: "me
  // gustaría poder elegir el color también", mirando la fila de cinco fondos). Se guarda
  // igual que el acento y el rastro: '#rrggbb' en el mismo campo, así no hay una opción
  // nueva que agregar a la lista blanca de `/aspecto` en `panel.py` — `fondo` ya viaja.
  //
  // De un color pelado hay que sacarle las otras dos cosas que un fondo trae puestas:
  //   · la SUPERFICIE (`--fondo2`), que es donde se apoyan las tarjetas y las barras. Va
  //     apenas despegada del fondo y SIEMPRE hacia el blanco, que es para donde van los
  //     cinco de arriba (#0b0d12 → #0f1320 el azulado, #f2f4f8 → #ffffff el claro).
  //   · si el tema es CLARO, que no es un gusto aparte: si el color elegido es luminoso,
  //     las letras claras de siempre no se leen encima y hay que dar vuelta la pantalla
  //     entera. Se decide por la luminosidad, con el corte en la mitad.
  // ⚠ Los dos salen en '#rrggbb' y no en `rgb(…)`: más abajo se los mezcla y se los pasa
  // a `conAlfa()`, y esas dos cuentan los dígitos del hex a mano (ver `mezclaHex`).
  // ⚠ Un color medio (gris, luz cerca de .5) va a quedar flojo elija lo que elija el
  // corte: no hay tema que lea bien sobre eso. Es su pantalla y se ve al instante, así
  // que no se le prohíbe nada — pero no esperar que un #808080 se vea prolijo.
  function fondoDe(){
    const v = aspecto.fondo;
    if (!esLibre(v)) return FONDOS[v] || FONDOS.azulado;
    const claro = luzDe(canal(v, 1), canal(v, 3), canal(v, 5)) > .5;
    return ['A gusto', v, mezclaHex('#ffffff', v, claro ? .5 : .05), claro];
  }

  // --- El tamaño de los controles (2026-09-12) ---------------------------------
  //
  // ⭐⭐ La referencia del zoom vive en SU PROPIA llave del navegador (`aspectoZoomRef`) y
  // NO adentro de `aspecto`, por dos motivos que son el mismo: es un dato de ESTA pantalla.
  //   · Al servidor no tiene que viajar: el teléfono tiene otra densidad y otra ampliación,
  //     y con la referencia de la laptop puesta ahí los botones saldrían de cualquier
  //     tamaño. Lo que sí viaja es la ELECCIÓN (`botones`, `botonesZoom`).
  //   · Y no puede vivir en `aspecto` ni aunque el servidor la tirara: la respuesta de
  //     `/aspecto` hace `Object.assign({}, BASE, d)`, o sea que pisa el objeto entero y se
  //     la llevaría puesta apenas contesta.
  const LLAVE_REF = 'aspectoZoomRef';
  // Cuánto zoom hay ahora. No es un número absoluto que signifique algo: en esta laptop el
  // 100 % del navegador ya da 1.75 porque Windows está ampliado al 175 %. Lo que sirve es
  // la RAZÓN contra el momento en que se clavó el tamaño.
  const zoomAhora = () => window.devicePixelRatio || 1;
  function refZoom(){
    try { const v = parseFloat(localStorage.getItem(LLAVE_REF)); return v > 0 ? v : 0; }
    catch (e) { return 0; }
  }
  function clavarZoom(){
    try { localStorage.setItem(LLAVE_REF, String(zoomAhora())); } catch (e) {}
  }
  // ⚠ El tope no es decorativo: sin él, un zoom al 500 % dejaría los botones en 8 px de
  // alto (ilegibles y casi imposibles de apretar) y uno al 30 % los volvería enormes. Se
  // clava el tamaño real hasta donde tiene sentido y después se acompaña.
  // ⚠⚠ El piso se midió, no se eligió a ojo: con .55 —el primer número que puse— el tope
  // ya se tocaba al 200 % de zoom, o sea que "quedan fijos" dejaba de estar fijo justo en
  // el zoom donde uno lo prende. Con .40 aguanta hasta el 250 % con los botones normales.
  const TOPE_UI = [.40, 2];
  function factorUi(){
    const paso = (BOTONES[aspecto.botones] || BOTONES.normal)[1];
    let f = paso;
    if (aspecto.botonesZoom === 'fijo') {
      // Sin referencia guardada, el zoom de ahora ES la referencia: recién prendido no
      // puede cambiar nada de lugar, y a partir de acá se compensa lo que se mueva.
      let ref = refZoom();
      if (!ref) { clavarZoom(); ref = zoomAhora(); }
      f = paso * (ref / zoomAhora());
    }
    return Math.min(TOPE_UI[1], Math.max(TOPE_UI[0], f));
  }

  // ⭐ La foto de fondo de UNA charla o de una carpeta (2026-10-10, colorcharla.js). Si hay,
  // tapa a la general mientras estás ahí; con '' vuelve la general. Lleva el mismo velo que
  // la general, así el texto se lee igual. ⚠ No dispara `aspecto-aplicado`: colorcharla.js
  // llama esto desde su repintado, que a su vez escucha ese evento — sería un bucle.
  let fotoPropia = '', temaClaro = false;
  // ⭐ Las partículas y la entrada suave del estilo Grok (2026-10-31). Un lienzo fijo
  // DETRÁS de todo (z-index -1: queda arriba de la foto y abajo del contenido) con puntitos
  // que suben despacio. Se apaga solo: con otro estilo, con el movimiento en "Sin
  // latidos"/"Quieto", si el sistema pide menos movimiento, y mientras la pestaña no se ve
  // (no gasta batería en el bolsillo).
  let lienzoFx = null, cuadroFx = 0, puntosFx = [], mirador = null;
  // De qué color son las partículas, en "tres números". Las de color salen del acento del
  // estilo (naranja en Grok) y el polvo es blanco sobre oscuro y gris oscuro sobre papel:
  // blanco sobre un fondo claro no se ve. Los pone `aplicar()`.
  let tintaFx = '251,146,60', polvoFx = '255,255,255';
  const vistoMax = new WeakMap();
  function particulas(prender){
    if (prender && window.matchMedia &&
        matchMedia('(prefers-reduced-motion: reduce)').matches) prender = false;
    if (!document.body) {           // aplicar() corre antes del <body>: se reintenta
      if (prender) document.addEventListener('DOMContentLoaded', () =>
        particulas(document.documentElement.classList.contains('estilo-grok')), {once: true});
      return;
    }
    entradas(prender);
    if (!prender) {
      cancelAnimationFrame(cuadroFx); cuadroFx = 0;
      if (lienzoFx) { lienzoFx.remove(); lienzoFx = null; }
      return;
    }
    if (lienzoFx) return;
    lienzoFx = document.createElement('canvas');
    lienzoFx.id = 'grokFx';
    lienzoFx.setAttribute('aria-hidden', 'true');
    document.body.appendChild(lienzoFx);
    const ctx = lienzoFx.getContext('2d');
    const medir = () => {
      if (!lienzoFx) return;
      const d = Math.min(2, window.devicePixelRatio || 1);
      lienzoFx.width = innerWidth * d; lienzoFx.height = innerHeight * d;
      ctx.setTransform(d, 0, 0, d, 0, 0);
      // Pocos: es un fondo que se mueve, no nieve. Proporcional al área de la pantalla.
      const n = Math.round(Math.min(70, innerWidth * innerHeight / 16000));
      puntosFx = Array.from({length: n}, () => ({
        x: Math.random() * innerWidth, y: Math.random() * innerHeight,
        r: .5 + Math.random() * 1.5, v: .08 + Math.random() * .25,
        der: (Math.random() - .5) * .15, fase: Math.random() * 6.3,
        naranja: Math.random() < .35}));
    };
    medir();
    window.addEventListener('resize', medir);
    const paso = t => {
      if (!lienzoFx) return;
      cuadroFx = requestAnimationFrame(paso);
      if (document.hidden) return;
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      for (const p of puntosFx) {
        p.y -= p.v; p.x += p.der + Math.sin(t / 3000 + p.fase) * .12;
        if (p.y < -4) { p.y = innerHeight + 4; p.x = Math.random() * innerWidth; }
        const a = .18 + .32 * (.5 + .5 * Math.sin(t / 900 + p.fase));
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283);
        ctx.fillStyle = p.naranja ? 'rgba(' + tintaFx + ',' + a + ')'
                                  : 'rgba(' + polvoFx + ',' + (a * .7) + ')';
        ctx.fill();
      }
    };
    cuadroFx = requestAnimationFrame(paso);
  }
  // ⚠⚠ El chat del celular se REDIBUJA ENTERO cada vez que algo cambia (innerHTML), así
  // que animar "todo .msg que aparece" haría parpadear la charla completa en cada vuelta.
  // Se anima solo el mensaje con número (`data-msg`) más alto que el último visto en esa
  // caja, y solo si llegaron uno o dos: muchos de golpe es abrir una charla, no un mensaje.
  function entradas(prender){
    if (!prender) { if (mirador) { mirador.disconnect(); mirador = null; } return; }
    if (mirador) return;
    mirador = new MutationObserver(cambios => {
      const cajas = new Set();
      cambios.forEach(c => c.addedNodes.length && cajas.add(c.target));
      cajas.forEach(caja => {
        if (!caja.querySelectorAll) return;
        const msgs = [...caja.querySelectorAll(':scope > .msg[data-msg]')];
        if (!msgs.length) return;
        const max = Math.max(...msgs.map(m => +m.dataset.msg || 0));
        const antes = vistoMax.get(caja);
        vistoMax.set(caja, max);
        if (antes === undefined || max <= antes || max - antes > 2) return;
        msgs.filter(m => +m.dataset.msg > antes).forEach(m => m.classList.add('grok-entra'));
      });
    });
    mirador.observe(document.body, {childList: true, subtree: true});
  }

  function ponerFoto(){
    // ⭐ Con el estilo Vidrio siempre hay una foto atrás: es de lo que está hecho. Si no
    // elegiste ninguna se muestra la del escritorio, SIN guardarla en tu aspecto: el día
    // que elijas otra, o cambies de estilo, no queda rastro.
    const base = aspecto.img || (deVidrio() ? FOTO_WINDOWS : '');
    const general = base === FOTO_WINDOWS && versionFondo
      ? FOTO_WINDOWS + '?v=' + encodeURIComponent(versionFondo) : base;
    const url = fotoPropia || general;
    let velo = (VELOS[aspecto.velo] || VELOS.media)[1];
    // El velo se afloja con Vidrio: los paneles ya oscurecen lo que tienen detrás, y con
    // el velo de siempre la foto no se vería (que es justo lo que este estilo muestra).
    // Sigue obedeciendo a tu perilla: "apenas" sigue siendo más oscuro que "a full".
    if (deVidrio && !temaClaro) velo = Math.max(.2, velo - .26);
    // ⚠ Con el tema claro el velo va BLANCO: uno negro apagaría la foto y encima dejaría
    // el texto —que ahora es oscuro— sobre un fondo oscuro, o sea ilegible.
    const tela = temaClaro ? '250,250,252' : '6,8,12';
    document.documentElement.style.setProperty('--fondo-img', url
      ? 'linear-gradient(rgba(' + tela + ',' + velo + '),rgba(' + tela + ',' + velo +
        ')),url("' + url + '")'
      : 'none');
    document.documentElement.classList.toggle('con-foto', !!url);
  }
  window.aspectoFoto = url => {
    url = url || '';
    if (url === fotoPropia) return;
    fotoPropia = url;
    ponerFoto();
  };

  // ⭐ El material del vidrio a gusto (2026-11-10). Escribe variables en el <html> SOLO para
  // lo que elegiste: lo que queda de fábrica se borra, y ahí manda la hoja de Sesiones con
  // los números de siempre (están de respaldo en cada var()). Así "de fábrica" es
  // exactamente la pantalla de antes, píxel por píxel.
  //   · Opacidad (0 a 100, fábrica 20): de 0 a 20 los paneles van de invisibles al velo
  //     blanco de siempre; de 20 a 100 se les suma el fondo hasta quedar casi sólidos. La
  //     hoja de la charla acompaña: de 10 % a 95 % de fondo (fábrica 50 %).
  //   · Color: tiñe los paneles y, más suave, la hoja.
  //   · Brillo (0 a 200 %): multiplica el filo de luz, el borde y el brillo de arriba.
  //   · Grano (0 a 200 %): la textura esmerilada. En 0 no hay grano.
  // ⚠ Las inline del <html> le ganan a "html.carta.vidrio{...}" de la hoja: por eso alcanza
  // con escribirlas acá, sin tocar el orden de las reglas.
  const GRANO = op => 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' ' +
    'width=\'200\' height=\'200\'%3E%3Cfilter id=\'g\' x=\'0\' y=\'0\' width=\'1\' height=\'1\'%3E' +
    '%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'.8\' numOctaves=\'2\' ' +
    'stitchTiles=\'stitch\'/%3E%3CfeColorMatrix values=\'0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 ' +
    '1.4 -.42\'/%3E%3C/filter%3E%3Crect width=\'200\' height=\'200\' filter=\'url(%23g)\' ' +
    'opacity=\'' + op + '\'/%3E%3C/svg%3E")';
  const numVd = k => {
    const n = parseFloat(aspecto[k]);
    return isFinite(n) ? n : VD_FAB[k];
  };
  const tinteVd = () => {
    const t = aspecto.vdTinte || '';
    return VD_TINTES[t] ? VD_TINTES[t][1] : (esLibre(t) ? t : '');
  };
  function vidrioFino(r){
    const tinte = tinteVd();
    const opElegida = aspecto.vdOpaco !== '' && aspecto.vdOpaco != null;
    if (opElegida || tinte){
      const o = Math.max(0, Math.min(100, numVd('vdOpaco')));
      // El velo del panel: blanco 8,5 % de fábrica; con un color, ese color al 24 %.
      const velo = (tinte ? 24 : 8.5) * Math.min(1, o / 20);
      const fondo = o <= 20 ? 0 : (o - 20) / 80 * 88;
      const capa = tinte || '#ffffff';
      r.setProperty('--vd-vidrio', 'color-mix(in srgb,' + capa + ' ' + velo.toFixed(1) +
        '%,color-mix(in srgb,var(--fondo) ' + fondo.toFixed(1) + '%,transparent))');
      const hoja = o <= 20 ? 10 + 40 * o / 20 : 50 + 45 * (o - 20) / 80;
      const color = tinte ? 'color-mix(in srgb,' + tinte + ' 30%,var(--fondo))' : 'var(--fondo)';
      r.setProperty('--vd-hoja', 'color-mix(in srgb,' + color + ' ' + hoja.toFixed(1) +
        '%,transparent)');
    } else {
      r.removeProperty('--vd-vidrio');
      r.removeProperty('--vd-hoja');
    }
    if (aspecto.vdBrillo !== '' && aspecto.vdBrillo != null)
      r.setProperty('--vd-b', (Math.max(0, Math.min(200, numVd('vdBrillo'))) / 100).toFixed(2));
    else r.removeProperty('--vd-b');
    if (aspecto.vdGrano !== '' && aspecto.vdGrano != null){
      const g = Math.max(0, Math.min(200, numVd('vdGrano')));
      r.setProperty('--vd-grano', g ? GRANO((.07 * g / 100).toFixed(3)) : 'none');
    } else r.removeProperty('--vd-grano');
  }

  function aplicar(){
    const r = document.documentElement.style;
    r.setProperty('--tipo', familiaDe(aspecto.tipo));
    r.setProperty('--escala', (LETRAS[aspecto.letra] || LETRAS.normal)[1]);
    // ⭐ El tamaño de los botones y las barras. Las pantallas lo leen como
    // `calc(38px * var(--ui,1))`: sin este archivo, o con todo en normal, vale 1 y queda
    // exactamente lo de siempre.
    r.setProperty('--ui', factorUi().toFixed(4));
    // ⭐ Los efectos de la letra se prenden con una CLASE, no con una regla que exista
    // siempre: ver el comentario grande del CSS. Sin elegir nada, la pantalla no tiene ni
    // una regla nueva encima.
    const cls = document.documentElement.classList;
    const prender = (pre, tabla, valor) => {
      Object.keys(tabla).forEach(k => cls.remove(pre + k));
      if (valor && valor !== 'normal' && tabla[valor]) cls.add(pre + valor);
    };
    prender('peso-', PESOS, aspecto.peso);
    prender('esp-', ESPACIADOS, aspecto.espaciado);
    prender('ren-', RENGLONES, aspecto.renglon);
    // Los títulos pueden tener SU tipografía. ⚠ Sin elegir nada la variable NO se define,
    // para que el `var()` caiga en su respaldo (`--tipo`) y el título siga al texto: es el
    // mismo truco de las barras y de las tintas.
    const otroTitulo = aspecto.tipoTitulo &&
                       (TIPOS[aspecto.tipoTitulo] || esFuenteLibre(aspecto.tipoTitulo));
    if (otroTitulo) r.setProperty('--tipo-titulo', familiaDe(aspecto.tipoTitulo));
    else r.removeProperty('--tipo-titulo');
    // Los diseños nuevos traen su propia letra para los títulos (la cursiva de la carta).
    // Con esta clase saben que elegiste otra y se corren.
    cls.toggle('titulo-propio', !!otroTitulo);
    const f = fondoDe();
    const claro = !!f[3];
    // ⭐⭐ Acá se da vuelta la pantalla entera. En oscuro las tintas se BORRAN, no se
    // definen en su valor original: así cada `var(--cXXXXXX,#xxxxxx)` cae en su respaldo,
    // que es el color de siempre, y el tema oscuro no depende de que estos cálculos estén
    // bien. Es la diferencia entre "queda igual" y "queda parecido".
    tintasDeLaPagina().forEach(t => {
      // El teñido por rol se aplica ANTES de dar vuelta la pantalla: tiñe el gris oscuro
      // conservando su luz, y si además el tema es claro, `claroDe()` invierte ese
      // resultado. Al revés daría un matiz distinto en cada tema.
      const tin = tenida('#' + t);
      if (!claro && !tin) {   // ⭐ nada elegido: se BORRA y manda el respaldo (ver arriba)
        r.removeProperty('--c' + t); r.removeProperty('--c' + t + '-rgb'); return;
      }
      const v = claro ? claroDe(tin || ('#' + t)) : tin;
      r.setProperty('--c' + t, v);
      // La misma tinta en "tres números", para los colores translúcidos: un separador
      // escrito como `rgba(var(--cffffff-rgb,255,255,255),.06)` se ve claro sobre el tema
      // oscuro y oscuro sobre el claro, que es justo lo que tiene que hacer una rayita.
      r.setProperty('--c' + t + '-rgb',
                    [1, 3, 5].map(i => parseInt(v.substr(i, 2), 16)).join(','));
    });
    document.documentElement.classList.toggle('tema-claro', claro);
    // El acento se oscurece en el tema claro: el celeste de siempre sobre un fondo blanco
    // no se lee. Se oscurece con la MISMA cuenta que el resto, así queda del mismo tono.
    const col = colorDe(f[1]);
    if (claro && esLibre(col[0])) {
      col[0] = claroDe(col[0]);
      col[1] = mezcla(col[0], f[1], .13);   // la pastilla del acento, ahora clarita
    }
    r.setProperty('--acento', col[0]);
    r.setProperty('--acento-bg', col[1]);
    // ⭐ La letra que va ENCIMA de una pieza pintada con el acento (2026-11-10): negra o
    // blanca según cuál se lea. Sin esto, elegir un acento oscuro dejaba el botón Enviar de
    // los diseños nuevos con letra oscura sobre fondo oscuro.
    {
      const n = esLibre(col[0]) ? [1, 3, 5].map(i => canal(col[0], i)) : [142, 203, 255];
      r.setProperty('--acento-sobre', luzDe(n[0], n[1], n[2]) > .55 ? '#14161c' : '#ffffff');
    }
    // El efecto de la letra. El resplandor sale del acento, así que se arma acá abajo, ya
    // con el acento corregido para el tema. Igual que los otros: sin efecto elegido no se
    // agrega la clase y no hay ninguna regla de sombra dando vueltas.
    const conFx = aspecto.letraFx && aspecto.letraFx !== 'nada' && LETRA_FX[aspecto.letraFx];
    document.documentElement.classList.toggle('con-fx', !!conFx);
    if (conFx) {
      r.setProperty('--letra-fx', aspecto.letraFx === 'resplandor'
        ? '0 0 7px ' + conAlfa(esLibre(col[0]) ? col[0] : '#8ecbff', .55)
        : LETRA_FX[aspecto.letraFx][1]);
    } else {
      r.removeProperty('--letra-fx');
    }
    r.setProperty('--fondo', f[1]);
    // ⚠ `--fondo2` se define más abajo, junto con el vidrio: cuánto se transparenta
    // depende de si hay foto puesta Y de cuánto vidrio eligió.
    // ⭐ Y con el mismo color se pintan las BURBUJAS del chat y los bordes: Martín
    // (2026-08-18) pidió que el tema llegue "a todo, absolutamente a todo", no solo a
    // los marcos. Se derivan del acento mezclándolo con el fondo, así el celeste da
    // burbujas celestes y el rosa, rosas, sin tener que elegir seis colores a mano.
    // ⚠ La tuya va FUERTE y la de Claude apenas teñida: el que escribe se distingue
    // por el peso del color, no por el lado nomás.
    // ⚠ Y si eligió un color para una burbuja, ese pisa al derivado: `--burbuja-vos` es
    // el FONDO de la tuya, así que el color elegido va tal cual; el de la sesión es
    // apenas un tinte sobre el fondo, y el elegido se usa para el tinte y para el borde
    // (pintarlo entero taparía el texto).
    const bVos = esLibre(aspecto.burbujaVos) ? aspecto.burbujaVos : '';
    const bIa  = esLibre(aspecto.burbujaIa)  ? aspecto.burbujaIa  : '';
    // ⚠⚠ En el tema claro la burbuja tuya se da vuelta entera: fondo clarito teñido y
    // letra oscura. La primera versión hacía lo contrario (fondo bien oscuro, letra
    // blanca) y el resultado era ilegible por un motivo que no se ve venir: el texto de
    // adentro NO siempre pide `--burbuja-vos-txt`, muchas veces es un color de la pantalla
    // que en tema claro ya se dio vuelta solo — o sea que la letra se volvió oscura por su
    // cuenta y quedó negro sobre azul. Con la burbuja clara, las dos formas se leen.
    r.setProperty('--burbuja-vos', bVos || mezcla(col[0], f[1], claro ? .22 : .40));
    r.setProperty('--burbuja-vos-txt', claro ? mezcla(col[0], '#000000', .35) : '#ffffff');
    r.setProperty('--burbuja-ia', mezcla(bIa || col[0], f[2], .07));
    r.setProperty('--burbuja-ia-borde', bIa || col[0]);
    // ⭐ Lo que ELEGISTE para las burbujas, aparte de lo que sale por cuenta (2026-11-10).
    // Los diseños nuevos dibujan tu burbuja discreta y la respuesta sin caja; si acá
    // elegiste un color, ese color manda, y para eso tienen que poder distinguir "lo
    // eligió" de "salió del acento". Sin elegir nada, estas variables no existen.
    if (bVos) {
      r.setProperty('--burbuja-vos-puesta', bVos);
      r.setProperty('--burbuja-vos-puesta-txt',
        luzDe(canal(bVos, 1), canal(bVos, 3), canal(bVos, 5)) > .55 ? '#14161c' : '#ffffff');
    } else {
      r.removeProperty('--burbuja-vos-puesta'); r.removeProperty('--burbuja-vos-puesta-txt');
    }
    if (bIa) r.setProperty('--burbuja-ia-puesta', bIa);
    else r.removeProperty('--burbuja-ia-puesta');
    document.documentElement.classList.toggle('con-burbuja-ia', !!bIa);
    r.setProperty('--borde', mezcla(col[0], f[2], .16));
    // El mismo borde pero que se vea: para lo que tiene que leerse como un marco y no
    // como una separación (la caja que abraza a un grupo de pestañas, por ejemplo).
    r.setProperty('--borde-fuerte', mezcla(col[0], f[2], .34));
    // ⭐ El rastro. "tema" = apagar el acento contra el fondo, que es lo que hace el
    // resto de la pantalla; cualquier otro valor es el color elegido a mano o con la
    // rueda. El fondo del bloque sale del mismo color, apenas teñido sobre el fondo,
    // para que se lea encima de la foto sin taparla.
    const rst = (RASTROS[aspecto.rastro] || [])[1]
                || (esLibre(aspecto.rastro) ? aspecto.rastro : mezcla(col[0], f[2], .55));
    r.setProperty('--rastro', rst);
    r.setProperty('--rastro-bg', aspecto.img ? conAlfa(mezcla(rst, f[2], .10), .78)
                                             : mezcla(rst, f[2], .10));
    r.setProperty('--rastro-borde', mezcla(rst, f[2], .26));
    // ⭐⭐ El semáforo, en cinco tonos por color. Las pantallas NO escriben más el verde
    // a mano: piden el escalón que necesitan. Los cinco salen de UN color elegido, así
    // que cambiarlo mueve el punto, el botón, su hover, el texto claro y el fondito
    // oscuro todos juntos y sin desafinar entre sí.
    // ⚠ Antes de esto había once verdes distintos repartidos en cinco pantallas (el panel
    // usaba #22c55e y el celular #3ddc84 para decir lo MISMO): por eso "elegir el verde"
    // no era una variable, era un trabajo. Medido el 2026-08-29.
    // ⚠ En el tema claro los tres se OSCURECEN, y los dos peldaños que en oscuro se
    // aclaraban ahora se hunden hacia el negro. No es simetría por prolijidad: el verde
    // de siempre sobre un fondo blanco no se lee, y el texto que va ARRIBA del botón
    // verde también se dio vuelta (era casi negro y ahora es casi blanco), así que el
    // botón tiene que quedar oscuro o el texto desaparece.
    const escalera = (nombre, elegido, fabrica) => {
      const crudo = esLibre(elegido) ? elegido : fabrica;
      const b = claro ? claroDe(crudo) : crudo;
      const hundir = claro ? '#000000' : f[1];
      const tinta  = claro ? '#000000' : '#ffffff';
      r.setProperty('--' + nombre,          b);                      // el punto, el boton
      r.setProperty('--' + nombre + '-2',   mezcla(b, hundir, .74)); // el hover, mas hundido
      r.setProperty('--' + nombre + '-txt', mezcla(b, tinta, .52));  // texto que se lee
      r.setProperty('--' + nombre + '-bd',  mezcla(b, f[2], .30));   // el borde
      r.setProperty('--' + nombre + '-bg',  mezcla(b, f[2], .13));   // el fondito
    };
    escalera('ok',    aspecto.ok,    PARTES.ok[1]);
    escalera('mal',   aspecto.mal,   PARTES.mal[1]);
    escalera('aviso', aspecto.aviso, PARTES.aviso[1]);
    escalera('pregunta', aspecto.pregunta, PARTES.pregunta[1]);
    // ⭐ Las dos barras. Sin color elegido la variable NO SE DEFINE, y eso es a propósito:
    // así cada pantalla pone su propio "como estaba" en el segundo argumento de `var()`
    // —el encabezado del panel es transparente, la barra de la pizarra es `--fondo2`— y
    // con una sola variable conviven dos defaults distintos. Definirla con un valor acá
    // (aunque fuera `transparent`) le gana al fallback y le pintaría la barra de la
    // pizarra de vidrio a quien no eligió nada.
    // Con la foto de fondo puesta se tiñe en vez de taparla, como el resto de las
    // superficies.
    const barra = (nombre, c) => {
      if (!esLibre(c)) { r.removeProperty(nombre); return; }
      r.setProperty(nombre, aspecto.img ? conAlfa(c, .80) : c);
    };
    barra('--barra', aspecto.barra);
    barra('--piz-barra', aspecto.pizBarra);
    // ⭐ Los siete bloques del panel. El color sale del acento girando el matiz, así que
    // son hermanos entre sí; el elegido a mano pisa al derivado, como en todo lo demás.
    // ⚠ Sin estilo puesto y sin color propio NO se pinta nada, y la clase tampoco se
    // agrega: el `::before` del filito ni existe, así que la pantalla de quien no eligió
    // nada no se mueve un píxel.
    // ⚠ En tema claro se oscurecen con la misma cuenta que el acento: son texto sobre el
    // fondo, y el celeste de siempre sobre blanco no se lee.
    const pintaBloques = !!(ESTILOS[aspecto.estilo] || {}).bloques;
    const elegidos = (aspecto.bloques && typeof aspecto.bloques === 'object')
                     ? aspecto.bloques : {};
    document.querySelectorAll('[data-bloque]').forEach(el => {
      const def = BLOQUES[el.dataset.bloque];
      let c = def && (esLibre(elegidos[el.dataset.bloque]) ? elegidos[el.dataset.bloque]
                      : pintaBloques ? girar(col[0], def[1] * PASO_BLOQUE) : '');
      // ⚠ El derivado ya sale legible (`col[0]` viene corregido para el tema y `girar`
      // conserva su luz), pero el elegido A MANO lo eligió Martín sin saber en qué tema
      // iba a caer. `aTinta` no toca al que ya está bien.
      if (c) c = aTinta(c, claro);
      el.classList.toggle('bq-color', !!c);
      if (c) el.style.setProperty('--bloque', c);
      else el.style.removeProperty('--bloque');
    });
    // ⭐ Las sombras, en cuatro peldaños. Los números de `normal` (k=1) son EXACTAMENTE
    // los que estaban escritos a mano en las pantallas: sin tocar nada, la sombra queda
    // igual que siempre. Al escalar se mueven las tres cosas juntas —lo lejos que cae,
    // lo difusa que es y cuánto tapa—, porque agrandar el desenfoque dejando el negro
    // fijo da un manchón gris en vez de una sombra.
    const k = (SOMBRAS[aspecto.sombra] || SOMBRAS.normal)[1];
    const som = (y, blur, alfa) => k <= 0 ? 'none'
      : (y * k).toFixed(1).replace(/\.0$/, '') + 'px ' +
        (blur * k).toFixed(1).replace(/\.0$/, '') + 'px rgba(0,0,0,' +
        // ⚠ Sin pelarle los ceros, `normal` escribe `rgba(0,0,0,0.500)` donde la pantalla
        // decía `.5`: se ve igual pero deja de ser comparable, y la prueba de "quedó
        // idéntico" es justamente lo que sostiene que esto no le cambió nada a nadie.
        Math.min(.85, alfa * (k < 1 ? .6 + .4 * k : k))
          .toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + ')';
    r.setProperty('--sombra-0', k <= 0 ? 'none' : '0 ' + som(1, 3, .3));
    r.setProperty('--sombra-1', k <= 0 ? 'none' : '0 ' + som(3, 10, .4));
    r.setProperty('--sombra-2', k <= 0 ? 'none' : '0 ' + som(8, 24, .5));
    r.setProperty('--sombra-3', k <= 0 ? 'none' : '0 ' + som(16, 46, .6));
    // El mismo peldaño como NÚMERO: una sombra compuesta (el vidrio lleva un filo de luz
    // y además su sombra) no puede usar las de arriba, porque con 'none' adentro de una
    // lista la regla entera deja de valer y se pierde también el filo.
    r.setProperty('--sombra-k', String(k));
    // La de la barra de abajo del celular, que cae para ARRIBA: mismo peldaño grande
    // con el signo dado vuelta.
    r.setProperty('--sombra-arriba', k <= 0 ? 'none' : '0 -' + som(18, 45, .5));
    // ⭐ El vidrio: cuánto se ve lo de atrás a través de las barras y los menús. Las
    // pantallas ya desenfocaban un poco; ahora ese desenfoque se multiplica por acá, así
    // que `normal` deja los mismos píxeles de siempre y `Opaco` lo apaga del todo.
    const v = desenfoqueDe(aspecto.vidrio);
    r.setProperty('--vidrio', v.toFixed(2));
    vidrioFino(r);
    // Y en "Vidrio" las superficies se vuelven translúcidas aunque no haya foto puesta:
    // el desenfoque solo no se nota sobre un fondo liso, porque no hay nada que borronear.
    r.setProperty('--fondo2', aspecto.img ? conAlfa(f[2], .74)
                                          : (v > 1.3 ? conAlfa(f[2], .55) : f[2]));
    // ⚠ El movimiento se apaga con una clase, no tocando cada animación (son más de
    // cincuenta): la regla de `CSS` gana con `!important` sobre todas juntas.
    const cl = document.documentElement.classList;
    Object.keys(MOVIS).forEach(m => MOVIS[m][1] && cl.remove(MOVIS[m][1]));
    const cm = (MOVIS[aspecto.movi] || MOVIS.normal)[1];
    if (cm) cl.add(cm);
    // ⭐ Las formas de Grok valen para CUALQUIER estilo (2026-11-10, Martín: "me gusta
    // mucho el aspecto de grok, quiero que cambies todos los que tenemos a sub-versiones
    // como esa"). Lo que cambia de uno a otro es la paleta y la letra. `grok-puro` deja los
    // grises neutros y la pieza blanca del original; en los demás la pieza llena (la
    // pestaña elegida, Mandar) y las partículas salen del acento de cada uno.
    // ⚠ Sin estilo elegido ("El de siempre", "volver a lo mío") no se pone ninguna de las
    // dos clases: esa sigue siendo la puerta de salida a la pantalla de antes.
    // ⭐ Carta celeste: la pantalla que trae su dibujo (`data-carta` en el `<html>`, hoy
    // solo /sesiones) lleva la clase `carta` y se queda SIN las formas de Grok — son dos
    // mundos y mezclados no se lee ninguno. Las demás siguen con las formas de Grok.
    // ⭐ `carta` es el CASCO nuevo y lo llevan dos estilos: Carta celeste y Vidrio. Vidrio
    // suma además su clase, que es la piel de vidrio encima del mismo casco.
    const celeste = aspecto.estilo === 'celeste', vidrio = deVidrio();
    const bandeja = aspecto.estilo === 'vbandeja';
    const carta = (celeste || vidrio) && document.documentElement.hasAttribute('data-carta');
    const conFormas = !!ESTILOS[aspecto.estilo] && !carta, puro = aspecto.estilo === 'grok';
    cl.toggle('estilo-grok', conFormas);
    cl.toggle('grok-puro', puro);
    cl.toggle('carta', carta);
    cl.toggle('vidrio', carta && vidrio);
    cl.toggle('vbandeja', carta && bandeja);
    fuentesCarta(celeste);
    const piezas = ['--grok-fuerte', '--grok-fuerte-txt', '--grok-fuerte-viva'];
    if (conFormas && !puro && esLibre(col[0])) {
      const n = [1, 3, 5].map(i => parseInt(col[0].substr(i, 2), 16));
      // La letra de la pieza llena: la que MÁS contraste da contra ese acento, medida con
      // la cuenta de siempre (un acento pastel pide letra negra; el azul oscuro de Papel,
      // blanca). Elegirla a ojo por estilo se rompe el día que alguien cambie un acento.
      const lin = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
      const L = .2126 * lin(n[0]) + .7152 * lin(n[1]) + .0722 * lin(n[2]);
      const negra = (L + .05) / .05 >= 1.05 / (L + .05);
      r.setProperty(piezas[0], col[0]);
      r.setProperty(piezas[1], negra ? '#0a0a0a' : '#ffffff');
      r.setProperty(piezas[2], negra ? '#15803d' : '#86efac');
      tintaFx = n.join(',');
    } else {
      piezas.forEach(v => r.removeProperty(v));
      tintaFx = '251,146,60';
    }
    polvoFx = claro ? '52,60,74' : '255,255,255';
    particulas(conFormas && !celeste && !vidrio && !cm);
    // El velo oscuro encima de la foto es lo que deja que el texto se siga leyendo.
    // A la foto de Windows se le pega la firma de la que está puesta AHORA: así el
    // navegador la vuelve a pedir cuando Windows la cambia, y no antes.
    temaClaro = claro;
    ponerFoto();
    // El color propio de cada charla (colorcharla.js) se arma CON este tema: si cambia el
    // fondo o el acento, tiene que rehacer su cuenta. Se avisa en vez de llamarlo, así este
    // archivo no depende de que el otro esté cargado.
    window.dispatchEvent(new Event('aspecto-aplicado'));
  }

  // ⭐ Las burbujas de UNA charla con color propio (2026-10-10). Misma receta que las
  // generales de `aplicar()` —la tuya con el color tal cual, la de la sesión apenas teñida
  // sobre la superficie y el color entero en el borde—, pero devuelve los valores en vez de
  // ponerlos en la página: los usa colorcharla.js sobre el chat abierto nomás. Un color
  // vacío devuelve `null` en su par, y ahí manda el general.
  // ⚠ La letra de tu burbuja se elige por la luz del color y no por el tema: un amarillo
  // en el tema oscuro con letra blanca no se lee.
  window.aspectoBurbujas = function (vos, ia){
    const f = fondoDe();
    const r = {vos: null, vosTxt: null, ia: null, iaBorde: null};
    if (esLibre(vos)) {
      r.vos = vos;
      r.vosTxt = luzDe(canal(vos, 1), canal(vos, 3), canal(vos, 5)) > .55 ? '#14161c' : '#ffffff';
    }
    if (esLibre(ia)) { r.ia = mezcla(ia, f[2], .07); r.iaBorde = ia; }
    return r;
  };

  function guardar(){
    try { localStorage.setItem('aspecto', JSON.stringify(aspecto)); }
    catch (e) { avisar('La imagen es muy pesada para guardarla; probá con otra.'); }
    // Al servidor, para que la misma elección valga en la compu y en el teléfono. Si
    // no contesta, queda la copia local y se vuelve a intentar la próxima.
    // ⚠⚠ Un panel VIEJO (sin reiniciar desde que se agregaron estos campos) no los tiene
    // en su lista blanca: los tira EN SILENCIO al reescribir el archivo, así que el color
    // se ve en este navegador y en ningún otro. Antes eso no se notaba hasta abrir el
    // teléfono; ahora el panel contesta con lo que guardó y, si falta, se dice en pantalla.
    fetch('/aspecto', {method: 'POST', headers: {'Content-Type': 'application/json'},
                       body: JSON.stringify(aspecto)})
      .then(r => r.json())
      .then(d => {
        const guardado = d && d.aspecto;
        // ⚠ Se pregunta por la tanda MÁS NUEVA de campos, no por una vieja: un panel que
        // conoce las partes pero no los estilos también está viejo, y también los tira.
        panelViejo = !guardado || !Object.keys(PARTES).some(k => k in guardado)
                     || !('tintaLetras' in guardado)
                     // ⚠ La tanda del 2026-09-12 (el tamaño de los botones). Un panel que
                     // conoce todo lo anterior pero no esto también los tira, y ahí la
                     // elección se pierde en el próximo F5 sin que nada lo diga.
                     || !('botones' in guardado)
                     // ⚠ Y el material del vidrio (2026-11-10): solo cuenta lo que elegiste.
                     || VD_CAMPOS.some(k => aspecto[k] && !(k in guardado));
        const cartel = document.getElementById('aspectoViejo');
        if (cartel) cartel.style.display = (panelViejo && hayPartes()) ? '' : 'none';
      })
      .catch(() => {});
  }

  let panelViejo = false;
  // Si hay algo elegido que un panel viejo tiraría. Incluye la tanda de los estilos: sin
  // esto, aplicar un estilo contra un panel sin reiniciar se veía acá y no viajaba, mudo.
  const hayPartes = () => Object.keys(PARTES).some(k => esLibre(aspecto[k])) ||
    !!aspecto.estilo || esLibre(aspecto.tintaLetras) || esLibre(aspecto.tintaCajas) ||
    Object.keys(aspecto.bloques || {}).length > 0 ||
    // El tamaño de los botones, si está elegido algo que no sea lo de siempre.
    (aspecto.botones && aspecto.botones !== 'normal') || aspecto.botonesZoom === 'fijo' ||
    VD_CAMPOS.some(k => aspecto[k]);

  // Lo que un estilo pisa, y por lo tanto lo único que hay que guardar para poder volver.
  // ⚠⚠ Guardar el aspecto ENTERO sería el camino corto y estaría mal: adentro está `img`,
  // que con una foto propia son cientos de kB en un dataURL. El almacenamiento del
  // navegador aguanta unos 5 MB en total y ya hay un aviso por foto pesada: duplicarla en
  // cada estilo que mira lo rompería, y encima la foto ni se pisa.
  const CAMPOS_ESTILO = ['fondo', 'color', 'estilo'].concat(Object.keys(LIMPIO));
  const copiaDeLoTuyo = a => {
    const c = {};
    CAMPOS_ESTILO.forEach(k => { c[k] = a[k]; });
    return c;
  };

  function ponerEstilo(k){
    const e = ESTILOS[k];
    if (!e) return;
    // ⚠ El "volver a lo mío" apunta SIEMPRE a la combinación que Martín tenía armada, no
    // al estilo anterior: probar tres estilos seguidos y volver tiene que devolverle LO
    // SUYO, no el segundo que miró de paso.
    const previo = (aspecto.estilo && aspecto.previo) ? aspecto.previo : copiaDeLoTuyo(aspecto);
    aspecto = Object.assign({}, aspecto, LIMPIO, e.campos, {estilo: k, previo});
  }

  function volverALoTuyo(){
    if (!aspecto.previo) return;
    aspecto = Object.assign({}, aspecto, aspecto.previo, {previo: null});
  }

  // "El de siempre": los colores de fábrica, sin estilo puesto.
  // ⚠ El `previo` se CONSERVA: sacar el estilo no es lo mismo que decidir que ya no querés
  // volver a lo tuyo. Para borrar todo de una está "volver a lo de fábrica".
  function sacarEstilo(){
    aspecto = Object.assign({}, aspecto, LIMPIO,
                            {fondo: BASE.fondo, color: BASE.color, estilo: ''});
  }

  const avisar = t => { try { alert(t); } catch (e) {} };

  // --- El panel de elección ---------------------------------------------------
  // ⭐⭐ Las tres tipografías de "Carta celeste" viajan ADENTRO de este archivo (2026-11-10).
  // ⚠ No es capricho: cada archivo de /estaticos tiene su ruta escrita a mano en panel.py,
  // así que una fuente suelta no se puede servir sin tocar el panel y reiniciarlo, y la
  // regla de la casa es que nada se baje de internet al abrir la página. Son ~66 kB entre
  // las tres (recorte "latin" de Google Fonts, formato woff2), en base64.
  // El día que el panel tenga una ruta para /estaticos/fuentes, esto se muda ahí.
  // Las tres son de fundiciones argentinas y de licencia libre (SIL Open Font License 1.1):
  //   · Archivo, de Omnibus-Type (Héctor Gatti y equipo) — todo lo que se opera.
  //   · Chivo Mono, de Omnibus-Type — horas, medidas y código.
  //   · Piazzolla (cursiva 500), de Juan Pablo del Peral, Huerta Tipográfica — los nombres.
  // ⚠ Cada fuente va en UN renglón larguísimo. No lo abras entero para leerlo.
  const FUENTES_CARTA = [
    ['Archivo', 'normal', '400 700', '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'],
    ['Chivo Mono', 'normal', '400', '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'],
    ['Piazzolla', 'italic', '500', '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'],
  ];
  // Se cuelgan una sola vez y no se sacan al cambiar de estilo: sacarlas haría parpadear
  // el texto, y una fuente declarada que nadie usa no cuesta nada.
  function fuentesCarta(prender){
    if (!prender || document.getElementById('fuentesCarta')) return;
    const s = document.createElement('style');
    s.id = 'fuentesCarta';
    s.textContent = FUENTES_CARTA.map(f => "@font-face{font-family:'" + f[0] + "';font-style:" +
      f[1] + ';font-weight:' + f[2] + ';font-display:swap;src:url(data:font/woff2;base64,' +
      f[3] + ") format('woff2')}").join('');
    document.head.appendChild(s);
  }

  const CSS = `
:root{--tipo:'Segoe UI',system-ui,sans-serif;--acento:#8ecbff;--acento-bg:#16233a;
      --fondo:#0b0d12;--fondo2:#0f1320;--fondo-img:none;--escala:1;--ui:1;
      --burbuja-vos:#1d4ed8;--burbuja-vos-txt:#fff;--burbuja-ia:#171c24;
      --burbuja-ia-borde:#a78bfa;--borde:#232a35;--borde-fuerte:#2d3a4d;
      /* El semáforo de fábrica, por si la hoja se lee antes de que corra el script. */
      --ok:#3ddc84;--ok-2:#2b9b5e;--ok-txt:#9eedc1;--ok-bd:#1d5c39;--ok-bg:#123a24;
      --mal:#ef4444;--mal-2:#a83131;--mal-txt:#f7a1a1;--mal-bd:#5a2a2a;--mal-bg:#3a1a1a;
      --aviso:#f59e0b;--aviso-2:#ab7008;--aviso-txt:#facf85;--aviso-bd:#5b4d1c;
      --aviso-bg:#3a3212;
      /* Y las sombras de fábrica, por lo mismo: son los valores que estas pantallas
         tenían escritos a mano antes de que la sombra se pudiera elegir. */
      --sombra-0:0 1px 3px rgba(0,0,0,.3);--sombra-1:0 3px 10px rgba(0,0,0,.4);
      --sombra-2:0 8px 24px rgba(0,0,0,.5);--sombra-3:0 16px 46px rgba(0,0,0,.6);
      --sombra-arriba:0 -18px 45px rgba(0,0,0,.5);--vidrio:1}
/* ⭐ Apagar el movimiento. Va con !important y sobre el selector universal porque es lo
   único que puede ganarle a cincuenta reglas escritas en cinco pantallas distintas, y con
   animation:none —no con duración cero— para que lo animado quede en su estado NORMAL:
   una animación acelerada al infinito parpadea, y una cortada a la fuerza puede dejar el
   elemento invisible si su último fotograma lo era.
   ⚠ Ojo al editar esta hoja: vive adentro de un template literal, así que un acento
   invertido en un comentario CORTA la cadena y el archivo deja de ser JavaScript válido
   (pasó justo acá el 2026-08-29). */
html.movi-poco *,html.movi-poco *::before,html.movi-poco *::after,
html.movi-nada *,html.movi-nada *::before,html.movi-nada *::after{
  animation:none !important}
html.movi-nada *,html.movi-nada *::before,html.movi-nada *::after{
  transition:none !important;scroll-behavior:auto !important}
/* ⭐ Los bloques del panel con color propio: el título y un filito al costado. La clase
   la pone el script SOLO cuando ese bloque tiene color — sin ella no hay ::before, o sea
   que a quien no eligió nada no se le mueve ni un píxel del título.
   ⚠ Sin acentos invertidos en estos comentarios: cortan el template literal (ver abajo). */
[data-bloque].bq-color > h2{color:var(--bloque)}
[data-bloque].bq-color > h2::before{content:'';display:inline-block;width:3px;
  height:.92em;border-radius:2px;margin-right:8px;vertical-align:-2px;
  background:var(--bloque)}
html,body{font-family:var(--tipo)}
/* ⭐ Los efectos de la letra, cada uno con SU CLASE en el html y ninguna regla cuando no
   elegiste nada.
   ⚠⚠ La primera versión ponía una sola regla fija en el body con var(--peso,400) y sus
   respaldos, y parecía inofensiva: los respaldos eran los valores del navegador. Pero una
   regla que existe SIEMPRE le gana a la de la pantalla — el celular y /sesiones declaran su
   propio interlineado en el body, y quedaron con 62.000 y 6.700 píxeles distintos. Lo cazó
   foto_pantallas.py. Sin clase no hay regla, y sin regla no hay nada que pisar.
   ⚠ Las reglas se escriben DESDE las tablas de arriba, no a mano: duplicar los valores
   acá abajo es la forma segura de que un día digan cosas distintas.
   ⚠ Y ojo con los acentos invertidos en estos comentarios: cortan el template literal. */
${Object.keys(PESOS).filter(k => k !== 'normal').map(k =>
  'html.peso-' + k + ' body{font-weight:' + PESOS[k][1] + '}').join('\n')}
${Object.keys(ESPACIADOS).filter(k => k !== 'normal').map(k =>
  'html.esp-' + k + ' body{letter-spacing:' + ESPACIADOS[k][1] + '}').join('\n')}
${Object.keys(RENGLONES).filter(k => k !== 'normal').map(k =>
  'html.ren-' + k + ' body{line-height:' + RENGLONES[k][1] + '}').join('\n')}
html.con-fx body{text-shadow:var(--letra-fx)}
/* ⭐ La tipografía de los títulos. Esta SÍ va siempre y no con clase, y arregla de paso
   algo que estaba roto desde antes: varias pantallas tienen un *{font-family:Segoe UI}
   —el selector universal, que le gana a la herencia del body— así que elegir "Con serifa"
   nunca les cambió los títulos. Con el respaldo en var(--tipo) el titulo sigue al texto
   cuando no elegiste letra propia, y con la tipografía de fábrica queda igual que siempre
   (verificado con foto_pantallas: cero píxeles). */
h1,h2,h3{font-family:var(--tipo-titulo,var(--tipo))}
body{background-color:var(--fondo);background-image:var(--fondo-img);
     background-size:cover;background-position:center;background-attachment:fixed;
     background-repeat:no-repeat}
#aspectoBtn{display:inline-flex;align-items:center;justify-content:center;
  width:30px;height:26px;border-radius:999px;border:1px solid var(--c262e3a,#262e3a);background:var(--c161b23,#161b23);
  font-size:14px;line-height:1;cursor:pointer;padding:0;flex:none}
#aspectoBtn:hover{background:var(--c1d2530,#1d2530);border-color:var(--c3a4658,#3a4658)}
/* ⚠ Con tope de alto y scroll propio: desde que se puede elegir también el tamaño del
   texto y cuánto se ve la foto, el panel entero no entra en la pantalla del teléfono y
   las últimas opciones quedaban abajo del borde, sin forma de llegar. */
#aspectoPanel{display:none;position:fixed;z-index:9999;width:calc(290px * var(--ui,1));
  background:var(--c151b26,#151b26);border:1px solid var(--c2a3342,#2a3342);border-radius:13px;padding:calc(13px * var(--ui,1)) calc(15px * var(--ui,1));
  box-shadow:var(--sombra-3);color:var(--ce8ecf1,#e8ecf1);
  max-height:calc(100dvh - 84px);overflow-y:auto;overscroll-behavior:contain;
  font:calc(13px * var(--ui,1))/1.45 'Segoe UI',system-ui,sans-serif}
#aspectoPanel.abierto{display:block}
#aspectoPanel .rub{font-size:calc(10.5px * var(--ui,1));letter-spacing:.16em;text-transform:uppercase;
  color:var(--c5c6675,#5c6675);font-weight:700;margin:calc(11px * var(--ui,1)) 0 calc(7px * var(--ui,1))}
#aspectoPanel .rub:first-child{margin-top:0}
#aspectoPanel .ops{display:flex;flex-wrap:wrap;gap:calc(6px * var(--ui,1))}
#aspectoPanel .op{padding:calc(6px * var(--ui,1)) calc(11px * var(--ui,1));border-radius:9px;background:var(--c1b2130,#1b2130);color:var(--c9aa6b5,#9aa6b5);
  font-size:calc(12.5px * var(--ui,1));cursor:pointer;border:1px solid transparent}
#aspectoPanel .op:hover{background:var(--c222b3d,#222b3d)}
#aspectoPanel .op.sel{border-color:var(--acento);color:var(--acento)}
#aspectoPanel .punto{width:calc(26px * var(--ui,1));height:calc(26px * var(--ui,1));border-radius:50%;padding:0;
  border:2px solid transparent}
#aspectoPanel .punto.sel{border-color:var(--ce8ecf1,#e8ecf1)}
/* La rueda de color: un <input type=color> disfrazado de pastilla redonda, para que
   quede en la misma fila que los colores de siempre.
   ⚠ Va adentro de un aro ARCOÍRIS: pintada del color actual a secas era el noveno
   puntito de la fila y nada decía que ahí se elige cualquier otro. */
#aspectoPanel .ruedaCaja{display:inline-flex;padding:calc(3px * var(--ui,1));border-radius:50%;
  border:2px solid transparent;
  background:conic-gradient(var(--cf87171,#f87171),var(--cfbbf24,#fbbf24),var(--c34d399,#34d399),var(--c22d3ee,#22d3ee),var(--c60a5fa,#60a5fa),var(--cc084fc,#c084fc),var(--cf87171,#f87171))}
#aspectoPanel .ruedaCaja.sel{border-color:var(--ce8ecf1,#e8ecf1)}
#aspectoPanel .rueda{width:calc(20px * var(--ui,1));height:calc(20px * var(--ui,1));padding:0;border-radius:50%;cursor:pointer;
  border:none;background:none;-webkit-appearance:none;appearance:none}
#aspectoPanel .rueda::-webkit-color-swatch-wrapper{padding:0}
#aspectoPanel .rueda::-webkit-color-swatch{border:none;border-radius:50%}
#aspectoPanel .rueda::-moz-color-swatch{border:none;border-radius:50%}
/* ⭐ Los colores por parte: una fila por parte, con el nombre a la izquierda y la rueda
   a la derecha. Se hizo así y NO con una fila de colores sugeridos como el rastro porque
   son siete partes: siete filas de seis pastillas cada una es un panel de dos pantallas
   de alto, y con la rueda cada parte ocupa un renglón (2026-08-29). */
#aspectoPanel .parte{display:flex;align-items:center;gap:calc(8px * var(--ui,1));margin:calc(5px * var(--ui,1)) 0}
#aspectoPanel .parte .nom{flex:1;color:var(--c9aa6b5,#9aa6b5);font-size:calc(12.5px * var(--ui,1))}
#aspectoPanel .parte.puesto .nom{color:var(--ce8ecf1,#e8ecf1)}
/* El ↺ vuelve esa parte al tema. Solo aparece si esa parte tiene un color elegido: si no,
   es un botón que no hace nada. */
#aspectoPanel .parte .quitar{cursor:pointer;color:var(--c6b7686,#6b7686);font-size:calc(13px * var(--ui,1));padding:0 calc(3px * var(--ui,1))}
#aspectoPanel .parte .quitar:hover{color:var(--ce8ecf1,#e8ecf1)}
/* Los deslizadores del vidrio (2026-11-10): nombre y valor arriba, la barra abajo a todo
   el ancho. La barra toma el color de acento, como lo elegido en el resto del panel. */
#aspectoPanel .desliz{margin:calc(9px * var(--ui,1)) 0 calc(4px * var(--ui,1))}
#aspectoPanel .desliz .cab{display:flex;align-items:center;gap:calc(8px * var(--ui,1))}
#aspectoPanel .desliz .nom{flex:1;color:var(--c9aa6b5,#9aa6b5);font-size:calc(12.5px * var(--ui,1))}
#aspectoPanel .desliz.puesto .nom{color:var(--ce8ecf1,#e8ecf1)}
#aspectoPanel .desliz .val{color:var(--c7d8899,#7d8899);font-size:calc(11.5px * var(--ui,1));
  font-variant-numeric:tabular-nums}
#aspectoPanel .desliz .quitar{cursor:pointer;color:var(--c6b7686,#6b7686);font-size:calc(13px * var(--ui,1))}
#aspectoPanel .desliz .quitar:hover{color:var(--ce8ecf1,#e8ecf1)}
#aspectoPanel .desliz input{width:100%;margin:calc(6px * var(--ui,1)) 0 0;accent-color:var(--acento,#8ecbff);
  cursor:pointer}
#aspectoPanel .op .gota{display:inline-block;width:calc(9px * var(--ui,1));height:calc(9px * var(--ui,1));
  border-radius:50%;margin-right:calc(6px * var(--ui,1));vertical-align:-1px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.25)}
#aspectoPanel .avisoVidrio{margin:calc(4px * var(--ui,1)) 0 calc(2px * var(--ui,1));color:var(--c7d8899,#7d8899);
  font-size:calc(11.5px * var(--ui,1));line-height:1.35}
#aspectoPanel .pie{margin-top:calc(12px * var(--ui,1));display:flex;gap:calc(7px * var(--ui,1));flex-wrap:wrap;
  border-top:1px solid var(--c232a35,#232a35);padding-top:calc(11px * var(--ui,1))}
#aspectoPanel .pie .op{flex:none}
#aspectoPanel .fabrica{margin-top:calc(10px * var(--ui,1));border-top:1px solid var(--c232a35,#232a35);padding-top:calc(10px * var(--ui,1))}
#aspectoPanel .fabrica .op{display:inline-block;color:var(--c7d8899,#7d8899)}
/* ⭐ Las secciones plegables (2026-08-29). El panel pasó de diecisiete renglones a
   treinta y pico: con todo desplegado no se encuentra nada y la última opción queda dos
   pantallas abajo (le pasó con la rueda del fondo el mismo día que se agregó). Arriba
   quedan los estilos, que es lo que uno quiere probar primero; el resto se abre. */
#aspectoPanel .sec{border-top:1px solid var(--c232a35,#232a35)}
#aspectoPanel .sec > summary{list-style:none;cursor:pointer;padding:calc(9px * var(--ui,1)) 0;
  font-size:calc(10.5px * var(--ui,1));letter-spacing:.16em;text-transform:uppercase;font-weight:700;
  color:var(--c5c6675,#5c6675);display:flex;align-items:center;gap:calc(7px * var(--ui,1));user-select:none}
#aspectoPanel .sec > summary::-webkit-details-marker{display:none}
#aspectoPanel .sec > summary::before{content:'▸';font-size:calc(9px * var(--ui,1));letter-spacing:0}
#aspectoPanel .sec[open] > summary::before{content:'▾'}
#aspectoPanel .sec > summary:hover{color:var(--c9aa6b5,#9aa6b5)}
#aspectoPanel .cuerpoSec{padding-bottom:calc(10px * var(--ui,1))}
#aspectoPanel .cuerpoSec .rub:first-child{margin-top:0}
/* La fila de estilos: pastillas un poco más grandes, porque cada una pinta la pantalla
   entera y no es lo mismo que elegir un valor de una lista. */
/* El desplegable de tipografías instaladas, y el aviso de que esa letra puede no estar
   en el teléfono. */
#aspectoPanel .selFuente{width:100%;margin-top:calc(7px * var(--ui,1));padding:calc(6px * var(--ui,1)) calc(8px * var(--ui,1));border-radius:9px;
  background:var(--c1b2130,#1b2130);color:var(--c9aa6b5,#9aa6b5);
  border:1px solid var(--c2a3342,#2a3342);font-size:calc(12.5px * var(--ui,1));cursor:pointer}
#aspectoPanel .selFuente:hover{background:var(--c222b3d,#222b3d)}
#aspectoPanel .avisoLetra{margin-top:calc(6px * var(--ui,1));font-size:calc(11px * var(--ui,1));line-height:1.35;
  color:var(--aviso-txt)}
/* El pie de "quedan fijos": explica qué quedó clavado y ofrece volver a clavarlo. Va en
   gris y no en ámbar porque no es una advertencia — es el estado normal de esa opción. */
#aspectoPanel .avisoZoom{margin-top:calc(6px * var(--ui,1));font-size:calc(11px * var(--ui,1));line-height:1.4;
  color:var(--c9aa6b5,#9aa6b5)}
#aspectoPanel .avisoZoom .op{display:inline-block;padding:calc(2px * var(--ui,1)) calc(8px * var(--ui,1));margin-top:calc(5px * var(--ui,1))}
#aspectoPanel .estilos{margin-bottom:calc(9px * var(--ui,1))}
#aspectoPanel .esti{padding:calc(7px * var(--ui,1)) calc(12px * var(--ui,1));font-size:calc(12.5px * var(--ui,1))}
#aspectoPanel .volver{margin:0 0 calc(10px * var(--ui,1))}
#aspectoPanel .volver .op{display:inline-block;color:var(--c9aa6b5,#9aa6b5)}
/* ⭐ Las FORMAS de Grok y su movimiento (2026-10-31) — y desde el 2026-11-10, las de TODOS
   los estilos: Martín pidió que los otros cinco fueran sub-versiones de este. Todo cuelga
   de la clase estilo-grok, que el script pone con cualquier estilo elegido; con "El de
   siempre" o "volver a lo mío" ninguna de estas reglas existe y la pantalla queda como
   estaba. Barras de vidrio flotando sobre la foto, pastillas, burbujas grandes y redondas,
   botones que se hunden al tocarlos con un rebote de resorte. Los mensajes NUEVOS entran
   deslizando (la clase grok-entra la pone el script, solo al que llegó).
   ⚠⚠ Acá abajo no se escribe ningún blanco ni negro a mano. El mismo bloque tiene que
   servir sobre negro (Grok, Terminal, Neón), sobre azul (Nórdico) y sobre papel claro, así
   que todo sale de dos cosas:
   · --grok-t, la tinta de los velos en "tres números" para poder darle transparencia:
     blanca en oscuro, casi negra en el tema claro. Un velo blanco sobre papel no se ve.
   · --grok-fuerte, la pieza llena (la pestaña elegida y Mandar): blanca en Grok, del
     acento en los demás. Ese color y el de su letra los pone el script (ver aplicar).
   Lo que es propio del Grok original y no de sus sub-versiones va con grok-puro. */
#grokFx{position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none}
html.estilo-grok{--grok-resorte:cubic-bezier(.22,1.25,.36,1);
  --grok-vidrio:color-mix(in srgb,var(--fondo) 80%,transparent);
  --grok-t:255,255,255;--grok-linea:rgba(var(--grok-t),.09);
  --grok-fuerte:#f4f4f5;--grok-fuerte-txt:#0a0a0a;--grok-fuerte-viva:#15803d}
html.estilo-grok.tema-claro{--grok-t:28,34,46;--grok-linea:rgba(var(--grok-t),.15)}
html.estilo-grok button,html.estilo-grok .tab,html.estilo-grok .correo,
html.estilo-grok .chip,html.estilo-grok .op{
  transition:transform .28s var(--grok-resorte),background-color .25s ease,color .25s ease,
             box-shadow .25s ease,border-color .25s ease}
html.estilo-grok button:active,html.estilo-grok .tab:active,
html.estilo-grok .correo:active{transform:scale(.94)}
/* Las barras: vidrio esmerilado sin filo, la foto se ve pasar por abajo. Un estilo que
   pide "sin vidrio" (Terminal, Papel) deja --vidrio en cero: queda la barra lisa. */
html.estilo-grok #barraArriba,html.estilo-grok #abajo,html.estilo-grok #escribir,
html.estilo-grok #cabecera{background:var(--grok-vidrio);border-top:0;border-bottom:0;
  box-shadow:none;backdrop-filter:blur(calc(18px * var(--vidrio,1))) saturate(1.3);
  -webkit-backdrop-filter:blur(calc(18px * var(--vidrio,1))) saturate(1.3)}
html.estilo-grok .tab{background:rgba(var(--grok-t),.06);border:1px solid var(--grok-linea)}
html.grok-puro .tab{color:#d4d4d8}
html.estilo-grok .tab.sel{background:var(--grok-fuerte);color:var(--grok-fuerte-txt);
  border-color:var(--grok-fuerte)}
html.estilo-grok .tab.sel .viva{color:var(--grok-fuerte-viva)}
html.estilo-grok #titulo .volver,html.estilo-grok #titulo .cierra{width:36px;height:36px;
  background:rgba(var(--grok-t),.08);border:1px solid var(--grok-linea)}
html.estilo-grok #titulo .eti{border-radius:999px;padding:3px 9px}
/* Las burbujas: grandes y redondas. La tuya del color del estilo (no el verde de
   WhatsApp); una charla con color propio sigue mandando, como siempre. */
html.estilo-grok .msg{border-radius:22px;padding:11px 16px;box-shadow:none}
html.estilo-grok .vos{background:var(--charla-vos,var(--burbuja-vos));
  color:var(--charla-vos-txt,var(--burbuja-vos-txt));border-bottom-right-radius:7px}
html.estilo-grok .claude,html.estilo-grok .ia{background:var(--charla-ia,rgba(var(--grok-t),.06));
  border:1px solid var(--grok-linea);border-top-left-radius:7px}
/* ⚠ El borde fino de arriba pisaba el color que una charla (o su carpeta) eligió para la
   burbuja de la sesión: en la compu ese color ES el borde, así que desaparecía entero.
   Con color propio, el contorno toma ese color (2026-11-10; lo cuida ver_color_charla). */
html.estilo-grok .con-color-ia .claude,html.estilo-grok .con-color-ia .ia{
  border-color:var(--charla-ia-borde,var(--grok-linea))}
html.estilo-grok .msg.grok-entra{animation:grokEntra .5s var(--grok-resorte) both}
html.estilo-grok .msg.vos.grok-entra{transform-origin:100% 100%}
html.estilo-grok .msg.claude.grok-entra{transform-origin:0 0}
@keyframes grokEntra{from{opacity:0;transform:translateY(14px) scale(.96)}
                     to{opacity:1;transform:none}}
/* Pensando: un brillo que barre la burbuja, en vez de quedarse quieta. */
html.estilo-grok .pensando{background-image:linear-gradient(100deg,transparent 30%,
  rgba(var(--grok-t),.09) 50%,transparent 70%);background-size:250% 100%;
  animation:grokBrillo 1.8s linear infinite}
@keyframes grokBrillo{from{background-position:120% 0}to{background-position:-120% 0}}
/* La caja de escribir: una pastilla con aro al enfocarla, y Mandar como pieza llena. */
html.estilo-grok #texto{border-radius:26px;background:rgba(var(--grok-t),.07);
  border:1px solid rgba(var(--grok-t),.13)}
html.estilo-grok #texto:focus{outline:none;
  border-color:color-mix(in srgb,var(--acento) 60%,transparent);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--acento) 18%,transparent)}
html.estilo-grok #mandar{background:var(--grok-fuerte);color:var(--grok-fuerte-txt);font-weight:700}
/* La lista de sesiones: tarjetas redondas en vez de renglones con raya. El estado deja
   de ser una barra de color a la izquierda y pasa a ser un puntito al final que brilla
   (el de trabajando late). Los colores siguen siendo los del semáforo. */
html.estilo-grok .correo{border-bottom:0;border-radius:18px;margin:5px 0;padding:12px;
  background:rgba(var(--grok-t),.035);border:1px solid rgba(var(--grok-t),.05)}
html.estilo-grok .correo.espera,html.estilo-grok .correo.trabajando,
html.estilo-grok .correo.fallada{border-left:1px solid rgba(var(--grok-t),.05);padding-left:12px}
html.estilo-grok .correo.espera{background:var(--ok-bg)}
html.estilo-grok .correo.trabajando{background:var(--aviso-bg)}
html.estilo-grok .correo.fallada{background:var(--mal-bg)}
/* El renglón de abajo, sobre una tarjeta TEÑIDA por su estado, quedaba en 4,2 de contraste
   (hace falta 4,5): el gris de siempre está pensado para el fondo liso. */
html.estilo-grok .correo.espera .baj,html.estilo-grok .correo.trabajando .baj,
html.estilo-grok .correo.fallada .baj{color:rgba(var(--grok-t),.68)}
html.estilo-grok .correo.espera::after,html.estilo-grok .correo.trabajando::after,
html.estilo-grok .correo.fallada::after{content:'';flex:none;width:9px;height:9px;
  border-radius:50%;background:var(--ok);box-shadow:0 0 10px var(--ok)}
html.estilo-grok .correo.trabajando::after{background:var(--aviso);
  box-shadow:0 0 10px var(--aviso);animation:grokLatido 1.4s ease-in-out infinite}
html.estilo-grok .correo.fallada::after{background:var(--mal);box-shadow:0 0 10px var(--mal)}
@keyframes grokLatido{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(.6);opacity:.5}}
/* ⭐ La columna de carpetas de Sesiones (2026-11-10, Martín con una captura: "se sigue
   sintiendo feo"). Eran bandas de color pegadas una a la otra y al borde izquierdo, con
   medio óvalo a la derecha: el resto de la pantalla ya era de pastillas y esto no.
   Ahora cada carpeta es una ficha suelta con aire alrededor. La pintada conserva SU color
   (va en el style del elemento, no se toca) y gana un filo fino del mismo tono, que antes
   estaba calculado y no se veía porque el renglón no tenía borde.
   ⚠⚠ Sin transition ni :active en .carpeta: el arrastre de la fila entera pone su propia
   transición de posición (.acomodando) y una regla de acá, que pesa más, se la pisaría —
   el reordenado volvería a ser un salto seco.
   ⚠ El margen y el relleno son IGUALES en todas (pintada, elegida o pelada): es lo que
   mantiene en columna las marcas de la derecha (ver_marcas_en_columna lo mide). */
html.estilo-grok aside{border-right-color:var(--grok-linea)}
html.estilo-grok .rubro{margin-left:23px}
html.estilo-grok #buscar{width:calc(100% - 20px);margin:0 10px 8px;padding:8px 14px;
  border-radius:999px;background:rgba(var(--grok-t),.06);border:1px solid var(--grok-linea)}
html.estilo-grok .carpeta{margin:3px 10px;border-radius:14px;border:1px solid transparent;
  padding:calc(7px * var(--ui,1)) calc(12px * var(--ui,1))}
html.estilo-grok .carpeta:hover{background:rgba(var(--grok-t),.06)}
html.estilo-grok .carpeta.sel{background:rgba(var(--grok-t),.1);border-color:var(--grok-linea)}
/* La pintada: su color manda sobre el de "pasaste el mouse" y el de "estás acá", así que
   esas dos cosas se dicen de otra forma — un poco más de luz, y un aro de su propio tono
   más la barrita de siempre, corrida para que no se coma la esquina redonda. */
html.estilo-grok .carpeta.pintada:hover{filter:brightness(1.2)}
html.estilo-grok .carpeta.pintada.sel{
  box-shadow:inset 0 0 0 1px color-mix(in srgb,currentColor 60%,transparent)}
html.estilo-grok .carpeta.pintada.sel::after{left:5px;top:9px;bottom:9px;border-radius:3px}
html.estilo-grok .carpeta.deslizando{background:color-mix(in srgb,var(--fondo) 88%,rgb(var(--grok-t)))}
html.estilo-grok .carpeta.hueco-arriba::before{top:-3px}
html.estilo-grok .carpeta.hueco-abajo::after{bottom:-3px}
/* Las marcas de la derecha siguen TODAS en su lugar, pero dejan de gritar: casi todas las
   carpetas heredan el navegador de base, así que el globito en cada renglón no decía nada,
   y un cero repetido catorce veces tampoco. Se encienden en el renglón donde estás. */
html.estilo-grok .carpeta .naveg{opacity:.3}
html.estilo-grok .carpeta:hover .naveg,html.estilo-grok .carpeta.sel .naveg{opacity:.8}
html.estilo-grok .carpeta .num.cero{opacity:0}
html.estilo-grok .carpeta:hover .num.cero{opacity:.75}
html.estilo-grok .carpeta .plegar{opacity:.55}
html.estilo-grok .carpeta:hover .plegar{opacity:1}
html.estilo-grok .carpeta .plegar:hover{background:rgba(var(--grok-t),.12)}
html.estilo-grok .carpeta.sumar{margin-top:8px;border:1px dashed rgba(var(--grok-t),.16)}
html.estilo-grok .carpeta.guardadas{margin-top:8px}
html.estilo-grok .carpeta.devolver{padding-left:30px}
html.estilo-grok .subcarpeta{margin:1px 10px 1px calc(32px * var(--ui,1));
  border-radius:0 10px 10px 0;border-left-color:rgba(var(--grok-t),.14)}
html.estilo-grok .subcarpeta:hover{background:rgba(var(--grok-t),.06)}
html.estilo-grok .subcarpeta.sel{background:rgba(var(--grok-t),.1);border-left-color:currentColor}
/* La barra de desplazamiento conserva el carril ancho para agarrarla (decisión del
   2026-09-13); lo que cambia es el pulgar, que era una franja gris y ahora es un velo. */
html.estilo-grok #paneProy::-webkit-scrollbar-thumb,html.estilo-grok #arbol::-webkit-scrollbar-thumb{
  background:rgba(var(--grok-t),.16);background-clip:content-box}
html.estilo-grok #paneProy::-webkit-scrollbar-thumb:hover,
html.estilo-grok #arbol::-webkit-scrollbar-thumb:hover{
  background:rgba(var(--grok-t),.36);background-clip:content-box}
/* ⭐ El menú de pantallas y el ⚡ sobre un fondo CLARO (2026-11-10). Sus colores están
   escritos a mano en menu.js y atajos.js, pensados para fondo oscuro, y el tema claro no
   los alcanza: sobre papel quedaban como pastillas negras. Acá se les da la tinta del
   tema claro. No depende de tener un estilo puesto: vale también para "El de siempre"
   con un fondo claro. Los menús que se DESPLIEGAN siguen oscuros: flotan encima, se leen. */
html.tema-claro .menu-pantallas a,html.tema-claro button.at-boton{
  background:rgba(28,34,46,.05);border-color:rgba(28,34,46,.16);color:#4b5565}
html.tema-claro .menu-pantallas a:hover,html.tema-claro button.at-boton:hover{
  background:rgba(28,34,46,.1);border-color:rgba(28,34,46,.3);color:#111827}
html.tema-claro .menu-pantallas a.aca,html.tema-claro .menu-pantallas .abrir,
html.tema-claro button.at-boton.abierto{background:var(--acento-bg);
  border-color:color-mix(in srgb,var(--acento) 45%,transparent);color:var(--acento)}
html.tema-claro .menu-pantallas.mini .todo a{background:#161b23;border-color:#262e3a;color:#8b93a1}
html.tema-claro .menu-pantallas.mini .todo a.aca{background:#16263a;border-color:#2c4a6b;color:#cfe6ff}
`;

  // Con qué color arranca la rueda de cada parte: el elegido si lo hay, y si no el que
  // esa parte tiene HOY siguiendo al tema. Se calcula acá y no se lee de la variable CSS
  // porque las variables salen como `rgb(…)` y la rueda solo entiende '#rrggbb'.
  function colorParte(k){
    if (esLibre(aspecto[k])) return aspecto[k];
    if (PARTES[k][1]) return PARTES[k][1];               // el semáforo tiene el de fábrica
    if (k === 'barra' || k === 'pizBarra') return '#161b23';
    return colorDe(fondoDe()[1])[0];                                   // las burbujas
  }

  // Con qué color arranca cada rueda de tinte y de bloque cuando todavía no elegiste nada:
  // el que esa cosa tiene HOY. Un selector de color que arranca en negro no te dice nada.
  const colorTinta = k => esLibre(aspecto[k]) ? aspecto[k]
                        : k === 'tintaLetras' ? '#e8eaed' : '#0f1320';
  function colorBloque(k){
    const el = (aspecto.bloques || {})[k];
    if (esLibre(el)) return el;
    return girar(colorDe(fondoDe()[1])[0], (BLOQUES[k][1] || 0) * PASO_BLOQUE);
  }

  // Un desplegable con las nueve de siempre MÁS todas las que estén instaladas. Cada
  // opción se dibuja con su propia letra: es la única forma de elegir una tipografía
  // mirándola, en vez de adivinando por el nombre. Va en desplegable y no en pastillas
  // porque son más de cuarenta y taparían la fila de nueve, que es la que anda en todos
  // lados. `vacio` es lo que dice la primera opción cuando no hay nada elegido.
  function selectorFuente(campo, valor, vacio){
    const e = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                            .replace(/"/g, '&quot;');
    const nueve = Object.keys(TIPOS).map(k =>
      '<option value="' + k + '"' + (valor === k ? ' selected' : '') +
      ' style="font-family:' + TIPOS[k][1] + '">' + e(TIPOS[k][0]) + '</option>').join('');
    const otras = fuentesInstaladas().map(f =>
      '<option value="' + e(f) + '"' + (valor === f ? ' selected' : '') +
      " style=\"font-family:'" + e(f) + "'\">" + e(f) + '</option>').join('');
    return '<select class="selFuente" data-fuente="' + campo + '">' +
      '<option value=""' + (valor ? '' : ' selected') + '>' + e(vacio) + '</option>' +
      nueve + (otras ? '<optgroup label="Instaladas acá">' + otras + '</optgroup>' : '') +
      '</select>';
  }

  // ⭐ Qué secciones del panel están abiertas. ⚠⚠ Vive ACÁ AFUERA y no en el DOM porque el
  // panel se vuelve a dibujar entero en cada elección: si el estado viviera en el
  // `<details>`, elegir un color te cerraría la sección que estás usando y habría que
  // volver a abrirla en cada clic.
  // ⚠ Y se recuerda entre recargas, en el navegador y no en el servidor: es cómo tenés
  // ordenado el panel, no cómo se ven las pantallas. Sin esto, cada vez que abrís el 🎨
  // hay que hacer dos clics para llegar a lo que venís tocando siempre — antes era uno.
  // ⚠ La primera vez arrancan TODAS cerradas, y se midió para decidirlo: con una sola
  // sección abierta el panel mide 742 px y hay que hacer scroll para llegar al fondo;
  // cerradas mide 420 y entra entero en el teléfono. Se ve el mapa completo de lo que se
  // puede tocar, y a partir del segundo uso queda como vos lo dejaste.
  const abiertas = new Set((() => {
    try { return JSON.parse(localStorage.getItem('aspectoAbiertas') || '[]'); }
    catch (e) { return []; }
  })());
  const recordarAbiertas = () => {
    try { localStorage.setItem('aspectoAbiertas', JSON.stringify([...abiertas])); }
    catch (e) {}
  };

  // Lo de fábrica de un campo: el del estilo puesto si lo trae, y si no el de siempre.
  // Es a donde vuelve el ↺ de un deslizador (Vidrio trae su desenfoque, por ejemplo).
  const fabricaDe = k => {
    const e = ESTILOS[aspecto.estilo];
    if (e && e.campos[k] !== undefined) return e.campos[k];
    return LIMPIO[k] !== undefined ? LIMPIO[k] : '';
  };
  // Los cuatro deslizadores del vidrio. `leer` da el número que muestra la barra, aunque
  // el campo esté vacío (de fábrica); `escribir` lo pasa a lo que se guarda.
  const DESLIZ = {
    vidrio:   {nom: 'Desenfoque', min: 0, max: 300, paso: 5,
               leer: () => Math.round(desenfoqueDe(aspecto.vidrio) * 100),
               fab: () => Math.round(desenfoqueDe(fabricaDe('vidrio')) * 100),
               escribir: n => (n / 100).toFixed(2),
               texto: n => n ? Math.round(18 * n / 100) + ' px' : 'Sin desenfoque'},
    vdOpaco:  {nom: 'Opacidad de los paneles', min: 0, max: 100, paso: 1,
               leer: () => Math.round(numVd('vdOpaco')), escribir: String, fab: () => VD_FAB.vdOpaco,
               texto: n => n <= 3 ? 'Casi invisibles' : n >= 95 ? 'Casi sólidos' : n + ' %'},
    vdBrillo: {nom: 'Brillo del borde', min: 0, max: 200, paso: 5,
               leer: () => Math.round(numVd('vdBrillo')), escribir: String, fab: () => VD_FAB.vdBrillo,
               texto: n => n ? n + ' %' : 'Sin brillo'},
    vdGrano:  {nom: 'Grano', min: 0, max: 200, paso: 5,
               leer: () => Math.round(numVd('vdGrano')), escribir: String, fab: () => VD_FAB.vdGrano,
               texto: n => n ? n + ' %' : 'Liso'},
  };

  function pintarPanel(){
    const panel = document.getElementById('aspectoPanel');
    if (!panel) return;
    const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const ops = (obj, campo, dibujo) =>
      Object.keys(obj).map(k => dibujo(k, obj[k], aspecto[campo] === k)).join('');
    // Una fila "nombre + ↺ + rueda", que es como se elige todo lo que no tiene una fila de
    // opciones sugeridas. `campo` es la clave de `aspecto` que toca esa rueda.
    const filaRueda = (campo, nombre, valor, puesto) =>
      '<div class="parte' + (puesto ? ' puesto' : '') + '" data-parte="' + campo + '">' +
        '<span class="nom">' + esc(nombre) + '</span>' +
        (puesto ? '<span class="quitar" title="Volver al del tema">↺</span>' : '') +
        '<span class="ruedaCaja' + (puesto ? ' sel' : '') + '">' +
          '<input type="color" class="rueda" data-rueda="' + campo + '" value="' +
          valor + '"></span></div>';
    // Un deslizador del vidrio: nombre, cuánto vale ahora, ↺ si lo cambiaste, y la barra.
    const deslizador = k => {
      const d = DESLIZ[k], n = d.leer(), puesto = n !== d.fab();
      return '<div class="desliz' + (puesto ? ' puesto' : '') + '" data-desliz="' + k + '">' +
        '<div class="cab"><span class="nom">' + esc(d.nom) + '</span>' +
          '<span class="val">' + esc(d.texto(n)) + '</span>' +
          (puesto ? '<span class="quitar" title="Volver al de fábrica">↺</span>' : '') +
        '</div><input type="range" min="' + d.min + '" max="' + d.max + '" step="' + d.paso +
          '" value="' + n + '" aria-label="' + esc(d.nom) + '"></div>';
    };
    const seccion = (k, titulo, dentro) =>
      '<details class="sec" data-sec="' + k + '"' + (abiertas.has(k) ? ' open' : '') + '>' +
        '<summary>' + esc(titulo) + '</summary><div class="cuerpoSec">' + dentro +
        '</div></details>';
    const libre = esLibre(aspecto.color);
    panel.innerHTML =
      // ⚠ El aviso de "panel viejo" va ARRIBA DE TODO y fuera de las secciones. Estaba
      // adentro de "cada parte": desde que las secciones se pliegan, quedaba escondido
      // atrás de un renglón cerrado justo cuando hay que leerlo.
      '<div id="aspectoViejo" style="display:' +
        ((panelViejo && hayPartes()) ? '' : 'none') + ';margin:0 0 9px;padding:6px 8px;' +
        'border-radius:8px;background:#3a3212;color:#facf85;font-size:11.5px;line-height:1.35">' +
        '⚠ Esto se ve acá pero no viaja al celular: el panel quedó viejo, reinicialo.</div>' +
      // ⭐⭐ Los estilos, arriba de todo y sin plegar: es lo primero que uno quiere probar,
      // y con un botón se pinta todo junto y combinado. Lo de abajo es el retoque fino.
      '<div class="rub">Estilos</div><div class="ops estilos">' +
        '<div class="op esti' + (!aspecto.estilo ? ' sel' : '') + '" data-esti="" ' +
          'title="Los colores de siempre">El de siempre</div>' +
        Object.keys(ESTILOS).map(k => '<div class="op esti' +
            (aspecto.estilo === k ? ' sel' : '') + '" data-esti="' + k + '">' +
            esc(ESTILOS[k].nom) + '</div>').join('') +
      '</div>' +
      // El deshacer. Solo aparece si hay algo a lo que volver: un botón que no hace nada es
      // peor que no tenerlo.
      (aspecto.previo
        ? '<div class="volver"><div class="op" id="aspVolver" title="Devuelve la ' +
          'combinación que tenías antes de probar estilos">↺ Volver a lo mío</div></div>'
        : '') +
      seccion('colores', 'Colores',
      '<div class="rub">Color</div><div class="ops" data-campo="color">' +
        ops(COLORES, 'color', (k, v, sel) => '<div class="op punto' + (sel ? ' sel' : '') +
            '" data-v="' + k + '" title="' + k + '" style="background:' + v[1] +
            ';box-shadow:inset 0 0 0 3px ' + v[0] + '"></div>') +
        // Y la rueda, para cualquier otro color que se le ocurra.
        '<span class="ruedaCaja' + (libre ? ' sel' : '') + '" title="Elegir cualquier ' +
          'otro color"><input type="color" class="rueda" id="aspRueda" value="' +
          (libre ? aspecto.color : colorDe('#0b0d12')[0]) + '"></span>' +
      '</div>' +
      // ⭐ El rastro: los renglones que cuentan lo que la sesión va haciendo. Va acá y no
      // en una pantalla aparte porque es un gusto más, como la tipografía o el fondo.
      '<div class="rub">Color del rastro</div><div class="ops" data-campo="rastro">' +
        ops(RASTROS, 'rastro', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
            '" data-v="' + k + '"' + (v[1] ? ' style="color:' + v[1] + '"' : '') + '>' +
            esc(v[0]) + '</div>') +
        '<span class="ruedaCaja' + (esLibre(aspecto.rastro) ? ' sel' : '') +
          '" title="Cualquier otro color para el rastro">' +
          '<input type="color" class="rueda" id="aspRuedaRastro" value="' +
          (esLibre(aspecto.rastro) ? aspecto.rastro : '#93a0b4') + '"></span>' +
      '</div>' +
      // ⭐⭐ Las dos perillas que tiñen la pantalla entera por rol (ver `tenida()`). Son
      // DOS y no veinte: cada gris se clasifica solo por su luminosidad. Los botones
      // grises caen en "las cajas" sin necesitar perilla propia.
      '<div class="rub">Tinte general</div>' +
        filaRueda('tintaLetras', 'Las letras', colorTinta('tintaLetras'),
                  esLibre(aspecto.tintaLetras)) +
        filaRueda('tintaCajas', 'Las cajas y los botones', colorTinta('tintaCajas'),
                  esLibre(aspecto.tintaCajas))) +
      // ⭐ Un color para cada parte. Va DESPUÉS del acento a propósito: lo de arriba viste
      // la pantalla entera y esto son los retoques, así que el que no los quiere ni los mira.
      seccion('partes', 'Cada parte',
        Object.keys(PARTES).map(k =>
          filaRueda(k, PARTES[k][0], colorParte(k), esLibre(aspecto[k]))).join('')) +
      // ⭐ Las siete zonas con título del panel principal. La rueda de cada una arranca en
      // el color que ese bloque tiene hoy (el derivado del acento), así se ve de qué se
      // está hablando antes de tocar nada.
      seccion('tarjetas', 'Cada tarjeta del panel',
        Object.keys(BLOQUES).map(k => {
          const puesto = esLibre((aspecto.bloques || {})[k]);
          return '<div class="parte' + (puesto ? ' puesto' : '') + '" data-bloq="' + k + '">' +
            '<span class="nom">' + esc(BLOQUES[k][0]) + '</span>' +
            (puesto ? '<span class="quitar" title="Volver al del estilo">↺</span>' : '') +
            '<span class="ruedaCaja' + (puesto ? ' sel' : '') + '">' +
              '<input type="color" class="rueda" data-bloq-rueda="' + k + '" value="' +
              colorBloque(k) + '"></span></div>';
        }).join('')) +
      seccion('letra', 'Letra',
        '<div class="rub">Tipografía</div><div class="ops" data-campo="tipo">' +
          ops(TIPOS, 'tipo', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '" style="font-family:' + v[1] + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        // ⭐ Y cualquier otra que esté instalada. Va en un desplegable y no en pastillas
        // porque son cuarenta y pico: en pastillas ocupan media pantalla y la fila de
        // nueve, que son las elegidas a mano y las que andan en el celular, se pierde.
        selectorFuente('tipo', aspecto.tipo, 'Otra tipografía…') +
        (esFuenteLibre(aspecto.tipo)
          ? '<div class="avisoLetra">⚠ Esta letra puede no estar en el celular: ahí se va ' +
            'a ver con la de siempre.</div>' : '') +
        // El tamaño de la letra de las conversaciones, que es lo que uno se pasa leyendo.
        '<div class="rub">Tamaño del texto</div><div class="ops" data-campo="letra">' +
          ops(LETRAS, 'letra', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '" style="font-size:' + (12.5 * v[1]).toFixed(1) + 'px">' +
              esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Grosor</div><div class="ops" data-campo="peso">' +
          ops(PESOS, 'peso', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '" style="font-weight:' + v[1] + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Espacio entre letras</div><div class="ops" data-campo="espaciado">' +
          ops(ESPACIADOS, 'espaciado', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '" style="letter-spacing:' + v[1] + '">' + esc(v[0]) +
              '</div>') +
        '</div>' +
        '<div class="rub">Renglones</div><div class="ops" data-campo="renglon">' +
          ops(RENGLONES, 'renglon', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        // ⚠ Sombra y resplandor son los únicos de toda la tanda que la prueba de contraste
        // NO puede juzgar: mide el color del texto contra el fondo y una sombra no cambia
        // ese número. Por eso son suaves.
        '<div class="rub">Efecto del texto</div><div class="ops" data-campo="letraFx">' +
          ops(LETRA_FX, 'letraFx', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Letra de los títulos</div>' +
          selectorFuente('tipoTitulo', aspecto.tipoTitulo, 'La misma del texto')) +
      // ⭐⭐ El tamaño de los controles (2026-09-12). Va en su propia sección y no adentro
      // de "Letra" porque no es letra: es cuánto lugar le come la herramienta a lo que uno
      // vino a leer. La pastilla se dibuja con SU tamaño, igual que las del texto.
      seccion('botones', 'Botones y barras',
        '<div class="rub">Tamaño</div><div class="ops" data-campo="botones">' +
          ops(BOTONES, 'botones', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '" style="font-size:' + (12.5 * v[1]).toFixed(1) + 'px">' +
              esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Con el zoom del navegador</div>' +
        '<div class="ops" data-campo="botonesZoom">' +
          ops(ZOOM_BOTONES, 'botonesZoom', (k, v, sel) => '<div class="op' +
              (sel ? ' sel' : '') + '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        (aspecto.botonesZoom === 'fijo'
          ? '<div class="avisoZoom">Quedaron clavados al zoom de cuando lo prendiste: ' +
            'ampliando la página crece el texto y los botones no. ' +
            '<span class="op" id="aspClavarZoom">Usar el tamaño de ahora</span></div>'
          : '')) +
      seccion('efectos', 'Efectos',
        '<div class="rub">Sombra</div><div class="ops" data-campo="sombra">' +
          ops(SOMBRAS, 'sombra', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Movimiento</div><div class="ops" data-campo="movi">' +
          ops(MOVIS, 'movi', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>') +
      // ⭐ El vidrio, con su propia sección (2026-11-10, Martín: "siento que tengo
      // limitaciones a la hora de configurar el vidrio"). Antes era UNA fila de tres
      // pastillas en "Efectos" y movía solo el desenfoque. El desenfoque vale en todas las
      // pantallas; lo demás es el material del estilo Vidrio, y lo dice.
      seccion('vidrio', 'Vidrio',
        deslizador('vidrio') +
        (deVidrio() ? '' :
          '<div class="avisoVidrio">Lo de abajo se ve con el estilo «Vidrio» puesto.</div>') +
        deslizador('vdOpaco') +
        '<div class="rub">Color del vidrio</div><div class="ops" data-campo="vdTinte">' +
          ops(VD_TINTES, 'vdTinte', (k, v, sel) => '<div class="op' +
              (sel || (!k && !aspecto.vdTinte) ? ' sel' : '') + '" data-v="' + k + '">' +
              (v[1] ? '<span class="gota" style="background:' + v[1] + '"></span>' : '') +
              esc(v[0]) + '</div>') +
          '<span class="ruedaCaja' + (esLibre(aspecto.vdTinte) ? ' sel' : '') +
            '" title="Cualquier otro color para el vidrio">' +
            '<input type="color" class="rueda" id="aspRuedaVd" value="' +
            (tinteVd() || '#8fb4e0') + '"></span>' +
        '</div>' +
        deslizador('vdBrillo') + deslizador('vdGrano')) +
      seccion('fondo', 'Fondo',
      // ⭐ El fondo: los cinco de siempre y, al lado, la rueda para cualquier otro color.
      // Va última en la fila y no primera a propósito: los cinco están pensados (los tres
      // oscuros y los dos claros son los que se ven bien), y la rueda es "si ninguno te
      // gusta". El color elegido decide solo si la pantalla se da vuelta a tema claro.
        '<div class="ops" data-campo="fondo">' +
          ops(FONDOS, 'fondo', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
          '<span class="ruedaCaja' + (esLibre(aspecto.fondo) ? ' sel' : '') +
            '" title="Cualquier otro color de fondo">' +
            '<input type="color" class="rueda" id="aspRuedaFondo" value="' +
            fondoDe()[1] + '"></span>' +
        '</div>' +
        '<div class="pie"><div class="op" id="aspWin" title="La foto que Windows va ' +
          'cambiando sola en el escritorio">🪟 La de Windows</div>' +
          '<div class="op" id="aspElegir">🖼 Una mía…</div>' +
          (aspecto.img ? '<div class="op" id="aspSacar">Sacarla</div>' : '') + '</div>' +
        // Cuánto se ve la foto: solo tiene sentido si hay una puesta.
        (aspecto.img
          ? '<div class="rub">Cuánto se ve la foto</div><div class="ops" data-campo="velo">' +
              ops(VELOS, 'velo', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
                  '" data-v="' + k + '">' + esc(v[0]) + '</div>') + '</div>'
          : '')) +
      '<div class="fabrica"><div class="op" id="aspFabrica">↺ Volver a lo de fábrica</div></div>';
    // ⚠ El `if` no es defensivo de más: la fila de estilos usa la misma pinta que las
    // demás (`.ops`) pero NO tiene `data-campo`, porque un estilo no es un valor que se
    // guarda en un campo — pisa media docena. Sin esto, tocar un estilo escribiría en
    // `aspecto[undefined]`.
    panel.querySelectorAll('.ops[data-campo]').forEach(caja => {
      caja.querySelectorAll('.op').forEach(op => {
        op.onclick = () => { aspecto[caja.dataset.campo] = op.dataset.v;
                             aplicar(); guardar(); pintarPanel(); };
      });
    });
    // ⭐ "Quedan fijos" necesita su propio clic, encima del genérico de arriba: prenderlo
    // quiere decir "conservá el tamaño que tienen AHORA", así que vuelve a clavar la
    // referencia. Sin esto, una referencia vieja (guardada otro día, con otro zoom) haría
    // saltar los botones de tamaño justo en el momento de prenderlo.
    const opFijo = panel.querySelector('.ops[data-campo="botonesZoom"] .op[data-v="fijo"]');
    if (opFijo) opFijo.onclick = () => {
      clavarZoom();
      aspecto.botonesZoom = 'fijo';
      aplicar(); guardar(); pintarPanel();
    };
    // Y el "usar el tamaño de ahora": re-clava sin tener que apagar y prender.
    const clavar = panel.querySelector('#aspClavarZoom');
    if (clavar) clavar.onclick = () => { clavarZoom(); aplicar(); pintarPanel(); };
    // Los desplegables de tipografía. ⚠ En el de la tipografía del texto, la opción vacía
    // es un cartel ("Otra tipografía…") y no un valor: elegirla vuelve a Segoe, porque una
    // pantalla sin tipografía no existe. En el de los títulos, vacío SÍ es un valor y
    // quiere decir "la misma del texto".
    panel.querySelectorAll('select[data-fuente]').forEach(s => {
      s.onchange = () => {
        const campo = s.dataset.fuente;
        aspecto[campo] = s.value || (campo === 'tipo' ? 'segoe' : '');
        aplicar(); guardar(); pintarPanel();
      };
    });
    // Los estilos y el "volver a lo mío".
    panel.querySelectorAll('.esti').forEach(op => {
      op.onclick = () => {
        if (op.dataset.esti) ponerEstilo(op.dataset.esti); else sacarEstilo();
        aplicar(); guardar(); pintarPanel();
      };
    });
    const volver = panel.querySelector('#aspVolver');
    if (volver) volver.onclick = () => { volverALoTuyo(); aplicar(); guardar(); pintarPanel(); };
    // Qué secciones quedan abiertas, para que el próximo repintado no las cierre.
    panel.querySelectorAll('details[data-sec]').forEach(d => {
      d.addEventListener('toggle', () => {
        if (d.open) abiertas.add(d.dataset.sec); else abiertas.delete(d.dataset.sec);
        recordarAbiertas();
      });
    });
    // Las ruedas de cada tarjeta del panel. Van aparte de las otras porque el color no vive
    // suelto en `aspecto` sino adentro de `aspecto.bloques`.
    panel.querySelectorAll('.rueda[data-bloq-rueda]').forEach(rd => {
      const k = rd.dataset.bloqRueda;
      const poner = v => {
        aspecto.bloques = Object.assign({}, aspecto.bloques, {[k]: v});
      };
      rd.oninput  = () => { poner(rd.value); aplicar(); };
      rd.onchange = () => { poner(rd.value); aplicar(); guardar(); pintarPanel(); };
    });
    panel.querySelectorAll('.parte[data-bloq] .quitar').forEach(q => {
      q.onclick = () => {
        const b = Object.assign({}, aspecto.bloques);
        delete b[q.parentElement.dataset.bloq];
        aspecto.bloques = b;
        aplicar(); guardar(); pintarPanel();
      };
    });
    // ⚠ Mientras arrastrás la rueda se aplica en vivo pero NO se guarda: cada movimiento
    // dispara un `input` y serían cien avisos al servidor por un solo color. Se guarda al
    // soltar (`change`). Y no se vuelve a dibujar el panel en el medio, o el navegador
    // cerraría su propio selector de colores.
    const rueda = panel.querySelector('#aspRueda');
    rueda.oninput  = () => { aspecto.color = rueda.value; aplicar(); };
    rueda.onchange = () => { aspecto.color = rueda.value; aplicar(); guardar(); pintarPanel(); };
    // La rueda del rastro, con la misma regla: en vivo mientras la movés, guardada al soltar.
    const ruedaR = panel.querySelector('#aspRuedaRastro');
    ruedaR.oninput  = () => { aspecto.rastro = ruedaR.value; aplicar(); };
    ruedaR.onchange = () => { aspecto.rastro = ruedaR.value; aplicar(); guardar(); pintarPanel(); };
    // ⭐ Los deslizadores del vidrio: misma regla que las ruedas — en vivo mientras lo
    // arrastrás, guardado al soltar, y sin redibujar el panel en el medio (perdería la
    // barra que tenés agarrada). Solo se actualiza el numerito de al lado.
    panel.querySelectorAll('.desliz[data-desliz]').forEach(fila => {
      const k = fila.dataset.desliz, d = DESLIZ[k];
      const barra = fila.querySelector('input'), val = fila.querySelector('.val');
      barra.oninput = () => {
        aspecto[k] = d.escribir(+barra.value);
        val.textContent = d.texto(+barra.value);
        aplicar();
      };
      barra.onchange = () => { aspecto[k] = d.escribir(+barra.value);
                               aplicar(); guardar(); pintarPanel(); };
      const q = fila.querySelector('.quitar');
      if (q) q.onclick = () => { aspecto[k] = fabricaDe(k); aplicar(); guardar(); pintarPanel(); };
    });
    const ruedaVd = panel.querySelector('#aspRuedaVd');
    ruedaVd.oninput  = () => { aspecto.vdTinte = ruedaVd.value; aplicar(); };
    ruedaVd.onchange = () => { aspecto.vdTinte = ruedaVd.value; aplicar(); guardar(); pintarPanel(); };
    // La del fondo, igual. ⚠ Esta es la única que puede dar vuelta la pantalla entera
    // mientras la arrastrás (al cruzar el corte de luminosidad se prende el tema claro):
    // se ve raro por un segundo y es correcto — soltás y queda.
    const ruedaF = panel.querySelector('#aspRuedaFondo');
    ruedaF.oninput  = () => { aspecto.fondo = ruedaF.value; aplicar(); };
    ruedaF.onchange = () => { aspecto.fondo = ruedaF.value; aplicar(); guardar(); pintarPanel(); };
    // Las ruedas de cada parte, con la misma regla que las otras dos: en vivo mientras la
    // movés, guardada al soltar. Y el ↺ le saca el color a ESA parte, no a todas.
    panel.querySelectorAll('.rueda[data-rueda]').forEach(rd => {
      const k = rd.dataset.rueda;
      rd.oninput  = () => { aspecto[k] = rd.value; aplicar(); };
      rd.onchange = () => { aspecto[k] = rd.value; aplicar(); guardar(); pintarPanel(); };
    });
    // ⚠ `[data-parte]` en el selector, y no `.parte .quitar` a secas: las filas de las
    // tarjetas usan la misma pinta pero guardan adentro de `aspecto.bloques`, y este
    // `onclick` (que se asigna, no se suma) le pisaba el suyo y escribía en
    // `aspecto[undefined]`.
    panel.querySelectorAll('.parte[data-parte] .quitar').forEach(q => {
      q.onclick = () => { aspecto[q.parentElement.dataset.parte] = '';
                          aplicar(); guardar(); pintarPanel(); };
    });
    panel.querySelector('#aspWin').onclick = () => {
      aspecto.img = '/fondo/windows'; aplicar(); guardar(); pintarPanel();
    };
    panel.querySelector('#aspElegir').onclick = () => document.getElementById('aspectoFile').click();
    const sacar = panel.querySelector('#aspSacar');
    if (sacar) sacar.onclick = () => { aspecto.img = ''; aplicar(); guardar(); pintarPanel(); };
    // Con nueve tipografías, ocho colores y la rueda, es fácil llegar a algo ilegible y
    // no acordarse de dónde se salió. Esto devuelve TODO a lo de fábrica de una.
    panel.querySelector('#aspFabrica').onclick = () => {
      // Lo de fábrica es Vidrio, lo mismo con lo que arranca un panel recién bajado.
      aspecto = Object.assign({}, FABRICA); aplicar(); guardar(); pintarPanel();
    };
  }

  // La imagen se achica ACÁ antes de guardarla: una foto del celular pesa 4 MB y el
  // almacenamiento del navegador aguanta ~5 en total. A 1600 px queda en unos cientos
  // de kB y en pantalla no se nota (mismo truco que usa la app para las fotos del chat).
  async function elegirImagen(input){
    const f = input.files[0];
    input.value = '';
    if (!f) return;
    try {
      const bm = await createImageBitmap(f);
      const escala = Math.min(1, 1600 / Math.max(bm.width, bm.height));
      const lienzo = document.createElement('canvas');
      lienzo.width = Math.round(bm.width * escala);
      lienzo.height = Math.round(bm.height * escala);
      lienzo.getContext('2d').drawImage(bm, 0, 0, lienzo.width, lienzo.height);
      aspecto.img = lienzo.toDataURL('image/jpeg', .72);
      aplicar(); guardar(); pintarPanel();
    } catch (err) {
      avisar('No pude usar esa imagen: ' + err);
    }
  }

  function armar(){
    const est = document.createElement('style');
    est.id = 'css-aspecto';
    est.textContent = CSS;
    document.head.appendChild(est);
    aplicar();      // ⚠ de nuevo: recién ahora existe la hoja de arriba (ver tintasDeLaPagina)

    // El botón va adentro del menú de pantallas si esta página lo tiene; si no, donde
    // la página diga (`#aspectoAqui`). Sin ninguno de los dos no se dibuja: el tema
    // igual se aplica (la pizarra adentro del iframe del celular es ese caso).
    const donde = document.getElementById('aspectoAqui') ||
                  document.getElementById('menuPantallas');
    if (!donde) return;
    const btn = document.createElement('button');
    btn.id = 'aspectoBtn';
    btn.title = 'Fondo, tipografía y color';
    btn.textContent = '🎨';
    donde.insertBefore(btn, donde.firstChild);

    const panel = document.createElement('div');
    panel.id = 'aspectoPanel';
    document.body.appendChild(panel);
    const file = document.createElement('input');
    file.type = 'file'; file.accept = 'image/*'; file.id = 'aspectoFile'; file.hidden = true;
    document.body.appendChild(file);
    file.addEventListener('change', () => elegirImagen(file));

    btn.onclick = e => {
      e.stopPropagation();
      const abierto = panel.classList.toggle('abierto');
      if (!abierto) return;
      pintarPanel();
      // Debajo del botón, pero sin salirse por la derecha en pantallas angostas.
      // ⚠ El ancho se MIDE, no se da por sabido: desde que el panel sigue a `--ui`
      // (2026-09-12) ya no son 290 px fijos, y con los botones en Grandes la cuenta vieja
      // lo dejaba salirse por la derecha.
      const c = btn.getBoundingClientRect();
      const ancho = panel.offsetWidth || 290;
      panel.style.top = Math.round(c.bottom + 8) + 'px';
      panel.style.left = Math.round(
        Math.max(8, Math.min(c.left, window.innerWidth - ancho - 8))) + 'px';
    };
    // ⚠ El clic de adentro se corta EN EL PANEL: al elegir una opción el panel se
    // vuelve a dibujar, así que para cuando el clic llega al documento el elemento que
    // tocaste ya no existe y "no está adentro de nada" — se cerraba solo en cada
    // elección (2026-08-17).
    panel.addEventListener('click', e => e.stopPropagation());
    document.addEventListener('click', () => panel.classList.remove('abierto'));
  }

  // Lo del servidor manda sobre la copia local: es lo que hace que la elección de la
  // compu valga en el teléfono. Se aplica primero lo local para que no haya un
  // parpadeo con los colores de fábrica mientras contesta.
  aplicar();
  fetch('/aspecto').then(r => r.json()).then(d => {
    if (d && typeof d === 'object' && d.tipo) {
      aspecto = Object.assign({}, BASE, d);
      try { localStorage.setItem('aspecto', JSON.stringify(aspecto)); } catch (e) {}
      aplicar();
      pintarPanel();
    }
  }).catch(() => {});

  // ⭐ Con "quedan fijos", cada vez que cambia el zoom hay que rehacer la cuenta. El
  // navegador lo avisa con `resize`, porque ampliar la página cambia su ancho en píxeles
  // CSS. ⚠ Se compara el devicePixelRatio y no se reaplica en cada `resize`: agrandar la
  // ventana con el mouse dispara decenas por segundo y ahí no hay nada que recalcular.
  let zoomVisto = zoomAhora();
  window.addEventListener('resize', () => {
    if (Math.abs(zoomAhora() - zoomVisto) < .001) return;
    zoomVisto = zoomAhora();
    if (aspecto.botonesZoom === 'fijo') { aplicar(); pintarPanel(); }
  });

  // ⭐ Que el fondo siga al escritorio: Windows rota la foto del "Windows spotlight"
  // cada tanto, y preguntamos la FIRMA (unos bytes) en vez de bajar la foto (2 MB).
  // Solo cuando cambia se vuelve a pedir la imagen. Cada 5 minutos alcanza: la rotación
  // de Windows es de horas (pedido de Martín, 2026-08-18).
  function mirarFondo(){
    if (aspecto.img !== FOTO_WINDOWS && !(deVidrio() && !aspecto.img)) return;
    fetch('/fondo/windows/version').then(r => r.json()).then(d => {
      if (d && d.v && d.v !== versionFondo){ versionFondo = d.v; aplicar(); }
    }).catch(() => {});
  }
  mirarFondo();
  setInterval(mirarFondo, 5 * 60 * 1000);
  // Y al volver a la pantalla, por si estuvo horas guardada en el bolsillo.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) mirarFondo(); });

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', armar);
  else armar();
})();
