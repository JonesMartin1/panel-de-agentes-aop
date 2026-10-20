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
  `;
  document.head.appendChild(css);

  async function pedir(u) {
    const r = await fetch('/movil/entorno?cwd=' + encodeURIComponent(u.cwd || '') +
                          '&sid=' + encodeURIComponent(u.sid || ''));
    return r.json();
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
    h += tarjeta('entorno', 'Entorno', '', ent);
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
  function pintar(caja, r, u) {
    const h = html(r, u);
    if (caja.dataset.html !== h) { caja.innerHTML = h; caja.dataset.html = h; }
  }

  document.addEventListener('toggle', e => {
    const d = e.target && e.target.closest && e.target.closest('.entornoCaja details.tarjDer');
    if (!d) return;
    if (d.open) plegadas.delete(d.dataset.t); else plegadas.add(d.dataset.t);
    localStorage.setItem('sesDerPlegadas', JSON.stringify([...plegadas]));
  }, true);

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
