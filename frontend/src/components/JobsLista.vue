<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { get } from '../services/api'
import { jobsAoVivo } from '../stores/tempoReal'
import type { Job } from '../types'

const props = defineProps<{ tipo: 'geracao' | 'treino'; atualizar?: number }>()
const emit = defineEmits<{ concluido: [job: Job] }>()
const jobs = ref<Job[]>([])
let timer = 0

async function carregar() {
  const todos = await get<Job[]>('/api/jobs?limite=40')
  const antes = new Map(jobs.value.map((j) => [j.id, j.status]))
  jobs.value = todos.filter((j) => j.tipo === props.tipo)
  for (const j of jobs.value) if (antes.get(j.id) && antes.get(j.id) !== 'concluido' && j.status === 'concluido') emit('concluido', j)
}

const linhas = computed(() =>
  jobs.value.map((j) => {
    const vivo = jobsAoVivo[j.id]
    const emAndamento = vivo && j.status !== 'concluido' && j.status !== 'erro'
    return {
      ...j,
      progresso: emAndamento ? vivo.progresso : j.status === 'concluido' ? 100 : j.progresso,
      mensagem: emAndamento ? vivo.mensagem : j.mensagem,
      status: emAndamento ? vivo.status : j.status,
    }
  }),
)

watch(
  () => Object.values(jobsAoVivo).map((j) => j.status).join(),
  () => carregar(),
)
watch(() => props.atualizar, () => carregar())
onMounted(() => {
  carregar()
  timer = window.setInterval(carregar, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div v-if="!linhas.length" class="vazio">Nenhum job ainda.</div>
  <table v-else class="tabela">
    <thead>
      <tr><th>Job</th><th>Quem</th><th>Status</th><th style="width: 35%">Progresso</th><th>Resultado</th></tr>
    </thead>
    <tbody>
      <tr v-for="j in linhas" :key="j.id">
        <td class="mono">{{ j.id }}<br /><small class="suave">{{ new Date(j.criado_em).toLocaleString() }}</small></td>
        <td>{{ j.criado_por }}</td>
        <td>
          <span class="pilula" :class="j.status === 'concluido' ? 'normal' : j.status === 'erro' ? 'critico' : 'atencao'">{{ j.status }}</span>
        </td>
        <td>
          <div class="barra"><i :style="{ width: `${j.progresso}%` }"></i></div>
          <small class="suave">{{ j.progresso.toFixed(0) }}% · {{ j.mensagem }}</small>
        </td>
        <td class="mono res">
          <template v-if="j.resultado && 'erro' in j.resultado"><span class="erro">{{ j.resultado.erro }}</span></template>
          <template v-else-if="j.resultado && tipo === 'geracao'">
            {{ Number(j.resultado.leituras).toLocaleString('pt-BR') }} leituras · {{ j.resultado.equipamentos }} equip. ·
            {{ j.resultado.equipamentos_com_falha }} com falha · {{ j.resultado.segundos }} s
          </template>
          <template v-else-if="j.resultado && tipo === 'treino'">modelo v{{ j.resultado.versao }} · {{ j.resultado.segundos }} s</template>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.res {
  font-size: 0.8rem;
}
</style>
