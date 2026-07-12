<template>
  <div class="setup-page">
    <SetupWizardShell
      :steps="steps"
      :active-index="activeIndex"
      @back="goBack"
      @skip="skipSetup"
    >
      <template v-if="activeStep.key === 'welcome'">
        <section class="mode-grid" aria-label="选择使用方式">
          <button
            v-for="mode in modes"
            :key="mode.key"
            type="button"
            class="mode-card"
            :class="{ active: selectedMode === mode.key }"
            @click="selectMode(mode.key)"
          >
            <el-icon><component :is="mode.icon" /></el-icon>
            <strong>{{ mode.title }}</strong>
            <small>{{ mode.caption }}</small>
          </button>
        </section>
      </template>

      <LLMSetupStep v-else-if="activeStep.key === 'llm'" @saved="handleLLMSaved" />
      <TTSSetupStep v-else-if="activeStep.key === 'tts'" @saved="handleTTSSaved" @skipped="goNext" />
      <StorageSetupStep v-else-if="activeStep.key === 'storage'" @saved="handleStorageSaved" />

      <section v-else class="finish-panel">
        <div class="finish-status-grid">
          <article v-for="item in finishItems" :key="item.label">
            <span :class="`dot dot-${item.type}`"></span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.value }}</small>
          </article>
        </div>

        <div class="finish-actions">
          <el-button type="primary" size="large" :icon="Plus" @click="router.push('/projects')">创建第一个广播剧项目</el-button>
          <el-button size="large" :icon="VideoPlay" :loading="isCreatingDemo" @click="openDemo">体验 Demo 工程</el-button>
          <el-button size="large" @click="router.push('/home')">进入首页</el-button>
        </div>
      </section>

      <template #footer>
        <el-button v-if="activeStep.key === 'welcome'" type="primary" @click="confirmMode">继续</el-button>
        <el-button v-else-if="activeStep.key !== 'finish'" @click="goNext">跳过这一步</el-button>
      </template>
    </SetupWizardShell>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock, MagicStick, Plus, Setting, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import LLMSetupStep from '../components/setup/LLMSetupStep.vue'
import SetupWizardShell from '../components/setup/SetupWizardShell.vue'
import StorageSetupStep from '../components/setup/StorageSetupStep.vue'
import TTSSetupStep from '../components/setup/TTSSetupStep.vue'
import { createDemoProject, fetchSetupSnapshot, markSetupSkipped } from '../api/setup'

const router = useRouter()
const activeIndex = ref(0)
const selectedMode = ref('quick')
const snapshot = ref(null)
const isCreatingDemo = ref(false)

const steps = [
  { key: 'welcome', title: '欢迎与模式选择', caption: '选择你想怎样开始' },
  { key: 'llm', title: '选择 AI 改编模型', caption: '测试小说改编能力' },
  { key: 'tts', title: '选择配音方式', caption: '测试并试听示例音频' },
  { key: 'storage', title: '项目保存位置', caption: '设置素材和导出目录' },
  { key: 'finish', title: '配置完成', caption: '进入制作流程' },
]

const modes = [
  {
    key: 'quick',
    title: '快速体验',
    caption: '创建 Demo 工程，使用 Edge-TTS 或占位流程跑通制作。',
    icon: VideoPlay,
  },
  {
    key: 'formal',
    title: '正式制作',
    caption: '配置 AI 改编模型、配音方式和项目保存位置。',
    icon: MagicStick,
  },
  {
    key: 'later',
    title: '稍后配置',
    caption: '进入首页，保留待办提醒，之后再补配置。',
    icon: VideoPause,
  },
]

const activeStep = computed(() => steps[activeIndex.value])
const finishItems = computed(() => {
  const snap = snapshot.value || {}
  const hasLLM = snap.activeLLMProviders?.length > 0
  const tts = snap.activeTTSProviders || []
  const hasEdge = tts.some((item) => item.provider_type === 'edge')
  return [
    { label: 'AI 改编', value: hasLLM ? '已配置' : '未配置', type: hasLLM ? 'ok' : 'warn' },
    { label: '配音生成', value: tts.length ? (hasEdge ? '仅 Edge / 已可用' : '已配置') : '未配置', type: tts.length ? 'ok' : 'warn' },
    { label: '保存路径', value: snap.defaultStoragePath || 'Auralis 默认本地目录', type: 'ok' },
  ]
})

onMounted(refreshSnapshot)

async function refreshSnapshot() {
  snapshot.value = await fetchSetupSnapshot().catch(() => null)
}

function selectMode(mode) {
  selectedMode.value = mode
}

async function confirmMode() {
  if (selectedMode.value === 'later') {
    await skipSetup()
    return
  }
  if (selectedMode.value === 'quick') {
    activeIndex.value = 2
    return
  }
  activeIndex.value = 1
}

function goBack() {
  activeIndex.value = Math.max(0, activeIndex.value - 1)
}

async function goNext() {
  activeIndex.value = Math.min(steps.length - 1, activeIndex.value + 1)
  if (activeStep.value.key === 'finish') await refreshSnapshot()
}

async function handleLLMSaved() {
  await refreshSnapshot()
  activeIndex.value = 2
}

async function handleTTSSaved() {
  await refreshSnapshot()
  activeIndex.value = 3
}

async function handleStorageSaved() {
  await refreshSnapshot()
  activeIndex.value = 4
}

async function skipSetup() {
  markSetupSkipped(true)
  ElMessage.info('已跳过首次配置，首页会继续显示待办提醒')
  router.push('/home')
}

async function openDemo() {
  if (isCreatingDemo.value) return
  isCreatingDemo.value = true
  try {
    const project = await createDemoProject()
    markSetupSkipped(false)
    ElMessage.success('Demo 工程已创建')
    router.push(`/projects/${project.id}/overview`)
  } catch (error) {
    ElMessage.error(error?.message || '创建 Demo 失败')
  } finally {
    isCreatingDemo.value = false
  }
}
</script>

<style scoped>
.setup-page {
  min-height: 100%;
  color: var(--el-text-color-primary);
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.mode-card {
  display: grid;
  gap: 10px;
  min-height: 180px;
  padding: 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.mode-card:hover,
.mode-card:focus-visible,
.mode-card.active {
  border-color: var(--el-color-primary);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--el-color-primary) 9%, transparent), transparent),
    var(--el-bg-color);
  outline: none;
}

.mode-card .el-icon {
  width: 42px;
  height: 42px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-primary) 12%, transparent);
  color: var(--el-color-primary);
  font-size: 20px;
}

.mode-card strong {
  font-size: 18px;
}

.mode-card small {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.finish-panel {
  display: grid;
  gap: 22px;
}

.finish-status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.finish-status-grid article {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 8px 10px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.finish-status-grid small {
  grid-column: 2;
  color: var(--el-text-color-secondary);
}

.dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 999px;
}

.dot-ok {
  background: var(--el-color-success);
}

.dot-warn {
  background: var(--el-color-warning);
}

.finish-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

@media (max-width: 960px) {
  .mode-grid,
  .finish-status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
