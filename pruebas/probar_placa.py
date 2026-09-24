"""La tarjeta de la placa: filtrar los modelos del escritorio, y no matar cualquier cosa.

No habla con la placa de verdad: le da a `placa.py` la salida REAL que devolvio
`nvidia-smi pmon` en la laptop de Martin el 2026-08-22, con los veinte procesos de
Windows que hacian inservible al `--query-compute-apps`. Si alguien "simplifica" el
filtro, esta prueba se pone roja con datos de verdad y no con un invento.
"""
import time

from app.nucleo import placa

bien = malo = 0


def ok(cond, que):
    global bien, malo
    if cond:
        bien += 1
        print("  ok   ", que)
    else:
        malo += 1
        print("  MAL  ", que)


# La salida tal cual, recortada: el escritorio entero sale `C+G` y los dos modelos `C`.
PMON = """# gpu         pid   type     sm    mem    enc    dec    jpg    ofa    command
# Idx           #    C/G      %      %      %      %      %      %    name
    0       2988   C+G      -      -      -      -      -      -    Microsoft.CmdPa
    0       6508   C+G      -      -      -      -      -      -    explorer.exe
    0      20372   C+G      -      -      -      -      -      -    AvastUI.exe
    0      30848   C+G      -      -      -      -      -      -    model_host.exe
    0      37984   C+G      -      -      -      -      -      -    Telegram.exe
    0      40216   C+G      -      -      -      -      -      -    WhatsApp.Root.e
    0      53360     C      -      -      -      -      -      -    python.exe
    0      55696     C      -      -      -      -      -      -    python.exe
"""
MEM = "6101, 8188, NVIDIA GeForce RTX 4070 Laptop GPU\n"


class ProcFalso:
    def __init__(self, nombre, cmd):
        self._n, self._c = nombre, cmd

    def name(self):
        return self._n

    def cmdline(self):
        return self._c.split(" ")


viejo_correr, viejo_hay = placa._correr, placa.hay_placa
try:
    placa._correr = lambda cmd, seg=8: PMON if "pmon" in cmd else MEM
    placa.hay_placa = lambda: True

    print("Separar los modelos del escritorio de Windows")
    pids = placa._pids_computo()
    ok(pids == [53360, 55696], "solo los dos de computo puro (`C`), no los 6 `C+G`")
    ok(6508 not in pids, "explorer.exe queda afuera")
    ok(30848 not in pids, "el model_host.exe de Avast queda afuera")
    # ⚠ Ese es el que Codex NO pudo matar el 22/8 ("Acceso denegado"): ni aparece.

    # ⭐ Lo preguntó Martín viendo la tarjeta: el medidor marcaba 1 GB y la lista estaba
    # vacía. Ese giga no es un modelo escondido: son las ventanas de Windows.
    graf = placa._pmon()["graficos"]
    ok(len(graf) == 6, "los `C+G` se cuentan aparte, no se tiran")
    ok(6508 in graf, "explorer.exe esta entre los que dibujan")

    print("\nEl medidor")
    m = placa.memoria()
    ok(m.get("usado") == 6101 and m.get("total") == 8188, "lee usado y total")
    ok(m.get("pct") == 75, "el porcentaje sale redondeado")
    ok("4070" in m.get("placa", ""), "trae el nombre de la placa")

    print("\nPonerle nombre en criollo a cada uno")
    casos = [
        ("python.exe", r"D:\IA\envs\wpp\python.exe -m app.voz.voz", "Voz de Laura"),
        ("python.exe", r"D:\IA\envs\wpp\python.exe -m app.ingesta.bot_telegram", "Bot de Telegram"),
        ("ollama.exe", r"C:\Ollama\ollama.exe serve", "Ollama"),
        ("python.exe", r"D:\IA\modelos-3d\hunyuan\gradio_app.py", "Generador 3D (Hunyuan)"),
    ]
    for nombre_exe, cmd, esperado in casos:
        ok(placa._bautizar(ProcFalso(nombre_exe, cmd))[0] == esperado,
           "%s -> %s" % (cmd.split("\\")[-1][:28], esperado))
    desconocido = placa._bautizar(ProcFalso("raro.exe", r"C:\loquesea\raro.exe --modelo"))
    ok(desconocido[0] == "raro.exe",
       "lo que no reconoce sale igual (no se le esconde nada a Martin)")

    # OJO: la consola de Windows es cp1252 y no traga simbolos raros: en los `print`
    # de las pruebas van solo letras (en los comentarios del codigo, lo que quieras).
    print("\nLa guarda de apagar (el endpoint recibe un numero del navegador)")
    r = placa.apagar_pid(4)
    ok(r["ok"] is False, "un pid que NO esta usando la placa se niega")
    ok("placa" in (r.get("error") or ""), "y dice por que")
    ok(placa.apagar_pid("hola")["ok"] is False, "un pid que ni es numero se niega")
    ok(placa.apagar_pid(6508)["ok"] is False,
       "explorer.exe no se puede matar desde el panel aunque exista")

    print("\nLos modelos que el panel sabe prender")
    ok(set(placa.MODELOS) == {"ollama", "hunyuan"}, "estan los dos: Ollama y el Hunyuan")
    hy = placa.MODELOS["hunyuan"]
    ok("--low_vram_mode" in hy["cmd"] and "--disable_tex" in hy["cmd"],
       "el Hunyuan arranca en modo poca memoria y sin texturas (o no entra en 8 GB)")
    ok(hy["env"].get("HY3DGEN_MODELS", "").endswith("hunyuan-models"),
       "y con los pesos apuntados a D: (si no se los baja de nuevo al disco chico)")
    ok(hy["tarda"] is True, "esta marcado como lento: la tarjeta lo muestra cargando")
    ok(placa.modelo_prender("loquesea")["ok"] is False, "un modelo que no existe se niega")

    # ⚠⚠ Lo que trajo Martin: *"si yo apago los modelos, las sesiones del panel andan
    # muy mal"*. La primera version reconocia los procesos por una palabra suelta de su
    # linea de comando ("ollama", "gradio_app.py") y se llevaba puesto lo ajeno.
    print("\nApagar un modelo NO puede matar procesos de otro")
    ajenos = [
        ("el bash de una sesion de Claude Code", "bash.exe",
         r"C:\Program Files\Git\bin\bash.exe -c curl localhost:11434 ollama"),
        ("TripoSR (tiene su propio gradio_app.py)", "python.exe",
         r"D:\IA\modelos-3d\TripoSR\venv\python.exe gradio_app.py"),
        ("el panel", "python.exe", r"D:\IA\envs\wpp\python.exe panel.py"),
    ]
    for clave in ("ollama", "hunyuan"):
        for que, exe, cmd in ajenos:
            ok(not placa.es_de(placa.MODELOS[clave], exe, cmd),
               "apagar %s no toca %s" % (clave, que))
    ok(placa.es_de(placa.MODELOS["ollama"], "ollama.exe", r"C:\Ollama\ollama.exe serve"),
       "...pero Ollama de verdad si se reconoce")
    ok(placa.es_de(placa.MODELOS["hunyuan"], "python.exe",
                   r"D:\IA\modelos-3d\Hunyuan3D-2\conda-env\python.exe gradio_app.py"),
       "...y el Hunyuan de verdad tambien")

    print("\nLos tres estados de un modelo")
    viejo_puerto, viejo_procs = placa._puerto_abierto, placa._procesos_de
    try:
        placa._puerto_abierto = lambda p, seg=0.4: False
        placa._procesos_de = lambda m: []
        e = placa.modelo_estado("hunyuan")
        ok(not e["vivo"] and not e["cargando"], "sin proceso y sin puerto: apagado")

        placa._procesos_de = lambda m: ["un proceso"]
        e = placa.modelo_estado("hunyuan")
        ok(e["cargando"] is True and e["vivo"] is False,
           "con proceso y el puerto mudo: CARGANDO (los pesos tardan minutos)")

        placa._puerto_abierto = lambda p, seg=0.4: True
        e = placa.modelo_estado("hunyuan")
        ok(e["vivo"] is True and e["cargando"] is False, "con el puerto abierto: prendido")
        ok(placa.modelo_prender("hunyuan").get("ya") is True,
           "prenderlo estando prendido no lanza otro proceso")
    finally:
        placa._puerto_abierto, placa._procesos_de = viejo_puerto, viejo_procs

    print("\nLa foto entera")
    placa._CACHE["t"] = 0.0
    d = placa.estado()
    ok(d["ok"] is True and len(d["procesos"]) <= 2, "el estado arma la foto sin explotar")
    ok(len(d.get("modelos") or []) == 2, "y siempre trae los modelos, prendidos o no")
    ok((d.get("escritorio") or {}).get("cuantos") == 6,
       "y de quien es lo usado cuando no hay ningun modelo (la pregunta de Martin)")

    # ⚠ El de la fila fija NO puede salir tambien como hallazgo del barrido: seria la
    # misma cosa dos veces, una con Prender y otra con Apagar.
    viejo_procesos = placa.procesos
    try:
        placa.procesos = lambda pids=None: [
            {"pid": 1, "nombre": "Voz de Laura", "cmd": "python.exe -m app.voz.voz"},
            {"pid": 2, "nombre": "Generador 3D (Hunyuan)",
             "cmd": r"D:\IA\modelos-3d\Hunyuan3D-2\conda-env\python.exe gradio_app.py"}]
        placa._CACHE["t"] = 0.0
        d = placa.estado()
        nombres = [p["nombre"] for p in d["procesos"]]
        ok(nombres == ["Voz de Laura"], "el Hunyuan no se duplica: queda su fila fija")
    finally:
        placa.procesos = viejo_procesos

    veces = []
    placa._correr = lambda cmd, seg=8: (veces.append(1), PMON if "pmon" in cmd else MEM)[1]
    placa._CACHE["t"] = time.time()
    placa.estado()
    ok(not veces, "la segunda vez sale del cache y no vuelve a llamar a nvidia-smi")
finally:
    placa._correr, placa.hay_placa = viejo_correr, viejo_hay
    placa._CACHE["t"] = 0.0

print("\n%d en verde, %d en rojo" % (bien, malo))
if malo:
    raise SystemExit(1)
