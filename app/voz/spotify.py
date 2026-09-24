"""Control de Spotify por voz, con la API oficial (Spotify Web API).

Por que la API y no automatizar la ventana: la API busca y pone la cancion exacta
en ~1 s, sin depender de que la ventana tenga el foco ni del diseno de la app.
Requiere Spotify PREMIUM (los endpoints de reproduccion son solo Premium).

SETUP, una sola vez:

  1. Entrar a https://developer.spotify.com/dashboard -> "Create app".
     Nombre y descripcion: cualquiera. En "Redirect URIs" poner EXACTAMENTE:

         http://127.0.0.1:8888/callback

     OJO: tiene que ser 127.0.0.1, no "localhost" (Spotify rechaza localhost).
     Marcar "Web API" y guardar.

  2. Copiar el Client ID y el Client Secret y ponerlos en el .env del proyecto:

         SPOTIFY_CLIENT_ID=lo_que_te_dio
         SPOTIFY_CLIENT_SECRET=lo_que_te_dio

  3. Desde la raiz del proyecto, una sola vez:

         python -m app.voz.spotify --autorizar

     Se abre el navegador, aceptas los permisos, y el token queda guardado en
     spotify_token.json (fuera de git). El access token se renueva solo.

     OJO: el dashboard de Spotify muestra "Refresh Token Lifetime: 180 days", asi
     que cada ~180 dias hay que volver a correr --autorizar. Si algun dia Venus
     contesta "no pude renovar el token de Spotify", es eso: no esta roto, se
     vencio la autorizacion.

  4. Probar sin usar la voz:

         python -m app.voz.spotify "californication"
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.parse
import webbrowser

# Esta laptop INTERCEPTA HTTPS: sin esto, cualquier request a Spotify muere con
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate". truststore
# le dice a Python que use el almacen de certificados de Windows, que si tiene el
# certificado del proxy. Lo hacen TODOS los modulos del proyecto que salen a
# internet (core, analizar_gemini, bot_telegram, webhook_wasender, agente_web);
# olvidarlo aca costo dos intentos de autorizacion.
os.environ.pop("SSLKEYLOGFILE", None)     # Avast lo apunta a un proxy propio y rompe el SSL
import truststore
truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv

from app.rutas import ENV, SPOTIFY_TOKEN

load_dotenv(ENV)

REDIRECT = "http://127.0.0.1:8888/callback"      # loopback por IP: Spotify no acepta localhost
PUERTO = 8888
# Lo minimo que hace falta: leer el estado del reproductor (para saber si hay un
# dispositivo activo) y modificarlo (para poner la cancion).
SCOPES = "user-read-playback-state user-modify-playback-state"
API = "https://api.spotify.com/v1"
TIMEOUT = 10
# Cuanto esperar a que Spotify se registre como dispositivo despues de abrirlo.
# Medido: tarda unos 4-8 s desde frio, por eso 25 y no 10.
ESPERA_DISPOSITIVO = 25
# Cuanto espera el server local a que aceptes en el navegador. 120 s era muy poco
# para un paso manual (se vencio dos veces); si igual no llegas, existe --codigo,
# que canjea el codigo despues sin depender de esta ventana.
ESPERA_AUTORIZACION = 900


def _cfg():
    cid = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    sec = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    return cid, sec


def _auth_basica():
    cid, sec = _cfg()
    return base64.b64encode(f"{cid}:{sec}".encode()).decode()


def _leer_token():
    try:
        return json.loads(SPOTIFY_TOKEN.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_token(d):
    # expira_en absoluto, no relativo: asi sobrevive a que se reinicie voz.py
    d = dict(d)
    if "expires_in" in d:
        d["expira_en"] = time.time() + float(d.pop("expires_in")) - 60
    viejo = _leer_token()
    viejo.update({k: v for k, v in d.items() if v})
    SPOTIFY_TOKEN.write_text(json.dumps(viejo, indent=2), encoding="utf-8")
    return viejo


def _token():
    """Access token valido. Lo renueva con el refresh token si hace falta."""
    t = _leer_token()
    if not t.get("refresh_token"):
        raise RuntimeError("Spotify no esta autorizado todavia. "
                           "Corre: python -m app.voz.spotify --autorizar")
    if t.get("access_token") and time.time() < t.get("expira_en", 0):
        return t["access_token"]
    r = requests.post("https://accounts.spotify.com/api/token",
                      data={"grant_type": "refresh_token",
                            "refresh_token": t["refresh_token"]},
                      headers={"Authorization": f"Basic {_auth_basica()}"},
                      timeout=TIMEOUT)
    if r.status_code != 200:
        # Lo mas probable a los ~180 dias: se vencio el refresh token (ver el
        # encabezado). No esta roto, hay que volver a autorizar.
        raise RuntimeError(
            f"no pude renovar el token de Spotify ({r.status_code}). "
            "Si ya venia andando, se vencio la autorizacion: corre de nuevo "
            "python -m app.voz.spotify --autorizar")
    return _guardar_token(r.json())["access_token"]


def _api(metodo, path, **kw):
    r = requests.request(metodo, API + path,
                         headers={"Authorization": f"Bearer {_token()}"},
                         timeout=TIMEOUT, **kw)
    return r


# ---------------------------------------------------------------- busqueda

# "poneme algo de X", "la radio de X", "musica de X" -> es un ARTISTA, no un tema.
_PISTAS_ARTISTA = ("la radio de ", "radio de ", "algo de ", "musica de ",
                   "temas de ", "canciones de ", "lo mejor de ")
_PISTAS_LISTA = ("la playlist ", "playlist ", "la lista ", "mi lista ")
# Ruido que deja el dictado adelante del nombre real.
_SOBRA = ("la cancion ", "el tema ", "el temita ", "la musica ", "musica ",
          "en spotify", "por spotify", "de spotify", "spotify")


def _limpiar(consulta):
    q = consulta.strip().strip(".,!?").lower()
    for s in _SOBRA:
        q = q.replace(s, " ")
    return " ".join(q.split())


def _sin_conector(q):
    """Saca el conector que queda colgando al recortar la pista.
    "la playlist de entrenamiento" -> pista "la playlist " -> queda "de entrenamiento",
    y buscar "de entrenamiento" da peores resultados que "entrenamiento"."""
    q = q.strip()
    for c in ("de ", "del ", "la ", "el ", "los ", "las ", "mi ", "mis "):
        if q.startswith(c):
            return q[len(c):].strip()
    return q


def buscar(consulta):
    """Devuelve (uri, descripcion, es_contexto) o (None, motivo, False).

    es_contexto=True cuando lo que hay que reproducir es una coleccion (artista o
    playlist) y va como context_uri; False cuando es un tema puntual.
    """
    bruto = consulta.strip().lower()
    tipo = "track"
    for p in _PISTAS_ARTISTA:
        if bruto.startswith(p) or f" {p}" in bruto:
            tipo = "artist"
            bruto = _sin_conector(bruto.split(p, 1)[1])
            break
    else:
        for p in _PISTAS_LISTA:
            if bruto.startswith(p):
                tipo = "playlist"
                bruto = _sin_conector(bruto.split(p, 1)[1])
                break

    q = _limpiar(bruto)
    if not q:
        return None, "no entendi que poner", False

    orden = [tipo] + [t for t in ("track", "artist", "playlist") if t != tipo]
    for t in orden:
        r = _api("GET", "/search", params={"q": q, "type": t, "limit": 1})
        if r.status_code != 200:
            return None, f"la busqueda fallo ({r.status_code})", False
        items = (r.json().get(t + "s") or {}).get("items") or []
        items = [i for i in items if i]          # Spotify devuelve None sueltos a veces
        if not items:
            continue
        it = items[0]
        if t == "track":
            quien = ", ".join(a["name"] for a in it.get("artists", []))
            return it["uri"], f"{it['name']} de {quien}", False
        if t == "artist":
            return it["uri"], it["name"], True
        return it["uri"], f"la lista {it['name']}", True
    return None, f"no encontre nada con {q}", False


# ---------------------------------------------------------------- dispositivo

def dispositivos():
    r = _api("GET", "/me/player/devices")
    if r.status_code != 200:
        return []
    return [d for d in r.json().get("devices", []) if d]


def asegurar_dispositivo():
    """Devuelve el id de un dispositivo donde reproducir. Si no hay ninguno, ABRE
    Spotify y espera a que se registre. Devuelve None si no aparece."""
    ds = dispositivos()
    activo = next((d for d in ds if d.get("is_active")), None)
    if activo:
        return activo["id"]
    if ds:                                       # hay pero dormido: sirve igual
        pc = next((d for d in ds if d.get("type") == "Computer"), ds[0])
        return pc["id"]

    print("spotify: no hay dispositivo, abro la app...", flush=True)
    try:
        # ⚠ creationflags, por lo mismo que en acciones.py: sin la marca el cmd.exe
        # del `start` parpadea como ventana negra en la pantalla (2026-09-06).
        subprocess.Popen('start "" spotify', shell=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print("spotify: no pude abrir la app:", e, flush=True)
        return None
    limite = time.time() + ESPERA_DISPOSITIVO
    while time.time() < limite:
        time.sleep(1.5)
        ds = dispositivos()
        if ds:
            pc = next((d for d in ds if d.get("type") == "Computer"), ds[0])
            print(f"spotify: dispositivo listo ({pc.get('name')})", flush=True)
            return pc["id"]
    return None


# ---------------------------------------------------------------- reproducir

def poner(consulta):
    """Busca y reproduce. Devuelve una frase CORTA para que la diga el TTS."""
    uri, desc, es_contexto = buscar(consulta)
    if not uri:
        return f"No pude: {desc}."

    dev = asegurar_dispositivo()
    if not dev:
        return "Abri Spotify y probá de nuevo, no lo veo disponible."

    cuerpo = {"context_uri": uri} if es_contexto else {"uris": [uri]}
    r = _api("PUT", "/me/player/play", params={"device_id": dev}, json=cuerpo)
    if r.status_code in (200, 202, 204):
        return f"Poniendo {desc}."
    if r.status_code == 403:
        # 403 en /play es casi siempre "no sos Premium" o restriccion de la cuenta.
        return "Spotify no me deja controlar la reproduccion. Revisá que la cuenta sea Premium."
    if r.status_code == 404:
        return "Spotify no tiene un dispositivo activo. Dale play una vez a mano y volvé a pedirme."
    return f"Spotify me dio error {r.status_code}."


# ---------------------------------------------------------------- autorizacion

def url_autorizacion():
    cid, _ = _cfg()
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": SCOPES})


def canjear(codigo_o_url):
    """Cambia el codigo de autorizacion por los tokens y los guarda.

    Acepta el codigo pelado o la URL completa a la que quedo el navegador, que es
    mas facil de copiar: basta con copiar la barra de direcciones.

    Existe para no depender de que el server local y el clic pasen dentro de la
    misma ventana de tiempo: se puede aceptar en el navegador cuando se quiera y
    canjear despues. OJO: el codigo es de UN SOLO USO y dura ~10 minutos.
    """
    c = codigo_o_url.strip()
    if "code=" in c:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(c).query)
        c = (q.get("code") or [""])[0]
    if not c:
        print("No encontre el codigo. Pegame la URL completa que quedo en el navegador,")
        print("la que empieza con http://127.0.0.1:8888/callback?code=...")
        return 1
    r = requests.post("https://accounts.spotify.com/api/token",
                      data={"grant_type": "authorization_code",
                            "code": c, "redirect_uri": REDIRECT},
                      headers={"Authorization": f"Basic {_auth_basica()}"},
                      timeout=TIMEOUT)
    if r.status_code != 200:
        print("Fallo el canje:", r.status_code, r.text[:300])
        if "invalid_grant" in r.text:
            print("Ese codigo ya se uso o se vencio. Abri el link de nuevo y aceptá otra vez.")
        return 1
    _guardar_token(r.json())
    print(f"Listo. Token guardado en {SPOTIFY_TOKEN}")
    try:
        ds = dispositivos()
        print("Dispositivos que veo:", ", ".join(d["name"] for d in ds) or "(ninguno)")
    except Exception as e:
        print("token guardado, pero no pude listar dispositivos:", e)
    return 0


def autorizar():
    """Flujo de una sola vez: abre el navegador, recibe el codigo y guarda el token."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    cid, sec = _cfg()
    if not cid or not sec:
        print("Faltan SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en el .env.")
        print("Ver las instrucciones al principio de este archivo.")
        return 1

    codigo = {}
    pedidos = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            partes = urllib.parse.urlparse(self.path)
            pedidos.append(partes.path)
            q = urllib.parse.parse_qs(partes.query)
            code = (q.get("code") or [None])[0]
            error = (q.get("error") or [None])[0]
            if code:
                codigo["code"] = code
            if error:
                codigo["error"] = error
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if code:
                msg = "Listo, ya podés cerrar esta pestaña."
            elif error:
                msg = f"Spotify rechazó la autorización: {error}"
            else:
                msg = "Esperando la respuesta de Spotify..."
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h2>{msg}"
                             "</h2></body></html>".encode("utf-8"))

        def log_message(self, *a):
            pass                                  # sin ruido en la consola

    url = url_autorizacion()
    print("Abriendo el navegador para autorizar Spotify...")
    print(f"Si no se abre solo, entrá a mano:\n  {url}\n")
    srv = HTTPServer(("127.0.0.1", PUERTO), Handler)
    abrio = webbrowser.open(url)
    print(f"navegador: {'lanzado' if abrio else 'NO se pudo abrir, entra a mano con el link de arriba'}")
    # BUCLE, no un solo handle_request(): esa funcion atiende UNA peticion y vuelve.
    # Si el navegador pedia /favicon.ico o hacia una preconexion, se consumia ese
    # pedido y salia diciendo "sin respuesta a tiempo" aunque el usuario hubiera
    # aceptado. Paso el 2026-08-10, dos veces.
    srv.timeout = 5
    limite = time.time() + ESPERA_AUTORIZACION
    print(f"Esperando que aceptes en el navegador "
          f"(hasta {ESPERA_AUTORIZACION // 60} minutos)...", flush=True)
    while time.time() < limite:
        if codigo.get("code") or codigo.get("error"):
            break
        srv.handle_request()                      # con timeout de 5 s por vuelta
    srv.server_close()

    if not codigo.get("code"):
        # Diagnostico separado: no es lo mismo "no llego NADA" que "llego otra cosa".
        if codigo.get("error"):
            print(f"Spotify rechazo la autorizacion: {codigo['error']}")
        elif pedidos:
            print(f"Llegaron pedidos al server local pero ninguno traia el codigo: {pedidos}")
            print("Revisa que el Redirect URI de la app sea EXACTAMENTE", REDIRECT)
        else:
            print("No llego NINGUN pedido al server local: nadie apreto 'Agree' a tiempo.")
            print("No hace falta correr esto de nuevo contra el reloj. Podes:")
            print("  1) abrir el link de arriba cuando quieras y aceptar;")
            print("  2) copiar la URL a la que queda el navegador (va a decir que no")
            print("     se puede conectar, no importa: lo que sirve es la barra de")
            print("     direcciones, que trae ?code=...);")
            print("  3) canjearla con:  python -m app.voz.spotify --codigo \"<esa URL>\"")
        return 1
    return canjear(codigo["code"])


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--autorizar":
        return autorizar()
    if args[0] == "--codigo":
        if len(args) < 2:
            print("Uso: python -m app.voz.spotify --codigo \"<la URL con ?code=... o el codigo>\"")
            return 1
        return canjear(args[1])
    if args[0] == "--link":
        print(url_autorizacion())
        return 0
    print(poner(" ".join(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
