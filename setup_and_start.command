#!/bin/bash
# setup_and_start.command — abre nova janela do Terminal, faz setup e arranca a app

DIR="$(cd "$(dirname "$0")" && pwd)"

/usr/bin/osascript <<EOF
tell application "Terminal"
    do script "cd \"$DIR\"; chmod +x setup.sh; ./setup.sh && source venv/bin/activate && streamlit run teste.py"
    activate
end tell
EOF
