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
  const LIMPIO = {burbujaVos: '', burbujaIa: '', ok: '', mal: '', aviso: '', barra: '',
                  pizBarra: '', rastro: 'tema', bloques: {}, tintaLetras: '',
                  tintaCajas: '', sombra: 'normal', vidrio: 'normal', movi: 'normal',
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
  };

  const BASE = {tipo: 'segoe', color: 'celeste', fondo: 'azulado', img: '',
                letra: 'normal', velo: 'media', rastro: 'tema',
                // ⭐ El tamaño de los botones y qué hacen con el zoom (2026-09-12).
                // ⚠ A propósito NO están en `LIMPIO`: un estilo pinta, no le cambia a
                // nadie el tamaño de los controles — misma razón que el tamaño del texto.
                botones: 'normal', botonesZoom: 'crece',
                burbujaVos: '', burbujaIa: '', ok: '', mal: '', aviso: '',
                barra: '', pizBarra: '',
                sombra: 'normal', vidrio: 'normal', movi: 'normal',
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

  let aspecto = Object.assign({}, BASE, leerLocal());

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
    // La de la barra de abajo del celular, que cae para ARRIBA: mismo peldaño grande
    // con el signo dado vuelta.
    r.setProperty('--sombra-arriba', k <= 0 ? 'none' : '0 -' + som(18, 45, .5));
    // ⭐ El vidrio: cuánto se ve lo de atrás a través de las barras y los menús. Las
    // pantallas ya desenfocaban un poco; ahora ese desenfoque se multiplica por acá, así
    // que `normal` deja los mismos píxeles de siempre y `Opaco` lo apaga del todo.
    const v = (VIDRIOS[aspecto.vidrio] || VIDRIOS.normal)[1];
    r.setProperty('--vidrio', v.toFixed(2));
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
    // El velo oscuro encima de la foto es lo que deja que el texto se siga leyendo.
    // A la foto de Windows se le pega la firma de la que está puesta AHORA: así el
    // navegador la vuelve a pedir cuando Windows la cambia, y no antes.
    const url = aspecto.img === FOTO_WINDOWS && versionFondo
      ? FOTO_WINDOWS + '?v=' + encodeURIComponent(versionFondo) : aspecto.img;
    const velo = (VELOS[aspecto.velo] || VELOS.media)[1];
    // ⚠ Con el tema claro el velo va BLANCO: uno negro apagaría la foto y encima dejaría
    // el texto —que ahora es oscuro— sobre un fondo oscuro, o sea ilegible.
    const tela = claro ? '250,250,252' : '6,8,12';
    r.setProperty('--fondo-img', url
      ? 'linear-gradient(rgba(' + tela + ',' + velo + '),rgba(' + tela + ',' + velo +
        ')),url("' + url + '")'
      : 'none');
    document.documentElement.classList.toggle('con-foto', !!aspecto.img);
  }

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
                     || !('botones' in guardado);
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
    (aspecto.botones && aspecto.botones !== 'normal') || aspecto.botonesZoom === 'fijo';

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
        '<div class="rub">Vidrio</div><div class="ops" data-campo="vidrio">' +
          ops(VIDRIOS, 'vidrio', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>' +
        '<div class="rub">Movimiento</div><div class="ops" data-campo="movi">' +
          ops(MOVIS, 'movi', (k, v, sel) => '<div class="op' + (sel ? ' sel' : '') +
              '" data-v="' + k + '">' + esc(v[0]) + '</div>') +
        '</div>') +
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
      aspecto = Object.assign({}, BASE); aplicar(); guardar(); pintarPanel();
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
    if (aspecto.img !== FOTO_WINDOWS) return;
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
