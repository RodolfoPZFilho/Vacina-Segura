"""API do VacinaSegura.

Executar (dentro da pasta backend, com o ambiente virtual ativo):
    uvicorn app.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query

from . import config, influx, mqtt_consumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

Periodo = Literal["15m", "1h", "6h", "24h", "7d"]
# Identificadores aceitos: letras, numeros, _ e - (evita injecao na consulta Flux)
ID = Annotated[str, Query(pattern=r"^[A-Za-z0-9_-]{1,32}$")]


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    mqtt_consumer.iniciar()
    yield
    mqtt_consumer.parar()
    influx.fechar()


app = FastAPI(title="VacinaSegura API", version="0.1.0", lifespan=ciclo_de_vida)


def _status(temperatura: float | None) -> str:
    if temperatura is None:
        return "sem_dados"
    if temperatura < config.TEMP_MIN:
        return "abaixo"
    if temperatura > config.TEMP_MAX:
        return "acima"
    return "ok"


@app.get("/api/saude")
def saude():
    """Situação do backend e da conexão com o Mosquitto."""
    return {"api": "ok", "mqtt": mqtt_consumer.estado}


@app.get("/api/config")
def configuracao():
    """Faixa segura usada pelo dashboard."""
    return {"temp_min": config.TEMP_MIN, "temp_max": config.TEMP_MAX}


@app.get("/api/geladeiras")
def geladeiras():
    """Geladeiras que já enviaram dados, com a última temperatura de cada uma."""
    itens = influx.listar_geladeiras()
    for item in itens:
        item["status"] = _status(item["temperatura"])
    return itens


@app.get("/api/leituras/atual")
def leitura_atual(ubs: ID, geladeira: ID):
    leitura = influx.leitura_atual(ubs, geladeira)
    if leitura is None:
        raise HTTPException(status_code=404, detail="Nenhuma leitura encontrada para esta geladeira.")
    leitura["status"] = _status(leitura["temperatura"])
    return leitura


@app.get("/api/leituras/historico")
def historico(ubs: ID, geladeira: ID, periodo: Periodo = "1h"):
    """Histórico agregado para o gráfico + estatísticas do período."""
    return {
        "periodo": periodo,
        "pontos": influx.historico(ubs, geladeira, periodo),
        "estatisticas": influx.estatisticas(ubs, geladeira, periodo),
    }
