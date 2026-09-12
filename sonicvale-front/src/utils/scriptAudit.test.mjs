import test from 'node:test'
import assert from 'node:assert/strict'
import { scriptAudit } from './scriptAudit.js'

test('long and consecutive narration remains descriptive, without a quality verdict', () => {
  const result = scriptAudit({ scenes: [{ lines: [
    { type: 'narration', track: 'voice', text: '三年后，他再次回到这里。'.repeat(10) },
    { type: 'sfx', text: '风' }, { type: 'narration', text: '车站停用了。' },
  ] }] })
  assert.equal(result.narrationRatio, 100)
  assert.equal(result.dialogueCount, 0)
  assert.equal(result.soundCount, 1)
  assert.equal(result.hasIssues, undefined)
  assert.match(result.message, /仅供参考/)
})

test('empty or mixed scripts return bounded factual metrics', () => {
  assert.equal(scriptAudit(null).narrationRatio, 0)
  assert.equal(scriptAudit({ scenes: [{ lines: [{ track: 'voice', text: '你好' }, { track: 'narration', text: '夜晚' }] }] }).narrationRatio, 50)
})
