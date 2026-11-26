/* El 🔑 de la caja de escribir: pegar una contraseña SIN que pase por la charla.
 *
 * Pedido de Martin (2026-11-26): "me parece importante que pueda pegar las contraseñas
 * aca en el panel". Escrita en el chat, una clave queda en la transcripcion (diez años) y
 * viaja al modelo en cada turno. Con esto:
 *   1. tocás 🔑, le ponés un nombre y pegás la clave (campo tapado);
 *   2. el panel la guarda en un archivo de la laptop (`~/.claude/claves/<nombre>`,
 *      ver app/voz/claves.py);
 *   3. a la caja de escribir vuelve SOLO el nombre y la ruta, para que la sesion la lea
 *      del archivo cuando la necesite.
 * La clave no vuelve nunca del servidor y el campo se vacia apenas se guarda.
 *
 * Lo comparten `/sesiones` (compu) y el celular, como atajos.js.
 *   Claves.abrir({insertar: texto => ...})
 */
(function () {
  const CSS = `
.cl-fondo{position:fixed;inset:0;z-index:1300;background:rgba(5,8,14,.62);display:flex;
  align-items:center;justify-content:center;padding:16px}
.cl-hoja{width:min(420px,100%);background:#151a24;border:1px solid #2a3444;border-radius:14px;
  padding:16px 16px 14px;box-shadow:0 18px 50px rgba(0,0,0,.6);color:#c9d2de;font-size:14px}
.cl-hoja h3{margin:0 0 4px;font-size:16px;color:#e6ecf3;font-weight:600}
.cl-hoja p.cl-ayuda{margin:0 0 12px;font-size:12.5px;color:#8b93a1;line-height:1.4}
.cl-hoja label{display:block;font-size:12px;color:#8b93a1;margin:10px 0 4px}
.cl-hoja input{width:100%;box-sizing:border-box;background:#0f141c;border:1px solid #2a3444;
  border-radius:9px;color:#e6ecf3;padding:10px 11px;font-size:15px;outline:none}
.cl-hoja input:focus{border-color:#3d6a99}
.cl-fila{display:flex;gap:6px;align-items:center}
.cl-fila input{flex:1;min-width:0}
.cl-hoja button{border-radius:9px;border:1px solid #2a3444;background:#1b2230;color:#c9d2de;
  padding:9px 14px;font-size:14px;cursor:pointer}
.cl-hoja button.cl-ojo{padding:9px 10px;flex:none}
.cl-hoja button.cl-ok{background:#1f3b5c;border-color:#2c5a88;color:#e6f1ff}
.cl-hoja button:disabled{opacity:.55;cursor:default}
.cl-pie{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.cl-error{min-height:18px;margin-top:8px;font-size:12.5px;color:#e0a36b}
`;
  let estilo = false;
  function ponerEstilo() {
    if (estilo) return;
    const s = document.createElement('style');
    s.textContent = CSS;
    document.head.appendChild(s);
    estilo = true;
  }

  function abrir(opc) {
    opc = opc || {};
    ponerEstilo();
    const fondo = document.createElement('div');
    fondo.className = 'cl-fondo';
    fondo.innerHTML = `
<form class="cl-hoja" autocomplete="off">
  <h3>🔑 Pegar una clave</h3>
  <p class="cl-ayuda">Se guarda en un archivo de la laptop. A la charla le llega solo el
  nombre: la clave no queda escrita en la conversación.</p>
  <label for="clNombre">Nombre</label>
  <input id="clNombre" list="clNombres" placeholder="ej.: panel-admin" autocapitalize="off"
         autocorrect="off" spellcheck="false" maxlength="60">
  <datalist id="clNombres"></datalist>
  <label for="clValor">Clave</label>
  <div class="cl-fila">
    <input id="clValor" type="password" autocomplete="off" autocapitalize="off"
           autocorrect="off" spellcheck="false" data-lpignore="true" data-1p-ignore>
    <button type="button" class="cl-ojo" title="Mostrar u ocultar">👁</button>
  </div>
  <div class="cl-error" aria-live="polite"></div>
  <div class="cl-pie">
    <button type="button" class="cl-no">Cancelar</button>
    <button type="submit" class="cl-ok">Guardar</button>
  </div>
</form>`;
    document.body.appendChild(fondo);
    const $ = s => fondo.querySelector(s);
    const nombre = $('#clNombre'), valor = $('#clValor'), err = $('.cl-error'), ok = $('.cl-ok');
    let reemplazar = false;

    function cerrar() {
      valor.value = '';
      fondo.remove();
      document.removeEventListener('keydown', tecla, true);
    }
    function tecla(e) { if (e.key === 'Escape') { e.preventDefault(); cerrar(); } }
    document.addEventListener('keydown', tecla, true);
    fondo.addEventListener('mousedown', e => { if (e.target === fondo) cerrar(); });
    $('.cl-no').onclick = cerrar;
    $('.cl-ojo').onclick = () => { valor.type = valor.type === 'password' ? 'text' : 'password'; };
    // Cambiar el nombre después de un "ya existe" vuelve a pedir confirmación.
    nombre.addEventListener('input', () => { reemplazar = false; ok.textContent = 'Guardar'; });

    fetch('/claves', {cache: 'no-store'}).then(r => r.json()).then(d => {
      const dl = $('#clNombres');
      (d.nombres || []).forEach(n => { const o = document.createElement('option'); o.value = n; dl.appendChild(o); });
    }).catch(() => {});

    $('form').onsubmit = async e => {
      e.preventDefault();
      err.textContent = '';
      if (!nombre.value.trim()) { err.textContent = 'Ponele un nombre.'; nombre.focus(); return; }
      if (!valor.value) { err.textContent = 'Falta la clave.'; valor.focus(); return; }
      ok.disabled = true;
      let d;
      try {
        const r = await fetch('/claves/guardar', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, cache: 'no-store',
          body: JSON.stringify({nombre: nombre.value, valor: valor.value, reemplazar})
        });
        d = await r.json();
      } catch (x) {
        d = {ok: false, error: 'No llegué al panel: ¿está prendido?'};
      }
      ok.disabled = false;
      if (!d.ok) {
        err.textContent = d.error || 'No se pudo guardar.';
        if (d.existe) { reemplazar = true; ok.textContent = 'Reemplazar'; }
        return;
      }
      cerrar();
      if (opc.insertar) opc.insertar(
        `(Te dejé la clave «${d.nombre}» en ${d.ruta}: leela de ese archivo cuando la ` +
        `necesites y no la escribas en la charla.)`);
    };
    setTimeout(() => nombre.focus(), 30);
  }

  window.Claves = {abrir};
})();
