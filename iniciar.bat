@echo off
rem Levanta Ollama, el backend (8000) y el frontend (5173), y abre el navegador.
rem Cada servicio queda en su propia ventana: cerrala para detenerlo.
cd /d "%~dp0"
title Historia de Las Varillas

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro .venv. Crealo e instala las dependencias:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r backend\requirements-dev.txt
    pause
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo Instalando dependencias del frontend...
    call npm --prefix frontend install
)

rem Ollama: solo se lanza si no responde (la app de escritorio puede haberlo levantado ya).
curl -s -m 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo Iniciando Ollama...
    start "Ollama" /min cmd /k ollama serve
    timeout /t 4 /nobreak >nul
)

rem Descarga el modelo local si falta.
ollama list | findstr /i "llama3.2" >nul
if errorlevel 1 (
    echo Descargando llama3.2...
    ollama pull llama3.2
)

echo Iniciando backend y frontend...
start "Backend" cmd /k ".venv\Scripts\python.exe backend\main.py"
start "Frontend" cmd /k npm --prefix frontend run dev

timeout /t 6 /nobreak >nul
start "" http://localhost:5173
