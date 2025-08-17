#!/bin/bash
# Script para arrancar a app de Andebol (teste.py)

# Ir para a pasta do projeto
cd "$(dirname "$0")"

# Ativar ambiente virtual
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️ Ambiente virtual não encontrado. Criar com: python3 -m venv venv"
    exit 1
fi

# Instalar dependências se não existirem
pip install -r requirements.txt

# Correr o Streamlit
streamlit run teste.py
