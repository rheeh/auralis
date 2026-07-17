<template>
  <section class="chat-production">
    <template v-if="!snapshot">
      <div class="creation-grid">
        <section class="creation-form">
          <div class="panel-heading"><div><p class="eyebrow">新会话</p><h2>从小说开始制作</h2></div><el-tag effect="plain">草稿隔离</el-tag></div>
          <div class="sound-first-hint">
            <strong>声音优先改编</strong>
            <span>先分类原文，再用对白、动作声和音乐推进；旁白只保留无法声音化的必要信息、文学金句和视角跳转。</span>
          </div>
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="目标项目" required>
              <el-select :model-value="projectId" filterable class="full" placeholder="选择项目" @update:model-value="$emit('update:projectId',$event)">
                <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="本章标题"><el-input v-model="draft.title" placeholder="例如：第一章 · 雨夜来信" /></el-form-item>
            <el-form-item label="改编要求"><el-input v-model="draft.instruction" type="textarea" :rows="3" resize="none" placeholder="例如：悬疑短剧，用雨声和敲门推进；对白短促，旁白不超过15%" /></el-form-item>
          </el-form>
        </section>
        <section class="source-card">
          <div class="panel-heading"><div><p class="eyebrow">原文</p><h2>小说正文</h2></div><span>{{ sourceChars }} 字</span></div>
          <el-input v-model="draft.source_text" type="textarea" :rows="16" resize="none" placeholder="粘贴本章小说正文。角色与剧本确认前，不会修改项目数据。" />
          <div class="create-actions"><small>创建后可离开页面，返回时会从检查点恢复。</small><el-button type="primary" :loading="isSubmitting" :disabled="!canCreate" @click="create">创建会话并解析原文</el-button></div>
        </section>
      </div>
    </template>

    <template v-else>
      <SessionRestoreBanner :visible="restored" />
      <header class="session-header">
        <div><p class="eyebrow">对话式改编</p><h2>{{ snapshot.title || '未命名改编会话' }}</h2><p>{{ stageDescription }}</p></div>
        <div class="session-actions"><el-tag :type="stageTagType" effect="dark">{{ stageLabel }}</el-tag><el-button :icon="Refresh" :loading="isRefreshing" @click="refresh">刷新</el-button><el-button v-if="canCancel" type="danger" plain @click="cancel">取消会话</el-button></div>
      </header>

      <SessionStageStepper :stage="snapshot.current_stage" />
      <WorkflowErrorCard v-if="snapshot.current_stage==='failed'" :message="snapshot.last_error_message" :loading="isSubmitting" @retry="retry" />

      <div v-else-if="isGenerating && !snapshot.script_draft" class="generating-card" role="status" aria-live="polite">
        <el-skeleton :rows="4" animated /><div><strong>{{ stageLabel }}</strong><p>可以离开此页面，生成完成后会保存在当前会话。</p></div>
      </div>

      <RoleDraftConfirmCard
        v-if="snapshot.current_stage==='awaiting_role_confirmation'"
        :roles="roleDrafts" :revision="snapshot.pending_confirm?.revision" :loading="isSubmitting" @confirm="confirmRoles"
      />
      <ScriptDraftConfirmCard
        v-if="snapshot.script_draft && ['generating_script','reviewing_script','awaiting_script_confirmation'].includes(snapshot.current_stage)"
        :script="snapshot.script_draft" :review="snapshot.script_review" :revision="snapshot.draft_revision"
        :revisions="snapshot.script_revisions || []" :reviewing="snapshot.current_stage==='reviewing_script'"
        :can-confirm="snapshot.current_stage==='awaiting_script_confirmation'" :loading="isSubmitting" @confirm="confirmScript"
      />
      <section v-if="snapshot.current_stage==='script_draft_ready'" class="commit-card">
        <div><p class="eyebrow">已确认</p><h3>剧本可以加入项目</h3><p>提交会在一个事务中写入章节、角色和台词；重复点击不会生成重复内容。</p></div>
        <el-button type="primary" :loading="isSubmitting" @click="commit">写入项目并进入配音</el-button>
      </section>
      <AudioReviewPanel v-if="snapshot.current_stage==='completed'" :session-id="snapshot.session_id" />

      <div class="conversation-grid">
        <section class="conversation-card"><div class="panel-heading"><div><p class="eyebrow">制作记录</p><h2>会话历史</h2></div><span>{{ messages.length }} 条</span></div><ChatMessageList :messages="messages" /></section>
        <ChatComposer v-if="snapshot.current_stage!=='cancelled'" :loading="isSubmitting||Boolean(assistantPending)||isGenerating" @send="sendFeedback" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { API_BASE_URL } from '../../api/config'
import {
  cancelChatSession, commitChatSession, confirmChatDraft, createChatSession,
  fetchChatHistory, fetchChatSession, resumeChatSession, sendChatMessage,
} from '../../api/drama'
import ChatComposer from './ChatComposer.vue'
import AudioReviewPanel from './AudioReviewPanel.vue'
import ChatMessageList from './ChatMessageList.vue'
import RoleDraftConfirmCard from './RoleDraftConfirmCard.vue'
import ScriptDraftConfirmCard from './ScriptDraftConfirmCard.vue'
import SessionRestoreBanner from './SessionRestoreBanner.vue'
import SessionStageStepper from './SessionStageStepper.vue'
import WorkflowErrorCard from './WorkflowErrorCard.vue'

const props = defineProps({ projects:{type:Array,default:()=>[]}, projectId:Number, sessionId:String })
const emit = defineEmits(['update:projectId','session-change','committed'])
const route = useRoute()
const router = useRouter()
const draft = reactive({ title:'', instruction:'', source_text:'' })
const snapshot = ref(null)
const messages = ref([])
const isSubmitting = ref(false)
const isRefreshing = ref(false)
const restored = ref(false)
const assistantPending = ref('')
let pollTimer = null
let socket = null
let reconnectTimer = null
let reconnectDelay = 1000

const sourceChars = computed(()=>draft.source_text.trim().length)
const canCreate = computed(()=>props.projectId && sourceChars.value>0)
const roleDrafts = computed(()=>snapshot.value?.role_drafts?.roles || [])
const isGenerating = computed(()=>['created','parsing','generating_script','reviewing_script'].includes(snapshot.value?.current_stage))
const canRevise = computed(()=>['awaiting_role_confirmation','awaiting_script_confirmation'].includes(snapshot.value?.current_stage))
const canCancel = computed(()=>snapshot.value && !['completed','cancelled'].includes(snapshot.value.current_stage))
const stageLabel = computed(()=>({created:'准备解析',parsing:'正在解析原文',awaiting_role_confirmation:'等待确认角色',generating_script:'正在生成剧本',reviewing_script:'初稿已出 · 审查中',awaiting_script_confirmation:'等待确认剧本',script_draft_ready:'等待写入项目',committing:'正在写入项目',completed:'制作已完成',failed:'需要处理',cancelled:'已取消'}[snapshot.value?.current_stage]||'准备中'))
const stageDescription = computed(()=>({awaiting_role_confirmation:'角色草稿已准备好，需要你的确认。',reviewing_script:'初稿已经可读，独立审查完成后会保留审查与返修版本。',awaiting_script_confirmation:'剧本草稿已准备好，可按场景检查。',script_draft_ready:'剧本已确认，正式项目数据尚未写入。',failed:'当前步骤未完成，可查看原因并重试。'}[snapshot.value?.current_stage]||'系统会保存每一步，页面刷新后仍可继续。'))
const stageTagType = computed(()=>snapshot.value?.current_stage==='failed'?'danger':snapshot.value?.current_stage==='completed'?'success':canRevise.value?'warning':'info')

onMounted(()=>{ const id=props.sessionId||route.params.sessionId||route.query.session_id; if(id) load(id,true) })
watch(()=>props.sessionId,(id)=>{if(id&&id!==snapshot.value?.session_id)load(id,true)})
onBeforeUnmount(cleanup)

function requestId(){ return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` }
function apiError(error, fallback){ return error?.response?.data?.message || error?.message || fallback }
async function create(){
  isSubmitting.value=true
  try{
    const response=await createChatSession({project_id:props.projectId,title:draft.title||null,instruction:draft.instruction||null,source_text:draft.source_text})
    if(![200,202].includes(response.code))throw new Error(response.message||'创建会话失败')
    snapshot.value=response.data;emit('session-change',response.data.session_id)
    await router.replace({path:'/studio',query:{...route.query,project_id:props.projectId,session_id:response.data.session_id}})
    connectSocket();startPolling();await refreshHistory();ElMessage.success('会话已创建，正在解析原文')
  }catch(error){ElMessage.error(apiError(error,'创建会话失败'))}finally{isSubmitting.value=false}
}
async function load(id,isRestore=false){
  isRefreshing.value=true
  try{const response=await fetchChatSession(id);if(response.code!==200)throw new Error(response.message||'会话不存在');snapshot.value=response.data;restored.value=isRestore;emit('update:projectId',response.data.project_id);await refreshHistory();connectSocket();startPolling()}catch(error){ElMessage.error(apiError(error,'恢复会话失败'))}finally{isRefreshing.value=false}
}
async function refresh(){if(!snapshot.value)return;isRefreshing.value=true;try{const response=await fetchChatSession(snapshot.value.session_id);if(response.code===200)snapshot.value=response.data;await refreshHistory()}catch(error){console.warn('刷新会话失败',apiError(error,'网络暂时不可用'))}finally{isRefreshing.value=false}}
async function refreshHistory(){if(!snapshot.value)return;const response=await fetchChatHistory(snapshot.value.session_id,{limit:100});messages.value=response.code===200?response.data:[];if(assistantPending.value&&messages.value.some(item=>item.role==='assistant'&&item.payload?.in_reply_to===assistantPending.value))assistantPending.value=''}
async function confirmRoles(roles){await submitConfirm('roles','confirm_roles',{roles})}
async function confirmScript(script){await submitConfirm('script','confirm_script',{script})}
async function submitConfirm(confirmType,action,payload){
  isSubmitting.value=true
  try{const response=await confirmChatDraft(snapshot.value.session_id,{confirm_type:confirmType,action,feedback:'',payload,client_request_id:requestId()});if(![200,202].includes(response.code))throw new Error(response.message);ElMessage.success(response.message||'操作已提交');startPolling()}catch(error){ElMessage.error(apiError(error,'操作失败'))}finally{isSubmitting.value=false}
}
async function sendFeedback(message){isSubmitting.value=true;try{const response=await sendChatMessage(snapshot.value.session_id,{message,client_request_id:requestId()});if(![200,202].includes(response.code))throw new Error(response.message);assistantPending.value=response.data?.user_message_id||'';startPolling()}catch(error){ElMessage.error(apiError(error,'发送失败'))}finally{isSubmitting.value=false}}
async function retry(){isSubmitting.value=true;try{const response=await resumeChatSession(snapshot.value.session_id);if(![200,202].includes(response.code))throw new Error(response.message);ElMessage.success('正在重试当前步骤');startPolling()}catch(error){ElMessage.error(apiError(error,'重试失败'))}finally{isSubmitting.value=false}}
async function commit(){
  isSubmitting.value=true
  try{const response=await commitChatSession(snapshot.value.session_id,{chapter_title:snapshot.value.title,replace_chapter_lines:true,client_request_id:requestId()});if(response.code!==200)throw new Error(response.message);ElMessage.success(response.message||'剧本已写入项目');await refresh();emit('committed',response.data)}catch(error){ElMessage.error(apiError(error,'写入失败'))}finally{isSubmitting.value=false}
}
async function cancel(){
  try{await ElMessageBox.confirm('取消后将保留会话历史，但不会写入项目数据。','取消改编会话',{confirmButtonText:'确认取消',cancelButtonText:'继续制作',type:'warning'})}catch{return}
  try{const response=await cancelChatSession(snapshot.value.session_id,requestId());if(response.code===200){snapshot.value=response.data;ElMessage.success('会话已取消')}else ElMessage.error(response.message||'取消失败')}catch(error){ElMessage.error(apiError(error,'取消失败'))}
}
function openProject(){router.push(`/projects/${snapshot.value.project_id}/overview`)}
function startPolling(){clearInterval(pollTimer);pollTimer=setInterval(async()=>{await refresh();if(!isGenerating.value&&!isSubmitting.value&&!assistantPending.value)clearInterval(pollTimer)},2200)}
function connectSocket(){
  if(!snapshot.value)return;if(socket)socket.close();clearTimeout(reconnectTimer)
  const api=new URL(API_BASE_URL);const protocol=api.protocol==='https:'?'wss':'ws';socket=new WebSocket(`${protocol}://${api.host}/ws/projects/${snapshot.value.project_id}/sessions/${snapshot.value.session_id}`)
  socket.onopen=()=>{reconnectDelay=1000;socket.send(JSON.stringify({type:'ping'}))}
  socket.onmessage=async(event)=>{try{const data=JSON.parse(event.data);if(data.event_type){await refresh();if(['role_draft_ready','script_draft_ready','workflow_failed','workflow_completed'].includes(data.event_type))await refreshHistory()}}catch{}}
  socket.onclose=()=>{if(snapshot.value&&!['completed','cancelled'].includes(snapshot.value.current_stage)){reconnectTimer=setTimeout(connectSocket,reconnectDelay);reconnectDelay=Math.min(reconnectDelay*2,15000)}}
}
function cleanup(){clearInterval(pollTimer);clearTimeout(reconnectTimer);if(socket){socket.onclose=null;socket.close()}}
</script>

<style scoped>
.chat-production{display:grid;gap:16px}.creation-grid{display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:16px}.creation-form,.source-card,.conversation-card,.session-header,.generating-card,.commit-card{padding:16px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}.panel-heading,.session-header,.create-actions,.session-actions,.commit-card{display:flex;align-items:center;justify-content:space-between;gap:12px}.panel-heading h2,.session-header h2,.commit-card h3,.eyebrow{margin:0}.panel-heading h2,.session-header h2{font-size:18px}.eyebrow{margin-bottom:4px;color:var(--el-color-primary);font-size:12px;text-transform:uppercase}.full{width:100%}.source-card{display:grid;gap:12px}.create-actions{align-items:flex-end}.create-actions small{max-width:420px;color:var(--el-text-color-secondary);line-height:1.5}.session-header>div>p:not(.eyebrow),.commit-card p,.generating-card p{margin:6px 0 0;color:var(--el-text-color-secondary);line-height:1.55}.session-actions{flex-wrap:wrap}.generating-card{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,320px);align-items:center}.commit-card{border-color:color-mix(in srgb,var(--el-color-success) 40%,var(--el-border-color));background:color-mix(in srgb,var(--el-color-success) 6%,var(--el-bg-color))}.conversation-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,390px);gap:16px;align-items:start}.conversation-card{display:grid;gap:12px}.sound-first-hint{display:grid;gap:4px;margin:12px 0 16px;padding:11px 12px;border:1px solid color-mix(in srgb,var(--el-color-primary) 28%,var(--el-border-color));border-radius:10px;background:linear-gradient(135deg,color-mix(in srgb,var(--el-color-primary) 9%,var(--el-bg-color)),color-mix(in srgb,#d88bd5 7%,var(--el-bg-color)))}.sound-first-hint strong{font-size:13px}.sound-first-hint span{color:var(--el-text-color-secondary);font-size:12px;line-height:1.55}
@media(max-width:900px){.creation-grid,.conversation-grid{grid-template-columns:1fr}.session-header,.commit-card{align-items:flex-start;flex-direction:column}.generating-card{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
</style>
