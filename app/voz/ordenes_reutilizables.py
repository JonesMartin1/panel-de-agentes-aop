"""Procedimientos repetibles que Martín puede pedirle a Laura con una frase corta.

No ejecutan nada por su cuenta: convierten una orden inequívoca en una instrucción
completa para el cerebro grande. Así Claude y Codex siguen las mismas etapas y las
reglas normales de confirmación continúan vigentes.
"""

import re
import unicodedata


def _plano(texto):
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


ORDENES = (
    {
        "nombre": "revisar el proyecto",
        "patrones": ("revisa este proyecto", "revisame este proyecto",
                      "ejecuta revision del proyecto", "usa revision del proyecto"),
        "instruccion": (
            "Ejecutá el procedimiento reutilizable 'revisar el proyecto': leé primero "
            "las instrucciones y el mapa existentes; mirá el estado actual, los cambios "
            "sin guardar, las pruebas y los riesgos principales. Es solo diagnóstico: no "
            "modifiques archivos. Al final dame un resumen hablado y ofrecé el detalle."
        ),
    },
    {
        "nombre": "correr las pruebas",
        "patrones": ("corre las pruebas", "ejecuta las pruebas", "proba el proyecto",
                      "usa correr las pruebas"),
        "instruccion": (
            "Ejecutá el procedimiento reutilizable 'correr las pruebas': leé las "
            "instrucciones del proyecto, identificá las pruebas relevantes para los "
            "cambios actuales, corré primero las específicas y después las generales si "
            "corresponde. No modifiques código. Informame qué pasó en una frase hablada."
        ),
    },
    {
        "nombre": "buscar errores",
        "patrones": ("busca errores", "buscame errores", "revisa si hay errores",
                      "usa buscar errores"),
        "instruccion": (
            "Ejecutá el procedimiento reutilizable 'buscar errores': revisá los cambios "
            "actuales buscando fallas reales, regresiones, problemas de seguridad y casos "
            "sin cubrir. Confirmá cada hallazgo con evidencia y no modifiques nada. "
            "Contame primero lo más importante, en formato hablado."
        ),
    },
)

_LISTAR = {
    "que ordenes de voz hay", "que funciones de voz hay", "que funciones reutilizables hay",
    "que ordenes reutilizables hay", "decime las ordenes de voz",
    "decime las ordenes reutilizables", "lista las ordenes de voz",
    "lista las ordenes reutilizables",
}


def resolver(texto):
    """Devuelve (instrucción, respuesta_local); ambas vacías si no era una orden."""
    plano = _plano(texto)
    if plano in _LISTAR:
        nombres = ", ".join(o["nombre"] for o in ORDENES)
        return "", "Tengo estas órdenes: " + nombres + "."
    for orden in ORDENES:
        if plano in orden["patrones"]:
            return orden["instruccion"], ""
    return "", ""
