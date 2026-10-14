"""El rastro con estado y detalle (2026-09-27): lo que no se hizo no puede verse como hecho,
y cada paso se despliega con su cambio o su salida, como en Claude Code.

Se arma una charla de mentira en una carpeta temporal (con el formato real del .jsonl de
Claude Code, copiado de una charla de verdad) y se mira lo que devuelven `_filas_de` y
`detalle_pasos`. No habla con Claude ni toca ninguna charla real.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_pasos_detalle
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_pasos_detalle --mutar
"""
import inspect
import json
import sys
import tempfile
import textwrap
from pathlib import Path

from app.voz import seguir, sesiones_movil as sm

VERDES, ROJOS = [], []


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def uso(tid, nombre, entrada, uuid):
    return {"type": "assistant", "uuid": uuid, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": nombre, "input": entrada}]}}


def resultado(tid, texto, error=False, extra=None):
    d = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": texto,
         **({"is_error": True} if error else {})}]}}
    if extra is not None:
        d["toolUseResult"] = extra
    return d


def armar(carpeta):
    lineas = [
        {"type": "user", "message": {"role": "user", "content": "arreglá el login"}},
        uso("t1", "Edit", {"file_path": "C:/p/app.py", "old_string": "a = 1",
                           "new_string": "a = 2"}, "u1"),
        resultado("t1", "The file C:/p/app.py has been updated.", extra={
            "filePath": "C:/p/app.py", "structuredPatch": [{
                "oldStart": 10, "oldLines": 3, "newStart": 10, "newLines": 3,
                "lines": [" def f():", "-    a = 1", "+    a = 2", "     return a"]}]}),
        uso("t2", "Bash", {"command": "pytest -q"}, "u2"),
        resultado("t2", "2 failed, 5 passed", error=True,
                  extra={"stdout": "2 failed, 5 passed", "stderr": ""}),
        # Tres "git push" seguidos: dos negados y uno que anduvo. NO se pueden juntar los
        # tres en "corrió: git push ×3" — escondería que dos nunca corrieron.
        uso("t3", "Bash", {"command": "git push"}, "u3"),
        resultado("t3", sm._MSJ_DENEGADO.format(tool="Bash"), error=True, extra="Error"),
        uso("t4", "Bash", {"command": "git push"}, "u4"),
        resultado("t4", sm._MSJ_DENEGADO.format(tool="Bash"), error=True, extra="Error"),
        uso("t5", "Bash", {"command": "git push"}, "u5"),
        resultado("t5", "Everything up-to-date", extra={"stdout": "Everything up-to-date"}),
        uso("t6", "Write", {"file_path": "C:/p/nuevo.txt", "content": "hola\nchau"}, "u6"),
        resultado("t6", "File created", extra={"type": "create", "filePath": "C:/p/nuevo.txt",
                                               "content": "hola\nchau", "structuredPatch": []}),
        uso("t7", "Read", {"file_path": "C:/p/largo.txt"}, "u7"),
        resultado("t7", "\n".join(f"linea {i}" for i in range(1000))),
        uso("t8", "Grep", {"pattern": "TODO"}, "u8"),    # sin resultado: todavía corriendo
        # Un subagente en segundo plano: el resultado solo dice "lo lancé"; lo que hizo
        # está en SU archivo, que se encuentra por el agentId.
        uso("t9", "Agent", {"description": "contar notas", "prompt": "..."}, "u9"),
        resultado("t9", "Async agent launched", extra={"isAsync": True,
                                                        "status": "async_launched",
                                                        "agentId": "abc123"}),
    ]
    cwd = str(carpeta / "proyecto")
    destino = seguir.carpeta_de(cwd)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "ses.jsonl").write_text("\n".join(json.dumps(x) for x in lineas) + "\n",
                                       encoding="utf-8")
    sub = destino / "ses" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "agent-abc123.jsonl").write_text("\n".join(json.dumps(x) for x in [
        uso("s1", "Glob", {"pattern": "*.txt"}, "v1"),
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hay 3 notas."}]}},
    ]) + "\n", encoding="utf-8")
    return cwd, "ses"


def correr_todo():
    tmp = Path(tempfile.mkdtemp(prefix="pasos_"))
    viejo = seguir.CLAUDE_PROYECTOS
    seguir.CLAUDE_PROYECTOS = tmp / "proyectos"
    sm._HILOS.clear()
    try:
        cwd, sid = armar(tmp)
        filas = sm._filas_de(seguir.carpeta_de(cwd) / f"{sid}.jsonl")
        pasos = [f for f in filas if f["de"] == "paso"]
        porid = {f["ids"][0]: f for f in pasos}

        print("\n1) Cada paso dice como le fue")
        ok(porid["t1"]["estado"] == "ok", "la edición anduvo")
        ok(porid["t2"]["estado"] == "error", "el comando que falló dice que falló")
        ok(porid["t3"]["estado"] == "negado", "el que se le negó dice que NO corrió")
        ok(porid["t8"]["estado"] == "", "el que todavía corre no tiene estado")

        print("\n2) Los repetidos se juntan solo si les fue igual")
        push = [p for p in pasos if p["base"] == "corrió: git push"]
        ok(len(push) == 2, f"'git push' ×3 queda en dos renglones, no en uno ({len(push)})")
        ok(push and push[0]["estado"] == "negado" and push[0]["veces"] == 2
           and push[0]["ids"] == ["t3", "t4"], "los dos negados juntos, con sus dos ids")
        ok(len(push) > 1 and push[1]["estado"] == "ok" and push[1]["veces"] == 1,
           "y el que anduvo, aparte")

        print("\n3) El detalle: el cambio como en Claude Code, y la salida")
        d = {x["nombre"] + ":" + x.get("comando", x.get("archivo", "")): x
             for x in sm.detalle_pasos(cwd, sid, ["t1", "t2", "t3", "t6", "t7", "t8"])}
        ed = d.get("Edit:C:/p/app.py", {})
        ok(ed.get("hunks", [{}])[0].get("lineas") == [" def f():", "-    a = 1", "+    a = 2",
                                                      "     return a"]
           and ed["hunks"][0]["nuevo"] == 10, "la edición trae el parche con su número de línea")
        ok(d.get("Bash:pytest -q", {}).get("salida") == "2 failed, 5 passed",
           "el comando trae lo que devolvió")
        neg = d.get("Bash:git push", {})
        ok(neg.get("estado") == "negado" and "denied" in neg.get("salida", ""),
           "el negado trae el motivo")
        nuevo = d.get("Write:C:/p/nuevo.txt", {})
        ok(nuevo.get("hunks", [{}])[0].get("lineas") == ["+hola", "+chau"],
           "un archivo nuevo se ve todo agregado")
        largo = d.get("Read:C:/p/largo.txt", {})
        ok(largo.get("cortado") is True and largo["salida"].count("\n") < 1000,
           "una salida enorme viene recortada y avisa")
        ok(d.get("Grep:", {}).get("estado") == "", "el que corre todavía no tiene resultado")
        ok(sm.detalle_pasos(cwd, sid, ["no-existe"]) == [], "un id que no está no rompe")
        ag = (sm.detalle_pasos(cwd, sid, ["t9"]) or [{}])[0]
        ok(ag.get("paso") == "lanzó un agente: contar notas", "el agente dice para qué lo lanzó")
        ok(ag.get("sub_pasos") == ["buscó «*.txt»"] and ag.get("salida") == "Hay 3 notas."
           and ag.get("segundo_plano") is True,
           "un agente en segundo plano muestra sus pasos y su informe (de su archivo)")
        print("\n4) La pantalla: pasos.js dibuja el estado y el cambio de verdad")
        dibujo = _dibujar_js(pasos, ed)
        ok(dibujo.get("negado") and dibujo.get("fallo"),
           "el renglón negado y el fallado llevan su marca")
        ok(dibujo.get("quitada") == ["11", "-", "    a = 1"]
           and dibujo.get("agregada") == ["11", "+", "    a = 2"],
           "la línea quitada y la agregada salen con su número (11) y su signo")
        ok(dibujo.get("contexto") == "10", "la línea de contexto lleva el número de al lado")
    finally:
        seguir.CLAUDE_PROYECTOS = viejo
        sm._HILOS.clear()


def _dibujar_js(pasos, edicion):
    """Corre `pasos.js` en node (con un documento de mentira) y mira el HTML que arma."""
    import re
    import subprocess
    js = (Path(__file__).resolve().parent.parent / "app/estaticos/pasos.js").as_posix()
    prog = (
        "global.window={};global.document={createElement:()=>({}),head:{appendChild(){}},"
        "addEventListener(){}};require(%r);const P=window.Pasos;"
        "P.iniciar({ubicacion:()=>({cwd:'c',sid:'s'})});const ms=%s;"
        "console.log(JSON.stringify({filas:ms.map((m,i)=>P.fila(ms,i)).join(''),"
        "dif:P.hunksHtml(%s)}))" % (js, json.dumps(pasos), json.dumps(edicion)))
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print("   node:", r.stderr[:300])
        return {}
    d = json.loads(r.stdout)
    filas = re.findall(r'<div class="dl (\w+)"><span class="dn">(\d*)</span>'
                       r'<span class="ds">(.)</span><span class="dt">([^<]*)</span>', d["dif"])
    quitada = next((list(f[1:]) for f in filas if f[0] == "dm"), None)
    agregada = next((list(f[1:]) for f in filas if f[0] == "dp"), None)
    contexto = next((f[1] for f in filas if f[0] == "dc"), None)
    return {"negado": 'paso abre negado' in d["filas"], "fallo": 'paso abre fallo' in d["filas"],
            "quitada": quitada, "agregada": agregada, "contexto": contexto}


MUTACIONES = {
    "se juntan los de distinto estado": ("_juntar_pasos",
                                         '\\\n                and ant["estado"] == f["estado"]:',
                                         ":"),
    "un negado se lee como fallado": ("_estado_resultado", 'return "negado" if', 'return "error" if'),
    "la edición no usa el parche": ("_detalle_uno", 'for h in extra.get("structuredPatch") or []:',
                                    "for h in []:"),
    "el agente no lee su archivo": ("detalle_pasos", "_sumar_subagente(d, ", "(lambda *a: None)(d, "),
}


def mutar():
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(sm, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        espacio = dict(vars(sm))
        exec(compile(fuente.replace(viejo, nuevo, 1), sm.__file__, "exec"), espacio)
        setattr(sm, funcion, espacio[funcion])
        antes = len(ROJOS)
        silencio = sys.stdout
        sys.stdout = open("nul" if sys.platform == "win32" else "/dev/null", "w")
        try:
            correr_todo()
        except Exception:
            ROJOS.append("excepcion")
        finally:
            sys.stdout.close()
            sys.stdout = silencio
            setattr(sm, funcion, original)
        cayo = len(ROJOS) > antes
        del ROJOS[antes:]
        caidas += cayo
        print(("  ok   " if cayo else "  FALLA ") + f"mutacion cazada: {nombre}")
        if not cayo:
            ROJOS.append("mutacion no cazada: " + nombre)
    return caidas


def main():
    correr_todo()
    if "--mutar" in sys.argv and not ROJOS:
        print("\n=== Las mutaciones: cada pieza tiene que poder fallar ===")
        n = mutar()
        print(f"\n{n} de {len(MUTACIONES)} mutaciones cazadas")
    print(f"\n{len(VERDES)} bien, {len(ROJOS)} mal")
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
