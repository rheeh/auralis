<template>
  <div>
    <div class="config-head">
      <div>
        <p class="eyebrow">高级配置</p>
        <h2>配置中心</h2>
      </div>
      <el-button type="primary" @click="router.push('/setup')">从向导配置</el-button>
    </div>

    <el-alert
      v-if="workflowCapability"
      :title="workflowCapability.workflow_enabled ? '数据库工作流与制作助手可用' : '对话式工作流已关闭'"
      :description="`Python ${workflowCapability.python_version} · ${workflowCapability.state_backend} 单一状态源 · 制作助手${workflowCapability.assistant_enabled ? '已启用' : '未启用'}`"
      :type="workflowCapability.workflow_enabled ? 'success' : 'warning'"
      show-icon
      :closable="false"
      class="workflow-capability"
    />

    <el-tabs v-model="activeTab">
      <!-- LLM 管理 -->
      <el-tab-pane label="LLM 管理" name="llm">
        <div class="toolbar">
          <el-button type="primary" @click="openLLMDialog()">新增 LLM 提供商</el-button>
        </div>

        <el-table :data="llmList" stripe border highlight-current-row class="styled-table">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="api_base_url" label="Base URL" min-width="240" />
          <el-table-column prop="model_list" label="模型列表" min-width="240">
            <template #default="{ row }">
              <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 8px;">
                <div style="display: flex; flex-wrap: wrap; gap: 4px; flex: 1;">
                  <el-tooltip
                    v-for="(item, idx) in (row.model_list || '').split(/[,，]/).filter(s => s.trim())"
                    :key="idx"
                    content="点击复制"
                    placement="top"
                    :show-after="500"
                  >
                    <el-tag
                      size="small"
                      effect="plain"
                      style="cursor: pointer;"
                      @click="copyText(item.trim())"
                    >
                      {{ item.trim() }}
                    </el-tag>
                  </el-tooltip>
                </div>
                <el-tooltip content="复制全部模型" placement="top">
                  <el-button
                    type="info"
                    link
                    :icon="CopyDocument"
                    @click="copyText(row.model_list)"
                    style="padding: 0; height: auto;"
                  />
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="API Key" min-width="180">
            <template #default="{ row }">
              <span class="api-key">{{ maskKey(row.api_key) }}</span>
            </template>
          </el-table-column>



          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag effect="light" :type="row.status === 1 ? 'success' : 'info'">
                <span class="status-dot" :class="row.status === 1 ? 'dot-green' : 'dot-gray'"></span>
                {{ row.status === 1 ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>

          <!-- <el-table-column prop="updated_at" label="更新于" min-width="180" /> -->

          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <div class="flex justify-center gap-2">
                <el-button type="primary" size="small" plain @click="openLLMDialog(row)">
                  编辑
                </el-button>

                <el-popconfirm title="确认删除该 LLM 提供商？" confirm-button-text="确定" cancel-button-text="取消"
                  @confirm="removeLLM(row.id)">
                  <template #reference>
                    <el-button type="danger" size="small" plain>
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>

        </el-table>
      </el-tab-pane>

      <!-- TTS 管理 -->
      <el-tab-pane label="TTS 管理" name="tts">
        <div class="toolbar">
          <el-button type="primary" @click="openTTSDialog()">新增 TTS 引擎</el-button>
          <el-button plain @click="openQwenDramaDialog">配置 Qwen 广播剧配音</el-button>
          <el-button text @click="router.push('/voices')">打开音色库</el-button>
        </div>

        <el-table :data="ttsList" stripe border highlight-current-row class="styled-table">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column label="类型" width="130">
            <template #default="{ row }">
              <el-tag effect="plain">{{ providerTypeLabel(row.provider_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="model" label="模型" min-width="160">
            <template #default="{ row }">
              {{ row.model || (row.provider_type === 'edge' ? 'Edge 内置' : '未设置') }}
            </template>
          </el-table-column>
          <el-table-column label="默认音色控制" min-width="150">
            <template #default="{ row }">
              <el-tag :type="ttsCapability(row).type" effect="plain">{{ ttsCapability(row).label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="api_base_url" label="Base URL" min-width="240" />

          <el-table-column label="API Key" min-width="180">
            <template #default="{ row }">
              <span class="api-key">{{ maskKey(row.api_key) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag effect="light" :type="row.status === 1 ? 'success' : 'info'">
                <span class="status-dot" :class="row.status === 1 ? 'dot-green' : 'dot-gray'"></span>
                {{ row.status === 1 ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>

          <!-- <el-table-column prop="updated_at" label="更新于" min-width="180" /> -->

          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <div class="flex justify-center gap-2">
                <el-button type="primary" size="small" plain @click="openTTSDialog(row)">编辑</el-button>
                <el-popconfirm
                  title="确认删除该 TTS 引擎？已选用它的项目需要重新选择。"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="removeTTS(row.id)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" plain>删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- LLM 弹窗 -->
    <el-dialog :title="llmForm.id ? '编辑 LLM 提供商' : '新增 LLM 提供商'" v-model="llmDialogVisible" width="560px">
      <el-form :model="llmForm" :rules="llmRules" ref="llmFormRef" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="llmForm.name" placeholder="如：DeepSeek" />
        </el-form-item>
        <el-form-item label="Base URL" prop="api_base_url">
          <el-input v-model="llmForm.api_base_url" placeholder="https://api.xxx.com" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="llmForm.api_key" placeholder="可留空" show-password />
        </el-form-item>
        <el-form-item label="模型列表">
          <el-select
            v-model="currentModelList"
            multiple
            filterable
            allow-create
            default-first-option
            :reserve-keyword="false"
            placeholder="输入模型后回车"
            style="width: 100%"
          >
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="llmForm.status" :active-value="1" :inactive-value="0" />
        </el-form-item>
        <el-form-item label="自定义参数" prop="custom_params">
          <el-input type="textarea" v-model="llmForm.custom_params" :rows="6" placeholder='请输入 JSON 格式参数' />
        </el-form-item>

      </el-form>

      <template #footer>
        <!-- 新增测试按钮 -->
        <el-button type="warning" @click="testLLM">测试</el-button>
        <el-button @click="llmDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitLLM">确定</el-button>
      </template>
    </el-dialog>

    <!-- TTS 弹窗 -->
    <el-dialog :title="ttsForm.id ? '编辑 TTS 引擎' : '新增 TTS 引擎'" v-model="ttsDialogVisible" width="560px">
      <el-form :model="ttsForm" :rules="ttsRules" ref="ttsFormRef" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="ttsForm.name" placeholder="如：Aliyun CosyVoice" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="ttsForm.provider_type" style="width: 100%">
            <el-option label="云端 TTS（自定义 URL/模型）" value="cloud" />
            <el-option label="Fish/旧版兼容" value="fish" />
            <el-option label="Edge-TTS（免费内置）" value="edge" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" v-if="ttsForm.provider_type !== 'edge'">
          <el-input v-model="ttsForm.api_base_url" placeholder="填完整 TTS 请求地址，例如 https://.../audio/speech" />
        </el-form-item>
        <el-form-item label="模型" v-if="ttsForm.provider_type !== 'edge'">
          <el-input v-model="ttsForm.model" placeholder="如 cosyvoice-v2、qwen3-tts，按你的服务实际填写" />
        </el-form-item>
        <el-form-item label="API Key" v-if="ttsForm.provider_type !== 'edge'">
          <el-input v-model="ttsForm.api_key" placeholder="可留空" show-password />
        </el-form-item>
        <el-form-item label="参数模板" v-if="ttsForm.provider_type !== 'edge'">
          <div class="tts-template-row">
            <el-select v-model="selectedTTSPreset" clearable placeholder="选择后可插入自定义参数模板">
              <el-option
                v-for="preset in TTS_PARAM_PRESETS"
                :key="preset.key"
                :label="preset.label"
                :value="preset.key"
              />
            </el-select>
            <el-button @click="applyTTSPreset" :disabled="!selectedTTSPreset">插入模板</el-button>
          </div>
        </el-form-item>
        <el-form-item label="自定义参数" prop="custom_params" v-if="ttsForm.provider_type !== 'edge'">
          <el-input
            type="textarea"
            v-model="ttsForm.custom_params"
            :rows="8"
            placeholder='可留 {}。推荐显式填写 driver 和指令能力：instruction_mode 可用 native、structured、mapped、none；HTTP 可用 instruction_field 或在 payload 中加入 {{instruction}}。'
          />
        </el-form-item>

        <el-form-item label="状态">
          <el-switch v-model="ttsForm.status" :active-value="1" :inactive-value="0" />
        </el-form-item>

      </el-form>

      <template #footer>
        <!-- 新增测试按钮 -->
        <el-button type="warning" @click="testTTS">测试</el-button>
        <el-button @click="ttsDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTTS">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>



<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import {
  fetchLLMProviders, createLLMProvider, updateLLMProvider, deleteLLMProvider,
  fetchTTSProviders, createTTSProvider, updateTTSProvider, deleteTTSProvider, testLLMProvider, testTTSProvider
} from '../api/provider'
import { fetchWorkflowCapabilities } from '../api/drama'
import { QWEN_DRAMA_MODEL, ttsCapability } from '../utils/ttsCapabilities'

const activeTab = ref('llm')
const router = useRouter()
const route = useRoute()
const workflowCapability = ref(null)

// ---------- LLM ----------
const llmList = ref([])

const loadLLM = async () => { llmList.value = await fetchLLMProviders() }

const llmDialogVisible = ref(false)
const llmFormRef = ref()
const DEFAULT_CUSTOM_PARAMS = JSON.stringify(
  {
    response_format: { type: 'json_object' },
    temperature: 0.7,
    top_p: 0.9
  },
  null,
  2  // 漂亮一点，换行缩进
)

const llmForm = ref({
  id: null,
  name: '',
  api_base_url: '',
  api_key: '',
  model_list: '',
  status: 1,
  custom_params: DEFAULT_CUSTOM_PARAMS
})
const llmRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  api_base_url: [{ required: true, message: '请输入 Base URL', trigger: 'blur' }],
  custom_params: [
    {
      required: true,
      message: '自定义参数不能为空，至少为 {}',
      trigger: 'blur'
    },
    {
      validator: (rule, value, callback) => {
        const v = (value || '').trim()
        if (!v) {
          return callback(new Error('自定义参数不能为空，至少为 {}'))
        }
        try {
          JSON.parse(v)
          callback()
        } catch (e) {
          callback(new Error('自定义参数必须是合法 JSON 格式'))
        }
      },
      trigger: 'blur'
    }
  ]
}

const currentModelList = ref([])

// 监听弹窗打开，初始化 currentModelList
watch(() => llmDialogVisible.value, (val) => {
  if (val) {
    if (llmForm.value.model_list) {
      currentModelList.value = llmForm.value.model_list
        .split(/[,，]/)
        .map(s => s.trim())
        .filter(s => s)
    } else {
      currentModelList.value = []
    }
  } else {
    currentModelList.value = []
  }
})

// 监听 currentModelList 变化，同步回 llmForm.model_list
watch(currentModelList, (val) => {
  // 如果输入包含逗号，自动分割
  let hasSplit = false
  const processedList = []

  for (const item of val) {
    if (item && (item.includes(',') || item.includes('，'))) {
      const parts = item.split(/[,，]/).map(s => s.trim()).filter(s => s)
      processedList.push(...parts)
      hasSplit = true
    } else {
      processedList.push(item)
    }
  }

  if (hasSplit) {
    // 去重并更新 currentModelList
    currentModelList.value = [...new Set(processedList)]
    return
  }

  llmForm.value.model_list = val.join(',')
}, { deep: true })

const copyText = (text) => {
  if (!text) return
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function openLLMDialog(row) {
  if (row) llmForm.value = { ...row }
  else llmForm.value = { id: null, name: '', api_base_url: '', api_key: '', model_list: '', status: 1, custom_params: DEFAULT_CUSTOM_PARAMS }
  llmDialogVisible.value = true
}
function submitLLM() {
  llmFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (llmForm.value.id) {
        await updateLLMProvider(llmForm.value.id, llmForm.value)
        ElMessage.success('已更新')
      } else {
        await createLLMProvider(llmForm.value)
        ElMessage.success('已创建')
      }
      llmDialogVisible.value = false
      await loadLLM()
    } catch {
      ElMessage.error('操作失败')
    }
  })
}
async function removeLLM(id) {
  try {
    await deleteLLMProvider(id)
    ElMessage.success('已删除')
    await loadLLM()
  } catch {
    ElMessage.error('删除失败')
  }
}


import { ElLoading } from 'element-plus'

async function testLLM() {
  // 打开等待框
  const loading = ElLoading.service({
    lock: true,
    text: '正在测试，请稍候...',
    background: 'rgba(0, 0, 0, 0.4)'
  })

  try {
    const res = await testLLMProvider(llmForm.value)
    if (res.code === 200) {
      ElMessage.success(res.message || '测试成功')
    } else {
      ElMessage.error(res.message || '测试失败')
    }
  } catch (e) {
    ElMessage.error('测试异常')
  } finally {
    // 关闭等待框
    loading.close()
  }
}



// ---------- TTS ----------
const ttsList = ref([])
const ttsDialogVisible = ref(false)
const ttsFormRef = ref()
const selectedTTSPreset = ref('')
const ttsForm = ref({
  id: 1,
  name: '',
  api_base_url: '',
  api_key: '',
  provider_type: 'cloud',
  model: '',
  custom_params: '{}',
  status: 1,
})
const ttsRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  custom_params: [
    {
      validator: (rule, value, callback) => {
        const v = (value || '{}').trim()
        try {
          JSON.parse(v)
          callback()
        } catch (e) {
          callback(new Error('自定义参数必须是合法 JSON 格式'))
        }
      },
      trigger: 'blur'
    }
  ]
}

const loadTTS = async () => {
  const list = await fetchTTSProviders()
  ttsList.value = Array.isArray(list) ? list : []
}

const TTS_PARAM_PRESETS = [
  {
    key: 'qwen_drama',
    label: '阿里云 Qwen-Audio 3.0 Plus（原生表演指令）',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: QWEN_DRAMA_MODEL,
    params: { driver: 'http', voice: 'longanlingxin', language_hints: ['zh'], format: 'mp3', sample_rate: 24000 }
  },
  {
    key: 'qwen_audio_flash',
    label: '阿里云 Qwen-Audio 3.0 Flash（原生表演指令）',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-audio-3.0-tts-flash',
    params: { driver: 'http', voice: 'longanfengyue', language_hints: ['zh'], format: 'mp3', sample_rate: 24000 }
  },
  {
    key: 'dashscope_cosyvoice',
    label: '阿里云 CosyVoice v3 Flash（固定情感）',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'cosyvoice-v3-flash',
    params: {
      driver: 'dashscope_cosyvoice',
      voice: 'longanhuan',
      format: 'mp3',
      instruction_mode: 'structured',
      supports_instruction: true
    }
  },
  {
    key: 'dashscope_cosyvoice_base',
    label: '阿里云 CosyVoice v1（基础模式）',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'cosyvoice-v1',
    params: {
      driver: 'dashscope_cosyvoice',
      format: 'mp3',
      instruction_mode: 'mapped',
      supports_instruction: false
    }
  },
  {
    key: 'dashscope_sambert',
    label: '阿里云 Sambert',
    api_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'sambert-zhifei-v1',
    params: {
      driver: 'dashscope_sambert',
      format: 'wav'
    }
  },
  {
    key: 'openai_speech',
    label: 'OpenAI-compatible Speech',
    params: {
      driver: 'http',
      endpoint: 'https://example.com/v1/audio/speech',
      auth_header: 'Authorization',
      auth_prefix: 'Bearer ',
      payload: {
        model: '{{model}}',
        input: '{{text}}',
        voice: '{{voice}}',
        instructions: '{{instruction}}'
      }
    }
  },
  {
    key: 'http_audio_url',
    label: 'HTTP JSON 返回音频 URL',
    params: {
      driver: 'http',
      endpoint: 'https://example.com/tts',
      auth_header: 'Authorization',
      auth_prefix: 'Bearer ',
      payload: {
        model: '{{model}}',
        text: '{{text}}',
        voice: '{{voice}}'
      },
      audio_url_path: 'data.audio_url',
      code_path: 'code',
      success_codes: [0, 200, '0', '200']
    }
  },
  {
    key: 'http_audio_base64',
    label: 'HTTP JSON 返回 Base64',
    params: {
      driver: 'http',
      endpoint: 'https://example.com/tts',
      auth_header: 'Authorization',
      auth_prefix: 'Bearer ',
      payload: {
        model: '{{model}}',
        text: '{{text}}',
        voice: '{{voice}}'
      },
      audio_base64_path: 'data.audio_base64',
      code_path: 'code',
      success_codes: [0, 200, '0', '200']
    }
  }
]

function applyTTSPreset() {
  const preset = TTS_PARAM_PRESETS.find((item) => item.key === selectedTTSPreset.value)
  if (!preset) return
  ttsForm.value.custom_params = JSON.stringify(preset.params, null, 2)
  if (!ttsForm.value.api_base_url && preset.api_base_url) {
    ttsForm.value.api_base_url = preset.api_base_url
  }
  if (preset.model) {
    ttsForm.value.model = preset.model
  }
  ElMessage.success('已插入参数模板')
}

function openQwenDramaDialog() {
  openTTSDialog()
  ttsForm.value.name = '阿里云 Qwen-Audio 3.0 广播剧'
  selectedTTSPreset.value = 'qwen_drama'
  applyTTSPreset()
  // Reuse the configured credential only in this unsaved form, for the same host.
  const existing = ttsList.value.find(provider => provider.api_key && provider.api_base_url === ttsForm.value.api_base_url)
  if (existing) ttsForm.value.api_key = existing.api_key
  activeTab.value = 'tts'
}

function openTTSDialog(row) {
  selectedTTSPreset.value = ''
  ttsForm.value = {
    id: null,
    name: '',
    api_base_url: '',
    api_key: '',
    provider_type: 'cloud',
    model: '',
    custom_params: '{}',
    status: 1,
    ...row,
    custom_params: row?.custom_params || '{}'
  }
  ttsDialogVisible.value = true
}

function submitTTS() {
  ttsFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (ttsForm.value.id) {
        await updateTTSProvider(ttsForm.value.id, ttsForm.value)
        ElMessage.success('已更新')
      } else {
        await createTTSProvider(ttsForm.value)
        ElMessage.success('已创建')
      }
      ttsDialogVisible.value = false
      await loadTTS()
    } catch (e) {
      ElMessage.error(e?.response?.data?.message || '操作失败')
    }
  })
}

async function removeTTS(id) {
  try {
    await deleteTTSProvider(id)
    ElMessage.success('已删除')
    await loadTTS()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '删除失败')
  }
}



async function testTTS() {
  const loading = ElLoading.service({
    lock: true,
    text: '正在测试 TTS，请稍候...',
    background: 'rgba(0, 0, 0, 0.4)'
  })

  try {
    const res = await testTTSProvider(ttsForm.value)
    if (res.code === 200) {
      ElMessage.success(res.message || 'TTS 测试成功')
    } else {
      ElMessage.error(res.message || 'TTS 测试失败')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || 'TTS 测试异常')
  } finally {
    loading.close()
  }
}



// ---------- 工具 ----------
const maskKey = (val) => (val ? '•'.repeat(Math.min(val.length, 8)) : '（未设置）')
const providerTypeLabel = (value) => {
  const map = {
    edge: 'Edge-TTS',
    cloud: '云端 TTS',
    fish: 'Fish 兼容',
    legacy: '旧版兼容'
  }
  return map[value] || value || '云端 TTS'
}

onMounted(async () => {
  const [, , capabilityResponse] = await Promise.all([
    loadLLM(),
    loadTTS(),
    fetchWorkflowCapabilities().catch(() => null),
  ])
  workflowCapability.value = capabilityResponse?.code === 200 ? capabilityResponse.data : null
  if (route.query.ttsPreset === 'qwen-drama') openQwenDramaDialog()
})
</script>

<style scoped>
.config-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.config-head h2 {
  margin: 0;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.toolbar {
  margin-bottom: 12px;
}

.workflow-capability {
  margin-bottom: 16px;
}

.masked {
  margin-right: 8px;
}

.styled-table {
  border-radius: 10px;
  overflow: hidden;
  font-size: 14px;
}

.styled-table ::v-deep(.el-table__header th) {
  background-color: var(--el-fill-color-light);
  font-weight: 600;
  text-align: center;
}

.styled-table ::v-deep(.el-table__body td) {
  text-align: center;
}

.api-key {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.tts-template-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  width: 100%;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.dot-green {
  background: #67c23a;
}

.dot-gray {
  background: #909399;
}
</style>
