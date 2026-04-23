#!/bin/bash
# Скрипт запуска GUI для arqParse

# Получаем директорию скрипта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Путь к интерпретатору
if [ -d "venv" ]; then
    PYTHON_BIN="./venv/bin/python"
else
    PYTHON_BIN="python3"
fi

echo "Запуск arqParse GUI..."
$PYTHON_BIN main.py --gui "$@"
