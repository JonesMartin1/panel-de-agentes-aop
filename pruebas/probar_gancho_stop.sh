#!/bin/sh
# Prueba del gancho de fin de turno, con el comando EXACTO que va en settings.
# Se corre desde cualquier carpeta a proposito: el gancho no controla su cwd.
#
#     sh pruebas/probar_gancho_stop.sh
#
# Espera: arbol sano -> nada y codigo 0. Regla rota -> {"decision":"block",...}.

CMD='cd /d/IA/wpp-transcriptor && D:/IA/envs/wpp/python.exe -m pruebas.gancho_stop'

cd /tmp || exit 1
for entrada in '{}' '' 'no soy json'; do
    salida=$(printf '%s' "$entrada" | sh -c "$CMD" 2>&1)
    codigo=$?
    echo "entrada=[$entrada]  codigo=$codigo  salida=[$salida]"
done
