<template>
  <section class="character-archive">
    <header><div><p class="eyebrow">人物设定</p><h3>本次改编人物卡</h3></div><el-tag effect="plain">{{ selectedRoles.length }} 人</el-tag></header>
    <div class="character-grid">
      <article v-for="(role,index) in selectedRoles" :key="role.draft_id || role.name" :style="{ '--role-color': roleColor(index) }">
        <el-avatar :size="64" :src="avatarUrl(role)">{{ role.name?.slice(0,1) }}</el-avatar>
        <div class="copy"><strong>{{ role.name }}</strong><small>{{ role.identity || '身份待补充' }}</small><p>{{ role.speech_style || '未设置表达特点' }}</p></div>
        <div class="voice-editor">
          <el-select :model-value="voiceIdForRole(role)" filterable placeholder="选择音色" @update:model-value="changeVoice(role,$event)">
            <el-option-group v-for="group in voiceGroups" :key="group.id" :label="group.label">
              <el-option v-for="voice in group.voices" :key="voice.id" :label="voice.name" :value="voice.id" :disabled="voiceUsedByOtherRole(voice.id,role)">
                <span>{{ voice.name }}</span>
                <button class="option-preview" type="button" :disabled="!voice.reference_path" :title="voice.reference_path?'试听音色':'暂无试听样音'" @mousedown.stop @click.stop="togglePreview(voice)"><el-icon><component :is="previewingId===voice.id?VideoPause:VideoPlay" /></el-icon></button>
              </el-option>
            </el-option-group>
          </el-select>
          <button v-if="voiceById(voiceIdForRole(role))?.reference_path" class="selected-preview" type="button" @click="togglePreview(voiceById(voiceIdForRole(role)))"><el-icon><component :is="previewingId===voiceIdForRole(role)?VideoPause:VideoPlay" /></el-icon>{{ previewingId===voiceIdForRole(role)?'停止试听':`试听 ${voiceName(voiceIdForRole(role))}` }}</button>
          <span v-else>{{ voiceName(voiceIdForRole(role)) }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { fetchTTSProviders } from '../../api/provider'
import { fetchVoicesByTTS, getVoiceAudioUrl } from '../../api/voice'
import { getRoleAvatarUrl } from '../../api/drama'
import { getRolesByProject, updateRole } from '../../api/role'

const props = defineProps({ roles:{type:Array,default:()=>[]}, sessionId:String, projectId:Number })
const emit=defineEmits(['voice-changed'])
const voices = ref([])
const providers = ref([])
const projectRoles = ref([])
const selectedVoiceMap = reactive({})
const previewingId = ref(null)
const voicePlayer = new Audio()
const selectedRoles = computed(()=>props.roles.filter(role=>role.selected!==false))
onMounted(async()=>{
  providers.value=(await fetchTTSProviders())||[]
  voices.value=(await Promise.all(providers.value.filter(item=>item.status!==0).map(item=>fetchVoicesByTTS(item.id)))).flat()
  const roleResponse=props.projectId?await getRolesByProject(props.projectId):null
  projectRoles.value=roleResponse?.code===200?roleResponse.data||[]:[]
  projectRoles.value.forEach(role=>{if(role.default_voice_id)selectedVoiceMap[role.id]=role.default_voice_id})
})
onBeforeUnmount(()=>{voicePlayer.pause();voicePlayer.removeAttribute('src')})
function avatarUrl(role){return getRoleAvatarUrl(props.sessionId,role.avatar_path)}
function voiceById(id){return voices.value.find(item=>item.id===id)||null}
function voiceName(id){return voices.value.find(item=>item.id===id)?.name||'未绑定音色'}
const voiceGroups=computed(()=>providers.value.map(provider=>({id:provider.id,label:`${provider.name} · ${provider.model||provider.provider_type||'TTS'}`,voices:voices.value.filter(voice=>voice.tts_provider_id===provider.id)})).filter(group=>group.voices.length))
function projectRole(role){return projectRoles.value.find(item=>item.name===role.name)||null}
function voiceIdForRole(role){const persisted=projectRole(role);return(persisted&&selectedVoiceMap[persisted.id])||role.default_voice_id||null}
function voiceUsedByOtherRole(voiceId,role){return projectRoles.value.some(item=>item.name!==role.name&&selectedVoiceMap[item.id]===voiceId)}
async function changeVoice(role,voiceId){
  const persisted=projectRole(role)
  if(!persisted)return ElMessage.error('没有找到项目中的角色记录')
  if(voiceUsedByOtherRole(voiceId,role))return ElMessage.warning('这个音色已被其他人物使用')
  const previous=selectedVoiceMap[persisted.id]
  selectedVoiceMap[persisted.id]=voiceId
  try{
    const response=await updateRole(persisted.id,{name:persisted.name,project_id:props.projectId,default_voice_id:voiceId,role_importance:persisted.role_importance,tts_route:persisted.tts_route,edge_voice:persisted.edge_voice,avatar_path:persisted.avatar_path})
    if(response?.code!==200)throw new Error(response?.message||'音色更新失败')
    persisted.default_voice_id=voiceId
    emit('voice-changed',{roleId:persisted.id,voiceId})
    ElMessage.success(`已更新「${role.name}」音色；已有音频需要重新生成`)
  }catch(error){previous?selectedVoiceMap[persisted.id]=previous:delete selectedVoiceMap[persisted.id];ElMessage.error(error?.message||'音色更新失败')}
}
async function togglePreview(voice){if(!voice)return;if(previewingId.value===voice.id&&!voicePlayer.paused){voicePlayer.pause();previewingId.value=null;return}voicePlayer.pause();previewingId.value=voice.id;voicePlayer.src=getVoiceAudioUrl(voice.id,Date.now());voicePlayer.onended=()=>previewingId.value=null;try{await voicePlayer.play()}catch(error){previewingId.value=null;ElMessage.error(error?.message||'该音色暂时无法试听')}}
function roleColor(index){return ['#37c9c6','#8b7cf6','#ef7eb8','#f2a84b','#55a7ed','#70bd69'][index%6]}
</script>

<style scoped>
.character-archive{display:grid;gap:14px}.character-archive header{display:flex;align-items:center;justify-content:space-between}.character-archive h3,.eyebrow{margin:0}.eyebrow{color:var(--el-color-primary);font-size:11px}.character-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.character-grid article{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;padding:14px;border:1px solid color-mix(in srgb,var(--role-color) 42%,var(--el-border-color));border-top:4px solid var(--role-color);border-radius:14px;background:var(--el-bg-color);min-width:0}.character-grid .el-avatar{background:color-mix(in srgb,var(--role-color) 18%,var(--el-fill-color));border:2px solid color-mix(in srgb,var(--role-color) 54%,white)}.copy{min-width:0}.copy strong,.copy small{display:block}.copy small,.copy p,.voice-editor>span{color:var(--el-text-color-secondary)}.copy p{margin:6px 0 0;line-height:1.5}.voice-editor{grid-column:2;display:grid;grid-template-columns:minmax(0,240px) auto;align-items:center;justify-content:start;gap:8px;min-width:0;font-size:12px}.voice-editor .el-select{width:100%}.option-preview{float:right;display:inline-grid;place-items:center;width:24px;height:24px;margin-top:3px;border:0;border-radius:50%;color:var(--el-color-primary);background:var(--el-fill-color-light);cursor:pointer}.option-preview:disabled{cursor:not-allowed;opacity:.35}.selected-preview{display:flex;align-items:center;gap:5px;padding:0;border:0;color:var(--el-color-primary);background:none;cursor:pointer;white-space:nowrap}
@media(max-width:720px){.voice-editor{grid-column:1/-1;grid-template-columns:1fr}.selected-preview{justify-self:start}}
</style>
