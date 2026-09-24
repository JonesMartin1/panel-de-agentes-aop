"""
Analisis con Gemini: toma la transcripcion + frames y devuelve JSON estructurado.
Requiere la variable de entorno GEMINI_API_KEY (ver archivo .env).

El "perfil" define el rol y que buscar segun el rubro (clinica, ventas,
reuniones, generico...). Los perfiles son archivos de texto en
app/nucleo/perfiles/<nombre>.txt; agregar uno nuevo es crear el .txt, no
tocar codigo. Un perfil desconocido cae en "generico" sin error.
"""

import os
import json
import mimetypes
from pathlib import Path

os.environ.pop("SSLKEYLOGFILE", None)  # Avast rompe el SSL de Python

import truststore
truststore.inject_into_ssl()

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.rutas import ENV

load_dotenv(ENV)

MODELO_GEMINI = "gemini-2.5-flash"   # rapido, barato y multimodal

DIR_PERFILES = Path(__file__).parent / "perfiles"
PERFIL_DEFECTO = "generico"

# Estructura comun a todos los perfiles: cambia el "rol" (que le decimos que
# es y que buscar), nunca la forma del JSON. Asi un solo formato_legible()
# sirve para cualquier rubro.
_ESTRUCTURA_JSON = """
Tu tarea: analizar el contenido y devolver SOLO un JSON con esta estructura exacta.
Si un campo no tiene informacion, dejalo como null o lista vacia.

{
  "resumen": "1-2 frases",
  "tema_principal": "string o null",
  "puntos_clave": ["..."],
  "hallazgos_visuales": ["..."],
  "transcripcion_visual": [{"segundo": 0.0, "descripcion": "qué se ve y qué ocurre"}],
  "datos_mencionados": {"...": "..."},
  "fechas_mencionadas": ["..."],
  "acciones": [{"prioridad": "urgente|seguimiento|administrativo", "detalle": "..."}],
  "frases_clave": ["citas textuales importantes del audio"]
}
"""


def perfiles_disponibles():
    """Nombres de perfil validos (uno por archivo .txt en perfiles/)."""
    return sorted(p.stem for p in DIR_PERFILES.glob("*.txt"))


def _cargar_perfil(nombre):
    """Arma el prompt completo para un perfil. Un nombre desconocido o vacio
    cae en PERFIL_DEFECTO sin avisar (no vale la pena romper un mensaje real
    por un caption mal escrito)."""
    if nombre not in perfiles_disponibles():
        nombre = PERFIL_DEFECTO
    rol = (DIR_PERFILES / f"{nombre}.txt").read_text(encoding="utf-8")
    return rol.strip() + "\n\n" + _ESTRUCTURA_JSON


def _cliente():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Cargala en el archivo .env "
            "(sacala de https://aistudio.google.com/apikey)")
    return genai.Client(api_key=api_key)


def analizar(datos, perfil=PERFIL_DEFECTO, incluir_frames=True):
    """
    datos: dict que devuelve core.procesar_archivo (tiene 'transcripcion' y 'frames').
    perfil: nombre de perfil (ver perfiles_disponibles()); default "generico".
    Devuelve un dict con el analisis estructurado.
    """
    client = _cliente()
    prompt = _cargar_perfil(perfil)

    partes = [prompt, "\n\n--- TRANSCRIPCION DEL AUDIO ---\n" + (datos.get("transcripcion") or "(vacia)")]

    if incluir_frames and datos.get("frames"):
        partes.append("\n\n--- FRAMES DEL VIDEO (en orden) ---")
        tiempos = datos.get("frames_tiempos") or []
        for i, ruta in enumerate(datos["frames"]):
            p = Path(ruta)
            if p.exists():
                segundo = float(tiempos[i]) if i < len(tiempos) else float(i * 4)
                partes.append("\nFotograma cerca de %d:%02d:" %
                              (int(segundo // 60), int(segundo % 60)))
                mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
                partes.append(types.Part.from_bytes(data=p.read_bytes(), mime_type=mime))

    resp = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=partes,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    try:
        return json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Gemini no devolvio JSON valido", "crudo": resp.text}


PROMPT_IMAGEN = """Analiza esta imagen y devolve SOLO un JSON con esta estructura:
{
  "descripcion": "que se ve en la imagen, claro y conciso",
  "texto_detectado": "TODO el texto que aparezca en la imagen (OCR), respetando saltos de linea; null si no hay texto"
}
No inventes texto que no este en la imagen."""


def analizar_imagen(ruta):
    """Describe la imagen y extrae su texto (OCR) con Gemini. Devuelve un dict."""
    client = _cliente()
    p = Path(ruta)
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    resp = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=[PROMPT_IMAGEN, types.Part.from_bytes(data=p.read_bytes(), mime_type=mime)],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    try:
        return json.loads(resp.text)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Gemini no devolvio JSON valido", "crudo": resp.text}


def responder_pantalla(img_bytes, pregunta):
    """Le pregunta a Gemini sobre una captura de pantalla. Devuelve texto breve (para voz)."""
    client = _cliente()
    prompt = ("Mira esta captura de pantalla y responde la pregunta en 1 o 2 frases, "
              "en espanol rioplatense, sin markdown ni emojis (se lee en voz alta).\n"
              "Pregunta: " + (pregunta or "Que hay en la pantalla?"))
    resp = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=[prompt, types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")],
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return (resp.text or "").strip()


def ubicar_elemento(img_bytes, descripcion):
    """Le pide a Gemini el bounding box (0-1000, [ymin,xmin,ymax,xmax]) del elemento descrito.
    Devuelve (ymin,xmin,ymax,xmax) o None si no lo encuentra."""
    client = _cliente()
    prompt = (f"En esta captura de pantalla, ubica EXACTAMENTE el elemento: \"{descripcion}\".\n"
              "Respeta el orden visual: 'primero/segundo/tercero' = de arriba hacia abajo y de izquierda a "
              "derecha. Respeta posiciones relativas ('el de abajo', 'a la derecha de', 'arriba'). "
              "Si menciona un texto/titulo, busca el que lo contenga.\n"
              "Devolve SOLO un JSON: {\"box_2d\": [ymin, xmin, ymax, xmax]} normalizado 0-1000 "
              "(origen arriba-izquierda). Si no lo encontras, {\"box_2d\": null}.")
    resp = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=[prompt, types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
    )
    try:
        box = json.loads(resp.text).get("box_2d")
        if box and len(box) == 4:
            return tuple(float(v) for v in box)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def formato_imagen(a):
    """Texto lindo para Telegram a partir del analisis de imagen."""
    if not a or "error" in a:
        return "🖼 No se pudo analizar la imagen."
    L = ["🖼 *Imagen*"]
    if a.get("descripcion"):
        L.append(f"👁 {a['descripcion']}")
    if a.get("texto_detectado"):
        L.append(f"\n📄 Texto detectado:\n{a['texto_detectado']}")
    return "\n".join(L)


def formato_legible(analisis):
    """Convierte el JSON del analisis a un texto lindo para mandar por el bot.
    Mismo formato para cualquier perfil: lo que cambia es el CONTENIDO que
    Gemini extrae, no la forma en que se muestra."""
    if not analisis or "error" in analisis:
        return "No se pudo analizar el contenido."
    L = []
    if analisis.get("resumen"):
        L.append(f"📋 *Resumen:* {analisis['resumen']}")
    if analisis.get("tema_principal"):
        L.append(f"🩺 *Tema:* {analisis['tema_principal']}")
    if analisis.get("puntos_clave"):
        L.append("💬 *Puntos clave:* " + "; ".join(analisis["puntos_clave"]))
    if analisis.get("hallazgos_visuales"):
        L.append("👁 *Se observa:* " + "; ".join(analisis["hallazgos_visuales"]))
    visual = analisis.get("transcripcion_visual") or []
    if visual:
        L.append("*Lo que se ve, en orden:*")
        for v in visual:
            try:
                segundo = max(0, int(float(v.get("segundo") or 0)))
            except (TypeError, ValueError):
                segundo = 0
            descripcion = str(v.get("descripcion") or "").strip()
            if descripcion:
                L.append("  %d:%02d %s" % (segundo // 60, segundo % 60, descripcion))
    if analisis.get("fechas_mencionadas"):
        L.append("📅 *Fechas:* " + "; ".join(analisis["fechas_mencionadas"]))
    acciones = analisis.get("acciones") or []
    if acciones:
        L.append("*Acciones:*")
        emoji = {"urgente": "🔴", "seguimiento": "🟡", "administrativo": "🔵"}
        for a in acciones:
            L.append(f"  {emoji.get(a.get('prioridad'), '•')} {a.get('detalle', '')}")
    return "\n".join(L) if L else "Sin datos relevantes detectados."


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        datos = json.load(f)
    res = analizar(datos)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n" + "=" * 40 + "\n")
    print(formato_legible(res))
