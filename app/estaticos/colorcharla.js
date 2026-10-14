// El color propio de cada charla (2026-10-10, pedido de Martín), y de cada CARPETA.
//
// Cada conversación puede tener hasta tres colores: tu burbuja, la burbuja de la sesión y
// un tinte del fondo. Lo mismo una carpeta entera, y entonces lo heredan todas sus charlas
// (también las que nazcan después). El orden manda así, de más fuerte a más débil:
//     lo de la charla  >  lo de su carpeta  >  el aspecto general (🎨)
// y se resuelve color por color: una charla puede tener su burbuja propia y seguir
// tomando el tinte de la carpeta.
// Lo comparten la página de sesiones de la compu y el celular, y se guarda en el SERVIDOR
// (`/charlas/colores`), así lo elegido en una pantalla se ve igual en la otra. Las
// carpetas van en el mismo archivo con la llave `carpeta:<ruta>` (ver `clave()`).
//
// ⭐ Cómo pinta sin tocar el resto de la pantalla: pone las MISMAS variables de las
// burbujas (`--burbuja-vos`, `--burbuja-ia`…) pero sobre el contenedor del chat abierto y
// no sobre la página entera. Las reglas de las burbujas ya leen esas variables, así que
// adentro del chat gana el color de la charla y afuera (lista, menús) sigue el general.
// ⚠ El tinte va como una sombra interior y no como `background`: el fondo puede ser la
// foto de Windows, y pisarlo con un color la taparía. La sombra se apoya encima, translúcida.
// ⚠ Las cuentas (mezclar con el fondo, qué letra se lee) las hace aspecto.js con
// `aspectoBurbujas()`: si se copiaran acá, el tema claro y el oscuro se desafinarían.
(function () {
  if (window.ColorCharla) return;
  let colores = {};          // llave (sid o `carpeta:<ruta>`) -> {vos, ia, tinte}
  let cargado = null;        // la promesa de la primera carga
  let pintado = null;        // [elemento, sid, cwd] de lo último que se pintó, para repintar
  const VARS = ['--burbuja-vos', '--burbuja-vos-txt', '--burbuja-ia', '--burbuja-ia-borde'];
  const CAMPOS = ['vos', 'ia', 'tinte'];
  const esHex = c => typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c);
  const ALFA_TINTE = .14;

  // ⭐ La llave de una carpeta es su RUTA y no su nombre: las dos pantallas tienen la ruta
  // de la charla abierta a mano, y el nombre que se ve puede ser un apodo. Se normaliza
  // porque Windows escribe la misma carpeta con barras y mayúsculas distintas según quién.
  const clave = cwd => cwd
    ? 'carpeta:' + String(cwd).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase() : '';
  const nombreCarpeta = cwd => String(cwd || '').replace(/[\\\/]+$/, '').split(/[\\\/]/).pop();

  function cargar() {
    cargado = fetch('/charlas/colores').then(r => r.json()).then(d => {
      colores = (d && d.colores) || {};
      repintar();
    }).catch(() => {});
    return cargado;
  }

  const de = llave => (llave && colores[llave]) || {};
  // Lo que se ve en una charla: color por color, lo suyo y si no lo de su carpeta.
  const efectivos = (sid, cwd) => Object.assign({}, de(clave(cwd)), sid ? de(sid) : {});

  function aplicar(el, sid, cwd) {
    if (!el) return;
    pintado = [el, sid, cwd];
    const c = efectivos(sid, cwd);
    const b = window.aspectoBurbujas ? window.aspectoBurbujas(c.vos, c.ia) : {};
    const poner = (v, valor) => valor ? el.style.setProperty(v, valor) : el.style.removeProperty(v);
    // ⚠ Dos juegos con los mismos valores: la compu pinta sus burbujas con `--burbuja-*`
    // (las del tema), pero el celular las tiene FIJAS estilo WhatsApp y solo cede cuando
    // la charla trae `--charla-*` (ver `.vos` y `.claude` en MOVIL_HTML). Si se pisara el
    // general ahí, el verde de WhatsApp desaparecería también en lo no elegido.
    VARS.forEach((v, i) => {
      const valor = [b.vos, b.vosTxt, b.ia, b.iaBorde][i];
      poner(v, valor);
      poner(v.replace('--burbuja', '--charla'), valor);
    });
    el.classList.toggle('con-color-ia', !!b.iaBorde);
    if (esHex(c.tinte)) {
      const rgb = [1, 3, 5].map(i => parseInt(c.tinte.substr(i, 2), 16)).join(',');
      el.style.boxShadow = 'inset 0 0 0 100vmax rgba(' + rgb + ',' + ALFA_TINTE + ')';
    } else {
      el.style.removeProperty('box-shadow');
    }
    el.classList.toggle('con-color-charla', !!(c.vos || c.ia || c.tinte));
    soloFoto = null;
    ponerFoto(c.foto);
  }
  const repintar = () => {
    if (pintado) aplicar(pintado[0], pintado[1], pintado[2]);
    else if (soloFoto !== null) ponerFoto(de(clave(soloFoto)).foto);
  };

  // ⭐ La foto propia va en el fondo de la PÁGINA, no del contenedor: es la misma capa de la
  // foto general (aspecto.js), así hereda su velo y la transparencia de los paneles. Solo
  // se aceptan direcciones hechas por el panel: el valor termina adentro de un `url()`.
  let soloFoto = null;       // la carpeta cuya foto se muestra sin charla abierta
  const fotoOk = f => typeof f === 'string' && /^\/charlas\/fondo\/[0-9a-f]+\.(jpg|png|webp)$/.test(f);
  const ponerFoto = f => { if (window.aspectoFoto) window.aspectoFoto(fotoOk(f) ? f : ''); };

  // Volver el contenedor a los colores generales (cuando no hay charla abierta). Con `cwd`,
  // la página queda con la foto de esa carpeta: es la bandeja de una carpeta sola.
  function limpiar(el, cwd) {
    if (el) {
      VARS.forEach(v => {
        el.style.removeProperty(v);
        el.style.removeProperty(v.replace('--burbuja', '--charla'));
      });
      el.style.removeProperty('box-shadow');
      el.classList.remove('con-color-charla', 'con-color-ia');
      if (pintado && pintado[0] === el) pintado = null;
    }
    soloFoto = cwd || null;
    ponerFoto(cwd ? de(clave(cwd)).foto : '');
  }

  function mandar(cuerpo) {
    return fetch('/charlas/color', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                   body: JSON.stringify(cuerpo)}).catch(() => {});
  }

  // Cambiar un color de una charla o de una carpeta (`llave`). `guardar=false` es la vista
  // previa mientras se arrastra la rueda: se ve al instante y recién al soltar viaja.
  function poner(llave, campo, valor, guardar) {
    const actual = Object.assign({}, de(llave));
    if (valor) actual[campo] = valor; else delete actual[campo];
    if (Object.keys(actual).length) colores[llave] = actual; else delete colores[llave];
    repintar();
    if (guardar === false) return Promise.resolve();
    const cuerpo = {sid: llave};
    cuerpo[campo] = valor || '';
    return mandar(cuerpo);
  }

  function volverTodo(llave) {
    delete colores[llave];
    repintar();
    return mandar({sid: llave, vos: '', ia: '', tinte: '', foto: ''});
  }

  // Elegir la foto: se achica en el navegador igual que la general de aspecto.js (1600 px
  // de lado, JPEG) y recién ahí viaja. Devuelve un texto de error, o '' si salió bien.
  async function subirFoto(llave, archivo) {
    try {
      const bm = await createImageBitmap(archivo);
      const escala = Math.min(1, 1600 / Math.max(bm.width, bm.height));
      const lienzo = document.createElement('canvas');
      lienzo.width = Math.round(bm.width * escala);
      lienzo.height = Math.round(bm.height * escala);
      lienzo.getContext('2d').drawImage(bm, 0, 0, lienzo.width, lienzo.height);
      const r = await fetch('/charlas/foto', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sid: llave, img: lienzo.toDataURL('image/jpeg', .8)})});
      const j = r.ok ? await r.json().catch(() => ({})) : {};
      if (!j.ok) return j.error || (r.status === 404 ? '¿el panel viejo? reinicialo' : 'no se pudo');
      colores[llave] = j.colores;
      repintar();
      return '';
    } catch (e) {
      return 'no pude usar esa imagen';
    }
  }

  // El color que hay que mostrar en la rueda cuando no hay nada elegido: el general de
  // ahora, pasado a '#rrggbb' (la rueda no entiende `rgb(…)`).
  function aHex(css) {
    const m = String(css || '').match(/(\d+)\D+(\d+)\D+(\d+)/);
    if (!m) return '#4a90d9';
    return '#' + [m[1], m[2], m[3]].map(n => (+n).toString(16).padStart(2, '0')).join('');
  }
  function general(variable) {
    return aHex(getComputedStyle(document.documentElement).getPropertyValue(variable));
  }

  // --- El cuadrito para elegir -------------------------------------------------------
  const CSS = `
  .cc-cuadro{position:fixed;z-index:9999;width:min(300px,calc(100vw - 20px));
    background:var(--fondo2,#151a24);color:var(--cffffff,#e8eaf0);border:1px solid var(--borde-fuerte,#2c3445);
    border-radius:12px;padding:12px 12px 10px;box-shadow:0 10px 30px rgba(0,0,0,.45);font-size:14px}
  .cc-cuadro h4{margin:0 0 8px;font-size:14px;font-weight:600}
  .cc-ambito{display:flex;gap:4px;margin:0 0 10px;padding:3px;border-radius:9px;
    border:1px solid var(--borde,#2c3445)}
  .cc-ambito button{flex:1;min-width:0;height:30px;border:0;border-radius:7px;background:transparent;
    color:inherit;cursor:pointer;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cc-ambito button.sel{background:var(--acento-bg,#1d2b44);color:var(--acento,#8ecbff);font-weight:600}
  .cc-fila{display:flex;align-items:center;gap:8px;margin:6px 0}
  .cc-fila span{flex:1}
  .cc-fila small{opacity:.55;font-size:12px}
  .cc-fila input[type=color]{width:42px;height:30px;padding:0;border:1px solid var(--borde,#2c3445);
    border-radius:6px;background:none;cursor:pointer}
  .cc-fila .cc-elegir{height:30px;padding:0 10px;border-radius:6px;border:1px solid var(--borde,#2c3445);
    background:transparent;color:inherit;cursor:pointer;font-size:13px}
  .cc-fila .cc-x:disabled{opacity:.35;cursor:default}
  .cc-fila .cc-x{width:30px;height:30px;border-radius:6px;border:1px solid var(--borde,#2c3445);
    background:transparent;color:inherit;cursor:pointer;font-size:15px;line-height:1}
  .cc-pie{display:flex;justify-content:space-between;gap:8px;margin-top:10px}
  .cc-pie button{flex:1;height:32px;border-radius:8px;border:1px solid var(--borde,#2c3445);
    background:transparent;color:inherit;cursor:pointer;font-size:13px}`;
  function estilos() {
    if (document.getElementById('cc-estilos')) return;
    const s = document.createElement('style');
    s.id = 'cc-estilos'; s.textContent = CSS;
    document.head.appendChild(s);
  }

  let abierto = null;
  function cerrar() {
    if (abierto) { abierto.remove(); abierto = null; }
    document.removeEventListener('pointerdown', fuera, true);
  }
  function fuera(e) { if (abierto && !abierto.contains(e.target)) cerrar(); }

  const FILAS = [['vos', 'Tu burbuja', '--burbuja-vos'],
                 ['ia', 'Burbuja de la sesión', '--burbuja-ia-borde'],
                 ['tinte', 'Tinte del fondo', '--acento']];
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

  // `cwd` es la carpeta de la charla. Con las dos cosas, arriba se elige si lo que tocás
  // vale para ESTA charla o para TODA la carpeta. Una charla sin estrenar (`nueva-…`)
  // todavía no tiene id donde guardar: ahí solo se puede elegir lo de la carpeta.
  function editor(sid, ancla, cwd) {
    cerrar();
    const charlaOk = !!sid && !/^nueva-/.test(sid);
    const carpeta = clave(cwd);
    if (!charlaOk && !carpeta) return;
    estilos();
    let ambito = charlaOk ? 'charla' : 'carpeta';
    const llave = () => ambito === 'charla' ? sid : carpeta;
    const d = document.createElement('div');
    d.className = 'cc-cuadro';
    d.innerHTML = '<h4>Colores</h4>' +
      (charlaOk && carpeta
        ? '<div class="cc-ambito"><button type="button" data-a="charla">Esta charla</button>' +
          '<button type="button" data-a="carpeta" title="Lo heredan todas las charlas de ' +
          esc(nombreCarpeta(cwd)) + ', también las nuevas">Toda la carpeta</button></div>'
        : '') +
      FILAS.map(([k, t]) =>
        '<div class="cc-fila" data-k="' + k + '"><span>' + t + ' <small></small></span>' +
        '<input type="color" title="Elegir el color">' +
        '<button class="cc-x" type="button">×</button></div>').join('') +
      '<div class="cc-fila" data-k="foto"><span>Foto de fondo <small></small></span>' +
      '<button class="cc-elegir" type="button" title="Elegir una foto de la compu">Elegir…</button>' +
      '<button class="cc-x" type="button">×</button>' +
      '<input type="file" accept="image/*" hidden></div>' +
      '<div class="cc-pie"><button type="button" class="cc-todo"></button>' +
      '<button type="button" class="cc-listo">Listo</button></div>';
    const refrescar = () => {
      const enCarpeta = ambito === 'carpeta';
      d.querySelector('h4').textContent = enCarpeta
        ? 'Colores y foto de la carpeta ' + nombreCarpeta(cwd) : 'Colores y foto de esta charla';
      d.querySelectorAll('.cc-ambito button').forEach(b =>
        b.classList.toggle('sel', b.dataset.a === ambito));
      const heredados = enCarpeta ? {} : de(carpeta);
      FILAS.forEach(([k, , v]) => {
        const fila = d.querySelector('[data-k="' + k + '"]');
        const propio = de(llave())[k];
        // De dónde sale el color que se ve si no elegís nada acá.
        fila.querySelector('small').textContent = propio ? ''
          : (heredados[k] ? '· de la carpeta' : '· general');
        fila.querySelector('input').value = propio || heredados[k] || general(v);
        fila.querySelector('.cc-x').title = enCarpeta || !heredados[k]
          ? 'Volver al color general' : 'Volver al color de la carpeta';
      });
      const ff = d.querySelector('[data-k="foto"]');
      const fotoPropia = de(llave()).foto;
      ff.querySelector('small').textContent = fotoPropia ? '· propia'
        : (heredados.foto ? '· de la carpeta' : '· general');
      ff.querySelector('.cc-x').title = enCarpeta || !heredados.foto
        ? 'Volver a la foto general' : 'Volver a la foto de la carpeta';
      ff.querySelector('.cc-x').disabled = !fotoPropia;
      d.querySelector('.cc-todo').textContent = enCarpeta
        ? 'Sacar los de la carpeta' : 'Sacar los de esta charla';
    };
    const ff = d.querySelector('[data-k="foto"]');
    const archivo = ff.querySelector('input[type=file]');
    ff.querySelector('.cc-elegir').onclick = () => archivo.click();
    archivo.onchange = async () => {
      const f = archivo.files[0];
      archivo.value = '';
      if (!f) return;
      const chico = ff.querySelector('small');
      chico.textContent = '· subiendo…';
      const error = await subirFoto(llave(), f);
      refrescar();
      if (error) chico.textContent = '· ' + error;
    };
    ff.querySelector('.cc-x').onclick = () => { poner(llave(), 'foto', ''); refrescar(); };
    d.querySelectorAll('.cc-ambito button').forEach(b =>
      b.onclick = () => { ambito = b.dataset.a; refrescar(); });
    FILAS.forEach(([k]) => {
      const fila = d.querySelector('[data-k="' + k + '"]');
      const rueda = fila.querySelector('input');
      rueda.oninput = () => { poner(llave(), k, rueda.value, false);
                              fila.querySelector('small').textContent = ''; };
      rueda.onchange = () => { poner(llave(), k, rueda.value); };
      fila.querySelector('.cc-x').onclick = () => { poner(llave(), k, ''); refrescar(); };
    });
    d.querySelector('.cc-todo').onclick = () => { volverTodo(llave()); refrescar(); };
    d.querySelector('.cc-listo').onclick = cerrar;
    refrescar();
    document.body.appendChild(d);
    // Se ubica pegado al botón que lo abrió, sin salirse de la pantalla.
    const r = ancla && ancla.getBoundingClientRect ? ancla.getBoundingClientRect() : null;
    const w = d.offsetWidth, h = d.offsetHeight;
    let x = r ? r.right - w : (innerWidth - w) / 2;
    let y = r ? (r.top - h - 8 > 8 ? r.top - h - 8 : r.bottom + 8) : (innerHeight - h) / 2;
    x = Math.max(10, Math.min(x, innerWidth - w - 10));
    y = Math.max(10, Math.min(y, innerHeight - h - 10));
    d.style.left = x + 'px'; d.style.top = y + 'px';
    abierto = d;
    setTimeout(() => document.addEventListener('pointerdown', fuera, true), 0);
  }

  // Si cambia el tema (fondo, acento, claro/oscuro), las burbujas propias se rehacen con él.
  window.addEventListener('aspecto-aplicado', repintar);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrar(); });

  window.ColorCharla = {cargar, de, efectivos, clave, aplicar, limpiar, poner, editor, cerrar,
                        listo: () => cargado || cargar()};
  cargar();
})();
