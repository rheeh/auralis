// Mount compiled repository SFCs with Vue's real reactivity/lifecycle. Only
// network, router and unrelated visual components are replaced by test doubles.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

export function workspaceHarness(snapshot) {
  globalThis.Audio = class { pause(){} removeAttribute(){} load(){} addEventListener(){} removeEventListener(){} play(){return Promise.resolve()} }
  globalThis.window = {addEventListener(){},removeEventListener(){}}
  globalThis.sessionStorage = {getItem(){return null}}
  const route=Vue.reactive({params:{id:1},query:{chapter_id:snapshot.chapter_id,view:'script'},path:'/project/1/workspace'})
  const guards={}
  const api={
    IS_STATIC_DEMO:false, getProjectDetail:async()=>({code:200,data:{id:1,name:'测试'}}),
    getChaptersByProject:async()=>({code:200,data:[{id:1},{id:2}]}),
    fetchChatSessions:async()=>({code:200,data:[snapshot]}), fetchChatSession:async()=>({code:200,data:structuredClone(snapshot)}),
    fetchChatHistory:async()=>({code:200,data:[]}), fetchTTSProviders:async()=>[], fetchVoicesByTTS:async()=>[],
    getRolesByProject:async()=>({code:200,data:[]}), getLinesByChapter:async()=>({code:200,data:[{id:1,text_content:'原句',production_note:'原指导'}]}),
    fetchSessionAudioTasks:async()=>({code:200,data:{tasks:[]}}), fetchAllEmotions:async()=>[],fetchAllStrengths:async()=>[],
    fetchChapterProductionConfiguration:async()=>({code:200,data:{lines:[]}}), getRoleAvatarUrl:()=>'', updateLine:async()=>({code:200}),
  }
  const navigation={async replace(location){Object.assign(route,location)},async push(location){Object.assign(route,location)}}
  const box={confirm:async()=>{throw 'cancel'}}
  const stub={setup:(_,ctx)=>()=>Vue.h('stub',ctx.slots.default?.())}
  const cache=new Map()
  const targets=['ProjectWorkspace.vue','RoleDraftConfirmCard.vue','ProductionScriptPanel.vue','SelectedTakeInfo.vue']
  function load(filename) {
    if(cache.has(filename))return cache.get(filename)
    let code=fs.readFileSync(filename,'utf8'), exports=[]
    if(filename.endsWith('.vue')) {
      const {descriptor}=parse(code,{filename})
      const script=compileScript(descriptor,{id:filename,genDefaultAs:'__component'})
      const template=compileTemplate({source:descriptor.template.content,filename,id:filename,compilerOptions:{bindingMetadata:script.bindings}})
      if(template.errors.length)throw template.errors[0]
      code=script.content+'\n'+template.code.replace('export function render','function render')+'\n__component.render=render;__component.__file='+JSON.stringify(filename)+';'
      exports=['default:__component']
    }else{
      code=code.replace(/export (?:async )?(function|const|let|class)\s+(\w+)/g,(all,kind,name)=>{exports.push(name);return all.replace('export ','')})
    }
    const dependencies=[]
    code=code.replace(/import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"];?/g,(_,binding,specifier)=>{
      let value
      if(specifier==='vue')value=Vue
      else if(specifier==='vue-router')value={useRoute:()=>route,useRouter:()=>navigation,onBeforeRouteUpdate:f=>guards.update=f,onBeforeRouteLeave:f=>guards.leave=f}
      else if(specifier==='element-plus')value={ElMessage:{success(){},error(){},warning(){}},ElMessageBox:box}
      else if(specifier.includes('icons-vue'))value=new Proxy({}, {get:()=>stub})
      else if(specifier.includes('/api/'))value=new Proxy(api,{get:(target,key)=>key==='IS_STATIC_DEMO'?target[key]:(...args)=>target[key](...args)})
      else {
        let resolved=path.resolve(path.dirname(filename),specifier)
        if(!path.extname(resolved))resolved+='.js'
        value=resolved.endsWith('.vue')&&!targets.includes(path.basename(resolved))?{default:stub}:load(resolved)
      }
      const index=dependencies.push(value)-1
      return binding.trim().startsWith('{')?`const ${binding.replace(/\bas\b/g,':')}=__deps[${index}];`:`const ${binding}=__deps[${index}].default;`
    })
    const result=new Function('__deps',code+`\nreturn {${exports.join(',')}}`)(dependencies)
    cache.set(filename,result)
    return result
  }
  const node=(type,text='')=>({type,text,children:[],props:{},style:{},parent:null,addEventListener(){},removeEventListener(){},setAttribute(){},removeAttribute(){}})
  const renderer=Vue.createRenderer({
    createElement:node,createText:text=>node('text',text),createComment:text=>node('comment',text),
    setText:(n,text)=>n.text=text,setElementText:(n,text)=>{n.text=text;n.children=[]},
    parentNode:n=>n.parent,nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1],
    patchProp:(n,key,_,value)=>n.props[key]=value,
    insert(n,parent,anchor){if(n.parent)n.parent.children.splice(n.parent.children.indexOf(n),1);n.parent=parent;const i=parent.children.indexOf(anchor);parent.children.splice(i<0?parent.children.length:i,0,n)},
    remove(n){if(n.parent)n.parent.children.splice(n.parent.children.indexOf(n),1)},
  })
  const component=load(fileURLToPath(new URL('../src/pages/ProjectWorkspace.vue',import.meta.url))).default
  const app=renderer.createApp(component)
  app.config.warnHandler=()=>{}
  const root=app.mount(node('root')).$
  function find(name,vnode=root.subTree) {
    if(vnode?.component?.type.__file?.endsWith(name))return vnode.component
    if(vnode?.component){const found=find(name,vnode.component.subTree);if(found)return found}
    for(const child of Array.isArray(vnode?.children)?vnode.children:[]){const found=find(name,child);if(found)return found}
  }
  return {api,route,guards,box,root,find,unmount:()=>app.unmount()}
}
export async function flush(){for(let i=0;i<12;i++){await Promise.resolve();await Vue.nextTick()}}
