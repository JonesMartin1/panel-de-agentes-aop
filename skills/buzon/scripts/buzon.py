#!/usr/bin/env python3
"""Buzon: canal por archivo entre Laura (asistente de voz) y las sesiones de Claude Code.

Un solo archivo global: ~/.claude/BUZON.md. Laura escribe, la sesion lee y responde.
Sin red, sin servicio corriendo: es un .md que las dos partes saben leer.
"""
import argparse
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BUZON = Path(os.environ.get("BUZON_PATH") or Path.home() / ".claude" / "BUZON.md")
CABECERA = re.compile(
    r"^## \[(?P<id>\d{4})\] (?P<ts>[\d\-: ]+) . DE (?P<de>[^·]+?) . PARA (?P<para>[^·]+?) . (?P<estado>PENDIENTE|HECHO)\s*$"
)
PLANTILLA = """# Buzon

Canal entre Laura (asistente de voz) y las sesiones de Claude Code.
Laura escribe con `buzon.py escribir`; la sesion responde con `buzon.py responder`.
No editar a mano salvo que haga falta: el formato de la cabecera es lo que se parsea.

"""


def _stdout_utf8():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    else:  # pragma: no cover
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _leer():
    if not BUZON.exists():
        return PLANTILLA
    return BUZON.read_text(encoding="utf-8")


def _entradas(texto):
    """Devuelve [(dict_cabecera, indice_linea_cabecera, [lineas_cuerpo])]."""
    lineas = texto.splitlines()
    out = []
    for i, ln in enumerate(lineas):
        m = CABECERA.match(ln)
        if not m:
            continue
        cuerpo = []
        for j in range(i + 1, len(lineas)):
            if CABECERA.match(lineas[j]):
                break
            cuerpo.append(lineas[j])
        d = {k: v.strip() for k, v in m.groupdict().items()}
        out.append((d, i, cuerpo))
    return out


def _proyecto_actual():
    return Path.cwd().name


def _aplica(entrada, proyecto):
    para = entrada["para"]
    return para == "*" or para.lower() == proyecto.lower()


def cmd_pendientes(args):
    proyecto = args.proyecto or _proyecto_actual()
    texto = _leer()
    pend = [
        (d, c) for d, _, c in _entradas(texto)
        if d["estado"] == "PENDIENTE" and _aplica(d, proyecto)
    ]
    if not pend:
        return 0
    print("BUZON - mensajes de Laura sin atender "
          "(respondelos con: python ~/.claude/skills/buzon/scripts/buzon.py responder <id> --texto \"...\")")
    for d, cuerpo in pend:
        cuerpo_txt = "\n".join(cuerpo).strip()
        print(f"\n  [{d['id']}] {d['ts']} - de {d['de']} - para {d['para']}")
        for ln in cuerpo_txt.splitlines():
            print(f"    {ln}")
    return 0


def cmd_ver(args):
    print(_leer().rstrip())
    return 0


def _proximo_id(texto):
    ids = [int(d["id"]) for d, _, _ in _entradas(texto)]
    return f"{(max(ids) + 1) if ids else 1:04d}"


def cmd_escribir(args):
    texto = args.texto if args.texto is not None else sys.stdin.read()
    texto = texto.strip()
    if not texto:
        print("nada que escribir (pasa --texto o mandalo por stdin)", file=sys.stderr)
        return 1
    actual = _leer()
    nid = _proximo_id(actual)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    bloque = f"\n## [{nid}] {ts} · DE {args.de} · PARA {args.para} · PENDIENTE\n{texto}\n"
    BUZON.parent.mkdir(parents=True, exist_ok=True)
    BUZON.write_text(actual.rstrip() + "\n" + bloque, encoding="utf-8")
    print(f"escrito [{nid}] para {args.para}")
    return 0


def _marcar(nid, respuesta=None):
    texto = _leer()
    lineas = texto.splitlines()
    encontrado = None
    for d, i, cuerpo in _entradas(texto):
        if d["id"] == nid:
            encontrado = (d, i, cuerpo)
            break
    if not encontrado:
        print(f"no existe la entrada [{nid}]", file=sys.stderr)
        return 1
    d, i, cuerpo = encontrado
    lineas[i] = lineas[i].rstrip()[: -len("PENDIENTE")] + "HECHO" if lineas[i].rstrip().endswith("PENDIENTE") else lineas[i]
    if respuesta:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        fin = i + 1 + len(cuerpo)
        cita = [f"> RESPUESTA ({ts}, {_proyecto_actual()}):"] + [f"> {l}" for l in respuesta.strip().splitlines()]
        lineas[fin:fin] = cita + [""]
    BUZON.write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
    print(f"[{nid}] marcada HECHO" + (" con respuesta" if respuesta else ""))
    return 0


def cmd_responder(args):
    texto = args.texto if args.texto is not None else sys.stdin.read()
    return _marcar(args.id, texto)


def cmd_hecho(args):
    return _marcar(args.id, None)


def main():
    _stdout_utf8()
    p = argparse.ArgumentParser(description="Buzon Laura <-> Claude Code")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("pendientes", help="lista lo que Laura dejo sin atender (lo usa el hook)")
    s.add_argument("--proyecto", default=None)
    s.set_defaults(func=cmd_pendientes)

    s = sub.add_parser("ver", help="muestra el buzon completo")
    s.set_defaults(func=cmd_ver)

    s = sub.add_parser("escribir", help="deja un mensaje (lo usa Laura)")
    s.add_argument("--de", default="Laura")
    s.add_argument("--para", default="*", help="nombre de carpeta del proyecto, o * para cualquiera")
    s.add_argument("--texto", default=None, help="si se omite, se lee de stdin")
    s.set_defaults(func=cmd_escribir)

    s = sub.add_parser("responder", help="contesta y marca HECHO")
    s.add_argument("id")
    s.add_argument("--texto", default=None)
    s.set_defaults(func=cmd_responder)

    s = sub.add_parser("hecho", help="marca HECHO sin responder")
    s.add_argument("id")
    s.set_defaults(func=cmd_hecho)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
