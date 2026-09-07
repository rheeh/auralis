import test from 'node:test'
import assert from 'node:assert/strict'
import { groupVoices } from './voiceGroups.js'
test('groups by model, keeps voice identity, prioritizes configured cloud and filters without duplicates',()=>{
 const p=[{id:1,provider_type:'edge',name:'Edge A'},{id:2,provider_type:'edge',name:'Edge B'},{id:3,model:'qwen-audio-3.0-tts-plus',name:'Qwen',custom_params:'{"selection_priority":1}'},{id:4,status:0,model:'disabled'}]
 const v=[{id:1,tts_provider_id:1,name:'小晓'},{id:2,tts_provider_id:2,name:'小晓'},{id:3,tts_provider_id:3,name:'温柔女声'},{id:4,tts_provider_id:4,name:'disabled'}]
 const g=groupVoices(p,v)
 assert.equal(g.length,2);assert.equal(g[0].id,'qwen-audio-3.0-tts-plus');assert.deepEqual(g[1].voices.map(v=>v.id),[1,2]);assert.equal(g[1].edge,true)
 assert.equal(groupVoices(p,v,'温柔')[0].voices[0].id,3)
 assert.equal(groupVoices(p,v,'missing').length,0)
})
