import test from 'node:test'
import assert from 'node:assert/strict'
import {handleDemoRequest} from './mockApi.js'
test('unknown Demo endpoints fail explicitly',async()=>{
  await assert.rejects(handleDemoRequest({method:'post',url:'/unimplemented-action'}),/不支持|未实现/)
})
test('Demo generation actions cannot pretend to generate audio',async()=>{
  await assert.rejects(handleDemoRequest({method:'post',url:'/chat/sessions/sess_57786eca321d46f198d50d479aedd63a/audio-tasks/generate'}),/预生成|实时/)
})
