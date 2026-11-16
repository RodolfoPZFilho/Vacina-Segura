"""Cria a topologia e os usuarios do RabbitMQ pela API de gerenciamento.

Roda uma vez (servico one-shot `rabbit-init`) antes dos demais servicos. E idempotente.

  exchange  vs.topic (topic)  - barramento interno
  exchange  vs.dlx   (fanout) - mensagens mortas  ->  fila q.dlq

  routing keys:
    telemetry.<ubs>.<tipo>.<dispositivo>     (gateway)
    command.<ubs>.<dispositivo>              (api)
    prediction.<ubs>.<equipamento>           (inferencia)
    alert.<ubs>.<equipamento>                (inferencia)
    job.request.<geracao|treino>             (api)
    job.progress.<tipo> / job.done.<tipo>    (lab)
"""
import logging
import sys
import time
from urllib.parse import quote

import httpx

from ..comum.config import EXCHANGE, EXCHANGE_DLX, VHOST, env
from ..comum.saude import configurar_logs

log = logging.getLogger("rabbit-init")

FILAS = {
    # nome: (bindings, argumentos extras, usa DLQ)
    "q.gravador": (["telemetry.#", "prediction.#"], {}, True),
    "q.inferencia": (["telemetry.*.compressor.*"], {}, True),
    "q.websocket": (["telemetry.#", "prediction.#", "alert.#", "job.progress.#", "job.done.#"],
                    {"x-message-ttl": 120_000, "x-max-length": 20_000}, False),
    "q.regras": (["telemetry.*.temperatura.*"], {}, True),
    "q.api.eventos": (["alert.#", "job.done.#", "job.progress.#"], {}, True),
    "q.comandos": (["command.#"], {}, True),
    "q.jobs.geracao": (["job.request.geracao"], {}, True),
    "q.jobs.treino": (["job.request.treino"], {}, True),
}

# usuario: (env da senha, configure, write, read, topic_write, tags)
USUARIOS = {
    "gateway": ("RABBIT_GATEWAY_SENHA", "^$", r"^vs\.topic$", r"^q\.comandos$", r"^telemetry\..*", ""),
    "gravador": ("RABBIT_GRAVADOR_SENHA", "^$", "^$", r"^q\.gravador$", "^$", ""),
    "inferencia": ("RABBIT_INFERENCIA_SENHA", "^$", r"^vs\.topic$", r"^q\.inferencia$", r"^(prediction|alert)\..*", ""),
    "lab": ("RABBIT_LAB_SENHA", "^$", r"^vs\.topic$", r"^q\.jobs\.(geracao|treino)$", r"^job\.(progress|done)\..*", ""),
    "api": ("RABBIT_API_SENHA", "^$", r"^vs\.topic$", r"^q\.(websocket|regras|api\.eventos|dlq)$",
            r"^(command|job\.request)\..*", "monitoring"),
}


def main():
    configurar_logs()
    base = f"http://{env('RABBIT_HOST', 'rabbitmq')}:15672/api"
    auth = (env("RABBIT_ADMIN_USUARIO"), env("RABBIT_ADMIN_SENHA"))
    vh = quote(VHOST, safe="")
    c = httpx.Client(base_url=base, auth=auth, timeout=10)

    for i in range(60):
        try:
            if c.get("/overview").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        log.info("Aguardando API de gerenciamento do RabbitMQ...")
        time.sleep(2)
    else:
        log.error("RabbitMQ nao respondeu")
        sys.exit(1)

    def put(caminho, corpo):
        r = c.put(caminho, json=corpo)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"PUT {caminho}: {r.status_code} {r.text}")

    put(f"/vhosts/{vh}", {})
    admin = auth[0]
    put(f"/permissions/{vh}/{quote(admin)}", {"configure": ".*", "write": ".*", "read": ".*"})

    put(f"/exchanges/{vh}/{EXCHANGE}", {"type": "topic", "durable": True})
    put(f"/exchanges/{vh}/{EXCHANGE_DLX}", {"type": "fanout", "durable": True})
    put(f"/queues/{vh}/q.dlq", {"durable": True, "arguments": {"x-queue-type": "classic"}})
    c.post(f"/bindings/{vh}/e/{EXCHANGE_DLX}/q/q.dlq", json={"routing_key": ""})

    for fila, (bindings, extras, dlq) in FILAS.items():
        args = dict(extras)
        if dlq:
            args["x-dead-letter-exchange"] = EXCHANGE_DLX
        put(f"/queues/{vh}/{fila}", {"durable": True, "arguments": args})
        for rk in bindings:
            r = c.post(f"/bindings/{vh}/e/{EXCHANGE}/q/{fila}", json={"routing_key": rk})
            if r.status_code not in (200, 201, 204):
                raise RuntimeError(f"binding {fila} {rk}: {r.text}")
        log.info("Fila %s ok (%s)", fila, ", ".join(bindings))

    for usuario, (senha_env, conf, wr, rd, topic_wr, tags) in USUARIOS.items():
        put(f"/users/{usuario}", {"password": env(senha_env), "tags": tags})
        put(f"/permissions/{vh}/{usuario}", {"configure": conf, "write": wr, "read": rd})
        put(f"/topic-permissions/{vh}/{usuario}", {"exchange": EXCHANGE, "write": topic_wr, "read": ".*"})
        log.info("Usuario %s ok", usuario)

    # garante que nao existe o usuario padrao guest
    if c.get("/users/guest").status_code == 200:
        c.delete("/users/guest")
        log.info("Usuario guest removido")
    log.info("Topologia do RabbitMQ pronta")


if __name__ == "__main__":
    main()
