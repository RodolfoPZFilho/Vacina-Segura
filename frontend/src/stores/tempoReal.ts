/**
 * Store de tempo real alimentado SOMENTE pelo WebSocket da API.
 *
 * Os dados brutos ficam em estruturas nao reativas (markRaw) para a cena 3D ler
 * dentro do loop de animacao sem custo. A UI em Vue observa apenas `versao`,
 * incrementada no maximo 4x por segundo.
 */
import { markRaw, reactive, ref } from 'vue'
import { enviar, get } from '../services/api'
import type { Alerta, Dispositivo, Mensagem, Previsao, Status } from '../types'

export interface Leitura {
  conteudo: Record<string, any>
  ts: string
  recebidoEm: number
}

const MAX_HIST = 120
export const SEM_DADOS_MS = 20_000

export const dados = markRaw({
  leituras: new Map<string, Leitura>(),
  historico: new Map<string, number[][]>(), // id -> [[t, v], ...]
  previsoes: new Map<string, Previsao & { recebidoEm: number }>(),
  ultimaMsg: 0,
  msgsPorSegundo: 0,
  dispositivos: [] as Dispositivo[],
})

export const versao = ref(0)
export const conexao = ref<'desconectado' | 'conectando' | 'conectado'>('desconectado')
export const alertasAbertos = ref<Alerta[]>([])
export const jobsAoVivo = reactive<Record<string, { progresso: number; mensagem: string; status: string; tipo: string }>>({})
export const versaoCadastro = ref(0)

let ws: WebSocket | null = null
let tentativas = 0
let contagem = 0
let agendado = false
let ativo = false

function avisarUi() {
  if (agendado) return
  agendado = true
  setTimeout(() => {
    agendado = false
    versao.value++
  }, 250)
}

function valorPrincipal(c: Record<string, any>): number | null {
  if (typeof c.valor === 'number') return c.valor
  if (typeof c.vibracao === 'number') return c.vibracao
  return null
}

function aoTelemetria(m: Mensagem) {
  const agora = Date.now()
  dados.leituras.set(m.dispositivo, { conteudo: m.conteudo, ts: m.ts, recebidoEm: agora })
  const v = valorPrincipal(m.conteudo)
  if (v !== null) {
    let h = dados.historico.get(m.dispositivo)
    if (!h) dados.historico.set(m.dispositivo, (h = []))
    h.push([agora, v])
    if (h.length > MAX_HIST) h.shift()
  }
  dados.ultimaMsg = agora
  contagem++
}

function aoPrevisao(m: Mensagem<Previsao>) {
  dados.previsoes.set(m.dispositivo, { ...m.conteudo, recebidoEm: Date.now() })
  if (m.conteudo.status === 'ok' && typeof m.conteudo.saude === 'number') {
    const id = `${m.dispositivo}#saude`
    let h = dados.historico.get(id)
    if (!h) dados.historico.set(id, (h = []))
    h.push([Date.now(), m.conteudo.saude])
    if (h.length > MAX_HIST) h.shift()
  }
}

function aoMensagem(ev: MessageEvent) {
  const d = JSON.parse(ev.data)
  if (d.canal === 'inicial') {
    for (const m of d.leituras as Mensagem[]) {
      dados.leituras.set(m.dispositivo, { conteudo: m.conteudo, ts: m.ts, recebidoEm: Date.parse(m.ts) || 0 })
    }
    for (const m of d.previsoes as Mensagem<Previsao>[]) {
      dados.previsoes.set(m.dispositivo, { ...m.conteudo, recebidoEm: Date.parse(m.ts) || 0 })
    }
  } else if (d.canal === 'telemetry') {
    aoTelemetria(d.msg)
  } else if (d.canal === 'prediction') {
    aoPrevisao(d.msg)
  } else if (d.canal === 'alerta_db') {
    const a = d.msg as Alerta
    const resto = alertasAbertos.value.filter((x) => x.id !== a.id)
    alertasAbertos.value = a.fechado_em ? resto : [a, ...resto]
  } else if (d.canal === 'job') {
    const c = d.msg.conteudo
    jobsAoVivo[c.job_id] = { progresso: c.progresso, mensagem: c.mensagem ?? c.status, status: c.status, tipo: c.tipo }
  }
  avisarUi()
}

async function abrir() {
  if (!ativo) return
  conexao.value = 'conectando'
  try {
    const { ticket } = await enviar<{ ticket: string }>('POST', '/api/ws/ticket')
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws?ticket=${encodeURIComponent(ticket)}`)
    ws.onopen = () => {
      conexao.value = 'conectado'
      tentativas = 0
    }
    ws.onmessage = aoMensagem
    ws.onclose = () => {
      conexao.value = 'desconectado'
      ws = null
      if (ativo) setTimeout(abrir, Math.min(15000, 1000 * 2 ** tentativas++))
    }
  } catch {
    conexao.value = 'desconectado'
    if (ativo) setTimeout(abrir, Math.min(15000, 1000 * 2 ** tentativas++))
  }
}

export async function recarregarCadastro() {
  dados.dispositivos = await get<Dispositivo[]>('/api/dispositivos')
  versaoCadastro.value++
}

export async function recarregarAlertas() {
  alertasAbertos.value = await get<Alerta[]>('/api/alertas?abertos=true')
}

export function iniciarTempoReal() {
  if (ativo) return
  ativo = true
  abrir()
  recarregarCadastro().catch(() => {})
  recarregarAlertas().catch(() => {})
  setInterval(() => {
    dados.msgsPorSegundo = contagem / 5
    contagem = 0
    versao.value++
  }, 5000)
}

export function pararTempoReal() {
  ativo = false
  ws?.close()
}

// ----------------------------------------------------------------- status
export function semDadosGlobal(): boolean {
  return !dados.ultimaMsg || Date.now() - dados.ultimaMsg > SEM_DADOS_MS
}

const PESO: Record<Status, number> = { sem_dados: 0, normal: 1, atencao: 2, critico: 3 }
export function pior(...s: Status[]): Status {
  return s.reduce((a, b) => (PESO[b] > PESO[a] ? b : a), 'normal' as Status)
}

export const FAIXAS_COMPRESSOR: Record<string, [number, number]> = {
  vibracao: [0, 3.5],
  corrente: [0, 2.6],
  temp_compressor: [0, 60],
}

export function statusDispositivo(d: Dispositivo): Status {
  const l = dados.leituras.get(d.id)
  if (!l || Date.now() - l.recebidoEm > SEM_DADOS_MS) return 'sem_dados'
  const c = l.conteudo
  const alertas = alertasAbertos.value.filter((a) => a.dispositivo === d.id)
  const sAlerta: Status = alertas.some((a) => a.severidade === 'critico')
    ? 'critico'
    : alertas.length
      ? 'atencao'
      : 'normal'
  if (d.categoria === 'atuador') return c.estado === 'ligado' && d.grandeza === 'alarme' ? 'critico' : 'normal'
  if (d.grandeza === 'porta') return c.valor ? 'atencao' : 'normal'
  if (d.grandeza === 'compressor') {
    const p = dados.previsoes.get(d.id)
    let s: Status = 'normal'
    if (c.estado === 'parado') s = 'critico'
    else if (p && p.status === 'ok') {
      if ((p.saude ?? 100) < 30 || (p.rul_h ?? 999) < 24) s = 'critico'
      else if ((p.saude ?? 100) < 60) s = 'atencao'
    } else {
      for (const [k, [, hi]] of Object.entries(FAIXAS_COMPRESSOR)) if (c[k] > hi) s = 'atencao'
    }
    return pior(s, sAlerta)
  }
  const v = c.valor as number
  if (d.faixa_min !== null && d.faixa_max !== null && d.faixa_max > d.faixa_min) {
    if (v < d.faixa_min || v > d.faixa_max) return pior('critico', sAlerta)
    const margem = (d.faixa_max - d.faixa_min) * 0.1
    if (v < d.faixa_min + margem || v > d.faixa_max - margem) return pior('atencao', sAlerta)
  }
  return pior('normal', sAlerta)
}

export const COR_STATUS: Record<Status, string> = {
  normal: '#16a34a',
  atencao: '#eab308',
  critico: '#dc2626',
  sem_dados: '#94a3b8',
}

export const ROTULO_STATUS: Record<Status, string> = {
  normal: 'Normal',
  atencao: 'Atenção',
  critico: 'Crítico',
  sem_dados: 'Sem dados',
}
