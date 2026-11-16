"""Inferencia em tempo real.

Consome a telemetria dos compressores (q.inferencia), mantem uma janela de 6 h por
equipamento, calcula as features com comum/features.py (o MESMO codigo do treino) e
aplica os modelos atuais. Publica:

  prediction.<ubs>.<equipamento>   {rul_h, saude, tendencia, versao_modelo}
  alert.<ubs>.<equipamento>        {estado: aberto|fechado, tipo, severidade, mensagem}

Os alertas tem histerese: 3 previsoes seguidas abaixo do limite para abrir e 10
seguidas acima para fechar, para nao ficar piscando.

O modelo e recarregado sozinho quando o lab publica uma versao nova (atual.json),
sem reiniciar o servico.
"""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..comum import features as F
from ..comum import mensagens
from ..comum.amqp import Barramento
from ..comum.config import env, env_int
from ..comum.saude import batimento_continuo, configurar_logs
from ..lab.treino import carregar_atual

log = logging.getLogger("inferencia")
DIR_MODELOS = Path(env("DIR_MODELOS", "/modelos"))

# (tipo, campo, limite, severidade, mensagem)
REGRAS_ALERTA = [
    ("saude_baixa", "saude", 50.0, "atencao", "Saude do compressor abaixo de 50: agendar manutencao preventiva."),
    ("falha_iminente", "rul_h", 24.0, "critico", "Falha prevista em menos de 24 h: transferir as vacinas e chamar a manutencao."),
]
N_DISPARAR = env_int("ALERTA_N_DISPARAR", 3)
N_LIMPAR = env_int("ALERTA_N_LIMPAR", 10)


@dataclass
class Janela:
    ubs: str
    dados: dict = field(default_factory=lambda: {v: deque(maxlen=F.J_LONGA) for v in (*F.VARIAVEIS, "hora")})
    saude_hist: deque = field(default_factory=lambda: deque(maxlen=24))
    abaixo: dict = field(default_factory=dict)
    acima: dict = field(default_factory=dict)
    alerta_aberto: dict = field(default_factory=dict)


class Inferencia:
    def __init__(self):
        self.versao = None
        self.m_rul = self.m_saude = None
        self.janelas: dict[str, Janela] = {}

    def recarregar_se_preciso(self):
        try:
            ponteiro = DIR_MODELOS / "atual.json"
            if not ponteiro.exists():
                return
            import json
            versao = json.loads(ponteiro.read_text())["versao"]
            if versao != self.versao:
                v, mr, ms, _ = carregar_atual(DIR_MODELOS)
                self.versao, self.m_rul, self.m_saude = v, mr, ms
                log.info("Modelo v%s carregado (sem reiniciar o servico)", v)
        except Exception as e:  # noqa: BLE001
            log.warning("Nao foi possivel carregar o modelo: %s", e)

    def processar(self, msg: dict) -> list[tuple[str, dict]]:
        c = msg["conteudo"]
        disp, ubs = msg["dispositivo"], msg.get("ubs", "x")
        j = self.janelas.setdefault(disp, Janela(ubs))
        for v in F.VARIAVEIS:
            val = c.get(v)
            j.dados[v].append(float(val) if isinstance(val, (int, float)) else np.nan)
        j.dados["hora"].append(float(c.get("hora_sim", 0.0)))

        saida = []
        n = len(j.dados["hora"])
        if self.m_rul is None:
            saida.append(("prediction", mensagens.nova("previsao", disp, {"status": "sem_modelo"}, ubs)))
            return saida
        if n < F.TICKS_MINIMOS:
            saida.append(("prediction", mensagens.nova("previsao", disp, {"status": "aquecendo", "leituras": n,
                                                                          "necessarias": F.TICKS_MINIMOS}, ubs)))
            return saida

        series = {v: np.array(j.dados[v], dtype=np.float64) for v in F.VARIAVEIS}
        X = F.ultima_linha(series, np.array(j.dados["hora"]))
        rul = float(np.clip(self.m_rul.predict(X)[0], 0.0, None))
        saude = float(np.clip(self.m_saude.predict(X)[0], 0.0, 100.0))
        if c.get("estado") == "parado":
            # compressor ja falhou (nao gira): fora do dominio do modelo, saude e RUL vao a zero
            rul, saude = 0.0, 0.0
        j.saude_hist.append(saude)
        tendencia = 0.0
        if len(j.saude_hist) >= 6:
            y = np.array(j.saude_hist)
            tendencia = float(np.polyfit(np.arange(y.size), y, 1)[0] * 12)  # pontos de saude por hora simulada
        conteudo = {"status": "ok", "rul_h": round(rul, 1), "saude": round(saude, 1), "tendencia": round(tendencia, 2),
                    "versao_modelo": self.versao, "estado_compressor": c.get("estado")}
        saida.append(("prediction", mensagens.nova("previsao", disp, conteudo, ubs)))

        valores = {"saude": saude, "rul_h": rul}
        for tipo, campo, limite, sev, texto in REGRAS_ALERTA:
            v = valores[campo]
            if v < limite:
                j.abaixo[tipo] = j.abaixo.get(tipo, 0) + 1; j.acima[tipo] = 0
            else:
                j.acima[tipo] = j.acima.get(tipo, 0) + 1; j.abaixo[tipo] = 0
            aberto = j.alerta_aberto.get(tipo, False)
            if not aberto and j.abaixo[tipo] >= N_DISPARAR:
                j.alerta_aberto[tipo] = True
                saida.append(("alert", mensagens.nova("alerta", disp, {
                    "estado": "aberto", "tipo": tipo, "severidade": sev, "mensagem": texto,
                    "valor": round(v, 1), "limite": limite, "origem": "ia", "versao_modelo": self.versao}, ubs)))
            elif aberto and j.acima[tipo] >= N_LIMPAR:
                j.alerta_aberto[tipo] = False
                saida.append(("alert", mensagens.nova("alerta", disp, {
                    "estado": "fechado", "tipo": tipo, "severidade": sev, "mensagem": f"Normalizado: {tipo}",
                    "valor": round(v, 1), "limite": limite, "origem": "ia"}, ubs)))
        return saida


async def main():
    configurar_logs()
    inf = Inferencia()
    inf.recarregar_se_preciso()
    bus = await Barramento("RABBIT_INFERENCIA_USUARIO", "RABBIT_INFERENCIA_SENHA", prefetch=1).conectar()

    async def ao_receber(msg: dict, _rk: str):
        for prefixo, saida in await asyncio.to_thread(inf.processar, msg):
            rk = f"{prefixo}.{mensagens.seguro(saida['ubs'])}.{mensagens.seguro(saida['dispositivo'])}"
            await bus.publicar(rk, saida)

    async def vigiar_modelo():
        while True:
            await asyncio.sleep(10)
            await asyncio.to_thread(inf.recarregar_se_preciso)

    await bus.consumir("q.inferencia", ao_receber)
    asyncio.create_task(vigiar_modelo())
    await batimento_continuo()


if __name__ == "__main__":
    asyncio.run(main())
