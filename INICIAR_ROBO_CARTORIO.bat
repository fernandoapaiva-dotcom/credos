@echo off
title Robo Local de Cartorio - CREDOS
color 0B

cd /d "%~dp0"

echo Instalando dependencias do robo local (requests e playwright)...
pip install requests playwright
playwright install chromium

cls
echo ========================================================
echo INICIANDO O ROBO LOCAL DE CARTORIO...
echo Lembre-se: O navegador precisa ter sido aberto com o
echo atalho "ABRIR_CHROME_ROBO.bat" (ou EDGE) para funcionar!
echo ========================================================
echo.

python robo_cartorio.py

pause
