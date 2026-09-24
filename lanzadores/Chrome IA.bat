@echo off
rem Abre un Chrome dedicado para el asistente (perfil propio + puerto de depuracion local).
rem La primera vez, logueate en Gmail/Kommo/etc UNA vez; queda guardado en este perfil.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="D:\IA\chrome-ia" https://www.google.com
