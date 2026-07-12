<template>
  <div class="wizard-shell">
    <aside class="wizard-rail">
      <RouterLink to="/home" class="brand-link" aria-label="返回首页">
        <span class="mark"><img src="/auralis-mark.svg" alt="" aria-hidden="true" /></span>
        <strong>Auralis</strong>
      </RouterLink>

      <ol class="step-list" aria-label="首次配置步骤">
        <li
          v-for="(step, index) in steps"
          :key="step.key"
          :class="{ active: index === activeIndex, done: index < activeIndex }"
        >
          <span>{{ index + 1 }}</span>
          <div>
            <strong>{{ step.title }}</strong>
            <small>{{ step.caption }}</small>
          </div>
        </li>
      </ol>
    </aside>

    <main class="wizard-main">
      <header class="wizard-header">
        <div>
          <p class="eyebrow">{{ currentStep.caption }}</p>
          <h1>{{ currentStep.title }}</h1>
        </div>
        <el-button text @click="$emit('skip')">稍后配置</el-button>
      </header>

      <section class="wizard-content">
        <slot />
      </section>

      <footer class="wizard-footer">
        <el-button :disabled="activeIndex === 0" @click="$emit('back')">上一步</el-button>
        <slot name="footer" />
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: {
    type: Array,
    required: true,
  },
  activeIndex: {
    type: Number,
    required: true,
  },
})

defineEmits(['back', 'skip'])

const currentStep = computed(() => props.steps[props.activeIndex] || props.steps[0])
</script>

<style scoped>
.wizard-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: calc(100vh - 104px);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  overflow: hidden;
  background: var(--el-bg-color);
  box-shadow: 0 18px 46px rgba(15, 23, 42, 0.08);
}

.wizard-rail {
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 22px;
  background:
    linear-gradient(180deg, rgba(31, 183, 201, 0.14), transparent 42%),
    var(--el-fill-color-lighter);
  border-right: 1px solid var(--el-border-color-light);
}

.brand-link {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--el-text-color-primary);
  text-decoration: none;
}

.mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #a7f3df, #83dcff);
}

.mark img {
  width: 100%;
  height: 100%;
}

.step-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step-list li {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--el-text-color-secondary);
}

.step-list li > span {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: var(--el-bg-color);
  font-weight: 700;
}

.step-list li.active {
  color: var(--el-text-color-primary);
  border-color: color-mix(in srgb, var(--el-color-primary) 38%, transparent);
  background: var(--el-bg-color);
}

.step-list li.done > span {
  color: #0f1720;
  background: linear-gradient(135deg, #a7f3df, #83dcff);
}

.step-list strong,
.step-list small {
  display: block;
  min-width: 0;
}

.step-list small {
  margin-top: 3px;
  line-height: 1.4;
}

.wizard-main {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
}

.wizard-header,
.wizard-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.wizard-footer {
  justify-content: flex-end;
  border-top: 1px solid var(--el-border-color-light);
  border-bottom: 0;
}

.wizard-header h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.2;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.wizard-content {
  min-width: 0;
  padding: 22px;
  overflow: auto;
}

@media (max-width: 860px) {
  .wizard-shell {
    grid-template-columns: 1fr;
  }

  .wizard-rail {
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-light);
  }

  .step-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
