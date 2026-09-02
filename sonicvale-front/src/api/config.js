// src/api/config.js
import axios from 'axios'
import { handleDemoRequest } from '../demo/mockApi'

export const IS_STATIC_DEMO = import.meta.env.MODE === 'demo'
export const API_BASE_URL = IS_STATIC_DEMO ? './' : 'http://127.0.0.1:8200/'

const service = axios.create({
  baseURL: API_BASE_URL, // 统一前缀，根据你的后端改
  timeout: 1000000
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
    // 这里可以加 token
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
service.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default service
