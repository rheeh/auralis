<!-- src/components/WaveCellPro.vue -->
<template>
  <div class="wavecell">
    <div class="preview-note"><strong>原音处理预听</strong><span>不选区间时调整整段；选中区间后只改变该段速度，其余部分保持原速。</span></div>
    <div class="bar">
      <!-- 替换原来的按钮 -->
      <el-button :type="isPlaying ? 'danger' : 'success'" class="play-btn" :class="{ playing: isPlaying }" circle
        size="default" :disabled="!ready || !!loadError" @click="togglePlay">
        <template #icon>
          <el-icon :size="22">
            <VideoPause v-if="isPlaying" />
            <VideoPlay v-else />
          </el-icon>
        </template>
      </el-button>

      <!-- 下载按钮 -->
      <el-tooltip :content="ready ? '下载音频' : '暂无音频'" placement="top">
        <el-button class="download-btn" :class="{ 'is-disabled': !ready }" circle size="default"
          @click="downloadAudio" :disabled="!ready">
          <template #icon>
            <el-icon :size="18">
              <Download />
            </el-icon>
          </template>
        </el-button>
      </el-tooltip>


      <span class="lbl">速度 <strong>{{ rate.toFixed(1) }}×</strong></span>
      <el-slider v-model="rate" :min="0.5" :max="2.0" :step="0.1" :show-tooltip="false" class="slider" />

      <span class="lbl">音量 <strong>{{ vol2x.toFixed(2) }}×</strong></span>
      <el-slider v-model="vol2x" :min="0" :max="2.0" :step="0.01" :show-tooltip="false" class="slider" />

      <span class="lbl">添加间隔(s)</span>
      <el-input-number v-model="tailSilence" :min="0" :max="30" :step="0.1" size="small" />


      <!-- <el-switch v-model="regionMode" active-text="标注" inactive-text="浏览" /> -->
      <el-button size="small" @click="makeRegion" :disabled="hasRegion">选择局部变速区间</el-button>
      <!-- <el-button size="small" @click="loopRegion" :disabled="!hasRegion">循环区间</el-button> -->
      <el-button size="small" @click="clearRegion" :disabled="!hasRegion">清除区间</el-button>

      <el-button size="small" type="primary" @click="confirmProcess" :disabled="!ready">{{ variantMode ? '保存为新音频版本' : '应用处理' }}</el-button>
    </div>

    <div ref="container" class="wave" />
    <small v-if="loadError" class="load-error">{{ loadError }}</small>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, Download } from '@element-plus/icons-vue'
import WaveSurfer from 'wavesurfer.js'
import Regions from 'wavesurfer.js/dist/plugins/regions.esm.js'


const props = defineProps({
  src: { type: String, required: true },     // 建议传 file://；否则会尝试转换
  speed: { type: Number, default: 1.0 },     // 初始速度
  volume2x: { type: Number, default: 1.0 },  // 0~2.0（前端试听倍数）
  startMs: { type: Number, default: null },  // 初始选区
  endMs: { type: Number, default: null },
  variantMode: { type: Boolean, default: false },
})

const emit = defineEmits([
  'request-stop-others', // (instance) 让父级停掉其它行
  'confirm',             // ({ speed, volume, start_ms, end_ms })
  'ready',
  'dispose',             // () 组件卸载时触发
  'ended',               // () 播放结束
])

const container = ref(null)

let ws = null
let regionsPlugin = null
const region = ref(null) // ← 关键：响应式
let themeListener = null

const isPlaying = ref(false)
const ready = ref(false)
const loadError = ref('')
const rate = ref(props.speed || 1.0)
const vol2x = ref(Math.max(0, Math.min(props.volume2x ?? 1.0, 2.0)))
const regionMode = ref(false)

const tailSilence = ref(0) // 默认 0 秒

const hasRegion = computed(() => !!region.value)

function getWaveColors() {
  const dark = document?.documentElement?.classList?.contains('dark')
  return {
    waveColor: dark ? '#5b6473' : '#cfd6e4',
    progressColor: '#409EFF',
  }
}

function applyWaveTheme() {
  if (!ws) return
  const { waveColor, progressColor } = getWaveColors()
  if (ws.setOptions) ws.setOptions({ waveColor, progressColor })
}

function toUrl(src) {
  if (!src) return ''
  if (/^https?:\/\//i.test(src) || /^file:\/\//i.test(src)) return src
  return window.native?.pathToFileUrl ? window.native.pathToFileUrl(src) : src
}

onMounted(async () => {
  themeListener = () => applyWaveTheme()
  window.addEventListener('sv-theme-changed', themeListener)

  const { waveColor, progressColor } = getWaveColors()
  ws = WaveSurfer.create({
    container: container.value,
    height: 64,
    normalize: true,
    autoScroll: true,
    autoCenter: true,
    barWidth: 2,
    waveColor,
    progressColor,
  })

  // v7：registerPlugin 获取实例
  regionsPlugin = ws.registerPlugin(Regions.create({ dragSelection: true }))

  ws.on('ready', () => {
    ready.value = true
    loadError.value = ''
    ws.setPlaybackRate(rate.value)
    ws.setVolume(Math.max(0, Math.min(vol2x.value ?? 1.0, 2.0)))

    // 恢复初始区域
    if (props.startMs != null && props.endMs != null && props.endMs > props.startMs) {
      region.value = regionsPlugin.addRegion({
        start: props.startMs / 1000,
        end: props.endMs / 1000,
        drag: true,
        resize: true,
        color: 'rgba(64,158,255,0.15)',
      })
    }
    emit('ready', ws)
  })

  ws.on('play', () => {
    isPlaying.value = true
    emit('request-stop-others', ws)
  })
  ws.on('pause', () => { isPlaying.value = false })
  ws.on('finish', () => {
    isPlaying.value = false        // 确保状态同步
    emit('ended', { src: props.src })                 // 通知父组件
  })
  ws.on('error', (error) => {
    ready.value = false
    isPlaying.value = false
    loadError.value = '音频加载失败'
    console.error('WaveSurfer 音频加载失败:', props.src, error)
  })

  // 区域事件（v7：挂 regionsPlugin）
  regionsPlugin.on('region-created', r => { region.value = r })
  regionsPlugin.on('region-updated', r => { region.value = r })
  regionsPlugin.on('region-clicked', (r, e) => {
    e.stopPropagation()
    region.value = r
    if (regionMode.value) r.play({ loop: true })  // v7：用 play({ loop:true })
    else ws.play(r.start)
  })

  try {
    await ws.load(toUrl(props.src))
  } catch (error) {
    ready.value = false
    isPlaying.value = false
    loadError.value = '音频加载失败'
    console.error('WaveSurfer 音频加载异常:', props.src, error)
  }
})

onBeforeUnmount(() => {
  try {
    if (themeListener) window.removeEventListener('sv-theme-changed', themeListener)
    emit('dispose', ws)
    ws && ws.destroy()
  }
  finally { ws = null; regionsPlugin = null; region.value = null; themeListener = null }
})

// —— 实时预听：速度/音量 —— //
watch(rate, v => ws && ws.setPlaybackRate(v || 1.0))
watch(vol2x, v => ws && ws.setVolume(Math.max(0, Math.min(v ?? 1.0, 2.0))))

// 切换“标注/浏览”：开关拖拽建区
watch(regionMode, (on) => {
  if (regionsPlugin?.setOptions) regionsPlugin.setOptions({ dragSelection: !!on })

})

function togglePlay() {
  if (!ws || !ready.value || loadError.value) {
    ElMessage.warning(loadError.value || '音频尚未加载完成')
    return
  }
  isPlaying.value ? ws.pause() : ws.play()
}

function play() {
  if (!ws || !ready.value || loadError.value) {
    ElMessage.warning(loadError.value || '音频尚未加载完成')
    return
  }
  ws.play()
}

function pause() {
  if (ws) ws.pause()
}

defineExpose({ play, pause })

function makeRegion() {
  if (!ws || region.value) return
  const dur = ws.getDuration() || 0
  const start = Math.max(0, (ws.getCurrentTime?.() || 0) - 0.25)
  const end = Math.min(dur, start + 1.5)
  region.value = regionsPlugin.addRegion({
    start, end,
    drag: true, resize: true,
    color: 'rgba(55,201,198,0.2)',
  })
}

function loopRegion() {
  if (region.value) region.value.play({ loop: true })
}

function clearRegion() {
  if (region.value) { region.value.remove(); region.value = null }
}

async function confirmProcess() {
  const start_ms = region.value ? Math.round(region.value.start * 1000) : null
  const end_ms = region.value ? Math.round(region.value.end * 1000) : null
  const current_ms = ws ? Math.round(ws.getCurrentTime() * 1000) : 0  // ✅ 新增
  if (region.value && Math.abs(Number(rate.value || 1) - 1) < 1e-6) {
    ElMessage.warning('已选择局部区间，请先把速度调为非 1.0×')
    return
  }
  await ElMessageBox.confirm(
    props.variantMode ? (region.value ? '只对选中区间应用当前速度，区间外保持原速，并从原音保存为独立版本。' : '对整段应用当前速度和音量，并从原音保存为独立版本。') : '确认应用当前音频处理吗？',
    props.variantMode ? '保存独立音频版本' : '应用本句音频处理',
    { type: props.variantMode ? 'info' : 'warning' },
  )
  emit('confirm', {
    speed: Number(rate.value || 1.0),
    volume: Number(vol2x.value || 1.0),
    start_ms, end_ms,
    silence_sec: Number(tailSilence.value || 0),
    current_ms,
    region_action: region.value ? 'speed' : null,
  })
}

// 下载音频
async function downloadAudio() {
  if (!props.src) {
    ElMessage.warning('暂无可下载的音频')
    return
  }

  try {
    // 解析源路径（支持 file:// 和普通路径）
    let sourcePath = props.src
    if (sourcePath.startsWith('file:///')) {
      // 解码 file:// URL 并提取路径
      sourcePath = decodeURI(sourcePath.replace('file:///', ''))
    } else if (sourcePath.startsWith('file://')) {
      sourcePath = decodeURI(sourcePath.replace('file://', ''))
    }
    
    // 去除可能存在的查询参数 (?v=xxx)
    sourcePath = sourcePath.split('?')[0]
    
    // 提取文件名作为默认保存名
    const fileName = sourcePath.split(/[\\/]/).pop() || 'audio.wav'
    
    // Electron 环境下使用原生保存对话框
    if (window.native?.saveFile && window.native?.writeFile) {
      const savePath = await window.native.saveFile({
        title: '保存音频文件',
        defaultPath: fileName,
        filters: [{ name: '音频文件', extensions: ['wav', 'mp3', 'flac', 'ogg'] }]
      })
      
      if (!savePath) {
        return // 用户取消
      }
      
      // 通过 fetch 获取音频数据
      const response = await fetch(toUrl(props.src))
      const arrayBuffer = await response.arrayBuffer()
      const uint8Array = new Uint8Array(arrayBuffer)
      
      // 使用 Electron 的 writeFile 方法直接写入文件
      const result = await window.native.writeFile(savePath, uint8Array)
      
      if (result.success) {
        ElMessage.success('音频下载成功')
      } else {
        ElMessage.error('写入文件失败: ' + (result.error || '未知错误'))
      }
    } else {
      // 非 Electron 环境，使用浏览器下载
      const response = await fetch(toUrl(props.src))
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      
      ElMessage.success('音频下载成功')
    }
  } catch (error) {
    console.error('下载音频失败:', error)
    ElMessage.error('下载音频失败: ' + (error.message || '未知错误'))
  }
}
</script>

<style scoped>
.wavecell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.preview-note{display:flex;align-items:baseline;justify-content:space-between;gap:10px;color:var(--el-text-color-secondary);font-size:11px}.preview-note strong{color:var(--el-text-color-primary)}

.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.lbl {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-left: 6px;
}
.lbl strong{color:var(--el-color-primary)}

.slider {
  width: 140px;
  min-width: 100px;
  flex:1 1 120px;
}

.wave {
  width: 100%;
}

.load-error {
  color: var(--el-color-danger);
  font-size: 12px;
}



/* 下载按钮样式 */
.download-btn {
  background: linear-gradient(135deg, #74b9ff 0%, #a29bfe 100%);
  border: none;
  color: #fff;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(116, 185, 255, 0.35);
}

.download-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(116, 185, 255, 0.5);
  background: linear-gradient(135deg, #a29bfe 0%, #74b9ff 100%);
}

.download-btn:active {
  transform: scale(0.95);
}

.download-btn .el-icon {
  color: #fff;
}

.download-btn.is-disabled {
  background: #c0c4cc;
  box-shadow: none;
  cursor: not-allowed;
}

.download-btn.is-disabled:hover {
  transform: none;
  background: #c0c4cc;
  box-shadow: none;
}
@media(max-width:900px){.bar{display:grid;grid-template-columns:auto auto minmax(80px,1fr) minmax(80px,1fr);align-items:center}.bar .play-btn,.bar .download-btn{grid-row:1}.bar .lbl{margin-left:0}.bar .slider{width:100%}.bar .el-input-number{width:120px}.preview-note{align-items:flex-start;flex-direction:column;gap:2px}}
@media(max-width:600px){.bar{grid-template-columns:auto auto 1fr}.bar .slider{grid-column:2/-1}.preview-note span{line-height:1.4}}
</style>
