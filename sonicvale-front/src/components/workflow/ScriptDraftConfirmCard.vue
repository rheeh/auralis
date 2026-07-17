<template>
  <section class="confirm-card" aria-labelledby="script-card-title">
    <header>
      <div><p class="eyebrow">{{ reviewing ? '审查进行中 · 初稿已可阅读' : '需要确认' }}</p><h3 id="script-card-title">{{ displayScript?.title || '剧本草稿' }}</h3><p>{{ displayScript?.logline }}</p></div>
      <div class="revision-picker" v-if="revisions.length">
        <el-select v-model="selectedRevision" size="small" aria-label="选择台本版本">
          <el-option v-for="item in revisions" :key="item.revision" :label="`${item.label} · v${item.revision}`" :value="item.revision" />
        </el-select>
        <el-tag size="small" :type="activeVersion?.status==='reviewing'?'warning':displayReview?.passed?'success':'info'">
          {{ activeVersion?.status==='reviewing'?'正在审查':displayReview?.passed?'审查通过':'已保留' }}
        </el-tag>
      </div>
      <DraftRevisionBar v-else :revision="revision" />
    </header>
    <div v-if="reviewing && activeVersion?.status==='reviewing'" class="review-progress">
      <el-icon class="is-loading"><Loading /></el-icon>
      <div><strong>AI 正在独立审查这一版</strong><span>你可以先阅读台本；审查完成或生成返修稿后，版本会自动保留在上方。</span></div>
    </div>
    <div class="draft-audit" :class="{ warning: audit.hasIssues }">
      <div class="audit-metrics">
        <el-tag size="small" effect="plain">对白 {{ audit.dialogueCount }}</el-tag>
        <el-tag size="small" effect="plain" :type="audit.narrationRatio > 18 ? 'warning' : 'success'">旁白 {{ audit.narrationRatio }}%</el-tag>
        <el-tag size="small" effect="plain" type="info">声音轨 {{ audit.soundCount }}</el-tag>
      </div>
      <span>{{ audit.message }}</span>
    </div>
    <section v-if="displayReview" class="ai-review" :class="{passed:displayReview.passed}">
      <header><div><strong>AI 独立审查</strong><span>{{ displayReview.repair_applied ? '已自动返修并复核' : '已完成规范复核' }}</span></div><el-tag :type="displayReview.passed?'success':'warning'" effect="dark">{{ displayReview.score }} 分 · {{ displayReview.passed?'通过':'需关注' }}</el-tag></header>
      <p>{{ displayReview.summary || (displayReview.passed?'剧本符合声音优先改编规范。':'仍有部分声音表达需要人工确认。') }}</p>
      <ul v-if="displayReview.issues?.length"><li v-for="(issue,index) in displayReview.issues.slice(0,5)" :key="index"><el-tag size="small" :type="issue.severity==='error'?'danger':issue.severity==='warning'?'warning':'info'">{{ issue.category }}</el-tag><span>{{ issue.evidence }}<template v-if="issue.suggestion"> · {{ issue.suggestion }}</template></span></li></ul>
    </section>
    <el-collapse accordion>
      <el-collapse-item v-for="(scene,index) in displayScript?.scenes || []" :key="index" :name="index">
        <template #title><strong>第 {{ index+1 }} 场 · {{ scene.title }}</strong><span class="scene-count">{{ scene.lines?.length || 0 }} 行</span></template>
        <div class="line-list">
          <article v-for="(line,lineIndex) in scene.lines" :key="lineIndex">
            <el-tag size="small" effect="plain">{{ trackLabel(line.track) }}</el-tag><strong>{{ line.speaker }}</strong><div><p>{{ displayText(line) }}</p><small v-if="line.productionNote">制作提示：{{ line.productionNote }}</small><small v-for="(event,eventIndex) in line.audioEvents || []" :key="eventIndex">{{ event.timing }} · {{ event.type }} · {{ event.content }} · {{ event.volume_db }}</small></div>
          </article>
        </div>
      </el-collapse-item>
    </el-collapse>
    <footer><span v-if="activeVersion?.feedback" class="revision-feedback">本版依据：{{ activeVersion.feedback }}</span><el-button v-if="canConfirm" type="primary" :loading="loading" @click="$emit('confirm',displayScript)">选用此版本，{{ confirmLabel || '确认剧本并准备写入项目' }}</el-button></footer>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import DraftRevisionBar from './DraftRevisionBar.vue'
const props = defineProps({ script: Object, review: Object, revision: Number, revisions: {type:Array,default:()=>[]}, reviewing: Boolean, canConfirm: {type:Boolean,default:true}, loading: Boolean, confirmLabel: String })
defineEmits(['confirm'])
const selectedRevision = ref(props.revision || 0)
watch(() => props.revisions.map(item=>item.revision).join(','), () => {
  selectedRevision.value = props.revisions.at(-1)?.revision || props.revision || 0
}, {immediate:true})
const activeVersion = computed(() => props.revisions.find(item=>item.revision===selectedRevision.value) || props.revisions.at(-1) || null)
const displayScript = computed(() => activeVersion.value?.script || props.script)
const displayReview = computed(() => activeVersion.value?.review || ((!activeVersion.value || activeVersion.value.revision===props.revision) ? props.review : null))
function trackLabel(track) { return { voice:'人物', narration:'旁白', sfx:'音效', bgm:'BGM' }[track] || track }
function displayText(line) { return line.text || line.soundPrompt || line.productionNote || '缺少声音提示，请让 AI 补充' }
const audit = computed(() => {
  const lines = (displayScript.value?.scenes || []).flatMap((scene) => scene.lines || [])
  const dialogues = lines.filter((line) => line.type === 'dialogue' || line.track === 'voice')
  const narrations = lines.filter((line) => line.type === 'narration' || line.track === 'narration')
  const soundCount = lines.filter((line) => ['sfx','bgm'].includes(line.type) || ['sfx','bgm'].includes(line.track)).length
  const countChars = (items) => items.reduce((sum,line) => sum + String(line.text || '').replace(/\s/g,'').length,0)
  const narrationChars = countChars(narrations)
  const dialogueChars = countChars(dialogues)
  const ratio = narrationChars + dialogueChars ? Math.round(narrationChars * 100 / (narrationChars + dialogueChars)) : 0
  const hasLong = narrations.some((line) => String(line.text || '').replace(/\s/g,'').length > 45)
  const hasConsecutive = (displayScript.value?.scenes || []).some((scene) => (scene.lines || []).some((line,index,all) => index > 0 && (line.type === 'narration' || line.track === 'narration') && (all[index-1].type === 'narration' || all[index-1].track === 'narration')))
  const hasIssues = ratio > 18 || hasLong || hasConsecutive
  return {
    dialogueCount: dialogues.length, narrationRatio: ratio, soundCount, hasIssues,
    message: hasIssues ? '建议继续修改：减少长旁白或连续旁白，让声音和角色行动承担信息。' : '声音结构通过快速检查，可以继续逐场确认。',
  }
})
</script>

<style scoped>
.confirm-card { display:grid; grid-template-columns:minmax(0,1fr); min-width:0; gap:14px; padding:16px; border:1px solid color-mix(in srgb,var(--el-color-primary) 35%,var(--el-border-color)); border-radius:12px; background:color-mix(in srgb,var(--el-color-primary) 5%,var(--el-bg-color)); }
.confirm-card>*{min-width:0}
.confirm-card header,.confirm-card footer { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.confirm-card header>div:first-child{min-width:0}
.confirm-card h3,.eyebrow { margin:0; }.confirm-card header p:not(.eyebrow){margin:6px 0 0;color:var(--el-text-color-secondary)}
.eyebrow { color:var(--el-color-primary); font-size:12px; }.scene-count{margin-left:10px;color:var(--el-text-color-secondary);font-size:12px}
.revision-picker{display:flex;align-items:center;gap:8px;min-width:230px}.revision-picker .el-select{flex:1}.review-progress{display:flex;align-items:center;gap:10px;padding:11px 12px;border:1px solid color-mix(in srgb,var(--el-color-primary) 38%,var(--el-border-color));border-radius:10px;background:color-mix(in srgb,var(--el-color-primary) 7%,var(--el-bg-color));color:var(--el-color-primary)}.review-progress div{display:grid;gap:2px}.review-progress span,.revision-feedback{color:var(--el-text-color-secondary);font-size:12px}.revision-feedback{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.draft-audit{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid color-mix(in srgb,var(--el-color-success) 28%,var(--el-border-color));border-radius:10px;background:color-mix(in srgb,var(--el-color-success) 5%,var(--el-bg-color));color:var(--el-text-color-secondary);font-size:12px}.draft-audit.warning{border-color:color-mix(in srgb,var(--el-color-warning) 42%,var(--el-border-color));background:color-mix(in srgb,var(--el-color-warning) 7%,var(--el-bg-color))}.audit-metrics{display:flex;gap:6px;flex:0 0 auto}
.ai-review{display:grid;gap:8px;padding:11px 12px;border:1px solid color-mix(in srgb,var(--el-color-warning) 38%,var(--el-border-color));border-radius:10px;background:color-mix(in srgb,var(--el-color-warning) 6%,var(--el-bg-color))}.ai-review.passed{border-color:color-mix(in srgb,var(--el-color-success) 34%,var(--el-border-color));background:color-mix(in srgb,var(--el-color-success) 6%,var(--el-bg-color))}.ai-review header{align-items:center}.ai-review header div strong,.ai-review header div span{display:block}.ai-review header div span{margin-top:2px;color:var(--el-text-color-secondary);font-size:11px}.ai-review p{margin:0;color:var(--el-text-color-secondary);font-size:12px;line-height:1.55}.ai-review ul{display:grid;gap:6px;margin:0;padding:0;list-style:none}.ai-review li{display:flex;align-items:flex-start;gap:7px;color:var(--el-text-color-secondary);font-size:11px;line-height:1.5}.ai-review li span{min-width:0;overflow-wrap:anywhere}
.line-list{display:grid;gap:8px}.line-list article{display:grid;grid-template-columns:auto minmax(64px,110px) 1fr;align-items:start;gap:8px}.line-list p{margin:0;line-height:1.6;overflow-wrap:anywhere}.line-list small{display:block;margin-top:4px;color:var(--el-text-color-secondary);line-height:1.45}.confirm-card footer{justify-content:flex-end}
@media(max-width:600px){.line-list article{grid-template-columns:auto 1fr}.line-list p{grid-column:1/-1}.confirm-card header,.draft-audit{display:grid}.revision-picker{min-width:0;width:100%}}
</style>
