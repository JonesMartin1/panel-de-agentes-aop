#!/usr/bin/env python3
"""Manda un aviso al usuario por Telegram o por WhatsApp. Solo ENVIA: nunca lee.

    python avisar.py "Termine el refactor, quedaron 3 tests en rojo"
    python avisar.py --por whatsapp "Se cayo el bot"
    python avisar.py --por ambos "Algo importante"
    python avisar.py --archivo salida.txt          # textos largos o con comillas
    python avisar.py --proyecto mi-proyecto "Listo"   # forzar el nombre del proyecto
    python avisar.py --categoria tarea "Termine el refactor"   # que categoria (ver abajo)
    python avisar.py --categoria error --proyecto mi-proyecto --solo-obsidian "Bug X"
    python avisar.py --hablar "Se desconecto el WhatsApp"   # + Laura lo dice

Por que no lee: el bot de wpp-transcriptor hace long-polling con el MISMO token de
Telegram. Si esta skill llamara getUpdates le robaria los mensajes y se romperia la
transcripcion y la Laura de Telegram. Enviar es seguro; leer, no.

Si el canal elegido falla del todo, prueba solo con el otro y lo aclara: un aviso
que no llega es peor que un aviso por el canal equivocado.

Ademas de mandar el mensaje, cada aviso queda anotado en el cuaderno de notas de
Obsidian (la carpeta de la variable de entorno CUADERNO_NOTAS), en una nota distinta
segun `--categoria` (tarea / produccion / decision / general / error). La categoria
"error" se agrupa por PROYECTO adentro de la nota, mas nuevo arriba. Es best-effort:
si no hay cuaderno configurado, el aviso igual sale (salvo que se use --solo-obsidian).

Solo stdlib, para que ande con cualquier python3 de cualquier proyecto.
"""

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

CONFIG_TG = Path.home() / ".claude" / "telegram.json"
CONFIG_WA = Path.home() / ".claude" / "whatsapp.json"
# Buzon de avisos para que Laura los DIGA en voz alta (--hablar). Lo come el hilo
# _vigilar_avisos_hablados de wpp-transcriptor cuando hay un hueco en la charla. Vive
# en ~/.claude y no en ese proyecto: esta skill es global y no lo conoce.
AVISOS_HABLADOS = Path.home() / ".claude" / "avisos_hablados.jsonl"
LIMITE = 3900          # Telegram corta en 4096; dejamos aire para el encabezado
TIMEOUT = 20

# La carpeta del cuaderno de Obsidian. Vacia = no se anota nada (el aviso sale igual).
NOTAS_DIR = Path(os.environ["CUADERNO_NOTAS"]) if os.environ.get("CUADERNO_NOTAS") else None
NOTA_POR_CATEGORIA = {
    "tarea": "Avisos - Tareas.md",
    "produccion": "Avisos - Produccion.md",
    "decision": "Avisos - Decisiones.md",
    "general": "Avisos - General.md",
    "error": "Avisos - Errores.md",
}


class SinConfig(Exception):
    """Falta o esta incompleta la config de un canal.

    Es una excepcion y NO un sys.exit a proposito: asi un canal mal configurado
    cae al otro canal en vez de matar el aviso entero.
    """


def _config(ruta, obligatorias, ejemplo):
    if not ruta.exists():
        raise SinConfig(f"falta {ruta} (tiene que tener: {ejemplo})")
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        raise SinConfig(f"no pude leer {ruta}: {e}")
    faltan = [k for k in obligatorias if not d.get(k)]
    if faltan:
        raise SinConfig(f"{ruta} necesita: {', '.join(faltan)}")
    return d


def _post(url, datos=None, json_body=None, headers=None):
    """Un intento por urllib y, si el SSL de la maquina lo rompe, por curl.

    Algunos antivirus interceptan HTTPS: SSLKEYLOGFILE hace explotar el SSL de
    Python con PermissionError y a veces el certificado no valida. curl usa el
    almacen de Windows y pasa igual.
    Devuelve (dict de respuesta, error) -- uno de los dos es None.
    """
    os.environ.pop("SSLKEYLOGFILE", None)
    headers = dict(headers or {})
    if json_body is not None:
        cuerpo = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    else:
        cuerpo = urllib.parse.urlencode(datos or {}).encode()
    try:
        req = urllib.request.Request(url, data=cuerpo, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}"), None
    except Exception as e:
        primero = e
    cmd = ["curl", "-s", "--max-time", str(TIMEOUT), "-X", "POST", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    if json_body is not None:
        cmd += ["-d", json.dumps(json_body)]
    else:
        for k, v in (datos or {}).items():
            cmd += ["--data-urlencode", f"{k}={v}"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 10)
        return json.loads(p.stdout or "{}"), None
    except Exception as e:
        return None, f"por python: {primero} | por curl: {e}"


def _por_telegram(texto):
    d = _config(CONFIG_TG, ("token", "chat_id"),
                '{"token": "...", "chat_id": "...", "nombre": "..."}')
    r, err = _post(f"https://api.telegram.org/bot{d['token']}/sendMessage",
                   datos={"chat_id": d["chat_id"], "text": texto,
                          "disable_web_page_preview": "true"})
    if err:
        return err
    return None if (r or {}).get("ok") else f"Telegram lo rechazo: {str(r)[:160]}"


def _por_whatsapp(texto):
    """Evolution API (self-hosted). El numero va tal cual: acepta numero o JID."""
    d = _config(CONFIG_WA, ("url", "apikey", "instancia", "numero"),
                '{"url": "...", "apikey": "...", "instancia": "...", "numero": "549..."}')
    url = (f"{d['url'].rstrip('/')}/message/sendText/"
           + urllib.parse.quote(d["instancia"], safe=""))
    r, err = _post(url, json_body={"number": d["numero"], "text": texto},
                   headers={"apikey": d["apikey"]})
    if err:
        return err
    # Evolution devuelve la clave del mensaje cuando salio bien.
    if (r or {}).get("key") or (r or {}).get("messageTimestamp"):
        return None
    return f"WhatsApp lo rechazo: {str(r)[:160]}"


def _subir(url, campos, archivo_campo, ruta, headers=None):
    """Sube un archivo por multipart. Va por curl y no por urllib a proposito:
    armar multipart a mano es codigo que no vale la pena mantener, y curl ya es
    el respaldo del resto del script."""
    cmd = ["curl", "-s", "--max-time", str(TIMEOUT * 3), "-X", "POST", url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    for k, v in campos.items():
        cmd += ["-F", f"{k}={v}"]
    cmd += ["-F", f"{archivo_campo}=@{ruta}"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT * 3 + 10)
        return json.loads(p.stdout or "{}"), None
    except Exception as e:
        return None, f"curl: {e}"


def _archivo_por_telegram(ruta, leyenda):
    """sendDocument. Es ENVIAR, asi que no choca con la regla de no leer."""
    d = _config(CONFIG_TG, ("token", "chat_id"),
                '{"token": "...", "chat_id": "...", "nombre": "..."}')
    r, err = _subir(f"https://api.telegram.org/bot{d['token']}/sendDocument",
                    {"chat_id": d["chat_id"], "caption": leyenda[:1024]},
                    "document", ruta)
    if err:
        return err
    return None if (r or {}).get("ok") else f"Telegram lo rechazo: {str(r)[:200]}"


def _archivo_por_whatsapp(ruta, leyenda):
    """Evolution manda documentos en base64, no multipart."""
    d = _config(CONFIG_WA, ("url", "apikey", "instancia", "numero"),
                '{"url": "...", "apikey": "...", "instancia": "...", "numero": "549..."}')
    ruta = Path(ruta)
    b64 = base64.b64encode(ruta.read_bytes()).decode()
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    url = (f"{d['url'].rstrip('/')}/message/sendMedia/"
           + urllib.parse.quote(d["instancia"], safe=""))
    r, err = _post(url, json_body={"number": d["numero"], "mediatype": "document",
                                   "mimetype": tipo, "media": b64,
                                   "fileName": ruta.name, "caption": leyenda[:900]},
                   headers={"apikey": d["apikey"]})
    if err:
        return err
    if (r or {}).get("key") or (r or {}).get("messageTimestamp"):
        return None
    return f"WhatsApp lo rechazo: {str(r)[:200]}"


def _mandar_archivo(canal, ruta, leyenda):
    try:
        return (_archivo_por_telegram if canal == "telegram"
                else _archivo_por_whatsapp)(ruta, leyenda)
    except SinConfig as e:
        return str(e)


CANALES = {"telegram": _por_telegram, "whatsapp": _por_whatsapp}


def _mandar(canal, partes, encabezado):
    """Manda todas las partes por un canal. Devuelve None si anduvo, o el error."""
    for n, parte in enumerate(partes):
        try:
            err = CANALES[canal](encabezado + parte if n == 0 else parte)
        except SinConfig as e:
            return str(e)
        if err:
            return f"{err} (parte {n + 1} de {len(partes)})"
    return None


def _formatear_entrada(ahora, primera_linea, resto, prefijo=""):
    cuerpo = f"- **{ahora}**{prefijo} — {primera_linea}"
    if resto:
        cuerpo += "\n  " + resto.replace("\n", "\n  ")
    return cuerpo + "\n"


def _anotar_plano(ruta, ahora, proyecto, primera_linea, resto):
    """Categorias normales: lista cronologica plana, con el proyecto inline."""
    if not ruta.exists():
        titulo = ruta.stem
        ruta.write_text(
            f"# {titulo}\n\nRegistro automatico de avisos de esta categoria. "
            f"Lo escribe `avisar.py` -- no editar a mano el formato de las lineas, "
            f"agregar comentarios propios abajo de todo si hace falta.\n\n", encoding="utf-8")
    entrada = _formatear_entrada(ahora, primera_linea, resto, prefijo=f" · {proyecto}")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(entrada)


def _anotar_agrupado_por_proyecto(ruta, ahora, proyecto, primera_linea, resto):
    """Categoria 'error': agrupada por proyecto, mas nuevo arriba de cada grupo."""
    encabezado_proyecto = f"## {proyecto}"
    entrada = _formatear_entrada(ahora, primera_linea, resto)

    if not ruta.exists():
        contenido = ("# Avisos - Errores\n\n"
                     "Registro automatico de errores, agrupado por proyecto. Lo escribe "
                     "`avisar.py` -- no editar a mano el formato de las lineas, agregar "
                     "comentarios propios abajo de todo si hace falta.\n")
    else:
        contenido = ruta.read_text(encoding="utf-8")

    marca = encabezado_proyecto + "\n"
    if marca in contenido:
        idx = contenido.index(marca) + len(marca)
        contenido = contenido[:idx] + entrada + contenido[idx:]
    else:
        if not contenido.endswith("\n\n"):
            contenido = contenido.rstrip("\n") + "\n\n"
        contenido += marca + entrada

    ruta.write_text(contenido, encoding="utf-8")


def _registrar_obsidian(categoria, proyecto, texto):
    """Deja una entrada en el cuaderno de notas, para poder leer despues que
    hicieron otras sesiones.

    Best-effort a proposito: si no hay cuaderno configurado o no existe la carpeta,
    el aviso por Telegram/WhatsApp ya salio y no tiene que fallar por esto.
    """
    try:
        if NOTAS_DIR is None or not NOTAS_DIR.exists():
            return
        nombre = NOTA_POR_CATEGORIA.get(categoria, NOTA_POR_CATEGORIA["general"])
        ruta = NOTAS_DIR / nombre
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        lineas = texto.strip().splitlines()
        primera_linea = lineas[0] if lineas else ""
        resto = "\n".join(lineas[1:])
        if categoria == "error":
            _anotar_agrupado_por_proyecto(ruta, ahora, proyecto, primera_linea, resto)
        else:
            _anotar_plano(ruta, ahora, proyecto, primera_linea, resto)
    except Exception as e:
        print(f"  (no pude anotar en el cuaderno: {e})")


def _dejar_hablado(proyecto, texto):
    """Deja el aviso para que Laura lo diga en voz alta, si esta prendida.

    Best-effort y NUNCA en lugar del mensaje al celular: si la voz esta apagada,
    nadie lo escucha.
    """
    try:
        AVISOS_HABLADOS.parent.mkdir(parents=True, exist_ok=True)
        entrada = json.dumps({"cuando": datetime.now().timestamp(),
                              "proyecto": proyecto, "texto": texto},
                             ensure_ascii=False)
        with open(AVISOS_HABLADOS, "a", encoding="utf-8") as f:
            f.write(entrada + "\n")
    except Exception as e:
        print(f"  (no pude dejarle el aviso hablado a Laura: {e})")


def main():
    ap = argparse.ArgumentParser(description="Avisarle al usuario por Telegram o WhatsApp.")
    ap.add_argument("mensaje", nargs="*", help="el texto a mandar")
    ap.add_argument("--por", default="telegram", choices=["telegram", "whatsapp", "ambos"],
                    help="canal (por defecto telegram)")
    ap.add_argument("--archivo", help="leer el texto de un archivo (textos largos)")
    ap.add_argument("--proyecto", help="de que proyecto viene (por defecto, la carpeta actual)")
    ap.add_argument("--adjuntar", help="mandar TAMBIEN un archivo (csv, imagen, pdf...). "
                                       "Telegram aguanta 50 MB; por WhatsApp conviene < 15 MB")
    ap.add_argument("--categoria", default="general",
                    choices=["tarea", "produccion", "decision", "general", "error"],
                    help="tarea larga terminada / algo roto en produccion / "
                         "esperando una decision / general (por defecto) / "
                         "error (se agrupa por proyecto en el cuaderno)")
    ap.add_argument("--solo-obsidian", action="store_true",
                    help="no mandar nada al celular, solo anotar en el cuaderno")
    ap.add_argument("--hablar", action="store_true",
                    help="ademas, que Laura lo diga en voz alta cuando haya un hueco")
    a = ap.parse_args()

    adjunto = None
    if a.adjuntar:
        adjunto = Path(a.adjuntar).expanduser()
        if not adjunto.is_file():
            sys.exit(f"No existe el archivo a adjuntar: {adjunto}")
        mb = adjunto.stat().st_size / 1024 / 1024
        if mb > 45:
            sys.exit(f"{adjunto.name} pesa {mb:.0f} MB: no entra en Telegram (50 MB).")

    texto = (Path(a.archivo).read_text(encoding="utf-8", errors="replace")
             if a.archivo else " ".join(a.mensaje)).strip()
    if not texto and not adjunto:
        sys.exit("No hay nada que mandar.")
    if not texto:
        texto = f"Te mando {adjunto.name}."

    # De que proyecto viene: con 2-3 agentes a la vez, sin esto no se sabe quien habla.
    proyecto = a.proyecto or Path.cwd().name

    # Antes que nada: es lo unico que puede llegar en el segundo en que pasa.
    if a.hablar:
        _dejar_hablado(proyecto, texto)

    if a.solo_obsidian:
        if NOTAS_DIR is None:
            sys.exit("No hay cuaderno configurado: falta la variable CUADERNO_NOTAS.")
        _registrar_obsidian(a.categoria, proyecto, texto)
        print(f"Anotado en el cuaderno (categoria: {a.categoria}), sin mandar nada al celular.")
        return

    encabezado = f"[{proyecto}]\n"
    partes = [texto[i:i + LIMITE] for i in range(0, len(texto), LIMITE)]
    cuantos = f" ({len(partes)} mensajes)" if len(partes) > 1 else ""

    pedidos = ["telegram", "whatsapp"] if a.por == "ambos" else [a.por]
    llegaron, fallaron = [], []
    for canal in pedidos:
        err = _mandar(canal, partes, encabezado)
        (llegaron if err is None else fallaron).append(canal if err is None else (canal, err))

    # Un solo canal pedido y fallo: probamos el otro. Un aviso que no llega es
    # peor que un aviso por el canal equivocado -- pero se aclara cual se uso.
    if not llegaron and len(pedidos) == 1:
        otro = "whatsapp" if pedidos[0] == "telegram" else "telegram"
        err2 = _mandar(otro, partes, encabezado + f"(no pude por {pedidos[0]})\n")
        if err2 is None:
            llegaron.append(otro)
        else:
            fallaron.append((otro, err2))

    if adjunto and llegaron:
        for canal in llegaron:
            err = _mandar_archivo(canal, str(adjunto), f"{proyecto}: {adjunto.name}")
            print(f"  ({adjunto.name} por {canal}: mandado)" if err is None
                  else f"  ({adjunto.name} por {canal} NO se pudo: {err})")

    _registrar_obsidian(a.categoria, proyecto, texto)

    if llegaron:
        print(f"Avisado por {' y '.join(llegaron)}{cuantos}.")
        for canal, err in fallaron:
            print(f"  (por {canal} no se pudo: {err})")
        return
    sys.exit("No pude avisar por ningun canal:\n" +
             "\n".join(f"  {c}: {e}" for c, e in fallaron))


if __name__ == "__main__":
    main()
