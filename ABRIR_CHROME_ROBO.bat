@echo off
title Abrindo Chrome para o Robo (Credos)
echo 🛑 FECHANDO ABSOLUTAMENTE TUDO DO CHROME...
powershell -Command "Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force"
timeout /t 3 >nul
echo 🚀 Abrindo seu Chrome (Perfil 3) com porta de automação...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --profile-directory="Profile 3" "https://www.pesquisaprotesto.com.br/login"
echo.
echo ✅ Chrome aberto!
echo ---------------------------------------------------------
echo 🛠️ INSTRUÇÕES:
echo 1. Faça o login nesta janela.
echo 2. Chegue no 'Painel'.
echo 3. Volte no terminal e rode: python teste_cartorio_simulado.py
echo ---------------------------------------------------------
echo.
pause
