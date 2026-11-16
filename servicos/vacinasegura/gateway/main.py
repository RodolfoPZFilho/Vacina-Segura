"""Gateway MQTT <-> RabbitMQ.

  Mosquitto  vacinasegura/telemetria/<ubs>/<tipo>/<id>  ->  RabbitMQ telemetry.<ubs>.<tipo>.<id>
  RabbitMQ   q.comandos (command.<ubs>.<id>)             ->  Mosquitto vacinasegura/comando/<ubs>/<id>

Mensagens invalidas vindas do MQTT sao descartadas com log; comandos que falham
no envio vao para a DLQ (nack sem requeue).
"""
import asyncio
import logging

import paho.mqtt.client as mqtt

from ..comum import mensagens
from ..comum.amqp import Barramento
from ..comum.config import env, env_int
from ..comum.saude import batimento_continuo, configurar_logs

log = logging.getLogger("gateway")
PREFIXO = "vacinasegura"


async def main():
    configurar_logs()
    loop = asyncio.get_running_loop()
    fila: asyncio.Queue = asyncio.Queue(maxsize=10_000)
    bus = await Barramento("RABBIT_GATEWAY_USUARIO", "RABBIT_GATEWAY_SENHA").conectar()

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gateway")
    cli.username_pw_set(env("MQTT_GATEWAY_USUARIO", "gateway"), env("MQTT_GATEWAY_SENHA"))
    cli.reconnect_delay_set(1, 30)
    conectado = asyncio.Event()

    def on_connect(c, _u, _f, rc, _p=None):
        log.info("Conectado ao Mosquitto (rc=%s)", rc)
        c.subscribe(f"{PREFIXO}/telemetria/+/+/+", qos=0)
        loop.call_soon_threadsafe(conectado.set)

    def on_message(_c, _u, m):
        def _por():
            try:
                fila.put_nowait((m.topic, m.payload))
            except asyncio.QueueFull:
                log.warning("Fila interna cheia; telemetria descartada")
        loop.call_soon_threadsafe(_por)

    cli.on_connect = on_connect
    cli.on_message = on_message
    host, porta = env("MQTT_HOST", "mosquitto"), env_int("MQTT_PORTA", 1883)
    while True:
        try:
            cli.connect(host, porta, keepalive=30)
            break
        except OSError as e:
            log.warning("Mosquitto indisponivel (%s)", e)
            await asyncio.sleep(3)
    cli.loop_start()

    async def comando(msg: dict, rk: str):
        # rk = command.<ubs>.<dispositivo>
        partes = rk.split(".")
        if len(partes) != 3:
            raise ValueError(f"routing key de comando invalida: {rk}")
        _, ubs, disp = partes
        topico = f"{PREFIXO}/comando/{ubs}/{disp}"
        reter = ubs == "sistema" and disp == "config"
        info = cli.publish(topico, mensagens.codificar(msg), qos=1, retain=reter)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"falha ao publicar no MQTT (rc={info.rc})")
        log.info("Comando -> %s %s", topico, msg["conteudo"].get("acao", ""))

    await bus.consumir("q.comandos", comando)
    asyncio.create_task(batimento_continuo())

    while True:
        topico, payload = await fila.get()
        try:
            msg = mensagens.decodificar(payload)
            _, _, ubs, tipo, disp = topico.split("/")
            rk = f"telemetry.{mensagens.seguro(ubs)}.{mensagens.seguro(tipo)}.{mensagens.seguro(disp)}"
            await bus.publicar(rk, msg, persistente=False)
        except Exception as e:  # noqa: BLE001
            log.warning("Telemetria invalida em %s: %s", topico, e)


if __name__ == "__main__":
    asyncio.run(main())
