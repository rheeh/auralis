<template>
  <div class="timeline-page">
    <header class="timeline-header">
      <div>
        <p class="eyebrow">后期制作</p>
        <h2>{{ exportOnly ? '导出章节成片' : '多轨时间线' }}</h2>
        <p class="overview-note">按真实音频位置编排并渲染章节成片。</p>
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
      <el-segmented v-if="!exportOnly" v-model="zoom" :options="zoomOptions" />
      <el-switch v-if="!exportOnly" v-model="snapEnabled" active-text="边缘吸附" />
      <el-tag effect="plain">{{ timeline.clip_count || 0 }} 条真实片段</el-tag>
      <el-tag type="success" effect="plain">{{ completedCount }} 条已生成</el-tag>
      <el-tag type="info" effect="plain">{{ formatDuration(timeline.duration_ms) }}</el-tag>
      <el-tag type="success" effect="plain">真实音频时长</el-tag>
      <el-button :loading="building" type="primary" plain :icon="Refresh" :disabled="rendering || savingClip" @click="rebuildTimeline(false)">构建/刷新时间线</el-button>
      <el-button
        type="success"
        :icon="VideoPlay"
        :loading="rendering"
        :disabled="!canRender"
        @click="renderTimeline"
      >渲染成片</el-button>
      <el-button @click="openDubbingProject">返回对应台词</el-button>
      <el-button v-if="!exportOnly" :icon="Bell" :disabled="!chapterId" @click="openSoundLibrary()">快捷加音效</el-button>
      <el-button v-if="!exportOnly" :disabled="!chapterLines.length" @click="openSoundLibrary(selectedLineId || materialLines[0]?.id, 'recommendations')">标签匹配音效</el-button>
    </section>

    <details v-if="timeline.missing_lines?.length" class="missing-lines">
      <summary>{{ timeline.missing_lines.length }} 条尚未进入时间线 · 渲染时跳过，点击查看</summary>
      <ul><li v-for="line in timeline.missing_lines" :key="line.line_id"><el-button text size="small" @click="openDubbingProject(line.line_id)">第 {{ line.line_order }} 行 · {{ trackDefinitions.find(track => track.key === line.track)?.label }} · {{ line.text_content }}</el-button></li></ul>
    </details>
    <SceneIllustration v-if="renderResult && visualScenes.length" :scenes="visualScenes" :seconds="renderTime" @seek="seekScene" />
    <section v-if="renderResult" class="render-result">
      <div>
        <strong>{{ renderResult.is_partial ? '阶段成片（部分音频）' : '时间线成片' }}</strong>
        <span>{{ formatDuration(renderResult.duration_ms) }} · {{ renderResult.rendered_clip_count }} 个有效片段</span>
      </div>
      <audio ref="renderPlayer" aria-label="播放时间线成片" controls preload="metadata" :src="renderAudioUrl" @timeupdate="renderTime = $event.target.currentTime" @seeking="renderTime = $event.target.currentTime" @loadedmetadata="renderTime = $event.target.currentTime" />
      <el-button :icon="Download" @click="downloadRender">下载 WAV</el-button>
    </section>

    <p v-if="!exportOnly" class="overview-note">拖动片段移动位置，拖动左右边界调整长度；背景音乐和音效超出原长会循环。吸附时显示竖线，按住 Alt 可临时关闭；点击片段可快捷对齐。</p>
    <TimelineTracks v-if="!exportOnly" :snap-marker-ms="snapMarkerMs" :tracks="displayTracks" :duration-ms="displayDurationMs" :pixels-per-second="pixelsPerSecond" :selected-line-id="selectedLineId" editable @select="handleClipClick" @interact="startClipInteraction" />

    <el-dialog v-model="soundLibraryVisible" title="给场景加入音效" width="min(1120px, 94vw)" destroy-on-close>
      <SoundLibraryPanel
        :chapter-id="chapterId"
        :lines="chapterLines"
        :material-lines="materialLines"
        :target-line-id="soundTargetLineId"
        :initial-view="soundLibraryView"
        @inserted="loadTimeline"
        @bound="loadTimeline"
      />
    </el-dialog>

    <el-dialog v-model="clipEditorVisible" title="编辑时间线片段" width="min(520px, 92vw)" destroy-on-close @close="stopClipPreview">
      <el-form v-if="clipForm" label-position="top">
        <p class="overview-note">源音频 {{ formatDuration(clipForm.source_duration_ms) }}<span v-if="isMaterialClip(clipForm)"> · 延长超出原长时循环播放</span></p>
        <div v-if="isMaterialClip(clipForm)" class="speed-tools">
          <el-form-item label="播放倍速"><el-input-number :model-value="clipForm.playback_rate" :min="0.5" :max="2" :step="0.05" :precision="2" controls-position="right" aria-label="音效播放倍速" @change="setPlaybackRate" /></el-form-item>
          <div><el-button v-for="rate in [0.5,0.75,1,1.25,1.5,2]" :key="rate" size="small" :type="clipForm.playback_rate === rate ? 'primary' : 'default'" @click="setPlaybackRate(rate)">{{ rate }}×</el-button></div>
          <small>0.5× 为半速，时长约翻倍；保持音调，起点不动。当前单次播放 {{ formatDuration(playableSourceDuration(clipForm)) }}。</small>
          <audio v-if="clipForm.line_id" ref="clipPreview" controls preload="none" :src="getLineAudioUrl(clipForm.line_id)" aria-label="音效倍速试听" @loadedmetadata="applyPreviewRate" @play="applyPreviewRate" />
          <small>试听当前素材的倍速效果；片段裁剪、循环和淡入淡出在渲染后生效。</small>
        </div>
        <div class="alignment-tools">
          <el-select v-model="alignmentTargetId" filterable aria-label="对齐参考片段" placeholder="选择要对齐的另一段音轨">
            <el-option v-for="clip in alignmentTargets" :key="clip.id" :value="clip.id" :label="`${trackDefinitions.find(track => track.key === clip.track_type)?.label} · 第${clip.line?.line_order || '?'}行 · ${(clip.line?.text_content || '').slice(0,30)}`" />
          </el-select>
          <div><el-button size="small" :disabled="!alignmentTargetId" @click="applyAlignment('start')">起点对齐</el-button><el-button size="small" :disabled="!alignmentTargetId" @click="applyAlignment('end')">终点对齐</el-button><el-button size="small" :disabled="!alignmentTargetId" @click="applyAlignment('after')">接在后面</el-button><el-button v-if="isMaterialClip(clipForm)" size="small" :disabled="!alignmentTargetId" @click="applyAlignment('span')">覆盖参考片段</el-button></div>
          <div v-if="isMaterialClip(clipForm)"><el-button size="small" @click="coverSpeech">铺满人声</el-button><el-button size="small" @click="extendMaterial(5000)">延长 5 秒</el-button><el-button size="small" @click="extendMaterial(10000)">延长 10 秒</el-button><el-button size="small" @click="setClipDuration(playableSourceDuration(clipForm))">恢复原长</el-button></div>
          <small>快捷调整后，点击「保存片段」生效。</small>
        </div>
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
        <el-button type="primary" plain @click="openSoundLibrary(clipForm?.line_id, 'recommendations')">标签匹配音效</el-button>
        <el-button :icon="Bell" @click="openSoundLibrary(clipForm?.line_id)">在这句附近加音效</el-button>
        <el-button @click="openDubbingProject(clipForm?.line_id)">查看对应台词</el-button>
        <el-button @click="clipEditorVisible = false">取消</el-button>
        <el-button type="primary" :icon="Check" :loading="savingClip" @click="saveClip">保存片段</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { alignClip, changeClipRate, playableSourceDuration, dragClip, durationLimit, isMaterialClip, MAX_TIMELINE_MS } from '../../utils/timelineEditing'
import { computed, nextTick, ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Check, Download, Film, Headset, Microphone, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { getLinesByChapter, getLineAudioUrl } from '../../api/line'
import TimelineTracks from './TimelineTracks.vue'
import SceneIllustration from './SceneIllustration.vue'
import { nativeSceneSchedule } from '../../demo/sceneImages'
import SoundLibraryPanel from '../SoundLibraryPanel.vue'
import {
  buildChapterTimeline,
  fetchChapterTimeline,
  fetchLatestTimelineRender,
  getTimelineRenderAudioUrl,
  renderChapterTimeline,
  updateTimelineClip,
} from '../../api/timeline'

const snapEnabled = ref(true), snapMarkerMs = ref(null), alignmentTargetId = ref(null)
const allClips = computed(() => (timeline.value.tracks || []).flatMap(track => track.clips || []))
const displayDurationMs = computed(() => Math.max(timeline.value.duration_ms || 0, ...allClips.value.map(clip => clip.start_ms + clip.duration_ms)) + (clipInteraction.value ? 5000 : 0))
const alignmentTargets = computed(() => allClips.value.filter(clip => clip.id !== clipForm.value?.id))
const props=defineProps({projectId:{type:Number,required:true},chapterId:{type:Number,required:true},exportOnly:Boolean,selectedLineId:[Number,String]})
const emit=defineEmits(['focus-line'])
const projectId=toRef(props,'projectId'),chapterId=toRef(props,'chapterId')
const timeline = ref({ status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 })
const zoom = ref('normal')
const building = ref(false)
const rendering = ref(false)
const renderResult = ref(null)
const renderAudioUrl = ref('')
const renderPlayer = ref(null), renderTime = ref(0)
const visualScenes = computed(() => nativeSceneSchedule(timeline.value.tracks || []))
function seekScene(seconds) { if (renderPlayer.value) { renderPlayer.value.currentTime = seconds; renderTime.value = seconds } }
const clipEditorVisible = ref(false)
const clipForm = ref(null)
const clipPreview = ref(null)
const savingClip = ref(false)
const clipInteraction = ref(null)
const suppressClipClick = ref(false)
const soundLibraryVisible = ref(false)
const soundTargetLineId = ref(null)
const soundLibraryView = ref('library')
const chapterLines = ref([])
const materialLines = computed(() => chapterLines.value.filter((line) => ['sfx', 'bgm'].includes(line.track || line.line_type)))

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
const canRender = computed(() => !building.value && !savingClip.value && (Number(timeline.value.clip_count || 0) > 0 || chapterLines.value.some(line => line.is_done === 1 || line.status === 'done')))
const trackByType = computed(() => Object.fromEntries((timeline.value.tracks || []).map((track) => [track.track_type, track])))
const completedCount = computed(() => (timeline.value.tracks || []).flatMap((track) => track.clips || []).filter((clip) => clip.line?.is_done === 1 || clip.line?.status === 'done').length)
const pixelsPerSecond = computed(() => ({ compact: 40, normal: 80, wide: 120 }[zoom.value] || 80))
const displayTracks=computed(()=>trackDefinitions.map(track=>({...track,...trackByType.value[track.key]})))
watch(()=>[props.projectId,props.chapterId],loadTimeline,{immediate:true})
watch(()=>props.selectedLineId,focusSelectedLine)
async function focusSelectedLine(){await nextTick();document.querySelector(`[data-clip-line-id="${Number(props.selectedLineId)}"]`)?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'})}

async function loadTimeline() {
  if (!projectId.value || !chapterId.value) return
  try {
    const [response, linesResponse] = await Promise.all([
      fetchChapterTimeline(projectId.value, chapterId.value),
      getLinesByChapter(chapterId.value),
    ])
    if (linesResponse.code === 200) chapterLines.value = linesResponse.data || []
    if (response.code !== 200) {
      ElMessage.error(response.message || '读取真实时间线失败')
      return
    }
    timeline.value = response.data || { status: 'not_built', tracks: [], clip_count: 0, duration_ms: 0 }
    renderResult.value = null
    renderAudioUrl.value = ''
    if (timeline.value.status === 'not_built') await rebuildTimeline(true)
    await focusSelectedLine()
    if (['ready', 'missing_audio'].includes(timeline.value.status) && timeline.value.clip_count > 0) {
      const requestedProject = projectId.value, requestedChapter = chapterId.value
      try {
        const latest = await fetchLatestTimelineRender(requestedProject, requestedChapter)
        if (latest.code === 200 && requestedProject === projectId.value && requestedChapter === chapterId.value) {
          renderResult.value = latest.data
          renderAudioUrl.value = getTimelineRenderAudioUrl(requestedProject, requestedChapter, Date.now())
        }
      } catch (error) {
        if (![404, 409].includes(error?.response?.status)) ElMessage.warning('已保存成片暂时无法读取，请稍后刷新。')
      }
    }
  } catch (error) { ElMessage.error(apiError(error, '读取时间线失败，请重试')) }
}

function openSoundLibrary(lineId = null, view = 'library') {
  soundLibraryView.value = view
  soundTargetLineId.value = lineId || soundTargetLineId.value || chapterLines.value[0]?.id || null
  clipEditorVisible.value = false
  soundLibraryVisible.value = true
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
    if (!['ready', 'missing_audio'].includes(timeline.value.status)) throw new Error('时间线未能刷新，请检查音频后重试')
    if (!silent) ElMessage.success(timeline.value.missing_line_count ? `已刷新，${timeline.value.missing_line_count} 条缺少音频，可先渲染已有片段` : '时间线已刷新，手动调整已保留')
    return true
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '构建真实时间线失败')
    return false
  } finally {
    building.value = false
  }
}

function openClipEditor(clip) {
  clipForm.value = {
    id: clip.id,
    line_id: clip.line_id,
    start_ms: Number(clip.start_ms || 0),
    duration_ms: Number(clip.duration_ms || 1),
    track_type: clip.track_type,
    playback_rate: clip.playback_rate || 1,
    source_duration_ms: Number(clip.asset?.duration_ms || clip.duration_ms || 1),
    max_duration_ms: durationLimit(clip),
    volume_db: Number(clip.volume_db || 0),
    fade_in_ms: Number(clip.fade_in_ms || 0),
    fade_out_ms: Number(clip.fade_out_ms || 0),
    is_muted: Boolean(clip.is_muted),
  }
  alignmentTargetId.value = null
  clipEditorVisible.value = true
}

function setPlaybackRate(rate) {
  if (!rate || !clipForm.value) return
  try {
    Object.assign(clipForm.value, changeClipRate(clipForm.value, Number(rate)))
    applyPreviewRate()
  } catch (error) { ElMessage.warning(error.message) }
}
function applyPreviewRate() {
  if (!clipPreview.value || !clipForm.value) return
  clipPreview.value.preservesPitch = true
  clipPreview.value.playbackRate = clipForm.value.playback_rate || 1
}
function stopClipPreview() { clipPreview.value?.pause() }

function applyAlignment(mode) {
  const target = alignmentTargets.value.find(clip => clip.id === alignmentTargetId.value)
  if (!target) return
  try { Object.assign(clipForm.value, alignClip(clipForm.value, target, mode)) }
  catch (error) { ElMessage.warning(error.message) }
}
function setClipDuration(value) {
  const form = clipForm.value
  form.duration_ms = Math.min(Math.max(1, value), form.max_duration_ms, MAX_TIMELINE_MS - form.start_ms)
  form.fade_in_ms = Math.min(form.fade_in_ms, form.duration_ms)
  form.fade_out_ms = Math.min(form.fade_out_ms, form.duration_ms - form.fade_in_ms)
}
function extendMaterial(ms) { setClipDuration(clipForm.value.duration_ms + ms) }
function coverSpeech() {
  const speech = allClips.value.filter(clip => ['voice', 'narration'].includes(clip.track_type) && !clip.is_muted)
  if (!speech.length) return ElMessage.warning('还没有可用的人声音轨')
  clipForm.value.start_ms = Math.min(...speech.map(clip => clip.start_ms))
  setClipDuration(Math.max(...speech.map(clip => clip.start_ms + clip.duration_ms)) - clipForm.value.start_ms)
}

function handleClipClick(clip) {
  if (suppressClipClick.value) {
    suppressClipClick.value = false
    return
  }
  openClipEditor(clip)
}

function startClipInteraction(event, clip, mode) {
  if (event.button !== 0 || savingClip.value || building.value || rendering.value) return
  event.preventDefault()
  const target = event.currentTarget
  target.setPointerCapture?.(event.pointerId)
  clipInteraction.value = {
    clip,
    mode,
    pointerId: event.pointerId,
    originX: event.clientX,
    originStartMs: Number(clip.start_ms || 0),
    originDurationMs: Number(clip.duration_ms || 1),
    origin: {...clip},
    surface: target.closest('.timeline-surface'),
    originScroll: target.closest('.timeline-surface')?.scrollLeft || 0,
    moved: false,
  }
  target.addEventListener('pointermove', updateClipInteraction)
  target.addEventListener('pointerup', finishClipInteraction, { once: true })
  target.addEventListener('pointercancel', cancelClipInteraction, { once: true })
}

function updateClipInteraction(event) {
  const interaction = clipInteraction.value
  if (!interaction || event.pointerId !== interaction.pointerId) return
  const surface = interaction.surface
  if (surface) {
    const bounds = surface.getBoundingClientRect()
    if (event.clientX > bounds.right - 30) surface.scrollLeft += 24
    else if (event.clientX < bounds.left + 185) surface.scrollLeft -= 24
  }
  const deltaMs = (event.clientX - interaction.originX + (surface?.scrollLeft || 0) - interaction.originScroll) / pixelsPerSecond.value * 1000
  if (Math.abs(event.clientX - interaction.originX) >= 3) interaction.moved = true
  if (!interaction.moved) return
  const {guide, ...values} = dragClip(interaction.origin, interaction.mode, deltaMs, allClips.value, snapEnabled.value && !event.altKey, 8 / pixelsPerSecond.value * 1000)
  Object.assign(interaction.clip, values)
  snapMarkerMs.value = guide
}

async function finishClipInteraction(event) {
  const interaction = clipInteraction.value
  event.currentTarget?.removeEventListener('pointermove', updateClipInteraction)
  event.currentTarget?.removeEventListener('pointercancel', cancelClipInteraction)
  clipInteraction.value = null
  snapMarkerMs.value = null
  if (!interaction) return
  if (!interaction.moved) return
  suppressClipClick.value = true
  setTimeout(() => { suppressClipClick.value = false }, 0)
  await persistClipInteraction(interaction.clip)
}

function cancelClipInteraction(event) {
  event.currentTarget?.removeEventListener('pointermove', updateClipInteraction)
  event.currentTarget?.removeEventListener('pointerup', finishClipInteraction)
  if (clipInteraction.value) Object.assign(clipInteraction.value.clip, clipInteraction.value.origin)
  clipInteraction.value = null
  snapMarkerMs.value = null
}

async function persistClipInteraction(clip) {
  savingClip.value = true
  try {
    const response = await updateTimelineClip(projectId.value, chapterId.value, clip.id, {
      start_ms: Math.round(Number(clip.start_ms || 0)),
      duration_ms: Math.round(Number(clip.duration_ms || 1)),
      fade_in_ms: clip.fade_in_ms,
      fade_out_ms: clip.fade_out_ms,
    })
    if (response.code !== 200) throw new Error(response.message || '保存失败')
    timeline.value = response.data
    renderResult.value = null
    renderAudioUrl.value = ''
    ElMessage.success(isMaterialClip(clip) && clip.duration_ms > playableSourceDuration(clip) ? '片段已保存，延长部分循环播放' : '片段位置和长度已保存')
  } catch (error) {
    await loadTimeline()
    ElMessage.error(apiError(error, '保存片段位置失败'))
  } finally {
    savingClip.value = false
  }
}

async function saveClip() {
  if (!clipForm.value || savingClip.value) return
  if (clipForm.value.fade_in_ms + clipForm.value.fade_out_ms > clipForm.value.duration_ms) {
    ElMessage.warning('淡入和淡出总时长不能超过片段长度')
    return
  }
  savingClip.value = true
  try {
    const { id, line_id, track_type, source_duration_ms, max_duration_ms, ...payload } = clipForm.value
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
    // Reconcile newly generated takes before every export, even when this view
    // was opened before generation completed.
    if (!await rebuildTimeline(true)) return
    if (!timeline.value.clip_count) throw new Error('还没有可用音频，请先生成至少一句或加入素材')
    const response = await renderChapterTimeline(projectId.value, chapterId.value)
    if (response.code !== 200) throw new Error(response.message || '渲染失败')
    renderResult.value = response.data
    renderAudioUrl.value = getTimelineRenderAudioUrl(projectId.value, chapterId.value, Date.now())
    ElMessage.success(response.data.is_partial ? `阶段成片已生成，已跳过 ${response.data.missing_lines.length} 条缺少音频的内容` : '时间线混音成片已生成')
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
    stale: '台词、声音或采用版本已变化。刷新会保留手动调整；也可直接渲染，系统会先同步已有音频。',
    failed: '构建失败，请检查音频资产后重试。',
    missing_audio: '部分内容没有可用音频，可以直接渲染已有片段；缺失内容会跳过，成片标记为阶段成片。',
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

function openDubbingProject(lineId = props.selectedLineId) {
  emit('focus-line', typeof lineId === 'number' || typeof lineId === 'string' ? lineId : null)
}
</script>

<style scoped>
.timeline-page { min-height: 100%; }
.timeline-header, .timeline-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.timeline-header { margin-bottom: 14px; }
.timeline-header h2 { margin: 0; font-size: 24px; letter-spacing: 0; }
.overview-note { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.eyebrow { margin: 0 0 4px; color: var(--el-text-color-secondary); font-size: 12px; text-transform: uppercase; }
.filters, .timeline-toolbar { display: flex; gap: 10px; }
.filters .el-select { width: 220px; }
.missing-lines { margin-bottom: 14px; color: var(--el-text-color-secondary); font-size: 13px; }
.missing-lines summary { cursor: pointer; }
.missing-lines ul { max-height: 220px; overflow: auto; }
.missing-lines .el-button { white-space: normal; text-align: left; height: auto; }
.timeline-status-alert { margin-bottom: 14px; }
.timeline-toolbar { flex-wrap: wrap; justify-content: flex-start; padding: 12px; margin-bottom: 14px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.render-result { display: grid; grid-template-columns: minmax(160px, 240px) minmax(280px, 1fr) auto; gap: 14px; align-items: center; padding: 10px 12px; margin-bottom: 14px; border-left: 3px solid var(--el-color-success); background: var(--el-fill-color-extra-light); }
.render-result strong, .render-result span { display: block; }
.render-result span { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 11px; }
.render-result audio { width: 100%; height: 36px; }
.speed-tools { display: grid; gap: 8px; margin-top: 12px; }
.speed-tools .el-form-item { margin-bottom: 0; }
.speed-tools audio { width: 100%; height: 34px; }
.speed-tools small { color: var(--el-text-color-secondary); }
.speed-tools .el-button { margin: 0 5px 4px 0; }
.alignment-tools { display: grid; gap: 10px; margin: 14px 0; }
.alignment-tools > div { display: flex; flex-wrap: wrap; gap: 6px; }
.alignment-tools .el-button { margin-left: 0; }
.alignment-tools small { color: var(--el-text-color-secondary); }
.clip-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.clip-form-grid .el-input-number { width: 100%; }
@media (max-width: 900px) { .timeline-header { align-items: flex-start; flex-direction: column; } .filters { width: 100%; } .filters .el-select { flex: 1; width: auto; } .timeline-toolbar { flex-wrap: wrap; } .render-result { grid-template-columns: 1fr auto; } .render-result audio { grid-column: 1 / -1; grid-row: 2; } }
@media (max-width: 560px) { .filters { flex-direction: column; } .filters .el-select { width: 100%; } .render-result, .clip-form-grid { grid-template-columns: 1fr; } .render-result audio { grid-column: 1; grid-row: auto; } }
</style>
