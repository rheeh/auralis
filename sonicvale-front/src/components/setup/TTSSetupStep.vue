<template>
  <div class="setup-step">
    <section class="choice-grid" aria-label="配音方式">
      <button
        v-for="choice in choices"
        :key="choice.key"
        type="button"
        class="choice-card"
        :class="{ active: form.provider_type === choice.type && selectedChoice === choice.key }"
        @click="applyChoice(choice)"
      >
        <el-icon><component :is="choice.icon" /></el-icon>
        <strong>{{ choice.title }}</strong>
        <small>{{ choice.caption }}</small>
      </button>
    </section>

    <el-form v-if="form.provider_type !== 'none'" ref="formRef" :model="form" :rules="rules" label-position="top" class="setup-form">
      <div class="form-grid">
        <el-form-item label="配音方式名称" prop="name">
          <el-input v-model="form.name" placeholder="例如 Edge-TTS 免费配音" />
        </el-form-item>
        <el-form-item v-if="form.provider_type !== 'edge'" label="模型" prop="model">
          <el-input v-model="form.model" placeholder="例如 cosyvoice-v1" />
        </el-form-item>
      </div>

      <template v-if="form.provider_type !== 'edge'">
        <el-form-item label="Base URL" prop="api_base_url">
          <el-input v-model="form.api_base_url" placeholder="https://example.com/v1/audio/speech" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" show-password placeholder="填入服务商 API Key" />
        </el-form-item>
        <el-form-item label="服务商模板">
          <div class="template-row">
            <el-select v-model="selectedTemplate" placeholder="选择模板" clearable>
              <el-option v-for="item in templates" :key="item.key" :label="item.label" :value="item.key" />
            </el-select>
            <el-button :disabled="!selectedTemplate" @click="applyTemplate">插入模板</el-button>
          </div>
        </el-form-item>
      </template>

      <el-collapse v-if="form.provider_type !== 'edge'" v-model="advancedOpen">
        <el-collapse-item title="高级设置：请求参数 JSON" name="advanced">
          <el-form-item prop="custom_params">
            <el-input v-model="form.custom_params" type="textarea" :rows="7" resize="none" />
          </el-form-item>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <el-alert
      v-else
      title="你可以先跳过配音配置。之后仍然可以生成台本，再从配置向导或配置中心补配音方式。"
      type="info"
      show-icon
      :closable="false"
    />

    <SetupTestResult :result="testResult" />

    <div class="step-actions">
      <el-button v-if="form.provider_type !== 'none'" :loading="isTesting" :icon="Headset" @click="testProvider">测试并试听</el-button>
      <el-button v-if="form.provider_type !== 'none'" type="primary" :loading="isSaving" :disabled="testResult?.status !== 'success'" @click="saveProvider">
        保存配音方式
      </el-button>
      <el-button v-else type="primary" @click="$emit('skipped')">暂不配置，继续</el-button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Cloudy, Headset, VideoPause } from '@element-plus/icons-vue'
import { createTTSProvider, testTTSProvider } from '../../api/provider'
import SetupTestResult from './SetupTestResult.vue'

const emit = defineEmits(['saved', 'skipped'])

const choices = [
  {
    key: 'edge',
    type: 'edge',
    title: '免费快速：Edge-TTS',
    caption: '适合旁白和普通角色，能先跑通制作链路。',
    icon: Headset,
  },
  {
    key: 'cloud',
    type: 'cloud',
    title: '云端高质量',
    caption: '适合主角、关键对白和更稳定的商业配音服务。',
    icon: Cloudy,
  },
  {
    key: 'none',
    type: 'none',
    title: '暂不配置',
    caption: '先生成台本，之后再补配音。',
    icon: VideoPause,
  },
]

const templates = [
  {
    key: 'dashscope_cosyvoice',
    label: '阿里云 CosyVoice v3 Flash（指令控制）',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'cosyvoice-v3-flash',
    params: {
      driver: 'dashscope_cosyvoice',
      voice: 'longanhuan',
      format: 'mp3',
      instruction_mode: 'structured',
      supports_instruction: true,
    },
  },
  {
    key: 'openai_speech',
    label: 'OpenAI-compatible Speech',
    api_base_url: '',
    model: 'tts-1',
    params: {
      driver: 'http',
      endpoint: 'https://example.com/v1/audio/speech',
      auth_header: 'Authorization',
      auth_prefix: 'Bearer ',
      payload: { model: '{{model}}', input: '{{text}}', voice: '{{voice}}', instructions: '{{instruction}}' },
    },
  },
]

const selectedChoice = ref('edge')
const selectedTemplate = ref('')
const advancedOpen = ref([])
const formRef = ref(null)
const isTesting = ref(false)
const isSaving = ref(false)
const testResult = ref(null)
const form = reactive({
  name: 'Edge-TTS 免费配音',
  provider_type: 'edge',
  api_base_url: '',
  api_key: '',
  model: '',
  custom_params: '{}',
  status: 1,
})

const rules = {
  name: [{ required: true, message: '请输入配音方式名称', trigger: 'blur' }],
  api_base_url: [{
    validator: (rule, value, callback) => {
      if (form.provider_type === 'edge' || value) callback()
      else callback(new Error('请输入 Base URL'))
    },
    trigger: 'blur',
  }],
  model: [{
    validator: (rule, value, callback) => {
      if (form.provider_type === 'edge' || value) callback()
      else callback(new Error('请输入模型名'))
    },
    trigger: 'blur',
  }],
  custom_params: [{
    validator: (rule, value, callback) => {
      try {
        JSON.parse(value || '{}')
        callback()
      } catch {
        callback(new Error('高级参数必须是合法 JSON'))
      }
    },
    trigger: 'blur',
  }],
}

function applyChoice(choice) {
  selectedChoice.value = choice.key
  form.provider_type = choice.type
  testResult.value = null
  if (choice.type === 'edge') {
    form.name = 'Edge-TTS 免费配音'
    form.api_base_url = ''
    form.api_key = ''
    form.model = ''
    form.custom_params = '{}'
  } else if (choice.type === 'cloud') {
    form.name = '云端高质量配音'
    form.api_base_url = ''
    form.model = ''
    form.custom_params = '{}'
  }
}

function applyTemplate() {
  const template = templates.find((item) => item.key === selectedTemplate.value)
  if (!template) return
  if (template.api_base_url) form.api_base_url = template.api_base_url
  if (template.model) form.model = template.model
  form.custom_params = JSON.stringify(template.params, null, 2)
  ElMessage.success('已插入云端 TTS 模板')
}

async function validateForm() {
  if (!formRef.value) return false
  return await formRef.value.validate().catch(() => false)
}

function normalizeError(message) {
  if (!message) return '测试失败'
  if (/edge-tts|依赖/i.test(message)) return 'Edge-TTS 运行依赖不可用'
  if (/base url|地址/i.test(message)) return 'TTS 服务地址缺失或不可访问'
  if (/model|模型/i.test(message)) return 'TTS 模型名缺失或不可用'
  if (/timeout|超时/i.test(message)) return 'TTS 服务响应超时'
  return message
}

async function testProvider() {
  if (!(await validateForm())) return
  isTesting.value = true
  testResult.value = null
  try {
    const res = await testTTSProvider({ ...form })
    if (res?.code === 200) {
      testResult.value = {
        status: 'success',
        title: '配音测试成功',
        message: res.message || '已生成示例音频。',
        audioUrl: res.data?.audio_data_url || '',
      }
      return
    }
    throw new Error(res?.message || '测试失败')
  } catch (error) {
    const reason = normalizeError(error?.response?.data?.message || error?.message)
    testResult.value = {
      status: 'error',
      title: '配音测试失败',
      message: reason,
      suggestion: form.provider_type === 'edge'
        ? '请确认后端环境已安装 edge-tts，或先选择“暂不配置”。'
        : '请检查 Base URL、API Key、模型名和高级参数模板。',
    }
  } finally {
    isTesting.value = false
  }
}

async function saveProvider() {
  if (!(await validateForm())) return
  isSaving.value = true
  try {
    const res = await createTTSProvider({ ...form })
    if (res?.code !== 200) throw new Error(res?.message || '保存失败')
    ElMessage.success('配音方式已保存')
    emit('saved', res.data)
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    isSaving.value = false
  }
}
</script>

<style scoped>
.setup-step {
  display: grid;
  gap: 18px;
}

.choice-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.choice-card {
  display: grid;
  gap: 8px;
  min-height: 136px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.choice-card:hover,
.choice-card:focus-visible,
.choice-card.active {
  border-color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 8%, var(--el-bg-color));
  outline: none;
}

.choice-card .el-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-primary) 12%, transparent);
  color: var(--el-color-primary);
}

.choice-card strong,
.choice-card small {
  display: block;
}

.choice-card small {
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

.setup-form {
  max-width: 820px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.template-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  width: 100%;
}

.step-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

@media (max-width: 960px) {
  .choice-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
