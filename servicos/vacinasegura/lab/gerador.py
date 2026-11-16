"""Gerador de dados sinteticos massivos.

Simula a vida inteira de muitas geladeiras (com compressor) usando a mesma fisica do
simulador ao vivo (comum/fisica.py). O calculo e vetorizado com numpy: a cada tick
todas as maquinas do bloco avancam juntas (nada de laco ponto a ponto).

Cada leitura gerada tem os rotulos de verdade (degradando? quanto falta para falhar?
indice de saude). Esses rotulos ficam APENAS no arquivo de treino; nunca entram nas
mensagens de tempo real.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ..comum import fisica
from ..comum.config import RUL_TETO_H, TICKS_POR_HORA

# Teto para nao travar a maquina
MAX_LEITURAS = 30_000_000
MAX_EQUIPAMENTOS = 2_000
MAX_DIAS = 365
BLOCO = 256  # maquinas por bloco


@dataclass
class ParametrosGeracao:
    equipamentos: int = 60
    dias: int = 60
    sensores_temperatura: int = 1    # sensores de temperatura interna por geladeira
    sensores_umidade: int = 1
    pct_falha: float = 50.0          # % de equipamentos que vao falhar no periodo
    modos_falha: list[str] = field(default_factory=lambda: ["rolamento", "entupimento", "superaquecimento", "desbalanceamento"])
    pct_falha_sensor: float = 10.0   # % de maquinas com deriva/travamento de sensor
    modos_sensor: list[str] = field(default_factory=lambda: ["deriva_sensor", "travamento_sensor"])
    ruido: float = 1.0               # multiplicador do ruido
    pct_faltantes: float = 1.0       # % de leituras faltantes (NaN)
    pct_outliers: float = 0.3        # % de valores absurdos
    semente: int = 42

    def validar(self) -> "ParametrosGeracao":
        self.equipamentos = int(np.clip(self.equipamentos, 2, MAX_EQUIPAMENTOS))
        self.dias = int(np.clip(self.dias, 2, MAX_DIAS))
        self.sensores_temperatura = int(np.clip(self.sensores_temperatura, 1, 4))
        self.sensores_umidade = int(np.clip(self.sensores_umidade, 0, 4))
        self.pct_falha = float(np.clip(self.pct_falha, 0, 100))
        self.pct_falha_sensor = float(np.clip(self.pct_falha_sensor, 0, 100))
        self.ruido = float(np.clip(self.ruido, 0.0, 5.0))
        self.pct_faltantes = float(np.clip(self.pct_faltantes, 0, 30))
        self.pct_outliers = float(np.clip(self.pct_outliers, 0, 10))
        self.modos_falha = [m for m in self.modos_falha if m in fisica.NOMES_MODOS and m != "nenhum"] or ["rolamento"]
        self.modos_sensor = [m for m in self.modos_sensor if m in fisica.MODOS_SENSOR and m != "nenhum"]
        if self.leituras_previstas() > MAX_LEITURAS:
            raise ValueError(
                f"Configuracao geraria {self.leituras_previstas():,} leituras; o teto e {MAX_LEITURAS:,}."
            )
        return self

    def ticks(self) -> int:
        return self.dias * 24 * TICKS_POR_HORA

    def sensores_por_maquina(self) -> int:
        # 3 variaveis do compressor + temperatura interna + umidade
        return 3 + self.sensores_temperatura + self.sensores_umidade

    def leituras_previstas(self) -> int:
        return self.equipamentos * self.ticks() * self.sensores_por_maquina()


def _aplicar_qualidade(x: np.ndarray, rng, p: ParametrosGeracao):
    """Faltantes e outliers, em bloco (x: ticks x maquinas)."""
    if p.pct_faltantes > 0:
        x[rng.random(x.shape) < p.pct_faltantes / 100.0] = np.nan
    if p.pct_outliers > 0:
        m = rng.random(x.shape) < p.pct_outliers / 100.0
        fator = rng.choice([-1.0, 3.0, 8.0, 40.0], size=int(m.sum()))
        x[m] = x[m] * fator
    return x


def gerar(p: ParametrosGeracao, destino: Path, progresso: Callable[[float, str], None] | None = None) -> dict:
    p.validar()
    destino.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(p.semente)
    T, N = p.ticks(), p.equipamentos
    t0 = time.time()

    # --- plano de falhas por maquina -------------------------------------------------
    vai_falhar = rng.random(N) < p.pct_falha / 100.0
    modo = np.zeros(N, dtype=np.int64)
    modo[vai_falhar] = rng.choice([fisica.NOMES_MODOS.index(m) for m in p.modos_falha], size=int(vai_falhar.sum()))
    tick_falha = np.full(N, np.iinfo(np.int64).max // 4, dtype=np.int64)
    tick_falha[vai_falhar] = (rng.uniform(0.35, 1.0, int(vai_falhar.sum())) * T).astype(np.int64)
    duracao = (rng.uniform(3, 20, N) * 24 * TICKS_POR_HORA).astype(np.int64)
    duracao = np.minimum(duracao, np.maximum(tick_falha, 1))
    tick_inicio = tick_falha - duracao
    expoente = rng.uniform(1.3, 2.6, N)

    sensor_falho = (rng.random(N) < p.pct_falha_sensor / 100.0) & (len(p.modos_sensor) > 0)
    modo_sensor = np.zeros(N, dtype=np.int64)
    if p.modos_sensor:
        modo_sensor[sensor_falho] = rng.choice([fisica.MODOS_SENSOR.index(m) for m in p.modos_sensor], size=int(sensor_falho.sum()))
    tick_sensor = (rng.uniform(0.1, 0.9, N) * T).astype(np.int64)
    taxa_deriva = rng.uniform(0.5, 3.0, N) / (24 * TICKS_POR_HORA)  # C por tick
    desloc_ubs = rng.normal(0.0, 1.0, N)
    dia_inicial = rng.uniform(0, 365)

    # --- arrays de saida ---------------------------------------------------------------
    f32 = np.float32
    vib = np.empty((T, N), f32); corr = np.empty((T, N), f32); tcomp = np.empty((T, N), f32)
    temp = np.empty((T, N, p.sensores_temperatura), f32)
    umid = np.empty((T, N, max(p.sensores_umidade, 0)), f32)
    rul = np.empty((T, N), f32); saude = np.empty((T, N), f32); degradando = np.empty((T, N), np.bool_)
    hora_vet, dia_vet = fisica.hora_e_dia(np.arange(T), dia_inicial * 1440.0)

    total_passos = T * ((N + BLOCO - 1) // BLOCO)
    feitos = 0
    for b0 in range(0, N, BLOCO):
        b1 = min(N, b0 + BLOCO)
        n = b1 - b0
        est = fisica.Estado.novo(n, rng)
        est.modo = modo[b0:b1].copy()
        valor_travado = np.full(n, np.nan)
        for t in range(T):
            hora, dia = hora_vet[t], dia_vet[t]
            t_amb = fisica.temperatura_ambiente(hora, dia, desloc_ubs[b0:b1])
            expediente = 7.0 <= hora < 17.0
            porta = (rng.random(n) < (0.05 if expediente else 0.003)).astype(np.float64)
            est.desgaste = fisica.curva_desgaste(t - tick_inicio[b0:b1], duracao[b0:b1], expoente[b0:b1])
            est.desgaste = np.where(t >= tick_falha[b0:b1], 1.0, est.desgaste)
            le = fisica.passo(est, t_amb, porta, np.zeros(n), rng, p.ruido)

            tc = le["temp_compressor"]
            ms = modo_sensor[b0:b1]
            ativo = t >= tick_sensor[b0:b1]
            deriva = (ms == 1) & ativo
            tc = np.where(deriva, tc + taxa_deriva[b0:b1] * (t - tick_sensor[b0:b1]), tc)
            trava = (ms == 2) & ativo
            valor_travado = np.where(trava & np.isnan(valor_travado), tc, valor_travado)
            tc = np.where(trava, valor_travado, tc)

            vib[t, b0:b1] = le["vibracao"]; corr[t, b0:b1] = le["corrente"]; tcomp[t, b0:b1] = tc
            for k in range(p.sensores_temperatura):
                temp[t, b0:b1, k] = le["temperatura"] + rng.normal(0, 0.05 * p.ruido, n)
            for k in range(p.sensores_umidade):
                umid[t, b0:b1, k] = le["umidade"] + rng.normal(0, 0.8 * p.ruido, n)

            faltam = (tick_falha[b0:b1] - t) / TICKS_POR_HORA
            rul[t, b0:b1] = np.clip(faltam, 0.0, RUL_TETO_H)
            saude[t, b0:b1] = 100.0 * (1.0 - np.clip(est.desgaste, 0, 1))
            degradando[t, b0:b1] = est.desgaste > 0
            feitos += 1
            if progresso and feitos % 2000 == 0:
                progresso(0.9 * feitos / total_passos, f"simulando maquinas {b0 + 1}-{b1} de {N}")

    if progresso:
        progresso(0.92, "aplicando ruido, faltantes e outliers")
    for arr in (vib, corr, tcomp):
        _aplicar_qualidade(arr, rng, p)
    _aplicar_qualidade(temp.reshape(T, -1), rng, p)
    if p.sensores_umidade:
        _aplicar_qualidade(umid.reshape(T, -1), rng, p)

    if progresso:
        progresso(0.96, "gravando arquivo do conjunto de dados")
    np.savez_compressed(
        destino / "dataset.npz",
        vibracao=vib, corrente=corr, temp_compressor=tcomp, temperatura=temp, umidade=umid,
        hora=hora_vet.astype(f32), rul_h=rul, saude=saude, degradando=degradando,
        tick_falha=tick_falha, modo=modo, modo_sensor=modo_sensor,
    )
    resumo = {
        "parametros": asdict(p),
        "leituras": int(p.leituras_previstas()),
        "ticks": T,
        "equipamentos": N,
        "equipamentos_com_falha": int(vai_falhar.sum()),
        "equipamentos_com_falha_sensor": int(sensor_falho.sum()),
        "falhas_por_modo": {m: int((modo[vai_falhar] == i).sum()) for i, m in enumerate(fisica.NOMES_MODOS) if m != "nenhum"},
        "segundos": round(time.time() - t0, 1),
    }
    (destino / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False))
    return resumo


def amostra_para_influx(destino: Path, max_maquinas: int = 4, passo_ticks: int = 12):
    """Pontos (maquina, tick, valores) de uma amostra horaria, para o bucket 'lab'."""
    d = np.load(destino / "dataset.npz")
    n = min(max_maquinas, d["vibracao"].shape[1])
    for m in range(n):
        for t in range(0, d["vibracao"].shape[0], passo_ticks):
            yield m, t, {
                "vibracao": float(d["vibracao"][t, m]),
                "corrente": float(d["corrente"][t, m]),
                "temp_compressor": float(d["temp_compressor"][t, m]),
                "temperatura": float(d["temperatura"][t, m, 0]),
                "rul_h": float(d["rul_h"][t, m]),
                "saude": float(d["saude"][t, m]),
            }
