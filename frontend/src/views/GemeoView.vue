<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MiniGrafico from '../components/MiniGrafico.vue'
import { comandar, fmt, NOMES_GRANDEZA, ultimoComando } from '../services/comandos'
import { pode } from '../stores/sessao'
import {
  alertasAbertos,
  COR_STATUS,
  dados,
  ROTULO_STATUS,
  semDadosGlobal,
  statusDispositivo,
  versao,
  versaoCadastro,
} from '../stores/tempoReal'
import { CenaGemeo } from '../three/cena'

const alvo = ref<HTMLDivElement>()
const selecionado = ref<string | null>(null)
let cena: CenaGemeo | null = null

onMounted(() => {
  cena = new CenaGemeo(alvo.value!, (id) => (selecionado.value = id))
  if (dados.dispositivos.length) cena.montar(dados.dispositivos)
})
watch(versaoCadastro, () => cena?.montar(dados.dispositivos))
onBeforeUnmount(() => cena?.destruir())

const semDados = computed(() => {
  void versao.value
  return semDadosGlobal()
})

const info = computed(() => {
  void versao.value
  const id = selecionado.value
  if (!id) return null
  const d = dados.dispositivos.find((x) => x.id === id)
  if (!d) return null
  const leitura = dados.leituras.get(id)
  const compId = d.geladeira ? dados.dispositivos.find((x) => x.geladeira === d.geladeira && x.grandeza === 'compressor')?.id : undefined
  const prev = compId ? dados.previsoes.get(compId) : undefined
  return {
    d,
    status: statusDispositivo(d),
    leitura: leitura?.conteudo,
    idade: leitura ? Math.round((Date.now() - leitura.recebidoEm) / 1000) : null,
    hist: dados.historico.get(id) ?? [],
    histSaude: compId ? dados.historico.get(`${compId}#saude`) ?? [] : [],
    prev,
    alertas: alertasAbertos.value.filter((a) => a.dispositivo === id || a.dispositivo === compId),
  }
})

const modo = ref('rolamento')
const horas = ref(24)
</script>

<template>
  <div class="gemeo">
    <div ref="alvo" class="tela3d">
      <div v-if="semDados" class="sem-dados">
        <strong>Sem dados em tempo real</strong>
        <span>A cena está parada: nenhuma mensagem chegou pelo WebSocket nos últimos 20 s.</span>
      </div>
      <div class="legenda">
        <span v-for="s in ['normal', 'atencao', 'critico', 'sem_dados'] as const" :key="s">
          <i :style="{ background: COR_STATUS[s] }"></i>{{ ROTULO_STATUS[s] }}
        </span>
      </div>
      <div class="dica">Arraste para girar · role para aproximar · clique em um item</div>
    </div>

    <aside class="cartao painel">
      <template v-if="info">
        <div class="linha entre">
          <h2>{{ NOMES_GRANDEZA[info.d.grandeza] ?? info.d.grandeza }}</h2>
          <span class="pilula" :class="info.status">{{ ROTULO_STATUS[info.status] }}</span>
        </div>
        <p class="suave mono id">{{ info.d.id }}</p>
        <p class="suave">{{ info.d.nome }}</p>

        <div v-if="info.leitura" class="leitura">
          <template v-if="info.d.grandeza === 'compressor'">
            <div><small>Vibração</small><b class="mono">{{ fmt(info.leitura.vibracao, 2) }} mm/s</b></div>
            <div><small>Corrente</small><b class="mono">{{ fmt(info.leitura.corrente, 2) }} A</b></div>
            <div><small>Temp. compressor</small><b class="mono">{{ fmt(info.leitura.temp_compressor) }} °C</b></div>
            <div><small>Estado</small><b>{{ info.leitura.estado }}</b></div>
          </template>
          <template v-else-if="info.d.categoria === 'atuador'">
            <div><small>Estado</small><b>{{ info.leitura.estado }}</b></div>
            <div><small>Controle</small><b>{{ info.d.controle === 'auto' ? 'Regra de negócio' : 'Aplicação Web' }}</b></div>
          </template>
          <template v-else-if="info.d.grandeza === 'porta'">
            <div><small>Porta</small><b>{{ info.leitura.valor ? 'Aberta' : 'Fechada' }}</b></div>
          </template>
          <template v-else>
            <div><small>Última leitura</small><b class="mono">{{ fmt(info.leitura.valor, 2) }} {{ info.d.unidade }}</b></div>
            <div v-if="info.d.faixa_max !== null">
              <small>Faixa normal</small><b class="mono">{{ info.d.faixa_min }} a {{ info.d.faixa_max }}</b>
            </div>
          </template>
          <div><small>Recebida há</small><b class="mono">{{ info.idade }} s</b></div>
        </div>
        <p v-else class="suave">Sem leitura recebida.</p>

        <MiniGrafico v-if="info.hist.length > 1" :pontos="info.hist" :altura="110"
          :faixa="info.d.faixa_max !== null && info.d.faixa_min !== null && info.d.faixa_max > info.d.faixa_min ? [info.d.faixa_min, info.d.faixa_max] : undefined" />

        <div v-if="info.prev" class="ia">
          <h3>Saúde prevista pela IA (compressor)</h3>
          <template v-if="info.prev.status === 'ok'">
            <div class="leitura">
              <div><small>Índice de saúde</small><b class="mono">{{ fmt(info.prev.saude, 0) }} / 100</b></div>
              <div><small>Vida útil restante</small><b class="mono">{{ fmt(info.prev.rul_h, 0) }} h</b></div>
              <div><small>Tendência</small><b class="mono">{{ fmt(info.prev.tendencia, 1) }} pts/h</b></div>
              <div><small>Modelo</small><b class="mono">v{{ info.prev.versao_modelo }}</b></div>
            </div>
            <MiniGrafico v-if="info.histSaude.length > 1" :pontos="info.histSaude" :min="0" :max="100" cor="#7c3aed" :altura="80" />
          </template>
          <p v-else class="suave">Previsão: {{ info.prev.status === 'aquecendo' ? `acumulando histórico (${info.prev.leituras}/${info.prev.necessarias})` : 'nenhum modelo treinado' }}</p>
        </div>

        <div v-for="a in info.alertas" :key="a.id" class="alerta" :class="a.severidade">{{ a.mensagem }}</div>

        <div v-if="pode('operador')" class="comandos">
          <template v-if="info.d.categoria === 'atuador' && info.d.controle === 'manual'">
            <h3>Comandos</h3>
            <div class="linha">
              <button class="btn" @click="comandar(info.d.id, 'ligar')">Ligar</button>
              <button class="btn-sec" @click="comandar(info.d.id, 'desligar')">Desligar</button>
            </div>
          </template>
          <p v-else-if="info.d.grandeza === 'alarme'" class="suave">O alarme é acionado automaticamente pela regra de negócio (temperatura fora de +2 a +8 °C).</p>
          <template v-if="info.d.grandeza === 'porta'">
            <h3>Simulação</h3>
            <button class="btn-sec" @click="comandar(info.d.id, 'abrir_porta', { minutos: 30 })">Abrir a porta por 30 min (simulados)</button>
          </template>
          <template v-if="info.d.grandeza === 'compressor'">
            <h3>Simulação de falha</h3>
            <div class="linha">
              <select v-model="modo">
                <option v-for="m in ['rolamento', 'entupimento', 'superaquecimento', 'desbalanceamento']" :key="m">{{ m }}</option>
              </select>
              <input v-model.number="horas" type="number" min="1" max="500" style="width: 70px" /> h
            </div>
            <div class="linha">
              <button class="btn-perigo" @click="comandar(info.d.id, 'injetar_falha', { modo, horas })">Injetar falha</button>
              <button class="btn-sec" @click="comandar(info.d.id, 'reparar')">Reparar</button>
            </div>
          </template>
          <p v-if="ultimoComando" :class="ultimoComando.erro ? 'erro' : 'suave'">{{ ultimoComando.texto }}</p>
        </div>
      </template>
      <div v-else class="vazio">
        <p>Clique em um sensor, atuador ou compressor na cena para ver os detalhes.</p>
        <p class="suave">
          A cena é atualizada só pelos dados que chegam pelo WebSocket. A janela acompanha a luminosidade medida (dia/noite),
          o termômetro da parede acompanha a temperatura da sala e a névoa fria mostra a temperatura interna.
        </p>
        <div v-if="pode('operador')" class="linha" style="justify-content: center">
          <button class="btn-sec" @click="comandar('simulador', 'pausar', { segundos: 60 })">Pausar simulador 60 s</button>
          <button class="btn-sec" @click="comandar('simulador', 'retomar')">Retomar</button>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.gemeo {
  display: grid;
  grid-template-columns: 1fr 330px;
  gap: 14px;
  height: calc(100vh - 110px);
  min-height: 520px;
}
.tela3d {
  position: relative;
  border-radius: var(--raio);
  overflow: hidden;
  border: 1px solid var(--borda);
  background: #dfe8ee;
}
.sem-dados {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: rgba(15, 37, 48, 0.55);
  color: white;
  z-index: 2;
  text-align: center;
  padding: 20px;
}
.sem-dados strong {
  font-size: 1.3rem;
}
.legenda {
  position: absolute;
  left: 12px;
  bottom: 12px;
  display: flex;
  gap: 12px;
  background: rgba(255, 255, 255, 0.85);
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.8rem;
}
.legenda i {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 4px;
}
.dica {
  position: absolute;
  right: 12px;
  top: 10px;
  font-size: 0.75rem;
  color: #334155;
  background: rgba(255, 255, 255, 0.7);
  padding: 3px 8px;
  border-radius: 6px;
}
.painel {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.id {
  margin: -4px 0 0;
  font-size: 0.8rem;
}
.leitura {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.leitura div {
  display: flex;
  flex-direction: column;
}
.leitura small {
  color: var(--texto-suave);
  font-size: 0.74rem;
}
.ia {
  border-top: 1px solid var(--borda);
  padding-top: 8px;
}
.ia h3,
.comandos h3 {
  margin-bottom: 6px;
}
.alerta {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
  background: #fef9c3;
}
.alerta.critico {
  background: #fee2e2;
}
.comandos {
  border-top: 1px solid var(--borda);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
select,
input {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 5px 8px;
}
@media (max-width: 900px) {
  .gemeo {
    grid-template-columns: 1fr;
    height: auto;
  }
  .tela3d {
    height: 60vh;
  }
}
</style>
