"""La charla continua del celular, probada con un microfono de mentira.

Prueba el ciclo entero DEL NAVEGADOR: tocar una vez, detectar que hablaste, cortar
al segundo de silencio, mandar, escuchar la respuesta y volver a escuchar solo.

⚠ El envio a Laura se INTERCEPTA a proposito. Si se dejara pasar, el pedido le
pide un turno a la misma sesion de Claude que esta corriendo esta prueba y se
espera a si misma para siempre (mismo auto-bloqueo que ya paso con el buzon).
Lo que esta prueba cubre es la mitad del navegador; la otra mitad — Whisper, Laura
y la voz de vuelta — ya se prueba sola cuando Martin habla de verdad.

    python -m pruebas.probar_charla_movil
"""
import io
import wave

from playwright.sync_api import sync_playwright

from app.rutas import RAIZ, VOZ_PIPER

BASE = "http://localhost:8750"
FALSO = RAIZ / "pruebas" / "voz_falsa.wav"


def hacer_wav_de_prueba():
    """Una frase dicha por Piper y despues silencio: eso es lo que va a 'oir'
    el navegador. El silencio del final es el que tiene que cerrar la frase."""
    from piper import PiperVoice
    voz = PiperVoice.load(str(VOZ_PIPER))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voz.synthesize_wav("Hola, esto es una prueba de la charla continua.", w)
    buf.seek(0)
    with wave.open(buf, "rb") as r:
        marcos, tasa, ancho, canales = r.readframes(r.getnframes()), r.getframerate(), \
            r.getsampwidth(), r.getnchannels()
    with wave.open(str(FALSO), "wb") as w:
        w.setnchannels(canales); w.setsampwidth(ancho); w.setframerate(tasa)
        w.writeframes(marcos)
        w.writeframes(b"\x00" * ancho * canales * tasa * 4)   # 4 s de silencio
    return FALSO


def wav_corto_b64():
    """Un pitido cortito, para hacer de 'respuesta hablada' sin molestar a Piper."""
    import base64
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(
            int(3000 * math.sin(i * 0.2)).to_bytes(2, "little", signed=True)
            for i in range(4000)))
    return base64.b64encode(buf.getvalue()).decode()


def main():
    archivo = hacer_wav_de_prueba()
    with sync_playwright() as p:
        nav = p.chromium.launch(args=[
            "--use-fake-ui-for-media-stream",              # acepta el permiso solo
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={archivo}"])
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, has_touch=True,
                              is_mobile=True, permissions=["microphone"])
        pag = ctx.new_page()
        errores = []
        pag.on("pageerror", lambda e: errores.append(str(e)))

        pedidos = []
        def responder(ruta, pedido):
            pedidos.append(len(pedido.post_data_buffer or b""))
            ruta.fulfill(status=200, content_type="application/json",
                         body='{"dicho":"Hola, esto es una prueba de la charla continua.",'
                              '"respuesta":"Te escuche fuerte y claro.",'
                              f'"audio_b64":"{wav_corto_b64()}"}}')
        pag.route("**/movil/hablar", responder)

        pag.goto(BASE + "/movil", wait_until="domcontentloaded")
        # ⚠ "Hablar" ya NO es una pestaña de arriba: los cuatro destinos fijos se mudaron
        # a la barra de abajo el 2026-08-16 (donde llega el pulgar), y arriba quedaron
        # solo las sesiones abiertas. La prueba seguía buscándolo en `#tabs` y se
        # quedaba esperando 30 s (visto el 2026-08-17).
        pag.wait_for_selector('#abajo .dest[data-ir="hablar"]', timeout=5000)
        pag.wait_for_timeout(1200)
        pag.locator('#abajo .dest[data-ir="hablar"]').click()
        # Entrar a la pestaña YA tiene que dejarla escuchando: no hay nada que apretar.
        pag.wait_for_function(
            "document.querySelector('#estado') && document.querySelector('#estado').textContent.includes('Te escucho')",
            timeout=15000)
        print("1) entrás y ya te escucha, sin apretar nada: OK")

        alto0 = pag.evaluate("document.querySelector('#onda i').style.height")
        pag.wait_for_function(
            "[...document.querySelectorAll('#onda i')].some(b => parseFloat(b.style.height) > 20)",
            timeout=15000)
        print(f"2) la onda se mueve con tu voz: OK (de {alto0 or '16px'} para arriba)")

        pag.wait_for_function("document.querySelector('#respuesta').textContent.length > 0",
                              timeout=25000)
        print(f"3) cortó la frase sola y la mandó: OK ({pedidos[0]} bytes de audio)")
        print("   me escuchó:", pag.locator("#dicho").text_content())

        pag.wait_for_function(
            "document.querySelector('#estado').textContent.includes('Te escucho')",
            timeout=20000)
        print("4) después de contestar vuelve a escuchar solo: OK")

        pag.click("#colgar")
        pag.wait_for_function(
            "document.querySelector('#estado').textContent.includes('Cortaste')", timeout=5000)
        print("5) el botón rojo corta la llamada: OK")
        print("errores de javascript:", errores or "ninguno")
        nav.close()
    archivo.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
