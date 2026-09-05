<template>
  <section class="sound-recommendations" aria-label="AI 音效推荐">
    <div class="recommend-heading">
      <div><strong>为这个位置挑声音</strong><p>结合小说原文与相邻台词，从音效库中挑选；先试听，再选用。</p></div>
      <el-button @click="$emit('browse')">去音效库挑选</el-button>
    </div>
    <div class="recommend-controls">
      <el-select v-model="model" aria-label="音效推荐模型" :disabled="loading">
        <el-option label="qwen3.8-27b" value="qwen3.8-27b" />
        <el-option label="kimi-k3" value="kimi-k3" />
      </el-select>
      <el-button type="primary" :disabled="!lineId" :loading="loading" @click="loadRecommendations(Boolean(result))">{{ result ? '重新推荐' : '推荐音效' }}</el-button>
      <small v-if="result">{{ result.model }} · {{ result.cached ? '已复用上次推荐' : '本次推荐' }}</small>
    </div>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
    <p v-if="!lineId" class="recommend-note">先选择上方的音效或定位台词，再获取推荐。</p>
    <div v-if="loading" class="recommend-loading" role="status">正在阅读这一幕并挑选素材…</div>
    <template v-if="result && !loading">
      <p class="direction-summary">{{ result.summary }}</p>
      <el-alert v-if="result.missing_sound" :title="result.missing_sound" type="info" :closable="false" show-icon />
      <article v-for="choice in result.recommendations" :key="choice.asset_id" class="recommend-card">
        <div class="choice-title"><strong>{{ choice.asset.name }}</strong><el-tag size="small" :type="choice.fit === 'match' ? 'success' : 'warning'" effect="plain">{{ choice.fit === 'match' ? '描述匹配' : '近似替代' }}</el-tag><span>{{ (choice.asset.duration_ms / 1000).toFixed(1) }} 秒</span></div>
        <p>{{ choice.reason }}</p>
        <small>{{ actionMode === 'bind' ? '保留起点和音量；短素材会缩短片段，选用后请重新渲染成片。' : `建议${placementLabels[choice.placement]} · ${choice.volume_db} dB，选用后可在时间线调整。` }}</small>
        <div class="choice-actions">
          <audio controls preload="none" :src="getSoundLibraryAudioUrl(choice.asset_id)" :aria-label="`试听推荐：${choice.asset.name}`" />
          <el-button type="primary" :disabled="Boolean(busyId)" :loading="busyId === choice.asset_id" @click="$emit('select', choice)">{{ actionMode === 'bind' ? '选用并替换此音效' : '选用并加入此处' }}</el-button>
        </div>
      </article>
      <el-empty v-if="!result.recommendations.length" description="库内暂时没有合适的音效，可以手动查找或导入素材。" />
      <small class="recommend-note">推荐依据为素材名称、标签与时长，实际听感请以试听为准。</small>
    </template>
  </section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { getSoundLibraryAudioUrl, recommendSounds } from '../api/soundLibrary'
import { IS_STATIC_DEMO } from '../api/config'

const props = defineProps({ chapterId: Number, lineId: Number, actionMode: String, busyId: String })
defineEmits(['select', 'browse'])
const model = ref('qwen3.8-27b'), loading = ref(false), error = ref(''), result = ref(null)
const placementLabels = { before: '在句前进入', with: '与该句同时进入', after: '在句后进入' }
let requestVersion = 0

async function loadRecommendations(refresh = false) {
  const version = ++requestVersion
  result.value = null
  error.value = ''
  loading.value = false
  if (!props.chapterId || !props.lineId) return
  if (IS_STATIC_DEMO) { error.value = '在线演示不连接模型；请在本地项目中使用 AI 音效推荐。'; return }
  loading.value = true
  try {
    const response = await recommendSounds({ chapter_id: props.chapterId, line_id: props.lineId, model: model.value, refresh })
    if (version !== requestVersion) return
    if (response?.code !== 200) throw new Error(response?.message || '推荐暂时不可用')
    result.value = response.data
  } catch (failure) {
    if (version !== requestVersion) return
    error.value = failure?.response?.data?.detail || (failure?.code === 'ECONNABORTED' ? '推荐超时，请稍后重试或手动挑选。' : failure?.message) || '推荐暂时不可用，请到音效库手动挑选。'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
watch(() => [props.chapterId, props.lineId], () => loadRecommendations(), { immediate: true })
watch(model, () => { ++requestVersion; result.value = null; error.value = ''; loading.value = false })
onBeforeUnmount(() => { ++requestVersion })
</script>

<style scoped>
.sound-recommendations{display:grid;gap:14px}.recommend-heading,.recommend-controls,.choice-title,.choice-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.recommend-heading{justify-content:space-between}.recommend-heading p,.recommend-card p{margin:6px 0;line-height:1.7}.recommend-heading p,.recommend-note,.recommend-card small,.recommend-controls small,.choice-title span{font-size:12px;color:var(--el-text-color-secondary)}.recommend-controls .el-select{width:180px}.recommend-card{display:grid;gap:8px;border:1px solid var(--el-border-color);border-radius:12px;padding:16px;background:var(--el-bg-color)}.choice-actions{justify-content:space-between}.choice-actions audio{width:min(320px,100%);height:38px}.recommend-loading{padding:28px;background:var(--el-fill-color-light);border-radius:10px;color:var(--el-text-color-secondary)}.direction-summary{margin:0;line-height:1.7}
</style>
