"""Gravador: consome q.gravador e grava telemetria e previsoes no InfluxDB (bucket 'leituras').

  measurement 'leitura'  tags: dispositivo, ubs, grandeza   fields: valor | vibracao, corrente, ...
  measurement 'previsao' tags: dispositivo, ubs             fields: rul_h, saude
"""
import asyncio
import logging
from datetime import datetime

from influxdb_client import Point, WritePrecision

from ..comum import influx
from ..comum.amqp import Barramento
from ..comum.saude import batimento_continuo, configurar_logs

log = logging.getLogger("gravador")
CAMPOS_NUMERICOS = ("valor", "vibracao", "corrente", "temp_compressor")


def para_ponto(msg: dict, rk: str) -> Point | None:
    c = msg["conteudo"]
    ts = datetime.fromisoformat(msg["ts"].replace("Z", "+00:00"))
    if msg["tipo"] == "telemetria":
        p = (Point("leitura").tag("dispositivo", msg["dispositivo"]).tag("ubs", msg.get("ubs", ""))
             .tag("grandeza", str(c.get("grandeza", rk.split(".")[2] if rk.count(".") >= 3 else ""))))
        tem = False
        for campo in CAMPOS_NUMERICOS:
            if isinstance(c.get(campo), (int, float)):
                p = p.field(campo, float(c[campo]))
                tem = True
        return p.time(ts, WritePrecision.MS) if tem else None
    if msg["tipo"] == "previsao":
        p = Point("previsao").tag("dispositivo", msg["dispositivo"]).tag("ubs", msg.get("ubs", ""))
        tem = False
        for campo in ("rul_h", "saude"):
            if isinstance(c.get(campo), (int, float)):
                p = p.field(campo, float(c[campo])); tem = True
        return p.time(ts, WritePrecision.MS) if tem else None
    return None


async def main():
    configurar_logs()
    cli = influx.cliente()
    while True:
        try:
            if cli.ping():
                break
        except Exception:  # noqa: BLE001
            pass
        log.info("Aguardando InfluxDB...")
        await asyncio.sleep(3)
    escrita = cli.write_api(write_options=influx.SYNCHRONOUS)
    bus = await Barramento("RABBIT_GRAVADOR_USUARIO", "RABBIT_GRAVADOR_SENHA", prefetch=200).conectar()
    contador = {"n": 0}

    async def gravar(msg: dict, rk: str):
        ponto = para_ponto(msg, rk)
        if ponto is None:
            return
        await asyncio.to_thread(escrita.write, bucket=influx.BUCKET_LEITURAS, record=ponto)
        contador["n"] += 1
        if contador["n"] % 500 == 0:
            log.info("%d pontos gravados", contador["n"])

    await bus.consumir("q.gravador", gravar)
    await batimento_continuo()


if __name__ == "__main__":
    asyncio.run(main())
