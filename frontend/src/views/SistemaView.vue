<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { get } from '../services/api'

interface Sistema {
  componentes: Record<string, boolean>
  segundos_desde_ultima_telemetria: number | null
  modelo_llm: string
  ws_clientes: number
  links: { nome: string; url: string }[]
}
const s = ref<Sistema | null>(null)
const erro = ref('')
let timer = 0
const NOMES: Record<string, string> = {
  postgresql: 'PostgreSQL',
  influxdb: 'InfluxDB',
  rabbitmq: 'RabbitMQ (API de gerenciamento)',
  ollama: 'Ollama (LLM local)',
  llm_carregado: 'Modelo do LLM carregado na memória',
  telemetria_recente: 'Telemetria chegando (< 20 s)',
}

async function carregar() {
  try {
    s.value = await get<Sistema>('/api/sistema')
    erro.value = ''
  } catch (e) {
    erro.value = (e as Error).message
  }
}
onMounted(() => {
  carregar()
  timer = window.setInterval(carregar, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="grade g2">
    <div class="cartao">
      <h2>Componentes</h2>
      <p v-if="erro" class="erro">{{ erro }}</p>
      <table v-if="s" class="tabela">
        <tbody>
          <tr v-for="(ok, k) in s.componentes" :key="k">
            <td>{{ NOMES[k] ?? k }}</td>
            <td><span class="pilula" :class="ok ? 'normal' : 'critico'">{{ ok ? 'ok' : 'indisponível' }}</span></td>
          </tr>
          <tr><td>Modelo do LLM</td><td class="mono">{{ s.modelo_llm }}</td></tr>
          <tr><td>Navegadores conectados ao WebSocket</td><td class="mono">{{ s.ws_clientes }}</td></tr>
          <tr><td>Última telemetria</td><td class="mono">{{ s.segundos_desde_ultima_telemetria ?? '—' }} s</td></tr>
        </tbody>
      </table>
    </div>
    <div class="cartao">
      <h2>Interfaces para estudo</h2>
      <p class="suave nota">Abertas somente em 127.0.0.1 (na máquina que roda o Docker). Usuários e senhas estão no arquivo <code>.env</code>.</p>
      <ul v-if="s" class="links">
        <li v-for="l in s.links" :key="l.url">
          <a :href="l.url" target="_blank" rel="noopener noreferrer">{{ l.nome }}</a>
          <span class="mono suave">{{ l.url }}</span>
        </li>
      </ul>
      <h2 style="margin-top: 16px">Arquitetura</h2>
      <pre class="arq">
Simulador ⇄ MQTT ⇄ Mosquitto ⇄ Gateway
                                   ⇅
          RabbitMQ (exchange topic vs.topic + DLQ)
   ↓            ⇅               ⇅              ⇅
Gravador   Inferência IA   Lab e treino   API FastAPI ⇄ PostgreSQL
   ↓            ↑               ↓              ⇅          Ollama
InfluxDB      Modelos (volume compartilhado)   ⇅
                                      Frontend (WebSocket)</pre>
    </div>
  </div>
</template>

<style scoped>
.nota {
  font-size: 0.85rem;
}
.links {
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.links li span {
  display: block;
  font-size: 0.8rem;
}
.arq {
  font-size: 0.78rem;
  background: #f8fafc;
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
}
</style>
