<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import JobsLista from '../components/JobsLista.vue'
import VChart from '../echarts'
import { enviar, get } from '../services/api'
import { fmt } from '../services/comandos'
import { pode } from '../stores/sessao'

interface Metricas {
  mae: number
  rmse: number
  r2: number
}
interface ModeloAlvo {
  alvo: string
  algoritmo: string
  candidatos: Record<string, { mae_validacao: number }>
  teste: Metricas
  base_media: Metricas
  vence_base: boolean
  importancia: { feature: string; importancia: number }[]
  previsto_vs_real: [number, number][]
}
interface Modelo {
  versao: number
  criado_em: string
  job_id: string
  metricas: {
    divisao: Record<string, number | string>
    dados: { leituras?: number; equipamentos?: number; equipamentos_com_falha?: number }
    modelos: Record<string, ModeloAlvo>
    segundos: number
  }
}

const modelos = ref<Modelo[]>([])
const emUso = ref<number | null>(null)
const sel = ref<number | null>(null)
const erro = ref('')
const atualizar = ref(0)

async function carregar() {
  const r = await get<{ modelos: Modelo[]; versao_em_uso: number | null }>('/api/modelos')
  modelos.value = r.modelos
  emUso.value = r.versao_em_uso
  if (sel.value === null && r.modelos.length) sel.value = r.modelos[0].versao
}
onMounted(carregar)

async function treinar() {
  erro.value = ''
  try {
    await enviar('POST', '/api/treino', { semente: 42 })
    atualizar.value++
  } catch (e) {
    erro.value = (e as Error).message
  }
}

const modelo = computed(() => modelos.value.find((m) => m.versao === sel.value))
const NOMES: Record<string, string> = { rul_h: 'Vida útil restante (horas)', saude: 'Índice de saúde (0–100)' }

function dispersao(m: ModeloAlvo) {
  const max = Math.max(...m.previsto_vs_real.flat(), 1)
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 36 },
    tooltip: { formatter: (p: { value: number[] }) => `real ${p.value[0].toFixed(1)} · previsto ${p.value[1].toFixed(1)}` },
    xAxis: { type: 'value', name: 'real', nameLocation: 'middle', nameGap: 22, min: 0, max: Math.ceil(max) },
    yAxis: { type: 'value', name: 'previsto', min: 0, max: Math.ceil(max) },
    series: [
      { type: 'scatter', symbolSize: 4, data: m.previsto_vs_real, itemStyle: { color: '#0e7490', opacity: 0.5 } },
      { type: 'line', data: [[0, 0], [max, max]], showSymbol: false, lineStyle: { type: 'dashed', color: '#94a3b8' } },
    ],
  }
}

function importancia(m: ModeloAlvo) {
  const top = m.importancia.slice(0, 10).reverse()
  return {
    animation: false,
    grid: { left: 150, right: 16, top: 8, bottom: 24 },
    tooltip: {},
    xAxis: { type: 'value', name: 'aumento do MAE', nameLocation: 'middle', nameGap: 20 },
    yAxis: { type: 'category', data: top.map((i) => i.feature), axisLabel: { fontSize: 10 } },
    series: [{ type: 'bar', data: top.map((i) => +i.importancia.toFixed(3)), itemStyle: { color: '#7c3aed' } }],
  }
}
</script>

<template>
  <div class="grade">
    <div class="cartao linha entre">
      <div>
        <h2>Modelos de regressão</h2>
        <p class="suave nota">
          Treinados com o último conjunto sintético. Divisão treino/validação/teste <b>por equipamento</b>; features calculadas pelo
          mesmo código usado na inferência ao vivo, olhando só para o passado. O modelo novo entra em uso sem reiniciar o serviço.
        </p>
      </div>
      <div class="linha">
        <span class="pilula">Versão em uso na inferência: {{ emUso ? `v${emUso}` : '—' }}</span>
        <select v-model="sel">
          <option v-for="m in modelos" :key="m.versao" :value="m.versao">v{{ m.versao }} · {{ new Date(m.criado_em).toLocaleString() }}</option>
        </select>
        <button class="btn" :disabled="!pode('administrador')" @click="treinar">Treinar novo modelo</button>
      </div>
    </div>
    <p v-if="erro" class="erro">{{ erro }}</p>

    <div v-if="modelo" class="cartao linha resumo">
      <span><small class="suave">Leituras sintéticas</small><b class="mono">{{ modelo.metricas.dados?.leituras?.toLocaleString('pt-BR') ?? '—' }}</b></span>
      <span><small class="suave">Equipamentos</small><b class="mono">{{ modelo.metricas.dados?.equipamentos ?? '—' }}</b></span>
      <span><small class="suave">Treino / validação / teste</small><b class="mono">{{ modelo.metricas.divisao.treino }} / {{ modelo.metricas.divisao.validacao }} / {{ modelo.metricas.divisao.teste }} equip.</b></span>
      <span><small class="suave">Linhas de treino</small><b class="mono">{{ Number(modelo.metricas.divisao.linhas_treino).toLocaleString('pt-BR') }}</b></span>
      <span><small class="suave">Tempo de treino</small><b class="mono">{{ modelo.metricas.segundos }} s</b></span>
    </div>

    <div v-if="modelo" class="grade g2">
      <div v-for="(m, alvo) in modelo.metricas.modelos" :key="alvo" class="cartao">
        <div class="linha entre">
          <h2>{{ NOMES[alvo] ?? alvo }}</h2>
          <span class="pilula" :class="m.vence_base ? 'normal' : 'critico'">{{ m.vence_base ? 'vence a base' : 'NÃO vence a base' }}</span>
        </div>
        <p class="suave">Algoritmo escolhido na validação: <b>{{ m.algoritmo }}</b>
          <span v-for="(c, nome) in m.candidatos" :key="nome"> · {{ nome }} MAE val. {{ fmt(c.mae_validacao, 2) }}</span>
        </p>
        <table class="tabela">
          <thead><tr><th>Conjunto de teste</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead>
          <tbody>
            <tr><td>Modelo</td><td class="mono">{{ fmt(m.teste.mae, 2) }}</td><td class="mono">{{ fmt(m.teste.rmse, 2) }}</td><td class="mono">{{ fmt(m.teste.r2, 3) }}</td></tr>
            <tr class="suave"><td>Base (prever sempre a média)</td><td class="mono">{{ fmt(m.base_media.mae, 2) }}</td><td class="mono">{{ fmt(m.base_media.rmse, 2) }}</td><td class="mono">{{ fmt(m.base_media.r2, 3) }}</td></tr>
          </tbody>
        </table>
        <h3 class="sub">Previsto × real (amostra do teste)</h3>
        <VChart :option="dispersao(m)" autoresize style="height: 240px" />
        <h3 class="sub">Importância dos atributos (permutação)</h3>
        <VChart :option="importancia(m)" autoresize style="height: 260px" />
      </div>
    </div>
    <div v-else class="cartao vazio">Nenhum modelo treinado ainda. Gere dados no Laboratório e clique em “Treinar novo modelo”.</div>

    <div class="cartao rolagem">
      <h2>Jobs de treino</h2>
      <JobsLista tipo="treino" :atualizar="atualizar" @concluido="carregar" />
    </div>
  </div>
</template>

<style scoped>
.nota {
  font-size: 0.85rem;
  max-width: 720px;
}
.resumo {
  gap: 28px;
}
.resumo span {
  display: flex;
  flex-direction: column;
}
.sub {
  margin-top: 12px;
}
select {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 6px 8px;
}
</style>
