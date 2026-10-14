// ⭐ El @ de la caja de escribir (2026-09-27): nombrar un archivo del proyecto como en
// Claude Code. Escribís `@pan` y aparece la lista con `panel.py` y compañía; con ↑ ↓ elegís,
// Enter o Tab lo pone, Esc la cierra. En el celular se toca. La búsqueda la hace el
// servidor (`GET /archivos/buscar`), con la misma llave que el explorador: solo adentro de
// una carpeta que el panel ya conoce.
//
// Se usa así:   Arroba.enganchar(textarea, () => cwdDeLaCharla)
// ⚠ Escucha el teclado ANTES que la página (fase de captura): mientras la lista está
// abierta, Enter elige en vez de mandar y ↑ se mueve en la lista en vez de traer tus
// mensajes anteriores. Con la lista cerrada no toca nada.
(function () {
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const estilos = document.createElement('style');
  estilos.textContent = `
    #arrobaLista{position:fixed;z-index:60;max-height:300px;overflow:auto;border-radius:10px;
      background:var(--c10161f,#10161f);border:1px solid var(--c25435e,#25435e);
      box-shadow:0 10px 30px rgba(0,0,0,.45);padding:4px;font:13px/1.35 system-ui,sans-serif}
    #arrobaLista .aItem{padding:6px 9px;border-radius:7px;cursor:pointer;display:flex;gap:6px;
      align-items:baseline;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #arrobaLista .aItem b{font-weight:600;color:#e8ecf1}
    #arrobaLista .aItem span{color:#6e7889;font-size:12px;overflow:hidden;text-overflow:ellipsis}
    #arrobaLista .aItem.sel{background:var(--c14304a,#14304a)}
    #arrobaLista .aNota{padding:6px 9px;color:#6e7889;font-size:12px}
  `;
  document.head.appendChild(estilos);

  let lista = null, caja = null, items = [], sel = 0, pedido = 0, temporizador = null;

  // El @ que estás escribiendo: desde un @ pegado al comienzo o a un espacio, hasta el cursor.
  function arrobaActual(c) {
    const antes = c.value.slice(0, c.selectionStart);
    const m = antes.match(/(^|\s)@([^\s@]*)$/);
    return m ? {q: m[2], desde: antes.length - m[2].length - 1} : null;
  }

  function cerrar() {
    if (lista) lista.remove();
    lista = null; items = []; sel = 0;
  }

  function pintar(c, q) {
    if (!lista) {
      lista = document.createElement('div');
      lista.id = 'arrobaLista';
      document.body.appendChild(lista);
      // mousedown y no click: si no, la caja pierde el foco antes de elegir.
      lista.addEventListener('mousedown', e => {
        const it = e.target.closest('.aItem');
        if (!it) return;
        e.preventDefault();
        elegir(+it.dataset.i);
      });
    }
    const r = c.getBoundingClientRect();
    lista.style.left = Math.max(6, r.left) + 'px';
    lista.style.width = Math.min(620, Math.max(260, r.width)) + 'px';
    lista.style.bottom = (window.innerHeight - r.top + 6) + 'px';
    lista.innerHTML = items.length ? items.map((ruta, i) => {
      const k = ruta.lastIndexOf('/');
      return '<div class="aItem' + (i === sel ? ' sel' : '') + '" data-i="' + i + '"><b>' +
        esc(ruta.slice(k + 1)) + '</b><span>' + esc(k >= 0 ? ruta.slice(0, k + 1) : '') + '</span></div>';
    }).join('') : '<div class="aNota">' + (q ? 'Ningún archivo con «' + esc(q) + '»' : 'Buscando…') + '</div>';
    const actual = lista.querySelector('.aItem.sel');
    if (actual) actual.scrollIntoView({block: 'nearest'});
  }

  function elegir(i) {
    const ruta = items[i];
    const a = caja && arrobaActual(caja);
    if (!ruta || !a) return cerrar();
    const v = caja.value, hasta = caja.selectionStart;
    const nuevo = v.slice(0, a.desde) + '@' + ruta + ' ';
    caja.value = nuevo + v.slice(hasta);
    caja.setSelectionRange(nuevo.length, nuevo.length);
    // Que la página se entere (alto de la caja, borrador guardado).
    caja.dispatchEvent(new Event('input', {bubbles: true}));
    cerrar();
    caja.focus();
  }

  function buscar(c, cwd) {
    const a = arrobaActual(c);
    if (!a || !cwd) return cerrar();
    caja = c;
    clearTimeout(temporizador);
    if (!lista) pintar(c, a.q);
    temporizador = setTimeout(async () => {
      const mio = ++pedido;
      let r = null;
      try {
        r = await (await fetch('/archivos/buscar?n=12&cwd=' + encodeURIComponent(cwd) +
                               '&q=' + encodeURIComponent(a.q))).json();
      } catch (e) {}
      if (mio !== pedido || !arrobaActual(c)) return;
      if (!r || !r.ok) return cerrar();
      items = r.archivos || []; sel = 0;
      pintar(c, a.q);
    }, 120);
  }

  function enganchar(c, cwdDe) {
    if (!c || c._arroba) return;
    c._arroba = true;
    c.addEventListener('input', () => buscar(c, cwdDe()));
    c.addEventListener('click', () => { if (arrobaActual(c)) buscar(c, cwdDe()); else cerrar(); });
    c.addEventListener('blur', () => setTimeout(cerrar, 150));
    c.addEventListener('keydown', e => {
      if (!lista) return;
      const mover = d => { if (items.length) { sel = (sel + d + items.length) % items.length; pintar(c, ''); } };
      if (e.key === 'ArrowDown') mover(1);
      else if (e.key === 'ArrowUp') mover(-1);
      else if ((e.key === 'Enter' || e.key === 'Tab') && items.length) elegir(sel);
      else if (e.key === 'Escape') cerrar();
      else return;
      e.preventDefault();
      e.stopImmediatePropagation();
    }, true);
  }

  window.Arroba = {enganchar, cerrar, _arrobaActual: arrobaActual};
})();
