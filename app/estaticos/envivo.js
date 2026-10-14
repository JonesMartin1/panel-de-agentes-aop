// ⭐⭐ El texto en vivo, como en Claude Code (2026-09-27), para las DOS pantallas que leen
// una charla: la de la compu (app/estaticos/sesiones.html) y la del celular (MOVIL_HTML,
// adentro de panel.py). Pedido de Martín: "quiero que me aparezca el texto tal cual como
// lo haría Claude Code". Antes el hilo salía SOLO del disco, y Claude Code escribe cada
// mensaje ahí recién cuando lo terminó: una respuesta larga aparecía entera y de golpe.
//
// Mientras la charla trabaja se abre UN canal (`/movil/envivo`, SSE) que empuja el
// borrador a medida que se escribe (`EN_VIVO` en sesiones_movil.py), y se dibuja en el
// `#envivo` que cada pantalla deja debajo del hilo.
//
// ⭐ El disco sigue mandando: cada bloque terminado trae el `uuid` de su línea del
// .jsonl, y apenas el hilo del disco lo trae (`EnVivo.hilo`), el borrador lo suelta. Las
// dos cosas pasan en el MISMO repintado, así que el texto no parpadea al cambiar de fuente.
// ⚠ `#envivo` NO entra en la firma del hilo de ninguna pantalla: si entrara, cada
// pedacito rearmaría el hilo entero (y las marcas, y el scroll).
// ⚠ Una sola conexión por página: el navegador aguanta 6 abiertas por sitio.
//
// Se usa así:
//   EnVivo.iniciar({activa: () => activa, repintar: () => pintarSesion()});
//   EnVivo.hilo(sid, mensajes);                        // cada vez que llega /movil/chat
//   EnVivo.seguir(sid, cwd, sidDelServidor, pensa);    // abre o cierra el canal
//   '<div id="envivo"></div>'                          // en el html del hilo
//   EnVivo.pintar();                                   // después de rearmar el hilo
(function () {
  let cfg = {activa: () => '', repintar: () => {}};
  let est = {sid: '', fuente: null, datos: null, finEn: 0};
  const uuids = {};
  let pendiente = false;
  const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const marcar = t => window.md ? '<div class="md">' + window.md(t) + '</div>' : esc(t);

  // Markdown a medio escribir: un bloque ``` sin cerrar se dibuja como código desde que
  // empieza (si no, se ve el texto crudo y "salta" al cerrarse), y un ** suelto al final
  // no se muestra hasta que llega su pareja.
  function cerrarCercas(t) {
    if ((t.match(/^\s*```/gm) || []).length % 2) return t + '\n```';
    if ((t.match(/\*\*/g) || []).length % 2) return t.replace(/\*\*(?=[^*]*$)/, '');
    return t;
  }

  function pintar() {
    const caja = document.getElementById('envivo');
    if (!caja) return;
    const d = est.datos, activa = cfg.activa();
    let bl = [];
    // Terminado el turno, lo que quede se suelta a los 6 s aunque el disco no lo haya
    // traído: puede ser algo que el hilo esconde a propósito, y no puede quedar pegado.
    if (d && est.sid === activa && !(d.fin && Date.now() - est.finEn > 6000)) {
      const vistos = uuids[activa] || new Set();
      bl = (d.bloques || []).filter(b => b.tipo !== 'pensando' && (b.texto || '').trim() &&
                                         !(b.u && vistos.has(b.u)));
    }
    let h = '';
    bl.forEach((b, i) => {
      if (b.tipo === 'paso') {
        h += ((bl[i - 1] || {}).tipo === 'paso' ? '' : '<div class="pasos">') +
             '<div class="paso' + (b.abierto ? ' corriendo' : '') + '">' + esc(b.texto) +
             '</div>' + ((bl[i + 1] || {}).tipo === 'paso' ? '' : '</div>');
      } else {
        h += '<div class="msg claude envivo' + (b.abierto ? ' escribiendo' : '') + '">' +
             marcar(cerrarCercas(b.texto)) + '</div>';
      }
    });
    if (h === caja._h) return;
    const c = document.getElementById('cuerpo');
    // Mismo criterio que el repintado: te sigue hacia abajo solo si ya estabas abajo.
    const abajo = c && c.scrollHeight - c.scrollTop - c.clientHeight < 90;
    caja.innerHTML = h;
    caja._h = h;
    if (abajo) c.scrollTop = c.scrollHeight;
  }

  function seguir(sid, cwd, sidServidor, pensa) {
    if (!sid || !pensa) {
      // El canal se cierra pero el borrador se queda un rato: los últimos bloques pueden
      // no estar todavía en el disco, y se sueltan cuando llegan (o a los 6 s del final).
      if (est.fuente) { est.fuente.close(); est.fuente = null; }
      return;
    }
    if (est.fuente && est.sid === sid) return;
    if (est.fuente) est.fuente.close();
    est = {sid: sid, fuente: null, datos: null, finEn: 0};
    const f = new EventSource('/movil/envivo?cwd=' + encodeURIComponent(cwd || '') +
                              '&sid=' + encodeURIComponent(sidServidor || ''));
    f.onmessage = e => {
      if (est.fuente !== f) return;
      let d;
      try { d = JSON.parse(e.data); } catch (_) { return; }
      // Terminó el turno: se pide el hilo del disco enseguida en vez de esperar al
      // repintado de 3 s, para que la respuesta quede en su lugar definitivo cuanto antes.
      if (d.fin && !(est.datos && est.datos.fin)) {
        est.finEn = Date.now();
        setTimeout(() => { if (cfg.activa() === est.sid) cfg.repintar(); }, 400);
      }
      est.datos = d;
      if (!pendiente) {
        pendiente = true;
        requestAnimationFrame(() => { pendiente = false; pintar(); });
      }
    };
    est.fuente = f;
  }

  function hilo(sid, mensajes) {
    const s = new Set();
    (mensajes || []).forEach(m => {
      if (m.u) s.add(m.u);
      (m.us || []).forEach(u => s.add(u));
    });
    uuids[sid] = s;
  }

  window.EnVivo = {
    iniciar: c => { cfg = Object.assign(cfg, c || {}); },
    seguir, hilo, pintar, cerrarCercas,
  };
})();
