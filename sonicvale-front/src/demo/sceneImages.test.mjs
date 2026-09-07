import test from 'node:test'
import assert from 'node:assert/strict'
import { demoSceneSchedule, nativeSceneSchedule, sceneAtTime, sceneImages } from './sceneImages.js'

test('scene switching follows real take timings, including seeking backwards', () => {
  const clips = [{kind:'voice',id:'01',start:.7},{kind:'voice',id:'04',start:14.9},{kind:'voice',id:'08',start:29.3}]
  const scenes = demoSceneSchedule(clips)
  assert.equal(sceneAtTime(scenes,14.899).id,'rain')
  assert.equal(sceneAtTime(scenes,14.9).id,'envelope')
  assert.equal(sceneAtTime(scenes,32).id,'phone')
  assert.equal(sceneAtTime(scenes,0).id,'rain')
  clips[1].start = 17.2
  assert.equal(sceneAtTime(demoSceneSchedule(clips),16).id,'rain')
})

test('native illustration anchors respect edited clip times and reject unrelated stories', () => {
  assert.deepEqual(nativeSceneSchedule([{clips:[{line:{text_content:'别的小说'},start_ms:0}]}]), [])
  const scenes = nativeSceneSchedule([{clips:sceneImages.map((scene,i)=>({line:{text_content:scene.anchorText},start_ms:i*10000}))}])
  assert.equal(sceneAtTime(scenes,10).id,'envelope')
  assert.equal(sceneAtTime(scenes,20).id,'phone')
})

test('missing anchors do not advance a scene prematurely', () => {
  const scenes = demoSceneSchedule([{kind:'voice',id:'01',start:0}])
  assert.equal(sceneAtTime(scenes,50).id,'rain')
  assert.equal(sceneAtTime([],0),null)
})
