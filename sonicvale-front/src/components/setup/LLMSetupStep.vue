<template>
  <div class="setup-step">
    <section class="preset-grid" aria-label="AI 改编模型预设">
      <button
        v-for="preset in presets"
        :key="preset.key"
        type="button"
        class="preset-card"
        :class="{ active: selectedPreset === preset.key }"
        @click="applyPreset(preset)"
      >
        <strong>{{ preset.name }}</strong>
        <small>{{ preset.caption }}</small>
      </button>
    </section>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="setup-form">
      <div class="form-grid">
        <el-form-item label="服务名称" prop="name">
          <el-input v-model="form.name" placeholder="例如 DeepSeek 改编模型" />
        </el-form-item>
        <el-form-item label="模型名" prop="model_list">
          <el-input v-model="form.model_list" placeholder="例如 deepseek-chat" />
        </el-form-item>
      </div>

      <el-form-item label="Base URL" prop="api_base_url">
        <el-input v-model="form.api_base_url" placeholder="https://api.example.com/v1" />
      </el-form-item>

      <el-form-item label="API Key">
        <el-input v-model="form.api_key" show-password placeholder="填入服务商 API Key" />
      </el-form-item>

      <el-collapse v-model="advancedOpen">
        <el-collapse-item title="高级设置：请求参数 JSON" name="advanced">
          <el-form-item prop="custom_params">
            <el-input v-model="form.custom_params" type="textarea" :rows="6" resize="none" />
          </el-form-item>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <SetupTestResult :result="testResult" />

    <div class="step-actions">
      <el-button :loading="isTesting" :icon="Connection" @click="testProvider">测试改编能力</el-button>
      <el-button type="primary" :loading="isSaving" :disabled="testResult?.status !== 'success'" @click="saveProvider">
        保存为可用模型
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection } from '@element-plus/icons-vue'
import { createLLMProvider, testLLMProvider } from '../../api/provider'
import SetupTestResult from './SetupTestResult.vue'

const emit = defineEmits(['saved'])

const DEFAULT_PARAMS = JSON.stringify({
  response_format: { type: 'json_object' },
  temperature: 0.7,
  top_p: 0.9,
}, null, 2)

const presets = [
  {
    key: 'openai',
    name: 'OpenAI-compatible',
    caption: '适合 OpenAI 兼容网关、自建代理和多数兼容接口。',
    api_base_url: 'https://api.openai.com/v1',
    model_list: 'gpt-4.1-mini',
  },
  {
    key: 'dashscope',
    name: 'DashScope',
    caption: '适合阿里云百炼兼容模式。',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model_list: 'qwen-plus',
  },
  {
    key: 'deepseek',
    name: 'DeepSeek',
    caption: '适合 DeepSeek 官方 OpenAI 兼容接口。',
    api_base_url: 'https://api.deepseek.com',
    model_list: 'deepseek-chat',
  },
  {
    key: 'custom',
    name: '自定义',
    caption: '填写自己的 Base URL、模型名和请求参数。',
    api_base_url: '',
    model_list: '',
  },
]

const selectedPreset = ref('openai')
const advancedOpen = ref([])
const formRef = ref(null)
const isTesting = ref(false)
const isSaving = ref(false)
const testResult = ref(null)
const form = reactive({
  name: 'OpenAI-compatible 改编模型',
  api_base_url: 'https://api.openai.com/v1',
  api_key: '',
  model_list: 'gpt-4.1-mini',
  status: 1,
  custom_params: DEFAULT_PARAMS,
})

const rules = {
  name: [{ required: true, message: '请输入服务名称', trigger: 'blur' }],
  api_base_url: [{ required: true, message: '请输入 Base URL', trigger: 'blur' }],
  model_list: [{ required: true, message: '请输入模型名', trigger: 'blur' }],
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

function applyPreset(preset) {
  selectedPreset.value = preset.key
  form.name = `${preset.name} 改编模型`
  form.api_base_url = preset.api_base_url
  form.model_list = preset.model_list
  testResult.value = null
}

async function validateForm() {
  if (!formRef.value) return false
  return await formRef.value.validate().catch(() => false)
}

function normalizeError(message) {
  if (!message) return '测试失败'
  if (/api key|unauthorized|401|鉴权|认证/i.test(message)) return 'API Key 无效或权限不足'
  if (/model|模型/i.test(message)) return '模型名可能不可用'
  if (/json/i.test(message)) return '模型没有按 JSON 格式返回'
  if (/timeout|超时/i.test(message)) return '接口响应超时'
  return message
}

async function testProvider() {
  if (!(await validateForm())) return
  isTesting.value = true
  testResult.value = null
  try {
    const res = await testLLMProvider({ ...form })
    if (res?.code === 200) {
      testResult.value = {
        status: 'success',
        title: '改编能力测试成功',
        message: res.message || '模型可以完成短文本 JSON 输出。',
        sample: res.data?.sample_output ? JSON.stringify(res.data.sample_output, null, 2) : '',
      }
      return
    }
    throw new Error(res?.message || '测试失败')
  } catch (error) {
    const reason = normalizeError(error?.response?.data?.message || error?.message)
    testResult.value = {
      status: 'error',
      title: '改编能力测试失败',
      message: reason,
      suggestion: '请检查 Base URL、API Key、模型名，确认该模型支持普通 chat completion 和 JSON 输出。',
    }
  } finally {
    isTesting.value = false
  }
}

async function saveProvider() {
  if (!(await validateForm())) return
  isSaving.value = true
  try {
    const res = await createLLMProvider({ ...form })
    if (res?.code !== 200) throw new Error(res?.message || '保存失败')
    ElMessage.success('AI 改编模型已保存')
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

.preset-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.preset-card {
  min-height: 112px;
  padding: 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.preset-card:hover,
.preset-card:focus-visible,
.preset-card.active {
  border-color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 8%, var(--el-bg-color));
  outline: none;
}

.preset-card strong,
.preset-card small {
  display: block;
}

.preset-card small {
  margin-top: 8px;
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

.step-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

@media (max-width: 960px) {
  .preset-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
