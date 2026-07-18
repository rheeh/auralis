<template>
  <section class="analysis-card">
    <header class="analysis-header">
      <div><p class="eyebrow">文章分析</p><h2>{{ analysis.title }}</h2><p>{{ analysis.summary }}</p></div>
      <div class="analysis-tags"><el-tag effect="plain">{{ analysis.category }}</el-tag><el-tag type="success" effect="plain">建议 {{ analysis.recommended_duration }} 分钟</el-tag></div>
    </header>
    <div class="analysis-grid">
      <section><h3>文章结构</h3><article v-for="section in analysis.sections || []" :key="section.id" class="section-row"><strong>{{ section.title }}</strong><p>{{ section.summary }}</p><small>{{ section.source_location }}</small></article></section>
      <section><h3>核心知识点</h3><article v-for="(point,index) in analysis.key_points || []" :key="point.id" class="knowledge-point">
        <div class="point-title"><span>{{ index+1 }}</span><div><strong>{{ point.title }}</strong><p>{{ point.one_sentence_summary || point.explanation }}</p></div><el-tag size="small" :type="point.is_ai_supplement?'warning':'info'" effect="plain">{{ originLabel(point.content_origin) }}</el-tag></div>
        <blockquote>{{ point.source_excerpt }}</blockquote>
        <small>{{ point.source_location || '原文位置未标注' }}</small>
      </article></section>
    </div>
    <footer class="outline-actions">
      <el-input v-model="feedback" type="textarea" :rows="2" resize="none" placeholder="例如：把第二个知识点讲得更适合没有技术背景的人" />
      <div><el-button :loading="loading" :disabled="!feedback.trim()" @click="$emit('revise',feedback)">按意见修改</el-button><el-button type="primary" :loading="loading" @click="$emit('confirm',analysis)">确认知识大纲</el-button></div>
    </footer>
  </section>
</template>

<script setup>
import { ref } from 'vue'
defineProps({analysis:{type:Object,required:true},loading:{type:Boolean,default:false}})
defineEmits(['confirm','revise'])
const feedback=ref('')
function originLabel(origin){return {fact_from_source:'原文事实',opinion_from_source:'原文观点',example_from_source:'原文案例',ai_explanation:'AI 解释',external_verified_fact:'外部资料',uncertain_claim:'待确认'}[origin]||'原文内容'}
</script>

<style scoped>
.analysis-card{display:grid;gap:18px;padding:18px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}.analysis-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.analysis-header h2,.analysis-header p,.eyebrow{margin:0}.analysis-header>div>p:last-child{margin-top:7px;color:var(--el-text-color-secondary);line-height:1.6}.eyebrow{margin-bottom:4px!important;color:var(--el-color-primary)!important;font-size:12px;text-transform:uppercase}.analysis-tags{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px}.analysis-grid{display:grid;grid-template-columns:minmax(220px,.7fr) minmax(0,1.3fr);gap:16px}.analysis-grid>section{display:grid;align-content:start;gap:10px}.analysis-grid h3{margin:0 0 2px;font-size:15px}.section-row,.knowledge-point{padding:12px;border:1px solid var(--el-border-color-light);border-radius:10px;background:var(--el-fill-color-extra-light)}.section-row p,.point-title p{margin:5px 0;color:var(--el-text-color-secondary);line-height:1.5}.section-row small,.knowledge-point>small{color:var(--el-text-color-secondary)}.point-title{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:9px;align-items:start}.point-title>span{display:grid;width:26px;height:26px;place-items:center;border-radius:8px;background:var(--el-color-primary);color:#fff;font-size:12px;font-weight:700}.knowledge-point blockquote{margin:9px 0 7px;padding:9px 11px;border-left:3px solid var(--el-color-primary-light-5);background:var(--el-bg-color);color:var(--el-text-color-regular);line-height:1.55}.outline-actions{display:grid;gap:10px;padding-top:14px;border-top:1px solid var(--el-border-color-light)}.outline-actions>div{display:flex;justify-content:flex-end;gap:8px}@media(max-width:900px){.analysis-header{flex-direction:column}.analysis-tags{justify-content:flex-start}.analysis-grid{grid-template-columns:1fr}}
</style>
