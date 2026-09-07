<template>
  <section class="sound-matches" aria-label="标签匹配音效">
    <div class="match-heading"><div><strong>按这段声音的标签找素材</strong><p>解析台本时生成标签，选素材时直接匹配；可修改标签或去素材库自己挑选。</p></div><el-button @click="$emit('browse')">去音效库挑选</el-button></div>
    <div class="tag-controls">
      <el-select v-model="tags" multiple filterable allow-create default-first-option :multiple-limit="12" aria-label="音效检索标签" placeholder="输入声源、材质或场景标签" :disabled="loading" @change="search">
        <el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" />
      </el-select>
      <el-button :disabled="!lineId || loading" :loading="saving" @click="save">保存到台本</el-button>
    </div>
    <small v-if="result">{{ sourceLabel }} · 本地标签检索 · {{ result.candidate_count }} 个素材</small>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
    <p v-if="!lineId">先选择音效或定位台词。</p>
    <div v-if="loading" role="status">正在匹配素材…</div>
    <template v-else-if="result">
      <el-alert v-if="result.missing_tags.length" :title="`库内暂无这些条件：${result.missing_tags.join('、')}，可以调整标签或导入素材。`" type="info" :closable="false" />
      <article v-for="asset in result.matches" :key="asset.id" class="match-card">
        <div class="choice-title"><strong>{{ asset.name }}</strong><span>{{ (asset.duration_ms / 1000).toFixed(1) }} 秒</span></div>
        <div class="matched-tags"><el-tag v-for="tag in asset.matched_tags" :key="tag" size="small" type="success">{{ tag }}</el-tag></div>
        <small v-if="asset.missing_tags.length">部分匹配 · 还缺 {{ asset.missing_tags.join('、') }}</small><small v-else>全部检索标签命中 · 请试听确认具体节奏与听感</small>
        <div class="choice-actions"><audio controls preload="none" :src="getSoundLibraryAudioUrl(asset.id)" :aria-label="`试听匹配：${asset.name}`" /><el-button type="primary" :disabled="Boolean(busyId)" :loading="busyId === asset.id" @click="$emit('select', {asset_id:asset.id,asset,placement:'with',volume_db:-12})">{{ actionMode === 'bind' ? '选用并替换此音效' : '选用并加入此处' }}</el-button></div>
      </article>
      <el-empty v-if="!result.matches.length" :description="tags.length ? '没有匹配素材，试试其他标签或去素材库挑选。' : '暂未提取到声音标签，可以手动添加。'" />
    </template>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getSoundLibraryAudioUrl, matchSounds, saveSoundTags } from '../api/soundLibrary'
const props=defineProps({chapterId:Number,lineId:Number,actionMode:String,busyId:String})
defineEmits(['browse','select'])
const tags=ref([]),availableTags=ref([]),loading=ref(false),saving=ref(false),error=ref(''),result=ref(null)
const sourceLabel=computed(()=>({script:'台本标签',local:'旧台本本地提取',custom:'自定义标签'}[result.value?.tag_source]||''))
let version=0
async function search(initial=false){
 const token=++version; error.value=''; result.value=null; loading.value=false
 if(!props.chapterId||!props.lineId)return
 loading.value=true
 try{
  const response=await matchSounds({chapter_id:props.chapterId,line_id:props.lineId,...(initial===true?{}:{tags:tags.value})})
  if(token!==version)return
  if(response?.code!==200)throw new Error(response?.message||'匹配失败')
  result.value=response.data;tags.value=response.data.tags;availableTags.value=response.data.available_tags
 }catch(e){if(token===version)error.value=e?.response?.data?.detail||'素材匹配暂时不可用，请去音效库挑选。'}
 finally{if(token===version)loading.value=false}
}
async function save(){
 const token=version; saving.value=true
 try{const response=await saveSoundTags({chapter_id:props.chapterId,line_id:props.lineId,tags:tags.value});if(token!==version)return;if(response?.code!==200)throw new Error();ElMessage.success('标签已保存，下次直接复用')}
 catch(e){if(token===version)error.value=e?.response?.data?.detail||'标签保存失败'}finally{saving.value=false}
}
watch(()=>[props.chapterId,props.lineId],()=>search(true),{immediate:true})
onBeforeUnmount(()=>{++version})
</script>
<style scoped>
.sound-matches{display:grid;gap:14px}.match-heading,.tag-controls,.choice-title,.choice-actions,.matched-tags{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.match-heading{justify-content:space-between}.match-heading p{font-size:12px;line-height:1.7;color:var(--el-text-color-secondary);margin:7px 0}.tag-controls .el-select{flex:1;min-width:220px}.match-card{display:grid;gap:10px;padding:16px;border:1px solid var(--el-border-color);border-radius:12px;background:var(--el-bg-color)}small,.choice-title span{font-size:12px;color:var(--el-text-color-secondary)}.choice-actions{justify-content:space-between}.choice-actions audio{width:min(320px,100%);height:38px}
</style>
