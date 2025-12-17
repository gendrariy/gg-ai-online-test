@echo off
chcp 65001 >nul
REM ==========================================
REM  Запуск AI Assistant — Jewelry Production
REM  Author: Gennadiy (ProjectAi_Modular)
REM ==========================================

REM Путь к виртуальному окружению
set VENV_PATH=C:\2_Script_for_download_PDF\GPT_Ai\venv

REM Activate the virtual environment
call "%VENV_PATH%\Scripts\activate.bat"

REM Переходим в папку проекта
cd /d C:\2_Script_for_download_PDF\GPT_Ai\ProjectAi_Modular

REM Запускаем Streamlit-приложение
echo Запуск AI Assistant...
streamlit run main_app.py

REM После выхода из Streamlit окно не закрываем сразу
pause
