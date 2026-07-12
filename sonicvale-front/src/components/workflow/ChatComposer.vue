<template>
  <form class="composer" @submit.prevent="submit">
    <label for="workflow-feedback">修改意见</label>
    <el-input id="workflow-feedback" v-model="message" type="textarea" :rows="3" resize="none" :disabled="disabled" placeholder="例如：让主角表达更克制，第二场只改冲突台词" />
    <div><span>修改会保留为新草稿版本</span><el-button native-type="submit" type="primary" plain :loading="loading" :disabled="disabled||!message.trim()">发送修改意见</el-button></div>
  </form>
</template>
<script setup>
import { ref } from 'vue'
const props = defineProps({ loading: Boolean, disabled: Boolean })
const emit = defineEmits(['send'])
const message = ref('')
function submit(){ if(props.disabled || !message.value.trim()) return; emit('send', message.value.trim()); message.value = '' }
</script>
<style scoped>
.composer{display:grid;gap:8px;padding:14px;border:1px solid var(--el-border-color-lighter);border-radius:10px;background:var(--el-bg-color)}.composer label{font-weight:600}.composer>div{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--el-text-color-secondary);font-size:12px}
@media(max-width:560px){.composer>div{align-items:stretch;flex-direction:column}}
</style>
