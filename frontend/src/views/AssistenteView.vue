<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { nextTick, onMounted, ref } from 'vue'
import { get, streamNdjson } from '../services/api'

// Saida do LLM = texto NAO confiavel: Markdown sem HTML e sem imagens remotas.
const md = new MarkdownIt({ html: false, linkify: false, breaks: true })
md.disable(['image', 'link'])

interface Msg {
  papel: 'user' | 'assistant'
  texto: string
}
const conversa = ref<Msg[]>([])
const pergunta = ref('')
const status = ref('')
const ocupado = ref(false)
const erro = ref('')
const modelo = ref<{ modelo: string; carregado: boolean } | null>(null)
const lista = ref<HTMLDivElement>()

const SUGESTOES = [
  'Qual geladeira está com o compressor em pior estado?',
  'Existe algum alerta aberto? O que devo fazer?',
  'Explique as métricas do último treino em palavras simples.',
  'Como os dados fluem pela arquitetura e por que usamos RabbitMQ?',
]

onMounted(async () => {
  try {
    modelo.value = await get('/api/assistente/status')
  } catch {
    /* ignore */
  }
})

async function rolar() {
  await nextTick()
  lista.value?.scrollTo({ top: lista.value.scrollHeight })
}

async function perguntar(texto?: string) {
  const q = (texto ?? pergunta.value).trim()
  if (!q || ocupado.value) return
  erro.value = ''
  pergunta.value = ''
  const historico = conversa.value.slice(-6)
  conversa.value.push({ papel: 'user', texto: q })
  const resposta: Msg = { papel: 'assistant', texto: '' }
  conversa.value.push(resposta)
  const idx = conversa.value.length - 1
  ocupado.value = true
  status.value = 'Pensando…'
  rolar()
  try {
    for await (const ev of streamNdjson('/api/assistente/perguntar', { pergunta: q, historico })) {
      if (ev.tipo === 'status') status.value = ev.texto
      else if (ev.tipo === 'token') {
        status.value = ''
        conversa.value[idx].texto += ev.texto
        rolar()
      } else if (ev.tipo === 'erro') erro.value = ev.texto
    }
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    ocupado.value = false
    status.value = ''
    if (!conversa.value[idx].texto) conversa.value.splice(idx, 1)
  }
}
</script>

<template>
  <div class="assistente">
    <div class="cartao chat">
      <div class="linha entre cab">
        <span class="suave">
          LLM local <b class="mono">{{ modelo?.modelo ?? '…' }}</b> rodando no Ollama (CPU, sem nuvem).
          {{ modelo ? (modelo.carregado ? 'Modelo carregado.' : 'Modelo ainda não carregado: a primeira resposta demora.') : '' }}
        </span>
      </div>
      <div ref="lista" class="mensagens">
        <div v-if="!conversa.length" class="vazio">
          <p>Pergunte sobre o estado das geladeiras, as previsões da IA, os modelos ou a arquitetura.</p>
          <div class="sugestoes">
            <button v-for="s in SUGESTOES" :key="s" class="btn-sec" @click="perguntar(s)">{{ s }}</button>
          </div>
        </div>
        <div v-for="(m, i) in conversa" :key="i" class="msg" :class="m.papel">
          <!-- eslint-disable-next-line vue/no-v-html -- markdown-it com html:false escapa qualquer HTML -->
          <div v-if="m.papel === 'assistant'" class="md" v-html="md.render(m.texto)"></div>
          <div v-else>{{ m.texto }}</div>
        </div>
        <div v-if="status" class="status"><span class="spinner"></span>{{ status }}</div>
      </div>
      <p v-if="erro" class="erro">{{ erro }}</p>
      <form class="entrada" @submit.prevent="perguntar()">
        <input v-model="pergunta" maxlength="1000" placeholder="Digite sua pergunta…" :disabled="ocupado" />
        <button class="btn" :disabled="ocupado || !pergunta.trim()">Enviar</button>
      </form>
      <small class="suave">Limite de perguntas por minuto por usuário. Cada pergunta é registrada na auditoria.</small>
    </div>
  </div>
</template>

<style scoped>
.assistente {
  max-width: 900px;
}
.chat {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: calc(100vh - 120px);
  min-height: 480px;
}
.cab {
  font-size: 0.85rem;
}
.mensagens {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px;
}
.msg {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.45;
  font-size: 0.93rem;
}
.msg.user {
  align-self: flex-end;
  background: var(--primaria);
  color: white;
}
.msg.assistant {
  align-self: flex-start;
  background: #f1f5f9;
}
.md :deep(p) {
  margin: 0 0 6px;
}
.md :deep(ul),
.md :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.md :deep(code) {
  background: #e2e8f0;
  padding: 1px 4px;
  border-radius: 4px;
}
.sugestoes {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
}
.entrada {
  display: flex;
  gap: 8px;
}
.entrada input {
  flex: 1;
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 9px 12px;
}
.status {
  color: var(--texto-suave);
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 8px;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #cbd5e1;
  border-top-color: var(--primaria);
  border-radius: 50%;
  animation: gira 0.8s linear infinite;
}
@keyframes gira {
  to {
    transform: rotate(360deg);
  }
}
</style>
