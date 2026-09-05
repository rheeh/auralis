import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const source=await readFile(new URL('./navigation.js',import.meta.url),'utf8')
const {workspaceLocation,resolveWorkspaceView}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
test('deep links keep project, chapter and line identity',()=>{
  assert.deepEqual(workspaceLocation(12,8,'timeline',92),{path:'/projects/12/workspace',query:{chapter_id:'8',view:'timeline',line_id:'92'}})
})
test('viewing earlier stages never changes workflow completion',()=>{
  for(const view of ['source','script','voices','timeline','export'])assert.equal(resolveWorkspaceView(view,'completed',8),view)
})
test('unfinished chapters cannot open production or export',()=>{
  assert.equal(resolveWorkspaceView('export','awaiting_role_confirmation',8),'script')
  assert.equal(resolveWorkspaceView('voices',null,null),'source')
  assert.equal(resolveWorkspaceView('invalid','completed',8),'voices')
})
