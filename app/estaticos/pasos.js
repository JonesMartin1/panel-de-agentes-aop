// ⭐⭐ El rastro de la charla, con pasos desplegables (2026-09-27), para las DOS pantallas
// que leen una charla: `/sesiones` (app/estaticos/sesiones.html) y el celular (MOVIL_HTML,
// adentro de panel.py). Pedido de Martín: que el panel muestre lo que muestra Claude Code.
//
// Cada paso ("escribió en panel.py", "corrió: pytest") ahora:
//   - dice su ESTADO: si se lo negaron ("no se lo dejé") o si corrió y falló. Antes un paso
//     negado se leía como hecho — "escribió en settings.json" sin haber escrito nada.
//   - se DESPLIEGA al tocarlo: una edición muestra su cambio en rojo y verde con número de
//     línea (el `structuredPatch` que guarda Claude Code, el mismo que dibuja la terminal);
//     un comando, lo que devolvió. El detalle se pide aparte (`GET /movil/paso`): el hilo se
//     pide cada 3 s y no puede cargar con todas las salidas.
//
// Se usa así:
//   Pasos.iniciar({ubicacion: () => ({cwd, sid}), repintar: () => pintarSesion()});
//   m.de === 'paso' ? Pasos.fila(mensajes, iM) : …        // adentro del armado del hilo
// Trae sus propios estilos. El clic lo escucha solo, en todo el documento.
(function () {
  let cfg = {ubicacion: () => null, repintar: () => {}};
  const abiertos = new Set();          // "sid|id1,id2" de los pasos desplegados
  const detalles = {};                 // misma clave -> lista de detalles (o 'cargando')
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                                              .replace(/"/g, '&quot;');

  const estilos = document.createElement('style');
  estilos.textContent = `
    .paso.abre{cursor:pointer}
    .paso.abre:hover{text-decoration:underline;text-underline-offset:3px}
    .paso.abierto{color:var(--c8ecbff,#8ecbff)}
    .paso.negado{text-decoration:line-through;opacity:.8}
    /* inline-block: si no, el tachado del paso tacharía también el cartel. */
    .paso.negado::after{content:'(no se lo dejé)';color:var(--aviso,#d8a657);display:inline-block;margin-left:5px}
    .paso.fallo::after{content:'(falló)';color:var(--mal-txt,#e39a9a);display:inline-block;margin-left:5px}
    .detPaso{background:var(--rastro-bg,rgba(16,21,30,.85));border:1px solid var(--rastro-borde,#232b3a);
      border-radius:10px;padding:9px 11px;margin:4px 0 8px;max-width:min(900px,96%);
      display:flex;flex-direction:column;gap:10px}
    .dpTit{font-size:12px;color:var(--rastro,#93a0b4);margin-bottom:5px}
    .dpTit b{font-weight:600;color:var(--c8ecbff,#8ecbff)}
    .detPaso pre{margin:0;white-space:pre-wrap;word-break:break-word;font:12px/1.5 Consolas,'Cascadia Mono',monospace;
      background:rgba(0,0,0,.28);border-radius:7px;padding:7px 9px;max-height:420px;overflow:auto;color:#d6dbe3}
    .dpCmd{color:#c9d1d9}
    .dpSub{font-size:12px;color:var(--rastro,#93a0b4);line-height:1.6;margin:2px 0 6px 4px}
    .dpNota,.dpVacio{font-size:11.5px;color:#6e7889}
    .dif{font:12px/1.45 Consolas,'Cascadia Mono',monospace;background:rgba(0,0,0,.28);border-radius:7px;
      padding:5px 0;max-height:480px;overflow:auto}
    .difArch{font-size:11.5px;color:#8b95a6;padding:0 9px 4px}
    .difSep{color:#5c6675;padding:2px 9px}
    .dl{display:flex;white-space:pre-wrap;word-break:break-word}
    .dl .dn{flex:none;width:44px;text-align:right;padding-right:8px;color:#5c6675;user-select:none}
    .dl .ds{flex:none;width:14px;color:#6e7889;user-select:none}
    .dl .dt{flex:1;padding-right:9px;color:#c9d1d9}
    /* Tonos suaves a propósito: una línea quitada no es un error (el rojo es para lo que
       está mal, regla de Martín); es el mismo código de colores de Claude Code, apagado. */
    .dl.dp{background:rgba(46,160,67,.16)} .dl.dp .ds,.dl.dp .dt{color:#a8d8b0}
    .dl.dm{background:rgba(229,83,75,.13)} .dl.dm .ds,.dl.dm .dt{color:#e0aeaa}
  `;
  document.head.appendChild(estilos);

  const claveDe = (sid, ids) => sid + '|' + ids.join(',');

  function hunksHtml(d) {
    let h = '<div class="dif">';
    if (d.archivo) h += '<div class="difArch">' + esc(d.archivo) + '</div>';
    d.hunks.forEach((k, i) => {
      let viejo = k.viejo, nuevo = k.nuevo;
      if (i) h += '<div class="difSep">⋯</div>';
      (k.lineas || []).forEach(l => {
        const s = l.charAt(0), x = l.slice(1);
        let cls = 'dc', num = '';
        if (s === '+') { cls = 'dp'; num = nuevo++; }
        else if (s === '-') { cls = 'dm'; num = viejo++; }
        else { num = nuevo++; viejo++; }
        h += '<div class="dl ' + cls + '"><span class="dn">' + num + '</span><span class="ds">' +
             (s === '+' || s === '-' ? s : ' ') + '</span><span class="dt">' + esc(x) + '</span></div>';
      });
    });
    return h + '</div>';
  }

  function detalleHtml(clave) {
    const dets = detalles[clave];
    if (dets === 'cargando') return '<div class="detPaso"><div class="dpNota">cargando…</div></div>';
    if (!Array.isArray(dets) || !dets.length)
      return '<div class="detPaso"><div class="dpNota">No encontré el detalle de este paso.</div></div>';
    return '<div class="detPaso">' + dets.map(d => {
      const est = d.estado === 'negado' ? ' · <b>no se lo dejé</b>' : d.estado === 'error' ? ' · <b>falló</b>'
                : d.estado === '' ? ' · todavía corriendo' : '';
      let h = '<div><div class="dpTit">' + esc(d.paso) + est +
              (d.segundo_plano ? ' · trabajó en segundo plano' : '') + '</div>';
      if (d.comando) h += '<pre class="dpCmd">$ ' + esc(d.comando) + '</pre>';
      // Lo que hizo un subagente (leído de su propio archivo), antes de su informe.
      if (d.sub_pasos && d.sub_pasos.length)
        h += '<div class="dpSub">' + d.sub_pasos.map(p => '<div>↳ ' + esc(p) + '</div>').join('') + '</div>';
      if (d.hunks) h += hunksHtml(d);
      if (d.salida) h += '<pre>' + esc(d.salida) + '</pre>';
      else if (!d.hunks && d.estado) h += '<div class="dpVacio">(no devolvió nada)</div>';
      if (d.cortado) h += '<div class="dpNota">Recortado: lo completo está en la transcripción de la charla.</div>';
      return h + '</div>';
    }).join('') + '</div>';
  }

  // Un renglón del rastro. Abre el bloque si es el primero de una tanda seguida y lo
  // cierra si es el último; al cerrarlo, agrega abajo el detalle de los que estén abiertos.
  function fila(mensajes, iM) {
    const m = mensajes[iM], ant = mensajes[iM - 1] || {}, sig = mensajes[iM + 1] || {};
    const u = cfg.ubicacion() || {};
    const ids = (m.ids || []).filter(Boolean);
    const clave = claveDe(u.sid || '', ids);
    const cls = 'paso' + (ids.length ? ' abre' : '') + (abiertos.has(clave) ? ' abierto' : '') +
                (m.estado === 'negado' ? ' negado' : m.estado === 'error' ? ' fallo' : '');
    let h = (ant.de === 'paso' ? '' : '<div class="pasos">') +
            '<div class="' + cls + '" data-msg="' + iM + '" data-ids="' + esc(ids.join(',')) + '">' +
            esc(m.texto) + '</div>';
    if (sig.de === 'paso') return h;
    h += '</div>';
    // Los detalles abiertos de toda esta tanda, en orden, debajo del bloque.
    let ini = iM;
    while (ini > 0 && (mensajes[ini - 1] || {}).de === 'paso') ini--;
    for (let j = ini; j <= iM; j++) {
      const k = claveDe(u.sid || '', (mensajes[j].ids || []).filter(Boolean));
      if (abiertos.has(k)) h += detalleHtml(k);
    }
    return h;
  }

  async function alternar(ids) {
    const u = cfg.ubicacion();
    if (!u || !u.sid || !ids.length) return;
    const clave = claveDe(u.sid, ids);
    if (abiertos.has(clave)) { abiertos.delete(clave); cfg.repintar(); return; }
    abiertos.add(clave);
    if (!Array.isArray(detalles[clave]) || detalles[clave].some(d => d.estado === '')) {
      detalles[clave] = 'cargando';
      cfg.repintar();
      try {
        const r = await (await fetch('/movil/paso?cwd=' + encodeURIComponent(u.cwd || '') +
                         '&sid=' + encodeURIComponent(u.sid) + '&ids=' +
                         encodeURIComponent(ids.join(',')))).json();
        detalles[clave] = r.pasos || [];
      } catch (e) { detalles[clave] = []; }
    }
    cfg.repintar();
  }

  document.addEventListener('click', e => {
    const p = e.target.closest && e.target.closest('.paso.abre');
    if (!p) return;
    // Estabas seleccionando texto (para copiar o marcar): eso no es un toque.
    const sel = window.getSelection && String(window.getSelection() || '');
    if (sel) return;
    alternar((p.dataset.ids || '').split(',').filter(Boolean));
  });

  window.Pasos = {
    iniciar: c => { cfg = Object.assign(cfg, c || {}); },
    fila, detalleHtml, hunksHtml,
  };
})();
