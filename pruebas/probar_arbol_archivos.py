"""El explorador de archivos de la pantalla de Sesiones, del lado del servidor.

Llama a las funciones de `panel.py` DIRECTO, sin levantar el servidor: el evento de
arranque de FastAPI (el vigilante de servicios) solo corre cuando lo sirve uvicorn,
asi que importar el panel no prende ni apaga nada (mismo truco que
`probar_unir_audios.py` y `probar_avisos.py`).

Lo que se controla, en orden de importancia:
  1. que NO se pueda leer nada afuera de la carpeta del proyecto (`..`, rutas
     absolutas de otro lado, carpetas que el panel no conoce);
  2. que la lista salga como en VS Code: carpetas primero y sin el ruido de siempre;
  3. que un archivo de texto se lea, uno binario se avise y uno enorme no se mande.

    D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_arbol_archivos
"""
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import panel
from app.rutas import RAIZ

ok = fallo = 0


def chequear(que, condicion, detalle=""):
    global ok, fallo
    if condicion:
        ok += 1
        print(f"  ok   {que}")
    else:
        fallo += 1
        print(f"  FALLA {que}" + (f"  ({detalle})" if detalle else ""))


print("\n== La raiz que se acepta ==")
chequear("este proyecto es una carpeta conocida", panel._arbol_raiz(str(RAIZ)) is not None)
chequear("una carpeta cualquiera del disco NO se abre",
         panel._arbol_raiz(r"C:\Windows\System32") is None)
chequear("una ruta relativa no se abre", panel._arbol_raiz("app") is None)
chequear("vacio no se abre", panel._arbol_raiz("") is None)

print("\n== Nadie se sale de la carpeta ==")
raiz = panel._arbol_raiz(str(RAIZ))
chequear("un `..` no sale de la raiz", panel._arbol_dentro(raiz, "../..") is None)
chequear("un `..` escondido en el medio tampoco",
         panel._arbol_dentro(raiz, "app/../../otro") is None)
chequear("una subcarpeta de verdad si", panel._arbol_dentro(raiz, "app/voz") is not None)
chequear("las barras de Windows valen igual",
         panel._arbol_dentro(raiz, r"app\voz") is not None)

r = panel.archivos_lista(cwd=r"C:\Windows", sub="")
chequear("listar una carpeta que el panel no conoce falla", r.get("ok") is False)
r = panel.archivos_ver(cwd=str(RAIZ), ruta="../../algo.txt")
chequear("leer con `..` falla", r.get("ok") is False)
r = panel.archivos_ver(cwd=r"C:\Windows", ruta="win.ini")
chequear("leer de una carpeta desconocida falla", r.get("ok") is False)

print("\n== La lista de una carpeta ==")
r = panel.archivos_lista(cwd=str(RAIZ), sub="")
chequear("la raiz del proyecto se lista", r.get("ok") is True, str(r)[:120])
items = r.get("items", [])
nombres = [i["nombre"] for i in items]
chequear("aparece panel.py", "panel.py" in nombres)
chequear("aparece la carpeta app", "app" in nombres)
chequear("NO aparece .git", ".git" not in nombres)
chequear("NO aparece __pycache__", "__pycache__" not in nombres)
carpetas = [i["dir"] for i in items]
chequear("las carpetas van primero", carpetas == sorted(carpetas, reverse=True))
solo_dirs = [i["nombre"].lower() for i in items if i["dir"]]
chequear("y ordenadas alfabeticamente", solo_dirs == sorted(solo_dirs))
chequear("los archivos traen su peso",
         all(i["bytes"] > 0 for i in items if not i["dir"] and i["nombre"] != ".gitkeep"))

r = panel.archivos_lista(cwd=str(RAIZ), sub="app/voz")
chequear("una subcarpeta se lista", r.get("ok") is True)
chequear("y trae voz.py", any(i["nombre"] == "voz.py" for i in r.get("items", [])))
r = panel.archivos_lista(cwd=str(RAIZ), sub="carpeta-que-no-existe")
chequear("una carpeta que no existe avisa", r.get("ok") is False)

print("\n== Leer un archivo ==")
r = panel.archivos_ver(cwd=str(RAIZ), ruta="CLAUDE.md")
chequear("CLAUDE.md se lee", r.get("ok") is True and r.get("tipo") == "texto")
chequear("y trae el texto de verdad", "Reglas de trabajo" in (r.get("texto") or ""))
chequear("dice cuanto pesa", (r.get("bytes") or 0) > 100)
chequear("y la ruta completa, para copiarla", str(RAIZ) in (r.get("completo") or ""))
chequear("no viene cortado", r.get("cortado") is False)

r = panel.archivos_ver(cwd=str(RAIZ), ruta="app/estaticos/sesiones.html")
chequear("un archivo de una subcarpeta se lee", r.get("ok") is True)
r = panel.archivos_ver(cwd=str(RAIZ), ruta="musica_espera.wav")
chequear("un .wav se marca como binario", r.get("tipo") in ("binario", "pesado"),
         str(r.get("tipo")))
r = panel.archivos_ver(cwd=str(RAIZ), ruta="app")
chequear("pedir una carpeta como archivo falla", r.get("ok") is False)

# Un archivo mas grande que el tope: tiene que llegar cortado, no entero.
grande = RAIZ / "resultados" / "_prueba_arbol_grande.txt"
grande.parent.mkdir(parents=True, exist_ok=True)
try:
    grande.write_text("linea de relleno\n" * 40000, encoding="utf-8")
    r = panel.archivos_ver(cwd=str(RAIZ), ruta="resultados/_prueba_arbol_grande.txt")
    chequear("un archivo largo llega cortado", r.get("cortado") is True)
    chequear("y no manda mas de lo permitido",
             len(r.get("texto") or "") <= panel.ARBOL_MAX_BYTES)
finally:
    grande.unlink(missing_ok=True)

print("\n== La ruta elegida para el mensaje ==")
chequear("el panel publica el selector de archivos",
         any(getattr(r, "path", "") == "/movil/elegir_archivo" for r in panel.app.routes))
ruta, relativa = panel._ruta_archivo_para_chat(
    str(RAIZ / "app" / "estaticos" / "sesiones.html"), str(RAIZ))
chequear("un archivo del proyecto queda relativo",
         relativa and ruta == os.path.join("app", "estaticos", "sesiones.html"), ruta)
ruta, relativa = panel._ruta_archivo_para_chat(
    str(RAIZ.parent / "notas" / "Servidor IA.md"), str(RAIZ))
chequear("tambien puede señalar un documento fuera del proyecto",
         relativa and ruta.startswith(".."), ruta)

print("\n== La imagen cruda ==")
r = panel.archivos_crudo(cwd=str(RAIZ), ruta="CLAUDE.md")
chequear("un .md NO se sirve por la ruta de imagenes", getattr(r, "status_code", 0) == 404)
r = panel.archivos_crudo(cwd=r"C:\Windows", ruta="Web/Wallpaper/img0.jpg")
chequear("una imagen de afuera del proyecto tampoco",
         getattr(r, "status_code", 0) == 404)

print(f"\n{ok} verdes, {fallo} en rojo")
sys.exit(1 if fallo else 0)
