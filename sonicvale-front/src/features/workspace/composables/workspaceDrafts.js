import { computed, reactive, ref } from 'vue'

const clone = value => JSON.parse(JSON.stringify(value))
const equal = (a,b) => JSON.stringify(a) === JSON.stringify(b)

// One active chapter, owned by the mounted workspace rather than its views.
// Changing chapters requires the workspace's explicit discard guard.
export function createProductionDrafts() {
  let context = null
  const editMap=reactive({}), editBaseline=reactive({}), promptMap=reactive({}), promptBaseline=reactive({})
  function clear(){for(const map of [editMap,editBaseline,promptMap,promptBaseline])Object.keys(map).forEach(key=>delete map[key]);context=null}
  function activate(next){if(context!==next){clear();context=next}}
  function dirty(){return Object.keys(editMap).some(key=>!equal(editMap[key],editBaseline[key])) || Object.keys(promptMap).some(key=>promptMap[key]!==promptBaseline[key])}
  return {editMap,editBaseline,promptMap,promptBaseline,activate,clear,dirty}
}

export function useRoleDrafts() {
  const roles=ref([]), baseline=ref([]), conflict=ref(false)
  let session=null, revision=null, pending=null
  const dirty=computed(()=>!equal(roles.value,baseline.value))
  function reset(){roles.value=[];baseline.value=[];conflict.value=false;session=null;revision=null;pending=null}
  function accept(sid,rev,incoming){
    const next=clone(incoming)
    if(session!==sid){reset();session=sid;revision=rev;roles.value=next;baseline.value=clone(next);return}
    if(revision!==rev && dirty.value){pending={rev,roles:next};conflict.value=true;return}
    if(!dirty.value)roles.value=next
    baseline.value=clone(next);revision=rev
  }
  function resolve(choice){
    if(!pending)return
    if(choice==='server')roles.value=clone(pending.roles)
    baseline.value=clone(pending.roles);revision=pending.rev;pending=null;conflict.value=false
  }
  function saved(submitted){baseline.value=clone(submitted)}
  return {roles,dirty,conflict,accept,resolve,reset,saved}
}
