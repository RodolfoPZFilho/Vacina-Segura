#!/bin/sh
# Gera o arquivo de senhas do Mosquitto a partir das variaveis de ambiente (vindas do .env).
set -e
: "${MQTT_SIMULADOR_SENHA:?defina MQTT_SIMULADOR_SENHA no .env}"
: "${MQTT_GATEWAY_SENHA:?defina MQTT_GATEWAY_SENHA no .env}"
mkdir -p /mosquitto/data
rm -f /mosquitto/data/passwd
touch /mosquitto/data/passwd
chmod 0700 /mosquitto/data/passwd
mosquitto_passwd -b /mosquitto/data/passwd simulador "$MQTT_SIMULADOR_SENHA"
mosquitto_passwd -b /mosquitto/data/passwd gateway "$MQTT_GATEWAY_SENHA"
chown -R mosquitto:mosquitto /mosquitto/data
exec "$@"
