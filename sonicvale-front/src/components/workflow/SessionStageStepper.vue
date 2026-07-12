<template>
  <ol class="workflow-steps" aria-label="改编进度">
    <li v-for="(item, index) in steps" :key="item.key" :class="item.status" :aria-current="item.status === 'current' ? 'step' : undefined">
      <span class="step-index">{{ item.status === 'done' ? '✓' : index + 1 }}</span>
      <span><strong>{{ item.title }}</strong><small>{{ item.caption }}</small></span>
    </li>
  </ol>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ stage: { type: String, default: 'created' } })
const steps = computed(() => {
  const definitions = [
    ['source', '解析原文', '提取人物、场景与冲突', ['created', 'parsing']],
    ['roles', '确认角色', '检查人物设定与声线建议', ['role_draft_ready', 'awaiting_role_confirmation']],
    ['script', '确认剧本', '按场景检查台词与声音轨', ['generating_script', 'script_draft_ready', 'awaiting_script_confirmation']],
    ['commit', '加入项目', '写入章节、角色与台词', ['committing', 'completed']],
  ]
  let current = definitions.findIndex((item) => item[3].includes(props.stage))
  if (props.stage === 'failed' || props.stage === 'cancelled' || current < 0) current = 0
  return definitions.map(([key, title, caption], index) => ({
    key, title, caption, status: index < current ? 'done' : index === current ? 'current' : 'upcoming',
  }))
})
</script>

<style scoped>
.workflow-steps { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:0; padding:0; list-style:none; }
.workflow-steps li { display:flex; gap:10px; min-width:0; padding:12px; border:1px solid var(--el-border-color-lighter); border-radius:10px; color:var(--el-text-color-secondary); background:var(--el-fill-color-lighter); }
.workflow-steps li.current { border-color:color-mix(in srgb,var(--el-color-primary) 55%,var(--el-border-color)); color:var(--el-text-color-primary); background:color-mix(in srgb,var(--el-color-primary) 9%,var(--el-bg-color)); }
.workflow-steps li.done { color:var(--el-color-success); }
.step-index { display:grid; place-items:center; width:28px; height:28px; flex:0 0 28px; border-radius:50%; background:var(--el-bg-color); font-weight:700; }
.workflow-steps strong,.workflow-steps small { display:block; overflow-wrap:anywhere; }
.workflow-steps small { margin-top:3px; color:var(--el-text-color-secondary); line-height:1.4; }
@media(max-width:900px){.workflow-steps{grid-template-columns:1fr 1fr}}
@media(max-width:560px){.workflow-steps{grid-template-columns:1fr}}
</style>
