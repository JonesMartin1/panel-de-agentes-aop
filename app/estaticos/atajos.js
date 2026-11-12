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
 *     caja:     <textarea>,  // opcional: sugerir mientras escribis "/algo" (ver `sugerir`)
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
/* ⚠ El fondo y el borde se apagan a proposito: las paginas tienen su propio .aviso
   (un cartel azul; sin comillas invertidas aca, que cortan el texto del CSS) y sin esto el "Leyendo…" salia como un bloque pintado en el medio. */
.at-menu .aviso{padding:10px;color:#7d8592;background:none;border:0;border-radius:0}
/* El buscador: pegado arriba mientras la lista corre por debajo. El fondo tapa las
   filas que pasan por atras, y el margen negativo lo estira sobre el padding del menu. */
.at-menu .at-buscar{position:sticky;top:-7px;z-index:1;margin:-7px -7px 4px;padding:7px;
  background:#151a24;border-bottom:1px solid #222a36}
.at-menu .at-buscar input{width:100%;box-sizing:border-box;height:34px;padding:0 10px;
  border-radius:9px;border:1px solid #2a3444;background:#0f141c;color:#dbe3ee;
  font-size:13px;outline:none}
.at-menu .at-buscar input:focus{border-color:#2c4a6b}
/* ⚠ En el celular, un input con letra de menos de 16 px hace que iOS agrande la
   pagina entera al tocarlo, y no la vuelve a achicar. */
@media (pointer:coarse){.at-menu .at-buscar input{font-size:16px;height:40px}}
.at-menu .fila.primera{background:#1a2433}
/* La skill que ya elegiste en esta apertura del menu: tildada y apagadita. */
.at-menu .fila.elegida{opacity:.55;cursor:default}
.at-menu .fila.elegida .nombre::before{content:'✓ ';color:#7fd1a8}
/* Los bloques plegables: el titulo es el boton, con flechita y la cantidad adentro. */
.at-menu .titulo.plegable{cursor:pointer;user-select:none;border-radius:6px}
.at-menu .titulo.plegable:hover{color:#b9c3d1;background:#1a212c}
.at-menu .titulo.plegable::before{content:'▾';display:inline-block;width:12px;
  transition:transform .15s}
.at-menu .seccion.plegada .titulo.plegable::before{transform:rotate(-90deg)}
.at-menu .titulo .cuantas{color:#5f6876;font-size:10px;margin-left:4px}.at-menu .at-lista:not(.buscando) .seccion.plegada > :not(.titulo){display:none}
/* Las sugerencias mientras escribis "/algo" en la caja, como en Claude Code. */
/* ⭐ 2026-11-11, "quedo bien feo": dos columnas limpias como Claude Code (nombre a la
   izquierda con ancho fijo, la descripcion apagada al lado) y nada mas. La categoria
   repetida en cada renglon era ruido: ahora sale una sola vez, de titulito, cuando cambia. */
.at-sug{position:fixed;z-index:1200;max-height:min(42vh,300px);overflow-y:auto;
  background:#11151d;border:1px solid #232c3a;border-radius:10px;padding:4px;
  box-shadow:0 12px 32px rgba(0,0,0,.5);font-size:13px;scrollbar-width:thin}
.at-sug .fila{display:grid;grid-template-columns:var(--at-col,150px) 1fr;column-gap:14px;
  align-items:baseline;padding:4px 10px;border-radius:6px;cursor:pointer;line-height:1.4}
.at-sug .fila.activa{background:#1b2738}
.at-sug .fila.activa .nombre{color:#cfe7ff}
.at-sug .nombre{color:#7fb8ec;font-family:ui-monospace,Consolas,monospace;font-size:12.5px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.at-sug .desc{color:#6f7886;font-size:12px;min-width:0;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.at-sug .fila.activa .desc{color:#9aa4b2}
.at-sug .grupo{padding:7px 10px 2px;font-size:10px;letter-spacing:.06em;text-transform:uppercase;
  color:#4f5867}
.at-sug .grupo:first-child{padding-top:3px}
.at-sug .grupo.plegable{cursor:pointer;user-select:none;border-radius:6px}
.at-sug .grupo.plegable:hover{color:#9aa4b2}
.at-sug .grupo.plegable::before{content:'▾';display:inline-block;width:12px;transition:transform .12s}
.at-sug .grupo.plegado::before{transform:rotate(-90deg)}
.at-sug .grupo .cuantas{opacity:.7;margin-left:3px;letter-spacing:0}
.at-sug .ayuda{padding:5px 10px 3px;font-size:10.5px;color:#4f5867;border-top:1px solid #1d2531;
  margin-top:4px}
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

  /* Cada seccion (Skills, Comandos, Prompts) va envuelta: asi el buscador puede
     esconder el titulo de una seccion que se quedo sin nada que mostrar. */
  /* ⭐ Cada bloque se pliega tocando su título (pedido de Martín, 2026-11-11: "esas
     subcarpetas las tengo que poder compactar"). Lo plegado se recuerda en el navegador
     por nombre de bloque, así el menú vuelve a abrirse como lo dejaste. Mientras buscás
     se ve todo igual: un resultado escondido adentro de un bloque plegado sería un
     buscador que miente. */
  const CLAVE_PLEGADAS = 'atajos.plegadas';
  const plegadas = () => {
    try { return JSON.parse(localStorage.getItem(CLAVE_PLEGADAS) || '[]'); } catch (e) { return []; }
  };
  function plegar(titulo, si) {
    const l = plegadas().filter(t => t !== titulo);
    if (si) l.push(titulo);
    try { localStorage.setItem(CLAVE_PLEGADAS, JSON.stringify(l)); } catch (e) {}
  }
  const seccion = (titulo, html) => {
    const n = (html.match(/class="fila /g) || []).length;
    const plegada = n && plegadas().includes(titulo) ? ' plegada' : '';
    return '<div class="seccion' + plegada + '" data-titulo="' + titulo.replace(/"/g, '&quot;') + '">' +
      '<div class="titulo' + (n ? ' plegable' : '') + '">' + titulo +
      (n ? ' <span class="cuantas">' + n + '</span>' : '') + '</div>' + html + '</div>';
  };
  /* Engancha el toque en los títulos de una lista recién pintada. */
  function plegables(lista, listo) {
    lista.querySelectorAll('.seccion .titulo.plegable').forEach(t => {
      t.onclick = () => {
        const sec = t.parentElement;
        const si = !sec.classList.contains('plegada');
        sec.classList.toggle('plegada', si);
        plegar(sec.dataset.titulo, si);
        if (listo) listo();
        // El cursor vuelve al buscador: si no, lo que tipeás después cae en los atajos
        // de una tecla de la pantalla en vez de buscar.
        const campo = abierto && abierto.menu.querySelector('.at-buscar input');
        if (campo && !matchMedia('(pointer:coarse)').matches) campo.focus();
      };
    });
  }

  /* Sin tildes y en minuscula: "compactacion" tiene que encontrar "compactación". */
  const normal = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  /* El buscador (pedido de Martin, 2026-09-30: "un buscador de skills en el mismo
     desplegable, tanto para la pc como para el celu"). Filtra por nombre Y por
     descripcion, y cada palabra tiene que aparecer en algun lado: "video film" encuentra
     procedural-film aunque "video" este solo en la descripcion. No va al servidor:
     filtra lo que el menu ya tiene dibujado, asi que responde al instante. */
  function filtrar(lista, q) {
    const palabras = normal(q).split(/\s+/).filter(Boolean);
    const buscando = palabras.length > 0;
    lista.classList.toggle('buscando', buscando);   // buscando, lo plegado se abre
    let primera = null;
    lista.querySelectorAll('.seccion').forEach(sec => {
      let alguna = false;
      sec.querySelectorAll('.fila').forEach(f => {
        const texto = normal((f.querySelector('.nombre') || {}).textContent + ' ' +
                             (f.querySelector('.desc') || {}).textContent);
        const ve = palabras.every(p => texto.includes(p));
        f.style.display = ve ? '' : 'none';
        f.classList.remove('primera');
        if (ve) {
          alguna = true;
          if (buscando && !primera && !f.classList.contains('rota')) primera = f;
        }
      });
      // Los carteles tipo "no tenés ningún prompt" no son resultados de nada.
      // "Leyendo…" (`.cargando`) si se queda: todavia no hay nada que filtrar.
      sec.querySelectorAll('.aviso:not(.cargando)').forEach(a => {
        a.style.display = buscando ? 'none' : '';
      });
      sec.style.display = alguna || !buscando || sec.querySelector('.cargando') ? '' : 'none';
    });
    const cargando = !!lista.querySelector('.cargando');
    // La que se elige con Enter queda marcada, para que Enter no sea una sorpresa.
    if (primera) primera.classList.add('primera');
    const pie = lista.querySelector('.pie');
    if (pie) pie.style.display = buscando ? 'none' : '';
    let nada = lista.querySelector('.at-nada');
    if (buscando && !primera && !cargando) {
      if (!nada) {
        nada = document.createElement('div');
        nada.className = 'aviso at-nada';
        lista.appendChild(nada);
      }
      nada.textContent = 'Nada coincide con «' + q.trim() + '».';
    } else if (nada) {
      nada.remove();
    }
  }

  /* ⭐ Varias skills de una (pedido de Martin, 2026-11-11): tocar una la escribe en la
     caja y el menu QUEDA ABIERTO, con la fila tildada, para seguir eligiendo. Se cierra
     tocando afuera, con Escape o con el mismo rayo. Una ya elegida no se repite. En la
     compu el buscador se limpia y recupera el cursor, asi se busca la siguiente al toque. */
  function elegirSkill(f, op) {
    if (f.classList.contains('elegida')) return;
    op.insertar(f.dataset.id + ' ');
    f.classList.add('elegida');
    const campo = abierto && abierto.menu.querySelector('.at-buscar input');
    if (campo && !matchMedia('(pointer:coarse)').matches) {
      if (campo.value) { campo.value = ''; campo.dispatchEvent(new Event('input')); }
      campo.focus();
    }
  }

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
  function pintarCodex(r, menu, listo, op, acciones) {
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
    menu.innerHTML = seccion('Skills',
      skillsHtml || '<div class="aviso">No pude leer las skills de Codex ' +
       '(¿el panel viejo? reinicialo).</div>') +
      seccion('Prompts de Codex',
        promptsHtml || '<div class="aviso">Todavía no tenés ningún prompt de Codex.</div>') +
      seccion('Comandos', comandosHtml) +
      '<div class="pie">Las skills son las mismas que las de Claude (están enlazadas en ' +
      '<b>' + esc(r.carpeta_skills || '~/.codex/skills') + '</b>), pero acá se llaman con ' +
      '<b>$nombre</b>.<br>Un prompt es otra cosa: un archivo <b>' +
      esc(r.carpeta || '~/.codex/prompts') + '\\&lt;nombre&gt;.md</b> que se invoca con ' +
      'la barrita. Los dos aparecen acá al abrir el menú, sin reiniciar nada.</div>';
    menu.querySelectorAll('.fila.skill').forEach(f => {
      f.onclick = () => elegirSkill(f, op);
    });
    menu.querySelectorAll('.fila.comando').forEach(f => {
      const c = COMANDOS.find(x => x.id === f.dataset.id);
      f.onclick = () => { cerrar(); if (c && acciones[c.accion]) acciones[c.accion](); };
    });
    plegables(menu, listo);
    listo();
  }

  /* ⭐ Sugerir mientras escribis (pedido de Martin, 2026-11-11: "cuando escribo / que
     me vayan apareciendo las skills, que mientras escribo me la sugiera, tal como lo
     hace Claude Code, y que con Tab se complete").
     Se dispara cuando la PALABRA donde esta el cursor empieza con "/" (o "$" en una
     charla de Codex), no solo al principio de la caja: Martin encadena varias skills
     en un mismo mensaje. Flechas para moverse, Tab o Enter para completar, Escape
     para cerrar. Un comando que en esta pantalla es un boton (/compact, /model…) lo
     aprieta, igual que en el menu ⚡.
     ⚠ Las teclas se atienden en la fase de CAPTURA de la caja y se cortan ahi: si no,
     el Enter de la pagina manda el mensaje y las flechas recorren tus mensajes viejos. */
  function sugerir(op) {
    const caja = op.caja;
    let datos = null, datosClave = '', datosHora = 0, pidiendo = null;
    let caja_sug = null, items = [], bloques = [], activa = 0, rango = null, descartado = '';
    const GRUPOS = {skill: 'Skills', comando: 'Comandos', tuyo: 'Tus comandos', prompt: 'Prompts'};
    /* Cuantas letras hay que cambiar, sacar o poner para pasar de una palabra a la otra. */
    function distancia(a, b) {
      let fila = Array.from({length: b.length + 1}, (_, k) => k);
      for (let x = 1; x <= a.length; x++) {
        const nueva = [x];
        for (let y = 1; y <= b.length; y++)
          nueva[y] = Math.min(fila[y] + 1, nueva[y - 1] + 1, fila[y - 1] + (a[x - 1] === b[y - 1] ? 0 : 1));
        fila = nueva;
      }
      return fila[b.length];
    }

    const claveSesion = () => {
      const s = op.sesion() || {};
      return s.de ? 'de=' + s.de : 'sid=' + encodeURIComponent(s.sid || '') +
                                   '&cwd=' + encodeURIComponent(s.cwd || '');
    };
    /* La lista se pide al servidor la primera vez que tipeas la barrita y se reusa un
       minuto: cada tecla filtra lo que ya esta en memoria, sin ir y venir. */
    function traer() {
      const clave = claveSesion();
      if (datos && clave === datosClave && Date.now() - datosHora < 60000) return;
      if (pidiendo === clave) return;
      pidiendo = clave;
      fetch('/skills?' + clave).then(r => r.json()).then(r => {
        if (pidiendo !== clave) return;
        datos = r; datosClave = clave; datosHora = Date.now(); pidiendo = null;
        mirar();
      }).catch(() => { pidiendo = null; });
    }

    function catalogo() {
      if (!datos || !datos.ok || datosClave !== claveSesion()) return [];
      const acciones = op.acciones || {};
      if (datos.cerebro === 'codex') {
        return (datos.skills || []).map(s => ({id: '$' + s.nombre, desc: s.descripcion, cat: 'skill'}))
          .concat((datos.prompts || []).map(c => ({id: '/' + c.nombre, desc: c.descripcion, cat: 'prompt'})))
          .concat(COMANDOS.filter(c => c.accion && acciones[c.accion])
            .map(c => ({id: c.id, desc: descDe(c, 'codex'), cat: 'comando', accion: c.accion})));
      }
      return (datos.skills || []).map(s => ({id: '/' + s.nombre, desc: s.descripcion,
                                             cat: s.categoria || 'skill'}))
        .concat(COMANDOS.map(c => ({id: c.id, desc: c.desc, cat: 'comando',
                                    accion: c.accion && acciones[c.accion] ? c.accion : ''})))
        .concat((datos.comandos || []).map(c => ({id: '/' + c.nombre, desc: c.descripcion, cat: 'tuyo'})));
    }

    /* La palabra que se esta escribiendo, del espacio anterior hasta el cursor. */
    function palabra() {
      const fin = caja.selectionStart;
      if (fin !== caja.selectionEnd) return null;
      const antes = caja.value.slice(0, fin);
      const ini = Math.max(antes.lastIndexOf(' '), antes.lastIndexOf('\n'), antes.lastIndexOf('\t')) + 1;
      const p = antes.slice(ini);
      // Una ruta ("/etc/hosts", "C:/algo") no es una skill: una sola barrita, al principio.
      if (!/^[\/$][\w:.-]*$/.test(p)) return null;
      // Si el cursor quedo en el medio de una palabra, tampoco: se completaria mal.
      if (/^\S/.test(caja.value.slice(fin))) return null;
      return {ini, fin, texto: p};
    }

    function ocultar() {
      if (caja_sug) { caja_sug.remove(); caja_sug = null; }
      items = []; bloques = []; rango = null;
    }

    function pintar() {
      if (!caja_sug) {
        caja_sug = document.createElement('div');
        caja_sug.className = 'at-sug';
        document.body.appendChild(caja_sug);
        // mousedown y no click: que la caja no pierda el foco (y el cursor) al tocar.
        caja_sug.addEventListener('mousedown', e => {
          const f = e.target.closest('.fila');
          const g = e.target.closest('.grupo.plegable');
          e.preventDefault();
          if (f) { activa = +f.dataset.i; completar(); }
          else if (g) {
            // Lo plegado es lo mismo que en el menu ⚡: se pliega aca y queda plegado alla.
            plegar(g.dataset.grupo, !g.classList.contains('plegado'));
            // Que la lista no salte hasta el renglon marcado: queda donde la estabas mirando.
            const arriba = caja_sug.scrollTop;
            mirar();
            if (caja_sug) caja_sug.scrollTop = arriba;
          }
        });
      }
      let i = 0;
      caja_sug.innerHTML = bloques.map(b =>
        '<div class="grupo plegable' + (b.abierto ? '' : ' plegado') + '" data-grupo="' +
          esc(b.nombre) + '">' + esc(b.nombre) + ' <span class="cuantas">' + b.filas.length +
          '</span></div>' +
        (b.abierto ? b.filas.map(it => {
          const j = i++;
          return '<div class="fila' + (j === activa ? ' activa' : '') + '" data-i="' + j + '">' +
            '<span class="nombre">' + esc(it.id) + '</span>' +
            '<span class="desc">' + esc(it.desc) + '</span></div>';
        }).join('') : '')
      ).join('') +
        '<div class="ayuda">Tab completa · ↑↓ elegir · tocá un bloque para plegarlo · Esc cerrar</div>';
      // La columna del nombre se ajusta al mas largo de los que se ven (con tope).
      const largo = items.reduce((m, it) => Math.max(m, it.id.length), 6);
      caja_sug.style.setProperty('--at-col', Math.min(largo + 1, 24) + 'ch');
      const r = caja.getBoundingClientRect();
      const ancho = Math.max(320, Math.min(r.width, 620));
      caja_sug.style.width = ancho + 'px';
      caja_sug.style.left = Math.max(8, Math.min(r.left, innerWidth - ancho - 8)) + 'px';
      caja_sug.style.bottom = (innerHeight - r.top + 6) + 'px';
      const act = caja_sug.querySelector('.fila.activa');
      if (act) act.scrollIntoView({block: 'nearest'});
    }

    function mirar() {
      const p = palabra();
      if (!p || p.texto === descartado) { ocultar(); return; }
      descartado = '';
      traer();
      const q = normal(p.texto.slice(1));
      const marca = p.texto[0];
      const puntaje = it => {
        const n = normal(it.id.slice(1));
        if (n.startsWith(q)) return 0;
        if (n.includes(q)) return 1;
        return q && normal(it.desc).includes(q) ? 2 : -1;
      };
      // Con "$" solo lo que se invoca con "$" (Codex); con "/" todo lo demas.
      const hallados = catalogo()
        .filter(it => (it.id[0] === '$') === (marca === '$'))
        .map((it, i) => ({it, p: puntaje(it), i}))
        .filter(x => x.p >= 0);
      if (!hallados.length) { ocultar(); return; }
      /* ⭐ Los bloques se pliegan como en el ⚡ (pedido de Martin, 2026-11-11: "tengo que
         poder compactar las carpetas desde aca tambien, a menos que escriba la skill que
         sea exacta o muy cerca por 3 caracteres"). Un bloque plegado muestra solo su
         titulo con cuantas coinciden; se abre solo, mientras buscas, si adentro hay una
         skill a 3 letras o menos de lo escrito ("/chie" abre el de /chief; "/gr" no). */
      const plegados = plegadas();
      const porGrupo = new Map();
      for (const x of hallados) {
        const g = GRUPOS[x.it.cat] || x.it.cat;
        if (!porGrupo.has(g)) porGrupo.set(g, []);
        porGrupo.get(g).push(x);
      }
      bloques = [...porGrupo].map(([nombre, xs]) => {
        xs.sort((a, b) => a.p - b.p || a.i - b.i);
        const cerca = q.length >= 2 && xs.some(x => distancia(q, normal(x.it.id.slice(1))) <= 3);
        return {nombre, filas: xs.map(x => x.it), abierto: !plegados.includes(nombre) || cerca,
                mejor: Math.min(...xs.map(x => x.p * 1e4 + x.i))};
      });
      // Buscando, primero el bloque que tiene lo mas parecido; sin buscar, el orden de siempre.
      if (q) bloques.sort((a, b) => a.mejor - b.mejor);
      // Si la que estaba marcada sigue a la vista, sigue marcada.
      const antes = items[activa] && items[activa].id;
      items = bloques.filter(b => b.abierto).flatMap(b => b.filas);
      const j = items.findIndex(it => it.id === antes);
      activa = j >= 0 ? j : 0;
      rango = p;
      pintar();
    }

    function completar() {
      const it = items[activa];
      if (!it || !rango) return;
      const {ini, fin} = rango;
      ocultar();
      if (it.accion) {
        // Es un boton de la pantalla: se saca la barrita escrita y se aprieta.
        caja.value = caja.value.slice(0, ini) + caja.value.slice(fin);
        caja.setSelectionRange(ini, ini);
        caja.dispatchEvent(new Event('input', {bubbles: true}));
        (op.acciones || {})[it.accion]();
        return;
      }
      const resto = caja.value.slice(fin).replace(/^ +/, '');
      caja.value = caja.value.slice(0, ini) + it.id + ' ' + resto;
      const pos = ini + it.id.length + 1;
      caja.setSelectionRange(pos, pos);
      // Que la pagina se entere (alto de la caja, borrador guardado), como si lo tipearas.
      caja.dispatchEvent(new Event('input', {bubbles: true}));
      caja.focus();
    }

    caja.addEventListener('input', mirar);
    caja.addEventListener('click', mirar);
    caja.addEventListener('blur', () => setTimeout(() => {
      if (document.activeElement !== caja) ocultar();
    }, 120));
    addEventListener('resize', () => { if (caja_sug) pintar(); });
    caja.addEventListener('keydown', e => {
      if (!caja_sug) return;
      if (e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === 'Escape') {
        descartado = rango ? rango.texto : ''; ocultar();
        e.preventDefault(); e.stopImmediatePropagation(); return;
      }
      // Con todos los bloques plegados no hay nada que elegir: las teclas siguen su camino.
      if (!items.length) return;
      let usada = true;
      if (e.key === 'ArrowDown') activa = (activa + 1) % items.length;
      else if (e.key === 'ArrowUp') activa = (activa - 1 + items.length) % items.length;
      else if ((e.key === 'Tab' && !e.shiftKey) || (e.key === 'Enter' && !e.shiftKey)) completar();
      else if (e.key === 'Escape') { descartado = rango ? rango.texto : ''; ocultar(); }
      else usada = false;
      if (!usada) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (caja_sug) pintar();
    }, true);
  }

  function montar(op) {
    if (!op || !op.contenedor) return;
    if (op.caja) sugerir(op);
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
    /* `icono` (2026-11-10) es para la compu: ahi el rayo es un icono de linea, de la misma
       familia que los botones de al lado. Es marcado que escribe la pagina, no texto de
       nadie de afuera; sin `icono` todo sigue como antes. */
    if (op.icono) boton.innerHTML = op.icono;
    else boton.textContent = op.etiqueta || '⚡ Skills y comandos';
    boton.title = 'Skills y comandos disponibles para esta charla';
    boton.setAttribute('aria-label', 'Skills y comandos');
    op.contenedor.appendChild(boton);

    boton.onclick = () => abrir(boton, async (menu, acomodar) => {
      const acciones = op.acciones || {};
      /* El campo se arma UNA vez y la lista se repinta abajo: si se rearmara con la
         lista, lo que escribiste mientras decia "Leyendo…" se borraba al llegar. */
      menu.innerHTML = '<div class="at-buscar"><input type="search" ' +
        'placeholder="Buscar skill o comando…" autocomplete="off" autocapitalize="off" ' +
        'spellcheck="false" aria-label="Buscar skill o comando"></div>' +
        '<div class="at-lista"></div>';
      const campo = menu.querySelector('.at-buscar input');
      const lista = menu.querySelector('.at-lista');
      // Al filtrar cambia el alto del menu: se reubica para no irse de la pantalla.
      const listo = () => { filtrar(lista, campo.value); acomodar(); };
      campo.oninput = listo;
      /* ⚠ El campo corta el teclado (la leccion del menu de carpetas en INTERFAZ.md):
         si no, los atajos de una tecla de la pantalla se disparan mientras escribis.
         Por eso Escape se atiende aca: primero borra lo escrito, despues cierra. */
      const corta = e => e.stopPropagation();
      campo.onkeyup = corta;
      campo.onkeypress = corta;
      campo.onkeydown = e => {
        e.stopPropagation();
        if (e.key === 'Escape') {
          e.preventDefault();
          if (campo.value) { campo.value = ''; listo(); } else cerrar();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          const f = lista.querySelector('.fila.primera');
          if (f) f.click();
        }
      };
      /* En la compu el cursor ya queda en el buscador. En el celular NO: abrir el
         teclado solo tapa medio menu y la mayoria de las veces se elige tocando. */
      if (!matchMedia('(pointer:coarse)').matches) campo.focus();
      const pintar = r => {
        const ok = !!(r && r.ok);
        /* ⭐ Una charla de Codex no tiene skills de Claude: tiene sus propios prompts
           (decisión de Martín, 2026-08-23). Y si todavía no creó ninguno, el menú lo
           dice y explica dónde se crean, en vez de salir en blanco — que se lee como
           "esta pantalla está rota" y no como "no tenés ninguno todavía". */
        if (ok && r.cerebro === 'codex') return pintarCodex(r, lista, listo, op, acciones);
        /* ⭐ Un bloque por categoría (pedido de Martín, 2026-11-11: "me gustaría poder
           agrupar las skills por categoría"). Las categorías y su orden los pone el
           servidor (`CATEGORIAS` en app/nucleo/skills.py) y las skills llegan ya juntas;
           acá se abre un bloque nuevo cada vez que cambia. Cada bloque es una `.seccion`,
           así el buscador esconde solo el título de una categoría que quedó vacía. Un
           panel viejo que no manda categoría cae todo en un único bloque "Skills". */
        const grupos = [];
        if (ok) (r.skills || []).forEach(s => {
          const cat = s.categoria || 'Skills';
          if (!grupos.length || grupos[grupos.length - 1].cat !== cat) grupos.push({cat, html: ''});
          grupos[grupos.length - 1].html +=
            filaHtml('/' + s.nombre, s.descripcion, chapaDe(s.nombre, r), 'skill');
        });
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
        const skillsSecciones = r === null
          ? seccion('Skills', '<div class="aviso cargando">Leyendo…</div>')
          : !ok
          ? seccion('Skills', '<div class="aviso">No pude leer las skills (¿el panel viejo? reinicialo).</div>')
          : (grupos.length || rotasHtml)
          ? grupos.map(g => seccion(esc(g.cat), g.html)).join('') +
            (rotasHtml ? seccion('Sin terminar', rotasHtml) : '')
          : seccion('Skills', '<div class="aviso">No hay skills instaladas.</div>');
        lista.innerHTML = skillsSecciones +
          seccion('Comandos', comandosHtml) +
          '<div class="pie">Las skills se escriben en la caja. Los comandos con equivalente ' +
          'en esta pantalla ejecutan ese control.<br>Una skill nueva va en ' +
          '<b>~/.claude/skills/&lt;nombre&gt;/SKILL.md</b> y aparece acá al abrir el menú, ' +
          'sin reiniciar nada.</div>';
        lista.querySelectorAll('.fila.skill').forEach(f => {
          f.onclick = () => elegirSkill(f, op);
        });
        lista.querySelectorAll('.fila.comando').forEach(f => {
          const c = COMANDOS.find(x => x.id === f.dataset.id);
          f.onclick = () => {
            cerrar();
            if (c && c.accion && acciones[c.accion]) acciones[c.accion]();
            else op.insertar(f.dataset.id + ' ');
          };
        });
        plegables(lista, listo);
        listo();
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
