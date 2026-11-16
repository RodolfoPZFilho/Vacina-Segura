r"""Gera dados fictícios (mas realistas) no InfluxDB para demonstração do dashboard.

Cria uma leitura por minuto, nos últimos N dias, para as geladeiras ubs01/g01 e ubs01/g02,
com ciclo do compressor, variação ao longo do dia, aberturas de porta no horário de
atendimento e alguns incidentes (queda de energia, porta esquecida aberta, termostato frio).

Uso (na pasta do projeto):
    backend\.venv\Scripts\python.exe ferramentas\gerar_dados_ficticios.py            # 10 dias
    backend\.venv\Scripts\python.exe ferramentas\gerar_dados_ficticios.py --dias 5
    backend\.venv\Scripts\python.exe ferramentas\gerar_dados_ficticios.py --limpar   # apaga as leituras antes
"""
import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from influxdb_client import InfluxDBClient, Point, WritePrecision  # noqa: E402
from influxdb_client.client.write_api import SYNCHRONOUS  # noqa: E402

from app import config  # noqa: E402  (lê backend/.env)

FUSO = timezone(timedelta(hours=-3))  # horário de Brasília

parser = argparse.ArgumentParser()
parser.add_argument("--dias", type=int, default=10)
parser.add_argument("--limpar", action="store_true", help="apaga todas as leituras antes de gerar")
parser.add_argument("--semente", type=int, default=42)
args = parser.parse_args()

agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
inicio = agora - timedelta(days=args.dias)


def incidente(t_local: datetime, dia_rel: int, hora_ini: float, duracao_h: float,
              pico: float, subida_h: float, descida_h: float) -> float:
    """Desvio de temperatura de um incidente que começa `dia_rel` dias atrás."""
    dia = (agora.astimezone(FUSO) - timedelta(days=dia_rel)).date()
    ini = datetime(dia.year, dia.month, dia.day, tzinfo=FUSO) + timedelta(hours=hora_ini)
    h = (t_local - ini).total_seconds() / 3600
    if h < 0:
        return 0.0
    if h <= duracao_h:
        return pico * min(1.0, h / subida_h)
    return pico * math.exp(-(h - duracao_h) / descida_h) if h < duracao_h + 5 * descida_h else 0.0


GELADEIRAS = {
    # base (°C), umidade base (%), incidentes
    "g01": {
        "base": 4.8, "umidade": 58,
        "incidentes": [
            # termostato regulado frio demais de madrugada -> abaixo de 2 °C
            dict(dia_rel=6, hora_ini=1.5, duracao_h=1.5, pico=-3.1, subida_h=0.8, descida_h=0.5),
        ],
    },
    "g02": {
        "base": 5.3, "umidade": 61,
        "incidentes": [
            # porta esquecida entreaberta à tarde
            dict(dia_rel=8, hora_ini=15.2, duracao_h=0.7, pico=4.4, subida_h=0.5, descida_h=0.25),
            # queda de energia à noite
            dict(dia_rel=3, hora_ini=22.0, duracao_h=3.5, pico=6.4, subida_h=3.0, descida_h=0.6),
        ],
    },
}

rnd = random.Random(args.semente)
pontos = []
for geladeira, cfg in GELADEIRAS.items():
    # sorteia aberturas de porta: dias úteis, 8h às 17h
    aberturas = []
    d = inicio.astimezone(FUSO).date()
    while d <= agora.astimezone(FUSO).date():
        if d.weekday() < 5:
            for _ in range(rnd.randint(4, 9)):
                h = rnd.uniform(8, 17)
                aberturas.append((datetime(d.year, d.month, d.day, tzinfo=FUSO) + timedelta(hours=h),
                                  rnd.uniform(1.2, 3.0)))
        d += timedelta(days=1)

    deriva_umid = 0.0
    t = inicio
    while t <= agora:
        tl = t.astimezone(FUSO)
        hora = tl.hour + tl.minute / 60
        minutos = (t - inicio).total_seconds() / 60

        temp = cfg["base"]
        temp += 0.35 * math.sin((hora - 9) / 24 * 2 * math.pi)          # mais quente à tarde
        temp += 0.55 * ((minutos % 22) / 22 - 0.5)                       # ciclo do compressor
        temp += rnd.gauss(0, 0.08)                                       # ruído do sensor
        porta = 0.0
        for momento, pico in aberturas:
            m = (tl - momento).total_seconds() / 60
            if 0 <= m < 40:
                porta += pico * math.exp(-m / 7)
        temp += porta
        for inc in cfg["incidentes"]:
            temp += incidente(tl, **inc)

        deriva_umid = max(-4, min(4, deriva_umid + rnd.gauss(0, 0.15)))
        umid = cfg["umidade"] + deriva_umid + 2.5 * porta + rnd.gauss(0, 0.4)

        pontos.append(
            Point(config.MEASUREMENT)
            .tag("ubs", "ubs01")
            .tag("geladeira", geladeira)
            .field("temperatura", round(temp, 2))
            .field("umidade", round(max(30, min(95, umid)), 1))
            .time(t, WritePrecision.S)
        )
        t += timedelta(minutes=1)

with InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG) as cliente:
    if args.limpar:
        cliente.delete_api().delete(
            datetime(1970, 1, 1, tzinfo=timezone.utc), agora + timedelta(days=1),
            f'_measurement="{config.MEASUREMENT}"', bucket=config.INFLUX_BUCKET, org=config.INFLUX_ORG,
        )
        print("Leituras anteriores apagadas.")
    escrita = cliente.write_api(write_options=SYNCHRONOUS)
    for i in range(0, len(pontos), 5000):
        escrita.write(bucket=config.INFLUX_BUCKET, record=pontos[i:i + 5000])

print(f"{len(pontos)} leituras gravadas ({args.dias} dias, geladeiras {', '.join(GELADEIRAS)}).")