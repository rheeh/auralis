import test from 'node:test'
import assert from 'node:assert/strict'
import { workspaceHarness, flush } from './vue-harness.mjs'

function snapshot(stage='completed') {return {session_id:'s1',chapter_id:1,current_stage:stage,pending_confirm:{revision:1},role_drafts:{roles:[{draft_id:'r1',name:'甲',selected:true,default_voice_id:1},{draft_id:'r2',name:'乙',selected:true,default_voice_id:2}]}}}
test('mounted role card keeps dirty edits on same revision and requires a choice on new revision',async()=>{
  const server=snapshot('awaiting_role_confirmation'),h=workspaceHarness(server)
  try{
    await flush()
    const card=h.find('RoleDraftConfirmCard.vue').setupState
    // Trigger the real card's update event, as its voice/checkbox controls do.
    if(card.updateRole){card.updateRole('r1',{default_voice_id:9});await flush();card.updateRole('r2',{selected:false})}
    else {card.editableRoles[0].default_voice_id=9;card.editableRoles[1].selected=false}
    await flush();await h.root.setupState.refresh();await flush()
    assert.equal(h.find('RoleDraftConfirmCard.vue').setupState.editableRoles[0].default_voice_id,9)
    assert.equal(h.root.setupState.roleEdits[1].selected,false)
    server.pending_confirm.revision=2;server.role_drafts.roles[0].default_voice_id=3
    await h.root.setupState.refresh();await flush()
    assert.equal(h.root.setupState.roleConflict,true)
    assert.equal(h.root.setupState.roleEditsReady,false)
    h.root.setupState.resolveRoleConflict('server');await flush()
    assert.equal(h.root.setupState.roleEdits[0].default_voice_id,3)
  }finally{h.unmount()}
})
test('mounted save A response preserves newer B and confirms only A',async()=>{
  const h=workspaceHarness(snapshot())
  try{
    await flush();const panel=h.find('ProductionScriptPanel.vue').setupState
    let resolve
    h.api.updateLine=()=>new Promise(r=>{resolve=r})
    panel.editMap[1].text_content='A'
    const saving=panel.saveLine(panel.lines[0]);await flush()
    panel.editMap[1].text_content='B'
    h.api.getLinesByChapter=async()=>({code:200,data:[{id:1,text_content:'A',production_note:'原指导'}]})
    resolve({code:200});await saving;await flush()
    assert.equal(panel.editMap[1].text_content,'B')
    assert.equal(panel.editBaseline[1].text_content,'A')
  }finally{h.unmount()}
})
test('mounted view changes retain chapter draft; chapter navigation requires explicit discard',async()=>{
  const h=workspaceHarness(snapshot())
  try{
    await flush();h.find('ProductionScriptPanel.vue').setupState.editMap[1].text_content='未保存'
    for(const view of ['voices','timeline','script']){h.route.query.view=view;await flush()}
    assert.equal(h.find('ProductionScriptPanel.vue').setupState.editMap[1].text_content,'未保存')
    const next={params:{id:1},query:{chapter_id:2}}
    assert.equal(await h.guards.update(next,h.route),false)
    h.box.confirm=async()=>{}
    assert.equal(await h.guards.update(next,h.route),true)
    const second={...snapshot(),session_id:'s2',chapter_id:2}
    h.api.fetchChatSessions=async()=>({code:200,data:[snapshot(),second]})
    h.api.fetchChatSession=async id=>({code:200,data:structuredClone(id==='s2'?second:snapshot())})
    h.api.getLinesByChapter=async id=>({code:200,data:[{id,text_content:id===2?'另一章原句':'原句',production_note:'原指导'}]})
    h.route.query.chapter_id=2;await flush()
    // Only one chapter's draft is kept; previous edits cannot leak to chapter 2.
    assert.equal(h.root.setupState.snapshot.chapter_id,2)
    assert.equal(h.find('ProductionScriptPanel.vue').setupState.editMap[2].text_content,'另一章原句')
    assert.equal(Object.hasOwn(h.find('ProductionScriptPanel.vue').setupState.editMap,1),false)
    assert.equal(h.root.setupState.productionDrafts.dirty(),false)
  }finally{h.unmount()}
})
test('regeneration conflict preserves guidance and displays the running input',async()=>{
  const h=workspaceHarness(snapshot())
  try{
    h.api.regenerateLineAudio=async()=>{throw {response:{status:409,data:{code:409,message:'新指导未保存',data:{task_id:'A',status:'processing',input_snapshot:{prepared:{production_note:'旧指导 A'}}}}}}}
    await flush();const panel=h.find('ProductionScriptPanel.vue').setupState
    panel.promptMap[1]='新指导 B'
    await panel.regenerate(panel.lines[0]);await flush()
    assert.equal(panel.promptMap[1],'新指导 B')
    assert.equal(panel.regenerationConflicts[1].task_id,'A')
    assert.match(panel.regenerationConflictText(1),/旧指导 A/)
  }finally{h.unmount()}
})
test('mounted take labels use resolved source instead of missing processed metadata',async()=>{
  const h=workspaceHarness(snapshot())
  try{
    h.api.getLinesByChapter=async()=>({code:200,data:[{id:1,text_content:'原句',track:'voice',should_speak:1,
      active_audio_version_id:'B',active_audio_variant_id:'missing',audio_variants:[{id:'missing',source_audio_version_id:'B'}],
      audio_versions:[{id:'A',text:'A 的文本'},{id:'B',text:'B 的文本'}]}]})
    h.api.fetchChapterProductionConfiguration=async()=>({code:200,data:{lines:[{line_id:1,has_audio:true,input_current:false,selected_version_id:'A',selected_variant_id:null,audio_resolution:{fallback_reason:'selected_variant_missing'}}]}})
    await flush();const panel=h.find('ProductionScriptPanel.vue').setupState
    assert.equal(panel.activeGeneratedVersionId(panel.lines[0]),'A')
    assert.equal(panel.activeVariant(panel.lines[0]),null)
    assert.equal(h.find('SelectedTakeInfo.vue').setupState.take.text,'A 的文本')
  }finally{h.unmount()}
})
