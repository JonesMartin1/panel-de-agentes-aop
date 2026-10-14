"""Sonda contra el CLI de VERDAD: ¿llega el texto en pedacitos con el proceso VIVO?

⚠ Esta NO es una prueba gratis: lanza `claude` de verdad y GASTA TOKENS (poco: modelo
chico y pedidos cortos). Por eso se llama `sonda_` y no `probar_`.

Lo que comprueba, que es el supuesto entero del texto en vivo de `/sesiones` (2026-09-27):

  1. con `--include-partial-messages` y el proceso VIVO entre turnos (`--input-format
     stream-json`, igual que el panel) llegan los `stream_event` con `text_delta`;
  2. llegan en TODOS los turnos, no solo en el primero;
  3. llegan con VARIAS sesiones a la vez (el bug #15055 decia que el 20-70 % de las
     sesiones simultaneas no recibian ninguno);
  4. el texto llega de a poco y no todo junto al final (si no, el en vivo no sirve de nada);
  5. los pedacitos pegados dan EXACTAMENTE el texto del mensaje completo.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_texto_en_vivo
    D:/IA/envs/wpp/python.exe -m pruebas.sonda_texto_en_vivo --sesiones 3 --modelo opus

Por que existe: los issues #17956 y #15055 de anthropics/claude-code dicen que en este modo
los pedacitos no llegaban o llegaban a medias, y se cerraron sin arreglo. Eran de versiones
viejas (2.0.75 y 2.1.5), pero hasta medirlo en esta maquina no se sabe.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.voz import seguir
from app.voz import sesiones_movil as sm

TURNOS = [
    "Conta del 1 al 60, un numero por linea, sin ningun otro texto.",
    # El segundo turno obliga a usar una herramienta: el texto de DESPUES de una
    # herramienta es justo el que el bug #96439 dice que llega de golpe con pensamiento.
    "Usa la herramienta Read para leer LEEME.md y despues escribi un parrafo de unas "
    "80 palabras sobre de que trata. No uses ninguna otra herramienta.",
]
# ⚠ Corre en una carpeta TEMPORAL, no en el proyecto: la primera version corria en la
# raiz y dejaba sus charlas de prueba mezcladas con las de Martin en `/sesiones`
# (2026-09-27, hubo que borrar cinco a mano). Al terminar se borra todo.
import shutil  # noqa: E402
import tempfile  # noqa: E402
CARPETA = Path(tempfile.mkdtemp(prefix="sonda_envivo_"))
(CARPETA / "LEEME.md").write_text(
    "# Faro de prueba\n\nUn faro en la costa guia a los barcos de noche con un destello "
    "que se repite cada diez segundos.\n", encoding="utf-8")


def _arg(nombre, defecto):
    if nombre in sys.argv:
        return sys.argv[sys.argv.index(nombre) + 1]
    return defecto


def correr_sesion(n, modelo, esfuerzo, salida):
    cmd = [sm._claude_bin(), "-p",
           "--input-format", "stream-json", "--output-format", "stream-json",
           "--verbose", "--include-partial-messages", "--model", modelo,
           "--permission-mode", "default", "--permission-prompt-tool", "stdio",
           "--allowedTools", "Read"]
    if esfuerzo:
        cmd += ["--effort", esfuerzo]
    p = subprocess.Popen(cmd, cwd=str(CARPETA), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         encoding="utf-8", errors="replace", bufsize=1,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    turnos = []
    try:
        for pedido in TURNOS:
            t0 = time.time()
            p.stdin.write(json.dumps({"type": "user", "message": {
                "role": "user", "content": [{"type": "text", "text": pedido}]}}) + "\n")
            p.stdin.flush()
            t = {"eventos": 0, "deltas": [], "herramientas": [], "final": [], "uuids": [],
                 "primer_delta": None, "reintentos": 0, "result": None}
            limite = t0 + 240
            while time.time() < limite:
                linea = p.stdout.readline()
                if not linea:
                    break
                linea = linea.strip()
                if not linea.startswith("{"):
                    continue
                d = json.loads(linea)
                ahora = time.time() - t0
                tipo = d.get("type")
                if tipo == "stream_event":
                    t["eventos"] += 1
                    ev = d.get("event") or {}
                    if ev.get("type") == "content_block_delta":
                        delta = ev.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            t["deltas"].append((ahora, delta.get("text") or ""))
                            if t["primer_delta"] is None:
                                t["primer_delta"] = ahora
                    elif ev.get("type") == "content_block_start":
                        b = ev.get("content_block") or {}
                        if b.get("type") == "tool_use":
                            t["herramientas"].append((ahora, b.get("name")))
                elif tipo == "assistant":
                    for b in (d.get("message") or {}).get("content") or []:
                        if b.get("type") == "text":
                            t["final"].append((ahora, b.get("text") or ""))
                    # ⭐ El borrador de la pantalla se cambia por el mensaje del disco
                    # buscandolo por este `uuid`: si el del chorro no fuera el mismo que
                    # queda en el .jsonl, el borrador no se iria nunca o se iria antes.
                    sid = d.get("session_id") or ""
                    arch = seguir.carpeta_de(CARPETA) / f"{sid}.jsonl"
                    try:
                        ya = (d.get("uuid") or "?") in arch.read_text(encoding="utf-8",
                                                                      errors="replace")
                    except OSError:
                        ya = False
                    t["uuids"].append((sid, d.get("uuid") or "", ya))
                elif tipo == "system" and d.get("subtype") == "api_retry":
                    t["reintentos"] += 1
                elif tipo == "result":
                    t["result"] = ahora
                    break
            turnos.append(t)
    finally:
        try:
            p.stdin.close()
            p.wait(timeout=20)
        except Exception:
            p.kill()
    salida[n] = turnos


def informe(n, turnos):
    fallas = []
    for i, t in enumerate(turnos, 1):
        texto_delta = "".join(x for _, x in t["deltas"])
        texto_final = "".join(x for _, x in t["final"])
        print(f"  sesion {n} · turno {i}: {t['eventos']} eventos, "
              f"{len(t['deltas'])} pedacitos de texto, reintentos {t['reintentos']}")
        if t["result"] is None:
            fallas.append(f"sesion {n} turno {i}: no termino (sin `result`)")
            continue
        if not t["deltas"]:
            fallas.append(f"sesion {n} turno {i}: CERO pedacitos de texto")
            continue
        # ¿Llego de a poco? Se mide que parte del texto llego en los ultimos 0,3 s: cerca
        # de 1 es "todo de golpe" (la misma medida del issue #96439).
        fin = t["deltas"][-1][0]
        total = sum(len(x) for _, x in t["deltas"]) or 1
        golpe = sum(len(x) for s, x in t["deltas"] if s >= fin - 0.3) / total
        primero = t["primer_delta"]
        print(f"     primer pedacito a los {primero:.1f} s, ultimo a los {fin:.1f} s, "
              f"termino a los {t['result']:.1f} s · de golpe al final: {golpe:.0%}")
        if t["herramientas"]:
            print("     herramientas vistas al nacer: "
                  + ", ".join(f"{nombre} ({s:.1f} s)" for s, nombre in t["herramientas"]))
        # ¿El uuid del chorro es el mismo que quedo en el disco? Se mira al final, con el
        # turno cerrado; y se cuenta cuantos YA estaban escritos al llegar por el chorro.
        faltan_disco = []
        for sid, u, _ya in t["uuids"]:
            arch = seguir.carpeta_de(CARPETA) / f"{sid}.jsonl"
            try:
                if u not in arch.read_text(encoding="utf-8", errors="replace"):
                    faltan_disco.append(u)
            except OSError:
                faltan_disco.append(u)
        ya = sum(1 for *_x, y in t["uuids"] if y)
        print(f"     mensajes completos: {len(t['uuids'])}, ya escritos en el disco al "
              f"llegar: {ya}")
        if faltan_disco:
            fallas.append(f"sesion {n} turno {i}: {len(faltan_disco)} uuid del chorro no "
                          "estan en el .jsonl")
        if texto_delta != texto_final:
            fallas.append(f"sesion {n} turno {i}: los pedacitos NO dan el texto final "
                          f"({len(texto_delta)} contra {len(texto_final)} letras)")
        if len(t["deltas"]) >= 5 and golpe > 0.8:
            if t["herramientas"]:
                # ⚠ Medido el 2026-09-27 con Opus 5.5 y el CLI 2.1.283: despues de una
                # herramienta, los 34 pedacitos llegaron en el mismo instante. Es el bug
                # #96439 de Anthropic (pasa igual en la terminal de Claude Code), no del
                # panel: se avisa y no se cuenta como falla. Si un dia deja de salir este
                # aviso con Opus, lo arreglaron.
                print(f"     AVISO: despues de la herramienta llego de golpe ({golpe:.0%}) "
                      "— bug #96439 de Anthropic, no del panel")
            else:
                fallas.append(f"sesion {n} turno {i}: el texto llego de golpe ({golpe:.0%})")
    return fallas


def main():
    sesiones = int(_arg("--sesiones", "2"))
    modelo = _arg("--modelo", "haiku")
    esfuerzo = _arg("--esfuerzo", "")
    print(f"Lanzando {sesiones} sesiones vivas a la vez con {modelo}"
          f"{' / ' + esfuerzo if esfuerzo else ''}, {len(TURNOS)} turnos cada una...\n")
    salida = {}
    hilos = [threading.Thread(target=correr_sesion, args=(n, modelo, esfuerzo, salida))
             for n in range(1, sesiones + 1)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    fallas = []
    for n in sorted(salida):
        fallas += informe(n, salida[n])
    faltan = sesiones - len(salida)
    if faltan:
        fallas.append(f"{faltan} sesiones no devolvieron nada")
    print()
    if fallas:
        print("FALLA:")
        for f in fallas:
            print("  -", f)
        return 1
    print("OK: el texto llega en pedacitos en todos los turnos y en todas las sesiones.")
    return 0


def limpiar():
    """Borra la carpeta temporal y las charlas que dejo en ~/.claude/projects."""
    shutil.rmtree(seguir.carpeta_de(CARPETA), ignore_errors=True)
    shutil.rmtree(CARPETA, ignore_errors=True)


if __name__ == "__main__":
    try:
        codigo = main()
    finally:
        limpiar()
    sys.exit(codigo)
