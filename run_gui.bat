@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ════════════════════════════════════════════════════════
echo   arqParse GUI — Запуск
echo ════════════════════════════════════════════════════════
echo.

:: 1. Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python не найден. Установите Python 3.8+
    echo     https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo [+] Python найден: %PY_VER%

:: 2. Проверка Tkinter
python -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [X] Tkinter не установлен.
    echo     Переустановите Python с опцией "tcl/tk"
    pause
    exit /b 1
)
echo [+] Tkinter установлен

:: 3. Создание venv если нет
if not exist "venv\Scripts\python.exe" (
    echo [*] Виртуальное окружение не найдено — создаю...
    python -m venv venv
    echo [+] venv создан
)

:: 4. Установка зависимостей
if exist "requirements.txt" (
    echo [*] Устанавливаю зависимости...
    call venv\Scripts\python.exe -m pip install --upgrade pip -q 2>nul
    call venv\Scripts\pip.exe install -r requirements.txt -q 2>nul
    echo [+] Зависимости готовы
)

echo.
echo [+] Всё готово
echo [^>] Запускаю arqParse GUI...
echo ════════════════════════════════════════════════════════
echo.

:: Запуск GUI
venv\Scripts\python.exe main.py --gui
