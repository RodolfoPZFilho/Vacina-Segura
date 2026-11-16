"""PostgreSQL: usuarios, dispositivos, regras, configuracoes, alertas, jobs, modelos e auditoria."""
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

from ..comum.config import env, env_int
from ..comum.dispositivos import cadastro_inicial

log = logging.getLogger("api.db")
pool: asyncpg.Pool | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            serial PRIMARY KEY,
    login         text UNIQUE NOT NULL,
    nome          text NOT NULL,
    papel         text NOT NULL CHECK (papel IN ('visualizador', 'operador', 'administrador')),
    senha_hash    text NOT NULL,
    falhas        int NOT NULL DEFAULT 0,
    bloqueado_ate timestamptz,
    criado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS dispositivos (
    id            text PRIMARY KEY,
    nome          text NOT NULL,
    categoria     text NOT NULL CHECK (categoria IN ('sensor', 'atuador', 'equipamento')),
    grandeza      text NOT NULL,
    ubs           text NOT NULL,
    geladeira     text,
    unidade       text NOT NULL DEFAULT '',
    faixa_min     double precision,
    faixa_max     double precision,
    controle      text,
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS regras (
    id                serial PRIMARY KEY,
    nome              text NOT NULL,
    sensor_grandeza   text NOT NULL,
    condicao          text NOT NULL CHECK (condicao IN ('fora_faixa', 'acima', 'abaixo')),
    limite            double precision,
    histerese         double precision NOT NULL DEFAULT 0.3,
    atuador_grandeza  text NOT NULL,
    ativa             boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS configuracoes (
    chave text PRIMARY KEY,
    valor jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas (
    id          serial PRIMARY KEY,
    dispositivo text NOT NULL,
    ubs         text,
    tipo        text NOT NULL,
    severidade  text NOT NULL,
    mensagem    text NOT NULL,
    origem      text NOT NULL,
    valor       double precision,
    aberto_em   timestamptz NOT NULL DEFAULT now(),
    fechado_em  timestamptz
);
CREATE INDEX IF NOT EXISTS alertas_abertos ON alertas (dispositivo, tipo) WHERE fechado_em IS NULL;
CREATE TABLE IF NOT EXISTS jobs (
    id            text PRIMARY KEY,
    tipo          text NOT NULL,
    status        text NOT NULL,
    progresso     double precision NOT NULL DEFAULT 0,
    mensagem      text,
    parametros    jsonb,
    resultado     jsonb,
    criado_por    text,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS modelos (
    versao    int PRIMARY KEY,
    criado_em timestamptz NOT NULL DEFAULT now(),
    job_id    text,
    metricas  jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS auditoria (
    id       bigserial PRIMARY KEY,
    ts       timestamptz NOT NULL DEFAULT now(),
    usuario  text,
    acao     text NOT NULL,
    detalhe  jsonb,
    ip       text
);
CREATE INDEX IF NOT EXISTS auditoria_ts ON auditoria (ts DESC);
"""


async def _json_codec(con):
    await con.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def iniciar():
    global pool
    for tentativa in range(40):
        try:
            pool = await asyncpg.create_pool(
                host=env("POSTGRES_HOST", "postgres"), port=env_int("POSTGRES_PORTA", 5432),
                user=env("POSTGRES_USER", "vacinasegura"), password=env("POSTGRES_PASSWORD"),
                database=env("POSTGRES_DB", "vacinasegura"), min_size=1, max_size=10, init=_json_codec)
            break
        except Exception as e:  # noqa: BLE001
            log.warning("PostgreSQL indisponivel (%s)", e)
            await asyncio.sleep(2)
    else:
        raise RuntimeError("PostgreSQL nao respondeu")
    async with pool.acquire() as con:
        await con.execute(ESQUEMA)
    await semear()


async def semear():
    from .auth import hash_senha
    async with pool.acquire() as con:
        for login, nome, papel, var in (
            ("administrador", "Administrador", "administrador", "ADMIN_SENHA"),
            ("operador", "Operador da UBS", "operador", "OPERADOR_SENHA"),
            ("visualizador", "Visualizador", "visualizador", "VISUALIZADOR_SENHA"),
        ):
            existe = await con.fetchval("SELECT 1 FROM usuarios WHERE login=$1", login)
            if not existe:
                await con.execute("INSERT INTO usuarios (login, nome, papel, senha_hash) VALUES ($1,$2,$3,$4)",
                                  login, nome, papel, hash_senha(env(var)))
                log.info("Usuario de demonstracao criado: %s (%s)", login, papel)
        if not await con.fetchval("SELECT count(*) FROM dispositivos"):
            for d in cadastro_inicial():
                await con.execute(
                    """INSERT INTO dispositivos (id, nome, categoria, grandeza, ubs, geladeira, unidade,
                       faixa_min, faixa_max, controle, ativo) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                    d["id"], d["nome"], d["categoria"], d["grandeza"], d["ubs"], d["geladeira"], d["unidade"],
                    d["faixa_min"], d["faixa_max"], d["controle"], d["ativo"])
        if not await con.fetchval("SELECT count(*) FROM regras"):
            await con.execute(
                """INSERT INTO regras (nome, sensor_grandeza, condicao, limite, histerese, atuador_grandeza)
                   VALUES ('Temperatura fora de +2..+8 °C liga o alarme', 'temperatura', 'fora_faixa', NULL, 0.3, 'alarme')""")
        await con.execute(
            """INSERT INTO configuracoes (chave, valor) VALUES
               ('faixa_vacinas', '{"min": 2, "max": 8}'),
               ('assistente', '{"perguntas_por_minuto": 6}')
               ON CONFLICT (chave) DO NOTHING""")


async def auditar(usuario: str | None, acao: str, detalhe: dict | None = None, ip: str | None = None):
    try:
        await pool.execute("INSERT INTO auditoria (usuario, acao, detalhe, ip) VALUES ($1,$2,$3,$4)",
                           usuario, acao, detalhe or {}, ip)
    except Exception as e:  # noqa: BLE001
        log.warning("Falha ao gravar auditoria: %s", e)


def linha(r) -> dict:
    d = dict(r)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d
