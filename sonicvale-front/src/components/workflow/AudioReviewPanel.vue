<template>
  <section class="audio-review" aria-labelledby="audio-review-title">
    <header class="panel-head">
      <div><p class="eyebrow">配音与试听</p><h3 id="audio-review-title">音频制作进度</h3></div>
      <div class="head-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="VideoPlay" :loading="generating" @click="generate(false)">生成待配音台词</el-button>
      </div>
    </header>

    <div class="progress-block" role="status" aria-live="polite">
      <div><strong>{{ summary.completed }} / {{ summary.total }}</strong><span> 已完成</span></div>
      <el-progress :percentage="summary.progress" :status="summary.counts.failed ? 'exception' : undefined" />
      <div class="status-row">
        <el-tag effect="plain">等待 {{ summary.counts.queued || 0 }}</el-tag>
        <el-tag type="warning" effect="plain">生成中 {{ summary.counts.processing || 0 }}</el-tag>
        <el-tag type="success" effect="plain">完成 {{ summary.counts.done || 0 }}</el-tag>
        <el-tag type="danger" effect="plain">失败 {{ summary.counts.failed || 0 }}</el-tag>
      </div>
    </div>

    <div v-if="summary.tasks.length" class="task-list">
      <article v-for="task in summary.tasks" :key="task.task_id" class="task-card">
        <div class="task-copy">
          <div class="line-heading">
            <span class="line-number">台词 {{ task.line_order ?? '—' }}</span>
            <span v-if="task.role_name" class="voice-role" :class="roleClass(task.role_name)">
              <b>{{ task.role_name }}</b>{{ roleVoiceLabel(task) }}
            </span>
          </div>
          <strong>{{ task.text || '无台词文本' }}</strong>
          <small>第 {{ task.attempt }} 次生成 · {{ statusLabel(task.status) }}</small>
        </div>
        <div class="task-status">
          <el-tag :type="statusType(task.status)" effect="plain">{{ statusLabel(task.status) }}</el-tag>
          <el-tag v-if="task.review_status !== 'pending'" :type="task.review_status === 'approved' ? 'success' : 'danger'" effect="dark">
            {{ task.review_status === 'approved' ? '已通过' : '需重做' }}
          </el-tag>
        </div>
        <div v-if="task.status === 'done'" class="review-controls">
          <audio :src="audioUrl(task.line_id)" controls preload="none">当前浏览器不支持音频播放。</audio>
          <div>
            <el-button :icon="CircleCheck" :disabled="busyTaskId === task.task_id" @click="review(task, true)">通过</el-button>
            <el-button type="danger" plain :icon="Close" :disabled="busyTaskId === task.task_id" @click="review(task, false)">需重做</el-button>
            <el-button v-if="task.review_status === 'rejected'" type="primary" plain :icon="RefreshRight" :loading="busyTaskId === task.task_id" @click="retry(task)">重新生成</el-button>
          </div>
        </div>
        <div v-if="task.status === 'failed'" class="error-row" role="alert">
          <span>{{ task.error_message || '音频生成失败，请重试。' }}</span>
          <el-button type="danger" plain :icon="RefreshRight" :loading="busyTaskId === task.task_id" @click="retry(task)">重试</el-button>
        </div>
      </article>
    </div>
    <el-empty v-else description="尚未创建配音任务" :image-size="64" />
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Close, Refresh, RefreshRight, VideoPlay } from '@element-plus/icons-vue'
import { API_BASE_URL } from '../../api/config'
import { fetchSessionAudioTasks, generateSessionAudio, retrySessionAudioTask, reviewSessionAudioTask } from '../../api/drama'

const props = defineProps({ sessionId: { type: String, required: true } })
const summary = reactive({ total: 0, completed: 0, progress: 0, counts: {}, tasks: [] })
const loading = ref(false)
const generating = ref(false)
const busyTaskId = ref(null)
let pollTimer = null

onMounted(load)
watch(() => props.sessionId, load)
onBeforeUnmount(() => clearTimeout(pollTimer))

function apiError(error, fallback) { return error?.response?.data?.message || error?.message || fallback }
function audioUrl(lineId) { return `${API_BASE_URL}lines/${lineId}/audio` }
function statusLabel(status) { return ({ queued: '等待中', processing: '生成中', done: '已生成', failed: '失败', skipped: '已跳过', cancelled: '已取消' })[status] || status }
function statusType(status) { return ({ processing: 'warning', done: 'success', failed: 'danger', skipped: 'info' })[status] || 'info' }
function roleClass(name) { return name === '知夏' ? 'female' : name === '闻舟' ? 'male' : '' }
function roleVoiceLabel(task) {
  if (task.role_name === '知夏') return ' · 年轻女声'
  if (task.role_name === '闻舟') return ' · 成熟男声'
  return task.tts_route === 'edge' ? ' · Edge 声线' : ''
}
function schedulePoll() {
  clearTimeout(pollTimer)
  if (summary.tasks.some((task) => ['queued', 'processing'].includes(task.status))) pollTimer = setTimeout(load, 1800)
}
async function load() {
  if (!props.sessionId) return
  loading.value = true
  try {
    const response = await fetchSessionAudioTasks(props.sessionId)
    if (response.code !== 200) throw new Error(response.message)
    Object.assign(summary, response.data)
    schedulePoll()
  } catch (error) { ElMessage.error(apiError(error, '读取音频任务失败')) } finally { loading.value = false }
}
async function generate(force) {
  generating.value = true
  try {
    const response = await generateSessionAudio(props.sessionId, force)
    if (response.code !== 200) throw new Error(response.message)
    ElMessage.success(response.data.created ? `已加入 ${response.data.created} 条配音任务` : '没有新的待配音台词')
    await load()
  } catch (error) { ElMessage.error(apiError(error, '创建配音任务失败')) } finally { generating.value = false }
}
async function review(task, approved) {
  let note = ''
  if (!approved) {
    try {
      const result = await ElMessageBox.prompt('请简要说明需要调整的地方，之后可重新生成。', '标记为需重做', { inputPlaceholder: '例如：语速太快，情绪需要更克制', confirmButtonText: '保存意见', cancelButtonText: '取消' })
      note = result.value || ''
    } catch { return }
  }
  busyTaskId.value = task.task_id
  try {
    const response = await reviewSessionAudioTask(props.sessionId, task.task_id, { approved, note })
    if (response.code !== 200) throw new Error(response.message)
    ElMessage.success(approved ? '试听已通过' : '已标记为需重做')
    await load()
  } catch (error) { ElMessage.error(apiError(error, '保存审核失败')) } finally { busyTaskId.value = null }
}
async function retry(task) {
  busyTaskId.value = task.task_id
  try {
    const response = await retrySessionAudioTask(props.sessionId, task.task_id)
    if (response.code !== 200) throw new Error(response.message)
    ElMessage.success('已重新加入生成队列')
    await load()
  } catch (error) { ElMessage.error(apiError(error, '重试失败')) } finally { busyTaskId.value = null }
}
</script>

<style scoped>
.audio-review{display:grid;gap:16px;padding:18px;border:1px solid color-mix(in srgb,var(--el-color-success) 36%,var(--el-border-color));border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}
.panel-head,.head-actions,.status-row,.task-status,.review-controls,.review-controls>div,.error-row,.line-heading{display:flex;align-items:center;gap:10px}.panel-head,.error-row{justify-content:space-between}.panel-head h3,.eyebrow{margin:0}.eyebrow{margin-bottom:4px;color:var(--el-color-primary);font-size:12px;text-transform:uppercase}.head-actions,.status-row,.task-status,.review-controls>div,.line-heading{flex-wrap:wrap}.progress-block{display:grid;gap:10px;padding:14px;border-radius:10px;background:var(--el-fill-color-light)}.progress-block strong{font-size:22px}.progress-block span{color:var(--el-text-color-secondary)}.task-list{display:grid;gap:10px}.task-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:14px;border:1px solid var(--el-border-color-lighter);border-radius:10px}.task-copy{display:grid;gap:6px;min-width:0}.task-copy strong{overflow-wrap:anywhere}.task-copy small,.line-number{color:var(--el-text-color-secondary);font-size:12px}.voice-role{padding:4px 9px;border-radius:999px;background:var(--el-fill-color-light);color:var(--el-text-color-secondary);font-size:12px}.voice-role.female{background:rgba(239,113,172,.1);color:#b34379}.voice-role.male{background:rgba(80,137,211,.11);color:#356fae}.review-controls,.error-row{grid-column:1/-1;flex-wrap:wrap;padding-top:10px;border-top:1px solid var(--el-border-color-lighter)}.review-controls audio{width:min(100%,420px)}.error-row{color:var(--el-color-danger)}.audio-review :deep(.el-button){min-height:44px}
@media(max-width:720px){.panel-head,.review-controls,.error-row{align-items:stretch;flex-direction:column}.head-actions{width:100%}.head-actions .el-button{flex:1}.task-card{grid-template-columns:1fr}.task-status{justify-content:flex-start}}
</style>
