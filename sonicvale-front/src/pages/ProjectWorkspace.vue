<template>
  <div class="project-workspace">
    <header class="workspace-header">
      <div><p class="workspace-eyebrow">章节工作台</p><h1>{{ project?.name || '广播剧制作' }}</h1></div>
      <div class="workspace-actions">
        <el-select :model-value="snapshot?.chapter_id || null" placeholder="选择章节" aria-label="当前章节" :disabled="loadingWorkspace" @change="changeChapter"><el-option v-for="chapter in chapters" :key="chapter.id" :label="chapter.title" :value="chapter.id" /></el-select>
        <el-button @click="startNew">新建章节</el-button>
        <el-button :aria-expanded="assistantOpen" @click="assistantOpen=!assistantOpen">{{ assistantOpen?'收起制作助手':'打开制作助手' }}</el-button>
      </div>
    </header>
    <ProductionSteps :model-value="selectedView" :steps="workspaceSteps" @update:model-value="selectView" />
    <el-alert v-if="workspaceError" :title="workspaceError" type="error" :closable="false" />
    <section v-loading="loadingWorkspace" class="workspace-grid" :class="{'assistant-hidden':!assistantOpen}">
      <aside v-show="assistantOpen" class="conversation-panel">
        <div class="conversation-scroll">
          <section v-if="snapshot" class="assistant-mission">
            <div>
              <span>当前任务</span>
              <div class="mission-actions"><el-tag size="small" effect="plain">{{ stageLabel }}</el-tag><el-button text size="small" @click="startNew">新改编</el-button></div>
            </div>
            <strong>{{ assistantMission.title }}</strong>
            <p>{{ assistantMission.detail }}</p>
          </section>
          <div v-if="!messages.length" class="welcome-message">
            <strong>一个页面完成广播剧制作</strong>
            <p>我会先解析小说并生成主要角色身份卡；你确认人物后生成台本，满意后逐句绑定音色并生成音频。</p>
          </div>
          <ChatMessageList v-else :messages="messages" />
        </div>

        <div v-if="snapshot" class="session-composer">
          <div class="assistant-actions">
            <template v-if="snapshot.current_stage==='awaiting_role_confirmation'">
              <el-button type="primary" :loading="actionBusy" :disabled="!roleEditsReady" @click="confirmRoles(roleEdits)">确认人物并生成台本</el-button>
              <small>你也可以继续在右侧修改人物卡、头像和音色。</small>
            </template>
            <template v-else-if="snapshot.current_stage==='awaiting_script_confirmation'">
              <el-button size="small" :disabled="actionBusy" @click="sendSuggestedRevision('进一步减少旁白，把能听见的动作改成对白或音效。')">减少旁白</el-button>
              <el-button size="small" :disabled="actionBusy" @click="sendSuggestedRevision('检查所有 SFX 和 BGM，为空的声音轨补充可直接制作的详细声音提示词。')">补全音效提示</el-button>
              <el-button type="primary" :loading="actionBusy" @click="confirmScript(snapshot.script_draft)">台本满意，进入制作</el-button>
            </template>
            <template v-else-if="snapshot.current_stage==='script_draft_ready'">
              <el-button type="primary" :loading="actionBusy" @click="commitScript">建立逐句制作</el-button>
            </template>
            <template v-else-if="snapshot.current_stage==='completed'">
              <el-button size="small" @click="selectView('script');resultView='characters'">查看人物卡</el-button>
              <el-button size="small" :disabled="assistantBusy" @click="sendSuggestedRevision('播放本章所有已生成的音频。')">一键播放</el-button>
              <el-button type="primary" size="small" :loading="assistantBusy" @click="sendSuggestedRevision('生成本章所有缺失的试听音频。')">生成缺失试听</el-button>
            </template>
            <span v-else class="working-hint"><i /> AI 正在处理，完成后这里会出现下一步操作。</span>
          </div>
          <el-input
            v-model="feedback"
            type="textarea"
            :rows="3"
            resize="none"
            :disabled="!canMessage || assistantBusy"
            :placeholder="assistantPlaceholder"
            @keydown.enter.exact.prevent="sendRevision"
          />
          <div class="composer-footer">
            <el-button :icon="Refresh" :loading="refreshing" @click="refresh">刷新</el-button>
            <el-button type="primary" :disabled="!canMessage || !feedback.trim() || assistantBusy" :loading="assistantBusy || submitting" @click="sendRevision">发送</el-button>
          </div>
        </div>
      </aside>

      <section class="result-panel">
        <div v-if="selectedView==='script' && canViewCharacters" class="result-head">
          <div class="view-switch">
            <el-button size="small" :type="resultView==='output'?'primary':'default'" @click="resultView='output'">当前制作</el-button>
            <el-button size="small" :type="resultView==='characters'?'primary':'default'" @click="selectView('script');resultView='characters'">人物卡</el-button>
          </div>
        </div>

        <section v-if="selectedView==='source'" class="workspace-source">
          <h2>小说原文</h2><p class="source-hint">从原文建立人物和台本，确认后进入配音与声音编排。</p>
          <template v-if="snapshot"><h3>{{ snapshot.title }}</h3><pre>{{ snapshot.source_text || '这个章节没有保存原文，可直接继续编辑台本。' }}</pre><p v-if="snapshot.instruction">改编要求：{{ snapshot.instruction }}</p><el-button type="primary" @click="selectView('script')">查看人物与台本</el-button></template>
        <div v-else class="source-composer">
          <el-input v-model="draft.title" placeholder="章节或本次改编标题（可选）" />
          <el-input v-model="draft.source_text" type="textarea" :rows="10" resize="none" placeholder="把小说原文粘贴到这里……" />
          <el-input v-model="draft.instruction" type="textarea" :rows="3" resize="none" placeholder="补充要求：风格、时长、节奏、旁白比例等（可选）" />
          <div class="composer-footer"><span>{{ sourceChars }} 字</span><el-button type="primary" :loading="submitting" :disabled="!sourceChars" @click="createSession">解析原文，进入人物与台本</el-button></div>
        </div>

        </section>
        <ChapterTimeline v-else-if="['timeline','export'].includes(selectedView) && snapshot?.chapter_id" :key="`timeline-${snapshot.chapter_id}-${selectedView}`" :project-id="projectId" :chapter-id="snapshot.chapter_id" :selected-line-id="selectedLineId" :export-only="selectedView==='export'" @focus-line="focusProductionLine" />
        <CharacterCardsArchive v-else-if="resultView==='characters' && selectedView==='script'" :roles="roleDrafts" :session-id="snapshot?.session_id" :project-id="projectId" @voice-changed="voiceRevision++" />

        <div v-else-if="!snapshot" class="result-empty">
          <el-icon><Document /></el-icon>
          <h3>等待小说原文</h3>
          <p>右侧不会跳走：角色卡、广播剧台本、角色音色和逐句音频都会依次出现在这里。</p>
        </div>

        <ScriptDraftConfirmCard
          v-else-if="snapshot.script_draft && ['generating_script','reviewing_script','awaiting_script_confirmation'].includes(snapshot.current_stage)"
          :script="snapshot.script_draft"
          :review="snapshot.script_review"
          :revision="snapshot.draft_revision"
          :revisions="snapshot.script_revisions || []"
          :reviewing="snapshot.current_stage === 'reviewing_script'"
          :can-confirm="snapshot.current_stage === 'awaiting_script_confirmation'"
          :loading="actionBusy"
          confirm-label="进入逐句制作"
          @confirm="confirmScript"
        />

        <div v-else-if="isGenerating" class="processing-state">
          <el-skeleton :rows="8" animated />
          <div><strong>{{ stageLabel }}</strong><p>{{ processingHint }}</p></div>
        </div>

        <WorkflowErrorCard v-else-if="snapshot.current_stage === 'failed'" :message="snapshot.last_error_message" :loading="actionBusy" @retry="retry" />

        <RoleDraftConfirmCard
          v-else-if="snapshot.current_stage === 'awaiting_role_confirmation'"
          :roles="roleDrafts"
          :session-id="snapshot.session_id"
          :revision="snapshot.pending_confirm?.revision"
          :loading="actionBusy"
          confirm-label="人物设定满意，生成台本"
          @update:roles="roleEdits=$event"
          @confirm="confirmRoles"
        />

        <section v-else-if="snapshot.current_stage === 'script_draft_ready'" class="commit-state">
          <div><p class="eyebrow">台本已确认</p><h3>正在建立逐句制作单元</h3><p>写入后，每句台词会直接显示角色音色、生成状态和试听结果。</p></div>
          <el-button type="primary" :loading="actionBusy" @click="commitScript">进入逐句制作</el-button>
        </section>

        <ProductionScriptPanel
          ref="productionRef"
          v-else-if="snapshot.current_stage === 'completed' && snapshot.chapter_id"
          :key="`production-${snapshot.chapter_id}-${selectedView}`"
          :session-id="snapshot.session_id"
          :project-id="projectId"
          :chapter-id="snapshot.chapter_id"
          :selected-line-id="selectedLineId"
          :script-only="selectedView==='script'"
          @open-timeline="openTimeline"
          :tts-provider-id="project?.tts_provider_id"
          :source-text="snapshot.source_text"
          :voice-revision="voiceRevision"
        />
      </section>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, Refresh } from '@element-plus/icons-vue'
import {
  openChapterWorkspace,
  commitChatSession,
  confirmChatDraft,
  createChatSession,
  fetchChatHistory,
  fetchChatSession,
  fetchChatSessions,
  resumeChatSession,
  sendChatMessage,
} from '../api/drama'
import { getProjectDetail } from '../api/project'
import { getChaptersByProject } from '../api/chapter'
import ProductionSteps from '../components/production/ProductionSteps.vue'
import ChapterTimeline from '../components/production/ChapterTimeline.vue'
import { defaultWorkspaceView, resolveWorkspaceView, workspaceLocation } from '../workspace/navigation'
import ChatMessageList from '../components/workflow/ChatMessageList.vue'
import CharacterCardsArchive from '../components/workflow/CharacterCardsArchive.vue'
import ProductionScriptPanel from '../components/workflow/ProductionScriptPanel.vue'
import RoleDraftConfirmCard from '../components/workflow/RoleDraftConfirmCard.vue'
import ScriptDraftConfirmCard from '../components/workflow/ScriptDraftConfirmCard.vue'
import WorkflowErrorCard from '../components/workflow/WorkflowErrorCard.vue'

const route = useRoute(), router = useRouter()
const projectId = Number(route.params.id)
const chapters=ref([]),assistantOpen=ref(false),loadingWorkspace=ref(false),workspaceError=ref('')
const selectedLineId=computed(()=>Number(route.query.line_id)||null)
const selectedView=computed(()=>resolveWorkspaceView(route.query.view,snapshot.value?.current_stage,snapshot.value?.chapter_id))
const workspaceSteps=computed(()=>[
  {id:'source',label:'原文'}, {id:'script',label:'人物与台本',disabled:!snapshot.value},
  ...[{id:'voices',label:'配音'},{id:'timeline',label:'声音编排'},{id:'export',label:'导出'}].map(item=>({...item,disabled:snapshot.value?.current_stage!=='completed'||!snapshot.value?.chapter_id})),
])
let workspaceEpoch=0
function selectView(view){resultView.value='output';router.replace({...workspaceLocation(projectId,snapshot.value?.chapter_id,view,selectedLineId.value),query:{...route.query,...workspaceLocation(projectId,snapshot.value?.chapter_id,view,selectedLineId.value).query}})}
function changeChapter(chapterId){router.push(workspaceLocation(projectId,chapterId,selectedView.value))}
function openTimeline(lineId){router.push(workspaceLocation(projectId,snapshot.value?.chapter_id,'timeline',lineId))}
async function focusProductionLine(lineId){await router.push(workspaceLocation(projectId,snapshot.value?.chapter_id,'voices',lineId));await nextTick();if(lineId)await productionRef.value?.focusLine?.(lineId)}
watch(()=>route.query.chapter_id,(next,previous)=>{if(next!==previous && Number(next)!==snapshot.value?.chapter_id)loadWorkspace()})
const project = ref(null)
const snapshot = ref(null)
const messages = ref([])
const feedback = ref('')
const assistantBusy = ref(false)
const pendingAssistantMessageId = ref('')
const assistantStartedAt = ref(0)
const draft = reactive({ title:'', source_text:'', instruction:'旁白克制，优先用对白、音效和音乐推进情节。' })
const submitting = ref(false)
const refreshing = ref(false)
const autoCommit = ref(false)
const resultView = ref('output')
const transitioning = ref(false)
const transitionFromStage = ref('')
const roleEdits = ref([])
const productionRef = ref(null)
const voiceRevision = ref(0)
let pollTimer = null
let transitionStartedAt = 0
watch(()=>snapshot.value?.current_stage,(stage,previous)=>{if(stage && stage!==previous && previous && ['source','script'].includes(selectedView.value))selectView(defaultWorkspaceView(stage))})

const sourceChars = computed(() => draft.source_text.trim().length)
const roleDrafts = computed(() => snapshot.value?.role_drafts?.roles || [])
const canViewCharacters = computed(() => roleDrafts.value.length > 0 && snapshot.value?.current_stage !== 'awaiting_role_confirmation')
const canMessage = computed(() => snapshot.value && !['created','parsing','generating_script','reviewing_script','committing','cancelled'].includes(snapshot.value.current_stage))
const actionBusy = computed(() => submitting.value || transitioning.value || assistantBusy.value)
const assistantPlaceholder = computed(() => ({
  awaiting_role_confirmation:'可以询问人物设定，或直接告诉助手如何修改角色……',
  awaiting_script_confirmation:'可以修改场景、对白、旁白或音效，也可以询问当前台本……',
  completed:'例如：查看缺失音频、修改第12句、给对应角色换音色并重新生成……',
  failed:'可以询问失败原因，或让助手检查当前项目状态……',
}[snapshot.value?.current_stage] || '可以随时询问当前进度或告诉制作助手下一步要做什么……'))
const roleEditsReady = computed(() => roleEdits.value.filter(role=>role.selected!==false).length>0 && roleEdits.value.filter(role=>role.selected!==false).every(role=>role.default_voice_id))
const isGenerating = computed(() => ['created','parsing','generating_script','reviewing_script','committing'].includes(snapshot.value?.current_stage))
const activeStage = computed(() => {
  const stage = snapshot.value?.current_stage
  if (!snapshot.value) return 'source'
  if (['created','parsing','awaiting_role_confirmation'].includes(stage)) return 'roles'
  if (['generating_script','reviewing_script','awaiting_script_confirmation','script_draft_ready','committing'].includes(stage)) return 'script'
  return 'production'
})
const stageLabel = computed(() => ({created:'准备解析',parsing:'正在解析小说',awaiting_role_confirmation:'确认人物设定',generating_script:'正在生成台本',reviewing_script:'初稿已出 · AI 审查中',awaiting_script_confirmation:'确认广播剧台本',script_draft_ready:'台本已确认',committing:'正在建立逐句制作',completed:'逐句制作',failed:'需要处理',cancelled:'已取消'}[snapshot.value?.current_stage] || '项目工作台'))
const stageDescription = computed(() => ({awaiting_role_confirmation:'先确认主要人物身份和说话方式。',awaiting_script_confirmation:'检查对白、旁白比例和声音轨。',completed:'逐句绑定音色、生成并试听音频。'}[snapshot.value?.current_stage] || 'AI 正在推进当前步骤。'))
const stageType = computed(() => snapshot.value?.current_stage === 'failed' ? 'danger' : snapshot.value?.current_stage === 'completed' ? 'success' : 'warning')
const processingHint = computed(() => activeStage.value === 'roles' ? '正在识别人物身份、关系、动机和说话方式。' : '正在把剧情改成对白、音效、音乐与少量必要旁白。')
const assistantMission = computed(() => ({
  awaiting_role_confirmation:{title:'确认人物、头像和声线',detail:'人物卡决定台词写法。确认前请保证每个人物已绑定不同音色。'},
  generating_script:{title:'正在生成广播剧台本',detail:'AI 正在把小说转换成对白、音效、BGM 与必要旁白。'},
  reviewing_script:{title:'初稿已经生成，正在独立审查',detail:'现在可以阅读初稿；如果 AI 返修，会保留两个版本供你比较。'},
  awaiting_script_confirmation:{title:'审听台本的声音结构',detail:'检查对白是否自然、旁白是否克制、音效提示是否足够具体。'},
  script_draft_ready:{title:'把台本建立为逐句制作单元',detail:'建立后即可单句生成试听、调整提示词和连续播放。'},
  completed:{title:'逐句试听与精修',detail:'可以单独生成任意一句，也可以生成缺失音频并整章连续播放。'},
  failed:{title:'当前步骤需要处理',detail:snapshot.value?.last_error_message||'请重试或修改输入。'},
}[snapshot.value?.current_stage]||{title:'AI 正在推进制作',detail:'处理完成后会自动刷新并显示下一步。'}))

onMounted(loadWorkspace)
onBeforeUnmount(() => {workspaceEpoch++;clearTimeout(pollTimer)})

async function loadWorkspace() {
  const epoch=++workspaceEpoch
  clearTimeout(pollTimer);loadingWorkspace.value=true;workspaceError.value=''
  try {
    try {const imported=sessionStorage.getItem(`auralis-source-${projectId}`);if(imported){Object.assign(draft,JSON.parse(imported));sessionStorage.removeItem(`auralis-source-${projectId}`)}} catch {}
    const [projectResponse,chaptersResponse,sessionsResponse]=await Promise.all([getProjectDetail(projectId),getChaptersByProject(projectId),fetchChatSessions({project_id:projectId,limit:100})])
    if(epoch!==workspaceEpoch)return
    if(projectResponse?.code!==200)throw new Error('项目不存在或无法读取')
    project.value=projectResponse.data;chapters.value=chaptersResponse?.code===200?chaptersResponse.data||[]:[]
    const projectCreatedAt=new Date(project.value.created_at||0).getTime()
    const sessions=(sessionsResponse?.code===200?sessionsResponse.data||[]:[]).filter(item=>item.current_stage!=='cancelled' && (!projectCreatedAt || new Date(item.created_at||0).getTime()>=projectCreatedAt))
    if(route.query.new==='1'){snapshot.value=null;messages.value=[];return}
    const requested=Number(route.query.chapter_id)
    if(requested && !chapters.value.some(chapter=>chapter.id===requested))throw new Error('该章节不属于当前项目或已被移除')
    const latest=route.query.session_id?sessions.find(item=>item.session_id===route.query.session_id):requested?sessions.find(item=>item.chapter_id===requested):sessions[0]
    snapshot.value=null;messages.value=[]
    if(latest)await loadSession(latest.session_id,epoch)
    else if(requested || chapters.value.length){const response=await openChapterWorkspace(projectId,requested||chapters.value[0].id);if(response?.code!==200)throw new Error(response?.message||'章节工作台打开失败');if(epoch===workspaceEpoch)await loadSession(response.data.session_id,epoch)}
    if(snapshot.value && epoch===workspaceEpoch){const location=workspaceLocation(projectId,snapshot.value.chapter_id,resolveWorkspaceView(route.query.view,snapshot.value.current_stage,snapshot.value.chapter_id),selectedLineId.value);if(!snapshot.value.chapter_id)location.query.session_id=snapshot.value.session_id;await router.replace(location)}
  } catch(error){if(epoch===workspaceEpoch){workspaceError.value=apiError(error,'工作台读取失败');snapshot.value=null}}
  finally{if(epoch===workspaceEpoch)loadingWorkspace.value=false}
}

function requestId() { return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}` }
function startNew(){workspaceEpoch++;clearTimeout(pollTimer);snapshot.value=null;messages.value=[];feedback.value='';assistantBusy.value=false;pendingAssistantMessageId.value='';draft.title='';draft.source_text='';resultView.value='output';workspaceError.value='';router.push({path:route.path,query:{view:'source',new:'1'}})}

async function createSession() {
  if (!sourceChars.value) return
  submitting.value = true
  try {
    const response = await createChatSession({ project_id:projectId, title:draft.title || null, source_text:draft.source_text, instruction:draft.instruction || null })
    if (![200,202].includes(response?.code)) throw new Error(response?.message || '创建会话失败')
    snapshot.value = response.data
    await router.replace({path:route.path,query:{view:'script',session_id:response.data.session_id}})
    await refreshHistory()
    schedulePoll()
  } catch (error) { ElMessage.error(apiError(error,'创建改编失败')) } finally { submitting.value=false }
}

async function loadSession(sessionId, epoch=workspaceEpoch) {
  const response = await fetchChatSession(sessionId)
  if (response?.code === 200 && epoch===workspaceEpoch) {
    const nextStage=response.data.current_stage
    snapshot.value=response.data
    if (transitioning.value && nextStage!==transitionFromStage.value) {
      transitioning.value=false;transitionFromStage.value='';transitionStartedAt=0
    }
    if (nextStage==='awaiting_role_confirmation') roleEdits.value=JSON.parse(JSON.stringify(response.data?.role_drafts?.roles||[]))
    await refreshHistory();schedulePoll()
  }
}
async function refresh() {
  if (!snapshot.value) return
  refreshing.value=true
  try { await loadSession(snapshot.value.session_id) } catch (error) { ElMessage.error(apiError(error,'刷新失败')) } finally { refreshing.value=false }
}
async function refreshHistory() {
  if (!snapshot.value) return
  const response = await fetchChatHistory(snapshot.value.session_id,{limit:100})
  messages.value = response?.code === 200 ? response.data || [] : []
  if (pendingAssistantMessageId.value) {
    const reply=messages.value.find(item=>item.role==='assistant'&&item.payload?.in_reply_to===pendingAssistantMessageId.value)
    if(reply){assistantBusy.value=false;assistantStartedAt.value=0;pendingAssistantMessageId.value='';await applyAssistantActions(reply.payload?.ui_actions||[])}
  }
}
async function sendRevision() {
  if (!canMessage.value || !feedback.value.trim()) return
  await submitRevision(feedback.value.trim())
}
async function sendSuggestedRevision(message) { await submitRevision(message) }
async function submitRevision(message) {
  if(!canMessage.value||assistantBusy.value)return
  assistantBusy.value=true;assistantStartedAt.value=Date.now()
  try {
    const response=await sendChatMessage(snapshot.value.session_id,{message,client_request_id:requestId()})
    if(![200,202].includes(response?.code))throw new Error(response?.message||'提交失败')
    feedback.value='';pendingAssistantMessageId.value=response.data?.user_message_id||'';await refreshHistory();schedulePoll()
  }catch(error){assistantBusy.value=false;assistantStartedAt.value=0;ElMessage.error(apiError(error,'制作助手处理失败'))}
}
async function confirmRoles(roles) { await submitConfirm('roles','confirm_roles',{roles}) }
async function confirmScript(script) { autoCommit.value=true;await submitConfirm('script','confirm_script',{script}) }
async function submitConfirm(confirmType,action,payload) {
  if(actionBusy.value)return
  transitioning.value=true;transitionFromStage.value=snapshot.value.current_stage;transitionStartedAt=Date.now()
  submitting.value=true
  try {
    const response=await confirmChatDraft(snapshot.value.session_id,{confirm_type:confirmType,action,feedback:'',payload,client_request_id:requestId()})
    if(![200,202].includes(response?.code))throw new Error(response?.message||'确认失败')
    if(response?.data?.current_stage && response.data.current_stage!==transitionFromStage.value) snapshot.value=response.data
    schedulePoll()
  }catch(error){transitioning.value=false;transitionFromStage.value='';autoCommit.value=false;ElMessage.error(apiError(error,'确认失败'))}finally{submitting.value=false}
}
async function commitScript() {
  if (!snapshot.value) return
  submitting.value=true
  try {
    const response=await commitChatSession(snapshot.value.session_id,{chapter_title:snapshot.value.title,replace_chapter_lines:true,client_request_id:requestId()})
    if(response?.code!==200)throw new Error(response?.message||'写入失败')
    autoCommit.value=false
    await loadSession(snapshot.value.session_id)
    ElMessage.success('台本已进入逐句制作')
  }catch(error){ElMessage.error(apiError(error,'建立逐句制作失败'))}finally{submitting.value=false}
}
async function retry() {
  submitting.value=true
  try { const response=await resumeChatSession(snapshot.value.session_id);if(![200,202].includes(response?.code))throw new Error(response?.message);schedulePoll() }
  catch(error){ElMessage.error(apiError(error,'重试失败'))}finally{submitting.value=false}
}
function schedulePoll() {
  clearTimeout(pollTimer)
  if (!snapshot.value) return
  const stage=snapshot.value.current_stage
  if (autoCommit.value && stage==='script_draft_ready') { commitScript();return }
  if (transitioning.value && transitionStartedAt && Date.now()-transitionStartedAt>120000) {
    transitioning.value=false;transitionFromStage.value='';ElMessage.warning('处理时间较长，已停止自动等待，可点击刷新查看。');return
  }
  if (assistantBusy.value && assistantStartedAt.value && Date.now()-assistantStartedAt.value>180000) {
    assistantBusy.value=false;assistantStartedAt.value=0;pendingAssistantMessageId.value='';ElMessage.warning('制作助手处理时间较长，请稍后点击刷新查看回复。')
  }
  if (isGenerating.value || autoCommit.value || transitioning.value || assistantBusy.value) pollTimer=setTimeout(async()=>{await refresh()},1000)
}
async function applyAssistantActions(actions){
  if(!actions.length)return
  await focusProductionLine(null)
  resultView.value='output'
  await nextTick()
  if(actions.some(action=>action.type==='refresh_project'))await productionRef.value?.loadAll?.()
  const focus=actions.find(action=>action.type==='focus_line')
  if(focus)productionRef.value?.focusLine?.(focus.line_id)
  const playLine=actions.find(action=>action.type==='play_line')
  if(playLine)productionRef.value?.playLineById?.(playLine.line_id)
  else if(actions.some(action=>action.type==='play_all'))productionRef.value?.togglePlayAll?.()
}
function apiError(error,fallback){return error?.response?.data?.message||error?.message||fallback}
</script>

<style scoped>
.project-workspace{height:100%;min-height:0}.workspace-meta,.composer-footer,.result-head,.stage-dots{display:flex;align-items:center;gap:10px}.result-head,.composer-footer{justify-content:space-between}.eyebrow,.result-head h2{margin:0}.eyebrow{margin-bottom:3px;color:var(--el-color-primary);font-size:11px;text-transform:uppercase}.workspace-grid{display:grid;grid-template-columns:minmax(320px,380px) minmax(0,1fr);gap:8px;height:100%;min-height:0}.conversation-panel,.result-panel{min-height:0;border:1px solid var(--el-border-color-lighter);border-radius:14px;background:var(--el-bg-color);box-shadow:var(--auralis-shadow-sm);overflow:hidden}.conversation-panel{display:grid;grid-template-rows:minmax(0,1fr) auto}.conversation-scroll{min-height:0;overflow:auto;padding:10px}.welcome-message{padding:13px;border-radius:11px;background:var(--el-fill-color-light)}.welcome-message p{margin:6px 0 0;color:var(--el-text-color-secondary);font-size:12px;line-height:1.6}.source-composer,.session-composer{display:grid;gap:8px;padding:10px;border-top:1px solid var(--el-border-color-lighter);background:var(--el-fill-color-extra-light)}.composer-footer span{color:var(--el-text-color-secondary);font-size:11px}.result-panel{display:flex;flex-direction:column}.result-head{flex:0 0 auto;padding:10px 14px;border-bottom:1px solid var(--el-border-color-lighter)}.result-head h2{font-size:20px}.stage-dots{flex-wrap:wrap}.stage-dots span{padding:4px 8px;border-radius:999px;color:var(--el-text-color-secondary);background:var(--el-fill-color-light);font-size:11px}.stage-dots span.active{color:#18212d;background:linear-gradient(135deg,#8feeee,#e8a3dd)}.stage-dots span.done{color:var(--el-color-success);background:var(--el-color-success-light-9)}.result-panel>:not(.result-head){margin:12px;overflow:auto}.result-empty{display:grid;place-items:center;align-content:center;min-height:360px;text-align:center;color:var(--el-text-color-secondary)}.result-empty .el-icon{font-size:54px}.result-empty h3{margin:16px 0 6px;color:var(--el-text-color-primary)}.result-empty p{max-width:460px;margin:0;line-height:1.7}.processing-state{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:20px;align-items:center}.processing-state p,.commit-state p{color:var(--el-text-color-secondary);line-height:1.6}.commit-state{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px!important;border:1px solid color-mix(in srgb,var(--el-color-success) 35%,var(--el-border-color));border-radius:12px;background:color-mix(in srgb,var(--el-color-success) 5%,var(--el-bg-color))}@media(max-width:1050px){.workspace-grid{grid-template-columns:minmax(290px,340px) minmax(0,1fr)}.stage-dots{display:none}}@media(max-width:760px){.project-workspace{height:auto}.workspace-grid{grid-template-columns:1fr}.conversation-panel{min-height:620px}.result-panel{min-height:600px}.processing-state{grid-template-columns:1fr}}
.assistant-mission{display:grid;gap:4px;margin-bottom:10px;padding:10px 11px;border:1px solid color-mix(in srgb,var(--el-color-primary) 24%,var(--el-border-color-lighter));border-radius:11px;background:linear-gradient(135deg,color-mix(in srgb,#69e9ef 8%,var(--el-bg-color)),color-mix(in srgb,#e58ad7 7%,var(--el-bg-color)))}
.assistant-mission>div{display:flex;align-items:center;justify-content:space-between;gap:8px}.assistant-mission>div span{color:var(--el-color-primary);font-size:11px;font-weight:600}.assistant-mission strong{font-size:13px}.assistant-mission p{margin:0;color:var(--el-text-color-secondary);font-size:11px;line-height:1.5}
.mission-actions{display:flex;align-items:center;gap:2px}.mission-actions .el-button{padding-inline:5px}
.assistant-actions{display:flex;flex-wrap:wrap;gap:6px}.working-hint{display:flex;align-items:center;gap:7px;color:var(--el-text-color-secondary);font-size:11px;line-height:1.45}
.working-hint i{width:7px;height:7px;flex:0 0 7px;border-radius:50%;background:var(--el-color-primary);box-shadow:0 0 0 4px color-mix(in srgb,var(--el-color-primary) 14%,transparent);animation:assistant-pulse 1.4s ease-in-out infinite}
@keyframes assistant-pulse{50%{opacity:.45;transform:scale(.82)}}
.result-head{justify-content:center;min-height:42px;padding:5px 12px}.view-switch{display:flex;align-items:center;gap:8px}.view-switch .el-button{min-width:88px;font-size:13px}

.project-workspace{height:auto;min-height:100%;display:flex;flex-direction:column;gap:16px}.workspace-header{display:flex;align-items:center;justify-content:space-between;gap:14px}.workspace-header h1{font-size:22px;margin:4px 0}.workspace-eyebrow{margin:0;font-size:11px;color:var(--el-text-color-secondary)}.workspace-actions{display:flex;gap:8px;align-items:center}.workspace-actions .el-select{width:240px}.workspace-grid{min-height:600px;flex:1;align-items:start}.workspace-grid.assistant-hidden{grid-template-columns:minmax(0,1fr)}.conversation-panel{position:sticky;top:12px;max-height:calc(100vh - 240px);min-height:500px}.result-panel{min-height:600px;overflow:visible}.workspace-source{padding:24px;max-width:960px}.workspace-source h2{margin:0 0 10px}.source-hint{color:var(--el-text-color-secondary)}.workspace-source pre{font:inherit;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere;padding:20px;background:var(--el-fill-color-extra-light);border-radius:10px}.workspace-source .source-composer{padding:0;border:0}.workspace-source .source-composer .el-input{margin-bottom:10px}@media(max-width:900px){.workspace-header{align-items:flex-start;flex-direction:column}.workspace-actions{width:100%;flex-wrap:wrap}.workspace-actions .el-select{flex:1;min-width:160px}.workspace-grid{grid-template-columns:1fr}.conversation-panel{position:static;max-height:520px}.workspace-source{padding:16px}}
</style>
