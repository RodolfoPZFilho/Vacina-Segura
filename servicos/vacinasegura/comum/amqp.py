"""Acesso ao RabbitMQ (AMQP) compartilhado pelos servicos.

A topologia (exchange, filas, DLQ e usuarios) e criada pelo servico rabbit-init.
Os servicos so a USAM: nao declaram nada (cada usuario tem permissao de configure vazia),
apenas publicam no exchange e consomem as proprias filas.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from . import mensagens
from .config import EXCHANGE, VHOST, env, env_int

log = logging.getLogger(__name__)

Handler = Callable[[dict, str], Awaitable[None]]


class Barramento:
    def __init__(self, usuario_env: str, senha_env: str, prefetch: int = 50):
        self.usuario = env(usuario_env)
        self.senha = env(senha_env)
        self.host = env("RABBIT_HOST", "rabbitmq")
        self.porta = env_int("RABBIT_PORTA", 5672)
        self.prefetch = prefetch
        self.conexao: aio_pika.abc.AbstractRobustConnection | None = None
        self.canal: aio_pika.abc.AbstractChannel | None = None
        self.exchange: aio_pika.abc.AbstractExchange | None = None

    async def conectar(self):
        tentativa = 0
        while True:
            try:
                self.conexao = await aio_pika.connect_robust(
                    host=self.host, port=self.porta, login=self.usuario, password=self.senha,
                    virtualhost=VHOST, client_properties={"connection_name": self.usuario},
                )
                self.canal = await self.conexao.channel(publisher_confirms=True)
                await self.canal.set_qos(prefetch_count=self.prefetch)
                self.exchange = await self.canal.get_exchange(EXCHANGE, ensure=False)
                log.info("Conectado ao RabbitMQ como %s", self.usuario)
                return self
            except Exception as e:  # noqa: BLE001
                tentativa += 1
                espera = min(30, 2 * tentativa)
                log.warning("RabbitMQ indisponivel (%s); nova tentativa em %ss", e, espera)
                await asyncio.sleep(espera)

    async def publicar(self, routing_key: str, msg: dict, persistente: bool = True):
        assert self.exchange is not None
        await self.exchange.publish(
            aio_pika.Message(
                body=mensagens.codificar(msg),
                content_type="application/json",
                message_id=msg["id"],
                type=msg["tipo"],
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT if persistente else aio_pika.DeliveryMode.NOT_PERSISTENT,
            ),
            routing_key=routing_key,
        )

    async def consumir(self, fila: str, handler: Handler):
        """Consome a fila. Erro no handler => nack sem requeue => mensagem vai para a DLQ."""
        assert self.canal is not None
        q = await self.canal.get_queue(fila, ensure=False)

        async def _on(message: AbstractIncomingMessage):
            try:
                msg = mensagens.decodificar(message.body)
                await handler(msg, message.routing_key or "")
                await message.ack()
            except Exception as e:  # noqa: BLE001
                log.exception("Falha ao processar mensagem de %s (vai para a DLQ): %s", fila, e)
                await message.nack(requeue=False)

        await q.consume(_on)
        log.info("Consumindo fila %s", fila)

    async def fechar(self):
        if self.conexao:
            await self.conexao.close()
