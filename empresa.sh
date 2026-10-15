#!/usr/bin/env bash
# Atalho para controlar o My AI Office.
#   ./empresa.sh trabalhar   -> turno em segundo plano (normalmente via systemd)
#   ./empresa.sh servir      -> dashboard em http://127.0.0.1:8770
#   ./empresa.sh tudo        -> dashboard + turno no mesmo processo
#   ./empresa.sh um-ciclo    -> executa uma rodada e sai
#   ./empresa.sh status      -> resumo no terminal
#   ./empresa.sh doutor      -> checa ollama/opencode/modelos
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:/usr/local/bin:/usr/bin:$PATH"
exec /usr/bin/python3 -m empresa "${@:-status}"
