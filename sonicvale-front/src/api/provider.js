import request from './config'

/**
 * LLM Providers
 */

// 获取 LLM 提供商列表
export function fetchLLMProviders() {
  return request.get('/llm_providers/').then(res => {
    if (res.code === 200) {
      return res.data
    }
    return []
  })
}

// 创建 LLM 提供商
export function createLLMProvider(payload) {
  // payload: { name, api_base_url, api_key?, model_list?, status? }
  return request.post('/llm_providers/', payload)
}

// 更新 LLM 提供商
export function updateLLMProvider(id, payload) {
  return request.put(`/llm_providers/${id}`, payload)
}

// 删除 LLM 提供商
export function deleteLLMProvider(id) {
  return request.delete(`/llm_providers/${id}`)
}
// 测试 LLM 提供商
export function testLLMProvider(data) {
  return request.post('/llm_providers/test', data)
}

// 获取 TTS 提供商
export function fetchTTSProviders() {
  return request.get('/tts_providers').then(res => {
    if (res.code === 200) {
      return res.data
    }
    
    // 如果后端暂时没实现接口，就返回默认值，避免前端报错
  })
}

// 创建 TTS 提供商
export function createTTSProvider(payload) {
  return request.post('/tts_providers/', payload)
}

// 更新 TTS 提供商
export function updateTTSProvider(id, payload) {
  return request.put(`/tts_providers/${id}`, payload)
}

// 删除 TTS 提供商
export function deleteTTSProvider(id) {
  return request.delete(`/tts_providers/${id}`)
}

// 测试 TTS 引擎
export function testTTSProvider(data) {
  return request.post('/tts_providers/test', data)
}
