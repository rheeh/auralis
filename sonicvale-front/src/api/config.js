// src/api/config.js
import axios from 'axios'
import { unwrapResponse, normalizeError } from './response.js'
import { handleDemoRequest } from '../demo/mockApi'

export const IS_STATIC_DEMO = import.meta.env.MODE === 'demo'
export const API_BASE_URL = IS_STATIC_DEMO ? './' : `${(globalThis.auralisRuntime?.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8200').replace(/\/$/, '')}/`

const service = axios.create({
  baseURL: API_BASE_URL, // 统一前缀，根据你的后端改
  timeout: 30000
})

if (IS_STATIC_DEMO) {
  service.defaults.adapter = async config => ({
    data: await handleDemoRequest(config),
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  })
}

// 请求拦截器
service.interceptors.request.use(
  config => {
    if(globalThis.auralisRuntime?.instanceToken)config.headers['X-Auralis-Token']=globalThis.auralisRuntime.instanceToken
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
service.interceptors.response.use(
  response => unwrapResponse(response.data),
  error => {
    console.error('API Error:', error)
    return Promise.reject(normalizeError(error))
  }
)

export default service

export function localMediaUrl(url) {
  const token=globalThis.auralisRuntime?.instanceToken
  return token ? `${url}${url.includes('?')?'&':'?'}instance_token=${encodeURIComponent(token)}` : url
}
