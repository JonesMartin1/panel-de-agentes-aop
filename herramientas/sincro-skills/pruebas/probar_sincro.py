"""Prueba del enlazador de skills. No toca NINGUNA carpeta real.

Arma tres carpetas de mentira, apunta el modulo ahi y verifica lo que tiene que pasar.
Es barata (no usa red ni GPU) y corre en menos de un segundo.

⭐ Con `--mutar` rompe cada regla a proposito, UNA POR VEZ y con el escenario limpio, y
exige que se note. Un chequeo que no puede fallar es un adorno.

⚠ La primera version de esta prueba tenia justo ese problema: el chequeo de la
cuarentena pasaba porque esa carpeta ni siquiera se escanea, no porque el freno
funcionara. Verde por el motivo equivocado. Por eso ahora cada defecto se prueba
aparte y con una consecuencia concreta.

Los dos defectos que ya salvaron el proyecto de verdad:

- **el prefijo `\\?\\`**: `os.readlink` lo devuelve y `Path.resolve()` NO lo saca, asi
  que comparando sin limpiar cada enlace correcto parecia apuntar a otro lado y el
  script los borraba y rehacia TODOS en cada corrida — o sea en cada mensaje;
- **razonar por carpetas en vez de por lectores**: hay tres carpetas pero dos cerebros,
  y Codex lee dos de ellas. Contando carpetas sobraban enlaces que le mostraban la
  misma skill dos veces.

Correr con:  python pruebas/probar_sincro.py
             python pruebas/probar_sincro.py --mutar
"""

import io
import sys
import contextlib
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sincro                                                       # noqa: E402

OK = MAL = 0


def chequear(nombre, cond):
    global OK, MAL
    print(("  ok   " if cond else "  MAL  ") + nombre)
    if cond:
        OK += 1
    else:
        MAL += 1
    return cond


def skill(carpeta, nombre, texto="hola"):
    d = carpeta / nombre
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {nombre}\n---\n{texto}", encoding="utf-8")
    return d


def apuntar(tmp):
    """Manda el modulo a las carpetas de mentira. Devuelve (claude, codex, agents)."""
    c, x, a = tmp / "claude", tmp / "codex", tmp / "agents"
    for p in (c, x, a):
        p.mkdir(parents=True, exist_ok=True)
    sincro.CLAUDE_SKILLS, sincro.CODEX_SKILLS, sincro.AGENTS_SKILLS = c, x, a
    sincro.RAICES = [c, x, a]
    sincro.LECTORES = [
        {"nombre": "Claude", "lee": [c], "pone_en": c},
        {"nombre": "Codex", "lee": [x, a], "pone_en": x},
    ]
    sincro.CUARENTENA = tmp / "cuarentena"
    sincro.CONOCIDAS = tmp / "conocidas.json"
    return c, x, a


def correr(*args):
    """Corre el script y devuelve lo que imprimio."""
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        sincro.main(list(args))
    return salida.getvalue()


def normal():
    """Todo lo que tiene que pasar cuando el script esta sano."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        claude, codex, agents = apuntar(tmp)

        skill(claude, "pizarra")                    # nace del lado de Claude
        skill(codex, "tresde")                      # nace del lado de Codex
        skill(agents, "prompt-master")              # vive en la ruta nueva de Codex
        skill(codex / ".system", "imagegen")        # de fabrica: no es de Martin
        skill(claude / "synced", "bajada-de-la-web")
        skill(tmp / "cuarentena", "recien-bajada")
        (claude / "_molde.md").write_text("no soy una skill", encoding="utf-8")

        print("--- primera corrida ---")
        salida = correr()
        chequear("siembra en silencio (no anuncia las 16 de golpe)",
                 "skill nueva" not in salida)
        chequear("Claude ve la que nacio en Codex",
                 sincro.es_enlace(claude / "tresde") is not None)
        chequear("Codex ve la que nacio en Claude",
                 sincro.es_enlace(codex / "pizarra") is not None)
        chequear("y los enlaces se leen de verdad",
                 (claude / "tresde" / "SKILL.md").exists())
        chequear("NO le duplica a Codex la que ya lee de .agents",
                 not (codex / "prompt-master").exists())
        chequear("pero Claude si la recibe", (claude / "prompt-master").exists())
        chequear("no enlaza las de fabrica (.system)",
                 not (claude / "imagegen").exists())
        chequear("no enlaza la carpeta reservada synced",
                 not (codex / "bajada-de-la-web").exists()
                 and not (codex / "synced").exists())
        chequear("no confunde un .md suelto con una skill",
                 not (codex / "_molde.md").exists())
        chequear("nunca enlaza una carpeta raiz",
                 sincro.es_enlace(claude) is None and sincro.es_enlace(codex) is None)

        # ⭐ El freno de la cuarentena, probado DIRECTO. No alcanza con ver que no
        # aparece: no aparece porque esa carpeta no se escanea. Lo que hay que probar
        # es que si un item de cuarentena llegara al plan, `aplicar` lo rechaza.
        plan_falso = {"crear": [{"nombre": "recien-bajada", "rehacer": False,
                                 "origen": str(tmp / "cuarentena" / "recien-bajada"),
                                 "donde": str(claude / "recien-bajada")}],
                      "choques": [], "vistas": []}
        hechos, fallados = sincro.aplicar(plan_falso)
        chequear("el freno de la cuarentena rechaza el enlace",
                 hechos == [] and len(fallados) == 1
                 and "cuarentena" in fallados[0][1])
        chequear("y no quedo nada creado",
                 not (claude / "recien-bajada").exists())

        print("\n--- segunda corrida: idempotente y callada ---")
        antes = sorted(p.name for r in (claude, codex) for p in r.iterdir())
        salida2 = correr()
        despues = sorted(p.name for r in (claude, codex) for p in r.iterdir())
        chequear("no cambia nada", antes == despues)
        chequear("y no imprime NADA (esto se inyecta en cada mensaje)",
                 salida2.strip() == "")

        print("\n--- una skill nueva: se enlaza y se anuncia UNA vez ---")
        skill(codex, "recien-hecha")
        salida3 = correr()
        chequear("la enlaza", (claude / "recien-hecha").exists())
        chequear("y la anuncia", "recien-hecha" in salida3)
        chequear("la vez siguiente ya no la nombra",
                 "recien-hecha" not in correr())

        print("\n--- choque: el mismo nombre real de los dos lados ---")
        skill(claude, "chocan", "version de Claude")
        skill(codex, "chocan", "version de Codex")
        skill(claude, "otra-mas")
        salida5 = correr()
        chequear("avisa del choque", "chocan" in salida5 and "OJO" in salida5)
        chequear("no toca ninguna de las dos",
                 (claude / "chocan" / "SKILL.md").read_text(
                     encoding="utf-8").endswith("version de Claude")
                 and sincro.es_enlace(claude / "chocan") is None)
        chequear("y sigue con el resto igual", (codex / "otra-mas").exists())

        print("\n--- deshacer: saca enlaces, no carpetas reales ---")
        sacados = sincro.deshacer()
        chequear("saco varios enlaces", len(sacados) >= 3)
        chequear("las skills de verdad siguen enteras",
                 (claude / "pizarra" / "SKILL.md").exists()
                 and (codex / "tresde" / "SKILL.md").exists()
                 and (agents / "prompt-master" / "SKILL.md").exists())


# --- Los defectos, uno por vez y con el escenario limpio --------------------------

def _escenario(tmp):
    claude, codex, agents = apuntar(tmp)
    skill(claude, "pizarra")
    skill(codex, "tresde")
    skill(agents, "prompt-master")
    correr()                                  # deja todo sano y enlazado
    return claude, codex, agents


def d_prefijo(tmp, claude, codex, agents):
    """Comparar rutas sin sacar el `\\?\\` (lo que pasaba usando `Path.resolve()`)."""
    sincro._mismo = lambda a, b: str(a) == str(b)
    # Con el defecto, un enlace que YA estaba correcto vuelve a darse por hacer.
    return bool(sincro.revisar()["crear"])


def d_por_carpetas(tmp, claude, codex, agents):
    """Razonar por carpetas: cada raiz es su propio lector."""
    sincro.LECTORES = [{"nombre": n, "lee": [r], "pone_en": r} for n, r in
                       (("Claude", claude), ("Codex", codex), ("Agents", agents))]
    # Con el defecto, le quiere duplicar a Codex la que ya lee de .agents.
    return any(i["nombre"] == "prompt-master" and "codex" in i["donde"].lower()
               for i in sincro.revisar()["crear"])


def d_is_symlink(tmp, claude, codex, agents):
    """Detectar enlaces con `is_symlink()`, que con un junction contesta False."""
    sincro.es_enlace = lambda p: "algo" if Path(p).is_symlink() else None
    # Con el defecto, los enlaces se leen como carpetas reales: choque en todas.
    return len(sincro.revisar()["choques"]) > 0


def d_cuarentena(tmp, claude, codex, agents):
    """Sacarle el freno a la cuarentena."""
    sincro.CUARENTENA = Path("Z:/carpeta-que-no-existe")
    origen = tmp / "cuarentena" / "bajada"
    skill(tmp / "cuarentena", "bajada")
    plan = {"crear": [{"nombre": "bajada", "origen": str(origen), "rehacer": False,
                       "donde": str(claude / "bajada")}], "choques": [], "vistas": []}
    hechos, _ = sincro.aplicar(plan)
    return bool(hechos)                       # con el defecto SI la enlaza


def mutar():
    """Cada defecto, en su propio escenario. Devuelve cuantos se cazaron."""
    defectos = [
        ("compara rutas sin limpiar el prefijo \\\\?\\", d_prefijo),
        ("razona por carpetas en vez de por lectores", d_por_carpetas),
        ("detecta enlaces con is_symlink()", d_is_symlink),
        ("no frena lo que viene de la cuarentena", d_cuarentena),
    ]
    guardados = (sincro._mismo, sincro.es_enlace)
    cazados = 0
    for nombre, romper in defectos:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            claude, codex, agents = _escenario(tmp)
            se_nota = romper(tmp, claude, codex, agents)
        sincro._mismo, sincro.es_enlace = guardados
        print(("  ok   " if se_nota else "  MAL  ") + "se caza: " + nombre)
        cazados += 1 if se_nota else 0
    return cazados, len(defectos)


def main():
    if "--mutar" in sys.argv:
        print("--mutar: cada defecto en su propio escenario; todos tienen que notarse\n")
        cazados, total = mutar()
        print(f"\nse cazaron {cazados} de {total} defectos")
        if cazados < total:
            print("MAL: algun defecto pasa sin que nadie lo note. Ese chequeo no "
                  "prueba lo que dice.")
            return 1
        print("Bien: los cuatro se cazan.")
        return 0

    normal()
    print(f"\n{OK} ok, {MAL} mal")
    return 1 if MAL else 0


if __name__ == "__main__":
    sys.exit(main())
