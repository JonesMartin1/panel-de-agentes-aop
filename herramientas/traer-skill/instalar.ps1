# Instala la puerta de entrada para skills de internet.
#
# Copia esta carpeta a ~/.claude/skills/traer-skill/ y crea la cuarentena.
# No toca settings.json ni ningun gancho: esta skill se invoca a mano.
# Correrlo dos veces no duplica nada.

$origen     = Split-Path -Parent $MyInvocation.MyCommand.Path
$destino    = "$HOME\.claude\skills\traer-skill"
$cuarentena = "$HOME\.claude\skills-cuarentena"

Write-Host "1) Copiando a $destino"
# ⚠ Se copia el CONTENIDO (`\*`) con la carpeta ya creada: `Copy-Item "$origen\scripts"`
# sobre un destino existente la mete adentro y deja `scripts\scripts`.
foreach ($sub in @("scripts", "pruebas")) {
    New-Item -ItemType Directory -Force -Path "$destino\$sub" | Out-Null
    Copy-Item "$origen\$sub\*" "$destino\$sub\" -Recurse -Force
}
Copy-Item "$origen\SKILL.md" $destino -Force
Write-Host "   listo"

Write-Host "2) Creando la cuarentena en $cuarentena"
New-Item -ItemType Directory -Force -Path $cuarentena | Out-Null
# Un README para que quede claro que es esa carpeta si alguien la encuentra suelta.
@"
Skills bajadas de internet que TODAVIA NO aprobo Martin.

Esta carpeta esta fuera de ~/.claude/skills y de ~/.codex/skills a proposito: aca
adentro ningun cerebro ve nada, y el enlazador (sincro-skills) la saltea explicitamente.

Lo que hay aca se mide con:
    python ~/.claude/skills/traer-skill/scripts/auditar.py "<carpeta>"

y recien con el visto bueno de Martin se copia a ~/.claude/skills/.
"@ | Set-Content "$cuarentena\LEEME.txt" -Encoding UTF8
Write-Host "   listo"

Write-Host "3) Corriendo la prueba del medidor"
& python "$destino\pruebas\probar_auditar.py"

Write-Host ""
Write-Host "Listo. La skill aparece sola en el menu, sin reiniciar nada."
Write-Host "Probala con:  /traer-skill"
