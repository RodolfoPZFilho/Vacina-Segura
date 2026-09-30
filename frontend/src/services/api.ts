import type { FaixaSegura, Geladeira, Historico, LeituraAtual, Periodo } from '../types'

async function get<T>(caminho: string): Promise<T> {
  const resposta = await fetch(caminho)
  if (!resposta.ok) {
    throw new Error(`Erro ${resposta.status} ao consultar ${caminho}`)
  }
  return resposta.json() as Promise<T>
}

export const api = {
  faixaSegura: () => get<FaixaSegura>('/api/config'),

  geladeiras: () => get<Geladeira[]>('/api/geladeiras'),

  leituraAtual: (ubs: string, geladeira: string) =>
    get<LeituraAtual>(`/api/leituras/atual?ubs=${encodeURIComponent(ubs)}&geladeira=${encodeURIComponent(geladeira)}`),

  historico: (ubs: string, geladeira: string, periodo: Periodo) =>
    get<Historico>(
      `/api/leituras/historico?ubs=${encodeURIComponent(ubs)}&geladeira=${encodeURIComponent(geladeira)}&periodo=${periodo}`,
    ),
}
