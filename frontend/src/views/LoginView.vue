<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { enviar } from '../services/api'
import { entrar, type Usuario } from '../stores/sessao'

const login = ref('')
const senha = ref('')
const erro = ref('')
const carregando = ref(false)
const router = useRouter()

async function enviarLogin() {
  erro.value = ''
  carregando.value = true
  try {
    const r = await enviar<{ token: string; usuario: Usuario }>('POST', '/api/auth/login', {
      login: login.value.trim(),
      senha: senha.value,
    })
    entrar(r.token, r.usuario)
    router.push('/')
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    carregando.value = false
  }
}
</script>

<template>
  <div class="tela">
    <form class="cartao caixa" @submit.prevent="enviarLogin">
      <div class="cab">
        <span class="logo">❄</span>
        <div>
          <h1>VacinaSegura</h1>
          <p class="suave">Monitoramento AIoT das geladeiras de vacinas das UBS</p>
        </div>
      </div>
      <label class="campo">Usuário <input v-model="login" autocomplete="username" required /></label>
      <label class="campo">Senha <input v-model="senha" type="password" autocomplete="current-password" required /></label>
      <p v-if="erro" class="erro">{{ erro }}</p>
      <button class="btn" :disabled="carregando">{{ carregando ? 'Entrando…' : 'Entrar' }}</button>
      <p class="suave dica">
        Usuários de demonstração: <b>administrador</b>, <b>operador</b> e <b>visualizador</b>. As senhas são geradas pelo
        script <code>gerar-segredos</code>.
      </p>
    </form>
  </div>
</template>

<style scoped>
.tela {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: radial-gradient(circle at 30% 20%, #164e63, #0f2530 60%);
  padding: 16px;
}
.caixa {
  width: min(400px, 100%);
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 26px;
}
.cab {
  display: flex;
  gap: 12px;
  align-items: center;
}
.logo {
  font-size: 34px;
  color: var(--primaria);
}
.cab p {
  margin: 2px 0 0;
  font-size: 0.85rem;
}
.dica {
  font-size: 0.78rem;
  margin: 0;
}
</style>
