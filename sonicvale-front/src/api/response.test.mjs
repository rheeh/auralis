import test from 'node:test'
import assert from 'node:assert/strict'
import { unwrapResponse, normalizeError } from './response.js'
test('legacy 200 business errors throw while accepted 202 remains success',()=>{
 assert.throws(()=>unwrapResponse({code:409,message:'冲突'}),/冲突/)
 assert.equal(unwrapResponse({code:202,data:1}).data,1)
 assert.equal(normalizeError({response:{data:{detail:'拒绝'}}}).message,'拒绝')
})
