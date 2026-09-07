export function providerOptions(provider) {
  try { return typeof provider?.custom_params === 'object' ? provider.custom_params || {} : JSON.parse(provider?.custom_params || '{}') } catch { return {} }
}
export const voiceStyles = [
  { id: 'all', label: '全部' },
  { id: 'dialogue', label: '自然对白' },
  { id: 'character', label: '角色表演' },
  { id: 'narration', label: '旁白 / 电台' },
  { id: 'unrated', label: '复刻待试听' },
]
// These are catalog-based browsing hints, not listening-quality ratings.
export function voiceStyle(voice) {
  const tags = (voice.description || '').split(',').filter(tag => !tag.includes(':') && !/指令/.test(tag)).join(' ')
  const text = `${voice.name || ''} ${tags}`
  if (/复刻/.test(text)) return 'unrated'
  if (/播音|电台|朗读|朗诵|有声阅读|旁白/.test(text)) return 'narration'
  if (/活泼|灵动|甜美|川普|低沉压抑|表演/.test(text)) return 'character'
  if (/日常对话|自然|亲和|内敛|质朴|直爽|爽朗/.test(text)) return 'dialogue'
  return 'other'
}
export function groupVoices(providers, voices, query = '', style = 'all') {
  const groups = new Map()
  for (const provider of providers) {
    if (provider.status === 0) continue
    const model = provider.provider_type === 'edge' ? 'edge' : provider.model || provider.name
    const options = providerOptions(provider)
    if (!groups.has(model)) groups.set(model, { id: model, label: model === 'edge' ? 'Edge · 免费基础配音' : model, edge: model === 'edge', priority: options.selection_priority ?? (model.includes('qwen-audio') ? 10 : model === 'edge' ? 80 : 50), note: options.selection_note || '', voices: [] })
    const group = groups.get(model)
    group.voices.push(...voices.filter(v => v.tts_provider_id === provider.id).map(v => ({ ...v, providerName: provider.name })))
  }
  const needle = query.trim().toLowerCase()
  const priority = { dialogue: 0, character: 1, unrated: 2, other: 3, narration: 4 }
  return [...groups.values()].map(g => ({ ...g, total: g.voices.length, voices: g.voices
    .filter(v => (style === 'all' || voiceStyle(v) === style) && (!needle || `${v.name} ${v.description || ''} ${g.label}`.toLowerCase().includes(needle)))
    .sort((a, b) => priority[voiceStyle(a)] - priority[voiceStyle(b)])
  })).filter(g => g.voices.length).sort((a,b) => a.priority-b.priority || a.label.localeCompare(b.label))
}
