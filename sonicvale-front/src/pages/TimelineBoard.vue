<template>
  <div class="timeline-page">
    <header class="timeline-header">
      <div>
        <p class="eyebrow">内容概览</p>
        <h1>多轨内容概览</h1>
        <p class="overview-note">读取真实音频资产的起始位置和时长；当前页面只读，暂不支持拖动编辑。</p>
      </div>
      <div class="filters">
        <el-select v-model="projectId" filterable placeholder="项目" @change="loadChapters">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="chapterId" filterable placeholder="章节" @change="loadTimeline">
          <el-option v-for="chapter in chapters" :key="chapter.id" :label="chapter.title" :value="chapter.id" />
        </el-select>
      </div>
    </header>

    <el-alert
      v-if="timelineStatus !== 'ready'"
      class="timeline-status-alert"
      :title="timelineStatusLabel(timelineStatus)"
      :description="timelineStatusDescription(timelineStatus)"
      :type="timelineStatus === 'failed' ? 'error' : timelineStatus === 'stale' ? 'warning' : 'info'"
      show-icon
      :closable="false"
    />

    <section class="timeline-toolbar">
      <el-segmented v-model="zoom" :options="zoomOptions" />
      <el-tag effect="plain">{{ timeline.clip_count || 0 }} 条真实片段</el-tag>
      <el-tag type="success" effect="plain">{{ completedCount }} 条已生成</el-tag>
      <el-tag type="info" effect="plain">{{ formatDuration(timeline.duration_ms) }}</el-tag>
      <el-tag type="success" effect="plain">真实音频时长</el-tag>
      <el-button :loading="building" type="primary" plain @click="rebuildTimeline">构建/刷新概览</el-button>
      <el-button @click="openDubbingProject">打开配音工程</el-button>
    </section>

    <section class="timeline-surface">
      <article v-for="track in trackDefinitions" :key="track.key" class="track-row">
        <aside class="track-label">
          <el-icon><component :is="track.icon" /></el-icon>
          <strong>{{ track.label }}</strong>
          <span>{{ trackByType[track.key]?.clips?.length || 0 }} 个片段</span>
          <el-tag v-if="trackByType[track.key]?.status && trackByType[track.key].status !== 'ready'" size="small" effect="plain">
            {{ statusLabel(trackByType[track.key].status) }}
          </el-tag>
        </aside>
        <div class="clip-lane">
          <div
            v-for="clip in trackByType[track.key]?.clips || []"
            :key="clip.id"
            class="clip"
            :class="{ done: clip.line?.is_done === 1 || clip.line?.status === 'done', muted: clip.is_muted }"
            :style="{ width: clipWidth(clip) }"
            @click="openDubbingProject"
          >
            <strong>{{ clip.line?.scene_title || track.label }}</strong>
            <p>{{ clip.line?.text_content || clip.asset?.type || '音频片段' }}</p>
            <span>
              {{ formatDuration(clip.start_ms) }} 起 · {{ formatDuration(clip.duration_ms) }} · {{ clip.asset?.status === 'ready' ? '资产正常' : '缺少资产' }}
            </span>
          </div>
          <el-empty v-if="!(trackByType[track.key]?.clips?.length)" description="暂无真实音频片段" />
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Film, Headset, Microphone } from '@element-plus/icons-vue'
import { fetchProjects } from '../api/project'
import { getChaptersByProject } from '../api/chapter'
import { buildChapterTimeline, fetchChapterTimeline } from '../api/timeline'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const chapters = ref([])
const projectId = ref(null)
const chapterId = ref(null)
const timeline = ref({ status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 })
const zoom = ref('normal')
const building = ref(false)

const zoomOptions = [
  { label: '紧凑', value: 'compact' },
  { label: '标准', value: 'normal' },
  { label: '放大', value: 'wide' },
]

const trackDefinitions = [
  { key: 'voice', label: '人物声', icon: Microphone },
  { key: 'narration', label: '旁白', icon: Headset },
  { key: 'sfx', label: '音效', icon: Bell },
  { key: 'bgm', label: 'BGM', icon: Film },
]

const timelineStatus = computed(() => timeline.value.status || 'not_built')
const trackByType = computed(() => Object.fromEntries((timeline.value.tracks || []).map((track) => [track.track_type, track])))
const completedCount = computed(() => (timeline.value.tracks || []).flatMap((track) => track.clips || []).filter((clip) => clip.line?.is_done === 1 || clip.line?.status === 'done').length)

onMounted(async () => {
  projects.value = await fetchProjects()
  if (projects.value.length) {
    projectId.value = selectProjectFromQuery() || projects.value[0].id
    await loadChapters()
  }
})

watch(() => route.query.project_id, async () => {
  const selected = selectProjectFromQuery()
  if (selected && selected !== projectId.value) {
    projectId.value = selected
    await loadChapters()
  }
})

function selectProjectFromQuery() {
  const id = Number(route.query.project_id)
  if (!id) return null
  return projects.value.some((project) => project.id === id) ? id : null
}

async function loadChapters() {
  chapters.value = []
  chapterId.value = null
  timeline.value = { status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 }
  if (!projectId.value) return
  const response = await getChaptersByProject(projectId.value)
  chapters.value = response.code === 200 ? response.data : []
  if (chapters.value.length) {
    chapterId.value = chapters.value[0].id
    await loadTimeline()
  }
}

async function loadTimeline() {
  if (!projectId.value || !chapterId.value) return
  const response = await fetchChapterTimeline(projectId.value, chapterId.value)
  if (response.code !== 200) {
    ElMessage.error(response.message || '读取真实时间线失败')
    return
  }
  timeline.value = response.data || { status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 }
  if (timeline.value.status === 'not_built') await rebuildTimeline(true)
}

async function rebuildTimeline(silent = false) {
  if (!projectId.value || !chapterId.value || building.value) return
  building.value = true
  try {
    const response = await buildChapterTimeline(projectId.value, chapterId.value, { force: true })
    if (response.code !== 200) throw new Error(response.message || '构建失败')
    timeline.value = response.data
    if (!silent) ElMessage.success('真实音频内容概览已刷新')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '构建真实时间线失败')
  } finally {
    building.value = false
  }
}

function statusLabel(status) {
  return {
    not_built: '尚未构建',
    stale: '已过期',
    failed: '构建失败',
    missing_audio: '缺少音频',
    building: '构建中',
    ready: '已就绪',
  }[status] || status
}

function timelineStatusLabel(status) {
  return `内容概览${statusLabel(status)}`
}

function timelineStatusDescription(status) {
  return {
    not_built: '首次打开会根据当前采用的音频版本自动构建。',
    stale: '台词或音频版本发生变化，请刷新概览。',
    failed: '构建失败，请检查音频资产后重试。',
    missing_audio: '部分台词没有可用音频，已生成的片段仍可查看。',
    building: '正在登记音频资产并计算真实时长。',
  }[status] || '当前没有需要处理的状态。'
}

function formatDuration(milliseconds = 0) {
  const totalSeconds = Math.max(0, Number(milliseconds || 0)) / 1000
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)} 秒`
  return `${Math.floor(totalSeconds / 60)}分${Math.floor(totalSeconds % 60)}秒`
}

function clipWidth(clip) {
  const multiplier = { compact: 8, normal: 13, wide: 20 }[zoom.value] || 13
  const seconds = Math.max(0.1, Number(clip.duration_ms || 0) / 1000)
  return `${Math.min(720, Math.max(96, seconds * multiplier))}px`
}

function openDubbingProject() {
  if (!projectId.value) {
    ElMessage.warning('请选择项目')
    return
  }
  router.push(`/projects/${projectId.value}/dubbing`)
}
</script>

<style scoped>
.timeline-page { min-height: 100%; }
.timeline-header, .timeline-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.timeline-header { margin-bottom: 14px; }
.timeline-header h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
.overview-note { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.eyebrow { margin: 0 0 4px; color: var(--el-text-color-secondary); font-size: 12px; text-transform: uppercase; }
.filters, .timeline-toolbar { display: flex; gap: 10px; }
.filters .el-select { width: 220px; }
.timeline-status-alert { margin-bottom: 14px; }
.timeline-toolbar { justify-content: flex-start; padding: 12px; margin-bottom: 14px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.timeline-surface { display: grid; gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.track-row { display: grid; grid-template-columns: 160px minmax(760px, 1fr); min-height: 118px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); overflow: hidden; }
.track-label { display: grid; align-content: center; gap: 6px; padding: 14px; border-right: 1px solid var(--el-border-color-light); background: var(--el-fill-color-light); }
.track-label strong, .track-label span { display: block; }
.track-label span { color: var(--el-text-color-secondary); font-size: 12px; }
.clip-lane { display: flex; align-items: center; gap: 10px; min-width: 0; overflow-x: auto; padding: 14px; }
.clip { flex: 0 0 auto; display: grid; align-content: start; gap: 5px; min-height: 76px; padding: 10px; border: 1px solid color-mix(in srgb, var(--el-color-primary) 36%, var(--el-border-color)); border-radius: 8px; background: color-mix(in srgb, var(--el-color-primary-light-9) 82%, var(--el-bg-color)); cursor: pointer; }
.clip.done { border-color: color-mix(in srgb, var(--el-color-success) 45%, var(--el-border-color)); background: color-mix(in srgb, var(--el-color-success-light-9) 80%, var(--el-bg-color)); }
.clip.muted { opacity: .6; }
.clip p { max-width: 420px; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clip span { color: var(--el-text-color-secondary); font-size: 11px; }
@media (max-width: 900px) { .timeline-header { align-items: flex-start; flex-direction: column; } .filters { width: 100%; } .filters .el-select { flex: 1; width: auto; } .timeline-toolbar { flex-wrap: wrap; } }
</style>
