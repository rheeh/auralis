<template>
  <div class="app-shell" :class="{ 'sidebar-compact': sidebarCompact, 'is-landing': route.name === 'Home' }">
    <aside v-if="route.name !== 'Home'" class="app-sidebar">
      <RouterLink to="/projects" class="brand" aria-label="Auralis 作品库">
        <span class="brand-mark"><img src="/auralis-mark.svg" alt="" /></span>
        <span class="brand-name">Auralis</span>
      </RouterLink>

      <nav class="sidebar-nav" aria-label="主导航">
        <RouterLink
          v-for="item in primaryNav"
          :key="item.path"
          :to="item.path"
          class="sidebar-link"
          :class="{ active: isNavActive(item) }"
          :title="item.label"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <section v-if="activeProjectId" class="project-nav">
        <p class="nav-section-label">当前作品</p>
        <div class="project-chip" :title="activeProjectName">
          <span>{{ projectInitial }}</span>
          <strong>{{ activeProjectName }}</strong>
        </div>
        <nav aria-label="项目制作导航">
          <RouterLink
            v-for="item in projectNav"
            :key="item.key"
            :to="projectRoute(item.key)"
            class="sidebar-link project-link"
            :class="{ active: item.match(route) }"
            :title="item.label"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
      </section>

      <div class="sidebar-spacer" />
      <nav class="sidebar-nav utility-nav" aria-label="工具导航">
        <RouterLink v-for="item in utilityNav" :key="item.path" :to="item.path" class="sidebar-link" :title="item.label">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <button
        class="sidebar-edge-toggle"
        type="button"
        :aria-label="sidebarCompact ? '展开侧栏' : '收起侧栏'"
        :title="sidebarCompact ? '展开侧栏' : '收起侧栏'"
        @click="sidebarCompact = !sidebarCompact"
      >
        <el-icon><component :is="sidebarCompact ? ArrowRightBold : ArrowLeftBold" /></el-icon>
      </button>
    </aside>

    <section class="app-stage" :class="{ 'is-project-workspace': route.name === 'ProjectWorkspace' }">
      <header v-if="route.name !== 'Home'" class="workspace-bar" :class="{ compact: route.name === 'ProjectWorkspace' }">
        <div class="workspace-title">
          <div class="breadcrumbs">
            <RouterLink v-if="route.name === 'ProjectWorkspace'" to="/projects">项目</RouterLink>
            <span v-else>{{ routeGroup }}</span>
            <el-icon><ArrowRight /></el-icon>
            <strong>{{ routeTitle }}</strong>
          </div>
          <p v-if="route.name !== 'ProjectWorkspace'">{{ routeCaption }}</p>
        </div>

        <div class="workspace-actions">
          <span class="local-status"><i /> 本地自动保存</span>
          <button
            class="icon-button"
            type="button"
            :title="isDark ? '切换浅色' : '切换深色'"
            :aria-label="isDark ? '切换浅色' : '切换深色'"
            @click="toggleTheme"
          >
            <el-icon><component :is="isDark ? Sunny : Moon" /></el-icon>
          </button>
        </div>
      </header>

      <main class="page-surface">
        <router-view />
      </main>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowRight,
  ArrowLeftBold,
  ArrowRightBold,
  DataLine,
  Document,
  Microphone,
  Moon,
  Operation,
  Setting,
  Sunny,
  Tickets,
} from '@element-plus/icons-vue'
import { getProjectDetail } from './api/project'

const route = useRoute()
const sidebarCompact = ref(false)
const isDark = ref(false)
const activeProject = ref(null)

const primaryNav = [
  { path: '/projects', label: '作品', icon: Tickets, match: ['/projects', '/home'] },
  { path: '/voices', label: '音色', icon: Microphone, match: ['/voices'] },
  { path: '/queue', label: '任务', icon: DataLine, match: ['/queue'] },
]

const projectNav = [
  { key: 'workspace', label: '项目工作台', icon: Operation, match: (current) => current.name === 'ProjectWorkspace' },
]

const utilityNav = [
  { path: '/prompts', label: '提示词', icon: Document },
  { path: '/config', label: '设置', icon: Setting },
]

const routeInfo = {
  Home: ['作品', '欢迎回来', '从一个作品开始，继续你的广播剧制作。'],
  Scripts: ['作品', '作品库', '创建、整理并继续最近的广播剧工程。'],
  Studio: ['创作', 'AI 改编', '从原文到角色与台本，逐步确认并写入作品。'],
  StudioSession: ['创作', '继续改编', '恢复上次会话，继续确认角色和台本。'],
  VoiceManager: ['资源', '音色库', '管理可跨作品复用的角色音色。'],
  Queue: ['生产', '任务队列', '查看生成进度，处理失败与等待任务。'],
  ProjectOverview: ['作品', '制作总览', '聚焦当前缺口和下一步制作动作。'],
  ProjectDubbingDetail: ['制作', '台本与配音', '编辑章节、台词、声线与音频结果。'],
  ProjectWorkspace: ['项目', '项目工作台', '从小说原文到逐句音频，在一个页面完成。'],
  Roles: ['制作', '角色与声线', '为当前作品分配角色层级和配音策略。'],
  Media: ['制作', '音频素材', '检查对白、音效和 BGM 素材。'],
  Timeline: ['制作', '时间线', '按多轨结构检查成片节奏。'],
  ConfigCenter: ['系统', '模型与服务', '配置 LLM、TTS 与本地存储。'],
  SetupWizard: ['系统', '首次配置', '完成模型、配音和存储位置配置。'],
  PromptManager: ['系统', '提示词', '管理改编提示词和结构化输出契约。'],
}

const activeProjectId = computed(() => Number(route.params.id || route.query.project_id) || 0)
const activeProjectName = computed(() => activeProject.value?.name || `作品 #${activeProjectId.value}`)
const projectInitial = computed(() => activeProjectName.value.trim().slice(0, 1) || '作')
const currentRouteInfo = computed(() => routeInfo[route.name] || ['工作区', 'Auralis', 'AI 广播剧创作空间'])
const routeGroup = computed(() => currentRouteInfo.value[0])
const routeTitle = computed(() => activeProjectId.value && ['ProjectOverview', 'ProjectDubbingDetail', 'ProjectWorkspace'].includes(route.name)
  ? activeProjectName.value
  : currentRouteInfo.value[1])
const routeCaption = computed(() => currentRouteInfo.value[2])

function isNavActive(item) {
  return item.match.some((prefix) => route.path.startsWith(prefix))
}

function projectRoute(key) {
  const id = activeProjectId.value
  const routes = {
    workspace: `/projects/${id}/workspace`,
  }
  return routes[key]
}

async function loadActiveProject() {
  activeProject.value = null
  if (!activeProjectId.value) return
  try {
    const response = await getProjectDetail(activeProjectId.value)
    if (response?.code === 200) activeProject.value = response.data
  } catch {
    activeProject.value = null
  }
}

function applyTheme(dark) {
  document.documentElement.classList.toggle('dark', !!dark)
}

function toggleTheme() {
  isDark.value = !isDark.value
}

onMounted(() => {
  const stored = localStorage.getItem('sv_theme')
  isDark.value = stored ? stored === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches
  sidebarCompact.value = localStorage.getItem('sv_sidebar_compact') === 'true'
  applyTheme(isDark.value)
  loadActiveProject()
})

watch(activeProjectId, loadActiveProject)
watch(isDark, (dark) => {
  applyTheme(dark)
  localStorage.setItem('sv_theme', dark ? 'dark' : 'light')
})
watch(sidebarCompact, (compact) => localStorage.setItem('sv_sidebar_compact', String(compact)))
</script>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
  overflow: hidden;
}

.app-shell {
  --sidebar-width: 224px;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  width: 100%;
  height: 100vh;
  background: var(--el-bg-color-page);
  transition: grid-template-columns 180ms ease;
}

.app-shell.sidebar-compact {
  --sidebar-width: 76px;
}

.app-shell.is-landing {
  display: block;
  background: #edf1f5;
}

.app-shell.is-landing .app-stage,
.app-shell.is-landing .page-surface {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.app-shell.is-landing .app-stage {
  display: block;
}

.app-shell.is-landing .page-surface {
  padding: 0;
  overflow: auto;
}

.workspace-bar.compact {
  min-height: 48px;
  padding-top: 0;
  padding-bottom: 0;
}

.workspace-bar.compact .workspace-title {
  gap: 0;
}

.breadcrumbs a {
  color: var(--el-color-primary);
  text-decoration: none;
}

.breadcrumbs a:hover {
  text-decoration: underline;
}

.app-stage.is-project-workspace .page-surface {
  padding-top: 10px;
}

.app-sidebar {
  position: relative;
  z-index: 12;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 12px 12px;
  color: #dce8f1;
  background:
    radial-gradient(circle at 12% 3%, rgba(89, 231, 255, 0.27), transparent 24%),
    radial-gradient(circle at 94% 32%, rgba(255, 112, 196, 0.2), transparent 30%),
    linear-gradient(178deg, #15162f 0%, #16152d 48%, #101b36 100%);
  border-right: 1px solid rgba(141, 215, 255, 0.2);
  box-shadow: 10px 0 32px rgba(34, 25, 75, 0.12);
  overflow: visible;
  box-sizing: border-box;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  height: 46px;
  margin: 0 4px 24px;
  color: #fff;
  text-decoration: none;
  overflow: hidden;
}

.brand-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
}

.brand-mark::after {
  content: "";
  position: absolute;
  inset: -5px;
  z-index: -1;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(96, 239, 255, 0.45), rgba(255, 122, 202, 0.38));
  filter: blur(9px);
}

.brand-mark {
  position: relative;
  z-index: 0;
}

.brand-mark img {
  display: block;
  width: 100%;
  height: 100%;
}

.brand-name {
  font-size: 20px;
  font-weight: 750;
  letter-spacing: -0.4px;
}

.sidebar-nav,
.project-nav nav {
  display: grid;
  gap: 5px;
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: #aebfca;
  background: transparent;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
  box-sizing: border-box;
  white-space: nowrap;
  transition: color 150ms ease, background 150ms ease, border-color 150ms ease;
}

.sidebar-link .el-icon {
  width: 20px;
  flex: 0 0 20px;
  font-size: 18px;
}

.sidebar-link:hover,
.sidebar-link:focus-visible {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
  outline: none;
}

.sidebar-link.active,
.sidebar-link.router-link-active {
  color: #fff;
  border-color: rgba(113, 226, 255, 0.42);
  background: linear-gradient(115deg, rgba(77, 213, 237, 0.28), rgba(210, 100, 207, 0.2));
  box-shadow: inset 3px 0 0 #73ecf1, 0 8px 22px rgba(10, 8, 36, 0.2);
}

.project-nav {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.nav-section-label {
  margin: 0 10px 10px;
  color: #6f8796;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.4px;
}

.project-chip {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  margin: 0 5px 10px;
  padding: 8px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.055);
}

.project-chip > span {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 7px;
  color: #09222b;
  background: linear-gradient(135deg, #82eff4, #a9b8ff 60%, #ff9ed8);
  font-size: 13px;
  font-weight: 800;
}

.project-chip strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.project-link {
  min-height: 36px;
  font-size: 13px;
}

.sidebar-spacer {
  flex: 1;
}

.utility-nav {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-edge-toggle {
  position: absolute;
  top: 50%;
  right: -13px;
  z-index: 30;
  display: grid;
  place-items: center;
  width: 26px;
  height: 52px;
  padding: 0;
  border: 1px solid rgba(123, 219, 247, 0.5);
  border-left: 0;
  border-radius: 0 13px 13px 0;
  color: #eafcff;
  background: linear-gradient(180deg, #3a3d77, #26284e);
  box-shadow: 7px 0 16px rgba(25, 17, 68, 0.2);
  transform: translateY(-50%);
  cursor: pointer;
}

.sidebar-edge-toggle:hover,
.sidebar-edge-toggle:focus-visible {
  color: #fff;
  background: linear-gradient(180deg, #4ccedc, #7b65c8);
  outline: none;
}

.sidebar-compact .brand-name,
.sidebar-compact .sidebar-link span,
.sidebar-compact .nav-section-label,
.sidebar-compact .project-chip strong {
  display: none;
}

.sidebar-compact .brand,
.sidebar-compact .sidebar-link,
.sidebar-compact .project-chip {
  justify-content: center;
}

.sidebar-compact .sidebar-link {
  padding-inline: 0;
}

.app-stage {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 68px minmax(0, 1fr);
}

.workspace-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 0 22px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: color-mix(in srgb, var(--el-bg-color) 94%, transparent);
  backdrop-filter: blur(16px);
}

.workspace-title {
  min-width: 0;
}

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.breadcrumbs strong {
  min-width: 0;
  overflow: hidden;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.breadcrumbs .el-icon {
  font-size: 11px;
}

.workspace-title p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.workspace-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 0 0 auto;
}

.local-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-right: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.local-status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2fc2a4;
  box-shadow: 0 0 0 4px rgba(47, 194, 164, 0.12);
}

.icon-button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 9px;
  color: var(--el-text-color-regular);
  background: var(--el-bg-color);
  cursor: pointer;
}

.page-surface {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 18px;
  background:
    radial-gradient(circle at 92% -4%, color-mix(in srgb, var(--auralis-mint) 13%, transparent), transparent 30%),
    var(--el-bg-color-page);
}

@media (max-width: 920px) {
  .app-shell {
    --sidebar-width: 76px;
  }

  .brand-name,
  .sidebar-link span,
  .nav-section-label,
  .project-chip strong,
  .sidebar-edge-toggle {
    display: none;
  }

  .brand,
  .sidebar-link,
  .project-chip {
    justify-content: center;
  }

  .sidebar-link {
    padding-inline: 0;
  }

  .workspace-title p,
  .local-status,
  .project-health-button {
    display: none;
  }
}

@media (max-width: 620px) {
  html,
  body,
  #app {
    overflow: auto;
  }

  .app-shell,
  .app-shell.sidebar-compact {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 100dvh;
  }

  .app-sidebar {
    position: sticky;
    top: 0;
    z-index: 20;
    min-height: 58px;
    flex-direction: row;
    align-items: center;
    padding: 8px;
  }

  .brand {
    height: 38px;
    margin: 0 8px 0 0;
  }

  .sidebar-nav {
    display: flex;
  }

  .project-nav,
  .utility-nav,
  .sidebar-spacer {
    display: none;
  }

  .sidebar-link {
    width: 40px;
    min-height: 40px;
  }

  .app-stage {
    grid-template-rows: 60px auto;
  }

  .workspace-bar {
    padding-inline: 14px;
  }

  .workspace-actions .el-button {
    display: none;
  }

  .page-surface {
    overflow: visible;
    padding: 10px;
  }
}
</style>
