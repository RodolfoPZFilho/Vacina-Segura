<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import VChart from '../echarts'
import { enviar, get } from '../services/api'
import { pode } from '../stores/sessao'

interface Fila {
  nome: string
  mensagens: number
  prontas: number
  nao_confirmadas: number
  consumidores: number
  taxa_publicacao: number
  taxa_entrega: number
  taxa_confirmacao: number
  dlq: boolean
}
interface Painel {
  filas: Fila[]
  totais: { publicacao: number; entrega: number; mensagens: number }
  consumidores: { fila: string; usuario: string; conexao: string; prefetch: number }[]
  conexoes: { nome: string; usuario: string; estado: string }[]
  ultimas_mensagens: { routing_key: string; recebida: string; tipo: string; dispositivo: string; conteudo: unknown }[]
}

const painel = ref<Painel | null>(null)
const erro = ref('')
const dlq = ref<{ routing_key: string; payload: string; fila_origem: string; motivo: string; vezes: number }[]>([])
const historico = ref<Record<string, number[][]>>({})
let timer = 0

const PAPEL_FILA: Record<string, string> = {
  'q.gravador': 'gravador → InfluxDB',
  'q.inferencia': 'inferência da IA',
  'q.websocket': 'API → WebSocket',
  'q.regras': 'API · regra do alarme',
  'q.api.eventos': 'API · alertas e jobs → PostgreSQL',
  'q.comandos': 'gateway → MQTT → dispositivo',
  'q.jobs.geracao': 'lab · geração de dados',
  'q.jobs.treino': 'lab · treino',
  'q.dlq': 'mensagens mortas',
}

async function carregar() {
  try {
    painel.value = await get<Painel>('/api/mensageria')
    erro.value = ''
    const agora = Date.now()
    for (const f of painel.value.filas) {
      const h = historico.value[f.nome] ?? []
      h.push([agora, f.mensagens])
      if (h.length > 90) h.shift()
      historico.value[f.nome] = h
    }
    if (painel.value.filas.find((f) => f.nome === 'q.dlq')?.mensagens) dlq.value = await get('/api/mensageria/dlq')
    else dlq.value = []
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function limparDlq() {
  if (!confirm('Esvaziar a DLQ? As mensagens serão descartadas.')) return
  await enviar('DELETE', '/api/mensageria/dlq')
  carregar()
}

onMounted(() => {
  carregar()
  timer = window.setInterval(carregar, 2000)
})
onUnmounted(() => clearInterval(timer))

const opcaoFilas = computed(() => ({
  animation: false,
  grid: { left: 40, right: 12, top: 30, bottom: 30 },
  tooltip: { trigger: 'axis' },
  legend: { type: 'scroll', top: 0 },
  xAxis: { type: 'time' },
  yAxis: { type: 'value', name: 'msgs na fila', minInterval: 1 },
  series: Object.entries(historico.value).map(([nome, pontos]) => ({ name: nome, type: 'line', showSymbol: false, data: pontos })),
}))
</script>

<template>
  <div class="grade">
    <p v-if="erro" class="erro">{{ erro }}</p>
    <div v-if="painel" class="grade g4">
      <div class="cartao kpi"><div class="rotulo">Publicação total</div><div class="valor">{{ painel.totais.publicacao.toFixed(1) }}</div><div class="sub">msgs/s</div></div>
      <div class="cartao kpi"><div class="rotulo">Entrega total</div><div class="valor">{{ painel.totais.entrega.toFixed(1) }}</div><div class="sub">msgs/s</div></div>
      <div class="cartao kpi"><div class="rotulo">Mensagens em filas</div><div class="valor">{{ painel.totais.mensagens }}</div></div>
      <div class="cartao kpi"><div class="rotulo">Consumidores conectados</div><div class="valor">{{ painel.consumidores.length }}</div><div class="sub">{{ painel.conexoes.length }} conexões</div></div>
    </div>

    <div v-if="painel" class="cartao rolagem">
      <h2>Filas do exchange <code>vs.topic</code></h2>
      <table class="tabela">
        <thead>
          <tr><th>Fila</th><th>Papel</th><th>Mensagens</th><th>Prontas</th><th>Sem ack</th><th>Consumidores</th><th>Publicação/s</th><th>Entrega/s</th><th>DLQ</th></tr>
        </thead>
        <tbody>
          <tr v-for="f in painel.filas" :key="f.nome" :class="{ parado: f.consumidores === 0 && f.nome !== 'q.dlq' }">
            <td class="mono">{{ f.nome }}</td>
            <td>{{ PAPEL_FILA[f.nome] ?? '' }}</td>
            <td class="mono"><b>{{ f.mensagens }}</b></td>
            <td class="mono">{{ f.prontas }}</td>
            <td class="mono">{{ f.nao_confirmadas }}</td>
            <td>
              <span class="pilula" :class="f.consumidores ? 'normal' : f.nome === 'q.dlq' ? '' : 'critico'">{{ f.consumidores }}</span>
            </td>
            <td class="mono">{{ f.taxa_publicacao.toFixed(2) }}</td>
            <td class="mono">{{ f.taxa_entrega.toFixed(2) }}</td>
            <td>{{ f.dlq ? 'sim' : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p class="suave nota">
        Demonstração do consumidor parado: <code>docker compose stop gravador</code> → a fila <b>q.gravador</b> cresce;
        <code>docker compose start gravador</code> → ela esvazia.
      </p>
    </div>

    <div class="cartao">
      <h2>Mensagens por fila (ao vivo)</h2>
      <VChart :option="opcaoFilas" autoresize style="height: 260px" />
    </div>

    <div v-if="painel" class="grade g2">
      <div class="cartao rolagem">
        <h2>Consumidores</h2>
        <table class="tabela">
          <thead><tr><th>Fila</th><th>Usuário RabbitMQ</th><th>Prefetch</th></tr></thead>
          <tbody>
            <tr v-for="c in painel.consumidores" :key="c.fila + c.conexao"><td class="mono">{{ c.fila }}</td><td class="mono">{{ c.usuario }}</td><td class="mono">{{ c.prefetch }}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="cartao">
        <div class="linha entre">
          <h2>DLQ (q.dlq)</h2>
          <button v-if="pode('administrador') && dlq.length" class="btn-perigo" @click="limparDlq">Esvaziar</button>
        </div>
        <div v-if="!dlq.length" class="vazio">Nenhuma mensagem morta.</div>
        <div v-for="(m, i) in dlq" :key="i" class="dlq">
          <div class="linha"><span class="pilula critico">{{ m.motivo }}</span><span class="mono">{{ m.fila_origem }}</span><span class="mono suave">{{ m.routing_key }}</span></div>
          <pre>{{ m.payload }}</pre>
        </div>
      </div>
    </div>

    <div v-if="painel" class="cartao rolagem">
      <h2>Últimas mensagens (formato único JSON)</h2>
      <table class="tabela">
        <thead><tr><th>Recebida</th><th>Routing key</th><th>Tipo</th><th>Conteúdo</th></tr></thead>
        <tbody>
          <tr v-for="m in painel.ultimas_mensagens.slice(0, 15)" :key="m.recebida + m.routing_key">
            <td class="mono">{{ new Date(m.recebida).toLocaleTimeString() }}</td>
            <td class="mono">{{ m.routing_key }}</td>
            <td>{{ m.tipo }}</td>
            <td class="mono conteudo">{{ JSON.stringify(m.conteudo) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.nota {
  font-size: 0.84rem;
  margin-bottom: 0;
}
tr.parado td {
  background: #fff7ed;
}
.dlq {
  border-top: 1px solid var(--borda);
  padding: 6px 0;
}
pre {
  font-size: 0.75rem;
  white-space: pre-wrap;
  word-break: break-all;
  background: #f8fafc;
  padding: 6px;
  border-radius: 6px;
  margin: 4px 0 0;
}
.conteudo {
  font-size: 0.75rem;
  word-break: break-all;
}
</style>
