"""Configurações lidas do arquivo backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise RuntimeError(
            f"Variável {nome} não definida. Rode infra/configurar-influxdb.ps1 "
            "ou copie backend/.env.example para backend/.env."
        )
    return valor


INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = _obrigatoria("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "vacinasegura")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "leituras")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1884"))
MQTT_TOPICO = os.getenv("MQTT_TOPICO", "vacinasegura/ubs/+/geladeira/+")

TEMP_MIN = float(os.getenv("TEMP_MIN", "2"))
TEMP_MAX = float(os.getenv("TEMP_MAX", "8"))

# Nome da "tabela" (measurement) no InfluxDB
MEASUREMENT = "geladeira"
