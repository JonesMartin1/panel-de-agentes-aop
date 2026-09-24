"""
Router comun: recibe cualquier archivo (audio/video/imagen) y devuelve el texto
listo para mandar por Telegram. Lo usan el bot de Telegram y el webhook de WhatsApp.
"""

from pathlib import Path
from app.nucleo import core
from app.nucleo import analizar_gemini
from app.nucleo import entrantes


def procesar_a_texto(ruta, perfil=analizar_gemini.PERFIL_DEFECTO,
                     origen="", de="") -> str:
    """perfil: que lente de analisis usar (ver analizar_gemini.perfiles_disponibles()).
    No aplica a imagenes: ahi siempre es descripcion + OCR, no depende del rubro.

    `origen` (el canal: "whatsapp", "telegram", "subida") y `de` (quien lo mando)
    son solo para la ficha del audio guardado — ver mas abajo. Son opcionales: un
    camino que no los pase sigue andando igual, el audio queda con "desconocido".
    """
    ext = Path(ruta).suffix.lower()

    # --- IMAGEN: describir + OCR ---
    if ext in core.EXT_IMAGEN:
        analisis = analizar_gemini.analizar_imagen(ruta)
        return analizar_gemini.formato_imagen(analisis)

    # --- AUDIO / VIDEO: transcribir + analizar ---
    # La cola es visible desde el Estudio aunque este trabajo lo haga otro proceso
    # (WhatsApp o Telegram). No cambiar el flujo de la transcripción por mostrarla.
    cola = entrantes.cola_abrir(ruta, origen=origen, de=de)

    def avanzar(pct, paso):
        if cola:
            # Whisper ocupa la mayor parte; el último tramo queda para Gemini.
            entrantes.cola_actualizar(cola, pct=round(float(pct) * .76), paso=paso)

    try:
        datos, _ = core.procesar_archivo(ruta, progreso=avanzar)
    except Exception as e:
        if cola:
            entrantes.cola_fallar(cola, e)
        raise
    texto = datos.get("transcripcion") or "(no se detecto voz)"

    partes = [f"📝 Transcripcion:\n{texto}"]
    try:
        if cola:
            entrantes.cola_actualizar(cola, pct=84, paso="Haciendo el análisis inteligente…")
        analisis = analizar_gemini.analizar(datos, perfil=perfil)
        if not isinstance(analisis, dict) or analisis.get("error"):
            detalle = analisis.get("error") if isinstance(analisis, dict) else ""
            raise RuntimeError(detalle or "Gemini no devolvió un análisis válido")
        partes.append(analizar_gemini.formato_legible(analisis))
        # ⭐ El Estudio recibe esta copia recién ahora: texto, recortes y Gemini se
        # escriben juntos en una misma ficha. Antes se guardaba primero el audio y
        # unos segundos después el análisis; la bandeja podía mostrarlo a medio hacer.
        guardado = entrantes.guardar(ruta, origen=origen, de=de,
                                     texto=datos.get("transcripcion") or "",
                                     segmentos=datos.get("segmentos"), analisis=analisis)
        if not guardado:
            raise RuntimeError("no se pudo guardar el archivo para el Estudio")
        if cola:
            entrantes.cola_terminar(cola, archivo=guardado,
                                    paso="Texto y análisis listos para editar")
    except Exception as e:
        partes.append(f"(analisis no disponible: {e})")
        if cola:
            entrantes.cola_fallar(cola, e)
    return "\n\n".join(partes)
