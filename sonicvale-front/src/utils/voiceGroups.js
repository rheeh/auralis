export function providerOptions(provider) {
  try { return typeof provider?.custom_params === 'object' ? provider.custom_params || {} : JSON.parse(provider?.custom_params || '{}') } catch { return {} }
}
export function groupVoices(providers, voices, query = '') {
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
  return [...groups.values()].map(g => ({ ...g, total: g.voices.length, voices: g.voices.filter(v => !needle || `${v.name} ${v.description || ''} ${g.label}`.toLowerCase().includes(needle)) })).filter(g => g.voices.length).sort((a,b) => a.priority-b.priority || a.label.localeCompare(b.label))
}
