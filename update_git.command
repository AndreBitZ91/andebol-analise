#!/bin/zsh
cd "$(dirname "$0")"

# Mensagem de commit com data/hora
COMMIT_MSG="Atualização automática em $(date '+%Y-%m-%d %H:%M:%S')"

echo "🔄 A adicionar alterações..."
git add -A

echo "📝 A criar commit..."
git commit -m "$COMMIT_MSG"

echo "📥 A sincronizar com o GitHub (pull --rebase)..."
git pull origin main --rebase

echo "🚀 A enviar alterações para o GitHub..."
git push origin main

echo "✅ Atualização concluída com sucesso!"
echo "Pressiona ENTER para sair."
read
