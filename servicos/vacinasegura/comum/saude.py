"""Healthcheck simples por arquivo de batimento.

O servico chama `bater()` periodicamente; o healthcheck do Docker roda
`python -m vacinasegura.comum.saude` e falha se o arquivo estiver velho.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

ARQ = Path(os.getenv("ARQ_SAUDE", "/tmp/saudavel"))
LIMITE_S = 60


def bater():
    ARQ.write_text(str(time.time()))


async def batimento_continuo(intervalo: float = 10.0):
    while True:
        bater()
        await asyncio.sleep(intervalo)


def configurar_logs():
    import logging
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)


if __name__ == "__main__":
    try:
        ok = time.time() - float(ARQ.read_text()) < LIMITE_S
    except Exception:  # noqa: BLE001
        ok = False
    sys.exit(0 if ok else 1)
