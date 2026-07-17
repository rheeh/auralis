<template>
  <section class="message-list" aria-live="polite">
    <article v-for="item in messages" :key="item.id" :class="item.role">
      <div class="bubble"><p>{{ item.content }}</p><div v-if="item.payload?.tool_results?.length" class="tool-summary"><span v-for="tool in item.payload.tool_results" :key="`${tool.tool}-${JSON.stringify(tool.arguments)}`">{{ toolLabel(tool.tool) }}</span></div><small>{{ item.role==='user' ? '你' : 'Auralis' }} · {{ formatTime(item.created_at) }}</small></div>
    </article>
    <el-empty v-if="!messages.length" description="创建会话后，制作记录会显示在这里" :image-size="56" />
  </section>
</template>
<script setup>
defineProps({ messages: { type: Array, default: () => [] } })
function formatTime(value){ return value ? new Date(value).toLocaleString('zh-CN',{hour:'2-digit',minute:'2-digit'}) : '' }
function toolLabel(name){return{get_project_status:'检查项目',list_roles_and_voices:'读取角色音色',inspect_lines:'查询台词',revise_current_draft:'修改草稿',update_line:'更新台词',bind_role_voice:'绑定音色',generate_missing_audio:'生成缺失音频',regenerate_line_audio:'重新生成',retry_failed_audio:'重试失败任务',play_audio:'播放音频'}[name]||name}
</script>
<style scoped>
.message-list{display:grid;gap:10px;padding:2px}.message-list article{display:flex;width:100%}.message-list article.assistant{justify-content:flex-start}.message-list article.user{justify-content:flex-end}.bubble{position:relative;max-width:84%;padding:9px 11px;border:1px solid var(--el-border-color-lighter);border-radius:4px 14px 14px 14px;background:var(--el-fill-color-light);box-shadow:0 2px 8px rgba(28,34,64,.035)}.user .bubble{border-color:color-mix(in srgb,var(--el-color-primary) 18%,var(--el-border-color-lighter));border-radius:14px 4px 14px 14px;color:var(--el-text-color-primary);background:color-mix(in srgb,var(--el-color-primary) 10%,var(--el-bg-color))}.message-list p{margin:0;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.message-list small{display:block;margin-top:4px;color:var(--el-text-color-placeholder);font-size:10px}.user small{text-align:right;color:var(--el-text-color-secondary)}
.tool-summary{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}.tool-summary span{padding:2px 6px;border:1px solid var(--el-border-color);border-radius:999px;color:var(--el-text-color-secondary);background:var(--el-bg-color);font-size:9px}
</style>
