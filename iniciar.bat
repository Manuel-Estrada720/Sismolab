@echo off
REM SismoLab AVL - doble clic para iniciar (Windows)
cd /d "%~dp0"
title SismoLab AVL

REM 1. Find Python: "python" or the Windows launcher "py"
set PY=python
python --version >nul 2>&1
if errorlevel 1 set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 goto nopython

REM 2. Open the window (only the standard library is needed: nothing to install)
echo Abriendo SismoLab AVL...
%PY% main.py
if errorlevel 1 (
  echo.
  echo El programa termino con un error. Copie el mensaje de arriba para revisarlo.
  pause
)
exit /b 0

:nopython
echo No se encontro Python en este computador.
echo Instale Python 3.8 o superior desde https://www.python.org/downloads/
echo y en el instalador marque "Add python.exe to PATH" y "tcl/tk and IDLE".
pause
exit /b 1
