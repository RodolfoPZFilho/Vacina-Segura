#!/bin/sh
# Baixa o modelo (so na primeira vez; fica no volume) e o deixa carregado na memoria,
# para a primeira pergunta da demonstracao nao esperar o carregamento.
set -e
MODELO="${OLLAMA_MODELO:-llama3.2:3b}"
URL="${OLLAMA_URL:-http://ollama:11434}"
echo "Baixando/verificando o modelo $MODELO ..."
curl -sf -X POST "$URL/api/pull" -d "{\"model\": \"$MODELO\", \"stream\": false}" > /dev/null
echo "Pre-carregando $MODELO na memoria ..."
curl -sf -X POST "$URL/api/generate" -d "{\"model\": \"$MODELO\", \"prompt\": \"ok\", \"keep_alive\": -1, \"stream\": false, \"options\": {\"num_ctx\": 4096}}" > /dev/null
echo "Modelo $MODELO pronto."
