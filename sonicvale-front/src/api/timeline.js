import { localMediaUrl } from './config'
import request, { API_BASE_URL } from './config'

export function fetchChapterTimeline(projectId, chapterId) {
  return request.get(`/projects/${projectId}/chapters/${chapterId}/timeline`)
}

export function buildChapterTimeline(projectId, chapterId, options = {}) {
  return request.post(`/projects/${projectId}/chapters/${chapterId}/timeline/build`, null, {
    params: {
      force: options.force ?? false,
      overwrite_manual: options.overwrite_manual ?? false,
    },
  })
}

export function updateTimelineClip(projectId, chapterId, clipId, payload) {
  return request.patch(`/projects/${projectId}/chapters/${chapterId}/timeline/clips/${clipId}`, payload)
}

export function renderChapterTimeline(projectId, chapterId) {
  // The local FFmpeg call is bounded to 600s by the backend.
  return request.post(`/projects/${projectId}/chapters/${chapterId}/timeline/render`, null, { timeout: 620000 })
}

export function fetchLatestTimelineRender(projectId, chapterId) {
  return request.get(`/projects/${projectId}/chapters/${chapterId}/timeline/render`)
}

export function getTimelineRenderAudioUrl(projectId, chapterId, version = 0) {
  const query = version ? `?v=${encodeURIComponent(version)}` : ''
  return localMediaUrl(`${API_BASE_URL}projects/${projectId}/chapters/${chapterId}/timeline/render/audio${query}`)
}
