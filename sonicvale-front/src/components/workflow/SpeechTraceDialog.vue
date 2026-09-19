<template>
  <el-dialog :model-value="modelValue" title="生成输入与记录" width="min(960px, 94vw)" append-to-body @update:model-value="$emit('update:modelValue', $event)" @open="load">
    <p class="hint">预览使用已保存的台词与当前配音设定，不调用语音模型。先保存台词编辑，再刷新查看。</p>
    <el-button :loading="loading" @click="load">刷新输入与记录</el-button>
    <el-tabs v-model="tab">
      <el-tab-pane label="当前输入预览" name="preview">
        <el-alert v-if="previewError" :title="previewError" type="warning" :closable="false" />
        <div v-if="preview" v-loading="loading">
          <p><el-tag>{{ preview.model }}</el-tag> {{ preview.context?.speaker }} · 强度 {{ preview.original_strength }} → {{ preview.effective_strength }}</p>
          <ul v-if="preview.warnings?.length" class="warnings"><li v-for="warning in preview.warnings" :key="warning">{{ warning }}</li></ul>
          <ScenePerformanceCard :plan="preview.context?.scene_performance?.plan" :cue="preview.context?.scene_performance?.cue" :message="preview.context?.scene_performance?.message" />
          <div class="text-comparison"><div><strong>原台词</strong><pre>{{ preview.original_text }}</pre></div><div><strong>送入 TTS 的正文</strong><pre>{{ preview.tts_text }}</pre></div></div>
          <details open><summary>最终请求预览（已脱敏）</summary><pre>{{ json(preview.request_preview) }}</pre></details>
          <details><summary>上下文与发音处理</summary><pre>{{ json({ context: preview.context, pronunciation: preview.pronunciation_applied, policy: preview.policy_version, settings_revision: preview.settings_revision }) }}</pre></details>
        </div>
      </el-tab-pane>
      <el-tab-pane :label="`生成历史（${records.length}${nextCursor ? '+' : ''}）`" name="history">
        <p class="hint">保留本功能启用后的实际请求、服务返回和错误；旧音频不会补造记录。返回文本是接口元数据，不代表模型解释或实际读音校对。</p>
        <el-alert v-if="historyError" :title="historyError" type="error" :closable="false" />
        <el-empty v-if="!records.length && !loading && !historyError" description="本句尚无生成记录" :image-size="55" />
        <article v-for="record in records" :key="record.id" class="trace-record">
          <header><el-tag :type="record.status === 'succeeded' ? 'success' : record.status === 'failed' ? 'danger' : 'info'">{{ statusLabel(record.status) }}</el-tag><time>{{ formatTime(record.created_at) }}</time><span v-if="record.audio_version_id">音频版本 {{ record.audio_version_id }}</span></header>
          <p v-if="record.error_message" class="error">{{ record.error_message }}</p>
          <details><summary>当时的台词、背景和指导</summary><pre>{{ json(record.input_snapshot) }}</pre></details>
          <details><summary>实际请求</summary><pre>{{ record.request_json ? json(record.request_json) : '请求尚未发出，或准备阶段已失败。' }}</pre></details>
          <details><summary>服务返回</summary><pre>{{ record.response_json ? json(record.response_json) : '未收到可记录的服务返回。' }}</pre></details>
          <details><summary>任务与音频摘要</summary><pre>{{ json({ generation_id: record.id, task_id: record.task_id, completed_at: record.completed_at, result: record.result_json }) }}</pre></details>
        </article>
        <el-button v-if="nextCursor" :loading="loadingMore" @click="loadMore">加载更早记录</el-button>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import ScenePerformanceCard from './ScenePerformanceCard.vue'
import { getSpeechPreview, getSpeechGenerations } from '../../api/speech'
const props = defineProps({ modelValue: Boolean, projectId: { type: Number, required: true }, lineId: Number })
defineEmits(['update:modelValue'])
const tab = ref('preview'), loading = ref(false), loadingMore = ref(false), preview = ref(null), records = ref([]), nextCursor = ref(null), previewError = ref(''), historyError = ref('')
let requestRevision = 0
const json = value => JSON.stringify(value, null, 2)
const message = exc => exc.response?.data?.detail || exc.message || '读取失败'
const statusLabel = status => ({ succeeded: '生成成功', failed: '生成失败', timed_out:'等待超时 / 结果未采用', interrupted:'进程中断 / 结果待检查', preparing: '准备中 / 未完成', requesting: '请求已发出 / 未完成' })[status] || status
const formatTime = value => value ? new Date(/[Zz]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('zh-CN') : ''
async function load() {
  if (!props.lineId) return
  const revision = ++requestRevision
  loading.value = true; preview.value = null; records.value = []; nextCursor.value = null; previewError.value = ''; historyError.value = ''
  const [current, history] = await Promise.allSettled([getSpeechPreview(props.projectId, props.lineId), getSpeechGenerations(props.projectId, props.lineId)])
  if (revision !== requestRevision) return
  if (current.status === 'fulfilled') preview.value = current.value.data
  else previewError.value = message(current.reason)
  if (history.status === 'fulfilled') { records.value = history.value.data.items; nextCursor.value = history.value.data.next_cursor }
  else historyError.value = message(history.reason)
  loading.value = false
}
async function loadMore() {
  const revision = requestRevision; loadingMore.value = true
  try {
    const { data } = await getSpeechGenerations(props.projectId, props.lineId, nextCursor.value)
    if (revision === requestRevision) { records.value.push(...data.items); nextCursor.value = data.next_cursor }
  } catch (exc) { if (revision === requestRevision) historyError.value = message(exc) }
  finally { loadingMore.value = false }
}
</script>

<style scoped>
.hint{color:var(--el-text-color-secondary);font-size:12px;line-height:1.7}.text-comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px}.text-comparison>div{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,monospace;padding:12px;background:var(--el-fill-color-light);border-radius:6px;max-height:420px;overflow-y:auto}details{margin:12px 0}summary{cursor:pointer;font-weight:600;line-height:1.8}.trace-record{border-top:1px solid var(--el-border-color);padding:16px 0}.trace-record header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:12px}.error{color:var(--el-color-danger);overflow-wrap:anywhere}.warnings{padding-left:20px;font-size:12px;line-height:1.8;color:var(--el-text-color-secondary)}@media(max-width:600px){.text-comparison{grid-template-columns:1fr}pre{font-size:11px}}
</style>
