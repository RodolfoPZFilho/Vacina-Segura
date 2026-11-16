import { ref } from 'vue'
import { enviar } from './api'

export const ultimoComando = ref<{ texto: string; erro: boolean; quando: number } | null>(null)

export async function comandar(dispositivo: string, acao: string, extras: Record<string, unknown> = {}) {
  try {
    await enviar('POST', '/api/comandos', { dispositivo, acao, ...extras })
    ultimoComando.value = { texto: `Comando "${acao}" enviado para ${dispositivo}`, erro: false, quando: Date.now() }
  } catch (e) {
    ultimoComando.value = { texto: (e as Error).message, erro: true, quando: Date.now() }
  }
}

export const NOMES_GRANDEZA: Record<string, string> = {
  temperatura: 'Temperatura interna',
  umidade: 'Umidade',
  porta: 'Porta',
  temp_ambiente: 'Temperatura da sala',
  luminosidade: 'Luminosidade',
  compressor: 'Compressor',
  alarme: 'Alarme sonoro',
  resfriamento: 'Resfriamento de emergência',
  luz: 'Luz da sala',
}

export const NOMES_UBS: Record<string, string> = { ubs01: 'UBS Centro', ubs02: 'UBS Vila Nova' }

export function nomeGeladeira(gid: string): string {
  const [ubs, g] = gid.split('-')
  return `${NOMES_UBS[ubs] ?? ubs} · ${g?.toUpperCase()}`
}

export function fmt(v: unknown, casas = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(casas) : '—'
}
