@echo off
chcp 65001 >nul
title Transcriptor WhatsApp - RTX 4070

if "%~1"=="" (
    echo.
    echo   Arrastra un audio o video encima de este archivo para transcribirlo.
    echo.
    pause
    exit /b
)

rem -m necesita que la carpeta del proyecto sea el directorio actual, para que
rem Python encuentre el paquete `app`. El archivo arrastrado llega con ruta
rem absoluta en %~1, asi que cambiar de carpeta no lo afecta.
cd /d "D:\IA\wpp-transcriptor"

"D:\IA\envs\wpp\python.exe" -m app.nucleo.transcribir "%~1"

echo.
echo ============================================
echo   Terminado. Podes cerrar esta ventana.
echo ============================================
pause
