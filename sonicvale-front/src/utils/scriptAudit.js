// Descriptive counts never decide whether narration has dramatic value.
export function scriptAudit(script) {
  const lines = (script?.scenes || []).flatMap(scene => scene.lines || [])
  const type = line => line.type || ({ voice: 'dialogue', narration: 'narration', sfx: 'sfx', bgm: 'bgm' }[line.track])
  const dialogue = lines.filter(line => type(line) === 'dialogue')
  const narration = lines.filter(line => type(line) === 'narration')
  const count = rows => rows.reduce((sum, line) => sum + String(line.text || '').replace(/\s/g, '').length, 0)
  const spoken = count(dialogue) + count(narration)
  return { dialogueCount: dialogue.length, narrationRatio: spoken ? Math.round(count(narration) * 100 / spoken) : 0,
    soundCount: lines.filter(line => ['sfx', 'bgm'].includes(type(line))).length,
    message: '旁白比例仅供参考；请按叙事功能、信息是否重复和听觉节奏审阅。' }
}
