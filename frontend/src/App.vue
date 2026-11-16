<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { pode, sair, sessao } from './stores/sessao'
import { conexao, iniciarTempoReal, semDadosGlobal, versao } from './stores/tempoReal'

const rota = useRoute()
const logado = computed(() => !!sessao.token)

watch(
  logado,
  (v) => {
    if (v) iniciarTempoReal()
  },
  { immediate: true },
)

const semDados = computed(() => {
  void versao.value
  return logado.value && conexao.value === 'conectado' && semDadosGlobal()
})

const menu = computed(() =>
  [
    { para: '/', texto: 'Dashboard', icone: '▦' },
    { para: '/gemeo', texto: 'Gêmeo 3D', icone: '◈' },
    { para: '/insights', texto: 'Insights IA', icone: '♥' },
    { para: '/dispositivos', texto: 'Dispositivos', icone: '⚙' },
    { para: '/laboratorio', texto: 'Laboratório', icone: '⚗' },
    { para: '/treinamento', texto: 'Treinamento', icone: '◎' },
    { para: '/mensageria', texto: 'Mensageria', icone: '⇄' },
    { para: '/assistente', texto: 'Assistente', icone: '✦' },
    { para: '/auditoria', texto: 'Auditoria', icone: '☰', papel: 'administrador' as const },
    { para: '/sistema', texto: 'Sistema', icone: 'ⓘ' },
  ].filter((i) => !i.papel || pode(i.papel)),
)

const PAPEIS: Record<string, string> = {
  visualizador: 'Visualizador',
  operador: 'Operador',
  administrador: 'Administrador',
}
</script>

<template>
  <RouterView v-if="!logado || rota.meta.publica" />
  <div v-else class="layout">
    <aside class="lateral">
      <div class="marca">
        <span class="logo">❄</span>
        <div>
          <strong>VacinaSegura</strong>
          <small>AIoT · UBS</small>
        </div>
      </div>
      <nav>
        <RouterLink v-for="i in menu" :key="i.para" :to="i.para" class="item">
          <span class="ic">{{ i.icone }}</span>{{ i.texto }}
        </RouterLink>
      </nav>
      <div class="usuario">
        <div>
          <strong>{{ sessao.usuario?.nome }}</strong>
          <small>{{ PAPEIS[sessao.usuario?.papel ?? ''] }}</small>
        </div>
        <button class="btn-sec" @click="sair">Sair</button>
      </div>
    </aside>
    <main class="conteudo">
      <header class="topo">
        <h1>{{ rota.meta.titulo }}</h1>
        <span class="conexao" :class="conexao">
          <i></i>{{ conexao === 'conectado' ? 'Tempo real conectado' : conexao === 'conectando' ? 'Conectando…' : 'Desconectado' }}
        </span>
      </header>
      <div v-if="semDados" class="faixa-aviso">
        Nenhum dado em tempo real há mais de 20 s: o simulador pode estar desligado ou pausado.
      </div>
      <RouterView />
    </main>
  </div>
</template>
