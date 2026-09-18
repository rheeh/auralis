<template>
  <details v-if="configuration?.has_audio" class="take-source" @click.stop>
    <summary>{{ statusText }} · 查看当前音频来源</summary>
    <template v-if="take">
      <p><strong>生成文本：</strong>{{ take.text || take.input_snapshot?.prepared?.original_text || '历史版本未记录文本' }}</p>
      <p><strong>生成指导：</strong>{{ take.input_snapshot?.prepared?.production_note || '历史版本未记录指导' }}</p>
    </template>
    <p v-else>此音频没有可核对的生成快照。保留试听，不能据此证明它对应当前文字。</p>
  </details>
</template>
<script setup>
import {computed} from 'vue'
const props=defineProps({line:{type:Object,required:true},configuration:Object})
const take=computed(()=>{
  const variant=(props.line.audio_variants||[]).find(item=>item.id===props.line.active_audio_variant_id)
  const source=variant?.source_audio_version_id||props.line.active_audio_version_id
  return (props.line.audio_versions||[]).find(item=>item.id===source)
})
const statusText=computed(()=>props.configuration?.input_current===true?'符合当前输入':props.configuration?.input_current===false?'历史音频，当前内容需要重新配音':'历史音频，输入来源未验证')
</script>
<style scoped>
.take-source{margin:8px 0;font-size:12px;color:var(--el-text-color-secondary)}
summary{cursor:pointer}p{white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0}
</style>
