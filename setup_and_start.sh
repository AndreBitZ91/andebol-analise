#!/bin/bash
# Setup + Start para a app de Andebol (teste.py)

set -e

echo "🔧 Setup inicial..."

# Ir para a pasta do projeto
cd "$(dirname "$0")"

# 1) Criar venv se não existir
if [ ! -d "venv" ]; then
  echo "📂 A criar ambiente virtual em ./venv"
  python3 -m venv venv
fi

# 2) Ativar venv
echo "🚀 A ativar ambiente virtual..."
source venv/bin/activate

# 3) Atualizar pip (opcional mas recomendado)
echo "⬆️ A atualizar pip..."
python -m pip install --upgrade pip

# 4) Instalar dependências
if [ -f "requirements.txt" ]; then
  echo "📦 A instalar dependências do requirements.txt..."
  pip install -r requirements.txt
else
  echo "⚠️ 'requirements.txt' não encontrado. A instalar pacotes mínimos..."
  pip install streamlit pandas openpyxl watchdog
fi

# 5) Verificar ficheiro Excel
if [ ! -f "Plantel.xlsx" ]; then
  echo "⚠️ Aviso: 'Plantel.xlsx' não encontrado na pasta do projeto."
  echo "   Podes carregá-lo pelo uploader do Streamlit quando a app arrancar."
fi

# 6) Arrancar a app
echo "✅ Setup concluído. A iniciar Streamlit..."
exec streamlit run teste.py
