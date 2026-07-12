<template>
  <section class="progress-stepper" aria-label="制作流程">
    <article v-for="step in steps" :key="step.key" :class="`is-${step.status}`">
      <span class="step-dot"></span>
      <div>
        <strong>{{ step.title }}</strong>
        <p>{{ step.caption }}</p>
        <small>{{ step.metric }}</small>
      </div>
      <el-button size="small" :type="step.status === 'current' ? 'primary' : 'default'" @click="$emit('open', step)">
        去处理
      </el-button>
    </article>
  </section>
</template>

<script setup>
defineProps({
  steps: {
    type: Array,
    required: true,
  },
})

defineEmits(['open'])
</script>

<style scoped>
.progress-stepper {
  display: grid;
  gap: 10px;
}

.progress-stepper article {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.step-dot {
  width: 12px;
  height: 12px;
  border: 3px solid var(--el-border-color);
  border-radius: 999px;
}

.is-complete .step-dot {
  border-color: var(--el-color-success);
  background: var(--el-color-success);
}

.is-current {
  border-color: color-mix(in srgb, var(--el-color-primary) 45%, var(--el-border-color-light));
  background: color-mix(in srgb, var(--el-color-primary) 6%, var(--el-bg-color));
}

.is-current .step-dot {
  border-color: var(--el-color-primary);
}

.is-issue .step-dot {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning);
}

.progress-stepper strong,
.progress-stepper p,
.progress-stepper small {
  display: block;
  margin: 0;
}

.progress-stepper p {
  margin-top: 3px;
  color: var(--el-text-color-regular);
  line-height: 1.45;
}

.progress-stepper small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 720px) {
  .progress-stepper article {
    grid-template-columns: 18px minmax(0, 1fr);
  }

  .progress-stepper .el-button {
    grid-column: 2;
    justify-self: start;
  }
}
</style>
