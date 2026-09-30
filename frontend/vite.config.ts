import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // o ECharts sozinho passa de 500 kB; o aviso padrao nao se aplica aqui
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    // Permite o acesso pelo link publico gerado por publicar-web.ps1 (Cloudflare Tunnel)
    allowedHosts: ['.trycloudflare.com'],
    // Encaminha as chamadas /api para o backend Python (evita problemas de CORS)
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

