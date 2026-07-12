<template><el-alert v-if="visible" title="已恢复上次制作进度" :description="description" type="info" show-icon :closable="false" /></template>
<script setup>
defineProps({ visible: Boolean, description: { type: String, default: '草稿和待确认步骤已从检查点恢复，可以继续制作。' } })
</script>
