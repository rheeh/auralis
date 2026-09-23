<template>
    <el-dialog v-model="visible" title="修改台词类型与角色" width="min(520px,92vw)" :close-on-click-modal="!typeSaving" :close-on-press-escape="!typeSaving" :show-close="!typeSaving">
      <el-form label-position="top">
        <el-form-item label="台词类型"><el-select v-model="typeForm.track" aria-label="台词类型"><el-option label="人物台词（含角色笑声、叹气）" value="voice" /><el-option label="旁白" value="narration" /><el-option label="音效（环境、群体反应）" value="sfx" /><el-option label="背景音乐" value="bgm" /></el-select></el-form-item>
        <el-form-item v-if="typeIsSpoken" label="发声角色"><el-select v-model="typeForm.role_id" filterable aria-label="发声角色" placeholder="选择当前项目的角色"><el-option v-for="role in typeRoleOptions" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item>
        <el-form-item :label="typeIsSpoken?'实际发声文字':'声音描述'"><el-input v-model="typeForm.text_content" type="textarea" :rows="3" aria-label="转换后的台词文本" /></el-form-item>
        <p v-if="typeIsSpoken" class="type-editor-hint">独立轻笑可写“呵。”，大笑可写“哈哈。”；“自然轻笑、不要念说明”放在下方，保留该角色声线。</p>
        <el-form-item label="声音指导"><el-input v-model="typeForm.production_note" type="textarea" :rows="2" aria-label="转换后的声音指导" /></el-form-item>
        <p class="type-editor-hint">原音频与修改前记录会保留；保存后本句需重新配音或选用素材，声音编排会标记待刷新。</p>
      </el-form>
      <template #footer><el-button :disabled="typeSaving" @click="visible=false">取消</el-button><el-button type="primary" :loading="typeSaving" @click="saveTypeChange">保存类型修改</el-button></template>
    </el-dialog>
</template>

<script setup>
import {computed,reactive,ref,watch,onBeforeUnmount} from 'vue'
import {ElMessage} from 'element-plus'
import {getRolesByProject} from '../../api/role'
import {changeLineType} from '../../api/line'
const props=defineProps({modelValue:Boolean,line:Object,projectId:Number,chapterId:Number})
const emit=defineEmits(['update:modelValue','saved'])
const visible=computed({get:()=>props.modelValue,set:value=>emit('update:modelValue',value)})
const typeSaving=ref(false),roles=ref([])
const typeForm=reactive({track:'voice',role_id:null,text_content:'',production_note:''})
const typeIsSpoken=computed(()=>['voice','narration'].includes(typeForm.track))
const typeRoleOptions=computed(()=>roles.value.filter(role=>!['音效','BGM','背景音乐','环境音'].includes(role.name)))
let epoch=0
onBeforeUnmount(()=>epoch++)
watch(()=>[props.modelValue,props.line?.id,props.projectId,props.chapterId],async()=>{
  const operation=++epoch
  typeSaving.value=false
  if(!props.modelValue||!props.line)return
  const line=props.line
  Object.assign(typeForm,{track:line.track||line.line_type||'voice',role_id:line.role_id||null,text_content:line.text_content||'',production_note:line.production_note||line.sound_prompt||''})
  roles.value=[]
  try{
    const response=await getRolesByProject(props.projectId)
    if(operation!==epoch)return
    if(response?.code!==200)throw new Error(response?.message||'读取角色失败')
    roles.value=response.data||[]
    if(!typeRoleOptions.value.some(role=>role.id===typeForm.role_id))typeForm.role_id=null
  }catch(error){if(operation===epoch)ElMessage.error(error?.message||'读取角色失败')}
},{immediate:true})
async function saveTypeChange(){
  if(!typeForm.text_content.trim())return ElMessage.warning('请填写台词文本或声音描述')
  if(typeIsSpoken.value&&!typeForm.role_id)return ElMessage.warning('请选择发声角色')
  const operation=epoch
  typeSaving.value=true
  try{
    const response=await changeLineType(props.line.id,{...typeForm,chapter_id:props.chapterId,role_id:typeIsSpoken.value?typeForm.role_id:null})
    if(operation!==epoch)return
    if(response?.code!==200)throw new Error(response?.message||'修改失败')
    emit('saved');visible.value=false
    ElMessage.success('已修改类型；请重新配音或选择素材，原音频保留')
  }catch(error){if(operation===epoch)ElMessage.error(error?.response?.data?.detail||error?.response?.data?.message||error?.message||'修改失败')}
  finally{if(operation===epoch)typeSaving.value=false}
}
</script>
<style scoped>.type-editor-hint{font-size:12px;color:var(--el-text-color-secondary);line-height:1.6}</style>
