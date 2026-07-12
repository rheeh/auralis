<template>
  <div class="board-page">
    <header class="board-header">
      <div>
        <p class="eyebrow">素材</p>
        <h1>音频素材库</h1>
      </div>
      <div class="filters">
        <el-select v-model="projectId" filterable placeholder="项目" @change="loadChapters">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="chapterId" filterable placeholder="章节" @change="loadLines">
          <el-option v-for="chapter in chapters" :key="chapter.id" :label="chapter.title" :value="chapter.id" />
        </el-select>
      </div>
    </header>

    <section class="media-toolbar">
      <el-segmented v-model="trackFilter" :options="trackOptions" />
      <el-select v-model="assetFilter" class="status-filter">
        <el-option label="全部素材" value="all" />
        <el-option label="已绑定" value="ready" />
        <el-option label="缺素材" value="missing" />
        <el-option label="占位素材" value="placeholder" />
      </el-select>
      <el-input v-model="keyword" clearable placeholder="搜索台词、提示或路径" class="search-box" />
      <el-tag effect="plain">{{ filteredLines.length }} / {{ lines.length }} 条</el-tag>
      <el-button @click="loadLines">刷新</el-button>
      <el-button type="warning" plain :loading="isRepairing" @click="createPlaceholders">补素材占位</el-button>
      <el-button type="primary" @click="openDubbingProject">打开配音工程</el-button>
    </section>

    <div class="media-grid">
      <article v-for="line in filteredLines" :key="line.id" class="media-item">
        <div>
          <div class="media-tags">
            <el-tag effect="plain">{{ trackLabel(line.track) }}</el-tag>
            <el-tag :type="isAudioReady(line) ? 'success' : 'info'" effect="plain">
              {{ isAudioReady(line) ? '已绑定' : '缺素材' }}
            </el-tag>
            <el-tag v-if="isPlaceholderMaterial(line)" type="warning" effect="plain">
              占位素材
            </el-tag>
            <el-tag v-if="line.status" effect="plain">{{ statusLabel(line.status) }}</el-tag>
          </div>
          <strong>{{ line.text_content || '空台词' }}</strong>
          <small v-if="line.sound_prompt">{{ line.sound_prompt }}</small>
          <span>{{ line.audio_path || '尚未生成音频' }}</span>
        </div>
        <audio v-if="line.audio_path" controls :src="toAudioUrl(line)" />
        <footer class="media-actions">
          <el-button size="small" :disabled="!line.audio_path" @click="copyPath(line.audio_path)">复制路径</el-button>
          <el-button size="small" :disabled="!line.audio_path" @click="openAudioFolder(line.audio_path)">打开目录</el-button>
          <el-button size="small" type="primary" plain @click="openDubbingProject">编辑台词</el-button>
        </footer>
      </article>
    </div>
    <el-empty v-if="!filteredLines.length" description="暂无素材" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchProjectReadiness, fetchProjects, repairProjectReadiness } from '../api/project'
import { getChaptersByProject } from '../api/chapter'
import { getLineAudioUrl, getLinesByChapter } from '../api/line'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const chapters = ref([])
const lines = ref([])
const projectId = ref(null)
const chapterId = ref(null)
const native = window.native
const trackFilter = ref('all')
const assetFilter = ref('all')
const keyword = ref('')
const readiness = ref(null)
const isRepairing = ref(false)

const trackOptions = [
  { label: '全部', value: 'all' },
  { label: '人物声', value: 'voice' },
  { label: '旁白', value: 'narration' },
  { label: '音效', value: 'sfx' },
  { label: 'BGM', value: 'bgm' },
]

const filteredLines = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return lines.value.filter((line) => {
    const track = line.track || 'voice'
    if (trackFilter.value !== 'all' && track !== trackFilter.value) return false
    if (assetFilter.value === 'ready' && !isAudioReady(line)) return false
    if (assetFilter.value === 'missing' && isAudioReady(line)) return false
    if (assetFilter.value === 'placeholder' && !isPlaceholderMaterial(line)) return false
    if (!q) return true
    return [
      line.text_content,
      line.sound_prompt,
      line.production_note,
      line.audio_path,
      line.scene_title,
    ].some((value) => String(value || '').toLowerCase().includes(q))
  })
})

const missingLineIds = computed(() => {
  const ids = new Set()
  ;(readiness.value?.missing_material_lines || []).forEach((line) => ids.add(line.line_id))
  ;(readiness.value?.missing_speakable_audio_lines || []).forEach((line) => ids.add(line.line_id))
  return ids
})

const placeholderLineIds = computed(() => {
  const ids = new Set()
  ;(readiness.value?.placeholder_material_lines || []).forEach((line) => ids.add(line.line_id))
  return ids
})

onMounted(async () => {
  projects.value = await fetchProjects()
  applyAssetFilterFromQuery()
  if (projects.value.length) {
    projectId.value = selectProjectFromQuery() || projects.value[0].id
    await loadChapters()
  }
})

watch(
  () => route.query.project_id,
  async () => {
    const selected = selectProjectFromQuery()
    if (selected && selected !== projectId.value) {
      projectId.value = selected
      await loadChapters()
    }
    applyAssetFilterFromQuery()
  }
)

watch(
  () => route.query.asset,
  () => {
    applyAssetFilterFromQuery()
  },
  { immediate: true }
)

function selectProjectFromQuery() {
  const id = Number(route.query.project_id)
  if (!id) return null
  return projects.value.some((project) => project.id === id) ? id : null
}

function applyAssetFilterFromQuery() {
  const value = String(route.query.asset || '')
  if (['all', 'ready', 'missing', 'placeholder'].includes(value)) {
    assetFilter.value = value
  }
}

async function loadChapters() {
  chapters.value = []
  lines.value = []
  chapterId.value = null
  if (!projectId.value) return
  await loadReadiness()
  const response = await getChaptersByProject(projectId.value)
  chapters.value = response.code === 200 ? response.data : []
  if (chapters.value.length) {
    chapterId.value = chapters.value[0].id
    await loadLines()
  }
}

async function loadLines() {
  lines.value = []
  if (!chapterId.value) return
  await loadReadiness()
  const response = await getLinesByChapter(chapterId.value)
  lines.value = response.code === 200 ? response.data : []
}

async function loadReadiness() {
  if (!projectId.value) {
    readiness.value = null
    return
  }
  try {
    const response = await fetchProjectReadiness(projectId.value)
    readiness.value = response?.code === 200 ? response.data : null
  } catch {
    readiness.value = null
  }
}

function trackLabel(track) {
  return { voice: '人物声', narration: '旁白', sfx: '音效', bgm: 'BGM' }[track] || '台词'
}

function statusLabel(status) {
  return {
    pending: '未生成',
    queued: '已入队',
    processing: '生成中',
    done: '已生成',
    failed: '失败',
    skipped: '素材轨',
  }[status] || status
}

function toAudioUrl(line) {
  if (!line?.audio_path) return ''
  if (/^https?:/.test(line.audio_path)) return line.audio_path
  return getLineAudioUrl(line.id)
}

function isAudioReady(line) {
  return Boolean(line.audio_path) && !missingLineIds.value.has(line.id)
}

function isPlaceholderMaterial(line) {
  const note = line.production_note || ''
  const path = line.audio_path || ''
  return placeholderLineIds.value.has(line.id)
    || note.includes('[AURALIS_PLACEHOLDER_MATERIAL]')
    || path.includes('_material_placeholder')
}

async function createPlaceholders() {
  if (!projectId.value || isRepairing.value) return
  try {
    await ElMessageBox.confirm(
      '这会给缺失的音效/BGM 生成低音量临时占位，方便先跑通导出。正式成片前应替换为真实素材。',
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

  isRepairing.value = true
  try {
    const response = await repairProjectReadiness(projectId.value, {
      sync_audio_status: true,
      create_material_placeholders: true,
    })
    if (![200, 207].includes(response?.code)) throw new Error(response?.message || '生成失败')
    const data = response.data || {}
    ElMessage.success(`已生成 ${data.created_material_placeholders || 0} 条素材占位`)
    await loadLines()
  } catch (error) {
    ElMessage.error(error?.message || '生成失败')
  } finally {
    isRepairing.value = false
  }
}

async function copyPath(path) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    ElMessage.success('路径已复制')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

async function openAudioFolder(path) {
  if (!path) return
  const folder = dirname(path)
  if (native?.openFolder) {
    const ok = await native.openFolder(folder)
    if (ok) return
  }
  ElMessage.info('当前环境不支持直接打开目录')
}

function openDubbingProject() {
  if (!projectId.value) {
    ElMessage.warning('请选择项目')
    return
  }
  router.push(`/projects/${projectId.value}/dubbing`)
}

function dirname(path) {
  return String(path).replace(/[\\/][^\\/]*$/, '')
}
</script>

<style scoped>
.board-page {
  min-height: 100%;
}

.board-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.board-header h1 {
  margin: 0;
  font-size: 24px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.filters {
  display: flex;
  gap: 10px;
}

.filters .el-select {
  width: 220px;
}

.media-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px;
  margin-bottom: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.status-filter {
  width: 130px;
}

.search-box {
  width: min(360px, 100%);
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}

.media-item {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.media-item div {
  display: grid;
  gap: 6px;
}

.media-tags {
  display: flex !important;
  flex-wrap: wrap;
  gap: 6px;
}

.media-item strong,
.media-item span,
.media-item small {
  min-width: 0;
  overflow-wrap: anywhere;
}

.media-item span,
.media-item small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.media-item audio {
  width: 100%;
}

.media-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 760px) {
  .board-header,
  .filters {
    align-items: stretch;
    flex-direction: column;
  }

  .filters .el-select,
  .status-filter,
  .search-box {
    width: 100%;
  }

  .media-grid {
    grid-template-columns: 1fr;
  }
}
</style>
