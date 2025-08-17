@echo off
echo ============================================
echo   Handball Stats App - Setup e Arranque
echo ============================================
echo.

REM Ir para a pasta do script
cd /d %~dp0

REM 1) Criar/ativar venv
if exist venv (
    echo Ambiente virtual encontrado. Ativando...
    call venv\Scripts\activate
) else (
    echo A criar ambiente virtual...
    py -3 -m venv venv || python -m venv venv
    call venv\Scripts\activate
)

REM 2) Atualizar pip
python -m pip install --upgrade pip

REM 3) Instalar dependencias
if exist requirements.txt (
    echo A instalar dependencias do requirements.txt...
    pip install -r requirements.txt
) else (
    echo requirements.txt nao encontrado. A instalar pacotes minimos...
    pip install streamlit pandas openpyxl watchdog
)

REM 4) Aviso Excel
if not exist Plantel.xlsx (
    echo Aviso: 'Plantel.xlsx' nao encontrado. Podes carregar pelo uploader quando a app abrir.
)

REM 5) Iniciar a aplicação
echo.
echo A iniciar a aplicação Streamlit...
python -m streamlit run teste.py
pause
