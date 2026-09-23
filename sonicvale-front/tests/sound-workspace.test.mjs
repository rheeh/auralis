import test from 'node:test'
import assert from 'node:assert/strict'
import {workspaceHarness,flush} from './vue-harness.mjs'

const snapshot={session_id:'s1',chapter_id:1,current_stage:'completed'}
const lines=[
  {id:1,line_order:1,track:'sfx',should_speak:0,text_content:'雨声持续铺底',sound_prompt:'雨声持续铺底'},
  {id:2,line_order:2,track:'bgm',should_speak:0,text_content:'轻柔钢琴'},
  {id:3,line_order:3,track:'voice',should_speak:1,text_content:'雨停了吗？'},
  {id:4,line_order:4,track:'narration',should_speak:1,text_content:'两人望向窗外。'},
]
const api={getLinesByChapter:async()=>({code:200,data:structuredClone(lines)})}

test('script and voices show spoken text only without deleting sound cues',async()=>{
  const h=workspaceHarness(snapshot,{api})
  try{
    await flush()
    for(const view of ['script','voices']){
      h.route.query.view=view;await flush()
      const panel=h.find('ProductionScriptPanel.vue').setupState
      assert.deepEqual(panel.scenes.flatMap(scene=>scene.lines.map(line=>line.id)),[3,4])
      assert.equal(panel.lines.length,4)
      assert.equal(h.elements('article').filter(node=>node.props['data-line-id']).length,2)
      assert.equal(h.elements('button').filter(node=>String(node.props.class).includes('round-play')).length,view==='script'?0:2)
    }
  }finally{h.unmount()}
})

test('arrangement shows bound sound previews, missing cues and long background editing',async()=>{
  const clip={id:11,line_id:1,track_type:'sfx',start_ms:0,duration_ms:60000,asset:{duration_ms:10000},line:lines[0]}
  const timeline={status:'ready',duration_ms:60000,clip_count:2,audio_sources:{1:{available:true},2:{available:false}},tracks:[
    {track_type:'sfx',clips:[clip]},
    {track_type:'voice',clips:[{id:13,line_id:3,track_type:'voice',start_ms:0,duration_ms:90000,line:lines[2]}]},
  ]}
  const changes=[]
  const h=workspaceHarness(snapshot,{view:'timeline',targets:['ChapterTimeline.vue','ChapterSoundMaterials.vue','LineTypeDialog.vue'],api:{...api,
    fetchChapterTimeline:async()=>({code:200,data:timeline}),fetchLatestTimelineRender:async()=>({code:404}),
    getLineAudioUrl:id=>`/test-audio/${id}`,
    getRolesByProject:async()=>({code:200,data:[{id:9,name:'小林'}]}),
    changeLineType:async(id,payload)=>{changes.push({id,...payload});return {code:200}},
  }})
  try{
    await flush()
    const sounds=h.find('ChapterSoundMaterials.vue')
    assert.ok(sounds,'sound cues should be directly available in arrangement')
    const audio=h.elements('audio').find(node=>node.props['aria-label']==='试听音效：雨声持续铺底')
    assert.equal(audio?.props.src,'/test-audio/1')
    assert.equal(h.elements('audio').some(node=>node.props.src==='/test-audio/2'),false)
    sounds.emit('edit',lines[0]);await flush()
    const editor=h.find('ChapterTimeline.vue').setupState
    assert.equal(editor.clipForm.duration_ms,60000)
    editor.coverSpeech()
    assert.equal(editor.clipForm.duration_ms,90000)
    sounds.emit('edit-type',lines[1]);await flush()
    const typeEditor=h.find('LineTypeDialog.vue').setupState
    assert.equal(typeEditor.typeForm.track,'bgm')
    Object.assign(typeEditor.typeForm,{track:'voice',role_id:9,text_content:'呵。'})
    await typeEditor.saveTypeChange();await flush()
    assert.deepEqual(changes,[{id:2,chapter_id:1,track:'voice',role_id:9,text_content:'呵。',production_note:''}])
    assert.equal(audio.paused,true,'refresh stops the previous audio element')
    const currentAudio=h.elements('audio').find(node=>node.props.src==='/test-audio/1')
    currentAudio.paused=false
    h.route.query.view='voices';await flush()
    assert.equal(currentAudio.paused,true,'leaving arrangement stops preview playback')
  }finally{h.unmount()}
})

test('refreshing the timeline also refreshes newly added sound cues',async()=>{
  const rows=[lines[2]]
  const data={status:'ready',tracks:[],clip_count:0,audio_sources:{}}
  const h=workspaceHarness(snapshot,{view:'timeline',targets:['ChapterTimeline.vue','ChapterSoundMaterials.vue'],api:{
    getLinesByChapter:async()=>({code:200,data:structuredClone(rows)}),
    fetchChapterTimeline:async()=>({code:200,data}),buildChapterTimeline:async()=>({code:200,data}),
  }})
  try{
    await flush();rows.push(lines[0])
    const editor=h.find('ChapterTimeline.vue').setupState
    await editor.rebuildTimeline(true);await flush()
    assert.equal(editor.materialLines.length,1)
  }finally{h.unmount()}
})
