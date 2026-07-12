<template>
  <section class="confirm-card" aria-labelledby="role-card-title">
    <header>
      <div><p class="eyebrow">需要确认</p><h3 id="role-card-title">角色草稿</h3></div>
      <DraftRevisionBar :revision="revision" />
    </header>
    <div class="card-actions">
      <span>先完成角色卡和音色，台本会按这些声线写作。</span>
      <el-button size="small" :icon="MagicStick" :disabled="!voices.length" @click="autoBind">自动匹配不同音色</el-button>
    </div>
    <div class="role-grid">
      <article v-for="(role,index) in editableRoles" :key="role.draft_id" class="role-item" :style="{ '--role-color': roleColor(index) }">
        <div class="avatar-cell">
          <el-avatar :size="58" :src="avatarUrl(role)">{{ role.name?.slice(0,1) }}</el-avatar>
          <label class="avatar-upload">
            {{ uploadingId === role.draft_id ? '上传中…' : '上传头像' }}
            <input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploadingId === role.draft_id" @change="uploadAvatar(role,$event)" />
          </label>
        </div>
        <el-checkbox v-model="role.selected" :aria-label="`选择角色 ${role.name}`" />
        <span class="role-copy">
          <strong>{{ role.name }}</strong>
          <small>{{ role.identity || '角色身份待补充' }}</small>
          <p>{{ role.speech_style || role.voice_type || '暂无表达特点' }}</p>
        </span>
        <div class="voice-picker">
          <el-select v-model="role.default_voice_id" filterable clearable placeholder="按模型来源选择音色">
            <el-option-group v-for="group in voiceGroups" :key="group.id" :label="group.label">
              <el-option v-for="voice in group.voices" :key="voice.id" :label="voice.name" :value="voice.id" :disabled="voiceUsedByOtherRole(voice.id, role.draft_id)">
                <span>{{ voice.name }}</span>
                <button class="option-preview" type="button" :disabled="!voice.reference_path" :title="!voice.reference_path?'该音色暂无样音':previewingId===voice.id?'停止试听':'试听音色'" @mousedown.stop @click.stop="toggleVoicePreview(voice)"><el-icon><component :is="previewingId===voice.id?VideoPause:VideoPlay" /></el-icon></button>
              </el-option>
            </el-option-group>
          </el-select>
          <button v-if="selectedVoice(role)?.reference_path" class="selected-preview" type="button" @click="toggleVoicePreview(selectedVoice(role))"><el-icon><component :is="previewingId===role.default_voice_id?VideoPause:VideoPlay" /></el-icon>{{ previewingId===role.default_voice_id?'停止试听':`试听「${selectedVoice(role).name}」` }}</button>
          <small v-else-if="selectedVoice(role)" class="no-preview">该音色暂无试听样音</small>
          <small>{{ role.voice_type || 'AI 声线建议' }}</small>
        </div>
      </article>
    </div>
    <footer>
      <el-button type="primary" :loading="loading" :disabled="!canConfirm" @click="$emit('confirm', editableRoles)">
        {{ confirmLabel || `确认 ${selectedCount} 个角色并生成剧本` }}
      </el-button>
    </footer>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import DraftRevisionBar from './DraftRevisionBar.vue'
import { fetchTTSProviders } from '../../api/provider'
import { fetchVoicesByTTS, getVoiceAudioUrl } from '../../api/voice'
import { getRoleAvatarUrl, uploadRoleAvatar } from '../../api/drama'

const props = defineProps({ roles: { type: Array, default: () => [] }, revision: Number, loading: Boolean, confirmLabel: String, sessionId: String })
const emit = defineEmits(['confirm','update:roles'])
const editableRoles = ref([])
const providers = ref([])
const voices = ref([])
const uploadingId = ref('')
const previewingId = ref(null)
const voicePlayer = new Audio()
watch(() => props.roles, (value) => {
  editableRoles.value = JSON.parse(JSON.stringify(value || []))
}, { immediate: true, deep: true })
watch(editableRoles, value => emit('update:roles', JSON.parse(JSON.stringify(value))), { deep:true })
const selectedCount = computed(() => editableRoles.value.filter((item) => item.selected !== false).length)
const selectedRoles = computed(() => editableRoles.value.filter((item) => item.selected !== false))
const canConfirm = computed(() => selectedCount.value > 0 && selectedRoles.value.every(role => role.default_voice_id))
const voiceGroups = computed(() => providers.value.map(provider => ({
  id: provider.id,
  label: `${provider.name} · ${provider.model || provider.provider_type || 'TTS'}`,
  voices: voices.value.filter(voice => voice.tts_provider_id === provider.id),
})).filter(group => group.voices.length))

onMounted(loadVoices)
onBeforeUnmount(() => { voicePlayer.pause();voicePlayer.removeAttribute('src');previewingId.value=null })

async function loadVoices() {
  providers.value = (await fetchTTSProviders()) || []
  const lists = await Promise.all(providers.value.filter(item => item.status !== 0).map(item => fetchVoicesByTTS(item.id)))
  voices.value = lists.flat()
}
function roleColor(index) { return ['#37c9c6','#8b7cf6','#ef7eb8','#f2a84b','#55a7ed','#70bd69'][index%6] }
function avatarUrl(role) { return getRoleAvatarUrl(props.sessionId, role.avatar_path) }
function voiceUsedByOtherRole(voiceId, draftId) { return selectedRoles.value.some(role => role.draft_id !== draftId && role.default_voice_id === voiceId) }
function selectedVoice(role){return voices.value.find(voice=>voice.id===role.default_voice_id)||null}
async function toggleVoicePreview(voice){
  if(!voice)return
  if(previewingId.value===voice.id&&!voicePlayer.paused){voicePlayer.pause();previewingId.value=null;return}
  voicePlayer.pause();previewingId.value=voice.id;voicePlayer.src=getVoiceAudioUrl(voice.id,Date.now())
  voicePlayer.onended=()=>{previewingId.value=null};voicePlayer.onpause=()=>{if(voicePlayer.currentTime>0&&voicePlayer.currentTime<voicePlayer.duration)previewingId.value=null}
  try{await voicePlayer.play()}catch(error){previewingId.value=null;ElMessage.error(error?.message||'该音色暂时无法试听')}
}
function tagsFor(voice) { return `${voice.name},${voice.description || ''}`.toLowerCase() }
function scoreVoice(role, voice) {
  const hint = `${role.voice_type || ''},${role.identity || ''},${role.speech_style || ''}`.toLowerCase()
  const tags = tagsFor(voice)
  return ['男','女','少年','青年','儿童','中年','老年','温柔','冷淡','活泼','沉稳','旁白'].reduce((score,key)=>score+(hint.includes(key)&&tags.includes(key)?2:0),0)
}
function autoBind() {
  const unused = [...voices.value]
  selectedRoles.value.forEach(role => {
    unused.sort((a,b)=>scoreVoice(role,b)-scoreVoice(role,a))
    const voice = unused.shift()
    role.default_voice_id = voice?.id || null
  })
  ElMessage.success('已按人物设定匹配不同来源的独立音色')
}
async function uploadAvatar(role,event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !props.sessionId) return
  uploadingId.value = role.draft_id
  try {
    const response = await uploadRoleAvatar(props.sessionId,file)
    if (response?.code !== 200) throw new Error(response?.message || '上传失败')
    role.avatar_path = response.data.avatar_path
    ElMessage.success(`已绑定「${role.name}」头像`)
  } catch(error) { ElMessage.error(error?.message || '头像上传失败') }
  finally { uploadingId.value = '' }
}
</script>

<style scoped>
.confirm-card { display:grid; gap:14px; padding:16px; border:1px solid color-mix(in srgb,var(--el-color-primary) 35%,var(--el-border-color)); border-radius:12px; background:color-mix(in srgb,var(--el-color-primary) 5%,var(--el-bg-color)); }
.confirm-card header,.confirm-card footer { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.confirm-card h3,.eyebrow { margin:0; }
.eyebrow { color:var(--el-color-primary); font-size:12px; }
.card-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--el-text-color-secondary);font-size:12px}.role-grid { display:grid; gap:10px; }
.role-item { display:grid; grid-template-columns:70px auto minmax(0,1fr) minmax(210px,260px); align-items:center; gap:10px; padding:12px; border:1px solid color-mix(in srgb,var(--role-color) 40%,var(--el-border-color-lighter)); border-left:4px solid var(--role-color); border-radius:12px; background:var(--el-bg-color); }
.avatar-cell{display:grid;justify-items:center;gap:5px}.avatar-cell .el-avatar{border:2px solid color-mix(in srgb,var(--role-color) 55%,white);background:color-mix(in srgb,var(--role-color) 16%,var(--el-fill-color))}.avatar-upload{color:var(--el-color-primary);font-size:10px;cursor:pointer}.avatar-upload input{display:none}.role-copy{min-width:0}
.role-item strong,.role-item small { display:block; }
.role-item small,.role-item p { color:var(--el-text-color-secondary); }
.role-item p { margin:4px 0 0; line-height:1.5; }
.voice-picker .el-select{width:100%}.voice-picker small{margin-top:5px}.option-preview{float:right;display:inline-grid;place-items:center;width:24px;height:24px;margin-top:3px;border:0;border-radius:50%;color:var(--el-color-primary);background:var(--el-fill-color-light);cursor:pointer}.option-preview:disabled{cursor:not-allowed;opacity:.35}.selected-preview{display:flex;align-items:center;gap:5px;margin-top:6px;padding:0;border:0;color:var(--el-color-primary);background:none;cursor:pointer;font-size:11px}.voice-picker .no-preview{color:var(--el-text-color-placeholder);font-size:10px}
.confirm-card footer { justify-content:flex-end; }
@media(max-width:760px){.role-item{grid-template-columns:62px auto minmax(0,1fr)}.voice-picker{grid-column:1/-1}.card-actions{align-items:flex-start;flex-direction:column}}
</style>
