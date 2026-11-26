// ⭐ La pieza VISTA de la columna derecha (2026-11-16): los PDF y las fotos de la charla
// abierta, para mirarlos SIN salir del panel. Pedido de Martín: "si una sesión me crea un PDF o
// me muestra una imagen, me gustaría poder verlo acá".
//
//   Vista.iniciar({ubicacion, agrandar});    ubicacion() -> {cwd, sid, nombre} | null
//   Vista.mostrar(caja);   Vista.ocultar();
//
// La lista la arma el panel (`app/voz/vista.py`) leyendo la charla: lo que la sesión creó,
// abrió, nombró, o lo que vos le pasaste. Acá solo se dibuja:
//  · Una grilla con lo más nuevo primero; tocar uno lo abre en grande (la foto entera, o el PDF
//    en el visor del navegador). ‹ › pasan al de al lado, Esc vuelve a la grilla.
//  · Se pide de a UN pedido por vez y solo con la pieza a la vista: escondida no gasta nada.
//  · ⚠ Los archivos se piden por su CÓDIGO (`id`), nunca por la ruta: el panel solo sirve lo que
//    esa charla nombró. La ruta se muestra, pero no viaja.
//  · Lo que apareció desde la última vez que miraste lleva un aro: es "lo nuevo" sin robarte la
//    pantalla (abrirlo solo, en medio de otra cosa, sería peor que no avisar).
(function () {
  let cfg = {ubicacion: () => null, agrandar: null};
  let caja = null, visible = false, reloj = null, pidiendo = false;
  let sid = '', cwd = '', archivos = [], firma = '', abierto = '', filtro = 'todo';
  let error = '', cargado = false;
  let aviso = null;                       // {texto, mal, deshacer: id} — el renglón de abajo
  let relojAviso = null, menu = null, armada = '', relojArmada = null;
  const vistos = {};                      // sid -> Set de ids ya vistos (para el aro de "nuevo")

  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                                             .replace(/"/g, '&quot;');
  const url = (a) => '/vista/crudo?cwd=' + encodeURIComponent(cwd) + '&sid=' + encodeURIComponent(sid) +
                     '&id=' + encodeURIComponent(a.id);
  const peso = b => b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(0) + ' kB'
                  : (b / 1048576).toFixed(1).replace('.', ',') + ' MB';
  function hace(iso) {
    const t = Date.parse(iso || '');
    if (!t) return '';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 60) return 'recién';
    if (s < 3600) return 'hace ' + Math.round(s / 60) + ' min';
    if (s < 86400) return 'hace ' + Math.round(s / 3600) + ' h';
    return new Date(t).toLocaleDateString('es-AR', {day: 'numeric', month: 'short'});
  }
  const COMO = {'creó': 'la creó la sesión', 'abrió': 'la abrió la sesión',
                'tuya': 'la mandaste vos', 'nombró': 'la nombró la sesión'};

  const css = document.createElement('style');
  css.textContent = `
    .vsta{display:flex;flex-direction:column;height:100%;min-height:0;font-size:13px;color:#9aa3b5}
    .vsta .vsBarra{flex:none;display:flex;align-items:center;gap:6px;margin-bottom:10px;min-width:0}
    .vsta .vsBarra .hueco{flex:1}
    .vsta .vsTit{color:#e6e9ef;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .vsta .vsCuenta{font-size:12px;color:#8a93a6;white-space:nowrap}
    .vsta button.vsB{appearance:none;background:none;border:1px solid var(--rastro-borde,#273042);
      border-radius:7px;color:#c9d4ea;font:inherit;font-size:12.5px;padding:3px 9px;cursor:pointer;white-space:nowrap}
    .vsta button.vsB:hover{border-color:#5b8def;color:#e6e9ef}
    .vsta button.vsB.on{border-color:#5b8def;color:#8fb4ff}
    .vsta button.vsB[disabled]{opacity:.35;cursor:default}
    .vsta a.vsB{border:1px solid var(--rastro-borde,#273042);border-radius:7px;color:#c9d4ea;
      font-size:12.5px;padding:3px 9px;text-decoration:none;white-space:nowrap}
    .vsta a.vsB:hover{border-color:#5b8def;color:#e6e9ef}
    .vsta .vsNota{font-size:12.5px;line-height:1.5;padding:18px 6px;text-align:center}
    .vsta .vsNota b{color:#c9d4ea;font-weight:600}
    .vsta .vsGrilla{flex:1 1 0;min-height:0;overflow:auto;display:grid;gap:10px;align-content:start;
      grid-template-columns:repeat(auto-fill,minmax(130px,1fr));padding:2px}
    .vsta .vsTarj{appearance:none;background:rgba(255,255,255,.03);border:1px solid var(--rastro-borde,#273042);
      border-radius:10px;padding:0;overflow:hidden;cursor:pointer;text-align:left;font:inherit;color:inherit;
      display:flex;flex-direction:column;min-width:0}
    .vsta .vsTarj:hover{border-color:#5b8def}
    .vsta .vsTarj.nuevo{box-shadow:0 0 0 2px #5b8def}
    .vsta .vsMini{height:110px;display:flex;align-items:center;justify-content:center;
      background:rgba(0,0,0,.18);overflow:hidden}
    .vsta .vsMini img{width:100%;height:100%;object-fit:cover;display:block}
    .vsta .vsMini .pdf{font-size:34px;line-height:1;display:flex;flex-direction:column;align-items:center;gap:4px}
    .vsta .vsMini .pdf small{font-size:10.5px;letter-spacing:.08em;color:#e5a04b;font-weight:700}
    .vsta .vsPie{padding:6px 8px 7px;min-width:0}
    .vsta .vsNom{color:#e6e9ef;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .vsta .vsDe{font-size:11px;color:#8a93a6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .vsta .vsLienzo{flex:1 1 0;min-height:0;display:flex;align-items:center;justify-content:center;overflow:auto;
      border-radius:10px;background:rgba(0,0,0,.22)}
    .vsta .vsLienzo img{max-width:100%;max-height:100%;object-fit:contain;display:block}
    .vsta .vsLienzo iframe{width:100%;height:100%;border:0;border-radius:10px;background:#fff}
    .vsta .vsRuta{flex:none;font-size:11px;color:#8a93a6;margin-top:6px;overflow:hidden;text-overflow:ellipsis;
      white-space:nowrap;direction:rtl;text-align:left}
    /* El ⋯ de cada tarjeta: se ve al pasar el mouse (y siempre en pantallas táctiles). */
    .vsta .vsTarj{position:relative}
    .vsta .vsMas{position:absolute;top:6px;right:6px;width:26px;height:22px;border-radius:7px;display:flex;
      align-items:center;justify-content:center;background:rgba(10,14,22,.72);color:#e6e9ef;font-size:15px;
      line-height:1;opacity:0;transition:opacity .12s}
    .vsta .vsTarj:hover .vsMas,.vsta .vsTarj:focus-visible .vsMas{opacity:1}
    @media (hover:none){.vsta .vsMas{opacity:1}}
    .vsta .vsMas:hover{background:#5b8def}
    .vsMenu{position:fixed;z-index:9999;min-width:210px;padding:5px;border-radius:10px;
      background:rgba(18,23,34,.97);border:1px solid var(--rastro-borde,#273042);box-shadow:0 10px 30px rgba(0,0,0,.45);
      font-size:13px;color:#c9d4ea;backdrop-filter:blur(12px)}
    .vsMenu button{appearance:none;display:block;width:100%;text-align:left;background:none;border:0;border-radius:7px;
      color:inherit;font:inherit;padding:7px 10px;cursor:pointer}
    .vsMenu button:hover{background:rgba(91,141,239,.16);color:#e6e9ef}
    .vsMenu button.armada{color:var(--pregunta,#e5a04b);background:rgba(229,160,75,.12)}
    .vsMenu hr{border:0;border-top:1px solid var(--rastro-borde,#273042);margin:4px 2px}
    .vsMenu small{display:block;font-size:11px;color:#8a93a6;margin-top:1px}
    .vsta .vsAviso{flex:none;display:flex;align-items:center;gap:10px;margin-top:8px;padding:7px 10px;border-radius:8px;
      background:rgba(91,141,239,.12);color:#c9d4ea;font-size:12.5px}
    .vsta .vsAviso.mal{background:rgba(229,90,90,.14);color:#f0b4b4}
    .vsta .vsAviso .hueco{flex:1}
    .vsta .vsAviso button{appearance:none;background:none;border:0;color:#8fb4ff;font:inherit;cursor:pointer;padding:0}
  `;
  document.head.appendChild(css);

  function lugar() {
    let u = null;
    try { u = cfg.ubicacion && cfg.ubicacion(); } catch (e) { u = null; }
    return u || {cwd: '', sid: ''};
  }

  async function pedir() {
    if (!visible || pidiendo || document.visibilityState === 'hidden') return;
    const u = lugar();
    if (u.sid !== sid || u.cwd !== cwd) {         // cambió la charla: se arranca de cero
      sid = u.sid || ''; cwd = u.cwd || ''; archivos = []; abierto = ''; cargado = false; error = '';
      dibujar();
    }
    if (!sid) { cargado = true; dibujar(); return; }
    pidiendo = true;
    try {
      const r = await fetch('/vista/lista?cwd=' + encodeURIComponent(cwd) + '&sid=' + encodeURIComponent(sid),
                            {cache: 'no-store'});
      if (r.status === 404) { error = 'Falta reiniciar el panel (⟳) para que ande esta pestaña.'; }
      else {
        const d = await r.json();
        if (u.sid === sid) {                       // si cambiaste de charla en el medio, se tira
          error = d.ok ? '' : (d.error || 'No pude leer la charla.');
          archivos = d.archivos || [];
          if (!vistos[sid]) vistos[sid] = new Set(archivos.map(a => a.id));   // la 1ª vez nada es "nuevo"
        }
      }
    } catch (e) { error = 'No pude hablar con el panel.'; }
    pidiendo = false;
    cargado = true;
    dibujar();
  }

  const deFiltro = () => archivos.filter(a => filtro === 'todo' || (filtro === 'pdf' ? a.tipo === 'pdf' : a.tipo !== 'pdf'));

  function dibujar() {
    if (!caja) return;
    const lista = deFiltro();
    const sel = abierto && archivos.find(a => a.id === abierto);
    if (abierto && !sel) abierto = '';             // se borró del disco: vuelve a la grilla
    const f = JSON.stringify([sid, error, cargado, filtro, abierto, archivos.map(a => a.id + a.ts),
                              [...(vistos[sid] || [])].length, aviso]);
    if (f === firma) return;
    firma = f;
    let html = '<div class="vsta">';
    if (sel) {
      const i = lista.findIndex(a => a.id === sel.id);
      html += '<div class="vsBarra">' +
        '<button class="vsB" data-a="volver" title="Volver a todos (Esc)">← Todos</button>' +
        '<button class="vsB" data-a="ant" title="El anterior (←)"' + (i <= 0 ? ' disabled' : '') + '>‹</button>' +
        '<button class="vsB" data-a="sig" title="El siguiente (→)"' + (i < 0 || i >= lista.length - 1 ? ' disabled' : '') + '>›</button>' +
        '<span class="vsTit" title="' + esc(sel.nombre) + '">' + esc(sel.nombre) + '</span><span class="hueco"></span>' +
        '<button class="vsB" data-menu="' + esc(sel.id) + '" title="Quitar de la lista, mandar a la papelera…">⋯</button>' +
        (cfg.agrandar ? '<button class="vsB" data-a="agrandar" title="Agrandar la columna">⤢</button>' : '') +
        '<a class="vsB" href="' + esc(url(sel)) + '" target="_blank" rel="noopener" title="Abrirlo en una pestaña aparte">↗ Aparte</a>' +
        '</div><div class="vsLienzo">' +
        (sel.tipo === 'pdf'
          ? '<iframe src="' + esc(url(sel)) + '#view=FitH" title="' + esc(sel.nombre) + '"></iframe>'
          : '<img src="' + esc(url(sel)) + '" alt="' + esc(sel.nombre) + '">') +
        '</div><div class="vsRuta" title="' + esc(sel.ruta) + '">' + esc(sel.ruta) + '</div>';
    } else {
      const nPdf = archivos.filter(a => a.tipo === 'pdf').length;
      html += '<div class="vsBarra">' +
        ['todo', 'pdf', 'foto'].map(k => '<button class="vsB' + (filtro === k ? ' on' : '') + '" data-f="' + k + '">' +
          (k === 'todo' ? 'Todo' : k === 'pdf' ? 'PDF' : 'Fotos') + '</button>').join('') +
        '<span class="hueco"></span><span class="vsCuenta">' +
        (archivos.length ? archivos.length + (archivos.length === 1 ? ' archivo' : ' archivos') +
          (nPdf ? ' · ' + nPdf + ' PDF' : '') : '') + '</span></div>';
      if (error) html += '<div class="vsNota">' + esc(error) + '</div>';
      else if (!sid) html += '<div class="vsNota">Abrí una charla y acá aparecen los <b>PDF</b> y las <b>fotos</b> que la sesión creó, abrió o te mostró.</div>';
      else if (!cargado) html += '<div class="vsNota">Buscando en la charla…</div>';
      else if (!lista.length) html += '<div class="vsNota">' + (archivos.length
          ? 'No hay ' + (filtro === 'pdf' ? 'PDF' : 'fotos') + ' en esta charla.'
          : 'Esta charla todavía no tiene <b>PDF</b> ni <b>fotos</b>.<br>Cuando la sesión cree uno, te mande una captura o le pases una imagen, aparece acá solo.') + '</div>';
      else {
        const vi = vistos[sid] || new Set();
        html += '<div class="vsGrilla">' + lista.map(a =>
          '<button class="vsTarj' + (vi.has(a.id) ? '' : ' nuevo') + '" data-id="' + esc(a.id) + '" title="' + esc(a.ruta) + '">' +
          '<div class="vsMini">' + (a.tipo === 'pdf'
            ? '<div class="pdf">📄<small>PDF</small></div>'
            : '<img loading="lazy" src="' + esc(url(a)) + '" alt="">') + '</div>' +
          '<span class="vsMas" data-menu="' + esc(a.id) + '" title="Quitar de la lista, mandar a la papelera…">⋯</span>' +
          '<div class="vsPie"><div class="vsNom">' + esc(a.nombre) + '</div>' +
          '<div class="vsDe">' + esc([COMO[a.como] || '', hace(a.cuando)].filter(Boolean).join(' · ')) +
          ' · ' + esc(peso(a.bytes)) + '</div></div></button>').join('') + '</div>';
      }
    }
    if (aviso)
      html += '<div class="vsAviso' + (aviso.mal ? ' mal' : '') + '"><span>' + esc(aviso.texto) + '</span>' +
              '<span class="hueco"></span>' +
              (aviso.deshacer ? '<button data-a="deshacer">Deshacer</button>' : '') + '</div>';
    caja.innerHTML = html + '</div>';
  }

  // --- ⭐ Eliminar (2026-11-16): "quitar de la lista" o "mandar a la papelera" -------------------
  // Martín eligió las dos. Quitar no toca el archivo y se deshace; la papelera lo saca del disco
  // pero a la Papelera de Windows, y pide un SEGUNDO toque (el primero la arma 4 s, en ámbar: el
  // rojo es solo para errores). El panel nunca borra para siempre.
  function avisar(texto, mal, deshacer) {
    aviso = {texto, mal: !!mal, deshacer: deshacer || ''};
    clearTimeout(relojAviso);
    relojAviso = setTimeout(() => { aviso = null; dibujar(); }, deshacer ? 8000 : 6000);
    dibujar();
  }
  async function mandar(que, id) {
    try {
      const r = await fetch('/vista/' + que, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                              body: JSON.stringify({cwd, sid, id})});
      if (r.status === 404) return {ok: false, error: 'Falta reiniciar el panel (⟳) para esto.'};
      return await r.json();
    } catch (e) { return {ok: false, error: 'No pude hablar con el panel.'}; }
  }
  // Se saca de la pantalla AL TOQUE (sin esperar la vuelta de 4 s), y si estaba abierto se pasa
  // al de al lado: borrar mirando uno por uno es justo el uso.
  function sacarDeLaVista(id) {
    const lista = deFiltro(), i = lista.findIndex(a => a.id === id);
    archivos = archivos.filter(a => a.id !== id);
    if (abierto === id) {
      const resto = deFiltro();
      abierto = resto.length ? resto[Math.min(Math.max(i, 0), resto.length - 1)].id : '';
    }
  }
  async function accion(que, id) {
    cerrarMenu();
    const a = archivos.find(x => x.id === id);
    if (!a) return;
    if (que === 'aparte') return void window.open(url(a), '_blank', 'noopener');
    if (que === 'copiar') {
      try { await navigator.clipboard.writeText(a.ruta); avisar('Ruta copiada.'); }
      catch (e) { avisar('No pude copiarla: ' + a.ruta, true); }
      return;
    }
    const d = await mandar(que === 'quitar' ? 'quitar' : 'papelera', id);
    if (!d.ok) return avisar(d.error || 'No se pudo.', true);
    sacarDeLaVista(id);
    if (que === 'quitar') avisar('«' + a.nombre + '» quitado de la lista. El archivo sigue en su carpeta.', false, id);
    else avisar('«' + a.nombre + '» está en la Papelera de Windows: de ahí se recupera.');
  }
  async function deshacer(id) {
    const d = await mandar('devolver', id);
    if (!d.ok) return avisar(d.error || 'No se pudo.', true);
    aviso = null;
    await pedir();
  }

  function cerrarMenu() {
    if (menu) menu.remove();
    menu = null; armada = '';
    clearTimeout(relojArmada);
  }
  function abrirMenu(id, x, y) {
    cerrarMenu();
    const a = archivos.find(z => z.id === id);
    if (!a) return;
    menu = document.createElement('div');
    menu.className = 'vsMenu';
    menu.setAttribute('role', 'menu');
    menu.innerHTML =
      '<button data-m="aparte">↗ Abrir aparte</button>' +
      '<button data-m="copiar">📋 Copiar la ruta</button><hr>' +
      '<button data-m="quitar">Quitar de la lista<small>El archivo queda en su carpeta</small></button>' +
      '<button data-m="papelera">🗑 Mandar a la papelera<small>Se recupera desde la Papelera de Windows</small></button>';
    document.body.appendChild(menu);
    // Que no se salga de la ventana.
    const r = menu.getBoundingClientRect();
    menu.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 6)) + 'px';
    menu.style.top = Math.max(6, Math.min(y, innerHeight - r.height - 6)) + 'px';
    menu.addEventListener('click', e => {
      const b = e.target.closest('button[data-m]');
      if (!b) return;
      e.stopPropagation();
      if (b.dataset.m !== 'papelera') return accion(b.dataset.m, id);
      if (armada === id) return accion('papelera', id);
      armada = id;
      b.classList.add('armada');
      b.innerHTML = '🗑 ¿Seguro? Tocá de nuevo<small>' + esc(a.nombre) + ' va a la Papelera</small>';
      clearTimeout(relojArmada);
      relojArmada = setTimeout(() => {
        if (!menu || armada !== id) return;
        armada = '';
        b.classList.remove('armada');
        b.innerHTML = '🗑 Mandar a la papelera<small>Se recupera desde la Papelera de Windows</small>';
      }, 4000);
    });
  }
  // Un toque afuera del menú, o mover la página, lo cierra.
  document.addEventListener('pointerdown', e => { if (menu && !menu.contains(e.target)) cerrarMenu(); }, true);
  addEventListener('resize', cerrarMenu);
  document.addEventListener('scroll', e => { if (menu && !menu.contains(e.target)) cerrarMenu(); }, true);

  function abrir(id) {
    abierto = id;
    (vistos[sid] = vistos[sid] || new Set()).add(id);
    dibujar();
  }
  function correr(paso) {
    const lista = deFiltro(), i = lista.findIndex(a => a.id === abierto);
    if (i < 0) return;
    const otro = lista[i + paso];
    if (otro) abrir(otro.id);
  }

  function alClic(e) {
    const m = e.target.closest('[data-menu]');
    if (m && caja.contains(m)) {
      e.stopPropagation();
      const r = m.getBoundingClientRect();
      return abrirMenu(m.dataset.menu, r.right - 210, r.bottom + 4);
    }
    const t = e.target.closest('[data-id],[data-a],[data-f]');
    if (!t || !caja.contains(t)) return;
    if (t.dataset.a === 'deshacer') return deshacer(aviso && aviso.deshacer);
    if (t.dataset.id) return abrir(t.dataset.id);
    if (t.dataset.f) { filtro = t.dataset.f; return dibujar(); }
    const a = t.dataset.a;
    if (a === 'volver') { abierto = ''; dibujar(); }
    else if (a === 'ant') correr(-1);
    else if (a === 'sig') correr(1);
    else if (a === 'agrandar' && cfg.agrandar) cfg.agrandar();
  }
  // El teclado solo cuenta con un archivo abierto y sin estar escribiendo en otro lado.
  function alTecla(e) {
    if (menu && e.key === 'Escape') { cerrarMenu(); e.preventDefault(); return; }
    if (!visible || !abierto || e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (/INPUT|TEXTAREA|SELECT/.test(tag) || (document.activeElement && document.activeElement.isContentEditable)) return;
    if (e.key === 'Escape') { abierto = ''; dibujar(); }
    else if (e.key === 'ArrowLeft') correr(-1);
    else if (e.key === 'ArrowRight') correr(1);
    else return;
    e.preventDefault();
  }
  document.addEventListener('keydown', alTecla);

  function mostrar(c) {
    if (caja !== c) {
      caja = c;
      caja.addEventListener('click', alClic);
      // Botón derecho sobre una tarjeta o sobre lo que se está mirando: el mismo menú del ⋯.
      caja.addEventListener('contextmenu', e => {
        const t = e.target.closest('.vsTarj[data-id], .vsLienzo');
        if (!t || !caja.contains(t)) return;
        const id = t.dataset.id || abierto;
        if (!id) return;
        e.preventDefault();
        abrirMenu(id, e.clientX, e.clientY);
      });
      firma = '';
    }
    visible = true;
    pedir();
    clearInterval(reloj);
    reloj = setInterval(pedir, 4000);
  }
  function ocultar() {
    visible = false;
    cerrarMenu();
    clearInterval(reloj);
    reloj = null;
    // Lo que se vio con la pieza abierta deja de ser "nuevo" la próxima vez.
    if (sid) vistos[sid] = new Set(archivos.map(a => a.id));
  }

  window.Vista = {iniciar: c => { cfg = Object.assign(cfg, c || {}); }, mostrar, ocultar,
                  _estado: () => ({sid, cwd, archivos, abierto, filtro})};
})();
