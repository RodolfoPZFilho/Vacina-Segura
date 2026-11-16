import { createRouter, createWebHistory } from 'vue-router'
import { pode, sessao, type Papel } from './stores/sessao'

declare module 'vue-router' {
  interface RouteMeta {
    titulo?: string
    papel?: Papel
    publica?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { publica: true, titulo: 'Entrar' } },
    { path: '/', component: () => import('./views/DashboardView.vue'), meta: { titulo: 'Dashboard' } },
    { path: '/gemeo', component: () => import('./views/GemeoView.vue'), meta: { titulo: 'Gêmeo digital 3D' } },
    { path: '/insights', component: () => import('./views/InsightsView.vue'), meta: { titulo: 'Insights da IA' } },
    { path: '/dispositivos', component: () => import('./views/DispositivosView.vue'), meta: { titulo: 'Dispositivos' } },
    { path: '/laboratorio', component: () => import('./views/LabView.vue'), meta: { titulo: 'Laboratório de dados' } },
    { path: '/treinamento', component: () => import('./views/TreinoView.vue'), meta: { titulo: 'Treinamento' } },
    { path: '/mensageria', component: () => import('./views/MensageriaView.vue'), meta: { titulo: 'Mensageria' } },
    { path: '/assistente', component: () => import('./views/AssistenteView.vue'), meta: { titulo: 'Assistente' } },
    {
      path: '/auditoria',
      component: () => import('./views/AuditoriaView.vue'),
      meta: { titulo: 'Auditoria', papel: 'administrador' },
    },
    { path: '/sistema', component: () => import('./views/SistemaView.vue'), meta: { titulo: 'Sistema' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (!to.meta.publica && !sessao.token) return '/login'
  if (to.meta.papel && !pode(to.meta.papel)) return '/'
  return true
})

router.afterEach((to) => {
  document.title = to.meta.titulo ? `${to.meta.titulo} · VacinaSegura` : 'VacinaSegura'
})
