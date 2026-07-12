<template>
  <section class="error-card" role="alert">
    <div><strong>{{ title }}</strong><p>{{ message || '当前步骤执行失败。' }}</p><small>可以重试当前步骤；如仍失败，请检查项目的模型配置。</small></div>
    <el-button type="danger" plain :loading="loading" @click="$emit('retry')">重试当前步骤</el-button>
  </section>
</template>
<script setup>
defineProps({ title: { type: String, default: '制作流程遇到问题' }, message: String, loading: Boolean })
defineEmits(['retry'])
</script>
<style scoped>
.error-card{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px;border:1px solid color-mix(in srgb,var(--el-color-danger) 45%,var(--el-border-color));border-radius:12px;background:color-mix(in srgb,var(--el-color-danger) 7%,var(--el-bg-color))}.error-card p{margin:5px 0;color:var(--el-text-color-primary)}.error-card small{color:var(--el-text-color-secondary)}
@media(max-width:560px){.error-card{align-items:stretch;flex-direction:column}}
</style>
