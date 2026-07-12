<template>
  <div class="overview-page">
    <el-skeleton v-if="isLoading" :rows="8" animated />

    <template v-else>
      <header class="overview-hero">
        <div class="project-title">
          <p class="eyebrow">项目总览</p>
          <h1>{{ project?.name || '未命名项目' }}</h1>
          <p>{{ project?.description || '广播剧制作工程' }}</p>
          <div class="hero-meta">
            <el-tag :type="statusTagType" effect="dark">{{ productionStatus }}</el-tag>
            <span>完成度 {{ readinessScore }}%</span>
            <span>更新于 {{ updatedAtLabel }}</span>
          </div>
        </div>
        <div class="hero-actions">
          <el-button :icon="Refresh" :loading="isLoadingReadiness" @click="loadReadiness">制作体检</el-button>
          <el-button type="primary" :icon="nextAction.icon" @click="runNextAction(nextAction)">继续制作</el-button>
        </div>
      </header>

      <ProjectStatsGrid :counts="readinessCounts" />
      <section v-if="activeSession" class="session-resume-card">
        <div><p class="eyebrow">未完成会话</p><h2>{{ activeSession.title || '对话式改编' }}</h2><p>{{ sessionStageLabel(activeSession.current_stage) }} · 草稿尚未写入项目</p></div>
        <el-button type="primary" @click="continueSession(activeSession)">继续改编会话</el-button>
      </section>
      <NextActionPanel :action="nextAction" @run="runNextAction" />

      <section class="overview-layout">
        <main class="overview-main">
          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">Workflow</p>
                <h2>制作流程</h2>
              </div>
              <el-progress :percentage="readinessScore" :status="readinessProgressStatus" :stroke-width="12" />
            </div>
            <ProjectProgressStepper :steps="progressSteps" @open="openStep" />
          </section>

          <section class="recent-grid">
            <article class="panel">
              <div class="panel-heading compact">
                <div>
                  <p class="eyebrow">最近章节</p>
                  <h2>章节</h2>
                </div>
                <el-button size="small" @click="router.push(`/studio?project_id=${projectId}`)">写入章节</el-button>
              </div>
              <div v-if="recentChapters.length" class="recent-list">
                <button v-for="chapter in recentChapters" :key="chapter.id" type="button" @click="router.push(`/projects/${projectId}/dubbing`)">
                  <strong>{{ chapter.title }}</strong>
                  <span>{{ chapter.text_content ? `${String(chapter.text_content).length} 字` : '暂无正文' }}</span>
                </button>
              </div>
              <el-empty v-else description="还没有章节" :image-size="64" />
            </article>

            <article class="panel">
              <div class="panel-heading compact">
                <div>
                  <p class="eyebrow">最近改编</p>
                  <h2>运行记录</h2>
                </div>
                <el-button size="small" @click="router.push(`/studio?project_id=${projectId}`)">打开工作台</el-button>
              </div>
              <div v-if="recentRuns.length" class="recent-list">
                <button v-for="run in recentRuns" :key="run.run_id" type="button" @click="router.push(`/studio?project_id=${projectId}`)">
                  <strong>{{ run.title || '未命名改编' }}</strong>
                  <span>{{ runStatusLabel(run) }} · {{ formatDate(run.updated_at || run.created_at) }}</span>
                </button>
              </div>
              <el-empty v-else description="暂无改编记录" :image-size="64" />
            </article>

            <article class="panel">
              <div class="panel-heading compact">
                <div>
                  <p class="eyebrow">最近导出</p>
                  <h2>导出文件</h2>
                </div>
                <el-button size="small" type="primary" plain @click="router.push(`/timeline?project_id=${projectId}`)">预览导出</el-button>
              </div>
              <div class="export-empty">
                <strong>{{ readiness?.ready_for_export ? '可以进入预览导出' : '还不能导出' }}</strong>
                <p>当前版本没有导出历史接口。导出完成后可在配音制作页打开导出目录。</p>
              </div>
            </article>
          </section>
        </main>

        <aside class="overview-side">
          <ReadinessChecklist
            :items="checklistItems"
            :loading="isLoadingReadiness"
            @refresh="loadReadiness"
            @action="runChecklistAction"
          />

          <section class="panel repair-panel">
            <div>
              <p class="eyebrow">自动修复</p>
              <h2>可安全执行的检查</h2>
            </div>
            <el-button :loading="isRepairing" @click="repair(false)">同步已有音频状态</el-button>
            <el-button type="warning" plain :loading="isRepairing" @click="repair(true)">补素材占位</el-button>
          </section>
        </aside>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection,
  DocumentChecked,
  EditPen,
  FolderOpened,
  Headset,
  MagicStick,
  Refresh,
  Setting,
  VideoPlay,
} from '@element-plus/icons-vue'
import NextActionPanel from '../components/project/NextActionPanel.vue'
import ProjectProgressStepper from '../components/project/ProjectProgressStepper.vue'
import ProjectStatsGrid from '../components/project/ProjectStatsGrid.vue'
import ReadinessChecklist from '../components/project/ReadinessChecklist.vue'
import { fetchChatSessions, fetchDramaAdaptations } from '../api/drama'
import { getChaptersByProject } from '../api/chapter'
import { fetchProjectReadiness, getProjectDetail, repairProjectReadiness } from '../api/project'
import { fetchSetupSnapshot, SETUP_STATUS } from '../api/setup'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(route.params.id))
const project = ref(null)
const readiness = ref(null)
const setupSnapshot = ref(null)
const chapters = ref([])
const runs = ref([])
const sessions = ref([])
const isLoading = ref(false)
const isLoadingReadiness = ref(false)
const isRepairing = ref(false)

const readinessCounts = computed(() => readiness.value?.counts || {
  chapters: 0,
  roles: 0,
  lines: 0,
  missing_voice_roles: 0,
  missing_material_lines: 0,
  placeholder_material_lines: 0,
  missing_speakable_audio_lines: 0,
})
const readinessScore = computed(() => readiness.value?.readiness_score || 0)
const readinessProgressStatus = computed(() => {
  if (readinessScore.value >= 85) return 'success'
  if (readinessScore.value >= 50) return 'warning'
  return 'exception'
})
const productionStatus = computed(() => {
  const counts = readinessCounts.value
  if (!readiness.value) return '等待体检'
  if (!readiness.value.ready_for_adaptation && !project.value?.tts_provider_id) return '未配置'
  if (!counts.chapters) return '待改编'
  if (counts.lines && counts.missing_voice_roles) return '待分配声线'
  if (counts.lines && counts.missing_speakable_audio_lines) return '待生成配音'
  if (counts.missing_material_lines) return '待补素材'
  if (readiness.value.ready_for_final_export) return '可导出'
  if (readiness.value.ready_for_export) return '可导出草稿'
  return counts.lines ? '台本已生成' : '台本检查'
})
const statusTagType = computed(() => {
  if (readiness.value?.ready_for_final_export) return 'success'
  if (readinessScore.value >= 50) return 'warning'
  return 'info'
})
const updatedAtLabel = computed(() => formatDate(project.value?.updated_at || project.value?.updatedAt || project.value?.created_at || project.value?.createdAt))
const recentChapters = computed(() => chapters.value.slice(0, 4))
const recentRuns = computed(() => runs.value.slice(0, 4))
const activeSession = computed(() => sessions.value.find((item) => !['completed', 'cancelled'].includes(item.status)))
const setupBlocking = computed(() => {
  const status = setupSnapshot.value?.status
  return status && ![SETUP_STATUS.READY, SETUP_STATUS.SKIPPED].includes(status)
})

const progressSteps = computed(() => {
  const counts = readinessCounts.value
  return [
    {
      key: 'setup',
      title: '项目设置',
      caption: readiness.value?.ready_for_adaptation && project.value?.tts_provider_id ? '模型和配音方式已具备' : '补齐 AI 改编或配音配置',
      metric: project.value?.project_root_path || '默认工作区',
      status: readiness.value?.ready_for_adaptation && project.value?.tts_provider_id ? 'complete' : 'current',
      target: 'setup',
    },
    {
      key: 'adapt',
      title: '小说改编',
      caption: counts.chapters ? '已有章节进入项目' : '从工作台粘贴正文生成章节',
      metric: `章节 ${counts.chapters || 0}`,
      status: counts.chapters ? 'complete' : 'current',
      target: 'studio',
    },
    {
      key: 'script',
      title: '台本检查',
      caption: counts.lines ? '多轨台词已生成' : '章节还没有台词',
      metric: `台词 ${counts.lines || 0}`,
      status: counts.lines ? 'complete' : (counts.chapters ? 'current' : 'not-started'),
      target: 'dubbing',
    },
    {
      key: 'roles',
      title: '角色声线',
      caption: counts.missing_voice_roles ? '存在角色未绑定音色' : '角色声线可继续检查',
      metric: `角色 ${counts.roles || 0}，缺音色 ${counts.missing_voice_roles || 0}`,
      status: counts.missing_voice_roles ? 'issue' : (counts.roles ? 'complete' : 'not-started'),
      target: 'roles',
    },
    {
      key: 'dubbing',
      title: '配音与素材',
      caption: counts.missing_speakable_audio_lines ? '人物或旁白音频未完成' : '可检查素材轨',
      metric: `待配音 ${counts.missing_speakable_audio_lines || 0}，缺素材 ${counts.missing_material_lines || 0}`,
      status: counts.missing_speakable_audio_lines || counts.missing_material_lines ? 'issue' : (counts.lines ? 'complete' : 'not-started'),
      target: counts.missing_material_lines ? 'media-missing' : 'dubbing',
    },
    {
      key: 'export',
      title: '预览导出',
      caption: readiness.value?.ready_for_final_export ? '可以导出正式制作包' : '仍有缺口需要处理',
      metric: `占位素材 ${counts.placeholder_material_lines || 0}`,
      status: readiness.value?.ready_for_final_export ? 'complete' : (readiness.value?.ready_for_export ? 'current' : 'not-started'),
      target: 'timeline',
    },
  ]
})

const checklistItems = computed(() => {
  const counts = readinessCounts.value
  const items = []
  if (!readiness.value?.ready_for_adaptation) {
    items.push({
      key: 'llm',
      level: 'warning',
      title: '还没有配置 LLM，无法自动改编小说',
      detail: '配置 AI 改编模型后，工作台才能把小说正文拆成广播剧台本。',
      actionLabel: '去配置',
      target: 'setup',
    })
  }
  if (!project.value?.tts_provider_id) {
    items.push({
      key: 'tts',
      level: 'warning',
      title: '还没有配置可用配音方式',
      detail: '可以先使用 Edge-TTS 跑通旁白和普通角色。',
      actionLabel: '去配置',
      target: 'setup',
    })
  }
  if (!counts.chapters) {
    items.push({
      key: 'chapters',
      level: 'info',
      title: '项目还没有章节',
      detail: '进入工作台粘贴小说正文，生成或导入第一个章节。',
      actionLabel: '去工作台',
      target: 'studio',
    })
  }
  if (counts.missing_voice_roles) {
    items.push({
      key: 'voices',
      level: 'danger',
      title: `${counts.missing_voice_roles} 个角色没有绑定音色`,
      detail: '绑定声线后才能批量生成对应人物对白。',
      actionLabel: '去绑定声线',
      target: 'roles',
    })
  }
  if (counts.missing_speakable_audio_lines) {
    items.push({
      key: 'speech',
      level: 'warning',
      title: `${counts.missing_speakable_audio_lines} 条人物/旁白还没有生成音频`,
      detail: '进入配音制作页批量生成，失败任务可以在队列里重试。',
      actionLabel: '批量生成',
      target: 'dubbing',
    })
  }
  if (counts.missing_material_lines) {
    items.push({
      key: 'materials',
      level: 'warning',
      title: `${counts.missing_material_lines} 条音效/BGM 还没有素材`,
      detail: '可以先补占位素材跑通导出，正式成片前再替换。',
      actionLabel: '打开素材库',
      target: 'media-missing',
    })
  }
  if (counts.placeholder_material_lines) {
    items.push({
      key: 'placeholders',
      level: 'info',
      title: `${counts.placeholder_material_lines} 条素材是临时占位`,
      detail: '正式导出前建议替换成真实音效或 BGM。',
      actionLabel: '查看占位',
      target: 'media-placeholder',
    })
  }
  return items
})

const nextAction = computed(() => {
  const counts = readinessCounts.value
  if (activeSession.value) return action('继续未完成的改编', sessionStageLabel(activeSession.value.current_stage), '继续会话', 'active-session', MagicStick)
  if (setupBlocking.value) return action('完成首次配置', '补齐应用级配置，之后可以顺畅创建和制作项目。', '打开配置向导', 'setup', Setting)
  if (!readiness.value?.ready_for_adaptation) return action('配置 AI 改编模型', '项目还不能自动改编小说，先完成 LLM 测试。', '去配置', 'setup', Setting)
  if (!counts.chapters) return action('导入或改编小说', '从工作台粘贴正文，生成第一个广播剧章节。', '进入工作台', 'studio', MagicStick)
  if (!counts.lines) return action('生成台本台词', '章节已有正文，但还没有可制作的多轨台词。', '打开配音制作', 'dubbing', EditPen)
  if (counts.missing_voice_roles) return action('分配角色声线', '先把角色和音色绑定好，再批量生成配音。', '去绑定声线', 'roles', Collection)
  if (counts.missing_speakable_audio_lines) return action('生成人物和旁白音频', '进入配音制作页批量生成剩余台词音频。', '批量生成', 'dubbing', Headset)
  if (counts.missing_material_lines) return action('补齐音效和 BGM 素材', '处理素材缺口，必要时先生成占位素材。', '打开素材库', 'media-missing', FolderOpened)
  return action('预览并导出制作包', '当前工程已具备导出条件，可以进入预览导出。', '预览导出', 'timeline', VideoPlay)
})

onMounted(loadAll)

watch(projectId, loadAll)

async function loadAll() {
  if (!projectId.value) return
  isLoading.value = true
  try {
    await Promise.all([
      loadProject(),
      loadReadiness(),
      loadRecentContent(),
      loadSetup(),
    ])
  } finally {
    isLoading.value = false
  }
}

async function loadProject() {
  const response = await getProjectDetail(projectId.value)
  project.value = response?.code === 200 ? response.data : null
}

async function loadReadiness() {
  isLoadingReadiness.value = true
  try {
    const response = await fetchProjectReadiness(projectId.value)
    readiness.value = response?.code === 200 ? response.data : null
  } catch {
    readiness.value = null
  } finally {
    isLoadingReadiness.value = false
  }
}

async function loadRecentContent() {
  const [chapterResponse, runResponse, sessionResponse] = await Promise.all([
    getChaptersByProject(projectId.value).catch(() => null),
    fetchDramaAdaptations({ project_id: projectId.value, limit: 5 }).catch(() => null),
    fetchChatSessions({ project_id: projectId.value, limit: 10 }).catch(() => null),
  ])
  chapters.value = chapterResponse?.code === 200 && Array.isArray(chapterResponse.data) ? chapterResponse.data : []
  runs.value = runResponse?.code === 200 && Array.isArray(runResponse.data) ? runResponse.data : []
  sessions.value = sessionResponse?.code === 200 && Array.isArray(sessionResponse.data) ? sessionResponse.data : []
}

async function loadSetup() {
  setupSnapshot.value = await fetchSetupSnapshot().catch(() => null)
}

function action(title, detail, label, target, icon) {
  return { title, detail, label, target, icon }
}

function routeForTarget(target) {
  const id = projectId.value
  const routes = {
    setup: '/setup',
    studio: `/studio?project_id=${id}`,
    roles: `/roles?project_id=${id}&filter=missing_voice`,
    dubbing: `/projects/${id}/dubbing`,
    'media-missing': `/media?project_id=${id}&asset=missing`,
    'media-placeholder': `/media?project_id=${id}&asset=placeholder`,
    timeline: `/timeline?project_id=${id}`,
    'active-session': activeSession.value ? `/studio?project_id=${id}&session_id=${activeSession.value.session_id}` : `/studio?project_id=${id}`,
  }
  return routes[target] || `/projects/${id}/dubbing`
}

function continueSession(session) {
  router.push(`/studio?project_id=${projectId.value}&session_id=${session.session_id}`)
}

function sessionStageLabel(stage) {
  return {
    created: '准备解析原文', parsing: '正在解析原文', awaiting_role_confirmation: '等待确认角色',
    generating_script: '正在生成剧本', awaiting_script_confirmation: '等待确认剧本',
    script_draft_ready: '等待写入项目', failed: '需要重试当前步骤',
  }[stage] || stage
}

function runNextAction(item) {
  router.push(routeForTarget(item.target))
}

function openStep(step) {
  router.push(routeForTarget(step.target))
}

function runChecklistAction(item) {
  router.push(routeForTarget(item.target))
}

async function repair(createPlaceholders) {
  if (isRepairing.value) return
  if (createPlaceholders) {
    try {
      await ElMessageBox.confirm(
        '这会为缺失的音效/BGM 生成低音量临时占位音频。正式成片前仍建议替换为真实素材。',
        '补素材占位',
        { confirmButtonText: '生成占位', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  }
  isRepairing.value = true
  try {
    const response = await repairProjectReadiness(projectId.value, {
      sync_audio_status: true,
      create_material_placeholders: createPlaceholders,
    })
    if (![200, 207].includes(response?.code)) throw new Error(response?.message || '修复失败')
    const data = response.data || {}
    ElMessage.success(
      createPlaceholders
        ? `已同步 ${data.synced_audio || 0} 条，生成 ${data.created_material_placeholders || 0} 条占位素材`
        : `已同步 ${data.synced_audio || 0} 条音频状态`
    )
    await loadReadiness()
  } catch (error) {
    ElMessage.error(error?.message || '修复失败')
  } finally {
    isRepairing.value = false
  }
}

function runStatusLabel(run) {
  return {
    created: '已创建',
    parse_novel: '解析小说',
    write_script: '生成台本',
    polish_language: '整理语言',
    script_ready: '待写入',
    committed: '已写入',
    failed: '失败',
  }[run.status] || run.current_stage || run.status || '运行记录'
}

function formatDate(value) {
  if (!value) return '暂无时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}
</script>

<style scoped>
.overview-page {
  display: grid;
  gap: 16px;
  min-height: 100%;
  color: var(--el-text-color-primary);
}

.overview-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 24%, var(--el-border-color-light));
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(36, 198, 220, 0.12), rgba(255, 179, 102, 0.1)),
    var(--el-bg-color);
}

.project-title h1,
.project-title p,
.panel-heading h2,
.repair-panel h2 {
  margin: 0;
  letter-spacing: 0;
}

.project-title h1 {
  font-size: 30px;
  line-height: 1.15;
}

.project-title > p {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.hero-meta,
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.hero-meta {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.overview-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
}

.overview-main,
.overview-side {
  display: grid;
  align-content: start;
  gap: 16px;
}

.panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.session-resume-card {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
  padding:16px;
  border:1px solid color-mix(in srgb,var(--el-color-primary) 40%,var(--el-border-color));
  border-radius:10px;
  background:color-mix(in srgb,var(--el-color-primary) 7%,var(--el-bg-color));
}

.session-resume-card h2,
.session-resume-card p { margin:0; }
.session-resume-card > div > p:last-child { margin-top:5px; color:var(--el-text-color-secondary); }

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading .el-progress {
  width: 180px;
}

.panel-heading h2,
.repair-panel h2 {
  font-size: 18px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.recent-list {
  display: grid;
  gap: 8px;
}

.recent-list button {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.recent-list button:hover,
.recent-list button:focus-visible {
  border-color: var(--el-color-primary);
  outline: none;
}

.recent-list span,
.export-empty p {
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

.export-empty {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.export-empty p {
  margin: 0;
}

.repair-panel .el-button {
  justify-self: start;
}

@media (max-width: 1180px) {
  .overview-layout,
  .recent-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .session-resume-card { align-items:stretch; flex-direction:column; }
  .overview-hero,
  .panel-heading {
    flex-direction: column;
    align-items: stretch;
  }

  .panel-heading .el-progress {
    width: 100%;
  }
}
</style>
