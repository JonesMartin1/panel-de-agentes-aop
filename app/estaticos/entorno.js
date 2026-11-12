// ⭐ La columna de la derecha del Claude Desktop, en el panel (2026-10-20): Entorno
// (máquina, carpeta, control remoto), Contexto, Conectores y lo último que vio en el
// navegador. Una sola pieza para las dos pantallas, como `pasos.js`: en la compu va en la
// columna de la derecha de /sesiones, en el celular en una hoja que se abre con ⓘ.
//
//   Entorno.iniciar({ubicacion: () => ({cwd, sid, nombre}), alCambiar: () => …});
//   const r = await Entorno.pedir(u);  caja.innerHTML = Entorno.html(r, u);
//
// Los datos salen todos juntos de `GET /movil/entorno`. El clic en la llave del control
// remoto y lo abierto/cerrado de cada tarjeta los escucha sola, en todo el documento.
(function () {
  let cfg = {ubicacion: () => null, alCambiar: () => {}};
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                                             .replace(/"/g, '&quot;');
  const plegadas = new Set(JSON.parse(localStorage.getItem('sesDerPlegadas') || '[]'));

  const css = document.createElement('style');
  css.textContent = `
    .entornoCaja .tarjDer{border:1px solid var(--rastro-borde,#1b2130);border-radius:10px;
      padding:10px 12px;margin-bottom:10px;font-size:13px;color:#9aa3b5}
    .entornoCaja .tarjDer>summary{cursor:pointer;list-style:none;display:flex;align-items:center;
      color:#e6e9ef;font-weight:600}
    .entornoCaja .tarjDer>summary::-webkit-details-marker{display:none}
    .entornoCaja .tarjDer>summary::after{content:'▾';color:#6e7889;font-weight:400;margin-left:8px}
    .entornoCaja .tarjDer:not([open])>summary::after{content:'▸'}
    .entornoCaja .resumen{font-weight:400;color:#8a93a6;margin-left:auto}
    .entornoCaja .renDer{display:flex;align-items:center;gap:8px;margin-top:8px;min-width:0}
    .entornoCaja .txt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
    .entornoCaja .barraCtx{height:6px;border-radius:4px;background:#1d2534;margin-top:8px;overflow:hidden}
    .entornoCaja .barraCtx i{display:block;height:100%;background:#5b8def}
    .entornoCaja .barraCtx.medio i{background:#d9a441}
    .entornoCaja .barraCtx.mucho i{background:#e0703c}
    .entornoCaja .bolaCon{width:8px;height:8px;border-radius:50%;flex:none;background:#566}
    .entornoCaja .bolaCon.connected{background:#3fb950}
    .entornoCaja .bolaCon.failed{background:#e5534b}
    .entornoCaja .bolaCon.pending{background:#d9a441}
    .entornoCaja .llave{margin-left:auto;position:relative;width:34px;height:19px;flex:none;
      cursor:pointer;border-radius:10px;background:#39445a;transition:background .15s;border:0;padding:0}
    .entornoCaja .llave::after{content:'';position:absolute;top:2px;left:2px;width:15px;height:15px;
      border-radius:50%;background:#e6e9ef;transition:left .15s}
    .entornoCaja .llave.on{background:#3d7bd9}
    .entornoCaja .llave.on::after{left:17px}
    .entornoCaja .llave.yendo{opacity:.5;cursor:progress}
    .entornoCaja a{color:#8fb4ff}
    .entornoCaja .notaDer{font-size:12px;color:#7a8396;margin-top:6px;line-height:1.35}
    .entornoCaja .fotoPaso{max-width:100%;margin:8px 0 2px}
    .entornoCaja .fij{gap:6px}
    .entornoCaja .fij .ico{flex:none;width:18px;text-align:center}
    .entornoCaja .fij a.txt,.entornoCaja .fij button.txt{flex:1;text-align:left;background:none;border:0;
      padding:0;font:inherit;color:#c9d4ea;cursor:pointer;text-decoration:none}
    .entornoCaja .fij a.txt:hover,.entornoCaja .fij button.txt:hover{color:#8fb4ff;text-decoration:underline}
    .entornoCaja .fij.falta button.txt{color:#7a8396;text-decoration:line-through}
    .entornoCaja .fijQuitar{flex:none;background:none;border:0;color:#6e7889;cursor:pointer;
      font-size:15px;line-height:1;padding:0 2px;opacity:0;transition:opacity .12s}
    .entornoCaja .fij:hover .fijQuitar,.entornoCaja .fijQuitar:focus{opacity:1}
    .entornoCaja .fijQuitar:hover{color:#e5534b}
    @media (hover:none){.entornoCaja .fijQuitar{opacity:1}}
    .entornoCaja .fijSec{font-size:11.5px;color:#7a8396;margin-top:12px;letter-spacing:.02em}
    .entornoCaja .fijSec:first-of-type{margin-top:8px}
    .entornoCaja .fijMas{display:block;margin-top:6px;background:none;border:0;padding:0;
      font:inherit;font-size:12.5px;color:#7a8396;cursor:pointer;text-align:left}
    .entornoCaja .fijMas:hover{color:#c9d4ea}
    .entornoCaja .fijForm{margin-top:8px}
    .entornoCaja .fijForm input{width:100%;box-sizing:border-box;background:transparent;border:0;
      border-bottom:1px solid rgba(138,147,166,.35);border-radius:0;color:inherit;font:inherit;
      font-size:12.5px;padding:3px 0 4px}
    .entornoCaja .fijForm input::placeholder{color:#6e7889}
    .entornoCaja .fijForm input:focus{outline:none;border-bottom-color:#5b8def}
    .entornoCaja .fijAviso{font-size:12px;margin-top:6px;color:#8fb4ff}
    .entornoCaja .fijAviso.mal{color:#e5a04b}
    .entornoCaja .desp{align-items:flex-start;text-decoration:none;color:inherit}
    .entornoCaja .desp .ico{flex:none;width:18px;text-align:center;color:#8a93a6}
    .entornoCaja .desp .quien{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
    .entornoCaja .desp .txt{color:#c9d4ea}
    .entornoCaja a.desp:hover .txt{color:#8fb4ff;text-decoration:underline}
    .entornoCaja .desp .cuando{font-size:12px;color:#8a93a6}
    .entornoCaja .desp.trabaja .ico,.entornoCaja .desp.pregunta .ico,
    .entornoCaja .desp.pregunta .cuando{color:var(--aviso-txt,#facf85)}
    .entornoCaja .desp.termino .ico{color:var(--ok-txt,#9eedc1)}
    .entornoCaja .desp.fallo .ico,.entornoCaja .desp.fallo .cuando{color:var(--mal-txt,#f7a1a1)}
  `;
  document.head.appendChild(css);

  // ⭐ Los DESPACHOS de la sesión chief (2026-11-11): a quién le mandó algo y cómo va cada
  // cosa. Pedido de Martín: mientras el chief espera no había señal de vida, y mirando la
  // otra charla creyó que había terminado. Vienen de `/movil/despachos`, aparte: con un
  // panel sin reiniciar ese pedido da 404 y la tarjeta no aparece. Tampoco aparece en una
  // charla que no despachó nada: existe solo donde hay algo que mostrar.
  let despVivos = false, ultimoPedido = 0;
  const VIVO_DESP = {trabaja: 1, pregunta: 1};
  async function pedirDespachos(u) {
    if (!u || !u.sid) return null;
    try {
      const r = await fetch('/movil/despachos?cwd=' + encodeURIComponent(u.cwd || '') +
                            '&sid=' + encodeURIComponent(u.sid));
      if (!r.ok) return null;
      const d = await r.json();
      return d && d.ok && Array.isArray(d.items) && d.items.length ? d : null;
    } catch (e) { return null; }
  }

  // "4 min", "1 h 20 min". Por debajo del minuto no se cuentan segundos: la tarjeta se
  // reescribe solo cuando cambia el texto, o sea una vez por minuto.
  function hace(seg) {
    const m = Math.floor(Math.max(0, seg) / 60);
    if (m < 1) return 'menos de 1 min';
    if (m < 60) return m + ' min';
    const h = Math.floor(m / 60), r = m % 60;
    return h + ' h' + (r ? ' ' + r + ' min' : '');
  }
  const ICONO_DESP = {trabaja: '●', pregunta: '✋', termino: '✓', fallo: '✕', corto: '⚠', paro: '■'};
  const TEXTO_DESP = {termino: 'terminó', fallo: 'falló', corto: 'se cortó', paro: 'se paró'};
  function htmlDespachos(d) {
    // La hora la pone el servidor: el reloj del teléfono puede estar corrido.
    const ahora = d.ahora || Date.now() / 1000;
    let b = '', vivos = 0;
    for (const f of d.items) {
      const t = hace(ahora - (f.desde || ahora));
      if (VIVO_DESP[f.estado]) vivos++;
      const cuando = f.estado === 'trabaja' ? 'trabaja · ' + t
                   : f.estado === 'pregunta' ? 'te pregunta algo'
                   : (TEXTO_DESP[f.estado] || 'se cortó') + ' hace ' + t;
      // ⚠ En DOS renglones: el nombre arriba con todo el ancho y el estado abajo. En uno
      // solo, con los nombres de verdad ("Migración de tal cosa · seguir acá") el estado se
      // comía el lugar y del nombre quedaban seis letras: no se sabía cuál era cuál.
      const cuerpo = '<span class="ico">' + (ICONO_DESP[f.estado] || '⚠') + '</span>' +
                     '<span class="quien"><span class="txt">' + esc(f.nombre) + '</span>' +
                     '<span class="cuando">' + cuando + '</span></span>';
      const clase = 'renDer desp ' + esc(f.estado);
      // Sin id todavía (una charla que está naciendo) no hay adónde ir: va sin enlace.
      b += f.sid
        ? '<a class="' + clase + '" href="' + esc(location.pathname + '?c=' + encodeURIComponent(f.sid)) +
          '" data-desp="' + esc(f.sid) + '" data-cwd="' + esc(f.cwd) + '" data-nombre="' + esc(f.nombre) +
          '" data-cerebro="' + esc(f.cerebro) + '" title="' + esc(f.nombre) + ' · abrir esa charla">' +
          cuerpo + '</a>'
        : '<div class="' + clase + '">' + cuerpo + '</div>';
    }
    return tarjeta('despachos', 'Despachos', vivos ? vivos + ' en curso' : '', b);
  }
  // Tocar un renglón abre esa charla sin recargar, si la pantalla dijo cómo (`abrir`). Con
  // Ctrl, Shift o el botón del medio se deja al navegador: abre su dirección en otra pestaña.
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('.entornoCaja a.desp');
    if (!a || !cfg.abrir || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    cfg.abrir(a.dataset.cwd || '', a.dataset.desp, a.dataset.nombre || '', a.dataset.cerebro || '');
  });
  // ⭐ Con algo en curso, la columna se vuelve a pedir cada 4 s. Sin esto una charla quieta
  // —y el chief esperando ESTÁ quieto— se refresca cada 10: "terminó" llegaba tarde. Solo
  // corre si la caja está a la vista, y no se suma a un refresco que ya viene seguido.
  setInterval(() => {
    if (!despVivos || document.visibilityState === 'hidden' || Date.now() - ultimoPedido < 4000) return;
    const caja = document.querySelector('.entornoCaja');
    const r = caja && caja.getBoundingClientRect();
    if (!r || r.width < 40 || r.height < 1 || r.top >= innerHeight || r.bottom <= 0) return;
    cfg.alCambiar();
  }, 1000);

  // ⭐ Los ENLACES Y ARCHIVOS de la carpeta (2026-11-11) vienen de `/fijados`, aparte. Si el
  // panel todavía no los sirve (no se reinició), ese pedido falla y la tarjeta no aparece:
  // la columna queda exactamente como antes.
  // Trae los DOS apartados: el del proyecto (la carpeta) y el de esta sesión. `sesion` llega
  // null en una charla sin id todavía, y entonces ese apartado no se dibuja.
  async function pedirFijados(u) {
    if (!u || !u.cwd) return null;
    try {
      const r = await fetch('/fijados?cwd=' + encodeURIComponent(u.cwd) +
                            '&sid=' + encodeURIComponent(u.sid || ''));
      if (!r.ok) return null;
      const d = await r.json();
      if (!d || !d.ok) return null;
      return {proyecto: d.proyecto || d.items || [], sesion: Array.isArray(d.sesion) ? d.sesion : null};
    } catch (e) { return null; }
  }

  // ⭐ El ESCRITORIO REMOTO (2026-11-12) en la compu es una pieza de la columna derecha. En el
  // celular no hay columna: si el panel lo sirve Y deja entrar desde donde se está mirando
  // (por el túnel público no deja, a propósito), la tarjeta Entorno suma un acceso a su
  // página suelta. Se pregunta una sola vez por carga.
  let hayEscritorio = null;
  async function mirarEscritorio() {
    if (hayEscritorio !== null || window.Escritorio) return;
    hayEscritorio = false;
    try { hayEscritorio = (await fetch('/escritorio/llave', {cache: 'no-store'})).ok; } catch (e) {}
  }

  async function pedir(u) {
    ultimoPedido = Date.now();
    const [r, fij, desp] = await Promise.all([
      fetch('/movil/entorno?cwd=' + encodeURIComponent(u.cwd || '') +
            '&sid=' + encodeURIComponent(u.sid || '')).then(x => x.json()),
      pedirFijados(u), pedirDespachos(u), mirarEscritorio()]);
    if (r && fij) r.fijados = fij;
    if (r && desp) r.despachos = desp;
    despVivos = !!(desp && desp.items.some(f => VIVO_DESP[f.estado]));
    return r;
  }

  // Lo que pasó con el último agregar/abrir/sacar, para mostrarlo un rato debajo de la lista.
  // El aviso sale debajo del apartado donde pasó (proyecto o sesión).
  let fijAviso = null;            // {texto, mal, hasta, amb}
  function avisar(texto, mal, amb) { fijAviso = {texto, mal: !!mal, hasta: Date.now() + 6000, amb}; }

  const ICONO_FIJ = {enlace: '🔗', archivo: '📄', carpeta: '📁'};
  // ⭐ Dos apartados (2026-11-11): PROYECTO, que ven todas las charlas de la carpeta, y ESTA
  // SESIÓN, que ve solo esta charla. Cada uno con su "+ Agregar"; cada fila sabe de cuál es
  // (`data-amb`) para que abrir y sacar le peguen a la lista correcta.
  function htmlApartado(amb, titulo, items) {
    let b = '<div class="fijSec">' + titulo + '</div>';
    for (const f of items) {
      const ico = '<span class="ico">' + (ICONO_FIJ[f.tipo] || '📄') + '</span>';
      const quitar = '<button type="button" class="fijQuitar" data-fij-quitar="' + esc(f.id) +
                     '" data-amb="' + amb + '" title="Sacar de la lista" aria-label="Sacar ' +
                     esc(f.nombre) + '">×</button>';
      if (f.tipo === 'enlace') {
        b += '<div class="renDer fij" title="' + esc(f.destino) + '">' + ico +
             '<a class="txt" href="' + esc(f.destino) + '" target="_blank" rel="noopener noreferrer">' +
             esc(f.nombre) + '</a>' + quitar + '</div>';
      } else {
        const falta = f.existe === false;
        b += '<div class="renDer fij' + (falta ? ' falta' : '') + '" title="' + esc(f.destino) +
             (falta ? ' (ya no está ahí)' : ' · se abre en la compu') + '">' + ico +
             '<button type="button" class="txt" data-fij-abrir="' + esc(f.id) + '" data-amb="' + amb +
             '">' + esc(f.nombre) + '</button>' + quitar + '</div>';
      }
    }
    if (fijAviso && fijAviso.amb === amb && Date.now() < fijAviso.hasta)
      b += '<div class="fijAviso' + (fijAviso.mal ? ' mal' : '') + '">' + esc(fijAviso.texto) + '</div>';
    // Quieta es una sola línea tenue ("+ Agregar"); la caja aparece recién al tocarla.
    b += fijEditando === amb ? formFij(amb)
       : '<button type="button" class="fijMas" data-fij-mas="' + amb + '">+ Agregar</button>';
    return b;
  }
  function htmlFijados(f) {
    let b = htmlApartado('proyecto', 'Proyecto', f.proyecto);
    if (f.sesion) b += htmlApartado('sesion', 'Esta sesión', f.sesion);
    const n = f.proyecto.length + (f.sesion ? f.sesion.length : 0);
    return tarjeta('fijados', 'Enlaces y archivos', n ? String(n) : '', b);
  }
  let fijEditando = null;          // 'proyecto' | 'sesion' | null: qué apartado tiene la caja abierta
  const formFij = amb => '<form class="fijForm" autocomplete="off" data-ambito="' + amb + '">' +
    '<input name="t" placeholder="Pegá un enlace o una ruta y Enter" ' +
    'aria-label="Enlace o ruta para agregar" title="Enter agrega · Esc cancela"></form>';
  function cerrarFij() {
    fijEditando = null;
    cfg.alCambiar();
  }

  function tarjeta(id, titulo, resumen, cuerpo) {
    return '<details class="tarjDer" data-t="' + id + '"' + (plegadas.has(id) ? '' : ' open') +
           '><summary>' + titulo + (resumen ? '<span class="resumen">' + resumen + '</span>' : '') +
           '</summary>' + cuerpo + '</details>';
  }

  const mil = n => n >= 1000000 ? (n / 1000000).toFixed(1).replace('.', ',') + ' M'
                                : Math.round(n / 1000) + ' k';

  function html(r, u) {
    if (!r || !r.ok) return '<div class="notaDer">El panel no contestó (¿falta reiniciarlo?).</div>';
    let h = '';
    // Despachos va PRIMERA: en la charla del chief es lo que se viene a mirar.
    if (r.despachos) h += htmlDespachos(r.despachos);
    // Entorno: máquina, carpeta y el control remoto.
    const rem = r.remoto || {};
    let ent = '<div class="renDer"><span>💻</span><span class="txt">' + esc(r.maquina) + '</span></div>' +
              '<div class="renDer" title="' + esc(r.carpeta) + '"><span>📁</span><span class="txt">' +
              esc(r.nombre || r.carpeta) + '</span></div>';
    if (r.remoto_posible) {
      ent += '<div class="renDer"><span>📱</span><span class="txt">Control remoto</span>' +
             '<button class="llave' + (rem.prendido ? ' on' : '') + '" data-remoto ' +
             'title="Publicar esta charla en claude.ai/code para seguirla desde la app de Claude"></button></div>';
      if (rem.prendido && rem.url)
        ent += '<div class="notaDer"><a href="' + esc(rem.url) + '" target="_blank" rel="noopener">' +
               'Abrir en claude.ai</a>' +
               (rem.estado && rem.estado !== 'conectado' ? ' · ' + esc(rem.estado) : '') + '</div>';
      else if (!rem.prendido)
        ent += '<div class="notaDer">Prendelo para escribirle desde la app de Claude o claude.ai/code.</div>';
    }
    if (hayEscritorio && !window.Escritorio)
      ent += '<div class="renDer fij"><span class="ico">🖥</span><a class="txt" href="/escritorio" ' +
             'target="_blank" rel="noopener">Escritorio remoto</a></div>';
    h += tarjeta('entorno', 'Entorno', '', ent);
    if (r.fijados) h += htmlFijados(r.fijados);
    // Contexto: el porcentaje del techo del modelo y lo que arrastra en cada mensaje.
    const c = r.contexto;
    if (c && c.tokens) {
      const tope = c.tope || 200000, pct = Math.min(100, Math.round(100 * c.tokens / tope));
      h += tarjeta('contexto', 'Contexto', pct + ' %',
        '<div class="barraCtx ' + esc(c.nivel || '') + '"><i style="width:' + pct + '%"></i></div>' +
        '<div class="notaDer">' + mil(c.tokens) + ' de ' + mil(tope) +
        ': es lo que se relee en cada mensaje.' + (c.aviso ? '<br>' + esc(c.aviso) : '') + '</div>');
    } else if (u && u.sid) {
      h += tarjeta('contexto', 'Contexto', '',
        '<div class="notaDer">Todavía no hay medida: aparece después de la primera respuesta.</div>');
    }
    // Conectores: los servidores MCP y cómo están.
    if (r.cerebro !== 'codex') {
      const con = r.conectores || [];
      const ok = con.filter(x => x.estado === 'connected').length;
      const resumen = !con.length ? '' : r.conectores_de === 'configurados'
                    ? con.length + ' configurado(s)' : ok + ' conectado(s)';
      h += tarjeta('conectores', 'Conectores', resumen,
        (con.length ? con.map(x => '<div class="renDer" title="' + esc(x.estado || 'sin arrancar') + '">' +
                        '<span class="bolaCon ' + esc(x.estado) + '"></span><span class="txt">' +
                        esc(x.nombre) + '</span></div>').join('')
                    : '<div class="notaDer">Sin conectores anotados.</div>') +
        (r.conectores_de && r.conectores_de !== 'ahora'
          ? '<div class="notaDer">' + (r.conectores_de === 'configurados'
              ? 'Según la configuración: el estado se ve cuando la charla arranca.'
              : 'Según ' + esc(r.conectores_de) + '.') + '</div>' : ''));
    }
    // Navegador: lo último que vio, como el panel de la página del Desktop.
    const nav = r.navegador;
    if (nav) {
      let cn = '<div class="renDer"><span>🌐</span><span class="txt">Chrome · ' + esc(nav.perfil) + '</span></div>';
      if (nav.url) cn += '<div class="notaDer txt" title="' + esc(nav.url) + '">' + esc(nav.url) + '</div>';
      cn += nav.foto && window.Pasos && Pasos.fotoHtml ? Pasos.fotoHtml(nav.foto)
          : '<div class="notaDer">Todavía no usó el navegador en esta charla.</div>';
      h += tarjeta('navegador', 'Navegador', '', cn);
    }
    return h;
  }

  // ⚠ Solo se reescribe si cambió algo: si no, la foto parpadea en cada refresco y un
  // toque en la llave se pierde a mitad de camino.
  // ⚠ Y lo que estás escribiendo en la caja de "Enlaces y archivos" sobrevive al redibujo: se
  // guarda el texto, el foco y dónde estaba el cursor, y se devuelven. NO se saltea el
  // redibujo con la caja llena: así era al principio y, con un enlace rechazado esperando que
  // lo corrijas, la columna entera quedaba congelada (sin el aviso, sin la × y sin Contexto).
  function pintar(caja, r, u) {
    const h = html(r, u);
    if (caja.dataset.html === h) return;
    const inp = caja.querySelector('.fijForm input');
    const valor = inp ? inp.value : '';
    const tenia = !!inp && document.activeElement === inp;
    const desde = tenia ? inp.selectionStart : null, hasta = tenia ? inp.selectionEnd : null;
    caja.innerHTML = h; caja.dataset.html = h;
    const n = caja.querySelector('.fijForm input');
    if (!n) return;
    if (valor) n.value = valor;
    if (tenia) { n.focus(); try { n.setSelectionRange(desde, hasta); } catch (e) {} }
  }

  async function mandarFij(que, datos) {
    const r = await fetch('/fijados/' + que, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(datos)});
    try { return await r.json(); } catch (e) { return {ok: false, error: 'El panel no contestó.'}; }
  }

  document.addEventListener('submit', async e => {
    const form = e.target.closest && e.target.closest('.entornoCaja .fijForm');
    if (!form) return;
    e.preventDefault();
    const u = cfg.ubicacion();
    const inp = form.querySelector('input');
    const texto = (inp.value || '').trim();
    if (!u || !u.cwd || !texto || inp.readOnly) return;
    const ambito = form.dataset.ambito === 'sesion' ? 'sesion' : 'proyecto';
    inp.readOnly = true;
    let r;
    try { r = await mandarFij('agregar', {cwd: u.cwd, sid: u.sid || '', ambito, texto}); }
    catch (err) { r = {ok: false, error: 'No pude hablar con el panel.'}; }
    inp.readOnly = false;
    if (r.ok) {
      inp.value = '';
      fijEditando = null;
      if (r.repetido) avisar('Ya estaba en la lista.', false, ambito);
    } else avisar(r.error || 'No lo pude agregar.', true, ambito);   // queda abierta, para corregir
    cfg.alCambiar();
  });

  // "+ Agregar" abre la caja ahí mismo; Esc la cierra, y también salir de ella vacía.
  // Una sola caja abierta por vez: abrir la de un apartado cierra la del otro.
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.entornoCaja [data-fij-mas]');
    if (!b) return;
    const vieja = document.querySelector('.entornoCaja .fijForm');
    if (vieja) vieja.outerHTML = '<button type="button" class="fijMas" data-fij-mas="' +
      vieja.dataset.ambito + '">+ Agregar</button>';
    fijEditando = b.dataset.fijMas === 'sesion' ? 'sesion' : 'proyecto';
    b.outerHTML = formFij(fijEditando);
    const n = document.querySelector('.entornoCaja .fijForm input');
    if (n) n.focus();
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !e.target.closest || !e.target.closest('.entornoCaja .fijForm')) return;
    e.preventDefault();
    e.target.value = '';
    cerrarFij();
  });
  document.addEventListener('focusout', e => {
    const inp = e.target.closest && e.target.closest('.entornoCaja .fijForm input');
    if (!inp) return;
    // Un rato después: el redibujo reemplaza la caja y le devuelve el foco, y eso también
    // dispara un focusout. Solo se cierra si de verdad ya nadie la tiene y quedó vacía.
    setTimeout(() => {
      const ahora = document.querySelector('.entornoCaja .fijForm input');
      if (fijEditando && ahora && !ahora.value && document.activeElement !== ahora) cerrarFij();
    }, 150);
  });

  document.addEventListener('toggle', e => {
    const d = e.target && e.target.closest && e.target.closest('.entornoCaja details.tarjDer');
    if (!d) return;
    if (d.open) plegadas.delete(d.dataset.t); else plegadas.add(d.dataset.t);
    localStorage.setItem('sesDerPlegadas', JSON.stringify([...plegadas]));
  }, true);
  // ⚠ Y además en el CLIC del título (2026-11-11). El `toggle` llega un momento después: si
  // en ese medio la columna se redibuja, llega a la tarjeta vieja, que ya no está en la
  // página, y se pierde — la tarjeta reaparecía abierta. El clic llega siempre, antes.
  document.addEventListener('click', e => {
    const s = e.target.closest && e.target.closest('.entornoCaja details.tarjDer > summary');
    if (!s || !s.parentElement.dataset.t) return;
    const d = s.parentElement;
    if (d.open) plegadas.add(d.dataset.t); else plegadas.delete(d.dataset.t);   // el que VA a quedar
    localStorage.setItem('sesDerPlegadas', JSON.stringify([...plegadas]));
  }, true);

  // Abrir un archivo (en la compu) o sacar una fila de la lista.
  document.addEventListener('click', async e => {
    const ab = e.target.closest && e.target.closest('.entornoCaja [data-fij-abrir]');
    const qu = e.target.closest && e.target.closest('.entornoCaja [data-fij-quitar]');
    if (!ab && !qu) return;
    e.preventDefault();
    const u = cfg.ubicacion();
    if (!u || !u.cwd) return;
    const ambito = (ab || qu).dataset.amb === 'sesion' ? 'sesion' : 'proyecto';
    const donde = {cwd: u.cwd, sid: u.sid || '', ambito};
    let r;
    try {
      r = ab ? await mandarFij('abrir', Object.assign({id: ab.dataset.fijAbrir}, donde))
             : await mandarFij('quitar', Object.assign({id: qu.dataset.fijQuitar}, donde));
    } catch (err) { r = {ok: false, error: 'No pude hablar con el panel.'}; }
    if (!r.ok) avisar(r.error || 'No se pudo.', true, ambito);
    else if (ab) avisar(r.aviso || 'Abierto en la compu.', false, ambito);
    cfg.alCambiar();
  });

  document.addEventListener('click', async e => {
    const b = e.target.closest && e.target.closest('.entornoCaja [data-remoto]');
    if (!b || b.classList.contains('yendo')) return;
    const u = cfg.ubicacion();
    if (!u || !u.sid) return;
    const prender = !b.classList.contains('on');
    b.classList.add('yendo');
    try {
      const r = await (await fetch('/movil/remoto', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cwd: u.cwd, sid: u.sid, prender, nombre: u.nombre || ''})})).json();
      if (!r.ok) alert(r.error || 'No pude cambiar el control remoto.');
    } catch (err) { alert('No pude hablar con el panel.'); }
    b.classList.remove('yendo');
    cfg.alCambiar();
  });

  window.Entorno = {iniciar: c => { cfg = Object.assign(cfg, c || {}); }, pedir, html, pintar};
})();
