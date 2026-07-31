<template>
  <section class="library-panel">
    <div class="library-toolbar">
      <el-segmented v-model="sourceFilter" :options="sourceOptions" />
      <el-select v-model="categoryFilter" class="category-filter" aria-label="素材分类">
        <el-option label="全部分类" value="all" />
        <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-input v-model="keyword" clearable placeholder="搜索名称或标签" class="library-search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <span class="asset-count">{{ filteredAssets.length }} 个素材</span>
      <el-tooltip content="刷新素材库">
        <el-button :icon="Refresh" circle :loading="loading" aria-label="刷新素材库" @click="loadAssets" />
      </el-tooltip>
      <el-button type="primary" :icon="Upload" @click="chooseUpload">导入音频</el-button>
    </div>

    <div v-if="materialLines.length" class="bind-target">
      <span>绑定目标</span>
      <el-select v-model="selectedLineId" filterable placeholder="选择当前章节的音效或 BGM 台词">
        <el-option
          v-for="line in materialLines"
          :key="line.id"
          :label="`${trackLabel(line.track)} · ${line.text_content || `台词 #${line.id}`}`"
          :value="line.id"
        />
      </el-select>
      <small>素材会复制进项目，素材库原件不会被修改。</small>
    </div>
    <el-alert v-else type="info" :closable="false" show-icon title="当前章节没有音效或 BGM 台词，可先浏览和导入素材。" />

    <div v-loading="loading" class="asset-table-wrap">
      <div v-if="filteredAssets.length" class="asset-list">
        <article v-for="asset in filteredAssets" :key="asset.id" class="asset-row">
          <div class="asset-main">
            <div class="asset-title">
              <strong>{{ asset.name }}</strong>
              <el-tag size="small" effect="plain">{{ categoryLabel(asset.category) }}</el-tag>
              <el-tag size="small" :type="asset.source_type === 'builtin' ? 'success' : 'info'" effect="plain">
                {{ asset.source_type === 'builtin' ? '内置 CC0' : '我的素材' }}
              </el-tag>
            </div>
            <div class="asset-meta">
              <span>{{ formatDuration(asset.duration_ms) }}</span>
              <span v-if="asset.sample_rate">{{ formatSampleRate(asset.sample_rate) }}</span>
              <span v-if="asset.channels">{{ asset.channels }} 声道</span>
              <a v-if="asset.source_url" :href="asset.source_url" target="_blank" rel="noreferrer">来源</a>
            </div>
            <div v-if="asset.tags?.length" class="asset-tags">
              <el-tag v-for="tag in asset.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
            </div>
          </div>
          <audio controls preload="metadata" :src="audioUrl(asset)" />
          <div class="asset-actions">
            <el-button
              type="primary"
              :icon="Link"
              :disabled="!selectedLineId"
              :loading="bindingId === asset.id"
              @click="bindAsset(asset)"
            >绑定</el-button>
            <el-tooltip v-if="asset.source_type === 'user'" content="删除我的素材">
              <el-button
                type="danger"
                plain
                :icon="Delete"
                circle
                aria-label="删除我的素材"
                @click="removeAsset(asset)"
              />
            </el-tooltip>
          </div>
        </article>
      </div>
      <el-empty v-else description="没有符合条件的素材" />
    </div>

    <input ref="fileInput" class="hidden-input" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac" @change="onBrowserFile" />

    <el-dialog v-model="uploadVisible" title="导入到我的素材" width="min(480px, 92vw)" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="音频文件">
          <el-input :model-value="pendingFileName" disabled />
        </el-form-item>
        <el-form-item label="素材名称">
          <el-input v-model="uploadForm.name" maxlength="255" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="uploadForm.category">
            <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="uploadForm.tags" placeholder="用逗号分隔，例如：室内, 门铃, 短音" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">导入</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Delete, Link, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bindSoundLibraryAsset,
  deleteSoundLibraryAsset,
  getSoundLibraryAssets,
  getSoundLibraryAudioUrl,
  importSoundLibraryPath,
  uploadSoundLibraryFile,
} from '../api/soundLibrary'

const props = defineProps({
  materialLines: { type: Array, default: () => [] },
  targetLineId: { type: Number, default: null },
})
const emit = defineEmits(['bound'])

const assets = ref([])
const loading = ref(false)
const bindingId = ref('')
const sourceFilter = ref('all')
const categoryFilter = ref('all')
const keyword = ref('')
const selectedLineId = ref(null)
const fileInput = ref(null)
const pendingPath = ref('')
const pendingFile = ref(null)
const pendingFileName = ref('')
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadForm = ref({ name: '', category: 'foley', tags: '' })

const sourceOptions = [
  { label: '全部', value: 'all' },
  { label: '内置素材', value: 'builtin' },
  { label: '我的素材', value: 'user' },
]
const categoryOptions = [
  { label: '环境氛围', value: 'ambience' },
  { label: '天气', value: 'weather' },
  { label: '门与机关', value: 'doors' },
  { label: '脚步', value: 'footsteps' },
  { label: '撞击', value: 'impacts' },
  { label: '拟音', value: 'foley' },
  { label: '背景音乐', value: 'bgm' },
]

const filteredAssets = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return assets.value.filter((asset) => {
    if (sourceFilter.value !== 'all' && asset.source_type !== sourceFilter.value) return false
    if (categoryFilter.value !== 'all' && asset.category !== categoryFilter.value) return false
    if (!query) return true
    return [asset.name, asset.category, ...(asset.tags || [])]
      .some((value) => String(value || '').toLowerCase().includes(query))
  })
})

watch(() => props.targetLineId, (value) => {
  if (value && props.materialLines.some((line) => line.id === value)) selectedLineId.value = value
}, { immediate: true })

watch(() => props.materialLines, (value) => {
  if (selectedLineId.value && !value.some((line) => line.id === selectedLineId.value)) selectedLineId.value = null
}, { deep: true })

onMounted(loadAssets)

async function loadAssets() {
  loading.value = true
  try {
    const response = await getSoundLibraryAssets()
    assets.value = response?.code === 200 ? response.data : []
  } catch (error) {
    ElMessage.error(apiError(error, '素材库加载失败'))
  } finally {
    loading.value = false
  }
}

async function chooseUpload() {
  if (window.native?.pickAudio) {
    const path = await window.native.pickAudio()
    if (!path) return
    prepareUpload({ path, name: basename(path) })
    return
  }
  fileInput.value?.click()
}

function onBrowserFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  prepareUpload({ file, name: file.name })
}

function prepareUpload({ path = '', file = null, name }) {
  pendingPath.value = path
  pendingFile.value = file
  pendingFileName.value = name
  uploadForm.value = {
    name: String(name || '').replace(/\.[^.]+$/, ''),
    category: 'foley',
    tags: '',
  }
  uploadVisible.value = true
}

async function submitUpload() {
  if (!uploadForm.value.name.trim()) {
    ElMessage.warning('请输入素材名称')
    return
  }
  uploading.value = true
  try {
    const metadata = { ...uploadForm.value }
    const response = pendingPath.value
      ? await importSoundLibraryPath({
          source_path: pendingPath.value,
          name: metadata.name,
          category: metadata.category,
          tags: splitTags(metadata.tags),
        })
      : await uploadSoundLibraryFile(pendingFile.value, metadata)
    if (response?.code !== 200) throw new Error(response?.message || '导入失败')
    uploadVisible.value = false
    sourceFilter.value = 'user'
    await loadAssets()
    ElMessage.success('素材已导入')
  } catch (error) {
    ElMessage.error(apiError(error, '导入失败'))
  } finally {
    uploading.value = false
  }
}

async function bindAsset(asset) {
  if (!selectedLineId.value) {
    ElMessage.warning('请先选择绑定目标')
    return
  }
  bindingId.value = asset.id
  try {
    const response = await bindSoundLibraryAsset(asset.id, selectedLineId.value)
    if (response?.code !== 200) throw new Error(response?.message || '绑定失败')
    ElMessage.success('素材已绑定到当前章节')
    emit('bound', { lineId: selectedLineId.value, asset })
  } catch (error) {
    ElMessage.error(apiError(error, '绑定失败'))
  } finally {
    bindingId.value = ''
  }
}

async function removeAsset(asset) {
  try {
    await ElMessageBox.confirm(`删除“${asset.name}”？已复制到项目的音频不会受影响。`, '删除素材', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteSoundLibraryAsset(asset.id)
    await loadAssets()
    ElMessage.success('素材已删除')
  } catch (error) {
    ElMessage.error(apiError(error, '删除失败'))
  }
}

function audioUrl(asset) {
  return getSoundLibraryAudioUrl(asset.id, asset.created_at ? Date.parse(asset.created_at) : 1)
}

function categoryLabel(category) {
  return categoryOptions.find((item) => item.value === category)?.label || category
}

function trackLabel(track) {
  return track === 'bgm' ? 'BGM' : '音效'
}

function formatDuration(value) {
  const milliseconds = Math.max(0, Number(value || 0))
  const seconds = milliseconds > 0 ? Math.max(1, Math.round(milliseconds / 1000)) : 0
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function formatSampleRate(value) {
  return `${(Number(value) / 1000).toFixed(Number(value) % 1000 ? 1 : 0)} kHz`
}

function basename(path) {
  return String(path || '').split(/[\\/]/).pop() || ''
}

function splitTags(value) {
  return String(value || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean)
}

function apiError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}
</script>

<style scoped>
.library-panel { display: grid; gap: 12px; }
.library-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 12px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.category-filter { width: 140px; }
.library-search { width: min(320px, 100%); }
.asset-count { margin-left: auto; color: var(--el-text-color-secondary); font-size: 12px; }
.bind-target { display: grid; grid-template-columns: auto minmax(240px, 560px) minmax(180px, 1fr); gap: 10px; align-items: center; padding: 10px 12px; border-left: 3px solid var(--el-color-primary); background: var(--el-fill-color-extra-light); }
.bind-target > span { font-size: 12px; font-weight: 600; }
.bind-target small { color: var(--el-text-color-secondary); }
.asset-table-wrap { min-height: 240px; }
.asset-list { border-top: 1px solid var(--el-border-color-lighter); }
.asset-row { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(260px, 380px) auto; gap: 16px; align-items: center; min-height: 104px; padding: 12px 4px; border-bottom: 1px solid var(--el-border-color-lighter); }
.asset-main { min-width: 0; }
.asset-title, .asset-meta, .asset-tags, .asset-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.asset-title strong { min-width: 0; overflow-wrap: anywhere; }
.asset-meta { margin-top: 7px; color: var(--el-text-color-secondary); font-size: 11px; }
.asset-meta a { color: var(--el-color-primary); text-decoration: none; }
.asset-tags { margin-top: 7px; }
.asset-row audio { width: 100%; height: 36px; }
.hidden-input { display: none; }
.el-form .el-select { width: 100%; }
@media (max-width: 900px) {
  .asset-count { margin-left: 0; }
  .asset-row { grid-template-columns: minmax(0, 1fr) auto; }
  .asset-row audio { grid-column: 1 / -1; grid-row: 2; }
  .bind-target { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .category-filter, .library-search { width: 100%; }
  .asset-row { grid-template-columns: 1fr; }
  .asset-actions, .asset-row audio { grid-column: 1; }
}
</style>
