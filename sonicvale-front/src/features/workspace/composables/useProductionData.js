import { ref, reactive, watch, onBeforeUnmount, inject } from 'vue'
import { createProductionDrafts } from './workspaceDrafts.js'
import { ElMessage } from 'element-plus'
import { createRequestScope, mergeDraft } from './requestScope.js'
import { fetchSessionAudioTasks, fetchChapterProductionConfiguration } from '../../../api/drama'
import { getLinesByChapter } from '../../../api/line'
import { getRolesByProject } from '../../../api/role'
import { fetchVoicesByTTS } from '../../../api/voice'
import { fetchTTSProviders } from '../../../api/provider'
import { fetchAllEmotions, fetchAllStrengths } from '../../../api/enums'

export function useProductionData(props, onFocus) {
const roles=ref([]),voices=ref([]),providers=ref([]),lines=ref([]),productionConfiguration=ref([])
const emotions=ref([]),strengths=ref([]),loading=ref(false)
const roleVoiceMap=reactive({}),audioSummary=reactive({total:0,completed:0,counts:{},tasks:[]})
const drafts=inject('productionDrafts',null)||createProductionDrafts()
const {promptMap,editMap,editBaseline,promptBaseline}=drafts
drafts.activate(`${props.projectId}:${props.chapterId}`)
const requestScope=createRequestScope(()=>`${props.projectId}:${props.chapterId}:${props.sessionId}`)
let pollTimer=null
watch(()=>[props.projectId,props.sessionId,props.chapterId],()=>{
  requestScope.invalidate();clearTimeout(pollTimer)
  drafts.activate(`${props.projectId}:${props.chapterId}`)
  Object.keys(roleVoiceMap).forEach(key=>delete roleVoiceMap[key])
  lines.value=[];productionConfiguration.value=[];loading.value=false;loadAll()
})
onBeforeUnmount(()=>{requestScope.dispose();clearTimeout(pollTimer)})
async function loadAll(){
  if(!props.chapterId)return
  const token=requestScope.begin()
  const {projectId,chapterId,sessionId}=props
  loading.value=true
  try{
    const available=(await fetchTTSProviders())?.filter(item=>item.status!==0)||[]
    if(!requestScope.current(token))return
    const [roleResponse,lineResponse,voiceLists,taskResponse,emotionList,strengthList,config]=await Promise.all([
      getRolesByProject(projectId),getLinesByChapter(chapterId),Promise.all(available.map(item=>fetchVoicesByTTS(item.id))),
      fetchSessionAudioTasks(sessionId),fetchAllEmotions(),fetchAllStrengths(),fetchChapterProductionConfiguration(projectId,chapterId)])
    if(!requestScope.current(token))return
    providers.value=available;roles.value=roleResponse?.data||[];lines.value=lineResponse?.data||[]
    voices.value=voiceLists.flat();emotions.value=emotionList||[];strengths.value=strengthList||[]
    Object.keys(roleVoiceMap).forEach(key=>delete roleVoiceMap[key])
    roles.value.forEach(role=>{if(role.default_voice_id)roleVoiceMap[role.id]=role.default_voice_id})
    lines.value.forEach(line=>{
      const incoming={text_content:line.text_content||'',emotion_id:line.emotion_id||null,strength_id:line.strength_id||null,production_note:line.production_note||''}
      editMap[line.id]=mergeDraft(editMap[line.id],editBaseline[line.id],incoming)
      editBaseline[line.id]=incoming
      if(promptMap[line.id]===undefined||promptMap[line.id]===promptBaseline[line.id])promptMap[line.id]=line.production_note||''
      promptBaseline[line.id]=line.production_note||''
    })
    if(taskResponse?.code===200)Object.assign(audioSummary,taskResponse.data)
    productionConfiguration.value=config?.data?.lines||[]
    if(props.selectedLineId)await onFocus(props.selectedLineId)
    if(requestScope.current(token))schedulePoll()
  }catch(error){if(requestScope.current(token))ElMessage.error(error?.message||'读取制作数据失败')}
  finally{if(requestScope.current(token))loading.value=false}
}

function schedulePoll(){clearTimeout(pollTimer);if((audioSummary.tasks||[]).some(task=>['queued','processing','completing'].includes(task.status)))pollTimer=setTimeout(loadAll,1800)}
return {roles,voices,providers,lines,productionConfiguration,emotions,strengths,loading,roleVoiceMap,audioSummary,promptMap,editMap,editBaseline,requestScope,loadAll}
}
