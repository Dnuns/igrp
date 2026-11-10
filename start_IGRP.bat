@echo off
setlocal
title IGRP SCRIPT
cd /d "%~dp0"

rem Use UTF-8 so accented names (turma, paths) print correctly.
chcp 65001 >nul
set "PYTHONUTF8=1"

rem Prefer the local virtual environment when it exists.
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" "%~dp0igrp-script.py"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
pause
exit /b %EXIT_CODE%
