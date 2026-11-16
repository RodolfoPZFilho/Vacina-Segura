"""Treino dos modelos de regressao a partir do conjunto sintetico.

Modelos (alvo continuo):
  * RUL  - vida util restante do compressor, em horas (teto de 168 h);
  * Saude - indice de saude de 0 a 100.

Regras seguidas:
  * features calculadas por comum/features.py (mesmo codigo da inferencia);
  * divisao treino/validacao/teste POR EQUIPAMENTO (nunca aleatoria por linha);
  * comparacao com uma base simples (prever sempre a media do treino);
  * o modelo novo e gravado em /modelos/vN e o ponteiro atual.json e trocado
    de forma atomica, para a inferencia carregar sem reiniciar.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from ..comum import features as F
from ..comum.config import TICKS_POR_HORA

AMOSTRAGEM = 6           # usa 1 linha a cada 30 min (linhas vizinhas sao quase iguais)
AQUECIMENTO = F.J_LONGA  # ignora o comeco da serie (janela de 6 h incompleta)
MAX_LINHAS_TREINO = 400_000


def _montar_tabela(d, maquinas: np.ndarray):
    X, y_rul, y_saude, grupo = [], [], [], []
    hora = d["hora"].astype(np.float64)
    tick_falha = d["tick_falha"]
    for m in maquinas:
        series = {v: d[v][:, m].astype(np.float64) for v in F.VARIAVEIS}
        feats = F.calcular(series, hora)
        fim = min(feats.shape[0], int(tick_falha[m]) + 1)   # depois da falha nao entra
        idx = np.arange(AQUECIMENTO, fim, AMOSTRAGEM)
        if idx.size == 0:
            continue
        X.append(feats[idx]); y_rul.append(d["rul_h"][idx, m]); y_saude.append(d["saude"][idx, m])
        grupo.append(np.full(idx.size, m))
    return (np.vstack(X), np.concatenate(y_rul).astype(np.float64),
            np.concatenate(y_saude).astype(np.float64), np.concatenate(grupo))


def _metricas(y, p):
    return {
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "r2": float(r2_score(y, p)),
    }


def _treinar_alvo(nome, Xtr, ytr, Xva, yva, Xte, yte, semente):
    candidatos = {
        "gradient_boosting": HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0,
            early_stopping=True, validation_fraction=0.1, random_state=semente),
        "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)),
    }
    resultados = {}
    melhor_nome, melhor_mae, melhor = None, np.inf, None
    for cand, modelo in candidatos.items():
        modelo.fit(Xtr, ytr)
        mae_va = mean_absolute_error(yva, modelo.predict(Xva))
        resultados[cand] = {"mae_validacao": float(mae_va)}
        if mae_va < melhor_mae:
            melhor_nome, melhor_mae, melhor = cand, mae_va, modelo

    p_te = melhor.predict(Xte)
    base = np.full_like(yte, ytr.mean())
    met = _metricas(yte, p_te)
    met_base = _metricas(yte, base)

    rng = np.random.default_rng(semente)
    sub = rng.choice(Xva.shape[0], size=min(3000, Xva.shape[0]), replace=False)
    imp = permutation_importance(melhor, Xva[sub], yva[sub], n_repeats=3, random_state=semente,
                                 scoring="neg_mean_absolute_error")
    importancia = sorted(
        ({"feature": f, "importancia": float(v)} for f, v in zip(F.NOMES_FEATURES, imp.importances_mean)),
        key=lambda r: -r["importancia"])

    amostra = rng.choice(yte.size, size=min(600, yte.size), replace=False)
    return melhor, {
        "alvo": nome,
        "algoritmo": melhor_nome,
        "candidatos": resultados,
        "teste": met,
        "base_media": met_base,
        "vence_base": bool(met["mae"] < met_base["mae"]),
        "importancia": importancia,
        "previsto_vs_real": [[float(yte[i]), float(p_te[i])] for i in amostra],
    }


def treinar(dir_dados: Path, dir_modelos: Path, semente: int = 42,
            progresso: Callable[[float, str], None] | None = None) -> dict:
    t0 = time.time()
    prog = progresso or (lambda *_: None)
    prog(0.02, "carregando conjunto de dados")
    d = np.load(dir_dados / "dataset.npz")
    n_maq = d["vibracao"].shape[1]

    rng = np.random.default_rng(semente)
    maquinas = rng.permutation(n_maq)
    n_te = max(1, int(round(n_maq * 0.15)))
    n_va = max(1, int(round(n_maq * 0.15)))
    m_te, m_va, m_tr = maquinas[:n_te], maquinas[n_te:n_te + n_va], maquinas[n_te + n_va:]

    prog(0.10, f"calculando features ({n_maq} equipamentos)")
    Xtr, rtr, str_, _ = _montar_tabela(d, m_tr)
    Xva, rva, sva, _ = _montar_tabela(d, m_va)
    Xte, rte, ste, _ = _montar_tabela(d, m_te)
    if Xtr.shape[0] > MAX_LINHAS_TREINO:
        sel = rng.choice(Xtr.shape[0], MAX_LINHAS_TREINO, replace=False)
        Xtr, rtr, str_ = Xtr[sel], rtr[sel], str_[sel]

    prog(0.35, "treinando modelo de vida util restante (RUL)")
    m_rul, met_rul = _treinar_alvo("rul_h", Xtr, rtr, Xva, rva, Xte, rte, semente)
    prog(0.70, "treinando modelo de indice de saude")
    m_saude, met_saude = _treinar_alvo("saude", Xtr, str_, Xva, sva, Xte, ste, semente)

    prog(0.92, "gravando modelos")
    dir_modelos.mkdir(parents=True, exist_ok=True)
    versoes = [int(p.name[1:]) for p in dir_modelos.glob("v*") if p.name[1:].isdigit()]
    versao = (max(versoes) + 1) if versoes else 1
    pasta = dir_modelos / f"v{versao}"
    pasta.mkdir()
    joblib.dump(m_rul, pasta / "rul.joblib")
    joblib.dump(m_saude, pasta / "saude.joblib")

    resumo_dados = {}
    if (dir_dados / "resumo.json").exists():
        resumo_dados = json.loads((dir_dados / "resumo.json").read_text())
    metricas = {
        "versao": versao,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": F.NOMES_FEATURES,
        "divisao": {"treino": int(m_tr.size), "validacao": int(m_va.size), "teste": int(m_te.size),
                    "linhas_treino": int(Xtr.shape[0]), "linhas_teste": int(Xte.shape[0]),
                    "criterio": "por equipamento"},
        "dados": {k: resumo_dados.get(k) for k in ("leituras", "equipamentos", "equipamentos_com_falha", "parametros")},
        "modelos": {"rul_h": met_rul, "saude": met_saude},
        "segundos": round(time.time() - t0, 1),
    }
    (pasta / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False))

    tmp = dir_modelos / "atual.json.tmp"
    tmp.write_text(json.dumps({"versao": versao, "pasta": pasta.name}))
    os.replace(tmp, dir_modelos / "atual.json")
    prog(1.0, f"modelo v{versao} publicado")
    return metricas


def carregar_atual(dir_modelos: Path):
    """(versao, modelo_rul, modelo_saude, metricas) ou None se nao houver modelo."""
    ponteiro = dir_modelos / "atual.json"
    if not ponteiro.exists():
        return None
    info = json.loads(ponteiro.read_text())
    pasta = dir_modelos / info["pasta"]
    return (info["versao"], joblib.load(pasta / "rul.joblib"), joblib.load(pasta / "saude.joblib"),
            json.loads((pasta / "metricas.json").read_text()))


__all__ = ["treinar", "carregar_atual", "TICKS_POR_HORA"]
