"""El rastro: ver lo que la sesion HACE mientras trabaja, no solo lo que contesta.

Pedido de Martin (2026-08-28): "me gustaria ir viendo como razona". El PENSAMIENTO no se
puede mostrar y no es que lo filtremos — Claude Code lo tapa en las dos puntas: en el
`.jsonl` el bloque `thinking` queda con cero letras y solo su firma, y por el chorro en
vivo llega igual de vacio (probado forzando esfuerzo alto). Lo que si se puede es cada
herramienta contada en criollo, un renglon por paso.

    python -m pruebas.probar_rastro_pasos
    python -m pruebas.probar_rastro_pasos --mutar

No gasta tokens, no abre nada: arma un `.jsonl` de mentira y mira que sale.

⚠⚠ La trampa de este cambio es el RECORTE. Un solo turno puede usar sesenta herramientas,
asi que si el tope de la pantalla cuenta los pasos, la conversacion —lo unico que uno
viene a leer— se cae por arriba. Por eso se cuenta lo hablado y los pasos viajan de
arriba, y por eso ese es el chequeo mas importante de acá.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.voz import sesiones_movil as sm


def linea_asistente(bloques):
    return json.dumps({"type": "assistant", "timestamp": "2026-08-28T12:00:00.000Z",
                       "message": {"role": "assistant", "content": bloques}})


def linea_usuario(texto):
    return json.dumps({"type": "user", "timestamp": "2026-08-28T12:00:00.000Z",
                       "message": {"role": "user", "content": texto}})


def correr(callar=False):
    r = {}

    def chequear(titulo, condicion, detalle=""):
        r[titulo] = bool(condicion)
        if not callar:
            print(f"  ok   {titulo}" if condicion
                  else f"  MAL  {titulo}" + (f" -> {detalle}" if detalle else ""))

    CH = sm.CHROME_PREFIJO
    if not callar:
        print("\nCada herramienta, contada en criollo")
    casos = [
        (CH + "navigate", {"url": "http://localhost:8750/pizarra"}, "entró a http://localhost:8750/pizarra"),
        (CH + "computer", {"action": "left_click", "coordinate": [1, 2]}, "hizo clic"),
        (CH + "computer", {"action": "type", "text": "REGUERA"}, "escribió «REGUERA»"),
        (CH + "computer", {"action": "screenshot"}, "miró la pantalla"),
        (CH + "read_page", {}, "leyó la página"),
        (CH + "read_console_messages", {}, "leyó la consola"),
        (CH + "browser_batch", {"actions": [1, 2, 3]}, "hizo 3 pasos seguidos en el navegador"),
        ("Bash", {"command": "python -m pruebas.probar_no_romper"},
         "corrió: python -m pruebas.probar_no_romper"),
        ("Read", {"file_path": r"D:\IA\wpp-transcriptor\panel.py"}, "leyó panel.py"),
        ("Edit", {"file_path": r"D:\IA\x\voz.py"}, "escribió en voz.py"),
        ("Grep", {"pattern": "navegador"}, "buscó «navegador»"),
    ]
    for nombre, entrada, esperado in casos:
        chequear(f"{nombre.replace(CH, 'navegador: '):<26} -> {esperado}",
                 sm._paso_de(nombre, entrada) == esperado, sm._paso_de(nombre, entrada))
    chequear("la lista de tareas NO se repite como paso (ya es una tarjeta)",
             sm._paso_de("TodoWrite", {"todos": []}) == "")
    chequear("la pregunta con botones tampoco",
             sm._paso_de("AskUserQuestion", {"questions": []}) == "")
    chequear("una herramienta desconocida igual se muestra, con su nombre",
             sm._paso_de("HerramientaRara", {}) == "HerramientaRara")
    chequear("un comando larguísimo se recorta",
             len(sm._paso_de("Bash", {"command": "x" * 500})) < 120)

    if not callar:
        print("\nDel archivo al hilo")
    tmp = Path(tempfile.mkdtemp(prefix="rastro_")) / "s.jsonl"
    tmp.write_text("\n".join([
        linea_usuario("probá la pizarra"),
        linea_asistente([{"type": "thinking", "thinking": "", "signature": "xxx"},
                         {"type": "tool_use", "name": CH + "navigate",
                          "input": {"url": "http://localhost:8750"}}]),
        linea_asistente([{"type": "tool_use", "name": CH + "computer",
                          "input": {"action": "screenshot"}}]),
        linea_asistente([{"type": "text", "text": "Cargó bien, sin errores."}]),
    ]), encoding="utf-8")
    filas = sm._filas_de(tmp)
    tipos = [f["de"] for f in filas]
    chequear("aparecen los pasos, en orden, entre lo dicho",
             tipos == ["vos", "paso", "paso", "claude"], tipos)
    chequear("el paso dice a dónde entró",
             filas[1]["texto"].startswith("entró a http://localhost:8750"), filas[1]["texto"])
    chequear("el pensamiento vacío no ensucia el hilo",
             not any("thinking" in f["texto"] for f in filas))

    if not callar:
        print("\n⚠ El recorte cuenta lo HABLADO, no los pasos")
    muchas = ([{"de": "vos", "texto": "hola", "h": ""}]
              + [{"de": "paso", "texto": f"paso {i}", "h": ""} for i in range(60)]
              + [{"de": "claude", "texto": "listo", "h": ""}])
    corto = sm._ultimos_mensajes(muchas, 40)
    chequear("con 60 pasos y 2 mensajes, no se cae ninguno de los mensajes",
             sum(1 for f in corto if f["de"] != "paso") == 2,
             sum(1 for f in corto if f["de"] != "paso"))
    chequear("y los pasos viajan con ellos", sum(1 for f in corto if f["de"] == "paso") == 60)
    largo = ([{"de": "vos", "texto": f"m{i}", "h": ""} for i in range(50)])
    chequear("una charla larga sí se recorta a lo pedido",
             len(sm._ultimos_mensajes(largo, 40)) == 40,
             len(sm._ultimos_mensajes(largo, 40)))
    chequear("y deja las ÚLTIMAS, no las primeras",
             sm._ultimos_mensajes(largo, 40)[-1]["texto"] == "m49")
    return r


MUTACIONES = [
    ("el recorte vuelve a contar los pasos",
     lambda: setattr(sm, "_ultimos_mensajes", lambda filas, n: filas[-n:]),
     ["con 60 pasos y 2 mensajes, no se cae ninguno de los mensajes"]),
    ("los pasos del navegador dejan de contarse",
     lambda: setattr(sm, "_paso_de", lambda nombre, entrada: ""),
     ["aparecen los pasos, en orden, entre lo dicho", "el paso dice a dónde entró"]),
]


def mutar():
    print("\nProbando la prueba: se rompe cada regla a proposito\n")
    bien = mal = 0
    for nombre, romper, deben_fallar in MUTACIONES:
        guardado = {n: getattr(sm, n) for n in ("_ultimos_mensajes", "_paso_de")}
        try:
            romper()
            sm._HILOS.clear()          # el hilo esta cacheado por archivo: se vacia
            r = correr(callar=True)
            cayo = [t for t in deben_fallar if not r.get(t, True)]
        finally:
            for n, v in guardado.items():
                setattr(sm, n, v)
            sm._HILOS.clear()
        falta = [t for t in deben_fallar if t not in cayo]
        if falta:
            mal += 1
            print(f"  MAL  {nombre}")
            for t in falta:
                print(f"       el chequeo '{t}' siguio en verde con el defecto puesto")
        else:
            bien += 1
            print(f"  ok   {nombre} -> la cazan {len(cayo)} chequeos")
    print(f"\n{'LA PRUEBA SIRVE' if mal == 0 else 'HAY CHEQUEOS DE ADORNO'} — "
          f"{bien} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


def main():
    if "--mutar" in sys.argv:
        return mutar()
    r = correr()
    mal = sum(1 for v in r.values() if not v)
    print(f"\n{'TODO BIEN' if mal == 0 else 'HAY PROBLEMAS'} — "
          f"{len(r) - mal} bien, {mal} mal\n")
    return 0 if mal == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
