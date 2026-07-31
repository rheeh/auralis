<template>
  <div class="timeline-page">
    <header class="timeline-header">
      <div>
        <p class="eyebrow">后期制作</p>
        <h1>多轨时间线</h1>
        <p class="overview-note">按真实音频位置编排并渲染章节成片。</p>
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
      <el-button :loading="building" type="primary" plain :icon="Refresh" @click="rebuildTimeline">构建/刷新时间线</el-button>
      <el-button
        type="success"
        :icon="VideoPlay"
        :loading="rendering"
        :disabled="!canRender"
        @click="renderTimeline"
      >渲染成片</el-button>
      <el-button @click="openDubbingProject">打开配音工程</el-button>
    </section>

    <section v-if="renderResult" class="render-result">
      <div>
        <strong>时间线成片</strong>
        <span>{{ formatDuration(renderResult.duration_ms) }} · {{ renderResult.rendered_clip_count }} 个有效片段</span>
      </div>
      <audio controls preload="metadata" :src="renderAudioUrl" />
      <el-button :icon="Download" @click="downloadRender">下载 WAV</el-button>
    </section>

    <section class="timeline-surface">
      <div class="timeline-scroll">
        <div class="timeline-ruler">
          <aside class="track-label"><strong>统一时间轴</strong><span>{{ formatDuration(timeline.duration_ms) }}</span></aside>
          <div class="timeline-canvas" :style="canvasStyle">
            <span v-for="tick in timelineTicks" :key="tick.ms" class="time-tick" :style="tickStyle(tick)">{{ tick.label }}</span>
          </div>
        </div>
        <article v-for="track in trackDefinitions" :key="track.key" class="track-row">
          <aside class="track-label">
            <el-icon><component :is="track.icon" /></el-icon>
            <strong>{{ track.label }}</strong>
            <span>{{ trackByType[track.key]?.clips?.length || 0 }} 个片段</span>
            <el-tag v-if="trackByType[track.key]?.status && trackByType[track.key].status !== 'ready'" size="small" effect="plain">
              {{ statusLabel(trackByType[track.key].status) }}
            </el-tag>
          </aside>
          <div class="timeline-canvas" :style="canvasStyle">
            <span v-for="tick in timelineTicks" :key="`grid-${track.key}-${tick.ms}`" class="timeline-grid-line" :style="tickStyle(tick)" />
            <div
              v-for="clip in trackByType[track.key]?.clips || []"
              :key="clip.id"
              class="clip"
              :class="{ done: clip.line?.is_done === 1 || clip.line?.status === 'done', muted: clip.is_muted }"
              :style="clipStyle(clip)"
              @click="openClipEditor(clip)"
            >
              <strong>{{ clip.line?.scene_title || track.label }}</strong>
              <p>{{ clip.line?.text_content || clip.asset?.type || '音频片段' }}</p>
              <span>
                {{ formatDuration(clip.start_ms) }} 起 · {{ formatDuration(clip.duration_ms) }} · {{ formatVolume(clip.volume_db) }}
              </span>
            </div>
            <span v-if="!(trackByType[track.key]?.clips?.length)" class="empty-lane">暂无真实音频片段</span>
          </div>
        </article>
      </div>
    </section>

    <el-dialog v-model="clipEditorVisible" title="编辑时间线片段" width="min(520px, 92vw)" destroy-on-close>
      <el-form v-if="clipForm" label-position="top">
        <div class="clip-form-grid">
          <el-form-item label="开始时间（毫秒）">
            <el-input-number v-model="clipForm.start_ms" :min="0" :step="100" controls-position="right" />
          </el-form-item>
          <el-form-item label="片段长度（毫秒）">
            <el-input-number v-model="clipForm.duration_ms" :min="1" :max="clipForm.max_duration_ms" :step="100" controls-position="right" />
          </el-form-item>
          <el-form-item label="音量（dB）">
            <el-input-number v-model="clipForm.volume_db" :min="-60" :max="12" :step="1" controls-position="right" />
          </el-form-item>
          <el-form-item label="静音">
            <el-switch v-model="clipForm.is_muted" />
          </el-form-item>
          <el-form-item label="淡入（毫秒）">
            <el-input-number v-model="clipForm.fade_in_ms" :min="0" :max="clipForm.duration_ms" :step="100" controls-position="right" />
          </el-form-item>
          <el-form-item label="淡出（毫秒）">
            <el-input-number v-model="clipForm.fade_out_ms" :min="0" :max="clipForm.duration_ms" :step="100" controls-position="right" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="clipEditorVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" :loading="savingClip" @click="saveClip">保存片段</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Check, Download, Film, Headset, Microphone, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { fetchProjects } from '../api/project'
import { getChaptersByProject } from '../api/chapter'
import {
  buildChapterTimeline,
  fetchChapterTimeline,
  getTimelineRenderAudioUrl,
  renderChapterTimeline,
  updateTimelineClip,
} from '../api/timeline'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const chapters = ref([])
const projectId = ref(null)
const chapterId = ref(null)
const timeline = ref({ status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 })
const zoom = ref('normal')
const building = ref(false)
const rendering = ref(false)
const renderResult = ref(null)
const renderAudioUrl = ref('')
const clipEditorVisible = ref(false)
const clipForm = ref(null)
const savingClip = ref(false)

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
const canRender = computed(() => timelineStatus.value === 'ready' && Number(timeline.value.clip_count || 0) > 0)
const trackByType = computed(() => Object.fromEntries((timeline.value.tracks || []).map((track) => [track.track_type, track])))
const completedCount = computed(() => (timeline.value.tracks || []).flatMap((track) => track.clips || []).filter((clip) => clip.line?.is_done === 1 || clip.line?.status === 'done').length)
const pixelsPerSecond = computed(() => ({ compact: 40, normal: 80, wide: 120 }[zoom.value] || 80))
const timelineDurationMs = computed(() => Math.max(Number(timeline.value.duration_ms || 0), 10000))
const timelineCanvasWidth = computed(() => `${Math.max(960, timelineDurationMs.value / 1000 * pixelsPerSecond.value + 24)}px`)
const canvasStyle = computed(() => ({ width: timelineCanvasWidth.value, '--grid-size': `${pixelsPerSecond.value}px` }))
const timelineTicks = computed(() => {
  const duration = timelineDurationMs.value
  const step = duration <= 30000 ? 5000 : duration <= 120000 ? 10000 : 30000
  const ticks = []
  for (let ms = 0; ms <= duration; ms += step) ticks.push({ ms, label: `${Math.round(ms / 1000)}s` })
  if (ticks.at(-1)?.ms !== duration) ticks.push({ ms: duration, label: `${Math.round(duration / 1000)}s` })
  return ticks
})

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
  renderResult.value = null
  renderAudioUrl.value = ''
  if (timeline.value.status === 'not_built') await rebuildTimeline(true)
}

async function rebuildTimeline(silent = false) {
  if (!projectId.value || !chapterId.value || building.value) return
  building.value = true
  try {
    const response = await buildChapterTimeline(projectId.value, chapterId.value, { force: true })
    if (response.code !== 200) throw new Error(response.message || '构建失败')
    timeline.value = response.data
    renderResult.value = null
    renderAudioUrl.value = ''
    if (!silent) ElMessage.success('真实音频时间线已刷新')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '构建真实时间线失败')
  } finally {
    building.value = false
  }
}

function openClipEditor(clip) {
  clipForm.value = {
    id: clip.id,
    start_ms: Number(clip.start_ms || 0),
    duration_ms: Number(clip.duration_ms || 1),
    max_duration_ms: Number(clip.asset?.duration_ms || clip.duration_ms || 1),
    volume_db: Number(clip.volume_db || 0),
    fade_in_ms: Number(clip.fade_in_ms || 0),
    fade_out_ms: Number(clip.fade_out_ms || 0),
    is_muted: Boolean(clip.is_muted),
  }
  clipEditorVisible.value = true
}

async function saveClip() {
  if (!clipForm.value || savingClip.value) return
  if (clipForm.value.fade_in_ms + clipForm.value.fade_out_ms > clipForm.value.duration_ms) {
    ElMessage.warning('淡入和淡出总时长不能超过片段长度')
    return
  }
  savingClip.value = true
  try {
    const { id, max_duration_ms, ...payload } = clipForm.value
    const response = await updateTimelineClip(projectId.value, chapterId.value, id, payload)
    if (response.code !== 200) throw new Error(response.message || '保存失败')
    timeline.value = response.data
    renderResult.value = null
    renderAudioUrl.value = ''
    clipEditorVisible.value = false
    ElMessage.success('时间线片段已更新')
  } catch (error) {
    ElMessage.error(apiError(error, '保存片段失败'))
  } finally {
    savingClip.value = false
  }
}

async function renderTimeline() {
  if (!canRender.value || rendering.value) return
  rendering.value = true
  try {
    const response = await renderChapterTimeline(projectId.value, chapterId.value)
    if (response.code !== 200) throw new Error(response.message || '渲染失败')
    renderResult.value = response.data
    renderAudioUrl.value = getTimelineRenderAudioUrl(projectId.value, chapterId.value, Date.now())
    ElMessage.success('时间线混音成片已生成')
  } catch (error) {
    ElMessage.error(apiError(error, '时间线渲染失败'))
  } finally {
    rendering.value = false
  }
}

async function downloadRender() {
  if (!renderResult.value || !renderAudioUrl.value) return
  try {
    const response = await fetch(renderAudioUrl.value)
    if (!response.ok) throw new Error('读取成片失败')
    const bytes = new Uint8Array(await response.arrayBuffer())
    if (window.native?.saveFile && window.native?.writeFile) {
      const savePath = await window.native.saveFile({
        title: '保存时间线成片',
        defaultPath: renderResult.value.file_name || 'timeline_mix.wav',
        filters: [{ name: 'WAV 音频', extensions: ['wav'] }],
      })
      if (!savePath) return
      const result = await window.native.writeFile(savePath, bytes)
      if (!result?.success) throw new Error(result?.error || '保存失败')
    } else {
      const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
      const link = document.createElement('a')
      link.href = url
      link.download = renderResult.value.file_name || 'timeline_mix.wav'
      link.click()
      URL.revokeObjectURL(url)
    }
    ElMessage.success('成片已保存')
  } catch (error) {
    ElMessage.error(error?.message || '下载成片失败')
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
  return `时间线${statusLabel(status)}`
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

function formatVolume(value = 0) {
  const number = Number(value || 0)
  return `${number > 0 ? '+' : ''}${number.toFixed(1)} dB`
}

function apiError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

function tickStyle(tick) {
  return { left: `${tick.ms / 1000 * pixelsPerSecond.value}px` }
}

function clipStyle(clip) {
  const left = Math.max(0, Number(clip.start_ms || 0)) / 1000 * pixelsPerSecond.value
  const width = Math.max(8, Number(clip.duration_ms || 0) / 1000 * pixelsPerSecond.value)
  return { left: `${left}px`, width: `${width}px` }
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
.render-result { display: grid; grid-template-columns: minmax(160px, 240px) minmax(280px, 1fr) auto; gap: 14px; align-items: center; padding: 10px 12px; margin-bottom: 14px; border-left: 3px solid var(--el-color-success); background: var(--el-fill-color-extra-light); }
.render-result strong, .render-result span { display: block; }
.render-result span { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 11px; }
.render-result audio { width: 100%; height: 36px; }
.timeline-surface { overflow-x: auto; padding-bottom: 8px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.timeline-scroll { min-width: max-content; }
.timeline-ruler, .track-row { display: grid; grid-template-columns: 160px auto; }
.timeline-ruler { min-height: 42px; border-bottom: 1px solid var(--el-border-color-light); }
.track-row { min-height: 118px; border-bottom: 1px solid var(--el-border-color-light); }
.track-row:last-child { border-bottom: 0; }
.track-label { display: grid; align-content: center; gap: 6px; padding: 14px; border-right: 1px solid var(--el-border-color-light); background: var(--el-fill-color-light); }
.track-label strong, .track-label span { display: block; }
.track-label span { color: var(--el-text-color-secondary); font-size: 12px; }
.timeline-canvas { position: relative; min-height: 100%; background-image: linear-gradient(to right, color-mix(in srgb, var(--el-border-color-light) 62%, transparent) 1px, transparent 1px); background-size: var(--grid-size, 80px) 100%; }
.timeline-ruler .timeline-canvas { min-height: 42px; }
.time-tick { position: absolute; top: 9px; z-index: 2; color: var(--el-text-color-secondary); font-size: 11px; transform: translateX(-50%); }
.timeline-grid-line { position: absolute; top: 0; bottom: 0; border-left: 1px dashed color-mix(in srgb, var(--el-border-color) 70%, transparent); pointer-events: none; }
.clip { position: absolute; top: 14px; display: grid; align-content: start; gap: 5px; min-height: 76px; padding: 10px; overflow: hidden; border: 1px solid color-mix(in srgb, var(--el-color-primary) 36%, var(--el-border-color)); border-radius: 8px; background: color-mix(in srgb, var(--el-color-primary-light-9) 82%, var(--el-bg-color)); cursor: pointer; }
.clip.done { border-color: color-mix(in srgb, var(--el-color-success) 45%, var(--el-border-color)); background: color-mix(in srgb, var(--el-color-success-light-9) 80%, var(--el-bg-color)); }
.clip.muted { opacity: .6; }
.clip p { max-width: 420px; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clip span { color: var(--el-text-color-secondary); font-size: 11px; }
.empty-lane { position: absolute; top: 50%; left: 14px; color: var(--el-text-color-secondary); font-size: 12px; transform: translateY(-50%); }
.clip-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.clip-form-grid .el-input-number { width: 100%; }
@media (max-width: 900px) { .timeline-header { align-items: flex-start; flex-direction: column; } .filters { width: 100%; } .filters .el-select { flex: 1; width: auto; } .timeline-toolbar { flex-wrap: wrap; } .render-result { grid-template-columns: 1fr auto; } .render-result audio { grid-column: 1 / -1; grid-row: 2; } }
@media (max-width: 560px) { .filters { flex-direction: column; } .filters .el-select { width: 100%; } .render-result, .clip-form-grid { grid-template-columns: 1fr; } .render-result audio { grid-column: 1; grid-row: auto; } }
</style>
