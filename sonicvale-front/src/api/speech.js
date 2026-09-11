import service from './config'

export const getSpeechSettings = projectId => service.get(`/projects/${projectId}/speech-settings`)
export const saveSpeechSettings = (projectId, settings) => service.put(`/projects/${projectId}/speech-settings`, settings)
export const getSpeechPreview = (projectId, lineId) => service.get(`/projects/${projectId}/lines/${lineId}/speech-preview`)
export const getSpeechGenerations = (projectId, lineId, before) => service.get(`/projects/${projectId}/tts-generations`, { params: { line_id: lineId, limit: 10, before } })
