@echo off
setlocal
cd /d "%~dp0"
title Mikoshi - Inicializador

echo.
echo ==========================================
echo   MIKOSHI // INICIALIZACAO LOCAL
echo ==========================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Docker Desktop nao foi encontrado no PATH.
  echo Instale ou inicie o Docker Desktop e tente novamente.
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [ERRO] O Docker Desktop nao esta em execucao.
  echo Abra o Docker Desktop, aguarde o Engine iniciar e execute este arquivo novamente.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [INFO] Criando .env a partir do exemplo...
  copy /Y ".env.example" ".env" >nul
)

set "MIKOSHI_OLLAMA_MODEL=llama3.2"
set "MIKOSHI_OLLAMA_PULL=true"
set "MIKOSHI_OLLAMA_LIBRARY=cpu_avx2"
if exist "config\ollama.json" (
  for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "$c=Get-Content -Raw 'config/ollama.json' ^| ConvertFrom-Json; $c.selected_model"`) do set "MIKOSHI_OLLAMA_MODEL=%%M"
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$c=Get-Content -Raw 'config/ollama.json' ^| ConvertFrom-Json; $c.auto_pull_model"`) do set "MIKOSHI_OLLAMA_PULL=%%P"
  for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "$c=Get-Content -Raw 'config/ollama.json' ^| ConvertFrom-Json; $c.llm_library"`) do set "MIKOSHI_OLLAMA_LIBRARY=%%L"
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo [AVISO] Ollama nao encontrado. A Mikoshi usara respostas locais de fallback.
) else (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags ^| Out-Null; exit 0 } catch { exit 1 }"
  if errorlevel 1 (
    echo [INFO] Iniciando Ollama...
    start "Mikoshi Ollama" powershell -NoExit -ExecutionPolicy Bypass -Command "$env:OLLAMA_LLM_LIBRARY='%MIKOSHI_OLLAMA_LIBRARY%'; ollama serve"
    timeout /t 3 /nobreak >nul
  ) else (
    echo [INFO] Ollama ja esta em execucao. Biblioteca atual nao pode ser alterada sem reiniciar o Ollama.
  )
  if /I "%MIKOSHI_OLLAMA_PULL%"=="true" (
    ollama show "%MIKOSHI_OLLAMA_MODEL%" >nul 2>nul
    if errorlevel 1 (
      echo [INFO] Baixando modelo Ollama: %MIKOSHI_OLLAMA_MODEL%
      ollama pull "%MIKOSHI_OLLAMA_MODEL%"
    )
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Criando ambiente Python...
  py -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o ambiente Python com o comando py.
    pause
    exit /b 1
  )
)

echo [INFO] Atualizando dependencias Python...
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias Python.
  pause
  exit /b 1
)

echo [INFO] Iniciando PostgreSQL com pgvector...
docker compose up -d
if errorlevel 1 (
  echo [ERRO] Falha ao iniciar os containers.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo [INFO] Instalando dependencias do frontend...
  pushd frontend
  call npm install
  if errorlevel 1 (
    popd
    echo [ERRO] Falha ao instalar dependencias do frontend.
    pause
    exit /b 1
  )
  popd
)

echo [INFO] Abrindo backend e frontend...
start "Mikoshi Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%CD%'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000"
start "Mikoshi Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%CD%\frontend'; npm run dev"

echo.
echo Mikoshi iniciada.
echo Frontend: http://localhost:5173
echo API:      http://localhost:8000/docs
echo.
echo Esta janela pode ser fechada; backend e frontend continuarao nas janelas abertas.
pause
