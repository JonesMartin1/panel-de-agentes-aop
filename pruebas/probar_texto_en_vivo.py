"""El texto en vivo de `/sesiones` (2026-09-27): el borrador que crece mientras se escribe.

Pedido de Martin: "quiero que me aparezca el texto tal cual como lo haria Claude Code",
no de golpe al terminar. El proceso de la sesion manda el texto en pedacitos
(`--include-partial-messages`), `_turno` los junta en `EN_VIVO` y la pantalla lo recibe
por `/movil/envivo`. Aca se prueba todo lo del servidor con el CLI de mentira
(`cli_falso_sesion.py`, modo `envivo`): no se habla con Claude ni se gasta un token.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_texto_en_vivo
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_texto_en_vivo --mutar

Con `--mutar` rompe a proposito cada pieza que importa y exige que alguna prueba caiga:
un chequeo que no puede fallar es un adorno. Lo que se cuida:
  - que el borrador CREZCA durante el turno (no que aparezca entero al final);
  - que cada bloque terminado se quede con el uuid que despues trae el disco;
  - que el reintento de Anthropic no deje texto repetido;
  - que un subagente no se meta en la respuesta;
  - que el borrador de una charla nueva se mude a su id real (si no, la PROXIMA charla
    nueva de esa carpeta lo encontraria como suyo).

La contraparte que gasta tokens, contra el CLI de verdad, es `sonda_texto_en_vivo.py`.
"""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

from app.voz import seguir, sesiones_movil as sm

VERDES, ROJOS = [], []


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def preparar(carpeta):
    cli = Path(__file__).with_name("cli_falso_sesion.py")
    cmd = carpeta / "claude_falso.cmd"
    cmd.write_text('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, cli),
                   encoding="utf-8")
    sm._claude_bin = lambda: str(cmd)
    sm.es_codex = lambda sid: False
    sm.modelo_de = lambda sid: "haiku"
    sm.esfuerzo_de = lambda sid: ""
    sm.contexto = lambda cwd, sid, cola=0: {"tokens": 0}


def limpiar():
    for viva in list(sm.VIVAS.values()):
        try:
            sm._matar_arbol(viva.proc)
        except Exception:
            pass
    sm.VIVAS.clear()
    sm.EN_VIVO.clear()
    seguir.PIDS_PANEL.clear()


def turno_mirando(cwd, sid, texto):
    """Manda un turno y va sacando fotos del borrador cada 50 ms mientras corre."""
    fotos, salida = [], {}

    def correr():
        try:
            salida["r"] = sm.mandar(cwd, sid, texto)
        except Exception as e:
            salida["error"] = str(e)

    h = threading.Thread(target=correr)
    h.start()
    while h.is_alive():
        fotos.append(sm.envivo_de(cwd, sid))
        time.sleep(0.05)
    h.join()
    return fotos, salida


def textos(foto, tipo="texto"):
    return [b["texto"] for b in foto["bloques"] if b["tipo"] == tipo]


def pruebas_turno(cwd):
    print("\n1) Charla nueva: el borrador CRECE mientras se escribe")
    fotos, salida = turno_mirando(cwd, "", "envivo")
    ok("error" not in salida, "el turno termina bien (%s)" % salida.get("error", "ok"))
    sid = (salida.get("r") or ("", ""))[1]
    vistos = [t for f in fotos for t in textos(f)]
    ok("Hola " in vistos or "Hola que " in vistos,
       "se vio el texto A MEDIAS antes de que terminara el turno")
    ok(any(f["v"] and not f["fin"] for f in fotos),
       "mientras corre, el borrador dice que no termino")
    ok(any(b["tipo"] == "texto" and b["abierto"] for f in fotos for b in f["bloques"]),
       "el bloque que se esta escribiendo va marcado abierto (el cursor que late)")
    ok(any("leyendo un archivo…" in textos(f, "paso") for f in fotos),
       "la herramienta aparece APENAS arranca, antes de tener su detalle")
    ok(any(b["tipo"] == "pensando" for f in fotos for b in f["bloques"]),
       "se sabe cuando esta pensando")

    print("\n2) Al terminar: todo con su uuid, listo para cambiarlo por el del disco")
    fin = sm.envivo_de(cwd, sid)
    ok(fin["fin"], "el borrador queda marcado terminado")
    por_u = {b["u"]: b for b in fin["bloques"]}
    ok(por_u.get("u-texto-1", {}).get("texto") == "Hola que tal.",
       "el primer texto quedo entero y con el uuid de su linea del disco")
    ok(por_u.get("u-paso-1", {}).get("texto") == "leyó README.md",
       "el paso quedo contado igual que en el rastro del disco (`_paso_de`)")
    ok(por_u.get("u-texto-2", {}).get("texto") == "Listo.", "el segundo texto tambien")
    ok(all(b["u"] for b in fin["bloques"]), "no queda ningun bloque sin su uuid")
    ok(not any(b["tipo"] == "pensando" for b in fin["bloques"]),
       "el 'pensando' se va cuando termina de pensar")
    ok("u-todo" not in por_u, "la lista de tareas no aparece como paso (tiene su tarjeta)")
    ok(not any("SUBAGENTE" in b["texto"] for b in fin["bloques"]),
       "lo que dice un subagente no se mete en la respuesta")
    ok("↳ agente: leyó SUB.md" in textos(fin, "paso"),
       "pero lo que HACE un subagente sí se ve, como paso (2026-09-27)")

    print("\n3) La charla nacio: el borrador se muda a su id")
    ok(bool(sid) and sm._clave(cwd, sid) in sm.EN_VIVO,
       "el borrador esta bajo el id real")
    ok(sm._clave(cwd, "") not in sm.EN_VIVO,
       "y la clave 'nueva:<carpeta>' quedo libre para la proxima charla nueva")
    ok(sm.envivo_de(cwd, "")["v"] == 0,
       "una charla nueva en la misma carpeta arranca sin borrador ajeno")

    print("\n4) Un reintento de Anthropic no deja el texto repetido")
    fotos, salida = turno_mirando(cwd, sid, "reintento")
    ok(any("BASURA" in t for f in fotos for t in textos(f)),
       "se llego a ver el intento que fallo (la prueba ejercita el caso)")
    # ⚠ Se mira DURANTE el turno, no al final: al terminar se barre todo lo que no tiene
    # uuid, asi que mirando el final el intento fallado desaparecia igual y la prueba
    # daba verde por el motivo equivocado (lo cazo la mutacion).
    despues = [f for f in fotos if not f["fin"] and "Listo." in textos(f)]
    ok(bool(despues) and not any("BASURA" in t for f in despues for t in textos(f)),
       "mientras se escribe el reintento, el intento fallado ya no se ve")
    fin = sm.envivo_de(cwd, sid)
    ok(textos(fin).count("Listo.") == 1, "y el texto bueno esta una sola vez")

    print("\n5) El turno siguiente arranca con el borrador limpio")
    # "lento" tarda 2 s: con uno instantaneo no se llega a sacar ni una foto del turno.
    fotos, _ = turno_mirando(cwd, sid, "lento")
    # La primera foto del turno NUEVO (las de antes de arrancar son del anterior, ya
    # terminado, y esas la pantalla las filtra por uuid).
    nuevas = [f for f in fotos if not f["fin"]]
    ok(bool(nuevas) and not any("BASURA" in t or "Hola que tal." in t
                                for t in textos(nuevas[0])),
       "no hereda lo del turno anterior")

    print("\n6) La cocina de compactar no se transmite")
    fotos, _ = turno_mirando(cwd, sid, sm.PEDIDO_RESUMEN)
    ok(all(not f["bloques"] or f["fin"] for f in fotos),
       "el pedido de resumen no arma borrador (el hilo lo esconde, en vivo tambien)")


def pruebas_disco():
    print("\n7) El hilo del disco trae los uuid para reconocer lo que ya llego")
    tmp = Path(tempfile.mkdtemp(prefix="envivo_disco_"))
    j = tmp / "x.jsonl"
    lineas = [
        {"type": "assistant", "uuid": "a1",
         "message": {"content": [{"type": "text", "text": "Hola"}]}},
        {"type": "assistant", "uuid": "a2", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/a.py"}}]}},
        {"type": "assistant", "uuid": "a3", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/a.py"}}]}},
    ]
    j.write_text("\n".join(json.dumps(x) for x in lineas) + "\n", encoding="utf-8")
    filas = sm._filas_de(j)
    ok(any(f.get("de") == "claude" and f.get("u") == "a1" for f in filas),
       "un texto trae el uuid de su linea")
    pasos = [f for f in filas if f.get("de") == "paso"]
    ok(len(pasos) == 1 and pasos[0].get("us") == ["a2", "a3"],
       "dos pasos iguales juntados en un renglon traen los DOS uuid")


def pruebas_sueltas():
    print("\n8) Sin borrador, la respuesta es vacia y no rompe")
    d = sm.envivo_de("C:/no/existe", "nadie")
    ok(d == {"v": 0, "fin": True, "bloques": []}, "charla sin turno: borrador vacio")
    print("\n9) El tope: un turno con cientos de pasos no crece sin fin")
    clave = "prueba:tope"
    sm._en_vivo_empezar(clave)
    for i in range(sm.TOPE_EN_VIVO + 30):
        sm._en_vivo_evento(clave, {"type": "stream_event", "event": {
            "type": "content_block_start", "index": i,
            "content_block": {"type": "tool_use", "name": "Bash"}}})
    ok(len(sm.EN_VIVO[clave]["bloques"]) == sm.TOPE_EN_VIVO,
       "se quedan solo los ultimos %d bloques" % sm.TOPE_EN_VIVO)
    sm.EN_VIVO.pop(clave, None)


def pruebas_pantallas():
    """Las dos pantallas enchufan la MISMA pieza (`/estaticos/envivo.js`)."""
    import re
    import subprocess
    import warnings
    print("\n10) Las dos pantallas usan /estaticos/envivo.js")
    raiz = Path(__file__).resolve().parent.parent
    src = (raiz / "panel.py").read_text(encoding="utf-8")
    m = re.search(r'^MOVIL_HTML = """', src, re.M)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        movil = eval(src[m.start() + len("MOVIL_HTML = "):src.index('"""', m.end()) + 3])
    ses = (raiz / "app/estaticos/sesiones.html").read_text(encoding="utf-8")
    for nombre, html in (("la compu", ses), ("el celular", movil)):
        ok('<script src="/estaticos/envivo.js">' in html, f"{nombre} carga envivo.js")
        ok(all(x in html for x in ('id="envivo"', "EnVivo.iniciar(", "EnVivo.seguir(",
                                   "EnVivo.hilo(", "EnVivo.pintar()")),
           f"{nombre} deja el lugar del borrador y lo enchufa en su repintado")
    ok('@app.get("/estaticos/envivo.js")' in src and '@app.get("/movil/envivo")' in src,
       "el panel sirve el archivo y el canal")
    print("\n11) El markdown a medio escribir no se ve crudo")
    js = (raiz / "app/estaticos/envivo.js").as_posix()
    casos = {"```py\nx = 1": "```py\nx = 1\n```", "hola **mun": "hola mun",
             "**listo** y ya": "**listo** y ya"}
    prog = ("global.window={};global.document={};require(%r);const c=window.EnVivo.cerrarCercas;"
            "console.log(JSON.stringify(%s.map(c)))" % (js, json.dumps(list(casos))))
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8")
    salida = json.loads(r.stdout or "null") if r.returncode == 0 else None
    ok(salida == list(casos.values()),
       "bloque de código abierto se cierra, ** suelto se esconde, lo cerrado queda igual"
       + ("" if salida else " (node: %s)" % (r.stderr or "")[:200]))


def correr_todo():
    tmp = Path(tempfile.mkdtemp(prefix="envivo_"))
    preparar(tmp)
    try:
        pruebas_turno(str(tmp))
    finally:
        limpiar()
    pruebas_disco()
    pruebas_sueltas()
    pruebas_pantallas()


MUTACIONES = {
    # Sin la bandera, el CLI falso (como el de verdad) no manda pedacitos.
    "sin la bandera en el arranque": ("_arrancar_viva", '"--include-partial-messages",', ""),
    "los pedacitos no se suman": ("_en_vivo_evento",
                                  'b["texto"] += delta.get("text") or ""', "pass"),
    "el bloque terminado no guarda su uuid": ("_en_vivo_evento",
                                              "b.update(texto=c.get(\"text\") or \"\", u=u,",
                                              "b.update(texto=c.get(\"text\") or \"\", u=\"\","),
    "el reintento no tira lo que venia": ("_en_vivo_evento",
                                          'ent["bloques"] = [b for b in bloques if b["u"]]\n'
                                          '            idx.clear()',
                                          "idx.clear()"),
    "los subagentes se meten": ("_en_vivo_evento",
                                "_en_vivo_subagente(clave, d)\n        return",
                                "pass"),
    "los pasos del subagente no se ven": ("_en_vivo_subagente",
                                          'ent["bloques"].append(', "(lambda x: x)("),
    "el borrador no se muda al nacer": ("_remapear",
                                        "EN_VIVO[viva.clave()] = ent",
                                        "EN_VIVO[vieja] = ent"),
}


def mutar():
    import inspect
    import textwrap
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(sm, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto en {funcion}")
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
        VERDES.clear()
        n = mutar()
        print(f"\n{n} de {len(MUTACIONES)} mutaciones cazadas")
    print(f"\n{len(VERDES)} bien, {len(ROJOS)} mal")
    return 1 if ROJOS else 0


if __name__ == "__main__":
    sys.exit(main())
