# Lecciones de la skill `avisar`

Formato fijo (la más nueva arriba): síntoma · causa raíz · regla · evidencia · vigencia.
Ver [_molde-automejora.md](../_molde-automejora.md).

---

## 2026-08-12 · Una config faltante no puede matar el aviso: tiene que caer al otro canal
- **Síntoma:** con dos canales configurados, si al canal pedido le faltaba el archivo de
  credenciales el script moría con `sys.exit` y el aviso no salía por ningún lado —
  aunque el otro canal estuviera perfecto.
- **Causa raíz:** `_config()` cortaba el proceso en vez de devolver un error manejable,
  así que el respaldo entre canales nunca llegaba a ejecutarse.
- **Regla:** en un camino con respaldo, los errores de configuración se tratan como
  cualquier otra falla del canal (excepción atrapable), no como un final del programa.
  Solo se muere cuando fallaron TODOS los canales.
- **Evidencia:** 2026-08-12, se escondió `~/.claude/telegram.json` y se pidió
  `--por telegram`: salió por WhatsApp con la aclaración "no pude por telegram".
- **Vigencia:** permanente.

## 2026-08-12 · Que el bot conteste NO prueba que el Servidor esté vivo
- **Síntoma:** se mandó un mensaje de prueba por Telegram, llegó perfecto, y sin embargo
  el Servidor de `wpp-transcriptor` (bot de Telegram + webhook de WhatsApp + túnel)
  llevaba casi un día apagado.
- **Causa raíz:** esta skill le habla **directo a la API de Telegram**, no al bot local.
  El camino de salida (avisar) y el de entrada (que el bot escuche y transcriba) son
  independientes: uno anda con la máquina apagada, el otro no.
- **Regla:** nunca uses un aviso que salió bien como prueba de que los servicios están
  arriba. Para eso, mirá el panel (`http://localhost:8750/status`).
- **Evidencia:** 2026-08-12, `sendMessage` devolvió `ok:true` y en el mismo minuto
  `/status` daba `telegram/webhook/tunel: vivo=false`.
- **Vigencia:** permanente mientras la skill hable directo con la API.
