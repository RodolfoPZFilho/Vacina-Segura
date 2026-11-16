import { sessao, sair } from '../stores/sessao'

export class ErroApi extends Error {
  status: number
  constructor(status: number, mensagem: string) {
    super(mensagem)
    this.status = status
  }
}

function cabecalhos(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  if (sessao.token) h.Authorization = `Bearer ${sessao.token}`
  return h
}

async function tratar<T>(r: Response): Promise<T> {
  if (r.status === 401 && sessao.token) {
    sair()
    throw new ErroApi(401, 'Sessão expirada. Faça login novamente.')
  }
  if (!r.ok) {
    let msg = `Erro ${r.status}`
    try {
      const corpo = await r.json()
      msg = typeof corpo.detail === 'string' ? corpo.detail : JSON.stringify(corpo.detail ?? corpo)
    } catch {
      /* corpo nao e JSON */
    }
    throw new ErroApi(r.status, msg)
  }
  if (r.status === 204) return undefined as T
  return r.json() as Promise<T>
}

export async function get<T>(url: string): Promise<T> {
  return tratar<T>(await fetch(url, { headers: cabecalhos() }))
}

export async function enviar<T>(metodo: 'POST' | 'PUT' | 'DELETE', url: string, corpo?: unknown): Promise<T> {
  return tratar<T>(
    await fetch(url, {
      method: metodo,
      headers: cabecalhos(corpo !== undefined ? { 'Content-Type': 'application/json' } : {}),
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
    }),
  )
}

/** POST que devolve NDJSON em streaming (assistente). */
export async function* streamNdjson(url: string, corpo: unknown): AsyncGenerator<Record<string, string>> {
  const r = await fetch(url, {
    method: 'POST',
    headers: cabecalhos({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(corpo),
  })
  if (!r.ok || !r.body) {
    await tratar(r)
    return
  }
  const leitor = r.body.getReader()
  const dec = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await leitor.read()
    if (done) break
    buffer += dec.decode(value, { stream: true })
    let i: number
    while ((i = buffer.indexOf('\n')) >= 0) {
      const linha = buffer.slice(0, i).trim()
      buffer = buffer.slice(i + 1)
      if (linha) yield JSON.parse(linha)
    }
  }
}
