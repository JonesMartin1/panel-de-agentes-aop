"""El ciclo de testing adversarial, sin gastar un solo token.

    python -m pruebas.probar_adversarial
    python -m pruebas.probar_adversarial --mutar

No llama a ningun CLI, no toca la GPU, no manda ningun Telegram y no escribe en
`resultados/`: le tapa la boca a `sesiones_movil.mandar`, al aviso y al `git diff`, y
mira que hizo el orquestador con lo que le contestaron.

Lo que se verifica son las reglas que Martin decidio el 2026-08-29, no el codigo:

  1. Un hallazgo sin EVIDENCIA no cuenta, lo firme quien lo firme.
  2. El informe vacio es una respuesta valida: sin hallazgos, verde.
  3. Dos vueltas y recien ahi el empate.
  4. El telefono suena UNA vez y SOLO en el empate.
  5. El aviso dice QUE se discute, no "hay una decision pendiente".
  6. Los revisores nacen de contexto limpio; el implementador conserva su charla.
  7. El expediente lo escribe el que MIRO, y lo guarda este modulo: el que
     implementa no tiene por donde tocarlo.
  8. El navegador es de Claude; los lectores van por Codex.

⭐ Con `--mutar` se rompe cada una a proposito y se exige que el chequeo la cace: un
chequeo que no puede fallar es un adorno (misma idea que `probar_no_romper`).
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.voz import adversarial as adv

# Lo que contesta cada papel, segun el guion que pida el caso.
EXPEDIENTE_ROJO = ("HALLAZGO: el boton Guardar no guarda\n"
                   "EVIDENCIA: abri /alta, complete el formulario, aprete Guardar y la "
                   "lista siguio vacia\n"
                   "ESCENARIO: dado un alta valida, cuando guardo, entonces aparece\n")
EXPEDIENTE_VERDE = "VERDE\n"
# Una opinion sin respaldo: es exactamente lo que el metodo NO acepta.
LECTOR_SIN_EVIDENCIA = "HALLAZGO: el codigo me parece fragil\n"


class Espia:
    """Se pone en lugar de `sesiones_movil.mandar` y anota cada turno pedido."""

    def __init__(self, guion):
        self.guion = guion          # {"mirador": [...], "lector": [...]}
        self.turnos = []            # (papel, sid, cerebro, texto)
        self.vuelta_mirador = 0

    def papel_de(self, texto):
        if "Abri el sistema en el navegador" in texto:
            return "mirador"
        if "revisor adversarial numero" in texto:
            return "lector"
        return "implementador"

    def __call__(self, cwd, sid, texto, modelo="", cerebro="", esfuerzo="",
                 velocidad="", al_nacer=None):
        papel = self.papel_de(texto)
        self.turnos.append({"papel": papel, "sid": sid, "cerebro": cerebro,
                            "texto": texto})
        if papel == "mirador":
            respuestas = self.guion["mirador"]
            i = min(self.vuelta_mirador, len(respuestas) - 1)
            self.vuelta_mirador += 1
            return respuestas[i], "sid-mirador-%d" % self.vuelta_mirador
        if papel == "lector":
            return self.guion.get("lector", "VERDE\n"), "sid-lector"
        return "listo, lo toque", (sid or "sid-implementador")


class EspiaAviso:
    def __init__(self):
        self.avisos = []

    def __call__(self, texto, proyecto):
        self.avisos.append({"texto": texto, "proyecto": proyecto})
        return True


# ⭐⭐ EL CANDADO, y esta primero porque es la leccion mas cara de este archivo
# (2026-08-29). Hasta hoy el pizarron se tapaba dentro de `correr()`, o sea POR CORRIDA,
# y eso dejaba afuera todo lo que no pasa por ahi: `resolver()` llamado derecho desde la
# suite, y —peor— el HILO que larga `arrancar()`, que sigue vivo despues del `finally` y
# escribe cuando el tapado ya se levanto. Resultado real: correr esta prueba le colgaba
# papelitos al pizarron DE VERDAD de Martin. Se junto tanto que la pizarra se le hizo
# ilegible, y asi fue como se descubrio — no lo cazo ningun chequeo.
# Ahora el tapado es GLOBAL a toda la suite y ademas ANOTA cada intento: un camino nuevo
# que se olvide de taparlo no ensucia nada y encima sale en rojo por `_FUGAS`.
_FUGAS = []


def _sin_panel(ruta, datos=None, metodo=None):
    """El panel de verdad, tapiado. Anota el intento y no habla con nadie."""
    _FUGAS.append(ruta)
    if ruta == "/pizarra/estado":
        return {"items": []}
    return {"ok": True, "id": 0}


def _esperar(condicion, segundos=5.0):
    """Espera a que pase algo de verdad, no a que pase el tiempo.

    ⚠ Hace falta para el hilo de `arrancar()`: `_correr` pone el estado final ANTES de
    colgar el bloque en el pizarron, asi que esperar el estado deja al hilo a mitad de
    camino — y lo que le quedaba por hacer era justamente escribir.
    """
    limite = time.time() + segundos
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return False


class EspiaPizarron:
    """El pizarron visual de mentira: guarda lo que se le agrega y lo que se le borra.

    Empieza con un papelito de Martin y otro de Laura puestos, que son los que NUNCA
    se pueden tocar. Sin eso, un barrido que vacie el tablero entero pasaria la prueba.
    """

    def __init__(self):
        # ⚠ Con coordenadas de verdad: sin ellas el buscador de hueco no las ve y
        # "no pisa nada" pasaria por no haber nada que pisar.
        self.items = [
            {"id": 1, "tipo": "nota", "texto": "comprar cafe", "x": 100, "y": 100},
            # ⚠⚠ Esta nota ancha tiene que ser el elemento MAS A LA DERECHA del tablero,
            # y a la altura donde cae el bloque. Si no, medirla mal no cambia nada (manda
            # otro elemento) y la mutacion del bug pasa sin que nadie la cace: la prueba
            # daria verde sin haber probado lo que dice probar.
            {"id": 2, "tipo": "nota", "texto": "de Laura", "nombre": "laura:1",
             "x": 600, "y": 120, "w": 420},
            {"id": 3, "tipo": "lapiz", "puntos": [{"x": 380, "y": 60},
                                                  {"x": 520, "y": 240}]},
        ]
        self.borrados = []
        self.proximo = 4

    def __call__(self, ruta, datos=None, metodo=None):
        if ruta == "/pizarra/estado":
            return {"items": self.items}
        if ruta == "/pizarra/agregar":
            nuevo = dict(datos, id=self.proximo)
            self.proximo += 1
            self.items.append(nuevo)
            return {"ok": True, "id": nuevo["id"]}
        if ruta.startswith("/pizarra/item/") and metodo == "DELETE":
            ident = int(ruta.rsplit("/", 1)[1])
            self.borrados.append(ident)
            self.items = [i for i in self.items if i["id"] != ident]
            return {"ok": True}
        raise AssertionError("el pizarron no conoce esa ruta: " + ruta)

    def mios(self, tipo=None):
        return [i for i in self.items
                if str(i.get("nombre") or "").startswith(adv.MARCA)
                and (tipo is None or i.get("tipo") == tipo)]


# ⚠⚠ Esta cuenta esta REPETIDA a proposito y NO llama a `adv._caja_de`. La primera
# version del chequeo de "no pisa nada" usaba la funcion del modulo, o sea que medía con
# la misma regla que estaba probando: torcida la regla, los dos coincidian y la prueba
# daba verde igual. Es el mismo error que ya se documento en este proyecto — una prueba
# que pasa por el motivo equivocado. La regla del que mide tiene que ser suya.
def _caja(item):
    """La caja (x1,y1,x2,y2) de un item, calculada por la prueba misma."""
    tipo = item.get("tipo") or "nota"
    if tipo in ("nota", "texto", "pin"):
        x, y = item.get("x"), item.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        w = float(item.get("w") or 220.0)      # el max-width del CSS del pizarron
        h = float(item.get("h") or 140.0)
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if all(isinstance(item.get(c), (int, float)) for c in ("x1", "y1", "x2", "y2")):
        return (min(item["x1"], item["x2"]), min(item["y1"], item["y2"]),
                max(item["x1"], item["x2"]), max(item["y1"], item["y2"]))
    xs = [p["x"] for p in (item.get("puntos") or []) if isinstance(p, dict)]
    ys = [p["y"] for p in (item.get("puntos") or []) if isinstance(p, dict)]
    return (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None


def _chocan(a, b):
    """Si dos cajas se superponen. Tambien de la prueba, no del modulo."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _adentro(fondo, cajas):
    """Si el fondo contiene enteras a todas esas cajas."""
    f = _caja(fondo)
    return all(f[0] <= c[0] and f[1] <= c[1] and f[2] >= c[2] and f[3] >= c[3]
               for c in cajas)


def _rebota(f):
    """Que la llamada se queje en vez de arrancar tres sesiones de agente por nada."""
    try:
        f()
        return False
    except ValueError:
        return True


def correr(guion, carpeta, pizarron=None):
    """Una corrida entera con todo tapado. Devuelve (ficha, espia, avisos)."""
    import app.voz.sesiones_movil as sm
    espia = Espia(guion)
    avisos = EspiaAviso()
    viejo_mandar, viejo_aviso, viejo_diff = sm.mandar, sm._mandar_aviso_espera, adv._diff
    viejo_panel = adv._pedir_panel
    sm.mandar = espia
    sm._mandar_aviso_espera = avisos
    adv._diff = lambda cwd: "diff de mentira"
    # Sin esto la prueba le escribiria al pizarron DE VERDAD de Martin.
    adv._pedir_panel = pizarron or EspiaPizarron()
    try:
        t = adv._ficha_nueva(str(carpeta), "que el alta guarde", "dado un alta valida...")
        with adv._CANDADO:
            adv._CORRIDAS[t["id"]] = t
        adv._correr(t["id"])
        return t, espia, avisos
    finally:
        sm.mandar, sm._mandar_aviso_espera, adv._diff = viejo_mandar, viejo_aviso, viejo_diff
        adv._pedir_panel = viejo_panel


def suite():
    """Corre todos los casos. Devuelve {titulo: paso_si_o_no}."""
    r = {}
    tmp = Path(tempfile.mkdtemp(prefix="adv_prueba_"))
    viejo_dir = adv.ADVERSARIAL
    adv.ADVERSARIAL = tmp
    # ⭐⭐ El candado va acá, envolviendo TODA la suite: ver `_sin_panel`. Lo que cada
    # caso tape adentro es para poder mirar lo que colgó, no para protegerse.
    _FUGAS.clear()
    viejo_panel_global = adv._pedir_panel
    adv._pedir_panel = _sin_panel
    try:
        # --- Caso VERDE: nadie encuentra nada -------------------------------------
        t, espia, avisos = correr({"mirador": [EXPEDIENTE_VERDE]}, tmp)
        r["el informe vacio da verde"] = t["estado"] == "verde"
        r["en verde el telefono NO suena"] = not avisos.avisos
        r["en verde no hay segunda vuelta"] = t["vuelta"] == 1
        r["el que mira nace sin sid (contexto limpio)"] = all(
            x["sid"] == "" for x in espia.turnos if x["papel"] == "mirador")
        r["los lectores nacen sin sid (contexto limpio)"] = all(
            x["sid"] == "" for x in espia.turnos if x["papel"] == "lector")
        r["el que mira va por Claude, no por Codex"] = all(
            x["cerebro"] != "codex" for x in espia.turnos if x["papel"] == "mirador")
        r["los lectores van por Codex"] = all(
            x["cerebro"] == "codex" for x in espia.turnos if x["papel"] == "lector")
        r["hay dos lectores"] = (
            len([x for x in espia.turnos if x["papel"] == "lector"]) == adv.LECTORES)
        r["la ficha queda escrita en el disco"] = (tmp / (t["id"] + ".json")).exists()

        # --- Caso ROJO que no se arregla: dos vueltas y empate ---------------------
        t, espia, avisos = correr({"mirador": [EXPEDIENTE_ROJO, EXPEDIENTE_ROJO]}, tmp)
        r["en rojo va una segunda vuelta"] = t["vuelta"] == adv.MAX_VUELTAS
        r["sigue en rojo despues del tope: empate"] = t["estado"] == "empate"
        r["el telefono suena UNA sola vez"] = len(avisos.avisos) == 1
        r["el aviso dice QUE se discute"] = bool(
            avisos.avisos and "Guardar no guarda" in avisos.avisos[0]["texto"])
        r["el implementador conserva su charla entre vueltas"] = (
            [x["sid"] for x in espia.turnos if x["papel"] == "implementador"][1:]
            == ["sid-implementador"])
        r["el que mira vuelve a nacer limpio en la vuelta 2"] = (
            len([x for x in espia.turnos if x["papel"] == "mirador"]) == 2
            and all(x["sid"] == "" for x in espia.turnos if x["papel"] == "mirador"))
        # El expediente que se guarda es el del que MIRO, no el del que implemento.
        r["el expediente es del que miro"] = t["expediente"] == EXPEDIENTE_ROJO
        r["el expediente no lo escribio el implementador"] = (
            "listo, lo toque" not in (t["expediente"] or ""))
        pedidos_lector = [x["texto"] for x in espia.turnos if x["papel"] == "lector"]
        r["el lector recibe el expediente del que miro"] = bool(
            pedidos_lector and "Guardar no guarda" in pedidos_lector[0])

        # --- La regla de evidencia -------------------------------------------------
        t, espia, avisos = correr(
            {"mirador": [EXPEDIENTE_VERDE], "lector": LECTOR_SIN_EVIDENCIA}, tmp)
        r["una opinion sin evidencia no cuenta"] = t["estado"] == "verde"
        r["lo descartado se cuenta, no se tira callado"] = t["descartados"] == adv.LECTORES

        # --- El desempate ----------------------------------------------------------
        t, espia, avisos = correr({"mirador": [EXPEDIENTE_ROJO, EXPEDIENTE_ROJO]}, tmp)
        import app.voz.sesiones_movil as sm
        viejo = sm.mandar
        sm.mandar = Espia({"mirador": [EXPEDIENTE_VERDE]})
        # ⚠ `resolver()` NO pasa por `correr()`, asi que hay que taparle el pizarron acá:
        # sin esto le escribe al de Martin. Fue uno de los dos escapes del 2026-08-29.
        viejo_piz = adv._pedir_panel
        adv._pedir_panel = EspiaPizarron()
        try:
            devuelto = adv.resolver(t["id"], "implementador")
        finally:
            sm.mandar, adv._pedir_panel = viejo, viejo_piz
        r["desempate a favor del que escribio: queda verde"] = (
            devuelto is not None and devuelto["estado"] == "verde")

        t2, _e, _a = correr({"mirador": [EXPEDIENTE_ROJO, EXPEDIENTE_ROJO]}, tmp)
        viejo_piz = adv._pedir_panel
        adv._pedir_panel = EspiaPizarron()
        try:
            r["un empate resuelto no se puede volver a resolver"] = (
                adv.resolver(t2["id"], "implementador") is not None
                and adv.resolver(t2["id"], "implementador") is None)
        finally:
            adv._pedir_panel = viejo_piz

        # --- El pizarron visual ----------------------------------------------------
        # Martin lo pidio para TODAS las corridas, verde incluido (2026-08-29).
        piz = EspiaPizarron()
        t, _e, _a = correr({"mirador": [EXPEDIENTE_VERDE]}, tmp, piz)
        r["una corrida verde deja su bloque"] = len(piz.mios("texto")) == 1
        r["el analisis dice el proyecto y como salio"] = bool(
            piz.mios("texto") and "verde" in piz.mios("texto")[0]["texto"])

        piz = EspiaPizarron()
        t, _e, _a = correr({"mirador": [EXPEDIENTE_ROJO, EXPEDIENTE_ROJO]}, tmp, piz)
        # ⚠ UNO por corrida, no uno por vuelta ni uno por hallazgo: el tablero es donde
        # Martin tiene sus dibujos.
        r["una corrida deja UN papelito, no uno por paso"] = len(piz.mios("texto")) == 1
        r["el analisis del empate dice que se encontro"] = bool(
            piz.mios("texto") and "Guardar no guarda" in piz.mios("texto")[0]["texto"])
        r["cada pieza lleva la marca para poder barrerla"] = bool(
            piz.mios() and all(i["nombre"] == adv.MARCA + t["id"] for i in piz.mios()))
        # --- Que no le caiga encima a nada de Martin -------------------------------
        ajenas = [_caja(i) for i in piz.items
                  if not str(i.get("nombre") or "").startswith(adv.MARCA)]
        mias = [_caja(i) for i in piz.mios()]
        r["el bloque no pisa nada de lo que ya habia"] = bool(mias) and not any(
            _chocan(m, a) for m in mias for a in ajenas if m and a)

        # Desempatar cambia el veredicto: el bloque viejo se va y queda uno solo.
        viejo_panel = adv._pedir_panel
        adv._pedir_panel = piz
        try:
            adv.resolver(t["id"], "implementador")
        finally:
            adv._pedir_panel = viejo_panel
        r["desempatar no deja dos bloques de la misma corrida"] = len(piz.mios("texto")) == 1
        r["al desempatar, el analisis ya no dice que te espera"] = bool(
            piz.mios("texto") and "te espera" not in piz.mios("texto")[0]["texto"])

        # Dos corridas seguidas: la segunda no puede caerle encima a la primera.
        piz = EspiaPizarron()
        correr({"mirador": [EXPEDIENTE_VERDE]}, tmp, piz)
        primera = [_caja(i) for i in piz.mios()]
        correr({"mirador": [EXPEDIENTE_VERDE]}, tmp, piz)
        segunda = [_caja(i) for i in piz.mios() if _caja(i) not in primera]
        r["dos corridas seguidas no se pisan entre si"] = bool(segunda) and not any(
            _chocan(s, p) for s in segunda for p in primera if s and p)

        # El barrido: solo lo propio.
        adv._pedir_panel = piz
        try:
            sacadas = adv.limpiar_pizarra()
        finally:
            adv._pedir_panel = viejo_panel
        r["el barrido saca todas las piezas propias"] = sacadas == 4 and not piz.mios()
        r["el barrido NO toca lo de Martin ni lo de Laura"] = (
            len(piz.items) == 3 and all(
                str(i.get("nombre") or "") == "" or i["nombre"].startswith("laura:")
                for i in piz.items))

        # --- La captura, con el analisis abajo (pedido de Martin) ------------------
        viejo_deposito = adv.PIZARRA_IMAGENES
        adv.PIZARRA_IMAGENES = tmp / "pizarra_imagenes"
        try:
            from PIL import Image
            foto = tmp / "lo_que_vio.png"
            Image.new("RGB", (800, 400), "white").save(foto)
            expediente = EXPEDIENTE_ROJO + "CAPTURA: %s\n" % foto
            piz = EspiaPizarron()
            # Un dibujo de Martin bien a la derecha: lo nuevo no puede caerle encima.
            piz.items.append({"id": 9, "tipo": "rectangulo", "x1": 500, "y1": 10,
                              "x2": 900, "y2": 300})
            t, _e, _a = correr({"mirador": [expediente, expediente]}, tmp, piz)
            imagenes = piz.mios("imagen")
            notas = piz.mios("texto")
            fondos = piz.mios("rectangulo")
            r["la captura se cuelga en el pizarron"] = len(imagenes) == 1
            # --- El bloque: fondo carbon atras de todo ---------------------------
            r["hay un fondo carbon detras del bloque"] = bool(
                fondos and fondos[0]["color"] == adv.CARBON
                and fondos[0].get("relleno") == "solido")
            # ⚠ El pizarron dibuja en el ORDEN de la lista: el primero queda atras. Si
            # el fondo se cuelga ultimo, tapa la foto entera.
            r["el fondo se cuelga ANTES que la foto y el texto"] = bool(
                fondos and imagenes and notas
                and piz.items.index(fondos[0]) < piz.items.index(imagenes[0])
                and piz.items.index(fondos[0]) < piz.items.index(notas[0]))
            r["el fondo contiene la foto y el analisis"] = bool(
                fondos and imagenes and notas and _adentro(
                    fondos[0], [_caja(imagenes[0]), _caja(notas[0])]))
            r["el analisis va en tiza, no en papelito de color"] = not piz.mios("nota")
            r["la captura no se estira: respeta la proporcion"] = bool(
                imagenes and abs((imagenes[0]["y2"] - imagenes[0]["y1"])
                                 / (imagenes[0]["x2"] - imagenes[0]["x1"]) - 400 / 800) < 0.01)
            # ⚠ Todo con .get(): una mutacion puede colgar notas sin coordenadas, y ahi
            # la prueba tiene que FALLAR, no reventar. Un chequeo que explota no es un
            # chequeo rojo, es un chequeo que no contesto.
            r["el analisis queda ABAJO de la captura"] = bool(
                imagenes and notas and notas[0].get("y", -1) > imagenes[0]["y2"])
            r["el analisis queda alineado con la captura"] = bool(
                imagenes and notas
                and abs(notas[0].get("x", -999)
                        - (imagenes[0]["x1"] + imagenes[0]["x2"]) / 2) < 1)
            r["no se cuelga encima de los dibujos de Martin"] = bool(
                imagenes and imagenes[0]["x1"] > 900)
            r["el archivo se copia, no se enlaza al original"] = (
                adv.PIZARRA_IMAGENES / ("adv_%s.png" % t["id"])).exists()
            # El barrido tiene que llevarse la foto Y el pie, no una sola de las dos.
            adv._pedir_panel = piz
            try:
                adv.limpiar_pizarra()
            finally:
                adv._pedir_panel = viejo_panel
            r["el barrido se lleva la captura y el analisis juntos"] = not piz.mios()

            # Una ruta que no existe no puede dejar a la corrida sin veredicto visible.
            piz = EspiaPizarron()
            malo = EXPEDIENTE_ROJO + "CAPTURA: C:\\no\\existe\\nada.png\n"
            correr({"mirador": [malo, malo]}, tmp, piz)
            r["una captura que no existe no tumba el analisis"] = (
                len(piz.mios("texto")) == 1)
        finally:
            adv.PIZARRA_IMAGENES = viejo_deposito

        # --- La puerta de entrada, que es la que usa el panel ----------------------
        # ⚠ Va aparte de los casos de arriba a proposito: aquellos llaman a `_correr`
        # derecho, asi que ninguno probaba que `arrancar()` largue el hilo de verdad.
        r["arrancar() sin tarea no arranca nada"] = _rebota(lambda: adv.arrancar(str(tmp), ""))
        r["arrancar() con una carpeta que no existe rebota"] = _rebota(
            lambda: adv.arrancar(str(tmp / "no-existe"), "algo"))
        import app.voz.sesiones_movil as sm
        viejo_mandar, viejo_diff = sm.mandar, adv._diff
        sm.mandar = Espia({"mirador": [EXPEDIENTE_VERDE]})
        adv._diff = lambda cwd: ""
        # ⚠⚠ El hilo de `arrancar()` es de VERDAD y vive mas que este bloque: hay que
        # taparle el pizarron a el tambien. Y no alcanza con esperar el estado final —
        # `_correr` lo pone ANTES de colgar el bloque, asi que soltar el tapado ahi
        # dejaba al hilo escribiendo en el pizarron real un instante despues. Ese fue el
        # segundo escape del 2026-08-29, y el mas dificil de ver.
        piz_hilo = EspiaPizarron()
        viejo_piz = adv._pedir_panel
        adv._pedir_panel = piz_hilo
        try:
            ficha = adv.arrancar(str(tmp), "que el alta guarde")
            _esperar(lambda: adv.estado(ficha["id"])["estado"]
                     in ("verde", "empate", "fallo"))
            # Y recien ahora, a que el hilo TERMINE de colgar lo suyo.
            _esperar(lambda: bool(piz_hilo.mios()))
        finally:
            sm.mandar, adv._diff = viejo_mandar, viejo_diff
            adv._pedir_panel = viejo_piz
        r["arrancar() larga el ciclo en segundo plano"] = (
            adv.estado(ficha["id"])["estado"] == "verde")
        # ⚠⚠ Y que se lo haya esperado HASTA EL FINAL, no hasta el estado. Este chequeo
        # mira el efecto (¿colgó su bloque?) y no el reloj, porque una fuga que pasa
        # DESPUES de que termina la suite no la puede ver ningun contador leido al final:
        # para entonces el tapado ya se levanto y el papelito cae en el pizarron real.
        r["se espera a que el hilo de arrancar() cuelgue lo suyo"] = bool(piz_hilo.mios())
        r["la corrida sale en la lista de su carpeta"] = any(
            c["id"] == ficha["id"] for c in adv.listar(str(tmp)))

        # --- La lista de proyectos no puede usar la funcion lenta ------------------
        # ⚠ Esto se mide LLAMANDO, no leyendo el codigo: un chequeo de texto pasaba
        # tambien por el comentario que dice "NO se usa listar()", o sea que daba
        # verde por el motivo equivocado.
        import app.rutas as rutas
        import app.voz.sesiones_movil as sm
        vacia = tmp / "proyectos_de_mentira"
        vacia.mkdir(exist_ok=True)
        llamadas = []
        viejo_listar, viejo_dir_proy = sm.listar, rutas.CLAUDE_PROYECTOS
        sm.listar = lambda *a, **k: llamadas.append(1) or []
        rutas.CLAUDE_PROYECTOS = vacia
        adv._CARPETAS.update({"cuando": 0.0, "lista": []})
        try:
            adv.carpetas()
        finally:
            sm.listar, rutas.CLAUDE_PROYECTOS = viejo_listar, viejo_dir_proy
            adv._CARPETAS.update({"cuando": 0.0, "lista": []})
        r["carpetas() no llama a la listar() lenta"] = not llamadas

        # ⭐⭐ El chequeo que faltaba y que habria evitado todo esto: correr la prueba no
        # puede tocarle el pizarron a Martin. Va ULTIMO porque mira lo que hizo toda la
        # suite. Si algun camino nuevo se olvida de tapar el pizarron, cae acá.
        r["la prueba no le escribe al pizarron de verdad"] = not _FUGAS
        if _FUGAS:
            print("     se escaparon hacia el panel real:", sorted(set(_FUGAS)))
    finally:
        adv._pedir_panel = viejo_panel_global
        adv.ADVERSARIAL = viejo_dir
        shutil.rmtree(tmp, ignore_errors=True)
    return r


# ------------------------------------------------------------------ las mutaciones

def _mutar_sin_regla_evidencia():
    """Aceptar hallazgos sin evidencia: la regla de oro del metodo, apagada."""
    viejo = adv._parsear

    def flojo(texto, quien):
        hallazgos, descartados = viejo(texto, quien)
        for linea in (texto or "").splitlines():
            m = adv._HALLAZGO.match(linea)
            if m and not any(h["que"] == m.group(1).strip() for h in hallazgos):
                hallazgos.append({"de": quien, "que": m.group(1).strip(),
                                  "evidencia": "", "escenario": ""})
                descartados -= 1
        return hallazgos, max(0, descartados)

    adv._parsear = flojo
    return lambda: setattr(adv, "_parsear", viejo)


def _mutar_avisa_siempre():
    """Avisar tambien cuando esta todo bien: el bot que se silencia en dos dias."""
    viejo = adv._contrastar

    def ruidoso(t):
        hallazgos = viejo(t)
        adv._avisar_empate(t)
        return hallazgos

    adv._contrastar = ruidoso
    return lambda: setattr(adv, "_contrastar", viejo)


def _mutar_revisor_con_memoria():
    """El que mira hereda la charla del implementador: deja de ser independiente."""
    viejo = adv._mirar

    def sucio(t):
        from app.voz import sesiones_movil
        return sesiones_movil.mandar(
            t["cwd"], t["sid_implementador"] or "sid-implementador",
            "Abri el sistema en el navegador y refutalo.")[0]

    adv._mirar = sucio
    return lambda: setattr(adv, "_mirar", viejo)


def _mutar_expediente_del_acusado():
    """El expediente lo arma el que escribio el codigo: el acusado escribe el sumario."""
    viejo = adv._contrastar

    def torcido(t):
        hallazgos = viejo(t)
        t["expediente"] = "listo, lo toque"
        return hallazgos

    adv._contrastar = torcido
    return lambda: setattr(adv, "_contrastar", viejo)


def _mutar_aviso_pelado():
    """Un aviso que no dice que se discute: el que Martin no puede leer en el celular."""
    viejo = adv._avisar_empate

    def pelado(t):
        if t.get("avisado"):
            return
        from app.voz.sesiones_movil import _mandar_aviso_espera
        t["avisado"] = bool(_mandar_aviso_espera(
            "Hay una decision pendiente en el panel.", t["proyecto"]))

    adv._avisar_empate = pelado
    return lambda: setattr(adv, "_avisar_empate", viejo)


def _mutar_barrido_arrasador():
    """El barrido vacia el pizarron entero: se lleva puestos los dibujos de Martin."""
    viejo = adv.limpiar_pizarra

    def arrasa():
        estado = adv._pedir_panel("/pizarra/estado")
        sacadas = 0
        for item in (estado.get("items") or []):
            adv._pedir_panel("/pizarra/item/%s" % item["id"], metodo="DELETE")
            sacadas += 1
        return sacadas

    adv.limpiar_pizarra = arrasa
    return lambda: setattr(adv, "limpiar_pizarra", viejo)


def _mutar_anota_cada_paso():
    """Un papelito por cada paso: en dos dias no ve mas sus dibujos."""
    viejo = adv._paso

    def charlatan(t, texto):
        viejo(t, texto)
        try:
            adv._pedir_panel("/pizarra/agregar",
                             {"tipo": "texto", "texto": texto, "x": 0, "y": 0,
                              "nombre": adv.MARCA + t["id"]})
        except Exception:
            pass

    adv._paso = charlatan
    return lambda: setattr(adv, "_paso", viejo)


def _mutar_captura_estirada():
    """Colgarla cuadrada, ignorando la proporcion: la evidencia deformada miente."""
    viejo = adv._colgar_captura
    # Miente sobre el alto real: dice que la imagen es cuadrada.
    adv._colgar_captura = lambda ruta, cid: (
        (viejo(ruta, cid) or (None, 0, 0))[0] and
        (viejo(ruta, cid)[0], viejo(ruta, cid)[1], viejo(ruta, cid)[1]) or None)
    return lambda: setattr(adv, "_colgar_captura", viejo)


def _mutar_nota_encima():
    """El pie de foto encima de la captura: tapa justo lo que hay que mirar."""
    viejo_anotar = adv._anotar_pizarra

    def encima(t):
        viejo_anotar(t)
        for item in list(getattr(adv._pedir_panel, "items", [])):
            if (item.get("tipo") == "texto"
                    and str(item.get("nombre") or "").startswith(adv.MARCA)):
                item["y"] = 0.0

    adv._anotar_pizarra = encima
    return lambda: setattr(adv, "_anotar_pizarra", viejo_anotar)


def _mutar_lugar_por_el_centro():
    """El bug de hoy: medir la nota por su centro y no por su caja.

    Con una nota ancha en el tablero, el bloque nuevo le cae encima justo la mitad
    del ancho. Es exactamente lo que Martin pidio que no pasara.
    """
    viejo = adv._caja_de

    def sin_ancho(item):
        if (item.get("tipo") or "nota") in ("nota", "texto", "pin"):
            x, y = item.get("x"), item.get("y")
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return None
            return (x, y, x, y)          # un punto: la nota "no ocupa lugar"
        return viejo(item)

    adv._caja_de = sin_ancho
    return lambda: setattr(adv, "_caja_de", viejo)


def _mutar_fondo_adelante():
    """Colgar el fondo carbon al final: queda ADELANTE y tapa la foto entera."""
    viejo = adv._anotar_pizarra

    def al_reves(t):
        viejo(t)
        items = getattr(adv._pedir_panel, "items", [])
        fondos = [i for i in items if i.get("tipo") == "rectangulo"
                  and str(i.get("nombre") or "").startswith(adv.MARCA)]
        for f in fondos:                 # lo manda al frente
            items.remove(f)
            items.append(f)

    adv._anotar_pizarra = al_reves
    return lambda: setattr(adv, "_anotar_pizarra", viejo)


def _mutar_fondo_chico():
    """Un fondo mas chico que lo que tiene que sostener: la foto le sobresale."""
    viejo = adv.MARGEN_BLOQUE
    adv.MARGEN_BLOQUE = -60.0
    return lambda: setattr(adv, "MARGEN_BLOQUE", viejo)


def _mutar_pizarron_destapado():
    """El pizarron de mentira deja de tapar: es "me olvide de taparlo" hecho defecto.

    Es el escape que le lleno la pizarra a Martin el 2026-08-29. No puede ensuciar nada
    al correr esta mutacion: el candado global (`_sin_panel`) sigue puesto y lo unico
    que pasa es que la fuga queda ANOTADA, que es justo lo que el chequeo mira.
    """
    viejo = EspiaPizarron.__call__
    EspiaPizarron.__call__ = lambda self, ruta, datos=None, metodo=None: _sin_panel(
        ruta, datos, metodo)
    return lambda: setattr(EspiaPizarron, "__call__", viejo)


def _mutar_no_esperar_al_hilo():
    """Soltar el tapado sin esperar a que el hilo de `arrancar()` termine de colgar.

    El estado final se pone ANTES de anotar en el pizarron, asi que el hilo escribe un
    instante despues — cuando el tapado de ese bloque ya se levanto. El segundo escape
    del 2026-08-29, y el que ningun chequeo veia.
    """
    global _esperar
    viejo = _esperar
    _esperar = lambda condicion, segundos=5.0: True
    def reponer():
        global _esperar
        _esperar = viejo
    return reponer


MUTACIONES = [
    ("el pizarron de mentira no tapa nada (le escribe al de Martin)",
     _mutar_pizarron_destapado, ["la prueba no le escribe al pizarron de verdad"]),
    # ⚠ Este apunta al chequeo del EFECTO y no al contador de fugas: con el defecto
    # puesto la fuga ocurre DESPUES de que la suite ya conto, asi que el contador la
    # veria vacia y la mutacion pasaria — medido, no supuesto.
    ("no esperar a que el hilo de arrancar() termine de colgar lo suyo",
     _mutar_no_esperar_al_hilo, ["se espera a que el hilo de arrancar() cuelgue lo suyo"]),
    ("aceptar hallazgos sin evidencia", _mutar_sin_regla_evidencia,
     ["una opinion sin evidencia no cuenta", "lo descartado se cuenta, no se tira callado"]),
    ("avisar aunque este todo bien", _mutar_avisa_siempre,
     ["en verde el telefono NO suena", "el telefono suena UNA sola vez"]),
    ("el revisor hereda la charla del implementador", _mutar_revisor_con_memoria,
     ["el que mira nace sin sid (contexto limpio)"]),
    ("el expediente lo escribe el acusado", _mutar_expediente_del_acusado,
     ["el expediente es del que miro", "el expediente no lo escribio el implementador"]),
    ("el aviso no dice que se discute", _mutar_aviso_pelado,
     ["el aviso dice QUE se discute"]),
    ("el barrido vacia el pizarron entero", _mutar_barrido_arrasador,
     ["el barrido NO toca lo de Martin ni lo de Laura"]),
    ("anotar un papelito en cada paso", _mutar_anota_cada_paso,
     ["una corrida deja UN papelito, no uno por paso"]),
    ("colgar la captura estirada", _mutar_captura_estirada,
     ["la captura no se estira: respeta la proporcion"]),
    ("poner el analisis encima de la captura", _mutar_nota_encima,
     ["el analisis queda ABAJO de la captura"]),
    ("medir las notas por su centro y no por su caja", _mutar_lugar_por_el_centro,
     ["el bloque no pisa nada de lo que ya habia"]),
    ("colgar el fondo carbon adelante de todo", _mutar_fondo_adelante,
     ["el fondo se cuelga ANTES que la foto y el texto"]),
    ("un fondo mas chico que el bloque", _mutar_fondo_chico,
     ["el fondo contiene la foto y el analisis"]),
]


def main():
    mutar = "--mutar" in sys.argv
    # Sin emojis ni rayas largas: la consola de Windows es cp1252 y revienta.
    print("\nTesting adversarial - el que escribe el codigo no lo juzga\n")
    r = suite()
    for titulo, paso in r.items():
        print(("  ok   " if paso else "  MAL  ") + titulo)
    mal = [t for t, p in r.items() if not p]
    print("\n%d chequeos, %d mal" % (len(r), len(mal)))
    if not mutar:
        if mal:
            print("\nOJO: hay reglas del metodo que el codigo ya no cumple.\n")
        return 1 if mal else 0

    print("\n--- Ahora al reves: rompo cada regla y exijo que el chequeo la cace ---\n")
    fallos = 0
    for nombre, aplicar, deben_caer in MUTACIONES:
        revertir = aplicar()
        try:
            rr = suite()
        finally:
            revertir()
        cayeron = [c for c in deben_caer if not rr.get(c, True)]
        if cayeron:
            print("  ok   %s -> lo caza: %s" % (nombre, ", ".join(cayeron)))
        else:
            fallos += 1
            print("  MAL  %s -> NADIE lo caza. Ese chequeo es un adorno." % nombre)
    print("\n%d mutaciones, %d sin cazar" % (len(MUTACIONES), fallos))
    return 1 if (mal or fallos) else 0


if __name__ == "__main__":
    sys.exit(main())
