// ⭐ La terminal adentro del panel (2026-11-10). Martín: *"hay cosas de Claude Code que
// podríamos agregar a este panel, como la terminal o el navegador dentro del mismo panel"*.
// Es una pieza de la columna de la derecha de /sesiones (ver `Paneles` en sesiones.html):
//
//   Consola.iniciar({ubicacion: () => ({cwd}), traer, alChat(texto), agrandar});
//   Paneles.registrar({id: 'terminal', …, alMostrar: Consola.mostrar, alOcultar: Consola.ocultar});
//   Consola.escribir(texto, cwd)     ← el ▶ de un bloque de código
//
// El lado del servidor es `app/voz/terminales.py`: cada terminal es un programa de terminal
// de verdad (PowerShell, CMD, Git Bash) que vive en el panel. Esta pieza solo la DIBUJA (con
// xterm.js, copiado a `estaticos/terceros/`) y le pasa las teclas por un WebSocket.
//
// ⭐⭐ SEGUNDA VUELTA (2026-11-10). Martín: *"faltan configuraciones de la terminal, siento
// que nos quedamos cortos si nos comparamos con Claude Code; me gustaría agregarle cosas que
// tiene Cursor también"*. Lo que se sumó:
//  · ⚙ Ajustes (se guardan en `sesTerm`): tamaño y letra, forma y parpadeo del cursor,
//    copiar al seleccionar, clic derecho pega, cuántos renglones recuerda, y con qué
//    programa se abren las nuevas. Ctrl + / Ctrl − / Ctrl 0 agrandan, achican y vuelven.
//  · 🔍 Buscar (Ctrl+F), enlaces que se abren con un clic, renombrar una terminal (doble clic
//    en su pestaña), elegir el programa de cada una (▾ al lado del ＋), y ⤢ agrandar.
//  · Lo de Cursor:
//      - Ctrl+K: describís lo que querés en tus palabras y te ESCRIBE el comando (no lo
//        ejecuta: el Enter sigue siendo tuyo). Lo genera Haiku en el panel, ~8 s y 0,0002
//        dólares por pedido (`/terminal/sugerir`).
//      - Cada comando lleva un puntito al costado, verde si anduvo y rojo si falló. Cuando
//        falla, aparece "Arreglalo con la sesión": arma el mensaje para la charla con el
//        comando y su salida, y lo deja en la caja para que lo mandes vos.
//      - Seleccionás un pedazo y "Mandar a la charla" (o Ctrl+Shift+L) lo pega en la caja.
//      - Ctrl+↑ / Ctrl+↓ saltan de comando en comando.
//    Los puntitos y el "arreglalo" salen de unas marcas invisibles que el PowerShell escribe
//    en cada renglón (`ESC ] 633`, las mismas de VS Code y Cursor). En CMD y Git Bash no
//    hay marcas: ahí no aparecen, lo demás anda igual.
//
// ⚠ Lo que hay que saber antes de tocarla:
//  · Mientras nadie la mira NO gasta nada: `ocultar()` corta el WebSocket y desarma el
//    dibujo. La terminal sigue viva en el servidor, y al volver se le pide lo que escribió
//    mientras tanto (el servidor guarda lo último).
//  · ⚠⚠ El primer mensaje es el REPASO y se dibuja `mudo`: sin contestarle nada al servidor
//    (ver CLAUDE.md, "No romper"). Y los puntitos de los comandos del repaso NO se
//    recalculan: son comandos viejos, ya contados.
//  · La llave (`/terminal/llave`) se pide una vez y viaja en cada pedido. Si el panel se
//    reinicia la llave cambia Y las terminales se pierden: se pide de nuevo y se abre otra.
//  · Las terminales son de una CARPETA. Al cambiar de charla se muestran las de la carpeta
//    de esa charla; las otras siguen abiertas y vuelven cuando volvés.
//  · El ▶ y el Ctrl+K ESCRIBEN y no aprietan Enter: el Enter es tuyo, y es la confirmación.
(function () {
  let cfg = {ubicacion: () => null, traer: () => {}, alChat: () => false, agrandar: () => {}};
  // Las pruebas la sirven desde un servidor chico aparte; el panel, desde sí mismo.
  const BASE = (window.TERMINAL_BASE || '').replace(/\/$/, '');
  const WSBASE = BASE ? BASE.replace(/^http/, 'ws')
                      : (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host;
  let llave = '', hay = null;          // hay: ¿el servidor tiene con qué abrir terminales?
  let shells = [];                     // los programas que se pueden abrir, según el servidor
  let sugerirHay = false;              // ¿el panel ya sabe generar comandos (Ctrl+K)?
  let caja = null, visible = false;
  let carpeta = null;                  // la carpeta cuyas terminales se están mostrando
  let lista = [];                      // las terminales de esa carpeta, según el servidor
  let actual = '';                     // la que se ve
  let xt = null, ajuste = null, buscador = null, ws = null, mirador = null, reloj = 0, vuelta = 0;
  let pendiente = '';                  // lo que el ▶ quiere pegar apenas haya dónde
  let relojPegar = 0;
  let mudo = false;                    // dibujando el repaso: no se le contesta nada al servidor
  let ultima = 0;                      // cuándo llegó lo último que escribió la terminal
  let comandos = [];                   // los de la terminal que se ve: {marca, cmd, codigo}
  let enCurso = null;                  // el que se está tipeando o corriendo: {marca, col}
  let fallo = null;                    // el último que falló, para "arreglalo con la sesión"

  // --- Los ajustes ---------------------------------------------------------------------------
  const FABRICA = {tam: 13, letra: 'cascadia', cursor: 'block', parpadeo: true, copiarSel: false,
                   clicDerPega: true, memoria: 5000, shell: 'pwsh', marcas: true};
  const LETRAS = {cascadia: '"Cascadia Mono","Cascadia Code",Consolas,monospace',
                  consolas: 'Consolas,"Cascadia Mono",monospace',
                  jetbrains: '"JetBrains Mono","Cascadia Mono",Consolas,monospace',
                  estilo: ''};
  let aj = Object.assign({}, FABRICA);
  try { Object.assign(aj, JSON.parse(localStorage.getItem('sesTerm') || '{}')); } catch (e) {}
  const guardarAj = () => localStorage.setItem('sesTerm', JSON.stringify(aj));
  let nombres = {};
  try { nombres = JSON.parse(localStorage.getItem('sesTermNombres') || '{}'); } catch (e) {}
  const guardarNombres = () => localStorage.setItem('sesTermNombres', JSON.stringify(nombres));

  const css = document.createElement('style');
  css.textContent = `
    .derPane[data-pieza="terminal"]{padding:0;display:flex;flex-direction:column;overflow:hidden;
      position:relative}
    .derPane[data-pieza="terminal"][hidden]{display:none}
    .conCab{flex:none;display:flex;align-items:center;gap:4px;padding:8px 10px 6px 12px;min-width:0;
      position:relative}
    .conTabs{display:flex;gap:4px;min-width:0;overflow:hidden}
    .conTab,.conMas,.conBot{appearance:none;border:1px solid transparent;background:none;cursor:pointer;
      font:inherit;font-size:12px;line-height:1;color:inherit;opacity:.62;border-radius:7px;
      padding:5px 8px;display:inline-flex;align-items:center;gap:6px;white-space:nowrap;
      transition:opacity .15s ease-out,background-color .15s ease-out}
    .conTab:hover,.conMas:hover,.conBot:hover,.conBot.on{opacity:1;background:rgba(127,127,127,.14)}
    .conTab.sel{opacity:1;background:rgba(127,127,127,.2);font-weight:600}
    .conTab .x{opacity:.55;font-size:11px}
    .conTab .x:hover{opacity:1}
    .conTab .sh{font-weight:400;opacity:.6;font-size:11px}
    .conTab input{width:9em;font:inherit;font-size:12px;color:inherit;background:rgba(127,127,127,.18);
      border:1px solid rgba(127,127,127,.45);border-radius:5px;padding:1px 4px}
    .conMasSh{padding:5px 4px;margin-left:-4px}
    .conDonde{flex:1 1 auto;font-size:11.5px;opacity:.55;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis;min-width:0;direction:rtl;text-align:right;margin:0 4px}
    .conCuerpo{flex:1 1 auto;min-height:0;position:relative;margin:0 8px 10px;
      padding:8px 2px 6px 10px;border-radius:12px;
      background:color-mix(in srgb,var(--fondo,#0b1020) 62%,transparent)}
    .conCuerpo .xterm{height:100%}
    /* ⚠ La capa de los puntitos de xterm se sale del cuadro (mide todo lo guardado, no lo
       que se ve) y tapaba los botones de abajo, como "Arreglalo con la sesión". */
    .conCuerpo{overflow:hidden}
    .conCuerpo .xterm-decoration-container{pointer-events:none}
    .conCuerpo .xterm-viewport{background:transparent !important}
    .conNota{flex:none;padding:8px 14px 14px;font-size:12.5px;opacity:.75;line-height:1.4}
    .conNota:empty{display:none}
    .conNota button,.conBarra button,.conMenu button.op{appearance:none;font:inherit;font-size:12.5px;
      cursor:pointer;color:inherit;background:none;border:1px solid rgba(127,127,127,.4);
      border-radius:8px;padding:5px 11px}
    .conNota button{margin-top:8px}
    .conNota button:hover,.conBarra button:hover,.conMenu button.op:hover{background:rgba(127,127,127,.16)}
    /* Lo que flota abajo de la terminal: buscar, pedir un comando, "falló", "mandar a la charla". */
    /* ⚠⚠ FLOTAN encima de la terminal, no le roban lugar. La primera versión las ponía
       debajo: al aparecer "Mandar a la charla" la terminal se achicaba, xterm se volvía a
       medir y al medirse BORRA la selección — o sea que la barra se borraba a sí misma. */
    .conFlota{position:absolute;left:16px;right:16px;bottom:20px;z-index:6;display:flex;
      flex-direction:column;gap:6px;pointer-events:none}
    .conBarra{display:flex;align-items:center;gap:8px;padding:6px 8px;pointer-events:auto;
      border-radius:10px;font-size:12.5px;backdrop-filter:blur(10px);
      background:color-mix(in srgb,var(--ct-pieza,var(--c151b26,#151b26)) 88%,transparent);
      border:1px solid rgba(127,127,127,.28);box-shadow:0 8px 24px -10px rgba(0,0,0,.55)}
    .conBarra[hidden]{display:none}
    .conBarra input{flex:1 1 auto;min-width:0;font:inherit;font-size:13px;color:inherit;
      background:transparent;border:0;outline:0;padding:3px 4px}
    .conBarra .info{opacity:.7;white-space:nowrap}
    .conBarra.mal{background:color-mix(in srgb,var(--mal,#e5534b) 22%,var(--ct-pieza,var(--c151b26,#151b26)))}
    .conBarra .txt{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .conBarra .cerrar{border:0 !important;padding:3px 6px !important;opacity:.6}
    @keyframes conPiensa{0%,100%{opacity:.35}50%{opacity:1}}
    .conBarra.piensa .info{animation:conPiensa 1.2s ease-in-out infinite}
    /* El menú de ajustes y el de elegir programa. */
    .conMenu{position:absolute;top:calc(100% + 2px);right:10px;z-index:20;min-width:250px;
      padding:10px 12px;border-radius:12px;font-size:12.5px;display:grid;gap:9px;
      background:var(--ct-pieza,var(--c151b26,#151b26));border:1px solid rgba(127,127,127,.3);
      box-shadow:0 14px 36px -12px rgba(0,0,0,.6)}
    .conMenu[hidden]{display:none}
    .conMenu .fila{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .conMenu select,.conMenu input[type=number]{font:inherit;font-size:12.5px;color:inherit;
      background:rgba(127,127,127,.14);border:1px solid rgba(127,127,127,.35);border-radius:7px;
      padding:3px 6px;max-width:150px}
    .conMenu input[type=number]{width:64px}
    .conMenu .tit{font-weight:600;opacity:.85}
    .conMenu .ayuda{opacity:.6;font-size:11.5px;line-height:1.4}
    .conMenu.sh{left:auto;min-width:200px;gap:2px;padding:6px}
    .conMenu.sh button{appearance:none;font:inherit;font-size:12.5px;color:inherit;background:none;
      border:0;border-radius:7px;padding:7px 10px;text-align:left;cursor:pointer}
    .conMenu.sh button:hover{background:rgba(127,127,127,.16)}
    /* Los puntitos de cada comando, al costado. */
    .conPunto{width:6px !important;height:6px !important;border-radius:50%;margin:6px 0 0 -8px;
      pointer-events:none}
    .conPunto.ok{background:var(--ok,#3fb950);opacity:.75}
    .conPunto.mal{background:var(--mal,#e5534b)}
    @media (prefers-reduced-motion:reduce){ .conBarra.piensa .info{animation:none} }
  `;
  document.head.appendChild(css);

  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                                             .replace(/"/g, '&quot;');
  const $c = s => caja ? caja.querySelector(s) : null;

  // --- Lo que hay que cargar una sola vez: la biblioteca y la llave ------------------------
  let cargaLib = null;
  function biblioteca() {
    if (cargaLib) return cargaLib;
    const una = (etiqueta, attrs, opcional) => new Promise((si, no) => {
      const e = Object.assign(document.createElement(etiqueta), attrs);
      e.onload = si;
      // Los complementos son opcionales: con un panel sin reiniciar no existen, y la
      // terminal tiene que andar igual (sin buscar ni enlaces).
      e.onerror = () => opcional ? si() : no(new Error('no cargó ' + (attrs.src || attrs.href)));
      document.head.appendChild(e);
    });
    const ter = n => BASE + '/estaticos/terceros/' + n;
    // ⚠ En orden: los complementos se enganchan a la biblioteca ya cargada.
    cargaLib = una('link', {rel: 'stylesheet', href: ter('xterm.css')})
      .then(() => una('script', {src: ter('xterm.js')}))
      .then(() => Promise.all([una('script', {src: ter('xterm-addon-fit.js')}),
                               una('script', {src: ter('xterm-addon-search.js')}, true),
                               una('script', {src: ter('xterm-addon-web-links.js')}, true)]))
      .catch(e => { cargaLib = null; throw e; });
    return cargaLib;
  }
  async function pedirLlave() {
    const r = await (await fetch(BASE + '/terminal/llave', {cache: 'no-store'})).json();
    if (!r.ok) throw new Error(r.error || 'sin llave');
    llave = r.llave;
    hay = !!r.disponible;
    shells = r.shells || [];
    sugerirHay = !!r.sugerir;
  }
  async function pedir(ruta, cuerpo) {
    const hacer = () => fetch(BASE + ruta, cuerpo === undefined
      ? {headers: {'X-Terminal-Llave': llave}, cache: 'no-store'}
      : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Terminal-Llave': llave},
         body: JSON.stringify(cuerpo)});
    if (!llave) await pedirLlave();
    let r = await hacer();
    // El panel se reinició: la llave es otra. Se pide de nuevo, una sola vez.
    if (r.status === 403) { await pedirLlave(); r = await hacer(); }
    if (r.status === 404) return {ok: false, error: 'falta reiniciar el panel para esto', viejo: true};
    return r.json();
  }

  // --- El dibujo de la pieza ---------------------------------------------------------------
  function armar() {
    if (caja.dataset.armada) return;
    caja.dataset.armada = '1';
    caja.innerHTML =
      '<div class="conCab"><div class="conTabs"></div>' +
        '<button type="button" class="conMas" title="Otra terminal en esta carpeta">＋</button>' +
        '<button type="button" class="conMas conMasSh" title="Elegir con qué programa abrirla">▾</button>' +
        '<span class="conDonde"></span>' +
        '<button type="button" class="conBot" data-hace="buscar" title="Buscar (Ctrl+F)">🔍</button>' +
        '<button type="button" class="conBot" data-hace="pedir" title="Describí lo que querés y te escribo el comando (Ctrl+K)">✦</button>' +
        '<button type="button" class="conBot" data-hace="agrandar" title="Agrandar o achicar la columna">⤢</button>' +
        '<button type="button" class="conBot" data-hace="ajustes" title="Ajustes de la terminal">⚙</button>' +
        '<div class="conMenu" data-menu="ajustes" hidden></div>' +
        '<div class="conMenu sh" data-menu="shell" hidden></div>' +
      '</div>' +
      '<div class="conCuerpo"></div><div class="conFlota">' +
      '<div class="conBarra" data-barra="buscar" hidden><span class="info">🔍</span>' +
        '<input type="text" placeholder="Buscar en la terminal… (Enter: siguiente · Shift+Enter: anterior)">' +
        '<span class="info cuenta"></span><button type="button" class="cerrar" title="Cerrar (Esc)">✕</button></div>' +
      '<div class="conBarra" data-barra="pedir" hidden><span class="info">✦</span>' +
        '<input type="text" placeholder="¿Qué querés hacer? Te escribo el comando (Enter · Esc cierra)">' +
        '<button type="button" class="cerrar" title="Cerrar (Esc)">✕</button></div>' +
      '<div class="conBarra" data-barra="sel" hidden><span class="txt">Hay texto seleccionado.</span>' +
        '<button type="button" data-hace="selChat" title="Ctrl+Shift+L">Mandar a la charla</button>' +
        '<button type="button" data-hace="selCopiar">Copiar</button></div>' +
      '<div class="conBarra mal" data-barra="fallo" hidden><span class="txt"></span>' +
        '<button type="button" data-hace="arreglar">Arreglalo con la sesión</button>' +
        '<button type="button" class="cerrar" data-hace="olvidarFallo" title="Cerrar">✕</button></div>' +
      '</div><div class="conNota"></div>';
    $c('.conMas:not(.conMasSh)').onclick = () => abrirOtra();
    $c('.conMasSh').onclick = e => { e.stopPropagation(); menu('shell'); };
    $c('.conTabs').onclick = e => {
      const x = e.target.closest('[data-cerrar]');
      if (x) return cerrar(x.dataset.cerrar);
      const b = e.target.closest('[data-id]');
      if (b && b.dataset.id !== actual && !e.target.closest('input')) ver(b.dataset.id);
    };
    $c('.conTabs').ondblclick = e => {
      const b = e.target.closest('[data-id]');
      if (b && !e.target.closest('[data-cerrar]')) renombrar(b);
    };
    caja.addEventListener('click', e => {
      const b = e.target.closest('[data-hace]');
      if (!b) return;
      const h = b.dataset.hace;
      if (h === 'buscar') abrirBarra('buscar');
      else if (h === 'pedir') abrirBarra('pedir');
      else if (h === 'agrandar') cfg.agrandar();
      else if (h === 'ajustes') { e.stopPropagation(); menu('ajustes'); }
      else if (h === 'selChat') mandarSeleccion();
      else if (h === 'selCopiar') copiarSeleccion();
      else if (h === 'arreglar') arreglar();
      else if (h === 'olvidarFallo') { fallo = null; barra('fallo', false); }
    });
    caja.querySelectorAll('.conBarra .cerrar:not([data-hace])').forEach(b =>
      b.onclick = () => cerrarBarra(b.closest('.conBarra').dataset.barra));
    // Buscar.
    const ib = $c('[data-barra="buscar"] input');
    ib.oninput = () => buscar(ib.value, true, true);
    ib.onkeydown = e => {
      if (e.key === 'Enter') { e.preventDefault(); buscar(ib.value, !e.shiftKey, false); }
      else if (e.key === 'Escape') { e.preventDefault(); cerrarBarra('buscar'); }
    };
    // Pedir un comando.
    const ip = $c('[data-barra="pedir"] input');
    ip.onkeydown = e => {
      if (e.key === 'Enter') { e.preventDefault(); pedirComando(ip.value); }
      else if (e.key === 'Escape') { e.preventDefault(); cerrarBarra('pedir'); }
    };
    $c('.conNota').onclick = e => { if (e.target.closest('[data-abrir]')) abrirOtra(); };
    // Los menús se cierran con un clic afuera o con Escape (y vuelve el foco a la terminal).
    document.addEventListener('click', e => {
      if (caja && !e.target.closest('.conMenu')) caja.querySelectorAll('.conMenu').forEach(m => m.hidden = true);
    });
    caja.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      const abiertos = [...caja.querySelectorAll('.conMenu')].filter(m => !m.hidden);
      if (!abiertos.length) return;
      abiertos.forEach(m => m.hidden = true);
      e.preventDefault();
      if (xt) xt.focus();
    });
  }
  function nota(html) { const n = $c('.conNota'); if (n) n.innerHTML = html || ''; }
  function barra(cual, ver) { const b = $c('[data-barra="' + cual + '"]'); if (b) b.hidden = !ver; return b; }
  function abrirBarra(cual) {
    if (cual === 'pedir' && !sugerirHay)
      return nota('Para pedir comandos con tus palabras falta reiniciar el panel.');
    const b = barra(cual, true);
    if (!b) return;
    const i = b.querySelector('input');
    if (cual === 'buscar' && xt && xt.hasSelection()) i.value = xt.getSelection().split('\n')[0];
    i.focus();
    i.select();
  }
  function cerrarBarra(cual) {
    barra(cual, false);
    if (cual === 'buscar' && buscador) { try { buscador.clearDecorations(); } catch (e) {} }
    if (xt) xt.focus();
  }
  const etiquetaShell = id => ((shells.find(s => s.id === id) || {}).nombre || id || '')
    .replace('Windows PowerShell', 'PS 5').replace('PowerShell 7', 'PS').replace('Símbolo del sistema', 'CMD');
  function pintarTabs() {
    $c('.conTabs').innerHTML = lista.map((t, i) =>
      '<button type="button" class="conTab' + (t.id === actual ? ' sel' : '') + '" data-id="' + esc(t.id) +
      '" title="' + esc(t.cwd) + ' · doble clic para cambiarle el nombre">' +
      esc(nombres[t.id] || String(i + 1)) +
      (t.shell && t.shell !== 'pwsh' ? '<span class="sh">' + esc(etiquetaShell(t.shell)) + '</span>' : '') +
      '<span class="x" data-cerrar="' + esc(t.id) + '" title="Cerrar esta terminal">✕</span></button>').join('');
    const d = $c('.conDonde');
    d.textContent = carpeta || '';
    d.title = carpeta || '';
    const pedirB = $c('[data-hace="pedir"]');
    if (pedirB) pedirB.hidden = !sugerirHay;
    const buscarB = $c('[data-hace="buscar"]');
    if (buscarB) buscarB.hidden = !window.SearchAddon;
  }
  function renombrar(b) {
    const id = b.dataset.id;
    const i = document.createElement('input');
    i.value = nombres[id] || '';
    i.placeholder = 'Nombre';
    b.textContent = '';
    b.appendChild(i);
    i.focus();
    const listo = guardar => {
      if (guardar) { const v = i.value.trim().slice(0, 30); if (v) nombres[id] = v; else delete nombres[id]; guardarNombres(); }
      pintarTabs();
    };
    i.onkeydown = e => { if (e.key === 'Enter') listo(true); else if (e.key === 'Escape') listo(false); };
    i.onblur = () => listo(true);
  }

  // --- Los menús: ajustes y programa ---------------------------------------------------------
  function menu(cual) {
    const m = $c('[data-menu="' + cual + '"]');
    const abrir = m.hidden;
    caja.querySelectorAll('.conMenu').forEach(x => x.hidden = true);
    if (!abrir) return;
    if (cual === 'shell') {
      m.innerHTML = '<div class="ayuda" style="padding:4px 10px 6px">Abrir otra con…</div>' +
        (shells.length ? shells : [{id: 'pwsh', nombre: 'PowerShell 7'}]).map(s =>
          '<button type="button" data-sh="' + esc(s.id) + '">' + esc(s.nombre) +
          (s.id === aj.shell ? ' · la de siempre' : '') + '</button>').join('');
      m.onclick = e => { const b = e.target.closest('[data-sh]'); if (b) { m.hidden = true; abrirOtra(b.dataset.sh); } };
    } else pintarAjustes(m);
    m.hidden = false;
  }
  function pintarAjustes(m) {
    const op = (v, t) => '<option value="' + v + '">' + t + '</option>';
    m.innerHTML =
      '<div class="tit">Ajustes de la terminal</div>' +
      '<label class="fila">Tamaño de letra <input type="number" data-a="tam" min="9" max="24" step="1"></label>' +
      '<label class="fila">Letra <select data-a="letra">' + op('cascadia', 'Cascadia Mono') +
        op('consolas', 'Consolas') + op('jetbrains', 'JetBrains Mono') + op('estilo', 'La del estilo') + '</select></label>' +
      '<label class="fila">Cursor <select data-a="cursor">' + op('block', 'Bloque') + op('bar', 'Barra') +
        op('underline', 'Raya abajo') + '</select></label>' +
      '<label class="fila">Que el cursor parpadee <input type="checkbox" data-a="parpadeo"></label>' +
      '<label class="fila">Copiar al seleccionar <input type="checkbox" data-a="copiarSel"></label>' +
      '<label class="fila">Clic derecho pega <input type="checkbox" data-a="clicDerPega"></label>' +
      '<label class="fila">Renglones que recuerda <select data-a="memoria">' + op('1000', '1.000') +
        op('5000', '5.000') + op('20000', '20.000') + op('50000', '50.000') + '</select></label>' +
      '<label class="fila">Las nuevas se abren con <select data-a="shell">' +
        (shells.length ? shells : [{id: 'pwsh', nombre: 'PowerShell 7'}]).map(s => op(s.id, esc(s.nombre))).join('') +
        '</select></label>' +
      '<label class="fila">Puntito verde/rojo por comando <input type="checkbox" data-a="marcas"></label>' +
      '<div class="ayuda">Atajos: Ctrl+K pedir un comando · Ctrl+F buscar · Ctrl+Shift+L mandar lo ' +
        'seleccionado a la charla · Ctrl+↑/↓ saltar de comando · Ctrl + / Ctrl − / Ctrl 0 tamaño · ' +
        'Ctrl+C con algo seleccionado copia.</div>' +
      '<div class="fila"><span></span><button type="button" class="op" data-volver>Volver a lo de fábrica</button></div>';
    m.querySelectorAll('[data-a]').forEach(c => {
      const k = c.dataset.a;
      if (c.type === 'checkbox') c.checked = !!aj[k]; else c.value = String(aj[k]);
      c.onchange = () => {
        aj[k] = c.type === 'checkbox' ? c.checked : (c.type === 'number' || k === 'memoria') ? +c.value : c.value;
        if (k === 'tam') aj.tam = Math.max(9, Math.min(24, aj.tam || 13));
        guardarAj();
        aplicarAj();
      };
    });
    m.querySelector('[data-volver]').onclick = () => { aj = Object.assign({}, FABRICA); guardarAj(); aplicarAj(); pintarAjustes(m); };
  }
  function opcionesXt() {
    return {fontSize: aj.tam, fontFamily: LETRAS[aj.letra] || getComputedStyle(caja).fontFamily || LETRAS.cascadia,
            cursorStyle: aj.cursor, cursorBlink: !!aj.parpadeo, scrollback: aj.memoria || 5000,
            rightClickSelectsWord: false};
  }
  function aplicarAj() {
    if (!xt) return;
    const o = opcionesXt();
    Object.keys(o).forEach(k => { try { xt.options[k] = o[k]; } catch (e) {} });
    pintarMarcas();
    try { ajuste.fit(); } catch (e) {}
  }

  // La letra y el cursor salen del estilo que esté puesto: la terminal no trae los suyos.
  // El fondo de xterm va transparente y el que se ve es el de `.conCuerpo`, que es el color
  // de fondo del estilo a medio tapar: con Vidrio la columna es casi transparente, y una
  // terminal sobre una foto clara no se lee (se vio en la primera captura).
  // ⚠ Sobre un fondo oscuro, tres de los colores de fábrica de una terminal (negro, gris y
  // azul) están pensados para una ventana NEGRA y acá se pierden: van aclarados. Con el tema
  // claro quedan los de fábrica.
  function tema() {
    const cs = getComputedStyle(caja), raiz = document.documentElement;
    const acento = getComputedStyle(raiz).getPropertyValue('--acento').trim();
    const t = {foreground: cs.color, background: 'rgba(0,0,0,0)', cursor: acento || cs.color,
               cursorAccent: 'rgba(0,0,0,.6)', selectionBackground: 'rgba(127,160,255,.35)'};
    if (!raiz.classList.contains('tema-claro'))
      Object.assign(t, {black: '#232b3d', brightBlack: '#8f9bb0', blue: '#6ea8ff', brightBlue: '#a3c8ff'});
    return t;
  }
  // Cambiaste el estilo o un color en el 🎨 con la terminal a la vista: toma los nuevos.
  window.addEventListener('aspecto-aplicado', () => {
    if (xt && caja) { try { xt.options.theme = tema(); if (aj.letra === 'estilo') aplicarAj(); } catch (e) {} }
  });

  // --- Copiar, pegar, mandar a la charla -----------------------------------------------------
  async function copiarSeleccion() {
    if (!xt || !xt.hasSelection()) return false;
    try { await navigator.clipboard.writeText(xt.getSelection()); } catch (e) { return false; }
    return true;
  }
  function bloque(texto) { return '```\n' + String(texto).replace(/\s+$/, '') + '\n```'; }
  function mandarSeleccion() {
    if (!xt || !xt.hasSelection()) return;
    const hecho = cfg.alChat('De la terminal (' + (carpeta || '') + '):\n' + bloque(xt.getSelection()) + '\n');
    if (!hecho) nota('Abrí una charla para mandarle esto.');
    else { xt.clearSelection(); barra('sel', false); }
  }
  // "Arreglalo con la sesión" (el "Debug with AI" de Cursor): arma el mensaje y lo DEJA en la
  // caja. No lo manda: el Enter es tuyo, y antes de mandarlo podés agregarle algo.
  function arreglar() {
    if (!fallo) return;
    const msg = 'Este comando falló en la terminal (código ' + fallo.codigo + ', carpeta ' + (carpeta || '') +
                '):\n' + bloque(fallo.cmd) + '\nLo que mostró:\n' + bloque(fallo.salida || '(nada)') +
                '\n¿Qué pasó y cómo lo arreglo?';
    if (cfg.alChat(msg)) { fallo = null; barra('fallo', false); }
    else nota('Abrí una charla para pedirle que lo arregle.');
  }

  // --- Buscar ----------------------------------------------------------------------------
  function buscar(q, adelante, incremental) {
    if (!buscador || !q) { $c('[data-barra="buscar"] .cuenta').textContent = ''; return; }
    const o = {incremental, decorations: {matchOverviewRuler: '#888', activeMatchColorOverviewRuler: '#ffd60a',
               matchBackground: '#ffd60a55', activeMatchBackground: '#ffd60aaa'}};
    const hallo = adelante ? buscador.findNext(q, o) : buscador.findPrevious(q, o);
    if (!hallo) $c('[data-barra="buscar"] .cuenta').textContent = 'no está';
  }

  // --- Pedir un comando (Ctrl+K) -----------------------------------------------------------
  function pantalla(renglones) {
    if (!xt) return '';
    const b = xt.buffer.active, fin = b.baseY + b.cursorY, ini = Math.max(0, fin - renglones);
    const out = [];
    for (let i = ini; i <= fin; i++) { const l = b.getLine(i); if (l) out.push(l.translateToString(true)); }
    return out.join('\n');
  }
  async function pedirComando(q) {
    q = (q || '').trim();
    if (!q) return;
    const b = barra('pedir', true), i = b.querySelector('input');
    const t = lista.find(x => x.id === actual) || {};
    b.classList.add('piensa');
    b.querySelector('.info').textContent = '✦ pensando…';
    i.disabled = true;
    let r;
    try { r = await pedir('/terminal/sugerir', {pedido: q, shell: t.shell || 'pwsh', cwd: carpeta || '', pantalla: pantalla(40)}); }
    catch (e) { r = {ok: false, error: 'no pude hablar con el panel'}; }
    b.classList.remove('piensa');
    b.querySelector('.info').textContent = '✦';
    i.disabled = false;
    if (!r.ok || !r.comando) { i.value = ''; i.placeholder = r.error || 'No me salió. Probá decirlo de otra forma.'; i.focus(); return; }
    if (r.comando.startsWith('#')) { i.value = ''; i.placeholder = r.comando.replace(/^#\s*/, ''); i.focus(); return; }
    i.value = '';
    cerrarBarra('pedir');
    pegar(r.comando);
  }

  // --- Los comandos: dónde empieza y termina cada uno (marcas 633) ----------------------------
  function engancharMarcas() {
    if (!xt.parser || !xt.parser.registerOscHandler) return;
    xt.parser.registerOscHandler(633, datos => {
      const [que, valor] = String(datos).split(';');
      if (que === 'B') {
        // Empieza lo que tipeás: acá se anota dónde, para leer el comando cuando termine.
        // ⚠ Con un renglón de entrada que llena justo el ancho, el cursor queda "pasado" del
        // borde (en la columna que no existe) y la primera letra que tipeás va en la última
        // columna de ESE renglón: sin el tope, el comando perdía su primera letra.
        enCurso = {marca: xt.registerMarker(0), col: Math.min(xt.buffer.active.cursorX, xt.cols - 1)};
      } else if (que === 'D' && enCurso) {
        terminoComando(enCurso, valor === undefined ? null : +valor);
        enCurso = null;
      }
      return true;
    });
  }
  function terminoComando(ec, codigo) {
    const b = xt.buffer.active;
    if (!ec.marca || ec.marca.isDisposed || ec.marca.line < 0) return;
    const fin = b.baseY + b.cursorY;
    // El comando: desde donde empezó a tipearse, más los renglones que se le pegaron.
    let i = ec.marca.line, cmd = (b.getLine(i) || {translateToString: () => ''}).translateToString(true).slice(ec.col);
    while (i + 1 < fin && b.getLine(i + 1) && b.getLine(i + 1).isWrapped) {
      i++; cmd += b.getLine(i).translateToString(true);
    }
    cmd = cmd.trim();
    if (!cmd) { ec.marca.dispose(); return; }              // un Enter en blanco no cuenta
    const salida = [];
    for (let j = i + 1; j < fin; j++) { const l = b.getLine(j); if (l) salida.push(l.translateToString(true)); }
    const c = {marca: ec.marca, cmd, codigo, salida: salida.join('\n').replace(/\s+$/, '').slice(-8000), deco: null};
    comandos.push(c);
    if (comandos.length > 500) { const v = comandos.shift(); try { v.deco && v.deco.dispose(); } catch (e) {} }
    pintarMarca(c);
    if (mudo) return;                                      // del repaso: ya pasó, no se avisa
    if (codigo) {
      fallo = c;
      const t = barra('fallo', true);
      t.querySelector('.txt').textContent = '✕ «' + cmd.slice(0, 80) + '» falló (código ' + codigo + ')';
    } else if (fallo) { fallo = null; barra('fallo', false); }
  }
  function pintarMarca(c) {
    try { c.deco && c.deco.dispose(); } catch (e) {}
    c.deco = null;
    if (!aj.marcas || c.codigo === null || !xt.registerDecoration) return;
    const d = xt.registerDecoration({marker: c.marca, x: 0, width: 1, layer: 'top'});
    if (!d) return;
    // ⚠ Con `classList`, no pisando `className`: xterm le pone su propia clase al elemento
    // (`xterm-decoration`) y es la que lo ubica en su renglón. Pisándola, el puntito existía
    // pero caía debajo de toda la terminal, donde nadie lo veía.
    d.onRender(el => { el.classList.add('conPunto');
                       el.classList.toggle('mal', !!c.codigo); el.classList.toggle('ok', !c.codigo);
                       el.title = c.codigo ? 'Falló (código ' + c.codigo + ')' : 'Anduvo'; });
    c.deco = d;
  }
  function pintarMarcas() { comandos.forEach(pintarMarca); }
  function saltarComando(arriba) {
    const b = xt.buffer.active, desde = b.viewportY;
    const vivos = comandos.filter(c => !c.marca.isDisposed && c.marca.line >= 0).map(c => c.marca.line);
    const destino = arriba ? vivos.filter(l => l < desde).pop() : vivos.find(l => l > desde);
    if (destino !== undefined) xt.scrollToLine(destino); else if (!arriba) xt.scrollToBottom();
  }

  // --- Las teclas que son de la página y no de la terminal -----------------------------------
  function teclas(e) {
    if (e.type !== 'keydown') return true;
    const ctrl = e.ctrlKey || e.metaKey, k = (e.key || '').toLowerCase();
    if (ctrl && !e.shiftKey && !e.altKey && k === 'k') { e.preventDefault(); abrirBarra('pedir'); return false; }
    if (ctrl && !e.shiftKey && !e.altKey && k === 'f' && buscador) { e.preventDefault(); abrirBarra('buscar'); return false; }
    if (ctrl && e.shiftKey && k === 'l') { e.preventDefault(); mandarSeleccion(); return false; }
    // Ctrl+C con algo seleccionado COPIA (como en la Terminal de Windows); sin selección
    // sigue siendo cortar el programa que corre.
    if (ctrl && !e.shiftKey && k === 'c' && xt.hasSelection()) { e.preventDefault(); copiarSeleccion(); xt.clearSelection(); return false; }
    if (ctrl && e.shiftKey && k === 'c') { e.preventDefault(); copiarSeleccion(); return false; }
    if (ctrl && !e.altKey && (k === '=' || k === '+')) { e.preventDefault(); tamano(+1); return false; }
    if (ctrl && !e.altKey && k === '-') { e.preventDefault(); tamano(-1); return false; }
    if (ctrl && !e.altKey && k === '0') { e.preventDefault(); aj.tam = FABRICA.tam; guardarAj(); aplicarAj(); return false; }
    if (ctrl && !e.shiftKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) { e.preventDefault(); saltarComando(e.key === 'ArrowUp'); return false; }
    return true;
  }
  function tamano(d) { aj.tam = Math.max(9, Math.min(24, (aj.tam || 13) + d)); guardarAj(); aplicarAj(); }

  // --- La terminal que se ve ----------------------------------------------------------------
  function desarmar() {
    mudo = false;
    comandos = []; enCurso = null; fallo = null;
    ['fallo', 'sel', 'buscar', 'pedir'].forEach(b => barra(b, false));
    if (mirador) { mirador.disconnect(); mirador = null; }
    if (ws) { const w = ws; ws = null; w.onclose = null; try { w.close(); } catch (e) {} }
    if (xt) { try { xt.dispose(); } catch (e) {} xt = null; ajuste = null; buscador = null; }
    const c = $c('.conCuerpo');
    if (c) c.innerHTML = '';
  }
  function mandar(m) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(m));
  }
  function ver(id) {
    desarmar();
    actual = id;
    pintarTabs();
    nota('');
    if (!id) return;
    const donde = $c('.conCuerpo');
    xt = new window.Terminal(Object.assign({allowTransparency: true, allowProposedApi: true, theme: tema()}, opcionesXt()));
    ajuste = new window.FitAddon.FitAddon();
    xt.loadAddon(ajuste);
    if (window.SearchAddon) { buscador = new window.SearchAddon.SearchAddon(); xt.loadAddon(buscador);
      buscador.onDidChangeResults && buscador.onDidChangeResults(r => {
        const c = $c('[data-barra="buscar"] .cuenta');
        if (c) c.textContent = r && r.resultCount ? (r.resultIndex + 1) + ' de ' + r.resultCount : 'no está';
      }); }
    if (window.WebLinksAddon) xt.loadAddon(new window.WebLinksAddon.WebLinksAddon((ev, url) => {
      ev.preventDefault();
      window.open(url, '_blank', 'noopener');
    }));
    xt.open(donde);
    try { ajuste.fit(); } catch (e) {}
    engancharMarcas();
    xt.attachCustomKeyEventHandler(teclas);
    // ⚠ `mudo`: mientras se dibuja el repaso (lo que ya había), lo que xterm quiera
    // "tipear" NO se manda. No son teclas tuyas: son sus respuestas a preguntas viejas que
    // vienen adentro del repaso, y al PowerShell le llegarían como texto tipeado.
    xt.onData(d => { if (!mudo) mandar({t: 'i', d}); });
    xt.onResize(({cols, rows}) => mandar({t: 'm', f: rows, c: cols}));
    xt.onSelectionChange(() => {
      const hay = xt.hasSelection() && xt.getSelection().trim();
      barra('sel', !!hay);
      if (hay && aj.copiarSel) copiarSeleccion();
    });
    // Clic derecho: si hay algo seleccionado lo copia, si no pega (como la Terminal de Windows).
    donde.oncontextmenu = async e => {
      if (!aj.clicDerPega) return;
      e.preventDefault();
      if (xt.hasSelection()) { await copiarSeleccion(); xt.clearSelection(); return; }
      try { const t = await navigator.clipboard.readText(); if (t) xt.paste(t); } catch (err) {}
    };
    // La pieza cambia de tamaño (arrastrás el borde, achicás la ventana): la terminal se
    // vuelve a medir, de a una vez por cuadro.
    let cuadro = 0;
    mirador = new ResizeObserver(() => {
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() => { try { ajuste && ajuste.fit(); } catch (e) {} });
    });
    mirador.observe(donde);
    conectar(id);
  }
  function conectar(id) {
    const mio = new WebSocket(WSBASE + '/terminal/ws?id=' + encodeURIComponent(id) +
                              '&llave=' + encodeURIComponent(llave));
    ws = mio;
    let repaso = true;                              // el primer mensaje es lo que ya había
    mio.onopen = () => {
      if (ws !== mio || !xt) return;
      xt.reset();                                   // lo guardado llega entero otra vez
      comandos = []; enCurso = null;
      mandar({t: 'm', f: xt.rows, c: xt.cols});
    };
    mio.onmessage = e => {
      if (ws !== mio || !xt) return;
      ultima = Date.now();
      if (repaso) {
        repaso = false;
        if (e.data) { mudo = true; xt.write(e.data, () => { mudo = false; ultima = Date.now(); }); }
        return;
      }
      xt.write(e.data);
    };
    mio.onclose = e => {
      if (ws !== mio) return;
      ws = null;
      if (!visible) return;
      if (e.code === 4000) {                        // la terminal terminó (un `exit`)
        nota('Esta terminal se cerró.<br><button type="button" data-abrir>Abrir otra</button>');
        lista = lista.filter(t => t.id !== id);
        pintarTabs();
        return;
      }
      // Se cortó (el panel se reinició, o la llave venció): se vuelve a mirar qué hay.
      clearTimeout(vuelta);
      vuelta = setTimeout(() => { if (visible) { llave = ''; sincronizar(true); } }, 1500);
    };
  }

  // --- Qué terminales hay para esta carpeta -----------------------------------------------
  const misma = (a, b) => String(a || '').replace(/[\\/]+$/, '').replace(/\\/g, '/').toLowerCase() ===
                          String(b || '').replace(/[\\/]+$/, '').replace(/\\/g, '/').toLowerCase();
  async function sincronizar(forzar) {
    if (!visible) return;
    const u = cfg.ubicacion() || {};
    const quiero = u.cwd || '';
    if (!forzar && carpeta !== null && misma(quiero, carpeta) && actual) return;
    try {
      await biblioteca();
      const r = await pedir('/terminal/lista');
      if (!visible) return;
      if (hay === false) {
        desarmar(); lista = []; actual = ''; carpeta = quiero; pintarTabs();
        return nota('Al panel le falta la pieza que abre terminales (pywinpty).');
      }
      const mias = (r.terminales || []).filter(t => t.viva && (quiero ? misma(t.cwd, quiero) : true));
      carpeta = quiero;
      lista = mias;
      if (!mias.length) return abrirOtra();
      if (!mias.some(t => t.id === actual) || !xt) ver(mias[mias.length - 1].id);
      else pintarTabs();
    } catch (e) {
      nota('No pude hablar con el panel para abrir la terminal. Si lo acabás de actualizar, ' +
           'falta reiniciarlo.<br><button type="button" data-abrir>Probar de nuevo</button>');
    }
  }
  async function abrirOtra(shell) {
    try {
      await biblioteca();
      const u = cfg.ubicacion() || {};
      const r = await pedir('/terminal/abrir', {cwd: u.cwd || '', filas: 24, cols: 100, shell: shell || aj.shell || 'pwsh'});
      if (!visible) return;
      if (!r.ok) return nota(esc(r.error || 'No pude abrir la terminal.'));
      carpeta = u.cwd || '';
      lista = lista.filter(t => t.id !== r.id).concat([{id: r.id, cwd: r.cwd, viva: true, shell: r.shell}]);
      ver(r.id);
    } catch (e) {
      nota('No pude abrir la terminal.<br><button type="button" data-abrir>Probar de nuevo</button>');
    }
  }
  async function cerrar(id) {
    try { await pedir('/terminal/cerrar', {id}); } catch (e) {}
    lista = lista.filter(t => t.id !== id);
    delete nombres[id]; guardarNombres();
    if (id === actual) {
      desarmar(); actual = '';
      if (lista.length) ver(lista[lista.length - 1].id);
      else { pintarTabs(); nota('Sin terminales en esta carpeta.<br><button type="button" data-abrir>Abrir una</button>'); }
    } else pintarTabs();
  }

  // --- Lo que ve `Paneles` ---------------------------------------------------------------
  function mostrar(c) {
    caja = c;
    visible = true;
    armar();
    sincronizar(true);
    // Cambiaste de charla con la terminal a la vista: se muestran las de esa carpeta.
    clearInterval(reloj);
    reloj = setInterval(() => sincronizar(false), 900);
  }
  function ocultar() {
    visible = false;
    clearInterval(reloj);
    clearInterval(relojPegar);
    clearTimeout(vuelta);
    desarmar();
  }
  function pegar(texto) {
    if (!xt) return;
    xt.paste(texto);               // pegado "entre corchetes": varios renglones NO se ejecutan solos
    xt.focus();
  }
  // ¿La terminal está esperando que tipees? Conectada, sin repaso a medio dibujar, callada
  // hace un rato y con algo escrito en el renglón del cursor (su "PS C:\…>").
  function lista_para_tipear() {
    if (!xt || !ws || ws.readyState !== 1 || mudo) return false;
    if (!ultima || Date.now() - ultima < 450) return false;
    const b = xt.buffer.active, r = b.getLine(b.baseY + b.cursorY);
    return !!(r && r.translateToString(true).trim());
  }
  // ⚠ El ▶ NO pega apenas se conecta. Una terminal recién abierta tarda segundos en mostrar
  // su renglón (carga el perfil de PowerShell), y una a la que se vuelve está dibujando el
  // repaso: pegar ahí mezcla el comando con eso. Se espera a que esté lista; si a los 20 s
  // no lo está, se pega igual y que se vea.
  function pegar_cuando_pueda() {
    const desde = Date.now();
    clearInterval(relojPegar);
    relojPegar = setInterval(() => {
      if (!pendiente || !visible) return clearInterval(relojPegar);
      const vencio = Date.now() - desde > 20000;
      if (!lista_para_tipear() && !(vencio && xt && ws && ws.readyState === 1)) {
        if (Date.now() - desde > 40000) { pendiente = ''; clearInterval(relojPegar); }
        return;
      }
      clearInterval(relojPegar);
      const p = pendiente;
      pendiente = '';
      pegar(p);
    }, 120);
  }
  // El ▶ de un bloque de código. Devuelve true si se hace cargo (si no, el botón sigue con
  // el camino de antes, la ventana de PowerShell).
  function escribir(texto, cwd) {
    if (hay === false) return false;
    const limpio = String(texto || '').replace(/\s+$/, '');
    if (!limpio) return false;
    pendiente = limpio;
    cfg.traer();                                    // abre la columna y elige la pestaña
    // Queda anotado como quedaba con el botón de antes (lo tipeado a mano, no).
    pedir('/terminal/anotar', {id: actual, cwd: cwd || '', cmd: limpio}).catch(() => {});
    pegar_cuando_pueda();
    return true;
  }

  window.Consola = {iniciar: c => { cfg = Object.assign(cfg, c || {}); }, mostrar, ocultar, escribir,
                    // Para las pruebas y para mirar desde la consola del navegador.
                    estado: () => ({visible, carpeta, actual, cuantas: lista.length, hay,
                                    conectada: !!(ws && ws.readyState === 1),
                                    cols: xt ? xt.cols : 0, filas: xt ? xt.rows : 0,
                                    tam: xt ? xt.options.fontSize : 0, cursor: xt ? xt.options.cursorStyle : '',
                                    comandos: comandos.map(c => ({cmd: c.cmd, codigo: c.codigo})),
                                    seleccion: xt && xt.hasSelection() ? xt.getSelection() : '',
                                    fallo: fallo ? fallo.cmd : '', shell: (lista.find(t => t.id === actual) || {}).shell || ''})};
})();
