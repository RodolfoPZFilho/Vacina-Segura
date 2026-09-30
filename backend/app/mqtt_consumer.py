"""Assinante MQTT: recebe as leituras do Mosquitto e grava no InfluxDB.

Tópico esperado:  vacinasegura/ubs/<ubs>/geladeira/<geladeira>
Payload (JSON):   {"temperatura": 5.2, "umidade": 61.0}
"""
import json
import logging
import re

import paho.mqtt.client as mqtt

from . import config, influx

log = logging.getLogger("vacinasegura.mqtt")

IDENTIFICADOR = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# Guarda a última mensagem recebida (útil para a rota /api/saude)
estado = {"conectado": False, "mensagens_recebidas": 0, "ultima_mensagem": None}


def _ao_conectar(cliente, _userdata, _flags, codigo, _props):
    if codigo == 0:
        estado["conectado"] = True
        cliente.subscribe(config.MQTT_TOPICO, qos=0)
        log.info("Conectado ao Mosquitto %s:%s, assinando %s",
                 config.MQTT_HOST, config.MQTT_PORT, config.MQTT_TOPICO)
    else:
        log.error("Falha ao conectar no Mosquitto: %s", codigo)


def _ao_desconectar(_cliente, _userdata, _flags, codigo, _props):
    estado["conectado"] = False
    log.warning("Desconectado do Mosquitto (%s). Tentando reconectar...", codigo)


def _ao_receber(_cliente, _userdata, msg):
    partes = msg.topic.split("/")
    # vacinasegura / ubs / <ubs> / geladeira / <geladeira>
    if len(partes) != 5:
        log.warning("Tópico ignorado: %s", msg.topic)
        return
    ubs, geladeira = partes[2], partes[4]
    if not (IDENTIFICADOR.match(ubs) and IDENTIFICADOR.match(geladeira)):
        log.warning("Identificadores inválidos no tópico: %s", msg.topic)
        return

    try:
        dados = json.loads(msg.payload.decode("utf-8"))
        temperatura = float(dados["temperatura"])
        umidade = dados.get("umidade")
        umidade = float(umidade) if umidade is not None else None
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as erro:
        log.warning("Payload inválido em %s: %r (%s)", msg.topic, msg.payload, erro)
        return

    try:
        influx.gravar_leitura(ubs, geladeira, temperatura, umidade)
    except Exception:  # noqa: BLE001 - não derrubar o consumidor por erro de gravação
        log.exception("Erro ao gravar no InfluxDB")
        return

    estado["mensagens_recebidas"] += 1
    estado["ultima_mensagem"] = {"ubs": ubs, "geladeira": geladeira, "temperatura": temperatura}
    fora = not (config.TEMP_MIN <= temperatura <= config.TEMP_MAX)
    log.info("%s/%s -> %.1f °C%s", ubs, geladeira, temperatura, "  [FORA DA FAIXA]" if fora else "")


_cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vacinasegura-backend")
_cliente.on_connect = _ao_conectar
_cliente.on_disconnect = _ao_desconectar
_cliente.on_message = _ao_receber
_cliente.reconnect_delay_set(min_delay=1, max_delay=30)


def iniciar() -> None:
    _cliente.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    _cliente.loop_start()


def parar() -> None:
    _cliente.loop_stop()
    _cliente.disconnect()
