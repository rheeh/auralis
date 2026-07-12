<template>
  <div class="timeline-page">
    <header class="timeline-header">
      <div>
        <p class="eyebrow">时间线</p>
        <h1>多轨时间线</h1>
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

    <section class="timeline-toolbar">
      <el-segmented v-model="zoom" :options="zoomOptions" />
      <el-tag effect="plain">{{ lines.length }} 条片段</el-tag>
      <el-tag type="success" effect="plain">{{ completedCount }} 条已生成</el-tag>
      <el-tag type="info" effect="plain">约 {{ totalSeconds }} 秒</el-tag>
      <el-button type="primary" @click="openDubbingProject">打开配音工程</el-button>
    </section>

    <section class="timeline-surface">
      <article v-for="track in tracks" :key="track.key" class="track-row">
        <aside class="track-label">
          <el-icon><component :is="track.icon" /></el-icon>
          <strong>{{ track.label }}</strong>
          <span>{{ groupedLines[track.key]?.length || 0 }} 个片段</span>
        </aside>
        <div class="clip-lane">
          <div
            v-for="line in groupedLines[track.key]"
            :key="line.id"
            class="clip"
            :class="{ done: line.is_done === 1 || line.status === 'done', muted: line.should_speak === 0 }"
            :style="{ width: clipWidth(line) }"
            @click="openDubbingProject"
          >
            <strong>{{ line.scene_title || track.label }}</strong>
            <p>{{ line.text_content || '空片段' }}</p>
            <span>{{ statusLabel(line.status) }} · {{ estimateSeconds(line) }} 秒</span>
          </div>
          <el-empty v-if="!(groupedLines[track.key]?.length)" description="暂无片段" />
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
import { getLinesByChapter } from '../api/line'

const router = useRouter()
const route = useRoute()
const projects = ref([])
const chapters = ref([])
const lines = ref([])
const projectId = ref(null)
const chapterId = ref(null)
const zoom = ref('normal')

const zoomOptions = [
  { label: '紧凑', value: 'compact' },
  { label: '标准', value: 'normal' },
  { label: '放大', value: 'wide' },
]

const tracks = [
  { key: 'voice', label: '人物声', icon: Microphone },
  { key: 'narration', label: '旁白', icon: Headset },
  { key: 'sfx', label: '音效', icon: Bell },
  { key: 'bgm', label: 'BGM', icon: Film },
]

function statusLabel(status) {
  return {
    pending: '未生成',
    queued: '已入队',
    processing: '生成中',
    done: '已生成',
    failed: '失败',
    skipped: '素材轨',
  }[status || 'pending'] || status
}

const groupedLines = computed(() => {
  const groups = { voice: [], narration: [], sfx: [], bgm: [] }
  for (const line of lines.value) {
    const track = line.track || (line.should_speak === 0 ? 'sfx' : 'voice')
    ;(groups[track] || groups.voice).push(line)
  }
  return groups
})

const completedCount = computed(() => lines.value.filter((line) => line.is_done === 1 || line.status === 'done').length)
const totalSeconds = computed(() => lines.value.reduce((sum, line) => sum + estimateSeconds(line), 0))

onMounted(async () => {
  projects.value = await fetchProjects()
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
  }
)

function selectProjectFromQuery() {
  const id = Number(route.query.project_id)
  if (!id) return null
  return projects.value.some((project) => project.id === id) ? id : null
}

async function loadChapters() {
  chapters.value = []
  lines.value = []
  chapterId.value = null
  if (!projectId.value) return
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
  const response = await getLinesByChapter(chapterId.value)
  lines.value = response.code === 200 ? response.data : []
}

function estimateSeconds(line) {
  const text = String(line.text_content || '')
  if (!text) return 1
  if (line.track === 'bgm') return Math.max(8, Math.ceil(text.length / 12))
  if (line.track === 'sfx') return Math.max(2, Math.ceil(text.length / 18))
  return Math.max(2, Math.ceil(text.length / 4))
}

function clipWidth(line) {
  const multiplier = { compact: 8, normal: 13, wide: 20 }[zoom.value] || 13
  return `${Math.min(520, Math.max(96, estimateSeconds(line) * multiplier))}px`
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
.timeline-page {
  min-height: 100%;
}

.timeline-header,
.timeline-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.timeline-header {
  margin-bottom: 14px;
}

.timeline-header h1 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.filters,
.timeline-toolbar {
  display: flex;
  gap: 10px;
}

.filters .el-select {
  width: 220px;
}

.timeline-toolbar {
  justify-content: flex-start;
  padding: 12px;
  margin-bottom: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.timeline-surface {
  display: grid;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
}

.track-row {
  display: grid;
  grid-template-columns: 160px minmax(760px, 1fr);
  min-height: 118px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  overflow: hidden;
}

.track-label {
  display: grid;
  align-content: center;
  gap: 6px;
  padding: 14px;
  border-right: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-light);
}

.track-label strong,
.track-label span {
  display: block;
}

.track-label span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.clip-lane {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  overflow-x: auto;
  padding: 14px;
}

.clip {
  flex: 0 0 auto;
  display: grid;
  align-content: start;
  gap: 5px;
  min-height: 76px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 36%, var(--el-border-color));
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-primary-light-9) 82%, var(--el-bg-color));
  cursor: pointer;
}

.clip.done {
  border-color: color-mix(in srgb, var(--el-color-success) 44%, var(--el-border-color));
  background: color-mix(in srgb, var(--el-color-success-light-9) 88%, var(--el-bg-color));
}

.clip.muted {
  border-style: dashed;
}

.clip strong,
.clip p,
.clip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clip p {
  margin: 0;
}

.clip span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
