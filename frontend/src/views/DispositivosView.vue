<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { enviar } from '../services/api'
import { NOMES_GRANDEZA } from '../services/comandos'
import { pode } from '../stores/sessao'
import { dados, recarregarCadastro, ROTULO_STATUS, statusDispositivo, versao, versaoCadastro } from '../stores/tempoReal'
import type { Dispositivo } from '../types'

const filtro = ref('')
const erro = ref('')
const editando = ref<string | null>(null)
const novo = ref(false)
const form = reactive<Partial<Dispositivo>>({})

const GRANDEZAS = Object.keys(NOMES_GRANDEZA)

const lista = computed(() => {
  void versao.value
  void versaoCadastro.value
  const f = filtro.value.toLowerCase()
  return dados.dispositivos.filter((d) => !f || `${d.id} ${d.nome} ${d.grandeza}`.toLowerCase().includes(f))
})

function abrirNovo() {
  Object.assign(form, { id: '', nome: '', grandeza: 'temperatura', ubs: 'ubs01', geladeira: 'ubs01-g03', unidade: '°C', faixa_min: 2, faixa_max: 8, ativo: true })
  novo.value = true
  editando.value = null
}
function editar(d: Dispositivo) {
  Object.assign(form, { ...d })
  editando.value = d.id
  novo.value = false
}
function cancelar() {
  editando.value = null
  novo.value = false
  erro.value = ''
}

async function salvar() {
  erro.value = ''
  const corpo = {
    id: form.id,
    nome: form.nome,
    grandeza: form.grandeza,
    ubs: form.ubs,
    geladeira: form.geladeira || null,
    unidade: form.unidade ?? '',
    faixa_min: form.faixa_min === null || (form.faixa_min as unknown) === '' ? null : Number(form.faixa_min),
    faixa_max: form.faixa_max === null || (form.faixa_max as unknown) === '' ? null : Number(form.faixa_max),
    ativo: !!form.ativo,
  }
  try {
    if (novo.value) await enviar('POST', '/api/dispositivos', corpo)
    else await enviar('PUT', `/api/dispositivos/${editando.value}`, corpo)
    await recarregarCadastro()
    cancelar()
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function excluir(d: Dispositivo) {
  if (!confirm(`Excluir o dispositivo ${d.id}? O simulador deixa de publicá-lo.`)) return
  try {
    await enviar('DELETE', `/api/dispositivos/${d.id}`)
    await recarregarCadastro()
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function alternar(d: Dispositivo) {
  try {
    await enviar('PUT', `/api/dispositivos/${d.id}`, { ...d, ativo: !d.ativo })
    await recarregarCadastro()
  } catch (e) {
    erro.value = (e as Error).message
  }
}

function ultima(d: Dispositivo) {
  const c = dados.leituras.get(d.id)?.conteudo
  if (!c) return '—'
  if (d.grandeza === 'compressor') return `${c.vibracao} mm/s · ${c.corrente} A · ${c.temp_compressor} °C`
  if (d.categoria === 'atuador') return c.estado
  return `${c.valor} ${d.unidade}`
}
</script>

<template>
  <div class="grade">
    <div class="cartao">
      <div class="linha entre">
        <div class="linha">
          <input v-model="filtro" class="busca" placeholder="Filtrar por id, nome ou tipo" />
          <span class="suave">{{ lista.length }} dispositivos</span>
        </div>
        <button v-if="pode('administrador')" class="btn" @click="abrirNovo">Novo dispositivo</button>
      </div>
      <p class="suave nota">
        O cadastro fica no PostgreSQL. Ao salvar, a API envia a lista ao simulador pelo RabbitMQ → MQTT (mensagem retida), e o
        simulador passa a publicar (ou deixa de publicar) o dispositivo. Uma geladeira nova aparece sozinha na cena 3D.
      </p>
      <p v-if="erro" class="erro">{{ erro }}</p>

      <form v-if="novo || editando" class="form" @submit.prevent="salvar">
        <label class="campo">Id <input v-model="form.id" :disabled="!novo" required pattern="[A-Za-z0-9_-]+" /></label>
        <label class="campo">Nome <input v-model="form.nome" required /></label>
        <label class="campo">Tipo
          <select v-model="form.grandeza"><option v-for="g in GRANDEZAS" :key="g" :value="g">{{ NOMES_GRANDEZA[g] }}</option></select>
        </label>
        <label class="campo">UBS <input v-model="form.ubs" required /></label>
        <label class="campo">Geladeira <input v-model="form.geladeira" placeholder="ex.: ubs01-g03" /></label>
        <label class="campo">Unidade <input v-model="form.unidade" /></label>
        <label class="campo">Faixa mín. <input v-model="form.faixa_min" type="number" step="any" /></label>
        <label class="campo">Faixa máx. <input v-model="form.faixa_max" type="number" step="any" /></label>
        <label class="campo chk"><input v-model="form.ativo" type="checkbox" /> Ativo</label>
        <div class="linha">
          <button class="btn">Salvar</button>
          <button type="button" class="btn-sec" @click="cancelar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="cartao rolagem">
      <table class="tabela">
        <thead>
          <tr>
            <th>Id</th><th>Tipo</th><th>Categoria</th><th>UBS / geladeira</th><th>Faixa</th><th>Última leitura</th><th>Status</th><th>Ativo</th>
            <th v-if="pode('administrador')"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in lista" :key="d.id">
            <td class="mono">{{ d.id }}</td>
            <td>{{ NOMES_GRANDEZA[d.grandeza] ?? d.grandeza }}</td>
            <td>{{ d.categoria }}<small v-if="d.controle" class="suave"> ({{ d.controle === 'auto' ? 'regra' : 'web' }})</small></td>
            <td class="mono">{{ d.ubs }}<span v-if="d.geladeira"> / {{ d.geladeira }}</span></td>
            <td class="mono">{{ d.faixa_min !== null && d.faixa_max !== null && d.faixa_max > d.faixa_min ? `${d.faixa_min} a ${d.faixa_max}` : '—' }}</td>
            <td class="mono">{{ ultima(d) }}</td>
            <td><span class="pilula" :class="statusDispositivo(d)">{{ ROTULO_STATUS[statusDispositivo(d)] }}</span></td>
            <td>
              <button v-if="pode('administrador')" class="btn-sec mini" @click="alternar(d)">{{ d.ativo ? 'Sim' : 'Não' }}</button>
              <span v-else>{{ d.ativo ? 'Sim' : 'Não' }}</span>
            </td>
            <td v-if="pode('administrador')" class="linha">
              <button class="btn-sec mini" @click="editar(d)">Editar</button>
              <button class="btn-perigo mini" @click="excluir(d)">Excluir</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.busca {
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 7px 10px;
  width: 280px;
}
.nota {
  font-size: 0.83rem;
}
.form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  align-items: end;
  border-top: 1px solid var(--borda);
  padding-top: 12px;
}
.chk {
  flex-direction: row;
  align-items: center;
  gap: 6px;
}
.mini {
  padding: 3px 9px;
  font-size: 0.78rem;
}
</style>
