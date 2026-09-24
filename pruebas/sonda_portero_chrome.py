"""Sonda contra el CLI de VERDAD: ¿anda el navegador sin el atajo del allowlist?

⚠ Esta NO es una prueba gratis: lanza un `claude` de verdad y GASTA TOKENS. Por eso se
llama `sonda_` y no `probar_`. Se corre a mano cuando hay que volver a comprobar el
supuesto, no en cada commit.

Lo que comprueba, que es el supuesto entero del arranque perezoso (2026-08-29):

  1. las herramientas del navegador siguen existiendo para la sesion;
  2. cada una llega por stdio como `can_use_tool` (o sea: hay un momento donde enterarse
     de que la sesion va a navegar, que es donde se abre la ventana);
  3. concederla desde el portero alcanza para que se EJECUTE de verdad.

Si el 3 fallara, todos los proyectos se quedarian sin navegador y el panel no lo diria.

    D:/IA/envs/wpp/python.exe -m pruebas.sonda_portero_chrome
    D:/IA/envs/wpp/python.exe -m pruebas.sonda_portero_chrome --sin-ask   # tiene que FALLAR

⚠⚠ **Por que existe esta sonda**: sacar el servidor del `--allowedTools` parecia
suficiente y NO lo es. Corriendola la primera vez, `list_connected_browsers` se ejecuto
**sin pedir ningun permiso**: el CLI concede solo las herramientas que considera de
lectura. Con el diseño de aquel momento, una sesion que arranca preguntando que
navegadores hay se habria encontrado con los ajenos y el suyo cerrado — y ninguna prueba
de las gratis se podia enterar, porque el que decide es el CLI. De ahi salio
`AJUSTES_CHROME`. Eso es lo que `--sin-ask` reproduce.

No abre ningun Chrome: usa el que ya este conectado y solo le pregunta cuales hay.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.voz import sesiones_movil as sm

PEDIDO = ("Usa la herramienta mcp__claude-in-chrome__list_connected_browsers y decime "
          "en una linea cuantos navegadores conectados hay. Nada mas que eso.")


def main():
    # ⚠ El allowlist sale de `_permitidas_de` de verdad: si alguien le devuelve el atajo
    # del servidor entero, esta sonda deja de medir lo que dice medir.
    permitidas = sm._permitidas_de("D:/IA/chrome-prueba", [])
    if any("claude-in-chrome" in p for p in permitidas):
        print("La sonda no sirve: el navegador volvio a ir permitido de arranque.")
        return 1
    cmd = [sm._claude_bin(), "-p",
           "--input-format", "stream-json", "--output-format", "stream-json",
           "--verbose", "--model", "sonnet",
           "--permission-mode", "default",
           "--permission-prompt-tool", "stdio",
           "--allowedTools", *permitidas,
           "--chrome", "--disallowedTools", sm.CHROME_JS]
    if "--sin-ask" not in sys.argv:
        # ⭐ La pieza que hace que TODA herramienta del navegador pida permiso, incluidas
        # las de solo lectura que el CLI concede por su cuenta. Con `--sin-ask` se corre
        # la sonda sin ella y tiene que FALLAR: asi se comprueba que la pieza hace falta
        # de verdad y no es un amuleto (fue justo lo que se descubrio midiendo).
        cmd += ["--settings", json.dumps(sm.AJUSTES_CHROME)]
    print("Lanzando el CLI sin el servidor del navegador en el allowlist...\n")
    p = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent.parent),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", bufsize=1,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    p.stdin.write(json.dumps({"type": "user", "message": {
        "role": "user", "content": [{"type": "text", "text": PEDIDO}]}}) + "\n")
    p.stdin.flush()

    pedidos, ejecutadas, respuesta = [], [], ""
    limite = time.time() + 180
    for linea in p.stdout:
        if time.time() > limite:
            break
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            d = json.loads(linea)
        except Exception:
            continue
        t = d.get("type")
        if t == "control_request":
            req = d.get("request") or {}
            nombre = str(req.get("tool_name") or "")
            if req.get("subtype") == "can_use_tool":
                pedidos.append(nombre)
                # El portero concede, igual que hace `_turno` sin lista de sitios.
                p.stdin.write(json.dumps({
                    "type": "control_response", "response": {
                        "subtype": "success", "request_id": d.get("request_id"),
                        "response": {"behavior": "allow",
                                     "updatedInput": req.get("input") or {}}}}) + "\n")
                p.stdin.flush()
        elif t == "user":
            # El resultado de una herramienta vuelve como mensaje de usuario.
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    ejecutadas.append(str(b.get("content"))[:400])
        elif t == "result":
            respuesta = str(d.get("result") or "")
            break
    try:
        p.stdin.close()
        p.wait(timeout=10)
    except Exception:
        p.kill()

    del_navegador = [n for n in pedidos if n.startswith(sm.CHROME_PREFIJO)]
    print(f"pedidos de permiso que llegaron: {pedidos or 'ninguno'}")
    print(f"de esos, del navegador: {del_navegador or 'ninguno'}")
    print(f"resultados de herramienta: {len(ejecutadas)}")
    for e in ejecutadas:
        print("   ", e.replace("\n", " ")[:200])
    print(f"\nrespuesta final: {respuesta[:300]}\n")

    bien = True
    for titulo, ok in (
            ("la herramienta del navegador EXISTE y la sesion la pidio",
             bool(del_navegador)),
            ("el pedido llego por stdio (hay donde abrir la ventana)",
             bool(del_navegador)),
            ("concederla alcanzo para que se EJECUTE",
             any("rowser" in e or "id" in e for e in ejecutadas))):
        print(f"  {'ok  ' if ok else 'MAL '} {titulo}")
        bien = bien and ok
    print(f"\n{'EL SUPUESTO SE SOSTIENE' if bien else 'REVISAR: el supuesto falla'}\n")
    return 0 if bien else 1


if __name__ == "__main__":
    raise SystemExit(main())
