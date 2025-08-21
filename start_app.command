#!/bin/zsh
cd ~/Desktop/novo

# Ativar ambiente virtual
source venv/bin/activate

# Garantir que o openpyxl está instalado
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Correr a aplicação no Streamlit
python3 -m streamlit run teste.py
