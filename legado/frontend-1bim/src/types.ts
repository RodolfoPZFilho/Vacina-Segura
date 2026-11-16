export type Status = 'ok' | 'abaixo' | 'acima' | 'sem_dados'

export type Periodo = '15m' | '1h' | '6h' | '24h' | '7d' | '10d'

export interface Geladeira {
  ubs: string
  geladeira: string
  temperatura: number
  horario: string
  status: Status
}

export interface LeituraAtual {
  horario: string
  temperatura: number
  umidade: number | null
  status: Status
}

export interface PontoHistorico {
  horario: string
  temperatura: number | null
  umidade: number | null
}

export interface Estatisticas {
  minima: number | null
  maxima: number | null
  media: number | null
  total_leituras: number
  leituras_fora_da_faixa: number
}

export interface Historico {
  periodo: Periodo
  pontos: PontoHistorico[]
  estatisticas: Estatisticas
}

export interface FaixaSegura {
  temp_min: number
  temp_max: number
}
