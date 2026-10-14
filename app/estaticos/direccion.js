/* Cada conversación con su propia dirección web ------------------------------------
 *
 * Pedido de Martín (2026-08-18): "quiero que cada conversación tenga su propia dirección
 * web, para poder guardarla en favoritos y tener varias pestañas del navegador, cada una
 * en una conversación distinta. Al abrir una conversación la barra de direcciones tiene
 * que cambiar sola, y al entrar con esa dirección la app tiene que abrirse ya parada en
 * esa conversación."
 *
 * Vive en un archivo compartido (como marcado.js, menu.js y aspecto.js) porque son DOS
 * las pantallas que abren conversaciones — la de la compu y la app del celular — y la
 * dirección tiene que querer decir lo mismo en las dos:
 *
 *     /sesiones?c=<id de la conversación>      una charla abierta
 *     /sesiones                                la bandeja
 *     /sesiones?p=<nombre de la carpeta>       la bandeja de UNA carpeta (2026-10-10:
 *                                              el botón del medio sobre una carpeta)
 *     /movil?c=<id de la conversación>         la misma charla, en el celular
 *     /movil?v=panel|pizarra|hablar|nueva      las pantallas fijas del celular
 *
 * Se usa así:
 *     <script src="/estaticos/direccion.js"></script>
 *     Direccion.leer()                       -> {c: '<id>', v: ''}   (lo que dice la barra)
 *     Direccion.fijar({c: sid}, {titulo: n})  -> la escribe y cambia el título
 *     Direccion.alVolver(estado => …)         -> la flecha ← del navegador
 *
 * ⭐ Cambia también el TÍTULO de la página, y eso NO es un adorno: el navegador guarda el
 * favorito con el título que tenga la página en ese momento, y la pestaña del navegador
 * muestra ese mismo texto. Sin esto, seis pestañas abiertas dicen las seis "Sesiones" y
 * el favorito queda llamándose igual que todos los demás — o sea, ninguna de las dos
 * cosas que se venían a resolver funcionaría.
 *
 * ⚠ En la dirección va SOLO el id de la conversación, nunca la carpeta del disco: la
 * carpeta la resuelve el servidor (`GET /movil/donde`). Una dirección con la ruta
 * adentro es larga, se rompe si el proyecto se mueve, y encima quedaría escrita en los
 * favoritos del navegador.
 */
window.Direccion = (function () {
  const BASE = document.title;

  // Lo que dice la barra de direcciones ahora mismo.
  const leer = () => {
    const p = new URLSearchParams(location.search);
    return {c: (p.get('c') || '').trim(), v: (p.get('v') || '').trim(),
            p: (p.get('p') || '').trim()};
  };

  // La dirección que le correspondería a un estado, respetando cualquier otro
  // parámetro que ya estuviera puesto (no somos los dueños de la barra).
  function armar(estado) {
    const p = new URLSearchParams(location.search);
    p.delete('c'); p.delete('v'); p.delete('p');
    if (estado && estado.c) p.set('c', estado.c);
    else if (estado && estado.v) p.set('v', estado.v);
    else if (estado && estado.p) p.set('p', estado.p);
    const q = p.toString();
    return location.pathname + (q ? '?' + q : '') + location.hash;
  }

  const ahora = () => location.pathname + location.search + location.hash;

  /* Escribir la barra de direcciones y el título.
   *   estado: {c: '<id>'} una conversación, {v: 'panel'} una pantalla fija, {} la bandeja.
   *   opciones.titulo: cómo se llama lo que estás mirando (va adelante del título fijo).
   *   opciones.empujar: false para REEMPLAZAR la entrada del historial en vez de agregar
   *     una nueva. Se usa al arrancar y cuando la dirección se corrige sola (por ejemplo
   *     cuando una charla nueva recién estrenada consigue su id de verdad): si esas
   *     empujaran, la flecha ← te devolvería a una dirección que ya no significa nada.
   */
  function fijar(estado, opciones) {
    const o = opciones || {};
    const t = o.titulo ? (String(o.titulo).slice(0, 70) + ' · ' + BASE) : BASE;
    if (document.title !== t) document.title = t;
    const url = armar(estado);
    if (url === ahora()) return;
    // Empujar (y no reemplazar) es lo que hace que la flecha ← del navegador vuelva a la
    // conversación anterior, como en cualquier página.
    try {
      if (o.empujar === false) history.replaceState({}, '', url);
      else history.pushState({}, '', url);
    } catch (e) { /* si el navegador no deja, la pantalla anda igual */ }
  }

  // La flecha ← y la → del navegador. Llega el estado nuevo ya leído.
  const alVolver = fn => addEventListener('popstate', () => fn(leer()));

  // ¿En qué carpeta del disco vive esta conversación? Es lo que hace falta para poder
  // entrar con una dirección pelada (un favorito de la semana pasada, otra computadora,
  // una pestaña recién abierta): de la dirección viene solo el id.
  async function donde(sid) {
    if (!sid) return null;
    try {
      const r = await (await fetch('/movil/donde?sid=' + encodeURIComponent(sid))).json();
      return r && r.ok ? r : null;
    } catch (e) { return null; }
  }

  /* El ícono de la pestaña del navegador (2026-10-10). Pedido de Martín: "me gustaría que
   * cada ícono de carpeta de sesión sea del proyecto". Con las pestañas de Chrome en
   * columna se ve SOLO el ícono, y sin uno propio eran todas el mismo globito: no había
   * forma de saber cuál era cuál. Se dibuja el emoji en un SVG, que Chrome acepta como ícono.
   */
  let iconoPuesto = null;
  function icono(emoji) {
    const e = String(emoji || '').trim();
    if (e === iconoPuesto) return;
    iconoPuesto = e;
    let l = document.querySelector('link[rel="icon"]');
    if (!e) { if (l) l.remove(); return; }
    if (!l) { l = document.createElement('link'); l.rel = 'icon'; document.head.appendChild(l); }
    l.type = 'image/svg+xml';
    l.href = 'data:image/svg+xml,' + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
      '<text x="50" y="50" font-size="86" text-anchor="middle" dominant-baseline="central">' +
      e.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</text></svg>');
  }

  return {leer, fijar, alVolver, donde, icono};
})();
