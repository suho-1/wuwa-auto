@echo off
chcp 65001 >nul
title wuwa-auto
if exist "..\python\python.exe" (
    "%~dp0..\python\python.exe" "%~dp0main.py" %*
) else if exist "data\apps\ok-ww\python\python.exe" (
    "%~dp0data\apps\ok-ww\python\python.exe" "%~dp0data\apps\ok-ww\working\main.py" %*
) else (
    python "%~dp0main.py" %*
)
if errorlevel 1 pause
