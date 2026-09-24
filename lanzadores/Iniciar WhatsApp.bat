@echo off
chcp 65001 >nul
title WhatsApp -> 4070 (webhook + tunel)
cd /d "D:\IA\wpp-transcriptor"

echo Levantando el webhook (puerto 8080)...
start "Webhook 4070" "D:\IA\envs\wpp\python.exe" -m uvicorn app.ingesta.webhook_wasender:app --host 0.0.0.0 --port 8080

echo Esperando a que el webhook arranque...
timeout /t 5 >nul

echo Levantando el tunel de Cloudflare (el hostname esta en wpp-config.yml)...
"C:\cloudflared\cloudflared.exe" tunnel --config "D:\IA\wpp-transcriptor\wpp-config.yml" run wpp-transcriptor

echo.
echo El tunel se detuvo. Podes cerrar esta ventana.
pause
