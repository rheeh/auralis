export const QWEN_DRAMA_MODEL = 'qwen-audio-3.0-tts-plus'

// Historical Demo recordings retain their original model/voice identity.
export const QWEN_DRAMA_VOICES = [
  { voice: 'Moon', label: '月白 · 青年男声', role: '都市男角', sample: 'moon' },
  { voice: 'Maia', label: '四月 · 知性女声', role: '都市女角', sample: 'maia' },
  { voice: 'Vincent', label: '田叔 · 沙哑男声', role: '旁白', sample: 'vincent' },
]

export const QWEN_AUDIO_VOICES = {
  'qwen-audio-3.0-tts-plus': [
    { voice: 'longanlingxin', label: '龙安灵心 · 温暖女声', role: '都市女角', sampleFile: 'free-auditions/qwen-audio-plus-lingxin.mp3' },
    { voice: 'longanlufeng', label: '龙安鲁风 · 明亮男声', role: '都市男角', sampleFile: 'free-auditions/qwen-audio-plus-lufeng.mp3' },
  ],
  'qwen-audio-3.0-tts-flash': [
    { voice: 'longanfengyue', label: '龙安风悦 · 自然女声', role: '都市女角', sampleFile: 'free-auditions/qwen-audio-flash-fengyue.mp3' },
    { voice: 'longanhuan_v3.6', label: '龙安欢 · 青年女声', role: '都市女角' },
    { voice: 'longchuanshu_v3.6', label: '龙川叔 · 川普男声', role: '成熟角色' },
  ],
}

export function qwenDramaVoices(model) {
  return QWEN_AUDIO_VOICES[String(model || '').toLowerCase()] || QWEN_DRAMA_VOICES
}

export function isQwenDramaModel(model) {
  return !!QWEN_AUDIO_VOICES[String(model || '').toLowerCase()] || /^qwen3-tts-instruct-flash(?:-\d{4}-\d{2}-\d{2})?$/.test(String(model || '').toLowerCase())
}

// Mirror ConfigurableCloudTTSEngine; CosyVoice capability belongs to the voice,
// so the provider card describes its configured default voice only.
export function ttsCapability(provider, voiceName) {
  if (provider?.provider_type === 'edge') return { label: '基础韵律', type: 'info', mode: 'mapped' }
  let params = {}
  try { params = typeof provider?.custom_params === 'object' ? provider.custom_params || {} : JSON.parse(provider?.custom_params || '{}') } catch { params = {} }
  if (!params || typeof params !== 'object' || Array.isArray(params)) params = {}
  const model = String(provider?.model || '').toLowerCase()
  const configured = params.instruction_mode
  let mode = 'none'
  if (model.startsWith('cosyvoice')) {
    if (['mapped', 'none'].includes(configured)) mode = configured
    else if (params.supports_instruction === false || /^cosyvoice-v[12]/.test(model)) mode = 'mapped'
    else if (model.startsWith('cosyvoice-v3.5')) mode = 'native'
    else if (/^cosyvoice-v3-(flash|plus)/.test(model)) {
      const voice = voiceName || params.voice || 'longanyang'
      mode = ['longanyang', 'longanhuan', 'longhuhu_v3'].includes(voice) ? 'structured'
        : model.startsWith('cosyvoice-v3-flash') && voice.startsWith('cosyvoice-') ? 'native' : 'mapped'
    } else if (['native', 'structured'].includes(configured)) mode = configured
    else if (params.supports_instruction === true) mode = 'native'
  } else if (JSON.stringify(params.payload || params.body || {}).includes('{{instruction}}')) mode = 'native'
  else if (params.supports_instruction !== false && params.instruction_field !== false && (
    params.instruction_field || !!QWEN_AUDIO_VOICES[model] || (model.includes('qwen') && model.includes('instruct')) || (model.startsWith('gpt-4o') && model.includes('tts'))
  )) mode = 'native'
  return {
    native: { label: '原生表演指令', type: 'success', mode },
    structured: { label: '固定情感指令', type: 'success', mode },
    mapped: { label: '基础韵律', type: 'warning', mode },
    none: { label: '基础生成', type: 'info', mode },
  }[mode]
}
