<template>
  <section class="stats-grid" aria-label="项目关键数量">
    <article v-for="item in stats" :key="item.label">
      <el-icon><component :is="item.icon" /></el-icon>
      <strong>{{ item.value }}</strong>
      <span>{{ item.label }}</span>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { ChatLineRound, Collection, Headset, Tickets } from '@element-plus/icons-vue'

const props = defineProps({
  counts: {
    type: Object,
    default: () => ({}),
  },
})

const stats = computed(() => [
  { label: '章节', value: props.counts.chapters || 0, icon: Tickets },
  { label: '台词', value: props.counts.lines || 0, icon: ChatLineRound },
  { label: '角色', value: props.counts.roles || 0, icon: Collection },
  { label: '待配音', value: props.counts.missing_speakable_audio_lines || 0, icon: Headset },
])
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stats-grid article {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  gap: 2px 10px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.stats-grid .el-icon {
  grid-row: span 2;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-primary) 10%, transparent);
  color: var(--el-color-primary);
}

.stats-grid strong {
  font-size: 22px;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.stats-grid span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
