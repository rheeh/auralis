<template>
  <section class="message-list" aria-live="polite">
    <article v-for="item in messages" :key="item.id" :class="item.role">
      <div class="bubble"><p>{{ item.content }}</p><small>{{ item.role==='user' ? '你' : 'Auralis' }} · {{ formatTime(item.created_at) }}</small></div>
    </article>
    <el-empty v-if="!messages.length" description="创建会话后，制作记录会显示在这里" :image-size="56" />
  </section>
</template>
<script setup>
defineProps({ messages: { type: Array, default: () => [] } })
function formatTime(value){ return value ? new Date(value).toLocaleString('zh-CN',{hour:'2-digit',minute:'2-digit'}) : '' }
</script>
<style scoped>
.message-list{display:grid;gap:10px;padding:2px}.message-list article{display:flex;width:100%}.message-list article.assistant{justify-content:flex-start}.message-list article.user{justify-content:flex-end}.bubble{position:relative;max-width:84%;padding:9px 11px;border-radius:4px 14px 14px 14px;background:var(--el-fill-color-light);box-shadow:0 3px 10px rgba(28,34,64,.05)}.user .bubble{border-radius:14px 4px 14px 14px;color:#17202d;background:linear-gradient(135deg,#a9f1f1,#e9b5e3)}.message-list p{margin:0;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.message-list small{display:block;margin-top:4px;color:var(--el-text-color-placeholder);font-size:10px}.user small{text-align:right;color:rgba(23,32,45,.55)}
</style>
