import { createRouter, createWebHashHistory  } from 'vue-router'

const routes = [
  { path: '/demo', name: 'DemoStudio', component: () => import('../pages/DemoStudio.vue') },
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('../pages/Home.vue')
  },
  {
    path: '/setup',
    name: 'SetupWizard',
    component: () => import('../pages/SetupWizard.vue')
  },
  {
    path: '/studio',
    name: 'Studio',
    component: () => import('../pages/Studio.vue')
  },
  {
    path: '/studio/session/:sessionId',
    name: 'StudioSession',
    component: () => import('../pages/Studio.vue')
  },
  {
    path: '/projects',
    name: 'Scripts',
    component: () => import('../pages/ProjectList.vue')
  },
  {
    path: '/config',
    name: 'ConfigCenter',
    component: () => import('../pages/ConfigCenter.vue')
  },
  {
    path: '/voices',
    name: 'VoiceManager',
    component: () => import('../pages/VoiceManager.vue')
  },
  {
    path: '/roles',
    name: 'Roles',
    component: () => import('../pages/RolesBoard.vue')
  },
  {
    path: '/media',
    name: 'Media',
    component: () => import('../pages/MediaBoard.vue')
  },
  {
    path: '/timeline',
    name: 'Timeline',
    component: () => import('../pages/TimelineBoard.vue')
  },
  {
    path: '/queue',
    name: 'Queue',
    component: () => import('../pages/QueueBoard.vue')
  },
  // 配音详情页面（带项目 ID 参数）
  {
    path: '/projects/:id/workspace',
    name: 'ProjectWorkspace',
    component: () => import('../pages/ProjectWorkspace.vue')
  },
  {
    path: '/projects/:id/overview',
    redirect: to => `/projects/${to.params.id}/workspace`
  },
  { 
    path: '/projects/:id/dubbing', 
    redirect: to => `/projects/${to.params.id}/workspace`
  },
  { path: '/prompts',
    name: 'PromptManager', 
    component:() => import('../pages/PromptManager.vue') },    // 新增路由
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
