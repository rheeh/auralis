import request from './config'

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
