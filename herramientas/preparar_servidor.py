"""Preparar una carpeta para que pueda abrir charlas en el servidor (2026-11-17).

Pedido de Martín: que los chief de todos sus proyectos puedan mandar trabajo al servidor.
Una charla del servidor trabaja sobre los archivos de ALLÁ, así que la carpeta tiene que
existir allá y mantenerse igual a la de acá. Este comando hace las tres cosas de una:

  1. crea la carpeta en el servidor,
  2. le arma su sincronización en los dos sentidos (Mutagen),
  3. la anota en `maquinas.json`, que es lo que le dice al panel que ahí hay servidor.

    python -m herramientas.preparar_servidor <carpeta> [<carpeta> ...]
    python -m herramientas.preparar_servidor --solo-ver <carpeta>     (no toca nada)
    python -m herramientas.preparar_servidor --listar
    python -m herramientas.preparar_servidor --quitar <carpeta>

⭐⭐ LA REGLA: **solo viaja lo que está adentro de un repositorio git, y nunca un archivo de
claves.** No es prolijidad, son dos cosas concretas:
  - Lo que una charla del servidor borra allá, se borra acá. Con git se recupera lo
    commiteado; sin git no se recupera nada. Por eso una carpeta sin ningún repositorio
    adentro se rechaza, y en una carpeta que junta varios repositorios los archivos sueltos
    de afuera no viajan.
  - En las carpetas hay `.env` con claves de clientes (medido ese día: 56 en una sola). Allá
    corren charlas de OTRA cuenta de Claude, sin pedir permiso. La lista `SIEMPRE_AFUERA` va
    última a propósito: le gana a cualquier excepción que traiga el `.gitignore` del proyecto.

⚠ Las reglas de qué no viaja se fijan al crear la sincronización: Mutagen no deja cambiarlas
después. Si cambió el `.gitignore` de un proyecto, `--quitar` y volver a preparar.
⚠ Lo que YA ignora el `.gitignore` se anota dos veces: la regla traducida (para lo que
aparezca mañana) y la lista de lo que hoy está ignorado (por si la traducción no es exacta:
la sintaxis de Mutagen es "casi" la de git).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from app.rutas import MUTAGEN, REMOTAS_MAQUINAS, REMOTAS_REGLAS

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HONDO = 4                 # hasta qué profundidad se buscan repositorios adentro de una carpeta
TOPE_MB = 700             # más que esto no es código: se frena y se pregunta
PREFIJO = "srv-"          # nombre de la sincronización: srv-<carpeta de allá>
NO_ENTRAR = {"node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".claude"}

# Nunca viaja, lo diga o no el .gitignore del proyecto. Va ÚLTIMA: gana.
SIEMPRE_AFUERA = [
    # `.git` suelto: Mutagen ya deja afuera la CARPETA .git, pero en un worktree `.git` es un
    # ARCHIVO de un renglón que apunta a una ruta de esta máquina. Allá no sirve, y si una
    # charla lo borrara allá se borraría acá y rompería el worktree (visto el 2026-11-17).
    ".git",
    ".env", ".env.*", "*.env", ".envrc",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "id_rsa*", "id_ed25519*",
    "*credentials*", "*credenciales*", "*token*.json", "*secret*.json", "*.kdbx",
    "service-account*.json", ".npmrc", ".netrc", ".git-credentials",
    "*.sqlite", "*.sqlite3", "*.db",
    "node_modules/", ".venv/", "venv/", "__pycache__/", ".next/", ".turbo/", ".cache/",
    ".claude/", ".mutagen*", "*.log", "Thumbs.db", ".DS_Store",
    # Las plantillas sin claves sí viajan: una charla las necesita para entender el proyecto.
    "!.env.example", "!.env.ejemplo", "!.env.sample", "!.env.template",
]


def _correr(orden, entrada=None, espera=120, cwd=None):
    r = subprocess.run(orden, input=entrada, capture_output=True, timeout=espera, cwd=cwd,
                       creationflags=_SIN_VENTANA)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def _git(repo, *args):
    codigo, salida, _ = _correr(["git", "-c", "core.quotepath=off", "-C", str(repo), *args])
    return salida if codigo == 0 else ""


def _igual(a, b):
    n = lambda x: os.path.normcase(os.path.normpath(str(x)))
    return n(a) == n(b)


def _es_repo(carpeta):
    arriba = _git(carpeta, "rev-parse", "--show-toplevel").strip()
    return bool(arriba) and _igual(arriba, carpeta)


def repos_de(carpeta):
    """Los repositorios de esa carpeta: ella misma, o los que tenga adentro (sin anidar)."""
    carpeta = Path(carpeta)
    if _es_repo(carpeta):
        return [carpeta]
    hallados = []

    def bajar(d, nivel):
        try:
            hijos = sorted(p for p in d.iterdir() if p.is_dir())
        except OSError:
            return
        for h in hijos:
            if h.name in NO_ENTRAR or h.name == ".git":
                continue
            if (h / ".git").exists():
                if _es_repo(h):
                    hallados.append(h)
                continue          # adentro de un repositorio no se busca otro
            if nivel < HONDO:
                bajar(h, nivel + 1)

    bajar(carpeta, 1)
    return hallados


def _escapar(ruta):
    return re.sub(r"([\\*?\[\]{}!#])", r"\\\1", ruta)


def _traducir_gitignore(texto, donde):
    """Las reglas de un .gitignore que vive en `donde` (relativo a la raíz que se sincroniza,
    con barras comunes; vacío = la raíz), pasadas a reglas ancladas a esa raíz."""
    salida = []
    for renglon in texto.splitlines():
        r = renglon.rstrip()
        if not r.strip() or r.lstrip().startswith("#"):
            continue
        r = r.strip()
        niega = r.startswith("!")
        cuerpo = r[1:] if niega else r
        if not cuerpo:
            continue
        con_barra = "/" in cuerpo.rstrip("/")
        if con_barra:
            cuerpo = "/" + "/".join(x for x in (donde, cuerpo.lstrip("/")) if x)
        elif donde:
            cuerpo = "/" + donde + "/**/" + cuerpo
        salida.append(("!" if niega else "") + cuerpo)
    return salida


def reglas_de(carpeta, repos):
    """La lista ordenada de lo que NO viaja. El orden importa: la última que acierta, gana."""
    carpeta = Path(carpeta)
    reglas = []
    rel = lambda p: Path(p).relative_to(carpeta).as_posix() if not _igual(p, carpeta) else ""
    if not (len(repos) == 1 and _igual(repos[0], carpeta)):
        # Carpeta que junta repositorios: se cierra todo y se abre solo el camino a cada uno.
        abiertas = {""}                         # carpetas por las que hay que pasar
        for r in repos:
            partes = rel(r).split("/")
            for i in range(1, len(partes)):
                abiertas.add("/".join(partes[:i]))
        permitidos = {rel(r) for r in repos} | abiertas
        for a in sorted(abiertas, key=lambda x: (x.count("/"), x)):
            reglas.append(("/" + _escapar(a) if a else "") + "/*")
            for p in sorted(permitidos):
                if p and (p.rsplit("/", 1)[0] if "/" in p else "") == a:
                    reglas.append("!/" + _escapar(p))
    for r in repos:
        base = rel(r)
        # 1) las reglas del proyecto, traducidas (valen para lo que aparezca mañana)
        archivos = [".gitignore"] + [x for x in _git(r, "ls-files", "-co", "--exclude-standard",
                                                     "--", "*.gitignore").splitlines()
                                     if x and x != ".gitignore"]
        for g in archivos:
            ruta = Path(r) / g
            if not ruta.is_file():
                continue
            donde = "/".join(x for x in (base, Path(g).parent.as_posix().strip(".")) if x)
            try:
                reglas += _traducir_gitignore(ruta.read_text(encoding="utf-8", errors="replace"), donde)
            except OSError:
                pass
        # 2) lo que HOY está ignorado, por nombre y apellido
        for trozo in _git(r, "status", "--porcelain", "--ignored", "-z").split("\0"):
            if trozo.startswith("!! "):
                reglas.append("/" + "/".join(x for x in (_escapar(base), _escapar(trozo[3:].rstrip("/"))) if x))
    return reglas + SIEMPRE_AFUERA


def peso_de(repos):
    archivos = total = 0
    for r in repos:
        for f in _git(r, "ls-files", "-co", "--exclude-standard").splitlines():
            if not f:
                continue
            try:
                total += (Path(r) / f).stat().st_size
                archivos += 1
            except OSError:
                pass
    return archivos, total


# ------------------------------------------------------------------ maquinas.json

def _leer_maquinas():
    return json.loads(REMOTAS_MAQUINAS.read_text(encoding="utf-8"))


def _guardar_maquinas(datos):
    tmp = REMOTAS_MAQUINAS.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # El panel lee este archivo a cada rato, y en Windows no se puede reemplazar un archivo
    # mientras otro lo tiene abierto: se reintenta en vez de caerse (pasó el 2026-11-17, en
    # medio de una tanda, con el cuarto proyecto).
    for intento in range(40):
        try:
            os.replace(tmp, REMOTAS_MAQUINAS)
            return
        except PermissionError:
            time.sleep(0.15)
    os.replace(tmp, REMOTAS_MAQUINAS)


def _maquina(datos, nombre):
    buenas = [m for m in datos if isinstance(m, dict) and (not nombre or m.get("nombre") == nombre)]
    if len(buenas) != 1:
        sys.exit("No sé a qué servidor: pasá --maquina. Hay: " + ", ".join(str(m.get("nombre")) for m in datos))
    m = buenas[0]
    if not m.get("trabajo_host"):
        sys.exit(f"A «{m.get('nombre')}» le falta `trabajo_host` en maquinas.json (la carpeta del "
                 "servidor donde viven los proyectos).")
    return m


def _slug(nombre, usados):
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    plano = re.sub(r"[^A-Za-z0-9-]+", "-", plano).strip("-") or "proyecto"
    slug, n = plano, 2
    while slug.lower() in usados:
        slug, n = f"{plano}-{n}", n + 1
    return slug


def _mutagen(*args, espera=300):
    if not MUTAGEN.is_file():
        sys.exit(f"No encuentro Mutagen en {MUTAGEN}.")
    return _correr([str(MUTAGEN), *args], espera=espera)


def _estado_sync(nombre):
    """(estado, archivos de acá, archivos de allá, conflictos) de esa sincronización."""
    _, salida, _ = _mutagen("sync", "list", nombre, espera=60)
    estado = (re.search(r"^Status: (.*)$", salida, re.M) or [None, ""])[1].strip()
    cuentas = re.findall(r"(\d+) files?", salida)
    return estado, (int(cuentas[0]) if cuentas else 0), (int(cuentas[1]) if len(cuentas) > 1 else 0), \
        "Conflicts:" in salida


# ------------------------------------------------------------------------- acciones

def _prohibida(carpeta, datos):
    c = Path(carpeta)
    casa = Path.home()
    if _igual(c, casa) or _igual(c, c.anchor):
        return "es tu carpeta personal entera: ahí viven las claves de todo"
    for mala in (casa / ".claude", casa / ".ssh", REMOTAS_MAQUINAS.parent.parent):
        try:
            c.resolve().relative_to(Path(mala).resolve())
            return f"está adentro de {mala}: no es un proyecto"
        except ValueError:
            pass
    for m in datos:
        for p in (m.get("proyectos") or []):
            otra = Path(p.get("local", ""))
            if _igual(otra, c):
                return "YA"
            for a, b in ((c, otra), (otra, c)):
                try:
                    a.resolve().relative_to(b.resolve())
                    return f"se pisa con {otra}, que ya está preparada (una adentro de la otra)"
                except ValueError:
                    pass
    return ""


def preparar(carpeta, nombre_maquina, solo_ver=False, grande=False):
    carpeta = Path(os.path.abspath(carpeta))
    if not carpeta.is_dir():
        return "NO", "no existe"
    datos = _leer_maquinas()
    m = _maquina(datos, nombre_maquina)
    motivo = _prohibida(carpeta, datos)
    if motivo == "YA":
        return "YA", "ya estaba preparada"
    if motivo:
        return "NO", motivo
    repos = repos_de(carpeta)
    if not repos:
        return "NO", "no tiene ningún repositorio git: lo que se borre allá no se podría recuperar"
    archivos, total = peso_de(repos)
    if total > TOPE_MB * 1e6 and not grande:
        return "NO", f"pesa {total / 1e6:.0f} MB (tope {TOPE_MB}): con --grande va igual"
    reglas = reglas_de(carpeta, repos)
    usados = {str(p.get("remoto", "")).rsplit("/", 1)[-1].lower() for x in datos for p in (x.get("proyectos") or [])}
    slug = _slug(carpeta.name, usados)
    resumen = f"{len(repos)} repo(s), ~{archivos} archivos, {total / 1e6:.1f} MB, {len(reglas)} reglas → {slug}"
    if solo_ver:
        print(f"\n{carpeta}\n  {resumen}")
        for r in repos:
            print("  repo:", r)
        for r in reglas[:-len(SIEMPRE_AFUERA)]:
            print("  no viaja:", r)
        print(f"  (+ las {len(SIEMPRE_AFUERA)} de siempre: claves, bases, dependencias)")
        return "VER", resumen

    host = m["trabajo_host"].rstrip("/") + "/" + slug
    dueno = str(m.get("dueno_archivos") or "1500")
    orden = (f"if [ -e '{host}' ] && [ -n \"$(ls -A '{host}' 2>/dev/null)\" ]; then echo OCUPADA; "
             f"else mkdir -p '{host}' && chown {dueno}:{dueno} '{host}' && echo LISTA; fi")
    codigo, salida, error = _correr(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", m["ssh"], orden], espera=60)
    if "LISTA" not in salida:
        return "NO", ("la carpeta de allá ya tiene cosas adentro" if "OCUPADA" in salida
                      else "no pude crear la carpeta allá: " + (error.strip()[:120] or salida.strip()[:120]))

    REMOTAS_REGLAS.mkdir(parents=True, exist_ok=True)
    yml = REMOTAS_REGLAS / (slug + ".yml")
    yml.write_text("sync:\n  defaults:\n    ignore:\n      vcs: true\n      paths:\n"
                   + "".join("        - " + json.dumps(r, ensure_ascii=False) + "\n" for r in reglas),
                   encoding="utf-8")
    nombre = PREFIJO + slug
    codigo, salida, error = _mutagen(
        "sync", "create", "--name", nombre, "--no-global-configuration", "-c", str(yml),
        "--mode", "two-way-safe", "--symlink-mode", "ignore",
        "--default-owner-beta", "id:" + dueno, "--default-group-beta", "id:" + dueno,
        "--default-file-mode-beta", "0644", "--default-directory-mode-beta", "0755",
        str(carpeta), f"{m['ssh']}:{host}")
    if codigo != 0:
        return "NO", "Mutagen no la pudo crear: " + (error.strip() or salida.strip())[-200:]

    # Recién con la sincronización andando se le dice al panel que ahí hay servidor.
    hasta, estado, aca, alla, choque = time.time() + 240, "", 0, 0, False
    while time.time() < hasta:
        estado, aca, alla, choque = _estado_sync(nombre)
        if estado.startswith("Watching") and aca == alla:
            break
        time.sleep(3)
    datos = _leer_maquinas()
    m = _maquina(datos, nombre_maquina)
    m.setdefault("proyectos", []).append(
        {"local": str(carpeta), "remoto": m["cwd_remoto"].rstrip("/") + "/" + slug})
    _guardar_maquinas(datos)
    cola = f"{aca} archivos acá, {alla} allá" + (" · ⚠ CONFLICTOS" if choque else "")
    if not estado.startswith("Watching"):
        cola += f" · ⚠ todavía «{estado}»"
    return "OK", f"{resumen} · {cola}"


def quitar(carpeta, nombre_maquina):
    carpeta = Path(os.path.abspath(carpeta))
    datos = _leer_maquinas()
    m = _maquina(datos, nombre_maquina)
    quedan, sacado = [], None
    for p in m.get("proyectos") or []:
        if _igual(p.get("local", ""), carpeta):
            sacado = p
        else:
            quedan.append(p)
    if not sacado:
        return "NO", "no estaba preparada"
    slug = sacado["remoto"].rsplit("/", 1)[-1]
    m["proyectos"] = quedan
    _guardar_maquinas(datos)                      # primero el panel deja de ofrecerla
    codigo, salida, error = _mutagen("sync", "terminate", PREFIJO + slug, espera=60)
    return "OK", ("sincronización cortada" if codigo == 0 else "no había sincronización con ese nombre") + \
        f". La copia de allá NO se borró: {m['trabajo_host'].rstrip('/')}/{slug}"


def listar(nombre_maquina):
    datos = _leer_maquinas()
    m = _maquina(datos, nombre_maquina)
    for p in m.get("proyectos") or []:
        slug = p["remoto"].rsplit("/", 1)[-1]
        nombre = PREFIJO + slug
        estado, aca, alla, choque = _estado_sync(nombre)
        if not estado:                             # la primera se creó a mano, con otro nombre
            nombre = slug + "-servidor"
            estado, aca, alla, choque = _estado_sync(nombre)
        marca = "⚠ CONFLICTOS " if choque else ""
        print(f"{p['local']}\n    → {p['remoto']} · {estado or 'SIN SINCRONIZACIÓN'} · {aca} acá / {alla} allá {marca}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("carpetas", nargs="*")
    a.add_argument("--maquina", default="")
    a.add_argument("--solo-ver", action="store_true", help="muestra qué viajaría, sin tocar nada")
    a.add_argument("--grande", action="store_true", help=f"aceptar carpetas de más de {TOPE_MB} MB")
    a.add_argument("--quitar", action="store_true")
    a.add_argument("--listar", action="store_true")
    args = a.parse_args()
    if args.listar:
        return listar(args.maquina)
    if not args.carpetas:
        a.error("falta la carpeta")
    for c in args.carpetas:
        if args.quitar:
            resultado, detalle = quitar(c, args.maquina)
        else:
            resultado, detalle = preparar(c, args.maquina, args.solo_ver, args.grande)
        if resultado != "VER":
            print(f"{resultado:3} {c} — {detalle}", flush=True)


if __name__ == "__main__":
    main()
