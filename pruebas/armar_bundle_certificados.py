"""Arma el paquete de certificados que usa el CLI de Codex.

Por que existe: esta laptop tiene Avast inspeccionando el HTTPS, asi que los
servidores le presentan a Codex un certificado firmado por Avast. Python lo
resuelve con `truststore` y Node con NODE_EXTRA_CA_CERTS, pero el `codex` de
verdad es un binario Rust: no mira ninguna de las dos cosas y corta el stream a
la mitad con "invalid peer certificate: UnknownIssuer" (paso el 2026-08-22 y
tiraba a Laura de Codex a Claude en pleno turno).

La variable que ese binario SI lee es SSL_CERT_FILE, pero apunta a UN archivo que
reemplaza a todas las raices. Por eso hay que juntar todo en uno solo: las raices
de siempre (certifi), las del almacen de Windows y la de Avast.

Correr esto de nuevo si Avast rota su raiz o si Codex vuelve a quejarse del
certificado:

    python -m pruebas.armar_bundle_certificados
"""

import ssl
import certifi
from pathlib import Path

from app.rutas import CERT_NODE_CODEX, CERT_BUNDLE_CODEX


def armar():
    partes = [Path(certifi.where()).read_text(encoding="utf-8")]
    vistos = set()
    de_windows = 0
    for tienda in ("ROOT", "CA"):
        try:
            certificados = ssl.enum_certificates(tienda)
        except Exception:
            continue
        for der, _enc, confianza in certificados:
            # Solo las que Windows marca como validas para servidores web.
            sirve = confianza is True or (
                isinstance(confianza, set)
                and any("1.3.6.1.5.5.7.3.1" in str(u) for u in confianza))
            if not sirve or der in vistos:
                continue
            vistos.add(der)
            partes.append(ssl.DER_cert_to_PEM_cert(der))
            de_windows += 1

    # La de Avast va si o si, aunque no este en el almacen de Windows.
    if CERT_NODE_CODEX.exists():
        avast = CERT_NODE_CODEX.read_text(encoding="utf-8").strip()
        if avast and avast not in "\n".join(partes):
            partes.append(avast + "\n")

    CERT_BUNDLE_CODEX.parent.mkdir(parents=True, exist_ok=True)
    CERT_BUNDLE_CODEX.write_text("\n".join(partes), encoding="utf-8")
    total = "\n".join(partes).count("BEGIN CERTIFICATE")
    print(f"listo: {CERT_BUNDLE_CODEX} ({total} certificados, "
          f"{de_windows} del almacen de Windows)")


if __name__ == "__main__":
    armar()
