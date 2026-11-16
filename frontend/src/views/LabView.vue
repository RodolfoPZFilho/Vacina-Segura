<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import JobsLista from '../components/JobsLista.vue'
import { enviar } from '../services/api'
import { pode } from '../stores/sessao'

const p = reactive({
  equipamentos: 60,
  dias: 60,
  sensores_temperatura: 1,
  sensores_umidade: 1,
  pct_falha: 50,
  modos_falha: ['rolamento', 'entupimento', 'superaquecimento', 'desbalanceamento'],
  pct_falha_sensor: 10,
  modos_sensor: ['deriva_sensor', 'travamento_sensor'],
  ruido: 1.0,
  pct_faltantes: 1.0,
  pct_outliers: 0.3,
  semente: 42,
})
const MODOS = ['rolamento', 'entupimento', 'superaquecimento', 'desbalanceamento']
const MODOS_SENSOR = ['deriva_sensor', 'travamento_sensor']
const previa = ref<{ leituras: number; ok: boolean; erro?: string } | null>(null)
const msg = ref('')
const erro = ref('')
const atualizar = ref(0)

let t = 0
watch(
  p,
  () => {
    clearTimeout(t)
    t = window.setTimeout(async () => {
      try {
        previa.value = await enviar('POST', '/api/lab/previa', p)
      } catch {
        previa.value = null
      }
    }, 300)
  },
  { deep: true, immediate: true },
)

async function gerar() {
  erro.value = ''
  msg.value = ''
  try {
    const r = await enviar<{ job_id: string; leituras_previstas: number }>('POST', '/api/lab/geracao', p)
    msg.value = `Job ${r.job_id} enviado para a fila q.jobs.geracao (${r.leituras_previstas.toLocaleString('pt-BR')} leituras).`
    atualizar.value++
  } catch (e) {
    erro.value = (e as Error).message
  }
}
</script>

<template>
  <div class="grade">
    <div class="cartao">
      <h2>Gerar dados sintéticos</h2>
      <p class="suave nota">
        Simula a vida inteira de muitas geladeiras com a mesma física do simulador ao vivo. A degradação do compressor é
        progressiva (vibração, corrente e temperatura sobem aos poucos), com ciclo diário, ruído, sobreposição entre máquinas
        saudáveis e doentes, leituras faltantes e outliers. Os rótulos (horas até falhar, índice de saúde) ficam só no arquivo de
        treino. O job roda em segundo plano pela fila do RabbitMQ; uma amostra vai para o bucket <code>lab</code> do InfluxDB.
      </p>
      <form class="form" @submit.prevent="gerar">
        <label class="campo">Equipamentos (geladeiras) <input v-model.number="p.equipamentos" type="number" min="2" max="2000" /></label>
        <label class="campo">Período simulado (dias) <input v-model.number="p.dias" type="number" min="2" max="365" /></label>
        <label class="campo">Sensores de temperatura / geladeira <input v-model.number="p.sensores_temperatura" type="number" min="1" max="4" /></label>
        <label class="campo">Sensores de umidade / geladeira <input v-model.number="p.sensores_umidade" type="number" min="0" max="4" /></label>
        <label class="campo">% de equipamentos que falham <input v-model.number="p.pct_falha" type="number" min="0" max="100" /></label>
        <label class="campo">% com falha de sensor <input v-model.number="p.pct_falha_sensor" type="number" min="0" max="100" /></label>
        <label class="campo">Nível de ruído (×) <input v-model.number="p.ruido" type="number" step="0.1" min="0" max="5" /></label>
        <label class="campo">% leituras faltantes <input v-model.number="p.pct_faltantes" type="number" step="0.1" min="0" max="30" /></label>
        <label class="campo">% outliers <input v-model.number="p.pct_outliers" type="number" step="0.1" min="0" max="10" /></label>
        <label class="campo">Semente aleatória <input v-model.number="p.semente" type="number" min="0" /></label>
        <fieldset class="modos">
          <legend>Modos de falha do compressor</legend>
          <label v-for="m in MODOS" :key="m"><input v-model="p.modos_falha" type="checkbox" :value="m" /> {{ m }}</label>
        </fieldset>
        <fieldset class="modos">
          <legend>Falhas de sensor</legend>
          <label v-for="m in MODOS_SENSOR" :key="m"><input v-model="p.modos_sensor" type="checkbox" :value="m" /> {{ m.replace('_', ' ') }}</label>
        </fieldset>
        <div class="acoes">
          <div v-if="previa" :class="previa.ok ? '' : 'erro'">
            <b class="mono">{{ previa.leituras.toLocaleString('pt-BR') }}</b> leituras previstas
            <span v-if="previa.leituras < 1_000_000" class="suave"> (o mínimo pedido é 1 milhão)</span>
            <div v-if="!previa.ok">{{ previa.erro }}</div>
          </div>
          <button class="btn" :disabled="!pode('administrador') || (previa !== null && !previa.ok)">Gerar dados</button>
          <small v-if="!pode('administrador')" class="suave">Somente o administrador gera dados.</small>
        </div>
      </form>
      <p v-if="msg" class="suave">{{ msg }}</p>
      <p v-if="erro" class="erro">{{ erro }}</p>
    </div>
    <div class="cartao rolagem">
      <h2>Jobs de geração</h2>
      <JobsLista tipo="geracao" :atualizar="atualizar" />
    </div>
  </div>
</template>

<style scoped>
.nota {
  font-size: 0.85rem;
}
.form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
}
.modos {
  border: 1px solid var(--borda);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}
.acoes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: end;
}
</style>
