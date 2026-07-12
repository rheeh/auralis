<template>
  <section class="character-archive">
    <header><div><p class="eyebrow">人物设定</p><h3>本次改编人物卡</h3></div><el-tag effect="plain">{{ selectedRoles.length }} 人</el-tag></header>
    <div class="character-grid">
      <article v-for="(role,index) in selectedRoles" :key="role.draft_id || role.name" :style="{ '--role-color': roleColor(index) }">
        <el-avatar :size="64" :src="avatarUrl(role)">{{ role.name?.slice(0,1) }}</el-avatar>
        <div class="copy"><strong>{{ role.name }}</strong><small>{{ role.identity || '身份待补充' }}</small><p>{{ role.speech_style || '未设置表达特点' }}</p></div>
        <div class="tags"><button v-if="voiceById(role.default_voice_id)?.reference_path" type="button" @click="togglePreview(voiceById(role.default_voice_id))"><el-icon><component :is="previewingId===role.default_voice_id?VideoPause:VideoPlay" /></el-icon>{{ previewingId===role.default_voice_id?'停止':'试听' }} {{ voiceName(role.default_voice_id) }}</button><span v-else>{{ voiceName(role.default_voice_id) }}</span></div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { fetchTTSProviders } from '../../api/provider'
import { fetchVoicesByTTS, getVoiceAudioUrl } from '../../api/voice'
import { getRoleAvatarUrl } from '../../api/drama'

const props = defineProps({ roles:{type:Array,default:()=>[]}, sessionId:String })
const voices = ref([])
const previewingId = ref(null)
const voicePlayer = new Audio()
const selectedRoles = computed(()=>props.roles.filter(role=>role.selected!==false))
onMounted(async()=>{
  const providers=(await fetchTTSProviders())||[]
  voices.value=(await Promise.all(providers.filter(item=>item.status!==0).map(item=>fetchVoicesByTTS(item.id)))).flat()
})
onBeforeUnmount(()=>{voicePlayer.pause();voicePlayer.removeAttribute('src')})
function avatarUrl(role){return getRoleAvatarUrl(props.sessionId,role.avatar_path)}
function voiceById(id){return voices.value.find(item=>item.id===id)||null}
function voiceName(id){return voices.value.find(item=>item.id===id)?.name||'未绑定音色'}
async function togglePreview(voice){if(!voice)return;if(previewingId.value===voice.id&&!voicePlayer.paused){voicePlayer.pause();previewingId.value=null;return}voicePlayer.pause();previewingId.value=voice.id;voicePlayer.src=getVoiceAudioUrl(voice.id,Date.now());voicePlayer.onended=()=>previewingId.value=null;try{await voicePlayer.play()}catch(error){previewingId.value=null;ElMessage.error(error?.message||'该音色暂时无法试听')}}
function roleColor(index){return ['#37c9c6','#8b7cf6','#ef7eb8','#f2a84b','#55a7ed','#70bd69'][index%6]}
</script>

<style scoped>
.character-archive{display:grid;gap:14px}.character-archive header{display:flex;align-items:center;justify-content:space-between}.character-archive h3,.eyebrow{margin:0}.eyebrow{color:var(--el-color-primary);font-size:11px}.character-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.character-grid article{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;padding:14px;border:1px solid color-mix(in srgb,var(--role-color) 42%,var(--el-border-color));border-top:4px solid var(--role-color);border-radius:14px;background:var(--el-bg-color);min-width:0}.character-grid .el-avatar{background:color-mix(in srgb,var(--role-color) 18%,var(--el-fill-color));border:2px solid color-mix(in srgb,var(--role-color) 54%,white)}.copy{min-width:0}.copy strong,.copy small{display:block}.copy small,.copy p,.tags span{color:var(--el-text-color-secondary)}.copy p{margin:6px 0 0;line-height:1.5}.tags{grid-column:2;display:flex;align-items:center;justify-content:flex-start;min-width:0;font-size:12px}.tags span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tags button{display:flex;align-items:center;gap:5px;border:0;color:var(--el-color-primary);background:none;cursor:pointer}
</style>
