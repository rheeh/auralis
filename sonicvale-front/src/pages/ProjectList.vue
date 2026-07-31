<template>
  <div class="project-canvas-page">
    <section class="quick-board">
      <button class="quick-tile primary-tile" type="button" @click="openCreateDialog('studio')">
        <span class="tile-icon">
          <el-icon><EditPen /></el-icon>
        </span>
        <span class="tile-copy"><strong>新建项目</strong><small>创建后直接进入工作台，粘贴小说并生成台本。</small></span>
      </button>
      <button class="quick-tile" type="button" @click="$router.push('/config')">
        <span class="tile-icon">
          <el-icon><Setting /></el-icon>
        </span>
        <span class="tile-copy"><strong>整理模型配置</strong><small>新增或更换 Provider，测试后再绑定项目。</small></span>
      </button>
    </section>

    <section class="project-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">最近</p>
          <h2>我的项目</h2>
        </div>
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
      </div>

      <div v-if="projects.length" class="project-grid">
        <article
          v-for="item in projects"
          :key="item.id"
          class="project-card"
          role="link"
          tabindex="0"
          :aria-label="`打开 ${item.name} 项目工作台`"
          @click="openProject(item)"
          @keydown.enter.prevent="openProject(item)"
          @keydown.space.prevent="openProject(item)"
        >
          <header class="card-header">
            <div>
              <h3 :title="item.name">{{ item.name }}</h3>
              <el-tag v-if="activeSessionFor(item.id)" size="small" type="warning" effect="plain">有未完成会话</el-tag>
              <p :title="item.description">{{ item.description || '自由画布项目' }}</p>
              <small class="card-open-hint">点击进入项目工作台</small>
            </div>
            <el-popconfirm
              title="确认删除这个项目吗？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleDelete(item.id)"
            >
              <template #reference>
                <el-button link type="danger" :icon="Delete" aria-label="删除项目" @click.stop />
              </template>
            </el-popconfirm>
          </header>

          <div class="project-meta-grid">
            <div class="meta-item">
              <el-icon><Cpu /></el-icon>
              <span>{{ item.llmProviderId ? getLLMProviderName(item.llmProviderId) : '未绑定 LLM' }}</span>
            </div>
            <div class="meta-item">
              <el-icon><Mic /></el-icon>
              <span>{{ item.ttsProviderId ? getTTSProviderName(item.ttsProviderId) : '未绑定 TTS' }}</span>
            </div>
            <div class="meta-item">
              <el-icon><Document /></el-icon>
              <span>{{ item.promptId ? getPromptName(item.promptId) : '未绑定提示词' }}</span>
            </div>
            <div class="meta-item">
              <el-icon><Folder /></el-icon>
              <span :title="item.project_root_path">{{ item.project_root_path || '默认工作区' }}</span>
            </div>
          </div>

          <section class="workflow-canvas" :aria-label="`${item.name} 制作画布`">
            <header>
              <strong>制作画布</strong>
              <span>{{ readinessLabel(item) }}</span>
            </header>
            <el-progress
              :percentage="getReadiness(item)?.readiness_score || 0"
              :show-text="false"
              :status="readinessProgressStatus(item)"
            />
            <div class="workflow-nodes">
              <button
                v-for="node in getCanvasNodes(item)"
                :key="node.key"
                type="button"
                class="workflow-node"
                :class="`status-${node.status}`"
                @click.stop="openCanvasNode(item, node)"
              >
                <span></span>
                <strong>{{ node.label }}</strong>
                <small>{{ node.caption }}</small>
              </button>
            </div>
          </section>

          <footer class="project-footer">
            <span>
              <el-icon><Clock /></el-icon>
              {{ new Date(item.createdAt).toLocaleDateString() }}
            </span>
            <div class="card-actions">
              <el-button type="primary" size="small" :icon="EditPen" @click.stop="openWorkspace(item)">{{ activeSessionFor(item.id) ? '继续制作' : '进入工作台' }}</el-button>
            </div>
          </footer>
        </article>
      </div>

      <el-empty v-else description="还没有项目，从一段正文开始吧">
        <el-button type="primary" :icon="Plus" @click="openCreateDialog('studio')">新建项目</el-button>
      </el-empty>
    </section>

    <el-dialog
      title="新建项目"
      v-model="dialogVisible"
      width="720px"
      class="canvas-dialog"
      destroy-on-close
    >
      <el-form :model="form" ref="formRef" label-position="top" @submit.prevent>
        <section class="dialog-intro">
          <div>
            <p class="eyebrow">快速开始</p>
            <h3>只要一个想法就能开始</h3>
          </div>
          <el-tag effect="plain">配置稍后也能补</el-tag>
        </section>

        <el-form-item label="项目名称">
          <el-input
            v-model="form.name"
            placeholder="可留空，例如会自动生成：未命名广播剧 07-02 18:30"
            clearable
          />
        </el-form-item>

        <el-form-item label="一句话备注">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="可选：项目名、风格、主角关系、想做成几集等"
          />
        </el-form-item>

        <el-collapse v-model="advancedOpen" class="advanced-collapse">
          <el-collapse-item title="高级设置：模型、TTS、提示词和保存位置" name="advanced">
            <div class="advanced-grid">
              <el-form-item label="LLM 提供商">
                <el-select v-model="form.llm_provider_id" placeholder="稍后再选" clearable class="full">
                  <el-option v-for="provider in llmProviders" :key="provider.id" :label="provider.name" :value="provider.id" />
                </el-select>
              </el-form-item>

              <el-form-item label="LLM 模型">
                <el-select v-model="form.llm_model" placeholder="稍后再选" clearable class="full">
                  <el-option v-for="model in availableModels" :key="model" :label="model" :value="model" />
                </el-select>
              </el-form-item>

              <el-form-item label="TTS 引擎">
                <el-select v-model="form.tts_provider_id" placeholder="稍后再选" clearable class="full">
                  <el-option v-for="tts in ttsProviders" :key="tts.id" :label="tts.name" :value="tts.id" />
                </el-select>
              </el-form-item>

              <el-form-item label="提示词模板">
                <el-select v-model="form.prompt_id" placeholder="稍后再选" clearable class="full">
                  <el-option v-for="p in prompts" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="项目根路径">
              <el-input
                v-model="form.project_root_path"
                clearable
                placeholder="留空使用默认工作区；也可以输入 /Users/me/Projects/demo"
              >
                <template #append>
                  <el-button @click="pickRootDir">选择</el-button>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="精确填充">
              <el-switch
                v-model="form.is_precise_fill"
                :active-value="1"
                :inactive-value="0"
                active-text="开启"
                inactive-text="关闭"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="isCreating" @click="submitAndOpen">
          创建并进入工作台
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElLoading, ElMessage } from 'element-plus'
import { Clock, Cpu, Delete, Document, EditPen, Folder, Mic, Plus, Refresh, Setting } from '@element-plus/icons-vue'
import { createProject, deleteProject, fetchProjectReadiness, fetchProjects } from '../api/project'
import { fetchLLMProviders, fetchTTSProviders } from '../api/provider'
import { fetchPromptList } from '../api/prompt'
import { fetchChatSessions } from '../api/drama'

const router = useRouter()
const prompts = ref([])
const projects = ref([])
const dialogVisible = ref(false)
const isCreating = ref(false)
const advancedOpen = ref([])
const createDestination = ref('studio')
const formRef = ref(null)
const readinessMap = ref({})
const chatSessions = ref([])

const form = ref(createEmptyForm())
const llmProviders = ref([])
const availableModels = ref([])
const ttsProviders = ref([])

const activeLLMProviders = computed(() => llmProviders.value.filter((item) => item.status !== 0))
const activeTTSProviders = computed(() => ttsProviders.value.filter((item) => item.status !== 0))

onMounted(loadAll)

async function loadAll() {
  const [projectList, llmList, ttsList, promptList, sessionResponse] = await Promise.all([
    fetchProjects(),
    fetchLLMProviders(),
    fetchTTSProviders(),
    fetchPromptList(),
    fetchChatSessions({ limit: 200 }).catch(() => null),
  ])
  projects.value = projectList
  llmProviders.value = Array.isArray(llmList) ? llmList : []
  ttsProviders.value = Array.isArray(ttsList) ? ttsList : []
  prompts.value = Array.isArray(promptList) ? promptList : []
  chatSessions.value = sessionResponse?.code === 200 && Array.isArray(sessionResponse.data) ? sessionResponse.data : []
  await loadProjectReadiness()
}

function activeSessionFor(projectId) {
  return chatSessions.value.find((item) => item.project_id === projectId && !['completed', 'cancelled'].includes(item.status))
}

function openWorkspace(project) {
  router.push(`/projects/${project.id}/workspace`)
}

async function loadProjectReadiness() {
  const entries = await Promise.all(projects.value.map(async (project) => {
    try {
      const response = await fetchProjectReadiness(project.id)
      return [project.id, response?.code === 200 ? response.data : null]
    } catch {
      return [project.id, null]
    }
  }))
  readinessMap.value = Object.fromEntries(entries)
}

function createEmptyForm() {
  return {
    name: '',
    description: '',
    llm_provider_id: null,
    llm_model: null,
    tts_provider_id: null,
    prompt_id: null,
    is_precise_fill: 0,
    project_root_path: '',
  }
}

function openCreateDialog(destination = 'studio') {
  createDestination.value = destination
  advancedOpen.value = []
  form.value = createEmptyForm()
  applySmartDefaults()
  dialogVisible.value = true
}

function applySmartDefaults() {
  const llm = activeLLMProviders.value[0]
  if (llm) {
    form.value.llm_provider_id = llm.id
    const models = parseModelList(llm.model_list)
    availableModels.value = models
    form.value.llm_model = models[0] || null
  }

  const preferredTTS = activeTTSProviders.value.find((item) => item.provider_type === 'edge') || activeTTSProviders.value[0]
  if (preferredTTS) form.value.tts_provider_id = preferredTTS.id

  const prompt = prompts.value[0]
  if (prompt) form.value.prompt_id = prompt.id
}

function parseModelList(value) {
  if (!value) return []
  if (Array.isArray(value)) return value.filter(Boolean)
  return String(value).split(',').map((item) => item.trim()).filter(Boolean)
}

watch(
  () => form.value.llm_provider_id,
  (newVal, oldVal) => {
    const provider = llmProviders.value.find((p) => p.id === newVal)
    availableModels.value = provider ? parseModelList(provider.model_list) : []
    if (newVal !== oldVal) {
      form.value.llm_model = availableModels.value[0] || null
    }
  }
)

const getLLMProviderName = (id) => {
  const p = llmProviders.value.find((x) => x.id === id)
  return p ? p.name : id
}

const getTTSProviderName = (id) => {
  const p = ttsProviders.value.find((x) => x.id === id)
  return p ? p.name : id
}

const getPromptName = (id) => {
  const p = prompts.value.find((x) => x.id === id)
  return p ? p.name : id
}

function getReadiness(project) {
  return readinessMap.value[project.id] || null
}

function readinessLabel(project) {
  const readiness = getReadiness(project)
  if (!readiness) return '等待体检'
  if (readiness.ready_for_final_export) return '正式制作就绪'
  if (readiness.ready_for_export) return '可导出草稿'
  if (readiness.ready_for_generation) return '可批量配音'
  if (readiness.ready_for_adaptation) return '可开始改编'
  return '需要补配置'
}

function readinessProgressStatus(project) {
  const score = getReadiness(project)?.readiness_score || 0
  if (score >= 85) return 'success'
  if (score >= 50) return 'warning'
  return 'exception'
}

function getCanvasNodes(project) {
  const readiness = getReadiness(project)
  const counts = readiness?.counts || {}
  const hasModelConfig = Boolean(project.llmProviderId && project.llmModel)
  const hasTTSConfig = Boolean(project.ttsProviderId)
  const hasScript = (counts.lines || 0) > 0
  const hasRoles = (counts.roles || 0) > 0
  const missingVoices = counts.missing_voice_roles || 0
  const missingMaterial = counts.missing_material_lines || 0
  const missingSpeech = counts.missing_speakable_audio_lines || 0
  const placeholderMaterial = counts.placeholder_material_lines || 0

  return [
    {
      key: 'setup',
      label: '配置',
      caption: hasModelConfig && hasTTSConfig ? '模型已绑定' : '可先空着，后续补',
      status: hasModelConfig && hasTTSConfig ? 'ok' : 'warn',
      target: 'config',
    },
    {
      key: 'script',
      label: '台本',
      caption: hasScript ? `${counts.lines} 条多轨台词` : '粘贴原文或空白编写',
      status: hasScript ? 'ok' : 'wait',
      target: 'studio',
    },
    {
      key: 'roles',
      label: '角色',
      caption: hasRoles ? `${counts.roles} 个角色，缺声线 ${missingVoices}` : '待生成或手动创建',
      status: hasRoles && missingVoices === 0 ? 'ok' : (hasRoles ? 'warn' : 'wait'),
      target: 'roles',
    },
    {
      key: 'speech',
      label: '配音',
      caption: missingSpeech ? `待生成 ${missingSpeech} 条` : '人物/旁白已完成',
      status: hasScript && missingSpeech === 0 ? 'ok' : (hasScript ? 'warn' : 'wait'),
      target: 'dubbing',
    },
    {
      key: 'material',
      label: '素材',
      caption: missingMaterial ? `缺 ${missingMaterial} 条音效/BGM` : (placeholderMaterial ? `占位 ${placeholderMaterial} 条` : '素材已就绪'),
      status: missingMaterial ? 'warn' : (placeholderMaterial ? 'draft' : 'ok'),
      target: 'media',
    },
    {
      key: 'export',
      label: '导出',
      caption: readiness?.ready_for_final_export ? '可出正式制作包' : (readiness?.ready_for_export ? '可出草稿包' : '仍有缺口'),
      status: readiness?.ready_for_final_export ? 'ok' : (readiness?.ready_for_export ? 'draft' : 'wait'),
      target: 'timeline',
    },
  ]
}

function openCanvasNode(project, node) {
  router.push(`/projects/${project.id}/workspace`)
}

function openProject(project) {
  router.push(`/projects/${project.id}/workspace`)
}

async function handleDelete(id) {
  const loading = ElLoading.service({
    lock: true,
    text: '正在删除项目...',
    background: 'rgba(0, 0, 0, 0.28)',
  })
  try {
    await deleteProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  } finally {
    loading.close()
  }
}

async function submitAndStay() {
  await createProjectFromCanvas(null)
}

async function submitAndOpen() {
  await createProjectFromCanvas(createDestination.value)
}

async function createProjectFromCanvas(destination) {
  if (isCreating.value) return
  isCreating.value = true
  try {
    const payload = buildProjectPayload()
    const res = await createProject(payload)
    if (res?.code !== 200) throw new Error(res?.message || '创建失败')

    const created = res.data
    ElMessage.success('项目创建成功')
    dialogVisible.value = false
    await loadAll()

    if (destination) router.push(`/projects/${created.id}/workspace`)
  } catch (error) {
    ElMessage.error(`创建失败：${error?.message || '网络异常'}`)
  } finally {
    isCreating.value = false
  }
}

function buildProjectPayload() {
  return {
    name: form.value.name.trim() || generateProjectName(),
    description: form.value.description.trim(),
    llm_provider_id: form.value.llm_provider_id || null,
    llm_model: form.value.llm_model || null,
    tts_provider_id: form.value.tts_provider_id || null,
    prompt_id: form.value.prompt_id || null,
    is_precise_fill: form.value.is_precise_fill || 0,
    project_root_path: form.value.project_root_path?.trim() || null,
  }
}

function generateProjectName() {
  const date = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `未命名广播剧 ${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const native = window.native
async function pickRootDir() {
  if (!native?.selectDir) {
    ElMessage.info('当前环境不支持系统目录选择，请直接手动输入项目根路径')
    return
  }
  try {
    const dir = await native.selectDir()
    if (dir) form.value.project_root_path = dir
  } catch (error) {
    ElMessage.error(`选择失败：${error?.message || '未知错误'}`)
  }
}
</script>

<style scoped>
.project-canvas-page {
  display: grid;
  gap: 18px;
  color: var(--el-text-color-primary);
}

.canvas-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 24%, var(--el-border-color-light));
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(36, 198, 220, 0.14), rgba(255, 179, 102, 0.14)),
    var(--el-bg-color);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
}

.canvas-hero h1,
.section-heading h2,
.dialog-intro h3,
.project-card h3 {
  margin: 0;
  letter-spacing: 0;
}

.canvas-hero h1 {
  font-size: 30px;
  line-height: 1.15;
}

.hero-copy {
  max-width: 620px;
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.quick-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.quick-tile {
  min-height: 128px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.quick-tile:hover,
.quick-tile:focus-visible {
  transform: translateY(-2px);
  border-color: var(--el-color-primary);
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.08);
  outline: none;
}

.primary-tile {
  background:
    linear-gradient(135deg, rgba(34, 197, 214, 0.15), rgba(255, 179, 102, 0.12)),
    var(--el-bg-color);
}

.tile-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-bottom: 12px;
  border-radius: 8px;
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 12%, transparent);
}

.quick-tile strong {
  display: block;
  margin-bottom: 6px;
  font-size: 15px;
  color: var(--el-text-color-primary);
}

.quick-tile small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.project-section {
  display: grid;
  gap: 14px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.project-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.06);
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.project-card:hover,
.project-card:focus-visible {
  transform: translateY(-2px);
  border-color: var(--el-color-primary);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--el-color-primary) 5%, transparent), transparent),
    var(--el-bg-color);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.1);
  outline: none;
}

.card-header,
.project-footer,
.dialog-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.project-card h3 {
  max-width: 230px;
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-card p {
  display: -webkit-box;
  min-height: 42px;
  margin: 6px 0 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.card-open-hint {
  display: inline-flex;
  margin-top: 8px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 600;
}

.project-meta-grid {
  display: grid;
  gap: 8px;
}

.workflow-canvas {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 16%, var(--el-border-color-lighter));
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--el-color-primary) 5%, transparent), transparent),
    var(--el-fill-color-lighter);
}

.workflow-canvas header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.workflow-canvas header strong {
  font-size: 13px;
}

.workflow-canvas header span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.workflow-nodes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.workflow-node {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  gap: 4px 8px;
  align-items: start;
  min-height: 58px;
  padding: 9px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  text-align: left;
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.workflow-node:hover,
.workflow-node:focus-visible {
  transform: translateY(-1px);
  border-color: var(--el-color-primary);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
  outline: none;
}

.workflow-node > span {
  grid-row: 1 / span 2;
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 999px;
  background: var(--el-color-info);
}

.workflow-node strong,
.workflow-node small {
  min-width: 0;
  overflow-wrap: anywhere;
}

.workflow-node strong {
  font-size: 13px;
  line-height: 1.25;
}

.workflow-node small {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.workflow-node.status-ok > span {
  background: var(--el-color-success);
}

.workflow-node.status-warn > span {
  background: var(--el-color-warning);
}

.workflow-node.status-draft > span {
  background: var(--el-color-primary);
}

.workflow-node.status-wait > span {
  background: var(--el-text-color-placeholder);
}

.meta-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.meta-item span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-item .el-icon {
  color: var(--el-text-color-secondary);
}

.project-footer {
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.project-footer > span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.canvas-dialog :deep(.el-dialog__body) {
  padding-top: 10px;
}

.dialog-intro {
  align-items: center;
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.advanced-collapse {
  margin-top: 4px;
  border-top: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.advanced-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}

.full {
  width: 100%;
}

/* 首页同源的轻盈项目视觉 */
.project-canvas-page { gap:24px; }
.canvas-hero { position:relative;min-height:220px;padding:42px 48px;overflow:hidden;border-color:rgba(137,171,199,.16);border-radius:22px;background:radial-gradient(circle at 74% 48%,rgba(255,247,226,.95),transparent 17%),radial-gradient(circle at 80% 50%,transparent 0 14%,rgba(255,255,255,.82) 14.4% 15.1%,transparent 15.5%),linear-gradient(120deg,rgba(235,248,255,.96),rgba(245,245,255,.88) 58%,rgba(255,246,237,.92));box-shadow:0 18px 50px rgba(65,96,123,.08)}
.canvas-hero::after { content:"";position:absolute;left:42%;right:-4%;top:51%;height:54px;opacity:.46;background:repeating-linear-gradient(90deg,transparent 0 8px,rgba(55,158,220,.55) 8px 10px,transparent 10px 15px);mask:linear-gradient(180deg,transparent 0,black 35% 65%,transparent 100%);transform:skewY(-1deg);pointer-events:none; }
.canvas-hero > * { position:relative;z-index:2; }
.canvas-hero h1 { max-width:430px;font-size:38px;line-height:1.25;color:#1f3048; }
.canvas-hero .hero-copy { max-width:560px;color:#718095; }
.canvas-hero .eyebrow { color:#3598bf;font-weight:700;letter-spacing:.12em; }
.canvas-hero .el-button { height:48px;padding-inline:22px;border-radius:14px; }
.quick-board { grid-template-columns:repeat(2,minmax(0,1fr));gap:14px; }
.quick-tile { display:flex;align-items:center;gap:14px;min-height:72px;padding:14px 18px;border-color:rgba(135,169,197,.15);border-radius:16px;background:rgba(255,255,255,.7);box-shadow:0 10px 28px rgba(63,91,116,.05);backdrop-filter:blur(16px); }
.primary-tile { background:linear-gradient(135deg,rgba(232,248,255,.88),rgba(255,255,255,.78),rgba(255,244,236,.62)); }
.tile-icon { width:42px;height:42px;flex:0 0 42px;margin:0;border-radius:13px;background:linear-gradient(145deg,#e0f3ff,#eef1ff); }
.tile-copy { min-width:0; }
.tile-copy strong { margin-bottom:3px; }
.tile-copy small { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.section-heading { padding:4px 2px; }
.section-heading h2 { color:#22334a;font-size:24px; }
.project-grid { grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px; }
.project-card { gap:16px;padding:18px;overflow:hidden;border-color:rgba(132,166,194,.14);border-radius:20px;background:rgba(255,255,255,.76);box-shadow:0 14px 38px rgba(61,89,114,.07); }
.project-card:hover,.project-card:focus-visible { transform:translateY(-4px);border-color:rgba(66,155,211,.36);box-shadow:0 22px 46px rgba(57,94,125,.13); }
.workflow-canvas { border-color:rgba(125,164,195,.13);border-radius:14px;background:linear-gradient(145deg,rgba(239,249,255,.72),rgba(255,255,255,.7)); }
.workflow-node { border-color:rgba(130,163,190,.14);border-radius:11px;background:rgba(255,255,255,.74); }
.project-footer { border-top-color:rgba(128,159,185,.13); }

@media (max-width: 920px) {
  .canvas-hero,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-actions,
  .section-heading .el-button {
    width: 100%;
  }

  .hero-actions .el-button {
    flex: 1 1 180px;
    margin-left: 0;
  }

  .quick-board {
    grid-template-columns: 1fr;
  }

  .advanced-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .canvas-hero {
    padding: 18px;
  }

  .canvas-hero h1 {
    font-size: 26px;
  }

  .project-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .card-actions .el-button {
    flex: 1;
    margin-left: 0;
  }

  .workflow-nodes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
