"""Que una sesion de Codex del celular pueda commitear en un proyecto tuyo (2026-08-20).

El sintoma: las sesiones nacian con `.git` en solo lectura y cualquier commit moria
con "Unable to create '.git/index.lock': Permission denied", aunque el
`~/.codex/config.toml` dijera `danger-full-access`. La causa: `codex_mandar` mandaba
`--sandbox workspace-write` por linea de comandos, y ESA flag pisa la del config.

Lo que se prueba:

 1. `proyecto_confiable` de fabrica: toda carpeta adentro de las raices de trabajo si,
    incluso sin `.git`; una carpeta cualquiera (Temp) no.
 2. Que la lista escrita a mano mande sobre la regla de fabrica, y que "no" gane.
 3. Que `_codex_sandbox` traduzca eso a las flags correctas.
 4. ⭐ De punta a punta y GASTANDO UN TURNO REAL de Codex: se crea un repo de verdad
    adentro de una raiz confiable, se lo lanza por `codex_mandar` (el lanzador real,
    no una imitacion) y se verifica que el commit QUEDO en el log de git.

El paso 4 se saltea con  --sin-turno  si solo queres correr lo barato.

Correr:  D:\\IA\\envs\\wpp\\python.exe -m pruebas.probar_codex_git_confiable
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.rutas import PROYECTOS_CONFIABLES
from app.voz import sesiones_movil as sm

FALLOS = []


def va(condicion, que):
    print(("  ok   " if condicion else "  FALLA ") + que)
    if not condicion:
        FALLOS.append(que)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def repo_nuevo(carpeta):
    """Un repo git de verdad, con un commit de base."""
    carpeta.mkdir(parents=True, exist_ok=True)
    git(carpeta, "init", "-q")
    git(carpeta, "config", "user.email", "prueba@local")
    git(carpeta, "config", "user.name", "Prueba Codex")
    (carpeta / "a.txt").write_text("hola\n", encoding="utf-8")
    git(carpeta, "add", "a.txt")
    git(carpeta, "commit", "-qm", "base")
    return carpeta


# --- 1 y 2: quien es confiable -----------------------------------------------

def probar_confiables(repo_trabajo, repo_afuera, sin_git):
    print("\n1. Quien es confiable, de fabrica")
    va(sm.proyecto_confiable(repo_trabajo),
       "un proyecto dentro de una raiz de trabajo es confiable")
    va(not sm.proyecto_confiable(repo_afuera),
       "un repo git en Temp NO es confiable")
    va(sm.proyecto_confiable(sin_git),
       "una carpeta de trabajo sin .git tambien es confiable")
    va(not sm.proyecto_confiable(""),
       "sin carpeta no es confiable (no revienta)")

    print("\n2. La lista escrita a mano manda")
    guardado = PROYECTOS_CONFIABLES.read_text(encoding="utf-8") \
        if PROYECTOS_CONFIABLES.exists() else None
    try:
        PROYECTOS_CONFIABLES.write_text(
            json.dumps({"si": [str(repo_afuera)]}), encoding="utf-8")
        va(sm.proyecto_confiable(repo_afuera),
           '"si" sube a confiable una carpeta que la regla de fabrica rechazaba')

        PROYECTOS_CONFIABLES.write_text(
            json.dumps({"si": [str(repo_afuera)], "no": [str(repo_afuera)]}),
            encoding="utf-8")
        va(not sm.proyecto_confiable(repo_afuera), '"no" le gana a "si"')

        PROYECTOS_CONFIABLES.write_text(
            json.dumps({"no": [str(repo_trabajo.parent)]}), encoding="utf-8")
        va(not sm.proyecto_confiable(repo_trabajo),
           '"no" sobre la carpeta madre alcanza para bajar al hijo')

        PROYECTOS_CONFIABLES.write_text("{ esto no es json", encoding="utf-8")
        va(sm.proyecto_confiable(repo_trabajo),
           "un archivo roto no rompe nada: vale la regla de fabrica")
    finally:
        if guardado is None:
            PROYECTOS_CONFIABLES.unlink(missing_ok=True)
        else:
            PROYECTOS_CONFIABLES.write_text(guardado, encoding="utf-8")

    print("\n3. Las flags que sale a pedir")
    va(sm._codex_sandbox(repo_trabajo) == ["--sandbox", "danger-full-access"],
       "el proyecto confiable va sin jaula")
    afuera = sm._codex_sandbox(repo_afuera)
    va(afuera[:2] == ["--sandbox", "workspace-write"]
       and "sandbox_workspace_write.network_access=true" in afuera,
       "el que no es confiable conserva la jaula Y la red de antes")


# --- 4: el commit de verdad ---------------------------------------------------

def probar_commit_real(repo):
    print("\n4. Un turno REAL de Codex commiteando (esto gasta cupo)")
    antes = git(repo, "log", "--oneline").stdout.strip().splitlines()
    orden = ("Corré exactamente este comando y nada mas:\n"
             "    git commit --allow-empty -m 'sonda de permisos'\n"
             "Despues contestá en UNA linea: OK si salio, o el error textual si fallo.")
    try:
        respuesta, sid = sm.codex_mandar(str(repo), None, orden)
    except Exception as e:
        va(False, f"el turno de Codex reviento: {e}")
        return
    print(f"     Codex dijo: {(respuesta or '').strip()[:160]}")
    print(f"     sesion: {sid}")

    despues = git(repo, "log", "--oneline").stdout.strip().splitlines()
    va(len(despues) == len(antes) + 1,
       f"quedo UN commit nuevo en el log (antes {len(antes)}, despues {len(despues)})")
    va(any("sonda de permisos" in l for l in despues),
       "el commit nuevo es el que se le pidio")
    va("index.lock" not in (respuesta or ""),
       "no aparece el 'Permission denied' de .git/index.lock")


def main():
    raiz_trabajo = Path(sm.RAICES_CONFIABLES[0])
    if not raiz_trabajo.is_dir():
        print(f"No existe {raiz_trabajo}: no puedo probar el caso confiable.")
        return 2

    banco = raiz_trabajo / "_prueba-codex-git"
    afuera = Path(tempfile.gettempdir()) / "_prueba-codex-git-afuera"
    shutil.rmtree(banco, ignore_errors=True)
    shutil.rmtree(afuera, ignore_errors=True)
    try:
        repo_trabajo = repo_nuevo(banco / "proyecto")
        sin_git = banco / "sin-repo"
        sin_git.mkdir(parents=True, exist_ok=True)
        repo_afuera = repo_nuevo(afuera)

        probar_confiables(repo_trabajo, repo_afuera, sin_git)
        if "--sin-turno" not in sys.argv:
            probar_commit_real(repo_trabajo)
    finally:
        shutil.rmtree(banco, ignore_errors=True)
        shutil.rmtree(afuera, ignore_errors=True)

    print("\n" + ("TODO BIEN" if not FALLOS else f"{len(FALLOS)} FALLAS:"))
    for f in FALLOS:
        print("  - " + f)
    return 1 if FALLOS else 0


if __name__ == "__main__":
    raise SystemExit(main())
