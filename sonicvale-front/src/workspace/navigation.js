export const WORKSPACE_VIEWS = ['source', 'script', 'voices', 'timeline', 'export']
export function defaultWorkspaceView(stage) {
  if (stage === 'completed') return 'voices'
  return stage ? 'script' : 'source'
}
export function workspaceLocation(projectId, chapterId, view = 'voices', lineId = null) {
  return { path: `/projects/${Number(projectId)}/workspace`, query: {
    ...(chapterId ? { chapter_id: String(chapterId) } : {}),
    view: WORKSPACE_VIEWS.includes(view) ? view : 'voices',
    ...(lineId ? { line_id: String(lineId) } : {}),
  } }
}
export function resolveWorkspaceView(requested, stage, chapterId) {
  if (!WORKSPACE_VIEWS.includes(requested)) return defaultWorkspaceView(stage)
  if (['voices','timeline','export'].includes(requested) && (stage !== 'completed' || !chapterId)) return defaultWorkspaceView(stage)
  return requested
}
