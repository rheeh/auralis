export function unwrapResponse(data) {
  if (data && typeof data.code === 'number' && data.code >= 400) {
    const error = new Error(data.message || data.detail || '请求失败')
    error.response = { data, status: data.code }
    throw error
  }
  return data
}
export function normalizeError(error) {
  const data=error?.response?.data
  if(data?.message || typeof data?.detail==='string')error.message=data.message||data.detail
  return error
}
