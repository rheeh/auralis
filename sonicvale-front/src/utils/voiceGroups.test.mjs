import test from 'node:test'
import assert from 'node:assert/strict'
import { groupVoices, voiceStyle } from './voiceGroups.js'
test('groups by model, keeps voice identity, prioritizes configured cloud and filters without duplicates',()=>{
 const p=[{id:1,provider_type:'edge',name:'Edge A'},{id:2,provider_type:'edge',name:'Edge B'},{id:3,model:'qwen-audio-3.0-tts-plus',name:'Qwen',custom_params:'{"selection_priority":1}'},{id:4,status:0,model:'disabled'}]
 const v=[{id:1,tts_provider_id:1,name:'小晓'},{id:2,tts_provider_id:2,name:'小晓'},{id:3,tts_provider_id:3,name:'温柔女声'},{id:4,tts_provider_id:4,name:'disabled'}]
 const g=groupVoices(p,v)
 assert.equal(g.length,2);assert.equal(g[0].id,'qwen-audio-3.0-tts-plus');assert.deepEqual(g[1].voices.map(v=>v.id),[1,2]);assert.equal(g[1].edge,true)
 assert.equal(groupVoices(p,v,'温柔')[0].voices[0].id,3)
 assert.equal(groupVoices(p,v,'missing').length,0)
})
test('dialogue comes first; narration and unreviewed clones are never labelled natural dialogue',()=>{
 const providers=[{id:6,model:'qwen-audio-3.0-tts-plus'}]
 const voices=[{id:1,name:'电台质感音',description:'日常对话',tts_provider_id:6},{id:2,name:'内敛男声',tts_provider_id:6},{id:3,name:'复刻 A',description:'自然',tts_provider_id:6},{id:4,name:'活泼女声',tts_provider_id:6}]
 assert.equal(voiceStyle(voices[0]),'narration')
 assert.equal(voiceStyle(voices[2]),'unrated')
 assert.equal(voiceStyle({name:'质朴女声',description:'日常对话,原生表演指令,qwen_voice:model-id'}),'dialogue')
 assert.deepEqual(groupVoices(providers,voices)[0].voices.map(v=>v.id),[2,4,3,1])
 assert.deepEqual(groupVoices(providers,voices,'','dialogue')[0].voices.map(v=>v.id),[2])
 assert.equal(groupVoices(providers,voices,'电台','dialogue').length,0)
 assert.deepEqual(voices.map(v=>v.id),[1,2,3,4])
})
