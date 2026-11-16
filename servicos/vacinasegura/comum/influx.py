"""Acesso ao InfluxDB (leituras ao vivo no bucket 'leituras', amostras do laboratorio em 'lab')."""
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import ASYNCHRONOUS, SYNCHRONOUS, WriteOptions

from .config import env

BUCKET_LEITURAS = env("INFLUX_BUCKET", "leituras")
BUCKET_LAB = env("INFLUX_BUCKET_LAB", "lab")


def cliente() -> InfluxDBClient:
    return InfluxDBClient(url=env("INFLUX_URL", "http://influxdb:8086"), token=env("INFLUX_TOKEN"),
                          org=env("INFLUX_ORG", "vacinasegura"), timeout=20_000)


def garantir_bucket(cli: InfluxDBClient, nome: str, retencao_s: int = 0):
    api = cli.buckets_api()
    if api.find_bucket_by_name(nome) is None:
        from influxdb_client import BucketRetentionRules
        regras = [BucketRetentionRules(type="expire", every_seconds=retencao_s)] if retencao_s else []
        api.create_bucket(bucket_name=nome, retention_rules=regras, org=env("INFLUX_ORG", "vacinasegura"))


__all__ = ["cliente", "garantir_bucket", "BUCKET_LEITURAS", "BUCKET_LAB", "SYNCHRONOUS", "ASYNCHRONOUS", "WriteOptions"]
