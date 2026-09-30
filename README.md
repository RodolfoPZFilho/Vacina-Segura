# VacinaSegura

Monitoramento IoT da temperatura das geladeiras de vacinas das unidades basicas de saude (UBS).

## Problema

As vacinas precisam ser conservadas entre **+2 °C e +8 °C**. Em muitas unidades, a temperatura da geladeira e conferida manualmente algumas vezes por dia e anotada em papel. Uma falha a noite ou uma porta mal fechada no fim de semana passa despercebida, e lotes inteiros de vacinas acabam descartados.

O VacinaSegura mede a temperatura continuamente, guarda o historico e mostra em um painel Web se a geladeira esta dentro da faixa segura.

## Arquitetura

```
ESP32 + DHT22 (Wokwi) -> MQTT -> Mosquitto -> Python -> InfluxDB -> Dashboard Vue
```

| Camada | Tecnologia | Pasta |
|---|---|---|
| Dispositivo | ESP32 + sensor DHT22 simulado no Wokwi | `firmware/` |
| Comunicacao | MQTT + Mosquitto (porta 1884) | `infra/mosquitto.conf` |
| Backend | Python (FastAPI + paho-mqtt) | `backend/` |
| Banco de series temporais | InfluxDB 2.x | `infra/configurar-influxdb.ps1` |
| Frontend | Vue.js 3 + TypeScript + Vite | `frontend/` |
| Visualizacao | Apache ECharts | `frontend/src/components/` |

### Por que existe uma "ponte" no Mosquitto?

O ESP32 simulado no Wokwi roda nos servidores do Wokwi e nao acessa a rede local do computador. Por isso ele publica no broker publico `broker.hivemq.com`, e o Mosquitto do projeto se conecta a esse broker como **ponte (bridge)**, trazendo as mensagens para o broker local. O backend Python assina apenas o Mosquitto local.

| Onde | Topico |
|---|---|
| Broker publico (Wokwi) | `vacinasegura/35kr1sud/ubs/<ubs>/geladeira/<geladeira>` |
| Mosquitto local | `vacinasegura/ubs/<ubs>/geladeira/<geladeira>` |

Payload (JSON): `{"temperatura": 5.2, "umidade": 61.0}`

## Pre-requisitos

- Git, Node.js 20+ e Python 3.12
- Mosquitto 2.x (`C:\Program Files\mosquitto`)
- InfluxDB 2.x (`influxd`) e o cliente `influx`

## Como rodar (Windows)

```powershell
git clone <url-do-repositorio>
cd vacinasegura
powershell -ExecutionPolicy Bypass -File iniciar.ps1
```

Na primeira execucao o script configura o InfluxDB, cria o ambiente virtual do Python e instala as dependencias do frontend. Depois ficam disponiveis:

- Dashboard: http://localhost:5173
- Documentacao da API: http://localhost:8000/docs
- Interface do InfluxDB: http://localhost:8086 (usuario e senha em `backend/.env`)

Para encerrar: `powershell -ExecutionPolicy Bypass -File parar.ps1`

## Acesso pela internet

Com o sistema rodando (`iniciar.ps1`), execute:

```powershell
powershell -ExecutionPolicy Bypass -File publicar-web.ps1
```

O script usa o Cloudflare Tunnel (`cloudflared`) e mostra um link publico `https://....trycloudflare.com` que abre o dashboard de qualquer maquina. O link so funciona enquanto este computador e a janela do script estiverem abertos, e muda a cada execucao. Apenas o dashboard e a API de leitura ficam expostos; o InfluxDB e o Mosquitto continuam acessiveis so localmente.

## Dispositivo no Wokwi

1. Em [wokwi.com](https://wokwi.com), crie um projeto **ESP32** (Arduino).
2. Substitua o conteudo de `sketch.ino` e `diagram.json` pelos arquivos da pasta `firmware/`.
3. Na aba **Library Manager**, adicione `PubSubClient` e `DHT sensor library for ESPx`.
4. Clique em Play. Durante a simulacao, clique no DHT22 para mudar a temperatura: acima de 8 °C o LED vermelho acende e o dashboard mostra o alerta.

## Testar sem o Wokwi

O simulador publica no mesmo broker e topico que o ESP32:

```powershell
backend\.venv\Scripts\python.exe ferramentas\simulador.py           # geladeira normal
backend\.venv\Scripts\python.exe ferramentas\simulador.py --falha   # porta aberta
```

## API

| Rota | Descricao |
|---|---|
| `GET /api/saude` | Situacao do backend e da conexao MQTT |
| `GET /api/config` | Faixa segura (min./max.) |
| `GET /api/geladeiras` | Geladeiras com a ultima temperatura |
| `GET /api/leituras/atual?ubs=&geladeira=` | Leitura mais recente |
| `GET /api/leituras/historico?ubs=&geladeira=&periodo=` | Historico (`15m`, `1h`, `6h`, `24h`, `7d`) e estatisticas |

## Proximas etapas (2o bimestre)

- Alertas por e-mail ou Telegram quando a temperatura sair da faixa
- Varias UBS e geladeiras no mesmo painel
- Sensor de porta aberta
- Relatorio diario em substituicao a planilha de papel