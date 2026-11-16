"""Consultas de historico no InfluxDB (bucket 'leituras')."""
from __future__ import annotations

import asyncio
import re

from ..comum import influx

PERIODOS = {"15m": "30s", "1h": "1m", "6h": "5m", "24h": "15m", "7d": "1h"}
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_cli = None


def _api():
    global _cli
    if _cli is None:
        _cli = influx.cliente()
    return _cli.query_api()


def _historico(dispositivo: str, periodo: str, campo: str, measurement: str) -> list[dict]:
    if not _ID.match(dispositivo) or not _ID.match(campo) or periodo not in PERIODOS:
        raise ValueError("parametro invalido")
    flux = f'''
from(bucket: "{influx.BUCKET_LEITURAS}")
  |> range(start: -{periodo})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.dispositivo == "{dispositivo}" and r._field == "{campo}")
  |> aggregateWindow(every: {PERIODOS[periodo]}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
'''
    pontos = []
    for tabela in _api().query(flux):
        for r in tabela.records:
            pontos.append({"ts": r.get_time().isoformat(), "valor": round(float(r.get_value()), 3)})
    return pontos


async def historico(dispositivo: str, periodo: str, campo: str = "valor", measurement: str = "leitura") -> list[dict]:
    return await asyncio.to_thread(_historico, dispositivo, periodo, campo, measurement)


def _estatisticas(dispositivo: str, periodo: str, campo: str) -> dict:
    if not _ID.match(dispositivo) or not _ID.match(campo) or periodo not in PERIODOS:
        raise ValueError("parametro invalido")
    base = f'''from(bucket: "{influx.BUCKET_LEITURAS}") |> range(start: -{periodo})
  |> filter(fn: (r) => r._measurement == "leitura" and r.dispositivo == "{dispositivo}" and r._field == "{campo}")'''
    res = {}
    for nome in ("min", "max", "mean", "count"):
        for t in _api().query(base + f" |> {nome}()"):
            for r in t.records:
                res[nome] = round(float(r.get_value()), 2)
    return res


async def estatisticas(dispositivo: str, periodo: str, campo: str = "valor") -> dict:
    return await asyncio.to_thread(_estatisticas, dispositivo, periodo, campo)


def ping() -> bool:
    try:
        global _cli
        if _cli is None:
            _cli = influx.cliente()
        return bool(_cli.ping())
    except Exception:  # noqa: BLE001
        return False
