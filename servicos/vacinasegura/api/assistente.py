"""Assistente com LLM local (Ollama, em CPU, dentro do Docker Compose).

* O backend monta um RESUMO pronto dos dados atuais (saude, RUL, alertas, metricas do
  modelo, ultimas leituras) e envia junto com a pergunta. Modelos pequenos erram ao
  chamar ferramentas, entao nao ha tool calling: o LLM nunca acessa os bancos.
* As unicas "ferramentas" sao as funcoes de leitura da lista fixa FONTES abaixo,
  executadas pelo backend (somente leitura).
* A resposta volta em streaming (NDJSON), e a interface trata o texto como nao confiavel.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque

import httpx

from ..comum.config import env
from . import db
from .tempo_real import estado

OLLAMA = env("OLLAMA_URL", "http://ollama:11434")
MODELO = env("OLLAMA_MODELO", "llama3.2:1b")
_historico_perguntas: dict[str, deque] = defaultdict(deque)

ARQUITETURA = """\
Fluxo: simulador Python (sensores e atuadores) -> MQTT/Mosquitto -> gateway -> RabbitMQ (exchange topic vs.topic)
-> filas: q.gravador (grava no InfluxDB), q.inferencia (IA de regressao ao vivo), q.websocket (API envia ao navegador),
q.regras (regra de negocio do alarme), q.api.eventos (alertas e jobs no PostgreSQL), q.comandos (comandos de volta ao
dispositivo), q.jobs.geracao e q.jobs.treino (jobs demorados do laboratorio), q.dlq (mensagens que falharam).
Por que cada tecnologia: MQTT e leve para dispositivos de borda; RabbitMQ desacopla os servicos internos e segura
mensagens se um consumidor parar; InfluxDB guarda series temporais de leituras; PostgreSQL guarda usuarios,
dispositivos, regras, alertas e auditoria; FastAPI expoe REST e WebSocket; scikit-learn treina os modelos;
Ollama roda o LLM localmente sem enviar dados para a nuvem; Docker Compose sobe tudo com um comando.
Dominio: geladeiras de vacinas em UBS devem ficar entre +2 e +8 graus C. O compressor e o equipamento monitorado
(vibracao, corrente e temperatura do compressor). Os modelos preveem a vida util restante (RUL, horas simuladas, teto 168 h)
e o indice de saude (0 a 100). Alertas da IA: saude < 50 (atencao) e RUL < 24 h (critico), com histerese.
"""

SISTEMA = """Voce e o assistente do VacinaSegura, sistema que monitora geladeiras de vacinas em UBS.
Responda SEMPRE em portugues do Brasil, de forma curta e pratica (no maximo 8 frases ou uma lista curta).
Use APENAS os dados do bloco DADOS ATUAIS; se a informacao nao estiver la, diga que nao sabe.
Nunca invente numeros. Explique metricas em palavras simples (MAE = erro medio; R2 perto de 1 = bom).
Quando houver risco para as vacinas, diga o que fazer (transferir vacinas, chamar manutencao).
Responda em Markdown simples, sem HTML e sem imagens."""


async def _fonte_estado() -> str:
    linhas = []
    for disp, msg in estado.previsoes.items():
        c = msg["conteudo"]
        if c.get("status") == "ok":
            linhas.append((c["saude"], f"- {disp}: saude {c['saude']:.0f}/100, RUL {c['rul_h']:.0f} h, "
                           f"tendencia {c['tendencia']:+.1f} pts/h, compressor {c.get('estado_compressor')}, "
                           f"modelo v{c.get('versao_modelo')}"))
        else:
            linhas.append((999.0, f"- {disp}: previsao indisponivel ({c.get('status')})"))
    temps = []
    for disp, msg in sorted(estado.ultimas_leituras.items()):
        c = msg["conteudo"]
        if c.get("grandeza") in ("temperatura", "temp_ambiente", "porta") or c.get("grandeza") in ("alarme", "resfriamento", "luz"):
            v = c.get("valor") if "valor" in c else c.get("estado")
            temps.append(f"{disp}={v}")
    idade = time.time() - estado.ultima_telemetria if estado.ultima_telemetria else None
    situacao = f"Ultima telemetria ha {idade:.0f} s." if idade is not None else "Sem telemetria recebida ainda."
    return ("Previsoes da IA por compressor (pior saude primeiro):\n"
            + "\n".join(t for _, t in sorted(linhas))
            + "\nUltimas leituras: " + ", ".join(temps[:40])
            + "\n" + situacao)


async def _fonte_alertas() -> str:
    rows = await db.pool.fetch(
        "SELECT dispositivo, tipo, severidade, mensagem, aberto_em FROM alertas WHERE fechado_em IS NULL ORDER BY aberto_em DESC LIMIT 15")
    if not rows:
        return "Alertas abertos: nenhum."
    return "Alertas abertos:\n" + "\n".join(
        f"- [{r['severidade']}] {r['dispositivo']} {r['tipo']}: {r['mensagem']} (desde {r['aberto_em']:%d/%m %H:%M})" for r in rows)


async def _fonte_modelo() -> str:
    r = await db.pool.fetchrow("SELECT versao, metricas FROM modelos ORDER BY versao DESC LIMIT 1")
    if not r:
        return "Modelo: nenhum treino registrado ainda."
    m = r["metricas"]["modelos"]
    partes = []
    for alvo, met in m.items():
        t, b = met["teste"], met["base_media"]
        top = ", ".join(i["feature"] for i in met["importancia"][:3])
        partes.append(f"- {alvo} ({met['algoritmo']}): MAE {t['mae']:.2f}, RMSE {t['rmse']:.2f}, R2 {t['r2']:.2f}; "
                      f"base (media) MAE {b['mae']:.2f}; vence a base: {met['vence_base']}; atributos mais importantes: {top}")
    d = r["metricas"].get("dados") or {}
    return (f"Ultimo treino: modelo v{r['versao']}, {d.get('leituras')} leituras sinteticas de {d.get('equipamentos')} "
            f"equipamentos, divisao por equipamento.\n" + "\n".join(partes))


# Lista FIXA de fontes somente leitura que alimentam o resumo
FONTES = {"estado_atual": _fonte_estado, "alertas_abertos": _fonte_alertas, "metricas_modelo": _fonte_modelo}


async def montar_resumo() -> str:
    blocos = [await f() for f in FONTES.values()]
    return "DADOS ATUAIS\n" + "\n\n".join(blocos) + "\n\nARQUITETURA\n" + ARQUITETURA


def dentro_do_limite(login: str, por_minuto: int) -> bool:
    fila = _historico_perguntas[login]
    agora = time.time()
    while fila and fila[0] < agora - 60:
        fila.popleft()
    if len(fila) >= por_minuto:
        return False
    fila.append(agora)
    return True


async def modelo_carregado() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{OLLAMA}/api/ps")
            return any(m.get("name", "").startswith(MODELO) or m.get("model", "").startswith(MODELO)
                       for m in r.json().get("models", []))
    except Exception:  # noqa: BLE001
        return False


async def responder(pergunta: str, historico: list[dict]):
    """Gera linhas NDJSON: status, token..., fim."""
    def linha(**k):
        return (json.dumps(k, ensure_ascii=False) + "\n").encode()

    if not await modelo_carregado():
        yield linha(tipo="status", texto=f"Carregando o modelo {MODELO} na memoria (a primeira resposta em CPU demora)...")
    resumo = await montar_resumo()
    msgs = [{"role": "system", "content": SISTEMA + "\n\n" + resumo}]
    for h in historico[-6:]:
        if h.get("papel") in ("user", "assistant") and isinstance(h.get("texto"), str):
            msgs.append({"role": h["papel"], "content": h["texto"][:2000]})
    msgs.append({"role": "user", "content": pergunta})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5)) as c:
            async with c.stream("POST", f"{OLLAMA}/api/chat", json={
                "model": MODELO, "messages": msgs, "stream": True, "keep_alive": "60m",
                "options": {"temperature": 0.2, "num_ctx": 4096},
            }) as r:
                if r.status_code != 200:
                    yield linha(tipo="erro", texto=f"Ollama respondeu {r.status_code}: {(await r.aread())[:200].decode(errors='ignore')}")
                    return
                primeiro = True
                async for l in r.aiter_lines():
                    if not l:
                        continue
                    d = json.loads(l)
                    if primeiro:
                        yield linha(tipo="status", texto="")
                        primeiro = False
                    pedaco = (d.get("message") or {}).get("content", "")
                    if pedaco:
                        yield linha(tipo="token", texto=pedaco)
                    if d.get("done"):
                        break
    except httpx.HTTPError as e:
        yield linha(tipo="erro", texto=f"LLM local indisponivel: {e}")
        return
    yield linha(tipo="fim")
