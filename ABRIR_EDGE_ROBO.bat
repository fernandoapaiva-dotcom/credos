@echo off
title Abrindo Edge para o Robo (Credos)
echo 🛑 FECHANDO INSTANCIAS DO EDGE...
powershell -Command "Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force"
timeout /t 2 >nul
echo 🚀 Abrindo seu Microsoft Edge com porta de automação...
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Microsoft\Edge\User Data" "https://www.pesquisaprotesto.com.br/login"
echo.
echo ✅ Microsoft Edge aberto com SUCESSO!
echo ---------------------------------------------------------
echo 🛠️ INSTRUÇÕES:
echo 1. Faça o login nesta janela do Edge.
echo 2. Chegue no 'Painel'.
echo 3. Volte no terminal e rode: python teste_cartorio_simulado.py
echo ---------------------------------------------------------
echo.
pause
