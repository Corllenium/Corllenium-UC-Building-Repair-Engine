import { createRouter, createWebHistory } from 'vue-router'
import ModelsView from './views/ModelsView.vue'
import WorkspaceView from './views/WorkspaceView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'models', component: ModelsView },
    { path: '/workspace/:id', name: 'workspace', component: WorkspaceView },
  ],
})

export default router
