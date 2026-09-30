"""Acesso ao InfluxDB: gravação e consulta das leituras das geladeiras."""
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from . import config

_cliente = InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
_escrita = _cliente.write_api(write_options=SYNCHRONOUS)
_consulta = _cliente.query_api()

# Período pedido pelo dashboard -> janela de agregação do gráfico
PERIODOS = {
    "15m": "10s",
    "1h": "30s",
    "6h": "2m",
    "24h": "10m",
    "7d": "1h",
    "10d": "1h",
}

_BASE = f'from(bucket: "{config.INFLUX_BUCKET}")'


def gravar_leitura(ubs: str, geladeira: str, temperatura: float, umidade: float | None) -> None:
    ponto = (
        Point(config.MEASUREMENT)
        .tag("ubs", ubs)
        .tag("geladeira", geladeira)
        .field("temperatura", float(temperatura))
        .time(datetime.now(timezone.utc))
    )
    if umidade is not None:
        ponto = ponto.field("umidade", float(umidade))
    _escrita.write(bucket=config.INFLUX_BUCKET, record=ponto)


def _filtro(ubs: str, geladeira: str) -> str:
    # ubs e geladeira já chegam validados (apenas letras, números, _ e -)
    return (
        f'|> filter(fn: (r) => r._measurement == "{config.MEASUREMENT}" '
        f'and r.ubs == "{ubs}" and r.geladeira == "{geladeira}")'
    )


def listar_geladeiras() -> list[dict]:
    flux = f"""
    {_BASE}
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "{config.MEASUREMENT}" and r._field == "temperatura")
      |> group(columns: ["ubs", "geladeira"])
      |> last()
    """
    resultado = []
    for tabela in _consulta.query(flux):
        for r in tabela.records:
            resultado.append({
                "ubs": r.values["ubs"],
                "geladeira": r.values["geladeira"],
                "temperatura": r.get_value(),
                "horario": r.get_time().isoformat(),
            })
    return sorted(resultado, key=lambda g: (g["ubs"], g["geladeira"]))


def leitura_atual(ubs: str, geladeira: str) -> dict | None:
    flux = f"""
    {_BASE}
      |> range(start: -30d)
      {_filtro(ubs, geladeira)}
      |> last()
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    """
    for tabela in _consulta.query(flux):
        for r in tabela.records:
            return {
                "horario": r.get_time().isoformat(),
                "temperatura": r.values.get("temperatura"),
                "umidade": r.values.get("umidade"),
            }
    return None


def historico(ubs: str, geladeira: str, periodo: str) -> list[dict]:
    janela = PERIODOS[periodo]
    flux = f"""
    {_BASE}
      |> range(start: -{periodo})
      {_filtro(ubs, geladeira)}
      |> aggregateWindow(every: {janela}, fn: mean, createEmpty: false)
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    """
    pontos = []
    for tabela in _consulta.query(flux):
        for r in tabela.records:
            temp = r.values.get("temperatura")
            umid = r.values.get("umidade")
            pontos.append({
                "horario": r.get_time().isoformat(),
                "temperatura": round(temp, 2) if temp is not None else None,
                "umidade": round(umid, 1) if umid is not None else None,
            })
    return pontos


def estatisticas(ubs: str, geladeira: str, periodo: str) -> dict:
    """Mínima, máxima, média e quantidade de leituras fora da faixa (dados brutos)."""
    base = f"""
    {_BASE}
      |> range(start: -{periodo})
      {_filtro(ubs, geladeira)}
      |> filter(fn: (r) => r._field == "temperatura")
    """
    def _valor(sufixo: str):
        for tabela in _consulta.query(base + sufixo):
            for r in tabela.records:
                return r.get_value()
        return None

    fora = (
        f"|> filter(fn: (r) => r._value < {config.TEMP_MIN} or r._value > {config.TEMP_MAX})"
        "|> count()"
    )
    minima = _valor("|> min()")
    maxima = _valor("|> max()")
    media = _valor("|> mean()")
    return {
        "minima": round(minima, 2) if minima is not None else None,
        "maxima": round(maxima, 2) if maxima is not None else None,
        "media": round(media, 2) if media is not None else None,
        "total_leituras": _valor("|> count()") or 0,
        "leituras_fora_da_faixa": _valor(fora) or 0,
    }


def fechar() -> None:
    _cliente.close()
