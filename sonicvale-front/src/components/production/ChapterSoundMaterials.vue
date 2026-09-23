<template>
  <section v-if="lines.length" class="chapter-sounds" aria-label="音效与背景音乐">
    <header><div><h3>音效与背景音乐</h3><p>先试听素材，再设置入场和持续时间。雨声、钢琴等铺底声音可在「编辑时长与位置」中铺满人声，超出原长会循环。</p></div><el-tag effect="plain">{{ lines.length }} 项</el-tag></header>
    <article v-for="line in lines" :key="line.id" class="sound-row" :data-sound-line-id="line.id">
      <div class="sound-copy">
        <div><el-tag size="small" effect="plain">{{ label(line) }}</el-tag><small>{{ line.scene_title || '未命名场景' }} · 第 {{ line.line_order }} 行</small></div>
        <p>{{ line.sound_prompt || line.text_content || '尚未填写声音说明' }}</p>
        <div class="sound-tags"><el-tag v-for="tag in line.sound_tags || []" :key="tag" size="small" type="info" effect="plain">{{ tag }}</el-tag></div>
      </div>
      <div class="sound-preview">
        <audio v-if="sources[line.id]?.available" :ref="el=>setPlayer(line.id,el)" :key="`${line.id}-${audioRevision}`" controls preload="none" :src="getLineAudioUrl(line.id,audioRevision)" :aria-label="`试听${label(line)}：${line.sound_prompt || line.text_content}`" @play="startPreview($event.target)" @error="failed[line.id]=true" />
        <small v-else>待选素材 · 当前只有文字说明</small>
        <small v-if="failed[line.id]" role="status">音频暂时无法播放，请刷新或重新选择素材。</small>
        <small v-else-if="sources[line.id]?.available">素材原音试听；循环、音量与淡入淡出请在渲染成片后检查。</small>
      </div>
      <div class="sound-actions">
        <el-button size="small" type="primary" plain @click="$emit('choose',line,'library')">{{ sources[line.id]?.available ? '更换素材' : '选择素材' }}</el-button>
        <el-button size="small" @click="$emit('choose',line,'recommendations')">标签匹配</el-button>
        <el-button size="small" :disabled="!sources[line.id]?.available" @click="$emit('edit',line)">编辑时长与位置</el-button>
        <el-button size="small" text @click="$emit('edit-type',line)">修改类型 / 角色</el-button>
        <el-button size="small" text type="danger" @click="$emit('remove',line)">移除</el-button>
      </div>
    </article>
  </section>
</template>

<script setup>
import {onBeforeUnmount,reactive,watch} from 'vue'
import {getLineAudioUrl} from '../../api/line'
const props=defineProps({lines:{type:Array,default:()=>[]},sources:{type:Object,default:()=>({})},audioRevision:[String,Number]})
const emit=defineEmits(['choose','edit','edit-type','remove','preview'])
const players=new Map(),failed=reactive({})
function label(line){return (line.track||line.line_type)==='bgm'?'背景音乐':'音效'}
function setPlayer(id,el){if(el)players.set(id,el);else{players.get(id)?.pause();players.delete(id)}}
function stopPreviews(except=null){for(const player of players.values())if(player!==except)player.pause()}
function startPreview(player){stopPreviews(player);emit('preview')}
watch(()=>props.audioRevision,()=>{stopPreviews();Object.keys(failed).forEach(key=>delete failed[key])},{flush:'pre'})
onBeforeUnmount(()=>stopPreviews())
defineExpose({stopPreviews})
</script>

<style scoped>
.chapter-sounds{padding:16px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:var(--el-bg-color)}
.chapter-sounds header{display:flex;justify-content:space-between;align-items:start;gap:16px}.chapter-sounds h3{margin:0;font-size:16px}.chapter-sounds header p{margin:6px 0 14px;color:var(--el-text-color-secondary);font-size:12px;line-height:1.6}
.sound-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(240px,320px);gap:12px 20px;padding:16px 0;border-top:1px solid var(--el-border-color-lighter)}
.sound-copy>div,.sound-tags,.sound-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.sound-copy p{margin:8px 0;line-height:1.6;font-size:14px}.sound-copy small,.sound-preview small{color:var(--el-text-color-secondary);font-size:12px}.sound-preview{display:grid;align-content:center;gap:6px}.sound-preview audio{width:100%;height:36px}.sound-actions{grid-column:1/-1}.sound-actions .el-button+.el-button{margin-left:0}
@media(max-width:680px){.sound-row{grid-template-columns:1fr}.sound-actions{grid-column:1}.chapter-sounds{padding:12px}}
</style>
