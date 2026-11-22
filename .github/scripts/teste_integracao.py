"""Teste de integracao: confere os tres fluxos com a pilha inteira rodando no Docker Compose.

Tudo passa pelo frontend (nginx em http://localhost:8080), como no navegador.
Uso: python teste_integracao.py  (le as senhas do .env na raiz do projeto)
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8080"
ENV = dict(
    linha.split("=", 1)
    for linha in Path(__file__).resolve().parents[2].joinpath(".env").read_text().splitlines()
    if "=" in linha and not linha.startswith("#")
)


def req(metodo, caminho, corpo=None, token=None, timeout=30):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    r = urllib.request.Request(BASE + caminho, data=dados, method=metodo)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        texto = resp.read().decode()
        return resp.status, (json.loads(texto) if texto and resp.headers.get_content_type() == "application/json" else texto)


def esperar(descricao, condicao, limite_s, intervalo=10):
    inicio = time.time()
    ultimo_erro = None
    while time.time() - inicio < limite_s:
        try:
            valor = condicao()
            if valor:
                print(f"  OK  {descricao} ({time.time() - inicio:.0f} s)")
                return valor
        except Exception as e:  # servico ainda subindo
            ultimo_erro = e
        time.sleep(intervalo)
    print(f"  FALHOU  {descricao} (esperou {limite_s} s; ultimo erro: {ultimo_erro})")
    sys.exit(1)


print("== Frontend e API")
esperar("frontend responde", lambda: req("GET", "/")[0] == 200, 300)
esperar("API saudavel pelo nginx", lambda: req("GET", "/api/saude")[0] == 200, 300)

tokens = {}
for usuario, chave in (("administrador", "ADMIN_SENHA"), ("operador", "OPERADOR_SENHA"), ("visualizador", "VISUALIZADOR_SENHA")):
    tokens[usuario] = req("POST", "/api/auth/login", {"login": usuario, "senha": ENV[chave]})[1]["token"]
    print(f"  OK  login {usuario}")
adm, oper, vis = tokens["administrador"], tokens["operador"], tokens["visualizador"]

try:
    req("POST", "/api/auth/login", {"login": "administrador", "senha": "admin"})
    print("  FALHOU  senha errada foi aceita"); sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 401, e.code
    print("  OK  senha errada recusada (401)")

print("== Fluxo IoT -> Web (simulador, MQTT, gateway, RabbitMQ, API)")
esperar("leituras ao vivo chegando",
        lambda: (lambda d: d["leituras"] and d["segundos_desde_ultima"] is not None and d["segundos_desde_ultima"] < 60)(
            req("GET", "/api/leituras/atuais", token=vis)[1]), 300)
esperar("historico gravado no InfluxDB",
        lambda: any(req("GET", f"/api/leituras/historico?dispositivo={l['dispositivo']}", token=vis)[1]["pontos"]
                    for l in req("GET", "/api/leituras/atuais", token=vis)[1]["leituras"][:5]), 240, 15)

print("== Fluxo Web -> IoT (comando, RabbitMQ, gateway, MQTT, simulador)")
dispositivos = req("GET", "/api/dispositivos", token=vis)[1]
manual = next(d for d in dispositivos if d["categoria"] == "atuador" and d["controle"] == "manual")
try:
    req("POST", "/api/comandos", {"dispositivo": manual["id"], "acao": "ligar"}, token=vis)
    print("  FALHOU  visualizador conseguiu comandar"); sys.exit(1)
except urllib.error.HTTPError as e:
    assert e.code == 403, e.code
    print("  OK  visualizador nao pode comandar (403)")
assert req("POST", "/api/comandos", {"dispositivo": manual["id"], "acao": "ligar"}, token=oper)[0] == 202
print(f"  OK  operador ligou {manual['id']}")


def atuador_ligado():
    leituras = req("GET", "/api/leituras/atuais", token=vis)[1]["leituras"]
    return any(l["dispositivo"] == manual["id"] and l["conteudo"].get("estado") == "ligado" for l in leituras)


esperar(f"{manual['id']} aparece ligado nas leituras seguintes", atuador_ligado, 120, 5)

print("== Fluxo IA (laboratorio, treino, inferencia)")
esperar("primeiro modelo treinado pelo lab",
        lambda: req("GET", "/api/modelos", token=vis)[1]["modelos"], 900, 15)
modelos = req("GET", "/api/modelos", token=vis)[1]["modelos"]
print("      metricas:", json.dumps(modelos[0]["metricas"], ensure_ascii=False)[:600])
esperar("inferencia publicando previsoes ao vivo",
        lambda: req("GET", "/api/leituras/atuais", token=vis)[1]["previsoes"], 300, 10)
esperar("insights por equipamento", lambda: req("GET", "/api/insights", token=vis)[1], 120, 10)

print("== Mensageria e auditoria")
m = req("GET", "/api/mensageria", token=adm)[1]
print("      mensageria:", json.dumps(m, ensure_ascii=False)[:400])
aud = req("GET", "/api/auditoria", token=adm)[1]
acoes = {a["acao"] for a in aud}
assert {"login", "comando"} <= acoes, acoes
print("  OK  auditoria registrou login e comando")

print("== Assistente (LLM local)")
esperar("modelo do Ollama carregado",
        lambda: req("GET", "/api/assistente/status", token=vis)[1]["carregado"], 900, 15)
_, resposta = req("POST", "/api/assistente/perguntar",
                  {"pergunta": "Qual equipamento esta com pior saude?"}, token=vis, timeout=300)
print("      resposta (inicio):", str(resposta)[:300].replace("\n", " "))
assert resposta, "assistente nao respondeu"
print("  OK  assistente respondeu")

print("\nTODOS OS FLUXOS FUNCIONANDO")
