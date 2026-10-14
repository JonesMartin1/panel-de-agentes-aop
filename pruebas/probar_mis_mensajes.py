"""Tus mensajes no se pierden (2026-09-27): todo lo que llega a `/movil/mandar` queda
guardado ANTES de cualquier otra cosa, y `/movil/mis-mensajes` los devuelve para la ↑.

Pedido de Martin: "no perder los prompts que yo mando". Se prueba contra el panel de
verdad (la app de FastAPI, sin levantar servidor) pero con el archivo apuntando a una
carpeta temporal: no toca `resultados/mis_mensajes.jsonl` ni lanza ningun turno.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_mis_mensajes
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_mis_mensajes --mutar
"""
import inspect
import json
import sys
import tempfile
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

import panel

VERDES, ROJOS = [], []


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


def correr_todo():
    tmp = Path(tempfile.mkdtemp(prefix="mis_mensajes_"))
    panel.MIS_MENSAJES = tmp / "mis_mensajes.jsonl"
    cliente = TestClient(panel.app)
    ocupada = "sesion-ocupada-de-prueba"

    print("\n1) Un mensaje RECHAZADO igual queda guardado")
    with panel._TURNOS_CANDADO:
        panel._TURNOS_ABIERTOS.add(ocupada)
    try:
        r = cliente.post("/movil/mandar", data={"cwd": "C:/Proy/Uno", "sid": ocupada,
                                                "texto": "arreglá el login"}).json()
    finally:
        with panel._TURNOS_CANDADO:
            panel._TURNOS_ABIERTOS.discard(ocupada)
    ok(r.get("ok") is False, "el panel lo rechaza (la sesion estaba contestando)")
    lineas = (panel.MIS_MENSAJES.read_text(encoding="utf-8").splitlines()
              if panel.MIS_MENSAJES.exists() else [])
    ok(len(lineas) == 1 and json.loads(lineas[0])["texto"] == "arreglá el login",
       "pero el mensaje ya estaba guardado, con tildes y todo")

    print("\n2) La ↑ recibe lo de ESA carpeta, sin la marca de las fotos")
    panel._anotar_mensaje("C:/Proy/Dos", "x", "esto es de otra carpeta")
    # La marca de verdad, tal cual la arma `_guardar_imagenes`.
    panel._anotar_mensaje("C:\\Proy\\Uno\\", "y",
                          "[Te paso una imagen desde el celular; está guardada en "
                          "C:\\x\\foto_1.png — abrila con la herramienta Read antes de "
                          "contestar.] mirá esto")
    d = cliente.get("/movil/mis-mensajes", params={"cwd": "c:/proy/uno"}).json()
    textos = [m["texto"] for m in d["mensajes"]]
    ok(textos[:1] == ["arreglá el login"], "trae los de esa carpeta, del mas viejo al nuevo")
    ok("esto es de otra carpeta" not in textos, "no mezcla los de otra carpeta")
    ok(any(t == "mirá esto" for t in textos),
       "a la caja vuelve solo lo que escribiste, sin la marca de la foto")
    todos = cliente.get("/movil/mis-mensajes").json()["mensajes"]
    ok(len(todos) == 3, "sin carpeta trae todos")

    print("\n3) Si no se puede escribir, el envio sigue igual")
    panel.MIS_MENSAJES = tmp / "no" / "existe" / "\0malo.jsonl"
    try:
        panel._anotar_mensaje("C:/Proy/Uno", "", "hola")
        ok(True, "no tira ningun error hacia afuera")
    except Exception as e:
        ok(False, f"no tira ningun error hacia afuera ({e})")


MUTACIONES = {
    "se guarda DESPUES de los rechazos": (
        "movil_mandar",
        "    _anotar_mensaje(cwd, sid, texto)\n    if sid and sid == _sesion_de_laura():",
        "    if sid and sid == _sesion_de_laura():"),
    "la ↑ no filtra por carpeta": ("movil_mis_mensajes", "if cwd and", "if False and"),
    "un error al escribir voltea el envio": ("_anotar_mensaje", "    except Exception as e:\n"
                                             "        print(", "    except ZeroDivisionError as e:\n        print("),
}


def mutar():
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        original = getattr(panel, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        # Los endpoints estan colgados de la app: se cambia la funcion en la ruta tambien.
        espacio = dict(vars(panel))
        codigo = "\n".join(l for l in fuente.replace(viejo, nuevo, 1).splitlines()
                           if not l.startswith("@app."))
        exec(compile(codigo, panel.__file__, "exec"), espacio)
        nueva = espacio[funcion]
        rutas = [r for r in panel.app.router.routes if getattr(r, "endpoint", None) is original]
        setattr(panel, funcion, nueva)
        for r in rutas:
            r.endpoint = nueva
            r.dependant.call = nueva
            r.app = __import__("fastapi").routing.request_response(r.get_route_handler())
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
            setattr(panel, funcion, original)
            for r in rutas:
                r.endpoint = original
                r.dependant.call = original
                r.app = __import__("fastapi").routing.request_response(r.get_route_handler())
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
