"""El eco (la burbuja provisoria) se borra cuando tu mensaje entra al hilo.

⭐ El caso que se escapó dos veces el 2026-08-22: en una charla LARGA el mensaje se veia
DOS veces hasta que la sesion terminaba. `/movil/chat` devuelve solo los ULTIMOS 40
mensajes, y la pantalla guardaba la POSICION del hilo al mandar: pasados los 40 la lista
deja de crecer, esa posicion cae siempre al final y no se miraba ni un mensaje.
Ahora se CUENTA en vez de ubicar, y esta prueba corre la logica real de las dos
pantallas (`sesiones.html` y el `MOVIL_HTML` de `panel.py`), sacada del disco con node.

    python -m pruebas.probar_eco_mensaje
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.rutas import RAIZ

TOPE = 40           # el `ultimos` de /movil/chat
bien = malo = 0


def ok(cond, que):
    global bien, malo
    if cond:
        bien += 1
        print("  ok   ", que)
    else:
        malo += 1
        print("  MAL  ", que)


def js_de(nombre, fuente):
    """Saca `suelto` y `cuentaTuya` de una pantalla, tal cual estan en el disco."""
    trozos = []
    for pat in (r"const suelto = [\s\S]*?;\n", r"function cuentaTuya\([\s\S]*?\n\}\n"):
        m = re.search(pat, fuente)
        if not m:
            raise SystemExit("No encontré %s en %s" % (pat[:20], nombre))
        trozos.append(m.group(0))
    return "".join(trozos)


def js_fotos_compu(fuente):
    """Saca también la decisión real del eco con foto de la pantalla grande."""
    trozos = [js_de("/sesiones (la compu)", fuente)]
    for pat in (r"const cuentaFotos = [\s\S]*?;\n",
                r"function llegoEco\([\s\S]*?\n\}\n"):
        m = re.search(pat, fuente)
        if not m:
            raise SystemExit("No encontré %s en /sesiones (la compu)" % pat[:24])
        trozos.append(m.group(0))
    return "".join(trozos)


def pantalla_sesiones():
    return (RAIZ / "app" / "estaticos" / "sesiones.html").read_text(encoding="utf-8")


def pantalla_movil():
    arbol = ast.parse((RAIZ / "panel.py").read_text(encoding="utf-8"))
    for nodo in arbol.body:
        if (isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
                and any(getattr(d, "id", "") == "MOVIL_HTML" for d in nodo.targets)):
            return nodo.value.value
    raise SystemExit("No encontré MOVIL_HTML en panel.py")


def correr(js_pantalla, casos):
    """Corre los casos con la logica REAL de esa pantalla y devuelve los `yaLlego`."""
    guion = js_pantalla + """
const casos = %s;
const salida = casos.map(c => {
  // lo mismo que hace la pantalla: contar al mandar, contar al repintar
  const antes = cuentaTuya(c.hilo_al_mandar, c.escrito);
  const hilo = c.hilo_despues.slice(-%d);   // el servidor manda solo los ultimos
  return cuentaTuya(hilo, c.escrito) > antes;
});
console.log(JSON.stringify(salida));
""" % (json.dumps(casos, ensure_ascii=False), TOPE)
    # ⚠ Por ARCHIVO, no con `node -e`: con los casos adentro el guion pasa el límite de
    # largo de la línea de comando de Windows y sale un WinError 206 que no dice nada.
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8",
                                     delete=False) as f:
        f.write(guion)
        ruta = f.name
    try:
        r = subprocess.run(["node", ruta], capture_output=True, text=True,
                           encoding="utf-8")
    finally:
        os.unlink(ruta)
    if r.returncode != 0:
        raise SystemExit("node falló:\n" + (r.stderr or "")[:800])
    return json.loads(r.stdout.strip().splitlines()[-1])


def vos(t):
    return {"de": "vos", "texto": t}


def ia(t):
    return {"de": "claude", "texto": t}


MIO = "Cual es ese proceo que ocupa 1gb de mi grafica?"
MARCA = ("[Te paso una imagen desde el celular; está guardada en "
         r"D:\IA\wpp-transcriptor\resultados\chat_panel\1787445060297_0.png"
         " — abrila con la herramienta Read antes de contestar.] ")

# Un hilo LARGO: mas de 40 mensajes, que es donde se rompia.
LARGO = [(vos("mensaje viejo %d" % i) if i % 2 else ia("respuesta vieja %d" % i))
         for i in range(60)]

CASOS = [
    {"que": "charla corta: tu mensaje llegó",
     "escrito": MIO, "hilo_al_mandar": [vos("hola"), ia("hola")],
     "hilo_despues": [vos("hola"), ia("hola"), vos(MIO)], "espera": True},

    {"que": "charla corta: todavía no llegó (el eco tiene que quedarse)",
     "escrito": MIO, "hilo_al_mandar": [vos("hola"), ia("hola")],
     "hilo_despues": [vos("hola"), ia("hola")], "espera": False},

    {"que": "⭐ charla LARGA (60 mensajes): el caso que se veía doble",
     "escrito": MIO, "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [vos(MIO)], "espera": True},

    {"que": "charla larga y la sesión ya contestó varias veces encima",
     "escrito": MIO, "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [vos(MIO), ia("uno"), ia("dos"), ia("tres"), ia("cuatro")],
     "espera": True},

    {"que": "con una imagen: el corchete de la marca no rompe la comparación",
     "escrito": MIO, "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [vos(MARCA + MIO)], "espera": True},

    {"que": "con el clip (la foto no estaba en disco) tampoco",
     "escrito": MIO, "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [vos("📎 " + MIO)], "espera": True},

    {"que": "el CRLF que mete el navegador tampoco",
     "escrito": "Listo, ahora si\n\nCarga el hunyuan",
     "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [vos("Listo, ahora si\r\r\n\r\r\nCarga el hunyuan")],
     "espera": True},

    {"que": "mandás DOS veces lo mismo: el segundo eco no se borra con el primero",
     "escrito": MIO, "hilo_al_mandar": LARGO + [vos(MIO)],
     "hilo_despues": LARGO + [vos(MIO)], "espera": False},

    {"que": "...y sí se borra cuando el segundo entra de verdad",
     "escrito": MIO, "hilo_al_mandar": LARGO + [vos(MIO)],
     "hilo_despues": LARGO + [vos(MIO), ia("bueno"), vos(MIO)], "espera": True},

    {"que": "lo que dijo la SESIÓN no cuenta como tuyo",
     "escrito": MIO, "hilo_al_mandar": LARGO,
     "hilo_despues": LARGO + [ia(MIO)], "espera": False},
]

if not shutil.which("node"):
    raise SystemExit("Hace falta node para correr el JS de las pantallas.")

for nombre, fuente in (("/sesiones (la compu)", pantalla_sesiones()),
                       ("/movil (el celular)", pantalla_movil())):
    print("\n" + nombre)
    resultados = correr(js_de(nombre, fuente), CASOS)
    for caso, obtenido in zip(CASOS, resultados):
        ok(obtenido == caso["espera"], caso["que"])

# ⭐ 2026-08-25: en una charla larga, al entrar la captura nueva puede salir una vieja
# de los últimos 40. El total de fotos queda igual; con comentario, el texto es el ancla
# estable y la burbuja provisoria tiene que desaparecer igual.
fuente_compu = pantalla_sesiones()
guion_fotos = js_fotos_compu(fuente_compu) + """
const viejo = {de:'vos', texto:'foto anterior', imgs:['/vieja.png']};
const antes = [viejo];
for (let i=1; i<40; i++) antes.push({de:'claude', texto:'respuesta '+i});
const despues = antes.slice(1).concat([{de:'vos', texto:'Claro, tienen que mandar eso',
                                       imgs:['/nueva.png']}]);
console.log(JSON.stringify({
  fotosAntes: cuentaFotos(antes), fotosDespues: cuentaFotos(despues),
  llego: llegoEco(despues, 'Claro, tienen que mandar eso', true,
                  cuentaTuya(antes, 'Claro, tienen que mandar eso'), cuentaFotos(antes))
}));
"""
with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as f:
    f.write(guion_fotos)
    ruta_fotos = f.name
try:
    r = subprocess.run(["node", ruta_fotos], capture_output=True, text=True, encoding="utf-8")
finally:
    os.unlink(ruta_fotos)
if r.returncode != 0:
    raise SystemExit("node falló en el caso de fotos:\n" + (r.stderr or "")[:800])
foto = json.loads(r.stdout.strip().splitlines()[-1])
ok(foto["fotosAntes"] == foto["fotosDespues"],
   "la ventana larga reproduce el empate de cantidad de fotos")
ok(foto["llego"],
   "captura con comentario: se apaga el eco aunque salga una foto vieja del recorte")

print("\n%d en verde, %d en rojo" % (bien, malo))
if malo:
    raise SystemExit(1)
