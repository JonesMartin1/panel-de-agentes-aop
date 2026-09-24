#!/usr/bin/env python3
"""Le pone voz a un artefacto: genera la narracion y la deja embebida en el HTML.

    python narrar.py --html informe.html --guion guion.txt

Genera el audio con las tres voces, lo mete en el HTML como data URI y agrega el
reproductor. El resultado es una sola pagina que se escucha sin conexion y sin
depender de ningun servicio: por eso el audio va embebido y no por URL, ya que
el artefacto publicado bloquea cualquier pedido a otro host.

Es idempotente: si el HTML ya tenia narracion, la reemplaza.
"""
import argparse
import asyncio
import base64
import os
import re
import sys
import tempfile

try:
    import truststore  # noqa: F401
    truststore.inject_into_ssl()
except ImportError:
    # Sin truststore, en una maquina con proxy corporativo el TLS falla. Ver SKILL.md.
    pass

try:
    import edge_tts
except ImportError:
    sys.exit("Falta edge-tts. Instalalo con: pip install edge-tts truststore")

VOCES = [
    ("elena", "es-AR-ElenaNeural", "Elena \U0001F1E6\U0001F1F7"),
    ("dalia", "es-MX-DaliaNeural", "Dalia \U0001F1F2\U0001F1FD"),
    ("salome", "es-CO-SalomeNeural", "Salomé \U0001F1E8\U0001F1F4"),
]

MARCA_INI = "<!-- narrador:inicio -->"
MARCA_FIN = "<!-- narrador:fin -->"

# Las clases van prefijadas (nrr-) para no pisar el CSS del artefacto, y los
# colores salen de sus variables cuando existen, con un fallback propio.
CSS = """
<style>
  .nrr{display:flex;align-items:center;gap:14px;padding:14px 16px;margin:22px 0;
    background:var(--panel,#fff);border:1px solid var(--line,#e2dccd);
    border-radius:var(--radius,14px);box-shadow:var(--shadow,0 1px 3px rgba(23,35,59,.08),0 6px 22px rgba(23,35,59,.06))}
  .nrr-info{flex:1;min-width:0}
  .nrr-tit{font-weight:700;font-size:.95rem;display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;
    color:var(--ink,#17233b)}
  .nrr-voz{font-size:.72rem;font-weight:600;color:var(--brand,#ef6c1f)}
  .nrr-cap{font-size:.86rem;color:var(--ink-soft,#4a566e);margin-top:1px}
  .nrr-sw{display:flex;gap:8px;margin-top:11px;flex-wrap:wrap}
  .nrr-b{font-size:.82rem;padding:6px 13px;border-radius:20px;cursor:pointer;font-weight:600;
    border:1px solid var(--line,#e2dccd);background:var(--paper,#f4f1ea);color:var(--ink-soft,#4a566e);
    transition:transform .08s}
  .nrr-b.on{background:var(--brand,#ef6c1f);color:#fff;border-color:var(--brand,#ef6c1f)}
  .nrr-b:active{transform:scale(.96)}
  .nrr-b:focus-visible{outline:2px solid var(--brand,#ef6c1f);outline-offset:2px}
  .nrr audio{width:100%;margin-top:11px}
</style>
"""


def bloque(audios, minutos):
    botones = "".join(
        f'<button class="nrr-b{" on" if i == 0 else ""}" data-v="{k}">{n}</button>'
        for i, (k, _, n) in enumerate(VOCES)
    )
    nombres = ",".join(f'{k}:"{n}"' for k, _, n in VOCES)
    fuentes = ",".join(f'"{k}":"data:audio/mpeg;base64,{b64}"' for k, b64 in audios)
    primera = VOCES[0][0]
    return f"""{MARCA_INI}
{CSS}
<div class="nrr" id="nrr">
  <div class="nrr-info">
    <div class="nrr-tit">\U0001F50A Escuchá el resumen <span class="nrr-voz" id="nrr-voz"></span></div>
    <div class="nrr-cap">Voz neuronal (Microsoft, ≈{minutos} min). Elegí el acento y dale play.</div>
    <div class="nrr-sw">{botones}</div>
    <audio id="nrr-audio" controls preload="none"></audio>
  </div>
</div>
<script>
var NRR_AUDIO = {{{fuentes}}};
var NRR_NOMBRES = {{{nombres}}};
(function(){{
  var a = document.getElementById('nrr-audio');
  var hint = document.getElementById('nrr-voz');
  var btns = document.querySelectorAll('.nrr-b');
  function set(v, play){{
    a.src = NRR_AUDIO[v];
    hint.textContent = '· voz: ' + NRR_NOMBRES[v];
    btns.forEach(function(b){{ b.classList.toggle('on', b.dataset.v === v); }});
    if (play) a.play();
  }}
  btns.forEach(function(b){{ b.addEventListener('click', function(){{ set(b.dataset.v, true); }}); }});
  set('{primera}', false);
}})();
</script>
{MARCA_FIN}"""


def insertar(html, bloque_html):
    """Despues del encabezado, que es donde el lector espera el reproductor."""
    if MARCA_INI in html:  # ya tenia narracion: se reemplaza
        return re.sub(
            re.escape(MARCA_INI) + r".*?" + re.escape(MARCA_FIN),
            lambda _: bloque_html,
            html,
            flags=re.S,
        )
    for patron in (r"</header>", r"</h1>", r"<body[^>]*>"):
        m = re.search(patron, html, re.I)
        if m:
            return html[: m.end()] + "\n" + bloque_html + "\n" + html[m.end():]
    return bloque_html + "\n" + html


async def generar(texto, rate):
    # Los MP3 intermedios van a un temporal del sistema y no al directorio desde
    # donde se corre: la skill es global y se usa parada en cualquier proyecto,
    # no tiene por que dejarle basura al repo del cliente.
    salida = []
    with tempfile.TemporaryDirectory(prefix="narrador-") as tmpdir:
        for clave, voz, _ in VOCES:
            tmp = os.path.join(tmpdir, f"{clave}.mp3")
            await edge_tts.Communicate(texto, voz, rate=rate).save(tmp)
            with open(tmp, "rb") as fh:
                crudo = fh.read()
            salida.append((clave, base64.b64encode(crudo).decode()))
            print(f"   {clave:7s} {voz:20s} {len(crudo) / 1024:7.1f} KB")
    return salida


def main():
    p = argparse.ArgumentParser(description="Le pone narracion a un artefacto HTML")
    p.add_argument("--html", required=True, help="el artefacto a narrar (se modifica)")
    p.add_argument("--guion", required=True, help="archivo de texto con el guion hablado")
    p.add_argument("--rate", default="+6%", help="velocidad (default +6%%, suena natural)")
    a = p.parse_args()

    if not os.path.exists(a.html):
        sys.exit(f"No existe {a.html}")
    with open(a.guion, encoding="utf-8") as fh:
        texto = fh.read().strip()
    if not texto:
        sys.exit("El guion esta vacio")

    palabras = len(texto.split())
    minutos = max(1, round(palabras / 150))
    print(f"Guion: {palabras} palabras (~{minutos} min hablados)")
    if palabras > 900:
        print("   OJO: mas de 900 palabras. Con tres voces el peso se va cerca del tope")
        print("        de 16 MB del artefacto. Conviene acortar el guion.")

    audios = asyncio.run(generar(texto, a.rate))

    with open(a.html, encoding="utf-8") as fh:
        html = fh.read()
    nuevo = insertar(html, bloque(audios, minutos))
    with open(a.html, "w", encoding="utf-8") as fh:
        fh.write(nuevo)

    mb = len(nuevo.encode()) / 1024 / 1024
    print(f"\nOK -> {a.html}")
    print(f"   pesa {mb:.1f} MB " + ("(dentro del limite de 16 MB)" if mb < 16 else ">>> PASA EL LIMITE DE 16 MB"))


if __name__ == "__main__":
    main()
