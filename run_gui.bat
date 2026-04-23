@echo off
TITLE arqParse GUI
echo Запуск arqParse GUI...

if exist venv\Scripts\python.exe (
    set PYTHON_BIN=venv\Scripts\python.exe
) else (
    set PYTHON_BIN=python
)

%PYTHON_BIN% main.py --gui
if %errorlevel% neq 0 pause
