<template>
  <section class="content-type-selector" aria-labelledby="content-type-title">
    <div class="selector-heading">
      <div><p class="eyebrow">内容类型</p><h2 id="content-type-title">新建制作</h2></div>
      <span>选择后使用独立工作流</span>
    </div>
    <div class="type-grid">
      <button
        v-for="option in options" :key="option.value" type="button" class="type-card"
        :class="{ active:modelValue===option.value, disabled:option.disabled }" :disabled="option.disabled"
        @click="$emit('update:modelValue',option.value)"
      >
        <span class="type-icon" aria-hidden="true">{{ option.icon }}</span>
        <span class="type-copy"><strong>{{ option.title }}</strong><small>{{ option.description }}</small></span>
        <el-tag v-if="option.disabled" size="small" effect="plain">功能开关未开启</el-tag>
        <el-tag v-else-if="modelValue===option.value" size="small" type="primary" effect="dark">已选择</el-tag>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props=defineProps({modelValue:{type:String,default:'novel'},knowledgeArticleEnabled:{type:Boolean,default:false}})
defineEmits(['update:modelValue'])
const options=computed(()=>[
  {value:'novel',title:'小说广播剧',description:'解析人物和情节，制作角色化广播剧',icon:'剧',disabled:false},
  {value:'knowledge_article',title:'知识文章音频',description:'提炼核心观点，制作可听、可复习的知识音频',icon:'知',disabled:!props.knowledgeArticleEnabled},
])
</script>

<style scoped>
.content-type-selector{display:grid;gap:12px;padding:16px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}.selector-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:12px}.selector-heading h2,.eyebrow{margin:0}.selector-heading h2{font-size:18px}.selector-heading>span{color:var(--el-text-color-secondary);font-size:12px}.eyebrow{margin-bottom:4px;color:var(--el-color-primary);font-size:12px;text-transform:uppercase}.type-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.type-card{display:flex;align-items:center;gap:12px;min-height:88px;padding:14px;border:1px solid var(--el-border-color);border-radius:11px;background:var(--el-fill-color-blank);color:inherit;text-align:left;cursor:pointer;transition:border-color .18s ease,background .18s ease,transform .18s ease}.type-card:hover:not(.disabled){border-color:var(--el-color-primary);transform:translateY(-1px)}.type-card.active{border-color:var(--el-color-primary);background:color-mix(in srgb,var(--el-color-primary) 7%,var(--el-bg-color))}.type-card.disabled{cursor:not-allowed;opacity:.62}.type-icon{display:grid;flex:0 0 42px;width:42px;height:42px;place-items:center;border-radius:10px;background:var(--el-fill-color-light);color:var(--el-color-primary);font-size:17px;font-weight:700}.type-copy{display:grid;flex:1;gap:5px}.type-copy small{color:var(--el-text-color-secondary);line-height:1.45}@media(max-width:720px){.type-grid{grid-template-columns:1fr}.selector-heading{align-items:flex-start;flex-direction:column}}
</style>
