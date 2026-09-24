// Markdown a la vista, para los DOS lugares donde se lee lo que escribe Claude: la
// pagina de sesiones de la compu (app/estaticos/sesiones.html) y la pestaña de
// sesiones del celular (MOVIL_HTML, adentro de panel.py). Antes se pintaba el texto
// tal cual venia y se leian los asteriscos y los numerales a la vista — pedido de
// Martin (2026-08-17): "que pueda leer lo que dice sin estar diciendo asterisco,
// asterisco".
//
// Es un renderizador chiquito A PROPOSITO: no hay internet en el celular ni ganas de
// arrastrar una libreria, y lo que llega es siempre el mismo puñado de marcas
// (negritas, titulos, viñetas, `codigo`, bloques ``` y alguna tabla). Lo que no
// reconoce lo deja como texto normal, que es la falla segura.
//
// ⚠ El HTML se escapa SIEMPRE antes de armar nada: esto pinta texto que viene de
// otra sesion de Claude, o sea de afuera. Nada de innerHTML sin pasar por aca.
//
// Se usa asi:  elemento.innerHTML = '<div class="md">' + md(texto) + '</div>'
// (la clase `md` es la que apaga el `white-space:pre-wrap` de la burbuja, porque
// ahora los saltos los dibujan los bloques y no los espacios).
(function () {
  const escapar = s => (s || '').replace(/&/g, '&amp;')
                                .replace(/</g, '&lt;')
                                .replace(/>/g, '&gt;');

  window.md = function (texto) {
    const guardado = [];
    // Lo guardado se marca entre dos NUL: es el unico caracter que nunca puede
    // venir en el texto, asi que la marca no se pisa con algo que escribio Claude.
    const guardar = html => '\u0000' + (guardado.push(html) - 1) + '\u0000';
    let s = (texto === null || texto === undefined) ? '' : String(texto);

    // 1) Los bloques ``` se sacan ENTEROS antes de tocar nada: ahi adentro un ** es
    //    un **, no una negrita, y un # es un #.
    // ⭐ Cada bloque de codigo trae DOS botones arriba a la derecha: copiarlo, y correrlo
    // en una ventana de PowerShell (pedido de Martin, 2026-08-18, senalando la esquina de
    // un bloque: "dos botones, uno para correr en powershell el comando y otro para
    // copiar el texto del comando, tal y como se puede hacer con Claude Code"). Los
    // botones se dibujan ACA, con el bloque, y quien los atiende es un solo escucha
    // delegado (mas abajo): el hilo se rearma cada 3 segundos y engancharlos uno por uno
    // seria volver a engancharlos en cada repintado.
    s = s.replace(/```[^\n]*\n?([\s\S]*?)```/g,
      (_, cod) => guardar('<div class="md-bloque">' +
        '<div class="md-bts">' +
          '<span class="md-bt" data-md="copiar" title="Copiar el comando">📋</span>' +
          '<span class="md-bt" data-md="correr" title="Correr en PowerShell">▶</span>' +
        '</div><pre class="md-pre">' + escapar(cod.replace(/\s+$/, '')) + '</pre></div>'));
    s = escapar(s);
    // 2) Lo mismo con el `codigo` suelto de una linea.
    s = s.replace(/`([^`\n]+)`/g, (_, c) => guardar('<code class="md-cod">' + c + '</code>'));

    // Lo de adentro de una linea. El orden importa: primero los enlaces (que traen
    // parentesis), despues las negritas, y la cursiva al final pidiendo que el
    // asterisco arranque pegado a un espacio — si no, un `2 * 3 * 4` se vuelve bastardilla.
    const enLinea = l => l
      .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
        (_, t, u) => '<a class="md-lnk" href="' + u.replace(/"/g, '%22') +
                     '" target="_blank" rel="noopener">' + t + '</a>')
      .replace(/\*\*\*([^*\n]+)\*\*\*/g, '<b><i>$1</i></b>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
      .replace(/(^|[\s(¡¿"'])\*([^*\s][^*\n]*?[^*\s]|[^*\s])\*(?=$|[\s.,;:)!?"'])/g, '$1<i>$2</i>')
      .replace(/(^|[\s(¡¿"'])_([^_\s][^_\n]*?[^_\s]|[^_\s])_(?=$|[\s.,;:)!?"'])/g, '$1<i>$2</i>')
      .replace(/~~([^~\n]+)~~/g, '<s>$1</s>');

    const salida = [];
    let lista = null;                       // 'ul' | 'ol' | null, la que este abierta
    const cerrar = () => { if (lista) { salida.push('</' + lista + '>'); lista = null; } };
    // Un renglon en blanco se dibuja como un hueco chico, igual que se veia antes con
    // pre-wrap; dos seguidos no hacen dos huecos.
    const HUECO = '<div class="md-hueco"></div>';
    const hueco = () => { if (salida.length && salida[salida.length - 1] !== HUECO) salida.push(HUECO); };
    const fila = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());

    const lineas = s.split('\n');
    for (let i = 0; i < lineas.length; i++) {
      const l = lineas[i].replace(/\s+$/, '');
      let m;

      if (!l.trim()) { cerrar(); hueco(); continue; }

      // Un bloque ``` que quedo solo en su linea: va tal cual, sin envolverlo en nada.
      if (/^\u0000\d+\u0000$/.test(l.trim())) { cerrar(); salida.push(l.trim()); continue; }

      // Tabla: una fila de |…| seguida de la de guiones. Sin esto se leia el |---|---|
      // crudo, que es justo el tipo de ruido del que se queja el pedido.
      if (/^\s*\|.*\|\s*$/.test(l) && /^\s*\|[\s:|-]+\|\s*$/.test(lineas[i + 1] || '')) {
        cerrar();
        const filas = [];
        while (i < lineas.length && /^\s*\|.*\|\s*$/.test(lineas[i])) filas.push(fila(lineas[i++]));
        i--;
        filas.splice(1, 1);                 // la linea de guiones no se dibuja
        salida.push('<table class="md-tab">' + filas.map((f, n) => '<tr>' + f.map(c => {
          const t = n ? 'td' : 'th';
          return '<' + t + '>' + enLinea(c) + '</' + t + '>';
        }).join('') + '</tr>').join('') + '</table>');
        continue;
      }

      // La raya va ANTES de las viñetas: si no, un `---` entra como viñeta de "--".
      if (/^\s*([-*_]\s*){3,}$/.test(l)) { cerrar(); salida.push('<div class="md-raya"></div>'); continue; }

      if ((m = l.match(/^\s{0,3}(#{1,6})\s+(.+)$/))) {
        cerrar();
        salida.push('<div class="md-tit md-t' + m[1].length + '">' +
                    enLinea(m[2].replace(/\s+#+\s*$/, '')) + '</div>');
      } else if ((m = l.match(/^(\s*)[-*•+]\s+(.+)$/))) {
        if (lista !== 'ul') { cerrar(); salida.push('<ul class="md-lis">'); lista = 'ul'; }
        salida.push('<li' + (m[1].length >= 2 ? ' class="md-sub"' : '') + '>' + enLinea(m[2]) + '</li>');
      } else if ((m = l.match(/^(\s*)\d+[.)]\s+(.+)$/))) {
        if (lista !== 'ol') { cerrar(); salida.push('<ol class="md-lis">'); lista = 'ol'; }
        salida.push('<li>' + enLinea(m[2]) + '</li>');
      // ⚠ La cita se busca como `&gt;`, no como `>`: a esta altura el texto YA esta
      // escapado, si no la cita nunca engancha.
      } else if ((m = l.match(/^\s*&gt;\s?(.*)$/))) {
        cerrar();
        salida.push('<div class="md-cita">' + enLinea(m[1]) + '</div>');
      } else {
        cerrar();
        salida.push('<div class="md-p">' + enLinea(l) + '</div>');
      }
    }
    cerrar();
    // Y al final vuelven el codigo y los bloques que se habian guardado.
    return salida.join('').replace(/\u0000(\d+)\u0000/g, (_, i) => guardado[+i]);
  };

  // Los estilos viajan con el renderizador: asi las dos pantallas se ven igual y hay
  // un solo lugar donde tocarlos. Todo en `em`, para que herede el tamaño de letra de
  // cada pagina (la del celular es mas grande que la de la compu).
  const CSS = `
 .md{white-space:normal}
 .md-p{margin:0}
 .md-hueco{height:.5em}
 .md-tit{font-weight:700;color:#cfe6ff;line-height:1.3;margin:.55em 0 .2em}
 .md > .md-tit:first-child{margin-top:0}
 .md-t1,.md-t2{font-size:1.13em}
 .md-t3{font-size:1.06em}
 .md-t4,.md-t5,.md-t6{font-size:1em;color:#b9cbe0}
 .md b{color:#f4f8ff}
 .md-lis{margin:.15em 0;padding-left:1.3em}
 .md-lis li{margin:.14em 0}
 .md-lis li.md-sub{margin-left:.9em;list-style-type:circle}
 .md-cita{margin:.2em 0;padding-left:.6em;border-left:3px solid #3a4657;color:#aab6c6}
 .md-raya{border-top:1px solid #2a3342;margin:.55em 0}
 .md-cod{background:#0d1119;border:1px solid #232a35;border-radius:5px;padding:0 .3em;
         font-family:Consolas,ui-monospace,monospace;font-size:.9em;color:#a5d6ff;
         word-break:break-word}
 .md-pre{background:#0d1119;border:1px solid #232a35;border-radius:9px;padding:.6em .7em;
         margin:.4em 0;overflow-x:auto;white-space:pre;color:#cfe0f5;
         font-family:Consolas,ui-monospace,monospace;font-size:.86em;line-height:1.45}
 .md-lnk{color:#8ecbff}
 .md-tab{border-collapse:collapse;margin:.35em 0;font-size:.94em;display:block;overflow-x:auto}
 .md-tab th,.md-tab td{border:1px solid #2a3342;padding:.25em .5em;text-align:left}
 .md-tab th{background:#151b26;color:#cfe6ff}
 /* --- Los dos botones del bloque de codigo --- */
 .md-bloque{position:relative}
 /* ⚠ Se ven SIEMPRE, apagaditos, y se encienden al pasar por encima. Escondidos del todo
    hasta el hover quedaban mas prolijos, pero un boton que no se ve no se usa: Martin los
    pidio para verlos ahi. En el telefono, ademas, no hay "pasar por encima". */
 .md-bts{position:absolute;top:6px;right:6px;display:flex;gap:5px;opacity:.5;
         transition:opacity .15s ease;z-index:2}
 .md-bloque:hover .md-bts{opacity:1}
 .md-bt{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:7px;
        background:#1b2230;border:1px solid #2f3a4a;color:#9fb0c4;font-size:12px;
        line-height:1.5;cursor:pointer;user-select:none;white-space:nowrap;
        font-family:Segoe UI,system-ui,sans-serif}
 .md-bt:hover{background:#26364d;color:#e8ecf1;border-color:#3d5170}
 .md-bt.ok{background:#123a24;border-color:#1d5c39;color:#8ff0b6}
 .md-bt.mal{background:#3a1a1a;border-color:#5a2a2a;color:#ff9d9d}
 /* Preguntando "¿seguro?" se agranda y se pone azul: se tiene que notar que el proximo
    toque ejecuta algo de verdad. */
 .md-bt.pregunta{background:#1d4b7a;border-color:#2d6ca8;color:#fff}
 /* Con los botones arriba, el codigo no puede empezar debajo de ellos. */
 .md-bloque .md-pre{padding-right:6.2em}
`;
  const st = document.createElement('style');
  st.id = 'css-marcado';
  st.textContent = CSS;
  document.head.appendChild(st);

  /* ⭐ UN solo escucha para todos los bloques de todas las pantallas.
     La conversacion se rearma entera cada 3 segundos: enganchar cada boton al dibujarlo
     obligaria a volver a engancharlos todos en cada repintado (y a acordarse de hacerlo
     en las cuatro pantallas que dibujan markdown). */
  const aviso = (b, txt, clase) => {
    const antes = b.textContent;
    b.textContent = txt;
    b.classList.add(clase);
    setTimeout(() => { b.textContent = antes; b.classList.remove(clase); }, 1600);
  };

  document.addEventListener('click', async e => {
    const b = e.target.closest ? e.target.closest('.md-bt') : null;
    if (!b) return;
    const pre = b.closest('.md-bloque').querySelector('.md-pre');
    const cmd = pre ? pre.textContent : '';
    if (!cmd.trim()) return;
    e.preventDefault();
    e.stopPropagation();

    if (b.dataset.md === 'copiar') {
      try { await navigator.clipboard.writeText(cmd); aviso(b, '✓ copiado', 'ok'); }
      catch (err) { aviso(b, 'no pude', 'mal'); }
      return;
    }

    // ⚠⚠ Correr pide DOS toques, y el segundo es el que ejecuta. Esto abre una ventana y
    // corre lo que diga el bloque en la maquina de Martin: un solo clic de mas no puede
    // ser suficiente. La pregunta va en el propio boton, al lado del comando que se ve.
    if (b.dataset.md === 'correr') {
      if (!b.classList.contains('pregunta')) {
        b.dataset.antes = b.textContent;
        b.textContent = '▶ ¿corro esto?';
        b.classList.add('pregunta');
        clearTimeout(+b.dataset.reloj || 0);
        b.dataset.reloj = setTimeout(() => {
          b.textContent = b.dataset.antes || '▶';
          b.classList.remove('pregunta');
        }, 4000);
        return;
      }
      clearTimeout(+b.dataset.reloj || 0);
      b.classList.remove('pregunta');
      b.textContent = b.dataset.antes || '▶';
      // La carpeta de la conversacion abierta, si la pantalla sabe cual es: casi todo
      // comando de un proyecto da por sentado que estas parado adentro.
      const donde = (typeof window.MD_CWD === 'function') ? (window.MD_CWD() || '') : '';
      try {
        const r = await (await fetch('/correr', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({cmd, cwd: donde})})).json();
        aviso(b, r.ok ? '✓ va' : (r.error || 'no pude'), r.ok ? 'ok' : 'mal');
      } catch (err) { aviso(b, 'no pude', 'mal'); }
    }
  });
})();
