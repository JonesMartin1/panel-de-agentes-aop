"""El hilo de una charla se lee entero UNA vez y despues solo lo nuevo.

Pedido de Martin (2026-11-10): "que quede mas fluido que nunca" con muchas sesiones
abiertas. Lo medido ese dia: cada pedido de la pantalla (uno cada 3 s) releia el archivo
ENTERO de la conversacion si la charla estaba trabajando — 6 segundos en una de 115 MB —
y mientras tanto se frenaba el panel completo. Ahora `_filas_de` recuerda hasta donde
leyo cada archivo (`_HILOS` en `app/voz/sesiones_movil.py`).

    python -m pruebas.probar_hilo_incremental
    python -m pruebas.probar_hilo_incremental --mutar
    python -m pruebas.probar_hilo_incremental --a-fondo     (suma las charlas grandes)

No gasta tokens ni toca servicios. Arma charlas de mentira en una carpeta temporal y,
si en esta maquina hay charlas de verdad, las LEE (nunca las escribe) para comparar.

⚠⚠ La trampa de este cambio es que leer de a poco dé ALGO DISTINTO que leer de una: el
hilo se arma juntando pasos repetidos ("miró la pantalla ×4") y agrupando el navegador,
y esas dos cosas escriben arriba de las filas que reciben. Por eso el chequeo que manda
es el que alimenta el archivo de a pedazos —cortando por la mitad de un renglon— y
despues de CADA pedazo compara contra leerlo entero de cero. Y el que compara contra el
codigo viejo de git, fila por fila, sobre charlas reales.

⚠ Los chequeos de "no relee" CUENTAN renglones leidos, no miden tiempo: un chequeo por
reloj da verde o rojo segun como este de cargada la maquina ese dia.
"""
import json
import random
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.voz import sesiones_movil as sm

HORA = "2026-11-10T08:00:00.000Z"
CH = sm.CHROME_PREFIJO
# ⚠ El tope se anota ACA, antes de cualquier mutacion, y los bucles usan esta copia. La
# primera version recorria `range(sm.HILOS_MAX + 15)`: con la mutacion que pone el tope
# en mil millones, la prueba se ponia a crear mil millones de archivos y no terminaba.
TOPE = sm.HILOS_MAX


def asistente(bloques, uuid="u-1"):
    return json.dumps({"type": "assistant", "timestamp": HORA, "uuid": uuid,
                       "message": {"role": "assistant", "content": bloques}})


def usuario(contenido):
    return json.dumps({"type": "user", "timestamp": HORA,
                       "message": {"role": "user", "content": contenido}})


def uso(i, nombre, entrada):
    return asistente([{"type": "tool_use", "id": i, "name": nombre, "input": entrada}],
                     uuid="u-" + i)


def resultado(i, error=False, foto=False):
    cont = [{"type": "text", "text": "listo"}]
    if foto:
        cont.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": "QUJD" * 4000}})
    return usuario([{"type": "tool_result", "tool_use_id": i, "content": cont,
                     "is_error": error}])


def charla_de_mentira():
    """Una charla con todo lo que el hilo sabe dibujar. Devuelve sus renglones."""
    mandada = r"C:\tmp\imagenes\foto_que_mande.png"
    r = [usuario("hola, revisame la pagina"),
         asistente([{"type": "text", "text": "Dale, la abro."}], "u-a1")]
    # Tres comandos IGUALES seguidos: en el hilo son UN renglon con "×3".
    for n in range(3):
        r += [uso(f"t-b{n}", "Bash", {"command": "git status"}), resultado(f"t-b{n}")]
    # Una tanda del navegador con fotos: se agrupa en un renglon plegable.
    r += [uso("t-n1", CH + "navigate", {"url": "https://ejemplo.com/pagina"}), resultado("t-n1"),
          uso("t-n2", CH + "computer", {"action": "screenshot"}), resultado("t-n2", foto=True),
          uso("t-n3", CH + "computer", {"action": "left_click"}), resultado("t-n3", error=True),
          asistente([{"type": "text", "text": "Cargó bien."}], "u-a2"),
          # La foto que mando Martin: la sesion la abre con Read y NO se repite en el hilo.
          usuario(f"[Te paso una imagen; está guardada en {mandada}] mirá esto"),
          uso("t-r1", "Read", {"file_path": mandada.replace("\\", "/")}),
          resultado("t-r1", foto=True),
          # Una captura que saco la sesion: esa SI se ve.
          uso("t-r2", "Read", {"file_path": r"C:\tmp\captura.png"}), resultado("t-r2", foto=True),
          # Un mensaje que escribiste mientras trabajaba.
          json.dumps({"type": "attachment", "timestamp": HORA,
                      "attachment": {"type": "queued_command", "prompt": "y fijate el pie"}}),
          # Renglones que no son nada: el hilo los tiene que pasar de largo.
          json.dumps({"type": "last-prompt", "timestamp": HORA}), "esto no es json", "[1, 2]",
          asistente([{"type": "text", "text": "Listo, **todo** revisado."}], "u-a3")]
    for n in range(4):
        r += [uso(f"t-c{n}", "Grep", {"pattern": "pie"}), resultado(f"t-c{n}")]
    return r


def de_cero(ruta):
    """Lo que da leer ese archivo entero, sin nada recordado."""
    sm._HILOS.pop(str(ruta), None)
    return sm._filas_de(ruta)


def renglones_leidos(funcion):
    """Cuantos renglones del disco hizo falta leer para correr `funcion`."""
    cuenta, original = [0], sm._lineas_desde

    def espia(jsonl, marca):
        for linea in original(jsonl, marca):
            cuenta[0] += 1
            yield linea

    sm._lineas_desde = espia
    try:
        funcion()
    finally:
        sm._lineas_desde = original
    return cuenta[0]


def modulo_viejo():
    """El `sesiones_movil.py` de ANTES del cambio, sacado de git y cargado aparte.

    Devuelve (modulo, de donde salio) o (None, por que no). Si el cambio ya esta
    commiteado busca el commit que lo trajo y toma el anterior.
    """
    ruta = "app/voz/sesiones_movil.py"

    def git(*a):
        return subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, check=True) \
            .stdout.decode("utf-8", errors="replace")
    try:
        ref = "HEAD"
        fuente = git("show", f"{ref}:{ruta}")
        if "class _HiloLeido" in fuente:
            trajo = git("log", "--format=%H", "--reverse", "-Sclass _HiloLeido", "--", ruta).split()
            if not trajo:
                return None, "git no tiene una version anterior al cambio"
            ref = trajo[0] + "~1"
            fuente = git("show", f"{ref}:{ruta}")
            if "class _HiloLeido" in fuente:
                return None, "no encontre en git la version anterior al cambio"
        m = types.ModuleType("sesiones_movil_viejo")
        m.__file__ = sm.__file__
        exec(compile(fuente, "sesiones_movil_viejo", "exec"), m.__dict__)
        return m, ref
    except Exception as e:
        return None, f"no pude cargar la version de git ({type(e).__name__})"


def charlas_reales(a_fondo):
    """Charlas de verdad de esta maquina para comparar. Solo se leen."""
    try:
        todas = [(f, f.stat()) for f in sm.CLAUDE_PROYECTOS.glob("*/*.jsonl")]
    except OSError:
        return []
    import time
    quietas = [(f, e) for f, e in todas if time.time() - e.st_mtime > 300 and e.st_size > 2000]
    quietas.sort(key=lambda fe: -fe[1].st_mtime)
    tope = 200_000_000 if a_fondo else 12_000_000
    elegidas = [f for f, e in quietas if e.st_size <= tope][:60 if a_fondo else 25]
    if a_fondo:
        elegidas += [f for f, _ in sorted(quietas, key=lambda fe: -fe[1].st_size)[:4]
                     if f not in elegidas]
    return elegidas


def correr(callar=False, a_fondo=False, liviano=False):
    """`liviano` es para `--mutar`: con un defecto puesto a proposito el hilo puede crecer
    sin freno (el que "se olvida hasta donde leyo" suma la charla entera en cada pedido),
    asi que ahi no se corren ni los seis lectores a la vez ni las charlas reales. La
    primera version de esta prueba no tenia este freno y se comio 600 MB en una corrida."""
    r = {}

    def chequear(titulo, condicion, detalle=""):
        r[titulo] = bool(condicion)
        if not callar:
            print(f"  ok   {titulo}" if condicion
                  else f"  MAL  {titulo}" + (f" -> {detalle}" if detalle else ""))

    def titulo(t):
        if not callar:
            print("\n" + t)

    renglones = charla_de_mentira()
    with tempfile.TemporaryDirectory(prefix="hilo_inc_") as carpeta:
        carpeta = Path(carpeta)
        sm._HILOS.clear()

        # --- 1. Leer de a pedazos da lo mismo que leer de una -------------------------
        titulo("Leer de a poco da EXACTAMENTE lo mismo que leer de una")
        entero = ("\n".join(renglones) + "\n").encode("utf-8")
        azar = random.Random(20261110)
        peor = ""
        for vuelta in range(1 if liviano else 6):
            poco, ref = carpeta / f"poco{vuelta}.jsonl", carpeta / f"ref{vuelta}.jsonl"
            poco.write_bytes(b"")
            escrito = 0
            while escrito < len(entero) and not peor:
                # Pedazos de cualquier tamaño: muchos cortan un renglon por la mitad.
                escrito = min(len(entero), escrito + azar.randint(1, 9000))
                with open(poco, "ab") as f:
                    f.write(entero[len(poco.read_bytes()):escrito])
                ref.write_bytes(entero[:escrito])
                if sm._filas_de(poco) != de_cero(ref):
                    peor = f"vuelta {vuelta}, a los {escrito} bytes"
        chequear("alimentando el archivo de a pedazos (cortando renglones al medio), el hilo "
                 "coincide con leerlo entero despues de CADA pedazo", not peor, peor)

        charla = carpeta / "charla.jsonl"
        charla.write_bytes(entero)
        filas = sm._filas_de(charla)
        textos = [f["texto"] for f in filas]
        chequear("tres comandos iguales seguidos son UN renglon con ×3",
                 "corrió: git status ×3" in textos, str(textos[:6]))
        for _ in range(3):                      # releer no puede volver a contarlos
            with open(charla, "ab") as f:
                f.write((asistente([{"type": "text", "text": "sigo"}], "u-x") + "\n").encode())
            filas = sm._filas_de(charla)
        textos = [f["texto"] for f in filas]
        chequear("despues de tres lecturas mas sigue diciendo ×3 (no ×6 ni ×9)",
                 "corrió: git status ×3" in textos and not any("×6" in t or "×9" in t for t in textos),
                 str([t for t in textos if "×" in t]))
        nav = [f for f in filas if f.get("grupo")]
        chequear("la tanda del navegador sigue siendo un solo renglon con su foto",
                 len(nav) == 1 and nav[0].get("foto") == "t-n2" and "1 falló" in nav[0]["texto"],
                 str([(f["texto"], f.get("foto")) for f in nav]))

        # --- 2. No se relee lo ya leido ------------------------------------------------
        titulo("Lo ya leido no se vuelve a leer")
        n = renglones_leidos(lambda: sm._filas_de(charla))
        chequear("sin cambios en el archivo, pedir el hilo no lee NINGUN renglon", n == 0, f"leyo {n}")
        with open(charla, "ab") as f:
            f.write((asistente([{"type": "text", "text": "una mas"}], "u-y") + "\n").encode())
        n = renglones_leidos(lambda: sm._filas_de(charla))
        chequear("al agregarle UNA linea se lee UN renglon, no la charla entera", n == 1, f"leyo {n}")
        chequear("y esa linea ya esta en el hilo", sm._filas_de(charla)[-1]["texto"] == "una mas")

        # --- 3. El ultimo renglon, a medio escribir ------------------------------------
        titulo("Un renglon que Claude Code todavia esta escribiendo")
        antes = sm._filas_de(charla)
        nuevo = asistente([{"type": "text", "text": "llegó entero"}], "u-z").encode()
        with open(charla, "ab") as f:
            f.write(nuevo[:40])                 # la mitad, sin salto de linea
        chequear("un renglon por la mitad no cambia el hilo", sm._filas_de(charla) == antes)
        with open(charla, "ab") as f:
            f.write(nuevo[40:])                 # ya esta entero, todavia SIN salto
        f1 = sm._filas_de(charla)
        chequear("cuando se completa aparece, aunque le falte el salto de linea",
                 f1[-1]["texto"] == "llegó entero", f1[-1]["texto"][:40])
        with open(charla, "ab") as f:
            f.write(("\n" + asistente([{"type": "text", "text": "y otro"}], "u-w") + "\n").encode())
        f2 = sm._filas_de(charla)
        chequear("y cuando llega el salto y el renglon siguiente no se repite ninguno",
                 [x["texto"] for x in f2[-2:]] == ["llegó entero", "y otro"] and f2 == de_cero(charla),
                 str([x["texto"] for x in f2[-3:]]))

        # --- 4. El archivo ya no es el mismo -------------------------------------------
        titulo("Si reescriben el archivo, se lee de cero")
        sm._filas_de(charla)
        otra = "\n".join([usuario("otra charla distinta, mas corta"),
                          asistente([{"type": "text", "text": "si"}], "u-o")]) + "\n"
        charla.write_text(otra, encoding="utf-8")
        chequear("un archivo que se achico no arrastra nada de la charla anterior",
                 [x["texto"] for x in sm._filas_de(charla)] == ["otra charla distinta, mas corta", "si"])
        # Mismo largo o mas, pero con otro contenido donde ya se habia leido.
        base = sm._filas_de(charla)
        relleno = otra.replace("distinta", "DISTINTA") + \
            asistente([{"type": "text", "text": "y esto es nuevo"}], "u-p") + "\n"
        charla.write_text(relleno, encoding="utf-8")
        f3 = sm._filas_de(charla)
        chequear("un archivo MAS LARGO pero con lo de antes cambiado tambien se lee de cero",
                 f3 == de_cero(charla) and f3[0]["texto"] != base[0]["texto"], f3[0]["texto"])

        # --- 5. Lo que hace la pantalla con las filas no ensucia lo guardado -----------
        titulo("Lo que devuelve se puede tocar sin romper la proxima lectura")
        f4 = sm._filas_de(charla)
        for fila in f4:                         # como hace /movil/chat con las fotos
            fila["texto"] = "PISADO"
            fila["imgs"] = ["/x"]
        with open(charla, "ab") as f:
            f.write((asistente([{"type": "text", "text": "despues de pisar"}], "u-q") + "\n").encode())
        f5 = sm._filas_de(charla)
        chequear("pisar las filas devueltas no cambia lo que sale en la lectura siguiente",
                 f5 == de_cero(charla) and all(x["texto"] != "PISADO" for x in f5))

        # --- 6. Un tropiezo del disco no tira lo leido ---------------------------------
        titulo("Si el disco falla un momento (antivirus, archivo tomado)")
        bueno = sm._filas_de(charla)
        with open(charla, "ab") as f:
            f.write((asistente([{"type": "text", "text": "tras el tropiezo"}], "u-t") + "\n").encode())
        fallar = [True]

        def abrir(ruta, *a, **k):
            if fallar[0] and str(ruta) == str(charla):
                raise PermissionError("archivo tomado")
            return open(ruta, *a, **k)

        sm.open = abrir
        try:
            con_falla = sm._filas_de(charla)
            fallar[0] = False
            n = renglones_leidos(lambda: sm._filas_de(charla))
        finally:
            del sm.open
        chequear("mientras falla contesta lo que ya tenia (ni error ni charla vacia)",
                 con_falla == bueno, f"{len(con_falla)} filas contra {len(bueno)}")
        chequear("y al volver sigue desde donde estaba: lee UN renglon, no todo de nuevo",
                 n == 1 and sm._filas_de(charla)[-1]["texto"] == "tras el tropiezo", f"leyo {n}")

        # --- 7. Muchos pedidos a la vez ------------------------------------------------
        titulo("Varios pedidos al mismo tiempo sobre la misma charla")
        viva = carpeta / "viva.jsonl"
        viva.write_bytes(entero)
        errores, seguir_ = [], [True]

        def lector():
            vueltas = 0
            while seguir_[0] and vueltas < 400:     # con tope: nunca un bucle sin fin
                vueltas += 1
                try:
                    sm._filas_de(viva)
                except Exception as e:      # noqa: BLE001 — se junta para mostrarlo
                    errores.append(repr(e))
                    return

        if not liviano:
            hilos = [threading.Thread(target=lector) for _ in range(6)]
            for t in hilos:
                t.start()
            for i in range(60):
                with open(viva, "ab") as f:
                    f.write((uso(f"t-v{i}", "Bash", {"command": f"echo {i % 3}"}) + "\n" +
                             resultado(f"t-v{i}") + "\n").encode())
            seguir_[0] = False
            for t in hilos:
                t.join()
            chequear("seis lectores y uno que escribe: ningun error y nada repetido ni perdido",
                     not errores and sm._filas_de(viva) == de_cero(viva), str(errores[:1]))

        # --- 8. La memoria tiene techo -------------------------------------------------
        titulo("Lo recordado tiene tope")
        sm._HILOS.clear()
        for i in range(TOPE + 15):
            f = carpeta / f"m{i}.jsonl"
            f.write_text(usuario(f"charla {i}") + "\n", encoding="utf-8")
            sm._filas_de(f)
        sm._filas_de(carpeta / "m20.jsonl")      # se vuelve a mirar: pasa a ser la mas nueva
        for i in range(TOPE + 15, TOPE + 20):
            f = carpeta / f"m{i}.jsonl"
            f.write_text(usuario(f"charla {i}") + "\n", encoding="utf-8")
            sm._filas_de(f)
        chequear(f"nunca se recuerdan mas de {TOPE} charlas a la vez",
                 len(sm._HILOS) <= TOPE, str(len(sm._HILOS)))
        chequear("y la que se olvida es la que hace mas que no se mira, no una recien usada",
                 str(carpeta / "m20.jsonl") in sm._HILOS and str(carpeta / "m16.jsonl") not in sm._HILOS)

    # --- 9. Contra el codigo viejo, sobre charlas reales -------------------------------
    titulo("Contra el codigo de antes (git), sobre charlas de verdad de esta maquina")
    if liviano:
        sm._HILOS.clear()
        return r
    viejo, de_donde = modulo_viejo()
    reales = charlas_reales(a_fondo)
    if viejo is None or not reales:
        if not callar:
            print(f"  --   no se compara: {de_donde if viejo is None else 'no hay charlas guardadas'}")
    else:
        distintas, comparadas, megas = [], 0, 0
        for f in reales:
            try:
                e0 = f.stat()
                esperado = viejo._filas_de(f)
                sm._HILOS.pop(str(f), None)
                obtenido = sm._filas_de(f)
                e1 = f.stat()
            except Exception as e:      # noqa: BLE001
                distintas.append(f"{f.stem[:8]} revento: {type(e).__name__}: {e}")
                continue
            if (e0.st_mtime, e0.st_size) != (e1.st_mtime, e1.st_size):
                continue                # cambio mientras se leia: no es una comparacion valida
            comparadas += 1
            megas += e0.st_size / 1e6
            if esperado != obtenido:
                i = next((k for k, (a, b) in enumerate(zip(esperado, obtenido)) if a != b),
                         min(len(esperado), len(obtenido)))
                distintas.append(f"{f.stem[:8]}: {len(esperado)} filas contra {len(obtenido)}, "
                                 f"la primera distinta es la {i}")
        chequear(f"el hilo sale identico al del codigo viejo ({de_donde}) en {comparadas} "
                 f"charlas reales, {megas:.0f} MB", comparadas > 0 and not distintas,
                 "; ".join(distintas[:3]) or "no quedo ninguna para comparar")
    sm._HILOS.clear()
    return r


# Cada defecto puesto a proposito, y los chequeos que lo tienen que cazar.
def _sin_copiar(h):
    return sm._agrupar_navegador(sm._juntar_pasos(h.crudas, h.resultados),
                                 h.fotos - sm._fotos_que_mando(h.dicho, h.leidas))


def _olvida_donde_iba():
    original = sm._lineas_desde

    def desde_el_principio(jsonl, marca):
        marca[0] = 0
        return original(jsonl, marca)
    sm._lineas_desde = desde_el_principio


MUTACIONES = [
    ("el hilo se arma sobre las filas guardadas, sin copiarlas",
     lambda: setattr(sm, "_hilo_terminado", _sin_copiar),
     ["despues de tres lecturas mas sigue diciendo ×3 (no ×6 ni ×9)"]),
    ("se olvida hasta donde habia leido y suma todo de nuevo",
     _olvida_donde_iba,
     ["al agregarle UNA linea se lee UN renglon, no la charla entera"]),
    ("vuelve a leer la charla entera en cada pedido",
     lambda: setattr(sm, "_mismo_archivo", lambda h, j, t: False),
     ["al agregarle UNA linea se lee UN renglon, no la charla entera"]),
    ("no se da cuenta de que el archivo es otro",
     lambda: setattr(sm, "_mismo_archivo", lambda h, j, t: True),
     ["un archivo MAS LARGO pero con lo de antes cambiado tambien se lee de cero"]),
    ("se traga un renglon a medio escribir",
     lambda: setattr(sm, "_objeto_entero", lambda cruda: True),
     ["cuando se completa aparece, aunque le falte el salto de linea"]),
    ("lo recordado no tiene tope",
     lambda: setattr(sm, "HILOS_MAX", 10 ** 9),
     ["y la que se olvida es la que hace mas que no se mira, no una recien usada"]),
]


def mutar():
    print("\nProbando la prueba: se rompe cada regla a proposito\n")
    nombres = ("_hilo_terminado", "_lineas_desde", "_mismo_archivo", "_objeto_entero",
               "HILOS_MAX")
    bien = mal = 0
    for nombre, romper, deben_fallar in MUTACIONES:
        guardado = {n: getattr(sm, n) for n in nombres}
        try:
            romper()
            sm._HILOS.clear()
            try:
                res = correr(callar=True, liviano=True)
            except Exception:           # noqa: BLE001 — reventar tambien es cazarlo
                res = {}
            cayo = [t for t in deben_fallar if not res.get(t, False)]
        finally:
            for n, v in guardado.items():
                setattr(sm, n, v)
            sm._HILOS.clear()
        if len(cayo) < len(deben_fallar):
            mal += 1
            print(f"  MAL  {nombre}")
            for t in deben_fallar:
                if t not in cayo:
                    print(f"       el chequeo '{t}' siguio en verde con el defecto puesto")
        else:
            bien += 1
            print(f"  ok   {nombre} -> lo caza: {cayo[0]}")
    print(f"\n{'LA PRUEBA SIRVE' if mal == 0 else 'HAY CHEQUEOS DE ADORNO'} — "
          f"{bien} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


def main():
    if "--mutar" in sys.argv:
        return mutar()
    r = correr(a_fondo="--a-fondo" in sys.argv)
    mal = sum(1 for v in r.values() if not v)
    print(f"\n{'TODO BIEN' if mal == 0 else 'HAY PROBLEMAS'} — "
          f"{len(r) - mal} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
