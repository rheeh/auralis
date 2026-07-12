<template>
  <section class="production-script">
    <details class="source-fold">
      <summary><span>小说原文</span><small>{{ sourceText?.length || 0 }} 字 · 点击展开核对</small></summary>
      <div>{{ sourceText || '本次会话没有保存原文。' }}</div>
    </details>

    <header class="production-head">
      <div><p class="eyebrow">逐句制作时间线</p><h2>台本、音色与音频</h2></div>
      <div class="head-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button :icon="MagicStick" :loading="autoBinding" @click="autoBind">AI 自动配音色</el-button>
        <el-button :icon="isPlaying ? VideoPause : VideoPlay" :disabled="!playableLines.length" @click="togglePlayAll">
          {{ isPlaying ? '暂停' : '一键播放' }}
        </el-button>
        <el-button type="primary" :icon="Headset" :disabled="!voiceReady" :loading="generating" @click="generateAudio">
          {{ bulkGenerateLabel }}
        </el-button>
      </div>
    </header>

    <div class="voice-status" :class="{ ready: voiceReady }">
      <div><strong>{{ voiceReady ? '人物声线已就绪' : '请完成独立音色绑定' }}</strong><span>{{ voiceStatusText }}</span></div>
      <div class="status-metrics"><el-tag effect="plain">人物 {{ speakableRoles.length }}</el-tag><el-tag effect="plain" :type="voiceReady?'success':'warning'">音色 {{ uniqueVoiceCount }}/{{ speakableRoles.length }}</el-tag><el-tag effect="plain" type="success">音频 {{ completedAudioCount }}/{{ speakableLines.length }}</el-tag></div>
    </div>

    <div v-if="scenes.length" class="scene-list">
      <section v-for="scene in scenes" :key="scene.title" class="scene-block">
        <header class="scene-head"><div><span>场景</span><strong>{{ scene.title }}</strong></div><el-tag size="small" effect="plain">{{ scene.lines.length }} 句</el-tag></header>
        <div class="timeline">
          <article v-for="line in scene.lines" :key="line.id" class="production-line" :class="[{playing:playingLineId===line.id,expanded:expandedLineIds.has(line.id),clickable:isSpeakable(line)},`track-${line.track||line.line_type}`]" :style="{ '--role-color': roleColor(line.role_id) }" @click="toggleLineEditor(line,$event)">
            <div class="timeline-dot"><span>{{ line.line_order }}</span></div>
            <el-avatar v-if="isSpeakable(line)" :size="52" :src="roleAvatar(line.role_id)">{{ roleName(line.role_id).slice(0,1) }}</el-avatar>
            <div v-else class="material-icon"><el-icon><Headset /></el-icon></div>
            <div class="line-main">
              <div class="line-meta"><strong>{{ roleName(line.role_id) }}</strong><el-tag size="small" effect="plain">{{ trackLabel(line) }}</el-tag><span v-if="activeVariant(line)" class="active-version">当前采用 {{ activeVariant(line).label }}</span><span v-if="isSpeakable(line)" class="line-expand-state">{{ expandedLineIds.has(line.id)?'收起':'展开' }}</span></div>
              <p>{{ line.text_content }}</p>
              <div v-if="isSpeakable(line)" class="line-annotations">
                <el-tag size="small" :type="line.emotion_id?undefined:'warning'" effect="plain">情绪 · {{ emotionName(line.emotion_id) }}</el-tag>
                <el-tag size="small" :type="line.strength_id?undefined:'warning'" effect="plain">强度 · {{ strengthName(line.strength_id) }}</el-tag>
                <span :class="{missing:!line.production_note}">{{ line.production_note || '表演提示待补充' }}</span>
              </div>
              <div v-if="isSpeakable(line)" class="audio-strip">
                <button class="round-play" :disabled="!hasAudio(line)" @click="playLine(line)"><el-icon><component :is="playingLineId===line.id&&isPlaying?VideoPause:VideoPlay" /></el-icon></button>
                <span class="time">{{ playingLineId===line.id ? formatTime(currentTime) : '00:00' }}</span>
                <div class="waveform" :class="{active:playingLineId===line.id}"><i v-for="i in 44" :key="i" :style="{height:`${waveHeight(line.id,i)}%`}" /></div>
                <span class="time">{{ playingLineId===line.id ? formatTime(duration) : audioVersionLabel(line) }}</span>
              </div>
              <div v-if="isSpeakable(line)" class="line-tools">
                <span class="guidance-label">声音指导</span>
                <el-input v-model="promptMap[line.id]" size="small" placeholder="单句声音提示词：如更克制、语速稍慢、压低声音……" clearable />
                <el-button size="small" :type="hasAudio(line)?'default':'primary'" :loading="regeneratingId===line.id" @click="regenerate(line)">{{ hasAudio(line) ? '按提示词重新生成本句' : '生成本句音频' }}</el-button>
              </div>
              <div v-if="isSpeakable(line)&&expandedLineIds.has(line.id)" class="line-editor" @click.stop>
                <div class="metadata-editor">
                  <label class="text-field"><span>纯净朗读文本</span><el-input v-model="editMap[line.id].text_content" type="textarea" :rows="2" resize="vertical" /></label>
                  <label><span>情绪</span><el-select v-model="editMap[line.id].emotion_id" clearable><el-option v-for="item in emotions" :key="item.id" :label="item.name" :value="item.id" /></el-select></label>
                  <label><span>强度</span><el-select v-model="editMap[line.id].strength_id" clearable><el-option v-for="item in strengths" :key="item.id" :label="item.name" :value="item.id" /></el-select></label>
                  <label class="note-field"><span>声音指导（按模型能力发送到 TTS）</span><el-input v-model="editMap[line.id].production_note" placeholder="语速、重音、停顿、语气等" /></label>
                  <el-button type="primary" plain :loading="savingId===line.id" @click="saveLine(line)">保存台词信息</el-button>
                </div>
                <div v-if="line.audio_events?.length" class="audio-events">
                  <strong>声音事件</strong>
                  <span v-for="(event,index) in line.audio_events" :key="index"><el-tag size="small" effect="plain">{{ event.type }}</el-tag>{{ event.timing }} · {{ event.content }} · {{ event.volume_db }}</span>
                </div>
                <div v-if="hasAudio(line)" class="source-audio-label"><strong>从生成原音创建新版本</strong><small>下方变速只预听和处理原音；保存后会自动成为顶部播放器的当前版本。</small></div>
                <WaveCellPro v-if="hasAudio(line)" :key="`${line.id}-${audioVersion}`" :src="originalLineAudioUrl(line.id)" variant-mode @confirm="payload=>processLine(line,payload)" />
                <div v-if="line.audio_variants?.length" class="variant-list">
                  <header><strong>处理版本</strong><small>每个版本都从原始音频生成，互不覆盖</small></header>
                  <div v-for="variant in line.audio_variants" :key="variant.id" class="variant-item" :class="{active:line.active_audio_variant_id===variant.id}">
                    <span><strong>{{ variant.label }} <el-tag v-if="line.active_audio_variant_id===variant.id" size="small" type="success">当前采用</el-tag></strong><small>{{ variant.region_action==='speed'?`局部 ${variant.start_ms/1000}–${variant.end_ms/1000}s`:`整段 ${variant.speed}x` }} · {{ variant.volume }}x 音量</small></span>
                    <audio controls preload="none" :src="getAudioVariantUrl(line.id,variant.id,audioVersion)" />
                    <el-button v-if="line.active_audio_variant_id!==variant.id" size="small" plain type="primary" @click="activateVariant(line,variant)">设为当前</el-button>
                    <el-button size="small" text type="danger" @click="removeVariant(line,variant)">删除</el-button>
                  </div>
                </div>
                <p v-else class="editor-empty">还没有处理版本；可调整整段速度，或选择局部区间后只改变其中一段。</p>
              </div>
              <small v-if="!isSpeakable(line)">{{ line.sound_prompt || line.text_content || '缺少声音提示，请让 AI 补充。' }}</small>
            </div>
          </article>
        </div>
      </section>
    </div>
    <el-empty v-else description="台本写入后会在这里逐句制作" />

    <footer v-if="playableLines.length" class="master-player">
      <button @click="playPrevious"><el-icon><ArrowLeftBold /></el-icon></button>
      <button class="master-play" @click="togglePlayAll"><el-icon><component :is="isPlaying?VideoPause:VideoPlay" /></el-icon></button>
      <button @click="playNext"><el-icon><ArrowRightBold /></el-icon></button>
      <div class="now-playing"><strong>{{ currentLine ? roleName(currentLine.role_id) : '整章连播' }}</strong><span>{{ currentLine?.text_content || '点击播放，从第一句有音频的台词开始。' }}</span></div>
      <span>{{ formatTime(currentTime) }}</span><input type="range" min="0" :max="duration||0" :value="currentTime" @input="seek" /><span>{{ formatTime(duration) }}</span>
    </footer>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeftBold, ArrowRightBold, Headset, MagicStick, Refresh, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { addSmartRoleAndVoice } from '../../api/chapter'
import { fetchSessionAudioTasks, generateSessionAudio, regenerateLineAudio } from '../../api/drama'
import { activateAudioVariant, createAudioVariant, deleteAudioVariant, getAudioVariantUrl, getLinesByChapter, getLineAudioUrl, updateLine } from '../../api/line'
import { getRolesByProject } from '../../api/role'
import { fetchVoicesByTTS } from '../../api/voice'
import { fetchTTSProviders } from '../../api/provider'
import { fetchAllEmotions, fetchAllStrengths } from '../../api/enums'
import { getRoleAvatarUrl } from '../../api/drama'
import WaveCellPro from '../WaveCellPro.vue'

const props=defineProps({sessionId:{type:String,required:true},projectId:{type:Number,required:true},chapterId:{type:Number,required:true},ttsProviderId:Number,sourceText:String,voiceRevision:{type:Number,default:0}})
const roles=ref([]),voices=ref([]),providers=ref([]),lines=ref([])
const emotions=ref([]),strengths=ref([])
const roleVoiceMap=reactive({}),audioSummary=reactive({total:0,completed:0,counts:{},tasks:[]}),promptMap=reactive({}),editMap=reactive({})
const expandedLineIds=reactive(new Set())
const loading=ref(false),autoBinding=ref(false),generating=ref(false),voiceChanged=ref(props.voiceRevision>0),regeneratingId=ref(null),savingId=ref(null)
const playingLineId=ref(null),isPlaying=ref(false),currentTime=ref(0),duration=ref(0),playAllActive=ref(false),audioVersion=ref(Date.now())
const player=new Audio();let pollTimer=null
defineExpose({ togglePlayAll, generateAudio })

const speakableLines=computed(()=>lines.value.filter(isSpeakable))
const speakableRoleIds=computed(()=>[...new Set(speakableLines.value.map(line=>line.role_id).filter(Boolean))])
const speakableRoles=computed(()=>speakableRoleIds.value.map(id=>roles.value.find(role=>role.id===id)).filter(Boolean))
const selectedVoiceIds=computed(()=>speakableRoleIds.value.map(id=>roleVoiceMap[id]).filter(Boolean))
const uniqueVoiceCount=computed(()=>new Set(selectedVoiceIds.value).size)
const voiceReady=computed(()=>speakableRoles.value.length>0&&selectedVoiceIds.value.length===speakableRoles.value.length&&uniqueVoiceCount.value===speakableRoles.value.length)
const playableLines=computed(()=>speakableLines.value.filter(hasAudio))
const completedAudioCount=computed(()=>playableLines.value.length)
const bulkGenerateLabel=computed(()=>voiceChanged.value?'按新音色重新生成':completedAudioCount.value?'生成缺失试听':'生成全部试听')
const currentLine=computed(()=>lines.value.find(line=>line.id===playingLineId.value)||null)
const voiceStatusText=computed(()=>!speakableRoles.value.length?'当前台本还没有可朗读人物。':voices.value.length<speakableRoles.value.length?`全部来源共 ${voices.value.length} 个音色，至少需要 ${speakableRoles.value.length} 个。`:!voiceReady.value?'每个人物必须绑定不同音色；下拉框已按安装模型来源分组。':'可以生成或连续播放；修改音色后需要重新生成。')
const scenes=computed(()=>{const groups=new Map();for(const line of lines.value){const title=line.scene_title||'未命名场景';if(!groups.has(title))groups.set(title,[]);groups.get(title).push(line)}return[...groups.entries()].map(([title,sceneLines])=>({title,lines:sceneLines}))})

onMounted(()=>{bindPlayer();loadAll()});watch(()=>[props.sessionId,props.chapterId],loadAll);onBeforeUnmount(()=>{clearTimeout(pollTimer);player.pause();unbindPlayer()})
watch(()=>props.voiceRevision,(value,previous)=>{if(value>previous)voiceChanged.value=true})
async function loadAll(){if(!props.chapterId)return;loading.value=true;try{providers.value=(await fetchTTSProviders())?.filter(item=>item.status!==0)||[];const [roleResponse,lineResponse,voiceLists,taskResponse,emotionList,strengthList]=await Promise.all([getRolesByProject(props.projectId),getLinesByChapter(props.chapterId),Promise.all(providers.value.map(item=>fetchVoicesByTTS(item.id))),fetchSessionAudioTasks(props.sessionId),fetchAllEmotions(),fetchAllStrengths()]);roles.value=roleResponse?.code===200?roleResponse.data||[]:[];lines.value=lineResponse?.code===200?lineResponse.data||[]:[];voices.value=voiceLists.flat();emotions.value=emotionList||[];strengths.value=strengthList||[];Object.keys(roleVoiceMap).forEach(key=>delete roleVoiceMap[key]);roles.value.forEach(role=>{if(role.default_voice_id)roleVoiceMap[role.id]=role.default_voice_id});lines.value.forEach(line=>{promptMap[line.id]=line.production_note||'';editMap[line.id]={text_content:line.text_content||'',emotion_id:line.emotion_id||null,strength_id:line.strength_id||null,production_note:line.production_note||''}});if(taskResponse?.code===200)Object.assign(audioSummary,taskResponse.data);schedulePoll()}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'读取制作数据失败')}finally{loading.value=false}}
function isSpeakable(line){return line.should_speak!==0&&!['sfx','bgm'].includes(line.track)&&!['sfx','bgm'].includes(line.line_type)}
function trackLabel(line){return{voice:'人物',narration:'旁白',sfx:'音效',bgm:'BGM'}[line.track||line.line_type]||'台词'}
function roleName(id){return roles.value.find(role=>role.id===id)?.name||'未知角色'}
function roleAvatar(id){const role=roles.value.find(item=>item.id===id);return getRoleAvatarUrl(props.sessionId,role?.avatar_path)}
function roleColor(id){const index=Math.max(0,roles.value.findIndex(role=>role.id===id));return['#37c9c6','#8b7cf6','#ef7eb8','#f2a84b','#55a7ed','#70bd69'][index%6]}
function taskForLine(id){return(audioSummary.tasks||[]).find(task=>task.line_id===id)}function hasAudio(line){const task=taskForLine(line.id);return line.status==='done'&&(!task||task.status==='done')}
function lineAudioUrl(id){return getLineAudioUrl(id,audioVersion.value)}function originalLineAudioUrl(id){return getLineAudioUrl(id,audioVersion.value,true)}function waveHeight(id,i){return 22+((Number(id||1)*13+i*17)%70)}
function emotionName(id){return emotions.value.find(item=>item.id===id)?.name||'待补'}function strengthName(id){return strengths.value.find(item=>item.id===id)?.name||'待补'}
function activeVariant(line){return(line.audio_variants||[]).find(item=>item.id===line.active_audio_variant_id)||null}function audioVersionLabel(line){return !hasAudio(line)?'待生成':activeVariant(line)?`${activeVariant(line).speed}×`:'原音'}
function toggleLineEditor(line,event){if(!isSpeakable(line))return;if(event.target.closest('button,input,textarea,select,a,audio,.el-input,.el-select,.line-tools,[role="slider"]'))return;expandedLineIds.has(line.id)?expandedLineIds.delete(line.id):expandedLineIds.add(line.id)}
async function autoBind(){autoBinding.value=true;try{const response=await addSmartRoleAndVoice(props.projectId,props.chapterId);if(response?.code!==200)throw new Error(response?.message||'自动分配失败');voiceChanged.value=true;await loadAll();ElMessage.success('已从全部模型来源为人物分配不同音色')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'自动分配失败')}finally{autoBinding.value=false}}
async function generateAudio(){if(!voiceReady.value)return ElMessage.warning('请先为每个人物绑定不同音色');generating.value=true;try{const response=await generateSessionAudio(props.sessionId,voiceChanged.value);if(response?.code!==200)throw new Error(response?.message||'创建任务失败');voiceChanged.value=false;await loadAll();ElMessage.success(response.data?.created?`已加入 ${response.data.created} 条任务`:'没有新的待生成台词')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'生成失败')}finally{generating.value=false}}
async function regenerate(line){regeneratingId.value=line.id;try{const response=await regenerateLineAudio(props.sessionId,line.id,promptMap[line.id]||'');if(response?.code!==200)throw new Error(response?.message||'重新生成失败');audioVersion.value=Date.now();await loadAll();ElMessage.success('已按单句提示词加入生成队列')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'重新生成失败')}finally{regeneratingId.value=null}}
async function saveLine(line){const edit=editMap[line.id];if(!edit?.text_content?.trim())return ElMessage.warning('朗读文本不能为空');if(/[()（）\[\]【】]/.test(edit.text_content))return ElMessage.warning('朗读文本不能包含括号提示，请把提示写到后期说明');savingId.value=line.id;try{const changed=edit.text_content.trim()!==line.text_content;const response=await updateLine(line.id,{chapter_id:props.chapterId,text_content:edit.text_content.trim(),emotion_id:edit.emotion_id,strength_id:edit.strength_id,production_note:edit.production_note?.trim()||null,...(changed?{status:'pending',is_done:0}:{})});if(response?.code!==200)throw new Error(response?.message||'保存失败');await loadAll();ElMessage.success(changed?'台词已保存，请重新生成本句音频':'台词信息已保存')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'保存失败')}finally{savingId.value=null}}
async function processLine(line,payload){try{const response=await createAudioVariant(line.id,payload);if(response?.code!==200)throw new Error(response?.message||'音频版本创建失败');audioVersion.value=Date.now();await loadAll();ElMessage.success('已从原音频保存一个独立处理版本')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'音频版本创建失败')}}
async function activateVariant(line,variant){try{const response=await activateAudioVariant(line.id,variant.id);if(response?.code!==200)throw new Error(response?.message||'切换失败');audioVersion.value=Date.now();await loadAll();ElMessage.success('顶部播放器和导出已切换到这个版本')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'切换失败')}}
async function removeVariant(line,variant){try{const response=await deleteAudioVariant(line.id,variant.id);if(response?.code!==200)throw new Error(response?.message||'删除失败');audioVersion.value=Date.now();await loadAll();ElMessage.success('音频版本已删除')}catch(error){ElMessage.error(error?.response?.data?.message||error?.message||'删除失败')}}
function bindPlayer(){player.addEventListener('play',onPlay);player.addEventListener('pause',onPause);player.addEventListener('timeupdate',onTime);player.addEventListener('loadedmetadata',onMeta);player.addEventListener('ended',onEnded)}
function unbindPlayer(){player.removeEventListener('play',onPlay);player.removeEventListener('pause',onPause);player.removeEventListener('timeupdate',onTime);player.removeEventListener('loadedmetadata',onMeta);player.removeEventListener('ended',onEnded)}
function onPlay(){isPlaying.value=true}function onPause(){isPlaying.value=false}function onTime(){currentTime.value=player.currentTime||0}function onMeta(){duration.value=Number.isFinite(player.duration)?player.duration:0}
function onEnded(){if(playAllActive.value)playNext();else{isPlaying.value=false;playingLineId.value=null}}
function playLine(line,keepAll=false){if(!hasAudio(line))return;if(playingLineId.value===line.id){isPlaying.value?player.pause():player.play();return}playAllActive.value=keepAll;playingLineId.value=line.id;player.src=lineAudioUrl(line.id);player.play().catch(()=>ElMessage.error('音频播放失败'))}
function togglePlayAll(){if(isPlaying.value){player.pause();return}if(playingLineId.value&&player.src){playAllActive.value=true;player.play();return}const first=playableLines.value[0];if(first)playLine(first,true)}
function currentPlayableIndex(){return playableLines.value.findIndex(line=>line.id===playingLineId.value)}
function playNext(){const list=playableLines.value;if(!list.length)return;const index=currentPlayableIndex();const next=list[index+1];if(next)playLine(next,true);else{playAllActive.value=false;playingLineId.value=null;isPlaying.value=false;currentTime.value=0}}
function playPrevious(){const list=playableLines.value;if(!list.length)return;const index=currentPlayableIndex();playLine(list[Math.max(0,index-1)],playAllActive.value)}
function seek(event){player.currentTime=Number(event.target.value)||0}function formatTime(value){const total=Math.max(0,Math.floor(value||0));return`${String(Math.floor(total/60)).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`}
function schedulePoll(){clearTimeout(pollTimer);if((audioSummary.tasks||[]).some(task=>['queued','processing'].includes(task.status)))pollTimer=setTimeout(loadAll,1800)}
</script>

<style scoped>
.production-script{display:grid;gap:14px;padding-bottom:72px;min-width:0}.source-fold{border:1px solid var(--el-border-color-lighter);border-radius:10px;background:var(--el-fill-color-extra-light)}.source-fold summary{display:flex;justify-content:space-between;gap:12px;padding:10px 12px;cursor:pointer}.source-fold summary small{color:var(--el-text-color-secondary)}.source-fold>div{max-height:240px;overflow:auto;padding:12px;border-top:1px solid var(--el-border-color-lighter);white-space:pre-wrap;line-height:1.7}.production-head,.voice-status,.scene-head,.line-meta,.head-actions,.status-metrics{display:flex;align-items:center;gap:10px}.production-head,.voice-status,.scene-head{justify-content:space-between}.production-head{flex-wrap:wrap}.production-head h2,.production-head p,.eyebrow{margin:0}.eyebrow{color:var(--el-color-primary);font-size:11px}.head-actions,.status-metrics{flex-wrap:wrap}.voice-status{padding:10px 12px;border:1px solid color-mix(in srgb,var(--el-color-warning) 38%,var(--el-border-color));border-radius:11px;background:color-mix(in srgb,var(--el-color-warning) 6%,var(--el-bg-color))}.voice-status.ready{border-color:color-mix(in srgb,var(--el-color-success) 36%,var(--el-border-color));background:color-mix(in srgb,var(--el-color-success) 5%,var(--el-bg-color))}.voice-status strong,.voice-status span{display:block}.voice-status span{margin-top:3px;color:var(--el-text-color-secondary);font-size:11px}.scene-list{display:grid;gap:14px;min-width:0}.scene-block{border:1px solid var(--el-border-color-lighter);border-radius:13px;background:var(--el-bg-color);overflow:hidden}.scene-head{padding:10px 14px;background:var(--el-fill-color-light)}.scene-head div{display:flex;align-items:center;gap:8px}.scene-head span{color:var(--el-text-color-secondary);font-size:11px}.timeline{position:relative;padding:8px 10px 8px 34px}.timeline:before{content:"";position:absolute;left:20px;top:12px;bottom:12px;border-left:1px dashed color-mix(in srgb,var(--el-color-primary) 45%,var(--el-border-color))}.production-line{--role-color:#37c9c6;position:relative;display:grid;grid-template-columns:52px minmax(0,1fr);gap:12px;align-items:start;margin:8px 0;padding:12px;border:1px solid color-mix(in srgb,var(--role-color) 28%,var(--el-border-color-lighter));border-left:4px solid var(--role-color);border-radius:12px;background:var(--el-bg-color);box-shadow:0 5px 15px rgba(31,38,67,.05);min-width:0}.production-line.playing{box-shadow:0 0 0 2px color-mix(in srgb,var(--role-color) 45%,transparent),0 10px 24px rgba(31,38,67,.1)}.timeline-dot{position:absolute;left:-30px;top:18px;z-index:1}.timeline-dot span{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;color:white;background:var(--role-color);font-size:10px}.production-line>.el-avatar{border:2px solid color-mix(in srgb,var(--role-color) 55%,white);background:color-mix(in srgb,var(--role-color) 17%,var(--el-fill-color))}.material-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:50%;background:var(--el-fill-color)}.line-main{min-width:0}.line-meta{flex-wrap:wrap}.line-meta span{color:var(--el-text-color-secondary);font-size:11px}.line-main p{margin:7px 0;line-height:1.6}.line-main>small{color:var(--el-text-color-secondary)}.audio-strip{display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--el-border-color-lighter);border-radius:9px;background:var(--el-fill-color-extra-light);min-width:0}.round-play,.master-player button{display:grid;place-items:center;border:0;border-radius:50%;cursor:pointer}.round-play{width:28px;height:28px;flex:0 0 28px}.round-play:disabled{cursor:not-allowed;opacity:.45}.time{color:var(--el-text-color-secondary);font-size:10px}.waveform{display:flex;align-items:center;gap:2px;flex:1;height:26px;min-width:40px;overflow:hidden}.waveform i{width:2px;flex:0 0 2px;max-height:100%;border-radius:2px;background:color-mix(in srgb,var(--role-color) 72%,#fff)}.waveform.active i{background:var(--role-color)}.line-tools{display:flex;gap:8px;margin-top:8px}.line-tools .el-input{flex:1}.voice-cell{grid-column:2;display:grid;grid-template-columns:minmax(180px,240px) minmax(0,1fr);align-items:center;gap:8px}.voice-cell .el-select{width:100%}.voice-cell small{display:block;color:var(--el-text-color-secondary)}.track-sfx,.track-bgm{--role-color:#91a0ad}.master-player{position:sticky;z-index:5;bottom:-14px;display:grid;grid-template-columns:34px 42px 34px minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:9px 12px;border:1px solid var(--el-border-color);border-radius:13px 13px 0 0;background:color-mix(in srgb,var(--el-bg-color) 94%,transparent);box-shadow:0 -8px 28px rgba(28,34,64,.12);backdrop-filter:blur(14px);min-width:0}.master-player button{width:34px;height:34px;background:var(--el-fill-color)}.master-player .master-play{width:42px;height:42px;color:white;background:linear-gradient(135deg,#37c9c6,#7d70e8)}.now-playing{min-width:0}.now-playing strong,.now-playing span{display:block}.now-playing span{overflow:hidden;color:var(--el-text-color-secondary);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.master-player input{grid-column:1/-1;width:100%;accent-color:#37c9c6}@media(max-width:760px){.production-head,.voice-status{align-items:flex-start;flex-direction:column}.production-line{grid-template-columns:44px minmax(0,1fr)}.line-tools{flex-direction:column}.voice-cell{grid-template-columns:1fr}.head-actions{width:100%}.master-player{grid-template-columns:32px 40px 32px minmax(0,1fr)}.master-player>span{display:none}}
.line-editor{margin-top:9px;padding-top:10px;border-top:1px solid var(--el-border-color-lighter);cursor:default}.production-line.clickable{cursor:pointer}.production-line.clickable:hover{border-color:color-mix(in srgb,var(--role-color) 58%,var(--el-border-color));box-shadow:0 8px 20px rgba(31,38,67,.08)}.production-line.expanded{border-color:color-mix(in srgb,var(--role-color) 60%,var(--el-border-color));box-shadow:0 9px 24px rgba(31,38,67,.1)}.line-expand-state{margin-left:auto;color:var(--el-color-primary)!important;font-size:10px!important}
.metadata-editor{display:grid;grid-template-columns:minmax(120px,1fr) minmax(120px,1fr) auto;gap:9px;padding:10px}.metadata-editor label{display:grid;gap:5px}.metadata-editor label>span{color:var(--el-text-color-secondary);font-size:11px}.metadata-editor .text-field,.metadata-editor .note-field{grid-column:1/-1}.metadata-editor>.el-button{align-self:end}.audio-events{display:grid;gap:6px;margin:0 10px 10px;padding:9px;border-radius:8px;background:var(--el-bg-color)}.audio-events>span{display:flex;align-items:center;gap:7px;color:var(--el-text-color-secondary);font-size:11px}.line-editor .wavecell{margin:0 10px 10px}.editor-empty{margin:0 10px 10px!important;padding:10px;border-radius:8px;color:var(--el-text-color-secondary);background:var(--el-bg-color);font-size:11px}.voice-cell{grid-template-columns:minmax(180px,240px)}
@media(max-width:760px){.metadata-editor{grid-template-columns:1fr}.metadata-editor .text-field,.metadata-editor .note-field{grid-column:auto}}
.variant-list{display:grid;gap:7px;margin:0 10px 10px;padding:10px 10px 58px;border:1px solid var(--el-border-color-lighter);border-radius:9px;background:var(--el-bg-color)}.variant-list>header{display:flex;align-items:center;justify-content:space-between;gap:8px}.variant-list header small,.variant-item small{color:var(--el-text-color-secondary);font-size:10px}.variant-item{display:grid;grid-template-columns:minmax(150px,1fr) minmax(230px,320px) auto;align-items:center;gap:10px;padding:7px 0;border-top:1px solid var(--el-border-color-lighter)}.variant-item span strong,.variant-item span small{display:block}.variant-item audio{width:100%;height:32px}@media(max-width:760px){.variant-item{grid-template-columns:1fr auto}.variant-item audio{grid-column:1/-1}}
.line-annotations{display:flex;align-items:center;gap:6px;min-width:0;margin:4px 0 7px}.line-annotations>span{min-width:0;overflow:hidden;color:var(--el-text-color-secondary);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.line-annotations>span.missing{color:var(--el-color-warning)}.active-version{padding:2px 7px;border-radius:99px;color:var(--el-color-success)!important;background:var(--el-color-success-light-9)}.guidance-label{flex:0 0 auto;color:var(--el-text-color-secondary);font-size:11px}.source-audio-label{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:0 10px 8px}.source-audio-label small{color:var(--el-text-color-secondary);font-size:10px}.variant-list{padding-bottom:10px}.variant-item{grid-template-columns:minmax(150px,1fr) minmax(230px,320px) auto auto}.variant-item.active{margin:0 -5px;padding:7px 5px;border-radius:7px;background:var(--el-color-success-light-9)}
@media(max-width:760px){.line-annotations{flex-wrap:wrap}.line-annotations>span{flex-basis:100%}.line-tools{align-items:stretch;flex-direction:column}.source-audio-label{align-items:flex-start;flex-direction:column}.variant-item{grid-template-columns:1fr auto}.variant-item audio{grid-column:1/-1}}
</style>
