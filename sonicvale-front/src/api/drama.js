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

export function previewArticleSource(data) {
  return request.post('/chat/article-sources/preview', data)
}

export function importArticleSource(data) {
  return request.post('/chat/article-sources/import', data)
}

export function fetchArticleSource(sourceId) {
  return request.get(`/chat/article-sources/${sourceId}`)
}

export function normalizeArticleSource(sourceId, sourceText = null) {
  return request.post(`/chat/article-sources/${sourceId}/normalize`, { source_text: sourceText })
}

export function analyzeArticleSession(sessionId) {
  return request.post(`/chat/sessions/${sessionId}/article/analyze`)
}

export function fetchArticleAnalysis(sessionId) {
  return request.get(`/chat/sessions/${sessionId}/article/analysis`)
}

export function confirmArticleOutline(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/article/outline/confirm`, data)
}

export function reviseArticleOutline(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/article/outline/revise`, data)
}

export function generateKnowledgeScript(sessionId) {
  return request.post(`/chat/sessions/${sessionId}/article/script/generate`)
}

export function fetchKnowledgeReview(sessionId) {
  return request.get(`/chat/sessions/${sessionId}/article/review`)
}

export function reviseKnowledgeScript(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/article/script/revise`, data)
}

export function confirmKnowledgeScript(sessionId, data) {
  return request.post(`/chat/sessions/${sessionId}/article/script/confirm`, data)
}

export function fetchKnowledgePoints(sessionId) {
  return request.get(`/chat/sessions/${sessionId}/knowledge-points`)
}

export function fetchReviewQuestions(sessionId) {
  return request.get(`/chat/sessions/${sessionId}/review-questions`)
}

export function answerReviewQuestion(sessionId, questionId, answer) {
  return request.post(`/chat/sessions/${sessionId}/review-questions/${questionId}/answer`, { answer })
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
