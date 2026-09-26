import { createRouter, createWebHistory } from 'vue-router'
import ModelsView from './views/ModelsView.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import ErrorsView from './views/ErrorsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'models', component: ModelsView },
    { path: '/workspace/:id', name: 'workspace', component: WorkspaceView },
    { path: '/errors', name: 'errors', component: ErrorsView },
  ],
})

export default router
