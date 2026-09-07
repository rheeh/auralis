import test from 'node:test'
import assert from 'node:assert/strict'
import {dragClip, alignClip, packClipLanes, changeClipRate, playableSourceDuration} from './timelineEditing.js'
const material={id:1,track_type:'bgm',start_ms:1000,duration_ms:2000,asset:{duration_ms:2000},fade_in_ms:1000,fade_out_ms:1000}
test('material boundaries extend beyond source, speech cannot, fades stay valid',()=>{
 assert.equal(dragClip(material,'resize-right',5000,[],false).duration_ms,7000)
 assert.equal(dragClip({...material,track_type:'voice'},'resize-right',5000,[],false).duration_ms,2000)
 assert.equal(dragClip(material,'resize-left',-1000,[],false).duration_ms,3000)
 assert.equal(dragClip({...material,track_type:'voice'},'resize-left',-1000,[],false).start_ms,1000)
 const short=dragClip(material,'resize-right',-1500,[],false)
 assert.equal(short.fade_in_ms+short.fade_out_ms,short.duration_ms)
})
test('move snaps either edge, ignores itself, and Alt-equivalent bypasses snapping',()=>{
 const target={id:2,start_ms:5000,duration_ms:1000}
 assert.equal(dragClip(material,'move',2020,[material,target],true,80).start_ms,3000)
 assert.equal(dragClip(material,'move',3980,[target],true,80).start_ms,5000)
 assert.equal(dragClip(material,'move',2020,[target],false,80).start_ms,3020)
 assert.equal(dragClip(material,'move',-5000,[],false).start_ms,0)
})
test('reference alignment covers start, end, consecutive and span',()=>{
 const ref={start_ms:5000,duration_ms:4000}
 assert.equal(alignClip(material,ref,'start').start_ms,5000)
 assert.equal(alignClip(material,ref,'end').start_ms,7000)
 assert.equal(alignClip(material,ref,'after').start_ms,9000)
 assert.equal(alignClip(material,ref,'span').duration_ms,4000)
 assert.throws(()=>alignClip({...material,track_type:'voice'},ref,'span'))
 assert.throws(()=>alignClip(material,{start_ms:0,duration_ms:100},'end'))
})
test('overlapping clips occupy separate visible lanes, touching edges reuse lane',()=>{
 const result=packClipLanes([{id:1,start_ms:0,duration_ms:1000},{id:2,start_ms:100,duration_ms:500},{id:3,start_ms:1000,duration_ms:50}])
 assert.equal(result.count,2);assert.deepEqual(result.lanes,{1:0,2:1,3:0})
})

test('speed rescales duration and fades, preserves start and loop count',()=>{
 const slow=changeClipRate(material,0.5)
 assert.equal(slow.duration_ms,4000)
 assert.equal(slow.fade_in_ms,2000)
 assert.equal(playableSourceDuration({...material,...slow}),4000)
 assert.equal(changeClipRate({...material,...slow},1).duration_ms,2000)
 assert.equal(changeClipRate({...material,duration_ms:6000},2).duration_ms,3000)
 assert.throws(()=>changeClipRate(material,0.25))
})
