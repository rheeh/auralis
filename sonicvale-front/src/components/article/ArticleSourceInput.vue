<template>
  <section class="article-source-card">
    <div class="panel-heading"><div><p class="eyebrow">文章来源</p><h2>导入并确认正文</h2></div><el-tag v-if="confirmedSource" type="success" effect="plain">正文已确认</el-tag></div>
    <el-tabs v-model="inputMethod" @tab-change="resetPreview">
      <el-tab-pane label="公众号链接" name="url">
        <el-input v-model="sourceUrl" placeholder="https://mp.weixin.qq.com/s/..." clearable />
        <p class="input-help">若微信返回验证页或需要登录，系统会提示粘贴正文，不会把验证页当作文章。</p>
      </el-tab-pane>
      <el-tab-pane label="粘贴正文" name="paste"><el-input v-model="sourceText" type="textarea" :rows="12" resize="none" placeholder="粘贴完整文章正文" /></el-tab-pane>
    </el-tabs>
    <el-alert v-if="errorMessage" :title="errorMessage" type="warning" show-icon :closable="false"><template #default><el-button v-if="inputMethod==='url'" size="small" @click="inputMethod='paste';resetPreview()">改为粘贴正文</el-button></template></el-alert>
    <div class="preview-actions"><span>{{ inputMethod==='paste' ? `${sourceText.trim().length} 字` : '预览不会启动 AI 改编' }}</span><el-button :loading="isPreviewing" :disabled="!canPreview" @click="previewSource">预览和清洗</el-button></div>
    <section v-if="preview" class="article-preview">
      <div class="preview-meta"><el-input v-model="preview.title" placeholder="文章标题" /><div><span v-if="preview.author">作者：{{ preview.author }}</span><span v-if="preview.account_name">来源：{{ preview.account_name }}</span><span>{{ preview.content_chars }} 字</span></div></div>
      <el-input v-model="preview.normalized_content" type="textarea" :rows="14" resize="vertical" />
      <el-checkbox v-model="rightsConfirmed">我确认有权使用导入内容进行本地改编</el-checkbox>
      <div class="confirm-row"><small>请确认这里显示的正文确实是你要处理的文章。</small><el-button type="primary" :loading="isImporting" :disabled="!rightsConfirmed || !preview.normalized_content.trim()" @click="confirmSource">确认正文</el-button></div>
    </section>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { importArticleSource, previewArticleSource } from '../../api/drama'

const props=defineProps({projectId:Number,urlEnabled:{type:Boolean,default:false}})
const emit=defineEmits(['confirmed'])
const inputMethod=ref(props.urlEnabled?'url':'paste')
const sourceUrl=ref('')
const sourceText=ref('')
const preview=ref(null)
const rightsConfirmed=ref(false)
const isPreviewing=ref(false)
const isImporting=ref(false)
const errorMessage=ref('')
const confirmedSource=ref(null)
const canPreview=computed(()=>props.projectId && (inputMethod.value==='url'?sourceUrl.value.trim():sourceText.value.trim()))
function resetPreview(){preview.value=null;rightsConfirmed.value=false;errorMessage.value='';confirmedSource.value=null}
function apiError(error,fallback){return error?.response?.data?.message||error?.message||fallback}
async function previewSource(){
  isPreviewing.value=true;errorMessage.value='';confirmedSource.value=null
  try{const payload={project_id:props.projectId,input_method:inputMethod.value};if(inputMethod.value==='url')payload.source_url=sourceUrl.value.trim();else payload.source_text=sourceText.value;const response=await previewArticleSource(payload);if(response.code!==200)throw new Error(response.message||'文章预览失败');preview.value=response.data}
  catch(error){preview.value=null;errorMessage.value=apiError(error,'文章预览失败，请粘贴正文继续')}
  finally{isPreviewing.value=false}
}
async function confirmSource(){
  isImporting.value=true
  try{const response=await importArticleSource({project_id:props.projectId,input_method:inputMethod.value,source_url:preview.value.source_url,title:preview.value.title,author:preview.value.author,account_name:preview.value.account_name,source_text:preview.value.normalized_content,raw_content:preview.value.raw_content,rights_confirmed:rightsConfirmed.value});if(response.code!==200)throw new Error(response.message||'保存文章来源失败');confirmedSource.value=response.data;emit('confirmed',response.data);ElMessage.success('文章正文已确认')}
  catch(error){ElMessage.error(apiError(error,'保存文章来源失败'))}
  finally{isImporting.value=false}
}
</script>

<style scoped>
.article-source-card{display:grid;gap:12px;padding:16px;border:1px solid var(--el-border-color-light);border-radius:12px;background:var(--el-bg-color);box-shadow:0 14px 34px rgba(17,24,39,.06)}.panel-heading,.preview-actions,.confirm-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.panel-heading h2,.eyebrow{margin:0}.panel-heading h2{font-size:18px}.eyebrow{margin-bottom:4px;color:var(--el-color-primary);font-size:12px;text-transform:uppercase}.input-help,.preview-actions span,.confirm-row small{margin:7px 0 0;color:var(--el-text-color-secondary);font-size:12px;line-height:1.5}.article-preview{display:grid;gap:12px;padding-top:12px;border-top:1px solid var(--el-border-color-light)}.preview-meta{display:grid;gap:8px}.preview-meta>div{display:flex;flex-wrap:wrap;gap:12px;color:var(--el-text-color-secondary);font-size:12px}@media(max-width:720px){.panel-heading,.preview-actions,.confirm-row{align-items:flex-start;flex-direction:column}}
</style>
