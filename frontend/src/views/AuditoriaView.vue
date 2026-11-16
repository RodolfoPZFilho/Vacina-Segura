<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { get } from '../services/api'

interface Registro {
  id: number
  ts: string
  usuario: string
  acao: string
  detalhe: Record<string, unknown>
  ip: string
}
const registros = ref<Registro[]>([])
const acao = ref('')
const erro = ref('')
const ACOES = ['', 'login', 'login_falhou', 'login_bloqueado', 'comando', 'comando_automatico', 'job_geracao', 'job_treino',
  'pergunta_assistente', 'dispositivo_criado', 'dispositivo_editado', 'dispositivo_excluido', 'regra_editada', 'dlq_esvaziada']

async function carregar() {
  try {
    registros.value = await get<Registro[]>(`/api/auditoria?limite=300${acao.value ? `&acao=${acao.value}` : ''}`)
  } catch (e) {
    erro.value = (e as Error).message
  }
}
watch(acao, carregar)
onMounted(carregar)
</script>

<template>
  <div class="cartao rolagem">
    <div class="linha entre">
      <h2>Registro de auditoria (PostgreSQL)</h2>
      <div class="linha">
        <select v-model="acao">
          <option v-for="a in ACOES" :key="a" :value="a">{{ a || 'todas as ações' }}</option>
        </select>
        <button class="btn-sec" @click="carregar">Atualizar</button>
      </div>
    </div>
    <p v-if="erro" class="erro">{{ erro }}</p>
    <table class="tabela">
      <thead><tr><th>Quando</th><th>Usuário</th><th>Ação</th><th>Detalhe</th><th>IP</th></tr></thead>
      <tbody>
        <tr v-for="r in registros" :key="r.id">
          <td class="mono">{{ new Date(r.ts).toLocaleString() }}</td>
          <td>{{ r.usuario }}</td>
          <td><span class="pilula">{{ r.acao }}</span></td>
          <td class="mono det">{{ JSON.stringify(r.detalhe) }}</td>
          <td class="mono">{{ r.ip }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.det {
  font-size: 0.76rem;
  word-break: break-all;
  max-width: 560px;
}
select {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 6px 8px;
}
</style>
