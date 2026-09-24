@echo off
chcp 65001 >nul
title Bot Telegram - Transcriptor RTX 4070
cd /d "D:\IA\wpp-transcriptor"
echo Iniciando el bot... (dejalo abierto mientras lo uses)
echo.
"D:\IA\envs\wpp\python.exe" -m app.ingesta.bot_telegram
echo.
echo El bot se detuvo.
pause
