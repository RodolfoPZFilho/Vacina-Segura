"""Testes da parte de IA: features sem vazamento, gerador reproduzivel e treino que vence a base.

Rodar (na pasta servicos):  python -m pytest -q testes
"""
from pathlib import Path

import numpy as np

from vacinasegura.comum import features as F
from vacinasegura.comum import mensagens
from vacinasegura.lab.gerador import ParametrosGeracao, gerar
from vacinasegura.lab.treino import treinar


def _series(n=400, semente=1):
    rng = np.random.default_rng(semente)
    s = {v: rng.normal(2, 0.3, n).cumsum() / 50 + 2 for v in F.VARIAVEIS}
    s["vibracao"][::37] = np.nan          # faltantes
    s["corrente"][::53] = 999.0           # outlier absurdo
    return s, (np.arange(n) * 5 / 60) % 24


def test_features_olham_so_o_passado():
    """A feature do instante t calculada com a serie inteira deve ser igual a calculada
    com a serie cortada em t (ou seja, nao usa nenhum dado do futuro)."""
    s, h = _series()
    completa = F.calcular(s, h)
    for t in (5, 30, 100, 250, 399):
        cortada = F.calcular({k: v[: t + 1] for k, v in s.items()}, h[: t + 1])
        np.testing.assert_allclose(cortada[-1], completa[t], equal_nan=True, rtol=1e-6, atol=1e-6)


def test_inferencia_usa_mesmo_codigo():
    s, h = _series()
    janela = {k: v[-F.J_LONGA:] for k, v in s.items()}
    assert F.ultima_linha(janela, h[-F.J_LONGA:]).shape == (1, len(F.NOMES_FEATURES))


def test_outlier_vira_faltante():
    x = F.sanear("corrente", np.array([1.0, 999.0, -3.0, 2.0]))
    assert np.isnan(x[1]) and np.isnan(x[2]) and x[3] == 2.0


def test_gerador_reproduzivel_e_teto(tmp_path: Path):
    p = ParametrosGeracao(equipamentos=6, dias=3, semente=7)
    r1 = gerar(p, tmp_path / "a")
    r2 = gerar(ParametrosGeracao(equipamentos=6, dias=3, semente=7), tmp_path / "b")
    a, b = np.load(tmp_path / "a" / "dataset.npz"), np.load(tmp_path / "b" / "dataset.npz")
    np.testing.assert_array_equal(a["vibracao"], b["vibracao"])
    assert r1["leituras"] == r2["leituras"] == 6 * 3 * 288 * 5
    try:
        ParametrosGeracao(equipamentos=2000, dias=365, sensores_temperatura=4, sensores_umidade=4).validar()
        assert False, "deveria recusar acima do teto"
    except ValueError:
        pass


def test_treino_vence_base(tmp_path: Path):
    gerar(ParametrosGeracao(equipamentos=24, dias=30, pct_falha=60, semente=3), tmp_path / "dados")
    m = treinar(tmp_path / "dados", tmp_path / "modelos", semente=3)
    assert (tmp_path / "modelos" / "atual.json").exists()
    for alvo in ("rul_h", "saude"):
        assert m["modelos"][alvo]["vence_base"], alvo
    assert m["divisao"]["criterio"] == "por equipamento"


def test_formato_unico_da_mensagem():
    msg = mensagens.nova("telemetria", "ubs01-g01-temp", {"valor": 4.2}, ubs="ubs01")
    assert set(msg) == {"id", "ts", "tipo", "dispositivo", "ubs", "conteudo"}
    assert mensagens.decodificar(mensagens.codificar(msg)) == msg
