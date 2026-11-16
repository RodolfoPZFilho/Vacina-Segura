export interface Mensagem<C = Record<string, unknown>> {
  id: string
  ts: string
  tipo: 'telemetria' | 'comando' | 'previsao' | 'alerta' | 'job' | 'config'
  dispositivo: string
  ubs: string
  conteudo: C
}

export interface Dispositivo {
  id: string
  nome: string
  categoria: 'sensor' | 'atuador' | 'equipamento'
  grandeza: string
  ubs: string
  geladeira: string | null
  unidade: string
  faixa_min: number | null
  faixa_max: number | null
  controle: 'auto' | 'manual' | null
  ativo: boolean
}

export interface Previsao {
  status: 'ok' | 'sem_modelo' | 'aquecendo'
  rul_h?: number
  saude?: number
  tendencia?: number
  versao_modelo?: number
  estado_compressor?: string
  leituras?: number
  necessarias?: number
}

export interface Alerta {
  id: number
  dispositivo: string
  ubs: string
  tipo: string
  severidade: 'atencao' | 'critico'
  mensagem: string
  origem: string
  valor: number | null
  aberto_em: string
  fechado_em: string | null
}

export interface Job {
  id: string
  tipo: 'geracao' | 'treino'
  status: string
  progresso: number
  mensagem: string | null
  parametros: Record<string, unknown> | null
  resultado: Record<string, unknown> | null
  criado_por: string
  criado_em: string
}

export type Status = 'normal' | 'atencao' | 'critico' | 'sem_dados'
