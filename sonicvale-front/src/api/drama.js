import request from './config'
import { API_BASE_URL } from './config'

export function createDramaAdaptation(data) {
  return request.post('/drama-adaptation/runs', data)
}

export function getDramaAdaptation(runId) {
  return request.get(`/drama-adaptation/runs/${runId}`)
}

export function fetchDramaAdaptations(params = {}) {
  return request.get('/drama-adaptation/runs', { params })
}

export function commitDramaAdaptation(data) {
  return request.post('/drama-adaptation/commit', data)
}

export function createChatSession(data) {
  return request.post('/chat/sessions', data)
}

export function fetchWorkflowCapabilities() {
  return request.get('/chat/capabilities')
}

export function fetchChatSessions(params = {}) {
  return request.get('/chat/sessions', { params })
}

export function fetchChatSession(sessionId) {
  return request.get(`/chat/sessions/${sessionId}`)
}

export function fetchChatHistory(sessionId, params = {}) {
  return request.get(`/chat/sessions/${sessionId}/history`, { params })
}

export function uploadRoleAvatar(sessionId, file) {
  const data = new FormData()
  data.append('file', file)
  return request.post(`/chat/sessions/${sessionId}/role-avatar`, data)
}

export function getRoleAvatarUrl(sessionId, avatarPath) {
  if (!avatarPath) return ''
  const filename = String(avatarPath).split(/[\\/]/).pop()
  return `${API_BASE_URL}chat/sessions/${sessionId}/role-avatar/${encodeURIComponent(filename)}`
}

export function fetchChatEvents(sessionId, params = {}) {
  return request.get(`/chat/sessions/${sessionId}/events`, { params })
}

export function sendChatMessage(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/message`, data)
}

export function confirmChatDraft(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/confirm`, data)
}

export function resumeChatSession(sessionId) {
  return request.post(`/chat/sessions/${sessionId}/resume`)
}

export function commitChatSession(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/commit`, data)
}

export function cancelChatSession(sessionId, clientRequestId) {
  return request.post(`/chat/sessions/${sessionId}/cancel`, null, { params: { client_request_id: clientRequestId } })
}

export function fetchSessionAudioTasks(sessionId) {
  return request.get(`/chat/sessions/${sessionId}/audio-tasks`)
}

export function generateSessionAudio(sessionId, force = false) {
  return request.post(`/chat/sessions/${sessionId}/audio-tasks/generate`, null, { params: { force } })
}

export function retrySessionAudioTask(sessionId, taskId) {
  return request.post(`/chat/sessions/${sessionId}/audio-tasks/${taskId}/retry`)
}

export function reviewSessionAudioTask(sessionId, taskId, data) {
  return request.post(`/chat/sessions/${sessionId}/audio-tasks/${taskId}/review`, data)
}

export function regenerateLineAudio(sessionId, lineId, prompt = '') {
  return request.post(`/chat/sessions/${sessionId}/audio-tasks/lines/${lineId}/regenerate`, { prompt })
}
