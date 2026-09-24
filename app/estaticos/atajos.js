/* El boton de la caja de escribir: ⚡ Skills y comandos.
 *
 * Pedido de Martin (2026-08-18): "quiero que me aparezcan las opciones que suelen
 * aparecer cuando escribo la barrita en Claude Code... un boton para desplegar las
 * skills y un boton para desplegar los comandos, porque tener todo en el mismo me
 * confunde". Dos botones, dos listas — y la de skills ademas marca cuales YA uso
 * esta sesion (✓) y cual esta corriendo ahora (●), que fue la tercera vuelta del
 * pedido. El 2026-08-21 Martin pidio volver a juntarlos: ahora es una sola puerta,
 * pero adentro siguen siendo dos secciones claras. En la cuarta (2026-08-18) pidio
 * que estuvieran marcadas tambien las que
 * ocupa EN EL PROYECTO: en una conversacion recien abierta el menu salia todo en
 * blanco aunque en wpp-transcriptor ya se usaran ocho de las trece skills.
 *
 * Vive como archivo aparte —igual que menu.js y marcas.js— porque lo comparten la
 * pagina de sesiones (archivo suelto) y el chat del panel (adentro de panel.py).
 * Los datos los pone `GET /skills` (app/nucleo/skills.py): el catalogo sale de las
 * carpetas de skills y las usadas del propio .jsonl de la conversacion.
 *
 * Como se usa:
 *   Atajos.montar({
 *     contenedor: <span> donde poner los botones,
 *     sesion:   () => ({sid, cwd}) o ({de:'laura'}),   // que sesion preguntar
 *     insertar: texto => ...,                          // pegar en la caja de texto
 *     acciones: {compactar, nueva, modelo},            // comandos que ACA son un boton
 *   })
 *
 * ⚠ Los comandos de Claude Code no viajan como texto: `/compact` mandado a una
 * sesion por `-p` se ignora (probado el 2026-08-18, cero turnos). Por eso los que
 * tienen equivalente en la pantalla EJECUTAN ese equivalente, y solo los que son
 * skills de verdad (/init, /code-review...) se escriben en la caja.
 */
(function () {
  /* ⚠ Con `button.` adelante a proposito: las dos pantallas tienen reglas generales
     para sus botones (`.caja button`, `.barra-chat button`) con la misma
     especificidad, y como este <style> se inyecta al montar —o sea despues de los de
     la pagina— el empate lo gana este. Sin eso, los botones salian pintados como el
     de Enviar. */
  const CSS = `
button.at-boton{display:inline-flex;align-items:center;gap:5px;padding:0 11px;height:38px;
  align-self:center;border-radius:11px;border:1px solid #262e3a;background:#151b26;
  color:#8b93a1;font-size:12px;cursor:pointer;white-space:nowrap;user-select:none}
button.at-boton:hover{background:#1b2230;color:#c9d2de}
button.at-boton.abierto{background:#16263a;border-color:#2c4a6b;color:#cfe6ff}
.at-menu{position:fixed;z-index:1200;min-width:290px;max-width:420px;max-height:min(60vh,480px);
  overflow-y:auto;background:#151a24;border:1px solid #2a3444;border-radius:12px;
  padding:7px;box-shadow:0 14px 40px rgba(0,0,0,.55);font-size:13px}
.at-menu .titulo{padding:4px 10px 7px;font-size:11px;color:#7d8592;
  text-transform:uppercase;letter-spacing:.5px}
.at-menu .fila{display:flex;align-items:baseline;gap:8px;padding:7px 10px;
  border-radius:8px;cursor:pointer;line-height:1.35}
.at-menu .fila:hover{background:#1d2530}
.at-menu .nombre{color:#8ecbff;font-weight:600;white-space:nowrap}
.at-menu .desc{color:#8b93a1;font-size:12px;flex:1;min-width:0}
/* La marca de "ya se uso en esta charla" y la de "corriendo AHORA". El verde vivo es
   del semaforo de las sesiones: aca van tonos apagados, como pide la regla del rojo. */
.at-menu .chapa{font-size:10.5px;padding:1px 7px;border-radius:999px;white-space:nowrap;
  background:#1d2b22;color:#8fc9a2;border:1px solid #2b4636;align-self:center}
.at-menu .chapa.corre{background:#2e2a12;color:#e8c069;border-color:#5b4d1c;
  animation:atLate 1.6s ease-in-out infinite}
/* Usada en el PROYECTO pero no en esta charla: mas apagada a proposito. Las tres
   marcas tienen que poder distinguirse de un vistazo y en este orden de fuerza:
   corriendo ahora > la usaste en esta charla > la usas en el proyecto. */
.at-menu .chapa.proy{background:#1a212c;color:#7f93a8;border-color:#28323f}
/* Una carpeta de skill a la que le falta el SKILL.md. Ambar, no rojo: no esta rota la
   pantalla, esta mal puesto un archivo y hay que ir a acomodarlo. */
.at-menu .chapa.rota{background:#2a2117;color:#d5a06b;border-color:#4b3822}
.at-menu .fila.rota .nombre{color:#c9a175}
@keyframes atLate{50%{opacity:.45}}
.at-menu .pie{padding:7px 10px 3px;font-size:11px;color:#616977;border-top:1px solid #222a36;
  margin-top:5px;line-height:1.4}
.at-menu .aviso{padding:10px;color:#7d8592}
`;

  /* Los comandos que se ofrecen. `accion` = en esta pantalla son un boton que ya
     existe y se aprieta ese; sin accion, el comando es una skill que viaja como
     texto y se escribe en la caja. Los que solo andan en la terminal (/status,
     /help, /doctor...) no estan a proposito: ofrecer algo que aca no hace nada es
     peor que no ofrecerlo. */
  const COMANDOS = [
    { id: '/compact', desc: 'Resumir la charla y seguir en una sesion nueva, para dejar de arrastrar todo el contexto', accion: 'compactar' },
    { id: '/clear', desc: 'Arrancar una conversacion nueva, de cero', accion: 'nueva' },
    /* `descCodex` es para los comandos cuyo texto nombra a Claude: el mismo botón
       existe en una charla de Codex y decía "modelo de Claude", que es mentira ahí. */
    { id: '/model', desc: 'Elegir con que modelo de Claude corre esta charla',
      descCodex: 'Elegir con que modelo de Codex corre esta charla', accion: 'modelo' },
    { id: '/init', desc: 'Crear o poner al dia el CLAUDE.md del proyecto' },
    { id: '/code-review', desc: 'Revisar los ultimos cambios buscando errores' },
    { id: '/security-review', desc: 'Revision de seguridad de los cambios de la rama' },
  ];

  let abierto = null;   // {menu, boton, soltar}: lo que hay que desarmar al cerrar

  /* ⚠⚠ Cerrar es sacar el cartel Y desenganchar las escuchas del documento. La
     leccion es de marcas.js (2026-08-18): una escucha zombi cerraba el menu
     siguiente en el mousedown, antes de que llegara el clic — "aprieto el boton y
     no pasa nada". */
  function cerrar() {
    if (!abierto) return;
    abierto.menu.remove();
    abierto.boton.classList.remove('abierto');
    abierto.soltar();
    abierto = null;
  }

  function abrir(boton, armar) {
    const estaba = abierto && abierto.boton === boton;
    cerrar();
    if (estaba) return;                      // segundo toque en el mismo: se cierra
    const menu = document.createElement('div');
    menu.className = 'at-menu';
    document.body.appendChild(menu);
    const acomodar = () => {
      const r = boton.getBoundingClientRect();
      menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + 'px';
      // Siempre para ARRIBA: la caja de escribir vive contra el borde de abajo.
      menu.style.bottom = (innerHeight - r.top + 8) + 'px';
    };
    const teclado = e => { if (e.key === 'Escape') cerrar(); };
    const afuera = e => {
      if (!menu.contains(e.target) && e.target !== boton && !boton.contains(e.target)) cerrar();
    };
    document.addEventListener('keydown', teclado);
    document.addEventListener('mousedown', afuera);
    abierto = { menu, boton, soltar: () => {
      document.removeEventListener('keydown', teclado);
      document.removeEventListener('mousedown', afuera);
    } };
    boton.classList.add('abierto');
    armar(menu, acomodar);
    acomodar();
  }

  const esc = s => (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');

  /* La descripción de un comando según el cerebro de la charla. */
  const descDe = (c, cerebro) => (cerebro === 'codex' && c.descCodex) || c.desc;

  function filaHtml(nombre, desc, chapa, tipo) {
    return '<div class="fila ' + (tipo || '') + '" data-id="' + esc(nombre) + '">' +
      '<span class="nombre">' + esc(nombre) + '</span>' +
      '<span class="desc">' + esc(desc) + '</span>' +
      (chapa || '') + '</div>';
  }

  /* La marca de cada skill, de la mas fuerte a la mas debil:
       ● en uso    la esta corriendo AHORA
       ✓ usada     ya la invocaste en ESTA conversacion
       ✓ 8         la usas en el proyecto, en otras conversaciones
     La tercera es el pedido de Martin del 2026-08-18: abriendo el menu en una charla
     nueva estaba todo en blanco aunque en el proyecto ya use ocho de las trece. */
  function chapaDe(nombre, r) {
    const veces = (r.proyecto || {})[nombre] || 0;
    const enProyecto = veces ? ' · ' + veces + ' ' + (veces === 1 ? 'vez' : 'veces') +
                               ' en el proyecto' : '';
    if (nombre === r.corriendo) {
      return '<span class="chapa corre" title="Corriendo ahora mismo' + enProyecto +
             '">● en uso</span>';
    }
    if ((r.usadas || []).includes(nombre)) {
      return '<span class="chapa" title="Ya la usaste en esta conversación' +
             enProyecto + '">✓ usada</span>';
    }
    if (veces) {
      return '<span class="chapa proy" title="Todavía no en esta conversación, pero la ' +
             'usaste ' + veces + (veces === 1 ? ' vez' : ' veces') +
             ' en este proyecto">✓ ' + veces + '</span>';
    }
    return '';
  }

  /* El mismo menú, pero para una charla de Codex. Tres diferencias con el de Claude:
     las skills se invocan con `$nombre` en vez de `/nombre`, abajo de ellas van los
     prompts propios de Codex (`~/.codex/prompts`, esos sí con barrita), y de comandos
     quedan SOLO los que esta pantalla resuelve con un botón. Los otros (/init,
     /code-review…) son de Claude: mandados a Codex como texto no hacen nada, y ofrecer
     algo que no anda es peor que no ofrecerlo.

     ⚠⚠ Hasta el 2026-08-28 acá no se listaba ninguna skill y el pie decía "Codex no
     usa las skills de Claude". Era falso desde el 2026-08-19, que es cuando se
     enlazaron las 14 en `~/.codex/skills`. El menú fue durante nueve días la fuente de
     una creencia equivocada: Martín lo abría, veía el cartel vacío y concluía que
     Codex estaba pelado. Si volvés a tocar esto, comprobalo antes con
     `codex debug prompt-input "hola"`, que lista lo que Codex realmente tiene. */
  function pintarCodex(r, menu, acomodar, op, acciones) {
    /* `$nombre`, no `/nombre`: la barrita es de Claude. Verificado el 2026-08-28 con
       un `codex exec` real — con `$pizarra` contestó el comando exacto que está en el
       CUERPO del SKILL.md, o sea que lo abrió y no adivinó por la descripción. */
    const skillsHtml = (r.skills || []).map(s => filaHtml('$' + s.nombre, s.descripcion,
      s.a_pedido ? '<span class="chapa proy" title="Codex no la dispara sola: hay que ' +
                   'nombrarla, y por eso está acá">a pedido</span>' : '',
      'skill')).join('');
    const prompts = r.prompts || [];
    const promptsHtml = prompts.map(c => filaHtml('/' + c.nombre, c.descripcion,
      '<span class="chapa proy">tuyo</span>', 'skill')).join('');
    const comandos = COMANDOS.filter(c => c.accion && acciones[c.accion]);
    const comandosHtml = comandos.map(c => filaHtml(c.id, descDe(c, 'codex'),
      '<span class="chapa">se hace aca</span>', 'comando')).join('');
    menu.innerHTML = '<div class="titulo">Skills</div>' +
      (skillsHtml || '<div class="aviso">No pude leer las skills de Codex ' +
       '(¿el panel viejo? reinicialo).</div>') +
      '<div class="titulo">Prompts de Codex</div>' +
      (promptsHtml || '<div class="aviso">Todavía no tenés ningún prompt de Codex.</div>') +
      '<div class="titulo">Comandos</div>' + comandosHtml +
      '<div class="pie">Las skills son las mismas que las de Claude (están enlazadas en ' +
      '<b>' + esc(r.carpeta_skills || '~/.codex/skills') + '</b>), pero acá se llaman con ' +
      '<b>$nombre</b>.<br>Un prompt es otra cosa: un archivo <b>' +
      esc(r.carpeta || '~/.codex/prompts') + '\\&lt;nombre&gt;.md</b> que se invoca con ' +
      'la barrita. Los dos aparecen acá al abrir el menú, sin reiniciar nada.</div>';
    menu.querySelectorAll('.fila.skill').forEach(f => {
      f.onclick = () => { op.insertar(f.dataset.id + ' '); cerrar(); };
    });
    menu.querySelectorAll('.fila.comando').forEach(f => {
      const c = COMANDOS.find(x => x.id === f.dataset.id);
      f.onclick = () => { cerrar(); if (c && acciones[c.accion]) acciones[c.accion](); };
    });
    acomodar();
  }

  function montar(op) {
    if (!op || !op.contenedor) return;
    if (!document.getElementById('cssAtajos')) {
      const s = document.createElement('style');
      s.id = 'cssAtajos';
      s.textContent = CSS;
      document.head.appendChild(s);
    }
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.id = 'btnAtajos';
    boton.className = 'at-boton';
    /* `etiqueta` existe por el teléfono: en el ancho de la barra de escribir del
       celular "⚡ Skills y comandos" no entra y empuja la caja de texto. Ahí va solo
       el rayo, y el nombre completo queda en el title. */
    boton.textContent = op.etiqueta || '⚡ Skills y comandos';
    boton.title = 'Skills y comandos disponibles para esta charla';
    op.contenedor.appendChild(boton);

    boton.onclick = () => abrir(boton, async (menu, acomodar) => {
      const acciones = op.acciones || {};
      const pintar = r => {
        const ok = !!(r && r.ok);
        /* ⭐ Una charla de Codex no tiene skills de Claude: tiene sus propios prompts
           (decisión de Martín, 2026-08-23). Y si todavía no creó ninguno, el menú lo
           dice y explica dónde se crean, en vez de salir en blanco — que se lee como
           "esta pantalla está rota" y no como "no tenés ninguno todavía". */
        if (ok && r.cerebro === 'codex') return pintarCodex(r, menu, acomodar, op, acciones);
        const skillsHtml = ok ? (r.skills || []).map(s =>
          filaHtml('/' + s.nombre, s.descripcion, chapaDe(s.nombre, r), 'skill')).join('') : '';
        /* ⭐ Las carpetas de skills sin SKILL.md adentro (2026-08-23). Van al final de
           la lista y NO se pueden tocar: no hay nada que insertar, es un aviso. Es la
           respuesta a "la creé y no aparece": si está acá, el archivo quedó mal puesto;
           si no está en ninguna de las dos listas, no llegó a crearse. */
        const rotasHtml = ok ? (r.rotas || []).map(n => filaHtml(n,
          'la carpeta está pero le falta el archivo SKILL.md adentro: así Claude no la ve',
          '<span class="chapa rota">⚠ sin SKILL.md</span>', 'rota')).join('') : '';
        /* Los comandos TUYOS (~/.claude/commands) van atrás de los de siempre: antes el
           menú tenía seis fijos y uno propio no aparecía nunca. */
        const propiosHtml = ok ? (r.comandos || []).map(c => filaHtml('/' + c.nombre,
          c.descripcion, '<span class="chapa proy">tuyo</span>', 'comando')).join('') : '';
        const comandosHtml = COMANDOS.map(c => filaHtml(c.id, c.desc,
          c.accion && acciones[c.accion] ? '<span class="chapa">se hace aca</span>' : '',
          'comando')).join('') + propiosHtml;
        menu.innerHTML = '<div class="titulo">Skills</div>' +
          (r === null ? '<div class="aviso">Leyendo…</div>' :
           ok ? ((skillsHtml + rotasHtml) || '<div class="aviso">No hay skills instaladas.</div>') :
           '<div class="aviso">No pude leer las skills (¿el panel viejo? reinicialo).</div>') +
          '<div class="titulo">Comandos</div>' + comandosHtml +
          '<div class="pie">Las skills se escriben en la caja. Los comandos con equivalente ' +
          'en esta pantalla ejecutan ese control.<br>Una skill nueva va en ' +
          '<b>~/.claude/skills/&lt;nombre&gt;/SKILL.md</b> y aparece acá al abrir el menú, ' +
          'sin reiniciar nada.</div>';
        menu.querySelectorAll('.fila.skill').forEach(f => {
          f.onclick = () => { op.insertar(f.dataset.id + ' '); cerrar(); };
        });
        menu.querySelectorAll('.fila.comando').forEach(f => {
          const c = COMANDOS.find(x => x.id === f.dataset.id);
          f.onclick = () => {
            cerrar();
            if (c && c.accion && acciones[c.accion]) acciones[c.accion]();
            else op.insertar(f.dataset.id + ' ');
          };
        });
        acomodar();
      };
      pintar(null);
      const ses = op.sesion() || {};
      const q = ses.de ? 'de=' + ses.de
                       : 'sid=' + encodeURIComponent(ses.sid || '') +
                         '&cwd=' + encodeURIComponent(ses.cwd || '');
      let r = null;
      try { r = await (await fetch('/skills?' + q)).json(); } catch (e) {}
      if (abierto === null || abierto.menu !== menu) return;   // la cerraron esperando
      pintar(r);
    });
  }

  window.Atajos = { montar };
})();
