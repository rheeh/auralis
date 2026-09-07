<template>
  <figure v-if="scenes.length" class="scene-illustration" :data-scene-id="current?.id" aria-label="随剧情切换的场景画面">
    <div class="scene-frame">
      <img v-for="scene in scenes" :key="scene.id" :src="imageUrl(scene.file)" :alt="scene.title" :class="{visible:scene.id===current?.id}" :aria-hidden="scene.id!==current?.id" decoding="async" />
      <figcaption><small>雨夜来件 · {{ index + 1 }} / {{ scenes.length }}</small><strong>{{ current?.title }}</strong><span>{{ current?.caption }}</span></figcaption>
    </div>
    <div class="scene-chapters"><span>画面随播放自动切换</span><button v-for="scene in scenes" :key="scene.id" :disabled="!Number.isFinite(scene.start)" :aria-pressed="scene.id===current?.id" @click="$emit('seek',scene.start)">{{ scene.title }}</button></div>
  </figure>
</template>
<script setup>
import { computed } from 'vue'
import { sceneAtTime } from '../../demo/sceneImages'
const props = defineProps({ scenes: { type:Array, default:()=>[] }, seconds: { type:Number, default:0 } })
defineEmits(['seek'])
const current = computed(() => sceneAtTime(props.scenes, props.seconds))
const index = computed(() => props.scenes.findIndex(scene => scene.id === current.value?.id))
const imageUrl = file => `${import.meta.env.BASE_URL}demo-night/scenes/${file}`
</script>
<style scoped>
.scene-illustration{margin:0 0 20px;border:1px solid #3e4b46;border-radius:12px;overflow:hidden;background:#111d22;color:#f5e9d6}.scene-frame{position:relative;height:clamp(200px,28vw,330px);overflow:hidden}.scene-frame img{position:absolute;width:100%;height:100%;object-fit:cover;object-position:center 58%;opacity:0;transition:opacity .65s ease}.scene-frame img.visible{opacity:1}.scene-frame:after{content:'';position:absolute;inset:0;background:linear-gradient(0deg,#071015cf,transparent 75%);pointer-events:none}.scene-frame figcaption{position:absolute;left:28px;bottom:22px;z-index:1;display:grid;gap:5px}.scene-frame small{font-size:10px;letter-spacing:.1em;color:#d3c6ac}.scene-frame strong{font:27px 'Songti SC',serif}.scene-frame span{font-size:12px;color:#d7d5c8}.scene-chapters{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:10px 16px;flex-wrap:wrap}.scene-chapters>span{margin-right:auto;font-size:11px;color:#b7c1bb}.scene-chapters button{border:1px solid #53635b;border-radius:20px;background:transparent;color:#cbd1c5;padding:7px 13px;font:inherit;font-size:11px;cursor:pointer}.scene-chapters button[aria-pressed=true]{background:#d6c294;border-color:#d6c294;color:#172021}.scene-chapters button:disabled{opacity:.5;cursor:default}@media(prefers-reduced-motion:reduce){.scene-frame img{transition:none}}@media(max-width:600px){.scene-frame figcaption{left:18px;bottom:18px}.scene-chapters{gap:6px}.scene-chapters>span{width:100%}.scene-chapters button{flex:1;padding:8px}}
</style>
