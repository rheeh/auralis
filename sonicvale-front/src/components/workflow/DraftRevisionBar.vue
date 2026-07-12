<template>
  <div class="revision-bar">
    <span>草稿版本 {{ revision || 1 }}</span>
    <span v-if="updatedAt">更新于 {{ updatedAt }}</span>
    <el-tag size="small" effect="plain">确认前不会写入项目</el-tag>
  </div>
</template>

<script setup>
defineProps({ revision: Number, updatedAt: String })
</script>

<style scoped>
.revision-bar { display:flex; align-items:center; flex-wrap:wrap; gap:8px; color:var(--el-text-color-secondary); font-size:12px; }
</style>
