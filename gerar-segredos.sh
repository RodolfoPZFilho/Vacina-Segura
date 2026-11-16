#!/bin/sh
# Gera o arquivo .env com senhas e chaves aleatorias (ignorado pelo Git).
# Uso: ./gerar-segredos.sh [--forcar]
set -e
cd "$(dirname "$0")"
if [ -f .env ] && [ "$1" != "--forcar" ]; then
  echo ".env ja existe. Use --forcar para gerar novos segredos (e rode 'docker compose down -v')."
  exit 0
fi
s() { LC_ALL=C tr -dc 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789' </dev/urandom | head -c "${1:-24}"; }
ADMIN=$(s 12); OPER=$(s 12); VIS=$(s 12); INFLUX=$(s); PG=$(s); RADMIN=$(s)
cat > .env <<EOF
# Gerado por gerar-segredos.sh - NAO versionar (esta no .gitignore)
MQTT_SIMULADOR_SENHA=$(s)
MQTT_GATEWAY_SENHA=$(s)
RABBIT_ADMIN_USUARIO=vs-admin
RABBIT_ADMIN_SENHA=$RADMIN
RABBIT_GATEWAY_SENHA=$(s)
RABBIT_GRAVADOR_SENHA=$(s)
RABBIT_INFERENCIA_SENHA=$(s)
RABBIT_LAB_SENHA=$(s)
RABBIT_API_SENHA=$(s)
INFLUX_SENHA=$INFLUX
INFLUX_TOKEN=$(s 48)
POSTGRES_PASSWORD=$PG
JWT_SEGREDO=$(s 64)
ADMIN_SENHA=$ADMIN
OPERADOR_SENHA=$OPER
VISUALIZADOR_SENHA=$VIS
OLLAMA_MODELO=llama3.2:1b
TICK_SEGUNDOS=5
PORTA_WEB=8080
EOF
chmod 600 .env
echo "Arquivo .env criado."
echo "Usuarios: administrador=$ADMIN  operador=$OPER  visualizador=$VIS"
echo "InfluxDB http://127.0.0.1:8086 (vacinasegura / $INFLUX)"
echo "RabbitMQ http://127.0.0.1:15672 (vs-admin / $RADMIN)"
echo "Adminer  http://127.0.0.1:8081 (vacinasegura / $PG)"
echo "Proximo passo: docker compose up -d --build"
