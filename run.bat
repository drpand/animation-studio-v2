@echo off
chcp 65001 >nul
echo ========================================
echo   ANIMATION STUDIO v2 - РОДИНА
echo ========================================
echo.

:: Проверяем зависимости
if not exist "venv" (
    echo Установка зависимостей...
    python -m pip install -r requirements.txt
    echo.
)

echo Запуск сервера на http://localhost:7860
echo.
python main.py
pause
