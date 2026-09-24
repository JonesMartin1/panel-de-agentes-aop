# Instala el enlazador de skills donde tiene que vivir y lo deja andando solo.
#
# Hace tres cosas:
#   1. copia esta carpeta a ~/.claude/skills/sincro-skills/
#   2. le cuelga el gancho UserPromptSubmit (al lado del que ya corre el buzon)
#   3. lo corre una vez para verificar
#
# Hace copia de respaldo del settings.json antes de tocarlo, y si el JSON queda
# invalido lo restaura solo: un settings.json roto apaga TODA la configuracion de ese
# archivo en silencio, permisos y ganchos incluidos.
#
# Correrlo dos veces no duplica nada.

$origen  = Split-Path -Parent $MyInvocation.MyCommand.Path
$destino = "$HOME\.claude\skills\sincro-skills"
$ajustes = "$HOME\.claude\settings.json"
$comando = 'python "$HOME/.claude/skills/sincro-skills/scripts/sincro.py" 2>/dev/null || true'

# --- 1. copiar ---------------------------------------------------------------------
Write-Host "1) Copiando a $destino"
# ⚠ Se copia el CONTENIDO (`\*`) con la carpeta ya creada. `Copy-Item "$origen\scripts"`
# sobre un destino que ya existe la mete adentro y deja `scripts\scripts`: la segunda
# corrida quedaria distinta de la primera, que es justo lo que no puede pasar.
foreach ($sub in @("scripts", "pruebas")) {
    New-Item -ItemType Directory -Force -Path "$destino\$sub" | Out-Null
    Copy-Item "$origen\$sub\*" "$destino\$sub\" -Recurse -Force
}
Copy-Item "$origen\SKILL.md" $destino -Force
Write-Host "   listo"

# --- 2. el gancho ------------------------------------------------------------------
if (-not (Test-Path $ajustes)) { Write-Host "No encontre $ajustes"; exit 1 }

$respaldo = "$ajustes.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $ajustes $respaldo
Write-Host "2) Respaldo del settings.json en: $respaldo"

$config = Get-Content $ajustes -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $config.hooks) {
    $config | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{}) -Force
}
$eventos = $config.hooks
$actual = @($eventos.UserPromptSubmit)

$yaEsta = $false
foreach ($grupo in $actual) {
    foreach ($h in @($grupo.hooks)) {
        if ($h.command -like "*sincro.py*") { $yaEsta = $true }
    }
}

if ($yaEsta) {
    Write-Host "   el gancho ya estaba puesto, no lo toco"
} else {
    $nuevo = [pscustomobject]@{
        hooks = @([pscustomobject]@{
            type          = "command"
            command       = $comando
            timeout       = 15
            statusMessage = "Sincronizando skills entre Claude y Codex"
        })
    }
    # Se AGREGA al array, no lo reemplaza: ahi ya vive el gancho del buzon de Laura.
    $eventos | Add-Member -NotePropertyName UserPromptSubmit `
                          -NotePropertyValue (@($actual) + $nuevo) -Force
    $config | ConvertTo-Json -Depth 100 | Set-Content $ajustes -Encoding UTF8
    Write-Host "   gancho agregado"
}

# --- chequeo: que no haya quedado roto ---------------------------------------------
try {
    $v = Get-Content $ajustes -Raw -Encoding UTF8 | ConvertFrom-Json
    $cuantos = @($v.hooks.UserPromptSubmit).Count
    if ($cuantos -lt 2 -and -not $yaEsta) { throw "quedo un solo gancho: se piso el del buzon" }
    Write-Host "   settings.json valido, $cuantos ganchos en UserPromptSubmit"
} catch {
    Copy-Item $respaldo $ajustes -Force
    Write-Host "   ALGO SALIO MAL ($_). Restaure el respaldo, no quedo nada roto."
    exit 1
}

# --- 3. probarlo -------------------------------------------------------------------
Write-Host "3) Corriendo una vez para verificar"
& python "$destino\scripts\sincro.py" --simular
Write-Host "   (si no dijo nada, es que no falta ningun enlace: es lo que se espera)"
Write-Host ""
Write-Host "Listo. Reinicia Claude Code para que tome el gancho nuevo."
