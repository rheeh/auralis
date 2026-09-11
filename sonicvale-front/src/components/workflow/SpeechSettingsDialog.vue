<template>
  <el-dialog :model-value="modelValue" title="配音设定" width="min(760px, 94vw)" append-to-body @update:model-value="$emit('update:modelValue', $event)" @open="load">
    <div v-loading="loading">
      <p class="hint">用于本项目之后的配音。保存不会重新生成或覆盖已有音频。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="作品背景摘要"><el-input v-model="form.story_background" aria-label="作品背景摘要" type="textarea" :rows="4" :maxlength="1200" show-word-limit placeholder="时代、人物关系、长期动机和小说整体氛围。留空时沿用已有章节解析或项目简介。" /></el-form-item>
        <el-form-item label="共同表演基调"><el-input v-model="form.delivery_style" aria-label="共同表演基调" type="textarea" :rows="2" :maxlength="400" show-word-limit placeholder="例如：生活化接话，保持人物声线；悬疑感主要由停顿呈现。" /></el-form-item>
        <el-form-item><el-checkbox v-model="form.continuity_enabled">同场景、同人物限制无依据的情绪强度突增</el-checkbox><small class="hint">根据台本顺序限制强度向上跳级，不提高弱情绪，也不改写原标签。本句明确写“情绪转折”及表达方式时允许突变；该规则不能保证音频的实际情绪连续。</small></el-form-item>
        <div class="dictionary-head"><strong>发音词表</strong><el-button :disabled="form.pronunciation_entries.length >= 200" @click="addEntry">添加词条</el-button></div>
        <p class="hint">拼音用于已接入此能力的模型，例如 Qwen-Audio 3.0。其他模型可用“替代读法”；原台词和字幕保留原文。替代读法不会递归替换。</p>
        <div v-for="(entry, index) in form.pronunciation_entries" :key="index" class="dictionary-entry">
          <el-input v-model="entry.term" :aria-label="`词条${index + 1}原文`" placeholder="原文：重庆" :maxlength="80" />
          <el-input v-model="entry.pronunciation" :aria-label="`词条${index + 1}拼音`" placeholder="拼音：chong2 qing4" :maxlength="240" />
          <el-input v-model="entry.spoken_as" :aria-label="`词条${index + 1}替代读法`" placeholder="替代读法（可选）" :maxlength="120" />
          <el-button text type="danger" :aria-label="`删除词条${index + 1}`" @click="form.pronunciation_entries.splice(index, 1)">删除</el-button>
        </div>
        <el-empty v-if="!form.pronunciation_entries.length" description="可添加人名、地名、多音字和缩写" :image-size="45" />
      </el-form>
    </div>
    <template #footer><el-button @click="$emit('update:modelValue', false)">关闭</el-button><el-button type="primary" :loading="saving" :disabled="loading || !loaded" @click="save">保存配音设定</el-button></template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSpeechSettings, saveSpeechSettings } from '../../api/speech'
const props = defineProps({ modelValue: Boolean, projectId: { type: Number, required: true } })
const emit = defineEmits(['update:modelValue'])
const form = reactive({ story_background: '', delivery_style: '', continuity_enabled: true, pronunciation_entries: [] })
const loading = ref(false), saving = ref(false), loaded = ref(false), error = ref('')
function message(exc) {
  const detail = exc.response?.data?.detail
  return Array.isArray(detail) ? detail.map(item => item.msg).join('；') : detail || exc.message || '操作失败'
}
async function load() {
  loading.value = true; loaded.value = false; error.value = ''
  try {
    const { data } = await getSpeechSettings(props.projectId)
    for (const key of Object.keys(form)) form[key] = data[key]
    loaded.value = true
  } catch (exc) { error.value = message(exc) }
  finally { loading.value = false }
}
function addEntry() { form.pronunciation_entries.push({ term: '', pronunciation: '', spoken_as: '' }) }
async function save() {
  saving.value = true; error.value = ''
  try { await saveSpeechSettings(props.projectId, { ...form }); ElMessage.success('已保存，将用于之后的配音'); emit('update:modelValue', false) }
  catch (exc) { error.value = message(exc) }
  finally { saving.value = false }
}
</script>

<style scoped>
.hint{display:block;color:var(--el-text-color-secondary);font-size:12px;line-height:1.7;margin:0 0 14px;overflow-wrap:anywhere}.dictionary-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.dictionary-entry{display:grid;grid-template-columns:1fr 1.3fr 1fr auto;gap:8px;margin:10px 0} @media(max-width:600px){.dictionary-entry{grid-template-columns:1fr 1fr}.dictionary-entry>:nth-child(3){grid-column:1}.hint{font-size:12px}}
</style>
