@echo off
REM Reinicia el panel del Servidor IA (puerto 8750), esperando unos segundos primero.
REM
REM Para que existe: el panel tiene el HTML y las rutas cargados en MEMORIA, asi que
REM cualquier cambio adentro de panel.py necesita un reinicio. Y una sesion de Claude
REM lanzada desde el propio panel no puede reiniciarlo de una: se mataria a si misma
REM antes de contestar. Por eso este .bat se lanza suelto, espera, y recien ahi
REM apaga y prende.
REM
REM Uso:  "Reiniciar panel.bat" [segundos de espera, 5 por defecto] [auto]
REM
REM NO toca los servicios (voz, bot, webhook, tunel): son procesos aparte y el panel
REM solo los mira. Se relanza SIN --auto, que es como estaba corriendo.
REM EXCEPCION: con "auto" como segundo parametro se relanza CON --auto, que prende
REM todos los servicios al arrancar. Asi lo usa el boton "⟳ Reiniciar todo" del
REM panel (POST /reiniciar-todo): apaga los servicios, lanza este .bat y se deja matar.

setlocal
set ESPERA=%~1
if "%ESPERA%"=="" set ESPERA=5
set PYARGS='panel.py'
if /i "%~2"=="auto" set PYARGS='panel.py','--auto'

echo Reiniciando el panel en %ESPERA% segundos...
timeout /t %ESPERA% /nobreak >nul

REM ⚠⚠ Se busca por "panel.py" en la linea de comando Y por los DOS ejecutables,
REM python.exe y pythonw.exe (2026-08-18). Antes miraba solo python.exe y el dia que
REM el panel quedo levantado por el acceso del escritorio -- que lo abre con pythonw
REM para que no quede una ventana negra dando vueltas -- este .bat corria entero,
REM decia que reiniciaba, y NO mataba nada: el panel seguia con el codigo viejo y uno
REM se volvia loco buscando por que no aparecia el cambio en la pantalla.
REM Y se relanza con el MISMO ejecutable con el que estaba corriendo, para no
REM cambiarle a Martin la ventana (o la falta de ventana) que ya tenia.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe','pythonw.exe' -and $_.CommandLine -like '*panel.py*' }; $exe = ($p | Select-Object -First 1).ExecutablePath; if (-not $exe) { $exe = 'D:\IA\envs\wpp\pythonw.exe' }; $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep -Seconds 2; Start-Process -FilePath $exe -ArgumentList %PYARGS% -WorkingDirectory 'D:\IA\wpp-transcriptor'"

endlocal
