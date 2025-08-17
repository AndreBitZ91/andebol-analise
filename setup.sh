#!/bin/bash
# setup.sh — prepara o ambiente (venv + deps) para a app Streamlit (teste.py)

set -e

echo "🔧 Início do setup do projeto..."

# Criar ambiente virtual se não existir
if [ ! -d "venv" ]; then
    echo "📂 A criar ambiente virtual..."
    python3 -m venv venv
fi

# Ativar venv
echo "🚀 A ativar ambiente virtual..."
source venv/bin/activate

# Atualizar pip
echo "⬆️ A atualizar pip..."
python -m pip install --upgrade pip

# Instalar dependências
if [ -f "requirements.txt" ]; then
    echo "📦 A instalar dependências do requirements.txt..."
    pip install -r requirements.txt
else
    echo "⚠️ Não encontrei requirements.txt, a instalar pacotes básicos..."
    pip install streamlit pandas openpyxl watchdog
fi

echo "✅ Setup concluído com sucesso!"
echo "Para iniciar a app manualmente, corre:"
echo "streamlit run teste.py"
