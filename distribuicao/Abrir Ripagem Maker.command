#!/bin/zsh
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# Prefere versões compatíveis; o inicializador também procura alternativas.
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
 if command -v "$candidate" >/dev/null; then
  "$candidate" iniciar.py "$@"
  exit $?
 fi
done
echo 'Instale Python 3.12 em https://www.python.org/downloads/ e tente novamente.'
read '?Pressione Enter para fechar…'; exit 1
