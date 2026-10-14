"""Laura sorda con el interruptor en verde (arreglado el 2026-09-27).

Del 06/09 al 25/09 Laura no escucho: la bandera `mic_bloqueado.flag` habia quedado puesta,
los microfonos de Windows se habian destrabado por otro camino, y el panel —que miraba
SOLO a Windows— mostraba el interruptor en verde. Encima, tocarlo la volvia a bloquear.

Se prueba con la app de FastAPI de verdad, sin tocar Windows ni la bandera real: el mute,
el interruptor maestro y la ruta de la bandera se tapan.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_microfono_bloqueo
    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_microfono_bloqueo --mutar
"""
import inspect
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from fastapi.testclient import TestClient

import panel
from app.voz import chequeo_microfono as chm

VERDES, ROJOS = [], []
RAIZ = Path(__file__).resolve().parent.parent


def ok(cierto, que):
    (VERDES if cierto else ROJOS).append(que)
    print(("  ok   " if cierto else "  FALLA ") + que, flush=True)


class WindowsDeMentira:
    """El mute de los microfonos y el interruptor maestro, sin tocar la maquina."""
    def __init__(self, permitido):
        self.permitido = permitido
        self.maestro = []

    def mic(self, accion):
        if accion == "silenciar":
            self.permitido = False
        elif accion == "permitir":
            self.permitido = True
        return self.permitido

    def maestro_llamar(self, estado):
        self.maestro.append(estado)
        return True


def preparar(permitido, bandera):
    tmp = Path(tempfile.mkdtemp(prefix="mic_"))
    panel.MIC_BLOQUEADO = tmp / "mic_bloqueado.flag"
    if bandera:
        panel.MIC_BLOQUEADO.write_text("bloqueado desde el panel\n", encoding="utf-8")
    w = WindowsDeMentira(permitido)
    panel._mic_llamar = w.mic
    panel._maestro_llamar = w.maestro_llamar
    panel._MIC_CACHE.update(permitido=permitido, vence=0)
    return w


def correr_todo():
    cliente = TestClient(panel.app)

    print("\n1) El caso del bug: Windows deja, pero la bandera quedo puesta")
    w = preparar(permitido=True, bandera=True)
    s = cliente.get("/status").json()
    ok(s["mic_permitido"] is False, "el panel dice que Laura NO puede escuchar")
    ok(s["mic_bandera_sola"] is True, "y marca que es la bandera sola (el caso traicionero)")
    ok(isinstance(s.get("mic_bloqueado_desde"), (int, float)), "con desde cuando")
    cliente.post("/micacceso")
    ok(not panel.MIC_BLOQUEADO.exists(), "tocar el interruptor DESTRABA (antes la volvia a bloquear)")
    ok(w.maestro == [], "sin abrir la Configuracion de Windows: no hacia falta")
    ok(cliente.get("/status").json()["mic_permitido"] is True, "y queda habilitada")

    print("\n2) Bloquear y destrabar de siempre siguen andando")
    w = preparar(permitido=True, bandera=False)
    cliente.post("/micacceso")
    ok(panel.MIC_BLOQUEADO.exists() and w.permitido is False and w.maestro == ["off"],
       "bloquear: pone la bandera, silencia y apaga el maestro")
    ok("20" in panel.MIC_BLOQUEADO.read_text(encoding="utf-8"),
       "la bandera dice cuando se puso")
    cliente.post("/micacceso")
    ok(not panel.MIC_BLOQUEADO.exists() and w.permitido is True and w.maestro[-1] == "on",
       "destrabar: prende el maestro, desmutea y saca la bandera")

    print("\n3) El vigia: avisa si pasa un dia entero bloqueada, no por una noche")
    tmp = Path(tempfile.mkdtemp(prefix="mic_vigia_"))
    chm.MIC_BLOQUEADO = tmp / "mic_bloqueado.flag"
    ok(chm.estado()[0] is True, "sin bandera: bien")
    chm.MIC_BLOQUEADO.write_text("x", encoding="utf-8")
    ok(chm.estado()[0] is True, "bloqueada recien: todavia es normal")
    hace = time.time() - 19 * 86400
    os.utime(chm.MIC_BLOQUEADO, (hace, hace))
    bien, texto = chm.estado()
    ok(bien is False and "19 días" in texto, f"bloqueada hace 19 dias: avisa y lo dice ({texto[:60]}...)")
    r = subprocess.run([sys.executable, "-m", "app.voz.chequeo_microfono"], cwd=str(RAIZ),
                       capture_output=True, text=True, encoding="utf-8")
    ok(r.returncode in (0, 1), "el comando del vigia corre de verdad y sale con 0 o 1")


MUTACIONES = {
    "el panel mira solo a Windows": ("mic_estado", '"mic_permitido": windows and desde is None',
                                     '"mic_permitido": windows'),
    "el interruptor decide solo por Windows": ("micacceso", 'if est["mic_permitido"]:',
                                               'if mic_permitido():'),
    "el vigia no mira la fecha": ("estado", "if horas < UMBRAL_HORAS:", "if True:"),
}


def mutar():
    caidas = 0
    for nombre, (funcion, viejo, nuevo) in MUTACIONES.items():
        mod = chm if hasattr(chm, funcion) and funcion == "estado" else panel
        original = getattr(mod, funcion)
        fuente = textwrap.dedent(inspect.getsource(original))
        if viejo not in fuente:
            print(f"  FALLA la mutacion '{nombre}' ya no encuentra su texto")
            ROJOS.append(nombre)
            continue
        espacio = dict(vars(mod))
        codigo = "\n".join(l for l in fuente.replace(viejo, nuevo, 1).splitlines()
                           if not l.startswith("@app."))
        exec(compile(codigo, mod.__file__, "exec"), espacio)
        nueva = espacio[funcion]
        rutas = [r for r in panel.app.router.routes if getattr(r, "endpoint", None) is original]
        setattr(mod, funcion, nueva)

        def cambiar_rutas(f):
            import fastapi
            for r in rutas:
                r.endpoint = f
                r.dependant.call = f
                r.app = fastapi.routing.request_response(r.get_route_handler())
        cambiar_rutas(nueva)
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
            setattr(mod, funcion, original)
            cambiar_rutas(original)
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
