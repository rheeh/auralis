import request, { API_BASE_URL } from './config'

export function getSoundLibraryAssets(params = {}) {
  return request.get('/sound-library/assets', { params })
}

export function importSoundLibraryPath(payload) {
  return request.post('/sound-library/assets/import-path', payload)
}

export function uploadSoundLibraryFile(file, metadata) {
  const form = new FormData()
  form.append('file', file)
  form.append('name', metadata.name || '')
  form.append('category', metadata.category || 'foley')
  form.append('tags', metadata.tags || '')
  return request.post('/sound-library/assets/upload', form)
}

export function bindSoundLibraryAsset(assetId, lineId) {
  return request.post(`/sound-library/assets/${encodeURIComponent(assetId)}/bind/${lineId}`)
}

export function insertSoundLibraryAsset(assetId, payload) {
  return request.post(`/sound-library/assets/${encodeURIComponent(assetId)}/insert`, payload)
}

export function deleteSoundLibraryAsset(assetId) {
  return request.delete(`/sound-library/assets/${encodeURIComponent(assetId)}`)
}

export function getSoundLibraryAudioUrl(assetId, version = 0) {
  const query = version ? `?v=${encodeURIComponent(version)}` : ''
  return `${API_BASE_URL}sound-library/assets/${encodeURIComponent(assetId)}/audio${query}`
}
