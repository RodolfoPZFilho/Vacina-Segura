import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Em desenvolvimento (npm run dev) as chamadas /api e /ws vao para a API local.
// Em producao o nginx do container frontend faz esse encaminhamento.
export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
