"""Deja una nota en el pizarron visual del panel (el de la pantalla, no PIZARRA.md).

    python pizarra.py "lo que hay que anotar"
    python pizarra.py "titulo grande" --tipo texto
    python pizarra.py "ojo con esto" --color "#f5b8d0" --de mi-proyecto
    python pizarra.py --listar
    python pizarra.py --borrar 12

El pizarron vive adentro del panel del Servidor IA (wpp-transcriptor), en
http://127.0.0.1:8750/pizarra. Solo funciona en la maquina donde corre ese panel y
con el panel prendido: si no, avisa y no rompe nada.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

PANEL = "http://127.0.0.1:8750"
AYUDA_PANEL = ("El panel no esta prendido (nadie contesta en el 8750). "
               "Prendelo con 'python panel.py' en la carpeta de wpp-transcriptor y volve a intentar.")


def _pedir(ruta, datos=None, metodo=None):
    req = urllib.request.Request(
        PANEL + ruta,
        data=json.dumps(datos).encode("utf-8") if datos is not None else None,
        headers={"Content-Type": "application/json"},
        method=metodo or ("POST" if datos is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(AYUDA_PANEL, f"({e})", file=sys.stderr)
        sys.exit(2)


def main():
    p = argparse.ArgumentParser(description="Anotar en el pizarron del panel")
    p.add_argument("texto", nargs="?", help="lo que va escrito en la nota")
    p.add_argument("--tipo", default="nota", choices=["nota", "texto"],
                   help="nota = papelito de color (por defecto), texto = texto suelto")
    p.add_argument("--color", help="color en #rrggbb; si no, elige uno solo")
    p.add_argument("--de", help="quien la escribe (proyecto o sesion), va en la primera linea")
    p.add_argument("--x", type=float, help="posicion horizontal 0-100; si no, la acomoda solo")
    p.add_argument("--y", type=float, help="posicion vertical 0-100")
    p.add_argument("--listar", action="store_true", help="mostrar lo que ya hay en el pizarron")
    p.add_argument("--borrar", type=int, metavar="ID", help="sacar una nota por su numero")
    a = p.parse_args()

    if a.listar:
        estado = _pedir("/pizarra/estado")
        items = estado.get("items", [])
        if not items:
            print("El pizarron esta vacio.")
            return
        for i in items:
            texto = (i.get("texto") or i.get("tipo", "")).replace("\n", " / ")
            print(f'{i["id"]:>3}  {i.get("tipo","nota"):<10} {texto[:90]}')
        return

    if a.borrar is not None:
        _pedir(f"/pizarra/item/{a.borrar}", metodo="DELETE")
        print(f"Listo, saque la nota {a.borrar} del pizarron.")
        return

    if not a.texto:
        p.error("decime que escribir, o usa --listar / --borrar")

    texto = a.texto if not a.de else f"{a.de}:\n{a.texto}"
    datos = {"tipo": a.tipo, "texto": texto}
    for campo in ("color", "x", "y"):
        if getattr(a, campo) is not None:
            datos[campo] = getattr(a, campo)

    r = _pedir("/pizarra/agregar", datos)
    if r.get("ok") is False:
        print("No pude anotarla: " + str(r.get("error")), file=sys.stderr)
        sys.exit(1)
    print(f'Anotado en el pizarron (nota {r.get("id")}).')


if __name__ == "__main__":
    main()
