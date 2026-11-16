"""Simulador de dispositivos IoT (substitui o ESP32/Wokwi do 1o bimestre).

* Publica a telemetria de cada dispositivo ativo no Mosquitto:
      vacinasegura/telemetria/<ubs>/<tipo>/<dispositivo>
* Escuta comandos em:
      vacinasegura/comando/<ubs>/<dispositivo>
      vacinasegura/comando/sistema/config   (lista de dispositivos, retida, enviada pela API)
* Os atuadores reagem de verdade: resfriamento ligado faz a temperatura cair, luz
  ligada aumenta a luminosidade, e o estado aparece nas leituras seguintes.

Cada tick representa 5 minutos simulados (TICK_SEGUNDOS reais, padrao 5 s), entao um
dia simulado passa em ~24 min e a degradacao de um compressor em dezenas de minutos.
Os rotulos de verdade (desgaste, horas ate falhar) NUNCA sao publicados.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
import paho.mqtt.client as mqtt

from ..comum import fisica, mensagens
from ..comum.config import TICKS_POR_HORA, env, env_float, env_int
from ..comum.dispositivos import cadastro_inicial
from ..comum.saude import bater, configurar_logs

log = logging.getLogger("simulador")
PREFIXO = "vacinasegura"


@dataclass
class Geladeira:
    id: str
    ubs: str
    est: fisica.Estado
    modo: str = "nenhum"
    tick_inicio: int = 0
    ticks_total: int = 1
    expoente: float = 2.0
    desgaste_base: float = 0.0
    porta_ate: int = -1
    resfr: bool = False
    alarme: bool = False


class Simulador:
    def __init__(self):
        self.rng = np.random.default_rng(env_int("SIM_SEMENTE", 7))
        self.tick = 0
        self.minuto_inicial = 8 * 60          # comeca as 08:00 simuladas
        self.dia_inicial = 320
        self.tick_s = env_float("TICK_SEGUNDOS", 5.0)
        self.pausado_ate = 0.0
        self.trava = threading.Lock()
        self.dispositivos: list[dict] = []
        self.geladeiras: dict[str, Geladeira] = {}
        self.luzes: dict[str, bool] = {}
        self.desloc_ubs: dict[str, float] = {}
        self.aplicar_config(cadastro_inicial())
        # cenario inicial de demonstracao: uma geladeira ja degradando
        self._injetar("ubs01-g02", "rolamento", horas=30, desgaste_atual=0.35)
        self._injetar("ubs02-g01", "entupimento", horas=70, desgaste_atual=0.08)

    # ------------------------------------------------------------------ config
    def aplicar_config(self, itens: list[dict]):
        with self.trava:
            self.dispositivos = [d for d in itens if d.get("ativo", True)]
            gels = {d["geladeira"]: d["ubs"] for d in self.dispositivos if d.get("geladeira")}
            for gid, ubs in gels.items():
                if gid not in self.geladeiras:
                    self.geladeiras[gid] = Geladeira(gid, ubs, fisica.Estado.novo(1, self.rng))
            for gid in list(self.geladeiras):
                if gid not in gels:
                    del self.geladeiras[gid]
            for d in self.dispositivos:
                self.luzes.setdefault(d["ubs"], False)
                self.desloc_ubs.setdefault(d["ubs"], float(self.rng.normal(0, 0.8)))
        log.info("Config aplicada: %d dispositivos ativos, %d geladeiras", len(self.dispositivos), len(self.geladeiras))

    def _injetar(self, gid: str, modo: str, horas: float, desgaste_atual: float = 0.0):
        g = self.geladeiras.get(gid)
        if not g or modo not in fisica.NOMES_MODOS:
            return
        g.modo = modo
        g.est.modo = np.array([fisica.NOMES_MODOS.index(modo)])
        g.expoente = 2.0
        # escolhe o inicio para que a curva passe pelo desgaste atual e chegue a 1 em `horas`
        frac = desgaste_atual ** (1 / g.expoente) if desgaste_atual > 0 else 0.0
        restante = max(1, int(horas * TICKS_POR_HORA))
        total = int(restante / max(1e-6, 1 - frac))
        g.ticks_total = total
        g.tick_inicio = self.tick - (total - restante)
        log.info("Falha '%s' injetada em %s (%.0f h simuladas ate falhar)", modo, gid, horas)

    # ------------------------------------------------------------------ comandos
    def comando(self, dispositivo: str, conteudo: dict):
        acao = conteudo.get("acao")
        with self.trava:
            if dispositivo == "simulador":
                if acao == "pausar":
                    self.pausado_ate = time.time() + float(conteudo.get("segundos", 60))
                elif acao == "retomar":
                    self.pausado_ate = 0
                return
            d = next((x for x in self.dispositivos if x["id"] == dispositivo), None)
            if not d:
                log.warning("Comando para dispositivo desconhecido: %s", dispositivo)
                return
            g = self.geladeiras.get(d.get("geladeira") or "")
            gr = d["grandeza"]
            if gr in ("alarme", "resfriamento", "luz") and acao in ("ligar", "desligar"):
                ligado = acao == "ligar"
                if gr == "luz":
                    self.luzes[d["ubs"]] = ligado
                elif g and gr == "alarme":
                    g.alarme = ligado
                elif g:
                    g.resfr = ligado
            elif gr == "compressor" and g:
                if acao == "injetar_falha":
                    self._injetar(g.id, conteudo.get("modo", "rolamento"), float(conteudo.get("horas", 48)))
                elif acao == "reparar":
                    g.modo = "nenhum"; g.est.modo = np.array([0]); g.est.desgaste = np.zeros(1)
                    g.tick_inicio = 0; g.ticks_total = 1
                    log.info("Compressor de %s reparado", g.id)
            elif gr == "porta" and g and acao == "abrir_porta":
                g.porta_ate = self.tick + int(float(conteudo.get("minutos", 30)) / 5)
        log.info("Comando executado: %s %s", dispositivo, conteudo)

    # ------------------------------------------------------------------ simulacao
    def passo(self) -> list[tuple[str, dict]]:
        """Avanca 1 tick e devolve [(topico, mensagem)]."""
        with self.trava:
            self.tick += 1
            hora, dia = fisica.hora_e_dia(self.tick, self.minuto_inicial)
            hora, dia = float(hora), float(dia) + self.dia_inicial
            amb = {u: float(fisica.temperatura_ambiente(hora, dia, off)) for u, off in self.desloc_ubs.items()}
            leituras: dict[str, dict] = {}
            for g in self.geladeiras.values():
                expediente = 7.0 <= hora < 17.0
                porta = 1.0 if (self.tick <= g.porta_ate or self.rng.random() < (0.05 if expediente else 0.003)) else 0.0
                if g.modo != "nenhum":
                    w = fisica.curva_desgaste(np.array([self.tick - g.tick_inicio]), np.array([g.ticks_total]),
                                              np.array([g.expoente]))
                    g.est.desgaste = np.maximum(g.est.desgaste, np.minimum(w, 1.0))
                le = fisica.passo(g.est, np.array([amb[g.ubs]]), np.array([porta]), np.array([1.0 if g.resfr else 0.0]), self.rng)
                leituras[g.id] = {k: float(v[0]) for k, v in le.items()} | {"porta": porta, "falhou": bool(g.est.desgaste[0] >= 1)}

            saida = []
            ts = mensagens.agora_iso()
            for d in self.dispositivos:
                gr, ubs, gid = d["grandeza"], d["ubs"], d.get("geladeira")
                le = leituras.get(gid or "")
                if gr in ("temperatura", "umidade") and le:
                    conteudo = {"valor": round(le[gr], 2), "unidade": d["unidade"], "grandeza": gr}
                elif gr == "porta" and le:
                    conteudo = {"valor": int(le["porta"]), "unidade": "", "grandeza": gr}
                elif gr == "compressor" and le:
                    conteudo = {"vibracao": round(le["vibracao"], 3), "corrente": round(le["corrente"], 3),
                                "temp_compressor": round(le["temp_compressor"], 2), "hora_sim": round(hora, 3),
                                "estado": "parado" if le["falhou"] else "operando", "grandeza": gr}
                elif gr == "temp_ambiente":
                    conteudo = {"valor": round(amb[ubs] + float(self.rng.normal(0, 0.15)), 2), "unidade": "°C", "grandeza": gr}
                elif gr == "luminosidade":
                    lux = float(fisica.luz_natural(hora)) + (350.0 if self.luzes.get(ubs) else 0.0) + float(self.rng.normal(0, 8))
                    conteudo = {"valor": round(max(0.0, lux), 1), "unidade": "lux", "grandeza": gr}
                elif gr in ("alarme", "resfriamento", "luz"):
                    g = self.geladeiras.get(gid or "")
                    ligado = self.luzes.get(ubs, False) if gr == "luz" else bool(g and (g.alarme if gr == "alarme" else g.resfr))
                    conteudo = {"estado": "ligado" if ligado else "desligado", "valor": int(ligado), "grandeza": gr}
                else:
                    continue
                conteudo["hora_sim"] = round(hora, 3)
                tipo = "atuador" if d["categoria"] == "atuador" else gr
                msg = mensagens.nova("telemetria", d["id"], conteudo, ubs=ubs, ts=ts)
                saida.append((f"{PREFIXO}/telemetria/{mensagens.seguro(ubs)}/{tipo}/{mensagens.seguro(d['id'])}", msg))
            return saida


def main():
    configurar_logs()
    sim = Simulador()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulador")
    cli.username_pw_set(env("MQTT_SIMULADOR_USUARIO", "simulador"), env("MQTT_SIMULADOR_SENHA"))
    cli.reconnect_delay_set(1, 30)

    def on_connect(c, _u, _f, rc, _p=None):
        log.info("Conectado ao Mosquitto (rc=%s)", rc)
        c.subscribe(f"{PREFIXO}/comando/#", qos=1)

    def on_message(_c, _u, m):
        if m.topic.endswith("/sistema/health"):
            return  # mensagem do healthcheck do Mosquitto
        try:
            msg = mensagens.decodificar(m.payload)
            if m.topic.endswith("/sistema/config"):
                sim.aplicar_config(msg["conteudo"].get("dispositivos", []))
            else:
                sim.comando(msg["dispositivo"], msg["conteudo"])
        except Exception as e:  # noqa: BLE001
            log.warning("Comando invalido em %s: %s", m.topic, e)

    cli.on_connect = on_connect
    cli.on_message = on_message
    host, porta = env("MQTT_HOST", "mosquitto"), env_int("MQTT_PORTA", 1883)
    while True:
        try:
            cli.connect(host, porta, keepalive=30)
            break
        except OSError as e:
            log.warning("Mosquitto indisponivel (%s), tentando de novo...", e)
            time.sleep(3)
    cli.loop_start()

    proximo = time.time()
    while True:
        bater()
        if time.time() >= sim.pausado_ate:
            for topico, msg in sim.passo():
                cli.publish(topico, mensagens.codificar(msg), qos=0)
        proximo += sim.tick_s
        time.sleep(max(0.0, proximo - time.time()))


if __name__ == "__main__":
    main()
