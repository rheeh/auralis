<template>
  <section class="script-card">
    <header class="script-header">
      <div><p class="eyebrow">知识音频脚本</p><h2>{{ script.title }}</h2><p>{{ modeLabel(script.adaptation_mode) }} · {{ script.roles?.length || 0 }} 个声音 · {{ lineCount }} 条内容</p></div>
      <el-tag :type="review?.passed?'success':review?'warning':'info'" effect="dark">{{ reviewing?'独立审查中':review?.passed?'审查通过':review?'需要检查':'初稿' }}</el-tag>
    </header>
    <div class="script-layout">
      <main class="segments">
        <article v-for="segment in script.segments || []" :key="segment.id" class="segment">
          <header><div><small>{{ segmentTypeLabel(segment.segment_type) }}</small><h3>{{ segment.title }}</h3></div><div><el-tag v-for="id in segment.knowledge_point_ids || []" :key="id" size="small" effect="plain">{{ id }}</el-tag></div></header>
          <div v-for="(line,index) in segment.lines || []" :key="index" class="script-line" :class="`track-${line.track}`">
            <strong>{{ line.speaker }}</strong><p>{{ line.text }}</p><small>{{ originLabel(line.content_origin) }}</small>
          </div>
        </article>
      </main>
      <aside class="review-panel">
        <template v-if="review">
          <h3>三维审查</h3>
          <div class="score-grid"><span>准确性<strong>{{ review.accuracy_score }}</strong></span><span>学习质量<strong>{{ review.learning_quality_score }}</strong></span><span>音频表现<strong>{{ review.audio_quality_score }}</strong></span></div>
          <p>{{ review.summary }}</p>
          <article v-for="(issue,index) in review.issues || []" :key="index" class="review-issue"><strong>{{ issue.category || '审查建议' }}</strong><p>{{ issue.message || issue.evidence || issue.suggestion }}</p></article>
          <el-alert v-if="review.unmarked_supplements?.length" title="发现未标记补充内容" type="warning" :closable="false" />
        </template>
        <template v-else><el-skeleton :rows="5" animated /></template>
        <h3>听后复习</h3>
        <article v-for="(question,index) in script.review_questions || []" :key="question.id" class="question"><strong>{{ index+1 }}. {{ question.question }}</strong><details><summary>查看答案与依据</summary><p>{{ question.answer }}</p><blockquote>{{ question.source_excerpt }}</blockquote></details></article>
      </aside>
    </div>
    <footer v-if="canConfirm" class="script-actions"><el-input v-model="feedback" type="textarea" :rows="2" resize="none" placeholder="例如：删除所有不是原文内容的补充，第二段讲得更通俗" /><div><el-button :loading="loading" :disabled="!feedback.trim()" @click="$emit('revise',feedback)">按意见修改</el-button><el-button type="primary" :loading="loading" @click="$emit('confirm',script)">确认知识脚本</el-button></div></footer>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
const props=defineProps({script:{type:Object,required:true},review:Object,reviewing:{type:Boolean,default:false},canConfirm:{type:Boolean,default:false},loading:{type:Boolean,default:false}})
defineEmits(['confirm','revise'])
const feedback=ref('')
const lineCount=computed(()=>props.script.segments?.reduce((sum,item)=>sum+(item.lines?.length||0),0)||0)
function modeLabel(value){return {audio_lesson:'主持人讲解',dialogue_lesson:'主持人与学习者对话',knowledge_drama:'案例化知识剧场'}[value]||value}
function segmentTypeLabel(value){return {opening:'开场',knowledge_point:'知识点',case:'案例',summary:'总结',review:'复习'}[value]||value}
function originLabel(value){return {fact_from_source:'原文事实',opinion_from_source:'原文观点',example_from_source:'原文案例',ai_explanation:'AI 解释',external_verified_fact:'外部资料',uncertain_claim:'待确认'}[value]||'原文内容'}
</script>

<style scoped>
.script-card{display:grid;gap:18px;padding:18px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}.script-header,.segment>header,.script-actions>div{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.script-header h2,.script-header p,.segment h3,.eyebrow{margin:0}.script-header>div>p:last-child{margin-top:6px;color:var(--el-text-color-secondary)}.eyebrow{margin-bottom:4px!important;color:var(--el-color-primary)!important;font-size:12px;text-transform:uppercase}.script-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:16px}.segments,.review-panel{display:grid;align-content:start;gap:12px}.segment,.review-panel{padding:13px;border:1px solid var(--el-border-color-light);border-radius:10px;background:var(--el-fill-color-extra-light)}.segment>header>div:last-child{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px}.segment header small{color:var(--el-color-primary)}.script-line{display:grid;grid-template-columns:90px minmax(0,1fr) auto;gap:10px;margin-top:9px;padding:9px 10px;border-radius:8px;background:var(--el-bg-color)}.script-line p{margin:0;line-height:1.55}.script-line small{color:var(--el-text-color-secondary)}.track-sfx,.track-bgm{border-left:3px solid var(--el-color-warning)}.review-panel h3,.review-panel p{margin:0}.score-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.score-grid span{display:grid;gap:3px;padding:8px;border-radius:8px;background:var(--el-bg-color);color:var(--el-text-color-secondary);font-size:11px}.score-grid strong{color:var(--el-text-color-primary);font-size:18px}.review-issue,.question{padding:9px;border-radius:8px;background:var(--el-bg-color)}.review-issue p,.question p{margin:5px 0;line-height:1.5}.question summary{margin-top:6px;color:var(--el-color-primary);cursor:pointer}.question blockquote{margin:6px 0 0;padding-left:8px;border-left:2px solid var(--el-color-primary-light-5);color:var(--el-text-color-secondary)}.script-actions{display:grid;gap:10px;padding-top:14px;border-top:1px solid var(--el-border-color-light)}@media(max-width:1000px){.script-layout{grid-template-columns:1fr}}@media(max-width:700px){.script-header,.segment>header,.script-actions>div{flex-direction:column}.script-line{grid-template-columns:1fr}.score-grid{grid-template-columns:1fr}}
</style>
