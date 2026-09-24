# Reglas para Codex en este proyecto

Las reglas de trabajo de este repo están en **`CLAUDE.md`** y valen igual para vos:
leelo antes de tocar nada. Donde dice "Claude" aplicá "cualquier agente". La
arquitectura completa está en `README.md`, y si vas a tocar una pantalla, en
`INTERFAZ.md`. No se repite nada acá a propósito: una regla vive en un solo lugar.

Lo mínimo que no podés no saber, por si entrás de apuro:

- ⭐ **Antes de explorar el código, mirá `graphify-out/`** si existe: ahí está el grafo del
  repo y de los docs. Para preguntas de arquitectura, `graphify query "..."` o leé
  `graphify-out/GRAPH_REPORT.md`. Si no existe, se arma con `/graphify` (paso 12 del README).
- Python: el del entorno conda `wpp` (ver la instalación en `README.md`). Nunca el del sistema.
- Los módulos se lanzan con `-m` desde la raíz (`python -m app.voz.voz`), nunca
  por ruta al `.py`.
- Las rutas van en `app/rutas.py` y el código en `app/`. No ensuciar la raíz.
- Antes de reiniciar un servicio: verificar sintaxis con `py_compile` y leer la
  sección "No romper" de `CLAUDE.md` — esas reglas costaron sangre.
- Si trabajás en paralelo con otro agente, anotate en `PIZARRA.md` antes de tocar (si no
  existe, se crea con la skill `paralelo`).
