"""Estado em memoria, WebSocket e consumidores do RabbitMQ dentro da API.

Filas consumidas pela API:
  q.websocket    telemetria, previsoes, alertas e progresso de jobs -> repassa a todos os navegadores
  q.regras       temperatura das geladeiras -> regra de negocio que liga/desliga o alarme
  q.api.eventos  alertas e jobs -> persiste no PostgreSQL
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque

from fastapi import WebSocket

from ..comum import mensagens
from ..comum.amqp import Barramento
from . import db

log = logging.getLogger("api.tempo_real")


class Estado:
    def __init__(self):
        self.ultimas_leituras: dict[str, dict] = {}     # dispositivo -> ultima mensagem de telemetria
        self.previsoes: dict[str, dict] = {}            # equipamento -> ultima previsao
        self.ultimas_msgs: deque = deque(maxlen=60)     # para a pagina Mensageria
        self.ultima_telemetria = 0.0
        self.clientes: set[WebSocket] = set()
        self.estado_regra: dict[str, bool] = {}         # geladeira -> alarme ligado pela regra?
        self.bus: Barramento | None = None
        self.regras_cache: list[dict] = []
        self.regras_lidas_em = 0.0

    async def transmitir(self, dado: dict):
        if not self.clientes:
            return
        texto = json.dumps(dado, ensure_ascii=False)
        mortos = []
        for ws in list(self.clientes):
            try:
                await asyncio.wait_for(ws.send_text(texto), timeout=2)
            except Exception:  # noqa: BLE001
                mortos.append(ws)
        for ws in mortos:
            self.clientes.discard(ws)


estado = Estado()


async def publicar_comando(dispositivo: str, ubs: str, conteudo: dict):
    msg = mensagens.nova("comando", dispositivo, conteudo, ubs=ubs)
    await estado.bus.publicar(f"command.{mensagens.seguro(ubs)}.{mensagens.seguro(dispositivo)}", msg)
    return msg


async def publicar_config_simulador():
    """Envia ao simulador (retido no MQTT) a lista de dispositivos ativos do cadastro."""
    linhas = await db.pool.fetch("SELECT id, categoria, grandeza, ubs, geladeira, unidade, ativo FROM dispositivos")
    await publicar_comando("config", "sistema", {"acao": "config", "dispositivos": [dict(r) for r in linhas]})


# ---------------------------------------------------------------- consumidores
async def ao_websocket(msg: dict, rk: str):
    if msg["tipo"] == "telemetria":
        estado.ultimas_leituras[msg["dispositivo"]] = msg
        estado.ultima_telemetria = time.time()
    elif msg["tipo"] == "previsao":
        estado.previsoes[msg["dispositivo"]] = msg
    estado.ultimas_msgs.appendleft({"routing_key": rk, "recebida": mensagens.agora_iso(), **msg})
    await estado.transmitir({"canal": rk.split(".")[0], "routing_key": rk, "msg": msg})


async def _regras_ativas() -> list[dict]:
    if time.time() - estado.regras_lidas_em > 15:
        estado.regras_cache = [dict(r) for r in await db.pool.fetch("SELECT * FROM regras WHERE ativa")]
        estado.regras_lidas_em = time.time()
    return estado.regras_cache


async def ao_regra(msg: dict, _rk: str):
    """Regra de negocio: temperatura fora da faixa liga o alarme da geladeira (com histerese)."""
    valor = msg["conteudo"].get("valor")
    if not isinstance(valor, (int, float)):
        return
    disp = await db.pool.fetchrow("SELECT * FROM dispositivos WHERE id=$1", msg["dispositivo"])
    if not disp or not disp["geladeira"]:
        return
    for regra in await _regras_ativas():
        if regra["sensor_grandeza"] != disp["grandeza"]:
            continue
        lo = disp["faixa_min"] if disp["faixa_min"] is not None else 2.0
        hi = disp["faixa_max"] if disp["faixa_max"] is not None else 8.0
        h = regra["histerese"] or 0.0
        chave = f"{disp['geladeira']}:{regra['id']}"
        ligado = estado.estado_regra.get(chave, False)
        if regra["condicao"] == "fora_faixa":
            disparar, limpar = (valor > hi or valor < lo), (lo + h <= valor <= hi - h)
        elif regra["condicao"] == "acima":
            disparar, limpar = valor > regra["limite"], valor <= regra["limite"] - h
        else:
            disparar, limpar = valor < regra["limite"], valor >= regra["limite"] + h
        atuador = await db.pool.fetchrow(
            "SELECT id, ubs FROM dispositivos WHERE geladeira=$1 AND grandeza=$2 AND ativo",
            disp["geladeira"], regra["atuador_grandeza"])
        if not atuador:
            continue
        # depois de reiniciar a API, usa o estado real do atuador vindo da telemetria
        if chave not in estado.estado_regra:
            tele = estado.ultimas_leituras.get(atuador["id"])
            ligado = bool(tele and tele["conteudo"].get("estado") == "ligado")
            estado.estado_regra[chave] = ligado
        if disparar and not ligado:
            estado.estado_regra[chave] = True
            await publicar_comando(atuador["id"], atuador["ubs"], {"acao": "ligar", "origem": "regra", "regra": regra["nome"]})
            await db.auditar("regra", "comando_automatico", {"dispositivo": atuador["id"], "acao": "ligar",
                                                            "motivo": f"{disp['id']} = {valor}", "regra": regra["nome"]})
            await abrir_alerta(disp["id"], disp["ubs"], "temperatura_fora_faixa", "critico",
                               f"Temperatura {valor:.1f} °C fora da faixa {lo:g} a {hi:g} °C. Alarme acionado.", "regra", valor)
        elif limpar and ligado:
            estado.estado_regra[chave] = False
            await publicar_comando(atuador["id"], atuador["ubs"], {"acao": "desligar", "origem": "regra", "regra": regra["nome"]})
            await db.auditar("regra", "comando_automatico", {"dispositivo": atuador["id"], "acao": "desligar",
                                                            "motivo": f"{disp['id']} = {valor}", "regra": regra["nome"]})
            await fechar_alerta(disp["id"], "temperatura_fora_faixa")


async def abrir_alerta(dispositivo, ubs, tipo, severidade, mensagem, origem, valor=None):
    existe = await db.pool.fetchval(
        "SELECT id FROM alertas WHERE dispositivo=$1 AND tipo=$2 AND fechado_em IS NULL", dispositivo, tipo)
    if existe:
        return
    r = await db.pool.fetchrow(
        """INSERT INTO alertas (dispositivo, ubs, tipo, severidade, mensagem, origem, valor)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""", dispositivo, ubs, tipo, severidade, mensagem, origem, valor)
    await estado.transmitir({"canal": "alerta_db", "msg": db.linha(r)})


async def fechar_alerta(dispositivo, tipo):
    r = await db.pool.fetchrow(
        "UPDATE alertas SET fechado_em=now() WHERE dispositivo=$1 AND tipo=$2 AND fechado_em IS NULL RETURNING *",
        dispositivo, tipo)
    if r:
        await estado.transmitir({"canal": "alerta_db", "msg": db.linha(r)})


async def ao_evento(msg: dict, _rk: str):
    c = msg["conteudo"]
    if msg["tipo"] == "alerta":
        if c.get("estado") == "aberto":
            await abrir_alerta(msg["dispositivo"], msg.get("ubs"), c["tipo"], c.get("severidade", "atencao"),
                               c.get("mensagem", ""), c.get("origem", "ia"), c.get("valor"))
        else:
            await fechar_alerta(msg["dispositivo"], c["tipo"])
    elif msg["tipo"] == "job":
        job_id = c.get("job_id")
        status = c.get("status", "executando")
        await db.pool.execute(
            """INSERT INTO jobs (id, tipo, status, progresso, mensagem, resultado, criado_por, atualizado_em)
               VALUES ($1,$2,$3,$4,$5,$6,'sistema',now())
               ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, progresso=EXCLUDED.progresso,
                 mensagem=COALESCE(EXCLUDED.mensagem, jobs.mensagem),
                 resultado=COALESCE(EXCLUDED.resultado, jobs.resultado), atualizado_em=now()""",
            job_id, c.get("tipo", "?"), status, float(c.get("progresso", 0)), c.get("mensagem"), c.get("resultado"))
        res = c.get("resultado") or {}
        if c.get("tipo") == "treino" and status == "concluido" and "versao" in res:
            await db.pool.execute(
                "INSERT INTO modelos (versao, job_id, metricas) VALUES ($1,$2,$3) ON CONFLICT (versao) DO NOTHING",
                int(res["versao"]), job_id, res)


async def iniciar_consumidores():
    estado.bus = await Barramento("RABBIT_API_USUARIO", "RABBIT_API_SENHA", prefetch=100).conectar()
    await estado.bus.consumir("q.websocket", ao_websocket)
    await estado.bus.consumir("q.regras", ao_regra)
    await estado.bus.consumir("q.api.eventos", ao_evento)
    await publicar_config_simulador()
