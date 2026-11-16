<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MiniGrafico from '../components/MiniGrafico.vue'
import VChart from '../echarts'
import { get } from '../services/api'
import { comandar, fmt, nomeGeladeira, NOMES_GRANDEZA, NOMES_UBS, ultimoComando } from '../services/comandos'
import { pode } from '../stores/sessao'
import {
  alertasAbertos,
  COR_STATUS,
  dados,
  pior,
  ROTULO_STATUS,
  statusDispositivo,
  versao,
  versaoCadastro,
} from '../stores/tempoReal'
import type { Dispositivo, Status } from '../types'

const periodo = ref<'15m' | '1h' | '6h' | '24h' | '7d'>('1h')
const selecionado = ref('ubs01-g01-temp')
const campo = ref('valor')
const historico = ref<{ ts: string; valor: number }[]>([])
const estat = ref<Record<string, number>>({})
const erroHist = ref('')

const dispositivos = computed(() => {
  void versaoCadastro.value
  return dados.dispositivos
})

const geladeiras = computed(() => {
  void versao.value
  const mapa = new Map<string, Dispositivo[]>()
  for (const d of dispositivos.value) if (d.geladeira && d.ativo) mapa.set(d.geladeira, [...(mapa.get(d.geladeira) ?? []), d])
  return [...mapa.entries()].map(([gid, ds]) => {
    const por = (g: string) => ds.find((d) => d.grandeza === g)
    const l = (d?: Dispositivo) => (d ? dados.leituras.get(d.id)?.conteudo : undefined)
    const comp = por('compressor')
    const status = pior(...ds.map((d) => statusDispositivo(d)).filter((s): s is Status => s !== 'sem_dados'))
    const semNada = ds.every((d) => statusDispositivo(d) === 'sem_dados')
    return {
      gid,
      status: semNada ? ('sem_dados' as Status) : status,
      temp: l(por('temperatura'))?.valor,
      umid: l(por('umidade'))?.valor,
      porta: l(por('porta'))?.valor,
      comp: l(comp),
      prev: comp ? dados.previsoes.get(comp.id) : undefined,
      alarme: l(por('alarme'))?.estado,
      resfr: por('resfriamento'),
      resfrEstado: l(por('resfriamento'))?.estado,
      tempId: por('temperatura')?.id,
      hist: por('temperatura') ? dados.historico.get(por('temperatura')!.id) ?? [] : [],
    }
  })
})

const salas = computed(() => {
  void versao.value
  const ubs = [...new Set(dispositivos.value.map((d) => d.ubs))]
  return ubs.map((u) => {
    const por = (g: string) => dispositivos.value.find((d) => d.ubs === u && !d.geladeira && d.grandeza === g)
    const luz = por('luz')
    return {
      ubs: u,
      tamb: dados.leituras.get(por('temp_ambiente')?.id ?? '')?.conteudo.valor,
      lux: dados.leituras.get(por('luminosidade')?.id ?? '')?.conteudo.valor,
      hora: dados.leituras.get(por('temp_ambiente')?.id ?? '')?.conteudo.hora_sim,
      luz,
      luzEstado: dados.leituras.get(luz?.id ?? '')?.conteudo.estado,
    }
  })
})

const kpis = computed(() => {
  const g = geladeiras.value
  const saudes = g.map((x) => (x.prev?.status === 'ok' ? x.prev.saude ?? 100 : null)).filter((x): x is number => x !== null)
  return {
    foraFaixa: g.filter((x) => typeof x.temp === 'number' && (x.temp < 2 || x.temp > 8)).length,
    total: g.length,
    alertas: alertasAbertos.value.length,
    criticos: alertasAbertos.value.filter((a) => a.severidade === 'critico').length,
    piorSaude: saudes.length ? Math.min(...saudes) : null,
    taxa: dados.msgsPorSegundo,
  }
})

function hora(h?: number) {
  if (typeof h !== 'number') return '—'
  const hh = Math.floor(h)
  return `${String(hh).padStart(2, '0')}:${String(Math.floor((h - hh) * 60)).padStart(2, '0')}`
}

async function carregarHistorico() {
  erroHist.value = ''
  try {
    const r = await get<{ pontos: { ts: string; valor: number }[]; estatisticas: Record<string, number> }>(
      `/api/leituras/historico?dispositivo=${selecionado.value}&periodo=${periodo.value}&campo=${campo.value}`,
    )
    historico.value = r.pontos
    estat.value = r.estatisticas
  } catch (e) {
    erroHist.value = (e as Error).message
  }
}

const dispSel = computed(() => dispositivos.value.find((d) => d.id === selecionado.value))
const camposSel = computed(() =>
  dispSel.value?.grandeza === 'compressor' ? ['vibracao', 'corrente', 'temp_compressor'] : ['valor'],
)
watch(selecionado, () => {
  campo.value = camposSel.value[0]
})
watch([selecionado, periodo, campo], carregarHistorico)
onMounted(() => {
  carregarHistorico()
  setInterval(carregarHistorico, 30_000)
})

const opcaoHist = computed(() => {
  const d = dispSel.value
  const faixa = d && d.faixa_min !== null && d.faixa_max !== null && d.faixa_max > d.faixa_min ? [d.faixa_min, d.faixa_max] : null
  return {
    animation: false,
    grid: { left: 46, right: 16, top: 16, bottom: 56 },
    tooltip: { trigger: 'axis' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 8 }],
    xAxis: { type: 'time' },
    yAxis: { type: 'value', scale: true, name: d?.unidade },
    series: [
      {
        type: 'line',
        showSymbol: false,
        data: historico.value.map((p) => [p.ts, p.valor]),
        lineStyle: { width: 2, color: '#0e7490' },
        markArea: faixa
          ? { silent: true, itemStyle: { color: 'rgba(22,163,74,0.08)' }, data: [[{ yAxis: faixa[0] }, { yAxis: faixa[1] }]] }
          : undefined,
      },
    ],
  }
})
</script>

<template>
  <div class="grade">
    <div class="grade g4">
      <div class="cartao kpi">
        <div class="rotulo">Geladeiras fora de +2 a +8 °C</div>
        <div class="valor" :style="{ color: kpis.foraFaixa ? 'var(--critico)' : 'var(--ok)' }">
          {{ kpis.foraFaixa }} <small class="suave">/ {{ kpis.total }}</small>
        </div>
      </div>
      <div class="cartao kpi">
        <div class="rotulo">Alertas abertos</div>
        <div class="valor">{{ kpis.alertas }}</div>
        <div class="sub">{{ kpis.criticos }} críticos</div>
      </div>
      <div class="cartao kpi">
        <div class="rotulo">Pior saúde de compressor (IA)</div>
        <div class="valor">{{ kpis.piorSaude === null ? '—' : kpis.piorSaude.toFixed(0) }}</div>
        <div class="sub">índice de 0 a 100</div>
      </div>
      <div class="cartao kpi">
        <div class="rotulo">Telemetria recebida</div>
        <div class="valor">{{ kpis.taxa.toFixed(1) }}</div>
        <div class="sub">mensagens/s pelo WebSocket</div>
      </div>
    </div>

    <p v-if="ultimoComando" :class="ultimoComando.erro ? 'erro' : 'suave'">{{ ultimoComando.texto }}</p>

    <div class="grade auto">
      <div v-for="s in salas" :key="s.ubs" class="cartao sala">
        <div class="linha entre">
          <h2>{{ NOMES_UBS[s.ubs] ?? s.ubs }} · sala de vacinas</h2>
          <span class="suave mono">{{ hora(s.hora) }} (simulado)</span>
        </div>
        <div class="linha medidas">
          <div><small class="suave">Temp. sala</small><b class="mono">{{ fmt(s.tamb) }} °C</b></div>
          <div><small class="suave">Luminosidade</small><b class="mono">{{ fmt(s.lux, 0) }} lux</b></div>
          <div>
            <small class="suave">Luz da sala</small>
            <span class="pilula" :class="s.luzEstado === 'ligado' ? 'atencao' : ''">{{ s.luzEstado ?? '—' }}</span>
          </div>
        </div>
        <div v-if="s.luz && pode('operador')" class="linha">
          <button class="btn-sec" @click="comandar(s.luz!.id, 'ligar')">Acender luz</button>
          <button class="btn-sec" @click="comandar(s.luz!.id, 'desligar')">Apagar luz</button>
        </div>
      </div>
    </div>

    <div class="grade auto">
      <div v-for="g in geladeiras" :key="g.gid" class="cartao geladeira" :style="{ borderTop: `4px solid ${COR_STATUS[g.status]}` }">
        <div class="linha entre">
          <h2>{{ nomeGeladeira(g.gid) }}</h2>
          <span class="pilula" :class="g.status">{{ ROTULO_STATUS[g.status] }}</span>
        </div>
        <div class="temp mono" :style="{ color: typeof g.temp === 'number' && (g.temp < 2 || g.temp > 8) ? 'var(--critico)' : 'inherit' }">
          {{ fmt(g.temp) }} °C
        </div>
        <div class="linha medidas">
          <div><small class="suave">Umidade</small><b class="mono">{{ fmt(g.umid, 0) }}%</b></div>
          <div><small class="suave">Porta</small><b>{{ g.porta ? 'Aberta' : 'Fechada' }}</b></div>
          <div>
            <small class="suave">Alarme (regra)</small>
            <span class="pilula" :class="g.alarme === 'ligado' ? 'critico' : 'normal'">{{ g.alarme ?? '—' }}</span>
          </div>
        </div>
        <div class="linha medidas">
          <div><small class="suave">Vibração</small><b class="mono">{{ fmt(g.comp?.vibracao, 2) }} mm/s</b></div>
          <div><small class="suave">Corrente</small><b class="mono">{{ fmt(g.comp?.corrente, 2) }} A</b></div>
          <div><small class="suave">Temp. compr.</small><b class="mono">{{ fmt(g.comp?.temp_compressor) }} °C</b></div>
        </div>
        <div class="linha medidas">
          <div>
            <small class="suave">Saúde (IA)</small>
            <b class="mono">{{ g.prev?.status === 'ok' ? fmt(g.prev.saude, 0) : g.prev?.status ?? '—' }}</b>
          </div>
          <div>
            <small class="suave">Vida útil restante</small>
            <b class="mono">{{ g.prev?.status === 'ok' ? `${fmt(g.prev.rul_h, 0)} h` : '—' }}</b>
          </div>
          <div><small class="suave">Compressor</small><b>{{ g.comp?.estado ?? '—' }}</b></div>
        </div>
        <MiniGrafico :pontos="g.hist" :faixa="[2, 8]" :altura="80" />
        <div class="linha entre">
          <span class="suave">Resfriamento de emergência: <b>{{ g.resfrEstado ?? '—' }}</b></span>
          <div v-if="g.resfr && pode('operador')" class="linha">
            <button class="btn-sec" @click="comandar(g.resfr!.id, g.resfrEstado === 'ligado' ? 'desligar' : 'ligar')">
              {{ g.resfrEstado === 'ligado' ? 'Desligar' : 'Ligar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="grade g2">
      <div class="cartao">
        <div class="linha entre">
          <h2>Histórico (InfluxDB)</h2>
          <div class="linha">
            <select v-model="selecionado">
              <option v-for="d in dispositivos.filter((x) => x.categoria !== 'atuador')" :key="d.id" :value="d.id">{{ d.id }}</option>
            </select>
            <select v-if="camposSel.length > 1" v-model="campo">
              <option v-for="c in camposSel" :key="c" :value="c">{{ c }}</option>
            </select>
            <select v-model="periodo">
              <option v-for="p in ['15m', '1h', '6h', '24h', '7d']" :key="p">{{ p }}</option>
            </select>
          </div>
        </div>
        <p v-if="erroHist" class="erro">{{ erroHist }}</p>
        <VChart :option="opcaoHist" autoresize style="height: 280px" />
        <div class="linha suave mono">
          <span>mín {{ fmt(estat.min, 2) }}</span><span>máx {{ fmt(estat.max, 2) }}</span>
          <span>média {{ fmt(estat.mean, 2) }}</span><span>{{ estat.count ?? 0 }} leituras</span>
        </div>
      </div>
      <div class="cartao">
        <h2>Alertas abertos</h2>
        <div v-if="!alertasAbertos.length" class="vazio">Nenhum alerta aberto.</div>
        <table v-else class="tabela">
          <thead>
            <tr><th>Quando</th><th>Dispositivo</th><th>Severidade</th><th>Mensagem</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in alertasAbertos.slice(0, 12)" :key="a.id">
              <td class="mono">{{ new Date(a.aberto_em).toLocaleTimeString() }}</td>
              <td class="mono">{{ a.dispositivo }}</td>
              <td><span class="pilula" :class="a.severidade">{{ a.severidade }}</span></td>
              <td>{{ a.mensagem }} <small class="suave">({{ a.origem }})</small></td>
            </tr>
          </tbody>
        </table>
        <p class="suave" style="font-size: 0.8rem">
          {{ NOMES_GRANDEZA.alarme }} é acionado automaticamente pela regra de negócio; os alertas preditivos vêm da IA.
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.temp {
  font-size: 2.2rem;
  font-weight: 700;
  margin: 6px 0;
}
.medidas {
  gap: 18px;
  margin: 6px 0;
}
.medidas > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 80px;
}
.medidas small {
  font-size: 0.74rem;
}
.geladeira {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
select {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 5px 8px;
  background: white;
}
</style>
