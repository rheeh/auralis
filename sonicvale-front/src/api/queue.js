import request from './config'

export function fetchQueueStatus() {
  return request.get('/queue/status')
}

export function fetchRecentAudioTasks(params = {}) {
  return request.get('/queue/audio-tasks', { params })
}
