import { reactive } from 'vue'

export type Papel = 'visualizador' | 'operador' | 'administrador'
export interface Usuario {
  login: string
  nome: string
  papel: Papel
}

const NIVEL: Record<Papel, number> = { visualizador: 1, operador: 2, administrador: 3 }

function lerSalvo(): { token: string | null; usuario: Usuario | null } {
  try {
    const t = sessionStorage.getItem('vs_token')
    const u = sessionStorage.getItem('vs_usuario')
    return { token: t, usuario: u ? (JSON.parse(u) as Usuario) : null }
  } catch {
    return { token: null, usuario: null }
  }
}

export const sessao = reactive(lerSalvo())

export function entrar(token: string, usuario: Usuario) {
  sessao.token = token
  sessao.usuario = usuario
  try {
    sessionStorage.setItem('vs_token', token)
    sessionStorage.setItem('vs_usuario', JSON.stringify(usuario))
  } catch {
    /* armazenamento indisponivel: sessao so na memoria */
  }
}

export function sair() {
  sessao.token = null
  sessao.usuario = null
  try {
    sessionStorage.removeItem('vs_token')
    sessionStorage.removeItem('vs_usuario')
  } catch {
    /* ignore */
  }
  if (location.pathname !== '/login') location.assign('/login')
}

export function pode(papel: Papel): boolean {
  return !!sessao.usuario && NIVEL[sessao.usuario.papel] >= NIVEL[papel]
}
