"""Servico 'Lab e treino': executa os jobs demorados em segundo plano.

  q.jobs.geracao  ->  gera o conjunto sintetico em /dados/lab/<job>/ e grava uma amostra no bucket 'lab'
  q.jobs.treino   ->  treina os modelos e publica uma nova versao em /modelos (volume compartilhado)

Progresso e resultado voltam pelo RabbitMQ (job.progress.<tipo> e job.done.<tipo>) ate a
API, que repassa para a interface pelo WebSocket. Um job por vez (prefetch=1).
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from influxdb_client import Point, WritePrecision

from ..comum import influx, mensagens
from ..comum.amqp import Barramento
from ..comum.config import MINUTOS_POR_TICK, env
from ..comum.saude import batimento_continuo, configurar_logs
from . import gerador, treino

log = logging.getLogger("lab")
DIR_DADOS = Path(env("DIR_DADOS", "/dados")) / "lab"
DIR_MODELOS = Path(env("DIR_MODELOS", "/modelos"))


def ultimo_dataset() -> Path | None:
    ponteiro = DIR_DADOS / "ultimo.txt"
    if ponteiro.exists():
        p = DIR_DADOS / ponteiro.read_text().strip()
        if (p / "dataset.npz").exists():
            return p
    return None


def gravar_amostra_lab(pasta: Path, job_id: str):
    cli = influx.cliente()
    try:
        influx.garantir_bucket(cli, influx.BUCKET_LAB, retencao_s=30 * 86400)
        w = cli.write_api(write_options=influx.SYNCHRONOUS)
        inicio = datetime.now(timezone.utc) - timedelta(days=400)
        lote = []
        for m, t, valores in gerador.amostra_para_influx(pasta):
            p = Point("sintetico").tag("job", job_id).tag("maquina", f"m{m:03d}")
            for k, v in valores.items():
                if v == v:  # ignora NaN
                    p = p.field(k, v)
            lote.append(p.time(inicio + timedelta(minutes=t * MINUTOS_POR_TICK), WritePrecision.S))
            if len(lote) >= 5000:
                w.write(bucket=influx.BUCKET_LAB, record=lote); lote = []
        if lote:
            w.write(bucket=influx.BUCKET_LAB, record=lote)
    finally:
        cli.close()


async def main():
    configurar_logs()
    loop = asyncio.get_running_loop()
    bus = await Barramento("RABBIT_LAB_USUARIO", "RABBIT_LAB_SENHA", prefetch=1).conectar()

    def reporter(tipo: str, job_id: str):
        ultimo = {"t": 0.0}

        def _rep(frac: float, texto: str):
            agora = time.time()
            if agora - ultimo["t"] < 1.0 and frac < 1.0:
                return
            ultimo["t"] = agora
            msg = mensagens.nova("job", "lab", {"job_id": job_id, "tipo": tipo, "status": "executando",
                                                "progresso": round(frac * 100, 1), "mensagem": texto})
            asyncio.run_coroutine_threadsafe(bus.publicar(f"job.progress.{tipo}", msg, persistente=False), loop)
        return _rep

    async def concluir(tipo, job_id, status, resultado):
        await bus.publicar(f"job.done.{tipo}", mensagens.nova(
            "job", "lab", {"job_id": job_id, "tipo": tipo, "status": status, "progresso": 100.0, "resultado": resultado}))

    async def executar_geracao(job_id: str, params: dict):
        p = gerador.ParametrosGeracao(**{k: v for k, v in params.items() if k in gerador.ParametrosGeracao.__dataclass_fields__})
        pasta = DIR_DADOS / job_id
        rep = reporter("geracao", job_id)
        resumo = await asyncio.to_thread(gerador.gerar, p, pasta, rep)
        (DIR_DADOS / "ultimo.txt").write_text(job_id)
        rep(0.98, "gravando amostra no bucket 'lab' do InfluxDB")
        try:
            await asyncio.to_thread(gravar_amostra_lab, pasta, job_id)
            resumo["amostra_influx"] = "bucket lab"
        except Exception as e:  # noqa: BLE001
            log.warning("Amostra no InfluxDB falhou: %s", e)
            resumo["amostra_influx"] = f"falhou: {e}"
        return resumo

    async def executar_treino(job_id: str, params: dict):
        pasta = ultimo_dataset()
        if pasta is None:
            raise RuntimeError("Nenhum conjunto de dados gerado ainda. Gere os dados no Laboratorio primeiro.")
        metricas = await asyncio.to_thread(treino.treinar, pasta, DIR_MODELOS, int(params.get("semente", 42)),
                                           reporter("treino", job_id))
        metricas["dataset"] = pasta.name
        return metricas

    def handler(tipo, func):
        async def _h(msg: dict, _rk: str):
            c = msg["conteudo"]
            job_id = mensagens.seguro(str(c.get("job_id", msg["id"])))
            log.info("Job %s (%s) iniciado", job_id, tipo)
            try:
                resultado = await func(job_id, c.get("parametros", {}))
                await concluir(tipo, job_id, "concluido", resultado)
                log.info("Job %s concluido", job_id)
            except ValueError as e:
                # parametro invalido: resposta de erro, sem reprocessar
                await concluir(tipo, job_id, "erro", {"erro": str(e)})
            except Exception as e:
                await concluir(tipo, job_id, "erro", {"erro": str(e)})
                raise  # vai para a DLQ com a mensagem preservada
        return _h

    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    await bus.consumir("q.jobs.geracao", handler("geracao", executar_geracao))
    await bus.consumir("q.jobs.treino", handler("treino", executar_treino))

    # Primeira subida: gera um conjunto padrao e treina, para a demo ja ter um modelo
    if env("LAB_AUTOTREINO", "1") == "1" and not (DIR_MODELOS / "atual.json").exists():
        async def autotreino():
            try:
                log.info("Sem modelo: gerando dados padrao e treinando o modelo inicial")
                r = await executar_geracao("inicial", {})
                await concluir("geracao", "inicial", "concluido", r)
                m = await executar_treino("inicial-treino", {})
                await concluir("treino", "inicial-treino", "concluido", m)
            except Exception:  # noqa: BLE001
                log.exception("Autotreino falhou")
        asyncio.create_task(autotreino())

    await batimento_continuo()


if __name__ == "__main__":
    asyncio.run(main())
