<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import VChart from '../echarts'
import MiniGrafico from '../components/MiniGrafico.vue'
import { get } from '../services/api'
import { comandar, fmt, nomeGeladeira, ultimoComando } from '../services/comandos'
import { pode } from '../stores/sessao'
import { alertasAbertos, dados, ROTULO_STATUS, statusDispositivo, versao, versaoCadastro } from '../stores/tempoReal'

const versaoModelo = ref<number | null>(null)
let timer = 0

const equipamentos = computed(() => {
  void versao.value
  void versaoCadastro.value
  return dados.dispositivos
    .filter((d) => d.categoria === 'equipamento' && d.ativo)
    .map((d) => {
      const p = dados.previsoes.get(d.id)
      return {
        d,
        p,
        status: statusDispositivo(d),
        tele: dados.leituras.get(d.id)?.conteudo,
        hist: dados.historico.get(`${d.id}#saude`) ?? [],
        alertas: alertasAbertos.value.filter((a) => a.dispositivo === d.id || a.dispositivo === `${d.geladeira}-temp`),
      }
    })
    .sort((a, b) => (a.p?.saude ?? 101) - (b.p?.saude ?? 101))
})

function gauge(valor: number | undefined) {
  return {
    series: [
      {
        type: 'gauge',
        min: 0,
        max: 100,
        radius: '95%',
        progress: { show: true, width: 12 },
        axisLine: {
          lineStyle: {
            width: 12,
            color: [
              [0.3, '#dc2626'],
              [0.6, '#eab308'],
              [1, '#16a34a'],
            ],
          },
        },
        itemStyle: { color: (valor ?? 0) < 30 ? '#dc2626' : (valor ?? 0) < 60 ? '#eab308' : '#16a34a' },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: { valueAnimation: false, fontSize: 26, offsetCenter: [0, '10%'], formatter: (v: number) => v.toFixed(0) },
        title: { offsetCenter: [0, '55%'], fontSize: 11 },
        data: [{ value: valor ?? 0, name: 'saúde' }],
      },
    ],
  }
}

function textoRul(h?: number) {
  if (h === undefined) return '—'
  if (h >= 160) return 'mais de 7 dias'
  return `≈ ${h.toFixed(0)} h`
}

const modo = ref<Record<string, string>>({})

onMounted(async () => {
  const carregar = async () => {
    try {
      versaoModelo.value = (await get<{ versao_em_uso: number | null }>('/api/modelos')).versao_em_uso
    } catch {
      /* ignore */
    }
  }
  await carregar()
  timer = window.setInterval(carregar, 15000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="grade">
    <div class="cartao linha entre">
      <span>
        Previsões em tempo real feitas pelo serviço de inferência sobre a telemetria que chega pelo RabbitMQ.
        Vida útil em <b>horas simuladas</b> (1 leitura = 5 min).
      </span>
      <span class="pilula">Modelo em uso: {{ versaoModelo ? `v${versaoModelo}` : '—' }}</span>
    </div>
    <p v-if="ultimoComando" :class="ultimoComando.erro ? 'erro' : 'suave'">{{ ultimoComando.texto }}</p>
    <div class="grade auto">
      <div v-for="e in equipamentos" :key="e.d.id" class="cartao eq">
        <div class="linha entre">
          <h2>Compressor · {{ nomeGeladeira(e.d.geladeira ?? '') }}</h2>
          <span class="pilula" :class="e.status">{{ ROTULO_STATUS[e.status] }}</span>
        </div>
        <template v-if="e.p?.status === 'ok'">
          <div class="topo-eq">
            <VChart :option="gauge(e.p.saude)" autoresize style="height: 150px; width: 160px" />
            <div class="numeros">
              <div><small>Vida útil restante</small><b>{{ textoRul(e.p.rul_h) }}</b></div>
              <div>
                <small>Tendência da saúde</small>
                <b :style="{ color: (e.p.tendencia ?? 0) < -0.5 ? 'var(--critico)' : 'inherit' }">
                  {{ (e.p.tendencia ?? 0) > 0.5 ? '↗' : (e.p.tendencia ?? 0) < -0.5 ? '↘' : '→' }} {{ fmt(e.p.tendencia, 1) }} pts/h
                </b>
              </div>
              <div><small>Compressor</small><b>{{ e.tele?.estado ?? '—' }}</b></div>
            </div>
          </div>
          <MiniGrafico :pontos="e.hist" :min="0" :max="100" cor="#7c3aed" :altura="80" />
        </template>
        <p v-else class="suave">
          {{ e.p?.status === 'aquecendo' ? `Acumulando histórico: ${e.p.leituras}/${e.p.necessarias} leituras` : e.p?.status === 'sem_modelo' ? 'Nenhum modelo treinado ainda (veja Treinamento).' : 'Aguardando previsões…' }}
        </p>
        <div class="linha medidas mono">
          <span>vib {{ fmt(e.tele?.vibracao, 2) }} mm/s</span>
          <span>{{ fmt(e.tele?.corrente, 2) }} A</span>
          <span>{{ fmt(e.tele?.temp_compressor) }} °C</span>
        </div>
        <div v-for="a in e.alertas" :key="a.id" class="alerta" :class="a.severidade">
          <b>{{ a.tipo.replace(/_/g, ' ') }}</b> — {{ a.mensagem }}
        </div>
        <div v-if="!e.alertas.length" class="suave">Sem alertas ativos.</div>
        <div v-if="pode('operador')" class="linha sim">
          <select v-model="modo[e.d.id]">
            <option value="">modo de falha…</option>
            <option v-for="m in ['rolamento', 'entupimento', 'superaquecimento', 'desbalanceamento']" :key="m">{{ m }}</option>
          </select>
          <button class="btn-perigo" :disabled="!modo[e.d.id]" @click="comandar(e.d.id, 'injetar_falha', { modo: modo[e.d.id], horas: 24 })">
            Injetar (24 h)
          </button>
          <button class="btn-sec" @click="comandar(e.d.id, 'reparar')">Reparar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.eq {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.topo-eq {
  display: flex;
  gap: 8px;
  align-items: center;
}
.numeros {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.numeros div {
  display: flex;
  flex-direction: column;
}
.numeros small {
  color: var(--texto-suave);
  font-size: 0.75rem;
}
.medidas {
  font-size: 0.82rem;
  color: var(--texto-suave);
}
.alerta {
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 0.84rem;
  background: #fef9c3;
}
.alerta.critico {
  background: #fee2e2;
}
.sim select {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 5px 8px;
}
</style>
