/* El marcador de texto de las conversaciones — compartido por la compu y el celular.
 *
 * Pedido de Martín (2026-08-17): "poder pintar o subrayar el texto de las conversaciones
 * seleccionándolo, apretando clic derecho, y que ofrezca varias opciones de color, varias
 * formas de subrayarlo, la opacidad".
 *
 * ⭐ Vive en UN archivo, como `marcado.js` y `menu.js`: la conversación es la misma en las
 * dos pantallas, así que una marca tiene que dibujarse igual en las dos. La compu pinta y
 * borra; el celular, por ahora, solo muestra.
 *
 * ⭐⭐ Cómo se ancla una marca, que es lo único delicado de todo esto: NO se guarda HTML ni
 * un pedazo del DOM, porque la conversación se rearma entera cada 3 segundos y cualquier
 * cosa pegada al DOM se perdería en el primer repintado. Se guardan CUATRO números y un
 * texto: en qué mensaje (su posición en la charla), desde y hasta qué letra contadas sobre
 * el texto pelado de ese mensaje, y qué decía. Al repintar se vuelven a encontrar esas
 * letras y se envuelven de nuevo. Si el texto ya no coincide (el mensaje cambió), esa marca
 * no se dibuja: mejor no pintar nada que pintar el pedazo equivocado.
 *
 * ⚠ Las marcas se dibujan envolviendo pedazos de nodos de TEXTO, nunca reemplazando el HTML
 * del mensaje: así una selección que cruza una negrita, un enlace o un bloque de código
 * queda pintada sin romper el markdown que dibujó `marcado.js`.
 */
(function(){
  const API = '/marcas';

  // Los colores, como los ve Martín. El nombre es lo que se guarda; el valor, cómo se pinta.
  const COLORES = [
    {id:'amarillo', nombre:'Amarillo', css:'#ffd400'},
    {id:'verde',    nombre:'Verde',    css:'#3ddc84'},
    {id:'celeste',  nombre:'Celeste',  css:'#4aa8ff'},
    {id:'rosa',     nombre:'Rosa',     css:'#ff6ec7'},
    {id:'naranja',  nombre:'Naranja',  css:'#ff9d3d'},
    {id:'violeta',  nombre:'Violeta',  css:'#b586ff'},
  ];
  // Las formas. "marcador" es el subrayado grueso y torcido de resaltador, que es lo que
  // uno hace a mano sobre un papel; por eso está aunque el resaltado ya exista.
  const FORMAS = [
    {id:'resaltado', nombre:'Resaltado', muestra:'texto'},
    {id:'subrayado', nombre:'Subrayado', muestra:'texto'},
    {id:'marcador',  nombre:'Marcador',  muestra:'texto'},
    {id:'recuadro',  nombre:'Recuadro',  muestra:'texto'},
  ];

  const cache = {};                  // sid -> [marcas]
  let ultimo = {color:'amarillo', forma:'resaltado', op:0.4};
  try {
    const g = JSON.parse(localStorage.getItem('marcasUltimo') || 'null');
    if (g && g.color) ultimo = g;
  } catch(e){}

  // --- Estilos, traídos por el propio módulo (igual que menu.js) ---------------
  // Se meten una sola vez, y las páginas no tienen que saber nada de esto.
  function estilos(){
    if (document.getElementById('cssMarcas')) return;
    const s = document.createElement('style');
    s.id = 'cssMarcas';
    s.textContent = `
 .mkc{border-radius:3px;cursor:pointer}
 /* ⭐ La marca ELEGIDA: la tocás y queda agarrada, con su contorno punteado, mientras
    le cambiás el color o la forma — como cuando tocás un subrayado en el Acrobat. */
 .mkc.elegida{outline:2px dashed #8ecbff;outline-offset:2px}
 /* El color y la opacidad viajan en variables, así una sola regla sirve para todos. */
 .mkc.f-resaltado{background:color-mix(in srgb, var(--mkc) calc(var(--mko) * 100%), transparent);
                  padding:1px 2px;margin:0 -2px}
 .mkc.f-subrayado{border-bottom:2px solid var(--mkc);padding-bottom:1px}
 /* El resaltador de verdad: una franja gruesa abajo, un poco torcida, como el trazo
    que queda cuando pasás el fibrón a mano. */
 .mkc.f-marcador{background:linear-gradient(to top,
                   color-mix(in srgb, var(--mkc) calc(var(--mko) * 100%), transparent) 0 46%,
                   transparent 46%);
                 padding:0 2px;margin:0 -2px;border-radius:2px 6px 3px 5px}
 .mkc.f-recuadro{outline:1.5px solid var(--mkc);outline-offset:1px;border-radius:4px;
                 background:color-mix(in srgb, var(--mkc) calc(var(--mko) * 30%), transparent)}
 /* --- El menú del clic derecho --- */
 #menuMarcas{position:fixed;z-index:9999;background:#151a24;border:1px solid #2a3444;
             border-radius:12px;padding:10px;box-shadow:0 14px 40px rgba(0,0,0,.55);
             font:13px/1.4 Segoe UI,system-ui,sans-serif;color:#cfe6ff;min-width:214px;
             user-select:none}
 #menuMarcas .tit{font-size:11px;color:#7c8899;text-transform:uppercase;
                  letter-spacing:.06em;margin:0 0 6px}
 #menuMarcas .colores{display:flex;gap:7px;margin-bottom:11px}
 #menuMarcas .col{width:26px;height:26px;border-radius:50%;cursor:pointer;
                  border:2px solid transparent;transition:transform .12s ease}
 #menuMarcas .col:hover{transform:scale(1.14)}
 #menuMarcas .col.sel{border-color:#e8ecf1}
 /* El séptimo: elegir un color cualquiera. La rueda de colores se ve de lejos como lo
    que es, y el selector del sistema va encima, invisible y del mismo tamaño — así el
    clic cae en él sin que haya que dibujar nada aparte. */
 #menuMarcas .col.propio{position:relative;overflow:hidden;
   background:conic-gradient(#ff4d4d,#ffd400,#3ddc84,#4aa8ff,#b586ff,#ff6ec7,#ff4d4d)}
 #menuMarcas .col.propio input{position:absolute;inset:-6px;width:200%;height:200%;
   opacity:0;cursor:pointer;border:0;padding:0;background:none}
 #menuMarcas .col.propio i{position:absolute;inset:6px;border-radius:50%;
   border:2px solid #151a24}
 #menuMarcas .formas{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:11px}
 #menuMarcas .fr{padding:6px 8px;border-radius:8px;background:#1b2230;cursor:pointer;
                 text-align:center;border:1px solid #2a3444;font-size:12px}
 #menuMarcas .fr:hover{background:#243044}
 #menuMarcas .fr.sel{background:#243044;border-color:#3d7fbf;color:#fff}
 #menuMarcas .op{display:flex;align-items:center;gap:8px;margin-bottom:11px}
 #menuMarcas .op input{flex:1;accent-color:#3d7fbf}
 #menuMarcas .op b{font-weight:600;min-width:34px;text-align:right;color:#9aa6b5}
 #menuMarcas .acciones{display:flex;gap:6px}
 #menuMarcas .bt{flex:1;padding:7px 9px;border-radius:8px;text-align:center;cursor:pointer;
                 background:#1b2230;border:1px solid #2a3444;font-size:12px}
 #menuMarcas .bt:hover{background:#243044}
 #menuMarcas .bt.pintar{background:#1d4b7a;border-color:#2d6ca8;color:#fff;font-weight:600}
 #menuMarcas .bt.sacar:hover{background:#3a1a1a;border-color:#5a2a2a;color:#ff9d9d}`;
    document.head.appendChild(s);
  }

  // --- Contar letras adentro de un mensaje ------------------------------------
  // ⚠ Se cuenta sobre los nodos de TEXTO en orden, que es exactamente lo que ve
  // `textContent`. Así el número que se guarda no depende de cómo quedó armado el HTML.
  function nodosTexto(cont){
    const salida = [];
    const it = document.createTreeWalker(cont, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = it.nextNode())) salida.push(n);
    return salida;
  }

  // ¿En qué letra del mensaje cae este punto del DOM?
  function posicionDe(cont, nodo, dentro){
    let n = 0;
    for (const t of nodosTexto(cont)){
      if (t === nodo) return n + dentro;
      n += t.nodeValue.length;
    }
    return -1;
  }

  // --- Dibujar UNA marca ------------------------------------------------------
  // Se envuelve pedazo por pedazo: un nodo de texto que cae entero adentro se envuelve
  // completo, y el que queda a medias se parte. Así funciona con selecciones que cruzan
  // negritas, enlaces y código sin tocar el resto del dibujo.
  function pintarUna(cont, m){
    let n = 0;
    const partes = [];
    for (const t of nodosTexto(cont)){
      const largo = t.nodeValue.length;
      const desde = Math.max(m.ini, n), hasta = Math.min(m.fin, n + largo);
      if (hasta > desde) partes.push({t, a: desde - n, b: hasta - n});
      n += largo;
      if (n >= m.fin) break;
    }
    if (!partes.length) return false;
    for (const p of partes){
      let t = p.t;
      // ⚠ Se parte de atrás para adelante: partiendo primero por el principio, el
      // segundo corte caería sobre un nodo que ya cambió de largo.
      if (p.b < t.nodeValue.length) t.splitText(p.b);
      if (p.a > 0) t = t.splitText(p.a);
      const s = document.createElement('span');
      // ⚠ Lo elegido se vuelve a marcar en CADA repintado: el hilo se rearma cada 3 s y
      // si la clase viviera solo en el DOM, la marca que tenés agarrada se soltaría sola
      // mientras le estás cambiando el color.
      s.className = 'mkc f-' + (m.forma || 'resaltado') + (m.id === elegida ? ' elegida' : '');
      s.dataset.mk = m.id;
      s.style.setProperty('--mkc', colorCss(m.color));
      s.style.setProperty('--mko', String(m.op == null ? 0.4 : m.op));
      s.title = 'Marca — clic derecho para cambiarla o sacarla';
      t.parentNode.insertBefore(s, t);
      s.appendChild(t);
    }
    return true;
  }

  // ⭐ El color puede ser uno de los seis de siempre (guardado por su nombre) o uno
  // elegido a dedo con la rueda del sistema, y ahí se guarda el código tal cual (`#a1b2c3`).
  // Distinguirlos por el numeral alcanza y no hace falta ninguna lista aparte.
  const propio = c => typeof c === 'string' && c[0] === '#';
  const colorCss = id => propio(id) ? id : (COLORES.find(c => c.id === id) || COLORES[0]).css;

  // El texto pelado de un mensaje, para poder comprobar que la marca sigue cayendo donde
  // corresponde. ⚠ Se compara SIN espacios de más: el markdown redibujado puede meter o
  // sacar un salto de línea sin que el texto haya cambiado en nada.
  const flaco = s => (s || '').replace(/\s+/g, ' ').trim();

  /* ⭐⭐ La FIRMA de un mensaje: un numerito sacado de su texto entero.
     Hace falta porque `data-msg` es la posición en lo que trae el servidor, y el servidor
     manda SOLO LOS ÚLTIMOS 40 MENSAJES: cada vez que la charla sigue, todo se corre un
     lugar y una marca anclada al número apunta al mensaje equivocado. Con la firma, la
     marca encuentra SU mensaje aunque se haya movido de lugar — y como la conversación no
     se reescribe, el texto de un mensaje viejo no cambia nunca. */
  function firmaDe(texto){
    const t = flaco(texto);
    let h = 0;
    for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36) + '-' + t.length;
  }

  /* ⭐⭐ ¿DÓNDE empieza esta marca en este mensaje? Devuelve la letra, o -1 si no está.
     Lo que manda es EL TEXTO MARCADO, no el número de letra: se prueba primero donde
     decía la marca (que es lo normal y sale al instante) y, si ahí ya no está lo mismo,
     se lo busca en el mensaje. Anclar solo por posición no alcanzaba — se vio con las
     marcas de verdad de Martín el 2026-08-18: el mensaje seguía ahí, con el mismo texto,
     pero corrido unas letras, y las seis marcas no se dibujaban. */
  function ubicar(nodo, m){
    const t = nodo.textContent;
    // Hasta 200 letras alcanzan para reconocer un pedazo y no cuesta nada compararlas.
    const buscado = (m.texto || '').slice(0, 200);
    if (!buscado) return -1;
    if (t.substr(m.ini, buscado.length) === buscado) return m.ini;     // donde decía
    let i = t.indexOf(buscado);
    // Y si no aparece entero, con el arranque: al final del pedazo puede haber cambiado
    // un espacio o un salto de línea según cómo se dibujó el markdown.
    if (i < 0 && buscado.length > 60) i = t.indexOf(buscado.slice(0, 60));
    return i;
  }

  /* Pintar todas las marcas de una conversación ya dibujada.
     `cont` es el contenedor del hilo; adentro, cada mensaje lleva `data-msg` con su
     posición. Se llama DESPUÉS de cada repintado. */
  function pintar(cont, sid){
    if (!cont || !sid) return;
    estilos();
    const lista = cache[sid] || [];
    if (!lista.length) return;
    const msgs = [...cont.querySelectorAll('[data-msg]')];
    const firmas = msgs.map(n => firmaDe(n.textContent));
    for (const m of lista){
      // Se busca el mensaje en TRES pasos, del más confiable al más caro:
      // 1) por firma (la marca sabe a qué texto pertenece, aunque haya cambiado de lugar);
      let i = m.firma ? firmas.indexOf(m.firma) : -1;
      let pos = i >= 0 ? ubicar(msgs[i], m) : -1;
      // 2) por el número de mensaje que tenía guardado;
      if (pos < 0){
        const j = msgs.findIndex(x => +x.dataset.msg === +m.msg);
        const p = j >= 0 ? ubicar(msgs[j], m) : -1;
        if (p >= 0){ i = j; pos = p; }
      }
      // 3) y si no, se la busca mensaje por mensaje: así se rescatan las marcas viejas
      //    y las que quedaron corridas porque el chat trae solo los últimos 40 mensajes.
      if (pos < 0)
        for (let k = 0; k < msgs.length && pos < 0; k++){
          const p = ubicar(msgs[k], m);
          if (p >= 0){ i = k; pos = p; }
        }
      // Si no aparece en ningún lado, esa marca no se dibuja: el mensaje puede haber
      // quedado fuera de los últimos 40, o haber cambiado. Mejor nada que pintar al voleo.
      if (pos < 0) continue;
      const largo = Math.max(1, m.fin - m.ini);
      const donde = Object.assign({}, m, {ini: pos,
                                          fin: Math.min(pos + largo, msgs[i].textContent.length)});
      try { pintarUna(msgs[i], donde); } catch(e){ /* una marca rota no voltea el hilo */ }
      // Si la encontramos en otro lado del que decía, se la vuelve a anclar ahí — con su
      // firma, para que la próxima vez sea el paso 1 y no una búsqueda.
      if (m.firma !== firmas[i] || +m.msg !== +msgs[i].dataset.msg || m.ini !== donde.ini)
        reanclar(sid, m, +msgs[i].dataset.msg, firmas[i], donde.ini, donde.fin);
    }
  }

  // Guardar la marca donde de verdad está. Es "arreglarse sola": la primera vez que se
  // abre la charla después de que el hilo se corrió, la marca se reacomoda y queda firme.
  // ⚠ Va SACAR y después PONER, no un poner a secas: el servidor junta las marcas que
  // caen en el mismo lugar, así que mandando la misma marca con otro número de mensaje
  // quedaba la vieja colgada donde ya no está y se veía duplicada.
  async function reanclar(sid, m, msg, firma, ini, fin){
    m.msg = msg; m.firma = firma; m.ini = ini; m.fin = fin;   // en memoria ya queda bien
    try {
      await fetch(API + '/quitar', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, id: m.id})});
      await fetch(API + '/poner', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(Object.assign({sid}, m))});
    } catch(e){ /* si no se pudo guardar, se vuelve a buscar la próxima vez */ }
  }

  async function cargar(sid){
    if (!sid) return [];
    try {
      const r = await (await fetch(API + '?sid=' + encodeURIComponent(sid))).json();
      cache[sid] = (r.marcas && r.marcas[sid]) || [];
    } catch(e){ cache[sid] = cache[sid] || []; }
    return cache[sid];
  }

  async function poner(sid, marca){
    cache[sid] = (cache[sid] || []).filter(m => !(m.msg === marca.msg && m.ini === marca.ini
                                                 && m.fin === marca.fin));
    cache[sid].push(marca);                       // se ve YA, sin esperar al servidor
    try {
      const r = await (await fetch(API + '/poner', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(Object.assign({sid}, marca))})).json();
      if (r.marcas) cache[sid] = r.marcas;
    } catch(e){}
    return cache[sid];
  }

  async function quitar(sid, id, todas){
    cache[sid] = todas ? [] : (cache[sid] || []).filter(m => m.id !== id);
    try {
      const r = await (await fetch(API + '/quitar', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({sid, id, todas: !!todas})})).json();
      if (r.marcas) cache[sid] = r.marcas;
    } catch(e){}
    return cache[sid];
  }

  // --- El menú del clic derecho ------------------------------------------------
  // ⚠⚠ Cerrar el menú es SACAR EL CARTEL Y ADEMÁS DESENGANCHAR SUS ESCUCHAS. La primera
  // versión solo lo sacaba de la pantalla, y los `mousedown`/`keydown` que había dejado
  // puestos en el documento seguían vivos apuntando al menú viejo. ¿Qué pasaba? Que al
  // abrir el segundo menú, esa escucha zombi veía el clic "fuera del menú viejo" y lo
  // cerraba EN EL MOUSEDOWN, o sea antes de que llegara el clic: el primer marcado salía
  // bien y de ahí en adelante ningún botón hacía nada. Se veía exactamente como "no me
  // deja marcar nada" (2026-08-18).
  let soltarEscuchas = null;
  let elegida = null;          // el id de la marca agarrada, si hay una
  let alSoltarla = null;       // cómo se repinta cuando se suelta

  function cerrarMenu(){
    const m = document.getElementById('menuMarcas');
    if (m) m.remove();
    if (soltarEscuchas){ const f = soltarEscuchas; soltarEscuchas = null; f(); }
    // Cerrar el menú es también soltar la marca: el contorno punteado no puede quedar
    // puesto sin nada abierto, o parece que sigue seleccionada y no responde.
    if (elegida){
      elegida = null;
      const f = alSoltarla; alSoltarla = null;
      if (f) f();
    }
  }

  /* Abrirlo. `ev` es el evento del clic derecho, `sid` la conversación, `cont` el hilo y
     `alCambiar` lo que hay que hacer después (repintar). Devuelve false si no había nada
     seleccionado ni ninguna marca abajo del puntero: ahí la página deja pasar el menú
     del navegador, que es lo que uno espera cuando el clic derecho no viene al caso. */
  function menu(ev, sid, cont, alCambiar){
    estilos();
    cerrarMenu();
    const sel = window.getSelection();
    const encima = ev.target.closest ? ev.target.closest('.mkc') : null;
    // ⭐ Una selección puede cruzar VARIOS mensajes (arrastrás desde la mitad de uno hasta
    // dos párrafos más abajo, que es lo normal cuando querés marcar una explicación
    // entera). Como las letras se cuentan mensaje por mensaje, sale UNA marca por cada
    // mensaje tocado, con su pedacito. Antes se pintaba solo el primero y parecía que el
    // botón andaba a medias.
    const sitios = [];
    if (sel && !sel.isCollapsed && sel.rangeCount){
      const r = sel.getRangeAt(0);
      for (const nodo of cont.querySelectorAll('[data-msg]')){
        if (!sel.containsNode(nodo, true)) continue;
        const arranca = nodo.contains(r.startContainer);
        const termina = nodo.contains(r.endContainer);
        const ini = arranca ? posicionDe(nodo, r.startContainer, r.startOffset) : 0;
        const fin = termina ? posicionDe(nodo, r.endContainer, r.endOffset)
                            : nodo.textContent.length;
        if (ini < 0 || fin <= ini) continue;
        sitios.push({msg: +nodo.dataset.msg, ini, fin, firma: firmaDe(nodo.textContent),
                     texto: nodo.textContent.slice(ini, fin)});
      }
    }
    const sitio = sitios[0] || null;
    // ⚠ El texto se guarda ACÁ, al abrir el menú: apretar un botón puede soltar la
    // selección, y para entonces ya no habría nada que copiar.
    const seleccionado = sel && !sel.isCollapsed ? sel.toString() : '';
    if (!sitio && !encima) return false;
    ev.preventDefault();
    // ⭐ Tocar una marca la AGARRA: queda con su contorno punteado mientras el menú está
    // abierto, así se ve cuál estás cambiando (pedido de Martín, 2026-08-18: "como lo
    // ofrece el Adobe PDF, poder seleccionar ese subrayado y ahí recién cambiarle el
    // color"). Se suelta al cerrar el menú.
    if (encima && !sitio){
      elegida = encima.dataset.mk;
      alSoltarla = alCambiar || null;
      encima.classList.add('elegida');
    }

    const caja = document.createElement('div');
    caja.id = 'menuMarcas';
    // ⭐⭐ Lo que ya se pintó DESDE ESTE menú. Es lo que permite que tocar un color pinte en
    // el acto (sin apretar ningún "Pintar") y que el toque siguiente RETOQUE eso mismo en
    // vez de apilar otra marca encima. Pedido de Martín, 2026-08-18: "no me gusta tener
    // que apretar Pintar para que se pinte".
    let hechas = [];
    const dibujar = () => {
      caja.innerHTML =
        '<div class="tit">' + (hechas.length ? 'Lo que acabás de pintar'
                               : sitio ? 'Pintar lo seleccionado' : 'Esta marca') + '</div>' +
        '<div class="colores">' + COLORES.map(c =>
          '<div class="col' + (c.id === ultimo.color ? ' sel' : '') + '" data-color="' + c.id +
          '" title="' + c.nombre + '" style="background:' + c.css + '"></div>').join('') +
          // El de elegir a gusto va último y muestra adentro el color que tenés puesto.
          '<div class="col propio' + (propio(ultimo.color) ? ' sel' : '') +
            '" title="Elegir un color"><i style="background:' +
            (propio(ultimo.color) ? ultimo.color : 'transparent') + '"></i>' +
            '<input type="color" value="' + (propio(ultimo.color) ? ultimo.color : '#ffd400') +
            '"></div>' + '</div>' +
        '<div class="formas">' + FORMAS.map(f =>
          '<div class="fr' + (f.id === ultimo.forma ? ' sel' : '') + '" data-forma="' + f.id +
          '">' + f.nombre + '</div>').join('') + '</div>' +
        '<div class="op"><span>Opacidad</span>' +
          '<input type="range" min="10" max="100" value="' + Math.round(ultimo.op * 100) + '">' +
          '<b>' + Math.round(ultimo.op * 100) + '%</b></div>' +
        // ⭐ Ya NO hay botón "Pintar": el color ES el botón. Tocás el color y queda pintado.
        // Lo que queda acá son las dos cosas que no se pueden adivinar de un color.
        '<div class="acciones">' +
          // Copiar lo seleccionado, que es lo otro que uno quiere hacer con un pedazo de
          // conversación (pedido de Martín, 2026-08-18). Va acá y no en el menú del
          // navegador porque el menú del navegador ya no aparece cuando hay selección.
          (seleccionado ? '<div class="bt" data-hacer="copiar">📋 Copiar</div>' : '') +
          (encima || hechas.length
            ? '<div class="bt sacar" data-hacer="sacar">Sacar la marca</div>' : '') +
        '</div>';
    };
    dibujar();
    document.body.appendChild(caja);
    // Que no se salga de la pantalla: si no entra a la derecha o abajo, se acomoda sola.
    // ⚠ Cuando agarrás una marca, el menú va DEBAJO de ella y no en el puntero: puesto
    // donde clickeaste le tapaba justo el pedazo que estás por cambiarle de color.
    const an = caja.offsetWidth, al = caja.offsetHeight;
    const r = (encima && !sitio) ? encima.getBoundingClientRect() : null;
    const x = r ? r.left : ev.clientX;
    const y = r ? r.bottom + 8 : ev.clientY;
    caja.style.left = Math.max(6, Math.min(x, window.innerWidth - an - 6)) + 'px';
    // Si abajo no entra, se pone arriba de la marca en vez de encimarse.
    caja.style.top = (r && y + al > window.innerHeight - 6)
      ? Math.max(6, r.top - al - 8) + 'px'
      : Math.max(6, Math.min(y, window.innerHeight - al - 6)) + 'px';

    const recordar = () => localStorage.setItem('marcasUltimo', JSON.stringify(ultimo));
    // ⭐ Elegir un color o una forma con una marca abajo del puntero la cambia EN EL ACTO:
    // es lo que uno espera de un menú de formato, y evita "elegí y ahora dale a aplicar".
    const retocar = async ids => {
      for (const id of ids){
        const vieja = (cache[sid] || []).find(m => m.id === id);
        if (vieja) await poner(sid, Object.assign({}, vieja, {color: ultimo.color,
                                                              forma: ultimo.forma, op: ultimo.op}));
      }
    };
    const aplicar = async () => {
      if (hechas.length){
        // Segundo toque en adelante: se le cambia el color (o la forma, o la opacidad) a
        // lo que se acaba de pintar. Así se puede probar colores hasta que guste.
        await retocar(hechas);
      } else if (sitios.length){
        let n = 0;
        for (const s of sitios){
          const id = 'm' + Date.now() + '-' + (n++);
          hechas.push(id);
          await poner(sid, {id, msg: s.msg, ini: s.ini, fin: s.fin, firma: s.firma,
                            color: ultimo.color, forma: ultimo.forma, op: ultimo.op,
                            texto: s.texto});
        }
        // La selección ya cumplió: dejarla puesta hace que se vea el azul del navegador
        // encima de lo recién pintado y no se entienda de qué color quedó.
        try { window.getSelection().removeAllRanges(); } catch(e){}
        // Y queda AGARRADA, con su contorno: es lo que el menú está por seguir cambiando.
        elegida = hechas[0];
        alSoltarla = alCambiar || null;
      } else if (encima){
        await retocar([encima.dataset.mk]);
      }
      if (alCambiar) alCambiar();
    };
    caja.onclick = async e => {
      const c = e.target.dataset.color, f = e.target.dataset.forma, h = e.target.dataset.hacer;
      // ⭐ Tocar un color o una forma PINTA, sin más botones de por medio.
      if (c){ ultimo.color = c; recordar(); await aplicar(); dibujar(); enganchar(); return; }
      if (f){ ultimo.forma = f; recordar(); await aplicar(); dibujar(); enganchar(); return; }
      if (h === 'copiar'){
        // El aviso de que se copió va EN EL PROPIO BOTÓN y el menú se queda un momento:
        // copiar y que no pase nada visible es la manera de que uno lo apriete tres veces.
        try { await navigator.clipboard.writeText(seleccionado); e.target.textContent = '✓ Copiado'; }
        catch(err){ e.target.textContent = 'No pude copiarlo'; }
        setTimeout(cerrarMenu, 700);
        return;
      }
      if (h === 'sacar'){
        // Saca lo que el menú tenga entre manos: la marca que agarraste, o la que acabás
        // de pintar si te arrepentiste en el acto.
        const ids = hechas.length ? hechas.slice() : [encima.dataset.mk];
        cerrarMenu();
        for (const id of ids) await quitar(sid, id);
        if (alCambiar) alCambiar();
      }
    };
    const enganchar = () => {
      // La rueda de colores del sistema. ⚠ Se aplica al SOLTAR (`change`), no en cada
      // movimiento: mientras la arrastrás manda un evento por pixel.
      const p = caja.querySelector('.col.propio input');
      if (p) p.onchange = async () => {
        ultimo.color = p.value; recordar(); await aplicar(); dibujar(); enganchar();
      };
      const r = caja.querySelector('input[type=range]');
      if (!r) return;
      r.oninput = () => { ultimo.op = +r.value / 100; caja.querySelector('.op b').textContent = r.value + '%'; };
      // ⚠ Al soltar, no en cada movimiento: si no, cada pixelito del deslizador era un
      // pedido al servidor.
      // ⚠ La opacidad solo retoca lo que YA está pintado: mover el deslizador no puede
      // ser la manera de pintar sin querer un pedazo que estabas por copiar.
      r.onchange = async () => { recordar(); if (encima || hechas.length) await aplicar(); };
    };
    enganchar();
    // Se cierra tocando afuera o con Escape, como cualquier menú. ⚠ Las dos escuchas se
    // sueltan SIEMPRE al cerrar, por cualquiera de los caminos: eso es lo que hace
    // `cerrarMenu()` con `soltarEscuchas` (ver el comentario de arriba, costó caro).
    setTimeout(() => {
      document.addEventListener('mousedown', afuera);
      document.addEventListener('keydown', tecla);
      soltarEscuchas = () => {
        document.removeEventListener('mousedown', afuera);
        document.removeEventListener('keydown', tecla);
      };
    }, 0);
    function afuera(e){ if (!caja.contains(e.target)) cerrarMenu(); }
    function tecla(e){ if (e.key === 'Escape') cerrarMenu(); }
    return true;
  }

  window.Marcas = {cargar, pintar, poner, quitar, menu, cerrarMenu, COLORES, FORMAS,
                   cuantas: sid => (cache[sid] || []).length};
})();
