<template>
    <section class="timeline-surface" :class="{compact}" aria-label="章节音轨">
      <div class="timeline-scroll">
        <div class="timeline-ruler">
          <aside class="track-label"><strong>统一时间轴</strong><span>{{ formatDuration(durationMs) }}</span></aside>
          <div class="timeline-canvas" :style="canvasStyle">
            <span v-for="tick in timelineTicks" :key="tick.ms" class="time-tick" :style="tickStyle(tick)">{{ tick.label }}</span>
          </div>
        </div>
        <article v-for="track in tracks" :key="track.key" class="track-row">
          <aside class="track-label">
            <el-icon v-if="track.icon"><component :is="track.icon" /></el-icon>
            <strong>{{ track.label }}</strong>
            <span>{{ track.clips?.length || 0 }} 个片段</span>
            <el-tag v-if="track.status && track.status !== 'ready'" size="small" effect="plain">
              {{ statusLabel(track.status) }}
            </el-tag>
          </aside>
          <div class="timeline-canvas" :style="canvasStyle">
            <span v-for="tick in timelineTicks" :key="`grid-${track.key}-${tick.ms}`" class="timeline-grid-line" :style="tickStyle(tick)" />
            <div
              v-for="clip in track.clips || []"
              :key="clip.id"
              class="clip"
              :class="{ done: clip.line?.is_done === 1 || clip.line?.status === 'done', muted: clip.is_muted, selected: String(clip.line_id) === String(selectedLineId) }"
              :style="clipStyle(clip)"
              @pointerdown="$emit('interact', $event, clip, 'move')"
              @click="$emit('select',clip)"
              @keydown.enter="$emit('select',clip)"
              @keydown.space.prevent="$emit('select',clip)"
              role="button" tabindex="0" :aria-label="`音轨片段：${clip.line?.text_content || clip.asset?.type || clip.id}`" :data-clip-line-id="clip.line_id"
            >
              <span v-if="editable && !compact" class="clip-handle clip-handle-left" @pointerdown.stop="$emit('interact', $event, clip, 'resize-left')" />
              <strong>{{ clip.line?.scene_title || track.label }}</strong>
              <p>{{ clip.line?.text_content || clip.asset?.type || '音频片段' }}</p>
              <span>
                {{ formatDuration(clip.start_ms) }} 起 · {{ formatDuration(clip.duration_ms) }} · {{ formatVolume(clip.volume_db) }}
              </span>
              <span v-if="editable && !compact" class="clip-handle clip-handle-right" @pointerdown.stop="$emit('interact', $event, clip, 'resize-right')" />
            </div>
            <span v-if="!(track.clips?.length)" class="empty-lane">暂无真实音频片段</span>
          </div>
        </article>
      </div>
    </section>

</template>
<script setup>
import { computed } from 'vue'
const props=defineProps({tracks:{type:Array,default:()=>[]},durationMs:{type:Number,default:0},pixelsPerSecond:{type:Number,default:80},compact:Boolean,editable:Boolean,selectedLineId:[Number,String]})
defineEmits(['select','interact'])
const pixelsPerSecond=computed(()=>props.pixelsPerSecond)
const timelineDurationMs = computed(() => Math.max(Number(props.durationMs || 0), 10000))
const timelineCanvasWidth = computed(() => `${Math.max(960, timelineDurationMs.value / 1000 * pixelsPerSecond.value + 24)}px`)
const canvasStyle = computed(() => ({ width: timelineCanvasWidth.value, '--grid-size': `${pixelsPerSecond.value}px` }))
const timelineTicks = computed(() => {
  const duration = timelineDurationMs.value
  const step = duration <= 30000 ? 5000 : duration <= 120000 ? 10000 : 30000
  const ticks = []
  for (let ms = 0; ms <= duration; ms += step) ticks.push({ ms, label: `${Math.round(ms / 1000)}s` })
  if (ticks.at(-1)?.ms !== duration) ticks.push({ ms: duration, label: `${Math.round(duration / 1000)}s` })
  return ticks
})

function formatDuration(milliseconds = 0) {
  const totalSeconds = Math.max(0, Number(milliseconds || 0)) / 1000
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)} 秒`
  return `${Math.floor(totalSeconds / 60)}分${Math.floor(totalSeconds % 60)}秒`
}

function formatVolume(value = 0) {
  const number = Number(value || 0)
  return `${number > 0 ? '+' : ''}${number.toFixed(1)} dB`
}

function tickStyle(tick) {
  return { left: `${tick.ms / 1000 * pixelsPerSecond.value}px` }
}

function clipStyle(clip) {
  const left = Math.max(0, Number(clip.start_ms || 0)) / 1000 * pixelsPerSecond.value
  const width = Math.max(8, Number(clip.duration_ms || 0) / 1000 * pixelsPerSecond.value)
  if (props.compact) return { left: `${Number(clip.start_ms||0)/Math.max(1,props.durationMs)*100}%`, width: `${Number(clip.duration_ms||0)/Math.max(1,props.durationMs)*100}%` }
  return { left: `${left}px`, width: `${width}px` }
}


function statusLabel(status){return {ready:'已就绪',stale:'需刷新',missing_audio:'缺少音频'}[status]||status}
</script>
<style scoped>
.timeline-surface { overflow-x: auto; padding-bottom: 8px; border: 1px solid var(--el-border-color-light); border-radius: 8px; background: var(--el-bg-color); }
.timeline-scroll { min-width: max-content; }
.timeline-ruler, .track-row { display: grid; grid-template-columns: 160px auto; }
.timeline-ruler { min-height: 42px; border-bottom: 1px solid var(--el-border-color-light); }
.track-row { min-height: 118px; border-bottom: 1px solid var(--el-border-color-light); }
.track-row:last-child { border-bottom: 0; }
.track-label { position: sticky; left: 0; z-index: 4; display: grid; align-content: center; gap: 6px; padding: 14px; border-right: 1px solid var(--el-border-color-light); background: var(--el-fill-color-light); }
.track-label strong, .track-label span { display: block; }
.track-label span { color: var(--el-text-color-secondary); font-size: 12px; }
.timeline-canvas { position: relative; min-height: 100%; background-image: linear-gradient(to right, color-mix(in srgb, var(--el-border-color-light) 62%, transparent) 1px, transparent 1px); background-size: var(--grid-size, 80px) 100%; }
.timeline-ruler .timeline-canvas { min-height: 42px; }
.time-tick { position: absolute; top: 9px; z-index: 2; color: var(--el-text-color-secondary); font-size: 11px; transform: translateX(-50%); }
.timeline-grid-line { position: absolute; top: 0; bottom: 0; border-left: 1px dashed color-mix(in srgb, var(--el-border-color) 70%, transparent); pointer-events: none; }
.clip { position: absolute; top: 14px; display: grid; align-content: start; gap: 5px; min-height: 76px; padding: 10px; overflow: hidden; border: 1px solid color-mix(in srgb, var(--el-color-primary) 36%, var(--el-border-color)); border-radius: 8px; background: color-mix(in srgb, var(--el-color-primary-light-9) 82%, var(--el-bg-color)); cursor: pointer; }
.clip:active { cursor: grabbing; }
.clip-handle { position: absolute; top: 0; bottom: 0; z-index: 3; width: 8px; cursor: ew-resize; }
.clip-handle-left { left: 0; }
.clip-handle-right { right: 0; }
.clip.done { border-color: color-mix(in srgb, var(--el-color-success) 45%, var(--el-border-color)); background: color-mix(in srgb, var(--el-color-success-light-9) 80%, var(--el-bg-color)); }
.clip.muted { opacity: .6; }
.clip p { max-width: 420px; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clip span { color: var(--el-text-color-secondary); font-size: 11px; }
.empty-lane { position: absolute; top: 50%; left: 14px; color: var(--el-text-color-secondary); font-size: 12px; transform: translateY(-50%); }

.clip{box-sizing:border-box}.clip.selected{outline:2px solid var(--el-color-primary,#ae8053);outline-offset:-2px}.clip:focus-visible{outline:2px solid var(--el-color-primary,#ae8053)}.compact{--el-border-color-light:#dedbd3;--el-bg-color:#faf8f2;--el-text-color-secondary:#786f62;--el-color-primary:#a47a4c;--el-color-primary-light-9:#e9e0d3;--el-color-success:#63765d;--el-color-success-light-9:#e7ebdf}.compact .timeline-ruler{display:none}.compact .timeline-scroll{min-width:0}.compact .track-row{grid-template-columns:64px minmax(0,1fr);min-height:32px}.compact .track-label{padding:6px;font-size:10px}.compact .track-label span,.compact .track-label .el-icon{display:none}.compact .timeline-canvas{width:100%!important;min-height:32px;background:none}.compact .timeline-grid-line{display:none}.compact .clip{top:4px;min-height:24px;height:24px;padding:3px;border-radius:4px}.compact .clip strong,.compact .clip span{display:none}.compact .clip p{font-size:9px}.compact .empty-lane{font-size:10px}
</style>