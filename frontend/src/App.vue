<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import IndicadorTemperatura from './components/IndicadorTemperatura.vue'
import GraficoHistorico from './components/GraficoHistorico.vue'
import { api } from './services/api'
import type { FaixaSegura, Geladeira, Historico, LeituraAtual, Periodo } from './types'

const ATUALIZACAO_MS = 5000
const SEM_SINAL_MS = 60_000

const periodos: { valor: Periodo; rotulo: string }[] = [
  { valor: '15m', rotulo: '15 min' },
  { valor: '1h', rotulo: '1 h' },
  { valor: '6h', rotulo: '6 h' },
  { valor: '24h', rotulo: '24 h' },
  { valor: '7d', rotulo: '7 dias' },
]

const faixa = ref<FaixaSegura>({ temp_min: 2, temp_max: 8 })
const geladeiras = ref<Geladeira[]>([])
const selecionada = ref<string>('') // "ubs/geladeira"
const atual = ref<LeituraAtual | null>(null)
const historico = ref<Historico | null>(null)
const periodo = ref<Periodo>('1h')
const erro = ref<string | null>(null)
const agora = ref(Date.now())

const alvo = computed(() => {
  const [ubs, geladeira] = selecionada.value.split('/')
  return ubs && geladeira ? { ubs, geladeira } : null
})

const semSinal = computed(
  () => !!atual.value && agora.value - new Date(atual.value.horario).getTime() > SEM_SINAL_MS,
)

const situacao = computed(() => {
  if (!atual.value) return { classe: 'neutro', titulo: 'Aguardando leituras', texto: 'Nenhum dado recebido ainda.' }
  if (semSinal.value)
    return { classe: 'neutro', titulo: 'Sem sinal do sensor', texto: 'A última leitura tem mais de 1 minuto.' }
  const { temp_min, temp_max } = faixa.value
  if (atual.value.status === 'acima')
    return { classe: 'alerta', titulo: 'Temperatura ACIMA da faixa', texto: `Verifique a porta e a geladeira (máx. ${temp_max} °C).` }
  if (atual.value.status === 'abaixo')
    return { classe: 'frio', titulo: 'Temperatura ABAIXO da faixa', texto: `Risco de congelamento das vacinas (mín. ${temp_min} °C).` }
  return { classe: 'ok', titulo: 'Conservação adequada', texto: `Dentro da faixa segura de ${temp_min} °C a ${temp_max} °C.` }
})

const horarioUltima = computed(() => {
  if (!atual.value) return '--'
  const segundos = Math.max(0, Math.round((agora.value - new Date(atual.value.horario).getTime()) / 1000))
  const hora = new Date(atual.value.horario).toLocaleTimeString('pt-BR')
  return segundos < 60 ? `${hora} (há ${segundos} s)` : hora
})

function fmt(v: number | null | undefined, casas = 1) {
  return v === null || v === undefined ? '--' : v.toFixed(casas).replace('.', ',')
}

async function carregarGeladeiras() {
  geladeiras.value = await api.geladeiras()
  const primeira = geladeiras.value[0]
  if (!selecionada.value && primeira) {
    selecionada.value = `${primeira.ubs}/${primeira.geladeira}`
  }
}

async function carregarAtual() {
  if (!alvo.value) return
  atual.value = await api.leituraAtual(alvo.value.ubs, alvo.value.geladeira)
}

async function carregarHistorico() {
  if (!alvo.value) return
  historico.value = await api.historico(alvo.value.ubs, alvo.value.geladeira, periodo.value)
}

async function atualizarTudo() {
  try {
    await carregarGeladeiras()
    await Promise.all([carregarAtual(), carregarHistorico()])
    erro.value = null
  } catch (e) {
    erro.value = 'Não foi possível falar com o backend. Ele está rodando na porta 8000?'
    console.error(e)
  }
}

watch([selecionada, periodo], () => {
  atual.value = null
  historico.value = null
  atualizarTudo()
})

let temporizador: number | undefined
let relogio: number | undefined

onMounted(async () => {
  try {
    faixa.value = await api.faixaSegura()
  } catch {
    /* usa a faixa padrão */
  }
  await atualizarTudo()
  temporizador = window.setInterval(atualizarTudo, ATUALIZACAO_MS)
  relogio = window.setInterval(() => (agora.value = Date.now()), 1000)
})

onUnmounted(() => {
  window.clearInterval(temporizador)
  window.clearInterval(relogio)
})
</script>

<template>
  <header class="topo">
    <div class="marca">
      <img src="/favicon.svg" alt="" width="36" height="36" />
      <div>
        <h1>VacinaSegura</h1>
        <p>Monitoramento da temperatura das geladeiras de vacinas</p>
      </div>
    </div>
    <label class="seletor">
      <span>Geladeira</span>
      <select v-model="selecionada" :disabled="!geladeiras.length">
        <option v-if="!geladeiras.length" value="">Nenhuma geladeira enviou dados</option>
        <option v-for="g in geladeiras" :key="`${g.ubs}/${g.geladeira}`" :value="`${g.ubs}/${g.geladeira}`">
          {{ g.ubs.toUpperCase() }} · {{ g.geladeira.toUpperCase() }}
        </option>
      </select>
    </label>
  </header>

  <main class="conteudo">
    <p v-if="erro" class="erro">{{ erro }}</p>

    <section class="situacao" :class="situacao.classe">
      <span class="ponto" />
      <div>
        <strong>{{ situacao.titulo }}</strong>
        <span>{{ situacao.texto }}</span>
      </div>
    </section>

    <div class="grade">
      <section class="cartao">
        <h2>Temperatura atual</h2>
        <IndicadorTemperatura :temperatura="atual?.temperatura ?? null" :faixa="faixa" />
        <dl class="detalhes">
          <div>
            <dt>Umidade</dt>
            <dd>{{ fmt(atual?.umidade) }} %</dd>
          </div>
          <div>
            <dt>Última leitura</dt>
            <dd>{{ horarioUltima }}</dd>
          </div>
        </dl>
      </section>

      <section class="cartao historico">
        <div class="cabecalho-cartao">
          <h2>Histórico</h2>
          <div class="periodos" role="group" aria-label="Período">
            <button
              v-for="p in periodos"
              :key="p.valor"
              :class="{ ativo: periodo === p.valor }"
              @click="periodo = p.valor"
            >
              {{ p.rotulo }}
            </button>
          </div>
        </div>
        <GraficoHistorico :pontos="historico?.pontos ?? []" :faixa="faixa" />
      </section>
    </div>

    <section class="estatisticas">
      <div class="cartao estat">
        <span>Mínima</span>
        <strong>{{ fmt(historico?.estatisticas.minima) }} °C</strong>
      </div>
      <div class="cartao estat">
        <span>Média</span>
        <strong>{{ fmt(historico?.estatisticas.media) }} °C</strong>
      </div>
      <div class="cartao estat">
        <span>Máxima</span>
        <strong>{{ fmt(historico?.estatisticas.maxima) }} °C</strong>
      </div>
      <div class="cartao estat" :class="{ destaque: (historico?.estatisticas.leituras_fora_da_faixa ?? 0) > 0 }">
        <span>Leituras fora da faixa</span>
        <strong>
          {{ historico?.estatisticas.leituras_fora_da_faixa ?? 0 }}
          <small>de {{ historico?.estatisticas.total_leituras ?? 0 }}</small>
        </strong>
      </div>
    </section>
  </main>
</template>

<style scoped>
.topo {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding: 18px clamp(16px, 4vw, 40px);
  background: var(--cartao);
  border-bottom: 1px solid var(--borda);
}
.marca {
  display: flex;
  gap: 12px;
  align-items: center;
}
.marca h1 {
  margin: 0;
  font-size: 1.25rem;
  letter-spacing: -0.01em;
}
.marca p {
  margin: 2px 0 0;
  font-size: 0.85rem;
  color: var(--texto-suave);
}
.seletor {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.85rem;
  color: var(--texto-suave);
}
.seletor select {
  padding: 8px 12px;
  border: 1px solid var(--borda);
  border-radius: 10px;
  background: var(--cartao);
  font-weight: 600;
}

.conteudo {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px clamp(16px, 4vw, 40px) 48px;
  display: grid;
  gap: 20px;
}

.erro {
  margin: 0;
  padding: 12px 16px;
  border-radius: var(--raio);
  background: var(--alerta-fundo);
  color: var(--alerta);
  font-weight: 500;
}

.situacao {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 16px 20px;
  border-radius: var(--raio);
  border: 1px solid transparent;
}
.situacao div {
  display: grid;
  gap: 2px;
}
.situacao span:not(.ponto) {
  font-size: 0.9rem;
}
.ponto {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
  background: currentColor;
  box-shadow: 0 0 0 5px color-mix(in srgb, currentColor 18%, transparent);
}
.situacao.ok { background: var(--ok-fundo); color: var(--ok); }
.situacao.alerta { background: var(--alerta-fundo); color: var(--alerta); }
.situacao.alerta .ponto { animation: pulsar 1.2s ease-in-out infinite; }
.situacao.frio { background: var(--frio-fundo); color: var(--frio); }
.situacao.neutro { background: var(--cartao); color: var(--texto-suave); border-color: var(--borda); }

@keyframes pulsar {
  50% { box-shadow: 0 0 0 10px color-mix(in srgb, currentColor 5%, transparent); }
}

.grade {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 2.2fr;
  gap: 20px;
}
@media (max-width: 860px) {
  .grade { grid-template-columns: 1fr; }
}

.cartao {
  background: var(--cartao);
  border: 1px solid var(--borda);
  border-radius: var(--raio);
  box-shadow: var(--sombra);
  padding: 18px 20px;
  min-width: 0;
}
.cartao h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
}

.detalhes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 0;
  padding-top: 12px;
  border-top: 1px solid var(--borda);
}
.detalhes dt {
  font-size: 0.75rem;
  color: var(--texto-suave);
}
.detalhes dd {
  margin: 2px 0 0;
  font-family: var(--mono);
  font-size: 0.9rem;
}

.cabecalho-cartao {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.periodos {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: var(--fundo);
  border-radius: 10px;
}
.periodos button {
  border: 0;
  background: transparent;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.8rem;
  color: var(--texto-suave);
  cursor: pointer;
}
.periodos button.ativo {
  background: var(--cartao);
  color: var(--primaria);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(20, 35, 46, 0.12);
}

.estatisticas {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}
@media (max-width: 860px) {
  .estatisticas { grid-template-columns: repeat(2, 1fr); }
}
.estat {
  display: grid;
  gap: 6px;
}
.estat span {
  font-size: 0.8rem;
  color: var(--texto-suave);
}
.estat strong {
  font-family: var(--mono);
  font-size: 1.5rem;
}
.estat small {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--texto-suave);
}
.estat.destaque {
  border-color: color-mix(in srgb, var(--alerta) 40%, transparent);
  background: var(--alerta-fundo);
}
.estat.destaque strong {
  color: var(--alerta);
}
</style>
