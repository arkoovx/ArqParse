#!/bin/bash
# Скрипт запуска arqParse GUI — полностью автономный.
# При первом запуске создаёт venv, ставит зависимости, открывает GUI.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
PIP_BIN="$VENV_DIR/bin/pip3"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  arqParse GUI — Запуск${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo ""

# 1. Проверка Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 не найден${NC}"
    echo "Установите Python 3.8+ (python3)"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python найден: $PYTHON_VERSION"

# 2. Проверка Tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo -e "${RED}❌ Tkinter не установлен${NC}"
    echo ""
    echo "Установите одной из команд:"
    echo -e "  ${YELLOW}Ubuntu/Debian:${NC} sudo apt install python3-tk"
    echo -e "  ${YELLOW}Fedora/CentOS:${NC} sudo dnf install python3-tkinter"
    echo -e "  ${YELLOW}Arch:${NC}       sudo pacman -S tk"
    echo -e "  ${YELLOW}macOS:${NC}      brew install python-tk"
    exit 1
fi
echo -e "${GREEN}✓${NC} Tkinter установлен"

# 3. Создание venv если нет
if [ ! -f "$PYTHON_BIN" ]; then
    echo -e "${YELLOW}→${NC} Виртуальное окружение не найдено — создаю..."
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓${NC} venv создан"
fi

# 4. Установка зависимостей
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}→${NC} Устанавливаю зависимости..."
    "$PIP_BIN" install --upgrade pip -q 2>/dev/null || true
    "$PIP_BIN" install -r requirements.txt -q 2>/dev/null || true
    echo -e "${GREEN}✓${NC} Зависимости готовы"
fi

# 5. Проверка Xray (необязательно — только для тестирования)
if [ ! -f "$SCRIPT_DIR/bin/xray" ]; then
    echo -e "${YELLOW}⚠${NC} bin/xray не найден (нужен только для тестирования конфигов)"
fi

echo ""
echo -e "${GREEN}✓${NC} Всё готово"
echo -e "${CYAN}🚀 Запускаю arqParse GUI...${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo ""

# Запуск GUI
exec "$PYTHON_BIN" main.py --gui
