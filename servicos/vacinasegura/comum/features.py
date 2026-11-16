"""Calculo das variaveis de entrada (features) dos modelos.

UNICO codigo usado no treino (lab) e na inferencia em tempo real, para nao haver
divergencia entre os dois. Todas as janelas olham SO para o passado: a feature do
instante t usa as leituras t-janela+1 ... t (nunca t+1 em diante).

Entrada: series em ordem de tempo (1 leitura por tick de 5 min), podendo ter NaN
(leituras faltantes). Saida: matriz (n_ticks, n_features).
"""
from __future__ import annotations

import numpy as np

from .config import TICKS_POR_HORA

VARIAVEIS = ("vibracao", "corrente", "temp_compressor")

# Faixas fisicamente possiveis; fora disso a leitura e tratada como faltante (outlier)
FAIXAS_VALIDAS = {
    "vibracao": (0.0, 30.0),
    "corrente": (0.0, 15.0),
    "temp_compressor": (-10.0, 110.0),
}

J_CURTA = 1 * TICKS_POR_HORA     # 1 h = 12 leituras
J_LONGA = 6 * TICKS_POR_HORA     # 6 h = 72 leituras
TICKS_MINIMOS = J_CURTA          # inferencia so comeca com pelo menos 1 h de historico

NOMES_FEATURES = [
    f"{v}_{s}"
    for v in VARIAVEIS
    for s in ("media_1h", "desvio_1h", "max_1h", "media_6h", "tendencia_6h")
] + ["hora_sin", "hora_cos"]


def sanear(nome: str, x: np.ndarray) -> np.ndarray:
    lo, hi = FAIXAS_VALIDAS[nome]
    x = np.asarray(x, dtype=np.float64).copy()
    x[(x < lo) | (x > hi)] = np.nan
    return x


def _somas_moveis(x: np.ndarray, janela: int):
    """Soma e contagem moveis (ignorando NaN) da janela que TERMINA em cada instante."""
    valido = ~np.isnan(x)
    v = np.where(valido, x, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(v)])
    cn = np.concatenate([[0], np.cumsum(valido)])
    ini = np.maximum(np.arange(1, x.size + 1) - janela, 0)
    fim = np.arange(1, x.size + 1)
    return cs[fim] - cs[ini], cn[fim] - cn[ini], ini, fim


def _media_desvio(x: np.ndarray, janela: int, min_validos: int):
    s, n, ini, fim = _somas_moveis(x, janela)
    s2, _, _, _ = _somas_moveis(x * x, janela)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = s / n
        var = np.maximum(s2 / n - media * media, 0.0)
    media[n < min_validos] = np.nan
    desvio = np.sqrt(var)
    desvio[n < min_validos] = np.nan
    return media, desvio


def _maximo(x: np.ndarray, janela: int, min_validos: int):
    pad = np.concatenate([np.full(janela - 1, np.nan), x])
    vis = np.lib.stride_tricks.sliding_window_view(pad, janela)
    n = np.sum(~np.isnan(vis), axis=1)
    with np.errstate(all="ignore"):
        m = np.where(n > 0, np.nanmax(np.where(np.isnan(vis), -np.inf, vis), axis=1), np.nan)
    m[n < min_validos] = np.nan
    return m


def _tendencia(x: np.ndarray, janela: int, min_validos: int):
    """Inclinacao (unidades por hora) da reta de minimos quadrados na janela passada."""
    t = np.arange(x.size, dtype=np.float64) / TICKS_POR_HORA
    t = t - t[-1] if x.size else t           # centraliza para melhorar a precisao
    valido = ~np.isnan(x)
    tv = np.where(valido, t, 0.0)
    xv = np.where(valido, x, 0.0)
    st, n, _, _ = _somas_moveis(np.where(valido, t, np.nan), janela)
    sx, _, _, _ = _somas_moveis(np.where(valido, x, np.nan), janela)
    stt, _, _, _ = _somas_moveis(np.where(valido, tv * tv, np.nan), janela)
    stx, _, _, _ = _somas_moveis(np.where(valido, tv * xv, np.nan), janela)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = n * stt - st * st
        incl = (n * stx - st * sx) / den
    incl[(n < min_validos) | (np.abs(den) < 1e-9)] = np.nan
    return incl


def calcular(series: dict[str, np.ndarray], hora_dia: np.ndarray) -> np.ndarray:
    """Matriz de features (n_ticks, len(NOMES_FEATURES)) para UMA maquina."""
    colunas = []
    for nome in VARIAVEIS:
        x = sanear(nome, series[nome])
        m1, d1 = _media_desvio(x, J_CURTA, J_CURTA // 2)
        mx1 = _maximo(x, J_CURTA, J_CURTA // 2)
        m6, _ = _media_desvio(x, J_LONGA, J_CURTA // 2)
        tend = _tendencia(x, J_LONGA, J_CURTA)
        colunas += [m1, d1, mx1, m6, tend]
    h = np.asarray(hora_dia, dtype=np.float64)
    colunas.append(np.sin(2 * np.pi * h / 24.0))
    colunas.append(np.cos(2 * np.pi * h / 24.0))
    return np.column_stack(colunas)


def ultima_linha(series: dict[str, np.ndarray], hora_dia: np.ndarray) -> np.ndarray:
    """Features do instante mais recente (uso na inferencia ao vivo)."""
    return calcular(series, hora_dia)[-1:]
