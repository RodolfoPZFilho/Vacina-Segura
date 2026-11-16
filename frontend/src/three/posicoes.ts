/**
 * Posicoes 3D dos dispositivos. Ficam SO no frontend, indexadas pelo mesmo id do
 * cadastro (PostgreSQL). Dispositivos novos cadastrados recebem uma vaga automatica.
 *
 * Cada UBS e uma sala; cada geladeira ocupa uma vaga na parede do fundo da sala.
 */
export type Vec3 = [number, number, number]

export const LARGURA_SALA = 12
export const PROFUNDIDADE_SALA = 9
export const ALTURA_SALA = 4
export const ESPACO_ENTRE_SALAS = 14

/** Vaga de cada UBS (sala) e de cada geladeira, pelo id do cadastro. */
export const VAGA_UBS: Record<string, number> = { ubs01: 0, ubs02: 1 }
export const VAGA_GELADEIRA: Record<string, number> = {
  'ubs01-g01': 0,
  'ubs01-g02': 1,
  'ubs02-g01': 0,
  'ubs02-g02': 1,
}

/** Posicao (relativa ao centro da geladeira) de cada tipo de item da geladeira. */
export const OFFSET_GELADEIRA: Record<string, Vec3> = {
  corpo: [0, 0, 0],
  temperatura: [0.25, 1.45, 0.66], // display na porta
  umidade: [-0.78, 1.7, 0.1], // sensor na lateral esquerda
  porta: [0.68, 1.05, 0.66], // sensor magnetico na borda da porta
  compressor: [1.25, 0, -0.25],
  alarme: [-0.45, 2.3, 0.35],
  resfriamento: [0.15, 2.3, -0.15],
}

/** Posicao (relativa ao centro da sala) dos itens da sala. */
export const OFFSET_SALA: Record<string, Vec3> = {
  temp_ambiente: [-5.9, 1.8, 1.5], // termometro na parede lateral
  luminosidade: [-5.9, 2.9, -1.2], // sensor ao lado da janela
  luz: [0, 3.75, 0.5], // luminaria no teto
}

export function centroSala(ubs: string, todasUbs: string[]): Vec3 {
  const vaga = VAGA_UBS[ubs] ?? todasUbs.indexOf(ubs)
  const n = Math.max(todasUbs.length, 2)
  return [vaga * ESPACO_ENTRE_SALAS - ((n - 1) * ESPACO_ENTRE_SALAS) / 2, 0, 0]
}

export function centroGeladeira(gid: string, ubs: string, todasUbs: string[], geladeirasDaUbs: string[]): Vec3 {
  const sala = centroSala(ubs, todasUbs)
  const vaga = VAGA_GELADEIRA[gid] ?? geladeirasDaUbs.indexOf(gid)
  return [sala[0] - 3.2 + vaga * 3.6, 0, -2.7]
}

export function somar(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
