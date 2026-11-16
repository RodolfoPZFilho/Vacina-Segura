"""Consulta a API de gerenciamento do RabbitMQ (o navegador nunca fala direto com o broker)."""
from __future__ import annotations

from urllib.parse import quote

import httpx

from ..comum.config import VHOST, env

_BASE = f"http://{env('RABBIT_HOST', 'rabbitmq')}:15672/api"
_AUTH = (env("RABBIT_API_USUARIO"), env("RABBIT_API_SENHA"))
_VH = quote(VHOST, safe="")


def _taxa(stats: dict | None, chave: str) -> float:
    return round(float(((stats or {}).get(f"{chave}_details") or {}).get("rate", 0.0)), 2)


async def painel() -> dict:
    async with httpx.AsyncClient(base_url=_BASE, auth=_AUTH, timeout=5) as c:
        filas = (await c.get(f"/queues/{_VH}")).json()
        overview = (await c.get("/overview")).json()
        consumidores = (await c.get(f"/consumers/{_VH}")).json()
        conexoes = (await c.get("/connections")).json()
    return {
        "filas": [
            {
                "nome": q["name"],
                "mensagens": q.get("messages", 0),
                "prontas": q.get("messages_ready", 0),
                "nao_confirmadas": q.get("messages_unacknowledged", 0),
                "consumidores": q.get("consumers", 0),
                "taxa_publicacao": _taxa(q.get("message_stats"), "publish"),
                "taxa_entrega": _taxa(q.get("message_stats"), "deliver_get"),
                "taxa_confirmacao": _taxa(q.get("message_stats"), "ack"),
                "dlq": "x-dead-letter-exchange" in (q.get("arguments") or {}),
                "argumentos": q.get("arguments") or {},
            }
            for q in sorted(filas, key=lambda x: x["name"])
        ],
        "totais": {
            "publicacao": _taxa(overview.get("message_stats"), "publish"),
            "entrega": _taxa(overview.get("message_stats"), "deliver_get"),
            "mensagens": (overview.get("queue_totals") or {}).get("messages", 0),
        },
        "consumidores": [
            {"fila": c["queue"]["name"], "usuario": (c.get("channel_details") or {}).get("user"),
             "conexao": (c.get("channel_details") or {}).get("connection_name"), "prefetch": c.get("prefetch_count")}
            for c in consumidores
        ],
        "conexoes": [
            {"nome": (cx.get("client_properties") or {}).get("connection_name") or cx.get("name"),
             "usuario": cx.get("user"), "estado": cx.get("state")}
            for cx in conexoes if cx.get("vhost") == VHOST
        ],
    }


async def espiar_dlq(qtd: int = 20) -> list[dict]:
    """Le mensagens da DLQ sem remove-las (ackmode requeue)."""
    async with httpx.AsyncClient(base_url=_BASE, auth=_AUTH, timeout=5) as c:
        r = await c.post(f"/queues/{_VH}/q.dlq/get",
                         json={"count": qtd, "ackmode": "ack_requeue_true", "encoding": "auto", "truncate": 4000})
        r.raise_for_status()
        itens = r.json()
    saida = []
    for m in itens:
        props = m.get("properties") or {}
        mortes = (props.get("headers") or {}).get("x-death") or [{}]
        saida.append({
            "routing_key": m.get("routing_key"),
            "payload": m.get("payload"),
            "fila_origem": mortes[0].get("queue"),
            "motivo": mortes[0].get("reason"),
            "vezes": mortes[0].get("count"),
        })
    return saida


async def esvaziar_dlq():
    async with httpx.AsyncClient(base_url=_BASE, auth=_AUTH, timeout=5) as c:
        r = await c.delete(f"/queues/{_VH}/q.dlq/contents")
        r.raise_for_status()


async def ping() -> bool:
    try:
        async with httpx.AsyncClient(base_url=_BASE, auth=_AUTH, timeout=3) as c:
            return (await c.get("/overview")).status_code == 200
    except httpx.HTTPError:
        return False
