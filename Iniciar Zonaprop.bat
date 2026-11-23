@echo off
title Zonaprop Alquileres · Auditor Forense
color 0b
cls
echo ======================================================================
echo    ZONAPROP ALQUILERES - AUDITOR FORENSE INMOBILIARIO
echo ======================================================================
echo  Iniciando menu visual...
echo.

cd /d "%~dp0"

rem Se usa el Python del entorno virtual si existe: es el que tiene todas las
rem dependencias (requirements.txt). El "python" del PATH puede ser otra
rem instalacion a la que le falte alguna, por ejemplo anthropic, y el menu
rem lanza cada paso con el mismo Python con el que se abrio.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" zp.py menu
) else (
    python zp.py menu
)

if errorlevel 1 (
    echo.
    echo [ERROR] Ocurrio un problema al ejecutar la aplicacion.
    echo Presiona cualquier tecla para cerrar.
    pause >nul
)
