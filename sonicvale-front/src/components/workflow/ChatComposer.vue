<template>
  <form class="composer" @submit.prevent="submit">
    <label for="workflow-feedback">告诉制作助手</label>
    <el-input id="workflow-feedback" v-model="message" type="textarea" :rows="3" resize="none" :disabled="disabled||loading" placeholder="可以询问进度，也可以修改角色、台词、音色或音频" />
    <div><span>助手只会调用当前项目内的受控工具</span><el-button native-type="submit" type="primary" plain :loading="loading" :disabled="disabled||loading||!message.trim()">发送</el-button></div>
  </form>
</template>
<script setup>
import { ref } from 'vue'
const props = defineProps({ loading: Boolean, disabled: Boolean })
const emit = defineEmits(['send'])
const message = ref('')
function submit(){ if(props.disabled || props.loading || !message.value.trim()) return; emit('send', message.value.trim()); message.value = '' }
</script>
<style scoped>
.composer{display:grid;gap:8px;padding:14px;border:1px solid var(--el-border-color-lighter);border-radius:10px;background:var(--el-bg-color)}.composer label{font-weight:600}.composer>div{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--el-text-color-secondary);font-size:12px}
@media(max-width:560px){.composer>div{align-items:stretch;flex-direction:column}}
</style>
