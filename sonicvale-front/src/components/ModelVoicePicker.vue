<template>
  <el-popover v-model:visible="visible" trigger="click" placement="bottom-start" :width="460" popper-class="model-voice-popover">
    <template #reference><button class="picker-trigger" type="button" :aria-label="label" :aria-expanded="visible">{{ selected?.name || '按模型选择音色' }}<span>⌄</span></button></template>
    <section class="voice-browser" :aria-label="label">
      <el-input v-model="query" clearable placeholder="搜索音色、性别、风格或模型" aria-label="搜索角色音色" />
      <div class="model-groups">
        <details v-for="group in groups" :key="group.id" :open="isOpen(group)" @toggle="remember(group.id,$event)">
          <summary><strong>{{ group.label }}</strong><span>{{ group.voices.length }} 个音色</span></summary>
          <p v-if="group.note" class="model-note">{{ group.note }}</p>
          <div v-for="voice in group.voices" :key="voice.id" class="voice-choice" :class="{selected:voice.id===modelValue}">
            <button type="button" class="choose-voice" :disabled="isVoiceDisabled(voice.id)" :aria-pressed="voice.id===modelValue" @click="choose(voice.id)"><strong>{{ voice.name }}</strong><small>{{ displayTags(voice) }}</small></button>
            <button type="button" class="preview-voice" :aria-label="`试听音色：${voice.name}`" :disabled="!voice.reference_path" @click="$emit('preview',voice)">{{ previewingId===voice.id?'停止':'试听' }}</button>
          </div>
        </details>
        <el-empty v-if="!groups.length" description="未找到音色" :image-size="45" />
      </div>
      <footer><el-button v-if="clearable && modelValue" text @click="choose(null)">清除选择</el-button><router-link to="/voices" @click="visible=false">管理 / 复刻音色</router-link></footer>
    </section>
  </el-popover>
</template>
<script setup>
import { computed, ref, reactive } from 'vue'
import { groupVoices } from '../utils/voiceGroups'
const props=defineProps({modelValue:Number,providers:{type:Array,default:()=>[]},voices:{type:Array,default:()=>[]},previewingId:Number,isVoiceDisabled:{type:Function,default:()=>false},clearable:Boolean,label:{type:String,default:'按模型选择角色音色'}})
const emit=defineEmits(['update:modelValue','preview'])
const visible=ref(false),query=ref(''),opened=reactive({})
const groups=computed(()=>groupVoices(props.providers,props.voices,query.value))
const selected=computed(()=>props.voices.find(v=>v.id===props.modelValue))
function isOpen(group){return query.value.trim()?true:(opened[group.id]??false)}
function remember(id,event){if(!query.value.trim())opened[id]=event.target.open}
function choose(id){emit('update:modelValue',id);visible.value=false}
function displayTags(voice){return (voice.description||'').split(',').filter(t=>!t.includes(':')&&!/qwen|cosyvoice|sambert|edge/i.test(t)).slice(0,5).join(' · ')}
</script>
<style scoped>
.picker-trigger{display:flex;justify-content:space-between;gap:10px;align-items:center;width:100%;min-height:34px;padding:6px 12px;border:1px solid var(--el-border-color);border-radius:6px;background:var(--el-bg-color);color:var(--el-text-color-primary);font:inherit;text-align:left;cursor:pointer}.voice-browser{display:grid;gap:10px}.model-groups{max-height:380px;overflow:auto}.model-groups details{border-bottom:1px solid var(--el-border-color-lighter)}summary{display:flex;align-items:center;gap:7px;padding:12px 2px;cursor:pointer;list-style:none}summary:before{content:'▸'}details[open]>summary:before{content:'▾'}summary strong{font-size:12px;overflow-wrap:anywhere}summary span{margin-left:auto;white-space:nowrap;color:var(--el-text-color-secondary);font-size:12px}.model-note{margin:0 0 7px;font-size:12px;color:var(--el-text-color-secondary)}.voice-choice{display:flex;align-items:center;border-radius:6px;margin:3px 0}.voice-choice:hover,.voice-choice.selected{background:var(--el-fill-color-light)}.choose-voice{flex:1;display:grid;gap:4px;text-align:left;padding:10px;border:0;background:none;color:var(--el-text-color-primary);cursor:pointer}.choose-voice small{color:var(--el-text-color-secondary)}.preview-voice{border:0;background:none;color:var(--el-color-primary);padding:10px;cursor:pointer}button:disabled{opacity:.4;cursor:not-allowed}footer{display:flex;justify-content:flex-end;align-items:center;gap:12px}footer a{font-size:12px;color:var(--el-color-primary)}
</style>
<style>.model-voice-popover{max-width:calc(100vw - 32px);box-sizing:border-box}</style>
