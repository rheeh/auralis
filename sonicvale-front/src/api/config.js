// src/api/config.js
import axios from 'axios'

export const API_BASE_URL = 'http://127.0.0.1:8200/'

const service = axios.create({
  baseURL: API_BASE_URL, // 统一前缀，根据你的后端改
  timeout: 1000000
})

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
