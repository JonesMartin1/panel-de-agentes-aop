#!/bin/sh
# Portero de las reglas "No romper (costaron sangre)" del CLAUDE.md.
#
# Corre pruebas/probar_no_romper.py antes de cada commit. Son chequeos de texto:
# tardan menos de dos segundos, no tocan la GPU, el microfono ni ningun servicio,
# y no gastan un solo token. Si algo esta roto, el commit se frena y la salida
# dice cual es la regla y por que existe.
#
# PARA INSTALARLO (una sola vez, desde la raiz del proyecto):
#
#     cp pruebas/gancho_pre_commit.sh .git/hooks/pre-commit
#
# Convive con el post-commit de graphify, que es otro gancho distinto.
# Para saltearlo en una emergencia:  git commit --no-verify

PY="D:/IA/envs/wpp/python.exe"
[ -x "$PY" ] || PY="python"

cd "$(git rev-parse --show-toplevel)" || exit 0

salida=$("$PY" -m pruebas.probar_no_romper 2>&1)
estado=$?

if [ $estado -ne 0 ]; then
    echo "$salida"
    echo
    echo "--------------------------------------------------------------------"
    echo "  Commit frenado: se rompio una regla de 'No romper' del CLAUDE.md."
    echo "  Arreglalo, o si sabes lo que estas haciendo:  git commit --no-verify"
    echo "--------------------------------------------------------------------"
    exit 1
fi

exit 0
