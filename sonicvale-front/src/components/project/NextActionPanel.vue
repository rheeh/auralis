<template>
  <section class="next-action-panel">
    <div>
      <p class="eyebrow">下一步</p>
      <h2>{{ action.title }}</h2>
      <p>{{ action.detail }}</p>
    </div>
    <el-button type="primary" size="large" :icon="action.icon" @click="$emit('run', action)">
      {{ action.label }}
    </el-button>
  </section>
</template>

<script setup>
defineProps({
  action: {
    type: Object,
    required: true,
  },
})

defineEmits(['run'])
</script>

<style scoped>
.next-action-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 30%, var(--el-border-color-light));
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--el-color-primary) 12%, transparent), transparent),
    var(--el-bg-color);
}

.next-action-panel h2,
.next-action-panel p {
  margin: 0;
}

.next-action-panel h2 {
  font-size: 20px;
  letter-spacing: 0;
}

.next-action-panel p:not(.eyebrow) {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

@media (max-width: 720px) {
  .next-action-panel {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
