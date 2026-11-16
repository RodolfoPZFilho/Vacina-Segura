"""Leitura de configuracao por variaveis de ambiente (definidas no docker-compose.yml / .env)."""
import os


def env(nome: str, padrao: str | None = None) -> str:
    valor = os.getenv(nome, padrao)
    if valor is None or valor == "":
        raise RuntimeError(f"Variavel de ambiente obrigatoria nao definida: {nome}")
    return valor


def env_int(nome: str, padrao: int) -> int:
    return int(os.getenv(nome, str(padrao)))


def env_float(nome: str, padrao: float) -> float:
    return float(os.getenv(nome, str(padrao)))


# Constantes do dominio
TEMP_MIN = env_float("TEMP_MIN", 2.0)   # faixa segura das vacinas
TEMP_MAX = env_float("TEMP_MAX", 8.0)

# Cada leitura (tick) representa 5 minutos de operacao, tanto no gerador sintetico
# quanto no simulador ao vivo. As janelas das features sao contadas em ticks.
MINUTOS_POR_TICK = 5
TICKS_POR_HORA = 60 // MINUTOS_POR_TICK

# Teto do RUL usado nos rotulos (equipamento saudavel = "mais de 168 h (7 dias)")
RUL_TETO_H = 168.0

EXCHANGE = "vs.topic"
EXCHANGE_DLX = "vs.dlx"
VHOST = os.getenv("RABBIT_VHOST", "vacinasegura")
