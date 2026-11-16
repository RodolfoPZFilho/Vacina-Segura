"""API do VacinaSegura (FastAPI): REST, WebSocket e regras de negocio.

Papeis: visualizador (so ve), operador (comanda atuadores e simulador),
administrador (tambem gera dados, treina modelos, gerencia cadastro e ve a auditoria).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..comum import fisica, mensagens
from ..comum.config import env
from ..comum.dispositivos import FAIXAS_COMPRESSOR, GRANDEZAS
from ..comum.saude import configurar_logs
from ..lab.gerador import ParametrosGeracao
from . import assistente, auth, db, leituras, mensageria
from .tempo_real import estado, iniciar_consumidores, publicar_comando, publicar_config_simulador

configurar_logs()
log = logging.getLogger("api")


@asynccontextmanager
async def ciclo(_app: FastAPI):
    await db.iniciar()
    await iniciar_consumidores()
    yield
    if estado.bus:
        await estado.bus.fechar()


app = FastAPI(title="VacinaSegura API", version="2.0.0", lifespan=ciclo,
              docs_url="/api/docs", openapi_url="/api/openapi.json")

Visualizador = Depends(auth.exigir("visualizador"))
Operador = Depends(auth.exigir("operador"))
Admin = Depends(auth.exigir("administrador"))
ID_RE = r"^[A-Za-z0-9_-]{1,64}$"


# ======================================================================= saude / sistema
@app.get("/api/saude")
async def saude():
    return {"api": "ok", "ws_clientes": len(estado.clientes)}


@app.get("/api/sistema")
async def sistema(_u=Visualizador):
    async def ollama_ok():
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                return (await c.get(f"{assistente.OLLAMA}/api/tags")).status_code == 200
        except httpx.HTTPError:
            return False
    try:
        await db.pool.fetchval("SELECT 1"); pg = True
    except Exception:  # noqa: BLE001
        pg = False
    idade = time.time() - estado.ultima_telemetria if estado.ultima_telemetria else None
    return {
        "componentes": {
            "postgresql": pg,
            "influxdb": await asyncio.to_thread(leituras.ping),
            "rabbitmq": await mensageria.ping(),
            "ollama": await ollama_ok(),
            "llm_carregado": await assistente.modelo_carregado(),
            "telemetria_recente": idade is not None and idade < 20,
        },
        "segundos_desde_ultima_telemetria": round(idade, 1) if idade is not None else None,
        "modelo_llm": assistente.MODELO,
        "ws_clientes": len(estado.clientes),
        "links": [
            {"nome": "InfluxDB (séries temporais)", "url": "http://127.0.0.1:8086"},
            {"nome": "RabbitMQ (gerenciamento)", "url": "http://127.0.0.1:15672"},
            {"nome": "PostgreSQL (Adminer)", "url": "http://127.0.0.1:8081/?pgsql=postgres&username=vacinasegura&db=vacinasegura"},
            {"nome": "Documentação da API (Swagger)", "url": "/api/docs"},
        ],
    }


# ======================================================================= autenticacao
class Login(BaseModel):
    login: str = Field(max_length=64)
    senha: str = Field(max_length=200)


@app.post("/api/auth/login")
async def login(dados: Login, req: Request):
    ip = auth.ip_de(req)
    if auth.ip_bloqueado(ip):
        raise HTTPException(429, "Muitas tentativas a partir deste endereco. Aguarde alguns minutos.")
    u = await db.pool.fetchrow("SELECT * FROM usuarios WHERE login=$1", dados.login)
    agora = datetime.now(timezone.utc)
    if u and u["bloqueado_ate"] and u["bloqueado_ate"] > agora:
        await db.auditar(dados.login, "login_bloqueado", {}, ip)
        raise HTTPException(429, f"Usuario bloqueado por excesso de tentativas. Tente apos {u['bloqueado_ate']:%H:%M} UTC.")
    if not u or not auth.conferir_senha(dados.senha, u["senha_hash"]):
        auth.registrar_falha_ip(ip)
        if u:
            falhas = u["falhas"] + 1
            bloqueio = agora + auth.BLOQUEIO if falhas >= auth.MAX_FALHAS_LOGIN else None
            await db.pool.execute("UPDATE usuarios SET falhas=$2, bloqueado_ate=$3 WHERE id=$1",
                                  u["id"], 0 if bloqueio else falhas, bloqueio)
        await db.auditar(dados.login, "login_falhou", {}, ip)
        raise HTTPException(401, "Login ou senha incorretos")
    await db.pool.execute("UPDATE usuarios SET falhas=0, bloqueado_ate=NULL WHERE id=$1", u["id"])
    await db.auditar(u["login"], "login", {"papel": u["papel"]}, ip)
    return {"token": auth.criar_token(dict(u)), "usuario": {"login": u["login"], "nome": u["nome"], "papel": u["papel"]}}


@app.get("/api/auth/eu")
async def eu(u=Visualizador):
    return u


@app.post("/api/ws/ticket")
async def ticket_ws(u=Visualizador):
    """Ticket curto (30 s) e de uso unico para abrir o WebSocket sem expor o JWT na URL."""
    return {"ticket": auth.emitir_ticket(u)}


@app.websocket("/ws")
async def websocket(ws: WebSocket, ticket: str = ""):
    usuario = auth.consumir_ticket(ticket)
    if not usuario:
        await ws.close(code=4401)
        return
    await ws.accept()
    estado.clientes.add(ws)
    # estado inicial para a tela nao comecar vazia
    await ws.send_json({"canal": "inicial", "leituras": list(estado.ultimas_leituras.values()),
                        "previsoes": list(estado.previsoes.values())})
    try:
        while True:
            await ws.receive_text()  # mantem a conexao; o cliente nao envia comandos por aqui
    except WebSocketDisconnect:
        pass
    finally:
        estado.clientes.discard(ws)


# ======================================================================= dispositivos
class Dispositivo(BaseModel):
    id: str = Field(pattern=ID_RE)
    nome: str = Field(min_length=1, max_length=120)
    grandeza: Literal[tuple(GRANDEZAS)]  # type: ignore[valid-type]
    ubs: str = Field(pattern=ID_RE)
    geladeira: str | None = Field(default=None, pattern=ID_RE)
    unidade: str = Field(default="", max_length=10)
    faixa_min: float | None = None
    faixa_max: float | None = None
    ativo: bool = True


@app.get("/api/dispositivos")
async def listar_dispositivos(_u=Visualizador):
    rows = await db.pool.fetch("SELECT * FROM dispositivos ORDER BY ubs, geladeira NULLS FIRST, id")
    return [db.linha(r) for r in rows]


@app.get("/api/meta")
async def meta(_u=Visualizador):
    return {"grandezas": {k: {"categoria": v[0], "unidade": v[1], "faixa_min": v[2], "faixa_max": v[3], "controle": v[4]}
                          for k, v in GRANDEZAS.items()},
            "faixas_compressor": FAIXAS_COMPRESSOR,
            "modos_falha": [m for m in fisica.NOMES_MODOS if m != "nenhum"],
            "modos_sensor": [m for m in fisica.MODOS_SENSOR if m != "nenhum"]}


@app.post("/api/dispositivos", status_code=201)
async def criar_dispositivo(d: Dispositivo, req: Request, u=Admin):
    cat, _, _, _, controle = GRANDEZAS[d.grandeza]
    if d.grandeza in ("temperatura", "umidade", "porta", "compressor", "alarme", "resfriamento") and not d.geladeira:
        raise HTTPException(422, "Esse tipo de dispositivo precisa estar ligado a uma geladeira")
    try:
        r = await db.pool.fetchrow(
            """INSERT INTO dispositivos (id, nome, categoria, grandeza, ubs, geladeira, unidade, faixa_min, faixa_max, controle, ativo)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *""",
            d.id, d.nome, cat, d.grandeza, d.ubs, d.geladeira, d.unidade, d.faixa_min, d.faixa_max, controle, d.ativo)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(409, f"Nao foi possivel criar: {e}")
    await db.auditar(u["login"], "dispositivo_criado", d.model_dump(), auth.ip_de(req))
    await publicar_config_simulador()
    return db.linha(r)


@app.put("/api/dispositivos/{disp_id}")
async def editar_dispositivo(disp_id: str, d: Dispositivo, req: Request, u=Admin):
    cat, _, _, _, controle = GRANDEZAS[d.grandeza]
    r = await db.pool.fetchrow(
        """UPDATE dispositivos SET nome=$2, categoria=$3, grandeza=$4, ubs=$5, geladeira=$6, unidade=$7,
           faixa_min=$8, faixa_max=$9, controle=$10, ativo=$11, atualizado_em=now() WHERE id=$1 RETURNING *""",
        disp_id, d.nome, cat, d.grandeza, d.ubs, d.geladeira, d.unidade, d.faixa_min, d.faixa_max, controle, d.ativo)
    if not r:
        raise HTTPException(404, "Dispositivo nao encontrado")
    await db.auditar(u["login"], "dispositivo_editado", d.model_dump(), auth.ip_de(req))
    await publicar_config_simulador()
    return db.linha(r)


@app.delete("/api/dispositivos/{disp_id}", status_code=204)
async def excluir_dispositivo(disp_id: str, req: Request, u=Admin):
    n = await db.pool.execute("DELETE FROM dispositivos WHERE id=$1", disp_id)
    if n.endswith(" 0"):
        raise HTTPException(404, "Dispositivo nao encontrado")
    estado.ultimas_leituras.pop(disp_id, None)
    estado.previsoes.pop(disp_id, None)
    await db.auditar(u["login"], "dispositivo_excluido", {"id": disp_id}, auth.ip_de(req))
    await publicar_config_simulador()


# ======================================================================= leituras
Periodo = Literal["15m", "1h", "6h", "24h", "7d"]


@app.get("/api/leituras/atuais")
async def leituras_atuais(_u=Visualizador):
    return {"leituras": list(estado.ultimas_leituras.values()), "previsoes": list(estado.previsoes.values()),
            "segundos_desde_ultima": round(time.time() - estado.ultima_telemetria, 1) if estado.ultima_telemetria else None}


@app.get("/api/leituras/historico")
async def historico(dispositivo: str = Query(pattern=ID_RE), periodo: Periodo = "1h",
                    campo: str = Query("valor", pattern=ID_RE), _u=Visualizador):
    try:
        return {"pontos": await leituras.historico(dispositivo, periodo, campo),
                "estatisticas": await leituras.estatisticas(dispositivo, periodo, campo)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"InfluxDB indisponivel: {e}")


@app.get("/api/previsoes/historico")
async def historico_previsoes(dispositivo: str = Query(pattern=ID_RE), periodo: Periodo = "1h",
                              campo: Literal["saude", "rul_h"] = "saude", _u=Visualizador):
    return {"pontos": await leituras.historico(dispositivo, periodo, campo, "previsao")}


# ======================================================================= comandos (Web -> IoT)
class Comando(BaseModel):
    dispositivo: str = Field(pattern=ID_RE)
    acao: Literal["ligar", "desligar", "injetar_falha", "reparar", "abrir_porta", "pausar", "retomar"]
    modo: str | None = None
    horas: float | None = Field(default=None, ge=1, le=500)
    minutos: float | None = Field(default=None, ge=5, le=240)
    segundos: float | None = Field(default=None, ge=5, le=600)


@app.post("/api/comandos", status_code=202)
async def comando(c: Comando, req: Request, u=Operador):
    if c.dispositivo == "simulador":
        if c.acao not in ("pausar", "retomar"):
            raise HTTPException(422, "O simulador aceita apenas pausar/retomar")
        conteudo = {"acao": c.acao, "segundos": c.segundos or 60, "origem": "usuario", "usuario": u["login"]}
        msg = await publicar_comando("simulador", "sistema", conteudo)
    else:
        d = await db.pool.fetchrow("SELECT * FROM dispositivos WHERE id=$1", c.dispositivo)
        if not d:
            raise HTTPException(404, "Dispositivo nao encontrado")
        g = d["grandeza"]
        permitido = (
            (c.acao in ("ligar", "desligar") and d["categoria"] == "atuador" and d["controle"] == "manual")
            or (c.acao in ("injetar_falha", "reparar") and g == "compressor")
            or (c.acao == "abrir_porta" and g == "porta")
        )
        if not permitido:
            raise HTTPException(422, f"Acao '{c.acao}' nao se aplica a {d['id']} (o alarme e acionado pela regra de negocio)")
        if c.acao == "injetar_falha" and c.modo not in fisica.NOMES_MODOS:
            raise HTTPException(422, "Modo de falha invalido")
        conteudo = {k: v for k, v in c.model_dump().items() if v is not None and k != "dispositivo"}
        conteudo |= {"origem": "usuario", "usuario": u["login"]}
        msg = await publicar_comando(d["id"], d["ubs"], conteudo)
    await db.auditar(u["login"], "comando", {"dispositivo": c.dispositivo, **conteudo, "msg_id": msg["id"]}, auth.ip_de(req))
    return {"enviado": True, "id": msg["id"]}


# ======================================================================= alertas e insights
@app.get("/api/alertas")
async def alertas(abertos: bool = True, limite: int = Query(100, le=500), _u=Visualizador):
    sql = "SELECT * FROM alertas " + ("WHERE fechado_em IS NULL " if abertos else "") + "ORDER BY aberto_em DESC LIMIT $1"
    return [db.linha(r) for r in await db.pool.fetch(sql, limite)]


@app.get("/api/insights")
async def insights(_u=Visualizador):
    equipamentos = await db.pool.fetch("SELECT * FROM dispositivos WHERE categoria='equipamento' AND ativo ORDER BY id")
    abertos = await db.pool.fetch("SELECT * FROM alertas WHERE fechado_em IS NULL")
    saida = []
    for e in equipamentos:
        prev = estado.previsoes.get(e["id"])
        tele = estado.ultimas_leituras.get(e["id"])
        temp_id = f"{e['geladeira']}-temp" if e["geladeira"] else None
        relacionados = {e["id"]} | ({temp_id} if temp_id else set())
        saida.append({
            "dispositivo": db.linha(e),
            "previsao": prev["conteudo"] if prev else None,
            "previsao_ts": prev["ts"] if prev else None,
            "telemetria": tele["conteudo"] if tele else None,
            "temperatura_interna": (estado.ultimas_leituras.get(temp_id) or {}).get("conteudo"),
            "alertas": [db.linha(a) for a in abertos if a["dispositivo"] in relacionados],
        })
    return saida


# ======================================================================= regras e configuracoes
class Regra(BaseModel):
    nome: str = Field(max_length=120)
    sensor_grandeza: Literal["temperatura", "umidade", "temp_ambiente"]
    condicao: Literal["fora_faixa", "acima", "abaixo"]
    limite: float | None = None
    histerese: float = Field(0.3, ge=0, le=10)
    atuador_grandeza: Literal["alarme", "resfriamento"]
    ativa: bool = True


@app.get("/api/regras")
async def listar_regras(_u=Visualizador):
    return [dict(r) for r in await db.pool.fetch("SELECT * FROM regras ORDER BY id")]


@app.put("/api/regras/{regra_id}")
async def editar_regra(regra_id: int, r: Regra, req: Request, u=Admin):
    if r.condicao != "fora_faixa" and r.limite is None:
        raise HTTPException(422, "Informe o limite")
    row = await db.pool.fetchrow(
        """UPDATE regras SET nome=$2, sensor_grandeza=$3, condicao=$4, limite=$5, histerese=$6, atuador_grandeza=$7, ativa=$8
           WHERE id=$1 RETURNING *""", regra_id, r.nome, r.sensor_grandeza, r.condicao, r.limite, r.histerese,
        r.atuador_grandeza, r.ativa)
    if not row:
        raise HTTPException(404, "Regra nao encontrada")
    estado.regras_lidas_em = 0
    await db.auditar(u["login"], "regra_editada", {"id": regra_id, **r.model_dump()}, auth.ip_de(req))
    return dict(row)


# ======================================================================= laboratorio e treino
class Geracao(BaseModel):
    equipamentos: int = Field(60, ge=2, le=2000)
    dias: int = Field(60, ge=2, le=365)
    sensores_temperatura: int = Field(1, ge=1, le=4)
    sensores_umidade: int = Field(1, ge=0, le=4)
    pct_falha: float = Field(50, ge=0, le=100)
    modos_falha: list[str] = ["rolamento", "entupimento", "superaquecimento", "desbalanceamento"]
    pct_falha_sensor: float = Field(10, ge=0, le=100)
    modos_sensor: list[str] = ["deriva_sensor", "travamento_sensor"]
    ruido: float = Field(1.0, ge=0, le=5)
    pct_faltantes: float = Field(1.0, ge=0, le=30)
    pct_outliers: float = Field(0.3, ge=0, le=10)
    semente: int = Field(42, ge=0, le=2**31 - 1)


async def _criar_job(tipo: str, params: dict, usuario: str) -> str:
    job_id = f"{tipo[:3]}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    await db.pool.execute(
        "INSERT INTO jobs (id, tipo, status, parametros, criado_por, mensagem) VALUES ($1,$2,'na_fila',$3,$4,'aguardando na fila')",
        job_id, tipo, params, usuario)
    msg = mensagens.nova("job", "lab", {"job_id": job_id, "tipo": tipo, "parametros": params})
    await estado.bus.publicar(f"job.request.{tipo}", msg)
    return job_id


@app.post("/api/lab/previa")
async def previa_geracao(g: Geracao, _u=Visualizador):
    p = ParametrosGeracao(**g.model_dump())
    try:
        p.validar()
        return {"leituras": p.leituras_previstas(), "ok": True}
    except ValueError as e:
        return {"leituras": p.leituras_previstas(), "ok": False, "erro": str(e)}


@app.post("/api/lab/geracao", status_code=202)
async def gerar_dados(g: Geracao, req: Request, u=Admin):
    try:
        p = ParametrosGeracao(**g.model_dump()).validar()
    except ValueError as e:
        raise HTTPException(422, str(e))
    job_id = await _criar_job("geracao", g.model_dump(), u["login"])
    await db.auditar(u["login"], "job_geracao", {"job_id": job_id, "leituras": p.leituras_previstas(), **g.model_dump()},
                     auth.ip_de(req))
    return {"job_id": job_id, "leituras_previstas": p.leituras_previstas()}


class Treino(BaseModel):
    semente: int = Field(42, ge=0, le=2**31 - 1)


@app.post("/api/treino", status_code=202)
async def treinar(t: Treino, req: Request, u=Admin):
    job_id = await _criar_job("treino", t.model_dump(), u["login"])
    await db.auditar(u["login"], "job_treino", {"job_id": job_id}, auth.ip_de(req))
    return {"job_id": job_id}


@app.get("/api/jobs")
async def jobs(limite: int = Query(30, le=200), _u=Visualizador):
    return [db.linha(r) for r in await db.pool.fetch("SELECT * FROM jobs ORDER BY criado_em DESC LIMIT $1", limite)]


@app.get("/api/modelos")
async def modelos(_u=Visualizador):
    rows = await db.pool.fetch("SELECT versao, criado_em, job_id, metricas FROM modelos ORDER BY versao DESC LIMIT 20")
    em_uso = {p["conteudo"].get("versao_modelo") for p in estado.previsoes.values()} - {None}
    return {"modelos": [db.linha(r) for r in rows], "versao_em_uso": max(em_uso) if em_uso else None}


# ======================================================================= mensageria
@app.get("/api/mensageria")
async def painel_mensageria(_u=Visualizador):
    try:
        dados = await mensageria.painel()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"API de gerenciamento do RabbitMQ indisponivel: {e}")
    dados["ultimas_mensagens"] = list(estado.ultimas_msgs)[:30]
    return dados


@app.get("/api/mensageria/dlq")
async def dlq(_u=Visualizador):
    return await mensageria.espiar_dlq()


@app.delete("/api/mensageria/dlq", status_code=204)
async def limpar_dlq(req: Request, u=Admin):
    await mensageria.esvaziar_dlq()
    await db.auditar(u["login"], "dlq_esvaziada", {}, auth.ip_de(req))


# ======================================================================= assistente
class Pergunta(BaseModel):
    pergunta: str = Field(min_length=2, max_length=1000)
    historico: list[dict] = Field(default_factory=list, max_length=20)


@app.post("/api/assistente/perguntar")
async def perguntar(p: Pergunta, req: Request, u=Visualizador):
    cfg = await db.pool.fetchval("SELECT valor FROM configuracoes WHERE chave='assistente'") or {}
    limite = int(cfg.get("perguntas_por_minuto", 6))
    if not assistente.dentro_do_limite(u["login"], limite):
        raise HTTPException(429, f"Limite de {limite} perguntas por minuto atingido. Aguarde um pouco.")
    await db.auditar(u["login"], "pergunta_assistente", {"pergunta": p.pergunta[:500]}, auth.ip_de(req))
    return StreamingResponse(assistente.responder(p.pergunta, p.historico), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.get("/api/assistente/status")
async def status_assistente(_u=Visualizador):
    return {"modelo": assistente.MODELO, "carregado": await assistente.modelo_carregado()}


# ======================================================================= auditoria
@app.get("/api/auditoria")
async def auditoria(limite: int = Query(200, le=1000), acao: str | None = None, _u=Admin):
    if acao:
        rows = await db.pool.fetch("SELECT * FROM auditoria WHERE acao=$1 ORDER BY ts DESC LIMIT $2", acao, limite)
    else:
        rows = await db.pool.fetch("SELECT * FROM auditoria ORDER BY ts DESC LIMIT $1", limite)
    return [db.linha(r) for r in rows]


__all__ = ["app", "env"]
