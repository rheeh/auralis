<template>
  <div class="queue-page">
    <header class="queue-header">
      <div>
        <p class="eyebrow">任务</p>
        <h1>生成队列</h1>
      </div>
      <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
    </header>

    <section class="queue-metrics">
      <article>
        <span>TTS 等待数</span>
        <strong>{{ status.tts_queue_size }}</strong>
      </article>
      <article>
        <span>工作线程</span>
        <strong>{{ status.tts_workers }}</strong>
      </article>
      <article>
        <span>运行中线程</span>
        <strong>{{ status.workers_running }}</strong>
      </article>
      <article>
        <span>失败音频任务</span>
        <strong>{{ status.audio_task_counts.failed || 0 }}</strong>
      </article>
    </section>

    <section class="audio-task-panel">
      <div class="session-panel-head"><div><p class="eyebrow">音频生产</p><h2>最近配音任务</h2></div><el-tag effect="plain">{{ audioTasks.length }} 条</el-tag></div>
      <div v-if="audioTasks.length" class="audio-task-list">
        <button v-for="task in audioTasks" :key="task.task_id" type="button" @click="openAudioTask(task)">
          <span><strong>台词 {{ task.line_order ?? '—' }} · {{ task.text || '无文本' }}</strong><small>第 {{ task.attempt }} 次生成</small></span>
          <el-tag :type="audioStatusType(task.status)" effect="plain">{{ audioStatusLabel(task.status) }}</el-tag>
        </button>
      </div>
      <el-empty v-else description="暂无配音任务" :image-size="56" />
    </section>

    <section class="workflow-session-panel">
      <div class="session-panel-head"><div><p class="eyebrow">对话式改编</p><h2>改编会话</h2></div><el-tag effect="plain">{{ activeSessions.length }} 个待处理</el-tag></div>
      <div v-if="sessions.length" class="session-list">
        <button v-for="session in sessions" :key="session.session_id" type="button" @click="openSession(session)">
          <span><strong>{{ session.title || '未命名会话' }}</strong><small>{{ sessionStageLabel(session.current_stage) }}</small></span>
          <el-tag :type="session.status === 'failed' ? 'danger' : session.status === 'completed' ? 'success' : 'warning'" effect="plain">{{ session.status }}</el-tag>
        </button>
      </div>
      <el-empty v-else description="暂无改编会话" :image-size="56" />
    </section>

    <section class="queue-lanes">
      <article>
        <h2>运行中</h2>
        <div v-for="run in runningRuns" :key="run.run_id" class="run-card">
          <strong>{{ run.title }}</strong>
          <span>{{ stageLabel(run.current_stage) }}</span>
          <el-tag type="warning" effect="plain">{{ statusLabel(run.status) }}</el-tag>
        </div>
        <el-empty v-if="!runningRuns.length" description="暂无运行任务" />
      </article>
      <article>
        <h2>待制作</h2>
        <div v-for="run in readyRuns" :key="run.run_id" class="run-card">
          <strong>{{ run.title }}</strong>
          <span>章节 ID：{{ run.chapter_id || '未写入' }}</span>
          <el-tag type="success" effect="plain">{{ statusLabel(run.status) }}</el-tag>
          <div class="run-actions">
            <el-button
              v-if="run.status === 'script_ready'"
              size="small"
              type="primary"
              :loading="committingRunId === run.run_id"
              @click="commitRun(run)"
            >
              写入工程
            </el-button>
            <el-button v-if="run.project_id" size="small" @click="openProject(run)">打开工程</el-button>
          </div>
        </div>
        <el-empty v-if="!readyRuns.length" description="暂无待制作任务" />
      </article>
      <article>
        <h2>需要处理</h2>
        <div v-for="run in failedRuns" :key="run.run_id" class="run-card">
          <strong>{{ run.title }}</strong>
          <span>{{ run.error_message || stageLabel(run.current_stage) }}</span>
          <el-tag type="danger" effect="plain">{{ statusLabel(run.status) }}</el-tag>
        </div>
        <el-empty v-if="!failedRuns.length" description="暂无失败任务" />
      </article>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchQueueStatus, fetchRecentAudioTasks } from '../api/queue'
import { commitDramaAdaptation, fetchChatSessions, fetchDramaAdaptations } from '../api/drama'

const router = useRouter()
const status = reactive({
  tts_queue_size: 0,
  tts_workers: 0,
  workers_running: 0,
  audio_task_counts: {},
})
const runs = ref([])
const sessions = ref([])
const audioTasks = ref([])
const committingRunId = ref(null)

const runningRuns = computed(() => runs.value.filter((run) => ['pending', 'running'].includes(run.status)))
const readyRuns = computed(() => runs.value.filter((run) => ['script_ready', 'committed'].includes(run.status)))
const failedRuns = computed(() => runs.value.filter((run) => run.status === 'failed'))
const activeSessions = computed(() => sessions.value.filter((session) => !['completed', 'cancelled'].includes(session.status)))

onMounted(loadAll)

async function loadAll() {
  await Promise.all([loadStatus(), loadRuns(), loadSessions(), loadAudioTasks()])
}

async function loadAudioTasks() {
  const response = await fetchRecentAudioTasks({ limit: 30 })
  audioTasks.value = response.code === 200 ? response.data : []
}

async function loadSessions() {
  const response = await fetchChatSessions({ limit: 80 })
  sessions.value = response.code === 200 ? response.data : []
}

async function loadStatus() {
  const response = await fetchQueueStatus()
  if (response.code !== 200) return
  Object.assign(status, response.data)
}

async function loadRuns() {
  const response = await fetchDramaAdaptations({ limit: 80 })
  runs.value = response.code === 200 ? response.data : []
}

async function commitRun(run) {
  committingRunId.value = run.run_id
  try {
    const response = await commitDramaAdaptation({
      run_id: run.run_id,
      chapter_title: run.title,
      replace_chapter_lines: true,
    })
    if (response.code !== 200) throw new Error(response.message || '写入失败')
    ElMessage.success(response.message || '已写入工程')
    await loadRuns()
  } catch (error) {
    ElMessage.error(error?.message || '写入失败')
  } finally {
    committingRunId.value = null
  }
}

function openProject(run) {
  router.push(`/projects/${run.project_id}/overview`)
}

function openSession(session) {
  router.push(`/studio?project_id=${session.project_id}&session_id=${session.session_id}`)
}

function openAudioTask(task) {
  if (task.session_id) router.push(`/studio?project_id=${task.project_id}&session_id=${task.session_id}`)
  else router.push(`/projects/${task.project_id}/overview`)
}

function audioStatusLabel(status) {
  return ({ queued: '等待中', processing: '生成中', done: '已生成', failed: '失败', skipped: '已跳过', cancelled: '已取消' })[status] || status
}

function audioStatusType(status) {
  return ({ processing: 'warning', done: 'success', failed: 'danger', skipped: 'info' })[status] || 'info'
}

function sessionStageLabel(stage) {
  return {
    created: '准备解析', parsing: '解析原文', awaiting_role_confirmation: '等待确认角色',
    generating_script: '生成剧本', awaiting_script_confirmation: '等待确认剧本',
    script_draft_ready: '等待写入项目', completed: '已完成', failed: '需要重试', cancelled: '已取消',
  }[stage] || stage
}

function stageLabel(stage) {
  return {
    created: '已创建',
    parse_novel: '解析小说',
    write_script: '生成台本',
    polish_language: '整理语言',
    script_ready: '剧本待制作',
    committed: '已写入工程',
    failed: '失败',
  }[stage] || stage
}

function statusLabel(status) {
  return {
    pending: '等待中',
    running: '运行中',
    script_ready: '待写入',
    committed: '已写入',
    failed: '失败',
  }[status] || status
}
</script>

<style scoped>
.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.queue-header h1 {
  margin: 0;
  font-size: 24px;
}

.queue-header :deep(.el-button),
.run-actions :deep(.el-button) {
  min-height: 44px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.queue-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.queue-metrics article,
.queue-lanes article,
.workflow-session-panel,
.audio-task-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.workflow-session-panel,.audio-task-panel { display:grid; gap:12px; margin-bottom:16px; padding:16px; }
.session-panel-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.session-panel-head h2 { margin:0; font-size:16px; }
.session-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.session-list button { display:flex; align-items:center; justify-content:space-between; gap:10px; min-height:64px; padding:12px; border:1px solid var(--el-border-color-lighter); border-radius:8px; color:var(--el-text-color-primary); background:var(--el-fill-color-blank); text-align:left; cursor:pointer; }
.session-list button:hover,.session-list button:focus-visible { border-color:var(--el-color-primary); outline:2px solid color-mix(in srgb,var(--el-color-primary) 25%,transparent); }
.session-list strong,.session-list small { display:block; overflow-wrap:anywhere; }.session-list small { margin-top:4px; color:var(--el-text-color-secondary); }
.audio-task-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.audio-task-list button{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:64px;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:8px;color:var(--el-text-color-primary);background:var(--el-fill-color-blank);text-align:left;cursor:pointer}.audio-task-list button:hover,.audio-task-list button:focus-visible{border-color:var(--el-color-primary);outline:2px solid color-mix(in srgb,var(--el-color-primary) 25%,transparent)}.audio-task-list span{min-width:0}.audio-task-list strong,.audio-task-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.audio-task-list small{margin-top:4px;color:var(--el-text-color-secondary)}

.queue-metrics article {
  display: grid;
  gap: 8px;
  padding: 16px;
}

.queue-metrics span {
  color: var(--el-text-color-secondary);
}

.queue-metrics strong {
  font-size: 30px;
}

.queue-lanes {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.queue-lanes article {
  min-height: 360px;
  padding: 14px;
}

.queue-lanes h2 {
  margin: 0 0 12px;
  font-size: 16px;
}

.run-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.run-card strong,
.run-card span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.run-card span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.run-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 4px;
}

@media(max-width:900px){.session-list,.audio-task-list,.queue-lanes,.queue-metrics{grid-template-columns:1fr}}
</style>
