"""El uso del plan de Claude: el módulo y la pastilla del menú, sin hablar con Anthropic.

Pedido de Martín (2026-11-12): *"me gustaría ver en todo momento mi uso de claude"*.
- El módulo (`app/nucleo/uso_claude.py`) se prueba con respuestas de mentira, armadas con
  la forma REAL que contestó Anthropic ese día (`limits` + `five_hour`/`seven_day`).
- ⚠⚠ Se exige que el módulo NUNCA renueve la llave ni la escriba: renovarla rotaría el
  refresh token y dejaría a Claude Code deslogueado.
- La pastilla (`menu.js`) se mira en /sesiones con `/uso-claude` simulado: normal, alto,
  sin dato, panel sin reiniciar (404) y columnas anchas (pasa a la versión corta y entra).
`--mutar` rompe cada regla a propósito y exige que la prueba la cace.
Necesita el panel prendido en 8750 (para servir la página), no toca su endpoint real.
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

from playwright.sync_api import sync_playwright

from app.nucleo import uso_claude
from app.rutas import RAIZ
from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FUENTE = RAIZ / "app" / "nucleo" / "uso_claude.py"

# La forma que contestó Anthropic el 2026-11-12 (recortada), más una ventana de 5 h.
REAL = {"five_hour": {"utilization": 12.0, "resets_at": "2026-11-12T08:00:00+00:00"},
        "seven_day": {"utilization": 48.0, "resets_at": "2026-11-17T09:59:59+00:00"},
        "limits": [{"kind": "weekly_all", "group": "weekly", "percent": 48, "severity": "normal",
                    "resets_at": "2026-11-17T09:59:59+00:00", "scope": None, "is_active": True},
                   {"kind": "weekly_scoped", "group": "weekly", "percent": 45, "severity": "normal",
                    "resets_at": "2026-11-17T09:59:59+00:00",
                    "scope": {"model": {"id": None, "display_name": "Fable"}}, "is_active": False}]}


class Resp:
    def __init__(self, status, cuerpo):
        self.status_code, self._c = status, cuerpo
        self.ok = 200 <= status < 300

    def json(self):
        return self._c


def probar_modulo(fuente_mutada=None):
    fallas = []
    mod = uso_claude
    if fuente_mutada is not None:
        import types
        mod = types.ModuleType("uso_mutado")
        exec(compile(fuente_mutada, "uso_mutado", "exec"), mod.__dict__)
    with tempfile.TemporaryDirectory() as d:
        cred = Path(d) / ".credentials.json"
        bueno = {"claudeAiOauth": {"accessToken": "llave-de-mentira", "refreshToken": "r",
                                   "expiresAt": (time.time() + 3600) * 1000}}
        cred.write_text(json.dumps(bueno), encoding="utf-8")
        antes = cred.read_text(encoding="utf-8")
        pedidos = []

        def get(url, **kw):
            pedidos.append(("GET", url, kw.get("headers", {})))
            return Resp(200, REAL)

        def post(url, **kw):
            pedidos.append(("POST", url, kw.get("headers", {})))
            return Resp(200, {})

        with mock.patch.object(mod, "CREDENCIALES_CLAUDE", cred), \
             mock.patch.object(mod.requests, "get", side_effect=get), \
             mock.patch.object(mod.requests, "post", side_effect=post):
            mod._CACHE.update(ts=0.0, r=None)
            r = mod.uso(forzar=True)
            nombres = [(l["nombre"], l["pct"], l["activo"]) for l in r.get("limites", [])]
            if nombres != [("5 horas", 12, True), ("Semana", 48, True), ("Semana · Fable", 45, False)]:
                fallas.append("los límites no salen como en /usage: %s" % nombres)
            if not pedidos or pedidos[0][2].get("Authorization") != "Bearer llave-de-mentira":
                fallas.append("no le preguntó a Anthropic con la llave de la sesión")
            # Cache: un segundo pedido enseguida no vuelve a salir a internet.
            n = len(pedidos)
            mod.uso()
            if len(pedidos) != n:
                fallas.append("no guarda la respuesta: cada pantalla saldría a preguntar")
            # Llave vencida: no se pregunta y, sobre todo, NO se renueva.
            vencida = dict(bueno, claudeAiOauth=dict(bueno["claudeAiOauth"], expiresAt=(time.time() - 60) * 1000))
            cred.write_text(json.dumps(vencida), encoding="utf-8")
            antes = cred.read_text(encoding="utf-8")
            mod._CACHE.update(ts=0.0, r=None)
            pedidos.clear()
            r = mod.uso(forzar=True)
            if r.get("ok") or pedidos:
                fallas.append("con la llave vencida igual salió a preguntar o a renovarla: %s" % pedidos)
            if cred.read_text(encoding="utf-8") != antes:
                fallas.append("⚠ el módulo ESCRIBIÓ el archivo de la sesión de Claude Code")
            # 429 con un dato bueno de antes: devuelve el viejo, marcado.
            cred.write_text(json.dumps(bueno), encoding="utf-8")
            mod._CACHE.update(ts=0.0, r=None)
            mod.uso(forzar=True)
            with mock.patch.object(mod.requests, "get", return_value=Resp(429, {})):
                r = mod.uso(forzar=True)
            if not (r.get("ok") and r.get("viejo")):
                fallas.append("con un 429 no devolvió el último dato marcado como viejo: %s" % r)
            if any(p[0] == "POST" for p in pedidos):
                fallas.append("⚠ el módulo hizo un POST (¿renovar la llave?)")
    # Y en el texto: nada de renovar.
    texto = fuente_mutada if fuente_mutada is not None else FUENTE.read_text(encoding="utf-8")
    codigo = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("#"))
    codigo = codigo.split('"""', 2)[-1]            # sin el docstring de arriba
    if "refreshToken" in codigo or "requests.post" in codigo or "write_text" in codigo:
        fallas.append("⚠ el módulo toca el refresh token, hace POST o escribe archivos")
    return fallas


def probar_pastilla(nav, respuesta, cambios=None):
    """Devuelve lo que se ve de la pastilla con `/uso-claude` contestando `respuesta`."""
    ctx, pag, err = vb.montar(nav, "vbandeja", cambios, abrir=True)

    def ruta(r):
        if respuesta == 404:
            return r.fulfill(status=404, body="no")
        r.fulfill(status=200, content_type="application/json", body=json.dumps(respuesta))
    pag.route("**/uso-claude*", ruta)
    pag.evaluate("() => document.getElementById('menuPantallas').querySelector('.uso').click()")
    pag.wait_for_timeout(700)
    v = pag.evaluate("""() => { const e = document.querySelector('#menuPantallas .uso');
      const c = document.getElementById('menuPantallas'), b = document.getElementById('barraArriba');
      const vis = x => !!x && getComputedStyle(x).display !== 'none' && x.getBoundingClientRect().width > 0;
      return {ve: vis(e), texto: e ? e.innerText.replace(/\\s+/g, ' ').trim() : '', clase: e ? e.className : '',
              titulo: e ? e.title : '', cabe: c.getBoundingClientRect().right <= b.getBoundingClientRect().right + 1,
              compacto: c.classList.contains('compacto')}; }""")
    return ctx, pag, err, v


def bien(pct5, pctsem, fable_activo=False):
    return {"ok": True, "viejo": False, "ts": 0, "limites": [
        {"clave": "five_hour", "nombre": "5 horas", "pct": pct5, "renueva": "2026-11-12T08:00:00+00:00", "nivel": "normal", "activo": True},
        {"clave": "weekly_all", "nombre": "Semana", "pct": pctsem, "renueva": "2026-11-17T09:59:59+00:00", "nivel": "normal", "activo": True},
        {"clave": "weekly_scoped", "nombre": "Semana · Fable", "pct": 45, "renueva": "2026-11-17T09:59:59+00:00", "nivel": "normal", "activo": fable_activo}]}


def probar_pantalla(nav, cambios=None):
    fallas = []
    ctx, pag, err, v = probar_pastilla(nav, bien(12, 48), cambios)
    if not (v["ve"] and "5 horas 12 %" in v["texto"] and "Semana 48 %" in v["texto"] and "Fable" not in v["texto"]):
        fallas.append("normal: la pastilla no dice los límites que corren: %s" % v)
    if "alto" in v["clase"] or "tope" in v["clase"]:
        fallas.append("normal: la pastilla está pintada sin motivo (%s)" % v["clase"])
    if "Fable: 45 %" not in v["titulo"] or "se renueva" not in v["titulo"]:
        fallas.append("el globito no trae todos los límites con su renovación: %s" % v["titulo"])
    if not v["cabe"]:
        fallas.append("con la pastilla, el menú de arriba quedó cortado")
    # Columnas anchas: el menú se achica y la pastilla pasa a la versión corta, sin cortarse.
    pag.evaluate("() => { ensancharRiel(true); colW = 520; aplicarAnchos(); }")
    pag.wait_for_timeout(400)
    v2 = pag.evaluate("""() => { const e = document.querySelector('#menuPantallas .uso');
      const c = document.getElementById('menuPantallas'), b = document.getElementById('barraArriba');
      return {texto: e.innerText.replace(/\\s+/g, ' ').trim(), compacto: c.classList.contains('compacto') || c.classList.contains('mini'),
              cabe: c.getBoundingClientRect().right <= b.getBoundingClientRect().right + 1}; }""")
    if not (v2["compacto"] and v2["cabe"] and v2["texto"] == "sem 48 %"):
        fallas.append("con las columnas anchas la pastilla no pasó a la versión corta o se cortó: %s" % v2)
    pag.screenshot(path=str(vb.SALIDA / "uso_claude_angosto.png"), clip={"x": 600, "y": 0, "width": 900, "height": 60})
    # ⭐ La regla de verdad: en NINGÚN ancho el menú (con la pastilla) queda cortado. Se
    # recorre de a 12 px, que es donde una medida vieja (sin la pastilla) se equivoca.
    cortes = pag.evaluate("""async () => {
      const malos = [], espera = () => new Promise(r => setTimeout(r, 60));
      for (let w = 240; w <= 640; w += 12) {
        colW = w; aplicarAnchos(); await espera();
        const c = document.getElementById('menuPantallas'), b = document.getElementById('barraArriba');
        if (c.getBoundingClientRect().right > b.getBoundingClientRect().right + 1) malos.push(w);
      }
      return malos; }""")
    if cortes:
        fallas.append("con la lista en estos anchos el menú queda cortado: %s" % cortes)
    if err:
        fallas.append("errores en la página: " + "; ".join(err))
    ctx.close()
    ctx, pag, err, v = probar_pastilla(nav, bien(12, 86), cambios)
    if "alto" not in v["clase"]:
        fallas.append("al 86 %% la pastilla no avisa (clase %s)" % v["clase"])
    pag.screenshot(path=str(vb.SALIDA / "uso_claude.png"), clip={"x": 450, "y": 0, "width": 1050, "height": 60})
    ctx.close()
    ctx, pag, err, v = probar_pastilla(nav, {"ok": False, "motivo": "la sesión venció"}, cambios)
    if not (v["ve"] and "Claude ?" in v["texto"] and "venció" in v["titulo"]):
        fallas.append("sin dato no lo dice: %s" % v)
    ctx.close()
    ctx, pag, err, v = probar_pastilla(nav, 404, cambios)
    if v["ve"]:
        fallas.append("con el panel sin reiniciar (404) la pastilla igual aparece")
    ctx.close()
    return fallas


MUTA_MODULO = {
    "renueva la llave vencida": (
        "        return None, \"la sesión de Claude Code venció; se renueva sola cuando lo usás\"",
        "        requests.post('https://console.anthropic.com/v1/oauth/token', json={'refresh_token': o.get('refreshToken')})\n"
        "        return None, \"la sesión de Claude Code venció; se renueva sola cuando lo usás\""),
    "no guarda la respuesta": ("if not forzar and _CACHE[\"r\"]", "if False and _CACHE[\"r\"]"),
    "con 429 no devuelve el viejo": ("return _viejo_o({\"ok\": False, \"motivo\": \"Anthropic pidió esperar un rato\"})",
                                     "return {\"ok\": False, \"motivo\": \"Anthropic pidió esperar un rato\"}"),
}
MUTA_PANTALLA = {
    "la pastilla muestra también los límites que no corren": (
        "const corren = r.limites.filter(l => l.activo);", "const corren = r.limites;"),
    "no avisa al acercarse al tope": ("l.pct >= 80 ||", "l.pct >= 101 ||"),
    "no se vuelve a medir al cambiar": ("if (antes !== el.innerHTML + el.className) { anchos = null; acomodar(); }", ""),
}


def main():
    mutar = "--mutar" in sys.argv
    malas = []
    f = probar_modulo()
    for x in f:
        print("FALLA (módulo):", x)
    malas += f
    menu = (RAIZ / "app" / "estaticos" / "menu.js").read_text(encoding="utf-8")
    with sync_playwright() as p:
        nav = p.chromium.launch()
        f = probar_pantalla(nav)
        for x in f:
            print("FALLA (pastilla):", x)
        malas += f
        print("Uso del plan de Claude:", "todo bien" if not malas else "%d fallas" % len(malas))
        if mutar:
            fuente = FUENTE.read_text(encoding="utf-8")
            for nombre, (viejo, nuevo) in MUTA_MODULO.items():
                assert viejo in fuente, nombre
                cazada = bool(probar_modulo(fuente.replace(viejo, nuevo)))
                print(("cazada   " if cazada else "NO CAZADA") + " · " + nombre)
                if not cazada:
                    malas.append(nombre)
            for nombre, (viejo, nuevo) in MUTA_PANTALLA.items():
                assert viejo in menu, nombre
                # `ver_vbandeja.montar` sirve menu.js del disco con estos cambios en el camino:
                # el archivo de verdad no se toca.
                cazada = bool(probar_pantalla(nav, {"menu.js": [(viejo, nuevo)]}))
                print(("cazada   " if cazada else "NO CAZADA") + " · " + nombre)
                if not cazada:
                    malas.append(nombre)
        nav.close()
    sys.exit(1 if malas else 0)


if __name__ == "__main__":
    main()
