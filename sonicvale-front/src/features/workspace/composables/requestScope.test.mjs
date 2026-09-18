import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequestScope, mergeDraft } from './requestScope.js'

test('A response cannot write after switching to B or disposing', async () => {
  let key='A', current=''
  const scope=createRequestScope(()=>key)
  const a=scope.begin();key='B';const b=scope.begin()
  if(scope.current(b))current='B'
  if(scope.current(a))current='A'
  assert.equal(current,'B')
  scope.dispose();assert.equal(scope.current(b),false)
})
test('a later request in the same chapter supersedes an earlier request',()=>{
  const scope=createRequestScope(()=>1)
  const a=scope.begin(),b=scope.begin()
  assert.equal(scope.current(a),false);assert.equal(scope.current(b),true)
})
test('polling preserves unsaved input but updates a clean draft',()=>{
  assert.deepEqual(mergeDraft({text:'editing'},{text:'saved'},{text:'server'}),{text:'editing'})
  assert.deepEqual(mergeDraft({text:'saved'},{text:'saved'},{text:'server'}),{text:'server'})
})

test('operation context survives polling but not navigation',()=>{
  let key='A';const scope=createRequestScope(()=>key);const operation=scope.capture()
  scope.begin();scope.begin();assert.equal(scope.sameContext(operation),true)
  scope.invalidate();assert.equal(scope.sameContext(operation),false)
})
