"""¿Se ve de un vistazo qué charlas corren con OTRA cuenta de Claude, y se puede elegir?

Pedido de Martín (2026-11-16): *"quiero poder diferenciar en el panel las sesiones que son de
esta cuenta y las que no"*, y después *"que se vean de otra manera, poder integrarlo con
todo el panel"*: la charla del servidor vive ADENTRO del proyecto, se elige al escribir como
se elige Claude o Codex, y lleva las tres marcas (chapa, tinte e ícono en la luz).

Con datos de mentira —un proyecto preparado en un servidor de OTRA cuenta, con una charla
de allá entre las comunes, uno sin preparar, y el cajón de un servidor con la MISMA cuenta—:
  1. las charlas comunes no llevan ninguna marca;
  2. la del servidor lleva la chapa "servidor" (sin el nombre de la cuenta, ni siquiera en
     el cartelito), tinte, y una nube en el lugar de la luz que toma el color del estado;
  3. su pestaña lleva chapa y tinte;
  4. en una charla sin estrenar del proyecto preparado el selector ofrece "Servidor",
     elegirlo marca la pestaña y esconde el modelo; en un proyecto sin preparar no aparece;
  5. una charla nacida no se puede mudar de cuenta desde el selector;
  6. con la misma cuenta en otra máquina: la chapa "servidor" en gris, sin tinte;
  7. la página no tira ningún error.
`--mutar` rompe cada pieza y exige que se note. Usa el armado de `ver_vbandeja`
(página del disco, datos de mentira; panel prendido en 8750).
"""
import copy
import sys

from playwright.sync_api import sync_playwright

from pruebas import ver_vbandeja as vb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AJENA = {"maquina": "servidor-uno", "mail": "socio@ejemplo.com", "propia": False}
PROPIA = {"maquina": "servidor-dos", "mail": "yo@ejemplo.com", "propia": True}


def datos():
    d = copy.deepcopy(vb.SESIONES)
    alfa = d["proyectos"][0]
    alfa["servidores"] = [dict(AJENA, fijo=False)]
    alfa["sesiones"].insert(0, vb.ses("alfa-rem", "tarea en el servidor", 15, cuenta=AJENA,
                                      ocupada=True, detalle="activa, recién"))
    d["proyectos"].append({"proyecto": "servidor-dos", "cwd": "D:\\pruebas\\servidor-dos",
                           "vivo": False, "manual": True, "cuenta": PROPIA,
                           "servidores": [dict(PROPIA, fijo=True)], "sesiones": [
                               vb.ses("mia-1", "con mi cuenta", 70, cuenta=PROPIA),
                               vb.ses("mia-2", "otra con mi cuenta", 700, cuenta=PROPIA)]})
    d["carpetas"] = {"orden": ["alfa", "beta", "servidor-dos"], "ocultas": []}
    return d


FILAS = """() => [...document.querySelectorAll('#colCharlas .cc-it')].map(x => {
  const c = x.querySelector('.cer.cta'), n = x.querySelector('.cc-luz .nube');
  return {sid: x.dataset.sid, chapa: c ? c.textContent : null,
          chapaGris: !!c && c.classList.contains('propia'), titulo: c ? c.title : '',
          tinte: getComputedStyle(x).backgroundImage !== 'none',
          marcada: x.classList.contains('otra-cta'),
          nube: !!n, nubeEstado: n ? [...n.classList].filter(k => k !== 'nube').join(' ') : '',
          punto: !!x.querySelector('.cc-luz .ast')}; })"""

PESTANA = """() => { const t = document.querySelector('.tab.sel');
  if (!t) return null; const c = t.querySelector('.cer.cta');
  return {chapa: c ? c.textContent : null, marcada: t.classList.contains('otra-cta')}; }"""

SELECTOR = """() => { const s = document.getElementById('cerebro'), m = document.getElementById('modelo');
  return {opciones: [...s.options].map(o => o.value + '=' + o.textContent), valor: s.value,
          modeloVisible: !!m && m.style.display !== 'none',
          cerebroTab: (abiertas.find(x => x.sid === activa) || {}).cerebro || ''}; }"""


def correr(nav, cambios=None, foto=False):
    fallas = []
    original = vb.SESIONES
    vb.SESIONES = datos()
    try:
        ctx, pag, err = vb.montar(nav, "vbandeja", cambios, abrir=False)

        def abrir(sid, carpeta, nombre):
            pag.evaluate("([sid, cwd, nombre]) => { abiertas = [{sid, cwd, nombre, cerebro: ''}];"
                         " irTab(sid); }", [sid, "D:\\pruebas\\" + carpeta, nombre])
            pag.wait_for_timeout(700)

        def elegir(valor):
            pag.evaluate("v => { const s = document.getElementById('cerebro'); s.value = v;"
                         " s.dispatchEvent(new Event('change')); }", valor)
            pag.wait_for_timeout(500)

        # 1-3. Una charla del servidor entre las comunes del mismo proyecto.
        abrir("alfa-rem", "alfa", "tarea en el servidor")
        filas = {f["sid"]: f for f in pag.evaluate(FILAS)}
        rem, comunes = filas.get("alfa-rem"), [f for k, f in filas.items() if k != "alfa-rem"]
        if not comunes or any(f["chapa"] or f["tinte"] or f["nube"] or f["marcada"] for f in comunes):
            fallas.append("una charla común lleva alguna marca de cuenta (o no hay filas): %r" % comunes[:2])
        if not rem:
            fallas.append("la charla del servidor no aparece entre las del proyecto")
        else:
            if rem["chapa"] != "servidor" or rem["chapaGris"] or "NO es la cuenta" not in rem["titulo"]:
                fallas.append("la chapa de la charla ajena está mal: %r" % rem)
            if "socio" in rem["titulo"] or "servidor-uno" not in rem["titulo"]:
                fallas.append("el cartelito tiene que decir la máquina y no el nombre de la cuenta: %r"
                              % rem["titulo"])
            if not rem["marcada"]:
                fallas.append("la fila de la charla ajena no lleva la marca del tinte")
            if not rem["nube"] or rem["punto"]:
                fallas.append("la luz de la charla ajena no es la nube: %r" % rem)
            elif "trabajando" not in rem["nubeEstado"]:
                fallas.append("la nube no toma el estado de la charla (trabajando): %r" % rem["nubeEstado"])
        tab = pag.evaluate(PESTANA)
        if not tab or tab["chapa"] != "servidor" or not tab["marcada"]:
            fallas.append("la pestaña de la charla ajena no lleva chapa y tinte: %r" % tab)
        if foto:
            pag.screenshot(path=str(vb.SALIDA / "cuenta_remota.png"),
                           clip={"x": 0, "y": 0, "width": 980, "height": 420})

        # 5. Una charla nacida no se muda de cuenta.
        elegir("")
        sel = pag.evaluate(SELECTOR)
        if sel["valor"] != "servidor:servidor-uno":
            fallas.append("una charla nacida en el servidor se dejó pasar a Claude local: %r" % sel["valor"])
        abrir("alfa-1", "alfa", "arreglar el login")
        # El tinte se mira con OTRA charla abierta: la elegida lleva el color de selección.
        otra = {f["sid"]: f for f in pag.evaluate(FILAS)}.get("alfa-rem") or {}
        if not otra.get("tinte"):
            fallas.append("la fila de la charla ajena no lleva tinte: %r" % otra)
        elegir("servidor:servidor-uno")
        sel = pag.evaluate(SELECTOR)
        if sel["valor"] != "" or pag.evaluate(PESTANA)["marcada"]:
            fallas.append("una charla común nacida se dejó mudar al servidor: %r" % sel["valor"])

        # 4. Sin estrenar: en el proyecto preparado se puede elegir; en el otro no.
        abrir("nueva-1", "alfa", "Nueva")
        # El panel de mentira no devuelve modelos: se ponen a mano para poder ver si se esconden.
        pag.evaluate("() => { modelos = [{id: 'uno', nombre: 'Uno'}]; pintarModelo(); }")
        sel = pag.evaluate(SELECTOR)
        if "servidor:servidor-uno=Servidor" not in sel["opciones"]:
            fallas.append("el selector no ofrece el servidor en un proyecto preparado: %r" % sel["opciones"])
        elif sel["valor"] != "" or not sel["modeloVisible"]:
            fallas.append("una charla nueva no arranca en Claude de acá: %r" % sel)
        else:
            elegir("servidor:servidor-uno")
            sel, tab = pag.evaluate(SELECTOR), pag.evaluate(PESTANA)
            if sel["cerebroTab"] != "servidor:servidor-uno" or sel["valor"] != "servidor:servidor-uno":
                fallas.append("elegir el servidor no quedó en la pestaña: %r" % sel)
            if sel["modeloVisible"]:
                fallas.append("con el servidor elegido se sigue mostrando el modelo de acá")
            if not tab or tab["chapa"] != "servidor" or not tab["marcada"]:
                fallas.append("la pestaña sin estrenar no se marca al elegir el servidor: %r" % tab)
            elegir("")
            sel = pag.evaluate(SELECTOR)
            if sel["cerebroTab"] != "" or pag.evaluate(PESTANA)["marcada"]:
                fallas.append("no se puede volver a Claude de acá antes de mandar: %r" % sel)
        abrir("nueva-2", "beta", "Nueva")
        sel = pag.evaluate(SELECTOR)
        if any(o.startswith("servidor:") for o in sel["opciones"]):
            fallas.append("el selector ofrece el servidor en un proyecto SIN preparar: %r" % sel["opciones"])

        # 6. La misma cuenta en otra máquina.
        abrir("mia-1", "servidor-dos", "con mi cuenta")
        propias = pag.evaluate(FILAS)
        # Se mira también la que NO está abierta: la elegida no lleva tinte nunca.
        if ([(f["chapa"], f["chapaGris"], f["tinte"], f["nube"]) for f in propias]
                != [("servidor", True, False, True)] * 2):
            fallas.append("con tu misma cuenta en otra máquina: chapa gris, sin tinte, con nube. Hay: %r" % propias)
        if err:
            fallas.append("la página tiró errores: %r" % err[:2])
        ctx.close()
    finally:
        vb.SESIONES = original
    return fallas


MUTACIONES = [
    ("sacarle la chapa a las filas",
     {"sesiones.html": [("(s.cerebro === 'codex' ? ' · Codex' : '') + chapaCuenta(s.cuenta) + '</b>'",
                         "(s.cerebro === 'codex' ? ' · Codex' : '') + '</b>'")]}),
    ("sacarle el tinte a las filas",
     {"sesiones.html": [("function claseCuenta(c){ return c ? ' otra-cta'", "function claseCuenta(c){ return false ? ' otra-cta'")]}),
    ("dejar el punto de siempre en vez de la nube",
     {"sesiones.html": [("(s.cuenta ? nubeCuenta(s.cuenta, e === 'preguntando' ? 'preguntando' : e)",
                         "(false ? nubeCuenta(s.cuenta, e === 'preguntando' ? 'preguntando' : e)")]}),
    ("que la nube no tome el estado",
     {"sesiones.html": [("(c.propia ? ' propia' : '') + (estado ? ' ' + estado : '') +",
                         "(c.propia ? ' propia' : '') +")]}),
    ("sacarle la chapa a la pestaña",
     {"sesiones.html": [("chapaCuenta(cuentaDeTab(t)) +\n", "\n")]}),
    ("no ofrecer el servidor en el selector",
     {"sesiones.html": [("      sv.forEach(x => {\n        const o = document.createElement('option');",
                         "      [].forEach(x => {\n        const o = document.createElement('option');")]}),
    ("dejar mudar de cuenta una charla nacida",
     {"sesiones.html": [("  if (haciaSrv || cuentaDeTab(t)){", "  if (false){")]}),
    ("pintar la misma cuenta igual que la ajena",
     {"sesiones.html": [("function claseCuenta(c){ return c ? ' otra-cta' + (c.propia ? ' propia' : '') : ''; }",
                         "function claseCuenta(c){ return c ? ' otra-cta' : ''; }")]}),
    ("escribir el nombre de la cuenta en la chapa",
     {"sesiones.html": [("'\">servidor</span>';",
                         "'\">' + esc((c.mail || '').split('@')[0]) + '</span>';")]}),
    ("no avisar que la cuenta no es la tuya",
     {"sesiones.html": [("': NO es la cuenta de esta compu'", "''")]}),
]


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        fallas = correr(nav, foto=True)
        for f in fallas:
            print("  MAL  " + f)
        if fallas:
            nav.close()
            return 1
        print("  ok   la cuenta se elige al escribir y la charla del servidor se distingue (chapa, tinte, nube)")
        mal = 0
        if "--mutar" in sys.argv:
            for titulo, cambios in MUTACIONES:
                r = correr(nav, cambios)
                if r:
                    print("  ok   rompí '%s' y lo cazó: %s" % (titulo, r[0][:90]))
                else:
                    print("  MAL  rompí '%s' y NO lo notó nadie" % titulo)
                    mal += 1
            print("%d mutaciones, %d sin cazar" % (len(MUTACIONES), mal))
        nav.close()
        return 1 if mal else 0


if __name__ == "__main__":
    sys.exit(main())
