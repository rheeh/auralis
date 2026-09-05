<template>
  <section ref="panelRoot" class="library-panel">
    <div class="quick-scenes">
      <div><strong>给这一幕加点声音</strong><span>悬疑 / 都市常用素材 · 先试听，再加入</span></div>
      <div class="scene-shortcuts">
        <el-button v-for="scene in scenePresets" :key="scene.label" size="small" :type="keyword === scene.keyword ? 'primary' : 'default'" plain @click="applyScenePreset(scene)">{{ scene.label }}</el-button>
        <el-button size="small" text @click="resetFilters">全部素材</el-button>
      </div>
    </div>
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

    <div v-if="chapterId" class="quick-insert-target">
      <div class="target-heading">
        <strong>加入位置</strong>
        <el-radio-group v-if="materialLines.length" v-model="actionMode" size="small">
          <el-radio-button value="insert">新加一条音效</el-radio-button>
          <el-radio-button value="bind">替换已有音效</el-radio-button>
        </el-radio-group>
      </div>
      <template v-if="actionMode === 'insert'">
        <div class="insert-position">
          <el-select v-model="anchorLineId" filterable :placeholder="anchorLines.length ? '选择定位台词' : '空章节：从场景开头加入'" :disabled="!anchorLines.length" aria-label="定位台词">
            <el-option v-for="line in anchorLines" :key="line.id" :label="`${line.scene_title ? `${line.scene_title} · ` : ''}${line.line_order || ''} ${line.text_content || `台词 #${line.id}`}`" :value="line.id" />
          </el-select>
          <CuePlacementSelect v-model="insertForm.placement" allow-scene-start />
          <el-select v-model="mixPreset" aria-label="音效混音方式" @change="applyMixPreset">
            <el-option label="环境铺底 · 轻" value="ambience" />
            <el-option label="动作拟音 · 中" value="foley" />
            <el-option label="悬念强调 · 强" value="accent" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </div>
        <small class="insert-note">自动新建音效行并复制素材；与对白叠加。对白尚未生成时，保留加入位置，生成后按真实时长落位。</small>
        <el-collapse class="mix-settings">
          <el-collapse-item :title="`混音参数 · ${insertForm.volume_db} dB · 可调时长、偏移与淡入淡出`" name="mix">
            <div class="mix-grid">
              <label>音量（dB）<el-input-number v-model="insertForm.volume_db" :min="-60" :max="12" :step="1" controls-position="right" @change="mixPreset = 'custom'" /></label>
              <label>截取上限（秒，0 为完整）<el-input-number v-model="insertForm.duration" :min="0" :max="600" :step="1" controls-position="right" /></label>
              <label>时间偏移（秒）<el-input-number v-model="insertForm.offset" :min="-60" :max="60" :step="0.1" :precision="1" controls-position="right" /></label>
              <label>淡入（秒）<el-input-number v-model="insertForm.fadeIn" :min="0" :max="30" :step="0.1" :precision="1" controls-position="right" /></label>
              <label>淡出（秒）<el-input-number v-model="insertForm.fadeOut" :min="0" :max="30" :step="0.1" :precision="1" controls-position="right" /></label>
            </div>
            <small class="insert-note">短素材会按长度缩短淡入淡出；“句前”和负偏移最早落在 0 秒。加入后可在时间线继续调整。</small>
          </el-collapse-item>
        </el-collapse>
      </template>
    </div>

    <div v-if="materialLines.length && (!chapterId || actionMode === 'bind')" class="bind-target">
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
    <el-alert v-else-if="!chapterId" type="info" :closable="false" show-icon title="选择章节后，即可把素材快捷加入台本。" />
    <el-alert v-if="lastInsertion" type="success" show-icon :title="lastInsertion" @close="lastInsertion = ''" />

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
          <audio controls preload="none" :src="audioUrl(asset)" :aria-label="`试听${asset.name}`" @play="pauseOtherPreviews" />
          <div class="asset-actions">
            <el-button
              type="primary"
              :icon="Link"
              :disabled="Boolean(bindingId) || (chapterId && actionMode === 'insert' ? (anchorLines.length > 0 && !anchorLineId) : !selectedLineId)"
              :loading="bindingId === asset.id"
              @click="chapterId && actionMode === 'insert' ? insertAsset(asset) : bindAsset(asset)"
            >{{ chapterId && actionMode === 'insert' ? '＋ 加入' : '绑定' }}</el-button>
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
import CuePlacementSelect from './production/CuePlacementSelect.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { Delete, Link, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bindSoundLibraryAsset,
  deleteSoundLibraryAsset,
  getSoundLibraryAssets,
  getSoundLibraryAudioUrl,
  importSoundLibraryPath,
  insertSoundLibraryAsset,
  uploadSoundLibraryFile,
} from '../api/soundLibrary'

const props = defineProps({
  chapterId: { type: Number, default: null },
  lines: { type: Array, default: () => [] },
  materialLines: { type: Array, default: () => [] },
  targetLineId: { type: Number, default: null },
})
const emit = defineEmits(['bound', 'inserted'])

const assets = ref([])
const loading = ref(false)
const bindingId = ref('')
const sourceFilter = ref('all')
const categoryFilter = ref('all')
const keyword = ref('')
const selectedLineId = ref(null)
const anchorLineId = ref(null)
const actionMode = ref('insert')
const panelRoot = ref(null)
const lastInsertion = ref('')
const mixPreset = ref('foley')
const insertForm = ref({ placement: 'with', volume_db: -9, duration: 0, offset: 0, fadeIn: 0, fadeOut: 0.1 })
const fileInput = ref(null)
const pendingPath = ref('')
const pendingFile = ref(null)
const pendingFileName = ref('')
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadForm = ref({ name: '', category: 'foley', tags: '' })
const scenePresets = [
  { label: '雨夜街道', keyword: '雨', mix: 'ambience' },
  { label: '楼道脚步', keyword: '脚步', mix: 'foley' },
  { label: '门外来客', keyword: '门', mix: 'foley' },
  { label: '深夜调查', keyword: '时钟', mix: 'ambience' },
  { label: '翻找线索', keyword: '翻页', mix: 'foley' },
  { label: '突发撞击', keyword: '撞击', mix: 'accent' },
]
const anchorLines = computed(() => (props.lines.length ? props.lines : props.materialLines).filter((line) => {
  let events = line.audio_events || []
  if (typeof events === 'string') {
    try { events = JSON.parse(events) } catch { events = [] }
  }
  return !Array.isArray(events) || !events.some((event) => event?.type === 'sound_library_placement')
}))

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
  if (value && anchorLines.value.some((line) => line.id === value)) anchorLineId.value = value
}, { immediate: true })

watch(anchorLines, (lines) => {
  if (!lines.some((line) => line.id === anchorLineId.value)) {
    anchorLineId.value = lines.find((line) => line.id === props.targetLineId)?.id || lines[0]?.id || null
  }
}, { immediate: true })

watch(() => props.chapterId, () => { lastInsertion.value = '' })

watch(() => props.materialLines, (value) => {
  if (selectedLineId.value && !value.some((line) => line.id === selectedLineId.value)) selectedLineId.value = null
}, { deep: true })

onMounted(loadAssets)

function applyScenePreset(scene) {
  keyword.value = scene.keyword
  categoryFilter.value = 'all'
  sourceFilter.value = 'all'
  mixPreset.value = scene.mix
  applyMixPreset(scene.mix)
}

function resetFilters() {
  keyword.value = ''
  categoryFilter.value = 'all'
  sourceFilter.value = 'all'
}

function applyMixPreset(preset) {
  const options = {
    ambience: { volume_db: -18, fadeIn: 0.8, fadeOut: 1.2 },
    foley: { volume_db: -9, fadeIn: 0, fadeOut: 0.1 },
    accent: { volume_db: -3, fadeIn: 0, fadeOut: 0.2 },
  }[preset]
  if (options) Object.assign(insertForm.value, options)
}

function pauseOtherPreviews(event) {
  panelRoot.value?.querySelectorAll('audio').forEach((audio) => {
    if (audio !== event.target) audio.pause()
  })
}

async function insertAsset(asset) {
  if (bindingId.value || !props.chapterId) return
  const sourceDuration = Number(asset.duration_ms || 0)
  const requestedDuration = Math.round(Number(insertForm.value.duration || 0) * 1000)
  const duration = requestedDuration > 0 ? Math.min(requestedDuration, sourceDuration) : sourceDuration
  if (!duration) { ElMessage.error('素材时长不可用，请刷新素材库'); return }
  const fadeIn = Math.min(duration, Math.round(Number(insertForm.value.fadeIn || 0) * 1000))
  const fadeOut = Math.min(duration - fadeIn, Math.round(Number(insertForm.value.fadeOut || 0) * 1000))
  bindingId.value = asset.id
  try {
    const response = await insertSoundLibraryAsset(asset.id, {
      chapter_id: props.chapterId,
      anchor_line_id: anchorLineId.value,
      placement: insertForm.value.placement,
      volume_db: Number(insertForm.value.volume_db ?? -9),
      duration_ms: duration,
      offset_ms: Math.round(Number(insertForm.value.offset || 0) * 1000),
      fade_in_ms: fadeIn,
      fade_out_ms: fadeOut,
    })
    if (response?.code !== 200) throw new Error(response?.message || '加入失败')
    const result = response.data || {}
    lastInsertion.value = `已${result.duplicate ? '再次' : ''}加入“${asset.name}”${result.placement_pending ? '，已保存位置，构建时间线后按对白音频落位' : `，从 ${(Number(result.start_ms || 0) / 1000).toFixed(1)} 秒进入`}`
    ElMessage.success(result.duplicate ? '已再加一条独立音效，可在台本中删除多余项' : '音效已加入')
    emit('inserted', { ...result, lineId: result.line_id, asset })
  } catch (error) {
    ElMessage.error(apiError(error, '音效加入失败'))
  } finally {
    bindingId.value = ''
  }
}

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
.quick-scenes { display: grid; gap: 12px; padding: 16px; border-radius: 10px; background: var(--el-fill-color-light); }
.quick-scenes > div:first-child { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.quick-scenes span, .insert-note { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.scene-shortcuts { display: flex; gap: 8px; flex-wrap: wrap; }
.scene-shortcuts .el-button { margin-left: 0; }
.quick-insert-target { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 10px; }
.target-heading { display: flex; gap: 12px; justify-content: space-between; align-items: center; flex-wrap: wrap; }
.insert-position { display: grid; grid-template-columns: minmax(240px, 2fr) minmax(140px, 1fr) minmax(160px, 1fr); gap: 10px; }
.mix-settings { border-bottom: none; }
.mix-settings :deep(.el-collapse-item__header) { min-height: 42px; height: auto; line-height: 1.5; }
.mix-settings :deep(.el-collapse-item__wrap) { border-bottom: none; }
.mix-settings :deep(.el-collapse-item__content) { padding-bottom: 0; }
.mix-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 8px 0 12px; }
.mix-grid label { display: grid; gap: 6px; font-size: 12px; }
.mix-grid .el-input-number { width: 100%; }
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
  .insert-position { grid-template-columns: 1fr 1fr; }
  .insert-position > :first-child { grid-column: 1 / -1; }
  .asset-count { margin-left: 0; }
  .asset-row { grid-template-columns: minmax(0, 1fr) auto; }
  .asset-row audio { grid-column: 1 / -1; grid-row: 2; }
  .bind-target { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .insert-position { grid-template-columns: 1fr; }
  .category-filter, .library-search { width: 100%; }
  .asset-row { grid-template-columns: 1fr; }
  .asset-actions, .asset-row audio { grid-column: 1; }
}
</style>
