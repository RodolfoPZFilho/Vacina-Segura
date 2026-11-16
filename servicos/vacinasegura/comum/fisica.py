"""Modelo fisico simplificado de uma geladeira de vacinas com compressor.

O MESMO codigo e usado:
  * pelo gerador de dados sinteticos (lab), vetorizado sobre centenas de equipamentos;
  * pelo simulador ao vivo, com poucos equipamentos.
Assim os dados de treino e os dados ao vivo seguem exatamente a mesma fisica.

Cada chamada de `passo` avanca 1 tick (5 minutos de operacao).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import MINUTOS_POR_TICK

DT_H = MINUTOS_POR_TICK / 60.0

# Modos de falha do compressor e o efeito de cada um, quando o desgaste chega a 1:
#                     vibracao corrente temp_comp perda_capacidade
MODOS_FALHA = {
    "nenhum":           (0.0,     0.0,     0.0,      0.0),
    "rolamento":        (2.6,     0.35,    0.25,     0.35),
    "entupimento":      (0.35,    0.55,    0.70,     0.80),
    "superaquecimento": (0.30,    0.40,    1.10,     0.55),
    "desbalanceamento": (2.2,     0.20,    0.15,     0.25),
}
NOMES_MODOS = list(MODOS_FALHA)
EFEITOS = np.array([MODOS_FALHA[m] for m in NOMES_MODOS], dtype=np.float64)

# Falhas de sensor (nao afetam a saude real, so a medicao)
MODOS_SENSOR = ["nenhum", "deriva_sensor", "travamento_sensor"]


def temperatura_ambiente(hora_dia: np.ndarray | float, dia_ano: np.ndarray | float, deslocamento=0.0):
    """Sala da UBS: ciclo diario (pico as 15 h) + estacao do ano."""
    return (
        24.5
        + 3.5 * np.sin(2 * np.pi * (np.asarray(hora_dia) - 9.0) / 24.0)
        + 2.5 * np.cos(2 * np.pi * (np.asarray(dia_ano) - 15.0) / 365.0)
        + deslocamento
    )


def luz_natural(hora_dia: np.ndarray | float):
    """Luminosidade natural (lux) de 0 a ~600, dia entre 6 h e 18 h."""
    return np.clip(np.sin(np.pi * (np.asarray(hora_dia) - 6.0) / 12.0), 0.0, None) * 600.0


@dataclass
class Estado:
    """Estado de N geladeiras (arrays de tamanho N)."""
    t_in: np.ndarray                 # temperatura interna (C)
    desgaste: np.ndarray             # 0 = novo, 1 = falha
    modo: np.ndarray                 # indice em NOMES_MODOS
    k_vib: np.ndarray                # variacao de fabricacao de cada unidade
    k_corr: np.ndarray
    k_temp: np.ndarray
    cap0: np.ndarray                 # capacidade de refrigeracao nominal (C/h)
    duty: np.ndarray = field(default=None)  # fracao de tempo do compressor ligado no ultimo tick

    @classmethod
    def novo(cls, n: int, rng: np.random.Generator) -> "Estado":
        return cls(
            t_in=rng.uniform(3.8, 5.5, n),
            desgaste=np.zeros(n),
            modo=np.zeros(n, dtype=np.int64),
            k_vib=rng.normal(1.0, 0.12, n).clip(0.7, 1.35),
            k_corr=rng.normal(1.0, 0.10, n).clip(0.75, 1.3),
            k_temp=rng.normal(1.0, 0.10, n).clip(0.75, 1.3),
            cap0=rng.normal(12.0, 1.0, n).clip(9.0, 15.0),
            duty=np.full(n, 0.4),
        )


def passo(
    est: Estado,
    t_amb: np.ndarray,
    porta: np.ndarray,
    resfr: np.ndarray,
    rng: np.random.Generator,
    ruido: float = 1.0,
) -> dict[str, np.ndarray]:
    """Avanca 1 tick e devolve as leituras (sem falhas de sensor, sem faltantes)."""
    n = est.t_in.shape[0]
    w = np.clip(est.desgaste, 0.0, 1.0)
    falhou = est.desgaste >= 1.0
    ef = EFEITOS[est.modo]                      # (n, 4)

    capacidade = est.cap0 * (1.0 - ef[:, 3] * w)
    capacidade = np.where(falhou, 0.0, capacidade)

    # Termostato proporcional (setpoint ~4,5 C)
    duty = np.clip(0.25 + 0.5 * (est.t_in - 4.5), 0.05, 1.0)
    duty = np.where(falhou, 0.0, duty)

    carga = 0.25 * (t_amb - est.t_in) + porta * 0.8 * (t_amb - est.t_in)
    emergencia = resfr * np.clip(0.8 * (est.t_in - 3.5), 0.0, 1.0) * 8.0
    est.t_in = est.t_in + DT_H * (carga - duty * capacidade - emergencia)
    est.t_in = est.t_in + rng.normal(0.0, 0.03 * ruido, n)
    est.duty = duty

    vib = est.k_vib * (0.4 + 1.6 * duty) * (1.0 + ef[:, 0] * w)
    corr = est.k_corr * (0.3 + 1.5 * duty) * (1.0 + ef[:, 1] * w)
    tcomp = t_amb + est.k_temp * (8.0 + 22.0 * duty) * (1.0 + ef[:, 2] * w)
    # compressor parado: so ruido de fundo, temperatura volta para a da sala
    vib = np.where(falhou, 0.12, vib)
    corr = np.where(falhou, 0.04, corr)
    tcomp = np.where(falhou, t_amb + 1.0, tcomp)

    umid = 52.0 + 18.0 * porta + 4.0 * (est.t_in > 8.0)

    return {
        "temperatura": est.t_in + rng.normal(0.0, 0.08 * ruido, n),
        "umidade": umid + rng.normal(0.0, 1.5 * ruido, n),
        "vibracao": np.clip(vib + rng.normal(0.0, 0.15 * ruido, n), 0.0, None),
        "corrente": np.clip(corr + rng.normal(0.0, 0.06 * ruido, n), 0.0, None),
        "temp_compressor": tcomp + rng.normal(0.0, 0.8 * ruido, n),
    }


def curva_desgaste(ticks_desde_inicio: np.ndarray, ticks_total: np.ndarray, expoente: np.ndarray):
    """Desgaste progressivo: comeca devagar e acelera perto da falha."""
    frac = np.clip(ticks_desde_inicio / np.maximum(ticks_total, 1), 0.0, None)
    return np.where(ticks_desde_inicio < 0, 0.0, frac ** expoente)


def hora_e_dia(tick: np.ndarray | int, tick_inicial_minutos: float = 0.0):
    minutos = tick_inicial_minutos + np.asarray(tick) * MINUTOS_POR_TICK
    hora = (minutos / 60.0) % 24.0
    dia = (minutos / 1440.0) % 365.0
    return hora, dia


__all__ = [
    "DT_H", "Estado", "passo", "curva_desgaste", "temperatura_ambiente", "luz_natural",
    "NOMES_MODOS", "MODOS_SENSOR", "hora_e_dia",
]
