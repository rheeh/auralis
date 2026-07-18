<template>
  <section class="study-card">
    <header><div><p class="eyebrow">听后复习</p><h3>知识点、原文依据与复习问题</h3></div><el-button :loading="loading" @click="load">刷新</el-button></header>
    <div class="study-grid">
      <section class="points"><h4>核心知识点</h4><article v-for="point in points" :key="point.id"><strong>{{ point.title }}</strong><p>{{ point.one_sentence_summary || point.explanation }}</p><blockquote>{{ point.source_excerpt }}</blockquote><div v-if="point.script_lines?.length" class="related-lines"><span>相关音频片段</span><audio v-for="line in point.script_lines.filter(item=>item.has_audio)" :key="line.line_id" :src="audioUrl(line.line_id)" controls preload="none" /></div></article></section>
      <section class="questions"><h4>复习问题</h4><article v-for="(question,index) in questions" :key="question.id"><strong>{{ index+1 }}. {{ question.question }}</strong><el-input v-model="answers[question.id]" type="textarea" :rows="2" resize="none" placeholder="写下你的答案" /><el-button size="small" :loading="answeringId===question.id" :disabled="!answers[question.id]?.trim()" @click="submitAnswer(question)">提交答案</el-button><div v-if="results[question.id]" class="answer-result"><el-tag :type="results[question.id].matches_reference?'success':'info'" effect="plain">{{ results[question.id].matches_reference?'与参考答案一致':'请对照参考答案' }}</el-tag><p><strong>参考答案：</strong>{{ results[question.id].reference_answer }}</p><blockquote>{{ results[question.id].source_excerpt }}</blockquote><small>{{ results[question.id].note }}</small></div></article></section>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { answerReviewQuestion, fetchKnowledgePoints, fetchReviewQuestions } from '../../api/drama'
import { getLineAudioUrl } from '../../api/line'

const props=defineProps({sessionId:{type:String,required:true}})
const points=ref([])
const questions=ref([])
const answers=reactive({})
const results=reactive({})
const loading=ref(false)
const answeringId=ref('')
onMounted(load)
function audioUrl(lineId){return getLineAudioUrl(lineId)}
function apiError(error,fallback){return error?.response?.data?.message||error?.message||fallback}
async function load(){loading.value=true;try{const [pointResponse,questionResponse]=await Promise.all([fetchKnowledgePoints(props.sessionId),fetchReviewQuestions(props.sessionId)]);if(pointResponse.code!==200||questionResponse.code!==200)throw new Error(pointResponse.message||questionResponse.message);points.value=pointResponse.data||[];questions.value=questionResponse.data||[]}catch(error){ElMessage.error(apiError(error,'读取复习内容失败'))}finally{loading.value=false}}
async function submitAnswer(question){answeringId.value=question.id;try{const response=await answerReviewQuestion(props.sessionId,question.id,answers[question.id]);if(response.code!==200)throw new Error(response.message);results[question.id]=response.data;ElMessage.success('答案已保存')}catch(error){ElMessage.error(apiError(error,'保存答案失败'))}finally{answeringId.value=''}}
</script>

<style scoped>
.study-card{display:grid;gap:16px;padding:18px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}header{display:flex;align-items:center;justify-content:space-between;gap:12px}header h3,.eyebrow{margin:0}.eyebrow{margin-bottom:4px;color:var(--el-color-primary);font-size:12px;text-transform:uppercase}.study-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.points,.questions{display:grid;align-content:start;gap:10px}.points h4,.questions h4{margin:0}.points article,.questions article{display:grid;gap:8px;padding:12px;border:1px solid var(--el-border-color-light);border-radius:10px;background:var(--el-fill-color-extra-light)}article p,article blockquote{margin:0;line-height:1.55}article blockquote{padding:8px 10px;border-left:3px solid var(--el-color-primary-light-5);background:var(--el-bg-color);color:var(--el-text-color-secondary)}.related-lines{display:grid;gap:7px}.related-lines span,.answer-result small{color:var(--el-text-color-secondary);font-size:12px}.related-lines audio{width:100%}.answer-result{display:grid;gap:7px;padding-top:8px;border-top:1px solid var(--el-border-color)}@media(max-width:900px){.study-grid{grid-template-columns:1fr}header{align-items:flex-start}}
</style>
