"""Deja las skills de Martin visibles para sus DOS cerebros, sin que el se acuerde.

⚠ ESTA CARPETA ES UNA ESCALA, NO EL DESTINO. Esto es herramienta GLOBAL: su lugar
definitivo es `~/.claude/skills/sincro-skills/`. Vive aca porque el 2026-08-28 la
sesion no tenia permiso para escribir en esa carpeta y reiniciar Claude Code costaba
perder la conversacion. Se mueve con `herramientas/sincro-skills/instalar.ps1`.

El problema. Martin trabaja con Claude Code y con Codex. Cada uno busca las skills en
su propia carpeta, asi que una skill escrita de un lado no existe para el otro. Hasta
hoy eso se resolvia a mano: alguien creo 15 enlaces el 2026-08-19 y uno mas el 24/08.
Nada los mantenia al dia, y ya habia agujeros — `3d` vivia solo del lado de Codex y
Claude no la veia.

Este script recorre las tres carpetas y crea el enlace que falte, en las dos
direcciones. Es idempotente: correrlo mil veces da lo mismo que correrlo una.

⭐⭐ DOS REGLAS QUE NO SE TOCAN

1. **Enlace POR SKILL, jamas la carpeta contenedora.** Enlazar `~/.claude/skills`
   entera hace que Claude Code deje de cargar las skills de usuario (regresion
   conocida, issue anthropics/claude-code#38051, desde ~v2.1.69, por un parche de
   seguridad sobre symlinks). Enlazar cada `<skill>/` por separado si esta soportado y
   documentado de los dos lados. Si alguien "simplifica" esto enlazando la carpeta,
   rompe a Claude en silencio.

2. **Un enlace se detecta con `os.readlink()`, NUNCA con `is_symlink()`.** En Windows
   estos enlaces son *junctions*, y para Python un junction NO es un symlink:
   `Path.is_symlink()` devuelve **False** aunque `os.readlink()` funcione perfecto.
   Medido el 2026-08-28 contra los enlaces reales de esta maquina — los tres casos
   (junction hacia Claude, junction hacia .agents, carpeta real) contestaron `False`.
   Detectarlos con `is_symlink()` haria que el script viera carpetas reales por todos
   lados y reportara un choque de nombres por CADA skill, para siempre.
   (Git Bash los muestra como `lrwxrwxrwx`, o sea que `ls` y Python no coinciden. El
   que manda es `os.readlink()`.)

Se usa junction (`_winapi.CreateJunction`) y no symlink porque **no pide permisos de
administrador**, mientras que `os.symlink` en Windows si (salvo modo desarrollador).

QUE NO TOCA
- Lo que no es carpeta (hay un `_molde-automejora.md` suelto en la carpeta de skills).
- Las que empiezan con punto: `.system` son las que Codex trae de fabrica.
- `synced/`, que Claude Code reserva para lo que baja de claude.ai.
- La cuarentena: skills bajadas de internet que todavia no aprobo Martin. Esas NO se
  enlazan aunque el nombre ya sea conocido — es toda la razon de que exista la puerta.

EL ANUNCIO
`~/.claude/skills-conocidas.json` es memoria, no una lista de permitidos: sirve para
que el aviso de "aparecio una skill nueva" salga UNA vez y no en cada mensaje. La
decision (2026-08-28) fue avisar y no bloquear: una skill que aparece puede ser una que
Martin le pidio a un agente o una que se bajo sola, y para este script son
indistinguibles. Bloquear todo convertia la puerta en una traba diaria. Entonces se
enlaza y se anuncia, y **un nombre que el no reconozca ES la alarma**.

Corre colgado del gancho `UserPromptSubmit`, o sea en CADA mensaje de Martin a Claude,
en todos los proyectos. De ahi dos exigencias:
- **callado en el camino feliz**: lo que imprima se le inyecta a la conversacion;
- **barato**: solo `stat`, no lee el contenido de ningun archivo.

Uso:
    python sincro.py              # enlaza y habla solo si hizo o encontro algo
    python sincro.py --simular    # dice que haria, sin tocar nada
    python sincro.py --json       # para el panel
    python sincro.py --deshacer   # saca los enlaces, deja las carpetas reales
"""

import json
import os
import sys
from pathlib import Path

CASA = Path.home()

# Las tres raices donde un cerebro busca skills. `~/.codex/skills` es donde mira el
# Codex instalado hoy (0.148); `~/.agents/skills` es la ruta que nombra su doc nueva y
# ya existe en esta maquina (ahi vive `prompt-master`). Se miran las dos porque Codex
# esta migrando de una a la otra.
# ⚠ La prueba las reemplaza por carpetas de mentira: no son constantes de adorno.
CLAUDE_SKILLS = CASA / ".claude" / "skills"
CODEX_SKILLS = CASA / ".codex" / "skills"
AGENTS_SKILLS = CASA / ".agents" / "skills"

RAICES = [CLAUDE_SKILLS, CODEX_SKILLS, AGENTS_SKILLS]

# ⭐⭐ Hay TRES carpetas pero solo DOS lectores, y esa es toda la logica del script.
# Codex mira `.codex/skills` Y `.agents/skills` (comprobado con `codex debug
# prompt-input`: de ahi salen `avisar` y `prompt-master` respectivamente). Entonces una
# skill que ya vive en `.agents/skills` **Codex ya la ve**, y enlazarsela tambien en
# `.codex/skills` no le agrega nada: le muestra la misma skill dos veces.
#
# La pregunta correcta no es "¿esta en las tres carpetas?" sino **"¿la ve cada
# cerebro?"**. Razonandolo como carpetas daban 2 enlaces por hacer; razonandolo como
# lectores da 1, que es el que de verdad falta.
LECTORES = [
    {"nombre": "Claude", "lee": [CLAUDE_SKILLS], "pone_en": CLAUDE_SKILLS},
    {"nombre": "Codex", "lee": [CODEX_SKILLS, AGENTS_SKILLS], "pone_en": CODEX_SKILLS},
]
CUARENTENA = CASA / ".claude" / "skills-cuarentena"
CONOCIDAS = CASA / ".claude" / "skills-conocidas.json"

# `synced` la reserva Claude Code para las skills que Martin habilita en claude.ai: las
# baja el CLI y las vuelve a bajar, asi que enlazarlas seria pelearse con el.
RESERVADAS = {"synced"}


def es_enlace(p):
    """¿`p` es un enlace a otra carpeta? Devuelve el destino, o None.

    ⭐ Con `os.readlink`, no con `is_symlink()`: ver la regla 2 del encabezado. Un
    junction de Windows contesta que NO es symlink y sin embargo es un enlace.
    """
    try:
        return os.readlink(str(p))
    except OSError:
        return None


def _limpio(p):
    """La ruta en forma comparable: sin el prefijo `\\?\\`, normalizada y sin mayusculas.

    ⚠⚠ EL PREFIJO IMPORTA. `os.readlink` en Windows devuelve
    `\\?\\C:\\Users\\...` y **`Path.resolve()` NO se lo saca** (medido el 2026-08-28).
    Comparando sin limpiar, un enlace correcto parece apuntar a otro lado, el script lo
    marca para rehacer, y termina **borrando y recreando los 16 enlaces en cada
    corrida** — o sea en cada mensaje, porque esto cuelga de un gancho. Lo cazo el
    `--simular` antes de tocar nada; sin esa pasada en seco entraba derecho.
    """
    s = str(p)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    return os.path.normcase(os.path.normpath(s))


def _mismo(a, b):
    """¿Dos rutas apuntan al mismo lugar? Sin syscalls: esto corre en cada mensaje."""
    return _limpio(a) == _limpio(b)


def enlazar(destino, donde):
    """Crea el enlace `donde` -> `destino`. Junction en Windows, symlink en el resto."""
    donde.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(Path(destino).resolve()), str(donde))
    else:
        os.symlink(str(Path(destino).resolve()), str(donde), target_is_directory=True)


def desenlazar(p):
    """Saca un enlace SIN tocar la carpeta real del otro lado.

    ⚠ `os.rmdir` sobre un junction borra el enlace y deja el destino intacto
    (verificado el 2026-08-28). `shutil.rmtree` NO: seguiria adentro y borraria las
    skills de verdad. Por eso aca no se usa rmtree ni aunque parezca mas prolijo.
    """
    if os.name == "nt":
        os.rmdir(str(p))
    else:
        os.unlink(str(p))


def _skills_de(raiz):
    """{nombre: ruta} de lo que hay en una raiz. Ver "QUE NO TOCA" del encabezado."""
    salida = {}
    if not raiz.is_dir():
        return salida
    try:
        hijos = sorted(raiz.iterdir())
    except OSError:
        return salida
    for d in hijos:
        if d.name.startswith(".") or d.name.lower() in RESERVADAS:
            continue
        try:
            if not d.is_dir():          # un .md suelto no es una skill
                continue
        except OSError:
            continue
        salida[d.name] = d
    return salida


def _leer_conocidas():
    try:
        d = json.loads(CONOCIDAS.read_text(encoding="utf-8"))
        return set(d.get("skills") or [])
    except Exception:
        return set()


def _guardar_conocidas(nombres):
    try:
        CONOCIDAS.write_text(
            json.dumps({"skills": sorted(nombres)}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    except OSError:
        pass                            # no poder anotar no justifica romper un mensaje


def revisar():
    """Mira las tres raices y decide. NO toca nada: solo devuelve que habria que hacer.

    Separar el diagnostico de la accion es lo que deja probar todo esto sin crear ni un
    enlace, y es lo que hace posible `--simular`.
    """
    porraiz = {r: _skills_de(r) for r in RAICES}

    # Cada nombre, con las raices donde aparece como carpeta REAL y como enlace.
    reales, enlaces = {}, {}
    for raiz, skills in porraiz.items():
        for nombre, ruta in skills.items():
            if es_enlace(ruta) is None:
                reales.setdefault(nombre, []).append(ruta)
            else:
                enlaces.setdefault(nombre, []).append(ruta)

    plan = {"crear": [], "choques": [], "vistas": sorted(set(reales) | set(enlaces))}
    for nombre, rutas in sorted(reales.items()):
        if len(rutas) > 1:
            # ⭐ Dos originales distintos con el mismo nombre. Ninguna regla automatica
            # puede elegir bien: o pisa algo que escribio Martin, o elige al azar. Se
            # deja todo como esta, se avisa con las dos rutas, y se sigue con el resto
            # (decision del 2026-08-28: "frena y avisa").
            plan["choques"].append({"nombre": nombre, "rutas": [str(x) for x in rutas]})
            continue
        origen = rutas[0]
        for lector in LECTORES:
            # ¿Este cerebro ya la ve? Le alcanza con encontrarla en CUALQUIERA de las
            # carpetas que mira: como ella misma, o como un enlace que le apunte.
            la_ve = False
            viejo = None                # un enlace suyo que apunta a otra parte
            for raiz in lector["lee"]:
                ya = porraiz.get(raiz, {}).get(nombre)
                if ya is None:
                    continue
                if _mismo(ya, origen) or _mismo(es_enlace(ya) or "", origen):
                    la_ve = True
                    break
                if es_enlace(ya) is not None and _mismo(raiz, lector["pone_en"]):
                    viejo = ya          # quedo de una version anterior o de una mudanza
            if la_ve:
                continue
            plan["crear"].append({
                "nombre": nombre, "origen": str(origen), "cerebro": lector["nombre"],
                "donde": str(lector["pone_en"] / nombre), "rehacer": viejo is not None})
    return plan


def aplicar(plan, simular=False):
    """Crea los enlaces del plan. Devuelve (hechos, fallados)."""
    hechos, fallados = [], []
    for item in plan["crear"]:
        donde, origen = Path(item["donde"]), Path(item["origen"])
        # ⭐ Cinturon: nunca enlazar una raiz. Si un error de calculo pusiera aca la
        # carpeta contenedora, se rompe Claude Code entero (regla 1 del encabezado).
        if donde in RAICES or origen in RAICES:
            fallados.append((item["nombre"], "intento enlazar una carpeta raiz"))
            continue
        # Y nunca traer nada desde la cuarentena: eso saltearia la puerta.
        if CUARENTENA == origen.parent or CUARENTENA in origen.parents:
            fallados.append((item["nombre"], "viene de la cuarentena"))
            continue
        if simular:
            hechos.append(item)
            continue
        try:
            if item["rehacer"]:
                desenlazar(donde)
            enlazar(origen, donde)
            hechos.append(item)
        except OSError as e:
            fallados.append((item["nombre"], str(e)))
    return hechos, fallados


def deshacer(simular=False):
    """Saca TODOS los enlaces de las tres raices. Las carpetas reales no se tocan."""
    sacados = []
    for raiz in RAICES:
        for nombre, ruta in _skills_de(raiz).items():
            if es_enlace(ruta) is None:
                continue
            if not simular:
                try:
                    desenlazar(ruta)
                except OSError:
                    continue
            sacados.append(str(ruta))
    return sacados


def main(argv):
    simular = "--simular" in argv
    if "--deshacer" in argv:
        sacados = deshacer(simular)
        print(f"{'sacaria' if simular else 'saque'} {len(sacados)} enlaces "
              f"(las carpetas reales quedaron intactas)")
        for s in sacados:
            print("   ", s)
        return 0

    plan = revisar()
    conocidas = _leer_conocidas()
    primera = not CONOCIDAS.exists()
    nuevas = [n for n in plan["vistas"] if n not in conocidas]
    hechos, fallados = aplicar(plan, simular)

    if not simular:
        _guardar_conocidas(set(plan["vistas"]) | conocidas)

    if "--json" in argv:
        print(json.dumps({"enlazadas": hechos, "choques": plan["choques"],
                          "nuevas": [] if primera else nuevas,
                          "fallados": [list(f) for f in fallados]},
                         ensure_ascii=False))
        return 0

    # ⭐ La primera corrida siembra el registro EN SILENCIO: todo es "nuevo" y anunciar
    # las 16 de golpe seria ruido, no informacion.
    if primera:
        nuevas = []

    # ⭐ Callado en el camino feliz: esto se le inyecta a cada conversacion.
    if simular and hechos:
        print(f"[skills] enlazaria {len(hechos)}:")
        for h in hechos:
            print(f"   {h['nombre']}  ->  {h['donde']}")
    elif hechos and not simular:
        for n in sorted({h["nombre"] for h in hechos} & set(nuevas)):
            print(f"[skills] enlace una skill nueva: {n}")
    for c in plan["choques"]:
        print(f"[skills] OJO: '{c['nombre']}' existe como carpeta real en dos lados y "
              f"no se cual manda. No toque ninguna:")
        for r in c["rutas"]:
            print("   ", r)
    for nombre, motivo in fallados:
        print(f"[skills] no pude enlazar {nombre}: {motivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
