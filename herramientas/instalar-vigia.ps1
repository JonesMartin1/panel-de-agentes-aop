# Deja el vigia del WhatsApp corriendo solo, sin ninguna sesion de Claude abierta.
#
# Cada 10 minutos le pregunta a Evolution si la instancia sigue vinculada, y avisa
# por Telegram cuando se cae y cuando vuelve. Las reglas anti-ruido las trae
# `vigilar.py`: aguanta 2 fallos seguidos antes de gritar y no repite hasta que se
# recupere.
#
# Se corre una sola vez, en PowerShell:
#     & "D:\IA\wpp-transcriptor\herramientas\instalar-vigia.ps1"
#
# Dos caminos, y el script elige solo:
#   1. Tarea programada de Windows. Es el mejor, pero Register-ScheduledTask pide
#      permisos de administrador en esta maquina (2026-08-29: "Access is denied").
#   2. Carpeta de Inicio. No pide nada, arranca con la sesion de Martin y se puede
#      sacar borrando un archivo. Es el que se usa si el 1 no se puede.
#
# OJO: este script NO PUEDE decir "listo" sin haber verificado que quedo algo puesto.
# La primera version lo hacia: los errores de Register-ScheduledTask no frenan por
# $ErrorActionPreference y abajo imprimia "Listo" en verde igual. Un instalador que
# miente es peor que uno que falla, porque nadie vuelve a mirar.

$ErrorActionPreference = 'Stop'

$raiz    = 'D:\IA\wpp-transcriptor'
$python  = 'D:\IA\envs\wpp\python.exe'
$pythonw = 'D:\IA\envs\wpp\pythonw.exe'
$vigilar = "$HOME\.claude\skills\avisar\scripts\vigilar.py"
$config  = "$raiz\vigilar.json"
$tarea   = 'Vigia WhatsApp transcriptor'
$inicio  = [Environment]::GetFolderPath('Startup')
$vbs     = Join-Path $inicio 'vigia-whatsapp-transcriptor.vbs'
$SEG     = 600

foreach ($f in @($python, $pythonw, $vigilar, $config)) {
  if (-not (Test-Path $f)) { throw "No encuentro $f. No instalo nada a medias." }
}

# Prueba antes de instalar: si el chequeo no sabe contestar, la tarea tampoco va a
# saber, y un vigia que falla en silencio es peor que ninguno.
Write-Host "Probando el chequeo antes de instalar..." -ForegroundColor Cyan
& $python $vigilar --config $config --probar --una-vez
Remove-Item "$config.estado.json" -ErrorAction SilentlyContinue

$puesto = ''

# --- Camino 1: la tarea programada -------------------------------------------
try {
  if (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $tarea -Confirm:$false -ErrorAction Stop
  }
  $accion = New-ScheduledTaskAction -Execute $python `
    -Argument "`"$vigilar`" --config `"$config`" --una-vez" -WorkingDirectory $raiz
  $disp = New-ScheduledTaskTrigger -AtLogOn
  $disp.Delay = 'PT2M'
  $disp.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Seconds $SEG)).Repetition
  # Que corra aunque la laptop este a bateria: es justo cuando nadie la mira.
  $opc = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
  Register-ScheduledTask -TaskName $tarea -Action $accion -Trigger $disp `
    -Settings $opc -Description 'Avisa por Telegram si el WhatsApp del transcriptor se desvincula.' `
    -ErrorAction Stop | Out-Null
  # Verificar, no confiar: aca es donde mentia la version vieja.
  if (Get-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue) {
    Start-ScheduledTask -TaskName $tarea -ErrorAction SilentlyContinue
    $puesto = 'tarea'
  }
} catch {
  Write-Host "  La tarea programada pide administrador. Voy por la carpeta de Inicio." -ForegroundColor Yellow
}

# --- Camino 2: la carpeta de Inicio ------------------------------------------
if (-not $puesto) {
  # Un proceso que se queda mirando cada $SEG segundos, sin ventana (pythonw).
  $linea = 'CreateObject("WScript.Shell").Run """' + $pythonw + '"" ""' + $vigilar +
           '"" --config ""' + $config + '"" --cada ' + $SEG + '", 0, False'
  Set-Content -Path $vbs -Value $linea -Encoding ASCII
  if (-not (Test-Path $vbs)) { throw "No pude escribir $vbs. No quedo nada instalado." }

  # No dejar dos vigias mirando lo mismo: el de antes, si estaba, se apaga.
  Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
    Where-Object { $_.CommandLine -like '*vigilar.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

  Start-Process -FilePath 'wscript.exe' -ArgumentList "`"$vbs`"" -WindowStyle Hidden
  Start-Sleep -Seconds 3
  $vivo = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
          Where-Object { $_.CommandLine -like '*vigilar.py*' }
  if ($vivo) { $puesto = 'inicio' }
}

# --- El informe, que dice la verdad ------------------------------------------
Write-Host ""
if ($puesto -eq 'tarea') {
  Write-Host "LISTO. Quedo como tarea programada, mirando cada $($SEG/60) minutos." -ForegroundColor Green
  Write-Host "  Se ve con:    Get-ScheduledTask -TaskName '$tarea'"
  Write-Host "  Se saca con:  Unregister-ScheduledTask -TaskName '$tarea' -Confirm:`$false"
} elseif ($puesto -eq 'inicio') {
  Write-Host "LISTO. Quedo en la carpeta de Inicio, mirando cada $($SEG/60) minutos." -ForegroundColor Green
  Write-Host "  Ya esta corriendo ahora, y vuelve a arrancar solo cada vez que inicies sesion."
  Write-Host "  Se ve con:    Get-CimInstance Win32_Process -Filter `"Name like '%python%'`" | Where-Object { `$_.CommandLine -like '*vigilar.py*' }"
  Write-Host "  Se saca con:  Remove-Item '$vbs'   (y matar el proceso)"
} else {
  Write-Host "NO QUEDO INSTALADO NADA. El vigia no esta mirando." -ForegroundColor Red
  Write-Host "  La tarea programada pide administrador y el arranque por la carpeta de Inicio tampoco levanto."
  Write-Host "  Probalo a mano para ver el error:"
  Write-Host "    & '$pythonw' '$vigilar' --config '$config' --cada $SEG"
  exit 1
}
