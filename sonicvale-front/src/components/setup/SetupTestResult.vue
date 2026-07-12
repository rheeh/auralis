<template>
  <section v-if="result" class="test-result" :class="`is-${result.status}`" role="status">
    <div class="result-icon">
      <el-icon><CircleCheck v-if="result.status === 'success'" /><Warning v-else /></el-icon>
    </div>
    <div>
      <strong>{{ result.title }}</strong>
      <p>{{ result.message }}</p>
      <small v-if="result.suggestion">{{ result.suggestion }}</small>
      <pre v-if="result.sample">{{ result.sample }}</pre>
      <audio v-if="result.audioUrl" :src="result.audioUrl" controls />
    </div>
  </section>
</template>

<script setup>
import { CircleCheck, Warning } from '@element-plus/icons-vue'

defineProps({
  result: {
    type: Object,
    default: null,
  },
})
</script>

<style scoped>
.test-result {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.test-result.is-success {
  border-color: color-mix(in srgb, var(--el-color-success) 42%, var(--el-border-color-light));
  background: color-mix(in srgb, var(--el-color-success) 8%, var(--el-bg-color));
}

.test-result.is-error {
  border-color: color-mix(in srgb, var(--el-color-danger) 42%, var(--el-border-color-light));
  background: color-mix(in srgb, var(--el-color-danger) 7%, var(--el-bg-color));
}

.result-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-color-primary);
}

.test-result strong,
.test-result p,
.test-result small {
  display: block;
  margin: 0;
}

.test-result p {
  margin-top: 4px;
  color: var(--el-text-color-regular);
  line-height: 1.55;
}

.test-result small {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.test-result pre {
  max-height: 120px;
  margin: 10px 0 0;
  padding: 10px;
  overflow: auto;
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-size: 12px;
  line-height: 1.5;
}

.test-result audio {
  width: 100%;
  margin-top: 10px;
}
</style>
