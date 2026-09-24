/* El menu de pantallas, uno solo para las cinco.
 *
 * Antes cada pantalla tenia un "← volver al panel" y nada mas: para ir de la Pizarra
 * al Estudio habia que pasar por el panel. Pedido de Martin (2026-08-17): "me gustaria
 * en todas las pestañas poder entrar a todas las pestañas".
 *
 * Vive como archivo aparte —igual que marcado.js— porque lo comparten paginas que
 * estan adentro de panel.py (panel, pizarra) y paginas que son archivos
 * sueltos (sesiones, estudio). Agregar una pantalla nueva es agregar un renglon ACA,
 * y aparece en todas.
 *
 * Como se usa: un <nav id="menuPantallas"></nav> donde se lo quiera, y este script.
 * Trae sus propios estilos, asi que se ve igual en todas y no depende del CSS de cada
 * pagina (que son varias hojas distintas escritas en momentos distintos).
 *
 * ⭐⭐ SE ACHICA SOLO (2026-08-18), en tres pasos, segun el lugar que tenga:
 *    completo  ->  🏠 Panel  🧠 Sesiones  🧷 Pizarra …      (~600 px)
 *    compacto  ->  🏠 🧠 🧷 🎧 🔔                             (~210 px)
 *    mini      ->  un solo boton con la pantalla donde estas, que despliega el resto
 *
 * ⚠ HISTORIA, para no repetir el camino: esto nacio porque en `/sesiones` el menu
 * compartia renglon con las pestañas de las conversaciones y se las comia. Ese mismo
 * dia Martin decidio la solucion de fondo — *"no me gusta que las sesiones ocupen el
 * mismo lugar que las pestañas, se me hace incomodo trabajar asi; que las pestañas esten
 * arriba"* — y ahora el menu tiene SIEMPRE su propio renglon. Los tres pasos quedan
 * igual, pero ahora solo se llega a ellos por VENTANA ANGOSTA, no por un vecino.
 * El mecanismo del vecino (`data-menu-rival`) sigue andando por si alguna pantalla vuelve
 * a compartir renglon; hoy no lo usa ninguna.
 */
(function () {
  const PANTALLAS = [
    { href: '/',         ic: '🏠', nom: 'Panel',    tit: 'El panel del Servidor IA: servicios, chat y estado' },
    { href: '/sesiones', ic: '🧠', nom: 'Sesiones', tit: 'Las sesiones de Claude Code, cada una en su pestaña' },
    { href: '/pizarra',  ic: '🧷', nom: 'Pizarra',  tit: 'Pizarron interactivo: notas y pines que Laura deja por voz' },
    { href: '/estudio',  ic: '🎧', nom: 'Estudio',  tit: 'Estudio de audio: pegar varios audios y que salga uno solo' },
    { href: '/avisos',   ic: '🔔', nom: 'Avisos',   tit: 'Los Recordatorios de tu iPhone, y lo que anotes desde la compu' },
  ];

  const CSS = `
/* ⭐ Sigue a --ui, el tamaño de los controles del 🎨 (2026-09-12): si las pestañas de una
   pantalla achican y este menú no, queda la mitad de la barra grande y la otra chica —
   se vio en la captura de la prueba. Sin elegir nada vale 1 y queda igual que siempre.
   ⚠ medir() cachea los tres anchos, así que un cambio de --ui despues de medir deja el
   cache viejo. Hoy no molesta: acomodar() sale sin hacer nada cuando el menú no comparte
   renglón con nadie, y desde 2026-08-18 no lo comparte en ninguna pantalla.
   ⚠⚠ Y nada de acentos invertidos acá adentro: este CSS es un template literal y uno solo
   corta la cadena — el archivo deja de ser JavaScript válido, en silencio. Pasó al escribir
   este mismo comentario. */
.menu-pantallas{display:flex;align-items:center;gap:calc(8px * var(--ui,1));position:relative}
.menu-pantallas .todo{display:flex;align-items:center;gap:calc(8px * var(--ui,1));flex-wrap:wrap}
.menu-pantallas a{display:inline-flex;align-items:center;gap:calc(6px * var(--ui,1));
  padding:calc(3px * var(--ui,1)) calc(11px * var(--ui,1));
  border-radius:999px;font-size:calc(12px * var(--ui,1));line-height:1.5;background:#161b23;
  border:1px solid #262e3a;color:#8b93a1;text-decoration:none;white-space:nowrap;
  cursor:pointer;transition:background .15s,border-color .15s,color .15s}
.menu-pantallas a:hover{background:#1d2530;border-color:#3a4658;color:#e8eaed}
/* La pantalla en la que estas parado se marca y NO se puede clickear: apretarla
   recargaria la misma pagina, que es lo que uno menos quiere de un menu. */
.menu-pantallas a.aca{background:#16263a;border-color:#2c4a6b;color:#cfe6ff;
  cursor:default;pointer-events:none}
/* --- Paso 2: solo los iconos. El nombre queda en el globito del title. --- */
.menu-pantallas.compacto a{padding:calc(4px * var(--ui,1)) calc(8px * var(--ui,1));
  font-size:calc(14px * var(--ui,1))}
.menu-pantallas.compacto a .nom{display:none}
/* --- Paso 3: un solo boton. Muestra DONDE ESTAS, no un ☰ pelado: el menu tiene que
       seguir diciendo en que pantalla estas aunque este guardado. --- */
.menu-pantallas .abrir{display:none;align-items:center;gap:calc(6px * var(--ui,1));
  padding:calc(3px * var(--ui,1)) calc(10px * var(--ui,1));
  border-radius:999px;font-size:calc(12px * var(--ui,1));background:#16263a;border:1px solid #2c4a6b;
  color:#cfe6ff;cursor:pointer;white-space:nowrap;user-select:none}
.menu-pantallas .abrir:hover{background:#1d3049;border-color:#3a6ea8}
.menu-pantallas.mini .abrir{display:inline-flex}
.menu-pantallas.mini .todo{display:none;position:absolute;top:calc(100% + 7px);right:0;
  flex-direction:column;align-items:stretch;background:#151a24;border:1px solid #2a3444;
  border-radius:12px;padding:8px;box-shadow:0 14px 40px rgba(0,0,0,.55);z-index:60}
.menu-pantallas.mini.desplegado .todo{display:flex}
.menu-pantallas.mini .todo a{font-size:calc(13px * var(--ui,1));
  padding:calc(6px * var(--ui,1)) calc(12px * var(--ui,1))}
.menu-pantallas.mini .todo a .nom{display:inline}
`;

  /* La pagina de la que uno viene. Se compara solo el camino, sin barra final:
     "/sesiones/" y "/sesiones" son la misma pantalla. */
  function esAca(href) {
    const hoy = (location.pathname || '/').replace(/\/+$/, '') || '/';
    return hoy === href;
  }

  function dibujar() {
    const caja = document.getElementById('menuPantallas');
    if (!caja) return;                       // la pagina no lo pidio: no molestar
    if (!document.getElementById('cssMenuPantallas')) {
      const s = document.createElement('style');
      s.id = 'cssMenuPantallas';
      s.textContent = CSS;
      document.head.appendChild(s);
    }
    caja.classList.add('menu-pantallas');
    const aca = PANTALLAS.find(p => esAca(p.href)) || PANTALLAS[0];
    caja.innerHTML =
      '<div class="abrir" title="Ir a otra pantalla"><span>' + aca.ic + '</span>' +
        '<span>' + aca.nom + '</span><span style="opacity:.6;font-size:10px">▾</span></div>' +
      '<div class="todo">' + PANTALLAS.map(p =>
        '<a href="' + p.href + '"' + (esAca(p.href) ? ' class="aca"' : '') +
        ' title="' + p.tit + '"><span class="ic">' + p.ic + '</span>' +
        '<span class="nom">' + p.nom + '</span></a>').join('') + '</div>';
    caja.querySelector('.abrir').onclick = e => {
      e.stopPropagation();
      caja.classList.toggle('desplegado');
    };
    acomodar();
  }

  /* ⭐ Cuanto lugar le deja el menu a quien comparte el renglon.

     Se miden UNA vez los tres anchos del menu (completo, compacto y mini) y despues la
     decision es una cuenta, no un tanteo: cuanto le sobra o le falta al vecino, mas lo
     que ocupo yo ahora, menos lo que ocuparia en cada estado. Se elige el estado mas
     grande que entre.

     ⚠⚠ Por que una cuenta y no "probar y deshacer", que es lo primero que uno escribe:
     cambiar la clase cambia el ancho del vecino, el ResizeObserver vuelve a llamar acá,
     y el menu se pasa la vida agrandandose y achicandose a 60 por segundo. La cuenta no
     toca el DOM salvo cuando el estado de verdad cambia. */
  let anchos = null;

  /* ⚠⚠ Se mide SACANDOLO DEL RENGLON (`position:absolute` + `width:max-content`) y no
     donde esta. Quieto en su lugar, `offsetWidth` devuelve lo que OCUPA, no lo que
     NECESITA: en una ventana angosta el menu ya venia envuelto en dos lineas, media 562
     en vez de 700, la cuenta creia que entraba comodo y no se achicaba nunca — se veia
     como una barra de dos pisos con los botones cortados (pizarra a 760 px).
     Y como el resultado se guarda en `anchos` para siempre, una sola medicion mal hecha
     dejaba el menu roto toda la sesion. */
  function medir(caja) {
    const tenia = caja.className;
    const estilo = caja.getAttribute('style') || '';
    caja.style.position = 'absolute';
    caja.style.visibility = 'hidden';
    caja.style.width = 'max-content';
    const base = 'menu-pantallas';
    caja.className = base;               const completo = caja.offsetWidth;
    caja.className = base + ' compacto';  const compacto = caja.offsetWidth;
    caja.className = base + ' mini';      const mini = caja.offsetWidth;
    caja.className = tenia;
    caja.setAttribute('style', estilo);
    return {completo, compacto, mini};
  }

  function acomodar() {
    const caja = document.getElementById('menuPantallas');
    const rival = document.querySelector('[data-menu-rival]');
    // ⭐ Menu solo en su renglon: no se achica nunca. Se probo la cuenta contraria —
    // medir lo que le dejan sus hermanos en la fila— y NO sirve: en varias cabeceras hay
    // hermanos elasticos (`flex:1`) que se llevan todo el ancho sobrante, asi que la
    // cuenta veia cero lugar y guardaba el menu en una pantalla de 1500 px (le paso al
    // Estudio, 2026-08-18). Cuando el menu esta solo, el navegador ya lo acomoda.
    if (!caja || !rival) return;
    if (!anchos || !anchos.completo) anchos = medir(caja);
    const ahora = caja.offsetWidth;
    // Lo que le sobra al vecino (negativo = esta cortado) si el menu no cambiara.
    const sobra = rival.clientWidth - rival.scrollWidth;
    const entra = ancho => sobra + ahora - ancho >= 8;   // 8 px de aire, para no rozar
    // ⭐ PISO: en una pantalla grande el menu no baja de "solo iconos" aunque el vecino
    // siga sin entrar. Las pestañas se pueden correr con la rueda; el menu escondido en
    // un solo boton, no — y la gracia de este menu es llegar a cualquier pantalla de un
    // toque. Al ultimo paso se llega solo cuando la ventana es de verdad angosta.
    const fila = caja.parentElement;
    const angosto = fila && fila.clientWidth < 1100;
    const quiere = entra(anchos.completo) ? ''
                 : (entra(anchos.compacto) || !angosto) ? 'compacto'
                 : 'mini';
    const tiene = caja.classList.contains('mini') ? 'mini'
                : caja.classList.contains('compacto') ? 'compacto' : '';
    if (quiere === tiene) return;             // ⭐ no se toca el DOM al pedo
    caja.classList.remove('compacto', 'mini', 'desplegado');
    if (quiere) caja.classList.add(quiere);
  }

  // Se cierra el desplegable al tocar en cualquier otro lado.
  document.addEventListener('click', () => {
    const caja = document.getElementById('menuPantallas');
    if (caja) caja.classList.remove('desplegado');
  });

  /* Puede cargarse en el <head> (antes de que exista el nav) o al final del body. */
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', dibujar);
  else
    dibujar();

  // ⚠ El vecino cambia de tamaño sin que cambie la ventana: abris una pestaña mas y ya.
  // Por eso se lo vigila con un ResizeObserver y no solo con el `resize` de la ventana.
  window.addEventListener('resize', acomodar);
  if (window.ResizeObserver) {
    const ojo = new ResizeObserver(() => acomodar());
    const mirar = () => {
      const rival = document.querySelector('[data-menu-rival]');
      if (rival) { ojo.observe(rival); return true; }
      return false;
    };
    if (!mirar()) document.addEventListener('DOMContentLoaded', mirar);
  }

  window.menuPantallas = dibujar;            // por si alguna pantalla repinta su barra
  window.menuAcomodar = acomodar;            // y para avisarle que el vecino cambio
})();
