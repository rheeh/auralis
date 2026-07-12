<template>
  <section class="confirm-card" aria-labelledby="script-card-title">
    <header>
      <div><p class="eyebrow">需要确认</p><h3 id="script-card-title">{{ script?.title || '剧本草稿' }}</h3><p>{{ script?.logline }}</p></div>
      <DraftRevisionBar :revision="revision" />
    </header>
    <div class="draft-audit" :class="{ warning: audit.hasIssues }">
      <div class="audit-metrics">
        <el-tag size="small" effect="plain">对白 {{ audit.dialogueCount }}</el-tag>
        <el-tag size="small" effect="plain" :type="audit.narrationRatio > 18 ? 'warning' : 'success'">旁白 {{ audit.narrationRatio }}%</el-tag>
        <el-tag size="small" effect="plain" type="info">声音轨 {{ audit.soundCount }}</el-tag>
      </div>
      <span>{{ audit.message }}</span>
    </div>
    <el-collapse accordion>
      <el-collapse-item v-for="(scene,index) in script?.scenes || []" :key="index" :name="index">
        <template #title><strong>第 {{ index+1 }} 场 · {{ scene.title }}</strong><span class="scene-count">{{ scene.lines?.length || 0 }} 行</span></template>
        <div class="line-list">
          <article v-for="(line,lineIndex) in scene.lines" :key="lineIndex">
            <el-tag size="small" effect="plain">{{ trackLabel(line.track) }}</el-tag><strong>{{ line.speaker }}</strong><div><p>{{ displayText(line) }}</p><small v-if="line.productionNote">制作提示：{{ line.productionNote }}</small><small v-for="(event,eventIndex) in line.audioEvents || []" :key="eventIndex">{{ event.timing }} · {{ event.type }} · {{ event.content }} · {{ event.volume_db }}</small></div>
          </article>
        </div>
      </el-collapse-item>
    </el-collapse>
    <footer><el-button type="primary" :loading="loading" @click="$emit('confirm',script)">{{ confirmLabel || '确认剧本并准备写入项目' }}</el-button></footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import DraftRevisionBar from './DraftRevisionBar.vue'
const props = defineProps({ script: Object, revision: Number, loading: Boolean, confirmLabel: String })
defineEmits(['confirm'])
function trackLabel(track) { return { voice:'人物', narration:'旁白', sfx:'音效', bgm:'BGM' }[track] || track }
function displayText(line) { return line.text || line.soundPrompt || line.productionNote || '缺少声音提示，请让 AI 补充' }
const audit = computed(() => {
  const lines = (props.script?.scenes || []).flatMap((scene) => scene.lines || [])
  const dialogues = lines.filter((line) => line.type === 'dialogue' || line.track === 'voice')
  const narrations = lines.filter((line) => line.type === 'narration' || line.track === 'narration')
  const soundCount = lines.filter((line) => ['sfx','bgm'].includes(line.type) || ['sfx','bgm'].includes(line.track)).length
  const countChars = (items) => items.reduce((sum,line) => sum + String(line.text || '').replace(/\s/g,'').length,0)
  const narrationChars = countChars(narrations)
  const dialogueChars = countChars(dialogues)
  const ratio = narrationChars + dialogueChars ? Math.round(narrationChars * 100 / (narrationChars + dialogueChars)) : 0
  const hasLong = narrations.some((line) => String(line.text || '').replace(/\s/g,'').length > 45)
  const hasConsecutive = (props.script?.scenes || []).some((scene) => (scene.lines || []).some((line,index,all) => index > 0 && (line.type === 'narration' || line.track === 'narration') && (all[index-1].type === 'narration' || all[index-1].track === 'narration')))
  const hasIssues = ratio > 18 || hasLong || hasConsecutive
  return {
    dialogueCount: dialogues.length, narrationRatio: ratio, soundCount, hasIssues,
    message: hasIssues ? '建议继续修改：减少长旁白或连续旁白，让声音和角色行动承担信息。' : '声音结构通过快速检查，可以继续逐场确认。',
  }
})
</script>

<style scoped>
.confirm-card { display:grid; gap:14px; padding:16px; border:1px solid color-mix(in srgb,var(--el-color-primary) 35%,var(--el-border-color)); border-radius:12px; background:color-mix(in srgb,var(--el-color-primary) 5%,var(--el-bg-color)); }
.confirm-card header,.confirm-card footer { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.confirm-card h3,.eyebrow { margin:0; }.confirm-card header p:not(.eyebrow){margin:6px 0 0;color:var(--el-text-color-secondary)}
.eyebrow { color:var(--el-color-primary); font-size:12px; }.scene-count{margin-left:10px;color:var(--el-text-color-secondary);font-size:12px}
.draft-audit{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--el-color-success) 28%,var(--el-border-color));border-radius:10px;background:color-mix(in srgb,var(--el-color-success) 5%,var(--el-bg-color));color:var(--el-text-color-secondary);font-size:12px}.draft-audit.warning{border-color:color-mix(in srgb,var(--el-color-warning) 42%,var(--el-border-color));background:color-mix(in srgb,var(--el-color-warning) 7%,var(--el-bg-color))}.audit-metrics{display:flex;gap:6px;flex:0 0 auto}
.line-list{display:grid;gap:8px}.line-list article{display:grid;grid-template-columns:auto minmax(64px,110px) 1fr;align-items:start;gap:8px}.line-list p{margin:0;line-height:1.6;overflow-wrap:anywhere}.line-list small{display:block;margin-top:4px;color:var(--el-text-color-secondary);line-height:1.45}.confirm-card footer{justify-content:flex-end}
@media(max-width:600px){.line-list article{grid-template-columns:auto 1fr}.line-list p{grid-column:1/-1}.confirm-card header,.draft-audit{display:grid}}
</style>
