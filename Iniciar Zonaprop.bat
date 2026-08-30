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
python zp.py menu

if errorlevel 1 (
    echo.
    echo [ERROR] Ocurrio un problema al ejecutar la aplicacion.
    echo Presiona cualquier tecla para cerrar.
    pause >nul
)

