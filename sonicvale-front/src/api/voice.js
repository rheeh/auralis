import request from './config'
import { API_BASE_URL } from './config'

// 创建音色
export function createVoice(payload) {
  // payload: { name, tts_provider_id, reference_path?, description? }
  return request.post('/voices', payload)
}

// 查询单个音色
export function fetchVoice(id) {
  return request.get(`/voices/${id}`).then(res => {
    if (res.code === 200) return res.data
    return null
  })
}

export function getVoiceAudioUrl(voiceId, version = 0) {
  const query = version ? `?v=${encodeURIComponent(version)}` : ''
  return `${API_BASE_URL}voices/${voiceId}/audio${query}`
}

// 查询某个 TTS Provider 下的所有音色
export function fetchVoicesByTTS(tts_provider_id) {
  return request.get(`/voices/tts/${tts_provider_id}`).then(res => {
    if (res.code === 200) return res.data
    return []
  })
}

export function getVoicesByTTS(ttsId = 1) {
  return request.get(`/voices/tts/${ttsId}`)
}



// 更新音色
export function updateVoice(id, payload) {
  return request.put(`/voices/${id}`, payload)
}

// 删除音色
export function deleteVoice(id) {
  return request.delete(`/voices/${id}`)
}

// 导出音色库
export function exportVoices(tts_provider_id, export_path, voice_ids = null) {
  const payload = { tts_provider_id, export_path }
  if (Array.isArray(voice_ids) && voice_ids.length > 0) payload.ids = voice_ids
  return request.post('/voices/export', payload)
}

// 导入音色库
export function importVoices(tts_provider_id, zip_path, target_dir) {
  return request.post('/voices/import', {
    tts_provider_id,
    zip_path,
    target_dir
  })
}

// 使用 Edge-TTS 生成内置常见音色样例并写入音色库
export function seedEdgeVoicePresets(tts_provider_id, options = {}) {
  return request.post('/voices/presets/edge', {
    tts_provider_id,
    target_dir: options.target_dir || null,
    overwrite: !!options.overwrite,
  })
}

export function seedCosyVoicePresets(tts_provider_id, options = {}) {
  return request.post('/voices/presets/cosyvoice', {
    tts_provider_id,
    target_dir: options.target_dir || null,
    overwrite: !!options.overwrite,
  })
}

// 处理音色参考音频
export function processVoiceAudio(audio_path, params) {
  return request.post('/voices/process-audio', {
    audio_path,
    speed: params.speed,
    volume: params.volume,
    start_ms: params.start_ms,
    end_ms: params.end_ms,
    silence_sec: params.silence_sec,
    current_ms: params.current_ms
  })
}

// 复制音色
export function copyVoice(source_voice_id, new_name, target_dir = null) {
  return request.post('/voices/copy', {
    source_voice_id,
    new_name,
    target_dir
  })
}
