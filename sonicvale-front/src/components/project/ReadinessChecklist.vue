<template>
  <section class="readiness-card">
    <header>
      <div>
        <p class="eyebrow">智能检查</p>
        <h2>制作体检清单</h2>
      </div>
      <el-button size="small" :loading="loading" @click="$emit('refresh')">重新扫描</el-button>
    </header>

    <div v-if="items.length" class="issue-list">
      <article v-for="item in items" :key="item.key" :class="`level-${item.level}`">
        <span class="issue-marker"></span>
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.detail }}</p>
        </div>
        <el-button size="small" :type="item.level === 'danger' ? 'danger' : 'primary'" plain @click="$emit('action', item)">
          {{ item.actionLabel }}
        </el-button>
      </article>
    </div>

    <el-empty v-else description="当前没有阻塞制作的问题" :image-size="74" />
  </section>
</template>

<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['refresh', 'action'])
</script>

<style scoped>
.readiness-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.readiness-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.readiness-card h2 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.issue-list {
  display: grid;
  gap: 10px;
}

.issue-list article {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.issue-marker {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--el-color-info);
}

.level-danger .issue-marker {
  background: var(--el-color-danger);
}

.level-warning .issue-marker {
  background: var(--el-color-warning);
}

.issue-list strong,
.issue-list p {
  display: block;
  margin: 0;
}

.issue-list p {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

@media (max-width: 720px) {
  .issue-list article {
    grid-template-columns: 10px minmax(0, 1fr);
  }

  .issue-list .el-button {
    grid-column: 2;
    justify-self: start;
  }
}
</style>
