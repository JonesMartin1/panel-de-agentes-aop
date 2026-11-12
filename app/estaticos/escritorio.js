// ⭐ El ESCRITORIO REMOTO adentro del panel (2026-11-12): la pantalla de otra compu, por
// RustDesk, en la columna derecha de /sesiones — y sola, en `/escritorio`, para el celular.
// Pedido de Martín: "¿no podemos embeber RustDesk en el panel?". Se ve la pantalla, se maneja
// con clics y teclado, y es la MISMA conexión que usa el agente de una sesión (skill
// `rustdesk-agente`): lo que hace el agente se ve acá, y tocar la imagen es tomar el control.
//
//   Escritorio.iniciar({agrandar, suelta});
//   Escritorio.mostrar(caja);   Escritorio.ocultar();
//
// Todo lo sabe el panel (`app/voz/escritorio.py`): esta página solo dibuja y manda.
//  · Cada pedido lleva la llave (`/escritorio/llave`, la misma de la terminal). Si el panel se
//    reinicia, la llave cambia: se pide de nuevo, una sola vez.
//  · La imagen se pide de a una, y la siguiente recién cuando llegó la anterior: una captura
//    tarda ~1 s, así que eso da un cuadro por segundo sin amontonar pedidos. Con la pieza
//    escondida o la pestaña del navegador tapada no se pide nada.
//  · ⚠ Las coordenadas que se mandan son PÍXELES DE LA PANTALLA REMOTA, no de la imagen
//    dibujada: `aRemoto` hace la cuenta con el tamaño real de la imagen. Sin eso, con la
//    columna angosta un clic caería a la izquierda y arriba de donde tocaste.
//  · Lo que se manda va EN FILA (`mandar`): un clic y las teclas de después tienen que llegar
//    en el orden en que los hiciste, aunque el primero tarde.
(function () {
  let cfg = {agrandar: null, suelta: false};
  let caja = null, visible = false, llave = '';
  let est = null;                 // lo último que dijo /escritorio/estado
  let elegida = '';               // la conexión que se está mirando
  let vista = '';                 // qué hay dibujado ahora, para no redibujar al pedo
  let aviso = null;               // {texto, mal, hasta}
  let ocupado = '';               // "prendiendo", "conectando"…: mientras, los botones esperan
  // ⭐ Varias compus a la vez (2026-11-12): con una conexión abierta, "+ Equipo" muestra la
  // lista para sumar otra SIN cerrar la que está. Cada sesión del panel trabaja sobre la suya.
  let sumando = false;
  let apagarArmado = 0;           // "Apagar" con conexiones abiertas pide un segundo toque
  let equipos = null;
  let marca = '', urlFoto = '', pidiendoFoto = false, relojEstado = null, relojFoto = null;
  let fila = Promise.resolve(), letras = '', relojLetras = null, derecho = false;

  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                                             .replace(/"/g, '&quot;');
  const $ = (q, raiz) => (raiz || caja).querySelector(q);

  const css = document.createElement('style');
  css.textContent = `
    .escr{display:flex;flex-direction:column;height:100%;min-height:0;font-size:13px;color:#9aa3b5}
    .escr .escrBarra{flex:none;display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
    .escr .escrTit{color:#e6e9ef;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .escr .escrModo{font-size:12px;color:#8a93a6}
    .escr .escrModo.mio{color:var(--ok-txt,#9eedc1)}
    .escr .escrBarra .hueco{flex:1}
    .escr button.escrB{appearance:none;background:none;border:1px solid var(--rastro-borde,#273042);
      border-radius:7px;color:#c9d4ea;font:inherit;font-size:12.5px;padding:3px 9px;cursor:pointer}
    .escr button.escrB:hover{border-color:#5b8def;color:#e6e9ef}
    .escr button.escrB.on{border-color:#5b8def;color:#8fb4ff}
    .escr button.escrB[disabled]{opacity:.5;cursor:progress}
    .escr button.escrB.fuerte{border-color:#5b8def;color:#8fb4ff}
    .escr button.escrB.fuerte:hover{background:rgba(91,141,239,.14);color:#e6e9ef}
    .escr .escrNota{font-size:12.5px;line-height:1.45;margin:6px 0}
    .escr .escrAviso{font-size:12px;margin:6px 0;color:#8fb4ff}
    .escr .escrAviso.mal{color:#e5a04b}
    /* ⭐ La pantalla entra SIEMPRE entera: se achica por el ancho O por el alto, lo que mande
       (2026-11-12). Antes iba al ancho de la columna y, con la ventana baja, la barra de tareas
       de la otra compu quedaba abajo, fuera de vista. El lienzo ocupa todo el lugar libre y la
       imagen se acomoda adentro sin deformarse; su caja es exactamente lo dibujado, que es lo
       que usa "aRemoto" para la cuenta de los clics. */
    .escr .escrLienzo{flex:1 1 0;min-height:0;overflow:hidden;outline:none;position:relative;
      display:flex;align-items:flex-start;justify-content:center}
    .escr .escrLienzo img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;
      border-radius:8px;outline:1px solid var(--rastro-borde,#1b2130);outline-offset:-1px;
      user-select:none;-webkit-user-drag:none;touch-action:none;cursor:crosshair}
    .escr .escrLienzo:focus img{outline-color:#5b8def}
    .escr .escrLienzo .vacio{padding:22px 14px;text-align:center}
    .escr .escrToque{position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;
      border:2px solid #8fb4ff;pointer-events:none;animation:escrToque .45s ease-out forwards}
    @keyframes escrToque{from{opacity:.9;transform:scale(.4)}to{opacity:0;transform:scale(1.6)}}
    .escr .escrPie{flex:none;display:flex;gap:6px;margin-top:8px}
    .escr .escrPie input,.escr .escrForm input{flex:1;min-width:0;box-sizing:border-box;background:transparent;
      border:0;border-bottom:1px solid rgba(138,147,166,.35);color:#e6e9ef;font:inherit;font-size:13px;padding:4px 0}
    .escr .escrPie input:focus,.escr .escrForm input:focus{outline:none;border-bottom-color:#5b8def}
    .escr .escrForm{display:flex;gap:8px;margin:10px 0}
    .escr .escrEq{display:flex;align-items:center;gap:8px;width:100%;background:none;border:0;padding:5px 0;
      font:inherit;color:#c9d4ea;cursor:pointer;text-align:left}
    .escr .escrEq:hover{color:#8fb4ff}
    .escr .escrEq .bola{width:8px;height:8px;border-radius:50%;background:#566;flex:none}
    .escr .escrEq .bola.si{background:#3fb950}
    .escr .escrEq .quien{margin-left:auto;font-size:12px;color:#7a8396}
    .escr .escrSec{font-size:11.5px;color:#7a8396;margin-top:14px;letter-spacing:.02em}
    .escr .escrLista{overflow:auto;min-height:0}
    .escr .escrChips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
  `;
  document.head.appendChild(css);

  // --- Hablar con el panel ------------------------------------------------------------------
  async function pedirLlave() {
    const r = await (await fetch('/escritorio/llave', {cache: 'no-store'})).json();
    if (!r.ok) throw new Error(r.error || 'sin llave');
    llave = r.llave;
  }
  async function crudo(ruta, cuerpo, mas) {
    const hacer = () => fetch(ruta, cuerpo === undefined
      ? {headers: Object.assign({'X-Terminal-Llave': llave}, mas || {}), cache: 'no-store'}
      : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Terminal-Llave': llave},
         body: JSON.stringify(cuerpo)});
    if (!llave) await pedirLlave();
    let r = await hacer();
    if (r.status === 403) { await pedirLlave(); r = await hacer(); }   // el panel se reinició
    return r;
  }
  async function pedir(ruta, cuerpo) {
    try {
      const r = await crudo(ruta, cuerpo);
      if (r.status === 404) return {ok: false, error: 'Falta reiniciar el panel para esto.'};
      return await r.json();
    } catch (e) { return {ok: false, error: 'No pude hablar con el panel.'}; }
  }
  function avisar(texto, mal) { aviso = {texto, mal: !!mal, hasta: Date.now() + 7000}; pintarAviso(); }
  function pintarAviso() {
    const a = caja && $('.escrAviso');
    if (!a) return;
    const vivo = aviso && Date.now() < aviso.hasta;
    a.hidden = !vivo;
    a.className = 'escrAviso' + (vivo && aviso.mal ? ' mal' : '');
    a.textContent = vivo ? aviso.texto : '';
  }

  // --- Qué se está mirando ------------------------------------------------------------------
  const sesion = () => (est && est.sesiones || []).find(s => s.sid === elegida) || null;

  async function refrescar() {
    if (!visible || !caja) return;
    const r = await pedir('/escritorio/estado');
    if (!visible) return;
    est = r;
    const ss = (r && r.sesiones) || [];
    if (!ss.some(s => s.sid === elegida)) elegida = ss.length ? ss[0].sid : '';
    pintar();
  }

  function queVista() {
    if (!est || !est.ok) return 'error';
    if (!est.instalado) return 'falta';
    if (!est.puerta) return 'apagada:' + (est.oficial_abierto ? 'of' : '');
    const s = sesion();
    if (!s || sumando) return 'elegir' + (s ? ':mas' : '');
    if (s.estado === 'needs_password' || s.estado === 'wrong_password') return 'clave:' + s.sid + s.estado;
    if (!s.listo) return 'espera:' + s.sid + s.estado;
    return 'pantalla:' + s.sid;
  }

  // Un botón por compu conectada. Con una sola no hace falta (su nombre ya está en la barra),
  // salvo en la lista de "+ Equipo", donde es la forma de volver a ella (`todas`).
  function chips(todas) {
    const ss = est.sesiones || [];
    if (ss.length < (todas ? 1 : 2)) return '';
    return '<div class="escrChips">' + ss.map(s => '<button type="button" class="escrB' +
      (!todas && s.sid === elegida ? ' on' : '') + '" data-elegir="' + esc(s.sid) + '" title="Ver ' +
      esc(s.equipo) + '">' + esc(s.equipo) + '</button>').join('') + '</div>';
  }
  const pie = '<div class="escrAviso" hidden></div>';

  function pintar() {
    if (!caja) return;
    const v = queVista() + '|' + ocupado + '|' + ((est && est.sesiones) || []).map(s => s.sid).join(',');
    if (v === vista) { actualizarBarra(); pintarAviso(); return; }
    vista = v;
    const tipo = v.split(/[:|]/)[0];
    let h = '<div class="escr">';
    if (tipo === 'error') {
      h += '<div class="escrNota">' + esc((est && est.error) || 'El panel no contestó.') + '</div>';
    } else if (tipo === 'falta') {
      h += '<div class="escrNota">En esta máquina no está la versión de prueba de RustDesk que ' +
           'permite manejar otra compu desde acá.</div>';
    } else if (tipo === 'apagada') {
      h += '<div class="escrBarra"><span class="escrTit">Escritorio remoto</span></div>' +
           '<div class="escrNota">Ver y manejar otra compu por RustDesk, desde acá. Usa una versión ' +
           'de prueba de RustDesk que se abre en la laptop mientras dure.</div>' +
           (est.oficial_abierto
             ? '<div class="escrNota">⚠ Tu RustDesk de siempre está abierto y los dos no pueden convivir. ' +
               'Prender esto lo <b>cierra</b> (se corta cualquier conexión que tengas con él) y al apagar ' +
               'se vuelve a abrir.</div>' : '') +
           '<div class="escrNota">Mientras esté prendido, las sesiones pueden conectarse a un equipo ' +
           'sin pedir permiso en la laptop. Se apaga solo si nadie lo usa.</div>' +
           '<div class="escrForm"><button type="button" class="escrB fuerte" data-prender' +
           (ocupado ? ' disabled' : '') + '>' +
           (ocupado === 'prendiendo' ? 'Prendiendo…'
             : est.oficial_abierto ? 'Cerrar mi RustDesk y prender' : 'Prender') + '</button></div>' + pie;
    } else if (tipo === 'elegir') {
      const hay = (est.sesiones || []).length;
      h += '<div class="escrBarra"><span class="escrTit">' + (hay ? 'Conectar otro equipo' : 'Escritorio remoto') +
           '</span><span class="hueco"></span>' +
           (hay ? '<button type="button" class="escrB" data-volver>Volver</button>' : '') +
           '<button type="button" class="escrB" data-apagar>Apagar</button></div>' +
           (hay ? '<div class="escrSec" style="margin-top:0">Ya conectados (siguen abiertos)</div>' + chips(true) : '') +
           '<form class="escrForm" data-conectar autocomplete="off"><input name="id" inputmode="numeric" ' +
           'placeholder="ID de RustDesk" aria-label="ID del equipo"><button class="escrB fuerte"' +
           (ocupado ? ' disabled' : '') + '>' + (ocupado === 'conectando' ? 'Conectando…' : 'Conectar') +
           '</button></form>' + pie +
           '<div class="escrSec">Equipos recientes</div><div class="escrLista" data-equipos>' +
           htmlEquipos() + '</div>' +
           '<div class="escrNota">También podés abrir la conexión desde la ventana de RustDesk de la ' +
           'laptop: aparece acá sola.</div>';
    } else if (tipo === 'clave') {
      const s = sesion();
      h += barra(s) + chips() +
           '<div class="escrNota">' + (s.estado === 'wrong_password'
             ? 'Esa contraseña no es. ' : '') + 'Contraseña de RustDesk de <b>' + esc(s.equipo) + '</b>:</div>' +
           '<form class="escrForm" data-clave autocomplete="off"><input name="clave" type="password" ' +
           'autocomplete="off" placeholder="Contraseña" aria-label="Contraseña del equipo">' +
           '<button class="escrB fuerte"' + (ocupado ? ' disabled' : '') + '>' +
           (ocupado === 'entrando' ? 'Entrando…' : 'Entrar') + '</button></form>' + pie +
           '<div class="escrNota">No se guarda: se usa para esta conexión y nada más.</div>';
    } else if (tipo === 'espera') {
      const s = sesion();
      h += barra(s) + chips() + '<div class="escrNota">' +
           esc(s.paso || (s.estado === 'connecting' ? 'Conectando…' : 'Esperando al equipo…')) + '</div>' + pie;
    } else {
      const s = sesion();
      h += barra(s) + chips() + pie +
           '<div class="escrLienzo" tabindex="0" aria-label="Pantalla de ' + esc(s.equipo) + '">' +
           '<div class="vacio">Trayendo la pantalla…</div></div>' +
           '<form class="escrPie" data-texto autocomplete="off"><input name="t" ' +
           'placeholder="Escribir en la otra compu…" aria-label="Texto para escribir en la otra compu">' +
           '<button class="escrB" title="Escribe el texto">Escribir</button>' +
           '<button type="button" class="escrB" data-tecla="Enter" title="Enter">↵</button>' +
           '<button type="button" class="escrB" data-tecla="Escape" title="Escape">Esc</button>' +
           '<button type="button" class="escrB" data-tecla="Meta" title="Tecla Windows">⊞</button>' +
           '<button type="button" class="escrB" data-derecho title="El próximo toque es clic derecho">' +
           'Der</button></form>';
    }
    caja.innerHTML = h + '</div>';
    marca = '';
    actualizarBarra();
    pintarAviso();
    if (tipo === 'elegir' && !equipos) traerEquipos();
    if (tipo === 'pantalla') { armarLienzo(); pedirFoto(); }
  }

  function barra(s) {
    return '<div class="escrBarra"><span class="escrTit">' + esc(s.equipo) + '</span>' +
           '<span class="escrModo" data-modo></span><span class="hueco"></span>' +
           '<button type="button" class="escrB" data-control></button>' +
           (cfg.agrandar ? '<button type="button" class="escrB" data-agrandar title="Agrandar la columna">⤢</button>' : '') +
           '<button type="button" class="escrB" data-sumar title="Conectar otro equipo sin cerrar este">+ Equipo</button>' +
           '<button type="button" class="escrB" data-cortar title="Cerrar SOLO esta conexión; las otras siguen">Desconectar</button>' +
           '<button type="button" class="escrB" data-apagar title="Cerrar RustDesk con agente">Apagar</button></div>';
  }
  function actualizarBarra() {
    const s = sesion(), m = caja && $('[data-modo]'), b = caja && $('[data-control]');
    if (!s || !m || !b) return;
    const mio = s.modo === 'agent';
    m.textContent = mio ? 'con control' : 'mirando';
    m.className = 'escrModo' + (mio ? ' mio' : '');
    m.title = mio ? 'El panel y el agente manejan esta compu; la ventana de RustDesk de la laptop no.'
                  : 'La maneja la ventana de RustDesk de la laptop. Tocá la imagen para tomar el control.';
    b.textContent = mio ? 'Soltar' : 'Tomar control';
  }
  function htmlEquipos() {
    if (!equipos) return '<div class="escrNota">Buscando…</div>';
    if (!equipos.length) return '<div class="escrNota">Todavía no hay equipos recientes.</div>';
    return equipos.map(e => '<button type="button" class="escrEq" data-equipo="' + esc(e.id) + '">' +
      '<span class="bola' + (e.en_linea ? ' si' : '') + '" title="' + (e.en_linea ? 'en línea' : 'apagado') +
      '"></span><span>' + esc(e.nombre) + '</span><span class="quien">' + esc(e.usuario) + '</span></button>').join('');
  }
  async function traerEquipos() {
    const r = await pedir('/escritorio/equipos');
    equipos = r.ok ? r.equipos : [];
    const l = caja && $('[data-equipos]');
    if (l) l.innerHTML = htmlEquipos();
  }

  // --- La imagen ----------------------------------------------------------------------------
  async function pedirFoto() {
    clearTimeout(relojFoto);
    if (pidiendoFoto || !visible || document.hidden || !caja) return;
    const s = sesion(), lienzo = $('.escrLienzo');
    if (!s || !s.listo || !lienzo) return;
    pidiendoFoto = true;
    let espera = 250;
    try {
      const r = await crudo('/escritorio/foto?sid=' + encodeURIComponent(s.sid) + (cfg.suelta ? '&jpg=1' : ''),
                            undefined, marca ? {'If-None-Match': '"' + marca + '"'} : null);
      if (r.status === 200) {
        marca = (r.headers.get('ETag') || '').replace(/"/g, '');
        const url = URL.createObjectURL(await r.blob());
        let img = $('img', lienzo);
        if (!img) { lienzo.innerHTML = ''; img = document.createElement('img'); img.alt = ''; img.draggable = false; lienzo.appendChild(img); }
        const vieja = urlFoto;
        img.onload = () => { if (vieja) URL.revokeObjectURL(vieja); };
        img.src = url; urlFoto = url;
      } else if (r.status === 304) {
        espera = 500;                        // nada cambió: se afloja un poco
      } else {
        espera = 2500;
        if (r.status === 503 || r.status === 409) refrescar();
      }
    } catch (e) { espera = 3000; }
    pidiendoFoto = false;
    if (visible) relojFoto = setTimeout(pedirFoto, espera);
  }

  // Del punto tocado en la imagen DIBUJADA al píxel de la pantalla REMOTA.
  function aRemoto(img, clientX, clientY) {
    const c = img.getBoundingClientRect();
    const x = Math.round((clientX - c.left) * img.naturalWidth / c.width);
    const y = Math.round((clientY - c.top) * img.naturalHeight / c.height);
    return {x: Math.max(0, Math.min(img.naturalWidth - 1, x)), y: Math.max(0, Math.min(img.naturalHeight - 1, y))};
  }
  function marcarToque(lienzo, clientX, clientY) {
    const c = lienzo.getBoundingClientRect(), p = document.createElement('i');
    p.className = 'escrToque';
    p.style.left = (clientX - c.left + lienzo.scrollLeft) + 'px';
    p.style.top = (clientY - c.top + lienzo.scrollTop) + 'px';
    lienzo.appendChild(p);
    setTimeout(() => p.remove(), 500);
  }

  // Lo que se manda va en fila: llega en el orden en que lo hiciste.
  function mandar(a) {
    const s = sesion();
    if (!s) return;
    a.sid = s.sid;
    fila = fila.then(() => pedir('/escritorio/accion', a)).then(r => {
      if (!r.ok) avisar(r.error || 'No se pudo.', true);
      else if (r.tomo_control) { s.modo = 'agent'; actualizarBarra(); }
      clearTimeout(relojFoto); relojFoto = setTimeout(pedirFoto, 150);
    });
  }
  // Las letras se juntan un instante y viajan como un solo texto.
  function soltarLetras() {
    clearTimeout(relojLetras);
    if (!letras) return;
    const t = letras; letras = '';
    mandar({tipo: 'texto', texto: t});
  }
  const MODS = e => [e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && 'shift', e.metaKey && 'command'].filter(Boolean);
  const SOLAS = {Control: 1, Shift: 1, Alt: 1, AltGraph: 1, CapsLock: 1, Dead: 1, Unidentified: 1, Process: 1};

  function armarLienzo() {
    const lienzo = $('.escrLienzo');
    let abajo = null;
    lienzo.addEventListener('pointerdown', e => {
      const img = e.target.closest('img');
      if (!img) return;
      lienzo.focus({preventScroll: true});
      if (e.button > 2) return;
      e.preventDefault();
      try { img.setPointerCapture(e.pointerId); } catch (err) {}
      abajo = {cx: e.clientX, cy: e.clientY, p: aRemoto(img, e.clientX, e.clientY), boton: e.button};
    });
    lienzo.addEventListener('pointerup', e => {
      const img = e.target.closest('img');
      if (!img || !abajo) return;
      const d = abajo; abajo = null;
      soltarLetras();
      const hasta = aRemoto(img, e.clientX, e.clientY);
      const mods = MODS(e).filter(m => m !== 'command');
      marcarToque(lienzo, e.clientX, e.clientY);
      if (Math.hypot(e.clientX - d.cx, e.clientY - d.cy) > 6 && d.boton === 0) {
        mandar({tipo: 'mouse', accion: 'drag', x: d.p.x, y: d.p.y, a_x: hasta.x, a_y: hasta.y, mods});
        return;
      }
      const esDerecho = d.boton === 2 || derecho;
      if (derecho) { derecho = false; const b = $('[data-derecho]'); if (b) b.classList.remove('on'); }
      mandar({tipo: 'mouse', accion: d.boton === 1 ? 'middle_click' : esDerecho ? 'right_click' : 'click',
              x: hasta.x, y: hasta.y, mods});
    });
    lienzo.addEventListener('pointercancel', () => { abajo = null; });
    lienzo.addEventListener('contextmenu', e => { if (e.target.closest('img')) e.preventDefault(); });
    lienzo.addEventListener('dragstart', e => e.preventDefault());
    // La rueda: se junta un instante para no mandar veinte pedidos por un solo gesto.
    let rueda = null;
    lienzo.addEventListener('wheel', e => {
      const img = e.target.closest('img');
      if (!img) return;
      e.preventDefault();
      const p = aRemoto(img, e.clientX, e.clientY);
      if (!rueda) rueda = {dy: 0, dx: 0, p, reloj: setTimeout(() => {
        const r = rueda; rueda = null;
        const vertical = Math.abs(r.dy) >= Math.abs(r.dx), n = vertical ? r.dy : r.dx;
        if (!n) return;
        mandar({tipo: 'rueda', x: r.p.x, y: r.p.y,
                direccion: vertical ? (n > 0 ? 'down' : 'up') : (n > 0 ? 'right' : 'left'),
                cantidad: Math.max(1, Math.min(10, Math.round(Math.abs(n) / 100)))});
      }, 140)};
      rueda.dy += e.deltaY; rueda.dx += e.deltaX;
    }, {passive: false});
    // El teclado, con el lienzo enfocado. Una letra sola se junta con las vecinas; con Ctrl o
    // Alt, o una tecla con nombre (Enter, flechas, F5…), va como tecla.
    lienzo.addEventListener('keydown', e => {
      if (SOLAS[e.key] || e.key === 'Meta' || e.isComposing) return;
      e.preventDefault(); e.stopPropagation();
      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        letras += e.key;
        clearTimeout(relojLetras);
        relojLetras = setTimeout(soltarLetras, 90);
        return;
      }
      soltarLetras();
      const nombre = /^F\d{1,2}$/.test(e.key) ? 'VK_' + e.key : e.key === ' ' ? 'Space' : e.key;
      mandar({tipo: 'tecla', tecla: nombre, mods: MODS(e)});
    });
  }

  // --- Los botones y formularios (delegados: la pieza se redibuja) ---------------------------
  async function conectarA(id) {
    if (ocupado) return;
    ocupado = 'conectando'; pintar();
    const r = await pedir('/escritorio/conectar', {id});
    ocupado = '';
    if (!r.ok) avisar(r.error || 'No pude conectar.', true);
    else { if (r.sid) elegida = r.sid; sumando = false; }
    vista = ''; await refrescar();
  }
  document.addEventListener('click', async e => {
    if (!caja || !caja.contains(e.target)) return;
    const b = e.target.closest('button');
    if (!b) return;
    const s = sesion();
    if (b.dataset.prender !== undefined) {
      ocupado = 'prendiendo'; pintar();
      const r = await pedir('/escritorio/arrancar', {cerrar_oficial: !!(est && est.oficial_abierto)});
      ocupado = '';
      if (!r.ok) { if (r.oficial_abierto && est) est.oficial_abierto = true; avisar(r.error || 'No arrancó.', true); }
      vista = ''; equipos = null; await refrescar();
    } else if (b.dataset.apagar !== undefined) {
      // Apagar cierra TODAS las conexiones. Con alguna abierta pide un segundo toque: es el
      // único botón de la pieza que puede cortarle el trabajo a una sesión en otra compu.
      const n = ((est && est.sesiones) || []).length;
      if (n && Date.now() > apagarArmado) {
        apagarArmado = Date.now() + 5000;
        b.textContent = n === 1 ? '¿Cortar la conexión y apagar?' : '¿Cortar las ' + n + ' conexiones y apagar?';
        b.classList.add('on');
        setTimeout(() => { if (b.isConnected) { b.textContent = 'Apagar'; b.classList.remove('on'); } }, 5000);
        return;
      }
      apagarArmado = 0; sumando = false;
      const r = await pedir('/escritorio/apagar', {});
      if (!r.ok) avisar(r.error || 'No se pudo apagar.', true);
      equipos = null; vista = ''; await refrescar();
    } else if (b.dataset.equipo) {
      conectarA(b.dataset.equipo);
    } else if (b.dataset.sumar !== undefined) {
      sumando = true; equipos = null; vista = ''; pintar();
    } else if (b.dataset.volver !== undefined) {
      sumando = false; vista = ''; pintar();
    } else if (b.dataset.elegir) {
      elegida = b.dataset.elegir; sumando = false; vista = ''; pintar();
    } else if (b.dataset.control !== undefined && s) {
      const r = await pedir('/escritorio/control', {sid: s.sid, tomar: s.modo !== 'agent'});
      if (!r.ok) avisar(r.error || 'No se pudo.', true);
      await refrescar();
    } else if (b.dataset.cortar !== undefined && s) {
      const r = await pedir('/escritorio/desconectar', {sid: s.sid});
      if (!r.ok) avisar(r.error || 'No se pudo desconectar.', true);
      vista = ''; await refrescar();
    } else if (b.dataset.agrandar !== undefined && cfg.agrandar) {
      cfg.agrandar();
    } else if (b.dataset.tecla) {
      soltarLetras(); mandar({tipo: 'tecla', tecla: b.dataset.tecla, mods: []});
    } else if (b.dataset.derecho !== undefined) {
      derecho = !derecho; b.classList.toggle('on', derecho);
    }
  });
  document.addEventListener('submit', async e => {
    if (!caja || !caja.contains(e.target)) return;
    const f = e.target;
    e.preventDefault();
    if (f.dataset.conectar !== undefined) {
      const id = (f.elements.id.value || '').replace(/\D/g, '');
      if (id) conectarA(id);
    } else if (f.dataset.clave !== undefined) {
      const s = sesion(), clave = f.elements.clave.value;
      if (!s || !clave || ocupado) return;
      ocupado = 'entrando'; pintar();
      const r = await pedir('/escritorio/clave', {sid: s.sid, clave});
      ocupado = '';
      // Una contraseña mala no necesita aviso: la vista misma lo dice al redibujarse.
      if (r.ok) aviso = null;
      else if (r.error) avisar(r.error, true);
      vista = ''; await refrescar();
    } else if (f.dataset.texto !== undefined) {
      const t = f.elements.t.value;
      if (!t) return;
      f.elements.t.value = '';
      soltarLetras(); mandar({tipo: 'texto', texto: t});
    }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && visible) { refrescar(); pedirFoto(); } });

  function mostrar(c) {
    caja = c; visible = true; vista = '';
    if (!c.firstChild) c.innerHTML = '<div class="escr"><div class="escrNota">Cargando…</div></div>';
    refrescar();
    clearInterval(relojEstado);
    relojEstado = setInterval(refrescar, 3000);
  }
  function ocultar() {
    visible = false;
    clearInterval(relojEstado); clearTimeout(relojFoto);
    soltarLetras();
  }

  window.Escritorio = {iniciar: c => { cfg = Object.assign(cfg, c || {}); }, mostrar, ocultar,
                       _aRemoto: aRemoto};
})();
