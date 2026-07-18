<template>
  <div class="studio-page">
    <header class="studio-hero">
      <div class="hero-copy">
        <p class="eyebrow">{{ isKnowledgeEntry ? 'KNOWLEDGE AUDIO' : 'AI 改编' }}</p>
        <h1>{{ isKnowledgeEntry ? '把文章变成可听、可复习的知识音频' : (productionMode === 'chat' ? '和制作助手一起改编' : '结构化快速生成') }}</h1>
        <p class="hero-description">{{ isKnowledgeEntry ? '导入文章后，逐步确认原文证据、知识大纲、讲解脚本与复习问题。' : (productionMode === 'chat' ? '逐步确认角色与剧本，随时离开并从检查点继续制作。' : '一次生成完整台本，适合熟悉现有流程的高级用户。') }}</p>
        <div v-if="productionMode === 'structured'" class="hero-metrics">
          <span>{{ sourceCount }} 字</span>
          <span>{{ form.scene_count }} 场</span>
          <span>{{ densityLabel(form.adaptation_density) }}</span>
        </div>
        <el-segmented v-if="!isKnowledgeEntry" v-model="productionMode" class="mode-switch" :options="modeOptions" aria-label="制作模式" />
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadProjects">刷新项目</el-button>
        <el-button v-if="!isKnowledgeEntry && productionMode === 'structured'" type="primary" :icon="VideoPlay" :loading="isRunning" @click="runAdaptation">开始改编</el-button>
      </div>
    </header>

    <ChatProductionPanel
      v-if="productionMode === 'chat'"
      :projects="projects"
      :project-id="form.project_id"
      :session-id="activeSessionId"
      @update:project-id="form.project_id = $event"
      @session-change="activeSessionId = $event"
      @committed="loadReadiness"
    />

    <section v-else class="studio-grid">
      <aside class="setup-panel">
        <el-form label-position="top">
          <el-form-item label="目标项目">
            <el-select v-model="form.project_id" filterable placeholder="选择项目" class="full">
              <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="作品标题">
            <el-input v-model="form.title" placeholder="未命名广播剧" />
          </el-form-item>

          <el-form-item label="章节标题">
            <el-input v-model="form.chapter_title" placeholder="默认使用作品标题" />
          </el-form-item>

          <div class="form-row">
            <el-form-item label="目标场次">
              <el-input-number v-model="form.scene_count" :min="1" :max="24" controls-position="right" class="full" />
            </el-form-item>
            <el-form-item label="改编密度">
              <el-select v-model="form.adaptation_density" class="full">
                <el-option label="紧凑" value="compact" />
                <el-option label="均衡" value="balanced" />
                <el-option label="细致" value="detailed" />
              </el-select>
            </el-form-item>
          </div>

          <el-form-item label="执行选项">
            <el-checkbox v-model="form.commit_to_project">生成后写入项目</el-checkbox>
            <el-checkbox v-model="form.replace_chapter_lines">覆盖目标章节台词</el-checkbox>
          </el-form-item>

          <el-form-item label="改编指令">
            <el-input
              v-model="form.instruction"
              type="textarea"
              :rows="4"
              resize="none"
              placeholder="例如：更悬疑、旁白更少、第二场冲突更强"
            />
          </el-form-item>
        </el-form>
      </aside>

      <main class="source-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">原文</p>
            <h2>小说正文</h2>
          </div>
          <el-tag effect="plain">{{ sourceCount }} 字</el-tag>
        </div>
        <el-input
          v-model="form.source_text"
          type="textarea"
          resize="none"
          class="source-input"
          placeholder="粘贴小说正文"
        />
      </main>

      <aside class="run-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">流程</p>
            <h2>Agent 流程</h2>
          </div>
          <el-tag :type="runTagType" effect="dark">{{ runStatusLabel }}</el-tag>
        </div>

        <section class="readiness-panel">
          <div class="readiness-head">
            <div>
              <strong>制作体检</strong>
              <p>{{ readinessStatusText }}</p>
            </div>
            <el-progress
              type="dashboard"
              :width="82"
              :percentage="readinessScore"
              :status="readinessProgressStatus"
            />
          </div>

          <div class="readiness-metrics">
            <span>章节 {{ readinessCounts.chapters }}</span>
            <span>角色 {{ readinessCounts.roles }}</span>
            <span>台词 {{ readinessCounts.lines }}</span>
            <span>待配音 {{ readinessCounts.missing_speakable_audio_lines }}</span>
            <span>缺素材 {{ readinessCounts.missing_material_lines }}</span>
            <span>占位 {{ readinessCounts.placeholder_material_lines }}</span>
          </div>

          <div v-if="readinessIssues.length" class="readiness-issues">
            <article v-for="issue in readinessIssues" :key="`${issue.title}-${issue.detail}`">
              <el-tag size="small" :type="issueTagType(issue.level)" effect="plain">{{ issue.title }}</el-tag>
              <p>{{ issue.detail }}</p>
              <small>{{ issue.action }}</small>
            </article>
          </div>
          <el-empty v-else description="当前项目已具备制作条件" :image-size="56" />

          <div class="readiness-actions">
            <el-button size="small" :loading="isRepairingReadiness" @click="repairReadiness(false)">同步状态</el-button>
            <el-button size="small" type="warning" plain :loading="isRepairingReadiness" @click="repairReadiness(true)">补素材占位</el-button>
            <el-button size="small" @click="openRolesBoard">角色声线</el-button>
            <el-button size="small" @click="openMediaBoard">素材库</el-button>
            <el-button size="small" type="primary" @click="openDubbingProject">项目总览</el-button>
          </div>
        </section>

        <ol class="stage-list">
          <li v-for="stage in stages" :key="stage.key" :class="{ active: currentStage === stage.key, done: stage.done }">
            <span class="stage-dot"></span>
            <div>
              <strong>{{ stage.title }}</strong>
              <p>{{ stage.caption }}</p>
            </div>
          </li>
        </ol>

        <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />

        <div v-if="result" class="result-actions">
          <el-button
            v-if="result.status === 'script_ready'"
            type="primary"
            :icon="FolderChecked"
            :loading="isCommitting"
            @click="commitResult"
          >
            写入项目
          </el-button>
          <el-button v-if="result.chapter_id" :icon="EditPen" @click="openDubbingProject">
            打开项目总览
          </el-button>
        </div>
      </aside>
    </section>

    <section v-if="productionMode === 'structured'" class="script-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">台本</p>
          <h2>广播剧工程预览</h2>
        </div>
        <el-button :icon="DocumentCopy" :disabled="!scriptJson" @click="copyScript">复制 JSON</el-button>
      </div>

      <div v-if="script" class="script-preview">
        <article v-for="(scene, sceneIndex) in script.scenes" :key="sceneIndex" class="scene-block">
          <header>
            <span>第 {{ sceneIndex + 1 }} 场</span>
            <h3>{{ scene.title }}</h3>
            <p>{{ scene.location }} · {{ scene.mood }}</p>
          </header>
          <div class="line-table">
            <div v-for="(line, lineIndex) in scene.lines" :key="lineIndex" class="line-row" :class="`track-${line.track}`">
              <span class="line-track">{{ trackLabel(line.track) }}</span>
              <strong>{{ line.speaker }}</strong>
              <p>{{ line.text }}</p>
              <el-tag size="small" effect="plain">{{ line.shouldSpeak ? '朗读' : '素材' }}</el-tag>
            </div>
          </div>
        </article>
      </div>
      <el-empty v-else description="暂无广播剧工程" />
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DocumentCopy,
  EditPen,
  FolderChecked,
  Refresh,
  VideoPlay,
} from '@element-plus/icons-vue'
import { fetchProjectReadiness, fetchProjects, repairProjectReadiness } from '../api/project'
import { commitDramaAdaptation, createDramaAdaptation } from '../api/drama'
import ChatProductionPanel from '../components/workflow/ChatProductionPanel.vue'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const isRunning = ref(false)
const isCommitting = ref(false)
const isLoadingReadiness = ref(false)
const isRepairingReadiness = ref(false)
const currentStage = ref('created')
const result = ref(null)
const errorMessage = ref('')
const readiness = ref(null)
const productionMode = ref(route.query.content_type === 'knowledge_article' ? 'chat' : (route.query.mode === 'structured' ? 'structured' : 'chat'))
const activeSessionId = ref(String(route.params.sessionId || route.query.session_id || ''))
const modeOptions = [
  { label: '对话式改编', value: 'chat' },
  { label: '结构化编辑', value: 'structured' },
]

const form = reactive({
  project_id: null,
  title: '未命名广播剧',
  chapter_title: '',
  source_text: '',
  instruction: '',
  scene_count: 4,
  adaptation_density: 'balanced',
  commit_to_project: true,
  replace_chapter_lines: true,
})

const sourceCount = computed(() => form.source_text.trim().length)
const isKnowledgeEntry = computed(() => route.query.content_type === 'knowledge_article')
const script = computed(() => result.value?.script || null)
const scriptJson = computed(() => (script.value ? JSON.stringify(script.value, null, 2) : ''))
const readinessScore = computed(() => readiness.value?.readiness_score || 0)
const readinessCounts = computed(() => readiness.value?.counts || {
  chapters: 0,
  roles: 0,
  lines: 0,
  speakable_lines: 0,
  material_lines: 0,
  missing_voice_roles: 0,
  missing_material_lines: 0,
  placeholder_material_lines: 0,
  missing_speakable_audio_lines: 0,
})
const readinessIssues = computed(() => readiness.value?.issues || [])
const readinessProgressStatus = computed(() => {
  if (readinessScore.value >= 85) return 'success'
  if (readinessScore.value >= 50) return 'warning'
  return 'exception'
})
const readinessStatusText = computed(() => {
  if (isLoadingReadiness.value) return '正在检查项目缺口'
  if (!form.project_id) return '选择项目后开始检查'
  if (!readiness.value) return '暂无体检结果'
  if (readiness.value.ready_for_final_export) return '已具备正式导出制作包条件'
  if (readiness.value.ready_for_export) return '可导出草稿，仍有占位素材需替换'
  if (readiness.value.ready_for_generation) return '可以进入批量配音'
  if (readiness.value.ready_for_adaptation) return '可以开始改编台本'
  return '需要先补模型或项目内容'
})

const stages = computed(() => {
  const order = ['created', 'parse_novel', 'write_script', 'polish_language', 'script_ready', 'committed']
  const currentIndex = order.indexOf(currentStage.value)
  return [
    { key: 'parse_novel', title: '解析小说', caption: '剧情、人物、场景、声音线索' },
    { key: 'write_script', title: '生成台本', caption: '分场、台词、旁白、音效、BGM' },
    { key: 'polish_language', title: '整理可播语言', caption: '多轨分类与声线建议' },
    { key: 'committed', title: '写入工程', caption: '章节、角色、台词、素材轨' },
  ].map((stage) => ({ ...stage, done: currentIndex > order.indexOf(stage.key) }))
})

const runStatusLabel = computed(() => {
  if (isRunning.value) return '运行中'
  if (result.value?.status === 'committed') return '已写入'
  if (result.value?.status === 'script_ready') return '待写入'
  if (errorMessage.value) return '失败'
  return '待开始'
})

const runTagType = computed(() => {
  if (errorMessage.value) return 'danger'
  if (isRunning.value) return 'warning'
  if (result.value?.status === 'committed') return 'success'
  return 'info'
})

onMounted(loadProjects)

watch(
  () => route.query.project_id,
  (projectId) => {
    selectProjectFromQuery(projectId)
    loadReadiness()
  }
)

watch(
  () => route.query.session_id,
  (sessionId) => {
    activeSessionId.value = String(sessionId || '')
    if (sessionId) productionMode.value = 'chat'
  }
)

watch(
  () => route.query.content_type,
  (contentType) => {
    if (contentType === 'knowledge_article') productionMode.value = 'chat'
  }
)

watch(
  () => form.project_id,
  () => {
    loadReadiness()
  }
)

async function loadProjects() {
  projects.value = await fetchProjects()
  if (!selectProjectFromQuery(route.query.project_id) && !form.project_id && projects.value.length) {
    form.project_id = projects.value[0].id
  }
  await loadReadiness()
}

function selectProjectFromQuery(projectId) {
  const numericId = Number(projectId)
  if (!numericId) return false
  const exists = projects.value.some((project) => project.id === numericId)
  if (!exists) return false
  form.project_id = numericId
  return true
}

async function runAdaptation() {
  if (!form.project_id) {
    ElMessage.warning('请选择项目')
    return
  }
  if (!form.source_text.trim()) {
    ElMessage.warning('请粘贴小说正文')
    return
  }

  isRunning.value = true
  errorMessage.value = ''
  result.value = null
  currentStage.value = 'parse_novel'
  try {
    const response = await createDramaAdaptation({ ...form })
    if (response.code !== 200) throw new Error(response.message || '改编失败')
    result.value = response.data
    currentStage.value = response.data.current_stage || response.data.status
    ElMessage.success(response.message || '改编完成')
    await loadReadiness()
  } catch (error) {
    errorMessage.value = error?.message || '改编失败'
    currentStage.value = 'failed'
  } finally {
    isRunning.value = false
  }
}

async function copyScript() {
  if (!scriptJson.value) return
  await navigator.clipboard.writeText(scriptJson.value)
  ElMessage.success('已复制')
}

async function commitResult() {
  if (!result.value?.run_id) return
  isCommitting.value = true
  try {
    const response = await commitDramaAdaptation({
      run_id: result.value.run_id,
      chapter_title: form.chapter_title || form.title,
      replace_chapter_lines: form.replace_chapter_lines,
    })
    if (response.code !== 200) throw new Error(response.message || '写入失败')
    result.value = response.data
    currentStage.value = response.data.current_stage || response.data.status
    ElMessage.success(response.message || '已写入项目')
    await loadReadiness()
  } catch (error) {
    ElMessage.error(error?.message || '写入失败')
  } finally {
    isCommitting.value = false
  }
}

function openDubbingProject() {
  if (!form.project_id) return
  router.push(`/projects/${form.project_id}/overview`)
}

function openRolesBoard() {
  if (!form.project_id) return
  router.push(`/roles?project_id=${form.project_id}&filter=missing_voice`)
}

function openMediaBoard() {
  if (!form.project_id) return
  router.push(`/media?project_id=${form.project_id}&asset=missing`)
}

async function loadReadiness() {
  if (!form.project_id) {
    readiness.value = null
    return
  }
  isLoadingReadiness.value = true
  try {
    const response = await fetchProjectReadiness(form.project_id)
    readiness.value = response?.code === 200 ? response.data : null
  } catch (error) {
    readiness.value = null
  } finally {
    isLoadingReadiness.value = false
  }
}

async function repairReadiness(createPlaceholders) {
  if (!form.project_id || isRepairingReadiness.value) return
  if (createPlaceholders) {
    try {
      await ElMessageBox.confirm(
        '这会为缺失的音效/BGM 轨道生成低音量制作占位音频，方便先完成导出链路。正式成片前仍建议替换成真实素材。',
        '补素材占位',
        {
          confirmButtonText: '生成占位',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    } catch {
      return
    }
  }

  isRepairingReadiness.value = true
  try {
    const response = await repairProjectReadiness(form.project_id, {
      sync_audio_status: true,
      create_material_placeholders: createPlaceholders,
    })
    if (![200, 207].includes(response?.code)) {
      throw new Error(response?.message || '修复失败')
    }
    const data = response.data || {}
    ElMessage.success(
      createPlaceholders
        ? `已同步 ${data.synced_audio || 0} 条，生成 ${data.created_material_placeholders || 0} 条素材占位`
        : `已同步 ${data.synced_audio || 0} 条音频状态`
    )
    await loadReadiness()
  } catch (error) {
    ElMessage.error(error?.message || '修复失败')
  } finally {
    isRepairingReadiness.value = false
  }
}

function trackLabel(track) {
  return {
    voice: '人物',
    narration: '旁白',
    sfx: '音效',
    bgm: 'BGM',
  }[track] || track
}

function densityLabel(value) {
  return {
    compact: '紧凑改编',
    balanced: '均衡改编',
    detailed: '细致改编',
  }[value] || value
}

function issueTagType(level) {
  return {
    danger: 'danger',
    warning: 'warning',
    info: 'info',
  }[level] || 'info'
}
</script>

<style scoped>
.studio-page {
  min-height: 100%;
  color: var(--el-text-color-primary);
}

.studio-hero,
.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.studio-hero {
  min-height: 104px;
  padding: 18px 20px;
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  color: var(--el-text-color-primary);
  background:
    radial-gradient(circle at 78% 20%, color-mix(in srgb, var(--auralis-mint) 19%, transparent), transparent 34%),
    var(--el-bg-color);
  box-shadow: var(--auralis-shadow-sm);
}

.hero-copy,
.header-actions {
  min-width: 0;
}

.studio-hero h1,
.panel-heading h2 {
  margin: 0;
  letter-spacing: 0;
}

.studio-hero h1 {
  font-size: 24px;
  line-height: 1.15;
}

.hero-description {
  max-width: 560px;
  margin: 10px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.65;
}

.panel-heading h2 {
  font-size: 16px;
}

.eyebrow {
  margin: 0 0 4px;
  color: color-mix(in srgb, currentColor 64%, transparent);
  font-size: 12px;
  text-transform: uppercase;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.mode-switch {
  margin-top: 12px;
  min-height: 36px;
}

.hero-metrics span {
  min-height: 28px;
  padding: 5px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  font-size: 12px;
  box-sizing: border-box;
}

.studio-grid {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(420px, 1fr) minmax(260px, 340px);
  gap: 16px;
  align-items: stretch;
}

.setup-panel,
.source-panel,
.run-panel,
.script-panel {
  border: 1px solid var(--el-border-color-light);
  background: color-mix(in srgb, var(--el-bg-color) 94%, transparent);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 14px 34px rgba(17, 24, 39, 0.07);
}

.full {
  width: 100%;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.source-panel {
  min-height: 520px;
  display: flex;
  flex-direction: column;
}

.source-input {
  flex: 1;
  margin-top: 12px;
}

.source-input :deep(.el-textarea__inner) {
  min-height: 448px !important;
  height: 100%;
  line-height: 1.7;
}

.stage-list {
  list-style: none;
  padding: 0;
  margin: 16px 0;
}

.readiness-panel {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-fill-color-light) 72%, transparent);
}

.readiness-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.readiness-head strong,
.readiness-head p {
  min-width: 0;
  overflow-wrap: anywhere;
}

.readiness-head p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.readiness-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.readiness-metrics span {
  min-height: 26px;
  padding: 4px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  color: var(--el-text-color-regular);
  background: var(--el-bg-color);
  font-size: 12px;
  box-sizing: border-box;
}

.readiness-issues {
  display: grid;
  gap: 8px;
  max-height: 260px;
  overflow: auto;
}

.readiness-issues article {
  display: grid;
  gap: 5px;
  padding: 9px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.readiness-issues p,
.readiness-issues small {
  min-width: 0;
  overflow-wrap: anywhere;
}

.readiness-issues p {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.45;
}

.readiness-issues small {
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

.readiness-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.stage-list li {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 10px;
  padding: 10px 0;
  color: var(--el-text-color-secondary);
}

.stage-list strong {
  display: block;
  color: var(--el-text-color-primary);
}

.stage-list p {
  margin: 2px 0 0;
  font-size: 12px;
}

.stage-dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--el-border-color);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--el-border-color) 26%, transparent);
}

.stage-list li.active .stage-dot {
  background: var(--auralis-coral, var(--el-color-warning));
}

.stage-list li.done .stage-dot {
  background: var(--el-color-success);
}

.result-actions {
  margin-top: 16px;
}

.script-panel {
  margin-top: 16px;
}

.script-preview {
  display: grid;
  gap: 14px;
  margin-top: 14px;
}

.scene-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.scene-block header {
  padding: 12px 14px;
  background: var(--el-fill-color-light);
}

.scene-block header span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.scene-block h3,
.scene-block p {
  margin: 4px 0 0;
}

.line-table {
  display: grid;
}

.line-row {
  display: grid;
  grid-template-columns: 58px 110px minmax(0, 1fr) 56px;
  gap: 10px;
  align-items: center;
  min-height: 48px;
  padding: 10px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.line-row p {
  margin: 0;
  min-width: 0;
}

.line-track {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.track-sfx,
.track-bgm {
  background: color-mix(in srgb, var(--el-color-info-light-9) 70%, transparent);
}

@media (max-width: 1180px) {
  .studio-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .studio-grid {
    grid-template-columns: 1fr;
  }

  .source-panel {
    min-height: 360px;
  }

  .source-input :deep(.el-textarea__inner) {
    min-height: 300px !important;
  }
}

@media (max-width: 760px) {
  .studio-hero {
    min-height: 180px;
    padding: 18px;
  }

  .studio-hero h1 {
    max-width: 240px;
    font-size: 30px;
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .el-button {
    flex: 1 1 150px;
    margin-left: 0;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .setup-panel,
  .source-panel,
  .run-panel,
  .script-panel {
    padding: 14px;
  }

  .line-row {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .line-row .el-tag {
    width: fit-content;
  }
}
</style>
